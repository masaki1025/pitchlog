"""非ロック閲覧scopeだけが使う有限page関数の閉登録。"""

from dataclasses import dataclass, replace

from pitchlog.repositories.function_operations import _build_fixed_function_statement
from pitchlog.repositories.nonplay_prefix_read_operations import (
    NONPLAY_READ_OPERATIONS,
    NonplayActiveHistoryReadToken,
)
from pitchlog.repositories.ordinary_prefix_operations import PLAY_PREFIX_OPERATIONS
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixHistoryPageToken


@dataclass(frozen=True, slots=True)
class ViewerPlayPrefixHistoryPageToken(PlayPrefixHistoryPageToken):
    """v3保存pageをRR READ ONLYからのみ読む。"""

    _capability_id = "CAP:sync_play_prefix:read_viewer_play_prefix_history_page"


@dataclass(frozen=True, slots=True)
class ViewerNonplayActiveHistoryReadToken(NonplayActiveHistoryReadToken):
    """非play保存pageをRR READ ONLYからのみ読む。"""

    @property
    def capability_id(self) -> str:
        """writer側関数と別の有限能力を返す。"""
        return "CAP:sync_ordinary_pitch:read_viewer_nonplay_active_history"


def _viewer_registration(base, name, token, family):
    """既pageの入出力型・件数・decoderをそのまま閉宣言へ移す。"""
    capability = (
        "sync_play_prefix" if family == "SYNC_PLAY_PREFIX" else "sync_ordinary_pitch"
    )
    return replace(
        base,
        operation_id=f"{family}:{name}",
        capability_id=f"CAP:{capability}:{name}",
        token_type=token,
        function_id=f"sync_right_api.{name}",
        statement=_build_fixed_function_statement(
            "sync_right_api",
            name,
            base.input_fields,
            tuple(field for field, _ in base.result_fields),
            True,
        ),
    )


VIEWER_READ_OPERATIONS = (
    _viewer_registration(
        PLAY_PREFIX_OPERATIONS[2],
        "read_viewer_play_prefix_history_page",
        ViewerPlayPrefixHistoryPageToken,
        "SYNC_PLAY_PREFIX",
    ),
    _viewer_registration(
        NONPLAY_READ_OPERATIONS[0],
        "read_viewer_nonplay_active_history",
        ViewerNonplayActiveHistoryReadToken,
        "SYNC_ORDINARY_PITCH",
    ),
)
