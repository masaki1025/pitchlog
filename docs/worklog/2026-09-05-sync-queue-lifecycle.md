---
date: 2026-09-05
topic: 同期プロトコル — キューの状態遷移とクライアント規律(後続 α)
branch: feature/sync-queue-lifecycle
---

# 作業ログ: 2026-09-05 同期プロトコル — キューの状態遷移とクライアント規律(後続 α)

## やったこと

### /task-start

- Notion タスク(**TSK-280 の /task-done で起票済み**。重複起票はしていない)を取得
- worktree `../pitchlog-worktrees/feature-sync-queue-lifecycle`(ブランチ `feature/sync-queue-lifecycle`・
  起点 `origin/develop` = `76f0652`)を作成
- 計画書雛形 `docs/features/sync-queue-lifecycle/plan.md` と本ログを作成
- Notion のステータスを **進行中** へ・ブランチ名をタスクへコメント

### 着手前に Notion カードを訂正(2026-09-05)

**起票時に `NFR-019(d)` の 6 項目すべてを本タスクへ入れていたが、これは誤りだった。**
半分(**墓標/改訂の適用**・**サーバー適用の原子性〔クラッシュ注入〕**)は**サーバー適用側**であり、
キュー実装だけでは書けない。**後続 γ のカードへ移管**し、本タスクは**クライアント側 4 項目**
(複数タブの単一書き手競合・E5-1〜E5-3)に限定した。

**訂正の理由**: TSK-280 の計画で最も苦労したのが「**射程が実は成立していない**」型の欠陥だった
(「4 章のみ」では型が書けない / DoD が要求する (d) が 1 つも書けない)。**同じ型を後続へ持ち越さない**ため、
着手前に分担を確定した。

## 決定

- **射程はクライアント側**(7-2 / 7-4 / 7-7 / `K5` / W4 のクライアント規律側 + (d) の 4 項目)。
  ACK の応答契約(7-1・7-3)と undo の同期上の表現(7-6)は**後続 β**、
  サーバー適用の処理段階(6 章)と原子性(8 章)は**後続 γ**
- **重さ分類はコア領域**(同期プロトコル)。sol xhigh・敵対レビュー・**人間の逐行確認必須**
- **TSK-280 の作法を再発明しない** — オラクル照合(期待集合を TS 側に持たない)・注入境界(未注入は fail-closed)・
  値の形式を検査しない・ID は正本 ID・単一 locus・射程外の不在 assert を壊さない
- **`K5` は TSK-280 が射程外 allow-list に置いた。本タスクで実装対象へ移す**
  (未知 ID は throw するので移し忘れは red になる)

## 未決・次の一歩

- **`/investigate`** — 7-2 の状態遷移(`R-QUEUE-LIFE` の 5 要素)・7-4 の規律・7-7 の書き出しの全数把握。
  **旧 SPA の逆実装 3 件**(未同期時の全入力ブロック / undo の未同期時不可 / 状態補正の直接上書き)の
  I-28 裁定の逐語確認。**永続化技術**((B) 論点 19 = 実装計画へ委譲)の選択肢
- **`/plan`** — 実装ステップ表と「やること / やらないこと」の確定 → 計画レビュー → 人間承認
- **TSK-280 で残した申し送り**(改訂ゲート候補 3 件)は別タスクで起票済み。本タスクでは触らない

## /plan(2026-09-05)

- 計画書を作成 → **敵対レビュー(コア領域)1 周目は否決**(P0 8 件・P1 7 件・P2 1 件)
- 指摘を原典で確認して全面改訂(**10 → 14 ステップ**)。人間承認 2026-09-05・山田正輝
- **(B) 論点 19・20 と `U-5` を本計画で確定**(正本が実装計画へ委譲していたもの):
  永続化 = **IndexedDB** / 書き出し = **JSON + 注入 codec** / 単一書き手 = **Web Locks** / B4 の通知文面
- **表示を 2 層に分割** — 通知契約は本タスク、画面接続は**後続 δ**(記録画面が未実装のため)

## /implement(2026-09-05)

| ステップ | コミット | テスト |
| --- | --- | --- |
| 1 U-2 語走査の精緻化 | `0048c74` | 176 |
| 2 4 状態 + `R-QUEUE-LIFE` 全トークン照合 | `e5aed3a` | 193 |
| 3 遷移 14 行 + 注入境界 7 点 | `c88414e` | 242 |
| 4 `K5` 専用 reader と墓標生成条件 | `8a340d6` | 261 |
| 5 `C4` の写像確定ゲート | `805b40e` | 270 |
| 6 IndexedDB 永続キューと `Q1` の不可分性 | (ステップ 6) | 281 |
| 7 `Q3`・`Q7` と 24 時間破棄 | `d477c8e` | 293 |
| 8 通知契約 6 種 | `4ea1504` | 306 |
| 9 Web Locks による単一書き手 | (ステップ 9) | 322 |
| 10 ローカル書き出しと取り込み | `dfab694` | 332 |
| 11 `NFR-019(d)` 資産 4 件 + validator | (ステップ 11) | 344 |
| 12 (d) アダプタと 4 シナリオ実行 | (ステップ 12) | 353 |
| 13 W4 の 3 前提合成入口 + `P-24` + 走査対象の是正 | (ステップ 13) | 371 |

### 差し戻した内容(Claude の検証で見つけたもの)

1. **ステップ 2**: 3 下位ラベルの期待集合をテスト側に TS リテラルで持っていた。
   **オラクル JSON にこの 3 ラベルは存在せず**(grep で確認)、照合相手のない書き写し = **H-61**。
   構造検査へ置き換え、逐語の一致は**人間逐行確認へ送る**形にした
2. **ステップ 3**: 遷移行を**配列の添字**(`QUEUE_TRANSITION_RULES[1]` など)で束縛していた。
   行を 1 つ挿入するだけで全束縛が静かにずれ、件数 14 の検査も内容検査も通る。**行 ID 参照へ変更**
3. **ステップ 3**: `QT-06` が**改訂版と墓標を同条件で通していた**。正本は
   「改訂版はローカル生成 / 墓標はオンライン記録権確認後」と非対称に定める。
   **7 番目の注入境界 `confirmTombstoneGeneration`** を追加(未注入・`false`・例外はすべて遷移しない)
4. **ステップ 4**: 状態 ID・下位ラベル ID の位置参照が **11 箇所**に広がっていた。
   `queueStateId()` / `actionRequiredLabelId()`(未知 ID は throw)へ統一

### 計画書の是正(2026-09-05・`d7dd287`)

**承認済み計画書の `U-5` 文面が、正本 6-3 の B4 行(`:747`)の 3 要素を満たしていなかった。**
「**破棄されていないことを明示する**」が抜けており、閲覧・書き出しの案内で含意させるだけだった。
文面に「記録は破棄されていません。」を追加。あわせて「6-5 の非開示規則」は**正確には B6 に掛かる規則**
である旨を注記した。

### 実測として記録すること

- **`fake-indexeddb` を devDependency として追加**(`6.2.5`・テスト専用)。
  `jsdom` 30 は IndexedDB を実装しておらず、**トランザクション中断の意味論を本物で検証できない**ため。
  人間の判断を仰いで採用した
- **Codex の再開セッションが肥大**(ステップ 11 時点で累計 **97 万トークン**)。
  ステップ 12 の実行がハーネスのメモリ監視に **2 回強制終了**された(worktree は無傷)。
  **新規セッションへ切り替えて成功**。長い実装タスクでは `--resume` を途中で切る運用が要る
- **ステップ 12 のアダプタが `frontend/src/testing/` に置かれ、`prohibitions.spec.ts` の
  raw 走査対象から外れていた**(715 行)。単一 locus 検査と `U-1`〜`U-4` の不在 assert が効かない状態。
  **ステップ 13 で走査対象へ編入**して塞いだ

### `[手動・外部]` H-59 逐語照合表(**機械 green に数えない**)

**79 行**(TSK-280 の 24 行 + 本タスクの 55 行)。`prohibitions.spec.ts` が出力する。

```
V1 べき等キーD5 → eventFieldRules.ts / EVENT_FIELD_RULES・EVENT_IDENTIFIER_SLOT_IDS
V2 イベント連番D1 → eventFieldRules.ts / EVENT_FIELD_RULES（D1 付き経路必須・P3 禁止条件）
V3 記録権世代D4 → eventFieldRules.ts / EVENT_FIELD_RULES（D1 付き経路必須・P3 禁止条件）
V4 試合の識別 → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）
V5 イベント種別 → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）
V6 論理位置を定める値D2 → eventFieldRules.ts / EVENT_FIELD_RULES（参加区分条件・P3 禁止条件）
V7 ペイロード → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）
V8 状態差分 → eventFieldRules.ts / EVENT_FIELD_RULES（取消可能条件・P3 禁止条件）
V9 置換・墓標の状態 → eventFieldRules.ts / EVENT_FIELD_RULES（墓標・改訂条件・P3 禁止条件）
V10 対象イベントの参照 → syncEvent.ts / TargetEventReference（試合・対象の D4・対象の D1）
V11 対象の期待版 → eventFieldRules.ts / EVENT_FIELD_RULES（P3 必須条件）
V12 記録権証明 → requestBoundary.ts / RequestBoundaryEnvelope・V12_BOUNDARY_RULES
#1 毎球入力 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#2 undo → eventKinds.ts / EVENT_KIND_RULES（群 A・従属）
#3 選手交代 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#4 タイブレーク開始 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#5 試合終了宣言 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#6 選手のその場登録 → eventKinds.ts / EVENT_KIND_RULES（群 A・同期順のみ）
#7 状態補正 → eventKinds.ts / EVENT_KIND_RULES・buildSyncEventKindSet（群 A・論理位置を持つ）
#8 墓標 → eventKinds.ts / EVENT_KIND_RULES（群 A・同期順のみ）
#9 改訂版 → eventKinds.ts / EVENT_KIND_RULES（群 A・元イベントの参加区分を継承）
#10 プレイの修正 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）
#11 プレイ行の論理削除 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）
#12 交代イベントの修正 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）
状態 未送信 → queueState.ts / QUEUE_STATES（確定前・自動破棄しない）
状態 要操作 → queueState.ts / QUEUE_STATES（自動再送・自動破棄の対象外）
状態 同期済み → queueState.ts / QUEUE_STATES（端末永続化済み結果を保持）
状態 退避済み → queueState.ts / QUEUE_STATES（閲覧・書き出し対象）
要操作下位 改訂待ち → queueState.ts / QUEUE_ACTION_REQUIRED_LABELS
要操作下位 墓標待ち → queueState.ts / QUEUE_ACTION_REQUIRED_LABELS
要操作下位 管理者対応待ち → queueState.ts / QUEUE_ACTION_REQUIRED_LABELS
I6 P3受理結果の端末保持 / 端末永続化まで成立した対象参照 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / V11の版 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / D5 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / 確定内容 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / accepted_atを起点 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / 同期済みと同じ24時間保持 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / 保存済み結果の再掲で延長しない → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / サーバー確定から端末永続化まで保護なし → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / RG1中は自動破棄停止 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / 退避・閲覧・書き出し対象 → queueState.ts / I6_HOLDING_CONTRACT
I6 P3受理結果の端末保持 / 復元規則なし → queueState.ts / I6_HOLDING_CONTRACT
QT-01 （なし） → 未送信 / append-persisted / persistence-completed / 許可=true / 状態変更=true
QT-02 未送信 → 同期済み / apply-a5 / a5-result / A5=受理+重複 / 許可=true / 状態変更=true
QT-03 未送信 → 要操作 / apply-a5 / a5-rejection-with-b3-classification / A5=拒否 / 許可=true / 状態変更=true
QT-04 未送信 → 未送信 / apply-a5 / a5-result / A5=未処理 / 許可=true / 状態変更=false
QT-05 未送信 → 未送信 / ack-unavailable / ack-not-returned / 許可=true / 状態変更=false
QT-06 要操作 → 未送信 / action-replacement-persisted / same-slot-replacement-completed / 許可=true / 状態変更=true
QT-07 要操作 → 未送信 / o4-retry-persisted / o4-corrected-and-same-slot-replacement-completed / 許可=true / 状態変更=true
QT-08 未送信 → 退避済み / apply-a5 / a5-result / A5=退避 / 許可=true / 状態変更=true
QT-09 P3変更受理結果 → 同期済み / p3-acceptance-persisted / accepted-at-resolved-and-device-persistence-completed / 許可=true / 状態変更=true
QT-10 同期済み → 退避済み / i6-evacuation-saved / i6-evacuation-save-completed / 許可=true / 状態変更=true
QT-11 未送信 → 破棄 / discard / no-transition / 許可=false / 状態変更=false
QT-12 要操作 → 破棄 / discard / no-transition / 許可=false / 状態変更=false
QT-13 同期済み → 破棄 / discard / retention-elapsed-and-rg1-inactive-confirmed / 許可=true / 状態変更=true
QT-14 退避済み → 破棄 / discard / no-transition / 許可=false / 状態変更=false
Q1 新規スロットの追記と D1 採番を不可分に永続化 → durableQueue.ts
Q2 同一ブラウザの複数タブは単一の書き手だけが記録 → singleWriter.ts
Q3 警告閾値でも記録をブロックしない → clientDiscipline.ts
Q4 未送信件数を常時表示する記述子 → syncNotices.ts
Q5 キュー空の同期成功時に試合と球数を通知する記述子 → syncNotices.ts
Q6 永続ストレージ要求の拒否を警告する記述子 → syncNotices.ts
Q7 認証失効でもキューを失わず再ログイン後に同期再開 → clientDiscipline.ts
Q2-a 単一書き手選出の6前提 → singleWriter.ts / SINGLE_WRITER_PRECONDITION_IDS
Q2-b 非所有タブの記録不可と旧タブ終了の導線 → syncNotices.ts / singleWriter.ts
Q2-c ロック保持中の非所有タブ入力を未受理にする → singleWriter.ts
Q2-r1 steal を使わない → singleWriter.ts
Q2-r2 コンテキスト終了時の解放後に待機側が取得 → singleWriter.ts
Q2-r3 同一 storage bucket の永続キューを保持 → durableQueue.ts / singleWriter.ts
Q2-r4 ロック取得後かつ記録開始前に単一書き手を再検証 → singleWriter.ts
X1 書き出しで D1・D4・D5 を含むイベントの原形を保持 → localQueueFile.ts
X2 取り込み重複を D5 の同一性だけで吸収 → localQueueFile.ts
X3 同一 D4 と要求境界 verifier の成立時だけ取り込み → localQueueFile.ts
X4 同一端末・同一ブラウザだけを保証 → localQueueFile.ts
K5 オンライン記録権確認後に同じ D1 の墓標版へ不可分置換 → k5Tombstone.ts
C4 写像確定まで当該イベントを同期済みにしない → mappingConfirmationGate.ts
W4 オンライン前提 → 進行中 P3 は適用 / 終了後 P3 も適用
W4 記録権保持前提 → 進行中 P3 は要求境界で照合 / 終了後 P3 は適用しない
W4 未同期キュー空前提 → 進行中 P3 は適用 / 終了後 P3 は適用しない
```

**3 下位ラベル(改訂待ち / 墓標待ち / 管理者対応待ち)はオラクル JSON に存在せず、正本 7-2 の本文が
唯一の出所である。** `K5` の同一 D1 不可分置換・新しい D1 を採番しない・旧保持端末とオフライン時の
非提供も同様に本文が出所であり、**逐語の一致は機械化できない**。
