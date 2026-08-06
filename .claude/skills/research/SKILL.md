---
description: Web 技術調査を Codex に委任する(read-only + live search)。結論と参照 URL を記録する
argument-hint: "<調査したいこと>"
---

# Web 調査の Codex 委任(設計書 9.2 / ADR-001)

## 実行

モデルは ADR-001: 既定 `gpt-5.6-terra` + high。コア領域に関わる深い技術検証は `gpt-5.6-sol` + xhigh に引き上げる。

```bash
codex exec --skip-git-repo-check --ignore-user-config -s read-only \
  -m gpt-5.6-terra -c model_reasoning_effort=high -c web_search="live" \
  -o <scratchpad の一時ファイル> "<調査指示>"
```

- 調査指示には必ず含める: 「参照した URL を明記」「公式ドキュメント優先」「情報の公表日を確認し新旧仕様の混在に注意」
- 大きい調査はバックグラウンド実行にして他の作業を続ける
- 危険フラグ(danger-full-access / --yolo)は使わない(codex_guard が機構的にブロックする)

## 記録

結論の要約と参照 URL を、feature 調査なら `docs/features/<slug>/research.md`、単発なら当日の worklog に記録する。Codex の出力は鵜呑みにせず、重要な事実は URL を自分でも確認してから正本・計画書に採用する。
