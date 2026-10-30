"""作成/options候補のDTO・固定文・実scope拒否境界を検査する。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import bindparam, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert
from test_authz_tenant_context import make_tenant_context
from test_game_preparing_components import _create_payload, _saved_snapshot

from pitchlog.api.schemas.games import (
    ExistingTournament,
    NewTournament,
    PreparationOptionsRequest,
    PreparingGameCreate,
    decode_preparation_options_cursor,
    encode_preparation_options_cursor,
)
from pitchlog.db.game_state.models import Game
from pitchlog.db.tenant_isolation.models import TenantVocabulary
from pitchlog.repositories import base, transaction
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.preparing_game_creation import (
    PREPARING_GAME_CREATE_OPERATIONS,
    PreparingGameInsertToken,
    PreparingOpponentTeamLockToken,
    PreparingSelfTeamLockToken,
    PreparingTournamentInsertToken,
    PreparingTournamentNameExistsToken,
    PreparingTournamentOptionsToken,
    PreparingTournamentParentToken,
)
from pitchlog.repositories.rg1 import RG1PrecheckToken, RG1Unavailable
from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.services import game_creation

_TENANT = UUID("00000000-0000-0000-0000-000000000501")
_SELF = UUID("00000000-0000-0000-0000-000000000502")
_OTHER = UUID("00000000-0000-0000-0000-000000000503")


def _game_token(**changes: Any) -> PreparingGameInsertToken:
    """公開codecが検査する保存JSONと単純入力を持つtokenを作る。"""
    values: dict[str, Any] = {
        "game_id": uuid4(),
        "scheduled_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        "game_type_key": "game_official",
        "tournament_key": "spring",
        "away_team_record_id": _SELF,
        "home_team_record_id": _OTHER,
        "applied_rules_json": json.dumps(_saved_snapshot()),
        "plate_umpire": " =主審",
        "section_label": "　節 ",
        "week_label": "",
        "day_label": None,
        "game_number_label": "第1試合",
    }
    return PreparingGameInsertToken(**(values | changes))


def _tokens() -> tuple[TenantOperationToken, ...]:
    """候補7型を宣言順に作る。"""
    return (
        _game_token(),
        PreparingTournamentInsertToken("new", " 春季 "),
        PreparingTournamentOptionsToken(2, encode_preparation_options_cursor("春")),
        PreparingTournamentNameExistsToken(" 春季 "),
        PreparingTournamentParentToken("spring"),
        PreparingSelfTeamLockToken(_SELF),
        PreparingOpponentTeamLockToken(_OTHER),
    )


@dataclass
class _Result:
    """合成Sessionから実行器へ返す行集合/更新件数。"""

    rows: tuple[tuple[Any, ...], ...] = ()
    rowcount: int = 1

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        """実行器が行単位で不変化する。"""
        return iter(self.rows)


@contextmanager
def _scope(
    monkeypatch: pytest.MonkeyPatch,
    replies: list[Any],
    *,
    candidates: bool = False,
) -> Iterator[tuple[_TenantTransaction, list[str], list[dict[str, object]]]]:
    """試験専用Sessionで実scope/prepare/検査を通す。認証/HTTP成功ではない。"""
    events: list[str] = []
    parameters_seen: list[dict[str, object]] = []

    class _Session:
        def __init__(self, engine: object) -> None:
            events.append("session")

        def execute(self, statement: object, parameters: dict[str, object]) -> _Result:
            assert parameters["tenant_id"] == _TENANT
            parameters_seen.append(parameters)
            events.append("execute")
            if not replies:
                raise AssertionError("予定外の追加SQL")
            reply = replies.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            return reply

        def close(self) -> None:
            events.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    with monkeypatch.context() as patch:
        patch.setattr(transaction, "Session", _Session)
        patch.setattr(transaction, "create_database_engine", object)
        patch.setattr(transaction, "_tenant_transaction", _binding)
        if candidates:
            patch.setattr(
                base,
                "_OPERATION_REGISTRY",
                MappingProxyType(
                    {
                        **base._OPERATION_REGISTRY,
                        **{
                            spec.token_type: spec
                            for spec in PREPARING_GAME_CREATE_OPERATIONS
                        },
                    }
                ),
            )
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT)
        ) as scope:
            yield scope, events, parameters_seen


@pytest.mark.parametrize("value", ["", " ", "\t\r\n", "\u3000", "\u00a0"])
def test_new_tournament_rejects_only_blank_name(value: str) -> None:
    """Unicodeの空白onlyをDTOとtokenで拒否する。"""
    with pytest.raises(ValidationError):
        NewTournament(kind="new", display_name=value)
    with pytest.raises(ValidationError):
        PreparingTournamentInsertToken("opaque", value)


@pytest.mark.parametrize(
    "value", ["春季", " 春季 ", "春季\u3000", "Ａ大会", "A大会", "a" * 1000]
)
def test_new_tournament_preserves_exact_unicode_and_no_new_length_limit(
    value: str,
) -> None:
    """有効名をtrim/NFKC/独自上限で変えない。"""
    assert NewTournament(kind="new", display_name=value).display_name == value
    token = PreparingTournamentInsertToken("opaque", value)
    assert (
        PREPARING_GAME_CREATE_OPERATIONS[1].prepare(token)[1]["display_name"] == value
    )


@pytest.mark.parametrize("key", ["spring", " 大会　", "Ａ", "key/with?delimiter=1"])
def test_options_cursor_round_trips_key_and_validates_query(key: str) -> None:
    """keyset位置を正規形で戻し、値を正規化しない。"""
    cursor = encode_preparation_options_cursor(key)
    assert decode_preparation_options_cursor(cursor) == key
    assert PreparationOptionsRequest(limit="20", cursor=cursor).limit == 20
    with pytest.raises(ValueError):
        decode_preparation_options_cursor(cursor + "=")


@pytest.mark.parametrize("limit", [True, False, 0, 101, 1.2, "-1", "２０"])
def test_options_limits_reject_invalid_values(limit: Any) -> None:
    """件数を厳密に制限し、不正値を既定値へ戻さない。"""
    with pytest.raises((ValueError, ValidationError)):
        PreparationOptionsRequest(limit=limit)
    with pytest.raises((ValueError, ValidationError)):
        PreparingTournamentOptionsToken(limit=limit)


def test_candidates_are_registered_exactly_and_have_no_tenant_argument() -> None:
    """候補接続で7exact型を通常registryへ登録し、tenantを渡させない。"""
    specs = PREPARING_GAME_CREATE_OPERATIONS
    tokens = _tokens()
    assert len(specs) == len(tokens) == 7
    assert len({spec.token_type for spec in specs}) == 7
    for token, spec in zip(tokens, specs, strict=True):
        assert type(token) is spec.token_type
        assert "tenant_id" not in {field.name for field in fields(cast(Any, token))}
        assert base._operation_spec(token) is spec
        statement, parameters = spec.prepare(token)
        parameters["tenant_id"] = _TENANT
        base._TenantScopedOperation(spec.capability_id, statement, spec.tenant_column)
        base._validate_prepared_statement(spec, statement, parameters)


def test_game_insert_is_one_canonical_table_and_has_sql_null_override() -> None:
    """固定列・全label・6-keyを保持し、JSON nullをSQL NULLへ取り違えない。"""
    spec = PREPARING_GAME_CREATE_OPERATIONS[0]
    token = _game_token()
    statement, parameters = spec.prepare(token)
    assert type(statement) is Insert
    assert statement.table is Game.__table__
    assert parameters["applied_rules"] == _saved_snapshot()
    assert parameters["status"] == "preparing"
    assert parameters["game_type_category"] == "game_type"
    assert parameters["plate_umpire"] == " =主審"
    assert parameters["section_label"] == "　節 "
    assert parameters["week_label"] == ""
    assert parameters["day_label"] is None
    assert parameters["game_number_label"] == "第1試合"
    assert statement._values is not None
    for field in ("rule_override", "started_at"):
        assert field not in statement._values
        assert field not in parameters
        assert Game.__table__.c[field].nullable
        assert Game.__table__.c[field].default is None
        assert Game.__table__.c[field].server_default is None
    assert "recording_generations" not in str(statement)
    assert set(parameters) | {"tenant_id"} == set(statement.compile().params)


@pytest.mark.parametrize(
    "index,field,value",
    [
        (0, "status", "in_progress"),
        (0, "game_type_category", "roster_status"),
        (1, "category", "pitch_type"),
        (1, "disabled", True),
        (2, "disabled", True),
        (2, "category", "strategy"),
        (2, "limit", 102),
        (3, "limit", 2),
        (4, "limit", 2),
        (4, "disabled", True),
        (5, "kind", "opponent"),
        (6, "kind", "self"),
    ],
)
def test_registered_fixed_bindings_reject_changed_values(
    index: int, field: str, value: object
) -> None:
    """条件bindがあっても固定値を変えた実行を拒否する。"""
    spec = PREPARING_GAME_CREATE_OPERATIONS[index]
    statement, parameters = spec.prepare(_tokens()[index])
    with pytest.raises(RuntimeError):
        base._validate_prepared_statement(
            spec, statement, {**parameters, "tenant_id": _TENANT, field: value}
        )


def test_options_and_name_read_are_bounded_and_have_different_disabled_rules() -> None:
    """optionsは有効だけ、同名検査はdisabledを問わず1件に閉じる。"""
    options, name = PREPARING_GAME_CREATE_OPERATIONS[2:4]
    statement, parameters = options.prepare(_tokens()[2])
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY tenant_vocabularies.key" in compiled
    assert "tenant_vocabularies.key >" in compiled
    assert "LIMIT" in compiled and parameters["limit"] == 3
    assert parameters["cursor_key"] == "春"
    assert parameters["disabled"] is False
    statement, parameters = name.prepare(_tokens()[3])
    assert "disabled" not in str(statement)
    assert parameters["display_name"] == " 春季 "
    assert parameters["limit"] == 1


def test_tenant_condition_and_other_table_and_select_insert_swap_are_rejected() -> None:
    """同名tenant列/許可capabilityを使っても表や文種別を迂回できない。"""
    spec = PREPARING_GAME_CREATE_OPERATIONS[0]
    other = insert(cast(Any, TenantVocabulary.__table__)).values(
        tenant_id=bindparam("tenant_id")
    )
    with pytest.raises(RuntimeError):
        base._validate_prepared_statement(spec, other, {"tenant_id": _TENANT})
    with pytest.raises(RuntimeError):
        base._validate_prepared_statement(spec, select(Game.__table__.c.id))
    for spec in PREPARING_GAME_CREATE_OPERATIONS[2:]:
        with pytest.raises(RuntimeError):
            base._TenantScopedOperation(
                spec.capability_id, select(spec.tenant_column), spec.tenant_column
            )


@pytest.mark.parametrize(
    "index,field,bad",
    [
        (0, "applied_rules_json", "{}"),
        (0, "game_id", "uuid"),
        (0, "scheduled_at", datetime(2026, 1, 1)),
        (0, "game_type_key", "active"),
        (1, "display_name", " "),
        (2, "limit", True),
        (2, "cursor", "!"),
        (3, "display_name", "\u3000"),
        (4, "key", ""),
        (5, "team_record_id", True),
    ],
)
def test_token_forced_mutations_are_revalidated_before_sql(
    index: int, field: str, bad: object
) -> None:
    """frozen突破後も同じ単一DTO/codec検査を通して拒否する。"""
    token = _tokens()[index]
    object.__setattr__(token, field, bad)
    with pytest.raises((TypeError, ValueError)):
        PREPARING_GAME_CREATE_OPERATIONS[index].prepare(token)


def test_real_scope_and_real_rg1_false_roll_back_without_business_dml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実RG1登録のfalseだけを返す合成Sessionで、scope全取消/非成功を観測する。"""
    replies = [_Result(((False,),))]
    events: list[str] = []
    calls: list[dict[str, object]] = []
    with pytest.raises(RG1Unavailable):
        with _scope(monkeypatch, replies) as (scope, events, calls):
            game_creation.create_preparing_game(
                scope, PreparingGameCreate.model_validate(_create_payload())
            )
    assert events == ["session", "begin", "execute", "rollback", "close"]
    assert calls == [{"tenant_id": _TENANT}]
    assert replies == []
    spec = FUNCTION_OPERATION_REGISTRY[RG1PrecheckToken]
    assert spec.function_id == "rg1_api.rg1_read_open"


def test_service_refuses_arbitrary_or_expired_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任意Session/Protocol、閉じた実handleを受け入れない。"""
    body = PreparingGameCreate.model_validate(_create_payload())
    with pytest.raises(TypeError):
        game_creation.create_preparing_game(cast(Any, object()), body)
    with _scope(monkeypatch, []) as (scope, _, _):
        expired = scope
    with pytest.raises(RuntimeError, match="失効"):
        game_creation.create_preparing_game(expired, body)


def test_service_revalidates_mutated_dto_before_rg1_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DTO強制変更を、追加SQLなしで拒否する。"""
    body = PreparingGameCreate.model_validate(_create_payload())
    body.game_type_key = cast(Any, "active")
    with pytest.raises(ValidationError):
        with _scope(monkeypatch, []) as (scope, events, _):
            game_creation.create_preparing_game(scope, body)
    assert events == ["session", "begin", "rollback", "close"]


def test_new_name_conflict_and_missing_parent_roll_back_in_real_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """独立下位処理の同名/無効親を拒否する。作成成功の実証には数えない。"""
    for selection, response, code in (
        (
            NewTournament(kind="new", display_name="春"),
            _Result((("old-key",),)),
            "tournament_name_conflict",
        ),
        (
            ExistingTournament(kind="existing", key="missing"),
            _Result(),
            "not_available",
        ),
    ):
        with pytest.raises(game_creation.PreparingGameCreationError, match=code):
            with _scope(monkeypatch, [response], candidates=True) as (scope, events, _):
                game_creation._select_tournament(scope, selection)
        assert events[-2:] == ["rollback", "close"]


def test_new_tournament_insert_then_parent_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """合成DML後の拒否をscope外へ通す。実PGの両INSERT全取消は後続。"""
    replies = [_Result(), _Result(rowcount=1), _Result()]
    with pytest.raises(game_creation.PreparingGameCreationError, match="not_available"):
        with _scope(monkeypatch, replies, candidates=True) as (scope, events, calls):
            game_creation._select_tournament(
                scope, NewTournament(kind="new", display_name=" 春 ")
            )
    assert events[-2:] == ["rollback", "close"]
    assert calls[0]["display_name"] == calls[1]["display_name"] == " 春 "
    assert UUID(cast(str, calls[1]["key"]))
    assert calls[2]["key"] == calls[1]["key"]


def test_team_lookup_lock_order_and_same_team_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既存lookupを使い、UUID順ロック/同team重複除去を確認する。"""
    for away, home, replies in (
        (
            _OTHER,
            _SELF,
            [
                _Result(((_SELF, "self", "self", None),)),
                _Result(((_SELF,),)),
                _Result(((_OTHER, "opponent", "other", None),)),
                _Result(((_OTHER,),)),
            ],
        ),
        (
            _SELF,
            _SELF,
            [_Result(((_SELF, "self", "self", None),)), _Result(((_SELF,),))],
        ),
    ):
        with _scope(monkeypatch, replies, candidates=True) as (scope, _, calls):
            game_creation._lock_teams(scope, away, home)
        locked = [p["team_record_id"] for p in calls if "team_record_id" in p]
        assert locked == sorted({away, home})
        assert replies == []


@pytest.mark.parametrize(
    "opponent_row",
    [
        (),
        ((_OTHER, "opponent", "hidden", datetime.now(timezone.utc)),),
        ((_OTHER, "self", "wrong", None),),
    ],
)
def test_team_missing_hidden_wrong_kind_are_not_available(
    monkeypatch: pytest.MonkeyPatch, opponent_row: Any
) -> None:
    """不可視/別kind/不在を同じ非成功へ閉じる。"""
    replies = [_Result(((_SELF, "self", "self", None),)), _Result(opponent_row)]
    with pytest.raises(game_creation.PreparingGameCreationError, match="not_available"):
        with _scope(monkeypatch, replies, candidates=True) as (scope, events, _):
            game_creation._lock_teams(scope, _OTHER, _OTHER)
    assert events[-2:] == ["rollback", "close"]


def test_options_page_uses_single_bounded_read_and_seed_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """候補登録下のoptionsは1ページだけを読み、lookaheadを返さない。"""
    replies = [_Result((("a", "春"), ("b", "春"), ("c", "夏")))]
    with _scope(monkeypatch, replies, candidates=True) as (scope, _, calls):
        result = game_creation.read_preparation_options(
            scope, PreparationOptionsRequest(limit=2)
        )
    assert [x.key for x in result.tournaments.items] == ["a", "b"]
    assert (
        decode_preparation_options_cursor(result.tournaments.next_cursor or "") == "b"
    )
    seed = json.loads(game_creation._GAME_TYPES_PATH.read_text())
    assert [x.model_dump() for x in result.game_types] == [
        {"key": x["key"], "display_name": x["display_name"]} for x in seed
    ]
    assert len(calls) == 1 and calls[0]["limit"] == 3


def test_seed_failure_is_non_success_before_sql(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """seed欠損を固定5値の捏造や空の成功へ変換しない。"""
    monkeypatch.setattr(game_creation, "_GAME_TYPES_PATH", tmp_path / "absent.json")
    with pytest.raises(
        game_creation.PreparingGameCreationError, match="outcome_unconfirmed"
    ):
        with _scope(monkeypatch, [], candidates=True) as (scope, events, _):
            game_creation.read_preparation_options(scope, PreparationOptionsRequest())
    assert events == ["session", "begin", "rollback", "close"]


@pytest.mark.parametrize(
    "rows",
    [
        (("a",),),
        (("a", "A"), ("b", "B"), ("c",)),
        (("a", "A"), ("a", "A"), ("c", "C"), ("d", "D")),
    ],
)
def test_options_malformed_or_unbounded_result_is_not_success(
    monkeypatch: pytest.MonkeyPatch, rows: Any
) -> None:
    """lookaheadの外形異常も捨てず、上限超過を成功にしない。"""
    with pytest.raises(
        game_creation.PreparingGameCreationError, match="outcome_unconfirmed"
    ):
        with _scope(monkeypatch, [_Result(rows)], candidates=True) as (
            scope,
            events,
            _,
        ):
            game_creation.read_preparation_options(
                scope, PreparationOptionsRequest(limit=2)
            )
    assert events[-2:] == ["rollback", "close"]
