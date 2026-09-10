"""SQLAlchemy が受け取る PostgreSQL URL を正規化する。"""

_POSTGRESQL_SCHEME = "postgresql://"
_PSYCOPG_SCHEME = "postgresql+psycopg://"


def normalize_postgresql_url(database_url: str) -> str:
    """PostgreSQL URL のドライバを psycopg 3 に固定する。

    Args:
        database_url: SQLAlchemy に渡す PostgreSQL URL。

    Returns:
        ``postgresql+psycopg://`` を使う URL。

    Raises:
        ValueError: psycopg 以外のドライバまたは PostgreSQL 以外を指定した場合。
    """
    if database_url.startswith(_PSYCOPG_SCHEME):
        return database_url
    if database_url.startswith(_POSTGRESQL_SCHEME):
        return f"{_PSYCOPG_SCHEME}{database_url.removeprefix(_POSTGRESQL_SCHEME)}"

    scheme, separator, _ = database_url.partition("://")
    if separator and scheme.startswith("postgresql+"):
        raise ValueError(f"psycopg 以外の PostgreSQL ドライバは使用できない: {scheme}")
    raise ValueError("PostgreSQL URL は postgresql:// 形式で指定する必要がある")
