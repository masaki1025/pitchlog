---
feature: us1-sync-port-surface
type: proposal
created: 2026-10-16
---

# 具体差分の提示: U-S1・端末の製品変更(TSK-506 への接続)

計画: [plan.md](plan.md) のステップ 3 / 接続契約: [design.md](design.md) / 調査: [research.md](research.md)

**この文書は何か**: PO 裁定(山田正輝 2026-10-16 — plan.md:25)「U-S1 の挙動変更や共有資産の製品変更は包括承認していない。具体差分をまとめて 1 つの文書で提示する」に応える。**ここに書いた差分はまだ実装していない**。PO が差分ごとに承認・不承認を選び、承認されたものだけを計画追補でステップに起こして実装する(1 差分 = 1 ステップ = 1 コミット。各差分の完成条件は 0 節の表)。

**改訂の記録**: 初版(`50025c7d`)への敵対レビューの指摘 9 件(P0 4・P1 4・P2 1)をすべて反映した。主な変更: 既存の欠陥を独立の単位 **D-0** として切り出した / D-2c の「残余に記録」を承認候補から外し、墓標の表現を具体化した / D-2b の推奨を「wire の境界で写す」に変えた / D-3 に 506 側の要件を足した / D-6 の理由コードを必須の永続属性にした / 依存・完成条件・組での承認を表に書いた / D-4 の DB 試験を注入点の方式に変えた / D-7 の選択肢を 2 つにした / SP の行番号を確定版で引き直した。

**読み取り元**: worktree `feature/us1-sync-port-surface` HEAD `50025c7d`。製品コードは develop `e7e8d3a4` と同一(本ブランチの差分は文書だけ)。行番号はこの時点のもの。`本設計` の行番号は HEAD のコミット済みの内容で引く(作業中の未コミットの追記〔2-1 の G-G〕は含めない)。

**略記**: パスの `backend/src/pitchlog/` を省く(例 `sync/apply.py:292`)。端末は `frontend/src/lib/sync/` を省かずに書く。`SP` = `docs/design/sync-protocol.md`(**v0.9 確定済み — 2026-10-17 PO 承認**。行番号は確定版)。`WS` = `docs/features/sync-wire-schema/design.md`(本ブランチ)。`本設計` = `docs/features/us1-sync-port-surface/design.md`。`506/plan` = `feature-tsk506-sync-http-entry` の `docs/features/tsk506-sync-http-entry/plan.md`(`8fb05496` — 読むだけ)。`506/` で始まるパスは同じ worktree のファイル。推論には **[推論]** を付ける。

---

## 0. 承認の単位(PO はこの表で選ぶ)

| ID | 何を変えるか | 承認すると実装されるもの | 完成条件(この単位の 1 コミット) | 506 のゲート(本設計 2-1) | 依存 | PO が選ぶこと |
| --- | --- | --- | --- | --- | --- | --- |
| **D-0** | **既存の欠陥の是正**: ⑤ 不成立(B4)の要求で、D5 の候補表が後の候補で上書きされる | 候補表を D5 でなく **D1** で持つ(`sync/apply.py:330-333`) | 既存の backend 試験が green / 新しい単体・DB 境界試験(B4 + 同じ D5 の同一内容・異内容 + 未使用、入力順 2 通り)が green | なし(G-A の前提) | なし(**単独で承認できる**) | 承認 / 不承認 |
| **D-1** | E-1 の混在バッチの公開口 | 経路を持たない要求型 `SyncEventBatch` と入口 `apply_sync_events`。イベントごとに SP 8-1 の表で P1/P2 を判定し、その経路で指紋を取り、単一の `AckResult` を返す。改訂版の経路は T9 の拒否原本に保存した経路から継ぐ。既存の `apply_sync_request` は残す | ループの括り出しの後も既存の backend 試験が green / 2-5 の試験が green | **G-A** | **D-0** | 承認 / 不承認 |
| **D-2** | V5・V10・V9 の wire → U-S1 の変換 | 変換の置き場所(案 ① か ②)。墓標・改訂版は拒否原本から元の種別を引く | 3-6 の試験が green(D-2c を含めるなら data-model の確定と移行の適用後) | **G-B** | **D-1**(型と関数を使う)/ **TSK-331 の合意**(V9 に `rejected_d5`・案 ① なら WS:362 の担当の付け替え)/ D-2c は **data-model 正本の改訂(確定ゲート)** | **案 ① / 案 ②**、付帯 2 つ(**D-2b** V10 の写し方・**D-2c** 不正種別の原本への墓標の表現) |
| **D-3** | 公開結果型の構造化 | A5 の各件に B3 の分岐(内容起因 B3a/B3b・O4・O5)を持たせる。P3 の拒否に `current_version`(B8)・`b9_cause`(B9)を持たせる。**506 への要求**(境界に依らず A5 の各件を分類する)を接続契約に書く | 4-5 の試験が green / 既存の試験 2 箇所の修正 | **G-C**(+ 506 への要求 — 4-4) | D-4(O5 の分岐を載せるため。D-4 を承認しない場合は O5 抜きで実装できる) | 承認 / 不承認、付帯 1 つ(P3 の追加値を必須にするか) |
| **D-4** | O5 のサーバー側 | 本設計 11-1 の 7 件を専用の例外型で投げ、当該イベントの取引を全取消して B3 + A5「拒否」(理由コード O5)へ写す。7 件の列挙と、`raise` 全件の棚卸しを pytest で突合する | 6-6 の試験が green(注入点による DB 境界試験を含む) | なし(506 の HTTP 写像〔本設計 4 節〕と確認条件〔8 節〕の前提) | SP v0.9(確定済み — 2026-10-17 PO 承認)。**D-6 と組でしか承認できない**(6-7) | **D-6 と組で** 承認 / 不承認 |
| **D-5** | 内容起因の `other` を B3a へ | 本設計 11-2 の B3a 7 件を、内容拒否の例外型で投げ直し、T9 + B3a に載せる | 5-4 の試験が green | なし(同上) | なし(単独で承認できる) | 承認 / 不承認 |
| **D-6** | 端末の O5 | 拒否理由に O5 を足す。O4/O5 の理由コードを**スロットの必須の永続属性**にし、O5 の再開(内容も D5 も変えずに未送信へ)を O4 の再開(QT-07 — 新しい D5)と別の遷移にする。理由コードの無い管理者対応待ちのスロットは再開しない | 7-5 の Vitest が green / 遷移表の行数の検査を 15 行へ更新 | なし(506 の codec が受理する前提) | D-4・SP v0.9(確定済み)。**D-4 と組でしか承認できない** | **D-4 と組で** 承認 / 不承認 |
| **D-7** | 故障系資産(NFR-019(d))の O5 | SP 10-2 の O5 の観点(SP:1700)を母集合に入れる | 母集合 v2 と契約検査が green | なし | D-4(と組の D-6)。凍結資産の版上げ | **作成 / 受け取り先付きの繰り延べ** |

**承認の組**: D-4 と D-6 は片方だけでは効果が無い(D-4 だけでは端末が O5 の ACK を解釈できず B7 と同じ永久再送になる — 7-6 / D-6 だけではサーバーが O5 を返さない)。**組で承認するか、両方を不承認にする**。

**推奨の実装順**(承認されたものだけ): **D-0 → D-1 → D-2**(この 3 つはこの順で固定)。それ以外は独立で、D-5 → D-4(+ D-7 を同じステップで)→ D-6 → D-3 の順に、D-0〜D-2 の前後どちらに挟んでもよい [推論 — 小さく独立したものから。D-6 はサーバー側の O5 の後]。

**この文書で決めないもの**: 9 節(担当が別)。

---

## 1. D-0 候補表を D1 で持つ(既存の欠陥の是正)

### 1-1. 現状(欠陥)

- `apply_sync_request` は、④ で分類した D5 の候補を **D5 をキーにした辞書**に入れる(`sync/apply.py:330-333` — `{event.d5: candidate for event, candidate in zip(request.events, preflight.candidates, strict=True)}`)。S-1 は同じ要求の中の D5 の重複を拒否しない(WS の 3-2「`d5` の重複は S-1 で見ない」・`backend/tests/test_sync_apply_model_ports.py` の `test_duplicate_d5_is_left_for_processing`)。**同じ D5 のイベントが 2 件あると、入力順で後の候補が前の候補を上書きする**
- 候補をイベントごとに読むのは ⑤ 不成立(B4)の分岐だけ(`sync/apply.py:344` で B4 → `:356-379` で候補の種類を読む)。記録権が成り立つ場合は各イベントの取引の中で D5 を分類し直すので、この表を使わない(`sync/prefix_path.py:581`)
- **起きること**(要求に「保存済みの D5 = X と同じ内容」E1・「X と異なる内容」E2・未使用 D5 の E3 があり、記録権が成り立たない場合):
  - 入力順 `[E1, E2, E3]`: X の候補が「異内容」で上書きされ、**E1 が再掲されずに「未処理」**になる(`:357-360`)。正本は既存同一内容を保存済み結果として再掲する(DI2 — SP:1296)
  - 入力順 `[E2, E1, E3]`: X の候補が「保存済み」で上書きされ、**E2 が再掲の経路へ入り**(`:369-379`)、取引の中で異内容と分類し直されて B3b の「拒否」になる。正本は B4 の要求の既存異内容を「未処理」とする(SP:1032・SP:1689 の D1 混在バッチの行)
  - どちらでも結果が**入力順に依存**する
- 現行の公開口 `apply_sync_request` の欠陥で、D-1 の有無に依らない

### 1-2. 変更

- `sync/apply.py:330-333` の辞書のキーを `event.d1` にする(D1 付き経路では D1 は要求内で一意 — `sync/model.py:213-215`。`:350` で `event.d1` が None でないことを表明済み)。`:357`・`:361` の参照を `candidates[event.d1]` にする
- 公開口・型・署名は変えない
- [推論] 同じ形の D5 キーの辞書として `registrations`・`targets`(`:354-355`)があるが、これは呼び出し側が渡す入力で、本差分では変えない(同じ D5 の 2 件に同じ登録値が付くのは、同じ D5 = 同じ操作という前提に沿う)

### 1-3. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体(偽ポート) | B4 の要求で `[E1, E2, E3]` と `[E2, E1, E3]` の両方: E1 = 再掲(保存済み結果どおりの「重複」など)・E2 = 「未処理」・E3 = 「退避」。**2 つの入力順で A5 が同じ** |
| DB 境界 | 同じ 3 件を実 DB で(X を先に受理しておき、旧 D4 で送って B4 にする — 既存の `backend/tests/db/test_sync_apply_apply_boundary.py` の B4 の試験の組み方)。台帳・T8 の原本・T9 の原本の件数が、E3 の退避 1 件だけ増える。再送で同じ A5 |
| 負例 | 記録権が成り立つ要求で同じ D5 の 2 件 → 従来どおり(候補表を使わない経路なので結果が変わらないこと) |

### 1-4. この差分が無いと 506 の何が止まるか

506 の故障系(506/plan:76 の「同じ D5 の再送と ACK 消失、異内容同 D5」)と、本設計 8 節の確認条件「ACK 消失後の再送で保存済み結果を再掲」を、記録権の引き継ぎ後の要求(B4)で確かめると、入力順によって結果が変わる。D-1 は同じループを使うので、この欠陥を引き継ぐ。

---

## 2. D-1 E-1 の混在バッチの公開口(G-A)

### 2-1. 現状(問題)

- 要求は経路を 1 つしか持たない(`sync/model.py:158` `path: ApplicationPath`)。経路は D5 の指紋に入る(`sync/idempotency.py:277` `"path": path`)
- 適用核の内部で要求の経路を参照している箇所: `sync/apply.py:92`(④ の指紋)・`:153`・`:157`(経路の分岐)・`:179`・`:189`(T8/T9 へ渡す経路)・`:233`(⑤ 不成立の退避)・`:257`・`:268`(⑤ 不成立の再掲)・`:307`(P3 の分岐)・`:323`(P4 の要求で記録権が成立した場合の例外 `:327`)。あわせて `sync/idempotency.py:167`(`classify_request_d5` が `request.path` で D5 を分類 — 経路は B3b と B13 の分岐にだけ効く `:136`)
- 正本の経路は種別で決まる(SP:1301-1316 — 毎球入力・選手交代・タイブレーク開始・試合終了宣言・状態補正 = P2 / undo・選手のその場登録・墓標 = P1 / 改訂版 = 元イベントの参加区分を継承 SP:1313)。wire は「経路はクライアントが選ばず、サーバーが判定する」(WS:163)。506 の承認済み計画はステップ 4 の着手前に「P1/P2 混在バッチを単一 ACK・D1 順・部分成功で処理する型/関数」を求め、HTTP 側での分割を禁じる(506/plan:49・:64)

### 2-2. 署名(新設)

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
        """E-1 本文の S-1 外形を照合する(D-1 では照合だけ。値の変換は D-2 が足す)。"""

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
- **D-1 の入力は U-S1 の表現**(V5 は種別のリテラル、V9 は `{"tombstone"/"revision": true, "rejected_d5": ...}`)。wire の表現(番号・`"8"`/`"9"`)からの変換は D-2 が `SyncEventBatch.from_payload` と `apply_sync_events` の前処理に足す。**D-1 は D-2 に依存しない**(D-2 が D-1 の型と関数を使う)
- **既存の `SyncRequest.from_payload` と `apply_sync_request` との関係**: 両方とも残す。E-2(P3)と、経路を明示する既存の試験・故障系資産(例: `tests/fixtures/sync-protocol-failures/d1-mixed-batch_v1.json` は毎球入力を `applicationPath: "P1"` で送る)が使う。S-1 の D1 付き経路の照合(`sync/model.py:195-217`・本文の取り出し `:272-310`)は、`SyncRequest` と `SyncEventBatch` が**同じ内部関数を呼ぶ形に括り出す**(S-1 の規則を 2 か所に持たない)
- `apply_sync_events` は **P4 を要求の経路として使わない**。⑤ の不成立は、従来どおり U-S1 の内部で T8 へ回す(`sync/apply.py:356-379`)。退避の指紋はイベントの経路(P1/P2)で取る。`:322-327` の検査(P4 の要求で記録権が成立)は新しい入口では到達しない(research G-1b への回答)

### 2-3. 挙動

1. **経路の判定**(`route_for_event`): V9 が墓標 → **P1** / V9 が改訂版 → **拒否原本の経路**(下記 2)/ それ以外は V5 が `_P2_LOGICAL_KINDS`(`sync/prefix_path.py:87` = `db/sync_protocol/event_kinds.py:159-162` の論理位置を持つ 4 種別 + 状態補正)なら **P2**、それ以外(undo・その場登録・**V5 が欠落・未知の値**)は **P1**。表は既存の定数から導き、新しい表を作らない(NFR-018)。V5 が不正なイベントは P1 で ⑦ に入り、`_event_kind` で B3a になる(`sync/prefix_path.py:223-230`)— 経路の判定は例外を投げない
2. **改訂版の経路**: 「元イベントの参加区分を継承」(SP:1313)。**T9 の拒否原本に経路を保存し**(`sync/rejection.py:98-102` の `_original` に `"path"` を足す — `operation_fingerprint` を足している既存の前例 `:101` と同じ形。`_commit_result` は経路を引数で持っている `:111`)、改訂版はそれを継ぐ。原本の `V5` だけからは、原本が墓標の改訂版だった場合などを区別できない [推論]。`"path"` の無い旧原本は 1 の規則で原本の V5・V9 から導く。原本は内容の更新を禁止されている(`authz/runtime_contract.py:127` の `prevent_rejected_event_originals_content_update`・`sync/tokens.py:211`・`:219` は読取と挿入だけ)ので、**同じ改訂版は常に同じ経路・同じ指紋になる**
3. 原本の読取は ④ の前処理の取引(`sync/apply.py:87` の `tenant_transaction_scope`)で行い、指紋(`:90-95`)より先に経路を確定する(読取は `rejected_d5` で引く — `RejectedOriginalReadToken` `sync/tokens.py:211`)
4. **内部の作り替え**: `_preflight_d1`(`:80-137`)・`_run_d1_event`(`:140-201`)・`_escrow_without_right`(`:219-238`)・`_replay_existing`(`:241-284`)の引数を `request` から「`game_id`・`d4`・`v12` と、イベントごとの `path`」へ変え、`apply_sync_request` の `:313-434` のループ本体を共通関数へ括り出す。`apply_sync_request` は全イベントに `request.path` を渡す(**挙動は不変** — 既存の試験が回帰の検査になる)。`apply_sync_events` は `route_for_event` の結果を渡す。経路も候補(D-0)と同じく **D1 で引く**
5. D5 の事前分類は、イベントごとの経路で `classify_d5`(`sync/idempotency.py:139-145`)を呼ぶ(`classify_request_d5` の `request.path` は使わない。E-1 に P3 は来ないので B3b/B13 の分岐は変わらない)
6. 戻り: 単一の `AckResult`。D1 昇順・部分成功・停止境界は 1 つ(DI5 — SP:1299)。⑥ の欠落・B3・B4 の扱いは `apply_sync_request` と同一(同じループ)

### 2-4. 既存の試験・資産への影響

- 既存の試験は `apply_sync_request` を使い続けるので変えない [推論 — ループの括り出しは挙動を変えない前提。括り出しのコミットで既存の `backend/tests/test_sync_apply_apply.py`・`backend/tests/db/test_sync_apply_*` が green であることを完成条件にする]
- T9 の原本に `"path"` が増える。原本の照合(`sync/prefix_path.py:266-298`)は `d5`・`game_id`・`d4`・`d1`・`event_kind`・`d2`・指紋だけを見るので影響しない
- 故障系資産(`tests/fixtures/sync-protocol-failures/*`)は版を上げない(旧入口で走る)。新しい入口の故障系は DB 試験で足す

### 2-5. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | `route_for_event` の全行(#1〜#7・墓標・改訂版〔原本 P1/P2・`"path"` 無しの旧原本〕・V5 欠落/未知/非文字列 → P1)。同じイベントで何度呼んでも同じ値(永続状態を渡せない署名で担保)/ `SyncEventBatch.from_payload` の S-1 が `SyncRequest.from_payload` と同じ違反を同じ例外で拒否する(既存の S-1 の表 `backend/tests/test_sync_apply_model_ports.py:210-213` を両方に流す)/ **負例**: 本文に経路のキーを足すと S-1(未知キー — `sync/model.py:272-274`) |
| 単体(偽ポート) | 混在バッチ `[毎球入力, undo, その場登録, 毎球入力]` で各イベントが P2/P1 の局所経路へ渡り、指紋の経路がイベントごとに違うこと |
| DB 境界 | 混在バッチの単一 ACK・D1 昇順・部分成功(途中の B3a で前方は受理・後方は未処理)/ 同じ要求の再送で全件「重複」(DI2 — 指紋が一致)/ ⑤ 不成立の混在バッチで各イベントがイベントの経路の指紋で退避され、再送で再掲される(D-0 の同じ D5 の組を含める)/ 改訂版が原本の経路(P2 なら T5 の採番を通る)で適用される / D1 欠落で B2 |
| 故障系 | 混在バッチの途中のイベントの取引内で注入(既存の名前付き注入点 — `sync/crash_points.py:14-31`)→ 再送で前方は保存済み結果、当該は未使用として再適用 |

### 2-6. この差分が無いと 506 の何が止まるか

506 のステップ 4(backend の E-1 router)の**着手条件**が満たされない(506/plan:49 — 「現行 `SyncRequest.path` の単一値を HTTP が独自に分割して埋めない」)。DoD の「E-1 の単一/混在バッチの P1/P2 分類 … が U-S1 担当と受理済み」(506/plan:64)も閉じない。506 が単一経路の要求で送ると、毎球入力を P1 で送れば T5(D2 採番)を通らずに保存され、undo・その場登録を P2 で送れば B3a で T9 に永久に記録される(`sync/prefix_path.py:614-617`・`:636-638` — research G-1)。

---

## 3. D-2 V5・V10・V9 の wire → U-S1 の変換(G-B)

### 3-1. 現状(問題)

| 値 | wire | U-S1 が受けるもの | 変換が無いと |
| --- | --- | --- | --- |
| **V5** | 正本 5-5 の番号の文字列(E-1 `"1"`〜`"9"`・E-2 `"10"`〜`"12"` — WS:201・WS:237) | 種別のリテラル `play_input` 等(`sync/prefix_path.py:223-230`・`sync/change_path.py:173-176`) | E-1 は正規の毎球入力が B3a で T9 に永久に記録される / E-2 は B14 |
| **V5 の墓標・改訂版** | `"8"`・`"9"`(元の種別を運ばない) | 元の種別のリテラル + V9 の `tombstone`/`revision`(`sync/prefix_path.py:197-220`・`:284-287`) | 同上(B3a)。元の種別は拒否原本(T9)からしか分からない |
| **V9** | `replacement_state`。中身を WS は決めていない(WS:205) | `{"tombstone": true, "rejected_d5": "<D5>"}` または `{"revision": true, "rejected_d5": ...}`(`sync/prefix_path.py:201-204`) | 形が合わず B3a(`:205`) |
| **V10** | `target_reference` = `{"game_id", "d4", "d1"}`(WS:206) | `{"game", "d4", "d1"}`(`sync/prefix_path.py:237`・`:366`・`sync/change_path.py:78`) | undo は B3a(`:374`)、墓標・改訂版は W2 違反で B3a(`:238`)、P3 は B14(`change_path.py:184`) |

- 変換後の値が指紋に入る(`sync/idempotency.py:274-289` が `event_source` 経由で V5〜V11 を全部含める `:77-94`)。**変換は決定的で、版を固定する必要がある**
- 変換表の材料は既にある: `db/sync_protocol/event_kinds.py:85-128` の `OPERATION_EVENT_PARTICIPATIONS`(番号 → リテラル。#8・#9 はリテラルなし)。端末側の番号は `frontend/src/lib/sync/eventKinds.ts:29-114` の `id`(同じ SP 5-5 の番号)
- `from_payload` は DB に触れない classmethod である(`sync/model.py:230-233`)。**墓標・改訂版の原本の読取は、どちらの案でも DB の取引の中で行う**

### 3-2. 2 案

| | **案 ① U-S1 が写す** | **案 ② 506 が写し、表は U-S1 が公開する** |
| --- | --- | --- |
| 純粋な変換(V5 の `"1"`〜`"7"`・`"10"`〜`"12"`、V9 の形、V10 のキー) | `SyncEventBatch.from_payload`(D-1)と `SyncRequest.from_payload` の P3 分岐(`sync/model.py:235-271`)の中で写す | 506 の `sync/http_wire.py`(506/plan:43 の候補パス)が U-S1 の公開関数(例 `pitchlog.sync.wire_values.event_kind_literal(value)`)を呼んで写し、変換済みの値で `SyncEventBatch` を作る |
| 墓標・改訂版の元の種別(`"8"`/`"9"`) | `apply_sync_events` の前処理の取引で `rejected_d5` の原本を読み、V5 を原本の `event_kind` に、V9 を U-S1 の形に置き換えてから指紋を取る(D-1 の改訂版の経路の読取と同じ読取を共用) | 506 は原本を読めない(U-S1 の内部の token — 本設計 1-1 `:27`)ので、**U-S1 が別の公開口**(例 `resolve_replacement_events(context, game_id, events) -> tuple[SyncEvent, ...]` — 自分で読取の取引を開く)を出し、506 はそれを呼んでから適用を呼ぶ。D-1 の経路の判定は適用の前処理で原本をもう一度読む |
| 変換表の持ち主 | U-S1(`sync/` に 1 か所) | U-S1(同じ 1 か所。506 は呼ぶだけ) |

**代償の比較**

| 観点 | 案 ① | 案 ② |
| --- | --- | --- |
| **NFR-018(コピー実装)** | 表と適用が同じ単位にあり、コピーは生じない | 表は 1 か所だが、**呼び出しの順序**(純粋な変換 → 原本の解決 → 適用)を 506 が組む。506 側に「番号のまま通す」「一部だけ自前で写す」余地が残る。表を自前で持てば P0(AGENTS.md の Code Review Rules)[推論] |
| **指紋の安定性** | 変換と指紋が同じ関数の中で続けて起きる。入口が変換を飛ばす経路が無い | 506 が変換を呼び忘れる・順序を誤ると、**番号のままの V5 が B3a として T9 に記録され、その D5 は永久に消費される**(`sync/prefix_path.py:230` → `sync/rejection.py:207-209`)。誤りが不可逆 |
| **所有** | **WS:362 は「U-S1 のサービス層の型との対応は … 入口 PR の義務」とする**(N-18)。案 ① はこの担当を U-S1 へ付け替えるので、**TSK-331 の合意と WS の追記が要る**。U-S1 が wire の語彙(番号)を知ることになる | WS の担当分けのまま。U-S1 は wire の語彙を知らない(公開する表は「番号 → リテラル」の 1 枚) |
| **墓標・改訂版の変換の成立** | 成立する(前処理の取引で読む。原本は不変 — 2-3 の 2) | 成立するが、**取引が 1 つ増える**(読取 → 適用前処理でもう一度読取)。スコープごとの接続生成の費用(research G-13)が 1 要求あたり 1 回増える。原本は不変なので、2 回の読取の間に値が変わる心配は無い |
| 506 の実装量 | 本文を `SyncEventBatch.from_payload` に渡すだけ | 純粋な変換の呼び出し・原本の解決の呼び出し・その順序の試験 |

**推奨: 案 ①**。根拠: (1) 案 ② の主な代償(変換の呼び忘れで D5 が T9 に不可逆に消費される)は、HTTP の試験でしか検出できず、起きたら戻せない。案 ① は入口の型がそれを不可能にする。(2) 墓標・改訂版は DB の読取が必須で、どちらの案でも U-S1 に変換の口ができる。案 ② は変換が 2 単位に分かれるだけで、U-S1 の責務は減らない。(3) 案 ① の代償(WS:362 の担当の付け替え)は文書の合意で済み、製品の安全性に効かない。**ただし案 ① は TSK-331 の合意が前提**(合意が得られなければ案 ②)。

### 3-3. 共通の規則(どちらの案でも)

- **S-2 の値を例外にしない**: 未知の番号・非文字列・欠落はそのまま通し、処理段階が B3a/B14 にする(WS:201 は V5 を S-2 とする — `backend/tests/test_sync_apply_model_ports.py:234-251` は `event_kind: {"invalid": true}` を保持することを検査しており、この試験は green のまま)
- **V9 の wire 形**: `{"rejected_d5": "<D5>"}`(墓標か改訂版かは V5 の `"8"`/`"9"` で表す)を **WS に明記する — TSK-331 の合意が要る**(本設計 2-1 G-B と同じ)。`rejected_d5` が無い・原本が無い場合は変換せずに通し、⑦ で B3a になる(`sync/prefix_path.py:205`・`:261`)[推論 — 原本の無い `rejected_d5` を送るのは端末の誤りに限られる。後からその D5 が拒否されると、同じ D5 の再送の指紋が変わり B3b になりうる。残余として記録する]
- 変換は E-2(P3)にも掛ける(V5 `"10"`〜`"12"`・V10 のキー)。P3 の受理結果の `target_reference`(`試合`・`対象の D4`・`対象の D1` — `sync/change_path.py:216-220`・`sync/model.py:389`)を wire の `game_id`・`d4`・`d1`(WS:322)へ写すのは**出力側の codec**(506)で、本差分に含めない。`対象の D4` が整数で返る件は U-R1 の決定待ち(本設計 6 節・research G-4)

### 3-4. 付帯の選択

#### D-2b V10 の写し方

**推奨: U-S1 の内部キーは `game` のまま、wire の境界で `game_id` → `game` と写す。写すときは厳格に照合する**:

- 値が JSON object で、キーの集合が**ちょうど** `{"game_id", "d4", "d1"}` のときだけ `{"game", "d4", "d1"}` に写す
- それ以外の object(**wire に無い `game` キーを含むもの**を含む)は、U-S1 が必ず拒否する形に包んで渡す(例 `{"wire_invalid": <元の値>}` — 決定的なので指紋は安定する。U-S1 は `set(reference) != {"game", "d4", "d1"}` で拒否する — `sync/prefix_path.py:237`・`:366`・`sync/change_path.py:78`)。素通しにすると、端末が wire に無い `{"game", ...}` を送ったときに**写されずに U-S1 で受理される**(`sync/model.py:279-309` は V10 の中身を見ない — S-2)
- object でない値(欠落・null・配列など)はそのまま通す(S-2 — 処理段階が拒否する)
- 写しは案 ① なら U-S1 の `from_payload`、案 ② なら U-S1 が公開する変換関数の中に置く(どちらでも 1 か所)

**非推奨の選択肢: U-S1 の内部キーを `game_id` に一律に改名する**(`sync/prefix_path.py:237`・`:239`・`:366`・`:371`・`sync/change_path.py:78`・`:80`)。V10 の写しは不要になるが、代償が大きい:
- **指紋**: V10 は指紋に入る(`sync/idempotency.py:77-94` の `event_source` → `:274-289`)。改名前に保存した D5 の指紋と、改名後の同じイベントの指紋が変わり、**改名をまたいだ再送が B3b(異内容)になる**。保存済みの台帳と T9 原本の移行が要る
- **既存の公開口**: `sync/prefix_path.py:237`(墓標・改訂の V10)と `sync/change_path.py:78`(P3 の V10)の入力の形が変わる
- **試験・資産**: V10 を `game` で組む既存の試験(`backend/tests/test_sync_apply_prefix_path.py:120`・`:171`・`:187` ほか、`backend/tests/test_sync_apply_change.py`・`backend/tests/test_sync_apply_ordering.py`・`backend/tests/db/test_sync_apply_change_boundary.py`・`backend/tests/db/test_sync_apply_prefix_path_boundary.py`)と、凍結資産を走らせる実行器(`backend/tests/db/test_sync_apply_failure_runner.py:336`・`:367`)の書き換え。凍結資産の JSON 自体には V10 の `game` は無い(資産の `"game"` は無効化意図の範囲の値 — 7 ファイルを走査して確認)

#### D-2c 種別が不正な原本への墓標

**問題**: 種別が不正(V5 の欠落・未知の値 — WS:100 の S-2)で拒否された原本は、改訂版では再開できない(改訂版は元の種別の継承が強制される — `sync/prefix_path.py:284-287`・SP:1313)。正本は内容拒否から**墓標で D1 を消費して再開する**ことを定める(SP:869 の (b) 破棄)ので、墓標は適用できなければならない。しかし**墓標の行も `operation_events.event_kind` に有効なリテラルが要り**(`db/sync_protocol/models.py:140-143` の `ck_operation_events_event_kind` = `db/sync_protocol/event_kinds.py:420-422` の `event_kind IN (EVENT_KIND_LITERALS)`)、U-S1 の変更だけでは保存できない。

**提案する表現**: **墓標の行の `event_kind` は、元の種別が有効ならその種別、無効なら新設の値 `tombstone_unknown_kind`(仮称)とする**。

| 層 | 変更点 |
| --- | --- |
| データモデル(物理) | `db/sync_protocol/event_kinds.py` に定数 `TOMBSTONE_UNKNOWN_KIND_LITERAL`(仮称)を新設する。**`EVENT_KIND_LITERALS`(`:139-144`)には入れない** — この集合は端末が送る V5 の有効値の判定にも使う(`sync/prefix_path.py:228`)ので、入れると端末が新設の値を V5 として送れてしまう |
| CHECK | `EVENT_KIND_CHECK_EXPRESSION`(`:420-422`)を `event_kind IN (<EVENT_KIND_LITERALS>, '<新設の値>') AND (event_kind <> '<新設の値>' OR is_tombstone)` にする(新設の値は墓標の行にしか現れない)。C12 の行述語は通常の種別を `event_kind = '<リテラル>' AND NOT is_tombstone` とし(`:203-215`)、墓標は `is_tombstone` で表す(`:205-206`)ので、C12 の各 CHECK(`C12_CHECK_EXPRESSIONS`・`C12_TOMBSTONE_CHECK_EXPRESSION` `:409-412`)と `TOMBSTONE_CHECK_EXPRESSION`(`:428-434`)・`STATE_DIFF_BY_EVENT_KIND_CHECK_EXPRESSION`(`:423-427`)は変えずに済む [推論 — 各式を読んだ範囲。実装時に生成された CHECK の文字列で確かめる] |
| 移行 | `ck_operation_events_event_kind` を張り直す alembic の revision(前例: `backend/migrations/versions/0022_operation_event_state_diff.py:141`・`:170` がこの CHECK を扱っている) |
| U-S1 | 墓標の変換(D-2)で、原本の `event_kind` が `EVENT_KIND_LITERALS` に入っていれば V5 = その値、入っていなければ V5 = 新設の値にする。`_require_rejected_original` の種別の一致(`sync/prefix_path.py:284-287`)を、墓標では「原本の種別が有効なら一致・無効なら V5 = 新設の値」に変える。`_event_kind`(`:223-230`)は、新設の値を**墓標のときだけ**受ける。墓標で `_event_kind` を通る箇所(⑦ の `:618`・`_validate_v11` の C12 の引き当て `:341-343`・`_projection_event` の選手参照の位置 `:515`・行の作成 `:392`)を、墓標は参加区分 #8 で引く形に直す |
| 投影 | 投影ポートが新設の値の墓標を受ける(墓標はプレイ列に投影されない — SP 5-5 #8)。投影ポートの所有は U-X1(凍結中)なので、受け取りの確認が要る [推論] |

**ゲート**: `operation_events` の種別の値域と CHECK はデータモデルの正本(`docs/design/data-model.md` 5-3 — 種別の行 `:774`・置換・墓標の状態 `:776`・参加区分の物理表現 `:868-877`)に属する。**data-model 正本の改訂(新しい種別の値の追加 — 確定ゲート〔finalize-doc〕)が要る**。D-2c は、D-2 を承認しても data-model の改訂が確定するまで実装できない。

代替(非推奨): 墓標の行に限り `event_kind` を NULL にする。`event_kind` の NOT NULL(`db/sync_protocol/models.py:263`)を外すことになり、種別ごとの CHECK と C12 の述語の前提(種別が必ずある)が崩れるので、影響が大きい [推論]。

### 3-5. 依存(本差分の外)

- **端末の墓標生成器が V5・V9・V10 を作っていない**: `frontend/src/lib/sync/k5Tombstone.ts:179-189` は墓標のイベントを空の `fields` で作る(V5 `"8"`・V9 の `rejected_d5`・V10 が無い)。506 の codec(506/`frontend/src/lib/sync/wireCodec.ts`)にも墓標・改訂版の扱いは無い(`grep` で 0 件)。D-2 を実装しても、端末が送る墓標は U-S1 で B3a になる。**直す担当は端末側(U-F7/U-F8 か 506 の codec)で、本文書では提示しない**(9 節)

### 3-6. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | 番号 → リテラルの全行(#1〜#7・#10〜#12)が `OPERATION_EVENT_PARTICIPATIONS` と一致 / 未知・非文字列・欠落を変えずに通す(負例)/ V9 の写し / **V10 の厳格な照合**: `{game_id, d4, d1}` は写す・`{game, d4, d1}` は包んで渡し U-S1 が拒否する(負例)・キーの過不足も包む(負例)・object でない値は素通し / 同じ入力で何度呼んでも同じ出力 |
| 一致性 | 端末の `EVENT_KIND_RULES` の `id` と backend の番号 → リテラルの表が同じ集合(Vitest か pytest のどちらか 1 か所 — 契約試験として `contracts/` の既存の型に載せるかは実装時に決める [推論]) |
| DB 境界 | wire 形の `"9"` + `rejected_d5` で、原本の種別・経路を継承して適用 / `"8"` で墓標として適用 / 原本が無い `rejected_d5` → B3a / 同じ改訂版の再送で同じ指紋(DI2)/ E-2 の `"10"` が P3 で受理される / **D-2c**: 種別が不正な原本への墓標が新設の値で保存され D3 が進む・新設の値を V5 に持つ墓標でないイベントは B3a(負例)・新設の値で墓標でない行の挿入を DB の CHECK が拒否する(負例) |
| 故障系 | 原本の読取の後・適用の前に注入 → 再送で同じ変換・同じ結果 |

### 3-7. この差分が無いと 506 の何が止まるか

506 が wire の値をそのまま U-S1 へ渡すと、**正規の毎球入力が全件 B3a で T9 に永久に記録される**(`sync/prefix_path.py:230`)。506 の DoD「1 球を HTTP 経由で実 DB 原本・投影へ保存し、再読込」(506/plan:68)が成立しない。506 が独自に写すと NFR-018 のコピー実装(P0)になる。

---

## 4. D-3 公開結果型の構造化(G-C)

### 4-1. 現状(問題)

- `A5Result` は `(d4, d1, d5, state, reason: str | None)` だけで、B3 の分岐を持たない(`sync/model.py:320-328`)。分岐は要求に 1 つの `AckResult.b3_branch`(`:338` — 型 `B3Branch = Literal["B3a", "B3b", "O4"]` `:51`)で、停止したイベントの分だけ
- wire は「拒否」の**各件**に `rejection: {kind, branch, reason}` を求める(WS:308 — `kind` は `"内容起因"`・`"O4"`・`"O5"`、`branch` は内容起因のときだけ `"B3a"`/`"B3b"`)。停止イベント以外の「拒否」は、**B4 の要求で保存済み B3a を再掲したもの**(`sync/apply.py:344` で境界が B4 → `:369-379` の再掲 → `sync/rejection.py:85-95`)。このとき境界は B4 で、A5 には「拒否」が載る
- P3 の拒否は `RejectedChangeResult(boundary, d5, reason: str | None)` だけ(`sync/model.py:409-420`)。wire は B8 に `current_version`、B9 に `b9_cause`(`"記録権不保持"`/`"旧復旧世代"`)を求める(WS:341-342)。U-S1 は文言で区別している(`sync/change_path.py:148` 旧復旧世代・`:171` 記録権不保持・`:212` `f"現在版: {current_version}"`)— 文言の解析で写すと壊れやすい(research G-7)

### 4-2. 署名

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
    current_version: int | None = None      # 追加 — B8 のときだけ
    b9_cause: Literal["記録権不保持", "旧復旧世代"] | None = None   # 追加 — B9 のときだけ
```

`apply_sync_request`・`apply_sync_events` の署名は変えない(戻り値の型の中身が増えるだけ)。

### 4-3. 挙動

- `sync/apply.py:402-406`(A5 の 1 件を作る箇所)で、局所結果から `A5Rejection` を作る: `RejectionResult.boundary` の `"B3a"`/`"B3b"`(`sync/rejection.py:82`・`:152`)→ 内容起因 / `P1Result` の B3a・B3b(再掲 `sync/prefix_path.py:865-871`・衝突 `:432`)→ 内容起因 / O4・O5(D-4 で `P1Result` に足す区分 — 6-2)→ `kind` = `"O4"`/`"O5"`。B3b の理由は既存の文言(`sync/apply.py:403-405`)。**境界が B4 の要求でも、A5 が「拒否」の件には必ず `rejection` を付ける**
- `AckResult.b3_branch`・`reason`(`:338-339`)は残す(既存の試験・故障系資産が読む — `backend/tests/db/test_sync_apply_failure_runner.py:860` ほか)
- P3: `sync/change_path.py:147-149` → `b9_cause="旧復旧世代"` / `:170-172` → `b9_cause="記録権不保持"` / `:211-213` → `current_version=current_version`。文言(`reason`)は変えない
- `RejectedChangeResult.__post_init__`(`sync/model.py:417-420`)に「B8 ⇔ `current_version`・B9 ⇔ `b9_cause`」の検査を足す。**既存の試験 2 箇所が `RejectedChangeResult("B9", d5)` を作っている**(`backend/tests/test_sync_apply_model_ports.py:125`・`backend/tests/test_sync_apply_gate.py:321`)ので同じコミットで直す。必須にしない(None を許す)なら試験は変えずに済むが、506 が値の存在に頼れなくなる — **推奨は必須** [推論]

### 4-4. 506 への要求(506 の所有 — 本文書は要求として書くだけ)

- **要件**: **ACK アダプタは、境界の値に依らず、A5 の各件の拒否理由を分類する**。現行の 506 のアダプタは、境界が B3 のときだけ拒否を分類する(506/`frontend/src/lib/sync/ackAdapter.ts:122` — `if (boundaryResultId !== B3_BOUNDARY_RESULT_ID || rejections.length === 0) return {}`。develop の同じファイルも同じ条件 — `frontend/src/lib/sync/ackAdapter.ts:119`)。B4 の応答で再掲された B3a の「拒否」は分類されず、キュー遷移は分類が無ければ遷移しない(`frontend/src/lib/sync/queueTransition.ts:527-529`)ので、**そのスロットは未送信のまま再送され続け、要操作(改訂待ち / 墓標待ち)へ移れない**。正本はキュー遷移の根拠を A5 だけに置く(SP:1053)
- **受入条件**: B4 の要求に「保存済み B3a の D5」と「未使用 D5」が混在する HTTP 試験で、前者が要操作へ、後者が退避済みへ移ること(D-0 の同じ D5 の組を含めると、なおよい)
- 本設計 2-1 に 506 のゲートとして足す(G-G — 本設計への追記は別のコミット)

### 4-5. 既存の試験・資産への影響と試験の追加範囲

既存の試験は A5 をフィールドの射影で比べている(例 `backend/tests/test_sync_apply_apply.py:69`・`backend/tests/db/test_sync_apply_apply_boundary.py:177`)。`A5Result(...)` を「拒否」で直接作って比べる試験は 0 件(`grep`)。追加フィールドで壊れるのは上の 2 箇所だけの見込み [推論]。故障系資産の観測フィールド(`b3Branch` 等)は変えない。

| 種別 | 内容 |
| --- | --- |
| 単体 | `A5Rejection` の不変条件(**負例**: 内容起因で `branch` 無し・O4/O5 で `branch` あり・「拒否」以外で `rejection` あり → 例外)/ `RejectedChangeResult` の B8・B9 の排他(負例: B8 で `b9_cause`・B14 で `current_version`) |
| 単体(偽ポート) | B3a 停止・B3b 停止・O4・O5・**B4 の要求での保存済み B3a の再掲**の各件で `rejection` が正しい |
| DB 境界 | 既存の P3 境界試験(`backend/tests/db/test_sync_apply_change_boundary.py`)に B8 の `current_version`・B9 の 2 原因を足す / B4 の要求で保存済み B3a と未使用イベントが混在するとき、前者の A5 に `rejection`(内容起因・B3a)が付く |

### 4-6. この差分が無いと 506 の何が止まるか

506 のステップ 4 の結果写像(N-18 の U-S1 型 ↔ wire キー対応 — 506/plan:58)が、`event_results[].rejection` を停止イベント以外で推論し、`current_version`・`b9_cause` を文言の解析で埋めることになる。文言を変えると黙って壊れる。4-4 の要求が満たされないと、B4 の応答に載った再掲の「拒否」で端末のキューが止まる。

---

## 5. D-5 内容起因の `other` を B3a へ

### 5-1. 対象(本設計 11-2 `:200` の B3a 7 件)

| 箇所 | 現行 | 理由(本設計 11-4) |
| --- | --- | --- |
| `sync/prefix_path.py:444`・`:448`・`:450` | `P1PreconditionError("選手参照は UUID 文字列が必要")` ほか(`_resolve_player_reference`) | V7 の選手参照の内容で決まる |
| `sync/prefix_path.py:470` | `P1PreconditionError("一時選手 ID の確定写像がない")` | 端末が送った参照で決まる |
| `sync/prefix_path.py:496` | `P1PreconditionError("V5 で定義されない選手参照位置")`(`_resolve_payload`) | V7 の形で決まる |
| `sync/prefix_path.py:680` | `P1PreconditionError("一時 ID は別の確定写像に使用済み")` | その場登録の内容で決まる |
| `sync/ordering.py:34` | `P1PreconditionError("P2 の V6 は非負の bigint が必要")` | 端末が送った V6 で決まる |

いずれも ⑦ の `try`(`sync/prefix_path.py:612-639`)の外で投げるので、`P1ContentRejection` へ変換されず、`sync/apply.py:198-199` から再送出 → 500 → B7(永久再送)になっている。

### 5-2. 変更

7 箇所の例外を **`P1ContentRejection(<同じ文言>)`** に変える(`sync/prefix_path.py:841-842` — `P1PreconditionError` の部分型)。`sync/ordering.py:16` の import に `P1ContentRejection` を足す。公開口・型の追加は無い。

### 5-3. 挙動

- 取引は例外で全取消(`sync/prefix_path.py:788` の `tenant_transaction_scope` を例外で抜ける)→ `_run_d1_event` の `:183` が `isinstance(error, P1ContentRejection)` で拾い、新しい取引で T9 に原本・D5・理由を保存して B3a(`sync/rejection.py:207-209`)。端末は 2 択(改訂・墓標)で再開できる
- 7 箇所はすべて D5 の再照合(`sync/prefix_path.py:581-584`)より後なので、保存済み結果の再掲では起きない(DI2 を壊さない)
- **既存の試験は green のまま**: `pytest.raises(P1PreconditionError, match=...)` は部分型でも通る(`backend/tests/test_sync_apply_ordering.py:208`・`backend/tests/test_sync_apply_prefix_path.py:730`・`backend/tests/db/test_sync_apply_prefix_path_boundary.py:600` — いずれも局所関数を直接呼ぶ)
- [推論] 補足: V6 の上限を ⑦ の `_d2`(`sync/prefix_path.py:316` は下限だけを見る)にも足せば、P2 以外の経路での上限超え(DB の bigint 溢れ → B7)も B3a に寄る。本差分に含めるかは任意(含めると ⑦ の判定が 1 つ増える)

### 5-4. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体 | 7 箇所それぞれが `P1ContentRejection` を投げる / `_run_d1_event` が `cause="content_rejection"` で T9 経路へ渡す |
| DB 境界 | 各入力で T9 の原本・台帳 `rejected`・A5「拒否」(B3a)・D3 不前進・T5 の再採番が戻っている / 同じ D5 の再送で保存済み B3a を再掲 / その改訂版で再開できる |
| 負例 | B7 に残す `RuntimeError`(例 `sync/prefix_path.py:549`)が 500 のまま |

### 5-5. この差分が無いと 506 の何が止まるか

端末の内容の誤り(選手参照の誤記・一時 ID の再使用・V6 の範囲外)が 500 → B7 になり、**永久再送・先頭詰まり・理由の非表示**(plan.md:22)。506 の故障系(506/plan:76)で「解釈不能・5xx でキュー保持」は確かめられても、利用者が改訂・墓標で抜けられない。

---

## 6. D-4 O5 のサーバー側

### 6-1. 対象(本設計 11-1 `:167` の 7 件)

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

### 6-2. 署名

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

### 6-3. 挙動

1. 7 箇所の例外を `O5InvariantViolation(<code>, <既存の文言>)` に変える。**それ以外の `RuntimeError` は変えない**(列挙の外は B7 のまま — SP:1227 の O5 の定義「対象は実装が列挙する — 列挙の外は ① の B7」)
2. **捕捉する場所**: `sync/prefix_path.py` の `_apply_event` の `except` 群(`:808-813`)に `except O5InvariantViolation as violation: return P1Result("B3", 0, False, a5="拒否", reason=f"O5: {violation}", b3_code="O5")` を足す。O4 の `_NoWriteStop`(`:664-668` で取引の中で投げ、`:812-813` で取引の外で受ける)と同じ形で、**取引のスコープを例外で抜けた後に受けるので、ポートの書き込みを含めて全取消になる**。P1・P2 とも `_apply_event` を通る(`:828-838`・`sync/ordering.py:121-130`)
   - 代替案: `sync/apply.py` の `_run_d1_event`(`:172-199`)で受ける。取消の効果は同じだが、局所経路(`apply_p1_event`/`apply_p2_event`)を直接呼ぶ試験・故障系の実行器からは O5 が例外のまま見える。**推奨は `_apply_event`**(O4 と同じ層)
   - `:198-199` の `else: raise` は残る。O5・B3a を外した後にここへ来るのは `sync/prefix_path.py:592`(S-1 が保証 — 到達しない)・`:607`・`:655` の区分 `other`(端末とサーバーの D1 スロットの食い違い — SP v0.9 の残余で B7 のまま — SP:10)だけ
3. O4 の識別を区分に移す: `sync/prefix_path.py:664-668` の O4 の結果に `b3_code="O4"` を足し、`sync/apply.py:427` の `b3_branch = "O4" if result.boundary == "B3" else result.boundary` を `result.b3_code`(O4/O5)で決める形に変える。`B3Branch` に `"O5"`(`sync/model.py:51`)
4. **D5 を消費しない**: 7 箇所はすべて D5 の再照合(`:581-584`)より後で、台帳の挿入(`:705-706`)の前でも後でも同じ取引の中なので、取消で台帳の行も残らない(`:729` は挿入の後だが同じ取引)。同じ D5 の再送は、是正前なら同じ O5、是正後なら通常の適用になる(SP:1036)
5. ACK: 当該イベントは A5「拒否」(D-3 を承認すれば `rejection.kind = "O5"`)・D3 は直前まで・後続は未処理・前方は確定済みのまま同じ ACK(`sync/apply.py:425-429` の B3 の停止規則をそのまま使う — SP:778)
6. **理由の文言**: `"O5: " + 既存の固定文言`(O4 の `"O4: 永続化済み D2 の同値"` `:666` と同じ形)。7 件の文言は利用者入力も DB の値も含まない固定文字列(上の表)。理由の語彙は U-S1 が決める(WS:356)
7. **到達性の注記**: `sync/ordering.py:51` は実データでは到達しない。D2 の読取は `cursor = -1`(`sync/ordering.py:36`)から `d2 > after_d2`(`repositories/sync_apply.py:210-212`)で引くので負の D2 は読まれず、上限超えは bigint の列に入らない。不変条件の防御として列挙には残す(本設計 11-1 の判定どおり)

### 6-4. 列挙の仕組みと棚卸しの突合(pytest)

- **列挙の正は型と定数**: O5 は `O5InvariantViolation` を投げた箇所だけ。`O5_CODES` と、`sync/*.py` の AST から拾った `raise O5InvariantViolation(<code>, ...)` の `<code>` の集合が一致することを試験する(過不足を別々に数える)
- **`raise` 全件の棚卸しの突合**: 本設計 11-4 の 193 行を試験データ(例 `backend/tests/sync_raise_inventory.py`)に移し、`sync/*.py` の AST の `raise` 文と一対一で照合する(欠落 0・重複 0)。**キーは行番号でなく「ファイル・関数・例外型・文言・出現順」**にする [推論 — 行番号をキーにすると無関係な編集のたびに試験が落ちる]。行番号は表示用に持つ。D-4・D-5 で型が変わる 14 行は同じコミットで試験データを更新する

### 6-5. 既存の試験・資産への影響

- `backend/tests/test_sync_apply_ordering.py:200`(`pytest.raises(P1PreconditionError, match="隙間がない")`)は `O5InvariantViolation` に直す(`O5InvariantViolation` は `P1PreconditionError` の部分型にしない — 部分型にすると `_run_d1_event:172` の `except P1PreconditionError` に吸われうる)
- 故障系資産(p1/p2 の crash boundaries・o4)は変えない(O5 の箇所を通らない)。O5 の資産は D-7

### 6-6. 試験の追加範囲

| 種別 | 内容 |
| --- | --- |
| 単体(偽スコープ) | 7 箇所それぞれ: `_apply_event` が `P1Result("B3", a5="拒否", b3_code="O5")` を返し、例外は外へ出ない。7 箇所の状態は DB の制約か読取の条件で作れない(`:459` は NOT NULL の Uuid・`:651` は部分一意索引 `uq_operation_events_active_slot`・`:653` は外部キー `fk_operation_events_slot` — `db/sync_protocol/models.py:172-184`・`:729` は FOR UPDATE 済みの行の更新・`ordering:49`/`:51` は 6-3 の 7・`ordering:97` は値域の両端までの連続 — `backend/tests/test_sync_apply_ordering.py:194-201` の偽スコープの手法)ので、**発生箇所の検査はここで行う** |
| **DB 境界(注入点)** | 既存の名前付き注入点(`sync/crash_points.py:14-31` の `reach` と、試験だけが設置する `testing_crash_hook` `:45-52` — 既存の使い方 `backend/tests/db/test_sync_apply_apply_boundary.py:684`)の hook から、**列挙済みの `O5InvariantViolation(<O5_CODES の 1 つ>, ...)` を送出する**。製品コードに新しい注入の口は足さない。hook は点の名前しか受けないので、**対象イベントの何回目の到達かで送出する**(例: 前方 2 件 + 対象 + 後続 1 件の要求で、3 回目の `after_t4_projection` で送出)。送出する点は取引の中の書き込みの後に限る: `after_t1_ledger`(`sync/prefix_path.py:712` — 台帳の挿入の後)・`after_t3_prefix`(`:730` — D3 の前進の後)・`after_t4_projection`(`:732` — 投影の後)・P2 では `after_t5_order`(`:670` — 再採番の後)・その場登録では `after_t6_mapping`(`:742`)。**検証すること**: 前方 2 件は受理で同じ ACK に載る / 対象は A5「拒否」(O5)/ 後続は未処理 / D3 は前方まで / **対象の D5 の台帳行が無い**(D5 を消費しない)/ T9 の原本なし / 対象のイベント行・スロット・再採番・投影・一時 ID 写像・無効化意図が残っていない(全取消)/ hook を外して**同じ D5** で再送すると受理 |
| 負例 | 列挙の外の `RuntimeError`(`sync/prefix_path.py:549`・`:710`)は 500 のまま / hook から列挙の外の `RuntimeError` を送出すると O5 にならず 500 / 保存済み結果の再掲では O5 にならない(`:418`・`:422` は B7 のまま) |
| 突合 | 6-4 の 2 本 |

### 6-7. この差分が無いと 506 の何が止まるか

7 件の不変条件違反が 500 → B7 のままで、**その要求は ACK が返らないので、前方の確定済みイベントも端末では未送信のまま、当該イベントで永久再送**(本設計 3-2 `:76-77`)。SP v0.9 の O5 の契約(SP:769・:778)を HTTP 越しに満たせず、本設計 8 節の確認条件「O5 で当該イベントの再送が止まる」(`:142`)を 506 が確かめられない。**D-6 が無いと、D-4 を入れても端末が O5 の ACK を解釈できず同じ結果になる**(7-6)。

---

## 7. D-6 端末の O5

### 7-1. 現状(問題)

- 拒否理由の語彙は `内容起因` と `O4` だけ(`frontend/src/lib/sync/rejectionReason.ts:6-9`)。未知の `kind` は例外(`:90` `'未知の B3 分類です'`)。506 の codec はこの関数で ACK の `rejection` を読む(506/`frontend/src/lib/sync/wireCodec.ts:288`)ので、**サーバーが O5 を返すと ACK 全体が解釈不能**になり、WS 2-5 によりキューは一切変わらない(前方の受理も同期済みにならない)
- 要操作(管理者対応待ち)の下位ラベルは O4 と共用で 1 つ(`frontend/src/lib/sync/queueState.ts:9`・`frontend/src/lib/sync/queueTransition.ts:33`)。スロットは O4 と O5 の別を持たない(`queueTransition.ts:281-287`・`frontend/src/lib/sync/durableQueue.ts:96-105`)
- 管理者対応待ちからの再開は QT-07 だけで、**新しい D5 を必須**とする(`queueTransition.ts:604-611` の `sameSlotWithNewD5` — `:434-443`)。O5 の再開は「内容も D5 も変えずに未送信へ」(SP:1036)なので QT-07 では表せない
- 正本 v0.9 は、**要操作の状態と ACK の理由コード(O4/O5)を同じスロットへ不可分に確定し、再開時はその理由コードで再開方法を選び、理由コードが欠けたスロットは再開方法を推測せず要操作のまま管理者の判断を待つ**と定める(SP:1036・11-2 の「O4・O5 の区別の保持」SP:1808)
- 自動再送の停止は状態で決まる: 再送範囲は「未送信」だけを選ぶ(`frontend/src/lib/sync/resendRange.ts:156-160`)。要操作へ移せば止まる(変更不要)

### 7-2. 変更と署名

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
type AdminWaitRejectionCode = 'O4' | 'O5'
type D1QueueSlot = {                                       // :281-287
  ...; actionRequiredLabel?: ...
  rejectionCode?: AdminWaitRejectionCode   // ラベルが「管理者対応待ち」のスロットでは必須(下の 1)
}
QUEUE_TRANSITION_ROW_ID.O5_RETRY = 'QT-15'(:87-102)と規則の行(source 要操作 → target 未送信,
  trigger 'o5-retry-persisted', condition 'o5-corrected-same-d5-same-content')
QueueTransitionRequest に { kind: 'o5-retry-persisted'; slot: QueueSlot }(:352-386)
QueueTransitionInjections に confirmO5Correction?: (slot) => boolean | undefined(:332-350)
```

### 7-3. 挙動

1. **理由コードは必須の永続属性**: `applyA5` の O4 分岐(`queueTransition.ts:531-536`)に O5 を並べ、要操作・下位ラベル「管理者対応待ち」・`rejectionCode`(`'O4'`/`'O5'`)を**同じスロットへ 1 回の書き込みで**確定する(`durableQueue.ts:612-614` の複写に `rejectionCode` を足し、`:96-105` の型に持たせる)。新しい状態・下位ラベルは作らない(SP v0.9 の射程宣言 — SP:11)。`rejectionCode` は下位ラベルではなく、正本 v0.9 が求めるスロットの属性である(SP:1808)
2. **QT-07(O4 の再開)は `rejectionCode === 'O4'` のスロットだけ**: `applyO4Retry`(`:598-624`)の条件に `slot.rejectionCode === 'O4'` を足す
3. **QT-15(O5 の再開)**: 条件 = 起点が D1 付きスロット・状態が要操作・ラベルが管理者対応待ち・`rejectionCode === 'O5'`・`confirmO5Correction(slot) === true`(未注入・例外・`false` は遷移しない — 既存の「外部契約が未注入または確認不能なら状態を変えない」`:2`)。結果 = **同じ `(D4, D1, D5)`・同じ内容**で未送信(ラベルと `rejectionCode` を外す)。新しい D1 も新しい D5 も作らない(SP:1036・SP:886)。サーバーの是正確認は O4・O5 の別とともに渡す(SP:1036)ので、確認の注入も O4(`confirmO4Correction` `:348`)と O5(`confirmO5Correction`)に分ける
4. **理由コードの無い管理者対応待ちのスロットは再開しない**: QT-07 も QT-15 も適用しない(要操作のまま)。O4 とみなさない(SP:1036「理由コードが欠けた要操作(管理者対応待ち)のスロットは再開方法を推測せず、要操作のまま管理者の判断を待つ」)。永続層から読んだ記録に `rejectionCode` が無くても、例外にせず「理由コード欠落」の状態として保持する(破棄しない — SP:1041)[推論 — 同期はまだ本番で動いていない(506 未マージ)ので、理由コードの無い O4 のスロットが端末に残っている見込みは低い。移行で O4 を補うことは「推測」に当たるので行わない]
5. `ackAdapter.ts` の分類の注入(`frontend/src/lib/sync/ackAdapter.ts:123-134`)は `rejection.kind` をそのまま渡すので、型の追加だけで O5 が流れる(境界に依らない分類は D-3 の 506 への要求 — 4-4)

### 7-4. 既存の試験・資産への影響

- 遷移表の行数の固定: `frontend/src/lib/sync/queueTransition.spec.ts:72`(行 ID の列挙)・`:293` 以下の期待表(リテラル)・`:548`・`:677-678`(14 → 15)/ `frontend/src/lib/sync/prohibitions.spec.ts:2071`(H-59 の遷移の逐語照合 14 → 15 行)。期待表は「正本 7-2 の写し」(`queueTransition.ts:1`)で、写す元は確定済みの SP 7-2(SP:1036 を含む 15 行 — SP:1029-1043)
- 型の閉じた集合の検査: `prohibitions.spec.ts:307`(定数名の列挙)・`:533`(型名)・`:1482`(ACK アダプタが供給してはならない注入 — `confirmO5Correction` を `confirmO4Correction` と並べる)・`:1691-1712`(B3 の各型のキーの exact-set)に O5 を足す
- 既存の O4 の遷移の試験(`queueTransition.spec.ts:975-989`・`:1087-` の QT-07)は、スロットに `rejectionCode: 'O4'` を持たせる形に直す
- `frontend/src/lib/sync/ackAdapter.spec.ts:287-334`(O4 の分類)に O5 の対を足す

### 7-5. 試験の追加範囲(Vitest)

| 種別 | 内容 |
| --- | --- |
| 単体 | `parseB3Rejection` が O5 を `{kind, reason}` ちょうどで受ける / **負例**: O5 に `branch` → 例外・`reason` 欠落 → 例外 / `applyA5` で O5 → 要操作・管理者対応待ち・`rejectionCode: 'O5'`、O4 → `rejectionCode: 'O4'` |
| 遷移(負例中心) | QT-15: 同じ D5・同じ内容・確認 `true` → 未送信 / 新しい D5 → 不適用 / 内容が違う → 不適用 / 確認が未注入・`false`・例外 → 不適用 / `rejectionCode: 'O4'` のスロット → 不適用。QT-07: `rejectionCode: 'O5'` のスロット → 不適用。**`rejectionCode` の無い管理者対応待ちのスロット → QT-07 も QT-15 も不適用**(要操作のまま)/ 破棄(QT-12)も不適用のまま |
| 一致性 | 遷移表の行が SP 7-2 の 15 行と一致(既存の期待表方式)/ 再送範囲が要操作の O5 スロットを選ばない(`resendRange.ts` の既存の試験に O5 のスロットを 1 件足す) |
| 永続化 | 状態・ラベル・`rejectionCode` が 1 回の書き込みで確定し、IndexedDB の往復で保たれる(既存の `durableQueue.spec.ts` の手法)/ 書き込みの途中で失敗したとき、状態だけが要操作になって理由コードが欠ける中間状態が残らない |

### 7-6. この差分が無いと 506 の何が止まるか

D-4 を入れても、端末は O5 の ACK を解釈できず(`rejectionReason.ts:90`)キューを変えないので、**利用者から見た挙動は B7 の永久再送と同じ**(先頭詰まりも解けない)。D-4 と D-6 は組でしか承認できない(0 節)。506 の codec(506 所有)は `parseB3Rejection` に委ねているので、D-6 が入れば 506 側の codec の変更は要らない見込み [推論](境界に依らない分類は別 — 4-4)。

---

## 8. D-7 故障系資産(NFR-019(d))の O5

### 8-1. 現状

- SP v0.9 は 10-2 に O5 の観点の行を足した(SP:1700)。SP 10-3 の母集合の契約は、母集合を観点と ID の組の集合として exact-set で照合し、**繰り延べは繰り延べ先とともに母集合に記録して黙って欠落させない**と定める(SP:1745)
- 資産の母集合(`tests/fixtures/sync-protocol-population_v1.json`)の契約検査は、観点の集合を母集合ファイル自身から作る(`backend/tests/test_sync_apply_failure_contract.py:218` → `:961-985`)ので、**SP に行を足しても試験は落ちず、乖離が黙って残る**(現在 22 観点 — `:1775`)
- 母集合と資産は版付きの凍結資産で、コア領域(`.claude/core-areas.json:179`)

### 8-2. 選択肢(どちらも母集合 v2 を作る)

| 案 | 内容 | 代償 |
| --- | --- | --- |
| (a) 作成 | `tests/fixtures/sync-protocol-failures/o5-deterministic-invariant_v1.json` を作り(6-6 の注入点の方式で観測する)、母集合を v2 にする(`frontend/src/lib/sync/failureScenarioContract.spec.ts:23-40` の版表・`backend/tests/test_sync_apply_failure_contract.py:1775` の件数も) | 凍結資産の取り込みが 1 回増える。D-4 と同じステップで取り込めば 1 回で済む [推論] |
| (b) 受け取り先付きの繰り延べ | 母集合 v2 に `status: "deferred"` と受け取り先(タスク ID)を持つ行を足す(既存の U-R1 の繰り延べ行と同じ形) | 取り込みは同じく 1 回。資産は受け取り先が後で作る。受け取り先のタスクが要る |

**推奨: (a) を D-4 と同じステップで**(取り込みを 1 回にまとめる。D-4 の DB 境界試験と同じ注入点で観測できる)[推論]。

---

## 9. 本文書では提示しない(担当が別)

| 項目 | 506 への効き方 | 担当(典拠) |
| --- | --- | --- |
| `registrations`(その場登録の選手作成値)の生成 | 無いと、その場登録が B3a で T9 に記録される(`sync/prefix_path.py:628-629`)。登録値は指紋に入る(`sync/idempotency.py:278-287`) | 未割り当て — wire 契約(TSK-331)と端末(U-F7・U-F8)(本設計 2-1 G-F `:59`・5 節 `:108`) |
| `targets`(undo の解決済み対象)の生成 | 無いと undo が B3a(`sync/prefix_path.py:374`) | U-R1(`sync/prefix_path.py:118`・本設計 5 節 `:109`) |
| 506 の端末側の送信範囲の選択器(G-F が埋まるまで、最初のその場登録・undo の手前までの連続部分だけを送る) | 現行の選択器は未送信を全部選ぶ(`frontend/src/lib/sync/resendRange.ts:154-175`) | 506(本設計 2-1 `:61` — 506 の計画のステップ 3 の追補) |
| 506 の ACK アダプタの、境界に依らない拒否の分類 | 4-4 | 506(要求は 4-4 に書いた) |
| 配信の起動(`deliver_pending_sync_intents` を呼ぶ実行主体) | 製品の呼び出し元 0 件。無効化が配信されない | U-S1 の射程だが本 PR の射程外 — 受け皿のタスクが要る(本設計 5 節 `:111`・`sync/invalidation.py:174`) |
| ポートの登録表と検査器の接続 | 登録表が空で、全要求が `port_guard.py:496` で 500(本設計 11-1 `:174`) | 全 Port が揃った後に U-S1(本設計 9 節) |
| V12・D4・RG1・復旧世代の物理方式 | P3 の受理結果の `対象の D4` が整数(wire は文字列) | U-R1(本設計 6 節・G-D) |
| 内容検証・投影のポート実装 | 実経路が通らない。D-2c の新設の値の墓標を投影ポートが受けるかの確認も含む | U-X1(凍結中)・U-G2(G-E・本設計 7 節) |
| 端末の墓標生成器が V5・V9・V10 を作っていない(3-5) | wire の墓標が B3a になる | 端末側(U-F7/U-F8)か 506 の codec — 担当の確定が要る |
| O5 の理由の画面表示・自動エスケープ / Q8 / 「回復しない」の閾値 | — | 画面側の単位 / 論点 18(本設計 5 節 `:114-115`) |
| O5 の管理者への顕在化(ログ・通知)の実装 | SP は「O4・O5 は管理者へ不変条件違反を顕在化する」(SP:769)。ACK の理由は端末に届くが、管理者向けの経路は U-S1 に無い [推論] | 未割り当て [推論] |
| P3 の決定的な失敗(B10 のまま)・保存済み結果の破損の修復・端末とサーバーの D1 スロットの食い違い(`sync/prefix_path.py:607`・`:655` — B7 のまま) | — | SP v0.9 の残余(SP:10) |

---

## 10. PO への問い(まとめ)

1. D-0・D-1・D-2・D-3・D-5・D-7 のそれぞれを承認するか。**D-4 と D-6 は組で承認するか、両方とも不承認にするか**
2. D-2: **案 ①(推奨)か案 ②**。案 ① なら TSK-331 に WS:362 の担当の付け替えと V9 の `rejected_d5` の明記を依頼する(案 ② でも `rejected_d5` の明記は要る)
3. D-2b: V10 を **wire の境界で厳格に写す(推奨)** か、U-S1 の内部キーを `game_id` に改名する(非推奨 — 指紋・既存の公開口・試験の移行が要る)か
4. D-2c: 墓標の行の `event_kind` に**新設の値(仮称 `tombstone_unknown_kind`)を足す案(推奨)**か、墓標の行に限り `event_kind` を NULL にする案(非推奨)か。どちらも **data-model 正本の改訂(確定ゲート)を起こすことの承認**を含む
5. D-3: P3 の `current_version`・`b9_cause` を必須にするか(推奨 — 既存の試験 2 箇所を直す)
6. D-7: **(a) 作成(推奨 — D-4 と同じステップ)か (b) 受け取り先付きの繰り延べ**か。(b) なら受け取り先のタスク
7. 端末の墓標生成器(3-5)の担当をどこに置くか(本文書の射程外だが、D-2 の効果に効く)
