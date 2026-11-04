// generated=sha256:db0c52f2df92ddd76a9681a940e1bae83f29fb7ff7f9e988b23a76cd5b52b40d
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
