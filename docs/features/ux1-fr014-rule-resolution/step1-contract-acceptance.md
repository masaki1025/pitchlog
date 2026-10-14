# TSK-550 ステップ 1 接続受理シート（未完了）

2026-10-14、PO は計画 HEAD `93d2f49c` を承認し、ステップ 1 のみ指示した。段階 A を先行し、段階 B は後続。本書は契約の照合と未受理事項の記録であり、製品仕様・スキーマ・認可・凍結基準の承認ではない。

**同日の追加判断**: POは[最小追補](step1-gate-addendum-proposal.md)のAを**範囲として選択**した。ステップ1は実装前の契約受理、実関数の2接続/故障注入はTSK-550ステップ3〜6、U-G1実HTTP・RG1・全取消はTSK-395ステップ2。最終計画承認と個別資産変更の承認はまだない。`plan.md` の承認欄は追補承認待ちへ戻したが、旧計画HEADの承認履歴は有効な記録として維持する。

| Aの契約項目 | 受理状況 | 未成立なら起こること・次の受理先 |
| --- | --- | --- |
| JSONB内 `ruleSetId` + 凍結5値 | Codex D `24566d72` で**条件付き採用**。snake_case案は撤回 | exact-set codecと利用側U-G1の受理が必要。旧 `{}` を解決済みにしない |
| 全体既定の帰属・割当あり拒否・同一scope | 割当あり拒否と全確定/全取消の意味はCodex Dが採用。帰属は条件付き採用 | 既存行の出所、管理書込権限、全入口ロック順と保持期間をU-X1/認可面/tenant境界へ受理依頼。証明できない行は拒否 |
| 公開関数/成功型/4失敗/固定operation | Codex D `24566d72` では**未受理**（固定operationは条件付き） | U-X1・U-G1・tenant境界に具体signature/literal/登録差分を提示し回答を得る。仮operationで保存成功にしない |
| 実規則データの供給 | **値は要件書付録F-2で2026-07-22確定済み**。製品管理書込関数・F-2値の配置seedは未確認 | 推奨はF-2値/ID/出所と既存行衝突拒否を個別審査したデータmigrationをTSK-550ステップ3に含める。値自体を再裁定しない。管理者専用書込関数は後続の別差分で、権限/監査/競合保護の個別ゲートが必要。配置未了なら `rule_not_available` 等で全取消。RG1実operationもなければU-G1作成成功に届かない |
| 実測 | `24566d72` 時点では未実施 | TSK-550ステップ3〜6で実関数/2接続/故障注入、TSK-395ステップ2で実HTTP/RG1/全取消。実装前条件にはしない |

**次の具体差分**: `plan.md` のステップ2をstrict codecへ、3〜6を段階Aの実関数→固定operation→resolver→実測へ訂正した。正本の具体本文、関数DDL/ACL、repository-contract/7.7差分は各担当の契約受理と個別ゲートを経て起案・実施する。段階B、帰属列と曖昧な旧行の移行は今回確定しない。RG1①〜⑤のU-G1受理 `79e3da4a` は維持し、D4外部台帳はpreparingの条件に入れない。

## 段階 A と段階 B

| 段階 | 成功と拒否の境界 | 現時点 |
| --- | --- | --- |
| A（先行） | 安全に帰属を証明できる全体既定だけを解決し、規則 ID と付録 F の値をスナップショットとして試合作成と同じ transaction で保存。対象大会に割当があれば既定へフォールバックせず拒否。規則の出所を証明できない、割当有無を安全に判定できない、値が無効、読取に失敗した場合も成功しない | PO の方向性は確定。公開関数・型・帰属証明・保存表現・同時実行境界は未受理 |
| B（後続） | 大会割当、試合上書き、FR-014 全優先順位の実装。帰属列・制限関数・既存行移行を正式ゲートで確定。段階 A の「割当あり拒否」を既定へのフォールバックへ変更しない | 本ステップでは実装せず、契約・正本の個別ゲートを先取りしない |

## 既存契約との照合

| 項目 | 確認できた事実 | ステップ 1 に残る受理/判断 |
| --- | --- | --- |
| 優先順位と非遡及 | 要件書 FR-014、データモデル 6-5 は上書き > 大会 > 区分既定、保存時の規則値スナップショットと後日変更の非遡及を要求 | 段階 A の対象外入力（上書き、割当あり）をどの失敗結果に写すか。段階 B の優先順位は維持 |
| 全体既定の参照 | `game_type_rule_defaults` は `global_read_only` で `rule_set_id` を保持。`rule_sets` と `tournament_rule_assignments` は `function_only` | 既定 ID が指す規則の帰属を何で証明するか。アプリの `rule_sets` 直接読取を開かない制限関数/operation を U-X1・認可面側が受理 |
| 割当の有無 | `tournament_rule_assignments` は `(tenant_id,tournament_key)` を主キーとし `rule_set_id` を持つ。アプリ直接読取はできない | 論理的に有効な割当の定義と、割当ありを同一 scope で安全に判定・拒否する手段。作成と並行した割当変更のロック/整合時点 |
| 保存先 | 現行 `games.applied_rules` は非 NULL JSONB、`games.rule_override` は nullable JSONB。規則 ID 専用列はない | 本書の JSONB 案を推奨。ID+値の形状と旧行の扱いを U-X1/U-G1 が受理し、必要な正本ゲートを通す。値だけの保存を段階 A 完了としない |
| 公開面 | `_TenantTransaction.run` は登録済み operation token のみ。現行登録型は tenant column 付き `Select/Insert/Update` | 段階 A の公開関数名・入力型・不変結果型、制限関数を scope から安全に呼ぶ登録方法。直接 Session 逃げ道を作らない |
| 失敗と秘匿 | NFR-010 は他テナントの内容・存在を秘匿。計画は候補なし/越境/無効規則/読取失敗を内部で区別し、利用者向け外形を統一する | 段階 A の「割当あり」「出所不明」「上書き指定」の結果型と、TSK-395 HTTP 写像。内部区別を越境応答へ漏らさない |
| 原子性 | TSK-395 は U-X1 の結果を試合保存と同一 `tenant_transaction_scope` で使う。保存済み値は非遡及 | 読取/検証/ゲーム保存の全取消、規則 ID と値の一貫した取得・保存、commit 直前までの競合制御を担当受理。実 HTTP/認可試験は TSK-395 側 |

## 2026-10-14 推奨する具体案（受理前・製品契約未確定）

### 規則 ID と値の保存

`games.applied_rules` は非 NULL JSONB で、ORM 型は `dict[str, object]`。製品 decoder はまだ無く、試験 seed は `{}` も挿入する。データモデル 6-5 は値の保存と非遡及を要求し、JSONB を候補とする。`a1c11248` の snake_case 案は、Codex D が `24566d72` で指摘した既存の凍結5値 schema（`contracts/state-transition/game_end_contract_schema_v1.json` の `$defs.ruleSnapshot`）との不一致により**取り下げる**。段階 A の新規作成行には、同 schema の camelCase 5値へ規則 ID を1つ加えた次の形を推奨する。専用ゲーム列は追加しない。`{}` を解決済み規則へ補完しない。

```json
{
  "ruleSetId": "UUID文字列",
  "regulationInnings": 9,
  "coldConditions": [],
  "extensionLimit": null,
  "tiebreak": null,
  "dh": false
}
```

このJSONは形状例であり、個々の試合へ固定値を埋める指示ではない。試合区分の初期既定値は要件書付録F-2に確定済み。実際は安全な全体既定から読んだ規則のIDと検証済み**全5値**を同一読取時点から格納する。上位6 keyを exact-set とし、ID は canonical UUID 文字列、残る5 keyだけを既存 `$defs.ruleSnapshot` で検証する。`ruleSetId` を未知 key のまま既存 schema に流して拒否を回避しない。Python の `bool` を整数として受理しないこと、schema 後の付録 F 相関検証、encode/decode round-trip、旧 `{}` の拒否を契約試験にする。`rule_override` は入力上書き用の別列であり段階 A は指定を拒否する。U-G1 保存・後続 U-X1 計算側の受理と JSON 形状の正本明記は必要。列検索要件や既存利用側の固定形が新たに示されない限り、専用 ID 列は追加しない。帰属列migrationはAの必須から外した計画追補の最終承認待ち。

### 全体既定の帰属・変更権限

| 境界 | 現行証拠 | 推奨案と未成立条件 |
| --- | --- | --- |
| 参照 | `game_type_rule_defaults` は区分キーで一意、`rule_set_id` は `rule_sets.id` を参照。データモデル 6-5 と認可面設計 1-6 はこの既定をシステム管理とする | 段階 A の候補は**指定区分の既定表から辿れた ID だけ**。任意の `rule_sets.id` を入力・直接照会しない。既定表への参照を帰属の証跡とする案。ただし参照関係だけでは書込主体を証明できない |
| 書込権限 | `table-classification.json` は既定表 `global_read_only`、両規則表 `function_only`。`capability-catalog.json` には既定表の read だけ。`ddl-elements.json` の `pitchlog_app` ACL は既定表 SELECT のみ、他2表の ACL/既存制限関数はない | 既定対応の変更は認証済み管理経路だけ、チーム経路から既定 ID・規則値を変更できないことを**U-A2/認可面所有者が受理**。現行の分類は設計上の禁止を示すが、管理用書込関数の安全性や将来の付与まで実証しない。証明できなければ最小改訂は既定対応とその規則値の管理者専用書込関数・権限を明記して実 DB ACL 試験を追加。段階 B のテナント規則の帰属列・制約は別ゲートで扱う |
| 読取制限 | app は `rule_sets` と大会割当表を直接 SELECT できない。これらに app 用関数はまだない | 専用の読取制限関数を別 migration で提案する。固定 `search_path`、最小権限の関数所有者、app には `EXECUTE` のみ、認証済みテナント文脈と区分/大会キーを照合し、既定 ID+5値だけを返す。任意 ID を受けず、内部の他テナント有無を返さない。`SECURITY DEFINER` の要否・所有ロール・実行権は認可面/テナント境界所有者の個別受理対象 |

現行の `rule_sets` に帰属列はない。既定表が管理者専用に保護され、関数がその参照からしか値を返さないなら、**段階 A の全体既定に限り**帰属列なしで証明できる可能性がある。ただし認可面設計 1-6 は混在所有を指摘しており、将来の大会割当・任意 ID 読取にはこの証明を広げられない。管理書込境界を証明できない場合の最小スキーマ改訂候補は `rule_sets` に帰属区分と nullable な所有 `tenant_id` を加え、全体既定が全体帰属の行のみを指す制約と既存行の曖昧さを拒否する移行方針を設けること。列名/値/DDL/移行は未承認であり、別途データモデルの正式ゲートを通す。

### 大会割当の有無・同時実行

`tournament_rule_assignments` の主キーは `(tenant_id, tournament_key)` で、`rule_set_id` は非 NULL。削除状態列はなく、親に従う lifecycle。段階 A は認証済みテナント ID と入力大会キーの**同じ組**を制限関数内部で `EXISTS` 判定し、行が1つでもあれば規則値を返さず「段階 A 対象外」を返す。直接 SELECT 権限を app に付けない。大会キー自体が自テナントで有効かも先に検証し、越境/欠損の利用者向け外形を揃える。大会割当があるのに規則値が不正でも全体既定にフォールバックしない。

この `EXISTS` だけでは、判定後〜試合作成コミット前の割当 INSERT/UPDATE と競合する。推奨案は、解決・ゲーム INSERT・コミット直前ゲートを同一 `tenant_transaction_scope` とし、割当設定の書込関数と共通の `(tenant_id,tournament_key)` ロック規律を持つこと。現行の割当書込関数・ロック規律は確認できないため、これを受理済みとはしない。書込側との共通ロックを導入できないなら、隔離レベルを含む別の直列化方式と再試行可能な競合結果を U-X1/認可面/U-G1 が受理するまで作成成功にしない。読取故障・ロック競合・検証失敗・INSERT 失敗は全取消。2接続 PostgreSQL の競合試験と実 HTTP 結合試験を後続ゲートへ残す。

**独立受理担当への具体案（2026-10-14、未受理）**: 既存 `tenant_vocabularies(tenant_id,key)` 親行を直列化点とする。解決側は認証済みテナントと大会キーの親行を `FOR UPDATE` で先に取得し、同一 transaction 内で割当 `EXISTS` を判定する。割当書込側も INSERT/UPDATE/論理的な解除の**前**に同じ親行を `FOR UPDATE` し、commit/rollback まで保持する。割当解除を物理 DELETE で実装する意味ではない。これなら割当 INSERT の不存在行ロックに頼らず、双方の順序が親行ロックで決まる。次に既定対応行、規則行をこの順に `FOR SHARE` し、ID と5値を同じ transaction の読取結果から検証・保存する。管理側の既定対応/規則値 UPDATE はこれらの共有ロックと競合して待機する。管理書込と大会割当を一つの transaction で行う経路を作る場合は同じ親行→既定対応→規則行の順に従う。後続の試合行・RG1直前ゲートを含む全取得順は U-G1/U-R1 と照合し、ここだけで確定しない。線形化点の候補は親行取得後の割当判定と既定/規則行のロック取得が完了した時点で、ロックは試合 INSERT と RG1 ゲート後の commit/rollback まで保持する。管理書込関数と割当書込関数が未実装なので、将来の全書込経路がこの規律を守る受理と実 DB 試験なしに安全を宣言しない。

2接続試験案は、割当 INSERT 先行/解決先行、割当規則 UPDATE、解除、各側 rollback、別テナント並行、既定対応/規則値 UPDATE、lock timeout・deadlock・serialization failure、解決後/ゲーム INSERT 後の故障注入を含む。保存 JSON の ID と5値が同じ取得結果に一致し、割当ありで既定成功しないことを確認する。U-R1 の RG1 行 `FOR SHARE` は作成コミット直前まで保持する受理済み接続であり、この競合試験とは別に実経路で全順序を検証する。

### 受理を求める項目

**公開接続の解決候補**: `resolve_rule_set(transaction, game_type_key, tournament_key, rule_override=None)` のように、テナント ID を任意値として受け取らず、既存 `tenant_transaction_scope` に束縛済みの handle と入力キーだけを渡す。成功値は凍結した `AppliedRuleSnapshot` 相当（規則 UUID と付録 F の5値）とし、JSON 化は U-G1 の `games.applied_rules` 保存時に一度だけ行う。失敗は内部では少なくとも候補なし・越境/無効 scope・無効規則・読取失敗を区別し、段階 A 対象外（大会割当・上書き指定）と再試行可能な DB 競合も明示的に分類する。**名称・literal・公開 exception/result 型と HTTP 外形は未受理**。越境と候補なしを利用者向けに識別可能にしない。競合を隠れた自動再試行や保存成功へ写さない。

現行 `OperationRegistration` は `Select/Insert/Update` と実表の `tenant_column` を必須とし、`_TenantTransaction.run` はその token だけを実行する。既存の cross-tenant 関数登録は `TenantRepositoryBase.execute` 側で、同一作成 scope の公開関数呼出しにはそのまま使えない。したがって制限関数は、**固定の関数 ID・引数・戻り値を検証する tenant-bound function operation** を既存 scope/registry に限定追加する案を優先する。任意 SQL や Session 公開はしない。`repository-contract.json` と認可 capability/ACL/凍結基線の具体差分、7.7 受理、bypass 試験は別の個別ゲートを要する。これは計画ステップ 4 の実装対象であり、ステップ 1 では方式の担当受理までに限定する。

1. U-X1 独立担当 Codex D: 条件付き採用項目の成立条件、親行ロック案と管理書込の全経路、公開関数/入力/結果/4失敗 literal を採否付きで回答。条件付き採用を完了受理と読み替えない。
2. U-A2・認可面/テナント境界所有者: 管理書込の主体と制限関数/ACL/operation 登録、割当書込とのロック規律について、現行で証明可能な範囲と必要な最小差分を回答。
3. U-G1/TSK-395: ID+5値の保存、対象外・失敗の HTTP 外形、同一 scope での作成/全取消を消費側として受理。実経路試験は別途実施。

上記は**提案**。独立担当の指名は済んだが、契約の最終受理、既存行判断、必要な正本/認可/凍結ゲートが済むまでステップ 1 は未達。`feature_status` の「不明」は作業ログに残し、本件のためのハーネス改修は行わない。

## `24566d72` の差分受理への回答と次の差分

Codex D の差分受理原本 `docs/features/ux1-fr014-rule-resolution/delta-acceptance-a1c11248.md` は別 branch の `24566d72` にある。現 branch の本節は原本を代記せず、担当案への採否と次の作業を記す。

| 指摘 | 当担当の採否・訂正 | 次の具体差分 |
| --- | --- | --- |
| 既存 `$defs.ruleSnapshot` と snake_case 案が不一致 | **採用**。上記を `ruleSetId` + 既存 camelCase 5値へ訂正。JSONB 内保存は維持。凍結5値 schema 自体を変更しない | `data-model.md` §6-5 に保存 shape/旧行拒否を具体本文として起案。codec の exact-set/UUID/型/相関/round-trip は計画ステップ2の候補。独立受理と正本ゲートの後に実装 |
| 共通ロック順の全書込入口、親不在・無効化・解除が未定 | **採用**。親行がない/無効/大会以外なら成功しない。親作成は INSERT 自体の順序、親無効化は先に同じ行の更新ロック。割当の物理 DELETE は禁止し、現 schema では論理解除不能なので段階Aで解除操作を設けない | 段階A解決、全体既定/RuleSetの管理、割当 INSERT/UPDATE の閉じた入口一覧と、親→割当→既定→規則→game/RG1 の順を認可面・U-G1/U-R1と受理。現在は3規則表の製品書込関数が無い。実装する入口の範囲は下のPO選択で決める |
| 固定 function operation は条件付き採用 | **採用**。現行 `OperationRegistration` へ任意SQLを混ぜない。scope内で function ID、引数 schema、不変 decoder を固定する専用登録種別を候補とする | `operation_registration.py` / `operation_registry.py` / `transaction.py` と `repository-contract.json` の exact 差分を起案し、tenant境界所有者・認可面所有者の受理、7.7受理単位を確定。実装・bypass負例はステップ4 |
| 成功型・失敗 literal・全取消が未確定 | **採用**。`resolve_stage_a_rule(bound_transaction, request)` と frozen `AppliedRuleSnapshot(rule_set_id: UUID, regulation_innings: int, cold_conditions: tuple, extension_limit: int | None, tiebreak, uses_dh: bool)` を候補とする。request は `game_type_key`・必須の `tournament_key`・上書き有無で、任意 tenant ID を取らない。U-G1 の `games.tournament_key` は非NULLなので「大会キーなし成功」は作成経路にない | 公開失敗 literal 候補を `stage_a_unsupported` / `rule_not_available` / `invalid_rule` / `outcome_unconfirmed` の4つに固定して U-X1/U-G1 へ提示。前二者の内部原因は外部へ漏らさず、失敗時は scope 例外退出で全取消。HTTP status/本文は U-G1 が別受理 |
| 2接続・故障注入の実測が無い | **採用。ただし時点を分離**。実関数・実scope・実ゲーム INSERT が未実装のステップ1で実経路証跡を合格条件にすると循環する | ステップ1で試験の操作・期待結果・DB役割・所有者を受理。関数/ACLの実DB検査はステップ3、登録/bypassは4、解決の2接続は6、U-G1 HTTP/RG1/保存全取消は TSK-395 ステップ2で実測。生SQL probe は設計根拠に限り製品証跡としない |

**現行の書込面**: `pitchlog_app` は `game_type_rule_defaults` の SELECT のみを持ち、`rule_sets` と `tournament_rule_assignments` の直接 ACL はない。3表の製品書込関数・規則初期値の製品 seed も見当たらない。`pitchlog_management_fn_owner` は存在するが、規則関数の所有・EXECUTE は未登録。従って「既存の管理書込関数がロック順を満たす」とは記録できない。既存の規則行が存在する環境では、参照関係だけで作成主体を推定せず、承認された出所の証跡が無ければ段階A成功へ使わない。実データの既定値も推定で作らない。管理経路で規則を設定可能にするか、承認済みの実規則を配置する仕組みが着地するまで、U-G1 は候補なしを保存成功へ変換しない。

**全書込経路の契約候補（製品関数は現時点で不存在）**:

| 経路 | callerと取得順 | 段階Aでの扱い |
| --- | --- | --- |
| 規則セット作成・5値更新 | 認証済み管理経路のみ。作成は検証後INSERT、既存行更新は既定対応に結ばれていれば既定対応行→規則行、単独更新は規則行 `FOR UPDATE` のみ。単独更新後に親/既定対応を後取りしない | 既存行の出所が不明なら成功へ用いない。関数/ACL/監査と値検証は個別ゲート |
| 区分既定の設定・差替え | 認証済み管理経路のみ。対象既定行 `FOR UPDATE`→旧/新規則行をUUID昇順でロック。対応行が未作成なら候補なしの作成側失敗を許し、管理側だけが保護されたINSERTを行う | チーム経路に表書込/管理関数EXECUTEを付与しない。全体既定へ結ぶ規則の出所を管理作成/承認済み配置の証跡で確かめる |
| 大会割当 INSERT/UPDATE | 認証済み自テナント経路のみ。大会親行 `FOR UPDATE`→割当行→参照規則行。親不在/disabled/別categoryは拒否し、他テナント/任意規則IDの結付けを拒否 | 段階Aのresolverは割当行があれば拒否。書込関数を段階Aへ含めるかはPO選択。物理DELETE・解除は実装しない |
| 大会親行作成・無効化 | 自テナント語彙経路。作成は同じ transaction で親INSERTが先、後続の割当入口はその後。無効化は対象親行の更新ロックを取り、後から規則資源へ触れるなら同じ全順序 | 親不在/無効をresolverは `rule_not_available`。親作成の未コミット行を見えない場合も作成成功にしない |
| 段階A解決とU-G1作成 | scope束縛→大会親行 `FOR UPDATE`→割当存在判定→区分既定行 `FOR SHARE`→規則行 `FOR SHARE`→検証済みsnapshot→game INSERT→RG1直前ゲート→commit | 規則資源のロックはcommit/rollbackまで保持。U-G1/U-R1の他資源を含む順序は消費側受理で一本化 |

新規の管理/割当関数を実装する場合は、上表に対応する固定 signature、owner、EXECUTE role、失敗結果、監査境界を認可面側と受理してから製品へ入れる。既存 migration/特権接続は通常の製品書込入口ではなく、運用変更として別の権限・データ出所確認を要する。

**実装前に確定する契約**: (1) JSON shape、旧行の拒否、単一 codec と検証の境界、(2) 公開関数/入力/成功型/4 failure literal、例外退出と U-G1 の応答外形、(3) 閉じた書込入口・caller/owner/ACL、親不在/作成/無効化/解除の意味、全ロック順とロック保持期間、(4) function operation の固定登録と tenant context 注入・任意SQL拒否、(5) schema/正本/7.7の変更対象と担当受理。ここで求めるのは**契約とゲートの受理**であり、未実装のDB挙動が合格したという主張ではない。

**実装後に提出する証跡**: 2接続 PostgreSQLで割当 INSERT/UPDATE の先行・後行と rollback、親作成/無効化、既定/RuleSet並行更新、別tenant、lock timeout/deadlock/serialization failure、解決後とgame INSERT後の故障注入を、実関数・登録済み scope と U-G1 作成経路で検証する。IDと5値の同一読取、全取消、無条件再送0回、直接表/任意関数/偽造token拒否を確認する。試験コード・DBログ・実行HEADを保存し、ステップ1の受理記録へ後から遡及して「当時実施済み」と書かない。

**現在地**: 独立担当の指名と `24566d72` の差分判定は確認済み。上記4 literal・全入口・登録境界は**受理候補**であり、最終受理と個別正本ゲートはまだない。計画ステップ1は未合格、ステップ2以降の製品コードは未着手。[最小追補案](step1-gate-addendum-proposal.md)で循環とステップ2の帰属列前提を扱う。RG1①〜⑤は U-G1 `79e3da4a` で受理済み。U-R1 の RG1/D4 分割追補は承認済みだが、資源の個別承認と U-S1 受理は別。D4台帳は未承認で `preparing` 作成条件に含めない。

## 受理状態とゲート

- **U-X1 の独立した契約受理担当**: 2026-10-14 に Notion TSK-550 コメント `3f993b75-e687-8102-8738-001dc759dcb3` で **Codex D（本セッション、案コミット `d5f2ac26` の作成に不関与）**が指名された。JSONB保存と既定表経由の帰属案は条件付き採用、割当あり拒否と同一 transaction 全確定/全取消の意味は採用。**管理書込・割当並行変更の安全性、公開結果型/失敗 literal は未受理**で、ステップ1全体は未受理。上の具体案を提示し、採否と不足差分の回答を待つ。
- **U-G1/TSK-395 の消費側受理**: 段階 A の結果型、ID+値の保存表現、割当あり拒否、同一 scope と失敗外形が確定した後に照合する。現時点では未受理。
- **正本**: `docs/design/data-model.md` 6-5/10-5 の帰属・保存表現、`docs/features/product-impl-unit-split/{plan,design}.md` と U-X1 計画の凍結文言は 7.6 の規範/実装追随判定が未了。構造改訂なら 7.3 敵対レビュー・人間承認が必要。具体本文は未起案・未承認。
- **スキーマ・認可・凍結資産**: 変更の有無と差分は未確定。変更が必要な場合、計画 3 節の対象ファイルと 7.7 受理手順に従い、具体差分を人間に提示する。今回の計画承認で代記しない。
- **計画レビュー**: 正式第1回全文 P0=3/P1=2（全採用）、第2回反映差分 P0=1/P1=0/P2=0（採用）、第3回は **P0 限定**の収束確認で P0=0。第3回は P1/P2 を検査しておらず、反映差分以外の全文も未再確認。P1 の採否とこの未確認範囲は作業ログに残す。

## 正式ゲートへ出す差分の準備状態

| 対象 | 現行文言・意味 | 提示する最小差分と判定 |
| --- | --- | --- |
| `docs/features/product-impl-unit-split/plan.md` 帯4・着手可否 | U-X1 全体を ADR-003 段階①未了の「条文凍結」と記載 | **候補**: 対象計算 T1〜T6 の凍結は維持し、FR-014 の安全な規則読取/検証/帰属は J-3 により TSK-550 へ先行切り出し、と注記する。U-X1 の主所有 FR 表と TSK-539 の T1/T2 第1 PR は変更しない。規範変更か実装追随か 7.6 判定待ち。規範変更なら 7.3 の具体本文レビュー・人間承認が先 |
| `docs/features/product-authz-surface/design.md` §1-6 | 「規則を読む・大会へ結ぶ関数と帰属列は帯4解凍後にU-X1が足す」と記載 | **候補**: U-X1 のドメイン所有と両表の `function_only`、アプリ直接ACL禁止を保持したまま、TSK-550 段階Aの全体既定読取を独立ゲート後に先行、段階Bの大会割当/上書きと帰属列は後続の個別ゲート、と時点を分ける。認可面所有者の受理と 7.6 判定待ち |
| `docs/features/ux1-state-calc/design.md` §3 と `plan.md` | J-3 は PO 判断待ち、FR-014 関数は TSK-539 第1 PR 外 | **候補**: J-3 採用・TSK-550 の担当/段階A/Bへ現況追随。T1〜T6 の計算凍結と TSK-539 第1 PR 除外は維持。U-X1 所有側受理待ち |
| `docs/design/data-model.md` §6-5/10-5 と ORM/migration/manifest | 値 snapshot は規定されるが、現行 `games.applied_rules` に ID 専用列はない。`rule_sets` に帰属列はない | **正式本文・DDLは未提示**: 本書の `applied_rules` 内 ID+5値案を優先。既定表と管理書込境界で段階 A の帰属を証明できれば帰属列も段階 A では不要。証明不能なら最小帰属列/制約/既存行移行を起案し、7.3/7.6 ゲートへ出す。専用ゲーム列は根拠が増えない限り起案しない |

上の「候補」は正本そのものへの変更ではない。段階 A の関数・保存表現に依存する差分は受理後に具体本文と migration/契約差分を提示し、そのゲートの承認前に実装しない。後続ステップ表を段階 A/B に合わせて再配置する必要が判明した場合も、製品着手前に計画差分と規約上のレビュー要否を示す。

**判定**: ステップ 1 の合格条件は未達。受理済み契約・既存行判断・必要な正本承認がそろうまで `(ステップ 1/9)` コミットを作らず、ステップ 2 へ進まない。
