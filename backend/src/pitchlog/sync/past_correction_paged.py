"""P3通常v3原本を25件ずつ唯一核へ通す同TXの純準備。"""

from __future__ import annotations

import hashlib
import json
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
from pitchlog.sync.change_path import _bound_target
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.model import SyncEvent
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
    target: SavedLineupPitch


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
    return rolling


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
        game_id, generation, target_d1 = _bound_target(
            scope, event, bound_source
        )[:3]
        if game_id != UUID(event.game_id):
            raise PastCorrectionPageUnavailable("P3頁対象試合が不一致")
        payload = read_lineup_pitch_change_payload(
            json.dumps(_json_value(event.v7), ensure_ascii=False, allow_nan=False)
        )
        state = CorrectionPageState()
        page_count = 0
        seal = "0" * 64
        target: SavedLineupPitch | None = None
        last_original: SavedLineupPitch | None = None
        last_corrected: CorrectedLineupPitch | None = None
        last_physical: CorrectedPhysicalPitch | None = None

        with open_domain_host() as host:

            def visit(rows: tuple[SavedLineupPitch, ...]) -> None:
                nonlocal state, page_count, seal, target
                nonlocal last_original, last_corrected, last_physical
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
                page = PreparedP3Page(rows, corrected, payloads, physical)
                seal = _page_seal(seal, page)
                page_count += 1
                last_original = rows[-1]
                if corrected:
                    last_corrected = corrected[-1]
                    last_physical = physical[-1]
                consume(page)

            source = visit_past_correction_v3_source_pages(
                scope, game_id, target_d1, visit
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
        return P3PagedPreparationProof(
            generation,
            source.watermark,
            source.checkpoint,
            next_checkpoint,
            state,
            page_count,
            seal,
            target,
        )
    except (
        LineupCorrectionUnsupported,
        PastCorrectionSourceUnavailable,
        PastCorrectionPayloadError,
        PastCorrectionCheckpointError,
        ValueError,
        TypeError,
        KeyError,
    ):
        raise PastCorrectionPageUnavailable("P3頁原本と再評価が不成立") from None
