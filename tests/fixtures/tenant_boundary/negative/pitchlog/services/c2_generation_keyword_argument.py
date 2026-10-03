"""keyword 引数名 generation を使う条件 2 の負例。"""


def caller(service, value):
    """keyword の構文名を条件 2 の候補にする。"""
    service.apply(generation=value)
