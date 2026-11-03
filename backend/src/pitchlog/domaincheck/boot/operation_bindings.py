"""既承認の座標operationだけをBOOT正本対象へ部分供給として対応付ける。"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from pitchlog.domaincheck.cli import CheckerViolation, read_json, validate_asset

BINDINGS_PATH = Path("backend/domain/boot-operation-bindings.json")
BINDINGS_SCHEMA_PATH = Path("backend/domain/boot-operation-bindings.schema.json")
_OPERATION = "course-input-quantization"
_TARGET = "nfr018-alpha-02"
_SOURCE = "frontend/src/domain/courseQuantization.ts"


@dataclass(frozen=True, slots=True)
class PartialOperationBinding:
    """全対象完成を主張しない固定operation対応。"""

    operation: str
    target_id: str
    source: str


def parse_bindings(
    value: object, schema: object, allowed_target_ids: Collection[str]
) -> tuple[PartialOperationBinding, ...]:
    """閉schemaと採用済みの有限対応を両方検査する。"""
    validate_asset(value, schema)
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise CheckerViolation("BOOT operation bindingの版が不正")
    rows = value.get("bindings")
    if not isinstance(rows, list) or len(rows) != 1:
        raise CheckerViolation("BOOT operation bindingは採用済み1件に限る")
    row = rows[0]
    if (
        not isinstance(row, dict)
        or row.get("operation") != _OPERATION
        or row.get("targetId") != _TARGET
        or row.get("source") != _SOURCE
        or row.get("coverage") != "partial"
        or _TARGET not in allowed_target_ids
    ):
        raise CheckerViolation("BOOT operation bindingが採用済み部分供給と一致しない")
    return (PartialOperationBinding(_OPERATION, _TARGET, _SOURCE),)


def load_bindings(
    root: Path,
    allowed_target_ids: Collection[str],
    *,
    read_asset: Callable[[Path], object] = read_json,
) -> tuple[PartialOperationBinding, ...]:
    """任意対応を許さず、存在する固定資産を証跡readerで読む。"""
    if not (root / BINDINGS_PATH).exists():
        return ()
    return parse_bindings(
        read_asset(root / BINDINGS_PATH),
        read_asset(root / BINDINGS_SCHEMA_PATH),
        allowed_target_ids,
    )


def validate_partial_bindings(
    bindings: tuple[PartialOperationBinding, ...], allowed_target_ids: Collection[str]
) -> None:
    """呼出側で組み立てた任意の対応も境界で拒否する。"""
    if bindings and (
        bindings != (PartialOperationBinding(_OPERATION, _TARGET, _SOURCE),)
        or _TARGET not in allowed_target_ids
    ):
        raise CheckerViolation("BOOT operation bindingが採用済み部分供給と一致しない")
