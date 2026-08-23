---
description: 品質ゲート一括実行(フォーマット・リント・型・テスト — 存在するものだけ)
argument-hint: "[対象ディレクトリ(省略時はカレント)]"
---

# 品質チェック一括(設計書 10.1 のローカル版)

対象ディレクトリ(worktree)で以下を**存在するものだけ**順に実行し、結果を表で報告する。存在しない層は「スキップ(未導入)」と明記する。

## harness(ルート `pyproject.toml` がある場合、リポジトリルートで)

1. `uv run ruff check .`
2. `uv run ty check`
3. `uv run pytest tests/`(hooks・ラッパーの単体テスト)

<!-- ルートには formatter を導入していない。`ruff format` は走らせないこと(別 PR の follow-up)。
     検査対象は pyproject.toml の extend-exclude と [tool.ty.src] include で scripts/ と tests/ に
     限定してある。backend/ は backend ジョブ、.claude/ は未導入(H-13 の残余)。 -->

## backend(`backend/pyproject.toml` がある場合、backend/ で)

1. `uv run ruff format --check .`
2. `uv run ruff check .`
3. `uv run ty check`
4. `uv run pytest`

## frontend(`frontend/package.json` がある場合、frontend/ で)

1. `pnpm exec prettier --check .`
2. `pnpm exec eslint .`
3. `pnpm exec vue-tsc --noEmit`
4. `pnpm test -- --run`

## docs

- 今回変更した markdown の相対リンクが実在するファイルを指しているか確認する

## 報告

| 層 | チェック | 結果 |の表。失敗があれば原因を特定して修正方針を提示する。自動で直してよいのはフォーマットのみ。それ以外は /implement の差し戻し(Codex 実装分)か人間の判断を仰ぐ。
