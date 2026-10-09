"""TSK-405 ステップ 3 の証拠: 「表現可能」と判定する候補の DSL 記述を組み立てて検証する。

本スクリプトは製品コードではない。research.md §11 の判定の証拠を再現するための分析用の道具である。

やること:
    1. 候補ごとの宣言(calculation)を組み立て、1 つの宣言モデル `expressible_models.json` に書き出す
    2. `backend/domain/model.schema.json` に対する検証
       (生成コアの検証器 `core._validate_source_document`)
    3. 生成前検査 `pregen_checks.run_pregen_checks`(5 系統)
    4. 遷移の値を評価する小さな参照評価器で、結果が分かれる具体例 2 つ以上を計算し、
       手で導いた期待値と照合する

評価器の意味論について:
    宣言モデルから実行コードを生成する経路は存在しない(research.md §4)。そのため本評価器は、
    ADR-003 D-1 の語(四則・min・max)の**通常の整数の意味**だけを実装する。
    ガード(`guardRefs`)・reducer・出力(`outputs`)・null は**使わない**(意味が規定されていないため)。
    本スクリプトの記述は `guardRefs` を常に空配列とし、遷移ごとの同時代入だけで結果を表す。

実行方法(worktree のルートで):
    cd backend && uv run python ../docs/features/ux1-game-state-core/evidence/expressible_models.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from pitchlog.domaingen import core, pregen_checks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DOMAIN = ROOT / "backend" / "domain"

Expr = dict[str, object]


# ---------------------------------------------------------------------------
# 式の組み立て(ADR-003 D-1 の語だけを使う)
# ---------------------------------------------------------------------------


def lit(value: int) -> Expr:
    """整数リテラル。"""
    return {"kind": "numeric-literal", "value": {"kind": "integer", "value": value}}


def state(field: str) -> Expr:
    """状態フィールドの参照。"""
    return {"kind": "state-ref", "fieldRef": field}


def event(field: str) -> Expr:
    """イベントフィールドの参照。"""
    return {"kind": "event-ref", "fieldRef": field}


def inp(field: str) -> Expr:
    """入力フィールドの参照。"""
    return {"kind": "input-ref", "fieldRef": field}


def arith(operator: str, *operands: Expr) -> Expr:
    """四則。"""
    return {"kind": "arithmetic", "operator": operator, "operands": list(operands)}


def add(*operands: Expr) -> Expr:
    """加算。"""
    return arith("add", *operands)


def sub(left: Expr, right: Expr) -> Expr:
    """減算(2 項)。"""
    return arith("subtract", left, right)


def mul(*operands: Expr) -> Expr:
    """乗算。"""
    return arith("multiply", *operands)


def minimum(*operands: Expr) -> Expr:
    """最小値。"""
    return {"kind": "extremum", "operator": "min", "operands": list(operands)}


def maximum(*operands: Expr) -> Expr:
    """最大値。"""
    return {"kind": "extremum", "operator": "max", "operands": list(operands)}


def at_least(value: Expr, threshold: int) -> Expr:
    """整数 `value >= threshold` なら 1、そうでなければ 0。

    式は max(0, min(1, value - threshold + 1))。
    """
    return maximum(lit(0), minimum(lit(1), add(sub(value, lit(threshold)), lit(1))))


def at_least_expr(value: Expr, threshold: Expr) -> Expr:
    """整数 `value >= threshold`(閾値も式)なら 1、そうでなければ 0。"""
    return maximum(lit(0), minimum(lit(1), add(sub(value, threshold), lit(1))))


def equals(value: Expr, constant: int) -> Expr:
    """整数 `value == constant` なら 1、そうでなければ 0(= 1 - min(1, |value - constant|))。"""
    distance = maximum(sub(value, lit(constant)), sub(lit(constant), value))
    return sub(lit(1), minimum(lit(1), distance))


def logical_not(flag: Expr) -> Expr:
    """0/1 の否定。"""
    return sub(lit(1), flag)


def logical_or(left: Expr, right: Expr) -> Expr:
    """0/1 の論理和(= a + b - a*b)。"""
    return sub(add(left, right), mul(left, right))


def select(flag: Expr, when_one: Expr, when_zero: Expr) -> Expr:
    """0/1 の flag による選択(= flag*x + (1-flag)*y)。"""
    return add(mul(flag, when_one), mul(logical_not(flag), when_zero))


# ---------------------------------------------------------------------------
# 宣言の組み立て
# ---------------------------------------------------------------------------


def integer_field(field_id: str, low: int, high: int) -> dict[str, object]:
    """値域つきの整数フィールド宣言。"""
    return {
        "fieldId": field_id,
        "type": {"kind": "integer"},
        "nullable": False,
        "range": {
            "minimum": {"kind": "integer", "value": low},
            "maximum": {"kind": "integer", "value": high},
        },
        "unit": None,
        "scale": 0,
    }


def output_field(field_id: str, low: int, high: int) -> dict[str, object]:
    """出力フィールド宣言(型だけ。値を定める記述は schema に無い — 候補 C3)。"""
    return {**integer_field(field_id, low, high), "visibility": "user-visible"}


def calculation(
    calculation_id: str,
    *,
    inputs: list[dict[str, object]],
    state_fields: list[dict[str, object]],
    events: list[tuple[str, list[dict[str, object]]]],
    transitions: list[tuple[str, str, dict[str, Expr]]],
    outputs: list[dict[str, object]],
) -> dict[str, object]:
    """1 計算の宣言。遷移は (ruleId, eventRef, {状態フィールド: 式}) の並び。"""
    return {
        "calculationId": calculation_id,
        "inputs": inputs,
        "states": [{"stateId": "s", "fields": state_fields}],
        "events": [{"eventId": eid, "fields": fields} for eid, fields in events],
        "rules": [
            {
                "kind": "transition",
                "ruleId": rule_id,
                "eventRef": event_ref,
                "guardRefs": [],
                "nextState": [
                    {"fieldRef": field, "value": value}
                    for field, value in assignments.items()
                ],
            }
            for rule_id, event_ref, assignments in transitions
        ],
        "outputs": outputs,
        "displayRuleRefs": [],
    }


def build_model() -> dict[str, object]:
    """「表現可能」と判定する候補の宣言をまとめた宣言モデル。"""
    calculations: list[dict[str, object]] = []

    # C1 条件分岐 — 第 3 アウトで攻守交代(FR-005 R:231)。
    # half: 0=表, 1=裏。t = [outs + delta >= 3]
    reached = at_least(add(state("outs"), event("delta")), 3)
    calculations.append(
        calculation(
            "c1ThirdOutChange",
            inputs=[],
            state_fields=[
                integer_field("outs", 0, 2),
                integer_field("half", 0, 1),
                integer_field("inning", 1, 99),
            ],
            events=[("outRecorded", [integer_field("delta", 1, 3)])],
            transitions=[
                (
                    "applyOut",
                    "outRecorded",
                    {
                        "outs": mul(add(state("outs"), event("delta")), logical_not(reached)),
                        "half": sub(
                            add(state("half"), reached),
                            mul(lit(2), state("half"), reached),
                        ),
                        "inning": add(state("inning"), mul(reached, state("half"))),
                    },
                )
            ],
            outputs=[output_field("inningOut", 1, 99)],
        )
    )

    # C2 論理演算 — 振り逃げの前提(付録E-1 R:1256):
    # 「第3ストライク不捕球 かつ(二死 または 一塁空き)」
    eligible = mul(
        event("thirdStrike"),
        logical_not(event("caught")),
        logical_or(equals(state("outs"), 2), logical_not(state("firstOccupied"))),
    )
    calculations.append(
        calculation(
            "c2DroppedThirdStrike",
            inputs=[],
            state_fields=[
                integer_field("outs", 0, 2),
                integer_field("firstOccupied", 0, 1),
                integer_field("batterMayRun", 0, 1),
            ],
            events=[
                (
                    "pitch",
                    [integer_field("thirdStrike", 0, 1), integer_field("caught", 0, 1)],
                )
            ],
            transitions=[
                (
                    "judgeDroppedThirdStrike",
                    "pitch",
                    {
                        "outs": state("outs"),
                        "firstOccupied": state("firstOccupied"),
                        "batterMayRun": eligible,
                    },
                )
            ],
            outputs=[output_field("batterMayRunOut", 0, 1)],
        )
    )

    # C9 剰余 — 打順の 9 → 1 の循環(FR-005 R:229・R:231 / FR-001 R:195)。
    calculations.append(
        calculation(
            "c9BattingOrderWrap",
            inputs=[],
            state_fields=[integer_field("battingOrder", 1, 9)],
            events=[("plateAppearanceCompleted", [])],
            transitions=[
                (
                    "advanceBattingOrder",
                    "plateAppearanceCompleted",
                    {
                        "battingOrder": sub(
                            add(state("battingOrder"), lit(1)),
                            mul(lit(9), equals(state("battingOrder"), 9)),
                        )
                    },
                )
            ],
            outputs=[output_field("battingOrderOut", 1, 9)],
        )
    )

    # C14 規則の可変長配列 — コールド条件の段の配列(付録F-1 R:1286)を、
    # schema が閉じる最大段数(ADR-003 R:204 相当 — 本例は 2 段)の固定入力へ平坦化する。
    lead = maximum(sub(state("home"), state("away")), sub(state("away"), state("home")))
    lead_after = maximum(
        sub(add(state("home"), event("homeRuns")), add(state("away"), event("awayRuns"))),
        sub(add(state("away"), event("awayRuns")), add(state("home"), event("homeRuns"))),
    )
    del lead

    def segment(index: int) -> Expr:
        return mul(
            inp(f"segment{index}Active"),
            at_least_expr(lead_after, inp(f"segment{index}Lead")),
            at_least_expr(state("inning"), inp(f"segment{index}Inning")),
        )

    calculations.append(
        calculation(
            "c14ColdSegments",
            inputs=[
                integer_field("segment1Active", 0, 1),
                integer_field("segment1Lead", 1, 99),
                integer_field("segment1Inning", 1, 99),
                integer_field("segment2Active", 0, 1),
                integer_field("segment2Lead", 1, 99),
                integer_field("segment2Inning", 1, 99),
            ],
            state_fields=[
                integer_field("home", 0, 999),
                integer_field("away", 0, 999),
                integer_field("inning", 1, 99),
                integer_field("coldReached", 0, 1),
            ],
            events=[
                (
                    "playConfirmed",
                    [integer_field("homeRuns", 0, 4), integer_field("awayRuns", 0, 4)],
                )
            ],
            transitions=[
                (
                    "scoreAndJudgeCold",
                    "playConfirmed",
                    {
                        "home": add(state("home"), event("homeRuns")),
                        "away": add(state("away"), event("awayRuns")),
                        "inning": state("inning"),
                        "coldReached": maximum(
                            state("coldReached"), logical_or(segment(1), segment(2))
                        ),
                    },
                )
            ],
            outputs=[output_field("coldReachedOut", 0, 1)],
        )
    )

    # C16 状態を変えないイベント(FR-006 R:243) — 履歴文脈が空の undo は状態を変えず、
    # 「取り消す対象が無い」を返す。空かどうかは、取消可能な操作の数 `undoableDepth` を
    # 状態として数えて判定する(履歴スタックを読まない)。
    # resultCode: 1=適用された, 0=取り消す対象が無い。
    # 空でない場合の状態の復元は本記述の射程外(候補 C4)。
    nonempty = logical_not(equals(state("undoableDepth"), 0))
    calculations.append(
        calculation(
            "c16UndoOnEmptyHistory",
            inputs=[],
            state_fields=[
                integer_field("outs", 0, 2),
                integer_field("undoableDepth", 0, 9999),
                integer_field("resultCode", 0, 1),
            ],
            events=[("undo", [])],
            transitions=[
                (
                    "undoOrReportNothing",
                    "undo",
                    {
                        "outs": state("outs"),
                        "undoableDepth": maximum(lit(0), sub(state("undoableDepth"), lit(1))),
                        "resultCode": nonempty,
                    },
                )
            ],
            outputs=[output_field("resultCodeOut", 0, 1)],
        )
    )

    # C17 ガード不成立時 — 終了条件の成立後は入力をロックする(FR-005 R:232)。
    # resultCode: 1=適用された, 0=ロック中で適用されない(操作結果の区分 — R:927)
    open_flag = logical_not(state("locked"))
    calculations.append(
        calculation(
            "c17InputLock",
            inputs=[],
            state_fields=[
                integer_field("score", 0, 999),
                integer_field("locked", 0, 1),
                integer_field("resultCode", 0, 1),
            ],
            events=[
                (
                    "playConfirmed",
                    [integer_field("runs", 0, 4), integer_field("endConditionMet", 0, 1)],
                )
            ],
            transitions=[
                (
                    "applyUnlessLocked",
                    "playConfirmed",
                    {
                        "score": add(state("score"), mul(open_flag, event("runs"))),
                        "locked": maximum(
                            state("locked"), mul(open_flag, event("endConditionMet"))
                        ),
                        "resultCode": open_flag,
                    },
                )
            ],
            outputs=[output_field("scoreOut", 0, 999)],
        )
    )

    # C27 手動値の優先(FR-003 R:215) — 自動設定(単打で全走者 1 つ進塁)より、
    # 確定時の手動値を優先する。
    override = event("manualOverride")
    calculations.append(
        calculation(
            "c27ManualOverride",
            inputs=[],
            state_fields=[
                integer_field("first", 0, 1),
                integer_field("second", 0, 1),
                integer_field("third", 0, 1),
            ],
            events=[
                (
                    "singleConfirmed",
                    [
                        integer_field("manualOverride", 0, 1),
                        integer_field("manualFirst", 0, 1),
                        integer_field("manualSecond", 0, 1),
                        integer_field("manualThird", 0, 1),
                    ],
                )
            ],
            transitions=[
                (
                    "advanceOrOverride",
                    "singleConfirmed",
                    {
                        "first": select(override, event("manualFirst"), lit(1)),
                        "second": select(override, event("manualSecond"), state("first")),
                        "third": select(override, event("manualThird"), state("second")),
                    },
                )
            ],
            outputs=[output_field("firstOut", 0, 1)],
        )
    )

    # C8 / C22 — 投球イベントだけを数える絞り込み(R:166)と、登板中投手への選択(FR-021 R:432)。
    # 全履歴の集計(C22)は、遷移ごとの累積で表す(履歴を読み直さない)。
    calculations.append(
        calculation(
            "c8c22CurrentPitcherPitchCount",
            inputs=[],
            state_fields=[integer_field("pitchCount", 0, 999)],
            events=[
                ("recordConfirmed", [integer_field("isPitchEvent", 0, 1)]),
                ("pitcherChanged", []),
            ],
            transitions=[
                (
                    "countPitch",
                    "recordConfirmed",
                    {"pitchCount": add(state("pitchCount"), event("isPitchEvent"))},
                ),
                ("resetOnChange", "pitcherChanged", {"pitchCount": lit(0)}),
            ],
            outputs=[output_field("pitchCountOut", 0, 999)],
        )
    )

    # C19 日付の型 — 試合日(年・月の整数)から年度(4/1 始まり)を導く(付録A-1 R:1102)。
    calculations.append(
        calculation(
            "c19FiscalYear",
            inputs=[integer_field("gameYear", 2000, 2999), integer_field("gameMonth", 1, 12)],
            state_fields=[integer_field("fiscalYear", 1999, 2999)],
            events=[("derive", [])],
            transitions=[
                (
                    "deriveFiscalYear",
                    "derive",
                    {
                        "fiscalYear": sub(
                            inp("gameYear"), logical_not(at_least(inp("gameMonth"), 4))
                        )
                    },
                )
            ],
            outputs=[output_field("fiscalYearOut", 1999, 2999)],
        )
    )

    return {"schemaVersion": 1, "calculations": calculations, "displayRules": []}


# ---------------------------------------------------------------------------
# 参照評価器(整数の四則・min・max だけ)
# ---------------------------------------------------------------------------


def evaluate(expression: Mapping[str, object], env: Mapping[str, Mapping[str, int]]) -> int:
    """式を整数で評価する。"""
    kind = expression["kind"]
    if kind == "numeric-literal":
        value = expression["value"]
        assert isinstance(value, dict) and value["kind"] == "integer"
        return int(value["value"])
    if kind in {"state-ref", "event-ref", "input-ref"}:
        return env[str(kind)][str(expression["fieldRef"])]
    operands = [evaluate(o, env) for o in expression["operands"]]  # type: ignore[union-attr]
    operator = expression["operator"]
    if kind == "arithmetic":
        if operator == "add":
            return sum(operands)
        if operator == "subtract":
            assert len(operands) == 2
            return operands[0] - operands[1]
        if operator == "multiply":
            result = 1
            for item in operands:
                result *= item
            return result
    if kind == "extremum":
        return min(operands) if operator == "min" else max(operands)
    raise ValueError(f"本評価器の射程外の式: {kind}/{operator}")


def apply_transition(
    model: Mapping[str, object],
    calculation_id: str,
    event_id: str,
    pre_state: Mapping[str, int],
    event_values: Mapping[str, int],
    input_values: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """1 遷移を同時代入で適用した後の状態を返す。"""
    calc = next(
        c for c in model["calculations"] if c["calculationId"] == calculation_id  # type: ignore[union-attr,index]
    )
    rule = next(r for r in calc["rules"] if r["eventRef"] == event_id)
    env = {
        "state-ref": dict(pre_state),
        "event-ref": dict(event_values),
        "input-ref": dict(input_values or {}),
    }
    post = dict(pre_state)
    for assignment in rule["nextState"]:
        post[assignment["fieldRef"]] = evaluate(assignment["value"], env)
    return post


# ---------------------------------------------------------------------------
# 具体例(期待値は要件の条文から手で導いた値)
# ---------------------------------------------------------------------------

Case = tuple[str, str, str, dict[str, int], dict[str, int], dict[str, int], dict[str, int]]

COLD_INPUTS = {
    "segment1Active": 1,
    "segment1Lead": 10,
    "segment1Inning": 5,
    "segment2Active": 1,
    "segment2Lead": 7,
    "segment2Inning": 7,
}

CASES: list[Case] = [
    # (候補, 計算, イベント, 事前状態, イベント値, 入力, 期待する事後状態)
    (
        "C1",
        "c1ThirdOutChange",
        "outRecorded",
        {"outs": 2, "half": 0, "inning": 3},
        {"delta": 1},
        {},
        {"outs": 0, "half": 1, "inning": 3},
    ),
    (
        "C1",
        "c1ThirdOutChange",
        "outRecorded",
        {"outs": 0, "half": 1, "inning": 3},
        {"delta": 1},
        {},
        {"outs": 1, "half": 1, "inning": 3},
    ),
    (
        "C1",
        "c1ThirdOutChange",
        "outRecorded",
        {"outs": 2, "half": 1, "inning": 3},
        {"delta": 1},
        {},
        {"outs": 0, "half": 0, "inning": 4},
    ),
    (
        "C2",
        "c2DroppedThirdStrike",
        "pitch",
        {"outs": 1, "firstOccupied": 1, "batterMayRun": 0},
        {"thirdStrike": 1, "caught": 0},
        {},
        {"outs": 1, "firstOccupied": 1, "batterMayRun": 0},
    ),
    (
        "C2",
        "c2DroppedThirdStrike",
        "pitch",
        {"outs": 2, "firstOccupied": 1, "batterMayRun": 0},
        {"thirdStrike": 1, "caught": 0},
        {},
        {"outs": 2, "firstOccupied": 1, "batterMayRun": 1},
    ),
    (
        "C2",
        "c2DroppedThirdStrike",
        "pitch",
        {"outs": 0, "firstOccupied": 0, "batterMayRun": 0},
        {"thirdStrike": 1, "caught": 0},
        {},
        {"outs": 0, "firstOccupied": 0, "batterMayRun": 1},
    ),
    (
        "C2",
        "c2DroppedThirdStrike",
        "pitch",
        {"outs": 2, "firstOccupied": 0, "batterMayRun": 0},
        {"thirdStrike": 1, "caught": 1},
        {},
        {"outs": 2, "firstOccupied": 0, "batterMayRun": 0},
    ),
    (
        "C9",
        "c9BattingOrderWrap",
        "plateAppearanceCompleted",
        {"battingOrder": 9},
        {},
        {},
        {"battingOrder": 1},
    ),
    (
        "C9",
        "c9BattingOrderWrap",
        "plateAppearanceCompleted",
        {"battingOrder": 3},
        {},
        {},
        {"battingOrder": 4},
    ),
    (
        "C14",
        "c14ColdSegments",
        "playConfirmed",
        {"home": 9, "away": 0, "inning": 5, "coldReached": 0},
        {"homeRuns": 1, "awayRuns": 0},
        COLD_INPUTS,
        {"home": 10, "away": 0, "inning": 5, "coldReached": 1},
    ),
    (
        "C14",
        "c14ColdSegments",
        "playConfirmed",
        {"home": 8, "away": 0, "inning": 6, "coldReached": 0},
        {"homeRuns": 0, "awayRuns": 0},
        COLD_INPUTS,
        {"home": 8, "away": 0, "inning": 6, "coldReached": 0},
    ),
    (
        "C14",
        "c14ColdSegments",
        "playConfirmed",
        {"home": 0, "away": 7, "inning": 7, "coldReached": 0},
        {"homeRuns": 0, "awayRuns": 0},
        COLD_INPUTS,
        {"home": 0, "away": 7, "inning": 7, "coldReached": 1},
    ),
    (
        "C16",
        "c16UndoOnEmptyHistory",
        "undo",
        {"outs": 1, "undoableDepth": 0, "resultCode": 1},
        {},
        {},
        {"outs": 1, "undoableDepth": 0, "resultCode": 0},
    ),
    (
        "C16",
        "c16UndoOnEmptyHistory",
        "undo",
        {"outs": 2, "undoableDepth": 0, "resultCode": 1},
        {},
        {},
        {"outs": 2, "undoableDepth": 0, "resultCode": 0},
    ),
    (
        "C16",
        "c16UndoOnEmptyHistory",
        "undo",
        {"outs": 1, "undoableDepth": 2, "resultCode": 0},
        {},
        {},
        {"outs": 1, "undoableDepth": 1, "resultCode": 1},
    ),
    (
        "C17",
        "c17InputLock",
        "playConfirmed",
        {"score": 3, "locked": 0, "resultCode": 1},
        {"runs": 2, "endConditionMet": 1},
        {},
        {"score": 5, "locked": 1, "resultCode": 1},
    ),
    (
        "C17",
        "c17InputLock",
        "playConfirmed",
        {"score": 5, "locked": 1, "resultCode": 1},
        {"runs": 2, "endConditionMet": 0},
        {},
        {"score": 5, "locked": 1, "resultCode": 0},
    ),
    (
        "C27",
        "c27ManualOverride",
        "singleConfirmed",
        {"first": 1, "second": 0, "third": 0},
        {"manualOverride": 0, "manualFirst": 0, "manualSecond": 0, "manualThird": 0},
        {},
        {"first": 1, "second": 1, "third": 0},
    ),
    (
        "C27",
        "c27ManualOverride",
        "singleConfirmed",
        {"first": 1, "second": 0, "third": 0},
        {"manualOverride": 1, "manualFirst": 1, "manualSecond": 0, "manualThird": 1},
        {},
        {"first": 1, "second": 0, "third": 1},
    ),
    (
        "C8/C22",
        "c8c22CurrentPitcherPitchCount",
        "recordConfirmed",
        {"pitchCount": 41},
        {"isPitchEvent": 1},
        {},
        {"pitchCount": 42},
    ),
    (
        "C8/C22",
        "c8c22CurrentPitcherPitchCount",
        "recordConfirmed",
        {"pitchCount": 41},
        {"isPitchEvent": 0},
        {},
        {"pitchCount": 41},
    ),
    (
        "C8/C22",
        "c8c22CurrentPitcherPitchCount",
        "pitcherChanged",
        {"pitchCount": 41},
        {},
        {},
        {"pitchCount": 0},
    ),
    (
        "C19",
        "c19FiscalYear",
        "derive",
        {"fiscalYear": 1999},
        {},
        {"gameYear": 2026, "gameMonth": 3},
        {"fiscalYear": 2025},
    ),
    (
        "C19",
        "c19FiscalYear",
        "derive",
        {"fiscalYear": 1999},
        {},
        {"gameYear": 2026, "gameMonth": 4},
        {"fiscalYear": 2026},
    ),
]


def mark(ok: bool) -> str:
    """合否の記号。"""
    return "✓" if ok else "✗"


def render(expression: Mapping[str, object]) -> str:
    """式を中置記法で読める形にする(導出規則の提示用)。"""
    kind = expression["kind"]
    if kind == "numeric-literal":
        return str(expression["value"]["value"])  # type: ignore[index]
    if kind in {"state-ref", "event-ref", "input-ref"}:
        prefix = {"state-ref": "s", "event-ref": "e", "input-ref": "in"}[str(kind)]
        return f"{prefix}.{expression['fieldRef']}"
    parts = [render(o) for o in expression["operands"]]  # type: ignore[union-attr]
    operator = expression["operator"]
    if kind == "extremum":
        return f"{operator}({', '.join(parts)})"
    symbol = {"add": " + ", "subtract": " - ", "multiply": "*", "divide": " / "}[str(operator)]
    return "(" + symbol.join(parts) + ")"


def main() -> int:
    """証拠を組み立てて検証し、結果を書き出す。終了コード 0 = すべて通過。"""
    model = build_model()
    model_path = HERE / "expressible_models.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load(name: str) -> Mapping[str, object]:
        return json.loads((DOMAIN / name).read_text(encoding="utf-8"))

    schemas = core.SourceSchemas(
        model=load("model.schema.json"),
        manifest=load("manifest.schema.json"),
        vocabulary=load("vocabulary.schema.json"),
    )
    lines: list[str] = []
    out: Callable[[str], None] = lines.append

    out("# expressible_models.py の実行結果")
    out("")
    try:
        core._validate_source_document(model, core._MODEL_SCHEMA, schemas)  # noqa: SLF001
        out("- schema 検証(`model.schema.json`・生成コアの検証器): **通過**")
        schema_ok = True
    except core.GenerationError as error:
        out(f"- schema 検証: **失敗** — {error}")
        schema_ok = False

    report = pregen_checks.run_pregen_checks(model, schemas)
    attempted = ", ".join(sorted(check.value for check in report.attempted))
    out(f"- 生成前検査(実行した系統: {attempted}): **{'通過' if report.passed else '違反あり'}**")
    for violation in report.violations:
        out(f"  - {violation}")
    out("")

    out("## 導出規則(遷移の同時代入)")
    out("")
    for calc in model["calculations"]:  # type: ignore[union-attr]
        out(f"### {calc['calculationId']}")
        for rule in calc["rules"]:
            out(f"- 遷移 `{rule['ruleId']}`(イベント `{rule['eventRef']}`・`guardRefs` = 空)")
            for assignment in rule["nextState"]:
                out(f"  - `s.{assignment['fieldRef']}` ← `{render(assignment['value'])}`")
        out("")

    out("## 具体例(期待値は条文から手で導いた値)")
    out("")
    out("| 候補 | 計算 | イベント | 事前状態 | イベント値 | 入力 | 期待 | 評価結果 | 一致 |")
    out("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    all_ok = True
    for candidate, calc_id, event_id, pre, ev, inputs, expected in CASES:
        actual = apply_transition(model, calc_id, event_id, pre, ev, inputs)
        ok = actual == expected
        all_ok &= ok
        out(
            f"| {candidate} | `{calc_id}` | `{event_id}` | `{pre}` | `{ev}` | `{inputs or '-'}` "
            f"| `{expected}` | `{actual}` | {'✓' if ok else '✗'} |"
        )
    out("")

    # 陽性対照: 検証器が違反を実際に拾うことを確かめる
    # (通過が「見ていない」ことの結果でないことの確認)
    out("## 陽性対照(違反を仕込んだ記述が落ちること)")
    out("")
    controls_ok = True

    conditional = json.loads(json.dumps(model))
    conditional["calculations"][2]["rules"][0]["nextState"][0]["value"] = {
        "kind": "conditional",
        "condition": lit(1),
        "then": lit(1),
        "else": lit(2),
    }
    try:
        core._validate_source_document(conditional, core._MODEL_SCHEMA, schemas)  # noqa: SLF001
        out("- 条件ノード(`kind: conditional`)を入れた記述: schema 検証を**通ってしまった** ✗")
        controls_ok = False
    except core.GenerationError as error:
        detail = str(error)[:120]
        out(f"- 条件ノード(`kind: conditional`)を入れた記述: schema 検証で**拒否** ✓ — `{detail}`")

    duplicated = json.loads(json.dumps(model))
    rules = duplicated["calculations"][2]["rules"]
    rules.append({**rules[0], "ruleId": "advanceBattingOrderAgain"})
    duplicate_report = pregen_checks.run_pregen_checks(duplicated, schemas)
    if duplicate_report.passed:
        out("- 同じイベントに遷移 2 本: 生成前検査を**通ってしまった** ✗")
        controls_ok = False
    else:
        detail = duplicate_report.violations[0]
        out(f"- 同じイベントに遷移 2 本: 生成前検査で**違反** ✓ — `{detail}`")

    mistyped = json.loads(json.dumps(model))
    mistyped["calculations"][2]["rules"][0]["nextState"][0]["value"] = {
        "kind": "comparison",
        "operator": "equal",
        "left": state("battingOrder"),
        "right": lit(9),
    }
    mistyped_report = pregen_checks.run_pregen_checks(mistyped, schemas)
    if mistyped_report.passed:
        out("- 整数の状態へ比較式(真偽値)を代入: 生成前検査を**通ってしまった** ✗")
        controls_ok = False
    else:
        detail = mistyped_report.violations[0]
        out(f"- 整数の状態へ比較式(真偽値)を代入: 生成前検査で**違反** ✓ — `{detail}`")
    out("")

    out(
        f"**総合**: schema {mark(schema_ok)} / 生成前検査 {mark(report.passed)} "
        f"/ 具体例 {'全件一致' if all_ok else '不一致あり'} / 陽性対照 {mark(controls_ok)}"
    )
    all_ok &= controls_ok

    (HERE / "expressible_models.out.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if (schema_ok and report.passed and all_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
