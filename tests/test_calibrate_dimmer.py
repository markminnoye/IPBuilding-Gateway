"""Unit tests for scripts/calibrate_dimmer.py luma analysis and sync detection."""

from __future__ import annotations

import pytest

from scripts.calibrate_dimmer import (
    DEFAULT_STEPS,
    analyze_luma_series,
    detect_sync_off_time,
    format_uitgang,
    parse_steps,
)


def _build_synthetic_samples(
    *,
    steps: list[int],
    hold_s: float = 2.5,
    pre_dark_s: float = 0.0,
    sync_on_s: float = 2.0,
    sync_off_s: float = 3.0,
    y_dark: float = 340.0,
    y_max: float = 740.0,
    ignite_pct: int = 16,
    sat_pct: int = 65,
) -> list[tuple[float, float]]:
    """Build a synthetic 10 Hz YAVG luma series matching an AE/AF-locked capture."""
    samples: list[tuple[float, float]] = []

    def _luma_for_pct(pct: int) -> float:
        if pct < ignite_pct:
            return y_dark + 0.5  # Dead band (tiny driver noise below threshold)
        if pct >= sat_pct:
            return y_max
        frac = (pct - ignite_pct) / (sat_pct - ignite_pct)
        # Physical LED snaps on at ignition (~5% jump) and follows concave curve
        norm = 0.05 + 0.95 * (frac ** 0.55)
        return y_dark + (y_max - y_dark) * norm

    t = 0.0
    dt = 0.1

    def _emit(duration_s: float, y: float) -> None:
        nonlocal t
        n = round(duration_s / dt)
        for _ in range(n):
            samples.append((round(t, 3), y))
            t += dt

    if pre_dark_s > 0:
        _emit(pre_dark_s, y_dark)
    _emit(sync_on_s, y_max)
    _emit(sync_off_s, y_dark)
    for pct in steps:
        _emit(hold_s, _luma_for_pct(pct))
    _emit(2.0, y_dark)
    return samples


class TestSyncAndAnalysis:
    def test_sync_detection_at_t_2s(self) -> None:
        samples = _build_synthetic_samples(steps=DEFAULT_STEPS)
        t_off = detect_sync_off_time(samples)
        assert t_off == pytest.approx(2.0, abs=0.11)

    def test_sync_detection_with_pre_roll_dark(self) -> None:
        samples = _build_synthetic_samples(steps=DEFAULT_STEPS, pre_dark_s=2.5)
        t_off = detect_sync_off_time(samples)
        assert t_off == pytest.approx(4.5, abs=0.11)

    def test_analyze_derives_dim_min_max_and_gamma(self) -> None:
        samples = _build_synthetic_samples(
            steps=DEFAULT_STEPS,
            ignite_pct=16,
            sat_pct=65,
        )
        res_exact = analyze_luma_series(
            samples, DEFAULT_STEPS, hold_s=2.5, margin_min=0
        )
        assert res_exact.t_sync_off_s == pytest.approx(2.0, abs=0.11)
        assert res_exact.measured_dim_min == 16
        assert res_exact.recommended_dim_min == 16
        assert res_exact.recommended_dim_max == 65
        assert 1.0 <= res_exact.recommended_dim_gamma <= 3.5

        res_margin = analyze_luma_series(
            samples, DEFAULT_STEPS, hold_s=2.5, margin_min=1
        )
        assert res_margin.measured_dim_min == 16
        assert res_margin.recommended_dim_min == 17
        assert res_margin.recommended_dim_max == 65
        assert 1.0 <= res_margin.recommended_dim_gamma <= 3.5

        by_level = {s.level: s for s in res_margin.steps}
        assert by_level[14].state == "OFF"
        assert by_level[16].state == "ACTIVE"
        assert by_level[65].state == "SATURATED"

    def test_analyze_with_explicit_step_offsets(self) -> None:
        steps = [10, 16, 30, 65, 100]
        hold_s = 2.0
        samples = _build_synthetic_samples(
            steps=steps,
            hold_s=hold_s,
            ignite_pct=16,
            sat_pct=65,
        )
        offsets = [3.0 + i * hold_s for i in range(len(steps))]
        res = analyze_luma_series(
            samples,
            steps,
            hold_s=hold_s,
            step_offsets_s=offsets,
            margin_min=0,
        )
        assert res.measured_dim_min == 16
        assert res.recommended_dim_max == 65

    def test_helpers(self) -> None:
        assert format_uitgang("10.10.1.40", 0) == "40.1.1"
        assert format_uitgang("10.10.1.40", 1) == "40.1.2"
        assert format_uitgang("10.10.1.40", 2) == "40.1.3"
        assert format_uitgang("10.10.1.30", 8) == "30.2.1"
        assert parse_steps("20, 10, 20, 50") == [10, 20, 50]
        with pytest.raises(ValueError):
            parse_steps("10")
        with pytest.raises(ValueError):
            parse_steps("0, 50")
