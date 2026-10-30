"""初球tenant球種の未登録read宣言と純粋結果検査。global結果は保証しない。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

from sqlalchemy import Integer, Table, Text, Uuid, bindparam, select

from pitchlog.db.tenant_isolation.models import TenantVocabulary
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_ERROR = "初球球種の読取入力又は結果が不正です"
_TABLE = cast(Table, TenantVocabulary.__table__)
_COLUMNS = ("key", "category", "disabled")
_READ = (
    select(*(_TABLE.c[name] for name in _COLUMNS))
    .where(_TABLE.c.tenant_id == bindparam("tenant_id", type_=Uuid(as_uuid=True)))
    .where(_TABLE.c.key == bindparam("pitch_type_key", type_=Text))
    .limit(bindparam("limit", type_=Integer))
)


class FirstBallVocabularyError(ValueError):
    """入力やDB値を例外メッセージへ含めない固定の境界拒否。"""


def _key(value: object) -> str:
    """元の文字列を修復せず検査する。"""
    if type(value) is not str or not value:
        raise FirstBallVocabularyError(_ERROR)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class TenantPitchTypeReadToken(TenantOperationToken):
    """球種keyだけを持つ未登録値。tenantと上限は外部入力で受けない。"""

    pitch_type_key: str
    _capability: ClassVar[str] = "CAP:tenant_vocabularies:read"

    def __post_init__(self) -> None:
        """空値や派生型を暗黙変換しない。"""
        _key(getattr(self, "pitch_type_key", None))

    @property
    def capability_id(self) -> str:
        """既capabilityの識別だけを返し、実行資格を作らない。"""
        return self._capability


def _prepare_read(token: TenantOperationToken) -> PreparedOperation:
    """exact型と使用時の元keyを検査し、固定上限だけを添える。"""
    if type(token) is not TenantPitchTypeReadToken:
        raise FirstBallVocabularyError(_ERROR)
    token.__post_init__()
    return _READ, {"pitch_type_key": token.pitch_type_key, "limit": 2}


# 正式registry/資産の受理までは、実executorへ登録しない。
_UNREGISTERED_TENANT_PITCH_TYPES = (
    OperationRegistration(
        TenantPitchTypeReadToken,
        "CAP:tenant_vocabularies:read",
        _READ,
        _TABLE.c.tenant_id,
        _prepare_read,
        required_limit_parameter="limit",
        required_limit_max=2,
    ),
)


def is_enabled_tenant_pitch_type(
    result: TenantOperationResult, expected_key: str
) -> bool:
    """同tenant球種の有効性だけを検査し、保存やglobal結果を認定しない。

    Args:
        result: 登録readが返すべき不変な3列の結果。
        expected_key: 記録員が提示した元の球種key。

    Returns:
        一意な球種行が有効ならTrue。欠落・無効・別カテゴリはFalse。

    Raises:
        FirstBallVocabularyError: 実行器の結果形や元keyが不一致の場合。
    """
    expected_key = _key(expected_key)
    if type(result) is not TenantOperationResult:
        raise FirstBallVocabularyError(_ERROR)
    rows = getattr(result, "rows", None)
    if type(rows) is not tuple or len(rows) > 1:
        raise FirstBallVocabularyError(_ERROR)
    if not rows:
        return False
    row = rows[0]
    if (
        type(row) is not tuple
        or len(row) != 3
        or type(row[0]) is not str
        or row[0] != expected_key
        or type(row[1]) is not str
        or type(row[2]) is not bool
    ):
        raise FirstBallVocabularyError(_ERROR)
    return row[1] == "pitch_type" and row[2] is False
