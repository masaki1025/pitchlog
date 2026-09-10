---
feature: authz-decision-note-followup
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-10・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d793b75e6878176b9f5eb90e97b3357
branch: fix/authz-decision-note-followup
created: 2026-09-10
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし)
---

# 実装計画書: develop の red を解消する — 注記追随漏れ 1 件と CI の浅いクローン 2 ジョブ

## 1. 背景・目的

**develop が red である。** 原因は 2 つで、**どちらも PR #52(TSK-317・マージ済み `67e06a2`)由来**である。
**ただし起因コミットは 2 つの欠陥で別である**(敵対レビュー 1 周目 `P2-2` の是正 — **当初「`14973f6` が入れた `source_commit`」と書いたが誤りだった**):

| コミット | 何をしたか | どちらの欠陥の起因か |
| --- | --- | --- |
| **`5f668bf`** | **`manifest.json` と 2 段の静的照合を新設し、`source_commit` の機構を導入** | **② の起因** — **浅いクローンで解決できない履歴依存を CI へ持ち込んだのはこのコミットである**。`git merge-base --is-ancestor 5f668bf 67e06a2^1` は偽(**マージ前 develop の祖先ではない** = PR #52 で入った) |
| **`14973f6`** | **判定注記 7 行のみを追加**(SQL 3 ファイル) | **① の起因** — テスト側 2 箇所がこの注記に追随しなかった |
| **`8a72a93`** | **`source_commit` を `14973f6` へ再導出**(manifest 4 行) | **② の発現を確定させた** — **解決対象の SHA が tip 以外になった** |

| # | 欠陥 | 症状 |
| --- | --- | --- |
| **①** | **テスト側 2 箇所が判定注記 `MANAGEMENT_TARGET_GRANT_GROUP_MATCH` に追随していない** | **手元の `tests/db` で 11 件が red**(exact-set が 8 対 7) |
| **②** | **`ci.yml` の `harness` と `backend` が浅いクローン**(`fetch-depth: 0` が無い) | **CI が red** — `harness` 19 failed / `backend` 15 failed + 85 errors。`source_commit` を git で解決できない |

**② は ① を隠していた。** `provisioned_catalog` fixture が
`source_commit を解決できない` で死ぬので **`_assert_failure_case_contract()` に到達せず**、
CI ログに `sha256 exact-set 一致しない` は **0 件**である(TSK-343 の実測)。
**機械は ① を捕まえる設計だったが、その手前で別の理由で倒れていた。**

**PR #52 は red のままマージされた**(`backend` FAILURE ×2・`harness` FAILURE・`core-guard` FAILURE)。
**PR 作成者(私)が CI を確認しなかった** — `/pr` の導線は「CI 全グリーン → 人間がマージ」である。

**関連要件**: `NFR-010`(テナント分離)/ `NFR-019`(b)(越境テスト)。
**関連正本**: [`docs/design/data-model.md`](../../design/data-model.md) 12-4 節のマージゲート。

**急ぐ理由**: **TSK-343 が PR を出せない**。同タスクの DoD にコア領域の逐行確認があり
`/pr` は CI を見るため、**develop の red が直接のブロッカ**である。
同タスクの計画書はマージ順序へ本 fix を挿入済み
(`TSK-348(完了)→ TSK-317 PR #1(完了)→ TSK-317 fix → 本タスク → TSK-317 PR #2 → TSK-355 → TSK-235`)。

## 2. スコープ

### やること

**① テスト側 2 箇所を body の 8 件へ追随させる**

1. `backend/tests/db/test_authz_management_probe.py` の `_AUTHORIZATION_FAILURE_CASES` へ
   **8 件目**(`MANAGEMENT_TARGET_GRANT_GROUP_MATCH`)を追加
2. `backend/tests/db/test_authz_toctou.py` の 2 文 mutant SQL へ **`-- DECISION:` 注記だけ**を追加
   (**JOIN 条件は既に存在する** — `:381` に `ON target_grant.group_id = caller_membership.group_id`。
   **1 周目 `P0-1` の是正**。条件を重複追加してはならない)

**② CI の浅いクローンを是正する**

3. `.github/workflows/ci.yml` の **`harness`(:75)と `backend`(:207)の checkout へ `fetch-depth: 0`**
4. **`tests/test_ci_wiring.py` へ、この 2 ジョブの checkout を構造的に検査する試験を新設**
   (**2 周目 `P0-2` の是正** — 同ファイルは現在 `checkout` の語を **0 件**しか持たず、**CI の浅いクローンを検知する機構が存在しない**。**本欠陥の原因そのものを機械化する**)

### やらないこと

| 項目 | 理由 |
| --- | --- |
| `contracts/authz/**` の変更 | **body も manifest も MC/DC 写像も正しい状態**。追随漏れはテスト側だけ |
| 他の判定注記(`SHARED_*` 1 件 / `CONTROL_*` 5 件)の追随 | **追随漏れは `MANAGEMENT_*` の 1 件のみ**(下記 4 節・敵対レビューが独立に追認) |
| `docs-lint` と `frontend` ジョブの `fetch-depth` | **現状 green**。触る理由がない(射程を広げない) |
| `ci.yml` の ORM / Alembic のコマンド契約 | **TSK-343 のステップ 26 の射程** |
| `guard_paths` への新設パス登録 | **TSK-317 の改訂 3 第 2 弾の `S-8`** |
| `conftest.py` の `_required_db_execution_error` の強化 | **TSK-343 の提案(収集したのに call へ到達しないものを red にする)は妥当だが、本 fix の射程外**。**申し送りとして PR #2 へ送る** |
| DSN のスキーム(`postgresql+psycopg://`)の是正 | **環境側の設定**。リポジトリの変更を要しない(敵対レビューも妥当と判定) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/**` の正本 | **反映なし**(テストと CI 配線の追随のみで、規範も設計も変わらない) | — |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **`## 候補` へ 2 件追記する**(無条件。内容と経緯は 4 節)。**① SQLAlchemy URL と libpq conninfo の混同**(典拠は TSK-343 の 2026-09-10 実測・本文は先方が起草)/ **② fail-closed な setup error が実体的な red を飲み込む** | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| [`docs/README.md`](../../README.md) | **台帳行の要約と最終更新日を現行化する** | —(常に現行化 — 7.2) |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

**実装コードの変更範囲は次の 4 ファイルに限る**(1 周目 `P1-3` の是正 —
**実装コードの範囲と、許容する作業・記録文書の範囲を分けて定義する**):

| ファイル | 変更内容 |
| --- | --- |
| `backend/tests/db/test_authz_management_probe.py` | `_AUTHORIZATION_FAILURE_CASES` へ 8 件目 + 対応する fixture 変換関数 |
| `backend/tests/db/test_authz_toctou.py` | 2 文 mutant SQL へ **`-- DECISION:` 注記のみ**を追加 |
| `.github/workflows/ci.yml` | `harness` と `backend` の checkout へ `fetch-depth: 0` |
| `tests/test_ci_wiring.py` | **新設** — `harness` と `backend` の checkout が `fetch-depth: 0` を持つことの構造的検査 |

**許容する作業・記録文書**(実装コードではない):

| ファイル | 変更内容 |
| --- | --- |
| `docs/features/authz-decision-note-followup/**` | 本計画書(feature 作業ディレクトリ・正本ではない) |
| `docs/worklog/2026-09-10-authz-decision-note-followup.md` | 作業ログ |
| (台帳と索引は **3 節の正本宣言**へ移した — 無条件に反映する) |

## 4. 実装方針

**重さ分類 = コア領域(テナント分離)** — `backend/tests/db/**` は
`core-areas.json` の `tenant-isolation.paths` に登録済みで **core-guard が発火する**。
→ **敵対レビュー + 人間の逐行確認が必要**(逐行確認は PR 作成者以外)。

### 欠陥 ① の機序(原典で確定)

`test_authz_management_probe.py:256-270` の **`_decision_ids_from_body()`** が
**凍結 body から `-- DECISION:` を抽出して母集合とする**。これと exact-set 比較するのが 2 箇所:

| 比較箇所 | テスト側 | body |
| --- | --- | --- |
| `_assert_failure_case_contract()`(probe:370-378) | **7** | **8** |
| `_assert_mutant_decision_set()`(toctou:515-527) | **7** | **8** |

**`MANAGEMENT_TARGET_GRANT_GROUP_MATCH` は `backend/tests/db/` に 0 件**(実測)。

**追随漏れは 1 件だけである**: `_decision_ids_from_body()` は
**`_MANAGEMENT_FUNCTION_BODY_PATH`(管理関数の body 1 本)だけ**を読み、
**利用先はこの 2 ファイルだけ**なので、**`SHARED_*` 1 件と `CONTROL_*` 5 件は母集合に入らない**
(**敵対レビューが独立に追認済み**)。

### 欠陥 ② の機序(原典で確定)

**`fetch-depth: 0` を持つジョブと持たないジョブ**:

| 持つ | 持たない |
| --- | --- |
| `secrets` / `core-guard` / `nfr021-append-only` / `frontend-changes` / `backend-changes` | **`harness`(:75)** / **`backend`(:207)** / `docs-lint` / `frontend` |

**depth 1 では `14973f6` が履歴に存在しない**ので、
`git rev-parse <source_commit>:<path>` が `fatal: bad object` になる。

**`fetch-depth: 0` で足りる**(**2 周目 `P0-1` の是正** — 当初は
`verify_frozen_oracle_unchanged()` の base 解決も変える計画だったが**不要だった**)。
**ピン留めしている `actions/checkout`(`3d3c42e5`)は `fetch-depth: 0` のとき
全ブランチを取得し `+refs/heads/*:refs/remotes/origin/*` で remote-tracking ref を生成する**
(敵対レビューが実装の原典で確認)。したがって **`origin/develop` も取得され、
`14973f6` の解決と三点差分の双方が成立する**。
**`mutation_composition.py` は変更しない。**

### 3 節の正本宣言を無条件にした理由(2 周目 `P1-3` / 3 周目 `P0-1`)

**`scripts/check_plan_docs_sync.py:474-482` は 3 節の各行について、リンクされた `.md` とバッククォートのパスを抽出し、
その行に不反映を表す語が含まれていれば `no_change` へ、含まれていなければ `reflected` へ分類する。**

- **「該当時のみ」という条件付きの宣言は機構的に表現できない** —
  行に不反映の語が無ければ**無条件の反映宣言**として扱われ、
  **`status: in-review` のときに差分が無いと違反になる**(`:664`)
- **したがって条件分岐をやめ、台帳への追記と索引の現行化を確約した**
- **3 周目 `P0-1` の是正**: この機構の説明を 3 節の行に書いたところ、
  **説明文に含まれた語が抽出器のトリガになり、台帳が `no_change` へ分類された**。
  **機構が読む節に、機構のトリガ語を書いてはならない。**
  **説明は本節(4 節)へ移し、3 節の行はパスと変更内容だけにした。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`test_authz_management_probe.py` へ 8 件目の失敗ケースを追加** — `decision_id="MANAGEMENT_TARGET_GRANT_GROUP_MATCH"` / `changed_field_id="grant_group_id"` / **`mutate` は `grant_group_id` だけを `membership_group_id` と別値にする単独変更** | `[機械]` **`_AUTHORIZATION_FAILURE_CASES` が 8 件**・**`_decision_ids_from_body()` の 8 件と exact-set 一致**・**`_assert_failure_case_contract()` の後半(単独変更の検査)を通る**・`decision_id` の重複 0 |
| 2 | **`test_authz_toctou.py` の 2 文 mutant へ注記だけを追加** — **JOIN 条件は既にある**(`:381`)。**SQL の意味を変えない** | `[機械]` **mutant SQL 内の注記が 8 件**・**`_assert_mutant_decision_set()` が通る**・**`ON target_grant.group_id = caller_membership.group_id` が 1 回だけ現れる**(重複追加していない)・**既存の 2 文構成・barrier・TOCTOU の成立条件が不変** |
| 3 | **`ci.yml` の `harness` と `backend` へ `fetch-depth: 0`** — 他の 2 ジョブ(`docs-lint` / `frontend`)は触らない | `[機械]` **`harness` と `backend` の checkout ステップが `fetch-depth: 0` を持つ**(**件数ではなくジョブ名で検査する** — 2 周目 `P0-2`)・**`docs-lint` と `frontend` の checkout は変わらない**・**`secrets` / `core-guard` / `nfr021-append-only` / `frontend-changes` / `backend-changes` も変わらない** |
| 4 | **`tests/test_ci_wiring.py` へ checkout の構造的検査を新設** — **`ci.yml` の全ジョブについて `fetch-depth: 0` の有無を読み取り、宣言した集合と exact-set 照合する**。**同ファイルは現在 `checkout` の語を 0 件しか持たない**ため、**CI の浅いクローンを検知する機構が存在しない** | `[機械]` **`fetch-depth: 0` を持つジョブの集合が宣言と exact-set 一致する**(**3 周目 `P1-2` の是正** — `ci.yml` から「履歴を要するか」を機械導出する標識は無い〔履歴依存は `source_commit` 検査や三点差分へ**推移した先**にあり YAML には現れない〕。**したがって列挙する。ただし exact-set にして、ジョブが増減したら必ず red にする** — **新設ジョブが `fetch-depth` を持たずに追加されたらそこで止まり、明示的な判断を強制する**。**これが「人手列挙が避けられない場合の正しい形」**である)・**宣言する集合は 7 個**(`secrets` / `core-guard` / `nfr021-append-only` / `frontend-changes` / `backend-changes` / **`harness`** / **`backend`**)・**`fetch-depth` を持たないジョブの集合も exact-set で固定する**(`docs-lint` / `frontend` — **こちらが増えても red になる**)・**負例: ステップ 3 を巻き戻すと red**・**負例: 架空のジョブを宣言に足すと red**・`uv run pytest tests/test_ci_wiring.py` green |

## 5. DoD(受け入れ基準)

### 実装コードの範囲

- [ ] **変更が 4 ファイルに閉じている**(2 節「やること」の 4 ファイル)
- [ ] **`contracts/authz/**` の差分が 0**
- [ ] **既存の 7 ケースと既存の assertion を弱めていない**
- [ ] **toctou の JOIN 条件を重複追加していない**(`ON target_grant.group_id = ...` が 1 回だけ)

### 検証(**本欠陥の再発原因を閉じる**)

- [ ] **`cd backend && uv run pytest -c pyproject.toml tests/db` を無選別で実行し、
      その出力(件数と所要時間)を worklog へ記録した**
      (1 周目 `P0-2` の是正 — **`-k` / `-m` / `--deselect` / パス指定による部分実行で済ませない**。
      **本欠陥の原因は「回すテストを人が選んだ」ことである**)
- [ ] **収集された全件が passed で、failed と error が 0 件**
      (1 周目 `P2-4` の是正 — **固定件数を条件にしない**。
      **件数は結果の記録として worklog へ残す**。参考値: 現行 develop の収集は 111 件で、
      8 件目の parameter 追加により 112 件になる見込み)
- [ ] **CI が全ジョブ green**(**PR #52 で私が確認しなかった項目**。
      **`/pr` の導線どおり、green を確認してから人間へ引き渡す**)
- [ ] **TSK-343 が報告した 11 件が green**
      (`test_authz_management_probe.py` 8 件 + `test_authz_toctou.py` 3 件)
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(逐行確認は PR 作成者以外・実施記録行を確認者本人が記入)

### 申し送り

- [ ] **`conftest.py` の `_required_db_execution_error` の強化を PR #2 へ送った**
      (TSK-343 の提案 — **収集した DB 必須テストのうち call フェーズに到達しなかったものがあれば red**。
      **今回の「fixture で死んで assertion に到達しない」型が機構で見える**。**定数を要しない形**)

## 6. テスト計画(NFR-019)

**要件が定義する種別は 4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系)。

| 種別 | 追加内容 |
| --- | --- |
| **(b) 越境** | **新しいテスト関数は作らず、parameterized case を 1 件追加**(1 周目 `P2-4` の是正)。**8 件目は「対象 grant が別グループなら副作用が起きない」の検証**で、越境の拒否例に当たる |
| **(a) 一致性 /(c) E2E /(d) 故障系** | **追加なし** |
| **回帰** | **`tests/db` の収集された全件を無選別で実行**(参考: 現行 111 件 → 112 件になる見込み・所要は約 6 分 40 秒)+ ルート `pytest tests/` + `tests/test_ci_wiring.py` + `tests/test_authz_mutation_composition{,_full}.py` |

## 7. 検証(このタスクが終わったことの確認方法)

```bash
WT=../pitchlog-worktrees/fix-authz-decision-note-followup

# 1. 注記の件数が 3 箇所で一致すること
grep -c 'DECISION: MANAGEMENT_' "$WT/contracts/authz/function-bodies/functions/apply_representative_grant_change.sql"
grep -c '_AuthorizationFailureCase(' "$WT/backend/tests/db/test_authz_management_probe.py"
grep -c 'DECISION: MANAGEMENT_' "$WT/backend/tests/db/test_authz_toctou.py"

# 2. toctou の JOIN 条件が重複していないこと
grep -c 'ON target_grant.group_id = caller_membership.group_id' "$WT/backend/tests/db/test_authz_toctou.py"

# 3. 凍結資産に触っていないこと
git -C "$WT" diff --name-only origin/develop...HEAD -- contracts/

# 4. harness と backend の checkout が fetch-depth: 0 を持つこと
#    (grep -c は使わない — :90 のコメントを数えて実体と 1 ずれる。2 周目 P0-2)
cd "$WT" && uv run pytest tests/test_ci_wiring.py -q

# 5. 品質ゲート(静的)
cd "$WT" && uv run ruff check . && uv run ty check && uv run pytest tests/
cd "$WT/backend" && uv run ruff format --check . && uv run ruff check . && uv run ty check

# 6. 【必須】DB テストの全件実行(無選別。部分実行で済ませない)
cd "$WT/backend" && uv run pytest -c pyproject.toml tests/db
```

**手順 6 が本 fix の中心である。** **DB 必須テストの実行には
`PITCHLOG_TEST_ADMIN_DSN` と `PITCHLOG_TEST_ROLE_DSN` の実値が必要**(未設定は skip ではなく fail)。
**ローカルでは人間が用意する**(`NFR-014`)。

**注意(TSK-343 の実測)**: 環境変数が **`postgresql+psycopg://` 形式**の場合は
**SQLAlchemy の URL であり libpq conninfo ではない**ため psycopg が
`missing "=" after ...` で弾き、**`tests/db` の全件が setup error になる**。
**「DB / Docker に到達できない」という別の障害と区別できない**ので、
**`tests/db` の失敗が setup error で全件そろっていればスキームを疑う**。
**スキームから `+psycopg` を外して実行すれば 1 回で切り分けが付く。**

**人間が確認すること**: 8 件目の `mutate` が**単独変更**であること /
**toctou は注記のみの追加で SQL の意味が変わっていない**こと /
**`tests/db` の収集された全件が green** であること / **CI が全ジョブ green** であること。

## 8. 進め方

1. 本計画書を敵対レビューへ(**コア領域**): `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(1 周ごとに `計画レビュー周回` を +1)→ 収束したら**人間の承認**を求める
3. 承認後 `/implement` でステップ 1 から委任(1 委任 = 1 ステップ = 1 コミット・件名は `(ステップ k)`)
4. **実機の DB テストは人間へ依頼する**(**無選別の全件**・部分実行にしない)
5. **push 後に CI の全ジョブ green を確認してから人間へ引き渡す**(PR #52 で欠けた手順)
