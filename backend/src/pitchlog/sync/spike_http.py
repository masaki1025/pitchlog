"""spike 用の 1 球同期 HTTP 入口を作り、既存 app へ後付けする。

製品の `pitchlog.api` 配下は経路数を規約試験が固定しているため、この入口は
`api/` の外に置き、`create_app()` 済みの app へ `install(app)` で接続する。
認証と文脈発行は `require_tenant_access` に委ね、wire 変換は `spike_wire` の
S-1 型へ寄せてから同期核の `apply_sync_request` を呼ぶ。本物のポートは
`spike_ports.install(ports)` を起動時（または試験の monkeypatch）に接続する
前提で、ここでは渡されたまたは既定のスタブを束ねるだけにする。
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.sync.apply import apply_sync_request
from pitchlog.sync.model import (
    AckResult,
    RequestShapeError,
    SyncRequest,
)
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.spike_ports import SpikeProjection, SpikeRights, SpikeValidator
from pitchlog.sync.spike_wire import to_sync_request

_REQUEST_ERROR_STATUS = 422
_GAME_NOT_FOUND_STATUS = 404
_BLOCKED_STATUS = 503


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


def _build_sync_router(
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
) -> APIRouter:
    """束ねたポートで 1 球入口だけを持つ router を作る。"""

    @router.post(
        "/games/{game_id:uuid}/sync/events",
        response_model=SpikeSyncAckModel,
    )
    def post_sync_events(
        game_id: UUID,
        payload: Annotated[dict[str, Any], Body(...)],
        context: Annotated[TenantContext, Depends(require_tenant_access)],
    ) -> SpikeSyncAckModel:
        """1 球の同期要求を S-1 型へ変換して同期核へ渡す。"""
        request: SyncRequest
        try:
            request = to_sync_request("P1", str(game_id), payload)
        except RequestShapeError as error:
            raise HTTPException(status_code=_REQUEST_ERROR_STATUS) from error
        result = apply_sync_request(context, request, rights, projection, validator)
        # B6 と 404 は自テナント不存在と同一の固定封筒に写す（value を出さない）。
        if result == "B6":
            raise HTTPException(status_code=_GAME_NOT_FOUND_STATUS)
        if result == "B7":
            # spike のスタブゲートは停止しない。経路に入ることは未確認。
            raise HTTPException(status_code=_BLOCKED_STATUS)
        if not isinstance(result, AckResult):
            raise HTTPException(status_code=_BLOCKED_STATUS)
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

    return router


def install(
    app: Any,
    *,
    rights: RecordingRightsPort | None = None,
    projection: ProjectionPort | None = None,
    validator: ContentValidationPort | None = None,
) -> None:
    """create_app() 済み app へ spike の 1 球入口を後付けする。

    Args:
        app: 製品の `create_app()` が返した FastAPI app。型は循環 import を
            避けるため緩めて受ける。
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
    )
    app.include_router(router)


__all__ = ("install",)
