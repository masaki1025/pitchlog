import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

// Playwright 1.61 の失敗時DOMコピーだけを抑え、試験のassertionは維持する。
process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1'
// reporterがteardown後に出力先を再作成しないよう、last-run状態は保持しない。
process.env.PLAYWRIGHT_LAST_RUN_OUTPUT_FILE = '/dev/null'

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  globalSetup: './GameScreenE2eSupport.ts',
  use: {
    ...devices['Desktop Chrome'],
    ignoreHTTPSErrors: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    { name: 'sealed-ui', testMatch: 'GameScreen.e2e.ts' },
    { name: 'real-game', testMatch: 'GameScreen.real.e2e.ts' },
  ],
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
