import { describe, expect, it } from 'vitest'
import {
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_RULES,
  resolveEventFieldPresence,
} from '../lib/sync/eventFieldRules'
import {
  buildPitchEventDraft,
  PITCH_EVENT_DEFERRED_SLOT_IDS,
  PITCH_EVENT_DRAFT_SLOT_IDS,
  PITCH_EVENT_DRAFT_VIOLATION,
  PITCH_EVENT_KIND,
  PITCH_EVENT_PATH,
  PITCH_EVENT_REQUIRED_SLOT_IDS,
  type PitchEventDraftInput,
} from './GameScreenPitchEvent'

const d5 = '0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b'
const gameId = 'f1e2d3c4-b5a6-4789-9abc-def012345678'

function input(overrides: Partial<PitchEventDraftInput> = {}) {
  return {
    d5,
    d4: 'opaque-d4-token',
    gameId,
    d2: '0007',
    payload: { pitchTypeId: 'fastball', resultId: 'ball' },
    ...overrides,
  } satisfies PitchEventDraftInput
}

function fieldsOf(result: ReturnType<typeof buildPitchEventDraft>) {
  if (!result.ok) {
    throw new Error(`下書きの組み立てに失敗した: ${result.reason.violation}`)
  }
  return result.draft.fields
}

describe('1 球の下書きのスロット集合', () => {
  it('正本の要否から導いた必須スロットが、下書きの分と繰り延べた分に過不足なく分かれる', () => {
    expect([...PITCH_EVENT_REQUIRED_SLOT_IDS].sort()).toEqual(
      [...PITCH_EVENT_DRAFT_SLOT_IDS, ...PITCH_EVENT_DEFERRED_SLOT_IDS].sort(),
    )
    expect(PITCH_EVENT_DRAFT_SLOT_IDS).not.toHaveLength(0)
  })

  it('繰り延べるのは D1 と状態差分の 2 つだけである', () => {
    expect([...PITCH_EVENT_DEFERRED_SLOT_IDS].sort()).toEqual(['V2', 'V8'])
  })

  it('毎球入力は取消可能な操作なので状態差分が必須である（第 1 期で確定できない理由）', () => {
    const stateDiffRule = EVENT_FIELD_RULES.find((rule) => rule.id === 'V8')
    expect(stateDiffRule).toBeDefined()
    expect(
      resolveEventFieldPresence(stateDiffRule!, {
        path: PITCH_EVENT_PATH,
        eventKind: PITCH_EVENT_KIND,
        participation: PITCH_EVENT_KIND.participation,
        cancellable: true,
      }),
    ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
  })
})

describe('1 球の下書きの組み立て', () => {
  it('下書きに D1 と状態差分を入れず、残りの必須スロットだけを埋める', () => {
    const fields = fieldsOf(buildPitchEventDraft(input()))

    expect(Object.keys(fields).sort()).toEqual(
      [...PITCH_EVENT_DRAFT_SLOT_IDS].sort(),
    )
    expect('V2' in fields).toBe(false)
    expect('V8' in fields).toBe(false)
  })

  it('確定値を解釈せず、そのままスロットへ載せる', () => {
    const fields = fieldsOf(buildPitchEventDraft(input()))

    expect(fields.V1).toBe(d5)
    expect(fields.V3).toBe('opaque-d4-token')
    expect(fields.V4).toBe(gameId)
    expect(fields.V5).toBe(PITCH_EVENT_KIND.id)
    expect(fields.V6).toBe('0007')
    expect(fields.V7).toEqual({ pitchTypeId: 'fastball', resultId: 'ball' })
  })

  it('種別は正本の写しの毎球入力であり、経路は P2 である', () => {
    expect(PITCH_EVENT_KIND.name).toBe('毎球入力')
    expect(PITCH_EVENT_PATH).toBe('P2')
  })

  it('同じ入力から同じ下書きを作り、入力オブジェクトを変更しない', () => {
    const source = input()
    const snapshot = structuredClone(source)

    const first = fieldsOf(buildPitchEventDraft(source))
    const second = fieldsOf(buildPitchEventDraft(source))

    expect(first).toEqual(second)
    expect(source).toEqual(snapshot)
  })

  it('組み立て後に呼出元が payload を書き換えても下書きが変わらない', () => {
    const source = input()
    const fields = fieldsOf(buildPitchEventDraft(source))

    source.payload.resultId = 'strike'

    expect(fields.V7).toEqual({ pitchTypeId: 'fastball', resultId: 'ball' })
  })

  it('入れ子を書き換えても下書きが変わらない', () => {
    const source = input({
      payload: { pitchTypeId: 'fastball', detail: { speed: 140 } },
    })
    const fields = fieldsOf(buildPitchEventDraft(source))

    ;(source.payload.detail as { speed: number }).speed = 150

    expect(fields.V7).toEqual({
      pitchTypeId: 'fastball',
      detail: { speed: 140 },
    })
  })
})

describe('1 球の下書きが組み立てられない入力', () => {
  it.each([
    ['大文字を含む', '0B5F1C2E-3A4D-4E5F-8A9B-0C1D2E3F4A5B'],
    ['ハイフンがない', '0b5f1c2e3a4d4e5f8a9b0c1d2e3f4a5b'],
    ['波括弧つき', '{0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b}'],
    ['空文字', ''],
  ])('D5 が UUID の正規形でない(%s)ときは作らない', (_label, value) => {
    const result = buildPitchEventDraft(input({ d5: value }))

    expect(result).toEqual({
      ok: false,
      reason: {
        violation: PITCH_EVENT_DRAFT_VIOLATION.INVALID_D5,
        target: 'd5',
      },
    })
  })

  it('試合の識別が UUID の正規形でないときは作らない', () => {
    const result = buildPitchEventDraft(input({ gameId: 'game-1' }))

    expect(result).toEqual({
      ok: false,
      reason: {
        violation: PITCH_EVENT_DRAFT_VIOLATION.INVALID_GAME_ID,
        target: 'game_id',
      },
    })
  })

  it('D4 が空文字のときは作らない', () => {
    const result = buildPitchEventDraft(input({ d4: '' }))

    expect(result).toEqual({
      ok: false,
      reason: {
        violation: PITCH_EVENT_DRAFT_VIOLATION.INVALID_D4,
        target: 'd4',
      },
    })
  })

  it('D2 が欠けているときは作らない', () => {
    const result = buildPitchEventDraft(input({ d2: undefined }))

    expect(result).toEqual({
      ok: false,
      reason: {
        violation: PITCH_EVENT_DRAFT_VIOLATION.MISSING_D2,
        target: 'd2',
      },
    })
  })

  it.each([
    ['配列', [] as unknown],
    ['null', null as unknown],
    ['文字列', 'payload' as unknown],
  ])(
    'payload が JSON のオブジェクトでない(%s)ときは作らない',
    (_label, value) => {
      const result = buildPitchEventDraft(
        input({ payload: value as Record<string, unknown> }),
      )

      expect(result).toEqual({
        ok: false,
        reason: {
          violation: PITCH_EVENT_DRAFT_VIOLATION.INVALID_PAYLOAD,
          target: 'payload',
        },
      })
    },
  )
})
