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

## ステップ 1: draft PR の番号確定と承認記録の出所(2026-09-26)

### draft PR

**`masaki1025/pitchlog#82`**(https://github.com/masaki1025/pitchlog/pull/82)。

凍結基準の v2 記録は `acceptance_id` = `{repository.full_name}#{pull_request.number}` を要求する
(`../features/tenant-boundary-baseline/plan.md:111`。実例は `contracts/tenant_boundary/base-allowlist.json:72` の
`masaki1025/pitchlog#78`)。**ステップ 4 より前に番号が確定している必要がある**ため、ステップ 1 で開いた。

> **【承認後の追記 — 2026-09-26】** 承認済み計画のステップ 1 は「承認記録の出所を確定し記録する」だけだったが、
> **PR 番号の確定が抜けていた**。TSK-446 でも同じ壁に当たっており(あちらはステップ 1 で draft PR を開く設計だった)、
> **本計画はその教訓を写し損ねていた**。ステップ 1 の内容へ折り込んだ(ステップ数は増やしていない)。

### 承認記録の出所 — 人間の裁定(逐語)

> kimete承認

- **取得元**: 2026-09-26 の Claude Code セッションでの発話
- **決まったこと**: 7 節の未決 2 件を当方が確定させ、計画書を承認する
- **確定した方式**: **凍結基準の承認記録の出所は、本 PR(#82)へのコメントとする**

### なぜコメントなのか(TSK-446 の実績に基づく)

`allowed_symbols` は凍結基準で、**7.7-2 が承認者・承認日を要求する**
(`docs/development/dev-harness-design-2026-08-07.md:596`)。

**PR の自己承認は GitHub が拒否する**:

```
failed to create review: GraphQL: Review Can not approve your own pull request
```

→ **単独メンテナの体制では `APPROVED` review を出所にする統制が原理的に成立しない。**
この知見は TSK-446 で得られ、`docs/development/harness-evaluation.md` の `## 候補` に記録済み。
**規律そのものの見直しは TSK-458** が扱う。

**コメントなら成立する**: 自分の PR にも書け、**`user.login`(認証済み発信者)と
`created_at`(GitHub 側のタイムスタンプ)が機械可読**で、本文に**氏名・日付・対象**を含められる。

### ステップ 4 の直前に行うこと

1. **人間が** PR #82 へ次の形のコメントを投稿する:

```
凍結基準 base-allowlist.json の allowed_symbols へ
pitchlog.repositories.transaction.tenant_transaction_scope を追加することを承認する。
承認者: <氏名>。承認日: <YYYY-MM-DD>。
```

2. **当方が** `gh api repos/masaki1025/pitchlog/issues/82/comments` から**逐語転記**し、
   `reason` に **API パス・comment id・`created_at`** を出所として書く

**推定値を 1 つも入れない。** 取得できなければ **7.7-3 の fail-closed に従い停止する**
(`dev-harness-design-2026-08-07.md:607-610`)。

### 機械側の強制(TSK-431 の 7C・PR #78 でマージ済み)

```
scripts/frozen_history.py:39-41   予約 marker を拒否 {"PENDING","TODO","TBD","未承認","未定","レビュー待ち"}
scripts/frozen_history.py:1521    approved_by は非空・approved_on は実在する ISO 日付
```

**プレースホルダは書けない。** TSK-446 で 3 周連続 P0 になった論点が、機構で塞がれている。
