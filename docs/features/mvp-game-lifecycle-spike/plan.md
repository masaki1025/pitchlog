---
feature: mvp-game-lifecycle-spike
status: active
重さ分類: コア領域
branch: feature/mvp-game-lifecycle-spike
起点: 660d58554f3e0b74da2623ffd7e9a452188d7772
worktree: ~/projects/pitchlog-worktrees/feature-mvp-game-lifecycle-spike
created: 2026-11-05
---

# 試合の終了・再開・再終了の接続spike

## 1. 起点と統合状況

- 起点は公開候補 `feature/mvp-batted-hits@660d58554f3e0b74da2623ffd7e9a452188d7772`。
- 開始時点で正式 `develop` は `112f771e549d6a92d724f62d9b0b45dcc89973c1`。
  起点は `origin/develop` を祖先に持ち、`origin/develop..起点` は 89 コミット。
- 起点は正式 develop に未統合。GitHub PR #196（base `develop`）は open / draft。
  したがって本枝の成果も正式受理・正式統合済みとは扱わない。
- 本枝は専用 worktree で作成し、他 worktree・共有台帳・正本・`contracts/` を変更しない。

## 2. 目的

実画面で新規試合を作成・開始し、既存の通常投球画面で記録した後、

1. 画面から試合終了を宣言する
2. 画面から追記再開する
3. 追記再開後に記録を追加する（接続できる範囲で）
4. 画面から再終了する
5. サーバーから再取得し、ページ reload 後も終了確定版を確認する

を通し、認証・記録権・同期核・原子的保存を維持したまま、成績側へ渡す
「終了確定版」「再開による失効」「再終了の版」を観測可能にする。

対象は既存仕様の **9回制・同点でない試合** に限定する。コールド・サヨナラ・
タイブレーク・引き分け・終了後修正は本spikeの成功条件にしない。

## 3. 再利用する成果

| 起点 | 再利用するもの | 本枝での扱い |
| --- | --- | --- |
| 現行製品 | `POST /games/{id}/sync/events` の実認証・実端末提示・実writer・実記録権・P2 同期核・D5 台帳・原子 TX | 終了・再開・再終了をすべてこの入口へ送る |
| 現行製品 | `deriveLineupPlayPrefixWithContinuation` / T1・T2 の保存済み計算結果 | 最終状態を画面で再計算せず、サーバー保存済みの `after` を読む |
| 現行製品 | `GameScreenEntryHost` / `GameScreenStart` / `GameScreenOrdinaryPitch` | 試合作成・開始・初回記録に使う |
| 現行製品 | `GameStartPersistence` の端末資格・V12 | 終了・再開要求の実端末提示と記録権証明に使う |
| 現行製品 | `operation_events` / `idempotency_ledger` / `invalidation_intents` | 終了・再開の監査、再送の冪等、再開による失効意図に使う |
| undo 接続spike | 「保存済みイベントを D1 順に畳み、専用 GET で返す」読み方 | 専用 GET の設計だけを参考にし、コードは共有しない |

ドメイン計算のコピー実装は作らない。終了条件の検知は既存 T2 の保存結果を読み、
本spikeは「宣言」と「版」だけを追加する。

## 4. スコープ

### やること

- `game_end_declaration` の V7 に閉じた spike payload を載せ、既存 `/sync/events`
  の P2 経路で終了・再開・再終了を受理する。
- 終了確定版を `finalization.version`（1,2,…）と `D1`/`D5`/最終状態の組で表し、
  再開が直前の確定版を失効させたことをイベント列から導出する。
- 専用 GET `/spike/games/{id}/lifecycle` で、現在状態・終了確定版・失効・
  次の D1/D2 を返す。GET は実認証・tenant 束縛だけを使い、書込みをしない。
- 記録画面に lifecycle panel を追加し、終了・再開・再終了・再取得を実行する。
- 実 DB で、再送の重複、権限不足、越境、保存途中故障、再終了の版を検証する。
- 実ブラウザで、実画面の作成・開始・記録・終了・再開・再終了・reload を試す。

### やらないこと

- `contracts/`・`docs/requirements`・`docs/design`・`docs/adr`・共有台帳の変更。
- DB schema / migration / 認可 catalog / 共有 operation registry の変更。
- `games.status` の更新。現行 schema の直接更新経路と製品 projection の所有が
  未確定なため、本spikeではイベント列を現在状態の正とする。
- 再開後の製品 prefix 読取・通常投球入力の完全接続。現行 play prefix projection は
  同一 PA 内の非 play イベントを拒否するため、bridge 契約が必要（`proposal.md`）。
- 成績 API / CSV の実接続。渡す版の形だけを `proposal.md` に提案する。
- 正式統合・PR 作成・マージ。

## 5. spike payload（契約ではない）

終了:

```json
{
  "formatVersion": "game-lifecycle-spike-v1",
  "action": "end",
  "finalization": {
    "version": 1,
    "previous": null,
    "state": { "stateFields": {}, "scoreboard": {}, "battingOrderBySide": {} }
  }
}
```

再開:

```json
{
  "formatVersion": "game-lifecycle-spike-v1",
  "action": "reopen",
  "finalization": {
    "version": 1,
    "target": { "version": 1, "d1": 2 },
    "state": { "stateFields": {}, "scoreboard": {}, "battingOrderBySide": {} }
  }
}
```

再終了は `previous = {version:1,d1:2}`, `version:2` の `end`。
イベント種別は既存 `game_end_declaration` を使い、D1/D2/D4/D5/V12 は既存 P2 のまま。
`contracts/` へは反映しない。

## 6. 実装ステップ

| # | 内容 | 合格条件 |
| --- | --- | --- |
| 1 | lifecycle payload の内容検証・投影・イベント畳み込みを実装 | payload 形状、9回制、非同時点、版の連鎖、最新版の参照、状態一致を純粋試験で確認 |
| 2 | 既存 `/sync/events` に lifecycle 経路を接続 | 実認証・実記録権・P2 同期核・D5 冪等・原子 TX で終了/再開/再終了を保存。故障注入で全取消 |
| 3 | 専用 GET と lifecycle panel を実画面へ接続 | 終了→再開→再終了→再取得/reload を画面から実行し、確定版と失効を表示 |
| 4 | 実画面 E2E と非作者レビュー | 固定 HEAD・再現手順・証拠・未達条件を `findings.md` に記録 |

## 7. 検証

- 純粋: payload の閉キー、版の連鎖、状態一致、非同時点、再送同一 D5。
- 実 DB: 実 login → 実作成 → 実開始 → 実通常投球 → 終了 → 再送 → 再開 →
  再終了。別 tenant 404、V12 不一致の退避、故障時のイベント/水位不変。
- 実画面: 実 HTTPS の Vite + 実 app + owned PG で、作成・開始・記録・終了・
  再開・再終了・reload を Playwright で観測。
- 未達は成功へ読み替えず、`findings.md` に残す。
