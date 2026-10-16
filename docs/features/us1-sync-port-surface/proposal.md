---
feature: us1-sync-port-surface
type: proposal
created: 2026-10-16
---

# 具体差分の提示: U-S1・端末の製品変更(TSK-506 への接続)

計画: [plan.md](plan.md) のステップ 3 / 接続契約: [design.md](design.md) / 調査: [research.md](research.md)

**この文書は何か**: PO 裁定(山田正輝 2026-10-16 — plan.md:25)「U-S1 の挙動変更や共有資産の製品変更は包括承認していない。具体差分をまとめて 1 つの文書で提示する」に応える。**ここに書いた差分はまだ実装していない**。PO が差分ごとに承認・不承認を選び、承認されたものだけを計画追補でステップに起こして実装する(1 差分 = 1 ステップ = 1 コミット)。

**読み取り元**: worktree `feature/us1-sync-port-surface` HEAD `b63d11e9`。製品コードは develop `e7e8d3a4` と同一(本ブランチの差分は文書だけ — `git diff --stat e7e8d3a4..HEAD`)。行番号はこの時点のもの。

**略記**: パスの `backend/src/pitchlog/` を省く(例 `sync/apply.py:292`)。端末は `frontend/src/lib/sync/` を省かずに書く。`SP` = `docs/design/sync-protocol.md`(**v0.9 起案の行番号** — 本設計 design.md は v0.8 の行番号で引いているので、同じ箇所でも数値が違う)。`WS` = `docs/features/sync-wire-schema/design.md`(本ブランチ)。`本設計` = `docs/features/us1-sync-port-surface/design.md`。`506/plan` = `feature-tsk506-sync-http-entry` の `docs/features/tsk506-sync-http-entry/plan.md`(`8fb05496` — 読むだけ)。推論には **[推論]** を付ける。

---

## 0. 承認の単位(PO はこの表で選ぶ)

| ID | 何を変えるか | 承認すると実装されるもの | 506 のゲート(本設計 2-1) | 依存 | PO が選ぶこと |
| --- | --- | --- | --- | --- | --- |
| **D-1** | E-1 の混在バッチの公開口 | 経路を持たない要求型 `SyncEventBatch` と入口 `apply_sync_events`。イベントごとに SP 8-1 の対応表で P1/P2 を判定し、その経路で指紋を取り、単一の `AckResult` を返す。既存の `apply_sync_request` は残す | **G-A** | D-2(wire の墓標・改訂版の経路を決めるのに元の種別が要る)。TSK-331 の合意は D-2 経由 | 承認 / 不承認 |
| **D-2** | V5・V10・V9 の wire → U-S1 の変換 | 変換の置き場所(案 ① か ②)。墓標・改訂版は拒否原本から元の種別を引く | **G-B** | **TSK-331 の合意**(V9 に `rejected_d5` を運ぶ・案 ① なら WS:362 の担当の付け替え)。端末の墓標生成器が V9 を作っていない件(2-4) | **案 ① / 案 ②** と、付帯の 2 つ(**D-2b** V10 のキーを wire に揃えるか・**D-2c** 不正種別の原本への墓標をどうするか) |
| **D-3** | 公開結果型の構造化 | A5 の各件に B3 の分岐(内容起因 B3a/B3b・O4・O5)を持たせる。P3 の拒否に `current_version`(B8)・`b9_cause`(B9)を持たせる | **G-C** | D-4(O5 の分岐を載せるため。D-4 を承認しない場合は O5 抜きで実装できる) | 承認 / 不承認 |
| **D-4** | O5 のサーバー側 | 本設計 11-1 の 7 件を専用の例外型で投げ、当該イベントの取引を全取消して B3 + A5「拒否」(理由コード O5)へ写す。7 件の列挙と、`raise` 全件の棚卸しを pytest で突合する | なし(506 の HTTP 写像〔本設計 4 節〕と確認条件〔8 節〕の前提) | SP v0.9(**確定済み — 2026-10-17 PO 承認**)。D-6 と組で承認しないと効果が出ない(5 節) | 承認 / 不承認 |
| **D-5** | 内容起因の `other` を B3a へ | 本設計 11-2 の B3a 7 件を、内容拒否の例外型で投げ直し、T9 + B3a に載せる | なし(同上) | なし(単独で実装できる) | 承認 / 不承認 |
| **D-6** | 端末の O5 | 拒否理由に O5 を足し、O5 を要操作(管理者対応待ち)へ移し、O5 の再開(内容も D5 も変えずに未送信へ)を O4 の再開(QT-07 — 新しい D5)と別の遷移にする | なし(506 の codec が受理する前提) | D-4・SP v0.9(確定済み) | 承認 / 不承認、付帯 1 つ(**D-6a** O4/O5 の別をスロットに持たせるか) |
| **D-7** | 故障系資産(NFR-019(d))の O5 | SP 10-2 に足した O5 の観点(SP:1699)を母集合に入れる(資産の作成か繰り延べ行) | なし | D-4。凍結資産の版上げ | **作成 / 繰り延べ行 / 見送り** |

**推奨の実装順**(承認されたものだけ): D-5 → D-4 → D-3 → D-2 → D-1 → D-6(→ D-7 は D-4 と同じステップで取り込むか、最後) [推論 — 小さく独立したものから。D-1 は D-2 の変換に乗る。D-6 はサーバー側の O5 が出てから]。

**この文書で決めないもの**: 8 節(担当が別)。

---

## 1. D-1 E-1 の混在バッチの公開口(G-A)

### 1-1. 現状(問題)

- 要求は経路を 1 つしか持たない(`sync/model.py:158` `path: ApplicationPath`)。経路は D5 の指紋に入る(`sync/idempotency.py:277` `"path": path`)
- 適用核の内部で要求の経路を参照している箇所: `sync/apply.py:92`(④ の指紋)・`:153`・`:157`(経路の分岐)・`:179`・`:189`(T8/T9 へ渡す経路)・`:233`(⑤ 不成立の退避)・`:257`・`:268`(⑤ 不成立の再掲)・`:307`(P3 の分岐)・`:323`(P4 の要求で記録権が成立した場合の例外 `:327`)。あわせて `sync/idempotency.py:167`(`classify_request_d5` が `request.path` で D5 を分類 — 経路は B3b と B13 の分岐にだけ効く `:136`)
- 正本の経路は種別で決まる(SP:1300-1315 — 毎球入力・選手交代・タイブレーク開始・試合終了宣言・状態補正 = P2 / undo・選手のその場登録・墓標 = P1 / 改訂版 = 元イベントの参加区分を継承)。wire は「経路はクライアントが選ばず、サーバーが判定する」(WS:163)。506 の承認済み計画はステップ 4 の着手前に「P1/P2 混在バッチを単一 ACK・D1 順・部分成功で処理する型/関数」を求め、HTTP 側での分割を禁じる(506/plan:49・:64)

### 1-2. 署名(新設)

```python
# sync/model.py(新設 — SyncRequest の隣)
@dataclass(frozen=True, slots=True, init=False)
class SyncEventBatch:
    """E-1 の D1 付き要求。経路を持たない(イベントごとにサーバーが判定する)。"""
    game_id: str
    d4: str
    events: tuple[SyncEvent, ...]
    v12: StageValue = ABSENT

    @classmethod
    def from_payload(cls, game_id: str, payload: object) -> SyncEventBatch:
        """E-1 本文の S-1 外形を照合する(案 ① ではここで純粋な変換も行う — D-2)。"""

# sync/routing.py(新設)
def route_for_event(event: SyncEvent, original_path: Literal["P1", "P2"] | None) -> Literal["P1", "P2"]:
    """SP 8-1 の対応表でイベントの経路を返す。永続状態に依らない(改訂版は原本の経路を引数で受ける)。"""

# sync/apply.py(新設)
def apply_sync_events(
    context: TenantContext,
    batch: SyncEventBatch,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    *,
    registrations: Mapping[str, PlayerRegistration] | None = None,
    targets: Mapping[str, P1Target] | None = None,
) -> AckResult | Literal["B6", "B7"]:
```

- 本設計 2 節(`:41`)の仮称は `apply_sync_events(context, game_id, payload, ...)` だったが、**S-1(422)と適用を分ける既存の 2 段呼び出し**(`from_payload` → `apply_sync_request` — 本設計 1-1 `:22-23`)に合わせ、本文の照合は `SyncEventBatch.from_payload` に置く。名前・所在は実装のコミットで確定し、本設計 2 節と 10 節を更新する
- **既存の `SyncRequest.from_payload` と `apply_sync_request` との関係**: 両方とも残す。E-2(P3)と、経路を明示する既存の試験・故障系資産(例: `tests/fixtures/sync-protocol-failures/d1-mixed-batch_v1.json` は毎球入力を `applicationPath: "P1"` で送る)が使う。S-1 の D1 付き経路の照合(`sync/model.py:195-217`・本文の取り出し `:272-310`)は、`SyncRequest` と `SyncEventBatch` が**同じ内部関数を呼ぶ形に括り出す**(S-1 の規則を 2 か所に持たない)
- `apply_sync_events` は **P4 を要求の経路として使わない**。⑤ の不成立は、従来どおり U-S1 の内部で T8 へ回す(`sync/apply.py:356-379`)。退避の指紋はイベントの経路(P1/P2)で取る。`:322-327` の検査(P4 の要求で記録権が成立)は新しい入口では到達しない(research G-1b への回答)

### 1-3. 挙動

1. **経路の判定**(`route_for_event`): V9 が墓標 → **P1** / V9 が改訂版 → **拒否原本の経路**(下記)/ それ以外は V5 が `_P2_LOGICAL_KINDS`(`sync/prefix_path.py:87` = `db/sync_protocol/event_kinds.py:159-162` の論理位置を持つ 4 種別 + 状態補正)なら **P2**、それ以外(undo・その場登録・**V5 が欠落・未知の値**)は **P1**。表は既存の定数から導き、新しい表を作らない(NFR-018)。V5 が不正なイベントは P1 で ⑦ に入り、`_event_kind` で B3a になる(`sync/prefix_path.py:223-230`)— 経路の判定は例外を投げない
2. **改訂版の経路**: 「元イベントの参加区分を継承」(SP:1312)。U-S1 の表現では改訂版の V5 は原本の種別と一致が強制される(`sync/prefix_path.py:284-287`)ので、多くの場合は V5 から引ける。ただし原本が墓標だった場合などに V5 だけでは決まらないので [推論]、**T9 の拒否原本に経路を保存し**(`sync/rejection.py:98-102` の `_original` に `"path"` を足す — `operation_fingerprint` を足している既存の前例 `:101` と同じ形)、改訂版はそれを引き継ぐ。`"path"` の無い旧原本は 1 の規則で原本の V5・V9 から導く。原本は内容更新を禁止されている(`authz/runtime_contract.py:127` の `prevent_rejected_event_originals_content_update`・`sync/tokens.py:211`・`:219` は読取と挿入だけ)ので、**同じ改訂版は常に同じ経路・同じ指紋になる**
3. 原本の読取は ④ の前処理の取引(`sync/apply.py:87` の `tenant_transaction_scope`)で行い、指紋(`:90-95`)より先に経路を確定する。案 ① の D-2 の墓標・改訂版の変換と同じ読取を共用する
4. **内部の作り替え**: `_preflight_d1`(`:80-137`)・`_run_d1_event`(`:140-201`)・`_escrow_without_right`(`:219-238`)・`_replay_existing`(`:241-284`)の引数を `request` から「`game_id`・`d4`・`v12` と、イベントごとの `path`」へ変え、`apply_sync_request` の `:313-434` のループ本体を共通関数へ括り出す。`apply_sync_request` は全イベントに `request.path` を渡す(**挙動は不変** — 既存の試験が回帰の検査になる)。`apply_sync_events` は `route_for_event` の結果を渡す。経路の対応は **D1 で引く**(要求内で D1 は一意 — `sync/model.py:213-215`。D5 は重複を S-1 で拒否しない — `tests/test_sync_apply_model_ports.py` の `test_duplicate_d5_is_left_for_processing` — ので D5 では引かない)
5. D5 の事前分類は、イベントごとの経路で `classify_d5`(`sync/idempotency.py:139-145`)を呼ぶ(`classify_request_d5` の `request.path` は使わない。E-1 に P3 は来ないので B3b/B13 の分岐は変わらない)
6. 戻り: 単一の `AckResult`。D1 昇順・部分成功・停止境界は 1 つ(DI5 — SP:1298)。⑥ の欠落・B3・B4 の扱いは `apply_sync_request` と同一(同じループ)

### 1-4. 既存の試験・資産への影響

- 既存の試験は `apply_sync_request` を使い続けるので変えない [推論 — ループの括り出しは挙動を変えない前提。括り出しのコミットで既存の `backend/tests/test_sync_apply_apply.py`・`backend/tests/db/test_sync_apply_*` が green であることを合格条件にする]
- 故障系資産(`tests/fixtures/sync-protocol-failures/*`)は版を上げない(旧入口で走る)。新しい入口の故障系は DB 試験で足す(資産の版上げは D-7 で別に選ぶ)

### 1-5. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | `route_for_event` の全行(#1〜#7・墓標・改訂版〔原本 P1/P2・`"path"` 無しの旧原本〕・V5 欠落/未知/非文字列 → P1)。同じイベントで何度呼んでも同じ値(永続状態を渡せない署名で担保)/ `SyncEventBatch.from_payload` の S-1 が `SyncRequest.from_payload` と同じ違反を同じ例外で拒否する(既存の S-1 の表 `tests/test_sync_apply_model_ports.py:210-213` を両方に流す)/ **負例**: 本文に経路のキーを足すと S-1(未知キー — `sync/model.py:272-274`) |
| 単体(偽ポート) | 混在バッチ `[毎球入力, undo, その場登録, 毎球入力]` で各イベントが P2/P1 の局所経路へ渡り、指紋の経路がイベントごとに違うこと |
| DB 境界 | 混在バッチの単一 ACK・D1 昇順・部分成功(途中の B3a で前方は受理・後方は未処理)/ 同じ要求の再送で全件「重複」(DI2 — 指紋が一致)/ ⑤ 不成立の混在バッチで各イベントがイベントの経路の指紋で退避され、再送で再掲される / 改訂版が原本の経路(P2 なら T5 の採番を通る)で適用される / D1 欠落で B2 |
| 故障系 | 混在バッチの途中のイベントの取引内で注入(既存の `reach` の点 — `sync/crash_points.py`)→ 再送で前方は保存済み結果、当該は未使用として再適用 |

### 1-6. この差分が無いと 506 の何が止まるか

506 のステップ 4(backend の E-1 router)の**着手条件**が満たされない(506/plan:49 — 「現行 `SyncRequest.path` の単一値を HTTP が独自に分割して埋めない」)。DoD の「E-1 の単一/混在バッチの P1/P2 分類 … が U-S1 担当と受理済み」(506/plan:64)も閉じない。506 が単一経路の要求で送ると、毎球入力を P1 で送れば T5(D2 採番)を通らずに保存され、undo・その場登録を P2 で送れば B3a で T9 に永久に記録される(`sync/prefix_path.py:614-617`・`:636-638` — research G-1)。

---

## 2. D-2 V5・V10・V9 の wire → U-S1 の変換(G-B)

### 2-1. 現状(問題)

| 値 | wire | U-S1 が受けるもの | 変換が無いと |
| --- | --- | --- | --- |
| **V5** | 正本 5-5 の番号の文字列(E-1 `"1"`〜`"9"`・E-2 `"10"`〜`"12"` — WS:201・WS:237) | 種別のリテラル `play_input` 等(`sync/prefix_path.py:223-230`・`sync/change_path.py:173-176`) | E-1 は正規の毎球入力が B3a で T9 に永久に記録される / E-2 は B14 |
| **V5 の墓標・改訂版** | `"8"`・`"9"`(元の種別を運ばない) | 元の種別のリテラル + V9 の `tombstone`/`revision`(`sync/prefix_path.py:197-220`・`:284-287`) | 同上(B3a)。元の種別は拒否原本(T9)からしか分からない |
| **V9** | `replacement_state`。中身を WS は決めていない(WS:205) | `{"tombstone": true, "rejected_d5": "<D5>"}` または `{"revision": true, "rejected_d5": ...}`(`sync/prefix_path.py:201-204`) | 形が合わず B3a(`:205`) |
| **V10** | `target_reference` = `{"game_id", "d4", "d1"}`(WS:206) | `{"game", "d4", "d1"}`(`sync/prefix_path.py:237`・`:366`・`sync/change_path.py:78`) | undo は B3a(`:374`)、墓標・改訂版は W2 違反で B3a(`:238`)、P3 は B14(`change_path.py:184`) |

- 変換後の値が指紋に入る(`sync/idempotency.py:274-289` が `event_source` 経由で V5〜V11 を全部含める `:77-94`)。**変換は決定的で、版を固定する必要がある**
- 変換表の材料は既にある: `db/sync_protocol/event_kinds.py:85-128` の `OPERATION_EVENT_PARTICIPATIONS`(番号 → リテラル。#8・#9 はリテラルなし)。端末側の番号は `frontend/src/lib/sync/eventKinds.ts:29-114` の `id`(同じ SP 5-5 の番号)
- **本設計 2-1 G-B(`:55`)の記述の訂正**: 「① の案(U-S1 の `from_payload`)は拒否原本を同じトランザクションで読めるので成立する」とあるが、`from_payload` は DB に触れない classmethod である(`sync/model.py:230-233` — 引数は経路・試合・本文だけ)。**墓標・改訂版の原本の読取は、案 ① でも適用の前処理の取引(`sync/apply.py:87`)で行う**。以下はこの前提で書く

### 2-2. 2 案

| | **案 ① U-S1 が写す** | **案 ② 506 が写し、表は U-S1 が公開する** |
| --- | --- | --- |
| 純粋な変換(V5 の `"1"`〜`"7"`・`"10"`〜`"12"`、V9 の形、V10 のキー) | `SyncEventBatch.from_payload`(D-1)と `SyncRequest.from_payload` の P3 分岐(`sync/model.py:235-271`)の中で写す | 506 の `sync/http_wire.py`(506/plan:43 の候補パス)が U-S1 の公開関数(例 `pitchlog.sync.wire_values.event_kind_literal(value)`)を呼んで写し、変換済みの値で `SyncEventBatch` を作る |
| 墓標・改訂版の元の種別(`"8"`/`"9"`) | `apply_sync_events` の前処理の取引で `rejected_d5` の原本を読み(`RejectedOriginalReadToken` — `sync/tokens.py:211`)、V5 を原本の `event_kind` に、V9 を U-S1 の形に置き換えてから指紋を取る(D-1 の経路の判定と同じ読取) | 506 は原本を読めない(U-S1 の内部の token — 本設計 1-1 `:27`)ので、**U-S1 が別の公開口**(例 `resolve_replacement_events(context, game_id, events) -> tuple[SyncEvent, ...]` — 自分で読取の取引を開く)を出し、506 はそれを呼んでから適用を呼ぶ。経路の判定(D-1)は適用の前処理で原本をもう一度読む |
| 変換表の持ち主 | U-S1(`sync/` に 1 か所) | U-S1(同じ 1 か所。506 は呼ぶだけ) |

**代償の比較**

| 観点 | 案 ① | 案 ② |
| --- | --- | --- |
| **NFR-018(コピー実装)** | 表と適用が同じ単位にあり、コピーは生じない | 表は 1 か所だが、**呼び出しの順序**(純粋な変換 → 原本の解決 → 適用)を 506 が組む。506 側に「番号のまま通す」「一部だけ自前で写す」余地が残る。表を自前で持てば P0(AGENTS.md の Code Review Rules)[推論] |
| **指紋の安定性** | 変換と指紋が同じ関数の中で続けて起きる。入口が変換を飛ばす経路が無い(`apply_sync_events` は wire 形の値だけを受ける) | 506 が変換を呼び忘れる・順序を誤ると、**番号のままの V5 が B3a として T9 に記録され、その D5 は永久に消費される**(`sync/prefix_path.py:230` → `sync/rejection.py:207-209`)。誤りが不可逆 |
| **所有** | **WS:362 は「U-S1 のサービス層の型との対応は … 入口 PR の義務」とする**(N-18)。案 ① はこの担当を U-S1 へ付け替えるので、**TSK-331 の合意と WS の追記が要る**。U-S1 が wire の語彙(番号)を知ることになる | WS の担当分けのまま。U-S1 は wire の語彙を知らない(公開する表は「番号 → リテラル」の 1 枚) |
| **墓標・改訂版の変換の成立** | 成立する(前処理の取引で読む。原本は不変 — 1-3 の 2) | 成立するが、**取引が 1 つ増える**(読取 → 適用前処理でもう一度読取)。スコープごとの接続生成の費用(research G-13)が 1 要求あたり 1 回増える。原本は不変なので、2 回の読取の間に値が変わる心配は無い |
| 506 の実装量 | 本文を `SyncEventBatch.from_payload` に渡すだけ | 純粋な変換の呼び出し・原本の解決の呼び出し・その順序の試験 |

**推奨: 案 ①**。根拠: (1) 案 ② の主な代償(変換の呼び忘れで D5 が T9 に不可逆に消費される)は、HTTP の試験でしか検出できず、起きたら戻せない。案 ① は入口の型がそれを不可能にする。(2) 墓標・改訂版は DB の読取が必須で、どちらの案でも U-S1 に変換の口ができる。案 ② は変換が 2 単位に分かれるだけで、U-S1 の責務は減らない。(3) 案 ① の代償(WS:362 の担当の付け替え)は文書の合意で済み、製品の安全性に効かない。**ただし案 ① は TSK-331 の合意が前提**(合意が得られなければ案 ②)。

### 2-3. 共通の規則(どちらの案でも)

- **S-2 の値を例外にしない**: 未知の番号・非文字列・欠落はそのまま通し、処理段階が B3a/B14 にする(WS:201 は V5 を S-2 とする — `tests/test_sync_apply_model_ports.py:234-251` は `event_kind: {"invalid": true}` を保持することを検査しており、この試験は green のまま)
- **V9 の wire 形**: `{"rejected_d5": "<D5>"}`(墓標か改訂版かは V5 の `"8"`/`"9"` で表す)を **WS に明記する — TSK-331 の合意が要る**(本設計 2-1 G-B と同じ)。`rejected_d5` が無い・原本が無い場合は変換せずに通し、⑦ で B3a になる(`sync/prefix_path.py:205`・`:261`)[推論 — 原本の無い `rejected_d5` を送るのは端末の誤りに限られる。後からその D5 が拒否されると、同じ D5 の再送の指紋が変わり B3b になりうる。残余として記録する]
- 変換は E-2(P3)にも掛ける(V5 `"10"`〜`"12"`・V10 のキー)。P3 の受理結果の `target_reference`(`試合`・`対象の D4`・`対象の D1` — `sync/change_path.py:216-220`・`sync/model.py:389`)を wire の `game_id`・`d4`・`d1`(WS:322)へ写すのは**出力側の codec**(506)で、本差分に含めない。`対象の D4` が整数で返る件は U-R1 の決定待ち(本設計 6 節・research G-4)

### 2-4. 付帯の選択

**D-2b V10 のキー**: 案 ①・② とも、`{"game_id", ...}` → `{"game", ...}` の**改名だけ**で写すと、wire にない `{"game", ...}` を端末が送った場合に**改名されずに U-S1 で受理される**(`sync/model.py:279-309` は V10 の中身を見ない — S-2)。[推論] 推奨: **改名せず、U-S1 の内部キーを wire に揃える**(`sync/prefix_path.py:237`・`:239`・`:366`・`:371`・`sync/change_path.py:78`・`:80` の `"game"` を `"game_id"` に)。V10 の変換が不要になり、抜け道も消える。指紋に入る値が変わるが、本番の保存データは無い [推論]。

**D-2c 種別が不正な原本への墓標**: 本設計 2-1 G-B は「墓標では元の種別の検査を外し、`rejected_d5` の原本との照合だけを行う」とする。しかし**墓標の行も `operation_events.event_kind` に有効なリテラルが要る**(`db/sync_protocol/models.py:140-143` の `ck_operation_events_event_kind` = `event_kinds.py:420-422`。墓標の行の作成は `_event_kind(event)` を使う — `sync/prefix_path.py:392`)。種別が不正で拒否された原本には書ける種別が無く、**U-S1 の変更だけでは墓標を適用できない**。改訂版も元の種別の継承が強制される(`:284-287`・SP:1312)ので、この原本は 2 択のどちらでも再開できない(SP:868 の (b) 破棄に反する)。選択肢:
- (i) **本差分では扱わず残余に記録する**(推奨 [推論] — 端末は種別を `EVENT_KIND_RULES` から選ぶので、不正な種別は端末の誤りでしか生じない)
- (ii) データモデル(墓標の種別の表現 — `operation_events` の CHECK)の改訂を data-model の担当へ送る

### 2-5. 依存(本差分の外)

- **端末の墓標生成器が V5・V9・V10 を作っていない**: `frontend/src/lib/sync/k5Tombstone.ts:179-189` は墓標のイベントを空の `fields` で作る(V5 `"8"`・V9 の `rejected_d5`・V10 が無い)。506 の codec(`frontend/src/lib/sync/wireCodec.ts` — 506 の worktree)にも墓標・改訂版の扱いは無い(`grep` で 0 件)。D-2 を実装しても、端末が送る墓標は U-S1 で B3a になる。**直す担当は端末側(U-F7/U-F8 か 506 の codec)で、本文書では提示しない**(7 節)

### 2-6. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | 番号 → リテラルの全行(#1〜#7・#10〜#12)が `OPERATION_EVENT_PARTICIPATIONS` と一致 / 未知・非文字列・欠落を変えずに通す(負例)/ V10・V9 の写し(D-2b を採るなら V10 は恒等)/ 同じ入力で何度呼んでも同じ出力 |
| 一致性 | 端末の `EVENT_KIND_RULES` の `id` と backend の番号 → リテラルの表が同じ集合(Vitest か pytest のどちらか 1 か所 — 契約試験として `contracts/` の既存の型に載せるかは実装時に決める [推論]) |
| DB 境界 | wire 形の `"9"` + `rejected_d5` で、原本の種別・経路を継承して適用 / `"8"` で墓標として適用 / 原本が無い `rejected_d5` → B3a / 同じ改訂版の再送で同じ指紋(DI2)/ E-2 の `"10"` が P3 で受理される |
| 故障系 | 原本の読取の後・適用の前に注入 → 再送で同じ変換・同じ結果 |

### 2-7. この差分が無いと 506 の何が止まるか

506 が wire の値をそのまま U-S1 へ渡すと、**正規の毎球入力が全件 B3a で T9 に永久に記録される**(`sync/prefix_path.py:230`)。506 の DoD「1 球を HTTP 経由で実 DB 原本・投影へ保存し、再読込」(506/plan:68)が成立しない。506 が独自に写すと NFR-018 のコピー実装(P0)になる。

---

## 3. D-3 公開結果型の構造化(G-C)

### 3-1. 現状(問題)

- `A5Result` は `(d4, d1, d5, state, reason: str | None)` だけで、B3 の分岐を持たない(`sync/model.py:320-328`)。分岐は要求に 1 つの `AckResult.b3_branch`(`:338` — 型 `B3Branch = Literal["B3a", "B3b", "O4"]` `:51`)で、停止したイベントの分だけ
- wire は「拒否」の**各件**に `rejection: {kind, branch, reason}` を求める(WS:308 — `kind` は `"内容起因"`・`"O4"`・`"O5"`、`branch` は内容起因のときだけ `"B3a"`/`"B3b"`)。停止イベント以外の「拒否」は、B4 の要求で保存済み B3a を再掲したもの(`sync/apply.py:370-379` → `sync/rejection.py:85-95`)
- P3 の拒否は `RejectedChangeResult(boundary, d5, reason: str | None)` だけ(`sync/model.py:409-420`)。wire は B8 に `current_version`、B9 に `b9_cause`(`"記録権不保持"`/`"旧復旧世代"`)を求める(WS:341-342)。U-S1 は文言で区別している(`sync/change_path.py:148` 旧復旧世代・`:171` 記録権不保持・`:212` `f"現在版: {current_version}"`)— 文言の解析で写すと壊れやすい(research G-7)

### 3-2. 署名

```python
# sync/model.py
type RejectionKind = Literal["内容起因", "O4", "O5"]
type B3Branch = Literal["B3a", "B3b", "O4", "O5"]          # :51 に "O5" を足す(D-4 を承認しない場合は足さない)

@dataclass(frozen=True, slots=True)
class A5Rejection:
    """A5「拒否」1 件の B3 の分岐と理由(WS 4-2 の rejection)。"""
    kind: RejectionKind
    branch: Literal["B3a", "B3b"] | None   # kind == "内容起因" のときだけ値を持つ(__post_init__ で検査)
    reason: str

@dataclass(frozen=True, slots=True)
class A5Result:                             # :320-328
    d4: str; d1: int; d5: str; state: A5State
    reason: str | None = None               # 既存(残す)
    rejection: A5Rejection | None = None    # 追加 — state == "拒否" のときだけ値を持つ

@dataclass(frozen=True, slots=True)
class RejectedChangeResult:                 # :409-420
    boundary: RejectedChangeBoundary; d5: str; reason: str | None = None
    current_version: int | None = None      # 追加 — B8 のときだけ(必須)
    b9_cause: Literal["記録権不保持", "旧復旧世代"] | None = None   # 追加 — B9 のときだけ(必須)
```

`apply_sync_request`・`apply_sync_events` の署名は変えない(戻り値の型の中身が増えるだけ)。

### 3-3. 挙動

- `sync/apply.py:402-406`(A5 の 1 件を作る箇所)で、局所結果から `A5Rejection` を作る: `RejectionResult.boundary` の `"B3a"`/`"B3b"`(`sync/rejection.py:82`・`:152`)→ 内容起因 / `P1Result` の B3a・B3b(再掲 `sync/prefix_path.py:865-871`・衝突 `:432`)→ 内容起因 / O4・O5(D-4 で `P1Result` に足す区分 — 5-2)→ `kind` = `"O4"`/`"O5"`。B3b の理由は既存の文言(`sync/apply.py:403-405`)
- `AckResult.b3_branch`・`reason`(`:338-339`)は残す(既存の試験・故障系資産が読む — `backend/tests/db/test_sync_apply_failure_runner.py:860` ほか)
- P3: `sync/change_path.py:147-149` → `b9_cause="旧復旧世代"` / `:170-172` → `b9_cause="記録権不保持"` / `:211-213` → `current_version=current_version`。文言(`reason`)は変えない
- `RejectedChangeResult.__post_init__`(`sync/model.py:417-420`)に「B8 ⇔ `current_version`・B9 ⇔ `b9_cause`」の検査を足す。**既存の試験 2 箇所が `RejectedChangeResult("B9", d5)` を作っている**(`backend/tests/test_sync_apply_model_ports.py:125`・`backend/tests/test_sync_apply_gate.py:321`)ので同じコミットで直す。必須にしない(None を許す)なら試験は変えずに済むが、506 が値の存在に頼れなくなる — **推奨は必須** [推論]

### 3-4. 既存の試験・資産への影響

既存の試験は A5 をフィールドの射影で比べている(例 `backend/tests/test_sync_apply_apply.py:69`・`backend/tests/db/test_sync_apply_apply_boundary.py:177`)。`A5Result(...)` を「拒否」で直接作って比べる試験は 0 件(`grep`)。追加フィールドで壊れるのは上の 2 箇所だけの見込み [推論]。故障系資産の観測フィールド(`b3Branch` 等)は変えない。

### 3-5. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | `A5Rejection` の不変条件(**負例**: 内容起因で `branch` 無し・O4/O5 で `branch` あり・「拒否」以外で `rejection` あり → 例外)/ `RejectedChangeResult` の B8・B9 の排他(負例: B8 で `b9_cause`・B14 で `current_version`)|
| 単体(偽ポート) | B3a 停止・B3b 停止・O4・O5・B4 の要求での保存済み B3a の再掲の各件で `rejection` が正しい |
| DB 境界 | 既存の P3 境界試験(`backend/tests/db/test_sync_apply_change_boundary.py`)に B8 の `current_version`・B9 の 2 原因を足す |

### 3-6. この差分が無いと 506 の何が止まるか

506 のステップ 4 の結果写像(N-18 の U-S1 型 ↔ wire キー対応 — 506/plan:58)が、`event_results[].rejection` を停止イベント以外で推論し、`current_version`・`b9_cause` を文言の解析で埋めることになる。文言を変えると黙って壊れる。

---

## 4. D-5 内容起因の `other` を B3a へ

### 4-1. 対象(本設計 11-2 `:200` の B3a 7 件)

| 箇所 | 現行 | 理由(本設計 11-4) |
| --- | --- | --- |
| `sync/prefix_path.py:444`・`:448`・`:450` | `P1PreconditionError("選手参照は UUID 文字列が必要")` ほか(`_resolve_player_reference`) | V7 の選手参照の内容で決まる |
| `sync/prefix_path.py:470` | `P1PreconditionError("一時選手 ID の確定写像がない")` | 端末が送った参照で決まる |
| `sync/prefix_path.py:496` | `P1PreconditionError("V5 で定義されない選手参照位置")`(`_resolve_payload`) | V7 の形で決まる |
| `sync/prefix_path.py:680` | `P1PreconditionError("一時 ID は別の確定写像に使用済み")` | その場登録の内容で決まる |
| `sync/ordering.py:34` | `P1PreconditionError("P2 の V6 は非負の bigint が必要")` | 端末が送った V6 で決まる |

いずれも ⑦ の `try`(`sync/prefix_path.py:612-639`)の外で投げるので、`P1ContentRejection` へ変換されず、`sync/apply.py:198-199` から再送出 → 500 → B7(永久再送)になっている。

### 4-2. 変更

7 箇所の例外を **`P1ContentRejection(<同じ文言>)`** に変える(`sync/prefix_path.py:841-842` — `P1PreconditionError` の部分型)。`sync/ordering.py:16` の import に `P1ContentRejection` を足す。公開口・型の追加は無い。

### 4-3. 挙動

- 取引は例外で全取消(`sync/prefix_path.py:788` の `tenant_transaction_scope` を例外で抜ける)→ `_run_d1_event` の `:183` が `isinstance(error, P1ContentRejection)` で拾い、新しい取引で T9 に原本・D5・理由を保存して B3a(`sync/rejection.py:207-209`)。端末は 2 択(改訂・墓標)で再開できる
- 7 箇所はすべて D5 の再照合(`sync/prefix_path.py:581-584`)より後なので、保存済み結果の再掲では起きない(DI2 を壊さない)
- **既存の試験は green のまま**: `pytest.raises(P1PreconditionError, match=...)` は部分型でも通る(`backend/tests/test_sync_apply_ordering.py:208`・`backend/tests/test_sync_apply_prefix_path.py:730`・`backend/tests/db/test_sync_apply_prefix_path_boundary.py:600` — いずれも局所関数を直接呼ぶ)
- [推論] 補足: V6 の上限を ⑦ の `_d2`(`sync/prefix_path.py:316` は下限だけを見る)にも足せば、P2 以外の経路での上限超え(DB の bigint 溢れ → B7)も B3a に寄る。本差分に含めるかは任意(含めると ⑦ の判定が 1 つ増える)

### 4-4. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | 7 箇所それぞれが `P1ContentRejection` を投げる / `_run_d1_event` が `cause="content_rejection"` で T9 経路へ渡す |
| DB 境界 | 各入力で T9 の原本・台帳 `rejected`・A5「拒否」(B3a)・D3 不前進・T5 の再採番が戻っている / 同じ D5 の再送で保存済み B3a を再掲 / その改訂版で再開できる |
| 負例 | B7 に残す `RuntimeError`(例 `sync/prefix_path.py:549`)が 500 のまま |

### 4-5. この差分が無いと 506 の何が止まるか

端末の内容の誤り(選手参照の誤記・一時 ID の再使用・V6 の範囲外)が 500 → B7 になり、**永久再送・先頭詰まり・理由の非表示**(plan.md:22)。506 の故障系(506/plan:76)で「解釈不能・5xx でキュー保持」は確かめられても、利用者が改訂・墓標で抜けられない。

---

## 5. D-4 O5 のサーバー側

### 5-1. 対象(本設計 11-1 `:167` の 7 件)

| 箇所 | 現行 | 関数 |
| --- | --- | --- |
| `sync/prefix_path.py:459` | `RuntimeError("正式選手 ID の型が不正")` | `_resolve_player_reference`(`:689` の `_projection_event` から) |
| `sync/prefix_path.py:651` | `RuntimeError("D1 に複数の現行行がある")` | `_apply_locked` |
| `sync/prefix_path.py:653` | `RuntimeError("現行イベントのスロットがない")` | `_apply_locked` |
| `sync/prefix_path.py:729` | `RuntimeError("D3 の前進に失敗")` | `_apply_locked` |
| `sync/ordering.py:49` | `RuntimeError("D2 順の行の型が不正")` | `_assign_d2`(`sync/prefix_path.py:662` の `order_resolver`) |
| `sync/ordering.py:51` | `RuntimeError("永続化済み D2 が bigint の値域外")` | 同上 |
| `sync/ordering.py:97` | `P1PreconditionError("D2 の局所再採番に必要な隙間がない")`(区分 `other`) | 同上 |

現行は 6 件が未捕捉の `RuntimeError`、1 件が `sync/apply.py:198-199` の再送出で、いずれも 500 → B7。

### 5-2. 署名

```python
# sync/invariants.py(新設 — prefix_path と ordering の双方から import するため。循環を作らない)
type O5Code = Literal[
    "player_mapping_type", "d1_multiple_current_rows", "event_without_slot",
    "d3_advance_failed", "d2_row_type", "d2_out_of_range", "d2_no_gap",
]
O5_CODES: Final[frozenset[O5Code]]          # 列挙の正(7 件)

class O5InvariantViolation(RuntimeError):
    """O5: 未使用 D5 の新規適用の取引内で検出した決定的な不変条件違反(SP 6-3)。"""
    def __init__(self, code: O5Code, message: str) -> None: ...

# sync/prefix_path.py:125-135 の P1Result に追加
    b3_code: Literal["O4", "O5"] | None = None
```

公開口は増やさない(結果は既存の `AckResult` に載る)。

### 5-3. 挙動

1. 7 箇所の例外を `O5InvariantViolation(<code>, <既存の文言>)` に変える。**それ以外の `RuntimeError` は変えない**(列挙の外は B7 のまま — SP:1226 の O5 の定義「対象は実装が列挙する — 列挙の外は ① の B7」)
2. **捕捉する場所**: `sync/prefix_path.py` の `_apply_event` の `except` 群(`:808-813`)に `except O5InvariantViolation as violation: return P1Result("B3", 0, False, a5="拒否", reason=f"O5: {violation}", b3_code="O5")` を足す。O4 の `_NoWriteStop`(`:664-668` で取引の中で投げ、`:812-813` で取引の外で受ける)と同じ形で、**取引のスコープを例外で抜けた後に受けるので、ポートの書き込みを含めて全取消になる**。P1・P2 とも `_apply_event` を通る(`:828-838`・`sync/ordering.py:121-130`)
   - 代替案: `sync/apply.py` の `_run_d1_event`(`:172-199`)で受ける。取消の効果は同じだが、局所経路(`apply_p1_event`/`apply_p2_event`)を直接呼ぶ試験・故障系の実行器からは O5 が例外のまま見える。**推奨は `_apply_event`**(O4 と同じ層)
   - `:198-199` の `else: raise` は残る。O5・B3a を外した後にここへ来るのは `sync/prefix_path.py:592`(S-1 が保証 — 到達しない)・`:607`・`:655` の区分 `other`(確定スロットとの食い違い — v0.9 の確定ゲートで PO に問う。本設計 11-1 `:171`)だけ
3. O4 の識別を区分に移す: `sync/prefix_path.py:664-668` の O4 の結果に `b3_code="O4"` を足し、`sync/apply.py:427` の `b3_branch = "O4" if result.boundary == "B3" else result.boundary` を `result.b3_code`(O4/O5)で決める形に変える。`B3Branch` に `"O5"`(`sync/model.py:51`)
4. **D5 を消費しない**: 7 箇所はすべて D5 の再照合(`:581-584`)より後で、台帳の挿入(`:705-706`)より前か後かに関わらず同じ取引の中なので、取消で台帳の行も残らない(`:729` は挿入の後だが同じ取引)。同じ D5 の再送は、是正前なら同じ O5、是正後なら通常の適用になる(SP:1035)
5. ACK: 当該イベントは A5「拒否」(D-3 を承認すれば `rejection.kind = "O5"`)・D3 は直前まで・後続は未処理・前方は確定済みのまま同じ ACK(`sync/apply.py:425-429` の B3 の停止規則をそのまま使う — SP:777)
6. **理由の文言**: `"O5: " + 既存の固定文言`(O4 の `"O4: 永続化済み D2 の同値"` `:666` と同じ形)。7 件の文言は利用者入力も DB の値も含まない固定文字列(上の表)。理由の語彙は U-S1 が決める(WS:356)

### 5-4. 列挙の仕組みと棚卸しの突合(pytest)

- **列挙の正は型と定数**: O5 は `O5InvariantViolation` を投げた箇所だけ。`O5_CODES` と、`sync/*.py` の AST から拾った `raise O5InvariantViolation(<code>, ...)` の `<code>` の集合が一致することを試験する(過不足を別々に数える)
- **`raise` 全件の棚卸しの突合**: 本設計 11-4 の 193 行を試験データ(例 `backend/tests/sync_raise_inventory.py`)に移し、`sync/*.py` の AST の `raise` 文と一対一で照合する(欠落 0・重複 0)。**キーは行番号でなく「ファイル・関数・例外型・文言・出現順」**にする [推論 — 行番号をキーにすると無関係な編集のたびに試験が落ちる]。行番号は表示用に持つ。D-4・D-5 で型が変わる 14 行は同じコミットで試験データを更新する

### 5-5. 既存の試験・資産への影響

- `backend/tests/test_sync_apply_ordering.py:200`(`pytest.raises(P1PreconditionError, match="隙間がない")`)は `O5InvariantViolation` に直す(`O5InvariantViolation` は `P1PreconditionError` の部分型にしない — 部分型にすると `_run_d1_event:172` の `except P1PreconditionError` に吸われうる)
- 故障系資産(p1/p2 の crash boundaries・o4)は変えない(O5 の箇所を通らない)。O5 の資産は D-7

### 5-6. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体(偽スコープ) | 7 箇所それぞれ: `_apply_event` が `P1Result("B3", a5="拒否", b3_code="O5")` を返し、例外は外へ出ない。**DB の制約で作れない状態**はここで確かめる — `:459`(`player_id` は NOT NULL の Uuid)・`:651`(部分一意索引 `uq_operation_events_active_slot`)・`:653`(外部キー `fk_operation_events_slot` — `db/sync_protocol/models.py:172-184`)・`:729`・`ordering:49`・`ordering:97`(値域の両端までの連続 — `backend/tests/test_sync_apply_ordering.py:194-201` の偽スコープの手法) |
| DB 境界 | DB で作れる状態で 1 本: `ordering:51`(負の D2 の永続行 — `operation_events.d2` に符号の CHECK は見当たらない [推論 — `models.py` の `grep` で未検出])を置き、前方 2 件 + O5 + 後続 1 件を 1 要求で送る。前方は受理・当該は拒否(O5)・後続は未処理・D3 は前方まで・台帳に当該 D5 が無い・T9 なし・T5 の再採番と投影が戻っている・無効化意図なし。状態を是正して**同じ D5** を再送すると受理 |
| 負例 | 列挙の外の `RuntimeError`(`sync/prefix_path.py:549`・`:710`)は 500 のまま / 保存済み結果の再掲では O5 にならない(`:418`・`:422` は B7 のまま) |
| 突合 | 5-4 の 2 本 |

### 5-7. この差分が無いと 506 の何が止まるか

7 件の不変条件違反が 500 → B7 のままで、**その要求は ACK が返らないので、前方の確定済みイベントも端末では未送信のまま、当該イベントで永久再送**(本設計 3-2 `:76-77`)。SP v0.9 の O5 の契約(SP:768・:777)を HTTP 越しに満たせず、本設計 8 節の確認条件「O5 で当該イベントの再送が止まる」(`:142`)を 506 が確かめられない。

---

## 6. D-6 端末の O5

### 6-1. 現状(問題)

- 拒否理由の語彙は `内容起因` と `O4` だけ(`frontend/src/lib/sync/rejectionReason.ts:6-9`)。未知の `kind` は例外(`:90` `'未知の B3 分類です'`)。506 の codec はこの関数で ACK の `rejection` を読む(506 の `frontend/src/lib/sync/wireCodec.ts:288`)ので、**サーバーが O5 を返すと ACK 全体が解釈不能**になり、WS 2-5 によりキューは一切変わらない(前方の受理も同期済みにならない)
- 要操作(管理者対応待ち)の下位ラベルは O4 と共用で 1 つ(`frontend/src/lib/sync/queueState.ts:9`・`frontend/src/lib/sync/queueTransition.ts:33`)。スロットは O4 と O5 の別を持たない(`queueTransition.ts:281-287`・`frontend/src/lib/sync/durableQueue.ts:96-105`)
- 管理者対応待ちからの再開は QT-07 だけで、**新しい D5 を必須**とする(`queueTransition.ts:604-611` の `sameSlotWithNewD5` — `:434-443`)。O5 の再開は「内容も D5 も変えずに未送信へ」(SP:1035)なので QT-07 では表せない
- 自動再送の停止は状態で決まる: 再送範囲は「未送信」だけを選ぶ(`frontend/src/lib/sync/resendRange.ts:156-160`)。要操作へ移せば止まる(変更不要)

### 6-2. 変更と署名

```ts
// rejectionReason.ts
export const B3_REJECTION_KIND = { CONTENT: '内容起因', O4: 'O4', O5: 'O5' } as const   // :6-9
export type B3O5Rejection = Readonly<{
  kind: typeof B3_REJECTION_KIND.O5
  reason: unknown
  correctionConfirmation: typeof O4_CORRECTION_CONFIRMATION.PENDING   // :16-18 を共用(名前の一般化は実装時)
}>
export type B3Rejection = B3ContentRejection | B3O4Rejection | B3O5Rejection          // :35
// parseB3Rejection(:65-91)に O5 の分岐(キーは kind・reason ちょうど — O4 と同じ :76-88 の形)

// queueTransition.ts
B3_REASON_KIND に O5 を追加(:303-307)、B3ReasonClassification に O5(:314-317)
type D1QueueSlot = { ...; adminWaitCause?: 'O4' | 'O5' }                    // :281-287(D-6a)
QUEUE_TRANSITION_ROW_ID.O5_RETRY = 'QT-15'(:87-102)と規則の行(source 要操作 → target 未送信,
  trigger 'o5-retry-persisted', condition 'o5-corrected-same-d5-same-content')
QueueTransitionRequest に { kind: 'o5-retry-persisted'; slot: QueueSlot }(:352-386)
QueueTransitionInjections に confirmO5Correction?: (slot) => boolean | undefined(:332-350)
```

### 6-3. 挙動

1. **未送信 → 要操作**: `applyA5` の O4 分岐(`queueTransition.ts:531-536`)に O5 を並べ、下位ラベル「管理者対応待ち」と `adminWaitCause: 'O5'` を付ける(O4 は `'O4'`)。新しい状態・下位ラベルは作らない(SP v0.9 の射程宣言 — SP:10)
2. **QT-07(O4 の再開)を O4 に限る**: `applyO4Retry`(`:598-624`)の条件に `slot.adminWaitCause !== 'O5'` を足す(`adminWaitCause` の無い既存スロットは O4 とみなす [推論 — 既存の端末に O5 のスロットは存在しない])
3. **QT-15(O5 の再開)**: 条件 = 起点が D1 付きスロット・状態が要操作・ラベルが管理者対応待ち・`adminWaitCause === 'O5'`・`confirmO5Correction(slot) === true`(未注入・例外・`false` は遷移しない — 既存の「外部契約が未注入または確認不能なら状態を変えない」`:2`)。結果 = **同じ `(D4, D1, D5)`・同じ内容**で未送信(ラベルと `adminWaitCause` を外す)。新しい D1 も新しい D5 も作らない(SP:1035・SP:885)
4. `ackAdapter.ts` の分類の注入(`frontend/src/lib/sync/ackAdapter.ts:123-134`)は `rejection.kind` をそのまま渡すので、型の追加だけで O5 が流れる
5. `durableQueue.ts` は `adminWaitCause` を永続化・複写する(`:96-105` の型・`:612-614` の複写)

**D-6a(選択)**: O4 と O5 の別を**スロットの属性 `adminWaitCause` として永続化する**(推奨)か、再開時にサーバーへ問い合わせて決める(`confirmO5Correction` が O4/O5 を返す)か。後者は端末の保存形を変えないが、オフラインで再開条件を判定できない。属性は「下位ラベル」ではなく、SP の「下位ラベルを増やさない」(SP:10)に触れない [推論 — この読みは v0.9 の確定ゲートで PO に確かめる価値がある]。

### 6-4. 既存の試験・資産への影響

- 遷移表の行数の固定: `frontend/src/lib/sync/queueTransition.spec.ts:72`(行 ID の列挙)・`:293` 以下の期待表(リテラル)・`:548`・`:677-678`(14 → 15)/ `frontend/src/lib/sync/prohibitions.spec.ts:2071`(H-59 の遷移の逐語照合 14 → 15 行)。期待表は「正本 7-2 の写し」(`queueTransition.ts:1`)なので、**SP v0.9 の 7-2 の行(SP:1035)が確定した後に**写す
- 型の閉じた集合の検査: `prohibitions.spec.ts:307`(定数名の列挙)・`:533`(型名)・`:1482`(ACK アダプタが供給してはならない注入 — `confirmO5Correction` を `confirmO4Correction` と並べる)・`:1691-1712`(B3 の各型のキーの exact-set)に O5 を足す
- `frontend/src/lib/sync/ackAdapter.spec.ts:287-334`(O4 の分類)に O5 の対を足す

### 6-5. 試験の追加範囲(Vitest)

| 種別 | 内容 |
| --- | --- |
| 単体 | `parseB3Rejection` が O5 を `{kind, reason}` ちょうどで受ける / **負例**: O5 に `branch` → 例外・`reason` 欠落 → 例外 / `applyA5` で O5 → 要操作・管理者対応待ち・`adminWaitCause: 'O5'` |
| 遷移(負例中心) | QT-15: 同じ D5・同じ内容・確認 `true` → 未送信 / 新しい D5 → 不適用 / 内容が違う → 不適用 / 確認が未注入・`false`・例外 → 不適用 / O4 のスロット → 不適用。QT-07: O5 のスロット → 不適用・`adminWaitCause` の無いスロット → 従来どおり |
| 一致性 | 遷移表の行が SP 7-2 の 15 行と一致(既存の期待表方式)/ 再送範囲が要操作の O5 スロットを選ばない(`resendRange.ts` の既存の試験に O5 のスロットを 1 件足す) |
| 永続化 | `adminWaitCause` が IndexedDB の往復で保たれる(既存の `durableQueue.spec.ts` の手法) |

### 6-6. この差分が無いと 506 の何が止まるか

D-4 を入れても、端末は O5 の ACK を解釈できず(`rejectionReason.ts:90`)キューを変えないので、**利用者から見た挙動は B7 の永久再送と同じ**(先頭詰まりも解けない)。D-4 と D-6 は組で承認しないと効果が無い。506 の codec(506 所有)は `parseB3Rejection` に委ねているので、D-6 が入れば 506 側の変更は要らない見込み [推論]。

---

## 7. D-7 故障系資産(NFR-019(d))の O5

### 7-1. 現状

- SP v0.9 は 10-2 に O5 の観点の行を足した(SP:1699)。資産の母集合(`tests/fixtures/sync-protocol-population_v1.json`)は 10-2 の観点と exact-set で一致することを契約にしている(`backend/tests/test_sync_apply_failure_contract.py:961-985` — `"組の観点集合が 10-2 の観点と一致しません"`)。ただし観点の集合は母集合ファイル自身から作る(`:218`)ので、**SP に行を足しても試験は落ちず、乖離が黙って残る**(現在 22 観点 — `:1775`)
- 母集合と資産は版付きの凍結資産で、コア領域(`.claude/core-areas.json:179`)

### 7-2. 選択肢

| 案 | 内容 | 代償 |
| --- | --- | --- |
| (a) 作成 | `tests/fixtures/sync-protocol-failures/o5-deterministic-invariant_v1.json` を作り、母集合を v2 にする(`frontend/src/lib/sync/failureScenarioContract.spec.ts:23-40` の版表・`backend/tests/test_sync_apply_failure_contract.py:1775` の件数も) | 凍結資産の取り込みが 1 回増える。D-4 と同じステップで取り込めば 1 回で済む [推論] |
| (b) 繰り延べ行 | 母集合 v2 に `status: "deferred"` と受け取り先を持つ行だけ足す(既存の U-R1 の行と同じ形) | 取り込みは同じく 1 回。資産は後で別に要る |
| (c) 見送り | 何もしない | SP 10-2 と母集合の乖離が残る(10-3 の契約違反を黙認) |

**推奨: (a) を D-4 と同じステップで**(取り込みを 1 回にまとめる)[推論]。

---

## 8. 本文書では提示しない(担当が別)

| 項目 | 506 への効き方 | 担当(典拠) |
| --- | --- | --- |
| `registrations`(その場登録の選手作成値)の生成 | 無いと、その場登録が B3a で T9 に記録される(`sync/prefix_path.py:628-629`)。登録値は指紋に入る(`sync/idempotency.py:278-287`) | 未割り当て — wire 契約(TSK-331)と端末(U-F7・U-F8)(本設計 2-1 G-F `:59`・5 節 `:108`) |
| `targets`(undo の解決済み対象)の生成 | 無いと undo が B3a(`sync/prefix_path.py:374`) | U-R1(`sync/prefix_path.py:118`・本設計 5 節 `:109`) |
| 506 の端末側の送信範囲の選択器(G-F が埋まるまで、最初のその場登録・undo の手前までの連続部分だけを送る) | 現行の選択器は未送信を全部選ぶ(`frontend/src/lib/sync/resendRange.ts:154-175`) | 506(本設計 2-1 `:61` — 506 の計画のステップ 3 の追補) |
| 配信の起動(`deliver_pending_sync_intents` を呼ぶ実行主体) | 製品の呼び出し元 0 件。無効化が配信されない | U-S1 の射程だが本 PR の射程外 — 受け皿のタスクが要る(本設計 5 節 `:111`・`sync/invalidation.py:174`) |
| ポートの登録表と検査器の接続 | 登録表が空で、全要求が `port_guard.py:496` で 500(本設計 11-1 `:174`) | 全 Port が揃った後に U-S1(本設計 9 節) |
| V12・D4・RG1・復旧世代の物理方式 | P3 の受理結果の `対象の D4` が整数(wire は文字列) | U-R1(本設計 6 節・G-D) |
| 内容検証・投影のポート実装 | 実経路が通らない | U-X1(凍結中)・U-G2(G-E・本設計 7 節) |
| 端末の墓標生成器が V5・V9・V10 を作っていない(2-5) | wire の墓標が B3a になる | 端末側(U-F7/U-F8)か 506 の codec — 担当の確定が要る |
| O5 の理由の画面表示・自動エスケープ / Q8 / 「回復しない」の閾値 | — | 画面側の単位 / 論点 18(本設計 5 節 `:114-115`) |
| O5 の管理者への顕在化(ログ・通知)の実装 | SP は「O4・O5 は管理者へ不変条件違反を顕在化する」(SP:768)。ACK の理由は端末に届くが、管理者向けの経路は U-S1 に無い [推論] | 未割り当て [推論] |
| P3 の決定的な失敗(B10 のまま)・保存済み結果の破損の修復・確定スロットとの食い違い(`sync/prefix_path.py:607`・`:655`) | — | v0.9 の射程外(SP:10)/ 確定ゲートで PO に問う(本設計 11-1 `:171`) |

---

## 9. PO への問い(まとめ)

1. D-1〜D-7 のそれぞれを承認するか
2. D-2: **案 ①(推奨)か案 ②**。案 ① なら TSK-331 に WS:362 の担当の付け替えと V9 の `rejected_d5` の明記を依頼する
3. D-2b: V10 の U-S1 の内部キーを wire(`game_id`)に揃えるか(推奨)
4. D-2c: 種別が不正な原本への墓標を (i) 残余に記録する(推奨)か (ii) data-model へ送るか
5. D-3: P3 の `current_version`・`b9_cause` を必須にするか(推奨 — 既存の試験 2 箇所を直す)
6. D-6a: O4/O5 の別をスロットの属性として永続化するか(推奨)
7. D-7: (a) 作成(推奨 — D-4 と同じステップ)/ (b) 繰り延べ行 / (c) 見送り
8. 端末の墓標生成器(2-5)の担当をどこに置くか(本文書の射程外だが、D-2 の効果に効く)
