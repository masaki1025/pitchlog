"""開始名簿の配置検証を単一製品artifactへ渡す閉じた表現境界。

所属・認可・記録権・開始状態・保存の証明は作らず、Pythonで配置を計算しない。
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator, Field, TypeAdapter, ValidationError

from pitchlog.domainrt.first_pitch import (
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.first_pitch_continuation import (
    _check_frozen_members,
    _WireFrozen,
)
from pitchlog.domainrt.host import open_domain_host

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _canonical_uuid(value: str) -> str:
    """UUIDの表現だけを検査し、実在・所属を推測しない。"""
    if _UUID.fullmatch(value) is None:
        raise ValueError("canonical UUID表現が必要")
    return value


CanonicalUUID: TypeAlias = Annotated[str, AfterValidator(_canonical_uuid)]
OneToNine: TypeAlias = Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"]


class FieldingRole(_Frozen):
    """閉じた守備位置のwire表現。"""

    kind: Literal["fielding"]
    position: OneToNine


class DesignatedHitterRole(_Frozen):
    """DHのwire表現。配置の適否はartifactへ委ねる。"""

    kind: Literal["designated-hitter"]


Role: TypeAlias = FieldingRole | DesignatedHitterRole


class RosterEntry(_Frozen):
    """要求の一選手。打順と守備の組合せは計算しない。"""

    player_id: CanonicalUUID
    batting_order: OneToNine | None
    fielding_position: Role


class RosterSide(_Frozen):
    """要求の片側。順序を保持する不変tuple。"""

    team_id: CanonicalUUID
    entries: Annotated[tuple[RosterEntry, ...], Field(min_length=9, max_length=10)]


class InitialGameRosterRequest(_WireFrozen):
    """固定operationへ渡す閉要求。真正なDB sourceとは別の型。"""

    dh: bool
    away: RosterSide
    home: RosterSide


class OfficialPlayer(_Frozen):
    """公式選手参照の形。登録の存在確認ではない。"""

    kind: Literal["official"]
    player_id: CanonicalUUID


class NoBattingSlot(_Frozen):
    """打順なしの明示形。"""

    kind: Literal["none"]


class BattingSlot(_Frozen):
    """打順ありの明示形。"""

    kind: Literal["slot"]
    slot: OneToNine


class InitialOrigin(_Frozen):
    """初期出場のtag。開始receiptの代わりにはしない。"""

    kind: Literal["initial"]


class ProjectedEntry(_Frozen):
    """pointを持たない数学的な名簿射影。"""

    player: OfficialPlayer
    batting_slot: NoBattingSlot | BattingSlot
    roles: tuple[Role]
    entry_origin: InitialOrigin


class _ProjectedTeam(_Frozen):
    """順序を保つチーム射影の共通形。"""

    team_id: CanonicalUUID
    participants: Annotated[
        tuple[ProjectedEntry, ...], Field(min_length=9, max_length=10)
    ]


class ProjectedAway(_ProjectedTeam):
    """先頭に置くaway射影。"""

    side: Literal["away"]


class ProjectedHome(_ProjectedTeam):
    """後続に置くhome射影。"""

    side: Literal["home"]


class InitialRosterProjection(_Frozen):
    """受理済みABIのaway/homeの固定二要素。"""

    teams: tuple[ProjectedAway, ProjectedHome]


class InitialRosterSuccess(_Envelope):
    """配置計算の成功。開始・保存ACKではない。"""

    ok: Literal[True]
    value: InitialRosterProjection


class InitialRosterError(_Frozen):
    """artifact-localの既5拒否コード。"""

    code: Literal[
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "INVALID_INITIAL_LINEUP",
        "UNSUPPORTED_INITIAL_ROSTER_SCOPE",
    ]


class InitialRosterFailure(_Envelope):
    """非成功を同期ACKや保存許可へ変換しない。"""

    ok: Literal[False]
    error: InitialRosterError


InitialRosterResponse: TypeAlias = InitialRosterSuccess | InitialRosterFailure
_RESPONSE = TypeAdapter(InitialRosterResponse)


class InitialRosterProtocolError(RuntimeError):
    """未知又は壊れたartifact応答。公開メッセージは固定する。"""


def decode_initial_roster_response(raw: str) -> InitialRosterResponse:
    """JSONと全memberを照合し、黙った正規化を拒否する。

    Args:
        raw: 固定hostが返すJSON文字列。

    Returns:
        型付きのpoint無し射影又は既5コードの非成功。

    Raises:
        InitialRosterProtocolError: 応答が閉ABIに適合しない場合。
    """
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        decoded = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        if decoded.model_dump(mode="json", by_alias=True) != wire:
            raise ValueError("wireのkey又は表現が不一致")
        return decoded
    except (ValueError, ValidationError, TypeError):
        raise InitialRosterProtocolError(
            "開始名簿応答が固定ABIに適合しません"
        ) from None


def evaluate_initial_game_roster(
    request: InitialGameRosterRequest,
) -> InitialRosterResponse:
    """既hostの版/hash/lifetimeで固定operationを一回だけ呼ぶ。

    Args:
        request: 表現検証済みの要求。認可や真正sourceは別に必要。

    Returns:
        配置検証の結果。開始・記録権・保存の成功ではない。

    Raises:
        TypeError: 要求が指定DTOの実型ではない場合。
        ValidationError: 強制改変された入れ子member等が不正な場合。
        InitialRosterProtocolError: 応答が閉ABIと一致しない場合。
        DomainRuntimeError: 既hostの起動・実行・境界故障。
    """
    if type(request) is not InitialGameRosterRequest:
        raise TypeError("InitialGameRosterRequestの実型が必要です")
    _check_frozen_members(request)
    validated = InitialGameRosterRequest.model_validate(request)
    with open_domain_host() as host:
        return decode_initial_roster_response(
            host.call(
                "validateInitialGameRoster", validated.model_dump_json(by_alias=True)
            )
        )
