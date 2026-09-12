"""操作イベント種別の正本・コード・manifest 契約を照合する。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from type_boundary_contract import (
    _markdown_tables,
    _plain_markdown_cell,
    _section_body,
)

from pitchlog.db.sync_protocol.event_kinds import (
    CONDITIONAL_EVENT_KIND_LITERALS,
    EVENT_KIND_LITERALS,
    OPERATION_EVENT_PARTICIPATIONS,
    STATE_CORRECTION_EVENT_KIND,
    ParticipationBinding,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"
_DESIGN_PATH = (
    _REPOSITORY_ROOT / "docs" / "features" / "orm-schema-migration" / "design.md"
)
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"


def _canonical_participation_kinds(document: str) -> tuple[tuple[int, str], ...]:
    """正本 5-3 節の参加区分表から番号と種別名を文書順に抽出する。"""
    body = _section_body(document, "5-3")
    candidates: list[tuple[tuple[int, str], ...]] = []
    for headers, rows in _markdown_tables(body):
        plain_headers = [_plain_markdown_cell(header) for header in headers]
        if not {"参加区分", "種別", "自身の D2"} <= set(plain_headers):
            continue
        number_index = plain_headers.index("参加区分")
        kind_index = plain_headers.index("種別")
        contracts: list[tuple[int, str]] = []
        for row in rows:
            number_text = _plain_markdown_cell(row[number_index])
            number_match = re.fullmatch(r"#(?P<number>\d+)", number_text)
            if number_match is None:
                raise ValueError(f"参加区分番号を解決できない: {number_text}")
            contracts.append(
                (
                    int(number_match.group("number")),
                    _plain_markdown_cell(row[kind_index]),
                )
            )
        candidates.append(tuple(contracts))
    if len(candidates) != 1:
        raise ValueError(f"参加区分表を一意に解決できない: {len(candidates)} 件")
    return candidates[0]


def _design_event_kind_contracts(
    document: str,
) -> tuple[tuple[int, str, str, str | None], ...]:
    """詳細設計 3-6 節から番号・種別名・対応・リテラルを抽出する。"""
    body = _section_body(document, "3-6")
    for headers, rows in _markdown_tables(body):
        plain_headers = [_plain_markdown_cell(header) for header in headers]
        if plain_headers[:4] != [
            "#",
            "正本 5-3 節の参加区分",
            "対応",
            "V5 リテラル",
        ]:
            continue
        contracts: list[tuple[int, str, str, str | None]] = []
        for row in rows:
            number = _plain_markdown_cell(row[0])
            match = re.fullmatch(r"#(?P<number>\d+)", number)
            if match is None:
                raise ValueError(f"詳細設計の参加区分番号を解決できない: {number}")
            literal = _plain_markdown_cell(row[3])
            contracts.append(
                (
                    int(match.group("number")),
                    _plain_markdown_cell(row[1]),
                    _plain_markdown_cell(row[2]),
                    None if literal == "—" else literal,
                )
            )
        return tuple(contracts)
    raise ValueError("詳細設計 3-6 節の操作イベント種別対応表がない")


def test_event_kind_mapping_exactly_covers_canonical_participation_kinds() -> None:
    """対応表が正本の全参加区分だけを文書順に覆うと示す。"""
    canonical = _canonical_participation_kinds(
        _DATA_MODEL_PATH.read_text(encoding="utf-8")
    )
    code_contract = tuple(
        (participation.participation_number, participation.canonical_name)
        for participation in OPERATION_EVENT_PARTICIPATIONS
    )

    assert code_contract == canonical
    assert len(EVENT_KIND_LITERALS) == len(set(EVENT_KIND_LITERALS))
    assert len(EVENT_KIND_LITERALS) == 9
    assert CONDITIONAL_EVENT_KIND_LITERALS == (STATE_CORRECTION_EVENT_KIND,)
    assert {"state_correction", "tombstone", "revision"}.isdisjoint(EVENT_KIND_LITERALS)
    assert all(
        participation.event_kind_literal is None
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.binding
        in {ParticipationBinding.TOMBSTONE_STATE, ParticipationBinding.REVISION_STATE}
    )


def test_manifest_event_kind_check_literals_match_the_mapping() -> None:
    """列挙 CHECK のリテラル集合がコード側の対応表と一致すると示す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    operation_events = next(
        table for table in manifest["tables"] if table["name"] == "operation_events"
    )
    enum_checks = [
        check
        for check in operation_events["checks"]
        if re.fullmatch(r"event_kind IN \((?:'[^']+'(?:, )?)+\)", check)
    ]

    assert len(enum_checks) == 1
    assert tuple(re.findall(r"'([^']+)'", enum_checks[0])) == EVENT_KIND_LITERALS


def test_design_event_kind_table_matches_the_code_contract() -> None:
    """跨ぐ契約として記録した詳細設計の対応表がコードと一致すると示す。"""
    design_contract = _design_event_kind_contracts(
        _DESIGN_PATH.read_text(encoding="utf-8")
    )
    code_contract = tuple(
        (
            participation.participation_number,
            participation.canonical_name,
            participation.binding.value,
            participation.event_kind_literal,
        )
        for participation in OPERATION_EVENT_PARTICIPATIONS
    )

    assert design_contract == code_contract
