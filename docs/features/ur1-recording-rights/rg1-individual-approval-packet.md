# U-R1 新ステップ2: RG1専用資産の個別承認資料

2026-10-15。**審査候補であり、DDL・製品コード・凍結資産の変更承認ではない。** 基線は `origin/develop` `e6e1a867`、U-R1の文書固定コミットは`30ffaa71`。A統合後に実revision・digest・7.7のbefore/afterを計算し、この資料の旧試算値は承認値に使わない。

## 1. 確定した範囲とTSK-550の実際の承認状態

- POが承認したRG1物理方式は、単一状態行、通常テナントによる更新の禁止、制限関数境界、起動時既定閉鎖。新2に製品の`open`・解除を含めない。U-S1の③-a/⑧ Port署名・位置・同一scopeの固定関数口は担当のコミット済み計画8節で回答済み。Port実接合と実経路結合試験はU-R1新6、D4発行源・復旧世代は別ゲート。
- TSK-550本体の承認済み計画は`feature/ux1-fr014-rule-resolution`の`plan.md`（HEAD `ae380801`で確認）。承認記録は2026-10-14の`a2b8a5b5`追補と`e19f8651`開始条件追補などで、**最初の製品登録は段階A resolver 1件**。共有実行器だけを登録0件で先行する計画はまだ承認されていない。
- TSK-550担当は`shared-function-executor-split-proposal.md`と作業ログ（同HEAD `ae380801`）で、A＝共有実行器・製品登録0件、B＝段階A resolver 1件、C＝U-R1のRG1 2件を**条件付き提案**した。独立レビューは第1回P0=0/P1=5（全採用）、第2回P0/P1/P2=0。レビュー通過は正式追補・PO承認・資産受理を代替しない。
- U-R1の旧[追補案](shared-function-executor-addendum-proposal.md)は「Aにresolverまで含む」案で、TSK-550の後発A＝0件案と異なる。**U-R1はA＝0件を接続可能な候補として採用**する。ただしAの計画追補がPO承認され、必要なコアレビュー・個別資産ゲートを通りdevelopへ統合されるまで依存成立とはしない。現行の初回登録順を保つなら統合順はA→B→C。A→C→Bを許すには、初回登録順の明示的なPO改訂と両担当の計画・受理記録への反映が必要で、今は認めない。Bの全機能完成をCの実行時依存とはしない。

## 2. 新ステップ2で増やす集合（承認候補）

| 所有・対象 | 現在 → 候補の差分 | 限界・拒否条件 |
| --- | --- | --- |
| U-R1の固定登録 | Aの共有`FunctionOperationRegistration`/`_TenantTransaction.run_function`/固定registryを再利用。U-R1から`RG1PrecheckToken`・`RG1CommitCheckToken`の**2型・2 ID**（候補`RG1:precheck`、`RG1:commit_check`）だけ追加 | frozen/slotsのexact token、業務引数・関数名・SQL・bind・decoderのcaller注入なし。未登録・偽造・失効scope・DML ID衝突・任意SQL/Sessionを拒否。既存DML実行器を緩めない |
| SQL登録 | `SELECT rg1_api.rg1_read_open() AS is_open`と`SELECT rg1_api.rg1_assert_open_before_commit() AS is_open`の固定2文。bindなし、戻りは1行・`is_open`がexact bool | 0/複数行、NULL、型違い、関数例外、tenant文脈不明は成功にしない。repositoryの共有実行器が実行直前の文脈を照合。DB関数の直呼出しは別に検査 |
| 永続表 | なし → `public.rg1_restore_gate(singleton_id smallint PRIMARY KEY CHECK(singleton_id=1), state text NOT NULL CHECK(state IN ('closed','open')))`。AlembicはDDLと1行`(1,'closed')`のseedを担当。policy/ACL/`ENABLE`＋`FORCE ROW LEVEL SECURITY`は既存の製品認可適用器を唯一の適用元とする候補 | appの表`SELECT/INSERT/UPDATE/DELETE/TRUNCATE`を全拒否。通常経路は物理削除しない。行欠損・不正状態・行数異常はfail-closed。seedの再実行は既存状態を自動openにしない。migration後・認可適用前や適用失敗時も公開ゲートを閉じ、実カタログ合致まで通常書込みを許さない |
| 関数schemaとowner | `authz_private`はappのUSAGE拒否を維持。新候補`rg1_api`を`pitchlog_owner`所有で追加し、appに`USAGE`だけを付与。RG1専用`pitchlog_rg1_fn_owner`（`NOLOGIN`・`NOSUPERUSER`・`NOBYPASSRLS`・`NOCREATEDB`・`NOCREATEROLE`・`NOREPLICATION`・`NOINHERIT`）を追加し、既存管理ownerを流用しない | appにschema`CREATE`なし、PUBLICのUSAGE/CREATEなし。関数ownerには他の製品表/関数権限・ロール所属を与えない。role総数・分類の正本3-2改訂が必要 |
| 表ACL/RLS | 表ownerは既存`pitchlog_owner`。`pitchlog_rg1_fn_owner`へ表schemaのUSAGE、表の`SELECT(singleton_id,state)`と**`UPDATE(singleton_id)`だけ**付与。owner向けに`SELECT USING(singleton_id=1)`と`UPDATE USING(singleton_id=1) WITH CHECK(singleton_id=1)`の2 policyを置く | PostgreSQLの`SELECT ... FOR SHARE`は1列以上のUPDATE権とUPDATE policyも使う。`state`のUPDATE権は与えない。関数ownerはNOLOGIN、appはこのroleを継承しない。INSERT/DELETE policyなし、PUBLIC/app/他ownerのpolicyなし。`FORCE RLS`を維持し、実DBの実効ACL・policy集合をexact照合 |
| 読取関数 | `rg1_api.rg1_read_open()`は非ロック読取、`rg1_api.rg1_assert_open_before_commit()`は同じ1行を厳密な`FOR SHARE`でロックしscope終端まで保持。両方`SECURITY DEFINER`、固定search_path、完全修飾表名。作成と同一transactionで`PUBLIC EXECUTE`を剥奪しappへこの2件だけ`EXECUTE` | 関数内でもtenant GUCの欠損/不正を拒否。ただしappが直接SQLでGUCを設定できるなら認証済みの根拠とは扱わない。appの直接EXECUTEも想定し、任意行・任意関数へ到達しないこととlock待機の上限を実DBで検査。復元開始UPDATE関数は**新2では作らない** |
| 起動・再接続閉鎖 | 新2の製品用2関数は状態行を照合・必要なロックを取得した後も、**常に`false`を返す**候補とする。`open`状態の古いsnapshotを直接EXECUTEしても成功にしない。通常書込みはB7、P3はB10へ写して全取消 | 新2には安全なopen証明源・解除機能がないため、DBの`state='open'`だけで通過させない。正常open時のロック競合は隔離DBの試験用fixtureで再現し、製品の成功経路としない。新5でD4・復旧世代と不可分な解除契約を別承認する |

**ロックとRLSの根拠**: PostgreSQL 17の[SELECT](https://www.postgresql.org/docs/17/sql-select.html)は`FOR SHARE`にUPDATE権を要求し、[CREATE POLICY](https://www.postgresql.org/docs/17/sql-createpolicy.html)はUPDATE policyが`SELECT FOR SHARE`にも適用されると定める。[行ロック表](https://www.postgresql.org/docs/17/explicit-locking.html)では`FOR SHARE`が復元側のキー不変UPDATE（`FOR NO KEY UPDATE`）と衝突する。`FOR KEY SHARE`へ弱めない。`BYPASSRLS`ロールは`FORCE RLS`も迂回するため、専用ownerには付与しない（[RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)）。

**候補policyの形**（実DDLは認可適用器の唯一の生成・適用元に従い、現時点では実行しない）:

```sql
CREATE POLICY rg1_fn_select_singleton ON public.rg1_restore_gate
    FOR SELECT TO pitchlog_rg1_fn_owner USING (singleton_id = 1);
CREATE POLICY rg1_fn_lock_singleton ON public.rg1_restore_gate
    FOR UPDATE TO pitchlog_rg1_fn_owner
    USING (singleton_id = 1) WITH CHECK (singleton_id = 1);
GRANT SELECT (singleton_id, state), UPDATE (singleton_id)
    ON public.rg1_restore_gate TO pitchlog_rg1_fn_owner;
```

`SELECT FOR SHARE`がこの列ACLと2 policyで通るか、`UPDATE state`・INSERT・DELETEが拒否されるかをPostgreSQL 17実DBで確認する。実測に反すればDDLを独断で広げず、修正差分を認可担当とPOへ戻す。

## 3. 変更資産の境界と検査

| 資産群 | 新2の候補差分 | 先行条件・検査 |
| --- | --- | --- |
| DB・認可 | U-R1専用migration/ORM状態行、`data-model.md`§3-2と非テナント`function_only`1表の正本追補、`table-classification.json`・露出事実、`ddl-elements.json`/function-bodies/manifest、role/schema/table ACL/2 policy/2関数、認可適用器・catalog exact-set | 既存`classification.py`は非テナントを`global_read_only`に固定し、`FUNCTION_OWNER_UNITS`にU-R1がない。表1件だけの例外と負例を正本7.6で確定。正本の規範・role数変更は必要な7.3敵対レビューと人間承認を通す。authz_privateと既存表・既存関数のACLは不変 |
| repository凍結 | Aの共有登録欄にRG1 2型・2 ID・関数identity/固定SQLだけを追加。`pitchlog.repositories.rg1._build_rg1_read_statement`（候補`kind: Literal['precheck','commit_check']`）の許可は`SQLA_SELECT`だけ。正例fixtureは2 kindだけ、未知kind/任意関数/余計なbindは拒否 | 共有欄の形式と関数ID識別値はA統合済み契約を正とする。`repository-contract.json`、生成物、`base-allowlist.json`、テナント境界試験をU-R1差分のみ審査。Aの実行器や既存allowlist symbolの権限を拡大しない |
| 派生・7.7 | schema manifestとcanonical digest、runtime authz、派生lock・oracleのうち実入力が変わるもの、archive、単一未マージPRの受理記録 | A統合後の最新developをbeforeにし、実revision/digest・入力blob・movement_fact・reasonを算出して**正式反映前に別提示**。history authorityはbase-allowlist。既受理履歴、before側、PR #72のPENDING_ACCEPTANCEを保持。中間コミットを受理済み最終headにしない |

**DB/認可の検査表**: (1) 通常appの表4操作と`SET ROLE`/直接schema CREATE拒否、2関数以外のEXECUTE拒否、PUBLIC実効EXECUTEなし。(2) `FORCE RLS`/owner属性/列ACL/SELECT+UPDATE policyの実カタログexact-set、余剰policyの合成拒否。(3) 関数内の欠損・不正tenant GUC、行欠損・`open`古行、直接EXECUTEで`true`にならないこと。(4) 復元先行と通常側先行の2接続、`FOR KEY SHARE`負例、直接EXECUTEを含む3接続の待機・timeoutと全取消。(5) A固定実行器の2登録・unknown kind/偽造token/失効scope/SQL束縛値、既存DML非緩和。新6の実Port/HTTP結合試験はこの表に含めない。

**承認済み新2ステップ表との整合確認**: 現行計画の新2は「隔離状態で正常系を検証」と記す。一方、本候補の製品関数は安全な開放源がない間は常にfalseで、製品operationの`true`成功試験を新2へ置けない。新2の隔離試験は**同じRG1行への`FOR SHARE`取得・復元UPDATE待機・全取消と、欠損/古いopenの拒否**に限定する。復元開始側UPDATEは隔離試験の特権接続だけで発行し、製品の復元開始関数は新5。製品の正常open成功も新5の安全な解除実装後へ移す最小計画追補が必要。承認済みステップの合格条件を本資料だけで変更しない。6.1/6.3のコア計画差分レビューと人間承認を新2着手前のゲートとする。

## 4. 個別承認の順序

1. TSK-550担当がA＝0件案を正式計画追補へ反映し、6.1/6.3のコア計画レビューとPO承認、共有実行器A自体の正本・認可・凍結個別ゲートを通す。現行受理文を維持する場合はA→B→C。順序を変える場合はPOの明示改訂を先に記録する。
2. U-R1/認可面/データモデル所有側が本資料の1表・2関数・専用owner・RLS/ACL・常閉を項目別に審査し、必要な7.6/7.3と人間の個別承認を得る。特に`UPDATE(singleton_id)`＋UPDATE policyの最小性、app直接EXECUTE、通常側・復元側の待機上限は承認対象。
3. A統合後の実基線で完全なSQL/JSON、revision/digest、7.7のbefore/after、PR番号と未マージ記録を提示する。**実値の受理まで正式台帳を変更しない**。承認範囲が変われば差分を再審査する。

新2の製品コード・資産変更は上記ゲート後だけ。新2単独では本番通常書込みは停止したままであり、U-G1の作成成功を宣言しない。D4方式・新5の安全な解除は別ゲート、U-R1の実経路結合試験は新6。
