---
feature: uf5-team-player-management
status: active
承認: 済(2026-10-13・山田正輝)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2
branch: feature/uf5-team-player-management
created: 2026-10-13
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書案: U-F5 選手・対戦相手管理の初期分割（TSK-520）

## 1. 目的

[調査記録](research.md)で確認した U-M1 の実 API と、PR #120 が提供する U-F6 共通 API を使い、チームアカウントが自チーム・対戦相手の選手と対戦相手チームをページ単位で閲覧し、登録・通常編集できる画面を作る。

本計画は [TSK-520](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2) の**初期分割**である。正式カード全体のうち、一覧・選手登録・選手の属性編集・対戦相手登録・対戦相手名編集だけを扱う。カード全体を完了にしない。

## 2. 前提、依存、着手ゲート

- 調査開始時の起点は `origin/develop` の `928280e6b78c5e87049d164aa1f8f9538ef30edf`。専用 worktree と branch は作成済み。これは固定基点ではなく、PR #120 統合後の実装開始時に最新 `origin/develop` を取り込み、計画前提への影響を再確認する。
- U-M1 の backend API は develop に存在する。
- **製品コードのステップ 1 着手前に、人間の計画承認と PR #120 の develop 統合が必要**。統合後の `frontend/src/api/{client,types,roster}.ts` をそのまま使う。未統合 branch から cherry-pick、コピー、仮 DTO を作らない。
- PR #119 は初期の未公開コンポーネント実装には不要だが、実ログインを使う公開受入には必要。
- PR #121 は依存しない。在籍変更と一括変更を初期範囲から外す。
- U-F13 の統合済み provider / router は再利用する。初期 PR では `router.ts` と `App.vue` を変更せず、U-F13 残部を完了扱いにしない。

## 3. スコープ

### 3.1 実装する製品コード

- `frontend/src/screens/TeamScreen.vue`
  - self / opponent を含むチームレコードのページング一覧。
  - 選択したチームレコードの選手ページング一覧。
  - 次ページは `next_cursor` がある場合だけ取得し、取得済みページを表示へ連結する。全件一括取得はしない。
  - 初回、追加ページ、空一覧、再試行可能な失敗を区別して表示する。
- `frontend/src/components/settings/TeamMembersContent.vue`
  - 選手登録: 名前、投、打を必須、背番号を任意とする。作成要求は `roster_status_key='active'`、`roster_label_key=null`。
  - 選手編集: 名前、投、打、背番号だけを PATCH する。在籍区分とラベルは送らない。
  - `PlayerCreated.same_number_players` が空でなければ、登録完了を明示した上で同番号の現役選手を警告する。
- 対戦相手の登録・編集 UI
  - 登録は `createTeamRecord()` だけを使う。認証用チーム作成やセルフサインアップの文言・操作を置かない。
  - `kind='opponent'` の行だけに名称編集を出す。self の名称はこの画面から更新しない。
  - `TeamRecordCreated.similar_names` が空でなければ、登録完了を明示した上で類似名と作成した行の名称編集導線を示す。
- `frontend/src/lib/rosterQueryKeys.ts`
  - U-F5 と後続 U-F8 が共有する選手 query key の生成を一か所に置く。先頭は既決の `['players', teamId]` とし、チームレコード ID とページ条件を後続要素にする。
  - チームレコードは `['team-records', teamId]` を先頭にする。
  - 選手登録・編集後は **`['players', teamId]` の共有 prefix 全体**を invalidate し、U-F8 の共有一覧と U-F5 のチーム別・ページ付き query をまとめて古い状態にする。対戦相手登録・編集後は `['team-records', teamId]` の prefix 全体を invalidate する。
- 対応する `*.spec.ts`。API の関数と DTO は `frontend/src/api/roster.ts` から import する。

`teamId` が null の間は query を開始しない。チーム名や選択中のレコード IDをテナント ID の代用にしない。画面内の選択、入力途中、警告、エラーは `authEpoch` 変更時に破棄し、新認証の query が解決するまで旧一覧を表示しない。mutation は開始時の `authEpoch` を保持し、完了時に世代が違えば成功値・失敗値によるフォーム、警告、cache、invalidation の更新を行わない。`ApiStaleAuthError` を自動再送せず、「送信元チームで処理された可能性があり結果未確認」であることと、送信元チームへ戻って一覧を再読込して確認する手順を案内する。切替後の B の一覧を A の処理確認先として案内しない。

### 3.2 初期分割から外すもの

- 在籍区分・ラベル変更、複数選手のプレビューと一括変更。PR #121 のロック順修正統合後に別ステップで計画する。
- 選手と対戦相手の削除。正式 DoD の論理削除は後続で満たし、物理削除 UI や独自 DELETE は作らない。
- 試合中の選手登録、試合作成中の対戦相手登録、試合作成、前回スタメン、移行、名寄せ、プロフィール、測定値、分析プロフィール。
- login / logout、認証用チーム作成、テナント発行、認証ガード、応答テナント照合、router への `/team` 登録。
- `frontend/src/api/**`、`backend/**`、`contracts/**`、U-F13 の `App.vue` / `router.ts`、U-M2 担当ファイルの変更。
- 新しい mock mode、E2E harness、共通 API client、API / DTO。

## 4. 影響する正本とコア領域

### 4.1 5 領域判定

| 領域 | 判定 | 理由 |
| --- | --- | --- |
| S 同期 | 非該当 | 同期キュー・再送・操作イベントを扱わない |
| G 状況計算 | 非該当 | 状況遷移・成績計算を持たない |
| R 記録権 | 非該当 | 記録世代・引き継ぎ・フェンシングを扱わない |
| T テナント | **該当** | テナント所有のチーム・選手を取得・変更し、認証切替時の表示破棄を扱う |
| D 移行 | **該当（単位帰属を維持）** | 初期分割は移行コードを持たないが、正式 U-F5 が FR-038 の確認面に接するため、単位定義の fail-closed な T・D 重複帰属を降格しない |

コア領域として反対側の敵対レビューと人間逐行確認を行う。`guard_paths` / core areas の検出結果を PR 作成前に記録し、確認者本人以外がチェックを代記しない。

### 4.2 正本

`docs/requirements/**`、`docs/design/**`、`docs/adr/**`、`docs/development/**`、`docs/ops/**` は変更しない。承認済み要件、U-F5 の単位定義、U-M1 API、U-F2 / U-F6 の契約に従う実装である。変更する文書は本計画、調査記録、作業ログだけ。

## 5. 実装ステップ

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | PR #120 統合後の実コードを再照合し、query key、チーム・選手のカーソルページング一覧、認証切替時の一覧・選択状態破棄を実装する。経路へは登録しない | U-F6 の `listTeamRecords` / `listPlayers` と共有 QueryClient だけを使う。`limit` 付きで 1 ページずつ読み、`next_cursor` がないと停止する。self と opponent を識別し、選択チームの選手だけを表示する。`teamId=null` では送信しない。A→B の `authEpoch` 変更で A の一覧・選択を即時に隠し、B の取得前に再表示しない。Vitest、型検査、ESLint、Prettier、build が green |
| 2 | 選手と対戦相手の登録・通常編集、登録後警告、cache invalidation、エラー表示を実装する | 実在 DTO 以外を送らない。選手 mutation は `['players', teamId]` の共有 prefix 全体、対戦相手 mutation は `['team-records', teamId]` の prefix 全体を invalidate し、共有 key とチーム別・ページ付き key の双方を古い状態にする。登録・編集成功後に該当一覧を再取得し、再読込後も応答値が表示される。類似名・同番号は「登録済み」と分かる警告になり、名称編集へ進める。A の遅延 mutation が成功・失敗しても B のフォーム・警告・cache・invalidation を更新しない。フォーム入力と警告は authEpoch 変更で破棄する。`ApiStaleAuthError` を自動再送せず、送信元チームでの確認を案内する。404 / 401 / validation を旧データなしで表示する。利用者入力は Vue 補間だけで表示し `v-html` がない。全 frontend 品質ゲートとコアレビュー準備が green |

コミット件名は各ステップに `(ステップ 1/2)`、`(ステップ 2/2)` をちょうど 1 個含める。承認されたステップだけを実装して停止する。

## 6. DoD と残余

### 初期分割の DoD

- [ ] チームと選手の一覧がカーソルページングされ、全件一括読み込みをしない。
- [ ] 選手を名前・投・打・任意の背番号で登録し、通常属性を編集できる。
- [ ] 対戦相手をテナント内レコードとして登録し、対戦相手名を編集できる。認証チーム作成と混同する入口・文言がない。
- [ ] 登録後の同番号選手と類似チーム名を、登録成功を隠さず警告する。
- [ ] U-F6 共通 client / DTO と共有 QueryClient を再利用し、コピーや仮契約がない。
- [ ] 認証切替時に旧テナントの query cache、購読表示、選択、フォーム、警告を残さない。
- [ ] 404 / 401 / stale auth で別テナントの本文を表示せず、mutation を自動再送しない。
- [ ] 利用者入力を自動エスケープし、生 HTML 挿入をしない。
- [ ] コア領域の敵対レビューと人間逐行確認の記録欄を PR に設ける。

### TSK-520 固有で残る DoD

- [ ] FR-017 の在籍区分・ラベル・一括変更プレビュー。PR #121 の選手 UUID 昇順ロックと応答順維持へ接合する。
- [ ] FR-018 の選手論理削除と OB 化誘導、FR-039 の対戦相手論理削除とリネーム誘導。
- [ ] FR-015 / FR-039 の試合画面・試合作成画面を離れない登録。
- [ ] FR-038 の移行後確認、名寄せ、プロフィール・測定値関連の採否。
- [ ] U-F5 の公開経路に対する越境拒否、認証切替時の旧データ破棄、実 API を使う登録・編集→一覧→再読込の受入。

### U-F5 公開前の外部前提

- U-F13 所有: 保護 `/team` ルート、認証ガード、`RouterView` の `authEpoch` key。15 経路 + catch-all 全体は U-F13 の残余であり、TSK-520 の完了条件へ混ぜない。
- U-A1 / U-F2 所有: 認証済み主体から検証済みの tenant ID を U-F2 へ渡す承認済み契約。PR #119 の現行 `status` 応答だけでは未充足。
- U-F6 所有: 応答側の独立した tenant 証跡と、期待 tenant ID との完全照合。形式を U-F5 で仮定しない。
- 接続 PR: 上記の一致、保護ルート、実 API 受入を確認する。外部前提が未充足でも TSK-520 固有の残作業と混同せず、公開不可の blocker として追跡する。

## 7. テスト計画

| 種別 | 初期 PR で自動化する内容 |
| --- | --- |
| query / 表示 | 最初のページ、次ページ、末尾、空、追加取得失敗、チーム選択時の選手 query 切替、limit と cursor の引き継ぎ |
| 登録 / 編集 | 選手・対戦相手の要求、二重送信防止、成功後 invalidation と再読込、任意背番号の null、self チーム名編集なし。選手 mutation で共有 `['players', teamId]` とその配下のページ付き key がともに invalidation されること |
| 警告 | `same_number_players` と `similar_names` の文字列表示、登録済み表示、編集導線 |
| 認証境界 | `teamId=null` で未送信、authEpoch 変更で一覧・選択・入力・警告を破棄。遅延した A mutation の成功・失敗後も B のフォーム・警告・cache・invalidation を更新せず、B query だけを表示。stale mutation は送信元チームでの確認を案内 |
| エラー | 401、404、422、network、`ApiStaleAuthError`。別テナント由来の本文を保持せず mutation を自動再送しない |
| XSS | 要素・属性を含むチーム名 / 選手名を文字列として表示し、挿入要素やイベント handler を作らない |

実装ステップでは `frontend/` で `pnpm exec prettier --write .`、`pnpm exec eslint .`、`pnpm exec vue-tsc --noEmit`、`pnpm test`、`pnpm build` を行う。差分に応じて repository ルートの `uv run ruff check .`、`uv run ty check`、`uv run pytest tests/` と guard 検査を追加する。

公開接続 PR では、既存の開発 DB・backend・Vite proxy を使って次を実 API で確認し、証跡を残す。

1. A でログインし、対戦相手と選手を登録・編集する。
2. 一覧の次ページと画面再読込で保存値が残ることを確認する。
3. B へ認証を切り替えた直後に A の一覧・フォーム値・警告が消え、B のデータだけが表示されることを確認する。
4. A の選手 / 対戦相手 ID を B の Cookie で直接要求し、404 になり本文が画面へ出ないことを確認する。
5. 認証済み主体から得た期待 tenant ID と、応答側の独立した tenant 証跡が一致し、不一致応答を画面へ渡さないことを確認する。具体形式は U-A1 / U-F6 の承認済み契約を使う。

## 8. 人間承認が必要な判断

1. **初期 PR の公開境界**: 本計画どおり TeamScreen を経路未登録で先行実装し、U-F13 の保護ルート接続を別 PR にするか。推奨はこの分割である。
2. **開始ゲート**: PR #120 が develop に統合され、再照合が終わるまでステップ 1 を開始しないこと。
3. **公開ゲート**: PR #119、認証済み主体から検証済み tenant ID を U-F2 へ渡す契約、U-F13 の認証ガード / `authEpoch` key、U-F6 の応答 tenant 証跡と完全照合が揃うまで `/team` を公開しないこと。
4. **正式カードの扱い**: 初期分割の実装後も TSK-520 は未完了として維持し、6 節の残余を後続へ送ること。

承認後の開始ステップは **ステップ 1/2**。PR #120 が未統合なら承認済みでも待機し、未統合 branch のコードを取り込まない。

## 9. 人間承認記録

2026-10-13、山田正輝が本計画と次の 4 点を承認した。

1. `TeamScreen` を経路未登録で先行実装する。
2. PR #120 の develop 統合まで製品実装を待機する。
3. 認証、検証済み tenant ID の供給、認証ガード、応答 tenant 照合が揃うまで `/team` へ接続しない。
4. 初期分割完了後も TSK-520 を未完了として維持する。

実装開始時は最新 `origin/develop` を取り込み、前提差分を確認してからステップ 1/2 だけを実施する。
