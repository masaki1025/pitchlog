import { describe, expect, it } from 'vitest'
import { assertExactDefinedObject, assertInputArray } from './receptionInput'

const OBJECT_ERROR = '入力オブジェクトが完全ではありません'
const ARRAY_ERROR = '入力配列ではありません'
const DUPLICATE_ERROR = '入力配列に重複があります'
const ALLOWED_KEYS = ['required', 'optional'] as const
const REQUIRED_KEYS = ['required'] as const

describe('assertExactDefinedObject', () => {
  it('許可キーに過不足がなく必須値が定義済みなら通す', () => {
    expect(() =>
      assertExactDefinedObject(
        { required: {}, optional: null },
        ALLOWED_KEYS,
        REQUIRED_KEYS,
        OBJECT_ERROR,
      ),
    ).not.toThrow()
  })

  it.each([
    ['未知の文字列キー', { required: {}, unknown: {} }],
    ['余分な Symbol キー', { required: {}, [Symbol('余分なキー')]: {} }],
  ])('%s を拒否する', (_name, candidate) => {
    expect(() =>
      assertExactDefinedObject(
        candidate,
        ALLOWED_KEYS,
        REQUIRED_KEYS,
        OBJECT_ERROR,
      ),
    ).toThrowError(OBJECT_ERROR)
  })

  it('必須キーが欠けた入力を拒否する', () => {
    expect(() =>
      assertExactDefinedObject(
        { optional: {} },
        ALLOWED_KEYS,
        REQUIRED_KEYS,
        OBJECT_ERROR,
      ),
    ).toThrowError(OBJECT_ERROR)
  })

  it('必須キーが存在しても値が undefined なら拒否する', () => {
    expect(() =>
      assertExactDefinedObject(
        { required: undefined },
        ALLOWED_KEYS,
        REQUIRED_KEYS,
        OBJECT_ERROR,
      ),
    ).toThrowError(OBJECT_ERROR)
  })
})

describe('assertInputArray', () => {
  it('重複のない配列を通す', () => {
    expect(() =>
      assertInputArray(
        ['first', 'second'],
        ARRAY_ERROR,
        (first, second) => Object.is(first, second),
        DUPLICATE_ERROR,
      ),
    ).not.toThrow()
  })

  it('重複した配列を日本語のエラーメッセージで拒否する', () => {
    expect(() =>
      assertInputArray(
        ['same', 'same'],
        ARRAY_ERROR,
        (first, second) => Object.is(first, second),
        DUPLICATE_ERROR,
      ),
    ).toThrowError(DUPLICATE_ERROR)
  })

  it('NaN 同士を Object.is と同じ識別値として拒否する', () => {
    expect(() =>
      assertInputArray(
        [Number.NaN, Number.NaN],
        ARRAY_ERROR,
        (first, second) => Object.is(first, second),
        DUPLICATE_ERROR,
      ),
    ).toThrowError(DUPLICATE_ERROR)
  })

  it('+0 と -0 を Object.is と同じ別の識別値として通す', () => {
    expect(() =>
      assertInputArray(
        [0, -0],
        ARRAY_ERROR,
        (first, second) => Object.is(first, second),
        DUPLICATE_ERROR,
      ),
    ).not.toThrow()
  })

  it('配列でない入力を日本語のエラーメッセージで拒否する', () => {
    expect(() => assertInputArray({}, ARRAY_ERROR)).toThrowError(ARRAY_ERROR)
  })
})
