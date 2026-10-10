"""選手・対戦相手の閉じた operation と単一文の実行を検査する。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    Text,
    Uuid,
    bindparam,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.sql.selectable import Alias, Select
from test_authz_tenant_context import make_tenant_context

from pitchlog.api.schemas.roster import ROSTER_PAGE_SIZE_MAX
from pitchlog.authz.capability_registration import validate_capability_registrations
from pitchlog.db.game_state.models import Game
from pitchlog.db.tenant_isolation.models import Player, TeamRecord
from pitchlog.repositories import base as repository_base
from pitchlog.repositories import roster as roster_module
from pitchlog.repositories import transaction as transaction_module
from pitchlog.repositories.base import TenantRepositoryBase
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import (
    GameTeamLinkReadToken,
    PlayerCreateToken,
    PlayerReadToken,
    PlayerRosterLabelUpdateToken,
    PlayerRosterStatusUpdateToken,
    PlayerUpdateToken,
    RosterReferenceUnavailable,
    TeamRecordCreateToken,
    TeamRecordDeleteToken,
    TeamRecordReadToken,
    TeamRecordUpdateToken,
    create_roster_player,
    player_read_statement,
    player_update_statement,
    team_record_read_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_ROOT = Path(__file__).resolve().parents[2]
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000101")
_PLAYER_ID = UUID("00000000-0000-0000-0000-000000000102")
_TEAM_ID = UUID("00000000-0000-0000-0000-000000000103")
_PLAYER_ALIAS = cast(Alias, cast(Table, Player.__table__).alias("unscoped_players"))
_PLAYER_TARGET_ALIAS = cast(
    Alias, cast(Table, Player.__table__).alias("unscoped_target_players")
)


@pytest.mark.parametrize(
    ("constraint_name", "sqlstate", "hidden"),
    [
        ("fk_players_team", "23503", True),
        ("fk_players_roster_status", "23503", True),
        ("fk_players_roster_label", "23503", True),
        ("fk_players_other", "23503", False),
        ("pk_players", "23505", False),
        ("players_roster_status_category_check", "23514", False),
        ("fk_players_team", "23514", False),
    ],
)
def test_create_player_maps_only_known_reference_fks_to_closed_rejection(
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str,
    sqlstate: str,
    hidden: bool,
) -> None:
    """既知の参照先 FK だけを 404 用の拒否へ写す。"""
    context = make_tenant_context(_TENANT_ID)
    operation = PlayerCreateToken(
        id=_PLAYER_ID,
        team_record_id=_TEAM_ID,
        name="甲",
        roster_status_key="active",
    )

    class DatabaseFailure(Exception):
        def __init__(self) -> None:
            self.sqlstate = sqlstate
            self.diag = SimpleNamespace(constraint_name=constraint_name)

    failure = IntegrityError("INSERT", {}, DatabaseFailure())

    class FailedScope:
        def run(self, _operation: TenantOperationToken) -> TenantOperationResult:
            raise failure

    @contextmanager
    def failed_scope(_context: TenantContext) -> Iterator[FailedScope]:
        yield FailedScope()

    monkeypatch.setattr(transaction_module, "tenant_transaction_scope", failed_scope)
    if hidden:
        with pytest.raises(RosterReferenceUnavailable):
            create_roster_player(context, operation)
    else:
        with pytest.raises(IntegrityError) as caught:
            create_roster_player(context, operation)
        assert caught.value is failure


def test_player_reference_fks_match_model() -> None:
    """404 へ写す制約名が ORM の参照先 FK と一致することを確認する。"""
    table = cast(Table, Player.__table__)
    assert {constraint.name for constraint in table.foreign_key_constraints} == {
        "fk_players_team",
        "fk_players_roster_status",
        "fk_players_roster_label",
    }


def _replace_built_statement(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    statement: ClauseElement,
) -> None:
    """登録文の組み立て入口だけを負例の文へ差し替える。"""
    original = roster_module._build_roster_statement

    def replacement(
        requested_kind: str,
        operation: PlayerReadToken
        | PlayerUpdateToken
        | TeamRecordReadToken
        | None = None,
    ) -> ClauseElement:
        if requested_kind == kind:
            return statement
        return original(requested_kind, operation)

    monkeypatch.setattr(roster_module, "_build_roster_statement", replacement)


_PLAYER_CTE = select(Player.__table__.c.id).cte("unscoped_players")


@dataclass(frozen=True)
class _Registration:
    """生成した文を capability 検査器へ渡す。"""

    capability_id: str
    statement: ClauseElement


class _ReadResult:
    """1 行を返す読み取り結果。"""

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        """DB 行を 1 件だけ返す。"""
        return iter(((_PLAYER_ID, "選手"),))


class _WriteResult:
    """1 行を変更した書き込み結果。"""

    rowcount = 1


class _RecordingSession:
    """業務文の発行回数と束縛値を記録する。"""

    def __init__(self) -> None:
        """空の発行記録を作る。"""
        self.calls: list[tuple[ClauseElement, dict[str, object]]] = []

    def execute(
        self, statement: ClauseElement, parameters: dict[str, object]
    ) -> _ReadResult | _WriteResult:
        """文を記録し、文種に応じた結果を返す。"""
        self.calls.append((statement, parameters))
        if isinstance(statement, Select):
            return _ReadResult()
        return _WriteResult()


class _Repository(TenantRepositoryBase):
    """外部の供給方式を決めずに実行器を試す具象。"""

    def __init__(self, session: _RecordingSession) -> None:
        """テスト用の記録器を保持する。"""
        self._recording_session = session

    @property
    def _session(self) -> Session:
        """記録器を実行器へ渡す。"""
        return cast(Session, self._recording_session)


@contextmanager
def _transaction_stub(session: Session, context: TenantContext) -> Iterator[None]:
    """束縛の実 DB 検査を置き換え、業務文だけを数える。"""
    del session, context
    yield


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingSession:
    """テナント束縛後の業務文を記録する。"""
    monkeypatch.setattr(repository_base, "_tenant_transaction", _transaction_stub)
    return _RecordingSession()


def _run_transaction_token(
    context: TenantContext,
    recorder: _RecordingSession,
    operation: (
        PlayerReadToken
        | PlayerCreateToken
        | PlayerUpdateToken
        | TeamRecordReadToken
        | TeamRecordCreateToken
        | TeamRecordUpdateToken
        | TeamRecordDeleteToken
        | GameTeamLinkReadToken
    ),
) -> TenantOperationResult:
    """実 DB なしで run の登録文準備と実行を通す。"""
    state_key = object()
    transaction_module._TRANSACTION_RUNTIMES[state_key] = (
        cast(Session, recorder),
        ExitStack(),
    )
    handle = transaction_module._TenantTransaction(
        context,
        state_key,
        context.tenant_id,
        context._integrity_proof,
        transaction_module._HANDLE_CREATION_TOKEN,
    )
    try:
        return handle.run(operation)
    finally:
        handle._expire()
        del transaction_module._TRANSACTION_RUNTIMES[state_key]


@pytest.mark.parametrize(
    "operation",
    (
        PlayerReadToken(limit=2, record_id=_PLAYER_ID),
        PlayerCreateToken(_PLAYER_ID, _TEAM_ID, "選手", "active"),
        PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
        TeamRecordReadToken(limit=2, record_id=_TEAM_ID),
        TeamRecordCreateToken(_TEAM_ID, "対戦相手"),
        TeamRecordUpdateToken(_TEAM_ID, "改名"),
        TeamRecordDeleteToken(_TEAM_ID, datetime(2026, 10, 10, tzinfo=timezone.utc)),
        GameTeamLinkReadToken(_TEAM_ID),
    ),
)
def test_all_roster_tokens_use_prepared_statement_in_both_paths(
    recorder: _RecordingSession,
    operation: (
        PlayerReadToken
        | PlayerCreateToken
        | PlayerUpdateToken
        | TeamRecordReadToken
        | TeamRecordCreateToken
        | TeamRecordUpdateToken
        | TeamRecordDeleteToken
        | GameTeamLinkReadToken
    ),
) -> None:
    """リポジトリとトランザクションで 8 形の同じ準備結果を実行する。"""
    context = make_tenant_context(_TENANT_ID)
    transaction_recorder = _RecordingSession()
    repository_result = _Repository(recorder).execute(context, operation)
    transaction_result = _run_transaction_token(
        context, transaction_recorder, operation
    )
    assert repository_result == transaction_result
    assert len(recorder.calls) == len(transaction_recorder.calls) == 1
    repository_statement, repository_parameters = recorder.calls[0]
    transaction_statement, transaction_parameters = transaction_recorder.calls[0]
    assert str(repository_statement) == str(transaction_statement)
    assert repository_parameters == transaction_parameters
    tenant_bind = (
        "where_tenant_id"
        if isinstance(
            operation, (PlayerUpdateToken, TeamRecordUpdateToken, TeamRecordDeleteToken)
        )
        else "tenant_id"
    )
    assert repository_parameters[tenant_bind] == _TENANT_ID
    if isinstance(
        operation, (PlayerUpdateToken, TeamRecordUpdateToken, TeamRecordDeleteToken)
    ):
        assert repository_parameters["where_id"] == operation.id
    if isinstance(operation, (PlayerReadToken, TeamRecordReadToken)):
        assert repository_parameters["limit"] == operation.limit + 1
        if operation.record_id is not None:
            assert repository_parameters["record_id"] == operation.record_id
    if isinstance(operation, (TeamRecordReadToken, TeamRecordCreateToken)):
        assert repository_parameters["kind"] == "opponent"
    if isinstance(operation, (TeamRecordUpdateToken, TeamRecordDeleteToken)):
        assert repository_parameters["where_kind"] == "opponent"


@pytest.mark.parametrize(
    "operation",
    (
        PlayerReadToken(limit=2, record_id=_PLAYER_ID),
        PlayerCreateToken(_PLAYER_ID, _TEAM_ID, "選手", "active"),
        PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
        TeamRecordReadToken(limit=2, record_id=_TEAM_ID),
        TeamRecordCreateToken(_TEAM_ID, "対戦相手"),
        TeamRecordUpdateToken(_TEAM_ID, "改名"),
        TeamRecordDeleteToken(_TEAM_ID, datetime(2026, 10, 10, tzinfo=timezone.utc)),
        GameTeamLinkReadToken(_TEAM_ID),
    ),
    ids=(
        "player-read",
        "player-create",
        "player-update",
        "team-read",
        "team-create",
        "team-update",
        "team-delete",
        "game-team-link-read",
    ),
)
def test_prepared_tokens_compile_with_session_column_keys(
    operation: TenantOperationToken,
) -> None:
    """8 形の準備結果を実 Session と同じ列キーでコンパイルする。"""
    statement, parameters = repository_base._prepare_operation(operation, _TENANT_ID)
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        column_keys=list(parameters),
    )
    assert str(compiled)


def test_sqlite_session_executes_both_prepared_updates() -> None:
    """両表の UPDATE を実 Session で実行し、対象テナントだけを変更する。"""
    other_tenant = UUID("00000000-0000-0000-0000-000000000104")
    metadata = MetaData()
    players = Table(
        "players",
        metadata,
        Column("tenant_id", Uuid(as_uuid=True), primary_key=True),
        Column("id", Uuid(as_uuid=True), primary_key=True),
        Column("name", Text),
    )
    teams = Table(
        "team_records",
        metadata,
        Column("tenant_id", Uuid(as_uuid=True), primary_key=True),
        Column("id", Uuid(as_uuid=True), primary_key=True),
        Column("kind", Text),
        Column("name", Text),
        Column("hidden_at", Text),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        metadata.create_all(engine)
        with Session(engine) as session:
            session.execute(
                insert(players),
                (
                    {"tenant_id": _TENANT_ID, "id": _PLAYER_ID, "name": "旧選手"},
                    {"tenant_id": other_tenant, "id": _PLAYER_ID, "name": "他選手"},
                ),
            )
            session.execute(
                insert(teams),
                (
                    {
                        "tenant_id": _TENANT_ID,
                        "id": _TEAM_ID,
                        "kind": "opponent",
                        "name": "旧対戦相手",
                    },
                    {
                        "tenant_id": other_tenant,
                        "id": _TEAM_ID,
                        "kind": "opponent",
                        "name": "他対戦相手",
                    },
                ),
            )
            for operation in (
                PlayerUpdateToken(_PLAYER_ID, (("name", "新選手"),)),
                TeamRecordUpdateToken(_TEAM_ID, "新対戦相手"),
            ):
                statement, parameters = repository_base._prepare_operation(
                    operation, _TENANT_ID
                )
                session.execute(statement, parameters)
            assert (
                session.execute(
                    select(players.c.name).where(
                        players.c.tenant_id == _TENANT_ID, players.c.id == _PLAYER_ID
                    )
                ).scalar_one()
                == "新選手"
            )
            assert (
                session.execute(
                    select(players.c.name).where(
                        players.c.tenant_id == other_tenant, players.c.id == _PLAYER_ID
                    )
                ).scalar_one()
                == "他選手"
            )
            assert (
                session.execute(
                    select(teams.c.name).where(
                        teams.c.tenant_id == _TENANT_ID, teams.c.id == _TEAM_ID
                    )
                ).scalar_one()
                == "新対戦相手"
            )
            assert (
                session.execute(
                    select(teams.c.name).where(
                        teams.c.tenant_id == other_tenant, teams.c.id == _TEAM_ID
                    )
                ).scalar_one()
                == "他対戦相手"
            )
            statement, parameters = repository_base._prepare_operation(
                TeamRecordDeleteToken(
                    _TEAM_ID, datetime(2026, 10, 10, tzinfo=timezone.utc)
                ),
                _TENANT_ID,
            )
            assert getattr(session.execute(statement, parameters), "rowcount") == 1
            assert (
                session.execute(
                    select(teams.c.hidden_at).where(
                        teams.c.tenant_id == _TENANT_ID, teams.c.id == _TEAM_ID
                    )
                ).scalar_one()
                is not None
            )
    finally:
        engine.dispose()


def test_status_update_counts_changes_and_label_preserves_status() -> None:
    """区分の差分だけを更新件数とし、ラベル専用操作は区分を保つ。"""
    other_tenant = UUID("00000000-0000-0000-0000-000000000104")
    metadata = MetaData()
    players = Table(
        "players",
        metadata,
        Column("tenant_id", Uuid(as_uuid=True), primary_key=True),
        Column("id", Uuid(as_uuid=True), primary_key=True),
        Column("roster_status_key", Text),
        Column("roster_label_key", Text),
        Column("hidden_at", Text),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        metadata.create_all(engine)
        with Session(engine) as session:
            session.execute(
                insert(players),
                (
                    {
                        "tenant_id": _TENANT_ID,
                        "id": _PLAYER_ID,
                        "roster_status_key": "active",
                        "roster_label_key": None,
                    },
                    {
                        "tenant_id": other_tenant,
                        "id": _PLAYER_ID,
                        "roster_status_key": "active",
                        "roster_label_key": None,
                    },
                ),
            )
            changed = PlayerRosterStatusUpdateToken(
                _PLAYER_ID, "other", "OB", update_label=True
            )
            statement, parameters = repository_base._prepare_operation(
                changed, _TENANT_ID
            )
            assert getattr(session.execute(statement, parameters), "rowcount") == 1
            assert getattr(session.execute(statement, parameters), "rowcount") == 0

            label_only = PlayerRosterLabelUpdateToken(_PLAYER_ID, "その他")
            statement, parameters = repository_base._prepare_operation(
                label_only, _TENANT_ID
            )
            assert getattr(session.execute(statement, parameters), "rowcount") == 1
            rows = session.execute(
                select(
                    players.c.tenant_id,
                    players.c.roster_status_key,
                    players.c.roster_label_key,
                ).where(players.c.id == _PLAYER_ID)
            ).all()
            assert set(rows) == {
                (_TENANT_ID, "other", "その他"),
                (other_tenant, "active", None),
            }
    finally:
        engine.dispose()


def test_registered_statement_variants_match_catalog() -> None:
    """フィルタと PATCH の組み合わせも単一表の許可済み操作に閉じる。"""
    catalog: dict[str, Any] = json.loads(
        (_ROOT / "contracts/authz/product/capability-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    variants = (
        _Registration("CAP:players:read", player_read_statement(PlayerReadToken(200))),
        _Registration(
            "CAP:players:read",
            player_read_statement(
                PlayerReadToken(
                    limit=200,
                    record_id=_PLAYER_ID,
                    team_record_id=_TEAM_ID,
                    roster_status_key="active",
                    cursor_team_record_id=_TEAM_ID,
                    cursor_id=_PLAYER_ID,
                    include_hidden=True,
                )
            ),
        ),
        _Registration(
            "CAP:team_records:read",
            team_record_read_statement(TeamRecordReadToken(200)),
        ),
        _Registration(
            "CAP:team_records:read",
            team_record_read_statement(
                TeamRecordReadToken(
                    limit=200,
                    record_id=_TEAM_ID,
                    cursor_id=_TEAM_ID,
                    include_hidden=True,
                )
            ),
        ),
        _Registration(
            "CAP:players:update",
            player_update_statement(
                PlayerUpdateToken(
                    _PLAYER_ID,
                    (("name", "更新"), ("throws", None)),
                )
            ),
        ),
    )
    for variant in variants:
        validate_capability_registrations(catalog=catalog, registrations=(variant,))
    catalog_rows = {
        row["capability_id"]: (row["table_id"], row["operation"])
        for row in catalog["capabilities"]
    }
    for registration in repository_base._OPERATION_REGISTRY.values():
        prefix, table_id, operation = registration.capability_id.split(":")
        assert prefix == "CAP"
        assert catalog_rows[registration.capability_id] == (table_id, operation)
        assert cast(Table, registration.tenant_column.table).name == table_id


@pytest.mark.parametrize(
    ("kind", "operation"),
    (
        ("player_read", TeamRecordReadToken(1)),
        ("player_create", PlayerReadToken(1)),
        ("player_update", PlayerReadToken(1)),
        ("team_read", PlayerReadToken(1)),
        ("team_create", TeamRecordReadToken(1)),
        ("team_update", PlayerUpdateToken(_PLAYER_ID, (("name", "更新"),))),
    ),
)
def test_builder_rejects_mismatched_kind_and_token(
    kind: str,
    operation: PlayerReadToken | PlayerUpdateToken | TeamRecordReadToken,
) -> None:
    """同じ表や操作に見える token の取り違えも文を作る前に拒否する。"""
    with pytest.raises(ValueError):
        roster_module._build_roster_statement(kind, operation)


def test_builder_rejects_unknown_kind() -> None:
    """未知の文種を既定の更新として扱わない。"""
    with pytest.raises(ValueError, match="未知の roster 文"):
        roster_module._build_roster_statement("unknown", None)


def test_builder_preserves_registered_and_prepared_sql_shapes() -> None:
    """是正前の登録文 6 件と条件付き文 5 件の SQL 形状を固定する。"""
    statements = {
        kind: roster_module._build_roster_statement(kind, None)
        for kind in (
            "player_read",
            "player_create",
            "player_update",
            "team_read",
            "team_create",
            "team_update",
        )
    }
    statements.update(
        player_read_dynamic=player_read_statement(PlayerReadToken(200)),
        player_read_filtered=player_read_statement(
            PlayerReadToken(
                200,
                record_id=_PLAYER_ID,
                team_record_id=_TEAM_ID,
                roster_status_key="active",
                cursor_team_record_id=_TEAM_ID,
                cursor_id=_PLAYER_ID,
                include_hidden=True,
            )
        ),
        team_read_dynamic=team_record_read_statement(TeamRecordReadToken(200)),
        team_read_filtered=team_record_read_statement(
            TeamRecordReadToken(
                200, record_id=_TEAM_ID, cursor_id=_TEAM_ID, include_hidden=True
            )
        ),
        player_update_dynamic=player_update_statement(
            PlayerUpdateToken(
                _PLAYER_ID,
                (("name", "更新"), ("throws", None)),
            )
        ),
    )
    assert {kind: str(statement) for kind, statement in statements.items()} == {
        "player_read": (
            "SELECT players.id, players.team_record_id, players.name, "
            "players.throws, players.bats, players.uniform_number, "
            "players.roster_status_key, players.roster_label_key, "
            "players.hidden_at \n"
            "FROM players \n"
            "WHERE players.tenant_id = :tenant_id AND (:record_id IS NULL OR "
            "players.id = :record_id) AND (:team_record_id IS NULL OR "
            "players.team_record_id = :team_record_id) AND (:roster_status_key "
            "IS NULL OR players.roster_status_key = :roster_status_key) AND "
            "(:include_hidden IS true OR players.hidden_at IS NULL) AND "
            "(:cursor_team_record_id IS NULL OR players.team_record_id > "
            ":cursor_team_record_id OR players.team_record_id = "
            ":cursor_team_record_id AND players.id > :cursor_id) ORDER BY "
            "players.team_record_id, players.id\n"
            " LIMIT :limit"
        ),
        "player_create": (
            "INSERT INTO players (id, team_record_id, name, throws, bats, "
            "uniform_number, roster_status_key, roster_label_key, tenant_id) "
            "VALUES (:id, :team_record_id, :name, :throws, :bats, "
            ":uniform_number, :roster_status_key, :roster_label_key, :tenant_id)"
        ),
        "player_update": (
            "UPDATE players SET name=:value_name WHERE players.tenant_id = "
            ":where_tenant_id AND players.id = :where_id"
        ),
        "team_read": (
            "SELECT team_records.id, team_records.kind, team_records.name, "
            "team_records.hidden_at \n"
            "FROM team_records \n"
            "WHERE team_records.tenant_id = :tenant_id AND team_records.kind = "
            ":kind AND (:record_id IS NULL OR team_records.id = :record_id) AND "
            "(:include_hidden IS true OR team_records.hidden_at IS NULL) AND "
            "(:cursor_id IS NULL OR team_records.id > :cursor_id) ORDER BY "
            "team_records.id\n"
            " LIMIT :limit"
        ),
        "team_create": (
            "INSERT INTO team_records (id, kind, name, tenant_id) VALUES (:id, "
            ":kind, :name, :tenant_id)"
        ),
        "team_update": (
            "UPDATE team_records SET name=:name WHERE team_records.tenant_id = "
            ":where_tenant_id AND team_records.id = :where_id AND "
            "team_records.kind = :where_kind AND team_records.hidden_at IS NULL"
        ),
        "player_read_dynamic": (
            "SELECT players.id, players.team_record_id, players.name, "
            "players.throws, players.bats, players.uniform_number, "
            "players.roster_status_key, players.roster_label_key, "
            "players.hidden_at \n"
            "FROM players \n"
            "WHERE players.tenant_id = :tenant_id AND players.hidden_at IS NULL "
            "ORDER BY players.team_record_id, players.id\n"
            " LIMIT :limit"
        ),
        "player_read_filtered": (
            "SELECT players.id, players.team_record_id, players.name, "
            "players.throws, players.bats, players.uniform_number, "
            "players.roster_status_key, players.roster_label_key, "
            "players.hidden_at \n"
            "FROM players \n"
            "WHERE players.tenant_id = :tenant_id AND players.id = :record_id "
            "AND players.team_record_id = :team_record_id AND "
            "players.roster_status_key = :roster_status_key AND "
            "(players.team_record_id > :cursor_team_record_id OR "
            "players.team_record_id = :cursor_team_record_id AND players.id > "
            ":cursor_id) ORDER BY players.team_record_id, players.id\n"
            " LIMIT :limit"
        ),
        "team_read_dynamic": (
            "SELECT team_records.id, team_records.kind, team_records.name, "
            "team_records.hidden_at \n"
            "FROM team_records \n"
            "WHERE team_records.tenant_id = :tenant_id AND team_records.kind = "
            ":kind AND team_records.hidden_at IS NULL ORDER BY team_records.id\n"
            " LIMIT :limit"
        ),
        "team_read_filtered": (
            "SELECT team_records.id, team_records.kind, team_records.name, "
            "team_records.hidden_at \n"
            "FROM team_records \n"
            "WHERE team_records.tenant_id = :tenant_id AND team_records.kind = "
            ":kind AND team_records.id = :record_id AND team_records.id > "
            ":cursor_id ORDER BY team_records.id\n"
            " LIMIT :limit"
        ),
        "player_update_dynamic": (
            "UPDATE players SET name=:value_name, throws=:value_throws WHERE "
            "players.tenant_id = :where_tenant_id AND players.id = :where_id"
        ),
    }


def test_player_patch_rejects_unclassified_and_invalid_columns() -> None:
    """所属変更・空変更・重複・非 nullable の NULL を拒否する。"""
    for changes in (
        (),
        (("team_record_id", str(_TEAM_ID)),),
        (("name", "甲"), ("name", "乙")),
        (("name", None),),
        (("roster_status_key", None),),
        (("roster_status_key", "other"),),
        (("roster_label_key", "label"),),
        (("throws", "switch"),),
        (("bats", "switch"),),
    ):
        with pytest.raises(ValueError):
            PlayerUpdateToken(_PLAYER_ID, changes)
    with pytest.raises(ValueError):
        PlayerUpdateToken(_PLAYER_ID, cast(Any, [("name", "可変")]))


def test_create_and_update_execute_one_business_statement(
    recorder: _RecordingSession,
) -> None:
    """作成と複数列 PATCH が 1 操作 1 表 1 文を発行する。"""
    del recorder
    context = make_tenant_context(_TENANT_ID)
    operations = (
        TeamRecordCreateToken(_TEAM_ID, "対戦相手"),
        TeamRecordUpdateToken(_TEAM_ID, "改名"),
        PlayerCreateToken(_PLAYER_ID, _TEAM_ID, "選手", "active"),
        PlayerUpdateToken(
            _PLAYER_ID,
            (("name", "改名"), ("throws", None)),
        ),
    )
    calls: list[tuple[ClauseElement, dict[str, object]]] = []
    for operation in operations:
        operation_recorder = _RecordingSession()
        repository = _Repository(operation_recorder)
        assert repository.execute(context, operation) == TenantOperationResult(
            rows=((1,),)
        )
        assert len(operation_recorder.calls) == 1
        statement, parameters = operation_recorder.calls[0]
        calls.append((statement, parameters))
        assert (
            parameters[
                "where_tenant_id" if isinstance(statement, Update) else "tenant_id"
            ]
            == _TENANT_ID
        )
        assert not isinstance(statement, Select)
    assert calls[0][1]["kind"] == "opponent"
    assert calls[1][1]["where_kind"] == "opponent"
    assert calls[3][1]["value_throws"] is None


def test_reads_are_paged_and_omit_tenant_from_rows(recorder: _RecordingSession) -> None:
    """取得は limit+1 件を要求し、返り値は不変な行だけに閉じる。"""
    repository = _Repository(recorder)
    context = make_tenant_context(_TENANT_ID)
    result = repository.execute(context, PlayerReadToken(limit=200))
    assert result.rows == ((_PLAYER_ID, "選手"),)
    assert recorder.calls[-1][1]["limit"] == 201
    team_recorder = _RecordingSession()
    _Repository(team_recorder).execute(context, TeamRecordReadToken(limit=1))
    assert team_recorder.calls[-1][1]["kind"] == "opponent"
    assert team_recorder.calls[-1][1]["limit"] == 2
    with pytest.raises(ValueError):
        PlayerReadToken(limit=201)
    with pytest.raises(ValueError):
        TeamRecordReadToken(limit=0)


def test_same_number_read_uses_bounded_database_predicates() -> None:
    """同番号警告は tenant・現役・未削除・本人除外を DB 側で絞る。"""
    token = PlayerReadToken(
        limit=ROSTER_PAGE_SIZE_MAX,
        roster_status_key="active",
        uniform_number="7",
        exclude_id=_PLAYER_ID,
    )
    statement, parameters = repository_base._prepare_operation(token, _TENANT_ID)
    sql = str(statement)
    assert "players.tenant_id = :tenant_id" in sql
    assert "players.hidden_at IS NULL" in sql
    assert "players.roster_status_key = :roster_status_key" in sql
    assert "players.uniform_number = :uniform_number" in sql
    assert "players.id != :exclude_id" in sql
    assert "LIMIT :limit" in sql
    assert parameters["tenant_id"] == _TENANT_ID
    assert parameters["roster_status_key"] == "active"
    assert parameters["uniform_number"] == "7"
    assert parameters["exclude_id"] == _PLAYER_ID
    assert parameters["limit"] == ROSTER_PAGE_SIZE_MAX + 1


@pytest.mark.parametrize(
    ("builder_name", "operation", "statement"),
    (
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            select(Player.__table__.c.id),
        ),
        (
            "team_record_read_statement",
            TeamRecordReadToken(limit=1),
            select(TeamRecord.__table__.c.id),
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.id == bindparam("where_id"))
            .values(name=bindparam("value_name")),
        ),
    ),
)
def test_prepared_statement_without_tenant_predicate_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    builder_name: str,
    operation: PlayerReadToken | TeamRecordReadToken | PlayerUpdateToken,
    statement: ClauseElement,
) -> None:
    """動的な文からテナント条件が抜けた場合は業務文を発行しない。"""
    monkeypatch.setattr(roster_module, builder_name, lambda _: statement)
    with pytest.raises(repository_base._TenantOperationError):
        _Repository(recorder).execute(make_tenant_context(_TENANT_ID), operation)
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("builder_name", "operation", "statement"),
    (
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(Player.__table__.c.id == bindparam("where_id"))
            .where(TeamRecord.__table__.c.id == bindparam("other_id"))
            .values(name=bindparam("value_name")),
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, TeamRecord.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(TeamRecord.__table__.c.id == bindparam("where_id"))
            .values(name=bindparam("value_name")),
        ),
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            select(Player.__table__.c.id)
            .join(
                TeamRecord.__table__,
                Player.__table__.c.team_record_id == TeamRecord.__table__.c.id,
            )
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id")),
        ),
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            select(Player.__table__.c.id)
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id.in_(select(TeamRecord.__table__.c.id))),
        ),
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(Player.__table__.c.id == bindparam("where_id"))
            .values(name=bindparam("value_name")),
        ),
    ),
)
def test_prepared_statement_rejects_capability_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    builder_name: str,
    operation: PlayerReadToken | PlayerUpdateToken,
    statement: ClauseElement,
) -> None:
    """別表・複数表・異なる操作種別を業務文発行前に拒否する。"""
    monkeypatch.setattr(roster_module, builder_name, lambda _: statement)
    with pytest.raises(repository_base._TenantOperationError):
        _Repository(recorder).execute(make_tenant_context(_TENANT_ID), operation)
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("builder_name", "operation", "statement", "expected_error"),
    (
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            select(Player.__table__.c.id)
            .select_from(Player.__table__.alias("unscoped_players"))
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id")),
            "別名・結合・入れ子のFROM",
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(_PLAYER_TARGET_ALIAS)
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(Player.__table__.c.id == bindparam("where_id"))
            .values(name=bindparam("value_name")),
            "変更対象は実表",
        ),
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            select(Player.__table__.c.id)
            .select_from(_PLAYER_CTE)
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id")),
            "別名・結合・入れ子のFROM",
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(Player.__table__.c.id == bindparam("where_id"))
            .values(name=select(Player.__table__.c.name).scalar_subquery()),
            "別名・結合・入れ子のFROM",
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(Player.__table__.c.id == bindparam("where_id"))
            .where(_PLAYER_ALIAS.c.id == bindparam("other_id"))
            .values(name=bindparam("value_name")),
            "実表以外の列",
        ),
    ),
)
def test_prepared_statement_rejects_non_direct_from(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    builder_name: str,
    operation: PlayerReadToken | PlayerUpdateToken,
    statement: ClauseElement,
    expected_error: str,
) -> None:
    """同一表の別名・CTE・入れ子 SELECT を実行前に拒否する。"""
    monkeypatch.setattr(roster_module, builder_name, lambda _: statement)
    with pytest.raises(
        repository_base._TenantOperationError,
        match=expected_error,
    ):
        _Repository(recorder).execute(make_tenant_context(_TENANT_ID), operation)
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("operation", "statement_name", "statement"),
    (
        (
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            "player_update_statement",
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .values(name=bindparam("value_name")),
        ),
        (
            TeamRecordUpdateToken(_TEAM_ID, "改名"),
            "_TEAM_RECORD_UPDATE",
            update(cast(Table, TeamRecord.__table__))
            .where(TeamRecord.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(TeamRecord.__table__.c.kind == bindparam("where_kind"))
            .values(name=bindparam("name")),
        ),
    ),
)
def test_prepared_update_requires_target_id(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    operation: PlayerUpdateToken | TeamRecordUpdateToken,
    statement_name: str,
    statement: ClauseElement,
) -> None:
    """選手・対戦相手の全件 UPDATE を業務文発行前に拒否する。"""
    if statement_name == "player_update_statement":
        monkeypatch.setattr(roster_module, statement_name, lambda _: statement)
    else:
        _replace_built_statement(monkeypatch, "team_update", statement)
    with pytest.raises(repository_base._TenantOperationError, match="id = :where_id"):
        _Repository(recorder).execute(make_tenant_context(_TENANT_ID), operation)
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("operation", "kind"),
    (
        (PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)), "player_update"),
        (TeamRecordUpdateToken(_TEAM_ID, "改名"), "team_update"),
    ),
)
@pytest.mark.parametrize(
    ("tenant_bind", "id_bind", "expected_error"),
    (
        ("tenant_id", "where_id", "tenant_id = :where_tenant_id"),
        ("where_tenant_id", "id", "id = :where_id"),
        (None, "where_id", "tenant_id = :where_tenant_id"),
        ("where_tenant_id", None, "id = :where_id"),
    ),
)
def test_update_rejects_old_or_missing_where_bindings(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    operation: PlayerUpdateToken | TeamRecordUpdateToken,
    kind: str,
    tenant_bind: str | None,
    id_bind: str | None,
    expected_error: str,
) -> None:
    """旧名または欠けたテナント・行条件を両表とも実行前に拒否する。"""
    table = cast(
        Table,
        Player.__table__ if kind == "player_update" else TeamRecord.__table__,
    )
    value_bind = "value_name" if kind == "player_update" else "name"
    statement = update(table).values(name=bindparam(value_bind))
    if tenant_bind is not None:
        statement = statement.where(table.c.tenant_id == bindparam(tenant_bind))
    if id_bind is not None:
        statement = statement.where(table.c.id == bindparam(id_bind))
    if kind == "team_update":
        statement = statement.where(table.c.kind == bindparam("where_kind"))
        _replace_built_statement(monkeypatch, kind, statement)
    else:
        monkeypatch.setattr(
            roster_module, "player_update_statement", lambda _: statement
        )

    with pytest.raises(repository_base._TenantOperationError, match=expected_error):
        _Repository(recorder).execute(make_tenant_context(_TENANT_ID), operation)
    assert recorder.calls == []


def test_team_update_rejects_old_kind_bind_name(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
) -> None:
    """UPDATE の種別条件へ列名と重なる旧 bind 名を使わせない。"""
    table = cast(Table, TeamRecord.__table__)
    statement = (
        update(table)
        .where(table.c.tenant_id == bindparam("where_tenant_id"))
        .where(table.c.id == bindparam("where_id"))
        .where(table.c.kind == bindparam("kind"))
        .values(name=bindparam("name"))
    )
    _replace_built_statement(monkeypatch, "team_update", statement)
    with pytest.raises(
        repository_base._TenantOperationError, match="kind = :where_kind"
    ):
        _Repository(recorder).execute(
            make_tenant_context(_TENANT_ID), TeamRecordUpdateToken(_TEAM_ID, "改名")
        )
    assert recorder.calls == []


@pytest.mark.parametrize(
    "statement",
    (
        insert(cast(Table, TeamRecord.__table__)).values(
            id=bindparam("id"), kind=bindparam("kind"), name=bindparam("name")
        ),
        insert(cast(Table, TeamRecord.__table__)).values(
            tenant_id=bindparam("other"),
            id=bindparam("id"),
            kind=bindparam("kind"),
            name=bindparam("name"),
        ),
        insert(cast(Table, TeamRecord.__table__)).values(
            tenant_id=_TENANT_ID,
            id=bindparam("id"),
            kind=bindparam("kind"),
            name=bindparam("name"),
        ),
    ),
)
def test_prepared_insert_requires_tenant_bind(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    statement: ClauseElement,
) -> None:
    """テナント値の省略・別名 bind・定数を業務文発行前に拒否する。"""
    _replace_built_statement(monkeypatch, "team_create", statement)
    with pytest.raises(repository_base._TenantOperationError, match="tenant_id"):
        _Repository(recorder).execute(
            make_tenant_context(_TENANT_ID),
            TeamRecordCreateToken(_TEAM_ID, "対戦相手"),
        )
    assert recorder.calls == []


@pytest.mark.parametrize("execution_path", ("repository", "transaction"))
@pytest.mark.parametrize(
    ("builder_name", "operation", "statement", "expected_error"),
    (
        (
            "team_record_read_statement",
            TeamRecordReadToken(limit=1),
            select(TeamRecord.__table__.c.id)
            .where(TeamRecord.__table__.c.tenant_id == bindparam("tenant_id"))
            .limit(bindparam("limit")),
            "kind = :kind",
        ),
        (
            "_TEAM_RECORD_UPDATE",
            TeamRecordUpdateToken(_TEAM_ID, "改名"),
            update(cast(Table, TeamRecord.__table__))
            .where(TeamRecord.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(TeamRecord.__table__.c.id == bindparam("where_id"))
            .values(name=bindparam("name")),
            "kind = :where_kind",
        ),
        (
            "player_read_statement",
            PlayerReadToken(limit=1),
            select(Player.__table__.c.id).where(
                Player.__table__.c.tenant_id == bindparam("tenant_id")
            ),
            "LIMIT :limit",
        ),
        (
            "team_record_read_statement",
            TeamRecordReadToken(limit=1),
            select(TeamRecord.__table__.c.id)
            .where(TeamRecord.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(TeamRecord.__table__.c.kind == bindparam("kind")),
            "LIMIT :limit",
        ),
    ),
)
def test_required_kind_and_page_limit_cannot_be_removed(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    execution_path: str,
    builder_name: str,
    operation: TeamRecordReadToken | TeamRecordUpdateToken | PlayerReadToken,
    statement: ClauseElement,
    expected_error: str,
) -> None:
    """チーム種別または一覧上限の欠落を両実行経路で拒否する。"""
    if builder_name == "_TEAM_RECORD_UPDATE":
        _replace_built_statement(monkeypatch, "team_update", statement)
    else:
        monkeypatch.setattr(roster_module, builder_name, lambda _: statement)
    context = make_tenant_context(_TENANT_ID)
    with pytest.raises(repository_base._TenantOperationError, match=expected_error):
        if execution_path == "repository":
            _Repository(recorder).execute(context, operation)
        else:
            _run_transaction_token(context, recorder, operation)
    assert recorder.calls == []


def test_team_create_requires_kind_bind(recorder: _RecordingSession) -> None:
    """INSERT の種別束縛宣言を登録文に固定する。"""
    spec = repository_base._OPERATION_REGISTRY[TeamRecordCreateToken]
    invalid = insert(cast(Table, TeamRecord.__table__)).values(
        tenant_id=bindparam("tenant_id"),
        id=bindparam("id"),
        kind=bindparam("other_kind"),
        name=bindparam("name"),
    )
    with pytest.raises(repository_base._TenantOperationError, match="kind = :kind"):
        repository_base._validate_prepared_statement(
            spec,
            invalid,
            {"kind": "opponent"},
        )
    assert recorder.calls == []


@pytest.mark.parametrize("execution_path", ("repository", "transaction"))
@pytest.mark.parametrize(
    "operation",
    (
        PlayerReadToken(limit=ROSTER_PAGE_SIZE_MAX),
        TeamRecordReadToken(limit=ROSTER_PAGE_SIZE_MAX),
    ),
)
def test_page_limit_maximum_is_accepted(
    recorder: _RecordingSession,
    execution_path: str,
    operation: PlayerReadToken | TeamRecordReadToken,
) -> None:
    """DTO の上限から導いた LIMIT 201 を両経路で許す。"""
    context = make_tenant_context(_TENANT_ID)
    if execution_path == "repository":
        _Repository(recorder).execute(context, operation)
    else:
        _run_transaction_token(context, recorder, operation)
    spec = repository_base._OPERATION_REGISTRY[type(operation)]
    assert spec.required_limit_max == ROSTER_PAGE_SIZE_MAX + 1
    assert recorder.calls[0][1]["limit"] == ROSTER_PAGE_SIZE_MAX + 1


@pytest.mark.parametrize("execution_path", ("repository", "transaction"))
@pytest.mark.parametrize(
    "operation",
    (
        PlayerReadToken(limit=1),
        TeamRecordReadToken(limit=1),
    ),
)
def test_page_limit_above_registered_maximum_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    execution_path: str,
    operation: PlayerReadToken | TeamRecordReadToken,
) -> None:
    """準備関数が LIMIT を過大にしても業務 SQL を発行しない。"""
    spec = repository_base._OPERATION_REGISTRY[type(operation)]

    def oversized_prepare(token: PlayerReadToken | TeamRecordReadToken) -> Any:
        statement, parameters = spec.prepare(token)
        return statement, {**parameters, "limit": ROSTER_PAGE_SIZE_MAX + 2}

    registry = dict(repository_base._OPERATION_REGISTRY)
    registry[type(operation)] = replace(spec, prepare=oversized_prepare)
    monkeypatch.setattr(
        repository_base, "_OPERATION_REGISTRY", MappingProxyType(registry)
    )
    context = make_tenant_context(_TENANT_ID)
    with pytest.raises(repository_base._TenantOperationError, match="LIMIT の束縛値"):
        if execution_path == "repository":
            _Repository(recorder).execute(context, operation)
        else:
            _run_transaction_token(context, recorder, operation)
    assert recorder.calls == []


@pytest.mark.parametrize("execution_path", ("repository", "transaction"))
@pytest.mark.parametrize(
    ("operation", "builder_name", "statement", "expected_error"),
    (
        *(
            (
                PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
                "player_update_statement",
                update(cast(Table, Player.__table__))
                .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
                .where(Player.__table__.c.id == bindparam("where_id"))
                .values(
                    **{
                        "name": bindparam("value_name"),
                        forbidden: bindparam(f"value_{forbidden}"),
                    }
                ),
                "未許可列",
            )
            for forbidden in ("hidden_at", "team_record_id", "tenant_id", "id")
        ),
        (
            TeamRecordUpdateToken(_TEAM_ID, "改名"),
            "_TEAM_RECORD_UPDATE",
            update(cast(Table, TeamRecord.__table__))
            .where(TeamRecord.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(TeamRecord.__table__.c.id == bindparam("where_id"))
            .where(TeamRecord.__table__.c.kind == bindparam("where_kind"))
            .values(
                {
                    TeamRecord.__table__.c.name: bindparam("name"),
                    TeamRecord.__table__.c.hidden_at: bindparam("hidden_at"),
                }
            ),
            "未許可列",
        ),
        (
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            "player_update_statement",
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("where_tenant_id"))
            .where(Player.__table__.c.id == bindparam("where_id")),
            "許可済み列が 1 件以上",
        ),
    ),
)
def test_update_set_columns_stay_within_token_declaration(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    execution_path: str,
    operation: PlayerUpdateToken | TeamRecordUpdateToken,
    builder_name: str,
    statement: ClauseElement,
    expected_error: str,
) -> None:
    """UPDATE SET の余分な列と空集合を両経路で拒否する。"""
    if builder_name == "_TEAM_RECORD_UPDATE":
        _replace_built_statement(monkeypatch, "team_update", statement)
    else:
        monkeypatch.setattr(roster_module, builder_name, lambda _: statement)
    context = make_tenant_context(_TENANT_ID)
    with pytest.raises(repository_base._TenantOperationError, match=expected_error):
        if execution_path == "repository":
            _Repository(recorder).execute(context, operation)
        else:
            _run_transaction_token(context, recorder, operation)
    assert recorder.calls == []


def test_update_column_declarations_match_dto_fields() -> None:
    """更新宣言を DTO の列だけに固定し、識別子と削除列を除外する。"""
    assert repository_base._OPERATION_REGISTRY[
        PlayerUpdateToken
    ].allowed_update_columns == frozenset(
        {
            "name",
            "throws",
            "bats",
            "uniform_number",
        }
    )
    assert repository_base._OPERATION_REGISTRY[
        PlayerRosterStatusUpdateToken
    ].allowed_update_columns == frozenset({"roster_status_key", "roster_label_key"})
    assert repository_base._OPERATION_REGISTRY[
        PlayerRosterLabelUpdateToken
    ].allowed_update_columns == frozenset({"roster_label_key"})
    assert repository_base._OPERATION_REGISTRY[
        TeamRecordUpdateToken
    ].allowed_update_columns == frozenset({"name"})
    assert repository_base._OPERATION_REGISTRY[
        TeamRecordDeleteToken
    ].allowed_update_columns == frozenset({"hidden_at"})


def test_game_link_lookup_is_single_table_and_bounded() -> None:
    """削除ガード用の試合照会は対象テナントの 1 件だけを読む。"""
    statement, parameters = repository_base._prepare_operation(
        GameTeamLinkReadToken(_TEAM_ID), _TENANT_ID
    )
    assert isinstance(statement, Select)
    assert statement.get_final_froms() == [Game.__table__]
    assert parameters == {
        "tenant_id": _TENANT_ID,
        "team_record_id": _TEAM_ID,
        "limit": 1,
    }
    assert "games.tenant_id = :tenant_id" in str(statement)
    assert "games.home_team_record_id = :team_record_id" in str(statement)
    assert "games.away_team_record_id = :team_record_id" in str(statement)


def test_similar_team_lookup_is_filtered_and_bounded_in_sql() -> None:
    """類似名は SQL 側でテナント・種別・名前を絞って返す。"""
    statement, parameters = repository_base._prepare_operation(
        TeamRecordReadToken(
            limit=ROSTER_PAGE_SIZE_MAX,
            similar_name="Tokyo",
            exclude_id=_TEAM_ID,
        ),
        _TENANT_ID,
    )
    assert isinstance(statement, Select)
    assert statement.get_final_froms() == [TeamRecord.__table__]
    sql = str(statement)
    assert "team_records.tenant_id = :tenant_id" in sql
    assert "team_records.kind = :kind" in sql
    assert "team_records.hidden_at IS NULL" in sql
    assert "pg_catalog.normalize(team_records.name" in sql
    assert "pg_catalog.normalize(:similar_name" in sql
    assert "pg_catalog.btrim" in sql
    assert "pg_catalog.lower" in sql
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params["similar_form"] == "NFKC"
    assert "\u3000" in compiled.params["similar_whitespace"]
    assert "team_records.id != :exclude_id" in sql
    assert parameters["limit"] == ROSTER_PAGE_SIZE_MAX + 1


def test_team_delete_token_sets_only_hidden_at() -> None:
    """論理削除は名前を変えず、更新文を実行前に検査する。"""
    hidden_at = datetime.now(timezone.utc)
    statement, parameters = repository_base._prepare_operation(
        TeamRecordDeleteToken(_TEAM_ID, hidden_at), _TENANT_ID
    )
    assert "SET hidden_at=:hidden_at" in str(statement)
    assert "team_records.hidden_at IS NULL" in str(statement)
    assert parameters["hidden_at"] == hidden_at
    with pytest.raises(ValueError):
        TeamRecordUpdateToken(_TEAM_ID, "")


@pytest.mark.parametrize("path", ("repository", "transaction"))
def test_team_name_token_cannot_set_hidden_at(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    path: str,
) -> None:
    """名前変更の token から論理削除列を変える文を拒否する。"""
    statement = (
        update(cast(Table, TeamRecord.__table__))
        .where(TeamRecord.__table__.c.tenant_id == bindparam("where_tenant_id"))
        .where(TeamRecord.__table__.c.id == bindparam("where_id"))
        .where(TeamRecord.__table__.c.kind == bindparam("where_kind"))
        .values(hidden_at=bindparam("hidden_at"))
    )
    _replace_built_statement(monkeypatch, "team_update", statement)
    context = make_tenant_context(_TENANT_ID)
    with pytest.raises(repository_base._TenantOperationError, match="未許可列"):
        if path == "repository":
            _Repository(recorder).execute(
                context, TeamRecordUpdateToken(_TEAM_ID, "変更")
            )
        else:
            _run_transaction_token(
                context, recorder, TeamRecordUpdateToken(_TEAM_ID, "変更")
            )
    assert recorder.calls == []


@pytest.mark.parametrize("path", ("repository", "transaction"))
def test_team_delete_token_cannot_set_name(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _RecordingSession,
    path: str,
) -> None:
    """削除 token の登録集合に名前を混ぜても SQL 発行前に拒否する。"""
    statement = (
        update(cast(Table, TeamRecord.__table__))
        .where(TeamRecord.__table__.c.tenant_id == bindparam("where_tenant_id"))
        .where(TeamRecord.__table__.c.id == bindparam("where_id"))
        .where(TeamRecord.__table__.c.kind == bindparam("where_kind"))
        .values(hidden_at=bindparam("hidden_at"), name=bindparam("name"))
    )
    _replace_built_statement(monkeypatch, "team_delete", statement)
    context = make_tenant_context(_TENANT_ID)
    token = TeamRecordDeleteToken(_TEAM_ID, datetime.now(timezone.utc))
    with pytest.raises(repository_base._TenantOperationError, match="未許可列"):
        if path == "repository":
            _Repository(recorder).execute(context, token)
        else:
            _run_transaction_token(context, recorder, token)
    assert recorder.calls == []
