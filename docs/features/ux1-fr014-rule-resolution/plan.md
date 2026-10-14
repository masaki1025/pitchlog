---
feature: ux1-fr014-rule-resolution
status: active
承認: 未
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc
branch: feature/ux1-fr014-rule-resolution
created: 2026-10-14
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-X1／FR-014 安全な規則解決の先行実装

## 1. 背景・目的

TSK-550 は、PO の 2026-10-14 J-3 裁定で TSK-539（U-X1 計画）から切り出した FR-014 の先行実装タスクである。TSK-395（U-G1）は `preparing` 作成時にこの結果を消費する。実装担当は現 U-G1 担当、**ドメイン所有は U-X1**。別 worktree・本タスクだけの 1 PR とし、U-G1 の製品コードへ混在させない。本裁定は製品実装・正本改訂・スキーマ/認可/凍結資産変更の承認ではない。

現行 `rule_sets` には帰属列がなく、`rule_sets` と `tournament_rule_assignments` は `function_only`。直接読取を開かず、FR-014 の「試合上書き ＞ 大会規則 ＞ 試合区分既定」を解決し、付録 F の検証済みスナップショットを同一 transaction 内の試合作成へ渡す。TSK-539 の T1〜T6 状況・終了計算は実装しない。根拠は [調査](research.md) と [設計論点](design.md)。

## 2. スコープ

### 対象

- U-X1 所有の公開解決関数と不変の入出力型。候補なし、越境、無効/矛盾規則、読取失敗を内部で区別し、いずれも解決成功を返さない。越境では他テナントの存在情報を漏らさない。TSK-395 の利用者向け応答では候補なしと越境の外形を同一にする契約・試験条件を引き渡す。
- 付録 F の全欄を保存前に検証し、優先順位を単一経路で解決する。既存の単一規則実装・契約を使い、T1〜T6 やクライアントへ計算を複製しない。
- テナント帰属の表現、制限関数、登録済み operation の安全な呼出し、読取と U-G1 保存が同一 `tenant_transaction_scope` に収まる契約。作成側の保存自体は TSK-395。
- 実 DB による二テナント、故障、並行変更、解決 operation の同一 scope/rollback の試験。**試合保存との全取消と保存済み snapshot の非遡及は TSK-395 の結合試験**。関連する正本・認可・凍結基準の正規ゲートとコア領域レビュー。

### 対象外

U-G1 の HTTP/試合 INSERT、スタメン・開始、U-X1 の T1〜T6、規則管理 UI、大会規則の設定操作、RG1/D4、仮規則、仮の保存成功。大会への結付け**書込**が作成時の規則解決に不可欠と判明した場合は計画差分と U-X1 受理を先に得る。既存行の曖昧な帰属を推定で埋めない。

## 3. 影響する正本・資産とゲート

| 対象ファイル | 意味差分の候補 | 必要なゲート |
| --- | --- | --- |
| `docs/features/product-impl-unit-split/{plan,design}.md`、`docs/features/ux1-state-calc/{plan,design}.md` | U-X1 の対象計算の凍結を維持しつつ、**FR-014 読取/検証/帰属だけ**を TSK-550 に先行分割した事実へ追随。TSK-539 第1 PR へ取り込まない | 所有側受理と本計画レビュー。単位帰属・凍結の規範を変更するなら 7.6 の構造変更として 7.3 敵対レビュー＋人間承認。単なる実装追随か事前に判定 |
| `docs/features/product-authz-surface/design.md` §1-6 | `function_only` の制限関数と帰属列の着地を記録。アプリ用直接 ACL を開かない | 認可面所有者の確認、規範変更なら 7.3。実装追随の節更新のみなら同一 PR のレビュー |
| `docs/design/data-model.md` §6-5/§10-5、必要なら `docs/README.md` | 全体既定とテナント大会規則の帰属・参照・既存行移行の意味を定義 | **スキーマ構造変更**の正式版・7.3 敵対レビュー＋人間承認（ハーネス 7.6）。承認本文より先に migration を確定しない |
| `docs/requirements/requirements-pitchlog-2026-07-22.md`、`docs/adr/ADR-003-domain-calc-method.md`、`docs/development/dev-harness-design-2026-08-07.md` | 現時点で反映なし。FR-014/付録 F と対象計算の境界を変える必要が出たら作業停止し別の確定ゲートを提案 | 今回は変更しない |
| `backend/src/pitchlog/db/game_state/models.py`、`backend/migrations/versions/<新revision>.py`（帰属列と制限関数で**別 revision**）、`contracts/db/schema-manifest.json` | `rule_sets` の帰属を表現し、全体既定とテナント規則を制約で区別。既存行の移行方針を明示。関数・ACL の DDL は次の revision に置く | 上記正本承認後。各 migration/manifest 突合、実 DB 移行試験。revision 番号は着手時 head に合わせる |
| `contracts/authz/product/{table-classification.json,exposure-facts.json,ddl-elements.json,capability-catalog.json,application-steps.json,function-bodies/**}`、`contracts/tenant_boundary/{runtime-authz-contract.json,base-allowlist.json,history-snapshots/**}` | 制限関数、実行権、直接表権限の不付与、呼出し capability と露出事実 | 認可面所有者受理。7.7 の基準変更が生じる場合は `base-allowlist.json` の単一受理履歴・必要な snapshot を追記し、基線試験を通す。凍結資産を検査だけ緩めて通さない |
| `backend/src/pitchlog/repositories/{operation_registration.py,operation_registry.py,transaction.py,repository_contract.py,rule_resolution.py}`、`backend/tests/test_rule_resolution.py`、`contracts/tenant_boundary/{repository-contract.json,base-allowlist.json,history-snapshots/**}` | テナント束縛 scope から安全に関数を呼ぶ登録経路・型・失敗結果。`rule_resolution.py` は既存 `repositories/*` glob に入る。`repository_contract.py` は実装、JSON は凍結された公開契約 | **現行登録型は tenant_column 付き表 `Select/Insert/Update` のみ**。直接 Session 逃げ道は不可。JSON 契約の改訂が必要なら変更案の担当受理を先に得て、当該変更後の 7.7 受理と `base-allowlist.json` の単一受理履歴・必要な snapshot を同ステップの完了条件とする。確定ゲートの文書反映はステップ記法なしの別コミット。対象ファイルの実変更は設計受理後に限定 |
| `scripts/core_guard.py`、`tests/test_core_guard.py`、`.claude/core-areas.json` | 新規 `backend/tests/test_rule_resolution.py` を tenant-isolation と game-state へ宣言・登録。製品モジュールは既存 tenant-isolation glob に入る。既存3パスは merge-base の JSON 基線に保持する。`tenant-isolation` の AREA_PATH_ADDITIONS は新規試験パスだけへ**差し替え**、`game-state` へ新規追加する | 6.3 のコア領域敵対レビュー＋人間確認。宣言・テストと JSON 登録を別コミットにする |

## 4. 実装方針・ステップ

**着手前の独立受理**: U-X1 の具体的な受理担当を Claude 側で確保し、公開関数名・入力型（試合区分、大会、上書き、TenantContext）、検証済みスナップショット型、4 失敗結果、同一 scope の読取/保存/全取消を受理してもらう。TSK-395 呼出側も受理する。現時点で U-X1 の受理担当は未確認。受理前に契約を確定扱いしない。

**設計停止条件**: (a) 帰属列の型・制約、曖昧な既存行の扱い、全体既定の管理権限、(b) 制限関数の `SECURITY DEFINER` 等の安全条件・実行権・search_path と越境結果、(c) 現行 operation registry での関数呼出しの可否と、必要なら repository-contract の改訂、(d) 上書きの表現、規則マスタ並行変更時の一貫性/ロック期間を、U-X1 と認可面所有者・該当正本ゲートで決める。方式を本計画で先取りしない。

**計画の人間承認前には、ステップ 1 を含む実装ステップへ入らない。** 承認前は計画起案・レビューと担当調整だけを行う。承認後、ステップ 1 の着手前に単位分割・U-X1 計画の凍結文言是正が**規範変更か実装追随か**を 7.6 で判定する。規範変更なら 7.3 の確定ゲートと人間承認を先に通す。`data-model.md` の起案もステップ 1 より前の**ゲート側・ステップ記法なし**のコミットに置く。7.7 はこの時点で対象資産・受理手順・担当を決め、実際の資産変更後の基準受理を各実装ステップで行う。複数の正本で構造変更が要るなら、ゲートの射程と対象文書を一つの審査単位として先に固定し、本計画の `確定ゲート周回` をその一単位で数える。別々の審査が必要なら各正本の計画/周回記録を分離し、混在させない。正本確定ゲートの反映周コミットはステップ記法を付けず、ステップ 1 の別コミットは受理済み契約・移行判断・登録経路とゲート証跡を文書へ固定する。外部受理が揃わなければステップ 1 は緑にならず、製品実装へ進まない。

| # | ステップ（別コミット） | 合格条件 |
| --- | --- | --- |
| 1 | 接続契約・帰属移行・登録経路の選択と、必要な正本ゲートの結果と 7.7 の対象/手順/担当を、受理記録として文書に固定する | 関数・型・4 失敗・同一 scope 境界の担当受理記録、既存行判断、正式な正本承認と 7.7 受理の計画。変更後の基準受理はステップ 3・4 で行う。ステップコミットはこの証跡と判断の文書差分。未受理ならステップ 2 に進まない |
| 2 | 帰属列と制約の migration、ORM、schema manifest、移行試験 | 新規・既存行で帰属の曖昧さが残らず、二テナント・全体既定の制約とロールバックを実 DB で確認 |
| 3 | 制限関数の**別 migration**と ACL/認可資産、越境・故障試験 | app ロールの直接表読取/書込は拒否、関数経由だけ所定候補を返し、他テナント存在情報を漏らさない。関数 DDL、`ddl-elements.json`、manifest が一致し、当該変更後の 7.7 受理と凍結基線試験が緑 |
| 4 | 制限関数を呼ぶ登録済み operation の経路と契約試験。必要な repository-contract 改訂は変更案の担当受理後に同ステップで行い、変更後の 7.7 受理まで確認する | tenant-bound scope 以外から呼べず、現行 operation 不変条件と bypass 検査を維持。直接 Session を公開しない。改訂が不要と証明できた場合は根拠と登録済み経路の試験をコミットに残す |
| 5 | 登録済み scope 経由の公開解決関数・不変 DTO・保存前検証と単体試験 | 優先順位全分岐、付録 F の無効規則、候補なし、越境、読取失敗を識別。直接 Session、仮規則、T1〜T6 複製なし |
| 6 | 解決 operation の同一 scope・並行変更の実 DB 試験 | scope をまたぐ独立 commit をせず、解決失敗時は scope が rollback。並行更新でも合意した一貫性を保つ。**TSK-395 の試合 INSERT と snapshot 保存の全取消・非遡及は消費側の結合試験**として引き渡す |
| 7 | `backend/tests/test_rule_resolution.py` の `AREA_PATH_ADDITIONS` 宣言と guard 試験 | tenant-isolation・game-state で新規試験パスが検出される。既存3パスは JSON 基線に残し、`tenant-isolation` 宣言は新規パスだけへ差し替える。`validate_area_path_layers` の一部 overlap 拒否を再現し、差し替え後に通過することを試験で確認 |
| 8 | `.claude/core-areas.json` 登録 | ステップ 7 とは別コミット。head 側の core-guard が全対象を検出し、未記入の人間逐行確認を拒否 |
| 9 | 最終の正本追随・検査・申し送り | pytest/ruff/ty、DB/認可/基線/guard 検査を通し、TSK-395 へ公開契約と実経路試験条件を引き渡す。**PR 作成後**の敵対レビューと人間逐行確認は本ステップの完了条件に含めず、PR マージ前ゲートで記録する |

ステップ 1 以降は本計画の人間承認後に**指示されたステップだけ**実施する。各ステップで必要な契約・正本承認が未成立なら停止し、計画差分と判断先を示す。1 PR にまとめるが、U-G1 本体のブランチへ製品差分を移さない。

## 5. DoD

- [ ] U-X1 の独立した受理担当と TSK-395 呼出側が、公開関数/型/4 失敗/transaction 境界を受理。未確認の受理を代記しない。
- [ ] 帰属列・移行・制限関数・凍結基準の正式ゲートと承認記録が揃う。アプリ用ロールへ直接表 ACL を開かない。
- [ ] FR-014 の優先順位と付録 F の保存前検証が単一実装で、既存の規則計算を複製しない（NFR-018）。候補欠損・越境・無効規則・読取失敗で解決成功を返さない。TSK-395 側の保存成功禁止と HTTP 結合試験は消費側 DoD へ引き渡す。
- [ ] 制限関数は登録済み tenant-bound scope 以外から呼べず、bypass 検査を維持し、直接 Session を公開しない。`contracts/tenant_boundary/repository-contract.json` の改訂・7.7 受理が要る場合はその証跡、不要なら既存契約内で成立する根拠を残す。
- [ ] 二テナント、故障、並行変更と解決 operation の同一 scope/rollback を実 DB で確認。**試合保存と解決の全取消・保存済み snapshot 非遡及、実 HTTP/認可/RG1 結合試験は TSK-395 側の DoD**として引き渡す。
- [ ] pytest/ruff/ty と基線/guard が緑。**実装ステップ完了後に作る PR**でコア領域の敵対レビューと人間逐行確認の実施記録を得て、PR は人間判断でのみマージ。
- [ ] TSK-539 は計画タスク、TSK-395 は消費側、TSK-550 は先行実装として状態を分ける。U-X1 全体・TSK-395 を本タスクの完了で完了扱いしない。

## 6. テスト計画

pytest の単体試験で優先順位・付録 F 値域/矛盾・失敗分類を検証する。PostgreSQL 実 DB で二テナントの表直接拒否と関数結果、上書き ID の越境、候補欠損、読取故障、マスタ並行更新とロック期間、scope 内呼出し/失敗時 rollback を検証する。2 revision の migration、既存行移行と schema manifest、認可/凍結基線、core-guard の head 判定も検証する。TSK-395 が接続した後は試合保存との原子性・非遡及、実 HTTP・認可・RG1 の復元先行/作成先行を別途検証する。候補なしと越境の利用者向け外形が同一であることも同経路で検証し、内部エラーの区別を存在情報として漏らさない。本タスクの単体試験でこれらを代替しない。
