"""CSV私有ディスク退避の型保持・境界・cleanup・メモリを検証する。"""

import tracemalloc
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from test_play_export_source_binding import _bundle

from pitchlog.exports.play_export_csv import missing_supply_columns, snapshot_id_for
from pitchlog.repositories.play_export_spool import ExportRowStore, current_row_store


def test_spool_roundtrip_keeps_typed_values_and_business_tags() -> None:
    """UUID/日時/小数を保ち、同形の利用者JSONを型タグへ誤変換しない。"""
    row = {
        "id": UUID(int=5),
        "day": date(2026, 11, 7),
        "at": datetime(2026, 11, 7, tzinfo=timezone.utc),
        "numeric": Decimal("1.20"),
        "payload": {"uuid": "user-data", "nested": ["uuid", "business"]},
    }
    with ExportRowStore() as store:
        rows = store.rows((row,))
        assert list(rows) == [row]
        assert rows.index_by("id")[UUID(int=5)] == row
        path = Path(store.directory.name)
        assert current_row_store() is None
        with store.capture():
            assert current_row_store() is store
        assert current_row_store() is None
    assert not path.exists()


def test_disk_bundle_has_same_snapshot_validation_and_digest() -> None:
    """ディスク/メモリの同値原本は同じmanifest版と拒否結果を返す。"""
    bundle = _bundle()
    with ExportRowStore() as store:
        disk = replace(
            bundle,
            **{
                name: store.rows(getattr(bundle, name))
                for name in (
                    "plays",
                    "events",
                    "snapshots",
                    "runners",
                    "lineups",
                    "participations",
                    "players",
                    "teams",
                    "tenant_vocabularies",
                    "admin_vocabularies",
                    "runner_snapshots",
                )
            },
        )
        assert missing_supply_columns(disk) == ()
        assert snapshot_id_for(disk) == snapshot_id_for(bundle)
        bad = {**bundle.snapshots[0], "play_version": 999}
        assert missing_supply_columns(
            replace(disk, snapshots=store.rows((bad,)))
        ) == tuple(range(88))
        duplicate = store.rows((*bundle.snapshots, *bundle.snapshots))
        assert missing_supply_columns(replace(disk, snapshots=duplicate)) == tuple(
            range(88)
        )


def test_spool_limits_fail_before_archive_and_cleanup() -> None:
    """小さい明示容量を越えたら失敗し、私有ファイルを残さない。"""
    with pytest.raises(ValueError, match="容量"):
        with ExportRowStore(max_bytes=100, max_row_bytes=100) as store:
            path = Path(store.directory.name)
            store.rows(({"large": "a" * 1000},))
    assert not path.exists()


def test_disk_indexes_and_rows_do_not_grow_python_heap_with_all_data() -> None:
    """20MB超の原本を退避し、500/501/2001境界で有限heapを実測する。"""
    tracemalloc.start()
    try:
        with ExportRowStore() as store:
            rows = store.rows(
                {"id": UUID(int=i + 1), "payload": str(i) + "x" * 10000}
                for i in range(2001)
            )
            keys = store.keys()
            for i in range(2001):
                keys.add(UUID(int=i + 1))
                keys.add(UUID(int=i + 1))
            assert len(rows) == 2001
            assert rows[499]["id"] == UUID(int=500)
            assert rows[500]["id"] == UUID(int=501)
            assert rows[-1]["id"] == UUID(int=2001)
            assert sum(1 for _ in rows) == 2001
            assert sum(1 for _ in keys) == 2001
            index = rows.index_by("id")
            assert len(index) == 2001
            assert index[UUID(int=2001)]["payload"].startswith("2000")
            assert store.bytes > 20_000_000
            _, peak = tracemalloc.get_traced_memory()
            assert peak < 4_000_000
    finally:
        tracemalloc.stop()
