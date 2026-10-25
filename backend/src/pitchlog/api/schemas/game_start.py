"""開始前の入力外形を定義する。権利やスタメンの業務妥当性は認めない。

資格の非露出は公開Classのmodel_validate/model_validate_jsonと通常代入で保証する。
生TypeAdapter/SchemaValidatorのJSON構文エラーはClassへ到達せず、入力を保持し得る。
RequestValidationError.bodyも含め、内部入力まで無害化されたとは扱わない。
将来のHTTP入口は既存register_exception_handlersを維持し、body/生parser例外を
ログへ渡さず、利用者向け応答/ログの非露出を実HTTPでも検査する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import (
    AwareDatetime,
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
    """URLの試合へ提示する開始入力。通過しても開始や端末資格の証明ではない。

    公開Class入口を使用する。生のPydantic parser例外内部は非露出保証の対象外で、
    HTTPには共通handlerが必要である。SchemaValidator等を差し替えない。
    """

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


class _InitialResponseSchema(BaseSchema):
    """通信値の不変外形。通過しても発行・commit・認可の証明ではない。"""

    model_config = ConfigDict(frozen=True, strict=True, hide_input_in_errors=True)

    @model_validator(mode="wrap")
    @classmethod
    def _safe_response(
        cls, value: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        """公開Class入口で資格を含む入力と元例外を外へ連結しない。"""
        try:
            return handler(value)
        except ValidationError as error:
            sanitized = _without_input(cls.__name__, error)
        raise sanitized

    @classmethod
    def model_validate_json(
        cls, json_data: str | bytes | bytearray, **kwargs: Any
    ) -> Self:
        """構文エラーも安全な公開Class境界へ閉じる。"""
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as error:
            sanitized = _without_input(cls.__name__, error)
        raise sanitized

    def __setattr__(self, name: str, value: Any) -> None:
        """不変値への代入失敗にも提示された資格を残さない。"""
        try:
            super().__setattr__(name, value)
        except ValidationError as error:
            sanitized = _without_input(type(self).__name__, error)
        else:
            return
        raise sanitized


class InitialDeviceEnrollmentResponse(_InitialResponseSchema):
    """端末登録の応答外形。A単位では登録操作を実行しない。"""

    tenant_id: EntityId
    device_id: EntityId
    device_credential: SecretStr

    @field_validator("device_credential")
    @classmethod
    def _credential_present(cls, value: SecretStr) -> SecretStr:
        """空資格を補完しない。"""
        if (
            type(value) is not SecretStr
            or type(value.get_secret_value()) is not str
            or not value.get_secret_value()
            or len(value.get_secret_value()) > 4096
        ):
            raise ValueError("端末資格の外形が不正")
        return value


class InitialGameStartResponse(_InitialResponseSchema):
    """開始原本と初期権の外形。初期stateやReadyを生成しない。"""

    tenant_id: EntityId
    game_id: EntityId
    start_request_id: EntityId
    device_id: EntityId
    d4: str
    recovery_generation: str
    recording_right_proof: SecretStr
    started_at: AwareDatetime
    away_lineup_id: EntityId
    home_lineup_id: EntityId

    @field_validator("started_at", mode="before")
    @classmethod
    def _timestamp(cls, value: object) -> datetime:
        """JSONの日時文字列だけを明示解析し、数値timestampを拒否する。"""
        if type(value) is datetime:
            return value
        if type(value) is str and len(value) <= 64:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        raise ValueError("開始日時の外形が不正")

    @field_validator("d4")
    @classmethod
    def _reference_present(cls, value: str) -> str:
        """一般D4ではなく本応答の参照上限だけを検査する。"""
        if not value or len(value) > 128:
            raise ValueError("世代参照の外形が不正")
        return value

    @field_validator("recovery_generation")
    @classmethod
    def _epoch_present(cls, value: str) -> str:
        """正のbigint十進表現だけを受け、bool/numberを変換しない。"""
        if (
            not value.isascii()
            or not value.isdecimal()
            or value.startswith("0")
            or len(value) > 19
            or int(value) > 2**63 - 1
        ):
            raise ValueError("復旧世代の外形が不正")
        return value

    @field_validator("recording_right_proof")
    @classmethod
    def _proof_present(cls, value: SecretStr) -> SecretStr:
        """原V12を通常dumpへ出さず、不在を補完しない。"""
        if (
            type(value) is not SecretStr
            or type(value.get_secret_value()) is not str
            or not value.get_secret_value()
            or len(value.get_secret_value()) > 4096
        ):
            raise ValueError("記録権提示値の外形が不正")
        return value
