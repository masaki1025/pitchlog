---
feature: mvp-interference-csv-display
status: active
branch: fix/mvp-interference-csv-display-20261109
承認: PO委任 root の限定判断（2026-11-09 00:51 JST、計画 SHA256 48308b1db95989d10281ed2373bbdb4e2987b6c683c1d2f8e86d1ec861269fea）
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 妨害の副結果だけで完了した打席の CSV 表示

`40366224` の隔離実画面初球は、妨害罰則の保存時に 88 列 producer の打席結果表示で 503 になった。唯一 T1 は打席完了、物理主結果は NULL、副結果は正式 `secondary-result.batting-interference` であり、既表示生成器は主結果名を必須として拒否する。旧 SQL 42703 の修復とは別の停止点として保全する。

## 編集範囲

`backend/src/pitchlog/exports/record_projection.py`、対応する専用 pytest とこの計画だけを編集する。正式語彙・生成表示モデル・共有 SQL・認可・台帳は編集しない。

## 実装ステップ

| # | 単位 | 完了条件 |
|---|---|---|
| 1 | 閉じた副結果表示 | 真正 request の `resultId`・`interferenceRuling` と物理副結果が一致し、主結果が NULL の妨害罰則・走塁妨害・守備妨害だけ、記録時 admin 語彙 `display_name` を既 `plate_result_display` に渡す。実プレイ採用の主結果と通常/NP/未知は維持する |
| 2 | 純対向と候補保全 | 実859原本の三正例と実プレイ採用、欠語彙・別副結果・別裁定・偽主結果・未知値の負例を pytest で確認し、source と差分 SHA を固定する。実 PG は別の根拠付き再走へ分離する |

語彙名を文字列で決め打ちせず、元 V7 の request / 物理行 / 記録時語彙だけを使う。結果の選択に新しい野球計算を追加しない。

## 候補検査

実859原本から生成した妨害罰則・走塁妨害・守備妨害の物理行は、主結果 NULL / 副結果と T1 `resultId` 一致 / 打席完了 true だった。実プレイ採用は主結果を維持した。副結果相違、未知値、裁定相違、採用側相違、観測不一致、欠落・disabled・分類違いの語彙を拒否する純対向を追加した。関連 CSV 純検査は 139 passed、Ruff/Ty は対象 2 path で 0 件。初回の依存未設置による生成器赤 18 件は、同 WT の offline `pnpm install` 後に全件通過した。実 PG の再走はこの候補単独では行っていない。
