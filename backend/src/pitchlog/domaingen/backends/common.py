"""言語別 backend が共有する入力型と生成物型を提供する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

WRAPPER_ONLY_DELIVERY = "wrapper-only-fragment"


class BackendGenerationError(Exception):
    """中間表現から言語別生成物を構築できないことを表す。"""


class Language(StrEnum):
    """本ステップが生成する言語の閉じた集合。"""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    SQL = "sql"


@dataclass(frozen=True, slots=True)
class BackendInput:
    """一つの IR 段を言語 backend へ渡す入力。

    Attributes:
        generator_version: ステップ 26 の生成器 version。
        source_id: 宣言モデルの生成元条項 ID。
        calculation_id: 対象計算 ID。
        direct_target_id: 直接呼び出し対象 ID。
        target_class: target matrix の区分。
        stage: 中間表現が宣言した段。
        generated_id: マニフェスト由来の生成物 ID。
        source_hash: ステップ 26 が計算した段別 hash。
        declaration: 言語非依存の計算宣言。
    """

    generator_version: str
    source_id: str
    calculation_id: str
    direct_target_id: str
    target_class: str
    stage: str
    generated_id: str
    source_hash: str
    declaration: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    """製品経路へ直接 import できない言語別生成 fragment。

    Attributes:
        generator_version: 生成に用いたコアの version。
        source_id: 生成元条項 ID。
        calculation_id: 対象計算 ID。
        direct_target_id: 直接呼び出し対象 ID。
        target_class: target matrix の区分。
        stage: 中間表現上の段。
        generated_id: 生成物宣言の ID。
        language: 生成言語。
        source_hash: コアから再計算せず引き継いだ段別 hash。
        delivery: ラッパー経由だけを許す配布形態。
        content: 言語別の生成内容。
    """

    generator_version: str
    source_id: str
    calculation_id: str
    direct_target_id: str
    target_class: str
    stage: str
    generated_id: str
    language: Language
    source_hash: str
    delivery: str
    content: str

    def as_mapping(self) -> dict[str, object]:
        """外部出力用の厳密キー集合を持つ辞書へ変換する。"""
        return {
            "generatorVersion": self.generator_version,
            "sourceId": self.source_id,
            "calculationId": self.calculation_id,
            "directTargetId": self.direct_target_id,
            "targetClass": self.target_class,
            "stage": self.stage,
            "generatedId": self.generated_id,
            "language": self.language.value,
            "sourceHash": self.source_hash,
            "delivery": self.delivery,
            "content": self.content,
        }


def artifact(
    source: BackendInput,
    language: Language,
    content: str,
) -> GeneratedArtifact:
    """入力の provenance をそのまま保持した生成物を返す。

    Args:
        source: ステップ 26 が付与した情報を持つ段入力。
        language: 出力言語。
        content: 言語別に生成した fragment。

    Returns:
        ラッパー専用の生成物。
    """
    return GeneratedArtifact(
        generator_version=source.generator_version,
        source_id=source.source_id,
        calculation_id=source.calculation_id,
        direct_target_id=source.direct_target_id,
        target_class=source.target_class,
        stage=source.stage,
        generated_id=source.generated_id,
        language=language,
        source_hash=source.source_hash,
        delivery=WRAPPER_ONLY_DELIVERY,
        content=content,
    )
