"""表外既定の表示項目・製品呼出箇所・生成 formatter を突合する。

対象項目は要件書 `付録A-1 表示書式の共通規定` に従い、既存の
``collect_display_paths`` が ``model.schema.json`` の
``x-pitchlog.targetFieldSelectors`` から導出した閉包だけを使う。
項目名のリストをこのモジュールへ再入力しない。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    EXIT_NONCONFORMING,
    CheckerExecutionError,
    canonical_json,
    exact_set_difference,
    read_json,
)
from pitchlog.domaincheck.collect_display_paths import collect_display_paths


class DisplayBindingStatus(StrEnum):
    """表示対応の三値判定。"""

    CONFORMING = "conforming"
    NONCONFORMING = "nonconforming"
    INDETERMINATE = "indeterminate"


class DisplayBindingIndeterminate(Exception):
    """表示対応を静的に判定できないことを表す。"""


@dataclass(frozen=True, order=True, slots=True)
class DisplayBinding:
    """一つの表示項目と呼出箇所と formatter の対応。"""

    display_item: str
    callsite: str
    formatter: str

    @property
    def call_key(self) -> str:
        """収集結果との照合に使う呼出箇所キーを返す。"""
        return f"{self.callsite}#{self.formatter}"


@dataclass(frozen=True, slots=True)
class DisplayBindingReport:
    """表示対応の閉包・集合差・経由違反を保持する。"""

    status: DisplayBindingStatus
    attempts: int
    target_fields: frozenset[str]
    bindings: tuple[DisplayBinding, ...]
    missing_bindings: frozenset[str]
    unexpected_bindings: frozenset[str]
    missing_calls: frozenset[str]
    unregistered_calls: frozenset[str]
    non_formatter_calls: tuple[str, ...]
    invalid_formatters: tuple[str, ...]
    reasons: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """全差分が空で適合する場合だけ真を返す。"""
        return self.status is DisplayBindingStatus.CONFORMING

    def as_json(self) -> dict[str, object]:
        """CLI 出力用の JSON object を返す。"""
        return {
            "schemaVersion": 1,
            "status": self.status.value,
            "attempts": self.attempts,
            "targetFields": sorted(self.target_fields),
            "bindingCount": len(self.bindings),
            "missingBindings": sorted(self.missing_bindings),
            "unexpectedBindings": sorted(self.unexpected_bindings),
            "missingCalls": sorted(self.missing_calls),
            "unregisteredCalls": sorted(self.unregistered_calls),
            "nonFormatterCalls": list(self.non_formatter_calls),
            "invalidFormatters": list(self.invalid_formatters),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class FailClosedMeasurement:
    """三つの閉域検査に与えた解析不能例の実測 exit code。"""

    frontend: int
    backend: int
    display: int

    @property
    def complete(self) -> bool:
        """全経路が解析不能を exit 2 とした場合だけ真を返す。"""
        return (self.frontend, self.backend, self.display) == (
            EXIT_INDETERMINATE,
            EXIT_INDETERMINATE,
            EXIT_INDETERMINATE,
        )


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを例外として送出する。"""
        raise CheckerExecutionError(message)


def _object(value: object, label: str) -> Mapping[str, object]:
    """文字列キーの JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DisplayBindingIndeterminate(f"{label} が object でない")
    return value


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise DisplayBindingIndeterminate(f"{label} が array でない")
    return value


def _text(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise DisplayBindingIndeterminate(f"{label} が空でない文字列でない")
    return value


def _boolean(value: object, label: str) -> bool:
    """Boolean 値を返す。"""
    if not isinstance(value, bool):
        raise DisplayBindingIndeterminate(f"{label} が boolean でない")
    return value


def _string_array(value: object, label: str) -> list[str]:
    """重複しない非空文字列配列を返す。"""
    items = _array(value, label)
    if not items or not all(isinstance(item, str) and item for item in items):
        raise DisplayBindingIndeterminate(
            f"{label} が非空文字列からなる空でない配列でない"
        )
    strings = [str(item) for item in items]
    if len(strings) != len(set(strings)):
        raise DisplayBindingIndeterminate(f"{label} に重複がある")
    return strings


def _policy(policy: object) -> dict[str, object]:
    """表示対応資産の閉じた規則を読み取る。"""
    root = _object(policy, "display-binding policy")
    expected_root = {
        "schemaVersion",
        "authority",
        "sources",
        "targetDerivation",
        "bindingContract",
        "sealedMissingDeclaration",
    }
    if set(root) != expected_root or root.get("schemaVersion") != 1:
        raise DisplayBindingIndeterminate("表示対応資産のキー集合または版が不正")
    _text(root.get("authority"), "policy.authority")
    sources = _object(root.get("sources"), "policy.sources")
    if set(sources) != {
        "collector",
        "modelSchema",
        "vocabularySchema",
        "manifestSchema",
        "sealedSet",
    }:
        raise DisplayBindingIndeterminate("policy.sources のキー集合が不正")
    for key, value in sources.items():
        _text(value, f"policy.sources.{key}")

    derivation = _object(
        root.get("targetDerivation"),
        "policy.targetDerivation",
    )
    if set(derivation) != {
        "schemaSelector",
        "collectorResult",
        "requireComplete",
        "requireNonempty",
    }:
        raise DisplayBindingIndeterminate("policy.targetDerivation のキー集合が不正")
    _text(derivation.get("schemaSelector"), "targetDerivation.schemaSelector")
    _text(derivation.get("collectorResult"), "targetDerivation.collectorResult")
    _boolean(derivation.get("requireComplete"), "targetDerivation.requireComplete")
    _boolean(derivation.get("requireNonempty"), "targetDerivation.requireNonempty")

    contract = _object(root.get("bindingContract"), "policy.bindingContract")
    expected_contract = {
        "manifestField",
        "exactFields",
        "identityFields",
        "callsiteFields",
        "requiredCallKind",
        "generatedFormatterPathPrefix",
    }
    if set(contract) != expected_contract:
        raise DisplayBindingIndeterminate("policy.bindingContract のキー集合が不正")
    for key in (
        "manifestField",
        "requiredCallKind",
        "generatedFormatterPathPrefix",
    ):
        _text(contract.get(key), f"bindingContract.{key}")
    for key in ("exactFields", "identityFields", "callsiteFields"):
        _string_array(contract.get(key), f"bindingContract.{key}")
    return dict(root)


def _attempts(collection: Mapping[str, object]) -> int:
    """走査回数が内訳と一致する正の整数であることを確かめる。"""
    attempts = collection.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts <= 0:
        raise DisplayBindingIndeterminate("収集器の走査回数が正の整数でない")
    by_kind = _object(collection.get("attemptsByKind"), "attemptsByKind")
    measured = 0
    for value in by_kind.values():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise DisplayBindingIndeterminate("走査種別の件数が非負整数でない")
        measured += value
    if measured != attempts:
        raise DisplayBindingIndeterminate("走査回数と内訳が一致しない")
    return attempts


def _target_fields(
    collection: Mapping[str, object],
    policy: Mapping[str, object],
) -> frozenset[str]:
    """既存収集器が schema 閉包から導出した対象集合を返す。"""
    unresolved = _array(collection.get("unresolved"), "collection.unresolved")
    if unresolved:
        raise DisplayBindingIndeterminate(
            f"静的に解決できない表示経路が {len(unresolved)} 件ある"
        )
    closure = _object(collection.get("schemaClosure"), "schemaClosure")
    derivation = _object(policy.get("targetDerivation"), "targetDerivation")
    closure_derivation = _object(
        closure.get("derivation"),
        "schemaClosure.derivation",
    )
    schema_selector = _text(
        derivation.get("schemaSelector"),
        "targetDerivation.schemaSelector",
    )
    if closure_derivation.get("modelRoot") != schema_selector:
        raise DisplayBindingIndeterminate(
            "schema 閉包の selector が表示対応資産と一致しない"
        )
    if _boolean(derivation.get("requireComplete"), "requireComplete"):
        if closure.get("complete") is not True:
            raise DisplayBindingIndeterminate("schema 閉包の導出が完了していない")
    result_path = _text(
        derivation.get("collectorResult"),
        "targetDerivation.collectorResult",
    )
    node: object = collection
    for token in result_path.split("."):
        node = _object(node, f"collectorResult.{token}").get(token)
    fields = _string_array(node, result_path)
    if not fields and _boolean(
        derivation.get("requireNonempty"),
        "requireNonempty",
    ):
        raise DisplayBindingIndeterminate("schema 閉包の対象集合が空")
    return frozenset(fields)


def _bindings(
    manifest: object,
    contract: Mapping[str, object],
) -> tuple[DisplayBinding, ...]:
    """マニフェストの表示対応を exact-set の行として読む。"""
    root = _object(manifest, "manifest")
    field = _text(contract.get("manifestField"), "bindingContract.manifestField")
    rows = _array(root.get(field), f"manifest.{field}")
    exact_fields = set(
        _string_array(contract.get("exactFields"), "bindingContract.exactFields")
    )
    bindings: list[DisplayBinding] = []
    for index, raw_row in enumerate(rows):
        label = f"manifest.{field}[{index}]"
        row = _object(raw_row, label)
        if set(row) != exact_fields:
            raise DisplayBindingIndeterminate(f"{label} のキー集合が不正")
        bindings.append(
            DisplayBinding(
                _text(row.get("displayItem"), f"{label}.displayItem"),
                _text(row.get("callsite"), f"{label}.callsite"),
                _text(row.get("formatter"), f"{label}.formatter"),
            )
        )
        _text(row.get("provenance"), f"{label}.provenance")
    items = [binding.display_item for binding in bindings]
    if len(items) != len(set(items)):
        raise DisplayBindingIndeterminate("displayBindings[].displayItem が重複")
    call_keys = [binding.call_key for binding in bindings]
    if len(call_keys) != len(set(call_keys)):
        raise DisplayBindingIndeterminate("表示呼出箇所の宣言が重複")
    return tuple(bindings)


def _seal_element(
    sealed_set: object,
    policy: Mapping[str, object],
) -> None:
    """表示対応の宣言不在が固定封印集合に既存であることを検査する。"""
    sealed = _object(sealed_set, "boot seal")
    elements = _array(sealed.get("elements"), "boot seal.elements")
    expected = _object(
        policy.get("sealedMissingDeclaration"),
        "policy.sealedMissingDeclaration",
    )
    expected_keys = {"elementId", "constructor", "canonicalKey", "arguments"}
    if set(expected) != expected_keys:
        raise DisplayBindingIndeterminate("sealedMissingDeclaration のキー集合が不正")
    element_id = _text(expected.get("elementId"), "sealed elementId")
    matches = [
        _object(element, "boot seal element")
        for element in elements
        if isinstance(element, dict) and element.get("id") == element_id
    ]
    if len(matches) != 1:
        raise DisplayBindingIndeterminate("表示対応の封印要素が一意に実在しない")
    match = matches[0]
    for asset_key, seal_key in (
        ("constructor", "constructor"),
        ("canonicalKey", "canonicalKey"),
        ("arguments", "arguments"),
    ):
        if expected.get(asset_key) != match.get(seal_key):
            raise DisplayBindingIndeterminate("表示対応の封印要素が資産と一致しない")


def _observed_calls(
    collection: Mapping[str, object],
    contract: Mapping[str, object],
) -> tuple[frozenset[str], tuple[str, ...], tuple[str, ...]]:
    """有効な formatter 呼出しと経由違反を実測結果から分離する。"""
    required_kind = _text(
        contract.get("requiredCallKind"),
        "bindingContract.requiredCallKind",
    )
    generated_prefix = _text(
        contract.get("generatedFormatterPathPrefix"),
        "bindingContract.generatedFormatterPathPrefix",
    )
    definitions: set[tuple[str, str]] = set()
    for index, raw_definition in enumerate(
        _array(collection.get("formatterDefinitions"), "formatterDefinitions")
    ):
        label = f"formatterDefinitions[{index}]"
        definition = _object(raw_definition, label)
        definitions.add(
            (
                _text(definition.get("path"), f"{label}.path"),
                _text(definition.get("symbol"), f"{label}.symbol"),
            )
        )

    valid: set[str] = set()
    non_formatter: list[str] = []
    invalid_formatters: list[str] = []
    for index, raw_call in enumerate(
        _array(collection.get("displayCalls"), "displayCalls")
    ):
        label = f"displayCalls[{index}]"
        call = _object(raw_call, label)
        path = _text(call.get("path"), f"{label}.path")
        kind = _text(call.get("kind"), f"{label}.kind")
        occurrence = call.get("occurrence")
        if (
            isinstance(occurrence, bool)
            or not isinstance(occurrence, int)
            or occurrence < 1
        ):
            raise DisplayBindingIndeterminate(f"{label}.occurrence が正の整数でない")
        if kind != required_kind:
            if not path.startswith(generated_prefix):
                non_formatter.append(f"{path}#{kind}#{occurrence}")
            continue
        symbol = _text(call.get("symbol"), f"{label}.symbol")
        formatter_path = _text(call.get("formatter"), f"{label}.formatter")
        call_key = f"{path}#{symbol}"
        if not formatter_path.startswith(generated_prefix):
            invalid_formatters.append(f"{call_key}|not-generated:{formatter_path}")
            continue
        if (formatter_path, symbol) not in definitions:
            invalid_formatters.append(f"{call_key}|missing-definition:{formatter_path}")
            continue
        if call_key in valid:
            raise DisplayBindingIndeterminate(
                f"表示呼出箇所が occurrence を除いて重複している: {call_key}"
            )
        valid.add(call_key)
    return (
        frozenset(valid),
        tuple(sorted(non_formatter)),
        tuple(sorted(invalid_formatters)),
    )


def inspect_display_bindings(
    collection: object,
    manifest: object,
    policy: object,
    sealed_set: object,
) -> DisplayBindingReport:
    """Schema 閉包・宣言・静的実測の三集合を突合する。

    Args:
        collection: ステップ 12 の表示経路収集結果。
        manifest: ``displayBindings[]`` を持つマニフェスト。
        policy: ``display-binding.json`` の規則。
        sealed_set: ステップ 15 の固定封印集合。

    Returns:
        双方向の集合差と formatter 経由違反を持つ検査結果。

    Raises:
        DisplayBindingIndeterminate: 入力を静的に判定できない場合。
    """
    collected = _object(collection, "collection")
    checked_policy = _policy(policy)
    attempts = _attempts(collected)
    target_fields = _target_fields(collected, checked_policy)
    contract = _object(
        checked_policy.get("bindingContract"),
        "bindingContract",
    )
    bindings = _bindings(manifest, contract)
    _seal_element(sealed_set, checked_policy)
    observed_calls, non_formatter, invalid_formatters = _observed_calls(
        collected,
        contract,
    )

    item_difference = exact_set_difference(
        set(target_fields),
        {binding.display_item for binding in bindings},
    )
    call_difference = exact_set_difference(
        {binding.call_key for binding in bindings},
        set(observed_calls),
    )
    status = (
        DisplayBindingStatus.CONFORMING
        if item_difference.matches
        and call_difference.matches
        and not non_formatter
        and not invalid_formatters
        else DisplayBindingStatus.NONCONFORMING
    )
    return DisplayBindingReport(
        status=status,
        attempts=attempts,
        target_fields=target_fields,
        bindings=bindings,
        missing_bindings=item_difference.missing,
        unexpected_bindings=item_difference.unexpected,
        missing_calls=call_difference.missing,
        unregistered_calls=call_difference.unexpected,
        non_formatter_calls=non_formatter,
        invalid_formatters=invalid_formatters,
    )


def _build_parser() -> argparse.ArgumentParser:
    """表示対応 CLI の引数を定義する。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("backend/domain/display-binding.json"),
    )
    parser.add_argument("--frontend", type=Path, default=Path("frontend/src"))
    parser.add_argument(
        "--model-schema",
        type=Path,
        default=Path("backend/domain/model.schema.json"),
    )
    parser.add_argument(
        "--vocabulary-schema",
        type=Path,
        default=Path("backend/domain/vocabulary.schema.json"),
    )
    parser.add_argument(
        "--sealed-set",
        type=Path,
        default=Path("backend/domain/boot-seal.json"),
    )
    return parser


def _resolved(root: Path, path: Path) -> Path:
    """相対パスをリポジトリルート基準で解決する。"""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _indeterminate(reason: str, attempts: int) -> dict[str, object]:
    """判定不能時にも走査回数を残す JSON object を返す。"""
    return {
        "schemaVersion": 1,
        "status": DisplayBindingStatus.INDETERMINATE.value,
        "attempts": attempts,
        "targetFields": [],
        "bindingCount": 0,
        "missingBindings": [],
        "unexpectedBindings": [],
        "missingCalls": [],
        "unregisteredCalls": [],
        "nonFormatterCalls": [],
        "invalidFormatters": [],
        "reasons": [reason],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """表示対応を突合し、適合・不適合・判定不能を分離する。

    Args:
        argv: CLI 引数。``None`` ならプロセス引数を使う。

    Returns:
        適合は 0、不適合は 1、判定不能は 2。
    """
    attempts = 0
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        collection = collect_display_paths(
            root,
            _resolved(root, arguments.frontend),
            _resolved(root, arguments.model_schema),
            _resolved(root, arguments.vocabulary_schema),
        )
        raw_attempts = collection.get("attempts")
        if isinstance(raw_attempts, int) and not isinstance(raw_attempts, bool):
            attempts = raw_attempts
        report = inspect_display_bindings(
            collection,
            read_json(_resolved(root, arguments.manifest)),
            read_json(_resolved(root, arguments.policy)),
            read_json(_resolved(root, arguments.sealed_set)),
        )
        print(canonical_json(report.as_json()), end="")
        if report.status is DisplayBindingStatus.NONCONFORMING:
            print(
                "不適合: 表示対応に集合差または formatter 経由違反がある",
                file=sys.stderr,
            )
            return EXIT_NONCONFORMING
        return EXIT_CONFORMING
    except (
        CheckerExecutionError,
        DisplayBindingIndeterminate,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(canonical_json(_indeterminate(str(error), attempts)), end="")
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE


if __name__ == "__main__":
    raise SystemExit(main())
