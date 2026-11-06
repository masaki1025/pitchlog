"""P3有限再評価値から新current v3 checkpoint候補を構成する。"""

from __future__ import annotations

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.play_prefix import (
    LineupPrefixDocument,
    read_lineup_prefix_document,
)
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.past_correction_preparation import PreparedP3LineupCorrection


class PastCorrectionCheckpointError(RuntimeError):
    """新current候補と元CP・唯一評価値の結合が不成立。"""


def build_corrected_lineup_checkpoint(
    prepared: PreparedP3LineupCorrection,
) -> LineupPrefixDocument:
    """元原本を残して新head候補を閉型検査する。DB保存資格は発行しない。"""
    if (
        type(prepared) is not PreparedP3LineupCorrection
        or type(prepared.original_checkpoint) is not LineupPrefixDocument
        or not prepared.corrected
        or len(prepared.corrected) != len(prepared.physical)
        or prepared.corrected[-1].d1 != len(prepared.originals)
        or prepared.original_checkpoint.confirmed_watermark
        != str(len(prepared.originals))
        or prepared.original_checkpoint.prefix_ref
        != prepared.originals[-1].calculation.response.value.next_prefix_ref
    ):
        raise PastCorrectionCheckpointError("P3新headの真正原本が不一致")
    old = prepared.original_checkpoint
    final = prepared.corrected[-1].corrected_response.value
    last_physical = prepared.physical[-1]
    next_ref = final.next_prefix_ref
    if (
        next_ref.checkpoint.id == old.id
        or next_ref.tenant_id != old.prefix_ref.tenant_id
        or next_ref.game_id != old.prefix_ref.game_id
        or next_ref.generation != old.prefix_ref.generation
        or next_ref.length != old.prefix_ref.length
        or last_physical.d1 != len(prepared.originals)
        or last_physical.original_event_id
        != prepared.originals[-1].source_event_id
    ):
        raise PastCorrectionCheckpointError("P3新headの位置が不一致")
    value = old.model_dump(mode="json", by_alias=True, exclude_unset=True)
    value.update(
        id=next_ref.checkpoint.id,
        revision=next_ref.checkpoint.revision,
        storage_anchor={
            "id": next_ref.checkpoint.id,
            "history_epoch": old.history_version,
        },
        prefix_ref=next_ref.model_dump(mode="json", by_alias=True),
        after=final.t1.after.model_dump(mode="json", by_alias=True),
        t2=final.t2.model_dump(mode="json", by_alias=True),
        runners=[r.model_dump(mode="json", by_alias=True) for r in final.runners],
        participants=final.participants.model_dump(mode="json", by_alias=True),
        pa_start_source=final.next_responsibility.pa_start_source.model_dump(
            mode="json", by_alias=True
        ),
        lineup=final.lineup.model_dump(mode="json", by_alias=True),
        roster_digest=final.roster_digest,
        previous_prefix_ref=final.previous_prefix_ref.model_dump(
            mode="json", by_alias=True
        ),
        artifact_sha256=final.execution_artifact_sha256,
        projection_snapshot={
            "play_row": last_physical.play_row,
            "play_runners": list(last_physical.play_runners),
        },
    )
    del value["content_digest"]
    value["content_digest"] = source_fingerprint(value)
    try:
        return read_lineup_prefix_document(_canonical_json(value))
    except (ValueError, TypeError, KeyError):
        raise PastCorrectionCheckpointError("P3新head閉型が不成立") from None
