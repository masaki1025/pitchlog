---
feature: uf6-api-contract
type: research
date: 2026-10-11
---

# 調査メモ: U-F6 共通 API・形式契約(旧 api 層の Vue / TypeScript 化)

## 問い

U-F6(`docs/features/frontend-impl-units/design.md:313`)は、旧 React 実装の次のファイルを持つ単位である。

- `api/client.ts`・`endpoints.ts`・`types.ts`・`mock.ts`
- `lib/mockRules.ts`・`mockTeamManagement*`・`format.ts`

5 領域すべてに該当すると判定されている(同 `:334,349`)。計画を立てる前に、次の 6 点を確かめる。

1. 旧の api 層は何を持ち、どう動いていたか
2. それを当てる相手(develop の backend と既存の frontend 資産)はどこまであるか
3. 要件と設計決定は、旧の形をどこまで許すか(特にモックモードと NFR-018)
4. 隣の単位・タスクとの境界はどこか
   - U-F2・U-F7・U-F9
   - δ = TSK-470
   - 同期の入口 PR = TSK-506
   - API 契約の正本 = TSK-346
5. ファイル分割の義務(Notion の DoD「混在ファイルを分割するか、分割しない理由を書く」)にどう答えるか
6. コア領域の判定

調査は 4 本を並行させた(legacy-analyst・spec-checker・decision-tracer・Explore)。旧の固定コミット `dd03160` の 26 ファイルと import の一覧は、主セッションが書き出して渡した。要所は主セッションが原典で確かめた。

略記:

- `旧:` = 旧 `Baseball_Scoring` の固定コミット `dd03160044aa5932d3b5a025870c9a5a56d979ef` の `frontend/src/`
- `req:` = `docs/requirements/requirements-pitchlog-2026-07-22.md`
- `BE:` = `backend/src/pitchlog/`
- `PR:` = `docs/features/frontend-skeleton/porting-rules.md`

## 結論(要約)

**旧の `endpoints.ts`・`types.ts` は、いまの backend とほとんど噛み合わない。**

- 旧は `/api` 接頭辞付きの 74 関数・147 型である。根拠は旧 `api/endpoints.ts`・`api/types.ts` で、型の典拠は旧の `docs/api_contract_v1.md`(旧 `api/types.ts:1`)。
- develop の backend の業務ルートは 8 本しかない(選手 4・対戦相手 4 — `BE:api/routers/players.py:105-201`・`team_records.py:82-179`)。経路(`/team-records`)、ページング(カーソル)、DTO、エラー封筒(`{"error":{"message","fields"}}`)のどれも旧と違う。
- 2026-08-16 の PO 裁定は「API 契約を踏襲」(`docs/worklog/2026-08-16-frontend-skeleton.md:76-77`)としていた。しかし U-M1 は旧の経路を参照せずに新しい形を作っている。**両者をすり合わせた決定は見つからない。**

**旧の `mock.ts`(4372 行)はドメイン計算を自前で持つ。**

- 持っている計算: カウントの昇格・アウトと攻守交代・走者の進塁・得点・投球回の換算・自責点と責任投手の再構成・過去修正の再計算(旧 `api/mock.ts:1764-1843,2157-2339,1976-2104,2664-2777`)。
- そのまま移すと NFR-018(`req:928,936` — 人手の実装は 1 系統)に当たる。単位設計も「模擬計算は独立した正解実装にしない」と定めている(`frontend-impl-units/design.md:313,360`)。
- **モックモードを移すかどうかは、要件書・台帳・PO 裁定のどこにも決まっていない**(未決 — I-28 により計画書ゲートで PO に上げる。`docs/improvements-from-baseball-scoring.md:242`)。

**同期の通信層は U-F6 の担当ではない方向で決まっている。**

- wire 形式は TSK-331 で確定し、codec と通信層は「入口 PR」(TSK-506)の担当である(`docs/features/sync-wire-schema/design.md:362,399`)。
- 一方で単位定義は、べき等キー・世代の送受信型を U-F6 にも割り当てている(`frontend-impl-units/design.md:442,445`)。**この重なりを解いた記録は無い。**

**`format.ts` は移植済み。**

- 骨格タスクで逐語移植している(`PR:123,163`、`frontend/src/lib/format.ts`)。
- data-migration の paths にも入っている(`.claude/core-areas.json:546`)。

**U-F6 が今すぐ作れる実体は、次の 2 つに絞られる。**

- **共通 HTTP クライアント**: Cookie 送出・CSRF ヘッダ・エラー封筒の解釈・401 → `expireSession()`・送信前の `syncFromStorage()`・ダウンロード。
- **いま在る 8 経路の型と呼び出し**。

旧の残りの 66 関数は、相手の backend がまだ無い。**どの単位がいつ持つかを決める必要がある。**

## 詳細と典拠

### 1. 旧の api 層(legacy-analyst — 書き出した `dd03160` の写しから)

#### 1-1. `client.ts`(93 行)

| 項目 | 旧の事実 | 典拠 |
| --- | --- | --- |
| 形 | `api<T>(method, path, body?, { noAuthRedirect? }): Promise<T>`。送り先は `/api${path}` | 旧 `api/client.ts:42-51,60` |
| ヘッダ | body があれば `Content-Type: application/json`、token があれば `Authorization: Bearer`。べき等キーや端末 ID は付けない | `:56-59` |
| 応答 | JSON なら `res.json()`、そうでなければ text。**実行時の検証はしない** | `:68-73,92` |
| エラー | `ApiError{status, detail, retryAfterMs?}`。FastAPI の `{detail}` を読む。`Retry-After` は秒と HTTP-date の両方を解釈する | `:8-33,74-90` |
| 再送の判定 | `isRetryableError`: 500 以上とネットワーク断(TypeError)。`lib/syncPolicy.ts` が使う | `:35-40` |
| 401 | `noAuthRedirect` でなければ `logout()` を呼んでから投げる。対象外は login・register・changePassword、および LoginScreen からの getTeams | `:65-67`、`api/endpoints.ts:81,89,97,111-112` |
| モック | `VITE_MOCK==='1' \|\| MODE==='mock'` なら `await import('./mock')` に切り替える。**401 処理を通らない** | `:4-6,52-55` |

#### 1-2. `endpoints.ts`(779 行・74 関数)

| まとまり | 関数の数 | 主な領域([推論]) |
| --- | --- | --- |
| 認証(login・register・password・me・members) | 7 | T |
| チーム・選手・スタメン | 10 | T |
| 比較グループ | 8 | T(分析は T と G の混在) |
| 分析・カルテ・帳票 | 8 | G・出力 |
| 試合(一覧・作成・状態・スコア表・自責点・メモ・クロック・終了・補正・タイブレーク・交代・臨時代走) | 27 | G・R |
| プレイ(確定・取消・修正・過去修正・交代修正・一覧・CSV) | 15 | G・S・R・D |
| CSV 取り込み・書き出し | 3 | D |

- 典拠は旧 `api/endpoints.ts:76-779`。関数ごとの表は legacy-analyst の報告にある。
- `confirmPlay` が未同期キューの再送経路でもある(旧 `screens/GameScreen.tsx:1294`)。
- ダウンロード系 7 関数は fetch を直接呼ぶ。Blob とファイル名を取るためで(旧 `api/endpoints.ts:710`)、**401 でもログアウトしない**。うち 1 関数は ApiError でなく素の Error を投げる(`:720`)。
- 呼び出し元が写しからは確かめられない関数が 13 ある。中身を書き出していないファイル(`components/game/*Substitution*`・`AnalysisExportSheet`・`CsvImportScreen`)から import されている。

#### 1-3. `types.ts`(1491 行・147 型)

- 型が領域をまたいで混ざっている。
  - `PlayInput`: G・S・R(`expected_revision`・`client_key`・`client_event_id`・`device_id`)— 旧 `api/types.ts:1058-1088`
  - `PlayConfirmResponse`: G・S・R — `:1411`
  - `GameState`: G・R(`write_revision`)— `:962`
  - `ApiErrorDetail`: 全領域 — `:1476`
- `LoginResponse` は `auth_kind`・`role` を持つ(`:8`)。U-F2 で落とした項目である。

#### 1-4. `mock.ts`(4372 行)・`lib/mockRules.ts`・`lib/mockTeamManagement*`

- 経路の振り分けを if で並べている(旧 `api/mock.ts:2826-4371`)。データはモジュール内のメモリだけに持つ(`:91-124,400-407,1054-1067`)。
- **ドメイン計算を自前で持つ**(上の結論の行番号)。コメントは「実APIと同様に」と繰り返しており、サーバーの規則を手で写したものである(`:2117-2119,2132-2136`)。
- 依存している先:
  - `lib/playRules`(実画面の GameScreen も使う — `screens/GameScreen.tsx:60`)
  - `lib/scoringReview`(自責点の判定表の独自実装。NFR-018 違反と判定済み — `docs/features/legacy-frontend-coverage/research.md:163`)
- U-F6 の外の単位の経路も実装している。`/team-management/*`(`:2966-3119`)と `/stats/realtime`(`:3846`)。
- モックの CSV は 54 列で、88 列ではない(`:1070-1125,2500-2506`)。
- `lib/mockRules.ts` が持つのは、投球数・先頭走者・併殺走者・打球種別の導出と、client_key の索引である。`lib/mockTeamManagement.ts` が持つのは、配色・背番号の衝突・認証主体の妥当性である。どちらも `mock.ts` からしか読まれない。
- 本番ビルドにモックが入るかは不明である。`dev:mock` は `vite --mode mock`、`build` はモード指定なし(旧 `package.json:8,10`)。

#### 1-5. `format.ts`

- 中身は `isoToSlashDate`・`todayIso`・`cx`(旧 `lib/format.ts:1-16`)。
- **現行では逐語移植済み**(`frontend/src/lib/format.ts`・`PR:123,163`)。

### 2. 噛み合わせる相手(Explore・decision-tracer)

#### 2-1. backend(develop)

| 項目 | 実体 | 典拠 |
| --- | --- | --- |
| 業務ルート | `POST/GET /players`、`GET/PATCH /players/{id}`、`POST/GET /team-records`、`PATCH/DELETE /team-records/{id}`。ほかに `/health`・`/version`。**`/api` 接頭辞なし** | `BE:api/app.py:13,34-35`、`backend/tests/test_api_conventions.py:144-159` |
| DTO | `TeamRecordRead{id,kind,name,hidden_at}`、`PlayerRead{id,team_record_id,name,throws,bats,uniform_number,roster_status_key,roster_label_key,hidden_at}` ほか。すべて `extra="forbid"` | `BE:api/schemas/roster.py:19-122`、`base.py:9-12` |
| ページング | カーソル方式。要求は `{limit(1〜200・必須), cursor}`、応答は `Page{items, next_cursor}` | `base.py:35-49`、`roster.py:125-138` |
| エラー封筒 | `{"error":{"message", "fields"?:[{"location"}]}}`。`code` は持たない | `base.py:52-71`、`errors.py:53-57` |
| 状態と文言 | 401「認証情報がありません」/ 403(CSRF)「要求を確認できません」/ 404(403 から写したものを含む)「対象が見つかりません」/ 409(削除不可)/ 422「入力に誤りがあります」/ 500 | `errors.py:15-26,74-160` |
| 認証と CSRF | Cookie `__Host-pitchlog_token`。GET・HEAD・OPTIONS 以外は `X-Pitchlog-Request: 1` と `Origin` の許可リスト照合 | `BE:api/request_presentation.py:10-13,86-104` |
| ログイン | HTTP ルートは**無い**(δ TSK-470 が未着手。応答の形は未決) | `docs/features/uf2-auth-state/research.md` 3 節 |
| OpenAPI | 生成物は**コミットしない**ことが既決。置き場は TSK-346 へ送られている。型の生成器も無い | `docs/features/u00-api-shell/plan.md:67`、`docs/features/sync-wire-schema/design.md:427` |
| 規約の性格 | U-M1・U-00・U-01 の規約は暫定の層 (B)。**TSK-346 が別の形を定めたらそちらが正** | `docs/features/um1-player-roster-opponent/design.md:14,212,239`、`u00-api-shell/design.md:58-61,95` |

#### 2-2. frontend(develop)

| 項目 | 実体 | 典拠 |
| --- | --- | --- |
| `src/api/`・`lib/generated/` | `.gitkeep` だけ | 実測 |
| fetch | 製品コードに 0 件 | 実測 |
| `lib/sync/`(61 ファイル) | 通信非依存の camelCase DTO とパーサだけ(`ackEnvelope.ts`・`p3Result.ts`・`requestBoundary.ts`・`syncEvent.ts` ほか)。**べき等キー(D5)を生成するコードは無い** | `frontend/src/lib/sync/*`、`docs/design/sync-protocol.md:35` |
| `stores/authStore.ts` | U-F2。`expireSession()`・`syncFromStorage()`・`hasHydrated`・`teamId`(null 可) | `docs/features/uf2-auth-state/plan.md` 4 節 |
| vite の proxy | `/api` を接頭辞を残したまま `:8800` へ転送する。**backend は `/api` 無しで待つので噛み合わない**(`/api/health` が 404 になることは記録済み) | `frontend/vite.config.ts:506-511`、`docs/features/onboarding-approval/plan.md:55` |
| CSP | ビルド時に `connect-src 'self'` | `vite.config.ts:46,461-467` |
| モックの仕組み | 無い(`import.meta.env` の使用は 0 件・msw なし) | 実測 |

### 3. 要件と決定(spec-checker・decision-tracer)

| 項目 | 内容 | 典拠 | U-F6 への含意 |
| --- | --- | --- | --- |
| FR-012 | べき等キー・連番・同じキーでの再送。内容拒否と記録権拒否を区別する。失効しても未同期キューは失わない | `req:316-329` | 採番・付与はキュー側(U-F7・`lib/sync`)が持つ **[推論]**。U-F6 は変えずに送るだけで、401 でキューに触れない |
| FR-013 | 世代を送出する。旧世代は退避する | `req:337-344` | 旧世代拒否を受けたものを現世代へ付け替えて自動再送しない **[推論]** |
| FR-007・FR-028 | 楽観ロック。後発が先発を黙って消さない | `req:266,580` | 共通クライアントで 409 を自動再試行・上書きしない **[推論]** |
| FR-034 | 直叩きは 404。理由コードを返さない | `req:641-642,657` | 403 と 404 を区別する分岐を持ち込まない(I-2 — 台帳 `:39`) |
| FR-041 | 上限超過は要求全体を 400 で拒否する(切り捨てない) | `req:546,666` | 400 の後に集合を黙って詰めて再送しない **[推論]** |
| 4.0-2・NFR-015 | 失敗を黙殺しない | `req:165,913` | エラーを握りつぶさない(ダウンロード系も含む)。障害注入の試験が要る |
| NFR-005・I-1 | 一覧はページングし、表示分だけ取得する | `req:857`、台帳 `:29` | 一覧の呼び出しはカーソルを前提にする |
| NFR-013 | HTTPS | `req:903` | ベース URL に `http://` を固定しない(`__Host-` Cookie は Secure が前提) |
| NFR-018 | ドメイン計算は 1 系統。経路別のコピー実装を作らない。例外表は `COURSE_COORDINATE_SIZE` の 1 行だけ | `req:928-959` | **モックの独自計算は当たる可能性が高い [推論]** |
| NFR-023 | 利用者入力を構造として解釈させない | `req:1011` | 型変換や format で HTML を組み立てない |
| モックモード | 要件書・台帳・裁定のどこにも無い(未決)。接し得るのは Won't の「完全オフライン記録」(`req:101`)・「自責点」(`req:102`)、正本は DB の 1 系統(`req:167`)、NFR-018 | spec-checker の報告 | **計画書ゲートで PO に上げる** |
| 利用者向け CSV 取り込み | 要件の条文が無い(裁定 A-11 で「要件化へ送る」のまま未反映) | `docs/worklog/2026-09-02-decision-sheet-ruling.md:72,121` | U-F6 の範囲から外す案 **[推論]** |
| ファイル分割 | 設計書 6.3 の規則 ④ は「paths を狭めるなら先に分割する」という順序の規則で、分割を課すものではない | `docs/development/dev-harness-design-2026-08-07.md:404` | Notion の DoD「分割するか、分割しない理由を書く」に計画書で答える |
| 同期の入口 | wire 形式は確定(snake_case・`POST /games/{id}/sync/events` 等)。codec と通信層は TSK-506 の担当 | `sync-wire-schema/design.md:48-50,163-164,362,399` | U-F6 との分担を決める必要がある(未決) |
| API 契約の正本(TSK-346) | 未着手 | `sync-wire-schema/research.md:120` | U-F6 の型は暫定の層 (B) に依拠する |
| `GET /auth/session` | リポジトリに記録なし(δ への申し送りは U-F2 から) | `uf2-auth-state/plan.md:76,177` | 未決 |

### 4. コア領域

- `frontend/src/api/*` は**どの paths にも当たらない**。`lib/mock*` も当たらない(ファイルも無い)。
- `frontend/src/lib/format.ts` は data-migration に入っている(`.claude/core-areas.json:546`)。
- `frontend/vite.config.ts`・`package.json` は sync-protocol・game-state に入っている(`:112,178,274,276`)。proxy や依存を変えると機械判定でコアになる。
- 意味判定は 5 領域すべてに該当する(`frontend-impl-units/design.md:334`)。根拠は「`endpoints.ts`・`types.ts`・`mock.ts` に 4 つの面が混在する」こと(`:349`)である。
  - 混在のもとは、旧のファイルをそのまま移すことにある。
  - **持つ範囲を変えれば、判定も変わる**(計画書で当て直す)。

## 未解決・申し送り

### 計画書ゲートで PO に上げる分岐(/plan の入力)

1. **API の形の正をどちらに置くか**
   - 候補は 2 つある。
     - 旧の契約(2026-08-16 裁定の「API 契約を踏襲」)
     - develop の backend(U-M1 が作った形・TSK-346 待ちの暫定の層 (B))
   - **[推論] フロントは実在する backend に当てるしかない**。旧の 74 関数のうち相手が在るのは選手・対戦相手の範囲だけで、それも形が違う。
   - これに伴い、旧の残りの関数と型を誰が持つかも決める。
     - 案 a: 各画面単位が、backend の単位の着地に合わせて足す
     - 案 b: U-F6 が後から順次足す
   - 単位定義(`design.md:313` — U-F6 が `endpoints.ts`・`types.ts` を持つ)からの変更になる。
2. **モックモードを移すか**
   - 移すなら、ドメイン計算を持たない形に限る(NFR-018)。本番ビルドからは外す。
   - **[推論] 計算を抜いたモックでは画面の挙動を確かめられないので、移さない方が筋**。
3. **同期の通信層と U-F6 の分担**
   - TSK-506(入口 PR)が codec と通信層を持つ。
   - U-F6 は共通 HTTP クライアント(Cookie・CSRF・エラー封筒・401)を提供し、TSK-506 がそれを使う形が候補 **[推論]**。
4. **`/api` 接頭辞**
   - 旧は `/api${path}`、backend は接頭辞なし、vite の proxy は `/api` を残したまま転送する。
   - 候補は 2 つある。
     - (a) クライアントは接頭辞なしで送り、proxy を直す
     - (b) `/api` を付けて送り、proxy で外す
   - `vite.config.ts` はコア領域の paths に当たる。本番の配信構成(同一オリジンか)は ops で確かめる必要がある。
5. **テナント照合の窓**(U-F2 の決定 G)
   - 照合方式は δ の契約次第で、未決。
   - U-F6 はそれを差し込める口だけ作るか、δ を待つかを決める。

### 計画書で決めること(PO 裁定までは要らない見込み)

- 共通クライアントの形を決める。
  - `credentials: 'include'`
  - GET 以外での `X-Pitchlog-Request: 1`
  - エラー封筒 → `ApiError{status, message, fields}` への写像
  - `Retry-After` の扱い
  - 応答の実行時検証(`extra="forbid"` の backend に合わせ、型だけで受けるか、パーサを持つか)
- 401 の扱いを決める。
  - `expireSession()` を呼ぶ。ログイン・PW 変更は除外する(旧 `noAuthRedirect`)。
  - ダウンロード系も同じ経路を通す(旧の穴を持ち込まない)。
- 送信前に `hasHydrated` を待ち、`syncFromStorage()` を呼ぶ(U-F2 の申し送り)。
- ファイル分割への答え: 混在ファイルを持ち込まなければ、混在は生じない。
- 5 領域の当て直し: 共通クライアントは T(401・認証主体)。同期の通信が通るなら S も当たる。
- `format.ts` は移植済みとして扱う(再移植しない)。

### 下流・他タスクへの申し送り(計画で確定してから送る)

- **TSK-506(同期の入口 PR)**: 共通クライアントの使い方。
- **δ(TSK-470)**: ログインの呼び出しは U-F6 の共通クライアントを使う。テナント照合の契約。
- **TSK-346**: U-F6 の型が層 (B) に依拠していることを送る。正本ができたら追随する。
- **各画面単位**: 旧の関数と型の持ち方(分岐 1 の決着しだい)。
