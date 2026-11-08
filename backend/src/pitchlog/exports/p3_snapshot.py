"""P3 CSVの保存済み完成値を同版の有限S頁へ結ぶ。計算・資格発行はしない。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, cast
from uuid import UUID

from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.play_export_source_codec import SourceIdentity, SourceVersion

_COLUMNS = frozenset(CSV_HEADERS["plays.csv"])
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_IDENTITY_FIELDS = (
    "tenant_id",
    "game_id",
    "internal_generation",
    "capsule_id",
    "d1",
    "original_play_row_id",
    "effective_event_id",
    "effective_play_row_id",
    "play_row_version",
    "item_digest",
    "capsule_source_set_digest",
    "capsule_stats_version_id",
)
_ROW_FIELDS = frozenset(
    (
        *_IDENTITY_FIELDS,
        "plays_csv_json",
        "full_innings_json",
        "runner_rows_json",
        "reference_json",
        "captured_at",
    )
)


def _need(condition: bool) -> None:
    """不正値を別版や空欄へ補修しない。"""
    if not condition:
        raise PlayExportSupplyError("P3毎球CSVの原本又は完成版が未供給です")


def _positive(value: object) -> bool:
    """boolを整数へ補修しない。"""
    return type(value) is int and 0 < value < 2**63


@dataclass(frozen=True, slots=True)
class P3SnapshotIdentity:
    """同RRの真正Sとcapsule/itemから読む値。単独では読書資格にならない。"""

    tenant_id: UUID
    game_id: UUID
    internal_generation: int
    capsule_id: UUID
    d1: int
    original_play_row_id: UUID
    effective_event_id: UUID
    effective_play_row_id: UUID
    play_row_version: int
    item_digest: str
    capsule_source_set_digest: str
    capsule_stats_version_id: UUID

    def __post_init__(self) -> None:
        """未知型/非正準値を受けない。"""
        for field in (
            "tenant_id",
            "game_id",
            "capsule_id",
            "original_play_row_id",
            "effective_event_id",
            "effective_play_row_id",
            "capsule_stats_version_id",
        ):
            _need(type(getattr(self, field)) is UUID)
        for field in ("internal_generation", "d1", "play_row_version"):
            _need(_positive(getattr(self, field)))
        for field in ("item_digest", "capsule_source_set_digest"):
            value = getattr(self, field)
            _need(type(value) is str and _SHA.fullmatch(value) is not None)


@dataclass(frozen=True, slots=True)
class P3CompletedSnapshot:
    """閉検査済み表示原本。JSON自体を認可や計算成功として扱わない。"""

    identity: P3SnapshotIdentity
    values: Mapping[str, str | None]
    full_innings_json: tuple[object, ...]
    runner_rows_json: tuple[object, ...]


def require_p3_snapshot(
    row: object,
    expected: P3SnapshotIdentity,
    source: SourceIdentity,
) -> P3CompletedSnapshot:
    """選択済み現在capsule・item・Sの全identityを一対一で照合する。"""
    _need(type(expected) is P3SnapshotIdentity and type(source) is SourceIdentity)
    expected.__post_init__()
    for field in (
        "recording_generation",
        "d1",
        "slot_version",
        "play_row_version",
    ):
        _need(_positive(getattr(source, field)))
    _need(type(source.d2) is int and -(2**63) <= source.d2 < 2**63)
    for field in ("source_event_id", "play_row_id", "base_event_id"):
        _need(type(getattr(source, field)) is UUID)
    _need(
        type(source.source_fingerprint) is str
        and re.fullmatch(r"(?:wire-v1:)?[a-f0-9]{64}", source.source_fingerprint)
        is not None
    )
    _need(type(row) is dict and set(row) == _ROW_FIELDS)
    row = cast(dict[str, Any], row)
    for field in _IDENTITY_FIELDS:
        actual, wanted = row[field], getattr(expected, field)
        _need(type(actual) is type(wanted) and actual == wanted)
    _need(
        (
            source.recording_generation,
            source.d1,
            source.source_event_id,
            source.play_row_id,
            source.play_row_version,
        )
        == (
            expected.internal_generation,
            expected.d1,
            expected.effective_event_id,
            expected.effective_play_row_id,
            expected.play_row_version,
        )
    )
    _need(
        type(row["captured_at"]) is datetime
        and row["captured_at"].utcoffset() is not None
    )
    _need(row["reference_json"] is None or type(row["reference_json"]) is dict)
    values = row["plays_csv_json"]
    _need(type(values) is dict and set(values) == _COLUMNS)
    values = cast(dict[str, str | None], values)
    _need(all(type(value) is str or value is None for value in values.values()))
    innings, runners = row["full_innings_json"], row["runner_rows_json"]
    _need(type(innings) is list and type(runners) is list and len(runners) <= 3)
    return P3CompletedSnapshot(
        expected,
        MappingProxyType(dict(values)),
        tuple(cast(list[object], innings)),
        tuple(cast(list[object], runners)),
    )


def require_p3_snapshot_page(
    rows: object,
    sources: tuple[SourceIdentity, ...],
    identities: tuple[P3SnapshotIdentity, ...],
    *,
    version: SourceVersion,
    expected_version: SourceVersion,
) -> tuple[P3CompletedSnapshot, ...]:
    """500以下の一頁だけを同RR版へ結び、欠測/余剰/旧版/重複を拒否する。"""
    _need(type(version) is SourceVersion and type(expected_version) is SourceVersion)
    for value in (version, expected_version):
        _need(type(value.fact_version_id) is UUID and _positive(value.revision))
        _need(type(value.source_count) is int and 0 <= value.source_count < 2**63)
        _need(
            type(value.source_set_sha256) is str
            and _SHA.fullmatch(value.source_set_sha256) is not None
        )
        _need(value.completion_state in {"current_open", "confirmed_ended"})
        _need(
            type(value.transaction_id) is str
            and re.fullmatch(
                r"[0-9]+:[0-9]+:(?:[0-9]+(?:,[0-9]+)*)?", value.transaction_id
            )
            is not None
        )
    _need(version == expected_version)
    _need(type(rows) is tuple and type(sources) is tuple and type(identities) is tuple)
    rows = cast(tuple[object, ...], rows)
    _need(len(rows) == len(sources) == len(identities) <= 500)
    _need(all(type(item) is SourceIdentity for item in sources))
    _need(all(type(item) is P3SnapshotIdentity for item in identities))
    _need(
        len({(item.recording_generation, item.d1) for item in sources}) == len(sources)
    )
    _need(len({item.play_row_id for item in sources}) == len(sources))
    _need(
        len({(item.internal_generation, item.d1) for item in identities})
        == len(identities)
    )
    result = tuple(
        require_p3_snapshot(row, identity, source)
        for row, identity, source in zip(rows, identities, sources, strict=True)
    )
    _need(
        all(
            (a.identity.internal_generation, a.identity.d1)
            < (b.identity.internal_generation, b.identity.d1)
            for a, b in zip(result, result[1:])
        )
    )
    return result
