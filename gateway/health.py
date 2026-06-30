"""Gateway health aggregation for northbound status API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from gateway import __version__

HealthStatus = Literal["ok", "degraded", "unhealthy"]
IssueLevel = Literal["warning", "error"]

MESSAGE_TEMPLATES: dict[str, str] = {
    "installation.missing": "No installation configuration loaded (devices.json)",
    "installation.load_failed": "devices.json could not be loaded: {devices_file}",
    "module_metadata.http_failed": (
        "Module {ip} is not responding to {method} configuration requests"
    ),
    "discovery.unreachable": "Module {mac} has not been seen on the field bus",
}

STATUS_ACTIONS: dict[str, dict[str, str]] = {
    "discover": {"method": "POST", "path": "/api/v1/discover"},
    "refresh_modules": {"method": "POST", "path": "/api/v1/modules/refresh"},
}


@dataclass
class HealthIssue:
    """One open health issue."""

    id: str
    level: IssueLevel
    code: str
    technical: str
    message: str
    context: dict[str, Any]
    since: str


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_message(code: str, context: dict[str, Any]) -> str:
    template = MESSAGE_TEMPLATES.get(code, code)
    try:
        return template.format(**context)
    except KeyError:
        return template


class GatewayHealthMonitor:
    """Tracks open issues and computes aggregate gateway status."""

    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._issues: dict[str, HealthIssue] = {}
        self._change_callbacks: list[Callable[[], None]] = []
        self._last_notify_key: tuple[str, frozenset[str]] | None = None
        # Populated by main.py after the HaDiscoveryAdvertiser has loaded or
        # generated the instance id. Empty string means "not yet known".
        self._instance_id: str = ""

    def set_instance_id(self, instance_id: str) -> None:
        """Record the gateway's persistent HA-discovery instance id."""
        self._instance_id = instance_id

    def on_change(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked when aggregate status or issues change."""
        self._change_callbacks.append(callback)

    def report_issue(
        self,
        issue_id: str,
        code: str,
        level: IssueLevel,
        technical: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Upsert an open issue and notify listeners if the snapshot changed."""
        ctx = context or {}
        existing = self._issues.get(issue_id)
        issue = HealthIssue(
            id=issue_id,
            level=level,
            code=code,
            technical=technical,
            message=_format_message(code, ctx),
            context=ctx,
            since=existing.since if existing else _iso_now(),
        )
        self._issues[issue_id] = issue
        self._maybe_notify()

    def clear_issue(self, issue_id: str) -> None:
        """Remove a resolved issue."""
        if issue_id in self._issues:
            del self._issues[issue_id]
            self._maybe_notify()

    def compute_status(self) -> HealthStatus:
        """Worst-of open issues."""
        if any(issue.level == "error" for issue in self._issues.values()):
            return "unhealthy"
        if self._issues:
            return "degraded"
        return "ok"

    def _compute_subsystems(self) -> dict[str, HealthStatus]:
        subsystems: dict[str, HealthStatus] = {
            "installation": "ok",
            "module_metadata": "ok",
            "discovery": "ok",
        }
        if "installation.missing" in self._issues:
            subsystems["installation"] = "unhealthy"
        for issue in self._issues.values():
            if issue.code.startswith("module_metadata"):
                subsystems["module_metadata"] = "degraded"
            elif issue.code.startswith("discovery"):
                subsystems["discovery"] = "degraded"
        return subsystems

    def snapshot(self, *, include_actions: bool = True) -> dict[str, Any]:
        """Build the status payload for REST / WebSocket."""
        body: dict[str, Any] = {
            "status": self.compute_status(),
            "version": __version__,
            "instance_id": self._instance_id,
            "uptime_seconds": int(time.monotonic() - self._started_at),
            "updated_at": _iso_now(),
            "subsystems": self._compute_subsystems(),
            "issues": [
                {
                    "id": issue.id,
                    "level": issue.level,
                    "code": issue.code,
                    "technical": issue.technical,
                    "message": issue.message,
                    "context": issue.context,
                    "since": issue.since,
                }
                for issue in self._issues.values()
            ],
        }
        if include_actions:
            body["actions"] = STATUS_ACTIONS
        return body

    def set_installation_loaded(self, loaded: bool) -> None:
        """Report or clear installation.missing."""
        if loaded:
            self.clear_issue("installation.missing")
        else:
            self.report_issue(
                "installation.missing",
                "installation.missing",
                "error",
                "devices.json not loaded or installation empty",
                {},
            )

    def _notify_key(self) -> tuple[str, frozenset[str]]:
        return (self.compute_status(), frozenset(self._issues.keys()))

    def _maybe_notify(self) -> None:
        key = self._notify_key()
        if key == self._last_notify_key:
            return
        self._last_notify_key = key
        for callback in self._change_callbacks:
            callback()
