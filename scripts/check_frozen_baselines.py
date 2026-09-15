"""認可資産の凍結基準台帳と追記履歴を検査する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import NoReturn

SCRIPT_NAME = "check_frozen_baselines"
CATALOG_RELATIVE_PATH = Path("contracts/authz/frozen-baselines.json")
ALLOWLIST_RELATIVE_PATH = Path("scripts/frozen-baseline-scan-allowlist.json")
CONTRACTS_RELATIVE_PATH = Path("contracts")
SCHEMA_VERSION = 1
ASSET_KIND = "authz_frozen_baselines"
ALLOWLIST_ASSET_KIND = "frozen_baseline_scan_allowlist"
INITIAL_SOURCE_BY_SERIES = {
    "oracle_input": (
        "scripts/check_authz_catalog.py",
        "ORACLE_INPUT_BASELINE_COMMIT",
    ),
    "oracle_meaning": (
        "backend/tests/db/authz/mutation_composition.py",
        "STEP2_BASE_REVISION",
    ),
    "core_areas_guard": (
        "tests/test_core_guard.py",
        "AUTHZ_GUARD_BASE_REVISION",
    ),
}
ROOT_KEYS = frozenset(
    {"schema_version", "asset_kind", "declarations", "baselines"}
)
DECLARATION_KEYS = frozenset(
    {"frozen_targets", "identity", "granularity", "basis_series"}
)
ALLOWLIST_ROOT_KEYS = frozenset({"schema_version", "asset_kind", "entries"})
ALLOWLIST_ENTRY_KEYS = frozenset(
    {"path", "value", "reason", "pending_removal"}
)
COMMIT_RECORD_KEYS = frozenset(
    {"commit", "supersedes", "approved_by", "approved_at", "reason"}
)
VERSION_RECORD_KEYS = frozenset(
    {
        "version",
        "canonical_sha256",
        "supersedes",
        "approved_by",
        "approved_at",
        "reason",
    }
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SOURCE_COMMIT_PATTERN = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])"
)
ISO_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
GIT_TIMEOUT_SECONDS = 30
SOURCE_PATHSPECS = (
    ":(glob)scripts/**/*.py",
    ":(glob)tests/**/*.py",
    ":(glob)backend/**/*.py",
)
SOURCE_ROOTS = frozenset({"scripts", "tests", "backend"})
DIGEST_EDGE_CONTAINERS = frozenset(
    {"input_manifest", "input_assets", "sealed_assets", "oracle_context", "baselines"}
)
DIGEST_EDGE_KEY_PATTERN = re.compile(r"digest|sha256|checksum", re.IGNORECASE)
DIGEST_EDGE_VALUE_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")

type BaselineRecord = dict[str, object]
type BaselineHistories = dict[str, tuple[BaselineRecord, ...]]
type ScanKey = tuple[str, str]


@dataclass(frozen=True)
class FrozenDeclaration:
    """凍結対象と比較方式・基準系列の宣言を保持する。"""

    name: str
    frozen_targets: tuple[str, ...]
    identity: str
    granularity: str
    basis_series: str

    def specifications(self) -> dict[str, object]:
        """委任された3指定を台帳と同じ形で返す。"""
        return {
            "frozen_targets": list(self.frozen_targets),
            "identity": self.identity,
            "granularity": self.granularity,
            "basis_series": self.basis_series,
        }


@dataclass(frozen=True)
class _FrozenCatalog:
    """検証済みの宣言と基準履歴を保持する。"""

    declarations: dict[str, FrozenDeclaration]
    histories: BaselineHistories


@dataclass(frozen=True)
class _CorpusState:
    """version型宣言から導出した母集合と派生資産を保持する。"""

    anchor_path: str
    follower_paths: tuple[str, ...]


@dataclass(frozen=True)
class _ScanSummary:
    """凍結基準候補のソース走査件数を保持する。"""

    occurrences: int
    pairs: int
    values: int
    pending_removals: int


@dataclass(frozen=True)
class _DigestEdge:
    """資産全体を指す digest 辺の検出位置と値を保持する。"""

    asset_path: str
    key_path: str
    value: str


class _FrozenBaselineError(Exception):
    """凍結基準を安全に検査できない状態を表す。"""


class _ArgumentParser(argparse.ArgumentParser):
    """引数エラーを fail-closed の検査エラーへ変換する。"""

    def error(self, message: str) -> NoReturn:
        """argparse の引数エラーを検査エラーとして送出する。

        Args:
            message: argparse が生成したエラー説明。

        Raises:
            _FrozenBaselineError: 引数が不正な場合。
        """
        raise _FrozenBaselineError(f"引数が不正である: {message}")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _ArgumentParser(description="認可資産の凍結基準台帳を検査する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument(
        "--base",
        required=True,
        help="三点差分の比較元に使う revision",
    )
    return parser.parse_args(argv)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _FrozenBaselineError(f"F-1: JSON キーが重複している: {key}")
        result[key] = value
    return result


def _parse_json(text: str, display_path: str) -> object:
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise _FrozenBaselineError(
            f"F-1: {display_path} が JSON として不正である: {error}"
        ) from error


def _as_object(
    value: object,
    location: str,
    predicate: str = "F-1",
) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise _FrozenBaselineError(
            f"{predicate}: {location} はオブジェクトでなければならない"
        )
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _as_array(
    value: object,
    location: str,
    predicate: str = "F-1",
) -> list[object]:
    if not isinstance(value, list):
        raise _FrozenBaselineError(
            f"{predicate}: {location} は配列でなければならない"
        )
    return value


def _require_exact_keys(
    value: dict[str, object],
    expected: frozenset[str],
    location: str,
    predicate: str = "F-1",
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise _FrozenBaselineError(
            f"{predicate}: {location} のキーが exact-set 不一致である: "
            f"actual={sorted(actual)}, expected={sorted(expected)}"
        )


def _git_output(root: Path, *args: str, predicate: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise _FrozenBaselineError(
            f"{predicate}: git {' '.join(args)} がタイムアウトした"
        ) from error
    except OSError as error:
        raise _FrozenBaselineError(
            f"{predicate}: git {' '.join(args)} を起動できない: {error}"
        ) from error
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise _FrozenBaselineError(
            f"{predicate}: git {' '.join(args)} に失敗した"
            f"(exit={result.returncode}): {stderr}"
        )
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _FrozenBaselineError(
            f"{predicate}: git {' '.join(args)} の出力が UTF-8 ではない"
        ) from error


def _resolve_merge_base(root: Path, base: str) -> str:
    output = _git_output(
        root,
        "merge-base",
        "--all",
        base,
        "HEAD",
        predicate="F-4/F-7",
    )
    candidates = output.splitlines()
    if len(candidates) != 1 or COMMIT_PATTERN.fullmatch(candidates[0]) is None:
        raise _FrozenBaselineError(
            "F-4/F-7: base と HEAD の merge-base が一意な commit ではない"
        )
    return candidates[0]


def _validate_reachable_commit(root: Path, series: str, commit: str) -> None:
    _git_output(
        root,
        "cat-file",
        "-e",
        f"{commit}^{{commit}}",
        predicate=f"F-5: {series} の commit を解決できない",
    )
    _git_output(
        root,
        "merge-base",
        "--is-ancestor",
        commit,
        "HEAD",
        predicate=f"F-5: {series} の commit が HEAD から到達不能",
    )


def _validate_approval(record: BaselineRecord, location: str) -> None:
    for key in ("approved_by", "approved_at", "reason"):
        value = record[key]
        if not isinstance(value, str) or not value.strip():
            raise _FrozenBaselineError(f"F-3: {location}.{key} が空である")
    approved_at = record["approved_at"]
    if not isinstance(approved_at, str):
        raise _FrozenBaselineError(f"F-3: {location}.approved_at が文字列ではない")
    if ISO_DATE_PATTERN.fullmatch(approved_at) is None:
        raise _FrozenBaselineError(
            f"F-3: {location}.approved_at が ISO 日付ではない"
        )
    try:
        date.fromisoformat(approved_at)
    except ValueError as error:
        raise _FrozenBaselineError(
            f"F-3: {location}.approved_at が実在する ISO 日付ではない"
        ) from error


def _validate_commit_history(
    root: Path,
    series: str,
    raw_history: object,
) -> tuple[BaselineRecord, ...]:
    history = _as_array(raw_history, f"baselines.{series}")
    if not history:
        raise _FrozenBaselineError(f"F-1: baselines.{series} が空である")

    records: list[BaselineRecord] = []
    observed_commits: set[str] = set()
    previous_commit: str | None = None
    for index, raw_record in enumerate(history):
        location = f"baselines.{series}[{index}]"
        record = _as_object(raw_record, location)
        _require_exact_keys(record, COMMIT_RECORD_KEYS, location)

        commit = record["commit"]
        if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
            raise _FrozenBaselineError(
                f"F-1: {location}.commit が40桁の小文字hexではない"
            )
        if commit in observed_commits:
            raise _FrozenBaselineError(
                f"F-6: baselines.{series} に同じ commit が複数ある: {commit}"
            )
        observed_commits.add(commit)

        supersedes = record["supersedes"]
        if supersedes != previous_commit:
            raise _FrozenBaselineError(
                f"F-2: {location}.supersedes が直前の commit と一致しない"
            )
        if supersedes is not None and (
            not isinstance(supersedes, str)
            or COMMIT_PATTERN.fullmatch(supersedes) is None
        ):
            raise _FrozenBaselineError(
                f"F-2: {location}.supersedes が40桁の小文字hexではない"
            )

        _validate_approval(record, location)
        _validate_reachable_commit(root, series, commit)
        records.append(record)
        previous_commit = commit
    return tuple(records)


def _validate_version_history(
    series: str,
    raw_history: object,
) -> tuple[BaselineRecord, ...]:
    history = _as_array(
        raw_history,
        f"baselines.{series}",
        predicate="G-4",
    )
    if not history:
        raise _FrozenBaselineError(f"G-4: baselines.{series} が空である")

    records: list[BaselineRecord] = []
    previous_version: int | None = None
    for index, raw_record in enumerate(history):
        location = f"baselines.{series}[{index}]"
        record = _as_object(raw_record, location, predicate="G-4")
        _require_exact_keys(
            record,
            VERSION_RECORD_KEYS,
            location,
            predicate="G-4",
        )

        version = record["version"]
        expected_version = index + 1
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != expected_version
        ):
            raise _FrozenBaselineError(
                f"G-4: {location}.version は {expected_version} でなければならない"
            )
        supersedes = record["supersedes"]
        if supersedes != previous_version:
            raise _FrozenBaselineError(
                f"F-2: {location}.supersedes が直前の version と一致しない"
            )
        if supersedes is not None and (
            not isinstance(supersedes, int) or isinstance(supersedes, bool)
        ):
            raise _FrozenBaselineError(
                f"F-2: {location}.supersedes が整数または null ではない"
            )
        digest = record["canonical_sha256"]
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise _FrozenBaselineError(
                f"G-2: {location}.canonical_sha256 が64桁の小文字hexではない"
            )
        _validate_approval(record, location)
        records.append(record)
        previous_version = version
    return tuple(records)


def _validate_declarations(
    raw_declarations: object,
    series_names: frozenset[str],
) -> dict[str, FrozenDeclaration]:
    declarations = _as_object(raw_declarations, "declarations")
    _require_exact_keys(
        declarations,
        series_names,
        "declarations",
        predicate="宣言",
    )
    validated: dict[str, FrozenDeclaration] = {}
    for name, raw_declaration in declarations.items():
        location = f"declarations.{name}"
        declaration = _as_object(raw_declaration, location, predicate="宣言")
        _require_exact_keys(
            declaration,
            DECLARATION_KEYS,
            location,
            predicate="宣言",
        )
        raw_targets = _as_array(
            declaration["frozen_targets"],
            f"{location}.frozen_targets",
            predicate="宣言",
        )
        targets: list[str] = []
        for index, raw_target in enumerate(raw_targets):
            if not isinstance(raw_target, str):
                raise _FrozenBaselineError(
                    f"宣言: {location}.frozen_targets[{index}] が文字列ではない"
                )
            target = PurePosixPath(raw_target)
            if (
                target.is_absolute()
                or target.as_posix() != raw_target
                or ".." in target.parts
                or not target.parts
            ):
                raise _FrozenBaselineError(
                    f"宣言: {location}.frozen_targets[{index}] が"
                    "正規化済みリポジトリ相対パスではない"
                )
            targets.append(raw_target)
        if not targets or len(targets) != len(set(targets)):
            raise _FrozenBaselineError(
                f"宣言: {location}.frozen_targets が空または重複を含む"
            )
        identity = declaration["identity"]
        granularity = declaration["granularity"]
        basis_series = declaration["basis_series"]
        for key, value in (
            ("identity", identity),
            ("granularity", granularity),
            ("basis_series", basis_series),
        ):
            if not isinstance(value, str) or not value.strip():
                raise _FrozenBaselineError(f"宣言: {location}.{key} が空である")
        assert isinstance(identity, str)
        assert isinstance(granularity, str)
        assert isinstance(basis_series, str)
        if basis_series != name:
            raise _FrozenBaselineError(
                f"宣言: {location}.basis_series が宣言名と一致しない"
            )
        validated[name] = FrozenDeclaration(
            name=name,
            frozen_targets=tuple(targets),
            identity=identity,
            granularity=granularity,
            basis_series=basis_series,
        )
    return validated


def _validate_catalog(root: Path, text: str, display_path: str) -> _FrozenCatalog:
    catalog = _as_object(_parse_json(text, display_path), display_path)
    _require_exact_keys(catalog, ROOT_KEYS, display_path)
    schema_version = catalog["schema_version"]
    if not isinstance(schema_version, int) or isinstance(
        schema_version, bool
    ) or schema_version != SCHEMA_VERSION:
        raise _FrozenBaselineError(
            f"F-1: schema_version は {SCHEMA_VERSION} でなければならない"
        )
    if catalog["asset_kind"] != ASSET_KIND:
        raise _FrozenBaselineError(
            f"F-1: asset_kind は {ASSET_KIND} でなければならない"
        )

    baselines = _as_object(catalog["baselines"], "baselines")
    series_names = frozenset(baselines)
    if not series_names:
        raise _FrozenBaselineError("台帳: baselines が空である")
    declarations = _validate_declarations(catalog["declarations"], series_names)
    histories: BaselineHistories = {}
    for series, raw_history in baselines.items():
        history = _as_array(raw_history, f"baselines.{series}")
        if not history:
            raise _FrozenBaselineError(f"F-1: baselines.{series} が空である")
        first = _as_object(history[0], f"baselines.{series}[0]")
        if "commit" in first and "version" not in first:
            histories[series] = _validate_commit_history(root, series, history)
        elif "version" in first and "commit" not in first:
            histories[series] = _validate_version_history(series, history)
        else:
            raise _FrozenBaselineError(
                f"F-1: baselines.{series} の記録型を一意に判定できない"
            )
    commit_series = {
        series for series, history in histories.items() if "commit" in history[0]
    }
    version_series = {
        series for series, history in histories.items() if "version" in history[0]
    }
    if commit_series != set(INITIAL_SOURCE_BY_SERIES) or len(version_series) != 1:
        raise _FrozenBaselineError(
            "台帳: commit型3系列とversion型1系列の構成が不正である"
        )
    return _FrozenCatalog(declarations=declarations, histories=histories)


def _load_current_catalog(root: Path) -> _FrozenCatalog:
    path = root / CATALOG_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise _FrozenBaselineError(
            f"F-1: {CATALOG_RELATIVE_PATH} が UTF-8 ではない"
        ) from error
    except OSError as error:
        raise _FrozenBaselineError(
            f"F-1: {CATALOG_RELATIVE_PATH} を読み込めない: {error}"
        ) from error
    return _validate_catalog(root, text, CATALOG_RELATIVE_PATH.as_posix())


def _load_json_object(root: Path, relative_path: Path, predicate: str) -> dict[str, object]:
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise _FrozenBaselineError(
            f"{predicate}: {relative_path} が UTF-8 ではない"
        ) from error
    except OSError as error:
        raise _FrozenBaselineError(
            f"{predicate}: {relative_path} を読み込めない: {error}"
        ) from error
    return _as_object(
        _parse_json(text, relative_path.as_posix()),
        relative_path.as_posix(),
        predicate=predicate,
    )


def _collect_digest_edges(
    value: object,
    *,
    asset_path: str,
    key_path: str,
    edges: list[_DigestEdge],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{key_path}.{key}"
            if (
                DIGEST_EDGE_KEY_PATTERN.search(key) is not None
                and isinstance(child, str)
                and DIGEST_EDGE_VALUE_PATTERN.fullmatch(child) is not None
            ):
                edges.append(
                    _DigestEdge(
                        asset_path=asset_path,
                        key_path=child_path,
                        value=child,
                    )
                )
            _collect_digest_edges(
                child,
                asset_path=asset_path,
                key_path=child_path,
                edges=edges,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_digest_edges(
                child,
                asset_path=asset_path,
                key_path=f"{key_path}[{index}]",
                edges=edges,
            )


def _enumerate_digest_edges(root: Path) -> tuple[_DigestEdge, ...]:
    """contracts 配下から資産全体を指す digest 辺を全数列挙する。"""
    contracts_root = root / CONTRACTS_RELATIVE_PATH
    try:
        paths = sorted(contracts_root.rglob("*.json"))
    except OSError as error:
        raise _FrozenBaselineError(
            f"digest 辺: {CONTRACTS_RELATIVE_PATH} を走査できない: {error}"
        ) from error

    edges: list[_DigestEdge] = []
    for path in paths:
        relative_path = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise _FrozenBaselineError(
                f"digest 辺: {relative_path} が UTF-8 ではない"
            ) from error
        except OSError as error:
            raise _FrozenBaselineError(
                f"digest 辺: {relative_path} を読み込めない: {error}"
            ) from error
        raw = _parse_json(text, relative_path)
        if not isinstance(raw, dict):
            continue
        for container in sorted(DIGEST_EDGE_CONTAINERS):
            if container in raw:
                _collect_digest_edges(
                    raw[container],
                    asset_path=relative_path,
                    key_path=container,
                    edges=edges,
                )
    return tuple(edges)


def _version_declaration(catalog: _FrozenCatalog) -> FrozenDeclaration:
    declarations = [
        catalog.declarations[series]
        for series, history in catalog.histories.items()
        if "version" in history[0]
    ]
    if len(declarations) != 1:
        raise _FrozenBaselineError("G-4: version型の宣言が一意でない")
    return declarations[0]


def _require_declaration_protocol(
    declaration: FrozenDeclaration,
    *,
    identity: str,
    granularity: str,
) -> None:
    """宣言した比較方式に対応する実装経路だけを受理する。"""
    if (
        declaration.identity != identity
        or declaration.granularity != granularity
    ):
        raise _FrozenBaselineError(
            f"宣言: {declaration.name} の比較方式を実行できない: "
            f"identity={declaration.identity}, "
            f"granularity={declaration.granularity}"
        )


def _oracle_seal_from_declarations(
    root: Path,
    catalog: _FrozenCatalog,
) -> tuple[str, dict[str, object]]:
    """宣言対象から oracle seal を構造で一意に導出する。"""
    candidates: list[tuple[str, dict[str, object]]] = []
    targets = {
        target
        for declaration in catalog.declarations.values()
        for target in declaration.frozen_targets
        if target.startswith("contracts/") and target.endswith(".json")
    }
    for target in sorted(targets):
        value = _load_json_object(root, Path(target), "宣言")
        if "input_assets" in value and "sealed_assets" in value:
            candidates.append((target, value))
    if len(candidates) != 1:
        raise _FrozenBaselineError(
            "宣言: input_assets と sealed_assets を持つ凍結対象が一意でない"
        )
    return candidates[0]


def _declaration_for_exact_targets(
    catalog: _FrozenCatalog,
    targets: set[str],
    label: str,
) -> FrozenDeclaration:
    candidates = [
        declaration
        for declaration in catalog.declarations.values()
        if set(declaration.frozen_targets) == targets
    ]
    if len(candidates) != 1:
        raise _FrozenBaselineError(
            f"宣言: {label} の frozen_targets と完全一致する宣言が一意でない"
        )
    return candidates[0]


def _seal_target_sets(
    seal_path: str,
    seal: dict[str, object],
) -> tuple[set[str], set[str]]:
    input_assets = _as_array(
        seal.get("input_assets"),
        f"{seal_path}.input_assets",
        predicate="宣言",
    )
    sealed_assets = _as_array(
        seal.get("sealed_assets"),
        f"{seal_path}.sealed_assets",
        predicate="宣言",
    )

    def row_paths(rows: list[object], location: str) -> set[str]:
        paths: set[str] = set()
        for index, raw_row in enumerate(rows):
            row = _as_object(raw_row, f"{location}[{index}]", predicate="宣言")
            path = row.get("path")
            if not isinstance(path, str) or not path:
                raise _FrozenBaselineError(
                    f"宣言: {location}[{index}].path が空である"
                )
            if path in paths:
                raise _FrozenBaselineError(f"宣言: {location}.path が重複している")
            paths.add(path)
        return paths

    return (
        row_paths(input_assets, f"{seal_path}.input_assets"),
        row_paths(sealed_assets, f"{seal_path}.sealed_assets"),
    )


def _validate_declaration_wiring(
    root: Path,
    catalog: _FrozenCatalog,
) -> tuple[str, dict[str, object]]:
    """sealの実集合と宣言の対象集合・比較方式を完全一致で結線する。"""
    seal_path, seal = _oracle_seal_from_declarations(root, catalog)
    input_targets, sealed_targets = _seal_target_sets(seal_path, seal)
    input_declaration = _declaration_for_exact_targets(
        catalog,
        input_targets,
        "oracle入力",
    )
    _require_declaration_protocol(
        input_declaration,
        identity="git_blob_digest",
        granularity="blob",
    )
    meaning_declaration = _declaration_for_exact_targets(
        catalog,
        sealed_targets | {seal_path},
        "oracle意味本文",
    )
    _require_declaration_protocol(
        meaning_declaration,
        identity="canonical_json",
        granularity="asset_without_movable_pointers",
    )
    return seal_path, seal


def _expected_digest_edge_counts(
    catalog: _FrozenCatalog,
    corpus_state: _CorpusState,
    seal_path: str,
    seal: dict[str, object],
) -> dict[str, int]:
    """宣言済み資産の構造から digest 辺の期待本数を導出する。"""
    input_assets = _as_array(
        seal.get("input_assets"),
        f"{seal_path}.input_assets",
        predicate="digest 辺",
    )
    sealed_assets = _as_array(
        seal.get("sealed_assets"),
        f"{seal_path}.sealed_assets",
        predicate="digest 辺",
    )
    version_declaration = _version_declaration(catalog)
    expected = {
        target: 0
        for declaration in catalog.declarations.values()
        for target in declaration.frozen_targets
        if target.startswith("contracts/") and target.endswith(".json")
    }
    expected[seal_path] = len(input_assets) + len(sealed_assets)
    expected[corpus_state.anchor_path] = 1
    expected[CATALOG_RELATIVE_PATH.as_posix()] = len(
        catalog.histories[version_declaration.basis_series]
    )
    return expected


def _validate_digest_edge_composition(
    root: Path,
    catalog: _FrozenCatalog,
    corpus_state: _CorpusState,
    seal_path: str,
    seal: dict[str, object],
) -> tuple[_DigestEdge, ...]:
    edges = _enumerate_digest_edges(root)
    expected = _expected_digest_edge_counts(
        catalog,
        corpus_state,
        seal_path,
        seal,
    )
    actual: dict[str, int] = {}
    for edge in edges:
        actual[edge.asset_path] = actual.get(edge.asset_path, 0) + 1
    mismatches = {
        path: (actual.get(path, 0), count)
        for path, count in expected.items()
        if actual.get(path, 0) != count
    }
    unexpected = {
        path: count for path, count in actual.items() if path not in expected
    }
    if mismatches or unexpected:
        raise _FrozenBaselineError(
            "digest 辺: 資産ごとの構成が期待と一致しない: "
            f"mismatches={mismatches}, unexpected={unexpected}"
        )
    return edges


def _canonical_sha256(value: object) -> str:
    """既存 authz 資産と同じ canonical JSON の SHA-256 を返す。"""
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _corpus_version(value: dict[str, object], location: str, predicate: str) -> int:
    version = value.get("corpus_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise _FrozenBaselineError(
            f"{predicate}: {location}.corpus_version が1以上の整数ではない"
        )
    return version


def _validate_corpus_state(
    root: Path,
    catalog: _FrozenCatalog,
) -> _CorpusState:
    declaration = _version_declaration(catalog)
    _require_declaration_protocol(
        declaration,
        identity="canonical_sha256_and_corpus_version",
        granularity="canonical_json_asset",
    )
    latest = catalog.histories[declaration.basis_series][-1]
    ledger_version = latest["version"]
    ledger_digest = latest["canonical_sha256"]
    assert isinstance(ledger_version, int)
    assert isinstance(ledger_digest, str)

    assets = {
        target: _load_json_object(root, Path(target), "G-1/G-2/G-5")
        for target in declaration.frozen_targets
    }
    anchors: list[str] = []
    for target, asset in assets.items():
        input_manifest = asset.get("input_manifest")
        if not isinstance(input_manifest, dict):
            continue
        source_digest = input_manifest.get("source_blob_digest")
        if (
            isinstance(source_digest, str)
            and DIGEST_EDGE_VALUE_PATTERN.fullmatch(source_digest) is not None
        ):
            anchors.append(target)
    if len(anchors) != 1:
        raise _FrozenBaselineError(
            "G-2: 宣言対象のうち入力元 digest を持つ母集合が一意でない: "
            f"{tuple(sorted(anchors))}"
        )
    anchor_path = anchors[0]
    corpus = assets[anchor_path]
    corpus_version = _corpus_version(corpus, anchor_path, "G-1")
    if corpus_version != ledger_version:
        raise _FrozenBaselineError(
            "G-1: 母集合の corpus_version が台帳末尾の version と一致しない: "
            f"corpus={corpus_version}, ledger={ledger_version}"
        )
    actual_digest = _canonical_sha256(corpus)
    if actual_digest != ledger_digest:
        raise _FrozenBaselineError(
            "G-2: 母集合の canonical digest が台帳末尾と一致しない: "
            f"actual={actual_digest}, ledger={ledger_digest}"
        )
    follower_paths = tuple(
        target for target in declaration.frozen_targets if target != anchor_path
    )
    for relative_path in follower_paths:
        derived = assets[relative_path]
        derived_version = _corpus_version(derived, relative_path, "G-5")
        if derived_version != corpus_version:
            raise _FrozenBaselineError(
                f"G-5: {relative_path}.corpus_version が母集合と一致しない: "
                f"derived={derived_version}, corpus={corpus_version}"
            )
    return _CorpusState(
        anchor_path=anchor_path,
        follower_paths=follower_paths,
    )


def load_frozen_baseline_commit(root: Path, series: str) -> str:
    """commit 型系列の末尾から現行の凍結基準を読む。

    Args:
        root: リポジトリルート。
        series: 読み出す commit 型系列名。

    Returns:
        系列末尾の40桁commit。

    Raises:
        _FrozenBaselineError: 台帳を読めない、系列が不正、または記録が不正な場合。
    """
    catalog = _load_current_catalog(root.resolve())
    history = catalog.histories.get(series)
    if history is None or "commit" not in history[0]:
        raise _FrozenBaselineError(f"F-1: 未知の commit 型系列である: {series}")
    commit = history[-1]["commit"]
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        raise _FrozenBaselineError(
            f"F-1: baselines.{series} 末尾の commit が40桁の小文字hexではない"
        )
    return commit


def load_frozen_declaration_for_target(
    root: Path,
    target: str,
) -> FrozenDeclaration:
    """指定対象を含む宣言を一意に読み出す。

    Args:
        root: リポジトリルート。
        target: 宣言を探す凍結対象のリポジトリ相対パス。

    Returns:
        対象を含む一意な凍結宣言。

    Raises:
        _FrozenBaselineError: 宣言が無い、または複数ある場合。
    """
    catalog = _load_current_catalog(root.resolve())
    candidates = [
        declaration
        for declaration in catalog.declarations.values()
        if target in declaration.frozen_targets
    ]
    if len(candidates) != 1:
        raise _FrozenBaselineError(
            f"宣言: 凍結対象 {target} を含む宣言が一意でない"
        )
    return candidates[0]


def load_frozen_baseline_for_target(
    root: Path,
    target: str,
) -> tuple[FrozenDeclaration, str]:
    """対象の宣言と、その宣言が指す末尾 commit を返す。"""
    catalog = _load_current_catalog(root.resolve())
    candidates = [
        declaration
        for declaration in catalog.declarations.values()
        if target in declaration.frozen_targets
    ]
    if len(candidates) != 1:
        raise _FrozenBaselineError(
            f"宣言: 凍結対象 {target} を含む宣言が一意でない"
        )
    declaration = candidates[0]
    history = catalog.histories[declaration.basis_series]
    commit = history[-1].get("commit")
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        raise _FrozenBaselineError(
            f"F-1: baselines.{declaration.basis_series} 末尾の commit が不正"
        )
    return declaration, commit


def format_frozen_declaration_usage(declaration: FrozenDeclaration) -> str:
    """検査が現に用いた3指定を機械可読な1行にする。"""
    return json.dumps(
        declaration.specifications(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _base_has_catalog(root: Path, base: str) -> bool:
    output = _git_output(
        root,
        "ls-tree",
        "-z",
        "--name-only",
        base,
        "--",
        CATALOG_RELATIVE_PATH.as_posix(),
        predicate="F-4/F-7",
    )
    paths = tuple(path for path in output.split("\0") if path)
    if not paths:
        return False
    if paths != (CATALOG_RELATIVE_PATH.as_posix(),):
        raise _FrozenBaselineError(
            f"F-4/F-7: base の台帳パス解決結果が不正である: {paths}"
        )
    return True


def _load_base_catalog(root: Path, base: str) -> _FrozenCatalog:
    text = _git_output(
        root,
        "show",
        f"{base}:{CATALOG_RELATIVE_PATH.as_posix()}",
        predicate="F-4",
    )
    return _validate_catalog(root, text, f"{base}:{CATALOG_RELATIVE_PATH}")


def _validate_append_only(
    base_catalog: _FrozenCatalog,
    current_catalog: _FrozenCatalog,
) -> None:
    for series, base_history in base_catalog.histories.items():
        current_history = current_catalog.histories.get(series, ())
        if current_history[: len(base_history)] != base_history:
            predicate = "G-3/F-4" if "version" in base_history[0] else "F-4"
            raise _FrozenBaselineError(
                f"{predicate}: baselines.{series} の既存記録が書き換えまたは削除された"
            )


def _extract_base_constant(
    root: Path,
    base: str,
    source_path: str,
    constant_name: str,
) -> str:
    text = _git_output(
        root,
        "show",
        f"{base}:{source_path}",
        predicate="F-7",
    )
    pattern = re.compile(
        rf'^{re.escape(constant_name)}\s*=\s*"([0-9a-f]{{40}})"$',
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise _FrozenBaselineError(
            f"F-7: {base}:{source_path} の {constant_name} がちょうど1件ではない"
        )
    return matches[0]


def _validate_initial_records(
    root: Path,
    base: str,
    current_catalog: _FrozenCatalog,
) -> None:
    for series, (source_path, constant_name) in INITIAL_SOURCE_BY_SERIES.items():
        expected_commit = _extract_base_constant(
            root,
            base,
            source_path,
            constant_name,
        )
        initial_commit = current_catalog.histories[series][0]["commit"]
        if initial_commit != expected_commit:
            raise _FrozenBaselineError(
                f"F-7: baselines.{series}[0].commit が base 側の "
                f"{constant_name} と一致しない"
            )


def _load_scan_allowlist(root: Path) -> dict[ScanKey, bool]:
    path = root / ALLOWLIST_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise _FrozenBaselineError(
            f"allow-list: {ALLOWLIST_RELATIVE_PATH} が UTF-8 ではない"
        ) from error
    except OSError as error:
        raise _FrozenBaselineError(
            f"allow-list: {ALLOWLIST_RELATIVE_PATH} を読み込めない: {error}"
        ) from error

    allowlist = _as_object(
        _parse_json(text, ALLOWLIST_RELATIVE_PATH.as_posix()),
        ALLOWLIST_RELATIVE_PATH.as_posix(),
    )
    _require_exact_keys(
        allowlist,
        ALLOWLIST_ROOT_KEYS,
        ALLOWLIST_RELATIVE_PATH.as_posix(),
    )
    if allowlist["schema_version"] != SCHEMA_VERSION or isinstance(
        allowlist["schema_version"], bool
    ):
        raise _FrozenBaselineError(
            f"allow-list: schema_version は {SCHEMA_VERSION} でなければならない"
        )
    if allowlist["asset_kind"] != ALLOWLIST_ASSET_KIND:
        raise _FrozenBaselineError(
            f"allow-list: asset_kind は {ALLOWLIST_ASSET_KIND} でなければならない"
        )

    entries = _as_array(allowlist["entries"], "allow-list.entries")
    declared: dict[ScanKey, bool] = {}
    for index, raw_entry in enumerate(entries):
        location = f"allow-list.entries[{index}]"
        entry = _as_object(raw_entry, location)
        _require_exact_keys(entry, ALLOWLIST_ENTRY_KEYS, location)

        raw_path = entry["path"]
        if not isinstance(raw_path, str):
            raise _FrozenBaselineError(f"allow-list: {location}.path が文字列ではない")
        relative_path = PurePosixPath(raw_path)
        if (
            relative_path.is_absolute()
            or relative_path.as_posix() != raw_path
            or ".." in relative_path.parts
            or len(relative_path.parts) < 2
            or relative_path.parts[0] not in SOURCE_ROOTS
            or relative_path.suffix != ".py"
        ):
            raise _FrozenBaselineError(
                f"allow-list: {location}.path が走査対象の相対パスではない"
            )

        value = entry["value"]
        if not isinstance(value, str) or COMMIT_PATTERN.fullmatch(value) is None:
            raise _FrozenBaselineError(
                f"allow-list: {location}.value が40桁の小文字hexではない"
            )
        reason = entry["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise _FrozenBaselineError(f"allow-list: {location}.reason が空である")
        pending_removal = entry["pending_removal"]
        if not isinstance(pending_removal, bool):
            raise _FrozenBaselineError(
                f"allow-list: {location}.pending_removal が真偽値ではない"
            )

        key = (raw_path, value)
        if key in declared:
            raise _FrozenBaselineError(
                f"allow-list: (path, value) が重複している: {raw_path}, {value}"
            )
        declared[key] = pending_removal
    return declared


def _source_paths(root: Path) -> tuple[str, ...]:
    output = _git_output(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *SOURCE_PATHSPECS,
        predicate="allow-list",
    )
    paths = tuple(path for path in output.split("\0") if path)
    if len(paths) != len(set(paths)):
        raise _FrozenBaselineError("allow-list: 走査対象パスが重複している")
    return paths


def _scan_source_commits(root: Path) -> tuple[dict[ScanKey, int], int]:
    observed: dict[ScanKey, int] = {}
    occurrence_count = 0
    for relative_path in _source_paths(root):
        path = root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise _FrozenBaselineError(
                f"allow-list: {relative_path} が UTF-8 ではない"
            ) from error
        except OSError as error:
            raise _FrozenBaselineError(
                f"allow-list: {relative_path} を読み込めない: {error}"
            ) from error
        for match in SOURCE_COMMIT_PATTERN.finditer(text):
            key = (relative_path, match.group(0))
            observed[key] = observed.get(key, 0) + 1
            occurrence_count += 1
    return observed, occurrence_count


def _format_scan_keys(keys: set[ScanKey]) -> str:
    return ", ".join(f"({path}, {value})" for path, value in sorted(keys))


def _validate_source_scan(root: Path, base_has_catalog: bool) -> _ScanSummary:
    declared = _load_scan_allowlist(root)
    if base_has_catalog:
        pending = {key for key, is_pending in declared.items() if is_pending}
        if pending:
            raise _FrozenBaselineError(
                "allow-list: 台帳が base に存在するため pending_removal=true "
                f"を許可できない: {_format_scan_keys(pending)}"
            )

    observed, occurrence_count = _scan_source_commits(root)
    observed_keys = set(observed)
    declared_keys = set(declared)
    unknown = observed_keys - declared_keys
    if unknown:
        raise _FrozenBaselineError(
            "allow-list: 走査で見つかったが allow-list にない (path, value): "
            f"{_format_scan_keys(unknown)}"
        )
    stale = declared_keys - observed_keys
    if stale:
        raise _FrozenBaselineError(
            "allow-list: allow-list にあるが走査で見つからない (path, value): "
            f"{_format_scan_keys(stale)}"
        )
    return _ScanSummary(
        occurrences=occurrence_count,
        pairs=len(observed_keys),
        values=len({value for _, value in observed_keys}),
        pending_removals=sum(declared.values()),
    )


def check_frozen_baselines(
    root: Path,
    base_revision: str,
) -> tuple[
    str,
    _ScanSummary,
    tuple[_DigestEdge, ...],
    tuple[FrozenDeclaration, ...],
]:
    """凍結基準台帳を merge-base と現在の checkout の間で検査する。

    Args:
        root: 検査対象リポジトリのルート。
        base_revision: PR base を指す Git revision。

    Returns:
        解決した一意な merge-base commit、ソース走査件数、digest 辺の一覧、
        および現に用いた宣言。

    Raises:
        _FrozenBaselineError: 台帳違反または判定不能がある場合。
    """
    resolved_root = root.resolve()
    merge_base = _resolve_merge_base(resolved_root, base_revision)
    current_catalog = _load_current_catalog(resolved_root)
    seal_path, seal = _validate_declaration_wiring(resolved_root, current_catalog)
    corpus_state = _validate_corpus_state(resolved_root, current_catalog)
    base_has_catalog = _base_has_catalog(resolved_root, merge_base)
    if base_has_catalog:
        base_catalog = _load_base_catalog(resolved_root, merge_base)
        _validate_append_only(base_catalog, current_catalog)
    else:
        _validate_initial_records(resolved_root, merge_base, current_catalog)
    summary = _validate_source_scan(resolved_root, base_has_catalog)
    digest_edges = _validate_digest_edge_composition(
        resolved_root,
        current_catalog,
        corpus_state,
        seal_path,
        seal,
    )
    used_declarations = tuple(
        current_catalog.declarations[name]
        for name in sorted(current_catalog.declarations)
    )
    return merge_base, summary, digest_edges, used_declarations


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 引数を解釈し、違反または判定不能を非0終了にする。

    Args:
        argv: テスト時に差し替える引数列。省略時はプロセス引数を使う。

    Returns:
        全述語を満たせば0、違反または判定不能なら1。
    """
    try:
        args = _parse_args(argv)
        merge_base, summary, digest_edges, declarations = check_frozen_baselines(
            args.root,
            args.base,
        )
    except _FrozenBaselineError as error:
        print(f"{SCRIPT_NAME}: {error}", file=sys.stderr)
        return 1
    print(
        f"frozen-baselines: OK (base={merge_base}) "
        f"scan_occurrences={summary.occurrences} "
        f"scan_pairs={summary.pairs} "
        f"scan_values={summary.values} "
        f"pending_removal={summary.pending_removals} "
        f"digest_edges={len(digest_edges)}"
    )
    for declaration in declarations:
        print(
            f"frozen-declaration-used[{declaration.name}]="
            f"{format_frozen_declaration_usage(declaration)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
