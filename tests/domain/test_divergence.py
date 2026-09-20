"""D-3 のコミット単位乖離検出を合成 Git 履歴で検査する。"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
DIVERGENCE_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/divergence.py"
ADR_PATH = ROOT / "docs/adr/ADR-003-domain-calc-method.md"

sys.path.insert(0, str(BACKEND_SRC))
DIVERGENCE = importlib.import_module("pitchlog.domaincheck.divergence")

GENERATOR_PATH = "backend/src/pitchlog/domaingen/core.py"
SOURCE_A = "backend/domain/model-a.json"
SOURCE_B = "backend/domain/model-b.json"
GENERATED_A_PY = "backend/generated/model-a.py"
GENERATED_A_TS = "frontend/generated/model-a.ts"
GENERATED_B_SQL = "backend/generated/model-b.sql"

BINDING_A = DIVERGENCE.GeneratedBinding(
    "synthetic-a",
    (SOURCE_A,),
    (GENERATED_A_PY, GENERATED_A_TS),
)
BINDING_B = DIVERGENCE.GeneratedBinding(
    "synthetic-b",
    (SOURCE_B,),
    (GENERATED_B_SQL,),
)
MARKER = DIVERGENCE.GeneratorVersionMarker(GENERATOR_PATH)
SPECIFICATION = DIVERGENCE.DivergenceSpecification(
    (BINDING_A, BINDING_B),
    MARKER,
)


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """合成リポジトリで Git を実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def _write(path: Path, content: str) -> None:
    """合成リポジトリのテキストを親ディレクトリごと作る。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _render(
    version: str,
    source_content: str,
    generated_path: str,
) -> str:
    """合成生成器の決定的な出力を返す。"""
    return (
        "# synthetic generated artifact\n"
        f"generator={version}\n"
        f"source={source_content.strip()}\n"
        f"artifact={generated_path}\n"
    )


def _working_version(root: Path) -> str:
    """作業ツリーの合成 generator version を AST から読む。"""
    tree = ast.parse((root / GENERATOR_PATH).read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "GENERATOR_VERSION"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Constant)
    assert isinstance(assignment.value.value, str)
    return assignment.value.value


def _write_generated(root: Path, binding: Any) -> None:
    """現在の正本と version から対応する全生成物を書く。"""
    version = _working_version(root)
    source_content = "".join(
        (root / path).read_text(encoding="utf-8")
        for path in binding.source_paths
    )
    for path in binding.generated_paths:
        _write(root / path, _render(version, source_content, path))


def _regenerate(snapshot: Any, binding: Any) -> dict[str, str]:
    """commit snapshot に既存生成器相当の合成生成器を適用する。"""
    version = snapshot.python_string_constant(MARKER)
    source_content = "".join(
        snapshot.read_text(path) for path in binding.source_paths
    )
    return {
        path: _render(version, source_content, path)
        for path in binding.generated_paths
    }


def _commit(root: Path, message: str) -> str:
    """作業ツリー全体を一つの合成 commit にする。"""
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    """正本二つ・生成物三つ・version 一つを持つ基線を作る。"""
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "divergence-test@example.invalid")
    _git(root, "config", "user.name", "Divergence Test")
    _write(root / GENERATOR_PATH, 'GENERATOR_VERSION = "synthetic-v1"\n')
    _write(root / SOURCE_A, '{"value":"a-v1"}\n')
    _write(root / SOURCE_B, '{"value":"b-v1"}\n')
    _write_generated(root, BINDING_A)
    _write_generated(root, BINDING_B)
    return root, _commit(root, "合成基線")


def _inspect(root: Path, base: str) -> Any:
    """基線から HEAD までをコミット単位で検査する。"""
    return DIVERGENCE.inspect_pr_divergence(
        root=root,
        base_revision=base,
        head_revision="HEAD",
        specification=SPECIFICATION,
        regenerator=_regenerate,
    )


def _kinds(report: Any) -> set[Any]:
    """検出結果に含まれる乖離種別を返す。"""
    return {violation.kind for violation in report.violations}


def test_one_sided_commit_then_later_alignment_fails_even_if_head_matches(
    tmp_path: Path,
) -> None:
    """最終ツリーが一致しても途中の片側 commit を見逃さない。"""
    root, base = _repository(tmp_path)
    _write(root / SOURCE_A, '{"value":"a-v2"}\n')
    source_only_commit = _commit(root, "正本だけを先行")
    _write_generated(root, BINDING_A)
    generated_only_commit = _commit(root, "後続で生成物を整合")

    head = DIVERGENCE.CommitSnapshot(root, generated_only_commit)
    assert all(
        head.read_text(path) == expected
        for path, expected in _regenerate(head, BINDING_A).items()
    )
    report = _inspect(root, base)

    assert report.commits == (source_only_commit, generated_only_commit)
    assert any(
        item.commit_oid == source_only_commit
        and item.kind is DIVERGENCE.DivergenceKind.SOURCE_WITHOUT_GENERATED
        for item in report.violations
    )
    assert any(
        item.commit_oid == generated_only_commit
        and item.kind is DIVERGENCE.DivergenceKind.GENERATED_WITHOUT_SOURCE
        for item in report.violations
    )
    with pytest.raises(DIVERGENCE.DivergenceError, match="コミット単位"):
        DIVERGENCE.require_no_divergence(report)


def test_old_derived_artifacts_fail_despite_paths_being_cochanged(
    tmp_path: Path,
) -> None:
    """正本と生成物のパスを共変更しても古い派生内容を拒否する。"""
    root, base = _repository(tmp_path)
    _write(root / SOURCE_A, '{"value":"a-v2"}\n')
    for path in BINDING_A.generated_paths:
        _write(root / path, f"# stale derived artifact for {path}\n")
    _commit(root, "古い派生物を同居")

    report = _inspect(root, base)

    assert DIVERGENCE.DivergenceKind.SOURCE_WITHOUT_GENERATED not in _kinds(report)
    assert DIVERGENCE.DivergenceKind.STALE_GENERATED in _kinds(report)
    with pytest.raises(DIVERGENCE.DivergenceError):
        DIVERGENCE.require_no_divergence(report)


def test_hand_modified_generated_artifact_fails_individually(
    tmp_path: Path,
) -> None:
    """正本も version も変えない生成物の手修正を拒否する。"""
    root, base = _repository(tmp_path)
    _write(root / GENERATED_A_PY, "# hand modified\n")
    _commit(root, "生成物を手修正")

    report = _inspect(root, base)

    assert DIVERGENCE.DivergenceKind.GENERATED_WITHOUT_SOURCE in _kinds(report)
    assert DIVERGENCE.DivergenceKind.STALE_GENERATED in _kinds(report)
    with pytest.raises(DIVERGENCE.DivergenceError):
        DIVERGENCE.require_no_divergence(report)


def test_backend_domain_only_change_still_activates_check(tmp_path: Path) -> None:
    """backend/domain 配下だけの正本変更でも検査を発火させる。"""
    root, base = _repository(tmp_path)
    _write(root / SOURCE_B, '{"value":"b-v2"}\n')
    commit = _commit(root, "backend domain の正本だけを変更")

    changed = _git(root, "show", "--format=", "--name-only", commit).stdout.splitlines()
    report = _inspect(root, base)

    assert changed == [SOURCE_B]
    assert DIVERGENCE.DivergenceKind.SOURCE_WITHOUT_GENERATED in _kinds(report)
    with pytest.raises(DIVERGENCE.DivergenceError):
        DIVERGENCE.require_no_divergence(report)


def test_generator_version_change_requires_every_generated_artifact(
    tmp_path: Path,
) -> None:
    """version 変更時に一対象だけ再生成しても全生成物条件を満たさない。"""
    root, base = _repository(tmp_path)
    _write(root / GENERATOR_PATH, 'GENERATOR_VERSION = "synthetic-v2"\n')
    _write_generated(root, BINDING_A)
    _commit(root, "version と一部生成物だけを変更")

    report = _inspect(root, base)
    version_violations = [
        item
        for item in report.violations
        if item.kind
        is DIVERGENCE.DivergenceKind.GENERATOR_WITHOUT_ALL_GENERATED
    ]

    assert len(version_violations) == 1
    assert version_violations[0].paths == (GENERATED_B_SQL,)
    with pytest.raises(DIVERGENCE.DivergenceError):
        DIVERGENCE.require_no_divergence(report)


def test_source_and_generated_artifacts_in_same_commit_pass(tmp_path: Path) -> None:
    """正本と当該生成物を同じ commit に入れた通常動作が通る。"""
    root, base = _repository(tmp_path)
    _write(root / SOURCE_A, '{"value":"a-v2"}\n')
    _write_generated(root, BINDING_A)
    commit = _commit(root, "正本と生成物を同時更新")

    report = _inspect(root, base)

    assert report.commits == (commit,)
    assert report.conforming
    DIVERGENCE.require_no_divergence(report)


def test_generator_version_and_all_generated_artifacts_in_same_commit_pass(
    tmp_path: Path,
) -> None:
    """version と全生成物を同じ commit に入れた全面再生成が通る。"""
    root, base = _repository(tmp_path)
    _write(root / GENERATOR_PATH, 'GENERATOR_VERSION = "synthetic-v2"\n')
    _write_generated(root, BINDING_A)
    _write_generated(root, BINDING_B)
    _commit(root, "version と全生成物を同時更新")

    report = _inspect(root, base)

    assert report.conforming
    DIVERGENCE.require_no_divergence(report)


def test_git_execution_reuses_seal_boundary_and_closed_subcommands() -> None:
    """Git 実行を再実装せず seal の閉じた履歴コマンドだけを使う。"""
    source = DIVERGENCE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "pitchlog.domaincheck.seal"
    ]
    git_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_checked_git"
    ]
    subcommands = {
        call.args[1].value
        for call in git_calls
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant)
    }

    assert len(imports) == 1
    assert {alias.name for alias in imports[0].names} == {"_run_git"}
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            any(alias.name == "subprocess" for alias in node.names)
            if isinstance(node, ast.Import)
            else node.module == "subprocess"
        )
        for node in ast.walk(tree)
    )
    assert subcommands == {"rev-parse", "log", "show"}


def test_d3_authority_wording_exists() -> None:
    """D-3 の同一 commit 要求の逐語が条項内に実在する。"""
    adr = ADR_PATH.read_text(encoding="utf-8")
    start = adr.index("### D-3: 正本の版と生成物の同期規則")
    end = adr.index("### D-4:", start)
    section = adr[start:end]

    assert "生成物の再生成を同一コミットに含める" in section
    assert "全生成物を再生成する" in section
