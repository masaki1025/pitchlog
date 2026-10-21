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

## 2026-10-19 実装後 敵対レビュー（GLM）と反映

- PO指示により、実装後レビューをGLM（`opencode/glm-5.3-flash-free`・max）へ委任した。対象は`7c1afeba..HEAD`の全差分と承認済み計画。主要な主張は使い捨てPostgreSQLで再実測された（直接UPDATE・`MERGE WHEN MATCHED`・`INSERT … ON CONFLICT DO UPDATE`・別列BEFOREトリガによるすり替えを、トリガ名順序の前後双方で拒否）。
- **判定: 可決（P0=0 / P1=0 / P2=4）**。P2 4件は全件採用・不採用0。
  - P2-1: owner/superuserの残存経路（`DISABLE TRIGGER`・`session_replication_role=replica`・`TRUNCATE`後の再INSERT・関数drop）は通常製品ロールで到達できない。migrationのdocstringへ明記し、訂正・復旧は別ゲートとする。
  - P2-2: 既存の全表不変性監査はBEFORE UPDATEトリガのみを突合するため、AFTER第2層は本migrationと恒久試験がpinすることを明記した。
  - P2-3: 拒否rootがSQLSTATEのみだったため、全拒否アサーションでメッセージ`games.applied_rules is immutable after insert`を照合するよう強化した。
  - P2-4: 恒久試験のdocstringの「候補」を「恒久試験」へ修正した。
- 反映後の再実行: 恒久試験2件＋`test_schema_audit`・`test_immutability_enforcement`・`test_immutability_matrix`・`test_migration_round_trip`の計8件が合格。ruff/tyも合格。

## 2026-10-20 ステップ4（認可資産・7.7受理）と最終追随

- 統合順をPO判断で **#163 → #161 → #162** に入れ替えた。#162（§6-5正本）が本PRを取り込み、`games.applied_rules` の保護宣言が入った状態で受入シートを1回だけ判定できるようにするため。
- 認可資産: トリガ関数2本（`prevent_games_applied_rules_update`・`verify_games_applied_rules_final`）を `ddl-elements.json`・関数本体SQL・`function-bodies/manifest.json`・`probe-product-map.json` へ登録した。
- 7.7: `rederive --base 7c1afeba` → `render` → `check` rc=0。`runtime_contract_revision` 17→18、保護関数 53→55、`source_digest` `7d681ae1…`、`application_role.attributes` は変更なし。
- 受理記録: `base-allowlist.json` の履歴へ追記のみ（24件目）。`acceptance_id=masaki1025/pitchlog#161` / `approved_by=masaki1025` / `approved_on=2026-10-20`、snapshot `f4fcc729…`。
- 併せて: `test_alembic_migrations.py` の head 固定を `0033_game_rules_immutable` へ追随。N3 105行の判定を確定（出現084/085/091〜094 は PO 承認 2026-10-20 の「対象外」）。
- `tests/test_check_authz_catalog.py` の未発効状態の複製は暫定契約の版で固定するため、0033 も複製から外した（0028 と同じ扱い）。
- 検査: backend 非DB 2391 passed / 4 skipped / 650 deselected、root `test_check_authz_catalog.py` 25820 passed、`test_frozen_history.py` passed、`check_tenant_boundary_bypass.py --base-ref origin/develop` ok、`test_orm_acceptance_sheets.py` 13 passed、backend `ruff format --check`・`ruff check`・`ty` と root `ruff check`・`ty` 合格。実DB群は migration を変えていないため前回実測のままとし、ステップ4後の認可DB試験はCIで再実行する。
- 未了（人間）: core-guard の逐行確認、マージ、既存DBへの0033適用（別ゲート）。

## 2026-10-21 #161 引継ぎ・CI是正・基線追随

- DeepSeek担当の専用worktreeを引き継いだ。公開HEAD `0681e64e`に残っていた未コミット4ファイルを保全し、CI run `39421525534` の backend失敗2件に対応付けた。`test_0028_preflight_restores_product_force_rls_after_success` は復元する関数ACLの列挙不足、`test_all_trigger_functions_fire_without_app_execute_privilege` はAFTERトリガを含むmigration接続集合とBEFOREだけを発火させる横断試験の混同である。
- `ed15724d`で migration を既存の監査器が解析できる識別形式に合わせ、復元ACLの2関数を追加し、migration接続済み全トリガ関数のexact-set照合とBEFORE発火試験を分けた。AFTER層の実挙動は恒久実DB試験で維持する。使い捨てPostgreSQLで当該2失敗の再試験は各1件成功し、不変性の恒久実DB試験2件も成功した。共有DBの既存ロールは変更していない。
- 最新 `origin/develop=9136c2da`（#160統合後）を `fb47d483`で通常mergeし、競合はなかった。取り込みで本PRの凍結資産・7.7履歴への差分はなく、既受理値は変更していない。`runtime_contract_generator check`、rootのruff/ty・限定pytest 380件、backendのruff format/check・ty・限定pytest 17件は合格した。
- 旧HEADのCI成功や既存の人間チェックを新HEADの確認へ自動延長しない。CI全件、修正差分のレビュー、最新HEADの本人逐行確認は別の最終ゲートで確認する。既存DB適用・TSK-372全23表・#152の作業は含めない。

## 2026-10-21 Claude一次レビューと指摘対応

- Claude Code CLIの独立した一次レビューを `d9b755cc`・`origin/develop=9136c2da` の全差分に実施した（実モデルIDはCLI出力に現れず未取得）。既済みGLM敵対レビューとは別枠。判定はP0=0/P1=1/P2=3。レビューは読取専用で、試験とCIの実行・7.7承認根拠の本人確認は含まない。
- **P1（採用・正式追補待ち）**: POが後から決めた統合順 `#163→#161→#162` は原計画の正本先行条件と一致しない。plan 7節へ、#161の限定境界、#162へ移す正本・source_sections・派生資産、公開停止条件の最小追補案を作成した。POの順序裁定を再判断しないが、6.1の差分レビュー枠と追補の正式採否は未了。原計画の承認を追補へ自動延長しない。
- **P2-1（既受理値を維持）**: `approved_by=masaki1025` は過去の実名表記と異なる。受理済み7.7記録を書き換えない。根拠は既存worklogの受理記録であり、この引継ぎセッションで承認メッセージの所在は独立確認できていないため、本人確認資料に残す。
- **P2-2（採用）**: migrationトリガ接続の集計で後続DROPとAFTERの複数接続を捕捉するよう`a572682c`で修正し、削除済み関数の除外と重複維持の負例を恒久化した。関連実DB・単体計4件、ruff format/check、tyが合格。
- **P2-3（残余）**: 恒久不変性試験は専用DBの`pitchlog_app`ロールで実施しており、製品認可資産を適用したAFTER発火・MERGE・UPSERTの全組合せまでは恒久化していない。既存の製品認可横断試験と不変性実DB試験は別々に通る。GLMの使い捨てDB実測は作業ログに保全し、本人が計画DoDへの十分性を判断する対象に残す。
- GLM敵対レビューの第2回（`ed15724d`差分限定）を試みたが、外部モデルがレート制限を返したため**未実施**。既済み第1回の可決をこの後発差分の再レビュー済みとは記録しない。追加の独立レビュー枠は消費していない。
- Claude一次レビューの限定追確認（候補`15e6c8ee`、`d9b755cc..HEAD`の影響差分）は新規P0=0/P1=0/P2=3。既出P1は6.1正式追補待ち、既出P2-2は解消、表記・全製品経路の残余は維持。この追確認を正式Codex計画レビューまたはGLM敵対レビューへ読み替えない。
- 新規P2のうち、DB不要の集計負例を`requires_db`モジュールに置いた点は、専用非DB試験へ移して重複時の`trigger_expectations()`拒否も追加した。#152の位置が追補案に曖昧だった点は、#161・#162実統合後の単一headから再採番する条件を追記した。パーサが直接`op.execute`の単純な`CREATE/DROP TRIGGER`に限られる残余は、現行migrationの実記法に影響しないことを確認して記録し、任意の将来記法まで保証する表現をdocstringから除いた。後続のP1是正で無修飾と`public`明示の双方へ対応したが、他の構文追加時は解析可能性と実カタログ突合を別途確認する。

## 2026-10-21 コア敵対レビュー第2回と最終是正候補

- 正式経路 `.claude/scripts/codex_run.py review adversarial`、実モデル`gpt-6-sol`・effort`xhigh`で、`466d4169..d6e4038c`の後発差分と影響箇所を読取専用レビューした。既済みGLM第1回の全文は繰り返していない。判定は**P0=0/P1=2/P2=1**。P1-1は0033の関数・表名をCI是正時に無修飾へ変えた結果、作成先が`search_path`に依存した点。P1-2は計画7節の正式差分レビュー・採否待ち（既出）。P2はAFTER層と製品認可資産を組み合わせた恒久実DB試験の未整備（既出残余）。
- **P1-1採用**: 0033は関数・表の`public`修飾を戻し、migration解析器のCREATE FUNCTION/CREATE TRIGGER/DROP TRIGGERを既存の無修飾記法と`public`明示記法の双方へ対応させた。DB非依存負例も`public`修飾で試した。関連実DB・単体5件、隔離DBの0028復元1件、backend ruff format/check・tyは合格。受理済み7.7資産に差分はない。
- **P1-2未了**: POの統合順裁定は維持し、計画追補案の追加6.1差分レビュー枠と正式採否を待つ。P2は現行の二つの恒久試験群と使い捨てDB補助実測を証跡とし、製品認可を適用したAFTER層の組合せ実測は未完了として本人確認資料へ残す。レビュー後のP1-1反映差分を敵対レビュー済みとは記録しない。

## 2026-10-21 計画§7の追加6.1差分レビュー第4回

- POがこの1回に限り許可した追加レビュー。開始前に対象HEADを`6b8c8a4347ffc07351b2b523bb989c7b8108e011`、`d9b755cc..HEAD`の`plan.md`差分SHA-256を`61e748a8f46e7bfb7c64e656c3e3379000cced4769b24ef56692bc97a9fc3ae9`に固定した。正式経路`.claude/scripts/codex_run.py review adversarial`、Codex `gpt-6-sol`・effort `xhigh`、対象は統合順、migration親、#162への引渡し、共有資産・受理履歴への直接影響だけ。既済み計画レビュー3回の採否・回数は維持する。
- 判定は**否決（P0=0/P1=2/P2=1）**。P1-1「旧ステップ1・3、DoDの#161/#162境界が本文に残る」は採用し、§7で#161が満たす条件と#162統合まで未達の条件を個別に指定した。P1-2「`status: active`かつ旧承認済みでは未承認追補を実装できる」は採用し、原計画の承認記録を維持したまま追補の人間採否まで`status: in-review`へ移した。P2「#162への正本SHA・派生資産が曖昧」は採用し、manifestの`canonical_source.sha256`、shared-preconditionsの`mapping_target.git_blob_digest`、生成README・固定件数試験を明記した。第4回後のこの最終反映差分は独立再レビュー未実施として人間採否対象に残す。追加レビュー枠を自動追加しない。
- HEAD `6b8c8a43`のCI run `39457445738`はbackend・harnessを含む12ジョブ全件成功。`d6e4038c..6b8c8a43`で7.7受理済み資産とcorpusの差分はない。migrationの`public`明示と静的監査器の限定追随は`d1b1f760`の3製品／試験ファイルに限られ、受理済みの関数本文・識別値・snapshot・履歴は変更しない。したがってこのsearch_path是正単独で7.7再受理は不要。敵対レビュー第2回後の`d1b1f760`は独立再レビュー未実施のまま人間逐行確認対象に含める。
- PR本文では本人逐行確認のチェックだけが記入され、必須の`対象・範囲・方法`実施記録は空欄。よって本人確認は未成立。記録を代記せず、最終HEADの22ファイル差分、search_path是正、第4回後の計画反映差分を本人へ提示する。Draft解除・マージ・既存DB適用は行わない。

## 2026-10-21 計画§7追補の人間承認と#165統合後の基線

- 山田正輝は本会話で、最終計画差分SHA-256`a6263a977bc76119bb669568784686e33729404ce69763f58aa736db38560774`の§7追補を承認した。第4回レビューの3指摘は反映済みで、反映後差分は独立再レビュー未実施である残余を含む承認。原計画の2026-10-19承認と計画レビュー4回の採否履歴は維持し、計画状態を`active`へ戻した。この承認は本人逐行確認・7.7再受理・Draft解除・マージを含まない。
- 最新`origin/develop=caf5634787aeb60f692254fdcc179bb4fe34decf`はPR #165の統合を含む。`--no-commit`の試行mergeでは、`contracts/tenant_boundary/base-allowlist.json`と`tests/fixtures/frozen-archive-cases/manifest.json`の2ファイルだけが競合した。#165はbase履歴の24件目とrepository契約変更を正式受理しており、#161の未統合受理記録も24件目として`contract_revision:33`を使用するため、そのまま両履歴を連結すると基準遷移が不一致になる。試行mergeは安全にabortし、双方の受理済み記録と旧値を無変更で保全した。新基線への直列化は新しい完全値・受理方法の判断が必要であり、未受理値を正式履歴へ書かない。

## 2026-10-21 旧#161から最新develop起点の置換単位へ

- POは旧#161の置換PRを1件に限り許可した。旧ブランチ`feature/tsk372-applied-rules-plan`、受理記録、計画承認、レビュー履歴、HEAD`441b078e`とローカル承認記録`cfed4347`を保全する。新ブランチ`fix/tsk372-applied-rules-plan`は#165を含む実`origin/develop=caf56347`起点。旧#161の製品・試験・計画差分を移植したが、旧#161の`base-allowlist`受理行・snapshot・corpus digestは持ち込んでいない。
- 置換先でも実装範囲は`games.applied_rules`限定のままとし、§7の#161統合順は「置換PRが#161の位置を継ぐ」と読み替える。#162は置換PRの実統合後のdevelopから正本・派生資産を再導出する。後続#152もその後の実developを基線にする。置換先PR ID、7.7新実値、承認者・承認日は実番号と正式受理まで記入しない。旧承認は新実値へ流用しない。
- この移植では、旧#161の計画§7の承認済み実装境界を変更しない。増分審査対象は新基線への製品差分の意味比較、#165履歴の後ろへ追加する7.7の新前後値・snapshot・corpus、置換PR IDによる受理行、#162への引渡しと本人確認の最終差分に限定する。既済み全文レビューは繰り返さない。
- 置換Draft PRは[#172](https://github.com/masaki1025/pitchlog/pull/172)。#162へ[引渡しコメント](https://github.com/masaki1025/pitchlog/pull/162#issuecomment-6312641105)を送付した。この送付時点では受諾未確認だったが、後に#162側の`d9b3459f`へ引渡し受諾と派生値の再導出条件が記録された。旧#161は引継ぎの製品差分・新7.7資料が#172に公開され、保全を照合してから未マージのままクローズした。

## 2026-10-21 置換単位ステップ1: 実基線と受理境界

- #172は`origin/develop=caf56347`を実基線とし、Alembic単一headは`0032_rg1_restore_gate`。旧#161の`0033_game_rules_immutable`は同じ親で、未統合#152の配置revisionを親にしない。旧#161との差分は#165の自チームreadとrepository契約・受理履歴であり、移植した本単位の製品差分そのものに変更を加えない。
- #165の受理済み履歴24件を直前状態とする。`base-allowlist`の旧#161記録（同じ24件目）は移さない。#172が必要とする遷移は`runtime_contract_revision:17→18`、関数53→55で、#165の`repository-contract` revision22は直前・直後とも保持する。新受理行の`acceptance_id`は実PR ID `masaki1025/pitchlog#172`。正式な承認者・承認日は新実値の人間受理まで未記入。
- #162へは「#165→#172→#162、後続#152」の統合順と旧#161由来値の再導出を送付した。送付と受諾は別に記録し、#162側の`d9b3459f`で受諾を確認した。#172新7.7値の正式受理、実統合、#162側の実基線からの再導出、既存DB適用、本人逐行確認、Draft解除・マージは未了。

## 2026-10-21 置換単位ステップ2・3と新7.7候補

- `b42c8dc5`で旧#161と同一の0033 migration・恒久実DB試験を移植した。隔離DBの不変性試験2件、schema manifest・Alembic試験45件が成功した。親は実developの`0032_rg1_restore_gate`で、#152未統合revisionを親にしていない。
- `185b2c1b`で旧#161と同一のmanifest・ORM保護宣言、head固定試験、N3シートを移植した。root ORMシート試験15件が成功し、既存の人間判定・理由を保持する。
- 製品・契約・試験の移植対象17ファイルは旧#161の`cfed4347`とバイト単位で一致する。ファイル集合SHA-256は`2e90b294f12f2d7b2d3c8c5b838f28e1dede6a53b02c53b1d6417b175750f925`。旧計画・製品レビューは不変の内容に限り維持し、新履歴処理と最終差分の追加確認は未了。
- 新PR #172の候補入力treeは`a03a53bb49d23d7bd22b90fad828f3e67d818401`。7.7完全値は`replacement-77/decision-packet.json`、25件目の受理記録案は`replacement-77/record-proposal.json`へ固定した。案のSHA-256はそれぞれ`110a2ce24127d2c99c84caf757073504de00fbdf054652c4c7fc90d9cbde0acd`、`50531a87072e66e0dfebdd6ec4d154c78c3b68ebba5ccd62b45dff629e9f5e9b`。承認者・承認日は未記入。正式履歴・snapshot・corpus manifestは未変更。
- 比較元#165の受理履歴24件と前後値を維持する。runtime-authz射影だけ`061eeb9e…→f4fcc729…`、corpus入力digestは`f50b17a2…→b80afca5…`へ変わる候補。9資産・外部8ファイルの省略しない値は判断資料へ収録した。#161の24件目をそのまま連結しない。
- ステップ4の未受理実ファイル差分11件は`replacement-77/step4-candidate.patch.gz`へ固定した。圧縮ファイルSHA-256は`3a276fbebc26d538d41821a4e1580ee204098c24b19738edbeec5a4f654c9a2b`、展開patch SHA-256は`24295dc5d0be6b0f16ddbf2d4eeef19b01d1cc1300ba5f151acb0a34526ac0ee`。現在の候補worktreeで展開patchの`git apply --reverse --check`が成功した。正式資産・受理履歴は新実値の人間受理まで未変更。
- #172の公開HEAD`5bd6aa65`で移植実装・候補patch・7.7判断資料の公開を確認し、旧#161を**未マージ**のままクローズした。旧ブランチとローカル`cfed4347`を削除せず、旧7.7受理記録・承認/レビュー履歴も保持する。#172の本人逐行確認、Draft解除、マージは未実施。

## 2026-10-21 #172最新develop追随と7.7再導出

- 最新`origin/develop=fb719e368f6dbc8a178cba9d42af875553c1bc1f`は#164・#166を含む。未受理ステップ4の11ファイルを退避して`ed9aa966`で通常mergeし、退避内容を復元した。差分はU-F8のfrontend・文書15ファイルだけで、#172対象ファイルとの競合・意味変更はない。旧#161と一致する移植17ファイルを再度バイト照合した。
- 新比較元の9資産・外部8ファイルの完全射影を`frozen_history._asset_projection_snapshots`と実ファイルSHAで再計算し、全17値が前候補と一致した。corpus入力digestも再計算して`b80afca5ca0249990661f0e02ffbe2bd6b53b82271d6204b471a84ddf816cef1`で不変。受理記録案SHA-256`50531a87072e66e0dfebdd6ec4d154c78c3b68ebba5ccd62b45dff629e9f5e9b`も不変。
- 新候補入力tree`c2bfbdf7f96f1414c0fa9f5c1625f54bfbc64a36`と完全値を`replacement-77/decision-packet-fb719e36.json`へ固定した（SHA-256`77c18f343ed8a554852606be960b1ddbba2eca5b62b4d95266ea81e9d7becd80`）。前回packetと#165の既受理24件は証跡として保持し、正式履歴・snapshot・corpus manifestは未変更。
- 旧公開HEAD`fffe298a`のCIではharness 3件、backend 51件が失敗した。両者は0033 migrationに対してステップ4の認可関数2件が正式資産へ未反映であることに起因する同じ不整合で、別々の製品欠陥として重複計上しない。core-guardは本人逐行確認チェック未記入による拒否。新merge後のCIは未実施。
- 計画レビュー4回と旧#161の製品レビューは不変差分の証跡として保持する。置換・新履歴処理の限定独立レビューに使用できる未消費枠は確認できず、6.3に従う追加1回のPO裁定が必要。対象は新比較元への追随、#172新受理行の直列化と完全値、候補patchと旧#161同一性、#162引渡しの直接影響のみ。既済み全文レビューを反復しない。
- 最新候補の限定検査: 文書検査333件、隔離DBの不変性・Alembic試験33件、旧CI失敗と対応するroot認可試験3件・backend認可試験2件が成功。9資産・外部8ファイルと既受理履歴24件の再計算照合も成功。正式受理後のroot/backend全件・凍結/corpus検査・新HEAD CIは未実施。

## 2026-10-21 #172置換・履歴処理の追加限定独立レビュー

- POは公開HEAD`a431b4fe`、比較元`fb719e36`、候補tree`c2bfbdf7`、判断資料SHA-256`77c18f343ed8a554852606be960b1ddbba2eca5b62b4d95266ea81e9d7becd80`、受理記録案SHA-256`50531a87072e66e0dfebdd6ec4d154c78c3b68ebba5ccd62b45dff629e9f5e9b`に固定した追加独立レビュー1回を許可した。既済み計画レビュー4回・製品レビュー2回は維持し、コア領域の追加1回として記録する。
- 正式経路`.claude/scripts/codex_run.py review adversarial`、実モデル`gpt-6-sol`・effort`xhigh`、read-onlyで実施した。現物未反映のステップ4候補patchと未コミット11ファイルも対象に含め、不変な製品差分の全文審査は繰り返していない。判定は**可決、P0=0 / P1=0 / P2=1**。
- P2（起因・採用）: #162側の公開コミット`d9b3459f`には引渡し受諾と暫定派生値の再導出条件があるのに、#172側のREADME・作業ログは受諾未確認のままだった。上記2文書を訂正した。正式7.7受理、#172実統合、#162の実再導出は未了と区別する。**このP2是正後の文書差分は独立再レビュー未実施**であり、追加枠を自動使用しない。
- レビュアは旧#161との17ファイル同一性、24件の既受理履歴保持、25件目の案、9資産・外部8ファイル、snapshot・corpus、gzip patchと未コミット候補、候補treeを照合した。GitHub API接続失敗によりPR上のレビュー履歴・CIの独立照合は未完了として報告された。担当側は別に実PRとCIログを取得し、harness 3件・backend 51件をステップ4未反映の同一原因、core-guardを本人確認待ちと分類した。レビュアの未確認事項をレビュー済みへ読み替えない。

## 2026-10-21 #167統合後の比較元追随

- レビュー後に`origin/develop=32a4d828d6afe748e72ea16623711525f4912b6c`へ#167が統合された。未受理候補11ファイルを退避・復元して`39b49e4b`で通常mergeした。新規差分はU-F8のfrontend・文書9ファイルのみ、競合なし。追加レビュー枠は使用済みなので、この追随を独立レビュー済みとは記録しない。
- 新比較元から9資産・外部8ファイル、既受理履歴24件、corpus入力digestを再計算し、すべてレビュー対象時点の値と一致した。#172の記録案SHA-256`50531a87072e66e0dfebdd6ec4d154c78c3b68ebba5ccd62b45dff629e9f5e9b`とステップ4patch SHA-256`3a276fbebc26d538d41821a4e1580ee204098c24b19738edbeec5a4f654c9a2b`も不変。新候補tree`64b42211f398c184128d7f863746d4e6ee5240d1`、新完全値`replacement-77/decision-packet-32a4d828.json`のSHA-256`64513a4d8d164d05957004335acfc030d59b9a40ad9d4f8c6f267a5969381d40`。旧資料は比較元の証跡として保持し、正式資産・履歴へは未反映。
