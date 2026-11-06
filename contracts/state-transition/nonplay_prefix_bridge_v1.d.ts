/** 共通prefix橋の候補。参照値だけでは認可・原本・計算・保存資格にならない。 */
import type { Request as UndoRequest, AppliedValue, StateFields } from "./undo_v1";
import type { Scoreboard, BattingOrderBySide, HistoryEntry, SavedRuleWire,
  Lineup, Participant, Runner, Responsibility, T2 } from "./lineup_play_prefix_v1";
/** schemaで正準十進/EOSを検査する。桁数・stack深さの新上限なし。 */
export type Unsigned = string;
export type Positive = string;
export type Uuid = string;
export type Digest = string;
/** 既E1 wire-v1タグを全値保持する。旧plain64も保持しstrip/再hashしない。 */
export type Fingerprint = string;
export type Generation = string;
/** 既sync HTTPの正整数safe範囲。内部の十進文字列と混同しない。 */
export type WireD1 = number;
export type Scope = Readonly<{ tenantId: Uuid; gameId: Uuid; generation: Generation }>;
export type CheckpointRef = Readonly<{ id: Uuid; revision: Positive; digest: Digest }>;
export type EventSource = Readonly<{ eventId: Uuid; gameId: Uuid; generation: Generation;
  d1: Positive; d5: Uuid; fingerprint: Fingerprint; eventKind: "play_input" | "undo" | "substitution" | "game_end_declaration" | "game_reopen" }>;
export type D1Head = Readonly<{ kind: "accepted-event"; source: EventSource }>;
export type ProjectionHead = Readonly<{ kind: "started-game"; eventId: Uuid }> |
  Readonly<{ kind: "d1-event"; source: EventSource }>;
export type ActivePlay = Readonly<{ source: EventSource; playId: Uuid;
  d2: Unsigned; physicalPlayNumber: Positive }>;
export type Current = Readonly<{ stateFields: StateFields; scoreboard: Scoreboard;
  battingOrderBySide: BattingOrderBySide }>;
/** 保存済み原本から導出する復元文脈。別の可変stack正本を作らない。 */
export type RestoreContext = Readonly<{ current: Current; rules: SavedRuleWire;
  rulesDigest: Digest; layoutDigest: Digest; rosterDigest: Digest; lineup: Lineup;
  participants: Participant; runners: readonly Runner[]; responsibility: Responsibility;
  lastPlayEvaluation: T2 | null; substitutionState?: SubstitutionState }>;
export type SubstitutionTeam = Readonly<{teamId: Uuid; battingOrder: Readonly<Record<"1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9",Uuid>>;
  fielding: Readonly<Record<"1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9",Uuid|null>>; dhSlot: "1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9"|null}>;
export type SubstitutionResponsibility = Readonly<{kind:"unchanged"}> | Readonly<{kind:"changed-mid-plate-appearance";
  previousPitcherId:Uuid; reliefPitcherId:Uuid; strikesAtChange:"0"|"1"|"2"; ballsAtChange:"0"|"1"|"2"|"3"}>;
export type SubstitutionState = Readonly<{attackingSide:"away"|"home"; away:SubstitutionTeam; home:SubstitutionTeam;
  runners:readonly Runner[]; exitedPlayerIds:readonly Uuid[]; responsibility:SubstitutionResponsibility}>;
export type SubstitutionFrame = Readonly<{source:EventSource; afterPlayId:Uuid|null; beforeContext:RestoreContext; afterContext:RestoreContext}>;
export type LifecycleControlBridge = Readonly<{source:EventSource; action:"end"|"reopen";
  anchorEventId:Uuid; beforeContext:RestoreContext; afterContext:RestoreContext;
  kernel:Readonly<{request:unknown; response:unknown}>; frameId:Uuid; checkpointBefore:CheckpointRef}>;
export type Content = Readonly<{ scope: Scope;
  origin: Readonly<{ kind: "started-game"; eventId: Uuid }>; d3: Unsigned;
  d1Head: D1Head | null; projectionHead: ProjectionHead; activeHead: ActivePlay | null;
  activeDepth: Unsigned; historyVersion: Unsigned; storageHistoryEpoch: Unsigned;
  nextPhysicalPlayNumber: Positive; executionArtifactSha256: Digest; restored: RestoreContext;
  controlBridges?: readonly LifecycleControlBridge[]; substitutionFrames?: readonly SubstitutionFrame[] }>;
export type Checkpoint = Readonly<{ formatVersion: "nonplay-prefix-checkpoint-v1";
  ref: CheckpointRef; content: Content }>;
export type ActiveFrame = Readonly<{ play: ActivePlay; historyEntry: HistoryEntry;
  beforeContext: RestoreContext; afterContext: RestoreContext }>;
export type Source = Readonly<{ formatVersion: "nonplay-prefix-source-v1";
  checkpoint: Checkpoint; activeStack: readonly ActiveFrame[] }>;
export type Calculation = Readonly<{ request: UndoRequest;
  response: Readonly<{ ok: true; value: AppliedValue }> }>;
export type UndoPayload = Readonly<{ formatVersion: "native-undo-prefix-v1";
  artifactSha256: Digest; expectedCheckpoint: CheckpointRef; calculation: Calculation }>;
/** 対象D4はownD4と異なり得る。真正な世代連結とactive先頭を照合する。 */
export type Target = Readonly<{ game: Uuid; d4: Generation; d1: WireD1 }>;
/** V5=undo。V6/D2、V8、V9、V11、event tenantIdは存在しない。 */
export type UndoEvent = Readonly<{ d5: Uuid; d1: WireD1; d4: Generation;
  game_id: Uuid; event_kind: "undo"; payload: UndoPayload; target_reference: Target }>;
