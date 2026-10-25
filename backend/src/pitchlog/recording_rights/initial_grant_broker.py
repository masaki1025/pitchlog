"""root保護設定から作った私有actorと、単一issuerのcommit所有を接ぐ。"""

from __future__ import annotations

import hmac
import json
import os
import stat
from dataclasses import dataclass, field, replace
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DisconnectionError

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
    InitialStartReceipt,
)
from pitchlog.repositories.initial_recording_right import (
    _BeginStartAttemptToken,
    _credential_digest,
    _initial_recording_right_scope,
    _LockDeviceToken,
    _StartOwner,
)

if TYPE_CHECKING:
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
        url = normalize_postgresql_url(config.database_url)
        require_database_transport(url, args)
        engine = create_engine(url, connect_args=args, hide_parameters=True)

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
        provider = import_module("pitchlog.recording_rights.rg1_lifecycle")
    except ImportError:
        raise InitialGrantUnavailable("固定RG1 binding型が未供給") from None
    try:
        binding = provider.BusinessBinding.from_text(rows[0][0])
        config = _actor_state(runtime).configuration
        if (
            binding.system_identifier != config.system_identifier
            or binding.database_oid != config.database_oid
            or binding.database_name != config.database_name
            or binding.postmaster_started_at != config.postmaster_started_at
        ):
            raise InitialGrantUnavailable("実scope bindingがroot配置と一致しない")
    except provider.RG1ControlUnavailable:
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
