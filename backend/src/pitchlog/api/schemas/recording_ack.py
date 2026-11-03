"""D1付き記録応答の既存wire形状を閉じたDTOで表す。"""

from typing import Annotated

from pydantic import ConfigDict, Field, StrictInt, StrictStr

from pitchlog.api.schemas.base import BaseSchema
from pitchlog.sync.model import A5State


class _RecordingAckSchema(BaseSchema):
    """型変換や余剰キーを許さない応答の共通形。"""

    model_config = ConfigDict(strict=True)


class RecordingEventResult(_RecordingAckSchema):
    """イベントの識別値と既存の確定状態だけを返す。"""

    d4: StrictStr
    d1: Annotated[StrictInt, Field(ge=1)]
    d5: StrictStr
    a5_result: A5State = Field(alias="a5Result")


class RecordingPlayerIdMapping(_RecordingAckSchema):
    """その場登録の一時識別値と正式識別値の対応を返す。"""

    temporary_id: StrictStr = Field(alias="temporaryId")
    official_id: StrictStr = Field(alias="officialId")


class RecordingAckResponse(_RecordingAckSchema):
    """前進位置とイベント結果、存在するときだけ登録対応を返す。"""

    advanced_d3: Annotated[StrictInt, Field(ge=0)] = Field(alias="advancedD3")
    event_results: list[RecordingEventResult] = Field(alias="eventResults")
    player_id_mappings: list[RecordingPlayerIdMapping] = Field(
        default_factory=list, alias="playerIdMappings"
    )
