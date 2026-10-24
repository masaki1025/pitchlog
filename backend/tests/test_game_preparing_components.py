"""preparing 試合の入力 DTO と未登録 read 候補を検査する。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from collections import UserDict
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, cast, get_args
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Query
from pydantic import SecretStr, TypeAdapter, ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.selectable import Select

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.schemas.base import BaseSchema, PageRequest
from pitchlog.api.schemas.game_start import GameStartRequest, StartLineupInput
from pitchlog.api.schemas.games import (
    ExistingTournament,
    NewTournament,
    PreparingGameCreate,
    PreparingGameListRequest,
    _copy_preparing_snapshot_json,
    _decode_preparing_snapshot,
    decode_preparing_game_cursor,
    encode_preparing_game_cursor,
)
from pitchlog.db.game_state.models import Game
from pitchlog.db.game_state.rule_snapshot import (
    DomainValidatedRuleSnapshot,
    RuleSnapshotFailure,
    RuleSnapshotInvalid,
    encode_applied_rules,
)
from pitchlog.repositories.base import (
    _materialize_rows,
    _operation_spec,
    _prepare_operation,
    _TenantScopedOperation,
    _validate_prepared_statement,
)
from pitchlog.repositories.games import (
    PREPARING_GAME_READ_OPERATIONS,
    PreparingGameDetailToken,
    PreparingGameListToken,
)
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
from pitchlog.repositories.tokens import ImmutableValue

_SCHEDULED_AT = datetime(2026, 11, 1, 10, 30, tzinfo=timezone(timedelta(hours=9)))
_GAME_ID = UUID("11111111-1111-4111-8111-111111111111")


def _create_payload() -> dict[str, object]:
    """作成入力の最小有効値を返す。"""
    return {
        "scheduled_at": _SCHEDULED_AT.isoformat(),
        "game_type_key": "game_official",
        "away_team_record_id": str(uuid4()),
        "home_team_record_id": str(uuid4()),
        "tournament": {"kind": "existing", "key": "spring"},
    }


def _cursor_with_parts(stamp: str, id_hex: str) -> str:
    """不正な位置でも整合するチェックサムを付けて拒否分岐を試す。"""
    payload = f"{stamp}|{id_hex}".encode("ascii")
    checksum = hashlib.sha256(payload).hexdigest()[:16].encode("ascii")
    return (
        base64.urlsafe_b64encode(payload + b"|" + checksum).decode("ascii").rstrip("=")
    )


def test_create_input_uses_shared_schema_and_accepts_five_types() -> None:
    """共通 DTO と固定5区分、既存・新規大会の排他形を受理する。"""
    assert issubclass(PreparingGameCreate, BaseSchema)
    assert issubclass(PreparingGameListRequest, PageRequest)
    for game_type in (
        "game_official",
        "game_semi_official",
        "game_open",
        "game_intrasquad",
        "game_other",
    ):
        created = PreparingGameCreate.model_validate(
            {**_create_payload(), "game_type_key": game_type}
        )
        assert created.game_type_key == game_type
        assert created.scheduled_at.utcoffset() == timedelta(hours=9)
        assert isinstance(created.tournament, ExistingTournament)
    new = PreparingGameCreate.model_validate(
        {**_create_payload(), "tournament": {"kind": "new", "display_name": "春季"}}
    )
    assert isinstance(new.tournament, NewTournament)
    assert new.tournament.display_name == "春季"
    assert PreparingGameListRequest().limit == 20


def test_game_type_literal_matches_seed_keys() -> None:
    """作成 DTO の固定5区分が正本 seed の key 集合と一致する。"""
    seed_path = Path(__file__).resolve().parents[2] / "contracts/seeds/game-type.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    keys = [entry["key"] for entry in seed]
    literal = PreparingGameCreate.model_fields["game_type_key"].annotation
    assert len(keys) == len(set(keys)) == 5
    assert set(get_args(literal)) == set(keys)


def test_snapshot_json_copy_reverses_real_materialization_without_sharing() -> None:
    """実行器の不変行から新コンテナを作るだけで、codec 検証成功ではない。"""
    source: dict[str, Any] = {
        "coldConditions": [{"wind": "calm"}, [None, True, 7, "raw", 1.25]],
        "empty": {},
    }
    source_cold = cast(list[Any], source["coldConditions"])
    materialized = _materialize_rows(((source,),))
    immutable = cast(Any, materialized.rows[0][0])
    assert type(immutable) is MappingProxyType
    assert type(immutable["coldConditions"]) is tuple
    assert type(immutable["coldConditions"][0]) is MappingProxyType

    copied_value = _copy_preparing_snapshot_json(immutable)
    assert copied_value == source
    assert type(copied_value) is dict
    copied = cast(dict[str, Any], copied_value)
    assert type(copied["coldConditions"]) is list
    assert type(copied["coldConditions"][0]) is dict
    assert type(copied["coldConditions"][1]) is list
    assert copied is not source
    assert copied["coldConditions"] is not source["coldConditions"]
    assert copied["coldConditions"][0] is not source["coldConditions"][0]

    copied["coldConditions"][0]["wind"] = "gust"
    copied["coldConditions"][1].append("added")
    copied["empty"]["new"] = "copy-only"
    assert source_cold[0]["wind"] == "calm"
    assert len(source_cold[1]) == 5
    assert source["empty"] == {}
    assert immutable["coldConditions"][0]["wind"] == "calm"
    assert len(immutable["coldConditions"][1]) == 5
    assert immutable["empty"] == {}
    with pytest.raises(TypeError):
        immutable["new"] = "rejected"
    with pytest.raises(TypeError):
        immutable["coldConditions"][0]["wind"] = "rejected"

    source_cold[0]["wind"] = "rain"
    source_cold[1].append("source-only")
    assert copied["coldConditions"][0]["wind"] == "gust"
    assert len(copied["coldConditions"][1]) == 6
    assert immutable["coldConditions"][0]["wind"] == "calm"
    assert len(immutable["coldConditions"][1]) == 5


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
        {"unexpected": "raw", "coldConditions": True},
        {"coldConditions": 42, "extra": [False, 0]},
    ],
)
def test_snapshot_json_copy_preserves_unvalidated_shape(raw: dict[str, object]) -> None:
    """欠損・余分・不正な値を補完せず、codec 検証成功とは扱わない。"""
    immutable = _materialize_rows(((raw,),)).rows[0][0]
    copied_value = _copy_preparing_snapshot_json(immutable)
    assert type(copied_value) is dict
    copied = cast(dict[str, object], copied_value)
    assert copied == raw
    assert len(copied) == len(raw)


@pytest.mark.parametrize("value", [None, True, False, 0, 17, "raw", 1.25, -0.0])
def test_snapshot_json_copy_preserves_scalar_identity(value: object) -> None:
    """JSON スカラーを型変換せず同じ値として返す。"""
    assert _copy_preparing_snapshot_json(cast(ImmutableValue, value)) is value


@pytest.mark.parametrize(
    "value",
    [
        UUID("11111111-1111-4111-8111-111111111111"),
        date(2026, 11, 1),
        b"secret-raw",
        Decimal("1.25"),
        frozenset({"secret-raw"}),
        UserDict({"secret-raw": 1}),
        MappingProxyType({1: "secret-raw"}),
        MappingProxyType({"nested": (b"secret-raw",)}),
        float("inf"),
        float("-inf"),
        float("nan"),
    ],
)
def test_snapshot_json_copy_rejects_unsupported_without_value_leak(
    value: object,
) -> None:
    """非 JSON 型と非有限数を値を含まない固定例外で拒否する。"""
    with pytest.raises(ValueError, match="^snapshot JSON 値の型が不正$") as error:
        _copy_preparing_snapshot_json(cast(ImmutableValue, value))
    assert "secret-raw" not in str(error.value)


@pytest.mark.parametrize(
    "change",
    [
        {"scheduled_at": "2026-11-01T10:30:00"},
        {"scheduled_at": True},
        {"game_type_key": "practice"},
        {"game_type_key": True},
        {"away_team_record_id": True},
        {"home_team_record_id": "invalid"},
        {"tournament_key": "spring"},
        {"tenant_id": str(_GAME_ID)},
        {"status": "preparing"},
        {"applied_rules": {}},
        {"rule_override": {}},
        {"started_at": _SCHEDULED_AT.isoformat()},
        {"d4": "not allowed"},
        {"v12": "not allowed"},
        {"tournament": {"kind": "existing", "key": ""}},
        {"tournament": {"kind": "existing", "key": "spring", "display_name": "春"}},
        {"tournament": {"kind": "new", "display_name": ""}},
        {"tournament": {"kind": "new", "display_name": "春", "key": "spring"}},
        {"tournament": {"kind": "new"}},
        {"tournament": {"kind": "unknown", "key": "spring"}},
    ],
)
def test_create_input_rejects_reserved_invalid_and_ambiguous_values(
    change: dict[str, object],
) -> None:
    """出所・状態を外部入力で上書きせず、大会指定も曖昧にしない。"""
    with pytest.raises(ValidationError):
        PreparingGameCreate.model_validate({**_create_payload(), **change})


@pytest.mark.parametrize(
    "field_name",
    ("plate_umpire", "section_label", "week_label", "day_label", "game_number_label"),
)
def test_optional_labels_keep_input_without_normalization(field_name: str) -> None:
    """既存任意ラベルを独自の正規化や長さ制限なしで保持する。"""
    created = PreparingGameCreate.model_validate(
        {**_create_payload(), field_name: "  原文  "}
    )
    assert getattr(created, field_name) == "  原文  "


def test_cursor_round_trip_is_aware_and_supports_same_time_keyset() -> None:
    """日時と UUID の2要素を順序位置として復元する。"""
    cursor = encode_preparing_game_cursor(_SCHEDULED_AT, _GAME_ID)
    position = decode_preparing_game_cursor(cursor)
    assert position == (_SCHEDULED_AT.astimezone(timezone.utc), _GAME_ID)
    assert PreparingGameListRequest(cursor=cursor).cursor == cursor
    assert PreparingGameListToken(cursor=cursor).cursor == cursor


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not_base64!",
        "1",
        _cursor_with_parts(_SCHEDULED_AT.isoformat(), ""),
        _cursor_with_parts("", _GAME_ID.hex),
        _cursor_with_parts("2026-11-01T10:30:00", _GAME_ID.hex),
        _cursor_with_parts(_SCHEDULED_AT.isoformat(), "not-a-uuid"),
        True,
    ],
)
def test_cursor_rejects_invalid_type_partial_and_naive_values(cursor: object) -> None:
    """入力 DTO と token の両方が不正なページ位置を拒否する。"""
    with pytest.raises(ValidationError):
        PreparingGameListRequest.model_validate({"cursor": cursor})
    with pytest.raises(ValueError):
        PreparingGameListToken(cursor=cast(Any, cursor))


def test_cursor_rejects_payload_with_stale_checksum() -> None:
    """位置だけを変更した破損カーソルのチェックサム不一致を拒否する。"""
    cursor = encode_preparing_game_cursor(_SCHEDULED_AT, _GAME_ID)
    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    altered = raw.replace(_GAME_ID.hex.encode("ascii"), uuid4().hex.encode("ascii"))
    corrupted = base64.urlsafe_b64encode(altered).decode("ascii").rstrip("=")
    with pytest.raises(ValueError):
        decode_preparing_game_cursor(corrupted)


@pytest.mark.parametrize(
    "limit", [0, 101, True, 1.5, "0", "101", "1.5", "２０", "+20", ""]
)
def test_list_limit_rejects_out_of_range_or_invalid_values(limit: object) -> None:
    """DTO と token の双方で範囲外・bool・float・非十進表記を拒否する。"""
    with pytest.raises(ValidationError):
        PreparingGameListRequest.model_validate({"limit": limit})
    with pytest.raises(ValueError):
        PreparingGameListToken(limit=cast(Any, limit))


@pytest.mark.parametrize("limit", ["20", "020"])
def test_query_decimal_limit_is_dto_only_coercion(limit: str) -> None:
    """HTTP の数値文字列を DTO は受け、token は exact int を要求する。"""
    assert PreparingGameListRequest.model_validate({"limit": limit}).limit == 20
    with pytest.raises(ValueError):
        PreparingGameListToken(limit=cast(Any, limit))


def test_fastapi_query_binding_accepts_decimal_and_rejects_invalid_limit() -> None:
    """試験専用 app の Query 束縛だけを測り、製品 route 公開とは扱わない。"""
    app = FastAPI()

    @app.get("/games")
    async def list_games(
        query: Annotated[PreparingGameListRequest, Query()],
    ) -> dict[str, int]:
        return {"limit": query.limit}

    async def exercise() -> None:
        """ASGI transport で query を実際の FastAPI 束縛へ通す。"""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/games?limit=20")
            assert response.status_code == 200
            assert response.json() == {"limit": 20}
            for limit in ("0", "101", "1.5", "true", "%2B20", "%EF%BC%92%EF%BC%90"):
                assert (await client.get(f"/games?limit={limit}")).status_code == 422

    asyncio.run(exercise())


def test_tokens_have_no_tenant_argument_and_validate_game_id() -> None:
    """Tenant は token から渡さず、詳細 ID も UUID だけを受ける。"""
    assert {field.name for field in fields(PreparingGameListToken)} == {
        "limit",
        "cursor",
    }
    assert {field.name for field in fields(PreparingGameDetailToken)} == {"game_id"}
    with pytest.raises(TypeError):
        cast(Any, PreparingGameListToken)(tenant_id=uuid4())
    for invalid_id in ("invalid", str(_GAME_ID), True, 1, None):
        with pytest.raises(ValueError):
            PreparingGameDetailToken(game_id=cast(Any, invalid_id))


def test_candidate_statements_bind_tenant_visibility_state_limit_and_keyset() -> None:
    """索引順の一覧と1件詳細が DB 側で tenant・可視性を絞る。"""
    cursor = encode_preparing_game_cursor(_SCHEDULED_AT, _GAME_ID)
    list_spec, detail_spec = PREPARING_GAME_READ_OPERATIONS
    for spec in (list_spec, detail_spec):
        _TenantScopedOperation(spec.capability_id, spec.statement, spec.tenant_column)
        _validate_prepared_statement(spec, spec.statement)
        assert spec.capability_id == "CAP:games:read"
        assert isinstance(spec.statement, Select)
        assert spec.statement.get_final_froms() == [Game.__table__]
    list_statement, list_parameters = list_spec.prepare(
        PreparingGameListToken(limit=100, cursor=cursor)
    )
    detail_statement, detail_parameters = detail_spec.prepare(
        PreparingGameDetailToken(_GAME_ID)
    )
    _TenantScopedOperation(
        list_spec.capability_id, list_statement, list_spec.tenant_column
    )
    _validate_prepared_statement(
        list_spec, list_statement, list_parameters | {"tenant_id": uuid4()}
    )
    _validate_prepared_statement(
        detail_spec, detail_statement, detail_parameters | {"tenant_id": uuid4()}
    )
    sql = str(list_statement.compile(dialect=postgresql.dialect()))
    detail_sql = str(detail_statement.compile(dialect=postgresql.dialect()))
    for statement_sql in (sql, detail_sql):
        assert "games.tenant_id = %(tenant_id)s" in statement_sql
        assert "games.status = %(status)s" in statement_sql
        assert "games.trashed_at IS NULL" in statement_sql
        assert "games.hidden_at IS NULL" in statement_sql
        assert "LIMIT %(limit)s" in statement_sql
    assert "games.scheduled_at < %(cursor_scheduled_at)s" in sql
    assert "games.scheduled_at = %(cursor_scheduled_at)s" in sql
    assert "games.id < %(cursor_id)s" in sql
    assert (
        "(games.scheduled_at < %(cursor_scheduled_at)s OR "
        "games.scheduled_at = %(cursor_scheduled_at)s AND "
        "games.id < %(cursor_id)s::UUID)"
    ) in sql
    assert "ORDER BY games.scheduled_at DESC, games.id DESC" in sql
    assert "games.id = %(game_id)s" in detail_sql
    assert list_parameters == {
        "status": "preparing",
        "limit": 101,
        "cursor_scheduled_at": _SCHEDULED_AT.astimezone(timezone.utc),
        "cursor_id": _GAME_ID,
    }
    assert detail_parameters == {"status": "preparing", "game_id": _GAME_ID, "limit": 1}
    assert "tenant_id" not in list_parameters | detail_parameters


def test_first_page_has_limit_plus_one_without_cursor_branch() -> None:
    """初回一覧も全件読まず、次ページ判定分だけを要求する。"""
    spec = PREPARING_GAME_READ_OPERATIONS[0]
    statement, parameters = spec.prepare(PreparingGameListToken())
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert parameters == {"status": "preparing", "limit": 21}
    assert "cursor_scheduled_at" not in sql
    assert str(spec.statement.compile(dialect=postgresql.dialect())) == sql


def test_read_candidates_are_connected_to_real_executor_in_isolation() -> None:
    """隔離sourceの正規2token登録とtenant注入を確認する。正式受理は別。"""
    registered_types = {registration.token_type for registration in PRODUCT_OPERATIONS}
    for operation in (PreparingGameListToken(), PreparingGameDetailToken(_GAME_ID)):
        assert type(operation) in registered_types
        assert _operation_spec(operation).capability_id == "CAP:games:read"
        tenant = uuid4()
        _, parameters = _prepare_operation(operation, tenant)
        assert parameters["tenant_id"] == tenant


def _saved_snapshot() -> dict[str, Any]:
    """正規 codec が受理する保存値を返す。出所証明には使用しない。"""
    return {
        "ruleSetId": "0a000000-0000-4000-8000-000000000001",
        "regulationInnings": 9,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": {
            "startInning": 10,
            "runnerPlacement": "no_out_first_second",
            "leadoffRule": "continue_lineup",
        },
        "dh": True,
    }


def test_saved_snapshot_materialization_decodes_through_real_codec() -> None:
    """実行器の不変 JSON を単一 codec で検証し、保存値を同じ形で返す。"""
    raw = _saved_snapshot()
    immutable = _materialize_rows(((raw,),)).rows[0][0]
    decoded = _decode_preparing_snapshot(immutable)
    assert type(decoded) is DomainValidatedRuleSnapshot
    assert encode_applied_rules(decoded) == raw
    assert type(immutable) is MappingProxyType
    assert type(immutable["coldConditions"]) is tuple
    assert type(immutable["tiebreak"]) is MappingProxyType
    encoded = encode_applied_rules(decoded)
    encoded["coldConditions"] = [{"pointDifference": 10, "startInning": 5}]
    assert raw["coldConditions"] == []
    assert immutable["coldConditions"] == ()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({}, RuleSnapshotFailure.SHAPE),
        (
            {
                key: value
                for key, value in _saved_snapshot().items()
                if key != "ruleSetId"
            },
            RuleSnapshotFailure.SHAPE,
        ),
        ({**_saved_snapshot(), "extra": "secret-raw"}, RuleSnapshotFailure.SHAPE),
        ({**_saved_snapshot(), "ruleSetId": "secret-raw"}, RuleSnapshotFailure.VALUE),
        ({**_saved_snapshot(), "regulationInnings": 0}, RuleSnapshotFailure.VALUE),
        ({**_saved_snapshot(), "extensionLimit": 8}, RuleSnapshotFailure.CORRELATION),
        (
            {
                **_saved_snapshot(),
                "coldConditions": [{"pointDifference": 10, "startInning": 10}],
            },
            RuleSnapshotFailure.UNRESOLVED,
        ),
    ],
)
def test_saved_snapshot_rejects_old_corrupt_and_unresolved_values(
    raw: dict[str, Any],
    expected: RuleSnapshotFailure,
) -> None:
    """旧行や不正値を補完・再解決せず、正規 codec の失敗分類を保持する。"""
    immutable = _materialize_rows(((raw,),)).rows[0][0]
    with pytest.raises(RuleSnapshotInvalid) as error:
        _decode_preparing_snapshot(immutable)
    assert error.value.kind is expected
    assert "secret-raw" not in str(error.value)


def test_saved_snapshot_contract_unavailable_is_not_a_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """正規契約を取得できないときも未検証の保存値を成功へ戻さない。"""
    from pitchlog.db.game_state import rule_snapshot

    immutable = _materialize_rows(((_saved_snapshot(),),)).rows[0][0]
    rule_snapshot._validator.cache_clear()
    monkeypatch.setattr(rule_snapshot, "_CONTRACT_PATH", tmp_path / "missing.json")
    try:
        with pytest.raises(rule_snapshot.RuleSnapshotContractUnavailable):
            _decode_preparing_snapshot(immutable)
    finally:
        rule_snapshot._validator.cache_clear()


_START_PUBLIC_CREDENTIAL = "public-transport-fixture-not-an-issued-credential"


def _start_payload(away_size: int = 9, home_size: int = 9) -> dict[str, Any]:
    """発行済み権利を装わず、transport検査だけの公開固定入力を返す。"""

    def lineup(size: int) -> list[dict[str, object]]:
        return [
            {
                "player_id": str(uuid4()),
                "batting_order": index + 1 if index < 9 else None,
                "fielding_position": {"unresolved": [None, True, "raw", 1.5]},
            }
            for index in range(size)
        ]

    return {
        "start_request_id": str(uuid4()),
        "device_id": str(uuid4()),
        "device_credential": _START_PUBLIC_CREDENTIAL,
        "away": lineup(away_size),
        "home": lineup(home_size),
    }


def _assert_start_error_is_private(error: ValidationError) -> None:
    """strだけでなく公開エラー詳細/JSON/reprにも資格を残さない。"""
    assert error.error_count() > 0
    assert error.__context__ is None
    for representation in (
        str(error),
        repr(error),
        str(error.errors()),
        json.dumps(error.errors(), default=str),
        error.json(),
    ):
        assert _START_PUBLIC_CREDENTIAL not in representation
    assert all(item["input"] is None and "ctx" not in item for item in error.errors())


@pytest.mark.parametrize("sizes", [(9, 9), (9, 10), (10, 9), (10, 10)])
def test_start_transport_accepts_closed_shapes_without_issuing_rights(
    sizes: tuple[int, int],
) -> None:
    """両側9/10枠を外形として保持し、通常JSONの資格はmaskedにする。"""
    payload = _start_payload(*sizes)
    request = GameStartRequest.model_validate(payload)
    assert issubclass(GameStartRequest, BaseSchema)
    assert issubclass(StartLineupInput, BaseSchema)
    assert set(GameStartRequest.model_fields) == {
        "start_request_id",
        "device_id",
        "device_credential",
        "away",
        "home",
    }
    assert set(StartLineupInput.model_fields) == {
        "player_id",
        "batting_order",
        "fielding_position",
    }
    assert request.start_request_id == UUID(payload["start_request_id"])
    assert request.device_id == UUID(payload["device_id"])
    assert type(request.away) is type(request.home) is tuple
    assert (len(request.away), len(request.home)) == sizes
    assert type(request.device_credential) is SecretStr
    assert request.device_credential.get_secret_value() == _START_PUBLIC_CREDENTIAL
    assert payload["device_credential"] == _START_PUBLIC_CREDENTIAL
    dumped = json.loads(request.model_dump_json())
    assert dumped["device_credential"] == "**********"
    assert dumped["away"] == payload["away"] and dumped["home"] == payload["home"]
    assert _START_PUBLIC_CREDENTIAL not in repr(request)
    assert _START_PUBLIC_CREDENTIAL not in str(request)
    assert _START_PUBLIC_CREDENTIAL not in repr(request.model_dump())
    assert _START_PUBLIC_CREDENTIAL not in request.model_dump_json()


@pytest.mark.parametrize("field", ["away", "home"])
@pytest.mark.parametrize("count", [0, 8, 11])
def test_start_transport_rejects_invalid_side_counts(field: str, count: int) -> None:
    """各側の不足/超過を資格値の露出なしで拒否する。"""
    payload = _start_payload(11, 11)
    payload["away"] = payload["away"][:9]
    payload["home"] = payload["home"][:9]
    payload[field] = _start_payload(11, 11)[field][:count]
    with pytest.raises(ValidationError) as caught:
        GameStartRequest.model_validate(payload)
    _assert_start_error_is_private(caught.value)


@pytest.mark.parametrize("value", [True, False, 0, 10, -1, 1.0, "1", [], {}])
def test_start_transport_batting_order_is_exact_int_or_null(value: object) -> None:
    """打順の型/外形値域だけを検査し、bool/float/文字列を変換採用しない。"""
    payload = _start_payload()
    payload["away"][0]["batting_order"] = value
    with pytest.raises(ValidationError) as caught:
        GameStartRequest.model_validate(payload)
    _assert_start_error_is_private(caught.value)


@pytest.mark.parametrize(
    "field",
    [
        "tenant_id",
        "game_id",
        "status",
        "started_at",
        "d4",
        "d3",
        "v12",
        "recovery_generation",
        "reservation_attempt_id",
        "name",
        "uniform_number",
    ],
)
def test_start_transport_rejects_server_owned_and_unknown_fields(field: str) -> None:
    """本物の試合/記録権/予約/背番号をbodyで偽装できない。"""
    payload = _start_payload()
    payload[field] = _START_PUBLIC_CREDENTIAL
    with pytest.raises(ValidationError) as caught:
        GameStartRequest.model_validate(payload)
    _assert_start_error_is_private(caught.value)


@pytest.mark.parametrize("field", ["name", "uniform_number", "device_credential"])
def test_start_transport_rejects_extra_lineup_fields(field: str) -> None:
    """選手入力をexact3fieldに閉じ、名前/背番号/余剰資格を受理しない。"""
    payload = _start_payload()
    payload["home"][0][field] = _START_PUBLIC_CREDENTIAL
    with pytest.raises(ValidationError) as caught:
        GameStartRequest.model_validate(payload)
    _assert_start_error_is_private(caught.value)


@pytest.mark.parametrize(
    "change",
    [
        {"start_request_id": "not-a-uuid"},
        {"device_id": True},
        {"device_credential": ""},
        {"device_credential": None},
        {"device_credential": 12},
        {"device_credential": {"raw": _START_PUBLIC_CREDENTIAL}},
        {"away": None},
    ],
)
def test_start_transport_rejects_malformed_fields_without_credential_leak(
    change: dict[str, object],
) -> None:
    """他fieldや資格自体が不正でも、診断から資格を公開しない。"""
    with pytest.raises(ValidationError) as caught:
        GameStartRequest.model_validate({**_start_payload(), **change})
    _assert_start_error_is_private(caught.value)


@pytest.mark.parametrize("field", list(GameStartRequest.model_fields))
@pytest.mark.parametrize("json_input", [False, True])
def test_start_transport_missing_field_hides_whole_request(
    field: str,
    json_input: bool,
) -> None:
    """missingのinputが元request全体になる経路も、通常/JSONの両方で拒否する。"""
    payload = _start_payload()
    del payload[field]
    with pytest.raises(ValidationError) as caught:
        if json_input:
            GameStartRequest.model_validate_json(json.dumps(payload))
        else:
            GameStartRequest(**payload)
    _assert_start_error_is_private(caught.value)


def test_start_transport_unknown_positions_are_not_business_authorization() -> None:
    """未知守備/重複等は入力保持で、意味検証済み/ready/heldへ変換しない。"""
    payload = _start_payload()
    payload["away"] = [payload["away"][0]] * 9
    request = GameStartRequest.model_validate(payload)
    assert len({entry.player_id for entry in request.away}) == 1
    assert request.away[0].fielding_position == {"unresolved": [None, True, "raw", 1.5]}
    assert not any(hasattr(request, name) for name in ("ready", "held", "started_at"))


@pytest.mark.parametrize("bad_json", [False, True])
def test_start_transport_json_and_custom_jsonvalue_errors_are_sanitized(
    bad_json: bool,
) -> None:
    """modelより前のJSON構文拒否とJsonValueの独自errorも安全な例外へ閉じる。"""
    with pytest.raises(ValidationError) as caught:
        if bad_json:
            GameStartRequest.model_validate_json(
                '{"device_credential":"' + _START_PUBLIC_CREDENTIAL + '",'
            )
        else:
            payload = _start_payload()
            payload["home"][0]["fielding_position"] = object()
            GameStartRequest.model_validate(payload)
    _assert_start_error_is_private(caught.value)


def test_start_transport_assignment_keeps_credential_wrapped() -> None:
    """通常代入でも資格をstrへ置換できず、不正代入の診断も秘匿する。"""
    request = GameStartRequest.model_validate(_start_payload())
    setattr(request, "device_credential", _START_PUBLIC_CREDENTIAL)
    assert type(request.device_credential) is SecretStr
    with pytest.raises(ValidationError) as caught:
        setattr(request, "device_id", _START_PUBLIC_CREDENTIAL)
    _assert_start_error_is_private(caught.value)
    assert _START_PUBLIC_CREDENTIAL not in repr(request)


@pytest.mark.parametrize("core_parser", [False, True])
def test_start_transport_raw_json_parser_is_outside_class_safety(
    core_parser: bool,
) -> None:
    """生parserはClass入口前の壊れJSONを保持し得る。保証済みと偽らない。"""
    raw = ('{"device_credential":"' + _START_PUBLIC_CREDENTIAL + '",').encode()
    adapter = TypeAdapter(GameStartRequest)
    with pytest.raises(ValidationError) as caught:
        if core_parser:
            adapter.validator.validate_json(raw)
        else:
            adapter.validate_json(raw)
    # pinned実依存の負例。これらを安全な公開Class入口として使用してはいけない。
    assert any(item.get("input") == raw for item in caught.value.errors())
    assert _START_PUBLIC_CREDENTIAL in caught.value.json()


@pytest.mark.parametrize("malformed_json", [False, True])
def test_start_transport_normal_fastapi_handler_hides_inputs_and_logs(
    malformed_json: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """通常FastAPI検証の構文/他field不正を実共通handlerへ通し非露出を確認する。"""
    app = FastAPI()
    register_exception_handlers(app)
    invoked: list[GameStartRequest] = []

    @app.post("/_unit/start-input")
    def validate_transport(body: GameStartRequest) -> dict[str, bool]:
        """試験だけのtransport検証口。製品開始routeや業務成功ではない。"""
        invoked.append(body)
        return {"parsed": True}

    payload = _start_payload()
    del payload["home"]
    raw = (
        '{"device_credential":"' + _START_PUBLIC_CREDENTIAL + '",'
        if malformed_json
        else json.dumps(payload)
    )

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://unit"
        ) as client:
            return await client.post(
                "/_unit/start-input",
                content=raw,
                headers={"Content-Type": "application/json"},
            )

    with caplog.at_level(logging.INFO, logger="pitchlog.api.errors"):
        response = asyncio.run(request())
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "入力に誤りがあります"
    assert _START_PUBLIC_CREDENTIAL not in response.text
    assert not invoked, "不正入力を正常routeへ渡してはならない"
    records = [r for r in caplog.records if r.name == "pitchlog.api.errors"]
    assert records
    assert all(
        r.getMessage() == "リクエストの入力検証に失敗しました。" for r in records
    )
    assert all(r.exc_info is None and r.exc_text is None for r in records)
    assert _START_PUBLIC_CREDENTIAL not in caplog.text
    assert all(_START_PUBLIC_CREDENTIAL not in repr(r.__dict__) for r in records)
