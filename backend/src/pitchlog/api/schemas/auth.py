"""チームのログイン要求と応答を定義する。"""

from typing import Literal

from pitchlog.api.schemas.base import BaseSchema


class LoginRequest(BaseSchema):
    """チーム名とパスワードを受け取る。"""

    team_name: str
    password: str


class LoginResponse(BaseSchema):
    """提示値を含めずにログインの成功を伝える。"""

    status: Literal["authenticated"] = "authenticated"
