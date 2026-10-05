"""資産で宣言した規則による状況判定ケースの正規化を共有する。"""

from __future__ import annotations

import copy
from pathlib import PurePosixPath
from typing import Any


class NormalizationError(ValueError):
    """正規化規則または語彙参照が不正な場合を表す。"""


class NormalizationRules:
    """規則宣言と語彙シードから双方向の値変換を組み立てる。"""

    def __init__(
        self,
        schema: dict[str, Any],
        vocabulary: dict[str, Any],
        manifest: dict[str, Any],
        seed_path: PurePosixPath,
    ) -> None:
        """宣言と語彙の対応を検証する。

        Args:
            schema: 状況判定契約schema。
            vocabulary: 展開器と同じ経路で読んだ語彙シード。
            manifest: 語彙manifest。
            seed_path: 語彙シードのリポジトリ相対パス。
        """
        declaration = schema.get("x-pitchlog-stage1-normalization", {})
        catalog = declaration.get("ruleCatalog")
        if not isinstance(catalog, list) or not catalog:
            raise NormalizationError("正規化規則の宣言がない")
        self.rules: dict[str, dict[str, Any]] = {}
        for rule in catalog:
            if not isinstance(rule, dict) or not isinstance(rule.get("ruleId"), str):
                raise NormalizationError("正規化規則の識別子が不正")
            rule_id = rule["ruleId"]
            if rule_id in self.rules or not rule_id:
                raise NormalizationError("正規化規則の識別子が重複または空")
            transform = rule.get("transform")
            if not isinstance(transform, dict) or transform.get("kind") not in (
                "identity", "vocabulary-lookup"
            ):
                raise NormalizationError(f"未対応の正規化変換: {rule_id}")
            self.rules[rule_id] = transform
        declared_ids = schema.get("$defs", {}).get("normalizationRuleId", {}).get("enum")
        if not isinstance(declared_ids, list) or set(declared_ids) != set(self.rules):
            raise NormalizationError("規則カタログとcaseの規則語彙が不一致")
        bindings = manifest.get("seeds")
        if not isinstance(bindings, list) or not any(
            isinstance(item, dict)
            and item.get("path") == seed_path.as_posix()
            and item.get("vocabularyId") == vocabulary.get("vocabularyId")
            for item in bindings
        ):
            raise NormalizationError("語彙manifestとseedの対応が一致しない")
        axes = vocabulary.get("axes")
        if not isinstance(axes, list):
            raise NormalizationError("語彙seedに軸がない")
        self.axes = {
            axis["axisId"]: axis["entries"]
            for axis in axes
            if isinstance(axis, dict)
            and isinstance(axis.get("axisId"), str)
            and isinstance(axis.get("entries"), list)
        }

    def _mapping(
        self, transform: dict[str, Any], selector: str
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        """宣言された軸の表示値とIDを一意に対応付ける。"""
        if set(transform) != {
            "kind", "field", "selectorField", "axisBySelector",
            "rawEntryField", "normalizedEntryField",
        }:
            raise NormalizationError("語彙参照規則の形式が不正")
        axes = transform["axisBySelector"]
        if not isinstance(axes, dict) or selector not in axes:
            raise NormalizationError(f"正規化対象の軸が宣言されていない: {selector}")
        axis_id = axes[selector]
        if axis_id not in self.axes:
            raise NormalizationError(f"正規化対象の語彙軸がない: {axis_id}")
        forward: dict[str, str] = {}
        reverse: dict[str, str] = {}
        for entry in self.axes[axis_id]:
            if not isinstance(entry, dict):
                raise NormalizationError("語彙エントリが不正")
            raw = entry.get(transform["rawEntryField"])
            normalized = entry.get(transform["normalizedEntryField"])
            if (
                not isinstance(raw, str) or not raw
                or not isinstance(normalized, str) or not normalized
                or raw in forward or normalized in reverse
            ):
                raise NormalizationError(f"語彙の表示値とIDが一意でない: {axis_id}")
            forward[raw] = normalized
            reverse[normalized] = raw
        return transform["field"], forward, reverse

    def _convert(self, value: Any, rule_id: str, *, reverse: bool) -> Any:
        """同じ規則宣言を正方向または展開用の逆方向へ適用する。"""
        transform = self.rules.get(rule_id)
        if transform is None:
            raise NormalizationError(f"未宣言の正規化規則: {rule_id}")
        result = copy.deepcopy(value)
        if transform["kind"] == "identity":
            if set(transform) != {"kind"}:
                raise NormalizationError("identity規則の形式が不正")
            return result
        if not isinstance(result, dict):
            raise NormalizationError("語彙参照規則の入力がobjectでない")
        selector = result.get(transform.get("selectorField"))
        if not isinstance(selector, str):
            raise NormalizationError("正規化対象の軸選択値がない")
        field, forward, backward = self._mapping(transform, selector)
        lookup = backward if reverse else forward
        if result.get(field) not in lookup:
            raise NormalizationError(f"語彙値を解決できない: {rule_id}, {field}")
        result[field] = lookup[result[field]]
        return result

    def normalize(self, raw: Any, rule_id: str) -> Any:
        """宣言された規則をrawへ適用する。"""
        return self._convert(raw, rule_id, reverse=False)

    def raw_for_normalized(self, normalized: Any) -> tuple[Any, str]:
        """展開器向けに宣言済みの非identity規則を選びrawを作る。"""
        if not isinstance(normalized, dict):
            raise NormalizationError("展開用の正規化値がobjectでない")
        matching = [
            rule_id for rule_id, transform in self.rules.items()
            if transform["kind"] == "vocabulary-lookup"
            and normalized.get(transform.get("selectorField"))
            in transform.get("axisBySelector", {})
        ]
        if len(matching) > 1:
            raise NormalizationError("展開用の正規化規則が複数一致")
        if matching:
            rule_id = matching[0]
        else:
            identities = [
                rule_id for rule_id, transform in self.rules.items()
                if transform["kind"] == "identity"
            ]
            if len(identities) != 1:
                raise NormalizationError("identity規則を一意に選べない")
            rule_id = identities[0]
        return self._convert(normalized, rule_id, reverse=True), rule_id
