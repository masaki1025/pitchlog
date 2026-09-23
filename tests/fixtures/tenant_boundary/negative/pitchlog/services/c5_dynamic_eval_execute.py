"""eval による DB API 到達の負例。"""


def bypass(session: object, statement: object) -> object:
    """Session.execute を eval で解決する。"""
    return eval("session.execute")(statement)  # noqa: S307
