# TSK-372 `games.applied_rules`限定先行単位 作業ログ

## 2026-10-19 PO計画承認

- 山田正輝が候補コミット`8a45168a79b3838fe8dfc59ef62f746ffff11957`、計画SHA-256`e56e3ad535e556b710fc8bd1645fd63d52a59245a87a88f0338cab5d47254a7e`に固定された限定計画と採否を承認した。第3回レビュー後にN4影響行を追加した最終反映差分は独立再レビュー未実施であり、その残余を含む承認である。
- 指名は現TSK-550担当による`games.applied_rules`限定先行単位の代行であり、TSK-372全23表の所有移管・元所有側の受諾・全体完了を意味しない。製品コードの個別資産・7.7実値の正式承認、既存DB適用、公開を含めない。

## 2026-10-19 起案と所有

- POは現TSK-550担当を、TSK-372の`games.applied_rules`限定先行単位の代行担当に指名した。正式カードの23表全体の所有移管・完了、元所有側の受諾は記録しない。
- 比較元は`origin/develop=015dfa9db0b7b8740369911a9cb5195dd59a62ea`。計画専用worktree`feature/tsk372-applied-rules-plan`を作成した。既存候補worktree`feature/orm-applied-rules-immutability-candidate`の未コミットmigration・manifest・ORM・DB試験を保全し、製品実装へ移していない。候補には隔離PostgreSQLの4試験成功の記録があるが、正式ゲートの成功とはしない。
- #158を先に仕上げる。TSK-372の新規PRは計画・正本解釈・編集枠・個別ゲート確定前に作らない。

## 計画敵対レビュー第1回（全文）

`codex_run.py review adversarial`、実モデル`gpt-6-sol`・effort`xhigh`、P0=2/P1=2/P2=0、判定は否決。指摘4件を全採用した。

| 重大度 | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0 | 計画ディレクトリがブランチslugと不一致で6.1の現在地導出が失敗する | 採用。`docs/features/tsk372-applied-rules-plan/`へ移動し、frontmatterも一致させた |
| P0 | manifest変更後のN3生成シートをステップ4へ送ると、ステップ3のroot検査が赤になる | 採用。N3影響行の再生成・旧判定保全・新しい人間判定をステップ3へ移し、シート検査後に影響検査を行う |
| P1 | §6-5改訂時にmanifestの正本SHAが古くなる | 採用。正式改訂は別ゲートでステップ2前に確定・統合し、ステップ3で確定本文のSHAへ追随、7.7該当性を判定する |
| P1 | ステップ4が7.7履歴の別コミットと`(ステップ 4/4)`の両方を要求する | 採用。正式受理後の履歴・snapshot反映をステップ4の1コミットに固定した。正本確定ゲートの反映周コミットは別ゲート |

## 計画敵対レビュー第2回（反映差分・影響節）

実モデル`gpt-6-sol`・effort`xhigh`、P0=2/P1=0/P2=0、判定は否決。既済み全文レビューは繰り返さず、2件を全採用した。

| 重大度 | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0 | §6-5を別PRで先行統合し、manifestの正本SHAを本PRの後続ステップで直すと、その間に不一致が生じ、7.6-2の同一PR原則にも反する | 採用。新規規範が必要な場合は本実装を停止し、別の限定計画・正本ゲートで§6-5本文とmanifest SHA・シート・7.7を同一統合境界で閉じてから再開する |
| P0 | §6-5を`games`へ結ぶ`source_sections`がなく、N1/N3/N7シート・固定件数試験への影響が計画に漏れる | 採用。`games.source_sections`の`6-5`、N1/N3/N7影響行、生成README・件数試験の条件付き追随をステップ3へ含めた |

規約6.3により、第2回でP0が残ったため第3回はこの2件の修正差分に限る自動枠で確認する。第3回で新しいP0/P1が残れば、追加レビューは自動追加せずPO裁定へ送る。

## 計画敵対レビュー第3回（P0限定・自動枠）

実モデル`gpt-6-sol`・effort`xhigh`、P0=1/P1=0/P2=0、判定は否決。既済み全文レビューは繰り返さなかった。指摘は、`games.source_sections`へ`6-5`を足すとN4シートのgames行も変わるのに、N1/N3/N7だけを対象としていた点。全採用し、別ゲート・本PRの編集対象、ステップ3、DoD、検査へN4影響行の再生成と人間判定を加えた。

第3回で基本枠とP0自動枠を使い切った。**最終のN4追記差分は独立再レビュー未実施**。これ以上のCodexレビューを自動実施しない。6.3に従い、採否表と最終差分を人間承認へ示す。追加の独立レビューを要求する場合はPO裁定1回につき1枠が必要。

### 共有パスの稼働・編集所有

全worktreeの未コミット差分を対象パスで照合した。TSK-372候補worktreeが`schema-manifest.json`と`game_state/models.py`を保有するほか、U-R1のPR #156 worktreeがmanifestとN3シートを変更中、#152候補worktreeがN3シートを変更中である。U-R1のmanifest差分は現時点では正本SHA追随、N3差分は1行追加。これらを本単位へ移動・上書きせず、U-R1の編集解除・実統合基線、#152への引き渡し枠をステップ1の条件とした。元TSK-372全体の所有側受諾は未確認のまま。

## 2026-10-19 承認後の基線・独立候補検証

- 限定計画の承認と第3回後のN4影響行が独立再レビュー未実施である残余を`4e61ee45`に記録した。最新`origin/develop=ba339cf8bdaac4761b8cf437abaf21763617d064`を専用featureへ`5b4504ec`で取り込み、競合はなかった。これはステップ1完了・製品実装承認・個別資産受理を意味しない。
- 実developのAlembic単一headは`0032_rg1_restore_gate`で、既存候補`0033_game_rules_immutable.py`の親と一致する。#152は未統合のため基線に使わない。#156・#152はいずれもDraftで、#156 worktreeはmanifestとN3、#152 worktreeはN3に未コミット差分を持つ。編集順は、#156の対象パスの所有解除と実統合を確認し、当限定単位でmanifest・N1/N3/N4/N7を最新developから再導出し、後続#152が当単位の実統合後に追随する案とする。所有解除・#152側の受諾は未確認で、共有ファイルは変更していない。
- `data-model.md`§6-5の現文は、保存時スナップショットと規則マスタの後日変更の非遡及を規定するが、試合行自身の保存後異値UPDATE禁止は明記しない。所有側にこの限定解釈と7.6判定を求める。現文に含まれない判断なら、計画どおり§6-5の限定正本ゲートを先行する。無回答を受理としない。認可・復旧の通常経路に解除入口を設けず、正当な訂正migration・復旧の例外が必要なら別ゲートとする。
- 既存候補worktreeを変更せず、専用の使い捨てPostgreSQLとテスト内の使い捨てクラスタで`uv run pytest -q tests/db/test_games_applied_rules_immutability.py`を再実行して**2成功**。最初の再試験は接続用DB未起動によるsetup error 2件でcall未到達、その後の隔離再試験で解消した。旧候補の実DB結果であり、最新developへ正式に組み込んだHEADの品質ゲート結果ではない。候補の製品ロール確認は`SET ROLE`による最小権限検査であり、認証済み製品ロールの恒久試験要件を満たしたとは記録しない。
- #158はDraft HEAD`618fba2e67e267b815a8767311167bcecedd9bf5`を維持。本人逐行確認の回答・チェックは未受領であり、代記・core-guardの確認後再実行・Draft解除・マージは行わない。現時点でGitHubは#158を`CONFLICTING`と表示するため、本人確認後も統合前に最新developとの競合解消と新HEADの検査が要る。

## 2026-10-19 §6-5限定改訂の方針と共有パス照会

- POは現行§6-5から試合行自身の異値UPDATE禁止を既承認とは解釈せず、別の限定改訂として明文化する方針を採用した。`docs/design/data-model.md`候補は専用`feature/tsk372-applied-rules-canonical`で`in-review`化して7.3審査中。正式確定・具体資産承認・7.7受理ではない。
- 7.6-3後段の版繰り上げを要する新規範として扱う。最終本文は初回INSERT、同値・他列UPDATE、異値拒否、正当なmigration・復旧の別ゲートへ限定し、人間承認へ提示する。共有manifest・シートは現時点で変更していない。
- #156へmanifest・N3の編集所有と解除条件を[コメント](https://github.com/masaki1025/pitchlog/pull/156#issuecomment-6264448857)で、#152へN3の編集所有と後続追随の受諾条件を[コメント](https://github.com/masaki1025/pitchlog/pull/152#issuecomment-6264449206)で照会した。提示順は#156対象パス解除・実統合→本限定単位→#152追随。回答前につき順序の合意・所有解除は未確認。

## 2026-10-19 ステップ1: 所有側判定・実基線・編集枠・7.7対象

- **所有側判定**: POは2026-10-19、現行`data-model.md`§6-5が試合行自身の保存後異値UPDATE禁止を含むとは解釈せず、別の限定改訂として明文化する方針を採用した（本文・版・確定は未承認）。専用`feature/tsk372-applied-rules-canonical`の候補v0.12は`in-review`で、7.3は基本枠2回（第1回全文: P0=0/P1=1/P2=1、第2回差分: 可決 P0/P1/P2=0）で収束し、`確定ゲート周回=1`。**正式承認・approved化・索引・manifest正本SHA・`shared-preconditions`のblob digest・受入シート・7.7は未実施**。本限定単位はこの別ゲートの人間承認と実統合を前提にし、正本・派生値は本worktreeで変更しない。
- **実基線**: `origin/develop`=`7c1afeba`（#158統合後）を本featureへ取り込み（merge `5f52bfd8`、競合なし）。Alembic単一headは`0032_rg1_restore_gate`で、既存候補`0033_game_rules_immutable.py`の親と一致する。**#152の`0033_stage_a_rule_defaults`は未統合であり親にしない**。本単位のrevisionは`0033_games_applied_rules_immutable`（`down_revision=0032_rg1_restore_gate`）とし、#152は本単位の実統合後に単一headから再導出する。未確定revisionは適用しない。
- **認可・復旧**: 製品ロール`pitchlog_app`は現行`games`のUPDATE権限を持つが、追加するトリガは異値UPDATEをSQLSTATE`23514`で拒否する。通常製品に解除入口を置かない。正当な訂正migration・復旧で異値が必要な場合は、対象行・理由・排他区間・全取消・変更後照合を限定した別ゲートとする。トリガ関数の認可分類（`pitchlog_app`からのEXECUTE剥奪）とruntime contractへの登録要否は、実装後にカタログ検査で判定する。
- **編集枠（共有パス）**: #156のPR head`836232d6`の差分に`contracts/db/schema-manifest.json`・`docs/features/orm-schema-migration/acceptance-sheets/`は**含まれない**（worktreeもclean）。ただし#156は`docs/design/data-model.md`をv0.12で変更しており、本限定単位の正本改訂（候補v0.12）と**版番号が衝突**する。統合順は **#156実統合 → canonical正本（v0.13へ繰下げ）→ 本実装 → #152追随** とし、同一ファイルを同時に編集しない。manifest・シートは本単位が編集所有を持つが、正本SHA・blob digestの確定値はcanonical実統合後に同一境界で追随させる。
- **7.7対象の判定**: `schema-manifest.json`の`canonical_source.sha256`と`shared-preconditions.json`の`mapping_target.git_blob_digest`は`data-model.md`の内容に連動する。canonical正本の実統合で値が変わるため、その受理単位で7.7の前後識別値・変更内容・理由・snapshot・受理記録案を確定し、**人間の正式受理後に追記のみで反映**する。本ステップでは既受理値を変更せず、未受理値を記入しない。他系列（tenant/seed/oracle）の受理履歴は変更しない。

## 2026-10-19 ステップ2: DB拒否機構と恒久実DB試験

- 候補`feature/orm-applied-rules-immutability-candidate`（未コミット・HEAD`d8cc9448`）のmigrationと実DB試験を受諾して再利用した。候補のAFTER単独案は既存のmanifest全表監査が`BEFORE UPDATE OF`を要求するため、BEFORE/AFTERの2トリガ構成を維持した。
- **受諾しなかった点**: 候補は2トリガで1関数を共有していたが、製品認可の1対1検査（`product_authz_cross_cutting_cases`・`test_product_authz_cross_cutting`）が「migrationトリガ関数は1トリガに1関数」を要求するため、`prevent_games_applied_rules_update()`と`verify_games_applied_rules_final()`の2関数へ分割した。両関数ともSQLSTATE`23514`で拒否する。
- revisionは`0033_game_rules_immutable`、親は実develop単一headの`0032_rg1_restore_gate`。`alembic_version.version_num`は`varchar(32)`のため32字以内の名前にした。#152未統合の`0033_stage_a_rule_defaults`は親にせず、適用もしていない。
- 専用使い捨てPostgreSQLで恒久試験2件が合格。検証した経路は、初回INSERT許容、同値UPDATE許容、他列UPDATE許容、異値UPDATE拒否（`pitchlog_app`最小権限・特権接続の双方）、同一transaction全取消、別列BEFOREトリガによるすり替えのAFTER拒否、既存行の異値訂正拒否と値不変、downgradeでトリガ2本と関数2本だけを撤去、再upgrade後の拒否、既存行の`applied_rules`不変。

## 2026-10-19 ステップ3（実装済み・人間判定と認可受諾は未了）

- `contracts/db/schema-manifest.json`の`games.immutability.protected_columns`を`["applied_rules"]`、`backend/src/pitchlog/db/game_state/models.py`の`Game.immutability.protected_columns`を同値へ変更した。`coverage=partial`と`unclassified_handoff=TSK-372`は維持する（23表全体へ拡大しない）。
- 受入シートを`--carry-judgments-from origin/develop`で再生成した。変更はN3の6行（出現084・085・091・092・093・094）だけで、`games: protected=[]`→`['applied_rules']`の1点のみが変わった。生成器の安全則により旧判定は持ち越されず、**未判定6行**として人間の再判定を待つ。件数（N1 103 / N3 105 / N4 55 / N7 100）は不変。
- **旧判定の保全**（人間の再判定材料。新しい判定は記入していない）:
  - 084: 対象外「削除の前提条件を同一トランザクションで判定するという不変条件であり、列の不変性ではない」`data-model.md:11-1`
  - 085: 対象外「述語と不変条件だけを本書で決めるという射程の記述であり、列の不変性ではない」`data-model.md:11-1`
  - 091: 対象外「移行が要求する不変条件表の表頭であり、列の不変性ではない」`data-model.md:12-3`
  - 092: 対象外「D5は退役後も消費済みという業務上の不変条件であり、列の不変性ではない」`data-model.md:12-3`
  - 093: 対象外「退役述語を一意性へ加えるという不変条件であり、列の不変性ではない」`data-model.md:12-3`
  - 094: 対象外「退役述語を一意性へ加えるという不変条件であり、列の不変性ではない」`data-model.md:12-3`
  - N3-061（`team_records.kind`）を含む他の判定は変更していない。**N3-061は恒久是正と正式受理の成立前に`一致`へ変えない。**
- **未了（意図的に書いていない）**: `games.source_sections`への`6-5`追加（canonical正本の人間承認・実統合が前提）、正本SHA・`shared-preconditions`blob digest、製品認可資産（`ddl-elements`・関数本体・`probe-product-map`）、runtime contract revisionと7.7履歴、7.7の実値。
- 検査結果: 専用実DBの恒久試験2件・`test_schema_manifest.py`・`test_game_state_models.py`は合格。`tests/test_orm_acceptance_sheets.py::test_acceptance_sheet_judgments_are_complete`は上記の未判定6行で不合格（人間判定待ち）。`check_authz_catalog`は新規migrationトリガ関数2本が製品認可資産未登録のため不合格（認可所有側の受諾待ち）。
