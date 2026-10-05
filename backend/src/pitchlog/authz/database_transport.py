"""アプリ用 DB 接続の通信経路を検証する。"""

import ipaddress
import os
from collections.abc import Mapping

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


class DatabaseTransportConfigurationError(ValueError):
    """DB 接続の通信経路が安全に確定できない状態を表す。"""


def _local_endpoint(value: object, *, allow_socket: bool) -> bool:
    """明示した接続先が同一ホストに閉じるか判定する。

    絶対パスの UNIX ドメインソケット、IPv4 の 127.0.0.0/8、IPv6 の
    ::1 だけをローカルとする。localhost は名前解決に依存するため含めない。

    Args:
        value: libpq が受け取る host または hostaddr。
        allow_socket: host の UNIX ドメインソケットを許可するか。

    Returns:
        すべての接続先が上記の範囲なら True。
    """
    if not isinstance(value, str) or not value:
        return False
    for endpoint in value.split(","):
        if endpoint.startswith("/"):
            if not allow_socket:
                return False
            continue
        try:
            if not ipaddress.ip_address(endpoint).is_loopback:
                return False
        except ValueError:
            return False
    return True


def require_database_transport(
    normalized_url: str, connect_args: Mapping[str, object]
) -> None:
    """実際に libpq へ渡す通信設定を検証する。

    SQLAlchemy の psycopg dialect が正規化後 URL から作る接続引数へ
    ``connect_args`` を上書きし、実際の優先順位で判定する。ローカルは
    明示した UNIX ドメインソケットの絶対パス、127.0.0.0/8、::1 のみ。
    localhost・接続先の省略・service 経由はローカルと判定しない。
    リモートは sslmode=verify-full と gssencmode=disable を要求する。

    Args:
        normalized_url: psycopg 3 用に正規化済みの SQLAlchemy URL。
        connect_args: engine 生成時に渡す追加の psycopg 接続引数。

    Raises:
        DatabaseTransportConfigurationError: 接続先や証明書検証を
            安全に確定できない場合。例外に接続文字列は含めない。
    """
    try:
        url = make_url(normalized_url)
        _, url_parameters = url.get_dialect()().create_connect_args(url)
    except (SQLAlchemyError, TypeError, ValueError, KeyError):
        raise DatabaseTransportConfigurationError(
            "DB 接続の通信設定を解釈できない"
        ) from None
    parameters = {**url_parameters, **connect_args}
    mode = parameters.get("sslmode")
    if mode is None:
        raise DatabaseTransportConfigurationError("DB 接続には sslmode の明示が必要")

    if mode == "verify-full":
        if parameters.get("gssencmode") != "disable":
            raise DatabaseTransportConfigurationError(
                "DB の TLS 接続には gssencmode=disable が必要"
            )
        return

    if mode != "disable":
        raise DatabaseTransportConfigurationError(
            "DB 接続はローカルか証明書検証付き TLS に限る"
        )

    if (
        parameters.get("service")
        or parameters.get("servicefile")
        or os.environ.get("PGSERVICE")
        or os.environ.get("PGHOSTADDR")
    ):
        raise DatabaseTransportConfigurationError(
            "ローカル DB 接続では接続先の外部上書きを使用できない"
        )
    host = parameters.get("host")
    hostaddr = parameters.get("hostaddr")
    if not _local_endpoint(host, allow_socket=True) or (
        hostaddr is not None and not _local_endpoint(hostaddr, allow_socket=False)
    ):
        raise DatabaseTransportConfigurationError(
            "DB 接続はローカルか証明書検証付き TLS に限る"
        )
