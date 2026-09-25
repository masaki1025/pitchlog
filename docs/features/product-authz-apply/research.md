---
feature: product-authz-apply
type: research
date: 2026-09-25
---

# 調査メモ: 製品 authz の適用器・実 DB 試験(TSK-424 PR A2)の前提

## 問い

1. 開始条件の **TSK-431 の 7C** とは何で、いまどこまで進んでいるか。`allowed_symbols` の追加にどういう記録が要るか
2. 製品の適用器・カタログ検査を `backend/src` に足すと、迂回検査(`scripts/check_tenant_boundary_bypass.py`)で何が起きるか
3. probe の適用器・カタログ検査・DB fixture・試験のうち、製品版に流用できるものは何か
4. PR A1 の実装で、旧ステップ 13〜21(`git show 96d4132:docs/features/product-authz-surface/plan.md`)の前提から変わった事実は何か

## 結論(要約)

- **7C は TSK-431 = PR #78(OPEN・敵対レビュー中)の是正項目**で、7.7-2 第 3 項(変更前後の実内容の記録)に当たる。**記録の形式は未確定**なので、本計画の `allowed_symbols` のステップは、7C のマージ版で読み直す関門を置く
- 迂回検査は、**基準版と未変更の行で対応する同じ違反だけを相殺する**。したがって**新しい DB 呼び出しは、変更した既存行のものも含めてすべて「増えた違反」**になる。`allowed_symbols` は所属関数の**完全修飾名とシグネチャの完全一致**で効き、**記号 1 件ごとに正例 fixture が 1 件**要る → **DB 呼び出しを少数の末端関数に集め、probe の既存の DB 呼び出し行は変えない**
- 製品の適用は今は拒否される(`PRODUCT_SPEC` の操作の対応が空・staged 資産に手順の宣言が無い)。probe のカタログ検査は `role_kind` と `provisioning_claim` に依存し、製品資産にそのまま使えない → **製品の適用器とカタログ検査は新設のモジュールに置く**
- 流用できるのは、使い捨てクラスタ(`disposable_postgres_cluster`)・故障注入の形(記録点 + monkeypatch)・往復試験の形
- A1 で変わった事実: **トリガ関数は 37 個**(旧版の 33 ではない)/ **秘密の列は 3 件** / staged の件数(下表)

## 詳細と典拠

### 1. TSK-431 の 7C

- 計画書は worktree 側にだけある: `../pitchlog-worktrees/fix-tenant-boundary-baseline/docs/features/tenant-boundary-baseline/plan.md`(`status: active`・`承認: 済(2026-09-24・山田正輝)`)。ブランチ `fix/tenant-boundary-baseline` は **未マージ**、PR #78 は OPEN(`gh pr view 78`・2026-09-25 時点)
- 7C・7D の定義: `docs/features/tenant-boundary-enforcement/plan.md:104-107` — **7C** = `change.before/after` が状態ラベルと射影 digest しか持たず実内容を持たない(7.7-2 第 3 項違反)/ **7D** = `FROZEN_BASELINE_ASSETS` を HEAD 側の一覧だけで走査するので、削除・移動した資産の旧パスの履歴を検査できない
- 7.7-2 の本文: `docs/development/dev-harness-design-2026-08-07.md:581-606`(1 行為 1 記録・新旧の識別値・変えた事柄と前後の内容・事実・理由・承認者・承認日・追記のみ)
- `base-allowlist.json` は凍結基準の 1 つなので、記号の追加は 7.7 の「基準を動かす」行為になり、**7C が入るまで 7.7-2 に適合する記録を書けない**(`../pitchlog-worktrees/fix-tenant-boundary-baseline/docs/worklog/2026-09-24-tenant-boundary-baseline.md:80`)
- **7C の後の記録の見込み(PR #78 の未確定の中身に基づく — 確定ではない)**: `contract_revision` を +1 / `baseline_control.history` に v2 記録 1 件(`record_schema_version: 2`・`acceptance_id: "{repo}#{PR番号}"`・`change{subject, aspect[], before/after}`・`movement_fact`・`reason`・`approved_by`・`approved_on`)/ `contracts/tenant_boundary/history-snapshots/<sha256>` に変更前後の内容 / **PR 受理モードのため draft PR を先に作って番号を確定する**(同 worktree の `design.md:47-55・82-93・113-126`)
- `allowed_symbols` へ追加する手順そのものを書いた文書は**見つからない(不明)**

### 2. 迂回検査の数え方

- `allowed_symbols` の要素は `{symbol, signature, allowed_api_ids, fixture}`(`scripts/check_tenant_boundary_bypass.py:935-966`)。`allowed_api_ids` は inventory(`contracts/tenant_boundary/db-api-inventory.json`)の id に限る(`:946-951`)。**記号がソースに存在するかは読み込み時に検査しない**(`:931-973` に存在の検査が無い)
- 正例 fixture(`tests/fixtures/tenant_boundary/positive/**/*.py`)の集合は `allowed_symbols[].fixture` と完全一致が必要(`:1401-1412`)
- TB005: 所属関数の完全修飾名とシグネチャが `symbol` / `signature` に**完全一致**し、呼び出す DB API の id がその記号の `allowed_api_ids` に含まれるときだけ通す(`:2759-2766・2803-2821`)
- **増えた違反の判定**: 基準版の違反と相殺できるのは「同じ所属シンボルにあり、旧新の未変更行が対応する同一 AST 範囲」だけ(`:3383-3470` の docstring と `difflib.SequenceMatcher` による行対応)。**既存の DB 呼び出しの行を変えると、その行も新しい違反になる**
- 今の `allowed_symbols` は 5 件で、すべて `pitchlog.db.engine.*` と `pitchlog.repositories.*`(`contracts/tenant_boundary/base-allowlist.json`)。**probe の適用器・カタログ検査の DB 呼び出しは登録されておらず、基準版の既存違反として相殺されている**
- 使える API の id(抜粋): `PSYCOPG_CONNECTION_CURSOR`・`PSYCOPG_CONNECTION_EXECUTE`・`PSYCOPG_CONNECTION_COMMIT`・`PSYCOPG_CONNECTION_ROLLBACK`・`PSYCOPG_CURSOR_EXECUTE`(`contracts/tenant_boundary/db-api-inventory.json`)
- 検査の対象は `backend/src` だけ(`contracts/tenant_boundary/base-allowlist.json:75` の差分の対象パス・`scripts/check_tenant_boundary_bypass.py:3536・3575` の `backend/src/` 接頭辞)。**試験(`backend/tests`)の DB 呼び出しは対象外**

### 3. 流用できる既存の仕組み

- probe の適用器: 入口 `apply_authz_ddl(connection, root, spec=PROBE_SPEC)`(`backend/src/pitchlog/authz/provisioning.py:708`)。接続の前提(閉じていない・autocommit 無効・IDLE)を検査(`:682-685`)。**手順ごとに commit**(`:464-479`)。操作種別は spec ごとの閉じた対応(`:256`・`:301-302`)、probe は 5 種(`asset_spec.py:235-258`)
- **`PRODUCT_SPEC` での適用は今は拒否される**: `PRODUCT_SPEC.operation_handlers=()`(`asset_spec.py:293`、試験 `backend/tests/test_authz_provisioning_spec.py:145-146`)。staged 資産に `provisioning_claim` が無く `provisioning.py:273` で止まる。製品の roles は `role_kind` を持たず `_external_provisioner`(`:171-180`)でも失敗する
- probe のカタログ検査 `inspect_authz_catalog`(`backend/src/pitchlog/authz/catalog.py:1400`): spec を使うのは資産パスと生成器だけ(`:1427`・`:474`)。`role_kind`(`:799-806`)と `provisioning_claim.completion_catalog_expectations`(`:1196-1210`)に依存。関数定義の期待は同じクラスタの参照 DB から読む(`:483-491`)
- fixture: `disposable_postgres_cluster`(`backend/tests/db_fixtures.py:571` — docker・乱数の superuser)/ `provisioned_catalog`(`:634` — `PROBE_SPEC` 固定・参照 DB と本体 DB の両方に適用)/ DSN の env 名 `PITCHLOG_TEST_ADMIN_DSN`・`PITCHLOG_TEST_ROLE_DSN`(`backend/tests/db/environment-expectations.json:197,205`)/ `backend/tests/db/conftest.py` は再エクスポートと「DB 必須試験が 0 件」で red にするフック(`:57-119`)
- 故障注入: `contracts/authz/failure-injection-points.json`(probe の `ddl-elements.json` に blob digest で紐づく 5 点)。試験は `_CheckpointRecorder.record` を monkeypatch して指定の記録点の直後に例外を投げ、失敗前 A・失敗後 B・再適用後 C を観測する(`backend/tests/db/test_authz_failure_injection_points.py:292・300-358`)
- 往復: `backend/tests/db/test_migration_round_trip.py:52-93`(使い捨てクラスタで upgrade head → base → head、表集合と revision を exact で照合)
- `runtime_contract.py` は暫定のランタイム契約(`PROVISIONAL=True`・`SUPERSEDED_BY="contracts/authz/product/ddl-elements.json"`)。切り替えは PR B = TSK-443。**最終パスを作ると二状態検査が発火する**(`backend/tests/test_authz_runtime_contract.py:200`)

### 4. A1 の実装で変わった事実

- **トリガ関数は 37 個**。暫定契約の 33 個に migration 0015・0016・0017・0024 の 4 個が漏れていた(`docs/features/product-authz-surface/plan.md` 4 節の実装時の訂正)。旧ステップ 14・19 の「33 個」は 37 個へ読み替える
- **秘密の列は 3 件**(`tenant_credentials.password_hash`・`admin_credentials.password_hash`・`group_invitations.code_hash`)。`tenant_tokens.id`・`admin_sessions.id` は典拠が無いので除いた(同 4 節の人間の判断)
- staged 資産 `contracts/authz/product/ddl-elements.staged.json` の件数(`function-bodies/manifest.json` と一致):

| 種別 | 件数 |
| --- | --- |
| roles | 4 |
| databases | 1 |
| schemas | 2 |
| tables | 45 |
| predicates | 1 |
| policies | 32 |
| functions | 38(トリガ 37 + 補助関数 1) |
| acl_expectations | 28 |
| column_acl_expectations | 8 |

  あわせて `membership_edges` 0 件・`permanent_privileged_role_ids = ["pitchlog_owner"]`・scope `{status: product_configuration, product_schema: true}`・`pending_switch: TSK-443`。**`provisioning_claim` と `transaction_boundaries` は無い**

## 未解決・申し送り

- **7C の記録形式は PR #78 のマージまで確定しない** → 計画書 4 節の関門で扱う
- `allowed_symbols` への追加手順の文書は無い(不明)。7C のマージ版の検査器と試験から読み取る
