# MVP統合候補の引渡し（2026-11-12）

## 固定HEAD

- ブランチ: `feature/mvp-integration-20261109`
- コード固定HEAD: `e5360299`（以降は台帳・引渡し資料のみ。最終HEADはブランチ先頭）
- 比較元: `1989001a`（この日の開始時点）
- main / develop への push は行っていない。`feature/mvp-integration-20261109` は `1989001a` から `e5360299` まで通常push済み（force pushなし）。push後のローカルHEADと `origin/feature/mvp-integration-20261109` は `e5360299` で一致。

## 候補環境（テスト所有・使い捨て）

- URL: `https://127.0.0.1:60933`
- チーム名: `initial-scope-0ec4f78636a446758004f48109885242`
- パスワード: `public-owned-vertical-password-A1`
- これは `test_manual_app.py` が起動する owned DB / 実app / Vite の隔離環境であり、製品環境・実機・本番TLSの証拠ではない。環境を再起動すると URL・チーム名は変わる。

## 画面からの操作手順

1. 上記URLを開き、チーム名とパスワードでログインする。
2. `/games` の「開始済み一覧」から `/games/archive` を開く。準備中・進行中・終了のカード、状態フィルタ、ページ内検索、ページングを確認できる。
3. 準備中カードの「開始」または `/games` の「新しい試合」から試合を作成し、`/games/:id/record` で端末登録→スタメン→試合開始を行う。
4. 記録画面の「記録端末の安全確認が必要です」から4項目を確認し、球種・コース・結果を選んで保存する。通常結果は可視の結果パッド、打球結果は右ペインの観測フォームと「確定・保存」を使う。
5. メニューから「試合の終了・再開」「同期センター」「過去の訂正」「成績」「毎球CSV」を開ける。交代は下部バーの「交代」から `/games/:id/lineup` を開く。
6. 通信断の確認は、開始済み試合を一度開いてから DevTools の Network を Offline にし、reload して「端末内の記録」へ入る。未送信球は端末に残り、復帰後に「接続を確認して未送信記録を同期する」で送信される。

## このHEADで実証したこと

- **独立レビュー是正**: Codex敵対レビュー（`88652997`）のP1 1件・P2 2件を是正。P1は照会 `unresolved` 後も次attemptの回復許可が残り、次の独立操作後の再送で `skipRecovery` が適用され得た点。回復許可をslot/d5/attemptへ結び、`unresolved` で失効、送信直前にも一致を検査した。P2は停止解除時の自動再送と、打球語彙cacheの寿命・上限・認証切替時破棄。
- **ACK喪失E2E（是正後）**: `test_attempt_recovery_screen_e2e` **1 passed / 109.29秒**。

- **ACK喪失E2E**: `test_attempt_recovery_screen_e2e` **1 passed / 103.46秒**。ack-lost/before-httpの両モードで、再起動→復元→安全確認→「結果を照会」→「同じ要求を再送」→次球reloadを実画面・実DBで通過。照会は保存POSTを送らず、旧本文/旧attemptのまま権威照会だけを行う。照会中の切断でも保存POST 0件、再送は1回だけ（ack-lost=重複、before-http=受理）。

- **55プレイ通しE2E**: `test_screen_nine_innings_batted_out_stats_and_csv` **1 passed / 636.91秒**。新規作成→開始→55プレイ（18半回、本塁打1＋凡打54）→終了宣言→reload→成績27項目→毎球ZIP/成績CSVを保存原本と照合。

- `GET /games/archive` の実DB/実HTTP/実ブラウザ表示（2カード、状態、日時、試合ID、開始/成績/CSV導線）。比較画像: `docs/features/mvp-old-ui-parity/images/game-archive.png`。
- 実ブラウザで `GET /games/archive` の tenant 照合ヘッダー欠落を検出し、`_MATCH_OPERATIONS` と網羅試験で修正。
- 通信断cold再起動・未送信2球・復帰後の同原文順同期: `test_offline_recording_reentry_e2e` **1 passed / 94.47秒**。断中POST 0件、復帰後2 POSTの原文/attempt hash一致。
- 通常3球の実画面E2Eの最初のケース **1 passed / 33.7秒**。
- フロント全件 **216 files / 4135 tests passed**。
- backend 対象 **281 passed**（archive/authz/api/conventions）。既知赤は `test_batted_hit_product_declarations::test_batted_hit_sql_and_existing_activation_are_exact` のSQL digest 1件で、今回差分外。
- `base-allowlist.json` の `_BindingAuthority._call` 署名を実行時に一致させ、既知赤1件を解消。
- `repository-contract.json` の固定関数operation IDをregistryの全60件へ一致させ、既知赤1件を解消。

## 未達・既知の制限（MVP完成とは区別する）

- **終了・再開・追加・再終了の性能**: 実画面の機能assertは通過したが、同期1回が **7920ms** でNFR-002の5秒目標に未達。

- **タイブレーク開始・各半回再配置（TB-P1/P2/P3=A）**: 純遷移核と無効表示のみ。正式operationRows/case・保存・同期・画面・次球は未接続。
- **7回制・延長**: 固定5規則はすべて9回で、`resolve_stage_a_rule` が9回以外を拒否する。7回・延長上限>9を製品から作れない。
- **記録担当端末の引き継ぎ（FR-013）**: 通常/緊急引き継ぎ、世代更新、旧世代イベントの退避・閲覧の製品経路が未実装。
- **その場の選手登録の断中キュー**: オンラインの `POST /players` は接続したが、FR-015の一時ID・断中登録・交代との順序保証は未実装。断中は登録導線を閉じている。
- **登録の冪等性**: `POST /players` は要求ごとに新しいIDを作る。応答喪失時は「結果不明」として名簿再取得を促すが、同じ安定キーでの照会・再送は未実装。
- **tenant-boundary 7.7 正式受理**: `base-allowlist` は `contract_revision:54` のまま。統合ブランチの新規関数・経路に対して `tests/test_check_tenant_boundary_bypass.py` が多数赤（単一ファイルで570 failed / 1237 passed / 2 errors）。`repository-contract` 39 の履歴・snapshot・承認も未追随。受理済みとして扱わない。
- **歴史的射影の固定値**: `test_sync_apply_product_supply.py` の `catalog_before_revision`/`catalog_after_revision` が現在の `ddl-elements.json` と一致せず、3件が赤。非play通常保存で prepare/finish projection のSQL本文が意図的に変わったため、旧batted参照fixtureとの同時更新（正式受理）が必要。
- 実機・本番TLS・バックアップ復旧・運用公開は未実施（開発完了後の受入項目）。

## 次の作業

1. タイブレークの正式pipeline（operationRows/case、nonplay frame、保存・同期、画面、次球、成績/CSV）を実装する。
2. 7回制・延長の規則解決を正式資産として追加する。
3. FR-013の引き継ぎ（通常/緊急、世代、退避）を実装する。
4. 断中のその場選手登録（一時ID・耐久キュー・交代順序）を実装する。
5. tenant-boundary 7.7の正式受理とCI全件を通す。
6. 同期性能5秒目標と閲覧負荷を別担当の実測へ接続する。
