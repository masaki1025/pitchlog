"""pitchlog 内の推移的 import が禁止される合成ポート。"""

from pitchlog.api.routers import players


class TransitiveProjection:
    """別の pitchlog モジュールを経て禁止 import に到達する。"""

    def apply(self) -> None:
        """検査に拒否されるため、実行されない。"""
        _ = players.router
