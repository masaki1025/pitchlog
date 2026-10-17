---
feature: us1-sync-port-surface
created: 2026-10-16
---

# 詳細設計: U-S1 の公開面と同期の失敗分類 — TSK-506 への接続契約

計画: [plan.md](plan.md) / 調査: [research.md](research.md)(典拠の詳細は research の A・B 節)。

**読み取り元**: develop `e7e8d3a4`(U-S1 = PR #132 のマージ後)。典拠のパスは `backend/src/pitchlog/` を省略する(例 `sync/apply.py:292`)。`SP` = `docs/design/sync-protocol.md`(v0.8)、`WS` = `docs/features/sync-wire-schema/design.md`、`506/plan.md` = TSK-506 の計画書(worktree `feature-tsk506-sync-http-entry`・読むだけ)。

**本書の構成**: 1〜2 節が **506 の着手条件**(いま develop にある公開面と、本 PR で足す公開口の契約)。3〜4 節が失敗境界と 4 区分。5 節が担当。6・7 節が**決定待ち**(U-R1・U-X1)。8 節が**確認条件**(実装後に確かめるもの — 着手条件には置かない)。9 節がポート登録の順序。10 節が 506 の照会への回答。11 節が例外の棚卸しと O5 の伝播先。12 節が T1/T2 の投影・検証 Port の公開境界(U-X1 P-7 の受理)。

---

## 1. 現行の公開面(develop `e7e8d3a4` — 506 の着手条件)

### 1-1. 入口が呼ぶもの

| 名前 | 所在 | 役割 |
| --- | --- | --- |
| `SyncRequest.from_payload(path, game_id, payload)` | `sync/model.py:231` | URL の経路・試合と E-1/E-2 本文の S-1 外形を照合し、`SyncRequest` を作る。外形違反は `RequestShapeError`(S-1 — 境界結果ではない。WS:107) |
| `apply_sync_request(context, request, rights, projection, validator, *, registrations=None, targets=None, ...)` | `sync/apply.py:292`(`registrations`・`targets` は **D1 キー** — D-0 で変更。旧 D5 キーは `TypeError`) | ③ 以降を実行し、D1 昇順の A5 と唯一の停止境界を確定して `AckResult`(D1 付き)または P3 の結果を返す |

- **トランザクションは U-S1 が開く**。入口は `TenantContext` を渡すだけで、Session・トランザクション・スコープを持ち込まない(`sync/apply.py` → `repositories/transaction.py` の `tenant_transaction_scope`)
- **原子性はイベント 1 件ごと**(要求全体ではない)。要求の途中で失敗しても、それより前のイベントの確定は残る(SP 6-2・9-2。ACK が返らない場合は次の再送で保存済み結果を再掲 — DI2)
- 先頭 `_` の関数・`repositories/sync_apply.py` の token は入口から呼ばない(token の発行と失効は U-S1 の内部。入口は触らない — research A 2-3)

### 1-2. 現行の型の要点

- **`SyncRequest` は要求に経路を 1 つ持つ**(`path` — `sync/model.py`)。経路は D5 の指紋に入る。E-1 の P1/P2 混在バッチは 2 節の `SyncEventBatch` で受ける
- 戻り値の `AckResult` は A3(境界結果 B1〜B4)・A5(イベントごとの受理/重複/拒否/退避/未処理)・D3 を持つ(research A 2-2)
- 3 Port(`RecordingRightsPort`・`ProjectionPort`・`ContentValidationPort`)は引数で受け、呼ぶ前に登録を検査する(`sync/ports.py` の `require_registered_port`)。**検査器は `port_guard` の import 時に接続済み**(`sync/port_guard.py:500`)だが、**登録表が空なので、どの実装も照合を通らない**(`sync/ports.py:134`)— 9 節・12 節

## 2. U-S1 の公開口 — E-1 の混在バッチ(ステップ 6)

wire 設計は E-1 について「経路はクライアントが選ばず、正本 8-1 の経路表と 6-2 に従ってサーバーが判定する」と定める(WS:163)。506 の承認済み計画も、P1/P2 混在バッチを HTTP 側で分割せず単一 ACK で扱うことを着手前に求める(506/plan.md:49・:64)。ステップ 6 で U-S1 に入口を実装した(PO 承認 2026-10-17)。

| 項目 | 契約 |
| --- | --- |
| 関数 | `backend/src/pitchlog/sync/apply.py` の `apply_sync_events(context, batch, rights, projection, validator, *, registrations=None, targets=None)`。`registrations`・`targets` は D1 キー |
| 入力 | `backend/src/pitchlog/sync/model.py` の `SyncEventBatch.from_payload(game_id, payload)` が S-1 外形を照合する。要求型は **経路を持たない**。ステップ 6 では V5 は U-S1 の種別リテラル、V9 は U-S1 の置換表現を受ける。wire の番号からの変換はステップ 7(D-2) |
| 経路の判定 | `sync/routing.py` の `route_for_event` がイベントごとに判定する。規則は SP 8-1 の参加区分から経路への対応表(SP:1290-1300): 毎球入力・選手交代・タイブレーク開始・試合終了宣言・状態補正 = **P2** / undo・選手のその場登録・墓標 = **P1** / 改訂版 = **T9 の不変な拒否原本に保存した経路を継承**。経路のない旧原本は元の V5・V9 から判定する。原本は既存の `RejectedOriginalReadToken` で指紋計算前に読む。改訂版の原本が読めない場合は、自身の V5・V9 で経路を決め、⑤ 以降を通常どおり通す(既存 P1 の W2 原本不在と同じく、記録権があれば B3a で T9 に原本を保存し、無ければ B4 で退避する)。原本の可視性が後から変わって判定が変わっても、保存済みの D5 は台帳の指紋と一致する経路で照合し直すので、同じイベントは同じ結果を再掲する。P4(記録権の不成立)と P5(内容拒否)は従来どおり U-S1 の内部分岐 |
| 指紋 | 判定した経路で取る。改訂版の経路は T9 原本の可視性で変わりうるので、**保存済みの D5 は台帳の指紋と一致する経路で照合し直し、同じイベントには同じ保存済み結果を再掲する**(一致しなければ異内容 = B3b)。改訂版以外の経路はイベントの内容だけで決まる |
| 戻り | **単一の `AckResult`**。D1 昇順・部分成功(前方の確定は残る)・停止境界は 1 つ(DI5) |
| 既存の入口 | `apply_sync_request(path=...)` は残す(E-2 の P3 と、経路を明示する既存の試験・資産のため) |

**この公開口が満たすのは、506 の着手前ゲートのうち TSK-391 側の「P1/P2 混在バッチ」(G-A)だけ**である(506/plan.md:49 は U-R1・U-X1/U-G2 の受理も求める — 2-1)。T9 の拒否原本にだけ経路を追記し、T8 原本の形は維持する。新しい repository operation と凍結資産の改訂はない。

### 2-1. 506 の着手前ゲート(独立に列挙する)

| # | ゲート | 担当 | 状態 |
| --- | --- | --- | --- |
| G-A | P1/P2 混在バッチを単一 ACK で扱う公開関数と要求型 | U-S1(本書 2 節) | ステップ 6 で実装。単体試験と DB 境界試験(専用 DB で 66 件)が green |
| G-B | **V5(イベント種別)・V10(対象参照)の wire から U-S1 への変換** — wire の毎球入力は `event_kind: "1"`(WS:182)、U-S1 はリテラル(`prefix_path.py:614`・`:638`)。変換が無いと正規の毎球入力が B3a/T9 になる。墓標・改訂版の表現も含む: wire の墓標・改訂版は V5 = `"8"`・`"9"`(WS:201)で、元イベントの種別を運ばない。U-S1 は元の種別のリテラルを V5 に要求し、拒否原本との一致を検査する(`prefix_path.py:223-230`・`:284-286`)。改訂版の経路も元イベントを継承する(SP:1299-1300)。**元の種別は拒否原本(T9 — 不変)から引く**。ただし V10(試合・D4・D1 — WS:206)は D5 を持たず、T9 の原本は D5 ごとに一意(`db/sync_protocol/models.py:430`)なので、同じ D1 に異なる D5 の拒否が複数あると V10 だけでは原本を選べない。よって **V9 に拒否された D5(`rejected_d5`)を運ぶことを wire 契約に明記し**(TSK-331 の合意が要る)、その D5 で原本を読み、V10 は対象スロットとの一致確認に使う。変換は「`"8"`/`"9"` → V9 の墓標/改訂 + 元の種別(`rejected_d5` の原本から)」。原本は不変なので、再送しても同じ変換値・同じ指紋になる。**墓標は内容を持たないので、元の種別の正しさに依らず適用できる**ようにする(種別が不正〔V5 の欠落・未知値 — WS:100 の S-2〕で拒否された原本は、元の種別を写すと `prefix_path.py:223` の検査で再び拒否され、B3 から墓標で再開する契約〔SP:855〕を満たせない。墓標では元の種別の検査を外し、`rejected_d5` の原本との照合だけを行う — U-S1 の挙動変更なので差分提示に含める。**ただし墓標の行も `operation_events.event_kind` の CHECK 制約に有効な種別が要る**〔`db/sync_protocol/models.py:140-143`〕ので、データモデルの判断が要る — 差分提示 D-2c)。**端末の墓標生成器 `frontend/src/lib/sync/k5Tombstone.ts:179-189` は空の内容で墓標を作り V5・V9・V10 を持たない**ので、変換を実装しても端末が送る墓標は B3a になる(担当未確定 — 差分提示 8 節)。**① の案(U-S1 が写す)は、`from_payload` が DB に触れない classmethod なので(`sync/model.py:230-233`)、拒否原本の読取は適用の前処理の取引(`sync/apply.py:87` 付近)で行う形になる。② の案(506 側)は 506 が拒否原本を読めない(U-S1 の内部)ので、`"8"`/`"9"` だけは U-S1 が写す口を別に公開する必要がある** | 置き場所は 2 案(差分提示で PO が選ぶ): ① U-S1 の `from_payload` で写す ② 506 側で写すが、変換表は U-S1 が公開する 1 か所に置き 506 はそれを呼ぶだけ(2 か所に表を持つと NFR-018 のコピー実装)。**写した後の値が D5 の指紋に入る**(`idempotency.py:277`)ので、変換は決定的で版を固定する | PO 決定待ち |
| G-C | 公開結果型: A5 各件の B3 分岐(B3a/B3b/O4/O5)と、P3 の `current_version`・`b9_cause` の構造化(ステップ 10 の前は文字列の `reason` だけ — research A 7 節 G-7) | U-S1(差分提示 D-3) | **ステップ 10 で実装**。`sync/model.py` の `A5Rejection`(`kind` = `"内容起因"`/`"O4"`/`"O5"`・`branch` は内容起因のときだけ `"B3a"`/`"B3b"`・`reason` は空でない文字列)を `A5Result.rejection` に持たせ、**A5 が「拒否」の件だけ・境界の値に依らず必ず付ける**(`A5Result.__post_init__` が「拒否」⇔ 分岐ありを検査。B4 の要求で再掲した保存済み B3a も内容起因 B3a — G-G の前提)。`RejectedChangeResult` は B8 に `current_version`(正の整数)・B9 に `b9_cause`(`"記録権不保持"`/`"旧復旧世代"`)を**必須**で持ち、他の境界は持たない(`__post_init__` で検査)。従来の `reason`・`AckResult.b3_branch` は残す。`apply_sync_request`・`apply_sync_events` の両入口で同じ型。単体試験と DB 境界試験(専用 DB)が green |
| G-G | **506 の ACK アダプタが、境界の値に依らず A5 の各件の拒否理由を分類する**。B4 の要求でもサーバーは保存済みの B3a を A5 に再掲し(`sync/apply.py:530` で境界が B4 → `:555` の再掲)、ステップ 10 からはその件にも `rejection`(内容起因 B3a)を付ける(`:618` — G-C)が、506 のアダプタは境界が B3 のときだけ拒否を分類する(506 worktree `frontend/src/lib/sync/ackAdapter.ts:122`)ので、再掲された拒否のスロットが要操作へ移れない。受入条件: B4 に保存済み B3a と未使用イベントが混在する HTTP 試験 | 506 | 506 の計画への追補が要る(本書は要求だけを書く) |
| G-D | V12・D4・RG1(記録権) | U-R1 | U-R1 の決定待ち(6 節) |
| G-E | 内容検証・投影のポート実装 | U-X1(凍結中)・U-G2(ブロック中) | 7 節 |
| G-F | `registrations`(その場登録の選手作成値)・`targets`(undo の解決済み対象)の生成と注入 | `registrations` は wire 契約(TSK-331)と端末(U-F7 — 未着手・担当なし / U-F8 — 523 が調査中)が「端末が E-1 に何を載せるか」を決めるまで埋まらない。`targets` は U-R1 | 未割り当て(5 節) |

**G-F が埋まるまでの送信の規則**(506 の端末側の送信範囲の選択に実装する — 現行の `frontend/src/lib/sync/resendRange.ts:154-175` は未送信スロットを選ぶだけで、その場登録・undo の手前では止まらない。**506 の計画のステップ 3〔frontend 接続〕に、選択器・呼出側・連続性の試験を割り当てる追補が要る** — 506 の所有なので本書は要求だけを書く): その場登録と undo を U-S1 へ渡すと B3a で T9 に記録される(永久に残る)。一方、それらを保留して後続だけを送ると、サーバーは欠番で B2 にして止める(`apply.py:380`)。よって 506 は、**キューの先頭から、最初のその場登録・undo の手前までの連続した部分だけ**を送る(それ以降は未送信のまま保持)。登録値は D5 の指紋に入る(`idempotency.py:270`)ので、生成の規則が決まる前に一度でも送ってはならない。毎球入力だけのキューには影響しない。

## 3. 失敗境界

### 3-1. U-S1 が境界結果まで決めて返すもの(例外にならない)

- D1 付き: B1(受理・重複)/ B2(連番の欠落)/ B3(B3a 内容拒否・B3b 同じ D5 の異内容・O4)/ B4(記録権不一致 — 退避)/ B6(認可 — 自テナントの試合でない)/ B7 の一部(RG1 の事前読取の失敗)
- P3: 変更受理・B8・B9・B10・B12・B13・B14
- 典拠と各行の写像は research A 3-1 節

### 3-2. 例外として入口へ上がるもの(現行)

| 例外 | 典拠 | 現行の HTTP | v0.9 の後 |
| --- | --- | --- | --- |
| `RequestShapeError`(S-1 外形違反) | `sync/model.py` | 入口が 4xx に写す(WS 2-4 — S-1 は境界結果ではない)。送り直しても解消しない場合の止め方は未決(WS の WU-1) | 変わらない(要求単位の失敗で、イベントの境界結果に載せられない)。顕在化は Q8 |
| 区分 `other` の `P1PreconditionError`(内容検査の try の外) | `sync/apply.py:198-199` ほか — 11 節 | 未捕捉 → 500 → B7 | 11 節の判定で **O5**(B3 + 拒否 + 要操作 — ordering の「隙間がない」1 件。ステップ 8)または **B3a**(内容起因 5 件。ステップ 5)へ。残り(確定スロットの食い違い・状態依存・U-R1 待ち — 11-1)は B7 のまま |
| 不変条件の `RuntimeError` | 11 節 | 500 → B7 | 決定的かつイベントの取引内のもの(列挙 6 件)は **O5**(ステップ 8)、それ以外は B7 のまま |
| DB の例外・競合 | — | 500 → B7 | B7 のまま(再送で通り得る) |
| ポート未登録(`PortRegistrationError`) | `sync/ports.py:139-143` | 500 → B7 | B7 のまま(構成の誤り。9 節の接続で解消) |

**ステップ 8 の実装**: O5 の 7 件(上の 2 行の O5)は `O5InvariantViolation`(`sync/invariants.py` — 列挙の正は `O5_CODES`。`P1PreconditionError` の部分型にしない)で投げ、`sync/prefix_path.py` の `_apply_event` が取引のスコープを抜けた後に受けて `P1Result("B3", a5="拒否", reason="O5: <固定文言>", b3_code="O5")` を返す(O4 の `_NoWriteStop` と同じ層)。公開入口は `b3_code` で `AckResult.b3_branch` を `"O5"`(O4 は `"O4"`)にする。列挙の外の例外は従来どおり 500 → B7。

**全取消と再試行**: 失敗したイベントの取引は全取消される(イベント 1 件ごとの原子性)。それより前のイベントは確定済みのまま。B7(ACK なし)では次の再送で保存済み結果が再掲され、前方は同期済みになる。**O5(v0.9)は ACK を返すので、前方は同じ応答で同期済みになり、当該イベントで自動再送が止まる**。

## 4. 4 区分の対応表(山田正輝の指示 2026-10-16)

| 区分 | 恒久/一時 | 境界結果(v0.9 の後) | HTTP(506 が写す) | 端末のキュー | 顕在化 |
| --- | --- | --- | --- | --- | --- |
| **前提違反(イベント)**: 決定的な不変条件違反・区分 `other` の前提違反 | 恒久 | **O5** = B3 + A5「拒否」(理由種別 O5) | 200 + ACK | 要操作(**管理者対応待ち**)。自動再送を止める。是正確認後に未送信へ(7-2) | B3 の通知列(止まった位置と理由) |
| **前提違反(要求)**: S-1 外形違反 | 恒久 | 境界結果なし(S-1) | 4xx(WS 2-4) | 未送信のまま(要求が届いていない) | Q8「同期が進んでいない」(画面側) |
| **内容拒否** | 恒久 | B3a(内容起因の `other` も B3a へ寄せる) | 200 + ACK | 要操作(改訂待ち / 墓標待ち) | B3 の通知列 |
| **一時的 DB 障害**・競合・原因不明 | 一時 | B7 | 5xx(ACK なし) | 未送信のまま・自動再送 | 回復しない場合は顕在化(B7 行・Q8 — 閾値は論点 18) |
| **結果未確認**(タイムアウト・接続断) | 一時 | B7(端末側で判定) | — | 未送信のまま・自動再送。再送で保存済み結果を再掲(DI2) | 同上 |

**実挙動の典拠**(research B — コードと試験で確認): develop には同期要求を送るクライアントのコードが無い(送信層は 506 の未マージのステップ 3)。サーバーは未捕捉の例外を 500 にする(`api/errors.py:132-146`)。SP 段階 ① は原因を問わず B7(SP:694)、B7 は ACK なし・未送信のまま・自動再送・通知が届かない(SP:768)。**5xx を受けたときのキュー・再送・表示を確かめる既存の試験は無い**(research B 1-3)— 8 節の確認条件で 506 が足す。

## 5. 担当の線引き

| 項目 | U-S1(済み) | 本 PR(391) | 506(これから) | ほか |
| --- | --- | --- | --- | --- |
| S-1 外形の照合 | `from_payload` | — | 呼ぶ・4xx へ写す | — |
| **イベントごとの経路の判定**(P1/P2) | — | 差分提示(2 節)→ PO 承認後に実装 | 判定しない | — |
| P4・P5 の内部分岐 | `apply.py` の ⑤・⑦ | — | 関与しない | — |
| トランザクション・テナントスコープ | U-S1 が開く | — | `TenantContext` を渡す | — |
| O5 の写像 | — | 差分提示(計画のステップ 3)→ PO 承認後に実装 | 200 + ACK で返す | — |
| 例外 → HTTP の写像 | — | 本書 4 節で契約 | **実装** | — |
| V5(イベント種別)の値の対応(wire は番号・U-S1 はリテラル) | — | 差分提示(2-1 G-B) | — | **PO 決定待ち**(推奨: U-S1 の `from_payload` で写す)。変換は決定的で版を固定する(指紋に入る) |
| V10(対象参照)のキーの写し | — | 差分提示(2-1 G-B) | — | **PO 決定待ち**(同上) |
| 公開結果型(A5 の B3 分岐・P3 の `current_version`・`b9_cause`) | 文字列の `reason` だけ | 差分提示(2-1 G-C)→ ステップ 10 で実装 | 写す | — |
| `registrations`(その場登録の選手作成値)の生成 | 引数で受ける | — | — | **未割り当て**(2-1 G-F — wire 契約〔TSK-331〕と端末〔U-F7・U-F8〕の決定に依存) |
| `targets`(undo の解決済み対象)の生成 | 引数で受ける | — | — | **U-R1**(`sync/prefix_path.py:118` は U-R1 の解決を前提) |
| 3 Port の実装 | 型と検査 | — | — | 記録権 = U-R1 / 投影 = **U-X1(凍結中)** / 内容検証 = U-X1・U-G2(us1-sync-apply-core/design.md:38) |
| 配信の起動(`deliver_pending_sync_intents` を呼ぶ実行主体) | 配信関数(`sync/invalidation.py:174`) | — | — | **U-S1 の射程**(計画 R-13・data-model:11・:2337 — 同期経路の配信と再試行は同期側)だが**本 PR の射程外**。受け皿のタスクが要る(製品の呼び出し元 0 件) |
| 配信先の本物(`InvalidationSinkPort` の実装) | 型 | — | — | **PO 判断**(data-model v0.10 の射程宣言が「配信先の本物」を扱わない範囲に置く) |
| ポート登録表と検査器の接続 | — | — | — | 全 Port が揃った後(9 節)。所有は U-S1(`sync/ports.py`) |
| O5 の理由の画面表示・自動エスケープ | — | — | — | 画面側の単位(受入条件: wire の JSON の値を文字列として自動エスケープで表示し、生 HTML を挿入しない — NFR-023) |
| Q8 の常時表示・回復しない判定の閾値 | — | — | — | U-F7 または画面側 / 論点 18 |

**G-5 の扱い(506 の着手に効く)**: 2-1 の G-F と「G-F が埋まるまでの送信の規則」を参照。

## 6. U-R1 の決定待ち(決め打ちしない)

- **D4 の物理形式**: U-S1 は記録権世代番号の十進文字列と仮置きしている(`sync/apply.py:108-128`・`sync/rejection.py:183-189`)。wire は不透明な文字列(WS)
- **V12・復旧世代**: U-S1 は値をポートへ素通しする(判定は `RecordingRightsPort` — U-R1)
- **`targets` の解決**(undo)と `PortWriter.run_function`(未実装)
- 本書のどの着手条件も、これらの物理方式に依存しない

## 7. U-X1 の凍結解除まで満たせない条件(506 の DoD を分ける材料)

投影ポート `ProjectionPort` は U-X1 の所有(us1-sync-apply-core/design.md:38)、T4(投影)は P1・P2・P3 すべての経路に含まれる(SP:1267-1269)。よって次は U-X1 の凍結解除まで満たせない。

- 実在する試合への E-1・E-2 を、適用核まで通す経路全体(登録表が埋まらない — 9 節)
- 1 球を HTTP 経由で実 DB の原本・投影へ保存し再読込する結果(506/plan.md:68)
- data-model 12-4 の越境テスト再実行ゲートのうち、実経路を要する判定

**先行できるもの**: E-1・E-2 の形・ステータス・wire codec・通信分類・越境テスト(未登録ポートで止まる前段まで)・4 節の HTTP への写し方・EP-1〜EP-11 のうち適用核に依存しない項目。

## 8. 確認条件(506 が実装したら確かめる — 着手条件ではない)

| 確かめること | 既存の U-S1 の試験(典拠) | 506 が HTTP 越しに足すもの |
| --- | --- | --- |
| 混在バッチの単一 ACK・D1 順・部分成功 | `backend/tests/db/test_sync_apply_apply_boundary.py` の `test_mixed_event_batch_single_ack_routes_and_replays`・`test_mixed_event_batch_stops_after_content_rejection` ほか | E-1 で P1/P2 を混ぜた要求の ACK |
| ACK 消失後の再送で保存済み結果を再掲 | `backend/tests/db/test_sync_apply_*`(research A 6-2 の表) | 同じ要求を 2 回送る |
| O5 で当該イベントの再送が止まる | PO 承認後の実装で足す DB 試験 | 200 + ACK の A5 拒否(O5)と端末の要操作 |
| 5xx でキューが未送信のまま自動再送 | **試験なし**(research B 1-3) | 506 の送信層の試験 |
| B4 の退避・B3b の再掲 | `test_sync_apply_apply_boundary.py` ほか | 旧 D4 からの要求 |

## 9. ポート登録の順序 — 「最後の 1 本」

検査器 `_PORT_VERIFIER` は接続済みで(`sync/port_guard.py:500`)、残る配線は登録表 `PORT_IMPLEMENTATIONS` へ Port の実装を積むことだけである。所有は U-S1(`sync/ports.py`)。登録は Port ごとに独立して積める。1 球保存の経路が要求するのは記録権・投影・検証の 3 本で、無効化の配信先は配信の経路だけで照合する(12-3 節 — 2026-10-17 訂正。旧記述の「4 Port と配信の実行主体が揃ってから」は機構上の条件ではない)。依存の向き: 各 Port の実装(U-R1・U-X1・U-G2・未割り当て)→ 登録表への登録(U-S1)→ 実在する試合への経路が通る。本 PR では登録しない。

## 10. 506 の照会への回答(2026-10-16、G-A・G-C は 2026-10-17 更新)

| 照会 | 回答 |
| --- | --- |
| (1) 混在バッチを単一 ACK で渡す公開関数と要求型(対象コミット) | 2 節。`SyncEventBatch`(`sync/model.py`)と `apply_sync_events`(`sync/apply.py`)をステップ 6 で実装 |
| (2) イベントごとの分類の担当 | U-S1(2 節 — SP 8-1 の対応表) |
| (3) P4/P5 の内部分岐の担当 | U-S1(実装済み) |
| (4) `registrations`・`targets` の生成・注入 | 2-1 G-F。決まるまで、506 はキューの先頭から最初のその場登録・undo の手前までの連続した部分だけを送る |
| (5) B6/B7・P3 受理/拒否・内容拒否/例外の公開結果型 | 3 節・4 節。構造化(A5 の B3 分岐・P3 の `current_version`・`b9_cause`)は 2-1 G-C — **ステップ 10 で実装**(`A5Result.rejection`・`RejectedChangeResult.current_version`/`b9_cause`) |
| (6) HTTP へ渡す失敗境界と受理可否 | 4 節。**受理可否: 条件付き** — TSK-391 側の G-A はステップ 6、G-C はステップ 10 で実装、G-B は後続ステップの実装待ち(2-1)。G-D〜G-F は他の単位の受理が要る(本書では満たせない) |

## 11. 例外の棚卸しと O5 の伝播先

`backend/src/pitchlog/sync/*.py` の `raise` 文 **193 件**を、ファイル:行で一対一に棚卸しした(コミット `b63d11e9` 時点。`grep -n "raise\b"` の出力と表を突合して**欠落 0・重複 0**)。**ステップ 8 で突合を pytest にした**: 以後の棚卸しの正は試験データ `backend/tests/test_sync_apply_raise_inventory.py` の `_TABLE`(現行 204 件 — 11-2 の末尾・11-4 の冒頭)で、AST の `raise` 文と「ファイル・関数・例外型・文言・出現順」のキーで一対一に照合する(行番号は表示用)。区分は次の順で当てはめた: 1 適用外(確定後の配信)/ 2 定義・登録の検査 / 3 S-1 / 4 P3 / 5 内部制御 / 6 O4 / 7 既に境界結果 / 8 D1 の未分類の失敗。区分 8 だけを O5 / B3a / B7 / 決定的だが取引外 に判定した。

### 11-1. O5 の判定の方針(ステップ 2 の前提)

- **O5 は「決定的」かつ「イベントの取引内」かつ「未使用 D5 の新規適用」のものだけ**(**7 件**: prefix_path:459・651・653・729 / ordering:49・51・97)。当該イベントの取引を全取消し、D5 を消費しない(台帳に何も残らない)。ステップ 8 で 7 件を `O5InvariantViolation(<code>, <既存の文言>)` に変えた(`sync/invariants.py` の `O5_CODES` が列挙の正。送出箇所との一致は pytest が AST で突合する)
- **O5 の再開は「内容も D5 も変えずに再送」**(管理者の是正確認の後)。D5 を消費しないので同じ D5 で通る。**O4 の再開(同じ D1 スロット・新しい D5 — 端末の QT-07 は新しい D5 を必須とする `frontend/src/lib/sync/queueTransition.ts:604`・`:608`)とは条件を分ける**。端末の遷移の契約(7-2)に O5 の行を別に書く
- **D5 の再照合より前で走る 2 件(prefix_path:886・893 — 記録権世代行・D3 の型の検査)は O5 にしない**: `prefix_path.py:547`・`:581-584` で D5 の再照合より先に走るので、保存済み結果の**再掲**でも起き得る。再掲を B3 拒否に変えると DI2(SP:1282-1285 — 保存済み結果は再掲する)を破る。スキーマ破損でしか起きないので B7 のまま
- **保存済み結果の破損(3 件 — prefix_path:418・422 / idempotency:261)は O5 にしない**: 既存 D5 の**再掲**で起きる。受理済みなら D3 は既に前進しており、B3 の「拒否 + 直前までの D3」の契約(SP:764)と矛盾する。**B7 のまま**とし、管理者が台帳を修復するまで再送が続く(顕在化は B7 の「回復しない場合」— v0.9)。修復・再掲の手順は本 PR では決めない(残余)
- **確定スロットとの食い違い(2 件 — prefix_path:607・655 の区分 other)は O5 にしない**: 未使用 D5 なのに D1 ≤ D3、または D3+1 にスロットが既にある。D3 は後退しない(SP:666)ので、是正しても同じ D1 では通らない。**回復の契約(当該イベントをどう扱うか)を v0.9 の確定ゲートで PO に問い**、決まるまでは現行どおり(B7)。同じ行が投げる `w2_violation` は従来どおり B3a
- **前処理で起きる決定的な失敗(8 件)と確定後の 1 件(`apply.py:413`)は O5 にしない**。前処理の 8 件は、主キーで起こり得ないもの、スキーマ破損でしか起きないもの、試合の状態待ちで再送すれば通り得るもの(`apply.py:101` — 現世代の記録権行が無い準備中の試合)で、B7 に残す(fail-safe 側)。`apply.py:413` は一意制約と `prefix_path.py:680` で到達しない見込みで、B7 に残す
- **D4 の形式で止まる 2 件(`rejection.py:187`・`189`)は U-R1 の決定待ち**(6 節)。U-R1 が D4 の物理形式を決めるまで B7 のまま残し、決定後に T8 の世代番号の保存形式として扱う
- **区分 2(定義・登録の検査)は O5 にしない**: プログラム・構成の誤りで、デプロイで直して再送で通るのが正しい。いまは登録表が空なので、全要求が前処理の `port_guard.py:496`(未登録のポート実装)で 500 になる(9 節)
- **棚卸しの行番号はコミット `b63d11e9` 時点**(本節・11-2・11-4 の `ファイル:行`)。ステップ 4〜8 で行が動いた(例 ordering:34・49・51・97 → ステップ 8 の後 45・60・62・110)。ステップ 8 で raise 文と棚卸しの一対一の突合を pytest にし(`backend/tests/test_sync_apply_raise_inventory.py`)、照合のキーを行番号でなく「ファイル・関数・例外型・文言・出現順」にした(無関係な編集で落ちないように)。**現行の行番号・型・文言・区分は試験データが正**(11-4 の冒頭)
- **内容起因と判定した 7 件のうち 2 件(prefix_path:470・680)は永続状態に依存する**(ステップ 5 の実装で判明)。B3a にせず B7 のまま(再送で状態が変われば通り得る)
- **P3 には O5 の受け皿が無い**: P3 の決定的な `RuntimeError` は B10 のまま再試行が続く。本 PR の射程外(PO 裁定は D1 付き経路)として残余に記録する

### 11-2. 区分ごとの件数

| 区分 | 件数 | 内訳 |
| --- | --- | --- |
| 1 適用外 | 10 | invalidation 9・tokens 1 |
| 2 定義・登録の検査 | 56 | port_guard 25・rejection 6・prefix_path 5・idempotency 5・ports 4・model 4・tokens 3・invalidation 2・intent_ids 1・change_path 1 |
| 3 S-1 | 17 | model 17 |
| 4 P3 | 21 | change_path 20・model 1 |
| 5 内部制御 | 5 | prefix_path 4・rejection 1 |
| 6 O4 | 1 | prefix_path 1 |
| 7 既に境界結果 | 38 | prefix_path 34(B3a 33・B4 1)・gate 4(RG1) |
| 8 D1 の未分類の失敗 | 45 | 下の内訳 |
| **合計** | **193** | grep の 193 行と一致 |

区分 8 の内訳:

| 判定 | 件数 | 行 |
| --- | --- | --- |
| **O5** | **7** | prefix_path:459・651・653・729 / ordering:49・51・97 |
| **再照合前**(B7 のまま — 11-1) | **2** | prefix_path:886・893 |
| **再掲の破損**(B7 のまま — 11-1) | **3** | prefix_path:418・422 / idempotency:261 |
| **確定スロットの食い違い**(要決定 — 11-1) | **2** | prefix_path:607・655(区分 other。同じ行の w2_violation は B3a) |
| **U-R1 待ち**(B7 のまま — 11-1) | **2** | rejection:187・189 |
| **B3a** | **5** | prefix_path:444・448・450・496 / ordering:34(ステップ 5 で実装) |
| **B7(状態依存)** | **2** | prefix_path:470・680 — 選手行・一時 ID の写像の有無という永続状態で結果が変わるので B3a にしない(ステップ 5 で判明) |
| **B7** | **12** | prefix_path:177・549・710 / rejection:130・169・200・204 / idempotency:195・198・250 / invalidation:70・72 |
| **決定的だが取引外**(前処理 8・確定後 1) | **9** | 前処理: apply:101・104・107・127・327 / gate:46 / idempotency:117・132 — 確定後: apply:413 |
| 中継(送出元の判定に従う) | 1 | apply:199 |
| 計 | 45 | |

**突合**: grep の 193 行と下表の 193 行を `ファイル:行` で一対一に照合した — **欠落 0・重複 0**。ファイル別件数も一致(apply 7・change_path 21・gate 5・idempotency 11・intent_ids 1・invalidation 13・model 22・ordering 4・port_guard 25・ports 4・prefix_path 63・rejection 13・tokens 4)。

**ステップ 8 の時点(試験データ — 現行の正)**: **198 件** = 193 + 5。増えたのは区分 2 の 1 件(`apply.py` の `_apply_d1_request` の `TypeError`「registrations と targets は D1 をキーにする」— ステップ 4〜6)と区分 3 の 4 件(`model.py` の `SyncEventBatch.__new__` の S-1 — ステップ 6 の E-1)で、区分 2 は 57・区分 3 は 21。区分 8 の内訳は変わらない(O5 の 7 件は型が `O5InvariantViolation` に、B3a の 5 件はステップ 5 で `P1ContentRejection` に変わった)。ファイル別は apply 8・model 26、他は上と同じ。

**ステップ 10 の時点(試験データ — 現行の正)**: **204 件** = 198 + 1 + 5。ステップ 8 の是正で区分 8 B7 の 1 件(`prefix_path.py` の `_call_port` の `RuntimeError`「ポートが O5 の型を送出した」— design 12-2)、ステップ 10 で区分 2 の 5 件(`model.py` の D-3 の不変条件 — `A5Rejection.__post_init__` 2・`A5Result.__post_init__` 1・`RejectedChangeResult.__post_init__` 2)を追加した。ステップ 10 では `change_path.py` の B8・B9 の 3 行の文言(`current_version=`・`b9_cause=` の追加)も変わった(区分は 4 P3 のまま)。


### 11-3. O5 の正本への伝播先

#### 11-3-1. `docs/design/sync-protocol.md` の O4 の全行(`grep -n O4` → 25 行)

| 行 | 節・場所 | 判定 | 理由 |
| --- | --- | --- | --- |
| 132 | 2-5 R-ORDER-ASSIGN | **O4 固有 — 変えない** | 正本の表は「5-5 の O1・O2・O4」(D2 規則)。O5 は D2 によらないので、R-BOUNDARY(:136 — 6-3 の B1〜B7。B3a・B3b と同じ B3 の分岐の置き場)へ要素を足すか、新しい関係を立てる。どちらでも `scripts/design_relations/sync-protocol.json` を同時に直す(2-5 の双方向一致 — :124・:140)[推論: どの関係に入れるか] |
| 326 | 4-3-A W3-b | **O4 固有** | 「論理再生順は D2 だけで決まる(5-5 の O1・O2・O4)」— D2 の典拠 |
| 625 | 5-5 規則表の O4 | **O4 固有** | D2 同値の規則。O5 の規則行は 5-5 に置かず、6-3 に新しく置く [推論] |
| 629 | 5-5「O4 で検出したときの扱い」 | **O4 固有** | 採番競合・永続化済み同値の 2 場面は D2 のもの |
| 634 | 5-5 永続化済み同値の行 | **O4 固有** | 同上 |
| 638 | 5-5 O4 の既存結果・再開の段落 | **O4 固有** | ただし O5 側で同じ形の段落(既存の拒否・要操作を使い、新しい結果値・状態を作らない)を 6-3 / 7-2 に書くときの雛形になる |
| 755 | 6-3 定義の伝播(箇条) | **O5 を並べて足す** | 6-3 は B3 の置き場 |
| 764 | 6-3 B3 の行 | **O5 を並べて足す** | 成立条件(「恒久的な内容拒否、O4 …、または O5 …」)と、ACK・キュー・再試行・通知の各列 |
| 771 | 6-3「O4 の外部結果は B3 と A5 拒否…」 | **O5 を並べて足す** | O4・O5 に一般化 |
| 878 | 6-4 除外経路の O4 の行 | **O5 を並べて足す**(別の行) | 再開方法は O4 をそのまま写せない(所見 2・3) |
| 924 | 7-1 定義の伝播(箇条) | **O5 を並べて足す** | |
| 942 | 7-1「O4 は理由コード O4 とともに…」 | **O5 を並べて足す** | 理由コード O5。「当該 P2」は O5 では D1 付きの当該イベント |
| 957 | 7-1 経路別の応答契約 P2 | **O5 を足す(O4 の文は P2 固有のまま)** | O5 は P1・P2(P4 で O5 を採るなら P4 も)の各行に掛かる |
| 1002 | 7-2 定義の伝播(箇条) | **O5 を並べて足す** | |
| 1007 | 7-2 要操作の意味 | **O5 を並べて足す** | 待つもの(管理者の是正確認)を O5 にも |
| 1021 | 7-2 未送信 → 要操作 | **O5 を並べて足す** | |
| 1025 | 7-2 要操作(O4 の管理者対応待ち)→ 未送信 | **O5 を並べて足す** | 計画 2 節の 3 の「O4・O5 に一般化」。ただし是正後に同じ D1・新しい D5 で通らない O5 がある(所見 2・3) |
| 1214 | 8-1 定義の伝播(箇条) | **O5 を並べて足す** | O5 が 8-1 へ伝播する関係を 2-5 に宣言する場合 |
| 1226 | 8-1 T5 | **O4 固有 — 変えない** | T5 は D2 |
| 1268 | 8-1 経路別の適用表 P2 | **O5 を足す(O4 の文は P2 固有のまま)** | O5 は P1・P2(・P4)の行に「当該イベントを全取消して適用しない」を足す |
| 1550 | 9-5 回収(要操作の破棄契機) | **O5 を並べて足す** | 「O4・O5 では管理者対応が完了するまで」。9-5 は TSK-547(v0.10 へ繰り下げ)が単独 PR で触る節なので衝突に注意 [推論] |
| 1602 | 10-2 定義の伝播(箇条) | **O5 を並べて足す** | |
| 1685 | 10-2 O4 の試験観点の行 | **O4 固有 — 変えない** | D2 同値のシナリオ。O5 の観測行は別に足す(計画 2 節の 3「10-2 に O5 の観測」) |
| 1791 | 11-2 定義の伝播(箇条) | **O5 を並べて足す** | 11-2 の導入文(:1783 —「4-3、4-3-A、4-4、5-5 の定義行の意味」)は、O5 の定義を 6-3 に置くならあわせて直す |
| 1817 | 11-2 論点 2・3・26 D2 の方式 | **O4 固有 — 変えない** | O5 の構造上の帰結(端末の拒否結果へ理由 O5 を保存できる構造)は別の行で書く |

計 25 行 = **O5 を足す 16 行**(755・764・771・878・924・942・957・1002・1007・1021・1025・1214・1268・1550・1602・1791)/ **O4 固有で変えない 9 行**(132・326・625・629・634・638・1226・1685・1817)。

O4 の行ではないが O5 で触る箇所(参考): 6-2 段階 ① の注記(計画の典拠 `:694`)・6-3 B7 の行(`:768` — 回復しない場合の顕在化)・2-5 の関係宣言とマニフェスト(上の 132 の行)。

#### 11-3-2. `docs/features/sync-wire-schema/design.md` の O4 の全行(6 行)

| 行 | 場所 | 判定 | 理由 |
| --- | --- | --- | --- |
| 31 | 記号の注記「O1〜O4」 | **O5 を並べて足す** | 正本の記号の列挙(O1〜O5) |
| 90 | L-4 列挙値(O4 は `"O4"`) | **O5 を並べて足す** | O5 は `"O5"` |
| 147 | 2-6 対応表 `event_results[].rejection`(B3a・B3b・O4) | **O5 を並べて足す** | |
| 308 | 4-2 `rejection.kind`(`"内容起因"` または `"O4"`) | **O5 を並べて足す** | `kind` に `"O5"` |
| 356 | 4-5 B3a・O4・B14 の `reason` | **O5 を並べて足す(書き方に注意)** | 同じ行の「中身は内容の検証(⑦ / P3 の⑥)を実装する単位が決める」は O5 に当たらない。O5 の理由の語彙は U-S1(不変条件の検出側)が決める [推論] |
| 422 | N-11 理由の語彙・構造 | **O5 を並べて足す(書き方に注意)** | 受け取り先が「内容の検証を実装する単位」なので、O5 については U-S1 に分ける [推論] |

wire 設計の O4 には D2 固有の行が無い(6 行すべて O5 を足す)。

### 11-4. 全件の表(ファイル順・行順)

**この表は `b63d11e9` 時点の 193 行と判定理由の記録として残す。ステップ 8 以後の棚卸しの正は試験データ**(`backend/tests/test_sync_apply_raise_inventory.py` の `_TABLE` — 現行 204 行・現行の行番号・区分)で、pytest が AST の `raise` 文と一対一で照合する(`raise` を足す・消す・型や文言を変えるコミットは同じコミットで試験データを更新する)。この表からの差分: (a) O5 の 7 行は型が `O5InvariantViolation`(文言の前に列挙の code)/ (b) B3a の 5 行(prefix_path:444・448・450・496 / ordering:34)はステップ 5 で `P1ContentRejection` / (c) ステップ 4〜6 で 5 行を追加(11-2 の末尾)/ (d) 関数の移動: `apply.py` の :327・:413 は `apply_sync_request` → `_apply_d1_request`、`model.py` の S-1 は 4 行が `SyncRequest.__new__` → `_validate_d1_events`、2 行が `from_payload` → `_parse_d1_payload`(区分は不変)/ (e) 行番号は全ファイルで動いた。区分の判定理由は下の表のとおり。

#### apply.py(7)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| apply.py:101 | RuntimeError | 自テナントの記録権世代行が一件ではない | _preflight_d1 | 前処理 | 8 決定的・取引外 | 0 件 = 現世代(normal・未失効・未退役 — repositories/sync_apply.py:197-201)が無い永続状態で決まる。2 件以上は部分一意索引 `uq_recording_generations_current` があるので起きない。取引外なので O5 にできない。見込み: 「現世代なし」を B4 にするか O5 にするかは U-R1 が決める [推論] |
| apply.py:104 | RuntimeError | D3 の型が不正 | _preflight_d1 | 前処理 | 8 決定的・取引外 | `confirmed_watermark` は NOT NULL BIGINT(db/recording_rights/models.py:211)なので、スキーマが壊れたときだけ起きる。D3 は ACK 全体の起点なので要求単位で失敗するしかなく、取引内へ移す見込みは低い [推論] |
| apply.py:107 | RuntimeError | 記録権世代の型が不正 | _preflight_d1 | 前処理 | 8 決定的・取引外 | `generation` は NOT NULL BIGINT(同 :205)。理由は 104 と同じ |
| apply.py:127 | RuntimeError | D3 の型が不正(要求 D4 の世代) | _preflight_d1 | 前処理 | 8 決定的・取引外 | 旧 D4 の世代行の D3。理由は 104 と同じ |
| apply.py:199 | (再送出)P1PreconditionError | 区分 other かつ内容拒否でない前提違反 | _run_d1_event | 中継(元の取引は取消済み) | 8 中継 | 送出元ごとに判定する(prefix_path:592・607・655・680・444〜496、ordering:34・97、P4 経路の rejection:178〜206)。O5・B3a の写像をここで分ければよい [推論] |
| apply.py:327 | P1PreconditionError(other) | P4 は記録権不成立の経路に限る | apply_sync_request | 前処理(取引外) | 8 決定的・取引外 | 要求経路 P4 と記録権の成立(前処理で判定)だけで決まる。取引外なので O5 にできない。見込み: 4b の後は到達しなくなる(所見 7)[推論] |
| apply.py:413 | RuntimeError | 同じ一時 ID に異なる確定選手 ID がある | apply_sync_request | 確定後 | 8 決定的・確定後 | 一意制約 `uq_temporary_player_id_mappings_temporary`(db/sync_protocol/models.py:333-337)と prefix_path:680 の事前検査があるので、2 つ目の写像はできない。起きるのは保存済み結果が壊れたときだけ。確定前へは移せない(衝突は 2 件目の結果を見て初めて分かり、再掲は何も書かない)→ **O5 の対象外**。500(B7)のままにするか、到達不能の表明に留める [推論] |

#### change_path.py(21)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| change_path.py:79 | ValueError | V10 の対象参照が不正 | _target | 取引内(P3) | 4 | change_path.py:181-186 で捕まえて B14 |
| change_path.py:91 | ValueError | V10 の対象参照が不正 | _target | 取引内(P3) | 4 | 同上 → B14 |
| change_path.py:115 | RuntimeError | P3 の保存済み結果の形が不正 | _accepted_from_candidate | 取引内(P3) | 4 | 捕まえないので 500 → B10(wire 4-1)。台帳の破損で決まるが、P3 に O5 は無い(所見 6) |
| change_path.py:132 | RuntimeError | 認可後に試合行が消失した | _apply_locked | 取引内(P3) | 4 | 競合 → 500 → B10 |
| change_path.py:147 | _NoWriteResult | B9 要求作成時の復旧世代が旧世代 | _apply_locked | 取引内(P3) | 4 | :305-306 で捕まえて B9(取引を取り消してから) |
| change_path.py:155 | _D5Race | (保存済み結果・B13) | _apply_locked | 取引内(P3) | 4 | :303-304 で捕まえて、保存済み結果の再掲または B13 |
| change_path.py:158 | _NoWriteResult | B14 変更対象の試合が進行中・終了後ではない | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:170 | _NoWriteResult | B9 現在の記録権証明がない | _apply_locked | 取引内(P3) | 4 | → B9 |
| change_path.py:174 | _NoWriteResult | B14 P3 のイベント種別が不正 | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:178 | _NoWriteResult | B14 P3 の内容は JSON object が必要 | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:184 | _NoWriteResult | B14 V10 の対象参照が不正 | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:188 | _NoWriteResult | B14 V11 の期待版が不正 | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:193 | _NoWriteResult | B14 変更内容を受理できない(検証ポート) | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:201 | _NoWriteResult | B14 変更対象が存在しない | _apply_locked | 取引内(P3) | 4 | → B14 |
| change_path.py:205 | RuntimeError | event_slots の対象行が一件ではない | _apply_locked | 取引内(P3) | 4 | 主キーがあるので 2 件以上は起きない。起きれば 500 → B10 |
| change_path.py:209 | RuntimeError | 対象の確定版の型が不正 | _apply_locked | 取引内(P3) | 4 | → 500 → B10 |
| change_path.py:211 | _NoWriteResult | B8 現在版 | _apply_locked | 取引内(P3) | 4 | → B8 |
| change_path.py:245 | RuntimeError | D5 再照合が未使用に戻った | _apply_locked | 取引内(P3) | 4 | 競合 → 500 → B10 |
| change_path.py:246 | _D5Race | (先着の結果) | _apply_locked | 取引内(P3) | 4 | :303-304 で捕まえて、先着の再掲または B13 |
| change_path.py:254 | RuntimeError | 試合行ロック下で対象版の CAS が失敗 | _apply_locked | 取引内(P3) | 4 | → 500 → B10 |
| change_path.py:290 | ValueError | P3 の要求 1 件が必要 | apply_p3_change | 前処理 | 2 | S-1(model.py:183-185)と apply.py:307 が保証する呼出し規約 |

#### gate.py(5)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| gate.py:46 | RuntimeError | 認可対象の試合行が複数ある | game_accessible | 前処理(③ の非ロック読取。各イベントの前にも別の取引で読む) | 8 決定的・取引外 | games の主キーで 2 件以上は起きないはず [推論: games の主キー列は確かめていない]。取引外なので O5 にできない。到達しない前提なら移す必要も無い |
| gate.py:56 | RG1Blocked | RG1 の事前読取に失敗 | read_before_d5 | 各取引の先頭(③-a) | 7 RG1 | apply.py:320-321 で "B7"、prefix_path.py:808-809 と rejection.py:260-261 で B7、change_path.py:307-308 で B10(正本 6-2 ③-a・6-3 RG1) |
| gate.py:58 | RG1Blocked | 復元調整中 | read_before_d5 | 各取引の先頭(③-a) | 7 RG1 | 同上 |
| gate.py:66 | RG1Blocked | RG1 のコミット前読取に失敗 | check_before_commit | 取引内(⑧) | 7 RG1 | gate.py:211-212 で yield の後に投げるので取引全体が取り消される → B7/B10 |
| gate.py:68 | RG1Blocked | 復元調整中 | check_before_commit | 取引内(⑧) | 7 RG1 | 同上 |

#### idempotency.py(11)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| idempotency.py:53 | TypeError | 入力原本の JSON object のキーは文字列が必要 | _json_value | 前処理(指紋)・取引内 | 2 | 入力は freeze_json 済み(model.py:89-92 で文字列でないキーを拒否)と、固定キーの dict だけ |
| idempotency.py:59 | TypeError | 入力原本に JSON 以外の値を含められない | _json_value | 前処理・取引内 | 2 | 同上(model.py:85-93) |
| idempotency.py:105 | RuntimeError | D5 台帳の読み取り列数が正本と異なる | _stored_result | 前処理 | 2 | ORM 定義と読取文が食い違う構成の誤り。要求にも行にもよらない |
| idempotency.py:117 | RuntimeError | D5 台帳の保存結果の型が不正 | _stored_result | 前処理(apply.py:96 の全件分類で先に当たる) | 8 決定的・取引外 | 台帳行が壊れていれば決まる(result は NOT NULL JSONB だが object とは限らない)。見込み: 分類で「破損」候補を返し、イベントの取引内で O5 にすれば移せる。ただし所見 2 の再掲系 [推論] |
| idempotency.py:128 | ValueError | 未知の適用経路 | classify_result | 前処理 | 2 | 経路は S-1(model.py:175-176)と呼出し元の定数が保証する |
| idempotency.py:132 | RuntimeError | 同じテナントと D5 に複数の台帳行がある | classify_result | 前処理 | 8 決定的・取引外 | 主キー `pk_idempotency_ledger`(tenant_id, d5)(db/sync_protocol/models.py:369-374)があるので起きない。到達しない前提なら移す必要も無い |
| idempotency.py:159 | ValueError | D5 指紋の件数がイベント列と異なる | classify_request_d5 | 前処理 | 2 | 呼出し元 apply.py:90-96 が同じイベント列から作る |
| idempotency.py:195 | (再送出)IntegrityError | D5 以外の一意制約などの違反 | insert_result_or_recheck | 取引内 | 8 B7 | DB 由来。CHECK 違反のような決定的なものも混ざりうるが区別できないので、安全側で B7 [推論] |
| idempotency.py:198 | RuntimeError | D5 一意制約違反後に先着行を観測できない | insert_result_or_recheck | 取引内 | 8 B7 | 競合直後の可視性の問題で、再送で通りうる |
| idempotency.py:250 | RuntimeError | 拒否・退避以外の保存済み結果 | decode_stored_negative | 取引内(rejection.py:88 から) | 8 B7 | kind は CHECK で 3 値(models.py:368)。起きるのは T8/T9 経路で、同じ指紋の D5 が「受理」済みになっていたとき = 前段の取引の後に並行要求が受理した競合 [推論] |
| idempotency.py:261 | RuntimeError | 拒否・退避の保存済み結果の形が不正 | decode_stored_negative | 取引内(書き込み前) | 8 再掲の破損(B7 のまま — 11-1) | 保存済み結果 JSON の破損で決まる。所見 2(再掲系) |

#### intent_ids.py(1)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| intent_ids.py:20 | ValueError | 同期意図にはイベント識別と既知の範囲が必要 | derive_sync_intent_id | 取引内(意図記録)・token 構築時 | 2 | 呼出し元は固定の範囲集合(SCOPE_KIND_BY_SCOPE)と D5 などの識別文字列だけを渡す(invalidation.py:53-54・tokens.py:265) |

#### invalidation.py(13)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| invalidation.py:70 | (再送出)IntegrityError | 意図の主キー以外の制約違反 | _record_intents | 取引内(prefix_path.py:744 — D3 を進めたイベントの取引) | 8 B7 | DB 由来 |
| invalidation.py:72 | RuntimeError | 意図の一意制約違反後に先着行を観測できない | _record_intents | 取引内 | 8 B7 | 競合直後の可視性 |
| invalidation.py:116 | ValueError | P3 の V10 と対象確定版が必要 | record_p3_intents | 取引内(P3) | 2 | 呼出し元 change_path.py:273 は _target で検証済みの値と v11+1 を渡す |
| invalidation.py:137 | ValueError | D1 付き経路には試合 ID と D5 が必要 | record_d1_intents | 取引内 | 2 | 呼出し元 prefix_path.py:744 は UUID を渡す |
| invalidation.py:145 | RuntimeError | 意図行の {column} の型が不正 | _optional_uuid | 適用外(配信) | 1 | deliver_pending_sync_intents だけが使う |
| invalidation.py:158 | RuntimeError | 意図 ID または範囲の型が不正 | _delivery_intent | 適用外(配信) | 1 | 同上 |
| invalidation.py:160 | RuntimeError | 意図行の chart_kind の型が不正 | _delivery_intent | 適用外(配信) | 1 | 同上 |
| invalidation.py:187 | ValueError | 配信ページの上限は 1〜100 | deliver_pending_sync_intents | 適用外(配信) | 1 | 配信の入口 |
| invalidation.py:204 | RuntimeError | 意図行の列数が正本と異なる | deliver_pending_sync_intents | 適用外(配信) | 1 | 配信経路 |
| invalidation.py:208 | RuntimeError | 意図 ID または範囲の型が不正 | deliver_pending_sync_intents | 適用外(配信) | 1 | 配信経路 |
| invalidation.py:213 | RuntimeError | 同期意図 ID と範囲が一致しない | deliver_pending_sync_intents | 適用外(配信) | 1 | 配信経路 |
| invalidation.py:237 | RuntimeError | 配信完了を記録した意図行を再読できない | deliver_pending_sync_intents | 適用外(配信) | 1 | 配信経路 |
| invalidation.py:241 | RuntimeError | 配信完了の状態が永続化されていない | deliver_pending_sync_intents | 適用外(配信) | 1 | 配信経路 |

#### model.py(22)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| model.py:79 | RequestShapeError | S-1: JSON object またはキーの外形が不正 | _object_with_keys | 前処理(HTTP 入口の from_payload) | 3 | wire 設計 2-4「S-1 違反は境界結果ではない」(sync-wire-schema/design.md:107)・型の docstring(model.py:57)・422(同 :276) |
| model.py:91 | TypeError | JSON object のキーは文字列が必要 | freeze_json | 前処理 | 2 | JSON の解析結果のキーは常に文字列。直接構築を誤ったときだけ起きる |
| model.py:93 | TypeError | JSON に含められない値 | freeze_json | 前処理 | 2 | 同上 |
| model.py:135 | RequestShapeError | S-1: D5 または試合 ID が UUID 正規形ではない | SyncEvent.__new__ | 前処理 | 3 | 同上(design.md:100 の ②⑥) |
| model.py:176 | RequestShapeError | S-1: 未知の適用経路 | SyncRequest.__new__ | 前処理 | 3 | 同上 |
| model.py:178 | RequestShapeError | S-1: 試合 ID が UUID 正規形ではない | SyncRequest.__new__ | 前処理 | 3 | 同上 |
| model.py:182 | RequestShapeError | S-1: イベント列の外形が不正 | SyncRequest.__new__ | 前処理 | 3 | 同上 |
| model.py:185 | RequestShapeError | S-1: P3 は変更イベント 1 件が必要 | SyncRequest.__new__ | 前処理 | 3 | 同上 |
| model.py:187 | RequestShapeError | S-1: P3 の復旧世代がないか型が不正 | SyncRequest.__new__ | 前処理 | 3 | 同上(④) |
| model.py:194 | RequestShapeError | S-1: P3 に D1・D4・V6・V8・V9 を指定できない | SyncRequest.__new__ | 前処理 | 3 | 同上(design.md:242) |
| model.py:197 | RequestShapeError | S-1: D1 付き経路のイベント列は空にできない | SyncRequest.__new__ | 前処理 | 3 | 同上(design.md:196) |
| model.py:201 | RequestShapeError | S-1: D1 付き経路に復旧世代・V11 を指定できない | SyncRequest.__new__ | 前処理 | 3 | 同上(design.md:208) |
| model.py:205 | RequestShapeError | S-1: D1 付き経路の D4 がないか型が不正 | SyncRequest.__new__ | 前処理 | 3 | 同上(③) |
| model.py:212 | RequestShapeError | S-1: D1 または要求内 D4 が不正 | SyncRequest.__new__ | 前処理 | 3 | 同上(⑦⑧) |
| model.py:215 | RequestShapeError | S-1: D1 が重複している | SyncRequest.__new__ | 前処理 | 3 | 同上(⑧) |
| model.py:217 | RequestShapeError | S-1: 試合 ID がイベント列と一致しない | SyncRequest.__new__ | 前処理 | 3 | 同上(design.md:211) |
| model.py:254 | RequestShapeError | S-1: 変更イベントの識別がない | from_payload | 前処理 | 3 | 同上 |
| model.py:277 | RequestShapeError | S-1: イベント列は空でない JSON array が必要 | from_payload | 前処理 | 3 | 同上(⑤) |
| model.py:296 | RequestShapeError | S-1: イベントの識別がない | from_payload | 前処理 | 3 | 同上 |
| model.py:393 | ValueError | 変更受理には I6 の対象参照と確定時刻が必要 | AcceptedChangeResult.__new__ | 取引内(P3) | 4 | change_path.py:116 で、保存済み結果の target_reference のキーが壊れていると起きる → 500 → B10。新規受理(:221)は固定キーなので起きない |
| model.py:395 | ValueError | 変更受理には期待版と確定内容が必要 | AcceptedChangeResult.__new__ | 取引内(P3) | 2 | 呼出し元は int と Mapping だけを渡す(change_path.py:109-116・221-223) |
| model.py:420 | ValueError | P3 の拒否結果には B8〜B14 が必要 | RejectedChangeResult.__post_init__ | 取引内(P3) | 2 | 呼出し元は固定リテラルだけ |

#### ordering.py(4)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| ordering.py:34 | P1PreconditionError(other) | P2 の V6 は非負の bigint が必要 | _assign_d2 | 取引内(T5 — prefix_path.py:662) | 8 B3a | V6 が上限を超えるのは端末が送った内容で決まる(⑦ の射程)。⑦ の try(prefix_path.py:612-639)の外で投げるので、いまは apply.py:199 から 500 |
| ordering.py:49 | RuntimeError | D2 順の行の型が不正 | _assign_d2 | 取引内 | 8 O5 | 読取は `d2 > after_d2` で NULL を除き(repositories/sync_apply.py:210-215)、id は NOT NULL。スキーマが壊れたときだけ起きる。永続状態で決まる |
| ordering.py:51 | RuntimeError | 永続化済み D2 が bigint の値域外 | _assign_d2 | 取引内 | 8 O5 | 負の D2 が永続化されていれば毎回同じように失敗する(BIGINT なので上限を超える値は入らない)。D2 ≥ 0 の CHECK があるかは確かめていない [推論] |
| ordering.py:97 | P1PreconditionError(other) | D2 の局所再採番に必要な隙間がない | _assign_d2 | 取引内 | 8 O5 | 永続化済み D2 の並び(両側とも bigint の端まで連続)で決まる。V6 は端末の論理位置なので、編集しても解けない(内容の問題ではない)[推論]。いまは 500 |

#### port_guard.py(25)

すべて **区分 2**。登録表と import 閉包の検査で、要求の内容にはよらない。`require_registered_port` から呼ばれるので、発生位置は**呼出し時**(前処理の gate.py:182、取引内の prefix_path.py:595・change_path.py:138・rejection.py:179、配信の invalidation.py:188)。`validate_port_source` は合成ソース用(試験)。

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| port_guard.py:249 | PortRegistrationError | ポート実装のソースがない(pitchlog 内) | _module_file | 呼出し時 | 2 | 登録の構成 |
| port_guard.py:256 | PortRegistrationError | ポート実装のソースを解決できない | _module_file | 呼出し時 | 2 | 同上 |
| port_guard.py:260 | PortRegistrationError | ポート実装の Python ソースがない | _module_file | 呼出し時 | 2 | 同上 |
| port_guard.py:263 | PortRegistrationError | ポート実装のソースがない(ファイル無し) | _module_file | 呼出し時 | 2 | 同上 |
| port_guard.py:296 | PortRegistrationError | 禁止された標準ライブラリ名 | _validate_standard_symbols | 呼出し時 | 2 | ポート実装のソース検査 |
| port_guard.py:313 | PortRegistrationError | 禁止された getattr | _validate_standard_symbols | 呼出し時 | 2 | 同上 |
| port_guard.py:317 | PortRegistrationError | getattr の別名化は禁止 | _validate_standard_symbols | 呼出し時 | 2 | 同上 |
| port_guard.py:331 | PortRegistrationError | 標準モジュールの受け渡しは禁止 | _validate_standard_symbols | 呼出し時 | 2 | 同上 |
| port_guard.py:347 | PortRegistrationError | 禁止名を参照するポート実装 | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:357 | PortRegistrationError | 禁止属性を参照するポート実装 | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:363 | PortRegistrationError | Pitchlog モジュールのオブジェクト import は禁止(import 文) | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:379 | PortRegistrationError | 相対 import を解決できない | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:385 | PortRegistrationError | Pitchlog のルートからの import は禁止 | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:392 | PortRegistrationError | Pitchlog モジュールのオブジェクト import は禁止(from 文) | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:397 | PortRegistrationError | Pitchlog の非モジュール名と確認できないため import 禁止 | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:402 | PortRegistrationError | 禁止 import 属性を含むポート実装 | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:408 | PortRegistrationError | 禁止された標準ライブラリ名(from 文) | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:420 | PortRegistrationError | 書き手の発行情報を参照するポート実装 | _imported_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:437 | PortRegistrationError | 禁止 import を含むポート実装(禁止モジュール) | _validate_source | 呼出し時 | 2 | 同上 |
| port_guard.py:440 | PortRegistrationError | ソースのない import | _validate_source | 呼出し時 | 2 | 同上 |
| port_guard.py:442 | PortRegistrationError | 禁止 import を含むポート実装(許可外の標準) | _validate_source | 呼出し時 | 2 | 同上 |
| port_guard.py:451 | PortRegistrationError | ポート実装の構文を検査できない | validate_port_source | 定義時(合成ソースの検査 — 試験用) | 2 | 同上 |
| port_guard.py:472 | PortRegistrationError | ポート実装のソースを検査できない | validate_port_modules | 呼出し時 | 2 | 同上 |
| port_guard.py:490 | PortRegistrationError | 登録モジュールが読み込まれていない | require_registered_port | 呼出し時 | 2 | 登録の構成 |
| port_guard.py:496 | PortRegistrationError | 未登録のポート実装 | require_registered_port | 呼出し時 | 2 | 登録表が空(ports.py:134)なので、**いまは全要求でここに当たる**(所見 1) |

#### ports.py(4)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| ports.py:41 | PermissionError | PortWriter は適用核だけが発行できる | PortWriter.__init__ | 書き手の発行時 | 2 | 発行は _issue_port_writer に限る(ports.py:58-62)。プログラムの誤り |
| ports.py:48 | RuntimeError | PortWriter のトランザクションは閉じている | PortWriter.run | 呼出し時 | 2 | ポート実装が閉じた書き手を使う誤用 |
| ports.py:50 | TypeError | PortWriter は operation token だけを受け付ける | PortWriter.run | 呼出し時 | 2 | ポート実装の誤用 |
| ports.py:142 | PortRegistrationError | ポート登録検査器が未接続 | require_registered_port | 呼出し時 | 2 | 検査器は port_guard の import で接続される(port_guard.py:500) |

#### prefix_path.py(63)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| prefix_path.py:170 | RuntimeError | 同期表の読み取り列数が正本と異なる | _cell | 前処理・取引内 | 2 | ORM 定義と読取文が食い違う構成の誤り |
| prefix_path.py:177 | RuntimeError | {table} の対象行が一件ではない | _one_row | 取引内 | 8 B7 | D1 経路では記録権世代行(:881・:887)。0 件の条件は前処理の apply.py:100-101 が同じ token で先に調べているので、取引内で初めて起きるのは前処理の後に現世代が消えた競合 [推論]。一時写像(:456)は一意制約で起きない。games(change_path)は区分 4 の意味 |
| prefix_path.py:184 | P1PreconditionError(other) | P1 の V7 は JSON object が必要 | _json_object | 取引内(⑦ の try — :622・:623) | 7 B3a | ⑦ の try が other を P1ContentRejection に変え(:636-638)、apply.py:183-197 が T9 → B3a。:695 の呼び出しは検証済みの値なので投げない |
| prefix_path.py:205 | P1PreconditionError(other) | V9 の置換種別と拒否原本 D5 が不正 | _replacement_state | 取引内(⑦ の try — :613) | 7 B3a | 同上 |
| prefix_path.py:208 | P1PreconditionError(other) | V9 の置換種別が不正 | _replacement_state | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:213 | P1PreconditionError(other) | V9 の拒否原本 D5 が不正 | _replacement_state | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:219 | P1PreconditionError(other) | V9 の拒否原本 D5 が不正 | _replacement_state | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:230 | P1PreconditionError(other) | P1 の V5 は D1 付きイベント種別が必要 | _event_kind | 取引内(⑦ の try — :618 ほか) | 7 B3a | 同上。try の外の呼び出し(:689・:719)は検証済みの値なので投げない |
| prefix_path.py:238 | P1PreconditionError(w2_violation) | 墓標・改訂には V10 の対象参照が必要 | _replacement_target | 取引内 | 7 B3a | w2 は :639 で再送出、または :641 から上がり、apply.py:183 で T9(cause w2_violation)→ B3a |
| prefix_path.py:247 | P1PreconditionError(w2_violation) | V10 が置換する D1 と一致しない | _replacement_target | 取引内 | 7 B3a | 同上 |
| prefix_path.py:261 | P1PreconditionError(w2_violation) | 対応する内容拒否の D5 がない | _require_rejected_original | 取引内(:641) | 7 B3a | 同上 |
| prefix_path.py:264 | P1PreconditionError(w2_violation) | 対応する内容拒否原本がない | _require_rejected_original | 取引内 | 7 B3a | 同上 |
| prefix_path.py:275 | P1PreconditionError(w2_violation) | 内容拒否原本の D1 が置換対象と一致しない | _require_rejected_original | 取引内 | 7 B3a | 同上 |
| prefix_path.py:283 | P1PreconditionError(w2_violation) | V10 が内容拒否原本と一致しない | _require_rejected_original | 取引内 | 7 B3a | 同上 |
| prefix_path.py:285 | P1PreconditionError(w2_violation) | 改訂版は拒否原本の参加区分を継承する | _require_rejected_original | 取引内 | 7 B3a | 同上 |
| prefix_path.py:290 | P1PreconditionError(w2_violation) | 改訂版は拒否原本の D2 を継承する | _require_rejected_original | 取引内 | 7 B3a | 同上 |
| prefix_path.py:296 | P1PreconditionError(w2_violation) | 内容拒否原本と D5 台帳の指紋が一致しない | _require_rejected_original | 取引内 | 7 B3a | 同上 |
| prefix_path.py:305 | P1PreconditionError(other) | 墓標は D2 を持たない | _d2 | 取引内(⑦ の try — :619) | 7 B3a | ⑦ の try → B3a |
| prefix_path.py:311 | P1PreconditionError(other) | このイベント種別には D2 が必要 | _d2 | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:313 | P1PreconditionError(other) | このイベント種別は D2 を持たない | _d2 | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:317 | P1PreconditionError(other) | P1 の D2 が不正 | _d2 | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:325 | P1PreconditionError(other) | 墓標は V8 を持たない | _state_diff | 取引内(⑦ の try — :623) | 7 B3a | 同上 |
| prefix_path.py:331 | P1PreconditionError(other) | このイベント種別には V8 の状態差分が必要 | _state_diff | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:333 | P1PreconditionError(other) | このイベント種別は V8 の状態差分を持たない | _state_diff | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:345 | RuntimeError | P1 の V11 種別条件が未対応 | _validate_v11 | 取引内 | 2 | C12 の表では D1 付きの 7 種別とも V11 は「禁止」(event_kinds.py の C12_REQUIREMENT_MATRIX を読取専用で出力して確かめた)。表の定義が変わったときだけ起きる |
| prefix_path.py:347 | P1PreconditionError(other) | P1 のイベント種別は V11 を持たない | _validate_v11 | 取引内(⑦ の try — :624) | 7 B3a | ⑦ の try → B3a(S-1 も V11 を拒否する — model.py:198-203) |
| prefix_path.py:356 | P1PreconditionError(other) | 墓標・改訂には undo の対象を指定できない | _validate_v10 | 取引内(⑦ の try — :625) | 7 B3a | 同上 |
| prefix_path.py:361 | P1PreconditionError(other) | このイベント種別は V10 の対象を持たない | _validate_v10 | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:374 | P1PreconditionError(other) | undo の V10 と照合済み対象が一致しない | _validate_v10 | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:408 | RuntimeError | P1 の保存済み結果が受理ではない | _stored_result | 取引内 | 2 | 呼び出しは kind == "accepted" のときだけ(:860-861)。構築上の不変条件 |
| prefix_path.py:418 | RuntimeError | P1 の保存済み結果の形が不正 | _stored_result | 取引内(:582 — 書き込み前) | 8 再掲の破損(B7 のまま — 11-1) | 保存済み結果 JSON の破損で決まる。所見 2(再掲系) |
| prefix_path.py:422 | RuntimeError | P1 の保存済み写像の形が不正 | _stored_result | 取引内(書き込み前) | 8 再掲の破損(B7 のまま — 11-1) | 同上 |
| prefix_path.py:444 | P1PreconditionError(other) | 選手参照は UUID 文字列が必要 | _resolve_player_reference | 取引内(:689 — ⑦ の try の外) | 8 B3a | V7 の選手参照の内容で決まる(⑦ の射程)。try の外なので、いまは 500 |
| prefix_path.py:448 | P1PreconditionError(other) | 選手参照は UUID 文字列が必要 | _resolve_player_reference | 取引内 | 8 B3a | 同上 |
| prefix_path.py:450 | P1PreconditionError(other) | 選手参照は正規 UUID が必要 | _resolve_player_reference | 取引内 | 8 B3a | 同上 |
| prefix_path.py:459 | RuntimeError | 正式選手 ID の型が不正 | _resolve_player_reference | 取引内 | 8 O5 | player_id は NOT NULL Uuid(models.py:341)。スキーマが壊れたときだけ起きる |
| prefix_path.py:470 | P1PreconditionError(other) | 一時選手 ID の確定写像がない | _resolve_player_reference | 取引内 | 8 B7(状態依存 — 11-1) | 選手行・一時 ID の写像の有無という永続状態で結果が変わる(同じ参照でも、先行するその場登録が確定すれば通る)ので、内容だけでは決まらない — ステップ 5 で判明。B7 のまま |
| prefix_path.py:496 | P1PreconditionError(other) | V5 で定義されない選手参照位置 | _resolve_payload | 取引内 | 8 B3a | V7 の形で決まる |
| prefix_path.py:549 | RuntimeError | 認可後に試合行が消失した | _apply_locked | 取引内 | 8 B7 | 指定例。③ の後に状態が変わった競合 |
| prefix_path.py:592 | P1PreconditionError(other) | D1 付き経路には D1 と D4 が必要 | _apply_locked | 取引内 | 2 | S-1(model.py:204-212)が保証する。プログラムの誤りでだけ起きる |
| prefix_path.py:601 | P1PreconditionError(recording_rights) | P1 の記録権不一致は退避経路へ渡す | _apply_locked | 取引内 | 7 B4 | apply.py:173-182 で T8 → B4(A5 退避) |
| prefix_path.py:607 | P1PreconditionError(w2 / other) | 確定済み D1 は墓標・改訂で置換できない | _apply_locked | 取引内 | 8 確定スロットの食い違い(要決定 — 11-1) | V9 がある(w2)なら B3a。V9 が無い(other)なら、未使用 D5 なのに D1 ≤ D3 = 端末とサーバーで D1 の確定状態が食い違う不変条件違反 [推論]。所見 3・4 |
| prefix_path.py:617 | P1PreconditionError(other) | P2 は論理位置を持つイベント種別だけを受ける | _apply_locked | 取引内(⑦ の try) | 7 B3a | ⑦ の try → B3a |
| prefix_path.py:621 | P1PreconditionError(other) | P2 には論理位置 V6 が必要 | _apply_locked | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:627 | P1PreconditionError(other) | 墓標の payload は空 object が必要 | _apply_locked | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:629 | P1PreconditionError(other) | その場登録には選手作成値が必要 | _apply_locked | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:631 | P1PreconditionError(other) | 選手作成値はその場登録だけに使える | _apply_locked | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:635 | P1PreconditionError(other) | その場登録の V7 に一時選手 ID がない | _apply_locked | 取引内(⑦ の try) | 7 B3a | 同上 |
| prefix_path.py:638 | P1ContentRejection | (other の前提違反の文言) | _apply_locked | 取引内 | 5 | apply.py:183 で捕まえて T9 → **B3a** |
| prefix_path.py:639 | (再送出)P1PreconditionError | (w2_violation) | _apply_locked | 取引内 | 5 | try 内で other 以外に投げるのは w2 だけ(:238・:247)。apply.py:183 で T9 → **B3a** |
| prefix_path.py:644 | P1ContentRejection | 検証ポートの理由 / P1 の内容拒否は T9 へ渡す | _apply_locked | 取引内 | 5 | apply.py:183 で T9 → **B3a** |
| prefix_path.py:651 | RuntimeError | D1 に複数の現行行がある | _apply_locked | 取引内 | 8 O5 | スロットの主キーと `uq_operation_events_active_slot`(models.py:222-231)で起きないはず。起きれば永続状態の不変条件違反 |
| prefix_path.py:653 | RuntimeError | 現行イベントのスロットがない | _apply_locked | 取引内 | 8 O5 | イベント行があってスロット行が無い永続状態で決まる |
| prefix_path.py:655 | P1PreconditionError(w2 / other) | 確定済みイベントは墓標・改訂で置換できない | _apply_locked | 取引内 | 8 確定スロットの食い違い(要決定 — 11-1) | V9 の原本がある(w2)なら B3a。無い(other)なら、D3+1 にスロットかイベントが既にある = D3 と保存行が食い違う不変条件違反 [推論]。所見 3・4 |
| prefix_path.py:664 | _NoWriteStop | O4: 永続化済み D2 の同値 | _apply_locked | 取引内 | 6 | :812-813 で捕まえ、取り消してから B3 + A5 拒否(apply.py:427 で b3_branch "O4")。内部制御でもあるが、O4 を運ぶので区分 6 |
| prefix_path.py:680 | P1PreconditionError(other) | 一時 ID は別の確定写像に使用済み | _apply_locked | 取引内 | 8 B7(状態依存 — 11-1) | 既存の一時 ID の写像という永続状態で結果が変わるので、内容だけでは決まらない — ステップ 5 で判明。B7 のまま |
| prefix_path.py:710 | RuntimeError | D5 再照合が未使用に戻った | _apply_locked | 取引内 | 8 B7 | 指定例(競合) |
| prefix_path.py:711 | _D5Race | (先着の結果) | _apply_locked | 取引内 | 5 | :810-811 で捕まえ、取り消してから先着の保存済み結果(再掲)または B3b |
| prefix_path.py:729 | RuntimeError | D3 の前進に失敗 | _apply_locked | 取引内 | 8 O5 | 世代行は :887 で FOR UPDATE 済みなので、並行更新では起きない。起きれば構成か永続状態の異常で、毎回同じに失敗する [推論] |
| prefix_path.py:851 | P1PreconditionError(w2_violation) | T9 原本の指紋が不正 | _original_fingerprint | 取引内(:293) | 7 B3a | w2 → apply.py:183 → T9 → B3a |
| prefix_path.py:859 | RuntimeError | P1 の保存済み結果がない | _replay_saved_result | 取引内 | 2 | kind="stored_result" の候補は必ず stored を持つ(idempotency.py:135)。構築上の不変条件 |
| prefix_path.py:886 | RuntimeError | 記録権世代の型が不正 | _lock_game_generation | 取引内 | 8 再照合前(B7 のまま — 11-1) | NOT NULL BIGINT(スキーマが壊れたときだけ)。前処理の apply.py:107 が同じ行を先に調べる |
| prefix_path.py:893 | RuntimeError | D3 の型が不正 | _lock_game_generation | 取引内 | 8 再照合前(B7 のまま — 11-1) | 同上(apply.py:104) |

#### rejection.py(13)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| rejection.py:75 | ValueError | 内容拒否以外を T9 に記録できない | content_reason_for_precondition | 取引外(例外処理の中) | 2 | 呼出し元 apply.py:183 が同じ条件を先に判定する |
| rejection.py:87 | RuntimeError | 拒否・退避以外の保存済み結果は元の適用経路で再掲する | _candidate_result | 取引内 | 2 | kind="stored_result" は必ず stored を持つ(idempotency.py:135)。構築上の不変条件 |
| rejection.py:130 | RuntimeError | D5 再照合が未使用に戻った | _commit_result | 取引内 | 8 B7 | 指定例(競合) |
| rejection.py:131 | _RaceReplay | (先着の結果) | _commit_result | 取引内 | 5 | :262-263 で捕まえ、取り消してから先着の再掲または B3b |
| rejection.py:140 | RuntimeError | 退避原本の世代または D1 がない | _commit_result | 取引内 | 2 | evacuated の呼び出し(:190-198)は必ず old_generation を渡し、D1 は :177 で確かめ済み |
| rejection.py:169 | RuntimeError | 認可後に試合行が消失した | _apply_locked | 取引内 | 8 B7 | 競合 |
| rejection.py:178 | P1PreconditionError(other) | D1 付き経路には D1 と D4 が必要 | _apply_locked | 取引内 | 2 | S-1 が保証する(prefix_path:592 と同じ) |
| rejection.py:187 | P1PreconditionError(other) | 退避する旧 D4 の世代番号が不正(int 変換失敗) | _apply_locked | 取引内(T8) | 8 U-R1 待ち(B7 のまま — 11-1) | D4 の値で決まる。記録権が成立しないのに、退避先の bigint 列へ入れられない [推論]。所見 5(U-R1 待ち) |
| rejection.py:189 | P1PreconditionError(other) | 退避する旧 D4 の世代番号が不正(≦0・非正規表記) | _apply_locked | 取引内(T8) | 8 U-R1 待ち(B7 のまま — 11-1) | 同上 |
| rejection.py:200 | P1PreconditionError(other) | 記録権が成立するイベントは内容拒否の理由が必要 | _apply_locked | 取引内 | 8 B7 | reason=None で呼ぶのは記録権が成立しない前提の経路(P4・apply.py:174・_escrow_without_right)。ここで成立しているのは、前段の判定の後に記録権が移った競合 [推論]。P4 で最初から成立しているなら apply.py:327 が前処理で止める |
| rejection.py:204 | P1PreconditionError(other) | 確定済み D1 は内容拒否原本にできない | _apply_locked | 取引内 | 8 B7 | P1 経路は D1 ≤ D3 を prefix_path.py:606-610 で先に止めるので、ここに来るのは P1 の取引の後に D3 が進んだ競合 [推論] |
| rejection.py:206 | P1PreconditionError(other) | 内容拒否の理由が空 | _apply_locked | 取引内 | 2 | 理由は空でない固定文言(str(error))か `reason or 既定文言`(prefix_path.py:644)なので空にならない |
| rejection.py:239 | ValueError | P4 はその場登録を持たない | apply_rejection_or_escrow | 取引外(入口) | 2 | 呼出し規約の違反(P4 の要求に registrations を渡すのは入口の誤り)。apply.py:231-236・259-267 は P4 でも registration を渡しうる |

#### tokens.py(4)

| ファイル:行 | 型 | メッセージ | 関数 | 発生位置 | 区分 | 判定理由 |
| --- | --- | --- | --- | --- | --- | --- |
| tokens.py:247 | ValueError | 意図 ID のカーソルは文字列が必要 | InvalidationIntentPendingToken.__post_init__ | 適用外(配信) | 1 | 構築は invalidation.py:196(配信経路)だけ(grep で確かめた) |
| tokens.py:268 | ValueError | 試合範囲には試合 ID が必要 | SyncInvalidationIntentInsertToken.validate | 取引内(token 構築)・準備時 | 2 | 範囲は SCOPE_KIND_BY_SCOPE の固定集合。game_id は呼出し元が範囲に合わせて渡す(invalidation.py:61-65) |
| tokens.py:271 | ValueError | 広域範囲に試合 ID を指定できない | 同上 | 同上 | 2 | 同上 |
| tokens.py:273 | ValueError | 共有集計には専用 token が必要 | 同上 | 同上 | 2 | 同上(共有集計は :59 で専用 token) |

## 12. T1/T2 の投影・検証 Port の公開境界(U-X1 P-7 の受理 — 2026-10-17)

ADR-003 v0.8 の D-14-m(T1 状況判定・T2 終了判定に限る発効前の経過措置)を受け、U-X1 の計画(`fix/ux1-state-calc` `7e047f4e` の design.md:75 P-7)が U-S1 に求める 3 点を、既存のコードと本書の記述から名指しする。**新しい設計はしない**。実値の試験は着手条件に置かない(D-14-m)。実接合の試験は U-X1 の PR-1 のマージ前に関係担当と行う(U-X1 plan.md:87)。仮の Port と別計算は置かない。

### 12-1. 公開署名

| 項目 | 契約(典拠) |
| --- | --- |
| 入口 | E-1 = `apply_sync_events(context, batch, rights, projection, validator, *, registrations=None, targets=None)`(`sync/apply.py:396` — 2 節)/ E-2 の P3 と経路を明示する既存の呼び出し = `apply_sync_request(context, request, rights, projection, validator, *, registrations=None, targets=None)`(`sync/apply.py:364`)。どちらも **4 番目の位置引数 `projection`・5 番目の `validator`** で Port を受ける。呼出側(506)が実装のインスタンスを渡す |
| 投影 Port | `projection: ProjectionPort` — `apply(event: SyncEvent, writer: PortWriter) -> None`(`sync/ports.py:87-92`)。戻り値なし |
| 検証 Port | `validator: ContentValidationPort` — `validate(event: SyncEvent, writer: PortWriter) -> tuple[bool, str \| None]`(`sync/ports.py:95-102`)。受理なら `(True, None)`、受理しないなら `(False, 理由)` |
| 呼ぶ位置(D1 付き経路 — P1/P2 共通) | 検証: ⑤ 記録権・⑥ 連番・U-S1 自身の外形と内容の検査を通った後、スロット読取の前(`sync/prefix_path.py:642`)。投影: T2(イベント行の挿入)・T3(D3 の前進)の後、同じ取引の中(`sync/prefix_path.py:731`)。投影へ渡すのは墓標・改訂を置き換えた後のイベント |
| 呼ぶ位置(P3) | 検証: ⑥(`sync/change_path.py:191`)。投影: T2 の後(`sync/change_path.py:271`) |
| 取引と書き込み | Port は `PortWriter` だけを受け取り、`run(operation token)` で U-S1 の同じ取引の中で書く(`sync/ports.py:29-51`)。Session・SQL 文・取引の開閉を持たない。取引を開くのは U-S1(1 節)。取引が閉じた後の `run` は失敗する |
| 登録の検査 | 3 Port は、どれかを呼ぶ前に登録済みのクラスかを照合する(`sync/prefix_path.py:594-595`)。照合は「登録表 `PORT_IMPLEMENTATIONS` の `(モジュール名, クラス名)` のクラスと型が同一」かどうか(`sync/port_guard.py:484-497`)。あわせて、登録モジュールと、その推移的な pitchlog の import が静的検査を通ることを確かめる(`sync/port_guard.py:455-481` — 標準ライブラリは名前ごとの許可表 `:21-40`)。**U-X1 の Port のモジュールと、それが import する計算核も、この許可表の範囲で書く必要がある** |

### 12-2. 失敗境界

| Port の結果 | 境界結果 | 取引 | 恒久 / 再試行 |
| --- | --- | --- | --- |
| 検証が `(False, 理由)`(D1 付き経路) | **B3a**(内容拒否)。A5 は拒否、原本を T9 に記録(`sync/prefix_path.py:643-644` → `P1ContentRejection`) | 当該イベントの T2 以降は書かない。前方の確定は残る | 恒久。自動再送を止め、要操作(改訂待ち / 墓標待ち)へ(4 節) |
| 検証が `(False, 理由)`(P3) | **B14**(書き込みなし — `sync/change_path.py:192-197`) | 書き込みなし | 恒久 |
| 検証・投影が例外を投げる | **B7**(未捕捉 → 500。ACK なし — 3-2 節) | **当該イベントの取引を全取消**。前方の確定は残る(イベント 1 件ごとの原子性 — 1 節) | 一時。未送信のまま自動再送し、再送で通り得る |
| 登録されていない実装を渡す | **B7**(`PortRegistrationError` — 3-2 節) | どの Port も呼ばない | 構成の誤り |

- **恒久の拒否は、例外ではなく検証の `(False, 理由)` で返す**。ステップ 8(D-4)で入れた O5 は U-S1 自身の決定的な不変条件違反に限り(11-1 節)、Port の例外を O5 には寄せない。機構: D1 付き経路の 3 Port の呼び出しは `sync/prefix_path.py` の `_call_port` を通り、Port から抜けた O5 の型(`O5InvariantViolation`)は `RuntimeError` に包み直して B7 にする。O5 の型の部分型は作らない(試験で固定)。
- **投影 Port には拒否の口がない**。投影が例外を投げると毎回 B7 になり、再送しても通らないまま Q8 で顕在化する。よって、**検証を通ったイベントで投影が決定的に失敗しないことを、投影 Port の契約とする**。内容の可否の判定は検証 Port に寄せる。

### 12-3. 配線担当

- **U-S1 が持つ**(`sync/ports.py` — 9 節。core-areas の sync-protocol に属し、登録表の変更は敵対レビューと人間の逐行確認を受ける — `sync/ports.py:1-7`)。
- **残る配線は登録表 `PORT_IMPLEMENTATIONS` への 1 行の追加だけ**(Port 1 本につき `(モジュール名, クラス名)` 1 組)。検査器 `_PORT_VERIFIER` は `port_guard` の import 時に接続済み(`sync/port_guard.py:500`)で、入口のモジュールはすべて `port_guard` を import している。1-2 節と 9 節の「検査器も未接続」は不正確だったので、本日訂正した(正しくは「登録表が空なので、どの実装も照合を通らない」)。
- Port の実装クラス(投影・検証の T1/T2 部分)は U-X1 が書く。登録の 1 行は U-S1 が書く。
- **登録は Port ごとに独立して積める**(型の同一性で 1 本ずつ照合する — `sync/port_guard.py:487-495`)。1 球保存の経路(D1 付き・P3)が要求するのは **記録権・投影・検証の 3 本**で、どれかを呼ぶ前に 3 本とも照合する(`sync/prefix_path.py:594-595`・`sync/change_path.py:137-138`)。無効化の配信先 `InvalidationSinkPort` は配信の経路だけで照合し(`sync/invalidation.py:188`)、1 球保存の経路には乗らない。よって **T1/T2 の投影・検証を先に登録してよいが、それだけでは経路は開かない**。記録権 Port(U-R1)が未登録の間は入口が B7 で止まり、部分的な登録で経路が中途半端に開くことはない。
- **9 節の「4 Port と配信の実行主体が揃ってから」は機構上の条件ではない**(上記)。残るのは製品としての判断で、**PO 判断**とする: 配信の実行主体がないまま 1 球保存を開くと、T7 の無効化意図は記録されるが配信されず溜まる(`deliver_pending_sync_intents` の製品の呼び出し元は 0 件 — 5 節)。
