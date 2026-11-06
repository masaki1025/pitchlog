/** applyUndoの純ABI。保存/認可/真正履歴の資格を発行しない。 */
import type {
  StateFields as SharedStateFields,
  Scoreboard,
  Score,
  StatFlags,
  HistoryEntry,
  BattingOrderBySide,
} from "./lineup_play_prefix_v1";
export type CanonicalSigned = string;
export type StateFields = Readonly<
  Omit<
    SharedStateFields,
    | "state.count.strikes"
    | "state.count.balls"
    | "state.outs"
    | "state.battingOrder"
  > & {
    "state.count.strikes": "0" | "1" | "2";
    "state.count.balls": "0" | "1" | "2" | "3";
    "state.outs": "0" | "1" | "2";
    "state.battingOrder": "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9";
  }
>;
export type Current = Readonly<{
  stateFields: StateFields;
  scoreboard: Scoreboard;
  battingOrderBySide?: BattingOrderBySide;
}>;
export type Request = Readonly<{
  current: Current;
  history: Readonly<{ stack: readonly HistoryEntry[] }>;
}>;
export type Unchanged = Readonly<{ kind: "unchanged" }>;
export type SetEffect<T> = Readonly<{ kind: "set"; value: T }>;
export type IntegerEffect =
  | Unchanged
  | SetEffect<string>
  | Readonly<{ kind: "delta"; value: CanonicalSigned }>;
export type StateFieldEffects = Readonly<{
  "state.half": Unchanged | SetEffect<StateFields["state.half"]>;
  "state.count.strikes": IntegerEffect;
  "state.count.balls": IntegerEffect;
  "state.outs": IntegerEffect;
  "state.runners": Unchanged | SetEffect<StateFields["state.runners"]>;
  "state.battingOrder": IntegerEffect;
  "state.tiebreakActive": Unchanged | SetEffect<boolean>;
  "state.gameEnded": Unchanged | SetEffect<boolean>;
  "state.inning": IntegerEffect;
  "state.score": Unchanged | SetEffect<Score>;
}>;
export type ScoreboardEffects = Readonly<{
  inningScores: Unchanged | SetEffect<Score>;
  hits: IntegerEffect;
  errors: IntegerEffect;
  strikeouts: IntegerEffect;
  walks: IntegerEffect;
}>;
export type StateEffect<R extends "applied" | "nothing-to-undo"> = Readonly<{
  stateFields: R extends "applied"
    ? StateFieldEffects
    : Readonly<{ [K in keyof StateFieldEffects]: Unchanged }>;
  scoreboard: R extends "applied"
    ? ScoreboardEffects
    : Readonly<{ [K in keyof ScoreboardEffects]: Unchanged }>;
  statFlags: Readonly<{ [K in keyof StatFlags]: Unchanged }>;
  historyAndResult: Readonly<{
    history: R extends "applied"
      ? Readonly<{ kind: "pop"; count: "1" }>
      : Unchanged;
    operationResult: Readonly<{ kind: "set"; value: R }>;
  }>;
}>;
export type AppliedValue = Readonly<{
  operationResult: "applied";
  after: Current;
  stateEffect: StateEffect<"applied">;
  historyEffect: Readonly<{ pops: "1" }>;
  historyContext: readonly HistoryEntry[];
}>;
export type EmptyValue = Readonly<{
  operationResult: "nothing-to-undo";
  after: Current;
  stateEffect: StateEffect<"nothing-to-undo">;
  historyEffect: Readonly<{ pops: "0" }>;
  historyContext: readonly [];
}>;
export type Value = AppliedValue | EmptyValue;
export type Success = Readonly<{ ok: true; value: Value }>;
export type Failure = Readonly<{
  ok: false;
  error: Readonly<{
    code:
      | "INVALID_JSON"
      | "INVALID_REQUEST"
      | "INVALID_DECIMAL_INTEGER"
      | "UNSUPPORTED_T1_SCOPE";
  }>;
}>;
export type Response = Success | Failure;
