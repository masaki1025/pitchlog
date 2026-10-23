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
