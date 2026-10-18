"""初期記録権の単一発行と同一端末への安全な再交付を定義する。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = (
    "InitialGrant",
    "InitialGrantUnavailable",
    "InitialGrantConflict",
    "InitialGrantRecord",
    "ProofEnvelope",
    "RecoveryEpochFence",
    "V12Box",
    "assert_write_recovery_generation",
    "issue_initial_recording_right",
)


class InitialGrantUnavailable(RuntimeError):
    """発行源、秘密値または復旧世代を検証できないことを表す。"""


class InitialGrantConflict(RuntimeError):
    """同一試合・要求の現権利と再交付条件が一致しないことを表す。"""


@dataclass(frozen=True, slots=True)
class ProofEnvelope:
    """同一要求へだけ再交付するV12の暗号文。"""

    key_id: str
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class InitialGrantRecord:
    """業務DBの同一transactionへ保存する世代と配達値。"""

    tenant_id: UUID
    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    generation: int
    recovery_generation: int
    proof_digest: bytes = field(repr=False)
    envelope: ProofEnvelope = field(repr=False)


@dataclass(frozen=True, slots=True)
class InitialGrant:
    """確定済み開始応答へ渡す記録権値。"""

    game_id: UUID
    generation: int
    recovery_generation: str
    holder_device_id: UUID
    recording_right_proof: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ReservedGeneration:
    """外部台帳の耐久予約結果。"""

    generation: int
    recovery_generation: int
    tenant_id: UUID
    game_id: UUID
    start_request_id: UUID


class DurableGenerationSource(Protocol):
    """復元外の同期保全台帳にだけ実装する予約境界。"""

    def current_recovery_generation(self) -> int:
        """耐久記録済みの現復旧世代を返す。"""
        ...

    def reserve(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> ReservedGeneration:
        """ownerを束縛し、未使用attemptなら同じD4を耐久再照会する。"""
        ...

    def claim(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> None:
        """所有要求を再束縛し、業務DB使用前に一度だけ耐久消費する。"""
        ...


class RecoveryEpochFence(Protocol):
    """外部epoch行の共有ロックを業務DB commitまで保持する借用境界。"""

    @property
    def generation(self) -> int:
        """ロックされた外部の現復旧世代を返す。"""
        ...

    def assert_held(self) -> None:
        """保持が切れた場合は書込みを失敗閉鎖する。"""
        ...


class InitialGrantScope(Protocol):
    """U-G1の同一tenant scope内で実装する閉じたDB操作集合。"""

    def assert_bound_tenant(self, tenant_id: UUID) -> None:
        """実行器の固定済みtenantと入力値が一致することを確認する。"""
        ...

    def lock_valid_device(self, device_id: UUID, credential: str) -> bool:
        """資格行を共有ロックし、失効との直列化をcommitまで保持する。"""
        ...

    def existing_start(
        self, game_id: UUID, start_request_id: UUID
    ) -> InitialGrantRecord | None:
        """現権利かつ未失効の同一開始を読む。越境は不在として返す。"""
        ...

    def precheck_open_and_game(self, game_id: UUID) -> None:
        """予約前にRG1と対象試合を非ロックで確認する。"""
        ...

    def lock_preparing_game(self, game_id: UUID) -> None:
        """自tenantのpreparing試合1行をFOR UPDATEし状態を再照合する。"""
        ...

    def lock_current_start(
        self, game_id: UUID, start_request_id: UUID
    ) -> InitialGrantRecord | None:
        """試合→現世代→配達の順でロックし、現権利を再照合する。"""
        ...

    def assert_recovery_generation(self, value: int) -> None:
        """業務DBのRG1現復旧世代との一致を照合する。"""
        ...

    def insert_initial_grant(self, record: InitialGrantRecord) -> None:
        """現世代と配達暗号文を同一transactionで一意に挿入する。"""
        ...

    def assert_open_before_commit(self) -> None:
        """既存RG1の共有ロックをcommitまで保持する。"""
        ...


class V12Box:
    """業務DB外の鍵を用い、再交付値を要求と端末へ束縛する。"""

    def __init__(
        self,
        key_id: str,
        key: bytes,
        *,
        previous_keys: Mapping[str, bytes] | None = None,
    ) -> None:
        """現行鍵と保持中の旧鍵を受け取る。鍵の取得元は公開しない。"""
        if not key_id or type(key) is not bytes or len(key) != 32:
            raise ValueError("V12の暗号鍵設定が不正")
        old_keys = {} if previous_keys is None else dict(previous_keys)
        if key_id in old_keys or any(
            not old_id or type(old_key) is not bytes or len(old_key) != 32
            for old_id, old_key in old_keys.items()
        ):
            raise ValueError("V12の旧鍵設定が不正")
        self._key_id = key_id
        self._aead = AESGCM(key)
        self._read_keys = {key_id: self._aead}
        self._read_keys.update(
            {old_id: AESGCM(old_key) for old_id, old_key in old_keys.items()}
        )

    @staticmethod
    def _aad(
        tenant_id: UUID,
        game_id: UUID,
        start_request_id: UUID,
        device_id: UUID,
        generation: int,
        recovery_generation: int,
    ) -> bytes:
        """暗号文の再利用先を一意の固定長成分へ閉じる。"""
        if (
            any(
                type(value) is not UUID
                for value in (tenant_id, game_id, start_request_id, device_id)
            )
            or type(generation) is not int
            or type(recovery_generation) is not int
            or not 0 < generation < 2**63
            or not 0 < recovery_generation < 2**63
        ):
            raise ValueError("記録権の束縛値が不正")
        return (
            tenant_id.bytes
            + game_id.bytes
            + start_request_id.bytes
            + device_id.bytes
            + generation.to_bytes(8, "big")
            + recovery_generation.to_bytes(8, "big")
        )

    def issue(
        self,
        tenant_id: UUID,
        game_id: UUID,
        start_request_id: UUID,
        device_id: UUID,
        generation: int,
        recovery_generation: int,
    ) -> tuple[str, bytes, ProofEnvelope]:
        """新しい256-bit V12と検証digest・暗号化再交付値を作る。"""
        aad = self._aad(
            tenant_id,
            game_id,
            start_request_id,
            device_id,
            generation,
            recovery_generation,
        )
        raw = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        envelope = ProofEnvelope(
            self._key_id, nonce, self._aead.encrypt(nonce, raw, aad)
        )
        proof = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        return proof, hashlib.sha256(raw).digest(), envelope

    def reopen(self, record: InitialGrantRecord) -> str:
        """同じ要求・端末・世代へだけV12を復号する。"""
        aead = self._read_keys.get(record.envelope.key_id)
        if aead is None:
            raise InitialGrantUnavailable("記録権証明を再交付できない")
        try:
            raw = aead.decrypt(
                record.envelope.nonce,
                record.envelope.ciphertext,
                self._aad(
                    record.tenant_id,
                    record.game_id,
                    record.start_request_id,
                    record.device_id,
                    record.generation,
                    record.recovery_generation,
                ),
            )
        except (InvalidTag, ValueError) as error:
            raise InitialGrantUnavailable("記録権証明を再交付できない") from error
        if len(raw) != 32 or not hmac.compare_digest(
            hashlib.sha256(raw).digest(), record.proof_digest
        ):
            raise InitialGrantUnavailable("記録権証明を再交付できない")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def assert_write_recovery_generation(
    scope: InitialGrantScope,
    source: DurableGenerationSource,
    fence: RecoveryEpochFence,
    expected: int,
) -> None:
    """通常書込み直前に外部現値・業務DB現値・RG1を同じscopeで確認する。

    外部epoch行の共有ロックは業務DBのcommit後まで呼出側が保持する。
    復元開始はRG1行だけを閉じて確定した後、外部epochを排他更新する。
    U-G1/U-S1の実接合と保持期間は未受理。
    """
    fence.assert_held()
    current = source.current_recovery_generation()
    if current != expected or current != fence.generation:
        raise InitialGrantUnavailable("復旧世代が一致しない")
    scope.assert_recovery_generation(current)
    scope.assert_open_before_commit()
    fence.assert_held()


def issue_initial_recording_right(
    scope: InitialGrantScope,
    *,
    tenant_id: UUID,
    game_id: UUID,
    device_id: UUID,
    device_credential: str,
    start_request_id: UUID,
    reservation_attempt_id: UUID,
    source: DurableGenerationSource,
    fence: RecoveryEpochFence,
    box: V12Box,
) -> InitialGrant:
    """同一scopeで初期世代を作り、同一要求だけ既存証明を再交付する。

    U-G1がこの戻り値をHTTPに出す前にscopeのcommit成功を確認する。
    U-G1は他の開始書込みの後にもRG1・復旧世代の直前ゲートを行う。
    """
    if (
        type(tenant_id) is not UUID
        or type(game_id) is not UUID
        or type(device_id) is not UUID
        or type(start_request_id) is not UUID
        or type(reservation_attempt_id) is not UUID
        or type(device_credential) is not str
        or not device_credential
    ):
        raise InitialGrantUnavailable("初期付与の入力を検証できない")
    fence.assert_held()
    scope.assert_bound_tenant(tenant_id)
    # 型やtokenだけを信頼せず、資格失効と直列化する行ロックをscope終了まで保持する。
    if not scope.lock_valid_device(device_id, device_credential):
        raise InitialGrantUnavailable("端末資格を確認できない")
    existing = scope.existing_start(game_id, start_request_id)
    if existing is not None:
        if existing.device_id != device_id:
            raise InitialGrantConflict("同一開始を別端末へ再交付できない")
        scope.precheck_open_and_game(game_id)
        locked = scope.lock_current_start(game_id, start_request_id)
        if (
            locked is None
            or locked.tenant_id != tenant_id
            or locked.game_id != game_id
            or locked.start_request_id != start_request_id
            or locked.device_id != device_id
        ):
            raise InitialGrantConflict("同一開始の現権利を確認できない")
        current = source.current_recovery_generation()
        if current != locked.recovery_generation or current != fence.generation:
            raise InitialGrantUnavailable("復旧世代が一致しない")
        scope.assert_recovery_generation(current)
        scope.assert_open_before_commit()
        fence.assert_held()
        return InitialGrant(
            game_id,
            locked.generation,
            str(current),
            device_id,
            box.reopen(locked),
        )

    scope.precheck_open_and_game(game_id)
    expected_epoch = source.current_recovery_generation()
    if expected_epoch != fence.generation:
        raise InitialGrantUnavailable("復旧世代が一致しない")
    # 呼出側が予約前に耐久記録したattempt IDを使い、応答不明時に同じIDを再照会する。
    reserved = source.reserve(
        reservation_attempt_id, tenant_id, game_id, start_request_id
    )
    if reserved.recovery_generation != expected_epoch:
        raise InitialGrantUnavailable("復旧世代が一致しない")
    if (
        reserved.tenant_id != tenant_id
        or reserved.game_id != game_id
        or reserved.start_request_id != start_request_id
    ):
        raise InitialGrantConflict("D4予約の所有要求が一致しない")
    # 予約応答不明は再照会できるが、業務DBへ入る直前にD4を一度だけ消費する。
    source.claim(reservation_attempt_id, tenant_id, game_id, start_request_id)
    scope.lock_preparing_game(game_id)
    scope.assert_recovery_generation(expected_epoch)
    proof, digest, envelope = box.issue(
        tenant_id,
        game_id,
        start_request_id,
        device_id,
        reserved.generation,
        expected_epoch,
    )
    scope.insert_initial_grant(
        InitialGrantRecord(
            tenant_id,
            game_id,
            start_request_id,
            device_id,
            reserved.generation,
            expected_epoch,
            digest,
            envelope,
        )
    )
    scope.assert_open_before_commit()
    if source.current_recovery_generation() != expected_epoch:
        raise InitialGrantUnavailable("復旧世代が一致しない")
    fence.assert_held()
    return InitialGrant(
        game_id,
        reserved.generation,
        str(expected_epoch),
        device_id,
        proof,
    )
