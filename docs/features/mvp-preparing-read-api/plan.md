---
feature: mvp-preparing-read-api
status: active
承認: 済（PO委任によるCodex判断・隔離read API候補）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-preparing-read-api
created: 2026-10-23
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# preparing一覧・詳細GETの隔離接続候補

## 1. 背景・目的

#175承認計画 `d68e10ed30d77cbe5361ece4cab2a3bd6dac9461:docs/features/ug1-preparing-connection/plan.md` step4のうち、実HTTP readの接続準備を1単位で検証する。FR-001/013/014、NFR-005/014/018/019/023と既存C2 tenant照合を適用する。shared account・単一記録端末MVP、既存の役割/記録権の意味を変更しない。

本候補は#175固定HEAD起点の隔離worktreeで、正式#174→#173→#175の実統合・7.7反映前に候補sourceを接続して検証する追加実行単位。親6ステップ/承認/基本レビューの履歴を維持し、正式step4完了や公開を宣言しない。今回rootの委任は本plan/research起案だけで製品未着手。独立計画レビュー後のrootのPO委任判断を実装開始条件とする。

## 2. スコープ

| 種別 | 今回の将来実装範囲 |
| --- | --- |
| 新規source | `backend/src/pitchlog/api/routers/games.py`。GET2件と薄いrow→DTO/ページ変換を同所に置き、新services層を増やさない |
| 既存source | `api/schemas/games.py`、`api/app.py`、`api/tenant_access.py`、`repositories/operation_registry.py`（いずれもbackend/src/pitchlog配下）。既存 `repositories/games.py` のSQL/token2件を再利用し、その業務条件は変えない |
| 単一codec依存 | `backend/src/pitchlog/db/game_state/rule_snapshot.py` をsupplier `bc436803` の是正済みbyteへ固定供給。必要な `jsonschema==4.26.0` 1pinとその依存だけを `backend/pyproject.toml` / `backend/uv.lock` へ通常依存として同期 |
| 対象既存試験 | `backend/tests/test_game_preparing_components.py`、`test_game_preparing_read_boundary.py`、`test_api_app.py`、`test_roster_self_team_read.py` と `backend/tests/db/test_api_auth_exit_entry.py`。新test path/共通conftestは追加しない |
| 記録 | 本featureのresearch。正式登録用の必要deltaは同記録へ分離し、共有正式assetsを編集しない |

`6ddbc341` の新規codec接合差分は `api/schemas/games.py` のprivate関数と `test_game_preparing_components.py` の2パスだけを再利用する。同コミットが含む供給5パス全体をcherry-pickしない。旧codec/凍結基線を持ち込まない。固定元とhashは [research.md](research.md)。

UI/provider、作成POST/大会選択、resolver、RG1、RecordingRightsPort、開始/1球/同期、正式lock/seal/7.7/正本改訂は対象外。readはRG1/記録権/作成resolverの成功を条件にしない。これらを常時成功Portで補わない。実画面/reload・製品経路での保存をread SQL seedの成功から主張しない。

## 3. 影響する正本・正式資産

正本の反映なし。requirements/design/ADR/development/ops、既存#175 plan/review/正式追加枠の記録を変更しない。正式登録候補の限定対象はresearchの表に列挙する。今回は正式JSON/Python生成値、positive fixture、authz lock/seal、履歴/snapshotを反映しない。既存CAP:games:readとDB SELECT/RLSで不足する新grant/permission/schemaが見つかれば、その具体差分だけを別scopeへ返す。

通常の製品registryとC2 source閉集合には隔離候補sourceとして2件を登録する。実auth/実scopeは正式JSONの未受理値をruntime overrideして成功にする仕組みではなく、既存CAP/実RLS/実署名/実DB認証と通常registryを通す。正式checkerのtoken閉集合不一致/TB005拒否は未達として観測し、候補HTTP成功を正式受理に数えない。

## 4. 実装方針

### GETと保存値

`GET /games`（operation_id `preparing_game_list`）は既存PreparingGameListRequestと共通 `Page[PreparingGameRead]` を使う。default20/max100、limit+1、scheduled_at DESC/id DESCのkeyset、最後の返却行から次cursorを作る。status queryや全件集計は追加しない。

`GET /games/{game_id}`（operation_id `preparing_game_detail`）はUUID型のFastAPI引数とする。C2をpath DTO解析より先に通すため、文字列のpath templateをmatchさせた後でUUID型検証する。既存SQLのtenant/preparing/trashed_at IS NULL/hidden_at IS NULL/ID/LIMIT1を使い、0件・別tenant・不可視・他状態は共通404。新たな状態遷移を作らない。

PreparingGameReadは保存13列に対応するID/日時/5区分/必須大会key/両team ID/任意ラベル/statusとapplied_rulesを持つread DTO。tenant/記録権/D4/lineup/環境readyを加えない。statusはLiteral[preparing]、共通BaseSchema/aware日時を再利用する。snapshotは `_decode_preparing_snapshot` →単一codecの検証値→正規encodeでJSON化する。DTO側に6-key/相関のコピー実装を作らず、現在の規則へ再解決しない。単独codecは出所を証明せず、DB seedの資格をそのまま明記する。

通常 `PRODUCT_OPERATIONS` へ `PREPARING_GAME_READ_OPERATIONS` の2件だけを追加する。capabilityは既存CAP:games:read。tokenにtenant値を追加せず、query→token→実tenant_transaction_scope→scope.runを一度通す。未登録/偽造/派生token拒否と既存のSQL/tenant/status/LIMIT検査を維持する。既存試験の候補2件未登録期待は、新正規登録2件と偽造拒否の契約へ限定更新し、旧履歴を研究記録へ残す。

### 実auth/C2とHTTP失敗

games routerはTenantMatchedRouteを使い、`tenant_access._MATCH_OPERATIONS` へ上記2 IDを追加、appの通常ROUTERSへ登録する。require_presented_token→署名/実authn.verify_token→発行済みTenantContext→Expected-Tenant/challenge照合をquery/path検証・games SQLより先に行う。成功ACK/challenge echo/no-storeとCookie更新、既存rosterのC2対象を維持する。auth dependency overrideやC2 match stateの偽造はしない。

失敗写像は既存共通handlerに揃える。Cookie欠如/無効は401、C2欠落/重複/非canonical/不一致と不可視詳細は404、照合後の不正query/UUID/cursorは422。保存snapshotの旧/破損・契約取得不能、DB read故障/結果の不整合はscopeを例外終了させた後に固定HTTP503へ写し、既存HTTPException handlerの固定ErrorEnvelopeを使う。内部SQL/値/原例外/tracebackを公開・ログへ残さない。一覧内の不正行を補完・黙殺して成功pageへ進めない。auth自体の既存非成功外形は変更しない。

### 実API→DB検証

既存disposable PostgreSQLと実製品認可適用fixture、既存settings/identity準備を再利用する。HTTP `POST /auth/login` の実password照合/DB token発行が出すSecure CookieをHTTPSの同じclientで受け、C2 headers付きGETへ通す。手で作ったTenantContext/署名済み成功Cookieや `_login` 直接DB呼出しを実HTTP loginの代用にしない。engine factoryだけを実app engineへ接続でき、Session・署名/認可・tenant_access・scope・DB戻りは差し替えない。一時DB資格は既存隔離fixtureの範囲だけを使い、署名素材は既存repo内の非秘密の固定試験fixtureを再利用する。運用/本人署名鍵を新規発行せず、既存.env/秘密を読まない。

ゲーム/親/チーム/旧snapshotのSQL seedはread環境準備として隔離DBへだけ置く。登録/作成の成功証拠にはしない。共通autouseの実identity照合を維持し、port・DB・一時領域を分離、engine/connection/containerをfinally cleanupする。frontend artifactの検査が必要ならfrozen install等の環境setupのみ許し、検査stubや宣言/lockの無関係変更で回避しない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | preparing readの通常source登録と実認証HTTP/隔離DBの接続候補 | 単一codec固定供給/hash一致、正規registry2token・GET2・C2・DTO/Page接続、実HTTP loginのCookieから同tenant一覧/詳細・保存snapshot同値、ページング/同時刻、別tenant/不可視/他状態/未認証/C2不正/旧snapshot/read故障を検証。C2不一致をgames SQL前に拒否し、非成功の秘匿/rollback/no-storeを確認。対象pytestとbackend/root Ruff/ty、差分検査。正式checker拒否と未受理deltaを記録し、固定HEAD/diffを独立コードレビューへ提出 |

本表は親step4の候補準備1単位で、親の番号/総数を変更しない。正式#174→#173後の実基線と候補HEAD/diffを固定して行う既存追加敵対1回は未消費のまま残す。今回の隔離計画/候補コードの独立照合を、その正式枠の消費や回数リセットへ流用しない。

## 5. DoD

実API認証Cookie→C2→実tenant scope→DB SQL→保存codec→GET応答を、常時成功の認可/Port/providerなしで候補として確認する。DB WHERE/LIMIT、extra拒否・自動エスケープ、旧snapshot拒否・現在規則非遡及、越境の秘匿と非成功外形を保つ。shared account/単一記録端末の意味は不変。

正式基線/7.7、正式read step4全体、UI/provider、作成/RG1、実画面reload、公開は未達。正式lock/sealのafter値を先行確定せず、#174→#173の実履歴後に直列受理する。新実権限や意味仕様の不足は局所的にrootへ報告し、既受理事項の全再審査へ戻さない。

## 6. テスト計画

- 既存component/read境界: codec接合2パス再利用、応答型/旧行・値域・相関・型・契約読込不能、実登録2token/偽造拒否、query/cursor/上限/同時刻順とexact row→DTO。
- 既存app/C2閉集合試験: router method/path/operation IDをexact2件追加し、roster旧対象/拒否を保持。新routerは既存API内部へ登録し、HTTP副アプリや試験専用registryで代用しない。
- 既存DB API試験へ実login成功/無効password、Cookie欠如/改ざん/失効、C2各不正、別tenant/存在なし/trashed/hidden/他状態共通404、limit+1/cursor複数page/同時刻、旧/破損snapshot非成功、実SELECT拒否等のread故障、no-store/ACK成功限定とgames SQL前拒否を追加。
- 正規保存snapshotをseed後に現在規則を変更しても再解決しない。保存値の取得だけを保証し、正規作成経路の出所/原子性を実測済みと扱わない。
- 対象既存＋追加pytest、backend対象format/check/ty、root Ruff/ty、docs/差分検査。正式tenant checkerのtoken閉集合/TB005等は別に実測し未達を残す。skip/timeout/中断を成功へ数えず、同じ全件検査を理由なく反復しない。新権限/未知の閉集合変更が必要なら具体patchをrootへ返す。

### 試験鍵素材の限定（運用鍵を発行しない）

既存backend/tests/test_roster_boundary.py::_client_appの固定32byte素材設定式だけを再利用し、同helperの認可stubは呼ばない。
対象既存試験test_api_auth_exit_entry.py::_configure_requestとtest_api_app.py::_configure_signing_keyも固定素材へ揃え、実署名/検証・実login Cookie経路を維持する。
これは試験素材の限定で、認可/署名検証を成功固定へ変更するものではない。既存scope内の2試験で対応し、運用資格の作成や本人署名の代行をしない。

承認記録: 2026-10-23T15:14:30.102021+00:00、Codex主担当/root。独立/root/csv_reviewの第1回計画レビューは可決P0=0/P1=0/P2=0、対象plan SHA122d23b16e385e11cc5b21aca9c2481fd67ee6d6e779621fcfdd5a9f2c680455、research3d0e26cea697465e3fdebb90f545c0fd6a04619d54501a2b41805609147a5c49。その後rootは既存非秘密固定試験素材へ限定する同scope追補を判断し、承認対象は追補後SHA 7fcc9ce2fb26451c486b1264021ed70c96e03568b4031e8fe12ef09eda7abca6。PO指示4/5/6/8/10に基づく隔離実装を承認、正式#174→#173後の7.7と#175正式追加敵対1回/実画面は未達・未消費。人間逐行確認/山田正輝署名を代記しない。
