import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

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
  outputDir: mkdtempSync(resolve(tmpdir(), 'pitchlog-game-e2e-output-')),
})
