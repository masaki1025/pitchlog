"""ordinary appendの実末尾fastpathと既O4/O1/O2への委譲。"""

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch
from uuid import UUID

import pytest

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.repositories.ordinary_order import (
    ORDINARY_ORDER_OPERATIONS,
    OrdinaryOrderSummaryToken,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.ordering import _assign_ordinary_append_d2


def _tail(d2):
    values = {column.name: None for column in OperationEvent.__table__.c}
    values.update(
        id=str(UUID(int=9)), game_id=str(UUID(int=1)), tenant_id=str(UUID(int=2)), d2=d2
    )
    return values


@pytest.mark.parametrize(
    "tail,desired,expected", [(None, 1, 1), (0, 1000, 1000), (1001, 2001, 2001)]
)
def test_append_fastpath_uses_one_db_summary(tail, desired, expected):
    """実末尾後のappendだけ一封筒で返す。"""
    seen = []

    def run_function(token):
        seen.append(type(token))
        return SimpleNamespace(
            rows=(
                (
                    json.dumps(
                        {
                            "tail": None if tail is None else _tail(tail),
                            "duplicate": False,
                            "recovery_generation": 1,
                        }
                    ),
                ),
            )
        )

    scope = SimpleNamespace(run_function=run_function, _bound_tenant_id=UUID(int=2))
    with patch("pitchlog.sync.ordering._assign_d2") as old:
        assert (
            _assign_ordinary_append_d2(
                cast(_TenantTransaction, scope), UUID(int=1), desired
            )
            == expected
        )
        old.assert_not_called()
    assert seen == [OrdinaryOrderSummaryToken]


def test_o4_duplicate_precedes_ordinary_append_shortcut():
    """同時に末尾後でも全試合の重複があればO4。"""
    scope = SimpleNamespace(
        run_function=lambda token: SimpleNamespace(
            rows=(
                (
                    json.dumps(
                        {
                            "tail": _tail(1001),
                            "duplicate": True,
                            "recovery_generation": 1,
                        }
                    ),
                ),
            )
        ),
        _bound_tenant_id=UUID(int=2),
    )
    assert (
        _assign_ordinary_append_d2(cast(_TenantTransaction, scope), UUID(int=1), 2001)
        is None
    )


def test_old_o1_o2_kernel_is_reused_for_nonappend():
    """過去位置の採番は既唯一核のまま。"""
    scope = SimpleNamespace(
        run_function=lambda token: SimpleNamespace(
            rows=(
                (
                    json.dumps(
                        {
                            "tail": _tail(1001),
                            "duplicate": False,
                            "recovery_generation": 1,
                        }
                    ),
                ),
            )
        ),
        _bound_tenant_id=UUID(int=2),
    )
    with patch("pitchlog.sync.ordering._assign_d2", return_value=999) as old:
        assert (
            _assign_ordinary_append_d2(
                cast(_TenantTransaction, scope), UUID(int=1), 1000
            )
            == 999
        )
        old.assert_called_once_with(scope, UUID(int=1), 1000)


def test_fixed_summary_sql_is_bounded_and_aggregate_stays_in_db():
    """閉SQLAlchemyは単一固定関数のまま、集約は有限SQLbody。"""
    from pitchlog.authz.ordinary_order_sql import candidate_order_function_bodies

    sql = candidate_order_function_bodies()["read_ordinary_order_summary"]
    assert "GROUP BY e.d2 HAVING pg_catalog.count(*)>1 LIMIT 1" in sql
    assert "ORDER BY e.d2 DESC,e.id DESC LIMIT 1" in sql
    assert sql.count("e.tenant_id=p_tenant_id AND e.game_id=p_game_id") == 2
    assert "session_user" in sql and "current_user" in sql
    assert ORDINARY_ORDER_OPERATIONS[0].max_rows == 1
