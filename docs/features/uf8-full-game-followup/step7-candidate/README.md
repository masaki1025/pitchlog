# ステップ7: CI・凍結資産の未受理候補

このディレクトリは **2026-10-21 時点の候補**であり、正式7.7受理記録ではない。実 `.github/workflows/ci.yml`、`contracts/tenant_boundary/`、比較corpusには適用していない。計画承認を実値の受理へ流用しない。`accepted_by`、`accepted_date`、`accepted_on`、`signature`、追記履歴の `acceptance_id`、`approved_by`、`approved_on` は空欄である。既存23件の履歴と署名は `before` / `after` の共通prefixにそのまま保持し、追記24件目へ転記していない。

## 候補の単位と適用範囲

- ソース側 Git base: `8e4698f6dc254439b7d5e0c273cc2aef70cda657`。候補計算時の枝HEADは `a6f9783670d3eeb044b86d49ca61937d63829160`。Draft 6〜7の同一PR番号、受理直前・直後のSHAは未割当。PR時点の差分を元に再固定する。
- 宣言済み範囲: `.github/workflows/ci.yml`、`base-allowlist.json`、`census-baseline.json`、`history-snapshots/`、比較corpus `manifest.json`。CI候補は既存必須 `frontend` job の同じ検査列へ `uv` / 製品backend依存 / pinned PostgreSQL 17.11 / Chromium / `pnpm run test:browser` を追加する。既存の `mise`、Node、pnpm、eslint、Prettier、型、domain build、Vitestは保持する。
- 逆依存の実測: CIは計8資産の `baseline_control.identity.frozen_projection.external_files` に含まれる。未宣言の波及は `cache-invalidation-contract.json`、`db-api-inventory.json`、`negative-fixtures.json`、`repository-contract.json`、`runtime-authz-contract.json`、`tenant-context-allowlist.json` の6資産。正式適用にはこの具体範囲の計画追補が必要。対象集合や検査器を縮小しない。
- `frozen-inputs.json` は同じ検査の資産だがCIを外部凍結対象に持たず、識別子 `contract_revision:4` を維持する。候補のv2履歴は9資産全体の前後識別子を保持する。

## 実値とファイル

`metadata.json` は9資産の宣言場所・識別解釈・前後識別子・射影digest、外部8ファイルすべての前後SHA-256、発火trigger、oldhistoryとsnapshotの件数、比較corpus digestを列挙する。`before/` と `after/` はCI、影響8資産、manifestの全ファイルを保存する。`candidate.patch` はこれらの差分と新規snapshot9件の完全な統一patchであり、元の資産を消さない。`new-snapshots/` の各ファイル名は内容SHA-256である。

主要値:

| 対象 | 前 | 後候補 |
| --- | --- | --- |
| CI SHA-256 | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `0206d208474482e4e50dbb6993b9771a7ae86282a4d8e5e2598a7a52ec863718` |
| base識別子 | `contract_revision:33` | `contract_revision:34` |
| census識別子 | `contract_revision:14` | `contract_revision:15` |
| 既存履歴 / 新履歴 | 23件、最終旧record SHA-256 `b9f4c05b5899225392deb9350ef5c05543c4ad90c493ab77905572d180761b55` | 旧23件の同一prefix + 未受理候補1件 |
| snapshot件数 | 179件 | 旧179件保持 + 9件候補 |
| corpus入力digest | `b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce` | `21334bcd53f38962c50a5c968a48a2465ca526e6673e2596b3ba8457898cf835` |

`generate.py` は既存 `scripts/frozen_history.py` の `frozen_projection_content` を含む射影・movement・snapshot関数と、比較corpusの `runner.corpus_input_digest` を呼ぶ。独自の凍結射影・corpus digest手順を作らない。再生成コマンドはリポジトリルートで `PYTHONPATH=scripts:tests/fixtures/frozen-archive-cases .venv/bin/python docs/features/uf8-full-game-followup/step7-candidate/generate.py`。旧比較corpusの固定prefix（履歴6件、宣言済みsnapshot名）は維持し、新snapshotを固定済みprefixへ混入させない。新しい比較ケースfixtureは現時点で不要で、manifestの入力digestのみが変わる。

候補検査は `GameScreenCandidate.spec.ts`（元ファイルと候補beforeの同一性、対象集合、旧履歴prefix、未受理欄、新snapshot SHA、patch対象）と、隔離一時ディレクトリでの `git apply --check`・適用後bytes一致で行う。正式受理検査は、実PRの単一受理単位と人間本人の記録を得た後に別途実施する。空欄のまま正式履歴検査へ投入すると不合格になる設計であり、候補検査の成功を正式受理済みと扱わない。

既存 `scripts/frozen_archive.py` の `validate_snapshot_archive` を候補前後と隔離したsnapshot集合へ実行した結果、前179件・後188件、孤児snapshotは前後とも33件だった。新規9件に参照漏れはない。既存 `runner.validate_corpus_inputs` も候補afterの隔離ツリーで成功した。これらの検査は人間受理欄やPR受理単位を検証する正式検査の代替ではない。

主担当ホストの封鎖検査は `cd frontend && pnpm run test:browser`、同義の直接経路は `pnpm exec playwright test --config src/screens/GameScreen.playwright.config.ts --project sealed-ui`。`test:browser` は既存必須frontend jobへのCI候補でも同じ封鎖経路を指す。事前に `cd backend && uv sync --locked --dev`、frontendの固定lockによる `pnpm install --frozen-lockfile`、既存hostブラウザ1.61.0と `postgres:17.11-bookworm` imageの存在を確認する。追加downloadは内側sandboxで行わない。Python driver は pytest 開始前に自分の outer 使い捨てDBクラスタを立て、既存 `verify_connection_identities` autouse に実管理・実被検査ロール DSN を渡す。既存 `provisioned_product_catalog` は別の inner 専用クラスタを立て、実 `create_app`・実ログイン・Secure CookieをHTTPS画面で通す。外部/shared DSN は継承しない。

`pnpm run test:browser:real` または直接 `--project real-game` は、正式ゲームPort・シナリオdriverが未接続のため SHA/ID の環境文字列を与えても必ず未達で失敗する。`--project` を付けない直接コマンドは両projectを実行するため、同じく現段階では失敗する。これは封鎖検査の合否を実試合完遂へ流用しないための境界であり、実driverはステップ8〜9で接続する。主担当ホストの旧試行2回は、初回がPython import、2回目が outer DB の `ADMIN_DSN` 未設定によってsetupで失敗した。bootstrap是正後、主担当ホストで実HTTPS画面・実Auth HTTP・専用outer/inner DBの起動は実測した。初回は封鎖5件中3成功/2失敗、是正後の最終安定ソースでの試行は1成功/4失敗。別の安全な通信診断でChromiumのERR_NETWORK_CHANGEDを確認した。並行する全件DB検査のコンテナ作成/撤去との関係を切り分けるため、全件DB検査の終了後にブラウザを直列実行する。現時点で封鎖5件全成功、実ゲームPort受入、1試合完遂とは記録しない。

候補patchのSHA-256は `4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fc`。主担当は隔離環境で `git apply --check`、実適用後の全after bytes、9 snapshot SHAの一致を確認済み。この補完は `test:browser` scriptの意味を封鎖projectへ限定するだけで、CI候補の `pnpm run test:browser` 行とpatch bytesは変えない。未宣言6資産の計画追補案 `step7-scope-extension.md` は未回答・未受理であり、実CI・凍結資産・人間欄は変更していない。

主担当ホストの次の実測では実 Auth HTTP・HTTPS・専用 outer/inner DB の起動が成功し、sealed-ui は5件中3件成功・2件失敗（25.3秒）。logout要求の403は実 CSRF ゲートが要求する `X-Pitchlog-Request: 1` と自分の HTTPS Origin の許可不足、遅延テストは初期 `/team` GET と reload の重なりによる既存の認証不確実性が疑われる。候補サポートは先に自分用loopbackポートを選び、`strictPort:true` で衝突時は起動失敗にし、その厳密な `https://127.0.0.1:<port>` だけを backend の `PITCHLOG_ALLOWED_ORIGINS` に渡す。logoutの実ヘッダと旧Cookieの401、初期GET完了後の遅延、必要時の画面上の明示再確認GETから最終 `/games` 封鎖表示を検証する。修正後の host E2E 合否は主担当の再実行待ちであり、3成功2失敗を成功へ書き換えない。正式ゲームPort・1試合完遂は未提供のまま。

主担当ホストの続く2回の実測は `/tmp/uf8-entry-real-e2e-host2.log`（変更途上、36.9秒）と `/tmp/uf8-entry-real-e2e-host3.log`（前回wrapper終了後のsource、30.5秒）で、どちらも封鎖5件中3成功・2失敗。host3は通常route・未知ID/複数タブ・tenant変更が成功した一方、匿名/失効と遅延の2件はログイン補助の`/team`を先に5秒待って失敗した。先行していたteam一覧の待機は試験終了後に追加rejectionを出した。host2の匿名routeには初回表示が空のまま5秒経過した記録がある。この時点で初期Vite compile/host負荷と認証相関のどちらが原因かは未確定。logout 200と旧Cookie 401も未実測である。

補助を初回フォームの`aria-busy=false`と入力可能状態、実POST login 200とfixture tenant、POST後に始まる実session GETの応答、実team一覧GET 200・tenant照合・読取完了、最終画面の順に確認する形へ改めた。通常のsession GETは200・同tenantを要求する。実製品が認証不確実を示す場合に限り、画面の「状態を再確認」を1回操作して別の実session GET 200と同tenant、team一覧GET成功を要求する。資格情報の自動再送やmock認証は行わない。失敗時はHTTP method・queryを除いたpathname・status・経過msと固定UI状態のみを記録し、IDをpathnameから伏せる。初回ロードの通信が残っているのか、POST/GET応答は完了したのに画面が採用しないのかを次のhost実測で区別する。待機時間だけの緩和や失敗の成功扱いはしていない。修正後のhost合否とlogout 200/旧Cookie 401は主担当の再測定待ちである。
