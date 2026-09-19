"""BOOT-SEAL の導出集合を既存の封印機構へ接続する。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path

from pitchlog.domaincheck import seal
from pitchlog.domaincheck.boot_seal_derive import derive_boot_seal
from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    EXIT_NONCONFORMING,
    CheckerExecutionError,
    CheckerViolation,
    exact_set_difference,
    read_json,
)

BOOT_SEAL_BASE_COMMIT = "50501ebeea70cee77a9ff4ca8e6c0951015d517a"
BOOT_SEAL_ASSET = Path("backend/domain/boot-seal.json")
BOOT_SEAL_RECORD = Path("backend/domain/boot-seal.sealed.json")


def _canonical_keys(value: object, label: str) -> tuple[str, ...]:
    """封印集合から一意な正規キー列を取り出す。

    Args:
        value: 導出済みまたは封印対象の集合資産。
        label: エラーで入力を識別する名前。

    Returns:
        資産に記録された順序の正規キー列。

    Raises:
        CheckerExecutionError: 資産の形を解釈できない場合。
        CheckerViolation: 同じ事項が複数要素へ分割されている場合。
    """
    if not isinstance(value, Mapping):
        raise CheckerExecutionError(f"{label}が JSON object でない")
    elements = value.get("elements")
    if not isinstance(elements, list):
        raise CheckerExecutionError(f"{label}.elements が array でない")
    keys: list[str] = []
    for index, element in enumerate(elements):
        if not isinstance(element, Mapping):
            raise CheckerExecutionError(
                f"{label}.elements[{index}] が object でない"
            )
        key = element.get("canonicalKey")
        if not isinstance(key, str) or not key:
            raise CheckerExecutionError(
                f"{label}.elements[{index}].canonicalKey が空でない文字列でない"
            )
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise CheckerViolation(
            "NFR-018 (e) BOOT-SEAL 拘束④: 同一事項が複数要素に対応する"
        )
    return tuple(keys)


def assert_sealed_set_matches(derived: object, sealed_asset: object) -> None:
    """実測集合と封印対象集合の双方向差が空であることを要求する。

    Args:
        derived: 正本と schema から再導出した集合。
        sealed_asset: 固定 digest の対象となる集合資産。

    Raises:
        CheckerExecutionError: いずれかの集合を解釈できない場合。
        CheckerViolation: 欠落、追加、または重複がある場合。
    """
    derived_keys = frozenset(_canonical_keys(derived, "実測集合"))
    sealed_keys = frozenset(_canonical_keys(sealed_asset, "封印対象集合"))
    difference = exact_set_difference(derived_keys, sealed_keys)
    if not difference.matches:
        raise CheckerViolation(
            "NFR-018 (e) BOOT-SEAL: 集合差がある: "
            f"不足={sorted(difference.missing)!r}, "
            f"未登録={sorted(difference.unexpected)!r}"
        )


def verify_boot_seal(root: Path) -> int:
    """導出集合を照合してから既存の固定 SHA 封印を検証する。

    Args:
        root: 検証対象のリポジトリルート。

    Returns:
        適合は 0、不適合は 1、判定不能は 2。

    Raises:
        CheckerExecutionError: リポジトリまたは資産を読めない場合。
        CheckerViolation: 導出集合と封印対象集合が一致しない場合。
    """
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise CheckerExecutionError(
            f"リポジトリルートを読めない: {resolved_root}"
        )
    derived = derive_boot_seal(resolved_root)
    sealed_asset = read_json(resolved_root / BOOT_SEAL_ASSET)
    assert_sealed_set_matches(derived, sealed_asset)
    return seal.main(
        [
            "--root",
            str(resolved_root),
            "--asset",
            BOOT_SEAL_ASSET.as_posix(),
            "--seal",
            BOOT_SEAL_RECORD.as_posix(),
            "--base-commit",
            BOOT_SEAL_BASE_COMMIT,
            "--verify",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    """BOOT-SEAL 検証 CLI の引数パーサを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[4])
    return parser


def main(argv: list[str] | None = None) -> int:
    """封印集合を再導出し、既存機構による封印検証まで実行する。"""
    try:
        arguments = _parser().parse_args(argv)
        return verify_boot_seal(arguments.root)
    except CheckerViolation as error:
        print(f"不適合: {error}", file=sys.stderr)
        return EXIT_NONCONFORMING
    except CheckerExecutionError as error:
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE
    return EXIT_CONFORMING


if __name__ == "__main__":
    raise SystemExit(main())
