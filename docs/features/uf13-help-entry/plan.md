---
feature: uf13-help-entry
status: in-review
承認: 済(2026-10-13・依頼者)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f493b75e68781628422c331bfebc350
branch: feature/uf13-help-entry
created: 2026-10-13
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書案: U-F13 の利用ガイド入口

## 1. 目的と承認判断

U-F13 のうち、完成済みの U-F4 利用ガイドを製品の `/help` から表示できるようにする部分を先行実装する。U-F13 全体は U-F3 ほか多数の画面に依存する。先行分割と、テナントデータを取得・表示しない現行トップの暫定公開は、依頼者が 2026-10-13 に承認した。

正本は [要件書](../../requirements/requirements-pitchlog-2026-07-22.md) と [開発規約](../../../AGENTS.md)。単位境界は [frontend-impl-units/design.md](../frontend-impl-units/design.md) の U-F13 行、画面の受け渡しは [uf4-user-guide/plan.md](../uf4-user-guide/plan.md) 2 節・4 節、認証ストアの受け渡しは [uf2-auth-state/plan.md](../uf2-auth-state/plan.md) 2 節・4 節を使う。

**残余**: 後続の保護経路は U-F3 と未完成画面の着地後に別計画で扱う。既存の主所有 FR は変更しない。[U-F13 タスク TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350)は別接続で取得できたとの依頼者報告により識別した。今回の公開入口はカードの部分実装であり、15 経路と catch-all の一致、認証ガード、越境試験を後続に残す。カード全体を完了扱いにしない。

## 2. 独立性と実在する契約

| 確認点 | 現状と本計画での扱い |
| --- | --- |
| 起点 | `origin/develop` = `9114a5a6`(2026-10-13 再取得)。専用 worktree を fast-forward 済み。旧基点 `212379b5` からの差分は PR #122 の試合区分 seed と認可資産であり、本計画の変更対象ファイルは変わらない |
| 画面 | `frontend/src/screens/HelpScreen.vue` と `back` emit が存在する。利用者入力・API 呼び出しはない |
| 表示部品 | U-F1 の `Button.vue` 等は develop に存在し、HelpScreen が既に利用している |
| 起動 | `frontend/src/main.ts` と `App.vue` が存在する。現状は比較用画面を表示するだけでルータはない |
| 認証状態 | U-F2 の `authStore.ts` と Pinia 4.0.3 が存在する。本計画では Pinia の instance を生成・公開するが、認証判定・セッション操作はしない |
| API / DTO / データ契約 | ガイドは静的画面で通信しないため不要。既存 API や DTO に依存しないことを変更ファイルとテストで固定する |
| 除外する依存 | U-S1、PR #119・#120・#121・#122 の内容を import せず、各担当ファイルを変更しない |

## 3. 変更範囲

- `frontend/src/main.ts` と新規 `frontend/src/appProviders.ts`: 共有 Pinia instance を生成・公開し、既存の `lib/queryClient.ts` とともに install して router を接続する。別の QueryClient は作らない。
- `frontend/src/App.vue` と新規 `frontend/src/router.ts`: `/help` を公開経路として登録し、既存のトップ画面からガイドへの導線を置く。トップ `/` の比較用表示は**テナント所有データを読まない現状に限って暫定公開**とし、後続の U-F13 本体が認証ガードを付けるときに置き換える。この暫定例外は人間承認の対象とする。
- `frontend/package.json`・`frontend/pnpm-lock.yaml`: 既存の移植規則が指定する `vue-router` 4.6.4 のみを追加する。
- `frontend/src/**/*.spec.ts`: `/help` の直接到達、トップからの導線、ガイドの戻る操作、共有 Pinia と共有 QueryClient の install、公開トップがテナントデータに触れないことを検証する。
- 本計画書と作業ログ。正本改訂やハーネス変更は含めない。

`frontend/src/api/**`、`backend/**`、`contracts/**`、他の画面・ストア、既存担当者の worktree は触れない。認証ガード、ログイン画面、保護経路、仮の API・DTO は作らない。

### 3.1 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/**` | **反映なし**。承認済み要件を変更せず、完成済み U-F4 の公開入口だけを先行接続する | — |
| `docs/design/**`・`docs/adr/**` | **反映なし**。新しいAPI・DTO・画面契約・設計判断を追加しない | — |
| `docs/development/**`・`docs/ops/**`・`docs/README.md` | **反映なし**。既存の開発・運用手順に従う側で、規約や索引を変更しない | — |

**正本体系外だが同一 PR で更新するもの**: `frontend/package.json`、`frontend/pnpm-lock.yaml`、`frontend/src/{App.vue,App.spec.ts,main.ts,appProviders.ts,appProviders.spec.ts,router.ts,router.spec.ts}`、本計画書、`docs/worklog/2026-10-13-uf13-help-entry.md`。

## 4. 実装ステップと合格条件

| ステップ | 作業 | 合格条件 |
| --- | --- | --- |
| 1/2 | `vue-router` を導入し、共有 Pinia・既存 QueryClient とともに起動へ接続する。`/help` と既存トップの経路を定義し、直接到達の Vitest を置く | `/help` の直接表示が成功する。`appProviders.ts` の Pinia instance が共有され、Vue Query は `lib/queryClient.ts` と同一 instance を使う。保護経路や仮画面を登録していない。lint・型検査・Vitest が通る |
| 2/2 | トップからガイドへの導線と `back` emit の遷移を実装し、経路の Vitest を完成させる | 未ログインでガイドを開ける。戻る操作でトップへ戻る。暫定トップはテナントデータ取得を持たない。既存の表示が壊れない。lint・型検査・build・Vitest が通る |

各ステップのコミット件名には規約どおり `(ステップ 1/2)`、`(ステップ 2/2)` を 1 個だけ付ける。実装は承認済みステップだけ進める。

## 5. DoD

| 受入項目 | 成果物・ステップ | 確認 |
| --- | --- | --- |
| 未ログインで `/help` を直接開ける | `router.ts`・`App.vue`、1 | ルータ統合の Vitest |
| トップからガイドへ移動し、戻る操作でトップへ戻れる | `App.vue`、2 | DOM 操作の Vitest |
| 同一の Pinia・QueryClient を全画面の起動へ渡す | `appProviders.ts`・`main.ts`、1 | instance の同一性を調べる Vitest |
| 暫定トップでテナントデータの取得を始めない | `App.vue`・`router.ts`、2 | API import と送信がないことを確認する Vitest・差分確認 |
| U-F13 の残りの認証ガードと `authEpoch` による画面再生成を後続へ渡す | 本計画書・作業ログ、2 | PR 本文の申し送りと変更ファイル一覧 |

Notion タスクは **TSK-528** と確認済み。上表は公開ガイド入口だけの部分 DoD であり、カード全体の DoD ではない。15 経路と catch-all の一致、認証ガード、越境試験は後続で確認する。

## 6. テスト計画とレビュー

NFR-019(a) のドメイン一致性は対象外(状態計算なし)。NFR-019(b) は公開 `/help` と暫定トップにテナント所有データへの取得・表示経路がないことを Vitest と差分で確認する。NFR-019(c) の実戦 E2E は対象外(記録操作なし)。通常のコンポーネント統合試験として直接遷移、クリック遷移、戻る操作、共有 provider を Vitest で検証する。

- 計画レビューで先行分割、公開 `/help`、暫定トップの公開条件を確認済み。依頼者承認は 2026-10-13。
- コア領域に分類して敵対レビューと人間の逐行確認を行う。GitHub の `core-guard` に必要な記録を確認者本人が PR 本文へ記入する。
- PR は `develop` 向けに作り、必須 CI と反対側レビューを通す。マージは人間が行う。
- U-F13 の残りの認証ガード、`authEpoch` による画面再生成、画面ルートは、各画面と認証契約が揃った後の別計画へ申し送る。
