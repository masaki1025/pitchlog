"""census baseline pin の逐行確認シートを実装から機械生成する。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FEATURE_ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = FEATURE_ROOT / "verification-sheet.md"
DECLARATION_PATH = Path("contracts/tenant_boundary/census-baseline.json")
CENSUS_TEST_PATH = Path("tests/test_census_baseline_check.py")
BOUNDARY_TEST_PATH = Path("tests/test_check_tenant_boundary_bypass.py")
DESIGN_PATH = Path("docs/development/dev-harness-design-2026-08-07.md")
PLAN_PATH = Path("docs/features/census-baseline-pin/plan.md")
WORKLOG_PATH = Path("docs/worklog/2026-09-26-census-baseline-pin.md")
FROZEN_HISTORY_PATH = Path("scripts/frozen_history.py")
FROZEN_SCAN_PATH = Path("scripts/check_frozen_baselines.py")
CI_PATH = Path(".github/workflows/ci.yml")
HEX_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:[0-9a-f]{40}|[0-9a-f]{64})\b"
)


@dataclass(frozen=True)
class _Anchor:
    """解決済みのリポジトリ相対 file:line を保持する。"""

    path: Path
    line: int

    @property
    def token(self) -> str:
        """file:line の表示値を返す。"""
        return f"{self.path.as_posix()}:{self.line}"

    def markdown(self) -> str:
        """シートから対象行へ辿れる Markdown link を返す。"""
        relative = os.path.relpath(
            REPOSITORY_ROOT / self.path,
            start=OUTPUT_PATH.parent,
        )
        return f"[`{self.token}`]({Path(relative).as_posix()}#L{self.line})"


@dataclass(frozen=True)
class _Item:
    """単一の逐行確認項目を保持する。"""

    item_id: str
    owner: str
    title: str
    anchors: tuple[_Anchor, ...]
    measured: str
    decision: str


def _run(
    arguments: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """リポジトリルートでコマンドを実行する。"""
    return subprocess.run(
        arguments,
        cwd=REPOSITORY_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _git(arguments: list[str]) -> str:
    """Git コマンドの標準出力を返す。"""
    return _run(["git", *arguments]).stdout.strip()


def _source(path: Path) -> str:
    """リポジトリ相対パスの UTF-8 本文を返す。"""
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8")


def _line_anchor(path: Path, needle: str) -> _Anchor:
    """本文中で一意な文字列を file:line へ解決する。"""
    matches = [
        number
        for number, line in enumerate(_source(path).splitlines(), start=1)
        if needle in line
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"アンカー文字列が一意でない: {path}:{needle!r}: {matches}"
        )
    return _Anchor(path, matches[0])


def _function_anchor(path: Path, function_name: str) -> _Anchor:
    """Python 関数定義を AST から file:line へ解決する。"""
    tree = ast.parse(_source(path), filename=path.as_posix())
    matches = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"関数アンカーが一意でない: {path}:{function_name}: {matches}"
        )
    return _Anchor(path, matches[0])


def _function_source(source: str, function_name: str) -> str:
    """Python 本文から指定関数のソース区間を返す。"""
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"関数本文が一意でない: {function_name}")
    segment = ast.get_source_segment(source, matches[0])
    if segment is None:
        raise RuntimeError(f"関数本文を取得できない: {function_name}")
    return segment


def _assignment_literal(path: Path, name: str) -> Any:
    """Python の module-level 代入を literal として抽出する。"""
    tree = ast.parse(_source(path), filename=path.as_posix())
    matches: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            matches.append(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            matches.append(node.value)
    if len(matches) != 1:
        raise RuntimeError(f"代入が一意でない: {path}:{name}")
    return ast.literal_eval(matches[0])


def _load_declaration() -> dict[str, Any]:
    """census 宣言を JSON object として読む。"""
    value = json.loads(_source(DECLARATION_PATH))
    if not isinstance(value, dict):
        raise RuntimeError("census 宣言が object でない")
    return value


def _collect_census_nodes() -> tuple[str, ...]:
    """census モジュールから pytest node ID を収集する。"""
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            CENSUS_TEST_PATH.as_posix(),
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
    )
    prefix = f"{CENSUS_TEST_PATH.as_posix()}::"
    nodes = tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith(prefix)
    )
    if not nodes:
        raise RuntimeError("census pytest node を収集できない")
    return nodes


def _find_node(nodes: tuple[str, ...], suffix: str) -> str:
    """収集済み node ID を suffix で一意に選ぶ。"""
    matches = [node for node in nodes if node.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"pytest node が一意でない: {suffix}: {matches}")
    return matches[0]


def _find_parameterized_nodes(
    nodes: tuple[str, ...],
    function_name: str,
) -> tuple[str, ...]:
    """指定した parameterized test の全 node ID を収集順で返す。"""
    prefix = f"{CENSUS_TEST_PATH.as_posix()}::{function_name}["
    matches = tuple(node for node in nodes if node.startswith(prefix))
    if not matches:
        raise RuntimeError(f"parameterized pytest node が無い: {function_name}")
    return matches


def _run_evidence_tests(nodes: tuple[str, ...]) -> dict[str, str]:
    """証跡対象の pytest node を実行し、node ごとの結果を返す。"""
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            *nodes,
            "-vv",
            "--tb=no",
            "-p",
            "no:cacheprovider",
        ],
        check=False,
    )
    outcomes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        match = re.match(r"^(tests/\S+::\S+) (PASSED|FAILED|SKIPPED)\b", line)
        if match is not None:
            outcomes[match.group(1)] = match.group(2)
    missing = set(nodes) - set(outcomes)
    if result.returncode != 0 or missing or any(
        outcomes.get(node) != "PASSED" for node in nodes
    ):
        raise RuntimeError(
            "証跡 pytest が全件 PASSED でない\n"
            f"missing={sorted(missing)}\n"
            f"outcomes={outcomes}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    return outcomes


def _materialized_tree_probe(
    declaration: dict[str, Any],
) -> tuple[tuple[str, ...], dict[str, bytes], str]:
    """宣言規則どおり Git tree を再計算する。"""
    anchor = declaration["anchor"]
    tree = declaration["materialized_tree"]
    if not isinstance(anchor, dict) or not isinstance(tree, dict):
        raise RuntimeError("anchor または materialized_tree が object でない")
    commit = anchor["commit"]
    paths = tree["paths"]
    if not isinstance(commit, str) or not isinstance(paths, list) or not all(
        isinstance(path, str) for path in paths
    ):
        raise RuntimeError("materialize 宣言の型が不正")
    listing = _run(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", *paths]
    ).stdout.splitlines()
    relative_paths = tuple(sorted(listing))
    contents: dict[str, bytes] = {}
    rows: list[bytes] = []
    for relative_path in relative_paths:
        content = subprocess.run(
            ["git", "show", f"{commit}:{relative_path}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        contents[relative_path] = content
        content_digest = hashlib.sha256(content).hexdigest()
        rows.append(
            relative_path.encode("utf-8")
            + b"\0"
            + content_digest.encode("ascii")
            + b"\n"
        )
    digest = hashlib.sha256(b"".join(rows)).hexdigest()
    if len(relative_paths) != tree["file_count"] or digest != tree["digest"]:
        raise RuntimeError(
            "Git tree の実測が宣言と不一致: "
            f"files={len(relative_paths)}/{tree['file_count']}, "
            f"digest={digest}/{tree['digest']}"
        )
    return relative_paths, contents, digest


def _accepted_snapshot_probe(
    declaration: dict[str, Any],
    contents: dict[str, bytes],
) -> tuple[str, int, dict[str, str]]:
    """受理記録と materialize 内容の相互検査を再計算する。"""
    cross_check = declaration["acceptance_cross_check"]
    if not isinstance(cross_check, dict):
        raise RuntimeError("acceptance_cross_check が object でない")
    acceptance_id = cross_check["acceptance_id"]
    history_asset = cross_check["history_asset"]
    if not isinstance(acceptance_id, str) or not isinstance(history_asset, str):
        raise RuntimeError("相互検査宣言の型が不正")
    history_value = json.loads(_source(Path(history_asset)))
    history = history_value["baseline_control"]["history"]
    matches = [
        record
        for record in history
        if isinstance(record, dict) and record.get("acceptance_id") == acceptance_id
    ]
    if len(matches) != 1:
        raise RuntimeError(f"相互検査の受理記録が一意でない: {len(matches)}")
    snapshots = {
        snapshot["path"]: snapshot["sha256"]
        for snapshot in matches[0]["change"]["before"]["external_snapshots"]
    }
    verified: dict[str, str] = {}
    for key in ("checker_path", "helper_path"):
        relative_path = cross_check[key]
        digest = hashlib.sha256(contents[relative_path]).hexdigest()
        if snapshots.get(relative_path) != digest:
            raise RuntimeError(f"受理 snapshot と Git 内容が不一致: {relative_path}")
        verified[relative_path] = digest
    return acceptance_id, len(matches), verified


def _isolated_loader_probe() -> tuple[str, str, str, dict[str, str]]:
    """実装の隔離 loader を実行し、root 相対のロード先を返す。"""
    tests_path = str(REPOSITORY_ROOT / "tests")
    previous_path = list(sys.path)
    try:
        sys.path.insert(0, tests_path)
        census = importlib.import_module("test_census_baseline_check")
        with tempfile.TemporaryDirectory(prefix="census-verification-") as directory:
            reference_root = Path(directory) / "reference"
            (
                checker_module,
                returned_root,
                helper_file,
                tree_digest,
                verified_snapshots,
            ) = census._declared_anchor_checker(reference_root)
            checker_file = Path(checker_module.__file__).resolve()
            checker_relative = checker_file.relative_to(returned_root.resolve())
            helper_relative = helper_file.resolve().relative_to(returned_root.resolve())
            return (
                checker_relative.as_posix(),
                helper_relative.as_posix(),
                tree_digest,
                dict(verified_snapshots),
            )
    finally:
        sys.path[:] = previous_path


def _old_comparison_probe() -> tuple[bool, int, int, str]:
    """分岐点の旧 census テストに固定識別値が無かったことを測る。"""
    base_revision = _git(["merge-base", "origin/develop", "HEAD"])
    asset_result = _run(
        ["git", "cat-file", "-e", f"{base_revision}:{DECLARATION_PATH.as_posix()}"],
        check=False,
    )
    old_source = _git(
        ["show", f"{base_revision}:{BOUNDARY_TEST_PATH.as_posix()}"]
    )
    old_function = _function_source(
        old_source,
        "test_checker_census_matches_merge_base",
    )
    fixed_values = len(HEX_VALUE_PATTERN.findall(old_function))
    variable_references = old_function.count("origin/develop")
    mechanism_source = _source(FROZEN_HISTORY_PATH)
    marker_match = re.search(r'else \("([A-Z_]+)",\)', mechanism_source)
    if marker_match is None:
        raise RuntimeError("基準不在 marker を frozen_history.py から抽出できない")
    return asset_result.returncode == 0, fixed_values, variable_references, marker_match.group(1)


def _predicate_summary(predicate: dict[str, Any]) -> str:
    """宣言述語を人間向けの短い拘束説明へ変換する。"""
    predicate_id = predicate["id"]
    if "allowed_codes" in predicate:
        return (
            f"sets={predicate['sets']} の code を allowed_codes="
            f"{predicate['allowed_codes']} に包含"
        )
    if predicate.get("requirement") == "matches_declared_relaxation":
        return (
            f"{predicate['set']} の {predicate['code']} を "
            f"quantifier={predicate['quantifier']} で {predicate['requirement']}"
        )
    if "match_fields" in predicate:
        return (
            f"{predicate['set']} の {predicate['code']} の非裁定要素を "
            f"{predicate['current_set']} の {predicate['required_current_code']} と "
            f"match_fields={predicate['match_fields']}、"
            f"symbol_match={predicate['symbol_match']} で照合"
        )
    if "candidate_enumeration" in predicate:
        enumeration = predicate["candidate_enumeration"]
        return (
            f"{predicate['set']} を relation={predicate['relation']}、"
            f"source={predicate['candidate_source']}、AST={enumeration['ast_node_type']}、"
            f"filters={predicate['filters']} で拘束し、"
            f"derivation={predicate['forbidden_derivation_source']} を禁止"
        )
    if "nonempty_sets" in predicate:
        return f"nonempty_sets={predicate['nonempty_sets']} を要求"
    raise RuntimeError(f"未知の述語形: {predicate_id}")


def _test_evidence(nodes: tuple[str, ...], outcomes: dict[str, str]) -> str:
    """pytest node 群の実測結果を安定した文字列へする。"""
    states = [outcomes[node] for node in nodes]
    return (
        f"pytest={len(nodes)}/{len(nodes)} PASSED; "
        f"nodes={[node.split('::', 1)[1] for node in nodes]}; "
        f"states={states}"
    )


def _test_anchor(node: str) -> _Anchor:
    """pytest node ID をテスト関数の file:line へ解決する。"""
    path_text, test_part = node.split("::", 1)
    function_name = test_part.split("[", 1)[0]
    return _function_anchor(Path(path_text), function_name)


def _build_items() -> tuple[list[_Item], int]:
    """実装・宣言・テスト実測から全判定項目を構築する。"""
    declaration = _load_declaration()
    census_nodes = _collect_census_nodes()
    movement_node = (
        f"{BOUNDARY_TEST_PATH.as_posix()}::"
        "test_census_frozen_surface_mutation_triggers_pass_fail_mapping"
        "[implementation-module]"
    )
    evidence_nodes = (*census_nodes, movement_node)
    outcomes = _run_evidence_tests(evidence_nodes)

    relative_paths, contents, actual_tree_digest = _materialized_tree_probe(declaration)
    acceptance_id, acceptance_matches, verified_snapshots = _accepted_snapshot_probe(
        declaration,
        contents,
    )
    (
        isolated_checker,
        isolated_helper,
        isolated_tree_digest,
        isolated_snapshots,
    ) = _isolated_loader_probe()
    if isolated_tree_digest != actual_tree_digest or isolated_snapshots != verified_snapshots:
        raise RuntimeError("独立再計算と実装 probe の証跡が不一致")

    control = declaration["baseline_control"]
    identity = control["identity"]
    tree = declaration["materialized_tree"]
    predicates = declaration["pass_fail_mapping"]["predicates"]
    if not all(isinstance(predicate, dict) for predicate in predicates):
        raise RuntimeError("pass_fail_mapping.predicates の型が不正")
    source_hex_values = HEX_VALUE_PATTERN.findall(_source(CENSUS_TEST_PATH))
    materialize_source = _function_source(
        _source(CENSUS_TEST_PATH),
        "_materialize_declared_anchor",
    )
    mutable_reference_hits = {
        value: materialize_source.count(value)
        for value in ("origin/develop", "merge-base")
    }
    scan_roots = _assignment_literal(FROZEN_SCAN_PATH, "SCAN_SOURCE_ROOTS")
    external_files = identity["frozen_projection"]["external_files"]
    authority_assets = []
    for asset_path in sorted(
        (REPOSITORY_ROOT / "contracts/tenant_boundary").glob("*.json")
    ):
        asset = json.loads(asset_path.read_text(encoding="utf-8"))
        if asset.get("baseline_control", {}).get("history_authority") is True:
            authority_assets.append(asset_path.relative_to(REPOSITORY_ROOT).as_posix())
    old_asset_exists, old_fixed_values, old_variable_refs, no_baseline_marker = (
        _old_comparison_probe()
    )
    if old_asset_exists or old_fixed_values != 0 or old_variable_refs == 0:
        raise RuntimeError(
            "NO_BASELINE 再裁定の実測前提が成立しない: "
            f"asset_exists={old_asset_exists}, fixed={old_fixed_values}, "
            f"variable_refs={old_variable_refs}"
        )

    predicate_nodes = {
        predicate["id"]: _find_node(
            census_nodes,
            "test_each_declared_census_predicate_rejects_its_input_mutation"
            f"[{predicate['id']}]",
        )
        for predicate in predicates
    }
    candidate_omission_node = _find_node(
        census_nodes,
        "test_independent_added_predicate_rejects_candidate_checker_omission",
    )
    first_review_remediation_nodes = (
        _find_node(
            census_nodes,
            "test_declared_condition2_ast_node_types_match_minimal_cases",
        ),
        _find_node(
            census_nodes,
            "test_declared_unadjudicated_tb002_match_uses_symbol_prefix_relation",
        ),
        *_find_parameterized_nodes(
            census_nodes,
            "test_independent_condition2_candidates_match_checker_for_each_ast_type",
        ),
        _find_node(
            census_nodes,
            "test_removed_tb002_accepts_prefix_related_current_symbol",
        ),
        _find_node(
            census_nodes,
            "test_removed_tb002_rejects_unrelated_same_line_symbol",
        ),
    )
    if len(first_review_remediation_nodes) != 12:
        raise RuntimeError(
            "第1周是正テストの pytest node 数が不一致: "
            f"{len(first_review_remediation_nodes)}"
        )
    identifier_boundary_nodes = _find_parameterized_nodes(
        census_nodes,
        "test_removed_tb002_symbol_relation_honors_identifier_boundary",
    )
    if len(identifier_boundary_nodes) != 3:
        raise RuntimeError(
            "識別子境界テストの pytest node 数が不一致: "
            f"{len(identifier_boundary_nodes)}"
        )
    independent_predicate = next(
        predicate for predicate in predicates if "candidate_enumeration" in predicate
    )
    positive_node = _find_node(
        census_nodes,
        "test_checker_census_matches_declared_anchor",
    )
    fail_closed_nodes = {
        "unreadable": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_unreadable_declaration_and_recovers",
            ),
        ),
        "missing-field": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_declaration_mutation_and_recovers"
                "[missing-required-field]",
            ),
        ),
        "unresolved-anchor": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_declaration_mutation_and_recovers"
                "[unresolved-anchor]",
            ),
        ),
        "tree-digest": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_declaration_mutation_and_recovers"
                "[tree-digest-mismatch]",
            ),
        ),
        "file-count": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_declaration_mutation_and_recovers"
                "[file-count-mismatch]",
            ),
        ),
        "acceptance-record": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_declaration_mutation_and_recovers"
                "[acceptance-record-not-found]",
            ),
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_nonunique_acceptance_record_and_recovers",
            ),
        ),
        "acceptance-digest": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_acceptance_digest_mismatch_and_recovers",
            ),
        ),
        "module-cache": (
            _find_node(
                census_nodes,
                "test_fail_closed_rejects_module_cache_contamination_and_recovers",
            ),
        ),
    }
    regression_nodes = {
        "origin-develop": (
            _find_node(
                census_nodes,
                "test_reference_checker_regressions_are_rejected"
                "[origin-develop-loader]",
            ),
        ),
        "merge-base": (
            _find_node(
                census_nodes,
                "test_reference_checker_regressions_are_rejected"
                "[merge-base-loader]",
            ),
        ),
        "worktree": (
            _find_node(
                census_nodes,
                "test_reference_checker_regressions_are_rejected"
                "[current-worktree-checker]",
            ),
        ),
        "collection-cache": (
            _find_node(
                census_nodes,
                "test_reference_regression_rejects_git_bytes_cached_before_monitoring",
            ),
        ),
    }
    wiring_nodes = {
        "declaration-to-implementation": (
            _find_node(
                census_nodes,
                "test_declaration_to_implementation_rejects_unused_field_and_recovers",
            ),
        ),
        "implementation-to-declaration": (
            _find_node(
                census_nodes,
                "test_implementation_to_declaration_rejects_undeclared_input_and_recovers",
            ),
        ),
    }

    items: list[_Item] = []

    def add(
        item_id: str,
        owner: str,
        title: str,
        anchors: tuple[_Anchor, ...],
        measured: str,
        decision: str,
    ) -> None:
        items.append(_Item(item_id, owner, title, anchors, measured, decision))

    add(
        "A-1",
        "人間",
        "可変参照を census の基準にしない判断",
        (
            _line_anchor(PLAN_PATH, "**原因**: TSK-440 が入れたテストが"),
            _function_anchor(CENSUS_TEST_PATH, "_materialize_declared_anchor"),
        ),
        (
            f"現行 materialize 内の可変参照出現数={mutable_reference_hits}; "
            f"宣言 resolution={declaration['anchor']['resolution']}; "
            f"正例 pytest={outcomes[positive_node]}"
        ),
        "比較元と HEAD が合流後に自己比較になる問題を、固定宣言へ移す判断が妥当か。",
    )
    add(
        "A-2",
        "人間",
        "固定 SHA を Python ソースへ戻せない三経路の遮断",
        (
            _line_anchor(DESIGN_PATH, "2. **直書きの禁止**"),
            _function_anchor(FROZEN_SCAN_PATH, "_scan_python_sources"),
            _function_anchor(
                CENSUS_TEST_PATH,
                "_assert_declaration_implementation_wiring",
            ),
            _function_anchor(
                BOUNDARY_TEST_PATH,
                "test_census_frozen_surface_mutation_triggers_pass_fail_mapping",
            ),
        ),
        (
            f"(1) scan roots={list(scan_roots)}, census source hex hits="
            f"{len(source_hex_values)}; (2) 結線変異="
            f"{_test_evidence(wiring_nodes['implementation-to-declaration'], outcomes)}; "
            f"(3) frozen external_files に census module="
            f"{CENSUS_TEST_PATH.as_posix() in external_files}, movement mutation="
            f"{outcomes[movement_node]}"
        ),
        "走査・宣言外入力拒否・凍結 movement の三経路で直書きへの回帰を十分に防げるか。",
    )
    add(
        "A-3",
        "人間",
        "直前値を NO_BASELINE とする第8周再裁定",
        (
            _line_anchor(WORKLOG_PATH, "**8 周目で判定が反転した。**"),
            _line_anchor(PLAN_PATH, "### ★ 直前値は `NO_BASELINE` で正しい"),
            _line_anchor(FROZEN_HISTORY_PATH, 'else ("NO_BASELINE",)'),
        ),
        (
            f"分岐点で census 資産存在={old_asset_exists}; 旧テスト内の固定40/64 hex="
            f"{old_fixed_values}; 可変参照出現={old_variable_refs}; "
            f"機構の基準不在 marker={no_baseline_marker}"
        ),
        "識別値が置かれていない相対比較を、既存の凍結基準と数えない裁定が7.7-2に適合するか。",
    )
    add(
        "A-4",
        "人間",
        "7.7-1 宣言の外出し",
        (
            _line_anchor(DESIGN_PATH, "**7.7-1 凍結基準の外出し**"),
            _line_anchor(DECLARATION_PATH, '"anchor": {'),
            _function_anchor(CENSUS_TEST_PATH, "_load_census_baseline_declaration"),
        ),
        (
            f"宣言 anchor/resolution={declaration['anchor']}; "
            f"Python source の40/64 hex={len(source_hex_values)}"
        ),
        "基準値を資産宣言だけに置き、実装はロケータとschema keyだけを持つ境界が妥当か。",
    )
    add(
        "A-5",
        "人間",
        "7.7-2 更新記録を最終ステップへ送る手続",
        (
            _line_anchor(DESIGN_PATH, "**7.7-2 更新の記録**"),
            _line_anchor(DECLARATION_PATH, '"history": []'),
            _line_anchor(PLAN_PATH, "| 10 | **7.7-2 の受理記録を authority へ"),
        ),
        (
            f"census history件数={len(control['history'])}; "
            f"history_authority={control['history_authority']}; "
            f"authority assets={authority_assets}; "
            f"acceptance_unit={control['movement_policy']['acceptance_unit']}"
        ),
        "凍結対象が確定するステップ10でauthorityへ1記録を書く順序と受理単位が妥当か。",
    )
    add(
        "A-6",
        "人間",
        "7.7-3 fail-closed の満たし方",
        (
            _line_anchor(DESIGN_PATH, "**7.7-3 fail-closed**"),
            _function_anchor(
                CENSUS_TEST_PATH,
                "test_fail_closed_rejects_unreadable_declaration_and_recovers",
            ),
        ),
        (
            "fail-closed 8分類="
            f"{sum(len(nodes) > 0 for nodes in fail_closed_nodes.values())}/"
            f"{len(fail_closed_nodes)} PASSED; "
            f"pytest nodes={sum(len(nodes) for nodes in fail_closed_nodes.values())}"
        ),
        "確認不能をskip・中立・合格にせず不合格にする境界が十分か。",
    )

    add(
        "B-1",
        "機械",
        "宣言アンカーからの tree materialize と digest 突合",
        (
            _line_anchor(DECLARATION_PATH, '"materialized_tree": {'),
            _function_anchor(CENSUS_TEST_PATH, "_materialize_declared_anchor"),
        ),
        (
            f"anchor={declaration['anchor']['commit']}; paths={tree['paths']}; "
            f"files declared/actual={tree['file_count']}/{len(relative_paths)}; "
            f"digest declared/actual={tree['digest']}/{actual_tree_digest}; "
            "mutations="
            + _test_evidence(
                (
                    *fail_closed_nodes["unresolved-anchor"],
                    *fail_closed_nodes["tree-digest"],
                    *fail_closed_nodes["file-count"],
                ),
                outcomes,
            )
        ),
        "宣言値とGit由来の実測値が一致し、3変異が赤から復元greenになっているか。",
    )
    add(
        "B-2",
        "機械",
        "受理記録の checker・helper snapshot との相互検査",
        (
            _line_anchor(DECLARATION_PATH, '"acceptance_cross_check": {'),
            _function_anchor(
                CENSUS_TEST_PATH,
                "_cross_check_accepted_external_snapshots",
            ),
        ),
        (
            f"acceptance_id={acceptance_id}; matching_records={acceptance_matches}; "
            f"verified_sha256={verified_snapshots}; "
            "mutations="
            + _test_evidence(
                (
                    *fail_closed_nodes["acceptance-record"],
                    *fail_closed_nodes["acceptance-digest"],
                ),
                outcomes,
            )
        ),
        "受理記録が一意で、別経路の2ファイルdigestが一致し、不在・重複・不一致を拒否するか。",
    )
    add(
        "B-3",
        "機械",
        "旧 checker と旧 helper の隔離ロード",
        (
            _function_anchor(CENSUS_TEST_PATH, "_load_isolated_anchor_checker"),
            _function_anchor(
                CENSUS_TEST_PATH,
                "test_fail_closed_rejects_module_cache_contamination_and_recovers",
            ),
        ),
        (
            f"checker=<materialized-root>/{isolated_checker}; "
            f"helper=<materialized-root>/{isolated_helper}; current scripts 使用=False; "
            f"mutation={_test_evidence(fail_closed_nodes['module-cache'], outcomes)}"
        ),
        "両moduleがmaterialize先配下だけからロードされ、cache混入を拒否するか。",
    )

    mapping_key_paths: list[str] = []

    def collect_mapping_keys(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                mapping_key_paths.append(child_path)
                collect_mapping_keys(child, child_path)
        elif isinstance(value, list):
            for child in value:
                collect_mapping_keys(child, f"{path}[]")

    collect_mapping_keys(declaration["pass_fail_mapping"], "pass_fail_mapping")
    count_keys = [path for path in mapping_key_paths if "count" in path.lower()]
    add(
        "C-1",
        "人間",
        "製品コードで動く件数を基準値にしない判断",
        (
            _line_anchor(PLAN_PATH, "### ★ 合否写像は「件数」ではなく「述語」にする"),
            _line_anchor(DECLARATION_PATH, '"pass_fail_mapping": {'),
        ),
        (
            f"declared predicates={len(predicates)}; "
            f"pass_fail_mapping の count 系 key={count_keys}"
        ),
        "現行backend/srcの変化で動く件数を捨て、安定した述語へ置き換える判断が妥当か。",
    )

    handler_names = {
        "difference_codes_within_allowed_set": (
            "_assert_difference_codes_within_allowed_set"
        ),
        "removed_tb007_matches_declared_relaxations": (
            "_assert_removed_matches_declared_relaxations"
        ),
        "unadjudicated_removed_tb002_remains_in_current_census": (
            "_assert_unadjudicated_removed_remains"
        ),
        "added_equals_independently_derived_condition_2_candidates": (
            "_assert_added_equals_independently_derived_candidates"
        ),
        "difference_sets_are_nonempty": "_assert_difference_sets_are_nonempty",
    }
    for index, predicate in enumerate(predicates, start=2):
        predicate_id = predicate["id"]
        predicate_node = predicate_nodes[predicate_id]
        add(
            f"C-{index}",
            "人間",
            f"述語 `{predicate_id}` の拘束",
            (
                _line_anchor(DECLARATION_PATH, f'"id": "{predicate_id}"'),
                _function_anchor(CENSUS_TEST_PATH, handler_names[predicate_id]),
                _test_anchor(predicate_node),
            ),
            (
                f"宣言={_predicate_summary(predicate)}; "
                f"mutation={outcomes[predicate_node]}→正入力復元PASSED"
            ),
            "宣言された拘束が必要十分で、将来の製品コード変更を件数で縛らないか。",
        )
    add(
        "C-7",
        "人間",
        "述語4の右辺を candidate checker から独立させる判断",
        (
            _line_anchor(
                PLAN_PATH,
                "**★ 右辺を現行センサスからフィルタしてはいけない**",
            ),
            _function_anchor(CENSUS_TEST_PATH, "_independently_derived_added"),
            _test_anchor(candidate_omission_node),
        ),
        (
            f"candidate_source={independent_predicate['candidate_source']}; "
            f"forbidden_source={independent_predicate['forbidden_derivation_source']}; "
            f"candidate omission mutation={outcomes[candidate_omission_node]}"
        ),
        "候補checkerの取りこぼしと同時に期待集合まで縮む循環を断てているか。",
    )
    add(
        "C-8",
        "機械",
        "第1周是正の AST 8種・symbol 照合テスト12 node",
        tuple(
            dict.fromkeys(
                _test_anchor(node) for node in first_review_remediation_nodes
            )
        ),
        (
            "declared AST node types="
            f"{independent_predicate['candidate_enumeration']['ast_node_type']}; "
            + _test_evidence(first_review_remediation_nodes, outcomes)
        ),
        "8種の独立候補列挙とsymbol照合の追加テスト12 nodeがすべて実行されているか。",
    )
    unadjudicated_predicate = next(
        predicate for predicate in predicates if "symbol_match" in predicate
    )
    add(
        "C-9",
        "機械",
        "識別子境界付き接頭辞関係の3変異",
        tuple(
            dict.fromkeys(_test_anchor(node) for node in identifier_boundary_nodes)
        ),
        (
            f"declared relation={unadjudicated_predicate['symbol_match']['relation']}; "
            + _test_evidence(identifier_boundary_nodes, outcomes)
        ),
        "属性チェーンを受理し、同名接頭辞の別識別子と無関係な識別子を拒否するか。",
    )

    fail_closed_titles = {
        "unreadable": "① 宣言不在・JSON不正",
        "missing-field": "② 宣言の必須フィールド欠落",
        "unresolved-anchor": "③ アンカー解決不能",
        "tree-digest": "④ tree digest 不一致",
        "file-count": "⑤ materialize ファイル数不一致",
        "acceptance-record": "⑥ 受理記録不在・非一意",
        "acceptance-digest": "⑦ 受理 snapshot digest 不一致",
        "module-cache": "⑧ module-cache 混入",
    }
    for index, (key, title) in enumerate(fail_closed_titles.items(), start=1):
        nodes = fail_closed_nodes[key]
        add(
            f"D-{index:02d}",
            "機械",
            f"fail-closed {title}",
            tuple(dict.fromkeys(_test_anchor(node) for node in nodes)),
            _test_evidence(nodes, outcomes),
            "変異が赤として捕捉され、復元後greenまで到達しているか。",
        )

    regression_titles = {
        "origin-develop": "退行(a) origin/develop loader",
        "merge-base": "退行(b) merge-base loader",
        "worktree": "退行(c) 現行worktree checker",
        "collection-cache": "退行(d) collection時点のGit bytes cache",
    }
    for offset, (key, title) in enumerate(regression_titles.items(), start=9):
        nodes = regression_nodes[key]
        add(
            f"D-{offset:02d}",
            "機械",
            title,
            tuple(_test_anchor(node) for node in nodes),
            _test_evidence(nodes, outcomes),
            "宣言アンカー以外の比較元へ戻す退行が赤になり、正経路へ戻すとgreenか。",
        )

    wiring_titles = {
        "declaration-to-implementation": "結線① 宣言の未使用フィールド",
        "implementation-to-declaration": "結線② 宣言外の実装入力",
    }
    for offset, (key, title) in enumerate(wiring_titles.items(), start=13):
        nodes = wiring_nodes[key]
        add(
            f"D-{offset:02d}",
            "機械",
            title,
            tuple(_test_anchor(node) for node in nodes),
            _test_evidence(nodes, outcomes),
            "宣言と実装の片方向だけを外す変異が赤になり、復元後greenか。",
        )

    return items, len(evidence_nodes)


def _render_sheet(items: list[_Item], pytest_node_count: int) -> str:
    """判定項目を4節の Markdown シートへ変換する。"""
    human_count = sum(item.owner == "人間" for item in items)
    machine_count = sum(item.owner == "機械" for item in items)
    sections = {
        "A": "A. 基準を新設する判断と 7.7 の手続",
        "B": "B. 比較元の組み立て",
        "C": "C. 合否写像を述語にした判断",
        "D": "D. fail-closed と退行の実測",
    }
    lines = [
        "<!-- このファイルは generate_verification_sheet.py が機械生成する。手編集しない。 -->",
        "# census baseline pin 人間逐行確認シート",
        "",
        (
            "生成コマンド: `uv run python "
            "docs/features/census-baseline-pin/generate_verification_sheet.py`"
        ),
        "",
        "## 見る順序",
        "",
        "1. **A** で基準を新設する裁定と 7.7 の適用を判断する。",
        "2. **C** で件数を捨てて述語にした合否写像の十分性を判断する。",
        "3. **B** で宣言アンカーから比較元が一意に組み上がる実測を突合する。",
        "4. **D** で fail-closed・退行・両方向結線の変異がすべて赤になる証跡を確認する。",
        "",
        "## 機械と人間の境界",
        "",
        "- **機械**: 宣言値の再計算と、壊した入力が赤・復元後がgreenになる pytest を実行する。",
        (
            "- **人間**: AとCを中心に、基準の新設・NO_BASELINE・述語の選択が"
            "設計として妥当かを判断する。"
        ),
        (
            "- Cの変異テストは実装どおり動くことを機械確認するが、述語が必要十分かの"
            "最終判断は人間に残す。"
        ),
        "",
        "## 集計",
        "",
        f"- 判定項目総数: **{len(items)}**",
        f"- 機械が担保する項目: **{machine_count}**",
        f"- 人間が判断する項目: **{human_count}**",
        f"- 生成時に実行して全件PASSEDを要求した pytest node: **{pytest_node_count}**",
        "",
    ]
    for section_key, section_title in sections.items():
        lines.extend([f"## {section_title}", ""])
        for item in items:
            if not item.item_id.startswith(f"{section_key}-"):
                continue
            anchors = " / ".join(anchor.markdown() for anchor in item.anchors)
            lines.extend(
                [
                    f"### {item.item_id} [{item.owner}] {item.title}",
                    "",
                    f"- **アンカー**: {anchors}",
                    f"- **実測値**: {item.measured}",
                    f"- **判定観点**: {item.decision}",
                    "- **判定**: ☐ 適合 / ☐ 要修正",
                    "",
                ]
            )
    return "\n".join(lines)


def _validate_sheet(sheet: str, items: list[_Item]) -> int:
    """生成シートの全 item・anchor・checkbox が解決可能か検証する。"""
    item_ids = [item.item_id for item in items]
    if len(item_ids) != len(set(item_ids)):
        raise RuntimeError("判定項目 ID が重複している")
    if {item_id.split("-", 1)[0] for item_id in item_ids} != {"A", "B", "C", "D"}:
        raise RuntimeError("A〜D のいずれかが欠けている")
    if sheet.count("- **判定**: ☐") != len(items):
        raise RuntimeError("判定欄の数が判定項目数と一致しない")
    anchors = [anchor for item in items for anchor in item.anchors]
    for anchor in anchors:
        path = REPOSITORY_ROOT / anchor.path
        lines = path.read_text(encoding="utf-8").splitlines()
        if anchor.line < 1 or anchor.line > len(lines) or not lines[anchor.line - 1]:
            raise RuntimeError(f"アンカーを解決できない: {anchor.token}")
        if f"`{anchor.token}`" not in sheet:
            raise RuntimeError(f"シートにアンカーが無い: {anchor.token}")
    return len(anchors)


def main() -> int:
    """逐行確認シートを生成、または既存シートとの一致を確認する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="生成結果を書かず、既存シートとのbyte一致を検査する",
    )
    args = parser.parse_args()
    items, pytest_node_count = _build_items()
    sheet = _render_sheet(items, pytest_node_count)
    anchor_count = _validate_sheet(sheet, items)
    encoded = sheet.encode("utf-8")
    if args.check:
        if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_bytes() != encoded:
            raise SystemExit("verification-sheet.md が再生成結果と一致しない")
        mode = "check"
    else:
        OUTPUT_PATH.write_bytes(encoded)
        mode = "write"
    human_count = sum(item.owner == "人間" for item in items)
    machine_count = sum(item.owner == "機械" for item in items)
    print(
        f"verification-sheet: {mode} OK: items={len(items)}; "
        f"machine={machine_count}; human={human_count}; anchors={anchor_count}; "
        f"pytest_nodes={pytest_node_count}"
    )
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
