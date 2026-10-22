import { test } from '@playwright/test'

test('正式ゲームの1試合完遂は供給後のdriver接続まで未達', () => {
  // SHA/ID の環境文字列だけを提供証拠や画面・DB・HTTP の完遂証拠としない。
  throw new Error(
    'real-game 未達: 正式ゲームPort・実入力・認証済み経路・実HTTP/DB状態を検証する1試合完遂driverはステップ8〜9で接続する',
  )
})
