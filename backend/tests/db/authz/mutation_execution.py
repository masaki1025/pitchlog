"""全 mutation の資産駆動適用と三チャネル観測を提供する。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import secrets
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Final, LiteralString, TypeVar, cast
from unittest.mock import patch

import psycopg
import pytest
from _pytest.outcomes import Failed
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz import provisioning
from pitchlog.authz.ddl import DDLStatement, generate_authz_ddl
from pitchlog.authz.provisioning import ProvisioningResult

from .mutation import (
    ApplicationObservation,
    CatalogDelta,
    ChannelObservation,
    ExecutionPhase,
    ExecutionStatus,
    FailureKind,
    MutantSpec,
    MutationCatalog,
    MutationContractError,
    MutationEnvironment,
    MutationObservation,
    MutationRunner,
    MutationVerdict,
    MutationVerdictError,
    NotRunReason,
    _bind_exact_implementations,
    judge_mutation,
    mutation_plan,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DDL_ELEMENTS_PATH = REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
CLAIM_MUTANT_MAP_PATH = REPOSITORY_ROOT / "contracts/authz/claim-mutant-map.json"
REQUIREMENT_CLAIMS_PATH = REPOSITORY_ROOT / "contracts/authz/requirement-claims.json"
REQUIREMENT_CLAIMS_LOCK_PATH = (
    REPOSITORY_ROOT / "contracts/authz/requirement-claims.lock.json"
)
ROUTE_REGISTRY_PATH = REPOSITORY_ROOT / "contracts/authz/route-registry.json"
ORACLE_SEAL_PATH = REPOSITORY_ROOT / "contracts/authz/oracle-seal.lock.json"
AUTHZ_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_authz_catalog.py"

_MUTATION_AXIS_ENV = "PITCHLOG_MUTATION_AXIS"
_MUTATION_OPERATOR_ENV = "PITCHLOG_MUTATION_OPERATOR"
_TABLE_PRIVILEGE_PREFIX = "TABLE-PRIVILEGE:"
_CLAIM_DECISION_MODE = "claim_decision"
_NO_DATABASE_MODE = "no_database_mutation"
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_FUNCTION_IDENTITY_RE = re.compile(r'^[a-zA-Z0-9_"., ()\[\]]+$')
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class MutationBlueprint:
    """1 operator が導出した対象と DB 適用方式を保持する。"""

    mutant_id: str
    operator_id: str
    changed_element_ids: frozenset[str]
    database_mode: str


@dataclass(frozen=True, slots=True)
class MutationBatch:
    """同じ axis・operator で実行する mutation の刻みを表す。"""

    axis: str
    operator_id: str
    mutant_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MutationExecutionRecord:
    """判定不能・生存を人手判定へ渡す機械可読レコード。"""

    mutant_id: str
    axis: str
    operator_id: str
    failed_checks: tuple[str, ...]
    surviving_channels: tuple[str, ...]
    observation: Mapping[str, object] | None
    execution_error: str | None

    def to_json(self) -> str:
        """安定キー順の JSON Lines 1 行を返す。"""
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class MutationBatchError(AssertionError):
    """全件継続後に残った生存・実行不能 mutation を表す。"""

    def __init__(self, records: tuple[MutationExecutionRecord, ...]) -> None:
        """機械可読レコードを保持し、例外本文にも JSON Lines を載せる。"""
        self.records = records
        lines = "\n".join(record.to_json() for record in records)
        super().__init__(f"mutation-survivors-jsonl:\n{lines}")


OperatorImplementation = Callable[[MutantSpec], MutationBlueprint]


def _claim_blueprint(spec: MutantSpec) -> MutationBlueprint:
    """Claim ID 自体を対象とする認可述語 mutation を組み立てる。"""
    targets = frozenset(spec.claim_ids)
    if spec.target_element_ids != targets:
        raise MutationContractError(
            f"{spec.mutant_id}: claim_ids と target_element_ids が一致しない"
        )
    return MutationBlueprint(
        mutant_id=spec.mutant_id,
        operator_id=spec.operator_id,
        changed_element_ids=targets,
        database_mode=_CLAIM_DECISION_MODE,
    )


def _target_blueprint(spec: MutantSpec) -> MutationBlueprint:
    """資産が宣言した構成対象をそのまま DB 適用へ引き渡す。"""
    if not spec.target_element_ids:
        raise MutationContractError(f"{spec.mutant_id}: mutation 対象が空である")
    return MutationBlueprint(
        mutant_id=spec.mutant_id,
        operator_id=spec.operator_id,
        changed_element_ids=spec.target_element_ids,
        database_mode=spec.operator_id,
    )


def _handoff_claim_blueprint(spec: MutantSpec) -> MutationBlueprint:
    """Runtime を受取先へ渡す claim mutation を静的適用だけへ束ねる。"""
    blueprint = _claim_blueprint(spec)
    if spec.expected_runtime_outcome != "handoff":
        return blueprint
    return replace(blueprint, database_mode=_NO_DATABASE_MODE)


_OPERATOR_IMPLEMENTATIONS: Final[Mapping[str, OperatorImplementation]] = {
    "NEGATE_CLAIM_DECISION_UNIT": _handoff_claim_blueprint,
    "OMIT_ORDERED_STEP": _target_blueprint,
    "OVERAPPLY_SELF_TENANT_EXCEPTION": _handoff_claim_blueprint,
    "REMOVE_CONTROL_COMMON_PRECONDITION": _handoff_claim_blueprint,
    "REMOVE_EXPORT_SUBORDINATE_GRANT": _handoff_claim_blueprint,
    "REMOVE_GROUP_ACTIVE": _handoff_claim_blueprint,
    "REMOVE_KIND_SELF_GUARD": _handoff_claim_blueprint,
    "REMOVE_LAST_ADMIN_INVARIANT": _claim_blueprint,
    "REMOVE_OPERATION_ROLE_CONDITION": _claim_blueprint,
    "REMOVE_REQUESTER_MEMBERSHIP": _handoff_claim_blueprint,
    "REMOVE_TARGET_ACTIVE": _handoff_claim_blueprint,
    "REORDER_ORDERED_STEPS": _target_blueprint,
    "USE_OTHER_GROUP_GRANT": _handoff_claim_blueprint,
    "add_permissive_policy": _target_blueprint,
    "add_role_membership": _target_blueprint,
    "disable_force_rls": _target_blueprint,
    "grant_app_role_control_table_dml": _target_blueprint,
    "grant_database_temporary": _target_blueprint,
    "grant_function_execute": _target_blueprint,
    "grant_management_caller_table_privilege": _target_blueprint,
    "grant_schema_create": _target_blueprint,
    "omit_acl_revocation": _target_blueprint,
    "remove_policy_predicate": _target_blueprint,
    "remove_role_attribute": _target_blueprint,
    "remove_search_path_element": _target_blueprint,
    "replace_owner": _target_blueprint,
    "split_authorization_and_side_effect": _target_blueprint,
}


def bind_operator_implementations(
    catalog: MutationCatalog,
) -> Mapping[str, OperatorImplementation]:
    """資産由来 operator 集合を実装マップと exact-set 結合する。

    Args:
        catalog: Step 17 で検証済みの mutation 契約。

    Returns:
        余剰・不足がない不変の operator 実装マップ。
    """
    operator_ids = frozenset(spec.operator_id for spec in catalog.mutants)
    _bind_exact_implementations(
        operator_ids,
        _OPERATOR_IMPLEMENTATIONS,
        "mutation operator",
    )
    return MappingProxyType(dict(_OPERATOR_IMPLEMENTATIONS))


def mutation_blueprint(
    spec: MutantSpec,
    implementations: Mapping[str, OperatorImplementation],
) -> MutationBlueprint:
    """Mutant の operator と対象から適用計画を構築する。"""
    try:
        blueprint = implementations[spec.operator_id](spec)
    except KeyError as error:
        raise MutationContractError(
            f"{spec.mutant_id}: 未実装operator: {spec.operator_id}"
        ) from error
    if blueprint.changed_element_ids != spec.target_element_ids:
        raise MutationContractError(
            f"{spec.mutant_id}: 実装が全宣言対象を変更していない"
        )
    return blueprint


def mutation_batches(catalog: MutationCatalog) -> tuple[MutationBatch, ...]:
    """少数 axis、少数 operator の順へ全 mutation を分割する。"""
    by_axis: defaultdict[str, list[MutantSpec]] = defaultdict(list)
    for spec in catalog.mutants:
        by_axis[spec.axis].append(spec)

    batches: list[MutationBatch] = []
    for axis, axis_specs in sorted(
        by_axis.items(), key=lambda item: (len(item[1]), item[0])
    ):
        by_operator: defaultdict[str, list[MutantSpec]] = defaultdict(list)
        for spec in axis_specs:
            by_operator[spec.operator_id].append(spec)
        for operator_id, specs in sorted(
            by_operator.items(), key=lambda item: (len(item[1]), item[0])
        ):
            batches.append(
                MutationBatch(
                    axis=axis,
                    operator_id=operator_id,
                    mutant_ids=tuple(spec.mutant_id for spec in specs),
                )
            )
    return tuple(batches)


def select_mutation_batches(
    catalog: MutationCatalog,
    *,
    axis: str | None,
    operator_id: str | None,
) -> tuple[MutationBatch, ...]:
    """任意の axis・operator フィルタを閉じた資産語彙で適用する。"""
    batches = mutation_batches(catalog)
    axis_ids = frozenset(batch.axis for batch in batches)
    operator_ids = frozenset(batch.operator_id for batch in batches)
    if axis is not None and axis not in axis_ids:
        raise MutationContractError(f"未知のmutation axis: {axis}")
    if operator_id is not None and operator_id not in operator_ids:
        raise MutationContractError(f"未知のmutation operator: {operator_id}")
    selected = tuple(
        batch
        for batch in batches
        if (axis is None or batch.axis == axis)
        and (operator_id is None or batch.operator_id == operator_id)
    )
    if not selected:
        raise MutationContractError(
            f"axis/operator の交点にmutationがない: {axis}/{operator_id}"
        )
    return selected


def mutation_filters_from_environment(
    environment: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """実機の分割実行用フィルタを環境変数から読む。"""
    return (
        environment.get(_MUTATION_AXIS_ENV) or None,
        environment.get(_MUTATION_OPERATOR_ENV) or None,
    )


def _read_json_object(path: Path) -> dict[str, object]:
    """JSON object 資産を型確認して読む。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MutationContractError(
            f"mutation入力を読めない: {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise MutationContractError(f"mutation入力がobjectでない: {path}")
    return value


def _object_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """Object 配列を取得する。"""
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise MutationContractError(f"{label}はobject配列が必要")
    return tuple(row for row in value if isinstance(row, dict))


def _only(rows: Iterable[_T], label: str) -> _T:
    """一意な資産行を返す。"""
    values = tuple(rows)
    if len(values) != 1:
        raise MutationContractError(f"{label}を一意に導出できない")
    return values[0]


def _text(value: object, label: str) -> str:
    """空でない文字列だけを返す。"""
    if not isinstance(value, str) or not value:
        raise MutationContractError(f"{label}は空でない文字列が必要")
    return value


def _load_checker() -> ModuleType:
    """Root の独立検査器を通常 import path に依存せず読む。"""
    spec = importlib.util.spec_from_file_location(
        "authz_mutation_catalog_checker", AUTHZ_CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise MutationContractError("認可カタログ検査器をロードできない")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CHECKER = _load_checker()


def _negate_requirement_decisions(spec: MutantSpec) -> dict[str, object]:
    """対象 claim の分類決定だけを反転した一時資産を返す。"""
    mutated = copy.deepcopy(_read_json_object(REQUIREMENT_CLAIMS_PATH))
    rows = _object_rows(mutated.get("claims"), "requirement-claims.claims")
    changed: set[str] = set()
    for claim_id in spec.claim_ids:
        row = _only(
            (row for row in rows if row.get("source_id") == claim_id),
            f"requirement claim {claim_id}",
        )
        classification = _text(row.get("classification"), f"{claim_id}.classification")
        row["classification"] = f"not_{classification}"
        changed.add(claim_id)
    if changed != set(spec.target_element_ids):
        raise MutationContractError(
            f"{spec.mutant_id}: claim decision の変更対象が宣言と一致しない"
        )
    return mutated


def _mutate_selected_record(spec: MutantSpec) -> dict[str, object]:
    """設計 claim 用に選択 mutant の decision form だけを反転する。"""
    mutated = copy.deepcopy(_read_json_object(CLAIM_MUTANT_MAP_PATH))
    rows = _object_rows(mutated.get("mutants"), "claim-mutant-map.mutants")
    row = _only(
        (row for row in rows if row.get("mutant_id") == spec.mutant_id),
        f"mutant {spec.mutant_id}",
    )
    decision_form = _text(row.get("decision_form"), "mutant.decision_form")
    row["decision_form"] = f"NOT_{decision_form}"
    return mutated


def _mutable_string_list(row: dict[str, object], key: str, label: str) -> list[str]:
    """一時 JSON 行から可変な文字列配列を取得する。"""
    values = row.get(key)
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise MutationContractError(f"{label}.{key}が文字列配列でない")
    return values


def _ddl_row(
    asset: dict[str, object], section: str, id_key: str, element_id: str
) -> dict[str, object]:
    """一時 DDL 資産から ID 一致行を返す。"""
    return _only(
        (
            row
            for row in _object_rows(asset.get(section), f"ddl-elements.{section}")
            if row.get(id_key) == element_id
        ),
        f"ddl-elements.{section}/{element_id}",
    )


def _mutate_ddl_configuration(spec: MutantSpec) -> dict[str, object]:
    """構成 target grammar から事前構成の一時 DDL 資産を実際に変異する。"""
    asset = copy.deepcopy(_read_json_object(DDL_ELEMENTS_PATH))
    operator_id = spec.operator_id
    if operator_id == "remove_role_attribute":
        role_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        role = _ddl_row(asset, "roles", "role_id", role_id)
        role[attribute_id] = False
    elif operator_id == "replace_owner":
        function_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        function = _ddl_row(asset, "functions", "function_id", function_id)
        function[attribute_id] = _asset_role_id(asset, "tested_caller")
    elif operator_id == "omit_acl_revocation":
        function_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        function = _ddl_row(asset, "functions", "function_id", function_id)
        function[attribute_id] = True
    elif operator_id == "remove_search_path_element":
        function_id, attribute_id, removed_id = _parse_colon_target(
            _single_target(spec), 3
        )
        function = _ddl_row(asset, "functions", "function_id", function_id)
        values = _mutable_string_list(function, attribute_id, function_id)
        function[attribute_id] = [value for value in values if value != removed_id]
    elif operator_id == "disable_force_rls":
        table_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        table = _ddl_row(asset, "tables", "table_id", table_id)
        table[attribute_id] = False
    elif operator_id == "grant_schema_create":
        schema_id, role_id, privilege_id = _parse_colon_target(_single_target(spec), 3)
        if privilege_id != "CREATE":
            raise MutationContractError("schema CREATE targetでない")
        schema = _ddl_row(asset, "schemas", "schema_id", schema_id)
        _mutable_string_list(schema, "create_role_ids", schema_id).append(role_id)
    elif operator_id == "grant_function_execute":
        function_id, role_id, privilege_id = _parse_colon_target(
            _single_target(spec), 3
        )
        if privilege_id != "EXECUTE":
            raise MutationContractError("function EXECUTE targetでない")
        function = _ddl_row(asset, "functions", "function_id", function_id)
        _mutable_string_list(function, "execute_role_ids", function_id).append(role_id)
    elif operator_id == "remove_policy_predicate":
        prefix, table_id, policy_name, attribute_id = _parse_colon_target(
            _single_target(spec), 4
        )
        policy_id = f"{prefix}:{table_id}:{policy_name}"
        policy = _ddl_row(asset, "policies", "policy_id", policy_id)
        if attribute_id != "with_check":
            raise MutationContractError("WITH CHECK targetでない")
        del policy["with_check_predicate_id"]
    elif operator_id == "add_permissive_policy":
        table_id, predicate_id = _parse_colon_target(_single_target(spec), 2)
        table = _ddl_row(asset, "tables", "table_id", table_id)
        policy_id = f"POLICY:{table_id}:{predicate_id.casefold()}"
        _mutable_string_list(table, "policy_ids", table_id).append(policy_id)
        policies = asset.get("policies")
        if not isinstance(policies, list):
            raise MutationContractError("ddl-elements.policiesが配列でない")
        policies.append(
            {
                "policy_id": policy_id,
                "table_id": table_id,
                "command": "ALL",
                "policy_mode": "permissive",
                "role_ids": [_asset_role_id(asset, "tested_caller")],
                "using_predicate_id": predicate_id,
                "with_check_predicate_id": predicate_id,
            }
        )
    elif operator_id in {
        "grant_management_caller_table_privilege",
        "grant_app_role_control_table_dml",
    }:
        by_pair: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
        for table_id, role_id, privilege_id in _table_privilege_target_rows(spec):
            by_pair[(table_id, role_id)].append(privilege_id)
        acl_rows = asset.get("acl_expectations")
        if not isinstance(acl_rows, list):
            raise MutationContractError("ddl-elements.acl_expectationsが配列でない")
        for (table_id, role_id), privileges in by_pair.items():
            matches = [
                row
                for row in acl_rows
                if isinstance(row, dict)
                and row.get("object_kind") == "table"
                and row.get("object_id") == table_id
                and row.get("grantee_role_id") == role_id
            ]
            if matches:
                row = _only(matches, f"table ACL {table_id}/{role_id}")
                values = _mutable_string_list(row, "privilege_ids", "table ACL")
                values.extend(value for value in privileges if value not in values)
            else:
                acl_rows.append(
                    {
                        "acl_id": f"ACL:{table_id}:{role_id}:mutation",
                        "object_kind": "table",
                        "object_id": table_id,
                        "grantee_role_id": role_id,
                        "privilege_ids": privileges,
                        "grant_option": False,
                    }
                )
    elif operator_id == "split_authorization_and_side_effect":
        boundary_ids = {
            target for target in spec.target_element_ids if target.startswith("TX:")
        }
        if len(boundary_ids) != 1:
            raise MutationContractError("transaction boundary targetが一意でない")
        boundary_id = next(iter(boundary_ids))
        boundary = _ddl_row(asset, "transaction_boundaries", "boundary_id", boundary_id)
        boundary["atomic"] = False
        probe = asset.get("representative_management_probe")
        if not isinstance(probe, dict):
            raise MutationContractError("representative_management_probeがobjectでない")
        probe["authorization_and_side_effect_same_function"] = False
        probe["authorization_and_side_effect_same_transaction"] = False
    elif operator_id == "OMIT_ORDERED_STEP":
        claim = asset.get("provisioning_claim")
        if not isinstance(claim, dict):
            raise MutationContractError("provisioning_claimがobjectでない")
        steps = _object_rows(claim.get("ordered_steps"), "ordered_steps")
        claim["ordered_steps"] = [
            row for row in steps if row.get("step_id") not in spec.target_element_ids
        ]
    elif operator_id == "REORDER_ORDERED_STEPS":
        claim = asset.get("provisioning_claim")
        if not isinstance(claim, dict):
            raise MutationContractError("provisioning_claimがobjectでない")
        steps = _object_rows(claim.get("ordered_steps"), "ordered_steps")
        selected = [
            row for row in steps if row.get("step_id") in spec.target_element_ids
        ]
        if len(selected) != len(spec.target_element_ids):
            raise MutationContractError("順序反転stepを一意に導出できない")
        sequences = [row.get("sequence") for row in selected]
        for row, sequence in zip(selected, reversed(sequences), strict=True):
            row["sequence"] = sequence
    elif operator_id in {"add_role_membership", "grant_database_temporary"}:
        claim = asset.get("provisioning_claim")
        if not isinstance(claim, dict):
            raise MutationContractError("provisioning_claimがobjectでない")
        expectations = claim.get("completion_catalog_expectations")
        if not isinstance(expectations, list):
            raise MutationContractError("completion catalog expectationsが配列でない")
        expectations.append(
            {
                "catalog_check_id": sorted(spec.target_element_ids)[0],
                "inspection_predicate": "mutation_target_present = true",
            }
        )
    else:
        raise MutationContractError(f"DDL asset mutationが未実装: {operator_id}")
    return asset


def observe_schema_drift(
    spec: MutantSpec,
    blueprint: MutationBlueprint,
) -> ChannelObservation:
    """Step 9 の独立検査器で一時 mutation が red になることを観測する。

    実リポジトリの凍結資産は書き換えず、メモリ上のコピーだけを公開検査関数へ
    渡す。要件 claim は decision lock、それ以外は oracle seal を用いる。
    """
    try:
        if spec.axis == "authorization_predicate":
            requirement_asset = _read_json_object(REQUIREMENT_CLAIMS_PATH)
            source_ids = {
                row.get("source_id")
                for row in _object_rows(
                    requirement_asset.get("claims"), "requirement-claims.claims"
                )
            }
            if set(spec.claim_ids) <= source_ids:
                mutated = _negate_requirement_decisions(spec)
                lock = _read_json_object(REQUIREMENT_CLAIMS_LOCK_PATH)
                _CHECKER.validate_decision_lock(
                    mutated,
                    lock,
                    "contracts/authz/requirement-claims.json",
                )
            else:
                # 要件 1 行を分解した派生 claim は母集合行を持たないため、
                # その claim を所有する封印済み mutant 行を反転する。
                mutated = _mutate_selected_record(spec)
                seal = _read_json_object(ORACLE_SEAL_PATH)
                _CHECKER.validate_oracle_asset_seal(
                    mutated,
                    "contracts/authz/claim-mutant-map.json",
                    seal,
                )
        else:
            mutated = _mutate_ddl_configuration(spec)
            seal = _read_json_object(ORACLE_SEAL_PATH)
            _CHECKER.validate_oracle_asset_seal(
                mutated,
                "contracts/authz/ddl-elements.json",
                seal,
            )
    except _CHECKER.CatalogError:
        return ChannelObservation.expected_assertion_failure()
    except Exception:
        return ChannelObservation(
            status=ExecutionStatus.ERROR,
            phase=ExecutionPhase.CALL,
            failure_kind=FailureKind.OTHER,
        )
    if blueprint.changed_element_ids:
        return ChannelObservation.passed()
    return ChannelObservation(
        status=ExecutionStatus.ERROR,
        phase=ExecutionPhase.CALL,
        failure_kind=FailureKind.OTHER,
    )


@dataclass(slots=True)
class _RuntimeContext:
    """1 mutation 専用 DB の管理接続・実ロール接続を束ねる。"""

    admin: psycopg.Connection[Any]
    catalog: Any
    role_connections: Mapping[str, psycopg.Connection[Any]]
    asset: dict[str, object]
    statements: tuple[DDLStatement, ...]
    provisioner_id: str


def _asset_role_id(asset: dict[str, object], role_kind: str) -> str:
    """Role kind から一意な role ID を導出する。"""
    row = _only(
        (
            row
            for row in _object_rows(asset.get("roles"), "ddl-elements.roles")
            if row.get("role_kind") == role_kind
        ),
        f"role kind {role_kind}",
    )
    return _text(row.get("role_id"), f"{role_kind}.role_id")


def _asset_function(
    asset: dict[str, object],
    *,
    function_id: str | None = None,
    function_class: str | None = None,
) -> dict[str, object]:
    """ID または class から関数資産を一意に導出する。"""
    rows = _object_rows(asset.get("functions"), "ddl-elements.functions")
    return _only(
        (
            row
            for row in rows
            if (function_id is None or row.get("function_id") == function_id)
            and (function_class is None or row.get("function_class") == function_class)
        ),
        f"function {function_id or function_class}",
    )


def _asset_table(asset: dict[str, object], table_id: str) -> dict[str, object]:
    """Table ID から表資産を一意に導出する。"""
    return _only(
        (
            row
            for row in _object_rows(asset.get("tables"), "ddl-elements.tables")
            if row.get("table_id") == table_id
        ),
        f"table {table_id}",
    )


def _provisioner_dsn(
    admin: psycopg.Connection[Any],
    database_dsn: str,
    asset: dict[str, object],
    statements: tuple[DDLStatement, ...],
) -> tuple[str, str]:
    """共有クラスタでも再利用できる外部 provisioner 接続を準備する。"""
    provisioner_id = _asset_role_id(asset, "external_provisioner")
    role_statement = _only(
        (
            statement
            for statement in statements
            if statement.element_type == "role"
            and statement.element_id == provisioner_id
        ),
        "external provisioner DDL",
    )
    password = secrets.token_urlsafe(24)
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s",
            (provisioner_id,),
        )
        if cursor.fetchone() is None:
            cursor.execute(role_statement.sql.encode("utf-8"))
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(provisioner_id),
                sql.Literal(password),
            )
        )
        cursor.execute("SELECT current_database()")
        database_row = cursor.fetchone()
        if database_row is None:
            raise MutationContractError("mutation database ID を取得できない")
        cursor.execute(
            sql.SQL("GRANT CONNECT, CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(str(database_row[0])),
                sql.Identifier(provisioner_id),
            )
        )
    admin.commit()
    return (
        make_conninfo(database_dsn, user=provisioner_id, password=password),
        provisioner_id,
    )


def _sqlstate(error: BaseException) -> str | None:
    """例外連鎖から最初の PostgreSQL SQLSTATE を取得する。"""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, psycopg.Error) and current.sqlstate is not None:
            return current.sqlstate
        current = current.__cause__
    return None


def _apply_provisioning(
    provisioner_dsn: str,
    spec: MutantSpec,
) -> tuple[ApplicationObservation, ProvisioningResult | None]:
    """通常・省略・順序反転のいずれかで DDL を実適用する。"""
    try:
        with psycopg.connect(provisioner_dsn) as connection:
            if spec.operator_id == "OMIT_ORDERED_STEP":
                result = provisioning._apply_authz_ddl(
                    connection,
                    REPOSITORY_ROOT,
                    faults=provisioning._ProvisioningFaults(
                        skip_membership_revoke=True
                    ),
                )
            elif spec.operator_id == "REORDER_ORDERED_STEPS":
                original = provisioning._ordered_steps

                def reordered(
                    asset: dict[str, object],
                ) -> tuple[provisioning._ProvisioningStep, ...]:
                    """宣言された 2 step の相対順だけを反転する。"""
                    steps = list(original(asset))
                    target_ids = spec.target_element_ids
                    selected = [step for step in steps if step.step_id in target_ids]
                    if len(selected) != len(target_ids):
                        raise MutationContractError(
                            f"{spec.mutant_id}: 順序反転 step を導出できない"
                        )
                    indices = sorted(
                        index
                        for index, step in enumerate(steps)
                        if step.step_id in target_ids
                    )
                    for index, step in zip(indices, reversed(selected), strict=True):
                        steps[index] = step
                    return tuple(steps)

                with patch.object(provisioning, "_ordered_steps", reordered):
                    result = provisioning.apply_authz_ddl(
                        connection,
                        REPOSITORY_ROOT,
                    )
            else:
                result = provisioning.apply_authz_ddl(connection, REPOSITORY_ROOT)
    except provisioning.ProvisioningError as error:
        return (
            ApplicationObservation(
                applied=False,
                sqlstate=_sqlstate(error),
            ),
            None,
        )
    return ApplicationObservation.success(), result


def _function_identity(
    admin: psycopg.Connection[Any], schema_id: str, function_id: str
) -> str:
    """ALTER/GRANT 用の一意な regprocedure 表現をカタログから得る。"""
    with admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.oid::pg_catalog.regprocedure::text
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = %s
              AND routine.proname = %s
              AND routine.prokind = 'f'
            ORDER BY routine.oid
            """,
            (schema_id, function_id),
        )
        rows = tuple(cursor.fetchall())
    admin.rollback()
    if len(rows) != 1 or not isinstance(rows[0][0], str):
        raise MutationContractError(f"関数 identity が一意でない: {function_id}")
    identity = rows[0][0]
    if _FUNCTION_IDENTITY_RE.fullmatch(identity) is None:
        raise MutationContractError(f"関数 identity の構文が不正: {identity}")
    return identity


def _parse_colon_target(target: str, part_count: int) -> tuple[str, ...]:
    """Colon 区切りの target ID を閉じた個数で分解する。"""
    parts = tuple(target.split(":"))
    if len(parts) != part_count or any(not part for part in parts):
        raise MutationContractError(f"target ID の構文が不正: {target}")
    return parts


def _single_target(spec: MutantSpec) -> str:
    """単一 target を要求して返す。"""
    if len(spec.target_element_ids) != 1:
        raise MutationContractError(f"{spec.mutant_id}: 単一 target が必要")
    return next(iter(spec.target_element_ids))


def _safe_identifier(value: str, label: str) -> str:
    """資産由来 ID が PostgreSQL 識別子語彙か確認する。"""
    if _SAFE_IDENTIFIER_RE.fullmatch(value) is None:
        raise MutationContractError(f"{label}がSQL識別子でない: {value}")
    return value


def _function_statement(
    statements: tuple[DDLStatement, ...], function_id: str
) -> DDLStatement:
    """生成済み DDL から対象関数文を一意に返す。"""
    return _only(
        (
            statement
            for statement in statements
            if statement.element_type == "function"
            and statement.element_id == function_id
        ),
        f"function statement {function_id}",
    )


def _runtime_route_kind(spec: MutantSpec) -> str:
    """Claim の runtime target と route 資産から probe 種別を導出する。"""
    claim_map = _read_json_object(CLAIM_MUTANT_MAP_PATH)
    claim_rows = _object_rows(claim_map.get("claims"), "claim-mutant-map.claims")
    route_registry = _read_json_object(ROUTE_REGISTRY_PATH)
    route_rows = _object_rows(route_registry.get("routes"), "route-registry.routes")
    route_by_id = {_text(row.get("route_id"), "route_id"): row for row in route_rows}
    route_kinds: set[str] = set()
    for claim_id in spec.claim_ids:
        claim = _only(
            (row for row in claim_rows if row.get("claim_id") == claim_id),
            f"mutation claim {claim_id}",
        )
        runtime_target = claim.get("runtime_target")
        if not isinstance(runtime_target, dict):
            raise MutationContractError(f"{claim_id}: runtime_target がない")
        target_ids = runtime_target.get("target_ids")
        if not isinstance(target_ids, list) or not all(
            isinstance(item, str) for item in target_ids
        ):
            raise MutationContractError(f"{claim_id}: runtime target IDs が不正")
        for route_id in target_ids:
            route = route_by_id.get(route_id)
            if route is None:
                raise MutationContractError(f"未知のruntime route: {route_id}")
            route_kind = _text(route.get("route_kind"), f"{route_id}.route_kind")
            if route_kind == "legacy_route":
                route_class = _text(route.get("route_class"), f"{route_id}.route_class")
                route_kind = (
                    "shared_data" if route_class.startswith("shared_") else route_kind
                )
            route_kinds.add(route_kind)
    if len(route_kinds) != 1:
        raise MutationContractError(
            f"{spec.mutant_id}: runtime route kind が一意でない: {route_kinds}"
        )
    return next(iter(route_kinds))


def _claim_function_class(spec: MutantSpec) -> str:
    """Route kind から既存 probe 関数 class を一意に選ぶ。"""
    route_kind = _runtime_route_kind(spec)
    class_by_route_kind = {
        "shared_data": "shared_read",
        "control_read": "control_read",
        "management_operation": "representative_management_operation",
    }
    try:
        return class_by_route_kind[route_kind]
    except KeyError as error:
        raise MutationContractError(
            f"{spec.mutant_id}: probe 関数へ写像できないroute kind: {route_kind}"
        ) from error


def _mutate_claim_function(
    context: _RuntimeContext,
    spec: MutantSpec,
) -> None:
    """Route 種別に対応する実関数の認可条件だけを弱める。"""
    function_class = _claim_function_class(spec)
    function = _asset_function(context.asset, function_class=function_class)
    function_id = _text(function.get("function_id"), "function.function_id")
    statement = _function_statement(context.statements, function_id)
    source = provisioning._split_function_sql(statement).create_or_replace
    if function_class == "shared_read":
        from ..test_authz_runtime_positive import _POSITIVE_CASES

        case = _POSITIVE_CASES[0]
        grants = ", ".join(f"'{value}'" for value in case.required_grant_kinds)
        sentinel = _mutation_granularity(spec)
        anchor = "        VALUES\n"
        replacement = (
            anchor
            + "            (\n"
            + f"                '{sentinel}'::TEXT,\n"
            + f"                '{case.resource_kind}'::TEXT,\n"
            + f"                ARRAY[{grants}]::TEXT[]\n"
            + "            ),\n"
        )
        source, replacements = (
            source.replace(anchor, replacement, 1),
            source.count(anchor),
        )
        if replacements < 1:
            raise MutationContractError("shared authorization matrix を変更できない")
    elif function_class == "control_read":
        anchor = "NOT control_access_matrix.admin_required"
        source, replacements = re.subn(
            re.escape(anchor),
            f"TRUE OR {anchor}",
            source,
            count=1,
        )
        if replacements != 1:
            raise MutationContractError("control admin 条件を変更できない")
    else:
        anchor = "caller_membership.group_role = 'admin'"
        source, replacements = re.subn(
            re.escape(anchor),
            f"(TRUE OR {anchor})",
            source,
            count=1,
        )
        if replacements != 1:
            raise MutationContractError("management role 条件を変更できない")
    with context.admin.cursor() as cursor:
        cursor.execute(source.encode("utf-8"))
    context.admin.commit()


def _mutation_granularity(spec: MutantSpec) -> str:
    """Mutant ID から衝突しない probe 粒度を作る。"""
    digest = hashlib.sha256(spec.mutant_id.encode()).hexdigest()[:16]
    return f"mutation_{digest}"


def _grant_table_targets(context: _RuntimeContext, spec: MutantSpec) -> None:
    """TABLE-PRIVILEGE target 群から表・ロール・権限を導出して付与する。"""
    by_pair: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for target in spec.target_element_ids:
        prefix, table_id, role_id, privilege_id = _parse_colon_target(target, 4)
        if f"{prefix}:" != _TABLE_PRIVILEGE_PREFIX:
            raise MutationContractError(f"表権限targetでない: {target}")
        _safe_identifier(table_id, "table_id")
        _safe_identifier(role_id, "role_id")
        by_pair[(table_id, role_id)].append(privilege_id)
    with context.admin.cursor() as cursor:
        for (table_id, role_id), privilege_ids in by_pair.items():
            table = _asset_table(context.asset, table_id)
            schema_id = _text(table.get("schema_id"), f"{table_id}.schema_id")
            cursor.execute(
                sql.SQL("GRANT {} ON TABLE {}.{} TO {}").format(
                    sql.SQL(", ").join(
                        sql.SQL(cast(LiteralString, value)) for value in privilege_ids
                    ),
                    sql.Identifier(schema_id),
                    sql.Identifier(table_id),
                    sql.Identifier(role_id),
                )
            )
    context.admin.commit()


def _apply_configuration_mutation(
    context: _RuntimeContext,
    spec: MutantSpec,
) -> None:
    """Operator と target grammar から構成 mutation を実 DB へ適用する。"""
    operator_id = spec.operator_id
    if operator_id in {
        "grant_management_caller_table_privilege",
        "grant_app_role_control_table_dml",
    }:
        _grant_table_targets(context, spec)
        return
    if operator_id == "add_role_membership":
        member_id, role_id = _parse_colon_target(
            _single_target(spec).replace("->", ":"), 2
        )
        with context.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(role_id), sql.Identifier(member_id)
                )
            )
        context.admin.commit()
        return
    if operator_id == "remove_role_attribute":
        role_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        if attribute_id != "bypass_rls":
            raise MutationContractError(f"未対応のrole属性: {attribute_id}")
        with context.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE {} NOBYPASSRLS").format(sql.Identifier(role_id))
            )
        context.admin.commit()
        return
    if operator_id == "disable_force_rls":
        table_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        if attribute_id != "force_rls":
            raise MutationContractError(f"FORCE RLS targetでない: {attribute_id}")
        table = _asset_table(context.asset, table_id)
        schema_id = _text(table.get("schema_id"), f"{table_id}.schema_id")
        with context.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER TABLE {}.{} NO FORCE ROW LEVEL SECURITY").format(
                    sql.Identifier(schema_id), sql.Identifier(table_id)
                )
            )
        context.admin.commit()
        return
    if operator_id == "grant_schema_create":
        schema_id, role_id, privilege_id = _parse_colon_target(_single_target(spec), 3)
        with context.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("GRANT {} ON SCHEMA {} TO {}").format(
                    sql.SQL(cast(LiteralString, privilege_id)),
                    sql.Identifier(schema_id),
                    sql.Identifier(role_id),
                )
            )
        context.admin.commit()
        return
    if operator_id == "grant_database_temporary":
        object_kind, role_id, privilege_id = _parse_colon_target(
            _single_target(spec), 3
        )
        if object_kind != "database":
            raise MutationContractError(f"database targetでない: {object_kind}")
        with context.admin.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            row = cursor.fetchone()
            if row is None:
                raise MutationContractError("database IDを取得できない")
            cursor.execute(
                sql.SQL("GRANT {} ON DATABASE {} TO {}").format(
                    sql.SQL(cast(LiteralString, privilege_id)),
                    sql.Identifier(str(row[0])),
                    sql.Identifier(role_id),
                )
            )
        context.admin.commit()
        return
    if operator_id == "grant_function_execute":
        function_id, role_id, privilege_id = _parse_colon_target(
            _single_target(spec), 3
        )
        function = _asset_function(context.asset, function_id=function_id)
        schema_id = _text(function.get("schema_id"), f"{function_id}.schema_id")
        identity = _function_identity(context.admin, schema_id, function_id)
        with context.admin.cursor() as cursor:
            statement = cast(
                LiteralString,
                f"GRANT {privilege_id} ON FUNCTION {identity} TO {{}}",
            )
            cursor.execute(sql.SQL(statement).format(sql.Identifier(role_id)))
        context.admin.commit()
        return
    if operator_id == "omit_acl_revocation":
        function_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        if attribute_id != "public_execute":
            raise MutationContractError(f"PUBLIC EXECUTE targetでない: {attribute_id}")
        function = _asset_function(context.asset, function_id=function_id)
        schema_id = _text(function.get("schema_id"), f"{function_id}.schema_id")
        identity = _function_identity(context.admin, schema_id, function_id)
        with context.admin.cursor() as cursor:
            cursor.execute(
                cast(
                    LiteralString,
                    f"GRANT EXECUTE ON FUNCTION {identity} TO PUBLIC",
                )
            )
        context.admin.commit()
        return
    if operator_id == "remove_search_path_element":
        function_id, attribute_id, removed_id = _parse_colon_target(
            _single_target(spec), 3
        )
        if attribute_id != "search_path":
            raise MutationContractError(f"search_path targetでない: {attribute_id}")
        function = _asset_function(context.asset, function_id=function_id)
        schema_id = _text(function.get("schema_id"), f"{function_id}.schema_id")
        raw_path = function.get("search_path")
        if not isinstance(raw_path, list) or not all(
            isinstance(value, str) for value in raw_path
        ):
            raise MutationContractError(f"{function_id}.search_pathが不正")
        new_path = tuple(value for value in raw_path if value != removed_id)
        if len(new_path) + 1 != len(raw_path):
            raise MutationContractError(
                f"search_path要素を一意に除けない: {removed_id}"
            )
        identity = _function_identity(context.admin, schema_id, function_id)
        with context.admin.cursor() as cursor:
            statement = cast(
                LiteralString,
                f"ALTER FUNCTION {identity} SET search_path TO {{}}",
            )
            cursor.execute(
                sql.SQL(statement).format(
                    sql.SQL(", ").join(sql.Identifier(value) for value in new_path)
                )
            )
        context.admin.commit()
        return
    if operator_id == "replace_owner":
        function_id, attribute_id = _parse_colon_target(_single_target(spec), 2)
        if attribute_id != "owner_role_id":
            raise MutationContractError(f"owner targetでない: {attribute_id}")
        function = _asset_function(context.asset, function_id=function_id)
        schema_id = _text(function.get("schema_id"), f"{function_id}.schema_id")
        replacement_owner = _asset_role_id(context.asset, "tested_caller")
        identity = _function_identity(context.admin, schema_id, function_id)
        with context.admin.cursor() as cursor:
            statement = cast(
                LiteralString,
                f"ALTER FUNCTION {identity} OWNER TO {{}}",
            )
            cursor.execute(sql.SQL(statement).format(sql.Identifier(replacement_owner)))
        context.admin.commit()
        return
    if operator_id == "remove_policy_predicate":
        policy_prefix, table_id, policy_name, attribute_id = _parse_colon_target(
            _single_target(spec), 4
        )
        if policy_prefix != "POLICY" or attribute_id != "with_check":
            raise MutationContractError("WITH CHECK targetでない")
        table = _asset_table(context.asset, table_id)
        schema_id = _text(table.get("schema_id"), f"{table_id}.schema_id")
        with context.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER POLICY {} ON {}.{} WITH CHECK (TRUE)").format(
                    sql.Identifier(policy_name),
                    sql.Identifier(schema_id),
                    sql.Identifier(table_id),
                )
            )
        context.admin.commit()
        return
    if operator_id == "add_permissive_policy":
        table_id, predicate_id = _parse_colon_target(_single_target(spec), 2)
        if predicate_id != "USING_TRUE":
            raise MutationContractError(
                f"permissive policy targetでない: {predicate_id}"
            )
        table = _asset_table(context.asset, table_id)
        schema_id = _text(table.get("schema_id"), f"{table_id}.schema_id")
        role_id = _asset_role_id(context.asset, "tested_caller")
        policy_id = (
            f"mutation_{hashlib.sha256(spec.mutant_id.encode()).hexdigest()[:12]}"
        )
        with context.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE POLICY {} ON {}.{} AS PERMISSIVE FOR ALL TO {} "
                    "USING (TRUE) WITH CHECK (TRUE)"
                ).format(
                    sql.Identifier(policy_id),
                    sql.Identifier(schema_id),
                    sql.Identifier(table_id),
                    sql.Identifier(role_id),
                )
            )
        context.admin.commit()
        return
    if operator_id == "split_authorization_and_side_effect":
        # 分割はカタログ属性ではなく、後段の runtime 呼び出し順として適用する。
        return
    raise MutationContractError(f"未対応のDB mutation operator: {operator_id}")


def _offset_positive_fixture(fixture: Any, offset: int) -> Any:
    """Step 7 fixture の意味を保ったまま数値 ID だけを平行移動する。"""
    business_rows = tuple(
        replace(row, tenant_id=row.tenant_id + offset) for row in fixture.business_rows
    )
    invocations = tuple(
        replace(
            invocation,
            group_id=invocation.group_id + offset,
            target_tenant_ids=tuple(
                tenant_id + offset for tenant_id in invocation.target_tenant_ids
            ),
            expected_rows=frozenset(
                replace(row, tenant_id=row.tenant_id + offset)
                for row in invocation.expected_rows
            ),
        )
        for invocation in fixture.invocations
    )
    return replace(
        fixture,
        requester_tenant_id=fixture.requester_tenant_id + offset,
        groups=tuple(
            (group_id + offset, status) for group_id, status in fixture.groups
        ),
        memberships=tuple(
            (group_id + offset, tenant_id + offset, status, role)
            for group_id, tenant_id, status, role in fixture.memberships
        ),
        grants=tuple(
            (group_id + offset, tenant_id + offset, kind, enabled)
            for group_id, tenant_id, kind, enabled in fixture.grants
        ),
        business_rows=business_rows,
        invocations=invocations,
    )


def _insert_positive_fixture(context: _RuntimeContext, fixture: Any) -> None:
    """Step 7 の単一実装を通じて正例 fixture を投入する。"""
    from ..test_authz_runtime_positive import _insert_runtime_fixture

    _insert_runtime_fixture(context.catalog, fixture)


def _app_connection(context: _RuntimeContext) -> psycopg.Connection[Any]:
    """資産の tested caller 自身で認証した接続を返す。"""
    role_id = _asset_role_id(context.asset, "tested_caller")
    return context.role_connections[role_id]


def _role_connection(
    context: _RuntimeContext, role_kind: str
) -> psycopg.Connection[Any]:
    """Role kind に対応する実認証接続を返す。"""
    return context.role_connections[_asset_role_id(context.asset, role_kind)]


def _assert_shared_denial(
    context: _RuntimeContext,
    *,
    granularity: str | None = None,
    offset: int = 100_000,
) -> None:
    """Step 7 fixture の拒否 invocation が空集合のままか検査する。"""
    from ..test_authz_runtime_positive import (
        _POSITIVE_CASES,
        _fetch_authorized_shared_rows,
        _runtime_fixture_definition,
    )

    fixture = _offset_positive_fixture(
        _runtime_fixture_definition(_POSITIVE_CASES[0]), offset
    )
    if granularity is not None:
        fixture = replace(fixture, granularity=granularity)
    _insert_positive_fixture(context, fixture)
    invocation = next(value for value in fixture.invocations if not value.expected_rows)
    connection = _app_connection(context)
    try:
        rows = _fetch_authorized_shared_rows(connection, fixture, invocation)
        assert rows == frozenset(), (
            f"本来拒否される共有行へ到達した: {sorted(map(str, rows))}"
        )
    finally:
        connection.rollback()


def _assert_mutated_granularity_denied(
    context: _RuntimeContext, spec: MutantSpec
) -> None:
    """資産外 granularity による越境取得を拒否する期待を検査する。"""
    from ..test_authz_runtime_positive import (
        _POSITIVE_CASES,
        _fetch_authorized_shared_rows,
        _runtime_fixture_definition,
    )

    fixture = _offset_positive_fixture(
        _runtime_fixture_definition(_POSITIVE_CASES[0]), 120_000
    )
    fixture = replace(fixture, granularity=_mutation_granularity(spec))
    _insert_positive_fixture(context, fixture)
    invocation = next(value for value in fixture.invocations if value.expected_rows)
    connection = _app_connection(context)
    try:
        rows = _fetch_authorized_shared_rows(connection, fixture, invocation)
        assert rows == frozenset(), "資産外 granularity が認可されてしまった"
    finally:
        connection.rollback()


def _assert_control_admin_denial(context: _RuntimeContext) -> None:
    """一般 member が admin 詳細へ到達しないことを検査する。"""
    requester_id = 130_001
    other_tenant_id = 130_002
    group_id = 130_100
    with context.admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO probe_data.probe_groups (group_id, status) VALUES (%s, %s)",
            (group_id, "active"),
        )
        cursor.executemany(
            """
            INSERT INTO probe_data.probe_memberships
                (group_id, tenant_id, status, group_role)
            VALUES (%s, %s, %s, %s)
            """,
            (
                (group_id, requester_id, "active", "member"),
                (group_id, other_tenant_id, "active", "member"),
            ),
        )
    context.admin.commit()
    connection = _app_connection(context)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                (str(requester_id),),
            )
            cursor.execute(
                """
                SELECT *
                FROM authz_private.read_control_resources(%s, %s, %s, %s)
                """,
                (group_id, "membership_admin_details", 100, 0),
            )
            rows = tuple(cursor.fetchall())
        assert rows == (), "一般memberがadmin詳細へ到達した"
    finally:
        connection.rollback()


def _management_helpers() -> tuple[Any, ...]:
    """Step 10 の管理 probe 単一実装を遅延 import する。"""
    from ..test_authz_management_probe import (
        _BASELINE_FIXTURE,
        _effect_count,
        _insert_management_fixture,
        _invoke_management_function,
        _management_contract,
        _without_admin_role,
    )

    return (
        _BASELINE_FIXTURE,
        _effect_count,
        _insert_management_fixture,
        _invoke_management_function,
        _management_contract,
        _without_admin_role,
    )


def _assert_management_role_denial(context: _RuntimeContext) -> None:
    """管理ロール条件を欠く呼び出しに副作用がないことを検査する。"""
    (
        baseline,
        effect_count,
        insert_fixture,
        invoke,
        contract_factory,
        without_admin,
    ) = _management_helpers()
    fixture = without_admin(baseline)
    contract = contract_factory(context.asset)
    insert_fixture(context.catalog, fixture)
    connection = _role_connection(context, "management_caller")
    before = effect_count(context.catalog, contract)
    try:
        rows = invoke(connection, contract, fixture)
        connection.commit()
    finally:
        connection.rollback()
    after = effect_count(context.catalog, contract)
    assert rows == () and after == before, "管理ロール条件なしで副作用が発生した"


def _insert_direct_business_row(context: _RuntimeContext) -> tuple[int, int]:
    """RLS 越境観測用に異なる 2 tenant と業務行を投入する。"""
    requester_id = 140_001
    target_id = 140_002
    with context.admin.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO probe_data.probe_business_rows
                (tenant_id, resource_kind, ownership_kind, payload)
            VALUES (%s, %s, %s, %s::JSONB)
            """,
            (target_id, "team_statistics", "self", '{"mutation": true}'),
        )
    context.admin.commit()
    return requester_id, target_id


def _assert_direct_business_row_denied(
    context: _RuntimeContext, role_kind: str
) -> None:
    """指定実ロールの直接 SELECT が他 tenant 行へ届かないことを検査する。"""
    requester_id, target_id = _insert_direct_business_row(context)
    connection = _role_connection(context, role_kind)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                (str(requester_id),),
            )
            cursor.execute(
                """
                SELECT tenant_id
                FROM probe_data.probe_business_rows
                WHERE tenant_id = %s
                """,
                (target_id,),
            )
            rows = tuple(cursor.fetchall())
        assert rows == (), "直接SELECTで他tenant行へ到達した"
    finally:
        connection.rollback()


def _assert_role_membership_denied(context: _RuntimeContext, spec: MutantSpec) -> None:
    """追加 membership から owner へ切替えて越境できない期待を検査する。"""
    requester_id, target_id = _insert_direct_business_row(context)
    connection = _app_connection(context)
    _member_id, owner_id = _parse_colon_target(
        _single_target(spec).replace("->", ":"), 2
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                (str(requester_id),),
            )
            cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner_id)))
            cursor.execute(
                """
                SELECT tenant_id
                FROM probe_data.probe_business_rows
                WHERE tenant_id = %s
                """,
                (target_id,),
            )
            rows = tuple(cursor.fetchall())
        assert rows == (), "追加membershipからBYPASSRLS ownerへ到達した"
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
        connection.commit()


def _assert_write_check_denied(context: _RuntimeContext) -> None:
    """App role が他 tenant 行を直接 INSERT できないことを検査する。"""
    connection = _app_connection(context)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                ("150001",),
            )
            try:
                cursor.execute(
                    """
                    INSERT INTO probe_data.probe_business_rows
                        (tenant_id, resource_kind, ownership_kind, payload)
                    VALUES (%s, %s, %s, %s::JSONB)
                    """,
                    (150_002, "team_statistics", "self", '{"mutation": true}'),
                )
            except psycopg.errors.InsufficientPrivilege:
                return
        raise AssertionError("WITH CHECKなしで他tenant行をINSERTできた")
    finally:
        connection.rollback()


def _grant_schema_usage(context: _RuntimeContext, schema_id: str, role_id: str) -> None:
    """別の拒否要因を除く runtime fixture として schema USAGE を与える。"""
    with context.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema_id), sql.Identifier(role_id)
            )
        )
    context.admin.commit()


def _assert_public_execute_denied(context: _RuntimeContext) -> None:
    """PUBLIC 主体が共有関数を実行できない期待を実呼び出しで検査する。"""
    from ..test_authz_runtime_positive import (
        _POSITIVE_CASES,
        _fetch_authorized_shared_rows,
        _runtime_fixture_definition,
    )

    fixture = _offset_positive_fixture(
        _runtime_fixture_definition(_POSITIVE_CASES[0]), 160_000
    )
    _insert_positive_fixture(context, fixture)
    invocation = next(value for value in fixture.invocations if value.expected_rows)
    function = _asset_function(context.asset, function_class="shared_read")
    schema_id = _text(function.get("schema_id"), "shared function schema")
    outsider_id = _asset_role_id(context.asset, "negative_test_caller")
    _grant_schema_usage(context, schema_id, outsider_id)
    connection = _role_connection(context, "negative_test_caller")
    try:
        try:
            _fetch_authorized_shared_rows(connection, fixture, invocation)
        except psycopg.errors.InsufficientPrivilege:
            return
        raise AssertionError("PUBLIC経由で共有関数を実行できた")
    finally:
        connection.rollback()


def _assert_management_function_execute_denied(context: _RuntimeContext) -> None:
    """App role に管理関数の実行経路がない期待を検査する。"""
    (
        baseline,
        effect_count,
        insert_fixture,
        invoke,
        contract_factory,
        _without_admin,
    ) = _management_helpers()
    contract = contract_factory(context.asset)
    insert_fixture(context.catalog, baseline)
    app_role_id = _asset_role_id(context.asset, "tested_caller")
    _grant_schema_usage(context, contract.schema_id, app_role_id)
    before = effect_count(context.catalog, contract)
    connection = _app_connection(context)
    try:
        try:
            rows = invoke(connection, contract, baseline)
            connection.commit()
        except psycopg.errors.InsufficientPrivilege:
            return
    finally:
        connection.rollback()
    after = effect_count(context.catalog, contract)
    assert rows == () and after == before, "App roleが管理関数を実行できた"


def _table_privilege_target_rows(
    spec: MutantSpec,
) -> tuple[tuple[str, str, str], ...]:
    """表権限 target を table・role・privilege の組へ変換する。"""
    rows: list[tuple[str, str, str]] = []
    for target in sorted(spec.target_element_ids):
        prefix, table_id, role_id, privilege_id = _parse_colon_target(target, 4)
        if prefix != _TABLE_PRIVILEGE_PREFIX.removesuffix(":"):
            raise MutationContractError(f"表権限targetでない: {target}")
        rows.append((table_id, role_id, privilege_id))
    return tuple(rows)


def _assert_management_table_privilege_denied(
    context: _RuntimeContext, spec: MutantSpec
) -> None:
    """Step 11 の実操作・カタログ観測で直接表権限の不在を検査する。"""
    from ..test_authz_table_privileges import (
        _assert_direct_operation_is_table_privilege_denied,
        _grant_schema_usage_for_table_probe,
        _has_table_privilege,
        _table_privilege_contract,
    )

    contract = _table_privilege_contract(context.asset)
    rows = _table_privilege_target_rows(spec)
    if len(rows) != 1:
        raise MutationContractError("管理表権限mutationは単一権限が必要")
    table_id, role_id, privilege_id = rows[0]
    if table_id != contract.table_id or role_id != contract.calling_role_id:
        raise MutationContractError("管理表権限targetがStep 11契約と一致しない")
    case = next(value for value in contract.cases if value.privilege_id == privilege_id)
    if case.verification_method == "execution_and_catalog":
        _grant_schema_usage_for_table_probe(context.catalog, contract)
        connection = context.role_connections[role_id]
        _assert_direct_operation_is_table_privilege_denied(connection, case, contract)
        return
    assert not _has_table_privilege(context.admin, role_id, contract, privilege_id), (
        f"管理呼び出しロールへ{privilege_id}が付与された"
    )


def _insert_control_dml_fixture(
    context: _RuntimeContext, table_id: str
) -> tuple[int, int]:
    """対象 control 表へ app role から操作可能な基準行を投入する。"""
    requester_id = 170_001
    group_id = 170_100
    with context.admin.cursor() as cursor:
        if table_id == "probe_groups":
            cursor.execute(
                """
                INSERT INTO probe_data.probe_memberships
                    (group_id, tenant_id, status, group_role)
                VALUES (%s, %s, %s, %s)
                """,
                (group_id, requester_id, "active", "member"),
            )
            cursor.execute(
                "INSERT INTO probe_data.probe_groups "
                "(group_id, status) VALUES (%s, %s)",
                (group_id, "active"),
            )
        elif table_id == "probe_memberships":
            cursor.execute(
                """
                INSERT INTO probe_data.probe_memberships
                    (group_id, tenant_id, status, group_role)
                VALUES (%s, %s, %s, %s)
                """,
                (group_id, requester_id, "active", "member"),
            )
        elif table_id == "probe_grants":
            cursor.execute(
                """
                INSERT INTO probe_data.probe_grants
                    (group_id, tenant_id, grant_kind, enabled)
                VALUES (%s, %s, %s, %s)
                """,
                (group_id, requester_id, "performance", True),
            )
        elif table_id == "probe_invitations":
            cursor.execute(
                """
                INSERT INTO probe_data.probe_invitations
                    (group_id, invited_tenant_id, status)
                VALUES (%s, %s, %s)
                """,
                (group_id, requester_id, "active"),
            )
        else:
            raise MutationContractError(f"control DML対象外の表: {table_id}")
    context.admin.commit()
    return requester_id, group_id


def _control_dml_statement(
    table_id: str,
    privilege_id: str,
    requester_id: int,
    group_id: int,
    update_column_id: str,
) -> tuple[bytes, tuple[object, ...]]:
    """Control 表と権限から rollback 可能な実 DML を作る。"""
    if privilege_id == "INSERT":
        if table_id == "probe_groups":
            return (
                b"INSERT INTO probe_data.probe_groups "
                b"(group_id, status) VALUES (%s, %s)",
                (group_id + 1, "active"),
            )
        if table_id == "probe_memberships":
            return (
                b"INSERT INTO probe_data.probe_memberships "
                b"(group_id, tenant_id, status, group_role) "
                b"VALUES (%s, %s, %s, %s)",
                (group_id + 1, requester_id, "active", "member"),
            )
        if table_id == "probe_grants":
            return (
                b"INSERT INTO probe_data.probe_grants "
                b"(group_id, tenant_id, grant_kind, enabled) "
                b"VALUES (%s, %s, %s, %s)",
                (group_id + 1, requester_id, "performance", True),
            )
        return (
            b"INSERT INTO probe_data.probe_invitations "
            b"(group_id, invited_tenant_id, status) VALUES (%s, %s, %s)",
            (group_id + 1, requester_id, "active"),
        )
    if privilege_id == "UPDATE":
        return (
            (
                f"UPDATE probe_data.{table_id} "
                f"SET {update_column_id} = {update_column_id}"
            ).encode(),
            (),
        )
    if privilege_id == "DELETE":
        return (f"DELETE FROM probe_data.{table_id}".encode(), ())
    raise MutationContractError(f"control DML権限でない: {privilege_id}")


def _assert_app_control_dml_denied(context: _RuntimeContext, spec: MutantSpec) -> None:
    """App role の control 表 DML 3 種がすべて拒否される期待を検査する。"""
    target_rows = _table_privilege_target_rows(spec)
    table_ids = {table_id for table_id, _role_id, _privilege_id in target_rows}
    role_ids = {role_id for _table_id, role_id, _privilege_id in target_rows}
    if len(table_ids) != 1 or role_ids != {
        _asset_role_id(context.asset, "tested_caller")
    }:
        raise MutationContractError("App control DML target が一意でない")
    table_id = next(iter(table_ids))
    table = _asset_table(context.asset, table_id)
    row_shape_ids = table.get("row_shape_ids")
    if not isinstance(row_shape_ids, list) or not all(
        isinstance(value, str) for value in row_shape_ids
    ):
        raise MutationContractError(f"{table_id}.row_shape_idsが不正")
    update_column_id = _safe_identifier(row_shape_ids[-1], "update column")
    requester_id, group_id = _insert_control_dml_fixture(context, table_id)
    connection = _app_connection(context)
    succeeded: list[str] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                (str(requester_id),),
            )
            for _table_id, _role_id, privilege_id in target_rows:
                statement, parameters = _control_dml_statement(
                    table_id,
                    privilege_id,
                    requester_id,
                    group_id,
                    update_column_id,
                )
                cursor.execute("SAVEPOINT mutation_control_dml")
                try:
                    cursor.execute(statement, parameters)
                except psycopg.errors.InsufficientPrivilege:
                    cursor.execute("ROLLBACK TO SAVEPOINT mutation_control_dml")
                else:
                    succeeded.append(privilege_id)
                    cursor.execute("ROLLBACK TO SAVEPOINT mutation_control_dml")
                cursor.execute("RELEASE SAVEPOINT mutation_control_dml")
        assert succeeded == [], f"App roleのcontrol DMLが成功した: {succeeded}"
    finally:
        connection.rollback()


def _assert_added_capability_does_not_cross_tenant(
    context: _RuntimeContext, spec: MutantSpec
) -> None:
    """追加 CREATE/TEMP 権限を実行後も共有越境が閉じることを検査する。"""
    connection = _app_connection(context)
    try:
        with connection.cursor() as cursor:
            if spec.operator_id == "grant_schema_create":
                schema_id, _role_id, _privilege_id = _parse_colon_target(
                    _single_target(spec), 3
                )
                probe_id = f"mutation_{secrets.token_hex(6)}"
                cursor.execute(
                    sql.SQL("CREATE TABLE {}.{} (id BIGINT)").format(
                        sql.Identifier(schema_id), sql.Identifier(probe_id)
                    )
                )
            elif spec.operator_id == "grant_database_temporary":
                probe_id = f"mutation_{secrets.token_hex(6)}"
                cursor.execute(
                    sql.SQL("CREATE TEMPORARY TABLE {} (id BIGINT)").format(
                        sql.Identifier(probe_id)
                    )
                )
            else:
                raise MutationContractError("追加capability operatorが不正")
        connection.rollback()
    finally:
        connection.rollback()
    _assert_shared_denial(context, offset=180_000)


def _assert_split_management_denied(context: _RuntimeContext) -> None:
    """認可と副作用を分割した経路が拒否後に行を残さない期待を検査する。"""
    (
        baseline,
        effect_count,
        insert_fixture,
        invoke,
        contract_factory,
        without_admin,
    ) = _management_helpers()
    fixture = without_admin(baseline)
    contract = contract_factory(context.asset)
    insert_fixture(context.catalog, fixture)
    connection = _role_connection(context, "management_caller")
    before = effect_count(context.catalog, contract)
    rows = invoke(connection, contract, fixture)
    connection.commit()
    assert rows == (), "分割前提の拒否呼び出しが成功した"
    with context.admin.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO probe_data.probe_management_effects
                (group_id, tenant_id, effect_kind)
            VALUES (%s, %s, %s)
            """,
            (
                fixture.invocation_group_id,
                fixture.invocation_target_tenant_id,
                fixture.invocation_effect_kind,
            ),
        )
    context.admin.commit()
    after = effect_count(context.catalog, contract)
    assert after == before, "分割された副作用が認可失敗後に残った"


def _assert_provisioner_membership_closed(context: _RuntimeContext) -> None:
    """Step 5 後に外部 provisioner の owner 到達が残らないことを検査する。"""
    owner_ids = {
        _text(row.get("owner_role_id"), "owner_role_id")
        for key in ("schemas", "tables", "functions")
        for row in _object_rows(context.asset.get(key), f"ddl-elements.{key}")
    }
    observations: list[bool] = []
    with context.admin.cursor() as cursor:
        for owner_id in sorted(owner_ids):
            cursor.execute(
                "SELECT pg_catalog.pg_has_role(%s, %s, 'SET')",
                (context.provisioner_id, owner_id),
            )
            row = cursor.fetchone()
            observations.append(bool(row and row[0]))
    context.admin.rollback()
    assert not any(observations), "provisionerのowner SET到達が残った"


def _run_positive_cases(context: _RuntimeContext) -> None:
    """資産由来の全 allow セルを exact-row で再実行する。"""
    from ..test_authz_runtime_positive import (
        _POSITIVE_CASES,
        _fetch_authorized_shared_rows,
        _runtime_fixture_definition,
    )

    connection = _app_connection(context)
    for index, case in enumerate(_POSITIVE_CASES, start=1):
        fixture = _offset_positive_fixture(
            _runtime_fixture_definition(case),
            300_000 + index * 10_000,
        )
        _insert_positive_fixture(context, fixture)
        try:
            for invocation in fixture.invocations:
                actual = _fetch_authorized_shared_rows(connection, fixture, invocation)
                assert actual == invocation.expected_rows, (
                    f"{case.cell_id}/{invocation.invocation_id}"
                )
        finally:
            connection.rollback()


def _observe_assertion(call: Callable[[], None]) -> ChannelObservation:
    """Assertion 失敗と成功を kill/pass の生観測へ変換する。"""
    try:
        call()
    except (AssertionError, Failed, pytest.fail.Exception):
        return ChannelObservation.expected_assertion_failure()
    return ChannelObservation.passed()


def _observe_availability(context: _RuntimeContext) -> ChannelObservation:
    """共有関数の正例が利用不能になったことを可用性失敗として観測する。"""
    from ..test_authz_runtime_positive import (
        _POSITIVE_CASES,
        _fetch_authorized_shared_rows,
        _runtime_fixture_definition,
    )

    fixture = _offset_positive_fixture(
        _runtime_fixture_definition(_POSITIVE_CASES[0]), 250_000
    )
    _insert_positive_fixture(context, fixture)
    invocation = next(value for value in fixture.invocations if value.expected_rows)
    connection = _app_connection(context)
    try:
        try:
            rows = _fetch_authorized_shared_rows(connection, fixture, invocation)
        except psycopg.Error:
            return ChannelObservation.availability_failure()
        if rows != invocation.expected_rows:
            return ChannelObservation.availability_failure()
        return ChannelObservation.passed()
    finally:
        connection.rollback()


def _runtime_probe(
    context: _RuntimeContext,
    spec: MutantSpec,
    blueprint: MutationBlueprint,
) -> None:
    """Operator が破るべき runtime 境界を既存 probe 上で検査する。"""
    if blueprint.database_mode == _CLAIM_DECISION_MODE:
        function_class = _claim_function_class(spec)
        if function_class == "shared_read":
            _assert_mutated_granularity_denied(context, spec)
        elif function_class == "control_read":
            _assert_control_admin_denial(context)
        else:
            _assert_management_role_denial(context)
        return

    probes: Mapping[str, Callable[[], None]] = {
        "OMIT_ORDERED_STEP": lambda: _assert_provisioner_membership_closed(context),
        "add_permissive_policy": lambda: _assert_direct_business_row_denied(
            context, "tested_caller"
        ),
        "add_role_membership": lambda: _assert_role_membership_denied(context, spec),
        "disable_force_rls": lambda: _assert_direct_business_row_denied(
            context, "object_owner"
        ),
        "grant_app_role_control_table_dml": lambda: _assert_app_control_dml_denied(
            context, spec
        ),
        "grant_database_temporary": lambda: (
            _assert_added_capability_does_not_cross_tenant(context, spec)
        ),
        "grant_function_execute": lambda: _assert_management_function_execute_denied(
            context
        ),
        "grant_management_caller_table_privilege": lambda: (
            _assert_management_table_privilege_denied(context, spec)
        ),
        "grant_schema_create": lambda: _assert_added_capability_does_not_cross_tenant(
            context, spec
        ),
        "omit_acl_revocation": lambda: _assert_public_execute_denied(context),
        "remove_policy_predicate": lambda: _assert_write_check_denied(context),
        "remove_search_path_element": lambda: _assert_shared_denial(
            context, offset=190_000
        ),
        "replace_owner": lambda: _assert_shared_denial(context, offset=200_000),
        "split_authorization_and_side_effect": lambda: _assert_split_management_denied(
            context
        ),
    }
    try:
        probe = probes[spec.operator_id]
    except KeyError as error:
        raise MutationContractError(
            f"{spec.mutant_id}: runtime probe が未実装: {spec.operator_id}"
        ) from error
    probe()


def _runtime_observation(
    context: _RuntimeContext,
    spec: MutantSpec,
    blueprint: MutationBlueprint,
) -> ChannelObservation:
    """越境チャネルを handoff と実 DB 観測へ機械的に分ける。"""
    if spec.expected_runtime_outcome == "handoff":
        return ChannelObservation.not_run(NotRunReason.HANDOFF)
    if spec.expected_runtime_outcome == "not_run_application_failed":
        return ChannelObservation.passed()
    if spec.expected_runtime_outcome == "availability_failure":
        return _observe_availability(context)
    return _observe_assertion(lambda: _runtime_probe(context, spec, blueprint))


def _positive_observation(
    context: _RuntimeContext,
    spec: MutantSpec,
) -> ChannelObservation:
    """全 allow セルの正例チャネルを runtime と独立に観測する。"""
    if spec.expected_positive_outcome == "handoff":
        return ChannelObservation.not_run(NotRunReason.HANDOFF)
    if spec.expected_positive_outcome == "not_run_application_failed":
        return ChannelObservation.passed()
    return _observe_assertion(lambda: _run_positive_cases(context))


class FullMutationExecutor:
    """全 operator を一時 DB へ適用して三チャネルを実測する executor。"""

    def __init__(
        self,
        catalog: MutationCatalog,
        root: Path = REPOSITORY_ROOT,
    ) -> None:
        """資産・生成 DDL・exact-set 済み operator 実装を保持する。"""
        self.catalog = catalog
        self.root = root.resolve()
        self.implementations = bind_operator_implementations(catalog)
        self.asset = _read_json_object(self.root / "contracts/authz/ddl-elements.json")
        self.statements = generate_authz_ddl(self.root)
        self.execution_records: dict[
            str, tuple[MutationEnvironment, MutationObservation]
        ] = {}

    def _failed_application_observation(
        self,
        spec: MutantSpec,
        environment: MutationEnvironment,
        blueprint: MutationBlueprint,
        application: ApplicationObservation,
        schema_drift: ChannelObservation,
    ) -> MutationObservation:
        """適用失敗後の 2 runtime チャネルを未実行として閉じる。"""
        if application.applied:
            not_run = ChannelObservation.passed()
        else:
            not_run = ChannelObservation.not_run(NotRunReason.APPLICATION_FAILED)
        observation = MutationObservation(
            application=application,
            catalog_delta=CatalogDelta(blueprint.changed_element_ids),
            schema_drift=schema_drift,
            runtime_cross_tenant=not_run,
            runtime_positive_case=not_run,
        )
        self.execution_records[spec.mutant_id] = (environment, observation)
        return observation

    @contextmanager
    def _runtime_context(
        self,
        environment: MutationEnvironment,
        spec: MutantSpec,
        blueprint: MutationBlueprint,
    ) -> Iterator[tuple[_RuntimeContext | None, ApplicationObservation]]:
        """Provisioning と実認証ロール接続を mutation DB 内に構築する。"""
        from ..conftest import (
            DisposablePostgres,
            ProvisionedCatalog,
            _connect_provisioned_authz_login_roles,
        )

        with psycopg.connect(environment.database_dsn) as admin:
            provisioner_dsn, provisioner_id = _provisioner_dsn(
                admin,
                environment.database_dsn,
                self.asset,
                self.statements,
            )
            application, provisioning_result = _apply_provisioning(
                provisioner_dsn, spec
            )
            if not application.applied:
                yield None, application
                return
            if spec.operator_id == "REORDER_ORDERED_STEPS":
                yield None, application
                return
            if provisioning_result is None:
                raise MutationContractError("適用成功時のprovisioning結果がない")

            cluster = DisposablePostgres(
                container_name=environment.isolation.cluster_id,
                admin_dsn=environment.database_dsn,
                role_dsn_template=environment.database_dsn,
            )
            catalog = ProvisionedCatalog(
                cluster=cluster,
                admin=admin,
                reference_admin=admin,
                provisioner_dsn=provisioner_dsn,
                asset=self.asset,
                statements=self.statements,
                provisioning_result=provisioning_result,
            )
            context = _RuntimeContext(
                admin=admin,
                catalog=catalog,
                role_connections=MappingProxyType({}),
                asset=self.asset,
                statements=self.statements,
                provisioner_id=provisioner_id,
            )
            if blueprint.database_mode == _CLAIM_DECISION_MODE:
                _mutate_claim_function(context, spec)
            elif spec.operator_id != "OMIT_ORDERED_STEP":
                _apply_configuration_mutation(context, spec)

            with _connect_provisioned_authz_login_roles(catalog) as connections:
                context.role_connections = MappingProxyType(dict(connections))
                try:
                    yield context, application
                finally:
                    for connection in connections.values():
                        connection.rollback()
                    admin.rollback()

    def __call__(
        self,
        spec: MutantSpec,
        environment: MutationEnvironment,
    ) -> MutationObservation:
        """1 mutation を適用し、schema/runtime/positive を別々に観測する。"""
        blueprint = mutation_blueprint(spec, self.implementations)
        schema_drift = observe_schema_drift(spec, blueprint)
        if blueprint.database_mode == _NO_DATABASE_MODE:
            observation = MutationObservation(
                application=ApplicationObservation.success(),
                catalog_delta=CatalogDelta(blueprint.changed_element_ids),
                schema_drift=schema_drift,
                runtime_cross_tenant=ChannelObservation.not_run(NotRunReason.HANDOFF),
                runtime_positive_case=ChannelObservation.not_run(NotRunReason.HANDOFF),
            )
            self.execution_records[spec.mutant_id] = (environment, observation)
            return observation

        with self._runtime_context(environment, spec, blueprint) as (
            context,
            application,
        ):
            if context is None:
                return self._failed_application_observation(
                    spec,
                    environment,
                    blueprint,
                    application,
                    schema_drift,
                )
            runtime = _runtime_observation(context, spec, blueprint)
            positive = _positive_observation(context, spec)
            observation = MutationObservation(
                application=application,
                catalog_delta=CatalogDelta(blueprint.changed_element_ids),
                schema_drift=schema_drift,
                runtime_cross_tenant=runtime,
                runtime_positive_case=positive,
            )
            self.execution_records[spec.mutant_id] = (environment, observation)
            return observation


def _observation_mapping(observation: MutationObservation) -> Mapping[str, object]:
    """Dataclass 観測値を JSON 化可能な不変 mapping へ変換する。"""
    raw = asdict(observation)
    return MappingProxyType(raw)


def _surviving_channels(
    spec: MutantSpec, observation: MutationObservation
) -> tuple[str, ...]:
    """Red/kill 期待なのに通過したチャネルだけを返す。"""
    pairs = (
        ("schema_drift", spec.expected_drift_outcome, observation.schema_drift),
        (
            "runtime_cross_tenant",
            spec.expected_runtime_outcome,
            observation.runtime_cross_tenant,
        ),
        (
            "runtime_positive_case",
            spec.expected_positive_outcome,
            observation.runtime_positive_case,
        ),
    )
    return tuple(
        channel_id
        for channel_id, expected, actual in pairs
        if expected in {"red", "kill"} and actual.status is ExecutionStatus.PASSED
    )


def run_mutation_batches(
    runner: MutationRunner,
    executor: FullMutationExecutor,
    batches: tuple[MutationBatch, ...],
) -> tuple[MutationVerdict, ...]:
    """選択した刻みを全件継続し、生存を JSON Lines でまとめて失敗させる。"""
    selected_ids = tuple(
        mutant_id for batch in batches for mutant_id in batch.mutant_ids
    )
    if len(selected_ids) != len(set(selected_ids)):
        raise MutationContractError("実行batch内でmutant_idが重複している")
    unknown = sorted(set(selected_ids) - set(runner.catalog.mutant_by_id))
    if unknown:
        raise MutationContractError(f"実行batchに未知mutantがある: {unknown}")

    verdicts: list[MutationVerdict] = []
    failures: list[MutationExecutionRecord] = []
    for mutant_id in selected_ids:
        spec = runner.catalog.mutant_by_id[mutant_id]
        try:
            verdicts.append(runner.run_one(mutant_id, executor))
        except MutationVerdictError:
            record = executor.execution_records.get(mutant_id)
            if record is None:
                failures.append(
                    MutationExecutionRecord(
                        mutant_id=mutant_id,
                        axis=spec.axis,
                        operator_id=spec.operator_id,
                        failed_checks=("missing_observation",),
                        surviving_channels=(),
                        observation=None,
                        execution_error="kill判定前の観測値がない",
                    )
                )
                continue
            environment, observation = record
            verdict = judge_mutation(
                runner.catalog,
                spec,
                observation,
                mutation_plan(spec),
                environment.isolation,
            )
            failures.append(
                MutationExecutionRecord(
                    mutant_id=mutant_id,
                    axis=spec.axis,
                    operator_id=spec.operator_id,
                    failed_checks=verdict.failure_ids,
                    surviving_channels=_surviving_channels(spec, observation),
                    observation=_observation_mapping(observation),
                    execution_error=None,
                )
            )
        except Exception as error:
            failures.append(
                MutationExecutionRecord(
                    mutant_id=mutant_id,
                    axis=spec.axis,
                    operator_id=spec.operator_id,
                    failed_checks=("execution_error",),
                    surviving_channels=(),
                    observation=None,
                    execution_error=f"{type(error).__name__}: {error}",
                )
            )
    if failures:
        raise MutationBatchError(tuple(failures))
    return tuple(verdicts)
