"""P2 の D2 採番と局所再採番を P1 と共通の確定境界へ組み込む。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.prefix_path import P1PreconditionError, P1Result, _apply_event, _cell
from pitchlog.sync.tokens import (
    OperationEventOrderReadToken,
    OperationEventOrderUpdateToken,
)

_EVENT_COLUMNS = tuple(OperationEvent.__table__.c.keys())
_PAGE_SIZE = 256
_MAX_D2 = 2**63 - 1


def _assign_d2(scope: _TenantTransaction, game_id: UUID, desired: int) -> int | None:
    """O1 の試合行ロック下で空きを先に使い、必要な場合だけ O2 を行う。

    Returns:
        確定する D2。永続化済みの同値を見た場合は ``None``。
    """
    if desired < 0 or desired > _MAX_D2:
        raise P1PreconditionError("P2 の V6 は非負の bigint が必要")

    cursor = -1
    previous: int | None = None
    predecessor: int | None = None
    occupied = False
    left_run: list[tuple[UUID, int]] = []
    right_run: list[tuple[UUID, int]] = []
    right_gap = False
    while True:
        rows = scope.run(OperationEventOrderReadToken(game_id, cursor, _PAGE_SIZE)).rows
        for row in rows:
            value = _cell(row, _EVENT_COLUMNS, "d2")
            identifier = _cell(row, _EVENT_COLUMNS, "id")
            if type(value) is not int or type(identifier) is not UUID:
                raise RuntimeError("D2 順の行の型が不正")
            if value < 0 or value > _MAX_D2:
                raise RuntimeError("永続化済み D2 が bigint の値域外")
            if previous is not None and value == previous:
                return None
            if value < desired:
                predecessor = value
                if previous is not None and value == previous + 1:
                    left_run.append((identifier, value))
                else:
                    left_run = [(identifier, value)]
            elif value == desired:
                occupied = True
                right_run = [(identifier, value)]
            elif occupied and not right_gap:
                if previous is not None and value == previous + 1:
                    right_run.append((identifier, value))
                else:
                    right_gap = True
            previous = value
        if len(rows) < _PAGE_SIZE:
            break
        assert previous is not None
        # D2 だけのキーセットではページ境界を跨ぐ同値を見落とすため再照合する。
        boundary = scope.run(
            OperationEventOrderReadToken(game_id, previous - 1, 2)
        ).rows
        if len(boundary) == 2 and _cell(boundary[0], _EVENT_COLUMNS, "d2") == _cell(
            boundary[1], _EVENT_COLUMNS, "d2"
        ):
            return None
        cursor = previous

    if not occupied:
        return desired
    # V6 は挿入先の位置。直前に空きがあれば、その最大値を新イベントへ与える。
    if desired > 0 and (predecessor is None or predecessor < desired - 1):
        return desired - 1
    if right_run[-1][1] < _MAX_D2:
        # 即時一意索引のため、右の空きから逆順にずらす。
        for identifier, value in reversed(right_run):
            scope.run(OperationEventOrderUpdateToken(identifier, value + 1))
        return desired
    if left_run and left_run[0][1] > 0:
        # bigint 上限に達したときは左の空きから順に詰める。
        for identifier, value in left_run:
            scope.run(OperationEventOrderUpdateToken(identifier, value - 1))
        return desired - 1
    raise P1PreconditionError("D2 の局所再採番に必要な隙間がない")


def _assign_ordinary_append_d2(scope: _TenantTransaction, game_id: UUID, desired: int):
    """既O4の全試合重複判定を維持し、実末尾後のappendだけ全頁走査を省く。"""
    import json

    from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
    from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken

    if type(desired) is not int or not 0 <= desired <= _MAX_D2:
        raise P1PreconditionError("P2 の V6 は非負の bigint が必要")
    rows = scope.run_function(OrdinaryOrderSummaryToken(game_id)).rows
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not str:
        raise RuntimeError("D2実末尾readの型が不正")
    value = json.loads(
        rows[0][0], object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if (
        type(value) is not dict
        or set(value) != {"tail", "duplicate", "recovery_generation"}
        or type(value["duplicate"]) is not bool
        or type(value["recovery_generation"]) is not int
        or not 0 < value["recovery_generation"] < 2**63
    ):
        raise RuntimeError("D2実末尾readの封筒が不正")
    if value["duplicate"]:
        return None
    tail = value["tail"]
    if tail is None:
        return desired
    if (
        type(tail) is not dict
        or set(tail) != set(_EVENT_COLUMNS)
        or tail["game_id"] != str(game_id)
        or tail["tenant_id"] != str(scope._bound_tenant_id)
        or tail["replaced_at"] is not None
        or tail["retired_at"] is not None
        or type(tail["d2"]) is not int
        or not 0 <= tail["d2"] <= _MAX_D2
    ):
        raise RuntimeError("D2実末尾原本の型が不正")
    if desired > tail["d2"]:
        return desired

    # 過去位置のO1/O2は既唯一核へ委ね、順序・D5消費の意味を変えない。
    return _assign_d2(scope, game_id, desired)


def apply_p2_event(
    context: TenantContext,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    v12: object,
) -> P1Result:
    """P2 の一イベントを、共通の T1〜T4・T6 と T5 で確定する。

    Args:
        context: API 層で発行済みのテナント文脈。
        event: D1 と論理位置 V6 を持つ P2 イベント。
        rights: 記録権判定ポート。
        projection: 投影ポート。
        validator: 内容検証ポート。
        v12: 要求レベルの記録権証明。

    Returns:
        一イベントの局所結果。O4 は B3 と A5「拒否」を含む。
    """
    return _apply_event(
        context,
        event,
        rights,
        projection,
        validator,
        v12,
        path="P2",
        order_resolver=_assign_d2,
    )
