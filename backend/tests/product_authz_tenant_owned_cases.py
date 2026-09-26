"""製品 RLS の実 DB 試験に使う manifest 由来のケースと投入行。"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from psycopg import sql
from psycopg.types.json import Jsonb

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts/db/schema-manifest.json"
_EXPOSURE_FACTS_PATH = _REPOSITORY_ROOT / "contracts/authz/product/exposure-facts.json"
_MIGRATIONS_PATH = _REPOSITORY_ROOT / "backend/migrations/versions"
_UUID_NAMESPACE = UUID("a65d8e4b-e8ac-4faa-a6a1-40e0d6ef618c")
_RECORDED_AT = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
_FUNCTION_PATTERN = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"
    r"(?P<name>[a-z_][a-z0-9_]*)\s*\(\s*\).*?"
    r"AS\s+\$\$(?P<body>.*?)\$\$",
    re.IGNORECASE | re.DOTALL,
)
_RAISE_PATTERN = re.compile(
    r"RAISE\s+EXCEPTION\s+'(?P<message>(?:''|[^'])*)'\s+"
    r"USING\s+ERRCODE\s*=\s*'(?P<sqlstate>[0-9A-Z]{5})'",
    re.IGNORECASE | re.DOTALL,
)
_DROP_TRIGGER_PATTERN = re.compile(
    r"DROP\s+TRIGGER\s+(?P<trigger>[a-z_][a-z0-9_]*)\s+"
    r"ON\s+(?P<table>[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_TRIGGER_PATTERN = re.compile(
    r"CREATE\s+TRIGGER\s+(?P<trigger>[a-z_][a-z0-9_]*)\s+"
    r"BEFORE\s+UPDATE(?P<scope>.*?)\s+"
    r"ON\s+(?P<table>[a-z_][a-z0-9_]*)\s+"
    r"FOR\s+EACH\s+ROW\s+EXECUTE\s+FUNCTION\s+"
    r"(?P<function>[a-z_][a-z0-9_]*)\s*\(\s*\)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class SeedRow:
    """1 回の INSERT に使う表と列値を保持する。"""

    table: str
    values: dict[str, object]


@dataclass(frozen=True, slots=True)
class TenantUpdateGuard:
    """Tenant の付け替えを先に拒否する migration トリガの事実。"""

    table: str
    trigger_name: str
    function_name: str
    sqlstate: str
    message: str


@dataclass(frozen=True, slots=True)
class _MigrationFunction:
    """Migration が定義する例外送出関数の事実。"""

    name: str
    sqlstate: str
    message: str


@dataclass(frozen=True, slots=True)
class _MigrationTrigger:
    """Migration が最終的に残す BEFORE UPDATE トリガの事実。"""

    table: str
    name: str
    function_name: str
    update_columns: frozenset[str] | None


def _load_object(path: Path) -> dict[str, Any]:
    """JSON 資産を object として読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON 資産の root が object でない: {path}")
    return value


def manifest_tables() -> tuple[dict[str, object], ...]:
    """Schema manifest の表を宣言順で返す。"""
    raw_tables = _load_object(_MANIFEST_PATH).get("tables")
    if not isinstance(raw_tables, list) or not all(
        isinstance(table, dict) for table in raw_tables
    ):
        raise AssertionError("schema-manifest.tables は object 配列が必要")
    return tuple(table for table in raw_tables if isinstance(table, dict))


def _table_name(table: dict[str, object]) -> str:
    """Manifest 表の名前を返す。"""
    name = table.get("name")
    if not isinstance(name, str) or not name:
        raise AssertionError("manifest の表名は空でない文字列が必要")
    return name


def _column_names(table: dict[str, object]) -> tuple[str, ...]:
    """Manifest 表の列名を返す。"""
    raw_columns = table.get("columns")
    if not isinstance(raw_columns, list) or not all(
        isinstance(column, dict) for column in raw_columns
    ):
        raise AssertionError(f"{_table_name(table)}.columns は object 配列が必要")
    result: list[str] = []
    for column in raw_columns:
        if not isinstance(column, dict):
            continue
        name = column.get("name")
        if not isinstance(name, str) or not name:
            raise AssertionError(f"{_table_name(table)} の列名が不正")
        result.append(name)
    return tuple(result)


def tenant_id_table_names() -> tuple[str, ...]:
    """Manifest で tenant_id 列を持つ全表を返す。"""
    return tuple(
        _table_name(table)
        for table in manifest_tables()
        if "tenant_id" in _column_names(table)
    )


def _exposure_fact_tables() -> frozenset[str]:
    """Tenant-owned にできない露出事実の表集合を返す。"""
    raw_facts = _load_object(_EXPOSURE_FACTS_PATH).get("facts")
    if not isinstance(raw_facts, list) or not all(
        isinstance(fact, dict) for fact in raw_facts
    ):
        raise AssertionError("exposure-facts.facts は object 配列が必要")
    result: set[str] = set()
    for fact in raw_facts:
        if not isinstance(fact, dict):
            continue
        entries = fact.get("entries")
        if not isinstance(entries, list) or not all(
            isinstance(entry, dict) for entry in entries
        ):
            raise AssertionError("exposure-facts の entries は object 配列が必要")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            table = entry.get("table")
            if not isinstance(table, str) or not table:
                raise AssertionError("exposure-facts の table が不正")
            result.add(table)
    return frozenset(result)


def tenant_owned_table_names() -> tuple[str, ...]:
    """Manifest と露出事実から tenant_owned の表を導く。"""
    excluded = _exposure_fact_tables()
    return tuple(
        table_name
        for table_name in tenant_id_table_names()
        if table_name not in excluded
    )


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Migration モジュール直下の文字列定数を返す。"""
    result: dict[str, str] = {}
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            result[statement.targets[0].id] = statement.value.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            result[statement.target.id] = statement.value.value
    return result


def _render_migration_sql(
    expression: ast.expr,
    constants: dict[str, str],
) -> str | None:
    """定数文字列だけから成る op.execute 引数を展開する。"""
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    if not isinstance(expression, ast.JoinedStr):
        return None
    fragments: list[str] = []
    for value in expression.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            fragments.append(value.value)
        elif isinstance(value, ast.FormattedValue) and isinstance(
            value.value, ast.Name
        ):
            replacement = constants.get(value.value.id)
            if replacement is None:
                return None
            fragments.append(replacement)
        else:
            return None
    return "".join(fragments)


def _upgrade_sql(path: Path) -> tuple[str, ...]:
    """Migration の upgrade() が直接渡す SQL を呼び出し順で返す。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = _module_string_constants(tree)
    upgrade = next(
        (
            statement
            for statement in tree.body
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            and statement.name == "upgrade"
        ),
        None,
    )
    if upgrade is None:
        raise AssertionError(f"upgrade() が無い migration: {path}")
    calls = sorted(
        (
            node
            for node in ast.walk(upgrade)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
            and node.args
        ),
        key=lambda node: node.lineno,
    )
    result: list[str] = []
    for call in calls:
        rendered = _render_migration_sql(call.args[0], constants)
        if rendered is not None:
            result.append(rendered)
    return tuple(result)


def _trigger_update_columns(scope: str) -> frozenset[str] | None:
    """CREATE TRIGGER の UPDATE 対象列を返し、全列なら None を返す。"""
    normalized = scope.strip()
    if not normalized or normalized.upper().startswith("OR "):
        return None
    if re.match(r"OF\b", normalized, re.IGNORECASE) is None:
        raise AssertionError(f"未知の BEFORE UPDATE 形式: {scope!r}")
    return frozenset(
        name.lower()
        for name in re.findall(r"[a-z_][a-z0-9_]*", normalized[2:], re.IGNORECASE)
    )


def _migration_trigger_facts() -> tuple[
    dict[str, _MigrationFunction],
    dict[tuple[str, str], _MigrationTrigger],
]:
    """全 upgrade を順に適用した後の関数・トリガの事実を返す。"""
    functions: dict[str, _MigrationFunction] = {}
    triggers: dict[tuple[str, str], _MigrationTrigger] = {}
    for path in sorted(_MIGRATIONS_PATH.glob("*.py")):
        for statement in _upgrade_sql(path):
            for match in _FUNCTION_PATTERN.finditer(statement):
                raised = _RAISE_PATTERN.search(match.group("body"))
                if raised is None:
                    continue
                name = match.group("name").lower()
                functions[name] = _MigrationFunction(
                    name=name,
                    sqlstate=raised.group("sqlstate"),
                    message=raised.group("message").replace("''", "'"),
                )
            for match in _DROP_TRIGGER_PATTERN.finditer(statement):
                triggers.pop(
                    (match.group("table").lower(), match.group("trigger").lower()),
                    None,
                )
            for match in _CREATE_TRIGGER_PATTERN.finditer(statement):
                table = match.group("table").lower()
                name = match.group("trigger").lower()
                triggers[(table, name)] = _MigrationTrigger(
                    table=table,
                    name=name,
                    function_name=match.group("function").lower(),
                    update_columns=_trigger_update_columns(match.group("scope")),
                )
    return functions, triggers


def _tenant_update_candidate_names() -> tuple[str, ...]:
    """Manifest で tenant_id 自体が不変な tenant-owned 表を返す。"""
    tenant_owned = frozenset(tenant_owned_table_names())
    result: list[str] = []
    for table in manifest_tables():
        name = _table_name(table)
        immutability = table.get("immutability")
        if name not in tenant_owned or not isinstance(immutability, dict):
            continue
        protected_columns = immutability.get("protected_columns")
        if not isinstance(protected_columns, list):
            raise AssertionError(f"{name}.immutability.protected_columns が不正")
        if "tenant_id" in protected_columns:
            result.append(name)
    return tuple(result)


def tenant_update_guards() -> tuple[TenantUpdateGuard, ...]:
    """Manifest と migration から tenant 付け替え拒否トリガを導く。"""
    functions, triggers = _migration_trigger_facts()
    result: list[TenantUpdateGuard] = []
    for table in _tenant_update_candidate_names():
        matches = tuple(
            trigger
            for trigger in triggers.values()
            if trigger.table == table
            and (
                trigger.update_columns is None or "tenant_id" in trigger.update_columns
            )
        )
        if len(matches) != 1:
            raise AssertionError(
                f"{table} の tenant_id BEFORE UPDATE トリガが 1 件でない: {matches}"
            )
        trigger = matches[0]
        function = functions.get(trigger.function_name)
        if function is None:
            raise AssertionError(
                f"{trigger.function_name} の RAISE EXCEPTION が migration に無い"
            )
        result.append(
            TenantUpdateGuard(
                table=table,
                trigger_name=trigger.name,
                function_name=function.name,
                sqlstate=function.sqlstate,
                message=function.message,
            )
        )
    return tuple(result)


def _id(label: str) -> UUID:
    """試験内で安定した UUID を返す。"""
    return uuid5(_UUID_NAMESPACE, label)


TENANT_A = _id("tenant-a")
TENANT_B = _id("tenant-b")
TENANT_IDS = (TENANT_A, TENANT_B)

_TEAM_ID = _id("team")
_PLAYER_ID = _id("player")
_OTHER_PLAYER_ID = _id("other-player")
_GAME_ID = _id("game")
_OPERATION_EVENT_ID = _id("operation-event")
_PLAY_ID = _id("play")
_MEDICAL_NOTE_ID = _id("medical-note")
_MERGE_EVENT_ID = _id("merge-event")
_RULE_SET_ID = _id("rule-set")
_ANALYSIS_GROUP_ID = _id("analysis-group")
_IMPORT_BATCH_ID = _id("unconstrained-import-batch")
_ACCEPTED_D5 = _id("accepted-d5")
_REJECTED_D5 = _id("rejected-d5")
_EVACUATED_D5 = _id("evacuated-d5")
_INSERT_OPERATION_D5 = _id("insert-operation-d5")
_INSERT_REJECTED_D5 = _id("insert-rejected-d5")
_INSERT_EVACUATED_D5 = _id("insert-evacuated-d5")


def _global_id(table: str, tenant_id: UUID, suffix: str = "base") -> UUID:
    """Tenant 列を主キーに含めない表向けの UUID を返す。"""
    return _id(f"{table}:{tenant_id}:{suffix}")


def _tenant_rows(tenant_id: UUID) -> tuple[SeedRow, ...]:
    """1 tenant 分の対象 28 表と依存行を FK 順に返す。"""
    label = "a" if tenant_id == TENANT_A else "b"
    return (
        SeedRow(
            "tenants",
            {"id": tenant_id, "name": f"tenant-{label}", "enabled": True},
        ),
        SeedRow(
            "tenant_vocabularies",
            {
                "tenant_id": tenant_id,
                "key": "tournament-test",
                "category": "tournament",
                "display_name": "Tournament",
            },
        ),
        SeedRow(
            "team_records",
            {
                "tenant_id": tenant_id,
                "id": _TEAM_ID,
                "kind": "self",
                "name": f"team-{label}",
            },
        ),
        SeedRow(
            "players",
            {
                "tenant_id": tenant_id,
                "id": _PLAYER_ID,
                "team_record_id": _TEAM_ID,
                "name": f"player-{label}",
                "roster_status_key": "roster-status-test",
            },
        ),
        SeedRow(
            "players",
            {
                "tenant_id": tenant_id,
                "id": _OTHER_PLAYER_ID,
                "team_record_id": _TEAM_ID,
                "name": f"other-player-{label}",
                "roster_status_key": "roster-status-test",
            },
        ),
        SeedRow(
            "games",
            {
                "tenant_id": tenant_id,
                "id": _GAME_ID,
                "scheduled_at": _RECORDED_AT,
                "game_type_key": "game-type-test",
                "tournament_key": "tournament-test",
                "away_team_record_id": _TEAM_ID,
                "home_team_record_id": _TEAM_ID,
                "applied_rules": {},
            },
        ),
        SeedRow(
            "lineup_memories",
            {
                "tenant_id": tenant_id,
                "id": _id(f"lineup-memory:{label}"),
                "team_record_id": _TEAM_ID,
                "lineup": {},
            },
        ),
        SeedRow(
            "game_lineups",
            {
                "tenant_id": tenant_id,
                "id": _id(f"game-lineup:{label}"),
                "game_id": _GAME_ID,
                "team_record_id": _TEAM_ID,
                "entries_with_uniform_number_snapshot": {},
            },
        ),
        SeedRow(
            "participation_intervals",
            {
                "tenant_id": tenant_id,
                "id": _id(f"participation:{label}"),
                "game_id": _GAME_ID,
                "slot_kind": "batting_order",
                "slot": "1",
                "player_id": _PLAYER_ID,
                "valid_from_d2": 1,
            },
        ),
        SeedRow(
            "tournament_rule_assignments",
            {
                "tenant_id": tenant_id,
                "tournament_key": "tournament-test",
                "rule_set_id": _RULE_SET_ID,
            },
        ),
        SeedRow(
            "recording_generations",
            {
                "tenant_id": tenant_id,
                "game_id": _GAME_ID,
                "generation": 1,
                "kind": "normal",
                "issuance_order": 1,
            },
        ),
        SeedRow(
            "event_slots",
            {
                "tenant_id": tenant_id,
                "game_id": _GAME_ID,
                "generation": 1,
                "d1": 1,
            },
        ),
        *(
            SeedRow(
                "idempotency_ledger",
                {
                    "tenant_id": tenant_id,
                    "d5": d5,
                    "kind": kind,
                    "source_fingerprint": f"{kind}-{suffix}-{label}",
                    "result": {},
                },
            )
            for d5, kind, suffix in (
                (_ACCEPTED_D5, "accepted", "base"),
                (_REJECTED_D5, "rejected", "base"),
                (_EVACUATED_D5, "evacuated", "base"),
                (_INSERT_OPERATION_D5, "accepted", "insert"),
                (_INSERT_REJECTED_D5, "rejected", "insert"),
                (_INSERT_EVACUATED_D5, "evacuated", "insert"),
            )
        ),
        SeedRow(
            "operation_events",
            {
                "tenant_id": tenant_id,
                "id": _OPERATION_EVENT_ID,
                "game_id": _GAME_ID,
                "generation": 1,
                "d1": 1,
                "d2": None,
                "d5": _ACCEPTED_D5,
                "ledger_kind": "accepted",
                "event_kind": "player_registration",
                "payload": {},
            },
        ),
        SeedRow(
            "play_rows",
            {
                "tenant_id": tenant_id,
                "id": _PLAY_ID,
                "game_id": _GAME_ID,
                "source_event_id": _OPERATION_EVENT_ID,
                "play_number": 1,
                "event_kind": "non_pitch",
            },
        ),
        SeedRow(
            "play_runners",
            {
                "tenant_id": tenant_id,
                "id": _id(f"play-runner:{label}"),
                "play_id": _PLAY_ID,
                "base": 1,
                "runner_id": _PLAYER_ID,
                "status": "advanced",
                "status_source": "auto",
                "responsible_pitcher_id": _OTHER_PLAYER_ID,
            },
        ),
        SeedRow(
            "temporary_player_id_mappings",
            {
                "tenant_id": tenant_id,
                "id": _id(f"temporary-mapping:{label}"),
                "temporary_id": _id(f"temporary-player:{label}"),
                "player_id": _PLAYER_ID,
            },
        ),
        SeedRow(
            "rejected_event_originals",
            {
                "tenant_id": tenant_id,
                "id": _id(f"rejected-original:{label}"),
                "d5": _REJECTED_D5,
                "kind": "rejected",
                "payload": {},
            },
        ),
        SeedRow(
            "evacuated_event_originals",
            {
                "tenant_id": tenant_id,
                "id": _id(f"evacuated-original:{label}"),
                "game_id": _GAME_ID,
                "old_generation": 1,
                "original_d1": 1,
                "d5": _EVACUATED_D5,
                "kind": "evacuated",
                "origin": "authority_mismatch",
            },
        ),
        SeedRow(
            "medical_notes",
            {
                "tenant_id": tenant_id,
                "id": _MEDICAL_NOTE_ID,
                "player_id": _PLAYER_ID,
                "note_kind": "pitcher",
                "content": "base",
            },
        ),
        SeedRow(
            "medical_note_versions",
            {
                "tenant_id": tenant_id,
                "id": _id(f"medical-version:{label}"),
                "medical_note_id": _MEDICAL_NOTE_ID,
                "version": 1,
                "content": "base",
            },
        ),
        SeedRow(
            "pdf_export_records",
            {
                "tenant_id": tenant_id,
                "id": _id(f"pdf-export:{label}"),
                "team_record_id": _TEAM_ID,
                "applied_filters": {},
            },
        ),
        SeedRow(
            "tenant_auth_subjects",
            {
                "id": _global_id("tenant-auth-subject", tenant_id),
                "tenant_id": tenant_id,
            },
        ),
        SeedRow(
            "tenant_tokens",
            {
                "id": _global_id("tenant-token", tenant_id),
                "tenant_id": tenant_id,
                "auth_subject_id": _global_id("tenant-auth-subject", tenant_id),
                "credential_generation": 1,
                "expires_at": _RECORDED_AT,
                "last_used_at": _RECORDED_AT,
            },
        ),
        SeedRow(
            "admin_operation_logs",
            {
                "id": _global_id("admin-operation-log", tenant_id),
                "operation_kind": "tenant-test",
                "target": {},
                "tenant_id": tenant_id,
            },
        ),
        SeedRow(
            "player_merge_events",
            {
                "tenant_id": tenant_id,
                "id": _MERGE_EVENT_ID,
                "source_player_id": _PLAYER_ID,
                "target_player_id": _OTHER_PLAYER_ID,
                "executor": "tenant-test",
            },
        ),
        SeedRow(
            "player_move_records",
            {
                "tenant_id": tenant_id,
                "id": _id(f"player-move:{label}"),
                "merge_event_id": _MERGE_EVENT_ID,
                "resource_kind": "medical_note",
                "resource_id": _MEDICAL_NOTE_ID,
                "original_player_id": _PLAYER_ID,
                "moved_player_id": _OTHER_PLAYER_ID,
            },
        ),
        SeedRow(
            "group_memberships",
            {
                "id": _global_id("group-membership", tenant_id),
                "group_id": _ANALYSIS_GROUP_ID,
                "tenant_id": tenant_id,
                "role": "member",
                "status": "active",
            },
        ),
        SeedRow(
            "invalidation_intents",
            {
                "tenant_id": tenant_id,
                "intent_id": "base",
                "scope_kind": "team_total",
            },
        ),
        SeedRow(
            "migrated_final_lineups",
            {
                "tenant_id": tenant_id,
                "id": _id(f"migrated-lineup:{label}"),
                "game_id": _GAME_ID,
                "team_record_id": _TEAM_ID,
                "raw_lineup": "base",
                "legacy_row_identifier": f"legacy-{label}",
                "import_batch_id": _IMPORT_BATCH_ID,
            },
        ),
    )


def seed_rows() -> tuple[SeedRow, ...]:
    """共有依存行と A/B の対象行を FK 順に返す。"""
    shared = (
        SeedRow(
            "system_vocabularies",
            {
                "key": "game-type-test",
                "category": "game_type",
                "display_name": "Game type",
            },
        ),
        SeedRow(
            "system_vocabularies",
            {
                "key": "roster-status-test",
                "category": "roster_status",
                "display_name": "Roster status",
            },
        ),
        SeedRow(
            "rule_sets",
            {
                "id": _RULE_SET_ID,
                "regulation_innings": 9,
                "called_game_conditions": {},
            },
        ),
        SeedRow("analysis_groups", {"id": _ANALYSIS_GROUP_ID}),
    )
    rows_a = _tenant_rows(TENANT_A)
    rows_b = _tenant_rows(TENANT_B)
    result: list[SeedRow] = list(shared)
    table_order = tuple(dict.fromkeys(row.table for row in (*rows_a, *rows_b)))
    for table in table_order:
        result.extend(row for row in rows_a if row.table == table)
        result.extend(row for row in rows_b if row.table == table)
    return tuple(result)


def insert_candidate(table: str, tenant_id: UUID) -> SeedRow:
    """WITH CHECK を通れば制約上は妥当な追加行を返す。"""
    label = "a" if tenant_id == TENANT_A else "b"
    candidates: dict[str, dict[str, object]] = {
        "team_records": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-team:{label}"),
            "kind": "opponent",
            "name": "insert-team",
        },
        "players": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-player:{label}"),
            "team_record_id": _TEAM_ID,
            "name": "insert-player",
            "roster_status_key": "roster-status-test",
        },
        "games": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-game:{label}"),
            "scheduled_at": _RECORDED_AT,
            "game_type_key": "game-type-test",
            "tournament_key": "tournament-test",
            "away_team_record_id": _TEAM_ID,
            "home_team_record_id": _TEAM_ID,
            "applied_rules": {},
        },
        "lineup_memories": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-lineup-memory:{label}"),
            "team_record_id": _TEAM_ID,
            "lineup": {},
            "retired_at": _RECORDED_AT,
        },
        "game_lineups": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-game-lineup:{label}"),
            "game_id": _GAME_ID,
            "team_record_id": _TEAM_ID,
            "entries_with_uniform_number_snapshot": {},
        },
        "participation_intervals": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-participation:{label}"),
            "game_id": _GAME_ID,
            "slot_kind": "batting_order",
            "slot": "2",
            "player_id": _PLAYER_ID,
            "valid_from_d2": 2,
        },
        "event_slots": {
            "tenant_id": tenant_id,
            "game_id": _GAME_ID,
            "generation": 1,
            "d1": 2,
        },
        "operation_events": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-operation:{label}"),
            "game_id": _GAME_ID,
            "generation": 1,
            "d1": 1,
            "d2": None,
            "d5": _INSERT_OPERATION_D5,
            "ledger_kind": "accepted",
            "event_kind": "player_registration",
            "payload": {},
            "replaced_at": _RECORDED_AT,
        },
        "play_rows": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-play:{label}"),
            "game_id": _GAME_ID,
            "source_event_id": _OPERATION_EVENT_ID,
            "play_number": 2,
            "event_kind": "non_pitch",
        },
        "play_runners": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-play-runner:{label}"),
            "play_id": _PLAY_ID,
            "base": 2,
            "runner_id": _PLAYER_ID,
            "status": "advanced",
            "status_source": "auto",
            "responsible_pitcher_id": _OTHER_PLAYER_ID,
        },
        "temporary_player_id_mappings": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-temporary-mapping:{label}"),
            "temporary_id": _id(f"insert-temporary-player:{label}"),
            "player_id": _PLAYER_ID,
        },
        "idempotency_ledger": {
            "tenant_id": tenant_id,
            "d5": _id(f"insert-ledger:{label}"),
            "kind": "accepted",
            "source_fingerprint": f"insert-ledger-{label}",
            "result": {},
        },
        "rejected_event_originals": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-rejected:{label}"),
            "d5": _INSERT_REJECTED_D5,
            "kind": "rejected",
            "payload": {},
        },
        "evacuated_event_originals": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-evacuated:{label}"),
            "game_id": _GAME_ID,
            "old_generation": 2,
            "original_d1": 2,
            "d5": _INSERT_EVACUATED_D5,
            "kind": "evacuated",
            "origin": "authority_mismatch",
        },
        "recording_generations": {
            "tenant_id": tenant_id,
            "game_id": _GAME_ID,
            "generation": 2,
            "kind": "migration",
            "issuance_order": 2,
        },
        "medical_notes": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-medical-note:{label}"),
            "player_id": _PLAYER_ID,
            "note_kind": "batter",
            "content": "insert",
        },
        "medical_note_versions": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-medical-version:{label}"),
            "medical_note_id": _MEDICAL_NOTE_ID,
            "version": 2,
            "content": "insert",
        },
        "pdf_export_records": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-pdf-export:{label}"),
            "team_record_id": _TEAM_ID,
            "applied_filters": {},
        },
        "tenant_vocabularies": {
            "tenant_id": tenant_id,
            "key": "tournament-insert",
            "category": "tournament",
            "display_name": "Tournament insert",
        },
        "player_merge_events": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-player-merge:{label}"),
            "source_player_id": _PLAYER_ID,
            "target_player_id": _OTHER_PLAYER_ID,
            "executor": "tenant-test",
        },
        "player_move_records": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-player-move:{label}"),
            "merge_event_id": _MERGE_EVENT_ID,
            "resource_kind": "medical_note",
            "resource_id": _MEDICAL_NOTE_ID,
            "original_player_id": _PLAYER_ID,
            "moved_player_id": _OTHER_PLAYER_ID,
        },
        "invalidation_intents": {
            "tenant_id": tenant_id,
            "intent_id": "insert",
            "scope_kind": "team_total",
        },
        "migrated_final_lineups": {
            "tenant_id": tenant_id,
            "id": _id(f"insert-migrated-lineup:{label}"),
            "game_id": _GAME_ID,
            "team_record_id": _TEAM_ID,
            "raw_lineup": "insert",
            "legacy_row_identifier": f"insert-legacy-{label}",
            "import_batch_id": _IMPORT_BATCH_ID,
            "retired_at": _RECORDED_AT,
        },
    }
    if table not in candidates:
        raise AssertionError(f"tenant_owned の INSERT 行が未定義: {table}")
    return SeedRow(table=table, values=candidates[table])


def insert_statement(row: SeedRow) -> tuple[sql.Composed, tuple[object, ...]]:
    """SeedRow から識別子を引用した INSERT と束縛値を作る。"""
    columns = tuple(row.values)
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier("public", row.table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    params = tuple(
        Jsonb(value) if isinstance(value, (dict, list)) else value
        for value in row.values.values()
    )
    return statement, params
