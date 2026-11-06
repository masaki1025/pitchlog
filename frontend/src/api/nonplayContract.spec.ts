import { expect, it } from 'vitest'
import lifecycleCases from '../../../contracts/state-transition/game_lifecycle_cases_v1.json'
import { isNonplayDefinition } from './nonplayContract'
import { undoSample } from '../screens/GameScreenUndoProduct.test-support'
it('終了/再開bridgeのkernelを登録済みの正本schemaで閉検証する', () => {
  for (const sample of lifecycleCases.cases) {
    expect(
      isNonplayDefinition(
        sample.request,
        'Request',
        'game_lifecycle_schema_v1',
      ),
    ).toBe(true)
    expect(
      isNonplayDefinition(
        { ...sample.request, unknown: true },
        'Request',
        'game_lifecycle_schema_v1',
      ),
    ).toBe(false)
  }
})
it('既手導出全4 Source/要求/応答/payloadを外部取得なしで閉検証する', () => {
  for (const i of [2, 3, 4, 5]) {
    const s = undoSample(i),
      q = s.payload.calculation.request
    expect(isNonplayDefinition(q.source, 'Source')).toBe(true)
    expect(
      isNonplayDefinition(q, 'NonplayRequest', 'lineup_play_prefix_schema_v1'),
    ).toBe(true)
    expect(
      isNonplayDefinition(
        s.payload.calculation.response,
        'NonplaySuccess',
        'lineup_play_prefix_schema_v1',
      ),
    ).toBe(true)
    expect(
      isNonplayDefinition(
        s.payload,
        '$root',
        'lineup_play_prefix_payload_schema_v1',
      ),
    ).toBe(true)
  }
})
it.each([
  'unknown',
  'extra',
  'null',
  'type',
  'decimal',
  'nonfinite',
  'newline',
])('型/未知/余剰を補完しない: %s', (fault) => {
  const s: Record<string, unknown> = structuredClone(
    undoSample(2).payload.calculation.request.source,
  ) as unknown as Record<string, unknown>
  if (fault === 'unknown') s.formatVersion = 'unknown'
  else if (fault === 'extra') s.extra = true
  else if (fault === 'null') s.checkpoint = null
  else if (fault === 'type') s.activeStack = {}
  else if (fault === 'nonfinite') s.extra = Infinity
  else {
    const cp = s.checkpoint as { content: { d3: unknown } }
    cp.content.d3 = fault === 'decimal' ? 2 : '2\n'
  }
  expect(isNonplayDefinition(s, 'Source')).toBe(false)
})
it('未登録schema/定義を成功へfallbackしない', () => {
  expect(isNonplayDefinition({}, 'Unknown')).toBe(false)
})
