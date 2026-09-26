"""製品認可の適用・取り外しを実行する末端シンボルの正例。"""

from enum import Enum
from typing import Any

import psycopg  # ty: ignore


class ProductOperation(Enum):
    """製品認可に許可する閉じた操作種別。"""

    APPLY = "apply"
    UNAPPLY = "unapply"


def _run_product_operation(
    connection: psycopg.Connection[Any],
    operation: ProductOperation,
) -> None:
    """閉じた操作種別に対応する製品認可 DDL を実行する。"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    if operation is ProductOperation.APPLY:
        connection.commit()
    else:
        connection.rollback()
