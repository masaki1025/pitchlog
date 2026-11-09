"""P3 current capsuleの限定読取を元原本と唯一核へ再照合する。"""

from __future__ import annotations

import threading
from collections import OrderedDict
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
    """読取同TXのみに有効な検証済みcurrent又はLC前anchor。"""

    checkpoint: LineupPrefixDocument
    original_checkpoint: LineupPrefixDocument
    capsule_id: UUID
    change_event_id: UUID
    d5: UUID
    target_d1: int
    stats_version_id: UUID
    items: tuple[dict[str, object], ...]
    payloads: tuple[LineupPitchPlayPayload, ...]
    historical_anchor: bool
    first_control_preparation: dict[str, object] | None


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


def _verify_p3_current_member(
    raw_member: object,
    *,
    d1: int,
    tenant: UUID,
    game: UUID,
    generation: int,
    capsule_id: UUID,
    target_d1: int,
    change_id: UUID,
    change_event: dict[str, object],
    change_ledger: dict[str, object],
    prior_payload: LineupPitchPlayPayload | None,
) -> tuple[dict[str, object], LineupPitchPlayPayload, object, object]:
    """旧一括と新有界頁が共有する1行の原本・唯一計算・物理検証。"""
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
    return (
        item,
        effective_payload,
        change_ledger["source_fingerprint"]
        if d1 == target_d1
        else original_ledger["source_fingerprint"],
        row["d2"],
    )


_P3_PACKET_CACHE_LIMIT = 8
_P3_PACKET_CACHE: OrderedDict[str, VerifiedP3Current] = OrderedDict()
_P3_PACKET_CACHE_LOCK = threading.Lock()
# 診断だけが読む件数。cacheの意味や保存資格には使わない。
_P3_PACKET_CACHE_STATS: dict[str, int] = {
    "hit": 0,
    "miss": 0,
    "key_error": 0,
}


def _cache_json(value: object) -> object:
    """Cache key専用にstr subclassのkey/valueだけをplain strへ揃える。"""
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {
            str(key) if isinstance(key, str) else key: _cache_json(member)
            for key, member in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_cache_json(member) for member in value]
    if isinstance(value, str):
        return str(value)
    return value


def _p3_packet_cache_key(
    packet: object,
    tenant: UUID,
    game: UUID,
    generation: int,
    nonplay_checkpoint_row: dict[str, object] | None,
) -> str:
    """packet全bytesとscopeだけから再検証省略のkeyを作る。"""
    return source_fingerprint(
        cast(
            dict[str, object],
            _cache_json(
                {
                    "tenant": str(tenant),
                    "game": str(game),
                    "generation": generation,
                    "packet": packet,
                    "nonplay_checkpoint_row": nonplay_checkpoint_row,
                }
            ),
        )
    )


def _p3_packet_cached(key: str) -> VerifiedP3Current | None:
    """同一全bytesの検証済み結果をプロセス内有界cacheから返す。"""
    with _P3_PACKET_CACHE_LOCK:
        value = _P3_PACKET_CACHE.get(key)
        if value is not None:
            _P3_PACKET_CACHE.move_to_end(key)
        return value


def _remember_p3_packet(key: str, value: VerifiedP3Current) -> None:
    """検証成功したpacketだけを有界に保持し、失敗結果は保持しない。"""
    with _P3_PACKET_CACHE_LOCK:
        _P3_PACKET_CACHE[key] = value
        _P3_PACKET_CACHE.move_to_end(key)
        while len(_P3_PACKET_CACHE) > _P3_PACKET_CACHE_LIMIT:
            _P3_PACKET_CACHE.popitem(last=False)


def verify_p3_current_packet(
    packet: object,
    *,
    tenant: UUID,
    game: UUID,
    generation: int,
    nonplay_checkpoint_row: dict[str, object] | None = None,
) -> VerifiedP3Current:
    """DB現head又はLC前anchor/元原本/有効数学/物理/T5を同値へ閉じる。

    同じpacket全bytesの成功結果だけをプロセス内に有界保持し、再読取で
    唯一核の再実行を繰り返さない。1byteでも違えば全件を再検証する。
    """
    try:
        key = _p3_packet_cache_key(
            packet, tenant, game, generation, nonplay_checkpoint_row
        )
    except (TypeError, ValueError):
        with _P3_PACKET_CACHE_LOCK:
            _P3_PACKET_CACHE_STATS["key_error"] += 1
        return _verify_p3_current_packet_uncached(
            packet,
            tenant=tenant,
            game=game,
            generation=generation,
            nonplay_checkpoint_row=nonplay_checkpoint_row,
        )
    cached = _p3_packet_cached(key)
    if cached is not None:
        with _P3_PACKET_CACHE_LOCK:
            _P3_PACKET_CACHE_STATS["hit"] += 1
        return cached
    result = _verify_p3_current_packet_uncached(
        packet,
        tenant=tenant,
        game=game,
        generation=generation,
        nonplay_checkpoint_row=nonplay_checkpoint_row,
    )
    _remember_p3_packet(key, result)
    with _P3_PACKET_CACHE_LOCK:
        _P3_PACKET_CACHE_STATS["miss"] += 1
    return result


def _verify_p3_current_packet_uncached(
    packet: object,
    *,
    tenant: UUID,
    game: UUID,
    generation: int,
    nonplay_checkpoint_row: dict[str, object] | None = None,
) -> VerifiedP3Current:
    """検証本体。cache判定を通さず全itemとT5を毎回再実行する。"""
    if (
        type(tenant) is not UUID
        or type(game) is not UUID
        or type(generation) is not int
        or generation <= 0
    ):
        raise PastCorrectionCurrentUnavailable("P3 current scopeが不正")
    raw = _object(packet)
    anchor = raw.get("kind") == "p3-anchor"
    required = {
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
    if (
        set(raw)
        != (
            required
            | ({"nonplay_checkpoint", "first_control_preparation"} if anchor else set())
        )
        or raw["kind"] not in {"p3-current", "p3-anchor"}
        or (
            anchor
            and (
                type(nonplay_checkpoint_row) is not dict
                or raw["nonplay_checkpoint"] != nonplay_checkpoint_row
                or _object(raw["checkpoint"])
                != _object(
                    _object(_object(raw["first_control_preparation"])["storage"])["row"]
                )
            )
        )
        or (not anchor and nonplay_checkpoint_row is not None)
    ):
        raise PastCorrectionCurrentUnavailable("P3 current packetが不正")
    head = _object(raw["head"])
    capsule = _object(raw["capsule"])
    # 後続playがP3 headのstats pointerを進めた場合、headはP3版のまま、
    # capsuleのstats_version_idだけが現在版を指し得る。
    historical = not anchor and head["stats_version_id"] != capsule["stats_version_id"]
    checkpoint_row = _object(raw["checkpoint"])
    stats_row = _object(raw["stats"])
    # 後続版がhead/capsuleの現pointerでも、P3訂正版はwatermark一致の
    # invalidated版としてだけ選ばれる。同一源集合の別版へ読み替えない。
    historical_stats = (
        stats_row["id"] != head["stats_version_id"]
        and stats_row["invalidated_at"] is not None
        and head["stats_version_id"] == capsule["stats_version_id"]
    )
    change_event = _object(raw["change_event"])
    change_ledger = _object(raw["change_ledger"])
    members = raw["members"]
    suffix_raw = raw["suffix"]
    sources_raw = raw["stats_sources"]
    if type(members) is not list or not 1 <= len(members) <= 26:
        raise PastCorrectionCurrentUnavailable("P3 current件数が不正")
    try:
        first_prep = None
        source_upper = stats_row["source_count"] if anchor else None
        if anchor and (
            type(source_upper) is not int
            or not len(members) <= source_upper <= len(members) + 100
        ):
            raise PastCorrectionCurrentUnavailable("P3歴史anchor水位が不正")
        current = read_lineup_prefix_document(
            _canonical_json(checkpoint_row["content"])
        )
        source_upper = source_upper if anchor else int(current.confirmed_watermark)
        if type(source_upper) is not int:
            raise PastCorrectionCurrentUnavailable("P3 source水位が不正")
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
            or (
                head["stats_version_id"] != capsule["stats_version_id"]
                and not historical
            )
            or capsule["tenant_id"] != str(tenant)
            or capsule["game_id"] != str(game)
            or capsule["internal_generation"] != generation
            or capsule["change_event_id"] != str(change_id)
            or capsule["watermark"] != len(members)
            or capsule["expected_version"] != 1
        ):
            raise PastCorrectionCurrentUnavailable("P3 current head/capsuleが不一致")
        stats_source_count = stats_row["source_count"]
        if (
            (stats_row["id"] != head["stats_version_id"] and not historical_stats)
            or stats_row["tenant_id"] != str(tenant)
            or stats_row["game_id"] != str(game)
            or type(stats_source_count) is not int
            or stats_source_count < source_upper
        ):
            raise PastCorrectionCurrentUnavailable("P3 current stats rowが不一致")
        if (
            previous.id != capsule["prior_checkpoint_id"]
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
            or not len(members) <= source_upper <= len(members) + 100
            or int(current.revision)
            != int(at_change.revision) + int(current.confirmed_watermark) - len(members)
        ):
            raise PastCorrectionCurrentUnavailable("P3 current CP linkageが不一致")
        if (
            change_event["tenant_id"] != str(tenant)
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
            raise PastCorrectionCurrentUnavailable("P3 current change eventが不一致")
        items: list[dict[str, object]] = []
        payloads: list[LineupPitchPlayPayload] = []
        ledger_fingerprints: list[object] = []
        source_d2: list[object] = []
        prior_payload: LineupPitchPlayPayload | None = None
        for d1, raw_member in enumerate(members, start=1):
            item, effective_payload, fingerprint, d2 = _verify_p3_current_member(
                raw_member,
                d1=d1,
                tenant=tenant,
                game=game,
                generation=generation,
                capsule_id=capsule_id,
                target_d1=target_d1,
                change_id=change_id,
                change_event=change_event,
                change_ledger=change_ledger,
                prior_payload=prior_payload,
            )
            items.append(item)
            payloads.append(effective_payload)
            ledger_fingerprints.append(fingerprint)
            source_d2.append(d2)
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
        matched_paged_source = None
        if source_digest != capsule["source_set_digest"]:
            # P3頁chain形式はitem digestの逐次chainを正本にする。
            import hashlib

            from pitchlog.sync.past_correction_paged import _chain_step

            chain = "0" * 64
            for index, item in enumerate(items, start=1):
                chain = _chain_step(chain, index, cast(str, item["digest"]))
            paged_source = hashlib.sha256(
                ":".join(
                    (
                        "p3-page-chain-v2",
                        str(capsule_id),
                        str(change_id),
                        previous.content_digest,
                        at_change.content_digest,
                        str(len(members)),
                        chain,
                    )
                ).encode("ascii")
            ).hexdigest()
            if paged_source != capsule["source_set_digest"]:
                raise PastCorrectionCurrentUnavailable("P3 source集合が不一致")
            matched_paged_source = paged_source
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
        evaluation_matches = (
            evaluated.evaluation_set_digest == capsule["stats_evaluation_set_digest"]
        )
        if not evaluation_matches and matched_paged_source is not None:
            import hashlib

            from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
            from pitchlog.sync.past_correction_paged import _chain_step

            chain = "0" * 64
            for source in evaluated.sources:
                chain = _chain_step(
                    chain,
                    source.d1,
                    source.original_evaluation_digest,
                    source.evaluation_digest,
                )
            paged_evaluation = hashlib.sha256(
                ":".join(
                    (
                        "p3-stats-chain-v2",
                        str(capsule_id),
                        SOURCE_MODEL_HASH,
                        matched_paged_source,
                        chain,
                    )
                ).encode("ascii")
            ).hexdigest()
            evaluation_matches = (
                paged_evaluation == capsule["stats_evaluation_set_digest"]
            )
        if (
            not evaluation_matches
            or evaluated.model_sha256 != stats_row["model_sha256"]
        ):
            raise PastCorrectionCurrentUnavailable("P3 T5評価集合が不一致")
        source_evaluations = [source.evaluation for source in evaluated.sources]
        if type(suffix_raw) is not list or len(suffix_raw) != source_upper - len(
            members
        ):
            raise PastCorrectionCurrentUnavailable("P3後続件数が不一致")
        if not suffix_raw and current != at_change:
            raise PastCorrectionCurrentUnavailable("P3現headが不一致")
        prior_ref = at_change.prefix_ref
        prior_after = at_change.after
        prior_runners = at_change.runners
        prior_participants = at_change.participants
        prior_lineup = at_change.lineup
        reconstructed = at_change
        for offset, raw_suffix in enumerate(suffix_raw, start=1):
            suffix = _object(raw_suffix)
            if set(suffix) != {
                "event",
                "ledger",
                "history",
                "play_row",
                "play_runners",
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
            d1 = len(members) + offset
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
                or request.prefix_ref != prior_ref
                or request.t1.before != prior_after
                or request.source.runners != prior_runners
                or request.source.participants != prior_participants
                or request.source.lineup != prior_lineup
                or request.rules != at_change.rules
            ):
                raise PastCorrectionCurrentUnavailable("P3後続原本が不一致")
            if (
                not anchor
                and offset == len(suffix_raw)
                and (
                    value.next_prefix_ref != current.prefix_ref
                    or value.t1.after != current.after
                    or value.t2 != current.t2
                    or value.runners != current.runners
                    or value.participants != current.participants
                    or value.lineup != current.lineup
                    or current.projection_snapshot is None
                    or current.projection_snapshot.play_row != play
                    or list(current.projection_snapshot.play_runners) != runners
                )
            ):
                raise PastCorrectionCurrentUnavailable("P3後続現CPが不一致")
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
            if anchor:
                from pitchlog.sync.terminal_pitch_projection import (
                    build_lineup_next_checkpoint,
                )

                reconstructed = build_lineup_next_checkpoint(
                    reconstructed,
                    {
                        "id": event["id"],
                        "tenant_id": str(tenant),
                        "game_id": str(game),
                        "generation": str(generation),
                        "d1": str(event["d1"]),
                        "d2": str(event["d2"]),
                        "d5": event["d5"],
                        "source_fingerprint": ledger["source_fingerprint"],
                        "event_fingerprint": ledger["source_fingerprint"],
                    },
                    value,
                    payload.calculation.artifact_sha256,
                    play,
                    runners,
                )
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
            prior_ref = value.next_prefix_ref
            prior_after = value.t1.after
            prior_runners = value.runners
            prior_participants = value.participants
            prior_lineup = value.lineup
        if anchor:
            from pitchlog.repositories.nonplay_prefix import _stored_contexts

            checkpoint = _object(nonplay_checkpoint_row)
            nonplay_content = _object(_object(checkpoint["content"])["content"])
            bridges = nonplay_content["controlBridges"]
            if type(bridges) is not list or not bridges:
                raise PastCorrectionCurrentUnavailable("P3歴史anchor制御が欠落")
            first_bridge = _object(bridges[0])
            first_prep = _object(raw["first_control_preparation"])
            before_source = _object(first_prep["before_source"])
            before_checkpoint = _object(before_source["checkpoint"])
            _, last_after = _stored_contexts(
                payloads[-1].model_dump(mode="json", by_alias=True, exclude_unset=True)
            )
            if (
                reconstructed != current
                or before_checkpoint["ref"] != first_bridge["checkpointBefore"]
                or first_bridge["beforeContext"] != last_after
                or current.confirmed_watermark != str(source_upper)
            ):
                raise PastCorrectionCurrentUnavailable("P3歴史anchorとLC制御が不一致")
        if type(sources_raw) is not list or len(sources_raw) < len(items):
            raise PastCorrectionCurrentUnavailable("P3現T5件数が不一致")
        for d1, (raw_source, item, evaluation) in enumerate(
            zip(sources_raw[: len(items)], items, source_evaluations, strict=True),
            start=1,
        ):
            source = _object(raw_source)
            play = _object(item["play_row"])
            effective_id = (
                item["effective_event_id"]
                if d1 <= len(members)
                else play["source_event_id"]
            )
            expected_source = {
                "tenant_id": str(tenant),
                "game_id": str(game),
                "fact_version_id": stats_row["id"],
                "recording_generation": generation,
                "d1": d1,
                "d2": source_d2[d1 - 1],
                "source_event_id": effective_id,
                "source_fingerprint": ledger_fingerprints[d1 - 1],
                "play_row_id": play["id"],
                "play_row_version": play["version"],
                "slot_version": 2 if d1 == target_d1 else 1,
                "artifact_sha256": payloads[d1 - 1].calculation.artifact_sha256,
                "metric_states": evaluation,
                "rule_sha256": evaluation["native_rule_sha256"],
            }
            for name, wanted in expected_source.items():
                if source[name] != wanted:
                    raise PastCorrectionCurrentUnavailable(
                        "P3現T5原本が不一致:" + name
                    )
        return VerifiedP3Current(
            current,
            previous,
            capsule_id,
            change_id,
            _uuid(capsule["d5"]),
            target_d1,
            _uuid(stats_row["id"]),
            tuple(items),
            tuple(payloads),
            anchor,
            first_prep,
        )
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise PastCorrectionCurrentUnavailable("P3 current全値照合が不成立") from error
