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

## 9. ステップ3候補の実測・独立レビューと残る判断（2026-10-16）

本節は初回候補とその独立レビューの履歴である。後続の候補修正・比較実測・最終推奨は§10に記す。初回SHAを後続SHAへ遡及して書き換えない。

POは提出HEAD `830d3b62` の§8に限り、**候補作成と隔離DB試験・独立レビュー**を承認した。正式正本・認可資産・凍結履歴・既存DBへの適用、push/PR/マージは未承認のまま。候補は正式Alembic `versions` に登録せず、`backend/migrations/candidates/tsk550_stage_a_rule_defaults.py`（F-2配置A）と `tsk550_resolve_stage_a_rule.sql`（認可適用器へ載せる関数本体案）に隔離した。関数・owner・ACLは試験内でのみ付与し、製品認可適用器と製品operationには未登録。C1→U-R1→Bの共有ファイル編集順について両担当へ照会済みで、所有解除・順序受理は未確認。

| 候補・証跡 | 結果と限界 |
| --- | --- |
| 配置A | 固定5組を一transactionで挿入。既存ID/キーは同値でも停止、既存行は更新・削除しない。一時RLS 4件を同transaction内で撤去し、owner・RLS・表/列ACL・policyの前後一致を検査。`downgrade`は物理削除せず停止 |
| 関数SQL候補 | 4引数、scope UUID/GUC照合、READ COMMITTED、親`FOR UPDATE`後の別SQL割当照会、割当あり/override/出所不明/不正F-2値の拒否。戻りの6-keyは**出所候補**であり、既存codecの構造・相関検証を通すまでは保存可能snapshotでも成功でもない |
| 隔離PostgreSQL | `backend/tests/db/test_stage_a_rule_candidates.py` 6件合格。5区分、固定ID/キー衝突、挿入故障全取消、A commit後のB認可故障（配置10行は残りowner/関数無し・公開不可）、appの2表直読取拒否、GUC欠損/不一致、override、大会割当ありを確認。既存fixtureは`head→認可適用→候補A`のため、正式revisionを含むfresh bootstrapや2接続の競合は未実証 |
| 品質 | backend Ruff format/check、ty check、限定pytest 6件は合格。候補3ファイルのSHA-256は順に配置 `899dabbc6a02d3304ff81bcf4f397aab56f309fdaf177455f91c134f07b05bc3`、SQL `39b43aea013e1e0b5b827a00a2d6739ac7021ee800e5c22a9e9fa4c3f4d0d244`、試験 `8bb2f627ea96afa8c08602387ee974be295af5e707ea3fa0f9c1efce56f628bd`。全件・基線・7.7正式検査は未実施 |

**候補3ファイルの独立・限定敵対レビュー**: 上記SHAに対しP0=0、P1=2（未解消）、P2=1。事後のACL比較・既存キー衝突・GUC欠損・直表ACL負例は承認範囲内で問題なし。P1は以下、P2は後続の2接続/故障分類実測で管理する。既済みの正本7.3レビューや別の独立レビューをこの候補レビューへ読み替えない。

**P1 2件（候補の正式化前に解消）**:

1. 旧受理シート`step1-contract-acceptance.md`の「既定行→規則行を`FOR SHARE`しcommitまで保持」と、新認可正本候補§3・本書§3の「製品書込入口を閉じた間は通常SELECT」が実質不一致。`FOR SHARE`には対象表のUPDATE権限が必要だが、PO提示のowner最小権限は既定/規則にSELECTのみ。追加grantは今回の承認外。**推奨**: 段階Aを閉鎖モデル（製品管理書込0件、特権変更は保守停止）として旧シートの該当1行だけを明示追補し、通常SELECTの適用期間・将来書込時の再審査条件を正本所有側に受理してもらう。閉鎖保証が受理されないなら、行ロック案と必要な列UPDATE・RLS/ACL・2接続検査の個別人間承認を求める。候補に無断でgrantを足さない。
2. 新規DBの既存bootstrapは`backend/tests/db_fixtures.py`でAlembic `head`後に製品認可を適用する。候補AはownerのFORCE RLSを前提とするため、そのまま正式`versions`のheadへ登録すると新規DBのmigrationで停止する。**推奨**: 既存schema revision到達→既存認可適用/カタログ照合→A配置revision→B認可再適用/照合の段階起動を明示し、fresh cluster・既存認可済みDBの両方を実試験する。現在の未登録候補を正式headへ移す前に、適用入口・fixture・運用手順の対象差分と所有者受理を固定する。A失敗時は全取消、A成功/B失敗時はA行を残し公開不可、B結果不明時はカタログ照合まで再試行・公開を止める。

**その他の正式化前検査**: 親ロック待機後の割当再読取と2接続、既定/規則の同時管理更新（入口を開くなら必須）、GUCの不正UUID、appの全3表の直書込拒否、fresh bootstrap、製品認可適用器でのowner grant/撤去・PUBLIC/EXECUTE・7.7、固定operationと同一scope保存は未完了。SQL候補の手動付与試験を実製品認可経路の成功へ読み替えない。FR-014/DRAW-04は§4/§8-3の推奨A、GUC偽装の残余脅威は§3/§8-2の明示採否を維持し、いずれも未承認。正式正本D/Aの最終本文は§1と実ファイルの`in-review`本文に固定し、所有側の採否は未取得。候補段階のP1が残るため、ステップ3完了・7.7実値受理・試合作成成功を主張しない。

## 10. P1二件の比較実測と最終判断案（2026-10-16）

§9は初回レビュー時点の提案を保存する履歴である。**現在の推奨は本§10が優先**する。特に§8-2の既定/規則行を通常SELECTにする旧権限表と、§9の閉鎖書込モデル推奨は採らず、§10-1の既受理`FOR SHARE`維持案を正式判断へ出す。正式正本・ACLへはまだ反映していない。

### 10-1. 規則・既定行のロック契約

現行の製品認可資産では`pitchlog_app`に`game_type_rule_defaults`のSELECTだけがあり、`rule_sets`と`tournament_rule_assignments`の直接SELECT/書込権限はない。規則・既定の製品管理書込関数も未登録。通常の書込主体になり得るのは表ownerの`pitchlog_owner`、権限を持つ外部適用主体・superuser、および将来個別承認される管理関数である。`BYPASSRLS`属性だけでは表DML権限にならない。今回の関数owner候補は`NOLOGIN`・membership無し・固定関数本文DML無しとするが、列UPDATEを付ければそのロールには実際の書込能力が生じる。

| 案 | 同時変更排除の必要条件 | 権限・残余と採否 |
| --- | --- | --- |
| 閉鎖書込＋通常SELECT | 製品作成の新規流入を止め、既存の全tenant transaction scopeをcommit/rollbackまで排出する。運用担当がscope残数0を確認した後、特権migrationが**既定表→規則表**の順で`ACCESS EXCLUSIVE`を取得し、対象行照合・変更・commitまで保持。取得待ち・timeout・不明状態では変更せず公開停止を維持。通常SELECTはtransaction終了まで`ACCESS SHARE`を保持するため、正規の排他migrationは進行中読取を越えられない | 列UPDATE追加なし。ただし任意の特権DMLは`ACCESS SHARE`と競合しない。superuserや表ownerがこの停止・表ロック手順を迂回した場合はDBだけでは排除できない。運用手順・実行主体・監査の正式受理が不可欠。今回の候補比較では**推奨しない** |
| 既受理の`FOR SHARE`維持 | 親行`FOR UPDATE`→別文割当判定→既定行`FOR SHARE`→規則行`FOR SHARE`を単一scopeで取り、commit/rollbackまで保持。管理書込は同じ既定→規則順、特権migrationは製品停止と既定表→規則表`ACCESS EXCLUSIVE`で進行中scopeを排出する | [PostgreSQL SELECT仕様](https://www.postgresql.org/docs/17/sql-select.html)により各表で少なくとも1列のUPDATE権限が必要。候補最小列は既定`game_type_category`、規則`id`。前者は`CHECK (='game_type')`、後者の固定5行には既定表からFKがあるが、**列grantは実DML能力**であり、他行や自己更新の危険は残る。NOLOGIN・membership無し、固定関数DML禁止、app直接DML不付与、カタログ照合/撤去対称性を同時に個別受理する。**推奨** |

隔離PostgreSQLの2接続実測: 通常SELECTを開いたまま特権接続が規則行をUPDATEできた。一方、候補関数の`FOR SHARE`取得後は同じUPDATEが`lock_timeout`で停止し、特権接続の`ACCESS EXCLUSIVE`も待機した。解決transaction終了後は表排他取得・更新が可能になり、変更後のF-2不一致は`invalid_rule`として拒否された。最小列UPDATE grantを取り消すと2表の`FOR SHARE`は権限エラーになり、上記列だけを再付与すると実行できた。同時に既定表の自己UPDATEも実行でき、grantを無害なロック専用権限とは扱えない。[PostgreSQLロック表](https://www.postgresql.org/docs/17/explicit-locking.html)は通常SELECTの`ACCESS SHARE`と通常UPDATEの`ROW EXCLUSIVE`が競合せず、`ACCESS EXCLUSIVE`だけが通常SELECTを止めることを示す。

**推奨する最終契約の正本文差分（未承認）**: `docs/design/product-authz-surface.md` §2の既定・規則のowner権限行に、それぞれ`UPDATE(game_type_category)`・`UPDATE(id)`を明記し、実DML能力とNOLOGIN/非membership/固定関数DML禁止/再適用・撤去/カタログ照合を一体の条件にする。§3の「通常SELECT」と閉鎖モデルの一文を、上記`FOR SHARE`順・commit/rollbackまで保持へ置換する。親ロック待機後の割当別文照会と固定5組の出所/相関拒否は維持する。`docs/design/data-model.md` §3-2のowner説明は2表の最小列grantへ、§10-5は同一scopeの保持ロックへ追随する。旧`step1-contract-acceptance.md:211`の既受理`FOR SHARE`を維持し、同シートの受理済み事項を一括差し戻ししない。関数SQL候補だけに`FOR SHARE`を反映し、正式認可資産と正本はまだ変更していない。列grantは個別認可/7.7ゲートの人間承認を要する。

正本所有側へ提出する**置換本文**は次に固定する（実ファイルへは未反映）。`product-authz-surface.md` §2の表の2行は「`game_type_rule_defaults`: `SELECT(game_type_key,game_type_category,rule_set_id)`と行`FOR SHARE`のための`UPDATE(game_type_category)`」「`rule_sets`: `SELECT(id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh)`と行`FOR SHARE`のための`UPDATE(id)`」。表の後に「この2列のUPDATEはロック専用権限ではなく実DML能力である。ownerはNOLOGIN・非membership、関数本文はDML禁止、appへは直接UPDATEを与えず、grantの付与・再適用・撤去と関数本体のカタログ照合を同じ個別ゲートで検証する。」を追加する。§3の通常SELECT段落は次の本文へ置換する。

> 段階AのresolverはREAD COMMITTEDの同一transaction scopeで、大会親行をFOR UPDATEし、待機後に別SQL文で割当を判定し、区分既定行をFOR SHARE、対応する規則行をFOR SHAREで取得する。各行ロックは試合作成・RG1ゲートを含むscopeのcommitまたはrollbackまで保持する。規則・既定への製品管理書込入口は段階Aでは閉じ、後に開く場合は親→割当→既定→規則の取得順と2接続の競合試験を個別受理する。特権migrationは試合作成の流入停止と進行中scopeの排出後、既定表→規則表の順でACCESS EXCLUSIVEを取得し、commitまで保持する。待機timeoutまたは結果不明なら変更と試合作成公開を停止する。

`data-model.md` §3-2のowner行末には「親行の`UPDATE(disabled)`に加え、既定行`FOR SHARE`用の`UPDATE(game_type_category)`、規則行`FOR SHARE`用の`UPDATE(id)`を列単位で付ける。いずれも実DML能力であり、固定関数本文のDML禁止とowner隔離を必要条件とする」を追記する。§10-5の「同一成功境界へ渡す」文の後に「対象の既定行と規則行は同一scopeで`FOR SHARE`し、試合保存とRG1のcommit/rollbackまで保持する」を追記する。変更履歴には「TSK-550段階Aの既受理ロック契約を、必要最小列grantと特権migration停止手順を含めて明文化」と記し、旧§6-5・5 UUID・F-2値は変更しない。

### 10-2. 新規DBからの段階起動と再実行

候補の適用列は **S0: 既存schema head `0031_intent_selectors` → S1: 現行製品認可適用・カタログ照合 → S2: 配置AのAlembic revision・commit → S3: 関数/owner/ACLの認可B・commit → S4: カタログ/7.7/実経路検査が揃ってから試合作成公開**。AとBは別transaction。各段階を進める前に試合作成の流入を止め、進行中scopeを終了させる。S4以前の`create_app()`成功やHTTP疎通を試合作成可能の証拠にしない。

| 隔離DBで実行した状態 | 観測した停止/再実行結果 | 正式化時に残る証明 |
| --- | --- | --- |
| 完全な空DB→現行Alembic head（認可前） | FORCE RLSが無くA候補は停止。規則・既定追加行0 | 現行`head→認可`をそのまま新A revision付き`head`へ適用すると失敗する。S0で明示revision停止する起動器が必要 |
| S1認可後、Aの既定INSERTへ故障注入 | Aは全取消。追加行0・一時policy0。故障trigger撤去後、同じ候補を再実行して固定5+5行をcommitできた | 実revisionでAlembic versionが失敗時に進まず、成功時に同transactionで進むことを試験 |
| A commit後にAを直接再実行 | 固定キー衝突で停止し、5+5行を維持。**候補は意図的に非冪等** | 通常再起動はAlembic version照合でAをskipし、実行済みを値・policy/ACL/ownerで確認する。version欠損なのに5+5行があれば自動再stamp/上書きせず、人間調査へ停止 |
| A commit後、B transactionを故障注入 | Aの5+5行を保持し、候補owner/関数は0。現行認可適用器の再実行は既存基線を保持したが、候補Bは未登録なのでBの再試行成功は未実証 | Bの正式資産化後、失敗点全取消・再実行・commit結果不明時のカタログ照合を検証。公開は不可のまま |
| 既存認可済みDBへの追随 | 対象外の既存`rule_sets`行を保持してAの5+5組を追加。固定ID/キー衝突は同値でも全停止 | 既存DBのrevision・認可・出所/衝突を事前照合し、保守停止/進行中scope排出を運用で確認 |

現行の`backend/tests/db_fixtures.py`は`alembic head→認可適用`、`.github/workflows/ci.yml`のmigration jobも`alembic upgrade head`を直接実行し、同jobの接続は候補Aが要求する`pitchlog_owner`ではない。この順・主体を**今回変更しない**。正式A revisionを登録する前に、最小の起動器（S0の明示revision・S1認可・S2 Aをowner接続・S3 Bを認可適用主体・S4公開判定で順に実行し各段階をカタログ照合する閉じた入口）、当該DB fixture、CIのhead/migration検査と接続主体、`docs/ops/deployment.md`の手順・停止/復旧表を変更対象として所有側へ提示する。別のfixtureで`head`を直接呼ぶ箇所も影響調査し、正式revision化後の全件試験で漏れをなくす。起動器の正式仕様・権限・CI変更は別ゲートで承認し、候補試験だけで既存の起動契約を置き換えない。

### 10-3. P2と残る人間判断

初回独立レビューのP2は、実関数の**親ロック待機後の割当再読取、既定/規則の同時管理書込、故障分類を2接続で完走していないこと**。**採用**し、親/割当の両順序・rollback・timeout、将来の管理書込入口を有効化する場合の同時更新をステップ3〜6の実経路試験表へ残す。今回の2接続は既定/規則の読取対特権更新に限定し、P2全体を完了扱いにしない。

人間判断は、(1)§10-1の`FOR SHARE`最小列grantと正本D/Aの限定本文・所有側採否、(2)§10-2の段階起動器/CI/運用文書の具体変更範囲、(3)§4・§8-3のFR-014/DRAW-04推奨A、(4)§3・§8-2のGUC偽装残余脅威の採否、(5)配置・認可・schema/tenant境界資産の個別ゲートと実装後7.7。既承認の5 UUID、F-2値、6-key保存形、A固定実行器、codecは再判断しない。正本D/Aは`in-review`のまま、所有側採否は未取得。C1→U-R1→Bの共有資産編集枠も担当回答待ち。正式資産登録・既存DB適用・未受理履歴・push/PR/マージは行わない。

**必要な計画の最小追補案（未承認）**: `plan.md` §4ステップ3の着手前条件へ、(a)上記FOR SHARE列grant/owner権限の個別承認と正本D/Aの確定、(b)S0〜S4の起動入口・適用主体・CI/fixture/運用手順の所有側受理、(c)FR-014/DRAW-04の未裁定値の保存前拒否とGUC残余脅威の明示採否、を追加する。合格条件へ、空DB/既存DB両経路の実revision・失敗時version据置・A後B失敗/再試行・catalog公開判定、2接続のFOR SHARE/特権変更、7.7正式受理を追加する。候補だけの隔離試験をステップ3完了と読まない。ステップ4以後の固定operation/保存・TSK-395結合試験の責任は移さない。§3の「関数migration」は既承認の配置Alembic/認可適用器Bへ訂正するだけで、新たな関数migrationは作らない。この追補は計画差分として必要なレビューと人間承認へ出し、今回の候補許可を正式変更承認に読み替えない。

**最終候補の限定独立レビュー**: レビュー前の識別値は配置 `631e253ebaa69fb93449780e0d43ab14e069b4dffa2f02881919af08ff7f8974`、関数SQL `6cbdd887cc46e537604a9aeeb707e4f3e6ca0c7f8b9a9a6d178329303a0968aa`、試験 `744eb36caffee990b6510281c1f6c02620ccb4d263dfff6d2d953f473674ee9c`、本資料 `7ce1563fe39122d3a3f46b908430fc3a20a02e8156f68ddc70e7880b720ac450`。候補作成に関与しない担当がこの4値の差分を読み取り専用で確認し、**新規P0=0/P1=0/P2=0**。初回P1①は技術案と2接続比較、P1②は段階起動の候補試験で整理されたが、列grant・正本・7.7、実Alembic revision・起動器/CI/運用文書が未確定のため、いずれも正式解消とはしない。初回P2は実経路の親ロック待機後割当・管理書込・故障分類として採用し未完了。候補試験は専用使い捨てPostgreSQL 17で**10件合格**、Ruff format/check・tyも合格。実revision、正式認可適用器、U-G1保存境界、全件検査の代わりにはしない。本段落のレビュー結果追記で資料自身のSHAは変わるが、レビュー対象だった直前本文の値を上記に固定し、候補3ファイルは変更していない。

| 初回指摘 | 採否・今回の具体的な解消 | 正式ゲート後に残る検証 |
| --- | --- | --- |
| P1① ロック契約と権限の不一致 | **採用**。通常SELECTへの変更を撤回し、既受理の既定→規則`FOR SHARE`を候補SQLへ反映。2接続で特権UPDATEの待機を実測。最小2列grantは実DML能力なので、**正本/ACL個別承認までは未解消** | TSK-250の`data-model.md`限定追随、TSK-424の認可正本限定追随と列grant・剥奪対称性、正式7.3/7.6と7.7、実認可適用器でのACL/カタログ照合 |
| P1② 空DBの起動順逆転 | **採用**。S0〜S4を固定し、空DBの認可前停止、認可後A、故障全取消・再試行、既存DB追随を候補で実測。**実revision/起動器を未登録のため未解消** | 移行・認可/運用所有側が閉じた起動入口、`backend/tests/db_fixtures.py`、CI migration job、`docs/ops/deployment.md`の差分を受理。実Alembic version据置/skip、A成功B失敗/再試行、公開判定を正式資産で実測 |
| P2 親ロック待機後の割当・管理並行書込・故障分類 | **採用、後続証跡へ**。別SQL文による割当再読取とロック順を候補へ保持。今回の2接続は規則/既定対特権UPDATEに限定 | ステップ3〜6の実関数で両順序・timeout/rollback、管理入口を開く場合の同時書込、TSK-395で保存/RG1直前の全取消を試験 |

**今回の正式判断を担当別に束ねる**: TSK-250所有側は`data-model.md`§3-2/§10-5と変更履歴の§10-1差分、TSK-424認可/tenant境界所有側は`product-authz-surface.md`§2/§3とownerの列ACL・EXECUTE・GUC残余脅威、移行/運用所有側は§10-2のS0〜S4・一時RLS・失敗状態・CI/fixture/運用手順、POはFR-014/DRAW-04の§8-3選択肢Aと個別権限/配置ゲートを判断する。所有側不在の代替受理は対象節ごとに別裁定し、§6-5限定の過去承認を流用しない。候補試験10件と限定レビューの指摘0は、これらの人間判断や後続の実製品証跡を置き換えない。

### 10-4. 人間の項目別決定票（2026-10-16方針採用、設計正本は§10-6で正式確定）

次の5行は2026-10-16のPOメッセージで**方針採用済み**。その後の設計正本の正式確定は§10-6に記録した。表内の「正本未確定」「in-review」は方針採用時点の履歴であり、現在の残条件は§10-6/§10-7を正とする。§1〜9は採用済み契約、旧案、レビュー履歴と具体DDLの参照資料であり、§10-1/§10-2の結論と食い違う旧案を再選択しない。**承認済みの未登録候補・隔離試験は継続可能**だが、方針採用と正本確定は個別資産・権限承認、実変更後7.7受理、本人逐行確認を兼ねない。

| 項目 | 推奨する決定文 | 具体差分・担当と正式ゲート | 影響・未解消指摘 |
| --- | --- | --- | --- |
| **1 ロック契約** | 「段階AのresolverはREAD COMMITTEDの同一scopeで、大会親行`FOR UPDATE`→待機後の別SQL文で割当照会→既定行`FOR SHARE`→規則行`FOR SHARE`の順を守り、取得ロックをcommit/rollbackまで保持する。製品管理書込入口は閉じる。特権migrationは試合作成流入停止・進行中scope排出後、既定表→規則表の順で`ACCESS EXCLUSIVE`を取得し、timeout/結果不明時は公開停止する。通常SELECT案は採らない。」 | `docs/design/product-authz-surface.md`§2の既定/規則2行へそれぞれ`UPDATE(game_type_category)`/`UPDATE(id)`、§3の通常SELECT段落を§10-1の引用本文へ置換。`docs/design/data-model.md`§3-2/§10-5と各変更履歴は§10-1指定文へ追随。TSK-250/TSK-424所有側の採否、対象差分の正式7.3・7.6、列ACL・付与/撤去/カタログの個別承認、実変更後7.7が必要。 | ownerの2列UPDATEは自己更新を含む**実DML権限**であり、NOLOGIN/非membership・関数DML禁止・app直UPDATE拒否と一体で審査する。初回P1①は候補SQLと2接続で技術整理済み、**正式正本/ACL未承認のため未解消**。将来管理書込を開くときは同じ順の再審査が必要。 |
| **2 新規DB起動順** | 「新規DBと既存DBの起動は、S0=現行schema revision到達、S1=現行認可適用と照合、S2=F-2配置Aをownerで適用・commit、S3=関数/owner/ACLの認可Bを別transactionで適用・commit、S4=カタログ・7.7・実経路検査後に作成公開、の閉じた入口に統一する。S4前は作成不可。」 | 正式Alembic revisionは先行統合時の実headの後続に置き、起動器はS0の明示停止・各段階の主体/カタログ照合・失敗時停止を担う。`backend/tests/db_fixtures.py`の`head→認可`、`.github/workflows/ci.yml`の直接`upgrade head`、`docs/ops/deployment.md`の運用表をその入口へ追随。移行/認可/運用所有側が差分と実行主体を受理し、CI/fixture変更をPRレビュー、運用正本の規範変更なら7.6の判定に従う。配置/認可の実資産は個別ゲートと7.7を通す。 | S1前のAはFORCE RLS前提がなく停止。A失敗=全取消・version据置、A成功/B失敗=Aの10行は保持・作成非公開、B結果不明=カタログで確定するまで再試行/公開停止、A再実行=衝突停止・自動stamp禁止。初回P1②は空DB/故障/再試行/既存DBを候補で実測したが、**実revision・起動器・CI・運用が未受理/未実証のため未解消**。 |
| **3 正本最終本文** | 「`data-model.md` v1.1は§3-2の7ロールと§10-5の固定5組の出所証明を確定し、§10-1の2列ロック権限だけ追随する。新設`product-authz-surface.md` v0.1は4引数関数、scope注入UUIDとtenant GUC一致、閉じた書込入口、§10-1の`FOR SHARE`/owner最小列ACL、DB資格情報取得時の残余脅威を規範とする。§6-5・F-2値・5 UUID・機械文字列は変えない。」 | `data-model.md`の現行`in-review`本文と変更履歴v1.1へ§10-1の2文のみ追加。`product-authz-surface.md`の現行`in-review`候補のうち§2の2権限行と表後段落（3列`UPDATE`の実DML能力・付与/撤去）、§3の通常SELECT段落、§4の資格情報隔離・直SQL遮断・証明不可時の作成非公開、変更履歴を最終差分として人間採否対象に含める。4引数/UUID-GUC一致は現行候補に反映済みで再審査対象へ戻さない。TSK-250/TSK-424所有側採否、**今回のロック差分と影響節**に必要な追加7.3枠の6.3裁定、最終本文/反映差分の人間確認、7.6の改訂/新設承認が必要。所有側不在の代替受理は各本文の指定節に限り別裁定。 | 旧候補をそのままapprovedにすると§2/§3が候補SQLと矛盾するため、今回の修正後候補を審査・採否対象とする。正本の正式確定は未了。以前のD/A全文レビュー結果（各2周収束）と4引数限定レビューの採否は保持し、今回の新しい意味差分だけを審査する。§6-5の承認を拡張しない。 |
| **4 FR-014／DRAW-04** | 「FR-014の『コールド適用開始回Nが規定回Rを超える値は保存拒否』を優先し、`DRAW-04`の有効判定より前に`N>R`を拒否する。`N=R`はこの条件では拒否しない。裁定前は矛盾例を保存成功にしない。」 | 要件書FR-014の受入基準は維持。付録F-1の設定時分岐`DRAW-03`の拒否条件へ`いずれかのコールド段でN>R`を追加し、正例に`R=9,L=9,N=10`の拒否、負例に`N=R=9`がこの条件に非該当と追記。`DRAW-04`は`DRAW-01`〜`03`非該当の残余として現行の閉じたID集合を保つ。付録F-1の変更履歴と関連ゴールデンケースを追随。要件所有側の正式7.3・人間承認が必要。 | 例`R=9,L=9,N=10,tiebreak=null`は保存時エラーとなり、現行単一codecの相関拒否と一致する。F-2の既定5組に値変更なし。**要件の規範矛盾は未裁定**で、候補試験合格では解消しない。 |
| **5 GUC残余脅威** | 「通常製品経路は認証済み`TenantContext`→検証済みscope→固定function operation→4引数関数へ限定し、関数はscope UUID・`app.tenant_id`・大会tenantを照合する。DB接続資格情報を取得した主体による任意GUC設定はこの照合では防げない残余脅威として明示し、資格情報隔離・直SQL遮断を公開条件とする残余脅威の受容を提案する。認可・tenant境界所有側とPOの正式採否までは公開しない。隔離が成立しなければ作成公開を拒否する。」 | `product-authz-surface.md`§4の現行`in-review`本文へ資格情報隔離・直SQL遮断の公開条件と証明不可時の非公開を追記した意味差分を採否対象とし、認可/tenant境界所有側とPOが**受容する攻撃者能力と運用前提**を明示採否する。関数のUUID/GUC不一致・欠損/不正UUID・別tenant、app直表/任意関数の拒否、カタログ一致を実装後の専用DBで確認。資格情報や直SQL制御の正式資産に差分が出る場合だけ対象資産の個別ゲート/7.7へ載せる。 | GUC検査のみをDB接続窃取への防御と主張しない。受容しなければ別の資格情報/接続境界設計を承認するまで作成公開を停止。**残余脅威の明示採否は未了**で、限定レビュー指摘0件を受容と読み替えない。 |

**レビュー結果の読み方**: 初回候補レビューはP0=0/P1=2/P2=1。P1二件は上表1・2の候補/試験で技術的な対策を定めたが、個別正式ゲートが未成立で**未解消**。P2は§10-3の実製品試験へ採用し未完了。固定SHAの限定独立再レビューは**新規P0/P1/P2=0**であり、初回指摘の消込みや正式7.3/7.7の受理ではない。既承認のcodec、F-2値/UUID、A共有実行器、DB4引数・公開request3項目を再判断しない。人間の各行の採否後も、正式資産への反映はその行のゲート成立後とする。

### 10-5. 方針採用後の審査候補と停止境界（§10-6の確定前記録）

`docs/design/data-model.md` v1.1の審査中候補では§3-2の専用ownerに親`UPDATE(disabled)`、既定`UPDATE(game_type_category)`、規則`UPDATE(id)`と関数DML禁止・grant撤去を対応付け、§10-5に親ロック後の別SQL割当読取、既定→規則`FOR SHARE`、scope終了までの保持、特権migrationの流入停止・scope排出・表排他順を追記した。`docs/design/product-authz-surface.md` v0.1の審査中候補では§2の2列grantと付与/撤去/カタログ照合、§3のロック順・保持期間・特権migration停止、§4のDB資格情報隔離・直SQL遮断・隔離不成立時の公開停止を記した。各変更履歴も`in-review`を維持する。**これは正式確定や実grantではない**。今回の追加7.3はこのロック・列権限と影響節だけを対象とし、既済み全文レビューを繰り返さない。

候補SQL・配置・試験は§10-1/§10-2に既に一致する。隔離PostgreSQLの候補試験10件は、FOR SHAREと列UPDATEの関係、二接続での特権変更待機、S0前の配置停止、S1後の配置全取消/再試行、A成功B失敗時の非公開と既存DB追随を確認した。正式revision・認可適用器・起動器・CI・運用手順は未登録なので、候補試験を製品のS4成功と扱わない。起動器の変更対象は`backend/tests/db_fixtures.py`、`.github/workflows/ci.yml`、`docs/ops/deployment.md`と既存起動入口であり、各所有側と個別ゲートで具体差分を確定する。A失敗時は全取消/版据置、A成功B失敗時は配置行保持/作成非公開、B結果不明時はカタログ確定まで作成非公開とする。

FR-014の`N>R`拒否を優先する要件改訂候補は§10-4の4行目のとおり、正式要件本文を今回は変更しない。既存の単一相関検証と負例試験で矛盾例の保存成功を拒否し続ける。GUC偽装を接続資格情報取得主体について関数保証外とする脅威モデルはPO方針として採用されたが、認可・tenant境界所有側およびPOによる正式な脅威モデルの採否、資格情報隔離と直SQL遮断の実証は未了である。隔離条件を証明できなければ試合作成を公開しない。

**今回の限定追加7.3レビューと採否**: 2026-10-16にPOが許可した1回を、審査前4ファイル差分SHA `e2a7e6235cfb5aaa5d018edd1ddff60524363852b452758662a670b95bf68882`に対して候補作成に不関与の独立担当が読み取り専用で実施。**P0=0/P1=1/P2=1、両件採用**。P1は§10-4の項目3/5が認可正本§4の資格情報隔離・直SQL遮断・非公開条件を採否対象から漏らし、§2表後段落の3列grant/撤去も対象として不足した点。§10-4の3/5行に最終差分を明記して是正。P2は「残余脅威を受容する」が所有側/POの正式採否済みと読める点。脅威モデルはPO方針採用と正式採否未了を区別し、採否まで非公開と是正。レビュー担当の判定は**両件是正後に今回の限定レビュー収束可**であり、最終反映は人間承認対象。既済み全文レビューを繰り返さず、追加レビュー枠を自動で増やさない。初回候補レビューのP1二件・P2、所有側採否、正式7.6/7.7、実製品試験は別に未完了。

**最終候補の検査（同日）**: 候補3ファイルのSHAは配置`631e253ebaa69fb93449780e0d43ab14e069b4dffa2f02881919af08ff7f8974`、SQL`6cbdd887cc46e537604a9aeeb707e4f3e6ca0c7f8b9a9a6d178329303a0968aa`、試験`744eb36caffee990b6510281c1f6c02620ccb4d263dfff6d2d953f473674ee9c`で限定レビュー時から不変。共有開発DBの既存試験ロールにより最初のDB試験はfixture開始前に10件setup errorとなったため、共有ロールを変更せず専用使い捨てPostgreSQL 17で再実行し、候補10件と`N>R`単一相関負例1件の**11件合格**。候補Python2ファイルのRuff format/check、backend ty、`git diff --check`、docs-status 21文書/違反0も合格。正式revision・認可適用器・既存DB適用・実HTTP/RG1/保存・7.7受理の試験結果ではない。

### 10-6. 正本確定の記録とFR-014正式7.3

2026-10-16の本会話でPOは、§10-4〜10-5の両設計正本の最終本文と限定レビュー後P1/P2是正差分を確認し、**今回の改訂範囲だけ**正式確定を承認した。`data-model.md` v1.1、`product-authz-surface.md` v0.1のfrontmatter・変更履歴・`docs/README.md`をapprovedへ追随した。§6-5、固定5 UUID、F-2の値、機械文字列は不変。`schema-manifest.json`の正本SHAと`shared-preconditions.json`の参照blobは7.7実値受理前なので**未更新**であり、当該凍結検査は未合格のまま保持する。今回の正本確定を具体列grant・配置・起動器・凍結基準の承認に読み替えない。

FR-014と付録F-1の正式要件改訂候補は`requirements-pitchlog-2026-07-22.md` v2.15へ一本化した。変更は変更履歴、`DRAW-03`へのコールド段`N>R`保存拒否の追加と正例・負例、`DRAW-04`の負例追随だけ。FR-014受入基準、既存DRAW ID、`N=R`、F-2の5組/値は変えない。独立担当による正式7.3第1回全文レビューは差分SHA`f0decf4965ef1980e0029457274acb7a44699918758908932224d3114d634e61`に対し**P0=0/P1=0/P2=0、可決**。採否対象なし・反映0周で、ハーネス7.3-2の「1回目・指摘ゼロ→収束」により自動第2回は行わない。**2026-10-16の本会話でPO山田正輝が今回の最終本文と変更履歴を承認**したため、要件正本のfrontmatter・変更履歴・索引を`approved`へ更新した。承認はF-2値や他要件の改訂、関連ゴールデンケース・実製品保存入口・7.7の完了を含まない。

### 10-7. 個別資産のexact候補差分と所有側採否

| ゲート | exact候補差分・対象 | 所有側と未完了の判断 |
| --- | --- | --- |
| F-2配置 | 未登録`backend/migrations/candidates/tsk550_stage_a_rule_defaults.py`（SHA`631e253ebaa69fb93449780e0d43ab14e069b4dffa2f02881919af08ff7f8974`）を正式Alembicの**先行統合時点の実headの次revision**へ移す。固定5 UUID・5キー・5値、`rule_sets`と`game_type_rule_defaults`の10行だけをINSERT。owner=`pitchlog_owner`、2表の`ACCESS EXCLUSIVE`、FORCE RLS確認、一時owner向けSELECT/INSERTポリシー4件を同一transactionで作成・撤去。ID/キー/一時policy衝突で全取消、既存行UPDATE/DELETEなし、downgradeは物理削除せず停止。 | 移行/data-model所有側。U-R1作業木に次revision候補があり、番号を今固定しない。具体配置と一時RLS・revision/順序・downgradeの個別承認、正式資産の7.7が未了。 |
| 専用owner/関数 | `contracts/authz/product/ddl-elements.json`の`roles[]`へ`pitchlog_rule_resolution_fn_owner` 1件（`NOSUPERUSER NOLOGIN BYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION`、membership辺0）を追加。`schemas[public]`へ同ownerの`USAGE`を追加し`CREATE`は禁止。`functions[]`へ`FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)` 1件、`SECURITY DEFINER`/`VOLATILE`/`search_path=pg_catalog,pg_temp`/戻り`jsonb`/owner専用、`pitchlog_app`だけ`EXECUTE`、`PUBLIC`は剥奪。関数本文は候補SQL SHA`6cbdd887cc46e537604a9aeeb707e4f3e6ca0c7f8b9a9a6d178329303a0968aa`を同identityの`function-bodies/functions/`とmanifestへ登録し、任意SQL・関数内DML・transaction制御なしを検査する。 | 認可面/tenant境界所有側。`product_provisioning.py`の既存単一transactionとapply/unapply順序を維持。`ddl-elements.json`、分割本文とmanifest、生成snapshot/corpus、catalog checkerのexact-setと7.7受理が未了。U-R1所有の共有ファイルは当方で変更しない。 |
| 列ACL | `column_acl_expectations[]`へ専用ownerの15列を追加。`tenant_vocabularies`=`tenant_id,key,category,disabled`をSELECT、`disabled`をUPDATE。`tournament_rule_assignments`=`tenant_id,tournament_key`をSELECT。`game_type_rule_defaults`=`game_type_key,game_type_category,rule_set_id`をSELECT、`game_type_category`をUPDATE。`rule_sets`=`id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh`をSELECT、`id`をUPDATE。`UPDATE`の列集合は**3列だけ**、いずれも実DML能力。全15行の`function_id`は上記固定identity、`grant_option=false`。appの既存`global_read_only`既定表SELECTを維持し、規則/割当表のapp直SELECT/書込を開かない。unapplyは関数`EXECUTE`と15列grantを残さない。 | 認可面所有側。列grantを生成・静的照合する`product_control_access.py`、`scripts/check_authz_catalog.py`と負例、再適用/撤去後のカタログexact-setを個別承認後に実装・検証。今回の隔離候補試験は手動grantの実効性を示すだけで正式適用器を代替しない。 |
| S0〜S4起動入口 | S0=`0031_intent_selectors`など**正式登録直前の実schema head**まで適用して停止、S1=現行認可をsuperuser接続で適用・カタログ照合、S2=配置Aを`pitchlog_owner`で適用/commit、S3=owner/関数/ACLの認可Bをsuperuserの別transactionで適用/commit、S4=カタログ・7.7・実製品経路試験を確認して初めて作成公開。`backend/tests/db_fixtures.py`の`head→認可`、`.github/workflows/ci.yml`の直接`upgrade head`、`docs/ops/deployment.md`の新規/既存DB手順と既存起動入口をこの順へ変更する候補。S1前Aは拒否、A失敗は全取消/版据置、A成功B失敗は10行保持/作成非公開、B結果不明はカタログ確定まで非公開、S2のcommit結果不明を含むA再実行は、revision一致に加え固定5+5行のID・キー・値、4一時policyの非残存、既存ACL/RLS/ownerがすべて完全一致した場合だけskipする。不一致または照合不能なら停止し、自動stamp・盲目的再実行を禁止する。 | 移行/認可/運用所有側とCI所有側。既存起動器の正式差分・主体・停止/再試行の受理、運用正本7.6、凍結資産7.7、正式revisionの空DB・既存DB実測が未了。候補試験のS0〜S3実測をS4公開可の証拠にしない。 |

これらは**exact提案**であり、実ファイルへの正式登録ではない。共有資産はC1→U-R1→Bの編集・統合順を守り、B/Cに機能上の相互待ちを置かない。所有側から項目別採否が得られない場合は、(1)移行/data-model=F-2配置・一時RLS・revision/起動順だけ、(2)認可/tenant=owner・3列ACL・関数EXECUTE/GUCだけ、(3)CI/運用=S0〜S4入口だけ、という**ゲート限定の独立査読＋PO代替受理**を個別に裁定してもらう案とする。過去の§6-5限定代替受理を広げず、担当不在を自動受理にしない。

**候補差分の追加限定レビュー（設計正本・要件正本の7.3とは別）**: 配置・関数SQLの上記SHAは不変。候補試験の追加後SHAは`805b866f0ef527185eadf0fad22af47210a1c6c433de14ea05602c26fb76ee79`で、候補試験と本資料のレビュー前2ファイル差分SHAは`e45381b34a43cca7a764d1044978430f2edd1dcbd186f668f57d793ddbb709ee`。独立担当の読み取り専用レビューは**新規P0=0/P1=0/P2=1**。P2はS2のcommit結果不明時にrevisionのみでskipすると、配置値や一時RLS残存を見落とす指摘。採用し、上表S0〜S4行にrevision・固定5+5行のID/キー/値・一時policy非残存・既存ACL/RLS/ownerの完全一致をskip条件として追記した。不一致・照合不能なら停止する。修正は資料の停止条件のみで、候補コードと試験はレビュー後不変。独立レビューは正式15列ACLの生成・撤去、起動器、7.7、製品経路の完了を認定していない。

**候補の最終限定検査**: 専用使い捨てPostgreSQL 17で候補11件と`N>R`単一相関負例1件の**計12件合格**（41件deselected）。追加試験は専用ownerの3列UPDATEと関数EXECUTEの付与・剥奪を確認した。正式認可適用器の15列exact-setやunapplyの証明は個別ゲート後に残る。

### 10-8. 個別資産の最終承認票（正式受理前）

**固定した受理対象**: §10-7の本文だけのUTF-8 SHA-256は`2543ed7c35d7e6539a08bd8c2b04aef837501f03724e40eeb4f3c70d923ea859`（見出し直後から本見出し直前までを取り、末尾改行を1個へ正規化）。候補配置は`631e253ebaa69fb93449780e0d43ab14e069b4dffa2f02881919af08ff7f8974`、候補関数SQLは`6cbdd887cc46e537604a9aeeb707e4f3e6ca0c7f8b9a9a6d178329303a0968aa`、候補試験は`805b866f0ef527185eadf0fad22af47210a1c6c433de14ea05602c26fb76ee79`。HEADは`830d3b621a7f03095657d5b70e338402c4948581`であり、候補と本票は**未コミット差分**なのでHEAD単体を受理対象と呼ばない。正式登録後の生成資産・after digest・7.7値はこの票に含めない。

| 判断単位 | exact差分と必要性 | 拒否・停止条件 | レビュー採否と未了の所有判断 |
| --- | --- | --- | --- |
| **配置** | §10-7の配置行と候補配置SHA。実headの次revisionで固定5 UUID・5キー・5値の10行のみINSERTし、`pitchlog_owner`が2表`ACCESS EXCLUSIVE`、一時SELECT/INSERT RLS 4件を同一transactionで使い撤去する。実規則の出所を証明し、仮規則なしでresolverを動かすために必要。 | 固定ID/キー・既存行との衝突、一時policy残存、FORCE RLS欠落、配置値不一致、失敗/結果不明なら停止。旧行を推定・UPDATE/DELETEしない。downgradeも物理削除しない。 | 候補レビュー初回P1②は起動順の候補実測まで、正式revision未実証。追加限定レビューP2は結果不明時の照合条件へ採用済み。TSK-250移行/data-model所有側の配置・一時RLS・revision採否が未回答。**回答不能は未確認**。 |
| **owner** | §10-7のowner行。`pitchlog_rule_resolution_fn_owner`を`NOLOGIN`/`BYPASSRLS`/`NOINHERIT`等の指定属性、membership辺0で1件追加し、`public`の`USAGE`のみ付与して`CREATE`は与えない。固定関数が直接表権限をappへ開かずに読める最小主体。 | role属性・membership・schema権限の余剰、appのowner継承、ownerの任意SQL到達、関数内DMLがあれば拒否。apply/unapplyの権限残留やカタログ不一致で公開停止。 | 設計正本は今回範囲で承認済み。初回P1①は列grantと正式カタログ未了のため正式解消ではない。TSK-424認可/tenant境界所有側の具体role採否は未回答。**回答不能は未確認**。 |
| **関数・EXECUTE** | §10-7の関数行と候補SQL SHA。固定identity`public.resolve_stage_a_rule(uuid,text,text,boolean)`1件、`SECURITY DEFINER`/`VOLATILE`/固定`search_path`/`jsonb`戻り。`pitchlog_app`だけEXECUTE、`PUBLIC`は剥奪。scope注入UUIDとtenant GUCを照合し、親→割当別文→既定/規則`FOR SHARE`をscope終了まで保持するために必要。 | identity・本文・owner・EXECUTE・GUC・関数内DML・戻り値の不一致、割当あり/出所不明/無効値/読取失敗は保存成功禁止。資格情報隔離と直SQL遮断を証明できなければ公開停止。 | 4引数訂正の限定レビューP1/P2採用済み、今回の候補追加レビューは新規P0/P1=0。正式関数本文・EXECUTE・GUC脅威モデルのTSK-424所有側採否は未回答。**回答不能は未確認**。 |
| **列ACL** | §10-7の列ACL行。専用ownerへ`tenant_vocabularies` SELECT4/UPDATE`disabled`、`tournament_rule_assignments` SELECT2、`game_type_rule_defaults` SELECT3/UPDATE`game_type_category`、`rule_sets` SELECT6/UPDATE`id`、合計SELECT15列/UPDATE3列、`grant_option=false`。`FOR SHARE`に必要なUPDATE列を3列に閉じ、appの既存直権限を維持する。 | 余剰列grant、appの規則/割当表直SELECT・書込、関数外DML、unapply後の残留、15列exact-set/3列UPDATE不一致で公開停止。UPDATEは実DML能力であり安全なロック専用権限とは扱わない。 | 追加候補試験は3列UPDATEとEXECUTEの付与/撤去を実測、正式15列生成・撤去は未実装。初回P1①は正式ACL/7.7まで未解消。TSK-424所有側採否は未回答。**回答不能は未確認**。 |
| **S0〜S4起動入口** | §10-7の起動入口行。S0=実head直前のschema、S1=現行認可、S2=配置A、S3=関数/ACL B、S4=カタログ・7.7・実経路照合後だけ公開。対象は`backend/tests/db_fixtures.py`、`.github/workflows/ci.yml`、`docs/ops/deployment.md`と既存起動入口。新規DBの`head→認可`逆順を正すために必要。 | S1前の配置、配置失敗時の版進行、A成功B失敗時の公開、commit結果不明時の盲目的再実行/自動stamp、固定行・policy・ACL/RLS/owner不一致を拒否。 | 候補の空DB/故障/再試行/既存DB試験は合格、初回P1②は正式入口未実装のため未解消。移行/認可/CI/運用所有側の実行主体・共有ファイル編集枠・手順採否が未回答。U-R1が共有資産を編集中で、当方は変更しない。**回答不能は未確認**。 |

**所有側採否の現状と代替経路**: TSK-250、TSK-424、U-R1の照会先を再確認したが、今回の対象への採否回答は確認できない。「無回答」を「回答不能」や「受理済み」と記録しない。返信を無期限の前提にもせず、POが**無回答のまま当該ゲートに限る代替経路を選ぶか**、所有側の明示回答を待つかを判断する。前者を選ぶ場合も、下表の不足範囲を候補作成に関与していない独立担当が査読し、P0/P1/P2・採否・残余を固定してから、POが配置、認可/GUC、起動入口を**項目別に代替受理**する。独立査読前のこの票だけで代替受理成立とはしない。§6-5限定の過去承認は流用しない。

| 代替受理の対象 | 既済み独立査読が覆う範囲 | 未確認の範囲と必要な追加枠 |
| --- | --- | --- |
| 配置・一時RLS・revision | 配置DDL骨格の予備査読2回のP0/P1は採用。現候補Python SHA`631e253e…`の限定候補レビューは初回P0=0/P1=2/P2=1、後続の比較・差分レビューでは新規P0/P1=0。固定10行、衝突停止、全取消、空DBのS1前拒否などを隔離DBで確認。 | **現候補に対する移行所有側の契約採否の代替査読は未実施**。1件の限定独立査読枠で§10-7/10-8の配置行、候補Python全体、一時policyの作成/撤去、固定値と非更新/非削除、ロック・失敗/結果不明・downgrade、実head後のrevision割当規則を照合する。実revision番号と正式7.7値は実装後の別確認。 |
| owner・関数・列ACL・GUC | `product-authz-surface.md`の正式7.3全文2回、4引数訂正限定1回、ロック/列権限限定1回は各指摘を採用して正本確定。候補SQL SHA`6cbdd887…`と負例は限定レビュー済み。3列UPDATE/EXECUTEの手動grant・剥奪は隔離DBで確認。 | **正式認可資産のexact差分と脅威境界を所有側の代わりに採否する査読は未実施**。同じ限定枠で§10-7/10-8のowner属性・membership0・schema USAGE、4引数関数identity/本文/EXECUTE、15列SELECT/3列UPDATEの実DML能力、PUBLIC剥奪、apply/unapplyの対称性、tenant GUCと資格情報隔離/直SQL遮断の残余条件を確認する。正式適用器・生成資産が未作成のため、その実差分レビュー、catalog exact-setと7.7は実装後の別ゲート。 |
| S0〜S4起動入口 | 初回候補P1②を採用して空DBの認可前停止、A失敗全取消、A成功B失敗時の非公開、既存DB追随を候補試験で確認。結果不明時のskip条件は追加限定レビューP2を採用して§10-7へ反映。 | **正式起動器・fixture・CI・運用手順の差分査読は未実施**。同じ限定枠で§10-7/10-8の適用主体・S0〜S4順・現行`head→認可`入口との接合、revision/配置値/policy/ACL/RLS/ownerの再開照合と公開拒否を審査する。実起動器・CI・運用正本のexact変更は所有解除と個別ゲート後に作り、その時点の差分レビューと空DB/既存DB試験が必要。 |

**追加レビューの最小枠**: 必要なら**独立した読み取り専用の限定レビュー1回**をPOが明示許可する。対象は固定SHAの§10-7、§10-8の上記5行、配置/SQL/試験の固定3 SHA、既存設計正本の今回確定節と既存レビュー採否の残差だけ。既済みの正本全文レビュー・要件7.3・候補先行査読は繰り返さず、正式資産の実装済みであるかのような判定を求めない。候補作成に関与していないレビュアがP0/P1/P2と項目別の代替受理可否を返し、重大指摘は採否を決めてからPOへ一括提示する。レビュー枠の許可も、レビュー結果に基づくPO代替受理も**現時点で未取得**。

**GUC残余脅威の正式採否**: POが採用したのは「資格情報取得主体のGUC偽装は関数保証外、通常経路の資格情報隔離と直SQL遮断を公開条件」という**方針**。認可・tenant境界所有側による攻撃者能力と隔離条件の正式採否は**未回答・未受理**であり、無回答を受容としない。接続資格情報の管理と直SQL到達性を実製品経路で証明できない限り、S4へ進めず試合作成を公開しない。

**判断順**: 要件v2.15と両設計正本の今回範囲は承認済み。次に本票の**候補資産契約**と不足分の独立査読枠、無回答時の項目別PO代替経路を判断する。実装前の候補契約承認は、まだ存在しない正式起動器/認可適用器の実差分承認を代行しない。実登録によって決まるrevision・生成snapshot/corpus・after digestは別の7.7実値受理へ送る。現時点で既存DB適用・公開・push/PR/マージは行わない。

### 10-9. 2026-10-17 段階起動の別ファイル候補と統合条件

§10-8後のPO裁定で、固定SHAに対応する具体資産と所有側無回答項目を今回限定で代替受理した。上記§10-8の「未取得」は提出時点の履歴であり、現在の採否は計画書と受理シートの後続記録が正。認証済みTenantContext・検証済みscope・固定operation・資格情報隔離・直SQL遮断を公開条件とし、DB資格情報取得主体のGUC偽装は関数保証外としてPOが受容した。隔離条件を実証できなければS4へ進まない。

`backend/migrations/candidates/tsk550_stage_a_startup.py`は**隔離DB専用**の閉じた候補入口である。既存schemaの`0031_intent_selectors`と`pitchlog_owner`認証をS0として照合し、owner/認可適用接続のDB実体と17資産の完全集合・内容を変更前に照合する。既存製品認可をS1で適用、候補F-2配置をownerの別transactionでS2、17候補認可資産を管理接続の別transactionでS3へ進める。S1のFORCE RLSとS3の関数owner/EXECUTEを照合し、戻り値は常に`publishable=False`。これは正式migration・認可登録・S4公開判定の代用品ではない。U-R1の未統合revision `0032`を踏まえ、正式化時はS0の実revisionを最新基線から再導出する。

| 状態 | 候補で確かめる停止・再開条件 | 正式化時に残る接続 |
| --- | --- | --- |
| S0以前・S1失敗 | S0 revision/owner認証・両接続先・候補資産が違えば適用前に停止。S1のcommit前失敗は適用器が全取消し、作成非公開。commit後/結果不明は認可catalogと主体を照合するまで停止・非公開。現候補入口はこの状態からの自動再開を実装しない | 新規DB/既存DBの実入口、CIと運用起動主体、S1結果不明後の再開判定 |
| S2失敗・結果不明 | A配置はtransaction全取消。結果不明はrevisionと固定5+5行のID/キー/値、一時policy0、ACL/RLS/ownerを照合するまで停止し、自動stamp・盲目的再試行をしない | 実Alembic revisionの版据置/再開判定 |
| S3失敗・結果不明 | S2配置10行は残り、候補関数は公開不可。B認可のcommit前失敗は別transactionで全取消。commit後/結果不明はowner/ACL/関数のexact照合まで停止 | 正式manifest/適用器のapply・unapplyと7.7カタログ照合 |
| S4 | 候補入口は常に`publishable=False` | 7.7実値受理、実HTTP・認可・資格情報隔離・直SQL遮断、2接続/故障注入を確認した正式公開判定 |

候補fixtureは`backend/tests/db/test_stage_a_rule_candidates.py`の専用使い捨てDBを使う。CIのbackend jobは既に`uv run pytest -c pyproject.toml --cov`でこの試験を含むため、候補段階で重複実行を追加しない。一方、同jobの`uv run alembic upgrade head`は正式配置revision登録後にはS1前Aとなり得るため、**正式登録と同じ差分**でS0〜S3の実起動入口へ置換し、`alembic current --check-heads`と照合する。`backend/tests/db_fixtures.py`の`head→認可`も同じ時点で段階入口を使う。`docs/ops/deployment.md`への手順反映は、正式入口・実revision・7.7値が固定した差分で行う。現在の候補を既存DBへ適用しない。

共有資産の編集解除条件は、C1 PR #144の共有repository/tenant-boundary差分が統合または明示的に所有解除され、次にU-R1 PR #143の認可適用器・manifest・schema/contract資産とrevision `0032`の編集・受理履歴が統合またはファイル別に所有解除されること。両担当に対象パスと引渡し時点を照会済みで、**現時点の回答は未確認**。Bは解除後に最新developを取り込み、先行側の履歴・revisionを保持した追加集合だけを登録し、7.7実値を別受理へ出す。B/Cの機能上の相互待ちは設けない。

**2026-10-18の停止理由訂正**: PR #144は`3052e0db`で統合済みで、最新`origin/develop=ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`に含まれる。C1の統合待ちは現在の停止理由ではない。残るのはU-R1の共有編集枠のパス別引き渡しである。U-R1の未統合ブランチはBの基線に使わず、正式組込み時は実際の最新developと受理済み履歴・revisionから再導出する。U-R1カードへの確認コメント`3fd93b75-e687-81d5-b12e-001d7accda9d`で、現在所有するパス、解除条件、引き渡し予定を照会した。回答前に解除済みとは扱わない。候補17資産、最終限定レビュー指摘0、隔離DB全21件とTOCTOU是正後の影響4件の成功証跡は保持する。

### 10-10. PR #143統合後の正式組込み候補（2026-10-18）
`origin/develop=156dd139a893845428a1ecab69632143f7694e0b`はPR #143の統合コミットであり、#144 `3052e0db`と#143の受理履歴を包含する。U-R1/C1の統合・所有解除待ちは停止理由から外した。統合後の追加差分はAlembic `0033_stage_a_rule_defaults`、承認済み関数/owner/15列ACLの正式17資産、S0〜S3起動入口、fixture・CI・運用手順への追随である。製品関数operation登録は0件、S4公開判定は行わない。既存DBへの適用・push・PR作成・マージは行っていない。
CIの最初の実DB再現では、管理者所有DBへ0032を適用した後に配置ownerが`alembic_version`を読めずS0で停止した。専用owner所有の`pitchlog_stage_a_ci`を別途作る構成に修正し、実ワークフローのDB作成→0032→S1/S2/S3→`current --check-heads`→`alembic check`の5段階を隔離PostgreSQL 17で完走した。候補・正式入口の隔離DB24件、関連認可/migration100件、Ruff/ty、docs-statusは通過。S3故障後のS2固定5組・一時policy・owner/RLSの照合と閉じたS3再開を追加し、値改変は認可B前に拒否する。
正式組込みの第1回敵対レビュー（実DB操作なし）はP0=0/P1=3/P2=1、否決。P1①7.7未受理は下記の実値受理待ち。P1②正本digest不一致は承認済み正本を`96dcb38f`で反映し、schema-manifestとshared-preconditionsの実digestへ是正したが、要件claim全数オラクルは新しい変更履歴1行の分類・lock再sealを要するため別ゲートとして未完了。P1③S3故障後の再開入口は上記の閉じた実装/負例へ是正、S1結果不明は自動再開を禁止し運用者のカタログ確認を残す。P2の共通認可fixtureは0032時点のACL単体試験として維持し、実S0〜S3は専用隔離fixtureとCIで検証する案とする。採否の最終確認は差分レビューへ残す。

rootのcore-guard登録検査は新規`backend/src/pitchlog/db/stage_a_startup.py`が`areas[].paths`未登録として拒否した。既存計画のステップ7/8は`test_rule_resolution.py`だけを宣言・登録するため、正式登録時にこの起動入口も加える最小追補が必要。ステップ3で共有guard定義を先取り変更せず、後続のパス宣言とJSON登録を別コミットにする規律を維持する。
### 10-11. 7.7実値の受理記録案（正式履歴未記入）
比較元は上記`origin/develop`で、authority=`contracts/tenant_boundary/base-allowlist.json`の受理履歴23件をそのまま保持する。末尾は`masaki1025/pitchlog#143`。本表は候補実ファイルから機械導出した完全な射影SHA-256であり、受理済みafter値ではない。
| 資産 | 受理前識別子 → 候補識別子 | before射影SHA-256 | after射影SHA-256 |
| --- | --- | --- | --- |
| `base-allowlist.json` | `contract_revision:33` → `contract_revision:34` | `e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046` | `25aa9a11ffe99429769c831c301d211a16d1bcaf5b046856e553c1f8ffecbb16` |
| `cache-invalidation-contract.json` | `contract_revision:15` → `contract_revision:16` | `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` | `3d523972b5b192da1800e64f428a24cfb09f3a3ff52a39241cb87a6558f258df` |
| `census-baseline.json` | `contract_revision:14` → `contract_revision:15` | `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` | `2fd006e75b9e82be528ca1a4328a5643191bda3d4bcce0b52eb5b7bfcd5a2a30` |
| `db-api-inventory.json` | `inventory_revision:15` → `inventory_revision:16` | `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` | `b28bc2fa4d416a380ea225104f1e765e3020137922b79b337f419523a2a095e5` |
| `frozen-inputs.json` | `contract_revision:4` → `contract_revision:5` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | `8cba4c0e91785234ecc53e2c8e05358df4635e005341f7b50092897e0ec8d339` |
| `negative-fixtures.json` | `fixture_set_revision:17` → `fixture_set_revision:18` | `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` | `0d0c540e97e4e07b1db16fa3c811363be2d83ef8c3ffadfe24e17fba2a4ff490` |
| `repository-contract.json` | `contract_revision:21` → `contract_revision:22` | `0daf9ec4b9d5dc7eea364a0001804ba187f3bed87e02850f2da5b21613dc0e11` | `716595b4c3cd7cb937a670c860260cf2b73cd61b0992fdd11c393b7d326ab838` |
| `runtime-authz-contract.json` | `runtime_contract_revision:17` → `runtime_contract_revision:18` | `061eeb9e96f110e059ad51bf3026d9b420f7c636a24045809afa33e7a0f6b393` | `fdc2b229dd5cf8707aa8aebc6e6e8d4e7a35d6fc02538f0a893a33390f01c510` |
| `tenant-context-allowlist.json` | `contract_revision:16` → `contract_revision:17` | `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` | `9c399d870851da56bc6f6cb886e45c4a181d6f35d5073c823b45117744ad68df` |

外部snapshot対象8ファイルの完全なbefore/after SHA-256（同値も省略しない）。

| 外部ファイル | before SHA-256 | after SHA-256 |
| --- | --- | --- |
| `.github/workflows/ci.yml` | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `1fe5c648036e22addea11ba5c8c9c560c69ed3efd6b5ae98bc6d2deec4c3e5d1` |
| `scripts/check_tenant_boundary_bypass.py` | `3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883` | `3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883` |
| `scripts/frozen_archive.py` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` |
| `scripts/frozen_history.py` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` |
| `tests/domain/test_boot_seal.py` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` |
| `tests/test_census_baseline_check.py` | `163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd` | `163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd` |
| `tests/test_ci_wiring.py` | `36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396` | `2ca9c8a9d30337d0e4bf39457ef539fd410aca7fa3946b9d416ea21a2e58013b` |
| `tests/test_plan_generation.py` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` |

既存snapshotを保全したとき、after側の9射影と変更された外部2ファイルに対応して新規content-addressed snapshotが11件必要。候補名は次の通り（正式履歴へは未追加）。

- `fdc2b229dd5cf8707aa8aebc6e6e8d4e7a35d6fc02538f0a893a33390f01c510`
- `716595b4c3cd7cb937a670c860260cf2b73cd61b0992fdd11c393b7d326ab838`
- `8cba4c0e91785234ecc53e2c8e05358df4635e005341f7b50092897e0ec8d339`
- `2ca9c8a9d30337d0e4bf39457ef539fd410aca7fa3946b9d416ea21a2e58013b`
- `b28bc2fa4d416a380ea225104f1e765e3020137922b79b337f419523a2a095e5`
- `25aa9a11ffe99429769c831c301d211a16d1bcaf5b046856e553c1f8ffecbb16`
- `3d523972b5b192da1800e64f428a24cfb09f3a3ff52a39241cb87a6558f258df`
- `1fe5c648036e22addea11ba5c8c9c560c69ed3efd6b5ae98bc6d2deec4c3e5d1`
- `2fd006e75b9e82be528ca1a4328a5643191bda3d4bcce0b52eb5b7bfcd5a2a30`
- `9c399d870851da56bc6f6cb886e45c4a181d6f35d5073c823b45117744ad68df`
- `0d0c540e97e4e07b1db16fa3c811363be2d83ef8c3ffadfe24e17fba2a4ff490`

受理記録案はschema version 2、`change.aspect=[asset_snapshots,declaration,external_snapshots]`、比較元/候補識別子は上表、`change.before/after`は上表の完全射影と外部snapshot、`movement_fact`は#143後の0033・関数/ACL・CI/fixture追加、`reason`は承認済み段階Aの正式組込みとする。実PR番号に由来する`acceptance_id`・`change.subject`、承認者・承認日・正式記録SHAは取得/受理後にだけ確定する。現在は空欄のままであり、#143以前の履歴を再pinしない。比較corpus入力digestの現行pinは`b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`、候補実値は`aad2db0462f394fb2de17ae0c1ed406724e3ad5d2769e29f523503c75522d10e`。正式履歴/新規snapshotを含む最終候補で再導出し、7.7承認前に書き換えない。

**実ファイル照合（2026-10-18）**: `origin/develop=156dd139`のblobと作業木の実ファイルを`frozen_projection_content`で再計算し、上表の9資産のbefore/after射影18値と外部8ファイルのbefore/after SHA 16値がすべて一致した。比較runnerから算出した現況入力digestも上記候補値と一致する。これは候補値の整合確認であり、7.7正式受理・履歴反映・corpus再pinを意味しない。

### 10-12. 統合基線の全件検査で判明した追加ゲート

正式資産の候補登録後、root全件は68失敗/29604成功/2 skip、backendのDB非依存全件は12失敗/1945成功/4 skipだった。rootのCI配線2件はmutation jobへ段階A専用DSN宣言を1行追随して再実行で2件合格、mutation実DB2件は専用使い捨てDBで合格。新規DB試験内の64桁SHA定数は凍結走査に現れるため、ヘッダ・固定SQL本文・権限文の意味検査へ是正し、走査と関連負例16件が合格した。これらの是正後に全件を合格と読み替えない。正式7.7履歴・snapshot・corpus pin、要件claim再seal、ステップ7/8のcore-guard登録は未実施である。

次の2件は**承認済み17認可資産・配置revisionだけからは自動承認できない正式資産の追加差分**である。

| ゲート | 実際の拒否と最小の追加差分 | 必要な判断 |
| --- | --- | --- |
| migration衛生・seed許可 | `backend/tests/test_migration_hygiene.py`が`0033_stage_a_rule_defaults.py`を25件拒否する。`get_bind`経由の読取/挿入と一時`CREATE POLICY`が、現行`contracts/migrations/seed-allowlist.json`の3系列と衛生検査のどちらにも宣言されていない。固定5+5行、4一時policy、owner専用・全取消だけを対象に、新系列の宣言・受理履歴と、0033だけのSQL/実行APIを静的に検証する最小の検査契約差分が必要。既存revision全体のDML禁止は緩めない。 | seed-allowlistと衛生検査の対象限定改訂を今回の配置ゲートへ追加してよいか、7.7の実値・独立レビュー範囲とともにPOが判断する。許可前に正式台帳を更新しない。 |
| probe↔製品写像 | `contracts/authz/product/probe-product-map.json`の`product_only`へ`role:pitchlog_rule_resolution_fn_owner`と`function:FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)`の**2原子だけ**を追加すると、製品原子の双方向exact-setと負例の前提が回復する。probe側の既存写像は変更しない。 | この2行を今回の認可資産追随として承認するか、所有側の個別採否を要するか判断する。正式資産は未変更。 |

別単位の`docs/features/orm-schema-migration/acceptance-sheets`は、承認済みdata-model本文に追随する機械生成部分が古い。人間判断欄を含むため当方では上書きせず、同単位の所有側へ渡す。`contracts/authz/requirement-claims.json`の変更履歴1行の分類・lock再sealと、二つの承認済み要件`v2.15`行の版管理判断も残る。これらを無回答で受理済みとしない。

### 10-13. 0033衛生・写像の限定是正候補と追加1回レビュー

POの限定是正許可により、`0033_stage_a_rule_defaults.py`だけを候補宣言で扱う衛生検査と、probe↔製品写像のowner・関数2原子を追加した。候補宣言は`backend/tests/fixtures/stage_a/seed-allowlist-candidate.json`（SHA-256 `573ae2319cb569d548b2ff83a99ce7c6967a73bae05e040f1530477e570a1167`）へ置き、`acceptance_state=pending_7_7`を維持する。正式`contracts/migrations/seed-allowlist.json`と既存3系列の履歴はbyte不変（SHA-256 `1aa29afaa45c6649bd8958d62e442eea3ee2d2e4cbbb20cdb3061a163686fa5c`）。候補はrevision/パス、ソース全体SHA-256 `5a4b0c18fc7210e42bec77dde5cce3cd9b9788150485fe5d6d911416b9f47015`、固定5組・2表・4一時policy、INSERT対象、DB呼出と既存禁止SQL検査の違反種別/件数をexact照合する。候補宣言の正規JSON identityは`d5e302697e2a2a1bbbba05dc798b59bc3c0a618ed16a2c6fa13340279447bcbe`。正式台帳へ宣言だけを仮に重ねた候補ファイルSHA-256は`3bb4b36eaca63304daee9b448204e0e24e5f9837433fa52fdfd4223ad57c16fb`で、**正式履歴の追加・承認情報の記入ではない**。7.7-2記録案は本系列の`prior_identity={present:false,values:[]}`、`new_identity={present:true,values:[{kind:sha256_canonical_json,value:d5e302…}]}`、変更aspect=`declaration`、before=`absent`、after=候補宣言全文とし、承認者・承認日を正式受理後にだけ確定する。

写像は`role:pitchlog_rule_resolution_fn_owner`と`function:FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)`を`product_only`へ追加した。`probe-product-map.json`のファイルSHA-256はbefore `e755623b0b500ea4e2d3946d43242485e572cb0dca471785f86f08c7dabc99cd`、after `55831b271a5d81247b9a8a4ef9cb5e7a3769315984757c2fabc757fb37164602`。probe側の既存写像は不変。候補差分識別値（衛生検査・写像試験・写像JSONの`git diff` SHA-256）は`756d5f08ab65adfe6199dcf9625a055bac6d4ae5931743cd5224587a70fbb8eb`であり、別途候補fixtureの上記SHAと組みで識別する。

既定のコアレビュー2回の履歴は§10-11/§10-12どおり保持する。今回許可された追加1回の独立限定レビューでは初回P1を3件確認した。①検査器への固定値直書き、②宣言と表示パスを共に差し替えた別revisionの通過、③ソースとdigestを共に変更した任意SQLの通過。宣言由来の値、ソース内revision一致、通常scannerの違反集合・DB呼出件数・INSERT表/policy名のexact照合へ修正し、同一レビュー内で差分再確認済み。最終P0/P1/P2は0/0/0。最終レビュー後の型検査で`AnnAssign.value`の`None`絞込1行を追加し、同一レビュー枠で影響節・関連試験・tyを再確認、許可範囲不変かつ最終P0/P1/P2=0/0/0を維持した。固定候補の正例、行/policyの欠落・追加、別表/別revision、更新digest付き任意DML・余分な読取・UUID変更、写像2原子の欠落・過剰を拒否する25件が通過。正式台帳未受理のため、通常のmigration衛生試験は0033の25箇所を**意図どおり拒否**し、対象2ファイル全体は137成功/1失敗である。

**7.7・要件claimの実値**: §10-11の9資産のbefore/after射影18値、外部8ファイルのbefore/after SHA-256 16値、新規snapshot候補11件を追加差分後の実ファイルから再計算し、同節の完全表・一覧と全件一致した。比較corpus入力digestもbefore pin `b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`、after候補 `aad2db0462f394fb2de17ae0c1ed406724e3ad5d2769e29f523503c75522d10e`で不変。受理記録案は§10-11の全前後射影・外部値・snapshotをそのまま使い、正式受理ID/承認者/日付は未記入。要件claimは正式2ファイルを変更せず、承認済み要件本文`96dcb38f`を基に隔離候補を再sealして構造/decision lockを検証した。`requirement-claims.json`のファイルSHA-256は`91982af7c97eb373a99ac20730056d11a747b1233f63a3d30819a3f1748ec821`→候補`9b228dc6d86c1e4258b0cdfebfc2e7146559980ca6f163247007a21fe586a95d`、`requirement-claims.lock.json`は`3fc36dc92ff56a5f066e8e8499523458df4601ecb51fdf3f855627e9191edb50`→候補`fccfd5f9f9548a0cc3c4d69146953160027c48733c2213d02b20adec78f87b6c`。source blobは`ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`→`57f5e8f8be9946009151a4354a88176dd3ed630a`、table_rowは337→338、claim総数1417→1418、auth_claimは187で不変、lock集約digestは`2474c3e63e2b2ab2424cb0d5c237f9f48ec15ef80ca0a158372c9c5709f642b2`→候補`a250c60854007ed04179dcb84c87dc8080da77d40d0c9ada24e5e2933634d517`。新規変更履歴行は`out_of_scope/OUT_DOCUMENT_METADATA`、DRAW-03/04の本文更新は既存`out_of_scope/OUT_NON_AUTH_REQUIREMENT`を維持する案であり、正式資産の再sealと7.7受理は別ゲートである。

既存P1の現在地は次のとおり。第1回①7.7正式履歴・snapshot・corpus pinは実値表を照合済みだが**未受理**。第1回②正本/manifest実digestは是正済み、要件claimは上記候補の構造・lockを検証済みだが**正式再seal未了**。第1回③S3故障後再開は固定5組/一時policy/owner・RLS照合と拒否試験で解消済み。第2回①`frozen-inputs`のrevision 4→5とCI実SHAを§10-11の射影へ反映済み。第2回②要件claimは同じ正式再seal待ちであり、未受理を受理済みとは扱わない。今回の限定レビューP1 3件は上記の負例・外部化・型検査と再確認で解消済み。

**全件検査の完走結果（同一候補）**: rootの`uv run ruff check .`と`uv run ty check`、backendの`ruff format --check`・`ruff check`・`ty check`は合格。root `uv run pytest tests/ -q`は29,624成功/48失敗/2 skip（568.44秒）。失敗は、正式7.7履歴・snapshot・corpus・claim未受理に起因する45件、後続ステップ7/8の`stage_a_startup.py` core-guardパス登録1件、CI契約mutation件数130→134と別単位ORM受入シートの追随不足各1件に分類した。前者45件を候補検査の通過扱いにしない。

backendは専用使い捨てPostgreSQL 17を2つに分け、DB試験全59ファイルを完走した。DB非依存は1,988成功/2失敗/4 skip（272.19秒）で、失敗は正式seed台帳未登録と要件claim正式再seal待ち。DB試験の第1群は249成功/5失敗（1,064.25秒）、第2群は400成功/2失敗（1,489.67秒）。第1群の4件はworktreeの`frontend/node_modules/typescript`不足で、`pnpm install --frozen-lockfile`後に専用DBで4件通過した。第2群の環境期待値1件は最初の使い捨てDBで`POSTGRES_INITDB_ARGS`が欠けて照合不一致となり、正本の`--encoding=UTF8 --locale-provider=libc --locale=C.UTF-8`を付けた専用DBでは1件通過した。これらは環境由来で、製品不具合ではない。残るDB失敗2件は`test_operation_event_state_diff`と`test_operation_event_c12`が旧revisionでの往復中に現在のAlembic headを要求する`current(check_heads=True)`を呼ぶ整合不一致であり、0033専用衛生・写像の今回是正範囲外として該当所有側の追随対象にする。rootのCI mutation件数とORMシートも同様に未解消とする。環境是正後の限定再実行は行ったが、全件の成功と読み替えず、不要な全件反復はしない。

**正式受理へ出す値**: 7.7の9資産18射影、外部8ファイル16 SHA、新規snapshot11件、corpus前後、記録案は§10-11の完全表・一覧と一致し、今回の衛生・写像是正による値の増減はない。これに加え、上記0033 seed候補宣言とprobe↔製品写像2原子の前後値、および要件claim/lockの隔離再seal値を同時に提示する。既存#143までの受理履歴とbefore値は保持した。正式7.7受理情報、未受理seed宣言、claim/lock、snapshot、corpus pinを正本へ記入していない。正式受理・後続パス登録・別単位の整合是正まではステップ3完了ではなく、既存DB適用・試合作成公開・push/PR・人間逐行確認・マージへ進まない。

### 10-14. 全件の残差に対する最小追随候補と7.7差分固定

本節は§10-13後の候補差分であり、既定2回・追加1回の独立レビューの対象には含めない。旧revision往復2件は、0022/0026の制約と往復を検証したあと0032への復帰を`alembic_version`の実値と配置前metadata差分0で確認するよう是正した。0033を無条件に適用したり、旧revisionで`check_heads=True`/`command.check`を通す形にはしない。現行HEADへの復帰・認可・配置・非公開は別の正式S0→S3試験`test_formal_stage_a_startup_preserves_closed_publication`で確認し、影響3件が専用隔離DBで合格した。CIの全葉変異は基線65葉に`backend.env.PITCHLOG_STAGE_A_OWNER_DSN`と`mutation.env.PITCHLOG_STAGE_A_OWNER_DSN`の2葉が増えたため、値/削除各1回の期待数を130→134へ追随。全134変異の拒否試験は合格した。

| 初回backend全件での失敗群 | 件数 | 限定再試験と現在地 |
| --- | ---: | --- |
| DB非依存: 0033衛生・正式seed台帳 | 1 | 候補宣言25件は合格。正式台帳未受理の通常試験は引き続き拒否し、7.7待ち。 |
| DB非依存: 要件claim/lock | 1 | 隔離再seal候補の構造/lock照合済み。正式2資産を未変更とし、受理・反映待ち。 |
| DB: Node/TypeScript依存欠落 | 4 | このworktreeの依存を`pnpm install --frozen-lockfile`で整え、専用DBで4件合格。 |
| DB: 使い捨てDBのlocale不一致 | 1 | 正本の`POSTGRES_INITDB_ARGS`で専用DBを作り直し、1件合格。 |
| DB: 旧revision往復/HEAD混同 | 2 | 旧revision時点の検査と正式HEAD側の段階起動検査を分離し、影響3件合格。 |

この表のDB非依存2件とDB7件は**9件の異なる失敗**であり、環境是正や再試験を追加の失敗に数えない。rootのCI件数1件は別母集団で解消、ORMシート1件とステップ7/8のcore-guardパス登録1件は別ゲートで残る。`backend/src/pitchlog/db/stage_a_startup.py`は新規パスで、計画のステップ7で既存`test_rule_resolution.py`とともに`AREA_PATH_ADDITIONS`・guard試験へ宣言し、ステップ8の**別コミット**でJSONへ登録する最小追随案とする。6.3の意味境界ではtenant-isolationとgame-stateの重複帰属を候補とし、具体的登録は当該ステップの敵対レビュー・人間確認へ残す。共有guardファイルをステップ3から先取り変更しない。

ORMシートは所有側の現行ファイルを変更せず、生成候補を`/tmp/tsk550-orm-sheet-candidate/`へ隔離した。正本からの生成結果と人間欄を除く全文が一致し、既存のN1=103、N3=105、N4=55、N7=100行の判定・理由をすべて保持できることを1対1の語・節/版・実装側照合で確認した。新たな人間判断はN3の出現001（§変更履歴 v1.0 の「不変」）、出現061（§6-5の6-key不変snapshot）、出現086（§10-5の出所証明で「昇格させない」）、N7の候補094（§10-5のロック保持）の**4行だけ**。候補の`judgment_errors`は未判定3+1のみである。候補SHA-256はN1=`ecf7d1d221e4ed5392fcfce68ceb878ba7f47f4f20738a346fc7ddacef7eb767`、N3=`28fbb838ce5e680c9fa1f1fee3df216c752059ef5b5e65c6f1866916281b6322`、N4=`6a9ccb96eaf85f9ac2cfbbc1193a3d329eb09d37682fed18f99dd1ffe31e66a6`、N7=`9b3030aa0c52940bf4653e7cb2848c6ee748aeabf4c71c11c9b14137e5dc1f44`、README=`e66dceed63b7238f7964abe5fa18a83d55f4815cab9fd010e1ca1d551edd2484`。この4行の判定・理由はTSK-550が代記せず、ORM単位の所有側へ渡す。

CI試験追随は凍結外部ファイルに当たり、§10-11のafter値が**外部1件**`tests/test_ci_wiring.py`: `7a01bc23aef19549ecdb1d3afd2db2a1f5dae961a39b59a5bee4659b7bb9b995`→`2ca9c8a9d30337d0e4bf39457ef539fd410aca7fa3946b9d416ea21a2e58013b`、**射影1件**`frozen-inputs.json`: `2fb8fe81448fff6b11f5b014489225ca49407570f80e4b7251bdabcdffb5f28e`→`8cba4c0e91785234ecc53e2c8e05358df4635e005341f7b50092897e0ec8d339`へ変わった。before値、他8射影、他7外部、seed宣言identity、probe写像、要件claim候補、corpus入力digest `aad2db0462f394fb2de17ae0c1ed406724e3ad5d2769e29f523503c75522d10e`は不変。§10-11の完全な9資産/8外部の前後表とsnapshot11件はこの実値へ更新した。

完全な未受理記録案（旧#149ブランチに保全、未移植）は、比較元`origin/develop=156dd139a893845428a1ecab69632143f7694e0b`と既存受理履歴23件（末尾#143）を前提とし、9資産の宣言・movement policy・完全射影、外部8ファイル、seed宣言、probe写像、claim候補、corpusを一つのJSONへ収める。ファイルSHA-256=`79b307874aff8fdaaba35f73811a0fcb34e1d10f030da78d5caa478a046eead1`。PR番号から決まる`acceptance_id`/`change.subject`、承認者・承認日は`null`であり、正式7.7記録としては**未成立**。対象treeの識別値は本候補のファイルを含む作業木から別途固定する。7.7正式受理後にのみ、承認された値で履歴追記・新snapshot・corpus再pin・seed正式宣言/履歴・claim/lock反映を行う。その後、root/backend全件と比較corpus/基線/guardを再検査し、ステップ単位のコミット、通常pushと新HEADのCIを確認する。受理実値が変われば差分を再提示する。ORMの4行判定とステップ7/8登録は別条件として残し、受理だけで試合作成を公開しない。

## 10-15. 7.7正式受理後の反映（2026-10-18）

PO山田正輝は比較元`156dd139a893845428a1ecab69632143f7694e0b`、候補tree`b54af61047e099b47d9e276fa6e3ac011070e362`、本書§10-14の記録案SHA-256`79b307874aff8fdaaba35f73811a0fcb34e1d10f030da78d5caa478a046eead1`を正式7.7実値として受理した。Draft PR #149の実件名は`feat: TSK-550 段階A規則解決を追加`。`base-allowlist.json`の既受理履歴23件・before値を保持し、#149を新しい24件目にする。seed宣言と履歴、snapshot11件、corpus、要件claim/lockの反映は受理済み候補値との照合を要する。

正式反映後の試験が必要とするcandidate fixtureから正式seed台帳への追随は、固定5組・一時policy4件と範囲外拒否を維持する。後発差分は独立再レビュー未実施であり、既済みレビューの結果に読み替えない。ORM N3三行・N7一行の判定は所有側の本人欄を空欄に保つ。core-guardの宣言と登録は計画ステップ7・8の別コミットへ残す。既存DBへの適用・試合作成の公開・人間逐行確認・Draft解除・マージは未実施。
