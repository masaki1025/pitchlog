---
feature: vitest-vector-runner
status: active         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-09・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e687812ba2e8c20d469ea6db
branch: feature/vitest-vector-runner
created: 2026-10-08
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: (α) ベクタ契約の Vitest 側 runner(TSK-455)

## 1. 背景・目的

- Notion: [TSK-455](https://app.notion.com/p/3e593b75e687812ba2e8c20d469ea6db)
- ADR-003:284 は、(α) の契約を **pytest と Vitest の両 runner** が同じファイルで全件消費することを求める。Python 側には `run_vectors`(`backend/src/pitchlog/domaincheck/runners/vectors.py`)があるが、Vitest 側の runner はない([research.md](research.md) A・B-1)
- 要件: [NFR-018](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-018)(α は双方で同一コードに由来する実行体を使う。一致の正は `contracts/` のベクタ)・[NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(フロントエンドの runner は Vitest。PR ごとに CI で全部緑)
- 位置づけ: **段階 2 の依存**であり、段階 1 を止めるタスクではない(research B-1。TSK-236 の計画書 plan.md:67・:77)。実契約の全件消費は、TS の生成済み正規化と計算が揃う段階 2 でしか緑にできない(research 結論)。本タスクは、そのとき Vitest 側で使う runner の土台を、Python 側と同じ意味で動く形で先に用意する
- 人間の裁定(2026-10-08。research.md 末尾): U-1 Vitest は Python `run_vectors` の現状に揃える / U-2 経路一致は Python と同じ形 / U-3 共通の適合ベクタを両 runner に流す / U-4 証跡は報告オブジェクトまで

調査: [research.md](research.md) / 詳細設計: [design.md](design.md)

## 2. スコープ

### やること

1. **Python 側のブリッジ** `backend/src/pitchlog/domaincheck/runners/vector_bridge.py`: 子プロセスとして起動され、標準入出力の JSON Lines で TS とやりとりしながら、**既存の `run_vectors` をそのまま**動かす(design.md 1・2)
2. **TS 側の runner** `frontend/src/testing/vectorRunner.ts`: ブリッジを起動し、Python からの要求に応じて生成済み正規化と計算 adapter を呼ぶ。schema 検査・lossless 比較・完走判定は **TS に書かない**(design.md 1-2)
3. **共通の適合ベクタ** `tests/domain/runners/fixtures/vector-conformance/`: シナリオ 9 件(既存の Python テスト 6 件の写しと、失敗経路 3 件の追加)。pytest は `run_vectors` を直接、Vitest はブリッジ経由で同じシナリオを消費し、結果と呼び出しの痕跡が一致することを両側で検査する(design.md 3)
- 2026-10-09 人間の裁定(計画レビュー 1 周目 P1-1・P1-2): **`ci.yml` と `core-areas.json` は変えない**。適合ベクタは既存のコア glob(`tests/domain/*`)に入る位置へ置く。残余 R-a(適合ベクタ・ブリッジだけの変更では Vitest が走らない)と R-b(TS runner は既存のコア glob の外)は、記録して段階 2 受取タスクへ送る(design.md 4)

### やらないこと

- **Python の `run_vectors`・`validate_asset`・`path_match` の変更**(U-1。`vectors.py`・`cli.py`・`path_match.py` の差分は 0 件)
- **実契約(`contracts/state-transition/`)の読み込み**と `caseFieldMapping` の適用、schemaVersion・version・トップレベルの検査、全件の列挙 → 段階 2 受取タスク(U-1。両側を揃えて入れる)。このため **本タスクは #81 のマージに依存しない**
- **本物の 2 経路**(①製品の入口経由・②生成物の直接呼び出し)→ 段階 2(U-2)
- **`.github/workflows/ci.yml`・`.claude/core-areas.json` の変更**(裁定 2026-10-09。design.md 4)
- `frontend/src/lib/sync/prohibitions.spec.ts` は、走査一覧への `'testing/vectorRunner.ts'` の 1 行追加(ステップ 3)以外に触れない
- **JSON 証跡・reporter・収集器の拡張** → ADR-003:251 の「検査基盤の実装タスク」(U-4)。`frontend/vitest.config.ts` には触れない
- **TS の生成済み正規化・計算の生成**(段階 2)
- **Notion カードのタイトル(「PR #4 の開始条件」)の訂正**: 469 master が人間へ上げている(research B-1)。本計画では本文の「やること」1・3・5 が範囲外になったことを、DoD の同期とあわせてカードへ記録するだけにする

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| (なし) | **反映なし**。ADR-003 の条件は変えない(本タスクは条件の一部を満たす土台を作るだけで、満たした範囲を正本で宣言しない)。CI の構成も変えないので、ハーネス設計書 10.1 にも触れない | — |

## 4. 実装方針

**重さ分類: コア領域**。根拠: `backend/src/pitchlog/domaincheck/*` と `tests/domain/*` は `.claude/core-areas.json` の「状況計算(クライアント・サーバー)」「データ移行」の paths に該当し(`scripts/core_guard.py:472` は `fnmatchcase` なので `*` がディレクトリをまたぐ)、適合ベクタも `tests/domain/` の下に置いて同じ glob で覆う。TS runner は既存の glob の外だが、裁定(2026-10-09)により `core-areas.json` は変えず、残余 R-b として記録する(design.md 4)。

方式の要点(詳細は [design.md](design.md)):

- **判定は Python の 1 系統だけ**: TS へ移植せず、`run_vectors` をブリッジで動かす。言語差(research C-4 の 1〜4)が構造的に生じない。根拠と比較は design.md 1-2
- **同一性の保持**: 計算 adapter には、正規化 adapter が返した元のオブジェクトを渡す(design.md 2-1)。JSON で往復できない値は送る前に拒否する
- **例外の扱いを Python と揃える**: `VectorRunError` はメッセージをそのまま、adapter の想定外の例外は包まずに元の例外として送出する(research C-4 の 5。design.md 2)
- **適合ベクタは宣言だけ**: 正規化と計算の振る舞いを表で持ち、両言語のテスト側に論理を書かない(design.md 3-2)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **適合ベクタ**: `tests/domain/runners/fixtures/vector-conformance/vector_conformance_v1.json`(design.md 3-3 の 9 シナリオ)と `vector_conformance_schema_v1.json`、pytest 側の消費 `tests/domain/runners/test_vector_conformance.py`(`run_vectors` を直接呼び、表で宣言した adapter を使う) | `uv run pytest tests/domain/runners/` 緑。fixture が schema に適合する(`validate_asset`)。9 シナリオすべてで `expected` と `trace` が一致する。`test_vectors.py` の 6 テストそれぞれに対応するシナリオがあることを ID の対応表で検査する |
| 2 | **Python ブリッジ** `backend/src/pitchlog/domaincheck/runners/vector_bridge.py`(design.md 2 の規約。`run_vectors` を呼ぶだけで、schema 検査・比較・完走判定を自前で持たない)と単体テスト `tests/domain/runners/test_vector_bridge.py`(入出力を差し替えて in-process で駆動する) | `uv run pytest tests/domain/runners/` 緑。テストで次を確かめる: 完走時のメッセージ列(`normalize`→`normalized`→`execute`→`executed` の繰り返しと `report`)/ `unsupported` が `未対応 case: …` の `vector-run-error` になる / `adapter-error` が包まれずに伝わる / 未知の `type`・順序違反・JSON でない行が `protocol-error` になる / **ステップ 1 の 9 シナリオをブリッジ経由でも通し**(テスト側の宿主は表で宣言した adapter を Python で返すだけ)、`expected`・`trace` が直接呼び出しと一致する / ブリッジが `validate_asset`・`compare_path_set` を直接 import せず `run_vectors` を使う(静的検査)。`git diff` で `vectors.py`・`cli.py`・`path_match.py` が無変更。`uv run ruff check`・`uv run ty check` 緑 |
| 3 | **TS runner** `frontend/src/testing/vectorRunner.ts`(design.md 2-2 の公開面)と単体テスト `frontend/src/testing/vectorRunner.spec.ts`。あわせて `frontend/src/lib/sync/prohibitions.spec.ts` の `EXPECTED_TESTING_SOURCE_FILE_NAMES` に `'testing/vectorRunner.ts'` を 1 行足す(`src/testing/**/*.ts` を走査対象として固定しているため。2026-10-09 人間の裁定) | `pnpm test -- --run src/testing/vectorRunner.spec.ts` 緑。テストで次を確かめる: 計算 adapter に正規化の出力と同一のオブジェクトが渡る / JSON で往復できない値(`undefined`・`bigint`・`NaN`・`-0`・安全でない整数。入れ子の中も)を送る前に拒否する / thenable を返す adapter を拒否する / adapter の例外が元のオブジェクトのまま送出される(正規化 adapter が投げた `UnsupportedVectorCase` も包まれない)/ `python3` の起動失敗・終端前の終了・無応答(期限超過)・`report` 後に終了しない子・終了コード 0 以外が、いずれも runner の異常として送出され、どの場合も子プロセスが残らない(期限は差し替えて短くする)/ **既定の期限のまま**の無応答の子でも、テストの期限より先に runner が異常を送出して子を回収する(design.md 1-3 の大小関係) / `vectorRunner.ts` に比較・schema 検査の実装がない(静的検査: `additionalProperties`・`total-order`・`exact-numeric-representation` の語を含まない)。`pnpm exec eslint .`・`pnpm exec prettier --check .`・`pnpm exec vue-tsc --noEmit`・`pnpm exec depcruise src --validate` 緑 |
| 4 | **Vitest 側の適合ベクタ消費** `frontend/src/testing/vectorConformance.spec.ts`(ステップ 1 と同じ fixture をブリッジ経由で消費する) | `pnpm test -- --run src/testing/vectorConformance.spec.ts` 緑。9 シナリオすべてで `expected`・`trace` が pytest 側と同じ値で一致する。fixture のシナリオ件数と消費件数が一致する(取りこぼし 0)。lint 一式緑 |

## 5. DoD(受け入れ基準)

- [ ] ステップ 1〜4 がそれぞれ 1 コミットで入り、各合格条件を満たす
- [ ] `vectors.py`・`cli.py`・`path_match.py` に差分がない(U-1)
- [ ] 適合ベクタ 9 シナリオで、pytest(直接)と Vitest(ブリッジ経由)の結果と痕跡が一致する(U-3)
- [ ] TS 側に schema 検査・lossless 比較・完走判定の実装がない(静的検査で固定)
- [ ] CI の全ジョブが緑(本 PR は `frontend/**` を含むので frontend ジョブが発火する)
- [ ] コア領域の敵対レビューと、人間の逐行確認を通過している
- [ ] 段階 2 へ送る事項(design.md「未解決・検討メモ」と 4 節の残余 R-a・R-b)を、TSK-236 側(236 タブ、不在なら Notion の TSK-236 カード)へ runner のパスとマージ commit OID とともに伝えている(research B-2: `dependencies[]` 用)
- [ ] Notion カードの DoD を本節と同期し、「やること」1・3・5 が範囲外になった理由(U-1・U-2・U-4)を記録している

## 6. テスト計画

| NFR-019 の種別 | 追加するもの |
| --- | --- |
| 単体 | `test_vector_bridge.py`(ブリッジの規約・例外の伝わり方・9 シナリオのブリッジ経由での一致)/ `vectorRunner.spec.ts`(同一性・JSON 往復の拒否・子プロセスの回収・静的検査) |
| 一致性 | 適合ベクタ 9 シナリオを pytest(`test_vector_conformance.py`)と Vitest(`vectorConformance.spec.ts`)の両方で消費し、同じ期待値に一致させる。製品の対象計算の一致性(実契約)は段階 2 |
| 越境・E2E・故障系 | 追加なし(本タスクは製品の経路に触れない) |

テストの実行範囲は影響範囲に絞り(上記の各ファイルと lint 一式)、全件は CI に任せる。
