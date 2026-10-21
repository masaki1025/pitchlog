/** 画面の入力要求と下書き文脈だけを比較する。通信形式や要求IDは作らない。 */
function isPlainObject(value: object): boolean {
  const prototype: unknown = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

/** Vue の参照差や同一参照の後続変更に左右されない比較用コピー。 */
export function snapshotDisplayValue(
  value: unknown,
  seen = new WeakMap<object, unknown>(),
): unknown {
  if (typeof value !== 'object' || value === null) return value
  if (seen.has(value)) return seen.get(value)
  if (Array.isArray(value)) {
    const copy: unknown[] = []
    seen.set(value, copy)
    for (const item of value) copy.push(snapshotDisplayValue(item, seen))
    return copy
  }
  if (!isPlainObject(value)) return value
  const copy: Record<string, unknown> = Object.create(null)
  seen.set(value, copy)
  for (const key of Object.keys(value)) {
    copy[key] = snapshotDisplayValue(
      (value as Record<string, unknown>)[key],
      seen,
    )
  }
  return copy
}

/** 表示用の配列順と項目値を比較する。オブジェクトのプロパティ順は無視する。 */
export function sameDisplayValue(
  left: unknown,
  right: unknown,
  seen = new WeakMap<object, WeakSet<object>>(),
): boolean {
  if (Object.is(left, right)) return true
  if (
    typeof left !== 'object' ||
    left === null ||
    typeof right !== 'object' ||
    right === null
  )
    return false
  if (Array.isArray(left) || Array.isArray(right)) {
    if (
      !Array.isArray(left) ||
      !Array.isArray(right) ||
      left.length !== right.length
    )
      return false
  } else if (!isPlainObject(left) || !isPlainObject(right)) {
    return false
  }
  let compared = seen.get(left)
  if (compared?.has(right)) return true
  if (!compared) {
    compared = new WeakSet<object>()
    seen.set(left, compared)
  }
  compared.add(right)
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.every((item, index) =>
      sameDisplayValue(item, right[index], seen),
    )
  }
  const leftRecord = left as Record<string, unknown>
  const rightRecord = right as Record<string, unknown>
  const leftKeys = Object.keys(leftRecord)
  const rightKeys = Object.keys(rightRecord)
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key) =>
        Object.prototype.hasOwnProperty.call(rightRecord, key) &&
        sameDisplayValue(leftRecord[key], rightRecord[key], seen),
    )
  )
}
