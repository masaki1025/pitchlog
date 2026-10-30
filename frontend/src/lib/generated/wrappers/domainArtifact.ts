/** 配布済み公開口の疎通操作だけを表す。 */
export type DomainArtifact = Readonly<{
  ping: (requestJson: string) => string
}>

/**
 * 無変換で配信された IIFE の公開口を取り出す。
 *
 * 未読み込み、未凍結、または疎通操作の形が違う場合は明示的に失敗する。
 */
export function getDomainArtifact(): DomainArtifact {
  const candidate: unknown = (globalThis as { PitchlogDomain?: unknown })
    .PitchlogDomain
  if (candidate === undefined) {
    throw new Error('ドメイン artifact が読み込まれていません')
  }
  if (typeof candidate !== 'object' || candidate === null) {
    throw new Error('ドメイン artifact の公開口が不正です')
  }
  const ping = Object.getOwnPropertyDescriptor(candidate, 'ping')
  if (!Object.isFrozen(candidate) || typeof ping?.value !== 'function') {
    throw new Error('ドメイン artifact の公開口が不正です')
  }
  return candidate as DomainArtifact
}

/** 初球接続で許可した単一artifact操作。 */
export type FirstBallDomainOperation =
  'deriveFirstPitchWithContinuation' | 'quantizeCourse'

/** 計算を複製せず、配布物の閉じた操作へJSONを渡す。 */
export function invokeFirstBallDomain(
  operation: FirstBallDomainOperation,
  request: unknown,
): unknown {
  const descriptor = Object.getOwnPropertyDescriptor(
    getDomainArtifact(),
    operation,
  )
  if (typeof descriptor?.value !== 'function')
    throw new Error('初球のドメイン操作が供給されていません')
  const response: unknown = descriptor.value(JSON.stringify(request))
  if (typeof response !== 'string')
    throw new Error('ドメイン応答がJSON文字列ではありません')
  const parsed: unknown = JSON.parse(response)
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))
    throw new Error('ドメイン応答の封筒が不正です')
  const envelope = parsed as Record<string, unknown>
  if (
    envelope.ok === true &&
    Object.keys(envelope).every((key) => key === 'ok' || key === 'value') &&
    Object.hasOwn(envelope, 'value')
  )
    return envelope.value
  throw new Error('初球の正式計算が成立しませんでした')
}
