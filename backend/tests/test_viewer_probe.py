"""閲覧版hintの可視性と非ロック読取を確認する。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pitchlog.db.game_state.models import Game
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.viewer_probe import (
    ViewerProbeNotVisible,
    ViewerProbeUnavailable,
    read_viewer_probe,
)
from pitchlog.repositories.viewer_read import ViewerEffectiveVersionReadToken
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
        self.applied_override = None
        self.calls = []
        self.changed = False
        self.missing = False
        self.foreign = False
        self.raw_point = None
        self.point = {
            "checkpoint": {
                "id": str(uuid4()),
                "revision": 1,
                "history_version": 1,
                "confirmed_watermark": watermark,
                "applied_watermark": watermark,
                "content_digest": "a" * 64,
                "state": "current",
            },
            "p3": None,
            "lifecycle": None,
        }

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
        value = (
            self.watermark + 1
            if self.changed and len(self.calls) > 3
            else self.watermark
        )
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
                        "applied_prefix": (
                            value
                            if self.applied_override is None
                            else self.applied_override
                        ),
                    },
                ),
            )
        )

    def run_function(self, token):
        assert type(token) is ViewerEffectiveVersionReadToken
        self.calls.append(token)
        record = (
            self.raw_point if self.raw_point is not None else json.dumps(self.point)
        )
        return TenantOperationResult(((record,),))


def test_nonlocking_probe_reads_only_registered_point_tokens():
    """版probeは既登録の非ロック点読取だけを使う。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4())
    result = read_viewer_probe(scope, scope.game_id)
    assert (result.status, result.generation, result.watermark) == ("in_progress", 1, 2)
    assert result.version.startswith("ve1_") and len(result.version) == 68
    assert [type(token) for token in scope.calls] == [
        GameReadToken,
        RecordingGenerationReadToken,
        ViewerEffectiveVersionReadToken,
        GameReadToken,
        RecordingGenerationReadToken,
        ViewerEffectiveVersionReadToken,
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


@pytest.mark.parametrize("bad", [True, 1.0])
def test_watermark_bool_and_float_are_not_ints(bad):
    """同値比較でbool/float水位を真正整数へ読み替えない。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4(), watermark=1)
    checkpoint = scope.point["checkpoint"]
    assert type(checkpoint) is dict
    checkpoint["applied_watermark"] = bad
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)
    checkpoint["applied_watermark"] = 1
    scope.applied_override = bad
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)
    scope.applied_override = None
    scope.watermark = bad
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)


def test_same_watermark_p3_and_lifecycle_pointer_change_version():
    """D1を消費しない訂正と終了版のpoint更新を軽量版へ反映する。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4())
    before = read_viewer_probe(scope, scope.game_id).version
    scope.point["p3"] = {
        "capsule_id": str(uuid4()),
        "revision": 1,
        "source_set_digest": "b" * 64,
        "stats_version_id": str(uuid4()),
    }
    corrected = read_viewer_probe(scope, scope.game_id).version
    assert corrected != before
    assert read_viewer_probe(scope, scope.game_id).version == corrected
    scope.status = "finished"
    scope.point["lifecycle"] = {
        "last_version": 1,
        "is_finished": True,
        "active_receipt_id": str(uuid4()),
        "active_stats_version_id": str(uuid4()),
        "last_control_event_id": str(uuid4()),
    }
    assert read_viewer_probe(scope, scope.game_id).version != corrected


def test_zero_pitch_and_bad_point_are_closed():
    """開始直後だけCP欠損を許し、欠損・未知・別水位を拒否する。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4(), watermark=0)
    scope.point["checkpoint"] = None
    assert read_viewer_probe(scope, scope.game_id).watermark == 0
    scope.watermark = 1
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)
    scope.watermark = 0
    scope.point["p3"] = {"unknown": True}
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)


def test_unknown_or_duplicate_pointer_fails_closed():
    """版入力を後勝ちJSONや未知pointerへ拡張しない。"""
    scope = _Scope(tenant=uuid4(), game_id=uuid4())
    scope.raw_point = '{"checkpoint":null,"checkpoint":null,"p3":null,"lifecycle":null}'
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)
    scope.raw_point = None
    checkpoint = scope.point["checkpoint"]
    assert type(checkpoint) is dict
    checkpoint["content_digest"] = "not-a-digest"
    with pytest.raises(ViewerProbeUnavailable):
        read_viewer_probe(scope, scope.game_id)
