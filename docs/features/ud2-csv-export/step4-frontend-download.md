# ステップ4 実画面ダウンロード

実装日: 2026-11-06。`GameScreenEntryRecordHost.vue`（実record route）へ `GameCsvExport.vue` を接続し、既存 `apiDownload` を後方互換で拡張した。

## API 取得部

- `apiDownload` の戻り値へ `contentLength` / `sha256` を追加した。`Content-Length` は非負整数の正規形、`X-Pitchlog-Archive-SHA256` は64桁小文字hexだけを受理し、欠落・不正は `null` にする。既存の `blob` / `filename` とstale認証検証は変えない。
- `api/gameExports.ts` はcanonical UUIDだけを `/games/{id}/exports/plays.zip` へ渡す。`verifyGamePlayArchive` はヘッダ欠落、`Blob.size` と `Content-Length` の不一致、`crypto.subtle` のSHA256不一致を保存前に拒否する。

## 画面

- `GameCsvExport.vue` はダウンロード、取消、再試行、成功/取消/失敗、401/404/409/503、stale/tenant変更、長さ/SHA不一致を表示する。
- 取得中は二重押下を無効化し、AbortControllerで取消できる。認証世代・tenantが取得中に変わった場合は保存しない。
- 検証済みBlobだけからobject URLを作り、anchorで保存した後 `setTimeout(0)` と unmount で `revokeObjectURL` する。
- 未送信件数がある場合はZIPに含まれないことを表示する。未同期キューをサーバー確定記録へ混ぜない。
- 供給不足の409は「不足列 N 件」を表示し、内容のないファイルを保存しない。

## 検証

- `pnpm exec eslint .` / `pnpm exec vue-tsc --noEmit`: 成功。
- `pnpm test`: 132ファイル・2760試験成功（追加: `GameCsvExport.spec.ts` 8件、`gameExports.spec.ts` 4件、`client.spec.ts` 2件）。
- 実画面→HTTP→DBの1試合ZIP保存は、ステップ2の供給不足列が残るため未成立。iPhone/iPad/Mac実機も未実施。
