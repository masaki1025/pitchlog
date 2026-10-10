import { describe, expect, it } from 'vitest'
import { buildTeamSearchModel, normalizeTeamSearch } from './teamSearch'

describe('teamSearch', () => {
  it('チーム候補はAPI順を保ったまま重複を除く', () => {
    const model = buildTeamSearchModel(
      ['筑波大学', 'JR東日本東北', '筑波大学'],
      '',
    )

    expect(model.options).toStrictEqual(['筑波大学', 'JR東日本東北'])
    expect(model.matchCount).toBe(2)
    expect(model.selectionTarget).toBeUndefined()
  })

  it('全半角・大文字小文字・空白の違いを吸収して検索する', () => {
    const teams = ['IMF BANDITS 富山', 'JR東日本東北', 'トヨタ自動車東日本']

    expect(normalizeTeamSearch('ＩＭＦ bandits')).toBe('imfbandits')
    expect(buildTeamSearchModel(teams, 'ｊｒ 東日本').options).toStrictEqual([
      'JR東日本東北',
    ])
    expect(buildTeamSearchModel(teams, 'トヨタ').selectionTarget).toBe(
      'トヨタ自動車東日本',
    )
  })

  it('検索に一致しないときは空の候補一覧を返す', () => {
    const model = buildTeamSearchModel(['筑波大学', '北海道ガス'], '存在しない')

    expect(model.options).toStrictEqual([])
    expect(model.matchCount).toBe(0)
    expect(model.selectionTarget).toBeUndefined()
  })

  it('完全一致を複数候補より優先して確定候補にする', () => {
    const model = buildTeamSearchModel(
      ['JR東日本東北', 'JR東日本'],
      'ＪＲ 東日本',
    )

    expect(model.matchCount).toBe(2)
    expect(model.selectionTarget).toBe('JR東日本')
  })

  it('空白だけの検索語では全チームを返す', () => {
    const model = buildTeamSearchModel(['筑波大学', '北海道ガス'], ' \t ')

    expect(model.options).toStrictEqual(['筑波大学', '北海道ガス'])
    expect(model.matchCount).toBe(2)
    expect(model.selectionTarget).toBeUndefined()
  })

  it('検索語が空でもチームが一つなら確定候補にする', () => {
    const model = buildTeamSearchModel(['筑波大学'], '')

    expect(model.options).toStrictEqual(['筑波大学'])
    expect(model.matchCount).toBe(1)
    expect(model.selectionTarget).toBe('筑波大学')
  })
})
