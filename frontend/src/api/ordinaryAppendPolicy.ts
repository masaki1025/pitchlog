/** B論点26の有限技術候補。実SQL/既wire照合の非作者受理とは別に版を固定する。 */
export type OrdinaryAppendPolicy = Readonly<{
  version: 'ordinary-append-v1'
  first_d2: '1'
  d2_gap: '1000'
  /** このFE Number伝送policyのlossless上限。DB bigint/正本D2の全体上限ではない。 */
  max_d2: '9007199254740991'
}>
export const ORDINARY_APPEND_POLICY: OrdinaryAppendPolicy = Object.freeze({
  version: 'ordinary-append-v1',
  first_d2: '1',
  d2_gap: '1000',
  max_d2: '9007199254740991',
})
export function isOrdinaryAppendPolicy(
  value: unknown,
): value is OrdinaryAppendPolicy {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return false
  const row = value as Record<string, unknown>
  return (
    Object.keys(row).sort().join(',') === 'd2_gap,first_d2,max_d2,version' &&
    row.version === ORDINARY_APPEND_POLICY.version &&
    row.first_d2 === ORDINARY_APPEND_POLICY.first_d2 &&
    row.d2_gap === ORDINARY_APPEND_POLICY.d2_gap &&
    row.max_d2 === ORDINARY_APPEND_POLICY.max_d2
  )
}
/** 既確定位置を変更せず、通常末尾の次ラベルだけを求める。挿入/再採番はしない。 */
export function nextOrdinaryD2(
  last: string | null,
  policy: OrdinaryAppendPolicy,
): string | null {
  if (
    !isOrdinaryAppendPolicy(policy) ||
    (last !== null && (!/^[1-9][0-9]*$/.test(last) || last.trim() !== last))
  )
    return null
  const next =
    last === null
      ? BigInt(policy.first_d2)
      : BigInt(last) + BigInt(policy.d2_gap)
  return next <= BigInt(policy.max_d2) ? String(next) : null
}
