"""通常snapshotと真正P3完成原本の全監査coverageを同じ有限spoolで閉じる。"""

from __future__ import annotations

from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.play_export import _freeze_rows, _new_rows
from pitchlog.repositories.play_export_p3_read import validate_snapshot_row
from pitchlog.repositories.play_export_source_codec import SourceIdentity
from pitchlog.repositories.play_export_spool import DiskRows


def _need(ok):
    if not ok:
        raise PlayExportSupplyError("P3 CSVの現値/監査原本coverageが未供給です")


def _index(rows, key):
    return (
        rows.index_by(key)
        if isinstance(rows, DiskRows)
        else {row[key]: row for row in rows}
    )


def _snapshot_value(value):
    _need(type(value) is dict and set(value) == set(CSV_HEADERS["plays.csv"]))
    _need(all(type(item) is str or item is None for item in value.values()))


def resolve_p3_snapshots(bundle):
    """全歴代原本を検証し、唯一S順の現在88列原本だけを返す。

    任意JSONをDB資格へ昇格しない。呼出側repositoryは同RR専用readerを
    完全消費し、ここはその保存値の閉照合だけを担当する。全件tuple/dictへ
    戻さず、実exportでは私有ディスク索引を使う。
    """
    _need(
        bundle.p3_snapshots is not None
        and bundle.source_version is not None
        and bundle.source_identities is not None
        and bundle.audit_plays is not None
    )
    tenant, game = bundle.game["tenant_id"], bundle.game["id"]
    audit = _index(bundle.audit_plays, "id")
    events = _index(bundle.events, "id")
    normal = _index(bundle.snapshots, "play_row_id")
    current = _index(bundle.plays, "id")
    _need(
        len(audit) == len(bundle.audit_plays)
        and len(events) == len(bundle.events)
        and len(normal) == len(bundle.snapshots)
        and len(current) == len(bundle.plays)
    )
    covered = _new_rows()
    current_overlays = _new_rows()
    for snapshot in bundle.snapshots:
        play = audit.get(snapshot.get("play_row_id"))
        _need(play is not None)
        event = events.get(play["source_event_id"])
        _need(
            event is not None
            and event.get("ledger_kind") == "accepted"
            and event.get("is_tombstone") is False
        )
        _need(
            snapshot.get("tenant_id") == tenant
            and snapshot.get("game_id") == game
            and play.get("tenant_id") == tenant
            and play.get("game_id") == game
            and event.get("tenant_id") == tenant
            and event.get("game_id") == game
            and snapshot.get("source_event_id") == play["source_event_id"]
        )
        for key, wanted in (
            ("play_version", play["version"]),
            ("recording_generation", event["generation"]),
            ("event_sequence", event["d2"]),
        ):
            _need(
                type(snapshot.get(key)) is int
                and type(wanted) is int
                and snapshot[key] == wanted
            )
        _snapshot_value(snapshot.get("plays_csv_json"))
        covered.append({"id": play["id"]})
    group = None
    previous_d1 = 0
    watermark = None
    group_header = None
    current_capsule = None
    current_generation = None
    for row in bundle.p3_snapshots:
        # 値境界だけを再検査し、架空のheader/read資格を作らない。
        validate_snapshot_row(row, game)
        key = (row["internal_generation"], row["capsule_id"])
        if key != group:
            _need(group is None or (key > group and previous_d1 == watermark))
            group, previous_d1, watermark = key, 0, row["capsule_watermark"]
            group_header = (
                row["capsule_target_d1"],
                row["current_head"],
                row["capsule_source_set_digest"],
                row["capsule_stats_version_id"],
            )
            if current_generation != key[0]:
                current_generation, current_capsule = key[0], None
            if row["current_head"]:
                _need(current_capsule is None)
                current_capsule = key
        _need(row["d1"] == previous_d1 + 1 and row["capsule_watermark"] == watermark)
        _need(
            group_header
            == (
                row["capsule_target_d1"],
                row["current_head"],
                row["capsule_source_set_digest"],
                row["capsule_stats_version_id"],
            )
        )
        previous_d1 = row["d1"]
        _need(row["tenant_id"] == tenant and row["game_id"] == game)
        physical = audit.get(row["effective_play_row_id"])
        _need(
            physical is not None
            and physical.get("tenant_id") == tenant
            and physical.get("game_id") == game
            and physical.get("source_event_id") == row["effective_event_id"]
            and type(physical.get("version")) is int
            and physical["version"] == row["play_row_version"]
        )
        event = events.get(row["effective_event_id"])
        _need(
            event is not None
            and event.get("tenant_id") == tenant
            and event.get("game_id") == game
            and event.get("ledger_kind") == "accepted"
            and event.get("is_tombstone") is False
            and type(event.get("generation")) is int
            and event["generation"] == row["internal_generation"]
        )
        covered.append({"id": physical["id"]})
        if row["current_head"]:
            current_overlays.append(
                {**row, "play_row_id": row["effective_play_row_id"]}
            )
    _need(group is not None and previous_d1 == watermark)
    covered = _freeze_rows(covered)
    covered_index = _index(covered, "id")
    _need(len(covered_index) == len(audit))
    for play in bundle.audit_plays:
        _need(covered_index.get(play["id"]) is not None)
        if current.get(play["id"]) is None:
            event = events.get(play["source_event_id"])
            _need(
                play.get("hidden_at") is not None
                or event.get("retired_at") is not None
                or event.get("replaced_at") is not None
            )
        else:
            _need(current.get(play["id"]) == play)
    current_overlays = _freeze_rows(current_overlays)
    overlay_index = _index(current_overlays, "play_row_id")
    _need(len(overlay_index) == len(current_overlays))
    identities = _index(bundle.source_identities, "play_row_id")
    _need(
        len(identities) == len(bundle.plays)
        and len(bundle.source_identities) == len(bundle.plays)
        and bundle.source_version.source_count == len(bundle.plays)
    )
    resolved = _new_rows()
    for play in bundle.plays:
        _need(audit.get(play["id"]) == play)
        raw = identities.get(play["id"])
        _need(raw is not None)
        source = SourceIdentity(**raw)
        _need(
            source.source_event_id == play["source_event_id"]
            and source.play_row_version == play["version"]
        )
        overlay = overlay_index.get(play["id"])
        if overlay is None:
            snapshot = normal.get(play["id"])
            _need(snapshot is not None)
            resolved.append(snapshot)
        else:
            _need(
                (
                    overlay["internal_generation"],
                    overlay["d1"],
                    overlay["effective_event_id"],
                    overlay["effective_play_row_id"],
                    overlay["play_row_version"],
                )
                == (
                    source.recording_generation,
                    source.d1,
                    source.source_event_id,
                    source.play_row_id,
                    source.play_row_version,
                )
            )
            resolved.append(
                {
                    "tenant_id": tenant,
                    "game_id": game,
                    "play_row_id": source.play_row_id,
                    "source_event_id": source.source_event_id,
                    "play_version": source.play_row_version,
                    "recording_generation": source.recording_generation,
                    "event_sequence": source.d2,
                    "plays_csv_json": overlay["plays_csv_json"],
                    "full_innings_json": overlay["full_innings_json"],
                }
            )
    return _freeze_rows(resolved)
