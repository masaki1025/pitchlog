---
feature: vitest-vector-runner
type: research
date: 2026-10-08
---

# 調査メモ: (α) ベクタ契約の Vitest 側 runner(TSK-455)

略号:

- DV = develop のツリー(`/home/ymdms/projects/pitchlog`)
- WT = TSK-236 の worktree(`../pitchlog-worktrees/feature-appendix-e-golden-vectors`。ローカル HEAD `d76e2cf5`。origin より 961 コミット先行で、未 push)
- ADR = `docs/adr/ADR-003-domain-calc-method.md`(DV では approved v0.3)
- 要件書 = `docs/requirements/requirements-pitchlog-2026-07-22.md`(v2.9)

WT の行番号は、WT が push されて #81 がマージされると変わる。マージ前に #81 の diff で取り直す。

## 問い

1. ADR-003 と要件書は、Vitest 側 runner に何を課しているか。課された条件のうち、いま緑にできるものはどれか
2. TSK-455 の担当範囲はどう決まってきたか。段階 2 で埋める値は誰が書くのか
3. Python 側の `run_vectors` と同じ意味で消費する runner を TS で作るには、何が揃っていて何が欠けているか

## 結論(要約)

- **いま作れるのは runner の「消費エンジン」と、契約を読み込む層まで**。製品の (α) 契約(状況遷移 96 件・終了判定 170 件)を全件消費させることは、**段階 2 でないとできない**。消費には TS の生成済み正規化と生成済み計算が要るが、どちらも存在せず、生成器もない(D-1)。Python 側も同じで、ステップ 34 は合成契約で検証している
- **Python の `run_vectors` は ADR の条件をすべては満たしていない**。schemaVersion とトップレベルを読まない。最初の不一致で例外を投げ、全件を列挙しない。経路一致には同じ実値を両方の経路に入れている(A-3)。Vitest 側をこれに「揃える」のか「ADR に揃える」のかは、人間の判断が要る(未解決 U-1・U-2)
- **(α) 契約の形は `VectorContract` にそのままでは載らない**。終了判定には `expected` がなく、`/decision` から写す必要がある。`tags` は契約に存在しない。case schema は `additionalProperties: true` で未知 field を閉じていない。比較器は行の list を要求するが、契約の値は単一の object になっている(B-3)
- **言語をまたいで「同じ意味」を担保する仕組みが要る**。Python の `==`(bool と int を区別しない)、`json.dumps(sort_keys)` の順序、`re.search` の `$`、検証器が対応しているキーワードの範囲が、TS とずれる(C-4)。同じ負例と正例を両 runner に流し、判定が一致することを検査する「適合ベクタ」で担保する案を推す(推論)
- **重さの候補はコア領域**。`frontend/vitest.config.ts` と `frontend/src/lib/generated/*` は `.claude/core-areas.json` の paths に入っている(`.claude/core-areas.json:182,229`)。reporter を配線するなら前者に触れる

## 詳細と典拠

### A. ADR-003 と要件書が課す条件

#### A-1. 条文

| 条件 | 典拠 |
| --- | --- |
| (α) の契約は**両 runner(pytest と Vitest)が同じファイルを全件消費**する。未対応 case・未知 field・重複 ID・schema 不一致はすべて fail | ADR:284 |
| 両 runner は `schemaVersion` の不一致を fail にする。ファイル内の `version` はファイル名と一致させる | ADR:297-298 |
| 各 case は `id`(一意)/ `input` / `expected` / `tags` を持つ。正規化前の生値・規則識別子・正規化後の値の 3 点を持つ | ADR:267 |
| 実行契約: ①生値へ生成済みの正規化を適用 → ②正規化後の期待値と突合 → ③その実値を計算へ渡す。正規化後の値をそのまま入力として与え、規則の実装を素通りさせてはならない | ADR:285 |
| 期待値を正本実装から自動生成しない | ADR:286 |
| 経路一致: ①製品の実行入口経由と ②正本生成物の直接呼び出しの両方で実行し、①=期待値・②=期待値・①=② を検査する | ADR:217 |
| 5 判定。要求集合は `(calculation, vector, case, runner, entrypointId, directTargetId)` の直積。**証跡はアダプタの自己申告ではなく、CI 側の独立した収集器が作る**。hash が `generated[]` と食い違えば fail | ADR:249 |
| Vitest の証跡は reporter が JSON に書く。5 項目(calculation / propertyId / propertyKind / generatedCases / status)を出さないテストは実行済みに数えない。skip・todo・0 件生成も数えない | ADR:249(プロパティ層の規定) |
| 比較は lossless に限る。値は丸めない。未知フィールド・欠落フィールドは fail | ADR:245 |
| 不一致は例外を投げず、全件をリストで返す(最初の 1 件で止めない) | ADR:320 |
| (α) の directTargets は生成 Python と生成 TypeScript の関数の両方。TS 生成物の置き場は `frontend/src/lib/generated/` | ADR:245, 102, 105 |
| フィールドレベルの細部(証跡ファイルの具体形式など)は、ベクタ整備タスクと検査基盤の実装タスクで確定する | ADR:251 |
| NFR-018: (α) はクライアントとサーバーで同一のコードに由来する実行体を使う。人手で保守する実装は 1 系統だけ | 要件書:890, 897 |
| NFR-018 (b)②: 入口経由の出力と直接呼び出しの出力の一致を合否条件にする | 要件書:901 |
| BOOT-NO-CLAIM: 移行状態の CI が緑でも、NFR-019(a) の充足を意味しない | 要件書:918 |
| NFR-019: フロントエンドのテストランナーは Vitest に統一する。PR ごとに CI で実行し、全部緑でないとマージできない | 要件書:925 |

#### A-2. 段階

- 段階 1 では、ベクタの schema と独立に確認した期待値、および**検査基盤(生成器・マニフェスト・収集器・CI 配線)**を先に確定する。**この段階では対象計算のコードを追加しない**(ADR:441)
- 段階 2 では、対象計算 1 件ごとに、正本・生成物・製品経路の呼び出し部・3 層検査を**同一の変更**として追加する(ADR:442)
- 検査は、生成物・製品入口・変異対象が存在しないと緑にできない(ADR:440)
- **A-1 の個々の条件に段階を割り当てた条文はない**(spec-checker の全数確認)
- 推論による振り分け:
  - **いま合成契約で作って検証できるもの**: 全件消費と 4 種の fail、version・schemaVersion の検査、実行順序と素通りの検出、lossless 比較と全件の列挙、reporter の出力
  - **段階 2 でないと緑にできないもの**: 実契約の全件消費、5 判定の経路一致、`generated[]` の hash 照合

#### A-3. Python `run_vectors` と ADR の差(DV で原典を確認済み)

| ADR の要求 | `run_vectors` の現状 | 典拠 |
| --- | --- | --- |
| schemaVersion・version の検査(ADR:298) | 読まない。引数は `cases` 配列だけ | `backend/src/pitchlog/domaincheck/runners/vectors.py:205-227` |
| 全件の列挙(ADR:320) | 最初の不一致で `VectorRunError` を投げる | 同 :240-241, 252-253 |
| 経路一致 ①=②(ADR:217) | `PathSubmission(key, expected, actual, actual)`。同じ実値を両方の経路に入れているので、①=② は自明に成り立つ | 同 :190-202(本調査で原典を確認) |
| 未知 field の fail(ADR:284) | `validate_asset` 頼み。case schema が `additionalProperties: false` のときしか効かない | 同 :161-165 |
| 証跡の出力 | なし。dataclass を返すだけ | 同 :100-125 |

### B. 決定の経緯と (α) 契約の形

#### B-1. 担当の経緯

- TSK-235 の分担節は「TSK-235 = 段階 1 の②(検査基盤)、①ベクタは TSK-236〜239」と定めている。Vitest runner には触れていない(`docs/features/domain-calc-dsl/plan.md:90-96`)
- 2026-09-24 の PO 裁定で、「runner による契約の消費」は段階 2 に送られた(WT `docs/worklog/2026-09-24-appendix-e-golden-vectors.md:63-73`)
- TSK-236 の計画書は TSK-455 を「段階 2 の依存」としている(WT `docs/features/appendix-e-golden-vectors/plan.md:67, 77`。design.md:1361-1371 も同じ)
- **評価台帳にも ADR-003 の変更履歴にも TSK-455 の記述はない**(decision-tracer が本文を grep して確認)
- Notion カードにある「TSK-236 PR #4 の開始条件」は、リポジトリ側に根拠がない(worklog 2026-10-08 の「決定」)

#### B-2. 段階 2 の値は TSK-455 では書けない

- 引き渡し契約(WT `contracts/state-transition/appendix_e_consumer_handoff_v1.json`)の vitest 経路は `runnerRevision: "pending"` で、`normalizerId` / `entrypointId` / `directTargetId` は null(:59-66, 113-120)。`receiverTaskId` も null(:188)
- 対応する schema が値を固定している。`runnerRevision` は `const "pending"`、3 つの ID と `receiverTaskId` は `type: null`(WT `appendix_e_consumer_handoff_schema_v1.json:102-105, 225-236`)。確定値を書くとテストが fail する(WT `tests/test_consumer_handoff.py:281-286`)
- 値を確定するのは「段階 2 受取タスク」の receiverDoD とされている(handoff:159, 184)。このタスクはまだ起票されていない(WT `unresolved-report.md:100` の U110-01)
- `dependencies[]` には、Vitest 側の成果物が確定したあとで追加する(同 :101 の U110-02)。**TSK-455 が受け持つのは、runner のパスと commit OID を 236 側へ伝えることだけ**

#### B-3. (α) 契約の実データ(WT で原典を確認済み)

| 項目 | 状況遷移 | 終了判定 |
| --- | --- | --- |
| cases 数 | 96 | 170 |
| case のキー | caseId, rowRef, inputCoordinate, raw, normalizationRuleId, normalized, expected | caseId, branchId, rowRef, inputCoordinate, **decision**, raw, normalizationRuleId, normalized |
| `expected` | 96 件すべてにある | **0 件**。handoff が `/decision → /expected` へ写す(handoff:91-94) |
| case schema の `required` | rowRef, raw, normalizationRuleId, normalized(**caseId と expected は必須ではない**) | 8 キーすべて |
| `additionalProperties` | **true** | **true** |
| 正規化規則 | result-display-name-to-id 71 件、identity 25 件 | game-end-result-display-name-to-id 165 件、identity 5 件 |
| expected / decision の形 | 単一の object。キー集合は 3 種類(6 キー 89 件・operation 系 6 件・undo 1 件) | 単一の object。5 キー |

- `tags` は両契約ともない(handoff:41-45, 95-99 が `availability: "absent"`)
- handoff の比較方式は `"lossless"` という文字列だけで、`ComparisonContract`(surface / fields / normalizations)の中身は決まっていない(handoff:47-48)
- `stage2EntryGate`(handoff:181-187)はトップレベルからの読み込み、version・schemaVersion・descriptor digest の検査、両 runner での全件消費を求めている
- 記述が古い箇所がある。handoff:11 と unresolved-report.md:84 は「vectors.py は存在しない」と書いているが、DV にも WT にも存在する
- descriptor digest の値が一致しない。契約側は `sha256:ca4215…`(state_transition_contract_schema_v1.json:723)、handoff の artifacts は `sha256:9e51ee…`(handoff:138)。意味は検証していない

### C. frontend と CI の実体(DV)

#### C-1. Vitest の構成

- vitest 4.1.10、TypeScript 6.0.2、jsdom 30.0.1(`frontend/package.json:33`)
- `frontend/vitest.config.ts:1-13` は `environment: 'jsdom'` と `fileParallelism: false` だけを設定している。reporter・include・outputFile の指定はない
- JSON Schema の検証ライブラリは直接依存にない。ajv 6.15.0 が eslint の推移依存として入っているが、draft 2020-12 には対応していない(`frontend/pnpm-lock.yaml:619, 2370`)

#### C-2. contracts/ の読み方の前例

- `@contracts` の alias で静的 import する(`frontend/tsconfig.app.json:6-9`、`frontend/vite.config.ts:494-505`、`frontend/src/lib/courseCoordinateContract.spec.ts:2`)
- `node:fs` で読む(`frontend/src/lib/sync/failureScenarioContract.spec.ts:1-21`、`frontend/src/testing/failureScenarioAdapter.ts:3-34`)
- Vitest から Python を子プロセスで呼ぶ(`frontend/src/testing/entrypointClosure.spec.ts:150-156, 251-256`)

#### C-3. 生成物と静的規則

- `frontend/src/lib/generated/` には `.gitkeep` しかない(本調査で確認)
- `backend/src/pitchlog/domaingen/` に正規化の生成器はない(`normaliz` で grep して 0 件、本調査で確認)
- TS backend は wrapper 専用の断片を文字列で返すだけで、ファイルには書き出さない(`backend/src/pitchlog/domaingen/backends/typescript.py:15-42`)
- `generated/` は wrappers 経由でしか import できない(`frontend/.dependency-cruiser.cjs:4-17`、`frontend/eslint.config.js:44-66`)。spec ファイルはこの規則から除外されている(`.dependency-cruiser.cjs:60`)

#### C-4. Python と TS で意味がずれる箇所

1. **検証器**: Python の `validate_asset` は自前の部分集合実装。`$schema` 2020-12 を必須にし、外部 `$ref` を拒否する。minimum / maximum / allOf / contains などは黙って無視する(`backend/src/pitchlog/domaincheck/cli.py:202, 223-325, 322, 365-495`)。ajv 2020 のような完全実装を使うと判定が厳しくなる
2. **等値**: Python の `==` は `True == 1` を真とする(`path_match.py:426`、`cli.py:396-400`)。契約には bool と int が混在している
3. **total-order**: Python は `json.dumps(sort_keys=True, ensure_ascii=False)` の順に並べる(`path_match.py:359-366`)。JS はキーを挿入順に並べ、sort は UTF-16 単位で比べる。statFlags には日本語キーがある
4. **正規表現**: Python の `re.search` では `$` が末尾の改行の前にもマッチする
5. **例外**: Python は normalize / execute のその他の例外や KeyError を `VectorRunError` に包まずに送出する(`vectors.py:248`)

#### C-5. CI と証跡

- Vitest は `frontend` ジョブで `pnpm test -- --run` として走る。reporter の指定も artifact のアップロードもない(`.github/workflows/ci.yml:258-282`)。paths-filter には `contracts/**` が入っている(同 :255)
- 受け口の `collect_vitest_reporter` は DV にある(`backend/src/pitchlog/domaincheck/collect_layers.py:514-601`)。ただし **`propertyKind` は invariant / equivalence に限られている**(同 :44、本調査で確認)。プロパティ層向けで、ベクタ消費の証跡には使えない。CI からは呼ばれていない
- frontend ジョブの形は `tests/test_ci_wiring.py:60-80` が検査している

## 未解決・申し送り

人間の判断が要るもの(/plan の前提):

- **U-1 Python 側との非対称**: Vitest 側にだけ schemaVersion とトップレベルの検査、全件の列挙を入れると、「同じ契約を同じ意味で消費する」が崩れる。次の 3 案がある
  - ① Python 側 `run_vectors` も同じ変更で揃える(backend に範囲が広がる)
  - ② 両側とも段階 2 受取タスクに送る
  - ③ Vitest は ADR に揃え、Python 側の追随は別タスクに起票する
- **U-2 経路一致の作り方**: Python のように同じ実値を 2 経路に入れる(①=② が自明になる)か、入口と直接呼び出しを本当に 2 経路にするか。後者は生成物がないので、段階 1 では合成でしか作れない
- **U-3 言語をまたいだ意味の担保**: 同じ正例・負例(適合ベクタ)を両 runner に流し、判定の一致を検査する案(推論)。適合ベクタの置き場(`contracts/` か `tests/fixtures/`)と、Python 側テストへの追加が範囲に入るかを決める
- **U-4 証跡の形式**: ベクタ消費の証跡形式が両 runner とも決まっていない。ADR:251 はこれを「検査基盤の実装タスク」へ委任している。TSK-455 で決めるのか、収集器側(Python)の拡張も含めるのかを決める

PO の確認が要るもの(spec-checker が抽出。TSK-455 だけでは閉じない):

- **P-1** `tags` がない: ADR:267「各 case は tags を持つ」と食い違う。ADR:251 の委任の範囲に入るかは不明
- **P-2** 未知 field: case schema が `additionalProperties: true` なので、ADR:284 の fail を runner の側で実装する必要がある。どのキー集合を「既知」とするかの正が要る
- **P-3** D+1: `dPlusOnePolicy: "liveness-only"` と、5 判定の「①=expected」が両立しない(ADR:249・ADR:271・handoff:49)

申し送り:

- 236 タブへ: runner のパスと commit OID が決まったら伝える(`dependencies[]` 用)。handoff:11 の古い記述と、descriptor digest の不一致を参考として伝える
- WT の行番号と schema の最終形は、#81 の diff で取り直す

## 裁定(2026-10-08・人間)

- U-1: **Vitest は Python `run_vectors` の現状に揃える**。schemaVersion・トップレベル検査・全件列挙といった ADR の未充足分は、両側とも段階 2 受取タスクへ送る。カードの「やること 3」(schemaVersion 不一致の fail)とずれるので、計画書で明示し、カードも直す
- U-2: 経路一致は Python と同じ形にする(同じ実値を 2 経路に入れる。①=② が自明であることを明記する)。本物の 2 経路は段階 2
- U-3: 共通の適合ベクタ(合成契約の正例・負例)を `tests/fixtures/` に置き、pytest と Vitest の両方に流して判定の一致を検査する
- U-4: 証跡は `VectorRunReport` に相当する報告オブジェクトまで。JSON 証跡と収集器の拡張は、ADR:251 の「検査基盤の実装タスク」へ送る
