"""全11CSVのZIP完成・hash・故障cleanupを独立readerで検証する。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from dataclasses import replace
from itertools import chain, repeat
from uuid import UUID

import pytest

from pitchlog.exports import archive
from pitchlog.exports.archive import (
    ExportLimits,
    ExportSnapshot,
    PlayExportArchiveError,
    prepare_play_archive,
)
from pitchlog.exports.csv import CsvSerializationError
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError, SavedCsvRow

GAME = UUID("11111111-1111-4111-8111-111111111111")
SNAPSHOT = ExportSnapshot(GAME, "a" * 64, "b" * 64, "2026-11-04 13:04:05")


def _empty_tables():
    return {name: () for name in CSV_HEADERS}


def _row(**changes):
    return SavedCsvRow(
        GAME,
        SNAPSHOT.snapshot_id,
        {**dict.fromkeys(CSV_HEADERS["plays.csv"]), **changes},
    )


def test_completed_archive_manifest_hashes_and_independent_csv_reader() -> None:
    """全CSV/manifestの実bytesを独立ZIP/CSV readerで照合する。"""
    tables = _empty_tables()
    tables["plays.csv"] = [_row(球数=0, 打席Id='=式,"日本語"\n次行', 球速="142.5")]
    with prepare_play_archive(SNAPSHOT, tables) as output:
        handle = output.file
        data = b"".join(output.chunks(17))
        assert len(data) == output.byte_length
        assert hashlib.sha256(data).hexdigest() == output.sha256
        assert output.filename == f"pitchlog-plays-{GAME}.zip"
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            assert set(bundle.namelist()) == set(CSV_HEADERS) | {"manifest.json"}
            manifest = json.loads(bundle.read("manifest.json"))
            assert manifest["snapshot_id"] == SNAPSHOT.snapshot_id
            assert manifest["source_versions"] == SNAPSHOT.source_versions
            assert manifest["column_semantics"]["打球位置X/打球位置Y"] == {
                "coordinate_system": "normalized-bottom-left",
                "unit": "0..1",
                "value_source": "accepted-V7-decimal",
                "legacy_pixel_bytes": False,
            }
            assert (
                manifest["column_semantics"]["経過時間"]["clock"] == "server-accepted"
            )
            assert manifest["column_semantics"]["打席結果/Result_col"] == {
                "value_source": "accepted-play-result-and-D1-display",
                "same_value": True,
                "independent_result_decision": False,
                "legacy_default_zero": False,
            }
            for item in manifest["files"]:
                raw = bundle.read(item["name"])
                assert item["byte_length"] == len(raw)
                assert item["sha256"] == hashlib.sha256(raw).hexdigest()
                rows = list(
                    csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
                )
                assert rows[0] == list(CSV_HEADERS[item["name"]])
                assert item["data_row_count"] == len(rows) - 1
                if item["name"] == "plays.csv":
                    assert rows[1][34] == "0"
                    assert rows[1][0] == ""
                    assert rows[1][56] == "142.5"
                    assert rows[1][60] == '\'=式,"日本語"\n次行'
        assert not handle.closed
    assert handle.closed


@pytest.mark.parametrize(
    "name", ["../bad.csv", "/tmp/bad.csv", "bad\\file.csv", "manifest.json"]
)
def test_untrusted_file_names_are_rejected_before_spooling(name, monkeypatch) -> None:
    """固定名以外をZIPへ一切入れない。"""

    def forbidden(*args, **kwargs):
        pytest.fail("不正ファイル名でspoolを開いた")

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", forbidden)
    tables = _empty_tables()
    tables[name] = ()
    with pytest.raises(PlayExportSupplyError):
        with prepare_play_archive(SNAPSHOT, tables):
            pytest.fail("不正資源を成功にした")


def test_missing_sidecar_is_not_a_successful_empty_file() -> None:
    """明示的0行と未供給ファイルを分ける。"""
    tables = _empty_tables()
    del tables["events.csv"]
    with pytest.raises(PlayExportSupplyError):
        with prepare_play_archive(SNAPSHOT, tables):
            pytest.fail("欠測資源を成功にした")


@pytest.mark.parametrize(
    "field", ["max_file_bytes", "max_total_bytes", "max_archive_bytes"]
)
def test_byte_limits_close_spool_on_failure(field, monkeypatch) -> None:
    """CSV/展開後総量/ZIPの各上限を超えたら一時出力を閉じる。"""
    opened = []
    real = archive.tempfile.TemporaryFile

    def tracked(*args, **kwargs):
        file = real(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", tracked)
    limits = replace(ExportLimits(), **{field: 10})
    with pytest.raises(PlayExportArchiveError):
        with prepare_play_archive(SNAPSHOT, _empty_tables(), limits=limits):
            pytest.fail("容量超過を成功にした")
    assert len(opened) == 1 and opened[0].closed


def test_late_source_failure_never_yields_completed_handle(monkeypatch) -> None:
    """後半行で供給が壊れても、完成ハンドルを一度も渡さない。"""
    opened = []
    real = archive.tempfile.TemporaryFile

    def tracked(*args, **kwargs):
        file = real(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", tracked)

    def rows():
        yield _row(球数=0)
        raise OSError("test source failure")

    tables = _empty_tables()
    tables["plays.csv"] = rows()
    with pytest.raises(OSError, match="test source failure"):
        with prepare_play_archive(SNAPSHOT, tables):
            pytest.fail("途中失敗を成功にした")
    assert opened[0].closed


def test_temporary_disk_failure_is_propagated(monkeypatch) -> None:
    """一時ディスクの確保失敗を無内容の成功へ変えない。"""

    def fail(*args, **kwargs):
        raise OSError("test ENOSPC")

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", fail)
    with pytest.raises(OSError, match="test ENOSPC"):
        with prepare_play_archive(SNAPSHOT, _empty_tables()):
            pytest.fail("spool失敗を成功にした")


def test_consumer_cancel_closes_completed_spool() -> None:
    """途中送出で呼出側が取消してもcontextの終了で閉じる。"""
    with pytest.raises(RuntimeError, match="cancelled"):
        with prepare_play_archive(SNAPSHOT, _empty_tables()) as output:
            file = output.file
            assert next(output.chunks(8)).startswith(b"PK")
            raise RuntimeError("cancelled")
    assert file.closed


def test_completed_file_tampering_is_detected_on_full_consumption() -> None:
    """完成後の切詰めや内容変化はhash/サイズ不一致になる。"""
    with prepare_play_archive(SNAPSHOT, _empty_tables()) as output:
        output.file.seek(10)
        output.file.write(b"corrupted")
        with pytest.raises(PlayExportArchiveError):
            b"".join(output.chunks())


def test_invalid_csv_control_character_cannot_escape_as_complete_zip() -> None:
    """共有writerの拒否をZIP層が黙殺しない。"""
    tables = _empty_tables()
    tables["plays.csv"] = [_row(打席Id="bad\x00text")]
    with pytest.raises(CsvSerializationError):
        with prepare_play_archive(SNAPSHOT, tables):
            pytest.fail("CSV失敗を成功にした")


@pytest.mark.parametrize(
    "kwargs", [{"max_rows_per_file": 0}, {"chunk_size": True}, {"max_cell_chars": -1}]
)
def test_invalid_limits_are_rejected(kwargs) -> None:
    """無制限・bool・負上限を拒否する。"""
    with pytest.raises(PlayExportArchiveError):
        ExportLimits(**kwargs)


@pytest.mark.parametrize(
    "change",
    [
        {"snapshot_id": "unknown"},
        {"source_versions": "A" * 64},
        {"exported_at": "2026-2-30 00:00:00"},
        {"game_id": "../bad"},
    ],
)
def test_invalid_snapshot_metadata_is_rejected(change) -> None:
    """ファイル名や版へ不正メタデータを流さない。"""
    with pytest.raises(PlayExportSupplyError):
        replace(SNAPSHOT, **change)


def test_every_sidecar_can_contain_typed_values_and_remains_in_manifest():
    """全10sidecarに実行が到達し、明示NULLとJSONを元のまま運ぶ。"""
    tables = _empty_tables()
    for name, headers in CSV_HEADERS.items():
        if name == "plays.csv":
            continue
        values = dict.fromkeys(headers)
        values["game_id"] = str(GAME)
        for header in headers:
            if header.endswith("_json"):
                values[header] = '{"memo":"=日本語","zero":0,"null":null}'
        if "source_event_id" in values:
            values["source_event_id"] = "22222222-2222-4222-8222-222222222222"
            values["recording_generation"] = "1"
            values["event_sequence"] = "1"
        tables[name] = [SavedCsvRow(GAME, SNAPSHOT.snapshot_id, values)]
    with prepare_play_archive(SNAPSHOT, tables) as output:
        with zipfile.ZipFile(output.file) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            assert len(manifest["files"]) == 11
            for record in manifest["files"]:
                assert record["data_row_count"] == (
                    0 if record["name"] == "plays.csv" else 1
                )


def test_disk_write_failure_after_spool_creation_closes_handle(monkeypatch):
    """確保後の実書込故障でも部分ZIPを返さずcloseする。"""

    class FailingDisk(io.BytesIO):
        def write(self, data):
            raise OSError("test disk write failure")

    file = FailingDisk()
    monkeypatch.setattr(archive.tempfile, "TemporaryFile", lambda **kwargs: file)
    with pytest.raises(OSError, match="test disk write failure"):
        with prepare_play_archive(SNAPSHOT, _empty_tables()):
            pytest.fail("書込失敗を成功にした")
    assert file.closed


def test_crc_verification_failure_closes_handle_before_success(monkeypatch):
    """最終CRC照合が失敗したら完成ハンドルを渡さない。"""
    opened = []
    real = archive.tempfile.TemporaryFile

    def tracked(*args, **kwargs):
        file = real(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", tracked)
    monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: "plays.csv")
    with pytest.raises(PlayExportArchiveError, match="CRC"):
        with prepare_play_archive(SNAPSHOT, _empty_tables()):
            pytest.fail("CRC不一致を成功にした")
    assert opened[0].closed


def test_row_limit_is_enforced_during_archive_generation():
    """巨大供給をすべて消費する前に行上限で止める。"""
    consumed = []

    def rows():
        for value in range(10000):
            consumed.append(value)
            yield _row(球数=value)

    tables = _empty_tables()
    tables["plays.csv"] = rows()
    with pytest.raises(PlayExportSupplyError, match="行数"):
        with prepare_play_archive(
            SNAPSHOT, tables, limits=ExportLimits(max_rows_per_file=2)
        ):
            pytest.fail("行超過を成功にした")
    assert consumed == [0, 1, 2]


def test_independent_full_88_cell_golden_is_preserved():
    """固定goldenの全88セルを独立CSV readerで一括照合する。"""
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[2] / (
        "docs/features/ud2-csv-export/step1-independent-golden.json"
    )
    golden = json.loads(fixture.read_text())
    assert len(golden["saved_values"]) == 88
    tables = _empty_tables()
    tables["plays.csv"] = [
        SavedCsvRow(
            GAME,
            SNAPSHOT.snapshot_id,
            dict(zip(CSV_HEADERS["plays.csv"], golden["saved_values"], strict=True)),
        )
    ]
    with prepare_play_archive(SNAPSHOT, tables) as output:
        with zipfile.ZipFile(output.file) as bundle:
            rows = list(
                csv.reader(
                    io.StringIO(
                        bundle.read("plays.csv").decode("utf-8-sig"),
                        newline="",
                    )
                )
            )
    assert rows[1] == golden["expected_csv_cells"]


class _CountedTableMapping(Mapping):
    """外側供給の未知長キー列と値アクセス数を制御する。"""

    def __init__(self, keys, values, *, fail_key=None):
        self.keys_source = keys
        self.supplied = values
        self.fail_key = fail_key
        self.key_reads = 0
        self.value_reads = 0

    def __iter__(self):
        for key in self.keys_source:
            self.key_reads += 1
            yield key

    def __len__(self):
        raise AssertionError("任意Mappingのlenを信用した")

    def __getitem__(self, key):
        self.value_reads += 1
        if key == self.fail_key:
            raise OSError("test mapping value read failure")
        return self.supplied[key]


@pytest.mark.parametrize(
    "shape", ["large", "infinite", "duplicate", "missing", "extra_known"]
)
def test_outer_mapping_is_bounded_before_spool_and_value_reads(shape, monkeypatch):
    """巨大/無限の外側供給は12キー以内で拒否しspoolを確保しない。"""
    names = tuple(CSV_HEADERS)
    keys = {
        "large": chain(names, (f"extra-{i}" for i in range(10000))),
        "infinite": chain(names, repeat("unknown")),
        "duplicate": repeat(names[0]),
        "missing": iter(names[:-1]),
        "extra_known": chain(names, (names[0],)),
    }[shape]
    mapping = _CountedTableMapping(keys, _empty_tables())

    def forbidden(*args, **kwargs):
        pytest.fail("不正Mappingでspoolを確保した")

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", forbidden)
    with pytest.raises(PlayExportSupplyError):
        with prepare_play_archive(SNAPSHOT, mapping):
            pytest.fail("不正Mappingを成功にした")
    assert mapping.key_reads <= 12
    assert mapping.value_reads == 0


def test_valid_outer_mapping_reads_only_eleven_values_without_length():
    """正しい11資源は長さ偽装に依存せず一回ずつ読める。"""
    mapping = _CountedTableMapping(iter(CSV_HEADERS), _empty_tables())
    with prepare_play_archive(SNAPSHOT, mapping) as output:
        assert output.byte_length > 0
    assert mapping.key_reads == mapping.value_reads == 11


def test_outer_value_read_failure_occurs_before_spooling(monkeypatch):
    """外側の既知値getter故障でも完成物や一時fileを作らない。"""
    mapping = _CountedTableMapping(
        iter(CSV_HEADERS), _empty_tables(), fail_key="events.csv"
    )

    def forbidden(*args, **kwargs):
        pytest.fail("値取得故障後にspoolを確保した")

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", forbidden)
    with pytest.raises(OSError, match="mapping value read"):
        with prepare_play_archive(SNAPSHOT, mapping):
            pytest.fail("読出故障を成功にした")
    assert mapping.value_reads <= 10


def test_inner_mapping_read_failure_closes_spool_without_success(monkeypatch):
    """一行のgetter故障は生成途中のZIPを閉じ完成物を返さない。"""
    opened = []
    real = archive.tempfile.TemporaryFile

    def tracked(*args, **kwargs):
        file = real(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", tracked)
    mapping = _CountedTableMapping(
        iter(CSV_HEADERS["plays.csv"]),
        dict.fromkeys(CSV_HEADERS["plays.csv"]),
        fail_key="球数",
    )
    tables = _empty_tables()
    tables["plays.csv"] = [SavedCsvRow(GAME, SNAPSHOT.snapshot_id, mapping)]
    with pytest.raises(OSError, match="mapping value read"):
        with prepare_play_archive(SNAPSHOT, tables):
            pytest.fail("行読出故障を成功にした")
    assert mapping.key_reads == 88
    assert mapping.value_reads <= 88
    assert opened[0].closed


def test_infinite_inner_mapping_closes_spool_before_success(monkeypatch):
    """無限の一行キーでも固定幅で止まり、確保済みspoolを閉じる。"""
    opened = []
    real = archive.tempfile.TemporaryFile

    def tracked(*args, **kwargs):
        file = real(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(archive.tempfile, "TemporaryFile", tracked)
    mapping = _CountedTableMapping(
        chain(CSV_HEADERS["plays.csv"], repeat("unknown")), {}
    )
    tables = _empty_tables()
    tables["plays.csv"] = [SavedCsvRow(GAME, SNAPSHOT.snapshot_id, mapping)]
    with pytest.raises(PlayExportSupplyError):
        with prepare_play_archive(SNAPSHOT, tables):
            pytest.fail("無限Mappingを成功にした")
    assert mapping.key_reads == 89
    assert mapping.value_reads == 0
    assert opened[0].closed
