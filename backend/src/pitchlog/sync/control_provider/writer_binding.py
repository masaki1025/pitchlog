"""実scope・実leaseの両方に結合する短命writer資格を発行する。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pitchlog.sync.control_provider.binding_control import _BindingLease
    from pitchlog.sync.source_binding import E1Receipt


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

    __slots__ = ("_handle", "_owner", "_identity", "_lease", "_used", "_phase_snapshot")

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
        self._phase_snapshot = lease._phase_snapshot

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

    def assert_event_source(self, binding, *, context, request, event, phase):
        """実RPC snapshotと当該sourceを同writerで再照合し、純値だけを返す。"""
        import json
        from uuid import UUID

        from pitchlog.sync.control_provider.binding_control import _phase_wire
        from pitchlog.sync.control_provider.evidence import EventPhaseBinding
        from pitchlog.sync.source_binding import read_selected_event_source

        if (
            self._used
            or _LIVE_BINDINGS.get(self._owner[0]) is not self
            or self._handle._context is not context
            or self._lease._phase_snapshot != self._phase_snapshot
            or type(phase) is not EventPhaseBinding
            or type(phase.position) is not int
            or type(phase.d1) is not int
            or type(phase.attempt.event_count) is not int
        ):
            raise WriterBindingUnavailable("実phaseと入力sourceが不一致")
        self.assert_current()
        value = read_selected_event_source(
            binding, context=context, request=request, event=event
        )
        try:
            snapshot = json.loads(self._phase_snapshot)
            actual = snapshot["phase"]
            phase_wire = _phase_wire(
                phase, UUID(actual["authority_id"]), actual["control_version"]
            )
            if (
                snapshot["tenant_id"] != str(context.tenant_id)
                or actual != phase_wire
                or value.origin != "e1"
                or value.request_fingerprint != actual["request_fingerprint"]
                or value.event_fingerprint != actual["event_fingerprint"]
                or value.position != phase.position
                or event.d1 != phase.d1
                or event.d5 != actual["d5"]
                or request.game_id != actual["game_id"]
                or request.d4 != actual["wire_d4"]
                or actual["codec_version"] != 1
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise WriterBindingUnavailable("実phaseと入力sourceが不一致") from None
        self.assert_current()
        return value


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


class _DevicePresentation:
    """U11実issuer専用の私有参照。3Bに自由発行器は設けない。"""

    __slots__ = ()

    def __new__(cls):
        raise WriterBindingUnavailable("実端末提示が未発行")


@dataclass(frozen=True, slots=True, repr=False)
class _DevicePresentationState:
    """資格digestを同じ実受付とdeviceへ閉じて保持する未発行state形。"""

    receipt: E1Receipt
    context: object
    request: object
    reference_device: object
    credential_digest: bytes = field(repr=False)


_DEVICE_PRESENTATIONS: dict[_DevicePresentation, _DevicePresentationState] = {}


def _issue_device_presentation(
    receipt, entry_token, *, reference_device, credential_digest
) -> _DevicePresentation:
    """同一HTTP受付の生存期間だけ有効な実端末提示を一度だけ発行する。

    受付は同じ entry_token で開いたものだけを受け、資格は正規化せずに
    既存の単一 digest 関数が作った32byteだけを保持する。受付が無効・別要求・
    発行済みのいずれでも閉拒否し、値や資格を例外へ含めない。

    Args:
        receipt: 同HTTP入口が開いた E1 受付。
        entry_token: 同入口が発行した不透明token。
        reference_device: 要求ヘッダの端末ID。
        credential_digest: 端末資格のSHA-256（32byte）。

    Returns:
        同受付に閉じた実端末提示。

    Raises:
        WriterBindingUnavailable: 受付不一致・入力不正・重複発行の場合。
    """
    from uuid import UUID

    from pitchlog.sync.source_binding import (
        _attach_device_presentation,
        _receipt_for_entry,
    )

    if (
        type(reference_device) is not UUID
        or type(credential_digest) is not bytes
        or len(credential_digest) != 32
    ):
        raise WriterBindingUnavailable("実端末提示の入力が不正")
    try:
        state = _receipt_for_entry(receipt, entry_token)
    except ValueError:
        raise WriterBindingUnavailable("実端末提示の受付が不一致") from None
    presentation = object.__new__(_DevicePresentation)
    try:
        _attach_device_presentation(state, presentation)
    except ValueError:
        raise WriterBindingUnavailable("実端末提示を発行できない") from None
    _DEVICE_PRESENTATIONS[presentation] = _DevicePresentationState(
        receipt,
        state.context,
        state.request,
        reference_device,
        credential_digest,
    )
    return presentation


def _drop_device_presentations(owner) -> None:
    """受付の寿命終了時に、同受付へ結んだ提示だけを破棄する。"""
    for presentation, state in tuple(_DEVICE_PRESENTATIONS.items()):
        if state.receipt is owner:
            del _DEVICE_PRESENTATIONS[presentation]


def _qualified_device_digest(bound, presentation):
    """Raw scalar/偽参照/別requestから実credentialを作らない。"""
    import json
    from uuid import UUID

    from pitchlog.sync.source_binding import _receipt

    if type(presentation) is not _DevicePresentation:
        raise WriterBindingUnavailable("実端末提示が未発行")
    state = _DEVICE_PRESENTATIONS.get(presentation)
    if type(state) is not _DevicePresentationState:
        raise WriterBindingUnavailable("実端末提示が未発行")
    try:
        owner = _receipt(state.receipt)
        phase = json.loads(bound._phase_snapshot)
        if (
            owner.device_presentation is not presentation
            or owner.context is not state.context
            or owner.request is not state.request
            or bound._handle._context is not state.context
            or type(state.reference_device) is not UUID
            or state.reference_device != bound._lease.device_id
            or str(owner.tenant_id) != phase["tenant_id"]
            or owner.source.request_fingerprint != phase["phase"]["request_fingerprint"]
            or owner.request.game_id != str(bound._lease.game_id)
            or type(state.credential_digest) is not bytes
            or len(state.credential_digest) != 32
        ):
            raise ValueError
    except Exception:
        raise WriterBindingUnavailable("実端末提示の由来が不一致") from None
    return state.credential_digest


def _recheck_bound_device(bound, presentation):
    """真正提示だけをactual lease付き既bind_deviceへ渡す有限経路。"""
    from pitchlog.repositories.transaction import _port_predecision_phase
    from pitchlog.sync.tokens import PortBindCurrentDeviceToken

    digest = _qualified_device_digest(bound, presentation)
    with _port_predecision_phase(bound._handle, "device"):
        rows = bound._handle.run(PortBindCurrentDeviceToken(digest)).rows
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not bool:
        raise WriterBindingUnavailable("実端末資格の結果が不正")
    return rows[0][0]


def _verify_bound_device(bound, reference_device, game_id, *, presentation):
    """文脈二段判定。別端末→別試合の先行後にだけ実DB再照合する。"""
    from uuid import UUID

    if (
        type(bound) is not _LiveWriterBinding
        or _LIVE_BINDINGS.get(bound._owner[0]) is not bound
        or type(reference_device) is not UUID
        or type(game_id) is not str
    ):
        raise WriterBindingUnavailable("実端末文脈が不一致")
    bound.assert_current()
    if bound._lease.device_id != reference_device:
        return "different_device"
    if str(bound._lease.game_id) != game_id:
        return "different_game"
    matches = _recheck_bound_device(bound, presentation)
    if type(matches) is not bool:
        raise WriterBindingUnavailable("実端末資格の結果が不正")
    return "match" if matches else "credential_mismatch"
