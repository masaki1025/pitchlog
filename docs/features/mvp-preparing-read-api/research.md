# preparing実GET接続の限定調査と必要delta

2026-10-23、rootの委任で新branch/worktreeの不存在を確認し、#175 `d68e10ed30d77cbe5361ece4cab2a3bd6dac9461` 起点に `feature/mvp-preparing-read-api` を作成した。本回は本feature plan/researchだけを起案し、source・DB・他worktree・正式assetsは変更していない。

## 固定した供給物

| 供給 | 固定内容 |
| --- | --- |
| #175 | `d68e10ed30d77cbe5361ece4cab2a3bd6dac9461`。承認plan step4/design、repositories/games.pyの候補2token/SELECT、schemas/games.pyの作成/一覧入力とJSON表現復元、既存read登録準備資料を継承 |
| codec接合候補 | `6ddbc341`。新規接合はschemas/games.pyの `_decode_preparing_snapshot` とtest_game_preparing_components.pyの2パスだけ。初回供給5パス/旧codecを丸ごと再供給しない。元候補の独立0指摘・既存追加敵対未消費の履歴も保全 |
| 単一codec | supplier #174 `bc436803902a9cde2b54e6a72636acbe522e9e20:backend/src/pitchlog/db/game_state/rule_snapshot.py` |
| codec Git blob / SHA-256 | `cf2c5f55d3c6fd32c031dbaf764025c7a21e6b8d` / `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4` |
| codec通常依存 | jsonschema==4.26.0のみを通常dependenciesへ追加し、必要な解決依存をlockへ同期。--withを製品依存の代用にしない。supplier全lockのコピー/無関係な更新はしない |

`6ddbc341` が記録する元schema SHAは `d8be8b5c640aaf8f80bc002770a53a0036db1c4caf0a34fb63ad6adfb4c3d590`、接合後は `ec43115b461102715de7184c7fed28862fbec187f3099aed3de8dcbf46685527`。再利用は差分のprivate codec接続だけで、新read DTOは本候補の追加となる。元candidateのhashを新候補全体のhashとして扱わない。

## 現状とruntimeの最小接続

起点はPreparingGameRead/GET/routerが未存在。repositories/games.py:152の2件は未登録候補で、app.ROUTERSにもgamesはない。既存roster routerの通常のrun helperとtenant_transaction_scopeをread2件へ使う薄い構成が最小。新service moduleは不要。

runtimeで必要な閉集合は `repositories/operation_registry.py:PRODUCT_OPERATIONS` への候補2件と、`api/tenant_access.py:_MATCH_OPERATIONS` への `preparing_game_list` / `preparing_game_detail`。既存 `read-registration-review.md` のoperation IDを継承し、以前の調査中に仮記載したpreparing_game_readへ改名しない。

C2はTenantMatchedRoute.handleでrequire_presented_token→require_tenant_access→canonical expected/challengeを通し、scope stateを内部だけで引き継ぐ。require_tenant_accessは実 `issue_tenant_context_from_presented_token` / `verify_tenant_id` / authn.verify_tokenを呼ぶ。正式route-registry/matrixのJSONはこのruntime認証関数が読む値ではなく、候補sourceに通常登録することと、正式資産受理は別である。認証関数・C2・registryをmonkeypatch成功値へ置き換える案ではない。

CAP:games:readとgamesのSELECT/RLSは既存。新actor/ユーザー役割/記録権/RG1/管理権限は追加しない。read成功に作成resolverを呼ぶ必要もない。失敗時のsnapshot補完や架空providerを作らず、通常HTTPExceptionを共通handlerへ渡す固定503でsafeな非成功へ閉じる。

## 正式登録前に提出する限定delta（今回は未適用）

既存#175 `read-registration-candidate.json` / `read-registration-review.md` の具体案を正とし、範囲をcontracts全体へ拡大しない。

| ファイル/field | 最小候補と留保 |
| --- | --- |
| `contracts/tenant_boundary/repository-contract.json:product_operation_token_types` | 末尾へ `pitchlog.repositories.games.PreparingGameListToken` / `PreparingGameDetailToken` の2型だけ。product_capability_ids・戻り型・function集合は不変 |
| `backend/src/pitchlog/repositories/repository_contract.py:PRODUCT_OPERATION_TOKEN_TYPES` | 上記2型と対応する生成source digest。今回は未変更。実PRODUCT_OPERATIONSの2登録と正式受理時にexact集合を一致させる |
| `contracts/tenant_boundary/base-allowlist.json:allowed_symbols` | `_preparing_game_list_statement(cursor_position: tuple[datetime, UUID] | None=None) -> Select[Any]` と `_preparing_game_detail_statement() -> Select[Any]` の完全修飾2関数へSQLA_SELECTだけ。module全体・text/updateは許可しない |
| positive fixture 2パス | 正式反映時は `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games.py` と `.../games/__init__.py`。同一module解決とfixture一意性を両立する既存案を保持。今回は配置しない |
| `contracts/authz/route-registry.json:routes[]` | `ROUTE:RECORD:games:read`、record_and_aggregate/design/readの1行。provenance/ownerは正式基線後に確定 |
| `contracts/authz/http-route-matrix.json:routes[]` | 同routeへ `HTTP:ROUTE:RECORD:games:read` / conditional / test_ownerの1行。現構造は2GETのmethod/pathを保持しないため、HTTP実試験で各operationとの対応を別に固定 |
| `contracts/authz/route-registry.lock.json` / `http-route-matrix.lock.json` | asset_digest・entries/entry_count・aggregate_decision_digestの派生候補。今回は読み取り調査のみで算出/反映しない |
| `contracts/authz/oracle-seal.lock.json` | 正式入力/派生lockの整合が必要な将来ゲート対象として名前だけを保持。sealed期待値/P6資料は読まず、今回反映/受理しない |
| tenant-boundary履歴/基線 | 上記正式反映時のbase/repositoryのrevision/source_digest/baseline_control.history、必要な `contracts/tenant_boundary/history-snapshots/` とcensus-baselineのmaterialized_tree/implementation_field_inventory。正式履歴を保った後に派生させる。新しい履歴値・受理記録・anchorを本候補で予約/改訂しない |

`contracts/tenant_boundary/db-api-inventory.json` はSQLA_SELECTが既登録で、今回新しいengine/Session APIやreceiver factoryを作らないため、現時点で変更不要。`tenant-context-allowlist.json` は新しい発行経路を作らないため変更不要。authz capability catalog/table分類/DB ACL/RLS/DDLも変更不要の見込み。別の必要fieldが実検査で見つかったら、無断で範囲を足さず具体差分をrootへ返す。

現在の正式assetを無変更で使うcheckerは、2token閉集合不一致と2SELECTのTB005を拒否する見込み。これを実行不能と混同して全権限stubで迂回せず、通常runtimeの実HTTP/DB接続と正式checker未達を別々に記録する。正式値の算出・7.7完全前後値/受理は#174→#173の実履歴後の直列受理で行う。

## 既存試験・実authの資格

既存test_api_appはroute/operation IDのexact集合、test_roster_self_team_readはC2 exact集合を保持する。2GETを追加するsource変更に合わせて、それぞれ旧要素を残して2件を追記する必要がある。test_game_preparing_read_boundaryの候補未登録期待も正規2登録＋偽造/派生拒否へ更新する。新test path/core登録を増やさず、既存coreの `backend/src/pitchlog/api/*` / `repositories/*` と既存試験範囲で扱う。

DB HTTP検証は既存test_api_auth_exit_entry.pyのisolated catalog/settings/identity準備を利用できる。ただし既存 `_login` は直接DB呼出しなので今回はHTTP loginの代用にしない。`POST /auth/login` が発行するCookieを同じHTTPS clientで受け、実tenant_accessからGETを通す。DB資格は既存隔離fixtureだけ、署名素材は既存repoの非秘密固定試験fixtureを再利用し、運用/本人署名鍵を発行せず既存秘密を読まない。authのfactoryを実app engineへ接続できるが、認証関数/Session/認可成功値は代用しない。

ゲーム行のSQL seedは一覧/詳細readの環境準備。作成API・規則出所・RG1/game INSERT全取消を成立させたものではない。候補UI/providerは作らず、GETの成否を共有アカウント/単一記録端末の意味変更へ広げない。

## 未消費ゲート

親plan末尾の正式read追加敵対1回は、#174→#173実統合後の実基線・接続候補HEAD/diff固定が実行条件。本起案・隔離component/API接続の独立照合に流用しない。親の基本枠/追加許可・6.1計画レビュー・コードレビュー系列を分け、既存回数をリセットしない。現在は起案のみで、独立計画レビュー/本候補実装/正式7.7/正式step4全体は未成立。

## 承認後の隔離実装と実HTTP/DB検証（2026-10-24）

rootのPO委任承認 `9e2ac0a3fcadb9e75854866aebb553cbc2228087` により計画表1ステップを実装した。上段の起案時点の履歴は保持する。通常PRODUCT_OPERATIONSへ2token、通常app.ROUTERSへGET2、C2 runtime閉集合へ既存案の2 IDを接続した。既存SELECT/token本体は変更していない。新routerのwith内で保存codec/DTO/Pageを検証し、例外がscopeを終了させた後だけ固定503へ写す。新service、成功固定の認可/Port/provider、現在規則への再解決は作らなかった。

6ddbc341の新接合2パス差分だけを再利用し、単一codecはsupplier bc436803とbyte一致で供給した。JSON整数型是正を維持し、業務検証をDTO/サービスへ複製していない。依存はjsonschema==4.26.0と必要な5追加packageだけ。既存packageはbackend自身の依存宣言以外の差分0で、uvが付随生成した無関係metadataは元の正確な値へ戻した。frontendは `pnpm install --frozen-lockfile` のsetupだけで、宣言/lock・artifact検査は変更していない。

署名素材は既存roster fixtureの非秘密固定設定式だけを、指定2fixtureへ適用した。認可stub helperを呼んでおらず、当該fixture内に鍵生成呼出しがないことをASTで確認した。運用鍵/本人署名の発行や既存.env/秘密へのアクセスはない。鍵設定置換の初回補助scriptは局所変数を式と誤認してassertで停止したため、ASTの設定対象だけを特定して修正した。失敗を成功へ数えていない。

### 対象検査と失敗履歴

| 版/対象 | 結果 |
| --- | --- |
| 初回単体対象 | 126成功・1失敗。旧componentの『2候補が未登録』期待が、今回許可した正規登録と不一致。親step3の当時の期待を保持した履歴として記録し、当該試験だけを候補通常登録/tenant注入へ更新。偽造/派生token拒否は維持 |
| 静的修正途中 | 初回Ruff/tyはimport整列・追加SQL文字列長・不足Any import等で非成功。対象scope内の記述だけを整理し解消。検査規則/正式assetsを変更していない |
| 最終単体対象 | `uv run pytest tests/test_game_preparing_components.py tests/test_game_preparing_read_boundary.py tests/test_api_app.py tests/test_roster_self_team_read.py -q`: **127 passed / 1.16s / exit0** |
| 実DB対象 | `tests/db/test_api_auth_exit_entry.py`: **11 passed / 46.89s / exit0**（既存6＋新5、skipなし）。実測 **PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)** |
| 最終静的 | backend対象format・全backend Ruff/ty、root Ruff/ty、空白検査成功。root Ruffの既存test_core_guard docstring警告1件は終了0。計画同期は本単位base 9e2ac0a3で成功 |

DB新5件はHTTP POST /auth/loginの実password照合・token発行・署名Cookieを、同じHTTPS clientのGETへ通した。engine factoryだけが実製品app engineを返し、署名/認可/tenant_access/Session/scope/DB応答の代用はない。正規readと同時刻cursor複数page、現在規則変更の非遡及、Cookie欠如/改ざん/失効・無効password、C2不正のgames SQL前拒否、別tenant/不存在/不可視/他状態の共通404、旧/5-key/破損snapshotとDTO不正のwith内rollback後503、実games SELECT取消の固定503/秘匿/再試行0、全readのno-store/成功限定ACKを実測した。

ゲーム/チーム/大会/保存snapshotはadmin SQL seedによるread準備で、正規作成・出所・RG1/game INSERT全取消の証明ではない。既存identity autouseを維持するため、管理/被検査DSNも外側の専用disposable clusterから明示供給した。新5件のDBは各自独立、outer1とinner1の最大同時2個、動的loopback portと専用一時領域で分離した。engine/connection/containerのfinally cleanup後、disposable authzコンテナ0・本実行一時ディレクトリ0を確認。資格/署名素材の値は記録していない。

### 固定供給hashと提供境界

| 対象 | SHA-256 |
| --- | --- |
| 新games router | `7f8663a3f2d3a87abbe86b19cf15d85d4e3fce27530d7b67a4bd5a7a98cda121` |
| games schema/codec接合/Read DTO | `05e93029c9a2abd3ddd014d8806accad17fe83e38798daa2f8c49cac6c03483e` |
| 単一codec | `d646c0bbc73b7ff2507aa440e81effdd1e37debb4d5d767971608110853cdfc4` |
| 実DB HTTP試験 | `1a91bfca6cff17e2cfb2d9fba5adb2376ff594113212355a379e18e796517aac` |
| backend pyproject / lock | `e2048e9d69dd1fb9f494fa21cd7d06d385910a252d964bcc082c35b43651788c` / `fd4e71455bd7c8d45d2a335803cdf6023de56994b9c2bdc5a4933af5e5ce40ad` |

実HTTPの候補接続成功は正式登録/7.7の代用ではない。固定source commit後の `python scripts/check_tenant_boundary_bypass.py --base-ref 9e2ac0a3` はexit0。これは既存games SQL builderを含まない本単位差分だけの結果である。default比較の `python scripts/check_tenant_boundary_bypass.py` はexit1で、既存 `pitchlog/repositories/games.py:88` と `:114` のSQLA_SELECTをTB005として2件拒否した。正式2SELECT許可、2tokenのgenerated契約、route/matrix/7.7は未受理のままで、局所checker成功を全基線の正式通過へ流用しない。

共有正式assets/生成契約/fixture/lock/sealは差分0。#174→#173→#175の実基線、正式read追加敵対1回、UI/provider、作成/RG1、公開・push/PRは未達/未消費のまま、次は固定候補の独立コードレビューとする。source/testの対象全体は14ファイル（source6、依存2、既存試験5、本research1）。製品コード確定後の最終反映は本記録の検査結果だけで、sourceと試験は上記最終検査から変更していない。

独立計画第1回/root/csv_reviewは指定SHAを実読して可決P0=0/P1=0/P2=0。rootは運用秘密/署名鍵の新規発行を避けるため、既存固定試験素材の設定式だけを再利用する限定を追補しPO委任承認。_client_appの認可stubは再利用せず実HTTP login/Cookie/署名検証/tenant_access/DBを通す。対象版/日時はplanへ固定。実装未着手、正式登録/7.7/親追加1回/UI未達は保持。

## 独立最終コードレビューの限定受領

2026-10-24 JST、候補作者creation_path/rootに対し、非作者 `/root/o5_final_review` が独立レビューを実施。対象base `9e2ac0a3fcadb9e75854866aebb553cbc2228087`、HEAD `b3a8ef8bb7f1200c423fc32ec803300a0f1724ee`、`git diff --binary --full-index` SHA256 `d146e8f7dbad94804519056c74554650fb8a06fac05482782caf3a5928c16435`、14ファイル。結果 **可決 P0=0/P1=0/P2=0**。認証/C2先行、通常registry2件、scope内codec/DTO/Page、rollback後503、keyset、越境404、単一codec供給・正式assets差分0を確認した。

独立再実行は単体127成功/1.48秒、実HTTP/DB11成功/46.40秒（PG17.11、skip0）。専用一時資格・動的port・一時領域を使用し、cleanup後コンテナ0・worktree clean。局所checkerexit0、defaultは既知TB0052件/exit1を保持。認可stub成功・運用署名鍵新規発行・共有DB接続はしていない。

Codex主担当/rootはPO委任4/5/6/8/10に基づき、この隔離read API候補と検証結果を限定受領する。承認日時は本記録コミット時刻、対象版は上記HEAD/diff。正式7.7/認可閉集合/親#175追加敵対1回/UI/provider/作成保存の未達は解除しない。山田正輝の個別実値確認や署名を代記しない。本受領追記自体は独立未再レビューの記録差分で、製品source/試験/正式資産を変更しない。
