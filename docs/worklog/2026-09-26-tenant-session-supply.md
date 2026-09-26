---
date: 2026-09-26
topic: TenantRepositoryBase._session を満たす Session の供給(TSK-444 / TSK-424 PR C)
branch: feature/tenant-session-supply
---

# 作業ログ: 2026-09-26 TenantRepositoryBase._session を満たす Session の供給(TSK-444 / TSK-424 PR C)

## やったこと

- **着手**(/task-start)。`origin/develop` = `b4ae7394`(PR #78 = TSK-431 のマージを含む)起点で worktree を作成
- **開始条件の確認**: カードは「**TSK-431 の 7C のマージ**」を開始条件に挙げており、
  **PR #78 が develop へ入っている**ことを実測した(`b4ae7394 Merge pull request #78 from masaki1025/fix/tenant-boundary-baseline`)
- Notion カードに **DoD 欄が無かったので追加**した(横断要求のチェックのみ存在していた)

## 決定

- **重さ分類 = コア領域**。カード自身が「コア領域(テナント分離)→ 敵対レビュー + 人間の逐行確認」を横断要求に挙げており、
  **`base-allowlist.json`(凍結基準)を動かす**ことも明記されている
- **slug = `tenant-session-supply`**。既存の `feature/tenant-boundary-enforcement`・`feature/product-authz-surface` と同じ語彙圏に置く

## 未決・次の一歩

- **/investigate**。中心は次の 3 点:
  1. **トランザクションの単位をどう公開するか** — U-T1 ステップ 9(基底の公開シンボルは exact-set・生 Session と任意クエリを公開しない)と、
     ステップ 8(業務トランザクションの発行 SQL 列の先頭が束縛文)を同時に満たす形
  2. **FR-018 の並行性をどう満たすか** — カードが 2 案を挙げて「計画で比べて決める」としている。
     (a) 行ロック(`SELECT ... FOR UPDATE`)を capability の検査が許すノードの型に入れる /
     (b) 判定と削除を 1 つの operation にまとめ、その operation にだけ宣言付きで複数表の参照を許す。
     **「1 operation = 1 表」は緩めない**のが前提
  3. **凍結基準の動かし方** — `allowed_symbols` への追加を 7.7-2 に適合する形で記録する。
     **TSK-446 で `approved_by` / `approved_at` の出所が取れず敵対レビューが 3 周連続 P0 を出した**ので、
     **今回は着手前に承認記録の出所を決めておく**(TSK-458 が規律そのものを扱う)
- **待っている単位**: DB を使う全単位(帯 2 の葉 6 本・帯 3 の 6 本)。とくに **U-M1(TSK-393)の依存 3 と 8** を本タスクが外す
