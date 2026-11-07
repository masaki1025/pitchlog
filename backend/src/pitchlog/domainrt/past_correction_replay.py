"""既通常T1の有限訂正反復を固定artifactへ渡す閉境界。

保存原本の真正性、対象版、T2、帰属、P3の認可/保存資格は本型から導かない。
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import (
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from pitchlog.domainrt.first_pitch import (
    DecimalInteger,
    StateSnapshot,
    _Envelope,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch import OrdinaryPitchValue
from pitchlog.domainrt.ordinary_pitch_continuation import (
    CanonicalUuid,
    PositiveInteger,
    _WireFrozen,
)


class ReplayEvent(_WireFrozen):
    """変更前または変更後の一球の入力選択。野球結果は計算しない。"""

    event_kind: Literal["batting-result"] = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: Literal["pitch-event"] = Field(alias="pitchEventKind")


class ReplayRecord(_WireFrozen):
    """真正に読み出した一つの旧eventと保存済みafterの候補。"""

    source_event_id: CanonicalUuid = Field(alias="sourceEventId")
    source_d2: PositiveInteger = Field(alias="sourceD2")
    original: ReplayEvent
    stored_after: StateSnapshot = Field(alias="storedAfter")
    replacement: ReplayEvent | None


class ReplayPageRequest(_WireFrozen):
    """25件以下の旧正史と新正史を一つのartifact呼出で再評価する。"""

    version: Literal["past-correction-ordinary-page-v1"]
    original_before: StateSnapshot = Field(alias="originalBefore")
    corrected_before: StateSnapshot = Field(alias="correctedBefore")
    previous_d2: DecimalInteger = Field(alias="previousD2")
    target_included: bool = Field(alias="targetIncluded")
    records: Annotated[tuple[ReplayRecord, ...], Field(min_length=1, max_length=25)]

    @field_validator("target_included", mode="before")
    @classmethod
    def _strict_bool(cls, value: object) -> object:
        """boolを0/1から黙って作らない。"""
        if type(value) is not bool:
            raise ValueError("targetIncludedは真理値が必要")
        return value

    @model_validator(mode="after")
    def _one_replacement(self) -> Self:
        """対象を含むページの先頭だけを置換し、後付け差し替えを閉じる。"""
        for index, row in enumerate(self.records):
            expected = self.target_included and index == 0
            if (row.replacement is not None) != expected:
                raise ValueError("対象以外の置換は指定できない")
        if self.target_included and self.original_before != self.corrected_before:
            raise ValueError("対象の前値は共通である必要がある")
        return self

    @classmethod
    def model_validate_json(
        cls, json_data: str | bytes | bytearray, **kwargs: Any
    ) -> Self:
        """余剰/重複/型変換を保存前のwire境界で拒否する。"""
        wire = json.loads(
            json_data,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        result = super().model_validate_json(json_data, **kwargs)
        dumped = result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(wire, sort_keys=True) != json.dumps(dumped, sort_keys=True):
            raise ValueError("訂正page入力の全wire値が不一致")
        return result


class ReplayFrame(_WireFrozen):
    """旧/新のT1全出力を保持する。成績やP3保存結果ではない。"""

    source_event_id: CanonicalUuid = Field(alias="sourceEventId")
    source_d2: PositiveInteger = Field(alias="sourceD2")
    original: OrdinaryPitchValue
    corrected: OrdinaryPitchValue


class ReplayPageValue(_WireFrozen):
    """次ページへ渡す両状態と各球の全T1値。"""

    original_after: StateSnapshot = Field(alias="originalAfter")
    corrected_after: StateSnapshot = Field(alias="correctedAfter")
    last_d2: PositiveInteger = Field(alias="lastD2")
    frames: Annotated[tuple[ReplayFrame, ...], Field(min_length=1, max_length=25)]


class ReplayPageSuccess(_Envelope):
    """有限数学成功。DB原本やP3取引の成功を表さない。"""

    ok: Literal[True]
    value: ReplayPageValue


class ReplayPageError(_WireFrozen):
    """artifactの閉じた非成功集合。"""

    code: Literal[
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "SOURCE_MISMATCH",
        "CORRECTION_UNSUPPORTED",
    ]


class ReplayPageFailure(_Envelope):
    """未対応・原本不一致を成功へ補完しない。"""

    ok: Literal[False]
    error: ReplayPageError


ReplayPageResponse: TypeAlias = ReplayPageSuccess | ReplayPageFailure
_RESPONSE = TypeAdapter(ReplayPageResponse)


class ReplayPageProtocolError(RuntimeError):
    """固定ABIに適合しないhost応答。"""


def decode_replay_page_response(raw: str) -> ReplayPageResponse:
    """重複key/非有限数/未知field/黙った型変換を拒否する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        response = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        dumped = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(wire, sort_keys=True) != json.dumps(dumped, sort_keys=True):
            raise ValueError("訂正page応答の全wire値が不一致")
        return response
    except (ValueError, TypeError, ValidationError):
        raise ReplayPageProtocolError("訂正page応答が固定ABIに適合しません") from None


def _bind_success_to_request(
    request: ReplayPageRequest, response: ReplayPageResponse
) -> None:
    """host応答の順序・原本参照・末尾値を渡したpageへ束縛する。"""
    if not isinstance(response, ReplayPageSuccess):
        return
    value = response.value
    if len(value.frames) != len(request.records):
        raise ReplayPageProtocolError("訂正page応答の件数が入力と不一致")
    for source, frame in zip(request.records, value.frames, strict=True):
        if (
            frame.source_event_id != source.source_event_id
            or frame.source_d2 != source.source_d2
            or frame.original.after.model_dump(mode="json", by_alias=True)
            != source.stored_after.model_dump(mode="json", by_alias=True)
        ):
            raise ReplayPageProtocolError("訂正page応答の原本参照が入力と不一致")
    final = value.frames[-1]
    if (
        value.last_d2 != final.source_d2
        or value.original_after.model_dump(mode="json", by_alias=True)
        != final.original.after.model_dump(mode="json", by_alias=True)
        or value.corrected_after.model_dump(mode="json", by_alias=True)
        != final.corrected.after.model_dump(mode="json", by_alias=True)
    ):
        raise ReplayPageProtocolError("訂正page応答の末尾値がframeと不一致")


def evaluate_replay_page(request: ReplayPageRequest) -> ReplayPageResponse:
    """固定製品hostの新操作を一度呼び、Pythonの野球計算を置かない。"""
    if type(request) is not ReplayPageRequest:
        raise TypeError("ReplayPageRequestの実型が必要")
    validated = ReplayPageRequest.model_validate(request)
    with open_domain_host() as host:
        response = decode_replay_page_response(
            host.call(
                "replayPastCorrectionPage",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
    _bind_success_to_request(validated, response)
    return response
