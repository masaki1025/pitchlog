---
description: Web 技術調査を Codex に委任する(read-only + live search、ラッパー経由)。結論と参照 URL を記録する
argument-hint: "<調査したいこと>"
---

# Web 調査の Codex 委任(設計書 9.2 / ADR-001)

実行はラッパー経由のみ(read-only + `web_search="live"`。モデル・effort は ADR-001「決定」節の「Web 調査」行をラッパーが固定。コア領域に関わる深い技術検証は `--deep` — 同「Web 調査(深い技術検証 `--deep`)」行)。

```bash
python .claude/scripts/codex_run.py research - <<'EOF'
<調査指示>
EOF
```

- 調査指示に必ず含める: 「参照した URL を明記」「公式ドキュメント優先」「情報の公表日を確認し新旧仕様の混在に注意」
- 大きい調査はバックグラウンド実行にして他の作業を続ける

## 記録

結論の要約と参照 URL を、feature 調査なら `docs/features/<slug>/research.md`、単発なら当日の worklog に記録する。Codex の出力は鵜呑みにせず、重要な事実は URL を自分でも確認してから正本・計画書に採用する。
