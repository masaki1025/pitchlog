"""記録済み試合の毎球CSV・サイドカーを単一ZIPで返す。"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.exports.archive import (
    CompletedPlayArchive,
    ExportLimits,
    ExportSnapshot,
    PlayExportArchiveError,
    prepare_play_archive,
)
from pitchlog.exports.csv import CsvSerializationError
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.play_export import (
    PlayExportNotVisible,
    PlayExportSnapshotChanged,
    PlayExportSourceUnavailable,
    iter_play_rows,
    iter_sidecar_rows,
    read_play_export_source,
)
from pitchlog.repositories.transaction import tenant_export_read_scope

router = APIRouter(tags=["毎球CSV"], route_class=TenantMatchedRoute)

_ARCHIVE_SHA256_HEADER = "X-Pitchlog-Archive-SHA256"


def _tables(source) -> dict[str, Iterator]:
    """全10CSVを同じsourceの反復子として渡す。"""
    return {
        name: (
            iter_play_rows(source)
            if name == "plays.csv"
            else iter_sidecar_rows(source, name)
        )
        for name in CSV_HEADERS
    }


def _export_snapshot(source) -> ExportSnapshot:
    """リポジトリの版をZIP writerの版へ写す。"""
    return ExportSnapshot(
        game_id=source.snapshot.game_id,
        snapshot_id=source.snapshot.snapshot_id,
        source_versions=source.snapshot.source_versions,
        exported_at=source.snapshot.exported_at,
    )


def _stream(
    context_manager,
    archive: CompletedPlayArchive,
) -> Iterator[bytes]:
    """送出の成功・例外・切断の全経路で一時ZIPを閉じる。"""
    try:
        yield from archive.chunks()
    except BaseException:
        context_manager.__exit__(*sys.exc_info())
        raise
    else:
        context_manager.__exit__(None, None, None)


@router.get(
    "/games/{game_id}/exports/plays.zip",
    operation_id="game_play_csv_export",
    responses={
        200: {"content": {"application/zip": {}}},
        401: {"description": "認証が必要"},
        404: {"description": "不存在・別tenant・不可視"},
        409: {"description": "供給不足または出力版の変更"},
        503: {"description": "DB利用不能"},
    },
)
def export_play_csv(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> StreamingResponse:
    """同一REPEATABLE READで全資源を読み、完成ZIPだけを200で返す。"""
    context_manager = None
    archive: CompletedPlayArchive | None = None
    source = None
    try:
        with tenant_export_read_scope(context) as scope:
            source = read_play_export_source(scope, game_id)
            context_manager = prepare_play_archive(
                _export_snapshot(source),
                _tables(source),
                limits=ExportLimits(),
            )
            archive = context_manager.__enter__()
    except PlayExportNotVisible:
        raise HTTPException(status_code=404) from None
    except PlayExportSourceUnavailable:
        raise
    except (
        PlayExportArchiveError,
        PlayExportSupplyError,
        CsvSerializationError,
        OSError,
    ):
        raise HTTPException(status_code=500) from None
    except Exception:
        # DB/RG1/型の失敗は内部値を出さない非成功へ閉じる。
        raise HTTPException(status_code=503) from None

    if context_manager is None or archive is None or source is None:
        raise HTTPException(status_code=503)

    # 送出直前に別snapshotで可視性と版を再確認する。変わっていれば送らない。
    try:
        with tenant_export_read_scope(context) as verify_scope:
            verified = read_play_export_source(verify_scope, game_id)
            if (
                verified.snapshot.snapshot_id != source.snapshot.snapshot_id
                or verified.snapshot.source_versions != source.snapshot.source_versions
            ):
                raise PlayExportSnapshotChanged
    except PlayExportNotVisible:
        context_manager.__exit__(None, None, None)
        raise HTTPException(status_code=404) from None
    except PlayExportSnapshotChanged:
        context_manager.__exit__(None, None, None)
        raise
    except Exception:
        context_manager.__exit__(*sys.exc_info())
        raise HTTPException(status_code=503) from None

    headers = {
        "Content-Disposition": f'attachment; filename="{archive.filename}"',
        "Content-Length": str(archive.byte_length),
        _ARCHIVE_SHA256_HEADER: archive.sha256,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(
        _stream(context_manager, archive),
        media_type="application/zip",
        headers=headers,
    )
