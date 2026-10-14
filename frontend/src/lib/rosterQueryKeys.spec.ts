import { describe, expect, it } from 'vitest'
import { rosterQueryKeys } from './rosterQueryKeys'

describe('rosterQueryKeys', () => {
  it('ページ付き選手一覧を共有選手 prefix の配下に置く', () => {
    const all = rosterQueryKeys.players.all('tenant-a')
    const pages = rosterQueryKeys.players.pages(
      'tenant-a',
      3,
      'team-record-a',
      25,
    )

    expect(pages.slice(0, all.length)).toEqual(all)
  })

  it('ページ付きチーム一覧を tenant 単位の共有 prefix の配下に置く', () => {
    const all = rosterQueryKeys.teamRecords.all('tenant-a')
    const pages = rosterQueryKeys.teamRecords.pages('tenant-a', 3, 25)

    expect(pages.slice(0, all.length)).toEqual(all)
  })
})
