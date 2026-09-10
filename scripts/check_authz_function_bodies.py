"""認可関数 body の manifest、Git blob、要素 ID、判定注記を静的照合する。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

try:
    from check_authz_catalog import git_blob_digest
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読む場合だけ通る。
    from scripts.check_authz_catalog import git_blob_digest


BODY_DIRECTORY = PurePosixPath("contracts/authz/function-bodies")
MANIFEST_PATH = BODY_DIRECTORY / "manifest.json"
DDL_ELEMENTS_PATH = PurePosixPath("contracts/authz/ddl-elements.json")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
BLOB_DIGEST_RE = re.compile(r"^[0-9a-f]{40}$")
DECISION_RE = re.compile(r"^[ \t]*-- DECISION: ([A-Z0-9_-]+)$")
ELEMENT_TYPE_RE = re.compile(r"^-- ELEMENT-TYPE: ([a-z_]+)$", re.MULTILINE)
ELEMENT_ID_RE = re.compile(r"^-- ELEMENT-ID: (.+)$", re.MULTILINE)
ELEMENT_SECTIONS = {
    "role": ("roles", "role_id"),
    "schema": ("schemas", "schema_id"),
    "table": ("tables", "table_id"),
    "predicate": ("predicates", "predicate_id"),
    "policy": ("policies", "policy_id"),
    "function": ("functions", "function_id"),
    "acl_expectation": ("acl_expectations", "acl_id"),
    "column_acl_expectation": (
        "column_acl_expectations",
        "expectation_id",
    ),
}


class FunctionBodyCheckError(Exception):
    """検査を開始できない入力不正を表す。"""


@dataclass(frozen=True)
class ManifestEntry:
    """manifest の body 1 件を表す。"""

    path: str
    blob_digest: str
    element_type: str
    element_id: str


def _read_bytes(path: Path, label: str) -> bytes:
    """ファイルを生バイト列で読む。"""
    try:
        return path.read_bytes()
    except OSError as error:
        raise FunctionBodyCheckError(f"{label}を読めない: {path}: {error}") from error


def _read_text(path: Path, label: str) -> str:
    """UTF-8 ファイルを読む。"""
    data = _read_bytes(path, label)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FunctionBodyCheckError(f"{label}がUTF-8でない: {path}: {error}") from error


def _read_json(path: Path, label: str) -> object:
    """JSON ファイルを読む。"""
    try:
        return json.loads(_read_text(path, label))
    except json.JSONDecodeError as error:
        raise FunctionBodyCheckError(f"{label}がJSONでない: {path}: {error}") from error


def _expect_object(value: object, label: str) -> dict[str, object]:
    """値が JSON object であることを検査する。"""
    if not isinstance(value, dict):
        raise FunctionBodyCheckError(f"{label}はobjectでなければならない")
    if not all(isinstance(key, str) for key in value):
        raise FunctionBodyCheckError(f"{label}のkeyは文字列でなければならない")
    return value


def _expect_list(value: object, label: str) -> list[object]:
    """値が JSON array であることを検査する。"""
    if not isinstance(value, list):
        raise FunctionBodyCheckError(f"{label}はarrayでなければならない")
    return value


def _expect_string(value: object, label: str) -> str:
    """値が空でない文字列であることを検査する。"""
    if not isinstance(value, str) or not value:
        raise FunctionBodyCheckError(f"{label}は空でない文字列でなければならない")
    return value


def _expect_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    """JSON object のkey集合を完全照合する。"""
    if set(value) != expected:
        raise FunctionBodyCheckError(f"{label}のkey集合が不正")


def _validate_relative_path(path_text: str, root: Path, label: str) -> None:
    """manifest のパスが body ディレクトリ内の正規相対パスか検査する。"""
    pure_path = PurePosixPath(path_text)
    if pure_path.is_absolute() or pure_path.as_posix() != path_text:
        raise FunctionBodyCheckError(f"{label}が正規相対パスでない")
    if any(part in {"", ".", ".."} for part in pure_path.parts):
        raise FunctionBodyCheckError(f"{label}に不正なパス要素がある")
    try:
        pure_path.relative_to(BODY_DIRECTORY)
    except ValueError as error:
        raise FunctionBodyCheckError(f"{label}がbodyディレクトリ外を指す") from error
    resolved = (root / path_text).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise FunctionBodyCheckError(f"{label}がリポジトリ外を指す") from error


def _parse_manifest(raw: object, root: Path) -> tuple[str, tuple[ManifestEntry, ...]]:
    """manifest を厳密に解釈する。"""
    manifest = _expect_object(raw, "body manifest")
    _expect_keys(
        manifest,
        {"schema_version", "asset_kind", "source_commit", "entries"},
        "body manifest",
    )
    if (
        manifest["schema_version"] != 1
        or manifest["asset_kind"] != "authz_function_body_manifest"
    ):
        raise FunctionBodyCheckError(
            "body manifestのschema_versionまたはasset_kindが不正"
        )
    source_commit = _expect_string(
        manifest["source_commit"], "body manifest.source_commit"
    )
    if not COMMIT_RE.fullmatch(source_commit):
        raise FunctionBodyCheckError("body manifest.source_commitがcommit SHAでない")

    entries: list[ManifestEntry] = []
    for index, raw_entry in enumerate(
        _expect_list(manifest["entries"], "body manifest.entries")
    ):
        label = f"body manifest.entries[{index}]"
        entry = _expect_object(raw_entry, label)
        _expect_keys(
            entry,
            {"path", "blob_digest", "element_type", "element_id"},
            label,
        )
        path_text = _expect_string(entry["path"], f"{label}.path")
        _validate_relative_path(path_text, root, f"{label}.path")
        digest = _expect_string(entry["blob_digest"], f"{label}.blob_digest")
        if not BLOB_DIGEST_RE.fullmatch(digest):
            raise FunctionBodyCheckError(f"{label}.blob_digestがblob SHA-1でない")
        element_type = _expect_string(entry["element_type"], f"{label}.element_type")
        element_id = _expect_string(entry["element_id"], f"{label}.element_id")
        entries.append(
            ManifestEntry(
                path=path_text,
                blob_digest=digest,
                element_type=element_type,
                element_id=element_id,
            )
        )
    return source_commit, tuple(entries)


def _expected_elements(raw: object) -> set[tuple[str, str]]:
    """DDL 要素資産から種別とIDの期待集合を導出する。"""
    ddl_elements = _expect_object(raw, "ddl-elements")
    expected: set[tuple[str, str]] = set()
    for element_type, (section_name, id_field) in ELEMENT_SECTIONS.items():
        rows = _expect_list(ddl_elements.get(section_name), f"ddl-elements.{section_name}")
        for index, raw_row in enumerate(rows):
            label = f"ddl-elements.{section_name}[{index}]"
            row = _expect_object(raw_row, label)
            element_id = _expect_string(row.get(id_field), f"{label}.{id_field}")
            key = (element_type, element_id)
            if key in expected:
                raise FunctionBodyCheckError(f"ddl-elementsの要素IDが重複: {key}")
            expected.add(key)
    return expected


def _actual_body_paths(root: Path) -> set[str]:
    """manifest 自身を除く現bodyファイル集合を再帰採取する。"""
    body_root = root / BODY_DIRECTORY
    if not body_root.is_dir():
        raise FunctionBodyCheckError(f"bodyディレクトリがない: {body_root}")
    manifest_path = (root / MANIFEST_PATH).resolve()
    paths: set[str] = set()
    for path in body_root.rglob("*"):
        if path.is_symlink():
            raise FunctionBodyCheckError(f"body配下にsymlinkがある: {path}")
        if path.is_file() and path.resolve() != manifest_path:
            paths.add(path.relative_to(root).as_posix())
    return paths


def _run_git(root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """指定した引数でGitを非shell実行する。"""
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise FunctionBodyCheckError(f"gitを実行できない: {error}") from error


def _format_paths(paths: set[str]) -> str:
    """パス集合を安定順の表示文字列にする。"""
    return ", ".join(sorted(paths)) or "(なし)"


def _format_elements(elements: set[tuple[str, str]]) -> str:
    """要素集合を安定順の表示文字列にする。"""
    return ", ".join(f"{kind}:{element_id}" for kind, element_id in sorted(elements))


def _validate_decisions(root: Path, actual_paths: set[str]) -> list[str]:
    """全bodyの判定注記について構文とID一意性を検査する。"""
    findings: list[str] = []
    locations: defaultdict[str, list[str]] = defaultdict(list)
    for path_text in sorted(actual_paths):
        text = _read_text(root / path_text, path_text)
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "-- DECISION:" not in line:
                continue
            match = DECISION_RE.fullmatch(line)
            if line.count("-- DECISION:") != 1 or match is None:
                findings.append(f"{path_text}:{line_number}: DECISION注記の構文が不正")
                continue
            locations[match.group(1)].append(f"{path_text}:{line_number}")
    for decision_id, decision_locations in sorted(locations.items()):
        if len(decision_locations) > 1:
            findings.append(
                f"DECISION IDが重複: {decision_id}: {', '.join(decision_locations)}"
            )
    return findings


def validate_repository(root: Path) -> tuple[str, ...]:
    """リポジトリのbody manifestと静的契約を検査する。"""
    root = root.resolve()
    if not root.is_dir():
        raise FunctionBodyCheckError(f"リポジトリルートがない: {root}")
    manifest_raw = _read_json(root / MANIFEST_PATH, "body manifest")
    ddl_raw = _read_json(root / DDL_ELEMENTS_PATH, "ddl-elements")
    source_commit, entries = _parse_manifest(manifest_raw, root)
    expected_elements = _expected_elements(ddl_raw)
    actual_paths = _actual_body_paths(root)
    findings: list[str] = []

    commit_result = _run_git(
        root,
        ["rev-parse", "--verify", f"{source_commit}^{{commit}}"],
    )
    if commit_result.returncode != 0:
        raise FunctionBodyCheckError(f"source_commitを解決できない: {source_commit}")

    path_counts = Counter(entry.path for entry in entries)
    for path_text, count in sorted(path_counts.items()):
        if count > 1:
            findings.append(f"manifest pathが重複: {path_text}")
    manifest_paths = set(path_counts)
    manifest_relative_path = MANIFEST_PATH.as_posix()
    if manifest_relative_path in manifest_paths:
        findings.append("manifest.json自身をentriesに含めている")
    missing_paths = actual_paths - manifest_paths
    extra_paths = manifest_paths - actual_paths
    if missing_paths or extra_paths:
        findings.append(
            "bodyファイル被覆がexact-set不一致: "
            f"不足={_format_paths(missing_paths)}; 余分={_format_paths(extra_paths)}"
        )

    element_counts = Counter(
        (entry.element_type, entry.element_id) for entry in entries
    )
    for element, count in sorted(element_counts.items()):
        if count > 1:
            findings.append(f"manifest要素が重複: {_format_elements({element})}")
    manifest_elements = set(element_counts)
    missing_elements = expected_elements - manifest_elements
    extra_elements = manifest_elements - expected_elements
    if missing_elements or extra_elements:
        findings.append(
            "DDL要素被覆がexact-set不一致: "
            f"不足={_format_elements(missing_elements)}; "
            f"余分={_format_elements(extra_elements)}"
        )

    for entry in entries:
        path = root / entry.path
        if not path.is_file():
            findings.append(f"{entry.path}: 現bodyファイルがない")
        else:
            data = _read_bytes(path, entry.path)
            if git_blob_digest(data) != entry.blob_digest:
                findings.append(f"{entry.path}: 現bodyのblob digestが不一致")
            text = _read_text(path, entry.path)
            element_types = ELEMENT_TYPE_RE.findall(text)
            element_ids = ELEMENT_ID_RE.findall(text)
            if len(element_types) != 1 or len(element_ids) != 1:
                findings.append(f"{entry.path}: ELEMENTヘッダーが1組でない")
            elif (element_types[0], element_ids[0]) != (
                entry.element_type,
                entry.element_id,
            ):
                findings.append(f"{entry.path}: ELEMENTヘッダーがmanifestと不一致")

        revision_result = _run_git(
            root,
            ["rev-parse", f"{source_commit}:{entry.path}"],
        )
        if revision_result.returncode != 0:
            findings.append(f"{entry.path}: source_commit上のblobを解決できない")
        elif revision_result.stdout.strip() != entry.blob_digest:
            findings.append(f"{entry.path}: source_commit上のblob digestが不一致")

    findings.extend(_validate_decisions(root, actual_paths))
    return tuple(findings)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。"""
    parser = argparse.ArgumentParser(description="認可関数bodyを静的照合する")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="リポジトリルート")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """静的照合を実行して終了コードを返す。"""
    try:
        args = parse_args(argv)
        findings = validate_repository(args.root)
    except FunctionBodyCheckError as error:
        print(f"authz-function-bodies: 入力不正: {error}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(f"authz-function-bodies: 違反: {finding}", file=sys.stderr)
        return 1
    print("authz-function-bodies: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
