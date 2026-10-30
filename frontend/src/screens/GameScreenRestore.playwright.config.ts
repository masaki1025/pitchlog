import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

// pytest が実app・専用DB・broker を起動し、baseURL と資格を env で渡す。
export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenRestore.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  use: {
    ...devices['Desktop Chrome'],
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
