"""P3有効全sourceを既唯一生成T5核へ反復する保存前候補。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from pitchlog.stats.facts import evaluate_native_projection
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.past_correction_capsule import P3CurrentCapsule


class PastCorrectionStatsError(RuntimeError):
    """有効原本とT5全件の結合が不成立。"""


class PastCorrectionStatsUnsupported(PastCorrectionStatsError):
    """唯一T5の閉評価がまだ扱えない。"""


@dataclass(frozen=True, slots=True)
class P3StatsSourceCandidate:
    """唯一T5評価済みだが保存資格ではない各有効source。"""

    d1: int
    original_event_id: UUID
    effective_event_id: UUID
    effective_play_row_id: UUID
    original_evaluation: dict[str, object]
    original_evaluation_digest: str
    evaluation: dict[str, object]
    evaluation_digest: str


@dataclass(frozen=True, slots=True)
class P3StatsCandidate:
    """全評価のcapsule束縛。SQL canonical source-set SHAとは別値。"""

    capsule_id: UUID
    model_sha256: str
    sources: tuple[P3StatsSourceCandidate, ...]
    evaluation_set_digest: str


def _member(value: object, key: str) -> object:
    """閉JSONの必須memberを型補完せず読む。"""
    if type(value) is not dict or key not in value:
        raise ValueError("P3 T5原本memberが欠落")
    return cast(dict[str, object], value)[key]


def _string(value: object) -> str:
    """UUIDの自由文字列化を拒否する。"""
    if type(value) is not str:
        raise ValueError("P3 T5原本識別子が不正")
    return value


def evaluate_p3_capsule_stats(capsule: P3CurrentCapsule) -> P3StatsCandidate:
    """欠測や未対応操作を補わず、全D1を生成T5へ一回ずつ渡す。"""
    if (
        type(capsule) is not P3CurrentCapsule
        or not 1 <= len(capsule.items) <= 25
        or type(SOURCE_MODEL_HASH) is not str
        or re.fullmatch(r"sha256:[a-f0-9]{64}", SOURCE_MODEL_HASH) is None
    ):
        raise PastCorrectionStatsError("P3 T5入力が不正")
    result: list[P3StatsSourceCandidate] = []
    for d1, item in enumerate(capsule.items, start=1):
        if (
            type(item) is not dict
            or item.get("d1") != d1
            or type(item.get("payload")) is not dict
            or type(item.get("digest")) is not str
            or item["digest"]
            != source_fingerprint({k: v for k, v in item.items() if k != "digest"})
        ):
            raise PastCorrectionStatsError("P3 T5 itemとdigestが不一致")
        try:
            original = UUID(_string(item["original_event_id"]))
            effective = UUID(_string(item["effective_event_id"]))
            play_row = UUID(_string(item["effective_play_row_id"]))
            payload_value = _json_value(item["payload"])
            if (
                type(payload_value) is not dict
                or _member(
                    _member(
                        _member(_member(payload_value, "calculation"), "request"),
                        "playIdentity",
                    ),
                    "eventId",
                )
                != str(original)
                or _member(item["play_row"], "id") != str(play_row)
                or _member(item["play_row"], "source_event_id")
                != str(effective)
            ):
                raise ValueError
            payload = cast(dict[str, object], payload_value)
            original_payload_value = _json_value(item["original_payload"])
            if type(original_payload_value) is not dict:
                raise ValueError
            original_request = _member(
                _member(original_payload_value, "calculation"), "request"
            )
            effective_request = _member(
                _member(payload_value, "calculation"), "request"
            )
            original_rules = _member(original_request, "rules")
            effective_rules = _member(effective_request, "rules")
            if type(original_rules) is not dict or type(effective_rules) is not dict:
                raise ValueError
            rule_sha256 = source_fingerprint(cast(dict[str, object], original_rules))
            if (
                source_fingerprint(cast(dict[str, object], effective_rules))
                != rule_sha256
                or _member(_member(original_request, "source"), "rulesDigest")
                != rule_sha256
                or _member(_member(effective_request, "source"), "rulesDigest")
                != rule_sha256
            ):
                raise ValueError
            original_evaluation = evaluate_native_projection(
                cast(dict[str, object], original_payload_value),
                source_event_id=original,
            )
            evaluation = evaluate_native_projection(
                payload, source_event_id=effective
            )
            if type(evaluation) is not dict or type(original_evaluation) is not dict:
                raise ValueError
            original_value = _json_value(original_evaluation)
            full_value = _json_value(evaluation)
            if type(full_value) is not dict or type(original_value) is not dict:
                raise ValueError
            original_full = cast(dict[str, object], original_value)
            full = cast(dict[str, object], full_value)
            original_full["native_rule_sha256"] = rule_sha256
            full["native_rule_sha256"] = rule_sha256
        except (ValueError, TypeError, KeyError, IndexError):
            raise PastCorrectionStatsError("P3 T5原本を評価できない") from None
        if (
            set(original_full) != {
                "metrics", "pa_row", "source_event_id", "selected", "decisions",
                "native_rule_sha256",
            }
            or set(full) != set(original_full)
            or original_full["source_event_id"] != str(original)
            or full["source_event_id"] != str(effective)
        ):
            raise PastCorrectionStatsUnsupported("P3 T5評価の閉形が不一致")
        result.append(
            P3StatsSourceCandidate(
                d1,
                original,
                effective,
                play_row,
                original_full,
                source_fingerprint(original_full),
                full,
                source_fingerprint(full),
            )
        )
    evaluation_set_digest = source_fingerprint(
        {
            "capsule_id": str(capsule.capsule_id),
            "model_sha256": SOURCE_MODEL_HASH,
            "capsule_source_set_digest": capsule.source_set_digest,
            "sources": [
                {
                    "d1": source.d1,
                    "event_id": str(source.effective_event_id),
                    "play_row_id": str(source.effective_play_row_id),
                    "original_evaluation_digest": source.original_evaluation_digest,
                    "evaluation_digest": source.evaluation_digest,
                }
                for source in result
            ],
        }
    )
    return P3StatsCandidate(
        capsule.capsule_id,
        SOURCE_MODEL_HASH,
        tuple(result),
        evaluation_set_digest,
    )
