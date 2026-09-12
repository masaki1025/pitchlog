"""ORM モデルが宣言する表単位の契約メタデータを定義する。"""

import re
from dataclasses import dataclass
from enum import StrEnum

_TASK_HANDOFF_ID_PATTERN = re.compile(r"TSK-[0-9]+")


def is_task_handoff_id(value: str) -> bool:
    """受け取り先が実タスク ID の形式なら真を返す。"""
    return _TASK_HANDOFF_ID_PATTERN.fullmatch(value) is not None


class DeletionLifecycle(StrEnum):
    """業務オブジェクトの削除系統。"""

    TRASH = "ゴミ箱"
    HIDDEN = "非表示"
    DISABLED = "無効化"
    ENDED = "終了・離脱"
    NOT_APPLICABLE = "対象外"
    FOLLOWS_PARENT = "親に従う"


class AppendMode(StrEnum):
    """表の追記専用性。"""

    APPEND_ONLY = "追記専用"
    MUTABLE = "更新可"


class MigrationRetirement(StrEnum):
    """移行バッチ退役述語の有無。"""

    HAS_PREDICATE = "退役述語を持つ"
    NONE = "持たない"


class ImmutabilityCoverage(StrEnum):
    """不変列マトリクスによる列分類の被覆状態。"""

    EXHAUSTIVE = "exhaustive"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class Lifecycle:
    """削除・追記専用性・移行退役の独立した 3 軸。"""

    deletion: DeletionLifecycle
    append_mode: AppendMode
    migration_retirement: MigrationRetirement


@dataclass(frozen=True, slots=True)
class Immutability:
    """表の保護列と許可更新列を宣言する不変列マトリクスの一行。"""

    protected_columns: frozenset[str]
    allowed_update_columns: frozenset[str]
    coverage: ImmutabilityCoverage
    conditional_update_columns: frozenset[str] = frozenset()
    unclassified_handoff: str | None = None

    def __post_init__(self) -> None:
        """列分類の重複と被覆状態に反する受け取り先宣言を拒否する。"""
        overlap = (
            (self.protected_columns & self.allowed_update_columns)
            | (self.protected_columns & self.conditional_update_columns)
            | (self.allowed_update_columns & self.conditional_update_columns)
        )
        if overlap:
            columns = ", ".join(sorted(overlap))
            raise ValueError(f"不変列マトリクスの分類が重複している: {columns}")
        if (
            self.coverage is ImmutabilityCoverage.PARTIAL
            and not self.unclassified_handoff
        ):
            raise ValueError("部分被覆には未分類列の受け取り先が必要")
        if (
            self.coverage is ImmutabilityCoverage.EXHAUSTIVE
            and self.unclassified_handoff is not None
        ):
            raise ValueError("全列分類済みに未分類列の受け取り先は指定できない")
        if self.unclassified_handoff is not None and not is_task_handoff_id(
            self.unclassified_handoff
        ):
            raise ValueError(
                "未分類列の受け取り先 ID は TSK-<数字> 形式で指定してください"
            )
