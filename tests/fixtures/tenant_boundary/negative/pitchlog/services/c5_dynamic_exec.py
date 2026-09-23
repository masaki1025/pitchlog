"""exec による DB API 到達の負例。"""


def bypass() -> None:
    """Session.execute 呼び出しを動的コードとして実行する。"""
    exec("session.execute(statement)")  # noqa: S102
