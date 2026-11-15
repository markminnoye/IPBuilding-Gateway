#!/usr/bin/env python3
"""IP0300PoE dimmer calibration toolkit (status, sweep, analyze, apply).

Measures the physical ignition threshold (dimMin), saturation ceiling (dimMax),
and perceptual curve (dim_gamma) of an IP0300PoE dimmer channel using fixed-exposure
video (AE/AF Lock) + ffprobe luma (YAVG) analysis.

Usage examples:
  python3 scripts/calibrate_dimmer.py status
  python3 scripts/calibrate_dimmer.py sweep --channel 1
  python3 scripts/calibrate_dimmer.py analyze --video ~/Desktop/IMG_8060.MOV --sweep-log /tmp/dimmer_sweep_ch1.json
  python3 scripts/calibrate_dimmer.py apply --channel 1 --dim-min 16 --dim-max 68 --dim-gamma 2.2
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MODULE_IP = "10.10.1.40"
DEFAULT_GATEWAY_URL = "http://192.168.1.3:8080"
DEFAULT_STEPS = [
    5, 8, 10, 12, 14, 16, 18, 20, 22, 25,
    30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100,
]
DEFAULT_HOLD_S = 2.5
SYNC_ON_S = 2.0
SYNC_OFF_S = 3.0
POST_SWEEP_OFF_S = 2.0


@dataclass
class StepMeasurement:
    level: int
    start_s: float
    end_s: float
    yavg: float
    norm_luma: float
    state: str


@dataclass
class CalibrationResult:
    t_sync_off_s: float
    y_dark: float
    y_max: float
    measured_dim_min: int
    recommended_dim_min: int
    recommended_dim_max: int
    recommended_dim_gamma: float
    steps: list[StepMeasurement]


def format_uitgang(module_ip: str, channel: int) -> str:
    """Format physical cabinet address <last-octet>.<block>.<pin> (8 ch/block)."""
    octet = module_ip.split(".")[-1]
    block = (channel // 8) + 1
    pin = (channel % 8) + 1
    return f"{octet}.{block}.{pin}"


def parse_steps(raw: str) -> list[int]:
    """Parse comma-separated integer dimmer percentages (1..100)."""
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        val = int(part)
        if not 1 <= val <= 100:
            raise ValueError(f"Step percentage must be 1..100, got {val}")
        values.append(val)
    if len(values) < 2:
        raise ValueError("At least 2 steps are required")
    return sorted(set(values))


def _http_request(
    url: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> str:
    data: bytes | None = None
    headers: dict[str, str] = {}
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection failed {method} {url}: {exc.reason}") from exc


def fetch_module_statuses(module_ip: str, timeout: float = 5.0) -> list[dict[str, Any]]:
    """Read live channel statuses + dimMin/dimMax from IP0300PoE."""
    url = f"http://{module_ip}/api.html?method=statuses"
    raw = _http_request(url, timeout=timeout)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected statuses payload from {module_ip}: {raw[:200]}")
    return data


def save_module_channel(
    module_ip: str,
    channel: int,
    descr: str,
    gr: str,
    dim_min: int,
    dim_max: int,
    timeout: float = 5.0,
) -> str:
    """Persist descr/gr/dimMin/dimMax for one channel on IP0300PoE."""
    if not 0 <= channel <= 7:
        raise ValueError(f"channel must be 0..7, got {channel}")
    if not 0 <= dim_min < dim_max <= 100:
        raise ValueError(
            f"dimMin/dimMax must satisfy 0 <= dimMin < dimMax <= 100, "
            f"got {dim_min}..{dim_max}"
        )
    ds_q = urllib.parse.quote(descr, safe="")
    gr_q = urllib.parse.quote(gr, safe="")
    url = (
        f"http://{module_ip}/api.html?method=saveChannel"
        f"&ds={ds_q}&gr={gr_q}&dimMax={dim_max}&dimMin={dim_min}&ch={channel}"
    )
    return _http_request(url, timeout=timeout)


def fetch_gateway_devices(
    gateway_url: str, timeout: float = 5.0
) -> list[dict[str, Any]]:
    """Read full device list (including inactive) from Gateway REST API."""
    base = gateway_url.rstrip("/")
    raw = _http_request(f"{base}/api/v1/devices?include_inactive=1", timeout=timeout)
    data = json.loads(raw)
    devices = data.get("devices")
    if not isinstance(devices, list):
        raise RuntimeError(f"Unexpected /api/v1/devices payload: {raw[:200]}")
    return devices


def find_gateway_device(
    devices: list[dict[str, Any]], module_ip: str, channel: int
) -> dict[str, Any] | None:
    """Find the dimmer channel entry in the Gateway device list."""
    for dev in devices:
        if (
            dev.get("module_ip") == module_ip
            and dev.get("channel") == channel
            and dev.get("device_type") == "dimmer"
        ):
            return dev
    return None


def patch_gateway_device(
    gateway_url: str,
    device_id: str,
    patch: dict[str, Any],
    timeout: float = 5.0,
) -> dict[str, Any]:
    """PATCH northbound config fields (dim_gamma, default_fade) on Gateway."""
    base = gateway_url.rstrip("/")
    dev_q = urllib.parse.quote(device_id, safe="")
    raw = _http_request(
        f"{base}/api/v1/devices/{dev_q}",
        method="PATCH",
        json_body=patch,
        timeout=timeout,
    )
    return json.loads(raw)


def send_gateway_command(
    gateway_url: str,
    device_id: str,
    action: str,
    value: int | None = None,
    fade: int = 0,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Send a dimmer command through the Gateway REST API."""
    base = gateway_url.rstrip("/")
    dev_q = urllib.parse.quote(device_id, safe="")
    body: dict[str, Any] = {"action": action, "fade": fade}
    if value is not None:
        body["value"] = value
    raw = _http_request(
        f"{base}/api/v1/devices/{dev_q}/command",
        method="POST",
        json_body=body,
        timeout=timeout,
    )
    return json.loads(raw)


def _escape_lavfi_path(path: Path) -> str:
    s = str(path)
    return (
        s.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def extract_luma_from_video(video_path: Path, fps: int = 10) -> list[tuple[float, float]]:
    """Run ffprobe signalstats on video_path and return [(t_s, yavg), ...]."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    escaped = _escape_lavfi_path(video_path.resolve())
    filter_graph = f"movie='{escaped}',fps={fps},scale=64:36,signalstats"
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-f",
        "lavfi",
        filter_graph,
        "-show_entries",
        "frame=pts_time:frame_tags=lavfi.signalstats.YAVG",
        "-of",
        "csv=p=0",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    samples: list[tuple[float, float]] = []
    for line in proc.stdout.splitlines():
        parts = [p for p in line.strip().split(",") if p != ""]
        if len(parts) < 2:
            continue
        try:
            t_s = float(parts[0])
            yavg = float(parts[1])
        except ValueError:
            continue
        samples.append((t_s, yavg))
    if not samples:
        raise RuntimeError(f"No YAVG frames extracted from {video_path}")
    return samples


def _rolling_median(values: list[float], radius: int = 1) -> list[float]:
    n = len(values)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - radius)
        hi = min(n, i + radius + 1)
        out.append(statistics.median(values[lo:hi]))
    return out


def detect_sync_off_time(
    samples: list[tuple[float, float]],
    *,
    sync_on_s: float = SYNC_ON_S,
    sync_off_s: float = SYNC_OFF_S,
) -> float:
    """Detect the falling edge (ON 100% -> OFF 0%) of the initial sync pulse."""
    if len(samples) < 5:
        raise ValueError("Not enough frames to detect sync pulse")

    t0 = samples[0][0]
    search_end = t0 + max(12.0, sync_on_s + sync_off_s + 8.0)
    head = [(t, y) for t, y in samples if t <= search_end]
    if len(head) < 5:
        head = samples

    smooth_y = _rolling_median([y for _, y in head], radius=1)
    peak_idx = max(range(len(smooth_y)), key=lambda idx: smooth_y[idx])
    t_peak, y_peak = head[peak_idx][0], smooth_y[peak_idx]

    post_peak = [
        y
        for t, y in samples
        if t_peak + 0.3 <= t <= t_peak + sync_on_s + sync_off_s + 1.0
    ]
    if not post_peak:
        post_peak = [y for t, y in samples if t > t_peak]
    if not post_peak:
        raise ValueError("No post-peak frames found to establish dark baseline")

    sorted_post = sorted(post_peak)
    low_count = max(1, len(sorted_post) // 3)
    y_dark_init = statistics.median(sorted_post[:low_count])

    if y_peak - y_dark_init < 1.0:
        raise ValueError(
            f"Sync pulse contrast too low (peak={y_peak:.2f}, dark={y_dark_init:.2f})"
        )

    midpoint = (y_peak + y_dark_init) / 2.0
    for idx in range(peak_idx, len(samples)):
        t, y = samples[idx]
        if y <= midpoint:
            return t

    raise ValueError("Falling edge of initial ON->OFF sync pulse was not found")


def extract_step_yavg(
    samples: list[tuple[float, float]],
    start_t: float,
    end_t: float,
    *,
    trim_start_s: float = 0.6,
    trim_end_s: float = 0.2,
) -> float:
    """Return median YAVG inside the stabilized portion of a step window."""
    lo = start_t + trim_start_s
    hi = end_t - trim_end_s
    vals = [y for t, y in samples if lo <= t <= hi]
    if not vals:
        dur = max(0.0, end_t - start_t)
        vals = [
            y
            for t, y in samples
            if (start_t + 0.25 * dur) <= t <= (start_t + 0.75 * dur)
        ]
    if not vals:
        vals = [y for t, y in samples if start_t <= t <= end_t]
    if not vals:
        raise ValueError(f"No video samples inside window [{start_t:.2f}, {end_t:.2f}]")
    return float(statistics.median(vals))


def _interp_curve(x: float, xs: list[int], ys: list[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return ys[i]
            frac = (x - x0) / (x1 - x0)
            return ys[i] + frac * (ys[i + 1] - ys[i])
    return ys[-1]


def fit_dim_gamma(
    steps: list[int],
    norm_lumas: list[float],
    dim_min: int,
    dim_max: int,
) -> float:
    """Fit dim_gamma in [1.0, 3.5] against perceptual target L(u) = u^2.0."""
    if dim_max <= dim_min:
        return 1.0

    l_at_min = _interp_curve(float(dim_min), steps, norm_lumas)
    l_at_max = _interp_curve(float(dim_max), steps, norm_lumas)
    span = l_at_max - l_at_min

    u_grid = [0.05 * k for k in range(1, 20)]  # 0.05 .. 0.95
    best_gamma = 1.0
    best_err = float("inf")

    for step_idx in range(51):  # 1.00 .. 3.50 in 0.05 increments
        gamma = 1.0 + 0.05 * step_idx
        err = 0.0
        for u in u_grid:
            raw_pct = dim_min + (u ** gamma) * (dim_max - dim_min)
            raw_l = _interp_curve(raw_pct, steps, norm_lumas)
            if span > 0.05:
                l_eff = max(0.0, min(1.0, (raw_l - l_at_min) / span))
            else:
                l_eff = raw_l
            target = u ** 2.0
            diff = l_eff - target
            err += diff * diff
        if err < best_err:
            best_err = err
            best_gamma = gamma

    return round(max(1.0, min(3.5, best_gamma)), 2)


def analyze_luma_series(
    samples: list[tuple[float, float]],
    steps: list[int],
    hold_s: float,
    *,
    sync_on_s: float = SYNC_ON_S,
    sync_off_s: float = SYNC_OFF_S,
    step_offsets_s: list[float] | None = None,
    margin_min: int = 1,
    sat_threshold: float = 0.985,
) -> CalibrationResult:
    """Analyze a 10 Hz YAVG time series and derive dimMin, dimMax, and dim_gamma."""
    if step_offsets_s is not None and len(step_offsets_s) != len(steps):
        raise ValueError("step_offsets_s length must match steps length")
    if margin_min < 0:
        raise ValueError("margin_min must be >= 0")

    t_sync_off = detect_sync_off_time(
        samples, sync_on_s=sync_on_s, sync_off_s=sync_off_s
    )
    first_step_offset = step_offsets_s[0] if step_offsets_s else sync_off_s
    y_dark = extract_step_yavg(
        samples,
        t_sync_off,
        t_sync_off + first_step_offset,
    )

    step_windows: list[tuple[int, float, float, float]] = []
    for idx, pct in enumerate(steps):
        if step_offsets_s is not None:
            start_s = t_sync_off + step_offsets_s[idx]
            end_s = (
                t_sync_off + step_offsets_s[idx + 1]
                if idx + 1 < len(step_offsets_s)
                else start_s + hold_s
            )
        else:
            start_s = t_sync_off + sync_off_s + idx * hold_s
            end_s = start_s + hold_s
        yavg = extract_step_yavg(samples, start_s, end_s)
        step_windows.append((pct, start_s, end_s, yavg))

    y_max = max(item[3] for item in step_windows)
    span = y_max - y_dark
    if span <= 0.5:
        raise ValueError(
            f"Insufficient luma range between dark ({y_dark:.2f}) and max ({y_max:.2f})"
        )

    on_delta = max(3.0, 0.015 * span)
    on_threshold = y_dark + on_delta

    norm_lumas = [
        max(0.0, min(1.0, (yavg - y_dark) / span))
        for _, _, _, yavg in step_windows
    ]

    # Find lowest step where lamp stays visibly lit and monotonically non-falling.
    measured_min_idx: int | None = None
    for i in range(len(step_windows)):
        y_i = step_windows[i][3]
        if y_i <= on_threshold:
            continue
        if any(step_windows[j][3] <= on_threshold for j in range(i + 1, len(step_windows))):
            continue
        if i + 1 < len(step_windows) and step_windows[i + 1][3] < y_i - 0.5:
            continue
        measured_min_idx = i
        break

    if measured_min_idx is None:
        measured_min_idx = next(
            (i for i, (_, _, _, y) in enumerate(step_windows) if y > on_threshold),
            0,
        )

    measured_dim_min = step_windows[measured_min_idx][0]

    sat_idx = next(
        (i for i, norm in enumerate(norm_lumas) if norm >= sat_threshold),
        len(step_windows) - 1,
    )
    recommended_dim_max = max(2, min(100, step_windows[sat_idx][0]))
    recommended_dim_min = min(
        recommended_dim_max - 1,
        max(0, measured_dim_min + margin_min),
    )

    measurements: list[StepMeasurement] = []
    for idx, (pct, start_s, end_s, yavg) in enumerate(step_windows):
        norm = norm_lumas[idx]
        if yavg <= on_threshold:
            state = "OFF"
        elif norm >= sat_threshold or pct >= recommended_dim_max:
            state = "SATURATED"
        else:
            state = "ACTIVE"
        measurements.append(
            StepMeasurement(
                level=pct,
                start_s=round(start_s, 2),
                end_s=round(end_s, 2),
                yavg=round(yavg, 2),
                norm_luma=round(norm, 4),
                state=state,
            )
        )

    recommended_gamma = fit_dim_gamma(
        steps, norm_lumas, recommended_dim_min, recommended_dim_max
    )

    return CalibrationResult(
        t_sync_off_s=round(t_sync_off, 2),
        y_dark=round(y_dark, 2),
        y_max=round(y_max, 2),
        measured_dim_min=measured_dim_min,
        recommended_dim_min=recommended_dim_min,
        recommended_dim_max=recommended_dim_max,
        recommended_dim_gamma=recommended_gamma,
        steps=measurements,
    )


def cmd_status(args: argparse.Namespace) -> int:
    statuses = fetch_module_statuses(args.module_ip)
    devices = fetch_gateway_devices(args.gateway_url)
    by_ch = {int(entry["id"]): entry for entry in statuses if "id" in entry}

    print(f"IP0300PoE ({args.module_ip}) & Gateway ({args.gateway_url}):\n")
    print(
        "| Ch | Uitgang | Gateway naam | Module descr | Active | dimMin | dimMax | dim_gamma | default_fade | Status |"
    )
    print(
        "|---:|---------|--------------|--------------|--------|-------:|-------:|----------:|-------------:|-------:|"
    )
    for ch in range(8):
        mod = by_ch.get(ch, {})
        dev = find_gateway_device(devices, args.module_ip, ch) or {}
        uitgang = format_uitgang(args.module_ip, ch)
        gw_name = dev.get("name", "-")
        mod_descr = mod.get("descr", "-")
        active = dev.get("active", False)
        dim_min = mod.get("dimMin", "-")
        dim_max = mod.get("dimMax", "-")
        gamma = dev.get("dim_gamma", "-")
        fade = dev.get("default_fade", "-")
        status = mod.get("status", "-")
        print(
            f"| {ch} | {uitgang} | {gw_name} | {mod_descr} | {active} | "
            f"{dim_min} | {dim_max} | {gamma} | {fade} | {status} |"
        )
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    ch = args.channel
    steps = parse_steps(args.steps)
    output_path = Path(
        args.output or f"/tmp/dimmer_sweep_ch{ch}.json"
    )

    statuses = fetch_module_statuses(args.module_ip)
    mod_ch = next((s for s in statuses if int(s.get("id", -1)) == ch), None)
    if mod_ch is None:
        raise RuntimeError(f"Channel {ch} not found in {args.module_ip} statuses")

    devices = fetch_gateway_devices(args.gateway_url)
    gw_dev = find_gateway_device(devices, args.module_ip, ch)
    if gw_dev is None:
        raise RuntimeError(
            f"Dimmer device {args.module_ip} ch {ch} not found on {args.gateway_url}"
        )

    device_id = gw_dev["id"]
    if not gw_dev.get("active", True) and not args.force:
        raise RuntimeError(
            f"Device {device_id} ({gw_dev.get('name')}) is inactive. "
            "Pass --force to override."
        )

    orig_descr = str(mod_ch.get("descr", ""))
    orig_gr = str(mod_ch.get("gr", ""))
    orig_dim_min = int(mod_ch.get("dimMin", 0))
    orig_dim_max = int(mod_ch.get("dimMax", 100))
    orig_gamma = float(gw_dev.get("dim_gamma", 1.0) or 1.0)

    print(
        f"Target: {device_id} ({gw_dev.get('name')}, Uitgang {format_uitgang(args.module_ip, ch)})"
    )
    print(
        f"Backup: descr={orig_descr!r}, gr={orig_gr!r}, "
        f"dimMin={orig_dim_min}, dimMax={orig_dim_max}, dim_gamma={orig_gamma}"
    )

    if args.countdown > 0:
        print(
            f"Start iPhone video recording (AE/AF Lock, SDR 1080p) now! "
            f"Sweep begins in {args.countdown}s..."
        )
        for sec in range(args.countdown, 0, -1):
            print(f"  {sec}...", flush=True)
            time.sleep(1.0)

    events: list[dict[str, Any]] = []
    t0: float | None = None
    completed_cleanly = False

    def _restore_original() -> None:
        print(
            f"Restoring previous settings: dimMin={orig_dim_min}, "
            f"dimMax={orig_dim_max}, dim_gamma={orig_gamma}..."
        )
        save_module_channel(
            args.module_ip, ch, orig_descr, orig_gr, orig_dim_min, orig_dim_max
        )
        patch_gateway_device(args.gateway_url, device_id, {"dim_gamma": orig_gamma})

    try:
        print("Setting raw linear scale on module (dimMin=0, dimMax=100) and gateway (dim_gamma=1.0)...")
        save_module_channel(args.module_ip, ch, orig_descr, orig_gr, 0, 100)
        patch_gateway_device(args.gateway_url, device_id, {"dim_gamma": 1.0})

        t0 = time.monotonic()

        def _record_step(step_index: int | str, action: str, level: int, hold: float) -> None:
            assert t0 is not None
            t_rel = time.monotonic() - t0
            wall = datetime.now(timezone.utc).isoformat()
            res = send_gateway_command(
                args.gateway_url,
                device_id,
                action,
                value=level if action == "DIM" else None,
                fade=0,
            )
            entry = {
                "step_index": step_index,
                "action": action,
                "level": level,
                "t_rel_s": round(t_rel, 3),
                "wall_time": wall,
                "module_confirmed": res.get("module_confirmed"),
                "confirm_ms": res.get("confirm_ms"),
            }
            events.append(entry)
            print(
                f"  [{step_index}] {action} {level:3d}% @ t={t_rel:6.2f}s "
                f"(confirmed={entry['module_confirmed']}, {entry['confirm_ms']} ms)"
            )
            time.sleep(hold)

        _record_step("sync_on", "ON", 100, SYNC_ON_S)
        _record_step("sync_off", "OFF", 0, SYNC_OFF_S)
        for idx, pct in enumerate(steps):
            _record_step(idx, "DIM", pct, args.hold)
        _record_step("end_off", "OFF", 0, POST_SWEEP_OFF_S)
        completed_cleanly = True
    finally:
        if (completed_cleanly and not args.keep_raw) or (
            not completed_cleanly and args.restore_on_abort
        ):
            try:
                _restore_original()
            except Exception as exc:
                print(f"Warning: failed to restore original config: {exc}", file=sys.stderr)

    log_payload = {
        "schema_version": 1,
        "module_ip": args.module_ip,
        "channel": ch,
        "device_id": device_id,
        "device_name": gw_dev.get("name"),
        "uitgang": format_uitgang(args.module_ip, ch),
        "hold_s": args.hold,
        "sync_on_s": SYNC_ON_S,
        "sync_off_s": SYNC_OFF_S,
        "steps": steps,
        "previous_config": {
            "descr": orig_descr,
            "gr": orig_gr,
            "dimMin": orig_dim_min,
            "dimMax": orig_dim_max,
            "dim_gamma": orig_gamma,
        },
        "events": events,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")
    print(f"\nSweep log saved to {output_path}")
    print(
        "Next step: run\n"
        f"  python3 scripts/calibrate_dimmer.py analyze --video <path.MOV> --sweep-log {output_path}"
    )
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    video_path = Path(args.video).expanduser()
    step_offsets_s: list[float] | None = None
    channel: int | None = args.channel
    module_ip = args.module_ip

    if args.sweep_log:
        sweep_data = json.loads(Path(args.sweep_log).read_text(encoding="utf-8"))
        steps = [int(x) for x in sweep_data["steps"]]
        hold_s = float(sweep_data["hold_s"])
        sync_on_s = float(sweep_data.get("sync_on_s", SYNC_ON_S))
        sync_off_s = float(sweep_data.get("sync_off_s", SYNC_OFF_S))
        module_ip = sweep_data.get("module_ip", module_ip)
        if channel is None:
            channel = sweep_data.get("channel")
        events = sweep_data.get("events", [])
        sync_off_event = next(
            (e for e in events if e.get("step_index") == "sync_off"), None
        )
        step_events = [
            e for e in events if isinstance(e.get("step_index"), int)
        ]
        if sync_off_event is not None and len(step_events) == len(steps):
            t_off_rel = float(sync_off_event["t_rel_s"])
            step_offsets_s = [float(e["t_rel_s"]) - t_off_rel for e in step_events]
    else:
        steps = parse_steps(args.steps)
        hold_s = args.hold
        sync_on_s = SYNC_ON_S
        sync_off_s = SYNC_OFF_S

    samples = extract_luma_from_video(video_path)
    result = analyze_luma_series(
        samples,
        steps,
        hold_s,
        sync_on_s=sync_on_s,
        sync_off_s=sync_off_s,
        step_offsets_s=step_offsets_s,
        margin_min=args.margin_min,
        sat_threshold=args.sat_threshold,
    )

    print(
        f"Sync OFF detected at t={result.t_sync_off_s:.2f}s | "
        f"Y_dark={result.y_dark:.2f} | Y_max={result.y_max:.2f}\n"
    )
    print("| Raw % | Video window | YAVG | Norm % | State |")
    print("|------:|--------------|-----:|-------:|-------|")
    for s in result.steps:
        print(
            f"| {s.level:3d}% | {s.start_s:5.1f}–{s.end_s:5.1f}s | "
            f"{s.yavg:6.2f} | {s.norm_luma * 100:5.1f}% | {s.state} |"
        )

    print("\n### Recommended calibration")
    print(f"- Measured threshold `dimMin`: **{result.measured_dim_min}%**")
    print(
        f"- Recommended `dimMin` (margin +{args.margin_min}%): **{result.recommended_dim_min}%**"
    )
    print(
        f"- Recommended `dimMax` (sat >= {args.sat_threshold * 100:.1f}%): **{result.recommended_dim_max}%**"
    )
    print(f"- Recommended `dim_gamma`: **{result.recommended_dim_gamma:.2f}**")
    ch_arg = channel if channel is not None else "<ch>"
    print("\nApply command:")
    print(
        f"  python3 scripts/calibrate_dimmer.py apply "
        f"--module-ip {module_ip} --channel {ch_arg} "
        f"--dim-min {result.recommended_dim_min} "
        f"--dim-max {result.recommended_dim_max} "
        f"--dim-gamma {result.recommended_dim_gamma:.2f}"
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    ch = args.channel
    statuses = fetch_module_statuses(args.module_ip)
    mod_ch = next((s for s in statuses if int(s.get("id", -1)) == ch), None)
    if mod_ch is None:
        raise RuntimeError(f"Channel {ch} not found in {args.module_ip} statuses")

    descr = str(mod_ch.get("descr", ""))
    gr = str(mod_ch.get("gr", ""))
    print(
        f"Saving IP0300PoE {args.module_ip} ch {ch} ({descr!r}): "
        f"dimMin={args.dim_min}, dimMax={args.dim_max}..."
    )
    save_module_channel(
        args.module_ip, ch, descr, gr, args.dim_min, args.dim_max
    )

    verify_statuses = fetch_module_statuses(args.module_ip)
    verified = next((s for s in verify_statuses if int(s.get("id", -1)) == ch), None)
    if (
        verified is None
        or int(verified.get("dimMin", -1)) != args.dim_min
        or int(verified.get("dimMax", -1)) != args.dim_max
    ):
        raise RuntimeError(
            f"Verification failed on {args.module_ip} ch {ch}: got {verified}"
        )
    print(
        f"Verified on module: dimMin={verified['dimMin']}, dimMax={verified['dimMax']}"
    )

    patch: dict[str, Any] = {}
    if args.dim_gamma is not None:
        patch["dim_gamma"] = args.dim_gamma
    if args.default_fade is not None:
        patch["default_fade"] = args.default_fade

    if patch:
        devices = fetch_gateway_devices(args.gateway_url)
        gw_dev = find_gateway_device(devices, args.module_ip, ch)
        if gw_dev is None:
            raise RuntimeError(
                f"Dimmer device {args.module_ip} ch {ch} not found on {args.gateway_url}"
            )
        device_id = gw_dev["id"]
        updated = patch_gateway_device(args.gateway_url, device_id, patch)
        print(
            f"Verified on gateway ({device_id}): "
            f"dim_gamma={updated.get('dim_gamma')}, "
            f"default_fade={updated.get('default_fade')}"
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate IP0300PoE dimmer channels (dimMin, dimMax, dim_gamma)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show live module + gateway dimmer status.")
    p_status.add_argument("--module-ip", default=DEFAULT_MODULE_IP)
    p_status.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)

    p_sweep = sub.add_parser(
        "sweep",
        help="Temporarily switch channel to raw 0..100 and run a fade=0 step sweep.",
    )
    p_sweep.add_argument("--channel", type=int, required=True, choices=range(8))
    p_sweep.add_argument("--module-ip", default=DEFAULT_MODULE_IP)
    p_sweep.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    p_sweep.add_argument("--hold", type=float, default=DEFAULT_HOLD_S)
    p_sweep.add_argument(
        "--steps",
        default=",".join(str(x) for x in DEFAULT_STEPS),
        help="Comma-separated dimmer levels (1..100).",
    )
    p_sweep.add_argument(
        "--output",
        default=None,
        help="Sweep log JSON output path (default: /tmp/dimmer_sweep_ch<N>.json).",
    )
    p_sweep.add_argument(
        "--countdown",
        type=int,
        default=3,
        help="Countdown seconds before starting sync pulse (default: 3).",
    )
    p_sweep.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep raw dimMin=0, dimMax=100, dim_gamma=1.0 after sweep finishes.",
    )
    p_sweep.add_argument(
        "--no-restore-on-abort",
        dest="restore_on_abort",
        action="store_false",
        default=True,
        help="Do not restore previous dimMin/dimMax/dim_gamma if sweep aborts.",
    )
    p_sweep.add_argument(
        "--force",
        action="store_true",
        help="Allow sweep even if channel is marked inactive on the gateway.",
    )

    p_analyze = sub.add_parser(
        "analyze",
        help="Analyze an AE/AF-locked video with ffprobe and compute dimMin/dimMax/dim_gamma.",
    )
    p_analyze.add_argument("--video", required=True, help="Path to recorded .MOV/.MP4 video.")
    p_analyze.add_argument(
        "--sweep-log",
        default=None,
        help="JSON sweep log produced by `sweep` (overrides --hold/--steps timing).",
    )
    p_analyze.add_argument("--channel", type=int, default=None, choices=range(8))
    p_analyze.add_argument("--module-ip", default=DEFAULT_MODULE_IP)
    p_analyze.add_argument("--hold", type=float, default=DEFAULT_HOLD_S)
    p_analyze.add_argument(
        "--steps",
        default=",".join(str(x) for x in DEFAULT_STEPS),
        help="Comma-separated dimmer levels used if --sweep-log is omitted.",
    )
    p_analyze.add_argument(
        "--margin-min",
        type=int,
        default=1,
        help="Safety margin (%%) added on top of measured dimMin (default: 1).",
    )
    p_analyze.add_argument(
        "--sat-threshold",
        type=float,
        default=0.985,
        help="Normalized luma threshold (0..1) for dimMax saturation (default: 0.985).",
    )

    p_apply = sub.add_parser(
        "apply",
        help="Persist dimMin/dimMax on IP0300PoE and dim_gamma/default_fade on Gateway.",
    )
    p_apply.add_argument("--channel", type=int, required=True, choices=range(8))
    p_apply.add_argument("--dim-min", type=int, required=True)
    p_apply.add_argument("--dim-max", type=int, required=True)
    p_apply.add_argument("--dim-gamma", type=float, default=None)
    p_apply.add_argument("--default-fade", type=int, default=None)
    p_apply.add_argument("--module-ip", default=DEFAULT_MODULE_IP)
    p_apply.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "sweep":
        return cmd_sweep(args)
    if args.command == "analyze":
        return cmd_analyze(args)
    if args.command == "apply":
        return cmd_apply(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
