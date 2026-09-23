"""動的型への object.__new__ を表す負例。"""


def forge(context):
    return object.__new__(type(context))
