"""型解決できない Engine 引数からの DB 到達を表す負例。"""


def bypass(database):
    handle = database.connect()
    return handle.exec_driver_sql("SELECT secret FROM other_tenant")
