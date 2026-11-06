"""P3 current capsuleの限定読取を元原本と唯一核へ再照合する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.ordinary_prefix_read import _evaluate_lineup_payload
from pitchlog.repositories.play_prefix import (
    LineupPrefixDocument,
    read_lineup_prefix_document,
)
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.past_correction_capsule import P3CurrentCapsule
from pitchlog.sync.past_correction_stats import evaluate_p3_capsule_stats
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows


class PastCorrectionCurrentUnavailable(RuntimeError):
    """有効版と元原本の一対一照合が不成立。"""


@dataclass(frozen=True, slots=True)
class VerifiedP3Current:
    """読取同TXのみに有効な検証済みcurrent投影。"""

    checkpoint: LineupPrefixDocument
    original_checkpoint: LineupPrefixDocument
    capsule_id: UUID
    items: tuple[dict[str, object], ...]
    payloads: tuple[LineupPitchPlayPayload, ...]


_ITEM_COLUMNS = (
    "d1",
    "d2",
    "state",
    "original_event_id",
    "effective_event_id",
    "original_play_row_id",
    "effective_play_row_id",
    "original_payload",
    "original_history_entry",
    "original_play_row",
    "original_play_runners",
    "payload",
    "history_entry",
    "play_row",
    "play_runners",
)


def _object(value: object) -> dict[str, object]:
    """自由な辞書補修を避けてJSON objectを要求する。"""
    if type(value) is not dict:
        raise PastCorrectionCurrentUnavailable("P3 current読取形が不正")
    return cast(dict[str, object], value)


def _uuid(value: object) -> UUID:
    """DB JSON内の正規UUID文字列だけを採る。"""
    if type(value) is not str:
        raise PastCorrectionCurrentUnavailable("P3 current UUIDが不正")
    parsed = UUID(value)
    if str(parsed) != value:
        raise PastCorrectionCurrentUnavailable("P3 current UUIDが非正規")
    return parsed


def verify_p3_current_packet(
    packet: object, *, tenant: UUID, game: UUID, generation: int
) -> VerifiedP3Current:
    """DB現head/元全原本/有効数学/物理/T5集合を同一値へ閉じる。"""
    if (
        type(tenant) is not UUID
        or type(game) is not UUID
        or type(generation) is not int
        or generation <= 0
    ):
        raise PastCorrectionCurrentUnavailable("P3 current scopeが不正")
    raw = _object(packet)
    if (
        set(raw)
        != {
            "kind",
            "head",
            "capsule",
            "checkpoint",
            "stats",
            "change_event",
            "change_ledger",
            "members",
            "suffix",
            "stats_sources",
        }
        or raw["kind"] != "p3-current"
    ):
        raise PastCorrectionCurrentUnavailable("P3 current packetが不正")
    head = _object(raw["head"])
    capsule = _object(raw["capsule"])
    checkpoint_row = _object(raw["checkpoint"])
    stats_row = _object(raw["stats"])
    change_event = _object(raw["change_event"])
    change_ledger = _object(raw["change_ledger"])
    members = raw["members"]
    suffix_raw = raw["suffix"]
    sources_raw = raw["stats_sources"]
    if type(members) is not list or not 1 <= len(members) <= 25:
        raise PastCorrectionCurrentUnavailable("P3 current件数が不正")
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
        change_id = _uuid(change_event["id"])
        target_d1 = capsule["target_d1"]
        if (
            type(target_d1) is not int
            or target_d1 not in range(1, len(members) + 1)
            or head["tenant_id"] != str(tenant)
            or head["game_id"] != str(game)
            or head["internal_generation"] != generation
            or head["capsule_id"] != str(capsule_id)
            or head["source_set_digest"] != capsule["source_set_digest"]
            or head["stats_version_id"] != capsule["stats_version_id"]
            or stats_row["id"] != head["stats_version_id"]
            or stats_row["tenant_id"] != str(tenant)
            or stats_row["game_id"] != str(game)
            or stats_row["is_current"] is not True
            or stats_row["invalidated_at"] is not None
            or stats_row["source_count"] != int(current.confirmed_watermark)
            or capsule["tenant_id"] != str(tenant)
            or capsule["game_id"] != str(game)
            or capsule["internal_generation"] != generation
            or capsule["change_event_id"] != str(change_id)
            or capsule["watermark"] != len(members)
            or capsule["expected_version"] != 1
            or previous.id != capsule["prior_checkpoint_id"]
            or previous.revision != str(capsule["prior_checkpoint_revision"])
            or previous.content_digest != capsule["prior_checkpoint_digest"]
            or current.id != previous.id
            or current.history_version != previous.history_version
            or current.storage_anchor != previous.storage_anchor
            or current.id != checkpoint_row["id"]
            or current.revision != str(checkpoint_row["revision"])
            or current.content_digest != checkpoint_row["content_digest"]
            or at_change.id != capsule["next_checkpoint_id"]
            or at_change.revision != str(capsule["next_checkpoint_revision"])
            or at_change.content_digest != capsule["next_checkpoint_digest"]
            or at_change.confirmed_watermark != str(len(members))
            or current.id != at_change.id
            or current.history_version != at_change.history_version
            or current.storage_anchor != at_change.storage_anchor
            or int(current.confirmed_watermark) not in {len(members), len(members) + 1}
            or int(current.revision)
            != int(at_change.revision) + int(current.confirmed_watermark) - len(members)
            or change_event["tenant_id"] != str(tenant)
            or change_event["game_id"] != str(game)
            or change_event["d5"] != capsule["d5"]
            or change_event["event_kind"] != "play_change"
            or change_event["ledger_kind"] != "accepted"
            or change_event["is_tombstone"] is not False
            or change_event["replaced_at"] is not None
            or change_event["retired_at"] is not None
            or change_event["target_generation"] != generation
            or change_event["target_d1"] != target_d1
            or change_event["expected_version"] != 1
            or change_ledger["tenant_id"] != str(tenant)
            or change_ledger["d5"] != capsule["d5"]
            or change_ledger["kind"] != "accepted"
            or change_ledger["retired_at"] is not None
        ):
            raise PastCorrectionCurrentUnavailable("P3 current headが不一致")
        items: list[dict[str, object]] = []
        payloads: list[LineupPitchPlayPayload] = []
        ledger_fingerprints: list[object] = []
        source_d2: list[object] = []
        prior_payload: LineupPitchPlayPayload | None = None
        for d1, raw_member in enumerate(members, start=1):
            member = _object(raw_member)
            if set(member) != {
                "item",
                "original_event",
                "original_ledger",
                "original_history",
                "original_play_row",
                "original_play_runners",
                "effective_play_row",
                "effective_play_runners",
            }:
                raise PastCorrectionCurrentUnavailable("P3 item読取形が不正")
            row = _object(member["item"])
            original_event = _object(member["original_event"])
            original_ledger = _object(member["original_ledger"])
            history = _object(member["original_history"])
            old_play = _object(member["original_play_row"])
            effective_play = _object(member["effective_play_row"])
            original_runners = member["original_play_runners"]
            effective_runners = member["effective_play_runners"]
            item = {name: row[name] for name in _ITEM_COLUMNS}
            item["digest"] = row["item_digest"]
            old_payload = _evaluate_lineup_payload(item["original_payload"])
            effective_payload = _evaluate_lineup_payload(item["payload"])
            old_entry = old_payload.calculation.response.value.new_history_entry
            effective_entry = (
                effective_payload.calculation.response.value.new_history_entry
            )
            original_id = row["original_event_id"]
            effective_id = row["effective_event_id"]
            if (
                row["tenant_id"] != str(tenant)
                or row["game_id"] != str(game)
                or row["internal_generation"] != generation
                or row["capsule_id"] != str(capsule_id)
                or row["d1"] != d1
                or row["item_digest"]
                != source_fingerprint(
                    {key: value for key, value in item.items() if key != "digest"}
                )
                or original_event["id"] != original_id
                or original_event["tenant_id"] != str(tenant)
                or original_event["game_id"] != str(game)
                or original_event["generation"] != generation
                or original_event["d1"] != d1
                or original_event["d2"] != row["d2"]
                or original_event["event_kind"] != "play_input"
                or original_event["ledger_kind"] != "accepted"
                or original_event["is_tombstone"] is not False
                or original_event["replaced_at"] is not None
                or original_event["retired_at"] is not None
                or original_event["payload"] != item["original_payload"]
                or original_ledger["tenant_id"] != str(tenant)
                or original_ledger["d5"] != original_event["d5"]
                or original_ledger["kind"] != "accepted"
                or original_ledger["retired_at"] is not None
                or history["entry"] != item["original_history_entry"]
                or history["source_event_id"] != original_id
                or history["d1"] != d1
                or history["d2"] != row["d2"]
                or old_play != item["original_play_row"]
                or old_play["source_event_id"] != original_id
                or original_runners != item["original_play_runners"]
                or effective_play != item["play_row"]
                or effective_play["source_event_id"] != effective_id
                or effective_runners != item["play_runners"]
                or old_entry.model_dump(mode="json", by_alias=True, exclude_unset=True)
                != item["original_history_entry"]
                or effective_entry.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                )
                != item["history_entry"]
                or effective_payload.calculation.request.play_identity.event_id
                != original_id
                or effective_payload.calculation.request.play_identity.d5
                != original_event["d5"]
                or effective_payload.calculation.request.play_identity.play_id
                != row["original_play_row_id"]
            ):
                raise PastCorrectionCurrentUnavailable("P3 item原本が不一致")
            if d1 == target_d1:
                if (
                    row["state"] != "corrected"
                    or effective_id != str(change_id)
                    or row["effective_play_row_id"] == row["original_play_row_id"]
                    or _object(change_event["payload"]).get("targetEventId")
                    != original_id
                ):
                    raise PastCorrectionCurrentUnavailable("P3対象が不一致")
            elif (
                effective_id != original_id
                or row["effective_play_row_id"] != row["original_play_row_id"]
                or effective_play != old_play
                or effective_runners != original_runners
            ):
                raise PastCorrectionCurrentUnavailable("P3後続原本が不一致")
            if prior_payload is not None:
                prior_value = prior_payload.calculation.response.value
                request = effective_payload.calculation.request
                if (
                    request.prefix_ref != prior_value.next_prefix_ref
                    or request.t1.before != prior_value.t1.after
                    or request.source.runners != prior_value.runners
                    or request.source.participants != prior_value.participants
                    or request.source.lineup != prior_value.lineup
                ):
                    raise PastCorrectionCurrentUnavailable("P3有効連鎖が不一致")
            expected_play = pitch_physical_row(
                effective_payload.observations,
                effective_payload.participants,
                effective_payload.calculation.request.t1.result_id,
                tenant_id=tenant,
                game_id=game,
                source_event_id=_uuid(effective_id),
                row_id=_uuid(row["effective_play_row_id"]),
                play_number=effective_play["play_number"],
            )
            expected_runners = runner_physical_rows(
                effective_payload.calculation.request.source.runners,
                t1=effective_payload.calculation.response.value.t1,
                t1_input=effective_payload.calculation.request.t1,
                tenant_id=tenant,
                play_id=_uuid(row["effective_play_row_id"]),
            )
            if expected_play != effective_play or expected_runners != effective_runners:
                raise PastCorrectionCurrentUnavailable("P3有効物理行が不一致")
            items.append(item)
            payloads.append(effective_payload)
            ledger_fingerprints.append(
                change_ledger["source_fingerprint"]
                if d1 == target_d1
                else original_ledger["source_fingerprint"]
            )
            source_d2.append(row["d2"])
            prior_payload = effective_payload
        last = payloads[-1].calculation.response.value
        if (
            last.next_prefix_ref != at_change.prefix_ref
            or last.t1.after != at_change.after
            or last.t2 != at_change.t2
            or last.runners != at_change.runners
            or last.participants != at_change.participants
            or last.lineup != at_change.lineup
            or at_change.projection_snapshot is None
            or at_change.projection_snapshot.play_row != items[-1]["play_row"]
            or list(at_change.projection_snapshot.play_runners)
            != items[-1]["play_runners"]
        ):
            raise PastCorrectionCurrentUnavailable("P3 current CPが不一致")
        source_digest = source_fingerprint(
            {
                "capsule_id": str(capsule_id),
                "change_event_id": str(change_id),
                "old_checkpoint_digest": previous.content_digest,
                "new_checkpoint_digest": at_change.content_digest,
                "item_digests": [item["digest"] for item in items],
            }
        )
        if source_digest != capsule["source_set_digest"]:
            raise PastCorrectionCurrentUnavailable("P3 source集合が不一致")
        candidate = P3CurrentCapsule(
            capsule_id,
            change_id,
            generation,
            target_d1,
            _uuid(previous.id),
            int(previous.revision),
            previous.content_digest,
            previous,
            at_change,
            tuple(items),
            source_digest,
        )
        evaluated = evaluate_p3_capsule_stats(candidate)
        if (
            evaluated.evaluation_set_digest != capsule["stats_evaluation_set_digest"]
            or evaluated.model_sha256 != stats_row["model_sha256"]
        ):
            raise PastCorrectionCurrentUnavailable("P3 T5評価集合が不一致")
        source_evaluations = [source.evaluation for source in evaluated.sources]
        if current.confirmed_watermark == at_change.confirmed_watermark:
            if suffix_raw is not None or current != at_change:
                raise PastCorrectionCurrentUnavailable("P3現headが不一致")
        else:
            suffix = _object(suffix_raw)
            if set(suffix) != {
                "event", "ledger", "history", "play_row", "play_runners"
            }:
                raise PastCorrectionCurrentUnavailable("P3後続読取形が不正")
            event = _object(suffix["event"])
            ledger = _object(suffix["ledger"])
            history = _object(suffix["history"])
            play = _object(suffix["play_row"])
            runners = suffix["play_runners"]
            payload = _evaluate_lineup_payload(event["payload"])
            value = payload.calculation.response.value
            request = payload.calculation.request
            d1 = len(members) + 1
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
                or ledger["tenant_id"] != str(tenant)
                or ledger["d5"] != event["d5"]
                or ledger["kind"] != "accepted"
                or ledger["retired_at"] is not None
                or ledger["import_batch_id"] is not None
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
                or request.prefix_ref != at_change.prefix_ref
                or request.t1.before != at_change.after
                or request.source.runners != at_change.runners
                or request.source.participants != at_change.participants
                or request.source.lineup != at_change.lineup
                or request.rules != at_change.rules
                or value.next_prefix_ref != current.prefix_ref
                or value.t1.after != current.after
                or value.t2 != current.t2
                or value.runners != current.runners
                or value.participants != current.participants
                or value.lineup != current.lineup
                or current.projection_snapshot is None
                or current.projection_snapshot.play_row != play
                or list(current.projection_snapshot.play_runners) != runners
            ):
                raise PastCorrectionCurrentUnavailable("P3後続原本が不一致")
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
            if expected_play != play or expected_runners != runners:
                raise PastCorrectionCurrentUnavailable("P3後続物理行が不一致")
            from pitchlog.stats.facts import evaluate_native_projection

            native = evaluate_native_projection(
                _object(event["payload"]), source_event_id=_uuid(event["id"])
            )
            rule_sha = source_fingerprint(
                _object(request.rules.model_dump(mode="json", by_alias=True))
            )
            if request.source.rules_digest != rule_sha:
                raise PastCorrectionCurrentUnavailable("P3後続規則が不一致")
            native["native_rule_sha256"] = rule_sha
            items.append(
                {
                    "play_row": play,
                    "play_runners": runners,
                    "history_entry": history["entry"],
                }
            )
            payloads.append(payload)
            source_evaluations.append(native)
            ledger_fingerprints.append(ledger["source_fingerprint"])
            source_d2.append(event["d2"])
        if type(sources_raw) is not list or len(sources_raw) != len(items):
            raise PastCorrectionCurrentUnavailable("P3現T5件数が不一致")
        for d1, (raw_source, item, evaluation) in enumerate(
            zip(sources_raw, items, source_evaluations, strict=True), start=1
        ):
            source = _object(raw_source)
            play = _object(item["play_row"])
            effective_id = (
                item["effective_event_id"] if d1 <= len(members)
                else play["source_event_id"]
            )
            if (
                source["tenant_id"] != str(tenant)
                or source["game_id"] != str(game)
                or source["fact_version_id"] != stats_row["id"]
                or source["recording_generation"] != generation
                or source["d1"] != d1
                or source["d2"] != source_d2[d1 - 1]
                or source["source_event_id"] != effective_id
                or source["source_fingerprint"] != ledger_fingerprints[d1 - 1]
                or source["play_row_id"] != play["id"]
                or source["play_row_version"] != play["version"]
                or source["slot_version"] != (2 if d1 == target_d1 else 1)
                or source["artifact_sha256"]
                != payloads[d1 - 1].calculation.artifact_sha256
                or source["metric_states"] != evaluation
                or source["rule_sha256"] != evaluation["native_rule_sha256"]
            ):
                raise PastCorrectionCurrentUnavailable("P3現T5原本が不一致")
        return VerifiedP3Current(
            current, previous, capsule_id, tuple(items), tuple(payloads)
        )
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise PastCorrectionCurrentUnavailable("P3 current全値照合が不成立") from error
