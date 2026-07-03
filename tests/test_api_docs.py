"""Keep Postman collection in sync with gateway_api REST routes.

Run:  PYTHONPATH=. python -m pytest tests/test_api_docs.py -v
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_PATH = ROOT / "docs/api/ipbuilding-gateway.postman_collection.json"

EXPECTED_ROUTES: set[tuple[str, str]] = {
    ("GET", "/api/{apiVersion}/status"),
    ("GET", "/api/{apiVersion}/modules"),
    ("GET", "/api/{apiVersion}/modules/{module_id}"),
    ("POST", "/api/{apiVersion}/modules/refresh"),
    ("GET", "/api/{apiVersion}/devices"),
    ("GET", "/api/{apiVersion}/devices/{device_id}"),
    # Commands folder uses {{default_device_id}} (collection-level default)
    # instead of the generic {{device_id}} — both should be accepted as
    # the same logical route.
    ("POST", "/api/{apiVersion}/devices/{default_device_id}/command"),
    ("GET", "/api/{apiVersion}/installation"),
    ("POST", "/api/{apiVersion}/installation/validate"),
    ("POST", "/api/{apiVersion}/installation/apply"),
    ("POST", "/api/{apiVersion}/discover"),
    ("POST", "/api/{apiVersion}/provision/autonomy"),
}

# Aliases that the test accepts as equivalent (e.g. {default_device_id} when
# a folder-level default replaces the generic name).
ROUTE_ALIASES: dict[str, set[str]] = {
    "/api/{apiVersion}/devices/{default_device_id}/command": {
        "/api/{apiVersion}/devices/{device_id}/command",
    },
}

V21_SCHEMA_SUFFIX = "v2.1.0/collection.json"

POST_ROUTES_WITH_BODY: set[str] = {
    "/api/{apiVersion}/modules/refresh",
    "/api/{apiVersion}/installation/validate",
    "/api/{apiVersion}/installation/apply",
    # Commands folder uses {default_device_id} — accepted as equivalent.
    "/api/{apiVersion}/devices/{default_device_id}/command",
    "/api/{apiVersion}/devices/{device_id}/command",
    "/api/{apiVersion}/provision/autonomy",
}

# Leaf-request description must be at least this many characters (after strip).
MIN_DESCRIPTION_LEN = 100

# Postman UUID v4-ish pattern: 8-4-4-4-12 hex chars (we don't enforce v4 nibble
# bits because Postman accepts any UUID-shaped id).
_POSTMAN_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+")


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


def _iter_leaf_requests(items: list) -> list[tuple[str, dict, str]]:
    """Walk a Postman item tree and return (name, request_dict, path_str) per leaf."""
    found: list[tuple[str, dict, str]] = []
    for item in items:
        if "item" in item:
            found.extend(_iter_leaf_requests(item["item"]))
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
        found.append((item.get("name", ""), req, path))
    return found


def _iter_requests(items: list) -> list[tuple[str, str]]:
    """Backwards-compatible helper returning (method, path) tuples."""
    return [
        (req["method"].upper(), path)
        for (_name, req, path) in _iter_leaf_requests(items)
    ]


@pytest.fixture
def collection() -> dict:
    assert COLLECTION_PATH.is_file(), f"missing {COLLECTION_PATH}"
    return json.loads(COLLECTION_PATH.read_text(encoding="utf-8"))


def test_collection_uses_postman_v21_schema(collection: dict) -> None:
    schema = collection["info"]["schema"]
    assert schema.endswith(V21_SCHEMA_SUFFIX), schema


def test_collection_covers_all_gateway_rest_routes(collection: dict) -> None:
    routes = set(_iter_requests(collection["item"]))
    # Accept alias routes (e.g. {default_device_id} in place of {device_id})
    # by expanding the set with all alias pairs.
    expanded = set(routes)
    for route in routes:
        # route is (method, path); ROUTE_ALIASES is keyed by path strings.
        path = route[1]
        for alias_path in ROUTE_ALIASES.get(path, []):
            expanded.add((route[0], alias_path))
    missing = EXPECTED_ROUTES - expanded
    assert not missing, f"missing routes: {missing}"


def test_collection_has_no_legacy_v1_requests_key(collection: dict) -> None:
    assert "requests" not in collection, "use v2.1 item[] not legacy v1 requests[]"


def test_collection_has_info_version(collection: dict) -> None:
    """info.version must exist and look like a semver string (e.g. 1.0.0)."""
    version = collection.get("info", {}).get("version")
    assert isinstance(version, str) and version.strip(), (
        "collection info.version is missing or empty — set e.g. \"1.0.0\" in info{}"
    )
    assert _SEMVER_PATTERN.match(version), (
        f"collection info.version {version!r} does not look like MAJOR.MINOR.PATCH — "
        "expected e.g. \"1.0.0\""
    )


def test_collection_has_postman_uuid_id(collection: dict) -> None:
    """info._postman_id must be a UUID-shaped identifier."""
    postman_id = collection.get("info", {}).get("_postman_id")
    assert isinstance(postman_id, str) and postman_id, (
        "collection info._postman_id is missing or empty"
    )
    assert _POSTMAN_ID_PATTERN.match(postman_id), (
        f"info._postman_id {postman_id!r} is not a UUID — generate one with "
        "`python -c 'import uuid; print(uuid.uuid4())'` and set it in info{{}}"
    )


def test_every_request_has_description(collection: dict) -> None:
    """Every leaf request must have a description of >= MIN_DESCRIPTION_LEN chars."""
    offenders: list[str] = []
    for name, req, _path in _iter_leaf_requests(collection["item"]):
        desc = req.get("description")
        if not isinstance(desc, str):
            offenders.append(f"{name!r}: description missing or not a string")
            continue
        if len(desc.strip()) < MIN_DESCRIPTION_LEN:
            offenders.append(
                f"{name!r}: description is {len(desc.strip())} chars "
                f"(min {MIN_DESCRIPTION_LEN})"
            )
    assert not offenders, (
        "the following requests have short/missing descriptions "
        f"(min {MIN_DESCRIPTION_LEN} chars each):\n  - " + "\n  - ".join(offenders)
    )


def test_post_requests_with_body_have_body_field(collection: dict) -> None:
    """POST routes in POST_ROUTES_WITH_BODY must define a raw body."""
    offenders: list[str] = []
    for name, req, path in _iter_leaf_requests(collection["item"]):
        if req.get("method", "").upper() != "POST":
            continue
        if path not in POST_ROUTES_WITH_BODY:
            continue
        body = req.get("body")
        if not isinstance(body, dict):
            offenders.append(
                f"{name!r} ({path}): request.body is missing — "
                "POST routes need a raw JSON body"
            )
            continue
        if body.get("mode") != "raw":
            offenders.append(
                f"{name!r} ({path}): body.mode is {body.get('mode')!r}, expected 'raw'"
            )
            continue
        raw = body.get("raw")
        if not isinstance(raw, str) or not raw.strip():
            offenders.append(
                f"{name!r} ({path}): body.raw is empty — provide a sample JSON payload"
            )
    assert not offenders, (
        "the following POST requests are missing a raw body:\n  - "
        + "\n  - ".join(offenders)
    )


def test_collection_has_standard_top_level_fields(collection: dict) -> None:
    """Encourage the standard v2.1 top-level fields; skip gracefully if absent."""
    info = collection.get("info", {})
    expected_info_fields = {"name", "schema", "_postman_id", "version", "description"}
    missing_info = expected_info_fields - set(info.keys())
    assert not missing_info, (
        f"collection info is missing recommended fields: {sorted(missing_info)}"
    )
    assert isinstance(collection.get("item"), list) and collection["item"], (
        "collection.item must be a non-empty list"
    )
    if "auth" in collection:
        auth_type = collection["auth"].get("type") if isinstance(collection["auth"], dict) else None
        assert auth_type == "noauth", (
            f"collection.auth.type is {auth_type!r}, expected 'noauth' "
            "or remove the auth block"
        )
    if "protocolProfileBehavior" in collection:
        assert isinstance(collection["protocolProfileBehavior"], dict), (
            "collection.protocolProfileBehavior must be an object"
        )


def test_collection_has_api_version_variable(collection: dict) -> None:
    """The collection should define a `apiVersion` Postman variable."""
    variables = collection.get("variable")
    if not isinstance(variables, list):
        pytest.fail(
            "collection.variable must be a list — add a variable with key=\"apiVersion\""
        )
    keys = [v.get("key") for v in variables if isinstance(v, dict)]
    assert "apiVersion" in keys, (
        f"collection.variable is missing key \"apiVersion\"; got keys: {keys}"
    )
