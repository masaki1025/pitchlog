"""毎球CSV ZIPのHTTP外形・エラー写像・一時成果の後始末を検査する。"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_authz_tenant_context import make_tenant_context

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.routers import game_exports
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.exports.archive import CompletedPlayArchive, ExportSnapshot
from pitchlog.repositories.play_export import (
    MissingSupply,
    PlayExportNotVisible,
    PlayExportSourceUnavailable,
)

GAME = uuid4()


def _archive_bytes() -> bytes:
    """独立readerで開ける最小ZIP。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("plays.csv", b"header\r\n")
        bundle.writestr("manifest.json", b"{}")
    return buffer.getvalue()


def _source(snapshot_id: str = "a" * 64) -> SimpleNamespace:
    """HTTPが読む版だけを持つ合成source。"""
    return SimpleNamespace(
        snapshot=SimpleNamespace(
            game_id=GAME,
            snapshot_id=snapshot_id,
            source_versions="b" * 64,
            exported_at="2026-11-06 10:00:00",
        )
    )


def _install_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """DBを開かず同じcontext managerの外形だけを返す。"""

    @contextmanager
    def scope(_context) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(game_exports, "tenant_export_read_scope", scope)


def _install_archive(
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
    *,
    enter_error: Exception | None = None,
    closed: list[bool] | None = None,
) -> None:
    """完成ZIPを返す、または生成失敗するcontext managerを設置する。"""
    archive = CompletedPlayArchive(
        file=io.BytesIO(data),
        filename=f"pitchlog-plays-{GAME}.zip",
        byte_length=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )

    @contextmanager
    def prepare(_snapshot, _tables, *, limits=None):
        if enter_error is not None:
            raise enter_error
        try:
            yield archive
        finally:
            if closed is not None:
                closed.append(True)

    monkeypatch.setattr(game_exports, "prepare_play_archive", prepare)
    monkeypatch.setattr(
        game_exports,
        "_export_snapshot",
        lambda source: ExportSnapshot(
            source.snapshot.game_id,
            source.snapshot.snapshot_id,
            source.snapshot.source_versions,
            source.snapshot.exported_at,
        ),
    )
    monkeypatch.setattr(game_exports, "_tables", lambda source: {})


def _app(context) -> FastAPI:
    """ルータと共通エラー封筒だけを持つ検証用アプリ。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(game_exports.router)
    app.dependency_overrides[require_tenant_access] = lambda: context
    return app


@pytest.mark.anyio
async def test_export_returns_completed_zip_with_length_and_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完成ZIPの長さ・全体SHA・保存禁止ヘッダを返す。"""
    context = make_tenant_context(uuid4())
    data = _archive_bytes()
    _install_scope(monkeypatch)
    _install_archive(monkeypatch, data)
    monkeypatch.setattr(
        game_exports, "read_play_export_source", lambda scope, game_id: _source()
    )

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-length"] == str(len(data))
    assert (
        response.headers["x-pitchlog-archive-sha256"]
        == hashlib.sha256(data).hexdigest()
    )
    assert response.headers["cache-control"] == "no-store"
    assert (
        f'filename="pitchlog-plays-{GAME}.zip"'
        in response.headers["content-disposition"]
    )


@pytest.mark.anyio
async def test_export_not_visible_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """不存在・別tenant・隠蔽は同じ404へ閉じる。"""
    context = make_tenant_context(uuid4())
    _install_scope(monkeypatch)

    def missing(_scope, _game_id):
        raise PlayExportNotVisible

    monkeypatch.setattr(game_exports, "read_play_export_source", missing)

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 404
    assert str(GAME) not in response.text


@pytest.mark.anyio
async def test_export_supply_shortage_is_409_with_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """供給不足は列index・列名・供給群だけを409へ返す。"""
    context = make_tenant_context(uuid4())
    _install_scope(monkeypatch)

    def missing(_scope, _game_id):
        raise PlayExportSourceUnavailable(
            (MissingSupply("球数", 34, "G04-A", "internal-producer"),)
        )

    monkeypatch.setattr(game_exports, "read_play_export_source", missing)

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["message"] == "毎球CSVの供給が不足しています"
    assert body["error"]["fields"] == [{"location": "missing_column.34.球数.G04-A"}]
    assert "internal-producer" not in response.text


@pytest.mark.anyio
async def test_export_snapshot_changed_is_409_and_discards_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """送出前の版変更は200にせず、完成済み一時成果を閉じる。"""
    context = make_tenant_context(uuid4())
    closed: list[bool] = []
    _install_scope(monkeypatch)
    _install_archive(monkeypatch, _archive_bytes(), closed=closed)
    calls = 0

    def source(_scope, _game_id):
        nonlocal calls
        calls += 1
        return _source("a" * 64 if calls == 1 else "c" * 64)

    monkeypatch.setattr(game_exports, "read_play_export_source", source)

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 409
    assert response.json()["error"]["fields"] == [
        {"location": "export_snapshot_changed"}
    ]
    assert closed == [True]


@pytest.mark.anyio
async def test_export_archive_failure_is_500_without_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ZIP生成失敗は部分成果を返さず安全な500へ閉じる。"""
    context = make_tenant_context(uuid4())
    _install_scope(monkeypatch)
    _install_archive(
        monkeypatch,
        b"",
        enter_error=game_exports.PlayExportArchiveError("disk"),
    )
    monkeypatch.setattr(
        game_exports, "read_play_export_source", lambda scope, game_id: _source()
    )

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 500
    assert "disk" not in response.text
    assert "application/zip" not in response.headers.get("content-type", "")


@pytest.mark.anyio
async def test_export_second_check_not_visible_is_404_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """再確認で撤回・削除を観測したらZIPを閉じ404にする。"""
    context = make_tenant_context(uuid4())
    closed: list[bool] = []
    _install_scope(monkeypatch)
    _install_archive(monkeypatch, _archive_bytes(), closed=closed)
    calls = 0

    def source(_scope, _game_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _source()
        raise PlayExportNotVisible

    monkeypatch.setattr(game_exports, "read_play_export_source", source)

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 404
    assert closed == [True]


@pytest.mark.anyio
async def test_export_without_presented_token_is_401() -> None:
    """認証なしは既存の401境界で拒否する。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(game_exports.router)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_export_db_failure_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB/RG1の失敗は内部値を出さず503へ閉じる。"""
    context = make_tenant_context(uuid4())

    @contextmanager
    def failing_scope(_context) -> Iterator[object]:
        raise RuntimeError("db detail")
        yield object()  # pragma: no cover

    monkeypatch.setattr(game_exports, "tenant_export_read_scope", failing_scope)

    async with AsyncClient(
        transport=ASGITransport(app=_app(context)), base_url="https://test"
    ) as client:
        response = await client.get(f"/games/{GAME}/exports/plays.zip")

    assert response.status_code == 503
    assert "db detail" not in response.text


def test_stream_close_closes_archive_context() -> None:
    """クライアント切断で反復子を閉じても一時ZIPを解放する。"""
    closed: list[bool] = []

    @contextmanager
    def context_manager():
        try:
            yield
        finally:
            closed.append(True)

    data = _archive_bytes()
    archive = CompletedPlayArchive(
        file=io.BytesIO(data),
        filename="pitchlog-plays.zip",
        byte_length=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    entered = context_manager()
    entered.__enter__()
    stream = cast(Generator[bytes, None, None], game_exports._stream(entered, archive))
    next(stream)
    stream.close()
    assert closed == [True]
