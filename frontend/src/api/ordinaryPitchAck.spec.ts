import { createAckAdapterInjections } from '../lib/sync/ackAdapter'
import { expect, it } from 'vitest'
import { readOrdinaryPitchAck } from './ordinaryPitchAck'
import { readFirstBallAck } from './firstBallWire'
const key = {
  d4: 'opaque-D4',
  d1: 2,
  d5: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
}
const ack = (advancedD3: unknown = 3) => ({
  advancedD3,
  eventResults: [{ d4: key.d4, d1: key.d1, d5: key.d5, a5Result: '受理' }],
})
it('後続水位3で対象D1=2だけを再掲する正規ACKを読む', () => {
  const value = ack()
  const result = readOrdinaryPitchAck(value, key)
  expect(result?.envelope).toBe(value)
  expect(readOrdinaryPitchAck(ack(2), key)).toBeDefined()
  expect(readFirstBallAck(value, key)).toBeUndefined()
})
it('水位不足/非整数/別D4/D1/D5/未受理/余剰ACKを成功へ補完しない', () => {
  for (const watermark of [1, -1, 1.5, '3', NaN, Infinity])
    expect(readOrdinaryPitchAck(ack(watermark), key)).toBeUndefined()
  for (const change of [
    { d4: 'other' },
    { d1: 3 },
    { d5: '22222222-2222-4222-8222-222222222222' },
    { a5Result: '拒否' },
  ]) {
    const value = ack()
    Object.assign(value.eventResults[0]!, change)
    expect(readOrdinaryPitchAck(value, key)).toBeUndefined()
  }
  const extra = ack()
  extra.eventResults.push({ ...extra.eventResults[0]!, d1: 3 })
  expect(readOrdinaryPitchAck(extra, key)).toBeUndefined()
  expect(readOrdinaryPitchAck({ ...ack(), unknown: true }, key)).toBeUndefined()
})
it('対象キーを正規化せず、他slotの成功結果やafterを書き足さない', () => {
  expect(
    readOrdinaryPitchAck(ack(), { ...key, d5: key.d5.toUpperCase() }),
  ).toBeUndefined()
  expect(readOrdinaryPitchAck(ack(), { ...key, d1: 1.5 })).toBeUndefined()
  const result = readOrdinaryPitchAck(ack(), key)!
  expect(Object.keys(result).sort()).toEqual(['boundaryResult', 'envelope'])
  expect(result).not.toHaveProperty('after')
  expect((result.envelope as ReturnType<typeof ack>).eventResults).toHaveLength(
    1,
  )
})

it('正規重複を元envelope/idのまま既adapterへ渡し、受理へ書き換えない', () => {
  const value = ack(3)
  value.eventResults[0]!.a5Result = '重複'
  const result = readOrdinaryPitchAck(value, key)!
  expect(result.envelope).toBe(value)
  expect(value.eventResults[0]!.a5Result).toBe('重複')
  const adapter = createAckAdapterInjections({ d1: result })
  expect(adapter.resolveA5?.(key)?.result.id).toBe('重複')
  expect(adapter.resolveA5?.({ ...key, d1: 3 })).toBeUndefined()
  expect(
    adapter.resolveA5?.({ ...key, d5: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' }),
  ).toBeUndefined()
  expect(readFirstBallAck(value, key)).toBeUndefined()
})
it('重複も同slot/正水位/閉shapeを要求し、拒否・退避・未処理を成功化しない', () => {
  for (const state of ['拒否', '退避', '未処理']) {
    const value = ack()
    value.eventResults[0]!.a5Result = state
    expect(readOrdinaryPitchAck(value, key)).toBeUndefined()
  }
  for (const watermark of [1, '3', NaN, Infinity]) {
    const value = ack(watermark)
    value.eventResults[0]!.a5Result = '重複'
    expect(readOrdinaryPitchAck(value, key)).toBeUndefined()
  }
  for (const changed of [
    { d4: 'other' },
    { d1: 3 },
    { d5: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' },
  ]) {
    const value = ack()
    Object.assign(value.eventResults[0]!, changed, { a5Result: '重複' })
    expect(readOrdinaryPitchAck(value, key)).toBeUndefined()
  }
  const value = ack()
  value.eventResults[0]!.a5Result = '重複'
  expect(readOrdinaryPitchAck({ ...value, extra: true }, key)).toBeUndefined()
  expect(
    readOrdinaryPitchAck(
      {
        ...value,
        eventResults: [...value.eventResults, ...value.eventResults],
      },
      key,
    ),
  ).toBeUndefined()
})
