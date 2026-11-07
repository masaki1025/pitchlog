"""旧試行照会の既二値だけを表す。ACKや同期済み化の根拠ではない。"""

from typing import Literal

from pydantic import ConfigDict

from pitchlog.api.schemas.base import BaseSchema


class AttemptRecoveryResponse(BaseSchema):
    """元要求の照合再送許可または未解決だけを返す閉応答。"""

    model_config = ConfigDict(strict=True)

    resolution: Literal["retry_allowed", "unresolved"]
