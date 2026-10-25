"""付録 E のトップレベル宣言から runner 用 case を読み込む。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import cast

HANDOFF_PATH = "contracts/state-transition/appendix_e_consumer_handoff_v1.json"
DESCRIPTOR_PATH = "contracts/state-transition/input_axes_descriptor_v1.json"
CONTRACTS = {
    "state-transition": (
        "contracts/state-transition/state_transition_contract_v1.json",
        "state_transition_contract_v1",
        "/expected",
        frozenset(
            {
                "caseId",
                "rowRef",
                "inputCoordinate",
                "historyInput",
                "expected",
                "raw",
                "normalizationRuleId",
                "normalized",
            }
        ),
    ),
    "game-end": (
        "contracts/state-transition/game_end_contract_v1.json",
        "game_end_contract_v1",
        "/decision",
        frozenset(
            {
                "branchId",
                "caseId",
                "decision",
                "inputCoordinate",
                "normalizationRuleId",
                "normalized",
                "raw",
                "rowRef",
                "derivedSourceInput",
            }
        ),
    ),
}
DESCRIPTOR_ID = "pitchlog.input-axes"
DESCRIPTOR_VERSION = "input_axes_descriptor_v1"
DESCRIPTOR_SCHEMA_PATHS = (
    "contracts/state-transition/state_transition_contract_schema_v1.json",
    "contracts/state-transition/game_end_contract_schema_v1.json",
)
DEPENDENCY_OID = "b8fd5fe73e85ae80b3aa82b28bef7f2911f29b12"
DEPENDENCIES = {
    # 依存元の commit OID は出自として固定し、SHA-256 は現行の実資産を照合する。
    "backend/domain/history-depth.json": (
        "version",
        "sha256:933e41e9a717fe25f52575d7b34ca077904d4592f51173b56832c36963a31e97",
    ),
    "backend/domain/check-sets.json": (
        "schemaVersion",
        "sha256:c6bf9beeb86325c759f56abb50af060bf62b48323e50f9c1c1cfe5704cc7c18b",
    ),
    "backend/src/pitchlog/domaincheck/runners/vector_bridge.py": (
        None,
        "sha256:ba9263cdfb39118e95ec7b9df3ab2656db2ace990206c5bf3967fa0067fbbfff",
    ),
    "frontend/src/testing/vectorRunner.ts": (
        None,
        "sha256:b17eb6c8bc75f1677e038769e2d94b1280ee408fe16a93aa12dcaeb9abef6d06",
    ),
}
DEPENDENCY_ORIGINS = {
    "backend/domain/history-depth.json": ("TSK-235", DEPENDENCY_OID),
    "backend/domain/check-sets.json": ("TSK-235", DEPENDENCY_OID),
    "backend/src/pitchlog/domaincheck/runners/vector_bridge.py": (
        "TSK-455",
        "ee021d87e59f26d3afe4b01c7ea695866797f26f",
    ),
    "frontend/src/testing/vectorRunner.ts": (
        "TSK-455",
        "f8df3adabb2fe1c26b437149b0ec59c84c7f3d2e",
    ),
}
HANDOFF_KEYS = frozenset(
    {
        "handoffVersion",
        "calculationIds",
        "claimBoundary",
        "consumerBindings",
        "artifacts",
        "dependencies",
        "receiverDoD",
        "fr040Declaration",
        "descriptorParity",
        "consumptionVerification",
        "stage2EntryGate",
        "receiverTaskId",
    }
)
BINDING_KEYS = frozenset(
    {
        "calculationId",
        "vectorId",
        "contractPath",
        "version",
        "schemaVersion",
        "caseSchemaRef",
        "caseFieldMapping",
        "normalizationComparison",
        "outputComparison",
        "dPlusOnePolicy",
        "executionPaths",
    }
)
EXECUTION_PATH_KEYS = frozenset(
    {
        "runner",
        "runnerRevision",
        "normalizerId",
        "entrypointId",
        "directTargetId",
        "resolutionStage",
    }
)
PARITY_KEYS = frozenset(
    {
        "descriptorPath",
        "descriptorId",
        "projectionRulesPointer",
        "designPath",
        "designSection",
        "requirement",
        "verificationStage",
    }
)
DESCRIPTOR_KEYS = frozenset(
    {
        "descriptorId",
        "version",
        "digest",
        "digestSpec",
        "stage2ExternalConstraints",
        "inputCoordinateCoverage",
        "freezeBaseline",
        "stateTransitionAxes",
        "gameEndAxes",
        "gameEndCombinationRules",
        "nonCoverageFields",
        "projectionRules",
    }
)
CONTRACT_KEYS = {
    "state-transition": frozenset(
        {
            "schemaVersion",
            "version",
            "calculation",
            "inputAxesDescriptor",
            "provenance",
            "matrixRows",
            "operationRows",
            "undoRows",
            "mustOperationCoverage",
            "requiredSet",
            "cases",
        }
    ),
    "game-end": frozenset(
        {
            "schemaVersion",
            "version",
            "calculation",
            "inputAxesDescriptor",
            "provenance",
            "decisionRows",
            "requiredSet",
            "cases",
            "validationErrors",
        }
    ),
}


class HandoffLoadError(ValueError):
    """宣言・版・写像の不整合を規則 ID とともに表す。"""

    def __init__(self, code: str, detail: str) -> None:
        """規則 ID と診断を保持する。

        Args:
            code: 両 runner で共通の規則 ID。
            detail: 失敗した検査の説明。
        """
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class LoadedHandoffCases:
    """トップレベル検査後にだけ得られる写像済み case 群。"""

    calculation_id: str
    cases: list[dict[str, object]]
    source_cases: list[dict[str, object]] = dataclass_field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LoadedHandoff:
    """二契約の写像済み case 群と descriptor を保持する。"""

    by_calculation: Mapping[str, LoadedHandoffCases]
    descriptor: Mapping[str, object]


def _object(value: object, label: str) -> dict[str, object]:
    """JSON object 以外を拒否する。"""
    if not isinstance(value, dict):
        raise HandoffLoadError("HANDOFF_SHAPE", label)
    return cast(dict[str, object], value)


def _keys(value: object, expected: frozenset[str], label: str) -> dict[str, object]:
    """宣言済み field の完全一致を要求する。"""
    record = _object(value, label)
    if record.keys() != expected:
        raise HandoffLoadError("UNKNOWN_FIELD", label)
    return record


def _array(value: object, label: str) -> list[object]:
    """JSON array 以外を拒否する。"""
    if not isinstance(value, list):
        raise HandoffLoadError("HANDOFF_SHAPE", label)
    return cast(list[object], value)


def _same(actual: object, expected: object, code: str, label: str) -> None:
    """型も含めて宣言値との一致を調べる。"""
    if type(actual) is not type(expected) or actual != expected:
        raise HandoffLoadError(code, label)


def _parse(data: bytes, label: str) -> object:
    """精度を失う数値を JSON 解析中に拒否する。"""

    def safe_int(token: str) -> int:
        if token == "-0":
            raise HandoffLoadError("UNSAFE_INTEGER", label)
        value = int(token)
        if abs(value) > 9007199254740991:
            raise HandoffLoadError("UNSAFE_INTEGER", label)
        return value

    def reject_float(_token: str) -> float:
        raise HandoffLoadError("UNSAFE_INTEGER", label)

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise HandoffLoadError("UNKNOWN_FIELD", f"{label}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            data,
            parse_int=safe_int,
            parse_float=reject_float,
            object_pairs_hook=unique_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffLoadError("HANDOFF_SHAPE", label) from error


def _mapping(binding: dict[str, object], expected_pointer: str) -> dict[str, str]:
    """宣言された pointer だけを runner field へ対応付ける。"""
    mapping = _keys(
        binding["caseFieldMapping"],
        frozenset({"id", "input", "expected", "tags"}),
        "caseFieldMapping",
    )
    inputs = _keys(mapping["input"], frozenset({"raw", "normalized"}), "input")
    pairs = {
        "caseId": mapping["id"],
        "raw": inputs["raw"],
        "normalized": inputs["normalized"],
        "expected": mapping["expected"],
    }
    pointers: dict[str, str] = {}
    for target, pair in pairs.items():
        item = _keys(pair, frozenset({"contractPointer", "runnerPointer"}), target)
        source = expected_pointer if target == "expected" else f"/{target}"
        _same(item["contractPointer"], source, "MAPPING", target)
        _same(item["runnerPointer"], f"/{target}", "MAPPING", target)
        pointers[target] = source[1:]
    tags = _keys(
        mapping["tags"],
        frozenset({"contractPointer", "runnerPointer", "availability"}),
        "tags",
    )
    if tags != {
        "contractPointer": None,
        "runnerPointer": "/tags",
        "availability": "absent",
    }:
        raise HandoffLoadError("MAPPING", "tags")
    return pointers


def _sha(data: bytes) -> str:
    """生の artifact バイト列の SHA-256 を返す。"""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load_handoff(
    root: Path,
    read_asset: Callable[[str], bytes] | None = None,
) -> LoadedHandoff:
    """引き渡し契約を起点に二契約と descriptor を検査して写像する。

    Args:
        root: リポジトリのルート。実行経路では固定の既知パスだけを読む。
        read_asset: 試験でだけ使う読み取り差し替え口。

    Returns:
        二契約の写像済み case 群。

    Raises:
        HandoffLoadError: 宣言、版、digest、写像、または数値が不正な場合。
    """
    reader = read_asset or (lambda path: (root / path).read_bytes())

    def read_bytes(path: str) -> bytes:
        try:
            return reader(path)
        except OSError as error:
            raise HandoffLoadError("HANDOFF_SHAPE", path) from error

    def read(path: str) -> tuple[bytes, dict[str, object]]:
        raw = read_bytes(path)
        return raw, _object(_parse(raw, path), path)

    handoff_raw, handoff = read(HANDOFF_PATH)
    del handoff_raw
    _keys(handoff, HANDOFF_KEYS, "handoff")
    _keys(
        handoff["claimBoundary"],
        frozenset({"guaranteed", "notGuaranteed"}),
        "claimBoundary",
    )
    _keys(
        handoff["fr040Declaration"],
        frozenset({"content", "basis", "recordStage", "recordTarget"}),
        "fr040Declaration",
    )
    _same(
        handoff["handoffVersion"],
        "appendix_e_consumer_handoff_v1",
        "VERSION_MISMATCH",
        "handoffVersion",
    )
    _same(
        handoff["calculationIds"],
        list(CONTRACTS),
        "VERSION_MISMATCH",
        "calculationIds",
    )
    _keys(
        handoff["stage2EntryGate"],
        frozenset(
            {
                "topLevelLoad",
                "versionCheck",
                "bindingConstruction",
                "allCasesConsumption",
                "dPlusOnePrerequisite",
            }
        ),
        "stage2EntryGate",
    )
    parity = _keys(handoff["descriptorParity"], PARITY_KEYS, "descriptorParity")
    _same(parity.get("descriptorPath"), DESCRIPTOR_PATH, "DESCRIPTOR_MISMATCH", "path")
    _same(parity.get("descriptorId"), DESCRIPTOR_ID, "DESCRIPTOR_MISMATCH", "id")
    descriptor_raw, descriptor = read(DESCRIPTOR_PATH)
    _keys(descriptor, DESCRIPTOR_KEYS, "descriptor")
    # 既受理の契約schemaの閉じたconst宣言を期待値にする。
    # 実descriptorから期待値を導出しない。
    descriptor_digest: str | None = None
    descriptor_fields = ("descriptorId", "version", "digest")
    for path in DESCRIPTOR_SCHEMA_PATHS:
        _, schema = read(path)
        definitions = _object(schema.get("$defs"), f"{path}/$defs")
        binding = _keys(
            definitions.get("inputAxesDescriptorBinding"),
            frozenset({"type", "required", "additionalProperties", "properties"}),
            f"{path}/inputAxesDescriptorBinding",
        )
        _same(binding["type"], "object", "DESCRIPTOR_MISMATCH", "binding type")
        _same(
            binding["additionalProperties"],
            False,
            "DESCRIPTOR_MISMATCH",
            "binding closure",
        )
        _same(
            binding["required"],
            list(descriptor_fields),
            "VERSION_MISMATCH",
            "binding required",
        )
        properties = _keys(
            binding["properties"], frozenset(descriptor_fields), "binding properties"
        )
        constants: dict[str, str] = {}
        for field in descriptor_fields:
            declaration = _keys(
                properties[field], frozenset({"const"}), f"binding {field}"
            )
            value = declaration["const"]
            if not isinstance(value, str):
                raise HandoffLoadError("DESCRIPTOR_MISMATCH", f"binding {field}")
            constants[field] = value
        _same(
            constants["descriptorId"],
            DESCRIPTOR_ID,
            "DESCRIPTOR_MISMATCH",
            "binding id",
        )
        _same(
            constants["version"],
            DESCRIPTOR_VERSION,
            "DESCRIPTOR_MISMATCH",
            "binding version",
        )
        digest = constants["digest"]
        if (
            not digest.startswith("sha256:")
            or len(digest) != 71
            or any(char not in "0123456789abcdef" for char in digest[7:])
        ):
            raise HandoffLoadError("DESCRIPTOR_MISMATCH", "binding digest")
        if descriptor_digest is not None:
            _same(digest, descriptor_digest, "DESCRIPTOR_MISMATCH", "schema agreement")
        descriptor_digest = digest
    for field, expected in (
        ("descriptorId", DESCRIPTOR_ID),
        ("version", DESCRIPTOR_VERSION),
        ("digest", descriptor_digest),
    ):
        _same(descriptor.get(field), expected, "DESCRIPTOR_MISMATCH", field)

    bindings = _array(handoff["consumerBindings"], "consumerBindings")
    artifacts = _array(handoff["artifacts"], "artifacts")
    if len(bindings) != len(CONTRACTS) or len(artifacts) != len(CONTRACTS) + 1:
        raise HandoffLoadError("HANDOFF_SHAPE", "bindings/artifacts")
    artifact_by_path: dict[str, dict[str, object]] = {}
    for item in artifacts:
        artifact = _keys(item, frozenset({"path", "version", "digest"}), "artifact")
        path = artifact["path"]
        if not isinstance(path, str) or path in artifact_by_path:
            raise HandoffLoadError("HANDOFF_SHAPE", "artifact path")
        artifact_by_path[path] = artifact
    known_paths = {DESCRIPTOR_PATH, *(spec[0] for spec in CONTRACTS.values())}
    if artifact_by_path.keys() != known_paths:
        raise HandoffLoadError("UNKNOWN_FIELD", "artifact path")

    loaded: dict[str, LoadedHandoffCases] = {}
    raw_by_path = {DESCRIPTOR_PATH: descriptor_raw}
    for binding_value in bindings:
        binding = _keys(binding_value, BINDING_KEYS, "consumerBinding")
        calculation_id = binding["calculationId"]
        if not isinstance(calculation_id, str) or calculation_id not in CONTRACTS:
            raise HandoffLoadError("UNKNOWN_FIELD", "calculationId")
        if calculation_id in loaded:
            raise HandoffLoadError("HANDOFF_SHAPE", "duplicate binding")
        execution_paths = _array(binding["executionPaths"], "executionPaths")
        if len(execution_paths) != 2:
            raise HandoffLoadError("HANDOFF_SHAPE", "executionPaths")
        runners: set[str] = set()
        for value in execution_paths:
            execution = _keys(value, EXECUTION_PATH_KEYS, "executionPath")
            runner = execution["runner"]
            if not isinstance(runner, str) or runner in runners:
                raise HandoffLoadError("HANDOFF_SHAPE", "executionPath runner")
            runners.add(runner)
        if runners != {"pytest", "vitest"}:
            raise HandoffLoadError("HANDOFF_SHAPE", "executionPath runner")
        path, version, expected_pointer, case_keys = CONTRACTS[calculation_id]
        for field, expected in (
            ("vectorId", calculation_id),
            ("contractPath", path),
            ("version", version),
            ("schemaVersion", 1),
            ("caseSchemaRef", "#/$defs/normalizedCase"),
        ):
            _same(binding[field], expected, "VERSION_MISMATCH", field)
        pointers = _mapping(binding, expected_pointer)
        raw, contract = read(path)
        raw_by_path[path] = raw
        _keys(contract, CONTRACT_KEYS[calculation_id], path)
        _same(contract.get("calculation"), calculation_id, "VERSION_MISMATCH", path)
        _same(contract.get("version"), version, "VERSION_MISMATCH", path)
        _same(contract.get("schemaVersion"), 1, "SCHEMA_VERSION", path)
        descriptor_ref = _keys(
            contract.get("inputAxesDescriptor"),
            frozenset({"descriptorId", "version", "digest"}),
            path,
        )
        for field in ("descriptorId", "version", "digest"):
            _same(
                descriptor_ref[field],
                descriptor[field],
                "DESCRIPTOR_MISMATCH",
                f"{path}:{field}",
            )
        source_cases = _array(contract.get("cases"), f"{path}:cases")
        if not source_cases:
            raise HandoffLoadError("HANDOFF_SHAPE", f"{path}:empty cases")
        mapped: list[dict[str, object]] = []
        seen: set[str] = set()
        retained_sources: list[dict[str, object]] = []
        for value in source_cases:
            candidate = _object(value, f"{path}:case")
            has_pure_input = calculation_id == "state-transition" and (
                "inputId" in candidate or "inputPayload" in candidate
            )
            expected_keys = (
                (case_keys - {"historyInput"}) | {"inputId", "inputPayload"}
                if has_pure_input
                else case_keys
            )
            case = _keys(candidate, expected_keys, f"{path}:case")
            if has_pure_input:
                input_id = case["inputId"]
                if (
                    not isinstance(input_id, str)
                    or len(input_id) != 5
                    or input_id[0] != "n"
                    or any(char not in "0123456789" for char in input_id[1:])
                ):
                    raise HandoffLoadError("HANDOFF_SHAPE", "inputId")
                _object(case["inputPayload"], "inputPayload")
            retained_sources.append(case)
            result = {target: case[source] for target, source in pointers.items()}
            case_id = result["caseId"]
            if not isinstance(case_id, str) or not case_id or case_id in seen:
                raise HandoffLoadError("HANDOFF_SHAPE", f"{path}:caseId")
            seen.add(case_id)
            mapped.append(result)
        loaded[calculation_id] = LoadedHandoffCases(
            calculation_id, mapped, retained_sources
        )
    if loaded.keys() != CONTRACTS.keys():
        raise HandoffLoadError("HANDOFF_SHAPE", "missing binding")

    for path, raw in raw_by_path.items():
        artifact = artifact_by_path[path]
        version = (
            DESCRIPTOR_VERSION
            if path == DESCRIPTOR_PATH
            else next(spec[1] for spec in CONTRACTS.values() if spec[0] == path)
        )
        _same(artifact["version"], version, "VERSION_MISMATCH", path)
        _same(artifact["digest"], _sha(raw), "ARTIFACT_DIGEST", path)

    dependencies = _array(handoff["dependencies"], "dependencies")
    if len(dependencies) != len(DEPENDENCIES):
        raise HandoffLoadError("DEPENDENCY_MISMATCH", "dependency count")
    seen_dependencies: set[str] = set()
    for value in dependencies:
        dep = _keys(
            value,
            frozenset(
                {
                    "taskId",
                    "artifactPath",
                    "commitOid",
                    "version",
                    "establishmentCondition",
                }
            ),
            "dependency",
        )
        path = dep["artifactPath"]
        if (
            not isinstance(path, str)
            or path not in DEPENDENCIES
            or path in seen_dependencies
        ):
            raise HandoffLoadError("DEPENDENCY_MISMATCH", "dependency path")
        seen_dependencies.add(path)
        task_id, commit_oid = DEPENDENCY_ORIGINS[path]
        version_key, pinned_digest = DEPENDENCIES[path]
        _same(dep["taskId"], task_id, "DEPENDENCY_MISMATCH", path)
        _same(dep["commitOid"], commit_oid, "DEPENDENCY_MISMATCH", path)
        _same(dep["version"], 1, "DEPENDENCY_MISMATCH", path)
        if version_key is None:
            raw = read_bytes(path)
        else:
            raw, asset = read(path)
            _same(asset.get(version_key), 1, "DEPENDENCY_MISMATCH", path)
        _same(_sha(raw), pinned_digest, "DEPENDENCY_MISMATCH", path)
    return LoadedHandoff(loaded, descriptor)


__all__ = ["HandoffLoadError", "LoadedHandoff", "LoadedHandoffCases", "load_handoff"]
