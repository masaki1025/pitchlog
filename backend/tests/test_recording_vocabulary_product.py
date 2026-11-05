"""打球語彙readの新role/関数定義と既固定関数の拒否境界を検査する。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.authz import first_ball_product as product

_FUNCTION = "FUNCTION:recording_vocab_api:read_batted_ball_options(uuid, integer, text)"
_OWNER = "pitchlog_recording_vocab_fn_owner"
_ROOT = Path(__file__).resolve().parents[2]


def test_stable_catalog_read_is_kept_stable_on_first_apply_and_reapply():
    """SELECT専用の安定性を再適用時にvolatileへ誤変換しない。"""
    row = product.declaration("functions", _FUNCTION)
    assert row is not None and row["volatility"] == "stable"
    body = product.body("function", _FUNCTION)
    assert body is not None
    result = product.application_function_sql(_FUNCTION, body)
    assert result is not None and "p.provolatile='s'" in result
    assert "p.provolatile='v'" not in result
    assert "STABLE" in body and f"OWNER TO {_OWNER}" in body
    assert "FROM PUBLIC,pitchlog_app" in body
    assert "TO pitchlog_app" in body
    for detail in product.function_details():
        if detail[:2] == ("recording_vocab_api", "read_batted_ball_options"):
            assert detail[7] == "s"
        else:
            assert detail[7] == "v"


def test_catalog_roles_and_schema_have_collision_guards_without_new_memberships():
    """既存の過大roleや別ownerを再利用して成功させない。"""
    role = product.body("role", _OWNER)
    schema = product.body("schema", "recording_vocab_api")
    assert role is not None and schema is not None
    assert "pg_auth_members" in role and "NOBYPASSRLS" in role
    assert "NOLOGIN" in role and "NOINHERIT" in role
    assert "RAISE EXCEPTION" in role and "RAISE EXCEPTION" in schema
    assert "REVOKE CREATE ON SCHEMA recording_vocab_api FROM pitchlog_app" in schema


@pytest.mark.parametrize(
    "mutation",
    ("login", "bypass", "schema-owner", "execute-public", "predicate", "extra-column"),
)
def test_catalog_authority_mutations_are_rejected_by_canonical_profile(mutation):
    """一箇所の宣言自己改変でも閉じた採用profileを迂回できない。"""
    asset = json.loads(
        (_ROOT / "contracts/authz/product/ddl-elements.json").read_text()
    )
    assert product.validate(asset)
    changed = copy.deepcopy(asset)
    if mutation in {"login", "bypass"}:
        row = next(x for x in changed["roles"] if x["role_id"] == _OWNER)
        row["login" if mutation == "login" else "bypass_rls"] = True
    elif mutation == "schema-owner":
        row = next(
            x for x in changed["schemas"] if x["schema_name"] == "recording_vocab_api"
        )
        row["owner"] = "pitchlog_app"
    elif mutation == "execute-public":
        row = next(x for x in changed["functions"] if x["function_id"] == _FUNCTION)
        row["acl_expectations"].append(
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        )
    elif mutation == "predicate":
        row = next(
            x
            for x in changed["policies"]
            if x.get("policy_name") == "recording_vocab_select_batted_ball"
        )
        row["using_expression"] = "true"
    else:
        row = copy.deepcopy(
            next(
                x
                for x in changed["column_acl_expectations"]
                if x["grantee_role_id"] == _OWNER
            )
        )
        row["expectation_id"] += "-unaccepted"
        row["column_id"] = "tenant_id"
        changed["column_acl_expectations"].append(row)
    with pytest.raises(ValueError):
        product.validate(changed)


def test_official_runtime_projection_preserves_application_role_identity():
    """部分導出の上書きでrole名を落としても成功としない回帰。"""
    from pitchlog.authz.runtime_contract_state import derive_runtime_contract_fields

    runtime = json.loads(
        (_ROOT / "contracts/tenant_boundary/runtime-authz-contract.json").read_text()
    )
    assert runtime["application_role"]["rolname"] == "pitchlog_app"
    derived = derive_runtime_contract_fields(
        _ROOT / "contracts/authz/product/ddl-elements.json", runtime
    )
    assert all(
        runtime["application_role"][key] == value
        for key, value in derived["application_role"].items()
    )
    assert runtime["protected_objects"] == derived["protected_objects"]
    from pitchlog.authz.runtime_contract_generator import check_repository

    assert check_repository(_ROOT) == set()


def test_catalog_reads_new_schema_with_all_prior_lifecycle_schemas() -> None:
    """新語彙関数も実カタログの全属性照合へ含め、旧schemaを保持する。"""
    from pitchlog.authz import product_catalog

    query = product_catalog._LIFECYCLE_FUNCTION_DETAILS_QUERY
    for schema in (
        "rg1_control",
        "pitchlog_ledger_observer",
        "initial_right_api",
        "sync_fence_api",
        "sync_right_api",
        "recording_vocab_api",
    ):
        assert "'" + schema + "'" in query
    assert "routine.provolatile::text" in query
    assert "routine.proconfig, routine.prosrc" in query
