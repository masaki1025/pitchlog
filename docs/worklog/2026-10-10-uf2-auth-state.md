---
date: 2026-10-10
topic: U-F2 認証状態(authStore)
branch: feature/uf2-auth-state
---

# 作業ログ: 2026-10-10 U-F2 認証状態(authStore)

## やったこと

### /task-start

- 既存 Notion タスク TSK-517 に着手(master の振り直し — TSK-534 を後送りにして U-F2 を先行): https://app.notion.com/p/3f493b75e6878158b3d4fb0eafbb170d
- ブランチ `feature/uf2-auth-state` / worktree `../pitchlog-worktrees/feature-uf2-auth-state`(`origin/develop` = `24c023e4` 起点)

### /investigate

- 4 並列(legacy-analyst / spec-checker / decision-tracer / Explore)。legacy-analyst は旧リポジトリの固定コミットを読む手段がないため、`dd03160` の 34 ファイルを主セッションがスクラッチパッドへ書き出して再実行した(U-F1 と同じ手順)
- 結果は [research.md](../features/uf2-auth-state/research.md)。要点: トークンは HttpOnly Cookie で U-F2 は持たない / authKind・username・role は Won't と「チーム管理者ロールなし」で落ちる / δ のログイン API は未着地だが U-F2 は HTTP を持たないので先行できる / ログアウトで消すのはクエリキャッシュだけ(FR-012 `req:329`)/ 依存を切ってもコア(T 該当)

## 決定

## 未決・次の一歩

### /plan

- /plan 前に PO へ分岐 4 点を確認(2026-10-10・山田): P1 チームだけ持つ / P2 δ を待たずに作る / P3 pinia を同じ PR・保存は自前 / P4 タブ間同期を入れる。すべて推奨案
- 依存の版を `pnpm view` で確認: pinia 4.0.3(2026-08-12 公開・latest)、必須 peer `@vue/devtools-api` 8.2.1(2026-07-25)。依存 `nostics`(vuejs・vercel-labs の保守者)。どれも install スクリプトなし
- 計画レビュー中に develop が #95 のマージで進んだため取り込んだ(`scripts/core_guard.py` の宣言層が変わっており、paths 登録の手順に効くため)

#### 計画レビュー 1 回目(adversarial・計画書全文)— 否決 P0 3 / P1 1 / P2 0、全件採用

| # | 指摘 | 処理 |
| --- | --- | --- |
| P0-1 | `queryClient.clear()` は購読中の observer の直前結果を消さない → 画面を維持したまま A → B へ切り替えると A の結果が表示に残る | 採用。`authEpoch` を公開し、鍵で画面を作り直す(決定 J)。配線は U-F13 へ申し送り、本単位は鍵付けした試験部品で表示まで検査(ステップ 4 ②) |
| P0-2 | 同じ値の `setItem` は `storage` イベントを出さない(同名チームの退役・再作成で teamName・teamId が一致しうる)。書き込み失敗・イベントの遅延の窓もある | 採用。ログインごとの `sessionId` を保存して照合(決定 D・G)、`syncFromStorage()` を公開し U-F6 が送信前に呼ぶ(申し送り)、書き込み失敗時はキー削除を試みる。ストレージ自体が使えない環境の穴は残余として決定 G に明記 |
| P0-3 | paths 登録の後送りは 6.3 の落とし込み規則 ①(`:404`)に反する | 採用。宣言(ステップ 5)→ 登録(ステップ 6)の 2 段を本 PR に入れる |
| P1-4 | IndexedDB の「データベースが残る」では未同期レコードの保持を示せない | 採用。レコードを入れて内容まで残ることを検査(ステップ 4 ③) |
