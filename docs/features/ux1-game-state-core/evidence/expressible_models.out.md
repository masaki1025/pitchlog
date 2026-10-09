# expressible_models.py の実行結果

- schema 検証(`model.schema.json`・生成コアの検証器): **通過**
- 生成前検査(実行した系統: display-primitive-parameters, explicit-division-rounding, numeric-value-display-atom-boundary, transition-coverage-determinism, type-and-integer-range): **通過**

## 導出規則(遷移の同時代入)

### c1ThirdOutChange
- 遷移 `applyOut`(イベント `outRecorded`・`guardRefs` = 空)
  - `s.outs` ← `((s.outs + e.delta)*(1 - max(0, min(1, (((s.outs + e.delta) - 3) + 1)))))`
  - `s.half` ← `((s.half + max(0, min(1, (((s.outs + e.delta) - 3) + 1)))) - (2*s.half*max(0, min(1, (((s.outs + e.delta) - 3) + 1)))))`
  - `s.inning` ← `(s.inning + (max(0, min(1, (((s.outs + e.delta) - 3) + 1)))*s.half))`

### c2DroppedThirdStrike
- 遷移 `judgeDroppedThirdStrike`(イベント `pitch`・`guardRefs` = 空)
  - `s.outs` ← `s.outs`
  - `s.firstOccupied` ← `s.firstOccupied`
  - `s.batterMayRun` ← `(e.thirdStrike*(1 - e.caught)*(((1 - min(1, max((s.outs - 2), (2 - s.outs)))) + (1 - s.firstOccupied)) - ((1 - min(1, max((s.outs - 2), (2 - s.outs))))*(1 - s.firstOccupied))))`

### c9BattingOrderWrap
- 遷移 `advanceBattingOrder`(イベント `plateAppearanceCompleted`・`guardRefs` = 空)
  - `s.battingOrder` ← `((s.battingOrder + 1) - (9*(1 - min(1, max((s.battingOrder - 9), (9 - s.battingOrder))))))`

### c14ColdSegments
- 遷移 `scoreAndJudgeCold`(イベント `playConfirmed`・`guardRefs` = 空)
  - `s.home` ← `(s.home + e.homeRuns)`
  - `s.away` ← `(s.away + e.awayRuns)`
  - `s.inning` ← `s.inning`
  - `s.coldReached` ← `max(s.coldReached, (((in.segment1Active*max(0, min(1, ((max(((s.home + e.homeRuns) - (s.away + e.awayRuns)), ((s.away + e.awayRuns) - (s.home + e.homeRuns))) - in.segment1Lead) + 1)))*max(0, min(1, ((s.inning - in.segment1Inning) + 1)))) + (in.segment2Active*max(0, min(1, ((max(((s.home + e.homeRuns) - (s.away + e.awayRuns)), ((s.away + e.awayRuns) - (s.home + e.homeRuns))) - in.segment2Lead) + 1)))*max(0, min(1, ((s.inning - in.segment2Inning) + 1))))) - ((in.segment1Active*max(0, min(1, ((max(((s.home + e.homeRuns) - (s.away + e.awayRuns)), ((s.away + e.awayRuns) - (s.home + e.homeRuns))) - in.segment1Lead) + 1)))*max(0, min(1, ((s.inning - in.segment1Inning) + 1))))*(in.segment2Active*max(0, min(1, ((max(((s.home + e.homeRuns) - (s.away + e.awayRuns)), ((s.away + e.awayRuns) - (s.home + e.homeRuns))) - in.segment2Lead) + 1)))*max(0, min(1, ((s.inning - in.segment2Inning) + 1)))))))`

### c16UndoOnEmptyHistory
- 遷移 `undoOrReportNothing`(イベント `undo`・`guardRefs` = 空)
  - `s.outs` ← `s.outs`
  - `s.undoableDepth` ← `max(0, (s.undoableDepth - 1))`
  - `s.resultCode` ← `(1 - (1 - min(1, max((s.undoableDepth - 0), (0 - s.undoableDepth)))))`

### c17InputLock
- 遷移 `applyUnlessLocked`(イベント `playConfirmed`・`guardRefs` = 空)
  - `s.score` ← `(s.score + ((1 - s.locked)*e.runs))`
  - `s.locked` ← `max(s.locked, ((1 - s.locked)*e.endConditionMet))`
  - `s.resultCode` ← `(1 - s.locked)`

### c27ManualOverride
- 遷移 `advanceOrOverride`(イベント `singleConfirmed`・`guardRefs` = 空)
  - `s.first` ← `((e.manualOverride*e.manualFirst) + ((1 - e.manualOverride)*1))`
  - `s.second` ← `((e.manualOverride*e.manualSecond) + ((1 - e.manualOverride)*s.first))`
  - `s.third` ← `((e.manualOverride*e.manualThird) + ((1 - e.manualOverride)*s.second))`

### c8c22CurrentPitcherPitchCount
- 遷移 `countPitch`(イベント `recordConfirmed`・`guardRefs` = 空)
  - `s.pitchCount` ← `(s.pitchCount + e.isPitchEvent)`
- 遷移 `resetOnChange`(イベント `pitcherChanged`・`guardRefs` = 空)
  - `s.pitchCount` ← `0`

### c19FiscalYear
- 遷移 `deriveFiscalYear`(イベント `derive`・`guardRefs` = 空)
  - `s.fiscalYear` ← `(in.gameYear - (1 - max(0, min(1, ((in.gameMonth - 4) + 1)))))`

## 具体例(期待値は条文から手で導いた値)

| 候補 | 計算 | イベント | 事前状態 | イベント値 | 入力 | 期待 | 評価結果 | 一致 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | `c1ThirdOutChange` | `outRecorded` | `{'outs': 2, 'half': 0, 'inning': 3}` | `{'delta': 1}` | `-` | `{'outs': 0, 'half': 1, 'inning': 3}` | `{'outs': 0, 'half': 1, 'inning': 3}` | ✓ |
| C1 | `c1ThirdOutChange` | `outRecorded` | `{'outs': 0, 'half': 1, 'inning': 3}` | `{'delta': 1}` | `-` | `{'outs': 1, 'half': 1, 'inning': 3}` | `{'outs': 1, 'half': 1, 'inning': 3}` | ✓ |
| C1 | `c1ThirdOutChange` | `outRecorded` | `{'outs': 2, 'half': 1, 'inning': 3}` | `{'delta': 1}` | `-` | `{'outs': 0, 'half': 0, 'inning': 4}` | `{'outs': 0, 'half': 0, 'inning': 4}` | ✓ |
| C2 | `c2DroppedThirdStrike` | `pitch` | `{'outs': 1, 'firstOccupied': 1, 'batterMayRun': 0}` | `{'thirdStrike': 1, 'caught': 0}` | `-` | `{'outs': 1, 'firstOccupied': 1, 'batterMayRun': 0}` | `{'outs': 1, 'firstOccupied': 1, 'batterMayRun': 0}` | ✓ |
| C2 | `c2DroppedThirdStrike` | `pitch` | `{'outs': 2, 'firstOccupied': 1, 'batterMayRun': 0}` | `{'thirdStrike': 1, 'caught': 0}` | `-` | `{'outs': 2, 'firstOccupied': 1, 'batterMayRun': 1}` | `{'outs': 2, 'firstOccupied': 1, 'batterMayRun': 1}` | ✓ |
| C2 | `c2DroppedThirdStrike` | `pitch` | `{'outs': 0, 'firstOccupied': 0, 'batterMayRun': 0}` | `{'thirdStrike': 1, 'caught': 0}` | `-` | `{'outs': 0, 'firstOccupied': 0, 'batterMayRun': 1}` | `{'outs': 0, 'firstOccupied': 0, 'batterMayRun': 1}` | ✓ |
| C2 | `c2DroppedThirdStrike` | `pitch` | `{'outs': 2, 'firstOccupied': 0, 'batterMayRun': 0}` | `{'thirdStrike': 1, 'caught': 1}` | `-` | `{'outs': 2, 'firstOccupied': 0, 'batterMayRun': 0}` | `{'outs': 2, 'firstOccupied': 0, 'batterMayRun': 0}` | ✓ |
| C9 | `c9BattingOrderWrap` | `plateAppearanceCompleted` | `{'battingOrder': 9}` | `{}` | `-` | `{'battingOrder': 1}` | `{'battingOrder': 1}` | ✓ |
| C9 | `c9BattingOrderWrap` | `plateAppearanceCompleted` | `{'battingOrder': 3}` | `{}` | `-` | `{'battingOrder': 4}` | `{'battingOrder': 4}` | ✓ |
| C14 | `c14ColdSegments` | `playConfirmed` | `{'home': 9, 'away': 0, 'inning': 5, 'coldReached': 0}` | `{'homeRuns': 1, 'awayRuns': 0}` | `{'segment1Active': 1, 'segment1Lead': 10, 'segment1Inning': 5, 'segment2Active': 1, 'segment2Lead': 7, 'segment2Inning': 7}` | `{'home': 10, 'away': 0, 'inning': 5, 'coldReached': 1}` | `{'home': 10, 'away': 0, 'inning': 5, 'coldReached': 1}` | ✓ |
| C14 | `c14ColdSegments` | `playConfirmed` | `{'home': 8, 'away': 0, 'inning': 6, 'coldReached': 0}` | `{'homeRuns': 0, 'awayRuns': 0}` | `{'segment1Active': 1, 'segment1Lead': 10, 'segment1Inning': 5, 'segment2Active': 1, 'segment2Lead': 7, 'segment2Inning': 7}` | `{'home': 8, 'away': 0, 'inning': 6, 'coldReached': 0}` | `{'home': 8, 'away': 0, 'inning': 6, 'coldReached': 0}` | ✓ |
| C14 | `c14ColdSegments` | `playConfirmed` | `{'home': 0, 'away': 7, 'inning': 7, 'coldReached': 0}` | `{'homeRuns': 0, 'awayRuns': 0}` | `{'segment1Active': 1, 'segment1Lead': 10, 'segment1Inning': 5, 'segment2Active': 1, 'segment2Lead': 7, 'segment2Inning': 7}` | `{'home': 0, 'away': 7, 'inning': 7, 'coldReached': 1}` | `{'home': 0, 'away': 7, 'inning': 7, 'coldReached': 1}` | ✓ |
| C16 | `c16UndoOnEmptyHistory` | `undo` | `{'outs': 1, 'undoableDepth': 0, 'resultCode': 1}` | `{}` | `-` | `{'outs': 1, 'undoableDepth': 0, 'resultCode': 0}` | `{'outs': 1, 'undoableDepth': 0, 'resultCode': 0}` | ✓ |
| C16 | `c16UndoOnEmptyHistory` | `undo` | `{'outs': 2, 'undoableDepth': 0, 'resultCode': 1}` | `{}` | `-` | `{'outs': 2, 'undoableDepth': 0, 'resultCode': 0}` | `{'outs': 2, 'undoableDepth': 0, 'resultCode': 0}` | ✓ |
| C16 | `c16UndoOnEmptyHistory` | `undo` | `{'outs': 1, 'undoableDepth': 2, 'resultCode': 0}` | `{}` | `-` | `{'outs': 1, 'undoableDepth': 1, 'resultCode': 1}` | `{'outs': 1, 'undoableDepth': 1, 'resultCode': 1}` | ✓ |
| C17 | `c17InputLock` | `playConfirmed` | `{'score': 3, 'locked': 0, 'resultCode': 1}` | `{'runs': 2, 'endConditionMet': 1}` | `-` | `{'score': 5, 'locked': 1, 'resultCode': 1}` | `{'score': 5, 'locked': 1, 'resultCode': 1}` | ✓ |
| C17 | `c17InputLock` | `playConfirmed` | `{'score': 5, 'locked': 1, 'resultCode': 1}` | `{'runs': 2, 'endConditionMet': 0}` | `-` | `{'score': 5, 'locked': 1, 'resultCode': 0}` | `{'score': 5, 'locked': 1, 'resultCode': 0}` | ✓ |
| C27 | `c27ManualOverride` | `singleConfirmed` | `{'first': 1, 'second': 0, 'third': 0}` | `{'manualOverride': 0, 'manualFirst': 0, 'manualSecond': 0, 'manualThird': 0}` | `-` | `{'first': 1, 'second': 1, 'third': 0}` | `{'first': 1, 'second': 1, 'third': 0}` | ✓ |
| C27 | `c27ManualOverride` | `singleConfirmed` | `{'first': 1, 'second': 0, 'third': 0}` | `{'manualOverride': 1, 'manualFirst': 1, 'manualSecond': 0, 'manualThird': 1}` | `-` | `{'first': 1, 'second': 0, 'third': 1}` | `{'first': 1, 'second': 0, 'third': 1}` | ✓ |
| C8/C22 | `c8c22CurrentPitcherPitchCount` | `recordConfirmed` | `{'pitchCount': 41}` | `{'isPitchEvent': 1}` | `-` | `{'pitchCount': 42}` | `{'pitchCount': 42}` | ✓ |
| C8/C22 | `c8c22CurrentPitcherPitchCount` | `recordConfirmed` | `{'pitchCount': 41}` | `{'isPitchEvent': 0}` | `-` | `{'pitchCount': 41}` | `{'pitchCount': 41}` | ✓ |
| C8/C22 | `c8c22CurrentPitcherPitchCount` | `pitcherChanged` | `{'pitchCount': 41}` | `{}` | `-` | `{'pitchCount': 0}` | `{'pitchCount': 0}` | ✓ |
| C19 | `c19FiscalYear` | `derive` | `{'fiscalYear': 1999}` | `{}` | `{'gameYear': 2026, 'gameMonth': 3}` | `{'fiscalYear': 2025}` | `{'fiscalYear': 2025}` | ✓ |
| C19 | `c19FiscalYear` | `derive` | `{'fiscalYear': 1999}` | `{}` | `{'gameYear': 2026, 'gameMonth': 4}` | `{'fiscalYear': 2026}` | `{'fiscalYear': 2026}` | ✓ |

## 陽性対照(違反を仕込んだ記述が落ちること)

- 条件ノード(`kind: conditional`)を入れた記述: schema 検証で**拒否** ✓ — `$.calculations[2].rules[0]の oneOf 適合数が 0 である`
- 同じイベントに遷移 2 本: 生成前検査で**違反** ✓ — `CheckViolation(check_id=<CheckId.TRANSITIONS: 'transition-coverage-determinism'>, path='$.calculations[2].events[plateAppearanceCompleted]', message='複数の遷移が成立し決定的でない')`
- 整数の状態へ比較式(真偽値)を代入: 生成前検査で**違反** ✓ — `CheckViolation(check_id=<CheckId.TYPES_AND_RANGES: 'type-and-integer-range'>, path='$.calculations[2].rules[0].nextState[0].value', message='代入型が不一致: expected=integer, actual=boolean')`

**総合**: schema ✓ / 生成前検査 ✓ / 具体例 全件一致 / 陽性対照 ✓
