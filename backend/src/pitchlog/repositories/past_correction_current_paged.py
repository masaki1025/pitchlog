"""P3 26件超の同TX有界currentを既一行検証と唯一T5へ逐次通す。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, cast
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.ordinary_prefix_read import _evaluate_lineup_payload
from pitchlog.repositories.past_correction_current import (
    PastCorrectionCurrentUnavailable,
    _object,
    _uuid,
    _verify_p3_current_member,
)
from pitchlog.repositories.past_correction_paged_tokens import (
    _ReadP3CurrentHeaderToken,
    _ReadP3CurrentPageToken,
)
from pitchlog.repositories.play_prefix import (
    LineupPrefixDocument,
    read_lineup_prefix_document,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.stats.facts import evaluate_native_projection
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.past_correction_paged import _chain_step
from pitchlog.sync.past_correction_stats import evaluate_p3_current_item_stats
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows


@dataclass(frozen=True, slots=True)
class VerifiedP3PagedCurrent:
    """全頁検証後の固定headと要求範囲だけを保持する。"""

    checkpoint: LineupPrefixDocument
    original_checkpoint: LineupPrefixDocument
    capsule_id: UUID
    change_event_id: UUID
    d5: UUID
    target_d1: int
    stats_version_id: UUID
    watermark: int
    source_count: int
    selected_after_d1: int
    selected_items: tuple[dict[str, object], ...]
    selected_payloads: tuple[LineupPitchPlayPayload, ...]
    target_item: dict[str, object]
    last_item: dict[str, object]
    last_payload: LineupPitchPlayPayload


def read_verified_p3_paged_current(
    scope: _TenantTransaction,
    game: UUID,
    generation: int,
    *,
    selected_after_d1: int,
    selected_limit: int,
) -> VerifiedP3PagedCurrent | None:
    """有限関数tokenから同scopeに25件ずつ取り込み全頁を照合する。"""
    if (
        type(scope) is not _TenantTransaction
        or type(game) is not UUID
        or type(generation) is not int
        or generation < 1
    ):
        raise PastCorrectionCurrentUnavailable("P3頁reader scopeが不正")
    from pitchlog.repositories.ordinary_prefix_read import _function_one

    header = _function_one(scope, _ReadP3CurrentHeaderToken(game, generation))
    if type(header) is not dict:
        raise PastCorrectionCurrentUnavailable("P3頁headerが欠落")
    kind = header.get("kind")
    if type(kind) is not str:
        raise PastCorrectionCurrentUnavailable("P3頁header種別が不正")
    if kind in {"none", "p3-legacy"}:
        if set(header) != {"kind"}:
            raise PastCorrectionCurrentUnavailable("P3旧版headerが不正")
        return None
    capsule = _object(header.get("capsule"))
    stats = _object(header.get("stats"))
    checkpoint = _object(header.get("checkpoint"))
    head = _object(header.get("head"))
    watermark = capsule.get("watermark")
    source_count = stats.get("source_count")
    if (
        type(watermark) is not int
        or watermark <= 25
        or type(source_count) is not int
        or source_count < watermark
    ):
        raise PastCorrectionCurrentUnavailable("P3頁水位が不正")

    def pages() -> Iterable[object]:
        """cursorは受信値で進めず固定25幅で生成し、内容側が毎頁照合する。"""
        for after in range(0, watermark, 25):
            yield _function_one(
                scope,
                _ReadP3CurrentPageToken(
                    game,
                    generation,
                    _uuid(capsule["id"]),
                    _uuid(stats["id"]),
                    cast(str, checkpoint["content_digest"]),
                    cast(str, head["source_set_digest"]),
                    "capsule",
                    after,
                    min(25, watermark - after),
                ),
            )
        for after in range(watermark, source_count, 25):
            yield _function_one(
                scope,
                _ReadP3CurrentPageToken(
                    game,
                    generation,
                    _uuid(capsule["id"]),
                    _uuid(stats["id"]),
                    cast(str, checkpoint["content_digest"]),
                    cast(str, head["source_set_digest"]),
                    "suffix",
                    after,
                    min(25, source_count - after),
                ),
            )

    return verify_p3_paged_current(
        header,
        pages(),
        tenant=scope._bound_tenant_id,
        game=game,
        generation=generation,
        selected_after_d1=selected_after_d1,
        selected_limit=selected_limit,
    )


def _sha_ascii(*values: str) -> str:
    """保存側と同じ区切り付きASCII SHAを再計算する。"""
    return hashlib.sha256(":".join(values).encode("ascii")).hexdigest()


def verify_p3_paged_current(
    header_packet: object,
    pages: Iterable[object],
    *,
    tenant: UUID,
    game: UUID,
    generation: int,
    selected_after_d1: int,
    selected_limit: int,
) -> VerifiedP3PagedCurrent:
    """25件ごとの原本/唯一計算/T5と全件chainを検査し要求頁だけ保持する。"""
    if (
        type(tenant) is not UUID
        or type(game) is not UUID
        or type(generation) is not int
        or generation < 1
        or type(selected_after_d1) is not int
        or selected_after_d1 < 0
        or type(selected_limit) is not int
        or not 1 <= selected_limit <= 25
    ):
        raise PastCorrectionCurrentUnavailable("P3頁読取scopeが不正")
    header = _object(header_packet)
    if set(header) != {
        "kind",
        "head",
        "capsule",
        "checkpoint",
        "stats",
        "change_event",
        "change_ledger",
        "progress",
        "item_count",
        "source_count",
    } or header["kind"] != "p3-paged-header":
        raise PastCorrectionCurrentUnavailable("P3頁header形が不正")
    head = _object(header["head"])
    capsule = _object(header["capsule"])
    checkpoint_row = _object(header["checkpoint"])
    stats = _object(header["stats"])
    change = _object(header["change_event"])
    ledger = _object(header["change_ledger"])
    progress = _object(header["progress"])
    try:
        current = read_lineup_prefix_document(
            _canonical_json(checkpoint_row["content"])
        )
        at_change = read_lineup_prefix_document(
            _canonical_json(capsule["next_checkpoint_content"])
        )
        previous = read_lineup_prefix_document(
            _canonical_json(capsule["prior_checkpoint_content"])
        )
        capsule_id = _uuid(capsule["id"])
        change_id = _uuid(change["id"])
        d5 = _uuid(capsule["d5"])
        stats_id = _uuid(stats["id"])
        watermark = capsule["watermark"]
        upper = stats["source_count"]
        target_d1 = capsule["target_d1"]
        if (
            type(watermark) is not int
            or watermark <= 25
            or type(upper) is not int
            or upper < watermark
            or type(target_d1) is not int
            or not 1 <= target_d1 <= watermark
            or selected_after_d1 >= upper
            or capsule["digest_format"] != "p3-page-chain-v2"
            or capsule["tenant_id"] != str(tenant)
            or capsule["game_id"] != str(game)
            or capsule["internal_generation"] != generation
            or capsule["change_event_id"] != str(change_id)
            or capsule["expected_version"] != 1
            or head["tenant_id"] != str(tenant)
            or head["game_id"] != str(game)
            or head["internal_generation"] != generation
            or head["capsule_id"] != str(capsule_id)
            or head["source_set_digest"] != capsule["source_set_digest"]
            or head["stats_version_id"] != str(stats_id)
            or capsule["stats_version_id"] != str(stats_id)
            or stats["tenant_id"] != str(tenant)
            or stats["game_id"] != str(game)
            or stats["model_sha256"] != SOURCE_MODEL_HASH
            or stats["is_current"] is not True
            or stats["invalidated_at"] is not None
            or header["item_count"] != watermark
            or header["source_count"] != upper
            or set(progress)
            != {
                "digest_format",
                "state",
                "item_count",
                "page_count",
                "source_page_seal",
                "evaluation_page_seal",
            }
            or progress["digest_format"] != "p3-page-chain-v2"
            or progress["state"] != "finalized"
            or progress["item_count"] != watermark
            or type(progress["page_count"]) is not int
            or progress["page_count"] < (watermark + 24) // 25
            or progress["page_count"] > watermark
            or previous.id != capsule["prior_checkpoint_id"]
            or previous.revision != str(capsule["prior_checkpoint_revision"])
            or previous.content_digest != capsule["prior_checkpoint_digest"]
            or at_change.id != capsule["next_checkpoint_id"]
            or at_change.revision != str(capsule["next_checkpoint_revision"])
            or at_change.content_digest != capsule["next_checkpoint_digest"]
            or at_change.confirmed_watermark != str(watermark)
            or current.id != at_change.id
            or current.history_version != at_change.history_version
            or current.storage_anchor != at_change.storage_anchor
            or current.confirmed_watermark != str(upper)
            or current.applied_watermark != str(upper)
            or int(current.revision)
            != int(at_change.revision) + upper - watermark
            or current.id != checkpoint_row["id"]
            or current.revision != str(checkpoint_row["revision"])
            or current.content_digest != checkpoint_row["content_digest"]
            or change["tenant_id"] != str(tenant)
            or change["game_id"] != str(game)
            or change["d5"] != str(d5)
            or change["event_kind"] != "play_change"
            or change["ledger_kind"] != "accepted"
            or change["is_tombstone"] is not False
            or change["replaced_at"] is not None
            or change["retired_at"] is not None
            or change["target_generation"] != generation
            or change["target_d1"] != target_d1
            or change["expected_version"] != 1
            or ledger["tenant_id"] != str(tenant)
            or ledger["d5"] != str(d5)
            or ledger["kind"] != "accepted"
            or ledger["retired_at"] is not None
        ):
            raise PastCorrectionCurrentUnavailable("P3頁header原本が不一致")
        after = 0
        source_chain = "0" * 64
        evaluation_chain = "0" * 64
        prior_payload: LineupPitchPlayPayload | None = None
        selected_items: list[dict[str, object]] = []
        selected_payloads: list[LineupPitchPlayPayload] = []
        target_item: dict[str, object] | None = None
        last_item: dict[str, object] | None = None
        iterator = iter(pages)
        while after < watermark:
            page = _object(next(iterator))
            items_raw = page["items"]
            page_last = page.get("last_d1")
            if (
                set(page)
                != {
                    "kind",
                    "page_kind",
                    "tenant_id",
                    "game_id",
                    "internal_generation",
                    "capsule_id",
                    "stats_version_id",
                    "checkpoint_digest",
                    "head_digest",
                    "after_d1",
                    "last_d1",
                    "upper_d1",
                    "items",
                    "next_after_d1",
                }
                or page["kind"] != "p3-paged-page"
                or page["page_kind"] != "capsule"
                or page["tenant_id"] != str(tenant)
                or page["game_id"] != str(game)
                or page["internal_generation"] != generation
                or page["capsule_id"] != str(capsule_id)
                or page["stats_version_id"] != str(stats_id)
                or page["checkpoint_digest"] != current.content_digest
                or page["head_digest"] != head["source_set_digest"]
                or page["after_d1"] != after
                or page["upper_d1"] != watermark
                or type(items_raw) is not list
                or not 1 <= len(items_raw) <= 25
                or type(page_last) is not int
                or page_last != after + len(items_raw)
                or page["next_after_d1"]
                != (page_last if page_last < watermark else None)
            ):
                raise PastCorrectionCurrentUnavailable("P3頁境界が不一致")
            for raw in items_raw:
                d1 = after + 1
                member = _object(raw)
                if set(member) != {
                    "item",
                    "original_event",
                    "original_ledger",
                    "original_history",
                    "original_play_row",
                    "original_play_runners",
                    "effective_play_row",
                    "effective_play_runners",
                    "stats_source",
                }:
                    raise PastCorrectionCurrentUnavailable("P3頁item形が不正")
                source = _object(member["stats_source"])
                original_member = {
                    key: value for key, value in member.items() if key != "stats_source"
                }
                item, payload, fingerprint, d2 = _verify_p3_current_member(
                    original_member,
                    d1=d1,
                    tenant=tenant,
                    game=game,
                    generation=generation,
                    capsule_id=capsule_id,
                    target_d1=target_d1,
                    change_id=change_id,
                    change_event=change,
                    change_ledger=ledger,
                    prior_payload=prior_payload,
                )
                evaluated = evaluate_p3_current_item_stats(item, d1)
                if (
                    source["tenant_id"] != str(tenant)
                    or source["game_id"] != str(game)
                    or source["fact_version_id"] != str(stats_id)
                    or source["recording_generation"] != generation
                    or source["d1"] != d1
                    or source["d2"] != d2
                    or source["source_event_id"] != item["effective_event_id"]
                    or source["source_fingerprint"] != fingerprint
                    or source["play_row_id"] != item["effective_play_row_id"]
                    or source["play_row_version"]
                    != _object(item["play_row"])["version"]
                    or source["slot_version"] != (2 if d1 == target_d1 else 1)
                    or source["artifact_sha256"]
                    != payload.calculation.artifact_sha256
                    or source["metric_states"] != evaluated.evaluation
                    or source["rule_sha256"]
                    != evaluated.evaluation["native_rule_sha256"]
                ):
                    raise PastCorrectionCurrentUnavailable("P3頁T5原本が不一致")
                source_chain = _chain_step(source_chain, d1, cast(str, item["digest"]))
                evaluation_chain = _chain_step(
                    evaluation_chain,
                    d1,
                    evaluated.original_evaluation_digest,
                    evaluated.evaluation_digest,
                )
                if selected_after_d1 < d1 <= selected_after_d1 + selected_limit:
                    selected_items.append(item)
                    selected_payloads.append(payload)
                if d1 == target_d1:
                    target_item = item
                last_item = item
                prior_payload = payload
                after = d1
        if (
            type(last_item) is not dict
            or type(prior_payload) is not LineupPitchPlayPayload
        ):
            raise PastCorrectionCurrentUnavailable("P3頁末尾が欠落")
        at_change_value = prior_payload.calculation.response.value
        if (
            at_change_value.next_prefix_ref != at_change.prefix_ref
            or at_change_value.t1.after != at_change.after
            or at_change_value.t2 != at_change.t2
            or at_change_value.runners != at_change.runners
            or at_change_value.participants != at_change.participants
            or at_change_value.lineup != at_change.lineup
            or at_change.projection_snapshot is None
            or at_change.projection_snapshot.play_row != last_item["play_row"]
            or list(at_change.projection_snapshot.play_runners)
            != last_item["play_runners"]
        ):
            raise PastCorrectionCurrentUnavailable("P3頁訂正時CPが不一致")
        while after < upper:
            page = _object(next(iterator))
            items_raw = page["items"]
            page_last = page.get("last_d1")
            if (
                set(page)
                != {
                    "kind",
                    "page_kind",
                    "tenant_id",
                    "game_id",
                    "internal_generation",
                    "capsule_id",
                    "stats_version_id",
                    "checkpoint_digest",
                    "head_digest",
                    "after_d1",
                    "last_d1",
                    "upper_d1",
                    "items",
                    "next_after_d1",
                }
                or page["kind"] != "p3-paged-page"
                or page["page_kind"] != "suffix"
                or page["tenant_id"] != str(tenant)
                or page["game_id"] != str(game)
                or page["internal_generation"] != generation
                or page["capsule_id"] != str(capsule_id)
                or page["stats_version_id"] != str(stats_id)
                or page["checkpoint_digest"] != current.content_digest
                or page["head_digest"] != head["source_set_digest"]
                or page["after_d1"] != after
                or page["upper_d1"] != upper
                or type(items_raw) is not list
                or not 1 <= len(items_raw) <= 25
                or type(page_last) is not int
                or page_last != after + len(items_raw)
                or page["next_after_d1"]
                != (page_last if page_last < upper else None)
            ):
                raise PastCorrectionCurrentUnavailable("P3後続頁境界が不一致")
            for raw in items_raw:
                d1 = after + 1
                member = _object(raw)
                if set(member) != {
                    "event",
                    "ledger",
                    "history",
                    "play_row",
                    "play_runners",
                    "stats_source",
                }:
                    raise PastCorrectionCurrentUnavailable("P3後続頁形が不正")
                event = _object(member["event"])
                event_ledger = _object(member["ledger"])
                history = _object(member["history"])
                play = _object(member["play_row"])
                source = _object(member["stats_source"])
                runners = member["play_runners"]
                payload = _evaluate_lineup_payload(event["payload"])
                value = payload.calculation.response.value
                request = payload.calculation.request
                prior = prior_payload.calculation.response.value
                if (
                    event["tenant_id"] != str(tenant)
                    or event["game_id"] != str(game)
                    or event["generation"] != generation
                    or event["d1"] != d1
                    or event["event_kind"] != "play_input"
                    or event["ledger_kind"] != "accepted"
                    or event["is_tombstone"] is not False
                    or event["replaced_at"] is not None
                    or event["retired_at"] is not None
                    or event["import_batch_id"] is not None
                    or event["migration_unverified"] is not False
                    or event_ledger["tenant_id"] != str(tenant)
                    or event_ledger["d5"] != event["d5"]
                    or event_ledger["kind"] != "accepted"
                    or event_ledger["retired_at"] is not None
                    or event_ledger["import_batch_id"] is not None
                    or history["tenant_id"] != str(tenant)
                    or history["game_id"] != str(game)
                    or history["internal_generation"] != generation
                    or history["history_version"] != int(current.history_version)
                    or history["source_event_id"] != event["id"]
                    or history["d1"] != d1
                    or history["d2"] != event["d2"]
                    or history["entry"]
                    != value.new_history_entry.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    )
                    or event["state_diff"]
                    != value.new_history_entry.difference.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    )
                    or play["tenant_id"] != str(tenant)
                    or play["game_id"] != str(game)
                    or play["source_event_id"] != event["id"]
                    or play["hidden_at"] is not None
                    or play["import_batch_id"] is not None
                    or play["migration_unverified"] is not False
                    or request.play_identity.event_id != event["id"]
                    or request.play_identity.d5 != event["d5"]
                    or request.play_identity.play_id != play["id"]
                    or request.source.position.d1 != str(d1)
                    or request.source.position.d2 != str(event["d2"])
                    or request.prefix_ref != prior.next_prefix_ref
                    or request.t1.before != prior.t1.after
                    or request.source.runners != prior.runners
                    or request.source.participants != prior.participants
                    or request.source.lineup != prior.lineup
                    or request.rules != at_change.rules
                ):
                    raise PastCorrectionCurrentUnavailable("P3後続頁原本が不一致")
                expected_play = pitch_physical_row(
                    payload.observations,
                    payload.participants,
                    request.t1.result_id,
                    tenant_id=tenant,
                    game_id=game,
                    source_event_id=_uuid(event["id"]),
                    row_id=_uuid(play["id"]),
                    play_number=play["play_number"],
                )
                expected_runners = runner_physical_rows(
                    request.source.runners,
                    t1=value.t1,
                    t1_input=request.t1,
                    tenant_id=tenant,
                    play_id=_uuid(play["id"]),
                )
                native = evaluate_native_projection(
                    _object(event["payload"]), source_event_id=_uuid(event["id"])
                )
                rule_sha = source_fingerprint(
                    _object(request.rules.model_dump(mode="json", by_alias=True))
                )
                native["native_rule_sha256"] = rule_sha
                if (
                    expected_play != play
                    or expected_runners != runners
                    or request.source.rules_digest != rule_sha
                    or source["tenant_id"] != str(tenant)
                    or source["game_id"] != str(game)
                    or source["fact_version_id"] != str(stats_id)
                    or source["recording_generation"] != generation
                    or source["d1"] != d1
                    or source["d2"] != event["d2"]
                    or source["source_event_id"] != event["id"]
                    or source["source_fingerprint"]
                    != event_ledger["source_fingerprint"]
                    or source["play_row_id"] != play["id"]
                    or source["play_row_version"] != play["version"]
                    or source["slot_version"] != 1
                    or source["artifact_sha256"]
                    != payload.calculation.artifact_sha256
                    or source["metric_states"] != native
                    or source["rule_sha256"] != rule_sha
                ):
                    raise PastCorrectionCurrentUnavailable("P3後続頁物理/T5が不一致")
                item = {
                    "play_row": play,
                    "play_runners": runners,
                    "history_entry": history["entry"],
                }
                if selected_after_d1 < d1 <= selected_after_d1 + selected_limit:
                    selected_items.append(item)
                    selected_payloads.append(payload)
                last_item = item
                prior_payload = payload
                after = d1
        try:
            next(iterator)
        except StopIteration:
            pass
        else:
            raise PastCorrectionCurrentUnavailable("P3頁が余分")
        if (
            type(last_item) is not dict
            or type(target_item) is not dict
            or type(prior_payload) is not LineupPitchPlayPayload
            or len(selected_items)
            != min(selected_limit, upper - selected_after_d1)
            or progress["source_page_seal"] != source_chain
            or progress["evaluation_page_seal"] != evaluation_chain
        ):
            raise PastCorrectionCurrentUnavailable("P3頁全件sealが不一致")
        last = prior_payload.calculation.response.value
        if (
            last.next_prefix_ref != current.prefix_ref
            or last.t1.after != current.after
            or last.t2 != current.t2
            or last.runners != current.runners
            or last.participants != current.participants
            or last.lineup != current.lineup
            or current.projection_snapshot is None
            or current.projection_snapshot.play_row != last_item["play_row"]
            or list(current.projection_snapshot.play_runners)
            != last_item["play_runners"]
        ):
            raise PastCorrectionCurrentUnavailable("P3頁末尾CPが不一致")
        source_digest = _sha_ascii(
            "p3-page-chain-v2",
            str(capsule_id),
            str(change_id),
            previous.content_digest,
            at_change.content_digest,
            str(watermark),
            source_chain,
        )
        evaluation_digest = _sha_ascii(
            "p3-stats-chain-v2",
            str(capsule_id),
            SOURCE_MODEL_HASH,
            source_digest,
            evaluation_chain,
        )
        if (
            source_digest != capsule["source_set_digest"]
            or evaluation_digest != capsule["stats_evaluation_set_digest"]
        ):
            raise PastCorrectionCurrentUnavailable("P3頁集合digestが不一致")
        return VerifiedP3PagedCurrent(
            current,
            previous,
            capsule_id,
            change_id,
            d5,
            target_d1,
            stats_id,
            watermark,
            upper,
            selected_after_d1,
            tuple(selected_items),
            tuple(selected_payloads),
            target_item,
            last_item,
            prior_payload,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        IndexError,
        StopIteration,
    ) as error:
        raise PastCorrectionCurrentUnavailable("P3頁全値照合が不成立") from error
