"""同じT5 snapshotのDB十分統計を生成receiverへ渡す。"""

from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.play_export_primitives import (
    PrimitiveReadError,
    PrimitiveSnapshot,
    ReadPlayExportPrimitives,
    _read_call,
    _require_receipt,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.stats.generated.receiver import METRIC_IDS, receive_fact_row


@dataclass(frozen=True, slots=True)
class ReadPrimitiveTotalsToken(TenantOperationToken):
    """COUNT/pageと同じ版/Sだけを登録集計関数へ渡す。"""

    game_id: UUID
    player_id: UUID
    fact_version_id: UUID
    revision: int
    source_set_sha256: str
    model_sha256: str

    @property
    def capability_id(self):
        """登録された固定読取能力を返す。"""
        return "CAP:stats_primitives:read"


def read_primitive_totals(reader, receipt):
    """26行だけを受け取り、アプリで全eventを集計しない。"""
    if (
        type(reader) is not ReadPlayExportPrimitives
        or type(receipt) is not PrimitiveSnapshot
    ):
        raise PrimitiveReadError
    _require_receipt(reader, receipt)
    scope = receipt.scope
    operation = ReadPrimitiveTotalsToken(
        scope.game_id,
        scope.player_id,
        receipt.fact_version_id,
        receipt.revision,
        receipt.source_set_sha256,
        scope.model_sha256,
    )
    with _read_call(reader, operation, receipt=receipt):
        result = reader._handle.run(operation)
    if type(result) is not TenantOperationResult or len(result.rows) != len(METRIC_IDS):
        raise PrimitiveReadError
    values = {}
    for row in result.rows:
        if type(row) is not tuple or len(row) != 3 or row[0] in values:
            raise PrimitiveReadError
        metric, state, value = row
        values[metric] = receive_fact_row(
            {"metric_id": metric, "state": state, "value": value},
            maximum_integer_chars=reader._maximum_integer_chars,
        )
    if set(values) != set(METRIC_IDS):
        raise PrimitiveReadError
    return values
