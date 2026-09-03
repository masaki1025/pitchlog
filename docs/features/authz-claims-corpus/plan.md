---
feature: authz-claims-corpus
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d093b75e68781d894cac8a869bea666
branch: fix/authz-claims-corpus
created: 2026-09-03
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TSK-270 要件主張母集合のマージ後レビュー P0 7 件の是正(TSK-312)

## 1. 背景・目的

- Notion タスク: [TSK-312](https://app.notion.com/p/3d093b75e68781d894cac8a869bea666)(元タスク: [TSK-270](https://app.notion.com/p/3cc93b75e687816a9230e1c1b0ded0e7) / ブロック解除先: [TSK-278](https://app.notion.com/p/3ce93b75e68781c0967ccd269ee0c5dd) ステップ 10)
- 要件: **NFR-018**(単一実装 — 母集合は認可カタログの信頼境界の起点)・**NFR-019(b)**(認可検証の oracle 入力)・**FR-013/FR-034/FR-041**(母集合が凍結する認可要件群)。例外表 2 セルは NFR-018 達成条件 (c)(要件書 :902-906)
- TSK-270(完了・PR #33)の要件主張母集合 `contracts/authz/requirement-claims.json`(1,062 件)に、マージ後の敵対レビューで **P0 7 件**が残っている。**一次記録(個別列挙)は消失しており復元不能**(4 方向で不在確認 — [research.md](research.md) §1)。耐久記録は「分類と `decidable_at` の誤り・closed-world 文の落ち・経路レジストリと要件行の結線ほか」の要約のみ
- 本タスクは①**母集合と派生・oracle 資産への敵対レビューを再実施して P0 を全数列挙し直し**、②裁定に基づき是正し、③TSK-233 申し送り(例外表 2 セル・インデント表の採取欠陥)を反映し、④派生資産・lock・oracle 資産・seal・テスト期待件数を追随させる。**完了が TSK-278 ステップ 10(甲-1 裁定 2026-09-03)の実施前提**
- 調査の正: [research.md](research.md)(P0 一次記録の不存在確認・3 カテゴリの構造的裏付け・資産地図・連鎖と順序制約)

## 2. スコープ

### やること(= 本計画の変更対象ファイル集合)

1. 母集合(1,062 件の分類・`decidable_at`・closed-world 表現・経路結線)と**派生 3 資産・oracle 6 資産**への**敵対レビューの再実施**と、指摘の全数列挙・PO 裁定 — 変更対象: `docs/worklog/2026-09-03-authz-claims-corpus.md`・`docs/features/authz-claims-corpus/**`
2. 裁定に基づく**母集合・検査器・スキーマの是正** — 変更対象: `contracts/authz/**`・`scripts/check_authz_catalog.py`・`tests/test_check_authz_catalog.py`・`tests/fixtures/authz_claims/**`
3. **採取器の是正**: `_table_cells` のインデント非対応(`scripts/check_authz_catalog.py:229-232`)の修正 + インデント表のフィクスチャ負例追加
4. **TSK-233 申し送りの反映**: 要件書 NFR-018 例外表の 2 セル更新(検証テスト = `frontend/src/lib/courseCoordinateContract.spec.ts` / 状態 = `有効`。**終了証跡・失効判定者・対象シンボル・対応する契約値はバイト単位で無変更**)+ 変更履歴追記 + `docs/README.md` 現行化。**ゲート区分 = 7.6-3 前段・版 2.4 のまま(PO 裁定 2026-09-03 — 「本書の改訂を要する」列挙は追加・削除・失効の 3 つで有効化は列挙外・状態欄は (c) の従属値)**
5. 派生 3 資産 + 各 lock + oracle 6 資産 + `oracle-seal.lock.json` + `tests/test_check_authz_catalog.py` の期待件数の追随(**H-85 の 2 段制約に従う** — §4-(2))

### やらないこと

- **H-85 対応案②(digest 連鎖の 1 段化)・③(期待件数の非ハードコード化)** — PO 裁定 2026-09-03 で見送り・別起票(③はハードコードが「資産が黙って変わらない」凍結の役割を兼ねており、資産から読むと同義反復化する懸念 — 設計未確定のまま P0 是正に相乗りさせない)。ステップ 7 で起票する
- **TSK-278 の要件書 v2.6 への追随** — 本タスクは develop の v2.4 blob(digest `38a9bc67…`)に対して是正する。v2.6 追随は TSK-278 ステップ 10 の仕事(マージ順: 本タスク → TSK-278)
- 経路レジストリの design-origin 範囲(FR-020〜032 の 13 節)の再設計 — TSK-250 の射程
- 例外表の**失効(卒業)** — TSK-275 の射程(有効化と失効は別事象 — ADR-003 :391)
- DDL・PostgreSQL 構成・backend/frontend コードの変更(例外表が参照する frontend spec は既存・無変更)

**裁定リストとの衝突規則(計画改訂トリガーの閉じ)**: ステップ 1 の裁定リストの項目が「やること」の変更対象ファイル集合の外に出る場合、または上記「やらないこと」と衝突する場合、その項目を**確定範囲へ黙って入れない**。PO が項目ごとに **(a) 不採用として別起票** / **(b) 計画改訂(§4-(5))へ戻す** のどちらかを裁定し、worklog に記録する。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | NFR-018 例外表の 2 セル(検証テスト・状態)+ 変更履歴 1 行追記。**版は 2.4 のまま** | **PR レビュー**(7.6-3 前段 — PO 裁定 2026-09-03) |
| `docs/README.md` | 要件書行の最終更新日の現行化 | PR レビュー(常に現行化) |
| `contracts/authz/**`(母集合・lock・派生 3 資産 + lock・oracle 6 資産・seal) | P0 是正・採取追随・例外表セルの source_text 追随・reseal | PR レビュー(コア領域 — 敵対レビュー + 逐行確認は H-12 代替統制で担保) |

**正本体系外だが同一 PR で更新するもの**: `scripts/check_authz_catalog.py`(採取器是正 + 裁定による検査強化)/ `tests/test_check_authz_catalog.py`(期待件数・負例)/ `tests/fixtures/authz_claims/**`(負例フィクスチャ)/ `docs/features/authz-claims-corpus/**`・`docs/worklog/2026-09-03-authz-claims-corpus.md`(feature 文書)

## 4. 実装方針

### (1) 重さ分類の根拠 — コア領域

母集合は**テナント分離**(設計書 6.3)の認可カタログ・oracle の入力であり、誤分類は認可検証の穴に直結する(TSK-270 と同型)。`.claude/core-areas.json` の tenant-isolation の paths に要件書が含まれるため機構(core-guard)でも検出される。`contracts/authz/**` 自体は paths 未収載のため **H-12 の代替統制**を踏襲する: 計画・成果物の敵対レビュー / 人間の逐行確認 / PR チェック行の手動付与 / 典拠照合可能化(全変更レコードの帰属表 — §4-(4))。実装委任はラッパーが sol xhigh を自動適用する。

### (2) 順序の機構的制約(H-85 — research.md §5・§6)と red の機械的限定

- `_verify_manifest_commit` は「`input_manifest.commit` の指すコミットの要件書 blob = `source_blob_digest`」を要求 → **要件書の変更と母集合追随は同一コミットにできない**(先に要件書のみのコミット = **ステップ 2** を作り、**ステップ 5** で `input_manifest.commit` をステップ 2 のコミット SHA へ更新する)
- `oracle-seal.lock.json` は同制約を `oracle_commit`(8 入力資産の git blob)にも課し、`--reseal-oracle` は `oracle_commit` を自動更新しない → **8 入力資産を確定するコミット(= ステップ 5)を先に作り、ステップ 6 で `oracle_commit` をその SHA へ差し替えてから `--reseal-oracle`**(2 段)
- **各ステップの想定 red(これ以外の red は回帰として差し戻し)**:
  - ステップ 2 の後: `tests/test_check_authz_catalog.py::test_repository_catalog_covers_the_entire_requirements_file` のみ red(source_blob_digest 不一致)
  - ステップ 3・4 の後: 同上(kind/採取差分・検査強化による差分が加わる)。**フィクスチャ単体テストは green を維持**
  - ステップ 5 の後: `test_repository_oracle_assets_are_valid` のみ red(seal 未追随)。判定は **`check_authz_catalog.py --skip-oracle` の green** で行う(`--skip-derived` 単独は不可 — :3792)
  - ステップ 6 の後: **全 green**(lock 4 本 bytes 不変検査を含む)
- 例外表セルの変更(ステップ 2)と採取器是正(ステップ 3)は同じ 3 レコード(`NFR-018/paragraph-00{1..3}` → table 系 kind へ)を触るため、母集合追随(ステップ 5)で一括して 1 回で追随する

### (3) 再列挙の設計(ステップ 1 — 一次記録の消失への対処)

- **対象 = `contracts/authz/` 全資産**(母集合 + 決定 lock + **派生 3 資産 + 各 lock + oracle 6 資産 + seal**)+ 検査器 + 要件書 v2.4(凍結時と同一 blob — 入力条件は当時と等価)。結線情報(`source_claim_ids`)は経路レジストリ側にしかないため、**母集合だけを対象にすると結線の指摘が構造的に不可能**になる(計画レビュー 1 周目 P0-1)
- **観点の下限**(これを明示して依頼する): ①分類・`decidable_at` の誤り(誤 out_of_scope・誤 layer・誤 location)②closed-world 文(全域性宣言)の扱い ③経路レジストリと要件行の結線(**http 判定可能 184 件中 166 件が未結線・cache 17 件は下流ゼロ・db のみ exact-set** — research.md §2)④分類規則の罠の無力(`allowed_source_kinds: []` = 制約なし)⑤インデント表の採取欠陥(既知 — 8 件目候補)⑥oracle 資産(claim-mutant-map 等)と母集合の整合
- **H-53 の統制の具体形**(言葉の警告にしない — 計画レビュー 1 周目 P1-4):
  - レビュアーには**指摘対象の claim ID / 資産エントリ ID を機械可読リスト(1 行 1 ID)で出力**させる(自然文の中に埋めさせない)
  - Claude(PR 作成者)は母集合・派生資産から **python で直接**全 ID・分布(classification・kind・location・layer)を機械列挙し、レビュアーのリストと **ID の exact-set(差集合 0)**で突合する。**件数照合だけにしない**(脱落と混入の相殺を許さない)。checker の標準出力(total/auth/out/db/routes/cells のみ)に依存しない
  - 列挙結果と突合結果は `docs/features/authz-claims-corpus/` 配下へ機械可読で保存し、コミットに含める
- 当時の「7 件」との件数一致は要求しない — **再列挙の結果が新しい正**(worklog に旧要約 3 カテゴリとの対応を記録する)
- 全指摘に PO 裁定(採用/不採用・是正方針)を取り、**裁定リストがステップ 2〜6 の確定範囲**になる。§2 の衝突規則に該当する項目は (a) 別起票 / (b) 計画改訂 の PO 裁定を経る

### (4) 委任の分担と帰属の照合(CLAUDE.md の役割分担)

- コード(採取器・検査器・テスト)と母集合 JSON の機械的追随 = **`codex_run.py implement` 委任**(ステップ単位)
- 要件書・変更履歴・README・worklog = **Claude 直編集**(ドキュメントは Claude の役割)
- 是正の**分類判断そのものは PO 裁定リストで固定**してから委任する(委任先に判断させない — H-53)
- **帰属の照合(1:1 ではなく全帰属)**: 全変更レコード・全変更ファイルが「裁定リストの項目」または「既知 2 件(採取欠陥・例外表セル)」の**いずれかに帰属し、帰属のない変更が 0** であることを表で照合する(1 指摘対複数レコード・1 レコード対複数根拠を許す — 計画レビュー 1 周目 P1-8。例: 例外表データ行は採取欠陥〔kind/ID 変更〕と例外表セル〔source_text 変更〕の両方に帰属する)

### (5) ステップ 4 の粒度規定(裁定前に確定できない部分の扱い)

裁定リストのうち**検査器・スキーマの意味論に触れる是正**はステップ 4 に置く。裁定確定後、変更単位が**複数の独立した検査意味論**にまたがる場合は、**ステップ表を 4a・4b…に分割する計画改訂**(表の分割のみ・レビューは差分周 1 回)を経てから実行する(1 ステップ = 1 論理変更 = 1 コミットを裁定後にも保証する — 計画レビュー 1 周目 P1-6)。裁定リストに該当項目が 0 件の場合、ステップ 4 は「実施なし(裁定リストに検査意味論の変更なし)」を worklog に記録するコミットで閉じる。

### 実装ステップ(コミット単位)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **母集合・派生・oracle 資産の敵対レビュー再実施(P0 の再列挙)** — `codex_run.py review adversarial` に §4-(3) の対象・観点下限・機構列挙の縛り(ID リスト出力)で依頼。指摘の全数を worklog へ記録し、**PO 裁定(採用/不採用・是正方針)を取得**。旧要約 3 カテゴリ + 8 件目候補との対応表を作る | 全指摘に重大度と裁定が付き未裁定 0 / **指摘 ID リストと Claude の機械列挙の exact-set 突合(差集合 0)が保存されている** / 裁定リスト(= ステップ 2〜6 の確定範囲)が worklog にある / §2 衝突規則の該当項目は (a)/(b) の PO 裁定記録がある |
| 2 | **要件書 NFR-018 例外表の 2 セル更新**(Claude)— 検証テスト・状態の 2 セルのみ + 変更履歴 1 行 + `docs/README.md` 最終更新日 | 差分が 2 セル + 変更履歴 + README に限られる / 他セル・他行はバイト単位で無変更 / 版セルが 2.4 のまま / 想定 red が §4-(2) のとおり(それ以外の red なし) |
| 3 | **採取器の是正 + 負例**(codex 委任・既知分のみ)— `_table_cells` のインデント対応 + インデント表のフィクスチャ負例 | フィクスチャ単体テストで**負例が是正前 red → 是正後 green** の記録(実行コマンドと出力を worklog へ)/ 想定 red が §4-(2) のとおり / 既知分以外の変更なし |
| 4 | **裁定由来の検査器・スキーマ是正**(codex 委任)— ステップ 1 の裁定リストのうち検査意味論に属する是正(例: 分類規則の罠の実効化・closed-world/結線の検査)。**複数の意味論にまたがる場合は §4-(5) の計画改訂で分割してから** | 裁定リスト外の変更なし / 各変更が裁定項目へ帰属 / フィクスチャ単体テスト green / 想定 red が §4-(2) のとおり。0 件時は「実施なし」の worklog 記録コミット |
| 5 | **母集合・lock・派生 3 資産の追随**(codex 委任)— 裁定リストの分類・`decidable_at` 是正 + 採取追随(kind/source_id 変更 3 件)+ 例外表セルの source_text 追随 + `input_manifest.commit` = ステップ 2 コミット SHA + `--reseal` → 派生 3 資産の `input_manifest` 更新 + `--reseal-derived` + `tests/` 期待件数の更新 | **`check_authz_catalog.py --skip-oracle` green** / **Claude が python で直接計数した分布(classification・kind・location・layer)と全 ID 集合の照合が一致**(checker 出力に依存しない)/ **帰属表(§4-(4))で帰属のない変更 0** |
| 6 | **oracle 6 資産の追随 + seal の 2 段目**(codex 委任)— 裁定による AUTH 集合・DB 判定可否の変化を `claim-mutant-map.json`・`attack-tree.json` 等へ exact-set 追随 + 6 資産の `oracle_context.oracle_commit` と seal の `oracle_commit` を**ステップ 5 コミット SHA**へ差し替え + `--reseal-oracle` | `uv run pytest tests/` **全 green**(lock 4 本 bytes 不変検査を含む)/ seal の `input_assets` 8 件が現物 blob と一致 / oracle 6 資産の変更が裁定項目へ帰属 |
| 7 | **総合検証と後片付け**(Claude)— /check 一式・**人間の逐行確認用の突合シートを機械生成**(変更レコード全数 × 帰属根拠)・H-85 案②③の別起票(Notion)・worklog 締め | /check green / 突合シートが変更全数を覆う / 起票 URL が worklog にある |

## 5. DoD(Notion TSK-312 と同期)

- [ ] P0 の再列挙が完了し、全指摘に PO 裁定が付いている(一次記録の消失と再列挙の経緯が worklog に記録 — ID の exact-set で独立照合)
- [ ] **採用裁定された指摘の是正が母集合・検査器・派生資産・oracle 資産へ全件反映され、未反映 0**(帰属表と突合シートで確認)
- [ ] TSK-233 申し送りの反映: 例外表 2 セル更新(7.6-3 前段・版 2.4 のまま)+ 母集合追随が同一 PR にある
- [ ] インデント表の採取欠陥が是正され、負例が追加されている(是正前 red の記録つき)
- [ ] 派生 3 資産 + 各 lock + oracle 6 資産 + seal + tests の期待件数が追随し `uv run pytest tests/` green
- [ ] コア領域として敵対レビュー + 人間の逐行確認を通っている(突合シートで支援)

## 6. テスト計画(NFR-019)

- **単体(ハーネス pytest)**: インデント表の負例フィクスチャを `tests/fixtures/authz_claims/` に追加(**是正前 red → 是正後 green を、実行コマンドと出力つきで worklog に記録**)。既存統合テスト 3 本(:300・:885・:1279)は期待件数更新のうえ green 維持。lock 4 本の bytes 不変検査(:301-324)を維持
- **一致性・越境・E2E・故障系**: 対象外(本タスクは contracts + scripts + tests + 文書のみ。DB・API・フロントのコード変更なし — 例外表が参照する `frontend/src/lib/courseCoordinateContract.spec.ts` は既存・無変更で Vitest green を /check で確認)
- 検証コマンド: `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/` / `uv run python scripts/check_authz_catalog.py`(中間ステップは `--skip-oracle` — §4-(2))。**分布・ID 集合の照合は checker 出力に依存せず Claude が python で直接計数**(worklog へ転記)
