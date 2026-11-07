"""走者の既物理保存ラベル。唯一 T1 の再計算や新しい裁定は含まない。"""

ADVANCE_STATUS_BY_BASE_DESTINATION = {
    "1": {"2": "二進", "3": "三進", "4": "本進"},
    "2": {"3": "三進", "4": "本進"},
    "3": {"4": "本進"},
}

OUT_STATUS_BY_OBSERVED_KIND = {
    "force-out": "封殺",
    "pitcher-pickoff-out": "投手牽制死",
    "catcher-pickoff-out": "捕手牽制死",
    "caught-stealing": "盗塁死",
    "running-out": "走塁死",
}
