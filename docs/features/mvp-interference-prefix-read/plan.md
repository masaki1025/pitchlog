---
feature: mvp-interference-prefix-read
status: active
承認: 済（PO 委任 Codex 主担当 / root、2026-11-09）
重さ分類: コア領域
branch: fix/mvp-interference-prefix-read-20261109
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 妨害の保存済み v3 行を閉じて再取得する

実 POST 200・accepted 1 の後、同じ試合の v3 GET が 503 になる固定診断を起点とする。公開 route は原例外を 503 に包むため、読取 source の型分岐を修復し、実 GET 成功は別の隔離実測で確認する。

## 編集所有

`backend/src/pitchlog/repositories/ordinary_prefix_read.py`、`backend/src/pitchlog/api/schemas/started_games.py`、`frontend/src/api/startedGame.ts`、`frontend/src/api/lineupPrefixGame.ts`、これらの専用 BE/FE 試験と本計画のみ。正式 SQL・契約・認可・他 WT は変更しない。

## 実装ステップ

| # | 単位 | 到達条件 |
|---|---|---|
| 1 | 保存観測の読取 | INT 3 観測型の真正 course を使用し、既型を保持、未知型を拒否する |
| 2 | 閉じた公開行 | 主結果が null の INT 罰則・裁定だけを v3 専用の有限副結果行として BE/FE に追加し、実プレイ採用は旧主結果行を使用する |
| 3 | 検査と候補固定 | 唯一 mapper の原41列から正負を試験し、旧 DTO/codec 回帰・型・lint を確認する。PG/ブラウザは root の次の隔離実測へ分離する |

実保存原本の独立再評価、41列一致、tenant、資格と拒否順は既 reader のまま維持する。`no-pitch` 形は現在の INT 観測が全て pitch/course を必須にするため追加しない。主結果あり・副結果不一致・course 欠落・未知型は閉拒否する。
