"""選手・対戦相手の閉じた operation と単一文の実行を検査する。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import Table, bindparam, insert, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.sql.selectable import Alias, Select
from test_authz_tenant_context import make_tenant_context

from pitchlog.api.schemas.roster import ROSTER_PAGE_SIZE_MAX
from pitchlog.authz.capability_registration import validate_capability_registrations
from pitchlog.db.tenant_isolation.models import Player, TeamRecord
from pitchlog.repositories import base as repository_base
from pitchlog.repositories import roster as roster_module
from pitchlog.repositories import transaction as transaction_module
from pitchlog.repositories.base import TenantRepositoryBase
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import (
    PlayerCreateToken,
    PlayerReadToken,
    PlayerUpdateToken,
    TeamRecordCreateToken,
    TeamRecordReadToken,
    TeamRecordUpdateToken,
    player_read_statement,
    player_update_statement,
    team_record_read_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult

_ROOT = Path(__file__).resolve().parents[2]
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000101")
_PLAYER_ID = UUID("00000000-0000-0000-0000-000000000102")
_TEAM_ID = UUID("00000000-0000-0000-0000-000000000103")
_PLAYER_ALIAS = cast(Alias, cast(Table, Player.__table__).alias("unscoped_players"))
_PLAYER_TARGET_ALIAS = cast(
    Alias, cast(Table, Player.__table__).alias("unscoped_target_players")
)
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
    ),
) -> None:
    """リポジトリとトランザクションで 6 token の同じ準備結果を実行する。"""
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
    assert repository_parameters["tenant_id"] == _TENANT_ID
    if isinstance(operation, (PlayerReadToken, TeamRecordReadToken)):
        assert repository_parameters["limit"] == operation.limit + 1
        if operation.record_id is not None:
            assert repository_parameters["record_id"] == operation.record_id
    if isinstance(
        operation,
        (TeamRecordReadToken, TeamRecordCreateToken, TeamRecordUpdateToken),
    ):
        assert repository_parameters["kind"] == "opponent"


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
                    (
                        ("name", "更新"),
                        ("throws", None),
                        ("roster_status_key", "active"),
                    ),
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


def test_player_patch_rejects_unclassified_and_invalid_columns() -> None:
    """所属変更・空変更・重複・非 nullable の NULL を拒否する。"""
    for changes in (
        (),
        (("team_record_id", str(_TEAM_ID)),),
        (("name", "甲"), ("name", "乙")),
        (("name", None),),
        (("roster_status_key", None),),
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
        assert parameters["tenant_id"] == _TENANT_ID
        assert not isinstance(statement, Select)
    assert calls[0][1]["kind"] == "opponent"
    assert calls[1][1]["kind"] == "opponent"
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
            .where(Player.__table__.c.id == bindparam("id"))
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
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id == bindparam("id"))
            .where(TeamRecord.__table__.c.id == bindparam("other_id"))
            .values(name=bindparam("value_name")),
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, TeamRecord.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(TeamRecord.__table__.c.id == bindparam("id"))
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
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id == bindparam("id"))
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
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id == bindparam("id"))
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
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id == bindparam("id"))
            .values(name=select(Player.__table__.c.name).scalar_subquery()),
            "別名・結合・入れ子のFROM",
        ),
        (
            "player_update_statement",
            PlayerUpdateToken(_PLAYER_ID, (("name", "改名"),)),
            update(cast(Table, Player.__table__))
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id == bindparam("id"))
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
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .values(name=bindparam("value_name")),
        ),
        (
            TeamRecordUpdateToken(_TEAM_ID, "改名"),
            "_TEAM_RECORD_UPDATE",
            update(cast(Table, TeamRecord.__table__))
            .where(TeamRecord.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(TeamRecord.__table__.c.kind == bindparam("kind"))
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
        monkeypatch.setattr(roster_module, statement_name, statement)
    with pytest.raises(repository_base._TenantOperationError, match="id = :id"):
        _Repository(recorder).execute(make_tenant_context(_TENANT_ID), operation)
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
    monkeypatch.setattr(roster_module, "_TEAM_RECORD_CREATE", statement)
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
            .where(TeamRecord.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(TeamRecord.__table__.c.id == bindparam("id"))
            .values(name=bindparam("name")),
            "kind = :kind",
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
        monkeypatch.setattr(roster_module, builder_name, statement)
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
                .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
                .where(Player.__table__.c.id == bindparam("id"))
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
            .where(TeamRecord.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(TeamRecord.__table__.c.id == bindparam("id"))
            .where(TeamRecord.__table__.c.kind == bindparam("kind"))
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
            .where(Player.__table__.c.tenant_id == bindparam("tenant_id"))
            .where(Player.__table__.c.id == bindparam("id")),
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
        monkeypatch.setattr(roster_module, builder_name, statement)
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
            "roster_status_key",
            "roster_label_key",
        }
    )
    assert repository_base._OPERATION_REGISTRY[
        TeamRecordUpdateToken
    ].allowed_update_columns == frozenset({"name"})
