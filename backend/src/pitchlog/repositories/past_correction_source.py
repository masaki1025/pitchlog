"""P3前のcurrent v3原本を同一tenant取引の既限定readerで取得する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.past_correction_lineup import SavedLineupPitch
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixView,
    _function_one,
    _json,
    _verify_v2_read_packet,
    read_lineup_prefix,
)
from pitchlog.repositories.play_prefix import (
    LineupPrefixDocument,
    read_lineup_prefix_document,
)
from pitchlog.repositories.started_snapshot import _one
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.terminal_pitch_tokens import (
    PlayPrefixCheckpointReadToken,
    PlayPrefixHistoryPageToken,
)
from pitchlog.sync.tokens import RecordingGenerationReadToken


class PastCorrectionSourceUnavailable(RuntimeError):
    """限定v3の全原本と現在headを一取引へ束縛できない。"""


@dataclass(frozen=True, slots=True)
class PastCorrectionV3SourceSnapshot:
    """DB内部D4とTS上の不透明prefix generationを混同しない原本。"""

    internal_generation: int
    rows: tuple[SavedLineupPitch, ...]
    checkpoint: LineupPrefixDocument | None = None


@dataclass(frozen=True, slots=True)
class PastCorrectionV3PagedSource:
    """全ページ読了後だけ得られる同取引の現head証明。"""

    internal_generation: int
    watermark: int
    checkpoint: LineupPrefixDocument


def read_past_correction_watermark(
    scope: _TenantTransaction, game_id: UUID
) -> tuple[int, int]:
    """既E1読取資格で現在の内部世代と確定水位だけを閉じる。"""
    if type(scope) is not _TenantTransaction or type(game_id) is not UUID:
        raise PastCorrectionSourceUnavailable("P3水位読取の元参照が不正")
    try:
        current = _one(
            scope.run(RecordingGenerationReadToken(game_id)),
            _GENERATION_READ_COLUMNS,
        )
        generation = current["generation"]
        watermark = current["confirmed_watermark"]
        if (
            type(generation) is not int
            or generation < 1
            or type(watermark) is not int
            or watermark < 1
        ):
            raise PastCorrectionSourceUnavailable("P3確定水位が不正")
        return generation, watermark
    except (KeyError, TypeError, ValueError, OrdinaryPrefixError):
        raise PastCorrectionSourceUnavailable("P3確定水位が利用できない") from None


def _saved_from_packet(
    packet: tuple[object, ...],
    number: int,
    tenant: UUID,
    game_id: UUID,
    generation: int,
    *,
    _host=None,
) -> SavedLineupPitch:
    """既私有pageの1行を元event・物理・唯一計算の全値へ束縛する。"""
    if len(packet) != 1:
        raise PastCorrectionSourceUnavailable("v3原本packetが不正")
    item = _json(packet[0])
    if type(item) is not dict or set(item) != {
        "history",
        "event",
        "play_row",
        "expected_play_row",
        "play_runners",
        "expected_play_runners",
    }:
        raise PastCorrectionSourceUnavailable("v3原本packet形が不正")
    history, event = item["history"], item["event"]
    if (
        type(history) is not dict
        or type(event) is not dict
        or history["d1"] != number
        or event["d1"] != number
        or event["d2"] != history["d2"]
        or event["id"] != history["source_event_id"]
        or event["event_kind"] != "play_input"
        or event["generation"] != generation
        or event["tenant_id"] != str(tenant)
        or event["game_id"] != str(game_id)
        or event["replaced_at"] is not None
        or event["retired_at"] is not None
    ):
        raise PastCorrectionSourceUnavailable("v3原本の順序又は参照が不正")
    payload = _verify_v2_read_packet(item, tenant, game_id, lineup=True, _host=_host)
    return SavedLineupPitch(
        UUID(event["id"]),
        number,
        event["d2"],
        payload.calculation,
        payload,
        item["play_row"],
        tuple(item["play_runners"]),
    )


def visit_past_correction_v3_source_pages(
    scope: _TenantTransaction,
    game_id: UUID,
    target_d1: int,
    consume: Callable[[tuple[SavedLineupPitch, ...], LineupPrefixDocument], None],
    *,
    _host=None,
    _progress: Callable[[], None] | None = None,
) -> PastCorrectionV3PagedSource:
    """有界原本pageの実hostを一つだけ所有し、各行の再検証は省かない。"""
    from contextlib import nullcontext

    from pitchlog.domainrt.host import NodeDomainHost, open_domain_host

    if (
        type(scope) is not _TenantTransaction
        or type(game_id) is not UUID
        or type(target_d1) is not int
        or target_d1 < 1
        or not callable(consume)
        or (_host is not None and type(_host) is not NodeDomainHost)
        or (_progress is not None and not callable(_progress))
    ):
        raise PastCorrectionSourceUnavailable("P3頁読取の入力が不正")
    with open_domain_host() if _host is None else nullcontext(_host) as host:
        return _visit_past_correction_v3_source_pages_with_host(
            scope,
            game_id,
            target_d1,
            consume,
            host=host,
            progress=_progress,
        )


def _visit_past_correction_v3_source_pages_with_host(
    scope: _TenantTransaction,
    game_id: UUID,
    target_d1: int,
    consume: Callable[[tuple[SavedLineupPitch, ...], LineupPrefixDocument], None],
    *,
    host,
    progress: Callable[[], None] | None = None,
) -> PastCorrectionV3PagedSource:
    """同一scopeの25件keysetを全水位まで訪問し、全件RAM保持を避ける。"""
    if (
        type(scope) is not _TenantTransaction
        or type(game_id) is not UUID
        or type(target_d1) is not int
        or target_d1 < 1
        or not callable(consume)
    ):
        raise PastCorrectionSourceUnavailable("P3頁読取の入力が不正")
    try:
        current = _one(
            scope.run(RecordingGenerationReadToken(game_id)),
            _GENERATION_READ_COLUMNS,
        )
        generation = current["generation"]
        watermark = current["confirmed_watermark"]
        if (
            type(generation) is not int
            or generation < 1
            or type(watermark) is not int
            or watermark < target_d1
        ):
            raise PastCorrectionSourceUnavailable("P3頁読取の水位が不正")
        cursor: str | None = None
        after = (0, 0, UUID(int=0))
        seen = 0
        checkpoint: LineupPrefixDocument | None = None
        head: object = None
        storage_head: object = None
        last: SavedLineupPitch | None = None
        while seen < watermark:
            if progress is not None:
                progress()
            view = read_lineup_prefix(
                scope, game_id, limit=25, cursor=cursor, _host=host, _progress=progress
            )
            if type(view) is not OrdinaryPrefixView:
                raise PastCorrectionSourceUnavailable("P3頁のv3 readが欠落")
            projection = view.projection
            page = projection["page"]
            items = page["items"]
            ref = projection["prefix_ref"]
            anchor = projection["checkpoint_anchor"]
            storage = projection["storage_anchor"]
            if (
                type(page) is not dict
                or type(items) is not list
                or not 1 <= len(items) <= 25
                or seen + len(items) > watermark
                or type(anchor) is not dict
                or storage is None
                or page["next_cursor"] is not None
                and (type(page["next_cursor"]) is not str or not page["next_cursor"])
                or (page["next_cursor"] is None) != (seen + len(items) == watermark)
                or ref.length != str(watermark)
                or ref.tenant_id != str(scope._bound_tenant_id)
                or ref.game_id != str(game_id)
                or storage.id != anchor["id"]
            ):
                raise PastCorrectionSourceUnavailable("P3頁のhead又は件数が不正")
            if checkpoint is None:
                raw_checkpoint = _function_one(
                    scope, PlayPrefixCheckpointReadToken(game_id, generation)
                )
                if (
                    type(raw_checkpoint) is not dict
                    or raw_checkpoint.get("kind") != "checkpoint"
                    or type(raw_checkpoint.get("row")) is not dict
                    or type(raw_checkpoint["row"].get("content")) is not dict
                ):
                    raise PastCorrectionSourceUnavailable("P3頁のCPが欠落")
                row = raw_checkpoint["row"]
                checkpoint = read_lineup_prefix_document(
                    _canonical_json(row["content"])
                )
                if (
                    checkpoint.id != anchor["id"]
                    or checkpoint.revision != anchor["revision"]
                    or checkpoint.prefix_ref != ref
                    or checkpoint.internal_generation != str(generation)
                    or checkpoint.confirmed_watermark != str(watermark)
                    or checkpoint.content_digest != row.get("content_digest")
                    or row.get("id") != checkpoint.id
                    or row.get("state") != "current"
                ):
                    raise PastCorrectionSourceUnavailable("P3頁のCP原本が不一致")
                head = ref
                storage_head = storage
            elif (
                ref != head
                or storage != storage_head
                or anchor["id"] != checkpoint.id
                or anchor["revision"] != checkpoint.revision
            ):
                raise PastCorrectionSourceUnavailable("P3頁の途中headが変化")
            token = PlayPrefixHistoryPageToken(
                game_id,
                generation,
                int(storage.history_epoch),
                UUID(ref.checkpoint.id),
                int(anchor["revision"]),
                int(ref.history_version),
                watermark,
                *after,
                25,
            )
            packets = scope.run_function(token).rows
            lookahead = 0 if page["next_cursor"] is None else 1
            if len(packets) != len(items) + lookahead:
                raise PastCorrectionSourceUnavailable("P3頁の私有原本件数が不一致")
            source: list[SavedLineupPitch] = []
            for offset, packet in enumerate(packets[: len(items)], start=1):
                if progress is not None:
                    progress()
                saved = _saved_from_packet(
                    packet,
                    seen + offset,
                    scope._bound_tenant_id,
                    game_id,
                    generation,
                    _host=host,
                )
                public = items[offset - 1]
                if (
                    type(public) is not dict
                    or type(public.get("play_row")) is not dict
                    or saved.play_row is None
                    or public["play_row"].get("id") != saved.play_row.get("id")
                    or public["play_row"].get("source_event_id")
                    != str(saved.source_event_id)
                    or public.get("history_entry")
                    != saved.calculation.response.value.new_history_entry.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    )
                    or (last is not None and saved.d2 <= last.d2)
                ):
                    raise PastCorrectionSourceUnavailable("P3頁の公開/私有原本が不一致")
                if progress is not None:
                    progress()
                source.append(saved)
                last = saved
            assert checkpoint is not None
            consume(tuple(source), checkpoint)
            seen += len(source)
            assert last is not None
            after = (last.d1, last.d2, last.source_event_id)
            cursor = page["next_cursor"]
        if (
            checkpoint is None
            or last is None
            or cursor is not None
            or last.calculation.response.value.next_prefix_ref != checkpoint.prefix_ref
            or _one(
                scope.run(RecordingGenerationReadToken(game_id)),
                _GENERATION_READ_COLUMNS,
            )
            != current
        ):
            raise PastCorrectionSourceUnavailable("P3頁末尾とcurrent headが不一致")
        return PastCorrectionV3PagedSource(generation, watermark, checkpoint)
    except (OrdinaryPrefixError, KeyError, TypeError, ValueError, AttributeError):
        raise PastCorrectionSourceUnavailable("P3原本頁を全値確認できない") from None


def read_past_correction_v3_source_snapshot(
    scope: _TenantTransaction, game_id: UUID, target_d1: int
) -> PastCorrectionV3SourceSnapshot:
    """既v3 current head/全物理行を再検証し、先頭対象の有限suffixを読む。

    既readerはpoint CP/ledger/物理投影/履歴を照合する。ここでは元D1/D2と
    完全な保存計算封筒をP3用に束縛する。D1が25超又は非play混在なら閉じる。
    """
    if (
        type(scope) is not _TenantTransaction
        or type(game_id) is not UUID
        or type(target_d1) is not int
        or not 1 <= target_d1 <= 25
    ):
        raise PastCorrectionSourceUnavailable("限定v3原本対象が不正")
    try:
        view = read_lineup_prefix(scope, game_id, limit=25)
        if type(view) is not OrdinaryPrefixView:
            raise PastCorrectionSourceUnavailable("現在v3原本が利用できない")
        projection = view.projection
        page = projection["page"]
        items = page["items"]
        if (
            type(page) is not dict
            or type(items) is not list
            or not 1 <= len(items) <= 25
            or page["next_cursor"] is not None
        ):
            raise PastCorrectionSourceUnavailable("有限v3全履歴を確認できない")
        current = _one(
            scope.run(RecordingGenerationReadToken(game_id)),
            _GENERATION_READ_COLUMNS,
        )
        generation = current["generation"]
        watermark = current["confirmed_watermark"]
        anchor = projection["checkpoint_anchor"]
        storage = projection["storage_anchor"]
        ref = projection["prefix_ref"]
        if (
            type(generation) is not int
            or type(watermark) is not int
            or watermark != len(items)
            or watermark > 25
            or target_d1 > watermark
            or anchor["revision"] != ref.checkpoint.revision
            or storage.id != anchor["id"]
        ):
            raise PastCorrectionSourceUnavailable("current v3 headと履歴件数が不一致")
        raw_checkpoint = _function_one(
            scope, PlayPrefixCheckpointReadToken(game_id, generation)
        )
        if (
            type(raw_checkpoint) is not dict
            or raw_checkpoint.get("kind") != "checkpoint"
            or type(raw_checkpoint.get("row")) is not dict
        ):
            raise PastCorrectionSourceUnavailable("current v3 checkpointが欠落")
        checkpoint_row = raw_checkpoint["row"]
        if type(checkpoint_row.get("content")) is not dict:
            raise PastCorrectionSourceUnavailable("current v3 checkpoint本文が不正")
        checkpoint = read_lineup_prefix_document(
            _canonical_json(checkpoint_row["content"])
        )
        if (
            checkpoint.id != anchor["id"]
            or checkpoint.revision != anchor["revision"]
            or checkpoint.prefix_ref != ref
            or checkpoint.internal_generation != str(generation)
            or checkpoint.confirmed_watermark != str(watermark)
            or checkpoint.content_digest != checkpoint_row.get("content_digest")
            or checkpoint_row.get("id") != checkpoint.id
            or checkpoint_row.get("state") != "current"
        ):
            raise PastCorrectionSourceUnavailable("current v3 checkpoint原本が不一致")
        token = PlayPrefixHistoryPageToken(
            game_id,
            generation,
            int(storage.history_epoch),
            UUID(ref.checkpoint.id),
            int(anchor["revision"]),
            int(ref.history_version),
            watermark,
            0,
            0,
            UUID(int=0),
            25,
        )
        packets = scope.run_function(token).rows
        if len(packets) != watermark:
            raise PastCorrectionSourceUnavailable("v3原本pageが欠落又は余剰")
        source: list[SavedLineupPitch] = []
        for number, packet in enumerate(packets, start=1):
            source.append(
                _saved_from_packet(
                    packet, number, scope._bound_tenant_id, game_id, generation
                )
            )
        last = projection["last_source"]
        if (
            last is None
            or last.event_id != str(source[-1].source_event_id)
            or source[-1].calculation.response.value.next_prefix_ref != ref
        ):
            raise PastCorrectionSourceUnavailable("v3最終原本とcurrent headが不一致")
        return PastCorrectionV3SourceSnapshot(generation, tuple(source), checkpoint)
    except (OrdinaryPrefixError, KeyError, TypeError, ValueError, AttributeError):
        raise PastCorrectionSourceUnavailable("v3原本を全値確認できない") from None


def read_past_correction_v3_source(
    scope: _TenantTransaction, game_id: UUID, target_d1: int
) -> tuple[SavedLineupPitch, ...]:
    """旧有限原本利用者へ同じ閉読取の行列だけを返す。"""
    return read_past_correction_v3_source_snapshot(scope, game_id, target_d1).rows
