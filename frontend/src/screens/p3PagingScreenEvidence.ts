import { isDeepStrictEqual } from 'node:util'

type EvidencePage = {
  page: {
    items: readonly {
      play_row: { id: string; source_event_id: string; play_number: number }
    }[]
    next_cursor: string | null
  }
}

/** 試験専用。26件以下の同版原本を最大二頁で照合し、実対象だけを返す。 */
export async function readP3ScreenTarget<T extends EvidencePage>(
  head: T,
  target: number,
  count: number,
  next: (cursor: string) => Promise<T>,
): Promise<T['page']['items'][number]> {
  if (
    !Number.isSafeInteger(count) ||
    count < 1 ||
    count > 26 ||
    target < 1 ||
    target > count
  )
    throw new Error('P3画面試験の有限範囲が不正')
  let page = head
  let seen = 0
  let found: T['page']['items'][number] | undefined
  const ids = new Set<string>()
  const events = new Set<string>()
  const cursors = new Set<string>()
  for (let ordinal = 0; ordinal < 2; ordinal++) {
    if (!isDeepStrictEqual({ ...page, page: null }, { ...head, page: null }))
      throw new Error('P3画面試験の保存版が混在')
    if (page.page.items.length < 1 || page.page.items.length > 25)
      throw new Error('P3画面試験の頁件数が不正')
    for (const item of page.page.items) {
      const row = item.play_row
      seen++
      if (
        row.play_number !== seen ||
        ids.has(row.id) ||
        events.has(row.source_event_id)
      )
        throw new Error('P3画面試験の原本位置または実IDが重複')
      ids.add(row.id)
      events.add(row.source_event_id)
      if (seen === target) found = item
    }
    const cursor = page.page.next_cursor
    if (cursor === null) {
      if (seen !== count || !found) throw new Error('P3画面試験の原本が欠落')
      return found
    }
    if (ordinal === 1 || cursors.has(cursor))
      throw new Error('P3画面試験の頁上限を超過')
    cursors.add(cursor)
    page = await next(cursor)
  }
  throw new Error('P3画面試験の原本が未確定')
}
