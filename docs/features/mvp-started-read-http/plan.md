---
feature: mvp-started-read-http
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-28・PO委任によるCodex主担当判断)
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-started-read-http
created: 2026-10-28
計画レビュー周回: 3
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# U13 開始済み試合の再取得 HTTP 入口 — 実装計画書

本書は、計画候補(反映3)`PLAN-CANDIDATE.md`(SHA-256 `d1b85ebbda626aa78b094afe7d858854815aa78ca08e5049a72ae802a8ed9111`)の本文をそのまま置く。計画採用はtsk544計画のdda33eb8に記録済み。本branchへの限定取り込みはPO委任によるCodex主担当判断であり、本人署名・人間逐行確認ではない。ステップ 4 の登録の根拠行は次の 1 行で、`scripts/check_authz_catalog.py` が行頭の固定語で一意に抽出する。

## 登録の根拠(provenance)

開始済み試合readのGET `/games/{game_id}/started` は、既存の論理route `ROUTE:RECORD:games:read` へ、実operation `started_game_detail` と読取tokenの実CAPを個別に対応させる。新しい論理route・HTTP独自CAP・role・DB ACLは作らず、準備中試合の2GET(`GET /games`・`GET /games/{game_id}`)のprovenance・意味・byteを保持する。

---

作成: 2026-10-28。反映1: 2026-10-28(非作者レビュー P1×2・P2×8 を反映)。**反映2: 2026-10-28**(2 回目の非作者レビュー P1×2・P2×3 を全件反映。findings は `wave3-results-20261028/read-review.json`)。**反映3: 2026-10-28**(反映2の非作者レビュー〔判定 adopt、P0/P1 = 0、P2 = 5〕の P2 を全件反映。P2-1〜P2-5 の扱いは主担当判断〔PO 委任〕で、人間の承認ではない)。計画作者(候補)。**計画候補であり承認済み計画ではない。実装・commit はしていない。本計画の試験は未実行(下の「根拠の区別」に述べる作者の実行は、基線の測定と merge の模擬だけ)。**
主担当裁定(PO 委任)DECISIONS.md の A-1・A-2・A-3・A-11 を前提とする。承認は主担当の計画ゲートで行う。

**根拠の区別**
- [事実] は Git オブジェクト(`git show <sha>:<path>` / `git grep` / `git diff` / `git merge-base`)で確認したもの。行番号は基線 WB(2ed8f977)の値。**反映2までの測定は d523faa4 で行った。2ed8f977 は d523faa4 から `docs/features/tsk544-t1-state-calculation/plan.md` の +4 行だけ**(`git diff --stat` で確認。反映3の作者は測定をやり直していない)。d2df7c0d との差も同じ plan.md だけで、反映1が引いた backend・scripts・contracts の source は blob が同一(52 件中 51 件を `git rev-parse` で照合。残る 1 件が plan.md)。
- [実行] は反映2の作者が、`~/.cache/pitchlog/` 配下の detached worktree(終了時に除去)で実際に走らせた結果。内容は次のとおり。
  - 基線 5 点(WB d523faa4・#188 f0a8ce4e・組立 954cf860・MB 72f4118a・origin/develop 3a24f89e)での `check_tenant_boundary_bypass.py` と `check_authz_catalog.py`
  - WB での `tests/test_check_authz_catalog.py` 全件、`test_roster_self_team_read.py` の該当 1 本
  - `git merge-file` による 3 者 merge の模擬(下記)
- [探索] は [実行] のうち、作者が scratch の worktree でだけ検査の一部を無効にして測った結果(`--skip-oracle` と、履歴検査の関数を差し替えた呼出し)。**正式な合格・不合格の根拠にはしない**。基線の赤の奥に何があるかを見るための観測である。
- [レビュー静的読み] は非作者レビュアーが実行せずに読んで得た結論。[レビュー実行] は同レビュアーが走らせた結果。
- [推論] は静的な読みから導いたもの。
- **共有 DB への接続について(反映2の作者の過失の記録)**: 作者の環境変数 `PITCHLOG_TEST_ADMIN_DSN`・`PITCHLOG_TEST_ROLE_DSN` は `127.0.0.1:5432/pitchlog_dev`(共有 DB `pitchlog-db-1`)を指していた。この 2 変数を外さずに、WB の `backend/tests`(`tests/db` を除く)を 1 回走らせた(約 5 分)。DB を要する試験は共有 DB へ接続した可能性がある。以後の実行は 2 変数を外した。接続した事実の有無と、`pitchlog_test_role` 等の残骸の有無は、作者は DB へ接続しないので確かめていない。root が確認する(memory shared-db-suite-leaves-test-role)。
- 参照した source の blob SHA と sha256 は同じディレクトリの manifest.json に記録した。

**略記**: WB = writer-binding **2ed8f977**(d2df7c0d の後に docs commit が 3 つ続いた先〔d523faa4・fbb30756・2ed8f977〕。d523faa4 からは plan.md の +4 行だけ、d2df7c0d からは同じ plan.md の +6 行だけ。`origin/feature/mvp-first-ball-writer-binding` 上) / #188 = **f0a8ce4e**(ローカル候補・未 push。U3 の frozen 是正 dda01ca8 を含む。どのリモート ref にも含まれない。**GitHub の PR #188 の head は 72f4118a = MB で、state=OPEN・mergeStateStatus=BLOCKED**) / MB = WB と #188 の merge-base 72f4118a / ASM = 組立 worktree の 954cf860(WB d2df7c0d と #188 **1f8052fb**・#186・#187・browser-persistence 8cd0aa6f を merge 済み。**d523faa4 と f0a8ce4e は含まない**。status は clean) / N2 = `repositories/started_snapshot.py` の `read_initial_started_snapshot`

[事実] `git diff --name-only 72f4118a f0a8ce4e` は 22 path、`git log 72f4118a..f0a8ce4e` は 15 commit。1f8052fb から f0a8ce4e への差は `scripts/check_tenant_boundary_bypass.py`・`tests/test_check_tenant_boundary_bypass.py`・`docs/features/mvp-game-start-connection/plan.md` の 3 path だけで、U13 の変更対象とは重ならない。

---

## 0. 結論

- **基線は WB 2ed8f977 に載せる。** #188 f0a8ce4e には載せない(理由は 2 節)。
- **基線の 2 つの機械ゲートは、WB・#188・ASM・MB のいずれでも解析の前に契約エラーで止まる**(反映2。レビュー P1-1。2.1 節)。したがって、ゲートの exit 0 を前提にした完了条件は、基線を直すまで測れない。完了条件を「到達できるもの」と「基線修復後に測るもの(判定保留)」に分け、既知の赤は ID と出力で固定する(5 節)。基線の修復は root の別単位で、**U13 の範囲外**である(6 節の前提条件)。
- 変更は **新規 10 path(と計画書 1)・既存改修 10 path**(3 節。`backend/tests/test_roster_self_team_read.py` は `started_game_detail` の 1 件だけを足す)。(http-route-matrix とその lock は、checker が要求した場合だけ加える)。**`.claude/core-areas.json` の変更は 0**。base-allowlist・repository-contract・operation_registry の変更も 0 を見込む([推論]。ステップ 0 と 5 で実測して確かめる)。
- **7.7 受理は、WB 単独では不要の見込み。#188 合流版では必要**(反映1で訂正。[事実]: #188 の frozen-inputs rev 6 が、U13 の改修対象 2 ファイルを全文凍結している。6 節)。7.7 は root が #188 受理と同じ経路で **1 回だけ**行う。U13 の作者・各ステップは frozen-inputs・history-snapshots を書かない。
- 既存の preparing read(`GET /games`・`GET /games/{game_id}`)と、404 を固定した試験(`backend/tests/db/test_api_auth_exit_entry.py:758-775`)は **byte 単位で変えない**。
- 登録系の試験のうち 4 本は、route 一覧または C2 の対象集合を列挙して完全一致を検査している。このため **列挙に 1 行を足す改修が避けられない**(3.2 節。preparing の意味は変えない)。そのうち `test_roster_self_team_read.py` は、基線で既に赤(initial_* 3 件が余剰)であり、**この赤は #188 自身の CI の赤でもある**。**主担当判断(PO 委任)として、initial_* 3 件の期待集合への追加は #188 の枝で行い、U13 は `started_game_detail` の 1 件だけを足す**。合流後の期待集合は 14 件(2.2 節・3.2 節)。

---

## 1. 前提の再確認

| 項目 | 内容 | 根拠 |
| --- | --- | --- |
| 0 球 reader | N2 は WB だけにある。`read_initial_started_snapshot(handle, game_id)` が、同じ handle の上で次を順に行う。games の lock 読取 → 世代の read と lock 読取 → lineup 2 件 → 選手 → slot・event・PlayRow の存在確認 3 件 → 名簿の artifact 評価。結果として `StartedInitialSnapshot` を返す | [事実] started_snapshot.py:203-361、:238-279(lock)、:313-319(存在確認)。#188 には無い(`git ls-tree 1f8052fb` で 0 件。f0a8ce4e は 1f8052fb の後の 3 path だけが違い、N2 を含まない) |
| 実行器への登録 | 4 token は `PRODUCT_OPERATIONS` に登録済み | [事実] operation_registry.py:41-49(N2-B1。tsk544 plan.md:373-383) |
| 失敗の外形 | N2 の失敗は `StartedSnapshotUnavailable` 1 種類だけ。破損・状態違い・記録ありを区別しない | [事実] started_snapshot.py:45-50,360-361 |
| 現状の 404 | `GET /games/{game_id}` は preparing 限定で、in_progress は 404 になる。fixture は id=6 を in_progress として作り(:607)、:770-775 で本文同一を固定している | [事実] test_api_auth_exit_entry.py:607,758-775 |
| 開始 route | `POST /games/{game_id}/start` と `/start/resolve` は、MB・WB・#188 のいずれにもあり、内容は同一 | [事実] `git diff --quiet d523faa4 f0a8ce4e -- backend/src/pitchlog/api` が差分 0。games.py は MB と WB で同一 |
| d4 の符号化 | 符号化は特権 broker の私有関数 `_broker_d4` にしかない(`"d4.1."` に base64 を続ける形)。frontend には `d4.1` の実装は無い | [事実] initial_grant_broker.py:483-493。`git grep -F 'd4.1'` で該当はこの 1 箇所 |
| API の語彙検査 | api/ 配下の source は `generation` などを部分一致で禁止している。例外は game_start.py の承認済み 2 token だけ | [事実] test_api_conventions.py:42-48,150-185 |
| TB002 | 識別子 `generation` を使えるのは owner_paths(`sync/*` と `repositories/sync_apply.py`)だけ | [事実] base-allowlist.json の conditions[1] |
| 作成 route | 製品の HTTP に試合を作成する route は無い(GET 2 本・POST 3 本だけ) | [事実] games.py:70-233、test_api_conventions.py:313-345 |

**MAP・CRITIC の訂正の引継ぎ**: U12 は N2-A と N2-B1 で採用済み(CRITIC C2)。U13 は「HTTP route・DTO・tenant 照合・登録」だけを扱う。MAP:115 の「allowlist への登録」は、U13 については次の 2 つを指すと読む。
- C2 の `_MATCH_OPERATIONS`
- authz の route 登録

base-allowlist(DB API symbol の許可表)は指さない。理由は、U13 が新しい SQL token も DB API の直接呼出も追加しないため([推論])。

---

## 2. 基線の選択: WB 2ed8f977

**WB に載せる理由**
1. [事実] U13 が呼ぶ N2・4 token・その登録は WB にしかない。#188 に載せると、N2 の取り込みが先に必要になる。
2. [事実] 開始 route は両者で同一。「開始 route を含む」は #188 を選ぶ理由にならない。
3. [事実] #188 の 15 commit(`git log 72f4118a..f0a8ce4e`)の主な内容は次のとおり。U13 が触らない資産なので、U13 から見て #188 を待つ理由は無い。
   - 開始時の有限境界の登録(`check_tenant_boundary_bypass.py`、base-allowlist の #188 受理記録、frozen-inputs の 5→6)と、U3 の source SHA 直書き除去(dda01ca8)
   - broker の import の静的化
   - 世代読取の 12 列化
4. [事実] 世代読取を 12 列にする修正は、WB にも同等のものが入っている(3255ce2e。WB の sync/apply.py:65、prefix_path.py:79、sync_apply.py:38 が `RECORDING_GENERATION_READ_COLUMNS` を使う)。N2 が依存する列の形は WB 単独でそろっている。

**#188 との重なり(ファイル単位。反映2で再測)**

[事実] `git diff --name-only 72f4118a f0a8ce4e` は **22 path**(反映1の「24」は前回レビューの数字の引き写しで誤り)。U13 の変更対象(3 節)と照合した結果は次のとおり。「merge 模擬」は [実行]:MB の blob を base、WB に U13 相当の編集を入れた版を ours、f0a8ce4e を theirs として `git merge-file` を走らせ、衝突の数を数えた。U13 の実際の編集ではなく、同じ位置への小さな編集による模擬である。

| path | #188 の変更 | U13 の変更 | 重なり |
| --- | --- | --- | --- |
| `backend/src/pitchlog/recording_rights/initial_grant_broker.py` | hunk 3 つ(`@@ -15` の `import_module` 削除、`-299`、`-312`) | ステップ 1: :483-493 の `_broker_d4` の本体を委譲に置換し、import ブロックへ `from pitchlog.sync.d4_reference import encode_d4_reference` を 1 行足す | ファイル重なり。merge 模擬の衝突 0。hunk は離れている |
| `backend/tests/test_api_conventions.py` | `@@ -66` | ステップ 3: :313-345 の route 一覧に 1 行、**:317** の `assert len(routes) == 23` を 24 へ、**:314** の docstring の「23本」を「24本」へ(**3 箇所**) | ファイル重なり。merge 模擬の衝突 0。**このファイルは #188 の frozen-inputs rev 6 が全文凍結する(下記)** |
| `tests/test_check_authz_catalog.py` | `@@ -6504` | ステップ 4: :6010-6060 と追記 | ファイル重なり。MB と WB でも内容が違う。merge 模擬の衝突 0。**同じく凍結対象(下記)** |
| **`backend/tests/test_roster_self_team_read.py`** | **f0a8ce4e 時点では未修正**(MB・WB・#188 で blob が同一)。**#188 の枝が自身の CI の赤を直すため、同じ frozenset リテラルへ initial_* 3 件を足す**(2.2 節の主担当判断) | ステップ 3: 同じリテラルへ `started_game_detail` の 1 件を足す | **同一リテラルの重なり。置き場所で衝突が決まる**(下の表)。U13 は中ほどに置く |
| `sync/tokens.py`・`sync/apply.py`・`sync/prefix_path.py`・`repositories/sync_apply.py` | 世代読取の 12 列化(4 本) | **変更しない** | 重ならない。WB 側にも同種の変更が入っている(3255ce2e)。合流時の衝突有無は組立側が測る |
| `contracts/tenant_boundary/base-allowlist.json`・`frozen-inputs.json`・`history-snapshots/*` 4 本 | #188 が移動(frozen-inputs は rev 5→6) | **変更しない** | 重ならない。ただし frozen-inputs は U13 の 2 ファイルの内容を凍結するので、合流版で連動する(下記) |

**`test_roster_self_team_read.py` の merge 模擬(同一リテラル。[実行])**: base=MB、theirs=#188 が initial_* 3 件を足した版(仮)、ours=WB に `started_game_detail` を足した版。衝突の数は次のとおり。

| U13 の置き場所 \ #188 の置き場所 | リテラルの末尾に追記 | リテラルの先頭へ挿入 |
| --- | --- | --- |
| 先頭(`roster_team_list` の前) | 0 | **1** |
| 末尾(`preparing_game_detail` の後) | **1** | 0 |
| **中ほど(`roster_player_update` の前)** | **0** | **0** |

衝突 0 の 3 通りでも、合流後の集合は 14 件で重複なし([実行])。#188 がどこへ置くか作者は知らないので、**U13 は中ほどに置く**。衝突が起きた場合の解消は、両方の追加を残す和集合で機械的に決まる(merge の後に同試験が緑であることで確かめる)。

統合後に再検査を 1 回行う。merge は既存の隔離組立(U01)の手順に従い、本単位では行わない。

**#188 合流後の凍結の連動(反映1で追加。レビュー P1-1)**
- [事実] WB(d523faa4)の `contracts/tenant_boundary/frozen-inputs.json` は contract_revision 5 で、`baseline_control.identity.frozen_projection.external_files` は 4 本(`scripts/frozen_archive.py`、`tests/domain/test_boot_seal.py`、`tests/test_ci_wiring.py`、`tests/test_plan_generation.py`)。
- [事実] #188(f0a8ce4e)の同ファイルは contract_revision 6 で(1f8052fb と同じ内容)、上の 4 本に **`backend/tests/test_api_conventions.py` と `tests/test_check_authz_catalog.py`** を加え、2 本の全文 sha256 を `history-snapshots/48db4fce…`・`4f519485…` として保存している。`git diff --name-only` に当該 2 snapshot が出る。
- [レビュー静的読み] `scripts/frozen_history.py` は external_files の全文を読み、sha256 で射影する。revision が動かないまま射影が変わると拒否する(レビューの根拠: frozen_history.py:836-848,1032-1125,357。実行して確かめた結果ではない)。ローカル既定の不変量モードでは検出されず、PR モード(CI)で検出される。
- したがって、U13 が 3.2 節のとおりこの 2 ファイルを改修すると、**WB 単独(frozen-inputs が rev 5 で 2 ファイルを凍結していない版)では 7.7 は不要**だが、**#188 合流版では frozen-inputs の移動(rev 6→7、history-snapshots の追加、単一受理 = 7.7)が必要**になる。
- 扱い: **root が #188 の受理と同じ経路で 1 回だけ行う**。1 回で済ませるには、凍結する全文が U13 の 2 ファイル改修を含む最終内容であることが要る。#188 の受理と U13 の取り込みの順序は root が決める([推論]。順序が逆になれば、その分 rev がもう 1 回動く)。U13 の各ステップは frozen-inputs・history-snapshots・baseline_control を書かず、そのまま保つ。
- U13 の完了条件のうち「合流版での検査合格」(下の「受入の扱い」)には、この 7.7 の完了を含める。

**観測した事実(反映2で更新)**: 組立 worktree(`~/.cache/pitchlog/assembly-20261027`)の HEAD は **954cf860**(`assembly: merge browser-persistence 8cd0aa6f`。status は clean)。[事実] WB d2df7c0d と #188 の 1f8052fb を祖先に持つが、**d523faa4 と f0a8ce4e は祖先でない**(後ろの 2 commit は未取り込み)。[実行] 954cf860 の frozen-inputs は rev 6・external_files 8 本で、U13 の 2 本(`test_api_conventions.py`・`tests/test_check_authz_catalog.py`)を含む(いずれも閲覧のみ)。U13 はこの 2 本を変えないので、組立側の凍結関連の状態を増やさない。ただし上の連動により、合流版の frozen-inputs の内容(rev 7 の要否と全文 sha256)は U13 の 2 ファイルの最終内容に依存する。**どの #188 を受理の対象版にするか(GitHub の head 72f4118a、ローカル候補 f0a8ce4e、組立が取り込んだ 1f8052fb のどれか)は、root が決める**(9 節の確定点 8)。

**受入の扱い**: U13 の実 PG 受入はまず WB 単独で通す。#188 を合流した組立版でも、ステップ 5 の DB 試験と非 DB の影響範囲を再実行して合格し、かつ**合流版の 7.7(frozen-inputs の移動)が root の単一受理で完了していること**を、正式統合の条件とする。**さらに、5 節の「判定保留」2 項目(G-TB で TB の検出が U13 由来で増えていないこと、G-AZ が exit 0 で routes が 51 のままであること)が、基線修復後の再測定で合格していること**を、正式統合の条件に含める(反映3。レビュー P2-1)。保留の間は、これらを合格と書かない。

### 2.1 基線ゲートの既知の赤(反映2。レビュー P1-1)

[実行] 作者が基線 5 点で走らせた結果。どのコマンドも、各 worktree のルートで、repo の `.venv` の python を使って実行した。

| ゲート(CI の対応) | WB(測定は d523faa4。2ed8f977 と source は同一) | #188 f0a8ce4e | ASM 954cf860 | MB 72f4118a | origin/develop 3a24f89e |
| --- | --- | --- | --- | --- | --- |
| **G-TB** `scripts/check_tenant_boundary_bypass.py`(CI の tenant-boundary-bypass ジョブ) | exit 2「base-allowlist.json.baseline_control.history: **履歴末尾と 7 資産の識別値が不一致**」 | exit 2「…history: **射影が動いた資産は識別値の更新が必要: contracts/tenant_boundary/base-allowlist.json**」 | exit 2「…history: **1 受理につき追記 record は 1 件まで**」 | WB と同じ | exit 0 `ok` |
| **G-AZ** `scripts/check_authz_catalog.py` | exit 1「contracts/authz/route-registry.json: **oracle input blob が不一致**」 | 同じ | 同じ | 同じ | exit 0 `ok … routes=49` |

**なぜ止まるか([実行]+[事実])**
- **G-TB(WB・MB)**: base-allowlist の履歴末尾(#184 の受理 record)が記録する識別値は repository-contract が rev 28、runtime-authz が rev 22。WB の現物は repository-contract が rev 30、runtime-authz が rev 24。WB 自身が動かした分の受理 record が履歴にない。develop の履歴は WB と同じ 31 件で、WB 側に追記が無い。`--base-ref` を `72f4118a`・`origin/develop`・`d2df7c0d`・`3a24f89e`・`d523faa4` に変えても、WB・MB・#188・ASM は契約エラーのままで、メッセージが変わるだけだった。
- **G-TB(#188)**: 現物の repository-contract は rev 28、runtime-authz は rev 23、履歴は 32 件(末尾が #188 の受理)。メッセージは base-allowlist 自身の射影が動いたのに識別値が更新されていないことを指す。f0a8ce4e の dda01ca8(U3 の frozen 是正)を含めても同じメッセージで、解消していない。詳細な原因は #188 側の担当が確定する(作者は未確定)。
- **G-TB(ASM)**: 履歴は 33 件で、develop(31 件)に対し 2 件(#187 と #188 の受理)が追記されている。1 受理につき 1 件までという規則に当たる。
- **G-AZ**: `contracts/authz/oracle-seal.lock.json`(oracle_commit 8a40519d)の `input_assets` 4 本が、現物の git blob と違う。4 本は `route-registry.json`・`route-registry.lock.json`・`http-route-matrix.json`・`http-route-matrix.lock.json`。develop では一致する。WB 系列が `72800152`(初期開始の認可登録候補)でこれらを動かし、oracle seal を再封印していない。再封印(`--reseal-oracle`)は人間レビューが要る専用操作で、通常の検査は再封印しない(oracle-seal.lock.json の `reseal_policy`)。
- [事実] GitHub の PR #188 の head 72f4118a の CI(run 40352685972、2026-10-26)は、harness・tenant-boundary-bypass・core-guard・backend が failure で、これらの赤と整合する(レビューの観測。ジョブログ本文は未取得)。
- **U13 由来の赤ではない**。#188・WB の系列の既存の赤である。

**解析に入れないことの影響**: ゲートは検査の前半の契約検証で止まるので、TB の解析結果(TB001〜TB007 の検出)も、route の件数(`routes=…`)も出ない。計画の「TB002 が基線で緑か」「TB001〜TB004 が増えない」「exit 0 で routes 51」は、基線のままでは測れない。

**赤の奥に何があるか([探索]。scratch での観測で、合否の根拠にしない)**
- G-AZ: oracle seal だけを飛ばす(`check_authz_catalog.py --skip-oracle`。引数の説明は非表示)と、WB は exit 0 で `routes=51 cells=12`。**G-AZ の基線の赤は oracle seal の 1 点だけ**と読める。
- G-TB: 履歴の識別値の検査(`frozen_history._validate_repository_identifier_record`)だけを無効にした呼出しでは、WB は続けて「固定関数製品registryの登録形式が不正」の契約エラーで止まった。#188 は解析に入り、TB001×3・TB005×28・TB007×6 を出した。ASM は履歴の件数の契約エラーのまま。**履歴の記録を直しただけでは exit 0 にならない可能性が高い**。
- WB で `tests/test_check_authz_catalog.py` 全件を走らせると、**4 件が赤**(25914 passed)。`test_pending_state_always_runs_only_pending_protected_validation`(「初期4表はRG1既基線と共にexact-setで必要」)・`test_repository_catalog_covers_the_entire_requirements_file`・`test_repository_oracle_assets_are_valid`・`test_normal_validation_never_reseals_a_semantically_valid_drift`。後ろの 3 件は oracle input blob の不一致を E 行に持つ。
- WB で `backend/tests` の `tests/db` を除く全件(DSN を外した版)は、**100 failed・27 errors・8386 passed・4 skipped**(5 分 19 秒)。DB を要する試験が DB なしで失敗・エラーになる分を含むので、基線の確定値ではなく参考値である。静的な照合の試験が基線で赤の例として、`test_rg1_operations.py::test_rg1_keeps_two_fixed_functions_with_one_registered_rule_resolver`・`test_sync_first_ball_registration.py::test_no_runtime_registration_or_scalar_proof`・`test_roster_boundary.py::test_issuance_and_verification_callers_are_exact_sets`・`test_roster_self_team_read.py::test_tenant_match_operations_keep_old_routes_and_add_self` がある。**ステップ 0 は、専用の Postgres(または CI)で、赤の全件を ID と E 行で記録し直す**。

**基線修復の単位(U13 の範囲外。root が持つ)**: 次の 3 点は、WB 自身の受理(7.7)・#188 の受理・oracle seal の再封印にあたる。U13 の作者・各ステップはこれらを書かない。
1. WB の base-allowlist 履歴に、WB が動かした資産(repository-contract rev 30、runtime-authz rev 24 など)の受理 record を足す。[探索] の登録形式の契約エラーも解消する必要がある見込み。
2. #188 の側で、base-allowlist の識別値の更新と、ASM の 2 件追記の扱い(1 受理 1 件)を整える。
3. oracle seal の再封印。**U13 のステップ 4 が route-registry とその lock を動かす**ので、再封印は U13 の反映の後に 1 回で済ませるのが効率的([推論])。

### 2.2 #188・WB・U13 の範囲と merge 順序(反映2。レビュー P1-2)

**主担当判断(PO 委任)として次を採る。PO 本人の裁定でも人間の逐行確認でもなく、計画ゲート(承認欄は人間の明示承認まで書かない)で確定する。**
- **initial_* 3 件の期待集合への追加は、#188 の修正として #188 の枝で行う。**
- **U13 は `started_game_detail` の 1 件だけを `test_roster_self_team_read.py` の期待集合へ足す。** U13 は initial_* を書かない。
- **合流後の期待集合は 14 件**(10 + initial_* 3 + `started_game_detail` 1)。

**理由([事実]+[実行])**
- `test_roster_self_team_read.py` と `api/tenant_access.py` は、MB・WB・#188 で blob が同一。したがって #188 の枝でも同試験は同じ 1 failed(Extra items = initial_* 3 件)で、#188 自身の CI の赤である。f0a8ce4e でも未修正。`git diff --name-only 72f4118a f0a8ce4e` の 22 path に同試験は無い。
- #188 が緑になるには同じリテラルへ 3 件足す必要がある。同じ修正を U13 も持つと、同一行の修正が重複する。

**U13 の枝での見え方([実行]。scratch で `tenant_access` と同試験へ `started_game_detail` だけを足して測った)**
- WB + U13: `test_tenant_match_operations_keep_old_routes_and_add_self` は **1 failed。Extra items は initial_* 3 件だけ。Missing は 0 件で、`started_game_detail` は両側にある**。ステップ 0 の赤と同じ 3 件で、U13 は新しい赤を足さない。
- さらに initial_* 3 件を足した版(#188 の修正との合流相当): 同ファイル 14 passed。

**merge 順序(root が決める。作者の提案)**
1. #188 の枝で、initial_* 3 件を同試験へ足す(期待集合 13 件)。これは #188 の担当への申し送りで、U13 の作業ではない。**置き場所は、リテラルの末尾(`"preparing_game_detail"` の直後)へ追記する**。U13 は中ほど(`"roster_player_update"` の直前)に置くので、この置き場所なら衝突 0 になる。[実行] 反映3の作者の模擬(U13 と #188 が先頭・中ほど・末尾のどこに置くかの 3×3 = 9 通り)では、**両者が同じ位置に置いた 3 通りだけ**が衝突 1、残る 6 通りは衝突 0。レビューの模擬でも、`"roster_player_update"` の直前(U13 と同じ箇所)だけが 1 件衝突し、ほかは衝突 0 だった。#188 の担当が末尾以外に置くときは、中ほどを避けること。
2. 組立側で WB と #188 を合流する。
3. U13 を載せる(+1 で 14 件)。合流版で同試験が緑になることが、U13 の「合流版での検査合格」の条件の一部である。
- #188 の修正が U13 より後になる場合、合流版で同試験は一時的に赤(Extra = initial_* 3 件)になる。これは既知の赤として扱う。
- 置き場所は 2 節の表のとおり、U13 は中ほどに置く。

---

## 3. exactpaths

### 3.1 新規(10 path + 計画書 1)

| path | 内容 | 捕捉する core glob([事実] core_guard は fnmatchcase で照合する) |
| --- | --- | --- |
| `backend/src/pitchlog/sync/d4_reference.py` | d4 の wire 符号化を公開する関数 `encode_d4_reference(tenant_id, game_id, value) -> str`。純粋関数で、broker からは import しない(A-3) | `backend/src/pitchlog/sync/*`(sync-protocol と recording-rights。core-areas.json:261,516) |
| `backend/src/pitchlog/repositories/started_read.py` | 開始済み read の組立器(4 節) | `backend/src/pitchlog/repositories/*`(tenant-isolation、:629) |
| `backend/src/pitchlog/api/schemas/started_games.py` | DTO `StartedGameRead` | `backend/src/pitchlog/api/*`(:647) |
| `backend/src/pitchlog/api/routers/started_games.py` | `GET /games/{game_id}/started`(`operation_id="started_game_detail"`、`route_class=TenantMatchedRoute`) | 同上 |
| `backend/tests/test_api_started_game.py` | route・DTO・404/409/503 の外形・非開示の単体試験 | `backend/tests/test_api_*.py`(:648) |
| `backend/tests/test_started_read_repository.py` | 組立器の順序・振り分け・N2 の非改変 | `backend/tests/test_*_repository.py`(:646) |
| `backend/tests/test_d4_reference_boundary.py` | d4 符号化が broker の出力と byte 一致し、型が違えば拒否すること | `backend/tests/test_*_boundary.py`(:645) |
| `backend/tests/db/test_started_game_read_http.py` | owned PG と実 HTTP による受入(7 節) | `backend/tests/db/*`(5 領域すべて) |
| `frontend/src/api/startedGame.ts`・`startedGame.spec.ts` | API client と transport 形の検証 | `frontend/src/api/*`(:653) |
| `docs/features/mvp-started-read-http/plan.md` | 承認対象の計画書。route 登録の provenance として行頭固定の 1 行を置く | 非 core |

(計画書を除く内訳は、backend の source 4 本、backend の単体試験 3 本、DB 試験 1 本、frontend 2 本で、計 10 本。)

**命名の制約**
- api/ 配下の識別子と文字列に `generation` を含めない(test_api_conventions.py:42-48)。
- `generation` を識別子に使ってよいのは `sync/d4_reference.py` の中だけ(TB002 の owner path)。`repositories/started_read.py` の中では、N2 の戻り値属性 `.generation` を参照するだけにし、新しい名前は付けない。TB002 がこの書き方で通るかは、**基線のゲートが止まっている間は測れない**(2.1 節)。基線修復後の基線で実測する。それまでは、下の退避先を先に採るかを、計画ゲートで主担当が決める(9 節の確定点 9)。
  - [事実・補強。レビュー P2-8] TB002 は owner_paths 外の変更行に適用され、`a.b.c` を分割した各部分も候補にするので、`snapshot.generation` は候補に当たり得る。一方で、非 owner path の `started_snapshot.py:259` は局所名 `generation` を使い、base-allowlist(rev 39)に adjudication 0 件のまま通っている([推論]: 属性参照だけでは自動では赤にならない)。
  - **赤になった場合(または測れない間の予防)の退避先**: `.generation` を読む箇所を `sync/d4_reference.py` 側へ寄せる(組立器は snapshot から tenant_id・game_id と世代値を取り出す薄い関数を d4_reference に置いて呼ぶ)。base-allowlist への adjudication 追加は 7.7 を要するので、退避先にしない。
- 新規の非 DB 試験 3 本は、`pitchlog.db`・`schema-manifest`・`migrations` の文字列を本文に含めない。含めると core 登録が必須になる可能性がある(memory core-area-paths-locked)。DB のモデルが要る試験は `backend/tests/db/` に置く(この方針自体は変えない)。
  - **出典の訂正(反映1。レビュー P2-7)**: 計画候補は「core_guard の機械導出 token」と書いたが誤り。[事実] `scripts/core_guard.py` に当該文字列は無く、`fnmatch.fnmatchcase` の使用は :689 の 1 箇所だけ。`schema-manifest` の文字列は `scripts/check_authz_catalog.py:207`(`contracts/db/schema-manifest.json`)と `scripts/generate_orm_acceptance_sheets.py:15` にある。`pitchlog.db`・`migrations` が機械導出される出典は作者は特定していないので、「含めない」は安全側の運用として残し、出典は断定しない。

### 3.2 既存改修(10 path。preparing の意味は変えない)

| path | 変更 | 理由 |
| --- | --- | --- |
| `backend/src/pitchlog/recording_rights/initial_grant_broker.py` | `_broker_d4` の本体を `encode_d4_reference` への委譲に置き換える。名前・例外の写像(`_broker_invalid`)・出力 byte は保つ | A-3「符号化は 1 箇所」。NFR-018 の重複実装を避ける。既存試験 3 本(test_initial_recording_right_candidate.py:923 など)が `_broker_d4` を直接呼ぶので、名前を残す |
| `backend/src/pitchlog/api/app.py` | `ROUTERS` に `started_games.router` を 1 行追加する | [事実] app.py:18-25 |
| `backend/src/pitchlog/api/tenant_access.py` | `_MATCH_OPERATIONS` に `"started_game_detail"` を 1 件追加する | C2 照合。本文より先に、認証・Expected-Tenant・Challenge の照合を行わせる(:22-38,63-82) |
| `backend/tests/test_roster_self_team_read.py` | `test_tenant_match_operations_keep_old_routes_and_add_self`(:35-51)の期待集合へ **`"started_game_detail"` の 1 件だけ**を足す。置き場所は集合リテラルの中ほど(`"roster_player_update"` の直前)。試験名・docstring・initial_* の扱いは変えない | **完全一致の検査**。基線 WB の `_MATCH_OPERATIONS` は 13 件、同試験の期待集合は 10 件で、差は initial_* 3 件。**この 3 件は #188 の枝で足す**(主担当判断。2.2 節)。U13 は `started_game_detail` を足すと実集合は 14 件、期待集合は 11 件になり、WB 単独では Extra = initial_* 3 件の赤が残る(既知の赤。下の裁定) |
| `backend/tests/test_api_app.py` | :48-108 の route と operation_id の完全一致の列挙に 1 行追加する | 完全一致の検査なので必須。:244-260 の preparing 2 GET の試験は変えない(path の絞り込みが `{"/games","/games/{game_id}"}` なので影響しない) |
| `backend/tests/test_api_conventions.py` | **3 箇所**: ① :313-345 の静的 route 一覧に `("/games/{game_id}/started", {"GET"})` を追加 ② **:317** の `assert len(routes) == 23` を 24 へ ③ **:314** の docstring「の23本を照合」を「の24本を照合」へ | 完全一致の検査なので必須。**#188 合流版ではこのファイルが全文凍結の対象**(2 節) |
| `scripts/check_authz_catalog.py` | `_STARTED_READ_HTTP_BINDINGS` と provenance の照合を追加する。`_INITIAL_HTTP_BINDINGS` と同じ形にし、`/games/{game_id}/started` を論理 route `ROUTE:RECORD:games:read` に、読取 token とその CAP に個別に結び付ける | 既存の初期 HTTP 登録(:2363-2615)と同じ有限照合 |
| `tests/test_check_authz_catalog.py`(**#188 合流版では全文凍結の対象**。2 節) | 正例 1 件と変異拒否(欠落・余剰 CAP・games:update への誤結線・preparing 2 GET の provenance 改変など)を追加する。:6010-6058 の `test_preparing_read_registered_route_matches_real_gets` は、`games:read` の provenance について「旧 2 件を先頭に保ち、後ろに新規を足した完全一致」へ書き換える。games.py の GET 2 本の完全一致の部分は変えない | 新 GET は別ファイルに置く。このため :6040-6058 の games.py の AST 照合は変わらない |
| `contracts/authz/route-registry.json` と `.lock.json` | `games:read` の `provenance_ids` の末尾に追記し、`design_provenance` に追加する。lock は再生成する | 正式 JSON の writer は root だけ(mvp-game-start-connection plan.md:428 の前例) |
| `contracts/authz/http-route-matrix.json` と `.lock.json` | 変更しない見込み。論理 route を増やさず、`games:read` の行(disposition=conditional)を再利用するため。checker が要求した場合に限り、lock を再生成する | [事実] matrix の routes は 51 件。games:read の行は既にある |

**期待集合の裁定(反映2で改訂。レビュー P1-2)**

| 項目 | 内容 |
| --- | --- |
| 基線の赤 | [事実] 基線 WB の `tenant_access._MATCH_OPERATIONS` は 13 件、`test_roster_self_team_read.py` の期待集合は 10 件。差は `initial_device_enroll`・`initial_game_start`・`initial_game_start_resolve` の 3 件(逆向きの差は 0 件)。[実行] WB・#188 f0a8ce4e・ASM 954cf860 で `-k tenant_match_operations` が **1 failed**(Extra items: 上の 3 件)。develop(3a24f89e)では `initial_` が 0 件で **1 passed**。 |
| 3 件の由来 | [事実] initial_* 3 件は `5f53237d` が `tenant_access.py` に入れた。MB・WB・#188 のすべてにあり(各 3 件)、develop には無い。試験の期待集合だけが追随していない。 |
| 扱い(**PO委任の主担当判断。2.2 節**) | **initial_* 3 件の追加は #188 の枝で行う。U13 は `started_game_detail` の 1 件だけを足す。合流後の期待集合は 14 件。** PO 本人の裁定でも人間の逐行確認でもない。 |
| 基線の記録 | ステップ 0 の既知の赤として、同試験の ID と、Extra items の 3 件(E 行)を記録する。 |
| 完了条件(WB 単独) | ステップ 3 の後、同試験の失敗は **Extra items が initial_* 3 件だけ・Missing が 0 件・`started_game_detail` が両側にある**こと。これ以外の差が出たら新しい赤とみなす。同試験は WB 単独では緑にならない。 |
| 完了条件(合流版) | #188 の枝の修正(13 件)が入った合流版で、同試験が緑(実集合と期待集合が 14 件で一致)であること。 |
| 注意 | initial_* を持たない版(develop)へ U13 の改修だけを持ち込むと、実集合が 11 件、期待集合が 11 件で、この試験は緑になる。ただし U13 の基線は WB なので、その状況は想定しない。 |
| 試験が追う操作の範囲 | 同試験が完全一致で固定するのは `_MATCH_OPERATIONS` だけ。operation_id と route の対応は `test_api_app.py` の列挙が固定する。 |

**変えないもの(byte 単位で保持)**
- `api/routers/games.py`
- `api/schemas/games.py`
- `repositories/games.py`
- `repositories/started_snapshot.py`
- `repositories/started_snapshot_operations.py`
- `repositories/operation_registry.py`
- `frontend/src/api/games.ts`
- `frontend/src/api/client*`
- `backend/tests/db/test_api_auth_exit_entry.py`(全体)
- tenant_boundary の全 JSON
- `.claude/core-areas.json`

**レビューで見る点**: 上の各ファイルについて `git diff <基線> -- <path>` が空であることを、レビュー時に機械的に確認する。

---

## 4. 設計(A-1・A-2・A-3・A-11 の具体化)

### 4.1 組立器 `read_started_game(handle, game_id)`(repositories/started_read.py)

**handle**: `tenant_transaction_scope(context)` が返す `_TenantTransaction` をそのまま受ける。新しい Session・TX・分離レベルは作らない([事実] transaction.py:711-722)。

**手順(既採用の N2 と同じロック順。A-2)**

| 順 | 処理 | 結果の扱い |
| --- | --- | --- |
| ① | `GameLockToken(game_id)`。同じ TX で `GameReadToken(game_id)` を行い、2 つの行が一致し、tenant と id が一致することを確かめる | 0 行(別 tenant・不存在)→ **NotVisible**。**行はあるが lock 行と read 行が不一致、または tenant・id が不一致 → Corrupt**(N2 :240-241 と同じ。反映2) |
| ② | 状態を判定する。**条件は N2 :243-246 の 4 つだけ** | status が in_progress でない、または trashed_at・hidden_at・import_batch_id が非 NULL → **NotVisible**。以後の SQL は実行しない |
| ③ | `RecordingGenerationReadToken` → `RecordingGenerationLockToken(game_id, n)` | 0 行または不一致 → **Corrupt**(A-3 の「世代が無ければ null」は採らない。9 節の確定点 6) |
| ④ | 存在確認 token 3 件(`StartedEventSlotsExistenceToken` ほか) | 1 件でも行があれば → **Recorded**(U14 の拡張点)。全件 0 なら次へ |
| ⑤ | `read_initial_started_snapshot(handle, game_id)` を**そのまま**呼ぶ(N2 は改変しない) | `StartedSnapshotUnavailable` → **Corrupt**。**次は不可視でなく破損であり、404 へ倒さない**: `started_at` が datetime でない・tz を持たない(N2 :247-248)、away と home が同一(N2 :251-255)。この 2 つは組立器が自前で判定せず、N2 の拒否として Corrupt(503)になる(判定の複製を増やさない)。④で Recorded と判定した場合は N2 を呼ばないので、記録ありを優先して 409 になる(U13 の暫定。同 tenant にしか返らない)。 |

**戻り値と例外の分け方(反映1。レビュー P2-4)**
- **NotVisible と Recorded は値として返す**(`StartedReadNotVisible`・`StartedReadRecorded` の 2 つの閉じた型)。成功は `StartedGameView` を返す。
- **Corrupt は `with` の中で例外 `StartedReadCorrupt`(`Exception` の子)として送出する**。値で返さない。理由: 値で返すと `with` が正常終了し、`_TenantTransactionScope.__exit__` は例外なしの経路(`_before_writer_finish` → 確定の経路。transaction.py:583-640)を通る。read-only なので結果は変わらないが、「rollback した」という主張を機構が裏付けない。例外で抜ければ `__exit__` は例外つきの経路へ入り、`ExitStack.__exit__` へ例外が渡る([推論]: 例外つきの終了は Session の取消側へ進む。作者は実行していない)。
- ④で Recorded と判定した場合、および②で NotVisible と判定した場合は、例外にしない。404・409 は preparing と同じく `with` の外で `HTTPException` に写す(games.py の `with` は :107-109、`except Exception` は :110、503 は :111、404 は `with` の外の :112-113 で送出している)。

- ⑤で N2 は lock を取り直すが、同じ TX の中での再取得なので、内容は変わらない([推論])。

**判定の二重化の範囲と理由(反映1。レビュー P2-1)**
- [事実] N2 は :238-241 で games の lock 読取・read の一致と tenant・id を、:243-246 で status・trashed_at・hidden_at・import_batch_id を、:247-248 で started_at の型と tz を、:251-255 で away と home の同一を、:256-279 で世代の read・lock の一致と kind・revoked・retired・watermark・prefix を、:313-319 で存在確認 3 件を検査する。組立器の①②③④は、同じ token と同種の述語を、N2 より先に実行する。**同じ TX の中で、SQL 7 文(①の 2、③の 2、④の 3)が N2 の中で再実行される**。
- 理由: N2 の失敗は `StartedSnapshotUnavailable` 1 種類で、不可視(404)・記録あり(409)・破損(503)を区別できない(1 節)。A-2 は、記録ありの検出(④)を N2 より先に行うことを求める。404 と 503 を分けるには、②・③の判定も N2 より先に要る。N2 を改変しない(A-2)限り、先読みの二重化は避けられない([推論])。
- **テナント分離は壊れない**。両方とも tenant を executor が束縛する token で、越境は 0 行になる。
- 述語がずれる危険(組立器が NotVisible にした試験を N2 が通す、またはその逆)は、次の 2 つの試験で抑える(`test_started_read_repository.py`)。
  - 「②の NotVisible 条件の集合は **N2 :243-246 の 4 条件**と同一」であることを、条件ごとの fixture で確かめる。started_at の型・tz、away と home の同一、①の行不一致は ② に含めず、Corrupt になることを別の fixture で確かめる。
  - 「N2 が `StartedSnapshotUnavailable` を返す全 fixture で、組立器は NotVisible・Recorded・Corrupt のいずれかに落ちる。成功(200 相当)にならない」ことを確かめる。
- **振り分けに `StartedSnapshotUnavailable` を使わない(A-2)**。0 球か記録後かは④で決める。⑤の例外は、④で「記録なし」と判定した後に起きたものだけなので、破損として扱う。

**成功時に返す値(すべて④・⑤と同じ TX でロック下に読んだ値)**
- 見出し: ①の game 行の列のうち、preparing DTO と同じ 11 列
- started_at
- applied_rules: 既存の公開 codec `decode_applied_rules` → `encode_applied_rules` で変換する(rule_snapshot.py:315,320。preparing と同じ codec を通す。NFR-018)
- 保存 lineup 2 件(N2 の `lineups`)
- 名簿の射影(N2 の `roster`。単一 artifact の出力)
- 初期状態(N2 の `before`。stateFields と scoreboard)
- `current_d4`: `encode_d4_reference(snapshot.tenant_id, snapshot.game_id, snapshot.generation)`

### 4.2 HTTP(api/routers/started_games.py)

- `with tenant_transaction_scope(context) as scope: result = read_started_game(scope, game_id)` の形にする。
- 例外は preparing と同じ形で閉じる(games.py:106-113。try が :106、`with` が :107-109)。404・409 は `with` の外で、組立器が値で返した結果から写す(4.1 節)。

| 結果 | 応答 |
| --- | --- |
| NotVisible | 404。本文は preparing の 404 と byte 単位で同じ(同じ `HTTPException(404)` の経路) |
| Recorded | **409、固定の本文。値は含めない**(U13 の暫定。U14 で 200 に置き換える) |
| Corrupt(`StartedReadCorrupt`)・その他の例外 | 503、固定の本文。`with` の中で例外として抜け、preparing と同じ `except Exception: raise HTTPException(status_code=503) from None`(games.py:110-111。**作者が 2ed8f977 で `git show` して数えた行番号**。レビューの指摘は :109-110 だが、`except` は :110、`raise` は :111)で写す |
| 成功 | 200 |

- 成功応答の header は既存の `tenant_match_response_headers` が付ける。`no-store`、match ack、challenge の返送。
- **409 は主担当が確定する点**。A-1 の「他状態は 404」は status が別のものを指し、記録後の in_progress は該当しない。同じ tenant にしか返らないので、B6 の非開示(SP:973-986)にも触れない([推論])。代替案として 503 も挙げておく。ただし 503 では、端末が「一時障害」と誤って再試行し続ける。

### 4.3 DTO `StartedGameRead`(A-3・A-11: 確定状態と current_d4 だけ)

```
read_kind: Literal["initial"]          # U14 で "recorded" を足す判別子
id, scheduled_at, game_type_key, tournament_key, away_team_record_id,
home_team_record_id, plate_umpire, section_label, week_label, day_label,
game_number_label                       # preparing と同じ見出し 11 列
status: Literal["in_progress"]
started_at: AwareDatetime
applied_rules: dict                     # 既存 codec で変換
lineups: {away, home}: {lineup_id, team_record_id,
          entries[{player_id, batting_order, fielding_position, uniform_number_snapshot}]}
roster: InitialRosterProjection (initial_game_roster_v1 の wire)
state: StateSnapshot (t2_first_pitch_continuation_v1.d.ts の StateSnapshot)
current_d4: str | None                  # U13 の 200 応答では常に str。null は返さない(世代が無ければ 503。9 節の確定点 6)
```

**返さないもの**
- holder_device・device_id
- recovery_generation・recording_right_proof・proof_digest・V12
- issuance_order・granted_at
- confirmed_watermark・applied_prefix(D3 を返すかは O1 へ移るときに決める。A-11)
- tenant_id

**`extra="forbid"` と frozen の扱い**
- DTO は `extra="forbid"`、frozen にする。
- 照合は全キーの完全一致で行う。frontend の検証器も、未知のキーと未知の `read_kind` を拒否する(fail-closed)。

**holder 表示**: 端末が「保持」と表示するのは、U18 が端末 grant の d4 と比べた結果である。U13 はこの比較を行わず、書込みの許可にも使わない(A-3)。

### 4.4 frontend(frontend/src/api/startedGame.ts)

- `readStartedGame(id, signal)` は `apiRequest('GET', `/games/${id}/started`, {tenantBound:true, signal})` を呼ぶ。
- 応答は transport の形だけを検証する。業務規則は再計算しない。state と roster の型は `contracts/state-transition/*.d.ts` から import する(既存の前例: frontend/src/domain/initialGameRoster.spec.ts:7)。
- 結果の写像: 404 → `not-found`、409 → `recorded-unsupported`、それ以外 → 例外。
- route の選択(開始応答をヒントにする、preparing が 404 のときだけ 1 回試す)と、authEpoch の再照合は **U18 の provider の責務**とし、U13 には入れない(A-1 の frontend 側の記述は U18 で実装する)。

---

## 5. 実装ステップ(1 ステップ = 1 commit。コア領域なので、各ステップで敵対レビューと人間の逐行確認を行う)

| # | 範囲 | 完了条件 |
| --- | --- | --- |
| 0 | 事前の実測。コードは変えない | WB(2ed8f977)の detached worktree で次を実行し、**基線の値を ID と出力(E 行)まで記録する**。① `uv run python scripts/check_tenant_boundary_bypass.py` ② `uv run python scripts/check_authz_catalog.py` ③ backend の非 DB 試験(専用 Postgres または CI の環境で。共有 DB へ接続しない。DB 接続の環境変数を外す) ④ `tests/test_check_authz_catalog.py`。**既知の赤として必ず記録するもの(2.1 節)**: **G-TB の exit 2 と「履歴末尾と 7 資産の識別値が不一致」**(出力全文)、**G-AZ の exit 1 と「oracle input blob が不一致」**(出力全文)、`tests/test_check_authz_catalog.py` の赤 4 件、`test_tenant_match_operations_keep_old_routes_and_add_self` の Extra items 3 件。**TB002 と TB001〜TB004 の実測は、ゲートが止まるのでこのステップでは行わない**(修復後の基線で行う。2.1 節)。参考として `check_authz_catalog.py --skip-oracle` の結果(WB で `routes=51`)を記録してよい(正式な合格ではない) |
| 1 | d4 符号化の公開化: `sync/d4_reference.py`、broker を委譲に置き換え、`test_d4_reference_boundary.py` | broker の既存試験がすべて通る。新しい関数と `_broker_d4` が、固定ベクタ(世代 1、17、2^63−1、tenant と game の境界値)で byte 一致する。型違いと範囲外は拒否する |
| 2 | 組立器 `repositories/started_read.py` と `test_started_read_repository.py` | **到達できる条件**: 次の 9 点を試験で確かめる。① token の発行順が A-2 と一致する ② NotVisible のときは②以降の SQL が 0 件 ③ Recorded のときは N2 を呼ばない ④ N2 の例外は Corrupt に写る ⑤ `StartedSnapshotUnavailable` を振り分けの条件に使っていない(AST で確認) ⑥ **②の NotVisible 条件の集合が N2 :243-246 の 4 条件と同一であること** ⑦ N2 が `StartedSnapshotUnavailable` を返す全 fixture で、組立器が成功にならず NotVisible・Recorded・Corrupt のいずれかに落ちること ⑧ Corrupt は例外として送出され、値で返らないこと ⑨ **`started_at` が naive・away と home が同一・①の lock 行と read 行が不一致の fixture は、NotVisible でなく Corrupt になること**。かつ、新しく追加した試験を含め、**ステップ 0 の既知の赤の集合(ID と E 行)が変わらず、新しい赤が 0 件**であること。**判定保留(基線修復後に測る)**: G-TB で TB001〜TB004 が新しく増えないこと。基線の赤の間は、G-TB の出力がステップ 0 の記録と全文一致する(exit 2・同じメッセージ)ことだけを記録し、**TB の解析を通ったとは書かない** |
| 3 | HTTP と DTO: schemas・routers・app.py・tenant_access.py・test_api_app.py・test_api_conventions.py・**`test_roster_self_team_read.py`(`started_game_detail` の 1 件だけ)**・`test_api_started_game.py` | 404・409・503 の本文固定、非開示キーの完全一致、C2 照合が SQL より先に行われること、API の語彙検査(generation 0 件)を確かめる。preparing の試験群は改変しない。**`test_roster_self_team_read.py` は、期待集合へ `started_game_detail` だけを足す。WB 単独では同試験は赤のまま残り、その失敗が Extra items = initial_* 3 件だけ・Missing 0 件であること(ステップ 0 の記録と同一)を確かめる**。合流版での緑(14 件)は 2.2 節の条件で、#188 の枝の修正を含む合流版で確かめる。新しい赤が 0 件であること |
| 4 | authz の route 登録。**2 段に分ける**(反映3。レビュー P2-2)。**1 段目 = 作者の commit**: `scripts/check_authz_catalog.py`・`tests/test_check_authz_catalog.py`・計画書の provenance 行。route-registry とその lock の**候補値は cache へ出すだけ**で、repo の JSON は書かない。**2 段目 = root の commit**: `contracts/authz/route-registry.json` とその lock(checker が要求した場合だけ http-route-matrix とその lock)。2 段目の commit の件名のステップ記法は、root が設計書 6.1 の文法に従って決める | **完了条件は root の 2 段目の commit の後に測る**。**1 段目だけの時点の一時の赤**: `test_preparing_read_registered_route_matches_real_gets` は、3.2 節のとおり `games:read` の provenance を「旧 2 件を先頭に保ち、後ろに新規を足した完全一致」へ書き換えるので、registry に新しい provenance が入る前(1 段目の後・2 段目の前)は**赤になる**。registry の新 provenance を読む正例の試験も同じ。これは意図した一時の赤で、ステップ 0 の既知の赤には足さず、ID と E 行を「ステップ 4 1 段目の一時の赤」として別に記録し、2 段目の後に 0 件になることを確かめる。**2 段目の後の到達できる条件**: 変異拒否の試験(`tests/test_check_authz_catalog.py` に足したもの)がすべて赤を返し、正例が緑。preparing の provenance 2 件が先頭のまま保たれる。`test_preparing_read_registered_route_matches_real_gets` が緑。`tests/test_check_authz_catalog.py` の赤は、ステップ 0 の 4 件のままで新しい赤が 0 件。`check_authz_catalog.py` の出力が、ステップ 0 の記録と全文一致する(exit 1・oracle input blob の不一致。route-registry の反映後は同じメッセージで blob だけが違う)こと。参考として `--skip-oracle` で exit 0 かつ routes が 51 のままであること(**暫定の補助判定。正式な合格ではない**)。**判定保留(基線修復後に測る)**: 通常の `check_authz_catalog.py` が exit 0 で、routes が 51 のまま変わらないこと。oracle seal の再封印は root の作業で、U13 の route-registry 反映(2 段目)の後に行う |
| 5 | owned PG による受入: `backend/tests/db/test_started_game_read_http.py` | 7 節の DB 試験がすべて合格する(専用の owned Postgres。共有 DB には接続しない)。**H8 の必須プローブ(READ ONLY の TX で FOR UPDATE が拒否されること)を 1 回実行し、結果を `docs/features/mvp-started-read-http/plan.md` の見直し条件に記録する**(7.1 節 H8。主担当判断)。repository-contract・base-allowlist・runtime-authz の diff が 0 であることを実測する(`git diff` による機械的な確認。ゲートの合格とは別) |
| 6 | frontend: `startedGame.ts` と spec | Vitest、eslint、vue-tsc が合格する |

- 1 と 3 は試験と同じ commit に入れる(NFR-019)。
- **完了条件の読み方(反映2)**: 「到達できる条件」は、基線が赤のままでも測れる。「判定保留」は、**基線修復(2.1 節。root の別単位)の後に同じコマンドを再実行して、初めて合否を言える**。保留の項目は、PR の作成と統合の前に必ず再実行する条件にする(6 節の前提条件)。保留の間に、これらを合格と書かない。
- **判定保留の比較点(反映3。レビュー P2-1)**: **基線修復の後、修復済みの基線(U13 なし)で、ステップ 0 の ① `check_tenant_boundary_bypass.py` と ② `check_authz_catalog.py` を再記録し、それを判定保留の比較点にする**。U13 を載せた版の結果を、この比較点と比べる。**TB の差分は、検出の path 単位で U13 由来かを判定する**(検出行の `path:行 TBxxx symbol` を、比較点にあるものと、U13 の変更ファイルが出したものに分ける。比較点にあり U13 の path ではない検出は、U13 由来ではない)。ステップ 0 で記録した、基線修復前の出力(契約エラーで止まる全文)は、修復前の比較点であり、判定保留の項目の比較点には使わない。
- **既知の赤の固定**: ステップ 0 の記録を正とし、各ステップの後に同じ試験を同じ環境で走らせ、赤の ID の集合と E 行が記録と一致し、差が新しい赤 0 件であることを確かめる。ID の差分だけでは新しい原因を見逃すので、E 行と check_* の出力も前回と比べる(memory known-failures-mask-new-causes)。
- **ステップ 4 の正式 JSON は root だけが書く**。作者は候補の値を cache に出し、root が反映する(前例: mvp-game-start-connection plan.md:428)。

---

## 6. コア登録と 7.7

**前提条件(反映2。レビュー P1-1)**
- **基線修復は root の作業で、U13 の範囲外**(2.1 節の 3 点: WB の受理・#188 の受理・oracle seal の再封印)。
- U13 のステップ 0〜6 は、基線が赤のままでも、「到達できる条件」と「既知の赤の固定」(5 節)で進められる。**ただし、判定保留の項目(G-TB の TB 検出が増えないこと、G-AZ が exit 0 で routes 51)は、基線修復が済んだ版で再実行して合格するまで、PR の作成・統合へ進まない。**
- 基線修復が済むまで、U13 の作者は「TB002 が通る」「routes が 51 のまま」を事実として書かない。

**コア登録**
- **`.claude/core-areas.json` は変えない**。3.1 節の表のとおり、新規 path はすべて既存の glob で捕捉される([事実] fnmatchcase で照合)。
- 前例: 「既 tenant-isolation がファイル全体を捕捉済み。重複帰属は許容であり必須ではないため、新 core 登録段階は追加しない」(mvp-game-start-connection plan.md:471)。
- 6.3 の規則①(不変条件を変え得るファイルを含める)は、glob による捕捉で満たしている。
- 意味の上では、組立器は game-state と recording-rights にも属する。これらへの重複登録は 6.3-⑤ の手続き(敵対レビュー+人間承認、AREA_PATH_ADDITIONS の差し替え、宣言 commit と JSON commit の 2 段)を要する。U13 の範囲には入れないことを推奨する。レビューで必須と判断された場合は、別ステップとして切り出す。

**7.7 受理(反映1で訂正。レビュー P1-1)**
- **WB 単独では不要の見込み**([推論])。U13 は WB 単独の版で次のいずれも動かさない。
  - tenant_boundary 系の凍結基準(repository-contract rev30、base-allowlist rev39、frozen-inputs、runtime-authz rev24、census、db-api-inventory、tenant-context-allowlist、negative-fixtures、cache-invalidation)。新しい token も CAP も DB API symbol も追加しないため。
  - test_api_conventions が固定している `game_start.py` の承認 revision。
  - [事実] WB の frozen-inputs(rev 5)の external_files 4 本に、U13 の改修対象は含まれない。
- **#188 合流版では必要**。[事実] #188 の frozen-inputs(rev 6)は `backend/tests/test_api_conventions.py` と `tests/test_check_authz_catalog.py` を external_files に加え、全文 sha256 で凍結する。U13 はこの 2 ファイルを改修する(3.2 節)ので、合流版では frozen-inputs の移動(rev 6→7、history-snapshots の追加、単一受理 = 7.7)が要る。詳細・順序の注意は 2 節。
  - **root が #188 の受理と同じ経路で 1 回だけ行う**。U13 の作者・ステップは、frozen-inputs・history-snapshots・baseline_control を書かない。
  - この 7.7 は、U13 の統合の完了条件に含める(2 節の受入の扱い)。
  - 検出の注意: ローカル既定(不変量モード)では出ない。PR モード(CI)で出る。したがって push の前に、2 親の merge を作って再現する(下記)。
- authz の route-registry と http-route-matrix の lock は decision lock(asset_digest と aggregate_decision_digest)で、`baseline_control` も history も持たない([事実] check_authz_catalog.py に frozen_history・baseline_control の参照は無い)。これらは上の frozen-inputs とは別機構。
- **条件**: 次のいずれかが実測で必要になった場合も、その時点で U13 を止めて root に戻す。7.7 の記録は root が単一受理で作る。
  - 基線修復の後に、ステップ 2・5 の再実行で checker が base-allowlist・repository-contract・db-api-inventory への追加を要求した(基線が赤の間は、checker が要求を出す前に止まる)
  - game_start.py を変える必要が生じた
  - TB002 が赤になり、3.1 節の退避先でも解消しない
- 凍結履歴の PR モード検査は CI でしか走らない。このため push の前に、2 親の merge を作って再現する(memory frozen-history-pr-mode-only-on-ci)。**この再現は、WB 単独の merge と、#188 合流版の merge の両方で行う**(後者で rev 6 の射影変化が出ることを予期して、root が 7.7 を先に済ませる)。

---

## 7. 試験一覧

### 7.1 owned PG と実 HTTP(`backend/tests/db/test_started_game_read_http.py`)

- **fixture**: 既存の `TestInitialGameStartHttpOwned` が使う owned 3PG・実 worker・実 app 容器を委譲で使う(test_api_auth_exit_entry.py:849-900 と同じ委譲の形)。共有 DB(pitchlog-db-1)には接続しない。終了後に容器と volume が 0 であることを確認する。
- **「作成」の扱い**: 製品の HTTP に作成 route は無い。このため、試合の作成は fixture が admin 接続で preparing 試合を作る形で代える。**「作成」を HTTP 経路の証拠とは呼ばない**。

| ID | 内容 | 合格条件 |
| --- | --- | --- |
| H1 | 作成(fixture)→ 実 `POST /start` → `GET /games/{id}/started` | 200。status=in_progress。started_at・lineup id 2 件・`current_d4` が開始応答と byte 一致する。state は balls・strikes・outs が 0、inning 1 top。名簿の射影は開始時の入力と一致する。`cache-control: no-store`、match ack、challenge の返送がある。**あわせて、GET 1 回の所要時間(games・世代行の FOR UPDATE を保持する区間を含む、route 入口から応答まで)を、10 回の反復で計測して試験の出力に記録する**(7.3 節 R1。しきい値での合否にはしない。値は申し送りの根拠にする) |
| H2 | 別 tenant の in_progress 試合、不存在の UUID、hidden、trashed、**import 済みの in_progress(import_batch_id 非 NULL。4.1 節②の NotVisible 条件)**、preparing、finished(fixture で作る)に対して `/started` を呼ぶ | すべて 404。`len(set(bodies)) == 1`。さらに、preparing route の 404 本文と同じ bytes である。match header は無い |
| H3 | preparing との相互排他 | 開始前: `/games/{id}` が 200、`/started` が 404。開始後: `/games/{id}` が 404、`/started` が 200。既存の :758-775 は変更せずに合格する |
| H4 | 記録権情報の非開示 | 200 本文の key 集合が DTO 定義と完全一致する。本文の bytes に次が含まれない: holder_device の UUID 文字列、device_id、device_credential の原値、recording_right_proof、recovery_generation の値、`watermark`・`prefix` の key。H2 の 404 本文に d4 が含まれない |
| H5 | 記録ありの扱い | admin が event_slot を 1 件入れた後に GET すると、409 と固定の本文が返る。値は含まない |
| H6 | 破損時の扱い | 次の各ケースで 503 と固定の本文。本文と log に SQL の語・DB の値が出ない。(a) lineup を 1 件欠かした (b) 世代が revoked (c) **世代が retired(retired_at が非 NULL)** (d) **現在の世代が非normalのmigration種別(7.3 節 R2 の宣言どおり 503)** (e) 世代が 0 行。**書込みが無いこと**を、ケースの前後で games・世代・event_slot・event・PlayRow の行 digest(admin 接続)が一致することで確かめる。Corrupt は `with` の中の例外として抜け、`except Exception` で 503 に写る(4.1・4.2 節)。「rollback した」とは書かず、観測するのは書込み 0 と 503 だけとする |
| H7 | 認証と C2 の順序 | 未認証は 401。Expected-Tenant が別 tenant、または Challenge が不正なら 404。どちらの場合も games への SQL は 0 件 |
| H8 | app ロールでの lock 読取 | H1 の成功そのものが、app ロールで FOR UPDATE の lock 読取が通ることの実証になる。42501 が出た場合は、DB grant の不足として root に戻し、U13 では grant を作らない |

H8 の補足(**反映3で「任意」から「必須の 1 回プローブ」へ改めた。主担当判断〔PO 委任〕。レビュー P2-4**):
- A-2 は「REPEATABLE READ READ ONLY を退ける根拠(PG は READ ONLY の TX で FOR UPDATE を拒否する)は推論なので、owned PG で 1 回確認してから記録する」としている(DECISIONS.md :39。実 PG では未確認のまま :403 に残っている)。**この確認を H8 に同居させ、必須にする。**
- **内容**: owned PG の app ロールの接続で、`REPEATABLE READ READ ONLY` の TX を開き、games 行の lock 読取(`FOR UPDATE`)を 1 回試みて、**拒否されることを観測する**。観測するのは、拒否されたこと、その SQLSTATE と文言(PG の既知の挙動として `25006 read_only_sql_transaction` の見込み。[推論]、確認前)、TX が使えなくなる前に何も書かれていないこと。
- **記録**: 結果を `docs/features/mvp-started-read-http/plan.md` の見直し条件に追記する。拒否されなかった場合は A-2 の退ける根拠が崩れるので、U13 を止めて主担当へ戻す(READ ONLY の方式を再判断する)。
- 生の SQL をどの層で発行するか(試験の中で直接か、admin 接続の補助関数か)は、tenant-boundary 系の検査が `backend/tests/` を見るかを基線修復後に確かめて決める([推論]。見る場合は、`tests/db/` の補助関数に閉じる)。製品コードの read 経路は READ ONLY にしない。
- CRITIC C9 が残した確認(app ロールの lock 権限)は、H1 の成功で閉じる。

### 7.2 非 DB

| 試験 | 内容 |
| --- | --- |
| `test_d4_reference_boundary.py` | ステップ 1 の完了条件 |
| `test_started_read_repository.py` | ステップ 2 の完了条件(⑥⑦⑧を含む。N2 との述語の同一性) |
| `test_api_started_game.py` | 次の 5 点。① 新 route が TenantMatchedRoute を使い、`_MATCH_OPERATIONS` に入っている ② DTO の key 集合 ③ 404 の本文が preparing と同一 ④ 409・503 の本文が固定 ⑤ `create_app` が Node を起動しない(test_api_app.py:229-236 と同じ監視) |
| test_api_app.py・test_api_conventions.py(3 箇所)・test_roster_self_team_read.py | 列挙の更新(`test_roster_self_team_read.py` は期待集合へ `started_game_detail` の 1 件だけを足す。initial_* 3 件は #188 の枝で足す。3.2 節・2.2 節) |
| tests/test_check_authz_catalog.py | ステップ 4 の正例と変異 |
| frontend `startedGame.spec.ts` | 次の 4 点。① path と tenantBound ② 余剰 key(holder_device を入れたもの)と未知の read_kind を拒否 ③ UUID 不一致 ④ 404・409 の写像 |

**検査範囲**: 影響範囲だけを回す。是正の後と受理の前には、非 DB の全件(約 1 分)を必ず回す(memory test-scope-preference)。

---

## 7.3 危険と見直し条件

- **R1 ロック中の Node 起動**([推論]。レビュー P2-3 を反映)
  - N2 は呼出しのたびに `evaluate_initial_game_roster` を実行し、`open_domain_host()` が Node プロセスを起動する(domainrt/host.py:210-244)。
  - この間、games 行と世代行を FOR UPDATE で保持し続ける。
  - **この route は、同 tenant の認証済み利用者なら誰でも呼べる**(端末限定ではない)。呼出しが続くと、同じ試合の sync writer・start worker を待たせる([事実] route は C2 を通った同 tenant の利用者に開いている。待たせる範囲は作者は実行していない)。
  - 0 球の 1 試合 1 端末なら許容できる見込み。ただし、閲覧者のポーリングへ流用する前に、ロックしない方式を再判断する(A-2 の見直し条件。REQ:448,853,874)。
  - **対処(反映1)**: ① H1 で GET 1 回のロック保持を含む所要時間を計測して記録する(7.1 節)。② **U18 への申し送り**: 「開始直後の 1 回読取だけを行う。ポーリング・定期再取得・複数タブからの連打に使わない」。この route を閲覧者向けの更新に流用する場合は、MVP-D の条件付き票(DECISIONS.md の D1: ロック読取を閲覧者のポーリングへ流用する場合)を起票する。③ API プロセスに製品の Node と artifact が要るので、配備の前提に加える。
- **R2 非normal世代**
  - 現在の世代が非normalのmigration種別のとき、N2 は拒否するので、U13 では 503 になる。
  - 緊急の引継ぎは MVP 外(LEAD progress.md:112)なので、範囲外として記録する。
- **R3 409 の意味**
  - U14 が入るまでは、1 球目を保存した試合を再取得できない。
  - これは A-11 の「2 球目は範囲外」と同じく、一時的な非成功として表に出す。FR-008 の復元完了は主張しない。

---

## 8. 記録後(U14)へ広げるときの拡張点

1. **組立器の Recorded 分岐**
   - ④の分岐で、tsk544 単位 5 の候補 reader(`repositories/recorded_snapshot.py`。plan.md:515-520)を、**同じ handle・同じロック順**で呼ぶ。A-4④に従い、整合方式は A-2 に揃える。
   - N2 は引き続き「記録ありは拒否」のまま残す(plan.md:375)。
2. **DTO**
   - `read_kind` を判別子にした union に `"recorded"` を足す。after・scoreboard・history・23flags・T2・PlayRow の一覧を加える。
   - 既存の `"initial"` の形は変えない。frontend は fail-closed なので、U14 では frontend の検証器も同じ commit で更新する。
3. **HTTP**
   - 409 の分岐を 200 に置き換える。H5 は「200 で recorded が返る」に書き換え、409 の固定は削除する。
   - 404・503 の写像と C2 は変えない。
4. **authz 登録**
   - `_STARTED_READ_HTTP_BINDINGS` の同じ行に、記録後の reader が使う token と CAP を末尾追記する。論理 route は `games:read` のまま。
   - 新しい token を足す場合は、repository-contract・operation_registry・base-allowlist の改訂と、7.7 が必要になる見込み。この点で U13 と性質が変わる。
5. **正しさの担保と開示範囲**
   - A-4 の方式(2): 正式 artifact で再評価し、保存済みの値と全値一致を確かめる。artifact の identity が一致しない場合は暫定で fail-closed にする(MVP-D08 は未回答)。
   - D3(confirmed_watermark)を返すかどうかは O1 へ移るときに決める(A-11)。U14 でも既定では返さない。
6. **NFR-005**: 記録後の読取は上限付きにし、DB 側で絞り込む(WHERE と LIMIT)。全件を読み込む方式にはしない。

---

## 9. 主担当が計画承認時に確定する点

1. 記録ありのときの応答を 409(推奨)にするか、503 にするか。
2. route 名 `/games/{game_id}/started` と operation_id `started_game_detail`。A-1 は名前を委任内で決めるとしている。
3. d4 符号化の置き場所を `sync/d4_reference.py` にするか。TB002 の owner path に入り、既存の glob で捕捉される。代替案は recording_rights 配下だが、glob の外になるため core 登録が必要になる。
4. game-state と recording-rights への重複登録を見送る判断(6 節)。
5. U14 で `"recorded"` を足すまでの間、frontend の U18 が 409 をどう表示するか。U18 の受入条件へ申し送る。あわせて、R1 の申し送り(開始直後の 1 回読取のみ。ポーリング禁止)を U18 の受入条件へ入れる。
6. **A-3 の「世代が無ければ null を返し、画面は unknown にする」を、U13 では採らず 503 とする**(反映1。レビュー P2-2)。理由: N2 が世代を必須とし、世代が 0 行・不一致・非normal（migration）・revoked・retired のとき `StartedSnapshotUnavailable` で拒否する(1 節)。N2 を改変しない(A-2)ので、200 で null を返す経路が作れない。DTO の `current_d4` は型として `str | None` を残すが、U13 の 200 応答では常に `str` で、null は返さない。null 返却の経路(世代が無い開始済み試合を unknown で表示する)は、U14/O1 で N2 の扱いと合わせて再判断する。A-3 からの逸脱なので、主担当の確定点に挙げる。
7. 反映1で変わった確定点: ① 7.7 は WB 単独では不要、#188 合流版では root が 1 回だけ行う(6 節) ② 組立器①〜③が N2 の判定を二重化することの容認(4.1 節)。(反映1の「期待集合を 14 件にする」は反映2で改め、下の 8 以降に置き換えた。)
8. **#188 の対象版**(反映2。レビュー P2-B): 合流版の 7.7 で受理する #188 が、GitHub の PR head 72f4118a、ローカル候補 f0a8ce4e、組立が取り込んだ 1f8052fb のどれかを、root に確認する。f0a8ce4e は未 push。
9. **TB002 の予防**(反映2): 基線のゲートが止まるので、`snapshot.generation` の属性参照が通るかは測れない。退避先(`.generation` を読む箇所を `sync/d4_reference.py` 側へ寄せる。3.1 節)を最初から採るか、基線修復後に実測してから決めるか。
10. **initial_* 3 件の追加を #188 の枝に依頼すること**(反映2。2.2 節の主担当判断): 依頼先は #188 の担当。U13 の完了条件のうち「合流版で `test_roster_self_team_read.py` が緑(14 件)」は、この修正が入るまで満たせない。
11. **基線修復の担当と順序**(反映2。2.1 節): WB の受理・#188 の受理・oracle seal の再封印を、root がどの順で行うか。再封印は U13 のステップ 4(route-registry の反映)の後に 1 回で済ませるのが効率的([推論])。
12. **共有 DB の確認**(反映2): 前述の作者の過失(環境変数が共有 DB を指したまま backend の試験を 1 回走らせた)について、root が `pitchlog_test_role` 等の残骸の有無を確認する。
13. **反映3の主担当判断(PO 委任。人間の承認ではない)**: ① 判定保留は、修復済み基線(U13 なし)の ①② の再記録を比較点にし、TB の差分は検出の path 単位で U13 由来かを判定する(5 節)② 正式統合の条件に判定保留 2 項目の合格を含める(2 節)③ ステップ 4 は作者の commit と root の commit の 2 段にし、完了条件は root の commit の後に測る(5 節)④ #188 は initial_* 3 件をリテラルの末尾へ追記する(2.2 節)⑤ H8 の READ ONLY プローブは必須の 1 回(7.1 節)。

**PO 採用 D09〜D13(2026-10-28)との関係**(原典: `decision-sheet.md` 117-125 行「PO採用記録(2026-10-28、D09〜D13)」。作者が全文を読んだ)
- U13 は read だけを扱い、端末文脈・lease・端末資格・座標・端末キュー・語彙投入のいずれも使わない。したがって D09〜D13 は U13 を止めず、解除もしない([推論])。U13 の待ちを解除したのは、主担当裁定の A-1・A-2・A-3・A-11 である。
- D09=α: 判断票が「HTTP入口」を影響先に挙げるのは、端末文脈を必須とする**書込み側**の入口である。U13 の `GET /games/{game_id}/started` は C2(Expected-Tenant・Challenge)だけを通し、device credential を使わず、writer 結合にも入らない([推論])。
- D10=A: 端末資格不成立は B5 で拒否する話であり、U13 の route は端末資格の成否を分岐に使わない。404 の非開示(H2・H7)は D10 の「既存の情報非開示との整合」と矛盾しない([推論])。
- D11=A・D12=A・D13=A: 座標の整数化・durableQueue の版・打撃結果の初期語彙投入は、U13 の 200 応答(0 球の初期状態)が返す値に関与しない([推論])。ただし D12 により、frontend の `startedGame.ts` を端末キュー(v4)へ載せる配線は U18・U20 の範囲で、U13 は client 関数だけを置く。
- いずれも PO 本人の逐行確認・実 DB 確認・独立レビュー・所有側受理の完了を意味しない。この計画候補は承認済みではない。

2026-10-28、PO委任によるCodex主担当判断。U13候補は非作者review0a1b4355b629673ae570506099cb86aa10d7e9f1cd652a654159defc372503b4 追加指摘0・独立backend128/authz35成功を根拠にstep1〜3/step4作者段を限定採用。別branch feature/mvp-started-read-httpをef921539起点で維持し、1step1commit。step4 root JSON/lockを別commit、基線修復/製品DB/step5/6は未完として保持。provenance根拠行は不変。

2026-10-28、step1〜4両段の実取込HEAD d4a9d7ecを非作者followup7a0cad94ff1dc79c59fcce6e3fbc8289aacdcf44ea68d0a9015290f2f2a18cb1 残0で確認。候補14path不変、plan限定metadata・既ABのchecker2関数・U13 AST17・root生成JSON/lock全byteを個別照合。独立backend128/authz37成功、root実WT31/81/16/authz37成功。step4を限定採用し保存するが、基線gate/製品DB/step5/6と記録後U14は未完。新たな利用者操作の実画面実証ではない。

2026-10-28、PO委任によるCodex主担当判断。step5原典照合でRecordingGeneration.kindの実CHECKはnormal/migrationのみ、N2はkind!=normalを拒否しrecovery種別は存在しないと確認。H6(d)/R2/確定点6のrecovery表記を実在する非normal migrationの503対向へ技術的訂正。recovery_generationは別のepoch値で、新kindや拒否条件を追加せずN2/既CHECKを変更しない。原文のrecovery種別ケースは成立不能と記録し、migration対向をrecovery実証済みと読み替えない。
