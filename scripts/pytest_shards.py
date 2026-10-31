"""CI の pytest 分割が全件を各1回だけ実行することを機械検証する。

シャード分割は、分割前の全件収集と各シャードの収集結果を突き合わせて
「欠落・重複・意図しない 0 件」が無いことを確認する。ファイル所属だけでなく
収集したテスト ID の和集合で判定するため、新しいテストファイルやパラメータ
追加も自動的に検査対象になる。

使い方:
    python scripts/pytest_shards.py verify --suite harness
    python scripts/pytest_shards.py verify --suite backend --require-db
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CONFIG_RELATIVE_PATH = Path("ci") / "pytest-shards.json"
SCRIPTS_RELATIVE_PATH = Path("scripts")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "pytest_shard_plugin"
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SHARD_TOTAL_ENV = "PITCHLOG_SHARD_TOTAL_FILE"


class ShardError(RuntimeError):
    """分割定義・収集・被覆のいずれかが契約に反する。"""


@dataclass(frozen=True, slots=True)
class Suite:
    """1 つの pytest スイート(CI ジョブ群)の分割定義。"""

    name: str
    root: Path
    targets: tuple[str, ...]
    ignore: tuple[str, ...]
    shards: int


def load_suites(root: Path) -> dict[str, Suite]:
    """分割定義を読み、契約どおりの形かを検証する。

    Args:
        root: リポジトリルート。

    Returns:
        スイート名から定義への対応。

    Raises:
        ShardError: 定義が読めない、または必須項目・型が不正な場合。
    """
    path = root / CONFIG_RELATIVE_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ShardError(f"分割定義を読めない: {path}: {error}") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ShardError("分割定義の schema_version が 1 ではない")
    suites = raw.get("suites")
    if not isinstance(suites, dict) or not suites:
        raise ShardError("分割定義の suites が空")
    result: dict[str, Suite] = {}
    for name, item in suites.items():
        if not isinstance(name, str) or not name or not isinstance(item, dict):
            raise ShardError("分割定義のスイート行が不正")
        root_value = item.get("root")
        targets = item.get("targets")
        ignore = item.get("ignore")
        shards = item.get("shards")
        if not isinstance(root_value, str) or not root_value:
            raise ShardError(f"{name}.root が文字列ではない")
        if (
            not isinstance(targets, list)
            or not targets
            or any(not isinstance(value, str) or not value for value in targets)
        ):
            raise ShardError(f"{name}.targets が文字列配列ではない")
        if not isinstance(ignore, list) or any(
            not isinstance(value, str) or not value for value in ignore
        ):
            raise ShardError(f"{name}.ignore が文字列配列ではない")
        if type(shards) is not int or shards < 1:
            raise ShardError(f"{name}.shards が正の整数ではない")
        result[name] = Suite(
            name=name,
            root=(root / root_value).resolve(),
            targets=tuple(targets),
            ignore=tuple(ignore),
            shards=shards,
        )
    return result


def _environment(root: Path) -> dict[str, str]:
    """プラグインを import 可能にする環境変数を返す。"""
    environment = dict(os.environ)
    scripts = str(root / SCRIPTS_RELATIVE_PATH)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{scripts}{os.pathsep}{existing}" if existing else scripts
    return environment


def normalize(node_id: str) -> str:
    """乱数 UUID を伏せた比較用の識別子を返す。

    パラメータに乱数 UUID を含む試験があるため、node id の文字列そのものは
    実行ごとに変わる。収集順の安定性を前提に、UUID だけを潰して多重集合で
    欠落・重複を判定する。
    """
    return UUID_RE.sub("<uuid>", node_id)


def collect(
    suite: Suite,
    root: Path,
    *,
    shard_count: int = 0,
    shard_index: int = 0,
    marker: str | None = None,
    total_file: Path | None = None,
) -> tuple[set[str], int | None]:
    """テスト ID を収集する。

    Args:
        suite: 対象スイート。
        root: リポジトリルート。
        shard_count: 分割数。0 は分割しない。
        shard_index: 0 始まりのシャード番号。
        marker: 追加の `-m` 条件。
        total_file: 分割前の総数を書き出すパス。

    Returns:
        収集された node id の集合と、分割前の総数(分割時のみ)。

    Raises:
        ShardError: pytest が収集に失敗した場合。
    """
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(suite.root / "pyproject.toml"),
        "-p",
        PLUGIN_NAME,
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        *suite.targets,
        *(f"--ignore={ignored}" for ignored in suite.ignore),
    ]
    if shard_count:
        command.extend(["--shard-count", str(shard_count), "--shard-index", str(shard_index)])
    if marker is not None:
        command.extend(["-m", marker])
    environment = _environment(root)
    if total_file is not None:
        environment[SHARD_TOTAL_ENV] = str(total_file)
    completed = subprocess.run(
        command,
        cwd=suite.root,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise ShardError(
            f"{suite.name}: 収集に失敗した: {completed.stdout[-2000:]}{completed.stderr[-2000:]}"
        )
    ids: set[str] = set()
    total: int | None = None
    if total_file is not None:
        try:
            total = int(total_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            total = None
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or "::" not in stripped:
            continue
        if stripped.startswith(("=", "_", " ", "!")):
            continue
        ids.add(stripped)
    if not ids:
        raise ShardError(f"{suite.name}: テスト ID を 1 件も収集できなかった")
    return ids, total


def verify(suite: Suite, root: Path, *, require_db: bool = False) -> str:
    """分割が全件を各1回だけ実行することを検証する。

    Args:
        suite: 対象スイート。
        root: リポジトリルート。
        require_db: requires_db の被覆も検証するか。

    Returns:
        検証結果の要約。

    Raises:
        ShardError: 0 件・欠落・重複・DB 未実行のいずれか。
    """
    everything, _ = collect(suite, root)
    per_shard: dict[int, set[str]] = {}
    totals: set[int] = set()
    for index in range(suite.shards):
        with tempfile.TemporaryDirectory(prefix="pytest-shard-total-") as raw:
            ids, total = collect(
                suite,
                root,
                shard_count=suite.shards,
                shard_index=index,
                total_file=Path(raw) / "total",
            )
        if total is None:
            raise ShardError(f"{suite.name}: シャード {index} の総数が報告されない")
        totals.add(total)
        per_shard[index] = ids
    if len(totals) != 1 or totals.pop() != len(everything):
        raise ShardError(
            f"{suite.name}: 分割前の総数が実行間で一致しない: "
            f"full={len(everything)} shards={sorted(totals)}"
        )
    union = collections.Counter(normalize(node_id) for ids in per_shard.values() for node_id in ids)
    expected = collections.Counter(normalize(node_id) for node_id in everything)
    if union != expected:
        missing = list((expected - union).elements())[:10]
        extra = list((union - expected).elements())[:10]
        raise ShardError(f"{suite.name}: 収集結果と分割が一致しない: 欠落={missing} 余剰={extra}")
    sizes = [len(per_shard[index]) for index in range(suite.shards)]
    if any(size == 0 for size in sizes):
        raise ShardError(f"{suite.name}: 0 件のシャードがある: sizes={sizes}")
    if require_db:
        db_tests, _ = collect(suite, root, marker="requires_db")
        if not db_tests:
            raise ShardError(f"{suite.name}: requires_db のテストが 1 件も無い")
        db_shards = [index for index in range(suite.shards) if per_shard[index] & db_tests]
        if not db_shards:
            raise ShardError(f"{suite.name}: requires_db を含むシャードが無い")
    return f"{suite.name}: {len(everything)} tests / {suite.shards} shards / sizes={sizes}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。"""
    parser = argparse.ArgumentParser(description="pytest シャードの被覆検査")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    checks = sub.add_parser("verify", help="全件被覆を検査する")
    checks.add_argument("--suite", required=True)
    checks.add_argument("--require-db", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """サブコマンドを実行する。"""
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        suites = load_suites(root)
        if args.suite not in suites:
            raise ShardError(f"未知のスイート: {args.suite}")
        print(verify(suites[args.suite], root, require_db=args.require_db))
        return 0
    except ShardError as error:
        print(f"pytest_shards: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
