import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenNonpitchPlayCsv.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 360_000,
  use: {
    ...devices['Desktop Chrome'],
    // 隔離loopbackの実HTTPS用。実機の信頼済みTLSの証拠にはしない。
    ignoreHTTPSErrors: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
