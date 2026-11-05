/** V8は実history差分。v2のbody再送は変更しない。 */
import type {Request,Success,HistoryEntry,PitchT1Input,BattedHitT1Input} from "./lineup_play_prefix_v1";
import type {Observations,Participants} from "./play_prefix_v2_payload_v1";
export type Calculation=Readonly<{formatVersion:"play-prefix-calculation-v3";artifactSha256:string;request:Request;response:Success}>;
type PitchOnlyT1 = PitchT1Input & Readonly<{officialScoringPayload?:never;interferenceRuling?:never;runnerAdvanceOverrides?:never;thirdOutObservation?:never}>;
type PitchOnlyObservations = Observations & Readonly<{[K in Exclude<keyof BattedHitObservations,keyof Observations>]?:never}>;
type CalculationFor<T extends Request["t1"]> = Readonly<Omit<Calculation,"request"> & {request:Readonly<Omit<Request,"t1"> & {t1:T}>}>;
export type PitchPlayPrefixV7 = Readonly<{formatVersion:"play-prefix-play-v3";observations:PitchOnlyObservations;participants:Participants;calculation:CalculationFor<PitchOnlyT1>}>;
export type BattedHitResult = BattedHitT1Input["resultId"];
export type BattedHitPlayPrefixV7<R extends BattedHitResult> = Readonly<{formatVersion:"play-prefix-play-v3";observations:Readonly<Omit<BattedHitObservations,"resultId"> & {resultId:R}>;participants:Participants;calculation:CalculationFor<Readonly<Omit<BattedHitT1Input,"resultId"> & {resultId:R}>>}>;
export type LineupPlayPrefixV7 = NonplayNormalV7 | PitchPlayPrefixV7 | {[R in BattedHitResult]:BattedHitPlayPrefixV7<R>}[BattedHitResult];
export type LineupPlayPrefixV8=HistoryEntry["difference"];

/** 無走者4安打の全明示観測。nullableは未観測の保持であり、値を推測しない。 */
export type BattedHitObservations = Readonly<{
  pitchTypeKey: Observations["pitchTypeKey"];
  course: Observations["course"];
  pitchSpeed: Observations["pitchSpeed"];
  stance: Observations["stance"];
  battingSide: Observations["battingSide"];
  resultId: "batting-result.single" | "batting-result.double" | "batting-result.triple" | "batting-result.home-run";
  battedBall: Readonly<{typeKey:string|null;strengthKey:string|null;hitX:string|null;hitY:string|null;rawFielderPosition:string|null;resolvedFielderId:string|null}>;
  officialScoringPayload: Readonly<{kind:"no-error";errorCount:"0";fielders:readonly []}>;
  interferenceRuling: Readonly<{kind:"not-required"}>;
  runnerAdvanceOverridesByRunner: Readonly<{kind:"not-applied";overrides:readonly []}>;
  thirdOutObservation: Readonly<{kind:"none"}>;
  thirdOutTimingByRunner: Readonly<Record<string,never>>;
}>;

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
