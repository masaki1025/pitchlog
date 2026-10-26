"""実scope・実leaseの両方に結合する短命writer資格を発行する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pitchlog.sync.control_provider.binding_control import _BindingLease


class WriterBindingUnavailable(RuntimeError):
    """同writerまたは真正leaseを確認できない。秘密を例外へ含めない。"""


@dataclass(frozen=True, slots=True)
class WriterIdentity:
    """自己writerから取得したPG identity。単体では資格ではない。"""

    system_identifier: str
    database_oid: str
    postmaster_started_at: datetime
    backend_pid: int
    backend_start: datetime
    transaction_id: str

    def __post_init__(self) -> None:
        """xid8を符号付き整数へ狭めず、曖昧なidentityを拒否する。"""
        if (
            any(
                type(v) is not str or re.fullmatch(r"[1-9][0-9]*", v) is None
                for v in (
                    self.system_identifier,
                    self.database_oid,
                    self.transaction_id,
                )
            )
            or not 0 < int(self.transaction_id) < 2**64
            or not 0 < int(self.system_identifier) < 2**64
            or not 0 < int(self.database_oid) < 2**32
            or type(self.backend_pid) is not int
            or not 0 < self.backend_pid < 2**31
            or any(
                type(v) is not datetime or v.utcoffset() is None
                for v in (self.postmaster_started_at, self.backend_start)
            )
        ):
            raise WriterBindingUnavailable("writer identityが不正")

    def wire(self) -> dict[str, object]:
        """内部channelの閉じた観測値へ写す。nonceを含めない。"""
        return {
            "system_identifier": self.system_identifier,
            "database_oid": self.database_oid,
            "postmaster_started_at": self.postmaster_started_at.isoformat(),
            "backend_pid": self.backend_pid,
            "backend_start": self.backend_start.isoformat(),
            "transaction_id": self.transaction_id,
        }


_ISSUER = object()
_LIVE_BINDINGS: dict[object, _LiveWriterBinding] = {}


class _LiveWriterBinding:
    """同一scopeの寿命とnonceを結び、外部scalarから生成させない。"""

    __slots__ = ("_handle", "_owner", "_identity", "_lease", "_used")

    def __init__(
        self,
        handle,
        owner,
        identity: WriterIdentity,
        lease: _BindingLease,
        creation: object,
    ) -> None:
        """private発行口の同writer確認後だけ生成する。"""
        if creation is not _ISSUER:
            raise WriterBindingUnavailable("writer資格の発行元が不正")
        self._handle, self._owner, self._identity, self._lease, self._used = (
            handle,
            owner,
            identity,
            lease,
            False,
        )

    def assert_current(self) -> None:
        """実leaseと同top-level TXをその場で再検証する。"""
        from pitchlog.repositories.writer_binding import _AssertWriterBindingToken

        if self._used:
            raise WriterBindingUnavailable("writer資格が失効している")
        self._handle._assert_writer_lifetime(self._owner)
        self._handle._assert_rg1_lease()
        self._lease.check()
        self._handle.run_function(
            _AssertWriterBindingToken(
                self._lease.attempt_id,
                self._lease.phase_id,
                self._lease.nonce,
                self._lease.device_id,
                self._lease.game_id,
            )
        )
        self._handle._assert_writer_lifetime(self._owner)


def _issue_live_writer_binding(handle, lease: _BindingLease) -> _LiveWriterBinding:
    """実scopeのidentityとactual leaseが一致した場合だけ資格を発行する。"""
    from pitchlog.repositories.transaction import _TenantTransaction
    from pitchlog.repositories.writer_binding import _ReadWriterIdentityToken
    from pitchlog.sync.control_provider.binding_control import _BindingLease

    if type(handle) is not _TenantTransaction or type(lease) is not _BindingLease:
        raise WriterBindingUnavailable("実writer/leaseの私有型が必要")
    owner = handle._writer_lifetime()
    identity = WriterIdentity(*handle.run_function(_ReadWriterIdentityToken()).rows[0])
    if identity != lease.identity or owner[0] in _LIVE_BINDINGS:
        raise WriterBindingUnavailable("writer/leaseの結合が不一致")
    bound = _LiveWriterBinding(handle, owner, identity, lease, _ISSUER)
    try:
        bound.assert_current()
    except BaseException:
        lease.abandon()
        raise
    _LIVE_BINDINGS[owner[0]] = bound
    return bound


def _before_writer_finish(handle) -> None:
    """PG確定直前に実TX/leaseを再検査する。"""
    key = handle._state_key
    if key in _LIVE_BINDINGS:
        _LIVE_BINDINGS[key].assert_current()


def _after_writer_finish(key: object) -> None:
    """PG終了後だけ権威側の入口閉鎖/別TX観測を開始する。"""
    bound = _LIVE_BINDINGS.pop(key, None)
    if bound is not None:
        bound._used = True
        bound._lease.finish()
