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

## 2. ブリッジの通信規約

標準入出力上の **JSON Lines**(1 行 = 1 メッセージ・UTF-8)。stderr は診断用で、規約には含めない。

| 向き | `type` | 中身 | 意味 |
| --- | --- | --- | --- |
| TS → PY | `start` | `cases`・`contract`・`normalizer`(`generatedId`・`sourceHash`) | 1 回の実行を始める。最初の 1 行だけ |
| PY → TS | `normalize` | `raw` | 生成済み正規化を 1 回呼ぶ。PY が `copy.deepcopy(case["raw"])` を渡す時点に対応する |
| TS → PY | `normalized` | `value` | 正規化の結果 |
| PY → TS | `execute` | `caseId`・`normalized` | 計算 adapter を 1 回呼ぶ |
| TS → PY | `executed` | `value` | 計算結果 |
| TS → PY | `unsupported` | — | adapter が `UnsupportedVectorCase` を投げた。PY 側で `UnsupportedVectorCase` を送出し、PY の既存処理が `VectorRunError("未対応 case: …")` に包む |
| TS → PY | `adapter-error` | `message` | adapter がそれ以外の例外を投げた。PY 側で専用例外を送出する。PY の `run_vectors` はこれを包まない(research C-4 の 5)ので、そのまま終了まで伝わる |
| PY → TS | `report` | `declaredCaseIds`・`consumedCaseIds`・`executions`・`complete` | 完走。`complete` は PY の `VectorRunReport.complete` の値をそのまま運ぶ(TS で再計算しない) |
| PY → TS | `vector-run-error` | `message` | PY が `VectorRunError` を送出した |
| PY → TS | `adapter-error` | — | TS 側 adapter の例外が伝わって終了した。TS は**保持している元の例外オブジェクト**を再送出する |
| PY → TS | `protocol-error` | `message` | 規約違反(未知の `type`・順序違反・JSON でない行)。TS は runner の内部異常として送出する |

### 2-1. 同一性と値の往復

- PY は `execute` に `normalized` を載せる。TS は直前の `normalize` で adapter が返した**元のオブジェクト**を保持しておき、受け取った `normalized` がそれと深い等値であることを確かめたうえで、**保持している元のオブジェクト**を計算 adapter に渡す。PY のテストが確かめている「計算に渡る値は正規化の出力そのもの」(`calculation.inputs[i][1] is normalizer.outputs[i]`)を TS 側でも保つ
- TS が PY に送る値は JSON で往復できるものに限る。`undefined`・関数・`bigint`・非有限数・`Number.isSafeInteger` を満たさない整数を含む値は、**送る前に** runner の内部異常として拒否する(黙って `null` や丸めた値に化けるのを防ぐ)

### 2-2. TS 側の公開面

`frontend/src/testing/vectorRunner.ts`:

- 型 `VectorContract`(PY の同名 dataclass と同じフィールドを camelCase で持つ。`runner` は `'vitest'` 固定)、`GeneratedNormalizer`(`generatedId`・`sourceHash`・`normalize(raw)`)、`CalculationAdapter`(`execute(caseId, normalized)`)、`VectorRunReport`
- 例外 `VectorRunError`(PY の `VectorRunError` のメッセージをそのまま持つ)、`UnsupportedVectorCase`(adapter が投げる)
- `runVectors(cases, contract, normalizer, calculation): Promise<VectorRunReport>`
- 置き場は `frontend/src/testing/`(テスト専用の前例 `failureScenarioAdapter.ts` と同じ)。製品のバンドルには入らない

## 3. 共通の適合ベクタ(裁定 U-3)

### 3-1. 目的

同じシナリオを **pytest は `run_vectors` を直接呼び**、**Vitest はブリッジ経由で呼び**、結果(完走 / 失敗の種類とメッセージの先頭 / 呼び出しの痕跡)が一致することを両側で検査する。判定の論理は 1 系統なので、ここで確かめるのは**ブリッジが意味を変えないこと**である。

### 3-2. 置き場と形

- `tests/fixtures/vector-conformance/vector_conformance_v1.json` と、それを閉じる `vector_conformance_schema_v1.json`(`additionalProperties: false`。pytest 側が `validate_asset` で検証する)
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

## 4. CI の発火条件

`.github/workflows/ci.yml` の `frontend-changes` の filter に `backend/src/pitchlog/domaincheck/**` と `tests/fixtures/vector-conformance/**` を足す。どちらも Vitest が読むのに、現状ではそこだけを変えた PR で frontend ジョブが走らない(前例 `entrypointClosure.spec.ts` も domaincheck を起動しているが、filter に入っていない)。`tests/test_ci_wiring.py:2280-2306` の前例(`scripts/design_relations/sync-protocol.json` の包含を検査)に倣い、包含を検査するテストを足す。

## 未解決・検討メモ

- **段階 2 受取タスクへ送るもの**(裁定 U-1・U-2・U-4): 実契約(`contracts/state-transition/`)の読み込みと `caseFieldMapping` の適用、schemaVersion・version・トップレベルの検査、全件の列挙、本物の 2 経路(①入口・②直接呼び出し)、JSON 証跡と収集器の拡張。いずれも Python 側と揃えて入れる
- **段階 2 で読み込み層を作るときの注意**: TS の `JSON.parse` は 2^53 を超える整数の精度を落とす。ブリッジは送る前に拒否するが、ファイルを読んだ時点で落ちた値は検出できない。読み込み層で対処する
- **カードとのずれ**: Notion カードの「やること」1(実契約を読む)・3(schemaVersion 不一致の fail)・5(5 判定の証跡形式)は、裁定 U-1・U-2・U-4 により本タスクの範囲外。タイトルの「PR #4 の開始条件」はリポジトリに根拠がない(research B-1)。カードの訂正は 469 master が人間へ上げている
