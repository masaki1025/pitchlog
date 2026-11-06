import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary_pitch_vectors_v1.json',
    ),
    'utf8',
  ),
) as {
  cases: Array<{
    caseId: string
    request: Record<string, unknown>
    expected: { ok: true; value: Record<string, unknown> }
  }>
}

function formal(caseId: string) {
  const item = vectors.cases.find((row) => row.caseId === caseId)
  if (!item) throw new Error(`正式caseがありません: ${caseId}`)
  return item
}

const uuid1 = '11111111-1111-4111-8111-111111111111'
const uuid2 = '22222222-2222-4222-8222-222222222222'

function event(row: ReturnType<typeof formal>) {
  return {
    eventKind: row.request.eventKind,
    resultId: row.request.resultId,
    pitchEventKind: row.request.pitchEventKind,
  }
}

function request() {
  const firstBall = formal('ORDINARY-PITCH-25')
  const secondBall = formal('ORDINARY-PITCH-28')
  const called = formal('ORDINARY-PITCH-01')
  return {
    version: 'past-correction-ordinary-page-v1',
    originalBefore: firstBall.request.before,
    correctedBefore: firstBall.request.before,
    previousD2: '0',
    targetIncluded: true,
    records: [
      {
        sourceEventId: uuid1,
        sourceD2: '1',
        original: event(firstBall),
        storedAfter: firstBall.expected.value.after,
        replacement: event(called),
      },
      {
        sourceEventId: uuid2,
        sourceD2: '2',
        original: event(secondBall),
        storedAfter: secondBall.expected.value.after,
        replacement: null,
      },
    ],
  }
}

function run(input: unknown) {
  return JSON.parse(
    domainOperations.replayPastCorrectionPage(JSON.stringify(input)),
  ) as Record<string, unknown>
}

describe('過去訂正の有限通常T1反復', () => {
  it('元の2球を正式caseで照合し、先頭ball→called後の後続ballを同artifactで再導出する', () => {
    const result = run(request()) as {
      ok: true
      value: {
        originalAfter: unknown
        correctedAfter: unknown
        lastD2: string
        frames: Array<{ original: unknown; corrected: unknown }>
      }
    }
    expect(result.ok).toBe(true)
    expect(result.value.frames).toHaveLength(2)
    expect(result.value.frames[0]!.original).toEqual(
      formal('ORDINARY-PITCH-25').expected.value,
    )
    expect(result.value.frames[1]!.original).toEqual(
      formal('ORDINARY-PITCH-28').expected.value,
    )
    expect(result.value.frames[0]!.corrected).toEqual(
      formal('ORDINARY-PITCH-01').expected.value,
    )
    expect(result.value.frames[1]!.corrected).toEqual(
      formal('ORDINARY-PITCH-26').expected.value,
    )
    expect(result.value.originalAfter).toEqual(
      formal('ORDINARY-PITCH-28').expected.value.after,
    )
    expect(result.value.correctedAfter).toEqual(
      formal('ORDINARY-PITCH-26').expected.value.after,
    )
    expect(result.value.lastD2).toBe('2')
  })

  it('保存済み旧afterの改竄を旧系列の自己承認に使わない', () => {
    const candidate = request()
    candidate.records[0]!.storedAfter = formal(
      'ORDINARY-PITCH-01',
    ).expected.value.after
    expect(run(candidate)).toEqual({
      ok: false,
      error: { code: 'SOURCE_MISMATCH' },
    })
  })

  it('未成立の後続操作、D2逆順、対象外の後付置換を閉じる', () => {
    const unknown = request()
    unknown.records[1]!.original = {
      eventKind: 'substitution',
      resultId: 'batting-result.ball',
      pitchEventKind: 'pitch-event',
    }
    expect(run(unknown).ok).toBe(false)
    const reversed = request()
    reversed.records[1]!.sourceD2 = '1'
    expect(run(reversed).ok).toBe(false)
    const secondReplacement = request()
    secondReplacement.records[1]!.replacement = event(
      formal('ORDINARY-PITCH-01'),
    )
    expect(run(secondReplacement).ok).toBe(false)
  })

  it('重複JSONキーと対象前状態の差し替えを閉じる', () => {
    expect(
      JSON.parse(
        domainOperations.replayPastCorrectionPage(
          '{"version":"past-correction-ordinary-page-v1","version":"other"}',
        ),
      ),
    ).toEqual({ ok: false, error: { code: 'INVALID_JSON' } })
    const candidate = request()
    candidate.correctedBefore = formal('ORDINARY-PITCH-01').expected.value.after
    expect(run(candidate).ok).toBe(false)
  })

})
