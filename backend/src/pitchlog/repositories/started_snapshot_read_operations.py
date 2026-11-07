"""記録画面GETだけが使う非ロック有限page関数の閉登録。"""

from dataclasses import dataclass, replace

from pitchlog.repositories.function_operations import _build_fixed_function_statement
from pitchlog.repositories.nonplay_prefix_read_operations import (
    NONPLAY_READ_OPERATIONS,
    NonplayActiveHistoryReadToken,
)
from pitchlog.repositories.ordinary_prefix_operations import (
    ORDINARY_PREFIX_OPERATIONS,
    PLAY_PREFIX_OPERATIONS,
    OrdinaryHistoryPageToken,
)
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixHistoryPageToken


@dataclass(frozen=True, slots=True)
class StartedOrdinaryHistoryPageToken(OrdinaryHistoryPageToken):
    """v1通常履歴をGET専用関数で読む。"""

    @property
    def capability_id(self) -> str:
        """固定readonly能力だけを返す。"""
        return "CAP:started_snapshot:read_started_ordinary_history_page"


@dataclass(frozen=True, slots=True)
class StartedPlayPrefixHistoryPageToken(PlayPrefixHistoryPageToken):
    """v2/v3履歴をGET専用関数で読む。"""

    @property
    def capability_id(self) -> str:
        """固定readonly能力だけを返す。"""
        return "CAP:started_snapshot:read_started_play_prefix_history_page"


@dataclass(frozen=True, slots=True)
class StartedNonplayActiveHistoryReadToken(NonplayActiveHistoryReadToken):
    """非play active履歴をGET専用関数で読む。"""

    @property
    def capability_id(self) -> str:
        """固定readonly能力だけを返す。"""
        return "CAP:started_snapshot:read_started_nonplay_active_history"


def _readonly_registration(base, name, token):
    """元関数の入出力とdecoderを一切変更せず別identityに閉じる。"""
    return replace(
        base,
        operation_id=f"STARTED_SNAPSHOT:{name}",
        capability_id=f"CAP:started_snapshot:{name}",
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


STARTED_SNAPSHOT_READ_OPERATIONS = (
    _readonly_registration(
        ORDINARY_PREFIX_OPERATIONS[2],
        "read_started_ordinary_history_page",
        StartedOrdinaryHistoryPageToken,
    ),
    _readonly_registration(
        PLAY_PREFIX_OPERATIONS[2],
        "read_started_play_prefix_history_page",
        StartedPlayPrefixHistoryPageToken,
    ),
    _readonly_registration(
        NONPLAY_READ_OPERATIONS[0],
        "read_started_nonplay_active_history",
        StartedNonplayActiveHistoryReadToken,
    ),
)
