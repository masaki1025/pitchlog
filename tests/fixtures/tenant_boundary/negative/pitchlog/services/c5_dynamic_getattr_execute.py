"""getattr と文字列連結による DB API 到達の負例。"""


def bypass(session: object, statement: object) -> object:
    """Session.execute を動的に解決する。"""
    run = getattr(session, "exe" + "cute")
    return run(statement)
