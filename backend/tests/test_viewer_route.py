"""閲覧routeのC2外形と実効版の拒否境界を確認する。"""

from contextlib import nullcontext
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
