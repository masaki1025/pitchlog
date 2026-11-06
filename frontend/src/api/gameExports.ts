import { apiDownload } from './client'

export interface PlayCsvDownload {
  blob: Blob
  filename: string | null
  contentLength: number | null
  sha256: string | null
}

export async function downloadPlayCsv(
  gameId: string,
  signal?: AbortSignal,
): Promise<PlayCsvDownload> {
  return apiDownload(`/games/${gameId}/exports/plays.zip`, { signal })
}
