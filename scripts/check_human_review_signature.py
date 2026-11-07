"""人間確認の署名記録を検証し、未確認の逐行確認シートを生成する。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

try:
    import check_input_axes_descriptor as descriptor_checker
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    from scripts import check_input_axes_descriptor as descriptor_checker

try:
    import check_vocabulary_manifest as vocabulary_checker
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    vocabulary_spec = importlib.util.spec_from_file_location(
        "check_vocabulary_manifest",
        Path(__file__).resolve().with_name("check_vocabulary_manifest.py"),
    )
    if vocabulary_spec is None or vocabulary_spec.loader is None:  # pragma: no cover
        raise ImportError("check_vocabulary_manifest.pyを読み込めない")
    vocabulary_checker = importlib.util.module_from_spec(vocabulary_spec)
    sys.modules[vocabulary_spec.name] = vocabulary_checker
    vocabulary_spec.loader.exec_module(vocabulary_checker)

SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/human_review_signature_schema_v1.json"
)
STATE_TRANSITION_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/state_transition_contract_schema_v1.json"
)
STATE_TRANSITION_CONTRACT_PATH = PurePosixPath(
    "contracts/state-transition/state_transition_contract_v1.json"
)
GAME_END_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/game_end_contract_schema_v1.json"
)
GAME_END_CONTRACT_PATH = PurePosixPath(
    "contracts/state-transition/game_end_contract_v1.json"
)
VOCABULARY_MANIFEST_PATH = PurePosixPath(
    "contracts/vocabulary/vocabulary_manifest_v1.json"
)


class HumanReviewSignatureRecordError(ValueError):
    """署名記録を宣言済みの機械保証範囲で検証できない場合を表す。"""


def _object(value: object, label: str) -> dict[str, Any]:
    """文字列キーのobjectを返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise HumanReviewSignatureRecordError(f"{label}がobjectでない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise HumanReviewSignatureRecordError(f"{label}が空でない文字列でない")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    """重複のない空でない文字列配列を返す。"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise HumanReviewSignatureRecordError(
            f"{label}が重複のない空でない文字列配列でない"
        )
    return tuple(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    """objectのキー集合が宣言形式と一致することを確認する。"""
    if set(value) != expected:
        raise HumanReviewSignatureRecordError(
            f"{label}のキーがexact-set不一致: "
            f"expected={sorted(expected)!r}; actual={sorted(value)!r}"
        )


def _load_schema(root: Path) -> dict[str, Any]:
    """署名記録schemaを重複キー拒否付きで読み込む。"""
    try:
        value = descriptor_checker.load_json(root / SCHEMA_PATH, "署名記録schema")
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    return _object(value, "署名記録schema")


def _policy(schema: Mapping[str, Any]) -> dict[str, Any]:
    """schemaの署名記録方針を閉じた宣言として返す。"""
    policy = _object(
        schema.get("x-pitchlog-human-review-signature-policy"),
        "x-pitchlog-human-review-signature-policy",
    )
    _exact_keys(
        policy,
        {
            "recordLocation",
            "subjectDigest",
            "recordedMethods",
            "attestationItems",
            "assuranceBoundary",
            "provenanceRelation",
            "devHarness63Relation",
        },
        "x-pitchlog-human-review-signature-policy",
    )
    if _string(policy["recordLocation"], "recordLocation") != "separate-document":
        raise HumanReviewSignatureRecordError("署名記録が独立文書として宣言されていない")

    digest = _object(policy["subjectDigest"], "subjectDigest")
    _exact_keys(
        digest,
        {
            "documentKind",
            "pathRoot",
            "canonicalization",
            "algorithm",
            "safeIntegerLimit",
        },
        "subjectDigest",
    )
    for key in ("documentKind", "pathRoot", "canonicalization", "algorithm"):
        _string(digest[key], f"subjectDigest.{key}")
    supported_digest_declaration = {
        "documentKind": "json",
        "canonicalization": "RFC8785",
        "algorithm": "sha256",
    }
    for key, supported in supported_digest_declaration.items():
        if digest[key] != supported:
            raise HumanReviewSignatureRecordError(
                f"未対応のsubjectDigest.{key}である: {digest[key]!r}"
            )
    safe_integer_limit = digest["safeIntegerLimit"]
    if (
        not isinstance(safe_integer_limit, int)
        or isinstance(safe_integer_limit, bool)
        or safe_integer_limit < 1
    ):
        raise HumanReviewSignatureRecordError(
            "subjectDigest.safeIntegerLimitが正の整数でない"
        )

    methods = _object(policy["recordedMethods"], "recordedMethods")
    attestations = _object(policy["attestationItems"], "attestationItems")
    if not methods or not attestations:
        raise HumanReviewSignatureRecordError("署名記録の閉じた宣言が空である")
    for method_id, raw_method in methods.items():
        method = _object(raw_method, f"recordedMethods.{method_id}")
        _exact_keys(method, {"humanMeaning"}, f"recordedMethods.{method_id}")
        _string(method["humanMeaning"], f"recordedMethods.{method_id}.humanMeaning")
    for attestation_id, raw_attestation in attestations.items():
        attestation = _object(
            raw_attestation, f"attestationItems.{attestation_id}"
        )
        _exact_keys(
            attestation,
            {"acceptedRecordedResponses", "humanMeaning"},
            f"attestationItems.{attestation_id}",
        )
        responses = attestation["acceptedRecordedResponses"]
        if not isinstance(responses, list) or not responses:
            raise HumanReviewSignatureRecordError(
                f"attestationItems.{attestation_id}.acceptedRecordedResponsesが空である"
            )
        _string(
            attestation["humanMeaning"],
            f"attestationItems.{attestation_id}.humanMeaning",
        )

    assurance = _object(policy["assuranceBoundary"], "assuranceBoundary")
    _exact_keys(
        assurance,
        {"mechanicallyGuaranteed", "humanControls", "wordingRule"},
        "assuranceBoundary",
    )
    _string_list(
        assurance["mechanicallyGuaranteed"],
        "assuranceBoundary.mechanicallyGuaranteed",
    )
    _string_list(assurance["humanControls"], "assuranceBoundary.humanControls")
    _string(assurance["wordingRule"], "assuranceBoundary.wordingRule")
    _string(policy["provenanceRelation"], "provenanceRelation")
    _string(policy["devHarness63Relation"], "devHarness63Relation")
    return policy


def _repository_subject_path(
    root: Path, raw_path: str, declared_root: str
) -> Path:
    """宣言された領域内の対象パスを返す。"""
    relative = PurePosixPath(raw_path)
    root_relative = PurePosixPath(declared_root)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "\\" in raw_path
        or relative.parts[: len(root_relative.parts)] != root_relative.parts
    ):
        raise HumanReviewSignatureRecordError(
            f"署名対象pathが宣言領域外である: {raw_path!r}"
        )
    resolved_root = root.resolve()
    resolved = (resolved_root / Path(*relative.parts)).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise HumanReviewSignatureRecordError(
            f"署名対象pathがリポジトリ外へ解決される: {raw_path!r}"
        ) from error
    return resolved


def _response_is_accepted(response: object, accepted: list[object]) -> bool:
    """JSON型を含めて記録済み宣誓応答が許容値に一致するか返す。"""
    actual = descriptor_checker.canonicalize_json(response)
    return any(
        actual == descriptor_checker.canonicalize_json(candidate)
        for candidate in accepted
    )


def compute_subject_digest(subject: object, safe_integer_limit: int) -> str:
    """対象JSON文書全体のRFC 8785 + SHA-256 digestを返す。

    Args:
        subject: 重複キー拒否を通過した対象JSON文書。
        safe_integer_limit: 許容する整数の絶対値上限。

    Returns:
        ``sha256:`` 接頭辞付きの小文字16進digest。
    """
    canonical = descriptor_checker.canonicalize_json(subject, safe_integer_limit)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _compact_json(value: object) -> str:
    """短縮表示不能値向けの決定的な1行JSONを返す。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("|", "\\|")


def _markdown_text(value: str) -> str:
    """表セルを壊さない1行のMarkdownテキストを返す。"""
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _load_vocabulary_display_names(root: Path) -> dict[str, str]:
    """manifest検証済み語彙シードからIDと初期表示名の写像を返す。"""
    try:
        vocabulary_checker.validate_manifest(root)
        manifest = _object(
            descriptor_checker.load_json(
                root / VOCABULARY_MANIFEST_PATH,
                "語彙manifest",
            ),
            "語彙manifest",
        )
    except (
        descriptor_checker.DescriptorCheckError,
        vocabulary_checker.VocabularyManifestError,
    ) as error:
        raise HumanReviewSignatureRecordError(str(error)) from error

    names: dict[str, str] = {}
    raw_seeds = manifest.get("seeds")
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise HumanReviewSignatureRecordError("語彙manifest.seedsが空または配列でない")
    for seed_index, raw_declaration in enumerate(raw_seeds):
        declaration = _object(raw_declaration, f"語彙manifest.seeds[{seed_index}]")
        path = _string(declaration.get("path"), f"seeds[{seed_index}].path")
        try:
            raw_seed = descriptor_checker.load_json(root / path, f"語彙シード {path}")
        except descriptor_checker.DescriptorCheckError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        seed = _object(raw_seed, f"語彙シード {path}")
        raw_axes = seed.get("axes")
        if not isinstance(raw_axes, list):
            raise HumanReviewSignatureRecordError(f"語彙シード {path}.axesが配列でない")
        for axis_index, raw_axis in enumerate(raw_axes):
            axis = _object(raw_axis, f"{path}.axes[{axis_index}]")
            raw_entries = axis.get("entries")
            if not isinstance(raw_entries, list):
                raise HumanReviewSignatureRecordError(
                    f"{path}.axes[{axis_index}].entriesが配列でない"
                )
            for entry_index, raw_entry in enumerate(raw_entries):
                entry = _object(
                    raw_entry,
                    f"{path}.axes[{axis_index}].entries[{entry_index}]",
                )
                entry_id = _string(entry.get("id"), "語彙entry.id")
                display_name = _string(
                    entry.get("initialDisplayName"),
                    "語彙entry.initialDisplayName",
                )
                if entry_id in names:
                    raise HumanReviewSignatureRecordError(
                        f"語彙IDが複数の表示名へ解決される: {entry_id!r}"
                    )
                names[entry_id] = display_name
    return names


def _schema_definition(
    schema: Mapping[str, Any],
    definition_id: str,
) -> dict[str, Any]:
    """状況判定契約schemaの指定定義を返す。"""
    definitions = _object(schema.get("$defs"), "状況判定契約schema.$defs")
    return _object(definitions.get(definition_id), f"$defs.{definition_id}")


def _runner_display_policy(schema: Mapping[str, Any]) -> tuple[
    dict[str, str], dict[str, tuple[str, ...]]
]:
    """schemaの走者存在宣言から塁名と存在値を取得する。"""
    constraints = _object(
        schema.get("x-pitchlog-matrix-cross-constraints"),
        "x-pitchlog-matrix-cross-constraints",
    )
    presence = _object(constraints.get("runnerPresence"), "runnerPresence")
    base_by_number = _object(
        presence.get("baseByRunnerNumber"),
        "runnerPresence.baseByRunnerNumber",
    )
    present_values = _object(
        presence.get("presentValuesByBase"),
        "runnerPresence.presentValuesByBase",
    )
    labels: dict[str, str] = {}
    values_by_base: dict[str, tuple[str, ...]] = {}
    for runner_number, raw_base in base_by_number.items():
        base = _string(raw_base, f"baseByRunnerNumber.{runner_number}")
        labels[base] = f"{runner_number}塁"
        values_by_base[base] = _string_list(
            present_values.get(base),
            f"presentValuesByBase.{base}",
        )
    return labels, values_by_base


def _predicate_args(raw_precondition: object) -> list[dict[str, Any]]:
    """共通部分の抽出に使えるand述語の引数を返す。"""
    precondition = _object(raw_precondition, "precondition")
    raw_args = precondition.get("args")
    if precondition.get("op") != "and" or not isinstance(raw_args, list):
        return []
    return [
        _object(raw_arg, f"precondition.args[{index}]")
        for index, raw_arg in enumerate(raw_args)
    ]


def _split_common_preconditions(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """全行共通の述語引数と行ごとの差分を決定的に分ける。"""
    args_by_row = [_predicate_args(row.get("precondition")) for row in rows]
    if not args_by_row or any(not args for args in args_by_row):
        return None, [
            _object(row.get("precondition"), "precondition") for row in rows
        ]

    canonical_by_row = [
        {descriptor_checker.canonicalize_json(arg) for arg in args}
        for args in args_by_row
    ]
    common_keys = set.intersection(*canonical_by_row)
    common_args = [
        arg
        for arg in args_by_row[0]
        if descriptor_checker.canonicalize_json(arg) in common_keys
    ]
    residuals = [
        {
            "op": "and",
            "args": [
                arg
                for arg in args
                if descriptor_checker.canonicalize_json(arg) not in common_keys
            ],
        }
        for args in args_by_row
    ]
    common = {"op": "and", "args": common_args} if common_args else None
    return common, residuals


def _format_precondition(
    raw_precondition: object,
    schema: Mapping[str, Any],
    unresolved: set[str],
) -> str:
    """現在解釈可能なPredicateを短い日本語へ整形する。"""
    precondition = _object(raw_precondition, "precondition")
    raw_args = precondition.get("args")
    if precondition.get("op") != "and" or not isinstance(raw_args, list):
        unresolved.add(f"precondition={_compact_json(precondition)}")
        return _compact_json(precondition)

    values: dict[str, object] = {}
    for index, raw_arg in enumerate(raw_args):
        arg = _object(raw_arg, f"precondition.args[{index}]")
        if arg.get("op") != "eq" or set(arg) != {"op", "axisId", "value"}:
            unresolved.add(f"precondition.args[{index}]={_compact_json(arg)}")
            continue
        axis_id = _string(arg.get("axisId"), f"precondition.args[{index}].axisId")
        if axis_id in values:
            unresolved.add(f"preconditionの重複軸={axis_id}")
            continue
        values[axis_id] = arg.get("value")

    parts: list[str] = []
    outs = values.pop("state.outs", None)
    if isinstance(outs, int) and not isinstance(outs, bool):
        parts.append("無死" if outs == 0 else f"{outs}死")
    elif outs is not None:
        unresolved.add(f"state.outs={_compact_json(outs)}")
        parts.append(f"state.outs={_compact_json(outs)}")

    runners = values.pop("state.runners", None)
    if runners == "empty":
        parts.append("走者なし")
    elif runners is not None:
        labels, present_values = _runner_display_policy(schema)
        occupied = [
            labels[base]
            for base in labels
            if isinstance(runners, str) and runners in present_values[base]
        ]
        if occupied:
            parts.append("走者 " + "・".join(occupied))
        else:
            unresolved.add(f"state.runners={_compact_json(runners)}")
            parts.append(f"state.runners={_compact_json(runners)}")

    strikes = values.pop("state.count.strikes", None)
    balls = values.pop("state.count.balls", None)
    valid_strikes = isinstance(strikes, int) and not isinstance(strikes, bool)
    valid_balls = isinstance(balls, int) and not isinstance(balls, bool)
    if valid_strikes and valid_balls:
        parts.append(f"カウント {balls}-{strikes}")
    else:
        if valid_strikes:
            parts.append(f"S={strikes}")
        elif strikes is not None:
            unresolved.add(f"state.count.strikes={_compact_json(strikes)}")
            parts.append(f"state.count.strikes={_compact_json(strikes)}")
        if valid_balls:
            parts.append(f"B={balls}")
        elif balls is not None:
            unresolved.add(f"state.count.balls={_compact_json(balls)}")
            parts.append(f"state.count.balls={_compact_json(balls)}")

    pitch_event_kind = values.pop("event.perPitch.pitchEventKind", None)
    if pitch_event_kind == "pitch-event":
        parts.append("投球イベント")
    elif pitch_event_kind == "non-pitch-event":
        parts.append("非投球イベント")
    elif pitch_event_kind is not None:
        unresolved.add(
            "event.perPitch.pitchEventKind=" + _compact_json(pitch_event_kind)
        )
        parts.append(_compact_json(pitch_event_kind))

    for axis_id, value in values.items():
        unresolved.add(f"{axis_id}={_compact_json(value)}")
        parts.append(f"{axis_id}={_compact_json(value)}")
    return " / ".join(parts) if parts else "—"


def _format_count_effect(
    raw_effect: object,
    schema: Mapping[str, Any],
    unresolved: set[str],
) -> str:
    """CountEffectをschema宣言順のS/B短縮表現へ整形する。"""
    effect = _object(raw_effect, "countEffect")
    count_schema = _schema_definition(schema, "countEffect")
    properties = _object(count_schema.get("properties"), "$defs.countEffect.properties")
    parts: list[str] = []
    for field in properties:
        raw_field_effect = effect.get(field)
        field_effect = _object(raw_field_effect, f"countEffect.{field}")
        short_name = field[:1].upper()
        kind = field_effect.get("kind")
        if kind == "unchanged":
            continue
        if kind == "delta":
            value = field_effect.get("value")
            if isinstance(value, int) and not isinstance(value, bool):
                parts.append(f"{short_name}{value:+d}")
                continue
        elif kind == "reset":
            parts.append(f"{short_name}→0")
            continue
        unresolved.add(f"countEffect.{field}={_compact_json(field_effect)}")
        parts.append(f"{short_name}:{_compact_json(field_effect)}")
    return " / ".join(parts) if parts else "—"


def _format_plate_appearance(value: object, unresolved: set[str]) -> str:
    """打席終了値を短い日本語へ整形する。"""
    if value is True:
        return "終了"
    if value is False:
        return "継続"
    if value == "not-applicable":
        return "—"
    unresolved.add(f"plateAppearanceEnded={_compact_json(value)}")
    return _compact_json(value)


def _format_batter_destination(value: object, unresolved: set[str]) -> str:
    """打者の行き先を短い日本語へ整形する。"""
    destination = _object(value, "batterDestination")
    kind = destination.get("kind")
    if kind == "continue":
        return "継続"
    if kind == "out":
        return "アウト"
    if kind == "score":
        return "得点"
    if kind == "not-applicable":
        return "—"
    if kind == "reach":
        base = destination.get("base")
        if isinstance(base, int) and not isinstance(base, bool):
            return f"{base}塁"
    unresolved.add(f"batterDestination={_compact_json(destination)}")
    return _compact_json(destination)


def _format_runner_advance(
    value: object,
    schema: Mapping[str, Any],
    unresolved: set[str],
) -> str:
    """走者の既定進塁を短縮し、全塁非該当ならダッシュを返す。"""
    advances = _object(value, "runnerDefaultAdvance")
    if advances and all(
        isinstance(advance, dict)
        and advance.get("modality") == "not-applicable"
        and advance.get("destination") is None
        for advance in advances.values()
    ):
        return "—"
    labels, _ = _runner_display_policy(schema)
    runner_schema = _schema_definition(schema, "runnerDefaultAdvance")
    bases = _string_list(
        runner_schema.get("required"),
        "$defs.runnerDefaultAdvance.required",
    )
    parts: list[str] = []
    for base in bases:
        advance = _object(advances.get(base), f"runnerDefaultAdvance.{base}")
        modality = advance.get("modality")
        destination = advance.get("destination")
        label = labels.get(base, base)
        if modality == "not-applicable" and destination is None:
            continue
        if modality == "hold" and destination is None:
            parts.append(f"{label}停止")
            continue
        if (
            modality in {"forced", "optional"}
            and isinstance(destination, int)
            and not isinstance(destination, bool)
        ):
            modality_name = "強制" if modality == "forced" else "非フォース"
            destination_name = "本塁" if destination == 4 else f"{destination}塁"
            parts.append(f"{label}→{destination_name}（{modality_name}）")
            continue
        unresolved.add(f"runnerDefaultAdvance.{base}={_compact_json(advance)}")
        parts.append(f"{label}:{_compact_json(advance)}")
    return " / ".join(parts) if parts else "—"


def _format_out_effect(value: object, unresolved: set[str]) -> str:
    """アウト数と対象を短い日本語へ整形する。"""
    effect = _object(value, "outEffect")
    count = effect.get("count")
    raw_targets = effect.get("targets")
    if not isinstance(count, int) or isinstance(count, bool) or not isinstance(
        raw_targets, list
    ):
        unresolved.add(f"outEffect={_compact_json(effect)}")
        return _compact_json(effect)
    if count == 0 and not raw_targets:
        return "0"

    targets: list[str] = []
    for raw_target in raw_targets:
        if raw_target == "batter":
            targets.append("打者")
        elif isinstance(raw_target, dict) and isinstance(raw_target.get("runner"), int):
            targets.append(f"{raw_target['runner']}塁走者")
        else:
            unresolved.add(f"outEffect.target={_compact_json(raw_target)}")
            targets.append(_compact_json(raw_target))
    return f"{count}（{'・'.join(targets)}）" if targets else str(count)


def _format_true_stat_flags(
    value: object,
    schema: Mapping[str, Any],
) -> str:
    """schemaが定める23フラグのうちtrueの名前だけを返す。"""
    flags = _object(value, "statFlags")
    stat_schema = _schema_definition(schema, "statFlags")
    fields = _string_list(stat_schema.get("required"), "$defs.statFlags.required")
    enabled = [field for field in fields if flags.get(field) is True]
    return "・".join(enabled) if enabled else "なし"


def _format_event_kind(value: object, unresolved: set[str]) -> str:
    """イベント種別を短い日本語へ整形する。"""
    if value == "batting-result":
        return "打撃結果"
    if value == "secondary-result":
        return "打撃結果2"
    if value == "runner-event":
        return "走者イベント"
    unresolved.add(f"eventKind={_compact_json(value)}")
    return _compact_json(value)


def render_matrix_rows_review_sheet(
    root: Path,
    contract: Mapping[str, Any],
) -> str:
    """未確認のmatrixRowsを人間向け逐行確認シートへ描画する。

    Args:
        root: リポジトリルート。
        contract: 状況判定契約。

    Returns:
        Markdown形式の逐行確認シート。

    Raises:
        HumanReviewSignatureRecordError: 契約schemaまたは描画元の必須宣言を
            解決できない場合。

    Note:
        この関数が検査するのは契約schemaへの適合だけである。状態効果の意味や
        人間レビューの実施は保証しない。
    """
    try:
        raw_schema = descriptor_checker.load_json(
            root / STATE_TRANSITION_SCHEMA_PATH,
            "状況判定契約schema",
        )
        schema = _object(raw_schema, "状況判定契約schema")
        descriptor_checker._validate_instance(
            dict(contract), schema, schema, "状況判定契約"
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error

    rows = contract.get("matrixRows")
    if not isinstance(rows, list) or not rows:
        raise HumanReviewSignatureRecordError("matrixRowsが空または配列でない")
    typed_rows = [
        _object(raw_row, f"matrixRows[{index}]")
        for index, raw_row in enumerate(rows)
    ]
    display_names = _load_vocabulary_display_names(root)
    unresolved: set[str] = set()

    provenance = _object(contract.get("provenance"), "provenance")
    source_ids: list[str] = []
    raw_sources = provenance.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise HumanReviewSignatureRecordError("provenance.sourcesが空または配列でない")
    for index, raw_source in enumerate(raw_sources):
        source = _object(raw_source, f"provenance.sources[{index}]")
        source_ids.append(
            _string(source.get("sourceId"), f"provenance.sources[{index}].sourceId")
        )

    author_id = _string(provenance.get("authorId"), "provenance.authorId")
    verifier_id = _string(
        provenance.get("independentVerifierId"),
        "provenance.independentVerifierId",
    )
    review_summary = "- 独立確認: **未実施**"
    if verifier_id != "not-performed":
        independent_review = _object(
            provenance.get("independentReview"),
            "provenance.independentReview",
        )
        verified_on = _string(
            independent_review.get("verifiedOn"),
            "provenance.independentReview.verifiedOn",
        )
        reviewer_role = _string(
            independent_review.get("reviewerRole"),
            "provenance.independentReview.reviewerRole",
        )
        exposure = _string(
            independent_review.get("authorWorkExposure"),
            "provenance.independentReview.authorWorkExposure",
        )
        if exposure == "seen-before-source-review":
            exposure_text = "作成結果を見た後に典拠確認"
        elif exposure == "not-seen-before-source-review":
            exposure_text = "作成結果を見る前に典拠確認"
        else:  # pragma: no cover - schemaが閉じたenumとして拒否する
            exposure_text = exposure
        review_summary = (
            "- 独立確認: **記録あり**"
            f"（確認者: `{verifier_id}` / 役割: `{reviewer_role}` / "
            f"確認日: `{verified_on}` / {exposure_text}）"
        )
    source_text = " / ".join(f"`{source_id}`" for source_id in source_ids)

    event_kinds = [row.get("eventKind") for row in typed_rows]
    common_event_kind = event_kinds[0] if all(
        value == event_kinds[0] for value in event_kinds
    ) else None
    common_precondition, residual_preconditions = _split_common_preconditions(
        typed_rows
    )
    common_parts: list[str] = []
    if common_event_kind is not None:
        common_parts.append(_format_event_kind(common_event_kind, unresolved))
    if common_precondition is not None:
        common_parts.append(
            _format_precondition(common_precondition, schema, unresolved)
        )

    lines = [
        "# `matrixRows[]` 逐行確認シート",
        "",
        "> この文書は状況判定契約から機械生成したレビュー入力であり、"
        "レビューの実施や判断の正しさを証明する記録ではない。",
        "",
        f"- 作成者: `{author_id}`",
        review_summary,
        f"- 由来条文: {source_text}",
        f"- 完全な値: `{STATE_TRANSITION_CONTRACT_PATH.as_posix()}` の "
        "`matrixRows[]`（入力座標 = `eventKind` + `resultId` + `precondition`）",
        "",
        f"**本表の全行に共通する前提:** {' / '.join(common_parts)}"
        if common_parts
        else "**本表の全行に共通する前提:** なし",
        "",
        "## 入力 → 出力",
        "",
    ]
    headers = ["#"]
    if common_event_kind is None:
        headers.append("種別")
    headers.append("結果")
    has_residual_preconditions = any(
        residual["args"] for residual in residual_preconditions
    )
    if has_residual_preconditions:
        headers.append("前提")
    headers.extend(
        ["カウント", "打席", "打者", "走者", "アウト", "成績フラグ（trueのみ）", "特記"]
    )
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---:" if item == "#" else "---" for item in headers) + " |")

    for index, row in enumerate(typed_rows, start=1):
        result_id = _string(row.get("resultId"), f"matrixRows[{index - 1}].resultId")
        result_name = display_names.get(result_id)
        if result_name is None:
            unresolved.add(f"resultId={result_id}")
            result_name = result_id
        cells = [str(index)]
        if common_event_kind is None:
            cells.append(_format_event_kind(row.get("eventKind"), unresolved))
        cells.append(result_name)
        if has_residual_preconditions:
            cells.append(
                _format_precondition(
                    residual_preconditions[index - 1],
                    schema,
                    unresolved,
                )
            )
        cells.extend(
            [
                _format_count_effect(row.get("countEffect"), schema, unresolved),
                _format_plate_appearance(row.get("plateAppearanceEnded"), unresolved),
                _format_batter_destination(row.get("batterDestination"), unresolved),
                _format_runner_advance(
                    row.get("runnerDefaultAdvance"), schema, unresolved
                ),
                _format_out_effect(row.get("outEffect"), unresolved),
                _format_true_stat_flags(row.get("statFlags"), schema),
                _string(row.get("remarks"), f"matrixRows[{index - 1}].remarks"),
            ]
        )
        lines.append("| " + " | ".join(_markdown_text(cell) for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## 機械検査として畳む項目",
            "",
            "- 生成時: `MatrixRow` の10列、必須キー、型、未知キー拒否",
            "- リポジトリ検査: 語彙IDと述語軸の参照、入力座標の一意性、"
            "`XC-01`〜`XC-08`・`XC-10`〜`XC-12`",
            "- `XC-13` は導出原則だけを保持する。23フラグ個別の導出表は"
            "段階2であり、現段階の機械保証には含めない",
            "",
            "## 人間が判断すること",
            "",
            "- 各入力座標に対するカウント、打席、打者・走者、アウトの効果が"
            "野球規則と要件条文の意味に照らして正しいか",
            "- 投球数を含む成績計上フラグが、この投球結果の意味として正しいか",
            "- 特記が状態効果を過不足なく説明し、機械検査の範囲外を隠していないか",
            "",
        ]
    )
    if unresolved:
        lines.extend(
            [
                "## 短縮表示できなかった値",
                "",
                *[f"- `{value}`" for value in sorted(unresolved)],
                "",
            ]
        )
    return "\n".join(lines)


def generate_matrix_rows_review_sheet(
    root: Path,
    contract_path: Path,
    output_path: Path,
) -> None:
    """契約JSONから逐行確認シートを生成する。

    Args:
        root: リポジトリルート。
        contract_path: 状況判定契約JSON。
        output_path: 出力するMarkdownファイル。
    """
    try:
        raw_contract = descriptor_checker.load_json(contract_path, "状況判定契約")
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    contract = _object(raw_contract, "状況判定契約")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_matrix_rows_review_sheet(root, contract),
        encoding="utf-8",
    )


def _review_json_block(label: str, value: object) -> list[str]:
    """契約の値を省略せず日本語見出し付きで描画する。

    Args:
        label: 値の見出し。
        value: 契約の値。

    Returns:
        Markdownの行。
    """
    return [
        f"**{label}**",
        "",
        "```json",
        json.dumps(value, ensure_ascii=False, indent=2),
        "```",
        "",
    ]


def _stage2_rows_and_cases(
    contract: Mapping[str, Any], layer: str
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """規範行と、それを参照する全caseを対応付ける。

    Args:
        contract: 契約全体。
        layer: 対象の規範行層。

    Returns:
        規範行と派生caseの組。

    Raises:
        HumanReviewSignatureRecordError: 規範行とcaseが対応しない場合。
    """
    raw_rows = contract.get(layer)
    raw_cases = contract.get("cases")
    if not isinstance(raw_rows, list) or not raw_rows or not isinstance(raw_cases, list):
        raise HumanReviewSignatureRecordError(f"{layer}またはcasesが配列でない")
    rows = [_object(value, f"{layer}[{i}]") for i, value in enumerate(raw_rows)]
    cases = [_object(value, f"cases[{i}]") for i, value in enumerate(raw_cases)]
    grouped: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    used_case_ids: set[str] = set()
    for row in rows:
        if layer == "decisionRows":
            coordinate = {"branchId": row["branchId"]}
        elif layer == "operationRows":
            coordinate = {
                key: row[key] for key in ("operationKind", "payloadShape", "precondition")
            }
        else:
            coordinate = {key: row[key] for key in ("targetKind", "precondition")}
        matched: list[dict[str, Any]] = []
        for case in cases:
            row_ref = _object(case.get("rowRef"), "case.rowRef")
            if row_ref.get("layer") == layer and row_ref.get("coordinate") == coordinate:
                case_id = _string(case.get("caseId"), "case.caseId")
                if case_id in used_case_ids:
                    raise HumanReviewSignatureRecordError(f"caseの重複: {case_id}")
                used_case_ids.add(case_id)
                matched.append(case)
        if not matched:
            raise HumanReviewSignatureRecordError(f"caseのない規範行: {layer} {coordinate!r}")
        grouped.append((row, matched))
    layer_case_ids = {
        _string(case.get("caseId"), "case.caseId")
        for case in cases
        if _object(case.get("rowRef"), "case.rowRef").get("layer") == layer
    }
    if used_case_ids != layer_case_ids:
        raise HumanReviewSignatureRecordError(
            f"規範行に対応しないcase: {sorted(layer_case_ids - used_case_ids)!r}"
        )
    return grouped


def _stage2_source_ids(row: Mapping[str, Any]) -> str:
    """規範行が宣言する条文IDを表示する。

    Args:
        row: 規範行。

    Returns:
        条文IDの表示。
    """
    if "sourceClauseIds" in row:
        return " / ".join(_string_list(row["sourceClauseIds"], "sourceClauseIds"))
    if "clauseId" in row:
        return _string(row["clauseId"], "clauseId")
    remarks = _string(row.get("remarks"), "remarks")
    ids = list(dict.fromkeys(re.findall(r"FR-\d+|D-\d+|XC-\d+", remarks)))
    if not ids:
        raise HumanReviewSignatureRecordError("undo行に条文IDが見つからない")
    return " / ".join(ids) + "（remarksから抽出）"


def render_stage2_line_review_sheet(
    root: Path,
    game_end: Mapping[str, Any],
    state_transition: Mapping[str, Any],
) -> str:
    """ステップ22〜32の規範行と派生caseを未確認のレビュー入力にする。

    Args:
        root: リポジトリルート。
        game_end: 終了判定契約。
        state_transition: 状況判定契約。

    Returns:
        機械生成したMarkdown。

    Raises:
        HumanReviewSignatureRecordError: 契約が不正か行とcaseが対応しない場合。
    """
    for label, contract, schema_path in (
        ("終了判定", game_end, GAME_END_SCHEMA_PATH),
        ("状況判定", state_transition, STATE_TRANSITION_SCHEMA_PATH),
    ):
        try:
            schema = _object(
                descriptor_checker.load_json(root / schema_path, f"{label}schema"),
                f"{label}schema",
            )
            descriptor_checker._validate_instance(
                dict(contract), schema, schema, f"{label}契約"
            )
        except descriptor_checker.DescriptorCheckError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error

    lines = [
        "# TSK-538 ステップ22〜32 逐行確認シート",
        "",
        "> この文書は契約から機械生成したレビュー入力であり、",
        "レビューの実施や判断の正しさを証明する記録ではない。",
        "",
        "- 作成者: codex",
        "- 独立確認: **未実施**",
        "- 確認観点: 各前提と期待値を由来条文から独立に導出し、契約の値と照合する。",
        "- case の入力には入力座標・正規化前後・導出元の実入力・履歴文脈を載せる。",
        "  期待値には契約の出力を省略せず載せる。",
        "- 対象: 終了判定の全 decisionRows（S27 の X 表記を含む）と全 case、",
        "  状況判定の全 operationRows・undoRows とその全 case。",
        "  matrixRows は今回の規範行変更の対象外。",
        "",
    ]
    for title, contract, layers, path in (
        (
            "終了判定",
            game_end,
            ("decisionRows",),
            GAME_END_CONTRACT_PATH,
        ),
        (
            "状況判定",
            state_transition,
            ("operationRows", "undoRows"),
            STATE_TRANSITION_CONTRACT_PATH,
        ),
    ):
        lines.extend([f"## {title}", "", f"契約: `{path}`", ""])
        for layer in layers:
            groups = _stage2_rows_and_cases(contract, layer)
            lines.extend(
                [
                    f"### `{layer}` — {len(groups)} 行・{sum(len(c) for _, c in groups)} case",
                    "",
                ]
            )
            for index, (row, cases) in enumerate(groups, start=1):
                identity = row.get("branchId", row.get("operationKind", row.get("targetKind")))
                lines.extend(
                    [
                        f"#### `{layer}[{index - 1}]` — `{identity}`",
                        "",
                        f"由来条文 ID: {_stage2_source_ids(row)}",
                        "",
                    ]
                )
                lines.extend(_review_json_block("規範行（識別・前提・各列の期待値・remarks）", row))
                for case in cases:
                    case_id = _string(case.get("caseId"), "case.caseId")
                    lines.extend([f"##### case `{case_id}`", ""])
                    for key, label in (
                        ("inputCoordinate", "入力座標"),
                        ("raw", "入力（正規化前）"),
                        ("normalizationRuleId", "正規化規則"),
                        ("normalized", "入力（正規化後）"),
                        ("derivedSourceInput", "派生軸の導出元の実入力"),
                        ("historyInput", "履歴の入力と前後の状態"),
                        ("expected", "期待値（履歴の各要素の種別と差分を含む）"),
                        ("decision", "期待する終了判定"),
                    ):
                        if key in case:
                            lines.extend(_review_json_block(label, case[key]))
    lines.extend(
        [
            "## 条文が決めていない点・機械検査の限界",
            "",
            "- 条文未確定事項は [未解消レポート §5]"
            "(../appendix-e-golden-vectors/unresolved-report.md"
            "#5-ゲート⑥で確認した条文未確定事項2026-10-14) の"
            " G6-E01〜E02・E04〜E14（TSK-545）、G6-E03（S22 の PO 裁定後に TSK-544）"
            " と G6-S01〜S11（TSK-544）を参照する。",
            "- 成立段数の値が条文に照らして正しいことは、ADR-003 v0.7 D-11 の",
            "  派生軸の関数性検査だけでは証明できない。ステップ26〜28の各値は独立確認を要する。",
            "- このシートは契約の転記と網羅性だけを機械的に保証する。",
            "  期待値の意味の確認は未実施である。",
            "",
        ]
    )
    return "\n".join(lines)


def generate_stage2_line_review_sheet(root: Path, output_path: Path) -> None:
    """既存の契約2件からステップ33の逐行確認シートを生成する。

    Args:
        root: リポジトリルート。
        output_path: 出力先のMarkdownファイル。
    """
    try:
        game_end = descriptor_checker.load_json(
            root / GAME_END_CONTRACT_PATH, "終了判定契約"
        )
        state_transition = descriptor_checker.load_json(
            root / STATE_TRANSITION_CONTRACT_PATH, "状況判定契約"
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_stage2_line_review_sheet(
            root,
            _object(game_end, "終了判定契約"),
            _object(state_transition, "状況判定契約"),
        ),
        encoding="utf-8",
    )


def validate_signature_record(
    root: Path,
    record: Mapping[str, Any],
    *,
    schema_value: Mapping[str, Any] | None = None,
) -> None:
    """署名記録の形式・対象digest・宣誓記載だけを検証する。

    Args:
        root: リポジトリルート。
        record: 検証する署名記録。
        schema_value: テスト用の署名記録schema差し替え。

    Raises:
        HumanReviewSignatureRecordError: 宣言形式、対象digest、記録上の
            識別子差、または宣誓記載を確認できない場合。

    Note:
        レビューの実施、確認者が実際に別人であること、条文からの直接
        レビュー、記載内容の真実性、および判断の正しさは保証しない。
    """
    schema = _load_schema(root) if schema_value is None else dict(schema_value)
    policy = _policy(schema)
    try:
        descriptor_checker._validate_instance(
            dict(record), schema, schema, "署名記録"
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error

    author_id = _string(record.get("artifactAuthorId"), "artifactAuthorId")
    reviewer_id = _string(record.get("recordedReviewerId"), "recordedReviewerId")
    if author_id == reviewer_id:
        raise HumanReviewSignatureRecordError(
            "作成者と確認者の記録上の識別子が同一である"
        )

    recorded_on = _string(record.get("recordedOn"), "recordedOn")
    try:
        date.fromisoformat(recorded_on)
    except ValueError as error:
        raise HumanReviewSignatureRecordError(
            f"recordedOnが実在するISO日付でない: {recorded_on!r}"
        ) from error

    methods = _object(policy["recordedMethods"], "recordedMethods")
    recorded_method = _string(record.get("recordedMethod"), "recordedMethod")
    if recorded_method not in methods:
        raise HumanReviewSignatureRecordError(
            f"未宣言の記録済み確認方法である: {recorded_method!r}"
        )

    subject = _object(record.get("subject"), "subject")
    digest_rule = _object(policy["subjectDigest"], "subjectDigest")
    subject_path = _repository_subject_path(
        root,
        _string(subject.get("path"), "subject.path"),
        _string(digest_rule.get("pathRoot"), "subjectDigest.pathRoot"),
    )
    try:
        subject_value = descriptor_checker.load_json(subject_path, "署名対象")
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    safe_integer_limit = digest_rule["safeIntegerLimit"]
    if not isinstance(safe_integer_limit, int) or isinstance(
        safe_integer_limit, bool
    ):
        raise HumanReviewSignatureRecordError(
            "subjectDigest.safeIntegerLimitが整数でない"
        )
    try:
        actual_digest = compute_subject_digest(subject_value, safe_integer_limit)
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    recorded_digest = _string(subject.get("digest"), "subject.digest")
    if recorded_digest != actual_digest:
        raise HumanReviewSignatureRecordError(
            "署名対象digestが現物と不一致: "
            f"recorded={recorded_digest}; actual={actual_digest}"
        )

    declared_attestations = _object(
        policy["attestationItems"], "attestationItems"
    )
    recorded: dict[str, object] = {}
    for index, raw_attestation in enumerate(record["attestations"]):
        attestation = _object(raw_attestation, f"attestations[{index}]")
        attestation_id = _string(
            attestation.get("attestationId"),
            f"attestations[{index}].attestationId",
        )
        if attestation_id in recorded:
            raise HumanReviewSignatureRecordError(
                f"宣誓記載が重複している: {attestation_id!r}"
            )
        recorded[attestation_id] = attestation["recordedResponse"]
    if set(recorded) != set(declared_attestations):
        raise HumanReviewSignatureRecordError(
            "宣誓記載がexact-set不一致: "
            f"missing={sorted(set(declared_attestations) - set(recorded))!r}; "
            f"unexpected={sorted(set(recorded) - set(declared_attestations))!r}"
        )
    for attestation_id, response in recorded.items():
        declaration = _object(
            declared_attestations[attestation_id],
            f"attestationItems.{attestation_id}",
        )
        accepted = declaration["acceptedRecordedResponses"]
        if not isinstance(accepted, list) or not _response_is_accepted(
            response, accepted
        ):
            raise HumanReviewSignatureRecordError(
                f"宣誓の記録済み応答が充足値でない: {attestation_id!r}"
            )


# 今回限定手続きのPR識別子。subjectの基準commit/hashは資産宣言から読む。
_GATE6_INTRODUCTION_PR = 183
GATE6_CARRY_PATH = PurePosixPath("contracts/state-transition/gate6_subject_carry_v1.json")
GATE6_CARRY_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/gate6_subject_carry_schema_v1.json"
)
_GATE6_RETAINED_PATHS = frozenset({
    "docs/features/adr003-stage2-runtime/signatures/gate6-game-end.json",
    "docs/features/adr003-stage2-runtime/signatures/gate6-state-transition.json",
    "docs/features/adr003-stage2-runtime/step33_line_review.md",
    str(SCHEMA_PATH),
})


def _carry_git_bytes(root: Path, arguments: list[str]) -> bytes:
    """carryの固定履歴をGitの読取専用コマンドだけで照合する。"""
    if not arguments or arguments[0] not in {"show", "rev-parse", "merge-base"}:
        raise HumanReviewSignatureRecordError("carryのGitコマンドが読取集合外")
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=root, capture_output=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HumanReviewSignatureRecordError("carryの固定Git履歴を読めない") from error
    if result.returncode != 0:
        raise HumanReviewSignatureRecordError("carryの固定Git履歴が欠落または祖先関係が不正")
    return result.stdout


def _carry_core_guard(root: Path) -> Any:
    """同checkoutの既core_guardを再利用する。別の委任判定器は作らない。"""
    spec = importlib.util.spec_from_file_location(
        "gate6_existing_core_guard", root / "scripts/core_guard.py",
    )
    if spec is None or spec.loader is None:
        raise HumanReviewSignatureRecordError("既core_guardを読めない")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _carry_projection(subject: Mapping[str, Any], projection: str) -> object:
    """旧recordが名指した範囲だけを取り出し、matrix確認へ広げない。"""
    if projection == "operation-undo-and-cases":
        return {
            "operationRows": subject["operationRows"],
            "undoRows": subject["undoRows"],
            "cases": [case for case in subject["cases"]
                      if case["rowRef"]["layer"] in {"operationRows", "undoRows"}],
        }
    if projection == "decision-cases-and-validation-errors":
        return {key: subject[key] for key in ("decisionRows", "cases", "validationErrors")}
    raise HumanReviewSignatureRecordError("旧署名範囲の射影が未宣言")


def _carry_array(document: dict[str, Any], pointer: str) -> list[Any]:
    """許可済み3位置のappend対象を返す。任意JSON patchは受けない。"""
    if pointer == "/matrixRows":
        return document["matrixRows"]
    if pointer == "/cases":
        return document["cases"]
    if pointer == "/mustOperationCoverage/mappings/0/rowRefs":
        return document["mustOperationCoverage"]["mappings"][0]["rowRefs"]
    raise HumanReviewSignatureRecordError("carry append位置が許可集合外")


_GATE6_T1_APPEND_PR = 185
_GATE6_T1_APPEND_BRANCH = "feature/mvp-t1-input-closure"
GATE6_T1_APPEND_PATH = PurePosixPath("contracts/state-transition/gate6_t1_input_append_v1.json")
GATE6_T1_APPEND_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/gate6_t1_input_append_schema_v1.json"
)
_GATE6_T1_CASE_IDS = (
    "ST-RBI-03-HELD-TOO-LONG-01", "ST-RBI-03-UNNECESSARY-THROW-01",
    "ST-RBI-04-HELD-TOO-LONG-01", "ST-RBI-04-UNNECESSARY-THROW-01",
    "ST-RBI-08-RESTART-NONCAUSAL-01",
)
@dataclass(frozen=True)
class _Gate6Baseline:
    """私有factoryがGitの導入baseとanchorを照合した不変の原本集合。"""

    base: str
    anchor: str
    policy_digest: str
    materials: Mapping[str, bytes]


def _gate6_ready_values(root: Path) -> tuple[str, str, str]:
    """既閉schemaのready形から重複していた参照値を取り出す。"""
    schema = _object(descriptor_checker.load_json(root / GATE6_T1_APPEND_SCHEMA_PATH,
                                                "T1 append schema"), "T1 append schema")
    branches = [branch for branch in schema.get("oneOf", [])
                if isinstance(branch, dict) and branch.get("properties", {}).get(
                    "status", {}).get("const") == "candidate-for-delegated-verification"]
    if len(branches) != 1:
        raise HumanReviewSignatureRecordError("T1 append schemaのready形が一意でない")
    properties = branches[0]["properties"]
    anchor = properties["anchor"]["properties"]
    commit = anchor["commit"]["const"]
    carry_hash = anchor["carryRawSha256"]["const"]
    policy_hash = properties["authority"]["properties"]["sourcePolicySha256"]["const"]
    if (not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None
            or any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None
                   for v in (carry_hash, policy_hash))):
        raise HumanReviewSignatureRecordError("T1 append schemaの固定参照型が不正")
    return commit, carry_hash, policy_hash


def _gate6_git_object(root: Path, revision: str, path: str | PurePosixPath) -> dict[str, Any]:
    """Git原本も既strict duplicate-key readerで解釈する。"""
    return _object(json.loads(_carry_git_bytes(root, ["show", f"{revision}:{path}"]),
                             object_pairs_hook=descriptor_checker._reject_duplicate_keys),
                   "Gate6 Git原本")


def _gate6_baseline_body(
    root: Path, record: Mapping[str, Any] | None = None, *, actual_base: str | None = None,
) -> _Gate6Baseline:
    """最終eventのbase一致を原本選択より先に検査する。localは技術検査だけ。"""
    if record is None:
        record = _object(descriptor_checker.load_json(root / GATE6_T1_APPEND_PATH,
                                                    "T1 append"), "T1 append")
    base = record["authority"]["baseRevision"]
    if actual_base is not None and actual_base != base:
        raise HumanReviewSignatureRecordError("T1 appendの最終PR baseと記録が不一致")
    if not isinstance(base, str) or re.fullmatch(r"[0-9a-f]{40}", base) is None:
        raise HumanReviewSignatureRecordError("T1 appendの導入baseが不正")
    anchor, carry_hash, policy_hash = _gate6_ready_values(root)
    if (record["anchor"] != {"commit": anchor, "carryRawSha256": carry_hash}
            or record["authority"]["sourcePolicySha256"] != policy_hash):
        raise HumanReviewSignatureRecordError("T1 appendのschema/record固定参照が不一致")
    carry = _gate6_git_object(root, base, GATE6_CARRY_PATH)
    old_schema = _gate6_git_object(root, base, GATE6_CARRY_SCHEMA_PATH)
    descriptor_checker._validate_instance(carry, old_schema, old_schema, "base旧carry")
    parents = _carry_git_bytes(root, ["rev-parse", f"{base}^@"]).decode("ascii").split()
    if parents != [carry["authority"]["baseRevision"], anchor]:
        raise HumanReviewSignatureRecordError("T1 appendの導入baseの2親/anchorが不一致")
    _carry_git_bytes(root, ["merge-base", "--is-ancestor", anchor, base])
    paths = {str(GATE6_CARRY_PATH), str(GATE6_CARRY_SCHEMA_PATH),
             str(STATE_TRANSITION_CONTRACT_PATH), str(GAME_END_CONTRACT_PATH),
             carry["authority"]["path"], *_GATE6_RETAINED_PATHS}
    materials = {}
    for path in paths:
        raw = _carry_git_bytes(root, ["show", f"{base}:{path}"])
        if raw != _carry_git_bytes(root, ["show", f"{anchor}:{path}"]):
            raise HumanReviewSignatureRecordError("anchorから導入baseへ旧保存原本が変わった")
        materials[path] = raw
    if (hashlib.sha256(materials[str(GATE6_CARRY_PATH)]).hexdigest() != carry_hash
            or hashlib.sha256(materials[carry["authority"]["path"]]).hexdigest() != policy_hash
            or carry["authority"]["sha256"] != policy_hash):
        raise HumanReviewSignatureRecordError("T1 appendの旧carry/policy実hashが不一致")
    return _Gate6Baseline(base, anchor, policy_hash, MappingProxyType(materials))


def _gate6_baseline(
    root: Path, record: Mapping[str, Any] | None = None, *, actual_base: str | None = None,
) -> _Gate6Baseline:
    """不明なGit/閉schemaを固定基準選択の成功へfallbackさせない。"""
    try:
        return _gate6_baseline_body(root, record, actual_base=actual_base)
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError(str(error)) from error


class _Gate6CurrentReader:
    """現checkoutを読むprivate入口。公開APIで読取revisionを選ばせない。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.head = _carry_git_bytes(root, ["rev-parse", "HEAD"]).decode("ascii").strip()

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """現在の検査対象byteを返す。"""
        return (self.root / path).read_bytes()

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """既strict readerを使い、旧テストの読取境界も保持する。"""
        return _object(descriptor_checker.load_json(self.root / path, label), label)


class _Gate6AcceptedAnchorReader(_Gate6CurrentReader):
    """固定受理anchorだけを読む。任意commitを受ける引数は持たない。"""

    def __init__(self, root: Path, *, baseline: _Gate6Baseline | None = None) -> None:
        self.root = root
        self.baseline = _gate6_baseline(root) if baseline is None else baseline
        self.head = self.baseline.anchor

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """実Gitから固定blobを読む。checkoutや旧コードを実行しない。"""
        return _carry_git_bytes(self.root, ["show", f"{self.head}:{path}"])

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """固定snapshotのschema/記録/subjectを重複key拒否で読む。"""
        return _object(json.loads(self.read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)


def _gate6_legacy_policy_prefix(
    authority: Mapping[str, Any], policy: Mapping[str, Any],
) -> dict[str, Any]:
    """旧PR183は新appendなしで、旧hashと同じ原文の唯一prefixを復元する。"""
    matches = []
    for count in range(1, len(policy["targets"]) + 1):
        candidate = {**policy, "targets": policy["targets"][:count]}
        raw = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if hashlib.sha256(raw).hexdigest() == authority["sha256"]:
            matches.append(candidate)
    if (len(matches) != 1 or matches[0].get("enabled") is not True
            or {"pr": _GATE6_INTRODUCTION_PR, "branch": authority["branch"]}
            not in matches[0]["targets"]):
        raise HumanReviewSignatureRecordError("旧carry policy原文の唯一prefixを復元できない")
    return matches[0]


def _validate_gate6_carry_policy(
    root: Path, head: str, guard: Any, authority: Mapping[str, Any],
    policy: Mapping[str, Any], policy_digest: str, policy_bytes: bytes,
    baseline: _Gate6Baseline | None = None,
) -> None:
    """既受理policyの不変部分と対象表の追記だけを技術的に継承する。"""
    if (
        hashlib.sha256(policy_bytes).hexdigest() != policy_digest
        or authority["repository"] != policy["repository"]
        or {"pr": authority["pr"], "branch": authority["branch"]} not in policy["targets"]
    ):
        raise HumanReviewSignatureRecordError("carryの委任policy・対象が不一致")
    if authority["sha256"] == policy_digest:
        return
    if (authority["pr"] != _GATE6_INTRODUCTION_PR
            or authority["path"] != str(guard.DELEGATION_POLICY_PATH)):
        raise HumanReviewSignatureRecordError("carryの既受理policy識別が不一致")
    if baseline is None:
        accepted = _gate6_legacy_policy_prefix(authority, policy)
        accepted_digest = authority["sha256"]
    else:
        accepted = _object(json.loads(baseline.materials[authority["path"]],
                         object_pairs_hook=descriptor_checker._reject_duplicate_keys),
                         "base旧policy")
        accepted_digest = hashlib.sha256(baseline.materials[authority["path"]]).hexdigest()
    if (authority["sha256"] != accepted_digest
            or authority["repository"] != accepted["repository"]
            or {"pr": authority["pr"], "branch": authority["branch"]} not in accepted["targets"]
            or {key: value for key, value in policy.items() if key != "targets"}
            != {key: value for key, value in accepted.items() if key != "targets"}
            or policy["targets"][:len(accepted["targets"])] != accepted["targets"]):
        raise HumanReviewSignatureRecordError("carryの既受理policyに追記以外の変更がある")


def _validate_gate6_carry_body(
    root: Path, reader: _Gate6CurrentReader,
) -> dict[str, Any]:
    """旧記録と現在値の技術的継承だけを検査し、委任受理は返さない。"""
    schema = reader.load_json(GATE6_CARRY_SCHEMA_PATH, "carry schema")
    carry = reader.load_json(GATE6_CARRY_PATH, "carry")
    descriptor_checker._validate_instance(carry, schema, schema, "carry")
    signature_schema = reader.load_json(SCHEMA_PATH, "署名schema")
    limit = _policy(signature_schema)["subjectDigest"]["safeIntegerLimit"]
    authority = carry["authority"]
    base = authority["baseRevision"]
    head = reader.head
    _carry_git_bytes(root, ["merge-base", "--is-ancestor", base, head])
    guard = _carry_core_guard(root)
    try:
        policy, policy_digest = guard._load_delegation_policy(root, head)
    except guard.GuardError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    _validate_gate6_carry_policy(root, head, guard, authority, policy, policy_digest,
                                 reader.read_bytes(authority["path"]),
                                 getattr(reader, "baseline", None))
    retained = {entry["path"]: entry["sha256"] for entry in carry["retainedDocuments"]}
    if set(retained) != _GATE6_RETAINED_PATHS or len(retained) != len(carry["retainedDocuments"]):
        raise HumanReviewSignatureRecordError("carryの旧記録保存集合がexact-set不一致")
    for path, expected_hash in retained.items():
        current = reader.read_bytes(path)
        if (
            current != _carry_git_bytes(root, ["show", f"{base}:{path}"])
            or hashlib.sha256(current).hexdigest() != expected_hash
        ):
            raise HumanReviewSignatureRecordError(
                "旧署名・日付・確認sheet・schemaのbyteが変更された"
            )
    receipt = carry["adoptionReceipt"]
    if (
        compute_subject_digest(receipt, limit) != carry["adoptionReceiptDigest"]
        or receipt.get("pr") != authority["pr"]
        or receipt.get("status") != "accepted-partial-contract-reflection"
        or receipt.get("human_personal_line_review_or_signature") is not False
    ):
        raise HumanReviewSignatureRecordError("carryの既受理記録が不一致または本人確認を主張した")
    subjects = {entry["path"]: entry for entry in carry["subjects"]}
    if set(subjects) != {str(STATE_TRANSITION_CONTRACT_PATH), str(GAME_END_CONTRACT_PATH)}:
        raise HumanReviewSignatureRecordError("carryの対象2契約がexact-set不一致")
    for path, entry in subjects.items():
        anchor = entry["oldSubjectCommit"]
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", anchor, base])
        old_bytes = _carry_git_bytes(root, ["show", f"{anchor}:{path}"])
        old = _object(
            json.loads(old_bytes, object_pairs_hook=descriptor_checker._reject_duplicate_keys),
            "旧署名対象",
        )
        if (
            hashlib.sha256(old_bytes).hexdigest() != entry["oldSubjectRawSha256"]
            or compute_subject_digest(old, limit) != entry["oldSubjectDigest"]
        ):
            raise HumanReviewSignatureRecordError("carryの旧対象raw/JCS digestが不一致")
        record = reader.load_json(entry["legacyRecordPath"], "旧署名記録")
        if record["subject"] != {"path": path, "digest": entry["oldSubjectDigest"]}:
            raise HumanReviewSignatureRecordError("旧署名記録と実対象が不一致")
        # 既validatorは変更せず、旧対象の隔離rootで元の記録をそのまま検証する。
        with tempfile.TemporaryDirectory(prefix="pitchlog-gate6-carry-") as temporary:
            legacy_root = Path(temporary)
            target = legacy_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old_bytes)
            validate_signature_record(legacy_root, record, schema_value=signature_schema)
        current = reader.load_json(path, "現対象")
        if compute_subject_digest(current, limit) != entry["currentSubjectDigest"]:
            raise HumanReviewSignatureRecordError("carryの現対象digestが不一致")
        projection = entry["projection"]
        if any(compute_subject_digest(_carry_projection(value, projection), limit)
               != entry["projectionDigest"] for value in (old, current)):
            raise HumanReviewSignatureRecordError("旧署名範囲の不変射影が不一致")
        expected_pointers = {"/inputAxesDescriptor/digest"}
        if path == str(STATE_TRANSITION_CONTRACT_PATH):
            expected_pointers |= {
                "/matrixRows", "/cases", "/mustOperationCoverage/mappings/0/rowRefs",
            }
        changes = entry["allowedChanges"]
        if (
            {change["pointer"] for change in changes} != expected_pointers
            or len(changes) != len(expected_pointers)
        ):
            raise HumanReviewSignatureRecordError("carryの許可差分位置がexact-set不一致")
        rebuilt = copy.deepcopy(old)
        for change in changes:
            if change["kind"] == "replace":
                if rebuilt["inputAxesDescriptor"]["digest"] != change["before"]:
                    raise HumanReviewSignatureRecordError("carry差分のbeforeが不一致")
                rebuilt["inputAxesDescriptor"]["digest"] = change["after"]
            else:
                array = _carry_array(rebuilt, change["pointer"])
                if len(array) != change["beforeCount"]:
                    raise HumanReviewSignatureRecordError("carry差分の旧prefix件数が不一致")
                if (
                    change["pointer"] == "/cases"
                    and [case["caseId"] for case in change["values"]] != carry["changedCaseIds"]
                ):
                    raise HumanReviewSignatureRecordError("carryの新2caseが不一致")
                array.extend(change["values"])
        if compute_subject_digest(rebuilt, limit) != entry["currentSubjectDigest"]:
            raise HumanReviewSignatureRecordError("現対象にcarry許可外の差分がある")
    return carry



def _validate_gate6_subject_carry(root: Path) -> dict[str, Any]:
    """現在値の旧carry検査は共有bodyを通す。新appendとは別のまま保つ。"""
    return _validate_gate6_carry_body(root, _Gate6CurrentReader(root))



def validate_gate6_subject_carry(root: Path) -> None:
    """技術的不変条件だけを検査する。最終委任受理・本人署名を表明しない。"""
    try:
        if _ordinary_present(root):
            if (root / _STRIKEOUT_REFERENCE_PATH).exists():
                _ordinary_strikeout_current_body(root)
            elif (root / "contracts/state-transition/terminal_pitch_cases_v1.json").exists():
                _ordinary_terminal_body(root)
            else:
                _ordinary_body(root)
        elif _gate6_t1_append_is_ready(root):
            _validate_gate6_t1_input_append(root)
        else:
            _validate_gate6_subject_carry(root)
    except (
        KeyError, TypeError, ValueError, OSError, descriptor_checker.DescriptorCheckError,
    ) as error:
        raise HumanReviewSignatureRecordError(str(error)) from error


def _validate_gate6_checkout(root: Path, event: Any) -> None:
    """署名対象headと同一treeの正確なCI mergeだけを追加で許す。"""
    if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None
           for value in (event.base_sha, event.head_sha)):
        raise HumanReviewSignatureRecordError("最終eventのGit識別値が不正")
    actual = _carry_git_bytes(root, ["rev-parse", "HEAD"]).decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{40}", actual) is None:
        raise HumanReviewSignatureRecordError("CI checkoutのGit識別値が不正")
    if actual == event.head_sha:
        return
    parents = _carry_git_bytes(root, ["rev-parse", f"{actual}^@"]).decode("ascii").split()
    if parents != [event.base_sha, event.head_sha]:
        raise HumanReviewSignatureRecordError("CI checkoutの親が最終eventと不一致")
    _carry_git_bytes(root, ["merge-base", "--is-ancestor", event.base_sha, event.head_sha])
    actual_tree = _carry_git_bytes(root, ["rev-parse", f"{actual}^{{tree}}"])
    head_tree = _carry_git_bytes(root, ["rev-parse", f"{event.head_sha}^{{tree}}"])
    if (re.fullmatch(rb"[0-9a-f]{40}\s*", actual_tree) is None
            or actual_tree != head_tree):
        raise HumanReviewSignatureRecordError("CI checkoutの全treeが最終headと不一致")


def _validate_gate6_head_bytes(root: Path, event: Any, authority: Mapping[str, Any]) -> None:
    """検査入力/実行validatorが最終eventのGit blobと一致することを確認する。"""
    _validate_gate6_checkout(root, event)
    paths = {
        str(GATE6_CARRY_PATH), str(GATE6_CARRY_SCHEMA_PATH),
        str(STATE_TRANSITION_CONTRACT_PATH), str(GAME_END_CONTRACT_PATH),
        authority["path"], "scripts/check_human_review_signature.py",
        "tests/test_human_review_signature.py",
        "docs/features/appendix-e-golden-vectors/matrix_rows_line_review.md",
        *_GATE6_RETAINED_PATHS,
    }
    for path in paths:
        committed = _carry_git_bytes(root, ["show", f"{event.head_sha}:{path}"])
        if (root / path).read_bytes() != committed:
            raise HumanReviewSignatureRecordError("carry検査入力の現byteと最終HEADが不一致")
    executed_source = Path(__file__).read_bytes()
    if executed_source != (root / "scripts/check_human_review_signature.py").read_bytes():
        raise HumanReviewSignatureRecordError("実行validatorと対象checkoutが不一致")


def validate_delegated_gate6_subject_carry(root: Path, event: Any) -> None:
    """最終event/Git byte/既core_guard証拠を満たす今回限定carryだけを受理する。"""
    if event is None:
        raise HumanReviewSignatureRecordError("最終PR eventが未提供")
    if event.number != _GATE6_INTRODUCTION_PR:
        raise HumanReviewSignatureRecordError("本carryの新受理は導入PRだけに限定する")
    carry = _validate_gate6_subject_carry(root)
    authority = carry["authority"]
    if (
        event.base_sha != authority["baseRevision"] or event.number != authority["pr"]
        or event.repository != authority["repository"]
        or event.head_repository != authority["repository"]
        or event.head_branch != authority["branch"]
    ):
        raise HumanReviewSignatureRecordError("carryと最終PR eventの対象版が不一致")
    _validate_gate6_head_bytes(root, event, authority)
    guard = _carry_core_guard(root)
    try:
        guard.verify_delegated_confirmation(root, event)
    except guard.GuardError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error


def validate_other_pr_gate6_carry_unchanged(root: Path, event: Any) -> None:
    """別PRはevent.baseの既受理carry/schema/対象と同値の時だけ継承する。"""
    if event is None:
        raise HumanReviewSignatureRecordError("最終PR eventが未提供")
    carry = _validate_gate6_subject_carry(root)
    authority = carry["authority"]
    if (
        type(event.number) is not int or event.number <= 0
        or event.number == authority["pr"]
        or event.repository != authority["repository"]
        or event.head_repository != authority["repository"]
        or not isinstance(event.head_branch, str)
        or not event.head_branch.startswith(("feature/", "fix/"))
        or any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None
               for value in (event.base_sha, event.head_sha))
    ):
        raise HumanReviewSignatureRecordError("別PRのcarry継承eventが不正")
    _validate_gate6_head_bytes(root, event, authority)
    schema = _object(descriptor_checker.load_json(root / GATE6_CARRY_SCHEMA_PATH,
                                                "carry schema"), "carry schema")
    current_values = {str(GATE6_CARRY_PATH): carry, str(GATE6_CARRY_SCHEMA_PATH): schema}
    for entry in carry["subjects"]:
        current_values[entry["path"]] = descriptor_checker.load_json(
            root / entry["path"], "carry対象",
        )
    limit = _policy(_load_schema(root))["subjectDigest"]["safeIntegerLimit"]
    for path, current in current_values.items():
        raw = _carry_git_bytes(root, ["show", f"{event.base_sha}:{path}"])
        previous = json.loads(raw, object_pairs_hook=descriptor_checker._reject_duplicate_keys)
        if compute_subject_digest(previous, limit) != compute_subject_digest(current, limit):
            raise HumanReviewSignatureRecordError("別PRで既受理carry/schema/対象を変更している")


def _gate6_t1_append_is_ready(root: Path) -> bool:
    """未供給を旧carryの不変検査へ限定し、PR185の新受理とは分ける。"""
    path = root / GATE6_T1_APPEND_PATH
    if not path.exists():
        return False
    record = _object(descriptor_checker.load_json(path, "T1 append"), "T1 append")
    return record.get("status") != "pending-root-values"


def _validate_t1_append_correspondence(changes: Mapping[str, Any]) -> None:
    """固定5caseと追加行/coverageを同順序で照合する。意味計算はしない。"""
    try:
        import representative_selection as selection_checker
    except ModuleNotFoundError:  # pragma: no cover - package経路
        from scripts import representative_selection as selection_checker
    rows = changes["/matrixRows"]["values"]
    cases = changes["/cases"]["values"]
    refs = changes["/mustOperationCoverage/mappings/0/rowRefs"]["values"]
    if (len(rows) != 5 or len(cases) != 5 or len(refs) != 5
            or tuple(case["caseId"] for case in cases) != _GATE6_T1_CASE_IDS):
        raise HumanReviewSignatureRecordError("T1 appendの固定5case/5rowがexact-set不一致")
    coordinates = []
    for row, case, ref in zip(rows, cases, refs, strict=True):
        coordinate = {key: row[key] for key in ("eventKind", "resultId", "precondition")}
        expected_ref = {"layer": "matrixRows", "coordinate": coordinate}
        output = {key: value for key, value in row.items()
                  if key not in {"eventKind", "resultId", "precondition", "remarks"}}
        if (case["rowRef"] != expected_ref or ref != expected_ref
                or case["expected"] != output
                or set(output) != {"countEffect", "plateAppearanceEnded", "batterDestination",
                                   "runnerDefaultAdvance", "outEffect", "statFlags"}
                or case["inputCoordinate"].get("eventKind") != row["eventKind"]
                or case["inputCoordinate"].get("resultId") != row["resultId"]
                or not selection_checker.predicate_holds(row["precondition"],
                                                       case["inputCoordinate"])):
            raise HumanReviewSignatureRecordError("T1 appendのrow/case/coverage対応が不一致")
        coordinates.append(coordinate)
    if len({compute_subject_digest(value, 9007199254740991)
            for value in coordinates}) != 5:
        raise HumanReviewSignatureRecordError("T1 appendの追加rowが重複する")


def _validate_gate6_t1_input_append_body(
    root: Path, baseline: _Gate6Baseline | None = None,
    *, reader: _Gate6CurrentReader | None = None,
) -> dict[str, Any]:
    """旧受理を固定anchorで再検査し、PR185の有限差分だけを再構成する。"""
    reader = _Gate6CurrentReader(root) if reader is None else reader
    schema = reader.load_json(GATE6_T1_APPEND_SCHEMA_PATH, "T1 append schema")
    record = reader.load_json(GATE6_T1_APPEND_PATH, "T1 append")
    descriptor_checker._validate_instance(record, schema, schema, "T1 append")
    if record["status"] != "candidate-for-delegated-verification":
        raise HumanReviewSignatureRecordError("T1 appendのroot正式値が未確定")
    _exact_keys(record, {"schemaVersion", "evidenceKind", "status", "authority", "anchor",
                         "changedCaseIds", "subjects", "scopeReceipt"}, "T1 append")
    if (type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1
            or record["evidenceKind"] != "t1-input-append"):
        raise HumanReviewSignatureRecordError("T1 appendの記録型が不一致")
    receipt = _object(record["scopeReceipt"], "T1 scope receipt")
    flags = {"personalReviewClaimed", "P6FullAcceptance", "P7FullAcceptance", "T1BodyStartComplete"}
    _exact_keys(receipt, {"kind", "evidenceLabel", *flags}, "T1 scope receipt")
    if (receipt["kind"] != "bounded-technical-candidate"
            or not isinstance(receipt["evidenceLabel"], str) or not receipt["evidenceLabel"]
            or any(receipt[key] is not False for key in flags)):
        raise HumanReviewSignatureRecordError("T1 appendを本人確認/全成立へ拡張している")
    baseline = _gate6_baseline(root, record) if baseline is None else baseline
    authority = _object(record["authority"], "T1 authority")
    _exact_keys(authority, {"repository", "pr", "branch", "path",
                            "sourcePolicySha256", "baseRevision"},
                "T1 authority")
    _exact_keys(_object(record["anchor"], "T1 anchor"), {"commit", "carryRawSha256"}, "T1 anchor")
    if (not isinstance(authority["baseRevision"], str)
            or re.fullmatch(r"[0-9a-f]{40}", authority["baseRevision"]) is None
            or authority["sourcePolicySha256"] != baseline.policy_digest):
        raise HumanReviewSignatureRecordError("T1 appendのauthority識別値が不正")
    if (type(authority["pr"]) is not int or authority["pr"] != _GATE6_T1_APPEND_PR
            or authority["branch"] != _GATE6_T1_APPEND_BRANCH
            or authority["repository"] != "masaki1025/pitchlog"
            or authority["path"] != "docs/features/mvp-delegated-core-review/policy.json"
            or record["anchor"]["commit"] != baseline.anchor
            or tuple(record["changedCaseIds"]) != _GATE6_T1_CASE_IDS):
        raise HumanReviewSignatureRecordError("T1 appendの固定authority/anchor/caseが不一致")
    _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                           baseline.anchor, authority["baseRevision"]])
    _carry_git_bytes(root, ["merge-base", "--is-ancestor", authority["baseRevision"], reader.head])
    guard = _carry_core_guard(root)
    try:
        policy, digest = guard._load_delegation_policy(root, reader.head)
    except guard.GuardError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    # 記録は固定の委任根拠を名指す。現policy hashは最終core_guard証拠で別に照合する。
    if (hashlib.sha256(reader.read_bytes(authority["path"])).hexdigest() != digest
            or {"pr": _GATE6_T1_APPEND_PR, "branch": _GATE6_T1_APPEND_BRANCH}
            not in policy["targets"]):
        raise HumanReviewSignatureRecordError("T1 appendの現policy/対象が不一致")
    anchor = _Gate6AcceptedAnchorReader(root, baseline=baseline)
    for path in (GATE6_CARRY_PATH, GATE6_CARRY_SCHEMA_PATH):
        if reader.read_bytes(path) != baseline.materials[str(path)]:
            raise HumanReviewSignatureRecordError("旧carry/schemaの固定受理byteが変更された")
    if record["anchor"]["carryRawSha256"] != hashlib.sha256(
            baseline.materials[str(GATE6_CARRY_PATH)]).hexdigest():
        raise HumanReviewSignatureRecordError("固定旧carry hashが不一致")
    old_carry = _validate_gate6_carry_body(root, anchor)
    # 新記録自身のcurrent policy hashが一致しても、旧targetの同時改変は許さない。
    _validate_gate6_carry_policy(root, reader.head, guard, old_carry["authority"],
                                policy, digest, reader.read_bytes(authority["path"]), baseline)
    for retained in old_carry["retainedDocuments"]:
        if reader.read_bytes(retained["path"]) != anchor.read_bytes(retained["path"]):
            raise HumanReviewSignatureRecordError("旧本人記録・sheetの固定byteが変更された")
    limit = _policy(anchor.load_json(SCHEMA_PATH, "固定署名schema"))[
        "subjectDigest"]["safeIntegerLimit"]
    entries = {entry["path"]: entry for entry in record["subjects"]}
    if len(entries) != 2 or set(entries) != {
        str(STATE_TRANSITION_CONTRACT_PATH), str(GAME_END_CONTRACT_PATH),
    } or len(record["subjects"]) != 2:
        raise HumanReviewSignatureRecordError("T1 appendの対象2subjectがexact-set不一致")
    projections = {entry["path"]: entry["projection"] for entry in old_carry["subjects"]}
    descriptor = reader.load_json("contracts/state-transition/input_axes_descriptor_v1.json",
                                  "現descriptor")
    descriptor_digest = descriptor_checker.compute_descriptor_digest(descriptor)
    if descriptor.get("digest") != descriptor_digest:
        raise HumanReviewSignatureRecordError("現descriptorのdigestが実射影と不一致")
    for path, entry in entries.items():
        _exact_keys(entry, {"path", "anchorRawSha256", "anchorDigest", "currentRawSha256",
                           "currentDigest", "projection", "projectionDigest", "allowedChanges"},
                    "T1 subject")
        old_raw = anchor.read_bytes(path)
        old = anchor.load_json(path, "固定anchor subject")
        current_raw = reader.read_bytes(path)
        current = reader.load_json(path, "現append subject")
        if (hashlib.sha256(old_raw).hexdigest() != entry["anchorRawSha256"]
                or compute_subject_digest(old, limit) != entry["anchorDigest"]
                or hashlib.sha256(current_raw).hexdigest() != entry["currentRawSha256"]
                or compute_subject_digest(current, limit) != entry["currentDigest"]
                or entry["projection"] != projections[path]
                or any(compute_subject_digest(_carry_projection(value, projections[path]), limit)
                       != entry["projectionDigest"] for value in (old, current))):
            raise HumanReviewSignatureRecordError("T1 appendのraw/JCS/旧署名射影が不一致")
        expected = {"/inputAxesDescriptor/digest"}
        if path == str(STATE_TRANSITION_CONTRACT_PATH):
            expected |= {"/matrixRows", "/cases", "/mustOperationCoverage/mappings/0/rowRefs"}
        changes = {change["pointer"]: change for change in entry["allowedChanges"]}
        if set(changes) != expected or len(changes) != len(entry["allowedChanges"]):
            raise HumanReviewSignatureRecordError("T1 appendの許可位置がexact-set不一致")
        if path == str(STATE_TRANSITION_CONTRACT_PATH):
            _validate_t1_append_correspondence(changes)
        rebuilt = copy.deepcopy(old)
        for pointer, change in changes.items():
            keys = {"kind", "pointer", "before", "after"} if pointer == (
                "/inputAxesDescriptor/digest"
            ) else {"kind", "pointer", "beforeCount", "values"}
            _exact_keys(change, keys, "T1 allowed change")
            if pointer == "/inputAxesDescriptor/digest":
                if (change["kind"] != "replace"
                        or change["before"] != old["inputAxesDescriptor"]["digest"]
                        or change["after"] != descriptor_digest):
                    raise HumanReviewSignatureRecordError("descriptor差分が実値と不一致")
                rebuilt["inputAxesDescriptor"]["digest"] = change["after"]
            else:
                array = _carry_array(rebuilt, pointer)
                before_count = 111 if pointer == "/cases" else 44
                if (change["kind"] != "append" or type(change["beforeCount"]) is not int
                        or len(array) != before_count or change["beforeCount"] != before_count):
                    raise HumanReviewSignatureRecordError("T1 appendの旧prefix件数が不一致")
                array.extend(change["values"])
        if compute_subject_digest(rebuilt, limit) != entry["currentDigest"]:
            raise HumanReviewSignatureRecordError("T1 appendに許可外差分がある")
    return record


def _validate_gate6_t1_input_append(
    root: Path, baseline: _Gate6Baseline | None = None,
) -> dict[str, Any]:
    """不正/欠落入力を新受理失敗へ閉じ、公開経路の成功へfallbackしない。"""
    try:
        return _validate_gate6_t1_input_append_body(root, baseline)
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError(str(error)) from error


def _validate_gate6_t1_append_head(root: Path, event: Any, authority: Mapping[str, Any]) -> None:
    """新記録/schemaと実行依存も最終eventのblobに束縛する。"""
    _validate_gate6_head_bytes(root, event, authority)
    for path in (
        str(GATE6_T1_APPEND_PATH), str(GATE6_T1_APPEND_SCHEMA_PATH),
        "scripts/core_guard.py", "scripts/representative_selection.py",
        "scripts/check_input_axes_descriptor.py", "scripts/state_transition_freeze.py",
        "contracts/state-transition/input_axes_descriptor_v1.json",
    ):
        if (root / path).read_bytes() != _carry_git_bytes(
            root, ["show", f"{event.head_sha}:{path}"]
        ):
            raise HumanReviewSignatureRecordError("T1 appendの検査入力と最終HEADが不一致")


def validate_delegated_gate6_t1_input_append(root: Path, event: Any) -> None:
    """PR185だけを現event/実diff/既非作者委任証拠で新受理する。"""
    if event is None:
        raise HumanReviewSignatureRecordError("最終PR eventが未提供")
    if (type(event.number) is not int or event.number != _GATE6_T1_APPEND_PR
            or event.repository != "masaki1025/pitchlog"
            or event.head_repository != "masaki1025/pitchlog"
            or event.head_branch != _GATE6_T1_APPEND_BRANCH):
        raise HumanReviewSignatureRecordError("T1 appendの新受理はPR185の固定対象だけに限定する")
    _validate_gate6_checkout(root, event)
    pre_record = _object(descriptor_checker.load_json(root / GATE6_T1_APPEND_PATH,
                                                     "T1 append"), "T1 append")
    baseline = _gate6_baseline(root, pre_record, actual_base=event.base_sha)
    record = _validate_gate6_t1_input_append(root, baseline)
    authority = record["authority"]
    _validate_gate6_t1_append_head(root, event, authority)
    guard = _carry_core_guard(root)
    try:
        guard.verify_delegated_confirmation(root, event)
    except guard.GuardError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error


def validate_other_pr_gate6_t1_append_unchanged(root: Path, event: Any) -> None:
    """後続PRの不変継承を新PR185の受理と別に検査する。"""
    if event is None:
        raise HumanReviewSignatureRecordError("最終PR eventが未提供")
    if (type(event.number) is not int or event.number <= 0
            or event.number in {_GATE6_INTRODUCTION_PR, _GATE6_T1_APPEND_PR}
            or event.repository != "masaki1025/pitchlog"
            or event.head_repository != "masaki1025/pitchlog"
            or not isinstance(event.head_branch, str)
            or not event.head_branch.startswith(("feature/", "fix/"))
            or any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{40}", v) is None
                   for v in (event.base_sha, event.head_sha))):
        raise HumanReviewSignatureRecordError("後続T1 appendの継承eventが不正")
    _validate_gate6_checkout(root, event)
    for path in (str(GATE6_T1_APPEND_PATH), str(GATE6_T1_APPEND_SCHEMA_PATH),
                 str(STATE_TRANSITION_CONTRACT_PATH), str(GAME_END_CONTRACT_PATH)):
        if (root / path).read_bytes() != _carry_git_bytes(
            root, ["show", f"{event.base_sha}:{path}"]
        ):
            raise HumanReviewSignatureRecordError("後続PRでT1 append/schema/subjectを変更している")
    base_record = _gate6_git_object(root, event.base_sha, GATE6_T1_APPEND_PATH)
    baseline = _gate6_baseline(root, base_record)
    record = _validate_gate6_t1_input_append(root, baseline)
    _validate_gate6_t1_append_head(root, event, record["authority"])


_ORDINARY_PR = 187
_ORDINARY_BRANCH = "feature/mvp-t1-ordinary-pitches"
GATE6_ORDINARY_PATH = PurePosixPath(
    "contracts/state-transition/gate6_t1_ordinary_pitch_v1.json"
)
GATE6_ORDINARY_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/gate6_t1_ordinary_pitch_schema_v1.json"
)
ORDINARY_PINS_PATH = PurePosixPath(
    "contracts/state-transition/gate6_t1_ordinary_pitch_pins_v1.json"
)
_ORDINARY_BASELINE_LEDGER_PATH = PurePosixPath("contracts/authz/frozen-baselines.json")


def _ordinary_authority_revision(root: Path) -> str:
    """pins/policyに共通する承認済みoracle_inputの単一commitを返す。"""
    try:
        from frozen_baselines import FrozenBaselineError, load_latest_series_identity
    except ModuleNotFoundError:  # pragma: no cover - packageとして読む経路
        from scripts.frozen_baselines import (
            FrozenBaselineError,
            load_latest_series_identity,
        )
    try:
        identities = load_latest_series_identity(
            root / _ORDINARY_BASELINE_LEDGER_PATH, "oracle_input"
        )
        if (len(identities) != 1 or identities[0].kind != "literal_commit_string"
                or re.fullmatch(r"[0-9a-f]{40}", identities[0].value) is None):
            raise HumanReviewSignatureRecordError("通常33 authorityの台帳commitが単一40桁でない")
        return identities[0].value
    except HumanReviewSignatureRecordError:
        raise
    except (FrozenBaselineError, OSError, UnicodeError, ValueError) as error:
        raise HumanReviewSignatureRecordError("通常33 authorityの台帳を読めない") from error


def _ordinary_pins(root: Path) -> dict[str, str]:
    """承認台帳の単一commitにある独立JSONだけから通常33の固定値を読む。"""
    try:
        revision = _ordinary_authority_revision(root)
        raw = _carry_git_bytes(root, ["show", f"{revision}:{ORDINARY_PINS_PATH}"])
        head = _carry_git_bytes(root, ["rev-parse", "HEAD"]).decode("ascii").strip()
        if re.fullmatch(r"[0-9a-f]{40}", head) is None:
            raise HumanReviewSignatureRecordError("通常33 authorityのcheckout識別値が不正")
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", revision, head])
        if (root / ORDINARY_PINS_PATH).read_bytes() != raw:
            raise HumanReviewSignatureRecordError("通常33 authorityの現JSONが固定blobと不一致")
        value = _object(json.loads(raw,
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), "通常33 authority")
        _exact_keys(value, {"anchor", "public_base", "record_sha256", "schema_sha256"},
                    "通常33 authority")
        for key, width in (("anchor", 40), ("public_base", 40),
                           ("record_sha256", 64), ("schema_sha256", 64)):
            if (not isinstance(value[key], str)
                    or re.fullmatch(r"[0-9a-f]{" + str(width) + "}", value[key]) is None):
                raise HumanReviewSignatureRecordError("通常33 authorityの固定値型/桁が不正")
        return value
    except HumanReviewSignatureRecordError:
        raise
    except (OSError, UnicodeError, ValueError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("通常33 authorityの固定原本を読めない") from error

_ORDINARY_FIXED_INPUTS = frozenset({
    str(GATE6_T1_APPEND_PATH), str(GATE6_T1_APPEND_SCHEMA_PATH),
    str(GATE6_CARRY_PATH), str(GATE6_CARRY_SCHEMA_PATH),
    str(GAME_END_CONTRACT_PATH), *_GATE6_RETAINED_PATHS,
    "contracts/state-transition/input_axes_descriptor_v1.json",
    "docs/features/appendix-e-golden-vectors/matrix_rows_line_review.md",
})
_ORDINARY_EXECUTION_INPUTS = frozenset({
    "scripts/core_guard.py", "scripts/check_required_set_coverage.py",
    "scripts/check_branch_row_mapping.py", "scripts/representative_selection.py",
    "scripts/check_input_axes_descriptor.py", "scripts/state_transition_freeze.py",
    "scripts/check_deriver_dependencies.py", "scripts/expand_game_end_cases.py",
    "scripts/expand_state_transition_cases.py", "scripts/check_expander_dependencies.py",
    "scripts/state_transition_normalization.py",
    str(ORDINARY_PINS_PATH), str(_ORDINARY_BASELINE_LEDGER_PATH),
    "scripts/frozen_baselines.py",
})


class _OrdinaryAcceptedReader(_Gate6CurrentReader):
    """受理済み30f67原本だけを読む。任意revision引数を持たない。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.head = _ordinary_pins(root)["anchor"]

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """固定Git blobを読む。旧コードは実行しない。"""
        return _carry_git_bytes(self.root, ["show", f"{self.head}:{path}"])

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """重複keyを拒否する既strict decoderで原本を読む。"""
        return _object(json.loads(self.read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)


def _ordinary_present(root: Path) -> bool:
    """片方だけの存在も新手続きへ送り、欠損をfallbackさせない。"""
    return any((root / path).exists() for path in (
        GATE6_ORDINARY_PATH, GATE6_ORDINARY_SCHEMA_PATH,
    ))


def _ordinary_base_presence(root: Path, revision: str) -> tuple[bool, bool]:
    """actual baseのrecord/schema存在を別々に返し、片側欠損を隠さない。"""
    listing = _carry_git_bytes(root, [
        "show", f"{revision}:contracts/state-transition",
    ]).decode("utf-8").splitlines()
    return (GATE6_ORDINARY_PATH.name in listing, GATE6_ORDINARY_SCHEMA_PATH.name in listing)


def _ordinary_base_present(root: Path, revision: str) -> bool:
    """currentより先にbaseを読み、片側だけでもordinary検査へ送る。"""
    return any(_ordinary_base_presence(root, revision))


def _ordinary_record(root: Path) -> dict[str, Any]:
    """PR187の実受理全値と閉schemaを固定hashで照合する。"""
    pins = _ordinary_pins(root)
    for path, digest in (
        (GATE6_ORDINARY_PATH, pins["record_sha256"]),
        (GATE6_ORDINARY_SCHEMA_PATH, pins["schema_sha256"]),
    ):
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            raise HumanReviewSignatureRecordError("通常33 record/schemaの固定全値が不一致")
    reader = _Gate6CurrentReader(root)
    record = reader.load_json(GATE6_ORDINARY_PATH, "通常33 record")
    schema = reader.load_json(GATE6_ORDINARY_SCHEMA_PATH, "通常33 schema")
    descriptor_checker._validate_instance(record, schema, schema, "通常33 record")
    return record


_ORDINARY_INTEGRATION_PR = 189
_ORDINARY_INTEGRATION_BRANCH = "feature/mvp-first-ball-vertical"


def _ordinary_policy_matches(policy: Mapping[str, Any], reference: Mapping[str, Any],
                             *, allow_append: bool) -> bool:
    """全非target fieldと順序付きprefixを保持した有限末尾追記だけを許す。"""
    return (
        {k: v for k, v in policy.items() if k != "targets"}
        == {k: v for k, v in reference.items() if k != "targets"}
        and policy["targets"][:len(reference["targets"])] == reference["targets"]
        and (allow_append or len(policy["targets"]) == len(reference["targets"]))
    )


def _ordinary_policy_origins(root: Path, guard: Any, anchor: _OrdinaryAcceptedReader,
                             pins: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """旧14と承認Gitの正式18を独立原典として閉じ、currentから期待を作らない。"""
    legacy = anchor.load_json(guard.DELEGATION_POLICY_PATH, "通常33旧policy")
    legacy["targets"].append({
        "pr": 184, "branch": "feature/mvp-rg1-profile-integration-candidate"})
    try:
        public, _ = guard._load_delegation_policy(root, pins["public_base"])
        if public != legacy:
            raise HumanReviewSignatureRecordError("通常33の実公開base policyが不一致")
        current_authority = _ordinary_authority_revision(root)
        fixed, _ = guard._load_delegation_policy(root, current_authority)
        if len(fixed["targets"]) == 19:
            # 後発197 oracle台帳は196末尾を含む。旧18の出典は実台帳の直前identity。
            ledger = _object(json.loads(
                (root / _ORDINARY_BASELINE_LEDGER_PATH).read_bytes(),
                object_pairs_hook=descriptor_checker._reject_duplicate_keys,
            ), "通常33 oracle台帳")
            history = ledger.get("history")
            if type(history) is not list or not history:
                raise HumanReviewSignatureRecordError("通常33 oracle履歴が不正")
            tail = _object(history[-1], "通常33 oracle末尾")
            _exact_keys(tail, {
                "acceptance_id", "changes", "moved", "new_identity",
                "placement_change", "prior_identity", "reason", "series",
                "approved_by", "approved_at",
            }, "通常33 oracle末尾")
            prior = _object(tail["prior_identity"], "通常33 oracle直前")
            after = _object(tail["new_identity"], "通常33 oracle現行")
            placement = _object(tail["placement_change"], "通常33 oracle配置")
            _exact_keys(prior, {"present", "values"}, "通常33 oracle直前")
            _exact_keys(after, {"present", "values"}, "通常33 oracle現行")
            _exact_keys(placement, {"before", "after"}, "通常33 oracle配置")
            prior_values = prior["values"]
            after_values = after["values"]
            series_location = [{
                "kind": "ledger_series",
                "path": str(_ORDINARY_BASELINE_LEDGER_PATH),
                "series": "oracle_input",
            }]
            if (tail["acceptance_id"] != "masaki1025/pitchlog#197"
                    or tail["series"] != "oracle_input"
                    or tail["moved"] is not False
                    or placement["before"] != series_location
                    or placement["after"] != series_location
                    or prior["present"] is not True or after["present"] is not True
                    or type(prior_values) is not list or len(prior_values) != 1
                    or type(after_values) is not list or len(after_values) != 1
                    or after_values[0] != {
                        "kind": "literal_commit_string", "value": current_authority,
                    }):
                raise HumanReviewSignatureRecordError("通常33 oracle後継の閉履歴が不一致")
            previous = _object(prior_values[0], "通常33 oracle旧identity")
            previous_rev = previous.get("value")
            if (previous.get("kind") != "literal_commit_string"
                    or type(previous_rev) is not str
                    or re.fullmatch(r"[0-9a-f]{40}", previous_rev) is None):
                raise HumanReviewSignatureRecordError("通常33 oracle旧identityの型が不一致")
            prior_ledger = _object(json.loads(
                _carry_git_bytes(root, [
                    "show", f"{previous_rev}:{_ORDINARY_BASELINE_LEDGER_PATH}",
                ]), object_pairs_hook=descriptor_checker._reject_duplicate_keys,
            ), "通常33 oracle旧台帳")
            old_bindings = _object(
                prior_ledger.get("implementation_bindings"), "通常33 oracle旧実装束縛",
            )
            new_bindings = copy.deepcopy(old_bindings)
            code_assets = new_bindings.get("code_assets")
            if (type(code_assets) is not list or len(code_assets) != 2
                    or code_assets[0].get("path") != "scripts/check_frozen_baselines.py"
                    or code_assets[1].get("path") != "scripts/frozen_baselines.py"):
                raise HumanReviewSignatureRecordError("通常33 oracle旧実装束縛が不一致")
            code_assets[0]["sha256"] = hashlib.sha256(
                Path(__file__).resolve().with_name("check_frozen_baselines.py").read_bytes()
            ).hexdigest()
            changes = tail["changes"]
            expected_change = [{
                "aspect": "implementation_bindings",
                "before": old_bindings,
                "after": new_bindings,
            }]
            if (changes not in ([], expected_change)
                    or ledger.get("implementation_bindings") != (
                        old_bindings if changes == [] else new_bindings
                    )):
                raise HumanReviewSignatureRecordError("通常33 oracle実装束縛の閉履歴が不一致")
            prior_policy, _ = guard._load_delegation_policy(root, previous_rev)
            if (not _ordinary_policy_matches(fixed, prior_policy, allow_append=True)
                    or fixed["targets"] != prior_policy["targets"] + [{
                        "pr": 196, "branch": "feature/mvp-batted-hits",
                    }]):
                raise HumanReviewSignatureRecordError("通常33 oracle19の196単一末尾が不一致")
            fixed = prior_policy
    except guard.GuardError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    suffix = [
        {"pr": 188, "branch": "feature/mvp-game-start-atomic-candidate"},
        {"pr": 189, "branch": _ORDINARY_INTEGRATION_BRANCH},
        {"pr": 190, "branch": "feature/mvp-recording-continuation"},
        {"pr": 191, "branch": "feature/mvp-terminal-pitches"},
        {"pr": 192, "branch": "feature/mvp-strikeout-pitches"},
        {"pr": 193, "branch": "feature/ci-shard-pytest"},
    ]
    if (len(public["targets"]) != 12 or len(fixed["targets"]) != 18
            or not _ordinary_policy_matches(fixed, public, allow_append=True)
            or fixed["targets"][len(public["targets"]):] != suffix):
        raise HumanReviewSignatureRecordError("通常33 integrationの承認policy18/旧12prefixが不一致")
    legacy["targets"].extend([
        {"pr": 186, "branch": "feature/mvp-t1-first-pitch"},
        {"pr": _ORDINARY_PR, "branch": _ORDINARY_BRANCH},
    ])
    return {"legacy14": legacy, "integration18": fixed}


def _ordinary_policy_mode(policy: Mapping[str, Any], origins: Mapping[str, Any],
                          *, allow_append: bool) -> str:
    """旧14/正式18のどちらか一意に一致する場合だけmodeを確定する。"""
    modes = [name for name, reference in origins.items()
             if _ordinary_policy_matches(policy, reference, allow_append=allow_append)]
    if len(modes) != 1:
        raise HumanReviewSignatureRecordError("通常33 policyの旧prefix/実PR末尾が不一致")
    return modes[0]


def _ordinary_body(root: Path, *, allow_policy_append: bool = False,
                   policy_mode: str | None = None,
                   _terminal_legacy: bool = False) -> dict[str, Any]:
    """旧185の同bodyと有限33の全資産を検査する。公開受理はしない。"""
    try:
        reader = (_TerminalLegacyReader(root) if _terminal_legacy
                  else _Gate6CurrentReader(root))
        pins = _ordinary_pins(root)
        record = _ordinary_record(root)
        anchor = _OrdinaryAcceptedReader(root)
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", pins["anchor"],
                               reader.head])
        _validate_gate6_t1_input_append_body(root, reader=anchor)
        for path in _ORDINARY_FIXED_INPUTS:
            if reader.read_bytes(path) != anchor.read_bytes(path):
                raise HumanReviewSignatureRecordError("通常33の旧固定入力が変更された")
        guard = _carry_core_guard(root)
        try:
            policy, _ = guard._load_delegation_policy(root, reader.head)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        origins = _ordinary_policy_origins(root, guard, anchor, pins)
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", pins["public_base"],
                               reader.head])
        if policy_mode is None:
            # localはexact14/exact18だけで、合法suffixも公開継承と混同しない。
            _ordinary_policy_mode(policy, origins, allow_append=False)
        elif (policy_mode not in origins or not _ordinary_policy_matches(
                policy, origins[policy_mode], allow_append=allow_policy_append)):
            raise HumanReviewSignatureRecordError("通常33 policyの指定mode/prefixが不一致")
        for path, digest in record["assets"].items():
            if hashlib.sha256(reader.read_bytes(path)).hexdigest() != digest:
                raise HumanReviewSignatureRecordError("通常33の9資産全値が不一致")
        # 既consumerで12ID/104旧object/expected/historyの不変を再検査する。
        previous_path = sys.path[:]
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            coverage = importlib.import_module("check_required_set_coverage")
        finally:
            sys.path[:] = previous_path
        current = reader.load_json(STATE_TRANSITION_CONTRACT_PATH,
                                                     "通常33現subject")
        mapping = coverage._ordinary_case_id_migrations(root, current)
        old = anchor.load_json(STATE_TRANSITION_CONTRACT_PATH, "通常33旧subject")
        rebuilt = copy.deepcopy(old)
        new_cases = {case["caseId"]: case for case in current["cases"]}
        old_refs = {}
        for case in old["cases"]:
            if case["caseId"] in mapping:
                old_refs[_compact_json(case["rowRef"])] = (
                    new_cases[mapping[case["caseId"]]]["rowRef"])
        for row in rebuilt["matrixRows"]:
            ref = {"layer": "matrixRows", "coordinate": {
                key: row[key] for key in ("eventKind", "resultId", "precondition")}}
            if _compact_json(ref) in old_refs:
                row["precondition"] = old_refs[_compact_json(ref)]["coordinate"]["precondition"]
        rebuilt["cases"] = [new_cases[mapping.get(case["caseId"], case["caseId"])]
                            for case in old["cases"]]
        # guard拡張で新たに通る値のcoverage caseは、代表行のcoverage直後へ
        # 有限追加としてだけ許す。
        derived = [
            "ST-COVERAGE-05a89716e39b67b0",
            "ST-COVERAGE-8d5c59594f90b5bd",
            "ST-COVERAGE-1ea6f651c912d341",
        ]
        insertion = next(
            (
                index for index, case in enumerate(rebuilt["cases"])
                if case["caseId"] == "ST-COVERAGE-8c8d497a5880b267"
            ),
            None,
        )
        if insertion is None:
            raise HumanReviewSignatureRecordError(
                "通常33のcoverage代表caseが再構成にない"
            )
        for offset, case_id in enumerate(derived):
            rebuilt["cases"].insert(insertion + offset, new_cases[case_id])

        def migrate_refs(value: Any) -> Any:
            if isinstance(value, dict):
                if _compact_json(value) in old_refs:
                    return copy.deepcopy(old_refs[_compact_json(value)])
                return {key: migrate_refs(item) for key, item in value.items()}
            if isinstance(value, list):
                return [migrate_refs(item) for item in value]
            return value

        rebuilt["mustOperationCoverage"] = migrate_refs(rebuilt["mustOperationCoverage"])
        if compute_subject_digest(rebuilt, 9007199254740991) != compute_subject_digest(
            current, 9007199254740991,
        ):
            raise HumanReviewSignatureRecordError("通常33の4guard/12ID/1case以外の差分")
        return record
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("通常33の固定入力/閉全値検査に失敗") from error


def _ordinary_head(root: Path, event: Any, record: Mapping[str, Any]) -> None:
    """全検査入力と実行依存を最終eventのblobへ束縛する。"""
    _validate_gate6_head_bytes(root, event, {
        "path": "docs/features/mvp-delegated-core-review/policy.json"})
    for path in {str(GATE6_ORDINARY_PATH), str(GATE6_ORDINARY_SCHEMA_PATH),
                 *record["assets"], *_ORDINARY_FIXED_INPUTS, *_ORDINARY_EXECUTION_INPUTS}:
        if (root / path).read_bytes() != _carry_git_bytes(
            root, ["show", f"{event.head_sha}:{path}"],
        ):
            raise HumanReviewSignatureRecordError("通常33の検査入力/依存が最終HEADと不一致")


def _ordinary_base_materials(root: Path, event: Any) -> dict[str, bytes]:
    """既受理record/schema/9数学/旧11入力をheadより先に固定照合する。"""
    pins = _ordinary_pins(root)
    if _ordinary_base_presence(root, event.base_sha) != (True, True):
        raise HumanReviewSignatureRecordError("通常33のbase記録/schemaが片側欠損")
    materials: dict[str, bytes] = {}
    for path, digest in (
        (GATE6_ORDINARY_PATH, pins["record_sha256"]),
        (GATE6_ORDINARY_SCHEMA_PATH, pins["schema_sha256"]),
    ):
        raw = _carry_git_bytes(root, ["show", f"{event.base_sha}:{path}"])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise HumanReviewSignatureRecordError("通常33のbase記録/schemaが固定値と不一致")
        materials[str(path)] = raw
    baseline_record = _gate6_git_object(root, event.base_sha, GATE6_ORDINARY_PATH)
    anchor = _OrdinaryAcceptedReader(root)
    for path, digest in baseline_record["assets"].items():
        raw = _carry_git_bytes(root, ["show", f"{event.base_sha}:{path}"])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise HumanReviewSignatureRecordError("通常33のbase数学9資産が固定値と不一致")
        materials[path] = raw
    for path in _ORDINARY_FIXED_INPUTS:
        raw = _carry_git_bytes(root, ["show", f"{event.base_sha}:{path}"])
        if raw != anchor.read_bytes(path):
            raise HumanReviewSignatureRecordError("通常33のbase旧原本が固定値と不一致")
        materials[path] = raw
    return materials


_TERMINAL_REFERENCE_PATH = PurePosixPath(
    "tests/fixtures/pr191_ordinary_extension_reference_v1.json"
)
_TERMINAL_EXTENSION_FILES = frozenset(
    "contracts/state-transition/" + name for name in (
        "input_axes_descriptor_v1.json", "game_end_contract_v1.json",
        "state_transition_contract_v1.json", "branch_row_mapping_v1.json",
        "game_end_coverage_declaration_v1.json", "appendix_e_consumer_handoff_v1.json",
    )
)
_TERMINAL_EXTENSION_PURPOSE = (
    "PR191 ordinary33の歴史scopeとterminal有限extensionの全前後を審査済み固定Gitへ束縛する。"
    "旧署名subject・現木自己期待・任意PRの受理に流用しない。"
)
_TERMINAL_EXTENSION_INPUTS = frozenset({
    str(_TERMINAL_REFERENCE_PATH), "contracts/tenant_boundary/frozen-inputs.json",
    "contracts/state-transition/terminal_pitch_cases_v1.json",
    str(descriptor_checker.SCHEMA_PATH),
    "scripts/check_branch_row_mapping.py", "scripts/check_gap_register.py",
})


def _terminal_extension_reference(root: Path) -> dict[str, Any]:
    """用途と旧登録を照合し、独立JSONの全SHAを固定Gitで検証する。"""
    try:
        reference = _Gate6CurrentReader(root).load_json(_TERMINAL_REFERENCE_PATH, "terminal原典")
        _exact_keys(reference, {"schema_version", "base_revision", "candidate_revision", "files"},
                    "terminal原典")
        if type(reference["schema_version"]) is not int or reference["schema_version"] != 1:
            raise HumanReviewSignatureRecordError("terminal原典の版が不正")
        inputs = _Gate6CurrentReader(root).load_json(
            "contracts/tenant_boundary/frozen-inputs.json", "terminal固定入力",
        )["frozen_inputs"]
        entry = _object(inputs["terminal_ordinary_extension_revision"], "terminal用途")
        _exact_keys(entry, {"value", "purpose", "sources"}, "terminal用途")
        if (entry["purpose"] != _TERMINAL_EXTENSION_PURPOSE or entry["sources"] != [
            "scripts/check_human_review_signature.py:_terminal_extension_reference",
            "tests/test_human_review_signature.py:terminal_extension_fixture",
        ] or entry["value"] != inputs["terminal_core_reference_head_revision"]["value"]
                or reference["candidate_revision"] != entry["value"]
                or reference["base_revision"]
                != inputs["terminal_core_reference_base_revision"]["value"]):
            raise HumanReviewSignatureRecordError("terminal原典の用途/独立登録が不一致")
        for key in ("base_revision", "candidate_revision"):
            revision = reference[key]
            if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
                raise HumanReviewSignatureRecordError("terminal原典は直接のfull commitが必要")
            resolved = _carry_git_bytes(root, ["rev-parse", "--verify", revision + "^{commit}"])
            if resolved.decode().strip() != revision:
                raise HumanReviewSignatureRecordError("terminal原典のcommitが不一致")
        _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                               reference["base_revision"], reference["candidate_revision"]])
        _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                               reference["candidate_revision"], "HEAD"])
        files = _object(reference["files"], "terminal全前後")
        _exact_keys(files, set(_TERMINAL_EXTENSION_FILES), "terminal全前後")
        for path, hashes in files.items():
            _exact_keys(_object(hashes, "terminal SHA"), {"before_sha256", "after_sha256"},
                        "terminal SHA")
            for key, revision in (("before_sha256", reference["base_revision"]),
                                  ("after_sha256", reference["candidate_revision"])):
                digest = hashes[key]
                if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                        or hashlib.sha256(_carry_git_bytes(
                            root, ["show", revision + ":" + path],
                        )).hexdigest() != digest):
                    raise HumanReviewSignatureRecordError("terminal全前後SHAが固定Gitと不一致")
        return reference
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("terminal独立原典を閉じて読めない") from error


class _TerminalLegacyReader(_Gate6CurrentReader):
    """既受理119を固定Bからだけ読み、旧33全検査を再利用する。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.head = _terminal_extension_reference(root)["base_revision"]

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """現木ではなく固定した旧受理blobを返す。"""
        return _carry_git_bytes(self.root, ["show", f"{self.head}:{path}"])

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """固定原本を既strict decoderで読む。"""
        return _object(json.loads(self.read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)


def _ordinary_terminal_body(root: Path, *,
                            _reader: _Gate6CurrentReader | None = None) -> dict[str, Any]:
    """旧33全値と新2行15例・6pathだけを分離し、公開受理はしない。"""
    try:
        reference = _terminal_extension_reference(root)
        old_reader = _TerminalLegacyReader(root)
        record = _ordinary_body(root, policy_mode="integration18", _terminal_legacy=True)
        current = _Gate6CurrentReader(root) if _reader is None else _reader
        for path in {*record["assets"], *_ORDINARY_FIXED_INPUTS}:
            raw = current.read_bytes(path)
            expected = (reference["files"][path]["after_sha256"]
                        if path in _TERMINAL_EXTENSION_FILES
                        else hashlib.sha256(old_reader.read_bytes(path)).hexdigest())
            if hashlib.sha256(raw).hexdigest() != expected:
                raise HumanReviewSignatureRecordError("terminal headが固定全値と不一致")
        prefix = "contracts/state-transition/"
        before = {Path(path).name: old_reader.load_json(path, "旧terminal比較元")
                  for path in _TERMINAL_EXTENSION_FILES}
        after = {name: current.load_json(prefix + name, "現terminal") for name in before}
        descriptor = after["input_axes_descriptor_v1.json"]
        prior_descriptor = before["input_axes_descriptor_v1.json"]
        schema = current.load_json(descriptor_checker.SCHEMA_PATH, "descriptor schema")
        descriptor_checker._validate_instance(descriptor, schema, schema, "terminal descriptor")
        freeze = descriptor_checker.freeze_checker
        try:
            freeze.validate_append_only_transition(
                descriptor["freezeBaseline"], prior_descriptor["freezeBaseline"],
            )
        except freeze.FreezeBaselineError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        history = descriptor["freezeBaseline"]["history"]
        if (len(history) != len(prior_descriptor["freezeBaseline"]["history"]) + 1
                or history[-1]["acceptanceId"] != "masaki1025/pitchlog#191"
                or descriptor["digest"]
                != descriptor_checker.compute_descriptor_digest(descriptor)):
            raise HumanReviewSignatureRecordError("terminal descriptorの有限受理が不一致")
        projected = copy.deepcopy(after)
        desc = projected["input_axes_descriptor_v1.json"]
        axes = desc["freezeBaseline"]["criteria"]["gapRegister"]["rowLayers"][0][
            "qualifyWhenPredicateAxes"]
        if axes[-1] != "state.gameEnded":
            raise HumanReviewSignatureRecordError("terminal資格軸が不一致")
        axes.pop()
        desc["freezeBaseline"]["history"].pop()
        desc["digest"] = prior_descriptor["digest"]
        for name in ("game_end_contract_v1.json", "state_transition_contract_v1.json"):
            projected[name]["inputAxesDescriptor"]["digest"] = prior_descriptor["digest"]
        coverage = importlib.import_module("check_required_set_coverage")
        contract = after["state_transition_contract_v1.json"]
        identifiers = coverage._terminal_case_extension(root, contract)
        if (len(identifiers) != 15
                or len(coverage._ordinary_case_id_migrations(root, contract)) != 12):
            raise HumanReviewSignatureRecordError("terminal追加集合/旧12移行が不一致")
        subject = projected["state_transition_contract_v1.json"]
        if (len(subject["cases"]) != 134 or len(subject["matrixRows"]) != 51
                or {case["caseId"] for case in subject["cases"][119:]} != identifiers):
            raise HumanReviewSignatureRecordError("terminal旧119以外の追加が不一致")
        subject["cases"] = subject["cases"][:119]
        subject["matrixRows"] = subject["matrixRows"][:49]
        refs = subject["mustOperationCoverage"]["mappings"][0]["rowRefs"]
        if len(refs) != 51:
            raise HumanReviewSignatureRecordError("terminal row参照が不一致")
        del refs[49:]
        mappings = projected["branch_row_mapping_v1.json"]["mappings"][11]
        if len(mappings["additionalCaseMappings"]) != 15:
            raise HumanReviewSignatureRecordError("terminal追加mappingが不一致")
        del mappings["additionalCaseMappings"]
        counts = projected["game_end_coverage_declaration_v1.json"]["normalCaseCounts"]
        if counts["stateTransition"] != 134:
            raise HumanReviewSignatureRecordError("terminal件数が不一致")
        counts["stateTransition"] = 119
        artifacts = projected["appendix_e_consumer_handoff_v1.json"]["artifacts"]
        for index, asset in enumerate(artifacts):
            if index < 3:
                raw = current.read_bytes(asset["path"])
                if asset["digest"] != "sha256:" + hashlib.sha256(raw).hexdigest():
                    raise HumanReviewSignatureRecordError("terminal handoff digestが不一致")
                asset["digest"] = before["appendix_e_consumer_handoff_v1.json"]["artifacts"][index][
                    "digest"]
        if projected != before:
            raise HumanReviewSignatureRecordError("terminal許可6path以外のJSON差分")
        return record
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("terminal旧scope/有限全値検査が不成立") from error


_STRIKEOUT_REFERENCE_PATH = PurePosixPath(
    "tests/fixtures/pr192_ordinary_extension_reference_v1.json"
)
_STRIKEOUT_REFERENCE_PURPOSE = (
    "PR192 ordinary33継承の独立全前後と有限4path拡張をroot前置Git全byteへ束縛する。"
    "旧署名subject・191scope・現木自己期待・任意PR受理へ流用しない。"
)
_STRIKEOUT_CHANGED_PATHS = tuple(
    "contracts/state-transition/" + name for name in (
        "state_transition_contract_v1.json", "branch_row_mapping_v1.json",
        "game_end_coverage_declaration_v1.json", "appendix_e_consumer_handoff_v1.json",
    )
)
_STRIKEOUT_AUXILIARY_INPUTS = frozenset(
    "contracts/state-transition/" + name for name in (
        "strikeout_pitch_cases_v1.json", "strikeout_pitch_schema_v1.json",
        "state_transition_contract_schema_v1.json",
    )
)
_STRIKEOUT_EXTENSION_INPUTS = frozenset({
    str(_STRIKEOUT_REFERENCE_PATH), *_TERMINAL_EXTENSION_INPUTS,
    *_STRIKEOUT_AUXILIARY_INPUTS, "scripts/check_required_set_coverage.py",
    "tests/test_human_review_signature.py",
    "tests/fixtures/pr192_tenant_source_expected_v1.json",
})


def _strikeout_extension_reference(root: Path) -> dict[str, Any]:
    """作者と別のroot前置Git原本を読み、正式合流前の二系統を区別する。"""
    try:
        current = _Gate6CurrentReader(root)
        frozen = current.load_json(
            "contracts/tenant_boundary/frozen-inputs.json", "三振固定入力",
        )["frozen_inputs"]
        entry = _object(frozen["pr192_ordinary_extension_reference_revision"], "三振用途")
        _exact_keys(entry, {"value", "purpose", "sources"}, "三振用途")
        if entry["purpose"] != _STRIKEOUT_REFERENCE_PURPOSE or entry["sources"] != [
            "scripts/check_human_review_signature.py:_strikeout_extension_reference",
            "tests/test_human_review_signature.py:strikeout_extension_fixture",
        ]:
            raise HumanReviewSignatureRecordError("三振原典の用途/consumerが不一致")
        revision = entry["value"]
        if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise HumanReviewSignatureRecordError("三振原典は直接のfull commitが必要")
        fixed = _carry_git_bytes(root, ["show", f"{revision}:{_STRIKEOUT_REFERENCE_PATH}"])
        if current.read_bytes(_STRIKEOUT_REFERENCE_PATH) != fixed:
            raise HumanReviewSignatureRecordError("三振原典がroot前置Git全byteと不一致")
        reference = _object(json.loads(fixed,
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), "三振原典")
        _exact_keys(reference, {"schema_version", "formal_base_revision",
                    "terminal_accepted_revision", "candidate_revision", "files",
                    "historical_ordinary_scope", "finite_extension"}, "三振原典")
        if type(reference["schema_version"]) is not int or reference["schema_version"] != 1:
            raise HumanReviewSignatureRecordError("三振原典の版が不正")
        for commit in (revision, reference["formal_base_revision"],
                       reference["terminal_accepted_revision"], reference["candidate_revision"]):
            if (not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None
                    or _carry_git_bytes(root, ["rev-parse", "--verify", commit + "^{commit}"]
                                       ).decode().strip() != commit):
                raise HumanReviewSignatureRecordError("三振原典の実commitが不一致")
        terminal = _terminal_extension_reference(root)
        if (reference["terminal_accepted_revision"] != terminal["candidate_revision"]
                or reference["candidate_revision"]
                != frozen["pr192_source_registration_revision"]["value"]):
            raise HumanReviewSignatureRecordError("三振原典の独立固定源が不一致")
        expectation_revision = frozen["pr192_source_expectation_revision"]["value"]
        if (not isinstance(expectation_revision, str)
                or re.fullmatch(r"[0-9a-f]{40}", expectation_revision) is None
                or _carry_git_bytes(root, ["rev-parse", "--verify",
                    expectation_revision + "^{commit}"]).decode().strip() != expectation_revision):
            raise HumanReviewSignatureRecordError("三振独立合流原典のcommitが不一致")
        expectation_path = "tests/fixtures/pr192_tenant_source_expected_v1.json"
        expected_raw = _carry_git_bytes(root, ["show",
            expectation_revision + ":" + expectation_path])
        if current.read_bytes(expectation_path) != expected_raw:
            raise HumanReviewSignatureRecordError("三振独立合流原典が固定Git全byteと不一致")
        expected = _object(json.loads(expected_raw,
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), "三振独立合流元")
        if (reference["formal_base_revision"] != expected["formal_base_revision"]
                or reference["candidate_revision"] != expected["source_revision"]):
            raise HumanReviewSignatureRecordError("三振正式base/候補が独立原典と不一致")
        # eb8は正式merge、9b76は並行候補。eb8→9b76という偽の祖先関係は要求しない。
        for prior, later in (
            (reference["terminal_accepted_revision"], reference["formal_base_revision"]),
            (reference["terminal_accepted_revision"], reference["candidate_revision"]),
            (reference["formal_base_revision"], revision),
            (reference["candidate_revision"], revision),
            (reference["candidate_revision"], expectation_revision),
            (expectation_revision, revision),
            (revision, current.head),
        ):
            _carry_git_bytes(root, ["merge-base", "--is-ancestor", prior, later])
        record = _gate6_git_object(root, terminal["base_revision"], GATE6_ORDINARY_PATH)
        files = _object(reference["files"], "三振11全前後")
        _exact_keys(files, {*record["assets"],
            "contracts/state-transition/input_axes_descriptor_v1.json",
            str(GAME_END_CONTRACT_PATH)}, "三振11全前後")
        for path, hashes in files.items():
            _exact_keys(_object(hashes, "三振SHA"), {"before_sha256", "after_sha256"},
                        "三振SHA")
            for key, commit in (("before_sha256", reference["formal_base_revision"]),
                                ("after_sha256", reference["candidate_revision"])):
                digest = hashes[key]
                raw = _carry_git_bytes(root, ["show", f"{commit}:{path}"])
                if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                        or hashlib.sha256(raw).hexdigest() != digest):
                    raise HumanReviewSignatureRecordError("三振全前後SHAが実Gitと不一致")
                if key == "before_sha256" and raw != _carry_git_bytes(root, ["show",
                    reference["terminal_accepted_revision"] + ":" + path,
                ]):
                    raise HumanReviewSignatureRecordError("正式191 baseと受理224の11全値が不一致")
        historical = _object(reference["historical_ordinary_scope"], "三振の旧署名scope")
        _exact_keys(historical, {"accepted_revision", "protected_file_sha256",
                                "signed_asset_sha256"}, "三振の旧署名scope")
        if (historical["accepted_revision"] != terminal["base_revision"]
                or historical["signed_asset_sha256"] != record["assets"]):
            raise HumanReviewSignatureRecordError("三振追加が旧署名の対象/9hashを変更")
        protected = historical["protected_file_sha256"]
        _exact_keys(_object(protected, "三振旧record/schema/pins"), {
            str(GATE6_ORDINARY_PATH), str(GATE6_ORDINARY_SCHEMA_PATH), str(ORDINARY_PINS_PATH),
        }, "三振旧record/schema/pins")
        for path, digest in protected.items():
            for commit in (historical["accepted_revision"], reference["formal_base_revision"],
                           reference["candidate_revision"]):
                if hashlib.sha256(_carry_git_bytes(root, ["show", f"{commit}:{path}"])
                                  ).hexdigest() != digest:
                    raise HumanReviewSignatureRecordError("三振基線の旧record/schema/pinsが不一致")
        return reference
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("三振の独立原典/合流検査が不成立") from error


class _StrikeoutTerminalReader(_Gate6CurrentReader):
    """PR192用に固定した正式191の原本だけを読み、任意revisionを受けない。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.head = _strikeout_extension_reference(root)["formal_base_revision"]

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """署名scopeと分離した正式191 Git全値を返す。"""
        return _carry_git_bytes(self.root, ["show", f"{self.head}:{path}"])

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """固定baseを重複key拒否で読む。"""
        return _object(json.loads(self.read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)


def _ordinary_strikeout_body(root: Path, *,
                             _reader: _Gate6CurrentReader | None = None) -> dict[str, Any]:
    """旧33/119/191を保持し、root前置7操作と規範24例だけを検査する。"""
    try:
        reference = _strikeout_extension_reference(root)
        current = _Gate6CurrentReader(root) if _reader is None else _reader
        reader = _StrikeoutTerminalReader(root)
        record = _ordinary_terminal_body(root, _reader=reader)
        for path, digest in reference["historical_ordinary_scope"]["protected_file_sha256"].items():
            if hashlib.sha256(current.read_bytes(path)).hexdigest() != digest:
                raise HumanReviewSignatureRecordError("三振headの旧record/schema/pinsが不一致")
        for path, hashes in reference["files"].items():
            if hashlib.sha256(current.read_bytes(path)).hexdigest() != hashes["after_sha256"]:
                raise HumanReviewSignatureRecordError("三振head11資産が固定192全値と不一致")
        for path in _STRIKEOUT_AUXILIARY_INPUTS:
            if current.read_bytes(path) != _carry_git_bytes(root, ["show",
                reference["candidate_revision"] + ":" + path,
            ]):
                raise HumanReviewSignatureRecordError("三振規範case/schemaが固定源と不一致")
        finite = _object(reference["finite_extension"], "三振有限差分")
        _exact_keys(finite, {"changed_paths", "added_case_ids", "additional_case_mapping_ids",
                           "added_matrix_row_coordinates", "projection_operations"},
                    "三振有限差分")
        if finite["changed_paths"] != list(_STRIKEOUT_CHANGED_PATHS):
            raise HumanReviewSignatureRecordError("三振の変更4pathが不一致")
        before = {p: reader.load_json(p, "三振旧191") for p in _STRIKEOUT_CHANGED_PATHS}
        after = {p: current.load_json(p, "三振現192") for p in _STRIKEOUT_CHANGED_PATHS}
        rebuilt = copy.deepcopy(before)
        operations = finite["projection_operations"]
        identities = [
            ("append", _STRIKEOUT_CHANGED_PATHS[0], "/cases"),
            ("append", _STRIKEOUT_CHANGED_PATHS[0], "/matrixRows"),
            ("append", _STRIKEOUT_CHANGED_PATHS[0], "/mustOperationCoverage/mappings/0/rowRefs"),
            ("append", _STRIKEOUT_CHANGED_PATHS[1], "/mappings/0/additionalCaseMappings"),
            ("append", _STRIKEOUT_CHANGED_PATHS[1], "/mappings/1/additionalCaseMappings"),
            ("replace", _STRIKEOUT_CHANGED_PATHS[2], "/normalCaseCounts/stateTransition"),
            ("replace", _STRIKEOUT_CHANGED_PATHS[3], "/artifacts/0/digest"),
        ]
        if type(operations) is not list or [
            (o["op"], o["path"], o["pointer"]) for o in operations
        ] != identities:
            raise HumanReviewSignatureRecordError("三振のprojectionは閉じた7操作だけに限定")
        for operation in operations:
            parent: Any = rebuilt[operation["path"]]
            segments = operation["pointer"].removeprefix("/").split("/")
            for segment in segments[:-1]:
                parent = parent[int(segment)] if type(parent) is list else parent[segment]
            key = segments[-1]
            if operation["op"] == "append":
                _exact_keys(operation, {"op", "path", "pointer", "property_previously_present",
                    "before_length", "after_length", "added_values"}, "三振append")
                if (type(parent) is not dict
                        or type(operation["property_previously_present"]) is not bool):
                    raise HumanReviewSignatureRecordError("三振appendの閉じた親型が不一致")
                if (key in parent) is not operation["property_previously_present"]:
                    raise HumanReviewSignatureRecordError("三振appendの既存propertyが不一致")
                if key not in parent:
                    parent[key] = []
                values = parent[key]
                if (type(values) is not list or type(operation["added_values"]) is not list
                        or type(operation["before_length"]) is not int
                        or type(operation["after_length"]) is not int
                        or len(values) != operation["before_length"]):
                    raise HumanReviewSignatureRecordError("三振appendの旧全値/長さが不一致")
                values.extend(copy.deepcopy(operation["added_values"]))
                if len(values) != operation["after_length"]:
                    raise HumanReviewSignatureRecordError("三振appendの新全値/長さが不一致")
            else:
                _exact_keys(operation, {"op", "path", "pointer", "before_value", "after_value"},
                            "三振replace")
                if _compact_json(parent[key]) != _compact_json(operation["before_value"]):
                    raise HumanReviewSignatureRecordError("三振replaceの前値が不一致")
                parent[key] = copy.deepcopy(operation["after_value"])
        if _compact_json(rebuilt) != _compact_json(after):
            raise HumanReviewSignatureRecordError("三振の許可7操作以外のJSON差分")
        coverage = importlib.import_module("check_required_set_coverage")
        contract = after[_STRIKEOUT_CHANGED_PATHS[0]]
        identifiers = coverage._strikeout_case_extension(root, contract)
        if (len(identifiers) != 24 or sorted(identifiers) != finite["added_case_ids"]
                or len(contract["cases"]) != 158 or len(contract["matrixRows"]) != 67
                or [case["caseId"] for case in contract["cases"][134:]]
                != finite["added_case_ids"]):
            raise HumanReviewSignatureRecordError("三振の新24例/旧134prefix/67行が不一致")
        coordinates = [{key: row[key] for key in ("eventKind", "resultId", "precondition")}
                       for row in contract["matrixRows"][51:]]
        if _compact_json(coordinates) != _compact_json(finite["added_matrix_row_coordinates"]):
            raise HumanReviewSignatureRecordError("三振の新16座標が不一致")
        mappings = after[_STRIKEOUT_CHANGED_PATHS[1]]["mappings"]
        for index, branch in enumerate(("SO-01", "SO-02")):
            row = mappings[index]
            if (row["branchId"] != branch or [c["caseId"] for c in row["additionalCaseMappings"]]
                    != finite["additional_case_mapping_ids"][branch]):
                raise HumanReviewSignatureRecordError("三振の規範branch/追加対応12が不一致")
        return record
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("三振の歴史scope/有限全値検査が不成立") from error


def _ordinary_strikeout_ci(root: Path, event: Any) -> str:
    """PR192の二系統合流と最終公開独立PO証拠を必須にする。"""
    try:
        if (type(event.number) is not int or event.number != 192
                or event.head_branch != "feature/mvp-strikeout-pitches"
                or event.repository != "masaki1025/pitchlog"
                or event.head_repository != event.repository):
            raise HumanReviewSignatureRecordError("三振追加は実PR192だけに限定する")
        _validate_gate6_checkout(root, event)
        reference = _strikeout_extension_reference(root)
        if event.base_sha != reference["formal_base_revision"]:
            raise HumanReviewSignatureRecordError("三振actual baseが固定正式191と不一致")
        # 実baseを先に読む。旧signed9hashを上書きせず191全値との同一性を検査する。
        for path, hashes in reference["files"].items():
            raw = _carry_git_bytes(root, ["show", f"{event.base_sha}:{path}"])
            if hashlib.sha256(raw).hexdigest() != hashes["before_sha256"]:
                raise HumanReviewSignatureRecordError("三振actual baseの11全値が不一致")
        for prior in (event.base_sha, reference["candidate_revision"]):
            _carry_git_bytes(root, ["merge-base", "--is-ancestor", prior, event.head_sha])
        guard = _carry_core_guard(root)
        try:
            base_policy, _ = guard._load_delegation_policy(root, event.base_sha)
            head_policy, _ = guard._load_delegation_policy(root, event.head_sha)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        origins = _ordinary_policy_origins(root, guard, _OrdinaryAcceptedReader(root),
                                           _ordinary_pins(root))
        if base_policy != origins["integration18"] or head_policy != base_policy:
            raise HumanReviewSignatureRecordError("三振policyの固定18全値が不一致")
        record = _ordinary_strikeout_body(root)
        _ordinary_head(root, event, record)
        for path in _STRIKEOUT_EXTENSION_INPUTS:
            if (root / path).read_bytes() != _carry_git_bytes(
                root, ["show", f"{event.head_sha}:{path}"],
            ):
                raise HumanReviewSignatureRecordError("三振の検査入力/依存が最終HEADと不一致")
        try:
            guard.verify_delegated_confirmation(root, event)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        return ("gate6 old ordinary33/PR191: HISTORICAL PRESERVED; PR192 strikeout extension: "
                "DELEGATED VERIFIED; not new PR187/191 acceptance; not a personal signature")
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("三振の公開委任/実HEAD検査が不成立") from error


class _BattedCarryBaseReader(_Gate6CurrentReader):
    """実PR196のbase blobだけを読む。旧コードや合成PR192 eventは実行しない。"""

    def __init__(self, root: Path, revision: str) -> None:
        if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise HumanReviewSignatureRecordError("安打carryの実baseが不正")
        self.root = root
        self.head = revision

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """実baseの原本をread-only Gitで読む。"""
        return _carry_git_bytes(self.root, ["show", f"{self.head}:{path}"])

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """現木へfallbackせず、重複keyも拒否する。"""
        return _object(json.loads(self.read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)


_BATTED_METADATA_DESCRIPTOR = "contracts/state-transition/input_axes_descriptor_v1.json"
_BATTED_METADATA_BINDINGS = {
    "contracts/state-transition/state_transition_contract_v1.json":
        ("inputAxesDescriptor", "digest"),
    "contracts/state-transition/game_end_contract_v1.json":
        ("inputAxesDescriptor", "digest"),
    "contracts/state-transition/state_transition_contract_schema_v1.json":
        ("$defs", "inputAxesDescriptorBinding", "properties", "digest", "const"),
    "contracts/state-transition/game_end_contract_schema_v1.json":
        ("$defs", "inputAxesDescriptorBinding", "properties", "digest", "const"),
}
_BATTED_METADATA_PATHS = frozenset({_BATTED_METADATA_DESCRIPTOR, *_BATTED_METADATA_BINDINGS})


def _batted_metadata_delta(root: Path, base: _BattedCarryBaseReader) -> bool:
    """descriptor監査2語/記録1と依存4参照だけを実原典から再構成する。"""
    previous_raw = base.read_bytes(_BATTED_METADATA_DESCRIPTOR)
    current_raw = (root / _BATTED_METADATA_DESCRIPTOR).read_bytes()
    # R4以前の経路は全5byte不変を必須にして旧挙動を維持する。
    if current_raw == previous_raw:
        if any((root / path).read_bytes() != base.read_bytes(path)
               for path in _BATTED_METADATA_BINDINGS):
            raise HumanReviewSignatureRecordError("descriptor不変で依存参照だけが変更された")
        return False
    previous = base.load_json(_BATTED_METADATA_DESCRIPTOR, "安打旧descriptor")
    current = _Gate6CurrentReader(root).load_json(_BATTED_METADATA_DESCRIPTOR, "安打descriptor")
    rebuilt = copy.deepcopy(previous)
    declaration = current["freezeBaseline"]
    prior = previous["freezeBaseline"]
    history = declaration["history"]
    if (type(history) is not list or len(history) != len(prior["history"]) + 1
            or _compact_json(history[:-1]) != _compact_json(prior["history"])):
        raise HumanReviewSignatureRecordError("安打metadataの旧履歴/単一196記録が不一致")
    navigation = rebuilt["freezeBaseline"]["scope"]["sourceLiteralAudit"][
        "permittedComparisonLiteralsBySource"]["scripts/check_input_axes_descriptor.py"][
            "json-object-member-name-used-only-for-navigation"]
    if (type(navigation) is not list or any(type(v) is not str for v in navigation)
            or "allOf" in navigation or "anyOf" in navigation):
        raise HumanReviewSignatureRecordError("安打metadataの監査旧原典が不一致")
    navigation.extend(["allOf", "anyOf"])
    navigation.sort()
    record = history[-1]
    if (record["acceptanceId"] != "masaki1025/pitchlog#196"
            or record["series"] != "state-transition-contract-checks"
            or type(record["changes"]) is not list or len(record["changes"]) != 1
            or record["changes"][0]["criterionId"] != prior["scope"]["identityCriterionId"]
            or _compact_json(record["changes"][0]["before"]) != _compact_json({
                "present": True, "value": prior["scope"]})
            or _compact_json(record["changes"][0]["after"]) != _compact_json({
                "present": True, "value": declaration["scope"]})
            or record["approvedBy"] != (
                "PO委任によるCodex主担当/root判断（本人署名・人間逐行確認の代記ではない）")
            or type(record["fact"]) is not str or "未承認" in record["fact"]):
        raise HumanReviewSignatureRecordError("安打metadataの196記録/委任主体が不一致")
    # before/after、全prior/new identity、日付形式と全closed recordは既engineで検査する。
    try:
        changed = descriptor_checker.freeze_checker.validate_append_only_transition(
            declaration, prior)
    except descriptor_checker.freeze_checker.FreezeBaselineError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    if changed != (prior["scope"]["identityCriterionId"],):
        raise HumanReviewSignatureRecordError("安打metadataの変更基準が不一致")
    rebuilt["freezeBaseline"]["history"].append(copy.deepcopy(record))
    rebuilt["digest"] = descriptor_checker.compute_descriptor_digest(rebuilt)
    # 全未知field/型/criteria/他scopeを含めて比較し、旧書式も再serialiseで変えない。
    expected_raw = (json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n").encode()
    if _compact_json(current) != _compact_json(rebuilt) or current_raw != expected_raw:
        raise HumanReviewSignatureRecordError("安打metadataは監査2語/記録1以外を変更")
    old_digest, new_digest = previous["digest"], rebuilt["digest"]
    for path, pointer in _BATTED_METADATA_BINDINGS.items():
        old_raw = base.read_bytes(path)
        value: Any = base.load_json(path, "安打旧descriptor参照")
        for key in pointer:
            value = value[key]
        old_literal = json.dumps(old_digest).encode()
        if value != old_digest or old_raw.count(old_literal) != 1:
            raise HumanReviewSignatureRecordError("安打metadataの旧参照がexact1でない")
        expected = old_raw.replace(old_literal, json.dumps(new_digest).encode(), 1)
        if (root / path).read_bytes() != expected:
            raise HumanReviewSignatureRecordError("安打metadataの依存4参照以外に差分")
    return True


_BATTED_HANDOFF_PATH = "contracts/state-transition/appendix_e_consumer_handoff_v1.json"
_BATTED_HANDOFF_SOURCES = (
    str(STATE_TRANSITION_CONTRACT_PATH), str(GAME_END_CONTRACT_PATH),
    _BATTED_METADATA_DESCRIPTOR,
)
_BATTED_PROJECTION_PATHS = _BATTED_METADATA_PATHS | {_BATTED_HANDOFF_PATH}


def _batted_current_legacy_documents(root: Path) -> None:
    """旧固定文書をactual headのbyteと既JSON読取値の双方で原典へ束縛する。"""
    current = _Gate6CurrentReader(root)
    anchor = _OrdinaryAcceptedReader(root)
    for path in sorted(_ORDINARY_FIXED_INPUTS - _BATTED_PROJECTION_PATHS):
        if current.read_bytes(path) != anchor.read_bytes(path):
            raise HumanReviewSignatureRecordError("安打current旧固定byteが原典と不一致: " + path)
        if PurePosixPath(path).suffix == ".json" and _compact_json(
            current.load_json(path, "安打current旧文書")
        ) != _compact_json(anchor.load_json(path, "安打旧文書原典")):
            raise HumanReviewSignatureRecordError("安打current旧JSON読取値が原典と不一致: " + path)


def _batted_handoff_delta(root: Path, base: _BattedCarryBaseReader) -> None:
    """base handoff全byteから実head3資産のdigestだけを導出し、その他の差を拒否する。"""
    previous = base.read_bytes(_BATTED_HANDOFF_PATH)
    handoff = base.load_json(_BATTED_HANDOFF_PATH, "安打base handoff")
    artifacts = handoff["artifacts"]
    if type(artifacts) is not list or len(artifacts) != len(_BATTED_HANDOFF_SOURCES):
        raise HumanReviewSignatureRecordError("安打handoffのbase資産集合が不一致")
    expected = previous
    for raw_entry, path in zip(artifacts, _BATTED_HANDOFF_SOURCES, strict=True):
        entry = _object(raw_entry, "安打base handoff資産")
        if (entry["path"] != path or entry["version"] != PurePosixPath(path).stem
                or entry["digest"] != "sha256:" + hashlib.sha256(
                    base.read_bytes(path)).hexdigest()):
            raise HumanReviewSignatureRecordError("安打handoffのbase path/version/digestが不一致")
        before = json.dumps(entry["digest"]).encode()
        if previous.count(before) != 1:
            raise HumanReviewSignatureRecordError("安打handoffの旧digest参照がexact1でない")
        after = json.dumps("sha256:" + hashlib.sha256((root / path).read_bytes()).hexdigest())
        expected = expected.replace(before, after.encode(), 1)
    if (root / _BATTED_HANDOFF_PATH).read_bytes() != expected:
        raise HumanReviewSignatureRecordError("安打handoffは実3digest以外を変更または更新漏れ")


class _BattedMetadataProjectionReader(_Gate6CurrentReader):
    """閉検証済みmetadata5とhandoffだけを原典へ戻し、他head値を既bodyへ渡す。"""

    def __init__(self, root: Path, base: _BattedCarryBaseReader) -> None:
        super().__init__(root)
        self.base = base

    def validate_current_views(self) -> None:
        """閉raw guardを通ったmetadata全6文書も既decoder境界で照合する。"""
        for path in sorted(_BATTED_PROJECTION_PATHS):
            self.load_json(path, "安打current射影文書")

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """閉検証対象以外は現checkoutの全byteを読む。"""
        if str(path) in _BATTED_PROJECTION_PATHS:
            return self.base.read_bytes(path)
        return super().read_bytes(path)

    def load_json(self, path: str | PurePosixPath, label: str) -> dict[str, Any]:
        """射影した同byteを重複key拒否で読む。"""
        if str(path) not in _BATTED_PROJECTION_PATHS:
            return super().load_json(path, label)
        current = super().load_json(path, label)
        actual = _object(json.loads(super().read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)
        if _compact_json(current) != _compact_json(actual):
            raise HumanReviewSignatureRecordError("安打headの読取値と射影前rawが不一致")
        return _object(json.loads(self.base.read_bytes(path),
            object_pairs_hook=descriptor_checker._reject_duplicate_keys), label)


def _ordinary_strikeout_current_body(root: Path) -> dict[str, Any]:
    """localは固定192への閉射影だけを検査し、最終公開受理を主張しない。"""
    _batted_current_legacy_documents(root)
    reference = _strikeout_extension_reference(root)
    base = _BattedCarryBaseReader(root, reference["candidate_revision"])
    if ((root / _BATTED_METADATA_DESCRIPTOR).read_bytes()
            == base.read_bytes(_BATTED_METADATA_DESCRIPTOR)):
        return _ordinary_strikeout_body(root)
    _batted_metadata_delta(root, base)
    _batted_handoff_delta(root, base)
    reader = _BattedMetadataProjectionReader(root, base)
    reader.validate_current_views()
    return _ordinary_strikeout_body(root, _reader=reader)


_BATTED_CARRY_FROZEN_KEYS = frozenset({
    "terminal_ordinary_extension_revision", "terminal_core_reference_head_revision",
    "terminal_core_reference_base_revision", "pr192_ordinary_extension_reference_revision",
    "pr192_source_registration_revision", "pr192_source_expectation_revision",
})


# 旧187/191/192/196の実入力path集合を閉じ、後継の取りこぼしを拒否する。
_PR197_GATE6_SCOPE_PATHS = frozenset({
    "contracts/authz/frozen-baselines.json",
    "contracts/state-transition/appendix_e_consumer_handoff_v1.json",
    "contracts/state-transition/branch_row_mapping_v1.json",
    "contracts/state-transition/game_end_contract_schema_v1.json",
    "contracts/state-transition/game_end_contract_v1.json",
    "contracts/state-transition/game_end_coverage_declaration_v1.json",
    "contracts/state-transition/gate6_subject_carry_schema_v1.json",
    "contracts/state-transition/gate6_subject_carry_v1.json",
    "contracts/state-transition/gate6_t1_input_append_schema_v1.json",
    "contracts/state-transition/gate6_t1_input_append_v1.json",
    "contracts/state-transition/gate6_t1_ordinary_pitch_pins_v1.json",
    "contracts/state-transition/gate6_t1_ordinary_pitch_schema_v1.json",
    "contracts/state-transition/gate6_t1_ordinary_pitch_v1.json",
    "contracts/state-transition/human_review_signature_schema_v1.json",
    "contracts/state-transition/input_axes_descriptor_schema_v1.json",
    "contracts/state-transition/input_axes_descriptor_v1.json",
    "contracts/state-transition/ordinary_pitch_request_schema_v1.json",
    "contracts/state-transition/ordinary_pitch_response_schema_v1.json",
    "contracts/state-transition/ordinary_pitch_v1.d.ts",
    "contracts/state-transition/ordinary_pitch_vectors_v1.json",
    "contracts/state-transition/required_set_input_coverage_v1.json",
    "contracts/state-transition/state_transition_contract_schema_v1.json",
    "contracts/state-transition/state_transition_contract_v1.json",
    "contracts/state-transition/strikeout_pitch_cases_v1.json",
    "contracts/state-transition/strikeout_pitch_schema_v1.json",
    "contracts/state-transition/terminal_pitch_cases_v1.json",
    "contracts/tenant_boundary/frozen-inputs.json",
    "docs/features/adr003-stage2-runtime/signatures/gate6-game-end.json",
    "docs/features/adr003-stage2-runtime/signatures/gate6-state-transition.json",
    "docs/features/adr003-stage2-runtime/step33_line_review.md",
    "docs/features/appendix-e-golden-vectors/matrix_rows_line_review.md",
    "docs/features/mvp-delegated-core-review/policy.json",
    "scripts/check_branch_row_mapping.py",
    "scripts/check_deriver_dependencies.py",
    "scripts/check_expander_dependencies.py",
    "scripts/check_gap_register.py",
    "scripts/check_input_axes_descriptor.py",
    "scripts/check_required_set_coverage.py",
    "scripts/core_guard.py",
    "scripts/expand_game_end_cases.py",
    "scripts/expand_state_transition_cases.py",
    "scripts/frozen_baselines.py",
    "scripts/representative_selection.py",
    "scripts/state_transition_freeze.py",
    "scripts/state_transition_normalization.py",
    "tests/fixtures/pr191_ordinary_extension_reference_v1.json",
    "tests/fixtures/pr192_ordinary_extension_reference_v1.json",
    "tests/fixtures/pr192_tenant_source_expected_v1.json",
    "tests/test_human_review_signature.py",
})
_PR197_GATE6_CONTROLLED = frozenset({
    "contracts/authz/frozen-baselines.json",
    "contracts/tenant_boundary/frozen-inputs.json",
    "docs/features/mvp-delegated-core-review/policy.json",
    "scripts/core_guard.py",
})
_PR197_GATE6_TEST_PATH = "tests/test_human_review_signature.py"
_PR197_GATE6_NEW_TYPED = frozenset({
    "pr197_source_revision", "pr197_expectation_revision",
    "pr197_expectation_fixture_sha256",
})
_PR197_GATE6_MIGRATED_TYPED = frozenset({
    "pr197_core_definition_ast_sha256",
    "pr197_generated_facts_sha256",
    "stats_foundation_legacy_core_revision",
    "stats_native_old_product_additions_sha256",
    "stats_native_old_product_bodies_sha256",
    "stats_native_old_product_details_sha256",
    "stats_native_old_product_guards_sha256",
    "stats_native_old_registry_sha256",
    "stats_primitive_sql_open_snapshot_sha256",
    "stats_primitive_sql_read_page_sha256",
    "stats_primitive_sql_read_totals_sha256",
    "stats_primitive_sql_save_source_sha256",
    "stats_primitive_v1_bodies_sha256",
    "stats_primitive_v1_declarations_sha256",
    "stats_primitive_v1_installer_sha256",
    "stats_primitive_v1_operations_sha256",
    "stats_season_source_set_game_a_sha256",
    "stats_season_source_set_game_b_sha256",
})
_PR197_GATE6_DOC_CARRY_TYPED = frozenset({
    "pr197_approved_doc_merge_revision",
    "pr197_core_carry_source_revision",
    "pr197_core_carry_definition_sha256",
})
_PR197_GATE6_RECOVERY_TYPED = frozenset({
    "pr197_identical_cochange_revision",
    "pr197_recovery_source_revision",
    "pr197_recovery_definition_sha256",
})


def _pr197_formal_ledger_binding_successor(
    root: Path, source: bytes, head: bytes, head_sha: str,
) -> None:
    """PR197で検査器実byteを束縛した台帳の唯一の追随形を検証する。"""
    old = _object(json.loads(
        source, object_pairs_hook=descriptor_checker._reject_duplicate_keys,
    ), "PR197固定S台帳")
    actual = _object(json.loads(
        head, object_pairs_hook=descriptor_checker._reject_duplicate_keys,
    ), "PR197現台帳")
    expected = copy.deepcopy(old)
    history = expected.get("history")
    bindings = _object(expected.get("implementation_bindings"), "PR197旧実装束縛")
    code_assets = bindings.get("code_assets")
    if (type(history) is not list or not history
            or history[-1].get("acceptance_id") != "masaki1025/pitchlog#197"
            or history[-1].get("changes") != []
            or type(code_assets) is not list or len(code_assets) != 2
            or code_assets[0].get("path") != "scripts/check_frozen_baselines.py"
            or code_assets[1].get("path") != "scripts/frozen_baselines.py"):
        raise HumanReviewSignatureRecordError("PR197旧台帳の実装束縛前値が不一致")
    checker_path = "scripts/check_frozen_baselines.py"
    checker_bytes = _carry_git_bytes(root, ["show", f"{head_sha}:{checker_path}"])
    if (root / checker_path).read_bytes() != checker_bytes:
        raise HumanReviewSignatureRecordError("PR197検査器実byteがheadと不一致")
    before = copy.deepcopy(bindings)
    code_assets[0]["sha256"] = hashlib.sha256(checker_bytes).hexdigest()
    history[-1]["changes"] = [{
        "aspect": "implementation_bindings",
        "before": before,
        "after": copy.deepcopy(bindings),
    }]
    history[-1]["reason"] += (
        " 同じ未受理PR197内で検査器実byteを改訂したため、code_assetsの固定SHAを"
        "正式base51bの前値から現実byteへ束縛し、履歴1件の変更として記録する。"
    )
    if actual != expected or head != (
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8"):
        raise HumanReviewSignatureRecordError("PR197台帳の限定実装束縛追随が不一致")


def _pr197_gate6_body(root: Path, head_sha: str) -> dict[str, Any]:
    """前置Eで固定した正式baseから旧scopeとPR197数学不変を検査する。"""
    try:
        try:
            import check_tenant_boundary_bypass as tenant_checker
        except ModuleNotFoundError:  # pragma: no cover - package読取経路
            from scripts import check_tenant_boundary_bypass as tenant_checker
        expected = tenant_checker._pr197_fixed_expectations(root)
        base_sha = _string(expected["formal_base_revision"], "PR197正式base")
        source_sha = _string(expected["source_revision"], "PR197固定source")
        expectation_sha = _string(
            expected["identity_successor"]["source_revision"], "PR197 identity source",
        )
        if source_sha != expectation_sha:
            raise HumanReviewSignatureRecordError("PR197 source/identity参照が不一致")
        for older, newer in (
            (base_sha, source_sha), (source_sha, head_sha),
        ):
            _carry_git_bytes(root, ["merge-base", "--is-ancestor", older, newer])
        # Eはtyped fixtureで固定済み。HEADで期待を再生成しない。
        expectation_rev = tenant_checker._PR197_FIXED_EXPECTATION_REVISION
        if type(expectation_rev) is not str:
            raise HumanReviewSignatureRecordError("PR197前置Eが未固定")
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", expectation_rev, head_sha])
        record = _ordinary_record(root)
        scope = {
            *record["assets"], *_ORDINARY_FIXED_INPUTS, *_ORDINARY_EXECUTION_INPUTS,
            *_TERMINAL_EXTENSION_INPUTS, *_STRIKEOUT_EXTENSION_INPUTS,
            *_STRIKEOUT_AUXILIARY_INPUTS, *_BATTED_PROJECTION_PATHS,
            str(GATE6_ORDINARY_PATH), str(GATE6_ORDINARY_SCHEMA_PATH),
            str(ORDINARY_PINS_PATH), str(_TERMINAL_REFERENCE_PATH),
            str(_STRIKEOUT_REFERENCE_PATH), _BATTED_HANDOFF_PATH,
            "docs/features/mvp-delegated-core-review/policy.json",
        }
        if scope != _PR197_GATE6_SCOPE_PATHS or len(record["assets"]) != 9:
            raise HumanReviewSignatureRecordError("PR197旧49path scopeが不一致")
        changed_math = subprocess.run(
            ["git", "diff", "--name-only", base_sha, head_sha, "--",
             "contracts/state-transition/"],
            cwd=root, capture_output=True, check=False, timeout=30,
        )
        if changed_math.returncode != 0 or changed_math.stdout.strip():
            raise HumanReviewSignatureRecordError("PR197で未知を含む数学pathが変更")
        guard = _carry_core_guard(root)
        for path in sorted(scope):
            baseline = _carry_git_bytes(root, ["show", f"{base_sha}:{path}"])
            source = _carry_git_bytes(root, ["show", f"{source_sha}:{path}"])
            head = _carry_git_bytes(root, ["show", f"{head_sha}:{path}"])
            if path == _PR197_GATE6_TEST_PATH:
                # 新負対向の追記はreview対象。現実行byteとGit headの一致は下で必須。
                pass
            elif path == "contracts/tenant_boundary/frozen-inputs.json":
                old = _object(json.loads(source,
                    object_pairs_hook=descriptor_checker._reject_duplicate_keys), "PR197旧typed")
                new = _object(json.loads(head,
                    object_pairs_hook=descriptor_checker._reject_duplicate_keys), "PR197現typed")
                before = _object(old["frozen_inputs"], "PR197旧入力")
                after = _object(new["frozen_inputs"], "PR197現入力")
                expected_added = (
                    _PR197_GATE6_NEW_TYPED
                    | _PR197_GATE6_MIGRATED_TYPED
                    | _PR197_GATE6_DOC_CARRY_TYPED
                    | _PR197_GATE6_RECOVERY_TYPED
                    | {"pr197_pin_origin_commit"}
                )
                if (not all(after.get(key) == value for key, value in before.items())
                        or set(after) - set(before) != expected_added):
                    raise HumanReviewSignatureRecordError("PR197旧typed入力または追加28が不一致")
                try:
                    for key in _PR197_GATE6_MIGRATED_TYPED:
                        guard.frozen_history.read_original_pr197_pin(key, root)
                except guard.frozen_history.ContractError as error:
                    raise HumanReviewSignatureRecordError(
                        "PR197新typed入力の固定Git原典が不一致"
                    ) from error
                try:
                    guard._pr197_merge_carry_pins(root, head_sha)
                except guard.GuardError as error:
                    raise HumanReviewSignatureRecordError(
                        "PR197文書merge typed版が不一致"
                    ) from error
                baseline_inputs = _object(json.loads(baseline,
                    object_pairs_hook=descriptor_checker._reject_duplicate_keys)["frozen_inputs"],
                    "PR197正式base typed")
                if not all(after.get(key) == value for key, value in baseline_inputs.items()):
                    raise HumanReviewSignatureRecordError("PR197正式baseの旧typed入力が変更")
            elif path == "contracts/authz/frozen-baselines.json":
                _pr197_formal_ledger_binding_successor(root, source, head, head_sha)
            elif path == "docs/features/mvp-delegated-core-review/policy.json":
                if head != source:
                    raise HumanReviewSignatureRecordError("PR197旧台帳/policyのS固定byteが変更")
            elif path == "scripts/core_guard.py":
                # 32→34の順序/全helperはcore guard自身の固定AST検査に委ねる。
                pass
            elif baseline != source or baseline != head:
                raise HumanReviewSignatureRecordError(
                    "PR197旧scopeのbase/S/head全byteが不一致: " + path,
                )
            if (root / path).read_bytes() != head:
                raise HumanReviewSignatureRecordError(
                    "PR197旧scopeの実行byteがheadと不一致: " + path,
                )
        # 実行checkerもGit headへ束縛し、private helperだけを差し替える検査を拒否する。
        checker_path = "scripts/check_human_review_signature.py"
        committed_checker = _carry_git_bytes(root, ["show", f"{head_sha}:{checker_path}"])
        if ((root / checker_path).read_bytes() != committed_checker
                or Path(__file__).read_bytes() != committed_checker):
            raise HumanReviewSignatureRecordError("PR197実行checkerがhead全byteと不一致")
        before_core = guard.load_core_areas_at_revision(root, base_sha)
        after_core = guard.load_core_areas_at_revision(root, head_sha)
        guard.validate_pr197_tenant_source_area_path_layers(
            before_core, after_core, root=root, base_revision=base_sha, head_sha=head_sha,
        )
        policy_path = "docs/features/mvp-delegated-core-review/policy.json"
        policy_raw = _carry_git_bytes(root, ["show", f"{head_sha}:{policy_path}"])
        policy = _object(json.loads(
            policy_raw, object_pairs_hook=descriptor_checker._reject_duplicate_keys,
        ), "PR197 policy")
        if (policy["targets"][-1] != {"pr": 197, "branch": "feature/mvp-stats-native-foundation"}
                or len(policy["targets"]) != 20):
            raise HumanReviewSignatureRecordError("PR197 policyの末尾/件数が不一致")
        return record
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, UnicodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("PR197旧scopeのGit/型検査が不成立") from error


def _ordinary_pr197_carry_ci(root: Path, event: Any) -> str:
    """PR197実eventだけで数学不変と委任公開証拠を検査する。"""
    if (type(event.number) is not int or event.number != 197
            or event.head_branch != "feature/mvp-stats-native-foundation"
            or event.repository != "masaki1025/pitchlog"
            or event.head_repository != event.repository):
        raise HumanReviewSignatureRecordError("PR197 carryの実eventが不一致")
    _validate_gate6_checkout(root, event)
    if event.base_sha != _string(
        _pr197_formal_base(root), "PR197前置base",
    ):
        raise HumanReviewSignatureRecordError("PR197 carryの実baseが前置Eと不一致")
    record = _pr197_gate6_body(root, event.head_sha)
    _ordinary_head(root, event, record)
    _validate_gate6_head_bytes(root, event, {"path": str(GATE6_ORDINARY_PATH)})
    guard = _carry_core_guard(root)
    try:
        guard.verify_delegated_confirmation(root, event)
    except guard.GuardError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    return ("gate6 PR197 carry: HISTORICAL ordinary33/PR191/PR192/PR196 PRESERVED; "
            "DELEGATED VERIFIED; no new historical acceptance; not a personal signature")


def _pr197_formal_base(root: Path) -> str:
    """既前置Eとtyped pinで検証済みの正式baseだけを返す。"""
    try:
        import check_tenant_boundary_bypass as tenant_checker
    except ModuleNotFoundError:  # pragma: no cover - package読取経路
        from scripts import check_tenant_boundary_bypass as tenant_checker
    try:
        return _string(tenant_checker._pr197_fixed_expectations(root)["formal_base_revision"],
                       "PR197正式base")
    except tenant_checker.ContractError as error:
        raise HumanReviewSignatureRecordError("PR197前置Eが不一致") from error

def _ordinary_batted_carry_ci(root: Path, event: Any) -> str:
    """実PR196だけで既191/192全検査をbaseへ適用し、署名scopeを拡張しない。"""
    try:
        if (type(event.number) is not int or event.number != 196
                or event.head_branch != "feature/mvp-batted-hits"
                or event.repository != "masaki1025/pitchlog"
                or event.head_repository != event.repository
                or any(type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None
                       for value in (event.base_sha, event.head_sha))):
            raise HumanReviewSignatureRecordError("安打carryは実PR196/repo/branchだけに限定する")
        _validate_gate6_checkout(root, event)
        _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                               event.base_sha, event.head_sha])
        base = _BattedCarryBaseReader(root, event.base_sha)
        pins = _ordinary_pins(root)
        for path, digest in ((GATE6_ORDINARY_PATH, pins["record_sha256"]),
                             (GATE6_ORDINARY_SCHEMA_PATH, pins["schema_sha256"])):
            if hashlib.sha256(base.read_bytes(path)).hexdigest() != digest:
                raise HumanReviewSignatureRecordError("安打baseの旧record/schemaが固定値と不一致")
        record = base.load_json(GATE6_ORDINARY_PATH, "安打base旧record")
        _batted_current_legacy_documents(root)
        # 検査コード/後発登録全体のbase不変は要求しない。数学・原典の閉集合だけを保護する。
        protected = {*record["assets"], *_ORDINARY_FIXED_INPUTS,
            str(GATE6_ORDINARY_PATH), str(GATE6_ORDINARY_SCHEMA_PATH), str(ORDINARY_PINS_PATH),
            str(_TERMINAL_REFERENCE_PATH), str(_STRIKEOUT_REFERENCE_PATH),
            "contracts/state-transition/terminal_pitch_cases_v1.json",
            *_STRIKEOUT_AUXILIARY_INPUTS, str(descriptor_checker.SCHEMA_PATH),
            "tests/fixtures/pr192_tenant_source_expected_v1.json"}
        _batted_metadata_delta(root, base)
        _batted_handoff_delta(root, base)
        _BattedMetadataProjectionReader(root, base).validate_current_views()
        for path in protected - _BATTED_PROJECTION_PATHS:
            if (root / path).read_bytes() != base.read_bytes(path):
                raise HumanReviewSignatureRecordError(
                    "安打carryで数学/旧署名/必要原典がbaseから変更")
        frozen_path = "contracts/tenant_boundary/frozen-inputs.json"
        old_inputs = base.load_json(frozen_path, "安打base固定入力")["frozen_inputs"]
        inputs = _Gate6CurrentReader(root).load_json(frozen_path, "安打固定入力")["frozen_inputs"]
        for key in _BATTED_CARRY_FROZEN_KEYS:
            if _compact_json(old_inputs[key]) != _compact_json(inputs[key]):
                raise HumanReviewSignatureRecordError("安打carryの191/192固定登録がbaseと不一致")
        reference = _strikeout_extension_reference(root)
        _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                               reference["candidate_revision"], event.base_sha])
        # headを期待原典にしない。既ordinary/terminal/strikeoutの全bodyを実baseで再利用する。
        _ordinary_strikeout_body(root, _reader=base)
        guard = _carry_core_guard(root)
        try:
            base_policy, _ = guard._load_delegation_policy(root, event.base_sha)
            head_policy, _ = guard._load_delegation_policy(root, event.head_sha)
            origins = _ordinary_policy_origins(root, guard, _OrdinaryAcceptedReader(root), pins)
            if (base_policy != origins["integration18"]
                    or not _ordinary_policy_matches(head_policy, base_policy, allow_append=True)
                    or head_policy["targets"] != base_policy["targets"] + [
                        {"pr": 196, "branch": "feature/mvp-batted-hits"}]):
                raise HumanReviewSignatureRecordError("安打carryの旧policy/単一196末尾が不一致")
            _ordinary_head(root, event, record)
            for path in _STRIKEOUT_EXTENSION_INPUTS | _BATTED_PROJECTION_PATHS:
                if (root / path).read_bytes() != _carry_git_bytes(
                    root, ["show", f"{event.head_sha}:{path}"],
                ):
                    raise HumanReviewSignatureRecordError("安打carryの実行依存が最終HEADと不一致")
            guard.verify_delegated_confirmation(root, event)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        return ("gate6 PR196 carry: HISTORICAL ordinary33/PR191/PR192 PRESERVED; "
                "DELEGATED VERIFIED; no new historical acceptance; not a personal signature")
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError(
            "安打carryの実base/最終公開証拠検査が不成立") from error


def _ordinary_terminal_ci(root: Path, event: Any) -> str:
    """実PR191の既受理継承と有限追加の公開PO証拠を両方検査する。"""
    try:
        if (type(event.number) is not int or event.number != 191
                or event.head_branch != "feature/mvp-terminal-pitches"
                or event.repository != "masaki1025/pitchlog"
                or event.head_repository != event.repository):
            raise HumanReviewSignatureRecordError("terminal追加は実PR191だけに限定する")
        _validate_gate6_checkout(root, event)
        reference = _terminal_extension_reference(root)
        materials = _ordinary_base_materials(root, event)
        old_reader = _TerminalLegacyReader(root)
        if event.base_sha != reference["base_revision"]:
            raise HumanReviewSignatureRecordError("terminal actual baseが固定基線と不一致")
        for path, raw in materials.items():
            if raw != old_reader.read_bytes(path):
                raise HumanReviewSignatureRecordError("terminal baseの旧scopeが不一致")
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", event.base_sha, event.head_sha])
        _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                               reference["candidate_revision"], event.head_sha])
        guard = _carry_core_guard(root)
        try:
            base_policy, _ = guard._load_delegation_policy(root, event.base_sha)
            head_policy, _ = guard._load_delegation_policy(root, event.head_sha)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        origins = _ordinary_policy_origins(root, guard, _OrdinaryAcceptedReader(root),
                                           _ordinary_pins(root))
        if base_policy != origins["integration18"] or head_policy != base_policy:
            raise HumanReviewSignatureRecordError("terminal policyの固定18全値が不一致")
        record = _ordinary_terminal_body(root)
        _ordinary_head(root, event, record)
        for path in _TERMINAL_EXTENSION_INPUTS:
            if (root / path).read_bytes() != _carry_git_bytes(
                root, ["show", f"{event.head_sha}:{path}"],
            ):
                raise HumanReviewSignatureRecordError("terminal全検査依存が最終HEADと不一致")
        try:
            guard.verify_delegated_confirmation(root, event)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        return ("gate6 old ordinary33: HISTORICAL PRESERVED; PR191 terminal extension: "
                "DELEGATED VERIFIED; not new PR187 acceptance; not a personal signature")
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("terminalの公開委任/実HEAD検査が不成立") from error


def _ordinary_ci(root: Path, event: Any, *, new_acceptance: bool) -> str:
    """今回新受理とbase-first不変継承を混同せず、失敗はfallbackしない。"""
    try:
        if (type(event.number) is not int or event.number <= 0
                or event.repository != "masaki1025/pitchlog"
                or event.head_repository != "masaki1025/pitchlog"
                or not isinstance(event.head_branch, str)
                or not event.head_branch.startswith(("feature/", "fix/"))):
            raise HumanReviewSignatureRecordError("通常33のPR event識別が不正")
        _validate_gate6_checkout(root, event)
        pins = _ordinary_pins(root)
        if new_acceptance:
            if (event.number != _ORDINARY_PR or event.head_branch != _ORDINARY_BRANCH
                    or event.base_sha != pins["public_base"]):
                raise HumanReviewSignatureRecordError("通常33の新受理は実PR187だけに限定する")
        else:
            if event.number in {_ORDINARY_PR, _GATE6_T1_APPEND_PR, _GATE6_INTRODUCTION_PR}:
                raise HumanReviewSignatureRecordError("通常33の継承PRが導入対象と混同された")
            materials = _ordinary_base_materials(root, event)
            anchor = _OrdinaryAcceptedReader(root)
            guard = _carry_core_guard(root)
            try:
                base_policy, _ = guard._load_delegation_policy(root, event.base_sha)
                head_policy, _ = guard._load_delegation_policy(root, event.head_sha)
            except guard.GuardError as error:
                raise HumanReviewSignatureRecordError(str(error)) from error
            origins = _ordinary_policy_origins(root, guard, anchor, pins)
            mode = _ordinary_policy_mode(base_policy, origins, allow_append=True)
            if mode == "integration18":
                if event.number <= _ORDINARY_INTEGRATION_PR:
                    raise HumanReviewSignatureRecordError("正式189後18の継承は後続PRだけに限定する")
                _carry_git_bytes(root, ["merge-base", "--is-ancestor",
                                       event.base_sha, event.head_sha])
            if not _ordinary_policy_matches(head_policy, base_policy, allow_append=True):
                raise HumanReviewSignatureRecordError("通常33のbase policyから末尾追記以外の変更")
            for path, raw in materials.items():
                if (root / path).read_bytes() != raw:
                    raise HumanReviewSignatureRecordError("後続PRで通常33の固定原本が変更された")
        record = _ordinary_body(root, allow_policy_append=not new_acceptance,
                                policy_mode="legacy14" if new_acceptance else mode)
        _ordinary_head(root, event, record)
        if new_acceptance:
            guard = _carry_core_guard(root)
            try:
                guard.verify_delegated_confirmation(root, event)
            except guard.GuardError as error:
                raise HumanReviewSignatureRecordError(str(error)) from error
            return "gate6 ordinary33: DELEGATED VERIFIED (not a personal signature)"
        return "gate6 ordinary33: UNCHANGED FROM PR BASE; no new ordinary acceptance"
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("通常33の公開/継承入力が不正") from error


def _ordinary_integration_ci(root: Path, event: Any) -> str:
    """PR189だけの候補統合carryを検証し、旧187受理/本人署名へ読み替えない。"""
    try:
        if (type(event.number) is not int or event.number != _ORDINARY_INTEGRATION_PR
                or event.repository != "masaki1025/pitchlog"
                or event.head_repository != "masaki1025/pitchlog"
                or event.head_branch != _ORDINARY_INTEGRATION_BRANCH
                or any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{40}", v) is None
                       for v in (event.base_sha, event.head_sha))):
            raise HumanReviewSignatureRecordError("通常33 integrationは実PR189 eventだけに限定する")
        _validate_gate6_checkout(root, event)
        _carry_git_bytes(root, ["merge-base", "--is-ancestor", event.base_sha, event.head_sha])
        if _ordinary_base_presence(root, event.base_sha) != (False, False):
            raise HumanReviewSignatureRecordError("通常33 integrationのbaseは両資産不存在で必要")
        if not all((root / path).exists() for path in (
                GATE6_ORDINARY_PATH, GATE6_ORDINARY_SCHEMA_PATH)):
            raise HumanReviewSignatureRecordError("通常33 integrationのhead両資産が未提供")
        pins = _ordinary_pins(root)
        anchor = _OrdinaryAcceptedReader(root)
        guard = _carry_core_guard(root)
        origins = _ordinary_policy_origins(root, guard, anchor, pins)
        try:
            base_policy, _ = guard._load_delegation_policy(root, event.base_sha)
            head_policy, _ = guard._load_delegation_policy(root, event.head_sha)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        if base_policy != origins["integration18"] or head_policy != origins["integration18"]:
            raise HumanReviewSignatureRecordError(
                "通常33 integrationの実base/head policy18全fieldが不一致")
        record = _ordinary_body(root, policy_mode="integration18")
        _ordinary_head(root, event, record)
        try:
            guard.verify_delegated_confirmation(root, event)
        except guard.GuardError as error:
            raise HumanReviewSignatureRecordError(str(error)) from error
        return ("gate6 PR189 integration carry: DELEGATED VERIFIED; "
                "not PR187 acceptance; not a personal signature")
    except HumanReviewSignatureRecordError:
        raise
    except (KeyError, TypeError, ValueError, OSError,
            descriptor_checker.DescriptorCheckError) as error:
        raise HumanReviewSignatureRecordError("通常33 integrationの公開入力が不正") from error


def validate_gate6_ci_event(root: Path, event: Any) -> str:
    """PR183の新受理と、別PRの変更を伴わない継承を区別する。"""
    if event is None:
        raise HumanReviewSignatureRecordError("最終PR eventが未提供")
    if event.number == 197:
        return _ordinary_pr197_carry_ci(root, event)
    if event.number == 196:
        return _ordinary_batted_carry_ci(root, event)
    if event.number == 192:
        return _ordinary_strikeout_ci(root, event)
    if event.number == 191:
        return _ordinary_terminal_ci(root, event)
    if event.number == _ORDINARY_PR:
        return _ordinary_ci(root, event, new_acceptance=True)
    if event.number == _ORDINARY_INTEGRATION_PR:
        return _ordinary_integration_ci(root, event)
    # 旧導入PRの分岐は保持する。後続ではbaseを先読し片側欠損も拒否する。
    if event.number not in {_GATE6_T1_APPEND_PR, _GATE6_INTRODUCTION_PR}:
        if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None
               for value in (event.base_sha, event.head_sha)):
            raise HumanReviewSignatureRecordError("通常33継承eventのGit識別値が不正")
        if _ordinary_base_present(root, event.base_sha):
            return _ordinary_ci(root, event, new_acceptance=False)
        if _ordinary_present(root):
            raise HumanReviewSignatureRecordError("通常33の新受理は実PR187以外に供給できない")
    if event.number == _GATE6_T1_APPEND_PR:
        validate_delegated_gate6_t1_input_append(root, event)
        return "gate6 T1 input append: DELEGATED VERIFIED (not a personal signature)"
    if event.number == _GATE6_INTRODUCTION_PR:
        validate_delegated_gate6_subject_carry(root, event)
        return "gate6 delegated subject carry: VERIFIED (not a personal signature)"
    if _gate6_t1_append_is_ready(root):
        validate_other_pr_gate6_t1_append_unchanged(root, event)
        return "gate6 T1 append: UNCHANGED FROM PR BASE; no new PR185 acceptance"
    validate_other_pr_gate6_carry_unchanged(root, event)
    return "gate6 prior subject carry: UNCHANGED FROM PR BASE; no new PR183 acceptance"


def main(argv: Sequence[str] | None = None) -> int:
    """署名記録を検証するか、契約から逐行確認シートを生成する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, nargs="?", help="検証する署名記録JSON")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--matrix-review-contract",
        type=Path,
        help="逐行確認シートの入力となる状況判定契約JSON",
    )
    parser.add_argument(
        "--stage2-review",
        action="store_true",
        help="ステップ22〜32の規範行と派生caseの未確認シートを生成する",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="逐行確認シートの出力先",
    )
    parser.add_argument("--gate6-carry", action="store_true", help="今回PRの対象継承を検査する")
    parser.add_argument("--ci", action="store_true", help="最終PR event/外部委任証拠まで必須にする")
    args = parser.parse_args(argv)
    try:
        if args.ci and not args.gate6_carry:
            parser.error("--ciは--gate6-carryとだけ併用する")
        if args.gate6_carry:
            if (
                args.record is not None or args.output is not None
                or args.stage2_review or args.matrix_review_contract
            ):
                parser.error("--gate6-carryは既署名/生成モードと併用できない")
            if args.ci:
                guard = _carry_core_guard(args.root)
                try:
                    event = guard.load_pull_request_event()
                except guard.GuardError as error:
                    raise HumanReviewSignatureRecordError(str(error)) from error
                print(validate_gate6_ci_event(args.root, event))
            else:
                validate_gate6_subject_carry(args.root)
                print("gate6 subject carry: TECHNICAL ONLY; final delegation NOT CHECKED; "
                      "no new ordinary acceptance")
            return 0
        if args.stage2_review:
            if args.record is not None or args.output is None or args.matrix_review_contract:
                parser.error("--stage2-reviewはrecordなし・--outputありで指定する")
            generate_stage2_line_review_sheet(args.root, args.output)
            print(f"stage2 review sheet: GENERATED: {args.output}")
            return 0
        if args.matrix_review_contract is not None:
            if args.record is not None or args.output is None:
                parser.error(
                    "--matrix-review-contractはrecordなし・--outputありで指定する"
                )
            generate_matrix_rows_review_sheet(
                args.root,
                args.matrix_review_contract,
                args.output,
            )
            print(f"matrixRows review sheet: GENERATED: {args.output}")
            return 0
        if args.record is None or args.output is not None:
            parser.error("署名検査ではrecordだけを指定する")
        raw_record = descriptor_checker.load_json(args.record, "署名記録")
        record = _object(raw_record, "署名記録")
        validate_signature_record(args.root, record)
    except (
        descriptor_checker.DescriptorCheckError,
        HumanReviewSignatureRecordError,
    ) as error:
        print(f"human review signature record: FAIL: {error}", file=sys.stderr)
        return 1
    print("human review signature record: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
