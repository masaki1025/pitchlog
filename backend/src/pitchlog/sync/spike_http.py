"""spike 用の 1 球同期 HTTP 入口を作り、既存 app へ後付けする。

製品の `pitchlog.api` 配下は経路数を規約試験が 17 本に固定しているため、この
入口は `api/` の外に置き、`create_app()` 済みの app へ `install(app)` で接続する。
層 (`sync/` → `api/`) の依存方向を保つため、テナント判定の依存
（`require_tenant_access` 相当）は `pitchlog.api` から import せず
`install(...)` の引数で受け取り、合成（どの依存を渡すか）は呼び出し側
（テスト・起動スクリプト）で行う。
wire 変換は `spike_wire` の S-1 型へ寄せてから同期核の `apply_sync_request`
を呼ぶ。本物のポートは `spike_ports.install(ports)` を起動時（または試験の
monkeypatch）に接続する前提で、ここでは渡されたまたは既定のスタブを束ねるだけ
にする。DB セッションの取得は `api/` に属さない既存の作法
（`repositories.transaction.tenant_transaction_scope`）をそのまま使う。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from pitchlog.db.recording_rights.models import RecordingGeneration
from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync.apply import apply_sync_request
from pitchlog.sync.model import (
    AcceptedChangeResult,
    AckResult,
    RejectedChangeResult,
    RequestShapeError,
    SyncRequest,
)
from pitchlog.sync.prefix_path import _cell
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.spike_ports import SpikeProjection, SpikeRights, SpikeValidator
from pitchlog.sync.spike_wire import to_sync_request
from pitchlog.sync.tokens import (
    GameReadToken,
    OperationEventOrderReadToken,
    RecordingGenerationReadToken,
)

_TENANT_ACCESS = Callable[..., TenantContext]
_GENERATION_COLUMNS = tuple(RecordingGeneration.__table__.c.keys())
_EVENT_COLUMNS = tuple(OperationEvent.__table__.c.keys())
_STATE_READ_LIMIT = 256

_REQUEST_ERROR_STATUS = 422
_GAME_NOT_FOUND_STATUS = 404
_BLOCKED_STATUS = 503
_NOT_IMPLEMENTED_STATUS = 501


class SpikeEventResultModel(BaseModel):
    """A5 の 1 件分。"""

    d4: str
    d1: int
    d5: str
    state: str
    reason: str | None = None


class SpikeSyncAckModel(BaseModel):
    """ACK 応答の 1 要求分。"""

    boundary_result: str
    advanced_d3: int
    b3_branch: str | None = None
    reason: str | None = None
    temporary_id_mapping: dict[str, str] = {}
    event_results: list[SpikeEventResultModel]


class SpikeSyncStateEventModel(BaseModel):
    """受理済みの操作イベント 1 件分。"""

    d5: str
    d1: int | None = None
    d2: int | None = None
    generation: int | None = None
    event_kind: str
    state_diff: dict[str, object]


class SpikeSyncStateModel(BaseModel):
    """spike 入口から見える現在の適用状態 1 通分。"""

    confirmed_watermark: int
    events: list[SpikeSyncStateEventModel]


def _build_sync_router(
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    tenant_access: _TENANT_ACCESS,
) -> APIRouter:
    """束ねたポートで 1 球入口だけを持つ router を作る。"""
    router = APIRouter()

    @router.post(
        "/games/{game_id:uuid}/sync/events",
        response_model=SpikeSyncAckModel,
    )
    def post_sync_events(
        game_id: UUID,
        payload: Annotated[dict[str, Any], Body(...)],
        context: TenantContext = Depends(tenant_access),
    ) -> SpikeSyncAckModel:
        """1 球の同期要求を S-1 型へ変換して同期核へ渡す。

        注釈の中に closure 変数 (`tenant_access`) を書かない。`from __future__
        import annotations` の文字列注釈の評価はモジュール全局を基準にする
        ため closure 変数は解決されず、FastAPI が依存を失って `context` を
        query param として扱う。`Depends(...)` は既定値の実値として渡す。
        """
        request: SyncRequest
        try:
            request = to_sync_request("P1", str(game_id), payload)
        except RequestShapeError as error:
            raise HTTPException(status_code=_REQUEST_ERROR_STATUS) from error
        result = apply_sync_request(context, request, rights, projection, validator)
        # B6 と 404 は自テナント不存在と同一の固定封筒に写す（value を出さない）。
        match result:
            case "B6":
                raise HTTPException(status_code=_GAME_NOT_FOUND_STATUS)
            case "B7":
                # spike のスタブゲートは停止しない。経路に入ることは未確認。
                raise HTTPException(status_code=_BLOCKED_STATUS)
            case AcceptedChangeResult() | RejectedChangeResult():
                # P3（変更・復旧）の経路はこの spike 入口の対象外。503 は
                # ③-a/⑧ の停止境界 B7 の意味を持つため、ChangeResult を 503 へ
                # 読み替えると状態の意味が濁る。一律のフォールバックではなく、
                # 未対応の明示として 501 Not Implemented を返す。
                raise HTTPException(status_code=_NOT_IMPLEMENTED_STATUS)
            case AckResult():
                return _ack_model(result)
            case _:
                raise RuntimeError("spike 入口が対応しない同期結果")

    @router.get(
        "/games/{game_id:uuid}/sync/state",
        response_model=SpikeSyncStateModel,
    )
    def read_sync_state(
        game_id: UUID,
        context: TenantContext = Depends(tenant_access),
    ) -> SpikeSyncStateModel:
        """spike 専用の再読込入口。設計提案ではなく spike の観察用の出口。

        適用済みの水位（`recording_generations.confirmed_watermark`）と
        受理済みのイベント（`operation_events` の現行行）を返す。ここで直接
        表を読むのは TSK-506 の製品経路を作る提案ではない。spike の横スライス
        の観察用に、DB セッションの取り方だけ既存ルータの作法に合わせる。
        """
        with tenant_transaction_scope(context) as scope:
            game_rows = scope.run(GameReadToken(game_id)).rows
            if not game_rows:
                raise HTTPException(status_code=_GAME_NOT_FOUND_STATUS)
            state_rows = scope.run(RecordingGenerationReadToken(game_id)).rows
            if len(state_rows) != 1:
                raise RuntimeError("spike 入口は現行の記録権世代 1 件だけを扱う")
            watermark = _cell(state_rows[0], _GENERATION_COLUMNS, "confirmed_watermark")
            if type(watermark) is not int:
                raise RuntimeError("確定水位が整数ではない")
            event_rows = scope.run(
                OperationEventOrderReadToken(game_id, -1, _STATE_READ_LIMIT)
            ).rows
        events: list[SpikeSyncStateEventModel] = []
        for row in event_rows:
            d1 = _cell(row, _EVENT_COLUMNS, "d1")
            d2 = _cell(row, _EVENT_COLUMNS, "d2")
            generation = _cell(row, _EVENT_COLUMNS, "generation")
            state_diff = _cell(row, _EVENT_COLUMNS, "state_diff")
            events.append(
                SpikeSyncStateEventModel(
                    d5=str(_cell(row, _EVENT_COLUMNS, "d5")),
                    d1=d1 if type(d1) is int else None,
                    d2=d2 if type(d2) is int else None,
                    generation=generation if type(generation) is int else None,
                    event_kind=str(_cell(row, _EVENT_COLUMNS, "event_kind")),
                    state_diff=state_diff if isinstance(state_diff, dict) else {},
                )
            )
        return SpikeSyncStateModel(confirmed_watermark=watermark, events=events)

    return router


def _ack_model(result: AckResult) -> SpikeSyncAckModel:
    """ACK 結果を応答の封筒へ写す。"""
    return SpikeSyncAckModel(
        boundary_result=result.boundary,
        advanced_d3=result.d3,
        b3_branch=result.b3_branch,
        reason=result.reason,
        temporary_id_mapping=dict(result.temporary_id_mapping),
        event_results=[
            SpikeEventResultModel(
                d4=item.d4,
                d1=item.d1,
                d5=item.d5,
                state=item.state,
                reason=item.reason,
            )
            for item in result.a5
        ],
    )


def install(
    app: Any,
    *,
    tenant_access: _TENANT_ACCESS,
    rights: RecordingRightsPort | None = None,
    projection: ProjectionPort | None = None,
    validator: ContentValidationPort | None = None,
) -> None:
    """create_app() 済み app へ spike の 1 球入口を後付けする。

    Args:
        app: 製品の `create_app()` が返した FastAPI app。型は循環 import を
            避けるため緩めて受ける。
        tenant_access: テナント判定と文脈発行の FastAPI 依存。`sync/` が
            `api/` に依存しないため、このモジュールは import せず引数で
            受け取る。製品の本命は `pitchlog.api.tenant_access.
            require_tenant_access` で、渡すかの判断（合成）は呼び出し側
            （テスト・起動スクリプト）が行う。
        rights: 記録権判定ポート。未指定なら spike のスタブを使う。呼び出し
            前に `spike_ports.install(ports)` か試験の monkeypatch で登録表へ
            接続しておくこと。
        projection: 投影ポート。未指定なら spike のスタブを使う。
        validator: 内容検証ポート。未指定なら spike のスタブを使う。
    """
    router = _build_sync_router(
        rights or SpikeRights(),
        projection or SpikeProjection(),
        validator or SpikeValidator(),
        tenant_access,
    )
    app.include_router(router)


__all__ = ("install",)
