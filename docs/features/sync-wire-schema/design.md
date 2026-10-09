---
feature: sync-wire-schema
type: design
date: 2026-10-09
---

# 詳細設計: 同期 wire 契約(TSK-331)

## 1. 射程と位置づけ

**契約は [plan.md](plan.md) が正。本書は同期 wire の詳細だけを持つ。** 調査の典拠は [research.md](research.md) にあり、本書は結論だけを引く。

### 1-1. 本書は何か

- 同期プロトコル正本 [sync-protocol.md](../../design/sync-protocol.md) **10-1 (B) 論点 18** の同期部分の受け取り先「**実装計画**」である。論点 18 が挙げる「HTTP 形状・エンドポイント・ペイロード形式・バッチサイズ・バックオフ定数・V12 の物理方式」と、8-1 のまとめ方のうち、**本書が決めるもの / 決めないもの**は plan.md 2 節が正
- 正本 10-1 は「実装計画」行きの事項を「**本書の意味規則を満たす限り自由。意味規則を変える必要が出たら本書へ戻る**」とする。**本書は意味規則を変えない**。変えなければ書けない事柄に当たったら、本書に書かずに未解決へ記録し、正本の改訂として扱う
- **API 全体の契約の正本は TSK-346**(未着手)が `docs/design/` に新設する。TSK-346 は本書を参照・収載する側であり、本書と矛盾させない(持ち主の裁定 2026-10-09 — plan.md 1 節)

### 1-2. 根拠の層

本書の各規則に、どちらの層かを付ける。

- **(A) 正本・要件の帰結** — 同期正本・要件書から直接導けるもの。破ってはならない
- **(B) 本書の設計判断** — 正本が「実装計画」に委ねた範囲で、本書が選んだもの。入口 PR は本書に従う。変える場合は本書を改め、理由を変更の記録に残す

### 1-3. 正本の参照方法(plan.md の原則 W-1)

- **意味の層は参照だけする**。D1〜D9・V1〜V12・VF1〜VF6・A1〜A5・B1〜B14・P1〜P5・I1〜I6・DI1〜DI5 などの**定義・規則を本書で言い換えて再掲しない**。本書が書くのは「その ID の値を wire のどこにどう載せるか」だけである
- 正本(同期正本・要件書・`docs/design/data-model.md`)は**節番号と ID で引く**(例: 「正本 6-3 の B4」「要件書 [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012)」)。**行番号では引かない** — 正本は改訂で行がずれ、TSK-346 が本書を収載するときに引用が壊れる(正本 2-6 と同じ理由)
- コードは**パスと識別子名**で引く(例: `backend/src/pitchlog/api/schemas/base.py` の `BaseSchema`)
- **本書が付ける記号**(E-・G-・K-・L-・S-・X-・N-・EP-・TK-・WU-)は本書の中だけのものである。要件書の付録 E-1・E-2、成功指標 G-1〜G-3、正本の K4・K5・T1〜T9・O1〜O4・U-*、運用評価台帳の H-* とは別物なので、**本書の外から引くときは「同期 wire 設計の K-1」のように文書名を付ける**(正本 2-6 の文書修飾と同じ扱い)

## 2. 規約

### 2-1. 運び方の前提

| # | 規約 | 層 | 典拠 |
| --- | --- | --- | --- |
| **G-1** | 要求・応答の本文は **JSON**(`application/json`、UTF-8)。経路は HTTPS だけ | (A) | 要件書 [NFR-013](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-013)(全通信 HTTPS) |
| **G-2** | **テナント ID を wire に載せない**。テナントは認証済みセッションと試合の所有関係から決まる | (A) | 正本 4-3 の V1 |
| **G-3** | **利用者 ID・入力者の識別を wire に載せない** | (A) | 正本 4-3「持たせてはならない値」・要件書 [2.2](../../requirements/requirements-pitchlog-2026-07-22.md#2.2)(Won't) |
| **G-4** | **順序の決定に使う時刻を wire に載せない**(正本 4-3「持たせてはならない値」)。イベントが時刻属性を持つかは正本が決めておらず 11-4 へ送っているので、**本書もイベントの時刻属性を決めない**(載せるとしても順序の決定に使わない) | (A) | 正本 4-3「持たせてはならない値」・11-4 |

### 2-2. キーの命名

| # | 規約 | 層 | 典拠 |
| --- | --- | --- | --- |
| **K-1** | **キーは snake_case**(`^[a-z][a-z0-9]*(_[a-z0-9]+)*$`) | (B) | backend の DTO 基底(`backend/src/pitchlog/api/schemas/base.py` の `BaseSchema` — `alias_generator` を持たない)・最初の製品 API(#95)・U-01 の判断(`docs/features/u01-dto-base/design.md`「camelCase を採るのは根拠の無い先決」)。**正本自身が P3 応答の時刻を `accepted_at` と snake_case で書いている**(正本 7-1 の I6) |
| **K-2** | **正本の述語を表すキーは、述語 ID を小文字にして名前に使う**(例: D5 → `d5`、前進後の D3 → `advanced_d3`、A5 の結果 → `a5_result`)。**記述的な英語の別名を作らない** | (B) | 正本 2-1(定義の単一化)・2-3(別名の禁止 — 台帳 H-79 の型: 別名で検索から漏れる) |
| **K-3** | **既存の frontend DTO がキーを持つ値は、そのキーを snake_case に機械変換した名前にする**。変換規則: 英大文字の前に `_` を入れて小文字にする(`advancedD3` → `advanced_d3`・`a5Result` → `a5_result`・`acceptedAt` → `accepted_at`)。これで wire ⇄ DTO は名前の変換だけで写る | (B) | `frontend/src/lib/sync/ackEnvelope.ts`・`p3Result.ts` のキー集合 |
| **K-4** | 述語 ID を持たない値(試合の識別・イベント種別・ペイロードなど)は、**正本の語に対応する英語の記述名**にする。ただし下の K-5 表の語は使わない | (B) | 正本 4-3 の V4・V5・V7 |
| **K-5** | **正本 2-3 が禁じる別名に当たる英語をキーにしない**(下表) | (A) | 正本 2-3 (a)・(b) |

**K-5 の表** — 正本 2-3 の各行に対応して、wire のキーに使わない英語(禁止語そのものは正本 2-3 を参照。全数の突き合わせは worklog のステップ 1 欄):

| 正本 2-3 の行 | キーに使わない英語 |
| --- | --- |
| (a) D1 | `server_arrival_order`・`server_received_order`・`received_order`・`serial_number`・`sequence_number`・`seq_no` |
| (a) D2 | `operation_order`・`record_order`・`display_order` |
| (a) D3 | `applied_position`・`sync_position`・`offset`・`cursor` |
| (a) D4 | `lock_generation`・`epoch` |
| (a) D5 | `request_id`・`idempotency_token`・`dedup_key` |
| (a) D6 | `gap_filler`・`delete_marker` |
| (a) D7 | `revision` |
| (a) D8 | `hold`・`dead_letter`・`archive` |
| (a) D9 | `receipt`・`success_response`・`sync_complete_notice` |
| (b) 到着順 | `arrival_order` |
| (b) 再送 | D7 を表すキーに `resend`・`retransmit` |
| (b) 応答 | ACK を表すキーに `response` |
| (b) 空イベント | `empty_event` |
| (b) 修正 / 訂正・上書き | D7 を表すキーに `correction`・`overwrite` |
| (b) スキップ | `skip`・`skipped` |
| (b) UUID | D5 を表すキーに `uuid` |
| (b) プレイ番号 | `play_number` |
| (b) トークン | D4 を表すキーに `token` |
| (b) 隔離 | D8 を表すキーに `quarantine` |
| (b) チェックポイント | `checkpoint` |

表は正本 2-3 の (a) 9 行と (b) 12 行に 1 行ずつ対応する((b) の「修正 / 訂正」と「上書き」は 1 行にまとめた)。

注: 墓標(D6)と改訂(D7)は**イベントの種類**(正本 5-5 の参加区分表の #8 墓標)と**置換の状態**(V9)として現れ、キー名にはならない。値の語彙は 2-3 の L-4 に従う。`cursor` は一覧のページング(`backend/src/pitchlog/api/schemas/base.py` の `PageRequest`)では正しい用法であり、**同期 wire の中で D3 の意味に使わない**という規約である。

### 2-3. 値の表現

| # | 値 | 表現 | 層 | 典拠 |
| --- | --- | --- | --- | --- |
| **L-1** | **D5**・**一時 ID** | **UUID の正規形の文字列** — 小文字 16 進・ハイフン区切り 8-4-4-4-12(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)。**クライアントは正規形で送り、サーバーは正規形でない値を受理しない**(大文字・ハイフンなし・波括弧つきを正規化して受け入れない)。サーバーが返す値は、受け取った値と文字列として一致する | (A)+(B) | D5 の物理形式 `uuid`(391 の回答 — `backend/src/pitchlog/db/sync_protocol/models.py` の `d5`)・一時 ID は UUID(要件書 [FR-015](../../requirements/requirements-pitchlog-2026-07-22.md#FR-015))。**正規化しない理由**: frontend の受け取り側は応答の値を端末が保持する値と `Object.is` で照合する(`frontend/src/lib/sync/p3Result.ts` の `parseP3ResultEnvelope` が受理期待と受理結果の D5 などを照合)ので、サーバーが正規化した別表記を返すと照合が外れる |
| **L-2** | **D1**・**D3** | **JSON の整数**。D1 は 1 以上、D3 は 0 以上。上限は 2^53 − 1(JavaScript の安全な整数) | (A)+(B) | クライアントが D3 + 1 から D1 昇順に数える(正本 6-2 の⑥・2-1 の D1 定義「最初の新規割り当てを 1」・D3「新しい記録権世代ではサーバーの D3 を 0」) |
| **L-3** | **D4**・**復旧世代**・**V12** | **クライアントが解釈しない不透明な文字列**(空文字は不可)。クライアントは受け取った値を保存して、そのまま送り返すだけで、分解・大小比較・生成をしない。**物理形式・長さの上限・寿命・更新方法は発行する側(U-R1 — TSK-392)が決める** | (B) | 物理形式は正本が決めない(2-1 の D4・4-3 の復旧世代と V12)。DB の `generation` は `BigInteger`(`backend/src/pitchlog/db/sync_protocol/models.py`)だが、JSON の数値は 2^53 を超えると精度を失うので文字列で運ぶ。V12 の物理方式の送り先は承認済み(plan.md 4 節「人間の判断が要る点」①) |
| **L-4** | **列挙値** | **正本の安定 ID をそのまま使う**(境界結果は `"B1"`〜`"B14"`、B3 の分岐は `"B3a"`・`"B3b"`、O4 は `"O4"`)。**ID を持たない値は正本の語をそのまま使う**(A5 の結果は `"受理"`・`"重複"`・`"拒否"`・`"退避"`・`"未処理"`、P3 の受理は `"変更受理"`)。英語の別名を作らない | (B) | 正本 2-3(別名の禁止)・7-1 の A5・2-5 の R-ACK-STATE(要素全集合が正本の語)。frontend の受け取り側も正本の語で照合している(`frontend/src/lib/sync/boundaryResults.ts`・`canonOracle.ts`) |
| **L-5** | **時刻** | **RFC 3339 のオフセット付き文字列**。オフセットのない時刻は受理しない。サーバーが返す時刻は JST(`+09:00`)で表す | (A)+(B) | 要件書 7.1(JST 基準)・`backend/src/pitchlog/api/schemas/base.py` の `Timestamp`(`AwareDatetime`) |
| **L-6** | **試合の識別** | サーバーが発行する試合の ID(UUID の正規形の文字列 — L-1 と同じ表記) | (B) | `backend/src/pitchlog/api/schemas/base.py` の `EntityId`(UUID)・`models.py` の `game_id`(`Uuid`) |

### 2-4. 形の検査 — どこで落とし、何として扱うか

正本の境界結果 B1〜B14 は、同期要求を処理する段階の列挙から導かれている(正本 6-2 の「網羅性の根拠」表と P3 の処理段階表)。要求の形が 2-1〜2-3 の規約に合わない場合に当たる結果は正本に無い。**本書は新しい境界結果を作らず、既存の境界結果の成立条件も広げない**(1-1)。形の検査を 2 層に分ける。

| 層 | 対象 | wire の層での扱い | 層 |
| --- | --- | --- | --- |
| **S-1 要求の外形** | **次に列挙する値だけ**: ① 要求の本文が JSON のオブジェクトであること・未知キーが無いこと ② 試合の識別(L-6)③ D1 付き経路の D4 の有無と型(L-3)④ P3 の要求作成時の復旧世代の有無と型(L-3)⑤ イベントの並びの形 ⑥ 各イベントの D5(L-1)⑦ D1 付き経路では各イベントの D1(L-2)⑧ D1 付き経路の要求内の整合 — 全イベントの D4 が同じ値(単一の `(試合, D4)` — 正本 6-2)・D1 が重複しない・各イベントの試合の識別が path と同じ(3-2) | 列挙した値だけを厳格に検査する。失敗は **S-1 違反**(下記)とし、処理段階に入らない | (B) |
| **S-2 それ以外のすべて** | **V12(有無・型・形を問わない)**、D4・復旧世代の値の照合(現行の値と一致するか — ⑧ の要求内の同一性は S-1)、V5〜V11 | **wire の層では欠落・型違いも含めて検査しない**。JSON の値のまま処理段階に渡し、結果は正本が決める(D1 付き経路は正本 6-2 の段階表・DI1〜DI5・A5、P3 は P3 の段階表・I1〜I4、V12 は VF1〜VF5) | (A) |

S-1 に入れる値の基準: 正本で条件なしに必須(正本 4-3 の V1・V2・V3、6-2 の P3 の③-b)で、かつ処理段階の照合を始めるのに要る値。**値が照合に通るか**は S-1 で見ない。

#### S-1 違反の扱い

- **S-1 違反は境界結果ではない**。B1〜B14 のどれにも当てはめない(正本 6-3 の B7・P3 の独立境界結果の B10 の成立条件を広げない)
- **サーバーは状態を一切変えない**(処理段階に入らないので D5 を照合も記録もしない)。違反をサーバーのログに記録する
- **S-1 の検査は試合の存在に依存しない**ので、応答の差から存在は漏れない(正本 6-5)。S-1 違反の応答は試合の識別の値によらず同じ形にする(4 節)
- **クライアントは S-1 違反の応答を受けたら、キューの状態と P3 の保持内容を一切変えず、S-1 違反を顕在化する**(要件書 [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012)・[NFR-015](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-015))。キューの状態を変えないので、**その後の送信は正本 7-2 の当該状態の扱いに従い、本書は再送の停止・再開の条件を足さない**
- S-1 違反が正本の外にあることは未解決 WU-1 に記録する

### 2-5. 応答側の未知の値

クライアントが、応答に未知のキー・未知の列挙値・2-3 に合わない値を見つけた場合:

- **D1 付き経路**: その応答を解釈せず、**キューの状態を一切変えない**。既存の受け取り側(`frontend/src/lib/sync/ackEnvelope.ts` の `parseD1AckEnvelope` など)が未知キー・重複を例外にしている振る舞いと一致する。解釈できない ACK でキューを進めると、確定していないイベントを同期済みにしうる(正本 7-1「ACK が保証しないこと」)
- **P3**: その応答を解釈せず、**端末が保持している P3 要求(同じ D5・同じ内容)を変えない**。正本 7-1 の I6 は、端末へ永続化した受理結果だけを保証の対象にしているので、解釈できない応答を受理結果として保存しない
- **どちらも S-1 違反と同じく顕在化する**。送り直したときの結果は正本が決める(D1 付き経路は DI2、P3 は I2)

### 2-6. wire キー ⇄ 正本 ID の対応表

3 節(要求)・4 節(応答)が行を足す。**本表に無いキーを wire に置かない。**

| wire キー | 位置 | 正本 ID | 値の表現 | 必須条件 | 既存 DTO のキー |
| --- | --- | --- | --- | --- | --- |
| `recording_right_proof` | E-1・E-2 の要求本文 | V12 | L-3 | VF1〜VF3 | `RequestBoundaryEnvelope.requestValues.V12`(5-1) |
| `recovery_generation` | E-2 の要求本文 | 要求作成時の復旧世代 | L-3 | 全 P3 | `RequestBoundaryEnvelope.recoveryGenerationAtCreation`(5-1) |
| `events` | E-1 の要求本文 | — | 配列 | E-1 で必須 | `SyncEvent` の並び(5-1) |
| `change` | E-2 の要求本文 | — | オブジェクト | E-2 で必須 | `SyncEvent` 1 件(5-1) |
| `d5` | イベント | V1(D5) | L-1 | 全イベント | `fields.V1` |
| `d1` | E-1 のイベント | V2(D1) | L-2 | P1・P2・P4 | `fields.V2` |
| `d4` | E-1 のイベント | V3(D4) | L-3 | P1・P2・P4 | `fields.V3` |
| `game_id` | イベント | V4 | L-6 | 全イベント | `fields.V4` |
| `event_kind` | イベント | V5 | L-4(正本 5-5 の番号) | 全イベント | `fields.V5` |
| `d2` | E-1 のイベント | V6(D2) | 3-4 | 種別条件付き | `fields.V6` |
| `payload` | イベント | V7 | JSON のオブジェクト | 全イベント | `fields.V7` |
| `state_diff` | E-1 のイベント | V8 | JSON のオブジェクト | 取消可能な操作 | `fields.V8` |
| `replacement_state` | E-1 のイベント | V9 | JSON のオブジェクト | 墓標・改訂 | `fields.V9` |
| `target_reference` | イベント | V10 | `game_id`・`d4`・`d1` の 3 要素 | 種別条件付き / P3 は必須 | `fields.V10`(要素名は `試合`・`対象の D4`・`対象の D1`) |
| `expected_version` | E-2 の `change` | V11 | 3-4 | P3 | `fields.V11` |
| `boundary_result` | ACK・P3 の結果 | A3 / P3 の結果 | L-4 | ACK・P3 の結果で必須 | `boundaryResults.ts` の `boundaryResult` / `p3Result.ts` の `boundaryResult` |
| `advanced_d3` | ACK | D3 | L-2 | ACK で必須 | `advancedD3` |
| `event_results` | ACK | A5 | 配列 | ACK で必須 | `eventResults` |
| `event_results[].d4`・`.d1`・`.d5` | ACK | A5 の `(D4, D1, D5)` | L-1〜L-3 | 必須 | `d4`・`d1`・`d5` |
| `event_results[].a5_result` | ACK | A5 の結果 | L-4 | 必須 | `a5Result` |
| `event_results[].rejection` | ACK | B3a・B3b・O4 | `kind`・`branch`・`reason` | `"拒否"` のときだけ | `rejectionReason.ts` の `kind`・`branch`・`reason` |
| `player_id_mappings` | ACK | A4 | 配列 | 受理・重複の選手登録を行うイベント(#6・元が #6 の #9)があるとき(4-2) | `playerIdMappings` |
| `player_id_mappings[].temporary_id`・`.official_id` | ACK | 一時 ID・正式 ID | L-1 の表記 | 必須 | `temporaryId`・`officialId` |
| `accepted_result` | P3 の結果 | I6 | オブジェクト | 変更受理のときだけ | `acceptedResult` |
| `accepted_result.target_reference`・`.expected_version`・`.d5`・`.confirmed_content`・`.accepted_at` | P3 の結果 | V10・V11・V1・確定内容・I6 の時刻 | 3 節・L-5 | 必須 | `targetReference`・`expectedVersion`・`d5`・`confirmedContent`・`acceptedAt` |
| `current_version` | P3 の結果 | B8 の現在版 | 3-4 | B8 のときだけ | (受け口なし — 5-3 の X-2) |
| `b9_cause` | P3 の結果 | B9 の成立条件 | L-4 | B9 のときだけ | (受け口なし — 5-3 の X-2) |
| `reason` | P3 の結果 | B14 の理由 | 4-5 | B14 のときだけ | (受け口なし — 5-3 の X-2) |
| `error`・`error.message`・`error.fields`・`error.fields[].location` | 共通エラー封筒(4-1) | — | `backend/src/pitchlog/api/schemas/base.py` の `ErrorEnvelope`・`ErrorDetail`・`ErrorField` | 4-1 の表のとおり | (受け口なし — 5-3 の X-3) |

## 3. エンドポイントと要求の形

### 3-1. エンドポイント

| # | method・path | 運ぶもの | 起きうる経路 | 層 |
| --- | --- | --- | --- | --- |
| **E-1** | `POST /games/{game_id}/sync/events` | **D1 付きの同期要求**(正本 5-5 の群 A のイベントの並び) | **P1・P2・P4・P5**。どの経路になるかはクライアントが選ばず、**経路の判定は正本 8-1 の経路表と 6-2 に従う** | (B) |
| **E-2** | `POST /games/{game_id}/sync/changes` | **P3 の変更要求**(正本 5-5 の群 B のイベント 1 件) | **P3** | (B) |

- **`{game_id}`** は試合の識別(L-6)。**1 要求は単一の `(試合, D4)` に限る**(正本 6-2)ので、試合は path で 1 つに決まる
- **E-2 は 1 要求 = 1 件**。P3 の応答契約は 1 件ごとの独立した結果である(正本 7-1 の経路別の応答契約 P3・I6)
- **path に `sync` を入れて同期 API をまとめる**。`route_id` の付与と `contracts/authz/route-registry.json` の FR-012 行の扱いは入口 PR が持つ(plan.md 2 節「やらないこと」)
- 群 A・群 B の別は正本 5-5 が正。E-1 に群 B の種別が来た場合・E-2 に群 A の種別が来た場合は、イベント種別(V5)の内容の誤りであり S-2(2-4)— 処理段階の内容の検証で扱う

### 3-2. E-1 の要求本文(D1 付き)

```json
{
  "recording_right_proof": "<V12 — 不透明な文字列>",
  "events": [
    {
      "d5": "<UUID の正規形>",
      "d1": 1,
      "d4": "<不透明な文字列>",
      "game_id": "<UUID の正規形>",
      "event_kind": "1",
      "d2": "<D2>",
      "payload": {},
      "state_diff": {}
    }
  ]
}
```

例は毎球入力(種別 #1)1 件。条件付きのキーの有無は下表と正本 4-3 に従う。

| キー | 正本 ID | 層(2-4) | 規約 |
| --- | --- | --- | --- |
| `recording_right_proof` | **V12**(要求レベル) | S-2 | 要求に 1 つ。有無・型・形を wire の層で検査しない(VF1・VF4) |
| `events` | — | S-1 | イベントの配列。**空でない**。**同じ要求の中で `d1` が重複しない**(墓標・改訂の扱いは正本 2-1 の D6・D7 を参照)。**`d5` の重複は S-1 で見ない**(正本 4-5 の D5 照合と DI5 の分類に委ねる)。**並び順に意味を持たせない**(サーバーは D1 の昇順で処理する — 正本 6-2 の⑥)。件数の上限は入口 PR が決める(W-6) |
| `d5` | **V1**(D5) | S-1 | L-1 |
| `d1` | **V2**(D1) | S-1 | L-2 |
| `d4` | **V3**(D4) | S-1(有無と型)/ S-2(値) | L-3。**要求内の全イベントで同じ値**(単一の `(試合, D4)` — 正本 6-2) |
| `game_id` | **V4** | S-1 | L-6。**path の `{game_id}` と同じ値** |
| `event_kind` | **V5** | S-2 | 正本 5-5 の種別の番号を文字列で(`"1"`〜`"9"`。L-4 — frontend の `frontend/src/lib/sync/eventKinds.ts` の `EVENT_KIND_RULES` の `id` と同じ) |
| `d2` | **V6**(D2) | S-2 | 論理位置を持つ種別だけが持つ(正本 5-5)。表現は D2 の物理形式(正本 10-1 論点 26 — 数値型は TSK-250)に従い、本書は決めない |
| `payload` | **V7** | S-2 | JSON のオブジェクト。種別ごとの中身は本書で決めない(3-4) |
| `state_diff` | **V8** | S-2 | 取消可能な操作だけが持つ(正本 4-3 の V8)。中身は本書で決めない |
| `replacement_state` | **V9** | S-2 | 墓標・改訂だけが持つ(正本 4-3 の V9)。中身は本書で決めない |
| `target_reference` | **V10** | S-2 | undo・墓標・改訂が持つ(正本 4-3 の V10)。要素は `game_id`(L-6)・`d4`(L-3)・`d1`(L-2)の 3 つ — 正本の `(試合, 対象の D4, 対象の D1)` |

- **E-1 のイベントは `expected_version`(V11)を持たない**(V11 は P3 だけ — 正本 4-3)。上表に無いキーは未知キーとして S-1 違反
- **値を持たないキーは省く**。`null` を「持たない」の意味に使わない(`null` の値は S-2 として処理段階に渡り、内容の誤りとして扱われる)
- **`d4` を各イベントに持たせる理由**: 正本は D4 をイベント属性として運ぶ方式を採っている(正本 4-3 の V3)。要求内で同じ値でなければならない(単一の `(試合, D4)`)ので、異なる値が混ざった要求は S-1 違反にする(要求の形が正本 6-2 の制約に合わない)
- **`game_id` を path と各イベントの両方に持たせる理由**: V4 は全イベントに無条件の値(正本 4-3)で、サイドカー結合キーの第 1 要素である。path の値はルーティングと認可(正本 6-2 の③)に使う。食い違いは S-1 違反

### 3-3. E-2 の要求本文(P3)

```json
{
  "recovery_generation": "<要求作成時の復旧世代 — 不透明な文字列>",
  "recording_right_proof": "<V12 — 進行中の試合のときだけ>",
  "change": {
    "d5": "<UUID の正規形>",
    "game_id": "<UUID の正規形>",
    "event_kind": "10",
    "payload": {},
    "target_reference": {"game_id": "<UUID>", "d4": "<不透明な文字列>", "d1": 1},
    "expected_version": "<V11>"
  }
}
```

| キー | 正本 ID | 層(2-4) | 規約 |
| --- | --- | --- | --- |
| `recovery_generation` | 要求作成時の復旧世代(正本 4-3-A「変更イベント(P3)の必須値対応」の末尾の段落・6-2 の P3 の③-b) | S-1(有無と型)/ S-2(値) | L-3。**全 P3 要求に必須**。応答が消えた後の自動再試行でも、作成時の値を変えない(正本 4-3-A) |
| `recording_right_proof` | **V12**(要求レベル) | S-2 | 有無・型・形を wire の層で検査しない(VF2・VF3・VF5) |
| `change` | — | S-1 | 変更イベント 1 件のオブジェクト |
| `d5` | **V1**(D5) | S-1 | L-1 |
| `game_id` | **V4** | S-1 | L-6。path の `{game_id}` と同じ値 |
| `event_kind` | **V5** | S-2 | 正本 5-5 の種別の番号を文字列で(`"10"`〜`"12"`) |
| `payload` | **V7** | S-2 | JSON のオブジェクト。中身は本書で決めない(3-4) |
| `target_reference` | **V10** | S-2 | E-1 と同じ 3 要素 |
| `expected_version` | **V11** | S-2 | 対象の期待版。表現は対象の確定版の物理形式に従い、本書は決めない(3-4) |

- **`change` は `d1`・`d4`・`d2`・`state_diff`・`replacement_state` を持たない**(P3 は V2・V3・V6・V8・V9 を持たない — 正本 4-3-A「変更イベント(P3)の必須値対応」)。上表に無いキーは未知キーとして S-1 違反
- **復旧世代は V1〜V12 に足す新しいイベント値ではない**(正本 4-3-A)。本書は要求の境界に載せるだけで、`change` の中に置かない

### 3-3-A. 要求の形の照合

| 照合 | 結果 |
| --- | --- |
| 正本 4-3 の V1〜V12 | 12 件すべてを 3-2・3-3 のキーで運ぶ(2-6 の対応表で 12 行) |
| 正本 4-3 の VF1〜VF6 | VF1〜VF5 は 3-2・3-3 の `recording_right_proof` の行で参照。VF6 は V12 の中身の問題で、wire は不透明な値として運ぶ(L-3) |
| 正本 4-3「持たせてはならない値」の表 | 3-2・3-3 のどのキーも、表の行に当たらない |
| K-5 表 | 3-2・3-3 のどのキーとも一致しない |

### 3-4. 本書で決めない要求の中身

| 値 | 決めない理由 | 送り先 |
| --- | --- | --- |
| **V7 ペイロード・V8 状態差分・V9 置換の状態の、種別ごとの中身** | 論点 18 の「ペイロード形式」は、本書では**要求・応答の本文をどう運ぶか**(JSON・`payload` などのキーに載せる)と解釈する。種別ごとの項目(投球情報・打撃結果・交代の内容など)は要件書の FR-002〜FR-004・FR-011 などと `docs/design/data-model.md` の操作イベントの扱いに属し、wire の層では検査しない(S-2 — 内容の検証は正本 6-2 の⑦ / P3 の⑥) | 各イベント種別を実装する単位(`docs/features/product-impl-unit-split/plan.md` の単位表) |
| **V6 D2 の表現** | 正本 10-1 論点 26(順序ラベルの具体パラメータ)と TSK-250(数値型) | 論点 26 の受け取り先 |
| **V11 期待版の表現** | 対象の確定版の物理形式に従う | 変更イベントを実装する単位(U-G2) |
| **D4・復旧世代・V12 の物理形式と長さの上限** | 発行する側が決める(L-3) | U-R1(TSK-392) |
| **E-1 の件数の上限** | 定数は決めない(W-6) | 入口 PR |

## 4. 応答の形と HTTP ステータス

### 4-1. 表れ方の写像(plan.md の原則 W-5)

| 群(W-5) | 結果 | 経路 | HTTP ステータス | 本文 | 層 |
| --- | --- | --- | --- | --- | --- |
| ① | **B1・B2・B3・B4** | E-1 | **200** | ACK(4-2) | (A)+(B) |
| ② | **変更受理** | E-2 | **200** | P3 の受理結果(4-3) | (A)+(B) |
| ③ | **B8・B9・B13・B14** | E-2 | **409** | P3 の拒否結果(4-3) | (A)+(B) |
| ④ | **B5** / **B11** | E-1 / E-2 | **401** | 共通エラー封筒 | (A)+(B) |
| ④ | **B6** / **B12** | E-1 / E-2 | **404** | **自テナントに存在しない試合の 404 と同一のバイト列**(4-4) | (A) |
| ④ | **B7** / **B10** | E-1 / E-2 | **408・500・502・503・504**、または**応答なし**(通信断・タイムアウト) | 応答があるときは共通エラー封筒 | (A)+(B) |
| — | **S-1 違反**(2-4 — 境界結果ではない) | E-1・E-2 | **422** | 共通エラー封筒(`fields` は発生箇所だけ) | (B) |

- **共通エラー封筒**は `backend/src/pitchlog/api/schemas/base.py` の `ErrorEnvelope`(`{"error": {"message": ..., "fields": [{"location": ...}]}}` — 理由コードを持たない)。文言は `backend/src/pitchlog/api/errors.py` の固定文言を使い、**同期の内部状態を文言に含めない**
- **③ を 409 にまとめ、422 を S-1 違反だけにする理由**: 正本は B8 を「成功として返さない」とする(正本 6-3 の P3 の独立境界結果)ので成功ステータスは使えない。B14 に 422 を当てると、既存の検証ハンドラ(`errors.py` の `_request_validation_exception_handler` — 422)が返す S-1 違反とステータスで区別できなくなる。③の 4 結果は本文の `boundary_result` で区別する
- **B7・B10 に当てるステータスを 5 つに限る理由**: 408・500・502・503・504 は正本 6-3 の B7・P3 の独立境界結果の B10 の成立条件に当たる。**501 など、処理しないことを確定して返すステータスは当たらない**ので、下の「上表に無いステータス」として扱う。`Retry-After` を付けるか・その値は入口 PR が決める(W-6)
- **上表に無いステータス**(400・413・429・501 など)を受けたクライアントは、2-5 と同じく応答を解釈せず、キューと P3 の保持内容を変えずに顕在化する。入口 PR が件数の上限超過(413)や流量制限(429)を導入する場合は、その表れ方を本表に足してから導入する(W-6)。一時的に処理しない応答(429 など)は、B7・B10 の成立条件に当たるかで群を決める

### 4-2. ACK の本文(E-1・B1〜B4)

```json
{
  "boundary_result": "B3",
  "advanced_d3": 41,
  "event_results": [
    {"d4": "<不透明な文字列>", "d1": 41, "d5": "<UUID>", "a5_result": "受理"},
    {"d4": "<不透明な文字列>", "d1": 42, "d5": "<UUID>", "a5_result": "拒否",
     "rejection": {"kind": "内容起因", "branch": "B3a", "reason": {}}},
    {"d4": "<不透明な文字列>", "d1": 43, "d5": "<UUID>", "a5_result": "未処理"}
  ],
  "player_id_mappings": [
    {"temporary_id": "<UUID>", "official_id": "<UUID>"}
  ]
}
```

| キー | 正本 ID | 規約 |
| --- | --- | --- |
| `boundary_result` | **A3** の境界結果 | `"B1"`〜`"B4"` のどれか(L-4)。ACK が返るのはこの 4 つだけ(正本 7-1 の A3) |
| `advanced_d3` | 前進後(または据え置き)の **D3** | L-2。**ACK の必須要素**(正本 7-1「ACK の必須要素は前進後の D3」) |
| `event_results` | **A5** | 要求に含めた**全イベント**について 1 件ずつ(正本 7-1 の A5)。並び順に意味を持たせない |
| `event_results[].d4`・`.d1`・`.d5` | A5 の `(D4, D1, D5)` | 要求で送った値を文字列・整数としてそのまま返す(L-1〜L-3) |
| `event_results[].a5_result` | A5 の結果 | `"受理"`・`"重複"`・`"拒否"`・`"退避"`・`"未処理"`(L-4 — 正本 2-5 の R-ACK-STATE の要素全集合) |
| `event_results[].rejection` | B3 の分岐と理由・O4 | **`a5_result` が `"拒否"` のときだけ持つ**。`kind` は `"内容起因"` または `"O4"`。`kind` が `"内容起因"` のとき `branch` は `"B3a"` または `"B3b"`(正本 7-1 の B3a・B3b)。`reason` は理由の内容(4-5) |
| `player_id_mappings` | **A4**(正本 4-4 の C1・C3・C4) | `a5_result` が `"受理"` または `"重複"` の**選手登録を行うイベント 1 件ごとに、その一時 ID の要素がちょうど 1 つある**(C1)。選手登録を行うイベントは、選手のその場登録(正本 5-5 の #6)と、その改訂版(#9 — 元の参加区分を継承する)。該当イベントが無い要求では持たない。要素は `temporary_id`(一時 ID — L-1)と `official_id`(正式 ID — **UUID の正規形の文字列**。表記は L-1 と同じ。選手 ID は `backend/src/pitchlog/db/sync_protocol/models.py` で `Uuid`)。再送で返す正式 ID は C3 に従う。**要素が欠けた ACK はクライアントが解釈しない**(2-5・正本 4-4 の C4) |

- **`advanced_d3` を `boundary_result` と一緒に返す**ので、B2・B3 で「どこで止まったか」をクライアントが特定できる(正本 6-3 の B2・B3 の通知列)。件数だけを返さない
- 再送で同じ要求が来たときに返す値は正本 7-1(A5・DI2)と 4-4 の C3 に従う。本書は形だけを決める

### 4-3. P3 の結果の本文(E-2)

**変更受理(200)**:

```json
{
  "boundary_result": "変更受理",
  "accepted_result": {
    "target_reference": {"game_id": "<UUID>", "d4": "<不透明な文字列>", "d1": 12},
    "expected_version": "<V11 — 要求で送った値>",
    "d5": "<UUID>",
    "confirmed_content": {},
    "accepted_at": "2026-10-09T14:03:21+09:00"
  }
}
```

**拒否(409)**:

```json
{"boundary_result": "B8", "current_version": "<対象の現在の確定版>"}
```

| キー | 正本 ID | 規約 |
| --- | --- | --- |
| `boundary_result` | P3 の結果 | `"変更受理"`・`"B8"`・`"B9"`・`"B13"`・`"B14"`(L-4)。200 なら `"変更受理"`、409 なら他の 4 つ |
| `accepted_result` | **I6** の受理結果 | 変更受理のときだけ持つ。`target_reference`(V10)・`expected_version`(要求時の V11)・`d5`(V1)・`confirmed_content`(サーバーが確定した変更内容)・`accepted_at`(サーバー確定時刻 — L-5)の 5 つ。**キー名 `accepted_at` は正本 7-1 の I6 の表記と同じ** |
| `current_version` | B8 で伝える**現在版** | B8 のときだけ持つ(正本 8-3「B8 は期待版不一致と現在版」)。表現は V11 と同じ(3-4) |
| `b9_cause` | B9 の成立条件のどれか | B9 のときだけ持つ。`"記録権不保持"`(進行中の P3 の V12 不成立 — VF5)または `"旧復旧世代"`(要求作成時の復旧世代の不一致 — 正本 6-2 の P3 の③-b)。正本 6-3 の B9 は両者で利用者への帰結を分けている |
| `reason` | B14 の理由 | B14 のときだけ持つ(正本 6-3 の B14「理由を顕在化」)。中身は 4-5 |

- **B13 は `boundary_result` だけを持つ**(先着の保存済み操作の内容を返さない — 正本 6-3 の B13・4-5)
- **409 の本文は、試合が自テナントに属することを③で確認した後にしか返らない**(正本 6-2 の P3 の段階順)ので、内容を含めても存在は漏れない

### 4-4. B6・B12 の 404 の同一性

- B6・B12 の応答は、**同じ path で自テナントに存在しない試合を指したときの 404 と、ステータス・ヘッダー・本文が同一**でなければならない(正本 6-5「自テナントに存在しない試合と同じ応答」・要件書 [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034)・[NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010))。既存の規律(`backend/tests/test_api_conventions.py` の `test_forbidden_response_is_hidden_as_not_found` — 403 を 404 と同一の本文へ写す)と同じ扱い
- 本文に `boundary_result`・理由・D3・A5 を含めない(正本 6-5)
- 監査のための記録はサーバー側のログに残す(正本 6-5 の「監査」行)

### 4-5. 理由(`reason`)の中身

- B3a・O4・B14 の `reason` は **JSON の値**として運ぶ。**中身(理由の語彙・構造)は本書で決めない** — 内容の検証(正本 6-2 の⑦ / P3 の⑥)を実装する単位が決める(送り先 — 6 節)。frontend の既存の受け取り側も `reason` を解釈しない(`frontend/src/lib/sync/rejectionReason.ts` の `B3ContentRejection.reason: unknown`)
- B3b の `reason` は、先着の原本の内容を含めない(正本 4-5 の衝突時の扱い — 先着の保存済み操作は変えず、後着を受理しない)
- **クライアントは `reason` を利用者へ表示するとき自動エスケープを通す**(要件書 [NFR-023](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-023))

## 5. 既存 DTO への写像と差分

既存の frontend DTO(`frontend/src/lib/sync/`)は transport-neutral で、**wire ⇄ DTO の変換(以下「codec」)は入口 PR が持つ**(plan.md 原則 W-2)。本節は codec が何を写すかと、DTO に受け口が無い値(差分)を決める。**U-S1 のサービス層の型との対応は本節で扱わない**(型がまだ無い — 6 節で入口 PR の義務にする)。

### 5-1. 要求の写像

| wire | DTO | 写し方 |
| --- | --- | --- |
| E-1 の `events` / E-2 の `change` | `SyncEvent` の並び / `SyncEvent` 1 件 | 要素ごとに下の行で写す |
| E-1・E-2 のイベントのキー(`d5`・`d1`・`d4`・`game_id`・`event_kind`・`d2`・`payload`・`state_diff`・`replacement_state`・`target_reference`・`expected_version`) | `syncEvent.ts` の `SyncEvent.fields` の `V1`〜`V11` | 2-6 の対応表の行どおりに 1 対 1 で写す。`fields` に無いスロットはキーごと省く(3-2) |
| `target_reference` の `game_id`・`d4`・`d1` | `TargetEventReference` の `試合`・`対象の D4`・`対象の D1`(`syncEvent.ts` の `TARGET_EVENT_REFERENCE_ELEMENTS`) | **要素名を明示的に対応させる**(DTO の要素名は日本語なので K-3 の機械変換は当たらない) |
| `recording_right_proof` | `requestBoundary.ts` の `RequestBoundaryEnvelope.requestValues` の `V12` | そのまま写す。終了後の P3 で `V12` が無ければキーごと省く |
| E-2 の `recovery_generation` | `RequestBoundaryEnvelope.recoveryGenerationAtCreation`(`path` が P3 のとき) | そのまま写す |
| (運ばない) | `RequestBoundaryEnvelope.recoveryGenerationAtCreation`(`path` が P1・P2・P4 のとき) | **E-1 には載せない**。正本は要求作成時の復旧世代を P3 の要求境界にだけ結合し(正本 4-3-A 末尾の段落・6-2 の P3 の③-b)、D1 付き経路は V12 の結合(VF6)で扱う。この値はクライアント内部だけで使う |
| (運ばない) | `RequestBoundaryEnvelope.p3State`(進行中 / 終了後) | **wire に載せない**。進行中か終了後かはサーバーが試合の状態から決める(正本 4-3-A の W4) |
| E-1 / E-2 の選択 | `RequestBoundaryEnvelope.path` | P1・P2・P4 → E-1、P3 → E-2 |

### 5-2. 応答の写像

| wire | DTO | 写し方 |
| --- | --- | --- |
| ACK の `advanced_d3`・`event_results`(`d4`・`d1`・`d5`・`a5_result`)・`player_id_mappings`(`temporary_id`・`official_id`) | `ackEnvelope.ts` の `D1AckEnvelope`(`advancedD3`・`eventResults`〔`d4`・`d1`・`d5`・`a5Result`〕・`playerIdMappings`〔`temporaryId`・`officialId`〕) | K-3 の名前の変換だけで写す。`a5_result` の値は正本の語のままで、DTO も同じ語で照合する(`canonOracle.ts` の `readCanonAckStateResults` — R-ACK-STATE の要素) |
| ACK の `boundary_result` | `ackAdapter.ts` の `D1AckAdapterInput.boundaryResult` | **封筒とは別の入力として、`"B1"`〜`"B4"` の ID 文字列をそのまま渡す**(`boundaryResults.ts` の `parseAckBoundaryResult` が ID 文字列を受け取り、`AckBoundaryResult` を返す) |
| ACK の `event_results[].rejection` | `D1AckAdapterInput.b3Rejection`(`rejectionReason.ts` の `parseB3Rejection` — `kind`・`branch`・`reason`) | 現在の `b3Rejection` は 1 件だけを受け、アダプタはそれを拒否されたすべてのイベントの区分に使う(`ackAdapter.ts` の `classifyB3`)。正本 7-1 の A5 の再掲に対応できないので、写し方は差分 X-1 で変える |
| B5〜B7(401・404・408・500・502・503・504・応答なし) | (`D1AckAdapterInput` には渡さない — `envelope` が必須で、`parseAckBoundaryResult` は ACK の無い結果を拒否する) | HTTP ステータスから 4-1 の表で結果を決める。受け口は差分 X-3 |
| P3 の `boundary_result`・`accepted_result`(`target_reference`・`expected_version`・`d5`・`confirmed_content`・`accepted_at`) | `p3Result.ts` の `P3ResultEnvelope`(`boundaryResult`・`acceptedResult`〔`targetReference`・`expectedVersion`・`d5`・`confirmedContent`・`acceptedAt`〕) | K-3 の名前の変換で写す。`target_reference` の要素は 5-1 と同じ明示の対応。`boundary_result` は `readCanonP3BoundaryResults` で正本の結果へ引き当てる。**既存の受け取り側は受理結果の各値を端末が保持する受理期待と `Object.is` で照合する**(`p3Result.ts` の `parseP3ResultEnvelope`)ので、オブジェクトの値(`confirmed_content` など)は差分 X-6 の手順で渡す |
| P3 の `current_version`・`b9_cause`・`reason` | (受け口なし) | 差分 X-2 |
| B10〜B12(5xx・応答なし・401・404) | `P3ResultEnvelope` は返らない | HTTP ステータスから 4-1 の表で結果を決める。受け口は差分 X-3 |
| S-1 違反(422)・4-1 の表に無いステータス・2-5 の解釈できない応答 | (受け口なし) | 差分 X-3 |
| 共通エラー封筒の `error`・`error.message`・`error.fields`・`error.fields[].location`(4-1) | (受け口なし) | 結果の判定には使わない(判定は HTTP ステータスだけで行う — 4-1)。S-1 違反の `location` は顕在化の診断に使う。差分 X-3 |

### 5-3. 差分一覧(入口 PR の作業)

**既存 DTO と受け取り側の入力のキー集合は変えない**。`frontend/src/lib/sync/prohibitions.spec.ts` が封筒(`D1AckEnvelope`・`D1AckEventResult`・`D1AckPlayerIdMapping`・`P3AcceptedResultEnvelope`・`P3RejectedResultEnvelope`・`I6AcceptedResult`)と、アダプタの入力(`AckAdapterRequest`・`D1AckAdapterInput`・`P3ResultAdapterInput`)・注入のキー集合を固定している。**キー集合を保ったまま値の型を変える必要があるのは X-1 だけ**で、その理由を X-1 に書く。

| # | 差分 | DTO の現状 | 入口 PR がすること |
| --- | --- | --- | --- |
| **X-1** | ACK の拒否の理由を**イベントごとに**分類すること(正本 7-1 の A5) | `D1AckAdapterInput.b3Rejection` は 1 件だけで、`classifyB3` が拒否されたすべてのイベントに同じ区分を返す | **必須**: `b3Rejection` の値を `(D4, D1, D5)` ごとの理由の並びに変え(**キー名 `b3Rejection` は変えない** — `prohibitions.spec.ts` のキー集合を保つ)、`classifyB3` がイベントのキーで理由を引き当てるようにする。**既存テストの追随**: `frontend/src/lib/sync/ackAdapter.spec.ts` の、`b3Rejection` に単一のオブジェクトを渡す 2 件の入力と期待値をイベント単位へ直す。**理由**: 現状のままでは、区分の違う拒否が 1 つの ACK に並んだとき、キューが誤った区分で要操作へ移す(正本 7-2・6-4) |
| **X-2** | P3 の `current_version`(B8)・`b9_cause`(B9)・`reason`(B14) | `P3RejectedResultEnvelope` は `boundaryResult` だけ | **アダプタを通さず**、通知の層(`frontend/src/lib/sync/syncNotices.ts` など)へ渡し、正本 8-3 の P3 の通知行を表示できるようにする。キューと I6 の状態遷移には使わない値なので、アダプタの入力のキー集合を変えずに済む |
| **X-3** | ACK・結果が返らない表れ方(B5〜B7・B10〜B12 の HTTP ステータス・応答なし)、S-1 違反、4-1 の表に無いステータス、2-5 の解釈できない応答、共通エラー封筒の 4 キー | 通信層が無い(`fetch`・`axios` は 0 件 — research.md 3 節)。ACK の無い結果をアダプタへ渡す口も無い | codec と通信層を作り、4-1 の表どおりに振り分ける。ACK の無い結果はアダプタを通さない経路で扱う。S-1 違反と解釈できない応答はキューと P3 の保持内容を変えずに顕在化する(2-4・2-5) |
| **X-4** | `target_reference` の要素名(wire は `game_id`・`d4`・`d1`、DTO は日本語) | — | codec で明示的に対応させる(5-1) |
| **X-5** | wire の値の表現の検査(L-1 の UUID の正規形・L-2 の整数・L-5 のオフセット付き時刻) | 既存の受け取り側は値を不透明に扱い、形式を検査しない(`ackEnvelope.spec.ts`・`p3Result.spec.ts` がソースに形式検査が無いことを検査している) | **形式の検査は codec に置き、既存の受け取り側には足さない**(既存の spec を壊さない) |
| **X-6** | P3 の受理結果のオブジェクトの値(`confirmed_content`、オブジェクトの場合の `expected_version`)の照合 | `parseP3ResultEnvelope` は受理期待と `Object.is` で照合する。wire から作ったオブジェクトは端末の保持する値と参照が違うので、内容が同じでも拒否される | codec が wire の値と端末の受理期待の値の**構造の一致**を確かめ、一致したら**端末が保持する値(同じ参照)**を受け取り側へ渡す。一致しなければ 2-5 の解釈できない応答として扱う |

## 6. 送り先と入口 PR の義務

### 6-1. 本書で決めないものの送り先

plan.md 2 節「やらないこと」の全行と、本書の各節で決めないとした値の受け取り先。**定数の値は 1 つも書かない**(plan.md 原則 W-6)— 書くのは「誰が・何を根拠に決めるか」だけ。

| # | 決めないもの | 送り先 | 決め方の条件 | 出どころ |
| --- | --- | --- | --- | --- |
| **N-1** | E-1 の件数の上限・要求本文の大きさの上限 | 入口 PR | 実回線・実クエリで測り、要件書 [NFR-002](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-002) の同期の時間の要求を満たす値にする。上限超過の表れ方(413 など)は 4-1 の表に足してから導入する | 3-4・4-1・正本 10-1 論点 18 |
| **N-2** | 再送の間隔・バックオフ・`Retry-After` の有無と値 | 入口 PR | 同上。B2・B7・B10 の再送の意味規則(正本 6-3)は変えない | 4-1・正本 6-3 の B2・B7 |
| **N-3** | 8-1 のトランザクションのまとめ方(1 件ずつ / 連続範囲を 1 つに) | U-S1(適用の核)と入口 PR の境界 | 正本 8-1「選択は (B) 論点 18 へ送る」。意味規則ではなく性能の都合なので、実測で決める | plan.md 2 節 |
| **N-4** | 流量制限(429 など)を入れるか | 入口 PR | 入れるなら 4-1 の表に足してから。B7・B10 の成立条件に当たるかで群を決める | 4-1 |
| **N-5** | V12 の物理形式・寿命・端末内の格納先・更新方法・長さの上限 | U-R1(TSK-392) | 発行する側が決める。wire は不透明な文字列として運ぶ(L-3)。承認済み(plan.md 4 節「人間の判断が要る点」①) | L-3・3-4 |
| **N-6** | D4・復旧世代の生成方式・物理形式・保存場所・長さの上限(論点 17 の一部) | U-R1(TSK-392) | 391 の回答(D4・復旧世代は U-R1 と読む — U-R1 とは未合意)。wire は不透明な文字列として運ぶ(L-3) | L-3・plan.md 2 節 |
| **N-7** | D5 の物理形式(論点 17 の一部) | U-S1(TSK-391) | 決定済み(`uuid`)。wire は L-1 の正規形で運ぶ | L-1 |
| **N-8** | V7 ペイロード・V8 状態差分・V9 置換の状態の、種別ごとの中身 | 各イベント種別を実装する単位 | wire の層では検査しない(S-2)。内容の検証(正本 6-2 の⑦ / P3 の⑥)を実装する単位が決める | 3-4 |
| **N-9** | V6 D2 の表現 | 正本 10-1 論点 26 の受け取り先(数値型は TSK-250) | 論点 26 の条件のとおり | 3-4 |
| **N-10** | V11 期待版の表現 | 変更イベントを実装する単位(U-G2) | 対象の確定版の物理形式に従う | 3-4 |
| **N-11** | B3a・O4・B14 の理由(`reason`)の語彙・構造 | 内容の検証を実装する単位 | wire は JSON の値として運ぶ(4-5)。表示は自動エスケープ(要件書 [NFR-023](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-023)) | 4-5 |
| **N-12** | 論点 19(ローカル書き出し・取り込みのファイル形式)・論点 22(閲覧端末への配信方式) | 正本 10-1 の各受け取り先 | 論点 18 の外 | plan.md 2 節 |
| **N-13** | 補正の内容の配信(正本 8-3) | TSK-441(通知契約 — 正本 11-4 の U-15) | ACK に補正内容の欄を設けない(4-2)。配信の形は通知契約と一緒に決める | plan.md 2 節 |
| **N-14** | 引き継ぎ要求(要件書 [FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013))・管理コンソールの退避の閲覧と書き出しの API | U-R1 / TSK-346 | 同期 wire ではない | plan.md 2 節 |
| **N-15** | `route_id` の付与・`contracts/authz/route-registry.json` の FR-012 行の扱い・越境テスト再実行ゲート | 入口 PR | `docs/design/data-model.md` 12-4 の「経路と入口の定義」(入口を開く PR が同一 PR で `route_id` を与える)と「越境テスト再実行ゲート」(実スキーマに対する通過条件・最低要求・測定経路・**通過判定の PR への記録**)。EP-11 | plan.md 2 節 |
| **N-16** | 機械可読な API スキーマ(OpenAPI など)の置き場・ハーネス設計書 4 章の `contracts/` の記述の揺れ・`contracts/README.md` の「将来 OpenAPI を収載」 | TSK-346 | API 全体の契約の正本を新設するときに決める。それまでの入口 PR には U-00 の既決(生成 OpenAPI はコミットしない)が効く | plan.md 2 節 |
| **N-17** | S-1 違反を正本の結果として書き足すか、および**同じ要求を送り直しても解消しない場合の再送の止め方・再開の条件**(未解決 WU-1) | TSK-346 | API 全体のエラーの規律を正本化するときに判断する。どちらもキューの意味規則に触れるので、決めるなら同期正本の改訂(確定ゲート)を伴う。それまでは 2-4 のとおり(キューの状態を変えず、送信は正本 7-2 の当該状態の扱いに従う) | 2-4 |
| **N-18** | U-S1 のサービス層の型(`sync/model.py`)と wire キーの対応 | 入口 PR | U-S1 の型定義が develop に入った後、2-6 の対応表の各行を型の名前へ写す | 5 節の柱書 |
| **N-19** | 移行イベントのペイロードを同期 wire 型と共有するか | データ移行を実装する単位 | 移行は同期 API を経由しない(`docs/design/data-model.md` 12-3) | plan.md 2 節 |
| **N-20** | イベントの時刻属性 | TSK-327(正本 11-4 の U-11 — 要件書改訂) | 順序の決定には使わない(G-4) | G-4 |
| **N-21** | 製品コードとテスト(Pydantic DTO・ルータ・codec・通信層) | 入口 PR | 本書に従って作る。作るものとテストは 6-2 の EP-1〜EP-11 | plan.md 2 節 |
| **N-22** | B5・B11(認証失効)の実装 | 入口 PR | 入口が無いと発生しない(U-S1 の計画書が入口 PR へ送っている)。テストは EP-7 | plan.md 2 節 |
| **N-23** | 正本の改訂(同期正本 10-1 の行の書き換えを含む) | — / TSK-346 | **本書は正本を改訂しない**(意味規則を変えない — 1-1)。意味規則を変える必要が出たら正本へ戻る(正本 10-1 の表の直後の段落)。正本への収載は TSK-346 | plan.md 2 節 |
| **N-24** | `.claude/core-areas.json`・`scripts/core_guard.py` の `AREA_PATH_ADDITIONS` | 入口 PR(EP-9) | **本タスクでは変更不要**(文書だけ)。追加が要るかは入口 PR が EP-9 で判断する | plan.md 2 節 |

### 6-2. 入口 PR の義務

入口 PR は E-1・E-2 を製品の外から到達できる入口として開く PR である。本書に従って次を**同じ PR に含める**。

| # | 義務 | 根拠 |
| --- | --- | --- |
| **EP-1** | **E-1・E-2 それぞれについて、製品の外から直接叩く越境テスト**(他テナントの試合を指したとき 4-4 の 404 になる) | 要件書 [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)・[NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)・`docs/design/data-model.md` 12-4(入口を開く PR は同一 PR にその入口を製品の外から直接叩くテストを含む) |
| **EP-2** | **B6・B12 の 404 が、自テナントに存在しない試合の 404 とステータス・ヘッダー・本文で同一**であることのテスト | 4-4・正本 6-5・要件書 [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034) |
| **EP-3** | **S-1 違反の応答が試合の識別の値によらず同じ**(存在する自テナントの試合・存在しない試合・他テナントの試合で同一)であることのテスト | 2-4・正本 6-5 |
| **EP-4** | **wire ⇄ DTO の往復テスト** — backend(pytest)は 3 節・4 節の各キーの形、frontend(Vitest)は codec が 5 節の写像どおりに既存の受け取り側へ渡すこと。X-6 の構造の一致の照合を含む | 要件書 [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)・5 節 |
| **EP-5** | **5-3 の差分 X-1〜X-6** の作業(X-1 の既存テストの追随を含む) | 正本 7-1 の A5・I6・6-3 の B3・7-2・8-3・4-4 の C1〜C4(各差分が支える意味規則)/ 5-3 |
| **EP-6** | **4-1 の表の全行**(ACK・P3 の結果・401・404・5xx・応答なし・422・表に無いステータス)について、クライアントがキューと P3 の保持内容をどう扱うかのテスト | 4-1・2-4・2-5・正本 6-3・7-2 |
| **EP-7** | **B5・B11(認証失効)でキューを失わず、再ログイン後に同じキュー・同じ D5 から再開する**ことのテスト。通信断からの復帰の E2E との接続 | 正本 6-3 の B5・P3 の独立境界結果の B11・要件書 [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012)(認証失効時もキューを保持)。通信断の E2E は [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(c) |
| **EP-8** | **V12(`recording_right_proof`)をログに書かない**。S-1 違反の記録(2-4)にも要求本文の V12 を含めない | **(B) 本書の設計判断** — V12 はサーバーが発行する記録権の証明(正本 4-3 の V12)であり、漏えいを避ける。**ログの扱いにかかわらず、VF6 の照合は処理段階⑤で必ず行う** |
| **EP-9** | **wire の DTO を置く場所と、既存の機械検査の扱い**: `backend/tests/test_api_conventions.py` は `backend/src/pitchlog/api/` に同期の語彙(`idempotenc`・`generation` など)があると落ち、凍結資産 TB002(`contracts/tenant_boundary/base-allowlist.json` 条件 2 — 検査器は `scripts/check_tenant_boundary_bypass.py`)は `backend/src` の変更した識別子を検査する(`recovery_generation` は `_generation` のパターンに当たる)。DTO を置く場所(コア領域の paths に入るか)と、これらの検査の扱いを、`.claude/core-areas.json` の窓口の調整(469 master)を含めて入口 PR が決める | ハーネス設計書 6.3(コア領域の paths の追加は敵対レビューと人間承認)/ research.md 3 節 |
| **EP-10** | **6-1 の N-1・N-2・N-4・N-15・N-18** を入口 PR の中で決める(N-1・N-2・N-4 は測定の記録を残す) | 要件書 [NFR-002](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-002)(N-1・N-2)・正本 10-1 論点 18(N-1・N-2・N-4)・`docs/design/data-model.md` 12-4(N-15)/ 6-1 |
| **EP-11** | **越境テスト再実行ゲートの通過判定**を、E-1・E-2 の入口について同じ PR で行い、**判定を PR に記録する**(誰が・いつ・**どの実スキーマに対して越境テストの green を確認したか**・どの入口〔`route_id` と method・path の組〕について) | `docs/design/data-model.md` 12-4「越境テスト再実行ゲート」の通過条件・判定の記録 |

### 6-3. TSK-346 が収載するときに矛盾させてはならない点

TSK-346 は本書を参照・収載する側である(持ち主の裁定 — plan.md 1 節)。**次はいずれも本書の同期 API(E-1・E-2)についての決定であり、同期以外の API の横断的な規律(エラー体の形・ステータスコードの規律)は TSK-346 の射程として縛らない**。TSK-346 は同期 API の契約を収載するとき、次と矛盾させない。変える必要が出たら本書を改め、入口 PR と U-S1 へ知らせる。

| # | 点 | 本書の節 |
| --- | --- | --- |
| **TK-1** | 同期 API で他テナントの試合を指したときは、存在しない試合と同一の 404(理由を本文に含めない) | 4-4 |
| **TK-2** | 同期 API の 4-1 の群④と S-1 違反(422)の本文は、理由コードを持たない共通エラー封筒(`ErrorEnvelope`)(B6・B12 は 4-4 の同一性が優先)。**P3 の拒否(409)の本文は P3 結果本文**(4-3)で、共通エラー封筒に置き換えない | 4-1・4-3 |
| **TK-3** | 同期 API の JSON のキーは snake_case | K-1 |
| **TK-4** | 同期 API では 422 を wire の形の誤り(S-1 違反)に使い、同期の境界結果には当てない | 4-1・2-4 |
| **TK-5** | 同期の結果の列挙値は正本の安定 ID・正本の語をそのまま使う | L-4 |
| **TK-6** | 同期 API の path は `/games/{game_id}/sync/` の下 | 3-1 |

## 未解決・検討メモ

- **WU-1 S-1 違反は正本の結果集合の外にある**(2-4)。正本の処理段階表は、要求の形が wire の規約に合わない場合の結果を持たない。本書は境界結果を作らず、成立条件も広げずに「サーバーは状態を変えない・クライアントはキューを変えず顕在化する」とだけ決めた。**同じ要求を送り直しても解消しない場合の再送の止め方・再開の条件は決めていない**(正本 7-2 の状態の扱いに委ねている)。**正本に結果として書き足すかは、API 全体のエラーの規律を決める TSK-346 が正本化するときに判断する**(送り先 — 6 節)
