"""動的 import と getattr による psycopg 到達の負例。"""


def bypass(url: str) -> object:
    """psycopg.connect を動的に解決する。"""
    driver = __import__("psyco" + "pg")
    return getattr(driver, "connect")(url)
