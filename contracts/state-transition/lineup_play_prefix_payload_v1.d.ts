/** V8は実history差分。v2のbody再送は変更しない。 */
import type {Request,Success,HistoryEntry,PitchT1Input,BattedHitT1Input,IntentionalWalkT1Input} from "./lineup_play_prefix_v1";
import type {Observations,Participants} from "./play_prefix_v2_payload_v1";
export type Calculation=Readonly<{formatVersion:"play-prefix-calculation-v3";artifactSha256:string;request:Request;response:Success}>;
type PitchOnlyT1 = PitchT1Input & Readonly<{officialScoringPayload?:never;interferenceRuling?:never;runnerAdvanceOverrides?:never;thirdOutObservation?:never}>;
type PitchOnlyObservations = Observations & Readonly<{[K in Exclude<keyof BattedHitObservations,keyof Observations>]?:never}>;
type CalculationFor<T extends Request["t1"]> = Readonly<Omit<Calculation,"request"> & {request:Readonly<Omit<Request,"t1"> & {t1:T}>}>;
export type PitchPlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:PitchOnlyObservations;participants:Participants;calculation:CalculationFor<PitchOnlyT1>}>;
export type BattedHitResult = BattedHitT1Input["resultId"];
export type BattedHitPlayPrefixV7<R extends BattedHitResult> = Readonly<{formatVersion:"play-prefix-play-v3";observations:Readonly<BattedHitObservations & {resultId:R}>;participants:Participants;calculation:CalculationFor<Readonly<BattedHitT1Input & {resultId:R}>>}>;
export type IntentionalWalkPlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:Readonly<{kind:"intentional-walk"}>;participants:Participants;calculation:CalculationFor<IntentionalWalkT1Input>}>;
export type LineupPlayPrefixV7 = RunnerPlayPrefixV7 | NonplayNormalV7 | PitchPlayPrefixV7 | IntentionalWalkPlayPrefixV7 | {[R in BattedHitResult]:BattedHitPlayPrefixV7<R>}[BattedHitResult];
export type LineupPlayPrefixV8=HistoryEntry["difference"];

/** 無走者4安打の全明示観測。nullableは未観測の保持であり、値を推測しない。 */
type BattedHitObservationBase = Readonly<{
  pitchTypeKey: Observations["pitchTypeKey"];
  course: Observations["course"];
  pitchSpeed: Observations["pitchSpeed"];
  stance: Observations["stance"];
  battingSide: Observations["battingSide"];
  resultId: "batting-result.single" | "batting-result.double" | "batting-result.triple" | "batting-result.home-run";
  battedBall: Readonly<{typeKey:string|null;strengthKey:string|null;hitX:string|null;hitY:string|null;rawFielderPosition:string|null;resolvedFielderId:string|null}>;
  officialScoringPayload: Readonly<{kind:"no-error";errorCount:"0";fielders:readonly []}>;
  interferenceRuling: Readonly<{kind:"not-required"}>;
  runnerAdvanceOverridesByRunner: (Readonly<{kind:"not-applied";overrides:readonly []}> | Readonly<{kind:"applied";overrides:readonly (Readonly<{runnerBase:"1"|"2"|"3";destination:"2"|"3"|"4"}>)[]}>);
  thirdOutObservation: Readonly<{kind:"none"}>;
  thirdOutTimingByRunner: Readonly<Record<string,never>>;
}>;

export type BattedHitObservations = BattedHitObservationBase | (Omit<BattedHitObservationBase,"resultId"|"thirdOutObservation"|"runnerAdvanceOverridesByRunner"> & Readonly<{resultId:"batting-result.batted-out"; runnerAdvanceOverridesByRunner:Readonly<{kind:"not-applied";overrides:readonly []}>; thirdOutObservation:Readonly<{kind:"none"}>|Readonly<{kind:"batter-before-first";batter:Readonly<{kind:"official";player_id:string}>}>}>);

/** 数学nextCPはlogical proposal echo。正式保存refはserver ACK後のGETで得る。 */
import type { NonplayRequest, NonplaySuccess } from "./lineup_play_prefix_v1";
export type NonplayNormalCalculation = Readonly<{
  formatVersion: "nonplay-prefix-calculation-v1";
  artifactSha256: string;
  request: Readonly<
    Omit<NonplayRequest, "t1"> & {
      t1: Readonly<
        PitchOnlyT1 & {
          resultId: "batting-result.ball";
          pitchEventKind: "pitch-event";
        }
      >;
    }
  >;
  response: NonplaySuccess &
    Readonly<{
      value: NonplaySuccess["value"] &
        Readonly<{
          t1: NonplaySuccess["value"]["t1"] &
            Readonly<{ plateAppearanceEnded: false }>;
        }>;
    }>;
}>;
export type NonplayNormalV7 = Readonly<{
  formatVersion: "play-prefix-play-v3";
  observations: PitchOnlyObservations;
  participants: Participants;
  calculation: NonplayNormalCalculation;
}>;

import type { RunnerEventT1Input, RunnerObservation, RunnerValue, RunnerNonplayValue } from './lineup_play_prefix_v1';
export type RunnerPitchObservations = Observations & Readonly<{runnerObservation:RunnerObservation}>;
export type RunnerNonpitchObservations = Readonly<{kind:'non-pitch-event';runnerObservation:RunnerObservation}>;
export type RunnerNormalPlayPrefixV7 = Readonly<{
 formatVersion:'play-prefix-play-v3';observations:RunnerPitchObservations|RunnerNonpitchObservations;participants:Participants;
 calculation: Readonly<{formatVersion:'play-prefix-calculation-v3';artifactSha256:string;request:Readonly<Omit<Request,'t1'>&{t1:RunnerEventT1Input}>;response:Readonly<{ok:true;value:RunnerValue}>}>
}>;
export type RunnerNonplayPrefixV7 = Readonly<{
 formatVersion:'play-prefix-play-v3';observations:RunnerPitchObservations|RunnerNonpitchObservations;participants:Participants;
 calculation: Readonly<{formatVersion:'nonplay-prefix-calculation-v1';artifactSha256:string;request:Readonly<Omit<NonplayRequest,'t1'>&{t1:RunnerEventT1Input}>;response:Readonly<{ok:true;value:RunnerNonplayValue}>}>
}>;
export type RunnerPlayPrefixV7 = RunnerNormalPlayPrefixV7 | RunnerNonplayPrefixV7;
