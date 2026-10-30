"""段階起動の既実装に対応する有限DB API正例。"""


from sqlalchemy import create_engine  # ty: ignore


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def _apply_writer_storage(owner_dsn: str) -> None:
        """宣言したAPIのみを固定した名前で呼ぶ。"""
        engine = create_engine("postgresql+psycopg://")
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
