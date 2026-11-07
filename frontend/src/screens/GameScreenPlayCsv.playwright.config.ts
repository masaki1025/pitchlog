import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenPlayCsv.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 360_000,
  use: {
    ...devices['Desktop Chrome'],
    // 所有loopback HTTPSの機能検査。運用TLSや実機の検証にはしない。
    ignoreHTTPSErrors: true,
    acceptDownloads: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
