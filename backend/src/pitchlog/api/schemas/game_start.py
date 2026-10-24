"""開始前の入力外形だけを定義し、権利やスタメンの業務妥当性を認めない。"""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    ModelWrapValidatorHandler,
    SecretStr,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from pitchlog.api.schemas.base import BaseSchema, EntityId

_INPUT_FIELDS = frozenset(
    {
        "start_request_id",
        "device_id",
        "device_credential",
        "away",
        "home",
        "player_id",
        "batting_order",
        "fielding_position",
    }
)


def _without_input(title: str, error: ValidationError) -> ValidationError:
    """他fieldの欠損等でも、資格を含む元object/JSON/例外contextを残さない。"""
    details: list[InitErrorDetails] = []
    for item in error.errors(include_input=False, include_context=False):
        details.append(
            {
                # JsonValueの独自errorも受け、元のmsg/context/inputはコピーしない。
                "type": PydanticCustomError(
                    "start_input_invalid", "開始入力の外形が不正"
                ),
                "input": None,
                "loc": tuple(
                    part if type(part) is int or part in _INPUT_FIELDS else "input"
                    for part in item["loc"]
                ),
            }
        )
    return ValidationError.from_exception_data(title, details, hide_input=True)


class StartLineupInput(BaseSchema):
    """確定前の選手/打順/守備表現を保持し、DHや在籍の意味検証は行わない。"""

    player_id: EntityId
    batting_order: Annotated[StrictInt, Field(ge=1, le=9)] | None
    fielding_position: JsonValue


class GameStartRequest(BaseSchema):
    """URLの試合へ提示する開始入力。通過しても開始や端末資格の証明ではない。"""

    model_config = ConfigDict(hide_input_in_errors=True, validate_assignment=True)

    start_request_id: EntityId
    device_id: EntityId
    device_credential: SecretStr
    away: Annotated[tuple[StartLineupInput, ...], Field(min_length=9, max_length=10)]
    home: Annotated[tuple[StartLineupInput, ...], Field(min_length=9, max_length=10)]

    @field_validator("device_credential")
    @classmethod
    def _nonempty_credential(cls, value: SecretStr) -> SecretStr:
        """新しい資格を発行せず、空の提示値を拒否する。"""
        if not value.get_secret_value():
            raise ValueError("端末資格は非空が必要")
        return value

    @model_validator(mode="wrap")
    @classmethod
    def _validate_without_input(
        cls, value: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        """解析失敗が元request全体や資格fieldを例外へ保持しないようにする。"""
        try:
            return handler(value)
        except ValidationError as error:
            sanitized = _without_input(cls.__name__, error)
        # exceptの外で送出し、原入力を持つ例外を__context__にも連結しない。
        raise sanitized

    @classmethod
    def model_validate_json(
        cls, json_data: str | bytes | bytearray, **kwargs: Any
    ) -> Self:
        """JSON構文エラーはmodel validatorより前なので、同じ非露出境界へ閉じる。"""
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as error:
            sanitized = _without_input(cls.__name__, error)
        raise sanitized
