// 同期応答の受け取り境界で共通する、構造と重複の fail-closed 検査を集約する。
// 値の物理形式は解釈せず、own key と undefined の有無だけを扱う。

function includesKey(
  keys: readonly PropertyKey[],
  expected: PropertyKey,
): boolean {
  return keys.some((key) => Object.is(key, expected))
}

export function assertExactDefinedObject(
  candidate: unknown,
  allowedKeys: readonly PropertyKey[],
  requiredKeys: readonly PropertyKey[],
  errorMessage: string,
): asserts candidate is Record<PropertyKey, unknown> {
  if (
    !Object.is(typeof candidate, 'object') ||
    Object.is(candidate, null) ||
    Array.isArray(candidate)
  ) {
    throw new Error(errorMessage)
  }

  const input = candidate as object
  const ownKeys = Reflect.ownKeys(input)
  const hasUnexpectedKey = ownKeys.some((key) => !includesKey(allowedKeys, key))
  const hasMissingKey = requiredKeys.some((key) => !includesKey(ownKeys, key))
  const hasUndefinedValue = ownKeys.some((key) =>
    Object.is(Reflect.get(input, key), undefined),
  )
  const hasInheritedInputKey = allowedKeys.some(
    (key) => !includesKey(ownKeys, key) && Reflect.has(input, key),
  )

  if (
    hasUnexpectedKey ||
    hasMissingKey ||
    hasUndefinedValue ||
    hasInheritedInputKey
  ) {
    throw new Error(errorMessage)
  }
}

export function assertInputArray<Item>(
  candidate: unknown,
  errorMessage: string,
  sameItem?: (first: Item, second: Item) => boolean,
  duplicateErrorMessage: string = errorMessage,
): asserts candidate is readonly Item[] {
  if (!Array.isArray(candidate)) {
    throw new Error(errorMessage)
  }
  if (!sameItem) {
    return
  }

  for (let firstIndex = 0; firstIndex < candidate.length; firstIndex += 1) {
    for (
      let secondIndex = firstIndex + 1;
      secondIndex < candidate.length;
      secondIndex += 1
    ) {
      if (
        sameItem(candidate[firstIndex] as Item, candidate[secondIndex] as Item)
      ) {
        throw new Error(duplicateErrorMessage)
      }
    }
  }
}
