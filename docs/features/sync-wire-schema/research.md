---
feature: sync-wire-schema
type: research
date: 2026-10-09
---

# 調査メモ: 同期プロトコルの wire 形式・プロパティ名・JSON / API スキーマ(TSK-331)

基準ツリー: `feature/sync-wire-schema`(起点 = develop `7167c182`)。行番号はすべて 2026-10-09 の再測値。
並行ブランチの行番号は当該 worktree の HEAD(各節に記載)での値。

調査: spec-checker(要件)/ decision-tracer(決定経緯・置き場・ゲート)/ legacy-analyst(旧システム)/
Explore(現行コード・並行ブランチ)の 4 並列。エージェント報告のうち計画を左右する主張は主セッションが原典で確認した
(**[確認]** と付記)。推論は **(推論)** と明記する。

## 問い

1. TSK-331 の射程(Notion 本文 2026-09-07)は今も成立するか。上位典拠は何か
2. wire の形を縛る要件・正本の確定事項はどこまでか(意味の層 / wire の層の境界)
3. 既存コード・規約・並行ブランチで、wire の形を先取りしている箇所(衝突面)はどこか
4. スキーマの置き場と、改訂の要る正本・ゲート
5. 他タスクとの射程の重なり

## 結論(要約)

1. **射程の典拠は `sync-protocol.md:1574`(10-1 (B) 論点 18)**。HTTP 形状・エンドポイント・ペイロード形式・バッチサイズ・バックオフ定数・V12 の物理方式と、8-1 のトランザクションのまとめ方。受け取り先は「実装計画」で、**意味規則を満たす限り自由・意味規則を変えるなら正本へ戻る**(`:1584`)。意味の層(V1〜V12・A1〜A5・B1〜B14・処理段階・P1〜P5 応答契約)は確定済みで再議論しない **[確認]**
2. **要件書(v2.9)に wire の形の要求は無い**が「一切無い」は言い過ぎ — 404 / 非開示 / 理由コードなし・`accepted_at` の 1 語・一時 ID = UUID・JST・利用者 ID を載せない(Won't)が wire を縛る
3. **TSK-346(API 契約の正本・未着手)との射程の重なり** — **裁定済み: 案 (A) = TSK-331 が持つ**(2026-10-09・山田正輝 — 未解決 1)。TSK-346 のカードは「同期 wire は TSK-331」と宣言する一方、2026-09-12 の TSK-378 からの申し送りは「論点 18 を TSK-346 が明示的に引き取れ」と言う。さらに**エラー体・ステータスコードの規律は TSK-346 の射程**と宣言されている **[確認]**
4. **命名規約が両側で割れている**: frontend の同期 DTO・ローカル書き出しファイル・(d) 資産は camelCase、backend の DTO 基底は snake_case で、U-01 は「決定が無い」ことを理由に camelCase を意図的に見送った。最初の製品 API(#95 U-M1)が snake_case の先例になろうとしている **[確認]**
5. **版番号**: sync-protocol.md の v0.5 を **#81(TSK-236・approved 2026-09-28)と U-S1(TSK-391・予約)の両方が取っている** **[確認]**。**裁定(469 master 経由・2026-10-09): #81 の v0.5 は動かさず、U-S1 が v0.6 へずれる** → TSK-331 は版を上げるなら v0.7 以降。計画書では版番号を決め打ちせず「U-S1 と #81 の後」と書く。そもそも論点 18 の受け取り先は「実装計画」なので、**正本を改訂せずに済む道がある**(推論)

## 詳細と典拠

### 1. 射程と上位典拠

| 事実 | 典拠 |
| --- | --- |
| 論点 18 の行: HTTP 形状・エンドポイント・ペイロード形式・バッチサイズ・バックオフ定数・V12 の物理方式。8-1 のまとめ方(1 件ずつ / 連続範囲)も同じ受け取り先。「実クエリ・実回線が無い段階で定数を確定させるのは根拠のない固定」 | `docs/design/sync-protocol.md:1574` [確認] |
| 論点 17: D5・D4・復旧世代の生成アルゴリズム・物理形式。受け取り先は「同期・記録権の最初の実装タスク」(TSK-331 と名指しされていない) | `sync-protocol.md:1573` [確認] |
| 論点 19(ローカル書き出しのファイル形式)・論点 22(閲覧側への配信方式)も「実装計画」行き | `sync-protocol.md:1575`・`:1578` |
| 「実装計画」行きの事項は意味規則を満たす限り自由。変えるなら本書へ戻る | `sync-protocol.md:1584` |
| 11-2 柱書の「列名・型・NULL 性・FK・索引・表分割は決めない」は **DB 構造**の話(受け取り先 TSK-250)。wire のプロパティ名が未確定である典拠は 11-2 ではなく論点 18 の「ペイロード形式」 | `sync-protocol.md:1796`・`:233` |
| β の送り: 「wire 形式・プロパティ名が正本で未確定なら transport-neutral な DTO まで」「JSON / API スキーマの確定は後続 γ」 | `docs/features/sync-ack-contract/plan.md:160`・`:246` |
| γ からの分離は TSK-321 の裁定 4「wire スキーマ — 含めない → TSK-331」。裁定 8・10 は TSK-330・332 の切り出しで wire と無関係(`research.md:52` の「裁定 4・8・10」は過大) | `docs/features/sync-server-apply/plan.md:126-137`・`:66` |
| 正本の現行版は v0.4(develop) | `sync-protocol.md:10` [確認] |

Notion 本文の行番号はすべて古い: ハーネス設計書 `:181`→`:195`・`:198`→`:212` / 要件書 `:599`→`:603`・`:846`→`:850` / 11-2 柱書 `:1774`→`:1796`。

### 2. wire を縛る要件と正本の確定事項

**要件書(現行 v2.9 — `docs/requirements/requirements-pitchlog-2026-07-22.md:46`)**: エンドポイント・OpenAPI・バッチ・バックオフ・API バージョニングは 0 件。wire を縛るもの:

| 要件 | 典拠 | wire への効き方 |
| --- | --- | --- |
| FR-034 / FR-041 / NFR-010 | `:603-604`・`:645`・`:681-687`・`:848` | 403 を使わず 404・存在を判別させない・理由コードを返さない・上限超過は 400 |
| 6.1 P3 受理結果の端末保持 | `:991` | **要件書にある唯一のプロパティ名 `accepted_at`** |
| FR-015 | `:363` | 一時 ID は UUID。同期時に正式 ID へ置換 |
| 7.1 | `:1019` | 時刻は JST 基準(wire 上の表現は記載なし) |
| 2.2 Won't(個人アカウント・入力者識別) | `:97` | 利用者 ID を wire に載せない(設計 P-20 `sync-protocol.md:297`) |
| FR-012 | `:300-310` | べき等キー・世代内連番・改訂は同じ連番に新しいキー・墓標は連番を消費・記録権拒否は内容拒否と別カテゴリ |
| FR-013 | `:321-328` | 引き継ぎ要求は (保持端末・世代・確定水位) を照合 |
| NFR-001 / NFR-002 | `:798`・`:803` | 入力は往復を待たない・同期 p95 5 秒(バッチ・バックオフの制約) |
| 7.1 サーバーはステートレス | `:1016` | V12・セッションの照合をプロセス内状態に頼れない(帰結は推論) |
| NFR-014 | `:869` | V12 を署名トークンにするなら鍵は環境変数(適用は推論) |
| NFR-019(b) | `:850`・`:933` | 経路が外から到達可能になった時点で越境テストの網羅対象に入る |
| NFR-018 | `:892` | 対象の列挙は閉じていて DTO / wire スキーマを含まない。**DTO の両側定義を NFR-018 で禁じる典拠は無い** |
| NFR-023 | `:967` | wire の JSON は列挙された出力経路に無い。退避内容を表示する管理コンソールは対象(適用は推論) |

**正本の確定事項(意味の層 — 再議論しない)**: V1〜V12 と「イベントはテナント ID を搬送しない」(`sync-protocol.md:261-274`・`:263`)/
持たせない値(`:295-300`)/ 1 要求は単一の `(試合, D4)`(`:677`)/ 処理段階と B1〜B14(`:685-725`)/
ACK A1〜A5・ACK が返るのは B1〜B4 だけ(`:920-926`・`:924`)/ P1〜P5 応答契約(`:947-953`)/
P3 応答は `accepted_at` を返す(`:964`)/ B6 の非開示(`:889-890`)。**数値の HTTP ステータスコードは正本に定義なし**。

### 3. 既存コード・規約(develop)

**frontend(transport-neutral DTO・camelCase)** [確認]
- `frontend/src/lib/sync/ackEnvelope.ts:1-2`「transport から本 DTO への変換は後続実装に委ねる」。キーは `advancedD3`・`eventResults`・`playerIdMappings` / `d4`・`d1`・`d5`・`a5Result` / `temporaryId`・`officialId`(`:10-38`)
- `frontend/src/lib/sync/p3Result.ts`: `boundaryResult`・`acceptedResult`・`targetReference`・`expectedVersion`・`d5`・`confirmedContent`・`acceptedAt`(`:25-53`)。**正本は `accepted_at`、DTO は `acceptedAt`**(表記の揺れ)
- `frontend/src/lib/sync/syncEvent.ts`: 要求イベントは `{fields: Partial<Record<EventSlotId, unknown>>}` — **wire キーが V 番号(`V1`〜`V12`)**。対象参照の要素名は日本語(`['試合','対象の D4','対象の D1']` — `eventFieldRules.ts:19-22`)
- `localQueueFile.ts:215-224`: 書き出しファイルのキーは camelCase(`schemaVersion`・`exportedAt`・`events`)— 実際に永続化している先例
- **固定している spec**: `ackEnvelope.spec.ts:215-231`・`p3Result.spec.ts:275-291`(ソースに形式検査コードが無いことを検査 — wire の形式検査を同じファイルに足すと red)/ `prohibitions.spec.ts:1286-1339`・`:1426-1437`(キー集合を固定)/ `resendRange.ts:54-59`(ACK キー集合の写し)
- 通信層は無い(`fetch`・`axios` 0 件。依存は `vue` のみ — `frontend/package.json:13-15`)

**backend(DTO 基底・snake_case)** [確認]
- `backend/src/pitchlog/api/schemas/base.py:9-69`: `BaseSchema(extra="forbid")`・`EntityId = UUID`・`Timestamp = AwareDatetime`・`Page{items, next_cursor}`・`ErrorEnvelope{error:{message, fields[{location}]}}`。`alias_generator` は 0 件
- 見送りは意図的: `docs/features/u01-dto-base/design.md:55`「DTO のフィールド命名を定めた決定が存在しない。camelCase を採るのは根拠の無い先決」
- `backend/src/pitchlog/api/errors.py`: 固定文言の共通封筒へ変換(422 は発生箇所だけ)
- 規約テスト `backend/tests/test_api_conventions.py:31-37`・`:109-113`(`api/**` に `idempotenc`・`seq_no`・`tombstone`・`revision_no`・`generation` があると fail)・`:135-141`(ルートは meta の 2 本に固定)
- TB002(凍結資産 `contracts/tenant_boundary/base-allowlist.json:8101-8113`)が `backend/src` の変更行の識別子 `idempotenc`・`generation`・`tombstone` 等を検査する。免除経路は U-S1 のステップ 3 で入る予定
- 生成 OpenAPI はコミットしない・`contracts/` へ収載しない(`docs/features/u00-api-shell/plan.md:67`・`docs/features/product-impl-unit-split/plan.md:518` ③)
- FR-012 の HTTP 項目は `out_of_registry`(`contracts/authz/route-registry.json:811-834`)— 反転は入口 PR の責務(469 master と合意)

**旧システム(legacy-analyst)**: 参考になるのは SPA 期(`dd03160`)だけで、キーは英語 snake_case(観測例からの推論 — `docs/features/legacy-frontend-coverage/research.md:115-138`)。
確定 POST に `client_event_id`(UUID)・`device_id`・`captured_at`・`pitch_coordinate_system` を載せていた。
**移行は同期 API を経由しない**(`docs/design/data-model.md:2423`・`:284-291`)。移行イベントのペイロードを同期 wire 型と共有するかは典拠なし(不明)。
旧の wire 形に踏襲を義務づける要件は無い。

### 4. 置き場と改訂ゲート

| 事実 | 典拠 |
| --- | --- |
| ハーネス設計書 4 章の揺れ: `:195`「OpenAPIスキーマ・付録Eゴールデンベクタ」/ `:212`「NFR-019a のゴールデンベクタの置き場」 | `docs/development/dev-harness-design-2026-08-07.md:195`・`:212` [確認] |
| `:212` を援用: 設計 10-3 は (d) 資産を `contracts/` に置かない / ADR-003 D-1-b は「同章の改訂(版繰り上げ + 確定ゲート)を誘発する」として 4 章に触れない | `sync-protocol.md:1712` / `docs/adr/ADR-003-domain-calc-method.md:105-107` |
| `contracts/README.md:14`「将来 … OpenAPI スキーマを収載」 | `contracts/README.md:14` |
| 台帳の候補(未採番): 昇格条件「**TSK-331 が置き場を裁定する時点で H-* を採番**」。対応案 (a) `:195` から OpenAPI を外す / (b) `:212` を広げる / (c) OpenAPI を `contracts/` の外と決め両方を書き換える | `docs/development/harness-evaluation.md:2668-2687` |
| 関連する台帳: CI の paths filter(`:2689-2712`)・`contracts/` の凍結資産が直列化点(`:5035` 以降)・**H-68**(実体の無い段階でスキーマの細部まで確定させると確定ゲートが閉じた輪に入る — `:1323`) | 同上 |
| JSON Schema の先例: `contracts/authz/frozen-baselines.schema.json`(draft 2020-12・`$id: https://pitchlog.local/contracts/…`)。#81 が `contracts/state-transition/*_schema_v1.json` を新設予定。jsonschema・ajv の依存はどこにも無い | Explore 報告(`scripts/check_frozen_baselines.py:32`) |
| `contracts/` を変えると frontend・backend 両ジョブが走る(`contracts/**` filter) | `.github/workflows/ci.yml:245-256`・`:295-303` |
| 7.6-3: 実装追随の節更新は PR レビューで可 / 版繰り上げを伴うスキーマ等の構造変更は 7.3 / `docs/design/` と `docs/adr/` は確定ゲート必須 | `dev-harness-design-2026-08-07.md:532`・`:432-433` |
| OpenAPI 採否を ADR 相当とした判断の記録は見つからない(不明) | decision-tracer 報告 |

**コア領域**(`.claude/core-areas.json`): `ackEnvelope.ts`・`p3Result.ts` は sync-protocol(`:73`・`:99`)と recording-rights(`:242`・`:258`)に**個別列挙**。
`frontend/src/lib/sync/` は glob ではない → **新規ファイルはコア外**。`contracts/<sync系>/` と `backend/src/pitchlog/api/**` はどの領域にも入っていない。
paths の追加は 6.3-⑤ で敵対レビュー + 人間承認(窓口は塞がっている — 469 master)。**既存ファイルの改訂と文書だけなら追加不要**。

### 5. 他タスク・並行ブランチとの衝突面

| 相手 | 衝突面 | 典拠 |
| --- | --- | --- |
| **TSK-346**(API 契約の正本・未着手・優先度 高・13pt) | **論点 18 の持ち主が重なる**。カードの射程表は「同期経路の wire 形式・プロパティ名・JSON スキーマ = TSK-331(本タスクは重複を作らない)」「**エラー体の形・ステータスコードの規律・テナント境界の表れ方 = 本タスク**(同期側と矛盾させない)」。2026-09-12 の TSK-378 からのコメントは「論点 18 が未引き取り。**本タスクが明示的に引き取らないと同期 API の契約が二重管理**」 | Notion TSK-346 本文・コメント(2026-09-09 / 2026-09-12)[確認]。`docs/features/merge-gate-api-cycle/design.md:346` |
| 同上 | 「各単位が経路表を書き、TSK-346 が後から収載。矛盾したら TSK-346 が正」 | `product-impl-unit-split/plan.md:495-500` |
| **U-S1**(TSK-391・承認済み) | `sync/model.py` にサービス層の要求・結果の型を作り、wire への写像は「TSK-331 の後の入口 PR」(R-3)。先に着地すると Python 側の型名が事実上の基準になる(推論)。v0.5 を予約(R-10) | `feature-us1-sync-apply-core` の `docs/features/us1-sync-apply-core/plan.md:33`・`:36`・`:64`・`:77`、`design.md:17`・`:29` [確認] |
| **#81**(TSK-236・draft) | sync-protocol.md を **v0.5(approved 2026-09-28)** に改訂済み — U-S1 の v0.5 と衝突。`contracts/README.md`・`core-areas.json`(`reference_discovery`)も変更 | `feature-appendix-e-golden-vectors`(HEAD `9ad60c60`)の `docs/design/sync-protocol.md:10` [確認] |
| **#95**(U-M1・draft) | 最初の製品 HTTP 入口。DTO は snake_case・alias なし(`schemas/roster.py:22-75`)→ 「製品 API は snake_case」の先例になる(推論) | Explore 報告 |
| **#100**(U-A1 γ) | `api/app.py`・規約テストを変更 — TSK-331 がこれらに触れるとテキスト衝突 | Explore 報告 |

## 未解決・申し送り(/plan で人間の裁定が要るもの)

1. **TSK-346 との境界** — **裁定済み(2026-10-09・山田正輝): 案 (A)**。TSK-331 が論点 18 の同期部分を全部持ち、エラー体・命名は backend の既存 DTO 基底(`api/schemas/base.py`)に揃える。TSK-346 は後から参照・収載する。検討した案:
   - (A) **TSK-331 が論点 18 の同期部分を全部持つ**。TSK-346 はそれを参照する。横断の規律(エラー体・ステータスコード・命名)は、TSK-331 が同期の範囲で決めて、TSK-346 が後から追随・収載する
   - (B) **TSK-346 が論点 18 を引き取る**。TSK-331 は TSK-346 へ吸収する(または取り下げる)
   - (C) **分割**: 横断の規律(命名規約・エラー体・ステータスコード・OpenAPI 採否・置き場)は TSK-346 が先に決め、TSK-331 は同期固有のペイロード・バッチ・バックオフ・V12 の物理方式だけを持つ。この案では TSK-331 が TSK-346 待ちになる
2. **命名規約**(camelCase / snake_case / 境界で変換)。1 の裁定次第で TSK-331 の射程外になりうる
3. **置き場**(台帳候補の対応案 a/b/c)。決めた時点で台帳の候補に H-* を振る
4. **論点 17 を入れるか**(既定は外す — 受け取り先は「同期・記録権の最初の実装タスク」)。**回答済み(391 タブ・2026-10-09 — 原典確認済み): TSK-331 の射程から外す**。D5 側は U-S1 が引き取る(物理形式は既に `uuid`・クライアント生成 — `backend/src/pitchlog/db/sync_protocol/models.py:259` / 内容同一性は U-S1 `design.md:121` Q-4 = 入力原本の正規化 JSON の全フィールド比較 / 記録 = `feature/us1-sync-apply-core` の `ffe8bab2`)。D4・復旧世代の生成方式と保存場所は U-S1 も引き取らず、U-R1(TSK-392)の射程と読む(**U-R1 との合意は未取得**)。**TSK-331 への制約: wire 上の D5 表現は `uuid` 型と矛盾させない**(UUID の文字列表現)。論点 19・22 も同様
5. **正本の版を上げるか**(既定は上げない — 論点 18 は「実装計画」行き。10-1 の行の受け取り先の書き換えが実装追随の節更新で済むかは、7.6-3 で判定する)。上げるなら #81(v0.5)→ U-S1(v0.6)の後 = v0.7 以降
6. **H-68 の型を避けるには**: 実体(HTTP 入口・実回線)が無い段階で定数を固定しない(`:1574` 自身がそう言っている)。バッチサイズ・バックオフ定数は入口 PR へ送るのが筋(推論)
7. 移行イベントのペイロードを同期 wire 型と共有するか — 典拠なし。射程外にする方向(推論)
