"""パッケージの公開状態を検証する。"""

import pitchlog


def test_package_can_be_imported() -> None:
    """パッケージを import できることを確認する。"""
    assert pitchlog.__name__ == "pitchlog"
