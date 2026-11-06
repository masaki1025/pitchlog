"""毎球CSVは保存版を照合し、非play変更もmanifestへ束縛する。"""

from copy import deepcopy
from dataclasses import replace
from uuid import UUID

import pytest

from pitchlog.exports.play_export_csv import missing_supply_columns, snapshot_id_for
from pitchlog.exports.play_rows import CSV_HEADERS
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
