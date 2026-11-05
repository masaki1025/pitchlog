import { describe, expect, it, vi } from 'vitest'
import * as api from '../statsPrimitives'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// 独立期待は生成入力に渡さず、実生成targetとの比較だけに使う。
const cases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../docs/features/mvp-stats-primitives/primitive-cases.candidate.json',
    ),
    'utf8',
  ),
).cases
// 配布形の印だけを先に置く。認可/正式sourceの証明ではない。
vi.hoisted(() => {
  ;(
    globalThis as { __PITCHLOG_GENERATED_WRAPPER__?: boolean }
  ).__PITCHLOG_GENERATED_WRAPPER__ = true
})

describe('生成count primitiveの純比較', () => {
  it('巨大整数をNumberへ落とさず加算する', () => {
    expect(api.addCounts('9007199254740993', '2')).toBe('9007199254740995')
    expect(() => api.addCounts(Number.MAX_SAFE_INTEGER + 1, '1')).toThrow()
  })

  it('振逃げのKとoutsを独立に保持する', () => {
    const source = cases.find(
      (c: { case_id: string }) => c.case_id === 'dropped-third-strike-reach',
    )
    const result = api.eventFacts(source.input.events[0])
    expect(result.metrics.k!.value).toBe('1')
    expect(result.metrics.pitcher_k!.value).toBe('1')
    expect(result.metrics.pitching_outs!.value).toBe('0')
  })

  it('3有効得点をbool=1へ縮めず責任を保つ', () => {
    const source = cases.find(
      (c: { case_id: string }) => c.case_id === 'home-run-3-effective-runs',
    )
    const result = api.eventFacts(source.input.events[0])
    expect(result.metrics.runs!.value).toBe('3')
    expect(result.metrics.rbi!.value).toBe('3')
    expect(result.metrics.total_bases!.value).toBe('4')
    expect(result.metrics.runs_allowed!.credits[0]!.quantity).toBe('3')
  })

  it('数量欠測を0やfalseで補わない', () => {
    const source = cases.find(
      (c: { case_id: string }) =>
        c.case_id === 'missing-run-quantities-not-boolean-one',
    )
    const result = api.eventFacts(source.input.events[0])
    expect(result.metrics.rbi!.state).toBe('source_unavailable')
    expect(result.metrics.rbi!.value).toBeNull()
    expect(result.metrics.pitch_count!.value).toBe('1')
    expect(result.pa_row!.rbi).toBeNull()
  })

  it('未回答4件を生成値で埋めない', () => {
    const source = cases.find(
      (c: { case_id: string }) => c.case_id === 'incomplete-pa-one-pitch',
    )
    const result = api.eventFacts(source.input.events[0])
    expect(result.pending).toEqual(source.expected.pending)
    expect(result.pa_row).toBeNull()
    expect(result.metrics.pa!.value).toBe('0')
  })

  it('未知enum・数値bool・遷移内上限を拒否する', () => {
    const source = cases.find(
      (c: { case_id: string }) => c.case_id === 'home-run-3-effective-runs',
    )
    const event = structuredClone(source.input.events[0])
    event.pa.hit_kind = '__proto__'
    expect(() => api.eventFacts(event)).toThrow()
    event.pa.hit_kind = 'home_run'
    event.stat_flags.投球数 = 1
    expect(() => api.eventFacts(event)).toThrow()
    event.stat_flags.投球数 = true
    event.runner_scores.push(...structuredClone(event.runner_scores))
    expect(() => api.eventFacts(event)).toThrow()
  })
})
