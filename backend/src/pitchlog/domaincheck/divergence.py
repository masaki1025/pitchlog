"""PR 内の各コミットで正本と生成物の乖離を検出する。

`ADR-003 D-3 同一コミット` と `NFR-018 (b)① 乖離検出` に従い、
最終ツリーだけでなく比較元より後の各コミットを検査する。Git の実行は
`pitchlog.domaincheck.seal` の既存境界へ委ね、生成内容は呼び出し側が既存の
`domaingen` を接続する再生成器へ委ねる。
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from pitchlog.domaincheck.seal import _run_git


class DivergenceError(Exception):
    """コミット単位の同期規則に適合しないことを表す。"""


class DivergenceInspectionError(Exception):
    """履歴または再生成結果を機械判定できないことを表す。"""


class DivergenceKind(StrEnum):
    """コミット単位で検出する乖離の閉じた集合。"""

    SOURCE_WITHOUT_GENERATED = "source-without-generated"
    GENERATOR_WITHOUT_ALL_GENERATED = "generator-without-all-generated"
    GENERATED_WITHOUT_SOURCE = "generated-without-source"
    STALE_GENERATED = "stale-generated"


def _repository_relative(path: str, label: str) -> str:
    """リポジトリ相対の正規化済みファイルパスを返す。"""
    candidate = PurePosixPath(path)
    if (
        not path
        or candidate.is_absolute()
        or ".." in candidate.parts
        or path != candidate.as_posix()
        or path.endswith("/")
    ):
        raise ValueError(f"{label} が正規化済み相対ファイルパスでない: {path}")
    return path


@dataclass(frozen=True, slots=True)
class GeneratedBinding:
    """正本の入力群とそこから生じる全生成物の対応。

    Attributes:
        binding_id: 対応を一意に識別する ID。
        source_paths: この対応の正本入力パス。
        generated_paths: 正本から再生成すべき生成物パス。
    """

    binding_id: str
    source_paths: tuple[str, ...]
    generated_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        """空・重複・不正パスを拒否する。"""
        if not self.binding_id:
            raise ValueError("binding ID が空")
        if not self.source_paths or not self.generated_paths:
            raise ValueError("正本または生成物のパス集合が空")
        for label, paths in (
            ("source", self.source_paths),
            ("generated", self.generated_paths),
        ):
            if len(paths) != len(set(paths)):
                raise ValueError(f"{label} path が重複")
            for path in paths:
                _repository_relative(path, f"{label} path")


@dataclass(frozen=True, slots=True)
class GeneratorVersionMarker:
    """生成器 version を持つ Python 定数の位置。"""

    path: str
    symbol: str = "GENERATOR_VERSION"

    def __post_init__(self) -> None:
        """生成器 version のパスと定数名を検査する。"""
        _repository_relative(self.path, "generator version path")
        if not self.symbol.isidentifier():
            raise ValueError("generator version symbol が識別子でない")


@dataclass(frozen=True, slots=True)
class DivergenceSpecification:
    """検査対象の正本・全生成物・version 定数を固定する。"""

    bindings: tuple[GeneratedBinding, ...]
    generator_version: GeneratorVersionMarker

    def __post_init__(self) -> None:
        """対応の母集合を空にせず、パス帰属を一意にする。"""
        if not self.bindings:
            raise ValueError("生成物対応が空")
        binding_ids = [binding.binding_id for binding in self.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("binding ID が重複")
        source_paths = [
            path for binding in self.bindings for path in binding.source_paths
        ]
        generated_paths = [
            path for binding in self.bindings for path in binding.generated_paths
        ]
        if len(source_paths) != len(set(source_paths)):
            raise ValueError("source path の帰属が重複")
        if len(generated_paths) != len(set(generated_paths)):
            raise ValueError("generated path の帰属が重複")
        if set(source_paths) & set(generated_paths):
            raise ValueError("正本と生成物のパスが重複")

    @property
    def all_generated_paths(self) -> frozenset[str]:
        """生成器 version 変更時に再生成する全パスを返す。"""
        return frozenset(
            path
            for binding in self.bindings
            for path in binding.generated_paths
        )


def _checked_git(root: Path, *arguments: str) -> str:
    """既存 Git 境界を使い、非 0 を判定不能へ変換する。"""
    result = _run_git(root, *arguments)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise DivergenceInspectionError(
            f"Git 履歴を判定できない: {arguments[0]}: {detail}"
        )
    return result.stdout


@dataclass(frozen=True, slots=True)
class CommitSnapshot:
    """Git commit のファイル内容を作業ツリー非依存で読む。"""

    root: Path
    commit_oid: str

    def read_text(self, path: str) -> str:
        """指定 commit 内の UTF-8 テキストを返す。"""
        relative = _repository_relative(path, "snapshot path")
        return _checked_git(self.root, "show", f"{self.commit_oid}:{relative}")

    def python_string_constant(self, marker: GeneratorVersionMarker) -> str:
        """Python モジュールの文字列定数を AST から一意に返す。"""
        try:
            tree = ast.parse(self.read_text(marker.path))
        except (SyntaxError, UnicodeError) as error:
            raise DivergenceInspectionError(
                "generator version の Python を解析できない"
            ) from error
        values = [
            node.value.value
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            if isinstance(target, ast.Name)
            and target.id == marker.symbol
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ]
        if len(values) != 1:
            raise DivergenceInspectionError(
                "generator version の文字列定数が一意でない"
            )
        return values[0]


Regenerator = Callable[
    [CommitSnapshot, GeneratedBinding],
    Mapping[str, str],
]


@dataclass(frozen=True, slots=True)
class CommitViolation:
    """一 commit に残る一つの同期違反。"""

    commit_oid: str
    kind: DivergenceKind
    binding_id: str | None
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DivergenceReport:
    """PR 内で走査した commit と検出した乖離。"""

    commits: tuple[str, ...]
    violations: tuple[CommitViolation, ...]

    @property
    def conforming(self) -> bool:
        """全 commit に乖離が無い場合だけ真を返す。"""
        return not self.violations


def _resolve_commit(root: Path, revision: str, label: str) -> str:
    """指定 revision を実在する完全 commit OID へ解決する。"""
    output = _checked_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    oid = output.strip()
    if not oid:
        raise DivergenceInspectionError(f"{label} commit OID が空")
    return oid


def _pr_commits(root: Path, base_oid: str, head_oid: str) -> tuple[str, ...]:
    """比較元を除く PR commit を古い順で返す。"""
    output = _checked_git(
        root,
        "log",
        "--reverse",
        "--format=%H",
        f"{base_oid}..{head_oid}",
    )
    return tuple(line for line in output.splitlines() if line)


def _changed_paths(snapshot: CommitSnapshot) -> frozenset[str]:
    """一 commit が親から変更した全パスを返す。"""
    output = _checked_git(
        snapshot.root,
        "show",
        "--format=",
        "--name-only",
        "--no-renames",
        snapshot.commit_oid,
    )
    return frozenset(line for line in output.splitlines() if line)


def _version_changed(
    snapshot: CommitSnapshot,
    marker: GeneratorVersionMarker,
) -> bool:
    """一 commit の親と比べて generator version が変化したかを返す。"""
    current = snapshot.python_string_constant(marker)
    parent = CommitSnapshot(snapshot.root, f"{snapshot.commit_oid}^")
    return current != parent.python_string_constant(marker)


def _path_violations(
    snapshot: CommitSnapshot,
    changed: frozenset[str],
    specification: DivergenceSpecification,
    version_changed: bool,
) -> list[CommitViolation]:
    """正本・生成物・version の同一 commit 条件を検査する。"""
    violations: list[CommitViolation] = []
    changed_bindings = {
        binding.binding_id
        for binding in specification.bindings
        if changed.intersection(binding.source_paths)
    }
    for binding in specification.bindings:
        if binding.binding_id in changed_bindings:
            missing = set(binding.generated_paths) - changed
            if missing:
                violations.append(
                    CommitViolation(
                        snapshot.commit_oid,
                        DivergenceKind.SOURCE_WITHOUT_GENERATED,
                        binding.binding_id,
                        tuple(sorted(missing)),
                    )
                )
        changed_generated = changed.intersection(binding.generated_paths)
        if (
            changed_generated
            and binding.binding_id not in changed_bindings
            and not version_changed
        ):
            violations.append(
                CommitViolation(
                    snapshot.commit_oid,
                    DivergenceKind.GENERATED_WITHOUT_SOURCE,
                    binding.binding_id,
                    tuple(sorted(changed_generated)),
                )
            )
    if version_changed:
        missing = specification.all_generated_paths - changed
        if missing:
            violations.append(
                CommitViolation(
                    snapshot.commit_oid,
                    DivergenceKind.GENERATOR_WITHOUT_ALL_GENERATED,
                    None,
                    tuple(sorted(missing)),
                )
            )
    return violations


def _affected_bindings(
    changed: frozenset[str],
    specification: DivergenceSpecification,
    version_changed: bool,
) -> tuple[GeneratedBinding, ...]:
    """その commit で再生成結果を突合すべき対応を返す。"""
    if version_changed:
        return specification.bindings
    return tuple(
        binding
        for binding in specification.bindings
        if changed.intersection(
            (*binding.source_paths, *binding.generated_paths)
        )
    )


def _content_violations(
    snapshot: CommitSnapshot,
    bindings: tuple[GeneratedBinding, ...],
    regenerator: Regenerator,
) -> list[CommitViolation]:
    """各 commit の再生成結果と記録済み生成物を完全一致で突合する。"""
    violations: list[CommitViolation] = []
    for binding in bindings:
        try:
            expected = regenerator(snapshot, binding)
        except DivergenceInspectionError:
            raise
        except Exception as error:
            raise DivergenceInspectionError(
                f"再生成できない: binding={binding.binding_id}: {error}"
            ) from error
        expected_paths = set(binding.generated_paths)
        actual_paths = set(expected)
        if actual_paths != expected_paths:
            raise DivergenceInspectionError(
                "再生成器の出力パス集合が宣言と不一致: "
                f"binding={binding.binding_id}, "
                f"missing={sorted(expected_paths - actual_paths)!r}, "
                f"unknown={sorted(actual_paths - expected_paths)!r}"
            )
        mismatched = tuple(
            path
            for path in binding.generated_paths
            if snapshot.read_text(path) != expected[path]
        )
        if mismatched:
            violations.append(
                CommitViolation(
                    snapshot.commit_oid,
                    DivergenceKind.STALE_GENERATED,
                    binding.binding_id,
                    tuple(sorted(mismatched)),
                )
            )
    return violations


def inspect_pr_divergence(
    *,
    root: Path,
    base_revision: str,
    head_revision: str,
    specification: DivergenceSpecification,
    regenerator: Regenerator,
) -> DivergenceReport:
    """PR 内の全 commit を走査し、D-3 の同期違反を返す。

    Args:
        root: 検査する Git リポジトリルート。
        base_revision: PR 比較元の revision。
        head_revision: PR 先端の revision。
        specification: 正本と全生成物の対応。
        regenerator: 既存生成器を commit snapshot へ適用する関数。

    Returns:
        最終ツリーへ丸めない commit ごとの検査結果。

    Raises:
        DivergenceInspectionError: 履歴または再生成を判定できない場合。
    """
    repository = root.resolve()
    if not repository.is_dir():
        raise DivergenceInspectionError("リポジトリルートが存在しない")
    base_oid = _resolve_commit(repository, base_revision, "base")
    head_oid = _resolve_commit(repository, head_revision, "head")
    commits = _pr_commits(repository, base_oid, head_oid)
    violations: list[CommitViolation] = []
    for commit_oid in commits:
        snapshot = CommitSnapshot(repository, commit_oid)
        changed = _changed_paths(snapshot)
        version_changed = _version_changed(
            snapshot,
            specification.generator_version,
        )
        violations.extend(
            _path_violations(
                snapshot,
                changed,
                specification,
                version_changed,
            )
        )
        bindings = _affected_bindings(
            changed,
            specification,
            version_changed,
        )
        violations.extend(_content_violations(snapshot, bindings, regenerator))
    return DivergenceReport(commits, tuple(violations))


def require_no_divergence(report: DivergenceReport) -> None:
    """乖離が一件でもあれば commit と種類を示して fail にする。"""
    if report.conforming:
        return
    details = [
        f"{item.commit_oid}:{item.kind.value}:{item.binding_id}:{item.paths!r}"
        for item in report.violations
    ]
    raise DivergenceError(f"コミット単位の乖離を検出: {details!r}")


__all__ = [
    "CommitSnapshot",
    "CommitViolation",
    "DivergenceError",
    "DivergenceInspectionError",
    "DivergenceKind",
    "DivergenceReport",
    "DivergenceSpecification",
    "GeneratedBinding",
    "GeneratorVersionMarker",
    "Regenerator",
    "inspect_pr_divergence",
    "require_no_divergence",
]
