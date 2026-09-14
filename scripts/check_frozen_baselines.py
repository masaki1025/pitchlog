"""認可資産の凍結基準台帳と追記履歴を検査する。"""

from __future__ import annotations

import argparse
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
SCHEMA_VERSION = 1
ASSET_KIND = "authz_frozen_baselines"
ALLOWLIST_ASSET_KIND = "frozen_baseline_scan_allowlist"
COMMIT_SERIES = (
    "oracle_input",
    "oracle_meaning",
    "core_areas_guard",
)
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
ROOT_KEYS = frozenset({"schema_version", "asset_kind", "baselines"})
ALLOWLIST_ROOT_KEYS = frozenset({"schema_version", "asset_kind", "entries"})
ALLOWLIST_ENTRY_KEYS = frozenset(
    {"path", "value", "reason", "pending_removal"}
)
RECORD_KEYS = frozenset(
    {"commit", "supersedes", "approved_by", "approved_at", "reason"}
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
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

type BaselineRecord = dict[str, object]
type BaselineHistories = dict[str, tuple[BaselineRecord, ...]]
type ScanKey = tuple[str, str]


@dataclass(frozen=True)
class _ScanSummary:
    """凍結基準候補のソース走査件数を保持する。"""

    occurrences: int
    pairs: int
    values: int
    pending_removals: int


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


def _as_object(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise _FrozenBaselineError(f"F-1: {location} はオブジェクトでなければならない")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _as_array(value: object, location: str) -> list[object]:
    if not isinstance(value, list):
        raise _FrozenBaselineError(f"F-1: {location} は配列でなければならない")
    return value


def _require_exact_keys(
    value: dict[str, object],
    expected: frozenset[str],
    location: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise _FrozenBaselineError(
            f"F-1: {location} のキーが exact-set 不一致である: "
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


def _validate_history(
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
        _require_exact_keys(record, RECORD_KEYS, location)

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


def _validate_catalog(root: Path, text: str, display_path: str) -> BaselineHistories:
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
    expected_series = frozenset(COMMIT_SERIES)
    _require_exact_keys(baselines, expected_series, "baselines")
    return {
        series: _validate_history(root, series, baselines[series])
        for series in COMMIT_SERIES
    }


def _load_current_catalog(root: Path) -> BaselineHistories:
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
    if series not in COMMIT_SERIES:
        raise _FrozenBaselineError(f"F-1: 未知の commit 型系列である: {series}")
    histories = _load_current_catalog(root.resolve())
    commit = histories[series][-1]["commit"]
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        raise _FrozenBaselineError(
            f"F-1: baselines.{series} 末尾の commit が40桁の小文字hexではない"
        )
    return commit


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


def _load_base_catalog(root: Path, base: str) -> BaselineHistories:
    text = _git_output(
        root,
        "show",
        f"{base}:{CATALOG_RELATIVE_PATH.as_posix()}",
        predicate="F-4",
    )
    return _validate_catalog(root, text, f"{base}:{CATALOG_RELATIVE_PATH}")


def _validate_append_only(
    base_histories: BaselineHistories,
    current_histories: BaselineHistories,
) -> None:
    for series in COMMIT_SERIES:
        base_history = base_histories[series]
        current_history = current_histories[series]
        if current_history[: len(base_history)] != base_history:
            raise _FrozenBaselineError(
                f"F-4: baselines.{series} の既存記録が書き換えまたは削除された"
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
    current_histories: BaselineHistories,
) -> None:
    for series in COMMIT_SERIES:
        source_path, constant_name = INITIAL_SOURCE_BY_SERIES[series]
        expected_commit = _extract_base_constant(
            root,
            base,
            source_path,
            constant_name,
        )
        initial_commit = current_histories[series][0]["commit"]
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
) -> tuple[str, _ScanSummary]:
    """凍結基準台帳を merge-base と現在の checkout の間で検査する。

    Args:
        root: 検査対象リポジトリのルート。
        base_revision: PR base を指す Git revision。

    Returns:
        解決した一意な merge-base commit とソース走査件数。

    Raises:
        _FrozenBaselineError: 台帳違反または判定不能がある場合。
    """
    resolved_root = root.resolve()
    merge_base = _resolve_merge_base(resolved_root, base_revision)
    current_histories = _load_current_catalog(resolved_root)
    base_has_catalog = _base_has_catalog(resolved_root, merge_base)
    if base_has_catalog:
        base_histories = _load_base_catalog(resolved_root, merge_base)
        _validate_append_only(base_histories, current_histories)
    else:
        _validate_initial_records(resolved_root, merge_base, current_histories)
    summary = _validate_source_scan(resolved_root, base_has_catalog)
    return merge_base, summary


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 引数を解釈し、違反または判定不能を非0終了にする。

    Args:
        argv: テスト時に差し替える引数列。省略時はプロセス引数を使う。

    Returns:
        全述語を満たせば0、違反または判定不能なら1。
    """
    try:
        args = _parse_args(argv)
        merge_base, summary = check_frozen_baselines(args.root, args.base)
    except _FrozenBaselineError as error:
        print(f"{SCRIPT_NAME}: {error}", file=sys.stderr)
        return 1
    print(
        f"frozen-baselines: OK (base={merge_base}) "
        f"scan_occurrences={summary.occurrences} "
        f"scan_pairs={summary.pairs} "
        f"scan_values={summary.values} "
        f"pending_removal={summary.pending_removals}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
