/** 十進表記を検査し、正規表現エンジンの差を境界に持ち込まない。 */
function isDecimalInteger(value: string): boolean {
  let first = true
  let negative = false
  let leadingZero = false
  let hasDigit = false

  for (const character of value) {
    if (first && !negative && character === '-') {
      negative = true
      continue
    }
    if (character < '0' || character > '9') return false
    if (first && character === '0') leadingZero = true
    else if (leadingZero) return false
    first = false
    hasDigit = true
  }

  return hasDigit && !(negative && leadingZero)
}

/** 十進整数の文字列だけを BigInt に変換し、不正な値は受理しない。 */
export function parseDecimalInteger(value: unknown): bigint | null {
  if (typeof value !== 'string' || !isDecimalInteger(value)) {
    return null
  }
  return BigInt(value)
}

/** BigInt を JSON 境界で使う十進整数の文字列に変換する。 */
export function formatDecimalInteger(value: bigint): string {
  return value.toString()
}
