"""文言走査の母集団を導出する支援機能。"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WordingScanFile:
    """文言走査の対象となるテキスト成果物。"""

    path: Path
    content: bytes


class WordingScanReadError(RuntimeError):
    """文言走査の候補を読めなかったことを表す。"""

    def __init__(self, path: Path, error: OSError) -> None:
        """読めなかったパスと原因を保持する。

        Args:
            path: リポジトリ相対の候補パス。
            error: 読み取り時に発生した例外。
        """
        self.path = path
        super().__init__(f"文言走査の候補を読めない: {path.as_posix()}: {error}")


def _is_text(content: bytes) -> bool:
    """バイト列を UTF-8 テキストとして扱えるか判定する。"""
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return "\0" not in decoded


def collect_wording_scan_files(
    repository_root: Path,
    roots: Iterable[Path],
    exclusions: frozenset[Path] = frozenset(),
) -> tuple[WordingScanFile, ...]:
    """指定範囲から文言走査対象のテキスト成果物を集める。

    Git が列挙する追跡済み・非 ignore の未追跡ファイルを実際に読み、
    UTF-8 復号可能かつ NUL を含まないものだけを対象とする。

    Args:
        repository_root: 走査する Git リポジトリのルート。
        roots: リポジトリ相対の走査ルート。
        exclusions: 理由を別途持つ、走査対象外のリポジトリ相対パス。

    Returns:
        リポジトリ相対パス順のテキスト成果物。

    Raises:
        WordingScanReadError: Git が列挙した候補を読み取れない場合。
        subprocess.CalledProcessError: Git による列挙に失敗した場合。
    """
    scan_roots = tuple(roots)
    if not scan_roots:
        return ()

    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *(str(path) for path in scan_roots),
        ],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    candidates = sorted(
        {
            Path(raw_path.decode("utf-8"))
            for raw_path in completed.stdout.split(b"\0")
            if raw_path
        }
        - exclusions
    )

    files: list[WordingScanFile] = []
    for path in candidates:
        try:
            content = (repository_root / path).read_bytes()
        except OSError as error:
            raise WordingScanReadError(path, error) from error
        if _is_text(content):
            files.append(WordingScanFile(path=path, content=content))
    return tuple(files)
