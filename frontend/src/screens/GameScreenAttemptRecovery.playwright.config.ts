import { defineConfig, devices } from '@playwright/test'
import { gameScreenOutputDirectory } from './GameScreenE2eProcess'

const origin = process.env.PITCHLOG_E2E_BASE_URL
if (
  origin &&
  (new URL(origin).hostname !== '127.0.0.1' ||
    new URL(origin).protocol !== 'https:')
)
  throw new Error('この証明書試験は隔離loopback HTTPS専用です')

export default defineConfig({
  testDir: '.',
  testMatch: 'GameScreenAttemptRecovery.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 480_000,
  use: {
    ...devices['Desktop Chrome'],
    // 隔離loopbackの実HTTPSだけを許す。信頼済み実機TLSの証拠にはしない。
    ignoreHTTPSErrors: true,
    // SW script取得はcontextのignoreHTTPSErrorsだけでは自己署名TLSを拒否する。
    // 実測対向で確認した隔離Chromium専用設定であり、製品/実機の信頼は変えない。
    launchOptions: { args: ['--ignore-certificate-errors'] },
    serviceWorkers: 'allow',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  reporter: 'list',
  outputDir: gameScreenOutputDirectory(),
})
