"""binding broker内部channelの固定接続だけの正例。"""

from __future__ import annotations

import socket


class BindingControl:
    """製品クラスの登録methodを表す。"""

    def _channel(self):
        """固定socket接続だけを表す。"""
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        channel.connect("/run/pitchlog-test/binding.sock")
        return channel
