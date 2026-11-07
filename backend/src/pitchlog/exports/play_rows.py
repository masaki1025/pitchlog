"""供給済み毎球CSVの全列・同一snapshotを検証する（計算を持たない）。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from pitchlog.exports.csv import CsvCell


class PlayExportSupplyError(ValueError):
    """完成保存値・列契約・版が揃わず出力できない場合。"""


# 候補schemaとpytestで全数照合する。正式資源受理済みとは扱わない。
_HEADERS: dict[str, tuple[str, ...]] = {
    "plays.csv": (
        "試合日時",
        "Season",
        "Kind",
        "Week",
        "Day",
        "GameNumber",
        "主審",
        "後攻チーム",
        "先攻チーム",
        "プレイの番号",
        "回",
        "表.裏",
        "先攻得点",
        "後攻得点",
        "S",
        "B",
        "アウト",
        "打席の継続",
        "イニング継続",
        "試合継続",
        "一走打順",
        "一走氏名",
        "二走打順",
        "二走氏名",
        "三走打順",
        "三走氏名",
        "打順",
        "打者氏名",
        "打席左右",
        "作戦",
        "作戦2",
        "作戦結果",
        "投手氏名",
        "投手左右",
        "球数",
        "捕手",
        "一走状況",
        "二走状況",
        "三走状況",
        "打者状況",
        "プレイの種類",
        "構え",
        "コースX",
        "コースY",
        "球種",
        "打撃結果",
        "打撃結果2",
        "捕球選手",
        "打球タイプ",
        "打球強度",
        "打球位置X",
        "打球位置Y",
        "牽制の種類",
        "牽制詳細",
        "エラーの種類",
        "タイムの種類",
        "球速",
        "プレス",
        "偽走",
        "打者位置",
        "打席Id",
        "打席結果",
        "Result_col",
        "打者登録名",
        "打者番号",
        "一走登録名",
        "一走番号",
        "二走登録名",
        "二走番号",
        "三走登録名",
        "三走番号",
        "投手番号",
        "入力項目",
        "先攻打順",
        "後攻打順",
        "経過時間",
        "開始時刻",
        "現在時刻",
        "top_poses",
        "top_names",
        "top_nums",
        "top_lrs",
        "bottom_poses",
        "bottom_names",
        "bottom_nums",
        "bottom_lrs",
        "top_score",
        "bottom_score",
    ),
    "play_links.csv": (
        "row_number",
        "game_id",
        "recording_generation",
        "event_sequence",
        "source_event_id",
        "play_row_id",
        "play_number",
        "version",
    ),
    "events.csv": (
        "game_id",
        "recording_generation",
        "event_sequence",
        "source_event_id",
        "event_kind",
        "d2",
        "target_generation",
        "target_event_sequence",
        "expected_version",
        "change_order",
        "is_tombstone",
        "replaced_at",
        "retired_at",
        "business_payload_json",
        "state_diff_json",
    ),
    "runners.csv": (
        "game_id",
        "recording_generation",
        "event_sequence",
        "source_event_id",
        "play_row_id",
        "runner_row_id",
        "base",
        "runner_id",
        "responsible_pitcher_id",
        "status",
        "status_source",
        "retired_at",
        "source_json",
    ),
    "lineups.csv": ("game_id", "lineup_id", "team_record_id", "entries_json"),
    "participations.csv": ("game_id", "participation_id", "source_json"),
    "game.csv": ("game_id", "source_json"),
    "references.csv": ("game_id", "reference_kind", "reference_id", "source_json"),
    "projections.csv": (
        "game_id",
        "recording_generation",
        "event_sequence",
        "source_event_id",
        "projection_kind",
        "source_version",
        "source_json",
    ),
    "preserved_sources.csv": (
        "game_id",
        "recording_generation",
        "event_sequence",
        "source_event_id",
        "preservation_kind",
        "source_json",
    ),
    "inning_scores.csv": (
        "game_id",
        "recording_generation",
        "event_sequence",
        "source_event_id",
        "play_row_id",
        "inning",
        "half",
        "state",
        "runs",
    ),
}
CSV_HEADERS: Mapping[str, tuple[str, ...]] = MappingProxyType(_HEADERS)
_SIDECAR_TYPES = {
    "play_links.csv": {
        "row_number": "decimal_integer_or_null",
        "game_id": "uuid",
        "recording_generation": "decimal_integer_or_null",
        "event_sequence": "decimal_integer_or_null",
        "source_event_id": "uuid",
        "play_row_id": "uuid",
        "play_number": "decimal_integer_or_null",
        "version": "decimal_integer_or_null",
    },
    "events.csv": {
        "game_id": "uuid",
        "recording_generation": "decimal_integer_or_null",
        "event_sequence": "decimal_integer_or_null",
        "source_event_id": "uuid",
        "event_kind": "supplied_text_or_null",
        "d2": "canonical_decimal_integer_or_null",
        "target_generation": "decimal_integer_or_null",
        "target_event_sequence": "decimal_integer_or_null",
        "expected_version": "canonical_decimal_integer_or_null",
        "change_order": "canonical_decimal_integer_or_null",
        "is_tombstone": "canonical_boolean_text",
        "replaced_at": "JST_timestamp_or_null",
        "retired_at": "JST_timestamp_or_null",
        "business_payload_json": "canonical_json_string",
        "state_diff_json": "canonical_json_string",
    },
    "runners.csv": {
        "game_id": "uuid",
        "recording_generation": "decimal_integer_or_null",
        "event_sequence": "decimal_integer_or_null",
        "source_event_id": "uuid",
        "play_row_id": "uuid",
        "runner_row_id": "uuid",
        "base": "canonical_decimal_integer_or_null",
        "runner_id": "uuid",
        "responsible_pitcher_id": "uuid",
        "status": "supplied_text_or_null",
        "status_source": "supplied_text_or_null",
        "retired_at": "JST_timestamp_or_null",
        "source_json": "canonical_json_string",
    },
    "lineups.csv": {
        "game_id": "uuid",
        "lineup_id": "uuid",
        "team_record_id": "uuid",
        "entries_json": "canonical_json_string",
    },
    "participations.csv": {
        "game_id": "uuid",
        "participation_id": "uuid",
        "source_json": "canonical_json_string",
    },
    "game.csv": {"game_id": "uuid", "source_json": "canonical_json_string"},
    "references.csv": {
        "game_id": "uuid",
        "reference_kind": "supplied_text_or_null",
        "reference_id": "source_key_string",
        "source_json": "canonical_json_string",
    },
    "projections.csv": {
        "game_id": "uuid",
        "recording_generation": "decimal_integer_or_null",
        "event_sequence": "decimal_integer_or_null",
        "source_event_id": "uuid",
        "projection_kind": "supplied_text_or_null",
        "source_version": "canonical_decimal_integer_or_null",
        "source_json": "canonical_json_string",
    },
    "preserved_sources.csv": {
        "game_id": "uuid",
        "recording_generation": "decimal_integer_or_null",
        "event_sequence": "decimal_integer_or_null",
        "source_event_id": "uuid",
        "preservation_kind": "supplied_text_or_null",
        "source_json": "canonical_json_string",
    },
    "inning_scores.csv": {
        "game_id": "uuid",
        "recording_generation": "decimal_integer_or_null",
        "event_sequence": "decimal_integer_or_null",
        "source_event_id": "uuid",
        "play_row_id": "uuid",
        "inning": "canonical_decimal_integer_or_null",
        "half": "supplied_text_or_null",
        "state": "supplied_text_or_null",
        "runs": "canonical_decimal_integer_or_null",
    },
}
SNAPSHOT_PATTERN = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True, slots=True)
class SavedCsvRow:
    """同一snapshotから供給された全セル。欠測と明示NULLを分ける。"""

    game_id: UUID
    snapshot_id: str
    values: Mapping[str, CsvCell]


def validate_snapshot_id(snapshot_id: str) -> None:
    """callerが渡した固定版の識別digestを検証する。"""
    if type(snapshot_id) is not str or SNAPSHOT_PATTERN.fullmatch(snapshot_id) is None:
        raise PlayExportSupplyError("出力snapshotの識別子が不正です")


def _unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """同じkeyのJSONを黙って上書きしない。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("重複JSONキー")
        result[key] = value
    return result


def _nonfinite_json(_value: str) -> object:
    """JSON外の非有限数を拒否する。"""
    raise ValueError("非有限JSON")


def _sidecar_cell(name: str, header: str, value: CsvCell) -> None:
    """候補のsidecarセル型だけを検証し、元の文字列は変えない。"""
    if value is None or name == "plays.csv":
        return
    kind = _SIDECAR_TYPES[name][header]
    if kind in ("decimal_integer_or_null", "canonical_decimal_integer_or_null"):
        if type(value) is int:
            return
        if type(value) is str and re.fullmatch(r"0|-?[1-9][0-9]*", value):
            return
        raise PlayExportSupplyError("整数セルの形式が不正です")
    if type(value) is not str:
        raise PlayExportSupplyError("完成文字列の供給が必要です")
    try:
        if kind == "uuid" and str(UUID(value)) != value:
            raise ValueError("非正準UUID")
        if kind == "canonical_json_string":
            json.loads(
                value, object_pairs_hook=_unique_json, parse_constant=_nonfinite_json
            )
        if kind == "canonical_boolean_text" and value not in ("true", "false"):
            raise ValueError("非正準boolean")
        if kind == "JST_timestamp_or_null":
            timestamp = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            if timestamp.strftime("%Y-%m-%d %H:%M:%S") != value:
                raise ValueError("非正準日時")
    except (ValueError, RecursionError) as error:
        raise PlayExportSupplyError("sidecarの完成値が不正です") from error


def _bounded_mapping[T](
    source: Mapping[str, T], headers: tuple[str, ...]
) -> dict[str, T]:
    """固定幅+1キーまでで検査し、既知キーの値だけを有限取得する。"""
    expected = frozenset(headers)
    seen: set[str] = set()
    for position, key in enumerate(source):
        if position >= len(headers):
            raise PlayExportSupplyError("供給に余剰キーがあります")
        if type(key) is not str or key not in expected or key in seen:
            raise PlayExportSupplyError("供給に未知または重複キーがあります")
        seen.add(key)
    if seen != expected:
        raise PlayExportSupplyError("供給キーが不足しています")
    # 任意Mappingをdict化しない。上のキー走査も未知キーの値を取得しない。
    result: dict[str, T] = {}
    try:
        for key in headers:
            result[key] = source[key]
    except KeyError as error:
        raise PlayExportSupplyError("供給値が不足しています") from error
    return result


def saved_values(
    name: str,
    rows: Iterable[SavedCsvRow],
    snapshot_id: str,
    *,
    game_id: UUID,
    max_rows: int,
    max_cell_chars: int,
    max_row_chars: int,
) -> Iterator[tuple[CsvCell, ...]]:
    """全列が実供給された行だけを元の順に一行ずつ取り出す。

    値の補完・整数化・座標変換・表示再生成・並べ替えはしない。

    Args:
        name: 固定されたCSV名。
        rows: 同一版の完成保存値。
        snapshot_id: 出力全体の版。
        game_id: 出力する試合。
        max_rows: このファイルのデータ行上限。
        max_cell_chars: 文字列セル一つの上限。
        max_row_chars: 一行の文字列合計上限。

    Yields:
        schemaの列順に並ぶ供給値。

    Raises:
        PlayExportSupplyError: 欠測・余剰・版不一致・型・上限違反の場合。
    """
    validate_snapshot_id(snapshot_id)
    if name not in CSV_HEADERS:
        raise PlayExportSupplyError("未登録の出力ファイルです")
    for limit in (max_rows, max_cell_chars, max_row_chars):
        if type(limit) is not int or limit < 1:
            raise PlayExportSupplyError("出力上限は正の整数が必要です")
    headers = CSV_HEADERS[name]
    for count, row in enumerate(rows, start=1):
        if count > max_rows:
            raise PlayExportSupplyError("出力行数の上限を超えました")
        if (
            type(row) is not SavedCsvRow
            or row.snapshot_id != snapshot_id
            or type(row.game_id) is not UUID
            or row.game_id != game_id
        ):
            raise PlayExportSupplyError("供給行のsnapshotが一致しません")
        if not isinstance(row.values, Mapping):
            raise PlayExportSupplyError("供給行は全列の写像が必要です")
        values = _bounded_mapping(row.values, headers)
        if "game_id" in values and values["game_id"] != str(game_id):
            raise PlayExportSupplyError("供給セルの試合が一致しません")
        width = 0
        result: list[CsvCell] = []
        for header in headers:
            value = values[header]
            if value is not None and type(value) not in (str, int):
                raise PlayExportSupplyError("セルは完成文字列・整数・NULLが必要です")
            if type(value) is str:
                if len(value) > max_cell_chars:
                    raise PlayExportSupplyError("供給セルの上限を超えました")
                width += len(value)
            elif type(value) is int:
                # 巨大整数の文字列化も上限内に制限する。
                if value.bit_length() > max_cell_chars * 4:
                    raise PlayExportSupplyError("供給整数の上限を超えました")
                try:
                    integer_size = len(str(value))
                except ValueError as error:
                    raise PlayExportSupplyError("供給整数を変換できません") from error
                if integer_size > max_cell_chars:
                    raise PlayExportSupplyError("供給整数の上限を超えました")
                width += integer_size
            if width > max_row_chars:
                raise PlayExportSupplyError("供給行の上限を超えました")
            _sidecar_cell(name, header, value)
            result.append(value)
        yield tuple(result)
