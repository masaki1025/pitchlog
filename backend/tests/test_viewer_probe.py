"""閲覧版hintの可視性と非ロック読取を確認する。"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from pitchlog.api.routers import viewer
from pitchlog.api.tenant_access import TenantMatchedRoute
from pitchlog.db.game_state.models import Game
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.viewer_probe import (
    ViewerProbe,
    ViewerProbeNotVisible,
    ViewerProbeUnavailable,
    read_viewer_probe,
)
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    GameReadToken,
    RecordingGenerationReadToken,
)


def _row(columns, values):
    return tuple(values.get(column) for column in columns)


class _Scope:
    def __init__(self, *, tenant, game_id, status="in_progress", watermark=2):
        self._bound_tenant_id = tenant
        self.game_id = game_id
        self.status = status
        self.watermark = watermark
        self.calls = []
        self.changed = False
        self.missing = False
        self.foreign = False

    def run(self, token):
        self.calls.append(token)
        if type(token) is GameReadToken:
            if self.missing:
                return TenantOperationResult(())
            columns = tuple(Game.__table__.c.keys())
            return TenantOperationResult(
                (
                    _row(
                        columns,
                        {
                            "tenant_id": (
                                uuid4() if self.foreign else self._bound_tenant_id
                            ),
                            "id": self.game_id,
                            "status": self.status,
                            "started_at": datetime(2026, 11, 6, tzinfo=UTC),
                        },
                    ),
                )
            )
        assert type(token) is RecordingGenerationReadToken
        columns = RECORDING_GENERATION_READ_COLUMNS
        value = self.watermark + int(self.changed and len(self.calls) > 2)
        return TenantOperationResult(
            (
                _row(
                    columns,
                    {
                        "tenant_id": self._bound_tenant_id,
                        "game_id": self.game_id,
                        "generation": 1,
                        "kind": "normal",
                        "confirmed_watermark": value,
                        "applied_prefix": value,
                    },
                ),
            )
        )


def test_nonlocking_probe_reads_only_registered_point_tokens():
    """版probeは既登録の非ロック点読取だけを使う。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4())
    assert read_viewer_probe(scope, scope.game_id) == ViewerProbe("in_progress", 1, 2)
    assert [type(token) for token in scope.calls] == [
        GameReadToken,
        RecordingGenerationReadToken,
        GameReadToken,
        RecordingGenerationReadToken,
    ]
    assert all(token.game_id == scope.game_id for token in scope.calls)


@pytest.mark.parametrize("change", ["missing", "foreign"])
def test_invisible_or_foreign_game_is_closed(change):
    """不可視試合と別tenantを同じ拒否へ写す。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4())
    setattr(scope, change, True)
    with pytest.raises(ViewerProbeNotVisible):
        read_viewer_probe(scope, scope.game_id)


def test_mixed_watermarks_are_rejected():
    """複数点読取に混在した版は成功へしない。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4())
    scope.changed = True
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)


def test_unconfirmed_or_nonstarted_not_displayed():
    """開始前と不正水位は表示へ供給しない。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4(), watermark=2)
    scope.status = "preparing"
    with pytest.raises(ViewerProbeNotVisible):
        read_viewer_probe(scope, scope.game_id)
    scope.status = "in_progress"
    scope.watermark = -1
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)


def test_route_uses_c2_and_distinguishes_invisible_from_failure(monkeypatch):
    """C2付きrouteの結果と固定非成功を分ける。"""
    assert all(type(route) is TenantMatchedRoute for route in viewer.router.routes)
    assert viewer.router.route_class is TenantMatchedRoute
    tenant = object()
    game_id = UUID("22222222-2222-4222-8222-222222222222")
    monkeypatch.setattr(
        viewer, "tenant_transaction_scope", lambda actual: nullcontext(actual)
    )
    monkeypatch.setattr(
        viewer,
        "read_viewer_probe",
        lambda actual, game: ViewerProbe("finished", 2, 7),
    )
    value = viewer.read_game_viewer_head(game_id, tenant)
    assert value.model_dump() == {
        "status": "finished",
        "generation": "2",
        "watermark": "7",
    }

    def unavailable(*_):
        raise ViewerProbeNotVisible

    monkeypatch.setattr(viewer, "read_viewer_probe", unavailable)
    with pytest.raises(HTTPException) as error:
        viewer.read_game_viewer_head(game_id, tenant)
    assert error.value.status_code == 404
    monkeypatch.setattr(viewer, "read_viewer_probe", lambda *_: 1 / 0)
    with pytest.raises(HTTPException) as error:
        viewer.read_game_viewer_head(game_id, tenant)
    assert error.value.status_code == 503
