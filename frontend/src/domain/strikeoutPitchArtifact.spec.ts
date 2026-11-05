import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const context = createContext({})
new Script(source).runInContext(context, { timeout: 1000 })
const api = context.PitchlogDomain as Record<string, (text: string) => string>
const assets = (name: string) =>
  JSON.parse(
    readFileSync(
      resolve(process.cwd(), '../contracts/state-transition', name),
      'utf8',
    ),
  )

describe('三振を追加した単一artifact', () => {
  it('旧9口を全保持し、SO一名だけを追加した完全集合を凍結する', () => {
    expect(Object.isFrozen(api)).toBe(true)
    expect(Object.keys(api)).toEqual([
      'ping',
      'deriveState',
      'deriveOrdinaryPitch',
      'deriveTerminalPitch',
      'deriveStrikeoutPitch',
      'derivePlayPrefixWithContinuation',
      'deriveLineupPlayPrefixWithContinuation',
      'deriveFirstPitchWithContinuation',
      'deriveOrdinaryPitchWithContinuation',
      'validateInitialGameRoster',
      'quantizeCourse',
    ])
  })
  it('旧通常37・BB/HBP15・新24の全応答を受理caseから比較する', () => {
    for (const [file, method] of [
      ['ordinary_pitch_vectors_v1.json', 'deriveOrdinaryPitch'],
      ['ordinary_two_strike_foul_candidate_v1.json', 'deriveOrdinaryPitch'],
      ['terminal_pitch_cases_v1.json', 'deriveTerminalPitch'],
      ['strikeout_pitch_cases_v1.json', 'deriveStrikeoutPitch'],
    ])
      for (const row of assets(file).cases)
        expect(JSON.parse(api[method](JSON.stringify(row.request)))).toEqual(
          row.expected,
        )
  })
})
