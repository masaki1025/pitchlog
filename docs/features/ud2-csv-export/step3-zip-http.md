# ステップ3 完成ZIPの実HTTP登録

実装日: 2026-11-06。ステップ2の `PlayExportSource` を既存 `stream_csv` / `prepare_play_archive` へ接続し、`GET /games/{game_id}/exports/plays.zip`（`operation_id=game_play_csv_export`）を登録した。

## 応答

- 200: `application/zip`。`Content-Length`、`X-Pitchlog-Archive-SHA256`、`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、固定形式 `Content-Disposition`。manifestは既存writerが全10CSVのSHA256/bytes/行数とsnapshot/versionを含む。
- 401: 既存 `require_tenant_access` の認証失敗。
- 404: 不存在・別tenant・共有グループ・hidden/trashed。理由は区別しない。
- 409: 供給不足は `EXPORT_SOURCE_UNAVAILABLE` 相当の固定文言と、欠測列の `column_index` / 列名 / 供給群を `error.fields` に返す。送出前の再確認で版が変わった場合は `export_snapshot_changed`。
- 500: ZIP容量・CSV構造・ディスク障害。部分ZIPは返さない。
- 503: DB/RG1/型の失敗。内部SQL・payload・例外値を出さない。

## 同一版と途中失敗

- 読み取りは `tenant_export_read_scope` のREPEATABLE READ・READ ONLYで行い、全10CSVを同じ `PlayExportSource` から生成する。
- 完成ZIPは一時ファイルへ書き、CRC・全体SHA256・長さを確定してからcontext限定ハンドルを返す。`StreamingResponse` の反復子は成功・例外・クライアント切断のいずれでも `finally` でcontextを閉じる。
- 送出直前に別scopeで可視性とsnapshot digestを再確認する。試合が撤回・削除・変更されていれば完成ZIPを破棄し、404または409にする。
- `prepare_play_archive` は既存の上限（行・セル・行長・ファイル・展開総量・ZIP）をそのまま使う。

## 検証

- `uv run pytest tests/test_game_export_http.py tests/test_api_app.py tests/test_api_conventions.py -q`: 91成功。
- 完成ZIPのbytes・Content-Length・全体SHA256・保存禁止ヘッダ、401/404/409/500/503、供給不足の列だけの公開、版変更時の一時成果破棄、クライアント切断時のcontext closeを確認した。
- 実DBからの200は、ステップ2に記録したG03/G04-A/G10等の未接続列が残るため、現時点では成立しない。409の列不足を200へ読み替えない。
