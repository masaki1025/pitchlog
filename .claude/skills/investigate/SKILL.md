---
description: 実装計画段階のリポ内調査。調査サブエージェント3本を並列で投げ、典拠付きの調査メモを作る
argument-hint: "<調査テーマ>(feature slug があれば併記)"
---

# 計画段階の調査(設計書 8.5)

## 手順

1. $ARGUMENTS のテーマを観点に分解し、調査サブエージェントへ**並列で**委任する(**既定 3 並列**。軽い単発確認は 1 本、広域監査は増やす — 作業の重さで調整):
   - **spec-checker**: 要件(FR/NFR・付録・改善台帳)との突合
   - **legacy-analyst**: 旧システムの実挙動・移行制約(88列は data-layer.md が正)
   - **decision-tracer**: 過去の決定(D-xx・I-xx・ADR・変更履歴)との整合
2. Web の技術調査が必要なら /research を併用する(Codex 委任 — リポ内調査と Web 調査を混ぜない)
3. 結果を `docs/features/<slug>/research.md`(テンプレ: `docs/development/templates/research-template.md`)に統合する:
   - **すべての事実に典拠**(ファイル:行 or URL)。典拠のないものは「不明」と書く
   - エージェント間で矛盾する報告があれば、原典を自分で確認して裁定する
4. /plan の該当節から research.md を参照させる

feature に紐づかない単発調査は worklog に記録して終える。
