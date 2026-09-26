"""凍結履歴から content-addressed snapshot の参照を構造的に抽出する。"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

# このファイルもパス指定でロードされるため、同階層 import を解決する。
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import frozen_history  # noqa: E402

ContractError = frozen_history.ContractError


class AspectReferenceKind(StrEnum):
    """v2 state の各 aspect が持つ snapshot 参照の分類を表す。"""

    NONE = "none"
    SNAPSHOT_ARRAY = "snapshot_array"


# ASPECT_NAMES から導出しない。schema 上の型と参照経路を明示する決定表である。
ASPECT_REFERENCE_KINDS: Mapping[str, AspectReferenceKind] = MappingProxyType(
    {
        "declaration": AspectReferenceKind.NONE,
        "movement_policy": AspectReferenceKind.NONE,
        "external_snapshots": AspectReferenceKind.SNAPSHOT_ARRAY,
        "asset_snapshots": AspectReferenceKind.SNAPSHOT_ARRAY,
    }
)

# 上の決定表の誤分類を、キー集合だけでなく値まで拘束する期待表である。
EXPECTED_ASPECT_REFERENCE_KINDS: Mapping[str, AspectReferenceKind] = (
    MappingProxyType(
        {
            "declaration": AspectReferenceKind.NONE,
            "movement_policy": AspectReferenceKind.NONE,
            "external_snapshots": AspectReferenceKind.SNAPSHOT_ARRAY,
            "asset_snapshots": AspectReferenceKind.SNAPSHOT_ARRAY,
        }
    )
)

SnapshotReferenceExtractor = Callable[
    [object, Mapping[str, bytes], str],
    frozenset[str],
]
RecordReferenceExtractor = Callable[
    [Mapping[str, Any], Mapping[str, bytes], str],
    frozenset[str],
]

# retired_history_ref など ASPECT_NAMES 外の record 直下参照は、将来ここへ
# 専用 extractor を登録する。本ステップでは対象 field を実装しない。
RECORD_REFERENCE_EXTRACTORS: Mapping[str, RecordReferenceExtractor] = (
    MappingProxyType({})
)


def _snapshot_array_references(
    value: object,
    snapshots: Mapping[str, bytes],
    location: str,
) -> frozenset[str]:
    """既存検証器で snapshot 配列を検証し、参照先ファイル名を返す。"""
    items = frozen_history._external_snapshots(value, snapshots, location)
    references: set[str] = set()
    for index, item in enumerate(items):
        item_location = f"{location}[{index}].snapshot_ref"
        snapshot_ref = frozen_history._nonempty_string(
            item.get("snapshot_ref"),
            item_location,
        )
        references.add(
            snapshot_ref.removeprefix(frozen_history.SNAPSHOT_REF_PREFIX)
        )
    return frozenset(references)


_REFERENCE_EXTRACTORS: Mapping[
    AspectReferenceKind,
    SnapshotReferenceExtractor | None,
] = MappingProxyType(
    {
        AspectReferenceKind.NONE: None,
        AspectReferenceKind.SNAPSHOT_ARRAY: _snapshot_array_references,
    }
)


def _validate_extraction_tables() -> None:
    """aspect 抽出表の網羅性と分類値を frozen_history の契約へ照合する。"""
    actual_keys = frozenset(ASPECT_REFERENCE_KINDS)
    if actual_keys != frozen_history.ASPECT_NAMES:
        raise ContractError(
            "snapshot 参照抽出表と ASPECT_NAMES のキー集合が不一致: "
            f"table={sorted(actual_keys)}, "
            f"aspects={sorted(frozen_history.ASPECT_NAMES)}"
        )
    if dict(ASPECT_REFERENCE_KINDS) != dict(EXPECTED_ASPECT_REFERENCE_KINDS):
        raise ContractError("snapshot 参照抽出表の分類値が期待表と不一致")


def _state_references(
    value: object,
    snapshots: Mapping[str, bytes],
    location: str,
) -> frozenset[str]:
    """検証済み v2 state の明示表にある経路だけから参照を抽出する。"""
    state = frozen_history._snapshot_state(value, snapshots, location)
    references: set[str] = set()
    for aspect, kind in ASPECT_REFERENCE_KINDS.items():
        extractor = _REFERENCE_EXTRACTORS[kind]
        if extractor is None:
            continue
        references.update(
            extractor(
                state[aspect],
                snapshots,
                f"{location}.{aspect}",
            )
        )
    return frozenset(references)


def _record_references(
    record: Mapping[str, Any],
    snapshots: Mapping[str, bytes],
    location: str,
) -> frozenset[str]:
    """ASPECT_NAMES 外の record 直下参照を専用表から抽出する。"""
    references: set[str] = set()
    for field, extractor in RECORD_REFERENCE_EXTRACTORS.items():
        references.update(
            extractor(
                record,
                snapshots,
                f"{location}.{field}",
            )
        )
    return frozenset(references)


def extract_referenced_snapshot_names(
    history: object,
    snapshot_root: Path,
    *,
    location: str = "baseline_control.history",
) -> frozenset[str]:
    """v2 履歴から検証済み snapshot ファイル名の一意集合を返す。

    v1 記録は snapshot 参照を持たない契約なので走査しない。v2 記録は
    ``change.before`` と ``change.after`` の明示表にある参照経路だけを走査する。
    参照の prefix・SHA-256・実ファイルとの一致は ``frozen_history`` の既存
    検証関数を共用する。

    Args:
        history: authority の ``baseline_control.history``。
        snapshot_root: ``history-snapshots`` ディレクトリ。
        location: エラー表示用の履歴位置。

    Returns:
        参照された snapshot の64桁小文字hexファイル名の一意集合。

    Raises:
        ContractError: 抽出表、v2 state、参照値、または実ファイルが不正な場合。
    """
    _validate_extraction_tables()
    snapshots = frozen_history._read_snapshot_directory(
        snapshot_root,
        f"{location}.snapshots",
    )
    references: set[str] = set()
    for index, raw_record in enumerate(
        frozen_history._history_array(history, location)
    ):
        record_location = f"{location}[{index}]"
        record = frozen_history._record_object(raw_record, record_location)
        if record.get("record_schema_version") != 2:
            continue
        change = frozen_history._mapping(
            record.get("change"),
            f"{record_location}.change",
        )
        for side in ("before", "after"):
            references.update(
                _state_references(
                    change.get(side),
                    snapshots,
                    f"{record_location}.change.{side}",
                )
            )
        references.update(
            _record_references(record, snapshots, record_location)
        )
    return frozenset(references)
