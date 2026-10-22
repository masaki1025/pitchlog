# UG1 ステップ4 read 登録の準備資料（未受理）

対象は PR #175 の公開済み `36e7129d`、比較元 `760c04d5`。この資料と隣の JSON Patch は候補であり、正式な契約・製品登録・HTTP 公開・snapshot 反映・7.7 受理を行っていない。#174 → #173 の共有ファイル確定と正式 codec の提供後に、実 develop から再導出する。

## tenant-boundary の最小許可候補

`read-registration-candidate.json` は `contracts/tenant_boundary/base-allowlist.json` の `allowed_symbols` 末尾にだけ追加する RFC 6902 形式の2操作。`760c04d5` の実ファイル SHA-256 は `0aeff342a6d27c8b065e75f280a0259319296ccec17d2b6b86d5a3ebd07096a5`。現作業木の同ファイルは base とバイト一致し、既存21 symbol、既存の履歴・他フィールドはパッチで変更しない。2件追加のみを既存の2空白インデント JSON として直列化した候補ファイル SHA-256 は `1d0a5e5a19767c5fec5b4a88636d7e8c5fb585b44e548546979a25715622e364`、symbol は23件となる。この digest は**受理後の最終値ではない**。

許可するのは `pitchlog.repositories.games._preparing_game_list_statement(cursor_position: tuple[datetime, UUID] | None=None) -> Select[Any]` と `pitchlog.repositories.games._preparing_game_detail_statement() -> Select[Any]` の各 `SQLA_SELECT` だけ。関数単位の正確な署名は既存 checker の `_function_signature` による AST 正規化値。任意の `select`、`text`、`update`、module 全体を許可しない。候補 fixture パス2件は将来の正例用で、現時点では存在しない。正式反映時は正例 fixture の exact-set、凍結 revision・履歴・snapshot を一緒に整合させる必要がある。今回のパッチだけを実 allowlist へ適用しても `load_contract` の fixture exact-set に合格しない。

既存 checker `scripts/check_tenant_boundary_bypass.py` の `load_contract(Path.cwd())` で現契約を読み、`dataclasses.replace(contract, allowed_symbols=(*contract.allowed_symbols, *two_symbols))` のメモリ候補を `scan_source` に渡した。実 `backend/src/pitchlog/repositories/games.py` は現契約で `TB005` 2件（行88・114）、候補で0件。同ファイルの別関数 `select`、既許可 `_tenant_profile_statement` 内の `text` と `update`、別 module の同名関数 `select` はそれぞれ `TB005` 1件で拒否した。候補関数の引数型を変えた変異は署名不一致と `select` の2件の `TB005` で拒否した。実 checker の `_current_allowed_symbol` は完全修飾 symbol と AST 署名の一致を見ており、`_visit_function` も署名不一致を `TB005` にする。ただしこれは静的呼出し境界の確認であり、SQL の tenant 条件や実 fixture・凍結履歴の成立を証明しない。

## repository と HTTP の未登録案

| 入口候補 | 固定 token 内容・検査 | 登録候補 |
| --- | --- | --- |
| 一覧 | `PreparingGameListToken(limit=20, cursor=None)`。`limit` は exact int の1〜100、cursor は aware `scheduled_at` と UUID の opaque keyset。token に tenant ID はない。 | `PREPARING_GAME_READ_OPERATIONS[0]` を `PRODUCT_OPERATIONS` へ追加。`CAP:games:read`、status `preparing` 固定、一覧 `LIMIT limit+1` 最大101、`scheduled_at DESC,id DESC`。 |
| 詳細 | `PreparingGameDetailToken(game_id: UUID)`。exact UUID、tenant ID なし。 | `PREPARING_GAME_READ_OPERATIONS[1]` を同じ registry へ追加。`CAP:games:read`、status `preparing`、`LIMIT 1`。 |

実体は `backend/src/pitchlog/repositories/games.py` の候補のみ。正式登録時は `contracts/tenant_boundary/repository-contract.json` の `product_operation_token_types` に完全修飾型名2件を順に追加し、`backend/src/pitchlog/repositories/repository_contract.py` の生成値・source digest と実 `backend/src/pitchlog/repositories/operation_registry.py` の `PRODUCT_OPERATIONS` を同じ受理単位で整合させる。現45 token から47 token となる候補だが、exact な型集合・順序・署名・capability の照合が契約であり、件数のみでは不可。新 capability、raw SQL、Session、別 scope は追加しない。

両 SQL は正本 `Game` ORM 表を使い、実行器が context tenant ID を `:tenant_id` に束縛する。`status=:status` の値は `preparing` のみ、`trashed_at` と `hidden_at` は NULL、一表だけ。cursor は同時刻に `id` で分岐する。`_TenantScopedOperation` が tenant 条件を確認し、`_validate_prepared_statement` が正本表・固定 status・LIMIT 上限などを確認する。後者**単独**は tenant 条件欠落を拒否しないため、登録時と実行時の既存連続検査を分離して扱う。可視性2条件は現 builder の SQL 形と固有試験で確認するが、validator の独立した可視性不変条件とは主張しない。正式登録時は builder 差分と実 DB の不可視行拒否も検証する。現実行器の `_operation_spec` は候補 token、偽 token、継承 token を未登録として拒否する。

HTTP 候補は `GET /games`（`operation_id="preparing_game_list"`）と `GET /games/{game_id}`（`operation_id="preparing_game_detail"`）の2入口。`backend/src/pitchlog/api/routers/games.py` を新設する場合も `backend/src/pitchlog/api/app.py` に接続する前に、`backend/src/pitchlog/api/tenant_access.py` の `TenantMatchedRoute` と `_MATCH_OPERATIONS` にこの2 ID を明示し、既存 C2 の `X-Pitchlog-Expected-Tenant` / challenge / 成功 ACK / `no-store` を維持する。query/path の解析・応答 SQL に先立ち認証と tenant 照合を行う。`frontend/src/api/games.ts` は正規 `frontend/src/api/client.ts` の `tenantBound: true` を用いる候補。POST、OPTIONS、開始・記録操作はこの受理案に含めない。

認可資産の現構造では `contracts/authz/route-registry.json` の `routes[]` に `route_kind: "record_and_aggregate"`、`origin: "design"`、`operation: "read"` を持つ `ROUTE:RECORD:games:read` を候補とする。同じ route ID に対し `contracts/authz/http-route-matrix.json` の `routes[]` に `matrix_route_id: "HTTP:ROUTE:RECORD:games:read"`、`disposition: "conditional"`、担当 `test_owner` を対応させ、2つの method/path/operation ID の対応を入口別検証に固定する。route ID は HTTP method/path を直接保持しない現構造なので、2 GET の存在は matrix 行だけで証明しない。`contracts/authz/route-registry.lock.json`、`contracts/authz/http-route-matrix.lock.json`、`contracts/authz/oracle-seal.lock.json` および入力 manifest / claim 射影は**未変更**。正式値は #174 → #173 後の最新入力と契約検査で再計算し、所有側 test_owner と provenance を確定する。

## read 成立条件と所有

read は、正式 codec による保存済み `applied_rules` の構造検証と、正規保存経路が担う出所・相関証明を別責任として確認し、正式7.7受理、認可・C2 tenant 照合を満たせば独立に開始でき、作成前の resolver や RG1 成功は read の開始条件にしない。旧 `{}` / 5-key や6-keyの形だけを有効 snapshot に昇格させない。正式 codec は現 develop に未提供であり、この枝に複製しない。正規保存済み fixture の read 成功は作成 API の resolver→RG1→commit 成功や実画面からの作成成功を証明しない。

U-F8回答 [6338616580](https://github.com/masaki1025/pitchlog/pull/171#issuecomment-6338616580)を実取得して照合した。preparing限定のGameScreenEntry/EntryRecord/EntryTypes・各spec、新api/games.ts・薄いProvider・必須大会フォームは**Dへの限定編集分担を受理**。U-F8は同じ製品UIを並行編集しない。DがAPI→表示用EntrySupply変換・取得・tenant/authEpoch/path/requestKey照合と失効破棄を担う。これはU-F8全体やresolver/RG1の所有移管ではない。

要修正点も採用：PreparingGameCreate/PreparingGameReadとEntrySupply/RecordDetail/EntryEnvironmentを分離し、GETだけでrecordingRight=held/premises=met/queuedCount=0を作らない。未提供のlineup/draftRestorationを架空pendingで埋めてRecordDetail全体をready化しない。preparing専用表示型を分けるか既存RecordDetailを未供給のまま保つ。開始/再開/記録権・未接続POST成功の封鎖を維持する。正式read応答型/codecはまだ実提供されていない。

## 7.7 の現在値と未確定値

現ファイルを機械読取した SHA-256（**受理の直前/直後値ではない**）:

| 資産 | 現ファイル SHA-256 | 再導出を阻む条件 |
| --- | --- | --- |
| `contracts/tenant_boundary/base-allowlist.json` | `0aeff342a6d27c8b065e75f280a0259319296ccec17d2b6b86d5a3ebd07096a5` | 上記2 symbol と fixture、履歴・revision の正式受理 |
| `contracts/tenant_boundary/repository-contract.json` | `43123d6b9c879b0b0b14ab6ee285ed82638c4a4dd47d667bdba87514ba3f62f9` | token exact-set と生成 Python、7.7 履歴 |
| `contracts/authz/route-registry.json` | `7157896098cd99001876fecaa3e46367f6f3940031e6b676d87aedb62c5d41d6` | #174 → #173 の入力・owner/provenance |
| `contracts/authz/http-route-matrix.json` | `80bc1fb43cf7d2dcfb26fc3b64c7b6f39ec30e64032553c8d26c18bc068a31db` | 同上と2 GET の入口検証 |
| `contracts/authz/route-registry.lock.json` | `7a2f0679ce2d952c59a8fa7468d31b4b8a85ab7f709a0854a22291e260f24698` | route registry の正式入力確定 |
| `contracts/authz/http-route-matrix.lock.json` | `baa8185ac6103527a3d03388986c5e8745f2bb4164f43aa5955aeaa4846e8cb4` | matrix の正式入力確定 |
| `contracts/authz/oracle-seal.lock.json` | `5d135d72e20fb1311bafe7698af1cf1b0ac3516367fcde6142fda5d4e9895480` | 全入力・派生 lock の確定 |

完全な7.7最終値は #174 → #173 統合後の実 develop、正式 codec、共有資産の担当側確定を待つ。契約/認可所有側が基線を再導出し、UG1 は今回の2 symbol・2 token・2 GET と実試験を提出する。受理直前/直後の完全射影、snapshot、authz lock/seal、履歴追記はその時点の単一受理案として作る。既受理履歴を遡及編集せず、承認者・承認日も未記入。PR #175 を単一レビュー受理の**案**とし、現時点は未受理・正式反映前の候補に留める。

## 追加負例の再現確認

候補2関数自体をtext/updateへ変異させる静的負例も既存checkerで実行した。実ソースは現契約TB005=2/メモリ候補=0、同ファイル別関数=1、今回の2関数内text=2/update=2、別モジュール同名関数=2で全件拒否。checker・実allowlistは変更0。候補資料の正例fixtureは未配置であり、これは正式load_contract/全体検査通過とは異なる。最初の検証用sourceでfuture import位置を誤りSyntaxErrorになった実行は失敗として保持し、import位置だけ修正して再実行した。

## 公開型・登録差分の正確な対象

共有正式ファイルには未適用のRFC 6902候補：

```json
[
  {"op":"add","path":"/product_operation_token_types/-","value":"pitchlog.repositories.games.PreparingGameListToken"},
  {"op":"add","path":"/product_operation_token_types/-","value":"pitchlog.repositories.games.PreparingGameDetailToken"}
]
```

適用先はrepository-contract.json、生成側の対象はrepository_contract.pyの`PRODUCT_OPERATION_TOKEN_TYPES`。`PRODUCT_CAPABILITY_IDS`は不変、戻り型は既存TenantOperationResultのまま。実operation_registry.pyはPREPARING_GAME_READ_OPERATIONSだけを追加し、固定function登録・他table/別操作・POSTは増やさない。旧45型を並べ替え/除外せず、追加2型と実registryを完全修飾名のexact集合で照合する。revision/source_digestは先行実統合後の基線から再導出するため現在の22から23を確定値として予約しない。

## レビュー対象と残ゲート

本資料は正式な7.7受理依頼の完成版ではない。既存コードの反対側一次の対象は固定36e7129dで、この資料/新境界試験はその査読対象外。資料初版時は製品敵対基本枠は未消費だった。反対側（Claude一次）と敵対（codex_run）は別系列で数え、計画査読とも区別する。9807c22cの敵対基本第1回はP0/P1/P2=0、同HEADの反対側差分第2回はP0/P1=0・P2=5だった。7.7完全前後値・snapshot・記録案は共有パスの先行統合後に固定する。不足枠が生じた場合は既存回数を保持して対象差分だけをPOへ提示し、既受理事項の全面再審査へ戻さない。

### 反対側第2回後の候補是正

正例候補のパスをgames.pyとgames/__init__.pyへ修正した。両者は同じpitchlog.repositories.gamesへ解決され、fixtureパスの一意性と元の完全修飾symbol照合を両立する。実fixture配置はまだ行わず、正式登録時のexact-set/全拒否変異の検査条件を維持する。候補ファイルdigestだけが上記の値へ変わり、正式7.7値・snapshot・履歴は変更0。前候補digestは受理済み値ではない。

route接合時はextra forbidのQuery modelへ共通clientが想定外queryを付けないことも検証する。これを理由にextra拒否を緩めない。

### 7.7記録案に固定できる項目と未確定欄

- 単一受理単位案：`masaki1025/pitchlog#175`。承認者・承認日：未記入。
- 対象：SQL構築2関数のSQLA_SELECT限定許可、repository公開2tokenと実registry、2 GET認可連動、必要な派生契約・fixture・snapshot・seal。新capabilityやPOST/作成/開始は含めない。
- 前状態：本資料の760c04d5機械照合値は準備基線のみ。正式な直前状態は#174→#173実統合後のdevelopと保持すべき受理済み履歴から再取得する。
- 後状態・revision・凍結射影・snapshot・8入力/派生seal・record digest：共有パスの正式引渡し後に一括生成する未確定欄。現在の生ファイルSHAやメモリscanをその代用にしない。
- 正式履歴への反映は完全値固定→レビュー/7.7受理後のみ。現在は記録本文の準備であり、正式受理を求められる完成した記録案ではない。

修正後の正例パス2本は専用一時ディレクトリへ最小fixtureを置き、既存scan_directoryで通常違反0、reject_all_db_calls=TrueでTB900を2件検出した。正確symbol/署名・許可APIの対応と全拒否変異の効力を確認したもので、実fixtureを共有正例集合へ登録した証拠ではない。

## 2026-10-22追加許可とread専用供給の具体化

追加敵対1回はPO許可済み・**未消費**。実行条件は#174→#173実統合後の実基線・正式read接続候補・差分SHAの固定であり、現在の資料/仮定した提供物で前倒し実行しない。先行2回と採否は保持する。

| readに必要な供給 | 確認できた候補名・責任 | 提供元/状態 |
| --- | --- | --- |
| 保存JSONBのstrict decoder | `pitchlog.db.game_state.rule_snapshot.decode_applied_rules(value: object) -> DomainValidatedRuleSnapshot`。内部は`decode_structure -> StructuralRuleSnapshot`、`validate_correlations -> DomainValidatedRuleSnapshot`。旧{}・5-key/余剰・不正UUID/値域/相関/未裁定コールド条件を拒否する。構造型だけを成功readへ昇格させない | TSK-550本体/#174担当。ローカル候補426d0ec84249d5940e7e2de5660a213d45401d0e内の実ソースをread-only確認。正式公開/実統合提供SHAは未成立 |
| 保存値の応答投影 | 同module `encode_applied_rules(value: DomainValidatedRuleSnapshot) -> dict[str, object]` を再利用する接合候補。再解決せず保存値と同じ6-keyを返す。規則計算やcodecを複製しない | 同担当/同候補。正式import契約は受領時に再照合 |
| 失敗境界 | `RuleSnapshotInvalid`（`RuleSnapshotFailure.SHAPE/VALUE/CORRELATION/UNRESOLVED`）、`RuleSnapshotContractUnavailable`。不正/読取不能を成功DTOへしない。DB原本/内部メッセージを外部へ出さない | 同担当。現時点の具体HTTPエラー契約を新たに確定したものではない |
| 規則行出所 | codecは規則行の出所を証明しない。作成側が検証済みresolverと同一scopeで確定保存し、readはtenant/可視性と保存済み値のstrict検証を行う。6-keyの形だけを出所証明にしない | TSK-550が保存前resolver、Dが保存・再取得。正規fixtureでのread検証と作成成功証拠は別 |

候補moduleのGit blobは`e30256c33d2ff2fc7a660715d7d7da3b787e153e`、SHA-256は`e587a8f1e01d4d28a39f5f943b2d811b388282f782063e25fe20203a8c6c6e23`。候補に対する識別値であり、#175の基線/供給済み認定ではない。実develop760c04d5に当該moduleがないことをGitで確認済み。他担当枝を取り込まず、モジュールもコピーしていない。

**readには不要な供給**：`public.resolve_stage_a_rule(uuid,text,text,boolean)`、公開resolver request/result、固定function operation、RG1書込成功許可。これらは新規作成時の規則解決/保存全取消に必要で、一覧/詳細readを止める同一条件へ束ねない。旧snapshotを現在のresolverで再計算して補完しない。

### 実行結果とcodec入力の接合

既存`TenantOperationResult.rows`のJSONBは`repositories.base._materialize_rows`によりdict/listからMappingProxyType/tupleへ不変化される。候補codecの`decode_structure`はexact dictとJSON listを要求するため、そのままでは読めない。D側でJSONコンテナだけを新dict/listへ戻し、正式codecへ一度渡す。未受領decoderの代用品を注入した成功試験は作らない。変換では旧{}・5-keyを補完せず、型/値も矯正せず、構造/相関/出所が検証済みという型やフラグを返さない。UUID/date/bytes等の非JSON値を文字列化して有効snapshotへ化けさせない。

正式codec提供後の確認は、実行器が返す不変行→JSON復元→正式decode→正式encode→応答DTOの全経路、旧/破損snapshotの拒否、同tenant/別tenant/未認証、不可視/別状態、page/cursor、古い認証世代の応答拒否とする。保存済みsnapshotの再取得は現在の規則を再解決しない。

## 2026-10-23 受取物と着手条件の照合

共有資産の反映順はPO指示どおり **#174 → #173 → #175**。#174公開HEAD `e30edc79a7f90aa27cb14303910676e414c2cab6` と#173公開HEAD `dac2ff15cd35b63a7c9f5bc69cd6a87f15e2ed5f` はともにOPEN・mergeCommit=null。最新実developは`1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`（#159統合）で、前回760c04d5以降のAPI/repository/今回対象共有資産差分はなく、正式codecも未収録。今はfetchによる確認だけとし、未統合候補を基線として使わない。

| 受取物/作業 | 担当・確認できた内容 | 不足/解除条件 | readの停止条件か |
| --- | --- | --- | --- |
| 保存値codecの正式供給 | TSK-550/#174。公開e30edc79内の`db/game_state/rule_snapshot.py`をGitHub contentsで照合し、blob e30256c33d2ff2fc7a660715d7d7da3b787e153e・11227 bytesが前回候補と同一と確認。decode_applied_rules/DomainValidatedRuleSnapshot/encode_applied_rulesと例外の候補名は既述のとおり | **公開済み、未統合**。#174の実統合SHAを含むdevelopから同一module/公開型/実行依存を再照合する。未公開だから待つという旧分類を現時点へ流用しない | 正式readのsnapshot検証に必要。新規作成resolverの完成待ちとは別 |
| #174の共有正式履歴 | #174担当。製品・7.7履歴を含む候補が公開済み。最新受渡コメント6348761806/6349413559 | 実統合SHA・最終共有内容が未成立。未マージHEADの履歴位置を予約しない | 後続#173の正式再導出に必要 |
| #173の共有資産引渡し | U-R1/#173。#174実統合後の再導出方針は受領済み、同じ順序を再照会しない | #174後の実基線からのbase/repository契約・派生Python・snapshot・corpus・受理履歴を含む実統合SHA/最終内容が未提供 | #175の最終登録/7.7基線の条件。RG1の業務成功許可をread条件へ追加しない |
| read登録・HTTP/認可接合と試験 | D/#175。SELECT限定2関数、公開2token、2 GET、既存CAP:games:read、JSON復元の準備済み | 上記実引渡し後、Dが実基線から登録/認可/TB005解消・旧snapshot拒否の候補を実装/固定する。これはDの残作業であり、他担当の未提供物と混同しない | 正式readに必要 |
| 7.7完全値・単一記録案 | D/#175。既受理履歴を保持して導出する | #174→#173後の実基線と最終接続候補から前後射影/外部入力/snapshot/派生値/単一記録案を固定。旧プレビューSHAを正式値へ転用しない | 正式受理前の反映は禁止 |
| 許可済み追加敵対1回 | Dが既定ラッパーで依頼。基本2回の結果は保持、追加は未消費 | 実基線SHA・接続候補HEAD・最終差分SHA固定後のみ実行。JSON復元2ファイルも含め、結果と7.7資料を一括提示する | 条件成立前に実行しない |
| 新規作成resolver・安全RG1成功 | TSK-550の公開resolver/固定function operation、U-R1のRG1。作成保存の外部条件 | resolverの公開request/result・登録operation、安全なRG1書込成功の実提供 | **readには不要**。POST作成・開始・初期権・1球の完成を#175の提出結果へ含めない |

JSON復元の後発差分は審査済み305d61ddから公開6bed7cf2の製品2ファイルに限定して識別し、`git diff --binary --full-index 305d61dd085cc0dd421b397140f07ef26e0bbf72..6bed7cf2f8ffd5c1fe95fd9e14b19a8d8a1ffa82 -- backend/src/pitchlog/api/schemas/games.py backend/tests/test_game_preparing_components.py` のSHA-256は`c5ec699c3ffa7e391955e1158fe505b9e87b5ecbdadbdaa69c5ba8c7a1cca70a`。**未再レビュー**であり、これは将来の正式read接続全体の最終差分SHAではない。
