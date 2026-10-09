---
date: 2026-10-08
topic: (α) ベクタ契約の Vitest 側 runner を実装する(TSK-455)
branch: feature/vitest-vector-runner
---

# 作業ログ: 2026-10-08 (α) ベクタ契約の Vitest 側 runner を実装する(TSK-455)

## やったこと

### /task-start(2026-10-08・455 タブ)

- Notion TSK-455 を 進行中 へ。ブランチ `feature/vitest-vector-runner`(起点 develop `1fdf1eec`)
- 申し送り元: 469 master(進行管理)。鎖 = TSK-455 マージ → TSK-236 PR #4 の開始条件 → ADR-003 段階 1 完了 → U-X1 解禁
- 実測: Python 側 runner `backend/src/pitchlog/domaincheck/runners/vectors.py` は develop に実在。Vitest 側 runner は実体なし
- 実測: `contracts/state-transition/` の (α) 契約 schema 群(30 ファイル超)は TSK-236 worktree のローカルにのみ存在。origin/feature/appendix-e-golden-vectors には input_axes_descriptor の 2 ファイルだけ(ローカル HEAD `d76e2cf5` が origin より 961 コミット先行)。TSK-236 の PR は #81 の 1 本(OPEN)

### 236 タブの回答(2026-10-08)と原典での裏取り

- (α) schema は凍結扱い: TSK-236 の全 110 ステップはコミット済み。`state_transition_contract_schema_v1.json` の最終変更 `1ea9b7cb`(10-07)を 236 worktree で確認。残る変動要因は人間のコア領域逐行確認による差し戻しだけ。マージ前に #81 の diff で最終形を取り直す
- PR は #81 の 1 本(draft)。#1〜#4 への分割計画はない。961 コミットは通常の push で上げる予定(force は不要)
- runner が消費する形(`appendix_e_consumer_handoff_v1.json` で確認): `caseFieldMapping` で expected が非対称(状況遷移 `/expected`、終了判定 `/decision` → `/expected`)。`tags` は契約側に無い(`availability: "absent"`)。`executionPaths[]` の vitest 経路は `runnerRevision: "pending"`・3 ID が null・`resolutionStage: "stage-2"`
- 未確定: `receiverTaskId` は null。`dependencies[]` に TSK-455 は入っていない(runner のパスが決まったら 236 へ伝える)
- **位置づけの食い違い**: TSK-236 の plan.md 1-2 節「打ち切り前に是正した 3 件」の #2 と 1-3 節は、TSK-455 を「**段階 2 の依存**」としている。カードと申し送りにある「TSK-455 マージ → PR #4 開始 → 段階 1 完了」という鎖は、計画書の現行版と合わない(PR #4 も存在しない)

### /investigate(2026-10-08)

- spec-checker・decision-tracer・Explore の 3 本を並列で実行し、`docs/features/vitest-vector-runner/research.md` に統合した。決定的な主張 6 件は原典で確認した(vectors.py:190-202 の同値投入、collect_layers.py:44、generated/ が .gitkeep のみ、domaingen に normaliz が 0 件、core-areas.json:182・229、両契約の additionalProperties と expected の有無)
- 要旨: いま作れるのは消費エンジンと読み込み層まで。実契約の全件消費は段階 2(TS の生成済み正規化と計算がない)。Python の run_vectors は ADR の条件を一部しか満たしていない(schemaVersion を読まない・最初の 1 件で止まる・経路一致が自明)

## 決定

- TSK-455 の位置づけ: 段階 1 を止めるタスクではなく、段階 2 の依存(469 master が原典 plan.md:67・:77・:276 で確認し、申し送りの鎖を撤回)。タスクは要る(ADR-003「(α) は両 runner が全件消費」)が、急ぎ度は下がる。カードのタイトル・本文にある「PR #4」の訂正は、469 master から山田さんへ上げる

- 2026-10-08 人間の裁定(U-1〜U-4。research.md 末尾にも記録):
  - U-1: **Vitest は Python `run_vectors` の現状に揃える**。schemaVersion・トップレベル検査・全件列挙といった ADR の未充足分は、両側とも段階 2 受取タスクへ送る。カードの「やること 3」(schemaVersion 不一致の fail)とずれるので、計画書で明示し、カードも直す
  - U-2: 経路一致は Python と同じ形にする(同じ実値を 2 経路に入れる。①=② が自明であることを明記する)。本物の 2 経路は段階 2
  - U-3: 共通の適合ベクタ(合成契約の正例・負例)を `tests/fixtures/` に置き、pytest と Vitest の両方に流して判定の一致を検査する
  - U-4: 証跡は `VectorRunReport` に相当する報告オブジェクトまで。JSON 証跡と収集器の拡張は、ADR:251 の「検査基盤の実装タスク」へ送る

## 未決・次の一歩

- 236 タブの回答(2026-10-09): (a) schema は凍結済み (b) `origin/feature/appendix-e-golden-vectors` を `a023f062` へ早送り push 済みで、`contracts/state-transition/` の 38 ファイルをリモートで読める(`state_transition_contract_schema_v1.json`・`game_end_contract_schema_v1.json`・`appendix_e_consumer_handoff_v1.json`〔`caseFieldMapping` / `executionPaths[]` の実値〕・`normalization_schema_examples_v1.json`)。PR #81 は draft のまま(凍結資産の受理記録と backend 全件が残る)
- 「#1〜#4 分割」の出どころは Notion TSK-455 カード本文(2026-09-24 作成)で、計画レビュー 2 周目の草案が固着したもの。正本(plan.md・引き渡し契約)には無い。カードの訂正は 469 タブが人間へ上げている。段階 2 の依存という読みで合っている
- 再開時: schema が凍っているので /plan へ進める。実装は #81 のマージ後

### /plan(2026-10-09)

- Notion を 保留中 → 進行中 へ戻し、ブランチを origin/develop(`7167c182`)へ rebase(未 push・docs のみ)
- 方式: **Python の `run_vectors` を子プロセスのブリッジで動かし、TS は正規化と計算 adapter の呼び出しだけを持つ**。判定の論理を TS に複製しない(design.md 1)。実契約の読み込みは段階 2 なので、**#81 のマージに依存しない**
- 重さ分類: コア領域(ブリッジが `backend/src/pitchlog/domaincheck/*`、テストが `tests/domain/*`)

### 計画レビュー 1 周目(敵対・2026-10-09)

所見: **不可**(P1×3・P2×3)。U-3 と方式の整合は「矛盾しない」との判定。

| # | 指摘 | 扱い |
| --- | --- | --- |
| P1-1 | `ci.yml` は凍結 corpus の入力(`tests/fixtures/frozen-archive-cases/manifest.json:9`)。filter を変えると harness の digest テストが赤になる | **人間の裁定(2026-10-09)**: `ci.yml` を変えない。ステップ 5 を削除し、残余 R-a として記録 |
| P1-2 | TS runner・spec・`tests/fixtures/vector-conformance/` は既存のコア glob に入らない | **人間の裁定(2026-10-09)**: `core-areas.json` を変えない。適合ベクタを `tests/domain/runners/fixtures/vector-conformance/` へ移して既存 glob で覆い、TS runner は残余 R-b として記録 |
| P1-3 | `-0` が JSON 往復で `0` に化ける(ADR-003:287 が禁止) | 採用: 送る前に再帰的に検出して拒否。ステップ 3 で検証 |
| P2-4 | `unsupported` は計算 adapter にだけ当てはまる(`vectors.py:242`) | 採用: 正規化側の `UnsupportedVectorCase` は `adapter-error` で元のまま伝える |
| P2-5 | `prettier`・`vue-tsc`・`depcruise` に `pnpm exec` がない | 採用 |
| P2-6 | 子プロセスの flush・stderr・期限・`report` 後の終了確認が規約とテストにない | 採用: 寿命の規約を design.md 1-3 に追加し、ステップ 3 で無応答・終了しない子・0 以外の終了を検証。adapter は同期に限り thenable を拒否 |


- 気づき(範囲外): ハーネス設計書 10.1 の `frontend` 行は「paths filter: frontend/ contracts/」と書くが、`ci.yml` の実体には `mise.toml`・`frontend/pnpm-lock.yaml`・`.github/workflows/ci.yml`・`scripts/design_relations/sync-protocol.json` も入っている。本タスクは `ci.yml` を変えないので直さない

### 計画レビュー 2 周目(敵対・差分・2026-10-09)

所見: **不可**(P1×1・P2×2)。1 周目の P1-3・P2-4・P2-5・P2-6 は閉じたとの判定。P0 がないので 3 周目は行わない(設計書 6.3 の上限)。3 件とも採用して反映した。

| # | 指摘 | 扱い |
| --- | --- | --- |
| P1-1 | runner の既定期限 30 秒が Vitest の既定テスト期限 5 秒より長く、既定のままでは回収の保証を検証できない | 採用: 既定を `DEFAULT_RESPONSE_TIMEOUT_MS = 10_000` とし、runner を使う spec のテスト期限をその 3 倍以上にする大小関係を design.md 1-3 に固定。ステップ 3 で既定期限のままの無応答を検証 |
| P2-2 | 起動コマンドと期限の差し替えが公開シグネチャにない | 採用: 第 5 引数 `options` の型を design.md 2-2 に明記 |
| P2-3 | R-a の「pytest 側で捕まる」は言い過ぎ(ブリッジ経由の回帰は直接呼び出しでは捕まらない) | 採用: ステップ順を入れ替え(1 = 適合ベクタ、2 = ブリッジ)、ブリッジの単体テストで 9 シナリオをブリッジ経由でも通す。R-a の捕捉範囲を書き直した |

### 実装中の計画修正: 走査一覧の固定(2026-10-09)

- ステップ 1(適合ベクタ・pytest 消費)と 2(Python ブリッジ)をコミット。各 1 回差し戻し(対応表の検査を等式に / 静的検査をモジュール経由の参照まで)
- ステップ 3 の `frontend/src/testing/vectorRunner.ts` が既存の `frontend/src/lib/sync/prohibitions.spec.ts` を赤にした。同テストは `src/testing/**/*.ts` を同期の禁止事項の raw 走査対象とし、ファイル集合を `EXPECTED_TESTING_SOURCE_FILE_NAMES` で固定している(新しいファイルを明示させる仕組み)。frontend 全件で 1 file failed・670 tests passed
- 一覧に `'testing/vectorRunner.ts'` を足した状態で同 spec は 41 件緑(試行後に元へ戻した)。`prohibitions.spec.ts` は同期プロトコルのコア領域(`core-areas.json` に該当)で、計画の変更範囲外だった
- **人間の裁定(2026-10-09)**: 一覧に 1 行足す。置き場は移さない。計画書のステップ 3 とやらないことに追記した

### 実装(/implement・2026-10-09)

| ステップ | 内容 | 差し戻し |
| --- | --- | --- |
| 1 | 適合ベクタ 9 シナリオ・schema・pytest 側の消費 | 1 回: `test_vectors.py` との対応表を「全 test_ 関数 = 対応表 ∪ 対象外(静的検査 1 件)」の等式に |
| 2 | Python ブリッジ `vector_bridge.py` と単体テスト | 1 回: 静的検査を import 名だけでなく AST 全体の名前・属性・`cli` の import まで |
| 3 | TS runner `vectorRunner.ts` と spec | 1 回: `prohibitions.spec.ts` の走査一覧へ 1 行(上記の裁定) |
| 4 | Vitest 側の適合ベクタ消費 `vectorConformance.spec.ts` | なし |

- `vectors.py`・`cli.py`・`path_match.py` の差分 0 件
- 総合検証中に、ハーネス全件で `tests/test_check_tenant_boundary_bypass.py::test_repository_is_green` が赤(`base-allowlist.json` の履歴 prefix 不一致)。原因は本変更ではなく、起点 `7167c182` 以降に develop で同ファイルの履歴が伸びたこと(#101・#100)。未 push だったので origin/develop へ rebase して解消(競合なし)
- Codex のサンドボックス内では `spawnSync` が `EPERM` になる既存 spec が 9 件ある(`dependencyClosure`・`entrypointClosure`)。サンドボックス外では緑

## 結果サマリ(/pr クローズ処理・2026-10-09)

- **実装したもの**: (α) ベクタ契約の Vitest 側 runner。判定は Python の `run_vectors` の 1 系統だけで、Vitest からは子プロセスのブリッジ(`vector_bridge.py`・JSON Lines)経由で駆動する。TS(`frontend/src/testing/vectorRunner.ts`)が持つのは正規化と計算 adapter の呼び出し・値の往復検査・子プロセスの回収だけ。共通の適合ベクタ 9 シナリオを pytest(直接)と Vitest(ブリッジ経由)の両方で消費し、結果と痕跡の一致を固定した
- **正本への反映**: なし(計画書 3 節の宣言どおり。/sync-docs で差分を検算済み)
- **検証**: ハーネス非 DB 全件 28,405 passed / backend 非 DB 全件 1,041 passed / frontend 全件 721 passed / ruff・ty・eslint・prettier・vue-tsc・depcruise 緑(origin/develop へ rebase 後)
- **段階 2 へ送る事項**: design.md「未解決・検討メモ」と計画書 4 節の残余 R-a・R-b。マージ後に runner のパスとマージ commit OID とともに TSK-236 側へ伝える(DoD)

### ハーネス運用評価台帳への追記: なし

本タスクの観測 3 件を台帳と突合し、いずれも追記しないと判断した。

1. **Codex の sandbox 内で既存 spec の `spawnSync` が `EPERM`**(`dependencyClosure`・`entrypointClosure` の 9 件。同じ sandbox で本タスクの spec の `spawn` は通った)— H-69「sandbox の制限により Codex へ委任できない検証がある」と同型で、委任側が sandbox 外で再実行して確かめる既存の手当てで足りた。原因(同期 spawn と非同期 spawn の差か)は切り分けておらず、型を確定できないので追記しない
2. **走査一覧の固定(`prohibitions.spec.ts` の `EXPECTED_TESTING_SOURCE_FILE_NAMES`)が新しいファイルで赤**— 固定の意図(新しいファイルを明示させる)どおりに働いた例で、穴ではない。計画レビュー 2 周が拾わなかったのは、依頼文が問うた軸しか出ない既知の性質による
3. **起点が古いブランチで `test_repository_is_green` が「比較元の履歴 prefix は変更・削除できない」で赤**— 既存候補「並行ブランチが CI 契約に規則を足すと、先行して設計済みのブランチが後から抵触する」と同じ機構(比較元 = `origin/develop` が先に進む)。本タスクは凍結資産に触れておらず、手元の全件でだけ赤になり、rebase 1 回で解消した。CI はマージ ref で走るので影響しない。新しい型ではないので追記しない

## PR #107 コア領域の敵対レビュー(2026-10-09)

設計書 6.3 の上限どおり、基本枠 2 回(全文 1・反映差分 1)+ P0 例外 1 回(P0 限定)で終えた。その後、人間の指示で 4 回目(上限外)を行った。**最後の反映(`419ca15c`)は Codex の再レビューを受けていない**(6.3 (4)・7.3-8 の残余リスク)ので、人間の逐行確認で最終反映の差分を確認する。

### 1 回目(PR 差分全体・否決: P0 2 / P1 2)— 全件採用

| # | 指摘 | 扱い |
| --- | --- | --- |
| P0-1 | 配列の添字でない数字キー(`"4294967295"` など)が送信前検査を通り、JSON 化で黙って消えて完走する | 採用: own key を `length` と 0 ≤ n < length の正準添字に限定(`8b3161c8`) |
| P0-2 | 子が stdout/stderr を孫に継承させて終了すると、`close` 待ちが孫の終了まで終わらない | 採用: `exit` で終了判定・回収待ちに上限・プロセスグループ・stdio の destroy(`8b3161c8`。2・3 回目で是正を重ねた) |
| P1-3 | 報告の `executions`(`generatedId`・`sourceHash` 等)をテストが照合していない | 採用: pytest はブリッジの報告を直接呼び出しの報告と全フィールド比較(`f569293c`)、Vitest は `executions` を要素全体で比較(`38dcc74b`) |
| P1-4 | `responseTimeoutMs` が 2**31-1 を超えると Node のタイマーで 1 ms に縮む | 採用: 上限超えを拒否(`8b3161c8`) |

### 2 回目(反映差分と影響箇所・否決: P0 2 / P1 3)— 4 件採用・1 件不採用

| # | 指摘 | 扱い |
| --- | --- | --- |
| P0-1 | 成功経路でもグループへ SIGKILL を送り、子の exit 後の PID 再利用で別グループを撃ちうる | 採用: exit 後はパイプの close を待ち、閉じないときだけ止める(`c7087780`)→ 3 回目で残存を指摘され方針を変更 |
| P0-2 | 後処理の例外が元の例外(`VectorRunError`・adapter の例外)を上書きする | 採用: 主処理が失敗していれば後処理のエラーで置き換えない(`c7087780`)。3 回目で解消を確認 |
| P1-3 | 終端前に終了した子の終了コードが診断から消えた | 採用: code・signal・stderr を含める(`c7087780`) |
| P1-4 | 親の強制終了時に detached の子が残る | **不採用(作成者判断 — 人間承認の場で PO の支持 / 採用指示を仰ぐ)**: 実ブリッジは親が死ぬと stdin が EOF になり、`protocol-error` を書いて自ら終了する(書き込みに失敗しても例外で終了する)。親の死を監視する仕組みは本タスクの射程に対して過剰 |
| P1-5 | タイマー上限の回帰テストが修正前のコードでも緑になる | 採用: 拒否の文言と、子を起動する前に拒否したことを表明(`c7087780`) |

### 3 回目(P0 限定の差分・否決: P0 1)— 採用・反映は未再レビュー

| # | 指摘 | 扱い |
| --- | --- | --- |
| P0 | 2 回目 P0-1 の一部残存: 孫が別セッションへ抜けてパイプを保持すると元のグループは空になり、終了済みの子の PID へのグループ signal が PID 再利用後に無関係なグループを撃ちうる(再利用後の誤送信は推論・未再現) | 採用: **子の `exit`/`error` を観測した後は signal を一切送らない**。グループへの SIGKILL は子が未回収(PID とグループ ID が再利用され得ない)の経路だけ。exit 後にパイプが閉じなければ自側の stdio を destroy して決着させ、パイプを保持する孫は止めない(実ブリッジは孫を作らない)(`6b528180`) |

- 上限に達したため、4 回目は行わない予定だった。frontend 全件 732 passed・lint 一式緑(`6b528180` 時点)

### 4 回目(人間の指示による上限外の追加・`6b528180` の差分と子プロセス寿命管理全体・否決: P0 1 / P1 2)— 全件採用・反映は未再レビュー

- 起点: `6b528180` が Codex の再レビューを受けていないため、人間(山田)が追加レビューを指示した(2026-10-09)。3 回目の P0(子の exit 観測後に古いグループへ signal を送る経路)は、解消を確認された
- 採否: 3 件とも人間の判断で採用した(2026-10-09)。修正後は Codex で再レビューせず、人間が最終差分を確認する

| # | 指摘 | 扱い |
| --- | --- | --- |
| P0 | 起動後の子の `error`(kill 失敗)を `exit` と同一視し、実際の終了を観測しないまま回収済みとして後処理を終えて子が残る(注入では再現済み。同一ユーザーの子への kill が権限不足になる条件で、実運用での発生は未確認。1〜3 回目は検出していない既存の欠陥) | 採用: 終了の観測は `exit` だけにする。`error` は起動失敗(pid なし)だけを終了扱いにし、起動後の `error` は記録して後処理の終了待ちを期限で打ち切る。回収できなければ内部異常に付記する(主処理が成功していれば「子を回収できない」の内部異常にする)。`VectorRunError` と adapter の元の例外は同一性を保つ。回帰テストは修正前に赤(`419ca15c`) |
| P1 | 回帰テストの spy が、グループ宛ての SIGKILL を記録したうえで実送信もする(回帰時に、PID 再利用後の無関係なグループをテスト自体が撃ちうる) | 採用: 負の PID は記録だけして実送信しない(`419ca15c`) |
| P1 | 孫を作るテストは、runner が期待どおり返らないと孫 PID が得られず、孫(`sleep 30`)が残る | 採用: 孫 PID を一時ファイルで受け取り、runner の成否によらず `finally` で止めて停止を確認する。経過時間の上限値は CI で安定しているため変えない(`419ca15c`) |

- 検証(`419ca15c` 時点): `src/testing/` と `prohibitions.spec.ts` の 118 passed・eslint・prettier・vue-tsc・depcruise 緑。テスト後に孫プロセスが残っていないことを確認
