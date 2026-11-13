"""真正play writerの同一TXでCSV表示原本を一度だけ保存する。"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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
from pitchlog.sync.substitution_payload import (
    SubstitutionPayloadError,
    read_substitution_payload,
)


class PlayExportWriterUnavailable(RuntimeError):
    """受理後のCSV保存原本欠測を入力拒否へ誤分類しない。"""


_SUBSTITUTE_SQL = text(
    "SELECT substitution_event_id,substitution_d2,substitution_payload "
    "FROM stats_api.read_writer_play_export_substitute("
    ":attempt_id,:phase_id,:source_event_id,:player_id,:binding_nonce)"
)


def _recorded_substitutes(
    scope, receipt, source, identity
) -> dict[UUID, dict[str, Any]]:
    """同writerの受理交代印と記録時playerを一点ずつ照合する。"""
    play = identity.play
    candidates = {
        value
        for value in (play["batter_id"], play["pitcher_id"])
        if type(value) is UUID
    }
    candidates.update(row["runner_id"] for row in identity.runners)
    if len(candidates) > 5 or any(type(value) is not UUID for value in candidates):
        raise RecordedExportProjectionUnavailable
    recorded: dict[UUID, dict[str, Any]] = {}
    first_candidate = True
    for player_id in candidates:
        # 先頭は直前にcapture_recorded_play_identityが_assert_scopeを完了している。
        if not first_candidate:
            _assert_scope(scope, receipt, source)
        first_candidate = False
        rows = tuple(
            scope.session.execute(
                _SUBSTITUTE_SQL,
                {
                    "attempt_id": source.attempt_id,
                    "phase_id": source.phase_id,
                    "source_event_id": source.source_event_id,
                    "player_id": player_id,
                    "binding_nonce": source.binding_nonce,
                },
            )
        )
        if len(rows) > 1:
            raise RecordedExportProjectionUnavailable
        if not rows:
            continue
        event_id, d2, raw = rows[0]
        if type(event_id) is not UUID or type(d2) is not int or type(raw) is not dict:
            raise RecordedExportProjectionUnavailable
        event = read_substitution_payload(
            json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
        ).to_wire()
        snapshots = [
            item
            for item in event["incomingSnapshots"]
            if item["playerId"] == str(player_id)
        ]
        if len(snapshots) != 1 or event["eventId"] != str(event_id):
            raise RecordedExportProjectionUnavailable
        player_rows = [
            row for row in identity.players if row.get("id") == player_id
        ]
        side = event["operation"]["side"]
        if (
            len(player_rows) != 1
            or side not in ("away", "home")
            or player_rows[0].get("team_record_id")
            != identity.game[f"{side}_team_record_id"]
            or player_rows[0].get("roster_status_key") != "active"
            or player_rows[0].get("uniform_number")
            != snapshots[0]["uniformNumber"]
            or type(player_rows[0].get("name")) is not str
        ):
            raise RecordedExportProjectionUnavailable
        recorded[player_id] = {
            "event_id": event_id,
            "d2": d2,
            "name": player_rows[0]["name"],
            "uniform_number_snapshot": snapshots[0]["uniformNumber"],
            "kind": event["operation"]["kind"],
            "side": side,
            "operation": event["operation"],
        }
    _assert_scope(scope, receipt, source)
    return recorded


def persist_accepted_play_export(scope, receipt, source, saved, revision: int) -> None:
    """一回消費済みnative source/保存版から88列を同TX内に保存する。"""
    from pitchlog.sync.stage_timing import begin_stage, end_stage

    # 呼出元の_flush_native_statsが保存SQL直後に_assert_scopeを完了している。
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
        identity_begin = begin_stage("play_export_identity")
        identity = capture_recorded_play_identity(scope, receipt, source)
        end_stage(identity_begin)
        substitutes_begin = begin_stage("play_export_substitutes")
        substitutes = _recorded_substitutes(scope, receipt, source, identity)
        end_stage(substitutes_begin)
        project_begin = begin_stage("play_export_project")
        direct = project_recorded_direct(identity, substitutes)
        call = build_save_snapshot_call(
            source, saved[0][0], saved[0][3], revision, direct
        )
        end_stage(project_begin)
        _assert_scope(scope, receipt, source)
        require_private_save_call(call, FUNCTION_OPERATION_REGISTRY)
        save_begin = begin_stage("play_export_save")
        rows = _bounded_rows(scope.session.execute(call.statement, call.parameters))
        _assert_scope(scope, receipt, source)
        decode_saved_play(rows, identity.play["id"])
        end_stage(save_begin)
    except (
        PlayExportIdentityUnavailable,
        RecordedExportProjectionUnavailable,
        FunctionOperationError,
        SubstitutionPayloadError,
        SQLAlchemyError,
    ) as error:
        raise PlayExportWriterUnavailable from error
