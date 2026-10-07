"""中間表現を Python・TypeScript・SQL の fragment へ変換する。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from pitchlog.domaingen.backends import python as python_backend
from pitchlog.domaingen.backends import sql as sql_backend
from pitchlog.domaingen.backends import typescript as typescript_backend
from pitchlog.domaingen.backends.common import (
    BackendGenerationError,
    BackendInput,
    GeneratedArtifact,
    Language,
)

LANGUAGES = frozenset(Language)
TARGET_CLASSES = frozenset({"alpha", "beta-1-5", "beta-7", "beta-6-8"})
_SOURCE_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_STAGES = {
    "alpha": None,
    "beta-1-5": ("sql", "typed-receiver", "formatter"),
    "beta-7": ("sql", "typed-receiver"),
    "beta-6-8": None,
}


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise BackendGenerationError(f"{label}が object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """配列を返す。"""
    if not isinstance(value, list):
        raise BackendGenerationError(f"{label}が array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise BackendGenerationError(f"{label}が空でない文字列でない")
    return value


def _stage_inputs(
    generator_version: str,
    source_id: str,
    calculation_id: str,
    declaration: Mapping[str, object],
    target: Mapping[str, object],
) -> tuple[BackendInput, ...]:
    """IR target の段を hash を変えず backend 入力へ変換する。"""
    direct_target_id = _string(
        target.get("directTargetId"),
        "target.directTargetId",
    )
    target_class = _string(target.get("targetClass"), "target.targetClass")
    if target_class not in TARGET_CLASSES:
        raise BackendGenerationError(f"未知の target class: {target_class}")
    stages = _array(target.get("stages"), "target.stages")
    observed_names: list[str] = []
    inputs: list[BackendInput] = []
    for index, raw_stage in enumerate(stages):
        stage = _object(raw_stage, f"target.stages[{index}]")
        stage_name = _string(stage.get("stage"), f"target.stages[{index}].stage")
        generated_id = _string(
            stage.get("generatedId"),
            f"target.stages[{index}].generatedId",
        )
        source_hash = _string(
            stage.get("sourceHash"),
            f"target.stages[{index}].sourceHash",
        )
        if _SOURCE_HASH_PATTERN.fullmatch(source_hash) is None:
            raise BackendGenerationError(f"段別 hash が不正: {source_hash}")
        observed_names.append(stage_name)
        inputs.append(
            BackendInput(
                generator_version=generator_version,
                source_id=source_id,
                calculation_id=calculation_id,
                direct_target_id=direct_target_id,
                target_class=target_class,
                stage=stage_name,
                generated_id=generated_id,
                source_hash=source_hash,
                declaration=declaration,
            )
        )
    expected = _EXPECTED_STAGES[target_class]
    if expected is None:
        if len(inputs) != 1:
            raise BackendGenerationError(f"{target_class} は単一段でなければならない")
    elif tuple(observed_names) != expected:
        raise BackendGenerationError(f"{target_class} の段順が不正: {observed_names!r}")
    return tuple(inputs)


def _generate_target(stages: tuple[BackendInput, ...]) -> list[GeneratedArtifact]:
    """Target matrix に従い、一つの target から生成物を作る。"""
    target_class = stages[0].target_class
    if target_class == "alpha":
        source = stages[0]
        return [
            python_backend.generate(source),
            typescript_backend.generate(source),
        ]
    if target_class == "beta-6-8":
        return [python_backend.generate(stages[0])]

    artifacts: list[GeneratedArtifact] = []
    for source in stages:
        if source.stage == "sql":
            artifacts.append(sql_backend.generate(source))
        elif source.stage == "typed-receiver":
            artifacts.append(python_backend.generate(source))
        elif source.stage != "formatter":
            raise BackendGenerationError(f"未知の生成段: {source.stage}")
    return artifacts


def generate_language_artifacts(
    intermediate: Mapping[str, object],
) -> tuple[GeneratedArtifact, ...]:
    """ステップ 26 の中間表現から target matrix の生成物を返す。

    Args:
        intermediate: ステップ 26 が生成した言語非依存中間表現。

    Returns:
        製品経路へ配置しないラッパー専用 fragment の列。

    Raises:
        BackendGenerationError: 中間表現の target matrix が不正な場合。
    """
    generator_version = _string(
        intermediate.get("generatorVersion"),
        "generatorVersion",
    )
    artifacts: list[GeneratedArtifact] = []
    calculations = _array(intermediate.get("calculations"), "calculations")
    for calculation_index, raw_calculation in enumerate(calculations):
        calculation = _object(
            raw_calculation,
            f"calculations[{calculation_index}]",
        )
        calculation_id = _string(
            calculation.get("calculationId"),
            f"calculations[{calculation_index}].calculationId",
        )
        source_id = _string(
            calculation.get("sourceId"),
            f"calculations[{calculation_index}].sourceId",
        )
        declaration = _object(
            calculation.get("declaration"),
            f"calculations[{calculation_index}].declaration",
        )
        targets = _array(
            calculation.get("targets"),
            f"calculations[{calculation_index}].targets",
        )
        for target_index, raw_target in enumerate(targets):
            target = _object(
                raw_target,
                f"calculations[{calculation_index}].targets[{target_index}]",
            )
            stages = _stage_inputs(
                generator_version,
                source_id,
                calculation_id,
                declaration,
                target,
            )
            artifacts.extend(_generate_target(stages))
    return tuple(artifacts)


__all__ = [
    "BackendGenerationError",
    "GeneratedArtifact",
    "LANGUAGES",
    "Language",
    "TARGET_CLASSES",
    "generate_language_artifacts",
]
