"""閲覧実環境試験の共通lockと正規CURRENT49配置の読取確認。"""

import json
from contextlib import contextmanager
from pathlib import Path

from .test_d03_normal49_http import _assert_normal49


@contextmanager
def viewer_log_directory():
    """自分のtest harnessログだけをcacheへ分離する。"""
    from . import test_screen_start_e2e as harness

    previous = harness._LOGS
    target = Path.home() / ".cache/pitchlog/viewer-actual-author-20261108/browser-logs"
    target.mkdir(parents=True, exist_ok=True)
    harness._LOGS = target
    try:
        yield
    finally:
        harness._LOGS = previous


def assert_current_viewer_catalog(admin):
    """後差込なしで正常49とviewer2関数のowner/ACLを確認する。"""
    _assert_normal49(admin)
    for identity in (
        "sync_right_api.read_viewer_effective_version(uuid,uuid,bigint)",
        "sync_right_api.read_viewer_play_prefix_history_page("
        "uuid,uuid,bigint,bigint,uuid,bigint,bigint,bigint,bigint,bigint,uuid,integer)",
    ):
        assert admin.execute(
            "SELECT r.rolname,p.prosecdef,EXISTS(SELECT 1 FROM pg_catalog.aclexplode("
            "COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a "
            "WHERE a.grantee=0 AND a.privilege_type='EXECUTE') "
            "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles r ON r.oid=p.proowner "
            "WHERE p.oid=pg_catalog.to_regprocedure(%s)",
            (identity,),
        ).fetchone() == ("pitchlog_sync_right_fn_owner", True, False)
        assert admin.execute(
            "SELECT has_function_privilege('pitchlog_app',%s,'EXECUTE')",
            (identity,),
        ).fetchone() == (True,)


def save_viewer_evidence(name, value):
    """公開試験結果だけをcacheへ固定し、Cookie/資格を出さない。"""
    target = Path.home() / ".cache/pitchlog/viewer-actual-author-20261108"
    target.mkdir(parents=True, exist_ok=True)
    (target / (name + ".json")).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )
