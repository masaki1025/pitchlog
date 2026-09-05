// このカタログと記述子は docs/design/sync-protocol.md 6-3・7-4 と、
// docs/features/sync-queue-lifecycle/plan.md 4 節の通知契約の実装である。
// 表示とエスケープは後続の画面層に委ね、ここでは素のデータだけを扱う。

export const SYNC_NOTICE_CATALOG = {
  Q4: '未送信件数を表示します。',
  Q5: '同期が成功し、キューが空になりました。',
  Q6: '永続ストレージの要求が拒否されたため、キューが消去される可能性があります。',
  'Q2-b':
    'このタブでは記録できません。記録中のタブを終了してから、もう一度お試しください。',
  B4: 'この端末は現在の記録権を保持していないため、この記録はサーバーへ反映せず退避しました。記録は破棄されていません。退避した記録は管理コンソールで閲覧・書き出しできます。',
  I6: '変更受理結果を端末へ永続化できませんでした。保存されていない結果があることを管理者へ通知してください。',
} as const

export type SyncNoticeId = keyof typeof SYNC_NOTICE_CATALOG

export const SYNC_NOTICE_IDS: readonly SyncNoticeId[] = Object.freeze(
  Object.keys(SYNC_NOTICE_CATALOG) as SyncNoticeId[],
)

type NoNoticeParams = Readonly<Record<never, never>>

export type SyncNoticeParamsById = Readonly<{
  Q4: Readonly<{ unsentCount: number }>
  Q5: Readonly<{ game: unknown; pitchCount: number }>
  Q6: NoNoticeParams
  'Q2-b': NoNoticeParams
  B4: NoNoticeParams
  I6: NoNoticeParams
}>

export type SyncNoticeDescriptor<Id extends SyncNoticeId = SyncNoticeId> =
  Id extends SyncNoticeId
    ? Readonly<{
        noticeId: Id
        params: SyncNoticeParamsById[Id]
      }>
    : never

const NOTICE_PARAMETER_KEYS = {
  Q4: ['unsentCount'],
  Q5: ['game', 'pitchCount'],
  Q6: [],
  'Q2-b': [],
  B4: [],
  I6: [],
} as const satisfies Readonly<Record<SyncNoticeId, readonly string[]>>

function assertNoticeParams(noticeId: SyncNoticeId, params: unknown): void {
  if (!Object.hasOwn(SYNC_NOTICE_CATALOG, noticeId)) {
    throw new Error(`未知の通知 ID です: ${noticeId}`)
  }
  if (typeof params !== 'object' || params === null || Array.isArray(params)) {
    throw new Error(`通知 ${noticeId} のパラメータが不正です`)
  }

  const expectedKeys = NOTICE_PARAMETER_KEYS[noticeId]
  const expectedKeySet = new Set<string>(expectedKeys)
  const actualKeys = Reflect.ownKeys(params)
  if (
    actualKeys.length !== expectedKeys.length ||
    actualKeys.some(
      (key) => typeof key !== 'string' || !expectedKeySet.has(key),
    ) ||
    expectedKeys.some(
      (key) =>
        !Object.hasOwn(params, key) || Reflect.get(params, key) === undefined,
    )
  ) {
    throw new Error(`通知 ${noticeId} のパラメータ集合が一致しません`)
  }
}

export function createSyncNotice<Id extends SyncNoticeId>(
  noticeId: Id,
  params: SyncNoticeParamsById[Id],
): SyncNoticeDescriptor<Id> {
  assertNoticeParams(noticeId, params)
  return Object.freeze({ noticeId, params }) as SyncNoticeDescriptor<Id>
}

export function createStoragePersistenceNotice(
  storagePersistenceGranted: boolean,
): SyncNoticeDescriptor<'Q6'> | undefined {
  return storagePersistenceGranted
    ? undefined
    : createSyncNotice('Q6', Object.freeze({}))
}
