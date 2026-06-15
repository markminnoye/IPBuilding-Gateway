"""Tests for gateway.health.GatewayHealthMonitor."""

from __future__ import annotations

from gateway.health import GatewayHealthMonitor


class TestGatewayHealthMonitor:
    def test_empty_is_ok(self) -> None:
        monitor = GatewayHealthMonitor()
        assert monitor.compute_status() == "ok"
        snap = monitor.snapshot()
        assert snap["status"] == "ok"
        assert snap["issues"] == []
        assert "version" in snap
        assert "uptime_seconds" in snap
        assert "actions" in snap

    def test_warning_issue_degraded(self) -> None:
        monitor = GatewayHealthMonitor()
        monitor.report_issue(
            "module_metadata.getSysSet.10.10.1.30",
            "module_metadata.http_failed",
            "warning",
            "HTTP getSysSet 10.10.1.30 failed: timeout",
            {"ip": "10.10.1.30", "method": "getSysSet"},
        )
        assert monitor.compute_status() == "degraded"
        issue = monitor.snapshot()["issues"][0]
        assert issue["level"] == "warning"
        assert "10.10.1.30" in issue["message"]
        assert issue["since"]

    def test_error_issue_unhealthy(self) -> None:
        monitor = GatewayHealthMonitor()
        monitor.set_installation_loaded(False)
        assert monitor.compute_status() == "unhealthy"
        assert monitor.snapshot()["subsystems"]["installation"] == "unhealthy"

    def test_clear_issue_returns_ok(self) -> None:
        monitor = GatewayHealthMonitor()
        monitor.report_issue(
            "module_metadata.getSysSet.10.10.1.30",
            "module_metadata.http_failed",
            "warning",
            "fail",
            {"ip": "10.10.1.30", "method": "getSysSet"},
        )
        monitor.clear_issue("module_metadata.getSysSet.10.10.1.30")
        assert monitor.compute_status() == "ok"

    def test_on_change_fires_on_status_change(self) -> None:
        monitor = GatewayHealthMonitor()
        calls: list[int] = []
        monitor.on_change(lambda: calls.append(1))
        monitor.report_issue("a", "module_metadata.http_failed", "warning", "t", {"ip": "1", "method": "m"})
        assert len(calls) == 1
        monitor.report_issue("b", "discovery.unreachable", "warning", "t", {"mac": "aa"})
        assert len(calls) == 2
        monitor.clear_issue("a")
        assert len(calls) == 3

    def test_on_change_dedup_same_snapshot(self) -> None:
        monitor = GatewayHealthMonitor()
        calls: list[int] = []
        monitor.on_change(lambda: calls.append(1))
        monitor.report_issue("a", "module_metadata.http_failed", "warning", "t1", {"ip": "1", "method": "m"})
        monitor.report_issue("a", "module_metadata.http_failed", "warning", "t2", {"ip": "1", "method": "m"})
        assert len(calls) == 1

    def test_snapshot_without_actions(self) -> None:
        monitor = GatewayHealthMonitor()
        assert "actions" not in monitor.snapshot(include_actions=False)

    def test_subsystems_module_metadata_degraded(self) -> None:
        monitor = GatewayHealthMonitor()
        monitor.report_issue(
            "module_metadata.getSysSet.10.10.1.30",
            "module_metadata.http_failed",
            "warning",
            "fail",
            {"ip": "10.10.1.30", "method": "getSysSet"},
        )
        assert monitor.snapshot()["subsystems"]["module_metadata"] == "degraded"
