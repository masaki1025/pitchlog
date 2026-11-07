"""記録画面専用RR scopeの有限能力と失効を純状態機械で検査する。"""

from contextlib import nullcontext
from uuid import uuid4

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import transaction
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken
from pitchlog.repositories.recorded_snapshot_operations import (
    RecordedEventRowsReadToken,
)
from pitchlog.sync.tokens import GameLockToken, GameReadToken


class _Engine:
    """SQLを実行せずRR/RO要求の実引数だけ捕捉する。"""

    def __init__(self) -> None:
        """開かれたscopeごとの設定を記録する。"""
        self.options: list[dict[str, object]] = []

    def execution_options(self, **options):
        """読取条件を同engineに固定する。"""
        self.options.append(options)
        return self


class _Session:
    """scope発行/失効だけを検査する閉じた接続代役。"""

    def __init__(self, engine) -> None:
        """受け取ったengineを保持する。"""
        self.engine = engine
        self.closed = False
        self.top = _Top()
        self.nested = False

    def get_transaction(self):
        """同TX参照を返す。"""
        return self.top

    def in_nested_transaction(self):
        """savepointの有無を返す。"""
        return self.nested

    def close(self) -> None:
        """終了を記録する。"""
        self.closed = True


class _Top:
    """top-level TX identityとactive状態の代役。"""

    is_active = True


def test_started_read_scope_is_rr_readonly_finite_and_expires(monkeypatch):
    """真正scopeだけが有限readを許し、行lock/終了後再使用を拒否する。"""
    from pitchlog.sync.control_provider import writer_binding

    engine = _Engine()
    sessions = []

    def new_session(value):
        session = _Session(value)
        sessions.append(session)
        return session

    monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
    monkeypatch.setattr(transaction, "Session", new_session)
    monkeypatch.setattr(
        transaction, "_tenant_transaction", lambda session, context: nullcontext()
    )
    monkeypatch.setattr(writer_binding, "_before_writer_finish", lambda handle: None)
    monkeypatch.setattr(writer_binding, "_after_writer_finish", lambda key: None)
    context = make_tenant_context(uuid4())
    game_id = uuid4()

    with transaction.started_snapshot_read_scope(context) as handle:
        assert engine.options == [
            {"isolation_level": "REPEATABLE READ", "postgresql_readonly": True}
        ]
        assert transaction.started_snapshot_read_mode(handle)
        transaction._require_started_read_token(
            handle, GameReadToken(game_id), function=False
        )
        transaction._require_started_read_token(
            handle, RecordedEventRowsReadToken(game_id), function=False
        )
        transaction._require_started_read_token(
            handle, _ReadP3CurrentToken(game_id, 1), function=True
        )
        with pytest.raises(TenantBindingError):
            transaction._require_started_read_token(
                handle, GameLockToken(game_id), function=False
            )
        with pytest.raises(TenantBindingError):
            handle.run_in_savepoint(GameReadToken(game_id))
        original_top = sessions[0].top
        sessions[0].top = _Top()
        with pytest.raises(TenantBindingError):
            transaction.require_started_snapshot_read_scope(handle)
        sessions[0].top = original_top
        sessions[0].nested = True
        with pytest.raises(TenantBindingError):
            transaction.require_started_snapshot_read_scope(handle)
        sessions[0].nested = False
        original_top.is_active = False
        with pytest.raises(TenantBindingError):
            transaction.require_started_snapshot_read_scope(handle)
        original_top.is_active = True
    assert sessions[0].closed
    assert not transaction.started_snapshot_read_mode(handle)
    with pytest.raises(TenantBindingError):
        transaction.require_started_snapshot_read_scope(handle)
