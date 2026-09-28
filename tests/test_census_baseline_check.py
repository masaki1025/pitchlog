"""テナント境界迂回検査のセンサス差分を検証する。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from test_check_tenant_boundary_bypass import (
    EXPECTED_CONDITION_2_ADJUDICATIONS,
    REPOSITORY_ROOT,
    checker,
)

CENSUS_BASELINE_PATH = (
    REPOSITORY_ROOT / "contracts" / "tenant_boundary" / "census-baseline.json"
)
CensusIdentity = tuple[str, int, int, str, str, str, str]


def _object(value: object, location: str) -> dict[str, Any]:
    """宣言値を JSON object として取得する。"""
    assert isinstance(value, dict), f"{location}: object が必要"
    return value


def _string(value: object, location: str) -> str:
    """宣言値を空でない文字列として取得する。"""
    assert isinstance(value, str) and value, f"{location}: 空でない文字列が必要"
    return value


def _string_array(value: object, location: str) -> tuple[str, ...]:
    """宣言値を空でない文字列配列として取得する。"""
    assert isinstance(value, list) and value, f"{location}: 空でない配列が必要"
    assert all(isinstance(item, str) and item for item in value), (
        f"{location}: 空でない文字列だけが必要"
    )
    return tuple(value)


def _load_census_baseline_declaration() -> dict[str, Any]:
    """census の固定比較元宣言を読む。"""
    value = json.loads(CENSUS_BASELINE_PATH.read_text(encoding="utf-8"))
    return _object(value, CENSUS_BASELINE_PATH.as_posix())


def _materialize_declared_anchor(
    destination: Path,
) -> tuple[dict[str, Any], dict[str, bytes], str]:
    """宣言アンカーの対象ファイルを展開し、ツリー digest を突合する。"""
    declaration = _load_census_baseline_declaration()
    anchor = _object(declaration.get("anchor"), "census.anchor")
    anchor_commit = _string(anchor.get("commit"), "census.anchor.commit")
    assert anchor.get("resolution") == "direct_full_commit_sha"
    assert len(anchor_commit) == 40

    tree = _object(declaration.get("materialized_tree"), "census.materialized_tree")
    assert tree.get("digest_algorithm") == "sha256"
    expected_digest = _string(tree.get("digest"), "census.materialized_tree.digest")
    assert len(expected_digest) == 64
    expected_file_count = tree.get("file_count")
    assert isinstance(expected_file_count, int) and expected_file_count > 0
    paths = _string_array(tree.get("paths"), "census.materialized_tree.paths")
    assert tree.get("path_enumeration") == "git_ls_tree_recursive_names"
    assert tree.get("path_order") == "lexicographic_ascending"
    assert tree.get("entry_encoding") == (
        "relative_path + NUL + lowercase_content_sha256 + LF"
    )

    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", anchor_commit, "--", *paths],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    relative_paths = tuple(sorted(result.stdout.splitlines()))
    assert len(relative_paths) == expected_file_count
    assert len(relative_paths) == len(set(relative_paths))

    destination.mkdir(parents=True)
    contents: dict[str, bytes] = {}
    digest_rows: list[bytes] = []
    for relative_path in relative_paths:
        path = Path(relative_path)
        assert not path.is_absolute() and ".." not in path.parts
        content = subprocess.run(
            ["git", "show", f"{anchor_commit}:{relative_path}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        contents[relative_path] = content
        content_digest = hashlib.sha256(content).hexdigest()
        digest_rows.append(
            relative_path.encode("utf-8")
            + b"\0"
            + content_digest.encode("ascii")
            + b"\n"
        )

    actual_digest = hashlib.sha256(b"".join(digest_rows)).hexdigest()
    assert actual_digest == expected_digest
    return declaration, contents, actual_digest


def _cross_check_accepted_external_snapshots(
    declaration: dict[str, Any],
    materialized_contents: dict[str, bytes],
) -> dict[str, str]:
    """受理記録とアンカー由来 checker・helper の digest を相互検査する。"""
    cross_check = _object(
        declaration.get("acceptance_cross_check"),
        "census.acceptance_cross_check",
    )
    assert cross_check.get("requirement") == (
        "accepted_external_snapshot_sha256_equals_materialized_git_content_sha256"
    )
    acceptance_id = _string(
        cross_check.get("acceptance_id"),
        "census.acceptance_cross_check.acceptance_id",
    )
    history_asset = _string(
        cross_check.get("history_asset"),
        "census.acceptance_cross_check.history_asset",
    )
    checker_path = _string(
        cross_check.get("checker_path"),
        "census.acceptance_cross_check.checker_path",
    )
    helper_path = _string(
        cross_check.get("helper_path"),
        "census.acceptance_cross_check.helper_path",
    )
    history_asset_path = REPOSITORY_ROOT / history_asset
    history_asset_value = _object(
        json.loads(history_asset_path.read_text(encoding="utf-8")),
        history_asset,
    )
    control = _object(history_asset_value.get("baseline_control"), "history.control")
    history = control.get("history")
    assert isinstance(history, list)
    matching_records = [
        _object(record, "history.record")
        for record in history
        if isinstance(record, dict) and record.get("acceptance_id") == acceptance_id
    ]
    assert len(matching_records) == 1
    change = _object(matching_records[0].get("change"), "history.record.change")
    before = _object(change.get("before"), "history.record.change.before")
    raw_snapshots = before.get("external_snapshots")
    assert isinstance(raw_snapshots, list)
    snapshots = {
        _string(snapshot.get("path"), "history.external_snapshot.path"): _string(
            snapshot.get("sha256"),
            "history.external_snapshot.sha256",
        )
        for raw_snapshot in raw_snapshots
        if isinstance(raw_snapshot, dict)
        for snapshot in [_object(raw_snapshot, "history.external_snapshot")]
    }
    assert len(snapshots) == len(raw_snapshots)

    verified: dict[str, str] = {}
    for relative_path in (checker_path, helper_path):
        assert relative_path in materialized_contents
        actual_digest = hashlib.sha256(
            materialized_contents[relative_path]
        ).hexdigest()
        assert snapshots.get(relative_path) == actual_digest
        verified[relative_path] = actual_digest
    return verified


def _load_isolated_anchor_checker(
    reference_root: Path,
    declaration: dict[str, Any],
) -> tuple[ModuleType, Path]:
    """materialize 済みの旧 checker と helper を import 状態から隔離して読む。"""
    cross_check = _object(
        declaration.get("acceptance_cross_check"),
        "census.acceptance_cross_check",
    )
    checker_path = reference_root / _string(
        cross_check.get("checker_path"),
        "census.acceptance_cross_check.checker_path",
    )
    helper_path = (
        reference_root
        / _string(
            cross_check.get("helper_path"),
            "census.acceptance_cross_check.helper_path",
        )
    ).resolve()
    scripts_directory = checker_path.resolve().parent
    previous_path = list(sys.path)
    previous_modules = dict(sys.modules)
    try:
        sys.path.insert(0, str(scripts_directory))
        sys.modules.pop("frozen_history", None)
        module_name = "check_tenant_boundary_bypass_declared_anchor"
        spec = importlib.util.spec_from_file_location(module_name, checker_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        loaded_helper = sys.modules.get("frozen_history")
        assert loaded_helper is not None
        loaded_helper_file = Path(
            _string(getattr(loaded_helper, "__file__", None), "frozen_history.__file__")
        ).resolve()
        assert loaded_helper_file == helper_path
        assert loaded_helper_file.is_relative_to(reference_root.resolve())
        assert Path(_string(module.__file__, "checker.__file__")).resolve().is_relative_to(
            reference_root.resolve()
        )
        return module, loaded_helper_file
    finally:
        sys.path[:] = previous_path
        sys.modules.clear()
        sys.modules.update(previous_modules)


def _declared_anchor_checker(
    reference_root: Path,
) -> tuple[ModuleType, Path, Path, str, dict[str, str]]:
    """宣言の検査を完了した比較元 checker と検証証跡を返す。"""
    declaration, contents, tree_digest = _materialize_declared_anchor(
        reference_root
    )
    verified_snapshots = _cross_check_accepted_external_snapshots(
        declaration,
        contents,
    )
    baseline_checker, helper_file = _load_isolated_anchor_checker(
        reference_root,
        declaration,
    )
    return (
        baseline_checker,
        reference_root,
        helper_file,
        tree_digest,
        verified_snapshots,
    )


def _checker_census(
    checker_module: ModuleType,
    *,
    repository_root: Path,
    source_root: Path,
) -> frozenset[CensusIdentity]:
    """検査器の全文走査結果を比較用の exact-set にする。"""
    contract = checker_module.load_contract(repository_root)
    violations = checker_module.scan_directory(source_root, contract=contract)
    return frozenset(
        (
            violation.path,
            violation.line,
            violation.end_line,
            violation.scope,
            violation.code,
            violation.symbol,
            violation.message,
        )
        for violation in violations
    )


def _compare_checker_census(
    reference_checker: ModuleType,
    candidate_checker: ModuleType,
    *,
    repository_root: Path,
    source_root: Path,
    reference_repository_root: Path | None = None,
) -> tuple[frozenset[CensusIdentity], frozenset[CensusIdentity]]:
    """宣言アンカー版から作業ツリー版への違反集合の増減を返す。

    この比較が証明するのは、両版が ``source_root`` にある現在の
    ``backend/src`` へ出す違反集合が同じこと、またはその差が期待どおりであること。
    現在のツリーに存在しない構文やコードへの挙動は証明せず、将来のコードは覆わない。
    """
    reference = _checker_census(
        reference_checker,
        repository_root=reference_repository_root or repository_root,
        source_root=source_root,
    )
    candidate = _checker_census(
        candidate_checker,
        repository_root=repository_root,
        source_root=source_root,
    )
    return candidate - reference, reference - candidate


def _assert_removed_tb007_matches_declared_relaxations(
    removed: frozenset[CensusIdentity],
) -> None:
    """減分が (iii) の宣言範囲への緩和だけで説明できると示す。"""
    source_root = REPOSITORY_ROOT / "backend" / "src"
    sources = {
        path.relative_to(source_root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    }
    reexport_map = checker._build_reexport_map(sources)
    contract = checker.load_contract(REPOSITORY_ROOT)
    scanners: dict[str, tuple[ast.Module, Any]] = {}

    for identity in removed:
        path, line, end_line, _, code, symbol, _ = identity
        assert code == "TB007"
        if path not in scanners:
            tree = ast.parse(sources[path], filename=path)
            scanner = checker._SourceScanner(
                path=path,
                module=checker._module_name(path),
                tree=tree,
                changed_lines=None,
                contract=contract,
                reject_all_db_calls=False,
                reexport_map=reexport_map,
            )
            scanner.visit(tree)
            scanner._validate_call_coverage(tree)
            scanners[path] = (tree, scanner)
        tree, scanner = scanners[path]

        matching_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if node.lineno != line or node.end_lineno != end_line:
                continue
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
            if symbol == "<unresolved-callable>" or symbol == resolved:
                matching_calls.append(node)

        assert matching_calls, identity
        explanations = []
        for node in matching_calls:
            if (
                isinstance(node.func, ast.Name)
                and id(node.func) in scanner.lexically_bound_name_ids
            ):
                explanations.append(node)
                continue
            constructor_name = contract.tenant_context.constructor_symbol.rsplit(
                ".", 1
            )[-1]
            callable_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if callable_name == constructor_name:
                continue
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
            reexport = scanner._reexport_resolution(node.func, resolved)
            if reexport is not None and (
                reexport.unresolved
                or contract.tenant_context.constructor_symbol in reexport.origins
            ):
                continue
            known_callable = scanner.flow.callable_symbol(node)
            if (
                known_callable is not None
                and known_callable
                != contract.tenant_context.constructor_symbol
            ):
                explanations.append(node)
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and known_callable is None
            ):
                explanations.append(node)
                continue
            alias_resolved = scanner.aliases.resolve(node.func)
            known_alias_callable = (
                scanner.aliases.resolve_known(node.func)
                if isinstance(node.func, ast.Name) and alias_resolved is not None
                else None
            )
            if (
                known_alias_callable is not None
                and scanner.aliases.canonical(known_alias_callable)
                != contract.tenant_context.constructor_symbol
                and known_callable is None
            ):
                explanations.append(node)

        assert explanations, identity


def test_checker_census_matches_declared_anchor(tmp_path: Path) -> None:
    """現行検査器と宣言アンカーを比べ、現行全文の差分を TB002・TB007 に拘束する。

    現行の検査器が、宣言されたアンカー時点の検査器と比べて、現行
    ``backend/src`` 全文に対する違反センサスの差分を対象コード内に収める。
    """
    (
        baseline_checker,
        reference_repository_root,
        _,
        _,
        _,
    ) = _declared_anchor_checker(
        tmp_path / "declared_anchor_repository",
    )

    added, removed = _compare_checker_census(
        baseline_checker,
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=REPOSITORY_ROOT / "backend" / "src",
        reference_repository_root=reference_repository_root,
    )

    assert added
    assert {identity[4] for identity in added} <= {"TB002", "TB007"}
    assert removed
    assert {identity[4] for identity in removed} <= {"TB002", "TB007"}
    removed_tb007 = frozenset(
        identity for identity in removed if identity[4] == "TB007"
    )
    assert removed_tb007
    _assert_removed_tb007_matches_declared_relaxations(removed_tb007)
    adjudicated_symbols = set(EXPECTED_CONDITION_2_ADJUDICATIONS)
    adjudicated_names = {
        symbol.rsplit(".", 1)[-1] for symbol in adjudicated_symbols
    }
    current_census = _checker_census(
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=REPOSITORY_ROOT / "backend" / "src",
    )
    for identity in removed:
        if identity[4] != "TB002" or identity[5] in (
            adjudicated_symbols | adjudicated_names
        ):
            continue
        assert any(
            current[0] == identity[0]
            and current[1] == identity[1]
            and current[4] == "TB002"
            for current in current_census
        )
