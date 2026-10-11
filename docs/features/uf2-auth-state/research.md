---
feature: uf2-auth-state
type: research
date: 2026-10-10
---

# 調査メモ: U-F2 認証状態(旧 `stores/authStore.ts` の Vue 3 / Pinia 化)

## 問い

U-F2(`docs/features/frontend-impl-units/design.md:309`)は、旧 React 実装の `stores/authStore.ts` を Vue 3 へ移す単位である。計画を立てる前に、次の 4 点を確かめる。

1. 旧の認証状態は何を持ち、誰がどう読み、ログアウトで何を消していたか
2. 要件(FR-033・FR-034 ほか)と、その後の設計決定(認証方式 H-2・正本 data-model.md 8-3)は、旧の形をどこまで許すか
3. 依存先の U-A1(認証)と U-T1(テナント境界)は、develop でどこまで揃っているか
4. 隣の単位(U-F1・U-F3・U-F6・U-F7・U-F13)との境界と、コア領域の判定

調査は 4 本を並行で走らせ、主セッションが要所を原典で裁定した。

- legacy-analyst: 旧の実挙動
- spec-checker: 要件の突合
- decision-tracer: 決定経緯と依存の到達点
- Explore: develop の backend 実装の実測

略記:

- `旧:` = 旧 `Baseball_Scoring` の固定コミット `dd03160044aa5932d3b5a025870c9a5a56d979ef` の `frontend/`。`git show` で取得した。ローカルの作業ツリーはこれより古いので使わない(`../uf1-common-ui/research.md:22`)
- `req:` = `docs/requirements/requirements-pitchlog-2026-07-22.md`
- `PR:` = `docs/features/frontend-skeleton/porting-rules.md`
- `DM:` = `docs/design/data-model.md`
- `BE:` = `backend/src/pitchlog/`

## 結論(要約)

**旧の形は移せない。** 旧は、トークンを `localStorage` の `bb.auth` に平文で置き、`Authorization: Bearer` で送っていた。新しい方式はこれと両立しない。

- 新方式はトークンを `HttpOnly` Cookie で運ぶ。決定は H-2(`docs/features/ua1-team-auth/design.md:18,196-197`)、実装は develop にマージ済み(`BE:api/request_presentation.py:10-13`)。
- 正本は、トークンの提示値を応答本文に出さないと定めている(`DM:1677-1678`)。
- したがって **U-F2 はトークンを持たない**。

**旧の項目の半分は要件が作らないと決めている。** 該当するのは `authKind`('team'|'member')・`username`・`role`('admin'|'scorer')である。

- 個人アカウントは Won't(`req:99`)。PO 裁定 B-1 も「Won't 維持」(`docs/worklog/2026-09-02-decision-sheet-ruling.md:53`)。
- チーム管理者ロールは導入しない(`req:1127`)。
- 旧のチームログインは、常に `role:'admin'` で返っていた(`旧:src/api/mock.ts:2872-2879`)。だから役割を落とすと、チームアカウント利用者の見え方は**旧のチームログインと同じ**になる。

**依存先のログイン API はまだ無い。**

- develop の HTTP ルートは `meta`・`players`・`team_records` の 3 つだけ(`BE:api/app.py:35`)。
- ログイン・ログアウト・セッション確認の経路は δ(TSK-470)が持つ。その計画書は未作成で、応答の形は未決(`docs/features/ua1-auth-app-layer/plan.md:81`)。
- ただし、U-F2 自体は HTTP を呼ばずに作れる。ログインの送信は U-F3、401 の検知は U-F6 が持つからである。
- U-F2 が決めるのは「状態の形」と「状態を変える操作」だけである。そのうえで、δ に返してほしい項目を申し送る。

**ログアウトで消してよいのは取得キャッシュだけである。**

- 失効して再ログインしても、未同期キューを失ってはならない(`req:329`)。
- 旧も、`queryClient.clear()` 以外は消していなかった(`旧:src/stores/authStore.ts:33,37`)。
- 認証が変わったときの `queryClient.clear()` は U-F2 が持つ。これは確定済みである(`../uf1-common-ui/plan.md:69`、`frontend/src/lib/queryClient.ts:10`)。

**コア領域の判定**

- U-F2 はテナント分離(T)に該当する(`../frontend-impl-units/design.md:330,356`)。`frontend/src/stores/` が paths に入っていなくても、意味範囲で該当する。
- pinia を入れると `frontend/package.json`・`pnpm-lock.yaml` を変えるので、機械判定でもコアになる(`.claude/core-areas.json` の sync-protocol・game-state)。
- **依存を別 PR に切っても、ストア本体は非コアにならない。**

## 詳細と典拠

### 1. 旧の実挙動(legacy-analyst・`dd03160`)

#### 1-1. 状態と操作

| 項目 | 旧の値 | 典拠 |
| --- | --- | --- |
| 状態 | `token`・`teamId`・`teamName`・`authKind`・`username`・`role` | `旧:src/stores/authStore.ts:5-21` |
| 初期値 / logout 後 | `authKind:'team'`・`role:'admin'`、ほかは null(両者は同じ) | 同 `:26-31,38-45` |
| login | `queryClient.clear()` の後に 6 項目を設定 | 同 `:32-35` |
| logout | `queryClient.clear()` の後に初期値へ戻す | 同 `:36-46` |
| 永続化 | `persist(…, { name: 'bb.auth' })` のみ。version・partialize・onRehydrateStorage はなく、6 項目すべてが保存される | 同 `:23-50` |
| zustand の版 | 指定は `^5.0.0`。実際に入る版は不明(ロックファイルは照合範囲外) | `旧:package.json:19` |
| 復元前の初期描画 | 対策なし。RequireAuth が token を同期的に読む。同期ストレージなら描画前に復元が終わる、というライブラリの挙動に頼っている **[推論]** | `旧:src/App.tsx:25-29` |
| 試験 | authStore にも 401 処理にも試験なし | `旧:package.json:9`、ファイル一覧 |

#### 1-2. 利用側(21 ファイル)

**命令的な参照(`getState()`)**

- `api/client.ts` は token を Bearer ヘッダに付ける(`旧:src/api/client.ts:56-59`)。
- 401 を受けると、`noAuthRedirect` が付いていなければ `logout()` を呼ぶ(`:65-67`)。
- モックモードでは 401 処理に届かない(`:52-55`)。
- `combinedReports.ts` も同じ形である(`旧:src/api/combinedReports.ts:51-60`)。
- ダウンロード系 7 関数は、**401 でもログアウトしない**(`旧:src/api/endpoints.ts:306-314` ほか 6 箇所)。

**購読(selector)** の内訳:

| 読む項目 | 使っている場所 | 用途 |
| --- | --- | --- |
| token | RequireAuth・HelpScreen | 認証の有無で入口と戻り先を分ける |
| teamId | 7 画面 | `ownerTeamId` として同期キューの絞り込みとクエリキーに使う |
| teamName | 4 箇所 | 表示 |
| role | 11 箇所 | `isTeamAdmin` として出力・削除・編集の出し分け、`/imports` の保護(`旧:src/App.tsx:114-123`) |
| authKind・username | SettingsSheet・TeamMembersContent・StartScreen | 個人アカウントの表示 |

**logout の呼び出し元は 4 系統ある。**

- StartScreen のボタン(`旧:src/screens/StartScreen.tsx:121`)
- PW 変更の成功後(`旧:src/components/settings/SettingsSheet.tsx:89-97`)
- client.ts の 401 処理
- combinedReports.ts の 401 処理

**login の呼び出し元は LoginScreen だけである。** 応答の 6 項目をそのまま渡している(`旧:src/screens/LoginScreen.tsx:73-84`)。応答の型は `旧:src/api/types.ts:8-15`。

#### 1-3. ログアウト・再ログインで残るもの

| 残るもの | 典拠 | 備考 |
| --- | --- | --- |
| `bb.sync`(未同期キュー。IndexedDB) | `旧:src/stores/syncStore.ts:29-39,234-244` | 項目は `ownerTeamId` だけを持つ。送信と表示は「今の teamId と一致するか」で絞る(`旧:src/screens/GameScreen.tsx:571-573,1275`) |
| `bb.game-kind-settings` | `旧:src/stores/gameKindSettingsStore.ts:25,137-142` | チームごとに分けて保存 |
| `bb.input-settings`・`bb.keyboard-shortcuts`・端末 ID | `旧:src/stores/inputSettingsStore.ts:28`、`shortcutStore.ts:16`、`lib/captureMetadata.ts:20-23` | 端末単位の設定 |

- **チームを含まないクエリキーがある**(例: `['games', 4]`、`旧:src/screens/StartScreen.tsx:47`)。テナント間の分離は、login・logout 時の `clear()` だけに頼っている。
- **タブ間の同期はない**(`addEventListener('storage'…)` は 0 件)。**[推論]** 別タブで別チームへ入り直すと、元のタブには前のチームのクエリキャッシュが残る。その状態で再取得すると、新しい Cookie で取った別チームのデータが同じキーへ入る。

### 2. 要件と設計決定(spec-checker・decision-tracer。要所は主セッションが原典で確認)

| 項目 | 内容 | 典拠 | U-F2 への含意 |
| --- | --- | --- | --- |
| FR-033 | チーム名と PW でログインし、操作は自チームに限る。認証はアプリの 1 層だけ。レート制限中も既存セッションは有効 | `req:628-635` | 保持するのは 1 テナントの主体。他人のロックを理由にセッションを捨てない |
| 個人アカウント | Won't | `req:99`、`req:1128`、裁定 B-1 | `authKind`・`username` を持ち込まない |
| チーム管理者ロール | 導入しない | `req:1127`、`DM:1556,1579-1585` | `role` と `requiresTeamAdmin`(`PR:71`)を持ち込まない |
| NFR-011 | 期限は既定 7 日のスライディング。PW 変更で全経路を即時失効 | `req:893`、`DM:1675` | 期限の判定はサーバー。クライアントは失効応答を受けて状態を捨てる |
| 提示形式 | トークン行 ID と HMAC 署名の組。ログ・応答本文・URL に出さない | `DM:1677-1678` | クライアントはトークンを見ない・持たない |
| H-2 | Cookie(`HttpOnly`・`Secure`・`SameSite=Strict`)と CSRF 対策 | `../ua1-team-auth/design.md:18,196-197` | 同上 |
| FR-035 / FR-036 | 無効化と PW 変更で即時失効。PW 変更は実行した端末も再ログイン | `req:775,793`、`DM:1702` | 失効応答で状態とクエリキャッシュを捨てる経路が要る |
| FR-012 | 失効して再ログインしても、未同期キューは失われず同期が再開される | `req:329` | **キューに触れない**。旧も触れていない |
| FR-034 | 直叩きは 404。判定はすべてサーバー | `req:641-642` | クライアントの状態は表示の出し分けにしか使えない(Notion の DoD「サーバー認可の代替にしない」) |
| NFR-010 / NFR-019 (b) | 分離は初日から全機能に適用。越境テストの列挙はサーバー経路が対象 | `req:885-889,977` | (b) が U-F2 に直接課す組合せはない **[推論]**。U-F2 の越境試験は「チーム A → B の切り替えで A の痕跡が残らない」形で置く |
| NFR-023 | チーム名は利用者入力。生 HTML に挿入しない | `req:1009-1013` | teamName を表示する側の規律。U-F2 は文字列として持つだけ |
| 設計書 6.3 | テナント分離の意味範囲は「キャッシュ無効化」を含む | `docs/development/dev-harness-design-2026-08-07.md:400` | **これがクライアントのクエリキャッシュを含むかの明文はない**。U-F1 の計画はそう読んで U-F2 に割り当てた(`../uf1-common-ui/research.md:42,188`) |
| 4.0 節の横断要求 | 物理削除しない・黙殺しない・正本は DB | `req:162-167` | ログアウトで消すのはクライアントの導出キャッシュでありデータの削除ではない、と明記する。キューを消さない |

**`PR:` の規則と後の決定の食い違い**

`PR:71,74,75` は次の 3 点を定めている。

- token が無ければ `/login` へ移す
- `bb.auth` に永続化する
- auth header を注入する

これらは 2026-08-16〜17 に起草された。その後の H-2(2026-10-03)・`DM:1678`・`req:1127` とすり合わせた決定は見つかっていない(decision-tracer)。

I-28 は、approved の要件書や台帳が既決にした改善を逐語移植より優先する、と定めている。判断が割れた場合は計画書ゲートで PO へ上げる(`docs/improvements-from-baseball-scoring.md:241-242`)。

### 3. 依存先の到達点(Explore・decision-tracer)

| 段 | 状態 | 典拠 |
| --- | --- | --- |
| α(正本 data-model v0.4) | approved | `../ua1-auth-app-layer/plan.md:23` |
| β(DB 層)| DB 関数 `authn.login(team_name, password) → uuid` がある。Python からの呼び出しは 0 件 | `contracts/authz/product/function-bodies/functions/FUNCTION:authn:login(text, text).sql:4-5,68-75` |
| γ(署名と検証) | develop にある。`TokenPresentation.encode`・`verify_tenant_id`・`logout_token`(HTTP からは未使用) | `BE:authz/token_presentation.py:25-31`、`BE:authz/verified_tenant.py:24,75,108` |
| U-M1 のリクエスト認証(#95 ステップ 8) | develop にマージ済み。Cookie `__Host-pitchlog_token`、GET・HEAD・OPTIONS 以外には `X-Pitchlog-Request: 1` と Origin 照合を要求 | `BE:api/request_presentation.py:10-13,86-104`、`../um1-player-roster-opponent/plan.md:124` |
| δ(ログイン・ログアウト・PW 変更の HTTP 入口。TSK-470) | **計画書なし**。応答の形・セッション確認の経路・Cookie の Max-Age は未決 | `../ua1-auth-app-layer/plan.md:81`、`../um1-player-roster-opponent/design.md:232` |

**401 と 403**

| 状況 | 応答 | 典拠 |
| --- | --- | --- |
| Cookie なし・検証失敗(期限切れ・失効を含む) | 401 | `BE:api/errors.py:19,126-129`、`BE:api/tenant_access.py:22-23` |
| CSRF 違反 | 403 | 同上 |
| 認可拒否 | 404 へ写す | `BE:api/errors.py:100-102` |

**[推論]** クライアントの判断は「401 なら未認証へ」で足りる。403 は設定の不備で、認証状態とは関係しない。

**サーバーが返すチーム情報**

- `verify_tenant_id` はテナント UUID をサーバー内部でだけ返す(`../um1-player-roster-opponent/design.md:245`)。
- クライアントへ teamId を返すかどうかは未決。
- 「自分は誰か」を返す API は存在しない。

### 4. 境界(decision-tracer)

| 単位 | U-F2 との境界 | 典拠 |
| --- | --- | --- |
| U-F1 | `queryClient` の生成と既定値まで(develop にある) | `../uf1-common-ui/plan.md:51,112` |
| U-F3 | ログイン入力と、情報を漏らさない失敗表示。ログインに成功したら U-F2 の操作を呼ぶ | `../frontend-impl-units/design.md:310,472` |
| U-F6 | `api/client.ts`(Cookie を付けた送信・CSRF ヘッダ・401 の検知)。401 で U-F2 の何を呼ぶかは未決 | `../frontend-impl-units/design.md:313`、`PR:75` |
| U-F7 | 未同期キュー。U-F2 はキューに触れない | `../frontend-impl-units/design.md:314`、`req:329` |
| U-F13 | `main.ts`・`App.vue`(pinia と vue-query の install)と route guard。U-F2 は hydration の完了を公開し、guard がそれを待つ | `../frontend-impl-units/design.md:320`、`PR:73-74` |

### 5. 依存と版

- pinia はまだ `frontend/package.json` に無い(現在の dependencies は `@tanstack/vue-query`・`lucide-vue-next`・`vue` の 3 つ)。
- 版 4.0.3 は frontend-skeleton が「版だけ先に決めた」もので、承認ではない(`PR:81,86-87`、`../frontend-skeleton/plan.md:123`)。U-F1 は自分の 2 件だけ測り直し、pinia は測り直していない(`../uf1-common-ui/plan.md:56`)。
- 永続化をプラグイン(pinia-plugin-persistedstate 等)で行うか自前で書くかの決定はない(docs 全体で 0 件)。

### 6. コア領域

- `frontend/src/stores/` に当たる paths は無い(`.claude/core-areas.json`)。
- U-F2 は意味範囲で T に該当する(`../frontend-impl-units/design.md:330,356`)。
- 判定に迷ったら含む側に倒す(`docs/development/dev-harness-design-2026-08-07.md:403`)。
- 意味範囲で該当し paths に当たらない型は、台帳 H-12 の残余②で 4 件再発している。各タスクは計画 4 節に代替統制 4 点を書いて運用した(`docs/development/harness-evaluation.md:628-637`)。
- `/pr` は paths でしか検知しないので(`.claude/skills/pr/SKILL.md:44`)、本単位も**コア領域の 2 項目を PR 本文に手動で有効化する**必要がある。

## 未解決・申し送り

### 計画書ゲートで PO に上げる分岐(/plan の入力)

1. **状態の形**: トークン・`authKind`・`username`・`role` を落とす
   - 根拠は H-2・`DM:1678`・`req:99,1127`。
   - `PR:71` の `requiresTeamAdmin` と、旧の `isTeamAdmin` による出し分けは、移植規則の側で「持ち込まない」と扱う必要がある。
   - porting-rules.md は正本ではない。本単位の計画で 6 節の該当行を改めるか、注記で済ませるかを決める。
2. **`bb.auth` に何を残すか**
   - 秘密でない項目(認証済みの見込み・チームの表示名、δ が返すならチーム ID)だけを保存する。
   - キー名は維持する(Notion の DoD)。
   - 旧の形式(`{state:{token,…},version:0}`)の値が残っていたら、読み捨てる(移行しない)。
3. **δ を待たずに作るか**
   - U-F2 は HTTP を持たないので作れる。
   - ただし「起動時にログイン済みかを確かめる経路」が無い。**[推論]** 当面は旧と同じ扱いにする。保存の見込みで認証済みとみなし、最初の 401 で未認証へ戻す。
   - δ への申し送り(ログイン応答に入れてほしい項目、セッション確認の経路の要否)を計画に含める。
4. **pinia を同じ PR に入れる**: ストア本体もコアなので、別 PR に切るとコア PR が 2 本になる。版は導入時に測り直す。
5. **永続化を自前で書くか、プラグインを足すか**: 保存する項目は少ない。**[推論]** 自前で書けば依存が 1 つで済む。
6. **タブ間の同期**: 旧に無い。
   - storage イベントで `bb.auth` の変化を受け、クエリキャッシュを捨てて状態を読み直す案がある。
   - 上の 1-3 の「別タブで別チームへ入り直す」経路を塞ぐ。
   - 旧からの逸脱になる。

### 計画書で決めること(PO 裁定までは要らない見込み)

- 操作の名前と引数(例: ログイン成功の反映・ログアウト・失効の反映)。401 由来のときに区別が要るか(PW 変更後の再ログイン要求)。
- hydration の完了の公開の仕方(`PR:74`。localStorage は同期なので、生成時に完了する形で足りるか)。
- 壊れた `bb.auth`(JSON でない・形が違う)のときの扱い。未認証として始め、例外で止めない。
- 試験の範囲(NFR-019)。
  - 状態の遷移と、保存される JSON に秘密が無いこと
  - ログイン・ログアウトでクエリキャッシュを捨てること
  - 他の `bb.*` キーと IndexedDB に触れないこと
  - チーム A → B の切り替えで A の痕跡が残らないこと
  - 壊れた値からの復帰

### 下流への申し送り

- **U-F6**: 401 を受けたら U-F2 の失効反映を呼ぶ。旧のダウンロード系 7 関数とモックモードは 401 でログアウトしない穴があり(1-2 節)、これを持ち込まない。`noAuthRedirect` に当たる除外(ログイン・PW 変更の呼び出し)が要る。
- **U-F3**: ログイン成功時に U-F2 の操作を呼ぶ。失敗理由からチーム名の存在を推測させない(`req:633`)のは U-F3 の表示側。
- **U-F13**: route guard は U-F2 の hydration 完了を待つ。`requiresTeamAdmin` の meta は作らない(上の分岐 1 が採られた場合)。
- **U-F5・U-F8・U-F10・U-F12 ほか**: 旧の `isTeamAdmin` による出し分けは、チームログインでは常に真だった。役割を落とすと、すべて「出す」側になる。
- **δ(TSK-470)**: ログイン応答に入れてほしい項目(チームの表示名・チーム ID の要否)と、起動時のセッション確認経路の要否。
