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

## 独立部分の実装と正常供給前の検証

承認140a920dに基づき独立部分を実装。追加不足だった`check_authz_catalog.py`の固定route集合1件拡張は、主担当のplan限定追補→非作者0/0/0→PO委任承認677481ccを受け、旧7件/各欠落/余剰拒否を保持して実装した。
2factory/2正例/2tokenの候補とread route/matrixを追加し、JSONの全生成fieldを既存snapshot ASTから標準json/hashlib/astで導出した。36定数の対応を全件照合し、現入力で差分になったのは2定数（tuple/digest）だった。3定数だけとの先決めはしていない。

初回局所検査は22成功/1失敗（record_and_aggregate専用の既存TSK446 provenance不足）。新read計画のprovenanceだけで代用せず、既存専用provenanceも保持して是正した。Ruffのimport/行長とtyのoptional methodsも是正した。
最終局所はroot23成功/3.34秒、backend対象162成功/2.03秒、root/backend Ruff/ty・docs21/0・計画同期成功。
正式tenant checkerは履歴識別値未更新でexit2、正式authz checkerはread行がdecision lockにないためexit1。履歴/snapshot/lock/oracleは書き換えず、未受理拒否として保持した。

広いroot2ファイル検査は正常供給が到着したため旧状態で区切り、**26206 passed / 5 failed / KeyboardInterrupt、407.03秒、exit2**。全件完走/全成功とは記録しない。同じ旧状態の長い全件再実行はしない。観測済み5失敗は次のとおり。

- `test_oracle_reseal_preserves_inputs_and_expected_asset_digests`: route/matrix JSONだけが未受理変更され、既存の受理済み入力drift集合に不一致。
- `test_repository_is_green`: allowlist/repository射影を変更したが正式履歴・識別値を更新していないため拒否。
- `test_repository_oracle_assets_are_valid`: route-registryのoracle input blob不一致。
- `test_repository_catalog_covers_the_entire_requirements_file`: read行がdecision lockにないためCLI exit1。
- `test_repository_derived_assets_are_valid`: 同じread行とdecision lockの不一致。

## 正常な初期付与候補の隔離接合

rootから新PR #180の固定`dfa697721f35f573d2e3802783ff3d8d3cd218fa`（step3/4）だけを正式に供給された。これは候補の供給であり、#180の正式受理/実統合を主張しない。
WIP12ファイルを`/home/ymdms/.cache/pitchlog/preparing-read-registration-wip-nec9tskk`へ保全し、manifest SHA256 `f3d6ba7cae6a7a095de562188208a66cfb01219cf9d4dbafd4b3519dae4c4cfb`、stash `828c762c4329c039651c15722dbc5825b6e3fb1f`を固定した。
merge競合はcore3ファイルだけ。rootは登録union・guard全関数AST不変・元の先行宣言/別JSON履歴保持に限定した機械整合を許可した。正式実base180ではinitialを据え置き層へ回転してAPI2だけをpendingにする条件をplanへ残した。正式7.7/最終lock/oracleの編集はしない。

### 接合結果と最終局所検証

正常dfaの機械接合commitは`4be3789a966de893ccbd783757d0fe01ca405c7b`、root許可の正常descendant95dの通常mergeは`9544e28fb0e444979195de5b30e976628939e648`。
両mergeを実`_changed_paths_in_commit`で検査すると空集合、`verify_area_path_baseline(...,31194,HEAD)`も成功した。guard関数ASTは677/dfaの双方と一致し、JSONは双方の全旧登録順序/metadataを保持する。元各枝の先行宣言・別JSON履歴は残した。coreの全382件は22.84秒で成功した。

WIPの復元時の衝突はrepository JSON/moduleのsource_digestだけで、95dの全fieldを保持して再導出した。生成全36定数とJSON全fieldの一致、95dの履歴/識別値/旧登録の完全保持を確認。初期付与の5source/checker（生成repository module以外）は95dとbyte一致、生成moduleも初期付与側の全fieldを保持しread2型だけを追加した。f48b5944/8037e1d9は祖先にない。
現在のcandidate revisionは正常供給からのallowlist35/repository24を保持した未受理内容であり、正式175の新revision/値を受理したものではない。repository source_digestは現JSON全値から`bf4ec2aa44c888131c1c09d8de2f259f7ef9199e3186004346f8feefee034f08`へ導出した。180rowのafterを175 readへ延長したとは扱わない。

post-join局所はroot23件成功/3.65秒、backend対象162件成功/3.45秒。root/backend Ruff/ty、docs/計画同期成功。旧状態の長いroot全件は再実行しない。
frontendはfrozen installのみで宣言/lock差分0。現在の実候補でread専用command `pnpm exec playwright test --config src/screens/GameScreenPreparingRead.playwright.config.ts`をexec session14368で実起動し、Running3/worker1から**3 passed / 24.7秒 / exit0**の完走を確認した。実login/Cookie/C2/専用PGのlist/detail/reload、ページ境界、越境404、abort/明示確認を通し、stub/新TLS・署名鍵/旧sealed driverは使っていない。実行前後のpitchlog-authz container0、補助process0、runtime tmp0。旧10/20出力dir37件は増減なしで削除していない。

実origin/developは31194a39と一致。HEAD9544＋未commit WIPのtenant `--base-ref31194`はexit0になったが、HEAD凍結比較とworkingtree参照範囲を含む結果であり正式175受理ではない。authzは未更新decision lockのread行追加でexit1を保持した。最終step固定HEADから95dを比較元に改めて検査結果を主担当へ渡す。実180統合後にはinitialを据置き層へ回転しAPI2のみpendingとして完全before/afterを再導出する。正式175履歴/snapshot/最終lock/oracleの自編集0、通常push/PRなし、親追加敵対1回は未消費。


## 初期付与の実統合後の宣言追随

#180は547d199eへ通常統合、95dと全tree同一をrootが確認した。正常merge後、tenantのpendingは新read2pathだけへ回転し、JSONは実547の全paths/順序/guard_pathsを保持して新read2件だけ末尾へ追記した。宣言ca9e2b03とJSONf69b278fは別commit、全guard関数/class ASTは実547と同一。実547→f69のverify_area_path_baselineは547を返す。同期/記録の初期付与宣言・全登録は維持し、旧初期付与の段階試験は当時の宣言を明示した隔離CLIへ分けた。

追随の初回は379成功/3失敗/26.27秒、歴史的fixtureが新pending宣言を使ったtenant不一致。合成fixtureの当時宣言を保持した次回は381成功/1失敗/24.20秒で、CLIも現在scriptを呼んでいた1件を確認。同一の当時scriptをCLIへ渡す局所fixture是正後は全core382成功/26.35秒。製品拒否条件・判定関数・例外は変更せず、旧部分/片側/順序/共変更拒否を保持した。3実行を単一成功と書かず旧失敗logをcache/preparing-read-core-after180*.logへ保持する。

正式9/8値・7.7・認可lock/oracle/175親追加レビュー1回/必須CI/実新規作成は未達。これは無関係な基線追随・必要な機械是正を既PO委任で行った記録であり、本人の逐行確認/署名ではない。


非作者rights_replacement_reviewは741bb698/比較6f60983cの機械追随限定確認0/0/0、独立core382成功/22.72秒。binary diff78742cfed90802c2bf4b7d0c70b6dc0e24901f0e09b5ee63b18b1ba55aca3141（full-index576a1788ad40d10b4ad04b395234746d98ae019ce76e55bb027707e55de75384）。親175正式追加枠は未消費。

実547の完全9射影/外部8をrootが再計算し、readで動いた射影はallowlist/repository2件だけ、他7/外部8は同一と確認。候補識別はallowlist35→36/repository24→25とし、repositoryのsource_digestと生成moduleの全fieldを対応させる。初回はJSON source_digestの追随漏れで47成功/1失敗/1秒、生成とJSONを同じ正規化digestへ是正して局所再検証した。履歴27prefix/202snapshotはこの候補段階で不変、正式受理は未成立。新値の独立照合/根拠/承認を後続に記録し、古い180受理をread差分へ自動延長しない。


認可の通常派生導出`--asset-spec product --reseal-derived`は1418項目検査成功、route/matrixのlock2件だけ更新、auth-catalog/claims/権限/意味は不変。oracleの入力8blobを含む次commit Cを固定し、context6/sealと既存oracle_input台帳の実識別値を同じCへ前進させる。C固定は正式受理/封印そのものではなく、後続の限定差分・完全値レビューとPO委任受理後に反映する。


正式受理前の完全値候補はcache/preparing-read-175-acceptance/proposal.json（SHA325e1a0803f021378c1ef0ad9cb7358dbe0c38b365fa45faf57de52df5cb9412）。実547→4c5b3794で9射影を全導出、変化2/不変7、外部8不変、27history/202snapshot全bytes不変。C=bda1262947ba284374a5e14b532c2ef3c3859544は追加の認可lock2件と研究記録だけなので、9/8の提案値は同一。aspectは実derive_aspectsのdeclaration/asset_snapshotsだけであり、外部不変を変更に数えない。

oracle6context/sealのcommit文字列を旧426d→同じCへ前進した候補を固定。6意味行は全不変で、ここではseal再導出・oracle_input系列行の正式追記をしない。必要な既存frozen-baselines.json系列の末尾1行追随をroot後続scopeへ明記し、旧全行・配置・target・拒否は保持する。cache/oracle-ledger-row-proposal.jsonのSHA1a9fa6733b2143dc566e376f66807047c8b7ee69bcff511e538c68024f0449d5は承認者/日付なしの未受理提案。全実値とこの最小scopeの非作者照合後、PO委任判断を根拠付きで正式記録してから必要行/封印を反映する。本人の個別確認を代記しない。


## 正式値のPO委任受理と反映

2026-10-23T19:07:51.897444+00:00、Codex主担当/rootはPO4/5/7/8/10と2026-10-24優先指示で、10fd/実547の完全提案325e1a08を受理。非作者rights_replacement_reviewは02ecの全9射影/外部8/19snapshot実体/全前後値/identifier/aspectを独立再計算して一致、0/0/0・48局所成功。C/02ecと後発10fdは9/8実値不変。証拠f7e85b13、全diff898657d2/直前diff706630c2。旧27prefix/202snapshot全保持、提案に承認者/日付2fieldだけを加えて175row1/必要snapshot2を反映し28/204とした。

6oracleのcommit以外の意味不変・入力8blobC=bda12629一致と、既存oracle_input系列の旧13prefix/target/配置保持の末尾175提案1a9fa673も同非作者0で確認し受理。提案に承認者/日付2fieldだけを加えて14行目へ反映。最小scope追補を委任で承認し、人間本人の個別確認/署名/逐行確認は記録しない。

root補助の初回は旧271f corpus不変という誤ったassertで停止した。入力宣言は同じだがread正例2追加・3既存入力の変更で実digest6e362f63へ変わることを実runnerと非作者の固定Git独立計算で確認（証拠dadb2245）。生成値の通常追随としてmanifestのdigest1fieldだけ更新し、旧pinned履歴6/名集合/全case/期待値/runner/選択宣言は不変。続く反映補助は旧legacy履歴にacceptance_idがない行を同形式と仮定してKeyErrorで書込み前に停止し、getによる存在確認へ是正。新rowやsnapshotの二重追加はない。封印再導出/更新flagなし全検査/親175全最終追加レビュー/必須CI/実保存成功は別未完ゲート。


反映後のtenant checkerは更新flagなしexit0。oracle再封印は起案の`--asset-spec product --reseal-oracle`が製品DDL（oracle_contextを持たない別資産）を選んでseal不一致を拒否し、書込みなしでexit1となった。実6対象はrootのprobe oracleであり、実装/検査器を変更せずコマンドを`--asset-spec probe --reseal-oracle`へ是正。全1418項目/202 oracle claims/235mutants/24cutsetsを検査し再封印成功。planの同コマンド1件だけ追随した。製品DDL検査は別途productモードの更新flagなしで実施し、probe/sourceと製品認可を混同しない。受理したC/6意味行/9射影値は変わらない。


反映後の更新flagなしtenant checker/probe oracle全検査/product認可検査/frozen-baselines invariantsは全exit0。archiveとcase runnerは65成功/67.47秒、旧pinned集合・期待結果をそのまま通した。root Ruff/ty成功、文書21件/違反0。これらは正式develop提供や必須全件CI、175親最終追加敵対1回を置換しない。


## 親175の最終追加レビュー・提出処理

許可済み親追加敵対1回は0ae8ee37470d4ceb02a9282c32629bc9fece5d22/実547/全72path binarydiff6b95482189837e5481341caf12a257310bc28df3d02e26863e154a30db6bdc83で消費し、非作者rights_replacement_reviewは0/0/0・重大未解消なしと判定。JSON復元を全文含め、独立backend162/9.11秒・frontend183/15.91秒・root22/9.19秒、更新flagなしtenant/probe/product/frozen検査を成功。旧基本2回/各component系列/全失敗とP6留保を保持する。証拠cache/review-read175-final-0ae8ee37-evidence.json SHA23ab88e0a6e9259dc884f5fceaba1cd489e143918231582ac440f31614ce2070。最終CI/実PR2親mergeと公開branch更新はroot後続、作成/開始/初球は未達。

提出時に本局所planをin-reviewへ、親UG1 planは6段階/DoD/status activeのまま提供範囲と継続featureだけを明記。これはPO委任の編集/統合順の最小具体化で、readを親作成全完成へ誤表示しない。ハーネス評価台帳への追記なし: 今回は既存委任手続き/検査器の同一規則を使い、候補命令のspec指定・履歴fixture/生成値追随の局所是正をresearchに保持する。恒久統制の再設計や新しい一般規則は導入していない。後発は上記3文書の提出メタデータだけで製品/正式値/検査bytes不変、非作者限定確認後に公開する。


## CI frontend失敗と限定bootstrap是正の起案

2026-10-23T19:50:53.918344+00:00、必須CI40011535070/frontend job120613591944は1853成功/3失敗で、GameScreenE2eProcess.specの新origin拒否3件がexpected exit1に対してstatus null。frontend jobはNodeだけでbackend venvを作らず、新試験のbackend/.venv起動依存が不整合。全run実行中のgh run view --log-failedはログ未提供を返したため、終了済みjob logs APIで当該jobを取得して特定した（別CIを再起動していない）。rootは同じorigin拒否を標準Python先行入口で検証し、実DB/認証起動は分離して既存意味のまま保持する最小scopeを追補する。旧CIを成功と数えず、残るbackend/harnessは同HEADの結果を回収し、修正後は新HEADで必須CIを確認する。


## CI bootstrap是正の実装・実接合結果

承認b574aaf6の限定3sourceを実装。Support.pyを標準ライブラリのみの先行origin/mode検証へ分離し、同一関数を実Server.pyも呼ぶ。実serverのfixture/auth/専用DB/cleanupの5関数ASTは旧6caaと一致し、自己path以外の処理は保持。Process.specは実入口をpython3 -I -Sで起動し、spawn失敗/signal/timeoutを正しい拒否へ数えずexit1/正確な理由/ready未作成を確認する。

旧入口のstdlib-only再現は3失敗（依存psycopg読込が先行し拒否理由不一致）、是正後process8成功/1.28秒。全frontend92files/1856成功/164.27秒、ESLint/vue-tsc/root Ruff/ty成功。envDir:falseのrepo外configを使い.envを読まない。実browser3成功/27.2秒（login→Cookie/C2→API→専用PG、一覧/詳細/reload、越境404、通信断→明示確認）。実行後docker稼働は共有pitchlog-db-1のみで自前資源cleanup済み。正式9資産/外部8のbytesは6caaと同一。実新規作成/初球/実機成功ではない。証拠はcache/pitchlog/read175-bootstrap-fix/{before-origin,after-process,frontend-full,browser-read}.log。

CI40011535070は最終的にfailure。frontend3失敗のほか、backendは3379成功/3失敗/4skip（route期待18対20、registry期待45対47、位置依存の拒否fixture）、harnessは29798成功/3失敗/2skip（failure-injectionのDDL blobとMC/DCのclaim-map blobの派生参照未追随）。元ログをcache/preparing-read-175-acceptance/ci-{frontend,backend,harness}-job.logへ保持。新HEADの全件CIは別途必要であり、旧結果を成功へ読み替えない。
