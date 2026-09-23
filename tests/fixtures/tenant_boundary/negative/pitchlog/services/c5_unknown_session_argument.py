"""型解決できない Session 引数からの DB 到達を表す負例。"""


def bypass(work):
    return work.execute("SELECT secret FROM other_tenant")
