"""preparing 試合の入力 DTO と未登録 read 候補を検査する。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
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
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.selectable import Select

from pitchlog.api.schemas.base import BaseSchema, PageRequest
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


def test_initial_scope_constructor_and_derived_type_cannot_be_forged() -> None:
    """私有発行なしのscope/派生ハンドルはDB前に拒否する。"""
    from test_authz_tenant_context import make_tenant_context

    from pitchlog.recording_rights.initial_grant import InitialGrantUnavailable
    from pitchlog.repositories.initial_recording_right import (
        InitialRecordingRightScope,
        _StartOwner,
    )

    context = make_tenant_context(_GAME_ID)
    owner = _StartOwner(
        _GAME_ID, _GAME_ID, _GAME_ID, _GAME_ID, _GAME_ID, bytes(range(32))
    )
    with pytest.raises(InitialGrantUnavailable, match="私有factory"):
        InitialRecordingRightScope(context, cast(Any, object()), owner, object())
    with pytest.raises(TypeError, match="派生"):
        type("ForgedInitialScope", (cast(Any, InitialRecordingRightScope),), {})


def test_initial_credential_digest_is_opaque_and_not_printed() -> None:
    """正規化しない単一helperを使い、資格/要求digestをreprへ出さない。"""
    from pitchlog.repositories.initial_recording_right import (
        _credential_digest,
        _StartOwner,
    )

    credential = "public-test-device-token"
    assert (
        _credential_digest(credential)
        == hashlib.sha256(credential.encode("utf-8")).digest()
    )
    assert _credential_digest(" " + credential) != _credential_digest(credential)
    assert _credential_digest(credential.upper()) != _credential_digest(credential)
    owner = _StartOwner(
        _GAME_ID, _GAME_ID, _GAME_ID, _GAME_ID, _GAME_ID, _credential_digest(credential)
    )
    assert credential not in repr(owner) and "request_digest=" not in repr(owner)


@pytest.mark.parametrize(
    "column,value",
    (
        (0, "pitchlog_app"),
        (1, "pitchlog_owner"),
        (2, False),
        (3, True),
        (4, True),
        (5, True),
        (6, True),
        (7, True),
        (8, True),
        (9, 1),
        (9, False),
        (10, "preconfigured"),
        (11, "other-database"),
        (12, True),
        (13, datetime(2026, 10, 24)),
        (14, 0),
    ),
)
def test_initial_actor_observed_boundary_rejects_each_mismatch(
    column: int, value: object
) -> None:
    """実観測比較の単独反転を拒否する。実DB認証成功とは数えない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantUnavailable
    from pitchlog.recording_rights.initial_grant_broker import (
        _ActorConfiguration,
        _validate_actor_observation,
    )

    started = datetime(2026, 10, 24, tzinfo=timezone.utc)
    config = _ActorConfiguration(
        "postgresql+psycopg://fixture@127.0.0.1/test?sslmode=disable",
        "12345",
        5,
        "fixture-business",
        started,
    )
    row: list[object] = [
        "pitchlog_initial_actor",
        "pitchlog_initial_actor",
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        0,
        None,
        "fixture-business",
        5,
        started,
        10,
    ]
    _validate_actor_observation(tuple(row), config)
    row[column] = value
    with pytest.raises(InitialGrantUnavailable):
        _validate_actor_observation(tuple(row), config)


def test_initial_actor_binding_missing_supplier_is_not_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scope_binding供給不足をboolやcaller JSONで埋めない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantUnavailable
    from pitchlog.recording_rights.initial_grant_broker import _verify_business_binding
    from pitchlog.repositories import operation_registry
    from pitchlog.repositories.rg1 import RG1ScopeBindingToken

    # 不変の本物の登録表を変更せず、供給欠落を差し込んで拒否を検査する。
    monkeypatch.setattr(
        operation_registry,
        "FUNCTION_OPERATION_REGISTRY",
        {
            key: value
            for key, value in operation_registry.FUNCTION_OPERATION_REGISTRY.items()
            if key is not RG1ScopeBindingToken
        },
    )
    with pytest.raises(InitialGrantUnavailable, match="未供給"):
        _verify_business_binding(cast(Any, object()), object())


def test_initial_storage_candidate_has_exact_tables_nullable_evidence_and_fks() -> None:
    """ORMの4表/旧nullable列/tenant付きFKをDBなしでcompile照合する。"""
    from sqlalchemy.schema import CreateTable

    from pitchlog.db import all_models
    from pitchlog.db.base import Base
    from pitchlog.db.recording_rights.models import RecordingGeneration, RG1RestoreGate

    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    names = {
        "trusted_devices",
        "game_start_requests",
        "game_start_attempts",
        "recording_right_deliveries",
    }
    for name in names:
        table = Base.metadata.tables[name]
        assert "tenant_id" in table.primary_key.columns
        assert all(
            "tenant_id" in fk.column_keys for fk in table.foreign_key_constraints
        )
        assert all(fk.ondelete == "NO ACTION" for fk in table.foreign_key_constraints)
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for table, name in (
        (RecordingGeneration.__table__, "proof_digest"),
        (RecordingGeneration.__table__, "recovery_generation"),
        (RG1RestoreGate.__table__, "recovery_generation"),
    ):
        assert table.c[name].nullable and table.c[name].server_default is None
    pending = next(
        i
        for i in Base.metadata.tables["game_start_attempts"].indexes
        if i.name == "uq_game_start_attempts_pending"
    )
    assert (
        pending.unique
        and str(pending.dialect_options["postgresql"]["where"]) == "outcome = 'pending'"
    )


def test_initial_scope_unregistered_object_has_no_owner_authority() -> None:
    """object生成や属性穴埋めで真正scopeの登録を代用できない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantUnavailable
    from pitchlog.repositories.initial_recording_right import InitialRecordingRightScope

    forged = object.__new__(InitialRecordingRightScope)
    with pytest.raises(InitialGrantUnavailable, match="owner束縛"):
        forged.assert_bound_tenant(_GAME_ID)


def test_initial_scope_matches_existing_nine_method_protocol() -> None:
    """単一issuerが要求する9methodの署名を増減せず提供する。"""
    import inspect

    from pitchlog.recording_rights.initial_grant import InitialGrantScope
    from pitchlog.repositories.initial_recording_right import InitialRecordingRightScope

    names = [
        name
        for name, value in InitialGrantScope.__dict__.items()
        if not name.startswith("_") and callable(value)
    ]
    assert len(names) == 9
    for name in names:
        assert tuple(
            inspect.signature(getattr(InitialRecordingRightScope, name)).parameters
        ) == tuple(inspect.signature(getattr(InitialGrantScope, name)).parameters)


def test_initial_actor_wrong_process_and_unregistered_runtime_are_closed() -> None:
    """私有runtimeを持たないcallerはengine取得へ進めない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantUnavailable
    from pitchlog.recording_rights.initial_grant_broker import (
        _initial_actor_engine,
        _InitialActorRuntime,
    )

    with pytest.raises(InitialGrantUnavailable):
        _InitialActorRuntime(object(), object())
    with pytest.raises(InitialGrantUnavailable):
        _initial_actor_engine(object())


def test_initial_storage_migration_is_frozen_and_never_backfills_epoch() -> None:
    """migration候補は4表だけを固定し、旧行UPDATEや旧trigger追加をしない。"""
    import runpy

    source = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/0036_initial_recording_right_storage.py"
    )
    module = runpy.run_path(str(source))
    assert module["down_revision"] == "0035_rg1_initial_fresh_epoch"
    ddl = "\n".join(module["_TABLE_DDL"])
    assert ddl.count("CREATE TABLE public.") == 4
    assert "CREATE UNIQUE INDEX uq_game_start_attempts_pending" in ddl
    body = module["_INTERNAL_TRIGGER_SQL"]
    assert "SECURITY INVOKER" in body and "pg_catalog, pg_temp" in body
    assert "TG_OP = 'DELETE'" in body
    assert "recording_generations" not in body and "rg1_restore_gate" not in body
    assert "UPDATE public.recording_generations" not in source.read_text()
    assert '"rg1_restore_gate"' not in source.read_text()
    assert module["revision"] == "0036_initial_right_storage"
    assert len(module["revision"]) <= 32


def _initial_transport_response_values():
    """公開合成の応答外形。実発行/commit成功を代用しない。"""
    from pydantic import SecretStr

    from pitchlog.api.schemas.game_start import (
        InitialDeviceEnrollmentResponse,
        InitialGameStartResponse,
    )
    from pitchlog.recording_rights.initial_grant_broker import _broker_d4

    tenant, game = UUID(int=1), UUID(int=2)
    enrollment = dict(
        tenant_id=tenant,
        device_id=UUID(int=5),
        device_credential=SecretStr("synthetic-enroll-sensitive"),
    )
    started = dict(
        tenant_id=tenant,
        game_id=game,
        start_request_id=UUID(int=4),
        device_id=UUID(int=5),
        d4=_broker_d4(tenant, game, 17),
        recovery_generation="2",
        recording_right_proof=SecretStr("synthetic-proof-sensitive"),
        started_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
        away_lineup_id=UUID(int=31),
        home_lineup_id=UUID(int=32),
    )
    return [
        (InitialDeviceEnrollmentResponse, enrollment, "synthetic-enroll-sensitive"),
        (InitialGameStartResponse, started, "synthetic-proof-sensitive"),
    ]


@pytest.mark.parametrize("index", [0, 1])
def test_initial_transport_response_is_frozen_and_ordinary_dump_is_redacted(
    index,
) -> None:
    """通常json/reprと代入/別field不正のerrorへ資格を残さない。"""
    model, values, secret = _initial_transport_response_values()[index]
    response = model.model_validate(values)
    assert secret not in repr(response) and secret not in str(response)
    assert secret not in response.model_dump_json()
    secret_field = "device_credential" if index == 0 else "recording_right_proof"
    with pytest.raises(ValidationError) as caught:
        setattr(response, secret_field, secret)
    assert secret not in str(caught.value) and secret not in caught.value.json()
    assert (
        secret not in repr(caught.value.errors()) and caught.value.__context__ is None
    )
    for invalid in [
        {**values, "tenant_id": False},
        {**values, secret: secret},
        {k: v for k, v in values.items() if k != "device_id"},
    ]:
        with pytest.raises(ValidationError) as caught:
            model.model_validate(invalid)
        assert secret not in str(caught.value) and secret not in caught.value.json()
        assert (
            secret not in repr(caught.value.errors())
            and caught.value.__context__ is None
        )
    with pytest.raises(ValidationError) as caught:
        model.model_validate_json('{"device_credential":"' + secret + '",')
    assert secret not in str(caught.value) and secret not in caught.value.json()


@pytest.mark.parametrize(
    "value", [0, True, 1.0, "0", "01", "2\n", "2\r\n", "2 ", "9223372036854775808"]
)
def test_initial_transport_response_epoch_has_no_numeric_or_canonical_coercion(
    value,
) -> None:
    """応答epochを正値/十進の閉表現に保つ。"""
    model, values, _ = _initial_transport_response_values()[1]
    with pytest.raises(ValidationError):
        model.model_validate({**values, "recovery_generation": value})


def test_initial_transport_http_validation_uses_real_common_safe_handler(
    caplog,
) -> None:
    """通常FastAPI検証の構文/他field不正でも応答/logへ資格を出さない。"""
    from fastapi.testclient import TestClient
    from test_initial_game_start_components import _body

    from pitchlog.api.errors import register_exception_handlers
    from pitchlog.api.schemas.game_start import GameStartRequest

    app = FastAPI()
    register_exception_handlers(app)

    # ローカル型をFastAPIが解決できるよう、宣言済み公開Classを注釈へ設定する。
    def validate(body):
        return {"shape": True}

    validate.__annotations__ = {"body": GameStartRequest}
    app.post("/shape-only")(validate)
    secret = "synthetic-http-sensitive"
    valid = _body()
    valid["device_credential"] = secret
    with TestClient(app) as client:
        for raw in [
            '{"device_credential":"' + secret + '",',
            json.dumps({**valid, "start_request_id": "bad"}),
            json.dumps({**valid, secret: secret}),
        ]:
            response = client.post(
                "/shape-only", content=raw, headers={"content-type": "application/json"}
            )
            assert response.status_code == 422 and secret not in response.text
    for record in caplog.records:
        assert secret not in record.getMessage() and record.exc_info is None


@pytest.mark.parametrize("inner", [True, 123, {"secret": "raw-private-value"}])
@pytest.mark.parametrize("index", [0, 1])
def test_initial_transport_response_revalidates_direct_secret_wrapper_inner(
    index, inner
) -> None:
    """直接SecretStr構築でも原入力や別例外を露出しない。"""
    from pydantic import SecretStr

    model, values, _ = _initial_transport_response_values()[index]
    name = "device_credential" if index == 0 else "recording_right_proof"
    with pytest.raises(ValidationError) as caught:
        model.model_validate({**values, name: cast(Any, SecretStr)(inner)})
    assert "raw-private-value" not in str(caught.value)
    assert caught.value.__context__ is None
