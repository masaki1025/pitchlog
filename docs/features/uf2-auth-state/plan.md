---
feature: uf2-auth-state
status: in-review            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-10・山田正輝) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f493b75e6878158b3d4fb0eafbb170d
branch: feature/uf2-auth-state
created: 2026-10-10
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-F2 認証状態(authStore)— TSK-517

## 1. 背景・目的

- Notion: [TSK-517](https://app.notion.com/p/3f493b75e6878158b3d4fb0eafbb170d)(優先度 高)
- 単位定義: [frontend-impl-units/design.md](../frontend-impl-units/design.md) の U-F2 行(`:309`)

旧 React 実装 `dd03160` の `stores/authStore.ts` は、**全画面をまたぐ唯一のストア**である(同 `:297`)。これを Vue 3 + Pinia へ移す。

- U-F3 以降の 13 画面と、共通 API(U-F6)・耐久キュー(U-F7)・起動入口(U-F13)が、この単位に依存する。
- 担う FR の面(分担): **FR-033 のセッション保持と失効反映**、**FR-034 のクライアント側の認可源**(同 `:471,473`)。
- 主所有は動かない。FR-033 は U-A1、FR-034 は U-T1 が持つ。

**旧の形はそのまま移せない**(調査: [research.md](research.md)「結論」)。

- 新方式では、トークンは `HttpOnly` Cookie で運ばれ、JavaScript からは読めない(H-2 — `../ua1-team-auth/design.md:18,196-197`、`backend/src/pitchlog/api/request_presentation.py:10`)。
- 正本は、提示値を応答本文に出さないと定めている(`docs/design/data-model.md:1678`)。
- 個人アカウントは Won't(要件書 `:99`、PO 裁定 B-1 `docs/worklog/2026-09-02-decision-sheet-ruling.md:53`)。
- チーム管理者ロールは導入しない(要件書 `:1127`)。

そこで本単位は、**秘密を持たない、チーム 1 つ分の認証状態**を作る。I-28(`docs/improvements-from-baseball-scoring.md:241-242`)により、要件と正本が既決にした改善を、旧の逐語より優先する。

**作り方**: 旧コードは参照資料とし、Vue / TypeScript で書き起こす。U-F1 の決定 K と同じ扱いで、ADR-002 v1.1 `:36` はどちらの作り方も許す。

**PO 決定(2026-10-10・山田正輝 — /plan 前の分岐確認)**:

| # | 分岐 | 決定 |
| --- | --- | --- |
| P1 | 状態の形 | **チームだけ持つ**。トークン・`authKind`・`username`・`role` を落とす。`bb.auth` には秘密でない項目だけを保存し、旧形式の値は読み捨てる |
| P2 | δ(TSK-470 — ログイン API)との順序 | **待たずに作る**。起動時は保存した見込みで認証済みとみなし、最初の 401 で未認証へ戻す(旧と同じ扱い)。δ へ応答に入れてほしい項目を申し送る |
| P3 | 依存と保存処理 | **pinia を同じ PR で足し、保存処理は自前で書く**(プラグインを足さない) |
| P4 | タブ間の同期 | **入れる**。旧に無いので、意図的な逸脱として記録する |

## 2. スコープ

### やること

- `frontend/src/stores/authStore.ts` を Pinia の setup store として書き起こす。持つものは次のとおり(4 節の決定表)。
  - 状態: 認証済みか・チームの表示名・チーム ID・失効したか・hydration の完了
  - 操作: ログイン成功の反映・ログアウト・失効の反映
  - 永続化(`bb.auth`)
- 認証が変わったときに `queryClient.clear()` を呼ぶ。U-F1 の申し送りで、これは U-F2 の担当と確定している(`../uf1-common-ui/plan.md:69`、`frontend/src/lib/queryClient.ts:10`)。
- 認証が変わるたびに増える世代番号(`authEpoch`)を公開する。購読中の画面を作り直す鍵に使う(決定 J)。
- タブ間の同期(P4)を入れる。U-F6 が送信前に呼ぶ照合の操作(`syncFromStorage()`)も公開する(決定 G)。
- `.claude/core-areas.json` の tenant-isolation の paths へ `frontend/src/stores/authStore*` を登録する(4 節「コア領域の判定」— 計画レビュー 1 回目 P0-3)。
- 依存 2 件を完全一致の版で足す: `pinia` **4.0.3** と、その必須 peer `@vue/devtools-api` **8.2.1**。
- Vitest の試験(6 節)を書く。
- 移植規則への追記(`porting-rules.md` 10 節の新設)と、単位定義(U-F2 行)への注記。
- 下流の Notion カードと δ への申し送り。

### やらないこと

| 項目 | 送り先・理由 |
| --- | --- |
| ログイン・ログアウトの HTTP 呼び出し、ログイン画面 | **U-F3**(入力・失敗表示)/ **δ TSK-470**(HTTP 入口)。本単位は通信を持たない |
| Cookie の付与・CSRF ヘッダ・401 の検知 | **U-F6**(`api/client.ts`)。401 を受けたら本単位の失効反映を呼ぶ |
| Pinia・vue-query の app への install、route guard | **U-F13**(`main.ts`・`App.vue`)。本単位は hydration の完了を公開し、guard がそれを待つ(`porting-rules.md:73-74`) |
| 未同期キュー(IndexedDB)・端末設定の `bb.*` キー | **U-F7・U-F8**。本単位は**触れない**(要件書 `:329`) |
| `requiresTeamAdmin` の route meta、`isTeamAdmin` による画面の出し分け | **作らない**(P1)。各画面単位へ申し送る |
| 起動時にセッションを確かめる経路 | **δ** の事項。本単位は P2 の扱いで待たない |
| `RouterView` に `authEpoch` を鍵として付ける配線 | **U-F13**。本単位は `authEpoch` を公開し、鍵で作り直せば前チームの表示が残らないことを試験の部品で示す(決定 J) |
| 送信前の照合の呼び出し | **U-F6**。本単位は `syncFromStorage()` を公開する(決定 G) |
| 共同分析グループの役割(FR-041 の `admin`/`member`) | グループごとの値で、セッションに 1 つ持つ形に合わない(research.md 2 節)。U-F11 |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| (なし) | **反映なし**。要件書・設計書・ADR・ハーネス設計書・ops のいずれも変えない。pinia の導入は ADR-002(フレームワークとツールチェーンだけを決める — `:26-28`)の射程外なので、本計画書の承認で扱う(U-F1 と同じ) | — |
| `docs/development/harness-evaluation.md` | `/pr` クローズ処理で追記(PR 作成時に宣言を追加): **H-69 へ再発の実測**(Codex の sandbox で pnpm の既定ストアを開けず `/tmp` のストアを経由・`.git` の index ロックを作れず `git checkout` が失敗・worktree 内へ uv キャッシュを作成)と、**候補「長時間 DB テストの強制終了が teardown を飛ばし…」へ共有 `/tmp` の満杯の再発**(3 回目 — プロンプトの書き出しが ENOSPC で失敗)。`H-*` は採番しない・版は上げない。索引の台帳行の日付はすでに 2026-10-10 のため変えない | PR レビュー(7.6-3 前段) |

正本ではない文書で更新するもの(PR レビューで扱う):

- `docs/features/frontend-skeleton/porting-rules.md`
  - 10 節「U-F2 認証状態で追加した差分」を新設する(4 節の決定のうち、規則から外れるもの)。
  - 6 節の 3 行(`:71` 認証リダイレクト・`:74` 永続化と hydration・`:75` `getState()`)は書き換えない。それぞれ「10 節を参照」と注記する。
- `docs/features/frontend-impl-units/design.md`
  - U-F2 行(`:309`)に注記する: 「役割は持たない(要件書 `:1127`)・トークンは持たない(H-2)」。

文書ではないが、ハーネスの機構を変えるもの(PR レビュー + 敵対レビュー + 人間承認 — 設計書 6.3-⑤):

- `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` と `tests/test_core_guard.py` の期待値(宣言)
- `.claude/core-areas.json` の tenant-isolation の paths(登録)

## 4. 実装方針

### 重さ分類: コア領域

**根拠 1(意味範囲)**

- U-F2 は**テナント分離(T)に該当**する(`../frontend-impl-units/design.md:330,356` — FR-033 の「認可源・管理経路」)。
- 設計書 6.3 の境界定義表は、テナント分離に「キャッシュ無効化」を含める(`docs/development/dev-harness-design-2026-08-07.md:400`)。認証が変わったときの `queryClient.clear()` はこの面に当たる。

**根拠 2(機械判定)**

- 依存を足すと `frontend/package.json`・`frontend/pnpm-lock.yaml` が変わる。どちらも `.claude/core-areas.json` の sync-protocol・game-state の paths に当たる。
- → **敵対レビュー + 人間の逐行確認**が要る。

**意味上の判定(契約 4 — 6.3 の 5 領域)**

| 領域 | 判定 | 理由 |
| --- | --- | --- |
| S 同期 | 非該当 | キュー・送信に触れない(触れないことを試験で示す) |
| G 状況 | 非該当 | 状況計算を持たない |
| R 記録権 | 非該当 | 世代・引き継ぎに触れない |
| **T テナント** | **該当** | 認可源・キャッシュ無効化 |
| D 移行 | 非該当 | 88 列に触れない |

**paths への登録(計画レビュー 1 回目 P0-3 の採用)**

- `frontend/src/stores/` はどの paths にも当たらない。本 PR は `package.json` で機械判定に当たるが、後の PR が `authStore.ts` だけを変えると非コアとして通ってしまう。
- 設計書 6.3 の落とし込み規則 ①(コアの不変条件・強制点を変え得るファイルを含める — `docs/development/dev-harness-design-2026-08-07.md:404`)に従い、**本 PR で tenant-isolation の paths に `frontend/src/stores/authStore*` を登録する**。
- 手順は機構が強制する 2 段で行う(`scripts/core_guard.py:30` のコメント・`verify_area_path_baseline()`)。
  - 宣言コミット: `AREA_PATH_ADDITIONS` を**本単位の 1 件だけに置き換える**。直前の宣言(U-M1 の tenant-isolation 7 件)は develop の JSON に取り込み済みなので消す。あわせて `tests/test_core_guard.py` の期待値を直す。
  - 登録コミット: `.claude/core-areas.json` の tenant-isolation の paths の末尾へ足す。
  - 2 つは同一コミットにできない。
- 他の単位が同時に宣言を足していれば、後着の側が develop を取り込んで宣言を置き換える。
- 登録は 6.3-⑤ の審査対象(敵対レビュー + 人間承認)で、本 PR がもともと受ける審査と同じである。

**逐行確認の対象**: `authStore.ts`・spec 3 本・依存の差分・宣言と登録の差分。PR 本文に明示する(台帳 H-12 の代替統制 (b) — `docs/development/harness-evaluation.md:628-637`)。

### 移植の決定(移植規則に無い・または規則から外れるもの)

| # | 対象 | 決定 | 根拠 |
| --- | --- | --- | --- |
| A | 状態の項目 | **`teamName: string \| null`・`teamId: string \| null`・`sessionExpired: boolean`・`hasHydrated: boolean`・`authEpoch: number`** を持ち、`isAuthenticated`(`teamName !== null`)を computed で出す。内部に `sessionId`(ログインごとの乱数 — 決定 D)を持つ。**トークン・`authKind`・`username`・`role` は持たない** | P1。トークンは HttpOnly Cookie(H-2・`DM:1678`)。`authKind`・`username` は個人アカウント(Won't)。`role` はチーム管理者ロールなし(要件書 `:1127`)。旧のチームログインは常に `role:'admin'` だった(旧 `api/mock.ts:2872-2879`)ので、役割を落としてもチームアカウントの見え方は変わらない。`teamId` は δ が返すか未決のため null を許す(P2) |
| B | 操作 | **`signIn({ teamName, teamId? })`・`signOut()`・`expireSession()`** の 3 つ。3 つとも先に `queryClient.clear()` を呼び、`authEpoch` を 1 増やす。`expireSession()` は `signOut()` と同じく未認証へ戻し、加えて `sessionExpired = true` を立てる(ログイン画面が「セッションが切れた」と示せるように)。`signIn` で `sessionExpired` を下ろす | 旧 `login`・`logout`(旧 `authStore.ts:32-46`)。旧は 401 でも黙って `logout()` していた(旧 `api/client.ts:65-67`)。失効を利用者へ示せる形にする(4.0-2「黙殺しない」の趣旨 — 要件書 `:165`)。PW 変更後の再ログイン要求(要件書 `:793`)も `expireSession()` で表せる |
| C | 消すもの | 認証が変わるとき(3 操作とタブ間の同期)に消すのは **`queryClient` のキャッシュだけ**。未同期キュー・他の `bb.*` キー・IndexedDB には触れない | 要件書 `:329`(失効して再ログインしても未同期キューを失わない)。旧も `queryClient.clear()` 以外は消していない(旧 `authStore.ts:33,37`)。ログアウトで消すのはクライアントの導出キャッシュでありデータの削除ではない(4.0-2 論理削除 — 要件書 `:163`、6.2 `:1039`) |
| D | 永続化の形 | キー **`bb.auth`** を維持する。値は認証済みのときだけ `{"version":1,"sessionId":…,"teamName":…,"teamId":…}` を書き、未認証では**キーを消す**。`sessionId` は `signIn` ごとに `crypto.randomUUID()` で作る。`sessionExpired`・`authEpoch` は保存しない。**書き込み(`setItem`・`removeItem`)が例外を投げたら**: キーの削除を試み(他のタブを未認証側へ倒す)、値を含まない警告を `console.warn` に出し、メモリ上の状態は進めたうえで**切り離し状態**に入る。切り離し状態では、その時点の保存値の生の文字列を覚え、**メモリを正とする**(決定 G — 保存値へ戻さない)。次に書き込みが成功したら抜ける | Notion の DoD(`bb.auth` の維持)。P1(秘密を書かない)。P3(自前で書く)。`sessionId` は、同じ値の再書き込みでは `storage` イベントが発火しない(HTML Standard の Storage `setItem`)ため、ログインごとに値を必ず変える(計画レビュー 1 回目 P0-2)。`sessionId` は認証情報ではない(サーバーは知らない)。切り離し状態は、保存に失敗したタブが古い保存値(前のチーム)へ戻り、Cookie は新しいチームのまま、という食い違いを防ぐ(計画レビュー 2 回目 P0-2) |
| E | 読めない値 | `bb.auth` が JSON でない、形が違う(旧 zustand の `{state:{token,…},version:0}` を含む)、ストレージへのアクセスが例外を投げる — どの場合も**未認証として始め、例外で止めない**。形の違う値は**消す**(旧形式は平文のトークンを含みうるため) | 旧には検査がない(旧 `authStore.ts:23-50`)。旧形式を移行しない(P1) |
| F | hydration | ストアを作るときに `localStorage` から**同期で**読み、終わったら `hasHydrated = true` にする。U-F13 の guard と U-F6 の送信は `hasHydrated` を待つ。**送信の直前に `syncFromStorage()` を呼ぶ**(別タブの切り替えがイベントより先に送信へ届く窓を狭める — 決定 G。窓を閉じきるものではない) | `porting-rules.md:74`(hydration の完了を明示する)。localStorage は同期なので、生成時に完了する |
| G | タブ間の同期 | **`syncFromStorage()`** を公開する。`bb.auth` を読み直し、**保存値の `sessionId`(未認証なら null)がメモリと違うときだけ** `queryClient.clear()`・`authEpoch` の加算をして状態を差し替える。**切り離し状態(決定 D)では保存値を採らない**: 保存値の生の文字列が切り離した時点から変わっていなければ何もせず、変わっていれば別タブで認証が変わったとみなして**未認証へ倒す**(`expireSession()` と同じ処理)。`window` の `storage` イベントで `key === 'bb.auth'`(または `null` — `localStorage.clear()`)を受けたらこれを呼ぶ。**イベントは別タブへ後から届くので、U-F6 は送信の直前にも `syncFromStorage()` を呼ぶ**(申し送り)。リスナーは setup store の `onScopeDispose` で外す | **旧からの意図的な逸脱(P4)**。旧はタブ間同期を持たない(旧に `addEventListener('storage'` が 0 件)。入れないと、別タブで別チームへ入り直したとき、元のタブの前チームのキャッシュへ新チームの Cookie で取ったデータが入る(research.md 1-3 節)。照合を `sessionId` で行うのは、同名チームの退役と再作成(`docs/design/data-model.md:403`)で `teamName`・`teamId` が同じ値になりうるため(計画レビュー 1 回目 P0-2)。**クライアントだけでは閉じない窓(計画レビュー 2 回目 P0-1)**: 別タブのログインで共有 Cookie が B に変わってから、そのタブが `bb.auth` を書き、元のタブがそれを読むまでの間に送った要求は、元のタブ(A の表示)へ B の応答を返しうる。`storage` イベントも送信前の照合も、この窓を狭めるだけで閉じない。**閉じるには、応答がどのテナントとして認証されたかをクライアントが照合できる契約が要る**。たとえば、要求に期待するチーム ID を付けてサーバーが不一致を拒否する、または応答に認証済みのチーム ID を付けて U-F6 が不一致の応答を表示・キャッシュへ渡さない。これは δ・U-F6 の事項なので申し送る。本単位は照合に使う `teamId` を保持する。書き込みも削除も失敗する環境で他のタブへ伝えられない穴も、同じ契約で閉じる |
| H | 命令的な参照 | component の外(U-F6 の HTTP client)からは `useAuthStore(pinia)` で取る。Pinia の instance は U-F13 が作って export する。本単位は instance を作らない | `porting-rules.md:75` の二択のうち前者を採る。後者(注入できる HTTP client)は U-F6 が併用してよい |
| I | ファイル名 | `stores/authStore.ts`(旧と 1:1)。store の id は `'auth'` | 移植規則 2 節(ディレクトリ・ファイルの 1:1 対応) |
| J | 購読中の画面 | **`authEpoch` を鍵にして、認証が変わったら購読中の画面を作り直す**。配線(`RouterView` の `:key`)は U-F13。本単位は、`useQuery` を使う試験用の部品を `authEpoch` で鍵付けし、A → B の切り替えのあとに A の結果が表示に残らないことを試験で示す | `queryClient.clear()` はキャッシュから query を外すが、購読中の observer は直前の結果を持ち続ける(`@tanstack/query-core` 5.101.4 の `QueryObserver`)。チームを含まないクエリキー(旧 `screens/StartScreen.tsx:47`)を使う画面では、キャッシュが空でも前チームの結果が表示に残る(計画レビュー 1 回目 P0-1)。旧も同じ欠陥を持つ(旧は `clear()` だけ — 旧 `authStore.ts:33,37`)ため、旧からの逸脱として記録する |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **依存 2 件を追加する**。`frontend/package.json` の `dependencies` に `pinia` **4.0.3**・`@vue/devtools-api` **8.2.1** を完全一致の版で足し(`^`・`~` なし)、`pnpm-lock.yaml` を更新する。ソースは触らない。版は 2026-10-10 に `pnpm view` で確認済み。pinia の必須 peer は `vue ^3.5.11`・`@vue/devtools-api ^8.1.5`。依存は `nostics`(vuejs・vercel-labs の保守者)。どちらも install スクリプトは無い。ネットワークが要る(`PITCHLOG_ALLOW_NET=1` — 人間へ報告して了承を得る) | `package.json` の差分が 2 行の追加だけで、版指定が完全一致 / `pnpm install --frozen-lockfile` 成功(`ERR_PNPM_IGNORED_BUILDS` が出ない)/ `pnpm exec vue-tsc --noEmit`・`pnpm exec eslint .`・`pnpm test`・`pnpm build` が green |
| 2 | **`authStore` を作る**。`stores/authStore.ts`(決定 A〜F・H・I・J の `authEpoch`)と `stores/authStore.spec.ts` | spec が 6 節の「単体」「故障系」をすべて含み green / 保存される JSON のキーが `version`・`sessionId`・`teamName`・`teamId` の 4 つだけであることを検査 / `vue-tsc`・`eslint`・`prettier --check .` green |
| 3 | **タブ間の同期を足す**(決定 G)。`authStore.ts` への `syncFromStorage()` と `storage` リスナーの追加、spec | spec: 別タブで別チームの値に変わると `queryClient` が空になり、状態と `authEpoch` が切り替わる / **同じチームへの再ログイン(`sessionId` だけ違う)でも切り替わる** / 同じ値の再通知では消さない / `key === null` で読み直す / 壊れた値なら未認証へ / **イベントが届く前に `syncFromStorage()` を直接呼べば切り替わる** / **書き込みが例外を投げたときキーの削除を試み、`console.warn` の引数に値(チーム名・ID・`sessionId`)が含まれない** / **切り離し状態: A の保存値がある状態で B の `signIn` の書き込みが失敗したとき、削除が成功した場合も失敗した場合も、次の `syncFromStorage()` でメモリが A へ戻らず B のまま。その後に保存値が別の値へ変わると未認証へ倒れる。書き込みが成功すると抜ける** / store の dispose でリスナーが外れる — すべて green |
| 4 | **越境の試験を足す**(NFR-019 (b) の趣旨・決定 C・J)。`stores/authStore.boundary.spec.ts` | 6 節「越境」の全項目が green。① チーム A でキャッシュを積む → `signOut` → チーム B で `signIn` のあと A のキャッシュが無い(同じタブで A → B へ直接 `signIn` する経路も)② **`useQuery` を使う試験用の部品を `authEpoch` で鍵付けしてマウントし、A の結果を表示した状態から B へ切り替える(直接 `signIn` とタブ間の 2 経路)と、A の結果が DOM に残らない** ③ **`fake-indexeddb` に未同期キューに見立てたレコード(所有チームの値を含む)を入れ、`expireSession` → 再 `signIn`、`signOut` → 別チームで `signIn` のあとに同じレコードが同じ内容で残る**。他の `bb.*` キーも残る(要件書 `:329`) |
| 5 | **paths の宣言を足す**(4 節「paths への登録」)。`scripts/core_guard.py` の `AREA_PATH_ADDITIONS` を `{"tenant-isolation": ("frontend/src/stores/authStore*",)}` に置き換え、`tests/test_core_guard.py` の期待値を合わせる。`.claude/core-areas.json` は**このコミットでは触らない** | `uv run pytest tests/test_core_guard.py` が green / `uv run ruff check .`・`uv run ty check` が green / `.claude/core-areas.json` が差分に無い / **`test_area_registration` などの件数・末尾の表明が、登録前(tenant-isolation 82 件)と登録後(83 件・末尾が本単位の 1 件)の両状態を受理する**(ステップ 6 で試験を直さずに緑にするため — 計画レビュー 2 回目 (c)) |
| 6 | **paths を登録する**。`.claude/core-areas.json` の tenant-isolation の paths の末尾へ `frontend/src/stores/authStore*` を足す | `uv run pytest tests/test_core_guard.py` が green(宣言済み追加層と一致)/ `scripts/core_guard.py` の `load_core_areas()` と `matched_paths()` に `frontend/src/stores/authStore.ts`・`authStore.spec.ts`・`authStore.boundary.spec.ts` を当てると 3 件とも検知され、`frontend/src/stores/other.ts` は検知されない(`uv run python -c` で確かめ、コマンドと出力をコミット本文に記録。CLI の `main()` は PR イベントが無いと検査しないため直接呼ばない) |
| 7 | **移植規則と単位定義へ追記し、下流へ申し送る**(Claude)。① `porting-rules.md` に 10 節を新設し、6 節の 3 行に参照を注記する。② `frontend-impl-units/design.md` の U-F2 行へ注記する。③ 下流の Notion カード(U-F3・U-F6・U-F7・U-F13・U-F5・U-F8・U-F10・U-F12・δ TSK-470)へコメントで申し送り、worklog に宛先と日付を記録する | ① 10 節に決定 A〜J のうち規則から外れるもの(A・B・D・E・G・H・J)が載り、4 節と食い違わない ② 注記がある ③ worklog に宛先ごとの記録がある / `uv run python scripts/check_plan_docs_sync.py` が 3 節(正本の反映なし)と矛盾しない |

各ステップ共通: `pnpm exec prettier --check .`・`pnpm exec eslint .`・`pnpm exec vue-tsc --noEmit`・影響する spec が green。

### 申し送りの中身(ステップ 7 ③)

| 宛先 | 内容 |
| --- | --- |
| U-F3 ログイン | ログイン成功時に `signIn({ teamName, teamId })` を呼ぶ。`sessionExpired` を見て失効の案内を出せる。失敗理由からチーム名の存在を推測させない(要件書 `:633`)のは U-F3 の表示側 |
| U-F6 共通 API | **応答のテナントの照合**(決定 G の窓): δ の契約に従い、要求時の `teamId` と応答の認証テナントが違う応答を表示・キャッシュへ渡さない。Cookie の変更が `bb.auth` の更新より先に起きる経路の試験を持つ。401 を受けたら `expireSession()` を呼ぶ。ログイン・PW 変更の呼び出しは除外する(旧 `noAuthRedirect`)。**旧のダウンロード系 7 関数とモックモードは 401 でログアウトしなかった**(旧 `api/endpoints.ts:306-314` ほか・`api/client.ts:52-55`)— 持ち込まない。送信は `hasHydrated` を待つ。**送信の直前に `syncFromStorage()` を呼ぶ**(別タブの切り替えがイベントより先に送信へ届く窓を狭める — 決定 G。窓を閉じきるものではない) |
| U-F7 耐久キュー | U-F2 は未同期キューに触れない。キューのテナントの区別(旧 `ownerTeamId`)を `teamId` から取るなら、δ が teamId を返すかに依存する |
| U-F13 起動入口 | Pinia の instance を作って export する(決定 H)。guard は `hasHydrated` を待ち、`isAuthenticated` で `/login` へ分ける。**`RouterView` に `:key="authEpoch"` を付け、認証が変わったら画面を作り直す**(決定 J)。`requiresTeamAdmin` の meta は作らない |
| U-F5・U-F8・U-F10・U-F12 ほか | 旧の `isTeamAdmin`(`role === 'admin'`)による出力・削除・編集の出し分けは、チームログインでは常に真だった。役割を持たないので、すべて「出す」側で移す |
| δ TSK-470 | **テナントの照合契約**(決定 G の窓 — 計画レビュー 2 回目 P0-1): 要求に期待するチーム ID を付けて不一致を拒否する方式か、応答に認証済みのチーム ID を付ける方式か、どちらかが要る。いずれにせよ**ログイン応答はチーム ID を返す必要がある**。ログイン応答に入れてほしい項目: チームの表示名(正規化前の表記)とチーム ID。起動時にセッションを確かめる経路を作るかどうか。Cookie の `Max-Age` と、クライアントの「認証済みの見込み」の寿命の関係 |

## 5. DoD(受け入れ基準)

Notion TSK-517 の DoD と同期する(括弧内は担当ステップ)。

- [ ] **`bb.auth` のキーを維持し、hydration を待てる形にした**(`hasHydrated` の公開 — 決定 D・F)(2)
- [ ] **クライアント側の認可をサーバー認可の代替にしない**: ストアは表示と送信の前提を持つだけで、認可の判定を持たない。役割を持たない(決定 A)。FR-034 の既定拒否はサーバーが正(要件書 `:641`)(2)
- [ ] **越境の試験を持つ**(NFR-019 (b) の趣旨 — チームの切り替えで前のチームの取得キャッシュも表示も残らない)(4)
- [ ] **自分が担う面を 5 領域すべてに当てた結果を計画書へ書いた**(契約 4 — 4 節「意味上の判定」)
- [ ] **横断要求を破っていない**(契約 5)
  - **論理削除**(4.0-2): 消すのはクライアントの導出キャッシュだけで、データを削除しない — 決定 C
  - **黙殺しない**(4.0-2・NFR-015): 未同期キューを消さない。失効を `sessionExpired` で示せる — 決定 B・C
  - **テナント分離**(NFR-010): 認証が変わるときとタブ間でキャッシュを捨て、購読中の画面を作り直せる鍵を出す — 決定 C・G・J
  - **自動エスケープ**(NFR-023): `teamName` は文字列として持つだけで、`v-html` を使わない
  - **シークレット**(NFR-014・AGENTS.md P0): トークンを持たず、保存しない。ログに認証情報を出さない
  - (2〜4)
- [ ] トークン・`authKind`・`username`・`role` を持ち込んでいない(P1)(2)
- [ ] 依存 2 件が完全一致の版で入っている(1)
- [ ] 移植規則 10 節と単位定義の注記がある。下流と δ への申し送りが Notion に届き、worklog に記録されている(7)
- [ ] **`frontend/src/stores/authStore*` が tenant-isolation の paths に登録されている**(宣言 → 登録の 2 段)(5・6)
- [ ] **敵対レビューと人間の逐行確認を通した**(設計書 6.3 — コア領域)(PR)
- [ ] `pnpm exec vue-tsc --noEmit` / `pnpm test` / `pnpm exec eslint .` / `pnpm exec prettier --check .` / `pnpm build` が green(全ステップ)

## 6. テスト計画

NFR-019 のテスト種別ごとに分ける(すべて Vitest・jsdom。Pinia は spec ごとに `setActivePinia(createPinia())`、`localStorage` は spec ごとに空にする)。

| 種別 | 追加するもの |
| --- | --- |
| 単体(2) | 初期状態(`bb.auth` なし)は未認証・`hasHydrated` は true |
| | `signIn` で認証済みになり、`bb.auth` に 4 キー(`version`・`sessionId`・`teamName`・`teamId`)だけを書く。`signIn` のたびに `sessionId` が変わる |
| | `signOut` でキーを消し未認証へ戻る |
| | `expireSession` で未認証になり `sessionExpired` が立つ。次の `signIn` で下りる |
| | 3 操作とも `queryClient` のキャッシュが空になり、`authEpoch` が 1 増える |
| | 保存済みの値からの復元(別の Pinia で読み直す) |
| | `teamId` 省略時は null |
| 故障系(2) | `bb.auth` が JSON でない / 形が違う / 旧 zustand 形式(`{"state":{"token":"…"},"version":0}`)のときは、未認証で始まり、キーが消える |
| | `localStorage.getItem`・`setItem` が例外を投げても、ストアの生成と操作が例外で止まらない |
| | 保存される JSON に `token` の語が現れない |
| タブ間(3) | `storage` イベントによる切り替え・同じチームへの再ログイン・不変時の非消去・`key === null`・壊れた値・イベント前の `syncFromStorage()`・書き込み失敗と切り離し状態(削除の成功・失敗の両方)・dispose(ステップ 3 の合格条件) |
| 越境(4) | チーム A → B の切り替え(`signOut` 経由と直接 `signIn` の 2 経路)で A のキャッシュが残らない |
| | `authEpoch` で鍵付けした `useQuery` の部品で、A → B(直接 `signIn` とタブ間)のあとに A の結果が DOM に残らない(決定 J) |
| | 未同期キューに見立てた IndexedDB のレコードと他の `bb.*` キーが、失効 → 再ログイン・別チームへの切り替えのあとも同じ内容で残る(要件書 `:329`) |
| 一致性・E2E | 対象なし(ドメイン計算を持たず、画面ではない。ログインから画面遷移までの E2E は U-F3・U-F13 と δ が揃ってから) |

越境試験は NFR-019 (b) の列挙(サーバー経路が対象 — 要件書 `:977`)を直接満たすものではない。根拠は NFR-010(`:887`)と設計書 6.3 の「キャッシュ無効化」(`:400`)である(research.md 2 節)。
