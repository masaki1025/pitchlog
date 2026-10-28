"""保存control phase・専用peer・実業務入口を有限操作で接合する。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import socket
import struct
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from pitchlog.repositories.context import TenantContext
from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    AuthorityBinding,
    EventPhaseBinding,
)
from pitchlog.sync.control_provider.writer_binding import (
    WriterBindingUnavailable,
    WriterIdentity,
)


class BindingOutcome(StrEnum):
    """DB観測とjournal解放条件を区別する閉じた四結果。"""

    UNKNOWN = "UNKNOWN"
    COMMITTED = "COMMITTED"
    ROLLBACK_CONFIRMED = "ROLLBACK_CONFIRMED"
    ENTRY_CLOSED_UNADMITTED = "ENTRY_CLOSED_UNADMITTED"


def _classify_observation(
    *,
    closed: bool,
    identity_valid: bool,
    admissions: int,
    matching: int,
    xid_status: str | None,
) -> BindingOutcome:
    """比較用の閉表。DB実証を代替せず、SQLと独立に対向を固定する。"""
    if not closed or not identity_valid:
        return BindingOutcome.UNKNOWN
    if admissions == 1 and matching == 1 and xid_status in (None, "committed"):
        return BindingOutcome.COMMITTED
    if admissions == 0 and matching == 0:
        if xid_status == "aborted":
            return BindingOutcome.ROLLBACK_CONFIRMED
        if xid_status in ("in progress", "committed"):
            return BindingOutcome.ENTRY_CLOSED_UNADMITTED
    return BindingOutcome.UNKNOWN


def _phase_wire(
    phase: EventPhaseBinding, authority_id: UUID, version: int
) -> dict[str, object]:
    """既F1単球phaseの全値を、制御3原本の閉形式へ写す。"""
    if (
        type(phase) is not EventPhaseBinding
        or phase.position != 1
        or phase.d1 != 1
        or phase.attempt.event_count != 1
        or type(authority_id) is not UUID
        or type(version) is not int
        or version <= 0
    ):
        raise WriterBindingUnavailable("単球phaseが不正")
    a = phase.attempt
    return {
        "authority_id": str(authority_id),
        "control_instance": str(a.authority.control_instance),
        "business_instance": str(a.authority.business_instance),
        "restore_epoch": str(a.authority.restore_epoch),
        "control_version": version,
        "attempt_id": str(a.attempt_id),
        "device_id": str(a.device_id),
        "game_id": str(a.game_id),
        "wire_d4": a.wire_d4,
        "internal_generation": a.internal_generation,
        "codec_version": a.codec_version,
        "request_fingerprint": a.request_fingerprint,
        "phase_id": str(phase.phase_id),
        "d5": str(phase.d5),
        "event_fingerprint": phase.event_fingerprint,
    }


def _writer_from_wire(value: object) -> WriterIdentity:
    """exact閉集合とcanonical日付だけを実型へ戻す。"""
    keys = {
        "system_identifier",
        "database_oid",
        "postmaster_started_at",
        "backend_pid",
        "backend_start",
        "transaction_id",
    }
    if type(value) is not dict or set(value) != keys:
        raise WriterBindingUnavailable("writer観測が不正")
    value = cast(dict[str, Any], value)
    try:
        if any(
            type(value[n]) is not str
            for n in ("postmaster_started_at", "backend_start")
        ):
            raise ValueError
        identity = WriterIdentity(
            value["system_identifier"],
            value["database_oid"],
            datetime.fromisoformat(value["postmaster_started_at"]),
            value["backend_pid"],
            datetime.fromisoformat(value["backend_start"]),
            value["transaction_id"],
        )
        if identity.wire() != value:
            raise ValueError
        return identity
    except (TypeError, ValueError):
        raise WriterBindingUnavailable("writer観測が不正") from None


class _BindingAuthority:
    """root workerの固定PG接続だけからphase照合と入口終結を実行する。"""

    def __init__(self, config: dict[str, Any], issuer: UUID) -> None:
        """root検証済み非秘密設定を受け、公開DSN構築器へしない。"""
        self._config = config
        self._issuer = issuer

    def _call(
        self,
        which: str,
        statement: LiteralString,
        params: tuple[object, ...],
        *,
        write: bool = False,
    ) -> tuple[Any, ...]:
        """固定呼出しごとにactual actorとread-committedを確認する。"""
        from pitchlog.durable_rights_ledger.adapter import _commit, _connection

        with _connection(
            self._config[f"binding_{which}_dsn"], self._config["timeout"]
        ) as c:
            identity = c.execute(
                "SELECT session_user,current_user,"
                "pg_catalog.current_setting('transaction_isolation')"
            ).fetchone()
            if identity != (
                "pitchlog_sync_binding_actor",
                "pitchlog_sync_binding_actor",
                "read committed",
            ):
                raise WriterBindingUnavailable("binding制御主体が不正")
            row = c.execute(statement, params).fetchone()
            if row is None:
                raise WriterBindingUnavailable("binding原本を取得できない")
            if write:
                _commit(c, self._config["timeout"])
            return row

    def validate_request(self, request: dict[str, Any]) -> None:
        """不正な閉入力でlease/journal/制御原本を消費しない。"""
        try:
            if (
                set(request) != {"operation", "tenant_id", "phase", "writer"}
                or request["operation"] != "binding_open"
                or type(request["tenant_id"]) is not str
            ):
                raise ValueError
            tenant = UUID(request["tenant_id"])
            if str(tenant) != request["tenant_id"]:
                raise ValueError
            phase = request["phase"]
            if type(phase) is not dict:
                raise ValueError
            for key, value in self._config["binding_authority"].items():
                if type(phase.get(key)) is not type(value) or phase[key] != value:
                    raise ValueError
            if any(
                type(phase.get(k)) is not int or not 0 < phase[k] < 2**63
                for k in ("internal_generation", "codec_version")
            ):
                raise ValueError
            authority = AuthorityBinding(
                *(
                    UUID(phase[k])
                    for k in ("control_instance", "business_instance", "restore_epoch")
                )
            )
            attempt = AttemptBinding(
                authority,
                tenant,
                UUID(phase["device_id"]),
                UUID(phase["game_id"]),
                phase["wire_d4"],
                phase["internal_generation"],
                UUID(phase["attempt_id"]),
                phase["codec_version"],
                phase["request_fingerprint"],
                1,
            )
            event = EventPhaseBinding(
                attempt,
                UUID(phase["phase_id"]),
                1,
                1,
                UUID(phase["d5"]),
                phase["event_fingerprint"],
            )
            if (
                _phase_wire(
                    event,
                    self._issuer,
                    self._config["binding_authority"]["control_version"],
                )
                != phase
            ):
                raise ValueError
            _writer_from_wire(request["writer"])
        except (KeyError, TypeError, ValueError, WriterBindingUnavailable):
            raise WriterBindingUnavailable("binding要求の閉入力が不正") from None

    def prepare(
        self, request: dict[str, Any], recovery_generation: int
    ) -> tuple[dict[str, object], dict[str, object], bytes]:
        """control原本全値照合後にintent用の閉値を準備する。"""
        self.validate_request(request)
        if set(request) != {"operation", "tenant_id", "phase", "writer"}:
            raise WriterBindingUnavailable("binding要求が不正")
        tenant = UUID(request["tenant_id"])
        phase = request["phase"]
        if type(phase) is not dict:
            raise WriterBindingUnavailable("phase原本が不正")
        expected = self._config["binding_authority"]
        if any(phase.get(k) != v for k, v in expected.items()) or phase.get(
            "authority_id"
        ) != str(self._issuer):
            raise WriterBindingUnavailable("phase権威が不一致")
        # 信頼された専用peerのみ到達する固定登録。部分上書きはSQLが拒否する。
        self._call(
            "control",
            "SELECT sync_control.register_first_ball_phase(%s,%s)",
            (tenant, Jsonb(phase)),
            write=True,
        )
        attempt, phase_id = UUID(phase["attempt_id"]), UUID(phase["phase_id"])
        saved = self._call(
            "control",
            "SELECT context_json FROM sync_control.read_first_ball_phase(%s,%s,%s)",
            (tenant, attempt, phase_id),
        )
        if (
            len(saved) != 1
            or type(saved[0]) is not str
            or json.loads(saved[0]) != phase
        ):
            raise WriterBindingUnavailable("保存phase全値が不一致")
        writer = _writer_from_wire(request["writer"])
        nonce = secrets.token_bytes(32)
        lease = uuid4()
        expires = datetime.now(timezone.utc) + timedelta(seconds=30)
        binding = {
            k: v for k, v in phase.items() if k not in {"attempt_id", "phase_id"}
        }
        binding.update(writer.wire())
        binding.update(
            issuer=str(self._issuer),
            lease_id=str(lease),
            recovery_generation=recovery_generation,
            expires_at=expires.isoformat(),
        )
        digest = hashlib.sha256(nonce).digest()
        record = {
            "tenant_id": str(tenant),
            "attempt_id": str(attempt),
            "phase_id": str(phase_id),
            "lease_id": str(lease),
            "recovery_generation": recovery_generation,
            "close_id": str(uuid4()),
            "phase": phase,
            "writer": writer.wire(),
            "nonce_digest": digest.hex(),
            "expires_at": expires.isoformat(),
        }
        return record, binding, nonce

    def publish_prepared(
        self, record: dict[str, Any], binding: dict[str, object], nonce: bytes
    ) -> None:
        """耐久intent後だけ固定原本を公開し、nonceをjournalへ書かない。"""
        self._call(
            "business",
            "SELECT sync_fence_api.publish_writer_binding(%s,%s,%s,%s,%s)",
            (
                UUID(record["tenant_id"]),
                UUID(record["attempt_id"]),
                UUID(record["phase_id"]),
                Jsonb(binding),
                hashlib.sha256(nonce).digest(),
            ),
            write=True,
        )

    def check(self, record: dict[str, Any], recovery_generation: int) -> None:
        """生存leaseのcontrol原本・世代・期限を毎回実照合する。"""
        if (
            record["recovery_generation"] != recovery_generation
            or datetime.now(timezone.utc)
            >= datetime.fromisoformat(record["expires_at"])
            or record["phase"]["authority_id"] != str(self._issuer)
            or any(
                record["phase"].get(k) != v
                for k, v in self._config["binding_authority"].items()
            )
        ):
            raise WriterBindingUnavailable("binding制御leaseが失効")
        row = self._call(
            "control",
            "SELECT context_json FROM sync_control.read_first_ball_phase(%s,%s,%s)",
            tuple(UUID(record[n]) for n in ("tenant_id", "attempt_id", "phase_id")),
        )
        if (
            len(row) != 1
            or type(row[0]) is not str
            or json.loads(row[0]) != record["phase"]
        ):
            raise WriterBindingUnavailable("binding制御原本が不一致")

    def resolve(self, record: dict[str, Any]) -> BindingOutcome:
        """drain/close COMMIT確認後の別取引からだけ終結を観測する。"""
        params = tuple(
            UUID(record[n])
            for n in ("tenant_id", "attempt_id", "phase_id", "lease_id", "close_id")
        )
        try:
            self._call(
                "business",
                "SELECT sync_fence_api.close_writer_binding(%s,%s,%s,%s,%s)",
                params,
                write=True,
            )
            row = self._call(
                "business",
                "SELECT outcome FROM sync_fence_api.observe_writer_binding"
                "(%s,%s,%s,%s,%s)",
                params,
            )
            if len(row) != 1 or type(row[0]) is not str:
                return BindingOutcome.UNKNOWN
            return BindingOutcome(row[0])
        except Exception:
            return BindingOutcome.UNKNOWN


_LEASE_CREATION = object()


class _BindingLease:
    """真正authority channelを所有する短命lease。scalarから成功しない。"""

    def __init__(
        self,
        ledger,
        channel_context,
        channel,
        phase: EventPhaseBinding,
        identity: WriterIdentity,
        reply: object,
        creation: object,
        *,
        phase_snapshot: str,
    ) -> None:
        """実channel応答をprivateclientから受ける。"""
        if creation is not _LEASE_CREATION or type(ledger) is not BindingControl:
            raise WriterBindingUnavailable("leaseの発行元が不正")
        if type(reply) is not dict or set(reply) != {"nonce", "lease_id", "expires_at"}:
            raise WriterBindingUnavailable("binding応答が不正")
        reply = cast(dict[str, Any], reply)
        if any(type(reply[n]) is not str for n in ("nonce", "lease_id", "expires_at")):
            raise WriterBindingUnavailable("binding応答が不正")
        self.nonce = bytes.fromhex(reply["nonce"])
        if len(self.nonce) != 32:
            raise WriterBindingUnavailable("binding応答が不正")
        UUID(reply["lease_id"])
        self._expires = datetime.fromisoformat(reply["expires_at"])
        if self._expires.utcoffset() is None or self._expires <= datetime.now(
            timezone.utc
        ):
            raise WriterBindingUnavailable("binding期限が不正")
        # RPC前の実送信値を保持し、応答後にcallerが再構成したphaseを採用しない。
        try:
            snapshot = json.loads(phase_snapshot)
            authority = UUID(snapshot["phase"]["authority_id"])
            version = snapshot["phase"]["control_version"]
            expected = {
                "tenant_id": str(phase.attempt.tenant_id),
                "phase": _phase_wire(phase, authority, version),
            }
            canonical = json.dumps(expected, sort_keys=True, separators=(",", ":"))
            if type(phase_snapshot) is not str or canonical != phase_snapshot:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise WriterBindingUnavailable("binding phase原本が不一致") from None
        self._phase_snapshot = phase_snapshot
        self.identity = identity
        self.attempt_id = phase.attempt.attempt_id
        self.phase_id = phase.phase_id
        self.device_id = phase.attempt.device_id
        self.game_id = phase.attempt.game_id
        self._ledger, self._context, self._channel = ledger, channel_context, channel
        self._closed = False

    def check(self) -> None:
        """期限内かつ実fenceが保持された場合だけ継続する。"""
        from pitchlog.durable_rights_ledger.adapter import _request

        if self._closed or datetime.now(timezone.utc) >= self._expires:
            raise WriterBindingUnavailable("writer leaseが失効している")
        _request(self._channel, {"operation": "binding_check"})

    def abandon(self) -> None:
        """切断は権威側に耐久quarantineさせ、解放成功と扱わない。"""
        if not self._closed:
            self._closed = True
            self._context.__exit__(None, None, None)

    def finish(self) -> BindingOutcome:
        """実PG終了後の固定close要求。終結内容はauthority自身が照会する。"""
        from pitchlog.durable_rights_ledger.adapter import _request

        if self._closed:
            raise WriterBindingUnavailable("writer leaseの終了が不明")
        try:
            result = _request(self._channel, {"operation": "binding_close"})
            outcome = BindingOutcome(result)
            if outcome not in (
                BindingOutcome.COMMITTED,
                BindingOutcome.ROLLBACK_CONFIRMED,
            ):
                raise WriterBindingUnavailable("writer終結を確認できない")
            return outcome
        finally:
            self.abandon()


_BROKER_KEYS = {
    "schema_version",
    "broker_uid",
    "broker_gid",
    "application_uid",
    "application_gid",
    "socket_path",
    "timeout",
    "authority_id",
    "control_version",
}


def _broker_endpoint(path: Path) -> dict[str, Any]:
    """root不変配置の非秘密broker endpointを閉じた値で検証する。"""
    from pitchlog.durable_rights_ledger.authority import _read_root_json

    value = _read_root_json(path, 0o644)
    if (
        set(value) != _BROKER_KEYS
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or any(
            type(value[k]) is not int
            for k in ("broker_uid", "broker_gid", "application_uid", "application_gid")
        )
        or (
            value["broker_uid"],
            value["broker_gid"],
            value["application_uid"],
            value["application_gid"],
        )
        != (20005, 20005, 20003, 20003)
        or type(value["timeout"]) not in (int, float)
        or not math.isfinite(value["timeout"])
        or not 0.1 <= value["timeout"] <= 30
        or type(value["socket_path"]) is not str
        or not Path(value["socket_path"]).is_absolute()
        or str(Path(value["socket_path"])) != value["socket_path"]
        or ".." in Path(value["socket_path"]).parts
        or len(os.fsencode(value["socket_path"])) >= 108
        or type(value["control_version"]) is not int
        or not 0 < value["control_version"] < 2**63
        or type(value["authority_id"]) is not str
        or str(UUID(value["authority_id"])) != value["authority_id"]
    ):
        raise WriterBindingUnavailable("binding broker配置が不正")
    return value


class _BindingBroker:
    """専用UID20005で既Cookie認証と実authority接続を所有する。"""

    def __init__(self, authority_endpoint: Path, verifier_runtime) -> None:
        """既設専用verifier runtimeを受け、新しい鍵やLOGINを発行しない。"""
        from pitchlog.durable_rights_ledger.adapter import DurableLedger
        from pitchlog.recording_rights.initial_grant_broker import _auth_verifier_state

        if os.geteuid() != 20005 or os.getegid() != 20005:
            raise WriterBindingUnavailable("binding broker主体が不正")
        self._ledger = DurableLedger(authority_endpoint)
        if (
            self._ledger._target.get("schema_version") != 3
            or self._ledger._target.get("role") != "sync_binding"
        ):
            raise WriterBindingUnavailable("専用authority endpointが必要")
        _auth_verifier_state(verifier_runtime)
        self._verifier_runtime = verifier_runtime

    def handle(self, channel: socket.socket) -> None:
        """実app peerと有効Cookieを両方照合した単球channelだけを中継する。"""
        from pydantic import SecretStr

        from pitchlog.durable_rights_ledger.adapter import (
            _receive,
            _request,
            _send,
            _send_error,
        )
        from pitchlog.recording_rights.initial_grant_broker import (
            _verify_initial_cookie,
        )

        try:
            _, uid, gid = struct.unpack(
                "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if (uid, gid) != (20003, 20003) or (os.geteuid(), os.getegid()) != (
                20005,
                20005,
            ):
                raise WriterBindingUnavailable("binding app主体が不正")
            request = _receive(channel)
            if (
                set(request) != {"operation", "cookie", "tenant_id", "phase", "writer"}
                or request["operation"] != "binding_open"
                or type(request["cookie"]) is not str
            ):
                raise WriterBindingUnavailable("binding app要求が不正")
            cookie = request.pop("cookie")
            authenticated = _verify_initial_cookie(
                self._verifier_runtime, SecretStr(cookie)
            )
            if authenticated is None or str(authenticated[0]) != request["tenant_id"]:
                raise WriterBindingUnavailable("binding認証が不一致")
            with self._ledger._channel() as authority:
                result = _request(authority, request)
                _send(channel, {"status": "ok", "result": result})
                while True:
                    current = _receive(channel)
                    if set(current) != {"operation"} or current["operation"] not in (
                        "binding_check",
                        "binding_close",
                    ):
                        raise WriterBindingUnavailable("binding app操作が不正")
                    if current["operation"] == "binding_check":
                        verified = _verify_initial_cookie(
                            self._verifier_runtime, SecretStr(cookie)
                        )
                        if verified is None or verified[0] != authenticated[0]:
                            raise WriterBindingUnavailable("binding認証が失効")
                    result = _request(authority, current)
                    _send(channel, {"status": "ok", "result": result})
                    if current["operation"] == "binding_close":
                        return
        except Exception:
            _send_error(channel, "unavailable")


class BindingControl:
    """app UID20003から専用認証brokerへだけ接続するclient。"""

    def __init__(self, endpoint: Path) -> None:
        """root保護の非秘密配置だけを受け取り、appのLedger能力を増やさない。"""
        self._endpoint = endpoint
        self._target = _broker_endpoint(endpoint)

    @contextmanager
    def _channel(self):
        """root配置と実broker peerが同じ場合だけ内部channelを貸す。"""
        if (os.geteuid(), os.getegid()) != (20003, 20003) or _broker_endpoint(
            self._endpoint
        ) != self._target:
            raise WriterBindingUnavailable("binding app配置が不一致")
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            channel.settimeout(self._target["timeout"])
            channel.connect(self._target["socket_path"])
            _, uid, gid = struct.unpack(
                "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if (uid, gid) != (20005, 20005):
                raise WriterBindingUnavailable("binding broker peerが不一致")
            yield channel
        finally:
            channel.close()

    def bind_writer(
        self, handle, context: TenantContext, phase: EventPhaseBinding, *, cookie: str
    ):
        """既Cookieと実scopeのidentityをbrokerが再認証してから資格化する。"""
        from pitchlog.durable_rights_ledger.adapter import _request
        from pitchlog.repositories.writer_binding import _ReadWriterIdentityToken
        from pitchlog.sync.control_provider.writer_binding import (
            _issue_live_writer_binding,
        )

        if (
            type(context) is not TenantContext
            or not context._has_valid_integrity_proof()
            or phase.attempt.tenant_id != context.tenant_id
            or handle._context is not context
            or type(cookie) is not str
        ):
            raise WriterBindingUnavailable("認証済みwriter contextが不一致")
        from pitchlog.repositories.rg1 import read_rg1_open

        handle._writer_lifetime()
        read_rg1_open(handle)
        identity = WriterIdentity(
            *handle.run_function(_ReadWriterIdentityToken()).rows[0]
        )
        manager = self._channel()
        channel = manager.__enter__()
        try:
            phase_wire = _phase_wire(
                phase,
                UUID(self._target["authority_id"]),
                self._target["control_version"],
            )
            phase_snapshot = json.dumps(
                {"tenant_id": str(context.tenant_id), "phase": phase_wire},
                sort_keys=True,
                separators=(",", ":"),
            )
            reply = _request(
                channel,
                {
                    "operation": "binding_open",
                    "cookie": cookie,
                    "tenant_id": str(context.tenant_id),
                    "phase": phase_wire,
                    "writer": identity.wire(),
                },
            )
            lease = _BindingLease(
                self,
                manager,
                channel,
                phase,
                identity,
                reply,
                _LEASE_CREATION,
                phase_snapshot=phase_snapshot,
            )
            return _issue_live_writer_binding(handle, lease)
        except BaseException:
            manager.__exit__(None, None, None)
            raise
