import { apiDownload, type DownloadResult } from './client'

const CANONICAL_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

export class GameExportVerificationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'GameExportVerificationError'
  }
}

export interface VerifiedGamePlayArchive {
  blob: Blob
  filename: string | null
  sha256: string
}

async function sha256Hex(blob: Blob): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new GameExportVerificationError('ZIPのSHA256を確認できません')
  }
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    await blob.arrayBuffer(),
  )
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('')
}

/** 完成ZIPの長さと全体SHA256を、保存前に必ず照合する。 */
export async function verifyGamePlayArchive(
  archive: DownloadResult,
): Promise<VerifiedGamePlayArchive> {
  if (archive.contentLength === null || archive.sha256 === null) {
    throw new GameExportVerificationError(
      '完成ZIPの長さまたはSHA256を取得できません',
    )
  }
  if (archive.blob.size !== archive.contentLength) {
    throw new GameExportVerificationError('完成ZIPの長さが一致しません')
  }
  const actual = await sha256Hex(archive.blob)
  if (actual !== archive.sha256) {
    throw new GameExportVerificationError('完成ZIPのSHA256が一致しません')
  }
  return {
    blob: archive.blob,
    filename: archive.filename,
    sha256: archive.sha256,
  }
}

/** 記録済み1試合の毎球CSV ZIPを取得する。 */
export async function downloadGamePlayCsv(
  gameId: string,
  options: { signal?: AbortSignal } = {},
): Promise<DownloadResult> {
  if (!CANONICAL_UUID.test(gameId)) {
    throw new Error('試合IDが不正です')
  }
  return apiDownload(`/games/${gameId}/exports/plays.zip`, {
    signal: options.signal,
  })
}
