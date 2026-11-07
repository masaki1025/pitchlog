"""毎球CSVの私有同TX保存siteは自由SQLや欠列を受けない。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import select

from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.play_export_writer_operations import (
    SAVE_EXPORT_SNAPSHOT_OPERATION,
    PlayExportWriterCall,
    _SaveExportSnapshotCall,
    build_save_snapshot_call,
    decode_saved_play,
    require_private_save_call,
)
from pitchlog.sync.stats_native_hook import _NativeStatsSource


def _source() -> _NativeStatsSource:
    """値だけでは保存資格とならない試験用sourceを作る。"""
    return _NativeStatsSource(
        UUID(int=1),
        UUID(int=2),
        1,
        1,
        1,
        UUID(int=3),
        UUID(int=4),
        "a" * 64,
        "{}",
        "b" * 64,
        UUID(int=5),
        UUID(int=6),
        b"x" * 32,
    )


def _direct() -> dict[str, str | None]:
    """物理88列からSQL供給3列だけを引いた閉集合を用いる。"""
    return {
        name: None
        for name in CSV_HEADERS["plays.csv"]
        if name not in ("球数", "top_score", "bottom_score")
    }


def test_private_save_registration_and_exact_85_columns():
    """実登録/SQL/bindが一致し、欠列/増列/型混同は拒否する。"""
    call = build_save_snapshot_call(_source(), UUID(int=7), "c" * 64, 3, _direct())
    assert (
        FUNCTION_OPERATION_REGISTRY[_SaveExportSnapshotCall]
        is SAVE_EXPORT_SNAPSHOT_OPERATION
    )
    require_private_save_call(call, FUNCTION_OPERATION_REGISTRY)
    for change in (lambda d: d.pop("打席Id"), lambda d: d.update(extra="x")):
        direct = _direct()
        change(direct)
        with pytest.raises(FunctionOperationError):
            build_save_snapshot_call(_source(), UUID(int=7), "c" * 64, 3, direct)
    direct = cast(dict[str, Any], _direct())
    direct["打席Id"] = 0
    with pytest.raises(FunctionOperationError):
        build_save_snapshot_call(_source(), UUID(int=7), "c" * 64, 3, direct)
    with pytest.raises(FunctionOperationError):
        require_private_save_call(
            PlayExportWriterCall(select(1), call.parameters),
            FUNCTION_OPERATION_REGISTRY,
        )


def test_save_token_and_registration_cannot_be_forged():
    """値型の通常構築・異なるowner/SQL/返答を成功へしない。"""
    with pytest.raises(FunctionOperationError):
        _SaveExportSnapshotCall()
    with pytest.raises(FunctionOperationError):
        replace(SAVE_EXPORT_SNAPSHOT_OPERATION, function_id="stats_api.untrusted")
    with pytest.raises(FunctionOperationError):
        decode_saved_play((), UUID(int=8))
    with pytest.raises(FunctionOperationError):
        decode_saved_play(((UUID(int=9),),), UUID(int=8))
    decode_saved_play(((UUID(int=8),),), UUID(int=8))
