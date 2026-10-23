# 正式read登録候補の起案調査

## 固定組立と不変境界

2026-10-24 JST、主担当の明示許可で新worktree/branchを指定実develop点から作成した。
今回はplan/researchだけを新規起案し、候補metadata・fixture・正式JSON/正本の新編集はしていない。

| 入力/組立 | 固定HEAD |
| --- | --- |
| 実develop指定起点 | `31194a39c9083bbef6c14bde19c24a3e49d09f2e` |
| API限定受領候補 | `270347f0658a9c233ce788ad11424b652e564a1c`（source `b3a8ef8bb7f1200c423fc32ec803300a0f1724ee`） |
| API履歴付きmerge | `68ee1bf81bbeeec7852237f1930fabdcbae95e32` |
| UI固定候補 | `9e5c59c3b57012547b3e32932bf8d850cb63eee5` |
| UI履歴付きmerge | `25b9cc1d00ac39fa1fe98c467d4edbf9e0f9e0fe` |
| browser固定候補 | `4977c1b640713b4907ebdad7c99a62f18dd982e3` |
| browser履歴付きmerge/組立HEAD | `f5bda183300846ba2d457cfa9c9eb92cdeffdd7e` |

すべてortの自動mergeで手動競合編集0。起点からの`git diff --no-ext-diff --binary --no-renames`のSHA256は
`357d94edd80e54b684107084d2bb2986d5fee8878c7f282b525eb03bb5ae7f07`。
起点からcontracts/requirements/design/ADR/development/opsの差分は0である。
APIから主要source5、UI6、browser6の計17パスのbyte一致をそれぞれの固定点と実照合した。
単一規則codecは指定develop起点とbyte一致、SHA256 `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4`。
個別レビュー済みsourceの再実装・旧#173 initial/propsの移植はない。

主repoのdevelop先端は作業中に別途進むため、指定起点を勝手に最新扱いしない。
依存単位は実173単位または正常履歴の置換PR。隔離接合に使えるのは主担当/rootが後で通知する新しい正常置換候補HEADだけで、現時点では未供給である。固定正常候補を受領し、独立レビュー/PO委任承認後は実統合前からmetadata候補の実装を進められる設計とした。
正常置換PRの実統合後の実baseからの完全before/after/履歴/snapshot/最終sealの受理はroot唯一writerの後続ゲートである。

## 不足する登録と実source

通常registryには`PREPARING_GAME_READ_OPERATIONS`の2件、C2には`preparing_game_list/preparing_game_detail`が既にあり、重複実装は不要。
正式repository契約の2token、SELECT factory2件のallowlist/正例、authz route/matrixへのread対応は未成立である。
旧#175資料の候補signature/パスを再利用するが、旧45→47件・revision・digest・受理値は現基線の確定値に流用しない。

許可sourceは`pitchlog.repositories.games._preparing_game_list_statement`と`_preparing_game_detail_statement`のみで、SQLA_SELECTだけ。
正例予定は`tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games.py`と`games/__init__.py`。
2ファイルを同moduleへ解決する既存方式により、fixture pathの一意性と完全修飾signatureを両立する。
新CAP/任意SQL/Session/書込/DB privilege/RLSをこの登録で増やさない。

authz候補は`ROUTE:RECORD:games:read`のrecord_and_aggregate/design/readと、対応するconditional matrix行。
現在のHTTP matrixのresource_kindsは集計用3値であり、gamesを足す必要はない。record_and_aggregateはconditionalでありshared_dataの3軸cellsとは別。
method/pathはmatrixに保存されないため、GET2・operation ID2・TenantMatchedRoute/C2の対応を入口試験で別途固定する。
test_ownerは実収集node IDに対応させ、未実施ならplannedをimplementedへ読み替えない。

## 生成手順の調査

現sourceにはrepository_contract.py専用generator CLIがない。既存`pitchlog.authz.runtime_contract_generator`のrender/check/switch/rederiveはauthz runtime_contract.json/py用であり、repository契約の生成CLIではない。
この単位では新しい常設generator pathを追加せず、既存JSONのcanonicalizationと標準json/hashlib/astで全field対応を決定的に導出する。
正は`backend/tests/test_authz_repository_contract.py`の`_asset_snapshot`（baseline_controlだけ除いた全入力）と`_generated_snapshot`の一致、source digest、実signature/registryとのexact-set試験である。
更新を先に3定数だけと限定しない。正常置換候補でfactory binding等が加われば、そのfieldも生成moduleと比較へ含める。
既存 `_asset_digest` はsource_digestだけを除き、UTF-8/ensure_ascii=False/sort_keys=True/separators=(',', ':')でSHA256を取る。
JSONの生ファイルhashやauthz runtime generatorの結果をその代用品にしない。

正式受理雛形CLIは`pitchlog.authz.runtime_contract_acceptance`。実base/acceptance ID/実承認者/日/理由/移動事実を受け、repo外bundleへ出力する。
派生lock生成は`check_authz_catalog.py --asset-spec product --reseal-derived`でroute/matrix/auth-catalogの3lockを扱い、最終oracle sealは別の`--reseal-oracle`である。
両者をこの起案で実行せず、正式受理前にshared履歴/値・snapshot・sealを追記しない。rootが正常置換PRの実統合後の実baseで直列に再導出・受理する。

## core被覆

指定baseの全core pathsは組立後の同領域pathsの先頭に同じ順で残り、guard_pathsも完全一致した。
API枝から既存tenant-isolation追加2パターンだけが加わり、既存O5等の登録は消えていない。
新規正例2パスは既存`tests/fixtures/tenant_boundary/*`、生成moduleは`backend/src/pitchlog/repositories/*`、
formal JSONは`contracts/tenant_boundary/*`/`contracts/authz/*`、既存試験パスも既登録である。
新test/script/実行candidateディレクトリを作らない計画なので、core追加登録は不要。将来必要なら実装前に別差分へ分ける。

## 承認と未達

起案時はこの新計画のレビュー0回・未承認として記録した。旧#175/個別API/UI/browserの回数・採否と、親の正式追加敵対1回未消費を保持する。
source接合済みは正式認可read閉集合/TB005/7.7の受理ではない。作成/resolver/RG1/1球/1試合/運用HTTPS・実機の成功でもない。
承認後の実装は新しい正常置換固定候補との隔離接合と局所metadata/試験を進め、正式実統合を一律開始条件にはしない。
不足が新意味/新DB権限に及ぶ場合は具体的な最小差分だけを主担当へ返す。

## 起案の検証

docs-statusは21文書/違反0、局所計画同期（base `31194a39c9083bbef6c14bde19c24a3e49d09f2e`）と差分空白/NUL検査は成功。
`uv run python scripts/check_tenant_boundary_bypass.py --base-ref 31194a39c9083bbef6c14bde19c24a3e49d09f2e`は**exit1**、
`pitchlog/repositories/games.py:88/:114`のSQLA_SELECTを**TB005 2件**として拒否した。これが現在残る未受理allowlist境界であり、成功へ読み替えない。
既存read実HTTPの対象名は`test_preparing_read_real_login_paging_and_snapshot`、`test_preparing_read_auth_and_c2_precede_query_sql`、
`test_preparing_read_invisible_details_are_uniform`、`test_preparing_read_invalid_saved_values_roll_back`、`test_preparing_read_real_select_denial_is_sanitized`。
今回それらやbrowser/実DBは再実行していない。新規ファイルは本plan/researchだけで、組立後の既存source/正式assetsの新編集は0。


## 正常履歴の置換依存への追補

主担当から独立履歴監査の結論を受領した。f48由来の同一commitでのcore JSON/guard定義変更違反は旧173公開0aaa側にあり、旧175/公開、API/UI/browser、組立f5には伝播しておらず履歴違反0。これは主担当からの監査結果であり、この起案で全履歴を再監査したとは記録しない。指定3候補/f5の再構築は不要として保全する。

旧173の0aaa/8037等をf5へmergeすると違反が伝播するため禁止する。旧文書/値は参照だけで、旧受理行の移植も行わない。隔離供給はrootが今後通知する新しい正常置換候補HEADだけに限定する。正式before/after/history/snapshot/最終sealは、その正常置換PRの実統合後に実baseからrootが唯一writerとして直列に再導出・受理する。正常固定候補を使うmetadata実装は独立レビュー/委任承認後に先行可能であり、実統合を候補準備の一律停止条件にはしない。

この追補の編集はplan/researchだけ。生成全field対応（3定数だけと先決めしない）、既存core被覆による新規登録不要、現在のTB005 2件未受理、既存レビュー回数/親の正式追加枠未消費の根拠は保持した。


## 独立計画レビュー第1回P1の採用

対象固定SHA256はplan `7a606525413ebdf979709d2a92b25ce6f6316942c2418ae798cd81f9b832ed08`、research `495e123fc7d11d210a619509393f9e3bfd0704d670cc498788ce50ffec93c565`。
主担当から独立第1回結果 **P0=0/P1=1/P2=0** を受領し、P1を全採用した。計画レビュー回数は1、改訂は未再レビュー・未承認。旧175/個別候補の回数と正式追加敵対枠は変更しない。

指摘はroot後続のoracle手順不足。`--reseal-oracle`はoracle_commitを進めないため、route/matrix変更後の新入力と旧commitでは正式検査が成立しない。
組立f5の`scripts/check_authz_catalog.py:7121`からの`_build_oracle_seal`はexisting sealをコピーしinput blob/digestだけを更新し、`:7184–7225`の`validate_oracle_seal`は6資産のcontext/seal commit一致と、そのcommit上の8入力blob一致を要求することをsourceの該当節だけで照合した。oracle6資産の内容をこの追補で読取/編集/移植していない。

plan第5節へroot後続ゲートとして追記した：更新済み8入力を確定するcommit C固定→oracle6の`oracle_context.oracle_commit`とsealの`oracle_commit`をCへ同時前進→最終6資産の必要差分レビュー/受理→再封印とflagなし全件検査。8入力がCから変われば入力commitの固定と影響差分の確認へ戻す。
この追補はcandidate source/編集scopeへoracle6を加えず、metadata候補実装開始を正式受理待ちへ戻さない。現在の変更はplan/researchだけ、code/正式assetsの新編集は0である。

第2回計画差分/影響レビュー: /root/independent_review、上記b9c01f62/1cddce04、可決0/0/0。rootはplan末尾の対象/日時でPO委任承認。root8入力固定commit→oracle6context/seal同時追随→最終差分レビュー/受理→再封印の後続順を保持。
