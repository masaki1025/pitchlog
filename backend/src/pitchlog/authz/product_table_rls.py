"""製品表のRLS有効化SQLを決定的に生成する。"""

from __future__ import annotations

_IDENTIFIER_INITIALS = "abcdefghijklmnopqrstuvwxyz_"
_IDENTIFIER_CHARACTERS = f"{_IDENTIFIER_INITIALS}0123456789"


def generate_product_table_rls_sql(table_id: str) -> str:
    """単一のpublic表にENABLEとFORCEを設定するSQLを返す。

    Args:
        table_id: PostgreSQLの引用不要な小文字表識別子。

    Returns:
        要素ヘッダーを含む決定的なSQL本文。

    Raises:
        ValueError: 表識別子が閉じた字句規則に合わない場合。
    """
    if (
        not table_id
        or table_id[0] not in _IDENTIFIER_INITIALS
        or any(character not in _IDENTIFIER_CHARACTERS for character in table_id)
    ):
        raise ValueError(f"表識別子が不正: {table_id!r}")
    return (
        "-- ELEMENT-TYPE: table\n"
        f"-- ELEMENT-ID: {table_id}\n"
        "\n"
        f"ALTER TABLE public.{table_id}\n"
        "    ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE public.{table_id}\n"
        "    FORCE ROW LEVEL SECURITY;\n"
    )
