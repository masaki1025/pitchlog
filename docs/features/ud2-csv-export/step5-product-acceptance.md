# ステップ5 往復・越境・故障の受入状況

実装日: 2026-11-06。実装HEADは `6646c7f7` 系（本表作成時点）。実装した範囲の検証と、未成立の受入を分けて記録する。

## 実行した検証

- backend static: `uv run ruff format --check src tests` / `uv run ruff check src tests` / `uv run ty check`（543ファイル）。
- backend unit/HTTP: `uv run pytest tests/test_authz_repository_contract.py tests/test_authz_capability_catalog.py tests/test_authz_capability_registration.py tests/test_play_export_repository.py tests/test_play_csv_rows.py tests/test_play_export_archive.py tests/test_csv_export.py tests/test_game_export_http.py tests/test_api_app.py tests/test_api_conventions.py -q`: 435成功。
- frontend: `pnpm exec eslint .` / `pnpm exec vue-tsc --noEmit` 成功、`pnpm test` 132ファイル・2760成功。
- 追加したpure/HTTP試験:
  - 88列の供給値と欠測の和が88列に一致し、欠測列を0/NULLへ置換しない。
  - 500行境界のキーセット継続、ページ内play_id集合の走者一括読取（N+1なし）。
  - 不存在・別tenant・hidden/trashedを同じ404へ閉じる。
  - ZIPのContent-Length/SHA256、401/404/409/500/503、版変更時の破棄、切断時の一時ファイルclose。
  - 画面の成功/失敗/取消/二重押下/認証世代変更/再試行/URL解除。
  - 9サイドカーが固定ヘッダの全キーを返す。
- 実DB受入テスト `backend/tests/db/test_play_export_repository_db.py` を追加した。実記録1試合を `tenant_export_read_scope` で読み、欠測列が上記の既知集合だけであること、不存在試合が `PlayExportNotVisible` になることを検査する。**この環境では `PITCHLOG_TEST_ADMIN_DSN` の接続先が起動しておらず、実行できていない**（`connection refused`）。CIのDB環境で実行する必要がある。

## 未成立（完了と扱わない）

- 実DB→実HTTP→画面の200往復は未成立。`handoff/supply-gaps.md` の列（34/42/43/50/51/61/62/73/74/86/87、non_pitch行の40）が欠測するため、実試合は409になる。部分88列を完成扱いしない。
- 終了→再開→訂正→再終了、新記録世代、大量データ、ページ境界の実DB受入は、実DBテストの実行後に確定する。
- 画面DLのbytesとbackend artifactの一致は、実HTTP 200が成立してから実測する。
- iPhone/iPad/Mac実機は未実施。
- 記録後改名時の履歴名保持は、共有同期核へのsnapshot追加（`handoff/supply-gaps.md` §2）が未適用。

## 引き渡し

- 制限付き資産の差分: `handoff/restricted-assets.patch`。
- 供給不足の列・提供元・必要差分: `handoff/supply-gaps.md`。
- PR作成・マージ・実機受入は主担当へ引き渡す。本ブランチは通常pushまで行う。
