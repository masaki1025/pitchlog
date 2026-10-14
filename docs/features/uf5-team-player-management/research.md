# U-F5 チーム・選手管理 調査記録

調査日: 2026-10-13

## 1. 起点と担当重複

- 専用 worktree: `/tmp/pitchlog-uf5-team-player-management`
- ブランチ: `feature/uf5-team-player-management`
- 起点: `origin/develop` の `928280e6b78c5e87049d164aa1f8f9538ef30edf`（PR #123 統合済み）
- `git worktree list`、ローカル branch、open PR を照合し、U-F5 / TSK-520 を名前または変更範囲に持つ別 worktree・branch・PR は見つからなかった。
- 既知の担当は U-D1、U-F8、U-M2、PR #119・#120 の各範囲であり、本計画の新規画面ファイルと重複しない。PR #120 の `frontend/src/api/**` と U-M2 の `backend/**` は依存先として読むだけで、変更しない。

## 2. 正式カードと単位境界

正式カードは [TSK-520 U-F5 チーム・選手画面](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2)。2026-10-13 の再取得時点でステータスは「未着手」、担当者は既存の人間担当者、優先度は「高」。カード本文と `frontend-impl-units/design.md` は次を定める。

- 旧 `TeamScreen.tsx`、`api/teamManagement.ts`、`TeamMembersContent.tsx` と選手プロフィール関連が候補全体。
- FR-015・017・018・039 の画面面、FR-034 の越境防止面、FR-038 の確認面に接する。
- 主所有は U-M1・U-T1・U-X5 のまま。
- T（テナント）・D（移行）のコア領域。敵対レビューと人間逐行確認が必要。
- 固有 DoD はページング、論理削除、同番号警告、類似名警告とリネーム誘導、越境試験、自動エスケープ、生 HTML 禁止、5 領域判定、反対側レビューと人間逐行確認。

本初期分割は一覧・登録・通常編集だけを扱う。FR-017 の在籍変更、FR-018 の削除、FR-015 の試合中その場登録、FR-039 の試合作成中その場登録、FR-038 の移行確認、プロフィール・測定値は後続である。したがって TSK-520 全体を完了扱いにしない。

## 3. develop に実在する U-M1 API

`backend/src/pitchlog/api/routers/{players,team_records}.py` と `schemas/roster.py` を照合した。架空の API や DTO は不要である。

| 操作 | 実在する経路 | 要求 / 応答 | 初期分割での扱い |
| --- | --- | --- | --- |
| チーム一覧 | `GET /team-records` | `limit` 必須、`cursor`、`include_hidden`; `Page[TeamRecordRead]` | `include_hidden=false` でカーソルページング |
| 対戦相手登録 | `POST /team-records` | `TeamRecordCreate{name}` → 201 `TeamRecordCreated` | 使用。作成される `kind` はサーバーが `opponent` に固定 |
| 対戦相手編集 | `PATCH /team-records/{id}` | `TeamRecordUpdate{name}` → `TeamRecordRead` | `kind=opponent` の行だけに表示 |
| 選手一覧 | `GET /players` | `limit` 必須、`cursor`、`team_record_id`、`roster_status_key`、`include_hidden`; `Page[PlayerRead]` | 選択したチーム単位、`include_hidden=false` でページング |
| 選手登録 | `POST /players` | `PlayerCreate` → 201 `PlayerCreated` | 使用。画面は投・打を必須入力し、新規在籍区分を `active`、ラベルを `null` に固定 |
| 選手編集 | `PATCH /players/{id}` | `PlayerUpdate` → `PlayerRead` | 名前・投・打・背番号だけ。API が拒否する在籍区分・ラベルは送らない |

`TeamRecordCreated.similar_names` は登録完了後に返る。画面は作成を取り消したように見せず、登録済みであることと類似候補を表示し、作成した行の名前編集へ誘導する。`PlayerCreated.same_number_players` も登録完了後に返るため、登録済みであることと同番号の現役選手を警告する。背番号は任意で、空欄は `null` として送る。

対戦相手登録はテナントを作らない。`TeamRecordCreateToken` が現在のテナント内へ `kind=opponent` のレコードを作る。PR #119 のログイン対象となる認証チームの作成やシステム管理者オンボーディングとは別である。

## 4. 共通 API と認証の実コード

### PR #120（U-F6）

`origin/feature/uf6-api-contract` には `frontend/src/api/{client,types,roster}.ts` がある。`roster.ts` は上表の API と DTO をすでに定義し、一覧の `limit` を型で必須にしている。U-F5 はこれを import し、コピーや別 DTO を作らない。

`client.ts` は Cookie を `credentials: 'include'` で送り、変更要求へ `X-Pitchlog-Request` を付ける。送信前・応答直後・本文読取後に U-F2 の `authEpoch` を照合し、切替済み応答を `ApiStaleAuthError` として破棄する。401 は現在のセッションを失効させる。

一方、PR #120 の計画書は応答テナントの完全照合を未実装と明記し、それが入るまでテナント所有データ画面を本番公開しない条件を置く。PR #120 は調査時点で open で、`origin/develop` に未統合である。

### PR #119（U-A1 認証 HTTP 入口）

`origin/feature/ua1-auth-http-entry` の `POST /auth/login` はチーム名・パスワードを受け、HttpOnly Cookie を発行する。成功本文は `{"status":"authenticated"}` だけで、`team_id` を返さない。保護 API は提示 Cookie から `TenantContext` を発行するため、サーバー側のテナント境界は存在する。

U-F2 の `teamId` は null を許す。PR #119 の応答だけでは、クライアントが期待テナント ID と応答テナントを照合できない。チーム名や Cookie の存在を ID の代用にしてはならない。したがって PR #119 の統合だけでは PR #120 が残した公開条件を満たさない。

### U-F13 の統合済み部分

develop には共有 Pinia、共有 QueryClient、router と公開 `/help` がある。現在の `router.ts` は `/` と `/help` だけで、認証ガード、`RouterView` の `authEpoch` key、保護画面、catch-all は未実装である。U-F13 の作業ログも 15 経路 + catch-all、認証ガード、越境試験を残余としている。

## 5. U-M2 のロック順との接合

PR #121 の U-M2 branch は、スタメン記憶保存と在籍変更のデッドロックを避けるため、`POST /players/status-apply` の選手行取得を UUID 昇順に変更し、応答順だけを入力順へ戻す。これは未統合のコア修正である。

初期分割は在籍変更・一括変更を含めず、`status-preview` / `status-apply` を呼ばない。したがって PR #121 を実装依存にしない。在籍変更を後続へ足すときは、PR #121 の統合後に同じロック順と応答順契約を再照合する。

## 6. 着手条件と公開条件

| 条件 | 初期画面の製品実装 | 保護ルート公開・実 API のブラウザ受入 |
| --- | --- | --- |
| PR #120 統合 | **必須**。共通クライアントと正規 DTO を import するため | 必須 |
| PR #119 統合 | 不要。未公開コンポーネントの実装と Vitest は可能 | **必須**。実ログイン Cookie で保護 API を呼ぶため |
| 応答テナント完全照合 | 未公開の間は残余として明示 | **必須**。U-F6 の公開禁止条件 |
| U-F13 認証ガード + `authEpoch` key | 未公開の間は残余として明示 | **必須**。U-F13 所有のルート接続条件 |
| 検証済みテナント ID の取得 | 未公開の間は残余として明示 | **必須**。認証済み主体から U-F2 へ期待 tenant ID を渡す承認済み契約と、応答側の独立した tenant 証跡が必要 |

初期 PR では `router.ts` と `App.vue` を変更せず、`TeamScreen.vue` を経路へ登録しない。これにより U-F13 の所有範囲と競合せず、不完全な保護画面を公開しない。実 API で登録・編集→一覧→再読込、A→B 認証切替時の A データ消去、別テナント ID への 404 は、上の公開条件が揃った接続 PR の必須受入とする。公開接続では、認証済み主体から得た期待 tenant ID と応答側の独立した tenant 証跡が一致することも実 API で確認する。取得元や応答形式は U-A1 / U-F6 の承認済み契約が決めるもので、本計画では仮の header・DTO・session API を定義しない。

## 7. テスト手段

現行 frontend に Playwright 設定や実バックエンドを起動する E2E harness はない。Vitest と Vue Test Utils はある。新しい harness を追加せず、初期 PR は次を自動化する。

- API 関数を境界で stub したコンポーネント試験: カーソルページング、登録、編集、警告、エラー、再取得。
- 共有 QueryClient と U-F2 store を使う統合試験: query key、mutation 後の invalidation、認証切替時のローカル状態と表示の破棄。
- 越境応答の 404 と `ApiStaleAuthError` を受けたとき、旧本文を表示せず mutation を自動再送しないこと。
- `<script>` や属性を含む名前を Vue の通常補間で文字列表示し、`v-html` を持たないこと。

実 API のブラウザ受入は接続 PR で既存の開発 DB・backend・Vite proxy を使って手動証跡を残す。将来 Playwright の正式 harness が着地した場合だけ、その正規経路へ同じシナリオを移す。
