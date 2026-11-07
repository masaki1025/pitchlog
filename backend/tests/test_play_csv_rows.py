"""毎球CSVの完成値検証と候補schemaの全数一致を確認する。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from itertools import chain, repeat
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.exports.play_rows import (
    CSV_HEADERS,
    PlayExportSupplyError,
    SavedCsvRow,
    saved_values,
)

GAME = UUID("11111111-1111-4111-8111-111111111111")
SNAPSHOT = "a" * 64


def _values(name="plays.csv"):
    return {
        header: str(GAME) if header == "game_id" else None
        for header in CSV_HEADERS[name]
    }


def _read(rows, **limits):
    return list(
        saved_values(
            "plays.csv",
            rows,
            SNAPSHOT,
            game_id=GAME,
            max_rows=limits.get("max_rows", 10),
            max_cell_chars=limits.get("max_cell_chars", 100),
            max_row_chars=limits.get("max_row_chars", 1000),
        )
    )


def test_candidate_headers_match_all_88_and_all_sidecars() -> None:
    """製品の候補列が全88列/全10sidecarからずれない。"""
    feature = Path(__file__).resolve().parents[2] / "docs/features/ud2-csv-export"
    columns = json.loads((feature / "columns.candidate.json").read_text())
    sidecars = json.loads((feature / "sidecars.candidate.json").read_text())
    assert (
        tuple(column["header"] for column in columns["columns"])
        == CSV_HEADERS["plays.csv"]
    )
    assert len(CSV_HEADERS["plays.csv"]) == 88
    assert {item["file"]: tuple(item["headers"]) for item in sidecars["files"]} == {
        name: headers for name, headers in CSV_HEADERS.items() if name != "plays.csv"
    }


def test_saved_values_preserve_order_and_explicit_null_zero_and_text() -> None:
    """元の値を計算せずschema順へ並べる。"""
    values = _values()
    values["球数"] = 0
    values["打席Id"] = "=日本語\nコメント"
    values["球速"] = "142.25"
    row = _read([SavedCsvRow(GAME, SNAPSHOT, dict(reversed(list(values.items()))))])[0]
    assert row[34] == 0
    assert row[56] == "142.25"
    assert row[60] == "=日本語\nコメント"
    assert row[0] is None


@pytest.mark.parametrize("change", ["missing", "extra", "snapshot", "game", "bad_type"])
def test_missing_extra_or_wrong_source_never_becomes_empty(change) -> None:
    """未供給・余剰・異版・異試合を空値で補完しない。"""
    values = _values()
    if change == "missing":
        values.pop("球数")
    if change == "extra":
        values["追加"] = 1
    if change == "bad_type":
        values["球数"] = True
    row = SavedCsvRow(
        UUID(int=2) if change == "game" else GAME,
        "b" * 64 if change == "snapshot" else SNAPSHOT,
        values,
    )
    with pytest.raises(PlayExportSupplyError):
        _read([row])


def test_sidecar_game_cell_must_match_snapshot_game() -> None:
    """行封筒だけが正しくても別試合セルは拒否する。"""
    values = _values("events.csv")
    values["game_id"] = str(UUID(int=2))
    with pytest.raises(PlayExportSupplyError):
        list(
            saved_values(
                "events.csv",
                [SavedCsvRow(GAME, SNAPSHOT, values)],
                SNAPSHOT,
                game_id=GAME,
                max_rows=10,
                max_cell_chars=100,
                max_row_chars=1000,
            )
        )


@pytest.mark.parametrize("value", [False, 1.5, {}, [], object()])
def test_non_supplied_cell_types_are_rejected(value) -> None:
    """bool/float/任意オブジェクトを自動変換しない。"""
    values = _values()
    values["球数"] = value
    with pytest.raises(PlayExportSupplyError):
        _read([SavedCsvRow(GAME, SNAPSHOT, values)])


@pytest.mark.parametrize(
    ("limits", "values"),
    [
        ({"max_cell_chars": 2}, {"打席Id": "長すぎる"}),
        ({"max_row_chars": 2}, {"打席Id": "長すぎる"}),
        ({"max_cell_chars": 2}, {"球数": 100}),
        ({"max_rows": 1}, {}),
        ({"max_rows": 0}, {}),
    ],
)
def test_supply_limits_reject_oversize_rows(limits, values) -> None:
    """行/文字/整数の上限は生成前に働く。"""
    row_values = {**_values(), **values}
    with pytest.raises(PlayExportSupplyError):
        _read([SavedCsvRow(GAME, SNAPSHOT, row_values)] * 2, **limits)


def test_three_digit_integer_at_limit_is_accepted() -> None:
    """bit長だけを十進桁数の代用にして有効値を拒否しない。"""
    values = {**_values(), "球数": 999}
    assert _read([SavedCsvRow(GAME, SNAPSHOT, values)], max_cell_chars=3)[0][34] == 999


def test_rows_are_consumed_only_when_requested() -> None:
    """未知長の供給を全件収集しない。"""
    consumed = []

    def rows():
        for value in range(10000):
            consumed.append(value)
            yield SavedCsvRow(GAME, SNAPSHOT, {**_values(), "球数": value})

    iterator = saved_values(
        "plays.csv",
        rows(),
        SNAPSHOT,
        game_id=GAME,
        max_rows=20000,
        max_cell_chars=100,
        max_row_chars=1000,
    )
    assert consumed == []
    assert next(iterator)[34] == 0
    assert consumed == [0]


@pytest.mark.parametrize(
    ("file", "header", "value"),
    [
        ("events.csv", "event_sequence", "01"),
        ("events.csv", "source_event_id", "not-a-uuid"),
        ("events.csv", "business_payload_json", '{"a":1,"a":2}'),
        ("events.csv", "state_diff_json", '{"value":NaN}'),
        ("events.csv", "is_tombstone", "yes"),
        ("events.csv", "replaced_at", "2026-02-30 00:00:00"),
        ("lineups.csv", "entries_json", "bad json"),
    ],
)
def test_sidecar_declared_cell_types_reject_invalid_completed_values(
    file, header, value
):
    """UUID/JSON/整数/boolean/日時の候補型も検証する。"""
    values = _values(file)
    values[header] = value
    with pytest.raises(PlayExportSupplyError):
        list(
            saved_values(
                file,
                [SavedCsvRow(GAME, SNAPSHOT, values)],
                SNAPSHOT,
                game_id=GAME,
                max_rows=10,
                max_cell_chars=100,
                max_row_chars=1000,
            )
        )


def test_sidecar_json_preserves_original_text_including_formula_and_null():
    """無害化前の文字列/NULLは元JSONで区別したまま保持する。"""
    text = '{"memo":"=1+1", "missing":null, "empty":"", "zero":0}'
    values = {**_values("events.csv"), "business_payload_json": text}
    result = list(
        saved_values(
            "events.csv",
            [SavedCsvRow(GAME, SNAPSHOT, values)],
            SNAPSHOT,
            game_id=GAME,
            max_rows=10,
            max_cell_chars=100,
            max_row_chars=1000,
        )
    )
    index = CSV_HEADERS["events.csv"].index("business_payload_json")
    assert result[0][index] == text


class _CountedRowMapping(Mapping):
    """長さを信用できない供給のキー/値アクセスを独立に数える。"""

    def __init__(self, keys, values):
        self.keys_source = keys
        self.supplied = values
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
        return self.supplied[key]


@pytest.mark.parametrize(
    "shape", ["large", "infinite", "duplicate", "missing", "extra_known"]
)
def test_untrusted_row_key_iteration_is_bounded_before_value_reads(shape):
    """巨大/無限/重複供給でも最大89キーで止まり、余剰値を読まない。"""
    headers = CSV_HEADERS["plays.csv"]
    keys = {
        "large": chain(headers, (f"extra-{i}" for i in range(10000))),
        "infinite": chain(headers, repeat("unknown")),
        "duplicate": repeat(headers[0]),
        "missing": iter(headers[:-1]),
        "extra_known": chain(headers, (headers[0],)),
    }[shape]
    mapping = _CountedRowMapping(keys, _values())
    with pytest.raises(PlayExportSupplyError):
        _read([SavedCsvRow(GAME, SNAPSHOT, mapping)], max_cell_chars=1, max_row_chars=1)
    assert mapping.key_reads <= 89
    assert mapping.value_reads == 0


def test_known_row_keys_are_read_once_without_using_mapping_length():
    """正常供給の88キー/値だけを有限取得し、長さ偽装へ依存しない。"""
    mapping = _CountedRowMapping(iter(CSV_HEADERS["plays.csv"]), _values())
    assert len(_read([SavedCsvRow(GAME, SNAPSHOT, mapping)])) == 1
    assert mapping.key_reads == mapping.value_reads == 88


def test_key_disappearing_before_value_read_is_rejected():
    """キー走査後に値が欠けても仮NULLで補わない。"""
    values = _values()
    del values["球数"]
    mapping = _CountedRowMapping(iter(CSV_HEADERS["plays.csv"]), values)
    with pytest.raises(PlayExportSupplyError, match="供給値"):
        _read([SavedCsvRow(GAME, SNAPSHOT, mapping)])
    assert mapping.value_reads <= 88
