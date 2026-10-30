import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import StrikeZone from '../components/zone/StrikeZone.vue'
import GameScreen from './GameScreen.vue'

const pitchTypes = [
  { id: 'fastball', displayName: '直球', enabled: true },
  { id: 'slider', displayName: 'スライダー', enabled: true },
  { id: 'hidden', displayName: '無効な球種', enabled: false },
]

const results = [
  { id: 'ball', displayName: 'ボール', enabled: true },
  { id: 'strike', displayName: '見逃し', enabled: true },
  { id: 'hidden-result', displayName: '無効な結果', enabled: false },
]

const courseView = { plateSide: '右', viewpoint: 'pitcher' as const }

afterEach(() => vi.restoreAllMocks())

describe('GameScreen の試合状態表示', () => {
  it('呼出元の整形済み文字列を変更せず表示する', () => {
    const wrapper = mount(GameScreen, {
      props: {
        state: {
          gameName: '筑波大 対 東京大',
          inning: '7回',
          half: '表',
          awayScore: '3',
          homeScore: '2',
          outs: '1アウト',
          runners: '一・三塁',
          count: '2ボール 1ストライク',
          batter: '打者 山田',
          pitcher: '投手 佐藤',
        },
      },
    })

    expect(wrapper.get('[data-testid="game-name"]').text()).toBe(
      '筑波大 対 東京大',
    )
    expect(wrapper.get('[data-testid="inning"]').text()).toBe('7回')
    expect(wrapper.get('[data-testid="half"]').text()).toBe('表')
    expect(wrapper.get('[data-testid="away-score"]').text()).toBe('3')
    expect(wrapper.get('[data-testid="home-score"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="outs"]').text()).toBe('1アウト')
    expect(wrapper.get('[data-testid="runners"]').text()).toBe('一・三塁')
    expect(wrapper.get('[data-testid="count"]').text()).toBe(
      '2ボール 1ストライク',
    )
    expect(wrapper.get('[data-testid="batter"]').text()).toBe('打者 山田')
    expect(wrapper.get('[data-testid="pitcher"]').text()).toBe('投手 佐藤')
    expect(wrapper.text()).not.toContain('保存しました')
  })

  it('未供給・欠損・空文字の値を未取得と表示する', async () => {
    const wrapper = mount(GameScreen)

    const fields = [
      'game-name',
      'inning',
      'half',
      'away-score',
      'home-score',
      'outs',
      'runners',
      'count',
      'batter',
      'pitcher',
    ]
    expect(
      fields.map((field) => wrapper.get(`[data-testid="${field}"]`).text()),
    ).toEqual(Array(10).fill('未取得'))

    await wrapper.setProps({ state: { gameName: '', awayScore: null } })
    expect(wrapper.get('[data-testid="game-name"]').text()).toBe('未取得')
    expect(wrapper.get('[data-testid="away-score"]').text()).toBe('未取得')
  })

  it('生数値が実行時に混入しても表示せず未取得にする', () => {
    const wrapper = mount(GameScreen, {
      props: {
        state: { awayScore: 3, count: 2 } as unknown as {
          awayScore: string
          count: string
        },
      },
    })

    expect(wrapper.get('[data-testid="away-score"]').text()).toBe('未取得')
    expect(wrapper.get('[data-testid="count"]').text()).toBe('未取得')
  })

  it('利用者文字列をHTMLとして解釈しない', () => {
    const input = '<img src=x onerror=alert(1)>'
    const wrapper = mount(GameScreen, {
      props: { state: { gameName: input, batter: input } },
    })

    expect(wrapper.get('[data-testid="game-name"]').text()).toBe(input)
    expect(wrapper.get('[data-testid="batter"]').text()).toBe(input)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.html()).toContain('&lt;img')
  })
})

describe('GameScreen の入力下書き', () => {
  it('有効候補のIDだけを選び、球速と結果を訂正・個別消去できる', async () => {
    const wrapper = mount(GameScreen, {
      props: { pitchTypes, results, courseView },
    })
    const pitchType = wrapper.get<HTMLSelectElement>(
      '[data-testid="pitch-type"]',
    )
    const result = wrapper.get<HTMLSelectElement>(
      '[data-testid="pitch-result"]',
    )
    const speed = wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]')

    expect(
      pitchType.findAll('option').map((option) => option.attributes('value')),
    ).toEqual(['', 'fastball', 'slider'])
    expect(
      result.findAll('option').map((option) => option.attributes('value')),
    ).toEqual(['', 'ball', 'strike'])

    await pitchType.setValue('slider')
    await result.setValue('strike')
    await speed.setValue('135')
    expect(pitchType.element.value).toBe('slider')
    expect(result.element.value).toBe('strike')
    expect(speed.element.value).toBe('135')

    await pitchType.setValue('fastball')
    await result.setValue('ball')
    await speed.setValue('128')
    expect(pitchType.element.value).toBe('fastball')
    expect(result.element.value).toBe('ball')
    expect(speed.element.value).toBe('128')

    await wrapper.get('[data-testid="clear-draft"]').trigger('click')
    expect(pitchType.element.value).toBe('')
    expect(result.element.value).toBe('')
    expect(speed.element.value).toBe('')
  })

  it('候補の改名は選択IDを保ち、無効化・削除はIDを消して再追加でも復活しない', async () => {
    const wrapper = mount(GameScreen, { props: { pitchTypes, results } })
    const pitchType = wrapper.get<HTMLSelectElement>(
      '[data-testid="pitch-type"]',
    )
    const result = wrapper.get<HTMLSelectElement>(
      '[data-testid="pitch-result"]',
    )

    await pitchType.setValue('slider')
    await result.setValue('strike')
    await wrapper.setProps({
      pitchTypes: pitchTypes.map((candidate) =>
        candidate.id === 'slider'
          ? { ...candidate, displayName: '新しい球種名' }
          : candidate,
      ),
      results: results.map((candidate) =>
        candidate.id === 'strike'
          ? { ...candidate, displayName: '新しい結果名' }
          : candidate,
      ),
    })
    expect(pitchType.element.value).toBe('slider')
    expect(result.element.value).toBe('strike')
    expect(pitchType.text()).toContain('新しい球種名')
    expect(result.text()).toContain('新しい結果名')

    await wrapper.setProps({
      pitchTypes: pitchTypes.map((candidate) =>
        candidate.id === 'slider'
          ? { ...candidate, enabled: false }
          : candidate,
      ),
      results: results.filter((candidate) => candidate.id !== 'strike'),
    })
    expect(pitchType.element.value).toBe('')
    expect(result.element.value).toBe('')

    await wrapper.setProps({ pitchTypes, results })
    expect(pitchType.element.value).toBe('')
    expect(result.element.value).toBe('')

    await pitchType.setValue('fastball')
    await result.setValue('ball')
    await wrapper.setProps({
      pitchTypes: pitchTypes.filter((candidate) => candidate.id !== 'fastball'),
      results: results.map((candidate) =>
        candidate.id === 'ball' ? { ...candidate, enabled: false } : candidate,
      ),
    })
    expect(pitchType.element.value).toBe('')
    expect(result.element.value).toBe('')

    await wrapper.setProps({ pitchTypes, results })
    expect(pitchType.element.value).toBe('')
    expect(result.element.value).toBe('')
  })

  it('StrikeZone の選択値を再変換せず保持し、訂正・消去できる', async () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 10,
      top: 20,
      width: 263,
      height: 263,
    } as DOMRect)
    const wrapper = mount(GameScreen, { props: { courseView } })
    const zone = wrapper.getComponent(StrikeZone)

    zone.get('svg').element.dispatchEvent(
      new MouseEvent('pointerdown', {
        bubbles: true,
        clientX: 90,
        clientY: 88,
      }),
    )
    await wrapper.vm.$nextTick()
    expect(zone.props('point')).toEqual({ x: 80, y: 68 })
    expect(wrapper.get('[data-testid="course-status"]').text()).toContain(
      '選択済み',
    )

    zone.get('svg').element.dispatchEvent(
      new MouseEvent('pointerdown', {
        bubbles: true,
        clientX: 100,
        clientY: 98,
      }),
    )
    await wrapper.vm.$nextTick()
    expect(zone.props('point')).toEqual({ x: 173, y: 78 })

    await wrapper.get('button[data-testid="clear-course"]').trigger('click')
    expect(zone.props('point')).toBeNull()
  })

  it('再マウントで下書きが消え、保存成功と誤認させる操作・表示がない', async () => {
    const props = { pitchTypes, results, courseView }
    const wrapper = mount(GameScreen, { props })
    await wrapper.get('[data-testid="pitch-type"]').setValue('fastball')
    await wrapper.get('[data-testid="pitch-result"]').setValue('ball')
    await wrapper.get('[data-testid="pitch-speed"]').setValue('140')
    wrapper.getComponent(StrikeZone).vm.$emit('tap', 123, 78)
    await wrapper.vm.$nextTick()
    expect(wrapper.getComponent(StrikeZone).props('point')).toEqual({
      x: 123,
      y: 78,
    })

    wrapper.unmount()
    const remounted = mount(GameScreen, { props })
    expect(
      remounted.get<HTMLSelectElement>('[data-testid="pitch-type"]').element
        .value,
    ).toBe('')
    expect(
      remounted.get<HTMLSelectElement>('[data-testid="pitch-result"]').element
        .value,
    ).toBe('')
    expect(
      remounted.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('')
    expect(remounted.getComponent(StrikeZone).props('point')).toBeNull()
    expect(remounted.text()).toContain('保存・送信されません')
    expect(remounted.text()).not.toContain('保存しました')
    expect(remounted.find('button[type="submit"]').exists()).toBe(false)
    // 確定の操作は置くが、計算核との接続まで無効のままにする（封鎖の正は
    // GameScreenCommitGate で、その試験が封鎖の内容を固定する）。
    expect(
      remounted.get<HTMLButtonElement>('[data-testid="commit-pitch"]').element
        .disabled,
    ).toBe(true)
    expect(remounted.text()).toContain('確定することはできません')
  })
})

describe('GameScreen の表示と操作のアクセシビリティ', () => {
  it('入力欄に可視ラベルがあり、未取得と未保存の状態を文章で示す', () => {
    const wrapper = mount(GameScreen)
    const labels = [
      ['pitch-type', '球種'],
      ['pitch-speed', '球速'],
      ['pitch-result', '結果'],
    ] as const

    for (const [id, name] of labels) {
      expect(wrapper.get(`label[for="${id}"]`).text()).toBe(name)
      const control = wrapper.get<HTMLInputElement | HTMLSelectElement>(
        `#${id}`,
      )
      expect(control.element.labels?.item(0)?.textContent?.trim()).toBe(name)
    }

    expect(wrapper.get('[data-testid="game-name"]').text()).toBe('未取得')
    for (const [testId, name] of [
      ['inning', '回'],
      ['half', '表裏'],
      ['away-score', '先攻'],
      ['home-score', '後攻'],
      ['outs', 'アウト'],
      ['runners', '走者'],
      ['count', 'カウント'],
      ['batter', '打者'],
      ['pitcher', '投手'],
    ] as const) {
      const value = wrapper.get(`[data-testid="${testId}"]`)
      expect(value.element.tagName).toBe('DD')
      expect(value.element.previousElementSibling?.tagName).toBe('DT')
      expect(value.element.previousElementSibling?.textContent).toBe(name)
      expect(value.text()).toBe('未取得')
    }

    const draft = wrapper.get('section[aria-label="投球入力の下書き"]')
    const note = draft.get('#draft-unsaved-note')
    expect(note.text()).toContain('この入力は保存・送信されません')
    expect(note.text()).toContain('画面を離れると消えます')
    for (const id of ['pitch-type', 'pitch-speed', 'pitch-result']) {
      expect(draft.get(`#${id}`).attributes('aria-describedby')).toBe(
        note.attributes('id'),
      )
    }
    expect(draft.find('button[type="submit"]').exists()).toBe(false)
  })

  it('コースをキーボードで選択・訂正でき、選択状態が表示に反映される', async () => {
    const wrapper = mount(GameScreen, { props: { courseView } })
    const zone = wrapper.getComponent(StrikeZone)
    const svg = zone.get('svg')

    expect(svg.attributes('aria-describedby')).toBe('draft-unsaved-note')
    expect(svg.attributes('tabindex')).toBe('0')
    expect(svg.attributes('aria-label')).toContain('矢印キーでコース入力')
    expect(svg.attributes('aria-label')).toContain('現在は未入力')

    await svg.trigger('keydown', { key: 'ArrowRight' })
    const first = zone.props('point') as { x: number; y: number }
    expect(Number.isFinite(first.x)).toBe(true)
    expect(Number.isFinite(first.y)).toBe(true)
    expect(wrapper.get('[data-testid="course-status"]').text()).toContain(
      '選択済み（未保存）',
    )
    expect(svg.attributes('aria-label')).toContain('現在位置')

    await svg.trigger('keydown', { key: 'ArrowLeft', shiftKey: true })
    const corrected = zone.props('point') as { x: number; y: number }
    expect(corrected).not.toEqual(first)
  })
})

describe('GameScreen の入力可否と下書きの配線', () => {
  const identity = {
    d5: '0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b',
    d4: 'generation-a',
    gameId: 'f1e2d3c4-b5a6-4789-9abc-def012345678',
    d2: '0007',
  }

  function allowed() {
    return {
      battedBall: false,
      rbiRulingRequired: false,
      scoringCandidateRunners: [],
    }
  }

  it('入力できない観測では入力欄を塞ぎ、理由を日本語で出す', () => {
    const wrapper = mount(GameScreen, {
      props: {
        pitchTypes,
        results,
        inputObservation: { ...allowed(), battedBall: true },
      },
    })

    for (const testId of ['pitch-type', 'pitch-speed', 'pitch-result']) {
      expect(
        wrapper.get<HTMLInputElement | HTMLSelectElement>(
          `[data-testid="${testId}"]`,
        ).element.disabled,
      ).toBe(true)
    }
    const reasons = wrapper.get('[data-testid="input-ineligible-reasons"]')
    expect(reasons.text()).toContain('打球が発生したプレイ')
    // 内部 ID をそのまま利用者に出さない。
    expect(reasons.text()).not.toContain('in-play-not-supported')
  })

  it('入力できる観測では入力欄を塞がない', () => {
    const wrapper = mount(GameScreen, {
      props: { pitchTypes, results, inputObservation: allowed() },
    })

    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="pitch-type"]').element
        .disabled,
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="input-ineligible-reasons"]').exists(),
    ).toBe(false)
  })

  it('確定値が揃うと下書きを組み立て、保存も送信もしていないと示す', async () => {
    const wrapper = mount(GameScreen, {
      props: { pitchTypes, results, eventIdentity: identity },
    })

    expect(wrapper.find('[data-testid="draft-assembly-status"]').exists()).toBe(
      false,
    )
    await wrapper.get('[data-testid="pitch-type"]').setValue('fastball')
    await wrapper.get('[data-testid="pitch-result"]').setValue('ball')

    expect(
      wrapper.get('[data-testid="draft-assembly-status"]').text(),
    ).toContain('組み立てました')
  })

  it('観測が入力不可へ変われば下書き組み立て成功を表示しない', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        pitchTypes,
        results,
        eventIdentity: identity,
        inputObservation: allowed(),
      },
    })
    await wrapper.get('[data-testid="pitch-type"]').setValue('fastball')
    await wrapper.get('[data-testid="pitch-result"]').setValue('ball')
    expect(
      wrapper.get('[data-testid="draft-assembly-status"]').text(),
    ).toContain('組み立てました')

    await wrapper.setProps({
      inputObservation: { ...allowed(), battedBall: true },
    })
    expect(wrapper.find('[data-testid="draft-assembly-status"]').exists()).toBe(
      false,
    )
    expect(
      wrapper.get('[data-testid="input-ineligible-reasons"]').text(),
    ).toContain('打球が発生したプレイ')
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="commit-pitch"]').element
        .disabled,
    ).toBe(true)
  })

  it('識別子が正規形でなければ、理由つきで組み立てられないと示す', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        pitchTypes,
        results,
        eventIdentity: { ...identity, d5: 'NOT-A-UUID' },
      },
    })

    await wrapper.get('[data-testid="pitch-type"]').setValue('fastball')
    await wrapper.get('[data-testid="pitch-result"]').setValue('ball')

    expect(
      wrapper.get('[data-testid="draft-assembly-status"]').text(),
    ).toContain('d5')
  })
})
