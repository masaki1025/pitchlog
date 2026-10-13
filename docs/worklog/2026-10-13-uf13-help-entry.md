---
date: 2026-10-13
topic: U-F13 公開ガイド入口の独立先行案
branch: feature/uf13-help-entry
---

# U-F13 公開ガイド入口の計画準備

`origin/develop` の `212379b5` から専用 worktree を作成。U-S1 と PR #119・#120・#121・#122 に依存しない候補として、完成済み U-F4 の `/help` 接続を選んだ。依頼者は 2026-10-13 に U-F13 の先行分割と、テナントデータを取得・表示しない現行トップの暫定公開を承認した。

## 計画レビュー 1 回目

`codex_run.py review adversarial` で P0 0 件、P1 3 件、P2 0 件。受理 3 件とも計画へ反映した。

| 指摘 | 反映 |
| --- | --- |
| DoD とテスト計画がない | 計画書 5・6 節に成果物・ステップ・試験との対応を追加。既存 U-F13 の Notion タスクを特定し、DoD 同期は承認前条件として明記 |
| provider の instance 契約が不足 | 共有 Pinia の生成・公開と既存 `queryClient` の再利用をステップ 1 の合格条件へ追加。`authEpoch` 配線は後続へ |
| 暫定トップの認証条件が曖昧 | テナント所有データを読まない現状に限る暫定公開として、人間承認対象・テスト条件を明示 |

差分レビュー 2 回目は P0・P1 の追加指摘なし。初回の 3 件は計画に反映済み。

Notion の U-F13 タスク URL は U-F2 の作業ログから得たが、現在の接続による fetch は `object_not_found`(404)。担当と DoD は検証できない。

`origin/develop` を再取得し、`9114a5a6` へ fast-forward。追加分は PR #122 の試合区分 seed・認可資産で、本計画の変更対象ファイルには差分なし。専用 worktree・ブランチは他セッションと重複せず、本セッションで担当する。Notion タスクの担当と固有 DoD は依然未確認で、依頼者が残余として了承した。

## 実装ステップ 1/2

`vue-router` 4.6.4 を既存の移植規則に合わせて追加した。`main.ts` から共有 Pinia、既存の QueryClient、router を起動時に install する。既存トップを `/`、完成済みガイドを `/help` に登録し、`/help` への直接到達と provider の instance 同一性を Vitest で確認した。既存の App テストも router を使う起動構成に合わせた。認証ガード、未完成画面、API・DTO、トップからの導線、ガイドの戻る遷移はこのステップに含めていない。

検証結果: フロントエンド Vitest 50 ファイル・864 件成功、ESLint 成功、`vue-tsc --noEmit` 成功、Prettier check 成功、`pnpm build` 成功、`git diff --check` 成功。最初の sandbox 実行では子プロセスを使う既存テストが `EPERM` になったため、権限付きで同じ全件テストを再実行して成功した。

## 正式カードとの差分と後続への申し送り

依頼者が別接続で正式カードを取得し、U-F13 は [TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350) と確認した。今回の `/help` 公開入口は TSK-528 の部分実装であり、カード全体を完了にしない。

後続には、移植規則に定めた **15 経路と catch-all の path・認可条件の一致**、U-F2 の hydration・`isAuthenticated`・`authEpoch` を使う**認証ガード**、テナント境界を確認する**越境試験**が残る。今回追加した `vue-router` はコア領域として扱い、PR では敵対レビューと人間の逐行確認、`core-guard` の記録を維持する。

## 実装ステップ 2/2

トップへ公開ガイドの導線を追加し、`HelpScreen` の `back` emit を名前付き `home` route への遷移へ接続した。共有 Pinia・既存 QueryClient を install した状態で、未ログインの `/help` 直接到達とトップ→ガイド→トップの往復を Vitest で検証する。往復中に `fetch` が呼ばれないことも確認し、暫定トップがテナントデータを取得しない条件を固定する。

検証結果: フロントエンド Vitest 50 ファイル・865 件成功、ESLint 成功、`vue-tsc --noEmit` 成功、Prettier check 成功、`pnpm build` 成功、`git diff --check` 成功。ビルド時の依存閉域検査も `conforming`。共有 provider の instance 同一性テストは継続して成功し、往復テストでは同じ Pinia store instance が維持された。

PR 段階の残ゲート: `vue-router` 追加を含むためコア領域として敵対レビューを実施し、人間の逐行確認と `core-guard` の確認記録を得る。これは TSK-528 全体の完了条件とは別であり、今回の部分実装をカード完了として扱わない。

## 結果サマリ（Draft PR 準備）

- U-F4 の静的ガイドを公開 `/help` へ接続し、トップからの導線と `back` emit によるトップ復帰を実装した。
- 共有 Pinia と既存 QueryClient をアプリ起動へ接続し、instance の同一性、未ログインの直接到達、往復操作、暫定トップで通信が発生しないことを Vitest で確認した。
- 正本の改訂はない。TSK-528 全体では 15 経路と catch-all、認証ガード、越境試験が未実装であり、本 PR はカードの部分充足として扱う。
- ハーネス運用評価台帳への追記なし。本作業で発生した sandbox の子プロセス制限は既知の実行環境差であり、製品ハーネスの新たな傾向・欠陥を示す知見ではないため。
- `vue-router` の依存追加がコア領域 paths に該当する。敵対レビュー、人間の逐行確認、`core-guard` の記録は Draft PR 上で完了させる。

## Draft PR #123 レビュー

- Claude 一次レビューは weekly limit で実行不能。依頼者が 2026-10-13 に、この PR に限って Codex による代替レビューを明示承認した。
- コア領域の敵対レビュー 1 回目（全文）: **否決（P0 0 / P1 1 / P2 0）**。P1 は、`/help` の直接到達テストがメモリ履歴へ事前に push しており、Web 履歴の初期 URL と HTTP 配信を実測していない点。採用し、計画を `active` へ戻して修正する。
