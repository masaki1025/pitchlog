"""NFR-019(d) の故障系資産の契約検査と結果検査(正本 SP 10-3 v0.8)。

資産の形と母集合を検査する契約検査と、runner の実行結果を資産の期待結果と
比べる結果検査を、別の検査として持つ(同じ検査器で兼ねない — SP 10-3)。
経路と T 要素の対応は設計関係データ ``R-TXN-ROUTE`` から読み、二重に定義しない。
サーバー側の runner(ステップ 19)はこのモジュールの検査器を読み込んで使う。
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_RELATIONS_PATH = (
    _REPOSITORY_ROOT / "scripts" / "design_relations" / "sync-protocol.json"
)

SCHEMA_VERSION = 2

type ApplicationPath = Literal["P1", "P2", "P3", "P4", "P5"]
APPLICATION_PATHS: tuple[ApplicationPath, ...] = ("P1", "P2", "P3", "P4", "P5")

ROOT_FIELD_IDS = (
    "schemaVersion",
    "scenarioId",
    "version",
    "input",
    "cases",
    "comparisonUnit",
)
INPUT_FIELD_IDS = (
    "initialPersistence",
    "queue",
    "d1",
    "d3",
    "d4",
    "d5",
    "currentRecoveryGeneration",
    "requestRecoveryGeneration",
    "applicationPath",
    "tabs",
    "lock",
    "p5Branch",
)
CASE_FIELD_IDS = ("caseId", "faultInjection", "observations")
FAULT_INJECTION_FIELD_IDS = (
    "target",
    "injectionPoint",
    "stopOperation",
    "restartOperation",
    "expectedReachability",
)
OBSERVATION_FIELD_IDS = ("observationPoint", "fields")
COMPARISON_UNIT_FIELD_IDS = (
    "scenarioId",
    "caseId",
    "injectionTarget",
    "observationPoint",
    "expectedField",
)
RESULT_FIELD_IDS = ("scenarioId", "cases")
RESULT_CASE_FIELD_IDS = ("caseId", "hookCalls", "observations")

# 共通の期待フィールド(SP 10-3「共通の期待フィールド」)。集合は経路で変えない。
COMMON_EXPECTED_FIELD_IDS = (
    "queue",
    "d1",
    "lock",
    "acceptanceDisplay",
    "reinputAvailability",
    "prefix",
    "idempotentResult",
    "temporaryIdMapping",
    "recordingRight",
    "tElementCommitment",
)
# P1・P2 に加わる期待フィールド(SP 10-3「契約」— v0.6)。
D1_PATH_EXTRA_FIELD_IDS = (
    "invalidationIntentIds",
    "invalidationIntentRows",
    "intentCountsAfterReplay",
    "intentCountsAfterFullDuplicate",
)
_I6_FIELD_IDS = (
    "i6TargetReference",
    "i6Version",
    "i6D5",
    "i6ConfirmedContent",
    "i6RetentionDeadline",
    "i6EscrowState",
)
# P3 に加わる期待フィールド 13 件(SP 10-3「契約」)。
P3_EXTRA_FIELD_IDS = (
    "recoveryGenerationCheck",
    "invalidationIntentIds",
    "invalidationIntentRows",
    "deliveryState",
    "consumerReflectionState",
    "deliveryCompletionRecord",
    "intentCountsAfterReplay",
    *_I6_FIELD_IDS,
)
_EXTRA_FIELD_IDS: Mapping[ApplicationPath | None, tuple[str, ...]] = {
    None: (),
    "P1": D1_PATH_EXTRA_FIELD_IDS,
    "P2": D1_PATH_EXTRA_FIELD_IDS,
    "P3": P3_EXTRA_FIELD_IDS,
    "P4": (),
    "P5": (),
}
_REPLAY_COUNT_FIELD_IDS = ("intentCountsAfterReplay", "intentCountsAfterFullDuplicate")
# 再掲の前の観測点では省けるが、資産のどこかの観測点で実値を持たなければならない。
REQUIRED_SOMEWHERE_FIELD_IDS: Mapping[ApplicationPath | None, tuple[str, ...]] = {
    None: (),
    "P1": _REPLAY_COUNT_FIELD_IDS,
    "P2": _REPLAY_COUNT_FIELD_IDS,
    "P3": ("intentCountsAfterReplay",),
    "P4": (),
    "P5": (),
}
_CLIENT_SIDE_FIELD_IDS = ("queue", "lock", "acceptanceDisplay", "reinputAvailability")
# 省略理由を書ける期待フィールド(省略可否だけを経路で条件付きにする — SP 10-3)。
# サーバー経路の資産で端末側の 4 項目を省けるのは、サーバー側 runner が端末を
# 観測しないため。tElementCommitment・idempotentResult・recordingRight は
# サーバー経路では省けない。
OMITTABLE_FIELD_IDS: Mapping[ApplicationPath | None, frozenset[str]] = {
    None: frozenset(
        (
            "prefix",
            "idempotentResult",
            "temporaryIdMapping",
            "recordingRight",
            "tElementCommitment",
        )
    ),
    "P1": frozenset((*_CLIENT_SIDE_FIELD_IDS, *_REPLAY_COUNT_FIELD_IDS)),
    "P2": frozenset((*_CLIENT_SIDE_FIELD_IDS, *_REPLAY_COUNT_FIELD_IDS)),
    "P3": frozenset(
        (
            *_CLIENT_SIDE_FIELD_IDS,
            "d1",
            "prefix",
            "temporaryIdMapping",
            "intentCountsAfterReplay",
            *_I6_FIELD_IDS,
        )
    ),
    "P4": frozenset((*_CLIENT_SIDE_FIELD_IDS, "temporaryIdMapping")),
    "P5": frozenset((*_CLIENT_SIDE_FIELD_IDS, "temporaryIdMapping")),
}

# T 要素の内部の保存単位(SP 10-3「tElementCommitment」)。ここにない組は単一値。
T_ELEMENT_UNITS: Mapping[tuple[ApplicationPath, str], tuple[str, ...]] = {
    ("P1", "T2"): ("slot", "event"),
    ("P2", "T2"): ("slot", "event"),
    ("P1", "T6"): ("result", "mapping"),
    ("P2", "T6"): ("result", "mapping"),
    ("P3", "T7"): ("targetVersion", "intents"),
    ("P4", "T8"): ("ledger", "original"),
    ("P5", "T9"): ("ledger", "original"),
}
T_ELEMENT_STATES = frozenset(("committed", "notCommitted", "no-write", "no-change"))
_COMMIT_STATES = frozenset(("committed", "notCommitted"))
_NO_EFFECT_STATES = frozenset(("no-write", "no-change"))

# トランザクションの外の 3 注入点(SP 10-3「注入点の組の導出元」)。
OUT_OF_TRANSACTION_POINTS = (
    "T7 確定後・無効化配信前",
    "消費側反映後・配信完了記録前",
    "サーバー確定後・I6端末永続化前",
)

# 母集合 — 観点 key と scenarioId の組 26 件(sync-server-apply design 6-2)。
OBSERVATION_SCENARIO_PAIRS: tuple[tuple[str, str], ...] = (
    ("tombstone-apply", "tombstone-application"),
    ("revision-apply", "revision-application"),
    ("p1", "p1-crash-boundaries"),
    ("p2", "p2-crash-boundaries"),
    ("p3", "p3-crash-boundaries"),
    ("p3", "p3-invalidation-consumed-before-complete"),
    ("d1-mixed-batch", "d1-mixed-batch"),
    ("b3b-after-gap", "b3b-after-gap"),
    ("d4-no-reuse-after-rollback", "restore-d4-issued-set"),
    ("d4-no-reuse-after-rollback", "restore-d4-consecutive-rollbacks"),
    ("all-write-paths-during-restore", "restore-all-write-paths-blocked"),
    ("rg1-commit-race", "restore-commit-race"),
    ("rg1-release-new-d4-boundary", "restore-release-new-generation-boundary"),
    ("restore-lifecycle-complete", "restore-fence-escrow-new-generation"),
    ("restore-crash-midway", "restore-crash-before-new-generation"),
    ("restore-uncollected-device", "restore-uncollected-device"),
    ("restore-24h-cleanup", "restore-cleanup-held"),
    ("restore-24h-cleanup", "restore-expired-not-collected"),
    ("o4-persisted-d2-equivalence", "o4-persisted-d2-equivalence"),
    ("multi-tab-single-writer", "multi-tab-single-writer"),
    ("p4", "p4-crash-boundaries"),
    ("p5", "p5-b3a-crash-boundaries"),
    ("p5", "p5-b3b-unreached-t9"),
    ("leader-freeze-reelection", "leader-freeze-reelection"),
    ("waiting-input-not-accepted", "waiting-input-not-accepted"),
    ("durable-append-failure", "durable-append-failure"),
)
# 正本 10-2 の (d) の故障系観点 22 行の key(sync-server-apply design 6-2)。
OBSERVATION_KEYS = frozenset(
    (
        "tombstone-apply",
        "revision-apply",
        "p1",
        "p2",
        "p3",
        "d1-mixed-batch",
        "b3b-after-gap",
        "d4-no-reuse-after-rollback",
        "all-write-paths-during-restore",
        "rg1-commit-race",
        "rg1-release-new-d4-boundary",
        "restore-lifecycle-complete",
        "restore-crash-midway",
        "restore-uncollected-device",
        "restore-24h-cleanup",
        "o4-persisted-d2-equivalence",
        "multi-tab-single-writer",
        "p4",
        "p5",
        "leader-freeze-reelection",
        "waiting-input-not-accepted",
        "durable-append-failure",
    )
)
# 本単位(U-S1)が資産を持つ scenarioId 16 件。
OWNED_SCENARIO_IDS = frozenset(
    (
        "multi-tab-single-writer",
        "leader-freeze-reelection",
        "waiting-input-not-accepted",
        "durable-append-failure",
        "tombstone-application",
        "revision-application",
        "p1-crash-boundaries",
        "p2-crash-boundaries",
        "p3-crash-boundaries",
        "p4-crash-boundaries",
        "p5-b3a-crash-boundaries",
        "p5-b3b-unreached-t9",
        "d1-mixed-batch",
        "b3b-after-gap",
        "p3-invalidation-consumed-before-complete",
        "o4-persisted-d2-equivalence",
    )
)
# 繰り延べた scenarioId と繰り延べ先(裁定 R-11 — 復元系 10 件は U-R1)。
DEFERRED_SCENARIO_IDS: Mapping[str, str] = {
    scenario_id: "U-R1(TSK-392)"
    for scenario_id in (
        "restore-fence-escrow-new-generation",
        "restore-crash-before-new-generation",
        "restore-uncollected-device",
        "restore-commit-race",
        "restore-cleanup-held",
        "restore-expired-not-collected",
        "restore-d4-issued-set",
        "restore-d4-consecutive-rollbacks",
        "restore-all-write-paths-blocked",
        "restore-release-new-generation-boundary",
    )
}
# トランザクション内の注入被覆 — 到達する注入 case が宣言する (経路, T 要素)。
TRANSACTION_INJECTION_COVERAGE: Mapping[str, frozenset[tuple[str, str]]] = {
    "p1-crash-boundaries": frozenset(("P1", t) for t in ("T1", "T2", "T3", "T4", "T6")),
    "p2-crash-boundaries": frozenset(
        ("P2", t) for t in ("T1", "T2", "T3", "T4", "T5", "T6")
    ),
    "p3-crash-boundaries": frozenset(("P3", t) for t in ("T1", "T2", "T4", "T6", "T7")),
    "p4-crash-boundaries": frozenset({("P4", "T8")}),
    "p5-b3a-crash-boundaries": frozenset({("P5", "T9")}),
}
TRANSACTION_INJECTION_DEFERRED: Mapping[tuple[str, str], str] = {}
# トランザクション外の注入被覆と繰り延べ。
OUT_OF_TRANSACTION_INJECTION_COVERAGE: Mapping[str, frozenset[str]] = {
    "p3-crash-boundaries": frozenset(
        ("T7 確定後・無効化配信前", "サーバー確定後・I6端末永続化前")
    ),
    "p3-invalidation-consumed-before-complete": frozenset(
        ("消費側反映後・配信完了記録前",)
    ),
}
OUT_OF_TRANSACTION_INJECTION_DEFERRED: Mapping[str, str] = {}

_FILE_NAME_PATTERN = re.compile(r"^([a-z0-9]+(?:-[a-z0-9]+)*)_v([1-9]\d*)\.json$")
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ROUTE_ROW_PATTERN = re.compile(r"^(P[1-5]):[^=]+=(T[1-9](?:,T[1-9])*)$")


class FailureScenarioContractError(ValueError):
    """故障系資産の契約または実行結果が正本 10-3 に合わない。"""


def _fail(message: str) -> Any:
    raise FailureScenarioContractError(message)


def load_transaction_routes(
    path: Path = _RELATIONS_PATH,
) -> dict[ApplicationPath, tuple[str, ...]]:
    """``R-TXN-ROUTE`` から経路ごとの T 要素の並びを読む。

    Args:
        path: 設計関係データ ``sync-protocol.json`` の場所。

    Returns:
        経路 → その経路の T 要素(8-1 の経路表の順)。

    Raises:
        FailureScenarioContractError: 経路の行が P1〜P5 の 5 行でない場合。
    """
    relation = json.loads(path.read_text(encoding="utf-8"))["R-TXN-ROUTE"]
    routes: dict[ApplicationPath, tuple[str, ...]] = {}
    for element in relation["source_elements"]:
        match = _ROUTE_ROW_PATTERN.match(element)
        if match is None:
            continue
        route = cast(ApplicationPath, match.group(1))
        if route in routes:
            _fail(f"R-TXN-ROUTE の経路が重複しています: {route}")
        routes[route] = tuple(match.group(2).split(","))
    if tuple(sorted(routes)) != APPLICATION_PATHS:
        _fail(f"R-TXN-ROUTE の経路が P1〜P5 ではありません: {sorted(routes)}")
    return routes


def transaction_pairs(
    routes: Mapping[ApplicationPath, Sequence[str]],
) -> frozenset[tuple[str, str]]:
    """経路表から (経路, T 要素) の有効な組を導く。"""
    return frozenset((path, t) for path, elements in routes.items() for t in elements)


def expected_field_ids(path: ApplicationPath | None) -> tuple[str, ...]:
    """観測点ごとの期待フィールドの集合を、経路に応じた順で返す。"""
    return (*COMMON_EXPECTED_FIELD_IDS, *_EXTRA_FIELD_IDS[path])


def injection_target_key(target: Mapping[str, Any]) -> str:
    """比較単位に載せる注入対象の正規表記を返す。"""
    kind = target["kind"]
    if kind == "transaction":
        return f"{target['path']}:{target['tElement']}"
    if kind == "outOfTransaction":
        return f"P3:{target['point']}"
    return f"client:{target['operation']}"


def _record(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _fail(f"{location} はオブジェクトでなければなりません")
    return cast(dict[str, Any], value)


def _exact_keys(value: object, keys: Sequence[str], location: str) -> dict[str, Any]:
    record = _record(value, location)
    if tuple(record) != tuple(keys):
        _fail(f"{location} のキーまたは順序が一致しません: {','.join(record)}")
    return record


def _non_empty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return _fail(f"{location} は空でない文字列でなければなりません")
    return value


def _non_empty_list(value: object, location: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        return _fail(f"{location} は空でない配列でなければなりません")
    return cast(list[Any], value)


def _is_omitted(value: object) -> bool:
    return isinstance(value, dict) and tuple(value) == ("omittedBecause",)


def _wrapped(value: object, location: str) -> tuple[bool, Any]:
    """入力・故障注入の ``{value}`` / ``{omittedBecause}`` を読む。"""
    record = _record(value, location)
    if tuple(record) == ("value",):
        if record["value"] is None:
            _fail(f"{location} の値を暗黙に省略できません")
        return True, record["value"]
    if tuple(record) == ("omittedBecause",):
        _non_empty_string(record["omittedBecause"], f"{location}.omittedBecause")
        return False, None
    return _fail(f"{location} は値または省略理由の一方だけを持たなければなりません")


def _required_value(section: Mapping[str, Any], key: str, location: str) -> Any:
    present, value = _wrapped(section[key], f"{location}.{key}")
    if not present:
        _fail(f"{location}.{key} は省略できません")
    return value


def _commitment_leaves(
    value: object,
    path: ApplicationPath,
    routes: Mapping[ApplicationPath, Sequence[str]],
    location: str,
) -> dict[str, tuple[str, ...]]:
    """TElementCommitment を検査し、T 要素 → 内部単位の状態の並びを返す。"""
    record = _exact_keys(value, routes[path], location)
    leaves: dict[str, tuple[str, ...]] = {}
    for element, state in record.items():
        units = T_ELEMENT_UNITS.get((path, element))
        if units is None:
            states: tuple[object, ...] = (state,)
        else:
            unit_record = _exact_keys(state, units, f"{location}.{element}")
            states = tuple(unit_record.values())
        for leaf in states:
            if leaf not in T_ELEMENT_STATES:
                _fail(f"{location}.{element} の状態が未知です: {leaf}")
        leaves[element] = cast(tuple[str, ...], states)
    commit_states = {
        leaf for states in leaves.values() for leaf in states if leaf in _COMMIT_STATES
    }
    if len(commit_states) > 1:
        _fail(f"{location} が部分確定です(確定と非確定が混在)")
    return leaves


def _validate_p5_branch(
    input_section: Mapping[str, Any], path: ApplicationPath | None
) -> str | None:
    present, branch = _wrapped(input_section["p5Branch"], "input.p5Branch")
    if path != "P5":
        if present:
            _fail("P5 以外の資産は input.p5Branch に省略理由を書かなければなりません")
        return None
    if not present:
        return _fail("P5 の資産は input.p5Branch を必須とします")
    branch_record = _record(branch, "input.p5Branch.value")
    d5 = _record(_required_value(input_section, "d5", "input"), "input.d5.value")
    d5 = _exact_keys(d5, ("persisted", "requested"), "input.d5.value")
    persisted = d5["persisted"]
    requested = d5["requested"]
    if not isinstance(persisted, list) or not isinstance(requested, list):
        _fail("input.d5.value の persisted・requested は配列でなければなりません")
    kind = branch_record.get("kind")
    if kind == "B3a":
        branch_record = _exact_keys(
            branch_record, ("kind", "d5", "rejectedOriginal"), "input.p5Branch.value"
        )
        if branch_record["d5"] in persisted:
            _fail("B3a の D5 が初期べき等集合に存在します(未使用でない)")
        if branch_record["d5"] not in requested:
            _fail("B3a の D5 が要求に含まれていません")
        if not _record(branch_record["rejectedOriginal"], "rejectedOriginal"):
            _fail("B3a の拒否原本が空です")
        return "B3a"
    if kind == "B3b":
        branch_record = _exact_keys(
            branch_record,
            ("kind", "firstOriginal", "laterInput"),
            "input.p5Branch.value",
        )
        first = _exact_keys(
            branch_record["firstOriginal"], ("d5", "content"), "firstOriginal"
        )
        later = _exact_keys(
            branch_record["laterInput"], ("d5", "content"), "laterInput"
        )
        if first["d5"] != later["d5"]:
            _fail("B3b の先着と後着の D5 が異なります")
        if first["content"] == later["content"]:
            _fail("B3b の先着と後着の内容が同一です")
        if first["d5"] not in persisted:
            _fail("B3b の D5 が初期べき等集合に存在しません")
        initial = _record(
            _required_value(input_section, "initialPersistence", "input"),
            "input.initialPersistence.value",
        )
        originals = initial.get("originals")
        if not isinstance(originals, list) or first not in originals:
            _fail("B3b の先着原本が初期永続状態に一致しません")
        return "B3b"
    return _fail(f"input.p5Branch.value.kind は B3a か B3b です: {kind}")


def validate_failure_scenario_contract(
    file_name: str,
    asset: object,
    routes: Mapping[ApplicationPath, Sequence[str]],
) -> dict[str, Any]:
    """資産 1 件の形を正本 10-3 v0.8 の契約で fail-closed に検査する。

    Args:
        file_name: ``<scenarioId>_v<N>.json`` のファイル名。
        asset: JSON から読んだ資産。
        routes: ``R-TXN-ROUTE`` 由来の経路表。

    Returns:
        検査済みの資産。

    Raises:
        FailureScenarioContractError: 契約に合わない場合。
    """
    name_match = _FILE_NAME_PATTERN.match(file_name)
    if name_match is None:
        _fail(f"ファイル名が版付け規則に一致しません: {file_name}")
    assert name_match is not None
    root = _exact_keys(asset, ROOT_FIELD_IDS, file_name)
    if root["schemaVersion"] != SCHEMA_VERSION or isinstance(
        root["schemaVersion"], bool
    ):
        _fail(f"schemaVersion は {SCHEMA_VERSION} でなければなりません")
    scenario_id = root["scenarioId"]
    if (
        scenario_id not in OWNED_SCENARIO_IDS
        and scenario_id not in DEFERRED_SCENARIO_IDS
    ):
        _fail(f"scenarioId が母集合にありません: {scenario_id}")
    version = root["version"]
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        _fail("version は正の整数でなければなりません")
    if name_match.group(1) != scenario_id or int(name_match.group(2)) != version:
        _fail("ファイル名と内部の scenarioId または version が一致しません")

    input_section = _exact_keys(root["input"], INPUT_FIELD_IDS, "input")
    for key in INPUT_FIELD_IDS:
        _wrapped(input_section[key], f"input.{key}")
    present, path_value = _wrapped(
        input_section["applicationPath"], "input.applicationPath"
    )
    if present and path_value not in APPLICATION_PATHS:
        _fail(f"input.applicationPath は P1〜P5 です: {path_value}")
    path = cast(ApplicationPath | None, path_value if present else None)
    p5_branch = _validate_p5_branch(input_section, path)

    pairs = transaction_pairs(routes)
    field_ids = expected_field_ids(path)
    cases = _non_empty_list(root["cases"], "cases")
    seen_case_ids: set[str] = set()
    seen_injections: set[tuple[str, str]] = set()
    expected_units: list[tuple[str, str, str, str]] = []
    reached_transaction = 0
    unreached_transaction = 0
    for case_index, raw_case in enumerate(cases):
        location = f"cases[{case_index}]"
        case = _exact_keys(raw_case, CASE_FIELD_IDS, location)
        case_id = _non_empty_string(case["caseId"], f"{location}.caseId")
        if not _ID_PATTERN.match(case_id):
            _fail(f"{location}.caseId は小文字英数とハイフンです: {case_id}")
        if case_id in seen_case_ids:
            _fail(f"caseId が重複しています: {case_id}")
        seen_case_ids.add(case_id)

        injection = _exact_keys(
            case["faultInjection"],
            FAULT_INJECTION_FIELD_IDS,
            f"{location}.faultInjection",
        )
        for key in FAULT_INJECTION_FIELD_IDS:
            _wrapped(injection[key], f"{location}.faultInjection.{key}")
        target = _record(
            _required_value(injection, "target", f"{location}.faultInjection"),
            f"{location}.faultInjection.target.value",
        )
        point = _non_empty_string(
            _required_value(injection, "injectionPoint", f"{location}.faultInjection"),
            f"{location}.faultInjection.injectionPoint.value",
        )
        reachability = _required_value(
            injection, "expectedReachability", f"{location}.faultInjection"
        )
        if reachability not in ("reached", "unreached"):
            _fail(f"{location} の expectedReachability は reached か unreached です")
        kind = target.get("kind")
        if kind == "transaction":
            _exact_keys(target, ("kind", "path", "tElement"), f"{location}.target")
            if target["path"] != path:
                _fail(f"{location} の注入経路が applicationPath と一致しません")
            if (target["path"], target["tElement"]) not in pairs:
                _fail(
                    f"{location} の (経路, T 要素) が R-TXN-ROUTE にありません: "
                    f"{target['path']}:{target['tElement']}"
                )
        elif kind == "outOfTransaction":
            _exact_keys(target, ("kind", "point"), f"{location}.target")
            if path != "P3":
                _fail(f"{location} のトランザクション外注入は P3 だけです")
            if target["point"] not in OUT_OF_TRANSACTION_POINTS:
                _fail(f"{location} の P3 外注入点が未知です: {target['point']}")
        elif kind == "client":
            _exact_keys(target, ("kind", "operation"), f"{location}.target")
            _non_empty_string(target["operation"], f"{location}.target.operation")
        else:
            _fail(f"{location} の注入対象の kind が未知です: {kind}")
        target_key = injection_target_key(target)
        if (target_key, point) in seen_injections:
            _fail(f"同じ注入が重複しています: {target_key} / {point}")
        seen_injections.add((target_key, point))

        observations = _non_empty_list(case["observations"], f"{location}.observations")
        seen_points: set[str] = set()
        has_commit_observation = False
        for observation_index, raw_observation in enumerate(observations):
            observation_location = f"{location}.observations[{observation_index}]"
            observation = _exact_keys(
                raw_observation, OBSERVATION_FIELD_IDS, observation_location
            )
            observation_point = _non_empty_string(
                observation["observationPoint"],
                f"{observation_location}.observationPoint",
            )
            if observation_point in seen_points:
                _fail(f"観測点が case 内で重複しています: {observation_point}")
            seen_points.add(observation_point)
            fields = _exact_keys(
                observation["fields"], field_ids, f"{observation_location}.fields"
            )
            for field_id in field_ids:
                value = fields[field_id]
                if value is None:
                    _fail(f"{observation_location}.fields.{field_id} の暗黙の省略です")
                if _is_omitted(value):
                    if field_id not in OMITTABLE_FIELD_IDS[path]:
                        _fail(
                            f"{observation_location}.fields.{field_id} は "
                            f"{path or 'クライアント側'} の資産で省略できません"
                        )
                    _non_empty_string(
                        value["omittedBecause"],
                        f"{observation_location}.fields.{field_id}.omittedBecause",
                    )
                elif isinstance(value, dict) and "omittedBecause" in value:
                    _fail(
                        f"{observation_location}.fields.{field_id} の省略表現が不正です"
                    )
                expected_units.append(
                    (case_id, target_key, observation_point, field_id)
                )
            commitment = fields["tElementCommitment"]
            if path is not None and not _is_omitted(commitment):
                leaves = _commitment_leaves(
                    commitment,
                    path,
                    routes,
                    f"{observation_location}.fields.tElementCommitment",
                )
                if any(
                    leaf in _COMMIT_STATES
                    for states in leaves.values()
                    for leaf in states
                ):
                    has_commit_observation = True
                if kind == "transaction" and reachability == "unreached":
                    target_states = leaves[target["tElement"]]
                    if not set(target_states) <= _NO_EFFECT_STATES:
                        _fail(
                            f"{observation_location} の到達しない注入対象 "
                            f"{target['tElement']} が確定・非確定を持ちます"
                        )
        if kind == "transaction":
            if reachability == "reached":
                reached_transaction += 1
                if not has_commit_observation:
                    _fail(
                        f"{location} は到達する注入なのに確定・非確定の観測がありません"
                    )
            else:
                unreached_transaction += 1

    for field_id in REQUIRED_SOMEWHERE_FIELD_IDS[path]:
        if all(
            _is_omitted(observation["fields"][field_id])
            for case in cases
            for observation in case["observations"]
        ):
            _fail(
                f"{field_id} はこの資産のどこかの観測点で実値を持たなければなりません"
            )

    if p5_branch == "B3b":
        if reached_transaction:
            _fail("B3b の資産はトランザクション内の到達する case を宣言しません")
        if not unreached_transaction:
            _fail("B3b の資産は T9 の到達しない注入点を必須とします")
    if p5_branch == "B3a" and not reached_transaction:
        _fail("B3a の資産は T9 の到達する注入点を必須とします")

    units = _non_empty_list(root["comparisonUnit"], "comparisonUnit")
    if len(units) != len(expected_units):
        _fail("comparisonUnit は全 case・全観測点・全期待フィールドを含みます")
    for index, raw_unit in enumerate(units):
        unit = _exact_keys(
            raw_unit, COMPARISON_UNIT_FIELD_IDS, f"comparisonUnit[{index}]"
        )
        case_id, target_key, observation_point, field_id = expected_units[index]
        if (
            unit["scenarioId"] != scenario_id
            or unit["caseId"] != case_id
            or unit["injectionTarget"] != target_key
            or unit["observationPoint"] != observation_point
            or unit["expectedField"] != field_id
        ):
            _fail(f"comparisonUnit[{index}] の内容または順序が一致しません")
    return root


def reached_transaction_pairs(asset: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    """検査済みの資産が到達する注入として宣言した (経路, T 要素) を返す。"""
    pairs: set[tuple[str, str]] = set()
    for case in asset["cases"]:
        injection = case["faultInjection"]
        target = injection["target"]["value"]
        if (
            target["kind"] == "transaction"
            and injection["expectedReachability"]["value"] == "reached"
        ):
            pairs.add((target["path"], target["tElement"]))
    return frozenset(pairs)


def out_of_transaction_points(asset: Mapping[str, Any]) -> frozenset[str]:
    """検査済みの資産が宣言したトランザクション外の注入点を返す。"""
    return frozenset(
        case["faultInjection"]["target"]["value"]["point"]
        for case in asset["cases"]
        if case["faultInjection"]["target"]["value"]["kind"] == "outOfTransaction"
    )


def validate_failure_scenario_result(
    asset: Mapping[str, Any],
    result: object,
    routes: Mapping[ApplicationPath, Sequence[str]],
) -> None:
    """Runner の実行結果を、検査済みの資産の期待結果と比べる。

    契約が省略理由を書いたフィールドは結果に現れてはならず、実値のフィールドは
    結果に同じ値で現れなければならない。

    Args:
        asset: ``validate_failure_scenario_contract`` を通った資産。
        result: runner が返した実行結果。
        routes: ``R-TXN-ROUTE`` 由来の経路表。

    Raises:
        FailureScenarioContractError: 欠落・未知・順序違い・値の不一致がある場合。
    """
    record = _exact_keys(result, RESULT_FIELD_IDS, "result")
    if record["scenarioId"] != asset["scenarioId"]:
        _fail("result.scenarioId が契約と一致しません")
    present, path_value = _wrapped(
        asset["input"]["applicationPath"], "input.applicationPath"
    )
    path = cast(ApplicationPath | None, path_value if present else None)
    result_cases = record["cases"]
    if not isinstance(result_cases, list) or len(result_cases) != len(asset["cases"]):
        _fail("result.cases の件数が契約と一致しません")
    for case_index, (expected_case, raw_case) in enumerate(
        zip(asset["cases"], result_cases, strict=True)
    ):
        location = f"result.cases[{case_index}]"
        case = _exact_keys(raw_case, RESULT_CASE_FIELD_IDS, location)
        if case["caseId"] != expected_case["caseId"]:
            _fail(f"{location}.caseId の順序または値が一致しません")
        hook_calls = case["hookCalls"]
        if (
            not isinstance(hook_calls, int)
            or isinstance(hook_calls, bool)
            or hook_calls < 0
        ):
            _fail(f"{location}.hookCalls は 0 以上の整数です")
        reachability = expected_case["faultInjection"]["expectedReachability"]["value"]
        if reachability == "unreached" and hook_calls != 0:
            _fail(f"{location} は到達しない注入点なのに注入点が呼ばれました")
        if reachability == "reached" and hook_calls == 0:
            _fail(f"{location} は到達する注入点なのに注入点が呼ばれていません")
        observations = case["observations"]
        expected_observations = expected_case["observations"]
        if not isinstance(observations, list) or len(observations) != len(
            expected_observations
        ):
            _fail(f"{location}.observations の件数が契約と一致しません")
        for observation_index, (expected, raw_observation) in enumerate(
            zip(expected_observations, observations, strict=True)
        ):
            observation_location = f"{location}.observations[{observation_index}]"
            observation = _exact_keys(
                raw_observation, OBSERVATION_FIELD_IDS, observation_location
            )
            if observation["observationPoint"] != expected["observationPoint"]:
                _fail(f"{observation_location} の観測点の順序が一致しません")
            real_field_ids = tuple(
                field_id
                for field_id, value in expected["fields"].items()
                if not _is_omitted(value)
            )
            fields = _exact_keys(
                observation["fields"], real_field_ids, f"{observation_location}.fields"
            )
            commitment = fields.get("tElementCommitment")
            if path is not None and commitment is not None:
                _commitment_leaves(
                    commitment,
                    path,
                    routes,
                    f"{observation_location}.fields.tElementCommitment",
                )
            for field_id in real_field_ids:
                if fields[field_id] != expected["fields"][field_id]:
                    _fail(f"{observation_location}.fields.{field_id} が一致しません")


def validate_population(
    pairs: Sequence[tuple[str, str]] = OBSERVATION_SCENARIO_PAIRS,
    observation_keys: frozenset[str] = OBSERVATION_KEYS,
    owned: frozenset[str] = OWNED_SCENARIO_IDS,
    deferred: Mapping[str, str] = DEFERRED_SCENARIO_IDS,
) -> None:
    """母集合を組の集合として exact-set で照合する(SP 10-3「母集合」)。

    Raises:
        FailureScenarioContractError: 組・観点・scenarioId に過不足がある場合。
    """
    pair_set = set(pairs)
    if len(pair_set) != len(pairs):
        _fail("観点と scenarioId の組が重複しています")
    scenario_ids = [scenario_id for _, scenario_id in pairs]
    if len(set(scenario_ids)) != len(scenario_ids):
        _fail("scenarioId が複数の観点に属しています")
    if {key for key, _ in pairs} != observation_keys:
        _fail("組の観点集合が 10-2 の観点と一致しません")
    if owned & set(deferred):
        _fail("作成と繰り延べの両方に属する scenarioId があります")
    if set(scenario_ids) != owned | set(deferred):
        _fail("作成 ∪ 繰り延べが母集合と一致しません")
    for scenario_id, receiver in deferred.items():
        if not receiver.strip():
            _fail(f"繰り延べ先がありません: {scenario_id}")


def validate_injection_coverage(
    routes: Mapping[ApplicationPath, Sequence[str]],
    transaction: Mapping[
        str, frozenset[tuple[str, str]]
    ] = TRANSACTION_INJECTION_COVERAGE,
    transaction_deferred: Mapping[
        tuple[str, str], str
    ] = TRANSACTION_INJECTION_DEFERRED,
    out_of_transaction: Mapping[
        str, frozenset[str]
    ] = OUT_OF_TRANSACTION_INJECTION_COVERAGE,
    out_of_transaction_deferred: Mapping[
        str, str
    ] = OUT_OF_TRANSACTION_INJECTION_DEFERRED,
) -> None:
    """注入点の被覆と繰り延べを exact-set で照合する。

    Raises:
        FailureScenarioContractError: 被覆 ∪ 繰り延べが注入点の全体と一致しない場合、
            または両方に属する注入点がある場合。
    """
    covered = set().union(*transaction.values()) if transaction else set()
    if covered & set(transaction_deferred):
        _fail("トランザクション内の注入点が被覆と繰り延べの両方にあります")
    if covered | set(transaction_deferred) != transaction_pairs(routes):
        _fail("トランザクション内の注入被覆が R-TXN-ROUTE の組と一致しません")
    for scenario_id in (*transaction, *out_of_transaction):
        if scenario_id not in OWNED_SCENARIO_IDS:
            _fail(
                f"被覆を宣言した scenarioId が本単位の資産ではありません: {scenario_id}"
            )
    out_covered: set[str] = (
        set().union(*out_of_transaction.values()) if out_of_transaction else set()
    )
    if out_covered & set(out_of_transaction_deferred):
        _fail("トランザクション外の注入点が被覆と繰り延べの両方にあります")
    if out_covered | set(out_of_transaction_deferred) != set(OUT_OF_TRANSACTION_POINTS):
        _fail("トランザクション外の注入被覆が 3 注入点と一致しません")


# ---------------------------------------------------------------------------
# 試験
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def routes() -> dict[ApplicationPath, tuple[str, ...]]:
    """正本 8-1 の経路表を設計関係データから読む。"""
    return load_transaction_routes()


def _wrap(value: object) -> dict[str, object]:
    return {"value": value}


def _omit(reason: str = "この資産の観測対象でないため") -> dict[str, str]:
    return {"omittedBecause": reason}


def _commitment(
    path: ApplicationPath,
    routes: Mapping[ApplicationPath, Sequence[str]],
    state: str,
    overrides: Mapping[str, object] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {}
    for element in routes[path]:
        units = T_ELEMENT_UNITS.get((path, element))
        record[element] = state if units is None else dict.fromkeys(units, state)
    record.update(overrides or {})
    return record


def _fields(
    path: ApplicationPath | None,
    routes: Mapping[ApplicationPath, Sequence[str]],
    state: str = "committed",
) -> dict[str, object]:
    fields: dict[str, object] = {}
    for field_id in expected_field_ids(path):
        if field_id == "tElementCommitment":
            fields[field_id] = (
                _omit() if path is None else _commitment(path, routes, state)
            )
        elif (
            path is not None
            and field_id in OMITTABLE_FIELD_IDS[path]
            and field_id not in REQUIRED_SOMEWHERE_FIELD_IDS[path]
        ):
            fields[field_id] = _omit("サーバー側 runner は端末を観測しないため")
        else:
            fields[field_id] = {"observed": field_id}
    return fields


def _asset(
    scenario_id: str,
    path: ApplicationPath | None,
    cases: list[dict[str, object]],
    *,
    p5_branch: object | None = None,
    d5: object | None = None,
    initial: object | None = None,
) -> dict[str, Any]:
    input_section: dict[str, object] = {
        key: _omit("この資産の入力でないため") for key in INPUT_FIELD_IDS
    }
    input_section["initialPersistence"] = _wrap(initial or {"rows": 0})
    input_section["applicationPath"] = _omit() if path is None else _wrap(path)
    if p5_branch is not None:
        input_section["p5Branch"] = _wrap(p5_branch)
    if d5 is not None:
        input_section["d5"] = _wrap(d5)
    asset: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "scenarioId": scenario_id,
        "version": 2,
        "input": input_section,
        "cases": cases,
        "comparisonUnit": [],
    }
    asset["comparisonUnit"] = _units(asset)
    return asset


def _units(asset: Mapping[str, Any]) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for case in asset["cases"]:
        target_key = injection_target_key(case["faultInjection"]["target"]["value"])
        for observation in case["observations"]:
            for field_id in observation["fields"]:
                units.append(
                    {
                        "scenarioId": asset["scenarioId"],
                        "caseId": case["caseId"],
                        "injectionTarget": target_key,
                        "observationPoint": observation["observationPoint"],
                        "expectedField": field_id,
                    }
                )
    return units


def _case(
    case_id: str,
    target: Mapping[str, object],
    fields: Mapping[str, object],
    *,
    reachability: str = "reached",
    point: str = "保存の直後・コミット前",
) -> dict[str, object]:
    return {
        "caseId": case_id,
        "faultInjection": {
            "target": _wrap(dict(target)),
            "injectionPoint": _wrap(point),
            "stopOperation": _wrap("プロセスを落とす"),
            "restartOperation": _wrap("同じ D5・同じ内容で再送する"),
            "expectedReachability": _wrap(reachability),
        },
        "observations": [{"observationPoint": "再起動後", "fields": dict(fields)}],
    }


def _transaction(path: str, element: str) -> dict[str, str]:
    return {"kind": "transaction", "path": path, "tElement": element}


def _p1_asset(routes: Mapping[ApplicationPath, Sequence[str]]) -> dict[str, Any]:
    return _asset(
        "p1-crash-boundaries",
        "P1",
        [
            _case(
                f"crash-{t.lower()}",
                _transaction("P1", t),
                _fields("P1", routes, "notCommitted"),
            )
            for t in routes["P1"]
        ],
    )


def _client_asset(routes: Mapping[ApplicationPath, Sequence[str]]) -> dict[str, Any]:
    return _asset(
        "durable-append-failure",
        None,
        [
            _case(
                "append-failure",
                {"kind": "client", "operation": "入力と D1 の不可分な永続キュー追記"},
                _fields(None, routes),
                point="キュー行と D1 カウンタを確定する前",
            )
        ],
    )


def _p3_asset(routes: Mapping[ApplicationPath, Sequence[str]]) -> dict[str, Any]:
    return _asset(
        "p3-crash-boundaries",
        "P3",
        [
            _case(
                "crash-t7",
                _transaction("P3", "T7"),
                _fields("P3", routes, "notCommitted"),
            ),
            _case(
                "after-t7-before-delivery",
                {"kind": "outOfTransaction", "point": "T7 確定後・無効化配信前"},
                _fields("P3", routes, "committed"),
                point="T7 確定後・無効化配信前",
            ),
        ],
    )


_FIRST = {"d5": "d5-a", "content": {"pitch": "ball"}}


def _b3b_asset(routes: Mapping[ApplicationPath, Sequence[str]]) -> dict[str, Any]:
    no_write = {"ledger": "no-write", "original": "no-write"}
    return _asset(
        "p5-b3b-unreached-t9",
        "P5",
        [
            _case(
                f"t9-{unit}",
                _transaction("P5", "T9"),
                {
                    **_fields("P5", routes),
                    "tElementCommitment": _commitment(
                        "P5", routes, "committed", {"T9": no_write}
                    ),
                },
                reachability="unreached",
                point=f"T9 の {unit} の保存後",
            )
            for unit in ("ledger", "original")
        ],
        p5_branch={
            "kind": "B3b",
            "firstOriginal": _FIRST,
            "laterInput": {"d5": "d5-a", "content": {"pitch": "strike"}},
        },
        d5={"persisted": ["d5-a"], "requested": ["d5-a"]},
        initial={"originals": [_FIRST]},
    )


def _b3a_asset(routes: Mapping[ApplicationPath, Sequence[str]]) -> dict[str, Any]:
    return _asset(
        "p5-b3a-crash-boundaries",
        "P5",
        [
            _case(
                "t9-original",
                _transaction("P5", "T9"),
                _fields("P5", routes, "notCommitted"),
                point="T9 の原本の保存後",
            )
        ],
        p5_branch={"kind": "B3a", "d5": "d5-new", "rejectedOriginal": {"pitch": "?"}},
        d5={"persisted": ["d5-a"], "requested": ["d5-new"]},
    )


_BUILDERS = {
    "p1-crash-boundaries": _p1_asset,
    "durable-append-failure": _client_asset,
    "p3-crash-boundaries": _p3_asset,
    "p5-b3b-unreached-t9": _b3b_asset,
    "p5-b3a-crash-boundaries": _b3a_asset,
}


def _validate(
    asset: Mapping[str, Any], routes: Mapping[ApplicationPath, Sequence[str]]
) -> dict[str, Any]:
    return validate_failure_scenario_contract(
        f"{asset['scenarioId']}_v{asset['version']}.json", asset, routes
    )


def _result_from(asset: Mapping[str, Any]) -> dict[str, Any]:
    cases = []
    for case in asset["cases"]:
        reached = case["faultInjection"]["expectedReachability"]["value"] == "reached"
        cases.append(
            {
                "caseId": case["caseId"],
                "hookCalls": 1 if reached else 0,
                "observations": [
                    {
                        "observationPoint": observation["observationPoint"],
                        "fields": {
                            key: copy.deepcopy(value)
                            for key, value in observation["fields"].items()
                            if not _is_omitted(value)
                        },
                    }
                    for observation in case["observations"]
                ],
            }
        )
    return {"scenarioId": asset["scenarioId"], "cases": cases}


def test_route_reader_reads_the_five_paths_of_8_1(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """経路表の 5 行と有効な 18 組を R-TXN-ROUTE から読む。"""
    assert routes == {
        "P1": ("T1", "T2", "T3", "T4", "T6"),
        "P2": ("T1", "T2", "T3", "T4", "T5", "T6"),
        "P3": ("T1", "T2", "T4", "T6", "T7"),
        "P4": ("T8",),
        "P5": ("T9",),
    }
    assert len(transaction_pairs(routes)) == 18
    assert set(T_ELEMENT_UNITS) <= transaction_pairs(routes)


def test_route_reader_rejects_a_missing_path(tmp_path: Path) -> None:
    """経路の行が欠けた設計関係データを拒否する。"""
    relations = json.loads(_RELATIONS_PATH.read_text(encoding="utf-8"))
    relations["R-TXN-ROUTE"]["source_elements"] = [
        element
        for element in relations["R-TXN-ROUTE"]["source_elements"]
        if not element.startswith("P4:")
    ]
    broken = tmp_path / "sync-protocol.json"
    broken.write_text(json.dumps(relations, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FailureScenarioContractError, match="P1〜P5"):
        load_transaction_routes(broken)


@pytest.mark.parametrize("scenario_id", sorted(_BUILDERS))
def test_contract_accepts_well_formed_assets(
    scenario_id: str, routes: dict[ApplicationPath, tuple[str, ...]]
) -> None:
    """正例: クライアント側・P1・P3・P5 の両分岐の資産が契約検査を通る。"""
    asset = _BUILDERS[scenario_id](routes)
    assert _validate(asset, routes) is asset


def test_expected_field_sets_are_unconditional_plus_path_extras() -> None:
    """共通の 10 件は無条件、P1・P2 に 4 件・P3 に 13 件が加わる。"""
    assert len(COMMON_EXPECTED_FIELD_IDS) == 10
    assert expected_field_ids(None) == COMMON_EXPECTED_FIELD_IDS
    assert expected_field_ids("P4") == COMMON_EXPECTED_FIELD_IDS
    assert len(expected_field_ids("P1")) == 14
    assert len(expected_field_ids("P3")) == 23
    for path in APPLICATION_PATHS:
        assert "tElementCommitment" not in OMITTABLE_FIELD_IDS[path]
        assert "idempotentResult" not in OMITTABLE_FIELD_IDS[path]
        assert "recordingRight" not in OMITTABLE_FIELD_IDS[path]


def _mutate_fields(asset: dict[str, Any], field_id: str, value: object) -> None:
    asset["cases"][0]["observations"][0]["fields"][field_id] = value


def test_contract_rejects_partial_commitment(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: T 要素の 1 つだけ(内部単位の 1 つだけを含む)が確定した部分確定。"""
    asset = _p1_asset(routes)
    _mutate_fields(
        asset,
        "tElementCommitment",
        _commitment("P1", routes, "notCommitted", {"T3": "committed"}),
    )
    with pytest.raises(FailureScenarioContractError, match="部分確定"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    _mutate_fields(
        asset,
        "tElementCommitment",
        _commitment(
            "P1",
            routes,
            "committed",
            {"T2": {"slot": "committed", "event": "notCommitted"}},
        ),
    )
    with pytest.raises(FailureScenarioContractError, match="部分確定"):
        _validate(asset, routes)


def test_contract_rejects_t_sets_that_differ_from_the_route(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: T 要素の集合・内部単位・状態の語彙が経路表と食い違う。"""
    missing = _commitment("P1", routes, "committed")
    del missing["T6"]
    extra = _commitment("P1", routes, "committed", {"T9": "committed"})
    flat_units = _commitment("P1", routes, "committed", {"T2": "committed"})
    unknown_state = _commitment("P1", routes, "committed", {"T3": "partial"})
    for commitment in (missing, extra, flat_units, unknown_state):
        asset = _p1_asset(routes)
        _mutate_fields(asset, "tElementCommitment", commitment)
        with pytest.raises(FailureScenarioContractError):
            _validate(asset, routes)


def test_contract_rejects_isolated_observations(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: case に属さない観測点(旧構造の expected・比較単位だけの観測点)。"""
    asset = _p1_asset(routes)
    asset["expected"] = {"observations": []}
    with pytest.raises(FailureScenarioContractError, match="キー"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    asset["comparisonUnit"][0]["observationPoint"] = "どの case にも無い観測点"
    with pytest.raises(FailureScenarioContractError, match="comparisonUnit"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    asset["comparisonUnit"].append(dict(asset["comparisonUnit"][0]))
    with pytest.raises(FailureScenarioContractError, match="comparisonUnit"):
        _validate(asset, routes)


def test_contract_rejects_duplicate_injection(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: 同じ注入対象・注入時点の case を重ねる。caseId の重複も拒否する。"""
    asset = _p1_asset(routes)
    duplicate = copy.deepcopy(asset["cases"][0])
    duplicate["caseId"] = "crash-again"
    asset["cases"].append(duplicate)
    asset["comparisonUnit"] = _units(asset)
    with pytest.raises(FailureScenarioContractError, match="同じ注入"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    asset["cases"][1]["caseId"] = asset["cases"][0]["caseId"]
    asset["comparisonUnit"] = _units(asset)
    with pytest.raises(FailureScenarioContractError, match="caseId"):
        _validate(asset, routes)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"firstOriginal": {"d5": "d5-b", "content": {"pitch": "ball"}}}, "D5"),
        ({"laterInput": {"d5": "d5-a", "content": {"pitch": "ball"}}}, "同一"),
        ({"firstOriginal": {"d5": "d5-a", "content": {"pitch": "foul"}}}, "初期永続"),
    ],
)
def test_contract_checks_b3b_value_relations(
    mutation: dict[str, object],
    message: str,
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: B3b の異なる D5・同一内容・初期永続状態に無い先着原本。"""
    asset = _b3b_asset(routes)
    asset["input"]["p5Branch"]["value"].update(mutation)
    with pytest.raises(FailureScenarioContractError, match=message):
        _validate(asset, routes)


def test_contract_checks_the_p5_discriminated_union(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: B3a の既存 D5・分岐の欠落・分岐と到達性の食い違い・P5 以外の分岐。"""
    asset = _b3a_asset(routes)
    asset["input"]["d5"]["value"]["persisted"].append("d5-new")
    with pytest.raises(FailureScenarioContractError, match="未使用"):
        _validate(asset, routes)

    asset = _b3a_asset(routes)
    asset["input"]["p5Branch"] = _omit()
    with pytest.raises(FailureScenarioContractError, match="p5Branch"):
        _validate(asset, routes)

    asset = _b3a_asset(routes)
    asset["input"]["p5Branch"]["value"]["kind"] = "B3"
    with pytest.raises(FailureScenarioContractError, match="kind"):
        _validate(asset, routes)

    asset = _b3b_asset(routes)
    asset["cases"][0]["faultInjection"]["expectedReachability"] = _wrap("reached")
    _mutate_fields(
        asset, "tElementCommitment", _commitment("P5", routes, "notCommitted")
    )
    with pytest.raises(FailureScenarioContractError, match="B3b"):
        _validate(asset, routes)

    asset = _b3a_asset(routes)
    asset["cases"][0]["faultInjection"]["expectedReachability"] = _wrap("unreached")
    _mutate_fields(
        asset,
        "tElementCommitment",
        {"T9": {"ledger": "no-write", "original": "no-write"}},
    )
    with pytest.raises(FailureScenarioContractError, match="B3a"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    asset["input"]["p5Branch"] = _b3a_asset(routes)["input"]["p5Branch"]
    with pytest.raises(FailureScenarioContractError, match="P5 以外"):
        _validate(asset, routes)


def test_contract_rejects_reachability_mismatch(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: 到達しない注入点に確定・非確定、到達する注入点に確定・非確定の観測なし。"""
    asset = _p1_asset(routes)
    asset["cases"][0]["faultInjection"]["expectedReachability"] = _wrap("unreached")
    with pytest.raises(FailureScenarioContractError, match="到達しない"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    _mutate_fields(asset, "tElementCommitment", _commitment("P1", routes, "no-write"))
    with pytest.raises(FailureScenarioContractError, match="到達する"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    asset["cases"][0]["faultInjection"]["expectedReachability"] = _wrap("maybe")
    with pytest.raises(FailureScenarioContractError, match="expectedReachability"):
        _validate(asset, routes)


@pytest.mark.parametrize("field_id", P3_EXTRA_FIELD_IDS)
def test_contract_rejects_a_missing_p3_field(
    field_id: str, routes: dict[ApplicationPath, tuple[str, ...]]
) -> None:
    """負例: P3 に加わる期待フィールドの欠落。"""
    asset = _p3_asset(routes)
    del asset["cases"][0]["observations"][0]["fields"][field_id]
    with pytest.raises(FailureScenarioContractError, match="fields"):
        _validate(asset, routes)


@pytest.mark.parametrize("field_id", D1_PATH_EXTRA_FIELD_IDS)
def test_contract_rejects_a_missing_d1_path_field(
    field_id: str, routes: dict[ApplicationPath, tuple[str, ...]]
) -> None:
    """負例: P1・P2 に加わる無効化意図の期待フィールドの欠落と省略。

    再掲後の意図件数は再掲の前の観測点で省けるが、資産の全観測点では省けない。
    """
    asset = _p1_asset(routes)
    del asset["cases"][0]["observations"][0]["fields"][field_id]
    with pytest.raises(FailureScenarioContractError, match="fields"):
        _validate(asset, routes)

    asset = _p1_asset(routes)
    _mutate_fields(asset, field_id, _omit())
    if field_id in REQUIRED_SOMEWHERE_FIELD_IDS["P1"]:
        _validate(asset, routes)
        for case in asset["cases"]:
            for observation in case["observations"]:
                observation["fields"][field_id] = _omit()
        with pytest.raises(FailureScenarioContractError, match="どこかの観測点"):
            _validate(asset, routes)
    else:
        with pytest.raises(FailureScenarioContractError, match="省略できません"):
            _validate(asset, routes)


def test_contract_limits_omission_by_path(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """省略可否だけを経路で条件付きにする。省略できないフィールドの省略は不合格。"""
    for field_id in ("tElementCommitment", "idempotentResult", "recordingRight"):
        asset = _p1_asset(routes)
        _mutate_fields(asset, field_id, _omit())
        with pytest.raises(FailureScenarioContractError, match="省略できません"):
            _validate(asset, routes)
    asset = _client_asset(routes)
    _mutate_fields(asset, "queue", _omit())
    with pytest.raises(FailureScenarioContractError, match="省略できません"):
        _validate(asset, routes)
    asset = _p3_asset(routes)
    _mutate_fields(asset, "invalidationIntentIds", _omit())
    with pytest.raises(FailureScenarioContractError, match="省略できません"):
        _validate(asset, routes)
    asset = _p1_asset(routes)
    _mutate_fields(asset, "prefix", {"omittedBecause": "理由", "value": 1})
    with pytest.raises(FailureScenarioContractError, match="省略表現"):
        _validate(asset, routes)


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "transaction", "path": "P1", "tElement": "T9"},
        {"kind": "transaction", "path": "P1", "tElement": "T10"},
        {"kind": "transaction", "path": "P2", "tElement": "T5"},
        {"kind": "outOfTransaction", "point": "T7 確定後・無効化配信前"},
        {"kind": "server", "operation": "停止"},
    ],
)
def test_contract_closes_the_injection_vocabulary(
    target: dict[str, str], routes: dict[ApplicationPath, tuple[str, ...]]
) -> None:
    """負例: 経路表に無い組・別経路の組・P3 以外の P3 外注入・未知の kind。"""
    asset = _p1_asset(routes)
    asset["cases"][0]["faultInjection"]["target"] = _wrap(target)
    asset["comparisonUnit"] = _units(asset)
    with pytest.raises(FailureScenarioContractError):
        _validate(asset, routes)


def test_contract_rejects_a_misspelled_out_of_transaction_point(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """負例: 誤字のある P3 のトランザクション外注入点。"""
    asset = _p3_asset(routes)
    asset["cases"][1]["faultInjection"]["target"] = _wrap(
        {"kind": "outOfTransaction", "point": "T7確定後・無効化配信前"}
    )
    asset["comparisonUnit"] = _units(asset)
    with pytest.raises(FailureScenarioContractError, match="未知"):
        _validate(asset, routes)


def test_contract_pairs_schema_version_with_structure(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """旧 schemaVersion + 新構造 / 新 schemaVersion + 旧構造をいずれも拒否する。"""
    asset = _p1_asset(routes)
    asset["schemaVersion"] = 1
    with pytest.raises(FailureScenarioContractError, match="schemaVersion"):
        _validate(asset, routes)

    legacy = _p1_asset(routes)
    first_case = legacy.pop("cases")[0]
    legacy.pop("comparisonUnit")
    legacy["faultInjection"] = first_case["faultInjection"]
    legacy["expected"] = {"observations": first_case["observations"]}
    legacy["comparisonUnit"] = []
    with pytest.raises(FailureScenarioContractError, match="キー"):
        _validate(legacy, routes)


def test_contract_checks_file_name_and_population(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """ファイル名と内部の scenarioId・version、母集合外の scenarioId を照合する。"""
    asset = _p1_asset(routes)
    with pytest.raises(FailureScenarioContractError, match="ファイル名"):
        validate_failure_scenario_contract("p1-crash-boundaries_v3.json", asset, routes)
    with pytest.raises(FailureScenarioContractError, match="版付け"):
        validate_failure_scenario_contract("P1_v2.json", asset, routes)
    asset["scenarioId"] = "unknown-scenario"
    with pytest.raises(FailureScenarioContractError, match="母集合"):
        _validate(asset, routes)


@pytest.mark.parametrize("scenario_id", sorted(_BUILDERS))
def test_result_check_accepts_matching_results(
    scenario_id: str, routes: dict[ApplicationPath, tuple[str, ...]]
) -> None:
    """結果検査の正例: 省略したフィールドを除く実値が一致する。"""
    asset = _BUILDERS[scenario_id](routes)
    validate_failure_scenario_result(asset, _result_from(asset), routes)


def test_result_check_is_separate_from_the_contract_check(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """結果に実値の欠落・省略の混入・未知のフィールド・値の不一致があれば不合格。"""
    asset = _p1_asset(routes)
    valid = _result_from(asset)

    missing = copy.deepcopy(valid)
    del missing["cases"][0]["observations"][0]["fields"]["prefix"]
    omitted_present = copy.deepcopy(valid)
    omitted_present["cases"][0]["observations"][0]["fields"]["queue"] = {"count": 0}
    omitted_marker = copy.deepcopy(valid)
    omitted_marker["cases"][0]["observations"][0]["fields"]["prefix"] = _omit()
    unknown = copy.deepcopy(valid)
    unknown["cases"][0]["observations"][0]["fields"]["extraPersistence"] = True
    different = copy.deepcopy(valid)
    different["cases"][0]["observations"][0]["fields"]["d1"] = {"observed": "other"}
    reordered = copy.deepcopy(valid)
    reordered["cases"].reverse()
    for result in (
        missing,
        omitted_present,
        omitted_marker,
        unknown,
        different,
        reordered,
    ):
        with pytest.raises(FailureScenarioContractError):
            validate_failure_scenario_result(asset, result, routes)


def test_result_check_rejects_a_single_flipped_t_element(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """部分確定の変異: 結果の T 要素を 1 つだけ反転すると不合格になる。"""
    asset = _p1_asset(routes)
    for element in routes["P1"]:
        result = _result_from(asset)
        commitment = result["cases"][0]["observations"][0]["fields"][
            "tElementCommitment"
        ]
        units = T_ELEMENT_UNITS.get(("P1", element))
        if units is None:
            commitment[element] = "committed"
        else:
            commitment[element][units[0]] = "committed"
        with pytest.raises(FailureScenarioContractError, match="部分確定"):
            validate_failure_scenario_result(asset, result, routes)


def test_result_check_compares_hook_calls_with_reachability(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """到達しない注入点の呼び出しは 0 回、到達する注入点は 1 回以上。"""
    asset = _b3b_asset(routes)
    result = _result_from(asset)
    result["cases"][0]["hookCalls"] = 1
    with pytest.raises(FailureScenarioContractError, match="到達しない"):
        validate_failure_scenario_result(asset, result, routes)

    asset = _p1_asset(routes)
    result = _result_from(asset)
    result["cases"][0]["hookCalls"] = 0
    with pytest.raises(FailureScenarioContractError, match="到達する"):
        validate_failure_scenario_result(asset, result, routes)


def test_population_is_an_exact_set_of_pairs() -> None:
    """母集合: 26 組・観点 22 種・scenarioId 26 件、作成 16 件と繰り延べ 10 件。"""
    validate_population()
    assert len(OBSERVATION_SCENARIO_PAIRS) == 26
    assert len(OBSERVATION_KEYS) == 22
    assert len(OWNED_SCENARIO_IDS) == 16
    assert len(DEFERRED_SCENARIO_IDS) == 10
    assert all(
        scenario_id.startswith("restore-") for scenario_id in DEFERRED_SCENARIO_IDS
    )


def test_population_rejects_each_single_mutation() -> None:
    """組の削除・付け替え・観点の欠落・作成と繰り延べの重複・欠落をいずれも拒否する。"""
    pairs = list(OBSERVATION_SCENARIO_PAIRS)
    with pytest.raises(FailureScenarioContractError):
        validate_population(pairs[1:])
    moved = [
        ("p2", "p1-crash-boundaries") if pair[0] == "p1" else pair for pair in pairs
    ]
    with pytest.raises(FailureScenarioContractError):
        validate_population(moved)
    with pytest.raises(FailureScenarioContractError):
        validate_population(pairs, OBSERVATION_KEYS - {"p1"})
    with pytest.raises(FailureScenarioContractError):
        validate_population(
            pairs, OBSERVATION_KEYS, OWNED_SCENARIO_IDS | {"restore-commit-race"}
        )
    with pytest.raises(FailureScenarioContractError):
        validate_population(
            pairs, OBSERVATION_KEYS, OWNED_SCENARIO_IDS - {"b3b-after-gap"}
        )
    with pytest.raises(FailureScenarioContractError):
        validate_population(
            pairs,
            OBSERVATION_KEYS,
            OWNED_SCENARIO_IDS,
            {**DEFERRED_SCENARIO_IDS, "restore-commit-race": " "},
        )


def test_injection_coverage_is_an_exact_set(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """注入被覆: トランザクション内 18 組と、トランザクション外の 3 注入点。"""
    validate_injection_coverage(routes)
    assert set().union(*OUT_OF_TRANSACTION_INJECTION_COVERAGE.values()) == set(
        OUT_OF_TRANSACTION_POINTS
    )


def test_injection_coverage_rejects_each_single_mutation(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """注入被覆: 1 組・1 点の欠落、被覆と繰り延べの重複、本単位外の宣言を拒否する。"""
    dropped = dict(TRANSACTION_INJECTION_COVERAGE)
    dropped["p2-crash-boundaries"] = dropped["p2-crash-boundaries"] - {("P2", "T5")}
    with pytest.raises(FailureScenarioContractError, match="R-TXN-ROUTE"):
        validate_injection_coverage(routes, dropped)
    with pytest.raises(FailureScenarioContractError, match="両方"):
        validate_injection_coverage(
            routes,
            TRANSACTION_INJECTION_COVERAGE,
            {("P4", "T8"): "U-R1(TSK-392)"},
        )
    out_dropped = dict(OUT_OF_TRANSACTION_INJECTION_COVERAGE)
    del out_dropped["p3-invalidation-consumed-before-complete"]
    with pytest.raises(FailureScenarioContractError, match="3 注入点"):
        validate_injection_coverage(
            routes, TRANSACTION_INJECTION_COVERAGE, {}, out_dropped
        )
    validate_injection_coverage(
        routes,
        TRANSACTION_INJECTION_COVERAGE,
        {},
        out_dropped,
        {"消費側反映後・配信完了記録前": "繰り延べ先"},
    )
    with pytest.raises(FailureScenarioContractError, match="両方"):
        validate_injection_coverage(
            routes,
            TRANSACTION_INJECTION_COVERAGE,
            {},
            OUT_OF_TRANSACTION_INJECTION_COVERAGE,
            {"消費側反映後・配信完了記録前": "繰り延べ先"},
        )
    with pytest.raises(FailureScenarioContractError, match="本単位"):
        validate_injection_coverage(
            routes,
            {**TRANSACTION_INJECTION_COVERAGE, "restore-commit-race": frozenset()},
        )


def test_declared_coverage_matches_the_assets_cases(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """資産が宣言した到達する注入とトランザクション外注入点を読み出せる。"""
    assert (
        reached_transaction_pairs(_p1_asset(routes))
        == (TRANSACTION_INJECTION_COVERAGE["p1-crash-boundaries"])
    )
    assert reached_transaction_pairs(_b3b_asset(routes)) == frozenset()
    assert (
        reached_transaction_pairs(_b3a_asset(routes))
        == (TRANSACTION_INJECTION_COVERAGE["p5-b3a-crash-boundaries"])
    )
    assert out_of_transaction_points(_p3_asset(routes)) == frozenset(
        {"T7 確定後・無効化配信前"}
    )


_FIXTURE_DIRECTORY = _REPOSITORY_ROOT / "tests" / "fixtures" / "sync-protocol-failures"
_FRONTEND_CONTRACT = (
    _REPOSITORY_ROOT
    / "frontend"
    / "src"
    / "lib"
    / "sync"
    / "failureScenarioContract.ts"
)


def _fixture_assets() -> list[tuple[str, Any]]:
    return [
        (path.name, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(_FIXTURE_DIRECTORY.glob("*.json"))
    ]


def test_every_fixture_passes_the_contract_check(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """実在する資産すべてが契約検査を通り、本単位の 16 件と過不足なく一致する。"""
    assets = _fixture_assets()
    assert assets
    scenario_ids = [
        validate_failure_scenario_contract(name, asset, routes)["scenarioId"]
        for name, asset in assets
    ]
    assert len(scenario_ids) == len(set(scenario_ids))
    assert set(scenario_ids) == OWNED_SCENARIO_IDS
    client_ids = {
        asset["scenarioId"]
        for _, asset in assets
        if _is_omitted(asset["input"]["applicationPath"])
    }
    assert client_ids == {
        "multi-tab-single-writer",
        "leader-freeze-reelection",
        "waiting-input-not-accepted",
        "durable-append-failure",
    }


def _typescript_string_array(source: str, name: str) -> tuple[str, ...]:
    match = re.search(
        rf"export const {name} = \[(?P<body>[^\]]*)\]", source, flags=re.S
    )
    assert match is not None, name
    return tuple(re.findall(r"'([^']+)'", match.group("body")))


def test_frontend_contract_shares_the_expected_field_tables() -> None:
    """消費側の frontend と期待フィールドの表を二重に持つので、食い違いを検出する。"""
    source = _FRONTEND_CONTRACT.read_text(encoding="utf-8")
    assert (
        _typescript_string_array(source, "FAILURE_EXPECTED_FIELD_IDS")
        == COMMON_EXPECTED_FIELD_IDS
    )
    client_required = _typescript_string_array(source, "CLIENT_REQUIRED_FIELD_IDS")
    assert (
        set(client_required)
        == set(COMMON_EXPECTED_FIELD_IDS) - (OMITTABLE_FIELD_IDS[None])
    )
    assert re.search(
        rf"export const FAILURE_SCENARIO_SCHEMA_VERSION = {SCHEMA_VERSION}\b", source
    )


def test_declared_coverage_equals_the_fixtures_cases(
    routes: dict[ApplicationPath, tuple[str, ...]],
) -> None:
    """宣言した注入被覆が、実在する資産の case から読んだ被覆と一致する。"""
    transaction: dict[str, frozenset[tuple[str, str]]] = {}
    out_of_transaction: dict[str, frozenset[str]] = {}
    for name, asset in _fixture_assets():
        validate_failure_scenario_contract(name, asset, routes)
        if pairs := reached_transaction_pairs(asset):
            transaction[asset["scenarioId"]] = pairs
        if points := out_of_transaction_points(asset):
            out_of_transaction[asset["scenarioId"]] = points
    assert transaction == dict(TRANSACTION_INJECTION_COVERAGE)
    assert out_of_transaction == dict(OUT_OF_TRANSACTION_INJECTION_COVERAGE)
    validate_injection_coverage(routes, transaction, {}, out_of_transaction, {})
