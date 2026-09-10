"""ORM モデル共通の宣言的基底を定義する。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """全 ORM モデルが継承する宣言的基底。"""
