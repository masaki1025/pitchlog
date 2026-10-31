"""7署名/4app入口/10列/2policy/2triggerを完全一致で検査する。"""

import re

import pytest

from pitchlog.authz.terminal_pitch_product import (
    FUNCTIONS,
    RUNNER_COLUMNS,
    candidate_declarations,
    require_registered_product,
)
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError


def test_exact_product_surface_and_no_direct_runner_app_grant():
    """私有3関数をappへ開かず、全列と新2triggerだけを描画する。"""
    declarations, bodies = candidate_declarations()
    assert len(declarations["functions"]) == 7
    assert len(declarations["policies"]) == 2
    assert len(declarations["column_acl_expectations"]) == 10
    assert {r["column_id"] for r in declarations["column_acl_expectations"]} == set(
        RUNNER_COLUMNS
    )
    for row in declarations["functions"]:
        name = row["function_name"]
        args, returns, app = FUNCTIONS[name]
        assert row["identity_args"] == args
        assert row["returns"] == returns
        assert bool(row["acl_expectations"]) is app
        sql = bodies["function|" + row["function_id"]]
        match = re.search(
            r"FUNCTION\s+sync_right_api\.\w+\((.*?)\)\s*RETURNS", sql, re.S
        )
        assert match
        actual = (
            ", ".join(part.split()[-1] for part in match[1].split(","))
            if match[1]
            else ""
        )
        assert actual == args
        assert "REVOKE ALL ON FUNCTION" in sql
    assert sum(sql.count("CREATE TRIGGER ") for sql in bodies.values()) == 2
    for row in declarations["column_acl_expectations"]:
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["privilege_ids"] == ["SELECT", "INSERT"]


@pytest.mark.parametrize(
    "section", ["functions", "policies", "column_acl_expectations"]
)
def test_missing_formal_registration_stays_closed(monkeypatch, section):
    """正式metadataの必要1要素欠落でも実受付を開かない。DB成功は別に要求する。"""
    import copy
    import json
    from pathlib import Path

    declarations, _ = candidate_declarations()
    operations = [
        "SYNC_PLAY_PREFIX:" + n for n, (_, _, app) in FUNCTIONS.items() if app
    ]

    def read(path, *args, **kwargs):
        if path.name == "ddl-elements.json":
            return json.dumps(declarations)
        if path.name == "repository-contract.json":
            return json.dumps({"product_function_operation_ids": operations})
        if path.name == "play-prefix-manifest.json":
            return json.dumps(
                {
                    "propertyCatalog": {
                        "path": "backend/domain/play-prefix-property-catalog.json",
                        "schema": (
                            "backend/domain/play-prefix-property-catalog.schema.json"
                        ),
                    },
                    "calculations": [
                        {
                            "calculation": "play-prefix-v2",
                            "source": {
                                "path": "frontend/src/domain/playPrefixContinuation.ts"
                            },
                            "directTargets": [
                                {
                                    "hash": "sha256:" + "a" * 64,
                                    "invocation": {
                                        "operation": "derivePlayPrefixWithContinuation"
                                    },
                                }
                            ],
                        }
                    ],
                }
            )
        if path.name == "play-prefix-property-catalog.json":
            return json.dumps({"schemaVersion": 1})
        if path.name == "play-prefix-property-catalog.schema.json":
            return json.dumps(
                {
                    "type": "object",
                    "properties": {"schemaVersion": {"const": 1}},
                    "required": ["schemaVersion"],
                    "additionalProperties": False,
                }
            )
        raise AssertionError("想定外metadata読取")

    monkeypatch.setattr(Path, "read_text", read)
    require_registered_product(artifact_sha256="a" * 64)
    declarations = copy.deepcopy(declarations)
    declarations[section].pop()
    with pytest.raises(OrdinaryPrefixError):
        require_registered_product(artifact_sha256="a" * 64)


def test_all_eight_function_bodies_pass_actual_installer_without_parser_relaxation():
    """CREATE改行形もproducerで正規化し、実installerを8本とも通す。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    declarations, _ = candidate_declarations()
    identifiers = [row["function_id"] for row in declarations["functions"]]
    identifiers.append(
        "FUNCTION:sync_right_api:guard_first_ball_projection_admission()"
    )
    assert len(identifiers) == 8
    for identifier in identifiers:
        canonical = body("function", identifier)
        assert canonical is not None
        assert "CREATE FUNCTION sync_right_api." in canonical
        assert "CREATE FUNCTION\nsync_right_api." not in canonical
        rendered = application_function_sql(identifier, canonical)
        assert type(rendered) is str
        assert "DO $first_ball_reapply$" in rendered


def test_trigger_catalog_observation_keeps_table_association():
    """同じname/functionを別tableへ移した欠陥を集合比較で見落とさない。"""
    from pitchlog.authz.product_catalog import CatalogQueryId, _query_for_id

    query = _query_for_id(CatalogQueryId.PLAY_PREFIX_TRIGGERS)
    assert "CASE WHEN t.tgrelid='public.play_rows'::pg_catalog.regclass" in query
    assert "THEN 'play_rows' ELSE 'play_runners' END,t.tgname" in query
