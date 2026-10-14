---
feature: adr003-stage2-runtime
type: design
date: 2026-10-11
---

# 詳細設計: ADR-003 段階 2 の実行経路(TSK-538)

[plan.md](plan.md) 4 節から参照する。事実の典拠は [research.md](research.md)(基準 develop `0e339ed9`。行番号は同時点)。
略記: `ADR3` = `docs/adr/ADR-003-domain-calc-method.md`、`req` = 要件書、`handoff` = `contracts/state-transition/appendix_e_consumer_handoff_v1.json`、`report` = `docs/features/appendix-e-golden-vectors/unresolved-report.md`。

## 1. 山田さんの裁定(2026-10-10〜11)

| # | 裁定 | 理由(調査の要点) |
| --- | --- | --- |
| D1 | **発効前に閉じられる分で閉じる**。`receiverDoD` 1〜5 の残りと (a) S01・S04・S29 の残りは **U-X1 の対象計算の PR**(T1・T2 それぞれ)へ移す | 対象計算の実体なしには閉じられない(research.md §2)。U-X1 PR-1 との所有の二重も解消する |
| D2 | **(b) のうち所有者のいない 11 件(S08・S09・S15〜S21・S27・S28)は TSK-538 に残す** | U-X1(P-8)と受取タスク(割り当てまで)の間で空白になっていた |
| D3 | 引き渡し契約の schema は **v1 のまま改訂** | schema 自身が「起票後に string へ改訂する」と予告(`appendix_e_consumer_handoff_schema_v1.json:104`)。値の意味は変えず仮値を実値にするだけ。D-12(`ADR3:347`)の明文はないので裁定で決めた |
| D4 | TS 正本 `frontend/src/domain/`・サーバー側ホスト `backend/src/pitchlog/domainrt/` を**専用の置き場として宣言**。#116 のマージ後 | 既存 glob に収めると、生成物(`generated/`)や検査器(`domaincheck/`)の置き場に製品の正本・ホストを混ぜる |
| D5 | エンジンは**試験の結果で決める**(quickjs-ng か常駐 Node) | 条文に使い分けの規定がない(`ADR3:513`・`:597`)。バインディングの BigInt 変換と eval の完全禁止が未確認(research.md §5) |
| D6 | S15・S16 は **descriptor の分割**で解く | 要件書 E-1 を拡張すると authz の要件書 digest・oracle-seal・三点突合へ連鎖する |
| D7 | S20 は**台帳 schema の終了判定の役割を 5 つ目に増やす** | 要件書の規範表との完全一致照合(`scripts/check_gap_register.py:1159`)を避け、契約の中で閉じる |
| D8 | S21 は**状況判定の operationRows `game-end-declaration`** に結ぶ | DRAW-05 は FR-010 の終了宣言による正式終了(`req:1679`)。付録E の中で閉じる |
| D9 | S08・S09 は **U-X1 の状況判定 PR へ送り直す**(TSK-538 は割り当てだけ) | 「実機とともに確定」(`ADR3:217`・`req:1433`・`:1554`)— 発効前・対象計算なしでは閉じられない |

**TSK-538 が解決する契約は 9 件**(S15・S16・S17・S18・S19・S20・S21・S27・S28)。S20 は終了判定側(25)だけを解決する — 状況判定側(サヨナラ時の得点上限)は**ゲート ⑤ の PO 裁定(2026-10-14)で TSK-544 へ送った**(既存の列では、手動上書きと `OUT3-*` で有効得点を確定した後に上限をかける順序を表せないため)。

## 2. 実行基盤の構成

```
frontend/src/domain/            TS 正本(人手で保守する唯一の実装 — 発効前は公開口・codec・合成フィクスチャ用の足場だけ)
        │  esbuild(bundle / format: iife / splitting: false / 固定 target)
        ▼
単一の JS artifact(コミット・SHA-256 を宣言)
        ├─ ブラウザ: frontend/public/ から無変換で配信 → <script src>(Vite に import させない — 変換で同一バイト列が崩れる)
        └─ サーバー: backend/src/pitchlog/domainrt/ がリテラルパスで読み、起動時に hash 照合 → エンジンへロード
公開口: globalThis.<名前> = Object.freeze({ 操作: (JSON 文字列) => JSON 文字列 })
境界: 整数は十進文字列(D-14-e。バインディングの int 変換は BigInt を作らない — research.md §5)
```

- **manifest は置かない**(1 周目 P1-6 で、報告経路への接続を本タスクに含めた): `backend/domain/manifest.json` を置くと consistency ジョブが `CheckerExecutionError` で落ちる(`backend/src/pitchlog/domaincheck/boot/report.py:227-231`)。schema は `calculations[]` 1 件以上を要求し、段階 2 判定器は 13 対象 ID 以外を拒否する。**manifest を置くのは U-X1 の最初の対象計算の PR**。本タスクはその前提となる収集器と `boot/report.py` への接続(ステップ 14)を用意し、manifest ありの一時リポジトリで未解消一覧を出せることを試験で固定する
- **artifact の置き場**: ブラウザ配信用は `frontend/public/domain/pitchlog-domain.js` と SHA-256 宣言 `pitchlog-domain.json`(無変換配信の唯一の道 — research.md §3)。サーバー実行イメージはリポジトリルートをビルドコンテキストとし、両ファイルを root 所有で同じ相対配置の `/app/frontend/public/domain/` に COPY する。仮想環境も root 所有で COPY し、実行ユーザーに Node ホストを書き換えさせない。Python の製品入口はコンテナ内の固定基準 `/app`、ソース実行時は `host.py` の固定相対配置から導くリポジトリルートを基準に、両リテラルパスを読む。SHA-256 照合済みのソースだけを Node に渡す。Node ホストの固定ソースは `pitchlog.domainrt.host` の Python 文字列定数として wheel に同梱し、Node を `--input-type=module --eval` で起動する。tenant boundary 検査器が `backend/src/` の非 Python ファイルを fail-closed で拒否するため、同ディレクトリに `.mjs` は置かない。`backend/domain` の規範 JSON は wheel に含めない(`tests/test_packaging.py`)。
- **R-b**(TSK-455 送り — `docs/features/vitest-vector-runner/design.md:126`): `frontend/src/testing/vectorRunner.ts` と spec 2 本をコア登録の対象に含める(ステップ 17・18)

## 3. 条文の要求と担保の対応

| 要求 | 典拠 | 担保(ステップ) |
| --- | --- | --- |
| eval・Function・動的 import の禁止 | `ADR3:748-760` | ESLint 規則(TS 正本の範囲)+ AST 検査器 a(4)+ artifact の字句検査(6)+ ホスト側の拒否試験(7) |
| 起動時の hash 照合・リテラルパス・単一ファイル | 同上 | ホスト(7)・FastAPI 起動時検査(8)・再現ビルド(6) |
| ホスト関数の集合を宣言し「ファイルを読む」「コードを評価する」能力を持たせない | `ADR3:752-760` | ホスト(7) |
| メモリ・時間の上限 | `ADR3:749` | ホスト(7)・エンジン試験(1) |
| `number` を使わない / 文字列 → `number` の変換も違反 / `Math.round`・`Math.floor` を丸めに使わない | `ADR3:633-655` | AST 検査器 b(5 — 型付き) |
| 変換可能な部分集合を宣言で閉じ、範囲外は fail-closed / 手書き SQL 禁止 | `ADR3:782-809` | AST 検査器 a(4)・SQL 生成経路の枠(10) |
| クライアントの別配信は入口の追加として宣言 | `ADR3:777-778` | クライアントの読み込み(9)・collect_entrypoints_fe の追随 |
| 再現可能なビルド | Web 調査(research.md §5) | 2 回ビルドの SHA-256 一致(6)・CI(15) |

**本タスクが決めないこと**: 発効条件 (i)〜(iv)(TSK-541)。プロパティ層の「実行体どうしの等価性」の比較相手((i))・descriptor 拘束の突合対象((ii))・正規化と表示経路((iii))・(β) 必須集計の変換可否((iv))。ステップ 10 の SQL 生成経路は**枠**までで、必須集計を覆うかの判定は (iv) の入力として渡す。

## 4. エンジン試験の判定基準(ステップ 1)

quickjs-ng を採用する条件(**すべて満たすこと**。1 つでも欠ければ常駐 Node):

1. 十進文字列で受け渡した BigInt(0・負数・2^31・2^53・2^64 を超える値)が往復で変わらない
2. ゲストコードの `eval`・`Function` 構築・動的 import を**設定またはバインディングの範囲で**拒否できる(`globalThis.eval` の削除だけでは不可)
3. 合成フィクスチャの同一 artifact について、QuickJS と Node の出力がバイト一致する(sort の同値キー・負数・BigInt 境界・例外を含む)
4. メモリ上限・時間上限の超過で fail-closed になる
5. 本番の platform(Linux・CPython 3.12)の wheel が入手できる

**費用の実測**(`ADR3:9` が段階 2 に送ったもの)を design.md に追記する。試験の後、PO がエンジンを承認する(ゲート ②)。

### 4-1. エンジン試験の結果(ステップ 1)

2026-10-11 に `quickjs-ng==0.17.0.1` と Node 24.16.0 で合成 artifact を実行した。以下の「合格」は各条件の実測範囲を指す。エンジンの採否はゲート ② で PO が決める。

| 条件 | quickjs-ng | 常駐 Node | 根拠となるテスト |
| --- | --- | --- | --- |
| 1. 十進文字列の BigInt 往復 | **合格**。6 境界値が保存された。ただし Python `int` の直接バインドは `number` になり、`2147483648` → `-2147483648`、`9007199254740993` → `1` などへ変化する | **合格**。同じ 6 境界値を保存 | `test_decimal_string_bigint_round_trip`、`test_direct_python_int_binding_is_number_and_can_change_value`、`test_persistent_node_reads_same_artifact_over_ndjson` |
| 2. `eval`・`Function`・動的 `import()` の拒否 | **不合格**。`Context` に `disable_eval=True` を渡しても無視される。`globalThis.eval` の削除後も `new Function` と `Function.prototype.constructor` は実行できる。動的 import は構文として通り、モジュール解決時に拒否されるだけ | **合格**。起動オプション `--disallow-code-generation-from-strings` と `vm.createContext({ codeGeneration: { strings: false, wasm: false } })` の併用で 3 経路を拒否。動的 import はローダーのコールバックを与えず `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING` で拒否。起動オプション単独では `vm` 内の `Function` を止められない | `test_eval_deletion_does_not_block_function_constructors`、`test_dynamic_import_has_no_module_loader_but_is_not_syntax_rejected`、`test_vm_options_reject_eval_function_and_dynamic_import`、`test_node_flag_alone_does_not_restrict_vm_context` |
| 3. 同一 artifact のバイト一致 | **合格**。同値キーの安定ソート、負数、BigInt 境界、明示例外と 0 除算を含む同一入力で一致 | **合格** | `test_same_artifact_outputs_identical_bytes`、`test_persistent_node_reads_same_artifact_over_ndjson` |
| 4. メモリ・時間超過の fail-closed | **合格**。`set_memory_limit` は out of memory、`set_time_limit` は interrupted、`set_max_stack_size` は StackOverflow を返す | **合格**。`--max-old-space-size=16` の超過でプロセスが異常終了し、`vm` の timeout は `ERR_SCRIPT_EXECUTION_TIMEOUT` を返す。外側のプロセスタイムアウトでは停止できる | `test_memory_limit_fails_closed`、`test_time_limit_fails_closed`、`test_stack_limit_fails_closed`、`test_heap_limit_stops_excessive_allocation`、`test_vm_timeout_rejects_unbounded_guest`、`test_process_timeout_stops_unbounded_guest` |
| 5. Linux・CPython 3.12 の wheel | **合格**。aarch64 で実際にインストールし、wheel の tag を確認。PyPI の公開一覧で x86_64 版も確認 | 対象外 | `test_installed_wheel_targets_current_linux_platform`、[PyPI 0.17.0.1 の配布一覧](https://pypi.org/pypi/quickjs-ng/0.17.0.1/json) |

条件 5 で確認した wheel のファイル名(どちらも `cp310-abi3` で CPython 3.12 に適合):

```text
quickjs_ng-0.17.0.1-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl
quickjs_ng-0.17.0.1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
```

**費用の実測**: aarch64 Linux、CPython 3.12.3、Node 24.16.0。合成 artifact を使い、ロードはファイル読込済みのコードを新しいコンテキストに評価する時間(各 200 回の中央値)、呼び出しはロード済み engine への Python からの 1 回の時間(QuickJS 1000 回、Node 500 回の中央値)を測った。試験の合否には使わない。

| engine | artifact ロード | 1 呼び出し | メモリ |
| --- | ---: | ---: | --- |
| quickjs-ng | 0.1268 ms | 0.0035 ms | context の `malloc_size` 104,640 B。測定 Python プロセス全体の RSS 34,400 KiB |
| 常駐 Node | 0.3081 ms | 0.2610 ms(stdin/stdout の往復を含む) | Node プロセスの RSS 61,164 KiB |

Node の起動から初回応答までは 32.6345 ms。RSS の 2 値はそれぞれ Python プロセス全体と Node プロセス単体なので、engine 単体のメモリ差としては読めない。Node の heap 上限はプロセス全体の RSS 上限ではない。製品ホストの上限と停止処理はステップ 7 で固定する。

**判定案**: 条件 2 が quickjs-ng バインディングで不合格のため、§4 の決定則に従い**常駐 Node を推奨**する。Node は起動オプションに加えて `vm` の `codeGeneration` 設定と動的 import ローダーを与えない構成が必要である([Node 24.16.0 CLI](https://nodejs.org/download/release/v24.16.0/docs/api/cli.html)、[Node 24.16.0 vm](https://nodejs.org/download/release/v24.16.0/docs/api/vm.html))。この段階では採否を確定しない。

**ゲート ② の決定(2026-10-11・山田正輝)**: **常駐 Node を採用する**。backend の実行環境に Node 24.16.0(`mise.toml` と同じ版)を同梱し、FastAPI から常駐プロセスとして使う。ステップ 2 は Node 選択時の合格条件(本番用の Node の版・配布・起動の固定)で進める。quickjs-ng の試験(`tests/domain/runtime/test_quickjs_engine.py`)は不採用の根拠として残す(quickjs-ng が無い環境では skip)

**配布定義の追加(2026-10-11・山田正輝)**: 本番の配布定義がリポジトリに無かった(開発 DB の `docker-compose.yml` のみ)ため、**ステップ 2 で `backend/Dockerfile` を新設し Node 24.16.0 を同梱する**(本番の CPU は x86_64・aarch64 の両方)。計画書を改訂し、計画レビューを経て再承認を得る

## 5. 契約 9 件の順序と依存

| 順 | ID | 中身 | 依存 | 正本 |
| --- | --- | --- | --- | --- |
| 22 | S27 | 終了判定 schema の `decision` に X 表記の欄を足し、170 case を再生成(展開器 `scripts/expand_game_end_cases.py:176-179` の固定値も改修) | — | 不要 |
| 23 | S28 | 到達不可 2817 件の縮小(行の無い分岐・固定されない軸値) | S19〜S21 の累積で完了(順序上は先に枠、各件で縮む) | 不要 |
| 24 | S21 | DRAW-05 を operationRows `game-end-declaration` に結ぶ(D8) | — | 不要 |
| 25 | S20(終了判定側) | 台帳 schema の終了判定の役割を 5 つに(D7)・walk-off の行と case(終了の検知) | — | 不要 |
| 26 | S19 | descriptor に成立段数の軸・凍結基準 `gameEndAxisFields` の受理記録・COLD-09 の行と case | — | **descriptor の確定ゲート** |
| 27 | — | 正本改訂のゲート投入: ADR-003 D-8(targetKind に「対象なし」・XC-09 を「シナリオ長」へ・stateEffect・guaranteeMode)・descriptor の分割(payload と履歴軸 — D6)・**サヨナラ時の得点上限の表現**(32 のため) | — | **/finalize-doc**(ゲート ⑤) |
| 28 | S18 | D+1 の liveness-only の行と case | 27 の承認・S03 の `D` 実値(13) | D-8 |
| 29 | S16 | undo の 3 ケース(取り消す対象の差分) | 27 | descriptor |
| 30 | S17 | targetKind「対象なし」の行 | 27 | D-8 |
| 31 | S15 | tiebreak-start の操作行(6 種目の被覆・発動回の述語) | 27 | descriptor |
| 32 | S15 と派生軸の仕組み | (旧 32「S20 状況判定側」は TSK-544 へ送った — 計画書の改訂 2026-10-14。S15 は旧 31 から移動)派生軸の属性と関数性・到達不可の検査、ステップ 26 の成立段数の是正、tiebreak-start の操作行 | 27 | ADR-003 v0.7 D-11 |

- **1 件 1 コミット**: 被覆履歴(`required_set_input_coverage_v1.json`)は 1 コミットで 1 件しか追加できない
- 各コミットで**連動して変わるもの**: `check_required_set_coverage.py` の固定値・`game_end_coverage_declaration_v1.json` の件数・`gap_register_v1.json`・fixture・**handoff の artifacts digest**(同じコミットで更新)・関連テスト(`tests/test_required_set_coverage.py`・`tests/test_gap_register.py`・`tests/test_consumer_handoff.py` の件数固定)
- **期待値は独立に確認する**(CI 規則 3 `ADR3:334`)。前例(コミット `3122ba52`)の手順に従う: Codex が作成 → 逐行確認シート(33 — 規範行と**派生 case の入力と期待値**を覆う)→ Claude が照合 → PO が承認(ゲート ⑥)→ `independentReview` と署名記録(34)
- **TSK-541 との衝突**: TSK-541 のブランチ(`feature/adr003-activation-conditions`)も ADR-003 を改訂する。**ステップ 27 の前に 510 タブと順序を合わせる**(どちらが先に approved になるか・D-8 と D-14 の節が重なるか)

## 6. 送り先の表(D1・D9)

| 項目 | 本タスクで閉じる部分 | 送り先(U-X1) |
| --- | --- | --- |
| `receiverDoD` 1(入口ゲート 4 工程) | 工程 1・2(読み込み・版検査)・runner の差し込み(11・12) | 工程 3 の実計算への binding・工程 4 の全 case 消費 → **T1・T2 の PR** |
| `receiverDoD` 2(runner 識別子と revision) | revision(34) | entrypointId・directTargetId(manifest の対象ごと)・normalizerId((iii) 待ち)→ **T1・T2 の PR** |
| `receiverDoD` 3(射影の照合) | descriptorParity と `D` の実値(13) | D-2 下の突合対象((ii) 待ち)→ TSK-541 の確定後に T1・T2 |
| `receiverDoD` 4(製品計算への投入証跡) | — | **T1・T2 の PR** |
| `receiverDoD` 5(FR-040 の宣言) | — | manifest を置く最初の PR(T1)。採否は U-X1 J-5 |
| `receiverDoD` 6(検証先の割り当て) | **全部**(21) | — |
| (a) S01・S04・S29・S33 の残り | 基盤部分(11・12) | **T1・T2 の PR** |
| (b) S08・S09 | 割り当て(21) | **T1 の PR**(実機とともに確定) |

### 6-2. (b) 27 件の確定した送り先(ステップ 21)

ゲート ④ で送り先のタスクを起票し、2026-10-14 に山田さんが次の割り当てを裁定した。このステップでは未解消レポートの第 3 列を更新し、各項目の解決は表の担当タスクで行う。

| 送り先 | 件数 | ID | 担当と条件 |
| --- | --- | --- | --- |
| TSK-538（D-2 実行基盤・契約整備） | 9 | S15・S16・S17・S18・S19・S20・S21・S27・S28 | 本タスクで解決する。 |
| TSK-544（U-X1 T1 状況判定の対象計算） | 15 | S05・S06・S07・S08・S09・S10・S12・S14・S23・S24・S25・S26・S30・S31・S32 | S08・S09 は実機とともに確定する。S06・S30 は D-8 の改訂の要否を T1 が判断する。S31 は FR-040 の採否に従う。 |
| TSK-546（付録 E 契約の PO 裁定） | 3 | S11・S13・S22 | PO 裁定の後、契約の中身は TSK-544 が受け取る。 |

## 7. コア領域の宣言(ステップ 17〜19)

- 新しい paths: `frontend/src/domain/*`・`backend/src/pitchlog/domainrt/*`・artifact の public 配置・`frontend/index.html`・`frontend/eslint.config.js`・`frontend/.dependency-cruiser.cjs`・ビルドスクリプト・契約を参照する新しい tests。R-b の既存 glob 外の対象は `frontend/src/testing/vectorRunner.ts`・`frontend/src/testing/vectorRunner.spec.ts`・`frontend/src/testing/vectorConformance.spec.ts` と明示する。加えて同じ runner 経路の `frontend/src/testing/artifactAdapter.ts`・`frontend/src/testing/artifactAdapter.spec.ts`・`frontend/src/testing/handoffLoader.ts`・`frontend/src/testing/handoffLoader.spec.ts` も登録対象にする。**game-state と data-migration の両方**(`DOMAIN_CALC_GLOBS` — `tests/test_core_guard.py:407`・`:2331`)。契約を参照する tests は sync-protocol にも(`.claude/core-areas.json:13-16`)
- 手順(`scripts/core_guard.py:30`・`:263-304`・`:378-389`、#116 の前例 `e0f06b4a` → `19bd74d9` → `2e8613a7`): 17 = `AREA_PATH_ADDITIONS` を**置き換え** + test_core_guard を登録前後の両状態受理に / 18 = core-areas.json(paths と S34 の deferred_to)・report:85・appendix-e design.md:1319 / 19 = テストを新状態だけに絞る
- **#116 との順序**: #116 が `AREA_PATH_ADDITIONS` と test_core_guard の同じ帯を変えるので、**#116 のマージ後に develop を取り込んでから 17 に入る**(ゲート ③)。#116 の U-F2 専用の表明 2 件を壊さない

## 8. リスク

- **規模**: 34 コミット・人間ゲート 6 つ・コア領域の敵対レビューが全面に掛かる。1 PR が大きい。逐行確認の負荷が高い
- **正本改訂の待ち**: /finalize-doc(ステップ 27 の後)の周回が長いと、28〜33 が止まる。ゲートの投入を早める(1〜16 と並行に周回させる)余地がある
- **エンジン試験の不合格**: 常駐 Node に切り替えるとホスト(7)・CI(15)の形が変わる。計画書の改訂(計画レビュー)を要する
- **TSK-541 との衝突**(§5)・**#116 との衝突**(§7)

## 未解決・検討メモ

- 技術スタックの追加(QuickJS または Node・esbuild)と artifact の public 配置の了承は、計画承認と同時に得る(ゲート ①)。要件書 7.1(`req:1059`「変更には承認を要する」)
- ガード是正(D-14-j・`ADR3:837`)の所有者は不明 — 本タスクの射程外として PO へ上げる
