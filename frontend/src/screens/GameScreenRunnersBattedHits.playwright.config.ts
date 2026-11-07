import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

const scope = process.env.PITCHLOG_E2E_RUNNER_SCOPE
if (scope !== undefined && scope !== 'all' && scope !== 'fault')
  throw new Error('未知の走者画面検証scope')

export default defineConfig({
  grep: scope === 'fault' ? /^走者あり打球のT4途中故障/ : undefined,
  testDir: '.',
  testMatch: 'GameScreenRunnersBattedHits.e2e.ts',
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
