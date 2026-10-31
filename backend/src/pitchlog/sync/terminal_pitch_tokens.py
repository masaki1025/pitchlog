"""v2の元参照命令/全列投影token。SQLや成功資格を受け取らない。"""

from dataclasses import dataclass, field
from uuid import UUID

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tokens import _SyncToken


@dataclass(frozen=True, slots=True)
class _PlayPrefixWriterToken(_SyncToken):
    """実writerからだけ補うnonce等の値。権限を発行しない。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID

    def __post_init__(self):
        """writer識別の型/nonce長だけを照合し、真正資格は実frameで要求する。"""
        if (
            any(
                type(v) is not UUID
                for v in (self.attempt_id, self.phase_id, self.device_id, self.game_id)
            )
            or type(self.binding_nonce) is not bytes
            or len(self.binding_nonce) != 32
        ):
            raise ValueError("v2 writer入力の型が不一致")


@dataclass(frozen=True, slots=True)
class PlayPrefixCheckpointReadToken(_SyncToken):
    """同tenant/game世代の一点読取。"""

    game_id: UUID
    generation: int
    _capability_id = "CAP:sync_play_prefix:read_play_prefix_checkpoint"

    def __post_init__(self):
        """同gameの正bigint世代へ閉じる。"""
        if (
            type(self.game_id) is not UUID
            or type(self.generation) is not int
            or not 0 < self.generation < 2**63
        ):
            raise ValueError("v2読取世代が不正")


@dataclass(frozen=True, slots=True)
class PlayPrefixCheckpointLockToken(_PlayPrefixWriterToken):
    """実writer nonce付きcheckpoint lock。"""

    generation: int

    @property
    def capability_id(self):
        """新modeの有限関数だけを指す。"""
        return "CAP:sync_play_prefix:lock_play_prefix_checkpoint"


@dataclass(frozen=True, slots=True)
class PlayPrefixHistoryPageToken(_SyncToken):
    """wire head/storage epochと有界cursorの閉入力。"""

    game_id: UUID
    generation: int
    storage_history_epoch: int
    wire_checkpoint_id: UUID
    wire_checkpoint_revision: int
    wire_history_version: int
    upper_watermark: int
    after_d1: int
    after_d2: int
    after_id: UUID
    page_size: int
    _capability_id = "CAP:sync_play_prefix:read_play_prefix_history_page"

    def __post_init__(self):
        """bool/範囲外/無制限pageを拒否する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.wire_checkpoint_id) is not UUID
            or type(self.after_id) is not UUID
            or any(
                type(x) is not int or not 0 < x < 2**63
                for x in (
                    self.generation,
                    self.storage_history_epoch,
                    self.wire_checkpoint_revision,
                    self.wire_history_version,
                )
            )
            or any(
                type(x) is not int or not 0 <= x < 2**63
                for x in (self.upper_watermark, self.after_d1, self.after_d2)
            )
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= 100
            or self.after_d1 > self.upper_watermark
        ):
            raise ValueError("v2履歴cursor又はpage上限が不正")


@dataclass(frozen=True, slots=True)
class PreparePlayPrefixProjectionToken(_PlayPrefixWriterToken):
    """私有frameから一回だけ発行するSQL準備。"""

    preparation_json: str = field(repr=False)

    @property
    def capability_id(self):
        """新modeの有限prepareだけを指す。"""
        return "CAP:sync_play_prefix:prepare_play_prefix_projection"


@dataclass(frozen=True, slots=True)
class ValidatePlayPrefixToken(_SyncToken):
    """実event/同writerだけを内容段へ返す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent = field(repr=False)
    writer: object = field(repr=False)
    _capability_id = "CAP:operation_events:read"

    def __post_init__(self):
        """UUID/元参照を変換せず照合する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.d5) is not UUID
            or type(self.event) is not SyncEvent
            or str(self.game_id) != self.event.game_id
            or str(self.d5) != self.event.d5
        ):
            raise ValueError("通常内容命令の参照が不一致")


@dataclass(frozen=True, slots=True)
class ProjectPlayPrefixToken(_SyncToken):
    """採番済み元eventの真正frame消費を要求する。"""

    game_id: UUID
    d5: UUID
    projected: SyncEvent = field(repr=False)
    writer: object = field(repr=False)
    _capability_id = "CAP:play_rows:insert"

    def __post_init__(self):
        """別game/D5/同型レコードを正規化しない。"""
        if (
            type(self.game_id) is not UUID
            or type(self.d5) is not UUID
            or type(self.projected) is not SyncEvent
            or str(self.game_id) != self.projected.game_id
            or str(self.d5) != self.projected.d5
        ):
            raise ValueError("通常投影命令の参照が不一致")


@dataclass(frozen=True, slots=True)
class PlayPrefixPlayRowInsertToken(_SyncToken):
    """実原本メタ値と41列だけのINSERT入力。"""

    game_id: UUID
    generation: int
    d1: int
    d2: int
    d5: UUID
    source_fingerprint: str
    row_json: str = field(repr=False)
    _capability_id = "CAP:play_rows:insert"
