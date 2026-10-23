# TSK-550 段階A・正本2ゲートと認可資産の判断用本文

**後続の射程訂正**: §Aの「§3-2/§6-5/§10-5を一体審査」は[最小追補](step-gates-minimal-addendum-proposal.md)の承認対象として分割する。ステップ2前は[§6-5保存本文だけ](step2-storage-canonical-gate-proposal.md)、owner/§3-2・出所/§10-5と認可/配置はステップ3前。この文書の旧一体案は現在の審査射程ではない。

**審査状態（2026-10-14）**: 本案だけの予備敵対レビューはP0=0/P1=6/P2=2で否決。正本全文を`in-review`にした7.3正式第1周ではない。認可面の正本配置、専用owner追加時の6ロール記述、親ロック後の割当照会の可視性などを修正対象とする。並行ブランチ`feature/tsk550-step1-gate-materials`の`007631c3`はPO採用値と異なるUUID・文字列を含むため、TSK-550コメント`3f993b75-e687-8113-acc0-001df7db0182`で正式ゲートへ出さないよう通知した。別owner案、親行だけのロック案、downgrade物理DELETE案は本書の最終提案へ採否を統合する。所有者の採否後に正本ファイル・版・全文を一意にし、正式7.3へ進める。

2026-10-14。POは[5つの固定UUIDと2つの機械文字列](step1-final-diff-review.md#3-付録f-2の配置差分と停止規律)を採用した。付録F-2の値・意味は変えない。以下は**所有者が正式7.3ゲートへ載せるための差分案**であり、正本、migration、ACL、凍結基準の承認済み本文ではない。TSK-550承認済み計画・Codex Dの閉鎖モデル/4失敗、固定function operationのPO代替受理は維持する。

## A. data-model独立7.3単位

対象は`docs/design/data-model.md`の**次版候補v1.0**、§3-2の専用owner行と6ロールの見出し・本文・総数、§6-5、§10-5、変更履歴。現行v0.9のTSK-543/B06、要件書F-2、ADR-003、物理列集合は変更しない。現行TSK-550計画の影響正本欄は§6-5/10-5だけを挙げるため、§3-2を足す最小追補とレビュー要否を**正本ゲート開始前**に判断する。所有者は変更履歴へ「本書で確定する範囲 = 段階Aの保存形・出所・旧行拒否・大会割当あり拒否・専用ownerの責務境界。実装時に確定する範囲 = codec/関数/migration/ACL/2接続試験/旧行の画面表示」を記し、`in-review`化と7.3適用版・条文SHAを同じゲート記録に残す。

**§3-2への正式本文候補（専用owner案）**: 現行「6ロール」を「7ロール」とし、用途別3関数ownerを4関数ownerへ更新する。表にも次の1行を追加する。

> 規則解決関数所有用ロールは`NOLOGIN`と`BYPASSRLS`を持ち、FR-014段階Aの全体既定を読む固定`SECURITY DEFINER`関数1件に限って使用する。管理者専用関数所有ロールと分け、アプリ用ロールとのmembershipを持たせない。参照列と行ロックに必要な列UPDATEだけを個別資産で付与し、関数本文にDMLを置かない。テナントの絞り込みは関数本体のGUC/親大会照合で行い、GUCの真正性をDB関数だけで証明したとは扱わない。

**§6-5への正式本文候補**:

> 段階Aで新規作成する試合の`games.applied_rules`は、既存JSONBの同一top-level objectに`ruleSetId`（正規の小文字・ハイフン付きUUID文字列）と、既存`contracts/state-transition/game_end_contract_schema_v1.json#/$defs/ruleSnapshot`に定義された`regulationInnings`、`coldConditions`、`extensionLimit`、`tiebreak`、`dh`の5値を、余分なキーなしで保存する。5値だけを既存schemaへ投影して検証し、IDは別途UUIDとして検証する。値は同一transactionで1つの`rule_sets`行から読んだスナップショットであり、後日のマスタ変更を既存試合へ遡及させない。ID専用ゲーム列を増やさず、計算/変換の複製を作らない。旧`{}`、5値だけ、未知キー、不正ID・値、出所不明の試合行を新しい解決済み値へ推定補完しない。

**§10-5への正式本文候補**:

> 段階Aの試合区分既定は、出所が付録F-2として確認できる`game_type_rule_defaults.game_type_key → rule_sets.id`の対応に限る。規則表への製品直接書込と大会割当書込の入口は閉じる。対象大会に割当行がある場合、全体既定へフォールバックせず段階A対象外として拒否する。保存する規則IDと5値は同一成功境界で確定し、解決失敗時は試合行も残さない。段階Aでは`rule_sets`帰属列、既存試合の推定移行、段階Bの大会/試合上書き解決を導入しない。

**受理を求める差分**: data-model所有者が§6-5/§10-5の意味、旧行の不補完、現行v0.9との非衝突を採否する。U-G1は同一`tenant_transaction_scope`でresolver→単一codec→game INSERT→RG1直前ゲート→commit/全取消を採否する。これらはF-2値の再裁定ではない。7.3本文の承認後に本feature PRへ取り込み、`docs/README.md`とmanifestの正本digestは承認後の実値で追随する。

## B. 認可面独立7.3単位

候補本文の参照元は`docs/features/product-authz-surface/design.md` §1-6だが、同書は7.2上**正本ではない**。認可面所有者は、認可規範を収録する`docs/design/`の正本ファイル（既存正本の別審査節か新設正本）を一意に指名し、状態・版・変更履歴・`docs/README.md`索引の扱いを確定してから7.3へ移す。data-modelの保存形ゲートとは審査対象・採否を混ぜない。

**§1-6への正式本文候補**:

> FR-014段階Aでは、試合区分の全体既定を読む`public.resolve_stage_a_rule(text,text,boolean)`相当の固定制限関数1件を、認証済みの同一tenant transaction scopeからのみ呼ぶ。入力は試合区分キー、必須大会キー、上書き有無であり、呼出側の任意tenant IDや規則IDを受けない。大会親行をtenant GUCと照合してロックし、同じtenant/大会の割当有無を調べ、割当があれば既定へフォールバックせず拒否する。親不存在・無効、大会越境、既定欠損、値不正、読取故障は受理済みの失敗へ分類し、非成功から試合INSERTへ進まない。`rule_sets`と`tournament_rule_assignments`への`pitchlog_app`直接SELECT/書込は開かず、`game_type_rule_defaults`の既存SELECTだけを保持する。大会割当/管理書込関数は本段階で追加しない。

> 関数は`SECURITY DEFINER`かつ`VOLATILE`、`SET search_path = pg_catalog, pg_temp`、全表参照をschema修飾、関数作成と同一transactionでPUBLICの既定EXECUTEを剥奪し`pitchlog_app`へ当該関数だけ付与する。READ COMMITTEDを要求し、親行ロックと割当照会を別SQL文に分け、待機後の新しいスナップショットで割当を確認する。他の分離レベルでは成功させない。GUCの存在・UUID形式・要求大会のtenant一致は関数で検査する。`app.tenant_id`は接続から設定可能なGUCであるため、**この検査だけでGUC偽装を防ぐとは扱わない**。通常製品経路のtenant真正性は認証済み`TenantContext`発行、固定function operation、DB接続資格情報の非公開と直SQL不可の運用境界に依存する。`pitchlog_app`接続そのものを取得した主体による任意GUC設定は残余脅威として明示し、その採否は認可面/tenant境界所有者とPOが行う。

現行data-model §3-2は`pitchlog_management_fn_owner`を**管理者専用**とする。通常の試合作成から呼ぶ本関数を同ownerに載せる案は責務を広げる。**最終提案は専用`pitchlog_rule_resolution_fn_owner`（NOLOGIN・BYPASSRLS・非継承・membershipなし）を新設**し、後述の限定列ACLだけを与える案。専用owner採用時は上記data-model §3-2も同じ独立ゲートの射程へ足す。既存shared owner案はFR-041共有機能と規則解決の権限を同一主体へ合流させるため不採用、既存management owner案は「管理者専用」の責務に反するため不採用。専用ownerの正式採用は§3-2の7.3と個別DDL/ACLゲートによる。

## C. 個別認可・配置ゲートに提示するexact差分

この節は**正本7.3承認とは別の、具体的資産変更の個別判断**である。`contracts/authz/product/`、`contracts/tenant_boundary/`、migration、カタログ検査を変える許可はまだない。採用するownerロール/列/ポリシーをこの表から選び、審査記録に固定する。

| 対象 | 推奨する許可・拒否の差分 | 根拠/検証 |
| --- | --- | --- |
| ownerロール | `pitchlog_rule_resolution_fn_owner`: `NOLOGIN BYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT`、`membership_edges=[]`を維持。`public`は`USAGE`だけ、`CREATE`なし | 既存管理ownerの責務を広げない。外部特権適用器が1 transactionでロール/関数を作成し、関数ownerとアプリのmembershipがないことをカタログ照合 |
| `tenant_vocabularies` | ownerに`SELECT(tenant_id,key,category,disabled)`、行ロックのため`UPDATE(disabled)`だけ | 大会親行を`FOR UPDATE`。`pitchlog_app`既存ACL/RLSは不変 |
| `tournament_rule_assignments` | ownerに`SELECT(tenant_id,tournament_key)`だけ、UPDATEなし | 割当有無は通常SELECT。製品書込入口は閉じ、特権書込は保守停止。割当INSERTと親FKロックの競合は実装後2接続で証明 |
| `game_type_rule_defaults` | ownerに`SELECT(game_type_key,game_type_category,rule_set_id)`、UPDATEなし | 既定行は通常SELECT。製品書込入口を閉じ、変更は保守停止下の特権migrationに限る。appの既存SELECTを維持 |
| `rule_sets` | ownerに`SELECT(id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh)`、UPDATEなし | 規則行は通常SELECT。製品書込入口を閉じ、変更は保守停止下の特権migrationに限る |
| 関数 | `public.resolve_stage_a_rule(text,text,boolean)`1件のみ。ownerは上記専用ロール、`SECURITY DEFINER`、固定search_path・schema修飾。`REVOKE ALL ... FROM PUBLIC`と`GRANT EXECUTE ... TO pitchlog_app`を作成と同一transactionで適用 | appからの直表SELECT/書込拒否、未知関数/任意SQL拒否、戻りdecoder・GUC不正/越境拒否を資産と実DBで照合。関数本文にDML/SET/commitなし |

PostgreSQLでは行ロック付きSELECTに対象表の少なくとも1列のUPDATE権限が要る。段階Aの最終提案は**親大会だけ`FOR UPDATE`し、既定・規則行は通常SELECT**とする。閉鎖中の既定・規則の変更は保守停止下の特権migrationだけに制限し、製品書込入口を開く変更ではロック範囲を別契約・2接続試験で再設計する。親表の`UPDATE(disabled)`は実際の更新権限でもあるため、NOLOGIN/membershipなし・固定読取関数の本文検査・appへの直権限不付与を同時に審査する。

### F-2配置migration Aの一時RLS（未承認）

実行ロールは既存`pitchlog_owner`。配置前に試合作成を停止し、正規のmigration接続・現在のAlembic head・F-2出所・5 UUID/5キー・FORCE RLSが有効であることを確認する。`rule_sets`と`game_type_rule_defaults`へ以下の**4つだけ**の一時ポリシーを、配置と**同じtransaction**で作る。`pitchlog_owner`以外を`TO`に含めない。

| 一時ポリシー名候補 | 対象/command | 条件 |
| --- | --- | --- |
| `tsk550_seed_rule_sets_select` | `rule_sets FOR SELECT TO pitchlog_owner` | `USING (id IN (承認済み5 UUID))` |
| `tsk550_seed_rule_sets_insert` | `rule_sets FOR INSERT TO pitchlog_owner` | `WITH CHECK (id IN (承認済み5 UUID))` |
| `tsk550_seed_defaults_select` | `game_type_rule_defaults FOR SELECT TO pitchlog_owner` | `USING (game_type_key IN (承認済み5キー))` |
| `tsk550_seed_defaults_insert` | `game_type_rule_defaults FOR INSERT TO pitchlog_owner` | `WITH CHECK (game_type_category='game_type' AND (game_type_key,rule_set_id) IN (承認済み5組))` |

対象表のDDL lockをtransaction終了まで保持し、候補ID/キーに既存行が**1件でもあれば出所不明として停止**する。値が一致しても流用・上書きしない。5つの`rule_sets`行を先にINSERTし、5つの既定対応をINSERTする。規則値/JSON形はF-2と承認済み機械文字列から構築し、配置直後に5組・5値・FKをexact照合する。**commit前に4ポリシーをDROPし、`relrowsecurity`/`relforcerowsecurity`、policy集合、ロール/列ACL、app直表権限が事前の宣言と一致することを確認**する。作成/検査/INSERT/DROP/事後照合のどこかで失敗したらtransactionをrollbackし、配置行も一時ポリシーも0件に戻す。事後カタログが検査不能なら成功を宣言しない。downgradeは成功を偽装せず明示的に停止し、復旧は管理者の別承認済み訂正migration/バックアップ復元で扱う。`0030_seed_game_type`のexact DELETE先例はあるが、今回は試合から参照され得る規則行のため同じ削除手順を流用しない。製品経路にはDELETEを追加しない。

配置Aと関数/ACLの製品認可適用Bは別の成功境界である。AがcommitしBが失敗した場合はAの出所付き行を残して**製品作成を公開せず**、Bの再試行または承認済み訂正migrationを要する。A+B全体が原子的と主張しない。Bは現行`application-steps.json`の単一transaction・固定7手順に従い、role→schema→definer function→RLS/policy→列ACLを適用する。もし関数DDLをAlembic別revisionに置くなら、既存適用器との重複・owner変更権限・PUBLIC EXECUTEの一瞬の露出がない具体順序を、実装前に認可面所有者が審査する。現行TSK-550計画の「関数migration」表現と適用器の関係に差分が出る場合は、ステップ3着手前に最小計画追補を出す。

### 7.7と正式受理の分離

ステップ1は対象を`ddl-elements.json`、`capability-catalog.json`、`application-steps.json`、必要なfunction-body/露出資産、`runtime-authz-contract.json`、`repository-contract.json`、`repository_contract.py`、`base-allowlist.json`、必要な`history-snapshots/**`、migration/DB catalogへ固定し、認可面・tenant境界・移行所有者とTSK-550担当の照合分担を決める。**digest/変更後基準は実変更後のステップ3・4で各受理直前の実状態から算出**する。正本7.3の人間承認、一時RLS/列UPDATEの個別承認、7.7の変更後受理を混同しない。
