"""正本 11-2 節とキャッシュ無効化要求 API の契約を検査する。"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any, cast, get_type_hints
from uuid import UUID

import pytest

from pitchlog.repositories import cache_invalidation
from pitchlog.repositories.cache_invalidation import (
    AnalyticsChartCacheKey,
    AnalyticsChartSubject,
    CacheInvalidationKey,
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CachePeriod,
    CachePropagationMode,
    CacheScope,
    MatchCacheKey,
    MatchChartSubject,
    PlayerCareerCacheKey,
    PlayerChartSubject,
    SharedAggregateCacheKey,
    TeamAggregateCacheKey,
    build_cache_invalidation_request,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ASSET_PATH = Path("contracts/tenant_boundary/cache-invalidation-contract.json")
_SOURCE_PATH = Path("docs/design/data-model.md")
_MODULE_PATH = Path("backend/src/pitchlog/repositories/cache_invalidation.py")
_TENANT_A = UUID("00000000-0000-0000-0000-000000001001")
_TENANT_B = UUID("00000000-0000-0000-0000-000000001002")
_TENANT_C = UUID("00000000-0000-0000-0000-000000001003")
_GROUP_ID = UUID("00000000-0000-0000-0000-000000001004")
_MATCH_ID = UUID("00000000-0000-0000-0000-000000001005")
_PLAYER_ID = UUID("00000000-0000-0000-0000-000000001006")


def _read_asset() -> dict[str, Any]:
    """キャッシュ無効化契約資産を読む。"""
    value = json.loads((_REPOSITORY_ROOT / _ASSET_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("キャッシュ無効化契約が JSON object でない")
    return value


def _asset_digest(asset: dict[str, Any]) -> str:
    """source_digest を除く正規化 digest を計算する。"""
    payload = dict(asset)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _source_section() -> str:
    """正本 11-2 節を次節の直前まで切り出す。"""
    document = (_REPOSITORY_ROOT / _SOURCE_PATH).read_text(encoding="utf-8")
    start_marker = "### 11-2. キャッシュ無効化契約"
    end_marker = "### 11-3. 索引設計の原則"
    start = document.index(start_marker)
    end = document.index(end_marker, start)
    return document[start:end]


def _plain_markdown(value: str) -> str:
    """表セルの強調・code span・注記を比較用に正規化する。"""
    return value.replace("**", "").replace("`", "").strip()


def _table_rows_after(section: str, header: str) -> list[list[str]]:
    """指定ヘッダに続く Markdown 表のデータ行を返す。"""
    lines = section.splitlines()
    header_index = lines.index(header)
    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def _source_matrix() -> tuple[tuple[str, ...], set[tuple[int, str, str]]]:
    """正本表から列見出しと ● セル集合を抽出する。"""
    section = _source_section()
    header = "| # | トリガー | ① 試合 | ② 選手通算 | ③ チーム | ④ 共有 | ⑤ チャート |"
    rows = _table_rows_after(section, header)
    scope_columns = (
        "① 試合",
        "② 選手通算",
        "③ チーム",
        "④ 共有",
        "⑤ チャート",
    )
    enabled: set[tuple[int, str, str]] = set()
    for row in rows:
        ordinal = int(row[0])
        trigger_label = _plain_markdown(row[1])
        for scope_column, cell in zip(scope_columns, row[2:], strict=True):
            if _plain_markdown(cell).startswith("●"):
                enabled.add((ordinal, trigger_label, scope_column))
    return scope_columns, enabled


def _asset_matrix(asset: dict[str, Any]) -> set[tuple[int, str, str]]:
    """資産の trigger×scope を正本表と同じ組へ変換する。"""
    scope_columns = {scope["id"]: scope["source_column"] for scope in asset["scopes"]}
    return {
        (trigger["ordinal"], trigger["source_label"], scope_columns[scope_id])
        for trigger in asset["triggers"]
        for scope_id in trigger["scope_ids"]
    }


def _key_by_scope() -> dict[CacheScope, CacheInvalidationKey]:
    """5 対象範囲それぞれのテスト用物理キーを返す。"""
    period = CachePeriod(date(2026, 4, 1), date(2027, 3, 31))
    return {
        CacheScope.MATCH: MatchCacheKey(_TENANT_A, _MATCH_ID),
        CacheScope.PLAYER_CAREER: PlayerCareerCacheKey(
            _TENANT_A,
            _PLAYER_ID,
            period,
        ),
        CacheScope.TEAM_AGGREGATE: TeamAggregateCacheKey(_TENANT_A, period),
        CacheScope.SHARED_AGGREGATE: SharedAggregateCacheKey(
            _GROUP_ID,
            _TENANT_A,
            _TENANT_B,
            period,
        ),
        CacheScope.ANALYTICS_CHART: AnalyticsChartCacheKey(
            _TENANT_A,
            PlayerChartSubject(_PLAYER_ID),
            "pitch_velocity",
        ),
    }


def _keys_for(
    trigger: CacheInvalidationTrigger,
) -> tuple[CacheInvalidationKey, ...]:
    """実装 matrix が要求する scope の物理キーを返す。"""
    key_by_scope = _key_by_scope()
    return tuple(
        key_by_scope[scope]
        for scope in CacheScope
        if scope in cache_invalidation._TRIGGER_SCOPES[trigger]
    )


def test_asset_digest_and_api_mode_are_exact() -> None:
    """資産の完全性と純粋要求生成器の採用を固定する。"""
    asset = _read_asset()

    assert asset["source_digest"] == _asset_digest(asset)
    assert asset["source"] == {
        "document": "docs/design/data-model.md",
        "section": "11-2",
        "requirements_section": "6.2",
    }
    assert asset["api"]["kind"] == "pure_request_factory"
    assert asset["api"]["owns_trigger_emission"] is False
    assert asset["api"]["writes_persistent_intents"] is False
    assert asset["api"]["tsk_424_capability_dependency"] is False
    assert asset["trigger_emission"]["owned_by_this_unit"] is False
    assert asset["preaggregation_independent"] is True


def test_source_matrix_and_asset_are_bidirectionally_exact() -> None:
    """正本の 14×5 と ● 45 セルを資産へ両方向 exact-set 結合する。"""
    asset = _read_asset()
    source_columns, source_cells = _source_matrix()

    assert len(asset["triggers"]) == 14
    assert len(asset["scopes"]) == 5
    assert tuple(scope["source_column"] for scope in asset["scopes"]) == (
        source_columns
    )
    assert len(source_cells) == 45
    assert _asset_matrix(asset) == source_cells


def test_each_matrix_cell_removal_or_addition_is_red() -> None:
    """● の欠落と — セルの追加を exact-set 比較が検出する。"""
    asset = _read_asset()
    _, source_cells = _source_matrix()
    asset_cells = _asset_matrix(asset)
    missing_mutant = set(asset_cells)
    missing_mutant.remove(next(iter(missing_mutant)))
    disabled_cells = {
        (trigger["ordinal"], trigger["source_label"], scope["source_column"])
        for trigger in asset["triggers"]
        for scope in asset["scopes"]
    } - asset_cells
    extra_mutant = set(asset_cells)
    extra_mutant.add(next(iter(disabled_cells)))

    assert missing_mutant != source_cells
    assert extra_mutant != source_cells


def test_invitation_revocation_is_explicitly_excluded() -> None:
    """招待の失効が trigger 集合へ混入しないことを固定する。"""
    asset = _read_asset()
    section = _source_section()

    assert "招待の失効は含めない" in _plain_markdown(section)
    assert asset["excluded_triggers"] == [
        {
            "id": "invitation_revocation",
            "source_label": "招待の失効",
            "reason": "権限の撤回ではないため",
        }
    ]
    assert "invitation_revocation" not in {
        trigger["id"] for trigger in asset["triggers"]
    }
    with pytest.raises(ValueError):
        CacheInvalidationTrigger("invitation_revocation")


def test_propagation_rules_are_exact_and_source_backed() -> None:
    """所有・共有・全テナント・参加前後和集合の波及規則を固定する。"""
    asset = _read_asset()
    propagation = asset["propagation"]
    section = _plain_markdown(_source_section())

    assert propagation["definition_authority"] == {
        "source": "docs/design/data-model.md#11-2",
        "exclusive": True,
    }
    assert propagation["scope_rules"] == {
        "owner_tenant": {
            "scope_ids": [
                "match",
                "player_career",
                "team_aggregate",
                "analytics_chart",
            ],
            "selector": "data_owner_tenant",
            "requires_effective_participation": False,
        },
        "group_effective_participants": {
            "scope_ids": ["shared_aggregate"],
            "selector": "group_effective_participant_tenants",
        },
    }
    assert propagation["system_non_tenant_changes"] == {
        "change_kinds": ["system_setting", "system_fixed_vocabulary"],
        "actor": "system_administrator",
        "has_self_tenant": False,
        "selector": "all_tenants_holding_aggregates_with_that_input",
        "default": "all_tenants",
        "narrowing_predicate": None,
        "requires_effective_participation": False,
    }
    assert propagation["participation_state_changes"] == {
        "trigger_ids": [
            "group_departure",
            "group_end",
            "tenant_disable",
            "tenant_reenable",
        ],
        "selector": "union_of_effective_participants_before_and_after",
        "post_state_only": False,
    }
    for source_phrase in (
        "本書の定義はここだけ",
        "そのデータを所有するテナント",
        "当該グループの実効参加テナント",
        "「自テナント」が存在しない",
        "システム管理者の操作",
        "本書は「全テナント」を既定とする",
        "操作の前後どちらかで実効参加だったテナントの和集合",
    ):
        assert source_phrase in section


def test_five_physical_key_adt_variants_match_source_and_runtime() -> None:
    """5 種の物理キー形を正本・資産・frozen dataclass で一致させる。"""
    asset = _read_asset()
    variants = asset["physical_key_adt"]["variants"]
    section = _source_section()
    physical_rows = _table_rows_after(
        section,
        "| 対象範囲 | 物理的な無効化先 | 単位 |",
    )
    source_units = {_plain_markdown(row[2]).split(" — ", 1)[0] for row in physical_rows}
    expected_types = {
        "match": MatchCacheKey,
        "player_career": PlayerCareerCacheKey,
        "team_aggregate": TeamAggregateCacheKey,
        "shared_aggregate": SharedAggregateCacheKey,
        "analytics_chart": AnalyticsChartCacheKey,
    }

    assert asset["physical_key_adt"]["discriminator"] == "kind"
    assert asset["physical_key_adt"]["tenant_or_group_prefix_required"] is True
    assert asset["physical_key_adt"]["cross_tenant_key_deletion_path_allowed"] is False
    assert len(variants) == 5
    assert {variant["source_unit"] for variant in variants} == source_units
    for variant in variants:
        runtime_type = expected_types[variant["kind"]]
        assert variant["python_type"] == (
            f"{runtime_type.__module__}.{runtime_type.__qualname__}"
        )
        assert [field.name for field in fields(runtime_type)] == [
            field_name for field_name, _ in variant["fields"]
        ]
        assert runtime_type.__dataclass_params__.frozen is True


def test_durable_intent_persistence_and_retry_contract_is_exact() -> None:
    """永続化・一意性・未配信検索・冪等再試行・非物理削除を固定する。"""
    asset = _read_asset()

    assert asset["durable_intent"] == {
        "required": True,
        "storage_kind": "cache_invalidation_intent_table",
        "rows_per_trigger": 1,
        "same_transaction_with": "T7",
        "uniqueness_fields": ["tenant_id", "intent_id"],
        "intent_id_derivation": [
            "target_event_v10",
            "target_confirmed_version",
        ],
        "delivery_states": ["pending", "completed"],
        "retry": "idempotent_until_completed",
        "saved_result_replay_creates_duplicate": False,
        "pending_lookup_fields": ["tenant_id", "delivery_state"],
        "physical_delete": False,
        "restoration_coordination": {
            "delivery_may_be_deferred": True,
            "intent_persistence_may_be_deferred": False,
        },
    }
    section = _plain_markdown(_source_section())
    for source_phrase in (
        "T7 と同一トランザクション",
        "UNIQUE (tenant_id, 意図 ID)",
        "配信完了まで冪等に再試行",
        "(tenant_id, 配信状態) で未配信だけを引ける",
        "物理削除しない",
    ):
        assert source_phrase in section


def test_public_symbols_and_factory_signature_are_exact() -> None:
    """公開シンボルを資産と __all__ の両方で exact-set にする。"""
    asset = _read_asset()
    expected_names = (
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
    expected_symbols = {
        f"{cache_invalidation.__name__}.{name}" for name in expected_names
    }
    signature = inspect.signature(build_cache_invalidation_request)
    hints = get_type_hints(build_cache_invalidation_request)

    assert cache_invalidation.__all__ == expected_names
    assert set(asset["api"]["public_symbols"]) == expected_symbols
    assert tuple(signature.parameters) == (
        "trigger",
        "keys",
        "effective_tenants_before",
        "effective_tenants_after",
    )
    assert signature.parameters["effective_tenants_before"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert signature.parameters["effective_tenants_after"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert signature.parameters["effective_tenants_before"].default is None
    assert signature.parameters["effective_tenants_after"].default is None
    assert hints == {
        "trigger": CacheInvalidationTrigger,
        "keys": tuple[cache_invalidation.CacheInvalidationKey, ...],
        "effective_tenants_before": frozenset[UUID] | None,
        "effective_tenants_after": frozenset[UUID] | None,
        "return": CacheInvalidationRequest,
    }
    with pytest.raises(TypeError, match="公開 factory"):
        CacheInvalidationRequest()


def test_factory_is_pure_and_has_no_persistence_or_trigger_dependencies() -> None:
    """製品 API が値生成だけで DB・キャッシュ・発火実装を持たない。"""
    source = (_REPOSITORY_ROOT / _MODULE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_roots.isdisjoint({"sqlalchemy", "psycopg", "redis"})
    assert "純粋な要求生成器" in (
        inspect.getdoc(build_cache_invalidation_request) or ""
    )


def test_runtime_matrix_matches_asset_and_each_missing_scope_is_red() -> None:
    """実行時 matrix の一致と全 trigger の scope 欠落拒否を確認する。"""
    asset = _read_asset()
    asset_scopes = {
        CacheInvalidationTrigger(trigger["id"]): frozenset(
            CacheScope(scope_id) for scope_id in trigger["scope_ids"]
        )
        for trigger in asset["triggers"]
    }

    assert cache_invalidation._TRIGGER_SCOPES == asset_scopes
    for trigger, expected_scopes in asset_scopes.items():
        keys = _keys_for(trigger)
        if trigger in cache_invalidation._PARTICIPATION_CHANGE_TRIGGERS:
            request = build_cache_invalidation_request(
                trigger,
                keys,
                effective_tenants_before=frozenset({_TENANT_A, _TENANT_B}),
                effective_tenants_after=frozenset({_TENANT_A, _TENANT_B}),
            )
        else:
            request = build_cache_invalidation_request(trigger, keys)
        assert request.trigger is trigger
        assert {
            cache_invalidation._KEY_SCOPES[type(key)] for key in request.keys
        } == expected_scopes

        with pytest.raises(ValueError, match="matrix と不一致"):
            if trigger in cache_invalidation._PARTICIPATION_CHANGE_TRIGGERS:
                build_cache_invalidation_request(
                    trigger,
                    keys[:-1],
                    effective_tenants_before=frozenset({_TENANT_A, _TENANT_B}),
                    effective_tenants_after=frozenset({_TENANT_A, _TENANT_B}),
                )
            else:
                build_cache_invalidation_request(trigger, keys[:-1])


def test_system_change_is_fail_closed_all_tenants() -> None:
    """設定値変更を絞り込み述語なしの全テナント波及として生成する。"""
    request = build_cache_invalidation_request(
        CacheInvalidationTrigger.SETTING_CHANGE,
        _keys_for(CacheInvalidationTrigger.SETTING_CHANGE),
    )

    assert request.propagation_mode is CachePropagationMode.ALL_TENANTS
    assert request.affected_tenant_ids is None


def test_participation_change_uses_before_after_union() -> None:
    """操作後だけでなく変更前後どちらかの実効参加テナントを残す。"""
    key = SharedAggregateCacheKey(
        _GROUP_ID,
        _TENANT_A,
        _TENANT_C,
        CachePeriod(None, None),
    )
    request = build_cache_invalidation_request(
        CacheInvalidationTrigger.GROUP_DEPARTURE,
        (key,),
        effective_tenants_before=frozenset({_TENANT_A, _TENANT_B}),
        effective_tenants_after=frozenset({_TENANT_B, _TENANT_C}),
    )

    assert request.propagation_mode is CachePropagationMode.BEFORE_AFTER_UNION
    assert request.affected_tenant_ids == frozenset({_TENANT_A, _TENANT_B, _TENANT_C})
    with pytest.raises(ValueError, match="前後の和集合"):
        build_cache_invalidation_request(
            CacheInvalidationTrigger.GROUP_DEPARTURE,
            (key,),
            effective_tenants_before=frozenset({_TENANT_B}),
            effective_tenants_after=frozenset({_TENANT_B, _TENANT_C}),
        )


def test_keys_and_requests_are_immutable_values() -> None:
    """物理キーと要求 DTO が完全実体化済みの frozen 値である。"""
    request = build_cache_invalidation_request(
        CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
        _keys_for(CacheInvalidationTrigger.GRANT_FLAG_CHANGE),
    )

    assert isinstance(request.keys, tuple)
    assert CacheInvalidationRequest.__dataclass_params__.frozen is True
    with pytest.raises(AttributeError):
        setattr(request, "keys", ())


def test_chart_subject_is_a_closed_player_or_match_adt() -> None:
    """チャート物理キーの対象が選手または試合の二択である。"""
    player_key = AnalyticsChartCacheKey(
        _TENANT_A,
        PlayerChartSubject(_PLAYER_ID),
        "batting_map",
    )
    match_key = AnalyticsChartCacheKey(
        _TENANT_A,
        MatchChartSubject(_MATCH_ID),
        "pitch_location",
    )

    assert isinstance(player_key.subject, PlayerChartSubject)
    assert isinstance(match_key.subject, MatchChartSubject)
    with pytest.raises(TypeError, match="chart subject"):
        AnalyticsChartCacheKey(
            _TENANT_A,
            cast(AnalyticsChartSubject, object()),
            "invalid",
        )
