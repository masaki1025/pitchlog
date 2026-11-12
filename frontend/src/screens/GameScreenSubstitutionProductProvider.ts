/** 真正GETで照合済みの交代文脈を画面要求と閉P2候補へ変換する。 */
import type { CheckpointRef } from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import {
  isSubstitutionState,
  type Side,
  type Slot,
  type SubstitutionOperation,
  type SubstitutionResult,
  type SubstitutionState,
} from '../domain/substitutionKernel'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import { isNonplayDefinition } from '../api/nonplayContract'
import {
  substitutionEvent,
  type SubstitutionPayload,
} from '../api/substitutionWire'
import type { SyncEvent } from '../lib/sync/syncEvent'
import type { PlayerCreate } from '../api/roster'
import { ApiError } from '../api/client'
import type {
  PlayerRegistrationDraft,
  RawSubstitutionDraft,
  SubstitutionChoice,
  SubstitutionOperationSupply,
  SubstitutionRequest,
  SubstitutionQuestion,
  SubstitutionValidation,
} from './GameScreenSubstitutionTypes'

export type VerifiedSubstitutionContext = Readonly<{
  tenantId: string
  gameId: string
  generation: string
  recoveryGeneration: string
  awayLineupId: string
  homeLineupId: string
  checkpoint: CheckpointRef
  nextD1: number
  nextD2: number
  /** 真正CPのstateFieldsから取得した、投手交代時のカウント。 */
  currentCount: Readonly<{
    strikes: '0' | '1' | '2'
    balls: '0' | '1' | '2' | '3'
  }>
  state: SubstitutionState
  /** 同tenant・同試合の実roster/登録イベントから照合された選手だけ。 */
  eligibleBySide: Readonly<Record<Side, readonly SubstitutionChoice[]>>
  /** このCPの検査済みGETからだけ供給する表示名。 */
  names: Readonly<Record<string, string>>
  /** 同じGET窓の登録選手pageで得た当時の背番号。 */
  uniformNumbers: Readonly<Record<string, string | null>>
}>

export type PreparedSubstitution = Readonly<{
  event: SyncEvent
  prediction: Extract<SubstitutionResult, { ok: true }>
}>

/** 画面は唯一配布artifactを呼ぶ。閉応答以外を保存候補にしない。 */
function calculate(
  state: SubstitutionState,
  selected: SubstitutionOperation,
  eligibleIncomingIds: string[],
): SubstitutionResult {
  const value = invokeFirstBallDomain('applySubstitutionV1', {
    version: 'substitution-calculation-v1',
    state,
    operation: selected,
    eligibleIncomingIds,
  })
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('交代artifactの応答が不正です')
  const result = value as Record<string, unknown>
  if (
    result.ok === true &&
    Object.keys(result).sort().join(',') ===
      'continuationLineup,ok,state,warnings' &&
    isSubstitutionState(result.state) &&
    Array.isArray(result.warnings) &&
    result.warnings.every(
      (w) =>
        w === 'fielding-position-missing' ||
        w === 'fielding-position-duplicate',
    ) &&
    (result.continuationLineup === null ||
      isNonplayDefinition(
        result.continuationLineup,
        'Lineup',
        'lineup_play_prefix_schema_v1',
      ))
  )
    return value as SubstitutionResult
  if (
    result.ok === false &&
    Object.keys(result).sort().join(',') === 'error,ok' &&
    typeof result.error === 'string' &&
    [
      'invalid-source',
      'invalid-operation',
      'unavailable-player',
      'reentry',
      'current-player-mismatch',
      'ambiguous-responsibility',
      'unsupported-dh-route',
    ].includes(result.error)
  )
    return value as SubstitutionResult
  throw new Error('交代artifactの閉応答が不一致です')
}

const position = (value: string | null | undefined): value is Slot =>
  value !== undefined && value !== null && /^[1-9]$/.test(value)
const side = (value: string | null | undefined): value is Side =>
  value === 'away' || value === 'home'
const count = (
  value: string | null | undefined,
  max: number,
): value is '0' | '1' | '2' | '3' =>
  value !== undefined &&
  value !== null &&
  /^[0-3]$/.test(value) &&
  Number(value) <= max

/** 同一CP内だけで下書きの検証と保存候補を結び直す鍵。 */
export function substitutionContextKey(c: VerifiedSubstitutionContext): string {
  return `${c.tenantId}/${c.gameId}/${c.generation}/${c.checkpoint.id}/${c.checkpoint.revision}/${c.checkpoint.digest}/${c.nextD1}`
}

function choices(
  c: VerifiedSubstitutionContext,
  ids: readonly string[],
): SubstitutionChoice[] {
  return [...new Set(ids)].map((id) => ({ id, label: c.names[id] ?? id }))
}

/** 画面の登録下書きを正式な選手作成入力へ写す。不正は null で閉じる。 */
export function playerRegistration(
  draft: PlayerRegistrationDraft,
  teamId: string,
): PlayerCreate | null {
  const field = (key: string): string => {
    const value = draft.answers[key]
    return typeof value === 'string' ? value.trim() : ''
  }
  const name = field('name')
  const throws = field('throws')
  const bats = field('bats')
  const uniform = field('uniformNumber')
  if (
    !name ||
    (throws !== 'right' && throws !== 'left') ||
    (bats !== 'right' && bats !== 'left' && bats !== 'both')
  )
    return null
  return {
    team_record_id: teamId,
    name,
    throws,
    bats,
    uniform_number: uniform === '' ? null : uniform,
    roster_status_key: 'active',
  }
}

/** 登録失敗を入力拒否と結果不明へ分け、結果不明だけ名簿再取得を要求する。 */
export function registrationFailure(error: unknown): {
  message: string
  reload: boolean
} {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500)
    return {
      message: '選手を登録できませんでした。入力内容を確認してください',
      reload: false,
    }
  return {
    message:
      '登録結果を確認できません。名簿を再取得し、同じ選手が登録されていないか確認してください',
    reload: true,
  }
}

/** その場登録の入力項目。登録APIの閉じた入力だけを供給し、意味判定はAPIへ委ねる。 */
const registrationQuestions: readonly SubstitutionQuestion[] = [
  { key: 'name', label: '選手名', input: 'text', required: true },
  {
    key: 'throws',
    label: '投',
    input: 'choice',
    required: true,
    options: [
      { id: 'right', label: '右' },
      { id: 'left', label: '左' },
    ],
  },
  {
    key: 'bats',
    label: '打',
    input: 'choice',
    required: true,
    options: [
      { id: 'right', label: '右' },
      { id: 'left', label: '左' },
      { id: 'both', label: '両' },
    ],
  },
  {
    key: 'uniformNumber',
    label: '背番号（任意）',
    input: 'text',
    required: false,
  },
]

/** 選手候補と設問はGET由来の実配置・実在籍から供給し、画面に意味判定を置かない。 */
export function substitutionRequest(
  c: VerifiedSubstitutionContext,
): SubstitutionRequest {
  const operations: SubstitutionOperationSupply[] = []
  for (const kind of [
    'pitcher',
    'pinch-hitter',
    'pinch-runner',
    'defense',
  ] as const) {
    const outgoing = new Set<string>()
    for (const team of [c.state.away, c.state.home]) {
      if (kind === 'pitcher' && team.fielding['1'])
        outgoing.add(team.fielding['1'])
      if (kind === 'pinch-hitter')
        Object.values(team.battingOrder).forEach((id) => outgoing.add(id))
      if (kind === 'defense')
        Object.values(team.fielding).forEach((id) => {
          if (id) outgoing.add(id)
        })
    }
    if (kind === 'pinch-runner')
      c.state.runners.forEach((runner) => outgoing.add(runner.runnerId))
    // 対象がいない操作を未取得の空候補として混ぜ、他の交代まで封鎖しない。
    if (outgoing.size === 0) continue
    const incoming = [
      ...c.eligibleBySide.away,
      ...c.eligibleBySide.home,
    ].filter((player) => !c.state.exitedPlayerIds.includes(player.id))
    operations.push({
      kind,
      outgoing: choices(c, [...outgoing]),
      incoming: [...new Map(incoming.map((p) => [p.id, p])).values()],
      registrationQuestions,
      placementQuestions: [],
      questions: [
        {
          key: 'side',
          label: 'チーム',
          input: 'choice',
          required: true,
          options: [
            { id: 'away', label: '先攻' },
            { id: 'home', label: '後攻' },
          ],
        },
        ...(kind === 'pitcher'
          ? [
              {
                key: 'strikes',
                label: '変更時ストライク',
                input: 'choice' as const,
                required: true,
                options: ['0', '1', '2'].map((v) => ({ id: v, label: v })),
              },
              {
                key: 'balls',
                label: '変更時ボール',
                input: 'choice' as const,
                required: true,
                options: ['0', '1', '2', '3'].map((v) => ({ id: v, label: v })),
              },
              {
                key: 'dh',
                label: 'DH',
                input: 'choice' as const,
                required: true,
                options: [
                  { id: 'retain', label: '継続' },
                  { id: 'pitcher-takes-dh-slot', label: '投手がDH枠に入る' },
                ],
              },
            ]
          : kind === 'pinch-hitter'
            ? [
                {
                  key: 'battingSlot',
                  label: '打順',
                  input: 'choice' as const,
                  required: true,
                  options: '123456789'
                    .split('')
                    .map((v) => ({ id: v, label: v })),
                },
              ]
            : kind === 'pinch-runner'
              ? [
                  {
                    key: 'base',
                    label: '塁',
                    input: 'choice' as const,
                    required: true,
                    options: ['1', '2', '3'].map((v) => ({ id: v, label: v })),
                  },
                ]
              : [
                  {
                    key: 'position',
                    label: '守備位置',
                    input: 'choice' as const,
                    required: true,
                    options: '123456789'
                      .split('')
                      .map((v) => ({ id: v, label: v })),
                  },
                ]),
      ],
    })
  }
  return { contextKey: substitutionContextKey(c), operations }
}

function operation(
  c: VerifiedSubstitutionContext,
  draft: RawSubstitutionDraft,
): SubstitutionOperation | null {
  const outgoingId = draft.outgoingId,
    incomingId = draft.incomingId
  if (
    draft.identity.contextKey !== substitutionContextKey(c) ||
    draft.identity.targetId !== outgoingId ||
    draft.incomingMode !== 'existing' ||
    !outgoingId ||
    !incomingId ||
    !side(draft.answers.side)
  )
    return null
  const selectedSide = draft.answers.side
  const keys = Object.keys(draft.answers).sort().join(',')
  if (draft.identity.operation === 'pitcher') {
    if (
      keys !== 'balls,dh,side,strikes' ||
      !count(draft.answers.strikes, 2) ||
      !count(draft.answers.balls, 3) ||
      draft.answers.strikes !== c.currentCount.strikes ||
      draft.answers.balls !== c.currentCount.balls ||
      (draft.answers.dh !== 'retain' &&
        draft.answers.dh !== 'pitcher-takes-dh-slot')
    )
      return null
    return {
      kind: 'pitcher',
      side: selectedSide,
      outgoingId,
      incomingId,
      count: {
        strikes: draft.answers.strikes as '0' | '1' | '2',
        balls: draft.answers.balls as '0' | '1' | '2' | '3',
      },
      dh: draft.answers.dh,
    }
  }
  if (draft.identity.operation === 'pinch-hitter') {
    if (keys !== 'battingSlot,side' || !position(draft.answers.battingSlot))
      return null
    return {
      kind: 'pinch-hitter',
      side: selectedSide,
      outgoingId,
      incomingId,
      battingSlot: draft.answers.battingSlot,
    }
  }
  if (draft.identity.operation === 'pinch-runner') {
    if (
      keys !== 'base,side' ||
      !['1', '2', '3'].includes(draft.answers.base ?? '')
    )
      return null
    return {
      kind: 'pinch-runner',
      side: selectedSide,
      outgoingId,
      incomingId,
      base: draft.answers.base as '1' | '2' | '3',
    }
  }
  if (draft.identity.operation === 'defense') {
    if (keys !== 'position,side' || !position(draft.answers.position))
      return null
    return {
      kind: 'defense',
      side: selectedSide,
      changes: [{ position: draft.answers.position, outgoingId, incomingId }],
    }
  }
  return null
}

export function validateSubstitutionDraft(
  c: VerifiedSubstitutionContext,
  draft: RawSubstitutionDraft,
): SubstitutionValidation {
  const selected = operation(c, draft)
  const candidate =
    selected &&
    calculate(
      c.state,
      selected,
      c.eligibleBySide[selected.side].map((player) => player.id),
    )
  return {
    identity: draft.identity,
    kind: candidate?.ok ? 'valid' : 'invalid',
    messages: candidate && !candidate.ok ? [candidate.error] : [],
  }
}

/** 検証済み同CPの下書きだけを候補化する。保存・GET後の状態はACKと実読取で確定する。 */
export function prepareSubstitution(
  c: VerifiedSubstitutionContext,
  draft: RawSubstitutionDraft,
  d5: string,
  eventId: string,
): PreparedSubstitution | null {
  const selected = operation(c, draft)
  if (!selected) return null
  const prediction = calculate(
    c.state,
    selected,
    c.eligibleBySide[selected.side].map((player) => player.id),
  )
  if (!prediction.ok) return null
  const incoming =
    selected.kind === 'defense'
      ? selected.changes
          .map((change) => change.incomingId)
          .filter((id): id is string => id !== null)
      : [selected.incomingId]
  if (incoming.some((id) => !Object.hasOwn(c.uniformNumbers, id))) return null
  const payload: SubstitutionPayload = {
    formatVersion: 'substitution-event-v1',
    expectedCheckpoint: structuredClone(c.checkpoint),
    eventId,
    operation: selected,
    incomingSnapshots: incoming.map((playerId) => ({
      playerId,
      uniformNumber: c.uniformNumbers[playerId]!,
    })),
  }
  return {
    event: substitutionEvent(c.gameId, c.generation, d5, c.nextD2, payload),
    prediction,
  }
}
