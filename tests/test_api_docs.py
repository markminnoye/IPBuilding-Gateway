"""Keep Postman collection in sync with gateway_api REST routes.

Run:  PYTHONPATH=. python -m pytest tests/test_api_docs.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_PATH = ROOT / "docs/api/ipbuilding-gateway.postman_collection.json"

EXPECTED_ROUTES: set[tuple[str, str]] = {
    ("GET", "/api/v1/modules"),
    ("GET", "/api/v1/modules/{module_id}"),
    ("POST", "/api/v1/modules/refresh"),
    ("GET", "/api/v1/devices"),
    ("GET", "/api/v1/devices/{device_id}"),
    ("POST", "/api/v1/devices/{device_id}/command"),
    ("POST", "/api/v1/provision/autonomy"),
}

V21_SCHEMA_SUFFIX = "v2.1.0/collection.json"


def _normalize_postman_path(raw: str) -> str:
    """Convert Postman URL path segments to gateway route template."""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
        raw = raw.split("/", 1)[1] if "/" in raw else ""
        raw = "/" + raw if raw else "/"
    parts = []
    for segment in raw.strip("/").split("/"):
        if segment.startswith("{{") and segment.endswith("}}"):
            parts.append("{" + segment[2:-2].strip() + "}")
        else:
            parts.append(segment)
    return "/" + "/".join(parts) if parts else "/"


def _iter_requests(items: list) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for item in items:
        if "item" in item:
            found.extend(_iter_requests(item["item"]))
            continue
        req = item.get("request")
        if not req:
            continue
        method = req["method"].upper()
        url = req["url"]
        if isinstance(url, str):
            path = _normalize_postman_path(url)
        else:
            path_segments = url.get("path") or []
            normalized_segments = []
            for seg in path_segments:
                if seg.startswith("{{") and seg.endswith("}}"):
                    normalized_segments.append("{" + seg[2:-2].strip() + "}")
                else:
                    normalized_segments.append(seg)
            path = "/" + "/".join(normalized_segments)
        found.append((method, path))
    return found


@pytest.fixture
def collection() -> dict:
    assert COLLECTION_PATH.is_file(), f"missing {COLLECTION_PATH}"
    return json.loads(COLLECTION_PATH.read_text(encoding="utf-8"))


def test_collection_uses_postman_v21_schema(collection: dict) -> None:
    schema = collection["info"]["schema"]
    assert schema.endswith(V21_SCHEMA_SUFFIX), schema


def test_collection_covers_all_gateway_rest_routes(collection: dict) -> None:
    routes = set(_iter_requests(collection["item"]))
    assert EXPECTED_ROUTES <= routes, f"missing routes: {EXPECTED_ROUTES - routes}"


def test_collection_has_no_legacy_v1_requests_key(collection: dict) -> None:
    assert "requests" not in collection, "use v2.1 item[] not legacy v1 requests[]"