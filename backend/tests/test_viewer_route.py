"""閲覧routeのC2外形と実効版の拒否境界を確認する。"""

from contextlib import contextmanager, nullcontext
from typing import cast
from uuid import UUID

import pytest
from fastapi import HTTPException

from pitchlog.api.routers import viewer
from pitchlog.api.tenant_access import TenantMatchedRoute
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.started_read import StartedReadNotVisible
from pitchlog.repositories.viewer_probe import ViewerProbe, ViewerProbeNotVisible

_GAME = UUID("22222222-2222-4222-8222-222222222222")
_VERSION = "ve1_" + "a" * 64


def test_routes_keep_tenant_matched_c2_and_head_shape(monkeypatch) -> None:
    """閲覧2routeは認証済みtenantを同じ境界で要求する。"""
    assert all(type(route) is TenantMatchedRoute for route in viewer.router.routes)
    assert viewer.router.route_class is TenantMatchedRoute
    tenant = cast(TenantContext, object())
    monkeypatch.setattr(
        viewer, "started_snapshot_read_scope", lambda actual: nullcontext(actual)
    )
    monkeypatch.setattr(
        viewer,
        "read_viewer_probe",
        lambda actual, game: ViewerProbe("in_progress", 1, 2, _VERSION),
    )
    assert viewer.read_game_viewer_head(_GAME, tenant).model_dump() == {
        "status": "in_progress",
        "version": _VERSION,
        "watermark": "2",
    }
    monkeypatch.setattr(
        viewer,
        "read_viewer_probe",
        lambda *_: (_ for _ in ()).throw(ViewerProbeNotVisible()),
    )
    with pytest.raises(HTTPException) as error:
        viewer.read_game_viewer_head(_GAME, tenant)
    assert error.value.status_code == 404


def test_body_requires_exact_head_and_reaches_current_p3_reader(monkeypatch) -> None:
    """同水位P3を一律503にせず、真正current readerまで進める。"""
    tenant = cast(TenantContext, object())
    calls: list[str] = []
    monkeypatch.setattr(
        viewer, "started_snapshot_read_scope", lambda actual: nullcontext(actual)
    )
    monkeypatch.setattr(
        viewer,
        "read_viewer_probe",
        lambda *_: ViewerProbe("in_progress", 1, 2, _VERSION, True),
    )

    def read(*_, **__):
        calls.append("current")
        return StartedReadNotVisible()

    monkeypatch.setattr(viewer, "read_viewer_prefix", read)
    with pytest.raises(HTTPException) as mismatch:
        viewer.read_game_viewer_saved(_GAME, tenant, expected_version="ve1_" + "b" * 64)
    assert mismatch.value.status_code == 503
    assert calls == []
    with pytest.raises(HTTPException) as missing:
        viewer.read_game_viewer_saved(_GAME, tenant, expected_version=_VERSION)
    assert missing.value.status_code == 404
    assert calls == ["current"]


@pytest.mark.parametrize("display_status", ["finished", "in_progress"])
def test_finished_body_uses_existing_same_tx_display_lifetime(
    monkeypatch, display_status
) -> None:
    """終了時だけ既貸与scope内で読み、終了不一致/未供給は503へ閉じる。"""
    tenant = cast(TenantContext, object())
    active = []
    calls = []
    monkeypatch.setattr(viewer, "started_snapshot_read_scope", nullcontext)
    monkeypatch.setattr(
        viewer, "read_viewer_probe", lambda *_: ViewerProbe("finished", 1, 2, _VERSION)
    )

    @contextmanager
    def display_scope(scope, game):
        assert scope is tenant and game == _GAME
        active.append(True)
        try:
            yield {"status": display_status}
        finally:
            active.pop()

    def read(*_, **__):
        assert active == [True]
        calls.append("in-display-scope")
        raise RuntimeError("実原本未供給の対向")

    monkeypatch.setattr(viewer, "lifecycle_display_scope", display_scope)
    monkeypatch.setattr(viewer, "read_viewer_prefix", read)
    with pytest.raises(HTTPException) as closed:
        viewer.read_game_viewer_saved(_GAME, tenant, expected_version=_VERSION)
    assert closed.value.status_code == 503
    assert calls == (["in-display-scope"] if display_status == "finished" else [])
    assert active == []


def test_in_progress_body_does_not_add_lifecycle_display_read(monkeypatch) -> None:
    """通常閲覧は終了貸与を追加せず、元の可視性拒否を保持する。"""
    tenant = cast(TenantContext, object())
    monkeypatch.setattr(viewer, "started_snapshot_read_scope", nullcontext)
    monkeypatch.setattr(
        viewer,
        "read_viewer_probe",
        lambda *_: ViewerProbe("in_progress", 1, 2, _VERSION),
    )

    def forbidden(*_):
        raise AssertionError("通常readへ終了scopeを追加していない")

    monkeypatch.setattr(viewer, "lifecycle_display_scope", forbidden)
    monkeypatch.setattr(
        viewer, "read_viewer_prefix", lambda *_, **__: StartedReadNotVisible()
    )
    with pytest.raises(HTTPException) as missing:
        viewer.read_game_viewer_saved(_GAME, tenant, expected_version=_VERSION)
    assert missing.value.status_code == 404


def test_visible_finished_v3_is_unsupported_503_not_notvisible_404(monkeypatch) -> None:
    """終了NPと異なるv3本文は、真正scopeの後も未供給503に閉じる。"""
    from types import SimpleNamespace

    from pitchlog.api.routers import started_games
    from pitchlog.repositories.ordinary_prefix_read import OrdinaryPrefixView
    from pitchlog.repositories.started_read import StartedGameView

    tenant = cast(TenantContext, object())
    monkeypatch.setattr(viewer, "started_snapshot_read_scope", nullcontext)
    monkeypatch.setattr(
        viewer, "read_viewer_probe", lambda *_: ViewerProbe("finished", 1, 2, _VERSION)
    )
    monkeypatch.setattr(
        viewer,
        "lifecycle_display_scope",
        lambda *_: nullcontext({"status": "finished"}),
    )
    # metadata整形は本unitの対象外。成功DTO/権限資格は作らない。
    monkeypatch.setattr(
        started_games, "_read", lambda _: SimpleNamespace(model_dump=lambda **_: {})
    )
    monkeypatch.setattr(
        viewer,
        "read_viewer_prefix",
        lambda *_, **__: OrdinaryPrefixView(
            cast(StartedGameView, object()), {"profile": "lineup-prefix-read-v3"}
        ),
    )
    with pytest.raises(HTTPException) as unsupported:
        viewer.read_game_viewer_saved(_GAME, tenant, expected_version=_VERSION)
    assert unsupported.value.status_code == 503
