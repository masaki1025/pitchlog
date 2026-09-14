"""認可資産の凍結基準台帳と追記履歴を検査する。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import NoReturn

SCRIPT_NAME = "check_frozen_baselines"
CATALOG_RELATIVE_PATH = Path("contracts/authz/frozen-baselines.json")
SCHEMA_VERSION = 1
ASSET_KIND = "authz_frozen_baselines"
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
RECORD_KEYS = frozenset(
    {"commit", "supersedes", "approved_by", "approved_at", "reason"}
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
ISO_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
GIT_TIMEOUT_SECONDS = 30

type BaselineRecord = dict[str, object]
type BaselineHistories = dict[str, tuple[BaselineRecord, ...]]


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


def check_frozen_baselines(root: Path, base_revision: str) -> str:
    """凍結基準台帳を merge-base と現在の checkout の間で検査する。

    Args:
        root: 検査対象リポジトリのルート。
        base_revision: PR base を指す Git revision。

    Returns:
        解決した一意な merge-base commit。

    Raises:
        _FrozenBaselineError: 台帳違反または判定不能がある場合。
    """
    resolved_root = root.resolve()
    merge_base = _resolve_merge_base(resolved_root, base_revision)
    current_histories = _load_current_catalog(resolved_root)
    if _base_has_catalog(resolved_root, merge_base):
        base_histories = _load_base_catalog(resolved_root, merge_base)
        _validate_append_only(base_histories, current_histories)
    else:
        _validate_initial_records(resolved_root, merge_base, current_histories)
    return merge_base


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 引数を解釈し、違反または判定不能を非0終了にする。

    Args:
        argv: テスト時に差し替える引数列。省略時はプロセス引数を使う。

    Returns:
        全述語を満たせば0、違反または判定不能なら1。
    """
    try:
        args = _parse_args(argv)
        merge_base = check_frozen_baselines(args.root, args.base)
    except _FrozenBaselineError as error:
        print(f"{SCRIPT_NAME}: {error}", file=sys.stderr)
        return 1
    print(f"frozen-baselines: OK (base={merge_base})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
