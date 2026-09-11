"""追跡済み生成物をリポジトリへ混入させないことを検証する。"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from os import fsdecode
from pathlib import Path
from uuid import uuid4

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class _IgnoredArtifactRepository:
    """ignore 対象を追跡した一時リポジトリ。"""

    root: Path
    artifact_path: Path


@dataclass(frozen=True, slots=True)
class _IndexEntry:
    """Git index の mode と blob 参照を保持する。"""

    mode: str
    object_id: str
    stage: int
    path: Path


@dataclass(frozen=True, slots=True)
class _NestedNegationRepository:
    """下位の否定規則と、その対象を持つ一時リポジトリ。"""

    root: Path
    ignore_path: Path
    artifact_path: Path
    ignore_blob: bytes


def _git(
    repository_root: Path,
    *arguments: str,
    check: bool = True,
    input_data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """指定ディレクトリを起点に Git を実行する。

    Args:
        repository_root: Git コマンドの作業ディレクトリ。
        arguments: Git へ渡す引数。
        check: 非ゼロ終了を例外にするか。
        input_data: 標準入力へ渡すバイト列。

    Returns:
        Git コマンドの実行結果。
    """
    return subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=check,
        input=input_data,
        capture_output=True,
    )


def _paths_from_nul(output: bytes) -> tuple[Path, ...]:
    """NUL 区切りの Git 出力をパスへ変換する。"""
    return tuple(
        Path(raw_path.decode("utf-8"))
        for raw_path in output.split(b"\0")
        if raw_path
    )


def _index_entries(repository_root: Path) -> tuple[_IndexEntry, ...]:
    """Git index にある全 entry を mode 付きで導出する。"""
    completed = _git(repository_root, "ls-files", "--stage", "-z")
    entries: list[_IndexEntry] = []
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        raw_mode, raw_object_id, raw_stage = metadata.split(b" ")
        entries.append(
            _IndexEntry(
                mode=raw_mode.decode("ascii"),
                object_id=raw_object_id.decode("ascii"),
                stage=int(raw_stage),
                path=Path(raw_path.decode("utf-8")),
            )
        )
    return tuple(entries)


def _paths_from_index_entries(entries: tuple[_IndexEntry, ...]) -> tuple[Path, ...]:
    """Index entry から重複しない追跡パスを導出する。"""
    return tuple(dict.fromkeys(entry.path for entry in entries))


def _tracked_paths(repository_root: Path) -> tuple[Path, ...]:
    """Git index にある全パスを導出する。"""
    return _paths_from_index_entries(_index_entries(repository_root))


def _initialize_repository(tmp_path: Path) -> Path:
    """空の一時 Git リポジトリを初期化する。"""
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    _git(repository_root, "init", "--quiet")
    return repository_root


def _initialize_nested_negation_repository(
    tmp_path: Path,
    *,
    symbolic_ignore: bool,
) -> _NestedNegationRepository:
    """下位の否定規則を通常ファイルまたは symlink として追跡する。"""
    repository_root = _initialize_repository(tmp_path)
    nested = Path(f"nested-{uuid4().hex}")
    ignore_path = nested / ".gitignore"
    artifact_path = nested / f"artifact-{uuid4().hex}"
    ignore_blob = f"!{artifact_path.name}".encode()
    (repository_root / nested).mkdir()
    (repository_root / ".gitignore").write_text(
        f"/{artifact_path.as_posix()}\n",
        encoding="utf-8",
    )
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    if symbolic_ignore:
        link_target = nested / ignore_blob.decode()
        (repository_root / link_target).write_text("readable target\n", encoding="utf-8")
        (repository_root / ignore_path).symlink_to(link_target.name)
        _git(repository_root, "add", "--", link_target.as_posix())
    else:
        (repository_root / ignore_path).write_bytes(ignore_blob)
    _git(repository_root, "add", "--", ".gitignore", ignore_path.as_posix())
    _git(repository_root, "add", "-f", "--", artifact_path.as_posix())
    return _NestedNegationRepository(
        root=repository_root,
        ignore_path=ignore_path,
        artifact_path=artifact_path,
        ignore_blob=ignore_blob,
    )


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


def _isolate_global_git_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """当該テストだけが使う HOME と global Git 設定領域を作る。"""
    home = tmp_path / "home"
    xdg_config_home = tmp_path / "xdg-config"
    home.mkdir()
    xdg_config_home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home))
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return home


def _check_ignored_paths(
    repository_root: Path,
    paths: tuple[Path, ...],
    *,
    no_index: bool,
) -> tuple[Path, ...]:
    """Git 自身の case-sensitive な ignore 判定で一致したパスを返す。

    CI が動く Linux の判定を green/red の権威とするため、開発環境から
    ``core.ignoreCase`` を継承せず case-sensitive に固定する。

    Args:
        repository_root: 判定を行う Git リポジトリ。
        paths: 判定対象のリポジトリ相対パス。
        no_index: 追跡状態を無視して判定するか。

    Returns:
        ignore 規則に一致した入力パス。
    """
    if not paths:
        return ()
    arguments = [
        "-c",
        "core.excludesFile=/dev/null",
        "-c",
        "core.ignoreCase=false",
        "check-ignore",
    ]
    if no_index:
        arguments.append("--no-index")
    arguments.extend(("-z", "--stdin"))
    completed = _git(
        repository_root,
        *arguments,
        check=False,
        input_data=b"\0".join(path.as_posix().encode() for path in paths) + b"\0",
    )
    if completed.returncode not in (0, 1):
        completed.check_returncode()
    return _paths_from_nul(completed.stdout)


def _index_evaluation_repository(
    repository_root: Path,
    workspace: Path,
    index_entries: tuple[_IndexEntry, ...],
) -> Path:
    """元リポジトリの index にある ignore 規則だけを直接書き出す。

    ``cat-file blob :<path>`` で index の blob を直接読むため、skip-worktree
    ビット、attributes、smudge filter のいずれも内容の抽出経路に入らない。
    通常ファイルは blob をそのまま書き、symlink は blob をリンク先として再現する。
    Gitlink は規則ファイルにならないため実体化せず、symlink を作れなければ失敗する。

    Args:
        repository_root: index を読む元リポジトリ。
        workspace: 一時評価リポジトリの親ディレクトリ。
        index_entries: 元リポジトリの mode 付き index entry。

    Returns:
        index 由来の ignore 規則と追跡パス情報を持つ新規 Git リポジトリ。
    """
    evaluation_root = workspace / f"index-{uuid4().hex}"
    evaluation_root.mkdir(parents=True)
    for entry in index_entries:
        if entry.path.name != ".gitignore":
            continue
        if entry.mode == "160000":
            # gitlink はディレクトリ entry であり、ignore 規則ファイルではない。
            continue
        if entry.mode not in {"100644", "100755", "120000"}:
            raise ValueError(f"未対応の index mode: {entry.mode} {entry.path}")
        content = _git(
            repository_root,
            "cat-file",
            "blob",
            f":{entry.path.as_posix()}",
        ).stdout
        destination = evaluation_root / entry.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if entry.mode == "120000":
            try:
                destination.symlink_to(fsdecode(content))
            except OSError as error:
                raise RuntimeError(
                    f"index の symlink を再現できない: {entry.path}"
                ) from error
        else:
            destination.write_bytes(content)

    _git(evaluation_root, "init", "--quiet")
    (evaluation_root / ".git/info/exclude").write_text("", encoding="utf-8")
    if index_entries:
        raw_index_entries = b"".join(
            (
                f"{entry.mode} {entry.object_id} {entry.stage}\t".encode()
                + entry.path.as_posix().encode()
                + b"\0"
            )
            for entry in index_entries
        )
        _git(
            evaluation_root,
            "update-index",
            "--info-only",
            "-z",
            "--index-info",
            input_data=raw_index_entries,
        )
    return evaluation_root


def _tracked_ignored_paths_with_mode(
    repository_root: Path,
    workspace: Path,
    *,
    no_index: bool,
) -> tuple[Path, ...]:
    """index 時点へ固定した環境で追跡済みパスを ignore 判定する。"""
    index_entries = _index_entries(repository_root)
    tracked_paths = _paths_from_index_entries(index_entries)
    evaluation_root = _index_evaluation_repository(
        repository_root,
        workspace,
        index_entries,
    )
    return _check_ignored_paths(
        evaluation_root,
        tracked_paths,
        no_index=no_index,
    )


def _tracked_ignored_paths(
    repository_root: Path,
    workspace: Path,
) -> tuple[Path, ...]:
    """追跡済みだが管理下の ignore 規則に一致するパスを返す。"""
    return _tracked_ignored_paths_with_mode(
        repository_root,
        workspace,
        no_index=True,
    )


def _assert_no_tracked_ignored_paths(paths: tuple[Path, ...]) -> None:
    """ignore 対象の追跡済みパスがないことを要求する。"""
    assert paths == (), f"ignore 対象が追跡されている: {paths}"


def _single_name_mutant(repository_root: Path) -> tuple[Path, ...]:
    """特定の生成物名だけを検出する不正な縮小実装を模倣する。"""
    target_name = "." + "coverage"
    return tuple(
        path for path in _tracked_paths(repository_root) if path.name == target_name
    )


def _head_snapshot_mutant(
    repository_root: Path,
    workspace: Path,
) -> tuple[Path, ...]:
    """コミット済み時点だけで述語を評価する不正実装を模倣する。"""
    tracked_paths = _tracked_paths(repository_root)
    evaluation_root = workspace / f"committed-{uuid4().hex}"
    _git(
        workspace,
        "clone",
        "--quiet",
        repository_root.as_posix(),
        evaluation_root.as_posix(),
    )
    return _check_ignored_paths(
        evaluation_root,
        tracked_paths,
        no_index=True,
    )


@pytest.fixture(autouse=True)
def real_repository_unchanged() -> Iterator[None]:
    """各テストの前後で実リポジトリの index と status を照合する。"""
    before = _repository_state(REPOSITORY_ROOT)
    yield
    assert _repository_state(REPOSITORY_ROOT) == before


@pytest.fixture
def isolated_git_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """一時リポジトリの初期化前に global Git 設定を隔離する。"""
    return _isolate_global_git_config(tmp_path, monkeypatch)


@pytest.fixture
def ignored_artifact_repository(tmp_path: Path) -> _IgnoredArtifactRepository:
    """動的な ignore 規則に一致するファイルを強制追跡する。"""
    repository_root = _initialize_repository(tmp_path)
    output_directory = Path(f"generated-{uuid4().hex}")
    artifact_path = output_directory / f"artifact-{uuid4().hex}"
    (repository_root / output_directory).mkdir()
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    (repository_root / ".gitignore").write_text(
        f"/{output_directory.as_posix()}/\n",
        encoding="utf-8",
    )
    _git(repository_root, "add", ".gitignore")
    _git(repository_root, "add", "-f", "--", artifact_path.as_posix())
    return _IgnoredArtifactRepository(repository_root, artifact_path)


def test_repository_has_no_tracked_ignored_artifacts(tmp_path: Path) -> None:
    """実リポジトリに ignore 対象の追跡済みファイルがない。"""
    _assert_no_tracked_ignored_paths(
        _tracked_ignored_paths(REPOSITORY_ROOT, tmp_path)
    )


def test_non_git_repository_fails_closed(tmp_path: Path) -> None:
    """Git の母集団導出に失敗した場合は空集合で合格させない。"""
    non_git_directory = tmp_path / "not-a-repository"
    non_git_directory.mkdir()

    with pytest.raises(subprocess.CalledProcessError):
        _tracked_ignored_paths(non_git_directory, tmp_path)


def test_tracked_ignored_artifact_is_detected(
    ignored_artifact_repository: _IgnoredArtifactRepository,
    tmp_path: Path,
) -> None:
    """Ignore 対象を index へ加える負例を検出する。"""
    violations = _tracked_ignored_paths(ignored_artifact_repository.root, tmp_path)

    assert violations == (ignored_artifact_repository.artifact_path,)
    with pytest.raises(AssertionError):
        _assert_no_tracked_ignored_paths(violations)


def test_new_ignore_pattern_is_applied_without_checker_changes(tmp_path: Path) -> None:
    """新しい ignore 規則へ検査実装の変更なしで追随する。"""
    repository_root = _initialize_repository(tmp_path)
    artifact_path = Path(f"new-artifact-{uuid4().hex}")
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    _git(repository_root, "add", "--", artifact_path.as_posix())
    assert _tracked_ignored_paths(repository_root, tmp_path) == ()

    (repository_root / ".gitignore").write_text(
        f"/{artifact_path.as_posix()}\n",
        encoding="utf-8",
    )
    _git(repository_root, "add", ".gitignore")

    assert _tracked_ignored_paths(repository_root, tmp_path) == (artifact_path,)


def test_single_name_mutant_misses_new_ignore_pattern(
    ignored_artifact_repository: _IgnoredArtifactRepository,
    tmp_path: Path,
) -> None:
    """特定名だけを見る縮小実装を動的な ignore 規則で拒否する。"""
    expected = _tracked_ignored_paths(ignored_artifact_repository.root, tmp_path)
    mutant = _single_name_mutant(ignored_artifact_repository.root)

    assert expected == (ignored_artifact_repository.artifact_path,)
    assert mutant == ()
    with pytest.raises(AssertionError):
        assert mutant == expected


def test_info_exclude_only_pattern_is_not_authoritative(tmp_path: Path) -> None:
    """ローカルな info/exclude だけの一致を違反にしない。"""
    repository_root = _initialize_repository(tmp_path)
    artifact_path = Path(f"local-artifact-{uuid4().hex}")
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    _git(repository_root, "add", "--", artifact_path.as_posix())
    (repository_root / ".git/info/exclude").write_text(
        f"/{artifact_path.as_posix()}\n",
        encoding="utf-8",
    )

    assert _check_ignored_paths(
        repository_root,
        (artifact_path,),
        no_index=True,
    ) == (artifact_path,)
    assert _tracked_ignored_paths(repository_root, tmp_path) == ()


def test_symlink_ignore_does_not_apply_nested_negation(tmp_path: Path) -> None:
    """Symlink の下位 ignore を通常ファイル化せず、違反を見逃さない。"""
    repository = _initialize_nested_negation_repository(
        tmp_path,
        symbolic_ignore=True,
    )
    ignore_entry = next(
        entry
        for entry in _index_entries(repository.root)
        if entry.path == repository.ignore_path
    )

    assert ignore_entry.mode == "120000"
    assert (
        _git(
            repository.root,
            "cat-file",
            "blob",
            f":{repository.ignore_path.as_posix()}",
        ).stdout
        == repository.ignore_blob
    )
    assert _check_ignored_paths(
        repository.root,
        (repository.artifact_path,),
        no_index=True,
    ) == (repository.artifact_path,)
    assert _tracked_ignored_paths(repository.root, tmp_path) == (
        repository.artifact_path,
    )


def test_regular_ignore_applies_same_nested_negation(tmp_path: Path) -> None:
    """同じ blob の通常ファイルでは下位の否定規則が有効になる。"""
    repository = _initialize_nested_negation_repository(
        tmp_path,
        symbolic_ignore=False,
    )
    ignore_entry = next(
        entry
        for entry in _index_entries(repository.root)
        if entry.path == repository.ignore_path
    )

    assert ignore_entry.mode == "100644"
    assert (
        _git(
            repository.root,
            "cat-file",
            "blob",
            f":{repository.ignore_path.as_posix()}",
        ).stdout
        == repository.ignore_blob
    )
    assert _check_ignored_paths(
        repository.root,
        (repository.artifact_path,),
        no_index=True,
    ) == ()
    assert _tracked_ignored_paths(repository.root, tmp_path) == ()


def test_skip_worktree_nested_ignore_is_extracted_from_index(tmp_path: Path) -> None:
    """Skip-worktree の下位 ignore 規則も index の blob から抽出する。"""
    repository_root = _initialize_repository(tmp_path)
    nested = Path(f"skip-{uuid4().hex}")
    ignore_path = nested / ".gitignore"
    artifact_path = nested / f"artifact-{uuid4().hex}"
    (repository_root / nested).mkdir()
    (repository_root / ignore_path).write_text(
        f"/{artifact_path.name}\n",
        encoding="utf-8",
    )
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    _git(repository_root, "add", "--", ignore_path.as_posix())
    _git(repository_root, "add", "-f", "--", artifact_path.as_posix())
    _git(repository_root, "update-index", "--skip-worktree", ignore_path.as_posix())

    assert ignore_path in _tracked_paths(repository_root)
    assert _tracked_ignored_paths(repository_root, tmp_path) == (artifact_path,)


def test_source_smudge_filter_does_not_change_indexed_ignore(
    tmp_path: Path,
) -> None:
    """Source 側の attributes と smudge filter を blob 抽出へ入れない。"""
    repository_root = _initialize_repository(tmp_path)
    nested = Path(f"filtered-{uuid4().hex}")
    ignore_path = nested / ".gitignore"
    artifact_path = nested / f"artifact-{uuid4().hex}"
    (repository_root / nested).mkdir()
    (repository_root / ignore_path).write_text(
        f"/{artifact_path.name}\n",
        encoding="utf-8",
    )
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    _git(repository_root, "add", "--", ignore_path.as_posix())
    _git(repository_root, "add", "-f", "--", artifact_path.as_posix())
    (repository_root / ".git/info/attributes").write_text(
        f"{ignore_path.as_posix()} filter=empty-ignore\n",
        encoding="utf-8",
    )
    _git(
        repository_root,
        "config",
        "filter.empty-ignore.smudge",
        "sed 's/.*//'",
    )
    checkout_probe = tmp_path / "checkout-probe"
    checkout_probe.mkdir()
    _git(
        repository_root,
        "checkout-index",
        "--force",
        f"--prefix={checkout_probe.as_posix()}/",
        "--",
        ignore_path.as_posix(),
    )
    assert (checkout_probe / ignore_path).read_text(encoding="utf-8").strip() == ""

    assert _tracked_ignored_paths(repository_root, tmp_path) == (artifact_path,)


def test_global_excludes_file_is_not_authoritative(
    tmp_path: Path,
    isolated_git_home: Path,
) -> None:
    """一時 HOME の global excludesFile によって判定を変えない。"""
    repository_root = _initialize_repository(tmp_path)
    artifact_path = Path(f"global-artifact-{uuid4().hex}")
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    _git(repository_root, "add", "--", artifact_path.as_posix())
    global_excludes = isolated_git_home / "global-excludes"
    global_excludes.write_text(f"/{artifact_path.as_posix()}\n", encoding="utf-8")
    _git(
        repository_root,
        "config",
        "--global",
        "core.excludesFile",
        global_excludes.as_posix(),
    )

    assert _tracked_ignored_paths(repository_root, tmp_path) == ()


def test_template_info_exclude_is_cleared(
    tmp_path: Path,
    isolated_git_home: Path,
) -> None:
    """Git template 由来の info/exclude によって判定を変えない。"""
    repository_root = _initialize_repository(tmp_path)
    artifact_path = Path(f"template-artifact-{uuid4().hex}")
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    _git(repository_root, "add", "--", artifact_path.as_posix())
    template = tmp_path / "git-template"
    template_info = template / "info"
    template_info.mkdir(parents=True)
    (template_info / "exclude").write_text(
        f"/{artifact_path.as_posix()}\n",
        encoding="utf-8",
    )
    _git(
        repository_root,
        "config",
        "--global",
        "init.templateDir",
        template.as_posix(),
    )

    assert _tracked_ignored_paths(repository_root, tmp_path) == ()


def test_global_ignore_case_does_not_change_case_sensitive_evaluation(
    tmp_path: Path,
    isolated_git_home: Path,
) -> None:
    """Global の ignoreCase=true を継承せず Linux と同じ判定にする。"""
    repository_root = _initialize_repository(tmp_path)
    pattern_name = f"case-artifact-{uuid4().hex}"
    artifact_path = Path(pattern_name.upper())
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    (repository_root / ".gitignore").write_text(
        f"/{pattern_name}\n",
        encoding="utf-8",
    )
    _git(repository_root, "add", ".gitignore", artifact_path.as_posix())
    _git(repository_root, "config", "--global", "core.ignoreCase", "true")

    assert _tracked_ignored_paths(repository_root, tmp_path) == ()


def test_without_no_index_mutant_misses_tracked_ignored_artifact(
    ignored_artifact_repository: _IgnoredArtifactRepository,
    tmp_path: Path,
) -> None:
    """No-index 判定を外すと追跡済みの負例を見逃す。"""
    expected = _tracked_ignored_paths(ignored_artifact_repository.root, tmp_path)
    mutant = _tracked_ignored_paths_with_mode(
        ignored_artifact_repository.root,
        tmp_path,
        no_index=False,
    )

    assert expected == (ignored_artifact_repository.artifact_path,)
    assert mutant == ()
    with pytest.raises(AssertionError):
        assert mutant == expected


def test_untracked_nested_ignore_files_do_not_change_evaluation(
    tmp_path: Path,
) -> None:
    """未追跡の下位 ignore 規則を正・否定の両方で評価から除く。"""
    repository_root = _initialize_repository(tmp_path)
    nested = Path(f"nested-{uuid4().hex}")
    artifact_path = nested / f"artifact-{uuid4().hex}"
    ordinary_path = nested / f"ordinary-{uuid4().hex}"
    (repository_root / nested).mkdir()
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    (repository_root / ordinary_path).write_text("ordinary\n", encoding="utf-8")
    (repository_root / ".gitignore").write_text(
        f"/{artifact_path.as_posix()}\n",
        encoding="utf-8",
    )
    _git(repository_root, "add", ".gitignore")
    _git(repository_root, "add", "--", ordinary_path.as_posix())
    _git(repository_root, "add", "-f", "--", artifact_path.as_posix())
    baseline = _tracked_ignored_paths(repository_root, tmp_path)
    assert baseline == (artifact_path,)

    nested_ignore = repository_root / nested / ".gitignore"
    nested_ignore.write_text(f"{ordinary_path.name}\n", encoding="utf-8")
    in_place_positive = _check_ignored_paths(
        repository_root,
        (artifact_path, ordinary_path),
        no_index=True,
    )
    assert frozenset(in_place_positive) == frozenset(
        {artifact_path, ordinary_path}
    )
    assert _tracked_ignored_paths(repository_root, tmp_path) == baseline

    nested_ignore.write_text(f"!{artifact_path.name}\n", encoding="utf-8")
    assert _check_ignored_paths(
        repository_root,
        (artifact_path,),
        no_index=True,
    ) == ()
    assert _tracked_ignored_paths(repository_root, tmp_path) == baseline
    assert nested / ".gitignore" not in _tracked_paths(repository_root)


def test_staged_ignore_change_is_used_instead_of_committed_snapshot(
    tmp_path: Path,
) -> None:
    """未コミットで stage した ignore 規則を同じ index 時点で評価する。"""
    repository_root = _initialize_repository(tmp_path)
    artifact_path = Path(f"staged-artifact-{uuid4().hex}")
    (repository_root / artifact_path).write_text("generated\n", encoding="utf-8")
    (repository_root / ".gitignore").write_text("", encoding="utf-8")
    _git(repository_root, "add", ".gitignore", artifact_path.as_posix())
    _git(
        repository_root,
        "-c",
        "user.name=Test User",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--quiet",
        "--no-gpg-sign",
        "-m",
        "baseline",
    )
    (repository_root / ".gitignore").write_text(
        f"/{artifact_path.as_posix()}\n",
        encoding="utf-8",
    )
    _git(repository_root, "add", ".gitignore")

    expected = _tracked_ignored_paths(repository_root, tmp_path)
    committed_snapshot_mutant = _head_snapshot_mutant(repository_root, tmp_path)

    assert expected == (artifact_path,)
    assert committed_snapshot_mutant == ()
    with pytest.raises(AssertionError):
        assert committed_snapshot_mutant == expected
