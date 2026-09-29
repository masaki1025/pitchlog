"""人間確認の署名記録を検証し、未確認の逐行確認シートを生成する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath
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
            modality_name = "強制" if modality == "forced" else "任意"
            parts.append(f"{label}→{destination}塁（{modality_name}）")
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


def main(argv: Sequence[str] | None = None) -> int:
    """署名記録を検証するか、状況判定契約から逐行確認シートを生成する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, nargs="?", help="検証する署名記録JSON")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--matrix-review-contract",
        type=Path,
        help="逐行確認シートの入力となる状況判定契約JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="逐行確認シートの出力先",
    )
    args = parser.parse_args(argv)
    try:
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
