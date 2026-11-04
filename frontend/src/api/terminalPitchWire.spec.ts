// @vitest-environment node
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import vectors from '../../../contracts/state-transition/play_prefix_v2_payload_vectors.json'
import type { PlayPrefixV7 } from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import {
  canonicalPlayJson,
  formatTerminalPitchWire,
  playHash,
  playWireHead,
  sealPlayMetadata,
  type PlaySuccess,
} from './terminalPitchWire'
const rows = vectors.cases as unknown as {
  caseId: string
  V7: PlayPrefixV7
  V8: unknown
}[]
beforeEach(() => {
  const vm: Record<string, unknown> = {}
  runInNewContext(
    readFileSync(
      resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
      'utf8',
    ),
    vm,
  )
  vi.stubGlobal('PitchlogDomain', Reflect.get(vm, 'PitchlogDomain'))
})
afterEach(() => vi.unstubAllGlobals())
it.each(rows)(
  '$caseId: 実一回artifactと選択digest/V7/V8全値が正規vectorに一致',
  async (row) => {
    const p = structuredClone(row.V7),
      q = p.calculation.request
    const response: PlaySuccess = {
      ok: true,
      value: invokeFirstBallDomain(
        'derivePlayPrefixWithContinuation',
        q,
      ) as PlaySuccess['value'],
    }
    expect(response).toEqual(p.calculation.response)
    const sealed = await sealPlayMetadata(q, response)
    expect(sealed).toEqual({ request: q, response: p.calculation.response })
    expect(
      await formatTerminalPitchWire(
        sealed.request,
        sealed.response,
        p.observations,
        p.participants,
      ),
    ).toEqual({ payload: p, stateDiff: row.V8 })
  },
)
it('全wire-head field改変とprior digest改変をseal不一致として拒否する', async () => {
  const p = structuredClone(rows[0]!.V7),
    q = p.calculation.request,
    r = p.calculation.response
  const head = playWireHead(q, r),
    expected = await playHash(head)
  for (const key of Object.keys(head)) {
    const changed = { ...head, [key]: null }
    expect(await playHash(changed), key).not.toBe(expected)
  }
  for (const mutate of [
    (v: Mutable<PlayPrefixV7>) => {
      v.calculation.request.prefixRef.checkpoint.digest = 'f'.repeat(64)
    },
    (v: Mutable<PlayPrefixV7>) => {
      v.calculation.request.nextCheckpoint.digest = 'f'.repeat(64)
    },
    (v: Mutable<PlayPrefixV7>) => {
      v.calculation.response.value.nextPrefixRef.checkpoint.digest = 'f'.repeat(
        64,
      )
    },
    (v: Mutable<PlayPrefixV7>) => {
      v.calculation.response.value.t1.after.scoreboard.walks = '999'
    },
  ]) {
    const v = structuredClone(p) as Mutable<PlayPrefixV7>
    mutate(v)
    await expect(
      formatTerminalPitchWire(
        v.calculation.request,
        v.calculation.response,
        v.observations,
        v.participants,
      ),
    ).rejects.toThrow()
  }
})
type Mutable<T> = {
  -readonly [K in keyof T]: T[K] extends object ? Mutable<T[K]> : T[K]
}
it('観測の末尾junk/余剰field/非正準hash値を拒否する', async () => {
  const p = structuredClone(rows[0]!.V7)
  for (const course of [
    { unit: '1/263' as const, x: '1x', y: '1' },
    { unit: '1/263' as const, x: '1\n', y: '1' },
  ])
    await expect(
      formatTerminalPitchWire(
        p.calculation.request,
        p.calculation.response,
        { ...p.observations, course },
        p.participants,
      ),
    ).rejects.toThrow()
  for (const v of [
    NaN,
    -0,
    undefined,
    new Date(),
    {
      get x() {
        return 'x'
      },
    },
  ])
    expect(() => canonicalPlayJson(v)).toThrow()
})

it('既観測小数球速139.5を保持し、余剰constructor/sourcePosition変異を閉拒否する', async () => {
  const p = structuredClone(rows[0]!.V7)
  const speed = {
    ...p.observations,
    pitchSpeed: { kmh: '139.5', outsideRangeConfirmed: false },
  }
  expect(
    (
      await formatTerminalPitchWire(
        p.calculation.request,
        p.calculation.response,
        speed,
        p.participants,
      )
    ).payload.observations.pitchSpeed.kmh,
  ).toBe('139.5')
  const extra = structuredClone(p)
  Object.defineProperty(extra.calculation.request.source, 'constructor', {
    value: 'unknown',
    enumerable: true,
  })
  await expect(
    formatTerminalPitchWire(
      extra.calculation.request,
      extra.calculation.response,
      extra.observations,
      extra.participants,
    ),
  ).rejects.toThrow()
  const position = structuredClone(p) as Mutable<PlayPrefixV7>
  position.calculation.response.value.sourcePosition.d1 = '999'
  await expect(
    formatTerminalPitchWire(
      position.calculation.request,
      position.calculation.response,
      position.observations,
      position.participants,
    ),
  ).rejects.toThrow()
})
