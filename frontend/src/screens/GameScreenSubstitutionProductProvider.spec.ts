import { ApiError } from '../api/client'
import { mount } from '@vue/test-utils'
import GameScreenSubstitutions from './GameScreenSubstitutions.vue'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import type {
  Request,
  Response,
} from '../../../contracts/state-transition/initial_game_roster_v1'
import { validateInitialGameRoster } from '../domain/initialGameRoster'
import { substitutionFromInitialRoster } from '../domain/substitutionKernel'
import {
  prepareSubstitution,
  substitutionContextKey,
  playerRegistration,
  registrationFailure,
  substitutionRequest,
  validateSubstitutionDraft,
  type VerifiedSubstitutionContext,
} from './GameScreenSubstitutionProductProvider'
import type { RawSubstitutionDraft } from './GameScreenSubstitutionTypes'

const originalArtifact = Object.getOwnPropertyDescriptor(
  globalThis,
  'PitchlogDomain',
)
beforeAll(() => {
  const scope = createContext({})
  new Script(
    readFileSync(
      resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
      'utf8',
    ),
  ).runInContext(scope)
  Object.defineProperty(globalThis, 'PitchlogDomain', {
    configurable: true,
    value: Object.getOwnPropertyDescriptor(scope, 'PitchlogDomain')!.value,
  })
})
afterAll(() => {
  if (originalArtifact)
    Object.defineProperty(globalThis, 'PitchlogDomain', originalArtifact)
  else Reflect.deleteProperty(globalThis, 'PitchlogDomain')
})

const cases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/initial_game_roster_cases_v1.json',
    ),
    'utf8',
  ),
).cases as { id: string; request: Request }[]
const original = cases.find((x) => x.id === 'NORMAL-DH-false')!
const result = JSON.parse(
  validateInitialGameRoster(JSON.stringify(original.request)),
) as Response
if (!result.ok) throw new Error('初期配置caseが不成立')
const projection = result.value
const newPlayer = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const game = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const tenant = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const d5 = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const eventId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'

function context(): VerifiedSubstitutionContext {
  return {
    tenantId: tenant,
    gameId: game,
    generation: 'grant-1',
    recoveryGeneration: '1',
    awayLineupId: projection.teams[0].team_id,
    homeLineupId: projection.teams[1].team_id,
    checkpoint: { id: eventId, revision: '1', digest: 'a'.repeat(64) },
    nextD1: 2,
    nextD2: 3,
    currentCount: { strikes: '1', balls: '2' },
    state: substitutionFromInitialRoster(projection, 'away'),
    eligibleBySide: {
      away: [],
      home: [{ id: newPlayer, label: '交代投手' }],
    },
    names: {},
    uniformNumbers: { [newPlayer]: '18' },
  }
}

function draft(c: VerifiedSubstitutionContext): RawSubstitutionDraft {
  const outgoingId = c.state.home.fielding['1']!
  return {
    identity: {
      contextKey: substitutionContextKey(c),
      uiInstanceId: 'screen-1',
      draftId: 1,
      operation: 'pitcher',
      targetId: outgoingId,
    },
    outgoingId,
    incomingMode: 'existing',
    incomingId: newPlayer,
    answers: { side: 'home', strikes: '1', balls: '2', dh: 'retain' },
  }
}

describe('交代画面の真正文脈adapter', () => {
  it('同CPの実候補から画面要求を構成し、交代P2を準備する', () => {
    const c = context(),
      input = draft(c)
    const request = substitutionRequest(c)
    expect(request.contextKey).toBe(input.identity.contextKey)
    expect(
      request.operations.find((x) => x.kind === 'pitcher')?.incoming,
    ).toContainEqual({
      id: newPlayer,
      label: '交代投手',
    })
    expect(validateSubstitutionDraft(c, input).kind).toBe('valid')
    const prepared = prepareSubstitution(c, input, d5, eventId)
    expect(prepared?.event.fields.V7).toMatchObject({
      expectedCheckpoint: c.checkpoint,
      operation: { kind: 'pitcher', side: 'home', incomingId: newPlayer },
      incomingSnapshots: [{ playerId: newPlayer, uniformNumber: '18' }],
    })
    expect(prepared?.prediction.state.home.fielding['1']).toBe(newPlayer)
    expect(c.state.home.fielding['1']).not.toBe(newPlayer)
  })

  it('古いCP、別側候補、現カウント偽装、未知回答を一件ずつ拒否する', () => {
    const c = context(),
      input = draft(c)
    const stale = { ...c, checkpoint: { ...c.checkpoint, revision: '2' } }
    expect(prepareSubstitution(stale, input, d5, eventId)).toBeNull()
    const wrongSide = { ...input, answers: { ...input.answers, side: 'away' } }
    expect(prepareSubstitution(c, wrongSide, d5, eventId)).toBeNull()
    const wrongCount = { ...input, answers: { ...input.answers, balls: '3' } }
    expect(prepareSubstitution(c, wrongCount, d5, eventId)).toBeNull()
    const unknown = { ...input, answers: { ...input.answers, unknown: null } }
    expect(prepareSubstitution(c, unknown, d5, eventId)).toBeNull()
    const unregistered = { ...c, eligibleBySide: { away: [], home: [] } }
    expect(prepareSubstitution(unregistered, input, d5, eventId)).toBeNull()
  })
})

it('無走者で代走対象がなくても実画面の投手交代は選べる', () => {
  const c = context()
  expect(c.state.runners).toEqual([])
  const request = substitutionRequest(c)
  const wrapper = mount(GameScreenSubstitutions, {
    props: {
      request,
      activeContextKey: request.contextKey,
      lockState: { contextKey: request.contextKey, state: 'open' },
    },
  })
  const types = wrapper
    .get('[data-testid="substitution-kind"]')
    .findAll('option')
    .map((option) => (option.element as HTMLOptionElement).value)
  expect(types).toContain('pitcher')
  expect(types).not.toContain('pinch-runner')
  expect(
    wrapper.find('[data-testid="substitution-unavailable"]').exists(),
  ).toBe(false)
  wrapper.unmount()
})

it('その場登録の回答を正式な選手作成入力へ写し、不正は閉じる', () => {
  const team = '11111111-1111-4111-8111-111111111111'
  expect(
    playerRegistration(
      {
        side: 'away',
        answers: {
          name: ' 新しい選手 ',
          throws: 'left',
          bats: 'both',
          uniformNumber: ' 18 ',
        },
      },
      team,
    ),
  ).toEqual({
    team_record_id: team,
    name: '新しい選手',
    throws: 'left',
    bats: 'both',
    uniform_number: '18',
    roster_status_key: 'active',
  })
  expect(
    playerRegistration(
      { side: 'away', answers: { name: '', throws: 'left', bats: 'both' } },
      team,
    ),
  ).toBeNull()
  expect(
    playerRegistration(
      { side: 'away', answers: { name: 'X', throws: 'switch', bats: 'both' } },
      team,
    ),
  ).toBeNull()
  expect(
    playerRegistration(
      { side: 'away', answers: { name: 'X', throws: 'right', bats: 'up' } },
      team,
    ),
  ).toBeNull()
})

it('登録失敗を入力拒否と結果不明へ分ける', () => {
  const rejected = registrationFailure(new ApiError(422, 'invalid', [], undefined, undefined))
  expect(rejected.reload).toBe(false)
  expect(rejected.message).toContain('入力内容')
  const unknown = registrationFailure(new Error('network'))
  expect(unknown.reload).toBe(true)
  expect(unknown.message).toContain('登録結果を確認できません')
})
