import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenViewerThreeGameLoad.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 900_000,
  use: {
    ...devices['Desktop Chrome'],
    ignoreHTTPSErrors: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
