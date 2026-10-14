# TSK-550 ステップ1・残る4件の判断用差分

2026-10-14。これは**正本と個別資産の変更案**であり、製品契約・migration・認可・凍結基準の承認または実装ではない。A追補計画`a2b8a5b5`、Codex Dの`06f7834f`、固定function operationのPO代替受理を維持する。段階B、大会割当/管理書込関数、ゲームHTTP実装を含めない。関係担当の採否と正本ゲートで本文を確定する。

## 1. 6-key保存とU-G1接続

**data-model §6-5へ追加する本文案**: 「段階Aで新規作成した試合の`games.applied_rules`は、既存JSONBの同一top-level objectに`ruleSetId`（正規UUID文字列）と、凍結`game_end_contract_schema_v1.json#/$defs/ruleSnapshot`の`regulationInnings`・`coldConditions`・`extensionLimit`・`tiebreak`・`dh`の5値をexact-setで持つ。保存時に同一transactionで取得した1つの規則行のIDと値だけを写し、規則マスタの後日変更は保存済み試合へ遡及しない。`ruleSetId`を既存5-key schemaへ未知keyとして渡さず、5-key projectionを既存schemaで検証する。規則ID専用ゲーム列と第2の規則計算実装は作らない。旧`{}`、未知key、不正UUID・値、出所不明行を新規の解決済み値へ補完しない。」

**data-model §10-5へ追加する本文案**: 「段階Aの全体既定は、`game_type_rule_defaults.game_type_key`から`rule_sets.id`へ辿り、閉じた製品書込権限と出所が証明された配置行に限る。大会割当が存在するときは既定へフォールバックしない。試合へ保存するのは規則IDと5値のスナップショットで、段階Aでは`rule_sets`の帰属列、大会割当書込関数、既存試合の推定移行を足さない。」

| JSONB key | 読取元 | 変換と制約 |
| --- | --- | --- |
| `ruleSetId` | `rule_sets.id` | UUIDをcanonical lowercase hyphenated文字列へ一度だけ変換 |
| `regulationInnings` | `rule_sets.regulation_innings` | 整数。既存5-key schema・相関検証 |
| `coldConditions` | `rule_sets.called_game_conditions` | JSONB段配列。`pointDifference`・`startInning`を保持し、既存schemaで検証 |
| `extensionLimit` | `rule_sets.extra_innings_limit` | 整数またはnull |
| `tiebreak` | `rule_sets.tiebreak_rule` | objectまたはnull。既存schemaで検証 |
| `dh` | `rule_sets.uses_dh` | boolean。boolをintegerとして許容しない |

U-G1への接続案: 認証済み`TenantContext`から開いた**同一**`tenant_transaction_scope`内で、RG1の作成前ゲート→段階A resolver→成功snapshotの単一codec encode→登録済みgame INSERTに`applied_rules`と`rule_override=NULL`を渡す→RG1コミット直前ゲート→commitの順とする。失敗値・decoder失敗・DB競合・RG1停止はscopeを例外終了してgameを0件へ戻す。resolverもcodecもcommitせず、別Sessionや再読でIDと値を取り直さない。U-G1が同一scope保存mappingと非成功からINSERTへ進めない呼出しを受理する。実HTTP/RG1/保存全取消はTSK-395ステップ2で確認する。

既存行は本タスクで一括更新しない。`{}`や5値だけの行を段階Aの解決済みとして再保存・利用しない。表示・復旧での具体的な扱いはU-G1/U-F8の消費側が別途確定し、過去行の一括移行は別タスク/ゲートとする。**`Game.applied_rules`列は既に非NULL JSONB**であり、専用列が無いという理由だけのDDL追加はしない。

## 2. 7.6判定と正本ゲートの射程

| 対象 | 具体的意味差分 | 7.6判定案・審査単位/担当 |
| --- | --- | --- |
| `docs/design/data-model.md` §6-5・§10-5 | 6-key保存形、旧行拒否、全体既定の出所と段階A拒否境界を**規範として追加**。ゲーム列/規則表の物理列は追加しない | JSONB内部の保存構造・受理形を新たに固定するため**構造的変更→7.3**を推奨。data-model所有者が本文差分と変更履歴を提出し、敵対レビュー→人間承認。`schema-manifest.json`の列集合は変えない |
| `docs/features/product-authz-surface/design.md` §1-6 | 閉鎖した3表のACL、段階Aの制限読取関数1件のowner/EXECUTE/tenant GUC/失敗とRLS迂回条件を追加。書込関数や直接SELECTを開かない | 新しい`SECURITY DEFINER`の越境境界であるため**認可アーキテクチャ変更→7.3**を推奨。認可面所有者が本文・変更履歴を提出し、敵対レビュー→人間承認。data-modelとは**別の正本審査単位**として各所有者の採否を残す |
| `docs/features/product-impl-unit-split/{plan,design}.md`、`docs/features/ux1-state-calc/{plan,design}.md` | TSK-539/U-X1からTSK-550へFR-014段階Aだけ先行分離した担当・現況を追記。T1〜T6の所有と凍結を変えない | **実装追随の節更新→PRレビュー**を推奨。所有者が凍結の規範を変えると判定した行だけ7.3に切り分ける。既存の承認済みA計画を再承認待ちへ戻さない |
| 要件書・ADR-003・開発ハーネス | F-2の値・FR-014優先順位・NFR-018・7.7規則は変更しない | 反映なし。タイブレークの新しい機械コードを要件の規範にする場合だけ**別の7.3差分**として審査 |

本feature worktreeは他担当が所有する正本ファイルを**無断で**編集しない。上の本文案を所有者へ渡し、各所有者が対象本文・版/変更履歴・審査計画を起案する。複数文書を1ゲートと数えるかどうかを後から曖昧にしないため、現案では**data-modelとauthzを各1審査単位**に分離し、各単位の7.3敵対レビュー周回・人間承認を別記録とする。承認された本文は対象所有者のコミットを本featureへcherry-pick/取り込みして**TSK-550の製品コードと同一PR**に含める。競合時の解消差分も同じ所有者・ゲートで確認する。別PRへ置く場合でも先行統合済み正本を本PRの基線として明示し、7.6の同一PR要件に対する適用判断をハーネス担当へ求める。どちらも構造変更でなく実装追随と所有者が判断する場合は、7.6の根拠を条文と意味差分に対応させて記録する。

## 3. 付録F-2の配置差分と停止規律

`contracts/seeds/game-type.json`とmigration `0030_seed_game_type`で確定した5キーに対し、次の**配置ID候補**を提示する。UUIDは`uuid5(NAMESPACE_URL, "pitchlog:FR-014:F-2:2026-07-22:" + game_type_key)`で再現可能。IDの採用とタイブレークの機械表現は**未承認**であり、migrationをまだ書かない。

| 試合区分キー | 規則UUID候補 | 規定 | コールド段（点差,開始回） | 上限 | タイブレーク | DH |
| --- | --- | --- | --- | --- | --- | --- |
| `game_official` | `ca626b2e-8751-530e-a431-9ef5c00f7d95` | 9 | `[]` | 12 | 10回、無死一・二塁、継続打順 | true |
| `game_semi_official` | `8fa3b9b7-481b-538b-8093-6af96050d97f` | 9 | `[(10,5),(7,7)]` | 9 | null | true |
| `game_open` | `b679f9f1-86a8-54f7-9466-a5b01d932953` | 9 | `[(10,5),(7,7)]` | 9 | null | true |
| `game_intrasquad` | `45677369-9e25-5220-9a30-1d89b338174c` | 9 | `[(10,5),(7,7)]` | 9 | null | true |
| `game_other` | `6ff51660-bee2-552a-9075-1f3f3d1e0dd7` | 9 | `[]` | 9 | null | true |

DB行は`rule_sets`の5列へ値を写し、`game_type_rule_defaults`を5キー→5UUIDへ結ぶ。`coldConditions`は段配列の`{pointDifference,startInning}`へ変換する。公式戦`tiebreak`は既存schemaの`{startInning,runnerPlacement,leadoffRule}`に対応し、`startInning=10`まではF-2に明記済み。`runnerPlacement`と`leadoffRule`には機械enumが未定義のため、候補を`"no_out_first_second"`/`"continue_lineup"`とし、**この2文字列だけはPO・U-X1/U-G1が採否を判断する**。承認なしに新しい意味値を製品へ入れない。既存schemaは非空文字列しか検査しないため、意味の妥当性は後続の単一codecと正式契約で閉じる。`tieBreak`というキーは作らず、既存schemaの`tiebreak`を使う。

**migration順序候補**: 現行`0030_seed_game_type`以降の最新統合headを基点に、(A)出所付きF-2規則データの配置revision→(B)制限読取関数・必要ACLのrevisionの順にする。revision番号は着手時のAlembic headで採番し、A→Bの`down_revision`を固定。Bより前の環境で製品作成を公開しない。既存DBでは`pitchlog_owner`もFORCE RLSに従うため、Aの**同一transaction内で最初に**`rule_sets`の候補5 IDと`game_type_rule_defaults`の候補5キーだけをownerがSELECT/INSERTできる一時ポリシーを作る。必要な表DDL lock/保守停止下で既存候補の有無を調べ、5規則行と5既定対応を検査・配置し、**commit前に一時ポリシーを除去してRLS/ACLの事後状態をexact照合**する。ポリシー作成/削除・データ配置・事後確認のどこかが失敗したら全rollbackする。ownerが候補外の行を読む必要が生じる検査はこの権限では通らないため、隠れた既存行を安全と推定せず停止する。これは既存`system_vocabularies`の所有者専用seed経路を参考にした新しい**個別認可ゲート候補**であり、正式承認前に適用しない。Aは候補IDまたは既定キーの既存行が1件でもあれば由来不明として停止し、値一致だけの冪等採用もしない。部分配置、別IDでの既定行、他用途の既存参照、出所を確認できない既存行があれば**全rollback**。物理DELETEのdowngradeは設けず、後戻しは別の訂正migrationとする。

**出所と排他**: 承認対象は要件書F-2の日付/節、5キー、5固定UUID、5値、変換、配置revisionとその監査/適用記録の組。製品runtimeの管理/割当書込は閉じたまま。初回配置・再適用時は試合作成を停止し、全検査→commit→正規の認可資産/関数適用→起動時確認を終えてから解除する保守窓を推奨。オンライン配置を認める場合は別途共通ロックと二接続証跡が必要で、今回のAには含めない。配置未了/不一致なら`rule_not_available`または`invalid_rule`へ分類して全取消、U-G1本番作成成功は未達。

## 4. 認可・凍結資産の具体差分と7.7

**product-authz §1-6へ追加する本文案**: 「段階Aは`public.resolve_stage_a_rule(text,text,boolean)`相当の**読取専用**制限関数1件を、認証済みtenant scope内から固定operationで呼ぶ。既存`authz_private`はappにUSAGEを与えていないため、そのschemaへapp呼出し関数を置く案は採らない。関数owner候補は既存`pitchlog_management_fn_owner`（NOLOGIN・BYPASSRLS）だが、必要な参照列のSELECTを別に与え、PUBLIC EXECUTEを取り消して`pitchlog_app`へ当該関数のEXECUTEだけを付与する。`SECURITY DEFINER`、`SET search_path = pg_catalog, pg_temp`、全表参照のschema修飾、tenant GUCの存在/UUID/親大会整合検査、同一tenantの割当存在拒否を必須とする。`rule_sets`と`tournament_rule_assignments`のapp直接SELECT/書込は開かず、`game_type_rule_defaults`の既存SELECTだけを維持する。」

**最小参照列候補**: ownerへ`tenant_vocabularies(tenant_id,key,category,disabled)`、`tournament_rule_assignments(tenant_id,tournament_key)`、`game_type_rule_defaults(game_type_key,rule_set_id)`、`rule_sets(id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh)`の列SELECTを付与する。`BYPASSRLS`だけでは表権限を得ないため、列ACLを資産・実DBカタログでexact照合する。現行`public` schemaのACL宣言には`pitchlog_management_fn_owner`のUSAGEがないため、関数の所有・解決に必要なschema権限も個別差分とする。直接の`pitchlog_app`表ACLは現行通り。関数は`SET`/DMLを発行せず、親大会を先に`FOR UPDATE`でロックし、**割当有無は通常SELECT**で確認した後、既定→規則を`FOR SHARE`でロックしてcommitまで保持する。割当の製品書込入口は閉じ、特権書込は保守停止に限定する。親大会への新しい割当INSERTは既存複合FKの親行ロックと競合させ、二接続で実測する。**PostgreSQLの行ロック付きSELECTには、親大会・既定・規則の各ロック対象表で少なくとも1列へのUPDATE権限が必要**であり、SELECT列ACLだけでは成立しない。推奨は既存NOLOGIN ownerの3表それぞれの最小列にUPDATEを個別付与し、関数本文がDMLを発行しないこと、ownerへの`SET ROLE`不可、app直UPDATEの増分なしを資産・実DBで検査する案。どの列を対象にするか、lock対象集合を縮小しても並行変更契約を保てるかは認可面/DB所有者が正式審査する。広い表UPDATEを黙って付けない。`set_config('app.tenant_id')`は既存scopeがtransaction-localに設定する。DB関数が検査できるのはGUCの存在/形式と対象行との整合までであり、任意のapp DB接続からのGUC偽造までDB単体で防げるとは主張しない。公開到達を固定registry/tenant context発行証跡へ閉じる前提と、直SQL脅威モデルの採否を認可面所有者が明示する。

| 資産・コード（変更候補） | exact差分と担当 | 7.7の受理単位・時点 |
| --- | --- | --- |
| `contracts/authz/product/{ddl-elements.json,capability-catalog.json,application-steps.json,function-bodies/**}`と必要な露出/写像資産 | 読取関数1件、ownerのschema USAGE/列SELECT/3表の行ロック用列UPDATE、PUBLIC revoke/app EXECUTE、function capabilityのexact IDと対象/戻り、適用順。F-2配置中だけのowner限定RLSポリシーと事後除去も認可面所有者・移行所有者が個別審査。TSK-550担当は原本/生成物を突合 | ステップ1で変更対象と前後基準の採取手順/担当を固定。実資産変更とDB適用・catalog検査はステップ3。管理/割当書込のcapabilityを追加しない |
| `contracts/tenant_boundary/{runtime-authz-contract.json,repository-contract.json,base-allowlist.json,history-snapshots/**}`と`backend/src/pitchlog/repositories/repository_contract.py` | 公開`run_function`/固定token型、関数ID/引数/戻りdecoder、保護関数集合、allowlistの新シンボル。既存DML登録/DTO許可集合の縮小・緩和なし。TSK-550担当、認可面/tenant境界担当の個別差分レビュー | ステップ1で凍結対象集合・受理単位を**repository境界とauthz関数面の2単位**として宣言。digest/基準値はまだ書かない。変更後の各単位のdigestと単一受理履歴、必要snapshotの追記/検査はステップ3・4の実変更時 |
| `contracts/db/schema-manifest.json`とAlembic revision | 列/制約は変更しない。規則配置と関数/ACLの実DB要素は既存manifestの表列形と整合させる。data-model/移行所有者、認可面所有者 | 基準が実際に動く資産だけ7.7対象を決める。migrationの具体DDL/データと適用結果はステップ3。未変更列のdigestを予測して記録しない |

**ステップ1で固定する7.7手順**: (1) `origin/develop`/PR merge-baseは影響調査だけに使い、対象集合・識別粒度・担当を宣言する。**旧識別値はステップ3・4の各受理直前の実状態**から算出する。(2) 各個別承認後の差分に対し、宣言と生成コード/機能/カタログをexact照合し、受理直後の状態を同じ受理単位として算出する。(3) 基準を動かした単位ごとに`base-allowlist.json`の宣言と追記のみの単一履歴、必要な`history-snapshots/**`を**同じ変更PR**に置き、確認不能なら検査を失敗させる。(4) 実DB/基線/迂回試験とコア敵対レビュー・人間逐行確認を行う。**新digest・変更後基準の受理は実資産が存在したステップ3・4でのみ確定**し、ステップ1の合格条件へ戻さない。正本7.3の人間承認と7.7資産受理を混同しない。

## 5. 判断と審査の依頼

| 判断対象 | 推奨案 | 採否担当・ゲート |
| --- | --- | --- |
| 6-key保存/旧行とU-G1同一scope | §1案。既存JSONB、旧行不補完、1回のencodeとgame INSERT、例外全取消 | U-G1消費側、data-model所有者。§6-5/10-5の7.3本文承認 |
| F-2固定IDとタイブレーク文字列 | §3のUUIDv5と`no_out_first_second`/`continue_lineup`。値はF-2から変更しない | PO・U-X1/U-G1、data-model所有者。新しい文字列意味が要件の規範になるなら要件書の別7.3 |
| 配置の順序/排他 | データA→読取関数B、保守停止、衝突全取消 | data-model/移行所有者、運用・認可面所有者。migrationの個別審査と7.7 |
| 関数公開面・owner・GUC | `public`の読取専用1関数、ownerのschema USAGE/列SELECT/行ロックに必要な列UPDATEを個別審査、PUBLIC revoke/app EXECUTE、GUC検証 | 認可面/tenant境界所有者。認可面§1-6の7.3、具体DDL/資産の7.7 |

人間が判断するのは**具体的なID/機械表現、2つの正本7.3本文、配置/認可資産の個別差分、GUC脅威モデル**である。計画Aや既受理の閉鎖モデル・4失敗・固定operation契約を再承認待ちへ戻さない。実装後証跡が必要な箇所は承認済み計画ステップ3〜6とTSK-395ステップ2へ残す。
