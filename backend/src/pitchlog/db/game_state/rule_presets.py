"""画面で選んだ規定回・延長上限を既存codecの不変snapshotへ写す。

規則の計算や終了判定は行わない。段階Aで解決済みの既定規則から、利用者が
選んだ規定回と最終延長回だけを差し替え、既存の単一codecで再検証する。
"""

from __future__ import annotations

from typing import Final, Literal
from uuid import UUID, uuid5

from pitchlog.db.game_state.rule_snapshot import (
    DomainValidatedRuleSnapshot,
    RuleSnapshotFailure,
    RuleSnapshotInvalid,
    StructuralRuleSnapshot,
    TiebreakRule,
    validate_correlations,
)

type RegulationInnings = Literal[7, 9]
type ExtensionLimit = Literal[7, 9, 12]

# 画面で選べる組み合わせだけを閉じる。延長上限は「行える最終回の番号」。
_ALLOWED_CHOICES: Final = frozenset({(7, 7), (7, 9), (7, 12), (9, 9), (9, 12)})
# 派生presetのIDを再現可能にする固定名前空間。DBのrule_sets行ではない。
_PRESET_NAMESPACE: Final = UUID("0b6f9c52-6f4d-5b1e-9f3a-6d2c8a4e7b10")


class RulePresetInvalid(ValueError):
    """画面選択を既存codecへ渡せない場合の閉じた失敗。"""


def _require_choice(regulation_innings: object, extension_limit: object) -> None:
    """DTOを経ない直接呼出しでも同じ有限選択だけを受理する。"""
    if (
        type(regulation_innings) is not int
        or type(extension_limit) is not int
        or (regulation_innings, extension_limit) not in _ALLOWED_CHOICES
    ):
        raise RulePresetInvalid("選択できない規定回または延長上限")


def _preset_rule_set_id(
    base: DomainValidatedRuleSnapshot,
    regulation_innings: int,
    extension_limit: int,
) -> UUID:
    """同じ既定規則と選択から常に同じ派生IDを作る。"""
    return uuid5(
        _PRESET_NAMESPACE,
        f"{base.structural.rule_set_id}:{regulation_innings}:{extension_limit}",
    )


def _selected_structure(
    base: DomainValidatedRuleSnapshot,
    regulation_innings: int,
    extension_limit: int,
    *,
    tiebreak: TiebreakRule | None,
) -> StructuralRuleSnapshot:
    """選択値だけを差し替えた未相関検証の構造を作る。"""
    return StructuralRuleSnapshot(
        rule_set_id=_preset_rule_set_id(base, regulation_innings, extension_limit),
        regulation_innings=regulation_innings,
        cold_conditions=base.structural.cold_conditions,
        extension_limit=extension_limit,
        tiebreak=tiebreak,
        dh=base.structural.dh,
    )


def apply_rule_choice(
    base: DomainValidatedRuleSnapshot,
    *,
    regulation_innings: RegulationInnings,
    extension_limit: ExtensionLimit,
) -> DomainValidatedRuleSnapshot:
    """既定規則へ画面選択を適用し、既存codecで検証したsnapshotを返す。

    Args:
        base: 段階Aで解決済みの既定規則snapshot。
        regulation_innings: 利用者が選んだ規定回（7または9）。
        extension_limit: 利用者が選んだ最終延長回（7・9・12）。

    Returns:
        同じ規則値なら出所IDを保ったbase、値が変わる場合だけ派生IDを持つ
        検証済みsnapshot。規則行のDB出所はbaseの範囲を超えない。

    Raises:
        RulePresetInvalid: 選択値が画面の有限集合にない場合。
        RuleSnapshotInvalid: 差し替え後の値が既存codecの相関検査に反する場合。
    """
    if type(base) is not DomainValidatedRuleSnapshot:
        raise RulePresetInvalid("検証済みの既定規則が必要")
    _require_choice(regulation_innings, extension_limit)
    if (
        base.structural.regulation_innings == regulation_innings
        and base.structural.extension_limit == extension_limit
    ):
        # 既定の9回・延長上限なし等はIDも値も変更しない。
        return base
    try:
        return validate_correlations(
            _selected_structure(
                base,
                regulation_innings,
                extension_limit,
                tiebreak=base.structural.tiebreak,
            )
        )
    except RuleSnapshotInvalid as error:
        if (
            error.kind is not RuleSnapshotFailure.CORRELATION
            or base.structural.tiebreak is None
        ):
            raise
        # 既存codecが既定タイブレークを今回の上限で不成立と判定した場合だけ
        # 外す。開始回の移動や新しい相関判定はここで作らない。
        return validate_correlations(
            _selected_structure(
                base,
                regulation_innings,
                extension_limit,
                tiebreak=None,
            )
        )
