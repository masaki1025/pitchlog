"""完成ZIPの送出直前拒否と一時ファイルcleanupの単体検査。"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from pitchlog.api.routers import game_exports
from pitchlog.exports.archive import ExportSnapshot
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.play_export import PlayExportNotFound


@pytest.mark.parametrize(
    "cause,status",
    [("revoked", 401), ("tenant", 404), ("hidden", 404), ("database", 503)],
)
def test_rejected_delivery_closes_completed_files(
    monkeypatch, cause: str, status: int
) -> None:
    """認可撤回/非可視/DB故障なら完成済みZIPでも200を返さない。"""
    tenant, game = UUID(int=1), UUID(int=2)
    context = Mock(spec=TenantContext, tenant_id=tenant)
    order = []
    files = []
    original_file = game_exports.tempfile.TemporaryFile

    def temporary_file(*args, **kwargs):
        file = original_file(*args, **kwargs)
        files.append(file)
        return file

    @contextmanager
    def scope(_context):
        yield object()

    def issue(*_args):
        # ZIPが完成した後の検証であることを、実際の先頭signatureで確認する。
        order.append("fresh-authorization")
        assert any(not file.closed and file.read(2) == b"PK" for file in files)
        if cause == "revoked":
            return None
        if cause == "tenant":
            return SimpleNamespace(tenant_id=UUID(int=9)), None
        return context, None

    def visibility(*_args):
        order.append("fresh-visibility")
        if cause == "hidden":
            raise PlayExportNotFound()
        raise RuntimeError("private database detail")

    from pitchlog.repositories import tenant_context_issuance

    monkeypatch.setattr(game_exports.tempfile, "TemporaryFile", temporary_file)
    monkeypatch.setattr(game_exports, "play_export_read_scope", scope)
    monkeypatch.setattr(game_exports, "read_play_export", lambda *_args: object())
    monkeypatch.setattr(game_exports, "missing_supply_columns", lambda _: ())
    snapshot = ExportSnapshot(game, "a" * 64, "a" * 64, "2026-11-07 00:00:00")
    monkeypatch.setattr(
        game_exports,
        "build_play_export_tables",
        lambda _: (snapshot, {name: () for name in CSV_HEADERS}),
    )
    monkeypatch.setattr(
        tenant_context_issuance, "issue_tenant_context_from_presented_token", issue
    )
    monkeypatch.setattr(game_exports, "require_visible_export_game", visibility)
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(state=SimpleNamespace(token_presentation=object())),
        }
    )
    with pytest.raises(HTTPException) as failure:
        game_exports.download_play_csv(
            game, request, "unit-only-not-a-real-credential", context
        )
    assert failure.value.status_code == status
    assert order[0] == "fresh-authorization"
    assert all(file.closed for file in files)
