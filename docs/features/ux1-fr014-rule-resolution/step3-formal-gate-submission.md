# TSK-550 ステップ3の個別ゲート提出本文（承認前）

2026-10-14。対象はステップ3の着手条件だけ。`data-model.md` v1.0 §6-5、codec、PO採用済み5 UUID・機械文字列・F-2規則値を再審査しない。本書は正本やDDL資産そのものではなく、所有側が正式7.3と個別資産ゲートへ載せる**差分指定**である。正本の所有側受理と人間承認、資産の個別承認が済むまで製品実装・DB適用をしない。

## 1. 正本ファイルと4ゲートの射程

| ゲート | 正本・資産と確定する差分 | 所有側・残る承認 |
| --- | --- | --- |
| D：規則の出所とowner | `docs/design/data-model.md` **次版の§3-2、§10-5、変更履歴、および同書内の「6ロール」等の参照追随だけ**。§6-5は不変。§3-2は専用ownerを追加し6→7ロール、§10-5はF-2の全体既定だけを段階Aで解決し割当ありを拒否する | TSK-250所有側の採否と、この改訂だけの7.3全文レビュー・人間承認。所有者不在なら**この二節と参照追随だけ**の独立査読＋PO代替受理を別途判断してもらう。§6-5限定の先例は拡張しない |
| A：認可規範 | 正本候補を**新設 `docs/design/product-authz-surface.md`**に一意化。既存`docs/features/product-authz-surface/design.md`は実装設計であり正本にしない。新正本には段階Aの1関数、owner、READ COMMITTED/親ロック後の別文割当照会、直接権限を開かない境界、GUC残余脅威だけを定める | TSK-424認可面所有側のファイル・射程採否。新設なので7.6の新設ゲート＝7.3全文レビュー＋人間承認。所有者不在の代替受理は**この新設節だけ**別途PO判断。既存の全製品認可設計を再確定しない |
| M：配置 | F-2の5行`rule_sets`＋5行`game_type_rule_defaults`の出所付きAlembic migration、対象5組の衝突停止、一時RLS4件、適用順・失敗時全取消、物理DELETEしないdowngrade。`docs/design/data-model.md`改訂後は**物理schema差分が0でも**`contracts/db/schema-manifest.json`の正本SHAを追随させる | 移行・data-model所有側、POによる**具体的な配置データ・一時RLS・downgrade**の個別承認。固定ID/文字列の再裁定ではない |
| P：権限と凍結資産 | `contracts/authz/product/{ddl-elements.json,application-steps.json,function-bodies/**}`、独立した`backend/src/pitchlog/authz/product_role_contract.py`、列`UPDATE`の付与・撤去を扱う`backend/src/pitchlog/authz/{product_control_access.py,product_provisioning.py}`、その静的照合を行う`scripts/check_authz_catalog.py`を必須差分とする。実際に変わる`capability-catalog.json`/exposure、`contracts/tenant_boundary/{runtime-authz-contract.json,base-allowlist.json,history-snapshots/**}`を宣言。新関数をruntime契約へ加える際は生成先`backend/src/pitchlog/authz/runtime_contract.py`を必ず再生成・同期。`repository-contract.json`と固定operationはステップ4 | TSK-424/tenant境界所有側、POによる**専用owner・列UPDATE・EXECUTE/GUC残余脅威、適用/取り外し対称性**の個別承認。変更後digestと基準受理は実装後7.7で行う。未変更資産は対象に増やさない |

正式7.3の起案では対象ファイルそのものを`in-review`にして変更履歴・索引・適用7.3版/SHAを同期する。資料への予備レビューを正式7.3周回と数えない。

### Dゲートの最終本文案

`data-model.md` §3-2の見出し・ロール表・定義の所在表・本文のロール総数を6から7へそろえ、次の行を表に追加する。

> **規則解決関数所有用**（`NOLOGIN`・`BYPASSRLS`・`NOINHERIT`）: FR-014段階Aの全体既定を読む固定`SECURITY DEFINER`関数1件の所有ロール。共有・管理・認証関数の所有ロールから分離し、アプリ用ロールを含めmembershipを持たせない。表・列権限は関数が読む列と大会親行のロックに必要な列だけを個別認可資産で与え、関数本文にDMLを置かない。GUC照合をDB接続取得者に対する真正性証明とみなさない。

`data-model.md` §10-5末尾へ次を追加する。

> FR-014段階Aの新規試合に限り、付録F-2に出所を固定した5組の`game_type_rule_defaults.game_type_key → rule_sets.id`から全体既定を解決する。`rule_sets`に帰属列を足さず、固定5組以外と出所不明の既存行を段階Aの成功候補へ昇格させない。対象大会に`tenant_id`と大会キーが一致する割当行があれば全体既定へフォールバックせず拒否する。規則IDと同一規則行から読んだ5値を、§6-5の既承認JSONB形で同一成功境界へ渡す。解決失敗時は試合行を残さない。製品の規則表直接書込と大会割当書込の入口は閉じ、段階Bの大会/試合上書き解決はこの段階の成功条件に含めない。

### Aゲートの新設正本本文案

`docs/design/product-authz-surface.md`はこの段階A認可境界だけを正本として新設する。射程宣言は「本書で確定する範囲=固定制限関数1件の到達経路、ownerと最小権限、親ロック後の割当照会、アプリ直表権限の拒否、GUC残余脅威。実装時に確定する範囲=関数SQL、認可資産・適用器、カタログ/2接続/故障試験の具体」とする。本文は次のとおり。

> 認証済みの同一tenant transaction scopeから、固定`public.resolve_stage_a_rule(uuid,text,text,boolean)`だけを呼ぶ。先頭UUIDは検証済みscopeから実行器が注入する。公開requestは試合区分キー、必須大会キー、上書き有無の3項目とし、任意tenant ID・規則IDを呼出側から受けない。`pitchlog_app`の`rule_sets`・`tournament_rule_assignments`直接SELECT/書込を拒否し、`game_type_rule_defaults`の既存SELECTだけ維持する。第1引数のUUIDとtenant GUCの厳密一致を確認し、不一致なら非成功とする。大会親行をtenant GUCと照合して`FOR UPDATE`し、READ COMMITTEDの別SQL文で同一大会の割当を確認する。割当あり、候補なし、越境、無効規則、読取失敗から試合INSERTへ進まない。固定5組のID・キー・出所と同一行の値を照合し、別IDへの付け替えを拒否する。関数は専用ownerの`SECURITY DEFINER`・`VOLATILE`、`SET search_path=pg_catalog,pg_temp`、全表参照をschema修飾し、DMLを含めない。関数作成とPUBLIC EXECUTE剥奪、`pitchlog_app`だけへのEXECUTE付与は認可適用器の単一transactionに収める。GUCの存在・UUID形式・第1引数UUIDとの厳密一致・大会のtenant一致を検査するが、DB接続資格情報を得た主体が任意GUCを設定する残余脅威はこの関数では防げない。通常製品経路のtenant真正性は認証済み`TenantContext`、固定operation、接続資格情報と直SQLの遮断に依存する。残余脅威の採否をPOと認可・tenant境界所有者が明示する。

## 2. 配置migration Aの審査用DDLと値

適用前提はmigration接続が`pitchlog_owner`、Alembic headに`0029_system_vocab_category_fk`と`0030_seed_game_type`を含むこと、対象2表の`ENABLE`/`FORCE RLS`、既存の5試合区分とその`game_type_category='game_type'`、製品作成の保守停止。revision番号は着手時headに従う。`0030`の5行と本配置の5組は次のexact対応とする。

| game_type_key | rule_sets.id | R / cold / L / tiebreak / DH |
| --- | --- | --- |
| `game_official` | `ca626b2e-8751-530e-a431-9ef5c00f7d95` | 9 / [] / 12 / 10回・`no_out_first_second`・`continue_lineup` / true |
| `game_semi_official` | `8fa3b9b7-481b-538b-8093-6af96050d97f` | 9 / [(10,5),(7,7)] / 9 / null / true |
| `game_open` | `b679f9f1-86a8-54f7-9466-a5b01d932953` | 9 / [(10,5),(7,7)] / 9 / null / true |
| `game_intrasquad` | `45677369-9e25-5220-9a30-1d89b338174c` | 9 / [(10,5),(7,7)] / 9 / null / true |
| `game_other` | `6ff51660-bee2-552a-9075-1f3f3d1e0dd7` | 9 / [] / 9 / null / true |

審査するDDLの骨格（未実行）:

```sql
-- Alembic の単一 transaction。接続ロール・head・RLS・試合区分の5行を事前照合。
LOCK TABLE public.rule_sets, public.game_type_rule_defaults IN ACCESS EXCLUSIVE MODE;
CREATE POLICY tsk550_seed_rule_sets_select ON public.rule_sets
  FOR SELECT TO pitchlog_owner
  USING (id IN (
    'ca626b2e-8751-530e-a431-9ef5c00f7d95',
    '8fa3b9b7-481b-538b-8093-6af96050d97f',
    'b679f9f1-86a8-54f7-9466-a5b01d932953',
    '45677369-9e25-5220-9a30-1d89b338174c',
    '6ff51660-bee2-552a-9075-1f3f3d1e0dd7'));
CREATE POLICY tsk550_seed_rule_sets_insert ON public.rule_sets
  FOR INSERT TO pitchlog_owner
  WITH CHECK (id IN (
    'ca626b2e-8751-530e-a431-9ef5c00f7d95',
    '8fa3b9b7-481b-538b-8093-6af96050d97f',
    'b679f9f1-86a8-54f7-9466-a5b01d932953',
    '45677369-9e25-5220-9a30-1d89b338174c',
    '6ff51660-bee2-552a-9075-1f3f3d1e0dd7'));
CREATE POLICY tsk550_seed_defaults_select ON public.game_type_rule_defaults
  FOR SELECT TO pitchlog_owner
  USING (game_type_key IN ('game_official', 'game_semi_official',
    'game_open', 'game_intrasquad', 'game_other'));
CREATE POLICY tsk550_seed_defaults_insert ON public.game_type_rule_defaults
  FOR INSERT TO pitchlog_owner
  WITH CHECK (game_type_category = 'game_type'
    AND (game_type_key, rule_set_id) IN (
      ('game_official', 'ca626b2e-8751-530e-a431-9ef5c00f7d95'),
      ('game_semi_official', '8fa3b9b7-481b-538b-8093-6af96050d97f'),
      ('game_open', 'b679f9f1-86a8-54f7-9466-a5b01d932953'),
      ('game_intrasquad', '45677369-9e25-5220-9a30-1d89b338174c'),
      ('game_other', '6ff51660-bee2-552a-9075-1f3f3d1e0dd7')));
-- 上記ID/キーの既存行が1行でもあれば停止（値が同じでも流用しない）。
INSERT INTO public.rule_sets
  (id, regulation_innings, called_game_conditions,
   extra_innings_limit, tiebreak_rule, uses_dh)
VALUES
  ('ca626b2e-8751-530e-a431-9ef5c00f7d95', 9, '[]'::jsonb, 12,
   '{"startInning":10,"runnerPlacement":"no_out_first_second","leadoffRule":"continue_lineup"}'::jsonb, true),
  ('8fa3b9b7-481b-538b-8093-6af96050d97f', 9,
   '[{"pointDifference":10,"startInning":5},{"pointDifference":7,"startInning":7}]'::jsonb, 9, null, true),
  ('b679f9f1-86a8-54f7-9466-a5b01d932953', 9,
   '[{"pointDifference":10,"startInning":5},{"pointDifference":7,"startInning":7}]'::jsonb, 9, null, true),
  ('45677369-9e25-5220-9a30-1d89b338174c', 9,
   '[{"pointDifference":10,"startInning":5},{"pointDifference":7,"startInning":7}]'::jsonb, 9, null, true),
  ('6ff51660-bee2-552a-9075-1f3f3d1e0dd7', 9, '[]'::jsonb, 9, null, true);
INSERT INTO public.game_type_rule_defaults
  (game_type_key, game_type_category, rule_set_id)
VALUES
  ('game_official', 'game_type', 'ca626b2e-8751-530e-a431-9ef5c00f7d95'),
  ('game_semi_official', 'game_type', '8fa3b9b7-481b-538b-8093-6af96050d97f'),
  ('game_open', 'game_type', 'b679f9f1-86a8-54f7-9466-a5b01d932953'),
  ('game_intrasquad', 'game_type', '45677369-9e25-5220-9a30-1d89b338174c'),
  ('game_other', 'game_type', '6ff51660-bee2-552a-9075-1f3f3d1e0dd7');
-- 対象5 ID・5キーの行・値・FK・固定区分をexact検査し、対象内の余剰/不足を停止。
DROP POLICY tsk550_seed_defaults_insert ON public.game_type_rule_defaults;
DROP POLICY tsk550_seed_defaults_select ON public.game_type_rule_defaults;
DROP POLICY tsk550_seed_rule_sets_insert ON public.rule_sets;
DROP POLICY tsk550_seed_rule_sets_select ON public.rule_sets;
-- commit前にrelrowsecurity/relforcerowsecurity、policy集合、ACLを事前宣言と照合。
```

これは**審査用DDL骨格**であり、事前検査・事後カタログ照合の失敗分岐を含む実行可能migrationではない。`called_game_conditions`と`tiebreak_rule`のJSONBは既存の凍結`ruleSnapshot`と同じフィールド名を提案するが、DB行からの単一変換経路と相関検証の受理を要する。**RLSが見せる5 ID/5キー以外の既存行を「存在しない」と判定しない**。段階Aの成功対象は上表の固定5組だけで、関数内でも対応IDのallowlistと値・出所を検査する。別IDの既存行は本migrationで流用・削除せず、その扱いは段階B/別移行判断へ送る。固定キーに既存行があれば値が同じでも拒否する。追加の管理書込入口は開かない。衝突、挿入、照合、ポリシー撤去のいずれかで失敗したら同transactionをrollbackし、5+5行と一時ポリシーの追加を0に戻す。既存行を物理削除するdowngradeは設けず、逆適用要求は明示失敗として別承認の訂正・復元へ送る。

## 3. 権限差分と既存適用器B

`pitchlog_rule_resolution_fn_owner`を`NOLOGIN BYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION`、membership無し、`public`の`USAGE`のみで作る。次の表以外の表ACLは付けない。

| 表 | ownerへ付ける列権限 | `pitchlog_app`で維持する境界 |
| --- | --- | --- |
| `tenant_vocabularies` | `SELECT(tenant_id,key,category,disabled)`、親行`FOR UPDATE`に必要な`UPDATE(disabled)` | 既存ACL/RLSを維持 |
| `tournament_rule_assignments` | `SELECT(tenant_id,tournament_key)` | 直接SELECT/書込は拒否 |
| `game_type_rule_defaults` | `SELECT(game_type_key,game_type_category,rule_set_id)` | 既存`global_read_only`のSELECTのみ維持、書込拒否 |
| `rule_sets` | `SELECT(id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh)` | 直接SELECT/書込は拒否 |

1件だけの`public.resolve_stage_a_rule(uuid,text,text,boolean)`を固定`SECURITY DEFINER`、`VOLATILE`、`SET search_path=pg_catalog,pg_temp`、全表参照schema修飾、関数内DML無しで置く。ownerの`UPDATE(disabled)`は**実際の更新能力**でもあるため、NOLOGIN/membership無し、関数本文とカタログの逐行・実DB検査を必須にする。関数の作成と同transactionで`REVOKE ALL ON FUNCTION ... FROM PUBLIC`を行い、`EXECUTE`を`pitchlog_app`だけへ付ける。GUCは存在・UUID形式・第1引数UUIDとの厳密一致・親行tenant一致を検査するが、アプリDB接続を取得した主体のGUC偽装は防げない。この残余脅威を認可面・tenant境界・POで採否する。

関数は`READ COMMITTED`以外で成功しない。大会親行を`FOR UPDATE`し、待機後に**別SQL文**で同tenant・大会の割当有無を照会する。割当があれば全体既定へfallbackしない。既定のキーと規則IDは上記の5組に一致する場合だけ成功候補とし、同じ規則行の5値を単一相関検査へ渡す。別IDへの付け替えは値が妥当でも出所を証明できないため拒否する。全体既定と規則行は、製品書込入口を閉じ保守停止中の特権変更に限る間だけ通常SELECTとする。割当INSERTを開く後続段階ではロック順と2接続実測を再審査する。

**Bの唯一の適用元は既存製品認可適用器**（`contracts/authz/product/application-steps.json`の単一transaction）とする。7固定手順のうち(1)rolesでowner属性、(2)database/schemaで`public` USAGE・CREATE拒否、(3)definer functionsで本体・owner・PUBLIC剥奪・app EXECUTE、(4)table RLSと(5)policiesで既存分類維持、(6)table/column ACLで上表、(7)trigger-function ACLで既存の状態維持を宣言・照合する。関数だけのAlembic migrationを追加しない。**独立した固定ロール意味契約にownerを追加し、取り外し側は`UPDATE(disabled)`を含む全列grantを剥奪してからownerを落とす**。現行の列ACL付与・静的照合・取り外しは`SELECT`だけを扱うため、`product_control_access.py`、`check_authz_catalog.py`、`product_provisioning.py`の3経路を個別Pゲートの必須差分とし、付与・再適用・取り外し・照合の試験を含める。表現できるまでBの成功を宣言しない。

順序は **既存schema→既存authz適用状態の照合→A（F-2配置・commit）→B（認可適用器7手順・別transactionでcommit）→製品公開判定**。Aの事前検査またはtransactionが失敗したらA/B未適用・製品作成不可。A成功後、Bの**commit前**に失敗した場合はB差分を全取消しし、F-2行だけが残る。Bの**commit後**または結果不明の失敗では、関数・権限が残り得るため実DBカタログを照合して状態を確定し、未知のまま再試行や製品公開をしない。いずれも製品作成不可とし、状態確定後の安全な再適用または別承認の訂正を要する。B成功後もcatalog・7.7・2接続/越境・故障試験が不合格なら公開しない。A+Bを単一原子境界とは呼ばない。

## 4. FR-014とDRAW-04の人間裁定

要件書[FR-014](../../requirements/requirements-pitchlog-2026-07-22.md#FR-014)は「コールド適用回＞規定イニング」等を不正値とし、保存を検証エラーで拒否する。一方[付録F-1 DRAW-04](../../requirements/requirements-pitchlog-2026-07-22.md#付録F-1-規則セットのスキーマ)はDRAW-01〜03に該当しなければ有効・保存とする。`R=9, L=9, cold=[{点差:10,適用開始回:10}], tiebreak=null`はDRAW-01（L<R）でも02（点差≤0）でも03（tiebreak不正）でもないためDRAW-04では有効だが、FR-014では拒否。受理済みcodecはこの衝突を成功へ昇格させない。

**推奨裁定**: FR-014の明示拒否を維持し、付録F-1の設定時分岐に「coldの適用開始回Nが規定イニングRを超えたら保存拒否」を追加し、DRAW-04をその拒否後の残余にする。N=Rを有効とするかも例で固定する。これは要件正本の規範改訂なので**要件所有側の7.3＋人間承認が別途必要**。未裁定中は矛盾例を保存成功にしない。F-2の5値・ID・機械文字列は変えない。

## 5. 計画文言の最小追補と未承認判断

`plan.md` §3のmigration行・§4ステップ3・検査欄にある「制限読取関数migration／関数migration」は、**F-2配置AだけAlembic、関数/owner/ACLは既存認可適用器Bの単一transaction**へ読み替える追補を提案する。順序と失敗状態は上記§3を採用し、2接続・故障注入の実測はステップ3以後。計画全体の再設計、codec/ステップ2の再承認はしない。この追補の計画差分レビューと人間承認が済むまでステップ3を開始しない。

未承認は (a) data-model §3-2/§10-5と新認可正本の所有側採否または**各射程限定の代替受理**、それぞれの正式7.3、(b) FR-014/DRAW-04の要件裁定、(c) 配置migrationの一時RLS/排他/downgrade、(d) 専用owner/列UPDATE/関数EXECUTE・GUC残余脅威、(e) 実変更資産に限る7.7受理。既承認の§6-5・codec・UUID・機械文字列はここに含めない。

## 6. 共有実行器Aの実統合後に判明したB登録境界（2026-10-16、接続方針採用済み）

PR #141の統合SHAは`e7e8d3a4324687ada828b1e4b49692c087af5c44`。`backend/src/pitchlog/repositories/function_operations.py`の固定SQL再構築は、登録済み`input_fields`の前に`tenant_id: UUID`を**常に第1 bind引数として追加**する。このため本書と承認済みplanに書いた`public.resolve_stage_a_rule(text,text,boolean)`はDB実関数の引数列としては不足する。登録IDは`public.resolve_stage_a_rule`のまま、DB実identityを**`public.resolve_stage_a_rule(uuid,text,text,boolean)`**とし、呼出側の公開requestは試合区分キー・必須大会キー・上書き有無の3項目のままとする方針をPOが採用した。先頭UUIDは認証済みscopeが注入し、利用者入力には出さず、関数内部で`app.tenant_id` GUCと一致検査する。GUC偽装の残余脅威は§3のまま。計画ステップ3/4・認可正本・DDL/ACL・登録資産へ同じidentityを追随させる。ただし、これらの個別正式ゲートは未成立である。A自体の登録0件と既存DML契約は変えない。

Bの公開Python契約候補は`resolve_stage_a_rule(scope, request) -> ResolvedStageARule | StageARuleFailure`。`request`は`game_type_key: str`、`tournament_key: str`（必須）、`has_override: bool`だけを持ち、tenant IDと任意rule IDを受けない。成功は既存codecの`DomainValidatedRuleSnapshot`と、固定5組の区分キー・規則IDを同一DB読取から照合した出所証明を束ねる不変値とする。失敗literalは既受理の`stage_a_unsupported`、`rule_not_available`、`invalid_rule`、`outcome_unconfirmed`の4件から増やさない。DB戻りはA実行器の行数・列数・exact型検査に収まる固定1行/1列のJSONB envelope候補とする。Aの`_materialize_rows`はDBの`dict`を再帰的に`MappingProxyType`へ変換してから登録decoderへ渡すため、`result_fields`は`dict`ではなく`MappingProxyType`を宣言し、decoderで状態・exact key・型を検査する。既存codecの`decode_structure`はexact `dict`を要求するので、検査後に業務値だけを新しい通常の`dict`へ再構成して**唯一の既存codec**へ渡す。`dict`型の登録宣言や未検証MappingProxyTypeの直接codec投入はAの実経路で失敗する。失敗行から規則値や他tenantの有無を外へ出さない。戻りenvelopeの正確なkey/SQL型と例外・4 literalへの写像は、認可面の関数本体とU-G1消費側の同時採否対象であり、現時点で製品契約として確定しない。

U-G1の同一scope境界は、`run_function`→固定5組と出所/codec検証→`games.applied_rules`へ承認済み6-keyをINSERT→RG1コミット直前ゲート→commitである。失敗・例外・タイムアウト時は例外退出してgame行と関連書込を全取消し、旧`{}`を補完しない。出所証明がない場合、固定キーの別IDへの付け替え、割当あり、親大会不在/無効/別tenant、コールド未裁定例は非成功とする。保存用JSONBは`DomainValidatedRuleSnapshot`から既存`encode_applied_rules`だけで生成する。U-G1のHTTP外形、初期RG1実operationと全ロック順はTSK-395側の実装/受理へ残す。

実装後の専用隔離PostgreSQL試験では、(1)固定5組の正例と出所不明・別ID・欠損・無効値、(2)同tenant割当あり拒否と別tenant割当の非漏洩、(3)親ロック取得待機後の別SQL文による割当再読取、(4)親INSERT/無効化との2接続競合、(5)既定/規則行の特権変更競合とロック保持期間、(6)関数読取後・game INSERT後・RG1直前の故障注入と全取消、(7)GUC欠損/不正・注入UUIDとの不一致・大会tenant不一致と直接EXECUTE、(8)READ COMMITTED以外の拒否、(9)appの2規則表直接SELECT/書込拒否と既定表SELECT維持、(10)関数ACL/owner/SEARCH_PATH/PUBLIC剥奪を実DBで確認する。このうち(1)〜(5)、(7)〜(10)と関数単体の読取後故障はTSK-550ステップ3〜6、game INSERT後/RG1直前の全取消と実HTTP外形はTSK-395ステップ2の担当証跡とする。製品関数とU-G1接続の実装前に生SQL probeを製品証跡へ代用しない。

最新developのA統合済み凍結基線は、`repository-contract.json` revision **19**、`base-allowlist.json` revision **31**、`runtime-authz-contract.json` revision **16**、製品`PRODUCT_FUNCTION_OPERATIONS=()`である。Bの具体差分・after digestはこの基線とU-R1/C1の先行統合結果を照合してから再導出し、旧提案のrevision候補を流用しない。C1/U-R1との調整で共有資産の先行PRが変われば、先に統合した履歴を保持しBは追加集合だけを個別7.7受理する。

## 7. ステップ3着手の一括承認資料（2026-10-16）

この節と§1〜6を**単一の判断対象**とする。既承認の§6-5、codec、固定5 UUID・2機械文字列・F-2の5値、Aの製品登録0件、DB関数4引数と公開request 3項目、decoderの不変`Mapping`検証と単一codec利用を再判断しない。§1のD/A/M/P、§2の配置DDL骨格、§3の権限表・適用順、§4の矛盾例、§5の最小計画追補が具体差分である。現行`docs/design/product-authz-surface.md`の3引数表記は**未承認の正本候補に残る未反映差分**であり、正式7.3追加審査と承認時に4引数へ訂正する。候補に残る3引数をDB実関数として実装しない。

| 判断単位 | 既済み審査・採否 | 人間に求める決定 | 承認後の実装範囲 |
| --- | --- | --- | --- |
| D: `data-model.md` v1.1 §3-2/§10-5・参照追随 | 正式7.3第1回P1=2/P2=1を全採用、第2回P0/P1/P2=0。§6-5はapprovedのまま | TSK-250所有側の採否と、7.6による版改訂の人間承認。所有者不在なら**この二節だけ**の独立査読＋PO代替受理を個別判断 | 固定5組の出所を正本に固定し、schema manifestの正本SHAを実値で追随 |
| A: 新設`product-authz-surface.md` v0.1 | 正式7.3第1回P0=2/P1=2を全採用、第2回P0/P1/P2=0。ただしA統合後の3→4引数はレビュー後差分 | TSK-424所有側の採否、4引数訂正と影響節に限定する追加7.3レビュー枠の6.3/7.3裁定、収束後の新設正本の人間承認。所有者不在の代替受理は本正本だけ別裁定 | scope UUID注入・GUC照合・親ロック後別SQL文・直接権限遮断を正本へ固定 |
| M: F-2配置migration | DDL骨格への予備査読第1回P0=1/P1=4を採用、第2回P0=1/P1=2を採用。正式資産審査は未了 | 移行所有側とPOが、5+5行の出所、固定ID/キー衝突時停止、`pitchlog_owner`向け一時RLS4件と撤去、`ACCESS EXCLUSIVE`、rollback、非DELETE downgrade、適用revision順を**実行可能差分**で個別承認 | 承認後に配置Alembicだけ作成し、隔離DBで全取消・事後ACL/RLS照合 |
| P: owner・ACL・認可適用器・凍結資産 | §1/§3に対象ファイルと7手順、付与/再適用/撤去を指定。予備査読P0/P1を採用したが、資産の最終差分と実digestは未承認 | TSK-424/tenant境界所有側とPOが、`NOLOGIN NOSUPERUSER BYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION`の専用owner、親列`UPDATE(disabled)`の実更新能力、最小SELECT、PUBLIC剥奪・appのみEXECUTE、GUC偽装残余脅威、既存適用器の付与/照合/撤去を個別承認。7.7は実変更後の完全before/afterと履歴で別受理 | 承認後に関数本体・owner/ACLを**認可適用器の単一transaction**へ追加。関数Alembicは作らず、B登録1件はステップ4の別ゲート |
| 計画・要件 | §5の「配置だけAlembic、関数は既存認可適用器」追補案。FR-014/DRAW-04の反例は§4 | 計画差分の必要レビューと人間承認。要件所有側はFR-014の拒否を優先する§4推奨裁定を正式7.3・人間承認で判断 | F-2の値は維持。矛盾例を有効として保存しない |

**編集・統合順**: 現在U-R1作業木が`product_control_access.py`、`product_role_contract.py`、`runtime_contract.py`、`repository_contract.py`、`schema-manifest.json`、`base-allowlist.json`等を編集中である。これらをTSK-550から上書きしない。共有資産はA実統合→**先に個別ゲートとレビューを通し統合されたBまたはC**→後続側がその受理履歴・revisionを保持して追加集合/digestを再導出する順とする。現状の編集占有はU-R1 Cにあり、同時編集を避けるためCの共有資産編集・候補確定を先行扱いとするが、Cの正式統合が遅れる場合でもB/Cの機能上の相互待ちは作らず、U-R1の所有解除確認後にBが同じ基線から編集する。U-C1はTSK-401で編集予定の回答待ち。重複ファイルが出た場合は先行統合側の承認済み履歴を後続側が維持する。担当からの順序受理は未確認であり、双方にこの具体順を照会する。

**実装後の証跡**: §6の縮小SQL probeは補助資料のみ。ステップ3〜6で実製品関数・認可・RLS・全5区分・2接続・故障注入を隔離DBで検証する。TSK-395ステップ2が同一scopeの`applied_rules`保存、RG1直前ゲート、実HTTP、失敗時全取消を担う。旧行補完、割当ありの既定fallback、出所不明の成功は許さない。上表の人間判断と個別ゲートが成立するまで製品登録・DB関数・migrationを実装しない。

**限定追加独立レビューの採否（対象`d2de0c3b`、1回のみ）**: 4引数訂正と影響節だけを候補作成に不関与の査読者が確認。P0=0/P1=1/P2=1。P1=認可正本§1/§4と変更履歴にUUID注入・GUC厳密一致拒否が欠落、P2=試験表に注入UUID≠GUCの負例が欠落。**両件採用**し、認可正本候補と本書§1/§3/§6へ追随した。A実装の第1UUID bind、scope検証・GUC設定、不変`Mapping`化と既存codecのexact `dict`要求はレビューで整合を確認。修正後の差分は担当が限定自己照合し、既済み7.3全文レビューを再実施しない。正本は`in-review`であり、人間確定を代記しない。

## 8. 人間判断の最終提出面（限定レビュー反映後）

基線`origin/develop=e7e8d3a4`（2026-10-16にremoteを再照合）。**承認対象は次の未確定差分だけ**。固定5 UUID、F-2の5値・2機械文字列、§6-5の6-key保存形、Aのscope注入・不変`Mapping`接続方針は承認済みであり、今回の判断から外す。正本候補・資産候補の`in-review`を人間確認前に`approved`としない。

### 8-1. 正本の全文と変更履歴

| 正本候補 | 人間が承認する実ファイルと本文 | 変更履歴・レビュー・追加判断 |
| --- | --- | --- |
| `docs/design/data-model.md` v1.1 | 現ファイルの変更履歴v1.1行、§3-2の7ロール表と参照追随、§10-5末尾の「FR-014段階Aの新規試合作成に限る出所証明」の**現全文**。`git diff origin/develop -- docs/design/data-model.md`にあるv1.0 §6-5は既承認の保持分であり今回の判断対象外 | v1.1の変更履歴は2026-10-15、`in-review`。正式7.3は2周で収束（第1回P1 2/P2 1を全採用、第2回0）。TSK-250所有側の採否と7.6人間承認。所有者不在の代替受理は§3-2/§10-5と参照追随だけ別判断 |
| `docs/design/product-authz-surface.md` v0.1 | 現ファイルの**全文45行相当**（変更履歴、射程、§1〜4）。§1の関数identityは`public.resolve_stage_a_rule(uuid,text,text,boolean)`、第1UUIDは検証済みscope注入、公開requestは3項目。§4は第1UUIDと`app.tenant_id`の厳密一致・不一致非成功、GUC偽装の残余脅威を明示。修正後の現ファイルを承認本文とし、旧3引数の履歴案は採らない | v0.1の変更履歴は2026-10-15起案と2026-10-16限定追加レビュー反映を同じ行に記録し、状態`in-review`。正式7.3基本2周は初回P0 2/P1 2を全採用して第2回0。PO許可の**限定追加独立レビュー1回**はP0 0/P1 1/P2 1を全採用。修正後差分と最終全文の人間確認、TSK-424所有側の採否と7.6新設正本承認が必要。所有者不在の代替受理は本正本だけ別判断 |

承認時は両ファイルの最終本文・変更履歴と`docs/README.md`の版/状態を照合し、確定した実SHAで`contracts/db/schema-manifest.json`を追随させる。`data-model.md`の既承認v1.0やdevelopの他節を書き戻さない。

### 8-2. 配置・権限・適用順の個別判断

| 対象と推奨案 | 拒否条件・失敗時状態 | 既存環境への影響と承認後の範囲 |
| --- | --- | --- |
| **配置A**: `backend/migrations/versions/<適用時headの後続>.py`だけにF-2の`rule_sets`5行と`game_type_rule_defaults`5行を置く。§2のUUID・値・INSERT・4一時policyをexact資産候補とし、既存`pitchlog_owner`だけへ一時RLSを与える。`ACCESS EXCLUSIVE`の保持中に固定5 ID/キーの衝突を全数検査し、INSERT後に5組の値/FK/ACL/RLSを照合、同transactionのcommit前に4 policyを撤去。revision番号は先行統合の実Alembic headから割り当てる | 既存対象ID/キーが1行でもあれば値が一致しても停止。前提role/head/5区分/FORCE RLS/事後照合の不一致も停止。commit前の失敗は全取消、追加行と一時policyは0。downgradeで規則行を物理DELETEせず明示停止。取消不能な既存行の扱いは別承認 | 既存行は更新・削除しない。対象2表の排他ロックと作成保守停止が必要。Aだけ成功しても試合作成は非公開。移行所有側とPOが**この10行・4一時policy・停止/取消方式を候補実装範囲として承認**した後にmigration候補を実装・隔離DB検証する。実ファイルの正式変更・既存DB適用・7.7受理は候補差分提示後の別ゲート |
| **権限B**: `pitchlog_rule_resolution_fn_owner`を7属性固定、NOLOGIN・membershipなし・`public USAGE`だけとする。§3表の4表に列SELECT、親`tenant_vocabularies`に限り`UPDATE(disabled)`を付与。固定関数1件を既存認可適用器の7手順・単一transactionで作成し、同transactionでPUBLICのEXECUTEを剥奪して`pitchlog_app`だけへ付与。列grantの付与・静的照合・取り外しを対称にする | owner属性/関数本文/関数identity/ACL/戻りcontractの不一致、PUBLIC付与残り、直接表権限の拡張、列UPDATE取り外し漏れは拒否。Bのcommit前失敗はB全取消・A配置行のみ残る。commit後失敗または結果不明は実DBカタログで状態を確定するまで再試行・製品公開を拒否 | appの既存`game_type_rule_defaults` SELECTを維持。`rule_sets`と`tournament_rule_assignments`のapp直接SELECT/書込は開かない。ownerの`UPDATE(disabled)`は実UPDATE能力なので、そのリスクの明示承認が必要。DB接続を奪った主体のGUC偽装は防げず、**残余脅威は未受理**。TSK-424・tenant境界所有側/POがこのowner属性・列grant・ACL境界を候補実装範囲として個別承認した後に関数・権限候補とカタログ試験を実装する。正式資産反映・既存DB適用は実差分の個別ゲート後 |
| **資産と順序**: 対象は`contracts/authz/product/{ddl-elements.json,application-steps.json,function-bodies/**,capability-catalog.json,exposure-facts.json}`、`backend/src/pitchlog/authz/{product_role_contract.py,product_control_access.py,product_provisioning.py,runtime_contract.py}`、`scripts/check_authz_catalog.py`、変更が生じる`contracts/tenant_boundary/{runtime-authz-contract.json,base-allowlist.json,history-snapshots/**}`とschema manifest。`repository-contract.json`と固定operation登録はステップ4の別ゲート。既存schema/認可状態照合→配置A commit→認可B commit→カタログ/7.7/実DB試験→公開判定 | 先行段階の失敗は後続を実行しない。A成功・B失敗ではF-2行だけ残り作成不可。B commit後に検査不合格なら作成不可のまま、カタログを照合して安全な再適用/別承認の訂正を選ぶ。A+Bを単一transactionと呼ばない | 変更した凍結資産だけ実before/after・snapshot・corpusを実装後に再導出し7.7個別受理。旧受理履歴は保持。関数だけのAlembic migrationは作らず、計画の「関数migration」表記は§5の最小追補で訂正する |

**ステップ3着手の推奨判断**: D/A両正本の所有側採否と7.6人間確定、配置Aの一時RLS/排他/停止・復旧方式の候補実装範囲承認、権限Bのowner/列UPDATE/EXECUTEの候補実装範囲承認とGUC残余脅威の明示採否、§5計画追補の必要レビュー・人間承認を一括で行う。GUCについての推奨は、通常製品経路の認証済みTenantContext・接続資格情報隔離・直SQL遮断を成立条件とし、DB資格情報を得た主体による偽装は残余脅威としてPOと認可/tenant境界所有者が明示受容する案である。受容されない場合は製品公開を停止して資格情報境界の別設計へ戻す。**現時点では受容済みではない**。B固定operation登録とrepository-contractはステップ4のゲートに残す。実装後でなければ出ない7.7のafter digest、実製品RLS・権限・全5区分・2接続/故障注入はステップ3〜6の検証と受理へ残し、着手前の循環条件にしない。

### 8-3. FR-014／DRAW-04の裁定

衝突する正本文言は、FR-014受入基準の「**不正な規則値（コールド適用回＞規定イニング等の矛盾）**」は保存時に「**検証エラーで保存できない**」、付録F-1 `DRAW-04`の「`DRAW-01`〜`DRAW-03`のいずれにも該当しない設定は**有効**とし、保存して実行時判定に用いる」である。例`R=9,L=9,cold=[{点差:10,適用開始回:10}],tiebreak=null`は前者で拒否、後者では`DRAW-04`で有効となる。F-2の既定値はこの反例に該当せず、変更しない。

| 選択肢 | 利用者の挙動と影響 | 推奨 |
| --- | --- | --- |
| A: FR-014の明示拒否を維持し、付録F-1の設定時判定に`N>R`の拒否を追加してから`DRAW-04`を残余とする | 例の規則は保存時に検証エラー。`N=R`は「超える」ではないため有効。既存F-2値と単一codecの拒否を維持し、矛盾設定を保存成功へ進めない。要件正本の7.3・人間承認が必要 | **推奨** |
| B: `DRAW-04`を優先し、FR-014の拒否条件を狭める | 例の規則を保存でき、規定回を超えるコールド開始が製品に残る。FR-014の受入基準・相関検証・既存codecの変更を伴うため段階Aの既承認範囲を超える | 不採用案 |

裁定前に矛盾例を保存成功扱いにしない。要件改訂の正式承認は規則データの値変更や未承認GUC残余脅威の受容を意味しない。

### 8-4. 共有資産の宛先別中継文

TSK-392（U-R1）とTSK-401（U-C1）に直接Notionコメントを送付済みだが、**担当からの採否は未確認**。編集順を確定するため、人間が中継する場合の短文を以下に固定する。

- **U-R1担当宛**: 「TSK-550 Bは、U-R1が現に編集中の認可適用器・repository-contract・tenant-boundary資産を上書きしません。Cの共有資産候補確定を先行編集とし、先に統合した側の受理履歴・revisionを後続が保持して差分だけ再導出します。Cの統合が遅れる場合、所有解除できるファイルと時点を指定してください。`7aea7b44`の採否、重複ファイル、見込みPR順を回答してください。B/Cに機能上の相互待ちは追加しません。」
- **U-C1担当宛**: 「TSK-550 Bが今後編集候補とする共有箇所は認可適用器・repository-contract・tenant-boundary資産です。U-C1が同じファイルを編集するなら対象パスと見込みPR順を回答してください。先に統合した受理履歴・revisionを後続が保持し、追加分だけ再導出します。U-C1所有の製品機能には触れません。」
