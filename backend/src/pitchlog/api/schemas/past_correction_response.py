"""既P3の対象・受理I6・拒否応答を、既domain型を使って閉じる。"""

from typing import Annotated, Literal, TypeAlias

from pydantic import ConfigDict, Field, StrictInt, StrictStr, TypeAdapter

from pitchlog.api.schemas.base import BaseSchema
from pitchlog.domainrt.lineup_play_prefix_continuation import PrefixRef
from pitchlog.domainrt.play_prefix_continuation import CanonicalUuid
from pitchlog.domainrt.strikeout_pitch import StrikeoutSnapshot
from pitchlog.sync.model import RejectedChangeBoundary
from pitchlog.sync.past_correction_payload import LineupPitchChangePayload

_Positive: TypeAlias = Annotated[StrictInt, Field(ge=1, lt=2**63)]
_WireRef: TypeAlias = Annotated[StrictStr, Field(min_length=1, max_length=128)]


class _ChangeResponse(BaseSchema):
    """型の補正・余剰フィールド・既JSON形の暗黙変更を許さない。"""

    model_config = ConfigDict(strict=True)


class ChangeTargetReference(_ChangeResponse):
    """既対象取得の英字3キーをそのまま返す。"""

    game: CanonicalUuid
    d4: _WireRef
    d1: _Positive


class ChangeReceiptReference(_ChangeResponse):
    """既I6の日本語3キーを別名のまま保持する。"""

    game: CanonicalUuid = Field(alias="試合")
    d4: _WireRef = Field(alias="対象の D4")
    d1: _Positive = Field(alias="対象の D1")


class ChangeTargetResponse(_ChangeResponse):
    """対象原本と既閉prefix参照だけを受け付ける。"""

    target_reference: ChangeTargetReference
    expected_version: _Positive
    expected_prefix_ref: PrefixRef
    target_event_id: CanonicalUuid
    target_play_id: CanonicalUuid
    original_result_id: Literal[
        "batting-result.ball",
        "batting-result.called-pitch",
        "batting-result.called-strikeout",
    ]


class ChangeConfirmationResponse(_ChangeResponse):
    """実受理原本と現保存状態の既確認形を保持する。"""

    target_reference: ChangeTargetReference
    confirmed_version: _Positive
    d5: CanonicalUuid
    source_event_id: CanonicalUuid
    target_play_id: CanonicalUuid
    stats_version_id: CanonicalUuid
    current_prefix_ref: PrefixRef
    current_after: StrikeoutSnapshot


class AcceptedChangeResponse(_ChangeResponse):
    """受理した既I6全項目を省かず、ACKへ取り違えない。"""

    boundary: Literal["変更受理"]
    target_reference: ChangeReceiptReference
    expected_version: _Positive
    d5: CanonicalUuid
    confirmed_content: LineupPitchChangePayload
    accepted_at: Annotated[StrictStr, Field(min_length=1)]


class RejectedChangeResponse(_ChangeResponse):
    """既B8〜B14と明示nullを含む理由を受理形から分離する。"""

    boundary: RejectedChangeBoundary
    d5: CanonicalUuid
    reason: StrictStr | None


ChangeResultResponse: TypeAlias = Annotated[
    AcceptedChangeResponse | RejectedChangeResponse, Field(discriminator="boundary")
]
_CHANGE_RESULT = TypeAdapter(ChangeResultResponse)


def validate_change_result_response(
    value: object,
) -> AcceptedChangeResponse | RejectedChangeResponse:
    """実応答を閉unionへ検証し、未知結果を成功へ補修しない。"""
    return _CHANGE_RESULT.validate_python(value)
