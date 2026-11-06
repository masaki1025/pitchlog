"""真正play writerの同一TXでCSV表示原本を一度だけ保存する。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.exports.record_projection import (
    RecordedExportProjectionUnavailable,
    project_recorded_direct,
)
from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.play_export_writer_operations import (
    build_save_snapshot_call,
    decode_saved_play,
    require_private_save_call,
)
from pitchlog.sync.play_export_identity import (
    PlayExportIdentityUnavailable,
    capture_recorded_play_identity,
)
from pitchlog.sync.stats_native_flush import _assert_scope, _bounded_rows


class PlayExportWriterUnavailable(RuntimeError):
    """受理後のCSV保存原本欠測を入力拒否へ誤分類しない。"""


def persist_accepted_play_export(scope, receipt, source, saved, revision: int) -> None:
    """一回消費済みnative source/保存版から88列を同TX内に保存する。"""
    _assert_scope(scope, receipt, source)
    if (
        type(saved) is not tuple
        or len(saved) != 1
        or type(saved[0]) is not tuple
        or len(saved[0]) != 4
        or type(saved[0][0]) is not UUID
        or saved[0][1] != source.source_event_id
    ):
        raise ValueError("毎球CSVの成績保存版が不正")
    try:
        identity = capture_recorded_play_identity(scope, receipt, source)
        direct = project_recorded_direct(identity)
        call = build_save_snapshot_call(
            source, saved[0][0], saved[0][3], revision, direct
        )
        _assert_scope(scope, receipt, source)
        require_private_save_call(call, FUNCTION_OPERATION_REGISTRY)
        rows = _bounded_rows(scope.session.execute(call.statement, call.parameters))
        _assert_scope(scope, receipt, source)
        decode_saved_play(rows, identity.play["id"])
    except (
        PlayExportIdentityUnavailable,
        RecordedExportProjectionUnavailable,
        FunctionOperationError,
    ) as error:
        raise PlayExportWriterUnavailable from error
