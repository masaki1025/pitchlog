"""タイブレーク開始の評価済み一回frameを同TX固定SQLへ貸与する。"""

from __future__ import annotations

from contextlib import contextmanager

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.nonplay_prefix import _run
from pitchlog.sync.tiebreak_start_execution import (
    _EXECUTIONS,
    TiebreakStartExecutionError,
    _live,
    tiebreak_start_preparation,
)

_WRITE_CALLS: dict[object, list] = {}


def assert_tiebreak_start_write_call(handle, operation) -> None:
    """同一投影区間の元tokenだけを検査する。"""
    loan = _WRITE_CALLS.get(handle._state_key)
    if loan is None or loan[1] is not operation or loan[2] is not False:
        raise TiebreakStartExecutionError("タイブレーク開始の固定SQL資格がありません")
    state, token, _used = loan
    _live(state)
    if (
        state.handle is not handle
        or state.phase != "consumed"
        or token.request_json != operation.request_json
    ):
        raise TiebreakStartExecutionError("タイブレーク開始の同TX SQL原本が不一致です")


def consume_tiebreak_start_write_call(handle, operation) -> None:
    """Root dispatcherで固定SQLの直前に一回だけ消費する。"""
    assert_tiebreak_start_write_call(handle, operation)
    _WRITE_CALLS[handle._state_key][2] = True


@contextmanager
def _write_call(state, token):
    """実一回frame/同sourceへのSQL貸与を失効させる。"""
    key = state.handle._state_key
    if key in _WRITE_CALLS:
        raise TiebreakStartExecutionError("タイブレーク開始SQLの再入です")
    loan = [state, token, False]
    _WRITE_CALLS[key] = loan
    try:
        yield
        if loan[2] is not True:
            raise TiebreakStartExecutionError("タイブレーク開始SQL資格が消費されません")
    finally:
        if _WRITE_CALLS.get(key) is loan:
            del _WRITE_CALLS[key]


def project_nonplay_tiebreak_start(handle, event, writer) -> None:
    """保存済eventの元参照を固定SQLで検証しCPを一回更新する。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.projected is not event or state.writer is not writer:
        raise TiebreakStartExecutionError("タイブレーク開始の保存投影が未発行です")
    preparation = tiebreak_start_preparation(handle, event, writer)
    from pitchlog.repositories.nonplay_prefix import _ConsumeNonplayTiebreakStart

    token = _ConsumeNonplayTiebreakStart(_canonical_json(preparation))
    with _write_call(state, token):
        rows = _run(handle, state.source, state.event, token)
    if rows != ((True,),) or type(rows[0][0]) is not bool:
        raise TiebreakStartExecutionError(
            "タイブレーク開始の同TX CP保存結果が不一致です"
        )
    state.phase = "projected"


def require_tiebreak_start_projected(handle, event) -> None:
    """同元要求の実SQL完了だけを成功とする。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None or state.event is not event or state.phase != "projected":
        raise TiebreakStartExecutionError("タイブレーク開始の保存完了がありません")
    _live(state)
