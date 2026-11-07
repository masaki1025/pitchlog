// @vitest-environment node
import { expect, it } from 'vitest'
import schema from '../../../contracts/state-transition/lineup_play_prefix_schema_v1.json'
import payloadSchema from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import formal from '../../../contracts/state-transition/state_transition_contract_schema_v1.json'
import lineupCases from '../../../contracts/state-transition/lineup_play_prefix_cases_v1.json'
import battedCases from '../../../contracts/state-transition/batted_hit_prefix_cases_v1.json'
import { isClosedPlaySchema } from './terminalPitchWire'

it('走塁の追加後も旧成功53行の要求・全応答を両schemaで受理する', () => {
  const rows = [...lineupCases.cases, ...battedCases.cases].filter(
    (row) => row.expected.ok === true,
  )
  expect(rows).toHaveLength(53)
  for (const document of [schema, payloadSchema])
    for (const row of rows) {
      expect(isClosedPlaySchema(row.request, document, 'Request')).toBe(true)
      expect(isClosedPlaySchema(row.expected, document, 'Success')).toBe(true)
    }
})

it('追加したPerPitchとその参照先は既規範定義と完全一致する', () => {
  const normative = formal.$defs as Record<string, unknown>
  for (const document of [schema, payloadSchema]) {
    const definitions = document.$defs as Record<string, unknown>
    const visited = new Set<string>()
    function visit(name: string): void {
      if (visited.has(name)) return
      visited.add(name)
      expect(definitions[name], name).toEqual(normative[name])
      for (const match of JSON.stringify(normative[name]).matchAll(
        /"\$ref":"#\/\$defs\/([^"]+)"/g,
      ))
        visit(match[1]!)
    }
    visit('T1PerPitchPayloadV2')
    expect(visited.size).toBe(22)
  }
})

it('UUIDの非正準値と未対応formatを閉拒否する', () => {
  const document = {
    $defs: { Item: { type: 'string', format: 'uuid' } },
  }
  expect(
    isClosedPlaySchema(
      'abcdef00-0000-0000-0000-000000000001',
      document,
      'Item',
    ),
  ).toBe(true)
  for (const value of ['ABCDEF00-0000-0000-0000-000000000001', 'bad', null])
    expect(isClosedPlaySchema(value, document, 'Item')).toBe(false)
  expect(
    isClosedPlaySchema(
      'value',
      { $defs: { Item: { format: 'unknown' } } },
      'Item',
    ),
  ).toBe(false)
})

it('uniqueItemsはキー順に依存せず重複objectを拒否し、値を補修しない', () => {
  const document = {
    $defs: { Item: { type: 'array', uniqueItems: true } },
  }
  const duplicate = [
    { a: '1', b: '2' },
    { b: '2', a: '1' },
  ]
  const before = structuredClone(duplicate)
  expect(isClosedPlaySchema(duplicate, document, 'Item')).toBe(false)
  expect(duplicate).toEqual(before)
  expect(
    isClosedPlaySchema(['batter', { runner: '1' }], document, 'Item'),
  ).toBe(true)
  expect(isClosedPlaySchema(['batter', 'batter'], document, 'Item')).toBe(false)
})
