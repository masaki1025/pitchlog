"""root保護設定から作った私有actorと、単一issuerのcommit所有を接ぐ。"""

from __future__ import annotations

import base64
import ctypes
import hmac
import json
import os
import queue
import secrets
import socket
import stat
import struct
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DisconnectionError

from pitchlog.api.schemas.game_start import (
    InitialDeviceEnrollmentResponse,
    InitialGameStartResponse,
)
from pitchlog.authz.database_transport import require_database_transport
from pitchlog.db.engine import engine_connect_args
from pitchlog.db.url import normalize_postgresql_url
from pitchlog.recording_rights.initial_grant import (
    DurableGenerationSource,
    InitialGrant,
    InitialGrantUnavailable,
    RecoveryEpochFence,
    V12Box,
    assert_write_recovery_generation,
    issue_initial_recording_right,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.game_start import (
    BoundInitialStartPayload,
    InitialStartPayload,
    InitialStartReceipt,
)
from pitchlog.repositories.initial_recording_right import (
    _BeginStartAttemptToken,
    _credential_digest,
    _initial_recording_right_scope,
    _LockDeviceToken,
    _StartOwner,
)
from pitchlog.sync.d4_reference import D4ReferenceInvalid, encode_d4_reference

if TYPE_CHECKING:
    from pitchlog.durable_rights_ledger import DurableLedger
    from pitchlog.repositories.transaction import _TenantTransaction

__all__: tuple[str, ...] = ()
_RUNTIME_CREATION = object()
_ACTOR_ROLE = "pitchlog_initial_actor"


@dataclass(frozen=True, slots=True)
class _ActorConfiguration:
    """rootが固定した接続先と期待する実business identity。"""

    database_url: str = field(repr=False)
    system_identifier: str
    database_oid: int
    database_name: str
    postmaster_started_at: datetime

    def __post_init__(self) -> None:
        """root配置を読めても期待identityの穴を許可しない。"""
        if (
            type(self.database_url) is not str
            or not self.database_url
            or type(self.system_identifier) is not str
            or not self.system_identifier.isdecimal()
            or type(self.database_oid) is not int
            or self.database_oid <= 0
            or type(self.database_name) is not str
            or not self.database_name
            or type(self.postmaster_started_at) is not datetime
            or self.postmaster_started_at.utcoffset() is None
        ):
            raise InitialGrantUnavailable("actor設定の形が不正")


class _InitialActorRuntime:
    """公開engine/DSNを持たず、私有registryの不透明keyだけを保持する。"""

    __slots__ = ("_key",)

    def __init__(self, key: object, creation: object) -> None:
        """実登録を伴わないruntime生成を拒否する。"""
        if creation is not _RUNTIME_CREATION or key not in _ACTOR_RUNTIMES:
            raise InitialGrantUnavailable("actor runtimeを確認できない")
        self._key = key


@dataclass(frozen=True, slots=True)
class _ActorState:
    """接続・暗号・期待identityをprocess内だけで保持する。"""

    engine: Engine = field(repr=False)
    configuration: _ActorConfiguration = field(repr=False)
    box: V12Box = field(repr=False)


_ACTOR_RUNTIMES: dict[object, _ActorState] = {}


def _actor_state(runtime: object) -> _ActorState:
    """正確な型/実登録/失効を毎回検査する。"""
    if type(runtime) is not _InitialActorRuntime:
        raise InitialGrantUnavailable("actor runtimeを確認できない")
    state = _ACTOR_RUNTIMES.get(runtime._key)
    if state is None:
        raise InitialGrantUnavailable("actor runtimeは失効している")
    return state


def _initial_actor_engine(runtime: object) -> Engine:
    """既transaction factoryだけが実登録済みengineを借りる。"""
    if os.geteuid() != 20002:
        raise InitialGrantUnavailable("actorの実process主体が一致しない")
    return _actor_state(runtime).engine


def _validate_actor_observation(
    row: tuple[object, ...], config: _ActorConfiguration
) -> None:
    """catalogの実属性を厳密に比較し、boolの真偽補完をしない。"""
    if len(row) != 15 or row[:2] != (_ACTOR_ROLE, _ACTOR_ROLE):
        raise InitialGrantUnavailable("actorの実DB主体が一致しない")
    if tuple(row[2:9]) != (True, False, False, False, False, False, False) or any(
        type(v) is not bool for v in row[2:9]
    ):
        raise InitialGrantUnavailable("actorの実DB属性が一致しない")
    if type(row[9]) is not int or row[9] != 0 or row[10] not in (None, ""):
        raise InitialGrantUnavailable("actorのmembership又はtenant初期値が不正")
    if (
        row[11] != config.database_name
        or type(row[12]) is not int
        or row[12] != config.database_oid
        or type(row[13]) is not datetime
        or row[13] != config.postmaster_started_at
        or type(row[14]) is not int
        or row[14] <= 0
    ):
        raise InitialGrantUnavailable("actorの接続先DB identityが一致しない")


def _verify_initial_actor_checkout(
    connection: Any, config: _ActorConfiguration
) -> None:
    """checkout毎に実role/接続先を読み、失敗接続を失効させる。"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT session_user::text, current_user::text,
                       r.rolcanlogin, r.rolsuper, r.rolbypassrls, r.rolinherit,
                       r.rolcreaterole, r.rolcreatedb, r.rolreplication,
                       (SELECT count(*) FROM pg_catalog.pg_auth_members AS m
                        WHERE m.member = r.oid OR m.roleid = r.oid),
                       pg_catalog.current_setting('app.tenant_id', true),
                       pg_catalog.current_database()::text, d.oid::integer,
                       pg_catalog.pg_postmaster_start_time(),
                       pg_catalog.pg_backend_pid()
                FROM pg_catalog.pg_roles AS r
                JOIN pg_catalog.pg_database AS d
                  ON d.datname = pg_catalog.current_database()
                WHERE r.rolname = session_user
            """)
            row = cursor.fetchone()
            if row is None or cursor.fetchone() is not None:
                raise InitialGrantUnavailable("actor属性を一意に確認できない")
            _validate_actor_observation(tuple(row), config)
        connection.rollback()
    except Exception:
        try:
            connection.rollback()
        except BaseException:
            pass
        # driver例外の接続情報/SQL/資格を公開経路へ伝播させない。
        raise DisconnectionError("初期権actorの接続検査に失敗した") from None


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """root配置と固定bindingの重複keyを拒否する。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("重複key")
        result[key] = value
    return result


def _load_initial_actor_runtime(path: Path, box: V12Box) -> _InitialActorRuntime:
    """Root bootstrapだけが保護設定と既V12Boxから私有runtimeを発行する。"""
    if os.geteuid() != 0 or type(box) is not V12Box:
        raise InitialGrantUnavailable("actor設定はroot bootstrapだけが読める")
    try:
        if not path.is_absolute():
            raise ValueError("絶対pathでない")
        for parent in path.parents:
            metadata = parent.stat(follow_symlinks=False)
            if (
                parent.is_symlink()
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise ValueError("保護されていない親directory")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as file:
            metadata = os.fstat(file.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > 16384
            ):
                raise ValueError("root保護設定でない")
            value = json.loads(file.read(16385), object_pairs_hook=_json_object)
        if type(value) is not dict or set(value) != {
            "database_url",
            "system_identifier",
            "database_oid",
            "database_name",
            "postmaster_started_at",
        }:
            raise ValueError("設定field不一致")
        stamp = value["postmaster_started_at"]
        if type(stamp) is not str:
            raise ValueError("日時型不一致")
        config = _ActorConfiguration(
            value["database_url"],
            value["system_identifier"],
            value["database_oid"],
            value["database_name"],
            datetime.fromisoformat(stamp),
        )
        args = engine_connect_args(False)
        args["gssencmode"] = "disable"
        args["connect_timeout"] = 1
        args["options"] = "-c statement_timeout=1500 -c lock_timeout=1000"
        url = normalize_postgresql_url(config.database_url)
        require_database_transport(url, args)
        engine = create_engine(
            url,
            connect_args=args,
            hide_parameters=True,
            pool_size=3,
            max_overflow=0,
            pool_timeout=0.5,
        )

        def checkout(connection: Any, record: Any, proxy: Any) -> None:
            """poolの実接続を用途固定の検査へ渡す。"""
            del record, proxy
            _verify_initial_actor_checkout(connection, config)

        event.listen(engine, "checkout", checkout)
    except Exception:
        raise InitialGrantUnavailable("初期権actorのroot設定を検証できない") from None
    key = object()
    _ACTOR_RUNTIMES[key] = _ActorState(engine, config, box)
    return _InitialActorRuntime(key, _RUNTIME_CREATION)


def _close_initial_actor_runtime(runtime: object) -> None:
    """runtimeを失効させ、所有poolだけを破棄する。"""
    state = _actor_state(runtime)
    assert type(runtime) is _InitialActorRuntime
    _ACTOR_RUNTIMES.pop(runtime._key)
    state.engine.dispose()


def _verify_business_binding(transaction: _TenantTransaction, runtime: object) -> None:
    """実scopeの固定RG1読取だけからsysidを含む接続先を再照合する。"""
    from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY

    registrations = [
        spec
        for spec in FUNCTION_OPERATION_REGISTRY.values()
        if (spec.operation_id, spec.function_id)
        == ("RG1:scope_binding", "rg1_control.scope_binding")
    ]
    if len(registrations) != 1:
        raise InitialGrantUnavailable("actor用の固定scope bindingが未供給")
    token = registrations[0].token_type()
    rows = transaction.run_function(token).rows
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not str:
        raise InitialGrantUnavailable("実scope bindingを確認できない")
    try:
        from pitchlog.recording_rights.rg1_lifecycle import (
            BusinessBinding,
            RG1ControlUnavailable,
        )
    except ImportError:
        raise InitialGrantUnavailable("固定RG1 binding型が未供給") from None
    try:
        binding = BusinessBinding.from_text(rows[0][0])
        config = _actor_state(runtime).configuration
        if (
            binding.system_identifier != config.system_identifier
            or binding.database_oid != config.database_oid
            or binding.database_name != config.database_name
            or binding.postmaster_started_at != config.postmaster_started_at
        ):
            raise InitialGrantUnavailable("実scope bindingがroot配置と一致しない")
    except RG1ControlUnavailable:
        raise InitialGrantUnavailable("実scope bindingを確認できない") from None


def _issue_initial_grant_impl(
    context: TenantContext,
    runtime: object,
    owner: _StartOwner,
    credential: str,
    source: DurableGenerationSource,
    fence: RecoveryEpochFence,
    start_payload: BoundInitialStartPayload | None = None,
) -> tuple[InitialGrant, InitialStartReceipt | None]:
    """短intentと業務commitを所有し、commit成功後だけ既issuerのV12を返す。"""
    from pitchlog.repositories.rg1 import read_rg1_open
    from pitchlog.repositories.transaction import _initial_actor_transaction_scope

    state = _actor_state(runtime)
    if (
        type(context) is not TenantContext
        or not context._has_valid_integrity_proof()
        or type(owner) is not _StartOwner
        or context.tenant_id != owner.tenant_id
    ):
        raise InitialGrantUnavailable("初期権の認証済み文脈が不正")
    if start_payload is not None:
        from pitchlog.repositories.game_start import BoundInitialStartPayload

        if type(start_payload) is not BoundInitialStartPayload:
            raise InitialGrantUnavailable("開始payloadの閉型が不正")
        start_payload.assert_owner(owner)
        if not hmac.compare_digest(
            start_payload.credential_digest, _credential_digest(credential)
        ):
            raise InitialGrantUnavailable("開始payloadの資格束縛が不一致")
    fence.assert_held()
    # このwithが終わるまでbusiness側を開かず、短intentのlockを流用しない。
    with _initial_actor_transaction_scope(context, runtime, "intent") as transaction:
        _verify_business_binding(transaction, runtime)
        read_rg1_open(transaction)
        rows = transaction.run_function(_LockDeviceToken(owner.device_id)).rows
        if (
            not rows
            or rows[0][1] is not None
            or not hmac.compare_digest(
                cast(bytes, rows[0][0]), _credential_digest(credential)
            )
        ):
            raise InitialGrantUnavailable("端末資格を確認できない")
        rows = transaction.run_function(
            _BeginStartAttemptToken(
                owner.game_id,
                owner.start_request_id,
                owner.device_id,
                owner.request_digest,
                owner.attempt_id,
            )
        ).rows
        if not rows:
            raise InitialGrantUnavailable("開始intentを確認できない")
        owner = replace(owner, attempt_id=cast(UUID, rows[0][0]))
        from pitchlog.repositories.rg1 import assert_rg1_open_before_commit

        assert_rg1_open_before_commit(transaction)
        fence.assert_held()
    if start_payload is not None:
        # intentが既attemptへ解決してもrequest指紋へattemptは追加しない。
        from pitchlog.repositories.game_start import BoundInitialStartPayload

        start_payload = BoundInitialStartPayload(
            start_payload.payload, owner, start_payload.credential_digest
        )
    with _initial_recording_right_scope(
        context, owner, runtime, start_payload
    ) as scope:
        _verify_business_binding(scope._transaction, runtime)
        grant = issue_initial_recording_right(
            scope,
            tenant_id=owner.tenant_id,
            game_id=owner.game_id,
            device_id=owner.device_id,
            device_credential=credential,
            start_request_id=owner.start_request_id,
            reservation_attempt_id=owner.attempt_id,
            source=source,
            fence=fence,
            box=state.box,
        )
        assert_write_recovery_generation(
            scope, source, fence, int(grant.recovery_generation)
        )
        _actor_state(runtime)
        receipt = scope._start_receipt
        if start_payload is not None and receipt is None:
            raise InitialGrantUnavailable("開始保存原本を確認できない")
    # withの実commitが例外ならここへ到達しない。応答不明は再発行へ変換しない。
    fence.assert_held()
    return grant, receipt


@dataclass(frozen=True, slots=True)
class _InitialStartedGame:
    """同business commit後の開始原本と既初期権。公開Readyではない。"""

    grant: InitialGrant
    receipt: InitialStartReceipt


def _issue_initial_grant(
    context: TenantContext,
    runtime: object,
    owner: _StartOwner,
    credential: str,
    source: DurableGenerationSource,
    fence: RecoveryEpochFence,
) -> InitialGrant:
    """旧grant-only経路を開始原本要求へ拡張せず保持する。"""
    grant, _ = _issue_initial_grant_impl(
        context, runtime, owner, credential, source, fence
    )
    return grant


def _start_initial_game(
    context: TenantContext,
    runtime: object,
    bound: BoundInitialStartPayload,
    credential: str,
    source: DurableGenerationSource,
    fence: RecoveryEpochFence,
) -> _InitialStartedGame:
    """型付き開始だけを既単一issuerと同じcommit所有本体へ接ぐ。"""
    from pitchlog.repositories.game_start import (
        BoundInitialStartPayload,
        InitialStartReceipt,
    )

    if type(bound) is not BoundInitialStartPayload:
        raise InitialGrantUnavailable("開始payloadの閉型が不正")
    grant, receipt = _issue_initial_grant_impl(
        context, runtime, bound.owner, credential, source, fence, bound
    )
    if type(receipt) is not InitialStartReceipt:
        raise InitialGrantUnavailable("開始保存原本を確認できない")
    return _InitialStartedGame(grant, receipt)


# Aは通信の型・表現だけ。実Cookie再検証/SQL/workerは後続Bで接続する。
_BROKER_MAX_FRAME = 131072
_BROKER_TIMEOUT = 2.0
_BROKER_SERVER_UID = 20002
_BROKER_SERVER_GID = 20002
_BROKER_ENDPOINT_PATH = Path("/run/pitchlog/initial-broker-endpoint.json")


class InitialBrokerUnavailable(RuntimeError):
    """通信を確認できない。業務rollbackや未使用予約を意味しない。"""

    def __init__(self) -> None:
        """原例外/資格/pathを受けない固定外形を作る。"""
        super().__init__("開始通信を確認できない（結果不明の可能性）")


def _broker_invalid() -> InitialBrokerUnavailable:
    """入力を例外へ取り込まない。"""
    return InitialBrokerUnavailable()


def _broker_d4(tenant_id: UUID, game_id: UUID, generation: int) -> str:
    """本issuerの実世代をowner付き参照へ写す。発行/認可は行わない。

    符号化は ``pitchlog.sync.d4_reference`` の単一実装へ委譲し、ここでは
    入力不正を従来どおり固定外形の通信不確定例外へ写すだけにする。
    """
    try:
        return encode_d4_reference(tenant_id, game_id, generation)
    except D4ReferenceInvalid:
        raise _broker_invalid() from None


def _broker_generation(value: str, tenant_id: UUID, game_id: UUID) -> int:
    """本issuer参照だけを解く。実権利/失効/epoch/RG1照合の代用ではない。"""
    try:
        if type(value) is not str or len(value) != 60 or not value.startswith("d4.1."):
            raise ValueError
        encoded = value[5:]
        if any(
            ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for ch in encoded
        ):
            raise ValueError
        raw = base64.b64decode(encoded + "=", altchars=b"-_", validate=True)
        if len(raw) != 41 or raw[0] != 1:
            raise ValueError
        generation = int.from_bytes(raw[33:], "big")
        if (
            raw[1:17] != tenant_id.bytes
            or raw[17:33] != game_id.bytes
            or _broker_d4(tenant_id, game_id, generation) != value
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        pass
    else:
        return generation
    raise _broker_invalid()


def _broker_secret(value: object) -> SecretStr:
    """秘密値を変換せず型/有限長を検査する。"""
    try:
        if type(value) is SecretStr:
            secret = value.get_secret_value()
            if type(secret) is str and 0 < len(secret.encode("utf-8")) <= 4096:
                return value
    except UnicodeError:
        pass
    raise _broker_invalid()


@dataclass(frozen=True, slots=True, repr=False)
class _BrokerIdentity:
    """公開challengeと提示Cookie。peerやこの型自体はtenant証明ではない。"""

    expected_tenant_id: UUID
    challenge: UUID
    cookie: SecretStr = field(repr=False)

    def __post_init__(self) -> None:
        """派生型や資格の暗黙変換を拒否する。"""
        if (
            type(self.expected_tenant_id) is not UUID
            or type(self.challenge) is not UUID
        ):
            raise _broker_invalid()
        _broker_secret(self.cookie)


@dataclass(frozen=True, slots=True)
class _EnrollDeviceCommand:
    """登録を実行せず、登録要求の外形だけを保持する。"""

    identity: _BrokerIdentity = field(repr=False)

    def __post_init__(self) -> None:
        """未検証の辞書を文脈へ昇格しない。"""
        if type(self.identity) is not _BrokerIdentity:
            raise _broker_invalid()
        self.identity.__post_init__()


@dataclass(frozen=True, slots=True)
class _StartInitialGameCommand:
    """元要求ID/全payloadを保持する。attemptやdigestをcallerから受けない。"""

    identity: _BrokerIdentity = field(repr=False)
    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    device_credential: SecretStr = field(repr=False)
    payload: InitialStartPayload

    def __post_init__(self) -> None:
        """閉型と深い不変payloadを再検査する。"""
        if (
            type(self.identity) is not _BrokerIdentity
            or any(
                type(value) is not UUID
                for value in (self.game_id, self.start_request_id, self.device_id)
            )
            or type(self.payload) is not InitialStartPayload
        ):
            raise _broker_invalid()
        self.identity.__post_init__()
        _broker_secret(self.device_credential)
        self.payload.__post_init__()


@dataclass(frozen=True, slots=True)
class _ResolveStartCommand:
    """同じ元要求の照会だけを表し、解決結果を推測しない。"""

    original: _StartInitialGameCommand = field(repr=False)

    def __post_init__(self) -> None:
        """元要求の差替えや派生型を拒否する。"""
        if type(self.original) is not _StartInitialGameCommand:
            raise _broker_invalid()
        self.original.__post_init__()


type _BrokerCommand = (
    _EnrollDeviceCommand | _StartInitialGameCommand | _ResolveStartCommand
)


def _broker_command_source(command: _BrokerCommand) -> dict[str, object]:
    """専用serializerだけが提示Cookie/資格を意図した通信fieldへ出す。"""
    from pitchlog.repositories.game_start import _entry_json

    if type(command) not in (
        _EnrollDeviceCommand,
        _StartInitialGameCommand,
        _ResolveStartCommand,
    ):
        raise _broker_invalid()
    command.__post_init__()
    selected = cast(
        _EnrollDeviceCommand | _StartInitialGameCommand,
        command.original if type(command) is _ResolveStartCommand else command,
    )
    assert type(selected) in (_EnrollDeviceCommand, _StartInitialGameCommand)
    identity = selected.identity
    result: dict[str, object] = {
        "version": 1,
        "command": (
            "enroll_device"
            if type(command) is _EnrollDeviceCommand
            else "resolve_start"
            if type(command) is _ResolveStartCommand
            else "start_initial_game"
        ),
        "expected_tenant_id": str(identity.expected_tenant_id),
        "challenge": str(identity.challenge),
        "cookie": identity.cookie.get_secret_value(),
    }
    if type(selected) is _StartInitialGameCommand:
        result["game_id"] = str(selected.game_id)
        result["request"] = {
            "start_request_id": str(selected.start_request_id),
            "device_id": str(selected.device_id),
            "device_credential": selected.device_credential.get_secret_value(),
            "away": [_entry_json(e) for e in selected.payload.away],
            "home": [_entry_json(e) for e in selected.payload.home],
        }
    return result


def _broker_json(value: object) -> bytes:
    """閉通信のJSONを一意なUTF-8表現へ写す。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _broker_frame(value: object) -> bytes:
    """有限bodyを4byte長付きframeへ写す。"""
    body = _broker_json(value)
    if not 0 < len(body) <= _BROKER_MAX_FRAME:
        raise _broker_invalid()
    return len(body).to_bytes(4, "big") + body


def _broker_object(frame: bytes) -> dict[str, Any]:
    """長さ/重複key/非有限/末尾余剰/非canonicalを先に拒否する。"""
    try:
        if type(frame) is not bytes or len(frame) < 5:
            raise ValueError
        size = int.from_bytes(frame[:4], "big")
        if not 0 < size <= _BROKER_MAX_FRAME or len(frame) != size + 4:
            raise ValueError
        body = frame[4:]
        value = json.loads(
            body, object_pairs_hook=_json_object, parse_constant=_broker_bad_constant
        )
        if type(value) is not dict or _broker_json(value) != body:
            raise ValueError
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        pass
    else:
        return value
    raise _broker_invalid()


def _broker_bad_constant(_value: str) -> NoReturn:
    """NaN/Infinityを例外値へコピーせず拒否する。"""
    raise ValueError("非有限JSON")


def _broker_uuid(value: object) -> UUID:
    """Canonical UUIDだけを受ける。"""
    try:
        if type(value) is str:
            parsed = UUID(value)
            if str(parsed) == value:
                return parsed
    except ValueError:
        pass
    raise _broker_invalid()


def _decode_initial_command(frame: bytes) -> _BrokerCommand:
    """非実行dispatch。分類した型を返すだけでSQL/issuer/authを呼ばない。"""
    from pitchlog.api.schemas.game_start import GameStartRequest
    from pitchlog.repositories.game_start import _entries

    try:
        value = _broker_object(frame)
        common = {"version", "command", "expected_tenant_id", "challenge", "cookie"}
        name = value.get("command")
        if type(value.get("version")) is not int or value["version"] != 1:
            raise ValueError
        if type(name) is not str or name not in (
            "enroll_device",
            "start_initial_game",
            "resolve_start",
        ):
            raise ValueError
        keys = common if name == "enroll_device" else common | {"game_id", "request"}
        if set(value) != keys or type(value["cookie"]) is not str:
            raise ValueError
        identity = _BrokerIdentity(
            _broker_uuid(value["expected_tenant_id"]),
            _broker_uuid(value["challenge"]),
            SecretStr(value["cookie"]),
        )
        if name == "enroll_device":
            return _EnrollDeviceCommand(identity)
        request = GameStartRequest.model_validate(value["request"])
        start = _StartInitialGameCommand(
            identity,
            _broker_uuid(value["game_id"]),
            request.start_request_id,
            request.device_id,
            request.device_credential,
            InitialStartPayload(_entries(request.away), _entries(request.home)),
        )
        command = _ResolveStartCommand(start) if name == "resolve_start" else start
        if _broker_command_source(command) != value:
            raise ValueError
        # bool/int等のPython同値性だけに頼らずwire全bytesへ逆射影して照合する。
        if _broker_frame(_broker_command_source(command)) != frame:
            raise ValueError
        return command
    except (ValueError, TypeError, KeyError, InitialGrantUnavailable):
        pass
    raise _broker_invalid()


def _encode_initial_command(command: _BrokerCommand) -> bytes:
    """強制改変もdecodeで再検査し、同じcommand全値を送る。"""
    try:
        frame = _broker_frame(_broker_command_source(command))
        _decode_initial_command(frame)
        return frame
    except (ValueError, TypeError, AttributeError, InitialGrantUnavailable):
        pass
    raise _broker_invalid()


def _postcommit_start_response(
    result: _InitialStartedGame, server_owner: _StartOwner
) -> InitialGameStartResponse:
    """同じ実postcommit戻り値を投影する。型/parseはcommit証明ではない。

    後続workerだけが実_start_initial_game完了後に、実解決ownerと共に呼ぶ。
    Aにはworker/issuer呼出しを置かず、別途渡された世代値も受け取らない。
    """
    try:
        if (
            type(result) is not _InitialStartedGame
            or type(result.grant) is not InitialGrant
            or type(result.receipt) is not InitialStartReceipt
            or type(server_owner) is not _StartOwner
            or type(result.receipt.owner) is not _StartOwner
        ):
            raise ValueError
        server_owner.__post_init__()
        result.receipt.owner.__post_init__()
        grant, receipt = result.grant, result.receipt
        if (
            receipt.owner != server_owner
            or grant.game_id != server_owner.game_id
            or grant.holder_device_id != server_owner.device_id
            or type(grant.game_id) is not UUID
            or type(grant.holder_device_id) is not UUID
            or type(grant.recording_right_proof) is not str
        ):
            raise ValueError
        return InitialGameStartResponse(
            tenant_id=server_owner.tenant_id,
            game_id=grant.game_id,
            start_request_id=server_owner.start_request_id,
            device_id=grant.holder_device_id,
            d4=_broker_d4(server_owner.tenant_id, grant.game_id, grant.generation),
            recovery_generation=grant.recovery_generation,
            recording_right_proof=SecretStr(grant.recording_right_proof),
            started_at=receipt.started_at,
            away_lineup_id=receipt.away_lineup_id,
            home_lineup_id=receipt.home_lineup_id,
        )
    except (ValueError, TypeError, AttributeError, InitialGrantUnavailable):
        pass
    raise _broker_invalid()


@dataclass(frozen=True, slots=True)
class _BrokerReply:
    """応答の分類のみ。parse結果を実登録/開始の証拠へ昇格しない。"""

    status: Literal[
        "enrolled", "started", "denied", "conflict", "unavailable", "unresolved"
    ]
    value: InitialDeviceEnrollmentResponse | InitialGameStartResponse | None = field(
        default=None, repr=False
    )

    def __post_init__(self) -> None:
        """未知statusを型内部にも保持せず、成功を補完しない。"""
        if type(self.status) is not str or self.status not in (
            "enrolled",
            "started",
            "denied",
            "conflict",
            "unavailable",
            "unresolved",
        ):
            raise _broker_invalid()
        if self.value is not None and type(self.value) not in (
            InitialDeviceEnrollmentResponse,
            InitialGameStartResponse,
        ):
            raise _broker_invalid()


def _initial_reply_source(
    command: _BrokerCommand, reply: _BrokerReply
) -> dict[str, object]:
    """意図した応答field以外へ秘密値を展開しない専用serializer。"""
    request = _broker_command_source(command)
    if type(reply) is not _BrokerReply:
        raise _broker_invalid()
    value: dict[str, object] = {
        "version": 1,
        "command": request["command"],
        "challenge": request["challenge"],
        "status": reply.status,
    }
    if reply.value is not None:
        if type(reply.value) not in (
            InitialDeviceEnrollmentResponse,
            InitialGameStartResponse,
        ):
            raise _broker_invalid()
        # construct/強制変更した値をserializerへ先に渡すと警告へ原値が出得る。
        secret_field = (
            "device_credential"
            if type(reply.value) is InitialDeviceEnrollmentResponse
            else "recording_right_proof"
        )
        if type(getattr(reply.value, secret_field)) is not SecretStr:
            raise _broker_invalid()
        checked = type(reply.value).model_validate(dict(vars(reply.value)))
        body = checked.model_dump(mode="json")
        if type(reply.value) is InitialDeviceEnrollmentResponse:
            body["device_credential"] = reply.value.device_credential.get_secret_value()
        elif type(reply.value) is InitialGameStartResponse:
            body["recording_right_proof"] = (
                reply.value.recording_right_proof.get_secret_value()
            )
        value["value"] = body
    return value


def _decode_initial_reply(frame: bytes, command: _BrokerCommand) -> _BrokerReply:
    """同command/challenge/ownerとwire全構造を照合する。"""
    try:
        request = _broker_command_source(command)
        value = _broker_object(frame)
        if (
            value.get("version") != 1
            or type(value.get("version")) is not int
            or value.get("command") != request["command"]
            or value.get("challenge") != request["challenge"]
        ):
            raise ValueError
        status = value.get("status")
        if type(status) is not str:
            raise ValueError
        model: InitialDeviceEnrollmentResponse | InitialGameStartResponse | None = None
        if status in ("enrolled", "started"):
            if set(value) != {"version", "command", "challenge", "status", "value"}:
                raise ValueError
            if status == "enrolled" and type(command) is _EnrollDeviceCommand:
                model = InitialDeviceEnrollmentResponse.model_validate_json(
                    _broker_json(value["value"])
                )
                if model.tenant_id != command.identity.expected_tenant_id:
                    raise ValueError
            elif status == "started" and type(command) in (
                _StartInitialGameCommand,
                _ResolveStartCommand,
            ):
                selected = (
                    command.original
                    if type(command) is _ResolveStartCommand
                    else command
                )
                assert type(selected) is _StartInitialGameCommand
                model = InitialGameStartResponse.model_validate_json(
                    _broker_json(value["value"])
                )
                if (
                    model.tenant_id != selected.identity.expected_tenant_id
                    or model.game_id != selected.game_id
                    or model.start_request_id != selected.start_request_id
                    or model.device_id != selected.device_id
                ):
                    raise ValueError
                _broker_generation(model.d4, model.tenant_id, model.game_id)
            else:
                raise ValueError
        elif (
            status not in ("denied", "conflict", "unavailable", "unresolved")
            or set(value) != {"version", "command", "challenge", "status"}
            or (
                type(command) is _EnrollDeviceCommand
                and status in ("conflict", "unresolved")
            )
        ):
            raise ValueError
        reply = _BrokerReply(cast(Any, status), model)
        if _broker_frame(_initial_reply_source(command, reply)) != frame:
            raise ValueError
        return reply
    except (ValueError, TypeError, AttributeError, KeyError, InitialGrantUnavailable):
        pass
    raise _broker_invalid()


def _encode_initial_reply(command: _BrokerCommand, reply: _BrokerReply) -> bytes:
    """未接続workerの成功を作らず、与えられた外形を相互検証する。"""
    try:
        frame = _broker_frame(_initial_reply_source(command, reply))
        _decode_initial_reply(frame, command)
        return frame
    except (ValueError, TypeError, AttributeError, InitialGrantUnavailable):
        pass
    raise _broker_invalid()


@dataclass(frozen=True, slots=True)
class _BrokerEndpoint:
    """root設定のsocket同一性。tenant/権利の証明には使わない。"""

    path: Path
    device: int
    inode: int
    group: int


def _broker_trusted_parents(path: Path) -> None:
    """symlinkやroot以外の書換え可能な経路を拒否する。"""
    if not path.is_absolute():
        raise _broker_invalid()
    for parent in path.parents:
        info = parent.stat(follow_symlinks=False)
        if (
            parent.is_symlink()
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise _broker_invalid()


def _load_broker_endpoint() -> _BrokerEndpoint:
    """固定位置のroot公開設定だけを読む。鍵/DSNは含めない。"""
    try:
        path = _BROKER_ENDPOINT_PATH
        _broker_trusted_parents(path)
        with os.fdopen(
            os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb"
        ) as file:
            info = os.fstat(file.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o644
                or info.st_size > 4096
            ):
                raise ValueError
            value = json.loads(file.read(4097), object_pairs_hook=_json_object)
        if type(value) is not dict or set(value) != {
            "version",
            "socket_path",
            "socket_device",
            "socket_inode",
            "socket_gid",
        }:
            raise ValueError
        if type(value["version"]) is not int or value["version"] != 1:
            raise ValueError
        if type(value["socket_path"]) is not str:
            raise ValueError
        endpoint = _BrokerEndpoint(
            Path(value["socket_path"]),
            value["socket_device"],
            value["socket_inode"],
            value["socket_gid"],
        )
        if (
            any(
                type(v) is not int or v < 0
                for v in (endpoint.device, endpoint.inode, endpoint.group)
            )
            or endpoint.inode == 0
        ):
            raise ValueError
        _check_broker_socket(endpoint)
        return endpoint
    except (OSError, ValueError, TypeError, KeyError):
        pass
    raise _broker_invalid()


def _check_broker_socket(endpoint: _BrokerEndpoint) -> None:
    """connect前後にroot設定の実socket inode/owner/modeを照合する。"""
    _broker_trusted_parents(endpoint.path)
    info = endpoint.path.stat(follow_symlinks=False)
    if endpoint.path.is_symlink():
        raise _broker_invalid()
    _validate_broker_socket_observation(info, endpoint)


def _validate_broker_socket_observation(
    info: os.stat_result, endpoint: _BrokerEndpoint
) -> None:
    """実statの属性だけを照合する。製品呼出元は直前の実statに限定する。"""
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != _BROKER_SERVER_UID
        or info.st_gid != endpoint.group
        or stat.S_IMODE(info.st_mode) != 0o660
        or (info.st_dev, info.st_ino) != (endpoint.device, endpoint.inode)
    ):
        raise _broker_invalid()


def _check_broker_peer(channel: socket.socket) -> None:
    """接続先の実Unix資格を照合する。callerのUID申告は受けない。"""
    _, uid, gid = struct.unpack(
        "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    if (uid, gid) != (_BROKER_SERVER_UID, _BROKER_SERVER_GID):
        raise _broker_invalid()


def _broker_remaining(channel: socket.socket, deadline: float) -> None:
    """部分受信で期限を延ばさない。"""
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise _broker_invalid()
    channel.settimeout(remaining)


def _broker_receive(channel: socket.socket, deadline: float) -> bytes:
    """単一responseと終端だけを有限期限で読み、末尾余剰も拒否する。"""
    chunks = bytearray()
    wanted = 4
    while len(chunks) < wanted:
        _broker_remaining(channel, deadline)
        part = channel.recv(wanted - len(chunks))
        if not part:
            raise _broker_invalid()
        chunks.extend(part)
        if len(chunks) == 4:
            size = int.from_bytes(chunks, "big")
            if not 0 < size <= _BROKER_MAX_FRAME:
                raise _broker_invalid()
            wanted = size + 4
    _broker_remaining(channel, deadline)
    if channel.recv(1) != b"":
        raise _broker_invalid()
    return bytes(chunks)


class _InitialBrokerClient:
    """固定root endpointへの一回通信だけ。自動再試行/成功補完をしない。"""

    __slots__ = ("_endpoint",)

    def __init__(self) -> None:
        """callerのsocket/engine/callbackを受けず、root公開設定を読む。"""
        try:
            self._endpoint = _load_broker_endpoint()
        except (OSError, ValueError, InitialBrokerUnavailable):
            pass
        else:
            return
        raise _broker_invalid()

    def call(self, command: _BrokerCommand) -> _BrokerReply:
        """実workerが無い/応答不明なら固定例外で閉じ、業務結果を推測しない。"""
        try:
            frame = _encode_initial_command(command)
            _check_broker_socket(self._endpoint)
            deadline = monotonic() + _BROKER_TIMEOUT
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                _broker_remaining(channel, deadline)
                channel.connect(str(self._endpoint.path))
                _check_broker_peer(channel)
                _check_broker_socket(self._endpoint)
                _broker_remaining(channel, deadline)
                channel.sendall(frame)
                channel.shutdown(socket.SHUT_WR)
                response = _broker_receive(channel, deadline)
            return _decode_initial_reply(response, command)
        except (OSError, ValueError, TypeError, InitialBrokerUnavailable):
            pass
        raise _broker_invalid()


_INITIAL_AUTH_VERIFIER_ROLE = "pitchlog_initial_auth_verifier"
_AUTH_VERIFIER_CHECKOUT_SQL = """
                SELECT session_user::text, current_user::text,
                       r.rolcanlogin, r.rolsuper, r.rolbypassrls, r.rolinherit,
                       r.rolcreaterole, r.rolcreatedb, r.rolreplication,
                       (SELECT count(*) FROM pg_catalog.pg_auth_members AS m
                        WHERE m.member = r.oid OR m.roleid = r.oid),
                       pg_catalog.current_setting('app.tenant_id', true),
                       pg_catalog.current_database()::text, d.oid::integer,
                       pg_catalog.pg_postmaster_start_time(),
                       pg_catalog.pg_backend_pid()
                FROM pg_catalog.pg_roles AS r
                JOIN pg_catalog.pg_database AS d
                  ON d.datname = pg_catalog.current_database()
                WHERE r.rolname = session_user
            """


class _InitialAuthVerifierRuntime:
    """rootが登録した検証専用poolの非転送可能な参照。"""

    __slots__ = ("_key",)

    def __init__(self, key: object, creation: object) -> None:
        """同型の偽runtimeを登録済みにしない。"""
        if creation is not _RUNTIME_CREATION or key not in _AUTH_VERIFIER_RUNTIMES:
            raise _broker_invalid()
        self._key = key


@dataclass(frozen=True, slots=True, repr=False)
class _AuthVerifierState:
    engine: Engine
    configuration: _ActorConfiguration
    presentation: object


_AUTH_VERIFIER_RUNTIMES: dict[object, _AuthVerifierState] = {}


def _auth_verifier_state(runtime: object) -> _AuthVerifierState:
    """閉runtimeの実型/registry/失効を確認する。"""
    if type(runtime) is not _InitialAuthVerifierRuntime:
        raise _broker_invalid()
    state = _AUTH_VERIFIER_RUNTIMES.get(runtime._key)
    if state is None:
        raise _broker_invalid()
    return state


def _validate_auth_verifier_observation(
    row: tuple[object, ...], config: _ActorConfiguration
) -> None:
    """専用roleと実DBを照合し、actor値へ変換した偽観測を使わない。"""
    if (
        len(row) != 15
        or row[:2] != (_INITIAL_AUTH_VERIFIER_ROLE, _INITIAL_AUTH_VERIFIER_ROLE)
        or tuple(row[2:9]) != (True, False, False, False, False, False, False)
        or any(type(v) is not bool for v in row[2:9])
        or type(row[9]) is not int
        or row[9] != 0
        or row[10] not in (None, "")
        or row[11] != config.database_name
        or type(row[12]) is not int
        or row[12] != config.database_oid
        or type(row[13]) is not datetime
        or row[13] != config.postmaster_started_at
        or type(row[14]) is not int
        or row[14] <= 0
    ):
        raise _broker_invalid()


def _verify_auth_verifier_checkout(
    connection: Any, config: _ActorConfiguration
) -> None:
    """実peer接続の検証専用主体をcheckoutごとに照合する。"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(_AUTH_VERIFIER_CHECKOUT_SQL)
            row = cursor.fetchone()
            if row is None or cursor.fetchone() is not None:
                raise _broker_invalid()
            _validate_auth_verifier_observation(tuple(row), config)
        connection.rollback()
    except Exception:
        try:
            connection.rollback()
        except BaseException:
            pass
        raise DisconnectionError("専用Cookie検証接続を確認できない") from None


def _initial_auth_verifier_url(config: _ActorConfiguration) -> str:
    """登録actorの同じUnix endpointのuserだけを固定置換する。"""
    from sqlalchemy.engine import make_url

    try:
        url = make_url(normalize_postgresql_url(config.database_url))
        query = dict(url.query)
        host = query.get("host", url.host)
        if (
            url.username != _ACTOR_ROLE
            or url.password is not None
            or type(host) is not str
            or not host.startswith("/")
            or "," in host
            or any(k not in {"host", "port", "sslmode", "gssencmode"} for k in query)
            or query.get("sslmode", "disable") != "disable"
            or query.get("gssencmode", "disable") != "disable"
            or url.database != config.database_name
        ):
            raise ValueError
        return url.set(username=_INITIAL_AUTH_VERIFIER_ROLE).render_as_string(
            hide_password=False
        )
    except (ValueError, TypeError, AttributeError):
        pass
    raise _broker_invalid()


def _load_initial_auth_verifier_runtime(
    actor_runtime: object, presentation: object
) -> _InitialAuthVerifierRuntime:
    """既root署名器と登録済みactor設定だけから専用runtimeを発行する。"""
    from pitchlog.authz import verified_tenant
    from pitchlog.authz.token_presentation import TokenPresentation

    engine: Engine | None = None
    try:
        if os.geteuid() != 0 or type(presentation) is not TokenPresentation:
            raise _broker_invalid()
        active = verified_tenant._ACTIVE_PRESENTATION
        if (
            active is None
            or active[0] is not presentation
            or active[1] is not presentation._key
        ):
            raise _broker_invalid()
        config = _actor_state(actor_runtime).configuration
        url = _initial_auth_verifier_url(config)
        args = engine_connect_args(False)
        args["gssencmode"] = "disable"
        args["connect_timeout"] = 1
        args["options"] = "-c statement_timeout=1500 -c lock_timeout=1000"
        args["passfile"] = "/dev/null"
        require_database_transport(url, args)
        engine = create_engine(
            url,
            connect_args=args,
            hide_parameters=True,
            pool_size=3,
            max_overflow=0,
            pool_timeout=0.5,
        )

        def checkout(connection: Any, record: Any, proxy: Any) -> None:
            """専用poolからの実接続だけを検証する。"""
            del record, proxy
            _verify_auth_verifier_checkout(connection, config)

        event.listen(engine, "checkout", checkout)
    except Exception:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
    else:
        key = object()
        _AUTH_VERIFIER_RUNTIMES[key] = _AuthVerifierState(engine, config, presentation)
        return _InitialAuthVerifierRuntime(key, _RUNTIME_CREATION)
    raise _broker_invalid()


def _close_initial_auth_verifier_runtime(runtime: object) -> None:
    """失効したruntimeを再使用できず、所有poolだけを閉じる。"""
    state = _auth_verifier_state(runtime)
    assert type(runtime) is _InitialAuthVerifierRuntime
    del _AUTH_VERIFIER_RUNTIMES[runtime._key]
    try:
        state.engine.dispose()
    except Exception:
        pass
    else:
        return
    raise _broker_invalid()


def _verify_initial_cookie(
    runtime: object, cookie: SecretStr
) -> tuple[UUID, datetime] | None:
    """実署名/実DB照合結果だけを返し、入力やdriver故障を漏らさない。"""
    from pitchlog.authz.token_presentation import TokenPresentation
    from pitchlog.authz.verified_tenant import verify_tenant_id

    try:
        state = _auth_verifier_state(runtime)
        _broker_secret(cookie)
        if type(state.presentation) is not TokenPresentation:
            raise _broker_invalid()
        return verify_tenant_id(
            cookie.get_secret_value(), state.presentation, state.engine
        )
    except Exception:
        pass
    raise _broker_invalid()


class _InitialEnrollmentOutcomeUnknown(InitialGrantUnavailable):
    """commit以降の結果不明。成功補完・再試行・資格再生をしない。"""


def _enroll_initial_device(
    context: TenantContext,
    actor_runtime: _InitialActorRuntime,
) -> InitialDeviceEnrollmentResponse:
    """実contextとactorだけから一回生成し、実commit後だけ資格を返す。"""
    from pitchlog.repositories.initial_recording_right import _EnrollDeviceToken
    from pitchlog.repositories.rg1 import assert_rg1_open_before_commit, read_rg1_open
    from pitchlog.repositories.transaction import (
        _EnrollmentBinding,
        _initial_enrollment_transaction_scope,
    )

    if type(context) is not TenantContext or not context._has_valid_integrity_proof():
        raise InitialGrantUnavailable("端末登録の文脈が不正")
    _initial_actor_engine(actor_runtime)
    device_id = uuid4()
    credential = secrets.token_urlsafe(32)
    digest = _credential_digest(credential)
    binding = _EnrollmentBinding(context, actor_runtime, device_id, digest)
    failed = False
    try:
        with _initial_enrollment_transaction_scope(binding) as transaction:
            _verify_business_binding(transaction, actor_runtime)
            read_rg1_open(transaction)
            result = transaction.run_function(_EnrollDeviceToken(device_id, digest))
            if result.rows != ((device_id,),):
                raise InitialGrantUnavailable("端末登録の戻り値が不一致")
            assert_rg1_open_before_commit(transaction)
    except Exception:
        failed = True
    if failed:
        if binding.commit_attempted:
            raise _InitialEnrollmentOutcomeUnknown("端末登録の確定結果が不明") from None
        raise InitialGrantUnavailable("端末登録は確定せず終了") from None
    if not binding.commit_completed:
        raise _InitialEnrollmentOutcomeUnknown("端末登録の確定結果が不明") from None
    return InitialDeviceEnrollmentResponse(
        tenant_id=context.tenant_id,
        device_id=device_id,
        device_credential=SecretStr(credential),
    )


@dataclass(frozen=True, slots=True)
class _WorkerState:
    """root bootstrapの実登録runtimeと固定ledgerをworker内へ保持する。"""

    actor: _InitialActorRuntime = field(repr=False)
    verifier: _InitialAuthVerifierRuntime = field(repr=False)
    source: DurableLedger = field(repr=False)


_WORKER_STATES: dict[object, _WorkerState] = {}
_WORKER_CREATION = object()


class _InitialWorkerRuntime:
    """caller Engine/DSN/任意callbackを受けない不透明な実登録。"""

    __slots__ = ("_key",)

    def __init__(self, key: object, creation: object) -> None:
        """Root bootstrapの実登録だけを受ける。"""
        if creation is not _WORKER_CREATION or key not in _WORKER_STATES:
            raise _broker_invalid()
        self._key = key


def _worker_state(runtime: object) -> _WorkerState:
    """実UID/閉型/失効/既actorとverifierの実登録を毎回確認する。"""
    from pitchlog.durable_rights_ledger import DurableLedger

    if os.geteuid() != _BROKER_SERVER_UID or type(runtime) is not _InitialWorkerRuntime:
        raise _broker_invalid()
    state = _WORKER_STATES.get(runtime._key)
    if state is None or type(state.source) is not DurableLedger:
        raise _broker_invalid()
    _initial_actor_engine(state.actor)
    _auth_verifier_state(state.verifier)
    return state


def _worker_start_bound(
    command: _StartInitialGameCommand, tenant: UUID, attempt: UUID
) -> BoundInitialStartPayload:
    """Aの専用表現を既公開DTOと唯一のowner/fingerprint束縛へ戻す。"""
    from pitchlog.api.schemas.game_start import GameStartRequest
    from pitchlog.repositories.game_start import bind_initial_start_request

    command.__post_init__()
    request = GameStartRequest.model_validate(
        _broker_command_source(command)["request"]
    )
    return bind_initial_start_request(
        request, tenant_id=tenant, game_id=command.game_id, attempt_id=attempt
    )


def _worker_resolve_start(
    command: _StartInitialGameCommand,
    context: TenantContext,
    state: _WorkerState,
    fence: RecoveryEpochFence,
) -> _InitialStartedGame | None:
    """非作成lookupとcommitted再交付を同Sessionで行い、pendingを終結としない。"""
    from pitchlog.repositories.game_start import _source
    from pitchlog.repositories.initial_recording_right import (
        _existing_start_scope_on_handle,
        _LookupExistingStartAttemptToken,
    )
    from pitchlog.repositories.rg1 import assert_rg1_open_before_commit, read_rg1_open
    from pitchlog.repositories.transaction import (
        _initial_resolution_transaction_scope,
        _ResolutionBinding,
    )
    from pitchlog.sync.idempotency import source_fingerprint

    command.__post_init__()
    credential = command.device_credential.get_secret_value()
    credential_digest = _credential_digest(credential)
    digest = bytes.fromhex(
        source_fingerprint(
            _source(
                command.payload,
                context.tenant_id,
                command.game_id,
                command.start_request_id,
                command.device_id,
                credential_digest,
            )
        )
    )
    binding = _ResolutionBinding(
        context,
        state.actor,
        command.game_id,
        command.start_request_id,
        command.device_id,
        digest,
        credential_digest,
    )
    fence.assert_held()
    with _initial_resolution_transaction_scope(binding) as transaction:
        _verify_business_binding(transaction, state.actor)
        read_rg1_open(transaction)
        transaction.run_function(_LockDeviceToken(command.device_id))
        rows = transaction.run_function(
            _LookupExistingStartAttemptToken(
                command.game_id, command.start_request_id, command.device_id, digest
            )
        ).rows
        if not rows or rows[0][1] != "committed":
            return None
        attempt = rows[0][0]
        if type(attempt) is not UUID:
            raise _broker_invalid()
        bound = _worker_start_bound(command, context.tenant_id, attempt)
        with _existing_start_scope_on_handle(
            context, bound.owner, state.actor, transaction, bound
        ) as scope:
            grant = issue_initial_recording_right(
                scope,
                tenant_id=context.tenant_id,
                game_id=command.game_id,
                device_id=command.device_id,
                device_credential=credential,
                start_request_id=command.start_request_id,
                reservation_attempt_id=attempt,
                source=state.source,
                fence=fence,
                box=_actor_state(state.actor).box,
            )
            assert_write_recovery_generation(
                scope, state.source, fence, int(grant.recovery_generation)
            )
            receipt = scope._start_receipt
            if receipt is None:
                raise _broker_invalid()
        assert_rg1_open_before_commit(transaction)
        fence.assert_held()
    fence.assert_held()
    return _InitialStartedGame(grant, receipt)


def _dispatch_initial_command(command: _BrokerCommand, runtime: object) -> _BrokerReply:
    """閉3操作だけを実Cookie→私有製品入口へ接ぎ、成功はpostcommitだけ。"""
    from pitchlog.repositories.tenant_context_issuance import (
        _issue_initial_broker_context,
    )

    state = _worker_state(runtime)
    # 再encode/decodeで強制改変も拒否し、wire外の能力を受け取らない。
    command = _decode_initial_command(_encode_initial_command(command))
    selected = cast(
        _EnrollDeviceCommand | _StartInitialGameCommand,
        command.original if type(command) is _ResolveStartCommand else command,
    )
    assert type(selected) in (_EnrollDeviceCommand, _StartInitialGameCommand)
    verified = _issue_initial_broker_context(
        selected.identity.cookie, selected.identity.expected_tenant_id, state.verifier
    )
    if verified is None:
        return _BrokerReply("denied")
    context = verified[0]
    if type(command) is _EnrollDeviceCommand:
        try:
            response = _enroll_initial_device(context, state.actor)
        except _InitialEnrollmentOutcomeUnknown:
            # enrollにはunresolved wire値がない。資格を送らず接続失敗へ残す。
            raise _broker_invalid() from None
        except InitialGrantUnavailable:
            return _BrokerReply("unavailable")
        return _BrokerReply("enrolled", response)
    assert type(selected) is _StartInitialGameCommand
    try:
        with state.source.recovery_fence() as fence:
            if type(command) is _ResolveStartCommand:
                result = _worker_resolve_start(selected, context, state, fence)
                if result is None:
                    return _BrokerReply("unresolved")
                owner = result.receipt.owner
            else:
                bound = _worker_start_bound(selected, context.tenant_id, uuid4())
                result = _start_initial_game(
                    context,
                    state.actor,
                    bound,
                    selected.device_credential.get_secret_value(),
                    state.source,
                    fence,
                )
                owner = result.receipt.owner
                if (
                    owner.tenant_id,
                    owner.game_id,
                    owner.start_request_id,
                    owner.device_id,
                    owner.request_digest,
                ) != (
                    bound.owner.tenant_id,
                    bound.owner.game_id,
                    bound.owner.start_request_id,
                    bound.owner.device_id,
                    bound.owner.request_digest,
                ):
                    raise _broker_invalid()
            response = _postcommit_start_response(result, owner)
            fence.assert_held()
        return _BrokerReply("started", response)
    except Exception as error:
        # claim/commitに着手した可能性を失敗メッセージから取消へ推測しない。
        from pitchlog.recording_rights.initial_grant import InitialGrantConflict

        conflict = isinstance(error, InitialGrantConflict)
    return _BrokerReply("conflict" if conflict else "unresolved")


def _worker_peer(channel: socket.socket) -> None:
    """appのkernel資格だけを許し、tenant認証は別に実行する。"""
    _, uid, gid = struct.unpack(
        "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    if (uid, gid) != (20003, 20003):
        raise _broker_invalid()


def _worker_connection(
    channel: socket.socket, endpoint: _BrokerEndpoint, runtime: object, accepted: float
) -> None:
    """queue期限とframe/socket期限を固定し、原例外を外へ出さず一要求で閉じる。"""
    with channel:
        try:
            if monotonic() - accepted > 1.0:
                raise _broker_invalid()
            _worker_peer(channel)
            _check_broker_socket(endpoint)
            frame = _broker_receive(channel, monotonic() + 1.5)
            command = _decode_initial_command(frame)
            reply = _dispatch_initial_command(command, runtime)
            response = _encode_initial_reply(command, reply)
            _broker_remaining(channel, monotonic() + 1.5)
            channel.sendall(response)
            channel.shutdown(socket.SHUT_WR)
        except Exception:
            # 不明の業務をrollbackや未使用D4へ変換せず、資格もechoしない。
            return


def _worker_configuration(path: Path) -> dict[str, str]:
    """root保護の有限pathだけを読み、任意engine/key/role/timeoutを受けない。"""
    try:
        _broker_trusted_parents(path)
        with os.fdopen(
            os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb"
        ) as file:
            info = os.fstat(file.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > 16384
            ):
                raise _broker_invalid()
            value = json.loads(file.read(16385), object_pairs_hook=_json_object)
        if type(value) is not dict or set(value) != {
            "version",
            "socket_path",
            "actor_config",
            "ledger_endpoint",
            "rg1_client_config",
        }:
            raise _broker_invalid()
        if type(value["version"]) is not int or value["version"] != 1:
            raise _broker_invalid()
        result = {}
        for key in (
            "socket_path",
            "actor_config",
            "ledger_endpoint",
            "rg1_client_config",
        ):
            item = value[key]
            if type(item) is not str or "\0" in item or not Path(item).is_absolute():
                raise _broker_invalid()
            _broker_trusted_parents(Path(item))
            result[key] = item
        if not 0 < len(os.fsencode(result["socket_path"])) < 108:
            raise _broker_invalid()
        return result
    except Exception:
        pass
    raise _broker_invalid()


def _expire_initial_queue(pending: queue.Queue[tuple[socket.socket, float]]) -> None:
    """処理workerがbusyでも、期限切れqueueのsocketをmain側で有限回掃除する。"""
    fresh = []
    for _ in range(3):
        try:
            channel, accepted = pending.get_nowait()
        except queue.Empty:
            break
        pending.task_done()
        if monotonic() - accepted > 1.0:
            channel.close()
        else:
            fresh.append((channel, accepted))
    for item in fresh:
        pending.put_nowait(item)


def serve_initial_broker(config_path: Path, presentation: object, box: V12Box) -> None:
    """Root bootstrapだけが降格後の閉workerを起動する。HTTP/運用鍵配置は行わない。"""
    from pitchlog.authz.token_presentation import TokenPresentation
    from pitchlog.durable_rights_ledger import DurableLedger
    from pitchlog.recording_rights.rg1_lifecycle import configure_runtime

    if (
        os.geteuid() != 0
        or type(presentation) is not TokenPresentation
        or type(box) is not V12Box
    ):
        raise _broker_invalid()
    actor = verifier = None
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stop = threading.Event()
    pending: queue.Queue[tuple[socket.socket, float]] = queue.Queue(maxsize=3)
    workers = []
    runtime_key = object()
    failed = False
    try:
        config = _worker_configuration(config_path)
        actor = _load_initial_actor_runtime(Path(config["actor_config"]), box)
        verifier = _load_initial_auth_verifier_runtime(actor, presentation)
        endpoint_path = _BROKER_ENDPOINT_PATH
        _broker_trusted_parents(endpoint_path)
        if endpoint_path.exists() or endpoint_path.is_symlink():
            raise _broker_invalid()
        path = Path(config["socket_path"])
        listener.bind(str(path))
        os.chown(path, 20002, 20003)
        os.chmod(path, 0o660)
        info = path.stat(follow_symlinks=False)
        endpoint = _BrokerEndpoint(path, info.st_dev, info.st_ino, 20003)
        _check_broker_socket(endpoint)
        endpoint_body = {
            "version": 1,
            "socket_path": str(path),
            "socket_device": info.st_dev,
            "socket_inode": info.st_ino,
            "socket_gid": 20003,
        }
        fd = os.open(
            endpoint_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o644,
        )
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o644)
            output.write(_broker_json(endpoint_body))
            output.flush()
            os.fsync(output.fileno())
        os.setgroups([])
        os.setgid(20002)
        os.setuid(20002)
        libc = ctypes.CDLL(None, use_errno=True)
        if (
            libc.prctl(38, 1, 0, 0, 0) != 0
            or os.geteuid() != 20002
            or os.getegid() != 20002
        ):
            raise _broker_invalid()
        configure_runtime(Path(config["rg1_client_config"]))
        source = DurableLedger(Path(config["ledger_endpoint"]))
        _WORKER_STATES[runtime_key] = _WorkerState(actor, verifier, source)
        runtime = _InitialWorkerRuntime(runtime_key, _WORKER_CREATION)
        listener.listen(3)
        listener.settimeout(0.05)

        def work() -> None:
            """有限queueから一要求ずつ取り、失敗値や秘密をlogへ出さない。"""
            while not stop.is_set():
                try:
                    channel, accepted = pending.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    _worker_connection(channel, endpoint, runtime, accepted)
                finally:
                    pending.task_done()

        for _ in range(3):
            worker = threading.Thread(target=work, daemon=True)
            worker.start()
            workers.append(worker)
        while True:
            _expire_initial_queue(pending)
            try:
                channel, _address = listener.accept()
            except TimeoutError:
                continue
            try:
                _worker_peer(channel)
                pending.put_nowait((channel, monotonic()))
            except (OSError, InitialBrokerUnavailable, queue.Full):
                channel.close()
    except Exception:
        failed = True
    finally:
        stop.set()
        listener.close()
        while True:
            try:
                channel, _accepted = pending.get_nowait()
            except queue.Empty:
                break
            channel.close()
            pending.task_done()
        for worker in workers:
            worker.join(timeout=2)
        _WORKER_STATES.pop(runtime_key, None)
        if verifier is not None:
            try:
                _close_initial_auth_verifier_runtime(verifier)
            except Exception:
                failed = True
        if actor is not None:
            try:
                _close_initial_actor_runtime(actor)
            except Exception:
                failed = True
    if failed:
        raise _broker_invalid() from None
