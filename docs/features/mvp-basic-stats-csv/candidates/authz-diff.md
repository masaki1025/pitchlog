# 基本成績APIの正式資産候補差分（未受理）

本ファイルは候補であり、`contracts/` を編集していない。owned隔離DBの検証で使った
完全な前後値だけを固定する。正式導出・seal/7.7は主担当が行う。

## 1. DB関数

`candidates/basic_stats_functions.sql` の全文を配置する。

- schema: `stats_basic_api`（owner `pitchlog_owner`、app USAGEのみ）
- `stats_basic_api.read_basic_stats(p_tenant_id uuid,p_game_id text,p_year_start text,
  p_year_end text,p_category text,p_raw_game_type_keys text,p_official boolean,
  p_after_player_id text,p_page_size integer,p_model_sha256 text)`
  - `SECURITY DEFINER`, `STABLE`, `SET search_path=pg_catalog,pg_temp`
  - 実体は既存 `stats/generated/stats.sql` のscope差し替えのみ
- `stats_basic_api.finalize_game_stats(p_tenant_id uuid,p_game_id uuid,
  p_completion_receipt_id uuid,p_public_pointer_receipt_id uuid,p_model_sha256 text)`
  - `SECURITY DEFINER`, `VOLATILE`
  - `current_open` → `confirmed_ended` の原子的UPDATE。同receipt再実行は冪等、別receiptは拒否。

## 2. ACL/RLS（既存catalogへの追加）

```sql
GRANT SELECT(scheduled_at,game_type_key,away_team_record_id,home_team_record_id)
  ON public.games TO pitchlog_sync_right_fn_owner;
GRANT SELECT(tenant_id,id,name,uniform_number,team_record_id,hidden_at)
  ON public.players TO pitchlog_sync_right_fn_owner;
GRANT SELECT(tenant_id,id,name,kind,hidden_at)
  ON public.team_records TO pitchlog_sync_right_fn_owner;
GRANT UPDATE(completion_state,completion_receipt_id,public_pointer_receipt_id)
  ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;

CREATE POLICY stats_basic_players ON public.players FOR SELECT TO
  pitchlog_sync_right_fn_owner USING (
    tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
    AND session_user='pitchlog_app');
CREATE POLICY stats_basic_teams ON public.team_records FOR SELECT TO
  pitchlog_sync_right_fn_owner USING (
    tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
    AND session_user='pitchlog_app');
CREATE POLICY stats_basic_finalize ON sync_fence.stats_fact_versions FOR UPDATE TO
  pitchlog_sync_right_fn_owner USING (
    tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
    AND session_user='pitchlog_app' AND completion_state='current_open')
  WITH CHECK (
    tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
    AND session_user='pitchlog_app' AND completion_state='confirmed_ended'
    AND completion_receipt_id IS NOT NULL AND public_pointer_receipt_id IS NOT NULL);
```

`contracts/authz/product/ddl-elements.json` では上記のCOLUMN-ACL expectationの
`privilege_ids` に SELECT/UPDATE を追加し、POLICY 3件を追加する。既存の
`stats_primitives_select/insert/update` は変更しない。

## 3. repository contract / token

`contracts/tenant_boundary/repository-contract.json` の
`product_capability_ids` に `CAP:stats_basic:read`、
`product_operation_token_types` に
`pitchlog.repositories.stats_basic.ReadBasicStatsToken`、
`product_function_operation_ids` に `STATS_BASIC:read` を追加し、
`backend/src/pitchlog/repositories/repository_contract.py` を公式helperで再生成する
（`CONTRACT_REVISION`/`SOURCE_DIGEST` 追随）。本枝の`stats_basic.py`は
`FunctionOperationRegistration` の汎用型で登録しており、既存`stats_api` 5関数の
native型検証には触れていない。

## 4. route registry / capability

`contracts/authz/route-registry.json` に以下のoperation/routeを追加する。

- `game_basic_stats` `GET /games/{game_id}/stats`
- `season_basic_stats` `GET /stats/seasons/{year}`
- `game_basic_stats_csv` `GET /games/{game_id}/stats.csv`
- `season_basic_stats_csv` `GET /stats/seasons/{year}/stats.csv`

いずれも既存 `require_tenant_access`（tenant照合）だけを使い、共有グループ経由の
生記録/成績参照は追加しない。外部tenant/不存在は404、関数境界拒否は404、
その他は503へ写す。

## 5. 正本への反映

- 本枝は要件/設計/ADRを変更しない。D02/D05は既採用、D03/D04は未接続として
  `source_unavailable` を返す。D03/D04の意味判断を戻さない。
- 終了確定providerの正式TX接続は `mvp-integration-lead` の終了/再開資産で行う。
- BF/登板の27項目化は `mvp-stats-bf-calculation` とnative 27 CHECK/migrationの
  別単位。本枝のAPIはmetric JSONに `appearances`/`batters_faced` が現れれば
  自動で表示するため、27接続後に再実装しない。
