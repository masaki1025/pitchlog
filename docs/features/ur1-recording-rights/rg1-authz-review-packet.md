# RG1限定関数の認可差分審査資料

2026-10-15。**候補。正本・製品コード・認可/凍結資産は未変更**。RG1物理方式（単一行、通常テナントの更新禁止、制限関数、起動時既定閉鎖）のPO承認だけを根拠とし、個別DDL/認可承認とは区別する。U-R1新ステップ2に製品open/解除とU-S1 Port実接合は含めない。

## 現行の制約

- `contracts/authz/product/ddl-elements.json` の `authz_private` は `pitchlog_app` の `USAGE` を明示的に拒否する。したがって同schemaに `rg1_*` 関数を置き `EXECUTE` だけ付与する旧候補は動かない。既存schemaのUSAGEを開けると他関数の名前解決面も広がるため採らない。
- `data-model.md` 3-2は製品ロールを6区分とし、管理関数所有ロールは `NOLOGIN` + `BYPASSRLS`。RG1専用ロールの新設は正本改訂を要する。現行の `non_tenant` 事実は `global_read_only` に、`function_only` は特別露出事実にしか分類できない。RG1を登録するにはRG1単独の例外事実と検査を7.6で確定する必要がある。
- アプリロールへ関数 `EXECUTE` を与えるとDB直接呼出しも可能で、Pythonの `run_function` 検査を通らない。tenant GUCは接続経路の整合確認には使えるが、appロールが直接SQLを実行できる場合の偽造不能な認証根拠とは扱わない。

## 認可担当への最小候補（採否待ち）

| 要素 | before → after の候補 | 拒否/検査 |
| --- | --- | --- |
| 表・分類 | 表なし → `public.rg1_restore_gate(singleton_id smallint PRIMARY KEY CHECK(singleton_id=1), state text NOT NULL CHECK(state IN ('closed','open')))`、ちょうど1行をmigrationで`closed`にseed。`ENABLE` + `FORCE RLS`。`table-classification.json`は**この1表だけ**`function_only`、owner_unit `U-R1`、非テナント制御資源の特別露出事実を新たに正本で定義 | appロールの表SELECT/INSERT/UPDATE/DELETEなし。欠損・未知状態・複数行を失敗。物理DELETEなし。seedとRLS適用の順はmigration審査で固定 |
| 関数schema | 既存`authz_private`は不変 → 候補`rg1_api`を追加し、`pitchlog_app`に`USAGE`のみ、`CREATE`なし。`PUBLIC`のUSAGE/CREATEを拒否 | 既存`authz_private`のapp USAGE拒否を維持。別schema内の登録外関数をappへ公開しない |
| owner | **修正候補**はRG1だけを所有する専用`NOLOGIN` owner。既存`pitchlog_management_fn_owner`の再利用案は認証管理権限を持ち過ぎるため撤回。RG1表を置くschemaへの`USAGE`と、必要列への`SELECT`、`FOR SHARE`側の最低1列`UPDATE`権、`FORCE RLS`下の実行権をexact-setで定義する | 新roleとロール総数の正本3-2改訂、BYPASSRLSの要否とRLS policyを7.6/7.3で審査。表schemaのUSAGE漏れをDB試験で拒否/成功両方確認。RG1以外の表ACL・既存関数ownerは不変 |
| 読取関数2件 | 候補`rg1_api.rg1_read_open()` / `rg1_api.rg1_assert_open_before_commit()`。固定SQL、`SECURITY DEFINER`、固定search_path `pg_catalog,pg_temp`、RG1専用owner。前者はsingleton非ロック読取、後者は同じ1行 `FOR SHARE` をtransaction終了まで保持。作成と同一transactionで`PUBLIC EXECUTE`を剥奪し、`pitchlog_app EXECUTE`をこの2件だけ付与 | DB関数内で行の存在・状態を検証し、欠損/不正GUC/DB例外を拒否。app直呼出しを含め実効ACLをexact-set検査。app接続のtransaction寿命・復元側のlock_timeout/再試行の上限と障害時閉鎖動作は認可・運用担当の具体決定待ち。直接EXECUTEを含む3接続競合試験を要求 |
| 復元開始 | 新2の製品DDLに復元開始関数を作らない。新5で復旧制御面の主体・専用schema・関数owner・EXECUTEを別承認する。新2の隔離DB競合試験だけで特権試験接続からRG1行をUPDATEする | 旧候補`rg1_api.rg1_begin_restore()`は撤回。関数を新5で作る時も作成transaction内で`PUBLIC EXECUTE`を剥奪し、appを含む実効ACLをexact-set検査。通常appの直接UPDATE/DELETEを拒否 |
| 起動時 | 新2の製品operationは起動/再接続時の許可を常に閉とし、復元された古い`open`行だけで開放しない。**強制点の具体実装は未決** | 古い`open`、再起動、再接続、appの直接EXECUTEで開放されない負例が新2の合格条件。隔離DBのopen行で`FOR SHARE`競合を検証する手順と、製品の常閉条件を混同しない。解除と新D4開始は新5の別承認 |

**認可担当へ求める判断**: (1) RG1専用ownerのrole定義・表schema USAGE・列ACL・`FORCE RLS`との組合せ。(2) `rg1_api`のapp USAGEと読取2関数だけのEXECUTE、PUBLICからの剥奪と実効ACL exact-set。(3) 非テナント`function_only`1表だけの新事実、owner集合、`non_tenant`規則との関係、正例・負例、正本3-2の7.6/7.3担当。(4) seed→RLS/ACL適用順、起動時の古いopen行を閉じる強制点と主体、app transaction寿命・復元lock_timeout/再試行の具体上限と失敗時動作。**これらはP1未解決の判断事項**。回答前に資産を変更しない。

**実revision/digest/7.7**: TSK-550共有実行器の統合後の`origin/develop`を比較元に、repository-contract、base-allowlist、runtime-authz、製品DDL/manifest、派生lock/oracleの実差分を算出する。受理済み履歴とbefore側を維持し、実PR番号で単一未マージ記録のafter側を作る。方式・接続面の受理を7.7の実値受理へ読み替えない。
