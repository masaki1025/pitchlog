# #173の実#174後再導出候補

移管日時: 2026-10-23T15:59:25.517736+00:00。

PO委任を受けた主担当 `/root` の今回指示により、`/root/independent_review`がこの時点から#173再導出候補の作者を担当する。最終独立レビューは別担当で実施する。

固定source HEAD: `36424c536255b6c6e6d9aac82bb55a9c51d7ef46`。比較元: 実#174統合 `1f506675`。対象は9 tenant_boundary JSON、既存生成Python3、archive manifest、post174命名の提案・候補snapshot・作業記録だけ。initial_grant/試験/checker/core/認可DDL/正本/他worktreeを変更しない。

実baseの26件history prefix、先行56関数、旧raw source hash、原状5239保全点、旧proposalと既受理履歴を保持する。新#173記録と新snapshotは候補資料のみに固定し、正式authority/正式snapshotdirへ反映しない。元#173由来の未参照snapshotも削除せず一覧候補とする。共有資産の唯一writerを引き受け、受理・コミット・push・DB/鍵操作は行わない。

## 再導出と検査（受理前）

runtime rederive --base 1f506675は製品DDL同一のため変更0。既存frozen_history.evaluate_repository_movementは外部checker/census試験の差分と限定allowlistから8資産をaffectedと導出した。8資産だけを実base+1、frozen-inputsは5のまま保持し、4つのsource_digest・生成Python3のrevision/digest・allowlist.inventory.sha256を正規方式へ追随した。

限定生成契約5試験は5 passed/0.47s。runtime generator check、root/backend対象Ruff、git diff --check成功。raw initial_grant/testは5239保全点とSHA一致、旧proposal2件は旧SHA一致、製品DDLは実baseとバイト同一/56関数、正式snapshot全件はHEADバイト不変。実資産の意味内容はrevision/digest/inventory binding以外HEAD同一。

初回censusはinventory binding追随前に開始し追随中と重なったため安定版検査へ採用しない（4 failed/30 passed/40 errors、25.03s）。inventoryの既存バイト封印参照を追随した後、固定した入力で全74件を再実行している。新たな検査条件の緩和やテストsource変更はない。

受理前の実checkerは26履歴末尾と新識別値の不一致でexit2。PR eventを通常feature HEADへ注入するだけでも2親/first-parent拘束で拒否され、GitHub合成merge上の実PR受理検査の代用にならない。正式173記録・新snapshotは未反映、現在の赤は未達として保持。

完全before/after、8外部/9資産snapshot、各識別値はpost174 proposalへ固定。新snapshot8件はfeature内候補ディレクトリのみ。正式dirの現未参照10件中2件は新提案が参照するため保持必須、受理後も未参照となる8件をderivation.jsonの別リストへ分離し削除せず主担当へ返す。corpusは既存pinned規則により271f8615f97591528e4a391334e37a431b720ea20ba485f55e7ecad74a5e5f28へ再導出し検証成功。

## 安定入力での最終検査と提出

`uv run pytest -n 2 tests/test_census_baseline_check.py -q --tb=short`: **74 passed / 514.27s / exit0**。inventory binding追随後の安定入力で全件成功。生成契約限定5件の成功と区別し、backend/root全件・正式archive/受理後履歴・GitHub合成mergeのCI成功は主張しない。

payload SHA256 `9150071ca34e11ac050030683749826209768e47e82886ef48348ec4231cc96f`、record案 SHA256 `492b1a09fd2c94ce387cc2ba4958785fb0cc5835fb78ee83c33057151e286a13`。sourceHEADは36424c53のままで、未コミット候補を一時indexのtreeと差分SHAへ固定して主担当へ提出する。tree識別値は自己参照を避けて外部cacheへ記録し、提出後に本担当は書込み停止する。

主担当に必要な次の動作は、独立非作者による新実値レビュー・PO委任による対象版受理、受理後の新173単一行/候補snapshot8件反映と旧orphan候補8件の整理判断、その後の正式PR合成merge受理検査と全件/CIである。承認者/日付を本作者が記入したり、未反映の赤を合格扱いにしたりしない。

## 独立追加レビュー第1回P1の採用

非作者/root/o5_final_reviewはtree e456edd6/source36424c53の限定追加1回を実施、P0=0/P1=1/P2=0。9資産/8外部/完全snapshot/26prefix/56関数/旧source/corpus271f/生成5件は一致。一方core357件中356成功/1失敗で、既存O5試験が現在の追加層をO5に固定し、既登録O5後のinitial_grant宣言回転と衝突した。主担当/rootはPO委任4/5/6/8によりP1を全採用し、同scope tests/test_core_guard.pyの正負2関数だけを是正する。登録済みO5を含む基線へ現宣言を追加し、全旧層順序/fixture1件保持・検出と限定外非包含を確認。負例はまず正規候補の成功を確認してから未宣言/誤領域/O5削除/置換を各々拒否し、既存JSON/宣言/製品guardの拒否を変更しない。

新実値の正式受理は是正レビュー後。core試験は外部8対象/固定corpus入力に含まれず、是正後に9資産/外部8/corpusの不変性を機械再確認する。旧追加1回/P1と基本系列を保持し、主担当は本是正差分・影響の限定追加2回目を必要と判断し許可する。新値の再計算を不必要に反復せず、同一値の主担当判断・独立確認を追跡する。

P1是正後のroot実行はcore357 passed/27.08秒・Ruff成功。9資産/外部8/全snapshot bytes/26prefix/corpus271fを主担当が再計算し、提案の完全before/afterと全一致、初回独立確認対象e456から凍結実値が不変と確認した。実値受理は第2回限定差分確認の後。

## 新実値のPO委任によるCodex受理・正式反映

2026-10-23T16:34:21.600455+00:00、Codex主担当/rootがPO指示4/5/6/8/9/10に基づき、新173実値を受理。対象は反映前HEAD8037e1d9（独立最終core11c19159、source差分5e6f1b9f/実base差分40581351、独立限定追加2回目可決0/0/0・357成功）。完全9資産/外部8の前後値・全snapshot bytes・8資産base+1/frozeninputs5・生成値・26prefix・corpus271fを主担当/非作者が照合済み。payload9150071c/record案492b1a09の全値を採用し、正式rowはapproved_by/approved_onの2項目だけを追加。山田正輝の個別確認/署名・人間逐行確認を代記しない。

#179は最終41258fe2/CI39981871883全必須成功後に通常merge31194a39、173は8037e1d9へ追随。1f506675から全9資産/外部8bytes/26履歴が不変なので同値の再導出・再受理を反復せず、今回受理の実baseを31194a39として対応付けた。旧173受理/5239原状/旧proposal/旧snapshotsはGit/候補docs/保全物に保持。新rowを末尾27件目へ追加し、新asset snapshot8件を反映。実base不在で新row反映後も未参照の旧候補8件だけをcacheへ再保全し正式dirから除去、基線snapshot/外部2件は不変。正式snapshot202は実base192と新規参照10の和集合。v2参照169以外の33件は全て実baseにある旧保全資産として変更しない。corpus271fは不変。

受理後archive/PR実merge-context検査、backend全件/root全件・最終CI/最終HEADレビュー/製品接続は未完。実台帳・端末資格・Port・安全なRG1 open・新5全体をこの反映で成立させない。

反映補助の初回は新row・8追加・今回8整理の後、v2参照だけと全snapshotの等値を過剰要求して停止した。v2抽出は旧保全snapshot全体を含まないことを確認し、実base192全bytes保持・新規10参照・欠落0/未参照新規0を検証して反映を完結。新rowの二重追加/基線snapshot削除はしていない。

提出前の整合: ブランチslugに対応する現在地写しplanを追加しin-reviewへ揃えた。元U-R1の9ステップ表/レビュー7回/DoDをbyte同一で参照し、親は全体未完のためactiveを保持。ローカル全件driverはcacheに準備済み未実行。必須CIのbackend/root全件で同じ最終HEADを検査し、同じ入力のローカル全件重複を増やさない。CI失敗・実DB診断が必要な場合だけ専用driverを用いる。ハーネス評価台帳への追記なし: 既存6.3⑤の宣言回転/既登録保持へ追随した実装試験の接合であり、検査モデルや運用規則の新知見・再設計はない。

## 提出候補の受理後検証

受理反映24eaa88bを対象にrootがarchive36成功/22.37秒、backend初期付与＋生成/tenant/runtime契約104成功/13.70秒、root/backend Ruff・ty、backend format379 files、docs-status21/0・計画同期・実origin/develop比tenant checkerexit0を確認。census74成功/514.27秒とP1是正後core357成功/27.08秒・独立357成功/10.71秒はsource/corpus不変の証拠として保持し、同じ全件を反復しない。実PR_ACCEPTANCEのGitHub合成mergeに対する検査、最終CIのbackend/root全件、最終headの非作者確認は提出時の別条件。

本追記を含む提出HEAD・binary差分・実baseはPR本文/委任証拠へ固定する。主担当は正式row27/承認メタデータ/新参照snapshot・旧base192全保全/今回未参照8整理/現在地写しとCSV実base追随の最終メタデータ差分に限定する独立追加3回目を必要と判断し許可する。旧156/170/173の系列と今回追加1回のP1・2回目の解消を保持しリセットしない。source変更や追加意味をこの最終確認へ紛れ込ませない。
