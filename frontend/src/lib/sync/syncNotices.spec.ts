import { describe, expect, it } from 'vitest'
import * as ts from 'typescript'
import syncNoticesSource from './syncNotices.ts?raw'
import {
  createStoragePersistenceNotice,
  createSyncNotice,
  SYNC_NOTICE_CATALOG,
  SYNC_NOTICE_IDS,
  type SyncNoticeId,
  type SyncNoticeParamsById,
} from './syncNotices'

const EXPECTED_NOTICE_IDS = [
  'Q4',
  'Q5',
  'Q6',
  'Q2-b',
  'B4',
  'I6',
  'B5',
] as const satisfies readonly SyncNoticeId[]

function createQ5With(params: unknown) {
  return createSyncNotice('Q5', params as SyncNoticeParamsById['Q5'])
}

function sourceStringLiterals(source: string): readonly string[] {
  const sourceFile = ts.createSourceFile(
    'syncNotices.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const literals: string[] = []

  function visit(node: ts.Node): void {
    if (
      ts.isStringLiteralLike(node) ||
      node.kind === ts.SyntaxKind.TemplateHead ||
      node.kind === ts.SyntaxKind.TemplateMiddle ||
      node.kind === ts.SyntaxKind.TemplateTail
    ) {
      literals.push(node.getText(sourceFile))
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return literals
}

describe('syncNotices', () => {
  it('7 種の noticeId を exact-set に閉じる', () => {
    expect(SYNC_NOTICE_IDS).toHaveLength(7)
    expect(new Set(SYNC_NOTICE_IDS)).toEqual(new Set(EXPECTED_NOTICE_IDS))
    expect(new Set(Object.keys(SYNC_NOTICE_CATALOG))).toEqual(
      new Set(EXPECTED_NOTICE_IDS),
    )
  })

  // B5 は ACK が返らない経路の通知である(7-1 の A3)。6-3 の B5 行(:748)が求める
  // 2 要素(再ログインを促す / キューが保持されていることを併せて示す)を固定する。
  it('B5 は再ログインの促しとキュー保持の 2 要素を含む', () => {
    const message = SYNC_NOTICE_CATALOG.B5
    // 単語の存在だけを見ると「認証情報は保持…」のような劣化でも green になるため、
    // 2 要素それぞれを明示する句で固定する(差分レビュー P2)。
    expect(message).toContain('再ログインしてください')
    expect(message).toContain('未送信の記録はそのまま保持')
    expect(createSyncNotice('B5', {})).toEqual({
      noticeId: 'B5',
      params: {},
    })
  })

  it('B5 の文面とパラメータに内部状態を出さない', () => {
    const message: string = SYNC_NOTICE_CATALOG.B5
    for (const forbidden of ['D4', 'V12', '端末', 'テナント']) {
      expect(message).not.toContain(forbidden)
    }
    expect(Reflect.ownKeys(createSyncNotice('B5', {}).params)).toEqual([])
  })

  it('Q4 は未送信件数をパラメータに載せる', () => {
    const descriptor = createSyncNotice('Q4', { unsentCount: 351 })

    expect(descriptor).toEqual({
      noticeId: 'Q4',
      params: { unsentCount: 351 },
    })
    expect(Reflect.ownKeys(descriptor.params)).toEqual(['unsentCount'])
  })

  it('Q5 は試合と球数を別々のパラメータに載せる', () => {
    const game = '<利用者入力の試合名>'
    const descriptor = createSyncNotice('Q5', { game, pitchCount: 93 })

    expect(descriptor).toEqual({
      noticeId: 'Q5',
      params: { game, pitchCount: 93 },
    })
    expect(Reflect.ownKeys(descriptor.params)).toEqual(['game', 'pitchCount'])
  })

  it.each([
    ['試合', { pitchCount: 93 }],
    ['球数', { game: 'game-a' }],
    ['試合の値', { game: undefined, pitchCount: 93 }],
    ['球数の値', { game: 'game-a', pitchCount: undefined }],
  ])('Q5 の%sが欠けると拒否する', (_name, params) => {
    expect(() => createQ5With(params)).toThrow(
      '通知 Q5 のパラメータ集合が一致しません',
    )
  })

  it('Q6 は永続ストレージ要求の拒否結果からだけ生成する', () => {
    expect(createStoragePersistenceNotice(true)).toBeUndefined()
    expect(createStoragePersistenceNotice(false)).toEqual({
      noticeId: 'Q6',
      params: {},
    })
  })

  it('Q2-b は記録不可と記録中タブの終了導線を含む', () => {
    const message = SYNC_NOTICE_CATALOG['Q2-b']
    const descriptor = createSyncNotice('Q2-b', {})

    expect(message).toContain('記録できません')
    expect(message).toContain('記録中のタブを終了')
    expect(descriptor.noticeId).toBe('Q2-b')
    expect(Reflect.ownKeys(descriptor.params)).toEqual([])
  })

  it('B4 は確定文面の3要素を含み、権利を奪われた表現を持たない', () => {
    const message = SYNC_NOTICE_CATALOG.B4

    expect(message).toBe(
      'この端末は現在の記録権を保持していないため、この記録はサーバーへ反映せず退避しました。記録は破棄されていません。退避した記録は管理コンソールで閲覧・書き出しできます。',
    )
    expect(message).toContain('この端末は現在の記録権を保持していない')
    expect(message).toContain('退避しました')
    expect(message).toContain('破棄されていません')
    expect(message).not.toContain('取られ')
    expect(message).not.toContain('奪')
  })

  it('B4 の文面とパラメータから内部識別情報を排除する', () => {
    const descriptor = createSyncNotice('B4', {})
    const message = SYNC_NOTICE_CATALOG.B4

    expect(message).not.toContain('D4')
    expect(message).not.toContain('V12')
    expect(message).not.toContain('端末識別子')
    expect(message).not.toContain('テナント識別子')
    expect(Reflect.ownKeys(descriptor.params)).toEqual([])
    expect(() =>
      createSyncNotice('B4', {
        deviceIdentifier: {},
      } as SyncNoticeParamsById['B4']),
    ).toThrow('通知 B4 のパラメータ集合が一致しません')
  })

  it('I6 の端末永続化失敗を記述子として顕在化する', () => {
    const descriptor = createSyncNotice('I6', {})

    expect(descriptor).toEqual({ noticeId: 'I6', params: {} })
    expect(SYNC_NOTICE_CATALOG.I6).toContain('永続化できませんでした')
  })

  it('通知契約に HTML 文字列や生 HTML 挿入経路を持たない', () => {
    expect(syncNoticesSource).not.toContain('innerHTML')
    expect(syncNoticesSource).not.toContain('v-html')
    expect(
      sourceStringLiterals(syncNoticesSource).filter((literal) =>
        literal.includes('<'),
      ),
    ).toEqual([])
  })
})
