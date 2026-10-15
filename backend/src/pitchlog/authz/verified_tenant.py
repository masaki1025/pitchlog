"""署名を照合した ID だけを DB の認証関数へ渡す境界を提供する。"""

from datetime import datetime as _datetime
from uuid import UUID as _UUID

from sqlalchemy import Engine as _Engine
from sqlalchemy import text as _text
from sqlalchemy.exc import SQLAlchemyError as _SQLAlchemyError

from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation

__all__ = ["verify_tenant_id", "logout_token"]

_ACTIVE_PRESENTATION: tuple[_TokenPresentation, bytes] | None = None


def _activate_presentation(presentation: _TokenPresentation) -> None:
    """起動時に検証した鍵から作った署名器を現在の唯一の署名器にする。"""
    if type(presentation) is not _TokenPresentation:
        raise TypeError("署名器の型が不正です")
    global _ACTIVE_PRESENTATION
    _ACTIVE_PRESENTATION = (presentation, presentation._key)


def verify_tenant_id(
    value: str, presentation: _TokenPresentation, engine: _Engine
) -> tuple[_UUID, _datetime] | None:
    """署名と DB の照合を通ったテナント ID と延長後の期限を返す。

    DB 呼び出しはこの関数内だけに置き、署名を照合した ``decode`` の戻り値を
    そのまま引数にする。生の UUID を受け取る DB 呼び出し口は公開しない。
    ``authn.verify_token`` は有効性を照合し、成功時に利用時刻と期限を延長する。

    Args:
        value: 外部から受け取った署名付き提示値。
        presentation: 起動時に設定した鍵を保持する署名器。
        engine: アプリ用ロールで接続する SQLAlchemy engine。

    Returns:
        両方の照合に成功したときだけテナント ID と期限。それ以外は ``None``。

    Raises:
        TypeError: 署名器が設定済みの型と異なる場合。
        RuntimeError: DB の照合を完了できない場合。入力値は例外に含めない。
    """
    if type(presentation) is not _TokenPresentation:
        raise TypeError("署名器の型が不正です")
    active = _ACTIVE_PRESENTATION
    if (
        active is None
        or presentation is not active[0]
        or presentation._key is not active[1]
    ):
        raise TypeError("設定済みの署名器ではありません")

    try:
        verified_id = presentation.decode(value)
    except ValueError:
        return None

    try:
        with engine.begin() as connection:
            result = connection.execute(
                _text(
                    "SELECT tenant_id, expires_at FROM authn.verify_token(:token_id)"
                ),
                {"token_id": verified_id},
            )
            tenant_id, expires_at = result.one()
            if tenant_id is None and expires_at is None:
                return None
            if (
                isinstance(tenant_id, _UUID)
                and isinstance(expires_at, _datetime)
                and expires_at.tzinfo is not None
                and expires_at.utcoffset() is not None
            ):
                return tenant_id, expires_at
            raise RuntimeError("トークンの照合結果が不正です")
    except _SQLAlchemyError:
        pass
    raise RuntimeError("トークンの照合を完了できない")


def logout_token(value: str, presentation: _TokenPresentation, engine: _Engine) -> None:
    """署名済み提示値から得た ID だけを使ってトークンを失効させる。

    ``authn.logout`` は void を返すため、行の有無や失効の成否を
    戻り値で区別しない。署名を照合できない提示値では DB に接続しない。

    Args:
        value: 外部から受け取った署名付き提示値。
        presentation: 起動時に設定した鍵を保持する署名器。
        engine: アプリ用ロールで接続する SQLAlchemy engine。

    Raises:
        TypeError: 署名器が設定済みの型と異なる場合。
        RuntimeError: DB の失効処理を完了できない場合。入力値は例外に含めない。
    """
    if type(presentation) is not _TokenPresentation:
        raise TypeError("署名器の型が不正です")
    active = _ACTIVE_PRESENTATION
    if (
        active is None
        or presentation is not active[0]
        or presentation._key is not active[1]
    ):
        raise TypeError("設定済みの署名器ではありません")

    try:
        verified_id = presentation.decode(value)
    except ValueError:
        return

    try:
        with engine.begin() as connection:
            connection.execute(
                _text("SELECT authn.logout(:token_id)"),
                {"token_id": verified_id},
            )
            return
    except _SQLAlchemyError:
        pass
    raise RuntimeError("トークンのログアウトを完了できない")
