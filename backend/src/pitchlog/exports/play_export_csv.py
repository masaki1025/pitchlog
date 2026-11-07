"""保存値から毎球CSV 88列と全10サイドカーを組み立てる。

88列本体は、記録時に確定したprojection（``plays_csv_json``）だけを写す。
このmoduleはT1の再計算・座標変換・全件集計をせず、未供給をNULL/0で補わない。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, cast
from uuid import UUID

from pitchlog.db.sync_protocol.event_kinds import EVENT_KIND_LITERALS
from pitchlog.exports.archive import ExportSnapshot
from pitchlog.exports.csv import CsvCell
from pitchlog.exports.play_rows import (
    CSV_HEADERS,
    PlayExportSupplyError,
    SavedCsvRow,
)
from pitchlog.repositories.play_export import PlayExportBundle
from pitchlog.repositories.play_export_spool import DiskRows

_JST = timezone(timedelta(hours=9), "JST")
_REDACTED_KEY_NAMES = frozenset(
    {
        "token",
        "credential",
        "nonce",
        "proof",
        "d4",
        "wired4",
        "password",
        "secret",
        "recordingrightproof",
    }
)
_SECRET_FRAGMENTS = ("token", "credential", "nonce", "proof", "password", "secret")
_REDACTION = {"redaction": "pitchlog-csv-redacted-v1"}
_BUSINESS_FORMAT = "pitchlog-event-business-redacted-v1"
_SNAPSHOT_COLUMNS = tuple(CSV_HEADERS["plays.csv"])


def _json_default(value: object) -> str:
    """保存済みUUID/日付/日時/有限numericを決定的な文字列へ写す。"""
    if type(value) is UUID:
        return str(value)
    if type(value) is datetime:
        return value.isoformat()
    if type(value) is date:
        return value.isoformat()
    if type(value) is Decimal and value.is_finite():
        return str(value)
    raise TypeError("JSONへ写せない保存値です")


def _safe_json(value: object, *, depth: int = 0) -> object:
    """全JSON出力で資格/D4を可視redactionし、未知秘密様keyを拒否する。"""
    if depth > 40:
        raise PlayExportSupplyError("監査JSONの深さが上限を超えました")
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise PlayExportSupplyError("監査JSONのkeyが不正です")
            compact = re.sub(r"[^a-z0-9]", "", key.casefold())
            if compact in _REDACTED_KEY_NAMES:
                result[key] = _REDACTION
            elif any(
                fragment in compact for fragment in _SECRET_FRAGMENTS
            ) or compact.endswith("d4"):
                raise PlayExportSupplyError("未知の資格様keyを出力できません")
            else:
                result[key] = _safe_json(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_json(item, depth=depth + 1) for item in value]
    return value


def _canonical_json(value: object) -> str:
    """保存済みJSONをkey順だけ正準化し、値を補完しない。"""
    return json.dumps(
        _safe_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def _business_event_json(event: Mapping[str, Any]) -> str:
    """閉じたV5の業務payloadだけを版付きredaction形式へ写す。"""
    kind = event.get("event_kind")
    payload = event.get("payload")
    if (
        type(kind) is not str
        or kind not in EVENT_KIND_LITERALS
        or type(payload) is not dict
    ):
        raise PlayExportSupplyError("監査eventの閉じた種別/業務原本が不正です")
    return _canonical_json(
        {
            "redactionFormatVersion": _BUSINESS_FORMAT,
            "eventKind": kind,
            "payload": payload,
        }
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


def _indexed_rows(rows, field: str):
    """ディスク集合は索引へ照合し、全量dictへ戻さない。"""
    if isinstance(rows, DiskRows):
        return rows.index_by(field)
    return {row[field]: row for row in rows}


def _event_by_id(bundle: PlayExportBundle) -> Mapping[UUID, dict[str, Any]]:
    """source_event_idを同snapshotのイベント索引へ写す。"""
    return _indexed_rows(bundle.events, "id")


def _play_by_id(bundle: PlayExportBundle) -> Mapping[UUID, dict[str, Any]]:
    """play_row_idを同snapshotのプレイ索引へ写す。"""
    return _indexed_rows(bundle.plays, "id")


def _source_digest(bundle: PlayExportBundle) -> str:
    """gameの確定source/slot/play版集合をmanifest用digestへ写す。"""
    # 監査イベント/出場/参照/保存projectionを含む同一RRの全供給版を束縛する。
    payload: dict[str, Any] = {
        "game": bundle.game,
        "plays": bundle.plays,
        "audit_plays": (
            bundle.audit_plays if bundle.audit_plays is not None else bundle.plays
        ),
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
    if bundle.source_version is not None:
        if bundle.source_identities is None:
            raise PlayExportSupplyError("同版source原本が不足しています")
        version = bundle.source_version
        payload["current_source_version"] = {
            "fact_version_id": version.fact_version_id,
            "revision": version.revision,
            "source_set_sha256": version.source_set_sha256,
            "source_count": version.source_count,
            "completion_state": version.completion_state,
        }
        payload["current_source_identities"] = bundle.source_identities
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )

    def write(value):
        for chunk in encoder.iterencode(value):
            digest.update(chunk.encode("utf-8"))

    digest.update(b"{")
    for index, key in enumerate(sorted(payload)):
        if index:
            digest.update(b",")
        write(key)
        digest.update(b":")
        if key in ("game", "current_source_version"):
            write(payload[key])
        else:
            digest.update(b"[")
            for row_index, row in enumerate(payload[key]):
                if row_index:
                    digest.update(b",")
                write(row)
            digest.update(b"]")
    digest.update(b"}")
    return digest.hexdigest()


def _missing_snapshot(bundle: PlayExportBundle) -> tuple[str, ...]:
    """有効行と監査原本を分け、全88列の記録元/版を閉検証する。"""
    unavailable = tuple(str(index) for index in range(88))
    # P3のS原本だけで88列/sidecar供給を推測せず、producer接合までは拒否する。
    if any(event.get("event_kind") == "play_change" for event in bundle.events):
        return unavailable
    if (bundle.source_version is None) != (bundle.source_identities is None):
        return unavailable
    if bundle.source_version is not None:
        source_rows = bundle.source_identities
        if source_rows is None:
            return unavailable
        identities = _indexed_rows(source_rows, "play_row_id")
        if (
            bundle.source_version.source_count != len(bundle.plays)
            or len(identities) != len(bundle.plays)
            or len(source_rows) != len(bundle.plays)
        ):
            return unavailable
        for play in bundle.plays:
            identity = identities.get(play.get("id"))
            if identity is None or (
                identity.get("source_event_id") != play.get("source_event_id")
                or identity.get("play_row_version") != play.get("version")
            ):
                return unavailable
    snapshots = _indexed_rows(bundle.snapshots, "play_row_id")
    events = _event_by_id(bundle)
    plays = _play_by_id(bundle)
    audit_rows = bundle.audit_plays if bundle.audit_plays is not None else bundle.plays
    audit_plays = _indexed_rows(audit_rows, "id")
    if (
        len(snapshots) != len(bundle.snapshots)
        or len(events) != len(bundle.events)
        or len(plays) != len(bundle.plays)
        or len(audit_plays) != len(audit_rows)
        or (bundle.audit_plays is not None and len(audit_plays) != len(snapshots))
    ):
        return unavailable
    current_count = 0
    for snapshot in bundle.snapshots:
        physical = audit_plays.get(snapshot.get("play_row_id"))
        if physical is None:
            return unavailable
        event = events.get(physical.get("source_event_id"))
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
            or (
                bundle.audit_plays is not None
                and (
                    physical.get("tenant_id") != bundle.game["tenant_id"]
                    or physical.get("game_id") != bundle.game["id"]
                    or event.get("tenant_id") != bundle.game["tenant_id"]
                    or event.get("game_id") != bundle.game["id"]
                    or event.get("is_tombstone") is not False
                )
            )
            or snapshot.get("play_row_id") != physical.get("id")
            or snapshot.get("source_event_id") != physical.get("source_event_id")
            or snapshot.get("source_event_id") != event["id"]
            or event.get("ledger_kind") != "accepted"
        ):
            return unavailable
        for key, expected in (
            ("recording_generation", event.get("generation")),
            ("event_sequence", event.get("d2")),
            ("play_version", physical.get("version")),
        ):
            actual = snapshot.get(key)
            if (
                type(actual) is not int
                or type(expected) is not int
                or actual != expected
            ):
                return unavailable
        current = plays.get(physical["id"])
        if current is None:
            if bundle.audit_plays is None or (
                physical.get("hidden_at") is None
                and event.get("retired_at") is None
                and event.get("replaced_at") is None
            ):
                return unavailable
        elif current != physical:
            return unavailable
        else:
            current_count += 1
    if current_count != len(bundle.plays):
        return unavailable
    for play in bundle.plays:
        if audit_plays.get(play["id"]) != play or snapshots.get(play["id"]) is None:
            return unavailable
    return ()


def snapshot_id_for(bundle: PlayExportBundle) -> str:
    """同一snapshotのdigestを返す。"""
    return _source_digest(bundle)


def export_snapshot(bundle: PlayExportBundle) -> ExportSnapshot:
    """manifestへ記録する同一版とJST出力時刻を返す。"""
    now = datetime.now(_JST).strftime("%Y-%m-%d %H:%M:%S")
    digest = _source_digest(bundle)
    return ExportSnapshot(
        game_id=bundle.game["id"],
        snapshot_id=digest,
        source_versions=digest,
        exported_at=now,
    )


def _plays_rows(bundle: PlayExportBundle, snapshot_id: str) -> Iterator[SavedCsvRow]:
    snapshots = _indexed_rows(bundle.snapshots, "play_row_id")
    for play in bundle.plays:
        values = snapshots[play["id"]]["plays_csv_json"]
        if set(values) != set(_SNAPSHOT_COLUMNS):
            raise PlayExportSupplyError("88列projectionの列集合が不一致です")
        yield _row(bundle.game["id"], snapshot_id, values)
    return


def _play_links_rows(
    bundle: PlayExportBundle, snapshot_id: str
) -> Iterator[SavedCsvRow]:
    events = _event_by_id(bundle)
    for index, play in enumerate(bundle.plays, start=1):
        event = events.get(play["source_event_id"])
        yield _row(
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
    return


def _events_rows(bundle: PlayExportBundle, snapshot_id: str) -> Iterator[SavedCsvRow]:
    for event in bundle.events:
        yield _row(
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
                "business_payload_json": _business_event_json(event),
                "state_diff_json": _canonical_json(event["state_diff"]),
            },
        )
    return


def _runner_rows(bundle: PlayExportBundle, snapshot_id: str) -> Iterator[SavedCsvRow]:
    plays = _play_by_id(bundle)
    events = _event_by_id(bundle)
    for runner in bundle.runners:
        play = plays.get(runner["play_id"])
        event = events.get(play["source_event_id"]) if play else None
        yield _row(
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
    return


def _lineup_rows(bundle: PlayExportBundle, snapshot_id: str) -> Iterator[SavedCsvRow]:
    yield from (
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
    )


def _participation_rows(
    bundle: PlayExportBundle, snapshot_id: str
) -> Iterator[SavedCsvRow]:
    yield from (
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
    )


def _game_rows(bundle: PlayExportBundle, snapshot_id: str) -> Iterator[SavedCsvRow]:
    yield from [
        _row(
            bundle.game["id"],
            snapshot_id,
            {"game_id": bundle.game["id"], "source_json": _canonical_json(bundle.game)},
        )
    ]


def _reference_rows(
    bundle: PlayExportBundle, snapshot_id: str
) -> Iterator[SavedCsvRow]:
    for kind, source in (
        ("player", bundle.players),
        ("team", bundle.teams),
        ("tenant_vocabulary", bundle.tenant_vocabularies),
        ("admin_vocabulary", bundle.admin_vocabularies),
    ):
        for row in source:
            yield _row(
                bundle.game["id"],
                snapshot_id,
                {
                    "game_id": bundle.game["id"],
                    "reference_kind": kind,
                    "reference_id": str(row["id"]) if "id" in row else str(row["key"]),
                    "source_json": _canonical_json(row),
                },
            )
    return


def _projection_rows(
    bundle: PlayExportBundle, snapshot_id: str
) -> Iterator[SavedCsvRow]:
    # 記録時の旧projectionも監査原本として同一RR版のまま出す。
    for snapshot in bundle.snapshots:
        yield _row(
            bundle.game["id"],
            snapshot_id,
            {
                "game_id": bundle.game["id"],
                "recording_generation": snapshot.get("recording_generation"),
                "event_sequence": snapshot.get("event_sequence"),
                "source_event_id": snapshot["source_event_id"],
                "projection_kind": "plays_csv_v1",
                "source_version": 1,
                "source_json": _canonical_json(snapshot["plays_csv_json"]),
            },
        )
    return


def _inning_score_rows(
    bundle: PlayExportBundle, snapshot_id: str
) -> Iterator[SavedCsvRow]:
    """最後の有効playと同版の生成済み全回値を一行ずつ写す。"""
    if not bundle.plays:
        return
    events = _event_by_id(bundle)
    last_play = bundle.plays[-1]
    last_event = events.get(last_play["source_event_id"])
    if (
        last_event is None
        or type(last_event.get("generation")) is not int
        or type(last_event.get("d2")) is not int
    ):
        raise PlayExportSupplyError("全回値のsource版が不正です")
    play_sources = (events.get(play["source_event_id"]) for play in bundle.plays)
    if any(
        event is None
        or type(event.get("generation")) is not int
        or type(event.get("d2")) is not int
        or (event["generation"], event["d2"])
        > (last_event["generation"], last_event["d2"])
        for event in play_sources
    ):
        raise PlayExportSupplyError("全回値のcurrent play順が未供給です")
    snapshots = _indexed_rows(bundle.snapshots, "play_row_id")
    snapshot = snapshots.get(last_play["id"])
    if snapshot is None:
        raise PlayExportSupplyError("全回値の保存原本がありません")
    innings = snapshot.get("full_innings_json")
    if type(innings) is not list or not innings or len(innings) % 2:
        raise PlayExportSupplyError("全回値の保存形が不正です")
    for position, inning in enumerate(innings):
        expected_half = "top" if position % 2 == 0 else "bottom"
        expected_inning = position // 2 + 1
        if type(inning) is not dict or set(inning) != {
            "inning",
            "half",
            "state",
            "runs",
        }:
            raise PlayExportSupplyError("全回値の保存形が不正です")
        inning = cast(dict[str, object], inning)
        state, runs = inning["state"], inning["runs"]
        if (
            type(inning["inning"]) is not int
            or inning["inning"] != expected_inning
            or inning["half"] != expected_half
            or state not in ("unplayed", "in-progress", "completed")
            or (
                (state == "unplayed" and runs is not None)
                or (state != "unplayed" and (type(runs) is not int or runs < 0))
            )
        ):
            raise PlayExportSupplyError("全回値の保存形が不正です")
        yield _row(
            bundle.game["id"],
            snapshot_id,
            {
                "game_id": bundle.game["id"],
                "recording_generation": snapshot["recording_generation"],
                "event_sequence": snapshot["event_sequence"],
                "source_event_id": last_play["source_event_id"],
                "play_row_id": last_play["id"],
                "inning": expected_inning,
                "half": expected_half,
                "state": state,
                "runs": runs,
            },
        )


def build_play_export_tables(
    bundle: PlayExportBundle,
) -> tuple[ExportSnapshot, dict[str, Iterable[SavedCsvRow]]]:
    """88列と全10サイドカーを同一snapshotの行集合へ写す。

    Args:
        bundle: ``read_play_export`` の同一RR snapshot。

    Returns:
        manifest用snapshotと、11ファイルの供給行。

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
        "inning_scores.csv": _inning_score_rows(bundle, snapshot_id),
    }
    if set(tables) != set(CSV_HEADERS):
        raise PlayExportSupplyError("出力ファイル集合が契約と不一致です")
    return snapshot, tables


def missing_supply_columns(bundle: PlayExportBundle) -> tuple[int, ...]:
    """88列projectionの不足範囲を列indexで返す。"""
    return tuple(int(value) for value in _missing_snapshot(bundle))
