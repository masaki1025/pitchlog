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
