"""認可適用器の資産指定と操作種別の閉包を検査する。"""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

import db_fixtures
import pytest

from pitchlog.authz import asset_spec
from pitchlog.authz.asset_spec import (
    PROBE_SPEC,
    AuthzAssetSpec,
    AuthzOperationHandlerSpec,
)
from pitchlog.authz.catalog import inspect_authz_catalog
from pitchlog.authz.provisioning import (
    ProvisioningError,
    _operation_handlers_for,
    _ordered_steps,
    apply_authz_ddl,
)

_TEST_OPERATION = "test_asset_operation"
_TEST_SPEC = replace(
    PROBE_SPEC,
    asset_root=PurePosixPath("test-authz"),
    ddl_elements_path=PurePosixPath("test-authz/ddl-elements.json"),
    body_manifest_path=PurePosixPath("test-authz/function-bodies/manifest.json"),
    body_directory=PurePosixPath("test-authz/function-bodies"),
    allowed_scope_status="test_configuration",
    asset_kind="product",
    operation_handlers=(AuthzOperationHandlerSpec(_TEST_OPERATION, "_create_roles"),),
)


def _asset_with_operation(operation_kind: str) -> dict[str, object]:
    """単一の操作種別を持つ最小の適用手順資産を作る。"""
    return {
        "provisioning_claim": {
            "ordered_steps": [
                {
                    "step_id": "test-step",
                    "sequence": 1,
                    "operation_kind": operation_kind,
                }
            ]
        },
        "transaction_boundaries": [
            {
                "boundary_kind": "ordered_application",
                "step_ids": ["test-step"],
                "atomic": False,
            }
        ],
    }


def test_probe_spec_owns_exactly_the_existing_operation_handlers() -> None:
    """現行 5 種だけが PROBE_SPEC の閉じた対応に属する。"""
    assert _operation_handlers_for(PROBE_SPEC) == {
        "create_no_login_bypass_owner": "_create_roles",
        "temporarily_grant_set_membership": "_open_set_path",
        "create_and_assign_owned_objects": "_assign_objects",
        "revoke_public_and_grant_named_execute": "_close_function_acl",
        "revoke_temporary_membership": "_close_set_path",
    }


def test_non_probe_test_spec_accepts_only_its_operation_kind() -> None:
    """非 probe の試験用 spec は自身の操作種別だけを受理する。"""
    steps = _ordered_steps(_asset_with_operation(_TEST_OPERATION), _TEST_SPEC)

    assert tuple(step.operation_kind for step in steps) == (_TEST_OPERATION,)
    assert _operation_handlers_for(_TEST_SPEC) == {_TEST_OPERATION: "_create_roles"}


@pytest.mark.parametrize(
    "foreign_operation",
    [
        pytest.param("not_declared_by_test_spec", id="undeclared-operation"),
        pytest.param(
            "create_no_login_bypass_owner",
            id="probe-operation",
        ),
    ],
)
def test_non_probe_test_spec_rejects_foreign_operation_kinds(
    foreign_operation: str,
) -> None:
    """試験用 spec に無い種別は未宣言・probe 由来の双方を拒否する。"""
    _ordered_steps(_asset_with_operation(_TEST_OPERATION), _TEST_SPEC)

    with pytest.raises(ProvisioningError, match="未対応"):
        _ordered_steps(_asset_with_operation(foreign_operation), _TEST_SPEC)


def test_asset_spec_rejects_duplicate_operation_kinds() -> None:
    """処理関数が異なっても同じ操作種別の重複を拒否する。"""
    with pytest.raises(ValueError, match="操作種別は一意"):
        replace(
            _TEST_SPEC,
            operation_handlers=(
                AuthzOperationHandlerSpec(_TEST_OPERATION, "_create_roles"),
                AuthzOperationHandlerSpec(_TEST_OPERATION, "_open_set_path"),
            ),
        )


def test_public_entry_points_default_to_probe_spec() -> None:
    """適用器と DB カタログ検査の無指定呼び出しを probe に保つ。"""
    apply_default = inspect.signature(apply_authz_ddl).parameters["spec"].default
    inspect_default = (
        inspect.signature(inspect_authz_catalog).parameters["spec"].default
    )

    assert apply_default is PROBE_SPEC
    assert inspect_default is PROBE_SPEC


def test_db_fixture_loader_uses_the_given_spec_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB 接続なしで fixture の資産読取先を spec から差し替える。"""
    expected = {"asset": "non-probe-test"}
    asset_path = tmp_path / _TEST_SPEC.ddl_elements_path
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(
        json.dumps(expected, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(db_fixtures, "_REPOSITORY_ROOT", tmp_path)

    assert db_fixtures._load_ddl_asset(_TEST_SPEC) == expected


def test_product_spec_is_not_defined_in_step_five() -> None:
    """試験用 spec を製品の正規 spec として公開していないことを確かめる。"""
    assert isinstance(_TEST_SPEC, AuthzAssetSpec)
    assert not hasattr(asset_spec, "PRODUCT_SPEC")
