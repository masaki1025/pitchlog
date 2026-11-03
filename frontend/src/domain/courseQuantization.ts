/** 最短往復の十進入力を厳密な整数と十進scaleへ読む。 */
type Decimal = { numerator: bigint; scale: bigint }

/** 長大入力を先に打ち切り、後段で文字列やBigIntを増大させない。 */
function bounded(value: string): boolean {
  let count = 0n
  for (const character of value) {
    if (character === '') return false
    count = count + 1n
    if (count > 400n) return false
  }
  return count > 0n
}

/** ASCII十進数字だけを判定する。 */
function digit(value: string): boolean {
  return value >= '0' && value <= '9'
}

/** 指数を二分して、深い再帰や浮動小数の累乗を避ける。 */
function power10(exponent: bigint): bigint {
  if (exponent === 0n) return 1n
  const half = power10(exponent / 2n)
  const square = half * half
  if (exponent % 2n === 0n) return square
  return square * 10n
}

/** 文法・指数防護を検査してから厳密値を構成する。 */
function decimal(value: unknown): Decimal | null {
  if (typeof value !== 'string' || !bounded(value)) return null
  let first = true
  let negative = false
  let phase = 'integer'
  let numerator = 0n
  let fractionDigits = 0n
  let integerDigits = 0n
  let leadingZero = false
  let exponent = 0n
  let exponentNegative = false
  let exponentDigits = 0n
  let dot = false
  let hasExponent = false
  for (const character of value) {
    if (first) {
      first = false
      if (character === '-') {
        negative = true
        continue
      }
    }
    if (phase === 'integer' || phase === 'fraction') {
      if (digit(character)) {
        if (phase === 'integer') {
          if (leadingZero) return null
          if (integerDigits === 0n && character === '0') leadingZero = true
          integerDigits = integerDigits + 1n
        } else fractionDigits = fractionDigits + 1n
        numerator = numerator * 10n + BigInt(character)
        continue
      }
      if (character === '.' && phase === 'integer' && integerDigits > 0n) {
        dot = true
        phase = 'fraction'
        continue
      }
      if ((character === 'e' || character === 'E') && integerDigits > 0n) {
        if (dot && fractionDigits === 0n) return null
        hasExponent = true
        phase = 'exponent-sign'
        continue
      }
      return null
    }
    if (phase === 'exponent-sign') {
      phase = 'exponent'
      if (character === '+' || character === '-') {
        exponentNegative = character === '-'
        continue
      }
    }
    if (!digit(character)) return null
    exponent = exponent * 10n + BigInt(character)
    exponentDigits = exponentDigits + 1n
    if (exponent > 400n) return null
  }
  if (integerDigits === 0n || (dot && fractionDigits === 0n)) return null
  if (hasExponent && exponentDigits === 0n) return null
  if (exponentNegative) exponent = -exponent
  if (negative) numerator = -numerator
  return { numerator: numerator, scale: fractionDigits - exponent }
}

/** sizeは正準な正整数の十進文字列だけを受ける。 */
function sizeValue(value: unknown): bigint | null {
  if (typeof value !== 'string' || !bounded(value)) return null
  let first = true
  let result = 0n
  for (const character of value) {
    if (!digit(character)) return null
    if (first && character === '0') return null
    first = false
    result = result * 10n + BigInt(character)
  }
  return result
}

/** 量子化前の厳密値で表示範囲を判定する。 */
function inRange(value: Decimal, size: bigint): boolean {
  if (value.numerator < 0n) return false
  if (value.scale <= 0n) return value.numerator * power10(-value.scale) <= size
  return value.numerator <= size * power10(value.scale)
}

/** 正負対称のhalf-up。範囲拒否後でも規則は単一で保持する。 */
function halfUp(value: Decimal): bigint {
  if (value.scale <= 0n) return value.numerator * power10(-value.scale)
  const divisor = power10(value.scale)
  let absolute = value.numerator
  if (absolute < 0n) absolute = -absolute
  let rounded = absolute / divisor
  if (2n * (absolute % divisor) >= divisor) rounded = rounded + 1n
  if (value.numerator < 0n) return -rounded
  return rounded
}

/** 閉じた失敗封筒だけを返す。 */
function failure(code: string): string {
  return JSON.stringify({ ok: false, error: { code: code } })
}

/** 画面座標を量子化後に視点反転し、B-7の保存正準整数へ一度だけ写す。 */
export function quantizeCourse(requestJson: string): string {
  if (typeof requestJson !== 'string') return failure('INVALID_JSON')
  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return failure('INVALID_JSON')
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))
    return failure('INVALID_REQUEST')
  const keys = ['x', 'y', 'view', 'size']
  if (!Object.keys(parsed).every((key) => keys.includes(key)))
    return failure('INVALID_REQUEST')
  if (!keys.every((key) => Object.prototype.hasOwnProperty.call(parsed, key)))
    return failure('INVALID_REQUEST')
  const input = parsed as Record<string, unknown>
  const size = sizeValue(input.size)
  if (size === null) return failure('INVALID_SIZE')
  if (input.view !== 'catcher' && input.view !== 'pitcher')
    return failure('INVALID_VIEW')
  const x = decimal(input.x)
  const y = decimal(input.y)
  if (x === null || y === null) return failure('INVALID_DECIMAL')
  if (!inRange(x, size) || !inRange(y, size)) return failure('OUT_OF_RANGE')
  const roundedX = halfUp(x)
  const roundedY = halfUp(y)
  let storedX = roundedX
  if (input.view === 'pitcher') storedX = size - roundedX
  return JSON.stringify({
    ok: true,
    value: {
      unit: '1/' + size.toString(),
      x: storedX.toString(),
      y: (size - roundedY).toString(),
    },
  })
}
