// この写像は docs/design/sync-protocol.md 4-4 の C2・C3 の写しである。
// 値の形式は実装で決めず、一時 ID の provenance は注入された判定だけを使う。
// C1・C4 は7章の契約に依存するため射程外とする。

export const TEMPORARY_ID_MAPPING_RULES = [
  {
    id: 'C2',
    rightHandSide: '後続イベントの参照+同じ正式ID+決定的に解決',
  },
  {
    id: 'C3',
    rightHandSide: 'ACK消失後の再送+別の正式ID+重複生成しない',
  },
] as const

export type TemporaryIdMappingRecord<TemporaryId, OfficialId> = Readonly<{
  temporaryId: TemporaryId
  officialId: OfficialId
}>

export class TemporaryIdMapping<TemporaryId, OfficialId> {
  readonly #records: TemporaryIdMappingRecord<TemporaryId, OfficialId>[] = []

  append(temporaryId: TemporaryId, officialId: OfficialId): void {
    const existing = this.#records.find((record) =>
      Object.is(record.temporaryId, temporaryId),
    )
    if (existing) {
      if (!Object.is(existing.officialId, officialId)) {
        throw new Error('C3')
      }
      return
    }

    const record = Object.freeze({ temporaryId, officialId })
    this.#records.push(record)
  }

  resolve(temporaryId: TemporaryId): OfficialId {
    const record = this.#records.find((candidate) =>
      Object.is(candidate.temporaryId, temporaryId),
    )
    if (!record) {
      throw new Error('C2')
    }
    return record.officialId
  }

  get records(): readonly TemporaryIdMappingRecord<TemporaryId, OfficialId>[] {
    return Object.freeze([...this.#records])
  }
}

export type TemporaryIdProvenance = (value: unknown) => boolean

export function assertD5IsNotTemporary(
  value: unknown,
  isTemporaryId: TemporaryIdProvenance | undefined,
): void {
  if (!isTemporaryId) {
    throw new Error('D5 provenance')
  }

  let isTemporary: boolean
  try {
    isTemporary = isTemporaryId(value)
  } catch {
    throw new Error('D5 provenance')
  }
  if (isTemporary) {
    throw new Error('D5 temporary ID')
  }
}
