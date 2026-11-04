// generated=sha256:f358df32f54bedfecb2866436e718c7bd6ece514798fe4de2325022d38a09422
export function parseCount(value: unknown): bigint {
  if (typeof value === 'bigint' && value >= 0n) return value
  if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)
    return BigInt(value)
  if (typeof value === 'string' && /^(0|[1-9][0-9]*)$/.test(value))
    return BigInt(value)
  throw new Error('正準非負整数が必要です')
}
export function formatCount(value: unknown): string | null {
  if (value === null) return null
  if (typeof value === 'bigint' && value >= 0n) return value.toString()
  if (typeof value === 'string' && /^(0|[1-9][0-9]*)$/.test(value)) return value
  throw new Error('正準非負整数が必要です')
}
