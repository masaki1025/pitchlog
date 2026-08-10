---
description: 実装計画書を固定フォーマットで作成・記入する(計画書ゲートの起点)
argument-hint: "<feature slug または plan.md のパス>"
disable-model-invocation: true
---

# 実装計画書の作成(設計書 6.1 — 固定フォーマット)

対象: `docs/features/<slug>/plan.md`(なければ `docs/development/templates/plan-template.md` から作成)。

## 記入規則(6 節すべて必須・空欄禁止)

1. **背景・目的**: Notion タスクと要件 FR/NFR へのリンクを必ず含める
2. **スコープ**: やること/やらないことを分けて書く
3. **影響する正本**: 更新・新設する正本を表で列挙する。**「反映なし」も明示**(/pr がこの宣言と PR 内容を突合する)
4. **実装方針**: frontmatter の重さ分類(軽微/通常/コア領域/機械的軽作業)の根拠を明記する。コア領域(CLAUDE.md の列挙)に触れるかを必ず判定する。**「実装ステップ(コミット単位)」の表を必須で埋める**(1 ステップ = 1 委任 = 1 コミット — 設計書 6.1 段階実装。/implement がこの表を上から実行し、ラッパーは表の無い計画書を拒否する。番号列は 1 からの連番)
5. **DoD**: Notion タスクの DoD と同期させる
6. **テスト計画**: NFR-019 のどのテスト種別(単体・一致性・越境・E2E・故障系)に何を足すか

- 下調べが不足していれば先に /investigate を実行し、research.md の結論を典拠として引用する
- **密度が高くなる場合は design.md へ分離する**(plan = 契約 / research = 調査 / design = 詳細設計 — 設計書 6.1 の 3 ファイル役割分担): 詳細設計・長文の検討は `docs/features/<slug>/design.md`(テンプレ: `docs/development/templates/design-template.md`)に書き、plan 4 節からは相対リンクで参照する(内容を複製しない)。機構が読む状態と実装ステップ表は plan.md のみに置く

## レビューと承認

1. 記入後、レビューへ(ラッパー経由。計画書全文+検証観点をプロンプトで渡す):
   - **通常**: `python .claude/scripts/codex_run.py review normal -`
   - **コア領域**: `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映し、収束したら**人間の承認を明示的に求める**。レビュー 1 周(指摘反映まで)ごとに frontmatter の `計画レビュー周回` を +1 する(feature_status.py が現在地表示に使う)
3. 承認されたら frontmatter を `承認: 済(YYYY-MM-DD・承認者)` に更新し、計画書をコミットする(**起票コミットにはステップ記法「(ステップ k)」を付けない** — 計画系コミットとして進捗導出から除外される)。あわせて Notion タスクへ計画書リンクと承認日をコメントで記録する(ステータスは 進行中 のまま — `.claude/notion-map.json`)

**計画承認前に /implement は実行できない**(implement 側でもチェックされる)。
