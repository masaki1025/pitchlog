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

#### 計画レビュー 2 回目(adversarial・反映差分と影響節)— 否決 P0 2 / P1 0 / P2 0、全件採用

1 回目の P0-1・P0-3・P1-4 は解決と判定。P0-2 の残り 2 経路が指摘された。

| # | 指摘 | 処理 |
| --- | --- | --- |
| P0-1 | 別タブのログインで Cookie が B に変わってから `bb.auth` が更新・読まれるまでの窓に送った要求は、A の表示へ B の応答を返しうる。送信前照合では閉じない | 採用。決定 F・G の「窓を閉じる」を「狭める」へ改め、閉じるにはテナントの照合契約(要求の期待チーム ID の拒否、または応答の認証チーム ID の照合)が要ることを明記。δ・U-F6 へ申し送り(δ はチーム ID を返す必要がある) |
| P0-2 | B の `signIn` の書き込みが失敗し削除も失敗すると、次の照合でメモリが A へ戻り Cookie は B のまま | 採用。切り離し状態(決定 D・G): 保存に失敗したらメモリを正とし保存値へ戻さない。保存値がその後変われば未認証へ倒す。削除の成功・失敗の両方を試験(ステップ 3) |
| (c) 所見 | ステップ 5 の試験修正は登録前後の両状態を受理させる必要がある | 合格条件へ追記 |

#### 計画レビュー 3 回目(adversarial・P0 限定の例外回)— 承認可 P0 0

- 2 回目の P0 2 件は閉じたと判定。テナント照合の窓を δ・U-F6 の契約へ送る扱いは単位境界(`frontend-impl-units/design.md:309`)に沿うと判定。ただし**製品として窓が閉じるのは δ・U-F6 の契約が実装された時点**(残余 — δ・U-F6 への申し送りで追跡)
- 切り離し状態から新たな P0 なし
- 回数の上限に到達(2 回 + P0 例外 1 回)。人間の承認へ上げる

### /implement

| ステップ | コミット | 要点 |
| --- | --- | --- |
| 1 | `04332630` | pinia 4.0.3・@vue/devtools-api 8.2.1。lockfile 追加 8 パッケージ・install スクリプトなし。初回は `PITCHLOG_NET_REASON` 未指定でラッパーが停止(12.1 の記録が必須)→ 付けて再実行。Codex は既定ストアの SQLite を開けず `/tmp` ストアを経由(H-69 の再発)。sandbox 外で frozen install・vue-tsc・build を確認 |
| 2 | `81ee74b4` | authStore(決定 A〜F・H・I・J の authEpoch)。spec 23 件 |
| 3 | `8a1e0823` | `syncFromStorage()`・storage イベント・切り離し状態。spec +18 件 |
| 4 | `08175c0b` | 越境試験 7 件。鍵なしの対照で `clear()` 後も A の表示が残ることを確認(決定 J の根拠) |
| 5 | `e0f06b4a` | `AREA_PATH_ADDITIONS` を U-M1 の 7 件から本単位の 1 件へ置き換え。試験は登録前後の両状態を受理(230 件) |
| 6 | `19bd74d9` | `.claude/core-areas.json` へ登録。`matched_paths()` で authStore 3 件を検知・`other.ts` は非検知 |
| 7 | (本コミット) | porting-rules.md 10 節と 6 節 3 行の注記・design.md の U-F2 行の注記・Notion 申し送り |

- ステップ 5 の委任直前に `/tmp`(tmpfs 7.7G)が満杯になり、プロンプトの書き出しが ENOSPC で失敗した。主因は `/tmp/pytest-of-ymdms`(5.8G)。前日の `pytest-37`・`pytest-143` と、ステップ 1 で Codex が作った `/tmp/pitchlog-uf2-pnpm-store` を消して 5G 空けた(当日の他セッションの run は残した)
- Codex がステップ 6 の検証で worktree 内に `.uv-cache` を作った → 削除

#### Notion への申し送り(ステップ 7 ③ — 2026-10-10)

| 宛先 | カード |
| --- | --- |
| U-F3 ログイン | https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14 |
| U-F6 共通 API | https://app.notion.com/p/3f493b75e6878145aa82d873e8cb65f3 |
| U-F7 耐久キュー | https://app.notion.com/p/3f493b75e687816f8cb4cac7bb1200ea |
| U-F13 起動入口 | https://app.notion.com/p/3f493b75e68781628422c331bfebc350 |
| δ TSK-470 | https://app.notion.com/p/3ee93b75e68781c99d5bd3a15f6e83b5 |
| U-F5 チーム・選手 | https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2 |
| U-F8 試合記録 | https://app.notion.com/p/3f493b75e68781b49976fc6c5ed970d5 |
| U-F10 分析・カルテ | https://app.notion.com/p/3f493b75e6878119ac98f7953c488290 |
| U-F12 スコアカード | https://app.notion.com/p/3f493b75e687815293abd2b3ebd7d9d0 |

### 総合検証(/check)

- frontend: prettier・eslint・vue-tsc・Vitest 838 件・`pnpm build` すべて成功
- harness: ruff・ty 成功。pytest 全件(8 並列・`--basetemp` を `/tmp` の外へ)は 29,172 件中 3 件失敗(`tests/domain/mut/` の 3 件 — U-F1 と同じ顔ぶれ)。単独の再実行で 3 件とも通過。本 PR は `tests/domain/` に触れていない
- backend: 触れていないため CI に任せる

### /sync-docs

- 正本の反映なし(計画書 3 節どおり)。`check_plan_docs_sync.py` exit 0。`core-areas.json` の変更は paths(機械可読)の正の更新で、設計書 6.3 の境界定義表(意味範囲の正)は変えていない

### /pr クローズ処理

- 結果: 旧 `authStore` を、トークン・個人アカウント・役割を持たない「チーム 1 つ分の認証状態」として Pinia で書き起こした。認証の変化でクエリキャッシュを捨て(未同期キューには触れない)、`authEpoch` で購読中の画面を作り直せる鍵を出し、タブ間で `sessionId` を照合する。`frontend/src/stores/authStore*` を tenant-isolation の paths に登録した
- 正本への反映: なし。正本外で `porting-rules.md` 10 節・`frontend-impl-units/design.md` の U-F2 行を更新
- 運用評価台帳: **追記あり**(H-69 の再発・候補「長時間 DB テストの強制終了…」へ `/tmp` 満杯の 3 回目)。`H-*` は採番しない・版は上げない。索引の台帳行はすでに 2026-10-10
- 残余: 別タブのログインで Cookie が先に変わる窓は、δ・U-F6 のテナント照合契約が実装されるまで閉じない(計画書 決定 G・Notion で申し送り済み)

### PR #116 敵対レビュー

#### 1 回目(差分全体)— 否決 P0 1 / P1 3 / P2 1、全件採用

| # | 指摘 | 処理 |
| --- | --- | --- |
| P0 | 認証済みで `syncFromStorage()` の `getItem` が失敗すると、前チームの状態・キャッシュ・表示が残る | 採用。通常状態で認証済みなら保存値を触らず失効(`f12458e1`)。計画書 決定 G に追記 |
| P1 | 切り離し後、外部変更で未認証に倒した次の照合で別タブの値を採る(決定 D・G と不一致) | 採用。切り離しは自分の書き込み成功まで抜けず、比較用の生の値を更新(`f12458e1`) |
| P1 | IndexedDB の保持試験が操作前の接続のまま読む | 採用。接続を閉じて開き直して比べる(`cdf90d80`) |
| P1 | paths 登録を外しても試験が通る | 採用。実際の JSON での包含を要求する独立試験(`2e8613a7`) |
| P2 | 保存値の大きさに上限がない | 採用。4096 文字・`sessionId` は小文字 UUID 形式(`f12458e1`) |

- 是正のため計画書を `active` に戻し(`30742190`)、Notion を 差し戻し → 進行中 へ。検証: stores の spec 53 件・`test_core_guard.py` 231 件・ruff・ty・vue-tsc・eslint・prettier(sandbox の外で再実行)
