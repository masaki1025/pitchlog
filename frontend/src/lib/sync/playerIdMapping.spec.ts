import { describe, expect, it } from 'vitest'
import playerIdMappingSource from './playerIdMapping.ts?raw'
import { CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE } from './canonOracle'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import {
  checkMappingConfirmation,
  MAPPING_CONFIRMATION_STATUS,
} from './mappingConfirmationGate'
import {
  receivePlayerIdMapping,
  type PlayerIdMappingReceptionRequest,
} from './playerIdMapping'
import { TemporaryIdMapping } from './temporaryIdMapping'

function playerRegistrationEventKind(): EventKind {
  const eventKind = EVENT_KIND_RULES.find(
    (candidate) => candidate.name === '選手のその場登録',
  )
  if (!eventKind) {
    throw new Error('選手登録イベント種別がありません')
  }
  return eventKind
}

const PLAYER_REGISTRATION_EVENT_KIND = playerRegistrationEventKind()
const OTHER_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.id !== PLAYER_REGISTRATION_EVENT_KIND?.id,
)
if (!OTHER_EVENT_KIND) {
  throw new Error('A4 受け取り検査用のイベント種別がありません')
}

function receptionRequest(
  eventKind: EventKind = PLAYER_REGISTRATION_EVENT_KIND,
): PlayerIdMappingReceptionRequest {
  const key = { d4: {}, d1: {}, d5: {} }
  const temporaryId = {}
  return {
    target: { eventKind, event: {}, key, temporaryId },
    response: {
      key,
      mappings: [{ temporaryId, officialId: {} }],
    },
  }
}

describe('playerIdMapping', () => {
  it('当該選手登録イベントの写像を既存の写像表と C4 ゲートへ供給する', () => {
    const request = receptionRequest()
    const reception = receivePlayerIdMapping(request)
    const confirmedMapping = reception.confirmedMapping
    if (!confirmedMapping) {
      throw new Error('確定済み写像がありません')
    }

    const mapping = new TemporaryIdMapping<unknown, unknown>()
    mapping.append(
      confirmedMapping.mapping.temporaryId,
      confirmedMapping.mapping.officialId,
    )
    const gateResult = checkMappingConfirmation(
      {
        eventKind: request.target.eventKind,
        event: request.target.event,
      },
      reception.mappingConfirmation,
    )

    expect(confirmedMapping.key).toBe(request.target.key)
    expect(mapping.resolve(request.target.temporaryId)).toBe(
      confirmedMapping.mapping.officialId,
    )
    expect(gateResult).toEqual({
      status: MAPPING_CONFIRMATION_STATUS.CONFIRMED,
      allowsSyncedTransition: true,
    })
  })

  it.each(['d4', 'd1', 'd5'] as const)(
    '%s が異なる別イベントの写像を拒否する',
    (keyPart) => {
      const request = receptionRequest()
      const response = request.response!

      expect(() =>
        receivePlayerIdMapping({
          ...request,
          response: {
            ...response,
            key: { ...response.key, [keyPart]: {} },
          },
        }),
      ).toThrowError(/別の選手登録イベント/)
    },
  )

  it('写像結果の欠落を fail-closed に拒否する', () => {
    const request = receptionRequest()

    expect(() =>
      receivePlayerIdMapping({
        ...request,
        response: { key: request.target.key, mappings: [] },
      }),
    ).toThrowError(/欠落/)
  })

  it('選手登録イベントで A4 応答自体が無ければ fail-closed に拒否する', () => {
    const request = receptionRequest()

    expect(() =>
      receivePlayerIdMapping({ target: request.target }),
    ).toThrowError(/A4 写像がありません/)
  })

  it('写像結果の重複を fail-closed に拒否する', () => {
    const request = receptionRequest()
    const response = request.response!
    const mapping = response.mappings[0]!

    expect(() =>
      receivePlayerIdMapping({
        ...request,
        response: { ...response, mappings: [mapping, mapping] },
      }),
    ).toThrowError(/重複/)
  })

  it.each(['temporaryId', 'officialId'] as const)(
    '写像の %s が undefined なら fail-closed に拒否する',
    (key) => {
      const request = receptionRequest()
      const response = request.response!

      expect(() =>
        receivePlayerIdMapping({
          ...request,
          response: {
            ...response,
            mappings: [{ ...response.mappings[0]!, [key]: undefined }],
          },
        }),
      ).toThrow()
    },
  )

  it('対象の一時 ID が undefined なら fail-closed に拒否する', () => {
    const request = receptionRequest()

    expect(() =>
      receivePlayerIdMapping({
        ...request,
        target: { ...request.target, temporaryId: undefined },
      }),
    ).toThrowError(/一時 ID/)
  })

  it.each([
    (request: PlayerIdMappingReceptionRequest) => ({ ...request, extra: {} }),
    (request: PlayerIdMappingReceptionRequest) => ({
      ...request,
      target: { ...request.target, extra: {} },
    }),
    (request: PlayerIdMappingReceptionRequest) => ({
      ...request,
      target: { ...request.target, key: { ...request.target.key, extra: {} } },
    }),
    (request: PlayerIdMappingReceptionRequest) => ({
      ...request,
      response: { ...request.response!, extra: {} },
    }),
    (request: PlayerIdMappingReceptionRequest) => ({
      ...request,
      response: {
        ...request.response!,
        mappings: [{ ...request.response!.mappings[0]!, extra: {} }],
      },
    }),
  ])('余分なキーを持つ A4 受け取り入力を拒否する', (mutate) => {
    expect(() =>
      receivePlayerIdMapping(
        mutate(receptionRequest()) as PlayerIdMappingReceptionRequest,
      ),
    ).toThrow()
  })

  it('余分な写像結果を fail-closed に拒否する', () => {
    const request = receptionRequest()
    const response = request.response!

    expect(() =>
      receivePlayerIdMapping({
        ...request,
        response: {
          ...response,
          mappings: [...response.mappings, { temporaryId: {}, officialId: {} }],
        },
      }),
    ).toThrowError(/余分/)
  })

  it('選手登録イベント以外は写像なしで C4 ゲートを素通しする', () => {
    const request = receptionRequest(OTHER_EVENT_KIND)
    const reception = receivePlayerIdMapping({
      target: {
        eventKind: request.target.eventKind,
        event: request.target.event,
        key: request.target.key,
      },
    })

    expect(reception.confirmedMapping).toBeUndefined()
    expect(
      checkMappingConfirmation(
        {
          eventKind: request.target.eventKind,
          event: request.target.event,
        },
        reception.mappingConfirmation,
      ),
    ).toEqual({
      status: MAPPING_CONFIRMATION_STATUS.NOT_REQUIRED,
      allowsSyncedTransition: true,
    })
  })

  it('検証済み resolver を別のイベントへ流用しても確定扱いしない', () => {
    const request = receptionRequest()
    const reception = receivePlayerIdMapping(request)

    expect(
      checkMappingConfirmation(
        { eventKind: request.target.eventKind, event: {} },
        reception.mappingConfirmation,
      ),
    ).toEqual({
      status: MAPPING_CONFIRMATION_STATUS.UNCONFIRMED,
      allowsSyncedTransition: false,
    })
  })

  it('写像値を不透明値として保持し、値の形式を検査しない', () => {
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
    const key = { d4: Symbol(), d1: null, d5: false }
    const event = {}
    const reception = receivePlayerIdMapping({
      target: {
        eventKind: PLAYER_REGISTRATION_EVENT_KIND,
        event,
        key,
        temporaryId,
      },
      response: {
        key,
        mappings: [{ temporaryId, officialId }],
      },
    })

    expect(reception.confirmedMapping?.mapping.temporaryId).toBe(temporaryId)
    expect(reception.confirmedMapping?.mapping.officialId).toBe(officialId)
  })

  it('値の長さ・文字種・物理型を検査するコードを持たない', () => {
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
      /typeof\s+[^\n]*(?:temporaryId|officialId|\.d[145])/,
    ]

    for (const pattern of formatInspectionPatterns) {
      expect(playerIdMappingSource).not.toMatch(pattern)
    }
  })

  it('イベント種別 ID を再定義せず eventKinds の既存定義だけを使う', () => {
    const exactEventKindIdLiterals = [
      ...playerIdMappingSource.matchAll(/(['"])(?:[1-9]|1[0-2])\1/g),
    ]

    expect(exactEventKindIdLiterals).toEqual([])
  })

  it('写像表を再実装せず既存の写像レコード型だけを受け渡す', () => {
    expect(playerIdMappingSource).not.toMatch(/\bclass\s+TemporaryIdMapping\b/)
    expect(playerIdMappingSource).not.toMatch(
      /\bnew\s+(?:Map|TemporaryIdMapping)\b/,
    )
    expect(playerIdMappingSource).toContain(
      "import type { TemporaryIdMappingRecord } from './temporaryIdMapping'",
    )
  })

  it('R-TEMP-ID-MAPPING の C1 を理由つきの射程外 allow-list に残す', () => {
    expect(CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE).toEqual([
      expect.objectContaining({ id: 'C1', reason: expect.any(String) }),
    ])
  })
})
