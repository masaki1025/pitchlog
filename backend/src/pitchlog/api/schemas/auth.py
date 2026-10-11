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


class PasswordChangeRequest(BaseSchema):
    """現行パスワードと新しいパスワードを受け取る。"""

    current_password: str
    new_password: str


class PasswordChangeResponse(BaseSchema):
    """新しい提示値を含めずに変更の成功を伝える。"""

    status: Literal["password_changed"] = "password_changed"


class LogoutResponse(BaseSchema):
    """ログアウトの完了を伝える。"""

    status: Literal["logged_out"] = "logged_out"
