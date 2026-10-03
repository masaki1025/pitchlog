"""match class pattern の keyword 名 generation を使う条件 2 の負例。"""


class State:
    """pattern 構文だけを検証するダミー型。"""


def use(value):
    """keyword pattern と capture の構文名を条件 2 の候補にする。"""
    match value:
        case State(generation=generation):
            return generation
