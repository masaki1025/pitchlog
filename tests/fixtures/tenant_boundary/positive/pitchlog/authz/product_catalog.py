"""製品認可のカタログ問い合わせを実行する末端シンボルの正例。"""

from enum import Enum
from typing import Any

import psycopg  # ty: ignore


class CatalogQueryId(Enum):
    """製品認可のカタログ検査に許可する問い合わせ ID。"""

    CURRENT_USER = "current_user"


_CATALOG_QUERIES = {
    CatalogQueryId.CURRENT_USER: "SELECT current_user",
}


def _fetch_catalog_rows(
    connection: psycopg.Connection[Any],
    query_id: CatalogQueryId,
    params: tuple[object, ...],
) -> list[tuple[object, ...]]:
    """閉じた問い合わせ ID に対応する行を読み取る。"""
    with connection.cursor() as cursor:
        cursor.execute(_CATALOG_QUERIES[query_id], params)
        return [tuple(row) for row in cursor]
