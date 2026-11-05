"""有効な打球語彙の閉じたページ要求と表示値を定義する。"""

from pydantic import Field

from pitchlog.api.schemas.base import BaseSchema
from pitchlog.api.schemas.games import PreparationOptionsRequest


class BattedBallOptionsRequest(PreparationOptionsRequest):
    """既ページと同じ正準key cursor・1..100件の要求。"""


class BattedBallOption(BaseSchema):
    """実admin語彙のキーと表示名だけを返す。"""

    key: str = Field(strict=True, min_length=1)
    display_name: str = Field(strict=True, min_length=1)
