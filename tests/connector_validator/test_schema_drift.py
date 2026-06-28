"""Drift-check CI for schema-owned enums the plugin restates as decision logic.

A handful of enums can't simply be deleted from the plugin: they ARE the
mapping logic (`enum-mappers.md` maps researched provider facts onto schema
enum values; `ProviderFacts` classifies into them; `CLAUDE.md` documents the
closed sets). Per the drift policy
(`docs/design/contract-derived-research.md` §2), anything that must stay
duplicated is pinned to the live schema here. If the published schema's enum
changes, the matching test fails and names the divergence, so the prose +
mappers are updated in the same change instead of silently drifting.

These tests fetch the live published schemas (with the validator's disk
cache, exactly like the rest of the suite) and skip when the host is
unreachable. Companion inventory: `docs/design/drift-audit.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import validate_connector as v  # noqa: E402

CONNECTOR_URL = v.CONNECTOR_SCHEMA_URL
API_ENDPOINT_URL = "https://schemas.analitiq.ai/api-endpoint/latest.json"

# --- plugin-side expected sets ---------------------------------------------
# These mirror the enums documented in CLAUDE.md / enum-mappers.md /
# io-contracts.md. When a test below fails, update BOTH the prose and the
# expected set here in the same change.

EXPECTED_AUTH_TYPES = {
    "api_key",
    "basic_auth",
    "oauth2_authorization_code",
    "oauth2_client_credentials",
    "jwt",
    "db",
    "credentials",
    "aws_iam",
    "none",
}
EXPECTED_ADBC_DRIVERS = {"postgresql", "snowflake", "bigquery"}
EXPECTED_DSN_ENCODINGS = {
    "raw",
    "host",
    "url_userinfo",
    "url_path_segment",
    "url_query_key",
    "url_query_value",
}
EXPECTED_PAGINATION_STYLES = {"offset", "page", "cursor", "link", "keyset"}


def _const_types(schema: dict, def_suffix: str) -> set[str]:
    """Collect the `type` const across `$defs/*<suffix>` definitions.

    Auth families and pagination styles are modelled as one discriminated
    `$def` per variant (e.g. `ApiKeyAuth`, `CursorPagination`), each pinning
    `properties.type.const` — not a single flat enum.
    """
    out: set[str] = set()
    for name, node in schema.get("$defs", {}).items():
        if name.endswith(def_suffix) and isinstance(node, dict):
            type_node = (node.get("properties") or {}).get("type") or {}
            if "const" in type_node:
                out.add(type_node["const"])
    return out


@pytest.fixture(scope="module")
def connector_schema() -> dict:
    try:
        return v.fetch_schema(CONNECTOR_URL)
    except Exception as exc:  # noqa: BLE001 - network/offline is a skip, not a failure
        pytest.skip(f"live connector schema unreachable: {exc}")


@pytest.fixture(scope="module")
def api_endpoint_schema() -> dict:
    try:
        return v.fetch_schema(API_ENDPOINT_URL)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live api-endpoint schema unreachable: {exc}")


def test_auth_types_match_schema(connector_schema: dict) -> None:
    schema_set = _const_types(connector_schema, "Auth")
    assert schema_set == EXPECTED_AUTH_TYPES, (
        "auth.type drift — update CLAUDE.md '## Supported Auth Types' and "
        "AuthTypeMapper in skills/connector-builder/references/enum-mappers.md. "
        f"schema-only={sorted(schema_set - EXPECTED_AUTH_TYPES)} "
        f"plugin-only={sorted(EXPECTED_AUTH_TYPES - schema_set)}"
    )


def test_adbc_drivers_match_schema(connector_schema: dict) -> None:
    schema_set = v._enum_at(
        connector_schema, "$defs", "AdbcTransport", "properties", "driver"
    )
    assert schema_set == EXPECTED_ADBC_DRIVERS, (
        "AdbcTransport.driver drift — update the driver-selection guidance "
        "(enum-mappers.md, spec-driver-selection.md). "
        f"schema={sorted(schema_set or set())} expected={sorted(EXPECTED_ADBC_DRIVERS)}"
    )


def test_dsn_encodings_match_schema(connector_schema: dict) -> None:
    schema_set = v._enum_at(
        connector_schema, "$defs", "DsnBinding", "properties", "encoding"
    )
    assert schema_set == EXPECTED_DSN_ENCODINGS, (
        "DsnBinding.encoding drift — update spec-dsn-bindings.md + CLAUDE.md. "
        f"schema={sorted(schema_set or set())}"
    )
    # The validator must derive the same set it enforces (no offline fallback drift).
    assert v.known_encodings() == frozenset(EXPECTED_DSN_ENCODINGS)


def test_pagination_styles_match_schema(api_endpoint_schema: dict) -> None:
    schema_set = _const_types(api_endpoint_schema, "Pagination")
    assert schema_set == EXPECTED_PAGINATION_STYLES, (
        "pagination style drift — update io-contracts.md ProviderFacts and "
        "spec-pagination.md. "
        f"schema-only={sorted(schema_set - EXPECTED_PAGINATION_STYLES)} "
        f"plugin-only={sorted(EXPECTED_PAGINATION_STYLES - schema_set)}"
    )
