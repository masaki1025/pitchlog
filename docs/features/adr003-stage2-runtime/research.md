---
feature: adr003-stage2-runtime
type: research
date: 2026-10-10
---

# 調査メモ: ADR-003 段階 2 の実行経路(TSK-538)— D-2 実行基盤と付録E 引き渡し契約の受け手

基準: develop `0e339ed9`(2026-10-10)。略記: `ADR3` = `docs/adr/ADR-003-domain-calc-method.md`、`req` = `docs/requirements/requirements-pitchlog-2026-07-22.md`、`設計書` = `docs/development/dev-harness-design-2026-08-07.md`、`handoff` = `contracts/state-transition/appendix_e_consumer_handoff_v1.json`、`510wl` = `docs/worklog/2026-10-10-adr003-stage2-owner.md`。
調査は decision-tracer / spec-checker / Explore(実測)の 3 並列 + Web(Codex `research --deep`)。食い違いは主セッションが原典で裁定した(「裁定」と明記)。

## 問い

1. D-2 の実行基盤が満たすべき条文と、発効前に作ってよい範囲
2. カード DoD(`receiverDoD` 6 項目・(a) 6 件・(b) 27 件・`receiverTaskId`)のうち、発効前に閉じられるもの
3. 既存の検査基盤の現況と、実ベクタ・実行体をつなぐ差し替え点
4. Python から QuickJS / 常駐 Node を使う技術的な現況
5. 他タスク(TSK-541・TSK-540・TSK-236・TSK-455・TSK-235・U-X1・#116)との境界

## 結論(要約)

- **PO 裁定「発効前は実行基盤まで」と、カード DoD の「`receiverDoD` 6 項目を満たす」「(a) 6 件を解決」は発効前に両立しない**。発効前に完全に満たせるのは `receiverDoD` 6(未解消レポートへの検証先の割り当て)だけで、1・2・3・4 は一部、5 は条件付き。(a) 6 件は S02 の版の確定・S03 の `D` 実値の解決を除き、対象計算の実体が要る(§2)。**同じ内容を U-X1 PR-1 も DoD に入れており、所有者が二重**
- **契約 schema v1 が更新を禁じている** — `receiverTaskId` は `type: null`、`runnerRevision` は `const "pending"`、3 識別子は `type: null`、`consumptionVerification` は `const "pending"`。**schema の改訂から始まる**(互換か非互換かは D-12 から決まらず不明)
- **`backend/domain/manifest.json` を置いた瞬間に consistency ジョブが落ちる**(`backend/src/pitchlog/domaincheck/boot/report.py:227-231` — 主セッション確認)。manifest を置く変更は、BOOT の意味スナップショットの収集器を同時に入れる必要がある
- **段階 2 判定器は 1 つの変更で 2 対象以上の完成を違反にする**(`backend/src/pitchlog/domaincheck/boot/phase2.py:395-398` — 主セッション確認)。**U-X1 計画書の PR-1(T1・T2 を同一 PR)はこのままでは通らない** — 対象ごとに PR を分ける必要がある
- **終了判定 170 case は `expected` を持たず `decision` を持つ**(主セッション確認)。runner は `case["expected"]` を固定で読む(`backend/src/pitchlog/domaincheck/runners/vectors.py:248`)
- D-2 の構成は Web 調査で成立の見通しが立つ: **TS → 単一 IIFE + `globalThis` 公開口(JSON 文字列 in/out)**。ブラウザは Vite `public` から無変換配信、サーバーは hash 照合後に QuickJS へロード。**Python 境界は十進文字列**(ADR3 D-14-e と一致 — バインディングの int 変換は BigInt を作らない)。**既存バインディングの設定だけで `eval` を完全に禁止できるかは未確認**
- QuickJS と常駐 Node の使い分け・置き場は条文に無い(計画判断)。**同型の公開事例は無い**

## 詳細と典拠

### 1. D-2 の実行基盤が満たすべき条文

| 項目 | 内容 | 典拠 |
| --- | --- | --- |
| 正本と artifact | TS 正本を唯一の人手保守実装とし、生成した**同一 JS artifact を両側で実行**。NFR-018 (a) の「埋め込みによる派生物」 | `ADR3:511-513`・`:614-615` |
| 何が同一か | 実行体が 1 つで hash で示せる | `ADR3:582`・`:721-722` |
| QuickJS / 常駐 Node | 並記のみ。**使い分けの規定なし**(非正本 worklog は QuickJS インプロセスを基本線 — 根拠は req のステートレス規定 `req:1060`) | `ADR3:513`・`:597`、`docs/worklog/2026-10-09-adr003-d2-switch.md:289`・`:306` |
| サーバー構成(D-14-h) | `eval`・`Function`・動的 import の禁止 + メモリ・時間の上限 / 起動時に artifact の hash を宣言値と照合 / build 時生成の固定ファイルをリテラルパスで読む / 到達モジュールの閉包(単一ファイル既定)/ 引数リテラル限定 / ホスト関数の集合を宣言し「ファイルを読む」「コードを評価する」能力を持たせない | `ADR3:748-760` |
| クライアント | バンドル同梱は現行と同形。Worker 化・別配信は入口の追加として宣言 | `ADR3:777-778` |
| 数値(D-14-e) | `number` 不使用・BigInt / **Python↔JS 境界は文字列** / 丸め `2r ≥ |d|` / 検査 (a) 算術 (b) 入力側で文字列 → `number` の変換も違反 (c) `Math.round`・`Math.floor` を丸めに使わない | `ADR3:633-655` |
| SQL(D-14-i) | (β)①〜⑤⑦ は TS 正本から SQL を生成し DB で実行 / 変換可能な部分集合を宣言で閉じる(具体は段階 2)/ 変換不能・判定不能は fail-closed / 手書き SQL 禁止 / 必須集計の変換可否は (iv) | `ADR3:782-809` |
| 決定性 | 明示条項なし(**不明**)。関連: 実行時の制限 `:749`・プロパティの seed 固定 `:240` | — |
| 置き場 | 規定なし。D-1 の置き場(`:111`)は発効後に失効(推論)。`contracts/` に置かない(`設計書:212`・`ADR3:113`) | — |
| 見直しトリガー | 数値表現の実現可能性が変われば発効前でも見直し — QuickJS の BigInt 追試はその入力(推論) | `ADR3:597-604` |
| 射程宣言 | 「実行基盤の実装 / 費用の実測 / ガードと生成前検査の是正」は実装時(段階 2)に確定 | `ADR3:9` |

**発効前に作ってよい範囲**: ADR に許可・禁止の明文は無い。根拠は PO 裁定(`510wl:234`、境界の明記の要求 `:239-240`)のみ。D-2 の構成要素「TS 正本 + artifact の build + 埋め込みエンジンの配線 + SQL 式の生成経路」(`ADR3:584`)が裁定の 3 要素と一致する。発効まで D-1 が現行(`ADR3:671`)、発効は PO による発効日の記録(`ADR3:681-682` — 変更履歴 `:9-10` に記録なし)。**fixture の正本規定は無い**(先例: `docs/features/domain-calc-dsl/plan.md:40`「実効性は合成 fixture と CI 実測へ委ねる」・`backend/tests/domain/fixtures/synthetic_dsl/`・`docs/features/vitest-vector-runner/plan.md:34`)。

**「段階 2」の二義**(推論): 帰結 1 の段階 2(`ADR3:930` — 対象計算の追加)と「実装時(段階 2)」(`ADR3:9`・`:217`)。本タスクの「発効前の実行基盤」は後者に当たり、前者(対象計算の追加)は発効後。

### 2. カード DoD — 発効前に閉じられるか

`receiverDoD`(`handoff:157-164`):

| # | 逐語(要約) | 発効前 | 理由 |
| --- | --- | --- | --- |
| 1 | 段階2入口ゲートの 4 工程を pytest・Vitest の両経路で満たし全 case の消費記録を残す | 一部 | 工程 1・2(読み込み・版検査 `handoff:182-183`)は可。工程 4 は「対象計算の全 case を消費」(`:185`)で計算が要る。D+1 の行・case も現存しない(`:186`) |
| 2 | 未確定の runner 識別子と revision を実在値で確定 | revision のみ | `vectors.py`・`vectorRunner.ts` は実在。entrypointId・directTargetId は manifest の対象ごとの要素(`ADR3:267`)。normalizerId は (iii)(`ADR3:729-733`) |
| 3 | descriptor と派生 schema の射影を全 projectionRules で照合 | 一部 | `backend/domain/history-depth.json` で `D` 実値は解決可。D-2 下の突合対象は (ii)(`ADR3:724-727`) |
| 4 | 正規化後の値を製品計算へ投入した証跡 | 不可 | 製品計算が要る |
| 5 | FR-040 の採否と根拠を製品 manifest へ宣言 | 条件付き | 採否の裁定が未了(U-X1 J-5)。manifest の実体なし。**計算ゼロの manifest が許されるかは不明**(schema は `calculations[]` 1 件以上 — 下記 §3) |
| 6 | 未解消レポートの段階 2 項目に検証先を割り当てる | **可** | — |

(a) 6 件(区分 `510wl:164`): S01 不可 / S02 版は可・実行は不可 / S03 `D` は可・射影は (ii) 待ち / S04 不可 / S29 不可(製品入口が要る)/ S33 不可。

(b) 27 件(S05〜S28・S30〜S32): 本タスクは**割り当てまで**(`510wl:243`)。PO・正本待ちのもの: S06・S30(D-8 — 担当不明)、S11(要件・descriptor の改訂)、S13・S22(PO 裁定)、S18(正本の改訂)、S31(FR-040 の採否)。**S08・S09・S15〜S21・S27・S28 の 11 件は所有者が空いている**(当初 10 件と誤記 — S15〜S21 は 7 件) — U-X1 は着手条件 P-8 として受取タスクへ送り(`docs/features/ux1-state-calc/design.md:76`・`plan.md:47`・J-7)、受取タスク(本タスク)は割り当てまでと定められている。新しい契約整備タスクの要否は PO 判断。リポジトリ内に S05〜S32 を ID で引き取る計画書は無い(走査 0 件)。

**S34 の送り先の記録は 4 箇所**(裁定 — decision-tracer の 3 箇所と spec-checker の 2 箇所の和): `docs/features/appendix-e-golden-vectors/unresolved-report.md:85`・`.claude/core-areas.json:43`(`deferred_to` — **guard_paths** `:48`)・`docs/features/appendix-e-golden-vectors/design.md:1319`・`tests/test_core_guard.py:923`(「段階2送り」を固定)。

### 3. 検査基盤の現況(実測 — カードの 24c023e4 からの変化なし)

`git diff --stat 24c023e4 0e339ed9 -- backend/src/pitchlog/domain{gen,check,mut} backend/domain frontend contracts/state-transition .github .claude` の差分は `.claude/core-areas.json` の 9 行(#95 の tenant-isolation 7 件)のみ。カード実測 1〜6 は真。7 は「状況判定・終了判定の TS は 0 行。ただし座標変換の `frontend/src/lib/courseInputView.ts`(58 行・NFR-018 (c) 例外表)がある」。

| 部品 | 現況 | 典拠 |
| --- | --- | --- |
| IR 生成 | `domaingen/core.py`(776 行)。CLI は IR を標準出力へ書くだけで backend を呼ばない | `core.py:559`・`:659`・`:724-772` |
| 言語 backend | 宣言を読まない固定スタブ(python 48 / typescript 42 / sql 38 行)。出力は `wrapper-only-fragment` の断片。呼び出し元はテストと domainmut のみ | `backends/__init__.py:105-125`・`common.py:9` |
| formatter | 表示規則から実コードを生成(生成 TS を node で実行して検証済み) | `tests/domain/gen/test_formatter.py:363-374` |
| manifest schema | トップレベル exact-set `propertyCatalog`・`calculations[]`(**1 件以上**)・`displayBindings[]`。calculation ごとに 10 項目(`generated[]` の artifactKind は python/typescript/sql/typed-receiver/formatter)。**宣言モデル前提で TS 正本を受ける項目が無い** | `backend/domain/manifest.schema.json:575-590` ほか |
| runner(Python) | `run_vectors` が case ごとに正規化 → 比較 → 実行 → `case["expected"]` と比較 | `domaincheck/runners/vectors.py:205-267`・`:248` |
| runner(TS — TSK-455) | `runVectors` が `python3 -m pitchlog.domaincheck.runners.vector_bridge` を spawn。判定は Python、正規化と計算は TS コールバック。現在は合成フィクスチャ 9 シナリオ | `frontend/src/testing/vectorRunner.ts:326-366`・`vectorConformance.spec.ts:45-85` |
| 差し替え点 | ①実契約の cases ②manifest から contract ③生成 normalizer ④`frontend/src/lib/generated/wrappers/` 経由の計算 — ②〜④は実在しない | 実測 |
| 終了判定 case のキー | `branchId, caseId, decision, inputCoordinate, normalizationRuleId, normalized, raw, rowRef` — **`expected` が無い** | 主セッション確認 |
| BOOT | 封印集合 136 要素(対象 13 × 10 + トップ 3 + mechanism 3)。`unresolvedCount` 136。**manifest が在ると `CheckerExecutionError`** | `backend/domain/boot-seal.json`・`boot/report.py:227-231` |
| 段階 2 判定 | `classify_phase2` 実装済み。**2 対象以上の同時完成は違反**。意味スナップショットの収集器は無い(空と空を渡す) | `boot/phase2.py:341-417`・`:395-398`・`boot/report.py:232-240` |
| CI | Python ジョブ(harness・mutation)に setup-node なし — ランナー既定の node を使う(推論・版固定なし)。frontend ジョブだけ `mise.toml` の node 24.16.0 | `.github/workflows/ci.yml:270-274` |
| frontend build | vite 8.2.1(rolldown)・typescript 6.0.2。esbuild は未導入。lib モード 0 件。`src/lib/generated/` への直接 import は depcruise が禁止(`wrappers/` 経由のみ) | `frontend/package.json`・`.dependency-cruiser.cjs` |

### 4. コア領域と検査経路

- game-state の paths(`.claude/core-areas.json:259`)は 110 件で、件数は `tests/test_core_guard.py:2300` に固定。`fnmatchcase`(`scripts/core_guard.py:485`)で `*` がディレクトリをまたぐ(`tests/test_core_guard.py:2372-2385`)ので、**`backend/domain/*`・`backend/src/pitchlog/{domaincheck,domaingen,domainmut,generated}/*`・`frontend/src/lib/generated/*`・`tests/domain/*` 配下なら宣言不要**。`frontend/package.json`・lockfile・`vite.config.ts`・`tsconfig*`・`mise.toml`・`backend/pyproject.toml`・`uv.lock` は既にコア(`core-areas.json:274-280`・`:294-295`)
- `AREA_PATH_ADDITIONS`(`scripts/core_guard.py:31-41`)は #95 の 7 件(基線に吸収済み)。規則の典拠はコードとテストのみ: 宣言を JSON より先のコミットで固定(`:30`)/ 「基線のまま」か「基線 + 宣言の全件」だけ許す(`:263-304`)/ JSON と基線定義の同一コミット変更は拒否(`:378-389`)/ `test_area_registration` が宣言の中身を固定(`tests/test_core_guard.py:2279-2282`)
- **逆依存閉包の 11 件は #95 後も成り立つ** — 実体は `tests/test_core_guard.py:998-1075`(`derive_contract_reference_python_paths`)、除外 11 件の固定は `:916`。#95 は閉包のコードも除外リストも変更していない(diff 確認)。TSK-540 の前提は現時点で有効
- **#116**(`origin/feature/uf2-auth-state` `30ba9deb`): `AREA_PATH_ADDITIONS` を `{"tenant-isolation": ("frontend/src/stores/authStore*",)}` に置き換え、`core-areas.json` に 1 行追加、`test_core_guard.py` に +100 行(`UF2_AUTH_STORE_AREA_PATH_ADDITIONS`・件数許容 82/83)、`frontend/package.json` に pinia 等を追加。**本タスクが `frontend/package.json` や core_guard を触るなら #116 と競合面を持つ**
- コア領域の判定: `contracts/state-transition/*` は game-state × sync-protocol(`core-areas.json:326`・`:209`)。`tests/test_consumer_handoff.py`・`tests/test_gap_register.py` もコア。**本タスクの重さ分類はコア領域**

### 5. Web 調査(Codex `research --deep`。URL は各項目に付記 — 採用前に主セッションで要確認)

- **構成案**: TS → 単一 IIFE(esbuild `bundle`・`format: 'iife'`・`splitting: false`・固定 `target`)+ `globalThis` 公開口(JSON 文字列 in/out)。ブラウザは Vite `public` から**無変換**配信(通常 import すると Vite が再変換して同一バイト列が崩れる — https://vite.dev/guide/assets.html)。QuickJS は hash 照合後に起動時ロード。常駐 Node は `.mjs` から静的 import(https://esbuild.github.io/api/)
- **Python バインディング**: `quickjs`(PetterS)1.19.4 は 2023-11-19 公開・リポジトリは 2026-01-01 にアーカイブ(https://pypi.org/project/quickjs/)/ **`quickjs-ng`(genotrance)0.17.0.1 は 2026-10-01 公開・abi3 manylinux wheel・MIT・継続開発 — 第一候補**(https://pypi.org/project/quickjs-ng/)/ `quickjs-runtime` は Linux wheel なし / `quickjs-rs` は WASM 方式・alpha
- **BigInt の境界**: エンジンは標準 BigInt 対応(https://bellard.org/quickjs/Changelog — 2025-04-26 に削除されたのは BigFloat 等の独自拡張)。**バインディングの Python int → JS は BigInt を作らず long か double**(https://github.com/genotrance/quickjs-ng/blob/main/module.c)— 32 bit 超で丸めの恐れ。**境界は十進文字列にする**(ADR3 D-14-e と一致)。`JSON.stringify` は BigInt で TypeError
- **決定性**: Math の超越関数は実装近似 / sort は安定(ただし NG に 2026-08-20 の比較関数修正・2026-09-21 の不一致 issue — https://github.com/quickjs-ng/quickjs/issues/1736)/ `Intl` なし / 正規表現は実装差 → 使う API を契約で絞り、Firefox・Safari も対象なら差分試験に含める
- **サンドボックス**: memory / stack / time 上限あり(time は CPU 時間の割り込みで、大きな BigInt 演算中は遅れうる — https://github.com/bellard/quickjs/issues/545)。**`quickjs-ng` バインディングは通常の `JS_NewContext()` で、`eval` を設定だけで完全に禁止できるかは確認できず**(`globalThis.eval` の削除は完全な禁止にならない)。独自 C バインディングなら `JS_AddIntrinsicEval` を省ける
- **常駐 Node**: asyncio subprocess + 改行区切り JSON が最小構成。参考実測 約 0.113 ms / 往復(Python 3.14・Node 24 — 本番条件ではない)。`PyExecJS` は EOL
- **再現可能ビルド**: 版固定だけで保証しない。CI で 2 回クリーンビルドして SHA-256 一致、配信物とサーバー配置物の hash 照合
- **同型の公開事例は見つからない** — 部品の組み合わせによる設計判断

### 6. 境界

| タスク | 関係 | 典拠 |
| --- | --- | --- |
| TSK-541(510 タブ) | 発効条件 (i)〜(iv) の条文化と要件書の規範改訂。本タスクは決めない。**リポ内に ID の出現は無い**(Notion のみ — 510 からの申し送りで ID 確定) | `docs/features/adr003-stage2-owner/plan.md:51` |
| TSK-540 | S34 の中身の是正。本タスクは S34 の送り先記録の更新を行う | `510wl:382-388` |
| TSK-236 | `receiverTaskId` 更新で同タスクのステップ 110 を事後充足(再オープンしない) | `510wl:392-393` |
| TSK-455 | 送り物(実契約の読み込み・本物の 2 経路・証跡と収集器・R-a・R-b) | `docs/features/vitest-vector-runner/design.md:121-130` |
| TSK-235 | D-1 前提の基盤。ガード是正(`ADR3:837`)の所有者は不明 | `docs/features/domain-calc-dsl/plan.md:65` |
| U-X1 | `receiverDoD` 1・2・4 を PR-1 の DoD にも持つ(所有者二重)。P-8 の 11 件が所有者空白 | `docs/features/ux1-state-calc/plan.md:82`・`:99` |
| 技術スタック承認(`req:1059`) | worklog が食い違う: 「確定ゲートで取る」(`docs/worklog/2026-10-09-adr003-d2-switch.md:273-274`・`:307`)/「TSK-538 で判断」(`510wl:368`) | — |

### 7. 再提案してはいけない選択肢(却下済み)

Pyodide / Rust+WASM / 一般の Python↔TS トランスパイル(`ADR3:125-128`)・両言語の手書き interpreter(`:117`)・D-1 拡張(`:552-569`)・手書き SQL(`:795-796`)・`number`・`Number()`・`Math.round`/`Math.floor`・「除数の半分」比較(`:633-655`)・比較器での丸め(`:267`)・変異範囲の縮小・夜間への移送・暫定マージ(`:254`)・夜間のみの担保(`:359`)・非リテラル `require`・ホスト関数のファイル読み/評価(`:752-760`)・`contracts/` への配置(`:113`)・「緑になってからコードを追加する」着手順(`:942`)・整数符号化(`:828`)。

## 未解決・申し送り

1. **カード DoD と PO 裁定の不両立**(§2)— `receiverDoD` 1〜5 と (a) 6 件は発効後の対象計算の変更でしか閉じない。**本タスクの DoD を「発効前の基盤 + 6 + 割り当て」に絞るか、発効後まで本タスクを開けておくか**、および U-X1 PR-1 との所有の二重を PO が裁定する
2. **(b) の 11 件の所有者空白**(S08・S09・S15〜S21・S27・S28)— 契約整備タスクの起票要否(PO)
3. **U-X1 計画書の PR-1 が段階 2 判定器に落ちる**(`phase2.py:395-398`)— T1・T2 を別 PR にする必要がある。U-X1 計画書の改訂(着手時まで持ち越し中)に追加
4. **manifest を置くと consistency が落ちる**(`boot/report.py:227-231`)— 収集器の実装を manifest と同じ変更に入れる。**計算ゼロの manifest は schema が許さない**(`calculations[]` 1 件以上)ので、発効前に manifest を置けるかは要設計
5. **schema v1 の改訂**(`appendix_e_consumer_handoff_schema_v1.json:96-98`・`:102-105`・`:225-236`)— 互換 / 非互換の判定。負例テスト(`tests/test_consumer_handoff.py:283-286`・`:299-300`)が現行値を固定
6. QuickJS か常駐 Node か・置き場・`eval` の完全禁止の方法(既存バインディングで足りるか、独自 C バインディングが要るか)— 実物の wheel での BigInt 往復・3 環境のバイト比較の試験が要る
7. 終了判定 case の `decision` キーへの runner 対応
8. 技術スタック承認の取り方(worklog の食い違い)
9. ガード是正(D-14-j・`ADR3:837`)の所有者
10. #116 との競合面(`frontend/package.json`・core_guard)— マージ順
