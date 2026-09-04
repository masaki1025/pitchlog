import { describe, expect, it } from 'vitest'
import {
  buildSyncEventKindSet,
  EVENT_KIND_GROUP,
  EVENT_KIND_RULES,
  EVENT_PARTICIPATION,
} from './eventKinds'

describe('eventKinds', () => {
  it('ID が一意で参加区分が4種に閉じている', () => {
    const ids = EVENT_KIND_RULES.map((eventKind) => eventKind.id)
    const participations = EVENT_KIND_RULES.map(
      (eventKind) => eventKind.participation,
    )

    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(participations)).toEqual(
      new Set(Object.values(EVENT_PARTICIPATION)),
    )
  })

  it('群 A と群 B の境界および変更版順属性を固定する', () => {
    expect(
      EVENT_KIND_RULES.filter(
        (eventKind) => eventKind.group === EVENT_KIND_GROUP.A,
      ).map((eventKind) => eventKind.id),
    ).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9'])
    expect(
      EVENT_KIND_RULES.filter(
        (eventKind) => eventKind.group === EVENT_KIND_GROUP.B,
      ).map((eventKind) => eventKind.id),
    ).toEqual(['10', '11', '12'])
    expect(
      EVENT_KIND_RULES.filter((eventKind) => eventKind.hasRevisionOrder).map(
        (eventKind) => eventKind.id,
      ),
    ).toEqual(['10', '11', '12'])
  })

  it('FR-040 が不採用なら状態補正だけを集合から除く', () => {
    const adopted = buildSyncEventKindSet({ stateCorrectionAdopted: true })
    const notAdopted = buildSyncEventKindSet({ stateCorrectionAdopted: false })
    const expected = adopted.filter((eventKind) => eventKind.id !== '7')

    expect(adopted).toEqual(EVENT_KIND_RULES)
    expect(notAdopted).toEqual(expected)
    expect(notAdopted).toHaveLength(adopted.length - 1)
    for (const eventKind of notAdopted) {
      expect(adopted.find((candidate) => candidate.id === eventKind.id)).toBe(
        eventKind,
      )
    }
  })

  it('FR-040 の採用状態を省略できない', () => {
    const callWithoutOptions = (): void => {
      // @ts-expect-error 採用状態に既定値を与えず、呼び出し側の明示を必須にする。
      buildSyncEventKindSet()
    }

    expect(callWithoutOptions).toBeTypeOf('function')
  })
})
