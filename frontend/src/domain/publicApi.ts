import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'

type DomainErrorCode =
  'INVALID_JSON' | 'INVALID_REQUEST' | 'INVALID_DECIMAL_INTEGER'

function errorResponse(code: DomainErrorCode): string {
  return JSON.stringify({ ok: false, error: { code } })
}

/**
 * 配布物の疎通だけに使う十進整数の往復操作。
 *
 * 入出力は JSON 文字列に統一する。不正な入力は例外を外へ出さず、
 * `{"ok":false,"error":{"code":"..."}}` を返す。計算対象のロジックは持たない。
 */
function ping(requestJson: string): string {
  if (typeof requestJson !== 'string') {
    return errorResponse('INVALID_REQUEST')
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return errorResponse('INVALID_JSON')
  }

  if (
    typeof parsed !== 'object' ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Object.prototype.hasOwnProperty.call(parsed, 'value') ||
    !Object.keys(parsed).every((key) => key === 'value')
  ) {
    return errorResponse('INVALID_REQUEST')
  }

  const value = parseDecimalInteger((parsed as Record<string, unknown>).value)
  if (value === null) {
    return errorResponse('INVALID_DECIMAL_INTEGER')
  }

  return JSON.stringify({ ok: true, value: formatDecimalInteger(value) })
}

/** JSON 文字列だけを境界とする操作の公開表。 */
export const domainOperations = Object.freeze({ ping })
