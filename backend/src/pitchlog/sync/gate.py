"""RG1 の事前読取とコミット直前の再検証を共通化する。

静的なポート検査は補助であり安全境界ではない。登録表の変更にはコア領域の
敵対レビューと人間の逐行確認が要り、本物の投影には U-X1 の DB 遮断を要する。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import port_guard
from pitchlog.sync.ports import PortWriter, RecordingRightsPort, _issue_port_writer
from pitchlog.sync.tokens import GameReadToken


class RG1Blocked(RuntimeError):
    """RG1 が閉じているか、ポートの読取に失敗した。"""


@dataclass(slots=True)
class GatedWriter:
    """一イベントの書き手と、⑧を必要とする書き込みの印。"""

    writer: PortWriter
    written: bool = False

    def mark_written(self) -> None:
        """この取引に確定すべき書き込みがあることを示す。"""
        self.written = True


def game_accessible(
    context: TenantContext,
    game_id: UUID,
    open_scope: Callable[[TenantContext], AbstractContextManager[_TenantTransaction]],
) -> bool:
    """③で自テナントの試合だけを非ロックで確かめる。"""
    with open_scope(context) as scope:
        rows = scope.run(GameReadToken(game_id)).rows
    if len(rows) > 1:
        raise RuntimeError("認可対象の試合行が複数ある")
    return bool(rows)


def read_before_d5(rights: RecordingRightsPort, writer: PortWriter) -> None:
    """③-a の非ロック読取を行い、確認不能も閉鎖として扱う。"""
    port_guard.require_registered_port(rights)
    try:
        open_for_writes = rights.read_rg1_before_d5(writer)
    except Exception as error:
        raise RG1Blocked("RG1 の事前読取に失敗") from error
    if open_for_writes is not True:
        raise RG1Blocked("復元調整中")


def check_before_commit(rights: RecordingRightsPort, writer: PortWriter) -> None:
    """⑧ の共有ロック読取を行い、確認不能なら取引全体を戻す。"""
    try:
        open_for_writes = rights.check_rg1_before_commit(writer)
    except Exception as error:
        raise RG1Blocked("RG1 のコミット前読取に失敗") from error
    if open_for_writes is not True:
        raise RG1Blocked("復元調整中")


@contextmanager
def gated_writer(
    scope: _TenantTransaction, rights: RecordingRightsPort
) -> Iterator[GatedWriter]:
    """③-a を全要求で行い、書き込みがある場合だけ⑧を行う。"""
    writer = _issue_port_writer(scope.run)
    gated = GatedWriter(writer)
    try:
        read_before_d5(rights, writer)
        yield gated
        if gated.written:
            check_before_commit(rights, writer)
    finally:
        writer._close()


@contextmanager
def delivery_writer(
    scope: _TenantTransaction, rights: RecordingRightsPort
) -> Iterator[PortWriter]:
    """配信取引には③-a だけを適用する。"""
    writer = _issue_port_writer(scope.run)
    try:
        read_before_d5(rights, writer)
        yield writer
    finally:
        writer._close()


@contextmanager
def gated_e1_writer(
    scope: _TenantTransaction, rights: RecordingRightsPort
) -> Iterator[GatedWriter]:
    """実bound E1だけを判定phaseへ束縛し、既legacy gateは変更しない。"""
    from pitchlog.repositories.transaction import _port_predecision_phase

    writer = _issue_port_writer(scope.run)
    gated = GatedWriter(writer)
    try:
        with _port_predecision_phase(scope, "rg1-precheck"):
            read_before_d5(rights, writer)
        yield gated
        if gated.written:
            with _port_predecision_phase(scope, "rg1-commit"):
                check_before_commit(rights, writer)
    finally:
        writer._close()
