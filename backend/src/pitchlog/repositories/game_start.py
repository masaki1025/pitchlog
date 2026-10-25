"""開始要求を閉じた不変値とowner束縛へ写す。開始や野球判定は行わない。"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import SecretStr

from pitchlog.api.schemas.game_start import GameStartRequest, StartLineupInput
from pitchlog.recording_rights.initial_grant import InitialGrantUnavailable
from pitchlog.repositories.initial_recording_right import (
    _credential_digest,
    _StartOwner,
)
from pitchlog.sync.idempotency import source_fingerprint

_DOMAIN = "pitchlog.initial-game-start.v1"


class InitialStartPayloadInvalid(ValueError):
    """入力原文や資格を含めない閉じたtransport失敗。"""

    def __init__(self) -> None:
        """入力値を受けない固定メッセージを使う。"""
        super().__init__("開始payloadの閉型又はowner束縛が不正")


@dataclass(frozen=True, slots=True)
class StartFieldingRole:
    """既T1のfielding roleの形だけを保持する。"""

    position: int

    def __post_init__(self) -> None:
        """bool/float等の暗黙変換をせず1〜9へ閉じる。"""
        if type(self.position) is not int or not 1 <= self.position <= 9:
            raise InitialStartPayloadInvalid()


@dataclass(frozen=True, slots=True)
class StartDesignatedHitterRole:
    """既T1のdesignated-hitter roleを不変なtagとして保持する。"""


type StartRole = StartFieldingRole | StartDesignatedHitterRole


@dataclass(frozen=True, slots=True)
class InitialStartLineupEntry:
    """所属やDH整合を証明しない公式選手のtransport閉型。"""

    player_id: UUID
    batting_order: int | None
    fielding_position: StartRole

    def __post_init__(self) -> None:
        """公式UUID・StrictInt/null・閉roleのexact型だけを検査する。"""
        if (
            type(self.player_id) is not UUID
            or (
                self.batting_order is not None
                and (
                    type(self.batting_order) is not int
                    or not 1 <= self.batting_order <= 9
                )
            )
            or type(self.fielding_position)
            not in (StartFieldingRole, StartDesignatedHitterRole)
        ):
            raise InitialStartPayloadInvalid()
        if type(self.fielding_position) is StartFieldingRole:
            self.fielding_position.__post_init__()


@dataclass(frozen=True, slots=True)
class InitialStartPayload:
    """9/10外形の両側を深く凍結する。名簿の業務受理を表さない。"""

    away: tuple[InitialStartLineupEntry, ...]
    home: tuple[InitialStartLineupEntry, ...]

    def __post_init__(self) -> None:
        """list/派生entry等を排除し、両sideの外形だけを検査する。"""
        for side in (self.away, self.home):
            if (
                type(side) is not tuple
                or len(side) not in (9, 10)
                or any(type(entry) is not InitialStartLineupEntry for entry in side)
            ):
                raise InitialStartPayloadInvalid()
            for entry in side:
                entry.__post_init__()


def _freeze_entry(entry: object) -> InitialStartLineupEntry:
    """既DTOのJSON roleを値変換せず既T1形の閉unionへ写す。"""
    if (
        type(entry) is not StartLineupInput
        or entry.model_extra
        or set(vars(entry)) != {"player_id", "batting_order", "fielding_position"}
    ):
        raise InitialStartPayloadInvalid()
    role = entry.fielding_position
    if type(role) is not dict or type(role.get("kind")) is not str:
        raise InitialStartPayloadInvalid()
    closed: StartRole
    if set(role) == {"kind", "position"} and role["kind"] == "fielding":
        position = role["position"]
        if type(position) is not int:
            raise InitialStartPayloadInvalid()
        closed = StartFieldingRole(position)
    elif set(role) == {"kind"} and role["kind"] == "designated-hitter":
        closed = StartDesignatedHitterRole()
    else:
        raise InitialStartPayloadInvalid()
    return InitialStartLineupEntry(entry.player_id, entry.batting_order, closed)


def _entries(side: object) -> tuple[InitialStartLineupEntry, ...]:
    """既DTOのtupleを新しい不変entryへ写して入力aliasを残さない。"""
    if type(side) is not tuple or len(side) not in (9, 10):
        raise InitialStartPayloadInvalid()
    return tuple(_freeze_entry(entry) for entry in side)


def _entry_json(entry: InitialStartLineupEntry) -> dict[str, object]:
    """canonical用の新しいJSON objectを作り内部の不変値を公開しない。"""
    if type(entry) is not InitialStartLineupEntry:
        raise InitialStartPayloadInvalid()
    entry.__post_init__()
    role: dict[str, object]
    if type(entry.fielding_position) is StartFieldingRole:
        role = {"kind": "fielding", "position": entry.fielding_position.position}
    elif type(entry.fielding_position) is StartDesignatedHitterRole:
        role = {"kind": "designated-hitter"}
    else:
        raise InitialStartPayloadInvalid()
    return {
        "player_id": str(entry.player_id),
        "batting_order": entry.batting_order,
        "fielding_position": role,
    }


@dataclass(frozen=True, slots=True)
class BoundInitialStartPayload:
    """要求全体の同値性だけを結合する。認証やowner真正性の証明ではない。"""

    payload: InitialStartPayload
    owner: _StartOwner
    credential_digest: bytes = field(repr=False)

    def __post_init__(self) -> None:
        """呼出側のdigestだけの構築を拒否し単一helperで実値を再計算する。"""
        if (
            type(self.payload) is not InitialStartPayload
            or type(self.owner) is not _StartOwner
            or type(self.credential_digest) is not bytes
            or len(self.credential_digest) != 32
        ):
            raise InitialStartPayloadInvalid()
        self.payload.__post_init__()
        owner_valid = False
        try:
            self.owner.__post_init__()
            owner_valid = True
        except InitialGrantUnavailable:
            pass
        if not owner_valid:
            raise InitialStartPayloadInvalid()
        actual = bytes.fromhex(source_fingerprint(self._source()))
        if not hmac.compare_digest(actual, self.owner.request_digest):
            raise InitialStartPayloadInvalid()

    def _source(self) -> dict[str, object]:
        """資格原文とattemptを含めず全要求と既資格digestを結合する。"""
        return _source(
            self.payload,
            self.owner.tenant_id,
            self.owner.game_id,
            self.owner.start_request_id,
            self.owner.device_id,
            self.credential_digest,
        )

    @property
    def canonical_bytes(self) -> bytes:
        """既source_fingerprintと同じJSON表現の不変UTF-8 bytesを返す。"""
        self.__post_init__()
        return json.dumps(
            self._source(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def assert_owner(self, owner: _StartOwner) -> None:
        """同attemptを含むowner同値を検査するが認証成功とは扱わない。"""
        self.__post_init__()
        if type(owner) is not _StartOwner or owner != self.owner:
            raise InitialStartPayloadInvalid()


def _source(
    payload: InitialStartPayload,
    tenant_id: UUID,
    game_id: UUID,
    request_id: UUID,
    device_id: UUID,
    credential_digest: bytes,
) -> dict[str, object]:
    """固定domainと閉値だけで指紋素材を構成し配列順を保持する。"""
    return {
        "domain": _DOMAIN,
        "tenant_id": str(tenant_id),
        "game_id": str(game_id),
        "start_request_id": str(request_id),
        "device_id": str(device_id),
        "credential_digest": credential_digest.hex(),
        "away": [_entry_json(entry) for entry in payload.away],
        "home": [_entry_json(entry) for entry in payload.home],
    }


def bind_initial_start_request(
    request: GameStartRequest,
    *,
    tenant_id: UUID,
    game_id: UUID,
    attempt_id: UUID,
) -> BoundInitialStartPayload:
    """既DTOを凍結しserverでdigestと既ownerを作る。DBには接続しない。

    Args:
        request: 既入力DTO。成功してもDH・所属・権限は未受理。
        tenant_id: 呼出側が別途認証するtenant。UUIDだけは認可証明ではない。
        game_id: URLから解決する対象試合。
        attempt_id: brokerが供給する耐久attempt。要求指紋には含めない。

    Returns:
        資格原文を保持しない不変payloadとowner束縛。

    Raises:
        InitialStartPayloadInvalid: 閉型又は結合値が不正な場合。
    """
    if (
        type(request) is not GameStartRequest
        or request.model_extra
        or set(vars(request))
        != {"start_request_id", "device_id", "device_credential", "away", "home"}
    ):
        raise InitialStartPayloadInvalid()
    if (
        any(
            type(value) is not UUID
            for value in (
                tenant_id,
                game_id,
                attempt_id,
                request.start_request_id,
                request.device_id,
            )
        )
        or type(request.device_credential) is not SecretStr
    ):
        raise InitialStartPayloadInvalid()
    payload = InitialStartPayload(_entries(request.away), _entries(request.home))
    credential_digest = None
    try:
        credential_digest = _credential_digest(
            request.device_credential.get_secret_value()
        )
    except InitialGrantUnavailable:
        pass
    # 既helperの原例外contextを連鎖せず、資格を公開失敗へ持ち出さない。
    if credential_digest is None:
        raise InitialStartPayloadInvalid()
    digest = bytes.fromhex(
        source_fingerprint(
            _source(
                payload,
                tenant_id,
                game_id,
                request.start_request_id,
                request.device_id,
                credential_digest,
            )
        )
    )
    owner = _StartOwner(
        tenant_id,
        game_id,
        request.start_request_id,
        request.device_id,
        attempt_id,
        digest,
    )
    return BoundInitialStartPayload(payload, owner, credential_digest)
