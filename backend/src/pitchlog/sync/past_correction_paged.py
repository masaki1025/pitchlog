"""P3通常v3原本を25件ずつ唯一核へ通す同TXの純準備。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.past_correction_lineup import (
    CorrectedLineupPitch,
    CorrectionPageState,
    LineupCorrectionUnsupported,
    SavedLineupPitch,
    _evaluate_page,
    build_corrected_lineup_payloads,
)
from pitchlog.repositories.past_correction_source import (
    PastCorrectionSourceUnavailable,
    visit_past_correction_v3_source_pages,
)
from pitchlog.repositories.play_prefix import LineupPrefixDocument
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync.change_path import _bound_target
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_capsule import (
    PastCorrectionCapsuleError,
    build_p3_current_item,
    p3_item_digest_source,
)
from pitchlog.sync.past_correction_checkpoint import (
    PastCorrectionCheckpointError,
    build_corrected_lineup_checkpoint_from_head,
)
from pitchlog.sync.past_correction_payload import (
    PastCorrectionPayloadError,
    bind_lineup_pitch_change_target,
    read_lineup_pitch_change_payload,
)
from pitchlog.sync.past_correction_physical import (
    CorrectedPhysicalPitch,
    prepare_corrected_physical_pitches,
)
from pitchlog.sync.past_correction_stats import (
    P3StatsSourceCandidate,
    PastCorrectionStatsError,
    evaluate_p3_current_item_stats,
)
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload


class PastCorrectionPageUnavailable(RuntimeError):
    """P3の同一原本・唯一評価・ページ間sealが不成立。"""


@dataclass(frozen=True, slots=True)
class PreparedP3Page:
    """同TX中だけ存在する最大25行の元原本と有効版。"""

    originals: tuple[SavedLineupPitch, ...]
    corrected: tuple[CorrectedLineupPitch, ...]
    payloads: tuple[LineupPitchPlayPayload, ...]
    physical: tuple[CorrectedPhysicalPitch, ...]
    items: tuple[dict[str, object], ...] = ()
    stats_sources: tuple[P3StatsSourceCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class P3PagedPreparationProof:
    """全ページ読了後の固定headと再走照合用seal。DB保存資格ではない。"""

    internal_generation: int
    watermark: int
    checkpoint: LineupPrefixDocument
    next_checkpoint: LineupPrefixDocument
    state: CorrectionPageState
    page_count: int
    page_seal: str
    digest_format: str
    source_chain: str
    evaluation_chain: str
    source_set_digest: str
    evaluation_set_digest: str
    target: SavedLineupPitch


def _chain_step(previous: str, d1: int, *digests: str) -> str:
    """DB側も同じASCII式で再計算できる有界行digest連鎖。"""
    if (
        type(d1) is not int
        or d1 < 1
        or re.fullmatch(r"[a-f0-9]{64}", previous) is None
        or any(
            type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None
            for value in digests
        )
    ):
        raise PastCorrectionPageUnavailable("P3連鎖digest入力が不正")
    return hashlib.sha256(
        ":".join((previous, str(d1), *digests)).encode("ascii")
    ).hexdigest()


def fingerprint_p3_streaming_array(
    before: Mapping[str, object],
    array_key: str,
    values: Iterable[object],
    after: Mapping[str, object],
) -> str:
    """source_fingerprintの同じ正規JSONを配列だけ逐次SHAへ流す。"""
    if (
        type(array_key) is not str
        or not array_key
        or not isinstance(before, Mapping)
        or not isinstance(after, Mapping)
        or any(type(key) is not str or key >= array_key for key in before)
        or any(type(key) is not str or key <= array_key for key in after)
        or not isinstance(values, Iterable)
        or isinstance(values, (str, bytes, Mapping))
    ):
        raise PastCorrectionPageUnavailable("P3逐次指紋の閉形が不正")

    def encoded(value: object) -> bytes:
        return json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    sha = hashlib.sha256()
    sha.update(b"{")
    first = True

    def field(key: str, value: object) -> None:
        nonlocal first
        if not first:
            sha.update(b",")
        sha.update(encoded(key))
        sha.update(b":")
        sha.update(encoded(value))
        first = False

    try:
        for key in sorted(before):
            field(key, before[key])
        if not first:
            sha.update(b",")
        sha.update(encoded(array_key))
        sha.update(b":[")
        first = True
        for value in values:
            if not first:
                sha.update(b",")
            sha.update(encoded(value))
            first = False
        sha.update(b"]")
        for key in sorted(after):
            sha.update(b",")
            sha.update(encoded(key))
            sha.update(b":")
            sha.update(encoded(after[key]))
        sha.update(b"}")
    except (TypeError, ValueError, OverflowError):
        raise PastCorrectionPageUnavailable("P3逐次指紋の値が不正") from None
    return sha.hexdigest()


def _page_seal(previous: str, page: PreparedP3Page) -> str:
    """頁内も一行ずつ正規JSONへ結び、全履歴配列を保持しない。"""
    if (
        type(page) is not PreparedP3Page
        or not 1 <= len(page.originals) <= 25
        or len(page.corrected) != len(page.payloads)
        or len(page.corrected) != len(page.physical)
        or bool(page.items) != bool(page.stats_sources)
        or (page.items and len(page.items) != len(page.originals))
        or (page.stats_sources and len(page.stats_sources) != len(page.originals))
    ):
        raise PastCorrectionPageUnavailable("P3準備頁の閉形が不正")
    rolling = source_fingerprint(
        {"previous": previous, "first_d1": page.originals[0].d1}
    )
    for saved in page.originals:
        if (
            type(saved) is not SavedLineupPitch
            or type(saved.payload) is not LineupPitchPlayPayload
            or type(saved.play_row) is not dict
            or type(saved.play_runners) is not tuple
        ):
            raise PastCorrectionPageUnavailable("P3準備頁の原本が欠落")
        rolling = source_fingerprint(
            {
                "previous": rolling,
                "d1": saved.d1,
                "d2": saved.d2,
                "event_id": str(saved.source_event_id),
                "payload": saved.payload.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                "play_row": _json_value(saved.play_row),
                "play_runners": _json_value(saved.play_runners),
            }
        )
    for frame, payload, physical in zip(
        page.corrected, page.payloads, page.physical, strict=True
    ):
        if (
            type(frame) is not CorrectedLineupPitch
            or type(payload) is not LineupPitchPlayPayload
            or type(physical) is not CorrectedPhysicalPitch
            or frame.d1 != physical.d1
            or frame.source_event_id != physical.original_event_id
        ):
            raise PastCorrectionPageUnavailable("P3準備頁の有効版が不一致")
        rolling = source_fingerprint(
            {
                "previous": rolling,
                "d1": frame.d1,
                "d2": frame.d2,
                "event_id": str(frame.source_event_id),
                "request": frame.corrected_request.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                "response": frame.corrected_response.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                "payload": payload.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                "effective_event_id": str(physical.effective_event_id),
                "play_row": _json_value(physical.play_row),
                "play_runners": _json_value(physical.play_runners),
            }
        )
    for item, source in zip(page.items, page.stats_sources, strict=True):
        if (
            type(item) is not dict
            or type(source) is not P3StatsSourceCandidate
            or item.get("d1") != source.d1
            or item.get("digest")
            != source_fingerprint(
                p3_item_digest_source(item)
            )
        ):
            raise PastCorrectionPageUnavailable("P3頁itemとT5候補が不一致")
        rolling = source_fingerprint(
            {
                "previous": rolling,
                "item_digest": item["digest"],
                "original_evaluation_digest": source.original_evaluation_digest,
                "evaluation_digest": source.evaluation_digest,
                "effective_event_id": str(source.effective_event_id),
            }
        )
    return rolling


def _assert_page_binding(
    scope: _TenantTransaction,
    event: SyncEvent,
    bound_source: object,
    expected_target: tuple[UUID, int, int, str],
) -> None:
    """有界処理の前後で同じ真正受付と対象を再確認し、失効を停止する。"""
    if _bound_target(scope, event, bound_source) != expected_target:
        raise PastCorrectionPageUnavailable("P3頁の真正受付が変化した")


def visit_p3_lineup_correction_pages(
    scope: _TenantTransaction,
    event: SyncEvent,
    *,
    capsule_id: UUID,
    change_event_id: UUID,
    bound_source: object,
    consume: Callable[[PreparedP3Page], None],
) -> P3PagedPreparationProof:
    """元値・訂正値を同じ唯一核で頁ごと検証し、全頁sealを返す。"""
    if (
        type(scope) is not _TenantTransaction
        or type(event) is not SyncEvent
        or event.v5 != "play_change"
        or not isinstance(event.v7, Mapping)
        or type(capsule_id) is not UUID
        or type(change_event_id) is not UUID
        or capsule_id == change_event_id
        or capsule_id.int == 0
        or change_event_id.int == 0
        or not callable(consume)
    ):
        raise PastCorrectionPageUnavailable("P3頁準備の入力が不正")
    try:
        expected_target = _bound_target(scope, event, bound_source)
        game_id, generation, target_d1 = expected_target[:3]
        if game_id != UUID(event.game_id):
            raise PastCorrectionPageUnavailable("P3頁対象試合が不一致")
        payload = read_lineup_pitch_change_payload(
            json.dumps(_json_value(event.v7), ensure_ascii=False, allow_nan=False)
        )
        state = CorrectionPageState()
        page_count = 0
        seal = "0" * 64
        source_chain = "0" * 64
        evaluation_chain = "0" * 64
        legacy_items: list[dict[str, object]] | None = []
        legacy_stats: list[P3StatsSourceCandidate] | None = []
        target: SavedLineupPitch | None = None
        last_original: SavedLineupPitch | None = None
        last_corrected: CorrectedLineupPitch | None = None
        last_physical: CorrectedPhysicalPitch | None = None

        with open_domain_host() as host:

            def visit(
                rows: tuple[SavedLineupPitch, ...], checkpoint: LineupPrefixDocument
            ) -> None:
                nonlocal state, page_count, seal, target
                nonlocal source_chain, evaluation_chain
                nonlocal legacy_items, legacy_stats
                nonlocal last_original, last_corrected, last_physical
                _assert_page_binding(scope, event, bound_source, expected_target)
                for saved in rows:
                    if saved.d1 == target_d1:
                        if target is not None:
                            raise PastCorrectionPageUnavailable("P3対象原本が重複")
                        target = saved
                checkpoint_ids = tuple(
                    uuid5(capsule_id, f"checkpoint:{row.source_event_id}")
                    for row in rows
                    if row.d1 >= target_d1
                )
                state, corrected = _evaluate_page(
                    rows,
                    payload.replacement_result_id,
                    checkpoint_ids,
                    host,
                    state,
                    target_d1=target_d1,
                )
                if corrected:
                    payloads = build_corrected_lineup_payloads(
                        rows,
                        corrected,
                        payload.replacement_observations,
                        target_d1=target_d1,
                    )
                    physical = prepare_corrected_physical_pitches(
                        rows,
                        corrected,
                        payloads,
                        tenant_id=scope._bound_tenant_id,
                        game_id=game_id,
                        capsule_id=capsule_id,
                        change_event_id=change_event_id,
                        target_d1=target_d1,
                    )
                else:
                    payloads = ()
                    physical = ()
                by_d1 = {frame.d1: frame for frame in corrected}
                payload_by_d1 = {
                    frame.d1: value
                    for frame, value in zip(corrected, payloads, strict=True)
                }
                physical_by_d1 = {value.d1: value for value in physical}
                if any(
                    len(values) != len(corrected)
                    for values in (by_d1, payload_by_d1, physical_by_d1)
                ):
                    raise PastCorrectionPageUnavailable("P3頁有効位置が重複")
                items = tuple(
                    build_p3_current_item(
                        saved,
                        target_d1=target_d1,
                        change_event_id=change_event_id,
                        checkpoint=checkpoint,
                        frame=by_d1.get(saved.d1),
                        payload=payload_by_d1.get(saved.d1),
                        projected=physical_by_d1.get(saved.d1),
                    )
                    for saved in rows
                )
                stats_sources = tuple(
                    evaluate_p3_current_item_stats(item, saved.d1)
                    for saved, item in zip(rows, items, strict=True)
                )
                page = PreparedP3Page(
                    rows, corrected, payloads, physical, items, stats_sources
                )
                seal = _page_seal(seal, page)
                for item, stats_source in zip(items, stats_sources, strict=True):
                    item_digest = item["digest"]
                    if type(item_digest) is not str:
                        raise PastCorrectionPageUnavailable("P3 item digestが不正")
                    source_chain = _chain_step(
                        source_chain, stats_source.d1, item_digest
                    )
                    evaluation_chain = _chain_step(
                        evaluation_chain,
                        stats_source.d1,
                        stats_source.original_evaluation_digest,
                        stats_source.evaluation_digest,
                    )
                if legacy_items is not None and legacy_stats is not None:
                    if len(legacy_items) + len(items) <= 25:
                        legacy_items.extend(items)
                        legacy_stats.extend(stats_sources)
                    else:
                        legacy_items = None
                        legacy_stats = None
                page_count += 1
                last_original = rows[-1]
                if corrected:
                    last_corrected = corrected[-1]
                    last_physical = physical[-1]
                _assert_page_binding(scope, event, bound_source, expected_target)
                consume(page)

            source = visit_past_correction_v3_source_pages(
                scope,
                game_id,
                target_d1,
                visit,
                _host=host,
                _progress=lambda: _assert_page_binding(
                    scope, event, bound_source, expected_target
                ),
            )
        if (
            source.internal_generation != generation
            or state.last_d1 != source.watermark
            or type(target) is not SavedLineupPitch
            or type(last_original) is not SavedLineupPitch
            or type(last_corrected) is not CorrectedLineupPitch
            or type(last_physical) is not CorrectedPhysicalPitch
            or state.previous_original is None
            or state.previous_corrected is None
            or state.previous_original.value.next_prefix_ref
            != source.checkpoint.prefix_ref
        ):
            raise PastCorrectionPageUnavailable("P3全頁と元CPが不一致")
        bind_lineup_pitch_change_target(
            payload, target, target_d1, source.watermark, source.checkpoint.prefix_ref
        )
        next_checkpoint = build_corrected_lineup_checkpoint_from_head(
            source.checkpoint,
            last_original,
            last_corrected,
            last_physical,
            source.watermark,
        )
        if legacy_items is not None and legacy_stats is not None:
            digest_format = "p3-full-v1"
            source_set_digest = source_fingerprint(
                {
                    "capsule_id": str(capsule_id),
                    "change_event_id": str(change_event_id),
                    "old_checkpoint_digest": source.checkpoint.content_digest,
                    "new_checkpoint_digest": next_checkpoint.content_digest,
                    "item_digests": [item["digest"] for item in legacy_items],
                }
            )
            evaluation_set_digest = source_fingerprint(
                {
                    "capsule_id": str(capsule_id),
                    "model_sha256": SOURCE_MODEL_HASH,
                    "capsule_source_set_digest": source_set_digest,
                    "sources": [
                        {
                            "d1": item.d1,
                            "event_id": str(item.effective_event_id),
                            "play_row_id": str(item.effective_play_row_id),
                            "original_evaluation_digest": (
                                item.original_evaluation_digest
                            ),
                            "evaluation_digest": item.evaluation_digest,
                        }
                        for item in legacy_stats
                    ],
                }
            )
        else:
            digest_format = "p3-page-chain-v2"
            source_set_digest = hashlib.sha256(
                ":".join(
                    (
                        digest_format,
                        str(capsule_id),
                        str(change_event_id),
                        source.checkpoint.content_digest,
                        next_checkpoint.content_digest,
                        str(source.watermark),
                        source_chain,
                    )
                ).encode("ascii")
            ).hexdigest()
            evaluation_set_digest = hashlib.sha256(
                ":".join(
                    (
                        "p3-stats-chain-v2",
                        str(capsule_id),
                        SOURCE_MODEL_HASH,
                        source_set_digest,
                        evaluation_chain,
                    )
                ).encode("ascii")
            ).hexdigest()
        return P3PagedPreparationProof(
            generation,
            source.watermark,
            source.checkpoint,
            next_checkpoint,
            state,
            page_count,
            seal,
            digest_format,
            source_chain,
            evaluation_chain,
            source_set_digest,
            evaluation_set_digest,
            target,
        )
    except (
        LineupCorrectionUnsupported,
        PastCorrectionSourceUnavailable,
        PastCorrectionPayloadError,
        PastCorrectionCheckpointError,
        PastCorrectionCapsuleError,
        PastCorrectionStatsError,
        ValueError,
        TypeError,
        KeyError,
    ):
        raise PastCorrectionPageUnavailable("P3頁原本と再評価が不成立") from None
