import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { h, nextTick, reactive, render } from 'vue'
import GameScreen from './GameScreen.vue'
import GameScreenLiveDisplay from './GameScreenLiveDisplay.vue'
import { safeLiveSources } from './GameScreenLiveDisplayShape'
import type {
  BatterDay,
  BatterSeason,
  DisplaySupply,
  GameFlow,
  LiveDisplaySources,
  LiveIdentity,
  PitchTypeShare,
  PitcherDay,
  PitcherSeason,
  PlateAppearanceRow,
  Scoreboard,
} from './GameScreenLiveDisplayTypes'

const identity: LiveIdentity = {
  scopeKey: 'tenant-a/game-1',
  contextKey: 'event-8',
  pitcherId: 'p-1',
  currentBatterId: 'b-1',
  nextBatterId: 'b-2',
  pitcherName: '投手甲',
  currentBatterName: '打者乙',
  nextBatterName: '打者丙',
}
function supplied<T>(value: T, playerId?: string): DisplaySupply<T> {
  return {
    scopeKey: identity.scopeKey,
    contextKey: identity.contextKey,
    playerId,
    status: 'ready',
    value,
  }
}
const dayPitcher: PitcherDay = {
  pitchCount: '81',
  inningsPitched: '6 1/3',
  fastestSpeed: '149',
  averageSpeed: '139',
  hitsAllowed: '4',
  strikeouts: '7',
  walks: '2',
  runsAllowed: '1',
}
const seasonPitcher: PitcherSeason = {
  periodLabel: '2026年度通算',
  vsLeftAverage: '.202',
  vsRightAverage: '.255',
  inningsPitched: '58 2/3',
  whip: '1.03',
  fip: '2.97',
}
const dayBatter: BatterDay = {
  plateAppearances: '4',
  atBats: '3',
  hits: '2',
  rbi: '1',
  walks: '1',
  hitByPitch: '0',
  strikeouts: '1',
  sacrificeBunts: '0',
  sacrificeFlies: '0',
}
const seasonBatter: BatterSeason = {
  periodLabel: '2026年度通算',
  vsLeftAverage: '.300',
  vsRightAverage: '.271',
  homeRuns: '8',
}
const score: Scoreboard = {
  teams: [
    { name: '先攻', total: '3', h: '7', e: '0', k: '5', b: '4' },
    { name: '後攻', total: '0', h: '2', e: '1', k: '7', b: '2' },
  ],
  innings: [
    {
      key: '1',
      label: '一回',
      cells: [
        { kind: 'text', text: '3' },
        { kind: 'text', text: '0' },
      ],
    },
    ...Array.from({ length: 5 }, (_, index) => ({
      key: String(index + 2),
      label: `${index + 2}回`,
      cells: [
        { kind: 'text' as const, text: '0' },
        { kind: 'text' as const, text: '0' },
      ] as const,
    })),
    {
      key: '7',
      label: '七回',
      cells: [{ kind: 'text', text: '0' }, { kind: 'blank' }],
    },
  ],
}
function candidateScore(
  teams: Scoreboard['teams'],
  innings: Scoreboard['innings'],
): Scoreboard {
  return { teams, innings }
}
const row = {
  key: 'pa-1',
  number: '4',
  inning: '7回表',
  resultName: '左前安打',
  atBat: '算入',
  hitType: '単打',
  rbi: '1',
  onBaseType: '安打',
}
function sources(): LiveDisplaySources {
  return {
    scoreboard: supplied(score),
    pitcherDay: supplied(dayPitcher, 'p-1'),
    pitcherSeason: {
      ...supplied(seasonPitcher, 'p-1'),
      fetchedAt: '12:34',
      offline: false,
    },
    currentBatterDay: supplied(dayBatter, 'b-1'),
    currentBatterSeason: {
      ...supplied(seasonBatter, 'b-1'),
      fetchedAt: '12:35',
      offline: false,
    },
    currentBatterHistory: supplied([row], 'b-1'),
    nextBatterDay: supplied({ ...dayBatter, hits: '0' }, 'b-2'),
    nextBatterSeason: {
      ...supplied(
        { ...seasonBatter, periodLabel: '2025年度通算', homeRuns: '2' },
        'b-2',
      ),
      fetchedAt: '12:36',
      offline: false,
    },
    nextBatterHistory: supplied(
      [{ ...row, key: 'pa-2', resultName: '四球' }],
      'b-2',
    ),
    pitchTypes: supplied(
      [{ key: 'fast', name: '直球', share: '60%', count: '48' }],
      'p-1',
    ),
    flow: supplied({
      inning: '7回表',
      battingOrder: '4番',
      endState: 'detected',
      promptRequired: true,
      undoAllowed: true,
      substitutionAllowed: false,
    }),
    viewerAppliedAt: supplied('12:37'),
    inputOffline: supplied(false),
  }
}
function at(wrapper: ReturnType<typeof mount>, id: string) {
  return wrapper.get(`[data-testid="${id}"]`).text()
}

afterEach(() => vi.restoreAllMocks())

describe('GameScreen の記録中表示契約', () => {
  it('FR020: 提供順の開始済み回と両チーム合計/H/E/K/Bを描画する', () => {
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: sources() },
    })
    expect(wrapper.findAll('[data-testid="inning-card"]')).toHaveLength(7)
    expect(['inning-1-0', 'inning-1-1'].map((id) => at(wrapper, id))).toEqual([
      '3',
      '0',
    ])
    expect(at(wrapper, 'inning-7-0')).toBe('0')
    const blank = wrapper.get('[data-testid="inning-7-1"]')
    expect(blank.element.textContent).toBe('')
    expect(blank.attributes('aria-label')).toBe('空欄')
    for (const id of ['inning-1-0', 'inning-1-1']) {
      expect(
        wrapper.get(`[data-testid="${id}"]`).attributes('aria-label'),
      ).toBeUndefined()
    }
    expect(at(wrapper, 'team-0')).toContain('合計3H7E0K5B4')
    expect(at(wrapper, 'team-1')).toContain('合計0H2E1K7B2')
    expect(wrapper.get('[data-testid="inning-list"]').classes()).toContain(
      'flex-wrap',
    )
    expect(wrapper.get('[data-testid="inning-card"]').classes()).toContain(
      'w-full',
    )
  })

  it('#153候補のX/空欄/3/空欄/0を成立場面ごとの別scope・文脈・セルで表示する', () => {
    const candidates: readonly {
      scopeKey: string
      contextKey: string
      scene: string
      scoreboard: Scoreboard
      cellId: string
      text: string
      blank: boolean
      inningCount: number
      teamTexts: readonly [string, string]
    }[] = [
      {
        scopeKey: 'candidate-x',
        contextKey: 'top-completed-home-ahead',
        scene: '9回表完了、後攻が1回の本塁打1安打でリード、9回裏は未開始',
        scoreboard: candidateScore(
          [
            { name: '先攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
            { name: '後攻', total: '1', h: '1', e: '0', k: '0', b: '0' },
          ],
          [
            {
              key: '1',
              label: '一回',
              cells: [
                { kind: 'text', text: '0' },
                { kind: 'text', text: '1' },
              ],
            },
            ...Array.from({ length: 7 }, (_, index) => ({
              key: String(index + 2),
              label: `${index + 2}回`,
              cells: [
                { kind: 'text' as const, text: '0' },
                { kind: 'text' as const, text: '0' },
              ] as const,
            })),
            {
              key: '9',
              label: '九回',
              cells: [
                { kind: 'text', text: '0' },
                { kind: 'text', text: 'X' },
              ],
            },
          ],
        ),
        cellId: 'inning-9-1',
        text: 'X',
        blank: false,
        inningCount: 9,
        teamTexts: ['合計0H0E0K0B0', '合計1H1E0K0B0'],
      },
      {
        scopeKey: 'candidate-waiting-blank',
        contextKey: 'first-top-in-progress-home-waiting',
        scene: '1回表進行中、1回裏は通常の未開始待ち',
        scoreboard: candidateScore(
          [
            { name: '先攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
            { name: '後攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
          ],
          [
            {
              key: '1',
              label: '一回',
              cells: [{ kind: 'text', text: '0' }, { kind: 'blank' }],
            },
          ],
        ),
        cellId: 'inning-1-1',
        text: '',
        blank: true,
        inningCount: 1,
        teamTexts: ['合計0H0E0K0B0', '合計0H0E0K0B0'],
      },
      {
        scopeKey: 'candidate-three',
        contextKey: 'top-started',
        scene: '1回表進行中に先攻が3安打で3点、1回裏は未開始',
        scoreboard: candidateScore(
          [
            { name: '先攻', total: '3', h: '3', e: '0', k: '0', b: '0' },
            { name: '後攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
          ],
          [
            {
              key: '1',
              label: '一回',
              cells: [{ kind: 'text', text: '3' }, { kind: 'blank' }],
            },
          ],
        ),
        cellId: 'inning-1-0',
        text: '3',
        blank: false,
        inningCount: 1,
        teamTexts: ['合計3H3E0K0B0', '合計0H0E0K0B0'],
      },
      {
        scopeKey: 'candidate-home-blank',
        contextKey: 'second-top-stopped-before-home',
        scene: '1回は完了、2回表の途中打切りで2回裏は未開始',
        scoreboard: candidateScore(
          [
            { name: '先攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
            { name: '後攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
          ],
          [
            {
              key: '1',
              label: '一回',
              cells: [
                { kind: 'text', text: '0' },
                { kind: 'text', text: '0' },
              ],
            },
            {
              key: '2',
              label: '二回',
              cells: [{ kind: 'text', text: '0' }, { kind: 'blank' }],
            },
          ],
        ),
        cellId: 'inning-2-1',
        text: '',
        blank: true,
        inningCount: 2,
        teamTexts: ['合計0H0E0K0B0', '合計0H0E0K0B0'],
      },
      {
        scopeKey: 'candidate-zero',
        contextKey: 'third-bottom-started',
        scene: '1回表3安打3点、3回裏は開始済みで0点',
        scoreboard: candidateScore(
          [
            { name: '先攻', total: '3', h: '3', e: '0', k: '0', b: '0' },
            { name: '後攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
          ],
          [
            ...Array.from({ length: 2 }, (_, index) => ({
              key: String(index + 1),
              label: `${index + 1}回`,
              cells: [
                { kind: 'text' as const, text: index === 0 ? '3' : '0' },
                { kind: 'text' as const, text: '0' },
              ] as const,
            })),
            {
              key: '3',
              label: '三回',
              cells: [
                { kind: 'text', text: '0' },
                { kind: 'text', text: '0' },
              ],
            },
          ],
        ),
        cellId: 'inning-3-1',
        text: '0',
        blank: false,
        inningCount: 3,
        teamTexts: ['合計3H3E0K0B0', '合計0H0E0K0B0'],
      },
    ]
    const shownCells = candidates.map((candidate) => {
      const wrapper = mount(GameScreenLiveDisplay, {
        props: {
          identity: {
            ...identity,
            scopeKey: candidate.scopeKey,
            contextKey: candidate.contextKey,
          },
          sources: {
            scoreboard: {
              ...supplied(candidate.scoreboard),
              scopeKey: candidate.scopeKey,
              contextKey: candidate.contextKey,
            },
          },
        },
      })
      expect(
        wrapper.find('[data-testid="score-status"]').exists(),
        candidate.scene,
      ).toBe(false)
      expect(
        wrapper.findAll('[data-testid="inning-card"]'),
        candidate.scene,
      ).toHaveLength(candidate.inningCount)
      if (candidate.scopeKey === 'candidate-x')
        expect(
          wrapper
            .findAll('[data-testid="inning-card"] h3')
            .map((heading) => heading.text()),
          candidate.scene,
        ).toEqual([
          '一回',
          '2回',
          '3回',
          '4回',
          '5回',
          '6回',
          '7回',
          '8回',
          '九回',
        ])
      for (const [index, expected] of candidate.teamTexts.entries())
        expect(at(wrapper, `team-${index}`), candidate.scene).toContain(
          expected,
        )
      const cell = wrapper.get(`[data-testid="${candidate.cellId}"]`)
      expect(cell.element.textContent, candidate.scene).toBe(candidate.text)
      expect(cell.attributes('aria-label'), candidate.scene).toBe(
        candidate.blank ? '空欄' : undefined,
      )
      return cell.element.textContent
    })
    expect(shownCells).toEqual(['X', '', '3', '', '0'])
  })

  it('FR021/022/023: 現投手と現在・次打者の全欄、7列、球種割合と球数を提供値で表示する', () => {
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: sources() },
    })
    const text = wrapper.text()
    for (const [label, value] of [
      ['当日投球数', '81'],
      ['投球回', '6 1/3'],
      ['最速球速', '149'],
      ['平均球速', '139'],
      ['被安打', '4'],
      ['奪三振', '7'],
      ['与四球', '2'],
      ['失点', '1'],
      ['対左被打率', '.202'],
      ['対右被打率', '.255'],
      ['WHIP', '1.03'],
      ['FIP', '2.97'],
    ])
      expect(text).toContain(`${label}${value}`)
    for (const label of [
      '当日投球数',
      '投球回',
      '最速球速',
      '平均球速',
      '被安打',
      '奪三振',
      '与四球',
      '失点',
      '対左被打率',
      '対右被打率',
      'WHIP',
      'FIP',
    ])
      expect(text).toContain(label)
    for (const label of [
      '打席数',
      '打数',
      '安打',
      '打点',
      '四球',
      '死球',
      '三振',
      '犠打',
      '犠飛',
      '対左打率',
      '対右打率',
      '本塁打',
    ])
      expect(at(wrapper, 'current-batter')).toContain(label)
    for (const [label, value] of [
      ['打席数', '4'],
      ['打数', '3'],
      ['安打', '2'],
      ['打点', '1'],
      ['四球', '1'],
      ['死球', '0'],
      ['三振', '1'],
      ['犠打', '0'],
      ['犠飛', '0'],
      ['対左打率', '.300'],
      ['対右打率', '.271'],
      ['本塁打', '8'],
    ])
      expect(at(wrapper, 'current-batter')).toContain(`${label}${value}`)
    for (const [label, value] of [
      ['番号', '4'],
      ['イニング', '7回表'],
      ['結果表示名', '左前安打'],
      ['打数算入', '算入'],
      ['安打種別', '単打'],
      ['打点', '1'],
      ['出塁別', '安打'],
    ])
      expect(
        wrapper
          .get('[data-testid="current-history"] [data-testid="plate-row"]')
          .text(),
      ).toContain(`${label}${value}`)
    for (const label of [
      '番号',
      'イニング',
      '結果表示名',
      '打数算入',
      '安打種別',
      '打点',
      '出塁別',
    ])
      expect(
        wrapper
          .get('[data-testid="current-history"] [data-testid="plate-row"]')
          .text(),
      ).toContain(label)
    expect(at(wrapper, 'current-batter')).toContain('左前安打')
    expect(at(wrapper, 'next-batter')).toContain('四球')
    expect(at(wrapper, 'pitch-types-status')).toBe('')
    expect(wrapper.get('[data-testid="pitch-type-share"]').text()).toContain(
      '割合 60% / 球数 48',
    )
    expect(at(wrapper, 'pitcher-season-note')).toBe(
      '最終取得: 12:34 / オンライン',
    )
    expect(at(wrapper, 'pitcher-season-period')).toBe('2026年度通算')
    expect(at(wrapper, 'current-season-period')).toBe('2026年度通算')
    expect(at(wrapper, 'next-season-period')).toBe('2025年度通算')
    expect(at(wrapper, 'viewer-applied-at')).toBe('12:37')
    expect(at(wrapper, 'input-offline')).toBe('オンライン')
  })

  it('提供された開始済み12回を最後まで省略せず描画する', () => {
    const innings = Array.from({ length: 12 }, (_, index) => ({
      key: String(index + 1),
      label: `${index + 1}回`,
      cells:
        index === 11
          ? ([{ kind: 'text', text: '11' }, { kind: 'blank' }] as const)
          : ([
              { kind: 'text', text: '0' },
              { kind: 'text', text: '0' },
            ] as const),
    }))
    const wrapper = mount(GameScreenLiveDisplay, {
      props: {
        identity,
        sources: {
          scoreboard: supplied(
            candidateScore(
              [
                { name: '先攻', total: '11', h: '11', e: '0', k: '0', b: '0' },
                { name: '後攻', total: '0', h: '0', e: '0', k: '0', b: '0' },
              ],
              innings,
            ),
          ),
        },
      },
    })
    expect(wrapper.findAll('[data-testid="inning-card"]')).toHaveLength(12)
    expect(at(wrapper, 'inning-12-0')).toBe('11')
    expect(at(wrapper, 'inning-12-1')).toBe('')
    expect(
      wrapper.get('[data-testid="inning-12-1"]').attributes('aria-label'),
    ).toBe('空欄')
  })

  it('合計の空文字は未取得へ倒し、0の正常供給は保持する', async () => {
    const wrapper = mount(GameScreenLiveDisplay, {
      props: {
        identity,
        sources: {
          scoreboard: supplied({
            ...score,
            teams: [
              { ...score.teams[0], total: '', h: '0' },
              score.teams[1],
            ] as Scoreboard['teams'],
          }),
        },
      },
    })
    expect(at(wrapper, 'score-status')).toBe('未取得')
    await wrapper.setProps({ sources: { scoreboard: supplied(score) } })
    const totals = wrapper
      .get('[data-testid="team-1"]')
      .findAll('dl > div > dd')
    expect(totals[0].element.textContent).toBe('0')
  })

  it('未取得・読取失敗・0件を区別し、0や空欄を補完しない', async () => {
    const wrapper = mount(GameScreenLiveDisplay, { props: { identity } })
    expect(at(wrapper, 'score-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-day-status')).toBe('未取得')
    expect(at(wrapper, 'pitch-types-status')).toBe('未取得')
    await wrapper.setProps({
      sources: {
        scoreboard: { ...supplied(score), status: 'read-failed' },
        pitcherDay: { ...supplied(dayPitcher, 'p-1'), status: 'empty' },
        pitchTypes: { ...supplied([], 'p-1'), status: 'empty' },
      },
    })
    expect(at(wrapper, 'score-status')).toBe('読取失敗')
    expect(at(wrapper, 'pitcher-day-status')).toBe('データなし')
    expect(at(wrapper, 'pitch-types-status')).toBe('データなし')
    expect(wrapper.findAll('[data-testid="pitch-type-share"]')).toHaveLength(0)
  })

  it('閲覧端末の正式鮮度3状態と断中未prefetchを提供状態だけで表示する', async () => {
    const data = sources()
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: data },
    })
    for (const [status, expected] of [
      ['read-failed', '読取失敗'],
      ['empty', 'データなし'],
      ['unavailable', '未取得'],
    ] as const) {
      await wrapper.setProps({
        sources: { ...data, viewerAppliedAt: { ...supplied('12:37'), status } },
      })
      expect(at(wrapper, 'viewer-applied-at')).toBe(expected)
    }
    await wrapper.setProps({
      sources: {
        ...data,
        pitcherSeason: {
          ...supplied(seasonPitcher, 'p-1'),
          status: 'unavailable',
          offline: true,
        },
        currentBatterSeason: {
          ...supplied(seasonBatter, 'b-1'),
          status: 'unavailable',
          offline: true,
        },
        nextBatterSeason: {
          ...supplied(seasonBatter, 'b-2'),
          status: 'unavailable',
          offline: true,
        },
      },
    })
    for (const slot of ['pitcher', 'current', 'next']) {
      expect(at(wrapper, `${slot}-season-status`)).toBe('未取得')
      expect(at(wrapper, `${slot}-season-note`)).toBe('オフラインのため未取得')
      expect(at(wrapper, `${slot}-season-period`)).toBe('未取得')
    }
  })

  it('投手・現在打者・次打者の断中シーズンreadyで取得時刻が欠けると値を隠す', async () => {
    for (const [slot, sourceKey, period, rate] of [
      ['pitcher', 'pitcherSeason', '2026年度通算', '.202'],
      ['current', 'currentBatterSeason', '2026年度通算', '.300'],
      ['next', 'nextBatterSeason', '2025年度通算', '.300'],
    ] as const) {
      const data = sources()
      const suppliedSeason = data[sourceKey]!
      const wrapper = mount(GameScreenLiveDisplay, {
        props: { identity, sources: data },
      })
      const seasonValues = () => {
        const section =
          slot === 'pitcher'
            ? wrapper.get('[aria-label="現投手の成績"]')
            : wrapper.get(`[data-testid="${slot}-batter"]`)
        return section
          .findAll('dl')[1]
          .findAll('dd')
          .map((field) => field.text())
      }
      for (const boundary of [
        { name: '欠落' },
        { name: 'null', fetchedAt: null },
        { name: '空文字', fetchedAt: '' },
        { name: '空白', fetchedAt: '   ' },
      ] as const) {
        const offlineSeason = { ...suppliedSeason, offline: true }
        delete offlineSeason.fetchedAt
        if (Object.hasOwn(boundary, 'fetchedAt'))
          offlineSeason.fetchedAt = boundary.fetchedAt
        await wrapper.setProps({
          sources: { ...data, [sourceKey]: offlineSeason },
        })
        expect(at(wrapper, `${slot}-season-status`), boundary.name).toBe(
          '未取得',
        )
        expect(at(wrapper, `${slot}-season-note`), boundary.name).toBe(
          'オフラインのため未取得',
        )
        expect(at(wrapper, `${slot}-season-period`), boundary.name).toBe(
          '未取得',
        )
        expect(seasonValues(), boundary.name).toEqual(
          Array(slot === 'pitcher' ? 5 : 3).fill('未取得'),
        )
      }
      await wrapper.setProps({
        sources: {
          ...data,
          [sourceKey]: {
            ...suppliedSeason,
            offline: true,
            fetchedAt: '12:34',
          },
        },
      })
      expect(at(wrapper, `${slot}-season-status`)).toBe('')
      expect(at(wrapper, `${slot}-season-note`)).toBe(
        '最終取得: 12:34 / オフライン',
      )
      expect(at(wrapper, `${slot}-season-period`)).toBe(period)
      expect(seasonValues()).toContain(rate)
    }
  })

  it('壊れた得点表の行・セル・疎配列は未取得へ倒し、停止表示と他の提供値を保つ', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue({ ok: true } as Response)
    const sparseTeams: unknown[] = [score.teams[0]]
    sparseTeams.length = 2
    Object.assign(sparseTeams, { extra: score.teams[1] })
    const sparseInnings: unknown[] = [score.innings[0]]
    sparseInnings.length = 2
    Object.assign(sparseInnings, { extra: score.innings[0] })
    const sparseCells: unknown[] = [score.innings[0].cells[0]]
    sparseCells.length = 2
    Object.assign(sparseCells, { extra: score.innings[0].cells[1] })
    const invalid: readonly unknown[] = [
      null,
      { ...score, teams: null },
      { ...score, teams: sparseTeams },
      { ...score, teams: [score.teams[0], null] },
      { ...score, teams: [{ ...score.teams[0], total: 3 }, score.teams[1]] },
      { ...score, innings: null },
      { ...score, innings: sparseInnings },
      { ...score, innings: [null] },
      { ...score, innings: [{ ...score.innings[0], cells: sparseCells }] },
      {
        ...score,
        innings: [
          { ...score.innings[0], cells: [null, score.innings[0].cells[1]] },
        ],
      },
      {
        ...score,
        innings: [
          {
            ...score.innings[0],
            cells: [{ kind: 'text', text: 0 }, score.innings[0].cells[1]],
          },
        ],
      },
      {
        ...score,
        innings: [
          {
            ...score.innings[0],
            cells: [{ kind: 'text', text: '' }, score.innings[0].cells[1]],
          },
        ],
      },
    ]
    const data = sources()
    const wrapper = mount(GameScreen, {
      props: {
        liveIdentity: identity,
        liveSources: data,
        stopDisplay: {
          phase: 'sending-stopped',
          deviceUnconfirmed: { kind: 'count', value: 2 },
        },
      },
    })
    for (const value of invalid) {
      await wrapper.setProps({
        liveSources: { ...data, scoreboard: supplied(value as Scoreboard) },
      })
      expect(at(wrapper, 'score-status')).toBe('未取得')
      expect(wrapper.find('[data-testid="inning-card"]').exists()).toBe(false)
      expect(at(wrapper, 'pitcher-day-status')).toBe('')
      expect(at(wrapper, 'stop-status')).toBe('送信停止')
      expect(at(wrapper, 'device-unconfirmed-count')).toBe('2')
      expect(
        wrapper
          .get('[data-testid="resume-same-content"]')
          .attributes('disabled'),
      ).toBeDefined()
    }
    for (const id of ['resume-same-content', 'commit-pitch', 'declare-end']) {
      wrapper
        .get(`[data-testid="${id}"]`)
        .element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('壊れた成績・履歴・球種・終了・鮮度のreadyは成功扱いせず未取得へ倒す', async () => {
    const data = sources()
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: data },
    })
    const sparseHistory: unknown[] = [row]
    sparseHistory.length = 2
    Object.assign(sparseHistory, { extra: row })
    const sparsePitchTypes: unknown[] = []
    sparsePitchTypes.length = 1
    Object.assign(sparsePitchTypes, {
      extra: { key: 'x', name: '球種', share: '1%', count: '1' },
    })
    for (const value of [null, [null], sparseHistory, [{ ...row, rbi: 1 }]]) {
      await wrapper.setProps({
        sources: {
          ...data,
          currentBatterHistory: supplied(
            value as readonly PlateAppearanceRow[],
            'b-1',
          ),
        },
      })
      expect(at(wrapper, 'current-history-status')).toBe('未取得')
      expect(
        wrapper
          .find('[data-testid="current-history"] [data-testid="plate-row"]')
          .exists(),
      ).toBe(false)
    }
    for (const value of [
      null,
      [null],
      sparsePitchTypes,
      [{ key: 'x', name: '球種', share: 1, count: '1' }],
    ]) {
      await wrapper.setProps({
        sources: {
          ...data,
          pitchTypes: supplied(value as readonly PitchTypeShare[], 'p-1'),
        },
      })
      expect(at(wrapper, 'pitch-types-status')).toBe('未取得')
      expect(wrapper.find('[data-testid="pitch-type-share"]').exists()).toBe(
        false,
      )
    }
    await wrapper.setProps({
      sources: {
        ...data,
        pitcherDay: supplied(
          { ...dayPitcher, pitchCount: 81 } as unknown as PitcherDay,
          'p-1',
        ),
        pitcherSeason: supplied(null as unknown as PitcherSeason, 'p-1'),
        currentBatterDay: supplied(
          { ...dayBatter, atBats: undefined } as unknown as BatterDay,
          'b-1',
        ),
        currentBatterSeason: supplied(
          { ...seasonBatter, homeRuns: 8 } as unknown as BatterSeason,
          'b-1',
        ),
        flow: supplied({
          ...data.flow!.value!,
          endState: 'constructor',
        } as unknown as GameFlow),
        viewerAppliedAt: supplied(123 as unknown as string),
        inputOffline: supplied('offline' as unknown as boolean),
      },
    })
    for (const id of [
      'pitcher-day-status',
      'pitcher-season-status',
      'current-day-status',
      'current-season-status',
      'flow-status',
    ])
      expect(at(wrapper, id)).toBe('未取得')
    expect(at(wrapper, 'end-state')).toBe('未取得')
    expect(at(wrapper, 'viewer-applied-at')).toBe('未取得')
    expect(at(wrapper, 'input-offline')).toBe('未取得')
    await wrapper.setProps({
      sources: {
        ...data,
        pitcherSeason: supplied(
          {
            ...seasonPitcher,
            periodLabel: undefined,
          } as unknown as PitcherSeason,
          'p-1',
        ),
      },
    })
    expect(at(wrapper, 'pitcher-season-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-season-period')).toBe('未取得')
    await wrapper.setProps({
      sources: {
        ...data,
        flow: supplied({
          ...data.flow!.value!,
          promptRequired: 'false',
        } as unknown as GameFlow),
      },
    })
    expect(at(wrapper, 'flow-status')).toBe('未取得')
    expect(at(wrapper, 'end-state')).toBe('未取得')
  })

  it('選手供給のplayerId欠落とidentity対象ID未取得はその人物だけ未取得へ倒す', async () => {
    const data = sources()
    const wrapper = mount(GameScreenLiveDisplay, {
      props: {
        identity,
        sources: {
          ...data,
          pitcherDay: supplied(dayPitcher),
          currentBatterDay: supplied(dayBatter),
        },
      },
    })
    expect(at(wrapper, 'pitcher-day-status')).toBe('未取得')
    expect(at(wrapper, 'current-day-status')).toBe('未取得')
    expect(at(wrapper, 'next-day-status')).toBe('')
    expect(at(wrapper, 'team-0')).toContain('合計3')
    await wrapper.setProps({
      identity: {
        ...identity,
        pitcherId: undefined,
        currentBatterId: undefined,
      } as unknown as LiveIdentity,
      sources: data,
    })
    expect(at(wrapper, 'pitcher-day-status')).toBe('未取得')
    expect(at(wrapper, 'current-day-status')).toBe('未取得')
    expect(at(wrapper, 'next-day-status')).toBe('')
    expect(at(wrapper, 'team-0')).toContain('合計3')
  })

  it('代打・投手交代時点で選手を切り替え、遅延した旧選手・旧scopeの応答を混ぜない', async () => {
    const data = sources()
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: data },
    })
    await wrapper.setProps({
      identity: {
        ...identity,
        contextKey: 'event-9',
        pitcherId: 'p-3',
        pitcherName: '新投手',
        currentBatterId: 'b-3',
        currentBatterName: '代打丁',
        nextBatterId: 'b-4',
        nextBatterName: '次打者戊',
      },
    })
    expect(at(wrapper, 'current-batter')).toContain('代打丁')
    expect(at(wrapper, 'next-batter')).toContain('次打者戊')
    expect(wrapper.text()).toContain('新投手')
    expect(at(wrapper, 'current-day-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-day-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-season-status')).toBe('未取得')
    expect(at(wrapper, 'pitch-types-status')).toBe('未取得')
    expect(wrapper.find('[data-testid="plate-row"]').exists()).toBe(false)
    await wrapper.setProps({
      sources: {
        ...data,
        currentBatterDay: {
          ...supplied(dayBatter, 'b-1'),
          contextKey: 'event-9',
        },
        pitcherDay: { ...supplied(dayPitcher, 'p-1'), contextKey: 'event-9' },
        pitcherSeason: {
          ...supplied(seasonPitcher, 'p-1'),
          contextKey: 'event-9',
        },
        pitchTypes: { ...data.pitchTypes!, contextKey: 'event-9' },
      },
    })
    expect(at(wrapper, 'current-day-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-day-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-season-status')).toBe('未取得')
    expect(at(wrapper, 'pitch-types-status')).toBe('未取得')
    expect(wrapper.find('[data-testid="pitch-type-share"]').exists()).toBe(
      false,
    )
    await wrapper.setProps({
      sources: {
        ...data,
        currentBatterDay: {
          ...supplied({ ...dayBatter, hits: '1' }, 'b-3'),
          contextKey: 'event-9',
        },
        pitcherDay: {
          ...supplied({ ...dayPitcher, pitchCount: '0' }, 'p-3'),
          contextKey: 'event-9',
        },
        pitcherSeason: {
          ...supplied(
            { ...seasonPitcher, periodLabel: '2024年度通算', whip: '1.11' },
            'p-3',
          ),
          contextKey: 'event-9',
        },
        pitchTypes: {
          ...supplied(
            [{ key: 'curve', name: 'カーブ', share: '0%', count: '0' }],
            'p-3',
          ),
          contextKey: 'event-9',
        },
        nextBatterDay: {
          ...supplied({ ...dayBatter, hits: '0' }, 'b-4'),
          contextKey: 'event-9',
        },
      },
    })
    expect(at(wrapper, 'current-batter')).toContain('安打1')
    expect(at(wrapper, 'next-batter')).toContain('安打0')
    expect(wrapper.text()).toContain('当日投球数0')
    expect(at(wrapper, 'pitcher-season-period')).toBe('2024年度通算')
    expect(wrapper.get('[aria-label="現投手の成績"]').text()).toContain(
      'WHIP1.11',
    )
    expect(wrapper.get('[aria-label="当日の球種"]').text()).toContain('新投手')
    expect(wrapper.get('[data-testid="pitch-type-share"]').text()).toContain(
      'カーブ割合 0% / 球数 0',
    )
    expect(at(wrapper, 'current-season-status')).toBe('未取得')
    await wrapper.setProps({
      identity: { ...identity, scopeKey: 'tenant-b/game-1' },
    })
    expect(at(wrapper, 'score-status')).toBe('未取得')
  })

  it('断中の提供最新当日投影更新を表示し、古い値への暫定ラベルだけでは合格にしない', async () => {
    const data = sources()
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: data },
    })
    await wrapper.setProps({
      sources: {
        ...data,
        scoreboard: {
          ...supplied({
            ...score,
            teams: [
              { ...score.teams[0], total: '4' },
              score.teams[1],
            ] as Scoreboard['teams'],
            innings: [
              {
                ...score.innings[0],
                cells: [{ kind: 'text', text: '4' }, score.innings[0].cells[1]],
              },
            ],
          }),
          provisional: true,
        },
        pitcherDay: {
          ...supplied({ ...dayPitcher, pitchCount: '82' }, 'p-1'),
          provisional: true,
        },
        currentBatterDay: {
          ...supplied({ ...dayBatter, hits: '3' }, 'b-1'),
          provisional: true,
        },
        nextBatterDay: {
          ...supplied({ ...dayBatter, hits: '0' }, 'b-2'),
          provisional: true,
        },
        pitchTypes: {
          ...supplied(
            [{ key: 'fast', name: '直球', share: '61%', count: '49' }],
            'p-1',
          ),
          provisional: true,
        },
        pitcherSeason: { ...data.pitcherSeason!, offline: true },
      },
    })
    expect(at(wrapper, 'team-0')).toContain('合計4')
    expect(wrapper.text()).toContain('当日投球数82')
    expect(at(wrapper, 'current-batter')).toContain('安打3')
    expect(wrapper.get('[data-testid="pitch-type-share"]').text()).toContain(
      '61% / 球数 49',
    )
    expect(at(wrapper, 'pitcher-season-note')).toBe(
      '最終取得: 12:34 / オフライン',
    )
    expect(wrapper.find('[data-testid="score-provisional"]').exists()).toBe(
      true,
    )
    expect(
      wrapper.find('[data-testid="pitcher-day-provisional"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="pitch-types-provisional"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="current-day-provisional"]').exists(),
    ).toBe(true)
    expect(wrapper.find('[data-testid="next-day-provisional"]').exists()).toBe(
      true,
    )
    await wrapper.setProps({
      sources: {
        ...data,
        pitcherSeason: {
          ...supplied(seasonPitcher, 'p-1'),
          status: 'unavailable',
          offline: true,
        },
      },
    })
    expect(at(wrapper, 'pitcher-season-status')).toBe('未取得')
    expect(at(wrapper, 'pitcher-season-note')).toBe('オフラインのため未取得')
  })

  it('終了検知・未同期宣言・追記再開・再終了を別表示し、#153 E02/E09/E10候補を表示する', async () => {
    const data = sources()
    const wrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: data },
    })
    expect(at(wrapper, 'end-state')).toBe('終了候補を検知（未宣言）')
    const flow = data.flow!.value!
    await wrapper.setProps({
      sources: {
        ...data,
        flow: supplied({
          ...flow,
          endState: 'declared-unsynced',
          promptRequired: false,
          undoAllowed: true,
          substitutionAllowed: false,
        }),
      },
    })
    expect(at(wrapper, 'end-state')).toBe('終了宣言済み・未同期')
    expect(wrapper.text()).not.toContain('試合完了')
    expect(at(wrapper, 'end-prompt')).toBe('なし')
    expect(at(wrapper, 'flow-undo')).toBe('あり')
    expect(at(wrapper, 'flow-substitution')).toBe('なし')
    await wrapper.setProps({
      sources: {
        ...data,
        flow: supplied({
          ...flow,
          endState: 'reopened',
          promptRequired: false,
          substitutionAllowed: true,
        }),
      },
    })
    expect(at(wrapper, 'end-state')).toBe('試合追記再開中')
    expect(at(wrapper, 'end-prompt')).toBe('なし')
    expect(at(wrapper, 'flow-substitution')).toBe('あり')
    await wrapper.setProps({
      sources: {
        ...data,
        flow: supplied({
          ...flow,
          endState: 'reclosed-unsynced',
          promptRequired: false,
          substitutionAllowed: false,
        }),
      },
    })
    expect(at(wrapper, 'end-state')).toBe('再終了宣言済み・未同期')
    expect(at(wrapper, 'end-prompt')).toBe('なし')
    expect(at(wrapper, 'flow-substitution')).toBe('なし')
  })

  it('正式鮮度が未提供なら未取得。長文は折返し、直接dispatchしても実操作0', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue({ ok: true } as Response)
    const saveSpy = vi.spyOn(Storage.prototype, 'setItem')
    const data = sources()
    delete data.viewerAppliedAt
    delete data.inputOffline
    data.scoreboard = supplied({
      ...score,
      teams: [
        { ...score.teams[0], name: '<img src=x onerror=alert(1)>'.repeat(8) },
        score.teams[1],
      ],
    })
    const oldWidth = window.innerWidth
    try {
      for (const width of [375, 320]) {
        Object.defineProperty(window, 'innerWidth', {
          configurable: true,
          value: width,
        })
        const wrapper = mount(GameScreen, {
          props: { liveIdentity: identity, liveSources: data },
        })
        expect(at(wrapper, 'viewer-applied-at')).toBe('未取得')
        expect(at(wrapper, 'input-offline')).toBe('未取得')
        expect(wrapper.find('img').exists()).toBe(false)
        expect(wrapper.get('[data-testid="live-display"]').classes()).toContain(
          'wrap-anywhere',
        )
        expect(wrapper.get('[data-testid="inning-list"]').classes()).toContain(
          'flex-wrap',
        )
        expect(wrapper.get('[data-testid="inning-card"]').classes()).toContain(
          'w-full',
        )
        for (const id of [
          'switch-inning',
          'declare-end',
          'reopen-game',
          'resume-same-content',
          'correct-stopped-content',
          'commit-pitch',
        ]) {
          const button = wrapper.get(`[data-testid="${id}"]`)
          expect(button.attributes('disabled')).toBeDefined()
          button.element.dispatchEvent(
            new MouseEvent('click', { bubbles: true }),
          )
        }
        expect(wrapper.emitted('save')).toBeUndefined()
        expect(wrapper.emitted('commit')).toBeUndefined()
        wrapper.unmount()
      }
    } finally {
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        value: oldWidth,
      })
    }
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(saveSpy).not.toHaveBeenCalled()
  })

  it('同内容props再供給で既存投球下書きを消さない', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        liveIdentity: identity,
        liveSources: sources(),
        state: { batter: '旧打者', pitcher: '旧投手' },
        pitchTypes: [{ id: 'fast', displayName: '直球', enabled: true }],
        results: [{ id: 'ball', displayName: 'ボール', enabled: true }],
      },
    })
    await wrapper.get('[data-testid="pitch-type"]').setValue('fast')
    await wrapper.get('[data-testid="pitch-speed"]').setValue('140')
    await wrapper.setProps({
      liveIdentity: { ...identity },
      liveSources: sources(),
    })
    expect(at(wrapper, 'batter')).toBe('旧打者')
    expect(at(wrapper, 'pitcher')).toBe('旧投手')
    await wrapper.setProps({
      liveIdentity: {
        ...identity,
        currentBatterName: '',
        pitcherName: 42,
      } as unknown as LiveIdentity,
    })
    expect(at(wrapper, 'batter')).toBe('旧打者')
    expect(at(wrapper, 'pitcher')).toBe('旧投手')
    expect(
      (wrapper.get('[data-testid="pitch-type"]').element as HTMLSelectElement)
        .value,
    ).toBe('fast')
    expect(
      (wrapper.get('[data-testid="pitch-speed"]').element as HTMLInputElement)
        .value,
    ).toBe('140')
  })

  it('検査時に読んだ値だけを独立snapshotとして描画し、Vue reactiveの更新も受ける', async () => {
    let totalReads = 0
    let nameReads = 0
    const team = { ...score.teams[0] }
    Object.defineProperty(team, 'total', {
      enumerable: true,
      get() {
        totalReads += 1
        return totalReads === 1 ? '3' : '99'
      },
    })
    const suppliedScore: Scoreboard = {
      ...score,
      teams: [team, score.teams[1]],
    }
    const suppliedIdentity = { ...identity }
    Object.defineProperty(suppliedIdentity, 'pitcherName', {
      enumerable: true,
      get() {
        nameReads += 1
        return nameReads === 1 ? '投手甲' : '別投手'
      },
    })
    // Test Utilsのprops深走査を通さず、実際のVue prop経路でgetterを試す。
    const host = document.createElement('div')
    render(
      h(GameScreenLiveDisplay, {
        identity: suppliedIdentity,
        sources: { ...sources(), scoreboard: supplied(suppliedScore) },
      }),
      host,
    )
    expect(host.querySelector('[data-testid="team-0"]')?.textContent).toContain(
      '合計3',
    )
    expect(
      host.querySelector('[aria-label="現投手の成績"]')?.textContent,
    ).toContain('投手甲')
    expect(totalReads).toBe(1)
    expect(nameReads).toBe(1)
    render(null, host)

    const mutableScore: Scoreboard = {
      ...score,
      teams: [{ ...score.teams[0] }, score.teams[1]],
    }
    const snapshot = safeLiveSources({ scoreboard: supplied(mutableScore) })
    ;(mutableScore.teams[0] as { total: string | null }).total = '9'
    expect(snapshot.scoreboard?.value?.teams[0].total).toBe('3')

    const reactiveSources = reactive(sources())
    const reactiveWrapper = mount(GameScreenLiveDisplay, {
      props: { identity, sources: reactiveSources },
    })
    expect(at(reactiveWrapper, 'team-0')).toContain('合計3')
    reactiveSources.scoreboard = supplied({
      ...score,
      teams: [
        { ...score.teams[0], total: '4' },
        score.teams[1],
      ] as Scoreboard['teams'],
      innings: [
        {
          ...score.innings[0],
          cells: [{ kind: 'text', text: '4' }, score.innings[0].cells[1]],
        },
      ],
    })
    await nextTick()
    expect(at(reactiveWrapper, 'team-0')).toContain('合計4')
  })

  it('例外を投げるliveIdentityでも既存停止UIを落とさない', () => {
    const badIdentity = { ...identity }
    Object.defineProperty(badIdentity, 'pitcherName', {
      get() {
        throw new Error('broken display getter')
      },
    })
    const host = document.createElement('div')
    render(
      h(GameScreen, {
        state: { batter: '元の打者', pitcher: '元の投手' },
        liveIdentity: badIdentity,
        liveSources: sources(),
        stopDisplay: { phase: 'sending-stopped' },
      }),
      host,
    )
    expect(host.querySelector('[data-testid="stop-status"]')?.textContent).toBe(
      '送信停止',
    )
    expect(host.querySelector('[data-testid="batter"]')?.textContent).toBe(
      '元の打者',
    )
    expect(host.querySelector('[data-testid="pitcher"]')?.textContent).toBe(
      '元の投手',
    )
    expect(
      host.querySelector('[data-testid="score-status"]')?.textContent,
    ).toBe('未取得')
    expect(
      (
        host.querySelector(
          '[data-testid="resume-same-content"]',
        ) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    render(null, host)
  })
})
