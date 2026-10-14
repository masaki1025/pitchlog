---
feature: ux1-fr014-rule-resolution
status: active
承認: 済(2026-10-14・山田正輝・A追補a2b8a5b5)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc
branch: feature/ux1-fr014-rule-resolution
created: 2026-10-14
計画レビュー周回: 4
確定ゲート周回: 1
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-X1／FR-014 安全な規則解決の先行実装

## 1. 背景・目的

TSK-550 は、PO の 2026-10-14 J-3 裁定で TSK-539（U-X1 計画）から切り出した FR-014 の先行実装タスクである。TSK-395（U-G1）は `preparing` 作成時にこの結果を消費する。実装担当は現 U-G1 担当、**ドメイン所有は U-X1**。別 worktree・本タスクだけの 1 PR とし、U-G1 の製品コードへ混在させない。本裁定は製品実装・正本改訂・スキーマ/認可/凍結資産変更の承認ではない。

**計画承認（2026-10-14、PO）**: HEAD `93d2f49c` の本計画を承認し、ステップ 1 のみ指示。段階 A は安全に帰属を証明できる全体既定だけを解決し、規則 ID と値のスナップショットを同一成功境界で保存する。対象大会に割当がある場合は、既定へフォールバックせず拒否する。段階 B は大会割当・試合上書き等の後続。段階 A/B は本タスクの実装順の区別であり、**個別の正本・スキーマ・認可・凍結資産変更の承認ではない**。ステップ 1 の照合結果は [接続受理シート](step1-contract-acceptance.md)に記録し、未受理ならステップ 1 を完了扱いしない。

**A案の範囲判断（2026-10-14、PO。追補の最終承認前）**: 実装前契約をステップ1、実関数の2接続/故障注入をステップ3〜6、U-G1の実HTTP・RG1・全取消をTSK-395ステップ2で検証する。段階Aは全体既定の安全な解決、規則ID+5値の保存、U-G1との同一transaction接続までを維持する。この節以下の変更は最終計画承認対象であり、旧計画の承認を新範囲へ自動延長しない。個別の正本・schema・認可・凍結資産変更も未承認。

**A追補の最終計画承認（2026-10-14、PO）**: 計画HEAD `a2b8a5b5f7e1c1869164770a38044361c7ab03b6` を承認し、**ステップ1のみ**指示。付録F-2配置migration案は最終機械レビュー後の追加差分であり、POの人間確認対象として[作業ログ](../../worklog/2026-10-14-ux1-fr014-rule-resolution.md)に記録する。この承認は具体的な配置データ、migration、認可、凍結資産の承認ではない。実装前契約と必要な正式ゲートを受理記録へ固定するまでステップ1を完了扱いしない。後続の実製品試験完了をステップ1の条件にしない。

**開始条件の最小追補承認（2026-10-14、PO、`e19f8651`）**: ステップ2のcodecと単体試験は、`data-model.md` §6-5の6-key保存契約と旧行拒否が正式7.3で確定した後に限り、ステップ1全体の未了と独立して先行できる。関数権限・配置migrationはステップ3、固定実行器・凍結契約はステップ4の着手前条件とする。TSK-550全体とステップ1全体は未完了のまま維持する。今回の追補は個別正本・認可・配置・凍結資産変更を承認しない。

**保存前検証境界の追補承認（2026-10-14、PO、`35c5f599`）**: codec結果は6-key形・UUID・5値schema上の型と単独値域を確認した**構造検証済み値**であり、ドメイン検証済みsnapshotやDB保存成功を意味しない。値間相関・規則行の出所は後続resolverが既存の単一規則実装で保存前に検証する。未検証値とコールド条件の矛盾例を有効として保存しない。FR-014と付録F-1 `DRAW-04`の不整合は保存成功経路の実装前に別途裁定し、この追補では解決しない。§6-5の正本編集担当は所有側が対応できない場合に限りTSK-550担当とし、独立査読とPO代替受理、正式7.3・人間承認を省略しない。

**保存本文の正式確定（2026-10-14、PO）**: `ca0a51ef`の正式7.3審査済み§6-5本文を`48e8a562`でapprovedに確定し、本文限定のPO代替受理を記録した。本featureには承認本文だけを取り込む。codecは既存schemaによる形・値域検査と、単一経路の付録F-1値間相関検査を区別する。出所の証明と保存成功の可否は後続resolver/TSK-395の同一scope境界で判断する。TSK-550全体・ステップ1全体は未完了。

現行 `rule_sets` には帰属列がなく、`rule_sets` と `tournament_rule_assignments` は `function_only`。直接読取を開かず、段階Aでは安全に帰属を証明できる試合区分の全体既定だけを解決し、付録Fの検証済み規則ID+5値を同一 transaction 内の試合作成へ渡す。大会割当・試合上書きがある場合は拒否し、FR-014 の全優先順位は段階Bに残す。TSK-539 の T1〜T6 状況・終了計算は実装しない。根拠は [調査](research.md) と [設計論点](design.md)。

## 2. スコープ

### 対象

- U-X1 所有の公開解決関数と不変の入出力型。候補なし、越境、無効/矛盾規則、読取失敗を内部で区別し、いずれも解決成功を返さない。越境では他テナントの存在情報を漏らさない。TSK-395 の利用者向け応答では候補なしと越境の外形を同一にする契約・試験条件を引き渡す。
- 付録 F の全5値と規則IDを保存前に検証する単一codec。既存 `games.applied_rules` JSONB に `ruleSetId` と凍結済み `$defs.ruleSnapshot` の camelCase 5値を格納し、旧 `{}` や出所不明の行を成功へ補完しない。既存の単一規則実装・契約を使い、T1〜T6 やクライアントへ計算を複製しない。
- 全体既定の帰属証明、割当存在判定と拒否、制限関数、登録済み operation の安全な呼出し、読取と U-G1 保存が同一 `tenant_transaction_scope` に収まる契約。作成側の保存自体は TSK-395。
- 実 DB による二テナント、故障、並行変更、解決 operation の同一 scope/rollback の試験。**試合保存との全取消と保存済み snapshot の非遡及は TSK-395 の結合試験**。関連する正本・認可・凍結基準の正規ゲートとコア領域レビュー。

### 対象外

U-G1 の HTTP/試合 INSERT、スタメン・開始、U-X1 の T1〜T6、規則管理 UI、段階Bの大会割当/試合上書きの解決と設定操作、RG1/D4、仮規則、仮の保存成功。既存行の曖昧な帰属を推定で埋めない。

## 3. 影響する正本・資産とゲート

| 対象ファイル | 意味差分の候補 | 必要なゲート |
| --- | --- | --- |
| `docs/features/product-impl-unit-split/{plan,design}.md`、`docs/features/ux1-state-calc/{plan,design}.md` | U-X1 の対象計算の凍結を維持しつつ、**FR-014 読取/検証/帰属だけ**を TSK-550 に先行分割した事実へ追随。TSK-539 第1 PR へ取り込まない | 所有側受理と本計画レビュー。単位帰属・凍結の規範を変更するなら 7.6 の構造変更として 7.3 敵対レビュー＋人間承認。単なる実装追随か事前に判定 |
| `docs/features/product-authz-surface/design.md` §1-6 | `function_only` の2表の制限関数を記録。`game_type_rule_defaults` の既存SELECTを保持し、3表の直接書込権限は開かない。帰属列は段階Bの個別判断 | 認可面所有者の確認、規範変更なら 7.3。実装追随の節更新のみなら同一 PR のレビュー |
| `docs/design/data-model.md` §6-5/§10-5、必要なら `docs/README.md` | 段階Aの全体既定の帰属証明、`applied_rules` 内のID+5値、旧行拒否、実規則データの出所を明記。帰属列や既存行移行が必要になれば別差分 | スキーマ/アーキテクチャの構造変更なら7.6により7.3敵対レビュー＋人間承認。単なる実装追随はPRレビュー。承認本文より先にmigrationを確定しない |
| `docs/requirements/requirements-pitchlog-2026-07-22.md`、`docs/adr/ADR-003-domain-calc-method.md`、`docs/development/dev-harness-design-2026-08-07.md` | 現時点で反映なし。FR-014/付録 F と対象計算の境界を変える必要が出たら作業停止し別の確定ゲートを提案 | 今回は変更しない |
| `backend/migrations/versions/<新revision>.py`、`contracts/db/schema-manifest.json` | 段階Aの制限読取関数と必要なACL/所有ロール、付録F-2の確定値を出所付きで配置するデータmigration。帰属列と曖昧な既存行の推定移行は予定しない。管理書込関数は別の具体差分 | 正本/認可面所有者の受理と個別の必要な7.3/7.7ゲート後。関数DDLとデータ配置のrevision/実行順はステップ1で固定し、番号は着手時headに合わせ、実DB移行/衝突拒否/権限試験 |
| `contracts/authz/product/{table-classification.json,exposure-facts.json,ddl-elements.json,capability-catalog.json,application-steps.json,function-bodies/**}`、`contracts/tenant_boundary/{runtime-authz-contract.json,base-allowlist.json,history-snapshots/**}` | 制限関数、実行権、呼出しcapabilityと露出事実。`rule_sets`・`tournament_rule_assignments` のapp直接SELECT/書込は不付与、`game_type_rule_defaults` は既存SELECTを保持し書込は不付与 | 認可面所有者受理。7.7 の基準変更が生じる場合は `base-allowlist.json` の単一受理履歴・必要な snapshot を追記し、基線試験を通す。凍結資産を検査だけ緩めて通さない |
| `backend/src/pitchlog/repositories/{operation_registration.py,operation_registry.py,transaction.py,repository_contract.py,rule_resolution.py}`、`backend/tests/test_rule_resolution.py`、`contracts/tenant_boundary/{repository-contract.json,base-allowlist.json,history-snapshots/**}` | テナント束縛 scope から安全に関数を呼ぶ登録経路・型・失敗結果。`rule_resolution.py` は既存 `repositories/*` glob に入る。`repository_contract.py` は実装、JSON は凍結された公開契約 | **現行登録型は tenant_column 付き表 `Select/Insert/Update` のみ**。直接 Session 逃げ道は不可。JSON 契約の改訂が必要なら変更案の担当受理を先に得て、当該変更後の 7.7 受理と `base-allowlist.json` の単一受理履歴・必要な snapshot を同ステップの完了条件とする。確定ゲートの文書反映はステップ記法なしの別コミット。対象ファイルの実変更は設計受理後に限定 |
| `scripts/core_guard.py`、`tests/test_core_guard.py`、`.claude/core-areas.json` | 新規 `backend/tests/test_rule_resolution.py` を tenant-isolation と game-state へ宣言・登録。製品モジュールは既存 tenant-isolation glob に入る。既存3パスは merge-base の JSON 基線に保持する。`tenant-isolation` の AREA_PATH_ADDITIONS は新規試験パスだけへ**差し替え**、`game-state` へ新規追加する | 6.3 のコア領域敵対レビュー＋人間確認。宣言・テストと JSON 登録を別コミットにする |

## 4. 実装方針・ステップ

**着手前の独立受理**: U-X1 の独立受理担当は Codex D と指名済み。公開関数名・入力型（試合区分、大会、上書き、束縛済みscope）、検証済みスナップショット型、4失敗結果、同一scopeの読取/保存/全取消と実データ供給・閉じた書込入口の最終受理を得る。TSK-395呼出側、認可面/テナント境界側も受理する。`24566d72` は条件付き/不足を残す差分回答であり、全体を受理済みと扱わない。

**設計停止条件**: (a) 全体既定の帰属と既存行の出所、管理書込の権限・全入口の競合保護、実規則データの供給、(b) 制限関数の `SECURITY DEFINER` 等の安全条件・実行権・search_path と越境結果、(c) 固定function operationの登録・必要なrepository-contract改訂、(d) 大会割当あり/上書きありの拒否と、規則マスタ並行変更時の一貫性/ロック期間を、U-X1・U-G1・認可面/テナント境界所有者と該当正本ゲートで決める。未確定の値を製品に置かない。

**段階 A/B のステップ 1 接続整理**: 段階Aの実装契約は、全体既定の帰属証明、対象大会の割当有無の安全な判定と割当ありの拒否、規則ID+5値のスナップショット、同一scopeの読取・保存・全取消を含む。段階Bの大会割当/上書き解決は段階Aの成功として扱わない。保存形は既存 `games.applied_rules` JSONBに `ruleSetId` + 凍結5値を推奨し、専用列がないことだけを列追加理由にしない。`rule_sets` に帰属列はないため、既定表の参照**だけ**でなく、書込主体・既存行の出所・制限関数を含めて帰属を証明する。証明不能な行は拒否する。新しい列、関数、ACL、凍結基準を本計画だけで確定しない。

**実規則データの供給と未整備時の拒否**: 要件書付録F-2の5区分の既定値は**2026-07-22確定済み**。現行の3規則表に製品用管理書込関数と、F-2値を配置した製品seedは見つかっていない。段階Aの推奨供給方法は、F-2の実値を厳密に写し、規則ID/5値/出所を検証できる**個別承認後のデータ配置migration**である。値そのものを再裁定せず、ID・データ表現・migration・既存行衝突時の拒否を具体差分として審査する。認証済み管理者専用RuleSet/区分既定書込関数は後続の運用変更経路として別ゲートで設け、製品用関数が現存するとは扱わない。app/チーム経路では `rule_sets`・`tournament_rule_assignments` の直接権限を付与せず、`game_type_rule_defaults` の既存SELECTを保持して3表の直接書込を拒否する。後続管理関数は所有ロール・EXECUTE対象・監査を固定し、既定対応の差替えは既定行→旧/新規則行、規則値更新は同じ順序で競合保護する。大会割当書込を有効化するなら大会親行→割当→既定→規則行の全順序を受理・実測する。migrationは既存の曖昧な行を推定で採用/更新せず、出所を検証できない衝突は停止する。無効な親・出所不明行・配置未了・必要な入口/保護が欠ける環境では `rule_not_available` 等の受理済み失敗として全取消し、U-G1は試合作成成功を返さない。**TSK-550段階Aのresolverだけでは、F-2データの安全な配置とRG1実operationがない環境のU-G1試合作成成功に届かない。** この依存を承認対象に含める。

**計画の人間承認前には、ステップ 1 を含む実装ステップへ入らない。** 承認前は計画起案・レビューと担当調整だけを行う。承認後、ステップ 1 の着手前に単位分割・U-X1 計画の凍結文言是正が**規範変更か実装追随か**を 7.6 で判定する。規範変更なら 7.3 の確定ゲートと人間承認を先に通す。`data-model.md` の起案は**ゲート側・ステップ記法なし**のコミットに置く。7.7 はステップ1で対象資産・受理手順・担当を決め、実際の資産変更後の基準受理を各実装ステップで行う。ステップ2前の正式ゲートは§6-5の保存契約・旧行拒否だけとし、他の正本・資産ゲートは該当ステップ前へ分離する。正本確定ゲートの反映周コミットはステップ記法を付けず、ステップ 1 の別コミットは受理済み契約・移行判断・登録経路とゲート証跡を文書へ固定する。外部受理が揃わなければステップ 1 は緑にならないが、§6-5確定後のステップ2先行だけは上記追補に従う。

### 実装ステップ

| # | ステップ（別コミット） | 合格条件 |
| --- | --- | --- |
| 1 | 段階Aの実装前接続契約、既存行の出所判断、実規則データ供給と閉じた管理書込、固定登録経路、必要な正本/認可/7.7ゲートの対象・担当・順序を受理記録へ固定 | U-X1独立担当・U-G1・認可面/テナント境界担当が公開関数/型/4失敗、ID+5値、全書込入口の権限/ロック順・保持期間、同一scope、未整備時の拒否を受理。必要な正式正本承認を得て、個別資産差分の7.7受理手順を固定。**未実装の2接続/故障注入は合格条件に含めない**。未受理でもステップ1全体は未完了とし、§6-5確定後のステップ2先行を妨げない |
| 2 | `games.applied_rules` JSONB の単一strict codecと付録F検証・試験 | **着手条件: `data-model.md` §6-5の6-key保存形・旧行拒否が正式7.3で確定すること（`48e8a562`で成立）。** `ruleSetId` + 既存凍結schemaのcamelCase5値をexact-setでencode/decodeし、UUID/型/値域・round-tripを検査。旧 `{}`、5-key、不正な値を拒否する。構造検証済み値はドメイン検証済みsnapshotと型で区別し、単一の付録F-1相関検査を通した値だけを後者に昇格する。規則行の出所はcodecだけで証明せず、後続resolverが保存前に確認する。未検証・矛盾例は保存成功へ進めない。帰属列migration、仮の既定値、保存成功の擬装を加えない |
| 3 | 段階Aの制限読取関数migrationとACL/認可資産、付録F-2データ配置migration、実DBの権限・越境・故障試験 | **着手前に**§10-5の出所/割当拒否と相関規則の矛盾、関数owner・RLS・EXECUTE・tenant GUC、配置migrationの出所/衝突/一時RLS/排他/downgrade、認可・移行資産の個別ゲートを確定する。`pitchlog_app` は `rule_sets` と `tournament_rule_assignments` の直接SELECT/書込を拒否し、`game_type_rule_defaults` は既存 `global_read_only` のSELECTを保持して書込だけ拒否する。関数は自テナントの大会割当があれば全体既定へフォールバックせず拒否。親行→既定行→規則行の取得・保持を検証。データ配置は個別の正式ゲート後にF-2値/出所と既存行衝突拒否を試験し、関数DDL/manifest/認可資産と必要な7.7受理・基線試験を通す。データ配置が未承認/未着地なら成功を作らず、ステップ3を完了扱いしない |
| 4 | 制限関数を呼ぶ固定function operationの登録経路と契約試験。必要なrepository-contract改訂は変更案の担当受理後に行い、変更後の7.7受理を確認 | **着手前に**固定実行器・凍結契約の具体差分、7.7の対象/手順/担当を確定する。tenant-bound scope以外から呼べず、関数ID・引数/戻り型を固定し、任意SQL・偽造token・直接Sessionを拒否。既存operationの不変条件/bypass検査を維持 |
| 5 | 登録済みscope経由の段階A公開resolver・不変DTO・失敗分類と単体試験 | 安全な全体既定だけを解決して規則ID+5値を返し、大会割当/試合上書きは拒否。候補なし、越境、無効規則、読取失敗とDB競合を受理済み結果へ分類。直接Session、仮規則、T1〜T6複製なし。U-G1へ同一scope保存契約を引き渡す |
| 6 | 実関数・登録済みscopeを通る隔離PostgreSQL二接続/故障注入試験 | 実装済みの全管理書込入口との両順序、ロック保持/rollback、別テナント、故障・競合を実測。未実装入口は未検証と明記し有効化しない。**U-G1の実HTTP・RG1・game INSERTとsnapshotの全取消/非遡及はTSK-395ステップ2**で実測する |
| 7 | `backend/tests/test_rule_resolution.py` の `AREA_PATH_ADDITIONS` 宣言と guard 試験 | tenant-isolation・game-state で新規試験パスが検出される。既存3パスは JSON 基線に残し、`tenant-isolation` 宣言は新規パスだけへ差し替える。`validate_area_path_layers` の一部 overlap 拒否を再現し、差し替え後に通過することを試験で確認 |
| 8 | `.claude/core-areas.json` 登録 | ステップ 7 とは別コミット。head 側の core-guard が全対象を検出し、未記入の人間逐行確認を拒否 |
| 9 | 最終の正本追随・検査・申し送り | pytest/ruff/ty、DB/認可/基線/guard 検査を通し、TSK-395 へ公開契約と実経路試験条件を引き渡す。**PR 作成後**の敵対レビューと人間逐行確認は本ステップの完了条件に含めず、PR マージ前ゲートで記録する |

ステップ 1 以降は本計画の人間承認後に**指示されたステップだけ**実施する。各ステップで必要な契約・正本承認が未成立なら停止し、計画差分と判断先を示す。1 PR にまとめるが、U-G1 本体のブランチへ製品差分を移さない。

## 5. DoD

- [ ] U-X1 の独立した受理担当と TSK-395 呼出側が、公開関数/型/4 失敗/transaction 境界を受理。未確認の受理を代記しない。
- [ ] TSK-395担当がステップ2の6-key codec入出力型・旧行拒否の保存mappingを受理する。公開resolver型・4失敗・同一scope接続の受理はステップ5の成果物として別に確認する。
- [ ] 段階Aの帰属証明、必要な制限関数・凍結基準の正式ゲートと承認記録が揃う。帰属列・移行が必要になれば別の具体差分/個別ゲートを通す。`pitchlog_app` の `rule_sets`・`tournament_rule_assignments` 直接SELECT/書込拒否と、`game_type_rule_defaults` の既存SELECT保持/書込拒否を維持する。
- [ ] 安全な全体既定だけを解決し、大会割当/上書きがあれば拒否する。規則ID+付録Fの5値を既存JSONBで同一取得時点のsnapshotとして保存できる契約・codecを提供する。ステップ2は構造検証済み値と相関検証済み値を区別し、相関検査を単一経路で提供する（NFR-018）。後続resolverは規則行の出所を同一scopeで確認し、相関検査済み値だけを保存前条件として受ける。未検証・矛盾例を保存成功としない。候補欠損・越境・無効規則・読取失敗・出所不明で解決成功を返さない。TSK-395側の保存・HTTP結合試験は消費側DoDへ引き渡す。
- [ ] 付録F-2確定値を、個別ゲートを通した配置migrationで出所・ID・5値を検証可能に供給する。曖昧な既存行は採用せず衝突時に停止する。将来の管理書込の権限・競合保護を受理記録で示し、未整備の書込入口は有効化しない。データ配置未了の環境は `rule_not_available` 等で拒否し、TSK-395の作成成功を主張しない。
- [ ] 制限関数は登録済み tenant-bound scope 以外から呼べず、bypass 検査を維持し、直接 Session を公開しない。`contracts/tenant_boundary/repository-contract.json` の改訂・7.7 受理が要る場合はその証跡、不要なら既存契約内で成立する根拠を残す。
- [ ] 二テナント、故障、並行変更と解決 operation の同一 scope/rollback を実 DB で確認。**試合保存と解決の全取消・保存済み snapshot 非遡及、実 HTTP/認可/RG1 結合試験は TSK-395 側の DoD**として引き渡す。
- [ ] pytest/ruff/ty と基線/guard が緑。**実装ステップ完了後に作る PR**でコア領域の敵対レビューと人間逐行確認の実施記録を得て、PR は人間判断でのみマージ。
- [ ] TSK-539 は計画タスク、TSK-395 は消費側、TSK-550 は先行実装として状態を分ける。U-X1 全体・TSK-395 を本タスクの完了で完了扱いしない。

## 6. テスト計画

pytest の単体試験でID+5値のexact-set codec、付録Fの値域/矛盾、旧 `{}` 拒否、段階A対象外/4失敗・DB競合分類を検証する。ステップ3〜6では実関数/登録済みscopeを通して、二テナントで `rule_sets`・`tournament_rule_assignments` のapp直接SELECT/書込拒否、`game_type_rule_defaults` の既存SELECT保持/書込拒否、割当あり拒否、候補欠損、読取故障、実装済み管理書込との並行変更・ロック保持、失敗時rollbackを隔離PostgreSQL二接続で検証する。未実装入口の実測を代記しない。関数migration/schema manifest、認可/凍結基線、core-guardのhead判定も検証する。TSK-395ステップ2では試合保存との原子性・非遡及、実HTTP・認可・RG1の復元先行/作成先行と全取消を別途検証する。候補なしと越境の利用者向け外形が同一であることも同経路で検証し、内部エラーの区別を存在情報として漏らさない。本タスクの単体試験でこれらを代替しない。
