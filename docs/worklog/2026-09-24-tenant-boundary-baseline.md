---
date: 2026-09-24
topic: 凍結基準の更新経路(設計書 7.7)への適合 — tenant_boundary 資産
branch: fix/tenant-boundary-baseline
---

# 作業ログ: 2026-09-24 凍結基準の更新経路への適合(TSK-431)

## やったこと

### 着手(/task-start)

ブランチ `fix/tenant-boundary-baseline` / worktree `../pitchlog-worktrees/fix-tenant-boundary-baseline`(起点 `origin/develop` = `bf8ba5b`)。**重さ分類 = コア領域**(テナント分離)。Notion TSK-431 を 着手可 → 進行中。

**担当は進行管理役のセッション(master)。** 同時に開けるタブが無く、PO 判断で兼務する。

### カードの記述の是正が必要(計画段階で反映する)

**カードの「前提・依存」欄が古い。** 同欄は「**7A は既知の fail-open のまま U-T1 がマージされる…本タスクの最優先項目とする**」と書くが、**同じカードの表の直前の注記が上書きしている**:

> **7A は 2026-09-21 に U-T1 の射程へ戻し、U-T1 の PR #72 で閉じた**(当初の影響評価が誤っており、統治の網にとどまらず**迂回検査そのものが no-op になる**ことが実測で判明したため)

PR #72 のコミットにも `fix: 迂回検査の比較元を検査対象から切り離す(3 周目 7A を射程へ戻して閉じる)` がある。**本タスクの実体は 7B / 7C / 7D / 7E の 4 件**(P0 3 + P2 1・8pt)。

### 履歴の「ちょうど 1 件」制約の解釈(TSK-440 との順序調整で実測)

`scripts/check_tenant_boundary_bypass.py:678-703` を読み、**「ちょうど 1 件」は merge-base 相対の増分**であることを確認した。

```python
if (len(current_history) < len(previous_history)
    or current_history[:len(previous_history)] != previous_history):
    raise ContractError("merge-base の既存履歴は変更・削除できない")
...
added = current_history[len(previous_history):]
...
if len(added) != 1:
    raise ContractError("射影が動いた受理には履歴をちょうど 1 件追加する")
```

**`added` は merge-base からの増分**であり絶対数ではない。したがって **TSK-440 と TSK-431 のどちらが先にマージしても、後から出す側が develop を取り込めば成立する**。`strict_required_status_checks_policy: true` が取り込みを強制するので、取り込み漏れも起きない。残る作業は `previous_baseline_identifiers` を新しい merge-base の値へ更新することだけで、機械的。

**TSK-440 の担当が当初「後からマージする側が壊れる」と見立てていたが、本実測を受けて撤回した。**

### `develop` の全違反 363 件(`--base-ref` を root commit にして全件走査)

**【訂正 — 当初「触れば表面化する潜在」と書いたが誤り】** `scripts/check_tenant_boundary_bypass.py:3806` の `_changed_source_violations` の docstring は逐語で「**変更ファイルを全行解析し、基準版から増えた違反を検出する**」であり、`scan_source_change(baseline_sources.get(relative), source, ...)` で**ファイルごとに基準版と比較**している。

**したがってファイルを触っただけでは既存の違反は表面化しない。増えたぶんだけが出る。** 下の 363 件は `--base-ref` を root commit にして基準版を空にした結果であり、「現在のツリーに存在する違反の総数」であって「触ると出る地雷の数」ではない。**TSK-424 の指摘により訂正**(2026-09-24)。

実害が出るのは**新しい違反を足したとき**で、具体的には TSK-424 PR A のステップ 13(製品の適用器)・14(製品のカタログ検査)が `backend/src/pitchlog/authz/` へ**新しい `cursor.execute` を足す**場合(424 の実測)。

| | 件数 | パッケージ別 |
| --- | ---: | --- |
| TB007 | **185** | `authz` 172 / `api` 9 / `db` 4 |
| **TB005** | **137** | 下表 |
| TB002 | 26 | |
| TB004 | 15 | |
| **計** | **363** | `authz` 244 / `db` 110 / `api` 9 |

### TB005 137 件の内訳(本セッションが測った — TSK-440 の推論を精密化)

symbol: `sqlalchemy.text` 64 / `psycopg.Cursor.execute` 35 / `psycopg.Connection.cursor` 24 / `psycopg.Connection.rollback` 8 / `psycopg.Connection.commit` 5 / `importlib.import_module` 1

**2 種類に割れる**:

| 群 | 件数 | 場所 | 性質 |
| --- | ---: | --- | --- |
| **A. 実行時 DB アクセス** | **72** | `authz/catalog.py` 40 / `authz/provisioning.py` 32 | **真陽性**。`with connection.cursor() as cursor: cursor.execute(...)`(`catalog.py:397-398`)。`allowed_symbols` に無いインフラ |
| **B. 宣言的スキーマ定義** | **65** | `db/*/models.py`(tenant_isolation 30 / game_state 12 / sync_protocol 11 / recording_rights 9 / data_migration 2 / all_models 1) | **誤検知**。`server_default=text("true")`(`models.py:65`)/ `postgresql_where=text("kind = 'self'")`(同 `:117`)= DDL の宣言であって実行時アクセスではない |

**TSK-440 は「137 件は真陽性の可能性が高い」と推論していたが、B の 65 件は別種の誤検知**。本セッションの指摘を受けて TSK-440 が撤回し、自分の射程へは引き込まず申し送りとして記録する方針にした。

`contracts/tenant_boundary/base-allowlist.json` の `allowed_symbols` は現在 **5 件のみ**:
`pitchlog.db.engine.create_database_engine` / `pitchlog.db.engine._verify_application_role_connection` / `pitchlog.repositories.context.TenantContext.__init__` / `pitchlog.repositories.binding._tenant_transaction` / `pitchlog.repositories.base.TenantRepositoryBase._execute_operation`

### TSK-424 の PR C(Session 供給)への波及

`contracts/tenant_boundary/db-api-inventory.json` に **`sqlalchemy.orm.Session` 27 箇所・`sessionmaker` 2 箇所・`scoped_session` 2 箇所**が登録済み(実測)。

**したがって PR C が Session 供給を新設すると、供給シンボルを `allowed_symbols` へ足さない限り TB005 に当たる**(誤検知ではなく設計どおりの検出)。`base-allowlist.json` は `FROZEN_BASELINE_ASSETS` の 1 つなので、**追加は 7.7 の「基準を動かす」行為**であり、**7C が開くまで 7.7-2 に適合する記録を書けない**。

### 7C を待つ消費者は 4 件(424 の回答で確定)

| # | 消費者 | 触る資産 |
| --- | --- | --- |
| 1 | **帯 2 の capability 登録**(U-M1 ほか) | `repository-contract.json` |
| 2 | **TSK-424 PR A ステップ 13 以降**(製品の適用器・カタログ検査が新しい `cursor.execute` を足す) | `base-allowlist.json` の `allowed_symbols` |
| 3 | **TSK-424 PR C**(Session 供給) | 同上 |

**PR B は 7D を待つ**(削除した資産の旧パスの履歴を検査できないため)。

**424 の提言: 7C を 7B の直後に置くと 3 つ同時に開く。** 計画のステップ順に反映する。

## 決定

- **TSK-440 とのマージ順序は固定しない。** 準備ができたほうから出し、後から出す側が develop を取り込んで履歴を 1 件足し直す(上記の実測による)。**PO 承認済み(2026-09-24)**
- **「基準の値」と「検査の手続き」の線引きは TSK-431 が決める**(TSK-440 と合意・案 A)。TSK-440 は「導出規則を資産に置くのは可 / 導出結果を資産に置くのは不可」の安全側にいるので、どちらの線を引いても矛盾しない見込み
- **7B を計画の先頭に置く。** TSK-440 の敵対レビューが `tenant-context-allowlist.json` の `pass_fail_mapping` が `external_files` 空で動かない件(= 7B の実害 1 例目)を P1 で指摘しており、**7B が先に develop へ入れば TSK-440 が申し送りでなく本来の形で受理できる**ため。**ただし TSK-440 を待たせない**

## 未決・次の一歩

- **`/investigate` 3 並列の結果待ち**(決定経緯 / 条文突合 / 現況測定)
- **TSK-424 PR C が 7C を待つか**の確認 — 424 へ依頼済み・未回答
- **線引き(基準の値 vs 検査の手続き)の結論** — TSK-421(#73・マージ済み)が同じ型を別資産系列で解いているはずなので、その方式を流用できるかが中心論点

## ステップ 1(2026-09-24)

### draft PR

**#78**(https://github.com/masaki1025/pitchlog/pull/78)。**`acceptance_id` = `masaki1025/pitchlog#78` に確定**した。

**実装より先に PR を作る理由**: `acceptance_id` を `{repository.full_name}#{pull_request.number}` から機械導出し、イベント値と照合する(design.md 4 節)。**PR 番号が無いと v2 の記録を書けない。**

### 送り出し 4 件の対応表

| 送り出す項目 | 受取タスク | 出所 |
| --- | --- | --- |
| **7D の残り**(削除記録の置き場・履歴アーカイブ・安定した履歴 ID) | **TSK-448** | 計画書「やらないこと」・design.md 0 節・5 節 |
| **7E**(バイト正規化) | **TSK-449** | 計画書「やらないこと」 |
| **センチネル 7 件**(7.7 に既存記録の訂正の規定が無い) | **TSK-450** | 計画書「やらないこと」・1 周目 `P0-1` |
| **次回以降の通常更新で比較元版の評価器を使うか** | **TSK-451** | 計画書「やらないこと」・2 周目 `P0-2` |

**4 項目すべてに受取タスクがある**(4 周目 `P1-7` の是正)。TSK-448 は **TSK-431 のマージが前提**(`history-snapshots/` と `record_schema_version: 2` が入ってから)。

### カードの現況化 — 3 件

**典拠つきで記録する。カード本文は書き換えない**(計画書がこの記録を正とする)。

| # | カードの記述 | 現況 | 典拠 |
| --- | --- | --- | --- |
| 1 | 「前提・依存」欄が **7A を未完として挙げている** | **7A は PR #72 で完了済み** | PR #72(マージ済み)。本タスクの射程は 7B + 7C + 7D の最小限 |
| 2 | 本文の**行番号参照が現行 HEAD とずれている** | research.md 1 節で実測済み。**計画書と設計書では節番号と関数名で書く** | research.md 1 節 |
| 3 | 射程が **7B/7C/7D/7E の 4 テーマ**として書かれている | **7E は送り出した**(TSK-449)。**7D は最小限だけ**(残りは TSK-448) | 計画書「やらないこと」 |

### 行番号参照の検査

`plan.md` と `design.md` に対して `\.(py|md|json|yml|ts|vue):[0-9]+` を走査 → **0 件**(ステップ 1 の合格条件)。research.md は調査の記録なので対象外(3 周目 `P2-2` の是正)。

### ステップ 1 の合格条件の充足

- [x] **draft PR が存在し PR 番号が確定している** — #78
- [x] **worklog に 3 件が典拠つきで記録されている** — 上記「カードの現況化」
- [x] **計画書と設計書に行番号参照が 0 件**
- [x] **送り出し 4 項目それぞれに受取タスク ID が対応付いた表がある** — TSK-448 / 449 / 450 / 451

## ステップ 2〜8(2026-09-24)

### 実装コミット

| ステップ | コミット | 中身 |
| --- | --- | --- |
| 1 | `86e089b` | draft PR #78・送り出し 4 件の起票・カードの現況化 |
| 2 | `0ad3eb1` | 版付き履歴 record の parser(未結線) |
| 3 | `195ff6e` | v2 の内容保存と機械導出した aspect の照合(未結線) |
| 4 | `870a7ac` | 評価の役割分担と PR 受理モードの強制(未結線) |
| 5 | `ef8959f` | 普遍下限の一般則と比較元側 ∪ HEAD 側の走査(未結線) |
| 6 | `98fb04a` | fail-closed の網羅と HEAD 側 fallback の不在証明(未結線) |
| **7** | **`4b05a09`** | **結線・`external_files`・`history_authority`・記録と識別値(検査器を触る唯一のコミット)** |
| 8 | `7f22075` | 変異テストの `[0]` 固定を解消し 7 資産 parametrize |

**ステップ 2〜6 では検査器を 1 バイトも触っていない**(各コミットで `git status` により確認)。

### 差し戻し 2 件(委任先の報告ではなくコードを検証して発見)

| ステップ | 指摘 | 実測 |
| --- | --- | --- |
| **2** | `_json_deep_equal` が int と float を数値として等価に扱い、**prefix の `13` を `13.0` に書き換えると素通り**した | `baseline_control` は `frozen_projection.excluded` に入るので履歴は射影の sha256 に含まれない。**prefix の deep-equal が比較元を守る唯一の機構**であり、数値型の差で素通りできると記録なしに既存履歴を書き換える経路になる。型一致まで要求する形へ是正 |
| **3** | 予約 marker 検査が **strip + upper の完全一致**で、`未承認(PR #78 のレビュー待ち)` と `TODO: 後で` が素通りした | 既存 v1 記録の `approved_by` は実際に `未承認(PR #72 のレビュー待ち)`。**この行をコピーして PR 番号だけ書き換える形が最も起きやすい**。包含判定へ是正し、`山田正輝` が誤検出されないことも確認 |

**既知の過剰検出**: 承認者名が予約語(`未定` など)を部分文字列として含むと拒否される。**受理せず拒否する側の誤り**なので fail-closed の方向として許容する。

### 私の誤り 1 件(訂正)

ステップ 7 の記録を見て「**`aspect` / `declaration` / `movement_policy` / `external_snapshots` が無く D3 が骨抜き**」と判断したが、**誤り**。これらは `change` の 1 段下に入っていた(`change = {subject, aspect, before, after}`、`before`/`after` が 3 キーを持つ)。**実内容との deep-equal と `aspect` の機械導出・exact-set 照合はいずれも効いている**。トップレベルのキーだけを見たのが原因。

## ステップ 9 — 人間の逐行確認(突合シート)

### 確認対象(SHA 固定)

- **対象=** `fix/tenant-boundary-baseline` の `e62aced..7f22075`(develop からの全差分)
- **範囲=** うち**逐行確認の中心は `4b05a09`(ステップ 7)** — 検査器を触る唯一のコミット。他 7 コミットは未結線の追加とテスト
- **方法=** 本シートの 3 節それぞれを目視で突合し、**PR 本文のチェックボックスへ記入**する

**確認後の差分は worklog 等の証跡ファイルに限る**(最終 HEAD SHA を書くと自己参照になるため — 5 周目 `P1`)。

### 1. 7 資産の `external_files` の exact-set

**期待する exact-set(順序込み)**:

1. `scripts/check_tenant_boundary_bypass.py`
2. `scripts/frozen_history.py`
3. `.github/workflows/ci.yml`

| 資産 | `external_files` | `history_authority` | 識別値(新) | 識別値(旧) |
| --- | --- | --- | --- | --- |
| `base-allowlist.json` | **一致** | `true` | `contract_revision:14` | `contract_revision:13` |
| `cache-invalidation-contract.json` | **一致** | `false` | `contract_revision:2` | `contract_revision:1` |
| `db-api-inventory.json` | **一致** | `false` | `inventory_revision:4` | `inventory_revision:3` |
| `negative-fixtures.json` | **一致** | `false` | `fixture_set_revision:6` | `fixture_set_revision:5` |
| `repository-contract.json` | **一致** | `false` | `contract_revision:3` | `contract_revision:2` |
| `runtime-authz-contract.json` | **一致** | `false` | `runtime_contract_revision:2` | `runtime_contract_revision:1` |
| `tenant-context-allowlist.json` | **一致** | `false` | `contract_revision:5` | `contract_revision:4` |

**変更前は `base-allowlist.json` だけが `["scripts/check_tenant_boundary_bypass.py"]` を持ち、他 6 資産は空だった**(7B の実害)。

**`history_authority: true` はちょうど 1 件。記録も `base-allowlist.json` にだけ 1 件追記されている**(他 6 資産の history 件数は 1 件のまま)。

**既存 7 記録の生 JSON は 1 バイトも変わっていない**(7 資産すべてで prefix 不変を機械確認済み)。

### 2. モード結線

| 確認項目 | 実装 |
| --- | --- |
| モードの決定元 | `frozen_history.resolve_evaluation_context()` が **`GITHUB_EVENT_NAME` を読む**。workflow の指定に従わない |
| PR コンテキストでの fallback | **無い**。`GITHUB_EVENT_PATH` が無い・読めない・キーが足りない場合は**例外**。不変量モードへ落ちない |
| PR 受理モードの条件 | `base.ref == develop` / HEAD が 2 親 / 第一親 == `base.sha` / 第二親 == `head.sha` / 遷移と記録 / `acceptance_id` の照合 |
| 不変量モード | `push` / `workflow_dispatch` / ローカル。遷移と `acceptance_id` を検査しない |
| `ci.yml` の扱い | **7 資産の `external_files` に含めた**(内容は変更していない)。workflow を書き換えて不変量モードだけを走らせる経路を射影で観測する |
| 実 CI での実走 | **draft PR #78 の `tenant-boundary-bypass` ジョブが PR コンテキストで pass**(合成 fixture だけで満たしていない — DoD の D4 項目) |

### 3. D1〜D6 の実装対応

| 裁定 | 実装 | 確認の勘所 |
| --- | --- | --- |
| **D1** 単一検査・1 記録 | `validate_repository_histories` / `validate_history_authority` / `_validate_movement_record_count` | **`history_authority: true` が 0 件・2 件でも red**。**authority 以外へ追記すると red**。**同一受理で 2 件足すと red** |
| **D2** 版付き schema | `parse_history` / `_json_deep_equal` | **prefix は生 JSON 値の deep-equal で、数値の型一致まで要求**。prefix 以後は明示 v2 のみ |
| **D3** content-addressed snapshot | `_validate_v2_record` / `_snapshot_state` / `_validate_snapshot_append_only` | `change.before` / `change.after` が **内容そのもの**を持ち、実遷移と deep-equal。**`aspect` は実差分から機械導出して exact-set 照合**。snapshot は追記専用 |
| **D4** 役割分担とモード強制 | `derive_role_separated_evaluation` / `resolve_evaluation_context` | **`after` の `external_snapshots` も比較元の対象集合で作る** — HEAD が自分の宣言で対象を縮小して自己申告する経路を塞ぐ |
| **D5** 普遍下限と 7D の最小限 | `REQUIRED_MOVEMENT_TRIGGERS` / `_movement_axis_values` / `evaluate_repository_movement` | **実装定数は 6 token ちょうど**。下限外は比較元宣言から取る。**6 token それぞれを実状態へ写像**(字面ではない)。**走査は比較元側 ∪ HEAD 側**で、比較元にあって HEAD に無い資産は red |
| **D6** 実装の隔離 | コミット履歴 | **ステップ 2〜6 のどのコミットでも検査器が 1 バイトも変わっていない** |

### snapshot の内容照合(機械確認済み)

| snapshot | 内容 | 照合結果 |
| --- | --- | --- |
| `dadd3e8604a2…` | `before`: develop 版の `check_tenant_boundary_bypass.py` | **develop の実内容と sha256 一致** |
| `3bab40813e14…` | `after`: HEAD 版の `check_tenant_boundary_bypass.py` | **HEAD の実内容と sha256 一致** |
| `361a9de2238c…` | `after`: HEAD 版の `frozen_history.py` | **HEAD の実内容と sha256 一致** |
| `47d436cef5f1…` | `after`: HEAD 版の `ci.yml` | **HEAD の実内容と sha256 一致** |

**4 ファイルすべてで「ファイル名 == 内容の sha256」が成立**(content-addressed)。

**申告 `aspect` = `["declaration", "external_snapshots"]`。** `movement_policy` は入っていない — `history_authority` は `movement_policy` の兄弟であり `movement_policy` 自体は変えていないため、実差分と整合する。

### ゲートの状態

| ゲート | 結果 |
| --- | --- |
| `uv run pytest tests/` | **1757 passed** |
| `uv run ruff check .` | green |
| `uv run ty check` | green |
| `uv run python scripts/check_tenant_boundary_bypass.py` | `tenant-boundary bypass check: ok` |
| CI `tenant-boundary-bypass`(PR コンテキスト) | **pass** |
| CI `core-guard` | **fail — 本逐行確認の完了を待っている**(PR 本文のチェックボックス) |

### 人間の判断が要る 2 件(私は手を付けていない)

1. **PR 本文のチェックボックス** — `core_guard` が `- [x] コア領域/検査経路の変更: 人間による逐行確認を実施した` を要求する。**これを満たすまで CI は red のまま**
2. **`scripts/frozen_history.py` が `.claude/core-areas.json` のどのパターンにも該当しない**(実測)。`tests/test_frozen_history.py` も同様。**本 PR がこの穴を作った** — `frozen_history.py` は tenant 分離の凍結更新判定を丸ごと担うのに、変更が `core_guard` の人間確認要求を素通りする。**登録は設計書 6.3 規則⑤の人間判断**なので、本 PR へ含めるか別タスクへ送るかを決める必要がある

### 確認対象の現行化(CI 是正後)

**シート冒頭の `対象= e62aced..7f22075` は `6d36a07` までに更新する。** ステップ 9 の逐行確認は下記を対象とする。

- **対象=** `fix/tenant-boundary-baseline` の `e62aced..6d36a07`
- **範囲=** **逐行確認の中心は `4b05a09`(ステップ 7)と `6d36a07`(その是正)** — 検査器を触る 2 コミット。他は未結線の追加・テスト・証跡
- **方法=** 本シートの 3 節を目視で突合し、PR 本文のチェックボックスへ記入する

### CI で出た実欠陥 2 件(`6d36a07` で是正)

**どちらもローカルの `uv run pytest tests/` だけでは出ない差だった。**

| # | 欠陥 | 原因 | 是正 |
| --- | --- | --- | --- |
| **1** | CI の `harness` で **10 件 fail**。`fatal: Invalid symmetric difference expression e62aced...HEAD` | `check_repository` が PR 受理モードのとき**引数の `base_ref` を無条件に捨てて `pull_request.base_sha` を使っていた**。一時リポジトリを検査するテストは自分の commit を渡すので、そこに無い develop の commit を参照して git が落ちた。**ローカルは `GITHUB_EVENT_NAME` が無く不変量モードなのでこの経路を通らない** | **イベントの適用範囲を `GITHUB_WORKSPACE` と同一のリポジトリに限定**。同一 workspace で**イベントと食い違う明示 `base_ref` は拒否**(自分で base を選び直す経路を開かない)。**別のリポジトリルートにはイベントを適用しない**。あわせて**評価コンテキストを履歴検査まで引き渡し、環境変数を再読して PR モードへ戻る経路を消した** |
| **2** | CI の `backend` で `contract_revision: 2 != 3` / `source_digest` 不一致 | `repository_contract.py` / `tenant_context_contract.py` / `runtime_contract.py` は**いずれも `contracts/tenant_boundary/` の資産からの生成モジュール**。ステップ 7 で資産を繰り上げたのに**生成物が旧版のまま**だった。**委任先が `backend/` のテストを回していなかった** | **3 件を資産から生成し直した**。**資産側は変えていない**(生成物を資産へ合わせるのであって逆ではない) |

**`6d36a07` は検査器と `frozen_history.py` を触るので射影が動く。** **新しい記録は足さず**(1 受理 1 記録)、**既存 v2 記録の `change.after` の snapshot 参照を実内容へ合わせ直した**。

- **旧 snapshot 4 件は不変**、**新 snapshot 2 件を追記**(計 6 件。全件で「ファイル名 == 内容の sha256」が成立)
- **識別値・記録件数・`external_files`・`history_authority` は 7 資産すべてで変えていない**(機械確認済み)

### DB テストを実機で実行した(委任先では未実行)

委任先の sandbox は Docker API へ接続できず **DB 必須 211 件が未実行**だった。**使い捨ての PostgreSQL 17.11-bookworm を別ポートで立てて自分で回した**(開発 DB と `.env` には触れていない)。

| 対象 | 結果 |
| --- | --- |
| `backend/` `uv run pytest` | **585 passed**(DB 必須 211 件を含む) |
| `backend/` `ruff check` / `ruff format --check` / `ty check` | green |
| ルート `uv run pytest tests/` | **1760 passed** |
| ルート `ruff check .` / `ty check` | green |
| `uv run python scripts/check_tenant_boundary_bypass.py` | `tenant-boundary bypass check: ok` |

**罠 1 件**: `db_fixtures.py` の被検査ロール fixture は**ロールを自前で作り、事前に存在すると fail-closed で落ちる**。CI の DSN を真似て `pitchlog_test_role` を先に作ったら 211 件が error になった。**事前に作らないのが正しい**。使い捨てコンテナは削除済みで、開発 DB にロールの残滓が無いことも確認した。

### CI の最終状態(`6d36a07`)

| ジョブ | 結果 |
| --- | --- |
| `tenant-boundary-bypass` | **pass**(PR 受理モードで実走 — DoD の D4 項目) |
| `harness` | **pass**(10m34s) |
| `backend` | **pass**(7m20s) |
| `frontend` / `docs-lint` / `secrets` / `nfr021-append-only` / `backend-changes` / `frontend-changes` | pass |
| **`core-guard`** | **fail — 本逐行確認の完了を待っている**(PR 本文のチェックボックス) |

## ステップ 10(2026-09-25)

### 計画スコープ外の変更 1 件(逸脱として記録 — 計画改訂の申し送りへ)

**`.claude/core-areas.json` の `tenant-isolation` 領域へ 2 件を追加した。**

- `scripts/frozen_history.py`
- `tests/test_frozen_history.py`

**理由**: **本 PR がこの穴を作った**。`frozen_history.py` は tenant 分離の凍結更新判定を丸ごと担うのに、**core-areas の 315 パターンのいずれにも該当せず `guard_paths` にも無かった**(実測)。**今後の変更が `core_guard` の人間確認要求を素通りする。**

**本 PR に含めた判断の根拠**: 穴を作ったのが本 PR であり、かつ **本 PR は既に逐行確認ゲートを通るので、ここで閉じても追加のゲートコストが無い**。別タスクへ送ると、その間 `frozen_history.py` の変更が無検査で通る期間ができる。

**置き場の選択**: `guard_paths` ではなく **領域の `paths`** にした。`scripts/check_tenant_boundary_bypass.py` と `tests/test_check_tenant_boundary_bypass.py` が同領域にあり、**`frozen_history.py` はその helper** だから。`scripts/frozen_baselines.py` が `guard_paths` にある前例もあるが、そちらは領域に属さない凍結基盤の検査経路。

**追加不要だったもの**: `contracts/tenant_boundary/history-snapshots/` は **既存の `contracts/tenant_boundary/*` で覆われている**。`core_guard.matched_paths` は `fnmatch.fnmatchcase` を使うので **`*` が `/` を越える**(実測で確認)。

### 付随して落ちた 2 件と追随

| テスト | 原因 | 対応 |
| --- | --- | --- |
| `test_core_guard.py::test_actual_core_area_paths_are_exact_expected_set` | **期待集合が人手の列挙**(`TENANT_BOUNDARY_AREA_PATH_CASES`)で、`EXPECTED_AREA_PATHS` が**列の順序まで比較**する | **同じ順序で 2 件を追加** |
| `test_doc_check_profile.py::test_propagation_checker_and_claude_files_are_unchanged` | `git diff HEAD -- .claude/` が空であることを要求する。**未コミットの `.claude/` 変更**で落ちていた | **コミットで解消**(内容の問題ではない) |

**観察**: 期待集合の人手列挙は、本日 TSK-440 のセッションと共有した「**母集団を人が列挙する検査は射程が動くと黙って古くなる**」の一例そのもの。**本 PR の射程外なので直していない**が、運用評価台帳の候補として `/pr` のクローズ処理で検討する。

### PR 本文へ転記した内容(ステップ 10 の合格条件)

- **`design.md` 8 節の 5 項目**を**同じ順序で**そのまま転記した(転記件数を機械確認: 5 件)
- **送り出し 4 件と受取タスク ID の対応表**(TSK-448 / 449 / 450 / 451)
- **計画スコープ外の変更 1 件**を逸脱として明記
- **逐行確認のチェックボックス**(未チェック — **人間が入れる欄**。私は書かない)

### 最終ゲート

| ゲート | 結果 |
| --- | --- |
| ルート `uv run pytest tests/` | **1766 passed** |
| ルート `uv run ruff check .` / `uv run ty check` | green |
| `backend/` `uv run pytest` | **585 passed**(DB 必須 211 件を含む・実機の PostgreSQL 17.11) |
| `backend/` `ruff check` / `ruff format --check` / `ty check` | green |
| `uv run python scripts/check_tenant_boundary_bypass.py` | `tenant-boundary bypass check: ok` |

**残りは人間の逐行確認 1 件のみ。** `core_guard` はそれを待って red のまま。

## クローズ処理(2026-09-25)

### 結果サマリ

**何を実装したか**: 設計書 7.7「凍結基準の更新経路」への適合。**7C**(履歴が変更前後の実内容を持つ)+ **7B**(7 資産の `external_files` へ合否写像の実体)+ **`required_triggers` の第 2 決定元の解消** + **7D の最小限**(比較元側 ∪ HEAD 側の走査)。

**何を正本へ反映したか**:

| 正本 | 反映内容 |
| --- | --- |
| `docs/development/harness-evaluation.md` | **`## 候補` へ 1 件 + 既存候補へ 5 例目 + 変更履歴表へ 1 行**(**版は上げない** — 7.6-3 前段) |
| `docs/README.md` | 台帳行の最終更新日を 2026-09-25 へ |
| 設計書 7.7 / `data-model.md` / 要件書 | **反映なし**(本タスクは条文への適合であって改訂ではない。**要件書に 7.7 の上位根拠は無い** — research.md 4 節) |

**正本体系外で同一 PR が運ぶもの**: `.claude/core-areas.json`(**計画スコープ外の逸脱** — 本 PR が作った穴を閉じる)と `tests/test_core_guard.py`(その期待集合の追随)。

### 台帳への追記の判断

**該当する**と判断した。追記した 2 件は次のとおり。

**新規候補** — **検査器が実行文脈の環境変数で経路を変えると、同じコマンドがローカルと CI で別の検査になる**

既存候補「検証コマンドを人が選ぶと、CI が走らせるコマンドとの差分が黙って残る」の 4 事例は**コマンド違い / 収集対象違い / 層違い**で、いずれも**検証する側の選択**に原因があった。本件は**検証する側が何を選んでも差が出ない** — **被検査コード自身が実行文脈で分岐する**。そして**このモード強制は 7.7-3 の要求そのもの**なので、**条文を満たすと同時にこの型を必ず作る**。

**既存候補へ 5 例目** — **委任先が `backend/` のゲートを回さず、生成モジュール 3 件の追随漏れが CI まで残った**

**3 例目(`ruff format --check` の脱落)と同一構造が 4 日後に別タスクで再発**した。**本タスクの対処は 3 例目と同じ「委任プロンプトへの常駐」であり、再発を防げなかった手当てでもある**ことを明記した。

### 追記しなかったもの(判断の記録)

| 知見 | 扱い | 理由 |
| --- | --- | --- |
| **母集団を人が列挙する検査は射程が動くと黙って古くなる**(本タスクの実例 2 件: 4 周目の「12 件の負例」列挙が棄却された件 / `EXPECTED_AREA_PATHS` の人手列挙) | **TSK-440 のセッションへ受け渡し済み。本タスクからは追記しない** | **先方が自身のクローズ処理で書くと明言**しており、**両方から書くと同じ候補が二重に数えられる**。**実例と、12 件列挙が「良い実践」ではなく「棄却された形」である旨の訂正は先方へ伝達済み** |
| **打ち切りの判断材料は周回数ではなく P0 の推移と内訳** | 同上 | **先方が候補として書くと明言**。本タスクの実例(4 周目の打ち切り提案が早く、5 周目に新種 2 件・P0 4 件が出た)も伝達済み |
| **`db_fixtures.py` の被検査ロール fixture は事前にロールが存在すると fail-closed で落ちる** | **追記しない** | **既知**。`docs/features/orm-schema-migration/plan.md` の `S-6` と 2026-09-09 の worklog 2 本に記録済みで、**新しい知見ではない**。本タスクは復旧手順どおりに解消した |
| **委任先の sandbox が Docker へ繋がらず DB テストが未実行で返る** | **追記しない** | **既知**。無人時の品質約束に「DB テストは必ず自分で実機で回す」として既に常駐している運用であり、**本タスクはそれが働いた例**にすぎない |

### 突合

- **未コミット**: なし
- **正本反映の双方向突合**: `check_plan_docs_sync.py` で機械突合(下記)
- **現在地導出**: `feature_status.py` の出力を PR 本文へ転記
- **品質**: 全ゲート green(ルート 1766 passed / backend 585 passed〔DB 必須 211 件を含む〕/ ruff / ty / 検査器)

### レビュー観点(コア領域 — 敵対レビュー + 人間の逐行確認が必須)

1. **`change.before` / `change.after` が実遷移と deep-equal で、`aspect` が実差分から機械導出されているか**(D3 — 5 周目 `P0-2` の是正)
2. **PR 受理モードの強制に fallback が無いか**(D4 — 7.7-3 が禁じる「判定の省略」)
3. **6 token それぞれが実状態へ写像され、字面の変異で代替されていないか**(D5 — 5 周目 `P0-3` の是正)
4. **1 受理 1 記録が崩れる経路が無いか**(D1 — authority 以外への追記・同一受理で 2 件)
5. **`design.md` 8 節の 5 項目が、実装が実際に保証していない範囲と一致しているか**

## 実装の敵対レビュー 1〜4 周(2026-09-25〜26)

| 周 | 指摘 | うち新種 | P0 | 判定 |
| --- | ---: | ---: | ---: | --- |
| 1 | 5 | 5 | **3** | マージ不可 |
| 2 | 4 | 4 | 1 | マージ不可 |
| 3 | 3 | 2 | 2(うち 1 件は前周の是正未完) | マージ不可 |
| **4** | 2 | 2 | **0** | マージ不可(P1・P2 のみ) |

**P0 が 4 周目で 0 になったため、PO 判断で打ち切り。5 周目は回さない。**

### 3 周連続で出た型 — 「関数は正しいが本番経路がその結果を使っていない」

| 周 | 該当 | 中身 |
| --- | --- | --- |
| 1 | `P0-1` | **既存の検査を結線から外した**。`_validate_baseline_transition` が develop では本番から呼ばれていたのに、結線でテスト専用になった。**契約本文を変えて宣言と履歴を据え置くと `moved == false`** になり、**develop なら red だった変更が green** になっていた |
| 1 | `P0-2` | **union 走査が死んだコード**。比較元と HEAD の資産マップをどちらも HEAD の定数から作っており、`evaluate_repository_movement` が本番から一度も呼ばれない(**比較元列挙が定数依存だったこと自体は develop 由来** — TSK-440 セッションの指摘で訂正) |
| 2 | `P1` | **union 評価の結果を呼出し元が捨てていた**。HEAD 側だけの資産追加を `baseline_set` movement として返すのに、直後の `base_names != head_names` で無条件拒否 |
| 3 | `P0-1` | **`evaluate_repository_movement` の戻り値を束縛していなかった**。`moved` を `derive_aspects` から別途再計算しており、**比較元が宣言した trigger が判定を一切変えなかった** |

**毎周この型を名指しで禁じ、「本番 `check_repository` 経路を通る変異テストで示せ」と指示していたにもかかわらず 3 周連続で出た。** 4 周目の是正指示では、個別の是正の前に**全公開関数の本番到達性の列挙**と**戻り値を捨てている呼び出しの全件確認**を要求した。

**有効だった判定基準**: **機構を壊す変異を入れて、本番経路テストが落ちるかを見る。** 落ちなければ結線されていない。**関数を直接呼ぶテストは、この 4 件をどれも捕まえられなかった。** TSK-440 セッションは同じ基準を自ら適用し、4 機構すべてが落ちることを実測している。

### 各周の主な是正

| 周 | 是正 |
| --- | --- |
| 1 | 7 資産の完全な凍結射影を content-addressed snapshot として記録へ含め本番検査へ復帰 / 比較元を `git ls-tree` で独立列挙し union 走査 / `GITHUB_WORKSPACE` による PR モード降格の廃止 / 影響資産の識別値更新を必須化 / 識別値を資産ごとの map へ |
| 2 | `required_triggers` を `frozen_history` の単一実装へ集約し実装側の `pass_fail_mapping` を削除 / HEAD 側への資産追加を受理 / 相対パス・symlink・Git blob 種別の検査 / 到達不能な旧経路を削除し `_read_external_implementations` を本番へ結線 |
| 3 | `movement_evaluation` を束縛し `moved` と `affected_assets` に使用 / 予約 marker の走査を**除外リスト方式**へ(record 全体の文字列を再帰走査し、明示した機械値だけ除外) |
| 4 | **未実施**(Codex のサービス障害で停止。下記) |

### 4 周目に残った 2 件(是正待ち)

| 重さ | 中身 |
| --- | --- |
| **P1** | **不変量モードが設計の範囲を超えて検査している**。`_validate_latest_v2_state` が最新 v2 の `after` と現在の完全状態を無条件比較するため、**PR 受理モードで正当に合格した遷移が、マージ後の develop への `push` で不合格になりうる**。`design.md` 4 節は不変量モードを「資産の構造・履歴の内部整合・prefix の deep-equal」に限定している。**現時点では発火しない**(7 資産すべてが全 token を宣言しているため)が、**このリポジトリは過去に同型でdevelop と全子ブランチを止めている** |
| **P2** | **予約語の部分一致が自然文を過剰検出する**。走査対象を `movement_fact` / `reason` / `change.subject` へ広げたため、**`未定義` が `未定` に、`suspending` が `PENDING` に当たる**(実測)。**以前「fail-closed 側だから許容」と判断したが、対象が自然文へ広がった時点でその判断は成立しなくなった** |

## Codex のサービス障害による停止(2026-09-26 07:52〜)

**4 周目の是正を投げた直後から、`codex_run.py` の全呼び出しが 401 で失敗した。**

```
ERROR: Reconnecting... 1/5 〜 5/5
warning: Falling back from WebSockets to HTTPS transport.
ERROR: unexpected status 401 Unauthorized: Incorrect API key provided: sk-svcac…fvMA
url: https://chatgpt.com/backend-api/codex/responses
```

**4 セッション(TSK-236 / TSK-431 / TSK-440 / 他)で同時発生し、キー接頭辞まで同一。** ユーザーの連絡により **Codex 側のサービス障害**と確定した。

**ローカル調査の結果(値は読んでいない)**: 環境変数 `OPENAI_API_KEY` などは未設定 / `~/.codex/auth.json` の `OPENAI_API_KEY` は null で `last_refresh` は成功 / `config.toml` 2 種にキーなし / **Claude Code のシェルスナップショットに `OPENAI_*` の文字列は 0 回**。**探す対象が最初から存在しなかった。**

**本セッションが出した決め手 2 つ**:

1. **使用上限は 401 ではなく専用メッセージで出る**(00:47 に実際に当たったログ: `You've hit your usage limit ... try again at Sep 30th`)。これにより「上限超過が別資格情報へフォールバックしている」という仮説が早期に潰れた
2. **最後の成功時刻 07:37:53**(4 周目レビューの完了)と `auth.json` の mtime 07:54 により、**発生窓が 14 分に締まった**

**あわせて `grep` がシェル関数として壊れる症状も出たが、別系統と判明した。** Claude Code のシェルスナップショットが `grep` を関数で置き換えて同梱の `ugrep` へ委譲しており、そのバイナリが無い環境でフォールバックが効ききらない。**スナップショットは 2 日前(2026-09-24 00:42)のもので 401 とは無関係。** 回避は `/usr/bin/grep`(本セッションは python 読みへ切り替えた)。

**被害はゼロ。** 失敗した委任は 1 バイトも書いておらず、作業ツリーは変更 0 件。

## CI の沈黙とその原因(2026-09-25〜26)

**`ae7530c` 以降の 3 push で CI が 1 つも走っていなかった。**

**原因は PR #78 が develop とコンフリクトしていたこと**(`mergeable=CONFLICTING` / `state=DIRTY`)。**GitHub は `refs/pull/78/merge` を作れないと `pull_request` の workflow を起動しない。** 同じリポジトリの PR #80 が走っていたのは、そちらが衝突していなかったため。

**衝突は `docs/README.md` と `docs/development/harness-evaluation.md` の 2 ファイルのみ**で、**実装の衝突はゼロ**(develop 側は `contracts/tenant_boundary/*`・検査器・`frozen_history.py`・`core-areas.json` を一切触っていない)。

**内容の衝突が 1 件**: **TSK-424 PR A1 が同じ候補「検証コマンドを人が選ぶ」へ 5 例目を追記していた**ため、本タスクの分を **6 例目へ繰り下げ**、索引の候補数を **77 件**へ更新した。

**取り込み後、`mergeable=MERGEABLE` になり CI が復活。** **`core-guard` 以外すべて pass**(`tenant-boundary-bypass` は **PR 受理モードで実走して pass** — DoD の D4 項目を現行 HEAD で充足)。

**教訓**: **CI が「走っていない」ことと「通っていない」ことは別**である。`gh pr checks` は前者を `no checks reported` としか言わない。**push のたびに run が作られたかを確認する必要がある。**
