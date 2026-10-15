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
