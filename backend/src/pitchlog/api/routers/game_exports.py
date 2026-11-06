"""毎球CSVのtenant限定ZIPダウンロード候補。"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from pitchlog.api.request_presentation import require_presented_token
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.exports.archive import prepare_play_archive
from pitchlog.exports.play_export_csv import (
    build_play_export_tables,
    missing_supply_columns,
)
from pitchlog.exports.play_rows import PlayExportSupplyError
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.play_export import (
    PlayExportNotFound,
    read_play_export,
    require_visible_export_game,
)
from pitchlog.repositories.transaction import play_export_read_scope

router = APIRouter(tags=["毎球CSV"], route_class=TenantMatchedRoute)


def _unavailable_response(columns: tuple[int, ...]) -> JSONResponse:
    """未供給の列indexだけを返し、内部SQL/値を露出しない。"""
    fields = [{"location": f"plays_csv.columns.{index}"} for index in columns]
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "message": "毎球CSVの供給が不足しています",
                "code": "EXPORT_SOURCE_UNAVAILABLE",
                "fields": fields,
            }
        },
    )


def _copy_archive(archive, output) -> None:
    """完成ZIPを応答用一時ファイルへ写し、長さ/hashを確定する。"""
    for chunk in archive.chunks():
        output.write(chunk)
    output.seek(0)


@router.get(
    "/games/{game_id}/exports/plays.zip",
    operation_id="game_play_csv_export",
)
def download_play_csv(
    game_id: UUID,
    request: Request,
    value: Annotated[str, Depends(require_presented_token)],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> Response:
    """記録済み1試合の88列と全9サイドカーを単一ZIPで返す。"""
    try:
        with play_export_read_scope(context) as handle:
            bundle = read_play_export(handle, game_id)
            missing = missing_supply_columns(bundle)
            if missing:
                return _unavailable_response(missing)
            snapshot, tables = build_play_export_tables(bundle)
    except PlayExportNotFound:
        raise HTTPException(status_code=404) from None
    except PlayExportSupplyError:
        return _unavailable_response(tuple(range(88)))
    except Exception:
        raise HTTPException(status_code=503) from None

    output = tempfile.TemporaryFile(mode="w+b")
    try:
        with prepare_play_archive(snapshot, tables) as archive:
            _copy_archive(archive, output)
            filename = archive.filename
            digest = archive.sha256
            length = archive.byte_length
    except PlayExportSupplyError:
        output.close()
        return _unavailable_response(tuple(range(88)))
    except Exception:
        output.close()
        raise HTTPException(status_code=503) from None

    # C2が保持する入口contextを再利用して「再認可済み」とはしない。
    from pitchlog.repositories.tenant_context_issuance import (
        issue_tenant_context_from_presented_token,
    )

    try:
        fresh = issue_tenant_context_from_presented_token(
            value,
            request.app.state.token_presentation,
        )
        if fresh is None:
            raise HTTPException(status_code=401)
        if fresh[0].tenant_id != context.tenant_id:
            raise HTTPException(status_code=404)
        with play_export_read_scope(fresh[0]) as handle:
            require_visible_export_game(handle, game_id)
    except PlayExportNotFound:
        output.close()
        raise HTTPException(status_code=404) from None
    except HTTPException:
        output.close()
        raise
    except Exception:
        output.close()
        raise HTTPException(status_code=503) from None

    def chunks() -> Iterator[bytes]:
        try:
            while data := output.read(65536):
                yield data
        finally:
            output.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(length),
            "X-Pitchlog-Archive-SHA256": digest,
            "Cache-Control": "no-store",
        },
    )
