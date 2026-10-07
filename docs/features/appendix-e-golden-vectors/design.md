---
feature: appendix-e-golden-vectors
type: design
date: 2026-09-24
---

# 詳細設計: 付録E ゴールデンケース全表 + 終了判定ベクタ(段階 1・ベクタ資産側)

plan.md 4 節から参照される詳細設計。調査の典拠は [research.md](./research.md)。

**v9(2026-09-24)**: 計画レビュー 8 周目の P1 4 件・P2 0 件を反映(7 周目の 7 件は解消 3 / 部分的 4 / 未解消 0)。
主要な変更: **`consumerBindings[]` に `executionPaths[]`(両 runner)と 2 面の比較契約**(1-3)/
**`history-depth.json` の権威関係を一意化し `nonCoverageFields` を 3 件に**(3-3・3-4)/
**述語 AST と `StateEffect` を閉じた型に + `eventKind` 別の合法組合せ表**(4-5・4-6)/
**`gapRegister` の `open` / `resolved` の述語を分離**(7-2)。

## 1. 段階 1 の終点

### 1-1. 本タスク = 段階 1 の**ベクタ資産側**成果物の完成

ADR-003:440-444 の段階 1 は「ベクタの schema と独立に確認した期待値」と「検査基盤」の双方。
**本タスクは前者のみ**(後者は TSK-235)。

| 区分 | 内容 |
| --- | --- |
| **本タスク** | 正本改訂 / descriptor / 契約 schema / 規範行 4 層 / 期待値 / `requiredSet` / `clauseBranchRegister` / 手作業 fixture / 語彙シード / oracle 遮断機構 / 未解消レポート / **段階 2 への引き渡し契約** |
| **段階 2** | 製品 manifest への計算登録 / **runner による契約の消費** / 正規化の計算投入証跡 / FR-040 宣言の manifest 記載 / **descriptor と schema の射影検査** |

### 1-2. runner 受入を段階 2 へ送る根拠

TSK-235 の `run_vectors()` はトップレベル契約や `schemaVersion` を読まず、
case に `caseId` / `raw` / `normalized` / `expected` を要求し(`vectors.py:150`)、
**全 case で `CalculationAdapter.execute()` を呼び出力一致を必須**とする(同:205)。
一方 ADR-003:267 の契約骨格は `id` / `input` / `expected` / `tags`、
`history-depth.json:145` は `D`+1 について出力同値を要求しない。
→ **段階 1 では両立しない**。最小 runner の自作は「検査基盤を作らない」と矛盾する。

### 1-3. 引き渡し契約(7 周目 P1-1 の是正)

v7 の 7 フィールドは**名前と概括だけ**で、受取側に必要な binding が無く、
「抽象的な文を入れて通せる」合格条件だった。→ **exact 型にする**。

```
handoffVersion / calculationIds[2]

consumerBindings[]:            ← 対象計算ごとに 1 件
  calculationId / vectorId / contractPath
  version / schemaVersion     … 契約ファイルの版と schema の版を**両方**
  caseSchemaRef               … case schema への JSON Pointer
  caseFieldMapping            … **JSON Pointer ベース**。契約の id/input/expected/tags →
                                runner の caseId/raw/normalized/expected/tags
  normalizationComparison     … 正規化面の比較契約(exact | lossless)
  outputComparison            … 出力面の比較契約(exact | lossless)  ← **比較は 2 面**
  dPlusOnePolicy              … "liveness-only"(拒否しない・切り捨てないのみ。出力同値を要求しない)
  executionPaths[]:           ← **実行経路の exact-set**(単数では (α) の両 runner を表せない)
    runner                    … "pytest" | "vitest"
    runnerRevision            … その runner の commit OID
                                **段階 1 では "pending"**(Vitest 側は TSK-455 が未着手・
                                pytest 側は TSK-235 が未マージのため確定できない — 9 周目 R9-P1-1)
    normalizerId / entrypointId / directTargetId
    resolutionStage           … "stage-2"(revision の確定は段階 2)

artifacts[]:  path / version / digest
dependencies[]: taskId / artifactPath / commitOid / version / 成立条件   ← task ID だけでは不可
receiverDoD[]
fr040Declaration              … 内容と根拠(記載先は段階 2)
descriptorParity              … 3-4 の射影規則への参照
consumptionVerification: "pending"   ← 段階 1 では未検証であることを明示
stage2EntryGate               … 段階 2 の最初の停止ゲート(下記)
receiverTaskId
```

**`executionPaths[]` を exact-set にする理由**(8 周目 P1-1): 本件の 2 契約はいずれも **(α)** であり、
**pytest と Vitest の両方**による全件消費が要る(ADR-003:284)。既存 runner のキーは
`calculation / vector / case / runner / entrypointId / directTargetId` の **6 次元**で、
**比較契約も 2 面**(`vectors.py:56` / `:178`)。単数の `runnerRevision` / `entrypointId` / `directTargetId` と
単一の `comparison` では、受取側が一意に `VectorContract` を構築できない。

**段階 1 で「実際に消費可能」とは主張しない。** `consumptionVerification: "pending"` を明記し、
**段階 2 の最初の停止ゲート**を「**トップレベル読込 / 版検査 / binding 構築 / `D`+1 を含む全 case 消費**」と定める。

## 2. 正本改訂

### 2-1. 順序(plan.md と一本化 — 7 周目 P1-5)

**要件書 → ADR-003 → 同期正本 → descriptor → 3 点突合 → `gapRegister` 骨格 → ゲート投入**。

**`in-review` 化はゲート投入コミットで行う**(descriptor と 3 点突合の後)。
v7 は design.md 内に「先に `in-review` で起案」と「descriptor 後に `in-review`」が混在していた。
→ **後者に統一する**。

**ゲート投入コミットの内容**(`/finalize-doc` 手順 1 に一致させる):
3 正本の frontmatter / 変更履歴の射程宣言 / `docs/README.md` の索引 / **worklog の適用版 + 条文 commit SHA**。
**`gapRegister` の骨格作成は別ステップ**。

### 2-2. 同期プロトコル正本

S2(:1309)と :1588 の正を「**D-6 で登録された状況判定ベクタ全体**」とし、内訳を
E-1 準拠の `matrixRows[]` と、該当 FR(FR-006 / FR-009 / FR-010 / FR-011 / FR-015)を典拠とする
`operationRows[]` / `undoRows[]` として記述。**D-8 は入力・出力・比較面の参照に限定**。

## 3. 入力軸 descriptor — **両段階を通した唯一の正**(7 周目 P1-2 の是正)

v7 は「段階 1 = descriptor / 段階 2 = schema」と**正が段階で交代する**記述で、
descriptor を一意の正にしたことにならなかった。また軸が D-11 の全体を覆っていなかった。

→ **descriptor を両段階を通した唯一の正とし、段階 2 の宣言モデル schema は
「descriptor に拘束される派生物」と D-11 に明記する**。

### 3-1. 構造

```
descriptorId / version / digest
stateTransitionAxes[]   … D-11:203 の全軸
gameEndAxes[]           … D-11:204 の全軸
nonCoverageFields[]     … schema で保持するが coverage 軸ではないもの
projectionRules[]       … schema への射影規則(3-4)
```

各軸: `axisId` / **由来条文 ID** / 分類(`finite-enumerable` / `boundary-partition` / `non-finite`)/
値集合 or 境界値 or 非有限の根拠。

### 3-2. `stateTransitionAxes`(D-11:203 の全軸)

| 群 | 軸 |
| --- | --- |
| 主要フラグ | `half` / `count.strikes` / `count.balls` / `outs` / `runners` / `battingOrder` / `tiebreakActive` / `gameEnded` / `inning` / `score` |
| **イベント** | **断中操作イベントの全種**(毎球入力の結果値 33 + 走者イベントの payload + 非毎球入力 4 種 + undo) |
| **履歴文脈** | **深さ**(0 / 1 / 2 / `D`)/ **構成の等価分割** / **シナリオ長**(1 / 2 / `D` / `D`+1) |

### 3-3. `gameEndAxes`(D-11:204 の全軸)

**規定イニング数** / **コールド条件**(点差・回・**段の配列長**)/ **延長上限** / **タイブレークの有無と開始回**。
組合せ規則(ペアワイズ + 境界値 × 状態×イベント の直積)も descriptor に持つ。

**`nonCoverageFields`**(付録F-1 の全 5 フィールドのうち終了判定に影響しないもの — 8 周目 P1-2):

| フィールド | 理由 |
| --- | --- |
| **DH 制** | 打順の構成に影響するが、**いつ試合が終わるか**には影響しない |
| **`tiebreak.runnerPlacement`**(走者配置) | タイブレーク**開始時の初期状態**を決めるが、終了条件の判定に入らない |
| **`tiebreak.leadoffRule`**(先頭打者規則) | 同上 |

**3 フィールドとも `nonCoverageFields` に列挙し、射影規則で schema 側に保持する**
(coverage 軸ではないが、派生 schema から脱落させない)。

### 3-4. 射影規則と拘束

| 項目 | 内容 |
| --- | --- |
| 射影規則 | descriptor の軸 → 宣言モデル schema の JSON Schema 表現への対応(整数範囲 → `minimum`/`maximum`、enum → `enum` 等)。**表現差を吸収して比較できる形** |
| 拘束 | schema は descriptor の **`descriptorId` / `version` / `digest`** を参照し、**exact-set / 値域一致**しなければ **manifest 登録不可** |
| 判定不能 | **fail**(fail-closed) |
| **既存資産との関係** | **descriptor は `history-depth.json` を参照しない**(9 周目 R9-P1-2 の是正)。同ファイルは **develop に存在しない**ため、参照すると **TSK-235 を待たない方針と両立しない**。descriptor は**値域を条文から独立に導出**し(3-2)、**`history-depth.json` との一致検査は段階 2** の `descriptorParity` で行う。**`D` の値も段階 2 で解決**する(段階 1 はシンボルのまま) |

**この射影検査の実行は段階 2**(引き渡し契約の `descriptorParity` で条件を渡す)。

### 3-5. digest

`digest` フィールドを除いた正規化 JSON の SHA-256(正規化方式を descriptor 自身に明記)。
**段階 1 の descriptor は外部参照を持たない**(3-4)ため、推移的 digest は不要。
**外部参照を持つ場合の規則**(JSON Pointer + 内容 hash による推移的 digest)は、
段階 2 で schema との射影を記録するときに適用する。

### 3-6. 数値基準の実測(ステップ 105)

測定日: **2026-10-06**。

契約ファイルの上限 **16 MB = 16,000,000 byte(十進 MB)** を
`contracts/state-transition/contract_size_limit_v1.json` に宣言する。
`scripts/check_required_set_coverage.py` は descriptor schema が参照する 2 契約と宣言の対象集合を
exact-set で照合し、各ファイルの実 byte 数が上限以下であることを検査する。
**16,000,000 byte ちょうどは通り、16,000,001 byte は失敗する**負例を持つ。

| 測定対象 | 実測値 | 試行回数・判定統計 |
| --- | ---: | --- |
| `state_transition_contract_v1.json` | 546,961 byte | 1 回のみ。統計処理なし |
| `game_end_contract_v1.json` | 334,193 byte | 1 回のみ。統計処理なし |
| 2 契約の合計 | 881,154 byte | 上記 2 件の和 |
| リポジトリ増分(`9ff36743` 基点、非圧縮の作業ツリー内容) | **3,462,485 byte** | 1 回のみ。統計処理なし |
| 契約サイズを含む requiredSet 検査 CLI | **2.74 秒** | 5 回、中央値(2.77 / 2.71 / 2.69 / 3.13 / 2.74 秒) |
| 影響範囲の pytest 検査群 | **63.84 秒** | 3 回、中央値(63.84 / 62.43 / 68.76 秒)。各回 679 件通過 |

実サイズの測定コマンド(リポジトリルートで実行):

```sh
wc -c contracts/state-transition/{state_transition_contract_v1,game_end_contract_v1}.json
```

リポジトリ増分は、merge-base `9ff3674398b3fd8dc36b9c5554e5c553792483ba` と
本ステップの作業ツリーを比較した。変更・新規ファイルごとに基点の Git blob サイズと現在の
ファイルサイズを取り、差分を合計する。削除・圧縮・`.git` 内の pack サイズは測定値に含めない。
測定コマンド(リポジトリルートで実行):

```sh
python3 - <<'PY'
import subprocess
from pathlib import Path

base = '9ff3674398b3fd8dc36b9c5554e5c553792483ba'
def git(*args):
    return subprocess.check_output(['git', *args])

paths = set(git('diff', '--name-only', '-z', base).decode().strip('\0').split('\0'))
paths |= set(git('ls-files', '--others', '--exclude-standard', '-z').decode().strip('\0').split('\0'))
paths.discard('')
before = after = 0
for name in sorted(paths):
    if Path(name).name == '.env':
        raise RuntimeError('unexpected .env path')
    current = Path(name)
    after += current.stat().st_size if current.is_file() else 0
    old = subprocess.run(['git', 'cat-file', '-s', f'{base}:{name}'], capture_output=True, text=True)
    before += int(old.stdout) if old.returncode == 0 else 0
print(f'changed_paths={len(paths)} before={before} after={after} net_added={after-before}')
PY
```

検査時間は `UV_CACHE_DIR=/tmp/uv-cache`、`uv run --offline`、既存 `.venv` を使い、
`/usr/bin/time` の経過実時間 `%e`(秒)を測る。コマンドは次のとおり。
各 `for` の反復が独立の 1 試行で、出力の中央値を判定値とする。

```sh
for i in 1 2 3 4 5; do
  /usr/bin/time -f '%e' env UV_CACHE_DIR=/tmp/uv-cache uv run --offline \
    python scripts/check_required_set_coverage.py
done
for i in 1 2 3; do
  /usr/bin/time -f '%e' env UV_CACHE_DIR=/tmp/uv-cache uv run --offline pytest -q \
    tests/test_input_axes_descriptor.py tests/test_input_axes_three_way_parity.py \
    tests/test_required_set_coverage.py tests/test_state_transition_contract_schema.py \
    tests/test_doc_check_profile.py tests/test_core_guard.py
done
```

**測定ランナー**: 手元の WSL2 Linux 6.6.114.1、aarch64、Qualcomm Oryon(論理 CPU 12 個)、
メモリ `MemTotal: 16121788 kB`、Python 3.12.3(`.venv`)、uv 0.11.21。
CPU 固定・他プロセス停止は行っていない。CI 設定の `harness` ジョブは `ubuntu-latest` だが、
**CI ランナー上の実サイズ・増分・実行秒数は測っていない**。CI の実機 CPU・メモリも測っていない。
本節の秒数はこの手元環境での記録値であり、後続の実測と手動比較できる。
自動合否の時間閾値は置かず、`ci.yml` に結ばない。

## 4. 契約の構成

```
状況判定: matrixRows[] / operationRows[] / undoRows[] / mustOperationCoverage / requiredSet / cases[]
終了判定: decisionRows[] / requiredSet / cases[] / validationErrors[]
```

### 4-1. `mustOperationCoverage` の 5 検査

①参照先の実在 ②行層・`eventKind` との一致 ③重複禁止 ④未帰属行の検出
⑤毎球入力の 3 下位分類の exact-set。**各検査に負例 1 件**。

### 4-2. `matrixRows[]` — E-1 **全 10 列**の exact 型(7 周目 P1-3 の是正)

v7 は 7 行しかなく、`イベント種別` / `結果ID・表示名` / `打席の終了` が欠けていた。

すべて `additionalProperties: false`、下表の列は**全て required**。

| # | 列 | exact 型 |
| --- | --- | --- |
| 1 | `eventKind` | `enum["batting-result", "secondary-result", "runner-event"]` |
| 2 | `resultId` | `string`(語彙シードの ID。参照整合)。**表示名は持たない**(語彙シードが正) |
| 3 | `precondition` | **述語 AST**(閉じた再帰型 — 4-6) |
| 4 | `countEffect` | `{strikes: Effect, balls: Effect}`。`Effect = {kind: "delta", value: int} \| {kind: "reset"} \| {kind: "unchanged"}`。**`kind: "reset"` と `"unchanged"` は `value` を持たない**(`additionalProperties: false`)。`delta` の `value` は strikes 0..2 / balls 0..3 |
| 5 | `plateAppearanceEnded` | `boolean \| enum["not-applicable"]` |
| 6 | `batterDestination` | `{kind: "continue" \| "out" \| "score" \| "not-applicable"}` または `{kind: "reach", base: 1..3}` |
| 7 | `runnerDefaultAdvance` | `{first: Adv, second: Adv, third: Adv}`。`Adv = {modality: enum["forced","optional","hold","not-applicable"], destination: 1..4 \| null}`。**`forced` / `optional` ⇔ `destination != null`**、**`hold` / `not-applicable` ⇔ `destination = null`**(双方向)。**起点塁別の到達可能集合**: first → {2,3,4} / second → {3,4} / third → {4}(research.md 7 節) |
| 8 | `outEffect` | `{count: 0..3, targets: [Target]}`。`Target = "batter" \| {runner: 1..3}`。**`count` と `targets` の長さが一致**。`count: 0` なら `targets` は空 |
| 9 | `statFlags` | **定義の穴 2 で確定した完全なキー集合**の各キー → `boolean`。**未知キーで fail**(`additionalProperties: false`)。**穴 2 の条文化を本表より前のステップに置く**(8 周目 P1-3 — 外延が閉じる前に exact 型は書けない) |
| 10 | `remarks` | `string`(**自由記述を許す唯一の列**) |

#### 4-2-1. 申告敬遠の `resultId` と投球有無(2026-09-29 PO 裁定)

要件書 4.0-2 の「FR-002 の必須項目（コース・球種・打撃結果）は投球イベントに限る」は、
記録画面で必須とする入力項目を定める規定であり、状態遷移契約の `resultId` に
`batting-result.intentional-walk` を用いることを禁じる規定とは読まない。申告敬遠の規範行は
`eventKind = batting-result`、`pitchEventKind = non-pitch-event` とし、`投球数`を計上しない。

この読みは旧 88 列の実測とも整合する。`docs/legacy/research/data-layer.md` では、45 列
「打撃結果」の 26 値に「申告敬遠」が含まれる一方、40 列「プレイの種類」は
「投球」／「牽制」／「ボーク」／「ピッチクロック違反」であり、申告敬遠を含まない。
したがって、要件書 4.0-2 の「旧版も『プレイの種類』列で同じ区別をしていた」という説明は、
牽制・ボーク・ピッチクロック違反には当てはまるが、申告敬遠には当てはまらない。

PO は 2026-09-29、旧機能の全面踏襲を前提に、記録者が打撃結果のドロップダウンから
申告敬遠を選ぶ入力経路を変えないことを決め手として、上記の扱いを裁定した。
これは承認済み要件書の改訂ではなく、本実装で採る条文の読みを固定する記録である。

#### 4-2-2. `凡打出塁` の状態効果と公式記録の境界(2026-09-30 PO 裁定)

`docs/legacy/research/input-screen.md:68` が記録する旧入力画面では、`凡打出塁`は
`凡打死` / `併殺打` / `ライナー併殺` / `ファールフライ` と同じ `outs`
カテゴリにある。`エラー` / `野手選択` / `犠打失策` は別の `miss`
カテゴリにあり、記録者の入力経路も異なる。同 `:163` は `凡打出塁`について、
打者の状態を出塁とし、全在塁走者を1塁ずつ進める旧状態効果を記録している。

PO は 2026-09-30、旧機能の全面踏襲と記録者の入力経路を変えないことを決め手とし、
`凡打出塁` を「凡打だが打者が生きた」値として、打者一塁出塁・全在塁走者の1進を
状態効果に置くと裁定した。ただし、`outs` と `miss` の入力カテゴリが異なる事実は、
`凡打出塁` の公式記録上の分類や失策の有無を定めない。`FR-004` の `officialScoringPayload`
と `official-scorer-judgment-input-contract`、およびそれらからの失策フラグ導出は段階2で確定する。

この裁定は承認済み要件書の改訂ではなく、旧実態から本実装に写す状態効果と、
本段階では定めない公式記録上の分類の境界を固定する記録である。

### 4-3. `operationRows[]` / `undoRows[]` の必須列(別表)

E-1 の 10 列を持たないため**独自に定める**。

**`operationRows[]`**(選手交代 FR-011 / タイブレーク開始 FR-009 / 試合終了宣言 FR-010 / その場登録 FR-015):

| 列 | 型 |
| --- | --- |
| `operationKind` | `enum["substitution","tiebreak-start","game-end-declaration","adhoc-registration"]` |
| `clauseId` | 典拠 FR の条文 ID |
| `payloadShape` | JSON Schema(`additionalProperties: false`) |
| `precondition` | 4-2 の述語 AST と同型 |
| `stateEffect` | **`StateEffect`**(4-6 の閉じた型)。**非影響面は `{kind: "unchanged"}`** |
| `historyEffect` | `{pushes: boolean, kind: string \| null}`(`pushes: false` なら `kind: null`) |
| `operationResult` | `enum["applied","rejected-precondition","rejected-invalid-payload"]` |
| `remarks` | `string` |

**`undoRows[]`**:

| 列 | 型 |
| --- | --- |
| `targetKind` | `enum["confirmed-play"]`(**FR-040 採用時に `"state-correction"` が加わる**。**`"undo"` を含めない**のが不変条件) |
| `precondition` | 履歴文脈の述語(深さ・先頭の種別) |
| `stateEffect` | **`StateEffect`**(4-6)。対象操作の差分の逆適用。**非影響面は `{kind: "unchanged"}`** |
| `historyEffect` | `{pops: 0 \| 1}` |
| `operationResult` | `enum["applied","nothing-to-undo"]` |
| `guaranteeMode` | `enum["full-equality","liveness-only"]`。**`D`+1 の行は `liveness-only`** |
| `remarks` | `string` |

### 4-4. 交差制約(すべてに `XC-*`)

| ID | 述語 |
| --- | --- |
| `XC-01` | `eventKind = runner-event` なら `batterDestination.kind = not-applicable` |
| `XC-02` | `precondition` が当該塁の走者不在を含むなら、その塁の `Adv.modality = not-applicable` |
| `XC-03` | `Adv.modality ∈ {hold, not-applicable}` なら `destination = null` |
| `XC-04` | `outEffect.count = targets.length` |
| `XC-05` | `eventKind = runner-event` なら `countEffect.*.kind = unchanged` |
| `XC-06` | `batterDestination.kind = continue` なら `plateAppearanceEnded = false` |
| `XC-07` | **双方向**: `plateAppearanceEnded = not-applicable` ⇔ `eventKind = runner-event`(片方向だと走者イベントに `true`/`false` を設定できてしまう) |
| `XC-08` | **`Adv.destination` が起点塁別の到達可能集合に含まれる**(一塁走者の一塁到達・三塁走者の二塁到達などを禁止)。`targetKind` に `"undo"` を含まないことは **`undoRows[]` の enum が既に排除**しているため交差制約から外す |
| `XC-09` | `guaranteeMode = liveness-only` は `D`+1 の行のみ |

### 4-6. 共通の閉じた型(`$defs` 相当 — 8 周目 P1-3)

散文で書いていた型を閉じる。**すべて `additionalProperties: false`**。

**`Predicate`**(述語 AST・再帰型。**演算子ごとの arity を固定**):

```
Predicate =
  | {op: "and" | "or",  args: [Predicate, ...]}        … arity >= 2
  | {op: "not",         args: [Predicate]}             … arity == 1
  | {op: "eq" | "gte" | "lte", axisId: string, value: Literal}
  | {op: "in",          axisId: string, values: [Literal, ...]}   … 非空
Literal = integer | boolean | string            … string は当該軸の enum 値のみ
```

**`axisId` は descriptor の軸 ID として実在すること**(参照整合)。
**`value` / `values` の型と値域は当該軸の分類・値集合に適合すること**。

**`StateEffect`**(比較面 4 面への影響):

```
StateEffect = {
  stateFields:   {<比較面の各フィールド>: FieldEffect}   … 全フィールド required
  scoreboard:    {<全欄>: FieldEffect}
  statFlags:     {<完全なキー集合>: FieldEffect}
  historyAndResult: {history: FieldEffect, operationResult: FieldEffect}
}
FieldEffect = {kind: "unchanged"} | {kind: "set", value: <当該フィールドの型>}
            | {kind: "delta", value: integer}
```

**「非影響面は `unchanged`」を型で強制する**(省略を許さない — ADR-003:324 の比較面を縮小しないため)。

### 4-5. `eventKind` 別の合法組合せ表(8 周目 P1-3)

`XC-*` は**片方向の禁止**しか表せず、不正な組合せを許していた。→ **合法組合せを表で固定する**。

| `eventKind` | `countEffect` | `plateAppearanceEnded` | `batterDestination.kind` |
| --- | --- | --- | --- |
| `batting-result` | 任意 | `true` \| `false` | `continue` \| `reach` \| `out` \| `score` |
| `secondary-result` | `unchanged` \| `delta` | `true` \| `false` | `continue` \| `reach` \| `not-applicable` |
| **`runner-event`** | **`unchanged` 固定** | **`not-applicable` 固定** | **`not-applicable` 固定** |

**表に無い組合せはすべて fail**(allowlist 方式)。

**各 `XC-*` につき最低 1 件の負例**を置く。

## 5. `requiredSet`

①行の要求(語彙シードの ID 集合 × 前提条件の分割規則・条文 ID 必須)と
②入力座標の要求(**descriptor から導出**。展開器のルールは読まない)の 2 段。

### 5-1. ①行の要求に用いる語彙軸と分割規則

①の語彙 ID 集合は、語彙シードの全値ではなく、次の `eventKind` ごとの
`resultId` 源から取る。分類の機械可読な正は
`contracts/state-transition/required_set_row_rules_v1.json` とし、語彙シードの全軸が
`result-id-source` または `not-result-id-source` のちょうど一方へ属さなければ fail とする。

| 語彙軸 | 分類 | 理由 |
| --- | --- | --- |
| `batting-result` | `batting-result` の `resultId` 源 | E-1・FR-003 が打撃結果の状態遷移を規範行へ置く |
| `secondary-result` | `secondary-result` の `resultId` 源 | E-1・FR-004 が打撃結果2を規範行へ置く |
| `strategy-category` | `runner-event` の `resultId` 源 | FR-004・A-4 の作戦3系統を走者イベントとして識別する |
| `pitcher-pickoff-destination` / `catcher-pickoff-destination` | `runner-event` の `resultId` 源 | FR-004 の投手／捕手牽制と対象塁を識別する |
| `pitch-type` | 非 `resultId` 源 | 投球属性。4.0-3 はチーム拡張語彙に値ごとの状態遷移規範を持たせない |
| `strategy-detail` / `strategy-result` | 非 `resultId` 源 | 作戦イベントの内訳／結果であり、イベント種別ではない |
| `error-type` / `pickoff-result` | 非 `resultId` 源 | FR-004 の payload に属する公式記録／走者別結果である |
| `batted-ball-type` / `batted-ball-strength` | 非 `resultId` 源 | 4.0-3 が打撃結果から分離する打球情報である |
| `batter-status` / `first-runner-status` / `second-runner-status` / `third-runner-status` | 非 `resultId` 源 | E-1 の状態効果側の値である |

前提条件の分割は、条文が同一語彙 ID に複数行を要求すると明示するものだけを採る。
現時点の閉じた規則は、既定の単一行、E-2・`SO-03` の振り逃げセーフ／アウト、
および FR-004・E-1 の `INT-01`〜`INT-07` が定める妨害裁定3組の計5規則である。
各規則は安定した `partitionRuleId`、適用する語彙 ID、抽象 `partitionId`、
`sourceClauseIds` を持つ。抽象 identity は行の要求を数えるための識別子であり、
後続ステップの `Predicate` を先取りしたとの主張はしない。規則の追加は典拠条文 ID を必須とし、
典拠の無い分割、どの規則にも属さない `resultId`、複数規則に属する `resultId` を fail とする。

**変異耐性の検査は展開器の実装後**。検出するのは「片経路の実装差」であり、
**両経路に共通する欠落は検出しない**。

## 6. `expected`

比較面 4 面をすべて持つ。**表示値は持たせない**。
**操作イベント・undo の出力面もこの 4 面を縮小しない**(非影響面は `unchanged`)。
**再開(FR-007)** は TSK-454 へ。**FR-006 のキュー投入・同期状態非依存**は同期側のテストへ。

## 7. 要件改訂 — 定義の穴 9 件

1 H/E/K/B の定義 + 延長時の扱い / 2 成績計上フラグの外延 / 3 コールド成立のタイミング /
4 引き分け成立の条件 / 5 X 表記の一般規則 / 6 タイムプレイの判定規則 /
7 妨害系 3 種の遷移 + 強制/任意進塁・停止の判定規則 / 8 `K3` の意味 + 三重殺 /
**9 打点の算出定義**。

**穴 3〜6・8・9 には閉じた分岐 ID の集合と各分岐の正負例**を置く。

### 7-0. 穴 9(打点の算出定義)— 実装中に発見(2026-09-25)

**ステップ 2 の導出元を確認していて判明した。** 打点は要求されているが**算出定義が無い**。

| 箇所 | 記述 |
| --- | --- |
| FR-022(`:442`) | 当日打席結果の **7 列の第 6 列が「打点」** |
| FR-022(`:443`) | 当日の集計(打席数・打数・安打・**打点**・四球・死球・三振・犠打・犠飛)は上記の行から導出する |
| 付録E-1(`:1269`) | 成績計上フラグの列挙に **打点** |

一方 **付録A-3(打者指標)に打点の行が無い**(打数 / 本塁打 / 打率 / 出塁率 / 長打率 /
コース別打率マップ / 打球方向 のみ)。A-2・A-5 にも無い。
→ 「**いつ得点が打点として記録されるか**」(併殺打の間の得点・失策による得点の扱いなど)が未定義。

**典拠**: **公認野球規則 9.04**(8-3 の典拠優先順位の 2 位)。
旧システムは「『本進』集計、併殺打時は除外」(`analytics-reports.md:68`)だが**旧は規範ではない**。

**手続き**: 計画書の退路(`gapRegister` へ `open` で追記 → 再改訂の要否を判定)に従う。
**フェーズ A(確定ゲートの前)なので、同一 PR 内で 9 件目として条文化する**。

#### ステップ56で確認したフォース連鎖と打点条件の矛盾（2026-09-30 PO裁定）

要件書E-1の走者既定進塁は、フォース連鎖を
`batterDestination.kind = reach`の場合に限定している。この定義をそのまま適用すると、
打者が`out`になる併殺打の一塁走者は`ADV-02`ではなく`ADV-04`となる。一方、A-3の
`RBI-01`は、打者のゴロがフォースダブルプレイまたはリバースフォースダブルプレイと
なった間の得点を打点に算入しないため、併殺打をフォースプレイとして扱っている。
そのため、`RBI-01`の適用条件は現行の`ADV-*`の機械的判定だけから導出できない。

この矛盾は、打点算出を所有する`GAP-09`へ`open`のまま記録し、`clauseIds`に
`E-1`・`ADV-02`・`ADV-04`・`RBI-01`を追加する。行20は承認済み条文を優先して
一塁走者を`hold`とするが、野球規則上のフォースプレイとの意味的な不一致を解消したとは
扱わない。なお、現行の機械検査は`XC-02`・`XC-03`・`XC-08`による存在・null対応・
到達可能塁を検査するだけで、`ADV-01`〜`ADV-04`の最初に一致する分岐を強制していない。
この検出欠落も同じ矛盾の解決待ちとして`GAP-09`に含め、条文の解決前に検査だけを
固定しない。

#### ステップ57で確認した犠打失策の記録員判断(2026-09-30 PO裁定・案A)

公認野球規則9.08は、打者のバントで走者が進塁し、失策がなければ一塁でアウトに
なったと思われる場合に犠打を記録する。ただし同条は、走者を進めるためでなく安打を
得るためであったことが明らかと記録員が判断したときは、犠打を記録せず打数を記録する
という分岐を本文に持ち、疑義のあるときは常に打者に有利に扱うと定めている。
つまり`犠打`と、その帰結として9.02(a)(1)が定める`打数`の除外は、記録員判断に依存する。

この分岐は現行の入力からは導出できない。要件書に「犠打失策」の語は現れず、語彙シードの
`batting-result.sacrifice-bunt-error`は`id`・表示名・`classification`の3フィールドだけで
記録員判断を含意しない。さらに`docs/legacy/research/input-screen.md:70`・`:71`が記録する
とおり、旧システムは同じ「犠打失策」を`miss`(`batting_result_miss`)と
`sacrifice`(`batting_result_sac`)の2カテゴリに持っており、新語彙はこれを1値へ統合した。
statFlagsは23件必須のexact型であるため、値を置かずに段階2へ送ることはできない。

そこで行26は規則9.08の既定側、すなわち`犠打 = true`・`打数 = false`に倒して確定させ、
表現できない分岐を観測入力の欠落として`GAP-09`へ`open`のまま記録し、`clauseIds`に
`FR-004`を追加する。`FR-004`は結果IDが「エラー」以外のプレイに付随する失策を
`officialScoringPayload`へ保持することを定める条文であり、犠打失策の公式記録側の所有に
あたる。`gapId`は9件のexact-setとして機械検査されているため新規IDは立てず、
この時点の`rowIds`は既存9件と同じく空のままとする。記録の実体は本節と行26の`remarks`が持ち、
双方が`GAP-09`を名指しして相互に辿れるようにする。

この判断で製品のふるまいは変わりうる。安打狙いのバントが失策で出塁した打席で、
本来は打数に算入され犠打が付かないところを、打数から除外し犠打を計上するため、
打率と犠打数が変わる。段階2で記録員判断を観測入力として確定するまで、本行を
規則9.08の全体を満たしたものとして扱わない。

#### ステップ58で確認したピッチクロック違反の違反主体(2026-10-01 PO裁定・案C)

ピッチクロック違反は、違反した側によって逆向きのカウント効果を持つ。NPBが
2026-08-03に導入を決定した規則では、投手が制限時間内に投球動作へ入らなければ
1ボールが加えられ、打者が残り8秒までに打撃姿勢を整えなければ1ストライクが
加えられる。したがって1語彙値に対して本来3行が要る。投手側(ボール+1・打席継続)、
打者側の2ストライク未満(ストライク+1・打席継続)、打者側の2ストライク
(アウト・打席終了・カウントreset)である。

違反主体を区別する入力は存在しない。descriptorの26軸に主体を持つ軸はなく、
`event.perPitch.pitchEventKind`は投球イベントと非投球イベントの別だけを持つ。
`event.perPitch.resultId`も「ピッチクロック違反」の1値である。入力座標は
`eventKind`・`resultId`・`precondition`の自然キーであるため、軸も語彙値も
増やさずに2行を置くと座標が衝突する。

要件書E-1はこの穴を一方の側だけ前提にしている。付録E-1の合法組合せallowlistは、
`secondary-result`へ`batterDestination.kind = out`を許す理由として`INT-06`と並べて
「打者側のピッチクロック違反が第3ストライクに当たる場合」を名指ししている。
投手側を代表に採ると、この`out`許容は本軸のどの行からも到達不能になる。

PO裁定により、投手側を代表1行として置き、打者側の2件を未解決差として残す。
投手側を選んだ根拠は1行で表せる唯一の側であることだけであり、規則上の優位でも
既定でもない。ステップ57の犠打失策とは性質が異なる。あちらは規則9.08が
「疑義のあるときは常に打者に有利に扱う」という既定を与えていたため既定側へ倒せたが、
本件に既定はなく、代表に選ばなかった側は単純に誤りになる。製品の実装前に、
違反主体の入力軸の追加または語彙値の分割として別途起票する。どちらもADR-003 D-11の
descriptorと要件書D-4の改訂にあたり、確定ゲートを要するため本タスクの射程外である。

帰属は`GAP-07`とする。同GAPの`clauseIds`は既に`E-1`と`FR-004`を持つため、
レジスタ側に足すものがない。穴の中身は本節と規範行の`remarks`が持つ。
これはステップ57の犠打失策と同じ型で、`gapId`が9件のexact-setとして機械検査される
一方、レジスタのエントリがID対応だけで本文を持てないため、後から見つかった穴は
意味の異なる既存GAPへ相乗りするほかなく、レジスタからは中身が読めない。
本タスクで2件目となるため、ハーネスの台帳へ候補として起票する。

#### ステップ58で確認した暴投・捕逸の分類と投球判定(2026-10-01 PO裁定・記録のみ)

要件書は暴投／捕逸・ボークを2通りに分類している。E-1の1410行は、allowlistの
`runner-event`行を説明する文脈で「盗塁・牽制・暴投／捕逸等の走者イベントは、打者の
カウントも打席の成否も変更しない」と書く。一方1460行は「PB／WP／ボーク等を伴うときは、
その特殊プレイの行で`optional`と到達塁を定める」と書き、同じ3値を特殊プレイ、すなわち
`secondary-result`として扱う。語彙シードはPB・WP・ボークを`secondary-result`軸の値として
持つため、行27・28・32は`secondary-result`として作った。`countEffect`を
`unchanged`としたのは1410行の「打者のカウントを変更しない」が直接の典拠である。

その帰結として、PB・WPが起きた投球のボールとストライクの判定がどこにも記録されない。
要件書1345行はイベント種別を「打撃結果／打撃結果2（特殊プレイ）／走者イベントの別」と
定め単一値としているため、1球1行の記録ではこの2つを同時に持てない。旧システムは
打撃結果と打撃結果2を同一行の別列として持っており
(`docs/legacy/baseball-scoring-db-structure.md:190`)、この情報は旧では失われていなかった。
たとえば1ボール1ストライクからの暴投で走者が進んだ場合、現行の規範行ではカウントが
1-1のまま残る。

これは規範行の誤りではなく要件書側の穴であり、行を変えても解決しない。本タスクの
射程外のため行は触らず、`GAP-07`へ帰属させて記録だけを残す。同GAPの`clauseIds`は
既に`E-1`と`FR-004`を持つため、レジスタ側に足すものはない。段階2で毎球記録の
イベント種別が単一値でよいかを判断するまで、PB・WPの行がその投球の判定を保持していると
扱わない。

#### ステップ61〜64の`payloadShape`の射程(2026-10-03 PO裁定・案A)

`operationRows[]`の`payloadShape`について、承認済みの2正本が正面から食い違う。
ADR-003のD-8は、各行が当該操作のpayloadを定める閉じたJSON Schemaを持ち、許可する
全フィールドを`properties`へ列挙して`additionalProperties: false`とすることを必須に
している。一方、入力軸descriptorの`stage2ExternalConstraints`は、`payloadAxisIds`へ
`event.operationPayload`を挙げ、`requiredArtifacts`へ`closed-payload-schemas`を
挙げて、これを段階2の確定対象としている。両者は要件書v2.10・ADR-003 v0.4・
同期プロトコル設計v0.5を一括検証した同じ確定ゲート12周を通っており、矛盾が残った。

FR-011は交代の種類と期待動作を定めるが、payloadのフィールド名・必須区分・型を
列挙していない。したがって推測でスキーマを書けばD-8違反か段階2の先取りのどちらかに
なる。この構造は選手交代に固有ではなく、ステップ62のタイブレーク開始、63の
試合終了宣言、64のその場登録にも同じ形で現れ、ステップ66の
`mustOperationCoverage`が6種を覆うという合格条件にも波及する。

PO裁定により、段階1と段階2で`payloadShape`の射程を次のように分ける。段階1が置くのは
**当該FRの受け入れ基準が名指しする要素だけを`properties`へ列挙した最小の閉じた形**で
あり、D-8が要求する`type: "object"`・`properties`の全列挙・`required`・
`additionalProperties: false`の4点を満たす。段階2が確定する`closed-payload-schemas`は
**内部制約まで含む完全形**であり、`constraintClasses`が挙げる`field-uniqueness`・
`reference-integrity`・`mutual-exclusion`・`payload-string-policy-reconciliation`を
伴う。段階1の最小形は段階2の完全形の部分集合であって競合しない。

この分け方で段階1が保証しないものを明示する。フィールドの一意性、他資産への参照整合、
相反するフィールドの同時指定の排除、およびD-8の文字列型制約とFR-015の任意選手名との
整合は、いずれも段階1では検査しない。段階1が保証するのは、列挙したフィールド以外を
payloadが持てないことと、必須フィールドの欠落が拒否されることだけである。
`operationResult`の`rejected-invalid-payload`は、この範囲での拒否を表す。

選手交代の`stateEffect`が比較面の全欄で`unchanged`になる点は、欠落ではない。
`stateFieldEffects`の10欄はいずれも状態量(回・表裏・カウント・アウト・走者・打順枠・
タイブレーク・試合終了・得点)であり、選手の識別子も守備位置も持たない。選手交代は
これらを変えないため、全面`unchanged`は「交代は状態中立である」という検証可能な主張に
なる。FR-011が定める以降のプレイの選手への紐づけは、出場履歴と成績帰属の側が持つ
関心であり、本契約の比較面ではない。この切り分けを各行の`remarks`へ残す。

`historyEffect`は`{pushes: false, kind: null}`とする。FR-006の補足が取消可能な操作を
「確定プレイ」と、FR-040を採用した場合の「状態補正」に限っており、選手交代を含めない
ためである。FR-011の補足が境界に挙げる「直前交代の取り消し」は、undoではなく同一枠への
再交代として記録する経路を指すものと解する。

#### ステップ62(タイブレーク開始)を段階2へ送る(2026-10-03 PO裁定・案B)

FR-009は、タイブレーク開始の結果がpayloadで指定した走者配置・先頭打者・回を反映する
ことを求める。これを規範行で表す手段が現行の機構に無い。

理由は2つある。第一に、要件書E-1が定める`FieldEffect`は`unchanged`、固定値の`set`、
整数の`delta`の3種に閉じており、payloadの指定値を参照する種別を持たない。第二に、
入力軸descriptorの`event.operationPayload`は`classification: boundary-partition`
であるが、その`boundaryValues`は`not-applicable`・`substitution`・`tiebreak-start`・
`game-end-declaration`・`adhoc-registration`・`state-correction`という操作種別の
タグだけで、payloadの中身を`precondition`で固定できない。

この2点により、置ける行はいずれも偽の主張になる。走者を固定値で`set`すると、別の
走者配置を指定したタイブレーク開始にも同じ結果を主張することになる。`unchanged`と
すると、走者が配置されないという条文に反する主張になる。

ステップ58までの穴とは強制の有無が違う。犠打失策の記録員判断、ピッチクロック違反の
違反主体、暴投・捕逸の分類は、いずれも`statFlags`が23件必須のexact型であるため値を
置かない選択肢がなく、規則の既定側または代表へ倒して差を記録した。本件は
`operationRows[]`に行を置かない選択ができるため、強制がない。

PO裁定により、ステップ62は段階2へ送る。`operationRows[]`へ
`operationKind = "tiebreak-start"`の行を作らず、`mustOperationCoverage`へ
`tiebreak-start`の対応も足さない。ステップ66の合格条件
「`mustOperationCoverage`が6種を覆う」は未達となるが、これは偽の主張を契約へ
入れないことと引き換えに受け入れる正直な未達であり、段階2の入口条件として扱う。

段階2で確定すべきものは2点である。第一に、`FieldEffect`がpayloadの指定値を参照する
表現、または`event.operationPayload`の境界値をpayload内容まで分割する表現のいずれか。
第二に、適用規則の発動条件を述語へ写す方法。現行の`Predicate`は軸とリテラルの比較で
あり、規則の発動回と現在回の関係を一般形で表す方法が未定義である。なお確定ゲートの
人間確認で「タイブレークの発動回 = 延長のみ」は決まっているが、これは発動回の範囲を
定めるものであって、規則条件を述語へ写す方法を与えるものではない。

ステップ63(試合終了宣言・FR-010)とステップ64(その場登録・FR-015)は本件の影響を
受けない。FR-010の状態効果は`state.gameEnded`を真にすることでpayloadに依存せず、
FR-015は選手の作成であって比較面の状態量を動かさないためである。両ステップは予定どおり
段階1で進める。

`historyEffect`については、FR-006の補足が取消可能な操作を「確定プレイ」とFR-040採用時の
「状態補正」に限るため、タイブレーク開始も`{pushes: false, kind: null}`となる。段階2で
行を作る際の前提として記録しておく。

#### ステップ63で見つかった`operationResult`の二重定義(2026-10-03・記録のみ)

`operationResult`は規範行の中に2箇所ある。ADR-003 D-8が定める`operationRows[]`の
8列のうちの1列と、同じくD-8が参照する`StateEffect`の`historyAndResult`が持つ
`operationResult`である。D-8はこの2つの関係を定めていない。

現在の4行はいずれも、列の側に`applied`または`rejected-precondition`を置き、
`historyAndResult`の側を`{kind: "unchanged"}`としている。これは列の側が当該行の
結果そのものを表し、`historyAndResult`の側は「この操作が比較面の
`operationResult`欄を変えるか」を表す、という読みに立っている。ただしこの読みは
条文にない。ステップ61で選んだ形をステップ63がそのまま踏襲したものであり、
根拠は整合性だけである。

両者が同じものを指すなら、列の値と`historyAndResult`の値が食い違う行を機械で
拒めるはずだが、現在そのような検査はない。別のものを指すなら、`historyAndResult`の
`operationResult`が何を表すかの定義が要る。どちらであるかを本タスクでは決めない。
段階2で`operationRows[]`の残りと`undoRows[]`を整備する際に、D-8の改訂を要するか
どうかも含めて判断する。

あわせて、`state.gameEnded = false`だけでは試合の準備中と進行中を機械的に区別
できない。ステップ63の`rejected-precondition`行は既に試合終了済みの試合へ再度宣言
する場合を前提としており、準備中への宣言を扱っていない。これも段階2の整備時に
区別が要るかを判断する。

いずれも本ステップでは規則を追加せず、未保証の範囲として記録するにとどめる。

#### ステップ65で置けたundo行と置けなかった3ケース(2026-10-03)

計画書はステップ65に、空履歴・履歴先頭の種別・連続undo・深さ`D`の4ケースを置いた。
このうち置けたのは空履歴の1件だけである。

空履歴は`history.depth = 0`を`precondition`に置き、`stateEffect`を比較面の全欄
`unchanged`、`historyEffect`を`{pops: 0}`、`operationResult`を`nothing-to-undo`、
`guaranteeMode`を`full-equality`とした。FR-006が「状態を変えず、取り消す対象が無い
ことを利用者へ示す」と定めるため、全欄`unchanged`は真であり、取り消す対象の差分に
依存しない。

残る3ケースはステップ62と同型の壁に当たる。D-8は`undoRows[]`の`stateEffect`を
「対象操作の差分を逆適用」するものと定めるが、D-11のdescriptorが持つ履歴文脈軸は
`history.depth`(0/1/2/D)・`history.composition`(top-confirmed-play ほか)・
`history.scenarioLength`(1/2/D/D+1)の3つで、いずれも「取り消す対象が確定プレイで
ある」ことまでしか表さず、その確定プレイが何だったかという差分を表さない。
`FieldEffect`は`unchanged`・固定値の`set`・整数の`delta`の3種に閉じているため、
固定値を置けば別の確定プレイを取り消す場合にも同じ結果を主張することになる。
したがって偽の主張を避けるため行を置かない。

本ステップで新たに見つかった定義上の穴が2件ある。第一に、空履歴の行にも`targetKind`が
必須であり、「対象なし」を表す値がない。現在の行は`confirmed-play`を置いているが、
これは取消可能種別の識別値であって実在する対象があるという主張ではない旨を`remarks`へ
明記した。第二に、ステップ63で記録した行の`operationResult`と
`stateEffect.historyAndResult.operationResult`の関係が未確定である点は、
`undoRows[]`でも同じく残る。本行は既存の`operationRows[]`と同じく内側を`unchanged`と
した。

`mustOperationCoverage`の`undo`写像はこの空履歴行1件を指す。schemaの
`requiredOperations`は`undo`に`rowLayer: "undoRows"`だけを求めdiscriminatorを持たない
ため、1行でも写像は成立する。ただしこれは適用側の行が揃ったことを意味しない。

#### ステップ66(`D`+1の行)を段階2へ送る(2026-10-03 PO裁定・案B)

ステップ66は`undoRows[]`へ`guaranteeMode = "liveness-only"`の行を置くものだが、
段階2へ送る。理由は2つあり、いずれも条文が決めていない事項を推測で埋めなければ
行を置けないためである。

第一に、`XC-09`の許可条件が入力座標で表せない。`XC-09`は
「`guaranteeMode = "liveness-only"`は、履歴文脈の**深さ**が`D`+1の行だけに許す」と
書くが、D-11のdescriptorの`history.depth`は`boundaryValues`が`0 / 1 / 2 / "D"`で
`"D+1"`を持たない。`"D+1"`を持つのは`history.scenarioLength`(`1 / 2 / "D" / "D+1"`)
である。ADR-003の変更履歴によれば、反映18周目で「履歴文脈は常に最大2要素」へ統一され、
反映20周目で履歴文脈は「有限にならない対象」として扱うと確定し、反映21周目で
「**シナリオ長**の`D`+1を(b)②の保証範囲外へ」と決めている。つまり`D`と`D`+1の区別が
生きているのはシナリオ長の側であり、`XC-09`が「深さ」と書いているのは文言の誤りで
ある。literalに読むと許可条件そのものが表現できない。

第二に、`liveness-only`の行の`stateEffect`が主張なのか必須列を埋めただけなのかを
条文が決めていない。`undoRows[]`の7列はすべてrequiredであるため`stateEffect`は値を
持たねばならないが、D-8は`undoRows[].stateEffect`を「対象操作の差分を逆適用」する
ものと定義している。`liveness-only`が出力同値を要求しないことはdesign.mdの引き渡し
方針が述べるが、それが`stateEffect`を比較対象から外すことまでは条文にない。全欄
`unchanged`を置けば、D-8の定義に反する主張になりうる。

この2点はいずれも推測で埋められる。`XC-09`の「深さ」をシナリオ長と読み替え、
`liveness-only`の`stateEffect`を比較対象外の埋め値と解すれば行は置ける。しかし
ステップ62とステップ65で「条文が言っていないことを主張しない」として行を置かな
かった以上、ここだけ推測を2つ重ねるのは一貫しない。PO裁定により置かない。

この判断の帰結として、ステップ66の合格条件3つはすべて未達となる。`XC-09`の充足、
出力同値を要求していないことの機械検査、`mustOperationCoverage`が6種を覆うこと、の
3つである。3つ目は本ステップ固有の問題ではなく、ステップ62を段階2へ送ったことの
波及で5種までしか写像が立たないことによる。

あわせて、`XC-09`の文言の誤りを記録する。これは承認済みの正本が確定ゲート12周を
通って矛盾を残した2件目である。1件目はD-8が`operationRows[]`に閉じた`payloadShape`を
必須とする一方、入力軸descriptorの`stage2ExternalConstraints`が
`event.operationPayload`の`closed-payload-schemas`を段階2へ送っている件である。
段階2で`XC-09`の改訂が要る。

#### フェーズCの段階2送りを1つの原因へまとめる(2026-10-03)

本タスクで段階2へ送った規範行は、ステップ62(タイブレーク開始)、ステップ65の3ケース
(履歴先頭の種別・連続undo・深さ`D`)、ステップ66(`D`+1の行)である。これらは別々の
判断として記録したが、原因は1つに集約できる。

**要件書E-1の`FieldEffect`は`unchanged`・固定値の`set`・整数の`delta`の3種に閉じて
おり、結果が「入力で指定された値」や「取り消す対象の差分」に依存する操作を表現できない。
かつ`precondition`の側でもその値を固定できない。**`event.operationPayload`の
`boundaryValues`は操作種別のタグ止まりで、履歴文脈の3軸は取り消す対象の種別止まりで
あり、いずれも中身を表さない。

したがって固定値を置けばその1例にしか当てはまらない結果を全ての場合に主張することに
なり、`unchanged`を置けば条文に反する。どちらも偽の主張になるため行を置かなかった。

段階2の入口条件は次の2つである。第一に、`FieldEffect`が入力の指定値や対象の差分を
参照する表現を得るか、`event.operationPayload`と履歴文脈軸の境界値を中身まで分割する
かのいずれか。第二に、`XC-09`の「深さ」をシナリオ長へ是正し、`liveness-only`の行で
`stateEffect`が比較対象かどうかを明示すること。前者が解ければステップ62・65・66の
すべてが解ける。

これに対し、ステップ55・57・58で段階2へ送った事項(犠打失策の記録員判断、ピッチクロック
違反の違反主体、暴投・捕逸の分類)は別の原因による。あちらは`statFlags`が23件必須の
exact型で値を置かない選択肢がなく、規則の既定側または代表へ倒したうえで差を記録した。
`operationRows[]`と`undoRows[]`は行を置かない選択ができるため、倒さずに送れた。

#### ステップ67〜68で`outcome`の語彙を条文から起こし直した(2026-10-03 PO裁定・案A)

ステップ67で`decisionRows[]`の列構成を定義した際、`gameEndDecision.outcome`の
enumを`clauseBranchRegister`の`GAME-END-*`4分岐から機械的に起こし、
`normal-end` / `extra-continue` / `limit-draw` / `tiebreak-continue`の4値で閉じた。
これは条文側の終了条件を確認しない定義であり、取りこぼしがあった。

要件書FR-005は「試合の適用規則(FR-014)で定まる**終了・コールド・サヨナラ**条件が成立」
したときに終了条件の成立を検知すると定める。さらに付録F-1の`DRAW-09`が上限回裏完了時の
引き分けを定める。4値のenumには**コールドもサヨナラも表す値が無かった**。計画書の
ステップ94が「`cases[]` — 終了判定(コールド・サヨナラ)」であることとも整合しない。

PO裁定により、enumを条文から起こし直して`cold-end`と`walk-off`を加えた6値とした。
enumは本タスクが定義した資産であり、条文に合わせる是正であって正本の改訂ではない。
既存4行の`outcome`は変えていない。

この是正により`COLD-08`の行が置けた。前周は「`COLD-09`の成立段の根拠集合も検知件数も
`decision`の5フィールドに無い」として`COLD-*`を1行も置かなかったが、精査すると
`endConditionDetected`はbooleanであるため「1件だけ検知する」は型として自然に満たされ、
「配列順や最初の一致に依存しない」は導出の性質であって行が主張する事柄ではない。
`COLD-08`(成立段が1件)は`tier-count:1`を前提に固定すれば一意に表せる。

残る穴が2件ある。

第一に、`COLD-09`(複数段が同時成立しても1件だけ検知)を置けない。
`gameEnd.coldConditions`の`tier-count:N`は**設定した段数**であって**成立した段数**では
なく、複数段が同時に成立したことを`precondition`で固定する入力軸が無い。段階2で
成立段数を識別する軸が要る。

第二に、サヨナラに対応する分岐IDが`clauseBranchRegister`の68分岐に存在しない。
FR-005が終了条件として名指しし、計画書のステップ94が`cases[]`で扱うにもかかわらず、
ステップ46の分岐列挙で拾われていない。`walk-off`はenumに入れたが、結び付ける分岐が
無いため行を置いていない。分岐台帳への追加はステップ46の射程であり、本ステップでは
行わない。

`COLD-01`〜`COLD-06`は段ごとの成立・未成立の中間判定であり、終了判定の結果ではない。
`decisionRows[]`には置かず、schemaへ中間分岐として明示し、結果行へ誤登録すると赤に
なる負例を置いた。`COLD-07`(設定が空または成立0件なら未成立)も同じく中間判定である。

`DRAW-*`の帰属は前周の判断を維持する。`DRAW-01`〜`DRAW-03`は不正な規則設定の期待拒否で
`validationErrors[]`が関係するが、ADR-003:293はそれを規範行の代替と認めない。
`DRAW-04`は有効設定の宣言、`DRAW-05`〜`DRAW-10`は実行時の`normative-case`である。
特に`DRAW-05`の途中宣言による引き分けを、上限到達を意味する`limit-draw`へ割り当てるのは
誤りであり、別の表現が要る。

#### ステップ70の手作業fixtureが覆えた分岐と覆えない16件(2026-10-03)

状況判定側の分岐42件(`SO-01`〜`05` / `RBI-01`〜`09` / `INT-01`〜`07` /
`ADV-01`〜`04` / `OUT3-01`〜`05` / `XC-*` 12件)に対し、手作業fixtureを26件作った。
合格条件は「該当分岐に最低1件」だが、16件を覆えていない。

覆えなかった16件の内訳と理由は次のとおりで、いずれも既知の段階2送りの帰結であり
新しい問題ではない。

`OUT3-01`〜`05`(5件)は第3アウト種別の観測入力が、`XC-13`(1件)は23フラグの
導出表が、いずれも確定ゲートの第2回PO射程縮小(2026-09-26)で段階2へ送られている。
期待値を置こうとすれば観測入力の形を先取りすることになる。

`INT-01`・`INT-03`・`INT-05`・`INT-07`(4件)は、ステップ58で妨害系3種の代表分岐を
`INT-02`(打撃妨害・罰則採用)・`INT-04`(走塁妨害・妨害走者へのプレイあり)・
`INT-06`(守備妨害・打者をアウト対象に含む)に選んだため、規範行が存在しない。
`clauseBranchRegister`は7分岐すべてを持つが、規範行は3件である。

`RBI-01`〜`RBI-05`(5件)は、記録員の因果判断に依存する。
descriptorの`stage2ExternalConstraints.payloadAxisIds`は
`event.perPitch.rbi.runnerContinuityByRunner`と
`event.perPitch.rbi.wouldScoreWithoutErrorByRunner`を含み、要件書v2.10の射程宣言も
`RBI-02`〜`RBI-05`の因果判断を記録者の観測入力として段階2へ送っている。
`RBI-01`はステップ56で記録したとおり、フォース連鎖の定義と食い違っており適用条件が
機械的に導けない。覆えたのは`RBI-06`(本塁打の打点)・`RBI-08`(犠飛等)・
`RBI-09`(該当なし)の3件である。

**本節の初版は`RBI-07`を記録員の因果判断に依存する群へ含めていたが、これは誤りで
あった**(2026-10-03・ステップ72で判明)。要件書の`RBI-07`は「満塁で四球、死球、
打撃妨害または走塁妨害により打者が走者となり、押し出された走者に本塁が与えられた
場合は、打点に算入する」であり、因果判断を含まない機械的な条件である。`RBI-07`に
fixtureが無い理由は、対応する規範行が無いこと(満塁の押し出しを表す行を置いていない)
と、軸間組合せ規則が段階2へ送られていることである。ステップ72の免除宣言はこの訂正後の
理由を記録している。

fixtureが主張するのは展開器からの独立だけであり、分岐台帳からの独立は主張しない
(design.md 8-1)。現段階の機械検査は型・典拠ID・分岐帰属・行参照・正例の主張と
既存行との一致・`XC`負例が制約に違反することまでで、**展開結果との完全一致とdigestの
凍結は未実施**である。分岐の意味的完全性と、典拠が期待値を支持するかは人間統制に残る。

残る課題として、現在のfixtureは分岐ごとの主張形式であり、ステップ73の凍結と
ステップ77の展開結果との完全一致の前に、完全な期待ケースの形を定める必要がある。

#### 手作業fixtureの形式を完全な期待ケースへ揃える(2026-10-03)

ステップ70(状況判定)とステップ71(終了判定)で、fixtureの形式が食い違った。

ステップ70は分岐ごとの部分的な主張の形である。`expected.assertions`へ
`{pointer: "/statFlags/三振", value: true}`のようにJSON Pointerと期待値の対を並べる。
ステップ71は完全な期待ケースの形で、`case.inputCoordinate`へ入力軸の値を全件置き、
`case.decision`へ結果の5フィールドを全件置く。

ステップ77は「展開器の出力がfixtureと全分岐で完全一致(不一致1件でfail)」を要求する。
ここでいう完全一致は、fixtureの`caseId`・`branchId`・入力座標全体・期待値全体と、
展開器が出す対応ケースとの一致である。`provenance`と条文例は比較対象外とする。
**部分的な主張の集まりでは、この意味の完全一致を判定できない。**主張していない
フィールドについて展開器が何を出しても一致と見なされ、第4層の遮断が空洞化する。

したがってステップ70の26件は、ステップ73の凍結前に完全な期待ケース形式へ作り直す。
凍結してから作り直すと、7.7-2が要求する追記のみの更新履歴へ、形式変更という本質的
でない記録が残る。design.md 8節の表が手作業fixtureへ求めるのは「展開結果との完全一致
/ digestの凍結」であり、形式の確定は凍結より前にある。

あわせてステップ71が、終了判定の入力座標に関する定義不足を1件見つけた。
`GAME-END-NORMAL`の行は`gameEnd.coldConditions`を`tier-count:0`(コールド段なし)と
しながら、非同点を表す`state.score`に`home-lead:M`を用いる。`M`はコールド条件の段が
持つ点差であり、付録F-1は`M`を1以上と定めて`DRAW-02`で値域を検証する。段が0件のとき
`M`が何を指すかは条文が定めていない。軸の`boundaryValues`としては
`home-lead:M`が合法であるため形式検査は通るが、意味は宙に浮く。規範行とdescriptorは
変更せず、記録のみとする。

#### 代表値の選択規則と、暫定記録を更新できることの是正(2026-10-04 PO裁定)

ステップ76で、述語を満たす値が複数あるとき展開器と手作業fixtureが別の値を選ぶことが
判明した。`GAME-END-NORMAL`の前提は`not(state.score == tie)`であり、`state.score`の
7境界値のうち`tie`以外の6値すべてが該当する。展開器はdescriptor順の先頭である
`away-lead:M+1`を、手作業fixtureは`home-lead:M`を選んでいた。どちらも行の前提を
満たすが入力座標が一致せず、ステップ77の「展開結果とfixtureの全分岐で完全一致」が
成立しない。

代表値の選び方を定める規則は、要件書にもADRにも無い。したがって本規則は本タスクが
決める実装上の約束である。`representative_selection_policy_v1.json`へ宣言し、
`authority`を`implementation-convention-not-requirements-or-adr`として機械可読な形で
明示した。`rationale`の末尾に「野球規則上の優先順位を意味しない」と書いたのは、
`away-lead:M+1`が選ばれていることに意味があると誤読されないためである。

規則はdescriptorの軸順と境界値順で述語を満たす最初の候補を採る。`eq`の指定値は固定し、
`in`・`not`・`and`・`or`・`gte`・`lte`は述語で候補を絞ってから列挙する。制約の無い軸は
宣言順の先頭を採る。両展開器がこの宣言を読んで動き、規則を直書きしていない。
`allowedReadPaths`へ追加したのは規則資産のみで、手作業fixtureと分岐対応表は
引き続き読まない。`claimBoundary.notGuaranteed`の7項目も維持した。

fixtureの変更は1件だけで済んだ。`GE-GAME-END-NORMAL`の`state.score`を
`home-lead:M`から`away-lead:M+1`へ揃えた。状況判定側の座標変更は0件、期待値は全31件
とも変更していない。実測では、fixtureを元の座標へ戻すと
`test_positive_manual_fixture_inputs_follow_representative_policy`が赤になる。
展開器とfixtureが同じ規則に縛られており、どちらか一方を書き換えて一致させることが
できない。

この作業の途中で、ステップ73で作った凍結検査器の設計の穴が判明した。bootstrap記録を
コミットした時点で検査器がHEADを既存履歴として読むため、暫定記録が不変になっていた。
更新すれば「追記のみでない」、据え置いて digest を変えれば「記録なしで基準を変更
できない」、追記にはPR番号が要る、と出口が無い。

既存機構は暫定記録という状態を正式に持っている。`frozen_history.py`は
`RESERVED_MARKER_TOKENS`として`PENDING`・`未承認`等を認識し、
`未承認(PR #<番号> のレビュー待ち)`を暫定値として判定する。
`check_tenant_boundary_bypass.py`は`source_commit`がPENDINGなら`approved_by`も
PENDINGでなければならないという整合検査を持つ。develop側にも
「記録を作り直す」コミットが複数あり、PR受理前に暫定記録を作り直すのは確立した運用で
ある。ステップ73の検査器が既存機構より厳しく、その厳しさに根拠が無かった。

PO裁定により検査器を是正した。更新を許すのは記録が暫定である場合に限り、受理済みの
記録は従来どおり追記のみとする。暫定値から人名へ書き換えてdigestを変える経路は塞いだ。
実測では`approved_by`だけを人名に書き換えると「暫定記録の整合が崩れている」で拒まれる。
受理済みに見せかける道を閉じたうえで、PR受理前の作り直しを許す形である。

#### ステップ79で判明した`requiredSet`差分の2つの構造的な穴(2026-10-05 PO裁定)

計画書はステップ79〜95の合格条件を「`requiredSet`の①②両方との差分が空」と定める。
ステップ79の着手時に、①も②もこの字句どおりには成立しないことが実測で判明した。

①行の要求は47件で、規範行は42行である。差が5件ある。内訳は
`batting-result.dropped-third-strike`の`out`側1件、
`secondary-result.batting-interference`の2件、`secondary-result.obstruction`の1件、
`secondary-result.offensive-interference`の1件で、いずれも分割規則が2〜3区分を要求する
のに規範行が1行しか無い。`dropped-third-strike`の行の備考は「アウト成否の観測入力が
段階2のためout側は未充足(GAP-08)」と自ら書いている。観測入力が段階2にある以上、
段階1で規範行を足すことはできない。規範行を足さずに`cases[]`側で埋めることも
ADR-003:293が禁じている(規範行が正であり`cases[]`は派生物である)。したがって
字句どおりの「差分が空」は段階1では到達不能である。

②入力座標の要求は150件で、descriptorの割当は行層(`matrixRows`・`operationRows`・
`undoRows`)までしか無い。どの要求をどの行カテゴリが埋めるかという割当は、要件書にも
descriptorにも定義が無い。150件の適用先は`matrixRows`専用76件、他層と共有63件、
`matrixRows`対象外11件である。カテゴリ別の残件数が確定できないため、カテゴリ単位の
ステップで「②の差分が空」を判定する手段が無い。

PO裁定により、合格条件の読みを次のとおり確定した。計画書の表は改訂しない。

①は「宣言済みの未充足を除いた差分が空」とする。未充足5件を
`required_set_coverage_declaration_v1.json`へexact-setで宣言し、各件が`gapRegister`の
`open`エントリに典拠を持つことを機械検査する。典拠は分割規則の`sourceClauseIds`から
`req:`接頭辞を外した集合と、GAPの`clauseIds`∪`branchIds`との交差が空でないことで引く。
`rowIds`は使わない(この裁定時点ではステップ69がPR後送りのため空であった)。実測では
`dropped-third-strike`の`out`はGAP-08へ、妨害系4件はGAP-07へ解決する。宣言が実際の
未充足集合とずれたら赤になるので、規範行を1行減らして穴を隠す経路も、未充足を
黙って増やす経路も塞がる。

②はカテゴリ別に分けず、被覆集合を全体で1つ持つ。各ステップの合格条件は
「本周の被覆集合が前周の被覆集合を包含し、後退しないこと」+「件数とdigestの記録」
とする。記録は設計書7.7-2に従い1ステップ1記録の追記のみとする。全体の差分が空になる
exact検査は、計画書がもともとその配線を置いているステップ102
(検査配線 — `requiredSet`差分(①②))で発火させる。割当規則を新たに発明するより、
正本にある事実だけで組める形を採った。

①の検査には「どの規範行がどの区分を覆っているか」の判定が要る。規範行には区分IDが
書かれていないため、`rowPartitionObservations`として、区分を読み取る信号(`expected`の
`batterDestination.kind`、あるいは前提の`event.perPitch.interferenceRuling`の値)を
資産側へ宣言した。代表値の選択規則と同じく本タスクが決めた実装上の約束であり、要件書に
根拠を持つものではない。信号の宣言が実態とずれれば未充足集合がずれ、exact-set検査が
赤になる。

この裁定に伴い、展開器に被覆展開モードを足した。代表値展開(1行1件)は不変で、
ステップ77の展開結果とfixtureの照合は従来どおり42件で緑を保つ。被覆展開は②の入力座標
要求を埋めるために同じ行から追加の`cases[]`を出す別モードであり、照合器の前提を
変えない。

ステップ82(`matrixRows` 42行が出そろった時点)で、②にも同じ構造の穴があることが
判明した。②の150件のうち100件を被覆した時点で残り50件あり、そのうち妨害裁定
(`event.perPitch.interferenceRuling`)の3値は、対応する規範行が無いため現行行から
正当に被覆できない。①で宣言した未充足4件(GAP-07)と同じ原因である。ステップ102の
全体exact検査でも、①と同様に「GAP典拠を持つ未充足を宣言で除いた差分が空」とする
必要がある。残り50件の内訳と、そのうち何件がGAP典拠で説明され何件が後続ステップ
(操作行・undo行・終了判定)で埋まるかは、ステップ102の着手時に実測して確定する。

被覆展開の過程で、軸の値を別の行へ接ぎ木してよいかという問題も出た。妨害裁定の値を
無関係な結果行の入力座標へ上書きすると、意味のない座標ができる。この束縛を展開器へ
直書きするのは設計書7.7-1に反するため、`coverage_row_binding_policy_v1.json`へ
軸ID・条文ID(FR-004・INT-01〜INT-07)・束縛されない値(`not-required`)・理由を宣言し、
展開器がこれを読む形にした。宣言の条文IDがdescriptorと一致しなければ展開器が失敗する。
「軸がいずれかの行の前提述語に現れるなら行に束縛される」という一般規則も検討したが、
実測で②が100件から99件へ後退し、記録済みの`not-required`が失われるため採らなかった。

ステップ83で`matrixRows` 42行の`cases[]`が出そろった時点の②の残件は46件で、内訳は
次のとおりである。

| 分類 | 件数 | 内訳 |
| --- | ---: | --- |
| どの規範行の前提も認めない | 4 | `state.count.strikes=1`・`state.count.balls=1`・同`=2`・`state.runners=second-third` |
| 前提は通るが接ぎ木が無意味 | 31 | `rbi.*` 11・`runnerAdvanceOverridesByRunner` 6・`thirdOutTimingByRunner` 4・`runnerEventPayload` 4・`interferenceRuling` 3・`officialScoringPayload` 3 |
| 操作行・undo行(ステップ84〜88) | 11 | `event.operationKind` 6・`event.operationPayload` 5 |

31件は、当該軸を前提で制約していない行であれば形式上どの値でも通る。たとえば
`batting-result.ball`の行へ`rbi.wouldScoreWithoutErrorByRunner`の
`single-runner-would-score`を乗せれば②の要求は埋まるが、見逃し三振の投球に打点の
裁定を付けた座標に意味はない。ステップ82で`coverage_row_binding_policy_v1.json`へ
出した行束縛と同じ問題であり、**見せかけの被覆は採らない**。31件の軸は、対応する
規範行が無いために埋まらないものである。軸ごとの典拠の目処は
`runnerAdvanceOverridesByRunner`と`interferenceRuling`がGAP-07(ADV-01〜04・
INT-01〜07)、`rbi.*`と`thirdOutTimingByRunner`がGAP-09(RBI-01〜09)で、
`runnerEventPayload`と`officialScoringPayload`の典拠は未確定である。

4件は、どの規範行の前提も認めない。規範行の前提が状態軸を特定の値に固定しており、
ストライク1・ボール1・ボール2・二三塁を前提に置く行が1つも無いためである。

確定はステップ102(検査配線 — `requiredSet`差分(①②))で行う。そこまでに
ステップ84〜88で11件が埋まる見込みで、残る35件の扱い — ①と同じく
GAP典拠つきの宣言除外とするか、段階2へ送るか — はステップ102の着手時に
実測値をそろえて決める。

#### ステップ92で判明した終了判定`requiredSet`の規模差(2026-10-05 PO裁定)

計画書はステップ92〜95の合格条件を「`requiredSet`との差分が空」と定める。ステップ92の
着手時に、終了判定の`requiredSet`が3844件あるのに対し`decisionRows`は5件しか無く、
字句どおりには成立しないことが実測で判明した。

到達可能性で切り分けた内訳は次のとおりである。

| 区分 | 総数 | 到達可能 | 到達不可 |
| --- | ---: | ---: | ---: |
| 終了規則の境界値ペア | 225 | 16 | 209 |
| 境界値 × 状態・イベント軸値 | 3588 | 998 | 2590 |
| F-1条文分岐 | 19 | 1 | 18 |
| 不正値拒否 | 12 | — | — |
| 計 | 3844 | 1015 | 2817 |

裁定の提示時にはこの表を到達可能1128件・到達不可2704件としていたが、過大だった。
1つのcaseが実現できるのは**同じ行**が固定する値の組だけであり、別々の行が固定する値を
跨いだ組は作れない。境界値ペアは23件ではなく16件、境界値×状態・イベント軸値は1104件
ではなく998件である。後者は、行が状態軸を前提で固定している場合にその軸の他の値へ
届かないぶんも引いている。裁定の骨格は変わらない。

到達不可の原因は①と同じ構造である。`decisionRows` 5件が固定する`gameEnd`軸値は
26件中8件しかなく、残り18軸値を前提に置く行が存在しない。境界値×状態・イベント軸値の
3588件は26軸値×138軸値の直積であり、8軸値しか届かないうえ、行が前提で固定している
状態軸ではその固定値以外へ届かないため、998件だけが到達可能である。
条文分岐も`COLD-08`の1件だけに行があり、残り18件(`COLD-01`〜`07`・`09`、
`DRAW-01`〜`10`)は行が無い。典拠は`COLD-*`がGAP-03、`DRAW-*`がGAP-04で、
どちらも`open`である。

PO裁定により、合格条件の読みを次のとおり確定した。計画書の表は改訂しない。

第一に、ステップ79と同じく「到達できない要求を宣言で除外した差分が空」とする。宣言は
exact-setで機械検査し、除外が1件増えたら赤になる。

第二に、除外は1件ずつではなく**規則で**宣言する。2704件を個別に並べるのは現実的でない
ため、「どの`decisionRows`も固定していない`gameEnd`軸値に依存する要求は除外」という
規則を資産へ置き、宣言するのは軸値18件と条文分岐18件だけにする。行が増えれば除外は
自動的に縮む。個別列挙にしないのは、列挙が規範行の変更に追随せず腐るためである。

第三に、到達可能な1015件は実際に埋める。ステップ92時点の充足は34件である。
ステップ93〜95で分岐を足しながら埋め、ステップ103(検査配線 — 件数・digest)で締める。
到達可能分を素通りさせない。

第四に、不正値拒否12件はステップ92〜95の判定から外す。これは`validationErrors[]`の
話であり、計画書のステップ96「`validationErrors[]`を分離」が担当する。正常系の
`cases[]`では原理的に埋まらない。

状況判定側のステップ79の裁定と骨格は同じである。違うのは、除外を個別宣言ではなく
規則で宣言する点と、不正値拒否を別ステップの担当として切り出す点の2つである。

### 7-1. 成績計上フラグの導出元(8 周目までの記述を補正)

v9 までは「付録A-2 / A-2b / A-3 / A-3b / A-5 から逆算」としていたが、**それだけでは足りない**。
**FR-022 の当日集計 9 項目**(打席数・打数・安打・**打点**・四球・死球・三振・犠打・犠飛)を導出元に加える。
`:443` が「上記の行から導出する(別実装で数え直さない → NFR-018)」と定めており、
**この 9 項目は付録E-1 の成績計上フラグから導けなければならない**。

### 7-2. `gapRegister` の 5 段と**所有**(7 周目 P1-4 の是正)

```
gapId / state(open → resolved の片方向)
clauseIds[] / branchIds[] / rowIds[] / fixtureCaseIds[] / generatedCaseSelector
```

v7 は 5 段を定義したが、**誰がいつ埋めるか未所有**だった。→ **段ごとに所有ステップを置く**。

| 段 | 埋めるタイミング |
| --- | --- |
| `clauseIds` | 条文化の直後(フェーズ A) |
| `branchIds` | **`clauseBranchRegister` の作成後** |
| `rowIds` | **規範行 4 層の完了後** |
| `fixtureCaseIds` | **手作業 fixture の凍結後** |
| `generatedCaseSelector` | **`cases[]` の生成完了後** |

### 7-3. 状態別の検査述語(8 周目 P1-4 の是正)

v8 は「どの段で途切れても fail」と無条件に書いており、**`open` の途中状態**(ステップ 25 で `clauseIds` だけ、
44 で `branchIds` まで…)を**ステップ 41 の検査が拒否してしまう**。
→ **状態別に述語を分ける**。

| 状態 | 述語 |
| --- | --- |
| **`open`** | **連続した prefix だけを許可**(`clauseIds` → `branchIds` → `rowIds` → `fixtureCaseIds` → `generatedCaseSelector` の順に、先頭から途切れなく埋まっている)。**途中段の飛ばし**・**存在しない参照**・**既に埋めた段の逆方向不一致**は **fail** |
| **`resolved`** | **5 段すべてが必須**かつ**全段で双方向一致** |

ここでいう**双方向一致**は、`gapRegister` から所有資産を引いた参照集合と、所有資産から当該
`gapId` へ帰属させた参照集合が一致することを指す。片方にだけ存在する参照は fail とする。
`clauseIds` は `open` 中は要件書での実在を検査し、`resolved` への遷移時は後続資産から導出した
逆方向帰属も含めて全5段を突合する。参照元が未整備の段を先に埋めた場合は判定不能として fail とする。

**各所有ステップ(44 / 66 / 71 / 94)の合格条件に、実資産へこの検査を適用して緑になることを含める。**

#### ステップ69の規範行同定と帰属(2026-10-05)

規範行には共通の行 ID が無い。`freezeBaseline.criteria.gapRegister.rowLayers`に
4層の資産パス・自然キー・帰属根拠の取得先を宣言し、次のIDを行内容から作る。
`matrixRows`は`eventKind`と`resultId`、`operationRows`は`operationKind`と
`precondition.axisId/value`、`undoRows`は`targetKind`と同じ前提軸・値、
`decisionRows`は`branchId`を使い、先頭に層名を付ける。全54行で重複がないことを
検査する。特に`operationKind`は各操作で適用・拒否の2行があるため、単独では
同定できない。`state.gameEnded=false/true`を含む前提を加えると6行を一意に引ける。

行からGAPへの帰属は、行の`remarks`に**完全な**`gapId`または当該GAPの
`branchIds`が明記される場合、終了判定行自身の`branchId`が一致する場合だけ採る。
終了判定行の`sourceClauseIds`は、GAPの`clauseIds`との共通典拠も確認する。
`F-1`のような一般条文だけではGAP-03/04のどちらかを特定できないため、
条文一致だけからは帰属させない。備考中の言及はそのGAPとの**関連**を示し、
当該分岐の被覆やGAPの解消を主張しない。規範行の追加・備考の変更と
`gapRegister.rowIds`の片方だけが変われば双方向検査で失敗する。

実測の`rowIds`件数はGAP-01〜09の順に`0, 0, 2, 4, 0, 0, 20, 5, 3`。
GAP-01/02/05/06には行備考または行自身の分岐IDから確定できる帰属が無く、
推測で埋めず空配列とした。`rowIds`はschemaで全エントリの必須キーであり、
空配列も段の未充填を表す。後続の`fixtureCaseIds`と
`generatedCaseSelector`を空のままにする限り、これらの`open`エントリも
連続prefixの述語に従う。暫定の凍結基準記録はPR #81のレビュー待ちを明示する。

#### ステップ97で`resolved`にできない4件(2026-10-05 PO裁定)

計画書はステップ97の合格条件を「全 9 エントリが 5 段すべてを持ち双方向一致。
**全エントリが`resolved`**。実資産へ`resolved`の検査を適用して緑」と定める。
着手時に、GAP-01・02・05・06 の 4 件が`resolved`にできないことが判明した。

7-3 の`resolved`の述語は「5 段すべてが必須かつ全段で双方向一致」であり、ステップ69 の
記録は「`rowIds`は schema で全エントリの必須キーであり、**空配列も段の未充填を表す**」と
書いている。この 4 件は`rowIds`も`fixtureCaseIds`も空であるため、`resolved`へ遷移させると
自らの述語に反する。

4 件の中身はいずれも**規範行が存在しない分岐**である。

| GAP | 分岐 | 内容 |
| --- | --- | --- |
| GAP-01 | `XMARK-01` | X 表記。ステップ95 で`decision`に対応フィールドが無いことを記録済み |
| GAP-05 | `XMARK-01`〜`03` | 同上 |
| GAP-02 | `XC-13` | 交差制約 |
| GAP-06 | `OUT3-01`〜`05` | 第 3 アウトの成立順。②の未充足として残っている軸 |

行も fixture も作れないものを`resolved`にするのは偽の主張である。ステップ62(タイブレーク
開始)・ステップ65(undo 3 ケース)・ステップ66(`D`+1 の行)・ステップ94(サヨナラ)で
「条文が言っていないことを主張しない」として行を置かなかったのと同じ筋であり、ここだけ
例外にする理由が無い。

PO裁定により、GAP-03・04・07・08・09 の 5 件を`resolved`へ遷移させ、残り 4 件は`open`の
まま据え置く。4 件には 5 段を埋められない理由を典拠つきで記録する。

合格条件のうち「実資産へ`resolved`の検査を適用して緑」は満たせる。`resolved`の 5 件へ
5 段必須と双方向一致を、`open`の 4 件へ連続 prefix を適用して、両方を緑にする。
満たせないのは「全エントリが`resolved`」の一語だけである。

検討した代案は 2 つある。第一に`resolved`の述語を緩めて空配列を許す案は、自ら置いた検査を
骨抜きにし「追跡が完了した」という主張の意味を失わせるため採らない。第二に空の段を埋める
案は、存在しない行・fixture への参照を作ることになり ADR-003:293 と双方向一致の両方に
反するため採らない。

あわせて、除外宣言の典拠 GAP に対する検査器の述語を`state == "open"`から
「`gapRegister`に実在し典拠が交差すること」へ緩めた。ステップ79 の①の未充足宣言と
ステップ93 の終了判定の条文分岐宣言が`open`を要求しており、本周の`resolved`遷移と
衝突するためである。`resolved`は 7-3 のとおり追跡完了であって穴の充足ではないため、
除外の正当化に必要なのは GAP の実在と条文・分岐の典拠の交差であり、記録の完成度では
ない。見逃しを防いでいるのは除外集合の exact-set 検査であり、そちらは弱めていない。
`gapId`が`gapRegister`に存在しない場合は引き続き fail とする(fail-closed)。

##### ステップ97の実装記録(2026-10-05)

`generatedCaseSelector`は`sourcePath`・`rowOwnerGapId`・`caseCount`の述語とした。
検査器は各`cases[].rowRef`の層と自然キーを規範行へ解決し、規範行の備考または
終了判定の`branchId`から独立に求めたGAP帰属でcaseを選ぶ。`caseCount`は片側だけの
case増減を検出する。生成`caseId`の列挙やドメイン計算の再実装はしない。
実測の選択件数はGAP-03/04/07/08/09の順に68/136/39/12/6件である。
GAP-03/04は終了判定170件、GAP-07/08/09は状況判定96件から選ぶ。
条文段の逆方向帰属は`gap_register_schema_v1.json`の`clauseGapOwnership`に
独立宣言し、要件書でのID実在と`gapRegister.clauseIds`との双方向一致を検査する。
この宣言の変更もGAP側だけの変更も赤になる。

| 据え置き | 典拠と規範行が存在しない理由 | 5段の現在地 |
| --- | --- | --- |
| GAP-01 | 要件書FR-020の`XMARK-01`は開始済み攻撃回のスコアボード**表示セル**を決める。`game_end_coverage_declaration_v1.json`のX表記除外とステップ95の記録どおり、現行`decision`にセル表示値・X判定値がない。終了判定行の5フィールドではこの分岐の正誤を表せず、行・fixtureを置けない | 条文・分岐まで。`rowIds=[]`、`fixtureCaseIds=[]`、selector=`null`、`open` |
| GAP-02 | 要件書付録E-1 `XC-13`は23件の`statFlags`を他列と入力から導出する**原則**。要件書付録E-1の`XC-13`とADR-003 D-11は、キー別の必要十分条件・負例を段階2へ委任している。現時点で特定の導出結果を規範行とfixtureに確定できない | 同上 |
| GAP-05 | FR-020・FR-005の`XMARK-01`〜`03`は開始済み／未開始の裏／将来回の表示セルを区別する。GAP-01と同じく現行`decision`に表示セルの出力がなく、3分岐に対応する規範行・fixtureを確定できない | 同上 |
| GAP-06 | 要件書A-1の`OUT3-01`〜`05`は第3アウト時の有効得点を成立順で判定する。要件書v2.10変更履歴とADR-003 D-11が第3アウト種別と記録員判断の観測入力を段階2へ送り、設計書7章の手作業fixture記録も当該5件を未収容とする。現行入力で成立順を一意に判定できないため行・fixtureを作れない | 同上 |

5件は5段を満たして`resolved`、4件は連続prefixのまま`open`である。
計画書ステップ97の原文を字義どおりに読むと、「全9件が5段すべて」と
「全エントリが`resolved`」はともに**未達**。PO裁定の代替判定では前者を
5件の5段必須・4件の連続prefixへ読み替えて検査し、全資産が緑になった。
凍結基準の受理は`未承認(PR #81 のレビュー待ち)`であり、この記録は受理済みを主張しない。

## 8. oracle 循環の遮断

| 層 | **機械が保証すること** | **人間統制** |
| --- | --- | --- |
| ① 由来の記録 | 典拠 ID の実在 / 作成者 ≠ 独立確認者 / 宣誓項目の充足 | 実際に独立確認したか |
| ② 依存遮断 | **実行可能な導出器・展開器のファイル読み取りのみ** | 手作業時に何を読んだか |
| ③ 人間確認 | digest の一致 / 宣誓内容の存在 | 別人による条文からの直接レビュー |
| ④ 手作業 fixture | **展開結果との完全一致** / digest の凍結 | 分岐の意味的完全性 |

**① `provenance` の宣誓と保証境界**:

- ①の宣誓項目は次の3件の閉じた一覧とする。(a) **独立確認者が典拠の条文そのものから確認し、導出物・生成物・他者の要約を根拠にしていないこと**、(b) **独立確認者が作成者の作業結果を見る前に典拠を読んだか、見た場合はその事実を記録したこと**、(c) **典拠が主張を支持すると独立確認者が判断したこと**。
- 機械が保証するのは、典拠種別ごとに下表で宣言した範囲の参照検査、記録上の作成者と独立確認者が異なること、および3宣誓項目の記録が充足することまでとする。**実際に独立確認したか、宣誓が真実か、および典拠が主張を支持するかは人間統制**であり、機械保証に含めない。
- ①は「どう作ったか」の由来記録である。③は「approved とする成果物を別人が条文から直接レビューしたか」の署名記録であり、③の宣誓はステップ43が所有する。①の `provenance` に③の宣誓を混ぜない。

**③ 人間確認の署名記録と保証境界**:

- ③の署名記録は対象成果物へ埋め込まず、`contracts/state-transition/human_review_signature_schema_v1.json` に従う**独立文書**とする。対象 JSON 文書全体の RFC 8785 JCS + SHA-256 digest を記録して自己参照を避ける。記録は、署名 ID、対象のリポジトリ相対 path と digest、記録上の成果物作成者 ID と確認者 ID、記録日、確認範囲、記録された方法、および宣誓記載を持つ。
- 機械が保証するのは、必須記録の形式、対象 path の宣言領域内での解決、**署名の記載と対象 digest の一致だけ**である。別人性については記録上の作成者 ID と確認者 ID が異なることまで、宣誓については閉じた宣誓 ID と充足応答が記載されていることまでを検査する。
- 実際にレビューしたか、確認者が実人物として別人か、典拠条文から直接レビューしたか、記録された作成者・確認者・日付・範囲・方法と宣誓が真実か、および判断が正しいかは**人間統制**であり、機械保証に含めない。①の `provenance` は作成由来、③の独立署名記録は approval 前の確認記録であり、相互に代用しない。
- 本記録は、開発ハーネス設計書 **6.3 の PR 側の逐行確認実施記録とは別**である。6.3 の記録は PR 運用規律であり本検査の対象にせず、本署名記録も 6.3 の実施記録を代替しない。

### 8-0. 導出器・展開器の依存遮断

本節でいう**導出器**は、ADR-003 D-6 の `requiredSet` を独立に作る実行可能な処理、すなわち
①行の要求、②入力座標の要求、および終了判定の要求を作るステップ48〜50の処理を指す。
ステップ41は導出器の実体を先取りせず、その3役割の読み取り許可集合と実行時トレース機構を置く。

読み取り許可集合の正は
`contracts/state-transition/deriver_dependency_policy_v1.json` とする。①行の要求は要件書、共有語彙の
seed / manifest、および5-1の機械可読な軸分類・分割規則、②入力座標の要求は入力軸 descriptor、
終了判定の要求は要件書と入力軸 descriptorだけを読める。検査は導出器の呼出区間で CPython の
`open` 監査イベントとして観測したパスを、
解決後のリポジトリ相対パスに戻して当該役割の allowlist と突合する。リポジトリ外・解決不能・
allowlist 外の読み取り、および追跡されない子プロセスの起動は fail とする。

**この検査が主張するのは、実行可能な導出器の追跡対象呼出区間で観測したファイル読み取りだけ**
である。展開器はステップ42の所有であり、本宣言の保証対象ではない。また、手作業で何を読んだか、
allowlist 内の資産の意味的独立性、実行されなかった分岐、追跡開始前に開かれたファイル記述子からの
読み取り、CPython の監査イベントを発生させない native 読み取り、および環境変数・ネットワーク等の
非ファイル入力は保証しない。これらを確認済みまたは異常なしと扱ってはならない。

本節でいう**展開器**は、ADR-003 D-6 の正である規範行から派生物の `cases[]` を作る実行可能な処理、
すなわち状況判定と終了判定を展開するステップ75・76の処理を指す。ステップ42は展開器の実体を
先取りせず、両役割の読み取り許可集合と、導出器と共通の実行時トレース機構を置く。

展開器の読み取り許可集合の正は
`contracts/state-transition/expander_dependency_policy_v1.json` とする。状況判定の展開器は入力軸
descriptor、共有語彙 seed / manifest、状況判定契約、および `clauseBranchRegister` だけを読める。
終了判定の展開器は入力軸 descriptor、終了判定契約、および `clauseBranchRegister` だけを読める。
契約と register の実体は後続の所有ステップで作成するが、展開器実装前に依存先のリポジトリ相対パスを
宣言しておく。手作業 fixture はいずれの allowlist にも含めない。

**この検査が主張するのは、実行可能な展開器の追跡対象呼出区間で観測したファイル読み取りだけ**
である。手作業 fixture の独立性について主張するのは展開器からの独立だけであり、fixture が各分岐を
見て作られる **`clauseBranchRegister` からの独立を主張しない**。そのため register は展開器にも明示的に
許可する。また、手作業で何を読んだか、allowlist 内の資産の意味的独立性、実行されなかった分岐、
追跡開始前に開かれたファイル記述子からの読み取り、CPython の監査イベントを発生させない native
読み取り、および環境変数・ネットワーク等の非ファイル入力は保証しない。これらを確認済みまたは
異常なしと扱ってはならない。

### 8-1. 手作業 fixture

**主張は「展開器からの独立」のみ**。`clauseBranchRegister` からの独立は主張しない
(fixture は register の各分岐を見て作るため)。**作成者の同一性は記録してレビュー対象にする**。

### 8-2. 凍結(7.7 準拠)

資産側への宣言 / 追記のみの更新履歴(承認者・日付・理由)/ fail-closed。
**再基線化**: 条文の再改訂 / `clauseBranchRegister` の変更 / develop 取り込みでの入力変化。

### 8-3. 典拠の優先順位

| 優先順位 | 典拠 | 機械が確かめる範囲 | 人間統制 |
| --- | --- | --- | --- |
| 1 | 要件書 | 本リポジトリの正本から抽出した条文 ID の実在 | 条文が主張を支持するか |
| 2 | 公認野球規則 | **条番号の書式のみ**。原典が本リポジトリに無いため、条番号の実在と内容は機械で確かめない | 条番号の実在と内容 |
| 3 | 旧 `vocab.ts`(版固定ミラー) | 共有語彙 manifest 経由で語彙 ID の実在 | ミラーの版が正しいか |
| 4 | `docs/legacy/research/`(照合資料) | リポジトリ内のパスと行の実在 | 照合資料としての妥当性 |

優先順位4のみの `provenance` は fail とする。優先順位3のみで充足できるのは**語彙の由来**だけとし、分岐または状態効果の由来は優先順位1または2を少なくとも1件持たなければならない。公認野球規則の実在は、機械に確認能力があるのに解決できない状態ではなく、**そもそも本リポジトリ内の原典を持たないため機械保証の範囲外**である。この非保証範囲を、確認済みまたは異常なしと扱ってはならない。

### 8-4. 旧システムの既知事項(5 不具合 + 1 制約 + 1 推奨)

不具合 2(不変条件ガード欠如)・3(サヨナラ余剰得点)・4(スコア取消の情報喪失)・5(9 回固定)は**正す**。
6(走者同定)は**制約**で射程外、7 は**推奨**で穴 7 として解決。**タイムプレイ**は穴 6。

### 8-5. 台帳候補 (10)

**`H-91`** を採番。(**計画時は `H-90` を予約していたが、TSK-448 が 2026-09-27 に取得し PR #83 が 09-30 にマージ済みであることを原典で確認したため `H-91` へ。PO 承認 2026-10-08**)**台帳追記・変更履歴・`docs/README.md` の台帳行は同一コミット**。

## 9. 語彙シード

**②参照データ契約**。schema・参照整合・**内容 hash** が必須。D-12 でパス・版・hash の宣言先を確定。
**管理者変更への二段階ゲート**(契約 PR 登録 → 管理者有効化)。製品側の拒否の実装は該当 FR の実装タスク。

## 10. 正規化規則(段階 1 の範囲)

case は 3 点(生値 / 規則識別子 / 正規化後の値)を持つ。**段階 1 は schema と例まで**。
**負例**: 非正規形の raw を使い、normalizer を identity へ変異すると正規化後の突合が fail。
「正規形 raw 自体を拒否する」は条件に含めない。

## 11. PR 構成 — 1 タスク・1 ブランチ・1 PR

4 周目に `check_plan_docs_sync.py` で検証済み(violations 0 / warnings 0)。

### 11-1. コミット順

| 相 | 内容 |
| --- | --- |
| **A** | 要件書 → ADR-003 → 同期正本 → descriptor → 3 点突合 → `gapRegister` 骨格 → **ゲート投入コミット** |
| **(ゲート)** | `/finalize-doc` の確定ゲート(**番号付きステップにしない**) |
| **B** | 契約 schema(構造 → 参照 → 値域 → 交差制約 → operation/undo 別表)→ `mustOperationCoverage` → 終了判定 schema → 語彙シード → 遮断機構 → `gapRegister` 検査 → core-areas |
| **C** | `clauseBranchRegister` → **`gapRegister.branchIds`** → `requiredSet` → 規範行 4 層 → **`gapRegister.rowIds`** → 手作業 fixture(作成 → 突合 → 凍結)→ **`gapRegister.fixtureCaseIds`** |
| **D** | 展開器 → 一致検査 → 変異耐性 → `cases[]` → 正規化 → **`gapRegister.generatedCaseSelector` と `resolved` 遷移** |
| **E** | 検査配線(検査器単位)→ 数値基準の実測 → 台帳 `H-91` → 未解消レポート → 引き渡し契約 |

**`/check` と `/pr` はステップのコミット内容から外す。**

### 11-2. develop 同期は 3 点

フェーズ A の確定前 / フェーズ D の完了後 / `/pr` の直前。

### 11-3. 退路

`gapRegister` へ `open` で追記 → 再改訂の要否 → 要るなら同一 PR 内で条文改訂 + `/finalize-doc` 再実施 + 再基線化。

## 12. 分担

| 事項 | 担当 |
| --- | --- |
| 契約 schema・規範行 4 層・`requiredSet`・descriptor・`clauseBranchRegister`・手作業 fixture・語彙シード | **本タスク** |
| **runner による契約の消費** / 製品 manifest 登録 / 正規化の計算投入証跡 / FR-040 の manifest 宣言 / **descriptor と schema の射影検査** | **段階 2** |
| 検査基盤(runner・生成器・変異器) | TSK-235 |
| Vitest 側の runner | [TSK-455](https://app.notion.com/p/3e593b75e687812ba2e8c20d469ea6db)(段階 2 の依存) |
| FR-007 再開の検証先 | [TSK-454](https://app.notion.com/p/3e593b75e687813bbe17c36d17ebee63) |
| FR-006 のキュー投入・同期状態非依存 | 同期側のテスト |
| 管理者による未登録 ID の有効化拒否の実装 | 該当 FR の実装タスク |

## 未解決・検討メモ

- **確定ゲートの周回数**。3 正本の同時改訂は過去実績で 7〜8 周。
- **`matrixRows[]` の行数**。数百行を想定。**1 コミットあたりの上限行数**をフェーズ C の開始時に決める。
- **`clauseBranchRegister` の分岐数**。手作業 fixture の作成量を規定するため、
  フェーズ C の開始時に実数を出して分割単位を決める。
- **descriptor の軸の完全性**と**分岐の完全性**は人間統制(8 節)。レビューの実施記録を署名に残す。
