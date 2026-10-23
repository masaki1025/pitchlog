import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1'
process.env.PLAYWRIGHT_LAST_RUN_OUTPUT_FILE = '/dev/null'

export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenPreparingRead.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  globalSetup: './GameScreenPreparingReadE2eSupport.ts',
  use: {
    ...devices['Desktop Chrome'],
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
