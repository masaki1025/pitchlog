---
feature: adr003-stage2-runtime
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-14・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f593b75e687817085ddefcaeff3687b
branch: feature/adr003-stage2-runtime
created: 2026-10-10
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 4          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: ADR-003 段階 2 の実行経路(TSK-538)

## 1. 背景・目的

- **Notion**: https://app.notion.com/p/3f593b75e687817085ddefcaeff3687b (TSK-538 — TSK-510 の PO 裁定 2026-10-10 で起票。実行経路と段階 2 受取タスクを 1 本に統合)
- **NFR**: NFR-018(ドメイン計算の単一実装 — 要件書 `docs/requirements/requirements-pitchlog-2026-07-22.md`)・NFR-019((a) 一致性テスト)。方式は [ADR-003](../../adr/ADR-003-domain-calc-method.md) D-14(D-2: TS 正本 → 同一 JS artifact を QuickJS / 常駐 Node で実行)
- **なぜ**: U-X1 状況計算核の着手条件 P-5(`docs/features/ux1-state-calc/design.md` §4)。段階 2 の実行経路を持つタスクが無く、付録E 引き渡し契約の受け手も未定(`receiverTaskId: null`)だった
- **段階の境界**(PO 裁定 2026-10-10): **発効前は実行基盤まで / 対象計算の追加は発効後**。D-2 は v0.5 で approved だが発効日の記録が無く、D-1 が現行(`ADR-003:671`・`:681-682`)。本タスクは**対象計算のコードを追加しない**
- 調査: [research.md](research.md) / 詳細設計: [design.md](design.md)(山田さんの裁定 D1〜D9 は design.md §1)

## 2. スコープ

### やること

- **D-2 の実行基盤**(合成フィクスチャで検証): エンジン試験と選定・TS 正本の足場・AST 検査器(部分集合・禁止構文・型付きの `number` 禁止)・再現ビルドの単一 IIFE artifact・サーバー実行ホストと FastAPI 起動時検査・クライアントの読み込み・SQL 生成経路の枠・runner の接続(caseFieldMapping の読み込み層)・descriptorParity(S03)・BOOT の意味スナップショット収集器・CI
- **引き渡し契約の受け手**: schema v1 の改訂(D3)・`receiverTaskId` を TSK-538 に・runner の revision の確定・古い記述の是正
- **S34 の送り先を TSK-540 へ**(記録 4 箇所)
- **未解消レポートの段階 2 項目の割り当て**((b) 27 件 — `receiverDoD` 6)
- **契約 9 件の解決**(S15・S16・S17・S18・S19・S20・S21・S27・S28)— うち S15〜S18 は ADR-003 D-8・D-11 と要件書 E-1(`HistoryEffect`)の改訂(/finalize-doc)、S19 は descriptor の軸追加。**S20 は終了判定側だけを解決し、状況判定側(サヨナラ時の得点上限)は TSK-544 へ送る**(ゲート ⑤ の PO 裁定 2026-10-14)
- 新しい置き場のコア領域への宣言(D4)

### やらないこと

- **対象計算(NFR-018 の 13 対象)のコードを追加すること**・`backend/domain/manifest.json` を置くこと(発効後 — U-X1 の対象計算の PR)
- **発効条件 (i)〜(iv) の条文化と要件書の規範改訂**(TSK-541)。SQL 生成経路は枠までで、必須集計の変換可否は (iv) の入力として渡す
- `receiverDoD` 1〜5 の残り・(a) S01・S04・S29・S33 の残り・(b) S08・S09(D1・D9 — U-X1 T1・T2 の PR へ。送り先の表は design.md §6)
- (b) の残り 16 件の**解決**(割り当てだけ)
- S34 の**中身の是正**(TSK-540)
- 要件書の改訂(D6・D7 で回避)— **ただし付録E-1 の `HistoryEffect` の新設(v2.14)を除く**(ゲート ⑤ の PO 裁定)
- **FR-040 採用時の状態補正の補正先の分割**(ADR-003 v0.7 D-11)— FR-040 は未採用(Should)のため本タスクでは行わない。採用時は FR-040 の採否を扱うタスクが、条件付きメンバーとして分割と受理記録を同時に加える(未解消レポート S31 の送り先 TSK-544 へ申し送る)
- **S20 の状況判定側(サヨナラ時の得点上限)**— TSK-544 へ送った(ゲート ⑤ の PO 裁定)
- ガード是正(D-14-j・`ADR-003:837`)— 所有者不明として PO へ上げる

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/adr/ADR-003-domain-calc-method.md` | **D-8 の改訂**(targetKind に「対象なし」・XC-09 を「シナリオ長」へ・undoRows の stateEffect と guaranteeMode — S17・S18)。変更履歴に追記 | **/finalize-doc**(敵対レビュー + 人間承認 — ステップ 27 の後) |
| `contracts/state-transition/` の入力軸 descriptor | **分割**(payload と履歴軸 — S15・S16)・**成立段数の軸の追加**(S19)・凍結基準 `gameEndAxisFields` の受理記録 | **確定ゲート**(/finalize-doc — ステップ 26・27) |
| `docs/development/github-setup.md` | CI ジョブの 3 分類の追随(ステップ 15) | PR レビュー |
| `docs/README.md`(索引) | ADR-003 の版の現行化 | PR レビュー |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **付録E-1 の `StateEffect` の履歴文脈の型を `HistoryEffect` へ**(v2.14 — ゲート ⑤ で approved・PO 裁定 2026-10-14。undo が履歴を pop する行を `FieldEffect` で書けないことが確定ゲート 2 回目で判明したため。D6・D7 で避けた E-1 の列の追加とは別) | **/finalize-doc**(ADR-003 v0.7 と一括検証 — ゲート ⑤) |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし** | — |

**正本体系外だが同一 PR で更新するもの**: `backend/Dockerfile`・`.dockerignore`(新設 — 本番の配布定義。ゲート ② の後に山田さんが追加を指示 2026-10-11)・`contracts/state-transition/`(handoff と schema・状態遷移契約・終了判定契約・被覆宣言・台帳 schema・gap register・fixture)・`.claude/core-areas.json`・`scripts/core_guard.py`・`docs/features/appendix-e-golden-vectors/{unresolved-report,design}.md`・`backend/`・`frontend/`・`tests/`・`.github/workflows/ci.yml`・root `pyproject.toml` と `uv.lock`。

## 4. 実装方針

**重さ分類 = コア領域**。`contracts/state-transition/*` は game-state × sync-protocol(`.claude/core-areas.json:209`・`:326`)、`tests/domain/*` と `backend/src/pitchlog/api/app.py` もコア。計画書は敵対レビュー、PR は敵対レビュー + 人間の逐行確認。

詳細設計は [design.md](design.md)。要点:

- **実行基盤の構成**(§2): TS 正本 → esbuild の単一 IIFE(`globalThis` 公開口・JSON 文字列 in/out)→ ブラウザは public から無変換配信 / サーバーはリテラルパスと hash 照合でエンジンへロード。**Python との境界は十進文字列**(D-14-e)
- **manifest は置かない**(§2): 置くと consistency が落ち、schema と段階 2 判定器が合成計算を受け付けない。置くのは U-X1 の最初の対象計算の PR。本タスクは前提の収集器を用意する
- **エンジン**(§4): quickjs-ng の 5 条件をすべて満たせば QuickJS、欠ければ常駐 Node。試験の後に PO が承認する
- **条文の要求と担保の対応**(§3)・**契約 9 件の順序**(§5)・**送り先の表**(§6)・**コア領域の宣言**(§7)・**リスク**(§8)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**ステップ外のゲート**(人間が行う — ステップ番号に数えない):

- ① 計画承認と同時に、**技術スタックの追加**(QuickJS または Node・esbuild — 要件書 `:1059`)と **artifact の public 配置**の了承を得る
- ② ステップ 1 の後、**PO がエンジンを承認**する
- ③ ステップ 16 と 17 の間で、**#116 のマージを待って develop を取り込む**
- ④ ステップ 21 の前に、**U-X1 T1・T2 の Notion カードを起票**する(送り先を実在させる)
- ⑤ ステップ 27 の後に **/finalize-doc**(ADR-003 D-8・descriptor・サヨナラ時の得点上限の表現 — 敵対レビュー + 人間承認)。**投入前に TSK-541 と順序を合わせる**(design.md §5)
- ⑥ ステップ 33 の後、**Claude が照合し PO が承認**する(独立に確認した期待値 — `ADR-003:334`)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **エンジン試験**: quickjs-ng と Node で、合成の artifact を使う characterization テストを `tests/domain/runtime/` に置く | design.md §4 の 5 条件それぞれの結果がテストで固定され、費用の実測(ロード時間・1 呼び出しの時間・メモリ)が design.md に記録されている。試験が緑 |
| 2 | **依存の追加と backend の配布定義**(ゲート ② で常駐 Node に決定): esbuild を `frontend/package.json`・`pnpm-lock.yaml` に版固定で追加。**`backend/Dockerfile` を新設**し、backend の実行イメージに Node 24.16.0(`mise.toml` と同じ版)を同梱する。基底イメージは x86_64・aarch64 の両方を持つものを digest で固定。`.dockerignore` で `.env`・シークレットを除外(NFR-014) | `pnpm install --frozen-lockfile` が緑。**Dockerfile の静的試験**(`tests/`)が緑: 同梱する Node の版が `mise.toml` と一致する・基底イメージが digest で固定されている・`.env` を COPY しない(`.dockerignore` を含む)。**開発機(aarch64)で `docker build` が通り、イメージ内の `node --version` が 24.16.0**。x86_64 の build 確認はステップ 15 の CI(x86_64 ランナー)で行う |
| 3 | **TS 正本の足場**: `frontend/src/domain/` に公開口と十進文字列の codec、および**疎通用の操作**(入力をそのまま返す等。対象計算ではない — ステップ 15 の配布物の起動確認で使う)。その範囲に ESLint(no-eval・no-implied-eval・no-new-func・動的 import 禁止)と depcruise の規則 | `vue-tsc --noEmit`・`eslint`・depcruise が緑。`globalThis` を経由してラッパー強制を迂回する負例が赤 |
| 4 | **AST 検査器 a**: TS 正本の構文の部分集合を宣言で閉じ、禁止構文(eval 系・動的 import・非リテラル require・宣言外のホスト関数)を拒否 | 規則ごとの負例 fixture がすべて赤。未知の構文ノードは fail-closed。合成の正例が緑 |
| 5 | **AST 検査器 b**: 型付き検査(TypeScript の型チェッカー)で `number` の使用・入力側の文字列 → `number` 変換・`Math.round`/`Math.floor` による丸めを拒否(D-14-e (a)(b)(c)) | 3 種それぞれの負例(推論で `number` が入り込むものを含む)が赤。BigInt だけの合成の正例が緑 |
| 6 | **再現ビルド**: esbuild で単一 IIFE を作るビルドスクリプトと artifact のコミット(SHA-256 を宣言)。**単一ファイル方式**とし、実行時の別モジュール読み込みを持たない | クリーンな 2 回のビルドで SHA-256 が一致。artifact に**リテラル・非リテラルを問わず** `require`・`import`・`import(` が残っていないことを字句検査で固定し、**リテラルな読み込みが残る負例**が赤(`ADR-003:752-756` の到達モジュールの閉包) |
| 7 | **サーバー実行ホスト** `backend/src/pitchlog/domainrt/`: リテラルパスで artifact を読み、hash 照合 → **選定エンジン**へロード。上限・ホスト関数の宣言・十進文字列の境界。配布物への同梱方法を決めて design.md に追記 | **製品ホスト経由で**、hash 不一致・timeout・メモリ超過、およびゲストの **`eval`・`Function` 構築・動的 import の 3 経路それぞれ**が fail-closed になる試験が緑(`ADR-003:748-749`) |
| 8 | **FastAPI の起動時検査**(`backend/src/pitchlog/api/app.py`) | artifact が無い・hash が合わないとき `create_app` が例外を出す試験が緑。既存の backend テストが緑 |
| 9 | **クライアントの読み込み**: artifact の public 配置と `<script src>`、`collect_entrypoints_fe` と閉域検査の追随、Vitest は `vm` で同一 artifact を読む | 収集器が static-public 入口を判定可能として列挙する。build 出力の artifact の SHA-256 が宣言値と一致。Vitest の読み込み試験が緑 |
| 10 | **SQL 生成経路の枠**: 部分集合から SQL を生成し、変換できない構文は fail-closed(手書き SQL を書けない構造)。**集計((β)①〜⑤ 型)と行単位の分類式((β)⑦ 型 — `ADR-003:798-802`)の両方** | 合成の集計と合成の行単位分類がそれぞれ SQL に変換でき、DB で期待値を返す。範囲外の構文・判定不能の負例が、集計と分類の両方で赤 |
| 11 | **runner a**: 契約のトップレベル読み込み・版検査・`caseFieldMapping`(`/decision` → `/expected`)の読み込み層を pytest 側と Vitest 側の両方に | 2 契約の全 case を写像できる(件数を検査)。`cases[]` の直読・版の不一致・未知 field は赤 |
| 12 | **runner b**: 選定エンジンの adapter(`GeneratedNormalizer`・`CalculationAdapter`)と Vitest の adapter。R-b の TS runner を含む | 合成ベクタが両経路で緑。同一入力に対する両経路の出力がバイト一致 |
| 13 | **descriptorParity(S03)**: 全 projectionRules で descriptor と派生 schema の射影を照合し、`backend/domain/history-depth.json` から `D` の実値を解決 | exact-set・値域・digest の照合が緑。値をずらした負例が赤。判定不能は fail |
| 14 | **BOOT の意味スナップショット収集器**(6 集合)と **`boot/report.py` への接続**: manifest が在るときに例外で落ちるのではなく、収集器の結果で段階 2 判定と未解消レポートを出す | 合成 manifest(一時ディレクトリ)から 6 集合を収集できる。観測できない集合は `None`(判定不能)。**manifest ありの一時リポジトリで `boot.report` が機械可読な未解消一覧を出す**試験が緑(要件書 `:962` BOOT-REPORT)。実リポジトリ(manifest なし)の `boot.report` と `--verify` が従来どおり緑 |
| 15 | **CI と凍結 corpus**(同じコミット): frontend ジョブに再現ビルドと hash 照合を足す(新しいジョブは作らない)・R-a のフィルタ拡張(適合ベクタ・ブリッジの変更で Vitest が走る)・harness でエンジン試験・**x86_64 ランナーでの `backend/Dockerfile` の build・イメージ内 `node --version` の確認・イメージの起動**(FastAPI の起動時検査〔ステップ 8〕が通り、常駐 Node 経由で artifact の疎通用の操作を呼べる)・`tests/test_ci_wiring.py` と `docs/development/github-setup.md` の追随・**`ci.yml` の変更に伴う凍結 corpus の受理記録**(`tests/fixtures/frozen-archive-cases/manifest.json:8-10`) | CI の全ジョブが緑。**起動したイメージで疎通用の操作の応答が期待値と一致**(frozen archive の試験 `tests/test_frozen_archive_case_runner.py:222-231` を含む)。`test_ci_wiring` が緑 |
| 16 | **`manifest.schema.json` の artifactKind enum に JS artifact を追加**(D-2 の生成物の種別)と schema テストの追随 | `tests/domain/` の manifest schema テストが緑。Calculation のプロパティ名は変えず、`boot-seal.sealed.json` の封印値が変わらない |
| 17 | **コア領域の宣言**: `AREA_PATH_ADDITIONS` を新しい paths(game-state と data-migration — design.md §7)に**置き換え**、`test_core_guard` を登録前後の両状態受理にする。S34 の `deferred_to` の新旧も両受理 | `test_core_guard` が登録前の状態で緑。#116 の U-F2 専用の表明が緑 |
| 18 | **登録**: `.claude/core-areas.json` の paths と S34 の `deferred_to`(TSK-540)、`unresolved-report.md:85`、`appendix-e-golden-vectors/design.md:1319` を同じコミットで変える(core_guard.py とテストは変えない) | core-guard が緑。`test_core_guard` が登録後の状態で緑 |
| 19 | **テストの絞り込み**: 新しい状態だけを受理し、新しい glob が実在ファイルに一致することも要求 | `test_core_guard` が緑 |
| 20 | **handoff の改訂 a**: schema v1 の `receiverTaskId` を `^TSK-[1-9][0-9]*$` に、値を `TSK-538` に。古い記述(`handoff:11`・`:147`・`:154`)の是正。`tests/test_consumer_handoff.py` の負例の書き換え | `test_consumer_handoff` が緑。`null` と不正な ID が赤 |
| 21 | **(b) の割り当て**: `unresolved-report.md` の第 3 列を実在する送り先へ(9 件は TSK-538、S08・S09 は U-X1 T1、ほか 16 件は design.md §6-2 の候補から実在するタスクへ。無いものは PO へ上げて起票してから) | 27 件すべてが Notion に実在するタスクを指す(ゲート ④ の後)。`tests/test_gap_register.py` が緑 |
| 22 | **S27**: 終了判定 schema の `decision` に X 表記の欄を足し、展開器を改修して 170 case を再生成 | 契約・被覆宣言・check 系スクリプト・関連テストが緑。handoff の artifacts digest を同じコミットで更新 |
| 23 | **S28**: 到達不可 2817 件の縮小(行の無い分岐・固定されない軸値の扱い) | 同上。縮小幅の固定値(`check_required_set_coverage.py`)を追随 |
| 24 | **S21**: DRAW-05 を operationRows `game-end-declaration` に結ぶ(D8) | 同上 |
| 25 | **S20(終了判定側)**: 台帳 schema の終了判定の役割を 5 つに(D7)、walk-off の行と case(終了の検知) | 同上。`check_gap_register.py` が緑。**サヨナラ時の得点値(状況判定側)は TSK-544 へ送った**(ゲート ⑤ の PO 裁定 2026-10-14 — 既存の列では有効得点の確定後に上限をかける順序を表せないため) |
| 26 | **S19**: descriptor に成立段数の軸・凍結基準 `gameEndAxisFields` の受理記録・COLD-09 の行と case | 同上。三点突合(`check_input_axes_three_way_parity.py`)が緑 |
| 27 | **正本改訂のゲート投入**: ADR-003 D-8 の改訂(targetKind に「対象なし」・XC-09 を「シナリオ長」へ・undoRows の stateEffect と guaranteeMode)と descriptor の分割(payload と履歴軸)に加え、**状況判定の規範行でサヨナラ時の得点上限を表す方法**(サヨナラ文脈の前提条件の軸と、得点上限の列 — 現行の `matrixRows` には得点値もサヨナラ文脈も表す列が無い `state_transition_contract_schema_v1.json:1151`)を in-review で起案(変更履歴に起案行) | docs-lint と文書の検査が緑。**この後ゲート ⑤** |
| 28 | **派生軸の仕組みと S19 の是正**(ADR-003 v0.7 D-11): descriptor schema に派生軸の属性(導出元の軸 ID・条文 ID)を入れ、**関数性**(導出元の**完全な入力値**が同じ case で派生値が異ならない — 軸のラベルでは判定しない)と**宣言された到達不可の除外**を検査する / ステップ 26 の `gameEnd.satisfiedColdTierCount` に属性を付け、**descriptor の `invalidBoundaryValues`(−1・17)を除き**、それから生成していた `validationErrors[]` の 2 件と連動する被覆・検査の期待値を保証範囲外の扱いへ直す | 契約系の検査・テストが緑。凍結基準の受理記録(D-12)。**負例が赤**: 導出元の属性の欠落 / 完全な入力値が同じで派生値だけ異なる case / 派生軸に不正境界値を置いた descriptor。digest を更新 |
| 29 | **履歴と結果の面の移行と S17**(ADR-003 v0.7 D-8・要件書 v2.14): 状況判定 schema に `HistoryEffect` と `operationResult` の `set`、`targetKind` に `"none"` を入れ、既存の操作行 7・undo 行 1 の `historyAndResult` を書き換える(**既存の空履歴の undo 行は `targetKind = "none"` へ** — S17)/ 2 列と 2 面の一対一対応(操作行は `pop` 禁止・undo 行は `push` 禁止)、**交差制約**(undo は `applied` ⇔ `pops = 1`・拒否された操作は `pushes = false`)と**対象なしの同値**(`"none"` ⇔ `nothing-to-undo` ⇔ 深さ 0 ⇔ `pops = 0`)の検査 / 展開器の **push の差分**: 状態欄・スコアボードは適用前後の比較面の変化前・変化後の値、**成績計上フラグは当該操作が出力した 23 値(前後の比較では作らない)**。確定プレイも同じ規則 | 契約系の検査・テストが緑。**負例が赤**: 列と面の不一致 / 操作行の `pop` / `applied` なのに `pops = 0` の undo / 拒否なのに `pushes = true` の操作行 / 対象なしの同値の片方だけ成り立つ行 / フラグを前後比較で作った差分。digest を更新 |
| 30 | **S18**: `D`+1 の liveness-only の行と case(`XC-09` — シナリオ長 `D`+1 = **取消可能な操作を `D`+1 件積んでから undo する構成**・対象あり)。比較は `applied` と**遷移後の履歴がちょうど 1 件少ない**こと | 同上。**負例が赤**: 2 件以上を失う undo / 拒否する実装 / シナリオ長 `D` 以下の行の `liveness-only` |
| 31 | **S16**: undo の 3 つの基礎シナリオ(履歴の先頭の種別・連続 undo・深さ `D`)から、先頭の差分のスカラー軸(変化した面の組合せ・変化量の境界値・**成績計上フラグの寄与の組**・**半イニングを跨ぐ差分**)で代表値を展開した行と case。**2 件目以降の要素は case の入力と期待出力で差分を保持**し、**undo 行の成績計上フラグの面は `unchanged`** | 同上。凍結基準の受理記録(D-12)。**負例が赤**: 変化量を取り違える undo(常に 1 点だけ戻す)/ 2 件目以降の差分を落とす undo |
| 32 | **S15**: tiebreak-start の操作行(payload の中身をフィールドごとのスカラー軸で分割・**指定値ごとに 2 つ以上の代表値**・発動回は派生軸〔28 の仕組みを使う〕。6 種目の被覆) | 同上。凍結基準の受理記録(D-12)。`required_set_input_coverage_declaration_v1.json` の除外宣言を外す。**負例が赤**: payload を無視して固定値を置く実装 |
| 33 | **逐行確認シートの生成**(ステップ 22〜32 で追加・変更した規範行すべてと、**それらから派生した case の入力と期待値**) | シートが全行と派生 case を覆い、digest を記録。ゲート ⑥ の承認対象はこの digest のシート。**この後ゲート ⑥** |
| 34 | **独立検証と revision の確定**: `independentReview` と署名記録、`runnerRevision` の確定(schema を 40 桁 OID の pattern に・`tests/test_consumer_handoff.py` の負例を書き換え) | 署名記録の検査が緑。各 OID が HEAD の祖先で、その時点の runner の blob が HEAD と一致 |

## 5. DoD(受け入れ基準)

Notion カードの DoD(2026-10-10 に PO 裁定で改訂)と対応づける。

- [ ] **D-2 の実行基盤が動く** — TS 正本 → 同一 JS artifact の再現ビルド / エンジンの配線(サーバー・クライアント)/ SQL 生成経路の枠(集計と行単位の分類)/ BOOT 報告経路の接続(ステップ 1〜16)
- [ ] **変換可能な部分集合を宣言で閉じ、その外を書けない構造になっている**。変換不能・判定不能は fail-closed(ステップ 4・5・10)
- [ ] **`receiverDoD` のうち発効前に閉じられる分を満たした** — 6 の全部(21)と、1〜3 の発効前に可能な部分(11〜13・34)。残りは U-X1 T1・T2 の PR へ(design.md §6)
- [ ] **(a) のうち発効前に解決できる分を解決した** — S02 の版(34)・S03(13)
- [ ] **(b) 27 件に検証先を割り当てた**(21)。**引き取った 11 件のうち 9 件を解決した**(22〜32 — **S20 は終了判定側だけ**。状況判定側のサヨナラ時の得点上限は TSK-544 へ送った)。S08・S09 は U-X1 T1 へ送り直した
- [ ] **`receiverTaskId` を TSK-538 に更新した**(20)— TSK-236 のステップ 110 が事後充足
- [ ] **S34 の送り先を TSK-540 へ更新した**(記録 4 箇所 — 17〜19)
- [ ] **対象計算を追加していない**(発効前は実行基盤まで — PO 裁定)
- [x] ADR-003 v0.7(D-8・D-11)と要件書 v2.14(E-1 の `HistoryEffect`)が確定ゲートで approved(ゲート ⑤ — 2026-10-14)
- [ ] 追加した規範行の期待値が独立に確認され、署名記録がある(33・34・ゲート ⑥)
- [ ] 各ステップの敵対レビューの採否が worklog にあり、**人間の逐行確認**を PR で行った
- [ ] PR の CI 全ジョブが green

## 6. テスト計画

| 種別 | 足すもの |
| --- | --- |
| **単体** | AST 検査器 a・b の正例と負例(4・5)・再現ビルド(6)・ホストの fail-closed(7)・runner の読み込み層(11)・descriptorParity(13)・収集器(14)・SQL 生成経路(10) |
| **一致性**(NFR-019 (a)) | **合成ベクタ**で両経路(pytest + 選定エンジン / Vitest + 同一 artifact)のバイト一致(12)。**実ベクタの一致性は U-X1 の対象計算の PR**(本タスクは対象計算を追加しない) |
| **越境** | **追加なし**。ホストと artifact は純関数を実行するだけで、テナントの入力を持たない |
| **E2E** | **追加なし**。表示面は U-F8 の持ち物 |
| **故障系** | artifact の不在・hash 不一致・timeout・メモリ超過・ゲストの eval(7・8) |
| **契約** | 契約 9 件ごとに規範行・case・被覆宣言の検査(22〜32 — S20 は終了判定側のみ)・**派生軸の関数性の負例**(28)・**履歴と結果の面の移行と交差制約の負例**(29)・handoff(20・34)・core-guard(17〜19) |
