"""取消後の有効CSVと残す監査原本の集合を分けて検証する。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from test_play_export_source_binding import GAME, TENANT, _bundle

from pitchlog.exports.play_export_csv import (
    build_play_export_tables,
    missing_supply_columns,
    snapshot_id_for,
)
from pitchlog.exports.play_rows import PlayExportSupplyError


def _recorded():
    """既完成fixtureへsource scopeと物理旧行を明示する。"""
    base = _bundle()
    play = {
        **base.plays[0],
        "tenant_id": TENANT,
        "game_id": GAME,
        "hidden_at": None,
    }
    event = {
        **base.events[0],
        "tenant_id": TENANT,
        "game_id": GAME,
        "is_tombstone": False,
        "replaced_at": None,
        "retired_at": None,
    }
    return replace(base, plays=(play,), events=(event,), audit_plays=(play,))


def _one_remaining():
    """一球目だけ論理取消し、二球目の実保存snapshotを残す。"""
    base = _recorded()
    old = {**base.plays[0], "hidden_at": datetime(2026, 11, 7, tzinfo=timezone.utc)}
    play = {
        **base.plays[0],
        "id": UUID(int=100),
        "source_event_id": UUID(int=101),
        "play_number": 2,
    }
    event = {**base.events[0], "id": UUID(int=101), "d2": 2001}
    saved = deepcopy(base.snapshots[0])
    saved.update(
        play_row_id=play["id"],
        source_event_id=event["id"],
        event_sequence=event["d2"],
    )
    return replace(
        base,
        plays=(play,),
        events=(*base.events, event),
        snapshots=(*base.snapshots, saved),
        audit_plays=(old, play),
    )


def test_all_undone_exports_header_only_but_keeps_audit_projection() -> None:
    """全取消は88列の偽空値を作らず、旧原本を版に含める。"""
    base = _recorded()
    old = {**base.plays[0], "hidden_at": datetime(2026, 11, 7, tzinfo=timezone.utc)}
    undone = replace(base, plays=(), audit_plays=(old,))
    assert missing_supply_columns(undone) == ()
    assert snapshot_id_for(undone) != snapshot_id_for(replace(undone, snapshots=()))
    _version, tables = build_play_export_tables(undone)
    assert list(tables["plays.csv"]) == []
    assert len(undone.events) == 1
    assert len(list(tables["projections.csv"])) == 1
    assert list(tables["inning_scores.csv"]) == []


def test_one_current_row_uses_exact_saved_source_and_preserves_old() -> None:
    """取消前の旧行を本体へ二重算入せず、監査projectionを残す。"""
    bundle = _one_remaining()
    assert missing_supply_columns(bundle) == ()
    _version, tables = build_play_export_tables(bundle)
    plays = list(tables["plays.csv"])
    assert len(plays) == 1
    assert len(list(tables["play_links.csv"])) == 1
    assert len(bundle.events) == 2
    assert len(list(tables["projections.csv"])) == 2
    assert list(tables["inning_scores.csv"])[0].values["source_event_id"] == str(
        bundle.plays[0]["source_event_id"]
    )


def test_p3_history_without_current_capsule_selector_is_unavailable() -> None:
    """旧行が非hiddenのP3をraw PlayRow二重計上へ進めない。"""
    bundle = _one_remaining()
    change = {**bundle.events[1], "id": UUID(int=444), "event_kind": "play_change"}
    bundle = replace(bundle, events=(*bundle.events, change))
    assert missing_supply_columns(bundle) == tuple(range(88))
    with pytest.raises(PlayExportSupplyError):
        build_play_export_tables(bundle)


@pytest.mark.parametrize(
    "mutation",
    (
        "other-tenant-snapshot",
        "other-game-snapshot",
        "unknown-source",
        "wrong-generation",
        "wrong-version",
        "other-tenant-physical",
        "other-game-event",
        "unaccepted-event",
        "not-retired",
        "missing-current-snapshot",
        "missing-historical-snapshot",
        "unbound-audit-physical",
        "duplicate-snapshot",
    ),
)
def test_audit_or_current_source_mismatch_is_unavailable(mutation: str) -> None:
    """古いsnapshotも他scope/未知原本/偽有効版として混入させない。"""
    bundle = _one_remaining()
    old = deepcopy(bundle.snapshots[0])
    if mutation == "other-tenant-snapshot":
        old["tenant_id"] = UUID(int=20)
    elif mutation == "other-game-snapshot":
        old["game_id"] = UUID(int=20)
    elif mutation == "unknown-source":
        old["source_event_id"] = UUID(int=20)
    elif mutation == "wrong-generation":
        old["recording_generation"] += 1
    elif mutation == "wrong-version":
        old["play_version"] += 1
    elif mutation == "other-tenant-physical":
        physical = {**bundle.audit_plays[0], "tenant_id": UUID(int=20)}
        bundle = replace(bundle, audit_plays=(physical, bundle.audit_plays[1]))
    elif mutation == "other-game-event":
        event = {**bundle.events[0], "game_id": UUID(int=20)}
        bundle = replace(bundle, events=(event, bundle.events[1]))
    elif mutation == "unaccepted-event":
        event = {**bundle.events[0], "ledger_kind": "rejected"}
        bundle = replace(bundle, events=(event, bundle.events[1]))
    elif mutation == "not-retired":
        physical = {**bundle.audit_plays[0], "hidden_at": None}
        bundle = replace(bundle, audit_plays=(physical, bundle.audit_plays[1]))
    elif mutation == "missing-current-snapshot":
        bundle = replace(bundle, snapshots=(bundle.snapshots[0],))
    elif mutation == "missing-historical-snapshot":
        bundle = replace(bundle, snapshots=(bundle.snapshots[1],))
    elif mutation == "unbound-audit-physical":
        physical = {**bundle.audit_plays[0], "id": UUID(int=300)}
        bundle = replace(bundle, audit_plays=(*bundle.audit_plays, physical))
    elif mutation == "duplicate-snapshot":
        bundle = replace(bundle, snapshots=(*bundle.snapshots, bundle.snapshots[0]))
    if mutation in {
        "other-tenant-snapshot",
        "other-game-snapshot",
        "unknown-source",
        "wrong-generation",
        "wrong-version",
    }:
        bundle = replace(bundle, snapshots=(old, bundle.snapshots[1]))
    assert missing_supply_columns(bundle) == tuple(range(88))
    with pytest.raises(PlayExportSupplyError):
        build_play_export_tables(bundle)
