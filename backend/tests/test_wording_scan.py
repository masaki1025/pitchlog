"""文言走査の母集団と失敗時の契約を DB なしで検証する。"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from wording_scan import (
    WordingScanFile,
    WordingScanReadError,
    collect_wording_scan_files,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_SCAN_ROOTS = (
    Path("backend"),
    Path("scripts"),
    Path("contracts"),
    Path("tests"),
    Path("docs/features/pg-authz-verification-g2"),
)


@dataclass(frozen=True, slots=True)
class _PopulatedRepository:
    """追跡済みと未追跡のテキストを持つ一時リポジトリ。"""

    root: Path
    expected_paths: frozenset[Path]
    tracked_paths: frozenset[Path]


def _git(
    repository_root: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """指定した一時リポジトリで Git を実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=check,
        capture_output=True,
    )


def _initialize_repository(tmp_path: Path) -> Path:
    """空の一時 Git リポジトリを初期化する。"""
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    _git(repository_root, "init", "--quiet")
    return repository_root


def _repository_state(repository_root: Path) -> tuple[bytes, bytes]:
    """Git index と status の論理状態を取得する。"""
    index = _git(repository_root, "ls-files", "--stage", "-z").stdout
    status = _git(
        repository_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "-z",
    ).stdout
    return index, status


def _assert_exact_population(
    actual: frozenset[Path], expected: frozenset[Path]
) -> None:
    """走査結果が作成側の期待集合と完全一致することを要求する。"""
    assert actual == expected


def _violations(
    files: tuple[WordingScanFile, ...], forbidden: bytes
) -> tuple[Path, ...]:
    """対象成果物から禁止文言を含むパスを返す。"""
    return tuple(item.path for item in files if forbidden in item.content)


@pytest.fixture
def populated_repository(
    tmp_path: Path,
    real_repository_unchanged: None,
) -> _PopulatedRepository:
    """各期待ルートに動的名の追跡済み・未追跡テキストを置く。"""
    repository_root = _initialize_repository(tmp_path)
    expected_paths: set[Path] = set()
    tracked_paths: set[Path] = set()

    for scan_root in _EXPECTED_SCAN_ROOTS:
        directory = repository_root / scan_root
        directory.mkdir(parents=True)
        tracked_path = scan_root / f"tracked-{uuid4().hex}"
        untracked_path = scan_root / f"untracked-{uuid4().hex}"
        for path in (tracked_path, untracked_path):
            (repository_root / path).write_text(
                f"generated basename: {path.name}\n", encoding="utf-8"
            )
            ignored = _git(
                repository_root,
                "check-ignore",
                "--quiet",
                "--",
                path.as_posix(),
                check=False,
            )
            assert ignored.returncode == 1
            expected_paths.add(path)
        tracked_paths.add(tracked_path)

    _git(
        repository_root,
        "add",
        "--",
        *(path.as_posix() for path in sorted(tracked_paths)),
    )
    return _PopulatedRepository(
        root=repository_root,
        expected_paths=frozenset(expected_paths),
        tracked_paths=frozenset(tracked_paths),
    )


@pytest.fixture
def real_repository_unchanged() -> Iterator[None]:
    """テスト前後で実リポジトリの index と status が不変と確認する。"""
    before = _repository_state(_REPOSITORY_ROOT)
    yield
    assert _repository_state(_REPOSITORY_ROOT) == before


def test_every_expected_root_includes_tracked_and_untracked_text(
    populated_repository: _PopulatedRepository,
) -> None:
    """独立した期待ルートすべての動的名テキストを包含する。"""
    files = collect_wording_scan_files(
        populated_repository.root,
        _EXPECTED_SCAN_ROOTS,
    )

    _assert_exact_population(
        frozenset(item.path for item in files),
        populated_repository.expected_paths,
    )


def test_ignored_text_is_excluded(tmp_path: Path) -> None:
    """Git が ignore するテキストを母集団から除外する。"""
    repository_root = _initialize_repository(tmp_path)
    scan_root = _EXPECTED_SCAN_ROOTS[0]
    (repository_root / scan_root).mkdir(parents=True)
    ignored_path = scan_root / f"ignored-{uuid4().hex}"
    (repository_root / ignored_path).write_text("ignored text\n", encoding="utf-8")
    (repository_root / ".gitignore").write_text(
        f"/{ignored_path.as_posix()}\n",
        encoding="utf-8",
    )
    _git(repository_root, "add", ".gitignore")
    ignored = _git(
        repository_root,
        "check-ignore",
        "--quiet",
        "--",
        ignored_path.as_posix(),
        check=False,
    )
    assert ignored.returncode == 0

    files = collect_wording_scan_files(repository_root, (scan_root,))

    assert ignored_path not in {item.path for item in files}


def test_non_ignored_binary_is_excluded(tmp_path: Path) -> None:
    """Git で無視されていないバイナリもテキスト母集団から除外する。"""
    repository_root = _initialize_repository(tmp_path)
    scan_root = _EXPECTED_SCAN_ROOTS[0]
    (repository_root / scan_root).mkdir(parents=True)
    text_path = scan_root / f"text-{uuid4().hex}"
    binary_path = scan_root / f"binary-{uuid4().hex}"
    (repository_root / text_path).write_text("plain text\n", encoding="utf-8")
    (repository_root / binary_path).write_bytes(b"SQLite format 3\0\xff\x00")
    ignored = _git(
        repository_root,
        "check-ignore",
        "--quiet",
        "--",
        binary_path.as_posix(),
        check=False,
    )
    assert ignored.returncode == 1

    files = collect_wording_scan_files(repository_root, (scan_root,))
    paths = frozenset(item.path for item in files)

    assert text_path in paths
    assert binary_path not in paths


def test_utf8_with_nul_is_excluded(tmp_path: Path) -> None:
    """UTF-8 として復号できても NUL を含む内容を母集団から除外する。"""
    repository_root = _initialize_repository(tmp_path)
    scan_root = _EXPECTED_SCAN_ROOTS[0]
    (repository_root / scan_root).mkdir(parents=True)
    nul_path = scan_root / f"nul-{uuid4().hex}"
    (repository_root / nul_path).write_bytes(b"abc\0def")

    files = collect_wording_scan_files(repository_root, (scan_root,))

    assert nul_path not in {item.path for item in files}


def test_forbidden_wording_in_included_file_is_detected(
    populated_repository: _PopulatedRepository,
) -> None:
    """包含対象へ禁止文言を置く負例が違反を発生させる。"""
    forbidden = ("6" + " 権限").encode()
    target = min(populated_repository.expected_paths)
    (populated_repository.root / target).write_bytes(
        b"prefix " + forbidden + b" suffix"
    )
    files = collect_wording_scan_files(
        populated_repository.root,
        _EXPECTED_SCAN_ROOTS,
    )

    violations = _violations(files, forbidden)
    assert violations == (target,)
    with pytest.raises(AssertionError):
        assert violations == ()


def test_unreadable_included_path_is_reported(
    populated_repository: _PopulatedRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """包含候補を読めない負例をパス付きエラーとして報告する。"""
    target = min(populated_repository.expected_paths)
    target_absolute = populated_repository.root / target
    original_read_bytes = Path.read_bytes

    def fail_target(path: Path) -> bytes:
        if path == target_absolute:
            raise PermissionError("injected unreadable path")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_target)

    with pytest.raises(
        WordingScanReadError,
        match=re.escape(target.as_posix()),
    ) as error:
        collect_wording_scan_files(
            populated_repository.root,
            _EXPECTED_SCAN_ROOTS,
        )
    assert error.value.path == target
    assert isinstance(error.value.__cause__, PermissionError)


def test_tracked_only_population_mutant_is_rejected(
    populated_repository: _PopulatedRepository,
) -> None:
    """未追跡を落とす縮小変異を包含の exact-set 比較で拒否する。"""
    files = collect_wording_scan_files(
        populated_repository.root,
        _EXPECTED_SCAN_ROOTS,
    )
    tracked_only_mutant = frozenset(
        item.path for item in files if item.path in populated_repository.tracked_paths
    )

    assert tracked_only_mutant == populated_repository.tracked_paths
    with pytest.raises(AssertionError):
        _assert_exact_population(
            tracked_only_mutant,
            populated_repository.expected_paths,
        )
