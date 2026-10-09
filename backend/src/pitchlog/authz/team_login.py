"""チームの資格情報から署名済み提示値を発行する境界を提供する。"""

from datetime import datetime as _datetime
from functools import cache as _cache
from uuid import UUID as _UUID

from sqlalchemy import Engine as _Engine
from sqlalchemy import text as _text
from sqlalchemy.exc import SQLAlchemyError as _SQLAlchemyError

from pitchlog.authz import verified_tenant as _verified_tenant
from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation
from pitchlog.db.engine import create_database_engine as _create_database_engine

__all__ = ["get_login_connection", "login_attempt"]


@_cache
def get_login_connection() -> _Engine:
    """最初のログイン要求時にアプリ用接続資源を作り、以後共有する。"""
    return _create_database_engine()


def login_attempt(
    team_name: str,
    password: str,
    source: str,
    presentation: _TokenPresentation,
    engine: _Engine,
) -> tuple[str, _datetime] | int:
    """認証結果を署名済み提示値と期限、または待ち時間へ変換する。

    Args:
        team_name: 入力されたチーム名。
        password: 入力されたパスワード。
        source: 正規化済みの試行元。
        presentation: 起動時に設定した鍵を保持する署名器。
        engine: アプリ用ロールで接続する SQLAlchemy engine。

    Returns:
        成功時は署名済み提示値と発行期限、失敗時はミリ秒単位の待ち時間。

    Raises:
        TypeError: 署名器または入力の型が不正な場合。
        RuntimeError: 認証関数の実行または結果の検査に失敗した場合。
    """
    if type(presentation) is not _TokenPresentation:
        raise TypeError("署名器の型が不正です")
    # 起動時の署名器は verified_tenant が管理する。同じ可変状態をその都度読むことで、
    # 鍵の入れ替え後も古い署名器から発行させない。
    active = _verified_tenant._ACTIVE_PRESENTATION
    if (
        active is None
        or presentation is not active[0]
        or presentation._key is not active[1]
    ):
        raise TypeError("設定済みの署名器ではありません")
    if not all(isinstance(value, str) for value in (team_name, password, source)):
        raise TypeError("ログイン入力の型が不正です")

    try:
        with engine.begin() as connection:
            token_id, wait_ms, expires_at = connection.execute(
                _text(
                    "SELECT token_id, wait_ms, expires_at "
                    "FROM authn.login_attempt(:team_name, :password, :source)"
                ),
                {"team_name": team_name, "password": password, "source": source},
            ).one()
    except _SQLAlchemyError:
        pass
    else:
        if type(wait_ms) is not int or wait_ms < 0:
            raise RuntimeError("ログインの照合結果が不正です")
        if token_id is None:
            if expires_at is not None:
                raise RuntimeError("ログインの照合結果が不正です")
            return wait_ms
        if (
            not isinstance(token_id, _UUID)
            or wait_ms != 0
            or not isinstance(expires_at, _datetime)
            or expires_at.tzinfo is None
            or expires_at.utcoffset() is None
        ):
            raise RuntimeError("ログインの照合結果が不正です")
        return presentation.encode(token_id), expires_at
    raise RuntimeError("ログインの照合を完了できない")
