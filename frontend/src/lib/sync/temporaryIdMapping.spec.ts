import { describe, expect, it, vi } from 'vitest'
import temporaryIdMappingSource from './temporaryIdMapping.ts?raw'
import * as temporaryIdMappingModule from './temporaryIdMapping'
import {
  assertD5IsNotTemporary,
  TemporaryIdMapping,
  type TemporaryIdProvenance,
} from './temporaryIdMapping'

describe('temporaryIdMapping', () => {
  it('C2: 同じ一時 ID を決定的に同じ正式 ID へ解決する', () => {
    const mapping = new TemporaryIdMapping<unknown, unknown>()
    const temporaryId = { provenance: 'temporary' }
    const officialId = { provenance: 'official' }

    mapping.append(temporaryId, officialId)
    mapping.append(temporaryId, officialId)

    expect(mapping.resolve(temporaryId)).toBe(officialId)
    expect(mapping.resolve(temporaryId)).toBe(officialId)
    expect(mapping.records).toEqual([{ temporaryId, officialId }])
    expect(mapping.records).toHaveLength(1)
  })

  it('C3: 同じ一時 ID の別の正式 ID への再写像を拒否する', () => {
    const mapping = new TemporaryIdMapping<unknown, unknown>()
    const temporaryId = {}
    const firstOfficialId = { id: 'first' }
    mapping.append(temporaryId, firstOfficialId)
    const firstRecords = mapping.records

    expect(() => mapping.append(temporaryId, { id: 'different' })).toThrowError(
      /C3/,
    )
    expect(mapping.records).toEqual(firstRecords)
    expect(mapping.resolve(temporaryId)).toBe(firstOfficialId)
  })

  it('一時 ID と正式 ID の置換記録を追記順に保持する', () => {
    const mapping = new TemporaryIdMapping<string, string>()

    mapping.append('temporary-1', 'official-1')
    mapping.append('temporary-2', 'official-2')

    expect(mapping.records).toEqual([
      { temporaryId: 'temporary-1', officialId: 'official-1' },
      { temporaryId: 'temporary-2', officialId: 'official-2' },
    ])
    expect(Object.isFrozen(mapping.records)).toBe(true)
    expect(mapping.records.every((record) => Object.isFrozen(record))).toBe(
      true,
    )
  })

  it('未登録の一時 ID を解決せず fail-closed に拒否する', () => {
    const mapping = new TemporaryIdMapping<unknown, unknown>()

    expect(() => mapping.resolve({})).toThrowError(/C2/)
  })

  it('上書き・削除 API を export せず、公開インスタンス API にも持たない', () => {
    expect(Object.keys(temporaryIdMappingModule).sort()).toEqual([
      'TEMPORARY_ID_MAPPING_RULES',
      'TemporaryIdMapping',
      'assertD5IsNotTemporary',
    ])
    expect(
      Object.getOwnPropertyNames(TemporaryIdMapping.prototype).sort(),
    ).toEqual(['append', 'constructor', 'records', 'resolve'])
  })

  it('provenance が一時 ID と判定した値を D5 として拒否する', () => {
    const temporaryId = { provenance: 'temporary' }
    const fields = { V1: temporaryId }
    const isTemporaryId = vi.fn<TemporaryIdProvenance>(
      (value) => value === temporaryId,
    )

    expect(() => assertD5IsNotTemporary(fields.V1, isTemporaryId)).toThrowError(
      /temporary ID/,
    )
    expect(isTemporaryId).toHaveBeenCalledWith(temporaryId)
    expect(() => assertD5IsNotTemporary({}, isTemporaryId)).not.toThrow()
  })

  it('provenance 判定器の未注入を fail-closed に拒否する', () => {
    const callWithoutProvenance = (): void => {
      // @ts-expect-error provenance 判定器の注入を型でも必須にする。
      assertD5IsNotTemporary({})
    }

    expect(callWithoutProvenance).toThrowError(/provenance/)
    expect(() => assertD5IsNotTemporary({}, undefined)).toThrowError(
      /provenance/,
    )
  })

  it('provenance 判定器の例外を fail-closed に拒否する', () => {
    const isTemporaryId: TemporaryIdProvenance = () => {
      throw new Error('provenance failure')
    }

    expect(() => assertD5IsNotTemporary({}, isTemporaryId)).toThrowError(
      /provenance/,
    )
  })

  it('値の形式を検査するコードを持たない', () => {
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
      expect(temporaryIdMappingSource).not.toMatch(pattern)
    }
  })

  it('C1・C4 の状態や prefix コミットを持たない', () => {
    const sourceWithoutCanonText = temporaryIdMappingSource.replace(
      /rightHandSide:\s*'[^']*'/g,
      '',
    )

    expect(sourceWithoutCanonText).not.toMatch(/ACK|同期済み|prefix/i)
  })
})
