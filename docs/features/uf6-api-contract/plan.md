---
feature: uf6-api-contract
status: in-review            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-11・山田正輝) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f493b75e6878145aa82d873e8cb65f3
branch: feature/uf6-api-contract
created: 2026-10-11
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-F6 共通 API・形式契約 — TSK-521

## 1. 背景・目的

- Notion: [TSK-521](https://app.notion.com/p/3f493b75e6878145aa82d873e8cb65f3)(優先度 高)
- 単位定義: [frontend-impl-units/design.md](../frontend-impl-units/design.md) の U-F6 行(`:313`)

画面 8 単位(U-F3・U-F5・U-F8・U-F9・U-F10・U-F11・U-F12・U-F14)が、U-F6 の**共通 API** を待っている。担う FR の面は分担で、FR-012・013・003・007・040・031・038・034・041 に**共通する通信・形式の面**である。

**調査で単位定義の前提が崩れた**([research.md](research.md)「結論」)。

- **旧の `endpoints.ts`・`types.ts` は develop の backend とほぼ噛み合わない。**
  - 旧は 74 関数・147 型で、`/api` 接頭辞付きの旧契約に基づく。
  - develop の業務ルートは選手 4・対戦相手 4 の 8 本だけ。`/api` 接頭辞なし・カーソルページング・エラー封筒 `{"error":{"message","fields"}}` と、形が違う(`backend/src/pitchlog/api/`)。
  - 2026-08-16 の PO 裁定「API 契約を踏襲」(`docs/worklog/2026-08-16-frontend-skeleton.md:76-77`)と、U-M1 が作った形をすり合わせた記録は無い。
- **旧の `mock.ts`(4372 行)はドメイン計算を自前で持つ。**
  - 持っている計算: カウント・アウト・走者・得点・自責点・過去修正の再計算。
  - そのまま移すと NFR-018(要件書 `:928,936`)に反する。
- **同期の通信層は TSK-506(入口 PR)の担当である**(`docs/features/sync-wire-schema/design.md:362,399`)。
- **`lib/format.ts` は骨格タスクで逐語移植済み**(`../frontend-skeleton/porting-rules.md:123,163`)。

**PO 決定(2026-10-10・山田正輝 — /plan 前の分岐確認)**:

| # | 分岐 | 決定 |
| --- | --- | --- |
| Q1 | API の型と呼び出しを何に合わせるか | **いまの backend** に合わせる。旧の契約は参照資料にとどめる。U-F6 が作るのは共通の通信の仕組みと、いま在る 8 経路の型・呼び出しだけ。旧の残りの関数は、backend の単位が着地したときに各画面単位が足す |
| Q2 | モックモードを移植するか | **移植しない**。対象は `mock.ts`・`lib/mockRules.ts`・`lib/mockTeamManagement*`。理由は 3 つ。NFR-018 に反する。自責点は Won't(要件書 `:102`)。計算を抜くと画面の挙動を確かめられない |
| Q3 | 同期の送信と U-F6 の分担 | **U-F6 は土台だけ**を作る。同期の型・変換・送信と再送の分類は、TSK-506 が U-F6 のクライアントの上に作る |
| Q4 | `/api` 接頭辞 | クライアントは **`/api` を付けて送る**。開発用の転送設定(vite の proxy)で外す。画面の経路(`/games/:gameId` 等)と API の経路(同期の `POST /games/{game_id}/sync/events` 等)が、同一オリジンでぶつからないようにするため。本番の配信構成は ops へ申し送る |

単位定義からの変更(`endpoints.ts`・`types.ts` を丸ごと持つ → 共通部分だけ)は、I-28 の「判断が割れる場合は計画書ゲートで PO へ上げる」(`docs/improvements-from-baseball-scoring.md:242`)に従って PO が決めた。旧の作り方を書き起こす扱いは U-F1・U-F2 と同じ(ADR-002 v1.1 `:36`)。

## 2. スコープ

### やること

- `frontend/src/api/types.ts`: 共通の型。`ApiErrorBody`・`Page<T>`・`PageRequest`。
- `frontend/src/api/client.ts`: 共通 HTTP クライアント。`apiRequest`・`apiDownload`・`ApiError`・`ApiNetworkError`・`ApiStaleAuthError`(4 節の決定表)。
- `frontend/src/api/roster.ts`: develop にある 8 経路の DTO と呼び出し。
  - 対戦相手(team-records)4 本: 一覧・作成・名前変更・非表示化
  - 選手 4 本: 一覧・単体取得・作成・更新
- Vitest の試験(6 節)。
- `frontend/vite.config.ts` の proxy で `/api` を外す。存在しない文書を指すコメントも直す。
- `.claude/core-areas.json` の tenant-isolation の paths へ `frontend/src/api/*` を、sync-protocol・recording-rights の paths へ `frontend/src/api/client*` を登録する(宣言 → 登録の 2 段)。
- 移植規則への追記(`porting-rules.md` 11 節を新設)、単位定義への注記、下流と他タスクへの申し送り。

### やらないこと

| 項目 | 送り先・理由 |
| --- | --- |
| 旧の残り 66 関数とその型(試合・プレイ・分析・カルテ・比較グループ・帳票・CSV) | **各画面単位**。backend の単位の着地に合わせて足す(Q1) |
| 同期の型・wire 変換・送信・再送の分類(B1〜B8) | **TSK-506**(Q3)。`frontend/src/lib/sync/` には触れない |
| モックモード(`mock.ts`・`mockRules`・`mockTeamManagement`) | **移植しない**(Q2) |
| `lib/format.ts` | 移植済み。触れない |
| ログイン・ログアウト・PW 変更・セッション確認の呼び出し | **δ TSK-470** の HTTP 入口ができてから(U-F3 か δ が U-F6 のクライアントの上に足す) |
| 応答のテナント照合の**完全な形**(U-F2 の決定 G の窓) | **δ の契約が決まってから U-F6 の改訂で入れる**。照合の方式(要求の期待チーム ID か、応答の認証チーム ID か)が未決。それまでは決定 N の**認証世代の照合**で窓を狭め、**照合の完全な形が入るまでテナント所有データを表示する画面を本番に出さない**(決定 N・5 節 — 計画レビュー 1 回目 P0-1) |
| 本番の配信構成(`/api` を backend へ渡す reverse proxy) | **ops**(申し送り) |
| 利用者向け CSV 取り込みの API | 要件が無い(裁定 A-11 で要件化待ち) |
| OpenAPI の生成・固定 | **TSK-346**(生成物はコミットしないことが既決 — `docs/features/u00-api-shell/plan.md:67`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| (なし) | **反映なし**。要件書・設計書・ADR・ハーネス設計書・ops の正本は変えない。API 契約の正本は TSK-346(未着手)の担当で、U-F6 の型は暫定の層 (B) に依拠する | — |
| `docs/development/harness-evaluation.md` | `/pr` クローズ処理で追記(PR 作成時に宣言を追加): **H-69 へ再発の実測**(Codex の sandbox で閉域 spec の子プロセスが EPERM・検証のために**別の worktree の `.venv`** を `UV_PROJECT_ENVIRONMENT` に指して使い、`/tmp` に uv キャッシュを残した)。`H-*` は採番しない・版は上げない | PR レビュー(7.6-3 前段) |
| `docs/README.md` | 台帳行の最終更新日を 2026-10-11 へ | PR レビュー(7.6-3 前段) |

正本ではない文書で更新するもの(PR レビューで扱う):

- `docs/features/frontend-skeleton/porting-rules.md`: 11 節「U-F6 共通 API で追加した差分」を新設する。
- `docs/features/frontend-impl-units/design.md`: U-F6 行(`:313`)と 5 領域判定の行(`:334`)に、Q1〜Q4 と当て直しの結果を注記する。

文書ではないが、ハーネスの機構を変えるもの(PR レビュー + 敵対レビュー + 人間承認 — 設計書 6.3-⑤):

- `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` と `tests/test_core_guard.py`(宣言)
- `.claude/core-areas.json` の tenant-isolation の paths(登録)

## 4. 実装方針

### 重さ分類: コア領域

**意味判定の当て直し(契約 4 — 設計書 6.3 の 5 領域)**

単位定義の「5 領域すべて該当」(`frontend-impl-units/design.md:334,349`)は、旧の `endpoints.ts`・`types.ts`・`mock.ts` をそのまま移す前提で、4 つの面が**混在する**ことが根拠だった。Q1〜Q3 で持つ範囲が変わったので、次のとおり当て直す。

| 領域 | 判定 | 理由 |
| --- | --- | --- |
| **S 同期** | **該当(`client.ts` のみ)** | 同期の型・べき等キー・再送の分類は持たない(Q3)。ただし `client.ts` は TSK-506 が乗る**送信路**であり、失敗の例外と 409 の本文の受け渡しは同期の契約(拒否の分類・現在版の通知 — `docs/design/sync-protocol.md:1330`、`../sync-wire-schema/design.md:272,331`)を**変え得る**。判定に迷うので含む側に倒す(設計書 6.3 `:403` — 計画レビュー 1 回目 P0-3) |
| G 状況 | 非該当 | 状況計算・成績を持たない。モックも移植しない(Q2) |
| **R 記録権** | **該当(`client.ts` のみ)** | 世代・期待版を送る型は持たない(Q1)。ただし記録権拒否・版不一致の 409 本文を損なわずに上位へ渡す責任を `client.ts` が負う(同上 P0-3) |
| **T テナント** | **該当(`api/*` 全体)** | 401 で失効する(FR-033 の認可源)・認証の Cookie を送出する・認証世代で応答を照合する(決定 N)・テナント所有データ(選手・対戦相手)の呼び出し |
| D 移行 | 非該当 | 88 列・CSV を扱わない。`format.ts` に触れない |

**機械判定**: `frontend/vite.config.ts` は sync-protocol・game-state の paths に当たる(`.claude/core-areas.json:112,274`)。したがって **PR 全体がコア領域**になる(敵対レビュー + 人間の逐行確認)。

**ファイル分割(Notion の DoD「混在ファイルを分割するか、分割しない理由を書く」)**: 旧の混在ファイルは持ち込まない。`client.ts`(S・R・T — 送信路)・`types.ts`(T — `api/*` の glob で含める)・`roster.ts`(T)に分け、業務データの領域(試合・プレイ・88 列)を共通部分へ混ぜない。設計書 6.3 の規則 ④ は「paths を狭めるなら先に分割する」という順序の規則で(`docs/development/dev-harness-design-2026-08-07.md:404`)、本計画は最初から分けた形で登録する。

**paths の登録**: 規則 ①(コアの強制点を変え得るファイルを含める — 同 `:404`)と ③(重複帰属を許す)に従い、tenant-isolation に `frontend/src/api/*`、sync-protocol と recording-rights に `frontend/src/api/client*` を登録する。

- `frontend/src/api/*` はいまどの paths にも当たらない。
- 後続の画面単位が `api/` に足すファイルも、自動でコア領域の検知に入る(fail-closed — 同 `:403`)。
- 手順は U-F2 と同じ 2 段(宣言コミット → 登録コミット)。
  - `AREA_PATH_ADDITIONS` は「いま追加中のものだけを載せる」回転式なので、U-F2 の宣言を自分の 3 件(3 領域)に**置き換える**。U-F2 の宣言(`frontend/src/stores/authStore*`)は develop の JSON に取り込み済みである。sync-protocol・recording-rights は据え置き領域への宣言の新設になる。
  - `tests/test_core_guard.py` の U-F2 専用の表明のうち「実際の JSON に `authStore*` が含まれる」は残す。

**逐行確認の対象**: `api/*.ts`・spec・`vite.config.ts`・宣言と登録の差分。PR 本文に明示する。

### 決定(移植規則に無い・または規則から外れるもの)

| # | 対象 | 決定 | 根拠 |
| --- | --- | --- | --- |
| A | ファイル構成 | 旧の `client.ts`・`endpoints.ts`・`types.ts`・`mock.ts` の 1:1 対応をやめる。`client.ts`・`types.ts`・`roster.ts` の 3 つにする | Q1・Q3。旧の `endpoints.ts`・`types.ts` は全領域が混在していた(research.md 1-3 節)。移植規則 2 節の 1:1 対応からの逸脱 |
| B | 送り先 | `fetch('/api' + path)`。`credentials: 'include'` を付ける | Q4。Cookie `__Host-pitchlog_token`(`backend/src/pitchlog/api/request_presentation.py:10`) |
| C | ヘッダ | 本文があるときだけ `Content-Type: application/json` を付ける。GET・HEAD・OPTIONS 以外には `X-Pitchlog-Request: 1` を付ける。`Authorization` は付けない | CSRF の要件(`request_presentation.py:11-12,90-92`)。トークンは HttpOnly Cookie(U-F2 の決定 A) |
| D | 送信前 | 送るたびに `useAuthStore(pinia).syncFromStorage()` を呼ぶ。`pinia` は `getActivePinia()` で取り、**無ければ `fetch` を呼ばずに例外で止める**(認証の照合なしに送らない — fail-closed)。U-F13 が `app.use(pinia)` を入れるまで、製品の実行経路で `apiRequest` を呼ぶ画面は無い(5 節の条件) | U-F2 の申し送り(`../uf2-auth-state/plan.md` 申し送り表)・U-F2 の決定 H。現行の `frontend/src/main.ts` は Pinia を install していない(計画レビュー 1 回目 P1-4) |
| E | 応答 | 2xx は JSON を返す(204・空本文は `undefined`)。JSON でない成功応答は `ApiError` にする(黙って文字列を返さない)。型は呼び出し側の宣言だけで受け、実行時の検証はしない | backend の DTO は `extra="forbid"` で形が固定されている(`backend/src/pitchlog/api/schemas/base.py:9-12`)。検証の要否は TSK-346 の形が決まってから |
| F | エラー | 封筒 `{"error":{"message","fields"?:[{"location"}]}}` を `ApiError{status, message, fields, retryAfterMs, body}` に写す。封筒でない応答は message を `HTTP <status>` にする。**どちらの場合も、解釈した本文(JSON なら値、そうでなければ文字列)を `body: unknown` として損なわずに保持する**(同期の 409 は `boundary_result`・`current_version`・`b9_cause` 等を本文で運ぶ — `../sync-wire-schema/design.md:272,331`。解釈は TSK-506 — 計画レビュー 1 回目 P0-2)。`Retry-After` は秒と HTTP-date の両方を解釈する | 封筒は `backend/src/pitchlog/api/errors.py:53-57`。`Retry-After` の解釈は旧 `api/client.ts:21-33` を書き起こす |
| G | 通信の失敗 | `fetch` の reject を `ApiNetworkError` に包んで投げる。`ApiError` とは区別する | NFR-015(黙殺しない)。再送の要否の判断は TSK-506 側 |
| H | 401 | **決定 N の世代照合を先に行い、世代が変わっていない 401 に限り**、`noAuthExpiry` が真でなければ `expireSession()` を呼んでから `ApiError` を投げる(古い世代の 401 で新しいセッションを失効させない — 計画レビュー 2 回目 P0-1)。画面遷移はしない(U-F13 の guard が担う) | U-F2 の申し送り。旧はダウンロード系とモックが 401 を素通りしていた(research.md 1-1・1-2 節)。`noAuthExpiry` は将来のログイン・PW 変更の呼び出し用 |
| I | 403・404・409 | 区別する分岐を持たない。どれも `ApiError` を投げる。自動の再試行も上書きもしない | FR-034(404 に一本化 — 要件書 `:641-642`)・I-2(台帳 `:39`)・FR-007 の楽観ロック(要件書 `:266`) |
| J | ダウンロード | `apiDownload(path, { query? })` は `{ blob, filename }` を返す。ファイル名は `Content-Disposition` から取る(RFC 5987 の `filename*` を優先)。保存の操作は呼び出し側 | 旧の 7 関数(`api/endpoints.ts:288-779`)が 401・`Retry-After`・例外型の扱いを揃えていなかった。1 本にまとめて同じ経路を通す |
| K | query | `query` は値が `undefined` の項目を省いて `URLSearchParams` に組む。配列は同じキーを繰り返す | backend の一覧の query(`roster.py:125-138`) |
| L | roster の呼び出し | 8 経路の DTO を `roster.py` に合わせ、snake_case のまま型にする。一覧は `limit` を必須にし、`cursor` と `next_cursor` を素通しで扱う。DELETE は `hideTeamRecord` という名前にする(論理削除 — 応答に `hidden_at` が入る) | `backend/src/pitchlog/api/schemas/roster.py:19-122`・`routers/team_records.py:154-179`。NFR-005・4.0-2(物理削除しない) |
| M | proxy | `vite.config.ts` の `/api` の proxy に `rewrite: (p) => p.replace(/^\/api(?=\/|\?|$)/, '') || '/'` を足す(`/api` の直後がパスの区切り・query・末尾のときだけ外す — 計画レビュー 2 回目 P1-3)。コメントは実在する根拠(本計画書)へ直す | Q4。現状は `/api` を残したまま転送し、backend の経路と合わない(`frontend/vite.config.ts:493,506-511`、`docs/features/onboarding-approval/plan.md:55`) |
| N | 認証世代の照合 | 送信の直前(決定 D の `syncFromStorage()` の後)に `authEpoch` を記録し、応答を受けたら**もう一度 `syncFromStorage()` を呼んで** `authEpoch` を比べる。変わっていれば応答を捨て、`ApiStaleAuthError` を投げる(表示・キャッシュへ渡さない)。**この照合は状態コードの解釈(401 の失効を含む)より先に行う**。`ApiStaleAuthError` は method・path・応答の status を持ち、message で「サーバーで処理された可能性があり、結果は未確認」と示す。**受け取った側は結果未確認として利用者に示し、保存・同期の要求なら完了扱いにしない**(NFR-015 — 計画レビュー 2 回目 P0-2・申し送り)。ダウンロードも同じ | U-F2 の決定 G の窓(別タブの切り替え)のうち、**要求の往復中に `bb.auth` が変わった場合**を閉じる。Cookie が `bb.auth` より先に変わる残りの窓は、δ の照合契約を入れるまで閉じない(やらないことの表・5 節の条件)。計画レビュー 1 回目 P0-1 |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`api/types.ts` と `api/client.ts`(`apiRequest`・`ApiError`・`ApiNetworkError`・`ApiStaleAuthError`)を作る**(決定 B〜I・K・N)。`api/client.spec.ts` を伴う | spec が 6 節「単体」「故障系」の client 分を含み green。とくに ① 封筒でない 409 の本文(`{"boundary_result":…,"current_version":…}` 形)が `ApiError.body` に同じ値で残る ② active Pinia が無いとき `fetch` が呼ばれずに例外になる ③ 往復中に `authEpoch` が変わった応答は `ApiStaleAuthError` になり、値を返さない ④ **往復中に世代が変わった 401 では `expireSession()` が呼ばれず、新しい認証状態と `bb.auth` が残る** / `vue-tsc`・`eslint`・`prettier --check .`・`depcruise src --validate` が green |
| 2 | **`apiDownload` を足す**(決定 J・N)。spec を伴う | spec: Blob とファイル名(`filename*` 優先・無いときは null)・401 で失効・エラーの封筒の写像・ネットワーク断・往復中の認証世代の変化で破棄 — green / 共通の検査が green |
| 3 | **`api/roster.ts` を作る**(決定 L)。`api/roster.spec.ts` を伴う | spec: 8 関数のメソッド・パス(UUID の埋め込み)・query(`limit` 必須・`cursor`・`include_hidden`・`team_record_id`・`roster_status_key`)・本文・戻り値の受け渡し — green / 共通の検査が green |
| 4 | **越境の試験を足す**(`api/client.boundary.spec.ts`) | ① 401 の応答で `sessionExpired` が立ち、`queryClient` が空になる。未同期キューに見立てた IndexedDB のレコード(`fake-indexeddb`)と他の `bb.*` キーは、開き直して同じ内容で残る ② 別タブで `bb.auth` が B に変わった状態で A のまま `apiRequest` を呼ぶと、送信前の照合で B へ切り替わる(キャッシュが空・`authEpoch` が増える) ③ `noAuthExpiry` の 401 では失効しない ④ 要求の往復中に別タブ相当の `bb.auth` の変化(B)が起きると、A の要求の応答は捨てられ(`ApiStaleAuthError`)、`queryClient` へ A のキーで入らない ⑤ 同じ状況で A の要求の応答が 401 でも、B の認証状態・`bb.auth`・キャッシュは失効しない — green |
| 5 | **`vite.config.ts` の proxy を直す**(決定 M)。rewrite の入出力を検査する spec(`src/testing/apiProxy.spec.ts` — 設定を import して `server.proxy['/api'].rewrite` を呼ぶ)を伴う | 差分は proxy の `rewrite` 1 項目・コメント・spec だけ / spec: `/api/health` → `/health`、`/api/players?limit=1` → `/players?limit=1`、`/api` → `/`、`/apix` は変えない(計画レビュー 1 回目 P1-5・2 回目 P1-3)/ `depcruise src --validate`・`pnpm run build`・`vitest run src/testing/`(閉域 spec)が green |
| 6 | **paths の宣言を置き換える**。`scripts/core_guard.py` の `AREA_PATH_ADDITIONS` を `{"sync-protocol": ("frontend/src/api/client*",), "recording-rights": ("frontend/src/api/client*",), "tenant-isolation": ("frontend/src/api/*",)}` に、`tests/test_core_guard.py` の期待値を新しい宣言に合わせる(合成設定の末尾判定・U-F2 の取り込み済み判定を含む — `tests/test_core_guard.py:598,2243,2297`)。`.claude/core-areas.json` は触らない | `uv run pytest tests/test_core_guard.py` が green / 「実際の JSON に `frontend/src/stores/authStore*` が含まれる」試験が残っている / 件数・末尾の表明が、登録前(sync-protocol 147・recording-rights 68・tenant-isolation 83)と登録後(148・69・84、各末尾が本単位の宣言)の両方を受理する / ruff・ty が green / `core-areas.json` が差分に無い |
| 7 | **paths を登録する**(`.claude/core-areas.json` の 3 領域の末尾 — **このコミットは JSON だけを変える**。`core_guard.py`・`test_core_guard.py` との同一コミットは機構が拒否する — `scripts/core_guard.py:370`、計画レビュー 2 回目 P1-4) | `uv run pytest tests/test_core_guard.py` が試験を直さずに green / `load_core_areas()` と `matched_paths()` に当てて `frontend/src/api/client.ts`・`roster.ts`・`client.spec.ts` が検知され、`frontend/src/lib/other.ts` は検知されない / 領域ごとに `client.ts` が sync-protocol・recording-rights・tenant-isolation の 3 つ、`roster.ts` が tenant-isolation だけに当たる(コマンドと出力をコミット本文に記録) |
| 8 | **登録を試験で固定する**。`tests/test_core_guard.py` に「実際の JSON の 3 領域に本単位の 3 件が含まれる」ことを要求する試験を足す(U-F2 の表明と同じ形・包含で見る)。JSON は触らない | `uv run pytest tests/test_core_guard.py` が green / 試験から 1 件を外した JSON の写しで落ちることをコミット本文に記録 / ruff・ty が green |
| 9 | **文書と申し送り**(Claude)。① `porting-rules.md` に 11 節を新設 ② `frontend-impl-units/design.md` の U-F6 行と 5 領域判定の行へ注記 ③ Notion へ申し送り、宛先と日付を worklog に記録 | ① 11 節に決定 A〜N と Q1〜Q4、利用の条件(Pinia・テナント照合)があり、4 節と食い違わない ② 注記がある ③ worklog に宛先ごとの記録がある / `uv run python scripts/check_plan_docs_sync.py` が 3 節と矛盾しない |

**各ステップ共通**: CI の frontend の全手順(`eslint`・`prettier --check .`・`vue-tsc --noEmit`・**`depcruise src --validate`**・`pnpm run build`・`pnpm test -- --run`)のうち、影響するものが green であること。ステップ 1・5 では全部を回す。depcruise は U-F2 で `/check` から漏れていたので明示する。

### 申し送りの中身(ステップ 9 ③)

| 宛先 | 内容 |
| --- | --- |
| TSK-506(同期の入口 PR) | 同期の送信は `apiRequest` の上に作る。U-F6 は再送の分類を持たないので、B1〜B8 の写像は TSK-506 の担当。`ApiNetworkError`・`ApiError.retryAfterMs`・`ApiError.body`(409 の本文を損なわず保持)を使える。**`ApiStaleAuthError` はサーバーで受理された可能性がある結果未確認の失敗で、キューを完了扱いにせず、同じべき等キーで再送して結果を確かめる**(FR-012 の同じキーでの再送 — 要件書 `:318`) |
| δ TSK-470 | ログイン・PW 変更の呼び出しは `apiRequest(..., { noAuthExpiry: true })` で作る。**テナント照合の契約が決まったら U-F6 の改訂で照合を入れる**(U-F2 の決定 G の窓)。`/api` 接頭辞(Q4) |
| TSK-346 | U-F6 の型は暫定の層 (B)(U-M1・U-00・U-01)に依拠している。正本ができたら追随する |
| U-F13 起動入口 | `app.use(pinia)` を入れるまで、製品の画面から `apiRequest` を呼べない(決定 D — fail-closed で例外になる) |
| 画面単位(U-F3・F5・F8・F9・F10・F11・F12・F14) | **δ の照合契約による応答のテナント照合が U-F6 へ入るまで、テナント所有データを表示する画面を本番へ出さない**(決定 N の残りの窓)。`ApiStaleAuthError` を受けたら結果未確認として利用者に示す(黙って捨てない — NFR-015)。旧の関数と型は移植しない。backend の経路が着地したら、自分の領域の `api/<領域>.ts` を `apiRequest` の上に足す。`api/*` は tenant-isolation の paths に入る(コア領域の検知)。モックは無い(Q2) |
| ops | 本番の配信で `/api/*` を backend へ渡し、`/api` を外す構成が要る(Q4)。CSP は `connect-src 'self'`(同一オリジン前提) |

## 5. DoD(受け入れ基準)

Notion TSK-521 の DoD と同期する(括弧内は担当ステップ)。

- [ ] **混在ファイルを分割するか、分割しない理由を書く** — 領域ごとにファイルを分け(決定 A)、混在ファイルを持ち込まない(4 節「ファイル分割」)(1・3)
- [ ] **ドメイン計算のコピー実装を作らない**(NFR-018)— モックを移植せず(Q2)、計算を持たない(1〜3)
- [ ] **越境の試験を持つ**(NFR-019 (b) の趣旨)— 401 で失効してキャッシュを捨て、キューは残る / 送信前に別タブの切り替えを反映する(4)
- [ ] **5 領域すべてへ当てた結果を計画書へ書いた**(契約 4 — 4 節の当て直し表)
- [ ] **横断要求を破っていない**(契約 5)(1〜4)
  - **論理削除**(4.0-2): 削除は `hideTeamRecord`(論理削除の経路)だけを呼ぶ
  - **黙殺しない**(4.0-2・NFR-015): エラーとネットワーク断を必ず投げる。ダウンロードも同じ経路を通す。認証世代の変化で捨てた応答は `ApiStaleAuthError`(結果未確認)として投げ、受け取る側の義務(利用者に示す・保存と同期を完了扱いにしない)を申し送る
  - **テナント分離**(NFR-010): 401 で失効させる・送信前と応答後に認証世代を照合する(決定 N)。残る窓は利用の条件で塞ぐ。認可の判定はサーバーが正で、403 と 404 を区別しない
  - **ページング**(NFR-005): 一覧は `limit` 必須・カーソル
  - **自動エスケープ**(NFR-023): HTML を組み立てない
  - **シークレット**(NFR-014): トークンを扱わない・ログに出さない
- [ ] **敵対レビューと人間の逐行確認を通した**(コア領域)(PR)
- [ ] `frontend/src/api/*` が tenant-isolation の、`frontend/src/api/client*` が sync-protocol・recording-rights の paths に登録され、試験で固定されている(6〜8)
- [ ] **利用の条件を下流へ渡した**(9): ① Pinia が install されるまで(U-F13)製品の画面から `apiRequest` を呼ばない ② **δ の照合契約による応答のテナント照合が U-F6 へ入るまで、テナント所有データを表示する画面を本番へ出さない**(決定 N で閉じない窓が残るため — NFR-010)
- [ ] 移植規則 11 節と単位定義の注記があり、申し送りが Notion に届いて worklog に記録されている(9)
- [ ] CI の frontend の全手順が green(全ステップ)

## 6. テスト計画

NFR-019 のテスト種別ごとに分ける(すべて Vitest・jsdom)。

- `fetch` は `vi.stubGlobal('fetch', …)` で差し替える。
- Pinia は `setActivePinia(createPinia())` で用意する。
- `localStorage` は spec ごとに空にする。

| 種別 | 追加するもの |
| --- | --- |
| 単体(1) | 送り先が `/api` + path になる |
| | `credentials: 'include'` が付く |
| | `X-Pitchlog-Request: 1` が POST・PATCH・DELETE にだけ付き、GET には付かない |
| | `Authorization` を付けない |
| | 本文の JSON 化と `Content-Type` |
| | 204・空本文が `undefined` になる |
| | query の組み立て(`undefined` の省略・配列) |
| | 封筒の写像(message・422 の fields) |
| | 封筒でない JSON や text のエラー |
| | `Retry-After` を秒と HTTP-date の両方で解釈する |
| | 送信前に `syncFromStorage` が呼ばれる |
| | 401 で `expireSession` が呼ばれる。`noAuthExpiry` のときは呼ばれない |
| | 403・404・409 が区別されずに `ApiError` になり、再試行されない(`fetch` の呼び出しは 1 回) |
| | 封筒でない 409 の本文が `ApiError.body` に同じ値で残る |
| | active Pinia が無いとき、`fetch` を呼ばずに例外 |
| | 往復中に `authEpoch` が変わった応答は `ApiStaleAuthError`(値を返さない)。世代が変わった 401 では失効させない |
| 単体(2) | `apiDownload` が Blob とファイル名を返す(`filename*`・`filename`・無し) |
| | 401・エラーが `apiRequest` と同じ扱いになる |
| 単体(3) | roster 8 関数のメソッド・パス・query・本文 |
| | `limit` が無い呼び出しを型が許さない(`@ts-expect-error` で固定) |
| 故障系(1・2) | `fetch` の reject が `ApiNetworkError` になる |
| | 成功応答が壊れた JSON のとき `ApiError` で投げる(黙って undefined にしない) |
| | JSON でない成功応答 |
| 越境(4) | ステップ 4 の合格条件 ①〜④ |
| 設定(5) | proxy の rewrite の入出力 |
| 一致性・E2E | 対象なし(ドメイン計算を持たない。backend との結合の E2E は画面単位とログイン入口が揃ってから) |

越境試験は NFR-019 (b) の列挙(サーバー経路が対象 — 要件書 `:977`)を直接満たすものではない。根拠は NFR-010(`:887`)と設計書 6.3 の「キャッシュ無効化」(`:400`)で、U-F2 と同じ扱いである。
