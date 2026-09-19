"""importlib による DB driver 到達の負例。"""

import importlib


def bypass(url: str) -> object:
    """psycopg を動的 import して接続する。"""
    driver = importlib.import_module("psycopg")
    return driver.connect(url)
