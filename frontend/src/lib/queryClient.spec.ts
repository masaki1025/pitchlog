import { describe, expect, it } from 'vitest'
import { queryClient } from './queryClient'

describe('queryClient', () => {
  it('クエリの既定値を設定する', () => {
    const queries = queryClient.getDefaultOptions().queries

    expect(queries?.retry).toBe(1)
    expect(queries?.refetchOnWindowFocus).toBe(false)
    expect(queries?.staleTime).toBe(30_000)
  })
})
