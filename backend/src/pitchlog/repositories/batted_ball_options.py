"""閉じた打球語彙readをtenant注入付き固定関数へ束縛する。"""

from dataclasses import dataclass

from pitchlog.api.schemas.batted_ball_options import BattedBallOptionsRequest
from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken


@dataclass(frozen=True, slots=True)
class BattedBallOptionsToken(TenantOperationToken):
    """tenant/categoryを受けず、件数と復号済みkeyだけを持つ。"""

    page_size: int = 20
    cursor_key: str = ""

    def __post_init__(self) -> None:
        """初回の空key以外は元文字列を保ち、型と件数を使用時も検査する。"""
        if type(self.page_size) is not int or type(self.cursor_key) is not str:
            raise ValueError("打球語彙ページの型が不正")
        BattedBallOptionsRequest(limit=self.page_size)
        if "\x00" in self.cursor_key:
            raise ValueError("打球語彙ページの位置が不正")

    @property
    def capability_id(self) -> str:
        """共通実行器の資格照合時にも強制書換えを拒否する。"""
        self.__post_init__()
        return "CAP:recording_vocabularies:read"


def _identity(result: TenantOperationResult) -> TenantOperationResult:
    """共通exact結果型の検査を迂回せず、そのまま返す。"""
    return result


# 正式registry/ACLへの登録はrootが独立採否後に行う。
BATTED_BALL_OPTIONS_OPERATIONS = (
    FunctionOperationRegistration(
        operation_id="RECORDING_VOCABULARIES:read_batted_ball_options",
        token_type=BattedBallOptionsToken,
        capability_id="CAP:recording_vocabularies:read",
        function_id="recording_vocab_api.read_batted_ball_options",
        statement=_build_fixed_function_statement(
            "recording_vocab_api",
            "read_batted_ball_options",
            (("page_size", int), ("cursor_key", str)),
            ("key", "display_name"),
            True,
        ),
        input_fields=(("page_size", int), ("cursor_key", str)),
        result_fields=(("key", str), ("display_name", str)),
        min_rows=0,
        max_rows=101,
        decoder=_identity,
    ),
)
