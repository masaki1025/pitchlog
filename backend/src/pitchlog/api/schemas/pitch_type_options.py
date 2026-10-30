"""有効なtenant球種のページ要求と表示値を定義する。"""

from pydantic import Field

from pitchlog.api.schemas.base import BaseSchema
from pitchlog.api.schemas.games import PreparationOptionsRequest


class PitchTypeOptionsRequest(PreparationOptionsRequest):
    """既選択肢と同じ正準key cursor・1..100件の要求。"""


class PitchTypeOption(BaseSchema):
    """実tenant球種から返すキーと表示名だけの閉じた値。"""

    key: str = Field(strict=True, min_length=1)
    display_name: str = Field(strict=True, min_length=1)
