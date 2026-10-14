# TSK-550 ステップ 1 接続受理シート（未完了）

2026-10-14、PO は計画 HEAD `93d2f49c` を承認し、ステップ 1 のみ指示した。段階 A を先行し、段階 B は後続。本書は契約の照合と未受理事項の記録であり、製品仕様・スキーマ・認可・凍結基準の承認ではない。

**現在地（2026-10-14、PO承認`e19f8651`）**: 開始条件の最小追補を`plan.md`へ反映した。ステップ2前のゲートはdata-model §6-5の保存形・旧行拒否の正式7.3だけとし、関数権限/配置migrationはステップ3、固定実行器/凍結契約はステップ4前へ配分する。ステップ1全体・TSK-550全体は未完了。§6-5は本worktreeでin-review起案し、所有側の回答は未確認。独立査読＋保存本文に限るPO代替受理の経路でも、正式7.3と人間承認が必要。下段の「未承認」は追補承認前の履歴である。

**開始条件の分割案（未承認）**: POの新指示を受け、[最小追補](step-gates-minimal-addendum-proposal.md)をレビュー中。ステップ2前に必要なゲートは[data-model §6-5の保存形/旧行拒否](step2-storage-canonical-gate-proposal.md)に限定し、関数権限/F-2配置はステップ3、実行器/凍結契約はステップ4へ配分する案。現行`plan.md`は追補未承認のため未変更。既受理のUUID/文字列・閉鎖モデル/4失敗・固定operationは維持する。保存本文の所有者採否・正式7.3は未了。

**同日の追加判断**: POは[最小追補](step1-gate-addendum-proposal.md)のAを**範囲として選択**した。ステップ1は実装前の契約受理、実関数の2接続/故障注入はTSK-550ステップ3〜6、U-G1実HTTP・RG1・全取消はTSK-395ステップ2。最終計画承認と個別資産変更の承認はまだない。`plan.md` の承認欄は追補承認待ちへ戻したが、旧計画HEADの承認履歴は有効な記録として維持する。

**その後の最終計画承認**: POはHEAD `a2b8a5b5f7e1c1869164770a38044361c7ab03b6` のA追補を承認し、ステップ1のみ指示した。上段は承認前の経緯。付録F-2配置migration案が最終レビュー後の追加差分だったことを人間確認対象として維持する。具体的な配置データ/migration/認可/凍結資産は未承認。下表の条件付き・未受理項目はこの計画承認によって受理済みには変わらない。

## 最新の採否とステップ1残条件（`06f7834f`・PO代替受理後）

Codex Dの独立回答 `06f7834fa8ba9a5689e8f9191e8669e28d397a9c`（`stagea-closed-writes-acceptance.md`、別ブランチ）は、**書込入口を閉じる段階A、必須大会キーを含むresolver入力、4失敗分類を受理**した。先の`df0db54b`は具体案、`06f7834f`がこの範囲の採否回答である。3規則表の製品runtime書込入口はなく、割当書込/管理書込関数を今回追加しない。親`tenant_vocabularies`にはapp INSERT/UPDATE ACLがあるが、現行製品operation/API登録はない。親行UPDATEとresolverの直列化、親不存在時の並行INSERTで成功させない条件は実装後の二接続試験に残す。

POは2026-10-14、下記の独立査読後の最終案を**ステップ1の固定function operation/repository境界に限って代替受理**した。対象は段階A resolver1件の固定登録、同一scopeの`run_function`、入力/tenant境界の検証、固定SQL/decoder、既存DML契約の非緩和。管理関数・汎用関数登録は含まない。査読P1への補正も含む。この受理を関数owner/RLS/EXECUTE/tenant GUC、`repository-contract.json`/allowlist等の具体資産変更承認とみなさない。実装/拒否試験と変更後7.7受理はステップ4。

| 項目 | 採否 | ステップ1に本当に残る条件・担当 |
| --- | --- | --- |
| 閉鎖モデル・割当あり拒否・resolver入力・4失敗・同一transaction全取消・契約/証跡分離 | **受理済み**。Codex D `24566d72`/`06f7834f`、POのA計画承認 | 実関数/実HTTP/二接続は後続ステップ。ここを一括待ちへ戻さない |
| 固定function operation/repository境界の契約 | **PO代替受理済み**（本書の修正後案に限定） | 具体的凍結資産差分と7.7ゲートは下の認可/資産行。ステップ4で実装・拒否試験 |
| 保存形 | Codex D `06f7834f`でUUID+5値と6-key JSONBを**条件付き受理** | data-model所有者の`games.applied_rules`形状/旧`{}`/出所不明行の正本文、U-G1の同一scope保存mappingの採否。値域・相関は既存単一schemaを使用。専用ゲーム列は欠如だけを理由に追加しない |
| 正本 | 影響箇所と7.6/7.3の順序は整理済み | U-X1切り出し/凍結文言と`docs/design/data-model.md` §6-5/10-5、認可面設計§1-6の具体本文について、所有者が規範変更か実装追随か判定し、必要な7.3確定を実施 |
| データ配置 | F-2の5区分値は既存要件で確定済み。**固定ID5件と2機械文字列はPO採用済み**。Codex D `06f7834f`は配置migrationを**個別ゲート付きで条件付き受理** | data-model/移行所有者が5値・出所・既存行衝突時の全停止・revision順・一時RLS・配置中の作成停止または同等排他を具体差分で審査。配置未了ならU-G1本番作成成功は未達 |
| 認可・凍結資産ゲート | 閉鎖ACLと固定operation方式は契約上確定。具体資産は**未承認** | 認可面/tenant境界所有者が制限関数owner・RLS/必要列権限・`SECURITY DEFINER`/固定`search_path`・PUBLIC剥奪・限定EXECUTE・GUC不正拒否を確定。`repository-contract.json`/allowlist/履歴/認可資産のexact差分と7.7対象・手順・担当を固定。実変更/試験はステップ3・4 |

以下の旧表と経緯節にある「Codex Dの閉鎖モデル・入力・4失敗待ち」「固定operationの担当/PO判断待ち」は、**上の最新判定より前の履歴**であり、現在の未受理一覧ではない。ステップ1全体の完了・完了コミット・ステップ2開始はまだ行わない。

## 残る4件の具体差分（担当採否前）

[判断用の本文・資産差分](step1-final-diff-review.md)を起案した。上表の既受理は維持する。以下は**承認・受理の代記ではない**。

**PO追加判断（2026-10-14）**: 同書の固定UUID5件と`no_out_first_second`/`continue_lineup`の機械文字列を採用。付録F-2の規則値・意味は不変。この項目だけを受理済みへ移し、data-model/認可面本文、配置migrationの一時RLS、関数ownerの列UPDATE、GUC脅威モデルは未承認のまま。[正本2ゲートと資産差分の本文案](step1-canonical-gate-packets.md)を個別採否用に起案した。

| 項目 | 提示した差分 | 採否と次の担当 |
| --- | --- | --- |
| 保存形 | 既存`games.applied_rules` JSONBを`ruleSetId`+凍結5値の6-key exact-setとする。単一codec、旧`{}`/5値だけの行を推定補完しない。同一`tenant_transaction_scope`でresolver→game INSERT→RG1直前ゲート→commit、失敗は全取消 | Codex Dは条件付き受理済み。data-model正本所有者とU-G1の同一scope保存接続は未受理。旧行の表示・復旧方法は消費側の別判断 |
| 正本 | data-model §6-5/10-5とproduct-authz §1-6の本文案を別々の構造変更候補として7.6判定し、必要なら各7.3敵対レビュー・人間承認。承認本文を本featureの実装PRへ含める | 各正本所有者・ハーネス担当が審査単位/同一PR経路を採否。要件書F-2値、ADR、ハーネス自体は変更しない |
| F-2配置 | 5固定UUIDと公式戦タイブレーク機械文字列はPO採用済み。5既定値と出所、候補行の既存衝突なら全停止。FORCE RLS下のowner専用一時ポリシー→同一transactionで配置→ポリシー除去、次revisionで読取関数/ACL。保守停止下で実施 | 配置・一時RLS・revision順は移行/認可面所有者の個別ゲート。値・意味はF-2で確定済み |
| 関数/凍結資産 | `public`の読取専用1関数、候補ownerのschema USAGE・列SELECT・親/既定/規則行ロックに必要な列UPDATE、PUBLIC EXECUTE剥奪/app限定EXECUTE、GUC/tenant照合。対象資産と7.7手順・担当を提案 | 認可面/tenant境界所有者がowner/権限/直接SQL脅威モデルを採否。7.7の新digest・変更後基準の受理は実資産変更後のステップ3・4 |

本案の敵対レビュー第1回はP0=0/P1=3/P2=1。FORCE RLS下の配置経路、3表の行ロック権限、7.6同一PR、7.7の受理直前実状態を**全件採用して修正**した。第2回は割当照会の行ロック解釈にP1=1、通常SELECTへの明記後の限定第3回は**P0/P1=0**。実DBの競合試験と正式ゲートを代替するレビューではない。ステップ1は未完了、製品コード・ステップ2には進まない。

| Aの契約項目 | 受理状況 | 未成立なら起こること・次の受理先 |
| --- | --- | --- |
| JSONB内 `ruleSetId` + 凍結5値 | Codex D `24566d72` で**条件付き採用**。snake_case案は撤回 | exact-set codecと利用側U-G1の受理が必要。旧 `{}` を解決済みにしない |
| 全体既定の帰属・割当あり拒否・同一scope | 割当あり拒否と全確定/全取消の意味はCodex Dが採用。帰属は条件付き採用 | 既存行の出所、管理書込権限、全入口ロック順と保持期間をU-X1/認可面/tenant境界へ受理依頼。証明できない行は拒否 |
| 公開関数/成功型/4失敗/固定operation | Codex D `24566d72` では**未受理**（固定operationは条件付き） | U-X1・U-G1・tenant境界に具体signature/literal/登録差分を提示し回答を得る。仮operationで保存成功にしない |
| 実規則データの供給 | **値は要件書付録F-2で2026-07-22確定済み**。製品管理書込関数・F-2値の配置seedは未確認 | 推奨はF-2値/ID/出所と既存行衝突拒否を個別審査したデータmigrationをTSK-550ステップ3に含める。値自体を再裁定しない。管理者専用書込関数は後続の別差分で、権限/監査/競合保護の個別ゲートが必要。配置未了なら `rule_not_available` 等で全取消。RG1実operationもなければU-G1作成成功に届かない |
| 実測 | `24566d72` 時点では未実施 | TSK-550ステップ3〜6で実関数/2接続/故障注入、TSK-395ステップ2で実HTTP/RG1/全取消。実装前条件にはしない |

**次の具体差分**: `plan.md` のステップ2をstrict codecへ、3〜6を段階Aの実関数→固定operation→resolver→実測へ訂正した。正本の具体本文、関数DDL/ACL、repository-contract/7.7差分は各担当の契約受理と個別ゲートを経て起案・実施する。段階B、帰属列と曖昧な旧行の移行は今回確定しない。RG1①〜⑤のU-G1受理 `79e3da4a` は維持し、D4外部台帳はpreparingの条件に入れない。

## 最終差分への受理依頼（A追補承認後・実装前）

以下は`24566d72`で未受理/条件付きだった項目に絞る。Codex Dの先の採用項目（割当あり拒否と同一transaction全確定/全取消の意味）やRG1①〜⑤を再審査対象へ戻さない。回答は項目ごとに「受理／条件付き／不足」と、その条件・担当・必要な正本/資産ゲートを記録する。**実関数の2接続/故障注入を本回答の前提にしない。**

| 対象・回答先 | 実装前に確定する提案 | 未受理なら止まる境界 |
| --- | --- | --- |
| 公開関数・型・失敗：U-X1独立担当Codex D、消費側U-G1 | 束縛済み`tenant_transaction_scope`を受ける`resolve_stage_a_rule(request)`相当。入力は試合区分キー・必須大会キー・上書き有無で、任意tenant ID/rule IDなし。成功は不変`AppliedRuleSnapshot(UUID+付録F5値)`。公開失敗候補は`stage_a_unsupported`、`rule_not_available`、`invalid_rule`、`outcome_unconfirmed`。候補なし/越境は利用者向け外形を同じにし、非成功ではgame INSERTへ進めずscopeを全取消 | 関数名・具体型・literal/HTTP写像の担当受理までステップ1未完了。HTTP実測はTSK-395ステップ2 |
| 保存形式：Codex D、U-G1、data-model所有者 | 既存`games.applied_rules` JSONBに`ruleSetId`と凍結`ruleSnapshot`のcamelCase5値をexact-setで保存。旧`{}`、未知key、無効相関、出所不明行は拒否。ID専用列/帰属列は段階Aの前提にしない | 保存形の正本差分と利用側受理が必要。codec実装/単体試験はステップ2 |
| 帰属・書込・ロック：Codex D、U-A2/認可面、tenant境界、U-G1/U-R1 | 段階A成功は付録F-2由来の出所が証明された区分既定行だけ。app直接権限は`game_type_rule_defaults` SELECTのみ、他2表SELECT/書込なし、3表の直接書込なし。大会親`(tenant_id,key)`の`FOR UPDATE`→割当有無→既定行`FOR SHARE`→規則行`FOR SHARE`→game/RG1→commitを候補とし、ロックはcommit/rollbackまで保持。割当書込を有効化する場合は同じ親行を先に取り、管理書込も既定→規則の順に固定。現時点で製品管理/割当書込関数は未実装と明示 | 全入口のcaller・owner・EXECUTE・ACL・監査、親不在/無効化/解除、線形化点と全ロック順の受理が必要。安全な入口がない操作は無効のまま。実装済み入口の2接続実測はステップ3〜6 |
| 実規則データ：Codex D、data-model/認可面所有者 | 確定済み付録F-2の5区分を、出所・ID・5値を検証可能な**個別審査後の配置migration**で供給。既存行衝突・出所不明時は停止。migrationを製品runtimeの管理書込入口と混同せず、配置と製品作成の同時運用を認めるなら保守停止または同じロック規律を個別ゲートで決める | 具体的データ・migration・運用順は未承認。配置が未着地なら`rule_not_available`等で全取消、U-G1本番作成成功は未達。配置migrationの実装はステップ3の個別ゲート後 |
| 固定operation：Codex D、tenant境界/認可面所有者 | `OperationRegistration`の表DML許可を緩めず、固定関数ID・exact引数/戻りdecoderを持つsealed function operationをscopeへ限定追加。任意SQL/Session/偽造token/任意tenant注入を拒否 | `repository-contract.json`、runtime authz、capability/DDL、`base-allowlist.json`/履歴の具体差分と7.7受理手順をステップ1で確定。実装・負例試験はステップ4 |

**正式ゲートの順序**: ①`docs/features/product-impl-unit-split/{plan,design}.md`とU-X1文書の先行切り出し/凍結文言を7.6で規範変更か実装追随か判定し、規範変更なら7.3で確定。②`docs/design/data-model.md` §6-5/10-5の6-key保存形・既存行拒否・F-2配置/出所の意味、必要なschema変更の有無を具体本文で審査し、構造変更なら7.3で確定。③`docs/features/product-authz-surface/design.md` §1-6の関数owner/EXECUTE/表ACL・管理書込境界と、tenant境界の固定operation契約を各所有者が受理し、規範変更なら7.3へ。④具体DDL/migration、認可資産、`repository-contract.json`等の凍結資産は**各差分を提示後**に7.7の対象・担当・手順を固定し、変更後の基準受理をステップ3・4で実施。今回の計画承認を①〜④の個別承認に代えない。TSK-550の実関数2接続/故障注入はステップ3〜6、TSK-395の実HTTP・RG1・保存全取消はステップ2で測定する。

## `df0db54b` 回答との項目別照合（2026-10-14）

Codex D の独立ブランチ `feature/tsk550-contract-evidence-split` の `df0db54b` は、**契約・証跡分離の具体案**であり、同文書自身が「未承認追補案」「ステップ1未合格」と記す。後発のPO判断Aと計画HEAD `a2b8a5b5` に採用された部分を成立済みとして扱う一方、Dが書いた案を他担当の受理や個別資産承認へ読み替えない。先行する独立差分判定は `24566d72`。下表は回答済みと、回答後も必要な差分を分ける。

| 項目 | 回答コミット・採否 | 残る差分・担当 |
| --- | --- | --- |
| 契約と実測の時点 | `df0db54b` §1/3/4で具体回答。POのA判断と承認済み計画に**採用済み**。ステップ1は契約/ゲート、実関数2接続・故障注入はTSK-550ステップ3〜6、実game/RG1/HTTPはTSK-395ステップ2 | 試験表に沿う実装後証跡だけが残る。TSK-550担当、U-G1担当。ステップ1の再回答事項ではない |
| 解決関数・入力/成功型 | `df0db54b` §2.1/2.3でDB署名と不変snapshotを提示。**具体案として採用、最終契約は条件付き**。任意tenant/rule IDを受けない点は先のD回答と整合 | `tournament_key: null`候補とU-G1作成の必須大会キー、公開Python関数の正確な署名/型を一致させる。Codex D（独立受理）・U-G1（消費側）。SQL署名/ownerは認可面の個別ゲート |
| 6-key保存と旧行 | `24566d72`でJSONB内ID+5値を条件付き採用、`df0db54b` §2.3で`ruleSetId`+凍結camelCase5値、exact-set/旧`{}`拒否を具体化。**保存案は収束、個別正本未確定** | `data-model.md` §6-5/10-5の意味差分とU-G1保存mappingの受理。data-model所有者・U-G1。codec実装/試験はステップ2。ID専用列は追加しない |
| 割当あり拒否・失敗分類 | 割当あり拒否と同一transaction全取消の意味は`24566d72`で**受理済み**。`df0db54b` §2.4が4 literal/秘匿/再送禁止を提示。**literalとHTTP外形は未受理** | `stage_a_unsupported`/`rule_not_available`/`invalid_rule`/`outcome_unconfirmed`の公開型とU-G1のHTTP写像、非成功からgame INSERTへ進めない境界をCodex D・U-G1が項目別受理。実HTTP試験はTSK-395ステップ2 |
| 帰属と実規則データ | `24566d72`の既定表経由は条件付き。`df0db54b`は管理書込関数案を示したが、現行承認済み計画のF-2配置migrationとは別経路。**配置データ・既存行衝突・運用順は未承認** | F-2確定値のID/5値/出所を個別審査した配置migration、衝突時停止、配置中の保守停止または同等の排他を具体化。data-model所有者・認可面/移行所有者・Codex D。製品管理書込を開く場合は別差分/ゲート |
| 大会割当の書込入口とロック | `df0db54b` §2.1/2.2の`upsert_tournament_rule`追加は**今回不採用**（PO判断）。現行製品には割当表の書込関数もapp直接ACLもなく、段階Aは閉じた書込面で割当存在を判定・拒否できる。親行→割当判定→既定→規則→game/RG1の取得順・commitまで保持はDの具体案 | app/管理/owner/migrationの実際の書込権限と入口を認可面・tenant境界が確認し、製品割当書込を開かない範囲・配置時の排他を固定する。Codex Dは**書込関数なしの閉鎖モデル**で安全性を再判定。将来入口を開く場合だけ同じ親ロック、全順序、2接続試験を個別ゲートへ。未実装入口の製品試験をステップ6の条件にしない |
| 固定function operation | `24566d72`は条件付き採用、`df0db54b` §2.5がsealed token/固定ID/引数/decoder/任意SQL拒否を提示。**方式案は回答済み、登録契約は未受理** | repository/tenant境界所有者が既存DML非緩和、実際のAPI・`repository-contract.json`差分、偽造token拒否を受理。認可面所有者がcapability/DDL/EXECUTEを受理。凍結7.7の対象/手順を固定し、実装と負例はステップ4 |
| 正本・凍結のゲート | `df0db54b` §5でdata-model/authz/repository/U-G1を分けて回答。PO承認済み計画の7.6/7.3/7.7の**対象整理に採用** | 各所有者が具体本文/差分を受理し、規範変更なら7.3で確定。DDL/migration・authz・repository凍結差分は個別審査後に7.7。計画承認を資産承認にしない |

**閉じた段階Aの成立範囲**: 現行製品コードの割当表使用はORM定義だけで、製品用書込関数は見当たらない。認可資産の`pitchlog_app`にも割当表の直接ACLはない。従って**割当書込関数の新設は段階Aの必須条件ではない**。既存の割当行があれば制限関数は拒否し、親大会行を先にロックして無効化・更新との競合を制御する。DB owner/migrationの特権書込まで「存在しない」とは言わず、製品作成と配置の同時運用を禁止する保守停止、または承認された同等の排他を個別ゲートで固定する。もし既存の製品割当書込実経路が後に見つかれば、そのファイル・caller・権限と親行ロックの最小差分を受理シートへ追記するまで段階A成功に使わない。`df0db54b` §3の割当書込との2接続ケースは**将来入口を開く際の試験表**として残し、未実装入口をステップ1の契約受理やステップ6の完了試験へ混入させない。

**`df0db54b` 時点で真に未回答だった受理先**: Codex Dには閉鎖モデルと公開型/4 literalの最終採否、U-G1にはsnapshot保存/HTTP/非成功境界、data-model所有者には6-key/出所/既存行の正本文、認可面/tenant境界所有者には閉鎖ACL・個別7.7差分の採否が残っていた。**Codex D項目は後の`06f7834f`で、固定operation契約はPO代替受理で解消した**。この段落は当時の照会履歴で、最新の未回答一覧は冒頭表とする。

## 固定function operationの最終契約案（PO代替受理済み・具体資産未承認）

POは**この項目に限り**、候補作成に関与しない独立担当の査読後に下記の修正後契約を代替受理した。査読・代替受理は具体的な凍結資産変更の承認ではない。現行の`operation_registration.py`/`operation_registry.py`は表DMLの`Select/Insert/Update`と`tenant_column`を要求し、`_TenantTransaction.run`は生成済みregistryのexact token型、frozen dataclass、capability ID、束縛済み`TenantContext`を検証する。`TenantRepositoryBase.execute`の別scope関数面を試合作成の同一transactionへ流用しない。以下をステップ1の受理済み契約境界とする。

| 査読軸 | 最終案と拒否条件 |
| --- | --- |
| 登録型・公開入口 | 既存`OperationRegistration`/`PRODUCT_OPERATIONS`/`_TenantTransaction.run`の表DML分岐は変更しない。別のfrozen登録型`FunctionOperationRegistration`をexactな`StageAResolveRuleToken`へ1対1で登録し、`_TenantTransaction.run_function(token)`だけがこれを実行する。registryは起動時に**既存DML集合と横断して**重複ID/型と契約不一致を拒否。最初の登録対象は段階A解決関数1件だけで、管理/大会割当書込関数や任意の関数登録APIは含めない |
| token不変性・引数 | `StageAResolveRuleToken`は`TenantOperationToken`に従うfrozen/slots dataclassとし、業務入力は`game_type_key: str`、**必須**`tournament_key: str`、`rule_override_present: bool`だけ。tokenには関数名、SQL、capability IDの可変値、tenant ID、規則ID、decoder、Sessionを持たせない。exact型と登録時固定のcapability/function ID・全業務値を**実行直前**に再検証し、未知/派生型、不正値、不一致ID、空/不正keyを拒否する。**同じ型のtokenは呼出側が生成・強制変更できるため、token自体を権限証明とは扱わない**。権限境界は発行済みtenant context、固定registryとDB ACLに置く。`df0db54b`のnullable大会キーはDB署名上の候補であり、U-G1作成入口で`None`成功を許す契約にはしない |
| tenant束縛とSQL | 既存`tenant_transaction_scope`の同じhandle・Session・transactionだけを使い、`run`と同じ`_state_key`失効検査、`TenantContext` exact型・tenant ID・発行証跡の再検証を**実行直前**に行う。関数専用検査で、**schema修飾した1つの固定関数呼出しだけ**を含むSQLAlchemy `select()`、関数identity、exact bind集合/型、戻り列を**起動時**に照合する。表DML専用`_validate_prepared_statement`を関数へ流用しない。実行時は固定文を再利用して検証済みbind値だけを渡し、汎用`prepare`やcaller提供のSQL引数を設けない。tenant IDを関数引数やtokenから取らず、DBのtenant GUCは既存`_tenant_transaction`だけが設定。callerが`text()`、SQL断片、関数名、戻り型、直接Sessionを渡す経路はない |
| 戻りdecoder | 実行結果を同一transaction内で全件実体化し、登録時固定decoderが**1行・固定列順/型・許容statusと成功/失敗のnull配置**を検査して既存のexact `TenantOperationResult`へ閉じる。遅延`Result`/ORM/可変dictを返さない。付録Fの値域・相関と`ruleSetId`+5値の唯一の業務codecはステップ2/5の単一実装を再利用し、登録decoderに複製しない。decoder違反/DB例外はscopeを例外終了し、成功扱いしない |
| 既存DMLと凍結契約 | 既存の表DML registry、`_validate_prepared_statement`、`TenantRepositoryBase.execute`、`TenantOperationResult`の既存許可集合を緩めない。新しい`run_function`/token型と固定登録IDのみを`repository-contract.json`、runtime authz/capability、生成契約、allowlist/履歴の**具体差分**として7.7個別ゲートへ提示する。関数ownerの必要列権限/RLS突破条件、PUBLIC EXECUTE剥奪、appの固定関数EXECUTE、固定`search_path`、関数内のGUC欠損/不正と親大会不整合の拒否は認可面の個別ゲートへ渡す。`run_function`の実装・bypass負例・変更後基線受理はステップ4で行う |

**査読で特に判定する点**: 固定SQLAlchemy文の構造検査を登録時にどの方法で保証するか、`TenantOperationToken`基底の`capability_id`がtoken入力で偽装されないか、関数の`SECURITY DEFINER`/固定`search_path`/EXECUTE対象とscopeのtenant GUCが一致するか、結果の構造decoderと業務codecの責任分界、DML側の既存拒否試験が無変更でgreenか。関数の実名/schema/ownerと凍結JSONのexact差分は認可面・個別7.7ゲートで確定するため、この査読のみで採用しない。

**独立査読結果（候補作成に不関与のCodex、2026-10-14）**: 契約案の現行リポジトリ実装との照合でP0=0、P1=3。P1①同型tokenは生成・強制変更できるためtoken自体を権限証明と呼べない、②表DML用検査では関数SQLの固定性を証明できず、起動時の関数専用構造検査とDML横断重複拒否が必要、③関数owner/RLS/列権限/PUBLIC EXECUTE/GUC拒否は認可面の個別ゲートが未確定、という指摘。①②は上表の最終案へ採用・補正した。③は必要な個別ゲートとして具体化し、承認済み資産とはしない。戻りdecoderと既存DML非緩和の方針は適合との判定。**本査読はPO代替受理の判断材料であり、契約受理・凍結変更承認の代記ではない。**

| ステップ1項目 | 現在の採否 | 完了に残る条件・判断先 |
| --- | --- | --- |
| 段階Aの範囲、割当あり拒否、同一transaction全取消、契約/実測分離 | **成立済み**。`24566d72`、`df0db54b`、POのA計画承認 | 実測は後続ステップ。ここを再受理待ちへ戻さない |
| 割当書込入口 | **追加見送り・閉鎖モデルを受理**（PO、Codex D `06f7834f`）。製品書込関数とapp直接ACLは現行で未確認 | 認可面/U-A2の特権/管理入口と配置時排他は個別認可/データ配置ゲートへ。製品割当書込の実装/試験は要求しない |
| 規則ID+5値の保存案 | Codex Dが条件付き採用、`df0db54b`で形状を具体化 | data-model正本の6-key/旧行/出所の個別ゲート、U-G1保存mappingの採否 |
| 公開型・4 failure | `06f7834f`で必須大会キーを含む入力と4 literalを**Codex Dが受理** | U-G1の保存mapping/HTTP写像は消費側実装・保存形の個別受理へ。実HTTP試験はTSK-395ステップ2 |
| 固定function operation/repository境界 | 上記の**修正後最終案は独立査読済み・PO代替受理済み**（P0=0、P1 3件のうち契約文2件補正、1件を認可ゲートへ分離） | 関数owner/EXECUTE等とrepository-contract/allowlistの具体差分は個別7.7ゲート、実装/負例はステップ4 |
| F-2配置・正本/認可/凍結ゲート | F-2の5値は確定済み。配置案と7.6/7.3/7.7の対象は整理済み | data-model・認可面/移行所有者による具体差分/運用順の受理と必要な正式正本承認。migration、認可、凍結資産の実変更は未承認 |

**照会先と到着状況**: Codex Dへ閉鎖モデル・型/4 literalの差分をTSK-550コメント`3f993b75-e687-81fc-8035-001d18acc98b`で照会し、**`06f7834f`の回答を受理**した。U-G1へ保存/HTTPをTSK-395コメント`3f993b75-e687-818c-bfb3-001d79b28346`、認可面へ閉鎖ACL・関数権限・配置時排他をTSK-424コメント`3f993b75-e687-811f-9eea-001d3d158499`、data-modelへ6-key/出所/正式ゲートをTSK-250コメント`3f993b75-e687-817a-aa1f-001d30743b07`、U-A2へ現存管理入口をコメント`3f993b75-e687-8103-b64a-001d867c382c`で照会した。固定operationの担当調整はTSK-390コメント`3f993b75-e687-8121-bcf5-001d36309e9b`の履歴に残すが、**PO代替受理で契約判断は成立**した。残る回答は冒頭表の保存形・正本・データ配置・認可資産ゲートに限定する。

## 段階 A と段階 B

| 段階 | 成功と拒否の境界 | 現時点 |
| --- | --- | --- |
| A（先行） | 安全に帰属を証明できる全体既定だけを解決し、規則 ID と付録 F の値をスナップショットとして試合作成と同じ transaction で保存。対象大会に割当があれば既定へフォールバックせず拒否。規則の出所を証明できない、割当有無を安全に判定できない、値が無効、読取に失敗した場合も成功しない | POの方向性、Codex Dの閉鎖モデル・入力/4失敗、固定operationのPO代替受理は成立。保存形の消費側・正本/配置/認可の個別ゲートは未完了 |
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
