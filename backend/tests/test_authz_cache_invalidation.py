"""正本 11-2 節とキャッシュ無効化要求 API の契約を検査する。"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
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
    SharedAggregateTargetSelector,
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


def _source_ordinals(label: str) -> set[int]:
    """正本表の先頭にある番号列と連続範囲を展開する。"""
    match = re.match(r"[0-9]+(?:[・〜][0-9]+)*", _plain_markdown(label))
    assert match is not None
    ordinals: set[int] = set()
    for part in match.group().split("・"):
        if "〜" in part:
            start, end = (int(value) for value in part.split("〜"))
            assert start <= end
            ordinals.update(range(start, end + 1))
        else:
            ordinals.add(int(part))
    return ordinals


def _assert_b06_source_matches_contract(section: str, asset: dict[str, Any]) -> None:
    """B06 の適用範囲・帰属・行規則を契約と双方向に照合する。"""
    b06 = section[section.index("#### 同期を通らないトリガーの発火・原子性・意図 ID") :]
    non_sync = asset["durable_intent"]["non_sync_triggers"]
    ordinal_by_id = {trigger["id"]: trigger["ordinal"] for trigger in asset["triggers"]}
    contract_ordinals = {ordinal_by_id[item] for item in non_sync["trigger_ids"]}
    scope_lines = [
        line
        for line in b06.splitlines()
        if _plain_markdown(line).startswith("適用範囲:")
    ]
    assert len(scope_lines) == 1
    source_scope = _plain_markdown(scope_lines[0]).split("上表のトリガー ", 1)[1]
    assert _source_ordinals(source_scope) == contract_ordinals

    attribution_rows = _table_rows_after(b06, "| トリガー | 帰属 |")
    normalized_attribution = tuple(
        tuple(_plain_markdown(cell) for cell in row) for row in attribution_rows
    )
    assert normalized_attribution == (
        (
            "5・7・9・14(自テナントの状態変更)",
            "状態を変えたテナント(tenant_id = そのテナント)。波及先は上記"
            "「無効化の波及先」の範囲ごとの規則に従う",
        ),
        (
            "8・10〜13",
            "本版では定めない。8 は自テナントが無く全テナントへ、10〜13 は操作前後の"
            "実効参加の和集合へ波及するので、状態を変えたテナントの 1 行では表せない。"
            "所有単位が発火点を作るときに本節へ足す(8・12・13 = U-A2、"
            "10・11 = U-C1)。上の共通の 3 規則はこれらにも掛かる",
        ),
    )
    source_attribution = {
        "self_tenant": _source_ordinals(normalized_attribution[0][0]),
        "defined_by_owner_unit": _source_ordinals(normalized_attribution[1][0]),
    }
    assert source_attribution["self_tenant"].isdisjoint(
        source_attribution["defined_by_owner_unit"]
    )
    assert set().union(*source_attribution.values()) == contract_ordinals
    assert set(non_sync["attribution"]) == set(source_attribution)
    for kind, source_ordinals in source_attribution.items():
        assert {ordinal_by_id[item] for item in non_sync["attribution"][kind]} == (
            source_ordinals
        )

    row_rule_rows = _table_rows_after(b06, "| トリガー | 行の数 | 行の識別子 | 鍵 |")
    normalized_row_rules = tuple(
        tuple(_plain_markdown(cell) for cell in row) for row in row_rule_rows
    )
    assert normalized_row_rules == (
        (
            "14(選手の在籍区分の変更)",
            "1 操作につき 1 件(一括変更でも 1 件)",
            "④ 共有集計",
            "④ の対象テナント単位の選択子(下)。対象テナント = 状態を変えたテナント",
        ),
        ("5・7〜13", "本版では定めない — 所有単位が足す", "同左", "同左"),
    )
    defined_ordinals = _source_ordinals(normalized_row_rules[0][0])
    owner_ordinals = _source_ordinals(normalized_row_rules[1][0])
    assert defined_ordinals.isdisjoint(owner_ordinals)
    assert defined_ordinals | owner_ordinals == contract_ordinals
    assert {ordinal_by_id[item] for item in non_sync["row_rules"]} == defined_ordinals
    assert non_sync["row_rules_for_other_triggers"] == "defined_by_owner_unit"
    assert owner_ordinals == contract_ordinals - defined_ordinals
    for rule in non_sync["row_rules"].values():
        assert rule["rows_per_operation"] == 1
        assert rule["selector_kind"] == "shared_aggregate_target_selector"
        assert rule["row_discriminator"] == "scope_id"
        assert rule["row_discriminator_value"] == "shared_aggregate"


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
    """実装 matrix が要求する scope の鍵を返す。"""
    if trigger is CacheInvalidationTrigger.ROSTER_STATUS_CHANGE:
        return (SharedAggregateTargetSelector(_TENANT_A),)
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
        "applies_to_trigger_ids": [
            "restored_sync",
            "play_correction",
            "undo",
            "substitution_record_or_correction",
            "postgame_correction",
        ],
        "non_sync_triggers": {
            "trigger_ids": [
                "game_delete_restore_or_resume",
                "player_merge_or_split",
                "setting_change",
                "grant_flag_change",
                "group_departure",
                "group_end",
                "tenant_disable",
                "tenant_reenable",
                "roster_status_change",
            ],
            "firing": "committed_state_change_with_value_change",
            "same_transaction_with": "triggering_state_change",
            "intent_id_derivation": [
                "trigger_id",
                "operation_id",
                "row_discriminator",
            ],
            "row_rules": {
                "roster_status_change": {
                    "rows_per_operation": 1,
                    "selector_kind": "shared_aggregate_target_selector",
                    "row_discriminator": "scope_id",
                    "row_discriminator_value": "shared_aggregate",
                }
            },
            "row_rules_for_other_triggers": "defined_by_owner_unit",
            "attribution": {
                "self_tenant": [
                    "game_delete_restore_or_resume",
                    "player_merge_or_split",
                    "grant_flag_change",
                    "roster_status_change",
                ],
                "defined_by_owner_unit": [
                    "setting_change",
                    "group_departure",
                    "group_end",
                    "tenant_disable",
                    "tenant_reenable",
                ],
            },
            "selectors": [
                {
                    "kind": "shared_aggregate_target_selector",
                    "scope_id": "shared_aggregate",
                    "python_type": (
                        "pitchlog.repositories.cache_invalidation."
                        "SharedAggregateTargetSelector"
                    ),
                    "fields": [["tenant_id", "uuid.UUID"]],
                    "source_unit": "(対象テナント)",
                    "matches": "physical_key_adt.shared_aggregate.target_tenant_id",
                }
            ],
            "delivery_owner": "unit_that_introduces_the_scope_cache",
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


def test_durable_intent_trigger_partition_and_b06_source_are_exact() -> None:
    """同期と非同期の適用範囲を分割し、B06 の選択子と原子性を照合する。"""
    asset = _read_asset()
    durable = asset["durable_intent"]
    non_sync = durable["non_sync_triggers"]
    sync_ids = set(durable["applies_to_trigger_ids"])
    non_sync_ids = set(non_sync["trigger_ids"])
    trigger_ids = {trigger["id"] for trigger in asset["triggers"]}

    assert len(sync_ids) == len(durable["applies_to_trigger_ids"]) == 5
    assert len(non_sync_ids) == len(non_sync["trigger_ids"]) == 9
    assert sync_ids.isdisjoint(non_sync_ids)
    assert sync_ids | non_sync_ids == trigger_ids
    _assert_b06_source_matches_contract(_source_section(), asset)

    section = _plain_markdown(_source_section())
    b06 = section[section.index("#### 同期を通らないトリガーの発火・原子性・意図 ID") :]
    selector_rows = _table_rows_after(
        _source_section(), "| 対象範囲 | 意図が選ぶ無効化先 | 選択子 |"
    )
    assert len(selector_rows) == 1
    assert [selector["source_unit"] for selector in non_sync["selectors"]] == [
        _plain_markdown(row[2]) for row in selector_rows
    ]
    for selector in non_sync["selectors"]:
        assert selector["python_type"] == (
            f"{SharedAggregateTargetSelector.__module__}."
            f"{SharedAggregateTargetSelector.__qualname__}"
        )
        assert [field.name for field in fields(SharedAggregateTargetSelector)] == [
            field_name for field_name, _ in selector["fields"]
        ]
    assert SharedAggregateTargetSelector.__dataclass_params__.frozen is True
    for source_phrase in (
        "5・7・8・9・10・11・12・13・14",
        "値が実際に変わらない要求は発火しない",
        "その状態変更と同一の DB トランザクションで意図を書く",
        "<トリガー>:<操作 ID>:<行の識別子>",
        "1 操作につき 1 件",
        "④ の対象テナント単位の選択子",
        "対象テナント成分が一致するものすべて",
        "その対象範囲のキャッシュ本体を初めて導入する単位が配信を作る",
    ):
        assert source_phrase in b06


def test_b06_attribution_table_movement_is_red() -> None:
    """正本の帰属表を 1 行変えただけでも契約照合が失敗する。"""
    section = _source_section()
    for before, after in (
        ("**5・7・9・14**", "**5・7・9**"),
        ("**8・10〜13**", "**8・10〜14**"),
    ):
        mutant = section.replace(before, after, 1)
        assert mutant != section
        with pytest.raises(AssertionError):
            _assert_b06_source_matches_contract(mutant, _read_asset())


def test_b06_table_cell_addition_is_red() -> None:
    """帰属と鍵のセルへ他テナント許可を足すと全文照合が失敗する。"""
    section = _source_section()
    for cell in (
        "**状態を変えたテナント**(`tenant_id` = そのテナント)。波及先は上記"
        "「無効化の波及先」の範囲ごとの規則に従う",
        "**④ の対象テナント単位の選択子**(下)。対象テナント = 状態を変えたテナント",
    ):
        assert section.count(cell) == 1
        mutant = section.replace(cell, cell + "。指定した他テナントも可", 1)
        with pytest.raises(AssertionError):
            _assert_b06_source_matches_contract(mutant, _read_asset())


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
        "SharedAggregateTargetSelector",
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
    assert set(asset["api"]["condition4_allowed_call_symbols"]) == {
        f"{cache_invalidation.__name__}.{name}"
        for name in (
            "AnalyticsChartCacheKey",
            "CachePeriod",
            "MatchCacheKey",
            "MatchChartSubject",
            "PlayerCareerCacheKey",
            "PlayerChartSubject",
            "SharedAggregateCacheKey",
            "SharedAggregateTargetSelector",
            "TeamAggregateCacheKey",
            "build_cache_invalidation_request",
        )
    }
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


def test_shared_aggregate_target_selector_is_only_accepted_for_roster_status() -> None:
    """④ の選択子はトリガー 14 のみが受け、他の 13 件を拒否する。"""
    selector = SharedAggregateTargetSelector(_TENANT_A)
    with pytest.raises(TypeError, match="UUID"):
        SharedAggregateTargetSelector(cast(UUID, "not-a-uuid"))

    request = build_cache_invalidation_request(
        CacheInvalidationTrigger.ROSTER_STATUS_CHANGE, (selector,)
    )
    assert request.keys == (selector,)
    assert request.propagation_mode is CachePropagationMode.BY_SCOPE

    for trigger in CacheInvalidationTrigger:
        if trigger is CacheInvalidationTrigger.ROSTER_STATUS_CHANGE:
            continue
        keys = tuple(
            selector if isinstance(key, SharedAggregateCacheKey) else key
            for key in _keys_for(trigger)
        )
        if all(key is not selector for key in keys):
            keys += (selector,)
        with pytest.raises(ValueError, match="選択子"):
            build_cache_invalidation_request(trigger, keys)


def test_roster_status_requires_exactly_one_target_selector() -> None:
    """在籍区分変更で物理キー・混在・複数の対象テナントを拒否する。"""
    physical_key = _key_by_scope()[CacheScope.SHARED_AGGREGATE]
    selector_a = SharedAggregateTargetSelector(_TENANT_A)
    selector_b = SharedAggregateTargetSelector(_TENANT_B)
    for keys in (
        (physical_key,),
        (selector_a, physical_key),
        (selector_a, selector_b),
    ):
        with pytest.raises(ValueError, match="ちょうど 1 件"):
            build_cache_invalidation_request(
                CacheInvalidationTrigger.ROSTER_STATUS_CHANGE, keys
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
