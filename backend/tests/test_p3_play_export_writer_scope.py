"""P3 CSVは公開handleにSessionを足さず既私有writer窓口を使う。

実型handle/Sessionと実registryを既fixtureから借りる。SQL/認可は無DBの
明示doubleであり、P3実frame mint/実DB書込成功の代用品にはしない。
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session
from test_stats_native_flush import flush_rig as flush_rig

from pitchlog.repositories import transaction
from pitchlog.sync.play_export_p3_producer import _assert_p3_sql_scope
from pitchlog.sync.play_export_producer import PlayExportWriterUnavailable
from pitchlog.sync.stats_native_flush import (
    StatsNativeFlushError,
    _assert_scope,
    _capture_scope,
)


def test_actual_handle_captures_registry_session_without_public_session(flush_rig):
    """真正型の既閉registryからprivate scopeだけへSessionを束縛する。"""
    rig = flush_rig
    assert type(rig.handle) is transaction._TenantTransaction
    assert not hasattr(rig.handle, "session")
    scope = _capture_scope(rig.handle, rig.writer)
    assert scope.handle is rig.handle and scope.writer is rig.writer
    assert type(scope.session) is Session and scope.session is rig.session
    assert scope.runtime is transaction._TRANSACTION_RUNTIMES[rig.key]
    assert scope.bound is rig.bound and scope.nonce == rig.bound._lease.nonce
    _assert_scope(scope)
    assert rig.calls == []


@pytest.mark.parametrize(
    "mutation", ["runtime-tuple", "runtime-session", "private-session"]
)
def test_changed_runtime_or_session_is_not_a_new_sql_window(
    flush_rig, monkeypatch, mutation
):
    """同値tuple/別Session/偽private参照へ差し替えたらSQL前に拒否する。"""
    rig = flush_rig
    scope = _capture_scope(rig.handle, rig.writer)
    extra = Session()
    try:
        if mutation == "runtime-tuple":
            monkeypatch.setitem(
                transaction._TRANSACTION_RUNTIMES, rig.key, (rig.session, object())
            )
        elif mutation == "runtime-session":
            monkeypatch.setitem(
                transaction._TRANSACTION_RUNTIMES, rig.key, (extra, object())
            )
        else:
            scope = replace(scope, session=extra)
        with pytest.raises(StatsNativeFlushError):
            _assert_scope(scope)
        assert rig.calls == []
    finally:
        extra.close()


def test_free_session_attribute_or_wrong_p3_source_is_rejected_before_sql(flush_rig):
    """session属性を付けたfake値をP3実行資格へ昇格しない。"""
    rig = flush_rig
    scope = _capture_scope(rig.handle, rig.writer)
    # 偽contextは不一致の負例だけ。P3 getter/認可をstubして肯定しない。
    context = SimpleNamespace(
        source=SimpleNamespace(bound=object(), context=rig.handle._context),
        nonce=scope.nonce,
    )
    for value in (SimpleNamespace(session=rig.session), scope):
        with pytest.raises(PlayExportWriterUnavailable):
            _assert_p3_sql_scope(rig.handle, rig.event, rig.writer, context, value)
    assert rig.calls == []
