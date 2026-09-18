"""キャッシュ無効化の純粋な要求生成 API を提供する。

このモジュールは値を検証して組み立てるだけであり、無効化意図の永続化、
配信、再試行、または各操作からの発火を行わない。永続化先の capability が
未確定でも利用できるため、TSK-424 には依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import final
from uuid import UUID

__all__ = (
    "AnalyticsChartCacheKey",
    "AnalyticsChartSubject",
    "CacheInvalidationKey",
    "CacheInvalidationRequest",
    "CacheInvalidationTrigger",
    "CachePeriod",
    "CachePropagationMode",
    "CacheScope",
    "MatchCacheKey",
    "MatchChartSubject",
    "PlayerCareerCacheKey",
    "PlayerChartSubject",
    "SharedAggregateCacheKey",
    "TeamAggregateCacheKey",
    "build_cache_invalidation_request",
)


class CacheInvalidationTrigger(StrEnum):
    """正本 11-2 節の 14 トリガー。"""

    RESTORED_SYNC = "restored_sync"
    PLAY_CORRECTION = "play_correction"
    UNDO = "undo"
    SUBSTITUTION_RECORD_OR_CORRECTION = "substitution_record_or_correction"
    GAME_DELETE_RESTORE_OR_RESUME = "game_delete_restore_or_resume"
    POSTGAME_CORRECTION = "postgame_correction"
    PLAYER_MERGE_OR_SPLIT = "player_merge_or_split"
    SETTING_CHANGE = "setting_change"
    GRANT_FLAG_CHANGE = "grant_flag_change"
    GROUP_DEPARTURE = "group_departure"
    GROUP_END = "group_end"
    TENANT_DISABLE = "tenant_disable"
    TENANT_REENABLE = "tenant_reenable"
    ROSTER_STATUS_CHANGE = "roster_status_change"


class CacheScope(StrEnum):
    """正本 11-2 節の 5 対象範囲。"""

    MATCH = "match"
    PLAYER_CAREER = "player_career"
    TEAM_AGGREGATE = "team_aggregate"
    SHARED_AGGREGATE = "shared_aggregate"
    ANALYTICS_CHART = "analytics_chart"


class CachePropagationMode(StrEnum):
    """波及先の選択規則を値として表す。"""

    BY_SCOPE = "by_scope"
    ALL_TENANTS = "all_tenants"
    BEFORE_AFTER_UNION = "before_after_union"


def _require_uuid(value: UUID, field_name: str) -> None:
    """物理キーの識別子が UUID であることを検査する。"""
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} は UUID が必要")


@final
@dataclass(frozen=True, slots=True)
class CachePeriod:
    """集計期間の開始日・終了日境界を表す不変値。"""

    start: date | None
    end: date | None

    def __post_init__(self) -> None:
        """期間境界の型と順序を検査する。"""
        for field_name, value in (("start", self.start), ("end", self.end)):
            if value is not None and type(value) is not date:
                raise TypeError(f"{field_name} は date または None が必要")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("期間の start は end 以下でなければならない")


@final
@dataclass(frozen=True, slots=True)
class PlayerChartSubject:
    """選手を対象にする分析チャート識別子。"""

    player_id: UUID

    def __post_init__(self) -> None:
        """選手 ID を検査する。"""
        _require_uuid(self.player_id, "player_id")


@final
@dataclass(frozen=True, slots=True)
class MatchChartSubject:
    """試合を対象にする分析チャート識別子。"""

    match_id: UUID

    def __post_init__(self) -> None:
        """試合 ID を検査する。"""
        _require_uuid(self.match_id, "match_id")


type AnalyticsChartSubject = PlayerChartSubject | MatchChartSubject


@final
@dataclass(frozen=True, slots=True)
class MatchCacheKey:
    """試合単位集計の物理キー。"""

    tenant_id: UUID
    match_id: UUID

    def __post_init__(self) -> None:
        """テナントと試合の識別子を検査する。"""
        _require_uuid(self.tenant_id, "tenant_id")
        _require_uuid(self.match_id, "match_id")


@final
@dataclass(frozen=True, slots=True)
class PlayerCareerCacheKey:
    """選手単位通算の物理キー。"""

    tenant_id: UUID
    player_id: UUID
    period: CachePeriod

    def __post_init__(self) -> None:
        """テナント・選手・期間を検査する。"""
        _require_uuid(self.tenant_id, "tenant_id")
        _require_uuid(self.player_id, "player_id")
        if not isinstance(self.period, CachePeriod):
            raise TypeError("period は CachePeriod が必要")


@final
@dataclass(frozen=True, slots=True)
class TeamAggregateCacheKey:
    """チーム単位集計の物理キー。"""

    tenant_id: UUID
    period: CachePeriod

    def __post_init__(self) -> None:
        """テナントと期間を検査する。"""
        _require_uuid(self.tenant_id, "tenant_id")
        if not isinstance(self.period, CachePeriod):
            raise TypeError("period は CachePeriod が必要")


@final
@dataclass(frozen=True, slots=True)
class SharedAggregateCacheKey:
    """要求元ごとの共有集計の物理キー。"""

    group_id: UUID
    requester_tenant_id: UUID
    target_tenant_id: UUID
    period: CachePeriod

    def __post_init__(self) -> None:
        """グループ・要求元・対象・期間を検査する。"""
        _require_uuid(self.group_id, "group_id")
        _require_uuid(self.requester_tenant_id, "requester_tenant_id")
        _require_uuid(self.target_tenant_id, "target_tenant_id")
        if not isinstance(self.period, CachePeriod):
            raise TypeError("period は CachePeriod が必要")


@final
@dataclass(frozen=True, slots=True)
class AnalyticsChartCacheKey:
    """分析チャートの物理キー。"""

    tenant_id: UUID
    subject: AnalyticsChartSubject
    chart_kind: str

    def __post_init__(self) -> None:
        """テナント・対象 ADT・チャート種別を検査する。"""
        _require_uuid(self.tenant_id, "tenant_id")
        if type(self.subject) not in {PlayerChartSubject, MatchChartSubject}:
            raise TypeError("subject は選手または試合の chart subject が必要")
        if not isinstance(self.chart_kind, str) or not self.chart_kind.strip():
            raise ValueError("chart_kind は空でない文字列が必要")


type CacheInvalidationKey = (
    MatchCacheKey
    | PlayerCareerCacheKey
    | TeamAggregateCacheKey
    | SharedAggregateCacheKey
    | AnalyticsChartCacheKey
)


_KEY_SCOPES: dict[type[object], CacheScope] = {
    MatchCacheKey: CacheScope.MATCH,
    PlayerCareerCacheKey: CacheScope.PLAYER_CAREER,
    TeamAggregateCacheKey: CacheScope.TEAM_AGGREGATE,
    SharedAggregateCacheKey: CacheScope.SHARED_AGGREGATE,
    AnalyticsChartCacheKey: CacheScope.ANALYTICS_CHART,
}

_ALL_SCOPES = frozenset(CacheScope)
_TRIGGER_SCOPES: dict[CacheInvalidationTrigger, frozenset[CacheScope]] = {
    **{
        trigger: _ALL_SCOPES
        for trigger in (
            CacheInvalidationTrigger.RESTORED_SYNC,
            CacheInvalidationTrigger.PLAY_CORRECTION,
            CacheInvalidationTrigger.UNDO,
            CacheInvalidationTrigger.SUBSTITUTION_RECORD_OR_CORRECTION,
            CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME,
            CacheInvalidationTrigger.POSTGAME_CORRECTION,
            CacheInvalidationTrigger.PLAYER_MERGE_OR_SPLIT,
        )
    },
    CacheInvalidationTrigger.SETTING_CHANGE: frozenset(
        {
            CacheScope.PLAYER_CAREER,
            CacheScope.TEAM_AGGREGATE,
            CacheScope.SHARED_AGGREGATE,
            CacheScope.ANALYTICS_CHART,
        }
    ),
    **{
        trigger: frozenset({CacheScope.SHARED_AGGREGATE})
        for trigger in (
            CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
            CacheInvalidationTrigger.GROUP_DEPARTURE,
            CacheInvalidationTrigger.GROUP_END,
            CacheInvalidationTrigger.TENANT_DISABLE,
            CacheInvalidationTrigger.TENANT_REENABLE,
            CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
        )
    },
}

_PARTICIPATION_CHANGE_TRIGGERS = frozenset(
    {
        CacheInvalidationTrigger.GROUP_DEPARTURE,
        CacheInvalidationTrigger.GROUP_END,
        CacheInvalidationTrigger.TENANT_DISABLE,
        CacheInvalidationTrigger.TENANT_REENABLE,
    }
)


@final
@dataclass(frozen=True, slots=True, init=False)
class CacheInvalidationRequest:
    """永続化や発火を行わない、検証済みの無効化要求値。"""

    trigger: CacheInvalidationTrigger
    keys: tuple[CacheInvalidationKey, ...]
    propagation_mode: CachePropagationMode
    affected_tenant_ids: frozenset[UUID] | None

    def __new__(cls) -> CacheInvalidationRequest:
        """公開 factory を通らない未検証 DTO の構築を拒否する。"""
        raise TypeError("CacheInvalidationRequest は公開 factory から生成する")

    @classmethod
    def _create(
        cls,
        *,
        trigger: CacheInvalidationTrigger,
        keys: tuple[CacheInvalidationKey, ...],
        propagation_mode: CachePropagationMode,
        affected_tenant_ids: frozenset[UUID] | None,
    ) -> CacheInvalidationRequest:
        """公開 factory が検証した値から DTO を作る。"""
        request = object.__new__(cls)
        object.__setattr__(request, "trigger", trigger)
        object.__setattr__(request, "keys", keys)
        object.__setattr__(request, "propagation_mode", propagation_mode)
        object.__setattr__(request, "affected_tenant_ids", affected_tenant_ids)
        return request


def _validated_participant_union(
    before: frozenset[UUID] | None,
    after: frozenset[UUID] | None,
) -> frozenset[UUID]:
    """参加変更前後の実効参加テナントを和集合に閉じる。"""
    if not isinstance(before, frozenset) or not isinstance(after, frozenset):
        raise TypeError("参加変更トリガーには変更前後の frozenset が必要")
    affected = before | after
    if not affected or any(not isinstance(item, UUID) for item in affected):
        raise ValueError("変更前後の実効参加テナント和集合には UUID が必要")
    return affected


def build_cache_invalidation_request(
    trigger: CacheInvalidationTrigger,
    keys: tuple[CacheInvalidationKey, ...],
    *,
    effective_tenants_before: frozenset[UUID] | None = None,
    effective_tenants_after: frozenset[UUID] | None = None,
) -> CacheInvalidationRequest:
    """正本の matrix と波及規則に適合する無効化要求値を組み立てる。

    この関数は純粋な要求生成器であり、DB・キャッシュ・outbox へ書かず、
    発火もしない。永続化と配信完了までの再試行は契約資産が規定し、
    実装は後続の所有単位が受け取る。

    Args:
        trigger: 正本に列挙された変更トリガー。
        keys: 5 種 ADT のいずれかで表した物理キー。トリガーが要求する
            対象範囲を過不足なく含める。
        effective_tenants_before: 参加変更前の実効参加テナント集合。
        effective_tenants_after: 参加変更後の実効参加テナント集合。

    Returns:
        検証済みの immutable な無効化要求。

    Raises:
        TypeError: trigger・keys・参加集合の型が契約外の場合。
        ValueError: 対象範囲の過不足、重複、または波及規則違反の場合。
    """
    if not isinstance(trigger, CacheInvalidationTrigger):
        raise TypeError("trigger は CacheInvalidationTrigger が必要")
    if not isinstance(keys, tuple):
        raise TypeError("keys は tuple が必要")
    if not keys:
        raise ValueError("トリガーの対象範囲が matrix と不一致: keys が空")
    if len(keys) != len(set(keys)):
        raise ValueError("物理キーを重複させてはならない")
    try:
        scopes = frozenset(_KEY_SCOPES[type(key)] for key in keys)
    except KeyError as error:
        raise TypeError("keys に契約外の物理キー型が含まれる") from error
    expected_scopes = _TRIGGER_SCOPES[trigger]
    if scopes != expected_scopes:
        raise ValueError(
            "トリガーの対象範囲が matrix と不一致: "
            f"expected={sorted(expected_scopes)}, actual={sorted(scopes)}"
        )

    if trigger in _PARTICIPATION_CHANGE_TRIGGERS:
        affected_tenant_ids = _validated_participant_union(
            effective_tenants_before,
            effective_tenants_after,
        )
        shared_keys = (
            key for key in keys if isinstance(key, SharedAggregateCacheKey)
        )
        if any(
            key.requester_tenant_id not in affected_tenant_ids
            or key.target_tenant_id not in affected_tenant_ids
            for key in shared_keys
        ):
            raise ValueError("共有キーの要求元・対象は参加変更前後の和集合が必要")
        propagation_mode = CachePropagationMode.BEFORE_AFTER_UNION
    else:
        if (
            effective_tenants_before is not None
            or effective_tenants_after is not None
        ):
            raise ValueError("参加変更以外へ変更前後の参加集合を渡してはならない")
        affected_tenant_ids = None
        propagation_mode = (
            CachePropagationMode.ALL_TENANTS
            if trigger is CacheInvalidationTrigger.SETTING_CHANGE
            else CachePropagationMode.BY_SCOPE
        )

    return CacheInvalidationRequest._create(
        trigger=trigger,
        keys=keys,
        propagation_mode=propagation_mode,
        affected_tenant_ids=affected_tenant_ids,
    )
