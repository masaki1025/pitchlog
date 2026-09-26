"""製品認可のその他プロファイル用ケースと投入行を組み立てる。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from product_authz_tenant_owned_cases import (
    TENANT_A,
    TENANT_B,
    SeedRow,
    manifest_tables,
    seed_rows,
    tenant_owned_table_names,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXPOSURE_FACTS_PATH = _REPOSITORY_ROOT / "contracts/authz/product/exposure-facts.json"
_HELPER_BODY_PATH = (
    _REPOSITORY_ROOT / "contracts/authz/product/function-bodies/functions/"
    "FUNCTION:authz_private:tenant_has_effective_membership(uuid, boolean).sql"
)
_UUID_NAMESPACE = UUID("07467864-acdb-4e9d-a418-354646ebcc8f")
_RECORDED_AT = datetime(2026, 9, 26, 13, 0, tzinfo=timezone.utc)
_FUNCTION_ONLY_FACT_KINDS = frozenset(
    {
        "mixed_ownership_rule_resource",
        "admin_only",
        "pre_auth_only",
        "migration_only",
    }
)


@dataclass(frozen=True, slots=True)
class ControlMatrixCase:
    """制御資源の実効参加状態と期待する真偽値。"""

    case_id: str
    tenant_id: UUID
    group_id: UUID
    general_visible: bool
    invitation_visible: bool


@dataclass(frozen=True, slots=True)
class HelperConditionMutation:
    """補助関数から 1 条件だけを除く変異と変化する行列セル。"""

    condition_id: str
    original_sql: str
    replacement_sql: str
    general_visible_cases: frozenset[str]
    invitation_visible_cases: frozenset[str]
    nonexistent_general_visible: bool = False
    nonexistent_invitation_visible: bool = False


def _id(label: str) -> UUID:
    """試験内で安定した UUID を返す。"""
    return uuid5(_UUID_NAMESPACE, label)


TENANT_DISABLED = _id("tenant-disabled")
NONEXISTENT_GROUP_ID = _id("group-nonexistent")

_RULE_SET_A = _id("rule-set-a")
_RULE_SET_B = _id("rule-set-b")
_TOURNAMENT_KEY_A = "step8-tournament-a"
_TOURNAMENT_KEY_B = "step8-tournament-b"
_ADMIN_CREDENTIAL_A = _id("admin-credential-a")
_ADMIN_CREDENTIAL_B = _id("admin-credential-b")
_MIGRATION_RUN_A = _id("migration-run-a")
_MIGRATION_RUN_B = _id("migration-run-b")

_CONTROL_CASE_ROWS = (
    ("member", TENANT_A, "member", "active", "active"),
    ("admin", TENANT_A, "admin", "active", "active"),
    ("non_member", TENANT_B, "admin", "active", "active"),
    ("left", TENANT_A, "admin", "left", "active"),
    ("terminated", TENANT_A, "admin", "active", "terminated"),
    ("disabled_tenant", TENANT_DISABLED, "admin", "active", "active"),
)


def _load_object(path: Path) -> dict[str, Any]:
    """JSON 資産を object として読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON 資産の root が object でない: {path}")
    return value


def manifest_table_names() -> tuple[str, ...]:
    """Manifest の全表名を宣言順で返す。"""
    result: list[str] = []
    for table in manifest_tables():
        name = table.get("name")
        if not isinstance(name, str) or not name:
            raise AssertionError("manifest の表名が不正")
        result.append(name)
    return tuple(result)


def exposure_fact_table_names(kind: str) -> tuple[str, ...]:
    """指定した露出事実に属する実在表を manifest 順で返す。"""
    facts = _load_object(_EXPOSURE_FACTS_PATH).get("facts")
    if not isinstance(facts, list):
        raise AssertionError("exposure-facts.facts は配列が必要")
    matched: set[str] = set()
    matched_kind = False
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("kind") != kind:
            continue
        matched_kind = True
        entries = fact.get("entries")
        if not isinstance(entries, list):
            raise AssertionError(f"露出事実 {kind} の entries は配列が必要")
        for entry in entries:
            if not isinstance(entry, dict):
                raise AssertionError(f"露出事実 {kind} の entry が不正")
            table = entry.get("table")
            if not isinstance(table, str) or not table:
                raise AssertionError(f"露出事実 {kind} の表名が不正")
            matched.add(table)
    if not matched_kind:
        raise AssertionError(f"未知の露出事実 kind: {kind}")
    manifest_names = manifest_table_names()
    unknown = matched - set(manifest_names)
    if unknown:
        raise AssertionError(f"露出事実に manifest 外の表がある: {sorted(unknown)}")
    return tuple(name for name in manifest_names if name in matched)


def self_tenant_row_table_names() -> tuple[str, ...]:
    """tenant_id FK が id を参照する親表を manifest から導く。"""
    targets: set[str] = set()
    for table in manifest_tables():
        foreign_keys = table.get("foreign_keys")
        if not isinstance(foreign_keys, list):
            raise AssertionError("manifest.foreign_keys は配列が必要")
        for foreign_key in foreign_keys:
            if not isinstance(foreign_key, dict):
                raise AssertionError("manifest の FK が不正")
            references = foreign_key.get("references")
            if (
                foreign_key.get("columns") != ["tenant_id"]
                or not isinstance(references, dict)
                or references.get("columns") != ["id"]
            ):
                continue
            target = references.get("table")
            if not isinstance(target, str) or not target:
                raise AssertionError("tenant_id FK の参照表が不正")
            targets.add(target)
    manifest_names = manifest_table_names()
    return tuple(name for name in manifest_names if name in targets)


def global_read_only_table_names() -> tuple[str, ...]:
    """非テナントの露出事実から全体読み取り専用表を導く。"""
    return exposure_fact_table_names("non_tenant")


def control_resource_table_names() -> tuple[str, ...]:
    """制御資源の露出事実から対象 4 表を導く。"""
    return exposure_fact_table_names("control_resource")


def function_only_table_names() -> tuple[str, ...]:
    """関数経由だけに閉じる露出事実の表を導く。"""
    selected: set[str] = set()
    for kind in _FUNCTION_ONLY_FACT_KINDS:
        selected.update(exposure_fact_table_names(kind))
    return tuple(name for name in manifest_table_names() if name in selected)


def profile_table_names() -> dict[str, tuple[str, ...]]:
    """分類資産に依存しない 5 プロファイルの表集合を返す。"""
    return {
        "tenant_owned": tenant_owned_table_names(),
        "self_tenant_row": self_tenant_row_table_names(),
        "effective_group_control": control_resource_table_names(),
        "global_read_only": global_read_only_table_names(),
        "function_only": function_only_table_names(),
    }


def _seed_value(table: str, column: str, tenant_id: UUID | None = None) -> object:
    """ステップ 7 の投入行から既存の参照値を得る。"""
    matches = tuple(
        row.values[column]
        for row in seed_rows()
        if row.table == table
        and column in row.values
        and (tenant_id is None or row.values.get("tenant_id") == tenant_id)
    )
    if len(matches) != 1:
        raise AssertionError(f"既存投入値が一意でない: {table}.{column}/{tenant_id}")
    return matches[0]


def _control_matrix_rows() -> tuple[SeedRow, ...]:
    """正負行列の各状態に 4 制御資源の対象行を用意する。"""
    groups: list[SeedRow] = []
    memberships: list[SeedRow] = []
    grants: list[SeedRow] = []
    invitations: list[SeedRow] = []
    for case_id, tenant_id, role, membership_status, group_status in _CONTROL_CASE_ROWS:
        group_id = _id(f"group-{case_id}")
        membership_id = _id(f"membership-{case_id}")
        groups.append(
            SeedRow(
                "analysis_groups",
                {
                    "id": group_id,
                    "status": group_status,
                    "terminated_at": (
                        _RECORDED_AT if group_status == "terminated" else None
                    ),
                    "termination_reason": (
                        "step8-test" if group_status == "terminated" else None
                    ),
                },
            )
        )
        memberships.append(
            SeedRow(
                "group_memberships",
                {
                    "id": membership_id,
                    "group_id": group_id,
                    "tenant_id": tenant_id,
                    "role": role,
                    "status": membership_status,
                    "left_at": (_RECORDED_AT if membership_status == "left" else None),
                },
            )
        )
        grants.append(
            SeedRow(
                "sharing_grants",
                {"membership_id": membership_id, "grant_flags": {}},
            )
        )
        invitations.append(
            SeedRow(
                "group_invitations",
                {
                    "id": _id(f"invitation-{case_id}"),
                    "group_id": group_id,
                    "code_hash": f"step8-code-{case_id}",
                    "expires_at": _RECORDED_AT,
                    "status": "unconsumed",
                    "initial_role": "member",
                },
            )
        )
    return (*groups, *memberships, *grants, *invitations)


def additional_seed_rows() -> tuple[SeedRow, ...]:
    """その他プロファイルに不足する行を FK 順で返す。"""
    subject_a = _seed_value("tenant_auth_subjects", "id", TENANT_A)
    subject_b = _seed_value("tenant_auth_subjects", "id", TENANT_B)
    base_rule_set = _seed_value("rule_sets", "id")
    return (
        SeedRow(
            "tenants",
            {
                "id": TENANT_DISABLED,
                "name": "tenant-disabled",
                "enabled": False,
                "disabled_at": _RECORDED_AT,
            },
        ),
        SeedRow(
            "admin_vocabularies",
            {
                "key": "step8-season",
                "category": "season",
                "display_name": "Step 8 season",
            },
        ),
        SeedRow(
            "system_settings",
            {"key": "step8-setting", "value": {"enabled": True}},
        ),
        SeedRow(
            "game_type_rule_defaults",
            {"game_type_key": "game-type-test", "rule_set_id": base_rule_set},
        ),
        SeedRow(
            "tenant_credentials",
            {"auth_subject_id": subject_a, "password_hash": "step8-a"},
        ),
        SeedRow(
            "tenant_credentials",
            {"auth_subject_id": subject_b, "password_hash": "step8-b"},
        ),
        SeedRow(
            "rate_limit_counters",
            {
                "id": _id("rate-limit-a"),
                "scope_key": f"tenant:{TENANT_A}",
                "window_start": _RECORDED_AT,
            },
        ),
        SeedRow(
            "rate_limit_counters",
            {
                "id": _id("rate-limit-b"),
                "scope_key": f"tenant:{TENANT_B}",
                "window_start": _RECORDED_AT,
            },
        ),
        SeedRow(
            "admin_credentials",
            {"id": _ADMIN_CREDENTIAL_A, "password_hash": "step8-admin-a"},
        ),
        SeedRow(
            "admin_credentials",
            {"id": _ADMIN_CREDENTIAL_B, "password_hash": "step8-admin-b"},
        ),
        SeedRow(
            "admin_sessions",
            {
                "id": _id("admin-session-a"),
                "admin_credential_id": _ADMIN_CREDENTIAL_A,
                "credential_generation": 1,
                "expires_at": _RECORDED_AT,
                "last_used_at": _RECORDED_AT,
            },
        ),
        SeedRow(
            "admin_sessions",
            {
                "id": _id("admin-session-b"),
                "admin_credential_id": _ADMIN_CREDENTIAL_B,
                "credential_generation": 1,
                "expires_at": _RECORDED_AT,
                "last_used_at": _RECORDED_AT,
            },
        ),
        SeedRow(
            "migration_runs",
            {
                "id": _MIGRATION_RUN_A,
                "source_counts": {},
                "generated_copy_counts": {},
                "validation_results": {},
            },
        ),
        SeedRow(
            "migration_runs",
            {
                "id": _MIGRATION_RUN_B,
                "source_counts": {},
                "generated_copy_counts": {},
                "validation_results": {},
            },
        ),
        *(
            SeedRow(
                "migration_quarantine",
                {
                    "id": _id(f"migration-quarantine-{label}"),
                    "import_batch_id": run_id,
                    "source_read_order": index,
                    "raw_payload": f"step8-{label}".encode(),
                },
            )
            for index, (label, run_id) in enumerate(
                (("a", _MIGRATION_RUN_A), ("b", _MIGRATION_RUN_B)),
                start=1,
            )
        ),
        *(
            SeedRow(
                "migration_resolution_reports",
                {
                    "id": _id(f"migration-resolution-{label}"),
                    "import_batch_id": run_id,
                    "source_kind": "step8",
                    "legacy_row_identifier": f"resolution-{label}",
                    "issue": {},
                },
            )
            for label, run_id in (("a", _MIGRATION_RUN_A), ("b", _MIGRATION_RUN_B))
        ),
        *(
            SeedRow(
                "migration_warning_reports",
                {
                    "id": _id(f"migration-warning-{label}"),
                    "import_batch_id": run_id,
                    "source_kind": "step8",
                    "legacy_row_identifier": f"warning-{label}",
                    "warning_kind": "step8",
                    "details": {},
                },
            )
            for label, run_id in (("a", _MIGRATION_RUN_A), ("b", _MIGRATION_RUN_B))
        ),
        SeedRow(
            "rule_sets",
            {
                "id": _RULE_SET_A,
                "regulation_innings": 7,
                "called_game_conditions": {"tenant": "a"},
            },
        ),
        SeedRow(
            "rule_sets",
            {
                "id": _RULE_SET_B,
                "regulation_innings": 7,
                "called_game_conditions": {"tenant": "b"},
            },
        ),
        SeedRow(
            "tenant_vocabularies",
            {
                "tenant_id": TENANT_A,
                "key": _TOURNAMENT_KEY_A,
                "category": "tournament",
                "display_name": "Step 8 tournament A",
            },
        ),
        SeedRow(
            "tenant_vocabularies",
            {
                "tenant_id": TENANT_B,
                "key": _TOURNAMENT_KEY_B,
                "category": "tournament",
                "display_name": "Step 8 tournament B",
            },
        ),
        SeedRow(
            "tournament_rule_assignments",
            {
                "tenant_id": TENANT_A,
                "tournament_key": _TOURNAMENT_KEY_A,
                "rule_set_id": _RULE_SET_A,
            },
        ),
        SeedRow(
            "tournament_rule_assignments",
            {
                "tenant_id": TENANT_B,
                "tournament_key": _TOURNAMENT_KEY_B,
                "rule_set_id": _RULE_SET_B,
            },
        ),
        *_control_matrix_rows(),
    )


def other_profile_seed_rows() -> tuple[SeedRow, ...]:
    """ステップ 7 の行とその他プロファイルの追加行を FK 順で返す。"""
    return (*seed_rows(), *additional_seed_rows())


def control_matrix_cases() -> tuple[ControlMatrixCase, ...]:
    """制御資源の全状態と期待値を返す。"""
    result: list[ControlMatrixCase] = []
    for case_id, tenant_id, role, membership_status, group_status in _CONTROL_CASE_ROWS:
        general_visible = case_id not in {
            "non_member",
            "left",
            "terminated",
            "disabled_tenant",
        }
        result.append(
            ControlMatrixCase(
                case_id=case_id,
                tenant_id=TENANT_A if case_id == "non_member" else tenant_id,
                group_id=_id(f"group-{case_id}"),
                general_visible=general_visible,
                invitation_visible=general_visible and role == "admin",
            )
        )
    return tuple(result)


def membership_helper_create_sql() -> str:
    """資産から補助関数の CREATE OR REPLACE 文だけを返す。"""
    source = _HELPER_BODY_PATH.read_text(encoding="utf-8")
    create_sql, marker, _ = source.partition("ALTER FUNCTION")
    if not marker or create_sql.count("CREATE OR REPLACE FUNCTION") != 1:
        raise AssertionError("補助関数資産から CREATE 文を一意に取り出せない")
    return create_sql.strip()


def helper_condition_mutations() -> tuple[HelperConditionMutation, ...]:
    """正負行列の負セルを変える 6 個の単一条件変異を返す。"""
    baseline_general = frozenset({"member", "admin"})
    baseline_invitation = frozenset({"admin"})
    return (
        HelperConditionMutation(
            condition_id="group_identity",
            original_sql="            WHERE effective_group.id = p_group_id\n",
            replacement_sql="            WHERE true\n",
            general_visible_cases=frozenset(
                {"member", "admin", "non_member", "left", "terminated"}
            ),
            invitation_visible_cases=frozenset(
                {"member", "admin", "non_member", "left", "terminated"}
            ),
            nonexistent_general_visible=True,
            nonexistent_invitation_visible=True,
        ),
        HelperConditionMutation(
            condition_id="group_active",
            original_sql="              AND effective_group.status = 'active'\n",
            replacement_sql="",
            general_visible_cases=baseline_general | {"terminated"},
            invitation_visible_cases=baseline_invitation | {"terminated"},
        ),
        HelperConditionMutation(
            condition_id="membership_active",
            original_sql="              AND membership.status = 'active'\n",
            replacement_sql="",
            general_visible_cases=baseline_general | {"left"},
            invitation_visible_cases=baseline_invitation | {"left"},
        ),
        HelperConditionMutation(
            condition_id="member_tenant_enabled",
            original_sql="              AND member_tenant.enabled\n",
            replacement_sql="",
            general_visible_cases=baseline_general | {"disabled_tenant"},
            invitation_visible_cases=baseline_invitation | {"disabled_tenant"},
        ),
        HelperConditionMutation(
            condition_id="requesting_tenant_membership",
            original_sql=(
                "              AND membership.tenant_id = NULLIF(\n"
                "                  pg_catalog.current_setting('app.tenant_id', true),\n"
                "                  ''\n"
                "              )::uuid\n"
            ),
            replacement_sql="",
            general_visible_cases=baseline_general | {"non_member"},
            invitation_visible_cases=baseline_invitation | {"non_member"},
        ),
        HelperConditionMutation(
            condition_id="admin_role",
            original_sql=(
                "              AND (NOT p_require_admin OR membership.role = 'admin')\n"
            ),
            replacement_sql="",
            general_visible_cases=baseline_general,
            invitation_visible_cases=baseline_invitation | {"member"},
        ),
    )


def mutated_membership_helper_sql(mutation: HelperConditionMutation) -> str:
    """補助関数資産から指定条件だけを除いた CREATE 文を作る。"""
    original = membership_helper_create_sql()
    if original.count(mutation.original_sql) != 1:
        raise AssertionError(
            f"補助関数の変異対象が 1 件でない: {mutation.condition_id}"
        )
    return original.replace(
        mutation.original_sql,
        mutation.replacement_sql,
        1,
    )
