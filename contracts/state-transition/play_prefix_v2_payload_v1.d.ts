/** v2 V7/V8の閉候補。保存資格やACKを表さない。 */
import type { PlayRequest, PlayResponse, HistoryEntry } from "./play_prefix_v2";
export type FirstBallCourse = Readonly<{ unit: "1/263"; x: string; y: string }>;
export type Observations = Readonly<{
  pitchTypeKey: string;
  course: FirstBallCourse;
  pitchSpeed: Readonly<{ kmh: string | null; outsideRangeConfirmed: boolean }>;
  stance: string | null;
  battingSide: "右" | "左" | null;
}>;
export type Participants = Readonly<{
  batterId: string;
  pitcherId: string;
  catcherId: string;
  battingOrder: "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9";
}>;
export type Calculation = Readonly<{
  formatVersion: "play-prefix-calculation-v2";
  artifactSha256: string;
  request: PlayRequest;
  response: Extract<PlayResponse, { readonly ok: true }>;
}>;
export type PlayPrefixV7 = Readonly<{
  formatVersion: "play-prefix-play-v2";
  observations: Observations;
  participants: Participants;
  calculation: Calculation;
}>;
export type PlayPrefixV8 = HistoryEntry["difference"];
