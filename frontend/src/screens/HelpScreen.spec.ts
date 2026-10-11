import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HelpScreen from './HelpScreen.vue'

describe('HelpScreen', () => {
  it('5 段の手順カードを順序どおりに描画する', () => {
    const wrapper = mount(HelpScreen)
    const cards = wrapper.get('section.mb-4').findAll('article')

    expect(cards).toHaveLength(5)
    expect(cards.map((card) => card.get('h2').text())).toEqual([
      'チーム・選手を準備', // dd03160:frontend/src/screens/HelpScreen.tsx:21
      '試合を作成', // dd03160:frontend/src/screens/HelpScreen.tsx:22
      '1球ずつ入力', // dd03160:frontend/src/screens/HelpScreen.tsx:23
      '保存・再開', // dd03160:frontend/src/screens/HelpScreen.tsx:24
      '確認・分析', // dd03160:frontend/src/screens/HelpScreen.tsx:25
    ])
  })

  it('戻るボタンを押すと payload なしの back を 1 回 emit する', async () => {
    const wrapper = mount(HelpScreen)

    // dd03160:frontend/src/screens/HelpScreen.tsx:35（aria-label）。
    await wrapper.get('button[aria-label="戻る"]').trigger('click')

    const backEvents = wrapper.emitted().back
    expect(backEvents).toHaveLength(1)
    expect(backEvents?.[0]).toEqual([])
  })

  it('外部依存を注入せずに単体でマウントできる', () => {
    const wrapper = mount(HelpScreen)

    expect(wrapper.exists()).toBe(true)
  })
})

describe('HelpScreen の文言', () => {
  const requiredLegacyPhrases = [
    'ホームの「新しい試合」', // dd03160:frontend/src/screens/HelpScreen.tsx:22（導線）。
    'それ以前は「試合一覧」', // dd03160:frontend/src/screens/HelpScreen.tsx:24（導線）。
    '送れなかった入力はこの端末に保持され', // dd03160:frontend/src/screens/HelpScreen.tsx:79（同期）。
    '接続回復後に自動再送されます', // dd03160:frontend/src/screens/HelpScreen.tsx:79（同期）。
    '未同期センターを開きます', // dd03160:frontend/src/screens/HelpScreen.tsx:79（同期）。
    '対象チーム・対戦相手・試合ID・期間・シーズン・試合種別', // dd03160:frontend/src/screens/HelpScreen.tsx:93（検索・出力）。
    '複数試合を選ぶと1つのZIP', // dd03160:frontend/src/screens/HelpScreen.tsx:98（出力）。
    '投手・打者・チーム集計CSVは取り込み対象外', // dd03160:frontend/src/screens/HelpScreen.tsx:103（出力）。
  ] as const

  const requiredRewrittenPhrases = [
    '初回のチーム登録はシステム管理者が行います', // design.md A-8・要件書:110,774（管理者が登録）。
    '明示的な引き継ぎ操作をしない限り記録できません', // design.md A-8・要件書:341（記録権の引き継ぎ）。
    '退避されたうえで管理コンソールで内容を確認・書き出しできます', // design.md A-8・要件書:344（退避の確認経路）。
    '分析PDF、試合用カルテへ進め', // design.md A-8・要件書:105,622（PPTX は暫定 Won't）。
  ] as const

  const forbiddenPhrases = [
    'AI分析', // 改善台帳 I-28:241（実体のない機能として破棄）。
    'PowerPoint', // 要件書:105,622（PPTX 出力は暫定 Won't）。
    'チーム新規登録', // 要件書:110,774（セルフサインアップは Won't）。
    '未同期センターで内容を確認してから再送', // 要件書:341,344,347（記録権のない端末の同期は拒否し、退避は管理コンソールで確認）。
  ] as const

  it.each(requiredLegacyPhrases)('%s を描画する', (phrase) => {
    expect(mount(HelpScreen).text()).toContain(phrase)
  })

  it.each(requiredRewrittenPhrases)('%s を描画する', (phrase) => {
    expect(mount(HelpScreen).text()).toContain(phrase)
  })

  it.each(forbiddenPhrases)('%s を描画とソースから除外する', (phrase) => {
    const rendered = mount(HelpScreen).text()
    // Vite の静的 URL 変換を避けるため、相対パスを分割して連結する。
    // './HelpScreen.vue' を直書きすると file: 以外の URL になり、readFileSync が失敗する。
    const source = readFileSync(
      new URL('./' + 'HelpScreen.vue', import.meta.url),
      'utf8',
    )

    expect(rendered).not.toContain(phrase)
    expect(source).not.toContain(phrase)
  })
})
