"""段階Aの規則読取をテナント束縛済み固定関数へ登録する。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import Boolean, String, Uuid, bindparam, func, select
from sqlalchemy.sql.selectable import Select

from pitchlog.db.game_state.rule_snapshot import (
    DomainValidatedRuleSnapshot,
    RuleSnapshotInvalid,
    decode_applied_rules,
)
from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

type AppliedRuleSnapshot = DomainValidatedRuleSnapshot
type RuleResolutionFailure = Literal[
    "stage_a_unsupported",
    "rule_not_available",
    "invalid_rule",
    "outcome_unconfirmed",
]

_FAILURE_STATUSES = frozenset(
    (
        "stage_a_unsupported",
        "rule_not_available",
        "invalid_rule",
        "outcome_unconfirmed",
    )
)


@dataclass(frozen=True, slots=True)
class StageARuleRequest:
    """段階Aの公開入力を不変な業務値だけに限定する。"""

    game_type_key: str
    tournament_key: str
    rule_override_present: bool

    def __post_init__(self) -> None:
        """空キーとexact型以外を生成時にも拒否する。"""
        _validate_request(self)


def _validate_request(request: StageARuleRequest) -> None:
    """強制変更後も同じ公開入力条件をSQL前に再検査する。"""
    if type(request) is not StageARuleRequest:
        raise TypeError("段階Aの公開入力型が必要")
    if (
        type(request.game_type_key) is not str
        or not request.game_type_key
        or type(request.tournament_key) is not str
        or not request.tournament_key
        or type(request.rule_override_present) is not bool
    ):
        raise ValueError("段階Aの入力型または必須キーが不正")


class RuleResolutionError(RuntimeError):
    """内部のSQLや存在情報を含めず固定4分類だけを公開する。"""

    def __init__(self, code: RuleResolutionFailure) -> None:
        """受理済みの失敗codeだけを保持する。"""
        if type(code) is not str or code not in _FAILURE_STATUSES:
            raise ValueError("未定義の規則解決失敗")
        self.code = code
        super().__init__(code)


def _restore_snapshot_json(value: ImmutableValue) -> object:
    """不変コンテナを単一codec用のJSON表現へ戻す。"""
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is MappingProxyType:
        if any(type(key) is not str for key in value):
            raise FunctionOperationError("規則応答のJSON表現が不正")
        return {key: _restore_snapshot_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_restore_snapshot_json(item) for item in value]
    raise FunctionOperationError("規則応答のJSON表現が不正")


def resolve_stage_a_rule(
    bound_transaction: _TenantTransaction, request: StageARuleRequest
) -> AppliedRuleSnapshot:
    """束縛済みscopeで規則を読み、単一codecの不変成功値を返す。

    Args:
        bound_transaction: 呼出し側が所有する実行中の実scope handle。
        request: 必須大会キーを含む不変入力。

    Returns:
        正規codecの構造・相関検証を通した規則IDと5値。

    Raises:
        TypeError: 実scopeまたは公開入力のexact型でない場合。
        ValueError: 必須キーまたは業務入力型が不正な場合。
        RuleResolutionError: 解決できない場合。scope外へ伝播させて全取消する。
    """
    # registryから本moduleをimportするため、実行器の実型は入口で遅延参照する。
    from pitchlog.repositories.transaction import _TenantTransaction

    if type(bound_transaction) is not _TenantTransaction:
        raise TypeError("束縛済みの実トランザクションが必要")
    _validate_request(request)
    try:
        result = bound_transaction.run_function(
            StageAResolveRuleToken(
                request.game_type_key,
                request.tournament_key,
                request.rule_override_present,
            )
        )
        value = result.rows[0][0]
        if type(value) is not MappingProxyType:
            raise FunctionOperationError("規則応答が不正")
        status = value["status"]
        if status == "resolved":
            payload = _restore_snapshot_json(value["rule"])
        elif type(status) is str and status in _FAILURE_STATUSES:
            raise RuleResolutionError(status)
        else:
            raise FunctionOperationError("規則応答が不正")
    except RuleResolutionError:
        raise
    except Exception:
        raise RuleResolutionError("outcome_unconfirmed") from None
    try:
        return decode_applied_rules(payload)
    except RuleSnapshotInvalid:
        raise RuleResolutionError("invalid_rule") from None
    except Exception:
        raise RuleResolutionError("outcome_unconfirmed") from None


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
