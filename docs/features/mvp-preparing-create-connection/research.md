# preparing試合作成接続の調査

## 起案の固定点と所有

2026-10-24、rootから試合作成接続の限定計画だけを委任された。新branch/worktreeの同名不存在を確認して、実develop固定`31194a39c9083bbef6c14bde19c24a3e49d09f2e`から作成した。所有はこのディレクトリのplan.md/research.mdの2パスだけ。既存read worktreeの編集は停止維持し、source merge・製品/正式資産/他worktree編集・新鍵発行・DB実行・push/PRは行わない。`.env`/秘密/legacy/P6 sealed期待値を読まない。

参照固定点はread `6f60983c4c905008615b7683c1f7084b8b1a5b45`、resolver `efe497ec05ca8784d6f570480ba6970c7134e149`、正常initial `95d766f5d20234b1d534538b96fc369eda1cc6f1`。その存在とcommitをgitで照合した。これらの個別正式受理/実統合未完を実develop提供済みとは記録しない。initialはread祖先でありRG1成功供給ではない。

## 原典・実装の照合

| 固定source | 必要箇所と結論 |
| --- | --- |
| 親d68e10ed `docs/features/ug1-preparing-connection/plan.md` §2/4/5/6と末尾採否 | 2026-10-22親6ステップ承認・基本2回履歴を保持。5/6は必須大会供給/新名登録、作成API、フォーム、同取引全取消。前段入力/拒否は先行可。6/6の実画面受入とread追加敵対1回は別単位 |
| 同`design.md` §2/3 | POST games/GET preparation-options、new/existing排他、commit後201、auth/C2をbody/業務SQL前、resolver4失敗のHTTP外形、結果不明自動再送0。大会なしへ縮めない |
| 起点 requirements FR-001:216–219、FR-014:363–365、§4.0-3:186–191 | 大会は必須・作成中の新大会登録を中断なしで供給。5区分/任意label/紅白戦同teamを保全。大会はチーム拡張語彙で、新挙動や管理権限を足さない |
| 起点 data-model §5-1:749–756、§10-3:2056以降、§10-5末尾 | 同team可、必須大会、ID参照・無効化/改名。段階Aは大会親FOR UPDATE→待機後別文で割当→既定/規則FOR SHARE、試合/RG1と同scope。大会名正規化・表示名uniqueは規定しない |
| 起点 `db/game_state/models.py` Game:66–158 | game status、必須tournament、複合team FK、入力label、snapshot/NULL上書き/開始。FKだけでは大会category/disabled・team hiddenを拘束しない |
| 起点 `db/tenant_isolation/models.py` TeamRecord:105–162、TenantVocabulary:1220–1280、migration0010:54–88 | self/opponent、selfはhidden不可、opponent hiddenあり。語彙PKは(tenant_id,key)、category/disabled/display_name Text。大会名unique・長さ制限・Unicode正規化なし。チーム認証名の正規化は別目的で転用しない |
| read `api/schemas/games.py` | 既存PreparingGameCreate/ExistingTournament/NewTournament。aware日時・5区分・両UUID・任意label、extra forbid、名称min_length1で空白だけはまだ拒否しない。候補新名をそのまま有効業務名と認定しない |
| read `api/routers/games.py`、`api/tenant_access.py`、`repositories/games.py` | GET list/detailとC2、通常token/SELECT、正規snapshot readのみ。作成service/POST/optionsは未実装。静的optionsを動的ID前に挿入する必要がある |
| resolver `repositories/rule_resolution.py`:47–150 | StageARuleRequest(game_type_key,tournament_key,rule_override_present)、実scope exact型、単一run_function・正規codec、公開4失敗。別Session/callback/合成成功型を受けない |
| 同`contracts/authz/product/function-bodies/functions/FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean).sql`:72–125 | 必須非空大会・有効category親FOR UPDATE、別文で割当拒否→固定既定→規則FOR SHARE。新語彙は同取引から見える親にできる。割当/上書きをfallbackで隠さない |
| read/resolver `repositories/rg1.py`、実RG1関数候補 | 公開read_rg1_open/assert_rg1_open_before_commit/RG1Unavailableと2token。現供給は常閉であり成功保存の証拠はない。initial供給を成功許可へ読み替えない |
| 起点 `contracts/authz/product/capability-catalog.json`:60–69/319–367 | CAP games read/insert、system_vocabularies read、team_records read、tenant_vocabularies read/insertが既存。新CAP/ACLを用意せず内部operationへ対応。system_vocabulariesは非tenant表なので通常tenant tokenへ偽装しない。optionsの固定区分表示は既存game-type seed参照を選ぶ。 |
| read `GameScreenEntryProvider.ts`、`GameScreenEntryTypes.ts`、`frontend/src/api/games.ts`、`api/roster.ts` | 実Pinia/QueryClient/tenantBound、epoch/tenant/route/要求世代、read自動retry0。既存self/opponent APIを再利用できる。作成mutation/formは別追加が必要 |
| 起点 harness §6.1/6.3/7.7、read checker `_build_oracle_seal`/`validate_oracle_seal` | 承認→1step/commit、コア捕捉、未確認拒否/旧登録保持、完全before/after受理。oracleは8入力commit固定→6context/seal同commit前進→差分受理→resealが必要。resealだけではcommitを進めない |

## core対象の実在照合

起点とreadの`.claude/core-areas.json`を読み、fnmatchで予定パスを照合した。後続実装は正常read供給の接合後に限る。

| 予定path | 既存登録と領域 |
| --- | --- |
| `backend/src/pitchlog/services/game_creation.py` | read追加の同exact、tenant-isolation。起点では未登録なので供給前に作らない |
| `backend/tests/test_game_preparing_create_boundary.py` | 起点のtest_*_boundary.pyとread追加test_game_preparing*.py、tenant-isolation |
| `backend/tests/test_game_preparing_components.py`/read_boundary.py | read追加test_game_preparing*.py、tenant-isolation |
| `backend/src/pitchlog/repositories/games.py`/operation_registry.py/repository_contract.py | repositories/*、tenant-isolation。RG1登録など既存複数領域の帰属も保持 |
| `backend/src/pitchlog/api/routers/games.py`/schemas/games.py/app.py/tenant_access.py | api/*、tenant-isolation |
| `frontend/src/screens/GameScreenPreparingCreate*`/GameScreenEntry* | GameScreen*、既存5領域すべて |
| `frontend/src/api/games*` | frontend/src/api/*、tenant-isolation |
| `backend/tests/db/test_game_preparing_create_db.py` | backend/tests/db/*、既存5領域すべて |
| tenant-boundary JSON/positive fixtures/既存root試験/authz checker/route assets | 起点で既存登録、限定追加を要しない |

新core登録は不要。実core_guardの部分overlap拒否を回避しない。supplier pending宣言はactual統合baseで必要な据置き回転をrootが別途受理する。今回planのみでcore3を変更しない。追加pathがこの閉集合を外れた場合は限定宣言/試験→別JSON→製品を先行する追補が必要。

## 既決事項・残りの限定判断

| 区分 | 根拠・例・扱い |
| --- | --- |
| 既決 | 大会必須/new登録・5区分/任意label・同team許可・段階A/単一codec・RG1前後fail-closed・同取引全取消・201はcommit後・結果不明再送0。POへ再照会しない |
| 通常実装選択 | server opaque UUID key、SQL keyset/limit、tenant注入、既存client/roster/型使用、team UUID順の重複除去、静的options先行。既存意味/権限を変更しない |
| 名称規則の残り | 親は名称長/正規化を既存規則へ照合するが、照合した要件4.0-3/FR001、data-model10-3、既存schema/migration0010/DTOには大会名のUnicode同一性・空白only・同名再使用規則がない。例:`春季大会`/` 春季大会 `、半角/全角、空白only、disabled同名、有効同名異key。planの限定提案は無変換保存+空白only拒否+完全一致既存名は409選択要求であり、現採用済みとは記録しない。表示名unique制約/同時新規名排他を新設しない。この最小追補は本計画レビュー/root委任判断対象 |
| 接続待ち | 実RG1成功許可source/権限・2接続の安全境界。常閉をtrueへ直さない。DML/DTO/form/拒否準備を止める理由にしない |
| 後続正式ゲート | read/resolver/initial/RG1のactual統合、createの7.7/lock/oracle/新route、親6/6画面全受入。候補実証を正式提供・read追加枠消費へ拡張しない |

## レビュー・検査記録

初回起案時は非作者レビュー0回・採否未発生であった。第1回非作者レビュー/root/rights_replacement_reviewはf77c172b対象でP0=0/P1=1/P2=0、rootがP1を全採用。今回その指摘を反映し、レビュー回数1・改訂未再レビュー・承認未とする。親の基本2回/read追加1回未消費、関連候補の既存レビューを保持し、新計画の承認へ流用しない。検査結果と対象SHAは提出時の報告へ固定する。現時点で製品試験・実DB・実HTTPは実行していない。

## 固定参照のSHA-256

| 参照 | SHA-256 |
| --- | --- |
| 親plan | `fdc1fa9e46e567c88e21c90aedd9403713d17f09b0633a07c44386f4c15b6926` |
| 親design | `d93ced7f86cbb2f10cadfdd6e1af19d71b24d8a8844cc00aa77a7647f07100b8` |
| read schema | `05e93029c9a2abd3ddd014d8806accad17fe83e38798daa2f8c49cac6c03483e` |
| read core | `3b324f5d073e8b1f295b9aa20907aaf41ea2a25b8aad91c4f98803068bfb4451` |
| resolver | `a7ddbc6dd4689bad7748075af49068663da1c4b2d713b000392bc97b06b63cf8` |
| 語彙/team model | `c4c7a53bc2e690441d73613d03aadad25d70213f92a57b88551a57ef730029ea` |
| capability | `29ba71c759e0c5eab6d4637c1efe83bdbebe5cbb11dbc003ebb73eafa52a46e5` |
| RG1 | `7e04ce1fd9284d059d44178b1df1df101b3166da302b9e8b62d20f51dd0b1c65` |

追加の局所照合: 起点`repositories/base.py`:172–181はFOR SHARE/read変種を拒否する。`authz/capability_registration.py`:`_is_lineup_team_lock`/1428–1436はteam id1列・tenant/id/kindのbind・hidden IS NULLの通常FOR UPDATE形を既存CAP:team_records:readで限定許可する。planはこの形だけを再利用し、大会親はresolver自身がロックする。新しいshared-table operationや汎用lock検査緩和を必要としない。

## 第1回P1採用と改訂（2026-10-24）

対象旧HEAD `f77c172b0b116ca2c2b69a27fb27a3eaf6f0d91e`、旧plan SHA `841e392249e8a9ba9a70f955cfa34ca1e4372387c001ddec42dd9e5d8aaaa543`。非作者/root/rights_replacement_review全文結果はP0=0/P1=1/P2=0、否決。P1内容は、既存readのgames.py/games/__init__.pyだけでは新SQL factory群の一意正例を供給できず、checkerのfixture重複拒否と矛盾し、テスト記述も旧2factoryのままであったこと。rootが指摘を全採用、反映未再レビュー。元の否決を消さず今回レビュー回数1を保持する。

修正はplan/researchだけ。source/JSON/fixture/DBの作成・変更0。新module `repositories/preparing_game_creation.py`へ6factory/7tokenを集め、step1の候補とstep3のproduction/metadata登録を分離する。正例は新exact6パス、read既存2パスは無変更、team lookup/既存RG1/resolver/GETを再利用する完全集合をplan表に明示した。SQL種別を混在許可する汎用builderにまとめず、INSERT2関数はSQLA_INSERTだけ、SELECT4関数はSQLA_SELECTだけを許す。

実checker根拠は固定read `6f60983c`の`_load_allowlist`:900–905（fixture一意）、`load_contract`:1606–1616（正例ファイルexact-set）、`scan_directory`:5931–5957（宣言fixtureに限りsymbol末尾2成分をclass-qualified aliasへ写す）。既存`positive/pitchlog/db/startup_allowed/_require_same_database.py`のclass stage_a_startup + staticmethod形を読み、新6fixtureではclass preparing_game_creation + 各factoryのstaticmethod1個へ対応する。余剰__init__.pyを作るとexact-set違反になるため作らない。

固定6f60983cの実checkerを読み、candidate source/正例/JSONをディスクへ作らず、メモリ内の6個のclass-qualified fixture文字列と追加AllowedSymbolだけでaliasとAPI検査を実行した（PYTHONDONTWRITEBYTECODE=1）。各6件について正例違反0、全拒否でTB900ちょうど1、SELECT/INSERT逆API・text/update混入でTB005を確認した。これはfixture構成の実行可能性の局所調査であり、候補製品6factoryの実装済み/本試験完了/正式受理ではない。sourceとJSONへの書込0、DB/接続API実行0。新fixture実装後は既存scan_directory全正例exact-setと各新pathの全拒否を正式な対象試験で検証する。

coreは固定6f60983cの実JSONで照合する。新sourceは`backend/src/pitchlog/repositories/*`、一意fixture6パスは`tests/fixtures/tenant_boundary/*`に一致し、いずれもtenant-isolation。境界試験は前回のread登録内。sourceglob/fixtureglobとも実在しており新core宣言/JSON登録は不要、core拒否/旧登録/順序の縮小0。新module/6正例追加を予定scopeに明記する。

名称提案について第1回は追加指摘なし。rootは最終計画承認で無変換・空白only拒否・完全一致new重複409をAPI入力/失敗の具体化として委任判断する予定、と通知した。現時点は承認未のまま、旧採用済み/表示名global unique追加として記録しない。旧175基本2回・親read追加1回未消費、各供給の既存レビューを維持する。

## 計画承認と第2回受領

2026-10-23T18:35:59.893253+00:00、非作者rights_replacement_reviewの第2回限定反映差分/影響0/0/0を受領。6正例のclass-qualified実行可能性を独立メモリ内確認し、初回P1は解消。rootはplan末尾の固定SHA/PO委任根拠で計画と名称のAPI具体化を承認。source/fixture/JSON/DBはまだ未実装、指定されたステップだけ実施する。親/既存供給の全レビュー系列・未達を保持する。

## 承認後ステップ1/3の実装・検証（2026-10-24）

rootの実装指示と承認commit `e7e34ef6`を確認し、指定ステップ1だけを実施した。第2回非作者差分レビューは0/0/0、rootによる大会名入力の具体化を含む委任承認はplan末尾に保持する。plan末尾の古い「未再レビュー・承認未」1文だけを現況へ機械追随した。初回P1・採否・親基本2回/追加read1回未消費の履歴は消さない。

### 正常供給の通常接合

- read6f60983cを`2ae8d80b8077855c6f0e1a3dde41b2ff1ac74f47`で通常merge。競合0。
- resolver efe497ecを`073ff31036a8c2468ce0b0db6770e16750127764`で通常merge。競合4パスはallowlist末尾のread2関数とresolver1関数、repository-contractの関数ID/派生digest、生成moduleのdigest、root試験末尾の独立群。read/initial側の旧全field/順序/履歴を保持して追加をunionし、SOURCE_DIGESTは現JSONの正規canonical化から再計算した。新しい受理行/識別値を作らない。全field対応試験成功を別途確認する。
- initial95d766f5はread祖先のためAlready up to date。実develop `547d199e0c68f3c7d73b6996056cf10ef5fb09fb`を`22327c4dd8a0b6fc3ba152a1ddfae429e16cf73d`で通常merge、競合0。
- root供給の実547追随read `741bb698ff746a9fde799f2a8ca5653acea7f029`を`6f2d69abe83367ba4cad095d2fdbb65ed133c1c0`で通常merge、競合0。core3は供給bytesのまま、tenant pendingはAPI2だけでactual547全prefix/旧全登録を保持する。新たなcore/拒否ロジック変更は行わない。先の連絡に書いた「9ab...」は未取得の誤記であり、同日直後に実6f2d69abへ訂正連絡済み。

正常mergeに伴う供給JSON/派生値の機械融合と、本単位の新create metadata/正式9/8受理を区別する。新create metadata/fixture/production registry/route/C2追加・正式履歴/snapshot/lock/oracleの独自編集0。現在の候補tokenは通常registry未登録で、POST/optionsはappへ公開していない。

### 実装済みの局所境界

既存schemaへ空白only大会名拒否、無変換保持、options query/cursorと区分・大会Page DTOを追加した。新repositoryに計画どおり6factory/7tokenと候補OperationRegistrationを置く。tenant注入、固定category/status/disabled、ページ上限、UUID/aware日時/余剰入力、強制変更後の単一DTO/codec再検証、teamの固定kindと主キー全束縛を維持する。game INSERTのstarted_at/rule_overrideは利用者入力にせず、既存nullable/no-default列をINSERTから省略してSQL NULLを保存する。

新serviceは実scope exact型だけを受ける。大会名の完全一致既存衝突、既存有効親、self/opponentの既存lookup、UUID順・同ID重複除去の限定team行ロック、正規resolver/単一encode、game INSERT、実RG1前後を同scopeへ接続する。例外をscope内で握り潰さず、戻り値もcommit前候補と明記する。常閉を変えず、現供給で保存成功には到達しない。optionsは正本game-type seedの表示値と、SQLで最大limit+1に制限した大会を返す。codec/計算/auth/実行器コピー・成功stubなし。

### 対象検査と失敗の採否

- 初回backend Ruff format/checkはimports等を是正。初回tyのunion narrowing/行DTO引数、次の試験用type注釈を是正し、最終backend Ruff/tyは成功。
- 初回新局所pytestは63成功/1失敗（4.40秒）。失敗は独自JSONB(none_as_null=True) bind型が既存exact検査に拒否されたこと。検査緩和を行わず、既存nullable/no-defaultのrule_override/started_atをINSERTから省略する既存SQL NULL表現へ是正した。2件のNULL bind前提を列省略/ORM default不在の確認へ置換し、新局所62成功/1.74秒。これを64成功とは記録しない。
- 最終局所回帰: `uv run pytest tests/test_game_preparing_create_boundary.py tests/test_game_preparing_components.py tests/test_game_preparing_read_boundary.py tests/test_api_app.py tests/test_authz_repository_contract.py -q --tb=short` は **229成功/1.65秒/exit0**。未登録7token、tenant/型/列/条件/上限/文種別拒否、real scope＋合成Session(false)での実RG1登録拒否/rollback、下位処理の大会名/親/team拒否、options Page/seed/不正行の非成功、旧read/実API構成/生成全fieldを確認した。下位処理・合成Sessionを実HTTP/保存成功へ数えない。
- root/creation_pathと重いslotを調整し、実DBは新1件だけ実行。commandは `PITCHLOG_PYTEST_TMPDIR=/home/ymdms/.cache/pitchlog/create-step1-pg-6f2d69ab uv run pytest tests/db/test_game_preparing_create_db.py::test_create_service_real_closed_rg1_rolls_back_before_business_sql -q --tb=short`（backend cwd、unified exec session99399）。**1成功/8.26秒/exit0**。既存provisioned_product_catalogを使いmigration0033/製品認可DDL/実appロール/実scope/実RG1常閉を通し、service拒否・DB rollback・業務INSERTなし・当該tenantのgame/語彙0を確認した。HTTP認証/登録/保存成功の実証ではない。共有DB不使用、TLS/署名鍵生成/運用open/成功stubなし。
- DB完走後はfixture所有pitchlog-authz-*コンテナ0、所有pytest tmp削除済みを確認してroot/creation_pathへ通知。実行前後に既存共有pitchlog-db-1だけが残り、不変更。backend/resourcesを閉じて重いslotを解放済み。
- 同じ広いDB/core全件は再走しない。coreは供給側382成功の既結果を保持し、こちらでは実547との本物verify_area_path_baseline/通常merge述語だけを固定点で確認する。root Ruff/ty、docs-status/局所plan-sync、正式checker未受理拒否は最終固定点の結果を後続報告に残す。

### 残りと次段の入力

ステップ1はDTO/SQL/token/serviceと拒否境界の候補まで。実RG1成功供給・新7token/6allowlist/6正例登録・POST/options認可/C2・7.7/履歴/snapshot/lock/oracle・実HTTP保存/両INSERT全取消はステップ3/root所有の未達。現常閉による業務INSERT0を新大会語彙+gameを実保存後に取消した証明へ読み替えない。

ステップ2へ渡せるrequestは既存PreparingGameCreateの全field、new/existing排他、名称無変換/空白only拒否、optionsはgame_typesとtournaments(items,next_cursor)のPage構成、既存roster self/opponent選択、送信中POST1回・旧authEpoch拒否・結果不明自動再送0である。フォームsourceはまだ変更していない。backendの実公開待ちを仮保存成功へ置き換えず、正規client/providerと入力/拒否境界を次の個別指示で実装できる。

固定点前pure検査: root Ruff成功（既存docstringのimplicit string concatenation warning1件）、backend Ruff/ty成功、docs-status21件/違反0。root tyは供給741bb698のtests/test_core_guard.py:4571/4591/4609/4615で4診断。INITIAL_RIGHTS_HISTORICAL_ADDITIONSのdict[str,tuple[str,str]]推論とhelper引数dict[str,tuple[str,...]]の不変性によるもので、本単位のbackend変更ではない。core3はroot所有のため無断修正せず通知し、未達を保持する。本物verify_area_path_baseline(actual547,6f2d69ab)は成功、正常merge073ff310/22327c4d/6f2d69abの_changed_paths_in_commitはいずれも空、旧f48b5944/8037e1d9は祖先でない（各exit1）。通常mergeの述語を迂回していない。
