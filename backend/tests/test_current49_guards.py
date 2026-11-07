"""通常49のprivate初期helperと監査guardの閉境界を検査する。"""

import copy
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from pitchlog.authz.product_catalog import (
    _COLUMN_ACL_QUERY,
    ProductCatalogError,
    _validate_initial_function_declarations,
    _validated_initial_column_rows,
    _validated_initial_policy_rows,
)
from pitchlog.db import current_product_startup as current

_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED = [
    ("d03_pitcher_entry_immutable", 27, True),
    ("d03_pitcher_entry_no_truncate", 34, True),
]


def test_entry_xmin_is_observed_without_granting_it():
    """新表の余剰system列権限も取得し、正規ACLへ補わない。"""
    assert "('sync_fence', 'pitcher_entry_sources')" in _COLUMN_ACL_QUERY
    assert not any(
        row["object_id"] == "pitcher_entry_sources" and row["column_id"] == "xmin"
        for row in _asset()["column_acl_expectations"]
    )


def _connection(rows):
    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=lambda _sql: None, fetchall=lambda: rows)

    return SimpleNamespace(cursor=cursor)


def test_full_and_pre_full_guard_states_are_distinct():
    """正規未適用と完成だけを受け、途中の1guardを完成へ補修しない。"""
    current._check_pitcher_entry_guards(_connection([]), "pre-full")
    current._check_pitcher_entry_guards(_connection(_EXPECTED), "full")
    with pytest.raises(current.CurrentProductStartupError):
        current._check_pitcher_entry_guards(_connection(_EXPECTED), "pre-full")
    with pytest.raises(current.CurrentProductStartupError):
        current._check_pitcher_entry_guards(_connection([]), "full")


@pytest.mark.parametrize("fault", ["partial", "extra", "disabled", "kind", "name"])
def test_guard_missing_extra_or_changed_shape_is_rejected(fault):
    """未知guard/条件付き属性不一致を無視せず公開を止める。"""
    rows = list(_EXPECTED)
    if fault == "partial":
        rows.pop()
    elif fault == "extra":
        rows.append(("unknown_guard", 27, True))
    elif fault == "disabled":
        rows[0] = (rows[0][0], rows[0][1], False)
    elif fault == "kind":
        rows[0] = (rows[0][0], 23, True)
    else:
        rows[0] = ("wrong_guard", 27, True)
    with pytest.raises(current.CurrentProductStartupError):
        current._check_pitcher_entry_guards(_connection(rows), "full")


def _asset():
    return json.loads(
        (_ROOT / "contracts/authz/product/ddl-elements.json").read_bytes()
    )


def test_private_initial_helper_is_accepted_only_as_full_d03_profile():
    """公開初期ABIは増やさず、新owner helperの全metadataを閉検査する。"""
    _validate_initial_function_declarations(_asset())


@pytest.mark.parametrize("fault", ["missing-helper", "owner", "execute", "table"])
def test_private_initial_helper_partial_or_extended_profile_is_rejected(fault):
    """未完全profileやPUBLIC/actorへの権限拡大を初期reserved集合へ入れない。"""
    asset = copy.deepcopy(_asset())
    key = "FUNCTION:initial_right_api:persist_start_pitcher_entry(uuid, uuid, bigint)"
    row = next(r for r in asset["functions"] if r["function_id"] == key)
    if fault == "missing-helper":
        asset["functions"].remove(row)
    elif fault == "owner":
        row["owner_role_id"] = "PUBLIC"
    elif fault == "execute":
        row["acl_expectations"].append(
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        )
    else:
        asset["tables"] = [
            r for r in asset["tables"] if r["table_id"] != "pitcher_entry_sources"
        ]
    with pytest.raises(ProductCatalogError):
        _validate_initial_function_declarations(asset)


def test_initial_columns_require_complete_canonical_d03_profile():
    """追加17列の正規権限だけを初期reserved集合へ受け入れる。"""
    _validated_initial_column_rows(_asset())


@pytest.mark.parametrize("fault", ["missing", "privilege", "owner", "extra"])
def test_initial_column_profile_cannot_be_reduced_or_expanded(fault):
    """欠落・余剰・owner変更・権限拡大を補修せず拒否する。"""
    asset = _asset()
    row = next(
        r
        for r in asset["column_acl_expectations"]
        if r["object_id"] == "pitcher_entry_sources"
        and r["grantee_role_id"] == "pitchlog_initial_fn_owner"
    )
    if fault == "missing":
        asset["column_acl_expectations"].remove(row)
    elif fault == "privilege":
        row["privilege_ids"].append("UPDATE")
    elif fault == "owner":
        row["grantee_role_id"] = "pitchlog_app"
    else:
        extra = copy.deepcopy(row)
        extra["expectation_id"] += ":unknown"
        asset["column_acl_expectations"].append(extra)
    with pytest.raises(ProductCatalogError):
        _validated_initial_column_rows(asset)


def test_initial_policy_profile_matches_canonical_d03_scope():
    """既初期policyに新しい有限2policyだけを接合する。"""
    _validated_initial_policy_rows(_asset())


@pytest.mark.parametrize("fault", ["missing", "role", "predicate", "extra"])
def test_initial_policy_profile_rejects_missing_or_expanded_access(fault):
    """初期ownerのtenant条件や主体の拡大を拒否する。"""
    asset = _asset()
    row = next(r for r in asset["policies"] if r["table_id"] == "pitcher_entry_sources")
    if fault == "missing":
        asset["policies"].remove(row)
    elif fault == "role":
        row["role_ids"].append("pitchlog_app")
    elif fault == "predicate":
        row["using_expression"] = "true"
    else:
        extra = copy.deepcopy(row)
        extra["policy_id"] += ":unknown"
        asset["policies"].append(extra)
    with pytest.raises(ProductCatalogError):
        _validated_initial_policy_rows(asset)
