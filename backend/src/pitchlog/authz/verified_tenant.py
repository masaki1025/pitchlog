"""署名済み提示値と DB の認証関数からテナント ID を確定する。"""

from uuid import UUID as _UUID

from sqlalchemy import Engine as _Engine
from sqlalchemy import text as _text
from sqlalchemy.exc import SQLAlchemyError as _SQLAlchemyError

from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation

__all__ = ["verify_tenant_id"]

_VERIFY_TOKEN = _text("SELECT authn.verify_token(:token_id)")


def verify_tenant_id(
    value: str, presentation: _TokenPresentation, engine: _Engine
) -> _UUID | None:
    """署名と DB の照合を通ったテナント ID だけを返す。

    DB 呼び出しはこの関数内だけに置き、署名を照合した ``decode`` の戻り値を
    そのまま引数にする。生の UUID を受け取る DB 呼び出し口は公開しない。
    ``authn.verify_token`` は有効性を照合し、成功時に利用時刻と期限を延長する。

    Args:
        value: 外部から受け取った署名付き提示値。
        presentation: 起動時に設定した鍵を保持する署名器。
        engine: アプリ用ロールで接続する SQLAlchemy engine。

    Returns:
        両方の照合に成功したときだけテナント ID。それ以外は ``None``。

    Raises:
        TypeError: 署名器が設定済みの型と異なる場合。
        RuntimeError: DB の照合を完了できない場合。入力値は例外に含めない。
    """
    if type(presentation) is not _TokenPresentation:
        raise TypeError("署名器の型が不正です")

    try:
        verified_id = presentation.decode(value)
    except ValueError:
        return None

    try:
        with engine.begin() as connection:
            result = connection.execute(_VERIFY_TOKEN, {"token_id": verified_id})
            tenant_id = result.scalar_one()
            if tenant_id is None or isinstance(tenant_id, _UUID):
                return tenant_id
            raise RuntimeError("トークンの照合結果が不正です")
    except _SQLAlchemyError:
        pass
    raise RuntimeError("トークンの照合を完了できない")
