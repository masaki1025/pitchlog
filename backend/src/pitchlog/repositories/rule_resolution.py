"""段階Aの規則読取をテナント束縛済み固定関数へ登録する。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from sqlalchemy import Boolean, String, Uuid, bindparam, func, select
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_FAILURE_STATUSES = frozenset(
    (
        "stage_a_unsupported",
        "rule_not_available",
        "invalid_rule",
        "outcome_unconfirmed",
    )
)


@dataclass(frozen=True, slots=True)
class StageAResolveRuleToken(TenantOperationToken):
    """任意のtenant IDやSQLを受け取らない段階A読取要求。"""

    game_type_key: str
    tournament_key: str
    has_override: bool

    @property
    def capability_id(self) -> str:
        """規則読取だけの固定capabilityを返す。"""
        return "CAP:rules:resolve_stage_a"


def _build_stage_a_rule_statement() -> Select[Any]:
    """scope注入UUIDと固定3入力で単一関数を呼び出す。"""
    return select(
        func.public.resolve_stage_a_rule(
            bindparam("tenant_id", type_=Uuid()),
            bindparam("game_type_key", type_=String()),
            bindparam("tournament_key", type_=String()),
            bindparam("has_override", type_=Boolean()),
        ).label("resolution")
    )


def _decode_stage_a_rule_result(result: TenantOperationResult) -> TenantOperationResult:
    """DB関数の閉じた外形だけを検証し、未検証の規則候補を保持する。

    規則値のcodec検証・出所受理・公開失敗分類は後続resolverの責務とする。
    この戻り値を保存可能なスナップショットとして扱わない。
    """
    if len(result.rows) != 1 or len(result.rows[0]) != 1:
        raise FunctionOperationError("段階Aの関数戻り行数または列数が不一致")
    value = result.rows[0][0]
    if type(value) is not MappingProxyType:
        raise FunctionOperationError("段階Aの関数戻り値が不変オブジェクトではない")
    status = value.get("status")
    if type(status) is not str:
        raise FunctionOperationError("段階Aの関数戻りstatusが不正")
    if status == "resolved":
        if (
            set(value) != {"status", "rule"}
            or type(value["rule"]) is not MappingProxyType
        ):
            raise FunctionOperationError("段階Aの規則候補の外形が不正")
    elif status not in _FAILURE_STATUSES or set(value) != {"status"}:
        raise FunctionOperationError("段階Aの関数戻りstatusまたは外形が不正")
    return result
