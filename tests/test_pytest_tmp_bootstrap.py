"""scripts/pytest_tmp_bootstrap.py の単体テストとルート配線の実測。"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import NoReturn

import pytest

from scripts import pytest_tmp_bootstrap as bootstrap

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _restore_tempfile_tempdir(monkeypatch: pytest.MonkeyPatch) -> None:
    """``activate`` が書き換える ``tempfile.tempdir`` をテスト前後で元へ戻す。"""
    monkeypatch.setattr(tempfile, "tempdir", tempfile.tempdir)


def _make_session(
    user_root: Path,
    name: str,
    *,
    age_days: float,
    lock_age_days: float | None = None,
) -> Path:
    """世代ディレクトリを指定の経過日数で作る。"""
    session = user_root / name
    session.mkdir(parents=True)
    (session / "artifact").write_text("x", encoding="ascii")
    if lock_age_days is not None:
        (session / bootstrap.LOCK_NAME).write_text("", encoding="ascii")
    _set_age(session, age_days)
    if lock_age_days is not None:
        _set_age(session / bootstrap.LOCK_NAME, lock_age_days)
    return session


def _set_age(path: Path, age_days: float) -> None:
    stamp = NOW - age_days * bootstrap.SECONDS_PER_DAY
    os.utime(path, (stamp, stamp))


def test_default_base_uses_xdg_cache_home(tmp_path: Path) -> None:
    base = bootstrap.default_base({"XDG_CACHE_HOME": str(tmp_path / "xdg")}, tmp_path)

    assert base == tmp_path / "xdg" / "pitchlog" / "pytest-tmp"


def test_default_base_falls_back_to_dot_cache(tmp_path: Path) -> None:
    base = bootstrap.default_base({}, tmp_path)

    assert base == tmp_path / ".cache" / "pitchlog" / "pytest-tmp"


def test_default_base_falls_back_when_xdg_is_relative(tmp_path: Path) -> None:
    base = bootstrap.default_base({"XDG_CACHE_HOME": "relative"}, tmp_path)

    assert base == tmp_path / ".cache" / "pitchlog" / "pytest-tmp"


def test_select_base_prefers_override(tmp_path: Path) -> None:
    stream = StringIO()
    environ = {
        bootstrap.ENV_OVERRIDE: str(tmp_path / "override"),
        bootstrap.ENV_TMPDIR: str(tmp_path / "tmpdir"),
    }

    selected = bootstrap.select_base(environ, tmp_path, warning_stream=stream)

    assert selected == (tmp_path / "override", bootstrap.SOURCE_OVERRIDE)
    assert stream.getvalue() == ""


def test_select_base_skips_unusable_override_with_warning(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="ascii")
    stream = StringIO()
    environ = {bootstrap.ENV_OVERRIDE: str(blocker / "sub")}

    selected = bootstrap.select_base(environ, tmp_path, warning_stream=stream)

    assert selected == (tmp_path / ".cache" / "pitchlog" / "pytest-tmp", bootstrap.SOURCE_DEFAULT)
    assert "書き込めない" in stream.getvalue()


def test_select_base_expands_tilde_with_given_home(tmp_path: Path) -> None:
    environ = {bootstrap.ENV_OVERRIDE: "~/pytest-tmp"}

    selected = bootstrap.select_base(environ, tmp_path, warning_stream=StringIO())

    assert selected == (tmp_path / "pytest-tmp", bootstrap.SOURCE_OVERRIDE)


def test_select_base_prefers_debug_temproot_over_override(tmp_path: Path) -> None:
    """pytest 自身の優先度に合わせ、``PYTEST_DEBUG_TEMPROOT`` が上書きに勝つ。

    併用時に上書きを選ぶと、実際の basetemp は temproot 側になるのに
    掃除の対象は上書き側になり、蓄積が残る(レビュー 1 回目の P1)。
    """
    stream = StringIO()
    environ = {
        bootstrap.ENV_DEBUG_TEMPROOT: str(tmp_path / "temproot"),
        bootstrap.ENV_OVERRIDE: str(tmp_path / "override"),
    }

    selected = bootstrap.select_base(environ, tmp_path, warning_stream=stream)

    assert selected == (tmp_path / "temproot", bootstrap.SOURCE_DEBUG_TEMPROOT)
    assert stream.getvalue() == ""


def test_activate_uses_debug_temproot_and_propagates_to_tmpdir(tmp_path: Path) -> None:
    environ = {bootstrap.ENV_DEBUG_TEMPROOT: str(tmp_path / "temproot")}

    activation = bootstrap.activate(
        environ=environ, home=tmp_path, warning_stream=StringIO()
    )

    base = tmp_path / "temproot"
    assert activation == bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEBUG_TEMPROOT)
    assert environ["TMPDIR"] == str(base)
    assert tempfile.tempdir == str(base)


def test_select_base_skips_relative_path_with_warning(tmp_path: Path) -> None:
    stream = StringIO()
    environ = {bootstrap.ENV_OVERRIDE: "relative/pytest-tmp"}

    selected = bootstrap.select_base(environ, tmp_path, warning_stream=stream)

    assert selected == (
        tmp_path / ".cache" / "pitchlog" / "pytest-tmp",
        bootstrap.SOURCE_DEFAULT,
    )
    assert "絶対パス" in stream.getvalue()


def test_select_base_skips_tilde_user_with_warning(tmp_path: Path) -> None:
    stream = StringIO()
    environ = {bootstrap.ENV_TMPDIR: "~other/pytest-tmp"}

    selected = bootstrap.select_base(environ, tmp_path, warning_stream=stream)

    assert selected == (
        tmp_path / ".cache" / "pitchlog" / "pytest-tmp",
        bootstrap.SOURCE_DEFAULT,
    )
    assert "絶対パス" in stream.getvalue()


def test_activate_applies_tmpdir_and_tempfile(tmp_path: Path) -> None:
    stream = StringIO()
    environ: dict[str, str] = {}

    activation = bootstrap.activate(environ=environ, home=tmp_path, warning_stream=stream)

    base = tmp_path / ".cache" / "pitchlog" / "pytest-tmp"
    assert activation == bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)
    assert environ["TMPDIR"] == str(base)
    assert tempfile.tempdir == str(base)
    assert base.is_dir()
    assert stream.getvalue() == ""


def test_activate_keeps_system_default_when_all_candidates_unusable(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="ascii")
    environ = {
        bootstrap.ENV_OVERRIDE: str(blocker / "sub"),
        "XDG_CACHE_HOME": str(blocker / "cache"),
    }
    before = tempfile.tempdir

    activation = bootstrap.activate(
        environ=environ, home=tmp_path, warning_stream=StringIO()
    )

    assert activation.base is None
    assert activation.source == bootstrap.SOURCE_FALLBACK
    assert "TMPDIR" not in environ
    assert tempfile.tempdir == before


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", bootstrap.DEFAULT_KEEP_DAYS), ("0", 0), ("7", 7), ("3.5", 3), ("-1", 3), ("x", 3)],
)
def test_keep_days(raw: str, expected: int) -> None:
    environ = {} if raw == "" else {bootstrap.ENV_KEEP_DAYS: raw}

    assert bootstrap.keep_days(environ, warning_stream=StringIO()) == expected


def test_keep_days_warns_for_invalid_value() -> None:
    stream = StringIO()

    bootstrap.keep_days({bootstrap.ENV_KEEP_DAYS: "x"}, warning_stream=stream)

    assert bootstrap.ENV_KEEP_DAYS in stream.getvalue()


def test_prune_removes_only_stale_sessions(tmp_path: Path) -> None:
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    old = _make_session(user_root, "pytest-1", age_days=4, lock_age_days=4)
    fresh = _make_session(user_root, "pytest-2", age_days=0.5, lock_age_days=0.5)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(
        activation, environ={}, now=NOW, warning_stream=StringIO()
    )

    assert deleted == [old]
    assert not old.exists()
    assert fresh.exists()


def test_prune_keeps_session_with_recent_lock(tmp_path: Path) -> None:
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    running = _make_session(user_root, "pytest-1", age_days=4, lock_age_days=0.01)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=StringIO())

    assert deleted == []
    assert running.exists()


def test_prune_removes_dangling_current_link(tmp_path: Path) -> None:
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    old = _make_session(user_root, "pytest-1", age_days=4, lock_age_days=4)
    link = user_root / bootstrap.CURRENT_LINK_NAME
    link.symlink_to(old)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=StringIO())

    assert not link.is_symlink()


def test_prune_skips_user_owned_bases(tmp_path: Path) -> None:
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    old = _make_session(user_root, "pytest-1", age_days=4, lock_age_days=4)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_TMPDIR)

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=StringIO())

    assert deleted == []
    assert old.exists()


def test_prune_is_disabled_by_zero_keep_days(tmp_path: Path) -> None:
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    old = _make_session(user_root, "pytest-1", age_days=99, lock_age_days=99)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(
        activation,
        environ={bootstrap.ENV_KEEP_DAYS: "0"},
        now=NOW,
        warning_stream=StringIO(),
    )

    assert deleted == []
    assert old.exists()


def test_prune_warns_when_base_cannot_be_scanned(tmp_path: Path) -> None:
    """基底を走査できないときは警告して掃除を飛ばす(例外で試験を止めない)。

    ``Path.glob`` は環境によって権限エラーを握り潰すため、走査失敗を
    再現する ``Path`` の派生で経路を固定する。
    """

    class _Unscannable(Path):
        def glob(self, pattern: str, *, case_sensitive: bool | None = None) -> NoReturn:
            raise PermissionError("denied")

    stream = StringIO()
    activation = bootstrap.Activation(
        base=_Unscannable(tmp_path / "base"), source=bootstrap.SOURCE_DEFAULT
    )

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=stream)

    assert deleted == []
    assert "走査できない" in stream.getvalue()


def test_prune_keeps_session_and_warns_when_removal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """削除が失敗した世代は黙って消えた扱いにせず、警告して残す。"""
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    stale = _make_session(user_root, "pytest-1", age_days=4, lock_age_days=4)
    monkeypatch.setattr(bootstrap.shutil, "rmtree", lambda *args, **kwargs: None)
    stream = StringIO()
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=stream)

    assert deleted == []
    assert stale.exists()
    assert "削除できない" in stream.getvalue()


def test_prune_skips_symlinked_session(tmp_path: Path) -> None:
    """世代ディレクトリの symlink は辿らず、指す先も消さない。"""
    base = tmp_path / "base"
    user_root = base / "pytest-of-ymdms"
    user_root.mkdir(parents=True)
    target = _make_session(tmp_path, "elsewhere", age_days=4, lock_age_days=4)
    link = user_root / "pytest-1"
    link.symlink_to(target, target_is_directory=True)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=StringIO())

    assert deleted == []
    assert link.is_symlink()
    assert target.exists()


def test_prune_skips_symlinked_user_root(tmp_path: Path) -> None:
    """基底直下の利用者ディレクトリが symlink なら辿らない。"""
    base = tmp_path / "base"
    base.mkdir()
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    stale = _make_session(real_root, "pytest-1", age_days=4, lock_age_days=4)
    (base / "pytest-of-ymdms").symlink_to(real_root, target_is_directory=True)
    activation = bootstrap.Activation(base=base, source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=StringIO())

    assert deleted == []
    assert stale.exists()


def test_prune_with_missing_base_is_noop(tmp_path: Path) -> None:
    activation = bootstrap.Activation(base=tmp_path / "missing", source=bootstrap.SOURCE_DEFAULT)

    deleted = bootstrap.prune_stale(activation, environ={}, now=NOW, warning_stream=StringIO())

    assert deleted == []


def test_root_conftest_wiring_redirects_basetemp(tmp_path: Path) -> None:
    """ルート conftest の配線をサブプロセスの実 pytest で実測する。"""
    redirect = tmp_path / "redirected"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "test_wiring.py").write_text(
        "import os\n"
        "\n"
        "\n"
        "def test_basetemp_is_redirected(tmp_path):\n"
        "    assert str(tmp_path).startswith(os.environ['PITCHLOG_TMP_EXPECT'])\n",
        encoding="utf-8",
    )
    environ = dict(os.environ)
    environ[bootstrap.ENV_OVERRIDE] = str(redirect)
    environ["PITCHLOG_TMP_EXPECT"] = str(redirect)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-p",
            "conftest",
            str(scratch / "test_wiring.py"),
        ],
        cwd=REPOSITORY_ROOT,
        env=environ,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
