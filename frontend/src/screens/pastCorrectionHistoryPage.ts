/** 同じ確定headの25件頁だけを保持し、対象の実行を探す。 */
import {
  readLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'

export function sameP3HistoryHead(
  first: LineupPrefixGame,
  next: LineupPrefixGame,
): boolean {
  return (
    first.id === next.id &&
    first.status === next.status &&
    first.current_d4 === next.current_d4 &&
    first.recovery_generation === next.recovery_generation &&
    sameOrdinaryWire(first.prefix_ref, next.prefix_ref) &&
    sameOrdinaryWire(first.after, next.after) &&
    sameOrdinaryWire(first.checkpoint_anchor, next.checkpoint_anchor) &&
    sameOrdinaryWire(first.storage_anchor, next.storage_anchor)
  )
}

/** 通常v3の連続D1を保証したサーバー頁の欠落・早期終端を拒否する。 */
export function completeP3HistoryPage(
  game: LineupPrefixGame,
  firstD1: number,
): boolean {
  if (!Number.isSafeInteger(firstD1) || firstD1 < 1) return false
  const remaining = BigInt(game.prefix_ref.length) - BigInt(firstD1) + 1n
  if (remaining < 0n) return false
  const count = remaining > 25n ? 25 : Number(remaining)
  return (
    game.page.items.length === count &&
    (game.page.next_cursor !== null) === remaining > 25n
  )
}

export async function readP3TargetPage(
  gameId: string,
  d1: number,
  assertIdentity: () => void,
): Promise<{
  game: LineupPrefixGame
  target: LineupPrefixGame['page']['items'][number]
}> {
  if (!Number.isSafeInteger(d1) || d1 < 1)
    throw new Error('訂正対象の位置が不正です')
  let cursor: string | null = null
  let firstD1 = 1
  let head: LineupPrefixGame | null = null
  for (;;) {
    const read = await readLineupPrefixGame(gameId, cursor, 25)
    assertIdentity()
    if (
      read.kind !== 'found' ||
      !completeP3HistoryPage(read.game, firstD1) ||
      (head !== null && !sameP3HistoryHead(head, read.game))
    )
      throw new Error('訂正履歴の同一版を確認できません')
    const game = read.game
    if (head === null) {
      if (BigInt(d1) > BigInt(game.prefix_ref.length))
        throw new Error('訂正対象が確定水位を越えています')
      // 先頭頁の配列を保持せず、headの比較に必要な一定サイズだけ残す。
      head = { ...game, page: { items: [], next_cursor: null } }
    }
    const target = game.page.items[d1 - firstD1]
    if (target) return { game, target }
    const next = game.page.next_cursor
    if (next === null || next === cursor || game.page.items.length === 0)
      throw new Error('訂正履歴の次頁が不正です')
    firstD1 += game.page.items.length
    cursor = next
  }
}
