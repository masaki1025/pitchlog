"""等価変異台帳を検査し、既存変異エンジンへ承認 ID を渡す。

`ADR-003 D-11 変異テスト規則` に従い、台帳にない mutant は非等価とする。
固定小数 scale 0 の formatter 迂回は、要求 case の全実行・表示の完全一致・
有効な kill 証跡の不在を実測し、PO の台帳行がある場合だけ除外できる。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import cast

from pitchlog.domainmut.scope import (
    CalculationGraph,
    ChangeKind,
    MutationScopePlan,
    SemanticChange,
    resolve_mutation_scope,
)

AUTHORITY_ID = "ADR-003 D-11 変異テスト規則"
LEDGER_PATH = "backend/domain/mutation-equivalents.json"

_TOP_LEVEL_KEYS = frozenset(
    {"schemaVersion", "authorityId", "operatingPolicy", "entries"}
)
_POLICY_KEYS = frozenset(
    {"unrecordedDisposition", "requiredJudge", "scaleZeroFormatterBypass"}
)
_BYPASS_KEYS = frozenset(
    {"candidate", "requiredObservations", "decision"}
)
_CANDIDATE_KEYS = frozenset(
    {"operatorId", "primitiveKind", "scale", "replacementRoute"}
)
_OBSERVATION_KEYS = frozenset({"id", "description"})
_DECISION_KEYS = frozenset({"equivalentWhen", "nonEquivalentWhen"})
_ENTRY_KEYS = frozenset({"mutantId", "reason", "judge", "decisionDate"})
_REQUIRED_OBSERVATION_IDS = frozenset(
    {
        "all-required-cases-executed",
        "outputs-exactly-equal",
        "valid-kill-evidence-absent",
    }
)
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")


class EquivalenceLedgerError(Exception):
    """等価変異台帳または判定材料が契約に適合しないことを表す。"""


class EquivalenceDisposition(StrEnum):
    """実測と PO 記録から一意に得られる二つの扱い。"""

    APPROVED_EQUIVALENT = "approved-equivalent"
    NON_EQUIVALENT = "non-equivalent"


@dataclass(frozen=True, slots=True)
class EquivalentMutationRecord:
    """PO が等価と判定した一 mutant の記録。"""

    mutant_id: str
    reason: str
    judge: str
    decision_date: date


@dataclass(frozen=True, slots=True)
class EquivalenceLedger:
    """検査済みの等価変異台帳。"""

    authority_id: str
    entries: tuple[EquivalentMutationRecord, ...]

    @property
    def approved_ids(self) -> frozenset[str]:
        """既存変異エンジンへ渡す承認済み mutant ID を返す。"""
        return frozenset(entry.mutant_id for entry in self.entries)

    def is_approved(self, mutant_id: str) -> bool:
        """台帳行がある場合だけ等価承認済みと返す。"""
        return mutant_id in self.approved_ids


@dataclass(frozen=True, slots=True)
class ScaleZeroFormatterObservation:
    """固定小数 scale 0 の formatter 迂回に対する実測。

    Attributes:
        mutant_id: 表示系演算子が生成した mutant ID。
        operator_id: 適用した表示系演算子 ID。
        primitive_kind: 迂回対象の表示 primitive 種別。
        scale: 宣言された固定小数の scale。
        replacement_route: formatter を置換した経路。
        required_case_ids: 判定に必要な case の母集合。
        executed_case_ids: 実際に双方を実行した case 集合。
        matching_case_ids: 表示が完全一致した case 集合。
        valid_kill_evidence_ids: hash 以外の有効な kill 証跡 ID。
    """

    mutant_id: str
    operator_id: str
    primitive_kind: str
    scale: int
    replacement_route: str
    required_case_ids: frozenset[str]
    executed_case_ids: frozenset[str]
    matching_case_ids: frozenset[str]
    valid_kill_evidence_ids: frozenset[str]

    def __post_init__(self) -> None:
        """要求 case 集合が閉じ、判定の母集合が空でないことを検査する。"""
        _require_identifier(self.mutant_id, "mutantId")
        if not self.required_case_ids:
            raise ValueError("scale 0 の要求 case 集合が空")
        if not self.executed_case_ids <= self.required_case_ids:
            raise ValueError("実行 case に要求集合外の ID がある")
        if not self.matching_case_ids <= self.executed_case_ids:
            raise ValueError("一致 case に未実行の ID がある")

    @property
    def is_candidate(self) -> bool:
        """台帳規約が扱う scale 0 の言語既定文字列化なら真を返す。"""
        return (
            self.operator_id == "display-formatter-invocation"
            and self.primitive_kind == "fixed-decimal"
            and self.scale == 0
            and self.replacement_route
            == "language-default-stringification"
        )

    @property
    def observations_pass(self) -> bool:
        """三つの必須観測がすべて成立した場合だけ真を返す。"""
        return (
            self.required_case_ids == self.executed_case_ids
            and self.required_case_ids == self.matching_case_ids
            and not self.valid_kill_evidence_ids
        )


def _require_object(value: object, label: str) -> Mapping[str, object]:
    """文字列キーの object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise EquivalenceLedgerError(f"{label} が object でない")
    return cast(Mapping[str, object], value)


def _require_array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise EquivalenceLedgerError(f"{label} が array でない")
    return cast(list[object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    """未知キーと欠落キーを両方向の集合差で拒否する。"""
    actual = set(value)
    missing = expected - actual
    unknown = actual - expected
    if missing or unknown:
        raise EquivalenceLedgerError(
            f"{label} のキー集合が不正: missing={sorted(missing)!r}, "
            f"unknown={sorted(unknown)!r}"
        )


def _require_string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise EquivalenceLedgerError(f"{label} が空でない文字列でない")
    return value


def _require_identifier(value: object, label: str) -> str:
    """変異エンジンと同じ閉じた文字種の ID を返す。"""
    identifier = _require_string(value, label)
    if _IDENTIFIER.fullmatch(identifier) is None:
        raise EquivalenceLedgerError(f"{label} が不正: {identifier}")
    return identifier


def _validate_policy(value: object) -> None:
    """未記録の扱いと scale 0 の判定手順を検査する。"""
    policy = _require_object(value, "operatingPolicy")
    _require_exact_keys(policy, _POLICY_KEYS, "operatingPolicy")
    if policy["unrecordedDisposition"] != "non-equivalent":
        raise EquivalenceLedgerError("未記録が非等価扱いでない")
    if policy["requiredJudge"] != "PO":
        raise EquivalenceLedgerError("台帳の必須判定者が PO でない")

    bypass = _require_object(
        policy["scaleZeroFormatterBypass"],
        "scaleZeroFormatterBypass",
    )
    _require_exact_keys(bypass, _BYPASS_KEYS, "scaleZeroFormatterBypass")
    candidate = _require_object(bypass["candidate"], "candidate")
    _require_exact_keys(candidate, _CANDIDATE_KEYS, "candidate")
    expected_candidate = {
        "operatorId": "display-formatter-invocation",
        "primitiveKind": "fixed-decimal",
        "scale": 0,
        "replacementRoute": "language-default-stringification",
    }
    if candidate != expected_candidate:
        raise EquivalenceLedgerError("scale 0 の等価候補条件が不正")

    observations = _require_array(
        bypass["requiredObservations"],
        "requiredObservations",
    )
    observation_ids: list[str] = []
    for index, raw_observation in enumerate(observations):
        observation = _require_object(
            raw_observation,
            f"requiredObservations[{index}]",
        )
        _require_exact_keys(
            observation,
            _OBSERVATION_KEYS,
            f"requiredObservations[{index}]",
        )
        observation_ids.append(
            _require_identifier(observation["id"], "observation.id")
        )
        _require_string(observation["description"], "observation.description")
    if len(observation_ids) != len(set(observation_ids)):
        raise EquivalenceLedgerError("requiredObservations の ID が重複")
    if set(observation_ids) != _REQUIRED_OBSERVATION_IDS:
        raise EquivalenceLedgerError("scale 0 の必須観測が過不足")

    decision = _require_object(bypass["decision"], "decision")
    _require_exact_keys(decision, _DECISION_KEYS, "decision")
    if decision != {
        "equivalentWhen": "all-observations-pass-and-po-entry-exists",
        "nonEquivalentWhen": "any-observation-fails-or-po-entry-absent",
    }:
        raise EquivalenceLedgerError("scale 0 の決定規則が不正")


def _entry(value: object, index: int) -> EquivalentMutationRecord:
    """一行を厳密キーの検査済み記録へ変換する。"""
    entry = _require_object(value, f"entries[{index}]")
    _require_exact_keys(entry, _ENTRY_KEYS, f"entries[{index}]")
    mutant_id = _require_identifier(entry["mutantId"], "mutantId")
    reason = _require_string(entry["reason"], "reason")
    judge = _require_string(entry["judge"], "judge")
    if judge != "PO":
        raise EquivalenceLedgerError("等価変異の判定者が PO でない")
    raw_date = _require_string(entry["decisionDate"], "decisionDate")
    try:
        decision_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise EquivalenceLedgerError("decisionDate が ISO 日付でない") from error
    if decision_date.isoformat() != raw_date:
        raise EquivalenceLedgerError("decisionDate が標準 ISO 日付でない")
    return EquivalentMutationRecord(mutant_id, reason, judge, decision_date)


def validate_equivalence_ledger(document: object) -> EquivalenceLedger:
    """台帳全体の厳密キー・運用規約・PO 記録を検査する。"""
    root = _require_object(document, "ledger")
    _require_exact_keys(root, _TOP_LEVEL_KEYS, "ledger")
    if type(root["schemaVersion"]) is not int or root["schemaVersion"] != 1:
        raise EquivalenceLedgerError("schemaVersion が 1 でない")
    if root["authorityId"] != AUTHORITY_ID:
        raise EquivalenceLedgerError("authorityId が不正")
    _validate_policy(root["operatingPolicy"])
    entries = tuple(
        _entry(value, index)
        for index, value in enumerate(_require_array(root["entries"], "entries"))
    )
    ids = [entry.mutant_id for entry in entries]
    if len(ids) != len(set(ids)):
        raise EquivalenceLedgerError("mutantId が重複")
    return EquivalenceLedger(AUTHORITY_ID, entries)


def load_equivalence_ledger(path: Path) -> EquivalenceLedger:
    """JSON 資産を読み、検査済み台帳を返す。

    Args:
        path: 等価変異台帳のパス。

    Returns:
        厳密に検査した台帳。

    Raises:
        EquivalenceLedgerError: 読み取り・JSON・契約のいずれかが不正な場合。
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EquivalenceLedgerError("等価変異台帳を読めない") from error
    return validate_equivalence_ledger(document)


def classify_scale_zero_formatter_bypass(
    observation: ScaleZeroFormatterObservation,
    ledger: EquivalenceLedger,
) -> EquivalenceDisposition:
    """実測と PO 記録を使って scale 0 の扱いを一意に返す。

    台帳行があっても必須観測が不成立なら、kill と等価の二重判定にせず
    不正な承認として fail する。台帳行が無い候補は常に非等価である。

    Args:
        observation: 生成した formatter 迂回 mutant の実測。
        ledger: 検査済みの PO 台帳。

    Returns:
        承認済み等価または非等価の一意な扱い。

    Raises:
        EquivalenceLedgerError: 実測不成立の mutant が承認済みの場合。
    """
    approved = ledger.is_approved(observation.mutant_id)
    measured_equivalent = (
        observation.is_candidate and observation.observations_pass
    )
    if approved and not measured_equivalent:
        raise EquivalenceLedgerError("実測不成立の mutant が等価承認されている")
    if approved and measured_equivalent:
        return EquivalenceDisposition.APPROVED_EQUIVALENT
    return EquivalenceDisposition.NON_EQUIVALENT


def resolve_ledger_change_scope(
    graph: CalculationGraph,
) -> MutationScopePlan:
    """台帳改変をステップ 42 の既存解決器で全面発火へ変換する。"""
    return resolve_mutation_scope(
        (SemanticChange(ChangeKind.EQUIVALENCE_LEDGER),),
        graph,
    )


__all__ = [
    "AUTHORITY_ID",
    "LEDGER_PATH",
    "EquivalenceDisposition",
    "EquivalenceLedger",
    "EquivalenceLedgerError",
    "EquivalentMutationRecord",
    "ScaleZeroFormatterObservation",
    "classify_scale_zero_formatter_bypass",
    "load_equivalence_ledger",
    "resolve_ledger_change_scope",
    "validate_equivalence_ledger",
]
