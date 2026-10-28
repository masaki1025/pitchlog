"""初球ball専用PlayRowの固定SQL登録。DB印/実Portは別境界。"""

from __future__ import annotations

import math
import re
from dataclasses import fields, replace
from typing import cast
from uuid import UUID

from sqlalchemy import Table, bindparam, insert, select

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.repositories.operation_registration import (
    OperationPreflight,
    OperationRegistration,
    PreparedOperation,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.first_ball_tokens import (
    FirstBallPlayRowInsertToken,
    FirstBallPlayRowReadToken,
)
from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

_ERROR = "初球PlayRowの投影値又は原イベントが一致しません"
_PLAYS = cast(Table, PlayRow.__table__)
_EVENT_COLUMNS = tuple(OperationEvent.__table__.c.keys())
_LEDGER_COLUMNS = tuple(IdempotencyLedger.__table__.c.keys())
PLAY_ROW_COLUMNS = tuple(_PLAYS.c.keys())
_INPUT_COLUMNS = (
    "id",
    "game_id",
    "source_event_id",
    "batter_id",
    "pitcher_id",
    "catcher_id",
    "pitch_type_key",
    "course_x",
    "course_y",
    "pitch_speed",
    "stance",
    "batting_side",
)
_CONSTANTS = {
    "play_number": 1,
    "batting_order": 1,
    "event_kind": "pitch",
    "batting_result_key": "batting-result.ball",
    "version": 1,
    "migration_unverified": False,
}
# 41列を明示し、defaultや未知列への暗黙書込を作らない。
_NULL_COLUMNS = (
    "strategy_key",
    "strategy_detail_key",
    "strategy_result_key",
    "batter_status",
    "secondary_batting_result_key",
    "raw_fielder_position",
    "resolved_fielder_id",
    "batted_ball_type",
    "batted_ball_strength",
    "hit_x",
    "hit_y",
    "pickoff_type",
    "pickoff_detail",
    "error_type",
    "raw_error_position",
    "resolved_error_player_id",
    "press",
    "fake_run",
    "comment",
    "hidden_at",
    "legacy_row_identifier",
    "import_batch_id",
)
_INSERT_COLUMNS = ("tenant_id", *_INPUT_COLUMNS, *_CONSTANTS, *_NULL_COLUMNS)
if set(_INSERT_COLUMNS) != set(PLAY_ROW_COLUMNS) or len(_INSERT_COLUMNS) != len(
    PLAY_ROW_COLUMNS
):
    raise RuntimeError("初球PlayRowの固定全列宣言がmodelと不一致")
_INSERT = insert(_PLAYS).values({name: bindparam(name) for name in _INSERT_COLUMNS})
_READ = (
    select(*_PLAYS.c)
    .where(
        _PLAYS.c.tenant_id == bindparam("tenant_id"),
        _PLAYS.c.game_id == bindparam("game_id"),
        _PLAYS.c.source_event_id == bindparam("source_event_id"),
        _PLAYS.c.hidden_at.is_(None),
        _PLAYS.c.import_batch_id.is_(None),
        _PLAYS.c.legacy_row_identifier.is_(None),
        _PLAYS.c.migration_unverified == bindparam("migration_unverified"),
    )
    .limit(bindparam("limit"))
)


class FirstBallOperationError(ValueError):
    """入力値や資格を含めない固定の非成功。"""


def _validate_read(token: TenantOperationToken) -> FirstBallPlayRowReadToken:
    """型とUUIDを検査し、値の修復を行わない。"""
    if type(token) is not FirstBallPlayRowReadToken:
        raise FirstBallOperationError(_ERROR)
    if (
        type(getattr(token, "game_id", None)) is not UUID
        or type(getattr(token, "source_event_id", None)) is not UUID
    ):
        raise FirstBallOperationError(_ERROR)
    return token


def _validate_insert(token: TenantOperationToken) -> FirstBallPlayRowInsertToken:
    """物理値の範囲だけを検査し、座標や野球結果を計算しない。"""
    if type(token) is not FirstBallPlayRowInsertToken or not all(
        hasattr(token, item.name) for item in fields(FirstBallPlayRowInsertToken)
    ):
        raise FirstBallOperationError(_ERROR)
    if any(
        type(getattr(token, field)) is not UUID
        for field in (
            "id",
            "game_id",
            "source_event_id",
            "d5",
            "batter_id",
            "pitcher_id",
            "catcher_id",
        )
    ):
        raise FirstBallOperationError(_ERROR)
    if (
        type(token.generation) is not int
        or not 1 <= token.generation <= 2**63 - 1
        or type(token.d1) is not int
        or token.d1 != 1
        or type(token.d2) is not int
        or not -(2**63) <= token.d2 <= 2**63 - 1
        or type(token.source_fingerprint) is not str
        or re.fullmatch(r"(?:wire-v1:)?[0-9a-f]{64}", token.source_fingerprint) is None
        or type(token.pitch_type_key) is not str
        or not token.pitch_type_key
        or type(token.course_x) is not float
        or not math.isfinite(token.course_x)
        or not 0 <= token.course_x <= 1
        or type(token.course_y) is not float
        or not math.isfinite(token.course_y)
        or not 0 <= token.course_y <= 1
        or (
            token.pitch_speed is not None
            and (
                type(token.pitch_speed) is not float
                or not math.isfinite(token.pitch_speed)
            )
        )
        or (
            token.stance is not None
            and (
                type(token.stance) is not str
                or re.fullmatch(r"(?:[1-9]|1[0-9]|2[0-5])", token.stance) is None
            )
        )
        or (
            token.batting_side is not None
            and (
                type(token.batting_side) is not str
                or token.batting_side not in ("右", "左")
            )
        )
    ):
        raise FirstBallOperationError(_ERROR)
    return token


def _prepare_insert(token: TenantOperationToken) -> PreparedOperation:
    """文脈tenant以外の全列を固定集合から供給する。"""
    value = _validate_insert(token)
    return _INSERT, (
        {name: getattr(value, name) for name in _INPUT_COLUMNS}
        | _CONSTANTS
        | dict.fromkeys(_NULL_COLUMNS)
    )


def _prepare_read(token: TenantOperationToken) -> PreparedOperation:
    """自由なlimit/tenant条件を受けず最大2行に固定する。"""
    value = _validate_read(token)
    return _READ, {
        "game_id": value.game_id,
        "source_event_id": value.source_event_id,
        "limit": 2,
        "migration_unverified": False,
    }


def _one(result: TenantOperationResult, columns: tuple[str, ...]) -> dict[str, object]:
    """現行1行と正確な列数以外を拒否する。"""
    if (
        type(result) is not TenantOperationResult
        or type(result.rows) is not tuple
        or len(result.rows) != 1
        or type(result.rows[0]) is not tuple
        or len(result.rows[0]) != len(columns)
    ):
        raise FirstBallOperationError(_ERROR)
    return dict(zip(columns, result.rows[0], strict=True))


def _preflight(
    token: TenantOperationToken, parameters: dict[str, object]
) -> OperationPreflight:
    """同handleの既event/台帳と既存投影の有無を照合する宣言だけを返す。"""
    value = replace(_validate_insert(token))
    # prepare結果を差し替えて検証した行と別のINSERTへ向けない。
    _, expected = _prepare_insert(value)
    tenant = parameters.get("tenant_id")
    if type(tenant) is not UUID or set(parameters) != set(expected) | {"tenant_id"}:
        raise FirstBallOperationError(_ERROR)
    if any(
        type(parameters[k]) is not type(v) or parameters[k] != v
        for k, v in expected.items()
    ):
        raise FirstBallOperationError(_ERROR)

    def validate(results: tuple[TenantOperationResult, ...]) -> None:
        """閉じた同tenant原本だけを受け入れ、資格を推定しない。"""
        if type(results) is not tuple or len(results) != 3:
            raise FirstBallOperationError(_ERROR)
        event = _one(results[0], _EVENT_COLUMNS)
        ledger = _one(results[1], _LEDGER_COLUMNS)
        expected_event = {
            "tenant_id": tenant,
            "id": value.source_event_id,
            "game_id": value.game_id,
            "generation": value.generation,
            "d1": value.d1,
            "d2": value.d2,
            "d5": value.d5,
            "event_kind": "play_input",
            "ledger_kind": "accepted",
            "replaced_at": None,
            "retired_at": None,
            "import_batch_id": None,
            "legacy_row_identifier": None,
            "migration_unverified": False,
            "is_tombstone": False,
            "target_generation": None,
            "target_d1": None,
            "expected_version": None,
            "change_order": None,
        }
        expected_ledger = {
            "tenant_id": tenant,
            "d5": value.d5,
            "kind": "accepted",
            "source_fingerprint": value.source_fingerprint,
            "retired_at": None,
        }
        for observed, wanted in ((event, expected_event), (ledger, expected_ledger)):
            if any(
                type(observed[k]) is not type(v) or observed[k] != v
                for k, v in wanted.items()
            ):
                raise FirstBallOperationError(_ERROR)
        prior = results[2]
        if (
            type(prior) is not TenantOperationResult
            or type(prior.rows) is not tuple
            or prior.rows
        ):
            raise FirstBallOperationError(_ERROR)

    return OperationPreflight(
        (
            OperationEventReadToken(value.game_id, value.generation, value.d1),
            IdempotencyLedgerReadToken(value.d5),
            FirstBallPlayRowReadToken(value.game_id, value.source_event_id),
        ),
        validate,
    )


# 初球ballだけの正式登録。真正frame/権利/DB核印は呼出側とDBで別に要求する。
FIRST_BALL_PLAY_OPERATIONS = (
    OperationRegistration(
        FirstBallPlayRowInsertToken,
        "CAP:play_rows:insert",
        _INSERT,
        _PLAYS.c.tenant_id,
        _prepare_insert,
        preflight=_preflight,
    ),
    OperationRegistration(
        FirstBallPlayRowReadToken,
        "CAP:play_rows:read",
        _READ,
        _PLAYS.c.tenant_id,
        _prepare_read,
        required_bindings=(
            RequiredBinding(
                _PLAYS.c.migration_unverified, "migration_unverified", False
            ),
        ),
        required_limit_parameter="limit",
        required_limit_max=2,
    ),
)
