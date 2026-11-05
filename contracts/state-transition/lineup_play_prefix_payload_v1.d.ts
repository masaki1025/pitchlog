/** V8は実history差分。v2のbody再送は変更しない。 */
import type {Request,Success,HistoryEntry} from "./lineup_play_prefix_v1";
import type {Observations,Participants} from "./play_prefix_v2_payload_v1";
export type Calculation=Readonly<{formatVersion:"play-prefix-calculation-v3";artifactSha256:string;request:Request;response:Success}>;
export type LineupPlayPrefixV7=Readonly<{formatVersion:"play-prefix-play-v3";observations:Observations;participants:Participants;calculation:Calculation}>;
export type LineupPlayPrefixV8=HistoryEntry["difference"];
