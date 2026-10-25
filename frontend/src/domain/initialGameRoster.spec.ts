import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type {
  Request,
  Response,
} from '../../../contracts/state-transition/initial_game_roster_v1'
import { validateInitialGameRoster } from './initialGameRoster'

type Case = { id: string; request: Request; expected: Response }
const cases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/initial_game_roster_cases_v1.json',
    ),
    'utf8',
  ),
).cases as Case[]
const noDh = cases.find((c) => c.id === 'NORMAL-DH-false')!
const withDh = cases.find((c) => c.id === 'NORMAL-DH-true')!

function invoke(input: unknown): Response {
  return JSON.parse(
    validateInitialGameRoster(JSON.stringify(input)),
  ) as Response
}

/** 試験対象の全objectへ余剰/欠落を入れる。業務判定は実装しない。 */
function* objects(value: unknown): Generator<Record<string, unknown>> {
  if (Array.isArray(value)) {
    for (const item of value) yield* objects(item)
  } else if (value !== null && typeof value === 'object') {
    yield value as Record<string, unknown>
    for (const item of Object.values(value)) yield* objects(item)
  }
}

function freeze(value: unknown): void {
  if (value !== null && typeof value === 'object') {
    for (const item of Object.values(value)) freeze(item)
    Object.freeze(value)
  }
}

describe('初期名簿の単一純核', () => {
  it.each(cases)('$id 全値が採用caseと一致する', ({ request, expected }) => {
    expect(invoke(request)).toEqual(expected)
  })
  it.each(cases)('$id 両sideを交換しても同じ意味で検査する', (item) => {
    const input = {
      ...item.request,
      away: item.request.home,
      home: item.request.away,
    }
    const expected = structuredClone(item.expected)
    if (expected.ok) {
      const [away, home] = expected.value.teams
      Object.assign(expected, {
        value: {
          teams: [
            { ...home, side: 'away' },
            { ...away, side: 'home' },
          ],
        },
      })
    }
    expect(invoke(input)).toEqual(expected)
  })
  it.each([noDh, withDh])(
    '$id を凍結しても全ID/配置/順序を保持する',
    (item) => {
      const input = structuredClone(item.request)
      const before = JSON.stringify(input)
      freeze(input)
      const first = invoke(input)
      expect(first).toEqual(item.expected)
      expect(invoke(input)).toEqual(first)
      expect(JSON.stringify(input)).toBe(before)
      if (!first.ok) throw new Error('正常名簿のprojectionがない')
      expect(Object.keys(first.value)).toEqual(['teams'])
      for (const [index, side] of [input.away, input.home].entries()) {
        expect(
          first.value.teams[index]!.participants.map((p) => p.player.player_id),
        ).toEqual(side.entries.map((p) => p.player_id))
      }
    },
  )
  it('入力の全objectでextra/欠落を補完しない', () => {
    const original = structuredClone(withDh.request)
    const all = [...objects(original)]
    for (const object of all) {
      object.unknown = true
      expect(invoke(original)).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
      delete object.unknown
      for (const key of Object.keys(object)) {
        const saved = object[key]
        delete object[key]
        expect(invoke(original)).toEqual({
          ok: false,
          error: { code: 'INVALID_REQUEST' },
        })
        object[key] = saved
      }
    }
  })
  it.each(['away', 'home'] as const)(
    '%sの打順/守備/UUID型を暗黙変換しない',
    (side) => {
      for (const value of [
        0,
        1,
        true,
        '01',
        '1\n',
        '1\r\n',
        '1 ',
        '0',
        '10',
        '-1',
        '1e0',
      ]) {
        for (const field of ['batting', 'fielding']) {
          const input = structuredClone(noDh.request)
          const entry = input[side].entries[0]!
          Object.assign(
            entry,
            field === 'batting'
              ? { batting_order: value }
              : { fielding_position: { kind: 'fielding', position: value } },
          )
          expect(invoke(input)).toEqual({
            ok: false,
            error: { code: 'INVALID_DECIMAL_INTEGER' },
          })
        }
      }
      for (const value of [
        null,
        1,
        '',
        'INVALID',
        '00000000-0000-4000-8000-00000000010a\n',
        '00000000-0000-4000-8000-00000000010A',
      ]) {
        const input = structuredClone(noDh.request)
        Object.assign(input[side].entries[0]!, { player_id: value })
        expect(invoke(input)).toEqual({
          ok: false,
          error: { code: 'INVALID_REQUEST' },
        })
      }
    },
  )
  it.each(['away', 'home'] as const)('%sの8/11人外形を拒否する', (side) => {
    for (const entries of [
      noDh.request[side].entries.slice(1),
      [...withDh.request[side].entries, withDh.request[side].entries[0]!],
    ]) {
      const input = structuredClone(noDh.request)
      Object.assign(input[side], { entries })
      expect(invoke(input)).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
    }
  })
  it.each(['away', 'home'] as const)(
    '%sのDH欠如/投手兼DH推測を拒否する',
    (side) => {
      const input = structuredClone(withDh.request)
      Object.assign(input[side].entries[9]!, {
        fielding_position: { kind: 'designated-hitter', position: '1' },
      })
      expect(invoke(input)).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
    },
  )
  it('raw構文と型不正を新操作だけの閉失敗へ写す', () => {
    expect(JSON.parse(validateInitialGameRoster('{'))).toEqual({
      ok: false,
      error: { code: 'INVALID_JSON' },
    })
    expect(
      JSON.parse(validateInitialGameRoster(null as unknown as string)),
    ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
  })
  it('cross-side同UUIDは在籍証明にせず、構造projectionだけを返す', () => {
    const input = structuredClone(noDh.request)
    Object.assign(input.home.entries[0]!, {
      player_id: input.away.entries[0]!.player_id,
    })
    const result = invoke(input)
    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error('構造projectionがない')
    expect(Object.keys(result.value)).toEqual(['teams'])
    expect(JSON.stringify(result)).not.toContain('authorized')
    expect(JSON.stringify(result)).not.toContain('point')
  })
})

it.each(['away', 'home'] as const)(
  '%sの整数不正より全side/階層の形状不正を先に拒否する',
  (decimalSide) => {
    const otherSide = decimalSide === 'away' ? 'home' : 'away'
    for (const numberField of ['batting', 'position']) {
      for (const fault of [
        'root',
        'other-side-extra',
        'other-team-uuid',
        'same-entry-player-missing',
        'same-entry-player-invalid',
        'same-entry-role-extra',
        'later-same-entry-missing',
        'other-entry-missing',
        'other-role-unknown',
        'other-side-entries8',
      ]) {
        const input = structuredClone(noDh.request)
        const entry = input[decimalSide].entries[0]!
        if (numberField === 'batting')
          Object.assign(entry, { batting_order: '01' })
        else
          Object.assign(entry, {
            fielding_position: { kind: 'fielding', position: '01' },
          })
        if (fault === 'root') Object.assign(input, { dh: 'false' })
        if (fault === 'other-side-extra')
          Object.assign(input[otherSide], { extra: true })
        if (fault === 'other-team-uuid')
          Object.assign(input[otherSide], { team_id: 'invalid' })
        if (fault === 'same-entry-player-missing')
          Reflect.deleteProperty(entry, 'player_id')
        if (fault === 'same-entry-player-invalid')
          Object.assign(entry, { player_id: 'invalid' })
        if (fault === 'same-entry-role-extra')
          Object.assign(entry.fielding_position, { extra: true })
        if (fault === 'later-same-entry-missing')
          Reflect.deleteProperty(input[decimalSide].entries[8]!, 'player_id')
        if (fault === 'other-entry-missing')
          Reflect.deleteProperty(input[otherSide].entries[0]!, 'player_id')
        if (fault === 'other-role-unknown')
          Object.assign(input[otherSide].entries[0]!, {
            fielding_position: { kind: 'unknown' },
          })
        if (fault === 'other-side-entries8')
          Object.assign(input[otherSide], {
            entries: input[otherSide].entries.slice(1),
          })
        expect(invoke(input), `${decimalSide}/${numberField}/${fault}`).toEqual(
          { ok: false, error: { code: 'INVALID_REQUEST' } },
        )
      }
    }
  },
)
