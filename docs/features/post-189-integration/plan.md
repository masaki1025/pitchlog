---
feature: post-189-integration
status: in-review
承認: 未
重さ分類: コア領域
worktree: ../../..
notion: 未設定
branch: feature/post-189-integration
created: 2026-11-03
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 統合計画書: #189統合後の #190〜#192 接続

## 1. 背景・目的

#189（初球縦断）は `fd1bb20a` で develop へマージ済み。#190（通常投球の連続保存）は #189 の旧headを基にしており、develop へ base を付け替えると **tenant/authz の生成資産を中心に26件の競合**が出る。#191/#192 はさらに積み上げで、develop との競合は各31件、#192は実装未完である。

#190 側の revision 28 / digest `9a19…` は旧 #189 時点の値であり、**#190 自身の現在木に対しても**生成物は stale である（`runtime_contract_generator check` が `DERIVED_FIELDS_STALE`、`design_provenance[6]` の `extracted_text` が `backend/src/pitchlog/api/routers/started_games.py` に逐語一致しない。develop 側は一致）。develop 側の revision 25 / digest `130e…` は #189 の受理済み最終値である。どちらかを丸ごと採用すると、#190 の新operation登録が消えるか、#189 の受理値を壊す。

本計画は、**共有受理資産は develop を基礎にし、#190 の新規・変更分だけを公式経路で再導出する**統合方針と、#190〜#192を順に develop へ接続するための後工程条件を定める。実際のコード変更ステップは各PRの計画追補に置く（本ブランチではコードを変更しない）。

要件の対応: FR-001（1球単位の記録）・FR-002（試合進行の再現）・NFR-005（DB側絞り込み）・NFR-018（ドメイン計算の単一実装）・NFR-019（テスト必須）・NFR-023（エスケープ/PDF外部資源無効）。本計画自体は意味変更を行わない。

## 2. スコープ

### やること

- **#190 の26件**の競合を3区分（develop採用 / union追記 / 再導出）へ**ファイル単位**で確定する
- tenant/authz の生成モジュール・契約・受理record・snapshot・凍結archive corpus の**書き込み経路と再導出順序・停止条件**を確定する
- 各PR（#190/#191/#192）が接続時に満たす完了条件を DoD として定める

#191/#192 の31件は、本書の手順を各PRの計画追補で適用して分類する（本PRでは区分表を作らない。#190 と競合集合が異なるため、写経すると未分類が残る）。

### やらないこと

- 製品の意味変更、検査の緩和、未受理値の受理扱い
- 本ブランチでの #190〜#192 のコード変更（各PRの計画追補で実施する）
- rebase による受理検証済み HEAD/digest の破壊（base付け替えは merge のみ）
- #191/#192 の31件の区分表（各PRの追補で作る）
- #192 の未完実装の完成（完了範囲は #192 の計画追補で定義する）
- 人間逐行確認・PO署名の代記

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` 6.1/6.3/7.6 | 反映なし（参照のみ） | なし |
| `docs/features/post-189-integration/plan.md` | 新設（本書） | PRレビュー |
| `docs/features/mvp-recording-continuation/plan.md` (#190) | 本PRでは変更しない（#190の追補PRで実行ステップを追加） | 各PR |
| `docs/features/mvp-terminal-pitches/plan.md` (#191) | 本PRでは変更しない（#191の追補PRで追加） | 各PR |
| `docs/features/mvp-strikeout-pitches/plan.md` (#192) | 本PRでは変更しない（#192の追補PRで追加。実装未完を明示） | 各PR |
| `contracts/tenant_boundary/*` | 本PRでは変更しない（#190/#191/#192で公式導出により再生成） | 各PR + finalize-doc該当時 |
| `contracts/authz/*` | 本PRでは変更しない（#190/#191/#192で公式helperにより再導出） | 各PR + finalize-doc該当時 |
| `docs/features/mvp-delegated-core-review/policy.json` | 本PRでは変更しない（対象PR/branchの確認のみ） | 各PR |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | 反映なし（意味変更なし） | なし |

## 4. 実装方針

### 重さ分類の根拠

`重さ分類: コア領域`。tenant分離・同期プロトコル・記録権の受理資産と生成契約に触れるため。設計書 6.3 の敵対レビューは省略しない。PO委任は `policy.json` の `targets` に列挙された PR/branch に限り人間確認の代替としてのみ扱い、**逐行確認・署名は代記しない**。**本PR（post-189-integration）は `policy.json` の対象外なので、人間承認が必要**。

### 前提（実測済みの事実）

1. #190 の生成値は基礎にできない（`DERIVED_FIELDS_STALE`、および `design_provenance[6]` の `extracted_text` が対象ファイルに逐語一致しないことは #190 単体で再現する）。
2. 受理recordの `change.after` は **`runtime_contract_acceptance` の出力だけ**を使う。手修正しない。
3. `frozen_projection.excluded` は9資産すべて `["baseline_control","source_digest"]`。受理recordの追記（`baseline_control.history`）は射影に入らないため、record自身の循環は閉じる。
4. `base-allowlist.json` は develop と #190 で**宣言キー集合が異なる**。どちらか一方の採用では、develop の `writer_binding_deployment_assets` / `condition_2_first_ball_scoped_findings` / `condition_5_first_ball_scoped_findings` か、#190 の `condition_2_initial_start_scoped_findings` / `condition_2_ordinary_scoped_findings` が消える。**union が必須**。
5. `backend/tests/test_function_operations_boundary.py` は両側追記（develop 68行 / #190 83行）で、単純採用では片側の拒否対向が消える。**union が必須**。
6. `census-baseline.json` は `anchor.commit` と `materialized_tree`（digest/file_count/paths）が両側同一で、**develop が厳密上位集合**（`initial_population_proof` を持ち `contract_revision: 21`）。#190 側を基礎にすると `initial_population_proof` 必須の検査で赤になる。
7. 受理record生成より前に**すべての入力を確定**させる。動かせないのは (a) `baseline_control` を持つ資産の識別値（生成後は `validate_current_history` の「履歴末尾と識別値の不一致」で赤、`runtime_contract_acceptance` も「history は雛形を作る前に追記できません」で拒否）と、(b) **`external_files` に載る実装**（受理recordの `change.after` は作業ツリー実体から作られるため、生成後に `tests/test_ci_wiring.py` 等を変えると `change.after: HEAD の実内容と不一致` と「射影が動いた資産は識別値の更新が必要」で PR 受理モードだけが赤になる）。
8. `contracts/tenant_boundary/frozen-inputs.json` の `external_files` には `tests/test_ci_wiring.py` 等が含まれる。したがって CI 期待値・corpus pin の更新は受理record生成より**前**に行う。

### 競合26件のファイル単位3区分（#190）

| # | パス | 区分 | 処置 |
| --- | --- | --- | --- |
| 1 | `backend/src/pitchlog/authz/runtime_contract.py` | 再導出 | asset確定後に `runtime_contract_generator render` |
| 2 | `backend/src/pitchlog/repositories/operation_registry.py` | union | developの登録と#190の新operation 8件を統合 |
| 3 | `backend/src/pitchlog/repositories/repository_contract.py` | 再導出 | 資産（revision再採番後）から定数を導出 |
| 4 | `backend/src/pitchlog/repositories/tenant_context_contract.py` | 再導出 | 同上 |
| 5 | `backend/tests/test_durable_rights_ledger_contract.py` | union | 両側の追記を保持 |
| 6 | `backend/tests/test_first_ball_write_stamp.py` | union | 両側の追記を保持 |
| 7 | `backend/tests/test_function_operations_boundary.py` | union | develop 68行 + #190 83行 |
| 8 | `backend/tests/test_sync_apply_source_binding.py` | union | 両側の追記を保持 |
| 9 | `backend/tests/test_sync_route_shape.py` | union | develop 243行 + #190 84行 |
| 10 | `contracts/tenant_boundary/base-allowlist.json` | union+再導出 | 宣言はunion、historyは受理template出力 |
| 11 | `contracts/tenant_boundary/cache-invalidation-contract.json` | develop採用 | 本文はdevelopと一致（revisionのみ差） |
| 12 | `contracts/tenant_boundary/census-baseline.json` | develop採用 | `initial_population_proof` と `contract_revision: 21` を保持 |
| 13 | `contracts/tenant_boundary/db-api-inventory.json` | develop採用 | 本文はdevelopと一致（revisionのみ差） |
| 14 | `contracts/tenant_boundary/negative-fixtures.json` | develop採用 | 本文はdevelopと一致（revisionのみ差） |
| 15 | `contracts/tenant_boundary/repository-contract.json` | develop採用+追記 | develop基礎 + #190の関数operation 7件 + token 1件を追加しrevision再採番、`source_digest` を再計算 |
| 16 | `contracts/tenant_boundary/runtime-authz-contract.json` | 再導出 | `rederive --base origin/develop` |
| 17 | `contracts/tenant_boundary/tenant-context-allowlist.json` | develop採用 | 本文はdevelopと一致（revisionのみ差） |
| 18 | `docs/features/mvp-first-ball-screen-vertical/manual-check.md` | union | #190の通常3球実証 + developの追記 |
| 19 | `docs/features/mvp-game-start-connection/plan.md` | union | 双方の追記節を保持 |
| 20 | `scripts/check_tenant_boundary_bypass.py` | union | develop 1867行 + #190 779行（検査を緩めない） |
| 21 | `tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/_apply_initial_storage.py` | develop採用 | 差分は `# ty: ignore` のみ |
| 22 | `tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/_apply_writer_storage.py` | develop採用 | ty注記に加え本体差あり（developが `raw` を明示検証する新しい版） |
| 23 | `tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/_require_initial_state.py` | develop採用 | 本体差あり（developは `alembic_version` を `0036_initial_right_storage` と照合する新しい版） |
| 24 | `tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/_require_writer_state.py` | develop採用 | 差分は `# ty: ignore` のみ |
| 25 | `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/function_operations.py` | develop採用 | 両側同一の意味変更（`LargeBinary` 追加）。union すると二重定義になる |
| 26 | `tests/test_check_tenant_boundary_bypass.py` | union | develop 1148行 + #190 478行 |

未分類は 0（26件すべてが1区分に属する）。区分内訳: 再導出 4 / union 10 / union+再導出 1 / develop採用 10 / develop採用+追記 1。

### 書き込み経路（公式writerの有無）

| 対象 | 公式writer | コマンド / 扱い |
| --- | --- | --- |
| `runtime-authz-contract.json` | あり | `python -m pitchlog.authz.runtime_contract_generator rederive --base origin/develop`（`backend/` で実行） |
| `runtime_contract.py` | あり | `python -m pitchlog.authz.runtime_contract_generator render` |
| 受理record + `history-snapshots/*`（9資産・external） | あり | `python -m pitchlog.authz.runtime_contract_acceptance --repository <repo> --base origin/develop --acceptance-id <owner/repo#PR> --approved-by <値> --approved-on <YYYY-MM-DD> --reason <理由> --movement-fact <事実> --output <リポジトリ外の任意パス>` → 出力の `record` と `snapshots_base64` を適用 |
| `contracts/authz/*` の派生3資産と各 decision lock | あり | `uv run python scripts/check_authz_catalog.py --asset-spec product --reseal-derived`（査読後） |
| oracle seal | あり（移動時のみ） | `uv run python scripts/check_authz_catalog.py --asset-spec product --reseal-oracle`（#190はoracle provenanceを触っていないため原則不要） |
| `cache-invalidation-contract.json` / `census-baseline.json` / `db-api-inventory.json` / `negative-fixtures.json` / `tenant-context-allowlist.json` | なし（検査のみ） | `git checkout origin/develop -- <path>` で develop採用。record上のsnapshotは受理templateが生成する |
| `repository-contract.json` | なし（検査のみ） | `git checkout origin/develop -- <path>` の後、#190の関数operation 7件 + token 1件を追記し revision を再採番し、`source_digest` を再計算（`test_authz_repository_contract.py` が本文sha256を要求）。追記は契約のスキーマ順に限定し、値は `operation_registry.py` と突合する |
| `repository_contract.py` / `tenant_context_contract.py` | **なし**（検査のみ） | 資産から定数とタプルを導出する薄い再導出スクリプトを#190で追加し、テストを付けて実行する。**手で書かない** |
| 凍結archive corpus digest | あり | `tests/fixtures/frozen-archive-cases/runner.py` の `corpus_input_digest()` を呼び、`manifest.json` の pin を更新 |
| `tests/test_ci_wiring.py` の期待値 | なし（定数） | 実CIのジョブ構成へ定数を追随（緩めない） |

「writerなし」の2種（`repository_contract.py` / `tenant_context_contract.py`）は、**検査器が比較に使う導出関数をそのまま呼ぶ**薄いスクリプトをPR内で追加する。追加スクリプト自身に単体テストを付け、検査の期待値を手で埋めない。

### 再導出の順序（資産識別値と external_files のデッドロックを閉じる）

1. **merge**: #190ブランチへ `origin/develop` を **merge**（rebaseしない）。競合は上表の3区分で解消
2. **generated modules**: `runtime_contract_generator rederive --base origin/develop` → `render` → `check` が0
3. **authz catalog**: `check_authz_catalog.py --asset-spec product --reseal-derived`（oracle移動がある場合のみ `--reseal-oracle`）
4. **tenant宣言**: `base-allowlist.json` の宣言union、`repository-contract.json` の限定追記とrevision再採番
5. **診断系モジュール**: `repository_contract.py`・`tenant_context_contract.py` を薄い再導出スクリプトで更新
6. **凍結archive / ci期待値**: `corpus_input_digest` と `test_ci_wiring` の期待値を実測へ追随（`test_ci_wiring.py` は `external_files` なので受理recordより前）
7. **受理record/snapshot（全入力の確定後・最後）**: `runtime_contract_acceptance` を実行し、`record` と `snapshots_base64` をそのまま適用。**これ以降は資産の識別値も `external_files` の実装も動かさない**
8. **全件検査**: tenant/authz/census/frozen/backend/harness を実行（下記6節）

途中で落ちたら**その段階で停止**し、前段の出力を手で直して先へ進めない。

### 実装ステップ（本ブランチで実行する作業）

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | 競合26件をファイル単位の3区分へ分類する（本節の表） | 26件すべてが1区分に属し、未分類0。`git merge-tree --write-tree --name-only origin/develop origin/feature/mvp-recording-continuation` の26件と集合一致 |
| 2 | 書き込み経路・再導出順序・停止条件を確定する（本節の2表） | 各対象に writer の有無と、コマンドまたは代替手順があり、「writerなし」は手編集禁止と追加スクリプトの条件が明記されている |
| 3 | 本PRのDoDと各PR接続時のDoDを分離する（5節） | 5.1の全項目が本PRの差分で検証でき、5.2の全項目がコマンド/CIジョブ名を持つ |
| 4 | 非作者レビューの指摘を本書へ反映する | P0/P1=0。反映は commit に残す |

（本PRの承認は上表の外のゲートであり、`policy.json` の対象外＝人間承認が必要。非作者レビューP0/P1=0でもPO委任では代替しない。）

## 5. DoD(受け入れ基準)

### 5.1 本PR（計画）の完了条件

- [ ] 26件がファイル単位で3区分に分類され、未分類0（`git merge-tree` と集合一致）
- [ ] 書き込み経路表の全対象に writer の有無と、コマンドまたは代替手順（develop採用コマンド / 追加スクリプト / 定数の追随先）がある
- [ ] 再導出順序がデッドロックを含めて閉じている（資産の識別値と `external_files` の実装は受理record生成より前に確定）
- [ ] `check_plan_docs_sync.py --base origin/develop`・`check_docs_status.py`・`check_design_propagation.py`・`check_doc_coverage.py` が緑
- [ ] 非作者レビューP0/P1=0、人間承認が記入され、逐行確認・署名の代記がない

### 5.2 各PR接続時の完了条件（#190/#191/#192 の各PRで満たす）

- [ ] 競合0（`git merge-tree` で確認）・未分類0
- [ ] `check_tenant_boundary_bypass.py --base-ref origin/develop` が ok
- [ ] `check_authz_catalog.py --asset-spec product` が ok、`runtime_contract_generator check` が0
- [ ] 9資産のsnapshotが `frozen_history.frozen_projection_content` の再計算値と一致し、受理recordの `change.after` が `runtime_contract_acceptance` の出力と一致（手修正なし）
- [ ] 凍結archive corpus と `test_ci_wiring` の期待値が実測と一致
- [ ] 必須CI（`docs-lint`・`harness-static`・`harness-shard (0..3)`・`harness`・`consistency`・`mutation`・`nfr021-append-only`・`secrets`・`tenant-boundary-bypass`・`frontend-changes`・`frontend`・`backend-changes`・`backend-static`・`backend-shard (0..3)`・`backend`・`core-guard`〔`pr-body.yml`〕）が緑
- [ ] 非作者レビューP0/P1=0、PO委任の対象PR/branch・承認値・日付が実値で記録され、人間逐行確認/署名を代記していない
- [ ] 検査の緩和・製品の意味変更・未受理値の受理扱いがない（拒否対向の件数が減っていない）

## 6. テスト計画

- **一致性**: `uv run python -m pytest -c pyproject.toml tests/test_check_tenant_boundary_bypass.py tests/test_frozen_history.py tests/test_frozen_archive.py tests/test_frozen_archive_case_runner.py tests/test_ci_wiring.py`（受理record・snapshot・corpus・CI配線の相互固定）
- **単体（authz/tenant）**: `uv run python scripts/check_authz_catalog.py --asset-spec product`、`cd backend && uv run python -m pitchlog.authz.runtime_contract_generator check`
- **越境（tenant）**: `uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`、`tests/test_census_baseline_check.py`
- **backend**: `cd backend && uv run pytest`（実DB必須はCIの `backend` 集約。4シャードと集約の両方）
- **harness**: ルート `uv run python -m pytest -c pyproject.toml tests/`（CIの `harness` 集約と同じ除外）
- **E2E**: #190/#191/#192 の既存実画面E2E（`test_ordinary_screen_e2e.py` 等）を各PRで実行。新規E2Eの要否は各PRの計画追補で判断
- **故障系**: 既存 tenant negative fixtures と拒否対向を維持し、件数を減らさない（検査の緩和禁止）
- **追加テスト**: 「writerなし」の薄い再導出スクリプトに単体テストを追加（導出値が検査器の期待と一致し、改変時に赤になること）
