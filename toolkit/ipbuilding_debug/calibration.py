"""IP0300PoE dimmer calibration helpers (ffprobe luma analysis & module HTTP)."""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import statistics
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

DEFAULT_SWEEP_STEPS: tuple[int, ...] = (
    5,
    8,
    10,
    12,
    14,
    16,
    18,
    20,
    22,
    25,
    30,
    35,
    40,
    45,
    50,
    55,
    60,
    65,
    70,
    75,
    80,
    85,
    90,
    95,
    100,
)
DEFAULT_SYNC_ON_SECONDS = 2.0
DEFAULT_SYNC_OFF_SECONDS = 3.0
DEFAULT_HOLD_SECONDS = 2.5


def format_uitgang(module_ip: str, channel: int) -> str:
    """Format physical cabinet address ``<last-octet>.<block>.<pin>`` (8 ch/block)."""
    octet = module_ip.split(".")[-1] if module_ip else "?"
    block = (channel // 8) + 1
    pin = (channel % 8) + 1
    return f"{octet}.{block}.{pin}"


def parse_steps(raw: str | list[int] | tuple[int, ...] | None) -> list[int]:
    """Parse dimmer percentage steps (1..100). Returns sorted unique list."""
    if raw is None:
        return list(DEFAULT_SWEEP_STEPS)
    values: list[int] = []
    if isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            return list(DEFAULT_SWEEP_STEPS)
        for part in cleaned.split(","):
            token = part.strip()
            if not token:
                continue
            val = int(token)
            if not 1 <= val <= 100:
                raise ValueError(f"Stappercentage moet tussen 1 en 100 liggen (kreeg {val}).")
            values.append(val)
    elif isinstance(raw, (list, tuple)):
        if not raw:
            return list(DEFAULT_SWEEP_STEPS)
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError(f"Stappen moeten gehele getallen zijn (kreeg {item!r}).")
            if not 1 <= item <= 100:
                raise ValueError(f"Stappercentage moet tussen 1 en 100 liggen (kreeg {item}).")
            values.append(item)
    else:
        raise ValueError("Ongeldig formaat voor steps.")

    unique = sorted(set(values))
    if len(unique) < 2:
        raise ValueError("Er zijn minstens 2 verschillende stappen nodig.")
    return unique


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


async def extract_video_luma_async(
    video_path: str | Path,
    *,
    fps: int = 10,
    scale: str = "64:36",
) -> list[tuple[float, float]]:
    """Run ``ffprobe`` signalstats asynchronously and return ``[(t_s, yavg), ...]``."""
    target = Path(video_path).expanduser()
    if not target.is_file():
        raise FileNotFoundError(f"Videobestand niet gevonden: {target}")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise FileNotFoundError("ffprobe is niet gevonden in PATH. Installeer ffmpeg.")

    escaped = _escape_lavfi_path(target.resolve())
    filter_graph = f"movie='{escaped}',fps={int(fps)},scale={scale},signalstats"
    proc = await asyncio.create_subprocess_exec(
        ffprobe_bin,
        "-v",
        "error",
        "-f",
        "lavfi",
        filter_graph,
        "-show_entries",
        "frame=pts_time:frame_tags=lavfi.signalstats.YAVG",
        "-of",
        "csv=p=0",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    if proc.returncode != 0:
        err = stderr_b.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffprobe mislukt (exit {proc.returncode}): {err}")

    samples: list[tuple[float, float]] = []
    for line in stdout_b.decode("utf-8", errors="replace").splitlines():
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        try:
            t_s = float(parts[0])
            yavg = float(parts[1])
        except ValueError:
            continue
        samples.append((t_s, yavg))
    if not samples:
        raise RuntimeError(f"Geen bruikbare YAVG-frames gevonden in {target}")
    return samples


def _rolling_median(values: list[float], radius: int = 1) -> list[float]:
    n = len(values)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - radius)
        hi = min(n, i + radius + 1)
        out.append(float(statistics.median(values[lo:hi])))
    return out


def detect_sync_off_time(
    samples: list[tuple[float, float]],
    *,
    sync_on_s: float = DEFAULT_SYNC_ON_SECONDS,
    sync_off_s: float = DEFAULT_SYNC_OFF_SECONDS,
) -> float:
    """Detect the falling edge (ON 100% -> OFF 0%) of the initial sync pulse."""
    if len(samples) < 5:
        raise ValueError("Te weinig frames om de sync-puls te detecteren.")

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
        raise ValueError("Geen donkere frames na de sync-puls gevonden.")

    sorted_post = sorted(post_peak)
    low_count = max(1, len(sorted_post) // 3)
    y_dark_init = float(statistics.median(sorted_post[:low_count]))

    if y_peak - y_dark_init < 1.0:
        raise ValueError(
            f"Sync-pulscontrast te klein (piek={y_peak:.2f}, donker={y_dark_init:.2f})."
        )

    midpoint = (y_peak + y_dark_init) / 2.0
    for idx in range(peak_idx, len(samples)):
        t, y = samples[idx]
        if y <= midpoint:
            return float(t)

    raise ValueError("Dalende flank van de sync-puls (ON -> OFF) niet gevonden.")


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
        raise ValueError(f"Geen videoframes in venster [{start_t:.2f}s, {end_t:.2f}s].")
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


def fit_dim_gamma_log_log(
    steps: list[int],
    norm_lumas: list[float],
    dim_min: int,
    dim_max: int,
) -> float:
    """Fit ``dim_gamma`` via log-log least squares against a 2.2 perceptual exponent."""
    if dim_max <= dim_min:
        return 1.0

    l_at_min = _interp_curve(float(dim_min), steps, norm_lumas)
    l_at_max = _interp_curve(float(dim_max), steps, norm_lumas)
    span = l_at_max - l_at_min
    if span <= 0.05:
        return 1.0

    sum_xx = 0.0
    sum_xy = 0.0
    points = 0
    for pct, y_norm in zip(steps, norm_lumas):
        if not (dim_min < pct < dim_max):
            continue
        u_raw = (pct - dim_min) / (dim_max - dim_min)
        l_norm = (y_norm - l_at_min) / span
        if not (0.02 <= u_raw <= 0.98 and 0.02 <= l_norm <= 0.98):
            continue
        x = math.log(u_raw)
        y = math.log(l_norm)
        sum_xx += x * x
        sum_xy += x * y
        points += 1

    if points < 2 or sum_xx <= 1e-9:
        return 1.0

    alpha = sum_xy / sum_xx
    if alpha <= 0.0:
        return 1.0

    return round(max(1.0, min(3.5, 2.2 / alpha)), 2)


def analyze_luma_series(
    samples: list[tuple[float, float]],
    steps: list[int],
    hold_seconds: float,
    *,
    sync_on_seconds: float = DEFAULT_SYNC_ON_SECONDS,
    sync_off_seconds: float = DEFAULT_SYNC_OFF_SECONDS,
    step_offsets_seconds: list[float] | None = None,
    margin_min: int = 1,
    sat_threshold: float = 0.985,
    sync_off_time: float | None = None,
) -> dict[str, Any]:
    """Analyze a time series of ``(t_s, YAVG)`` and recommend ``dimMin``, ``dimMax``, and ``dim_gamma``."""
    if step_offsets_seconds is not None and len(step_offsets_seconds) != len(steps):
        raise ValueError("Aantal step_offsets_seconds komt niet overeen met steps.")
    if margin_min < 0:
        raise ValueError("margin_min mag niet negatief zijn.")

    t_sync_off = (
        float(sync_off_time)
        if sync_off_time is not None
        else detect_sync_off_time(
            samples,
            sync_on_s=sync_on_seconds,
            sync_off_s=sync_off_seconds,
        )
    )
    first_step_offset = step_offsets_seconds[0] if step_offsets_seconds else sync_off_seconds
    y_dark = extract_step_yavg(
        samples,
        t_sync_off,
        t_sync_off + first_step_offset,
    )

    step_windows: list[tuple[int, float, float, float]] = []
    for idx, pct in enumerate(steps):
        if step_offsets_seconds is not None:
            start_s = t_sync_off + step_offsets_seconds[idx]
            end_s = (
                t_sync_off + step_offsets_seconds[idx + 1]
                if idx + 1 < len(step_offsets_seconds)
                else start_s + hold_seconds
            )
        else:
            start_s = t_sync_off + sync_off_seconds + idx * hold_seconds
            end_s = start_s + hold_seconds
        yavg = extract_step_yavg(samples, start_s, end_s)
        step_windows.append((pct, start_s, end_s, yavg))

    y_max = max(item[3] for item in step_windows)
    span = y_max - y_dark
    if span <= 0.5:
        raise ValueError(
            f"Te weinig lichtverschil tussen donker ({y_dark:.2f}) en maximum ({y_max:.2f})."
        )

    on_delta = max(3.0, 0.015 * span)
    on_threshold = y_dark + on_delta

    norm_lumas = [
        max(0.0, min(1.0, (yavg - y_dark) / span))
        for _, _, _, yavg in step_windows
    ]

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

    measurements: list[dict[str, Any]] = []
    for idx, (pct, start_s, end_s, yavg) in enumerate(step_windows):
        norm = norm_lumas[idx]
        if yavg <= on_threshold:
            state = "OFF"
        elif norm >= sat_threshold or pct >= recommended_dim_max:
            state = "SATURATED"
        else:
            state = "ACTIVE"
        measurements.append(
            {
                "level": pct,
                "start_s": round(start_s, 2),
                "end_s": round(end_s, 2),
                "yavg": round(yavg, 2),
                "norm_luma": round(norm, 4),
                "norm_pct": round(norm * 100.0, 1),
                "state": state,
            }
        )

    recommended_gamma = fit_dim_gamma_log_log(
        steps,
        norm_lumas,
        recommended_dim_min,
        recommended_dim_max,
    )

    return {
        "t_sync_off_s": round(t_sync_off, 2),
        "y_dark": round(y_dark, 2),
        "y_max": round(y_max, 2),
        "measured_dim_min": measured_dim_min,
        "recommended_dim_min": recommended_dim_min,
        "recommended_dim_max": recommended_dim_max,
        "recommended_dim_gamma": recommended_gamma,
        "steps": measurements,
    }


async def fetch_module_dimmer_statuses(
    module_ip: str,
    *,
    client: aiohttp.ClientSession | None = None,
    timeout: float = 4.0,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Read live channel statuses + ``dimMin``/``dimMax`` from an IP0300PoE module."""
    url = f"http://{module_ip}/api.html?method=statuses"
    own_client = client is None
    session = client or aiohttp.ClientSession()
    try:
        req_timeout = aiohttp.ClientTimeout(total=timeout)
        async with session.get(url, timeout=req_timeout) as response:
            text = await response.text(encoding="utf-8", errors="replace")
            if response.status >= 400:
                return None, f"HTTP {response.status} bij lezen van module-status"
            data = json.loads(text)
            if not isinstance(data, list):
                return None, "Onverwacht formaat in module-statusantwoord"
            return [row for row in data if isinstance(row, dict)], None
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, str(exc) or exc.__class__.__name__
    finally:
        if own_client:
            await session.close()


async def save_module_dimmer_channel(
    module_ip: str,
    channel: int,
    *,
    descr: str,
    gr: str,
    dim_min: int,
    dim_max: int,
    client: aiohttp.ClientSession | None = None,
    timeout: float = 4.0,
) -> tuple[bool, str | None]:
    """Persist ``descr``/``gr``/``dimMin``/``dimMax`` for one IP0300PoE channel."""
    if not 0 <= channel <= 7:
        return False, f"Kanaal moet tussen 0 en 7 liggen (kreeg {channel})."
    if not 0 <= dim_min < dim_max <= 100:
        return False, f"dimMin/dimMax moeten voldoen aan 0 <= dimMin < dimMax <= 100 (kreeg {dim_min}..{dim_max})."

    ds_q = quote(descr, safe="")
    gr_q = quote(gr, safe="")
    url = (
        f"http://{module_ip}/api.html?method=saveChannel"
        f"&ds={ds_q}&gr={gr_q}&dimMax={int(dim_max)}&dimMin={int(dim_min)}&ch={int(channel)}"
    )
    own_client = client is None
    session = client or aiohttp.ClientSession()
    try:
        req_timeout = aiohttp.ClientTimeout(total=timeout)
        async with session.get(url, timeout=req_timeout) as response:
            text = await response.text(encoding="utf-8", errors="replace")
            if response.status >= 400:
                return False, f"HTTP {response.status} bij saveChannel: {text[:160]}"
            return True, None
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        return False, str(exc) or exc.__class__.__name__
    finally:
        if own_client:
            await session.close()
