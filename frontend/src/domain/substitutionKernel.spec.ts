import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type {
  Request,
  Response,
} from '../../../contracts/state-transition/initial_game_roster_v1'
import { validateInitialGameRoster } from './initialGameRoster'
import {
  applySubstitution,
  isSubstitutionState,
  substitutionFromInitialRoster,
  walkResponsiblePitcher,
  type SubstitutionState,
} from './substitutionKernel'

const cases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/initial_game_roster_cases_v1.json',
    ),
    'utf8',
  ),
).cases as { id: string; request: Request }[]

function state(dh = false): SubstitutionState {
  const source = cases.find(
    (entry) => entry.id === (dh ? 'NORMAL-DH-true' : 'NORMAL-DH-false'),
  )!
  const response = JSON.parse(
    validateInitialGameRoster(JSON.stringify(source.request)),
  ) as Response
  if (!response.ok) throw new Error('既初期配置caseが不成立')
  return substitutionFromInitialRoster(response.value, 'away')
}

const newcomer = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const nextNewcomer = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

describe('交代の唯一更新核', () => {
  it('保存状態の閉形は旧正例を通し、未知memberと不正責任を拒否する', () => {
    const accepted = state()
    expect(isSubstitutionState(accepted)).toBe(true)
    expect(isSubstitutionState({ ...accepted, unknown: null })).toBe(false)
    expect(
      isSubstitutionState({
        ...accepted,
        responsibility: {
          kind: 'changed-mid-plate-appearance',
          previousPitcherId: newcomer,
          reliefPitcherId: newcomer,
          strikesAtChange: '1',
          ballsAtChange: '2',
        },
      }),
    ).toBe(false)
  })
  it.each([
    ['0', '0', false],
    ['0', '1', false],
    ['0', '2', false],
    ['1', '0', false],
    ['1', '1', false],
    ['1', '2', false],
    ['2', '0', true],
    ['2', '1', true],
    ['2', '2', false],
    ['3', '0', true],
    ['3', '1', true],
    ['3', '2', true],
  ] as const)('四球の責任: %s-%s', (balls, strikes, previous) => {
    const responsibility = {
      kind: 'changed-mid-plate-appearance' as const,
      previousPitcherId: newcomer,
      reliefPitcherId: nextNewcomer,
      strikesAtChange: strikes,
      ballsAtChange: balls,
    }
    expect(walkResponsiblePitcher(responsibility, nextNewcomer)).toBe(
      previous ? newcomer : nextNewcomer,
    )
  })
  it('投手交代は投捕/打順と打席途中の責任証拠を更新し、旧走者の責任を維持する', () => {
    const original = state()
    const previous = original.home.fielding['1']!
    const runner = {
      runnerId: original.away.battingOrder['3'],
      responsiblePitcherId: previous,
      base: '1' as const,
      status: '継続' as const,
      statusSource: 'auto' as const,
    }
    const source = { ...original, runners: [runner] }
    const result = applySubstitution(
      source,
      {
        kind: 'pitcher',
        side: 'home',
        outgoingId: previous,
        incomingId: newcomer,
        count: { strikes: '1', balls: '2' },
        dh: 'retain',
      },
      [newcomer],
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.state.home.fielding['1']).toBe(newcomer)
    expect(result.state.home.battingOrder['1']).toBe(newcomer)
    expect(result.state.responsibility).toEqual({
      kind: 'changed-mid-plate-appearance',
      previousPitcherId: previous,
      reliefPitcherId: newcomer,
      strikesAtChange: '1',
      ballsAtChange: '2',
    })
    expect(result.state.runners).toEqual([runner])
    expect(result.continuationLineup?.home.pitcherId).toBe(newcomer)
    expect(source.home.fielding['1']).toBe(previous)
  })

  it('代打は同打順枠を新選手へ渡し、守備欠員は警告する', () => {
    const source = state()
    const outgoingId = source.away.battingOrder['3']
    const result = applySubstitution(
      source,
      {
        kind: 'pinch-hitter',
        side: 'away',
        outgoingId,
        incomingId: newcomer,
        battingSlot: '3',
      },
      [newcomer],
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.state.away.battingOrder['3']).toBe(newcomer)
    expect(result.state.away.fielding['3']).toBeNull()
    expect(result.warnings).toContain('fielding-position-missing')
    expect(result.state.exitedPlayerIds).toContain(outgoingId)
    expect(result.continuationLineup?.away.battingOrder['3']).toBe(newcomer)
    expect(
      applySubstitution(
        result.state,
        {
          kind: 'pinch-hitter',
          side: 'away',
          outgoingId: newcomer,
          incomingId: outgoingId,
          battingSlot: '3',
        },
        [outgoingId],
      ),
    ).toEqual({ ok: false, error: 'reentry' })
  })

  it('代走は走者の責任投手を継承し、旧選手の打順も同枠で更新する', () => {
    const original = state()
    const outgoingId = original.away.battingOrder['4']
    const responsiblePitcherId = original.home.fielding['1']!
    const source = {
      ...original,
      runners: [
        {
          runnerId: outgoingId,
          responsiblePitcherId,
          base: '2' as const,
          status: '継続' as const,
          statusSource: 'auto' as const,
        },
      ],
    }
    const result = applySubstitution(
      source,
      {
        kind: 'pinch-runner',
        side: 'away',
        outgoingId,
        incomingId: newcomer,
        base: '2',
      },
      [newcomer],
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.state.runners[0]).toMatchObject({
      runnerId: newcomer,
      responsiblePitcherId,
    })
    expect(result.state.away.battingOrder['4']).toBe(newcomer)
    expect(result.state.away.fielding['4']).toBeNull()
  })

  it('同時守備位置交換は全変更を元位置に照合し、不足は警告だけにする', () => {
    const source = state()
    const first = source.home.fielding['3']!
    const second = source.home.fielding['4']!
    const switched = applySubstitution(
      source,
      {
        kind: 'defense',
        side: 'home',
        changes: [
          { position: '3', outgoingId: first, incomingId: second },
          { position: '4', outgoingId: second, incomingId: first },
        ],
      },
      [first, second],
    )
    expect(switched.ok).toBe(true)
    if (!switched.ok) return
    expect(switched.state.home.fielding['3']).toBe(second)
    expect(switched.state.home.fielding['4']).toBe(first)
    expect(switched.state.home.battingOrder).toEqual(source.home.battingOrder)
    expect(switched.warnings).toEqual([])
    expect(
      applySubstitution(
        source,
        {
          kind: 'defense',
          side: 'home',
          changes: [{ position: '3', outgoingId: second, incomingId: first }],
        },
        [first],
      ),
    ).toEqual({ ok: false, error: 'current-player-mismatch' })
  })

  it('DH解除の投手打順継承だけを閉じた経路で扱う', () => {
    const source = state(true)
    const dhSlot = source.home.dhSlot!
    const previous = source.home.fielding['1']!
    const result = applySubstitution(
      source,
      {
        kind: 'pitcher',
        side: 'home',
        outgoingId: previous,
        incomingId: newcomer,
        count: { strikes: '0', balls: '0' },
        dh: 'pitcher-takes-dh-slot',
      },
      [newcomer],
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.state.home.dhSlot).toBeNull()
    expect(result.state.home.battingOrder[dhSlot]).toBe(newcomer)
    expect(result.state.exitedPlayerIds).toContain(
      source.home.battingOrder[dhSlot],
    )
    expect(
      applySubstitution(
        state(),
        {
          kind: 'pitcher',
          side: 'home',
          outgoingId: state().home.fielding['1']!,
          incomingId: nextNewcomer,
          count: { strikes: '0', balls: '0' },
          dh: 'pitcher-takes-dh-slot',
        },
        [nextNewcomer],
      ),
    ).toEqual({ ok: false, error: 'unsupported-dh-route' })
  })

  it('無所属候補・別選手・前交代の曖昧責任は拒否する', () => {
    const source = state()
    const pitcher = source.home.fielding['1']!
    const change = {
      kind: 'pitcher' as const,
      side: 'home' as const,
      outgoingId: pitcher,
      incomingId: newcomer,
      count: { strikes: '1' as const, balls: '2' as const },
      dh: 'retain' as const,
    }
    expect(applySubstitution(source, change, [])).toEqual({
      ok: false,
      error: 'unavailable-player',
    })
    expect(
      applySubstitution(source, { ...change, outgoingId: nextNewcomer }, [
        newcomer,
      ]),
    ).toEqual({ ok: false, error: 'current-player-mismatch' })
    const first = applySubstitution(source, change, [newcomer])
    expect(first.ok).toBe(true)
    if (!first.ok) return
    expect(
      applySubstitution(
        first.state,
        { ...change, outgoingId: newcomer, incomingId: nextNewcomer },
        [nextNewcomer],
      ),
    ).toEqual({ ok: false, error: 'ambiguous-responsibility' })
  })
})
