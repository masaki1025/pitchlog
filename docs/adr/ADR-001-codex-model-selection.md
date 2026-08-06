# ADR-001: コーディング委任の Codex モデル・effort 選定

| 項目 | 内容 |
| --- | --- |
| 状態 | **in-review**(PO 承認済み 2026-08-07。確定ゲート〔敵対レビュー〕通過で approved 化 — 1周目指摘 P1-1 により approved から差し戻し) |
| 日付 | 2026-08-07 |
| 決定者 | プロダクトオーナー + Claude(調査・起案) |
| 改訂 | 2026-08-07: PO 指示により effort を調整(通常実装/一次レビュー = max・コア領域 = xhigh・軽作業 = luna xhigh)+ Web 調査行を追加。max の CLI 指定可否を実機検証 |

## 文脈

- 開発ハーネス([設計書](../development/dev-harness-design-2026-08-07.md))はコーディングを Codex に委任する。モデルは GPT-5.6 世代の 3 tier(sol / terra / luna)+ 旧 spark から選ぶ必要があった
- 実測・公式情報(2026-08-07 調査。本機 codex-cli v0.146.1 のモデルカタログ + 公式ドキュメント):
  - `gpt-5.6-sol`: フロンティア。「複雑なコーディング・リサーチで最強」。API $5/$30 per 1M tok、サブスクのクレジット消費は terra の 2 倍
  - `gpt-5.6-terra`: バランス型(公式: everyday workhorse)。API $2/$12。SWE-Bench Pro で sol と **1.2pt 差**(63.4% vs 64.6%)
  - `gpt-5.6-luna`: 高速・安価(消費 sol の 1/5)
  - effort は CLI から **max まで指定可能**(実機検証 2026-08-07: `codex exec -c model_reasoning_effort=max` で実行成功。公式 config リファレンスの記載は xhigh までだが実装は受理する)。対話ピッカー専用なのは Ultra のみ
  - Codex クラウドのコードレビューは公式に sol が担当(2026-07 末〜)
  - 要件フェーズの敵対レビューは sol / sol ultra の実績あり(要件書変更履歴 v1.1 / 1.4 / 1.5)

## 決定

「作業の重さ」で機械的に選ぶ。重さの判定はコア領域リスト(設計書 6.3)で決まり、人が都度迷わない:

| 作業 | モデル(明示 ID 固定) | effort |
| --- | --- | --- |
| 通常実装(CRUD・画面・帳票・テスト) | `gpt-5.6-terra` | **max** |
| 軽微な修正(小さな差分・微調整) | `gpt-5.6-terra` | medium |
| コア領域の実装(同期プロトコル・状況計算・記録権・テナント分離・移行) | `gpt-5.6-sol` | **xhigh** |
| 機械的軽作業(リネーム・ボイラープレート) | `gpt-5.6-luna` | xhigh |
| 一次コードレビュー(通常 PR) | `gpt-5.6-terra` | **max** |
| 敵対レビュー・コア領域 PR・正本確定ゲート | `gpt-5.6-sol` | xhigh(全面監査は人間が対話モードの Ultra で実施) |
| Web 調査(/research) | `gpt-5.6-terra` | high(コア領域に関わる深い技術検証は sol へ引き上げ) |

## 理由

1. **欠陥コストで線を引く**: 試合記録の喪失・クライアント/サーバー計算の乖離(要件書 R-3/R-5・G-1)は取り返しがつかない → コア領域と品質ゲートにフロンティア級(sol)を投じる
2. **物量は terra**: SWE-Bench Pro 1.2pt 差でコスト半分。公式の tier 設計(sol=仕上げと分析、terra=主力)とも一致
3. **レビュー水準の連続性**: 要件フェーズで sol による敵対レビューが成果を出しており、公式のクラウドレビュー担当も sol
4. エイリアス(`gpt-5.6` → sol 行き)は使わず明示 ID で固定(モデルドリフト防止。調査サブエージェントの Opus 5 固定と同じ規律)

## 帰結

- `/implement`・レビュー系スキルが本表どおり `-m <model> -c model_reasoning_effort=<effort>` を自動指定する(設計書 9.4)
- モデル世代交代(tier 名は維持されつつ各 tier が独自更新される)の際は本 ADR を改訂して切り替える
- 見直しトリガー: terra の品質不足に起因する欠陥が実際に出た場合/料金・レート改定/新 tier 登場

## 参照

- 設計書 9.4: [dev-harness-design-2026-08-07.md](../development/dev-harness-design-2026-08-07.md)
- 公式: https://learn.chatgpt.com/docs/models / https://developers.openai.com/api/docs/pricing / https://learn.chatgpt.com/docs/config-file/config-reference
