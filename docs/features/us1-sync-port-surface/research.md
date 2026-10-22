---
feature: us1-sync-port-surface
created: 2026-10-16
---

> 文書提出上の注意: 本資料の実装済み・試験件数は別枝 `feature/us1-sync-port-surface` の候補履歴である。`feature/us1-stop-contract-docs` は文書だけを提出し、製品コード・実Port・HTTP提供を含めない。

# 調査: U-S1 の公開面と同期の失敗分類(TSK-506 への接続契約)

読み取り元: develop `e7e8d3a4`(U-S1 マージ後)。TSK-506 の worktree(`feature/tsk506-sync-http-entry`)は読むだけ。各主張にファイル:行の典拠を付け、推論は [推論] と記す。2 つの調査を収録する。

- A. U-S1 の公開面(公開関数・型・失敗境界・担当・U-R1 の決定待ち・着手条件と確認条件)
- B. 同期要求の失敗時の振る舞いと、恒久的な失敗の正本上の置き場

# A. U-S1 の公開面(TSK-506 の HTTP 入口から見た境界)— 下書き

- 作成: 2026-10-16(読み取りだけ。リポジトリ・worktree は変更していない)
- 対象のコード: `/home/ymdms/projects/pitchlog` の develop **`e7e8d3a4`**(依頼文の `966d7a38` の後に #141 が入っている。`966d7a38..e7e8d3a4` の間で `backend/src/pitchlog/sync/` は**差分 0**。`repositories/transaction.py` に `run_function` が +34 行入っただけ — `git diff --stat` で確認済み)
- 典拠の表記: パスは `backend/src/pitchlog/` を省略する(例 `sync/apply.py:292`)。正本は `SP`(= `docs/design/sync-protocol.md`)、wire 設計は `WS`(= `docs/features/sync-wire-schema/design.md`)、506 の計画は `506/plan.md`(= worktree `feature-tsk506-sync-http-entry` の `docs/features/tsk506-sync-http-entry/plan.md`)
- 印: **[検証]** = コードまたは文書の該当行を読んで確かめた / **[推論]** = 読んだ行から導いたが、実行や担当の回答では確かめていない
- 依頼文の「SP 12 の記録権との境界」は、SP の 12 章が「検証記録」なので、記録権との境界表である **SP 9-2(1404 行〜)** を読んだ

---

## 0. 結論(先に)

1. 入口が呼ぶ関数は **`sync.apply.apply_sync_request` の 1 つ**と、要求を作る **`SyncRequest.from_payload`** の 2 つで足りる。トランザクションはすべて U-S1 が開き、入口は `TenantContext` を渡すだけ [検証]
2. ただし**現状の develop のままでは、入口から呼んでも製品では動かない**。ポートの登録表 `PORT_IMPLEMENTATIONS` が空なので、自テナントに実在する試合への要求は全経路で `PortRegistrationError` になる(不存在・他テナントは B6/B12 が先に返る)[検証]
3. U-S1 が境界結果まで決めて返すのは **B1〜B4(ACK)・B6・B7・P3 の変更受理/B8/B9/B10/B12/B13/B14**。**S-1 違反・未登録ポート・前提違反(`P1PreconditionError`)・不変条件の `RuntimeError`・DB 例外・ポート(RG1 以外)の例外は、例外のまま入口へ上がる**。写像は U-S1 にない [検証]
4. 「全取消」の単位は**イベント 1 件のトランザクション**で、要求全体ではない。途中で例外が上がっても、それより前の D1 の確定は残る(正本も要求全体の原子性を保証しない — SP 7-1 の A1)[検証]
5. 506 が期待する「P1/P2 混在バッチを 1 つの ACK で処理する公開型」は**存在しない**。`SyncRequest.path` は要求に 1 つで、経路名は D5 の指紋に入る。さらに wire と U-S1 の値の対応(V5 の番号/リテラル、V10 のキー名、D4 の表現、`registrations`/`targets` の出所)が埋まっていない。7 節に一覧 [検証]

---

## 1. 公開関数

### 1-1. 入口が呼ぶもの

| 名前 | モジュール:行 | シグネチャ | 用途 |
| --- | --- | --- | --- |
| `apply_sync_request` | `sync/apply.py:292-301` | `(context: TenantContext, request: SyncRequest, rights: RecordingRightsPort, projection: ProjectionPort, validator: ContentValidationPort, *, registrations: Mapping[str, PlayerRegistration] \| None = None, targets: Mapping[str, P1Target] \| None = None) -> ApplyResult` | E-1・E-2 の両方。`request.path == "P3"` なら P3 へ分岐(`sync/apply.py:307-311`) |
| `ApplyResult`(型別名) | `sync/apply.py:62` | `AckResult \| ChangeResult \| Literal["B6", "B7"]` | 戻り値 |
| `SyncRequest.from_payload` | `sync/model.py:230-317` | `(path: ApplicationPath, game_id: str, payload: object) -> SyncRequest` | URL の試合 ID と JSON 本文から S-1 を検査して要求を作る。違反は `RequestShapeError` |
| `RequestShapeError` | `sync/model.py:56-57` | `ValueError` の派生 | S-1 違反(境界結果ではない) |
| `require_tenant_access` | `api/tenant_access.py:12-39` | FastAPI 依存。`TenantContext` を返し、失敗は `RequestGateError("credential")` | B5/B11。`TenantContext` を発行できる製品の入口はこれだけ(`repositories/tenant_context_contract.py:29-35` の allowlist)[検証] |

- docstring は「B5・B11 は認証を所有する HTTP 入口が判定する。B6・B7 は ACK を持たないためコードだけを返し、P3 は専用の独立結果を返す」(`sync/apply.py:302-306`)[検証]
- U-S1 の設計も「`sync/apply.py` の公開関数は、認証・認可済みの `TenantContext` と要求オブジェクトを受け、結果オブジェクトを返す。wire 形式への写像は入口 PR が持つ」(`docs/features/us1-sync-apply-core/design.md:29`)[検証]

### 1-2. 入口が呼んではいけないもの(内部)

| 対象 | 理由・典拠 |
| --- | --- |
| `sync/apply.py` の `_preflight_d1`・`_run_d1_event`・`_escrow_without_right`・`_replay_existing`・`_event_state`・`_BatchPreflight` | 先頭 `_`。段階順(③→③-a→④→⑤→⑥)と DI5 の合成は `apply_sync_request` の中でしか保証されない(`sync/apply.py:313-434`)[検証] |
| `apply_p1_event`(`sync/prefix_path.py:816`)・`apply_p2_event`(`sync/ordering.py:100`)・`apply_rejection_or_escrow`(`sync/rejection.py:212`)・`apply_p3_change`(`sync/change_path.py:281`) | 先頭 `_` ではないが**局所経路**。単独で呼ぶと ③-a〜⑥ の要求単位の判定(D5 の全件先行分類・⑤ の要求単位判定・⑥ の欠落停止・ACK 合成)を飛ばす。docstring も「要求全体の ACK はここでは作らない」(`sync/prefix_path.py:127`・`sync/rejection.py:52`)[検証]。**入口は必ず `apply_sync_request` を経由する**[推論 — 公開・非公開の明示的な宣言(`__all__`)は `sync/` に無い] |
| `tenant_transaction_scope`・`_TenantTransaction`・`_sync_apply_active` | 入口が自分でスコープを開いて包み直さない(506/plan.md:47 も「HTTP は適用核の transaction を包み直さない」)。適用中の印が立っている間は新しいスコープを開けない(`repositories/transaction.py:43-51, 212-213`)[検証] |
| `sync/ports.py` の `_issue_port_writer`・`PortWriter` の生成・`PORT_IMPLEMENTATIONS` の書き換え | 書き手は適用核だけが発行する(`sync/ports.py:28-62`)。登録表の変更はコア領域(`sync/ports.py:1-8`)[検証] |
| `sync/crash_points.testing_crash_hook` | 試験専用(`sync/crash_points.py:46`)。製品では `reach` は何もしない(`sync/crash_points.py:38-43`)[検証] |

### 1-3. 実行の性質(入口の書き方に効くもの)

- **同期関数**である(SQLAlchemy の同期 `Session` — `repositories/transaction.py:224`)。既存の router は `def`(例 `api/routers/players.py:124`)。E-1/E-2 も `def` で書けばスレッドプールで動く [推論]
- **1 要求あたりのトランザクション数**: D1 付き経路は「③ の存在確認 1」+「④ の先行分類 1(読み取りだけ)」+「イベントごとに ③ の再確認 1 + 適用 1」(`sync/apply.py:314, 319, 352-398` と `sync/prefix_path.py:785-790`・`sync/rejection.py:240-245`)。P3 は 2(`sync/change_path.py:291-296`)[検証]
- **スコープごとに engine を作る**(`Session(create_database_engine())` — `repositories/transaction.py:224`、`db/engine.py:427-453` は呼ぶたびに `create_engine`)。N-1(件数上限)の性能測定に効く [検証 — 接続コストの大きさは未測定]

---

## 2. 型

### 2-1. 引数

**`SyncRequest`**(`sync/model.py:154-228` — frozen・`__new__` で S-1 検査)

| フィールド | 型 | 規則(典拠) |
| --- | --- | --- |
| `path` | `Literal["P1","P2","P3","P4"]`(`sync/model.py:32`) | 要求に 1 つ。**P5 は無い**(内部の拒否経路)[検証] |
| `game_id` | `str`(UUID 正規形・小文字) | `sync/model.py:60, 64-66, 177-178`。全イベントの `game_id` と一致(`:216-217`) |
| `events` | `tuple[SyncEvent, ...]` | D1 付き経路は空不可・D1 は 1〜2^53-1・重複不可・全件の D4 が要求の D4 と同じ(`:195-215`)。P3 は 1 件だけ(`:183-185`)。**D5 の要求内重複は検査しない**(`test_duplicate_d5_is_left_for_processing` — `backend/tests/test_sync_apply_model_ports.py:256`。WS 3-2 の表とも一致) |
| `d4` | `str \| None` | D1 付き経路は空でない文字列が必須、P3 は不可(`:188, 204-205`)。`from_payload` は先頭イベントの `d4` を要求の D4 にする(`:315`) |
| `recovery_generation` | `str \| MissingValue` | P3 は空でない文字列が必須、D1 付き経路は不可(`:186-187, 198-203`) |
| `v12` | `StageValue`(= `object`。欠落は `ABSENT`) | **型の層で検査しない**(`:30-31, 163, 225`)。wire の `recording_right_proof` |

**`SyncEvent`**(`sync/model.py:103-151`): `d5`・`game_id`(UUID 正規形)・`d1: int | None`・`d4: str | None`・`v5`〜`v11: StageValue`(欠落は `ABSENT`、JSON は不変化 — `freeze_json` `:83-93`)。wire キーとの対応は `from_payload` が持つ(E-1 `:279-309`、E-2 `:236-262`)[検証]

**`registrations: Mapping[str, PlayerRegistration]`**(キー = D5 文字列 — `sync/apply.py:354`)。`PlayerRegistration(temporary_id: UUID, team_record_id: UUID, name: str, roster_status_key: str)`(`sync/prefix_path.py:106-113`)。その場登録(`player_registration`)の選手作成値 [検証]

**`targets: Mapping[str, P1Target]`**(キー = D5 — `sync/apply.py:355`)。`P1Target(game_id: UUID, generation: int, d1: int)`(`sync/prefix_path.py:116-122`)。docstring は「U-R1 が V10 を解決した undo の対象スロット」[検証]

**ポート**(`sync/ports.py:65-102` — Protocol):

| ポート | メソッド | 所有(典拠) |
| --- | --- | --- |
| `RecordingRightsPort` | `read_rg1_before_d5(writer) -> bool` / `check_rg1_before_commit(writer) -> bool` / `is_recovery_generation_current(game_id: str, supplied: str, writer) -> bool` / `holds_recording_right(game_id: str, d4: StageValue, v12: StageValue, writer) -> bool` | U-R1(TSK-392)。署名は U-S1 計画書 8 節で採用済み(`docs/features/us1-sync-apply-core/plan.md:238-241`) |
| `ProjectionPort` | `apply(event: SyncEvent, writer) -> None` | U-X1(506 の research.md:17 の読み — U-S1 計画書 2 節「やらないこと」) |
| `ContentValidationPort` | `validate(event: SyncEvent, writer) -> tuple[bool, str \| None]` | U-X1/U-G2(同上) |

ポートには `TenantContext` もハンドルも渡らない。渡るのは `PortWriter`(operation token だけを実行し、スコープ終了で失効 — `sync/ports.py:28-55`)[検証]

### 2-2. 戻り値

**`AckResult`**(`sync/model.py:331-365`)— D1 付き経路(P1/P2/P4)で ACK が返る場合だけ

| フィールド | 型 | 意味(正本) | 組み立て(典拠) |
| --- | --- | --- | --- |
| `boundary` | `Literal["B1","B2","B3","B4"]`(`:50`) | A3 の境界結果のうち ACK が返る 4 つ(SP:931) | `sync/apply.py:337, 347, 385, 422-432` |
| `d3` | `int` | 前進後(または据え置き)の D3。**要求の D4 の世代の D3** を起点にし後退させない(SP 6-1 R1・R4) | `sync/apply.py:111-128, 336, 408` |
| `a5` | `tuple[A5Result, ...]` | A5。**D1 昇順**に並ぶ(`sync/apply.py:329`)。要求の全イベントを 1 件ずつ | `sync/apply.py:334-406` |
| `b3_branch` | `Literal["B3a","B3b","O4"] \| None`(`:51`) | 停止した B3 の分岐。**要求に 1 つ**(停止イベントのものだけ) | `sync/apply.py:425-428` |
| `reason` | `str \| None` | 停止した B3 の理由 | `sync/apply.py:403-405, 428` |
| `temporary_id_mapping` | `Mapping[str, str]`(不変) | A4(一時 ID → 正式 ID) | `sync/apply.py:409-414` |

**`A5Result`**(`sync/model.py:320-328`): `d4: str`・`d1: int`・`d5: str`・`state: Literal["受理","重複","拒否","退避","未処理"]`・`reason: str | None`。**イベントごとの B3a/B3b/O4 の分岐は持たない**(7 節 G-6)[検証]

**`ChangeResult`** = `AcceptedChangeResult | RejectedChangeResult`(`sync/model.py:423`)— P3 だけ

- `AcceptedChangeResult`(`:368-406`): `target_reference`(キーは **`試合`・`対象の D4`・`対象の D1`** — `:389`、値は `sync/change_path.py:216-220` で `対象の D4` が **int**)・`expected_version`・`d5`・`confirmed_content`・`accepted_at: str`(ISO 8601 UTC — `sync/change_path.py:215`)・`boundary = "変更受理"`。再掲では保存済みの `accepted_at` を返す(`backend/tests/test_sync_apply_change.py:60` `test_p3_replay_keeps_original_accepted_at`)[検証]
- `RejectedChangeResult`(`:409-420`): `boundary: Literal["B8","B9","B10","B11","B12","B13","B14"]`・`d5`・`reason: str | None`。**B11 は U-S1 が作らない**(入口の判定)[検証]

**`Literal["B6","B7"]`**: D1 付き経路で ACK を返さない 2 つ(SP:931 の A3「B5・B6・B7 では ACK 自体が返らない」)[検証]

### 2-3. token 型(入口は触らない)

- 入口は operation token を作らない。`sync/tokens.py` の token は適用核とポートが `PortWriter.run` に渡すもの(`sync/tokens.py:1-4`)[検証]
- **発行と失効**: `PortWriter` は適用核だけが `_issue_port_writer` で発行し(`sync/ports.py:58-62`、`sync/gate.py` の `gated_writer` 72 行〜)、発行元スコープの終了(commit・rollback とも)で `_close` され、以後の `run` は `RuntimeError("PortWriter のトランザクションは閉じている")`(`sync/ports.py:45-55`)[検証]
- **`PortWriter.run_function` はまだ無い**。U-S1 計画書 8 節で「条件付き採用・U-R1 の新ステップ 6 で足す」(`plan.md:240`)。`_TenantTransaction.run_function` は #141 で develop に入った(`repositories/transaction.py:144`)[検証]

### 2-4. テナントのスコープと、誰がトランザクションを開くか

| 項目 | 内容 | 典拠 |
| --- | --- | --- |
| 開く主体 | **すべて U-S1**。`apply_sync_request` とその下の経路が `tenant_transaction_scope(context)` を開く | `sync/apply.py:87, 314`、`sync/prefix_path.py:785-790`、`sync/rejection.py:240-245`、`sync/change_path.py:291-296` [検証] |
| 束縛 | スコープの入口で `set_config('app.tenant_id', …, true)`(トランザクション局所)。`TenantContext` の発行証跡を検査 | `repositories/binding.py:58-80`、`repositories/transaction.py:200-254` [検証] |
| 原子境界 | `with session.begin()` の中で yield するので、スコープ内の例外は**そのトランザクションを rollback** | `repositories/binding.py:70-80` [検証] |
| 再入禁止 | 適用中の印(ContextVar)が立っている間は新しいスコープを開けない(ポートの独自スコープ防止) | `repositories/transaction.py:39-51, 212-213` [検証] |
| 入口の義務 | `Depends(require_tenant_access)` で得た `TenantContext` をそのまま渡す。入口でスコープを開いて包まない。B6/B12 判定のために入口が独自に試合を読まない(U-S1 が ③ で判定する — `sync/gate.py:37-47`) | [推論 — 506/plan.md:47・design.md:94 と整合] |
| 試合の可視性 | ③ の `GameReadToken` は `games.id` だけで引く(`repositories/sync_apply.py:196, 237`)。論理削除済み(ごみ箱)の試合を除外する条件は無い | [検証 — これを B6 にすべきかは 7 節 G-12] |

---

## 3. 失敗境界

### 3-1. U-S1 が境界結果まで決めて返すもの

「全取消」の列は、**その結果を返したイベント(または要求の前段)のトランザクション**について。要求全体については 3-3。

| 戻り値 | 成立条件(コード) | 全取消か | 正本の再試行 | 典拠 |
| --- | --- | --- | --- | --- |
| `AckResult(B1)` | 全件を分類し切った | — (各件が確定) | 不要 | `sync/apply.py:337, 434`・SP:762 |
| `AckResult(B2)` | ⑥ で D1 欠落。以降は事前分類の B3b も含め未処理 | 欠落以降は書かない | gap から自動再送 | `sync/apply.py:380-387`・SP:763 |
| `AckResult(B3, b3_branch="B3a")` | 未使用 D5 の内容拒否 → T9 を確定してから返す | T9 は確定(拒否原本・D5・理由) | 操作者の 2 択 | `sync/apply.py:172-197, 425-428`・`sync/rejection.py:105-152` |
| `AckResult(B3, "B3b")` | 既存 D5・異内容(T9 なし) | 書かない | 新しい D5 / 2 択 | `sync/prefix_path.py:431-432`・`sync/rejection.py:81-82` |
| `AckResult(B3, "O4")` | P2 の永続化済み D2 同値。`_NoWriteStop` でポートの書き込みも含め rollback | **全取消** | 自動再送しない(管理者) | `sync/prefix_path.py:660-669, 812-813`・`sync/ordering.py:52-53, 76-79` |
| `AckResult(B4)` | ⑤ 不成立(要求単位 — 先行分類で未使用 D5 があるときポートに問う)。未使用は全件 T8、既存は再掲、異内容は未処理 | T8 は確定 | 退避(自動再送しない) | `sync/apply.py:129-134, 344-379, 415-417` |
| `"B6"` | ③ で試合が見えない(不存在・他テナント同一)。要求の冒頭、または途中のイベントで試合行が見えなくなった | 書かない(③ はポートより前) | 同じ認証での自動再送を止める | `sync/apply.py:314-315, 399-400`・`sync/prefix_path.py:785-786`・`sync/rejection.py:240-241` |
| `"B7"` | RG1 が閉じている(③-a)、⑧ のコミット直前に閉じた、**または RG1 の 2 メソッドが例外を投げた** | **全取消**(③-a は書く前、⑧ はスコープ全体を rollback)・D5 を消費しない | 自動再送 | `sync/gate.py:50-68, 72-84`・`sync/apply.py:318-321, 399-400`・`sync/prefix_path.py:808-809`・`sync/rejection.py:260-261` |
| `AcceptedChangeResult` | P3 の変更受理(再掲を含む) | — | — | `sync/change_path.py:215-275, 95-116` |
| `RejectedChangeResult(B8)` | V11 ≠ 現在版。`reason` は文字列 `"現在版: <n>"` | **全取消** | 再入力 | `sync/change_path.py:210-213` |
| `RejectedChangeResult(B9)` | 復旧世代が旧(`"要求作成時の復旧世代が旧世代"`)、または進行中で V12 不成立(`"現在の記録権証明がない"`) | **全取消**・D5 を消費しない | 自動再送しない | `sync/change_path.py:143-149, 164-172` |
| `RejectedChangeResult(B10)` | RG1(③-a・⑧・RG1 ポートの例外) | **全取消** | 自動再送 | `sync/change_path.py:307-308` |
| `RejectedChangeResult(B12)` | ③ で試合が見えない。`reason=None` | 書かない | 止める | `sync/change_path.py:291-292` |
| `RejectedChangeResult(B13)` | D5 衝突、または D5 が別の結果に使用済み | 書かない | 新しい D5 | `sync/change_path.py:95-103, 150-155` |
| `RejectedChangeResult(B14)` | 試合が進行中・終了後でない / V5・V7・V10・V11 の形 / 内容検証の拒否 / 対象スロットが無い | **全取消** | 新しい D5 | `sync/change_path.py:157-203` |

- ⑧ を呼ぶのは書き込みを確定する分岐だけ(再掲・拒否の分岐は呼ばない — `sync/prefix_path.py:804-806`・`sync/rejection.py:257-258`・`sync/change_path.py:300-301`、計画書 `plan.md:239`)[検証]
- B3 の外部確定順(⑥)と DI5 の上書き(停止後は B3b も未処理)は `sync/apply.py:340-387` [検証]

### 3-2. 例外として入口へ上がるもの(U-S1 は写像しない)

既定のままだと、未捕捉例外は共通ハンドラで **500**(`api/errors.py:132-146`)になり、WS 4-1 の表(`WS:275`)では **B7 の群**(クライアントは自動再送)に入る。各行の「入口の写像」は 506 が決める欄で、ここでは**選択肢を示すだけ**[推論]。

| 例外 | どこで(典拠) | 書き込み | 決定的か(再送で同じになるか) | 入口の写像(候補) |
| --- | --- | --- | --- | --- |
| `RequestShapeError`(S-1) | `SyncRequest.__new__`・`from_payload`(`sync/model.py:56, 74-80, 134-135, 175-217, 236-277`) | なし(適用核に入る前) | 決定的 | **422**・共通封筒(WS:276)。FastAPI の `RequestValidationError` ではないので**入口で捕まえる必要がある**(`api/errors.py:60-83` は別の例外型)[検証] |
| `PortRegistrationError`(`RuntimeError`) | 未登録のポートを呼ぶ前(`sync/gate.py:52`・`sync/prefix_path.py:594-595`・`sync/rejection.py:179`・`sync/change_path.py:137-138`・`sync/apply.py:131`)。**現 develop では登録表が空なので、自テナントの実在試合への要求は必ずここで止まる**(`sync/ports.py:134`、`backend/tests/test_sync_apply_model_ports.py:310-312`) | なし(③-a より前。スコープは rollback) | 配備の欠陥。再送しても同じ | 506/plan.md:33・design.md:96 のとおり「未登録で入口を開かない」。写像より**開通条件**の問題 |
| `P1PreconditionError`(`ValueError`、category `"other"`) | 下の 3-2-a の各所 | **そのイベントは rollback**。それより前の D1 は確定済みのことがある | 多くは決定的(下表) | 500 のままだと**同じ要求を永久に自動再送**しうる。7 節 G-8 |
| `ValueError("P4 はその場登録を持たない")` | `sync/rejection.py:238-239`(`path="P4"` で `registrations` を渡したとき) | なし | 決定的 | 入口の呼び方の誤り |
| `RuntimeError` 群(不変条件) | 3-2-b | そのトランザクションを rollback | 多くは決定的(データの不整合) | 500 |
| `TenantBindingError`・`_TenantOperationError`(どちらも `RuntimeError`) | `repositories/binding.py:17`・`repositories/base.py:57`(文脈の証跡不一致・未登録 token 等) | なし | 決定的 | 500 |
| ポートの例外(**RG1 の 2 メソッド以外**) | `holds_recording_right`(`sync/apply.py:132`・`sync/prefix_path.py:600`・`sync/rejection.py:180`・`sync/change_path.py:166`)、`is_recovery_generation_current`(`sync/change_path.py:144`)、`projection.apply`(`sync/prefix_path.py:731`・`sync/change_path.py:271`)、`validator.validate`(`sync/prefix_path.py:642`・`sync/change_path.py:191`)— どれも包まれていない | そのトランザクションを rollback | ポート次第 | U-S1 計画書 8 節の「Port の例外もスコープ全体を取り消して B7/B10」(`plan.md:238`)は **③-a・⑧ の Port についての契約**で、コードもその 2 つだけを `RG1Blocked` に包む(`sync/gate.py:53-58, 63-68`)。他のポートの例外は素で上がる [検証] |
| DB の例外(`sqlalchemy.exc.OperationalError`・`DBAPIError`〔直列化失敗 40001・デッドロック 40P01・ロック待ちの打ち切り〕・D5 以外の `IntegrityError`)、`DatabaseConfigurationError` | どこでも。U-S1 が捕まえるのは D5 の一意制約違反(23505 かつ制約名が `pk_idempotency_ledger`/`uq_idempotency_ledger_kind`)だけ(`sync/idempotency.py:27, 173-200`) | そのトランザクションを rollback | 一時障害が多い | **B7/B10 の群**(503 など — WS:275)。正本の B7 は「通信・サーバー」の一時障害で、部分確定があっても D3 を返さない(SP:768)[推論] |

#### 3-2-a. `P1PreconditionError`(category `"other"`)が要求の外へ上がる経路

`_run_d1_event` は `recording_rights` と `w2_violation` と `P1ContentRejection` だけを拒否・退避へ回し、それ以外は再送出する(`sync/apply.py:172-199`)。内容検査の大半は `_apply_locked` の内側の try で `P1ContentRejection`(= B3a/T9)に変えられる(`sync/prefix_path.py:612-639`)が、その try の**外**で投げられるものが残る [検証]。

| 発生箇所 | 条件 | 書き込み | 決定的か |
| --- | --- | --- | --- |
| `sync/apply.py:322-327` | `path="P4"` の要求なのに記録権が成立し、未使用 D5 がある | なし(先行分類は読み取りだけ) | 状態次第 |
| `sync/prefix_path.py:606-610` | 新しい D5 が確定済みの D1(D1 ≤ D3)を指し、V9 が無い | このイベントは rollback | 決定的 |
| `sync/prefix_path.py:654-658` | スロットまたは現行イベントが既にある(V9 なし) | 同上 | 決定的 |
| `sync/prefix_path.py:662` → `sync/ordering.py:33-34, 97` | P2 の V6 が bigint 外、または局所再採番の隙間が無い | 同上 | 決定的 |
| `sync/prefix_path.py:676-680` | その場登録の一時 ID が別の写像に使用済み | 同上 | 決定的 |
| `sync/prefix_path.py:689-694` → `:436-504` | 選手参照が UUID でない・正規形でない・写像も選手行も無い・V5 で定義されない選手参照位置 | 同上 | 決定的 |
| `sync/rejection.py:184-189` | 退避(T8)で D4 が十進整数の文字列でない | 同上 | 決定的(**D4 の表現次第 — 5 節**) |
| `sync/rejection.py:199-200` | ⑤ を不成立と読んだ後、退避のトランザクションでは記録権が成立した(競合) | 同上。**同じ要求のそれ以前の退避は確定済み** | 競合。再送で変わりうる |
| `sync/rejection.py:203-206` | 確定済み D1 の内容拒否、理由が空 | 同上 | 決定的 |

U-S1 の作業ログは、上の `sync/rejection.py:199-200` の競合を「記録権の前処理と取引内の判定の競合で素の例外になる件 — HTTP 入口の例外の写像で扱う」と**入口へ送っている**(`docs/worklog/2026-10-08-us1-sync-apply-core.md:336`)[検証]。

#### 3-2-b. 不変条件の `RuntimeError`(主なもの)

| 文言(典拠) | 起きうる状況 |
| --- | --- |
| 「自テナントの記録権世代行が一件ではない」(`sync/apply.py:100-101`)/「recording_generations の対象行が一件ではない」(`sync/prefix_path.py:174-178, 881-883`) | **現世代行が無い試合**(準備中で初期記録権がまだ無い — 計画書 R-17 `plan.md:78`、または現世代が失効・退役 — `repositories/sync_apply.py:197-201`)。**P3 でも状態検査(B14)より前に行ロックするので、準備中の試合への P3 は B14 ではなくこの例外になる**(`sync/change_path.py:130-135` の後に `:157`)[検証]。7 節 G-11 |
| 「認可後に試合行が消失した」(`sync/prefix_path.py:548-549`・`sync/rejection.py:168-169`・`sync/change_path.py:131-132`) | ③ と行ロックの間に試合行が消えた。B12/B6 へ戻さないことを試験が固定している(`backend/tests/test_sync_apply_gate.py:196-216` `test_lost_game_after_authorization_is_not_returned_as_b12`) |
| 「同じ一時 ID に異なる確定選手 ID がある」(`sync/apply.py:412-413`) | **それまでのイベントを確定した後**の ACK 合成で発生 |
| 「D3 の型が不正」「記録権世代の型が不正」「D1 に複数の現行行がある」「D3 の前進に失敗」「D5 再照合が未使用に戻った」「D5 一意制約違反後に先着行を観測できない」「P1/P3 の保存済み結果の形が不正」「拒否・退避の保存済み結果の形が不正」「試合行ロック下で対象版の CAS が失敗」 | DB の不整合・競合の異常(`sync/apply.py:103-107, 126-127`・`sync/prefix_path.py:650-653, 728-729, 709-710, 404-424`・`sync/idempotency.py:196-198, 247-261`・`sync/change_path.py:109-115, 204-209, 253-254`) |
| 「同期適用中の印へ再入できない」「同期適用中に新しいテナントスコープを開けない」「PortWriter のトランザクションは閉じている」 | ポート実装の誤り(`repositories/transaction.py:45-46, 212-213`・`sync/ports.py:47-48`) |

### 3-3. 要求単位で見た「全取消」と「再試行」

| 観点 | 内容 | 典拠 |
| --- | --- | --- |
| 原子の単位 | **1 イベント = 1 トランザクション**。要求全体は原子的でない(正本が許す: 「要求(バッチ)全体の原子性は保証しない」) | `sync/apply.py:349-398`・SP 7-1 の A1(929 行付近)・SP:1255 [検証] |
| 途中の B6/B7 | それまでのイベントは確定済みのまま、ACK なしで `"B6"`/`"B7"` を返す。D3 は次回再送の ACK で得る | `sync/apply.py:399-400`・SP:768 [検証] |
| 途中の例外 | 上がった時点のイベントだけ rollback。それ以前の確定は残る。**入口が 500 を返すと、クライアントは同じ要求を再送し、確定済み分は「重複」で再掲される**(DI2) | [推論 — `sync/apply.py` に例外時の後始末は無い] |
| 再送の同一性 | D5 の指紋に **経路名(P1/P2/P3/P4)・全 V 値(欠落と null を区別)・その場登録の値** が入る。**同じ D5 を別の経路名や別の `registrations` で再送すると B3b(P3 は B13)** | `sync/idempotency.py:77-99, 270-289` [検証] |

---

## 4. 担当の線引き

| 項目 | U-S1 側で実装済み(典拠) | 506 がこれから実装する |
| --- | --- | --- |
| 認証(B5/B11) | なし(`sync/apply.py:304`) | `Depends(require_tenant_access)`。失敗は既存ハンドラで 401(`api/errors.py:113-129`) |
| S-1 の外形検査 | `SyncRequest.from_payload`・`RequestShapeError`(`sync/model.py:230-317`) | `RequestShapeError` を 422 の共通封筒へ。S-1 を試合の存在より前に置く(呼び出し順で保証される — `from_payload` は DB を読まない)[検証] |
| 経路名(`path`)の決定 | `SyncRequest.path` を受けるだけ | **E-1 の `path` に何を入れるか**(7 節 G-1)。E-2 は `"P3"` 固定 |
| wire の値 → U-S1 の値 | `from_payload` はキー名だけを写す(値は変換しない) | V5 の番号 → リテラル、V10 のキー名、D4 の表現(7 節 G-2〜G-4) |
| `registrations`・`targets` | 引数で受けるだけ(`sync/apply.py:299-300, 316-317`) | **出所が未定**(7 節 G-5) |
| ③ 認可(B6/B12) | 実装済み・不存在と他テナントを同一化(`sync/gate.py:37-47`) | 404 の status・header・body を「自テナントに存在しない試合」と**バイト同一**にする(WS:348-352・SP:896) |
| ③-a・⑧ RG1 | 呼び出し位置と B7/B10 への写像は実装済み(`sync/gate.py:50-84`) | なし(U-R1 の本物のポートを注入するだけ) |
| ④ D5・⑤・⑥・⑦・T1〜T9・ACK 合成 | 実装済み(`sync/apply.py`・`prefix_path.py`・`ordering.py`・`rejection.py`・`change_path.py`・`idempotency.py`) | なし。HTTP で D5 を作らず、台帳・原本に直接書かない(506/plan.md:26, 47) |
| 結果 → wire | なし | `AckResult` → WS 4-2、`ChangeResult` → WS 4-3、`"B6"`/B12 → 404、`"B7"`/B10 → 503 等。不足は 7 節 G-6〜G-7 |
| 例外 → HTTP | なし(3-2) | 3-2 の各行。特に決定的な `P1PreconditionError` の扱い(7 節 G-8) |
| ポートの登録 | 登録表と検査器だけ(`sync/ports.py:134-143`・`sync/port_guard.py:484-500`)。製品の登録は空 | 本物のポートの**登録は U-R1・U-X1 側**(`sync/ports.py` の登録変更はコア領域)。506 は登録済みのクラスのインスタンスを渡す |
| V12 の非ログ化 | U-S1 は V12 を読まない(ポートへ素通し)。例外文言にも V12 は入らない | 入口の本文・例外ログに出さない(506/design.md:116)[推論 — ポートの例外文言は U-R1 次第] |

---

## 5. U-R1 の決定待ち(決め打ちしない)

| 依存する決定 | U-S1 の現在の仮置き(典拠) | 決定が変わると入口に効くこと |
| --- | --- | --- |
| **D4 の物理表現** | **D4 = 記録権世代番号(`recording_generations.generation`、整数)の十進文字列** と読む: ① ACK の D3 の起点を `request.d4.isdecimal()` で世代番号として引く(`sync/apply.py:108-128`)② 退避原本の `old_generation = int(event.d4)`、整数でなければ `P1PreconditionError`(`sync/rejection.py:183-189`)③ P3 の V10 の `d4` は整数または十進文字列(`sync/change_path.py:80-83`)、受理結果の `対象の D4` は **int**(`:216-220`)④ P3 の記録権照会に `str(generation)` を D4 として渡す(`:166-167`) | 不透明な文字列にすると、②が例外、①が現世代の D3 へ落ちる(「読めない D4 は現世代の D3 のまま」— `:110`)。WS は D4 を「不透明な文字列」(L-3)とし、物理形式を U-R1 へ送っている(WS 3-4 の表)。U-S1 の作業ログは「D4 の物理形式・世代の読み取り operation は U-R1 の決定事項なので、U-R1 の接続時(U-R1 新ステップ 6)に揃える」と送っている(`docs/worklog/2026-10-08-us1-sync-apply-core.md:336`)。その後、要求世代の D3 を返す処理は**十進整数の仮定の上で**入った(同 worklog の「結果のまとめ」・`sync/apply.py:108-128`) |
| **旧世代の読み取り** | `RecordingGenerationByNumberReadToken(game_id, generation: int)` — 失効・退役を問わず `kind='normal'` の世代行を番号で読む(`sync/tokens.py:52-58`・`repositories/sync_apply.py:203-205, 255-263`) | D4 の表現と世代行の主キーの関係が変われば token ごと変わる |
| **V12 の物理形式・照合** | 型の層で検査せず(`sync/model.py:30-31`)、`holds_recording_right(game_id, d4, v12, writer)` へ素通し。P3 は `ABSENT` のときだけ U-S1 が B9 を決める(`sync/change_path.py:164-172`)。D1 付き経路の V12 欠落の判定もポート任せ | VF1(V12 必須)の B4 化はポートの返り値に依存 [推論] |
| **復旧世代** | P3 の `recovery_generation: str` を `is_recovery_generation_current(game_id, supplied, writer)` へ素通し(`sync/change_path.py:143-149`) | 物理形式は U-R1(WS 3-4) |
| **RG1 の実体** | ポートの 2 メソッド(bool)。例外は閉鎖扱い(`sync/gate.py:50-68`)。仮置きの `is_restoration_active` は置き換え済み(`plan.md:238`) | FOR SHARE を宣言できる基底の拡張は U-R1 の PR(`plan.md:238` の残る条件) |
| **undo の対象(`P1Target`)** | 「U-R1 が V10 を解決した」値を引数で受ける(`sync/prefix_path.py:116-122`)。`generation: int` | V10 → 世代番号の解決は D4 の表現と一体 |
| **固定関数の口** | `PortWriter.run_function` は未実装(`sync/ports.py:28-55` に無い。`plan.md:240` で U-R1 新ステップ 6) | U-R1 のポートが TSK-550 の固定関数を使うなら、それが入るまで本物のポートが組めない [推論] |
| **初期記録権・現世代行の作成** | U-S1 は作らない。製品コードに `recording_generations` の行を作る経路は無い(`grep` で `sync/`・`repositories/` 以外に参照なし)。R-17 は「試合開始で付与」(`plan.md:78` — U-G1 の境界) | 現世代行が無い試合は 3-2-b の `RuntimeError`(7 節 G-11) |
| **合成ポート** | U-S1 の試験は試験中だけ登録表へ足す合成ポート(`GenerationRights` は「要求の D4 が DB の現世代と一致し保持端末なら記録権あり」— `backend/tests/test_sync_apply_port_prefix.py:125-147`)。製品の登録表は空のまま(`docs/features/us1-sync-apply-core/design.md:50`) | 506 は合成ポートで入口を開かない(506/plan.md:33)。**入口の単体試験で合成ポートを使うことと、稼働入口を開くことを分ける**[推論] |

---

## 6. 着手条件と確認条件

### 6-1. 着手条件(いま develop のコードから読み取れる公開面だけ)

506 のステップ 4 に着手するのに足りるのは次の「呼び方の契約」。いずれも上の 1〜3 節で典拠を示した。

1. 呼ぶ関数は `apply_sync_request`(`sync/apply.py:292-301`)と `SyncRequest.from_payload`(`sync/model.py:230-233`)の 2 つ
2. 戻り値の型は `AckResult | ChangeResult | Literal["B6","B7"]`(`sync/apply.py:62`)、各フィールドは 2-2 節
3. 入口が写像する例外の集合は 3-2 節(`RequestShapeError`・`PortRegistrationError`・`P1PreconditionError`・`ValueError`・`RuntimeError` 群・ポートの例外・DB 例外)
4. トランザクションは U-S1 が開き、入口は `TenantContext` を渡すだけ(2-4 節)

ただし、**7 節の G-1〜G-5 は「呼び方」そのものが決まらない穴**なので、着手条件として U-S1 維持担当(と G-2〜G-5 の各担当)の回答が要る。506/plan.md:49 の「ステップ 4 の着手前に TSK-391 の公開境界を受理」はこの部分に当たる [推論]。

### 6-2. 確認条件(506 が実装したら、この試験で確かめる)

着手条件に置かない。既存の U-S1 試験は**適用核を直接呼ぶ**ので、506 は同じ観測を HTTP 越しに取り直す。

| 確かめること | U-S1 の既存試験(オラクルとして参照) |
| --- | --- |
| B6/B12 の不存在・他テナント同一(404 のバイト同一) | `backend/tests/db/test_sync_apply_apply_boundary.py:489` `test_other_tenant_and_missing_game_have_identical_b6`、`backend/tests/db/test_sync_apply_change_boundary.py:215` `test_p3_other_tenant_and_missing_game_have_same_b12_before_rg1`、`backend/tests/db/test_sync_apply_gate_boundary.py:143` `test_p1_other_tenant_and_missing_game_stop_before_rg1`、`backend/tests/test_sync_apply_gate.py:220` `test_inaccessible_game_stops_before_rg1_even_when_closed` |
| RG1 閉鎖で D5 未消費・ロックなし(B7/B10) | `backend/tests/db/test_sync_apply_apply_boundary.py:513` `test_rg1_stop_from_public_entry_takes_no_row_locks`、`backend/tests/test_sync_apply_gate.py:108` `test_rg1_before_d5_stops_without_lock_or_d5`、`backend/tests/db/test_sync_apply_change_boundary.py:268` `test_p3_saved_result_is_blocked_by_rg1` |
| ⑧ のコミット直前閉鎖で全取消 | `backend/tests/db/test_sync_apply_gate_boundary.py:82` `test_p1_rg1_commit_failure_rolls_back_every_t_element`・`:205` `test_public_entry_rg1_commit_failure_rolls_back_each_path`、`backend/tests/db/test_sync_apply_change_boundary.py:250` `test_restoration_started_before_commit_rolls_back_all_t_elements`、`backend/tests/test_sync_apply_gate.py:340` `test_rg1_before_commit_rolls_back_without_consuming_d5` |
| ACK 消失後の再送(同じ写像・二重適用なし) | `backend/tests/db/test_sync_apply_apply_boundary.py:432` `test_lost_ack_replays_same_player_mapping` |
| gap と DI5(B2・事前分類の B3b を未処理に) | 同 `:150` `test_gap_example_preclassified_b3b_is_unprocessed`・`:186` `test_gap_before_only_existing_conflict_is_b2_not_b3b`、`backend/tests/test_sync_apply_apply.py:47, 77, 126` |
| B3a/T9・B3b | 同 `:415` `test_contiguous_invalid_content_commits_b3a_original`、`backend/tests/db/test_sync_apply_rejection_boundary.py:90` `test_b3a_replay_and_b3b_do_not_add_originals` |
| B4・退避の再掲・旧世代の再送 | `backend/tests/db/test_sync_apply_apply_boundary.py:215` `test_b4_request_replays_existing_and_escrows_every_unused`・`:247`・`:286` `test_old_generation_resend_replays_without_current_gap`・`:307`・`:342` `test_p4_resend_replays_escrow_with_p4_fingerprint`・`:371` `test_b4_request_leaves_conflict_unprocessed_without_t9`、`backend/tests/db/test_sync_apply_rejection_boundary.py:193` |
| P3 の各結果と書き込みなし | `backend/tests/db/test_sync_apply_change_boundary.py:126` `test_p3_acceptance_replay_intents_and_lock_order`・`:180` `test_p3_rejected_branches_do_not_write`(B8〜B10・B12〜B14)・`:239` `test_finished_p3_ignores_v12` |
| ロック順(試合行 → 世代行、D5 再照合を含む) | `backend/tests/db/test_sync_apply_apply_boundary.py:554` `test_public_entry_lock_order_including_d5_recheck` |
| クラッシュでイベント単位の全有無 | 同 `:637` `test_named_crash_points_leave_whole_event_or_no_event`、`backend/tests/db/test_sync_apply_failure_runner.py:1191` `test_server_failure_scenario_case` |
| S-1(422)の外形 | `backend/tests/test_sync_apply_model_ports.py:172, 179, 210, 216, 256, 274` |
| 未登録ポートを呼ぶ前に拒否 | `backend/tests/test_sync_apply_model_ports.py:310` `test_unregistered_port_is_rejected_before_call`、`backend/tests/test_sync_apply_change.py:90` `test_p3_rejects_unregistered_ports_before_any_call` |
| 結果の語彙(N-18 の型 ↔ wire) | `backend/tests/test_sync_apply_model_ports.py:92` `test_ack_and_change_results_use_canonical_vocabulary` |
| 認可後に試合行が消えたときは例外(B12 にしない) | `backend/tests/test_sync_apply_gate.py:196` |

**既存試験に無く、506 が新しく要るもの**[推論]: 3-2 の例外 → HTTP の写像(特に決定的な `P1PreconditionError` で無限再送にならないこと)、途中例外のときの部分確定と再送で「重複」になること、V12 が応答・ログに出ないこと、B5/B11。

---

## 7. 不明点・U-S1 側に欠けている公開面

| # | 欠けているもの | 根拠 | 影響 | 回答すべき担当 [推論] |
| --- | --- | --- | --- | --- |
| **G-1** | **E-1 の経路名の決め方と、P1/P2 混在バッチの公開型** | `SyncRequest.path` は要求に 1 つ(`sync/model.py:158`)。P2 の要求で P2 以外の種別(undo・その場登録・墓標)は**内容拒否 = B3a で T9 に永久に記録される**(`sync/prefix_path.py:614-617, 636-638`)。P1 の要求に毎球入力を入れると T5(D2 の採番)を通らずに保存される(P1 で毎球入力を拒む検査はコードに無い)。経路名は指紋に入るので、後から分類を変えると再送が B3b になる(`sync/idempotency.py:277`)。正本は毎球入力 = P2・undo/その場登録/墓標 = P1(SP:1292 以下)、WS は「経路はクライアントが選ばない」(WS:163) | 506 の照会文(506 worklog:46)のとおり、**混在を 1 つの ACK にする型は無い**。HTTP 側で分割すると ACK が分かれる(506/plan.md:49 が禁じる) | U-S1 維持担当(TSK-391 後続) |
| **G-1b** | `path="P4"` を入口が使うのか | ⑤ 不成立は P1/P2 の要求の中で内部的に T8 へ回る(`sync/apply.py:219-238, 344-379`)。`P4` の要求は記録権が成立すると例外(`:322-327`)。一方、P4 の指紋で保存した退避は P4 の要求でしか再掲できない(`:257-267`、`test_p4_resend_replays_escrow_with_p4_fingerprint`) | 入口が P4 を送らないなら P4 の要求経路は使われない。送るならいつか | U-S1 維持担当 |
| **G-2** | **V5(イベント種別)の値の対応** | wire は番号の文字列 `"1"`〜`"12"`(WS 3-2 の表・`frontend/src/lib/sync/eventKinds.ts:31-108`)。U-S1 はリテラル `play_input` 等を要求し(`sync/prefix_path.py:223-231`、`db/sync_protocol/event_kinds.py` の `EVENT_KIND_LITERALS`)、番号のままだと **B3a で T9 に記録される**。P3 は番号のままだと B14(`sync/change_path.py:173-176`)。さらに wire の `"8"`(墓標)・`"9"`(改訂版)に当たる種別は U-S1 に無く、U-S1 は V9 の `tombstone`/`revision` と**元の種別の V5** で表す(`sync/prefix_path.py:197-220, 284-287`)。状態補正(`state_correction`)は `EVENT_KIND_LITERALS` に入っていない(実行して確認) | 変換表の置き場(`sync/http_wire.py`?)と所有。指紋は変換後の値で取られるので、変換は決定的で版を固定する必要がある | U-S1 維持担当 + TSK-331(N-18) |
| **G-3** | **V10(対象参照)のキー名** | wire は `game_id`・`d4`・`d1`(WS 3-2)、U-S1 の入力は `game`・`d4`・`d1`(`sync/prefix_path.py:237`・`:366`・`sync/change_path.py:78`)、U-S1 の P3 受理結果は `試合`・`対象の D4`・`対象の D1`(`sync/model.py:389`)、既存 DTO も日本語キー(WS 2-6 の表) | 3 種類のキー集合を誰がどこで写すか | U-S1 維持担当 + TSK-331 |
| **G-4** | D4 の表現(5 節) | U-S1 は十進整数の文字列を仮定、wire は不透明な文字列 | P3 受理結果の `対象の D4` が int で返る(wire は文字列) | U-R1 |
| **G-5** | **`registrations`・`targets` の出所** | wire の E-1 本文にその場登録の選手作成値(`team_record_id`・`name`・`roster_status_key`)も、undo の解決済み対象(世代番号)も無い(WS 3-2)。渡さないと、その場登録は「その場登録には選手作成値が必要」、undo は「undo の V10 と照合済み対象が一致しない」で **B3a/T9**(`sync/prefix_path.py:628-629`・`:374`)。`registrations` は指紋に入る(`sync/idempotency.py:278-287`) | V7 から組み立てるなら、その規則と所有。`P1Target` は U-R1 が解決する前提(`sync/prefix_path.py:118`) | U-S1 維持担当・U-R1・U-M1 |
| **G-6** | ACK のイベントごとの B3 分岐 | wire は `event_results[].rejection.kind/branch` を「拒否」のイベントごとに要求(WS 4-2)。`A5Result` は分岐を持たず、`AckResult.b3_branch` は停止イベントの 1 つだけ(`sync/model.py:320-338`)。停止イベント以外の「拒否」(B4 要求での保存済み B3a の再掲)は保存済みの否定結果が B3a/B4 しかないので B3a と読める(`sync/idempotency.py:247-267`)[推論] | 入口が推論で埋めるか、U-S1 が型に足すか | U-S1 維持担当 + TSK-331 |
| **G-7** | P3 拒否の構造化された値 | wire は B8 の `current_version`・B9 の `b9_cause`(`"記録権不保持"`/`"旧復旧世代"`)を要求(WS 4-3)。U-S1 は `reason` の文字列だけ(`"現在版: <n>"`・`"要求作成時の復旧世代が旧世代"`・`"現在の記録権証明がない"` — `sync/change_path.py:148, 171, 212`) | 文言の解析で写すと壊れやすい | U-S1 維持担当 |
| **G-8** | 決定的な前提違反の写像 | 3-2-a の例外は境界結果を持たない。既定の 500 は WS 4-1 で B7 の群(自動再送)。同じ要求の再送は同じ例外になる | **端末が永久に再送する**[推論]。正本に当てはまる結果が無いので、WS 4-1 の「上表に無いステータス」(クライアントは解釈せず顕在化 — WS 4-1 の注)に置くか、U-S1 が B3a へ寄せるかの判断が要る。U-S1 は競合の 1 件を入口へ送っている(`docs/worklog/2026-10-08-us1-sync-apply-core.md:336`) | U-S1 維持担当 + TSK-331(4-1 の表を変えるなら正本ゲート) |
| **G-9** | ポートの例外(RG1 以外)の扱い | 素で上がる(3-2)。正本の B7 は「サーバー」の一時障害を含む(SP:768)が、U-S1 は分類しない | 投影・内容検証の不具合が自動再送の対象になる | U-S1 維持担当・U-X1 |
| **G-10** | 製品のポート登録 | `PORT_IMPLEMENTATIONS` が空(`sync/ports.py:134`)。本物は U-R1・U-X1(U-X1 の計算核は凍結中 — 506/design.md:129) | 登録まで E-1/E-2 は稼働入口として開けない | U-R1・U-X1/U-G2 |
| **G-11** | 現世代行が無い試合(準備中など) | D1 付き経路は `RuntimeError`(`sync/apply.py:100-101`)、P3 は B14 の判定より前に `RuntimeError`(`sync/change_path.py:130-135`) | 正本の境界結果が当たらない(B4? B14?)。500 になる | U-S1 維持担当・U-G1・U-R1 |
| **G-12** | 論理削除(ごみ箱)の試合 | ③ は `games.id` だけで引く(`repositories/sync_apply.py:196`) | ごみ箱の試合への同期を B6 にするか | U-D1・U-S1 維持担当 |
| **G-13** | 接続コスト | スコープごとに engine を生成(`repositories/transaction.py:224`・`db/engine.py:427-453`)。N 件の要求で 2 + 2N 回 | N-1(件数上限)・N-4 の測定に効く | 506(測定)・U-S1 維持担当 |

---

## 付記: 506 側で確認したこと(読むだけ)

- worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-tsk506-sync-http-entry`(HEAD `e4f78904`、ステップ 2/5 まで。未コミットで `frontend/src/lib/sync/ackAdapter*.ts` の変更と `wireCodec.ts`・`httpTransport.ts` の新規あり)
- 506 が U-S1 に期待しているもの: 「毎球入力 = P2、P1/P2 混在バッチを単一 ACK・D1 順・部分成功で処理する型/関数と P4/P5 内部分岐」(506/plan.md:49)、`registrations`/`targets` の生成元・B6/B7 と P3 の結果(506/design.md:102、worklog:46)。**照会は Notion コメントで送ったが、受理回答は 0 件**(506 worklog:104-106, 132)
- 506 は router を `api/sync_routes.py`、DTO/codec を `sync/http_wire.py` に置く予定(506/plan.md:43)

# B. 同期要求の失敗時の振る舞いと、恒久的な失敗の正本上の置き場(調査メモ)

- 調査日: 2026-10-16 / 基線: `develop` = `e7e8d3a4`(読むだけ。参考として `feature/tsk506-sync-http-entry` = `301997d1` の worktree を読んだ)
- 表記: **[検証]** = コード・正本・試験を読んだか実行して確かめた / **[推論]** = 読んだ事実からの推論で、実行や原典の明記で確かめていない
- 正本の行番号は develop の `docs/design/sync-protocol.md`(v0.8 approved)。依頼文の「`:763` 付近」は develop では **B2 の行**で、**B7 の行は `:768`**

---

## 0. 結論(先に)

1. **develop には同期要求を送るコードが存在しない** [検証]。`frontend/src/lib/sync/*` は API クライアントを 1 つも import していない(非 spec の import はすべて `./` 相対か `@design-relations`)。`lib/sync` を import する製品コード(画面・store)も無い(`testing/failureScenarioAdapter.ts` だけ)。**HTTP 500 を受けたときの振る舞いは develop には「無い」**。キューは ACK の A5 でしか遷移しないため、送らなければ `未送信` のままになる。自動再送のスケジューラ・上限・停止条件・利用者向け表示も無い。
2. 送信層は **TSK-506 の未マージのステップ 3(`httpTransport.ts`)** にある [検証]。そこでは **408・500・502・503・504・通信断・Abort → `no-ack` B7(P3 は B10)** として扱い、キューを変えない。**通知は出さず、再送のスケジューラも無い**(1 回送って結果の種類を返すだけ)。
3. サーバー側では、**分類されない例外はすべて共通ハンドラで 500 になる** [検証]（`backend/src/pitchlog/api/errors.py:132-146`・`:175`）。wire 設計 4-1 は **500 を B7/B10 に写す** [検証]。したがって **恒久的な失敗(区分 `other` の `P1PreconditionError`・不変条件の `RuntimeError`・ポート未登録)は、HTTP 入口が開いた時点で B7 として扱われる**。B7 は「ACK なし・未送信のまま・自動再送・理由は届かない」と決まっている。その結果、**永久に再送し、利用者には未送信件数しか見えない**状態になる。
4. 正本には **恒久的な処理失敗を表す境界結果が無い** [検証]。6-2 の段階①「要求が届き、**処理が完了したか**」→ B7(`:694`)が、原因を問わずすべてを B7 に吸い込む。恒久的な状態を受ける既存の仕組みは、**O4(永続化済み D2 同値)を B3 + 要操作(管理者対応待ち)へ載せた前例だけ**である。
5. 最小の正本差分案は 3 節に置いた。**案 A**: B7・B10 に「回復しない場合の顕在化」を足す。**新しい結果・状態は増やさず、意味規則は通知だけ増える**。**案 B**: O4 を一般化して、サーバーの不変条件違反を B3 / 要操作(管理者対応待ち)へ載せる。**結果値は増えないが、O 系の規則とキュー遷移が 1 つずつ増える**。

---

## 1. 問 1 — クライアントは同期要求の失敗にどう振る舞うか

### 1-1. develop(`e7e8d3a4`)の実体

| 調べたこと | 事実 | 典拠 |
| --- | --- | --- |
| 同期の送信コード | **無い**。`lib/sync/*.ts`(非 spec)の import はすべて相対か `@design-relations/sync-protocol.json`。`fetch`・`apiRequest` の呼び出しは 0 件 | `grep` の結果。`frontend/src/lib/sync/ackEnvelope.ts:2`「transport から本 DTO への変換は後続実装に委ねる」 |
| `lib/sync` を使う製品コード | **無い**(`testing/failureScenarioAdapter.ts` だけ) | `grep -rln lib/sync` |
| 再送スケジューラ・バックオフ | **無い**。`setTimeout`/`setInterval` は `Toast.vue` と `testing/vectorRunner.ts` だけ。`ApiError.retryAfterMs` は作られるが、使う側が無い | `frontend/src/api/client.ts:22-43`(`retryAfterMs`)・`:241,258`(`parseRetryAfterMs`) |
| HTTP ステータスの分類(共通層) | 2xx 以外 → `ApiError(status, message, fields, retryAfterMs, body)`。`fetch` の reject → `ApiNetworkError`。AbortError(タイムアウト含む)→ そのまま再 throw。往復中に認証世代が変わった → `ApiStaleAuthError`。401 → `auth.expireSession()` | `api/client.ts:193-198`・`:204,224`・`:226-229`・`:231-259` |
| キューの「ACK が返らない」遷移 | `QT-05`: `未送信 → 未送信`。trigger は `ack-unavailable`、`changesState: false`。**これを呼ぶ製品経路は無い**(関数として定義されているだけ) | `lib/sync/queueTransition.ts:151-158`・`:707-715` |
| ACK あり・なしの区分 | B1〜B4 = `ack`、B5〜B7 = `no-ack`。no-ack の結果を ACK として渡すと例外 | `lib/sync/boundaryResults.ts:23-28`・`:87-98` |
| 利用者通知カタログ | Q4・Q5・Q6・Q2-b・B4・I6・B5 の 7 種。**B6・B7、S-1 違反、解釈不能な応答の通知は無い** | `lib/sync/syncNotices.ts:5-17` |

**HTTP ステータス別の振る舞い(develop)** [検証 — 「送る経路が無い」ことによる]

| 区分 | キューの状態遷移 | 自動再送 | 利用者への表示 |
| --- | --- | --- | --- |
| 2xx | 送る経路が無いため発生しない(ACK を受け取れば `prepareA5Transition` で A5 遷移する部品はある — `durableQueue.ts:696-757`) | — | — |
| 4xx(401 以外) | 発生しない | 無し | 無し |
| 401 | 共通層が `expireSession`。キュー(IndexedDB)と `bb.sync` は残す | 無し | B5 の文言はカタログにあるが、出す経路は無い |
| 5xx | 発生しない(`ApiError` になるだけ) | 無し | 無し |
| タイムアウト・接続断 | 発生しない(`AbortError` / `ApiNetworkError` になるだけ) | 無し | 無し |

### 1-2. 参考: TSK-506 ステップ 3(未マージ・`feature/tsk506-sync-http-entry` `301997d1`)

`frontend/src/lib/sync/httpTransport.ts` の `noAck()`(`:79-103`)と `sendD1`/`sendP3`(`:120-240`)を読んだ。[検証(読んだだけ・実行は依頼の範囲外なので未実行)]

| 応答 | 返す結果 | キュー | 再送 | 表示 |
| --- | --- | --- | --- | --- |
| 200(ACK を解釈でき、A5 集合が要求と一致) | `ack` | A5 ごとに `prepareA5Transition` → `persistA5Transition` | — | 戻り値の種類だけ。通知記述子は返さない |
| 200(解釈できない・A5 集合が不一致) | `unrecognized-response` | 変えない | 無し | 無し |
| 401 | `no-ack` B5(P3 は B11) | 変えない | 無し | 無し(`createSyncNotice('B5')` は呼ばない) |
| 404 | `no-ack` B6(P3 は B12) | 変えない | 無し | 無し |
| 408・500・502・503・504 | `no-ack` B7(P3 は B10)+ `status` | 変えない(`未送信` のまま) | **無し**(スケジューラが無い) | **無し** |
| 通信断(`ApiNetworkError`)・AbortError | `no-ack` B7 / B10(`status` なし) | 変えない | 無し | 無し |
| 422 | `s1-violation` + `fields` | 変えない | 無し | 無し(通知 ID が無い) |
| 400・413・429・501 など | `unrecognized-response` | 変えない | 無し | 無し |
| 認証が切り替わった | `stale-auth` | 変えない | 無し | 無し |
| P3 の 409(B8・B9・B13・B14) | `p3-rejected` + 通知記述子 B8/B9/B13/B14 | I6 を保存しない | — | **ここだけ通知記述子を返す**(`syncNotices.ts` に 4 種追加) |

- **`sendD1` は 1 回で終わる関数**で、製品コードから呼ぶ側は無い(呼ぶのは spec だけ)。「いつ・何回再送するか」はどこにも実装されていない [検証]
- `retryAfterMs` は見ていない [検証]
- 計画書は「N-2(再送間隔/Retry-After)は性能測定後に判断する」としている(`docs/features/tsk506-sync-http-entry/research.md:172`、wire 設計 `N-2` `:413`)

### 1-3. 既存の試験と実行結果

**develop で実行**: `cd frontend && pnpm exec vitest run src/api/client.spec.ts src/api/client.boundary.spec.ts src/lib/sync/boundaryResults.spec.ts src/lib/sync/queueTransition.spec.ts src/lib/sync/restoreAdjustmentGate.spec.ts src/lib/sync/syncNotices.spec.ts`
→ **Test Files 6 passed / Tests 173 passed**(2026-10-16 15:02、4.27s)[検証]
(注: `pnpm exec` の実行時に pnpm が `frontend/node_modules` へ依存 72 件を自動で入れた。`git status` は clean のまま)

| 経路 | 確かめている試験 | 試験が確かめている範囲 |
| --- | --- | --- |
| 5xx → `ApiError` | `api/client.spec.ts:559`「500 の本文読み取り失敗は原因付き ApiError にする」、`:166`(封筒)、`:756`(download) | 共通層の例外の形だけ。**同期キューとの結合は試験なし** |
| 接続断 → `ApiNetworkError` | `api/client.spec.ts:328`、`:778` | 同上 |
| AbortError(タイムアウト) | `api/client.spec.ts:340`、`:599`、`:788` | 同上 |
| Retry-After の解釈 | `api/client.spec.ts:228`・`:236`・`:250` | 値の解釈だけ。**使う側は無い** |
| 401 でキューを残す | `api/client.boundary.spec.ts:137`「401 はセッションとキャッシュを失効させ、未同期キューと他の bb.* キーを保つ」 | IndexedDB のキューレコードが消えないこと |
| ACK なしでキュー状態を維持 | `lib/sync/queueTransition.spec.ts:340-347`(期待表の `QT-05`)・`:472-476`(評価)・`:743`(行ごとの it.each) | 遷移関数の単体。**送信層からの呼び出しは試験なし** |
| B5〜B7 は ACK 経路に入れない | `lib/sync/boundaryResults.spec.ts:23`(7 件 = ACK あり 4 + なし 3)・`:49-55`(no-ack を fail-closed) | 区分の exact-set |
| RG1 → B7/B10 | `lib/sync/restoreAdjustmentGate.spec.ts:111`・`:188` | 写像表の単体 |
| **5xx を受けたときのキュー・再送・表示(develop)** | **試験なし**(送信層が無い) | — |
| **自動再送の回数上限・停止条件** | **試験なし**(実装も正本の定義も無い) | — |
| **恒久的な失敗が続いたときの表示** | **試験なし** | — |
| 参考: 506 の 5xx → B7・キュー維持 | `httpTransport.spec.ts:119-151`(408/500/502/503/504 → B7 で `未送信`)・`:345-357`(P3 → B10)・`:153-168`(422/400/413/429/501)・`:170-186`(通信断・認証切替) | **未実行**(develop 以外は実行しない約束)。確かめているのは「キューを変えない」ことだけで、再送と表示は対象外 |

---

## 2. 問 2 — 恒久的な失敗に当てる境界結果は正本にあるか

### 2-1. 正本の契約(要点)

- **B7 は「ACK なし」を含む契約である** [検証]。7-1 A3 `:931`「**B5・B6・B7 では ACK 自体が返らない**。B7 の時点でサーバーに部分確定があっても D3 は返さず、次回再送の ACK で取得する」。6-3 B7 行 `:768`: ACK なし / **未送信のまま** / **自動再送(間隔・バックオフは (B) 論点 18)** / 「ACK 自体が返らないため、B7 の境界結果に基づく通知はクライアントへ届かない」+「記録を継続でき、**未送信件数を常時表示する**」
- **B7 の成立条件は「処理が完了しなかった」すべて** [検証]。6-2 の段階表 ①「トランスポート・処理系 | 要求が届き、**処理が完了したか** | B7 一時障害」(`:694`)。P3 も ① → B10(`:720`)・B10 行「通信またはサーバー処理が完了しない」(`:790`)。**原因が一時的か恒久的かを区別する列は無い**
- B2 には「**回復しない場合は『どこで止まったか』を明示**(4.0-2・NFR-015)」がある(`:763`)。**B7・B10 には同じ趣旨の節が無い** [検証]
- 7-2 `:1023`「B5〜B7 で ACK が返らないあいだは未送信のまま保持する。… B7 は自動再送により再開する」。7-2 ②(`:1056`)で `未送信` は自動再送の対象。7-3 手順 1(`:1072`)は「未送信のままの先頭から再送する」 [検証]
- 回数の上限・停止条件の定数は (B) 論点 18 として実装計画へ送られている(`:1581`)。**ただし正本が送ったのは「間隔・バックオフ」であり、「止めるかどうか」の意味規則は送っていない**。止めるのは要操作だけで、`要操作` へ移る契機は A5「拒否」(B3)に限られる(`:1021`)[検証]
- 前例: **O4**(永続化済み D2 同値 = データの不変条件違反)は「**B3 と A5『拒否』、要操作(管理者対応待ち)、自動再送を止める**、新しい結果値・キュー状態は追加しない」(`:755`・`:771`・`:942`・`:1007`・`:1025`)[検証]
- B8〜B14 は P3 専用で、D1 付き経路には使わない(`:824`)。恒久側は B13(D5 衝突)・B14(変更内容拒否)、条件次第で恒久になるのが B8・B9 [検証]

### 2-2. 区分ごとの当てはめ

| 区分 | サーバー実装での表れ(develop) | HTTP(wire 設計 4-1 / 506) | 正本で当たる境界結果 | 判定 |
| --- | --- | --- | --- | --- |
| **(a) S-1 の外形違反** | `RequestShapeError`(`backend/src/pitchlog/sync/model.py:56`)。処理段階に入らない | **422**(wire `design.md:276`) | **無し**。wire 2-4 が「S-1 違反は境界結果ではない」「B7・B10 の成立条件を広げない」と明記(`:107`)。クライアントはキューを変えずに顕在化する(`:110`)。**送り直しても解消しないときの止め方は未決**(WU-1 `:470`、N-17 `:428` → TSK-346) | **正本に行が無い** [検証]。状態は `未送信` のままなので、7-3 に従えば再送が続く [推論] |
| **(b) `P1PreconditionError`(区分ごと)** | `recording_rights` → P4/T8 で **B4**(`apply.py:172-182`)。`w2_violation` → T9 で **B3**(`:183-197`)。`other` のうち、⑦ 内容検査の try の中で投げたもの → `P1ContentRejection` で **B3a**(`prefix_path.py:637-638`)。**try の外で投げた `other` → `apply.py:198-199` で `raise` し直す → 未捕捉** | **未捕捉 → 500 → B7**(`errors.py:132-146,175`、wire 4-1) | 内容に起因するなら ⑦ B3a に当たるはずだが、**実装は B7 へ落としている**。該当箇所: `prefix_path.py:601-604`(未使用 D5 で D1 ≤ D3・V9 なし)、`:655-658`(スロットが既に在る・V9 なし)、`:680`(一時 ID が別の写像で使用済み)、`ordering.py:34`(V6 が bigint 上限超え — 試験 `tests/test_sync_apply_ordering.py:205-210`)、`ordering.py:97`(D2 の隙間が尽きた — 同 `:194-202`)、`apply.py:327`(P4 経路なのに記録権がある) | **正本上は ⑦ B3a または行無し**。実装は B7 [検証]。**D1 ≤ D3 に未使用 D5(V9 なし)が来た場合に当たる行は、正本の ⑥ にも ⑦ にも見当たらない** [推論 — 全文は検索していない] |
| **(c) 不変条件の `RuntimeError`** | `apply.py:101,104,107,127,413`、`prefix_path.py:170,177,345,408,418,422,459,549,651,653,710` と D3 前進失敗、`change_path.py:115,132,205,209,245,254`、`idempotency.py:105,117,132,198,250,261`。ほかに `PortRegistrationError`(ポート未登録 — 設定不備) | **未捕捉 → 500 → B7 / B10** | 段階 ①「処理が完了しなかった」→ **B7 / B10**。恒久を表す行は無い。**O4 だけが不変条件違反を B3 に載せた前例** | **正本に恒久側の行が無い** [検証]。一部(`認可後に試合行が消失`・`D5 再照合が未使用に戻った`)は競合で起きる一時的なもので、再送すると B6 や再掲に変わる [推論] |
| **(d) 内容拒否** | ⑦ `validator.validate` が偽、または try の中の `other` → **B3a / P5 / T9**(`prefix_path.py:640-644`)。P3 は **B14**(`change_path.py:170-199`) | 200 ACK(B3)/ 409(B14) | **B3a**(`:764`・`:811`)/ **B14**(`:794`) | **当たる行がある** [検証] |
| **(e) 一時的な DB 障害** | 接続・直列化の例外は未捕捉 → 500。1 イベント 1 トランザクションで、それまでのイベントは確定済み(`prefix_path.py:788-813`) | 500/503 → B7 | **B7**「サーバーで部分確定済みでも D3 は次回再送で取得」(`:768`・`:931`) | **正しく当たる** [検証(正本)/ 推論(DB 例外が 500 になること — DB 例外の試験は読んでいない)] |
| **(f) 結果未確認(タイムアウト・接続断)** | — | 応答なし → B7(wire 4-1 `:276`) | **B7 / B10**。再送して保存済み結果を再掲する(7-3) | **正しく当たる** [検証] |

### 2-3. 恒久的な失敗を B7 に写すと何が起きるか

1. **永久に再送する** [検証(規則)/ 推論(実害)]。B7 の再開手段は「自動再送」だけで(`:768`・`:1023`)、上限も停止条件も無い。`要操作` へ移すのは A5「拒否」だけ(`:1021`)なので、ACK が返らない B7 からは止まる状態へ移れない。同じ要求は毎回同じ例外を起こす(`apply.py` の分岐は決定的)。
2. **先頭で詰まり、正常な前方のイベントまで同期済みにならない** [検証(コード)]。`apply_sync_request` は D1 昇順にイベントごとのトランザクションを確定していき(`prefix_path.py:788`)、途中の例外はループの外へ抜ける(`apply.py:198-199` → 関数の外)。**それより前のイベントはサーバーでは確定済みなのに ACK が組み立てられない**ので、クライアントでは `未送信` のまま残る。再送しても前方は「重複」で再掲され、同じ位置でまた 500 になる。そのため:
   - Q5(キューが空になった通知)が一度も成立しない(`:1058`)[推論]
   - FR-007 の進行中修正の許可条件 ④(`未送信` 0 件)が永久に満たされない(`:1062`)[推論]
   - 7-5 の試合終了後の初回同期が完了しない [推論]
3. **理由が表示されない** [検証(規則)]。B7 は「通知はクライアントへ届かない」+「未送信件数を常時表示」だけ(`:768`)。共通エラー封筒は理由コードを持たず(wire 4-1 `:278`)、506 の送信層も B7 では通知記述子を返さない(`httpTransport.ts:98-100`)。利用者には「圏外で待っている」と「何度送っても通らない」の見分けがつかない。
4. **NFR-015 との関係** [推論]。NFR-015 は「同期の失敗は、利用者**または管理者**が気づける形(**画面通知・ログ**)で必ず顕在化する」で、測定方法は「障害注入テストで通知を確認」(要件書 `:921-924`。4.0-2「黙殺しない」`:174`)。サーバーは未捕捉例外を `_LOGGER.exception` で記録するので(`errors.py:145`)、**ログという意味では管理者側に痕跡は残る**。一方で:
   - 利用者画面には失敗の事実が出ない(未送信件数は通信断でも同じ値になる)
   - ログはどの試合・どのイベントで止まったかを構造として持たない(固定文言だけ — `errors.py:146`)。死活監視(NFR-016)は Should
   - 正本自身が B2 では「回復しない場合は明示」を NFR-015 の要求として書いている(`:763`)のに、B7 には無い
   → **恒久的な失敗を B7 で受ける限り、「回復しない同期失敗」を利用者に顕在化する規則が正本に無い**。NFR-015 の障害注入テスト(恒久失敗の注入)で利用者通知を確認できない
5. **wire 設計自身も穴を認めている** [検証]。WU-1「同じ要求を送り直しても解消しない場合の再送の止め方・再開の条件は決めていない」(`design.md:470`)。ただし射程は S-1 だけで、**500 に写る恒久失敗(b)(c)は WU-1 の射程外**であり、どこにも記録が無い。

---

## 3. 問 3 — 最小の正本差分案

正本に恒久側の行が無いことは 2 節で確かめた。以下は文言の**案**(未起案・未レビュー)。正本の改訂は 7.6 の決定表どおり**確定ゲート**(敵対レビュー + 人間承認)を通す。

### 案 A(最小 — 通知の意味規則だけ足す。結果・状態・遷移は増やさない)

**足す場所と文言**

1. **6-2 段階表 ① の直後に注記を 1 段落**:
   > 段階 ① の「処理が完了しない」は原因を問わない。通信・DB の一時障害のほか、サーバーの不変条件違反・設定不備など、同じ要求を再送しても結果が変わらない失敗も含む。サーバーはこれらを応答で区別せず(内部原因を返さない — 6-5)、原因と、要求の試合・D4・停止した D1・D5 をサーバーログへ記録する(V12 は記録しない)。
2. **6-3 の B7 行「利用者への通知」列の末尾**に追記(B2 行の書き方に合わせる):
   > **同じ未送信の先頭で B7 が続き回復しない場合は、同期が止まっていること・対象の試合・未送信件数を明示し(内部原因は示さない)、管理者へ顕在化する**(4.0-2「黙殺しない」・NFR-015)。自動再送は止めない。「回復しない」と判定する閾値は (B) 論点 18。
3. **P3 の独立境界結果表の B10 行**にも同じ趣旨を足す(「同じ D5 で B10 が続き回復しない場合は、変更が反映されていないことを明示する」)。
4. **7-4 に規律 Q8 を 1 行**:
   > Q8 | B7・B10・S-1 違反(wire 設計 2-4)・解釈できない応答が同じ要求で続く間は、未送信件数(Q4)と別に「同期が進んでいない」状態を常時表示する。キュー状態は変えない | NFR-015・4.0-2
5. **10-1 の論点 18 の行**に「B7・B10 の『回復しない』判定閾値」を受け取り物として追記する。

**意味規則を増やす範囲**: 通知規則 1 つ(B7/B10 の回復しない場合の顕在化)と、クライアントの規律 1 つ(Q8)。**境界結果・A5 の値・キュー状態・遷移・R-BOUNDARY の exact-set は変えない**(`boundaryResults.spec.ts:23` の 7 件・`canonOracle` の凍結 relation に影響なし [推論])。
**解けないこと**: 永久再送と、先頭詰まり(2-3 の 2)は残る。恒久失敗は管理者対応(バグ修正・データ是正)が入るまで続く。これを「受容したうえで黙殺だけは防ぐ」案。

### 案 B(恒久的な不変条件違反を O4 と同じ形で ACK 経路へ載せる)

**足す場所と文言**

1. **6-3 冒頭の定義伝播リスト**(`:755` の O4 の隣)に **O5** を新設:
   > **O5**: D1 付き経路で、⑤ 以降の処理中にサーバーの**不変条件違反**(正本・データモデルが禁じる永続状態を観測した、または同じ入力に対し決定的に処理を完了できない)を検出したイベントには、当該イベントのトランザクションを全取消したうえで **B3 と A5 の「拒否」**(理由種別 O5)を返し、キューを**要操作(管理者対応待ち)**へ移して**自動再送を止める**。D3 は進めず、T9 を開始しない。
2. **B3 行の成立条件**(`:764`)を「恒久的な内容拒否、または O4 の永続化済み D2 同値、**または O5 の不変条件違反**」に、キュー・再試行・通知の各列に O5 を O4 と並べて追記する。
3. **7-2 遷移表**: 「要操作(O4 の管理者対応待ち)→ 未送信」(`:1025`)を「**O4・O5**」に一般化する(是正の確認対象を「D2 一意性」から「当該不変条件」へ)。
4. **6-4 の除外経路表**に O5 の行を足す(2 択の対象外。管理者是正後に内容不変・新しい D5 で再送)。
5. **6-2 段階 ①** に「O5 に当たる失敗は ① ではなく B3 とする。① は一時的または原因を確定できない失敗に限る」を足す。

**意味規則を増やす範囲**: O 系の規則 1 つ(O5)と、要操作 → 未送信の契機の一般化 1 つ。**新しい境界結果・A5 の値・キュー状態・下位ラベルは増やさない**(O4 の `:771`「新しい結果値・キュー状態は追加しない」と同じ方針)。wire 設計 4-2 の `rejection.kind` に `"O5"` を足す必要がある [推論]。
**解けること**: 永久再送が止まる。ACK が返るので前方のイベントは同期済みへ移り、先頭詰まりが解ける。止まった位置と理由が出る(B3 の通知列)。
**危険と前提**: 一時的な失敗(`認可後に試合行が消失`・`D5 再照合が未使用に戻った` などの競合、DB 例外)を O5 に入れると、再送で通るはずのイベントを止めてしまう。**O5 に入れる例外は「明示的に列挙した不変条件」だけにし、未知の例外は B7 に残す**(fail-safe 側 = 再送を続ける)必要がある。どれが決定的かを列挙する作業は実装側(U-S1)に残る。

### 補足 — 正本差分ではなく実装の是正で済むもの [推論]

- 2-2(b) の **try の外で投げている `other`** のうち、内容に起因するもの(`ordering.py:34` の V6 上限超え、`prefix_path.py:680` の一時 ID 再使用)は、正本 ⑦ の B3a の射程(「イベント内容が受理できるか」)に入る。**正本を変えなくても、U-S1 側で B3a(P1ContentRejection)へ寄せれば B7 落ちを避けられる**可能性が高い。ここは U-S1 担当の判断で、正本の改訂ではない
- **D1 ≤ D3 に未使用 D5(V9 なし)が来た場合**(`prefix_path.py:601-604`)は、正本の ⑥・⑦ のどちらに当たるかが読み取れない。案 B の O5 に入れるか、⑦ B3a とするか、正本で決める必要がある
- 案 A と案 B は排他ではない。B を採っても、未知の例外は B7 に残るので A の通知規則は要る

---

## 4. 問 4 — 506 の計画書の失敗の写し方(読むだけ)

`/home/ymdms/projects/pitchlog-worktrees/feature-tsk506-sync-http-entry`(`301997d1`、ステップ 3/5 まで実装済み・未マージ)。[検証]

- `docs/features/tsk506-sync-http-entry/plan.md:57`(ステップ 3 の合格条件)「Vitest で全 4-1 HTTP 分岐、B5/B11・`ApiStaleAuthError`・不明応答のキュー/D5 保持」。**写し方は wire 設計 4-1 をそのまま使う**(500 → B7)
- `plan.md:58`(ステップ 4)「S-1 先行、認証 B5/B11、B6/B12 404 同一性、RG1、P3 の結果写像」。**サーバー側の未捕捉例外 → 500 の扱いへの言及は無い**
- `plan.md:77`(故障系)「commit 前例外で原本/台帳/投影の全取消、401/通信断/解釈不能応答のキュー保持」。**例外で全取消することは試すが、その要求が再送で同じ例外を繰り返す場合(恒久失敗)の観点は無い**
- `design.md:116`「RG1 が閉じている時は D5 未消費で B7/B10 … ステータス解釈不能や認証切替は元のキュー・D5 を保持する」
- `research.md:172`「N-1(件数/本文サイズ)、N-2(再送間隔/Retry-After)、N-4(流量制限)は NFR-002 の測定後に判断する。根拠の無い定数を計画で置かない」
- 計画は「要件/正本の意味変更」をスコープ外にしている(`plan.md:34`)。**恒久失敗の受け皿(案 A・B)は 506 の射程外**で、正本の改訂タスクが要る [推論]
- 実装(`httpTransport.ts:98-100`)は 500 → `no-ack` B7 で、キューを維持し通知も出さない。B7 通知・再送スケジューラは 506 のどのステップの合格条件にも無い [検証]。誰が持つかは `design.md:105` の U-F8 後続(「ACK 受理/401・通信断時のキュー保持」)が近いが、再送の繰り返しとその表示の担当は明記されていない [推論]

---

## 5. 参照した主なファイル

- `frontend/src/api/client.ts`、`frontend/src/lib/sync/{boundaryResults,queueState,queueTransition,syncNotices,resendRange,durableQueue}.ts`
- `backend/src/pitchlog/sync/{apply,prefix_path,change_path,idempotency,ordering}.py`、`backend/src/pitchlog/api/errors.py`
- `docs/design/sync-protocol.md`(6-2・6-3・6-4・7-1・7-2・7-3・7-4・10-1)、`docs/features/sync-wire-schema/design.md`(2-4・4-1・6-1・WU-1)、`docs/requirements/requirements-pitchlog-2026-07-22.md`(NFR-015 `:921`・4.0-2 `:174`・FR-012 `:320`)
- 506 worktree: `docs/features/tsk506-sync-http-entry/{plan,design,research}.md`、`frontend/src/lib/sync/httpTransport{,.spec}.ts`
