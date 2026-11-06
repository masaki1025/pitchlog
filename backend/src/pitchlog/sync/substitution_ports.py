"""交代の内容評価と保存投影をE1核へ閉じた参照で接続する。"""

from dataclasses import dataclass
from typing import final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter


@dataclass(frozen=True, slots=True)
class ValidateSubstitutionToken(TenantOperationToken):
    """同event・同writerの内容段だけを指す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent
    writer: PortWriter

    @property
    def capability_id(self):
        """交代内容検査の限定能力。"""
        return "CAP:sync_nonplay:validate_substitution"


@dataclass(frozen=True, slots=True)
class ProjectSubstitutionToken(TenantOperationToken):
    """同TXで一回の保存投影だけを指す。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent
    writer: PortWriter

    @property
    def capability_id(self):
        """交代投影の限定能力。"""
        return "CAP:sync_nonplay:project_substitution"


@final
class SubstitutionContentValidationPort:
    """実host評価済み結果だけを核のcontentへ渡す。"""

    def validate(self, event: SyncEvent, writer: PortWriter) -> tuple[bool, str | None]:
        """不明応答と拒否を混同しない。"""
        result = writer.run(
            ValidateSubstitutionToken(
                UUID(event.game_id), UUID(event.d5), event, writer
            )
        )
        if (
            type(result) is not TenantOperationResult
            or type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 2
            or type(result.rows[0][0]) is not bool
        ):
            raise RuntimeError("交代内容応答形が不一致です")
        accepted, reason = result.rows[0]
        if accepted is True and reason is None:
            return True, None
        if (
            accepted is False
            and type(reason) is str
            and reason == "交代内容が保存済み原本または実評価値と不一致"
        ):
            return False, reason
        raise RuntimeError("交代内容応答値が不一致です")


@final
class SubstitutionProjectionPort:
    """核の元event挿入後だけ実SQLを一回消費する。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """SQL応答の真値以外を保存成功にしない。"""
        result = writer.run(
            ProjectSubstitutionToken(UUID(event.game_id), UUID(event.d5), event, writer)
        )
        if (
            type(result) is not TenantOperationResult
            or result.rows != ((True,),)
            or type(result.rows[0][0]) is not bool
        ):
            raise RuntimeError("交代投影応答が不一致です")
