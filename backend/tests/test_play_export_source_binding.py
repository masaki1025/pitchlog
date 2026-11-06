"""毎球CSVは保存版を照合し、非play変更もmanifestへ束縛する。"""

from copy import deepcopy
from dataclasses import replace
from uuid import UUID

import pytest

from pitchlog.exports.play_export_csv import (
    build_play_export_tables,
    missing_supply_columns,
    snapshot_id_for,
)
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.play_export import PlayExportBundle

TENANT, GAME, PLAY, EVENT = (UUID(int=value) for value in range(1, 5))


def _bundle() -> PlayExportBundle:
    return PlayExportBundle(
        game={"id": GAME, "tenant_id": TENANT},
        plays=({"id": PLAY, "source_event_id": EVENT, "version": 2, "play_number": 1},),
        events=({"id": EVENT, "generation": 3, "d2": 1001, "ledger_kind": "accepted"},),
        snapshots=(
            {
                "tenant_id": TENANT,
                "game_id": GAME,
                "play_row_id": PLAY,
                "source_event_id": EVENT,
                "play_version": 2,
                "recording_generation": 3,
                "event_sequence": 1001,
                "plays_csv_json": dict.fromkeys(CSV_HEADERS["plays.csv"], ""),
                "full_innings_json": [
                    {"inning": 1, "half": "top", "state": "in-progress", "runs": 0},
                    {"inning": 1, "half": "bottom", "state": "unplayed", "runs": None},
                ],
            },
        ),
        runners=(),
        lineups=(),
        participations=(),
        players=(),
        teams=(),
        tenant_vocabularies=(),
        admin_vocabularies=(),
        runner_snapshots=(),
        snapshot_available=True,
    )


def test_exact_snapshot_source_version_is_available() -> None:
    """正しい原本/版のみを利用可能とする。"""
    assert missing_supply_columns(_bundle()) == ()


@pytest.mark.parametrize(
    "key,value",
    [
        ("recording_generation", 2),
        ("event_sequence", 1),
        ("play_version", 1),
        ("source_event_id", UUID(int=9)),
        ("tenant_id", UUID(int=9)),
        ("game_id", UUID(int=9)),
        ("play_version", True),
        ("play_version", None),
    ],
)
def test_stale_or_unbound_snapshot_is_unavailable(key: str, value: object) -> None:
    """旧版/型不正/別原本を全列未供給として拒否する。"""
    bundle = _bundle()
    snapshot = deepcopy(bundle.snapshots[0])
    snapshot[key] = value
    assert missing_supply_columns(replace(bundle, snapshots=(snapshot,))) == tuple(
        range(88)
    )


def test_duplicate_or_unaccepted_source_is_unavailable() -> None:
    """重複snapshotや未受理原本を拒否する。"""
    bundle = _bundle()
    assert missing_supply_columns(
        replace(bundle, snapshots=(*bundle.snapshots, *bundle.snapshots))
    ) == tuple(range(88))
    assert missing_supply_columns(replace(bundle, events=())) == tuple(range(88))
    assert missing_supply_columns(
        replace(bundle, events=({**bundle.events[0], "ledger_kind": "evacuated"},))
    ) == tuple(range(88))


@pytest.mark.parametrize(
    "field",
    ["events", "lineups", "participations", "players", "teams", "runner_snapshots"],
)
def test_nonplay_or_sidecar_source_changes_manifest(field: str) -> None:
    """非playと補助資源の版変更もmanifestへ反映する。"""
    bundle = _bundle()
    changed = replace(
        bundle, **{field: (*getattr(bundle, field), {"id": UUID(int=9), "version": 2})}
    )
    assert snapshot_id_for(changed) != snapshot_id_for(bundle)


def test_changed_export_cell_changes_manifest() -> None:
    """保存済みCSVセルの変更も版digestへ反映する。"""
    bundle = _bundle()
    snapshot = deepcopy(bundle.snapshots[0])
    snapshot["plays_csv_json"][CSV_HEADERS["plays.csv"][0]] = "変更"
    assert snapshot_id_for(replace(bundle, snapshots=(snapshot,))) != snapshot_id_for(
        bundle
    )


def test_saved_full_innings_sidecar_preserves_state_and_source() -> None:
    """同じ保存版の0/NULLとsourceを全回sidecarへ運ぶ。"""
    snapshot, tables = build_play_export_tables(_bundle())
    rows = list(tables["inning_scores.csv"])
    assert len(rows) == 2
    assert all(row.snapshot_id == snapshot.snapshot_id for row in rows)
    assert [row.values["runs"] for row in rows] == [0, None]
    assert [row.values["source_event_id"] for row in rows] == [str(EVENT)] * 2


def test_thirteenth_inning_is_not_lost_in_twelve_slot_display() -> None:
    """保存済み13回も旧12枠から再計算せず全回へ写す。"""
    bundle = _bundle()
    stored = deepcopy(bundle.snapshots[0])
    stored["full_innings_json"] = [
        {"inning": inning, "half": half, "state": "completed", "runs": 0}
        for inning in range(1, 14)
        for half in ("top", "bottom")
    ]
    _version, tables = build_play_export_tables(replace(bundle, snapshots=(stored,)))
    rows = list(tables["inning_scores.csv"])
    assert len(rows) == 26
    assert [(row.values["inning"], row.values["half"]) for row in rows[-2:]] == [
        (13, "top"),
        (13, "bottom"),
    ]


@pytest.mark.parametrize("change", ["missing", "duplicate", "unplayed_zero"])
def test_full_innings_missing_or_ambiguous_is_not_exported(change: str) -> None:
    """欠測・重複回・未消化0補完は409相当の供給失敗へ閉じる。"""
    bundle = _bundle()
    snapshot = deepcopy(bundle.snapshots[0])
    if change == "missing":
        snapshot.pop("full_innings_json")
    elif change == "duplicate":
        snapshot["full_innings_json"][1]["inning"] = 2
    else:
        snapshot["full_innings_json"][1]["runs"] = 0
    _version, tables = build_play_export_tables(
        replace(bundle, snapshots=(snapshot,))
    )
    with pytest.raises(PlayExportSupplyError):
        list(tables["inning_scores.csv"])
