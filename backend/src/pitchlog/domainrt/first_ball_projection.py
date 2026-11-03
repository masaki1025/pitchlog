"""初球の既計算値を閉JSONへ写し、独立な期待値と全値比較する。

数学・真正な同一評価・認可・writer資格・保存成功を証明しない。呼出側が
真正なrequest/responseと実artifact identityを供給する責任を保持する。
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from pitchlog.domainrt.first_pitch import (
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    CombinedSuccess,
    _check_frozen_members,
    _WireFrozen,
)

_FORMAT_VERSION = "first-ball-calculation-v1"
_ERROR = "初球計算値の閉形式又は期待値が一致しません"


class FirstBallProjectionError(ValueError):
    """入力や資格候補を含めない固定の形式/期待値拒否。"""


def _canonical_sha256(value: str) -> str:
    """出所を推定せず、明示されたhashの表現だけを検査する。"""
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("artifact hashの形式が不正")
    return value


class FirstBallCalculationValue(_WireFrozen):
    """再取得した不変値。private証明・Ready・保存ACKではない。"""

    format_version: Literal["first-ball-calculation-v1"] = Field(alias="formatVersion")
    artifact_sha256: Annotated[str, AfterValidator(_canonical_sha256)] = Field(
        alias="artifactSha256"
    )
    request: CombinedRequest
    response: CombinedSuccess


def _canonical_json(value: object) -> str:
    """辞書のkey順だけを正規化し、型・array順/件数を保つ。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _same_member_types(original: object, validated: object) -> None:
    """再検査で強制変更のmodel/tuple/派生型を黙って正規化させない。"""
    if type(original) is not type(validated):
        raise ValueError("model memberの型が不一致")
    if isinstance(original, _Frozen):
        assert isinstance(validated, _Frozen)
        for name in type(original).model_fields:
            _same_member_types(vars(original)[name], vars(validated)[name])
    elif type(original) is tuple:
        assert type(validated) is tuple
        if len(original) != len(validated):
            raise ValueError("tuple要素数が不一致")
        for before, after in zip(original, validated, strict=True):
            _same_member_types(before, after)


def _frame(
    request: CombinedRequest, response: CombinedSuccess, artifact_sha256: str
) -> FirstBallCalculationValue:
    """既DTOを再検査し、全値を独立した入れ子のmodelへ写す。"""
    if type(request) is not CombinedRequest or type(response) is not CombinedSuccess:
        raise TypeError("初球の既要求/成功型だけが必要")
    _canonical_sha256(artifact_sha256)
    _check_frozen_members(request)
    _check_frozen_members(response)
    checked_request = CombinedRequest.model_validate(request)
    checked_response = CombinedSuccess.model_validate(response)
    _same_member_types(request, checked_request)
    _same_member_types(response, checked_response)
    return FirstBallCalculationValue.model_validate_json(
        _canonical_json(
            {
                "formatVersion": _FORMAT_VERSION,
                "artifactSha256": artifact_sha256,
                "request": checked_request.model_dump(mode="json", by_alias=True),
                "response": checked_response.model_dump(mode="json", by_alias=True),
            }
        ),
        by_alias=True,
        by_name=False,
    )


def format_first_ball_calculation(
    request: CombinedRequest,
    response: CombinedSuccess,
    *,
    artifact_sha256: str,
) -> str:
    """既要求/成功の全値をJSONへ写す。数学的な正しさや出所は推定しない。

    Args:
        request: 呼出側が取得した既初球要求。
        response: 同じ評価から得るべき既成功値。
        artifact_sha256: 呼出側が明示する実artifact hash。

    Returns:
        閉形式のJSON。DB/HTTPへの保存は行わない。

    Raises:
        FirstBallProjectionError: 型/形状/表現が不正な場合。
    """
    try:
        value = _frame(request, response, artifact_sha256)
        return _canonical_json(value.model_dump(mode="json", by_alias=True))
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise FirstBallProjectionError(_ERROR) from None


def read_first_ball_calculation(
    raw: str,
    *,
    expected_request: CombinedRequest,
    expected_response: CombinedSuccess,
    expected_artifact_sha256: str,
) -> FirstBallCalculationValue:
    """独立に供給された期待pair/hashと全値比較して読み戻す。

    Args:
        raw: 取得した閉JSON。raw自身を期待値として信頼しない。
        expected_request: 真正性を呼出側が確認すべき既要求。
        expected_response: 同一評価の取得を呼出側が確認すべき既成功値。
        expected_artifact_sha256: 呼出側が確認する実artifact hash。

    Returns:
        全値一致した独立object。認可/数学/保存の証明ではない。

    Raises:
        FirstBallProjectionError: raw又は期待値の形式不正・全値不一致の場合。
    """
    try:
        if type(raw) is not str:
            raise TypeError("JSON文字列が必要")
        expected = _frame(expected_request, expected_response, expected_artifact_sha256)
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        actual = FirstBallCalculationValue.model_validate_json(
            raw, by_alias=True, by_name=False
        )
        actual_json = _canonical_json(actual.model_dump(mode="json", by_alias=True))
        if _canonical_json(wire) != actual_json:
            raise ValueError("wireの型又は別名が不一致")
        if actual_json != _canonical_json(
            expected.model_dump(mode="json", by_alias=True)
        ):
            raise ValueError("取得値が期待全値と不一致")
        return actual
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise FirstBallProjectionError(_ERROR) from None
