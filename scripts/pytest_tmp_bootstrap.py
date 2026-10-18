"""pytest の一時ディレクトリを共有 /tmp からディスク側へ移す起動ヘルパー。

背景: 本機の /tmp は tmpfs(搭載メモリ由来の限られた容量)であり、ルートと
backend の全件試験が ``tmp_path`` 配下へ GB 単位の生成物を書くため、並行実行や
異常終了の残骸で満杯になる(満杯の実測 3 回 — ``docs/development/harness-evaluation.md``)。
pytest が basetemp を置く場所は ``tempfile.gettempdir()`` が決めるため、本モジュールは
``TMPDIR`` と ``tempfile.tempdir`` をディスク側のパスへ向け替える。pytest 自身の
世代保持(直近 3 世代・失敗時に保持)とロックの規則は変えない。

解決順(先頭が優先。**pytest 自身の優先度と一致させる** — ``PYTEST_DEBUG_TEMPROOT`` は
pytest が最優先で参照するため、併用時はこの基底が実際の basetemp になる):

1. ``PYTEST_DEBUG_TEMPROOT``(pytest 公式の basetemp 上書き)
2. ``PITCHLOG_PYTEST_TMPDIR``(本ハーネス専用の上書き)
3. ``TMPDIR``(利用者の明示指定)
4. ``$XDG_CACHE_HOME/pitchlog/pytest-tmp``(既定。未設定時は ``~/.cache/...``)

値は絶対パスだけを使う(先頭 1 個の ``~`` はホームへ展開。``~user`` の形と相対パスは
実行時の cwd に依存して意図しない場所へ生成物を作りうるため、警告して飛ばす。
ただし ``PYTEST_DEBUG_TEMPROOT`` が相対値の場合は pytest 本体が cwd 基準で
``resolve()`` して使い続ける〔退避が無い〕ため、実 basetemp は pytest 側の解決に
従う。``XDG_CACHE_HOME`` の異常値は警告せず ``~/.cache`` へ退避する)。
候補が書込み不能なら警告して次の候補へ退避し、全滅時はシステム既定へ戻す
(試験を止めない。警告は stderr へ書くが、pytest 実行では capture に取り込まれて
通常の画面には出ない — 確認は単体テストや直呼びで行う)。選ばれた基底は ``TMPDIR`` と
``tempfile.tempdir`` の両方へ設定する
(子プロセスへ伝播。由来が 1・3 の場合も利用者の ``TMPDIR`` の値は選ばれた基底へ
置き換わる)。``prune_stale`` は自前の基底(上記 2・4 で選ばれた場合)に限り、
日数上限を超えた世代を実行時に掃除する(既定 3 日 — pytest 自身のロック失効と
同じ長さ。``PITCHLOG_PYTEST_TMP_KEEP_DAYS`` で変更、``0`` で無効)。掃除の発火は
起動ごと(上流は新規世代の作成時のみ)なので、3 日を超えて稼働した実行の世代は
上流より広く対象になりうる。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

ENV_OVERRIDE = "PITCHLOG_PYTEST_TMPDIR"
ENV_DEBUG_TEMPROOT = "PYTEST_DEBUG_TEMPROOT"
ENV_TMPDIR = "TMPDIR"
ENV_KEEP_DAYS = "PITCHLOG_PYTEST_TMP_KEEP_DAYS"

SOURCE_OVERRIDE = "override"
SOURCE_DEBUG_TEMPROOT = "pytest-debug-temproot"
SOURCE_TMPDIR = "tmpdir"
SOURCE_DEFAULT = "default"
SOURCE_FALLBACK = "system-temp"

DEFAULT_KEEP_DAYS = 3
SECONDS_PER_DAY = 60 * 60 * 24
CACHE_DIR_PARTS = ("pitchlog", "pytest-tmp")
USER_ROOT_GLOB = "pytest-of-*"
SESSION_GLOB = "pytest-*"
CURRENT_LINK_NAME = "pytest-current"
LOCK_NAME = ".lock"

# 掃除の対象にする由来(自前の基底だけを掃除し、利用者の TMPDIR の中は触らない)。
PRUNABLE_SOURCES = frozenset({SOURCE_OVERRIDE, SOURCE_DEFAULT})


@dataclass(frozen=True)
class Activation:
    """``activate`` の結果。

    Attributes:
        base: 実際に使う一時ディレクトリの基底。システム既定のままなら ``None``。
        source: 基底の由来(``override`` / ``pytest-debug-temproot`` / ``tmpdir`` /
            ``default`` / ``system-temp`` のいずれか)。
    """

    base: Path | None
    source: str


def _resolve_candidate(value: str, home: Path) -> Path | None:
    """環境変数の値を絶対パスへ解決する。解決できない値は ``None``。

    ``Path.expanduser`` は実環境のホームを参照するため、テストから差し替えられる
    よう ``~`` の展開を自前で行う。``~user`` の形と相対パスは、実行時の cwd に
    依存して意図しない場所へ生成物を作りうるため受け付けない。

    Args:
        value: 環境変数の値(空でないこと)。
        home: ``~`` の展開先。

    Returns:
        絶対パスの候補。``~user`` の形・相対パスなら ``None``。
    """
    if value.startswith("~"):
        parts = Path(value).parts
        if parts and parts[0] == "~":
            return home.joinpath(*parts[1:])
        return None
    path = Path(value)
    return path if path.is_absolute() else None


def default_base(environ: Mapping[str, str], home: Path) -> Path:
    """既定の基底(``$XDG_CACHE_HOME/pitchlog/pytest-tmp``)を返す。

    ``XDG_CACHE_HOME`` が絶対パスでない場合は ``~/.cache`` へ退避する。

    Args:
        environ: 参照する環境変数。
        home: ``XDG_CACHE_HOME`` 未設定時に使うホーム。

    Returns:
        既定の基底パス。
    """
    xdg = environ.get("XDG_CACHE_HOME", "").strip()
    cache = _resolve_candidate(xdg, home) if xdg else None
    return (cache or home / ".cache").joinpath(*CACHE_DIR_PARTS)


def _candidates(
    environ: Mapping[str, str], home: Path, *, warning_stream: TextIO
) -> list[tuple[Path, str]]:
    """優先順の候補(パスと由来)を返す。空値と解決できない値は飛ばす。

    Args:
        environ: 参照する環境変数。
        home: ``~`` の展開先。
        warning_stream: 解決できない値の警告を書く先。

    Returns:
        候補の並び(先頭が最優先)。末尾は常に既定の基底。
    """
    ordered: list[tuple[Path, str]] = []
    for key, source in (
        (ENV_DEBUG_TEMPROOT, SOURCE_DEBUG_TEMPROOT),
        (ENV_OVERRIDE, SOURCE_OVERRIDE),
        (ENV_TMPDIR, SOURCE_TMPDIR),
    ):
        value = environ.get(key, "").strip()
        if not value:
            continue
        resolved = _resolve_candidate(value, home)
        if resolved is None:
            message = f"pytest-tmp: {key}={value!r} は絶対パスでないため候補から外します"
            print(message, file=warning_stream)
            continue
        ordered.append((resolved, source))
    ordered.append((default_base(environ, home), SOURCE_DEFAULT))
    return ordered


def _usable(path: Path) -> bool:
    """ディレクトリを作成でき(既存なら書き込め)るかを試す。

    Args:
        path: 試すパス。

    Returns:
        書き込み可能なら ``True``。
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write-probe-{os.getpid()}"
        probe.write_text("", encoding="ascii")
        probe.unlink()
    except OSError:
        return False
    return True


def select_base(
    environ: Mapping[str, str], home: Path, *, warning_stream: TextIO
) -> tuple[Path, str] | None:
    """書き込み可能な最初の候補を選ぶ。

    書き込み不能な候補はその旨を警告して次へ退避する。

    Args:
        environ: 参照する環境変数。
        home: ``~`` の展開先。
        warning_stream: 退避の警告を書く先。

    Returns:
        選ばれたパスと由来。全候補が書き込み不能なら ``None``。
    """
    for path, source in _candidates(environ, home, warning_stream=warning_stream):
        if _usable(path):
            return path, source
        message = f"pytest-tmp: 候補 {path}(由来 {source})へ書き込めないため次を試します"
        print(message, file=warning_stream)
    return None


def activate(
    *,
    environ: MutableMapping[str, str] | None = None,
    home: Path | None = None,
    warning_stream: TextIO | None = None,
) -> Activation:
    """一時ディレクトリの基底をディスク側へ向け、環境変数と ``tempfile`` へ適用する。

    Args:
        environ: 参照と ``TMPDIR`` の書込みに使う環境変数。省略時は ``os.environ``。
        home: ``~`` の展開に使うホーム。省略時は ``Path.home()``。
        warning_stream: 退避の警告を書く先。省略時は ``sys.stderr``。

    Returns:
        選ばれた基底と由来。全候補が書き込み不能なら ``base=None`` のまま
        (システム既定の一時ディレクトリを使う)。
    """
    active = os.environ if environ is None else environ
    resolved_home = Path.home() if home is None else home
    stream = sys.stderr if warning_stream is None else warning_stream
    selected = select_base(active, resolved_home, warning_stream=stream)
    if selected is None:
        message = "pytest-tmp: 書き込み可能な候補が無いためシステム既定の一時ディレクトリを使います"
        print(message, file=stream)
        return Activation(base=None, source=SOURCE_FALLBACK)
    base, source = selected
    active[ENV_TMPDIR] = str(base)
    tempfile.tempdir = str(base)
    return Activation(base=base, source=source)


def keep_days(environ: Mapping[str, str], *, warning_stream: TextIO) -> int:
    """掃除の日数上限を環境変数から読む。

    Args:
        environ: 参照する環境変数。
        warning_stream: 不正値の警告を書く先。

    Returns:
        日数上限。未設定は既定、不正値は既定へ戻したうえで警告する。
    """
    raw = environ.get(ENV_KEEP_DAYS, "").strip()
    if not raw:
        return DEFAULT_KEEP_DAYS
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        message = (
            f"{ENV_KEEP_DAYS}={raw!r} は 0 以上の整数でないため"
            f"既定 {DEFAULT_KEEP_DAYS} を使います"
        )
        print(message, file=warning_stream)
        return DEFAULT_KEEP_DAYS
    return value


def prune_stale(
    activation: Activation,
    *,
    environ: Mapping[str, str] | None = None,
    now: float | None = None,
    warning_stream: TextIO | None = None,
) -> list[Path]:
    """自前の基底にある古い pytest 世代を削除する。

    対象は ``activate`` が ``override`` / ``default`` として選んだ基底に限る
    (利用者の ``TMPDIR`` や pytest のデバッグ指定の中は掃除しない)。世代の経過は
    セッションディレクトリと ``.lock`` の mtime の新しい方で見積もり、日数上限を
    超えたものだけを消す。削除できなかった世代は警告して残す。

    Args:
        activation: ``activate`` の結果。
        environ: 日数上限の読取りに使う環境変数。省略時は ``os.environ``。
        now: 現在時刻(Unix 秒)。省略時は ``time.time()``。テスト用。
        warning_stream: 警告を書く先。省略時は ``sys.stderr``。

    Returns:
        削除した世代ディレクトリの一覧。
    """
    active = os.environ if environ is None else environ
    stream = sys.stderr if warning_stream is None else warning_stream
    if activation.base is None or activation.source not in PRUNABLE_SOURCES:
        return []
    days = keep_days(active, warning_stream=stream)
    if days <= 0:
        return []
    cutoff = (time.time() if now is None else now) - days * SECONDS_PER_DAY
    return _prune_sessions(activation.base, cutoff, stream)


def _prune_sessions(base: Path, cutoff: float, warning_stream: TextIO) -> list[Path]:
    """基底配下の古い世代ディレクトリを削除する。

    Args:
        base: 一時ディレクトリの基底。
        cutoff: この時刻(Unix 秒)より新しい世代は残す。
        warning_stream: 警告を書く先。

    Returns:
        削除した世代ディレクトリの一覧。
    """
    deleted: list[Path] = []
    try:
        user_roots = sorted(base.glob(USER_ROOT_GLOB))
    except OSError as exc:
        print(f"pytest-tmp: {base} を走査できないため掃除を飛ばします({exc})", file=warning_stream)
        return deleted
    for user_root in user_roots:
        if user_root.is_symlink() or not user_root.is_dir():
            continue
        for session in sorted(user_root.glob(SESSION_GLOB)):
            if session.is_symlink() or not session.is_dir():
                continue
            newest = _newest_mtime(session)
            if newest is None or newest >= cutoff:
                continue
            shutil.rmtree(session, ignore_errors=True)
            if session.exists():
                print(f"pytest-tmp: {session} を削除できないため残します", file=warning_stream)
                continue
            deleted.append(session)
        _remove_dangling_current(user_root)
    return deleted


def _newest_mtime(session: Path) -> float | None:
    """世代ディレクトリと ``.lock`` の mtime の新しい方を返す。

    Args:
        session: 世代ディレクトリ。

    Returns:
        新しい方の mtime。読めない場合は ``None``。
    """
    try:
        newest = session.stat().st_mtime
        lock = session / LOCK_NAME
        if lock.is_file():
            newest = max(newest, lock.stat().st_mtime)
    except OSError:
        return None
    return newest


def _remove_dangling_current(user_root: Path) -> None:
    """削除済みの世代を指す ``pytest-current`` シンボリックリンクを取り除く。

    Args:
        user_root: ``pytest-of-<user>`` ディレクトリ。
    """
    current = user_root / CURRENT_LINK_NAME
    if current.is_symlink() and not current.exists():
        try:
            current.unlink()
        except OSError:
            pass
