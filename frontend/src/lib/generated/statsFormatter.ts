// generated=sha256:7f0282944e6ce61d171caa428b4240a9429b0ac30d0e9f55dea828cec6a76524
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
type RatioPair = readonly [bigint, bigint] | null
type RatioDisplay = {
  scale: number
  rounding: string
  leadingZero: boolean
  zeroDivisionGlyph: string
  denominators: readonly { component: string; prefix: string; suffix: string }[]
}
function _rateResult(
  value: RatioPair,
  components: Record<string, RatioPair>,
  display: RatioDisplay,
  reason = 'MISSING_OBSERVATION',
) {
  const expected = display.denominators.map((x) => x.component)
  if (
    Object.keys(components).length !== expected.length ||
    Object.keys(components).some((k) => !expected.includes(k))
  )
    throw new Error('比componentの閉集合が不正です')
  for (const pair of [value, ...Object.values(components)])
    if (
      pair !== null &&
      (!Array.isArray(pair) ||
        pair.length !== 2 ||
        pair.some((x) => typeof x !== 'bigint' || x < 0n))
    )
      throw new Error('比の整数型が不正です')
  if (Object.values(components).some((pair) => pair === null) && value !== null)
    throw new Error('不足観測に比を補完できません')
  if (Object.values(components).some((pair) => pair === null))
    return {
      state: 'source_unavailable',
      value_state: 'not_evaluated',
      exact_ratio: null,
      components: null,
      formatted_value: null,
      display: null,
      reason,
    }
  const raw: Record<string, { numerator: string; denominator: string }> = {}
  for (const [key, pair] of Object.entries(components)) {
    if (pair === null) throw new Error('比が不足しています')
    raw[key] = {
      numerator: pair[0].toString(),
      denominator: pair[1].toString(),
    }
  }
  let exact: { numerator: string; denominator: string } | null = null,
    formatted: string,
    state: string
  if (
    Object.values(components).some((pair) => pair !== null && pair[1] === 0n)
  ) {
    formatted = display.zeroDivisionGlyph
    state = 'undefined_zero_denominator'
  } else {
    if (value === null) throw new Error('定義済み比の値が不足しています')
    let [n, d] = value,
      a = n,
      b = d
    if (d === 0n) throw new Error('定義済み比の分母は正です')
    while (b !== 0n) {
      const r = a % b
      a = b
      b = r
    }
    n /= a
    d /= a
    exact = { numerator: n.toString(), denominator: d.toString() }
    const power = 10n ** BigInt(display.scale),
      q = (n * power) / d,
      r = (n * power) % d
    const rounded = q + (2n * r >= d ? 1n : 0n)
    formatted =
      (rounded / power).toString() +
      '.' +
      (rounded % power).toString().padStart(display.scale, '0')
    state = 'defined'
  }
  const labels = display.denominators.map(
    (label) => label.prefix + raw[label.component]!.denominator + label.suffix,
  )
  return {
    state: 'available',
    value_state: state,
    exact_ratio: exact,
    components: raw,
    formatted_value: formatted,
    display: formatted + '(' + labels.join('・') + ')',
    reason: null,
  }
}

const RATE_DISPLAYS: Record<string, RatioDisplay> = {
  ops: {
    scale: 3,
    rounding: 'half-up',
    leadingZero: true,
    zeroDivisionGlyph: '−',
    denominators: [
      { component: 'obp', prefix: '出塁率分母', suffix: '打席' },
      { component: 'slg', prefix: '長打率分母', suffix: '打数' },
    ],
  },
}
export function formatDerivedRate(
  rateId: string,
  value: RatioPair,
  components: Record<string, RatioPair>,
) {
  if (!Object.hasOwn(RATE_DISPLAYS, rateId)) throw new Error('未知の派生率です')
  return _rateResult(value, components, RATE_DISPLAYS[rateId]!)
}
