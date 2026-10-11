"""署名済み提示値からパスワード変更を行う境界を提供する。"""

from sqlalchemy import Engine as _Engine
from sqlalchemy import text as _text
from sqlalchemy.exc import SQLAlchemyError as _SQLAlchemyError

from pitchlog.authz import verified_tenant as _verified_tenant
from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation

__all__ = ["change_password_token"]


def change_password_token(
    value: str,
    current_password: str,
    new_password: str,
    presentation: _TokenPresentation,
    engine: _Engine,
) -> bool:
    """署名を照合した ID だけでパスワード変更を試みる。

    Args:
        value: 外部から受け取った署名付き提示値。
        current_password: 現行パスワード。
        new_password: 新しいパスワード。
        presentation: 起動時に設定した鍵を保持する署名器。
        engine: アプリ用ロールで接続する SQLAlchemy engine。

    Returns:
        変更できた場合だけ True。署名または DB の拒否は False。

    Raises:
        TypeError: 署名器または入力の型が不正な場合。
        RuntimeError: DB の処理を完了できない場合。
    """
    if type(presentation) is not _TokenPresentation:
        raise TypeError("署名器の型が不正です")
    active = _verified_tenant._ACTIVE_PRESENTATION
    if (
        active is None
        or presentation is not active[0]
        or presentation._key is not active[1]
    ):
        raise TypeError("設定済みの署名器ではありません")
    if not isinstance(current_password, str) or not isinstance(new_password, str):
        raise TypeError("パスワードの型が不正です")

    try:
        verified_id = presentation.decode(value)
    except ValueError:
        return False

    try:
        with engine.begin() as connection:
            changed = connection.execute(
                _text(
                    "SELECT authn.change_password("
                    ":token_id, :current_password, :new_password)"
                ),
                {
                    "token_id": verified_id,
                    "current_password": current_password,
                    "new_password": new_password,
                },
            ).scalar_one()
            if type(changed) is bool:
                return changed
            raise RuntimeError("パスワード変更の結果が不正です")
    except _SQLAlchemyError:
        pass
    raise RuntimeError("パスワード変更を完了できない")
