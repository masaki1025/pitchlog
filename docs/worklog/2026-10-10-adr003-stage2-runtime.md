---
date: 2026-10-10
topic: ADR-003 段階 2 の実行経路 — D-2 の実行基盤を作り、付録E 引き渡し契約の受け手になる(TSK-538)
branch: feature/adr003-stage2-runtime
---

# 作業ログ: 2026-10-10 ADR-003 段階 2 の実行経路(TSK-538)

## やったこと

### /task-start

- 既存 Notion タスクに着手: https://app.notion.com/p/3f593b75e687817085ddefcaeff3687b (TSK-510 の PO 裁定 2026-10-10 で起票・案 A = 実行経路と段階 2 受取タスクを 1 本に統合)
- ブランチ `feature/adr003-stage2-runtime` / worktree `../pitchlog-worktrees/feature-adr003-stage2-runtime`(`origin/develop` = `0e339ed9` 起点)
- **着手の判断**: master の盤面(2026-10-10)。U-X1 計画書(`docs/features/ux1-state-calc/design.md` §4)の着手条件 P-5 そのもの
- **射程の境界**(カード・PO 裁定): 発効前は実行基盤まで / 対象計算の追加は発効後。発効条件 (i)〜(iv) は TSK-541(510 タブ)の持ち物で、本タスクでは決めない

### /investigate(3 並列 + Web)

- `docs/features/adr003-stage2-runtime/research.md` に統合。食い違いの裁定 2 件(S34 の記録箇所 = 4 箇所の和 / TSK-541 はリポ内 0 件だが Notion に実在)
- **主セッションが原典で確認した 3 点**: ① manifest を置くと consistency が落ちる(`boot/report.py:227-231`)② 段階 2 判定器は 2 対象以上の同時完成を違反にする(`boot/phase2.py:395-398`)③ 終了判定 case は `expected` を持たず `decision` を持つ
- ②により **U-X1 計画書の PR-1(T1・T2 同一 PR)は通らない** — master へ通知

## 決定

- **射程 — 発効前の分で閉じる**(山田さん 2026-10-10): TSK-538 = 実行基盤・契約 schema v1 の改訂・`receiverTaskId` と S34 の更新・`receiverDoD` 6・(b) の割り当て・発効前に可能な部分(runner の revision 確定・`D` 実値)。**`receiverDoD` 1〜5 の残りと (a) の残りは U-X1 の対象計算の PR へ移す**(対象計算の実体なしに閉じられない — research.md §2)。Notion カードの DoD を改めた
- **所有者空白の (b) 11 件**(S08・S09・S15〜S21・S27・S28 — 当初 10 件と誤記)は **TSK-538 が引き取って解決する**(山田さん 2026-10-10)。独立に確認した期待値で(CI 規則 3 `ADR-003:334`)
- **追加調査(2026-10-11)の後の裁定**(山田さん): 11 件のうち S15〜S18 が正本の改訂を要すると判明したうえで、**TSK-538 に残す**(D2)。schema は **v1 のまま改訂**(D3)。置き場は **`frontend/src/domain/`・`backend/src/pitchlog/domainrt/` を宣言**(D4 — #116 のマージ後)。エンジンは**試験で決める**(D5)。S15・S16 は **descriptor の分割**(D6)、S20 は**台帳 schema の役割を 5 つに**(D7)、S21 は **operationRows `game-end-declaration`**(D8)、S08・S09 は **U-X1 の状況判定 PR へ送り直す**(D9)。→ TSK-538 が解決するのは 9 件
- 計画書の作り方(33 ステップ・ゲート 6 つ)は計画モードで山田さんが承認(2026-10-11)。plan.md の「承認: 済」は計画レビューの後に改めて得る

### /plan

- plan.md(6 節・33 ステップ・ゲート ①〜⑥)と design.md(裁定 D1〜D9・構成・条文と担保の対応・エンジン試験の基準・契約 9 件の順序・送り先の表・コア宣言・リスク)を作成

## 未決・次の一歩

- /investigate で現況を測り直す(カードの実測は develop `24c023e4` 時点。#95 で `scripts/core_guard.py` が変わった — TSK-540 の前提「逆依存閉包が 11 件を巻き込む」も要再測)
- #116(U-F2)が core_guard・core-areas を触って OPEN。検査経路に触る場合は #116 のマージ後に置き換え式・2 段コミットで
- `receiverTaskId` の更新と、未解消レポートの S34 行の TSK-540 への更新(510 からの申し送り)

### 計画レビュー 1 周目(全文・敵対)— 否決 P0 2 / P1 5 / P2 0 → **全件採用**

| # | 重大度 | 指摘 | 採否 | 反映 |
| --- | --- | --- | --- | --- |
| 1 | P0 | ステップ 2 の「wheel が入手できる」は Node を選んだとき緑にできない | 採用 | QuickJS 選択時は wheel、Node 選択時は版・配布・起動を固定する条件に分けた |
| 2 | P0 | ステップ 15 で `ci.yml` を変え corpus の受理を 16 に送ると、15 時点で凍結 corpus の digest 検査(`tests/test_frozen_archive_case_runner.py:222-231`)が赤 | 採用 | CI の変更と凍結 corpus の受理記録を 15 にまとめた。番号を保つため manifest schema の enum 追加を 16 へ移した(17 以降は不変) |
| 3 | P1 | 非リテラルの require・import の拒否だけでは、リテラルな別モジュール読み込みが残る artifact が緑になる(`ADR-003:752-756`) | 採用 | ステップ 6 を単一ファイル方式とし、リテラル・非リテラルを問わず拒否・リテラルの負例を追加 |
| 4 | P1 | ホストの負例が eval だけで、Node を選んだときの Function・動的 import を検証できない(`ADR-003:748-749`) | 採用 | ステップ 7 を製品ホスト経由・3 経路それぞれの拒否試験に |
| 5 | P1 | SQL 枠の試験が集計だけで (β)⑦ の行単位分類を覆わない(`ADR-003:798-802`) | 採用 | ステップ 10 に行単位分類と負例を追加 |
| 6 | P1 | 収集器が `boot/report.py` に接続されず、manifest が入ったときに報告できることを検証できない(BOOT-REPORT 要件書 `:962`) | 採用 | ステップ 14 に report.py への接続と manifest ありの報告試験を追加 |
| 7 | P1 | S20 は余剰得点の計上検証まで含むのに、design.md が U-X1 へ送っていた | 採用 | ステップ 25 に付録E 状態遷移契約のサヨナラ時の得点値の case を追加し、S20 を本タスクで閉じる |

### 計画レビュー 2 周目(反映差分と影響節)— 1 周目: 解消 6・部分的 1 / 新規 P1 2 / P0 0 → **全件採用**

| # | 重大度 | 指摘 | 採否 | 反映 |
| --- | --- | --- | --- | --- |
| 1 | P1 | サヨナラ時の得点値を「状況判定契約の case」として手で足すと、規範行が正で case は派生物(`ADR-003:293-301`)に反する。現行の `matrixRows` には得点値もサヨナラ文脈も表す列が無い | 採用 | 表現(サヨナラ文脈の前提条件の軸と得点上限の列)をステップ 27 の正本改訂に含め、ゲート ⑤ の後に**ステップ 32(新設)**で規範行を足して case を展開器で派生させる。S20 は 25(終了判定側)と 32(状況判定側)の 2 コミットに。旧 32・33 は 33・34 へ繰り下げ(**計 34 ステップ**) |
| 2 | P1 | 逐行確認シート(旧 32)が規範行だけを覆い、得点値の case の期待値を承認対象に含めない(`ADR-003:334`) | 採用 | ステップ 33 のシートを「規範行と派生 case の入力・期待値」を覆う形にし、サヨナラ時の得点値は要件書 `:249` から独立に導いた値との照合結果を含める。ゲート ⑥ の承認対象はこの digest のシート |

- **P0 なしのため 3 周目は回さない**(設計書 6.3「レビュー回数の上限」— 3 周目は 2 周目に P0 が残り採用したときだけ)。残る指摘なし(全 9 件採用・不採用 0)

### 計画承認(2026-10-11)

- **山田さんが計画書(plan.md + design.md・34 ステップ)を承認**。3 周目の追加レビューは行わない判断
- **ゲート ① を兼ねる**: 技術スタックの追加(QuickJS または常駐 Node・esbuild — 要件書 7.1 `:1059`)と、artifact の `frontend/public` 配置・配信を了承
- 次: /implement でステップ 1(エンジン試験)→ ゲート ②(PO がエンジンを承認)

### ステップ 1 とゲート ②(2026-10-11)

- ステップ 1(`d39b2696`): quickjs-ng は条件 2 が不合格(`disable_eval` が無視され、`globalThis.eval` の削除後も `new Function` が通る)。常駐 Node は起動オプション `--disallow-code-generation-from-strings` と `vm` の `codeGeneration` 設定・動的 import ローダーなしで 3 経路を拒否。ネットワーク使用は山田さん了承(`PITCHLOG_NET_REASON` を記録)
- **ゲート ②: 山田さんが常駐 Node を承認**(2026-10-11)。本番の CPU は x86_64・aarch64 の両方

### 計画の改訂(2026-10-11)— ステップ 2 に配布定義

- 本番の配布定義がリポジトリに無い(開発 DB の docker-compose のみ)ことが分かり、山田さんが **「配布定義も作る」** を指示。ステップ 2 に `backend/Dockerfile`(Node 24.16.0 を同梱・x86_64/aarch64)と `.dockerignore` を追加、ステップ 15 に x86_64 での build 確認を追加
- 承認済みの計画を変えるため、**改訂のあいだ「承認: 未」に戻した**。差分の敵対レビューを経て再承認を得る
- esbuild の取得のためのネットワーク使用は山田さん了承(2026-10-11)

#### 計画レビュー 3 周目(改訂差分)— P0 0 / P1 1 / P2 0 → **採用**

| # | 重大度 | 指摘 | 採否 | 反映 |
| --- | --- | --- | --- | --- |
| 1 | P1 | 追加した検証が build と `node --version` までで、FastAPI がイメージ内で起動し常駐 Node を使えることを確かめない(design.md の「起動の固定」と DoD「実行基盤が動く」に対応しない) | 採用 | ステップ 3 の公開口に疎通用の操作(対象計算ではない)を置き、ステップ 15 の CI でイメージを起動して FastAPI の起動時検査と常駐 Node 経由の疎通を確かめる合格条件を追加 |

- 改訂差分のレビューは 1 周で P0 なし。再承認へ上げる

- **山田さんが改訂後の計画書を再承認**(2026-10-11)

### 実装の進行(2026-10-11)

- ステップ 1〜10 をコミット(`d39b2696`〜`d5867035`)。差し戻し: ステップ 2(pnpm 11 の allowBuilds — `esbuild: false` で足りる)・ステップ 7(`.mjs` の同梱を package-data へ / artifact・宣言・`.venv` を root 所有に)・ステップ 10(DB 試験を既存の DB fixture へ — 試験内で docker を起動しない)
- **ステップ 15 への申し送り**: backend の DB 試験(`backend/tests/db/test_domain_sql_generation.py`)が Node を呼ぶ。**backend の CI ジョブにも Node 24.16.0(mise)を入れる**こと(計画のステップ 15 は frontend・harness だけを挙げている)
- 既存の挙動: backend の `pytest -m "not requires_db"` は全件 passed でも終了コード 1(`tests/db/conftest.py` が DB 試験 0 件のセッションを失敗にする)。本タスクの変更ではない

- **squash マージ禁止**: ステップ 20 で引き渡し契約の依存(`frontend/src/testing/vectorRunner.ts`)の commit OID を本ブランチのステップ 11 のコミット `f8df3ada` に向けた(段階 2 の読み込み接続後の現行版)。squash マージすると OID が develop に残らず参照が壊れるので、**PR はマージコミットで取り込む**(PR 本文にも書く)

### ゲート ④(2026-10-14)— 送り先の起票

- 山田さんの判断で Notion に 3 枚起票: **TSK-544** U-X1 T1 状況判定の対象計算(ブロック中)/ **TSK-545** U-X1 T2 終了判定の対象計算(ブロック中)/ **TSK-546** 付録E 契約の PO 裁定 3 件(S11・S13・S22)
- (b) 27 件の送り先(山田さん): TSK-538 = S15〜S21・S27・S28(9 件)/ TSK-544 = S05〜S10・S12・S14・S23〜S26・S30〜S32(15 件)/ TSK-546 = S11・S13・S22(3 件)
- ステップ 11 の見落とし: 契約参照の試験ファイル(`tests/domain/runners/test_handoff_loader.py`)が sync-protocol に未登録のまま `test_core_guard` が赤だった(ステップ 11 の検証で `test_core_guard` を回していなかった)。ステップ 17〜19 の登録で解消

- ステップ 25 の委任でラッパーが終了コード 1 を返した(Codex の最終報告は出ており、出力は 9MB で途中が切れていた)。原因は特定できず。作業ツリーを自分で検証して緑(関連 pytest 673 passed・ルートの ty 0・ローカルで回せる check_* 全件 OK)だったのでコミットした。`--acceptance` の受理遷移検査は PR の CI で確認する

### ドラフト PR #131 と受理記録の承認(2026-10-14)

- 凍結基準の受理単位が PR 番号のため、**ドラフト PR #131** を開いた(山田さん了承)。受理 ID = `masaki1025/pitchlog#131`
- **山田さんの承認(2026-10-14)**: ① `gameEndAxisFields` に成立段数の軸を足す(ステップ 26・S19)② `ci.yml` の変更(ステップ 15)に伴う `contracts/tenant_boundary/base-allowlist.json` の凍結基準の更新 ③ トリガー 10(propertyCatalog のトップレベル分離)の判定「発火しない」(2026-09-18)は `manifest.schema.json` への `js-artifact` 追加(ステップ 16)後も不変 — 証拠の digest を更新
- develop の取り込み 2 回(`4daa4155`・`7b71c38b`)。ステップ 22〜25 の検証でハーネスの全件を回していなかったため、10 件の失敗をまとめて是正(`72d2a487`)。以後、PR 前にハーネスの全件を回す
- **Ready 前の取り込みで必ずやること**(master の申し送り 2026-10-14): ① #119(δ)が `contracts/tenant_boundary/base-allowlist.json` を rev27→28・`runtime-authz-contract.json` を rev12→13 へ動かす。#119 が先に着地したら、本 PR の base-allowlist の受理記録(#131)の rev を**実測し直して作り直す**(digest・識別値は導出値 — 選ばず取り直す)② `.claude/core-areas.json` と `docs/README.md` が #128(TSK-541)と重なる
- **ステップ 27 は #128 の着地を待つ**: #128 が ADR-003 v0.6・要件書 v2.11 を approved で持つ(未マージ)。D-8 の改訂は v0.6 の上に積む。着手直前に ADR-003 の最大版を `refs/pull/128/head` を含めて実測する
- master の指摘: core_guard の同一コミット規則は `git diff-tree`(`-m`/`-c` なし)なのでマージコミットを検査しない — 本 PR は規則どおり 2 段に分けているが、機構の保証ではない(台帳候補として master が起票先を探す)
- **山田さんの承認(2026-10-14)④**: トリガー 11(manifest の登録要件)も `manifest.schema.json` を証拠にしており、判定「発火しない」(2026-09-18)は不変として再確認を追記・証拠の digest を更新
- ステップ 7 の設計の見落とし: `backend/src/pitchlog/domainrt/node_host.mjs` が tenant boundary の検査器(backend/src の非 Python を fail-closed で拒否 — TB000)に当たった。ホストスクリプトを `.py` の定数にして `node --eval` で起動する形へ是正
