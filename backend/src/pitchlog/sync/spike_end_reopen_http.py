"""試合ライフサイクルspike専用の読取入口。

製品の ``create_app`` には既定で接続しない。実認証済み tenant の保存済み
イベントだけを D1 順に畳み、終了確定版・再開による失効・次の D1/D2 を返す。
書込みは行わない。終了・再開・再終了は既存 ``POST /games/{id}/sync/events``
へ送る。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException

from pitchlog.api.tenant_access import TenantMatchedRoute
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.database_errors import DATABASE_ERRORS
from pitchlog.repositories.started_read import (
    StartedGameView,
    StartedReadCorrupt,
    StartedReadNotVisible,
    StartedReadRecorded,
    StartedRecordedView,
    read_started_game,
)
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync.d4_reference import encode_d4_reference
from pitchlog.sync.spike_end_reopen_ports import (
    event_row,
    fold_lifecycle,
    set_fault,
)
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    GameReadToken,
    RecordingGenerationReadToken,
)

_TENANT_ACCESS = Callable[..., TenantContext]


def _cell(row: tuple[object, ...], columns: tuple[str, ...], name: str) -> object:
    """固定列順から 1 値を読む。"""
    return row[columns.index(name)]


def _plain(value: object) -> object:
    """Immutable な JSON 値を素の値へ戻す。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _digest(value: object) -> str:
    """正準 JSON の SHA-256 を返す。"""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _state_view(state: Mapping[str, object]) -> dict[str, object]:
    """状態の閉じた表示形を返す。"""
    view: dict[str, object] = {
        "stateFields": _plain(state.get("stateFields")),
        "scoreboard": _plain(state.get("scoreboard")),
    }
    cursors = state.get("battingOrderBySide")
    if cursors is not None:
        view["battingOrderBySide"] = _plain(cursors)
    return view


def _initial_state(scope: object, game_id: UUID) -> Mapping[str, object] | None:
    """イベントが無い試合の開始状態を返す。"""
    result = read_started_game(cast(Any, scope), game_id)
    if type(result) is StartedGameView:
        return result.before.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if type(result) is StartedRecordedView:
        return result.after.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if type(result) is StartedReadNotVisible:
        raise HTTPException(status_code=404)
    if type(result) is StartedReadRecorded:
        raise HTTPException(status_code=409)
    raise HTTPException(status_code=409)


def _build_router(tenant_access: _TENANT_ACCESS) -> APIRouter:
    """実認証の tenant 依存を受けた読取 router を作る。"""
    router = APIRouter(route_class=TenantMatchedRoute)

    @router.get(
        "/spike/games/{game_id}/lifecycle",
        operation_id="spike_end_reopen_read",
    )
    def read_lifecycle(
        game_id: UUID,
        context: TenantContext = Depends(tenant_access),
    ) -> dict[str, object]:
        """保存済みイベントから現在状態と終了確定版を返す。"""
        try:
            with tenant_transaction_scope(context) as scope:
                rows = scope.run(RecordingGenerationReadToken(game_id)).rows
                if len(rows) == 0:
                    raise HTTPException(status_code=404)
                if len(rows) != 1:
                    raise HTTPException(status_code=409)
                row = rows[0]
                generation = _cell(
                    row, RECORDING_GENERATION_READ_COLUMNS, "generation"
                )
                watermark = _cell(
                    row,
                    RECORDING_GENERATION_READ_COLUMNS,
                    "confirmed_watermark",
                )
                if type(generation) is not int or type(watermark) is not int:
                    raise HTTPException(status_code=409)
                status, current, finalizations, next_d2, truncated = (
                    fold_lifecycle(scope, game_id, generation, watermark)
                )
                if current is None:
                    current = _initial_state(scope, game_id)
                if current is None:
                    raise HTTPException(status_code=409)
                current_plain = _state_view(current)
                state_digest = _digest(current_plain)
                enriched: list[dict[str, object]] = []
                for item in finalizations:
                    state = cast(Mapping[str, object], item["state"])
                    value = {
                        "version": item["version"],
                        "d1": item["d1"],
                        "d5": item["d5"],
                        "state": state,
                        "stateDigest": _digest(state),
                        "finalizationDigest": _digest(
                            {
                                "gameId": str(game_id),
                                "version": item["version"],
                                "d1": item["d1"],
                                "d5": item["d5"],
                                "state": state,
                            }
                        ),
                        "invalidatedBy": item["invalidatedBy"],
                    }
                    enriched.append(value)
                active = next(
                    (
                        item
                        for item in enriched
                        if item["invalidatedBy"] is None
                    ),
                    None,
                )
                if status != "finished":
                    active = None
                next_finalization: dict[str, object] | None = None
                if status == "in_progress":
                    last = enriched[-1] if enriched else None
                    if last is None:
                        next_finalization = {"version": 1, "previous": None}
                    else:
                        last_version = last.get("version")
                        if type(last_version) is not int:
                            raise HTTPException(status_code=409)
                        next_finalization = {
                            "version": last_version + 1,
                            "previous": {
                                "version": last_version,
                                "d1": last["d1"],
                            },
                        }
                d4 = encode_d4_reference(context.tenant_id, game_id, generation)
                events: list[dict[str, object]] = []
                upper = min(watermark, 512)
                for d1 in range(1, upper + 1):
                    event = event_row(scope, game_id, generation, d1)
                    if event is None:
                        continue
                    events.append(
                        {
                            "d1": d1,
                            "d5": str(event["d5"]),
                            "eventKind": event["event_kind"],
                            "action": (
                                None
                                if event["event_kind"] != "game_end_declaration"
                                else _event_action(event)
                            ),
                            "version": (
                                None
                                if event["event_kind"] != "game_end_declaration"
                                else _event_version(event)
                            ),
                            "targetD1": (
                                None
                                if event["event_kind"] != "game_end_declaration"
                                else _event_target_d1(event)
                            ),
                        }
                    )
                response = {
                    "gameId": str(game_id),
                    "status": status,
                    "generation": generation,
                    "d4": d4,
                    "watermark": watermark,
                    "nextD1": watermark + 1,
                    "nextD2": next_d2,
                    "truncated": truncated,
                    "stateDigest": state_digest,
                    "currentState": current_plain,
                    "activeFinalization": active,
                    "nextFinalization": next_finalization,
                    "finalizations": enriched,
                    "events": events,
                }
                return cast(dict[str, object], _plain(response))
        except HTTPException:
            raise
        except (StartedReadCorrupt, ValueError, TypeError, RuntimeError):
            raise HTTPException(status_code=409) from None
        except DATABASE_ERRORS:
            raise HTTPException(status_code=503) from None

    @router.post(
        "/spike/games/{game_id}/lifecycle/fault",
        operation_id="spike_end_reopen_fault",
    )
    def set_lifecycle_fault(
        game_id: UUID,
        payload: Annotated[dict[str, Any], Body(...)],
        context: TenantContext = Depends(tenant_access),
    ) -> dict[str, object]:
        """Spike の実DB故障注入点を設定する。イベントや状態は書かない。"""
        raw = payload.get("point")
        point: str | None = None
        if raw is not None:
            if type(raw) is not str:
                raise HTTPException(status_code=422)
            point = cast(str, raw)
        if point not in (None, "after_lifecycle_projection"):
            raise HTTPException(status_code=422)
        try:
            with tenant_transaction_scope(context) as scope:
                if not scope.run(GameReadToken(game_id)).rows:
                    raise HTTPException(status_code=404)
            set_fault(game_id, point)
        except ValueError:
            raise HTTPException(status_code=422) from None
        return {"fault": point}

    return router


def _event_payload(event: Mapping[str, object]) -> Mapping[str, object] | None:
    """保存済み V7 の封筒を返す。"""
    value = event.get("payload")
    return value if isinstance(value, Mapping) else None


def _finalization(event: Mapping[str, object]) -> Mapping[str, object] | None:
    """保存済み V7 の finalization を返す。"""
    payload = _event_payload(event)
    if payload is None or payload.get("formatVersion") != "game-lifecycle-spike-v1":
        return None
    value = payload.get("finalization")
    return value if isinstance(value, Mapping) else None


def _event_action(event: Mapping[str, object]) -> object:
    """表示用の action を返す。"""
    payload = _event_payload(event)
    return None if payload is None else payload.get("action")


def _event_version(event: Mapping[str, object]) -> object:
    """表示用の版を返す。"""
    value = _finalization(event)
    return None if value is None else value.get("version")


def _event_target_d1(event: Mapping[str, object]) -> object:
    """表示用の失効対象 D1 を返す。"""
    value = _finalization(event)
    if value is None:
        return None
    target = value.get("target")
    return target.get("d1") if isinstance(target, Mapping) else None


def install(app: Any, *, tenant_access: _TENANT_ACCESS) -> None:
    """create_app() 済み app へ lifecycle 読取入口を後付けする（試験専用）。"""
    app.include_router(_build_router(tenant_access))


__all__ = ("install",)
