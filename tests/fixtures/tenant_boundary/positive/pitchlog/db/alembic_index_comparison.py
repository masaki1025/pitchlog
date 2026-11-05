"""migration ownerの固定catalog読取だけに限定した正例。"""

from sqlalchemy import text


class PitchlogPostgresqlImpl:
    """検査器の完全修飾method署名を保持する正例。"""

    def correct_for_autogen_constraints(
        self, conn_unique_constraints, conn_indexes,
        metadata_unique_constraints, metadata_indexes,
    ):
        """SQLAのtextと既存connectionのexecuteだけを使用する。"""
        self.connection.execute(text("SELECT 1"))
