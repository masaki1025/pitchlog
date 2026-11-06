"""保存値から毎球CSV 88列と全9サイドカーを組み立てる。

88列本体は、記録時に確定したprojection（``plays_csv_json``）だけを写す。
このmoduleはT1の再計算・座標変換・全件集計をせず、未供給をNULL/0で補わない。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID

from pitchlog.exports.archive import ExportSnapshot
from pitchlog.exports.csv import CsvCell
from pitchlog.exports.play_rows import (
    CSV_HEADERS,
    PlayExportSupplyError,
    SavedCsvRow,
)
from pitchlog.repositories.play_export import PlayExportBundle

_JST = timezone(timedelta(hours=9), "JST")
_SECRET_KEYS = frozenset(
    {"token", "credential", "nonce", "proof", "d4", "password", "secret"}
)
_SNAPSHOT_COLUMNS = tuple(CSV_HEADERS["plays.csv"])


def _json_default(value: object) -> str:
    """保存済みUUID/日時だけを決定的な文字列へ写す。"""
    if type(value) is UUID:
        return str(value)
    if type(value) is datetime:
        return value.isoformat()
    raise TypeError("JSONへ写せない保存値です")


def _canonical_json(value: object) -> str:
    """保存済みJSONをkey順だけ正準化し、値を補完しない。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def _jst(value: datetime | None) -> str | None:
    """Aware datetimeだけをJST完成文字列へ写す。"""
    if value is None:
        return None
    if type(value) is not datetime or value.utcoffset() is None:
        raise PlayExportSupplyError("日時はtimezone付き保存値が必要です")
    return value.astimezone(_JST).strftime("%Y-%m-%d %H:%M:%S")


def _cell(value: object) -> CsvCell:
    """保存値をCSVセルへ写す。bool/floatの暗黙文字列化をしない。"""
    if value is None or type(value) is int or type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is UUID:
        return str(value)
    if type(value) is datetime:
        return _jst(value)
    raise PlayExportSupplyError("完成セルの型が不正です")


def _row(game_id: UUID, snapshot_id: str, values: Mapping[str, object]) -> SavedCsvRow:
    """閉じた列写像を検証可能な行へ写す。"""
    return SavedCsvRow(
        game_id=game_id,
        snapshot_id=snapshot_id,
        values={key: _cell(value) for key, value in values.items()},
    )


def _event_by_id(bundle: PlayExportBundle) -> dict[UUID, dict[str, Any]]:
    """source_event_idから同snapshotのイベントを引く。"""
    return {row["id"]: row for row in bundle.events}


def _play_by_id(bundle: PlayExportBundle) -> dict[UUID, dict[str, Any]]:
    """play_row_idから同snapshotのプレイを引く。"""
    return {row["id"]: row for row in bundle.plays}


def _source_digest(bundle: PlayExportBundle) -> str:
    """gameの確定source/slot/play版集合をmanifest用digestへ写す。"""
    # 監査イベント/出場/参照/保存projectionを含む同一RRの全供給版を束縛する。
    payload = {
        "game": bundle.game,
        "plays": bundle.plays,
        "runners": bundle.runners,
        "events": bundle.events,
        "lineups": bundle.lineups,
        "participations": bundle.participations,
        "players": bundle.players,
        "teams": bundle.teams,
        "tenant_vocabularies": bundle.tenant_vocabularies,
        "admin_vocabularies": bundle.admin_vocabularies,
        "snapshots": bundle.snapshots,
        "runner_snapshots": bundle.runner_snapshots,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _missing_snapshot(bundle: PlayExportBundle) -> tuple[str, ...]:
    """全88列と、その記録元/版の一致を閉検証する。"""
    unavailable = tuple(str(index) for index in range(88))
    snapshots = {row["play_row_id"]: row for row in bundle.snapshots}
    events = _event_by_id(bundle)
    if len(snapshots) != len(bundle.snapshots) or len(events) != len(bundle.events):
        return unavailable
    if set(snapshots) != {play["id"] for play in bundle.plays}:
        return unavailable
    for play in bundle.plays:
        snapshot = snapshots[play["id"]]
        event = events.get(play["source_event_id"])
        value = snapshot.get("plays_csv_json")
        if (
            event is None
            or type(value) is not dict
            or set(value) != set(_SNAPSHOT_COLUMNS)
        ):
            return unavailable
        if (
            snapshot.get("tenant_id") != bundle.game["tenant_id"]
            or snapshot.get("game_id") != bundle.game["id"]
            or snapshot.get("source_event_id") != event["id"]
            or event.get("ledger_kind") != "accepted"
        ):
            return unavailable
        for key, expected in (
            ("recording_generation", event["generation"]),
            ("event_sequence", event["d2"]),
            ("play_version", play["version"]),
        ):
            actual = snapshot.get(key)
            if (
                type(actual) is not int
                or type(expected) is not int
                or actual != expected
            ):
                return unavailable
    return ()


def snapshot_id_for(bundle: PlayExportBundle) -> str:
    """同一snapshotのdigestを返す。"""
    return _source_digest(bundle)


def export_snapshot(bundle: PlayExportBundle) -> ExportSnapshot:
    """manifestへ記録する同一版とJST出力時刻を返す。"""
    now = datetime.now(_JST).strftime("%Y-%m-%d %H:%M:%S")
    return ExportSnapshot(
        game_id=bundle.game["id"],
        snapshot_id=_source_digest(bundle),
        source_versions=_source_digest(bundle),
        exported_at=now,
    )


def _plays_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    snapshots = {row["play_row_id"]: row for row in bundle.snapshots}
    rows = []
    for play in bundle.plays:
        values = snapshots[play["id"]]["plays_csv_json"]
        if set(values) != set(_SNAPSHOT_COLUMNS):
            raise PlayExportSupplyError("88列projectionの列集合が不一致です")
        rows.append(_row(bundle.game["id"], snapshot_id, values))
    return rows


def _play_links_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    events = _event_by_id(bundle)
    rows = []
    for index, play in enumerate(bundle.plays, start=1):
        event = events.get(play["source_event_id"])
        rows.append(
            _row(
                bundle.game["id"],
                snapshot_id,
                {
                    "row_number": index,
                    "game_id": bundle.game["id"],
                    "recording_generation": event["generation"] if event else None,
                    "event_sequence": event["d2"] if event else None,
                    "source_event_id": play["source_event_id"],
                    "play_row_id": play["id"],
                    "play_number": play["play_number"],
                    "version": play["version"],
                },
            )
        )
    return rows


def _events_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    rows = []
    for event in bundle.events:
        rows.append(
            _row(
                bundle.game["id"],
                snapshot_id,
                {
                    "game_id": bundle.game["id"],
                    "recording_generation": event["generation"],
                    "event_sequence": event["d2"],
                    "source_event_id": event["id"],
                    "event_kind": event["event_kind"],
                    "d2": event["d2"],
                    "target_generation": event["target_generation"],
                    "target_event_sequence": event["target_d1"],
                    "expected_version": event["expected_version"],
                    "change_order": event["change_order"],
                    "is_tombstone": event["is_tombstone"],
                    "replaced_at": event["replaced_at"],
                    "retired_at": event["retired_at"],
                    "business_payload_json": _canonical_json(event["payload"]),
                    "state_diff_json": _canonical_json(event["state_diff"]),
                },
            )
        )
    return rows


def _runner_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    plays = _play_by_id(bundle)
    events = _event_by_id(bundle)
    rows = []
    for runner in bundle.runners:
        play = plays.get(runner["play_id"])
        event = events.get(play["source_event_id"]) if play else None
        rows.append(
            _row(
                bundle.game["id"],
                snapshot_id,
                {
                    "game_id": bundle.game["id"],
                    "recording_generation": event["generation"] if event else None,
                    "event_sequence": event["d2"] if event else None,
                    "source_event_id": play["source_event_id"] if play else None,
                    "play_row_id": runner["play_id"],
                    "runner_row_id": runner["id"],
                    "base": runner["base"],
                    "runner_id": runner["runner_id"],
                    "responsible_pitcher_id": runner["responsible_pitcher_id"],
                    "status": runner["status"],
                    "status_source": runner["status_source"],
                    "retired_at": runner["retired_at"],
                    "source_json": _canonical_json(runner),
                },
            )
        )
    return rows


def _lineup_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    return [
        _row(
            bundle.game["id"],
            snapshot_id,
            {
                "game_id": bundle.game["id"],
                "lineup_id": row["id"],
                "team_record_id": row["team_record_id"],
                "entries_json": _canonical_json(
                    row["entries_with_uniform_number_snapshot"]
                ),
            },
        )
        for row in bundle.lineups
    ]


def _participation_rows(
    bundle: PlayExportBundle, snapshot_id: str
) -> list[SavedCsvRow]:
    return [
        _row(
            bundle.game["id"],
            snapshot_id,
            {
                "game_id": bundle.game["id"],
                "participation_id": row["id"],
                "source_json": _canonical_json(row),
            },
        )
        for row in bundle.participations
    ]


def _game_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    return [
        _row(
            bundle.game["id"],
            snapshot_id,
            {"game_id": bundle.game["id"], "source_json": _canonical_json(bundle.game)},
        )
    ]


def _reference_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    rows = []
    for kind, source in (
        ("player", bundle.players),
        ("team", bundle.teams),
        ("tenant_vocabulary", bundle.tenant_vocabularies),
        ("admin_vocabulary", bundle.admin_vocabularies),
    ):
        for row in source:
            rows.append(
                _row(
                    bundle.game["id"],
                    snapshot_id,
                    {
                        "game_id": bundle.game["id"],
                        "reference_kind": kind,
                        "reference_id": str(row["id"])
                        if "id" in row
                        else str(row["key"]),
                        "source_json": _canonical_json(row),
                    },
                )
            )
    return rows


def _projection_rows(bundle: PlayExportBundle, snapshot_id: str) -> list[SavedCsvRow]:
    plays = _play_by_id(bundle)
    rows = []
    for snapshot in bundle.snapshots:
        play = plays.get(snapshot["play_row_id"])
        if play is None:
            continue
        rows.append(
            _row(
                bundle.game["id"],
                snapshot_id,
                {
                    "game_id": bundle.game["id"],
                    "recording_generation": snapshot.get("recording_generation"),
                    "event_sequence": snapshot.get("event_sequence"),
                    "source_event_id": play["source_event_id"],
                    "projection_kind": "plays_csv_v1",
                    "source_version": 1,
                    "source_json": _canonical_json(snapshot["plays_csv_json"]),
                },
            )
        )
    return rows


def build_play_export_tables(
    bundle: PlayExportBundle,
) -> tuple[ExportSnapshot, dict[str, list[SavedCsvRow]]]:
    """88列と全9サイドカーを同一snapshotの行集合へ写す。

    Args:
        bundle: ``read_play_export`` の同一RR snapshot。

    Returns:
        manifest用snapshotと、10ファイルの供給行。

    Raises:
        PlayExportSupplyError: 88列projectionが未供給/不正な場合。
    """
    missing = _missing_snapshot(bundle)
    if missing:
        raise PlayExportSupplyError("88列projectionが未供給です")
    snapshot = export_snapshot(bundle)
    snapshot_id = snapshot.snapshot_id
    tables = {
        "plays.csv": _plays_rows(bundle, snapshot_id),
        "play_links.csv": _play_links_rows(bundle, snapshot_id),
        "events.csv": _events_rows(bundle, snapshot_id),
        "runners.csv": _runner_rows(bundle, snapshot_id),
        "lineups.csv": _lineup_rows(bundle, snapshot_id),
        "participations.csv": _participation_rows(bundle, snapshot_id),
        "game.csv": _game_rows(bundle, snapshot_id),
        "references.csv": _reference_rows(bundle, snapshot_id),
        "projections.csv": _projection_rows(bundle, snapshot_id),
        "preserved_sources.csv": [],
    }
    if set(tables) != set(CSV_HEADERS):
        raise PlayExportSupplyError("出力ファイル集合が契約と不一致です")
    return snapshot, tables


def missing_supply_columns(bundle: PlayExportBundle) -> tuple[int, ...]:
    """88列projectionの不足範囲を列indexで返す。"""
    return tuple(int(value) for value in _missing_snapshot(bundle))
