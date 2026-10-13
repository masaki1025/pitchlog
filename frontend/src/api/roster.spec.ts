import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import {
  createPlayer,
  createTeamRecord,
  getPlayer,
  hideTeamRecord,
  listPlayers,
  listTeamRecords,
  updatePlayer,
  updateTeamRecord,
  type PlayerRead,
  type TeamRecordRead,
} from './roster'

const team: TeamRecordRead = {
  id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  kind: 'opponent',
  name: '相手',
  hidden_at: null,
}

const player: PlayerRead = {
  id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  team_record_id: team.id,
  name: '投手',
  throws: 'right',
  bats: 'left',
  uniform_number: '7',
  roster_status_key: 'active',
  roster_label_key: null,
  hidden_at: null,
}

let pinia: Pinia

function respond(body: unknown, status = 200): void {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function expectRequest(
  method: string,
  url: string,
  body?: unknown,
  signal?: AbortSignal,
): void {
  const fetchMock = vi.mocked(fetch)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  const [actualUrl, init] = fetchMock.mock.calls[0]!
  expect(actualUrl).toBe(url)
  expect(init?.method).toBe(method)
  expect(init?.credentials).toBe('include')
  expect(init?.body).toBe(body === undefined ? undefined : JSON.stringify(body))
  expect(init?.signal).toBe(signal)
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  disposePinia(pinia)
  queryClient.clear()
})

describe('roster API', () => {
  it('listTeamRecords は GET とページ query を送り、ページを返す', async () => {
    const page = { items: [team], next_cursor: 'next' }
    const signal = new AbortController().signal
    respond(page)

    const result = await listTeamRecords(
      { limit: 2, cursor: 'next/page', include_hidden: true },
      { signal },
    )

    expectRequest(
      'GET',
      '/api/team-records?limit=2&cursor=next%2Fpage&include_hidden=true',
      undefined,
      signal,
    )
    expect(result).toStrictEqual(page)
  })

  it('listTeamRecords は null の cursor を query に載せない', async () => {
    const page = { items: [], next_cursor: null }
    respond(page)

    const result = await listTeamRecords({ limit: 1, cursor: null })

    expectRequest('GET', '/api/team-records?limit=1')
    expect(result).toStrictEqual(page)
  })

  it('createTeamRecord は POST で本文を送り、類似名を含む結果を返す', async () => {
    const body = { name: '相手' }
    const created = { ...team, similar_names: ['相手A'] }
    respond(created, 201)

    const result = await createTeamRecord(body)

    expectRequest('POST', '/api/team-records', body)
    expect(result).toStrictEqual(created)
  })

  it('updateTeamRecord は id をエンコードして PATCH し、変更結果を返す', async () => {
    const body = { name: '新しい相手' }
    const updated = { ...team, name: body.name }
    respond(updated)

    const result = await updateTeamRecord('team/with space', body)

    expectRequest('PATCH', '/api/team-records/team%2Fwith%20space', body)
    expect(result).toStrictEqual(updated)
  })

  it('hideTeamRecord は id をエンコードして DELETE し、hidden_at を返す', async () => {
    const hidden = { ...team, hidden_at: '2026-10-11T00:00:00Z' }
    respond(hidden)

    const result = await hideTeamRecord('team/id')

    expectRequest('DELETE', '/api/team-records/team%2Fid')
    expect(result).toStrictEqual(hidden)
  })

  it('listPlayers は全ての絞り込みとページ query を送り、ページを返す', async () => {
    const page = { items: [player], next_cursor: 'next' }
    respond(page)

    const result = await listPlayers({
      limit: 2,
      cursor: 'next/page',
      include_hidden: true,
      team_record_id: team.id,
      roster_status_key: 'active',
    })

    expectRequest(
      'GET',
      `/api/players?limit=2&cursor=next%2Fpage&include_hidden=true&team_record_id=${team.id}&roster_status_key=active`,
    )
    expect(result).toStrictEqual(page)
  })

  it('listPlayers は undefined の cursor を query に載せない', async () => {
    const page = { items: [], next_cursor: null }
    respond(page)

    const result = await listPlayers({ limit: 1, cursor: undefined })

    expectRequest('GET', '/api/players?limit=1')
    expect(result).toStrictEqual(page)
  })

  it('getPlayer は id をエンコードして GET し、選手を返す', async () => {
    respond(player)

    const result = await getPlayer('player/id')

    expectRequest('GET', '/api/players/player%2Fid')
    expect(result).toStrictEqual(player)
  })

  it('createPlayer は POST で本文を送り、同じ背番号の選手を含む結果を返す', async () => {
    const body = {
      team_record_id: team.id,
      name: '新選手',
      throws: 'left' as const,
      bats: 'both' as const,
      uniform_number: '7',
      roster_status_key: 'active',
      roster_label_key: null,
    }
    const created = {
      ...player,
      name: body.name,
      same_number_players: [player],
    }
    respond(created, 201)

    const result = await createPlayer(body)

    expectRequest('POST', '/api/players', body)
    expect(result).toStrictEqual(created)
  })

  it('updatePlayer は id をエンコードして PATCH し、変更結果を返す', async () => {
    const body = {
      name: '変更後',
      throws: null,
      bats: 'both' as const,
      uniform_number: null,
    }
    const updated = {
      ...player,
      name: body.name,
      throws: null,
      bats: body.bats,
      uniform_number: null,
    }
    const signal = new AbortController().signal
    respond(updated)

    const result = await updatePlayer('player/id', body, { signal })

    expectRequest('PATCH', '/api/players/player%2Fid', body, signal)
    expect(result).toStrictEqual(updated)
  })

  it('一覧の limit を省いた呼び出しは型が拒否する', () => {
    const rejectedCalls = () => {
      // @ts-expect-error limit は必須。
      listTeamRecords({})
      // @ts-expect-error limit は必須。
      listPlayers({})
    }

    expect(rejectedCalls).toBeTypeOf('function')
  })

  it('PlayerUpdate は在籍区分の項目を型が拒否する', () => {
    const rejectedCalls = () => {
      // @ts-expect-error 更新ルータは roster_status_key を受け付けない。
      updatePlayer(player.id, { roster_status_key: 'active' })
      // @ts-expect-error 更新ルータは roster_label_key を受け付けない。
      updatePlayer(player.id, { roster_label_key: 'starter' })
    }

    expect(rejectedCalls).toBeTypeOf('function')
  })
})
