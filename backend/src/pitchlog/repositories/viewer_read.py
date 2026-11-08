"""現行RR readerと併用する、閲覧実効版の有限関数登録。"""

from dataclasses import dataclass, replace
from uuid import UUID

from pitchlog.repositories.first_ball import _identity
from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.started_snapshot_read_operations import (
    STARTED_SNAPSHOT_READ_OPERATIONS,
    StartedPlayPrefixHistoryPageToken,
)
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True)
class ViewerEffectiveVersionReadToken(TenantOperationToken):
    """同tenant/gameの現世代CP・P3・LC pointerだけを読む。"""

    game_id: UUID
    generation: int

    def __post_init__(self) -> None:
        """暗黙のUUID/int変換を許さない。"""
        if (
            type(self.game_id) is not UUID
            or type(self.generation) is not int
            or not 0 < self.generation < 2**63
        ):
            raise ValueError("閲覧版の対象が不正")

    @property
    def capability_id(self) -> str:
        """閲覧専用の固定関数能力を返す。"""
        return "CAP:sync_play_prefix:read_viewer_effective_version"


@dataclass(frozen=True, slots=True)
class ViewerPlayPrefixHistoryPageToken(StartedPlayPrefixHistoryPageToken):
    """現行RRで最新D1から旧頁へだけ進むv3有限token。"""

    @property
    def capability_id(self) -> str:
        """親のstarted専用propertyを閲覧の有限能力で上書きする。"""
        return "CAP:sync_play_prefix:read_viewer_play_prefix_history_page"

    def __post_init__(self) -> None:
        """元cursor全型と閲覧最大25件の両方を要求する。"""
        StartedPlayPrefixHistoryPageToken.__post_init__(self)
        if self.page_size > 25:
            raise ValueError("閲覧page上限が不一致")


VIEWER_READ_OPERATIONS = (
    replace(
        STARTED_SNAPSHOT_READ_OPERATIONS[1],
        operation_id="SYNC_PLAY_PREFIX:read_viewer_play_prefix_history_page",
        capability_id="CAP:sync_play_prefix:read_viewer_play_prefix_history_page",
        token_type=ViewerPlayPrefixHistoryPageToken,
        max_rows=26,
        function_id="sync_right_api.read_viewer_play_prefix_history_page",
        statement=_build_fixed_function_statement(
            "sync_right_api",
            "read_viewer_play_prefix_history_page",
            STARTED_SNAPSHOT_READ_OPERATIONS[1].input_fields,
            tuple(
                field for field, _ in STARTED_SNAPSHOT_READ_OPERATIONS[1].result_fields
            ),
            True,
        ),
    ),
    FunctionOperationRegistration(
        operation_id="SYNC_PLAY_PREFIX:read_viewer_effective_version",
        token_type=ViewerEffectiveVersionReadToken,
        capability_id="CAP:sync_play_prefix:read_viewer_effective_version",
        function_id="sync_right_api.read_viewer_effective_version",
        statement=_build_fixed_function_statement(
            "sync_right_api",
            "read_viewer_effective_version",
            (("game_id", UUID), ("generation", int)),
            ("record_json",),
            True,
        ),
        input_fields=(("game_id", UUID), ("generation", int)),
        result_fields=(("record_json", str),),
        decoder=_identity,
        min_rows=1,
        max_rows=1,
    ),
)
