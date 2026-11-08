/** V8は実history差分。v2のbody再送は変更しない。 */
import type {Request,Success,HistoryEntry,PitchT1Input,BattedHitT1Input,IntentionalWalkT1Input,BattingInterferencePenaltyT1Input,BattingInterferencePlayT1Input,AdjudicatedInterferenceT1Input,InterferencePenaltyRuling,InterferencePlayRuling,InterferenceObstructionRuling,InterferenceOffensiveRuling} from "./lineup_play_prefix_v1";
import type {Observations,Participants} from "./play_prefix_v2_payload_v1";
export type Calculation=Readonly<{formatVersion:"play-prefix-calculation-v3";artifactSha256:string;request:Request;response:Success}>;
type PitchOnlyT1 = PitchT1Input & Readonly<{officialScoringPayload?:never;interferenceRuling?:never;runnerAdvanceOverrides?:never;thirdOutObservation?:never}>;
type PitchOnlyObservations = Observations & Readonly<{[K in Exclude<keyof BattedHitObservations,keyof Observations>]?:never}>;
type CalculationFor<T extends Request["t1"]> = Readonly<Omit<Calculation,"request"> & {request:Readonly<Omit<Request,"t1"> & {t1:T}>}>;
export type PitchPlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:PitchOnlyObservations;participants:Participants;calculation:CalculationFor<PitchOnlyT1>}>;
export type BattedHitResult = BattedHitT1Input["resultId"];
export type BattedHitPlayPrefixV7<R extends BattedHitResult> = Readonly<{formatVersion:"play-prefix-play-v3";observations:Readonly<BattedHitObservations & {resultId:R}>;participants:Participants;calculation:CalculationFor<Readonly<BattedHitT1Input & {resultId:R}>>}>;
export type IntentionalWalkPlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:Readonly<{kind:"intentional-walk"}>;participants:Participants;calculation:CalculationFor<IntentionalWalkT1Input>}>;
export type BattingInterferencePenaltyObservations = Observations & Readonly<{resultId:"secondary-result.batting-interference";interferenceRuling:InterferencePenaltyRuling}>;
type InterferencePlayObservationFor<R extends BattedHitResult> = BattedHitObservations extends infer U ? U extends BattedHitObservations ? R extends U["resultId"] ? Omit<U,"resultId"|"interferenceRuling"> & Readonly<{resultId:R;interferenceRuling:InterferencePlayRuling<R>}> : never : never : never;
export type BattingInterferencePlayObservations = {[R in BattedHitResult]:InterferencePlayObservationFor<R>}[BattedHitResult];
export type AdjudicatedInterferenceObservations = Observations & (Readonly<{resultId:"secondary-result.obstruction";interferenceRuling:InterferenceObstructionRuling}> | Readonly<{resultId:"secondary-result.offensive-interference";interferenceRuling:InterferenceOffensiveRuling}>);
export type BattingInterferencePenaltyPlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:BattingInterferencePenaltyObservations;participants:Participants;calculation:CalculationFor<BattingInterferencePenaltyT1Input>}>;
export type BattingInterferencePlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:BattingInterferencePlayObservations;participants:Participants;calculation:CalculationFor<BattingInterferencePlayT1Input>}>;
export type AdjudicatedInterferencePlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:AdjudicatedInterferenceObservations;participants:Participants;calculation:CalculationFor<AdjudicatedInterferenceT1Input>}>;
export type LineupPlayPrefixV7 = RunnerPlayPrefixV7 | NonplayNormalV7 | PitchPlayPrefixV7 | IntentionalWalkPlayPrefixV7 | {[R in BattedHitResult]:BattedHitPlayPrefixV7<R>}[BattedHitResult] | BattingInterferencePenaltyPlayPrefixV7 | BattingInterferencePlayPrefixV7 | AdjudicatedInterferencePlayPrefixV7;
export type LineupPlayPrefixV8=HistoryEntry["difference"];

/** 明示した観測を保持する。配置・因果・実IDの相関は唯一核/codecで照合する。 */
import type {Uuid,BattedRbiRulingByRunner,BattedForceOutRunner} from "./lineup_play_prefix_v1";
export type BattedNoErrorScoring = Readonly<{kind:"no-error";errorCount:"0";fielders:readonly []}>;
export type BattedRecordedErrorScoring = Readonly<{kind:"error-recorded";errors:readonly [Readonly<{fielder:Readonly<{kind:"official";player_id:Uuid}>;count:1}>]}>;
type BattedObservationCommon = Readonly<{pitchTypeKey:Observations["pitchTypeKey"];course:Observations["course"];pitchSpeed:Observations["pitchSpeed"];stance:Observations["stance"];battingSide:Observations["battingSide"];battedBall:Readonly<{typeKey:string|null;strengthKey:string|null;hitX:string|null;hitY:string|null;rawFielderPosition:string|null;resolvedFielderId:string|null}>;interferenceRuling:Readonly<{kind:"not-required"}>;runnerAdvanceOverridesByRunner:Readonly<{kind:"not-applied";overrides:readonly []}>|Readonly<{kind:"applied";overrides:readonly Readonly<{runnerBase:"1"|"2"|"3";destination:"1"|"2"|"3"|"4"}>[]}>;thirdOutTimingByRunner:Readonly<Record<string,never>>}>;
export type BattedHitObservations =
 (BattedObservationCommon & Readonly<{resultId:"batting-result.single"|"batting-result.double"|"batting-result.triple"|"batting-result.batted-reach"|"batting-result.fielders-choice"|"batting-result.sacrifice-bunt"|"batting-result.sacrifice-fly";officialScoringPayload:BattedNoErrorScoring;thirdOutObservation:Readonly<{kind:"none"}>;rbiRulingByRunner?:BattedRbiRulingByRunner;outRunner?:never}>)
 | (BattedObservationCommon & Readonly<{resultId:"batting-result.home-run";officialScoringPayload:BattedNoErrorScoring;thirdOutObservation:Readonly<{kind:"none"}>;rbiRulingByRunner?:never;outRunner?:never}>)
 | (BattedObservationCommon & Readonly<{resultId:"batting-result.batted-out";officialScoringPayload:BattedNoErrorScoring;thirdOutObservation:Readonly<{kind:"none"}>|Readonly<{kind:"batter-before-first";batter:Readonly<{kind:"official";player_id:Uuid}>}>;rbiRulingByRunner?:BattedRbiRulingByRunner;outRunner?:never}>)
 | (Omit<BattedObservationCommon,"runnerAdvanceOverridesByRunner"> & Readonly<{resultId:"batting-result.double-play";officialScoringPayload:BattedNoErrorScoring;thirdOutObservation:Readonly<{kind:"none"}>;runnerAdvanceOverridesByRunner:Readonly<{kind:"not-applied";overrides:readonly []}>;outRunner:BattedForceOutRunner;rbiRulingByRunner?:never}>)
 | (BattedObservationCommon & Readonly<{resultId:"batting-result.error"|"batting-result.sacrifice-bunt-error";officialScoringPayload:BattedRecordedErrorScoring;thirdOutObservation:Readonly<{kind:"none"}>;rbiRulingByRunner?:never;outRunner?:never}>);
export type {WireHead} from "./lineup_play_prefix_v1";

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
