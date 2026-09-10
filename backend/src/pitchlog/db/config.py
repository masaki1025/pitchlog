"""データベース設定値の共通検証を提供する。"""


class DatabaseConfigurationError(Exception):
    """データベース設定が安全に解釈できない状態を表す。"""


def require_database_configuration(variable_name: str, value: str | None) -> str:
    """必須のデータベース設定値を検証する。

    Args:
        variable_name: 設定を供給する環境変数名。
        value: 環境から取得済みの値。

    Returns:
        空でない設定値。

    Raises:
        DatabaseConfigurationError: 設定値が未設定または空の場合。
    """
    if value is None or not value:
        raise DatabaseConfigurationError(
            f"必須のデータベース設定が未設定または空: {variable_name}"
        )
    return value
