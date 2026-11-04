# 再利用候補と根拠（2026-11-05）

- 起点は702948fcの固定候補。AGENTS.md、既TSK544/mvp-strikeout-pitches/mvp-terminal-pitches/mvp-t1-decision-contractsの限定計画を確認。新全体計画ではなく無走者4安打の操作単位。
- feature/ux1-roundtripの41d7175d、feature/ux1-undo-tsのb2ed1905のfrontend/src/domain/state.tsには4安打を含む前進deriveがある。後者の取消機構を輸入せず、前進の到達塁/得点/flagsだけを現共通核へ選別適用する。両旧核は包括的runner既定を持つため、全コピーして未観測を受理しない。
- 指定spike/ux1-mvpはGit refとして存在せず、元main/既2WTの同名ディレクトリも未確認。利用済みとはしない。rootへ実path照会済み。既2履歴の前進核は読み取り可能で、それだけで最初の共有計算差分の候補を具体化できる。
- 現state.tsはderiveOrdinary/deriveTerminal/deriveStrikeout/deriveLineupPitchからapplyCountRuleへ集約。新4安打は未対応で、既batter reachはfirstに固定。新moduleへ打順/count/履歴式を複製せず、共通核内のbase別到達/HR得点/hit flags/board差分だけを加える。
- state_transition_contract_v1.jsonの単打/二塁打/三塁打代表は無走者O0/S0/B0、HR代表は満塁。無走者HRはRBI-06・batterDestination score・4安打/flagsの既規範から独立手例を置き、既正式case登録済みとはしない。
- D07採用は二死二三塁の単打1配置だけ。今回には既走者がおらず、runnerDefaultAdvanceは3キーともnot-applicable/null。打者のbaseと走者のdefault/overrideを混同しない。
- FR-004のofficialScoringPayload/interferenceRulingは結果IDと独立の観測。no-error/not-requiredを利用者が確定した事実として要求し、未提示を既定値で補完しない。打球座標/種類/強さ/捕球選手の保存可否は既schema/共有変換に従い、数学本体が値を推定して生成しない。
- 23flagsの6true（非HR）/11true（HR）は付録Eと現23キー型に一致。塁打はbooleanで、成績数値の別式をUI/APIへ持ち込まない。
- 初回exact3の計画採用・開始許可待ち。publicAPI/artifact/contracts/同TX保存/UIは次の直列採否で扱い、pure計算だけで操作完了としない。
