// @vitest-environment node
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'

const root = resolve(process.cwd(), '..')
const old4 = '4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1'
const old9 = '9ae9d16db1f2fa48905eb0ac951c8cb3ce5704dfe308df95a7a0bba155f33d19'
const current =
  'ce622726b41f55f4f62c5db76241dc05499e9a53071ba134b5ce8da7a54d64fd'

function read(path: string): string {
  return readFileSync(resolve(root, path), 'utf8')
}

function differences(a: unknown, b: unknown, path = ''): string[] {
  if (Object.is(a, b)) return []
  if (
    typeof a !== 'object' ||
    a === null ||
    typeof b !== 'object' ||
    b === null ||
    Array.isArray(a) !== Array.isArray(b)
  )
    return [path]
  const left = a as Record<string, unknown>
  const right = b as Record<string, unknown>
  expect(Object.keys(right).sort(), path).toEqual(Object.keys(left).sort())
  return Object.keys(left).flatMap((key) =>
    differences(left[key], right[key], `${path}/${key}`),
  )
}

it('v2現行56例は旧数学/V8を保持し実行pinと自己echo二欄だけを変える', () => {
  const old = JSON.parse(
    read('contracts/state-transition/play_prefix_v2_payload_vectors.json'),
  )
  const next = JSON.parse(
    read('frontend/src/api/fixtures/currentPlayPrefixV2Payload.v1.json'),
  )
  const changed = differences(old, next)
  expect(changed).toHaveLength(56 * 5)
  expect(
    changed.every((path) =>
      /^\/cases\/\d+\/V7\/calculation\/(?:artifactSha256|request\/source\/executionArtifactSha256|response\/value\/executionArtifactSha256|request\/nextCheckpoint\/digest|response\/value\/nextPrefixRef\/checkpoint\/digest)$/.test(
        path,
      ),
    ),
  ).toBe(true)
  expect(
    next.cases.every(
      (row: { V7: { calculation: { artifactSha256: string } } }) =>
        row.V7.calculation.artifactSha256 === current,
    ),
  ).toBe(true)
})

it('lineup現行34例は旧数学/V8を保持しpin・32field内pin・自己echoだけを変える', () => {
  const old = JSON.parse(
    read(
      'contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json',
    ),
  )
  const next = JSON.parse(
    read('frontend/src/api/fixtures/currentLineupPrefixPayload.v1.json'),
  )
  const changed = differences(old, next)
  expect(changed).toHaveLength(34 * 8)
  expect(
    changed.every((path) =>
      /^\/cases\/\d+\/(?:V7\/calculation\/(?:artifactSha256|request\/source\/executionArtifactSha256|response\/value\/executionArtifactSha256|request\/nextCheckpoint\/digest|response\/value\/nextPrefixRef\/checkpoint\/digest)|wireHead\/(?:executionArtifactSha256|source\/executionArtifactSha256)|wireDigest)$/.test(
        path,
      ),
    ),
  ).toBe(true)
  expect(
    next.cases.every(
      (row: { V7: { calculation: { artifactSha256: string } } }) =>
        row.V7.calculation.artifactSha256 === current,
    ),
  ).toBe(true)
})

it('初球87例と打球19例は旧JSON文字列のpinだけを可逆置換する', () => {
  const pairs = [
    [
      'backend/tests/fixtures/first_ball_payload_vectors_v1.json',
      'frontend/src/api/fixtures/currentFirstBallPayload.v1.json',
      old4,
      102,
    ],
    [
      'contracts/state-transition/batted_hit_prefix_cases_v1.json',
      'frontend/src/api/fixtures/currentBattedHitPrefixCases.v1.json',
      old9,
      38,
    ],
  ] as const
  for (const [history, active, prior, count] of pairs) {
    const before = read(history),
      after = read(active)
    expect(before.split(prior).length - 1).toBe(count)
    expect(after.split(current).length - 1).toBe(count)
    expect(after.replaceAll(current, prior)).toBe(before)
  }
})

it('取消4例は旧数学と履歴を保持し実行pin三欄・CP digest三欄だけを変える', () => {
  const old = JSON.parse(
    read('frontend/src/api/fixtures/nativeUndoProduct.v1.json'),
  )
  const next = JSON.parse(
    read('frontend/src/api/fixtures/nativeUndoProduct.current.v1.json'),
  )
  const changed = differences(old, next)
  expect(changed).toHaveLength(4 * 6)
  expect(
    changed.every((path) =>
      /^\/samples\/\d+\/payload\/calculation\/(?:artifactSha256|request\/(?:prefixRef\/digest|source\/checkpoint\/(?:ref\/digest|content\/executionArtifactSha256))|response\/value\/(?:executionArtifactSha256|previousPrefixRef\/digest))$/.test(
        path,
      ),
    ),
  ).toBe(true)
  expect(
    next.samples.every(
      (row: { payload: { calculation: { artifactSha256: string } } }) =>
        row.payload.calculation.artifactSha256 === current,
    ),
  ).toBe(true)
})
