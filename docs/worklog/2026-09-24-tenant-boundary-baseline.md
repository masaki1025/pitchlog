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
