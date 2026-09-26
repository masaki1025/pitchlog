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

- 計画書は worktree 側にだけある: `../pitchlog-worktrees/fix-tenant-boundary-baseline/docs/features/tenant-boundary-baseline/plan.md`(`status: active`・`承認: 済(2026-09-24・山田正輝)`)。~~ブランチは未マージ、PR #78 は OPEN(2026-09-25 時点)~~ → **2026-09-26 にマージ済み(`b4ae7394`)。本節の以後の「見込み」は下部の追補が置き換える。**
- 7C・7D の定義: `docs/features/tenant-boundary-enforcement/plan.md:104-107` — **7C** = `change.before/after` が状態ラベルと射影 digest しか持たず実内容を持たない(7.7-2 第 3 項違反)/ **7D** = `FROZEN_BASELINE_ASSETS` を HEAD 側の一覧だけで走査するので、削除・移動した資産の旧パスの履歴を検査できない
- 7.7-2 の本文: `docs/development/dev-harness-design-2026-08-07.md:581-606`(1 行為 1 記録・新旧の識別値・変えた事柄と前後の内容・事実・理由・承認者・承認日・追記のみ)
- `base-allowlist.json` は凍結基準の 1 つなので、記号の追加は 7.7 の「基準を動かす」行為になり、**7C が入るまで 7.7-2 に適合する記録を書けない**(`../pitchlog-worktrees/fix-tenant-boundary-baseline/docs/worklog/2026-09-24-tenant-boundary-baseline.md:80`)
- **7C の後の記録の見込み(PR #78 の未確定の中身に基づく — 確定ではない)**: `contract_revision` を +1 / `baseline_control.history` に v2 記録 1 件(`record_schema_version: 2`・`acceptance_id: "{repo}#{PR番号}"`・`change{subject, aspect[], before/after}`・`movement_fact`・`reason`・`approved_by`・`approved_on`)/ `contracts/tenant_boundary/history-snapshots/<sha256>` に変更前後の内容 / **PR 受理モードのため draft PR を先に作って番号を確定する**(同 worktree の `design.md:47-55・82-93・113-126`)
- `allowed_symbols` へ追加する手順そのものを書いた文書は**見つからない(不明)**

### 2.(**行番号は PR #78 で全面的にずれたため、2026-09-26 に節番号・関数名へ書き換えた。事実そのものは成立している**)迂回検査の数え方

- `allowed_symbols` の要素は `{symbol, signature, allowed_api_ids, fixture}`(`scripts/check_tenant_boundary_bypass.py` の `_load_allowlist`)。`allowed_api_ids` は inventory(`contracts/tenant_boundary/db-api-inventory.json`)の id に限る(`:946-951`)。**記号がソースに存在するかは読み込み時に検査しない**(`:931-973` に存在の検査が無い)
- 正例 fixture(`tests/fixtures/tenant_boundary/positive/**/*.py`)の集合は `allowed_symbols[].fixture` と完全一致が必要(同 `_load_allowlist` の正例 fixture 集合の一致検査)
- TB005: 所属関数の完全修飾名とシグネチャが `symbol` / `signature` に**完全一致**し、呼び出す DB API の id がその記号の `allowed_api_ids` に含まれるときだけ通す(同 TB005 の判定)
- **増えた違反の判定**: 基準版の違反と相殺できるのは「同じ所属シンボルにあり、旧新の未変更行が対応する同一 AST 範囲」だけ(同 `scan_source_change` の docstring と `difflib.SequenceMatcher` による行対応)。**既存の DB 呼び出しの行を変えると、その行も新しい違反になる**
- 今の `allowed_symbols` は 5 件で、すべて `pitchlog.db.engine.*` と `pitchlog.repositories.*`(`contracts/tenant_boundary/base-allowlist.json`)。**probe の適用器・カタログ検査の DB 呼び出しは登録されておらず、基準版の既存違反として相殺されている**
- 使える API の id(抜粋): `PSYCOPG_CONNECTION_CURSOR`・`PSYCOPG_CONNECTION_EXECUTE`・`PSYCOPG_CONNECTION_COMMIT`・`PSYCOPG_CONNECTION_ROLLBACK`・`PSYCOPG_CURSOR_EXECUTE`(`contracts/tenant_boundary/db-api-inventory.json`)
- 検査の対象は `backend/src` だけ(`contracts/tenant_boundary/base-allowlist.json:75` の差分の対象パス・同検査器の `backend/src/` 接頭辞による絞り込み)。**試験(`backend/tests`)の DB 呼び出しは対象外**

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

- ~~**7C の記録形式は PR #78 のマージまで確定しない**~~ → **確定済み(2026-09-26)。下部の追補が正。**
- `allowed_symbols` への追加手順の文書は無い(不明)。7C のマージ版の検査器と試験から読み取る

---

## 追補: 7C のマージ後の実測(2026-09-26)— 関門 1・2 の照合結果

**TSK-431(PR #78)は `b4ae7394` でマージ済み**(2026-09-26 10:56 JST)。**本 worktree の HEAD はそのマージコミットを含む**(`git merge-base --is-ancestor b4ae7394 HEAD` が真 — 実測)。**計画書 4 節の関門 1 は充足。**

**本節が `research.md` 1 節の「見込み」を置き換える。** 以下はすべて develop の実物と `scripts/frozen_history.py` の実装からの実測であり、見込みではない。

### 裁定(調査 3 本の報告が割れたため原典で判定)

**改訂と承認の取り直しは不要。** 根拠は `plan.md:80` の逐語。

> 違えば、計画書を改訂し、承認を取り直してから実装する。**history-snapshots の exact な変更パスはこの照合で確定し、ステップ 2 の合格条件に書き足す**

**計画書自身が「照合で確定して書き足す」経路を持つ。** かつ `plan.md:98` のステップ 2 の合格条件は「**7.7-2 の記録が 7C の検査器で受理される**」であり、**記録の構造は検査器が決める**形である。**構造を計画書へ書き写す設計ではない。**

**ただし下記 4-1 の陳腐化 4 件は事実の誤りなので訂正が要る。**

### 1. v2 record の必須キー(exact-set・過不足いずれも不可)

`scripts/frozen_history.py:_validate_v2_record` が `_strict_keys` へ渡す集合。

```
record_schema_version / acceptance_id
new_baseline_identifiers / previous_baseline_identifiers
change / movement_fact / reason / approved_by / approved_on
```

**v1 との差**: `source_commit` が**消え**、`record_schema_version` と `acceptance_id` が**入る**。

**`research.md` 1 節の見込みには `new_baseline_identifiers` / `previous_baseline_identifiers` が無かった。** exact-set 検査なので**欠けると即 red**。

### 2. 識別値は「資産パス → 識別値配列」の map(7 資産分)

**v1 は文字列配列**(`["contract_revision:13"]`)だが、**v2 は 7 資産すべてを鍵に持つ map**。`_validate_repository_identifier_record` が **7 資産の実 `current_identifiers` と完全一致**を要求する。

**現在値(develop 実測)**

| 資産 | `history_authority` | `current_identifiers` | `identity.field` |
| --- | --- | --- | --- |
| `base-allowlist.json` | **true** | `contract_revision:15` | `contract_revision` |
| `cache-invalidation-contract.json` | false | `contract_revision:3` | `contract_revision` |
| `db-api-inventory.json` | false | `inventory_revision:5` | `inventory_revision` |
| `negative-fixtures.json` | false | `fixture_set_revision:7` | `fixture_set_revision` |
| `repository-contract.json` | false | `contract_revision:4` | `contract_revision` |
| `runtime-authz-contract.json` | false | `runtime_contract_revision:3` | `runtime_contract_revision` |
| `tenant-context-allowlist.json` | false | `contract_revision:6` | `contract_revision` |

**射影が動いた `integer_revision_field` 資産は識別値の更新が必須**(同関数)。

### 3. `change` の構造

`_strict_keys(change, {subject, aspect, before, after})`。

**`before` / `after` のキー exact-set = `{declaration, movement_policy, external_snapshots, asset_snapshots}`**(`ASPECT_NAMES`)。

| キー | 中身 |
| --- | --- |
| `declaration` | **7 資産分**の identity 宣言の実内容 |
| `movement_policy` | **7 資産分**の movement_policy の実内容 |
| `external_snapshots` | `{path, sha256, snapshot_ref}` の順序付き配列。現行の `after` は **3 件**(検査器・`frozen_history.py`・`ci.yml`) |
| `asset_snapshots` | 同形式で **7 件**(7 資産の凍結射影) |

**`aspect` は `derive_aspects` が実差分から導出した値と完全一致**が要る。申告値を手で書いても、実差分とずれれば red。

### 4. `history-snapshots/` は無条件で必須

`research.md` 1 節は「**7C のマージ版が要求する場合**」と条件付きにしていたが、**無条件**。`_external_snapshots` が全 `snapshot_ref` の実解決を要求し、`_read_snapshot_directory` が**ファイル名 == 内容の SHA-256** を検証、`_validate_snapshot_append_only` が**既存ファイルの削除・変更を拒否**する。

**現在 47 件。** **`plan.md:68` の「7C のマージ版が要求する場合の」という条件節は落とす。**

### 5. 予約 marker は除外リスト方式で record 全体に掛かる

`_reject_v2_reserved_markers` が record を**再帰全走査**し、除外リスト `_V2_RESERVED_MARKER_EXCLUDED_FIELDS`(`acceptance_id` / 新旧識別値 / `change.aspect` / `change.before` / `change.after`)以外の**すべての文字列**を検査する。

**実質の対象**: `change.subject` / `movement_fact` / `reason` / `approved_by` / `approved_on`。

**禁止トークン**: `PENDING` / `TODO` / `TBD` / `未承認` / `未定` / `レビュー待ち`(大小無視・**語境界つき**)。加えて `未承認(PR #<数字> のレビュー待ち)` の完全一致。

**受理される**(実測): `未定義動作を拒否するため。` / `suspending a stale check` / `山田正輝` / `2026-09-24`

**したがって記録を書く時点で、実在の承認者名と実在する ISO 8601 日付が要る。** プレースホルダを置けない。

### 6. ローカル実行では CI の合否を先取りできない

`resolve_evaluation_context` が `GITHUB_EVENT_NAME == "pull_request"` のときだけ **PR 受理モード**になる。**ローカルの `check_tenant_boundary_bypass.py --base-ref origin/develop` は不変量モード**で、次が**走らない**。

- `change.before` / `after` と実内容の突合
- `acceptance_id` と GitHub event 値の突合
- movement と追記 record 件数の厳密一致(`require_transition`)
- merge 形状(`base.ref == develop` / HEAD が 2 親 / 第一親 == `base.sha` / 第二親 == `head.sha`)

**`plan.md:123` の DoD コマンドだけでは足りない。** **ステップ 2 の合格は PR の CI(PR 受理モード)で確認する。**

### 7. `allowed_symbols` の追加は必ず movement を起こす

`_asset_baseline_value_content` = **資産本文から `baseline_control` と `source_digest` を除いた全 top-level フィールド**の正規化 JSON。**`allowed_symbols` はこの範囲に入る**ので、**記号を 2 件足せば `baseline_value` 軸が発火し `moved = True`**。

**帰結**: v2 記録 1 件が必須・`base-allowlist.json` の `contract_revision` を **15 → 16** へ繰り上げる。

**`aspect` の見込み**: `declaration`(`current_identifiers` が動く)と `asset_snapshots`(当該資産の射影が動く)の 2 つ。`movement_policy` と `external_snapshots` は不変。**ただし実値は検査器に出させて確認すること。**

### 8. 普遍下限の trigger

`REQUIRED_MOVEMENT_TRIGGERS` は **6 件**(`baseline_set` / `baseline_value` / `declaration_location` / `frozen_target_mapping` / `identity_granularity` / `identifier_interpretation`)。**`pass_fail_mapping` は実装側に無く、資産の宣言から取る**(資産側の宣言は 7 件)。**442 は `movement_triggers` を変えない**ので影響しない。

### 9. `external_files` の現況

**7 資産すべてが同一の 3 件**。

```
scripts/check_tenant_boundary_bypass.py
scripts/frozen_history.py
.github/workflows/ci.yml
```

**`plan.md:89` の差分 0 行の不変条件に `scripts/frozen_history.py` が挙がっていない。** 触らなければ実害は無いが、**触れば `external_snapshots` が動いて記録の内容が変わる**。あわせて**同ファイルは `.claude/core-areas.json` の `tenant-isolation` に登録済み**(2026-09-25)なので、**触れば `core_guard` の人間逐行確認が要求される**。

---

## 陳腐化していて訂正が要るもの(4 件)

| # | 箇所 | 現状 | 正 |
| --- | --- | --- | --- |
| 1 | `plan.md:27` | 「② TSK-431 の 7C のマージ(**未** — PR #78)」 | **マージ済み**(`b4ae7394`)。**開始条件は充足** |
| 2 | `research.md:28` / `:77`・`design.md:95` | 「PR #78 は OPEN」「記録形式は PR #78 のマージで確定する」 | **確定済み**(本追補) |
| 3 | `research.md` 2 節の行番号典拠 | `check_tenant_boundary_bypass.py:935-966` ほか | **PR #78 で全面的にずれた**。事実は成立。**節番号と関数名で書き直す** |
| 4 | `design.md:90` | `check_shared_preconditions.py:359-368` | 実際の digest 照合は **`:365-369`** |

---

## ステップ 2 の合格条件へ書き足すこと(`plan.md:80` が定める手続き)

1. **v2 record の必須キーは exact-set**(上記 1)。**新旧識別値は 7 資産分の map**(上記 2)
2. **`change.before` / `after` は 4 キー**で、`declaration` と `movement_policy` は **7 資産分の実内容**、`asset_snapshots` は **7 件**(上記 3)
3. **`history-snapshots/<sha256>` は無条件で必須**。**既存 47 件は 1 つも変更・削除しない**(上記 4)
4. **`approved_by` / `approved_on` に予約語を書けない**。**実在の承認者名と ISO 日付**(上記 5)
5. **合格は PR の CI(PR 受理モード)で確認する。ローカルの不変量モードでは不足**(上記 6)
6. **`contract_revision` を 15 → 16**(上記 7)

---

## 要件突合の結果

442 が引く要件は **3 件**(`plan.md:22`)。**いずれも逐語で一致**。

| 引用 | 判定 |
| --- | --- |
| NFR-010(チーム間データ分離・初日から全機能) | **一致**(要件書 `:846`・`:848`) |
| NFR-019(b)(越境アクセステスト) | **一致**(`:933`。略称は条文由来) |
| FR-034(データ所有権制御) | **一致**(`:599`・`:600`) |

**Won't(2.2 節)との衝突は無い。**

**1 件だけ射程超過(軽)**: 6 節のテスト計画の表頭が「**NFR-019 の種別**」となっているが、**条文が列挙するのは (a) 一致性 / (b) 越境 / (c) E2E / (d) 同期プロトコルの故障系の 4 種**で、**「単体」は条文に無い**。また **「故障系」= DDL 適用の原子性**は条文 (d) の「**同期プロトコルの**故障系」とは別物、**「一致性」= カタログ一致**は (a) の対象(NFR-018 区分(α)= クライアント/サーバー双方で実行するドメイン計算)ではない。**A1 の表を継承した際に限定語が落ちている。** 表頭を「テスト種別(NFR-019 の 4 種に限らない)」等へ改めるのが正確。

**改善台帳の引用が 0 件**。NFR-010 の台帳側の出所は **I-2**(`docs/improvements-from-baseball-scoring.md:32-39`)、移行バッチ用ロールは **I-7**(同 `:71`)。**矛盾ではないが、コア領域の計画書としては素性の明示が薄い。**

---

## 外部依存の実測(計画書の記述 vs 実物)

| 依存 | 計画書 | 実測 | 判定 |
| --- | --- | --- | --- |
| TSK-424 PR A1(#79) | 済 | `contracts/authz/product/` に 4 資産。**capability カタログ 74 件** | **一致** |
| **TSK-431 の 7C** | **未** | **マージ済み** | **計画書が古い** |
| RLS DDL の実スキーマ適用 | TSK-344・未 | `backend/migrations/` 全 26 リビジョンに `CREATE POLICY` / `CREATE ROLE` / `ROW LEVEL SECURITY` が **0 件** | **一致(未適用)** |
| Session 供給 | TSK-444・未 | `repositories/base.py` の `_session` は **abstract property**。実装は試験の二重のみ | **一致(未充足・442 の射程外)** |
| `allowed_symbols` の現況 | 5 件 | **5 件**。正例 fixture も 5 件 | **一致** |
| `runtime_contract.py` の暫定状態 | `PROVISIONAL=True` / `SUPERSEDED_BY` | 逐語どおり。最終パス `ddl-elements.json` は**不在** | **一致** |
| CI コマンド一覧 | `plan.md:123` | `.github/workflows/ci.yml` と**逐語一致** | **一致** |

---

## ステップ表の実行可能性

**11 ステップすべてについて参照先の実在を確認した。ブロッカーは無い。**

**不在の 5 点**(`application-steps.json` / 製品版 `failure-injection-points.json` / `migration-batch-role.json` / `probe-product-map.json` / `product_provisioning`・`product_catalog` の 2 モジュール)は**すべて 442 自身が新規に作ると宣言している成果物**。

**実在を確認した主なもの**: `asset_spec.py` の `PRODUCT_SPEC`(9 節・`operation_handlers=()`)/ `provisioning.py` の `apply_authz_ddl` と前提検査 / `db_fixtures.py` の `disposable_postgres_cluster`・`provisioned_catalog` / `catalog.py` の `inspect_authz_catalog` / `table-classification.json` の `profile` **45 件**(うち `tenant_owned` **23** / `function_only` **13**)/ 製品トリガ関数 **37 本 + 補助 1 本** / staged の `policy_id` **32 件**。

**未検証(不明)**: ステップ 7 の「`tenant_id` 列を持つ **28 表**」とステップ 10 の「導出集合 **19 表**」。**どちらも数の典拠が資産から直接引けなかった。実装時に数え直すこと。**
