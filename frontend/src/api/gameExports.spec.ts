import { describe, expect, it } from 'vitest'
import {
  verifyGamePlayArchive,
  GameExportVerificationError,
} from './gameExports'

async function digest(blob: Blob): Promise<string> {
  const value = await globalThis.crypto.subtle.digest(
    'SHA-256',
    await blob.arrayBuffer(),
  )
  return Array.from(new Uint8Array(value), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
}

const withSubtle = globalThis.crypto?.subtle ? it : it.skip

describe('verifyGamePlayArchive', () => {
  withSubtle('長さと全体SHA256が一致したZIPだけを受理する', async () => {
    const blob = new Blob(['zip-bytes'])
    const sha256 = await digest(blob)

    await expect(
      verifyGamePlayArchive({
        blob,
        filename: 'pitchlog-plays.zip',
        contentLength: blob.size,
        sha256,
      }),
    ).resolves.toEqual({
      blob,
      filename: 'pitchlog-plays.zip',
      sha256,
    })
  })

  it('ヘッダ欠落は保存対象にしない', async () => {
    await expect(
      verifyGamePlayArchive({
        blob: new Blob(['zip']),
        filename: null,
        contentLength: null,
        sha256: null,
      }),
    ).rejects.toBeInstanceOf(GameExportVerificationError)
  })

  withSubtle('長さ不一致は保存対象にしない', async () => {
    const blob = new Blob(['zip-bytes'])
    const sha256 = await digest(blob)

    await expect(
      verifyGamePlayArchive({
        blob,
        filename: null,
        contentLength: blob.size + 1,
        sha256,
      }),
    ).rejects.toThrow('長さが一致しません')
  })

  withSubtle('SHA256不一致は保存対象にしない', async () => {
    const blob = new Blob(['zip-bytes'])

    await expect(
      verifyGamePlayArchive({
        blob,
        filename: null,
        contentLength: blob.size,
        sha256: '0'.repeat(64),
      }),
    ).rejects.toThrow('SHA256が一致しません')
  })
})
