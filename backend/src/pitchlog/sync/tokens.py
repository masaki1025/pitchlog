"""同期適用の閉じた operation token を SQL 依存なしで定義する。

ポート実装が import できるのは値型だけであり、文と登録処理は repositories 側に置く。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.sync.intent_ids import derive_sync_intent_id
from pitchlog.sync.model import SyncEvent

# 保護された初期記録権の証拠列を含めない同期読取の固定順序。
RECORDING_GENERATION_READ_COLUMNS = (
    "tenant_id",
    "game_id",
    "generation",
    "kind",
    "issuance_order",
    "holder_device",
    "confirmed_watermark",
    "applied_prefix",
    "granted_at",
    "revoked_at",
    "import_batch_id",
    "retired_at",
)

# 保護された初期記録権の証拠列を含めない同期読取の固定順序。
RECORDING_GENERATION_READ_COLUMNS = (
    "tenant_id",
    "game_id",
    "generation",
    "kind",
    "issuance_order",
    "holder_device",
    "confirmed_watermark",
    "applied_prefix",
    "granted_at",
    "revoked_at",
    "import_batch_id",
    "retired_at",
)


class _SyncToken(TenantOperationToken):
    """各 token の固定 capability を公開する。"""

    __slots__ = ()
    _capability_id = ""

    @property
    def capability_id(self) -> str:
        """登録済みの単一 capability を返す。"""
        return self._capability_id


@dataclass(frozen=True, slots=True)
class GameReadToken(_SyncToken):
    """認可後の対象試合を読む。"""

    game_id: UUID
    _capability_id = "CAP:games:read"


@dataclass(frozen=True, slots=True)
class GameLockToken(_SyncToken):
    """イベント境界の最初に対象試合行をロックする。"""

    game_id: UUID
    _capability_id = "CAP:games:read"


@dataclass(frozen=True, slots=True)
class RecordingGenerationReadToken(_SyncToken):
    """要求境界で現在の記録権世代を読む。"""

    game_id: UUID
    _capability_id = "CAP:recording_generations:read"


@dataclass(frozen=True, slots=True)
class RecordingGenerationByNumberReadToken(_SyncToken):
    """要求の D4 が指す記録権世代を、失効・退役の有無によらず読む(ACK の D3)。"""

    game_id: UUID
    generation: int
    _capability_id = "CAP:recording_generations:read"


@dataclass(frozen=True, slots=True)
class RecordingGenerationLockToken(_SyncToken):
    """試合行の後に記録権世代行をロックする。"""

    game_id: UUID
    generation: int
    _capability_id = "CAP:recording_generations:read"


@dataclass(frozen=True, slots=True)
class RecordingPrefixUpdateToken(_SyncToken):
    """確定した D3 と適用済み prefix を前進させる。"""

    game_id: UUID
    generation: int
    confirmed_watermark: int
    applied_prefix: int
    _capability_id = "CAP:recording_generations:update"


@dataclass(frozen=True, slots=True)
class EventSlotReadToken(_SyncToken):
    """対象 D1 の確定版を読む。"""

    game_id: UUID
    generation: int
    d1: int
    _capability_id = "CAP:event_slots:read"


@dataclass(frozen=True, slots=True)
class EventSlotInsertToken(_SyncToken):
    """初回受理で D1 のスロットを作る。"""

    game_id: UUID
    generation: int
    d1: int
    _capability_id = "CAP:event_slots:insert"


@dataclass(frozen=True, slots=True)
class EventSlotVersionUpdateToken(_SyncToken):
    """旧版を照合して D1 の確定版を進める。"""

    game_id: UUID
    generation: int
    d1: int
    expected_version: int
    confirmed_version: int
    _capability_id = "CAP:event_slots:update"


@dataclass(frozen=True, slots=True)
class OperationEventReadToken(_SyncToken):
    """対象スロットの現行イベントを読む。"""

    game_id: UUID
    generation: int
    d1: int
    _capability_id = "CAP:operation_events:read"


@dataclass(frozen=True, slots=True)
class OperationEventOrderReadToken(_SyncToken):
    """局所再採番に必要な同一試合の D2 順の有限範囲を読む。"""

    game_id: UUID
    after_d2: int
    limit: int
    _capability_id = "CAP:operation_events:read"


@dataclass(frozen=True, slots=True)
class OperationEventInsertToken(_SyncToken):
    """受理済みイベントの不変内容を保存する。"""

    id: UUID
    game_id: UUID
    d5: UUID
    event_kind: str
    payload_json: str
    generation: int | None = None
    d1: int | None = None
    d2: int | None = None
    state_diff_json: str | None = None
    is_tombstone: bool = False
    target_generation: int | None = None
    target_d1: int | None = None
    expected_version: int | None = None
    change_order: int | None = None
    _capability_id = "CAP:operation_events:insert"


@dataclass(frozen=True, slots=True)
class OperationEventOrderUpdateToken(_SyncToken):
    """既存イベントの D2 を局所再採番する。"""

    id: UUID
    d2: int
    _capability_id = "CAP:operation_events:update"


@dataclass(frozen=True, slots=True)
class OperationEventReplaceToken(_SyncToken):
    """現行イベントを置換済みにする。"""

    id: UUID
    replaced_at: datetime
    _capability_id = "CAP:operation_events:update"


@dataclass(frozen=True, slots=True)
class TemporaryPlayerMappingReadToken(_SyncToken):
    """再送時に一時 ID の確定写像を読む。"""

    temporary_id: UUID
    _capability_id = "CAP:temporary_player_id_mappings:read"


@dataclass(frozen=True, slots=True)
class TemporaryPlayerMappingInsertToken(_SyncToken):
    """選手登録の一時 ID と正式 ID を同じ境界へ保存する。"""

    id: UUID
    temporary_id: UUID
    player_id: UUID
    _capability_id = "CAP:temporary_player_id_mappings:insert"


@dataclass(frozen=True, slots=True)
class IdempotencyLedgerReadToken(_SyncToken):
    """D5 の保存済み結果と原本の指紋を読む。"""

    d5: UUID
    _capability_id = "CAP:idempotency_ledger:read"


@dataclass(frozen=True, slots=True)
class IdempotencyLedgerInsertToken(_SyncToken):
    """D5 と確定結果を一度の INSERT で保存する。"""

    d5: UUID
    kind: str
    source_fingerprint: str
    result_json: str
    reason: str | None = None
    _capability_id = "CAP:idempotency_ledger:insert"


@dataclass(frozen=True, slots=True)
class RejectedOriginalReadToken(_SyncToken):
    """拒否された D5 の原本を再掲する。"""

    d5: UUID
    _capability_id = "CAP:rejected_event_originals:read"


@dataclass(frozen=True, slots=True)
class RejectedOriginalInsertToken(_SyncToken):
    """未使用 D5 の内容拒否原本を保存する。"""

    id: UUID
    d5: UUID
    payload_json: str
    _capability_id = "CAP:rejected_event_originals:insert"


@dataclass(frozen=True, slots=True)
class InvalidationIntentReadToken(_SyncToken):
    """確定済みの意図の配信状態を読む。"""

    intent_id: str
    _capability_id = "CAP:invalidation_intents:read"


@dataclass(frozen=True, slots=True)
class InvalidationIntentPendingToken(_SyncToken):
    """未配信意図を有界の一覧で読む。"""

    limit: int
    after_intent_id: str = ""
    _capability_id = "CAP:invalidation_intents:read"

    def __post_init__(self) -> None:
        """キーセットカーソルを文字列に限る。"""
        if type(self.after_intent_id) is not str:
            raise ValueError("意図 ID のカーソルは文字列が必要")


@dataclass(frozen=True, slots=True)
class SyncInvalidationIntentInsertToken(_SyncToken):
    """同期経路の①②③⑤の無効化意図を 1 行保存する。"""

    event_identity: str
    scope_kind: str
    game_id: UUID | None = None
    _capability_id = "CAP:invalidation_intents:insert"

    def __post_init__(self) -> None:
        """B03 の ID と①②③⑤の選択子の形を検査する。"""
        self.validate()

    def validate(self) -> None:
        """準備時にも凍結 token の変異を拒否する。"""
        derive_sync_intent_id(self.event_identity, self.scope_kind)
        if self.scope_kind == "game":
            if type(self.game_id) is not UUID:
                raise ValueError("試合範囲には試合 ID が必要")
        elif self.scope_kind in {"player_total", "team_total", "chart"}:
            if self.game_id is not None:
                raise ValueError("広域範囲に試合 ID を指定できない")
        else:
            raise ValueError("共有集計には専用 token が必要")

    @property
    def intent_id(self) -> str:
        """イベント識別と範囲から意図 ID を導出する。"""
        return derive_sync_intent_id(self.event_identity, self.scope_kind)


@dataclass(frozen=True, slots=True)
class SyncSharedInvalidationIntentInsertToken(_SyncToken):
    """同期経路の④共有集計を文脈テナントだけへ無効化する。"""

    event_identity: str
    _capability_id = "CAP:invalidation_intents:insert"

    def __post_init__(self) -> None:
        """B03 の共有集計意図 ID を検査する。"""
        self.validate()

    def validate(self) -> None:
        """準備時にも凍結 token の変異を拒否する。"""
        derive_sync_intent_id(self.event_identity, "shared_total")

    @property
    def intent_id(self) -> str:
        """イベント識別と④の範囲から意図 ID を導出する。"""
        return derive_sync_intent_id(self.event_identity, "shared_total")


@dataclass(frozen=True, slots=True)
class InvalidationIntentDeliveredToken(_SyncToken):
    """意図の配信完了を永続化する。"""

    intent_id: str
    delivered_at: datetime
    _capability_id = "CAP:invalidation_intents:update"


@dataclass(frozen=True, slots=True)
class EvacuatedOriginalReadToken(_SyncToken):
    """旧世代 D5 の退避原本を読む。"""

    d5: UUID
    _capability_id = "CAP:evacuated_event_originals:read"


@dataclass(frozen=True, slots=True)
class EvacuatedOriginalInsertToken(_SyncToken):
    """記録権不一致の原本を退避する。"""

    id: UUID
    game_id: UUID
    old_generation: int
    original_d1: int
    d5: UUID
    payload_json: str
    _capability_id = "CAP:evacuated_event_originals:insert"


@dataclass(frozen=True, slots=True)
class PortRG1PrecheckToken(_SyncToken):
    """Portから固定RG1読取へだけ到達する値命令。資格ではない。"""

    _capability_id = "CAP:rg1:precheck"


@dataclass(frozen=True, slots=True)
class PortRG1CommitCheckToken(_SyncToken):
    """同scopeの固定RG1確定前検査だけを要求する。"""

    _capability_id = "CAP:rg1:commit_check"


@dataclass(frozen=True, slots=True)
class PortBindCurrentDeviceToken(_SyncToken):
    """nonce等を貸与せず核が実bindingへ補う端末照合命令。"""

    credential_digest: bytes = field(repr=False)
    _capability_id = "CAP:sync_first_ball:bind_device"


@dataclass(frozen=True, slots=True)
class PortCheckCurrentRightToken(_SyncToken):
    """同bindingだけの現権利照合命令。proof値だけで資格を作らない。"""

    game_id: UUID
    wire_d4: str
    recovery_generation: int
    proof_digest: bytes = field(repr=False)
    _capability_id = "CAP:sync_first_ball:check_current_right"


@dataclass(frozen=True, slots=True)
class PortValidateFirstBallToken(_SyncToken):
    """同原eventの内容照合だけを要求する値命令。source/nonce/成功は受けない。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent = field(repr=False)
    writer: object = field(repr=False)
    _capability_id = "CAP:operation_events:read"

    def __post_init__(self) -> None:
        """正規化や同型DTOへの変換をせず、元参照を保持する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.d5) is not UUID
            or type(self.event) is not SyncEvent
            or str(self.game_id) != self.event.game_id
            or str(self.d5) != self.event.d5
        ):
            raise ValueError("初球内容命令の入力が不一致です")


@dataclass(frozen=True, slots=True)
class PortCheckPresentedRightToken(_SyncToken):
    """提示V12を未変換で核へ渡す。proof/epochを発行する資格ではない。"""

    game_id: UUID
    wire_d4: str
    raw_v12: object = field(repr=False)
    _capability_id = "CAP:sync_first_ball:check_current_right"
