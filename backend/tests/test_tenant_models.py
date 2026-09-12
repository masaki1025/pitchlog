"""テナント分離領域のモデルを manifest と照合する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression
from sqlalchemy.sql.schema import DefaultClause, Index, Table

from pitchlog.db.tenant_isolation.models import (
    AdminCredential,
    AdminOperationLog,
    AdminSession,
    AdminVocabulary,
    AnalysisGroup,
    GroupInvitation,
    GroupMembership,
    MedicalNote,
    MedicalNoteVersion,
    PdfExportRecord,
    Player,
    PlayerMergeEvent,
    PlayerMoveRecord,
    RateLimitCounter,
    SharingGrant,
    SystemSetting,
    SystemVocabulary,
    TeamRecord,
    Tenant,
    TenantAuthSubject,
    TenantCredential,
    TenantToken,
    TenantVocabulary,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_VOCABULARY_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0010_vocabularies_settings.py"
)
_AUTH_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0011_authentication_tables.py"
)
_ADMIN_OPERATION_LOG_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0012_admin_operation_logs.py"
)
_PLAYER_MERGE_MIGRATION_PATH = (
    _REPOSITORY_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0013_player_merge_rate_limits.py"
)
_ANALYSIS_GROUP_MIGRATION_PATH = (
    _REPOSITORY_ROOT / "backend" / "migrations" / "versions" / "0014_analysis_groups.py"
)
_MODEL_CLASSES: dict[str, Any] = {
    "tenants": Tenant,
    "team_records": TeamRecord,
    "players": Player,
    "medical_notes": MedicalNote,
    "medical_note_versions": MedicalNoteVersion,
    "pdf_export_records": PdfExportRecord,
    "system_vocabularies": SystemVocabulary,
    "admin_vocabularies": AdminVocabulary,
    "tenant_vocabularies": TenantVocabulary,
    "system_settings": SystemSetting,
    "tenant_auth_subjects": TenantAuthSubject,
    "tenant_credentials": TenantCredential,
    "admin_credentials": AdminCredential,
    "admin_sessions": AdminSession,
    "tenant_tokens": TenantToken,
    "admin_operation_logs": AdminOperationLog,
    "player_merge_events": PlayerMergeEvent,
    "player_move_records": PlayerMoveRecord,
    "rate_limit_counters": RateLimitCounter,
    "analysis_groups": AnalysisGroup,
    "group_memberships": GroupMembership,
    "sharing_grants": SharingGrant,
    "group_invitations": GroupInvitation,
}


class _ColumnContract(TypedDict):
    """比較用の列契約。"""

    name: str
    type: str
    nullable: bool
    default: str | None


class _UniqueContract(TypedDict):
    """比較用の一意制約契約。"""

    name: str
    kind: str
    columns: list[str]
    predicate: str | None
    roles: list[str]


class _IndexContract(TypedDict):
    """比較用の索引契約。"""

    name: str
    columns: list[str]
    predicate: str | None
    purpose: str


def _load_manifest_tables() -> dict[str, dict[str, Any]]:
    """Manifest の表を名前で引ける形にして返す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {table["name"]: table for table in manifest["tables"]}


def _column_type_name(column: Column[Any]) -> str:
    """SQLAlchemy の列型を manifest の型名へ正規化する。"""
    if isinstance(column.type, Uuid):
        return "uuid"
    if isinstance(column.type, JSONB):
        return "jsonb"
    if isinstance(column.type, BigInteger):
        return "bigint"
    if isinstance(column.type, Text):
        return "text"
    if isinstance(column.type, Boolean):
        return "boolean"
    if isinstance(column.type, DateTime) and column.type.timezone:
        return "timestamptz"
    raise AssertionError(f"未対応の列型: {column.name}: {column.type}")


def _column_default(column: Column[Any]) -> str | None:
    """サーバー既定値を manifest と比較できる文字列へ変換する。"""
    if column.default is not None:
        raise AssertionError(f"Python 側だけの既定値がある: {column.name}")
    if column.server_default is None:
        return None
    if not isinstance(column.server_default, DefaultClause):
        raise AssertionError(f"未対応のサーバー既定値: {column.name}")
    return str(column.server_default.arg)


def _model_columns(table: Table) -> list[_ColumnContract]:
    """Models の列契約を manifest と同じ形へ変換する。"""
    contracts: list[_ColumnContract] = []
    for column in table.columns:
        if column.nullable is None:
            raise AssertionError(f"NULL 性が未確定である: {table.name}.{column.name}")
        contracts.append(
            _ColumnContract(
                name=column.name,
                type=_column_type_name(column),
                nullable=column.nullable,
                default=_column_default(column),
            )
        )
    return sorted(contracts, key=lambda column: column["name"])


def _index_predicate(index: Index) -> str | None:
    """PostgreSQL 部分索引の述語全文を返す。"""
    predicate = index.dialect_options["postgresql"]["where"]
    return None if predicate is None else str(predicate)


def _model_unique_constraints(table: Table) -> list[_UniqueContract]:
    """主キーと一意索引を manifest の一意制約契約へ変換する。"""
    primary_key_name = table.primary_key.name
    if not isinstance(primary_key_name, str):
        raise AssertionError(f"主キー名が空である: {table.name}")
    contracts: list[_UniqueContract] = [
        {
            "name": primary_key_name,
            "kind": "PRIMARY KEY",
            "columns": list(table.primary_key.columns.keys()),
            "predicate": None,
            "roles": sorted(table.primary_key.info["roles"]),
        }
    ]
    for constraint in table.constraints:
        if not isinstance(constraint, UniqueConstraint):
            continue
        if not isinstance(constraint.name, str):
            raise AssertionError(f"一意制約名が空である: {table.name}")
        contracts.append(
            {
                "name": constraint.name,
                "kind": "UNIQUE",
                "columns": list(constraint.columns.keys()),
                "predicate": None,
                "roles": sorted(str(role) for role in constraint.info["roles"]),
            }
        )
    for index in table.indexes:
        if not index.unique:
            continue
        if not isinstance(index.name, str):
            raise AssertionError(f"一意索引名が空である: {table.name}")
        contracts.append(
            {
                "name": index.name,
                "kind": "UNIQUE INDEX",
                "columns": list(index.columns.keys()),
                "predicate": _index_predicate(index),
                "roles": sorted(str(role) for role in index.info["roles"]),
            }
        )
    return sorted(contracts, key=lambda contract: str(contract["name"]))


def _manifest_unique_constraints(table: dict[str, Any]) -> list[_UniqueContract]:
    """Manifest の一意制約から models が宣言する構造だけを取り出す。"""
    return sorted(
        (
            {
                "name": constraint["name"],
                "kind": constraint["kind"],
                "columns": constraint["columns"],
                "predicate": constraint["predicate"],
                "roles": sorted(constraint["roles"]),
            }
            for constraint in table["unique_constraints"]
        ),
        key=lambda constraint: str(constraint["name"]),
    )


def _model_indexes(table: Table) -> list[_IndexContract]:
    """非一意索引を manifest の索引契約へ変換する。"""
    contracts: list[_IndexContract] = []
    for index in table.indexes:
        if index.unique:
            continue
        if not isinstance(index.name, str):
            raise AssertionError(f"索引名が空である: {table.name}")
        contracts.append(
            {
                "name": index.name,
                "columns": _index_columns(index),
                "predicate": _index_predicate(index),
                "purpose": str(index.info["purpose"]),
            }
        )
    return sorted(contracts, key=lambda index: index["name"])


def _index_columns(index: Index) -> list[str]:
    """索引の列順と降順指定を manifest の形へ変換する。"""
    columns: list[str] = []
    for expression in index.expressions:
        if isinstance(expression, Column):
            columns.append(expression.name)
            continue
        if (
            isinstance(expression, UnaryExpression)
            and expression.modifier is operators.desc_op
            and isinstance(expression.element, Column)
        ):
            columns.append(f"{expression.element.name} DESC")
            continue
        raise AssertionError(f"未対応の索引式: {index.name}: {expression}")
    return columns


def _model_lifecycle(model: Any) -> dict[str, str]:
    """モデルのライフサイクル 3 軸を manifest の形へ変換する。"""
    return {
        "deletion": model.lifecycle.deletion.value,
        "append_mode": model.lifecycle.append_mode.value,
        "migration_retirement": model.lifecycle.migration_retirement.value,
    }


def _model_immutability(model: Any) -> dict[str, object]:
    """モデルの不変列マトリクスを比較用に正規化する。"""
    return {
        "protected_columns": sorted(model.immutability.protected_columns),
        "allowed_update_columns": sorted(model.immutability.allowed_update_columns),
        "conditional_update_columns": sorted(
            model.immutability.conditional_update_columns
        ),
        "coverage": model.immutability.coverage.value,
        "unclassified_handoff": model.immutability.unclassified_handoff,
    }


def test_tenant_models_match_manifest_contracts() -> None:
    """23 表の models が FK 以外の manifest 契約と exact-set 一致する。"""
    manifest_tables = _load_manifest_tables()

    for table_name, model in _MODEL_CLASSES.items():
        manifest = manifest_tables[table_name]
        table = model.__table__

        assert _model_columns(table) == sorted(
            manifest["columns"], key=lambda column: column["name"]
        )
        assert {
            str(check.sqltext)
            for check in table.constraints
            if isinstance(check, CheckConstraint)
        } == set(manifest["checks"])
        assert _model_unique_constraints(table) == _manifest_unique_constraints(
            manifest
        )
        assert _model_indexes(table) == sorted(
            manifest["indexes"], key=lambda index: index["name"]
        )
        assert _model_lifecycle(model) == manifest["lifecycle"]
        assert _model_immutability(model) == {
            key: sorted(value) if isinstance(value, list) else value
            for key, value in manifest["immutability"].items()
        }
        assert set(table.columns.keys()).isdisjoint(manifest["forbidden_columns"])


def test_step_six_uniqueness_and_uniform_number_contract() -> None:
    """チームと選手にステップ 6 固有の一意性だけがあることを検査する。"""
    team_uniques = _model_unique_constraints(cast(Table, TeamRecord.__table__))
    player_uniques = _model_unique_constraints(cast(Table, Player.__table__))

    assert {
        "name": "uq_team_records_self",
        "kind": "UNIQUE INDEX",
        "columns": ["tenant_id"],
        "predicate": "kind = 'self'",
        "roles": ["business_unique"],
    } in team_uniques
    assert all("name" not in constraint["columns"] for constraint in team_uniques)
    assert player_uniques == [
        {
            "name": "pk_players",
            "kind": "PRIMARY KEY",
            "columns": ["tenant_id", "id"],
            "predicate": None,
            "roles": ["fk_target", "primary_key"],
        }
    ]
    uniform_number = Player.__table__.columns["uniform_number"]
    assert isinstance(uniform_number.type, Text)


def test_pdf_export_records_have_no_deletion_or_migration_columns() -> None:
    """追記専用の PDF 出力実績に削除・退役・取り込み列が無いと示す。"""
    columns = set(PdfExportRecord.__table__.columns.keys())

    assert columns.isdisjoint(
        {
            "deleted_at",
            "disabled_at",
            "discarded_at",
            "ended_at",
            "hidden_at",
            "import_batch_id",
            "retired_at",
            "trashed_at",
        }
    )


def test_vocabulary_layers_have_no_deletion_or_migration_columns() -> None:
    """語彙3層に削除・退役・取り込み列が無いと示す。"""
    forbidden = {
        "deleted_at",
        "discarded_at",
        "ended_at",
        "hidden_at",
        "import_batch_id",
        "retired_at",
        "trashed_at",
    }

    for model in (SystemVocabulary, AdminVocabulary, TenantVocabulary):
        assert set(model.__table__.columns.keys()).isdisjoint(forbidden)


def test_vocabulary_migration_contains_no_seed_data() -> None:
    """語彙 migration が参照値を投入する DML を含まないと示す。"""
    source = _VOCABULARY_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source


def _foreign_key_graph() -> dict[str, set[str]]:
    """モデルの FK を参照元から参照先へのグラフに変換する。"""
    return {
        table_name: {
            constraint.referred_table.name
            for constraint in model.__table__.foreign_key_constraints
        }
        for table_name, model in _MODEL_CLASSES.items()
    }


def _reachable_tables(graph: dict[str, set[str]], source: str) -> set[str]:
    """指定した表から FK を辿って到達できる表を返す。"""
    reachable: set[str] = set()
    frontier = list(graph.get(source, set()))
    while frontier:
        target = frontier.pop()
        if target in reachable:
            continue
        reachable.add(target)
        frontier.extend(graph.get(target, set()) - reachable)
    return reachable


def test_admin_authentication_has_no_foreign_key_path_to_tenants() -> None:
    """管理者資格情報・セッションが FK グラフ上もテナントと別系統である。"""
    graph = _foreign_key_graph()

    assert _reachable_tables(graph, "admin_credentials") == set()
    assert _reachable_tables(graph, "admin_sessions") == {"admin_credentials"}
    assert "tenants" in _reachable_tables(graph, "tenant_auth_subjects")
    assert "tenants" in _reachable_tables(graph, "tenant_credentials")


def test_authentication_models_exclude_all_manifest_forbidden_columns() -> None:
    """認証5表に平文・可逆保持・主体混同につながる禁止列が無い。"""
    manifest_tables = _load_manifest_tables()
    for table_name in (
        "tenant_auth_subjects",
        "tenant_credentials",
        "admin_credentials",
        "admin_sessions",
        "tenant_tokens",
    ):
        columns = set(_MODEL_CLASSES[table_name].__table__.columns.keys())
        assert columns.isdisjoint(manifest_tables[table_name]["forbidden_columns"])


def test_authentication_migration_contains_no_seed_data() -> None:
    """認証 migration が資格情報を投入する DML を含まないと示す。"""
    source = _AUTH_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source


def test_admin_operation_logs_have_no_deletion_or_retention_columns() -> None:
    """管理者操作ログに削除・保持期限・移行用の列が無いと示す。"""
    columns = set(AdminOperationLog.__table__.columns.keys())

    assert columns.isdisjoint(
        {
            "deleted_at",
            "hidden_at",
            "import_batch_id",
            "retention_deadline",
            "retired_at",
            "trashed_at",
        }
    )


def test_admin_operation_log_targets_are_independently_optional() -> None:
    """管理者操作ログのテナント・グループ対象がともに任意だと示す。"""
    table = AdminOperationLog.__table__

    assert table.columns["tenant_id"].nullable
    assert table.columns["group_id"].nullable
    assert not table.columns["target"].nullable


def test_admin_operation_log_migration_contains_no_dml() -> None:
    """管理者操作ログ migration が DML を含まないと示す。"""
    source = _ADMIN_OPERATION_LOG_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source


def test_player_move_and_rate_limit_optional_columns_match_scope() -> None:
    """移動記録の任意列と認証前レート制限の非テナント性を示す。"""
    move_columns = PlayerMoveRecord.__table__.columns
    rate_limit_columns = set(RateLimitCounter.__table__.columns.keys())

    assert move_columns["medical_note_version_id"].nullable
    assert "tenant_id" not in rate_limit_columns
    assert "import_batch_id" not in rate_limit_columns
    assert "retired_at" not in rate_limit_columns
    assert RateLimitCounter.__table__.columns["locked_until"].nullable


def test_player_merge_migration_contains_no_dml() -> None:
    """選手統合・移動・レート制限 migration が DML を含まないと示す。"""
    source = _PLAYER_MERGE_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source


def test_group_control_tables_have_only_membership_tenant_column() -> None:
    """グループ制御資源では参加行だけが tenant_id を持つと示す。"""
    assert "tenant_id" not in AnalysisGroup.__table__.columns
    assert "tenant_id" in GroupMembership.__table__.columns
    assert "tenant_id" not in SharingGrant.__table__.columns
    assert "tenant_id" not in GroupInvitation.__table__.columns


def test_analysis_group_migration_contains_no_dml() -> None:
    """グループ migration が DML を含まないと示す。"""
    source = _ANALYSIS_GROUP_MIGRATION_PATH.read_text(encoding="utf-8").upper()

    assert "INSERT" not in source
    assert "BULK_INSERT" not in source
