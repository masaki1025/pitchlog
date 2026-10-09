---
feature: vitest-vector-runner
type: design
date: 2026-10-09
---

# 詳細設計: (α) ベクタ契約の Vitest 側 runner(TSK-455)

略号: PY = `backend/src/pitchlog/domaincheck/runners/vectors.py`(develop `7167c182`)。研究メモの典拠は [research.md](research.md)。

## 1. 方式: Python の `run_vectors` をブリッジで動かす

### 1-1. 結論

Vitest 側 runner は **判定の論理を TS に複製しない**。Python の `run_vectors` を子プロセスで起動し、Python が手順(schema 検査 → 重複 ID → 正規化 → 正規化後の照合 → 計算 → 計算結果の照合 → 完走判定)を進める。**TS が受け持つのは、生成済み正規化と計算 adapter の呼び出しだけ**である。Python は呼び出しが要る時点で TS へ要求を送り、TS が結果を返す。

### 1-2. 理由

| 観点 | ブリッジ(採用) | TS への移植(不採用) |
| --- | --- | --- |
| 裁定 U-1「Python の現状に揃える」 | 同じコードが動くので、揃うことが構造で保証される | 移植の正しさを別に示す必要がある |
| 言語差(research C-4 の 1〜4: 検証器の対応範囲・`==` の bool と int・`json.dumps(sort_keys)` の順序・`re.search` の `$`) | 生じない。判定はすべて Python 側で一度だけ行う | 4 件それぞれを TS で再現する必要があり、外れると黙って判定がずれる |
| 既存の設計原則 | PY 自身が「schema と lossless 比較は既存機構へ委ね、再実装しない」を静的テストで固定している(`tests/domain/runners/test_vectors.py` の `test_runner_uses_existing_schema_checker_and_lossless_comparator`) | 同じ原則に反する(`cli.py:199-495` の `validate_asset` 一式と、`path_match.py` の比較器の複製) |
| 段階 2 との接続 | ADR-003:249 は「証跡は CI 側の独立した収集器が作る」とし、収集器は Python(`collect_layers.py`)。判定を Python に寄せる方向と一致する | 段階 2 で Python 側と二重になる |
| 費用 | Vitest から Python を起動する。前例がある(`frontend/src/testing/entrypointClosure.spec.ts:150-156`。CI の frontend ジョブで system `python3` を使って緑) | なし |

### 1-3. 起動

- `python3 -m pitchlog.domaincheck.runners.vector_bridge`、`PYTHONPATH=<repo>/backend/src`、`cwd=<repo>`(前例と同じ形)
- domaincheck の import 連鎖は標準ライブラリだけで閉じている(`cli.py`・`path_match.py`・`collect_layers.py`・`vectors.py` の import 行を確認。`StrEnum` のため Python 3.11 以上)。ローカルは 3.14、CI の ubuntu-latest は 3.12
- 1 回の `runVectors` 呼び出しにつき子プロセスを 1 個起動し、終了時に必ず回収する(成功・失敗・例外のいずれでも)
- 寿命の規約:
  - PY は 1 行書くごとに flush する。TS は 1 行ごとに書き、改行で区切る
  - TS は stderr を常に読み続けて保持する(パイプが詰まって子が止まるのを防ぐ)。異常時のメッセージに含める
  - TS は PY からの各応答を**期限つき**で待つ。既定は `DEFAULT_RESPONSE_TIMEOUT_MS = 10_000`(export する)。期限を過ぎたら子を kill し、回収してから runner の内部異常を送出する
  - **期限の大小関係**: runner を使う spec は、ファイル単位でテスト期限を `3 × DEFAULT_RESPONSE_TIMEOUT_MS` 以上に設定する(Vitest の既定 5 秒より runner の既定期限が長いため。期限超過・kill・回収・終了確認の 3 段がテスト期限内に収まる)
  - 終端メッセージ(`report`・`vector-run-error`・`adapter-error`・`protocol-error`)の後、TS は stdin を閉じ、子が**期限内に終了コード 0** で終わることを確かめる。終わらなければ kill して異常、0 以外なら異常(終端が `report` でも完走にしない)
  - 子が終端メッセージの前に終了した場合は、終了コードと stderr を添えて異常にする
  - テストのため、起動コマンドと期限を `runVectors` の任意引数で差し替えられるようにする(無応答の子・`report` 後に止まらない子を作るため)

## 2. ブリッジの通信規約

標準入出力上の **JSON Lines**(1 行 = 1 メッセージ・UTF-8)。stderr は診断用で、規約には含めない。

| 向き | `type` | 中身 | 意味 |
| --- | --- | --- | --- |
| TS → PY | `start` | `cases`・`contract`・`normalizer`(`generatedId`・`sourceHash`) | 1 回の実行を始める。最初の 1 行だけ |
| PY → TS | `normalize` | `raw` | 生成済み正規化を 1 回呼ぶ。PY が `copy.deepcopy(case["raw"])` を渡す時点に対応する |
| TS → PY | `normalized` | `value` | 正規化の結果 |
| PY → TS | `execute` | `caseId`・`normalized` | 計算 adapter を 1 回呼ぶ |
| TS → PY | `executed` | `value` | 計算結果 |
| TS → PY | `unsupported` | — | **計算 adapter** が `UnsupportedVectorCase` を投げた。PY 側の計算 proxy が `UnsupportedVectorCase` を送出し、PY の既存処理が `VectorRunError("未対応 case: …")` に包む。**`normalize` への応答には使えない**(PY が包むのは `calculation.execute` の例外だけ — `vectors.py:242`。正規化 adapter が `UnsupportedVectorCase` を投げた場合は次行の `adapter-error` として元の例外のまま伝える) |
| TS → PY | `adapter-error` | `message` | adapter がそれ以外の例外を投げた。PY 側で専用例外を送出する。PY の `run_vectors` はこれを包まない(research C-4 の 5)ので、そのまま終了まで伝わる |
| PY → TS | `report` | `declaredCaseIds`・`consumedCaseIds`・`executions`・`complete` | 完走。`complete` は PY の `VectorRunReport.complete` の値をそのまま運ぶ(TS で再計算しない) |
| PY → TS | `vector-run-error` | `message` | PY が `VectorRunError` を送出した |
| PY → TS | `adapter-error` | — | TS 側 adapter の例外が伝わって終了した。TS は**保持している元の例外オブジェクト**を再送出する |
| PY → TS | `protocol-error` | `message` | 規約違反(未知の `type`・順序違反・JSON でない行)。TS は runner の内部異常として送出する |

### 2-1. 同一性と値の往復

- PY は `execute` に `normalized` を載せる。TS は直前の `normalize` で adapter が返した**元のオブジェクト**を保持しておき、受け取った `normalized` がそれと深い等値であることを確かめたうえで、**保持している元のオブジェクト**を計算 adapter に渡す。PY のテストが確かめている「計算に渡る値は正規化の出力そのもの」(`calculation.inputs[i][1] is normalizer.outputs[i]`)を TS 側でも保つ
- TS が PY に送る値は JSON で往復できるものに限る。`undefined`・関数・`bigint`・非有限数・`-0`(ADR-003:287 が禁止。`JSON.stringify` で `0` に化ける)・`Number.isSafeInteger` を満たさない整数を含む値は、**送る前に**再帰的に検出し、runner の内部異常として拒否する(黙って `null` や丸めた値に化けるのを防ぐ)
- adapter は**同期関数に限る**(PY の Protocol と同じ)。戻り値が thenable なら runner の内部異常として拒否する

### 2-2. TS 側の公開面

`frontend/src/testing/vectorRunner.ts`:

- 型 `VectorContract`(PY の同名 dataclass と同じフィールドを camelCase で持つ。`runner` は `'vitest'` 固定)、`GeneratedNormalizer`(`generatedId`・`sourceHash`・`normalize(raw)`)、`CalculationAdapter`(`execute(caseId, normalized)`)、`VectorRunReport`
- 例外 `VectorRunError`(PY の `VectorRunError` のメッセージをそのまま持つ)、`UnsupportedVectorCase`(adapter が投げる)
- `runVectors(cases, contract, normalizer, calculation, options?): Promise<VectorRunReport>`。`options` は `Readonly<{ command?: readonly [string, ...string[]]; responseTimeoutMs?: number }>`(テスト用。既定は `python3 -m pitchlog.domaincheck.runners.vector_bridge` と `DEFAULT_RESPONSE_TIMEOUT_MS`)
- 置き場は `frontend/src/testing/`(テスト専用の前例 `failureScenarioAdapter.ts` と同じ)。製品のバンドルには入らない

## 3. 共通の適合ベクタ(裁定 U-3)

### 3-1. 目的

同じシナリオを **pytest は `run_vectors` を直接呼び**、**Vitest はブリッジ経由で呼び**、結果(完走 / 失敗の種類とメッセージの先頭 / 呼び出しの痕跡)が一致することを両側で検査する。判定の論理は 1 系統なので、ここで確かめるのは**ブリッジが意味を変えないこと**である。

### 3-2. 置き場と形

- `tests/domain/runners/fixtures/vector-conformance/vector_conformance_v1.json` と、それを閉じる `vector_conformance_schema_v1.json`(`additionalProperties: false`。pytest 側が `validate_asset` で検証する)
- 1 シナリオの形:

| キー | 中身 |
| --- | --- |
| `id`・`description` | シナリオ ID と説明 |
| `contract` | `calculation`・`vector`・`entrypointId`・`directTargetId`・`caseSchema`・`normalizationComparison`・`outputComparison`。`runner` は持たず、消費側が自分の ID(`pytest` / `vitest`)を入れる |
| `normalizer` | `generatedId`・`sourceHash`・`mode`(`table` / `passthrough`)・`table`(呼び出し順の配列。k 回目の呼び出しで `raw` が `table[k].raw` と等しいことを確かめ、`table[k].normalized` を返す) |
| `calculation` | `supportedCaseIds`、任意の `outputs`(caseId → 返す値。無ければ受け取った値をそのまま返す) |
| `cases` | `run_vectors` に渡す配列 |
| `expected` | `{"outcome": "complete", "declaredCaseIds", "consumedCaseIds"}` または `{"outcome": "vector-run-error", "messagePrefix"}` |
| `trace` | `normalizeCalls`(回数)・`executedCaseIds`(計算 adapter に届いた caseId の順序) |

正規化と計算の振る舞いを**表で宣言**するので、両言語のテスト側に論理を書かない(表引きと深い等値だけ)。

### 3-3. シナリオ

PY の既存テスト 6 件(`tests/domain/runners/test_vectors.py`)をすべて写し、PY が送出する残りの失敗経路を足す。

| ID | 由来 | 期待 |
| --- | --- | --- |
| `valid-two-cases` | 既存 | 完走。2 件とも計算まで届く |
| `passthrough-normalizer` | 既存 | `生成済み正規化の出力が不一致`。正規化 1 回・計算 0 件 |
| `unsupported-case` | 既存 | `未対応 case: caseTwo`。計算に届くのは caseOne だけ |
| `unknown-case-field` | 既存 | `case schema 不一致`。正規化 0 回 |
| `duplicate-case-id` | 既存 | `case ID が重複` |
| `case-schema-mismatch` | 既存 | `case schema 不一致` |
| `output-mismatch` | 追加 | `計算結果が不一致` |
| `invalid-normalizer-hash` | 追加 | `正規化生成物 hash が不正`。正規化 0 回 |
| `empty-cases` | 追加 | `cases が空でない array でない` |

## 4. 置き場とコア領域・CI の範囲(2026-10-09 人間の裁定)

計画レビュー 1 周目の P1-1・P1-2 に対する裁定。どちらも、マージを待たせる費用を避けて残余を記録する。

- **置き場**: 適合ベクタは `tests/domain/runners/fixtures/vector-conformance/` に置く。既存の glob `tests/domain/*` で覆われ、コア領域の判定に入る。U-3 の「`tests/fixtures/`」から置き場だけを変えた(両 runner に流す方式は同じ)
- **`ci.yml` は変えない**: `ci.yml` は凍結 corpus の入力(`tests/fixtures/frozen-archive-cases/manifest.json:9`)なので、変えると凍結資産の受理が要る
- **`core-areas.json` は変えない**: 追加は回転式の窓口に並ぶ(#95 → #81 → U-S1 の後ろ)

残余(段階 2 受取タスクへ送る):

| # | 残余 | 捕まる場所 |
| --- | --- | --- |
| R-a | 適合ベクタかブリッジだけを変えた PR では、Vitest(frontend ジョブ)が走らない。`frontend-changes` の filter は `frontend/**`・`contracts/**` などで、`tests/domain/**`・`backend/src/pitchlog/domaincheck/**` を含まない(前例 `entrypointClosure.spec.ts` も同じ状態) | pytest 側(harness ジョブで常時実行)で捕まる範囲: `run_vectors` の判定の変化と fixture の誤り(`test_vector_conformance.py` が直接呼び出しで検査)、ブリッジによる意味の変化(`test_vector_bridge.py` が同じ 9 シナリオをブリッジ経由で検査)。**捕まらないのは、ブリッジの規約を変えて TS 側の宿主と食い違った場合だけ**で、次に `frontend/**` を変える PR で赤になる |
| R-b | `frontend/src/testing/vectorRunner.ts`・`vectorConformance.spec.ts`・`vectorRunner.spec.ts` は既存のコア glob に入らない。後日これらだけを変える PR はコア判定(敵対レビュー・逐行確認)を通らない | 本タスクの PR はブリッジと `tests/domain/*` を含むのでコア判定に入る。段階 2 は `frontend/src/lib/generated/*`(コア)に触れるので、そのときに paths の追加を判断する |

## 未解決・検討メモ

- **段階 2 受取タスクへ送るもの**(裁定 U-1・U-2・U-4、および 4 節の残余 R-a・R-b): 実契約(`contracts/state-transition/`)の読み込みと `caseFieldMapping` の適用、schemaVersion・version・トップレベルの検査、全件の列挙、本物の 2 経路(①入口・②直接呼び出し)、JSON 証跡と収集器の拡張。いずれも Python 側と揃えて入れる
- **段階 2 で読み込み層を作るときの注意**: TS の `JSON.parse` は 2^53 を超える整数の精度を落とす。ブリッジは送る前に拒否するが、ファイルを読んだ時点で落ちた値は検出できない。読み込み層で対処する
- **カードとのずれ**: Notion カードの「やること」1(実契約を読む)・3(schemaVersion 不一致の fail)・5(5 判定の証跡形式)は、裁定 U-1・U-2・U-4 により本タスクの範囲外。タイトルの「PR #4 の開始条件」はリポジトリに根拠がない(research B-1)。カードの訂正は 469 master が人間へ上げている
