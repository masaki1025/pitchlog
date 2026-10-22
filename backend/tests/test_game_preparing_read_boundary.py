"""preparing read 候補の実行前境界と未登録 token の拒否を検査する。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import bindparam, select

from pitchlog.db.game_state.models import Game
from pitchlog.db.tenant_isolation.models import TeamRecord
from pitchlog.repositories.base import (
    _operation_spec,
    _TenantScopedOperation,
    _validate_prepared_statement,
)
from pitchlog.repositories.games import (
    PREPARING_GAME_READ_OPERATIONS,
    PreparingGameDetailToken,
    PreparingGameListToken,
)
from pitchlog.repositories.tokens import TenantOperationToken

_GAME_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.parametrize("index", [0, 1])
def test_preparing_read_rejects_missing_tenant_condition(index: int) -> None:
    """候補登録の表が正しくても tenant 条件を欠く文を拒否する。"""
    spec = PREPARING_GAME_READ_OPERATIONS[index]
    games = Game.__table__
    statement = (
        select(games.c.id)
        .where(games.c.status == bindparam("status"))
        .where(games.c.trashed_at.is_(None))
        .where(games.c.hidden_at.is_(None))
        .limit(bindparam("limit"))
    )
    with pytest.raises(RuntimeError, match="tenant_id"):
        _TenantScopedOperation(spec.capability_id, statement, spec.tenant_column)


@pytest.mark.parametrize("index,limit", [(0, 102), (1, 2)])
def test_preparing_read_rejects_limit_above_registered_max(
    index: int, limit: int
) -> None:
    """一覧の上限と詳細の1件上限を束縛値で検査する。"""
    spec = PREPARING_GAME_READ_OPERATIONS[index]
    with pytest.raises(RuntimeError, match="LIMIT"):
        _validate_prepared_statement(
            spec,
            spec.statement,
            {"tenant_id": uuid4(), "status": "preparing", "limit": limit},
        )


@pytest.mark.parametrize("index", [0, 1])
def test_preparing_read_rejects_non_preparing_status(index: int) -> None:
    """SQL が status bind を持っていても別状態の値を拒否する。"""
    spec = PREPARING_GAME_READ_OPERATIONS[index]
    with pytest.raises(RuntimeError, match="status"):
        _validate_prepared_statement(
            spec,
            spec.statement,
            {"tenant_id": uuid4(), "status": "started", "limit": 1},
        )


@pytest.mark.parametrize("index", [0, 1])
def test_preparing_read_rejects_other_table(index: int) -> None:
    """同名の tenant 列を持つ別表への文を流用できない。"""
    spec = PREPARING_GAME_READ_OPERATIONS[index]
    teams = TeamRecord.__table__
    statement = (
        select(teams.c.id)
        .where(teams.c.tenant_id == bindparam("tenant_id"))
        .limit(bindparam("limit"))
    )
    with pytest.raises(RuntimeError):
        _validate_prepared_statement(spec, statement)


@dataclass(frozen=True, slots=True)
class _FakeReadToken(TenantOperationToken):
    """製品登録に存在しない別 operation の token。"""

    @property
    def capability_id(self) -> str:
        """既存 capability を名乗る。"""
        return "CAP:games:read"


@dataclass(frozen=True, slots=True)
class _ListTokenSubclass(PreparingGameListToken):
    """登録候補の継承型で exact 型検査を試す。"""


@pytest.mark.parametrize(
    "operation",
    [
        PreparingGameListToken(),
        PreparingGameDetailToken(_GAME_ID),
        _FakeReadToken(),
        _ListTokenSubclass(),
    ],
)
def test_real_registry_rejects_preparing_candidates_and_forged_tokens(
    operation: TenantOperationToken,
) -> None:
    """候補・偽 token・サブクラスを製品登録済みとして扱わない。"""
    with pytest.raises(RuntimeError, match="未登録または偽造"):
        _operation_spec(operation)


def test_candidate_prepare_rejects_other_operation_type() -> None:
    """一覧候補の prepare へ詳細 token を渡しても操作を混同しない。"""
    with pytest.raises(ValueError, match="一覧 token"):
        PREPARING_GAME_READ_OPERATIONS[0].prepare(PreparingGameDetailToken(_GAME_ID))
