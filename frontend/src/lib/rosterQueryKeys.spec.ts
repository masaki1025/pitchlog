import { describe, expect, it } from 'vitest'
import { rosterQueryKeys } from './rosterQueryKeys'

describe('rosterQueryKeys', () => {
  it('自チーム鍵をtenantとauthEpochで分離し、一覧prefixへ入れない', () => {
    const first = rosterQueryKeys.selfTeamRecord('tenant-a', 3)
    expect(first).not.toEqual(rosterQueryKeys.selfTeamRecord('tenant-a', 4))
    expect(first).not.toEqual(rosterQueryKeys.selfTeamRecord('tenant-b', 3))
    expect(first).not.toEqual(
      rosterQueryKeys.teamRecords.pages('tenant-a', 3, 25),
    )
    expect(first[0]).not.toBe(rosterQueryKeys.teamRecords.all('tenant-a')[0])
    expect(first[0]).not.toBe(rosterQueryKeys.players.all('tenant-a')[0])
  })

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
