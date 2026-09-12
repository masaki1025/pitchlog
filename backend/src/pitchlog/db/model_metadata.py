"""ORM モデルが宣言する表単位の契約メタデータを定義する。"""

from dataclasses import dataclass
from enum import StrEnum


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

    def __post_init__(self) -> None:
        """保護列と許可更新列が重複する誤った宣言を拒否する。"""
        overlap = self.protected_columns & self.allowed_update_columns
        if overlap:
            columns = ", ".join(sorted(overlap))
            raise ValueError(f"保護列と許可更新列が重複している: {columns}")
