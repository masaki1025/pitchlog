/** 保存済み同版の最大3頁だけを確認する試験補助。製品計算は行わない。 */
import { isDeepStrictEqual } from 'node:util'

type PagedRow = { play_row: { id: string; play_number: number } }
type PagedHead = {
  page: { items: readonly PagedRow[]; next_cursor: string | null }
}

/** 頁以外の全値を固定し、重複や不足を成功に置き換えない。 */
export async function recordedBattedRow<Head extends PagedHead>(
  initial: Head,
  playNumber: number,
  readPage: (cursor: string) => Promise<Head>,
): Promise<Head['page']['items'][number]> {
  if (!Number.isSafeInteger(playNumber) || playNumber < 1 || playNumber > 59)
    throw new Error('59操作範囲外の記録位置')
  const metadata = (head: Head) =>
    Object.fromEntries(Object.entries(head).filter(([key]) => key !== 'page'))
  const expected = metadata(initial)
  const cursors = new Set<string>()
  const playNumbers = new Set<number>()
  const rowIds = new Set<string>()
  const matches: Head['page']['items'][number][] = []
  let head = initial
  for (let page = 0; page < 3; page++) {
    if (!isDeepStrictEqual(metadata(head), expected))
      throw new Error('記録頁の版または全head値が変化')
    if (head.page.items.length > 25) throw new Error('既定25件を超える記録頁')
    for (const row of head.page.items) {
      if (
        playNumbers.has(row.play_row.play_number) ||
        rowIds.has(row.play_row.id)
      )
        throw new Error('記録頁のplayが重複')
      playNumbers.add(row.play_row.play_number)
      rowIds.add(row.play_row.id)
      if (row.play_row.play_number === playNumber) matches.push(row)
    }
    const cursor = head.page.next_cursor
    if (cursor === null) {
      if (matches.length !== 1)
        throw new Error('保存済み当該playの実DTOが一意でない')
      return matches[0]!
    }
    if (!cursor || cursors.has(cursor) || head.page.items.length === 0)
      throw new Error('記録頁のcursorが反復または不正')
    if (page === 2) throw new Error('59操作の最大3頁を超過')
    cursors.add(cursor)
    head = await readPage(cursor)
  }
  throw new Error('保存済み当該playの実DTOがない')
}
