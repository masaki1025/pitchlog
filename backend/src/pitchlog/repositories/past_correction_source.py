"""P3前のcurrent v3原本を同一tenant取引の既限定readerで取得する。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.domainrt.past_correction_lineup import SavedLineupPitch
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixView,
    _json,
    _verify_v2_read_packet,
    read_lineup_prefix,
)
from pitchlog.repositories.started_snapshot import _one
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixHistoryPageToken
from pitchlog.sync.tokens import RecordingGenerationReadToken


class PastCorrectionSourceUnavailable(RuntimeError):
    """限定v3の全原本と現在headを一取引へ束縛できない。"""


def read_past_correction_v3_source(
    scope: _TenantTransaction, game_id: UUID, target_d1: int
) -> tuple[SavedLineupPitch, ...]:
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
            or anchor["id"] != ref.checkpoint.id
            or anchor["revision"] != ref.checkpoint.revision
            or storage.id != anchor["id"]
        ):
            raise PastCorrectionSourceUnavailable("current v3 headと履歴件数が不一致")
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
                or event["tenant_id"] != str(scope._bound_tenant_id)
                or event["game_id"] != str(game_id)
                or event["replaced_at"] is not None
                or event["retired_at"] is not None
            ):
                raise PastCorrectionSourceUnavailable("v3原本の順序又は参照が不正")
            payload = _verify_v2_read_packet(
                item, scope._bound_tenant_id, game_id, lineup=True
            )
            source.append(
                SavedLineupPitch(
                    UUID(event["id"]),
                    number,
                    event["d2"],
                    payload.calculation,
                    payload,
                )
            )
        last = projection["last_source"]
        if last is None or last.event_id != str(source[-1].source_event_id):
            raise PastCorrectionSourceUnavailable("v3最終原本とcurrent headが不一致")
        return tuple(source)
    except (OrdinaryPrefixError, KeyError, TypeError, ValueError, AttributeError):
        raise PastCorrectionSourceUnavailable("v3原本を全値確認できない") from None
