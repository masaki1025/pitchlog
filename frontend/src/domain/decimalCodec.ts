const DECIMAL_INTEGER = /^-?(0|[1-9][0-9]*)$/

/** 十進整数の文字列だけを BigInt に変換し、不正な値は受理しない。 */
export function parseDecimalInteger(value: unknown): bigint | null {
  if (
    typeof value !== 'string' ||
    value === '-0' ||
    !DECIMAL_INTEGER.test(value)
  ) {
    return null
  }
  return BigInt(value)
}

/** BigInt を JSON 境界で使う十進整数の文字列に変換する。 */
export function formatDecimalInteger(value: bigint): string {
  return value.toString()
}
