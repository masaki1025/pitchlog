import { describe, expect, it } from 'vitest'
import ackEnvelopeSource from './ackEnvelope.ts?raw'
import { readCanonAckStateResults } from './canonOracle'
import { parseD1AckEnvelope } from './ackEnvelope'

describe('ackEnvelope', () => {
  it('R-ACK-STATE の全結果をイベント単位で受け取る', () => {
    const canonResults = readCanonAckStateResults()
    const advancedD3 = {}
    const parsed = parseD1AckEnvelope({
      advancedD3,
      eventResults: canonResults.map((result, index) => ({
        d4: {},
        d1: index,
        d5: {},
        a5Result: result.id,
      })),
    })

    expect(canonResults).toHaveLength(5)
    expect(parsed.advancedD3).toBe(advancedD3)
    expect(
      parsed.eventResults.map((eventResult) => eventResult.a5Result),
    ).toEqual(canonResults)
  })

  it('前進後の D3 が無い ACK を fail-closed に拒否する', () => {
    expect(() => parseD1AckEnvelope({ eventResults: [] })).toThrowError(/D3/)
  })

  it.each([
    ['ACK 封筒', { advancedD3: {}, eventResults: [], extra: {} }],
    [
      'イベント結果',
      {
        advancedD3: {},
        eventResults: [
          {
            d4: {},
            d1: {},
            d5: {},
            a5Result: readCanonAckStateResults()[0]!.id,
            extra: {},
          },
        ],
      },
    ],
    [
      'A4 写像',
      {
        advancedD3: {},
        eventResults: [],
        playerIdMappings: [{ temporaryId: {}, officialId: {}, extra: {} }],
      },
    ],
  ])('%s の余分なキーを拒否する', (_name, candidate) => {
    expect(() => parseD1AckEnvelope(candidate)).toThrow()
  })

  it.each(['advancedD3', 'eventResults'] as const)(
    '%s が undefined の ACK を拒否する',
    (key) => {
      expect(() =>
        parseD1AckEnvelope({
          advancedD3: {},
          eventResults: [],
          [key]: undefined,
        }),
      ).toThrow()
    },
  )

  it.each(['d4', 'd1', 'd5', 'a5Result'] as const)(
    '%s が undefined のイベント結果を拒否する',
    (key) => {
      expect(() =>
        parseD1AckEnvelope({
          advancedD3: {},
          eventResults: [
            {
              d4: {},
              d1: {},
              d5: {},
              a5Result: readCanonAckStateResults()[0]!.id,
              [key]: undefined,
            },
          ],
        }),
      ).toThrow()
    },
  )

  it.each(['temporaryId', 'officialId'] as const)(
    '%s が undefined の A4 写像を拒否する',
    (key) => {
      expect(() =>
        parseD1AckEnvelope({
          advancedD3: {},
          eventResults: [],
          playerIdMappings: [
            { temporaryId: {}, officialId: {}, [key]: undefined },
          ],
        }),
      ).toThrow()
    },
  )

  it('未知の A5 結果を fail-closed に拒否する', () => {
    expect(() =>
      parseD1AckEnvelope({
        advancedD3: {},
        eventResults: [{ d4: {}, d1: {}, d5: {}, a5Result: '未知の結果' }],
      }),
    ).toThrowError(/未知の A5/)
  })

  it('同じ D4・D1・D5 のイベント結果が重複した ACK を拒否する', () => {
    const resultId = readCanonAckStateResults()[0]!.id
    const d4 = {}
    const d1 = {}
    const d5 = {}
    const eventResult = { d4, d1, d5, a5Result: resultId }

    expect(() =>
      parseD1AckEnvelope({
        advancedD3: {},
        eventResults: [eventResult, { ...eventResult }],
      }),
    ).toThrowError(/重複/)
  })

  it.each(['d4', 'd1', 'd5'] as const)(
    '%s が異なるイベント結果を重複と扱わない',
    (differentPart) => {
      const resultId = readCanonAckStateResults()[0]!.id
      const first = { d4: {}, d1: {}, d5: {}, a5Result: resultId }
      const second = { ...first, [differentPart]: {} }

      expect(
        parseD1AckEnvelope({
          advancedD3: {},
          eventResults: [first, second],
        }).eventResults,
      ).toHaveLength(2)
    },
  )

  it('イベント結果が 0 件でも D3 を持つ ACK として受け取る', () => {
    const parsed = parseD1AckEnvelope({
      advancedD3: {},
      eventResults: [],
    })

    expect(parsed.eventResults).toEqual([])
    expect(Object.isFrozen(parsed.eventResults)).toBe(true)
  })

  it('A4 写像を条件付き要素として受け取り、不在時は補わない', () => {
    const withoutMapping = parseD1AckEnvelope({
      advancedD3: {},
      eventResults: [],
    })
    const temporaryId = {}
    const officialId = {}
    const withMapping = parseD1AckEnvelope({
      advancedD3: {},
      eventResults: [],
      playerIdMappings: [{ temporaryId, officialId }],
    })

    expect(Object.hasOwn(withoutMapping, 'playerIdMappings')).toBe(false)
    expect(withMapping.playerIdMappings).toEqual([{ temporaryId, officialId }])
    expect(Object.isFrozen(withMapping.playerIdMappings)).toBe(true)
  })

  it('同じ一時 ID の A4 写像を重複として拒否する', () => {
    const temporaryId = {}

    expect(() =>
      parseD1AckEnvelope({
        advancedD3: {},
        eventResults: [],
        playerIdMappings: [
          { temporaryId, officialId: {} },
          { temporaryId, officialId: {} },
        ],
      }),
    ).toThrowError(/重複/)
  })

  it('A4 写像の値の形式を検査せず、不透明値として保持する', () => {
    const temporaryId = new Proxy(
      {},
      {
        get() {
          throw new Error('一時 ID の内部を読みました')
        },
        ownKeys() {
          throw new Error('一時 ID の内部キーを読みました')
        },
      },
    )
    const officialId = Symbol('official')

    const parsed = parseD1AckEnvelope({
      advancedD3: '',
      eventResults: [],
      playerIdMappings: [{ temporaryId, officialId }],
    })

    expect(parsed.playerIdMappings?.[0]?.temporaryId).toBe(temporaryId)
    expect(parsed.playerIdMappings?.[0]?.officialId).toBe(officialId)
  })

  it('識別値の長さ・文字種・物理型を検査するコードを持たない', () => {
    const formatInspectionPatterns = [
      /\.length\b/,
      /\.match\s*\(/,
      /\.test\s*\(/,
      /\bRegExp\b/,
      /charCodeAt/,
      /codePointAt/,
      /\.startsWith\s*\(/,
      /\.endsWith\s*\(/,
      /UUID/i,
    ]

    for (const pattern of formatInspectionPatterns) {
      expect(ackEnvelopeSource).not.toMatch(pattern)
    }
  })
})
