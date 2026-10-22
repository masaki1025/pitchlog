"""preparing 試合の入力 DTO と未登録 read 候補を検査する。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, cast, get_args
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Query
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.selectable import Select

from pitchlog.api.schemas.base import BaseSchema, PageRequest
from pitchlog.api.schemas.games import (
    ExistingTournament,
    NewTournament,
    PreparingGameCreate,
    PreparingGameListRequest,
    decode_preparing_game_cursor,
    encode_preparing_game_cursor,
)
from pitchlog.db.game_state.models import Game
from pitchlog.repositories.base import (
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


def test_read_candidates_remain_unregistered_in_real_executor() -> None:
    """候補を製品登録済みと見なさず、実レジストリの拒否を確かめる。"""
    registered_types = {registration.token_type for registration in PRODUCT_OPERATIONS}
    for operation in (PreparingGameListToken(), PreparingGameDetailToken(_GAME_ID)):
        assert type(operation) not in registered_types
        with pytest.raises(RuntimeError, match="未登録"):
            _operation_spec(operation)
        with pytest.raises(RuntimeError, match="未登録"):
            _prepare_operation(operation, uuid4())
