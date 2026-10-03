"""テストランナーの出力から層別の実行証跡を独立収集する。

必須 5 項目は `ADR-003 D-11 ③ 宣言された構成の完全性` の、
プロパティ層の証跡 schema を固定する文から導出する。同条項が列挙する
`calculation` / `propertyId` / `propertyKind` / `generatedCases` / `status`
以外を推測で加えず、この 5 項目を欠くテストは実行済みに数えない。
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

REQUIRED_LAYER_PROPERTIES = frozenset(
    {
        "calculation",
        "propertyId",
        "propertyKind",
        "generatedCases",
        "status",
    }
)
_TRACE_FIELDS = frozenset(
    {
        "vector",
        "case",
        "entrypointId",
        "directTargetId",
        "expected",
        "entrypointOutput",
        "directTargetOutput",
        "artifactHashes",
        "issuedSqlOrAst",
        "stageIO",
    }
)
_STAGE_IO_FIELDS = frozenset({"stage", "artifactHash", "input", "output"})
_PROPERTY_KINDS = frozenset({"invariant", "equivalence"})
_PASSED = "passed"


class CollectionError(Exception):
    """ランナー出力の形式が判定不能であることを表す。"""


class Runner(StrEnum):
    """証跡を独立採取できるテストランナー。"""

    PYTEST = "pytest"
    VITEST = "vitest"


@dataclass(frozen=True, slots=True)
class StageExpectation:
    """Composite の一段に期待する名前と生成物 hash。

    Attributes:
        stage: 順序付きの段名。
        artifact_hash: 宣言済み生成物の内容 hash。
    """

    stage: str
    artifact_hash: str


@dataclass(frozen=True, slots=True)
class TargetExpectation:
    """直接呼び出し対象の構成を収集器へ与える期待値。

    Attributes:
        calculation: 対象計算 ID。
        direct_target_id: Direct target ID。
        kind: `single` または `composite`。
        stages: 宣言順の段と hash。
    """

    calculation: str
    direct_target_id: str
    kind: str
    stages: tuple[StageExpectation, ...]

    def __post_init__(self) -> None:
        """不正な target 期待値を早期に拒否する。"""
        if self.kind not in {"single", "composite"}:
            raise ValueError(f"未知の target kind: {self.kind}")
        minimum = 2 if self.kind == "composite" else 1
        maximum = None if self.kind == "composite" else 1
        if len(self.stages) < minimum or (
            maximum is not None and len(self.stages) > maximum
        ):
            raise ValueError(f"{self.kind} の段数が不正: {len(self.stages)}")


@dataclass(frozen=True, slots=True)
class RunnerProvenance:
    """証跡を取り出したランナー文書の由来。

    Attributes:
        runner: 入力文書のランナー。
        source_format: JUnit XML または reporter JSON。
        source_hash: 入力文書全体の SHA-256。
        test_id: 文書内でランナーが付与したテスト識別子。
    """

    runner: Runner
    source_format: str
    source_hash: str
    test_id: str


@dataclass(frozen=True, slots=True)
class FiveJudgments:
    """収集器が生値から独立計算した経路一致の 5 判定。

    Attributes:
        entrypoint_executed: 製品入口の生出力が提出された。
        direct_target_executed: 正本生成物側の生出力が提出された。
        entrypoint_equals_expected: 製品入口出力が期待値と一致した。
        direct_target_equals_expected: 直接対象出力が期待値と一致した。
        paths_equal: 両経路の生出力が一致した。
    """

    entrypoint_executed: bool
    direct_target_executed: bool
    entrypoint_equals_expected: bool
    direct_target_equals_expected: bool
    paths_equal: bool

    @property
    def complete(self) -> bool:
        """5 判定がすべて成立した場合だけ真を返す。"""
        return all(
            (
                self.entrypoint_executed,
                self.direct_target_executed,
                self.entrypoint_equals_expected,
                self.direct_target_equals_expected,
                self.paths_equal,
            )
        )


@dataclass(frozen=True, slots=True)
class LayerEvidence:
    """完走した一テストから独立収集した実行証跡。

    Attributes:
        calculation: 対象計算 ID。
        property_id: プロパティ ID。
        property_kind: 不変条件または等価性。
        generated_cases: 実際に生成した case 数。
        status: ランナー出力と一致した完走状態。
        vector: ベクタ ID。
        case: Case ID。
        entrypoint_id: 製品入口 ID。
        direct_target_id: Direct target ID。
        judgments: 生の三値から収集器が計算した 5 判定。
        artifact_hashes_valid: 実行 artifact hash の突合結果。
        stage_chain_valid: 段別出力と次段入力の値連鎖検証結果。
        provenance: 元のランナー文書へ戻れる生成由来。
    """

    calculation: str
    property_id: str
    property_kind: str
    generated_cases: int
    status: str
    vector: str
    case: str
    entrypoint_id: str
    direct_target_id: str
    judgments: FiveJudgments
    artifact_hashes_valid: bool
    stage_chain_valid: bool
    provenance: RunnerProvenance

    @property
    def complete(self) -> bool:
        """5 判定・hash・値連鎖がすべて成立した場合だけ真を返す。"""
        return (
            self.judgments.complete
            and self.artifact_hashes_valid
            and self.stage_chain_valid
        )


@dataclass(frozen=True, slots=True)
class RejectedEvidence:
    """実行済みに数えなかったテストと理由。

    Attributes:
        test_id: ランナー文書内のテスト識別子。
        reason: 除外した機械可読な理由。
    """

    test_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """一つのランナー文書を収集した結果。

    Attributes:
        evidence: 実行済みとして採取できた証跡。
        rejected: 実行済みに数えなかった提出。
    """

    evidence: tuple[LayerEvidence, ...]
    rejected: tuple[RejectedEvidence, ...]

    @property
    def executed_count(self) -> int:
        """実行済みとして採取したテスト数を返す。"""
        return len(self.evidence)

    @property
    def complete(self) -> bool:
        """有効な証跡があり、不成立も除外もない場合だけ真を返す。"""
        return (
            bool(self.evidence)
            and not self.rejected
            and all(item.complete for item in self.evidence)
        )


ExpectationIndex = Mapping[tuple[str, str], TargetExpectation]


def _read_bytes(path: Path) -> bytes:
    """ランナー出力を byte 列として読み込む。"""
    try:
        return path.read_bytes()
    except OSError as error:
        raise CollectionError(f"ランナー出力を読めない: {path}: {error}") from error


def _source_hash(content: bytes) -> str:
    """ランナー文書全体の SHA-256 を返す。"""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーの JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CollectionError(f"{label} が object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise CollectionError(f"{label} が array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CollectionError(f"{label} が空でない文字列でない")
    return value


def _json_value(value: str, label: str) -> object:
    """文字列に埋め込まれた JSON 値を復号する。"""
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise CollectionError(f"{label} が JSON でない: {error}") from error


def _generated_cases(value: object) -> int | None:
    """Boolean を除く非負整数表現を解釈する。"""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if str(parsed) == value else None
    return None


def _trace(value: object) -> dict[str, object]:
    """Runner property の trace を厳密キー集合で読み取る。"""
    if isinstance(value, str):
        value = _json_value(value, "trace")
    trace = _object(value, "trace")
    observed = frozenset(trace)
    if observed != _TRACE_FIELDS:
        missing = sorted(_TRACE_FIELDS - observed)
        unexpected = sorted(observed - _TRACE_FIELDS)
        raise CollectionError(
            f"trace のキー集合が不正: missing={missing!r}, unexpected={unexpected!r}"
        )
    return trace


def _properties_from_junit(testcase: ET.Element) -> dict[str, object]:
    """Pytest testcase の JUnit properties を一意に読み取る。"""
    properties: dict[str, object] = {}
    container = testcase.find("properties")
    if container is None:
        return properties
    for item in container.findall("property"):
        name = item.get("name")
        if name is None or not name:
            raise CollectionError("JUnit property の name が空")
        if name in properties:
            raise CollectionError(f"JUnit property が重複: {name}")
        properties[name] = item.get("value", item.text or "")
    return properties


def _junit_state(testcase: ET.Element) -> str:
    """JUnit testcase の native 状態を自己申告と独立に導出する。"""
    skipped = testcase.find("skipped")
    if skipped is not None:
        marker = " ".join(
            filter(
                None,
                (skipped.get("type"), skipped.get("message"), skipped.text),
            )
        ).lower()
        return "xfail" if "xfail" in marker else "skip"
    if testcase.find("failure") is not None or testcase.find("error") is not None:
        return "failed"
    return _PASSED


def _provenance(
    runner: Runner,
    source_format: str,
    source_hash: str,
    test_id: str,
) -> RunnerProvenance:
    """ランナー文書の生成元情報を構築する。"""
    return RunnerProvenance(runner, source_format, source_hash, test_id)


def _validate_stage_io(
    trace: Mapping[str, object],
    expectation: TargetExpectation,
) -> tuple[bool, bool]:
    """生成物 hash と composite の段別値連鎖を独立検証する。"""
    hashes = _object(trace.get("artifactHashes"), "trace.artifactHashes")
    expected_hashes = {stage.stage: stage.artifact_hash for stage in expectation.stages}
    hashes_valid = hashes == expected_hashes
    raw_stage_io = _array(trace.get("stageIO"), "trace.stageIO")
    if expectation.kind == "single":
        return hashes_valid, not raw_stage_io
    if len(raw_stage_io) != len(expectation.stages):
        return hashes_valid, False

    stage_io: list[dict[str, object]] = []
    for index, raw_item in enumerate(raw_stage_io):
        item = _object(raw_item, f"trace.stageIO[{index}]")
        if frozenset(item) != _STAGE_IO_FIELDS:
            return hashes_valid, False
        stage_io.append(item)
    stages_match = all(
        item.get("stage") == expected.stage
        and item.get("artifactHash") == expected.artifact_hash
        for item, expected in zip(stage_io, expectation.stages, strict=True)
    )
    links_match = all(
        current.get("output") == following.get("input")
        for current, following in zip(stage_io, stage_io[1:])
    )
    final_matches = stage_io[-1].get("output") == trace.get("directTargetOutput")
    return hashes_valid, stages_match and links_match and final_matches


def _collect_one(
    *,
    test_id: str,
    native_state: str,
    properties: Mapping[str, object],
    provenance: RunnerProvenance,
    expectations: ExpectationIndex,
) -> LayerEvidence | RejectedEvidence:
    """一つの runner test を証跡または除外理由へ変換する。"""
    if native_state in {"skip", "xfail", "todo"}:
        return RejectedEvidence(test_id, native_state)
    if native_state != _PASSED:
        return RejectedEvidence(test_id, f"runner-status:{native_state}")
    missing = REQUIRED_LAYER_PROPERTIES - frozenset(properties)
    if missing:
        return RejectedEvidence(
            test_id,
            f"missing-properties:{','.join(sorted(missing))}",
        )

    try:
        calculation = _string(properties.get("calculation"), "calculation")
        property_id = _string(properties.get("propertyId"), "propertyId")
        property_kind = _string(properties.get("propertyKind"), "propertyKind")
        status = _string(properties.get("status"), "status")
        generated_cases = _generated_cases(properties.get("generatedCases"))
        trace = _trace(properties.get("trace"))
        vector = _string(trace.get("vector"), "trace.vector")
        case = _string(trace.get("case"), "trace.case")
        entrypoint_id = _string(trace.get("entrypointId"), "trace.entrypointId")
        direct_target_id = _string(trace.get("directTargetId"), "trace.directTargetId")
    except CollectionError as error:
        return RejectedEvidence(test_id, f"invalid-evidence:{error}")

    if property_kind not in _PROPERTY_KINDS:
        return RejectedEvidence(test_id, f"property-kind:{property_kind}")
    if status != native_state:
        return RejectedEvidence(test_id, "status-mismatch")
    if generated_cases is None:
        return RejectedEvidence(test_id, "generated-cases-invalid")
    if generated_cases == 0:
        return RejectedEvidence(test_id, "zero-generated-cases")
    if generated_cases < 0:
        return RejectedEvidence(test_id, "generated-cases-invalid")

    expectation = expectations.get((calculation, direct_target_id))
    if expectation is None:
        return RejectedEvidence(test_id, "unknown-direct-target")
    try:
        hashes_valid, chain_valid = _validate_stage_io(trace, expectation)
    except CollectionError as error:
        return RejectedEvidence(test_id, f"invalid-stage-evidence:{error}")
    expected = trace.get("expected")
    entrypoint_output = trace.get("entrypointOutput")
    direct_target_output = trace.get("directTargetOutput")
    judgments = FiveJudgments(
        entrypoint_executed=True,
        direct_target_executed=True,
        entrypoint_equals_expected=entrypoint_output == expected,
        direct_target_equals_expected=direct_target_output == expected,
        paths_equal=entrypoint_output == direct_target_output,
    )
    return LayerEvidence(
        calculation=calculation,
        property_id=property_id,
        property_kind=property_kind,
        generated_cases=generated_cases,
        status=status,
        vector=vector,
        case=case,
        entrypoint_id=entrypoint_id,
        direct_target_id=direct_target_id,
        judgments=judgments,
        artifact_hashes_valid=hashes_valid,
        stage_chain_valid=chain_valid,
        provenance=provenance,
    )


def collect_pytest_junit(
    path: Path,
    expectations: ExpectationIndex,
) -> CollectionResult:
    """Pytest の JUnit XML properties から証跡を採取する。

    Args:
        path: Pytest が `--junitxml` で生成した XML。
        expectations: 宣言された direct target の段と hash。

    Returns:
        実行済み証跡と除外理由。

    Raises:
        CollectionError: Pytest JUnit XML として解析できない場合。
    """
    content = _read_bytes(path)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise CollectionError(f"JUnit XML を解析できない: {error}") from error
    if root.tag != "testsuites" or not root.get("name", "").startswith("pytest"):
        raise CollectionError("Pytest JUnit XML の生成元 marker がない")
    suites = root.findall("testsuite")
    if not suites or any(suite.get("name") != "pytest" for suite in suites):
        raise CollectionError("Pytest testsuite の生成元 marker がない")

    digest = _source_hash(content)
    evidence: list[LayerEvidence] = []
    rejected: list[RejectedEvidence] = []
    for suite in suites:
        for testcase in suite.findall("testcase"):
            classname = testcase.get("classname", "")
            name = testcase.get("name", "")
            test_id = f"{classname}::{name}" if classname else name
            result = _collect_one(
                test_id=test_id,
                native_state=_junit_state(testcase),
                properties=_properties_from_junit(testcase),
                provenance=_provenance(
                    Runner.PYTEST,
                    "junit-xml",
                    digest,
                    test_id,
                ),
                expectations=expectations,
            )
            if isinstance(result, LayerEvidence):
                evidence.append(result)
            else:
                rejected.append(result)
    return CollectionResult(tuple(evidence), tuple(rejected))


def _vitest_envelope(document: object) -> list[dict[str, object]]:
    """Vitest JSON reporter の標準 envelope から assertion を列挙する。"""
    root = _object(document, "Vitest reporter")
    marker_fields = {
        "numTotalTests",
        "numPassedTests",
        "numFailedTests",
        "numPendingTests",
        "numTodoTests",
        "testResults",
    }
    if not marker_fields <= set(root):
        raise CollectionError("Vitest reporter JSON の生成元 marker がない")
    assertions: list[dict[str, object]] = []
    for result_index, raw_result in enumerate(
        _array(root.get("testResults"), "testResults")
    ):
        result = _object(raw_result, f"testResults[{result_index}]")
        for assertion_index, raw_assertion in enumerate(
            _array(result.get("assertionResults"), "assertionResults")
        ):
            assertions.append(
                _object(
                    raw_assertion,
                    f"testResults[{result_index}].assertionResults[{assertion_index}]",
                )
            )
    return assertions


def collect_vitest_reporter(
    path: Path,
    expectations: ExpectationIndex,
) -> CollectionResult:
    """Vitest reporter JSON から証跡を採取する。

    Args:
        path: Vitest JSON reporter が生成した文書。
        expectations: 宣言された direct target の段と hash。

    Returns:
        実行済み証跡と除外理由。

    Raises:
        CollectionError: Vitest reporter JSON として解析できない場合。
    """
    content = _read_bytes(path)
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CollectionError(
            f"Vitest reporter JSON を解析できない: {error}"
        ) from error
    assertions = _vitest_envelope(document)
    digest = _source_hash(content)
    evidence: list[LayerEvidence] = []
    rejected: list[RejectedEvidence] = []
    for index, assertion in enumerate(assertions):
        test_id = _string(
            assertion.get("fullName", assertion.get("title")),
            f"assertionResults[{index}].fullName",
        )
        native_state = _string(
            assertion.get("status"),
            f"assertionResults[{index}].status",
        ).lower()
        meta = _object(assertion.get("meta"), f"assertionResults[{index}].meta")
        properties = _object(
            meta.get("pitchlog"),
            f"assertionResults[{index}].meta.pitchlog",
        )
        result = _collect_one(
            test_id=test_id,
            native_state=native_state,
            properties=properties,
            provenance=_provenance(
                Runner.VITEST,
                "vitest-reporter-json",
                digest,
                test_id,
            ),
            expectations=expectations,
        )
        if isinstance(result, LayerEvidence):
            evidence.append(result)
        else:
            rejected.append(result)
    return CollectionResult(tuple(evidence), tuple(rejected))


__all__ = [
    "REQUIRED_LAYER_PROPERTIES",
    "CollectionError",
    "CollectionResult",
    "FiveJudgments",
    "LayerEvidence",
    "RejectedEvidence",
    "Runner",
    "RunnerProvenance",
    "StageExpectation",
    "TargetExpectation",
    "collect_pytest_junit",
    "collect_vitest_reporter",
]
