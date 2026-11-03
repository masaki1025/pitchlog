import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenFirstBall.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  use: {
    ...devices['Desktop Chrome'],
    // 隔離loopbackの実HTTPS専用。実機の信頼済みTLS検証の証拠にはしない。
    ignoreHTTPSErrors: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
