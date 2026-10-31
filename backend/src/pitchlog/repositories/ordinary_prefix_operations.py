"""private checkpointは有限固定関数だけで読み、public表制約を緩めない。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.first_ball import _FirstBallToken, _identity
from pitchlog.repositories.function_operations import (
    _SYNC_ORDINARY_PREFIX_FUNCTION_TYPES,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True)
class OrdinaryCheckpointReadToken(TenantOperationToken):
    """同tenant/game/current世代の一点だけを読む。"""

    game_id: UUID
    generation: int

    def __post_init__(self):
        """UUID/intの実型とDB範囲を検査する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.generation) is not int
            or not 0 < self.generation < 2**63
        ):
            raise ValueError("checkpoint読取識別が不正")

    @property
    def capability_id(self):
        """有限definer関数の能力だけを返す。"""
        return "CAP:sync_ordinary_pitch:read_ordinary_checkpoint"


@dataclass(frozen=True, slots=True)
class OrdinaryCheckpointLockToken(_FirstBallToken):
    """実writer nonce/leaseを用いる限定point-lock。readonly能力とは別。"""

    generation: int

    @property
    def capability_id(self):
        """実writer検証を必須にする固定関数能力。"""
        return "CAP:sync_ordinary_pitch:lock_ordinary_checkpoint"


@dataclass(frozen=True, slots=True)
class OrdinaryHistoryPageToken(TenantOperationToken):
    """版/水位/keysetを固定した最大100件＋存在確認1件。"""

    game_id: UUID
    generation: int
    history_version: int
    checkpoint_id: UUID
    checkpoint_revision: int
    upper_watermark: int
    after_d1: int
    after_d2: int
    after_id: UUID
    page_size: int

    def __post_init__(self):
        """自由tenant/SQL・bool変換・範囲外上限を拒否する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.after_id) is not UUID
            or type(self.checkpoint_id) is not UUID
            or any(
                type(x) is not int or not 0 < x < 2**63
                for x in (
                    self.generation,
                    self.history_version,
                    self.checkpoint_revision,
                )
            )
            or any(
                type(x) is not int or not 0 <= x < 2**63
                for x in (self.upper_watermark, self.after_d1, self.after_d2)
            )
            or self.after_d1 > self.upper_watermark
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= 100
        ):
            raise ValueError("履歴page識別又は上限が不正")

    @property
    def capability_id(self):
        """有限page関数の能力だけを返す。"""
        return "CAP:sync_ordinary_pitch:read_ordinary_history_page"


def _declarations():
    """任意schema/SQLを開放せずexact3関数だけを登録する。"""
    result = []
    for name, token_type in (
        ("read_ordinary_checkpoint", OrdinaryCheckpointReadToken),
        ("lock_ordinary_checkpoint", OrdinaryCheckpointLockToken),
        ("read_ordinary_history_page", OrdinaryHistoryPageToken),
    ):
        inputs, outputs, nullable, aware, minimum, maximum = (
            _SYNC_ORDINARY_PREFIX_FUNCTION_TYPES[f"sync_right_api.{name}"]
        )
        result.append(
            FunctionOperationRegistration(
                operation_id=f"SYNC_ORDINARY_PITCH:{name}",
                capability_id=f"CAP:sync_ordinary_pitch:{name}",
                token_type=token_type,
                function_id=f"sync_right_api.{name}",
                statement=_build_fixed_function_statement(
                    "sync_right_api", name, inputs, tuple(n for n, _ in outputs), True
                ),
                input_fields=inputs,
                result_fields=outputs,
                decoder=_identity,
                min_rows=minimum,
                max_rows=maximum,
                nullable_results=nullable,
                aware_datetime_results=aware,
            )
        )
    return tuple(result)


ORDINARY_PREFIX_OPERATIONS = _declarations()


def _play_prefix_declarations():
    """v2の新4関数を旧3関数と別能力へ登録する。"""
    from pitchlog.repositories.function_operations import (
        _SYNC_PLAY_PREFIX_FUNCTION_TYPES,
    )
    from pitchlog.sync.terminal_pitch_tokens import (
        PlayPrefixCheckpointLockToken,
        PlayPrefixCheckpointReadToken,
        PlayPrefixHistoryPageToken,
        PreparePlayPrefixProjectionToken,
    )

    result = []
    for name, token in [
        ("read_play_prefix_checkpoint", PlayPrefixCheckpointReadToken),
        ("lock_play_prefix_checkpoint", PlayPrefixCheckpointLockToken),
        ("read_play_prefix_history_page", PlayPrefixHistoryPageToken),
        ("prepare_play_prefix_projection", PreparePlayPrefixProjectionToken),
    ]:
        inputs, outputs, nullable, aware, minimum, maximum = (
            _SYNC_PLAY_PREFIX_FUNCTION_TYPES["sync_right_api." + name]
        )
        result.append(
            FunctionOperationRegistration(
                operation_id="SYNC_PLAY_PREFIX:" + name,
                capability_id="CAP:sync_play_prefix:" + name,
                token_type=token,
                function_id="sync_right_api." + name,
                statement=_build_fixed_function_statement(
                    "sync_right_api", name, inputs, tuple(n for n, _ in outputs), True
                ),
                input_fields=inputs,
                result_fields=outputs,
                decoder=_identity,
                min_rows=minimum,
                max_rows=maximum,
                nullable_results=nullable,
                aware_datetime_results=aware,
            )
        )
    return tuple(result)


PLAY_PREFIX_OPERATIONS = _play_prefix_declarations()
