"""Backend の宣言入口を独立収集結果と照合し、実行時にも閉じる。

`ADR-003 D-11 ③ 経路一致検査の理由` と design.md §10-2 に従い、
入口の発見は既存の ``collect_entrypoints_be`` だけへ委ねる。静的照合に加え、
``RuntimeEntrypointGate`` は宣言外の callable を呼び出す前に拒否する。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import NoReturn, TypeVar

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    EXIT_NONCONFORMING,
    CheckerExecutionError,
    canonical_json,
    exact_set_difference,
    read_json,
)
from pitchlog.domaincheck.collect_entrypoints_be import collect_backend_entries

_RESULT = TypeVar("_RESULT")


class BackendClosureStatus(StrEnum):
    """Backend 閉域検査の三値状態。"""

    CONFORMING = "conforming"
    NONCONFORMING = "nonconforming"
    INDETERMINATE = "indeterminate"


class BackendClosureIndeterminate(Exception):
    """入力から閉域の適否を決められないことを表す。"""


class UndeclaredEntrypointError(PermissionError):
    """宣言外の入口を実行前に拒否したことを表す。"""


@dataclass(frozen=True, order=True, slots=True)
class EntrypointIdentity:
    """Backend 入口の比較に使うモジュールとシンボルの組。"""

    module: str
    symbol: str

    def __post_init__(self) -> None:
        """空の識別子を拒否する。"""
        if not self.module or not self.symbol:
            raise ValueError("入口の module または symbol が空")

    @property
    def canonical(self) -> str:
        """集合差と出力に用いる正規キーを返す。"""
        return f"{self.module}:{self.symbol}"


@dataclass(frozen=True, slots=True)
class RuntimeEntrypointGate:
    """宣言済み入口だけに callable の実行を許可するゲート。"""

    allowed: frozenset[EntrypointIdentity]

    def invoke(
        self,
        module: str,
        symbol: str,
        operation: Callable[[], _RESULT],
    ) -> _RESULT:
        """宣言を確認してから callable を実行する。

        Args:
            module: 実行対象の Python モジュール。
            symbol: 実行対象のシンボル。
            operation: 許可後にだけ呼び出す処理。

        Returns:
            許可された処理の戻り値。

        Raises:
            UndeclaredEntrypointError: 入口が宣言集合に無い場合。
        """
        identity = EntrypointIdentity(module, symbol)
        if identity not in self.allowed:
            raise UndeclaredEntrypointError(
                f"宣言外の入口を拒否した: {identity.canonical}"
            )
        return operation()


@dataclass(frozen=True, slots=True)
class BackendClosureReport:
    """実測入口と宣言入口の照合結果。"""

    status: BackendClosureStatus
    attempts: int
    declared: frozenset[EntrypointIdentity]
    observed: frozenset[EntrypointIdentity]
    undeclared: frozenset[str]
    missing_actual: frozenset[str]
    forbidden_dynamic_loads: tuple[str, ...]
    import_graph_edges: int
    reasons: tuple[str, ...] = ()

    def as_json(self) -> dict[str, object]:
        """CLI 出力用の JSON object を返す。"""
        return {
            "schemaVersion": 1,
            "status": self.status.value,
            "attempts": self.attempts,
            "declaredCount": len(self.declared),
            "observedCount": len(self.observed),
            "importGraphEdgeCount": self.import_graph_edges,
            "undeclaredEntrypoints": sorted(self.undeclared),
            "missingActualEntrypoints": sorted(self.missing_actual),
            "forbiddenDynamicLoads": list(self.forbidden_dynamic_loads),
            "reasons": list(self.reasons),
        }


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを例外として送出する。"""
        raise CheckerExecutionError(message)


def _object(value: object, label: str) -> Mapping[str, object]:
    """値を文字列キーの object として検査する。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise BackendClosureIndeterminate(f"{label} が object でない")
    return value


def _array(value: object, label: str) -> list[object]:
    """値を配列として検査する。"""
    if not isinstance(value, list):
        raise BackendClosureIndeterminate(f"{label} が配列でない")
    return value


def _text(row: Mapping[str, object], key: str, label: str) -> str:
    """行の必須非空文字列を返す。"""
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise BackendClosureIndeterminate(f"{label}.{key} が非空文字列でない")
    return value


def _source_prefix(source_root: str) -> tuple[str, ...]:
    """収集器の source root を安全な相対パスとして分解する。"""
    path = PurePosixPath(source_root)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != source_root:
        raise BackendClosureIndeterminate("sourceRoot が正規化済み相対パスでない")
    return path.parts


def _manifest_module(value: str, source_prefix: tuple[str, ...]) -> str:
    """マニフェストの path または dotted module をモジュール名へ揃える。"""
    if not value.endswith(".py"):
        return value
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise BackendClosureIndeterminate("entrypoints[].module が安全な相対パスでない")
    parts = path.parts
    if parts[: len(source_prefix)] != source_prefix:
        raise BackendClosureIndeterminate(
            "Python 入口の module path が収集対象 source root の外にある"
        )
    module_parts = list(parts[len(source_prefix) :])
    if not module_parts:
        raise BackendClosureIndeterminate("Python 入口の module path が空")
    module_parts[-1] = module_parts[-1][:-3]
    if module_parts[-1] == "__init__":
        module_parts.pop()
    if not module_parts or not all(part.isidentifier() for part in module_parts):
        raise BackendClosureIndeterminate("Python 入口の module path が不正")
    return ".".join(module_parts)


def _declared_entrypoints(
    manifest: object, source_prefix: tuple[str, ...]
) -> frozenset[EntrypointIdentity]:
    """マニフェスト全対象の入口宣言を正規集合へ変換する。"""
    root = _object(manifest, "manifest")
    calculations = _array(root.get("calculations"), "manifest.calculations")
    declared: set[EntrypointIdentity] = set()
    for calculation_index, raw_calculation in enumerate(calculations):
        calculation = _object(
            raw_calculation,
            f"manifest.calculations[{calculation_index}]",
        )
        entrypoints = _array(
            calculation.get("entrypoints"),
            f"manifest.calculations[{calculation_index}].entrypoints",
        )
        for entrypoint_index, raw_entrypoint in enumerate(entrypoints):
            label = (
                f"manifest.calculations[{calculation_index}]"
                f".entrypoints[{entrypoint_index}]"
            )
            entrypoint = _object(raw_entrypoint, label)
            if set(entrypoint) != {"entrypointId", "module", "symbol", "adapter"}:
                raise BackendClosureIndeterminate(
                    f"{label} のキー集合が schema と一致しない"
                )
            module = _manifest_module(
                _text(entrypoint, "module", label),
                source_prefix,
            )
            symbol = _text(entrypoint, "symbol", label)
            _text(entrypoint, "entrypointId", label)
            _text(entrypoint, "adapter", label)
            declared.add(EntrypointIdentity(module, symbol))
    return frozenset(declared)


def _observed_entrypoints(
    collection: Mapping[str, object],
) -> frozenset[EntrypointIdentity]:
    """既存収集器の入口と ROUTERS を同じ正規集合へ変換する。"""
    observed: set[EntrypointIdentity] = set()
    for collection_key in ("entries", "routers"):
        rows = _array(collection.get(collection_key), f"collection.{collection_key}")
        for index, raw_row in enumerate(rows):
            label = f"collection.{collection_key}[{index}]"
            row = _object(raw_row, label)
            observed.add(
                EntrypointIdentity(
                    _text(row, "module", label),
                    _text(row, "attribute", label),
                )
            )
    if not observed:
        raise BackendClosureIndeterminate("実在入口の収集結果が 0 件")
    return frozenset(observed)


def _forbidden_dynamic_loads(
    collection: Mapping[str, object],
) -> tuple[str, ...]:
    """本番到達可能な importlib・getattr・entry point を列挙する。"""
    violations: list[str] = []
    entries = _array(collection.get("entries"), "collection.entries")
    for index, raw_row in enumerate(entries):
        label = f"collection.entries[{index}]"
        row = _object(raw_row, label)
        kind = _text(row, "kind", label)
        if kind == "project-entry-point":
            violations.append(f"{_text(row, 'origin', label)}|{kind}")

    resolved = _array(
        collection.get("resolvedDynamic"),
        "collection.resolvedDynamic",
    )
    for index, raw_row in enumerate(resolved):
        label = f"collection.resolvedDynamic[{index}]"
        row = _object(raw_row, label)
        reachable = row.get("reachable")
        if not isinstance(reachable, bool):
            raise BackendClosureIndeterminate(f"{label}.reachable が boolean でない")
        if not reachable:
            continue
        construct = _text(row, "construct", label)
        if construct == "getattr" or construct.startswith("importlib."):
            violations.append(
                f"{_text(row, 'path', label)}|{construct}|"
                f"{_text(row, 'expression', label)}"
            )
    return tuple(sorted(violations))


def _collection_shape(
    collection: object,
) -> tuple[Mapping[str, object], int, int]:
    """収集結果の母集合計測と import graph の形を検査する。"""
    root = _object(collection, "collection")
    attempts = root.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts <= 0:
        raise BackendClosureIndeterminate("収集器の走査回数が正の整数でない")
    attempts_by_kind = _object(
        root.get("attemptsByKind"),
        "collection.attemptsByKind",
    )
    measured_attempts = 0
    for value in attempts_by_kind.values():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BackendClosureIndeterminate("走査種別の件数が非負整数でない")
        measured_attempts += value
    if measured_attempts != attempts:
        raise BackendClosureIndeterminate("走査回数と種別内訳が一致しない")

    unresolved = _array(root.get("unresolved"), "collection.unresolved")
    if unresolved:
        raise BackendClosureIndeterminate(
            f"静的に解決できない入口が {len(unresolved)} 件ある"
        )
    graph = _array(root.get("importGraph"), "collection.importGraph")
    for index, raw_edge in enumerate(graph):
        label = f"collection.importGraph[{index}]"
        edge = _object(raw_edge, label)
        _text(edge, "from", label)
        _text(edge, "to", label)
        _text(edge, "kind", label)
    return root, attempts, len(graph)


def inspect_backend_closure(
    collection: object,
    manifest: object,
) -> BackendClosureReport:
    """独立収集結果とマニフェストの入口を両方向に照合する。

    Args:
        collection: ``collect_entrypoints_be`` が返した実測値。
        manifest: D-11 の ``entrypoints[]`` を持つマニフェスト。

    Returns:
        走査件数、集合差、動的読み込みを持つ三値の検査結果。

    Raises:
        BackendClosureIndeterminate: 入力を静的に判定できない場合。
    """
    collected, attempts, graph_edges = _collection_shape(collection)
    source_root = collected.get("sourceRoot")
    if not isinstance(source_root, str) or not source_root:
        raise BackendClosureIndeterminate("collection.sourceRoot が非空文字列でない")
    source_prefix = _source_prefix(source_root)
    observed = _observed_entrypoints(collected)
    declared = _declared_entrypoints(manifest, source_prefix)
    difference = exact_set_difference(
        {item.canonical for item in declared},
        {item.canonical for item in observed},
    )
    forbidden = _forbidden_dynamic_loads(collected)
    status = (
        BackendClosureStatus.CONFORMING
        if difference.matches and not forbidden
        else BackendClosureStatus.NONCONFORMING
    )
    return BackendClosureReport(
        status=status,
        attempts=attempts,
        declared=declared,
        observed=observed,
        undeclared=difference.unexpected,
        missing_actual=difference.missing,
        forbidden_dynamic_loads=forbidden,
        import_graph_edges=graph_edges,
    )


def runtime_gate(manifest: object, source_root: str) -> RuntimeEntrypointGate:
    """マニフェスト宣言から実行時拒否ゲートを作る。"""
    return RuntimeEntrypointGate(
        _declared_entrypoints(manifest, _source_prefix(source_root))
    )


def _build_parser() -> argparse.ArgumentParser:
    """Backend 閉域 CLI の引数を定義する。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path("backend/src"))
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("backend/pyproject.toml"),
    )
    return parser


def _resolved(root: Path, path: Path) -> Path:
    """相対パスをリポジトリルート基準で解決する。"""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _indeterminate_report(reason: str, attempts: int = 0) -> dict[str, object]:
    """判定不能時にも走査件数を明示する JSON object を返す。"""
    return {
        "schemaVersion": 1,
        "status": BackendClosureStatus.INDETERMINATE.value,
        "attempts": attempts,
        "declaredCount": 0,
        "observedCount": 0,
        "importGraphEdgeCount": 0,
        "undeclaredEntrypoints": [],
        "missingActualEntrypoints": [],
        "forbiddenDynamicLoads": [],
        "reasons": [reason],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """独立収集と閉域照合を実行し、三値の exit code を返す。

    Args:
        argv: CLI 引数。``None`` ならプロセス引数を使う。

    Returns:
        適合は 0、不適合は 1、判定不能は 2。
    """
    attempts = 0
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        collection = collect_backend_entries(
            root,
            _resolved(root, arguments.source_root),
            _resolved(root, arguments.pyproject),
        )
        raw_attempts = collection.get("attempts")
        if isinstance(raw_attempts, int) and not isinstance(raw_attempts, bool):
            attempts = raw_attempts
        report = inspect_backend_closure(
            collection,
            read_json(_resolved(root, arguments.manifest)),
        )
        print(canonical_json(report.as_json()), end="")
        if report.status is BackendClosureStatus.NONCONFORMING:
            print("不適合: 宣言外の入口または閉域違反がある", file=sys.stderr)
            return EXIT_NONCONFORMING
        return EXIT_CONFORMING
    except (
        BackendClosureIndeterminate,
        CheckerExecutionError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(canonical_json(_indeterminate_report(str(error), attempts)), end="")
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE


if __name__ == "__main__":
    raise SystemExit(main())
