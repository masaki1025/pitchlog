---
feature: authz-claims-corpus
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-03・山田正輝) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d093b75e68781d894cac8a869bea666
branch: fix/authz-claims-corpus
created: 2026-09-03
計画レビュー周回: 6        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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

1. 母集合(1,062 件の分類・`decidable_at`・closed-world 表現・経路結線)と**派生 3 資産・oracle 6 資産・seal**への**敵対レビューの再実施**と、指摘の全数列挙・PO 裁定 — 変更対象: `docs/worklog/2026-09-03-authz-claims-corpus.md`・`docs/features/authz-claims-corpus/**`
2. 裁定に基づく**母集合・検査器・スキーマの是正** — 変更対象: `contracts/authz/**`・`scripts/check_authz_catalog.py`・`tests/test_check_authz_catalog.py`・`tests/fixtures/authz_claims/**`
3. **採取器の是正**: `_table_cells` のインデント非対応(`scripts/check_authz_catalog.py:229-232`)の修正 + インデント表のフィクスチャ負例追加
4. **TSK-233 申し送りの反映**: 要件書 NFR-018 例外表の 2 セル更新(検証テスト = `frontend/src/lib/courseCoordinateContract.spec.ts` / 状態 = `有効`。**終了証跡・失効判定者・対象シンボル・対応する契約値はバイト単位で無変更**)+ 変更履歴 1 行追記 + `docs/README.md` 現行化。**ゲート区分 = 7.6-3 前段・版 2.4 のまま(PO 裁定 2026-09-03)**。**変更履歴の追記行自体も全数採取の対象になる**(母集合 total 1062 → **1063**・`CHANGELOG` 配下の `table_row` +1。**分類の既定 = 既存の変更履歴行と同じ規則による `out_of_scope`** — 新規行はステップ 1 時点で未存在のため母集団・観点には含めず〔§4-(3)〕、ステップ 10 の合格条件で Claude が規則適用の妥当性を検査し、PR の総合敵対レビューの対象に含める)
5. 派生 3 資産 + 各 lock + oracle 6 資産 + `oracle-seal.lock.json` + `tests/test_check_authz_catalog.py` の期待件数の追随(**H-85 の 2 段制約に従う** — §4-(2))

### やらないこと

- **H-85 対応案②(digest 連鎖の 1 段化)・③(期待件数の非ハードコード化)** — PO 裁定 2026-09-03 で見送り・別起票(③はハードコードが「資産が黙って変わらない」凍結の役割を兼ねており、資産から読むと同義反復化する懸念 — 設計未確定のまま P0 是正に相乗りさせない)。ステップ 12 で起票する
- **TSK-278 の要件書 v2.6 への追随** — 本タスクは develop の v2.4 blob(digest `38a9bc67…`)に対して是正する。v2.6 追随は TSK-278 ステップ 10 の仕事(マージ順: 本タスク → TSK-278)
- 経路レジストリの design-origin 範囲(FR-020〜032 の 13 節)の再設計 — TSK-250 の射程
- 例外表の**失効(卒業)** — TSK-275 の射程(有効化と失効は別事象 — ADR-003 :391)
- DDL・PostgreSQL 構成・backend/frontend コードの変更(例外表が参照する frontend spec は既存・無変更)

**裁定リストとの衝突規則(計画改訂トリガーの閉じ)**: ステップ 1 の裁定リストの項目が「やること」の変更対象ファイル集合の外に出る場合、または上記「やらないこと」と衝突する場合、その項目を**確定範囲へ黙って入れない**。PO が項目ごとに次のどちらかを裁定し、worklog に記録する:
- **(a) 不採用として別起票** — **起票する項目が有効な P0(認可の穴)を含む場合、PO は同時に「後続タスクを本タスクの /task-done の前提とするか」「TSK-278 ステップ 10 のブロッカへ昇格するか」を裁定**し、Notion 相互リンクと worklog へ記録する(P0 を起票だけで宙に浮かせない)
- **(b) 計画改訂へ戻す** — スコープ(§2)・ステップ表・正本宣言(§3)を改訂し、**差分の再レビュー 1 周**を経て再承認する(§4-(5) の分割改訂に限らない通常の計画改訂)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | NFR-018 例外表の 2 セル(検証テスト・状態)+ 変更履歴 1 行追記。**版は 2.4 のまま** | **PR レビュー**(7.6-3 前段 — PO 裁定 2026-09-03) |
| `docs/README.md` | 要件書行の最終更新日の現行化 | PR レビュー(常に現行化) |
| `contracts/authz/**`(母集合・lock・派生 3 資産 + lock・oracle 6 資産・seal) | P0 是正・採取追随・例外表セル/変更履歴行の追随・reseal | PR レビュー(コア領域 — 敵対レビュー + 逐行確認は H-12 代替統制で担保。**oracle 資産の変更は seal の review_policy に従い差分敵対レビュー + 人間確認を経る** — ステップ 11) |

**正本体系外だが同一 PR で更新するもの**: `scripts/check_authz_catalog.py`(採取器是正 + 裁定による検査強化)/ `tests/test_check_authz_catalog.py`(期待件数・負例)/ `tests/fixtures/authz_claims/**`(負例フィクスチャ)/ `docs/features/authz-claims-corpus/**`(帰属表 `attribution.json`・レビュー母集団リストを含む)・`docs/worklog/2026-09-03-authz-claims-corpus.md`(feature 文書)

## 4. 実装方針

### (1) 重さ分類の根拠 — コア領域

母集合は**テナント分離**(設計書 6.3)の認可カタログ・oracle の入力であり、誤分類は認可検証の穴に直結する(TSK-270 と同型)。`.claude/core-areas.json` の tenant-isolation の paths に要件書が含まれるため機構(core-guard)でも検出される。`contracts/authz/**` 自体は paths 未収載のため **H-12 の代替統制**を踏襲する: 計画・成果物の敵対レビュー / 人間の逐行確認 / PR チェック行の手動付与 / 典拠照合可能化(帰属表 — §4-(4))。実装委任はラッパーが sol xhigh を自動適用する。

### (2) 順序の機構的制約(H-85 — research.md §5・§6)と red の機械的限定

- `_verify_manifest_commit` は「`input_manifest.commit` の指すコミットの要件書 blob = `source_blob_digest`」を要求 → **要件書の変更と母集合追随は同一コミットにできない**(先に要件書のみのコミット = **ステップ 2** を作り、**ステップ 10** で `input_manifest.commit` をステップ 2 のコミット SHA へ更新する)
- `oracle-seal.lock.json` は同制約を `oracle_commit`(8 入力資産の git blob)にも課し、`--reseal-oracle` は `oracle_commit` を自動更新しない → **8 入力資産を確定するコミット(= ステップ 10)を先に作り、ステップ 11 で `oracle_commit` をその SHA へ差し替えてから `--reseal-oracle`**(2 段)
- **ステップ 10 内の reseal 実行順(一意化 — 計画レビュー 2 周目 P1-6)**: ①母集合 + 決定 lock の更新 → `--reseal --skip-derived --skip-oracle` ②派生 3 資産の `input_manifest`(母集合の新 blob digest)更新 → `--reseal-derived --skip-oracle` ③`tests/` 期待件数更新 → 判定 = `check_authz_catalog.py --skip-oracle` green(`--skip-derived` は単独使用不可 — :3792)
- **想定 red の固定方法**: 各ステップの委任前に **Claude が「当該ステップ完了後の期待失敗集合」(下記見込みを現物で検算したもの)を worklog に固定**し、委任後に **`uv run pytest tests/ -q --no-header`(全件実行 — `-x` は初回失敗で停止するため使わない)**で失敗テスト ID を完全列挙して**期待集合との一致**で判定する(委任前の実測は開始状態の確認であり比較基準ではない — 正しい実装でも前後で集合は遷移する。計画レビュー 3 周目 P0-2・P0-3)。**現時点の見込み**(実測で確定): ステップ 2〜9 の後 = `test_repository_catalog_covers_the_entire_requirements_file`(source_blob_digest 不一致。**同一原因で `test_repository_derived_assets_are_valid`・`test_repository_oracle_assets_are_valid` が推移的に red になる場合はそれも列挙に含める**)/ ステップ 10 の後 = **`test_repository_catalog_covers_the_entire_requirements_file`(引数なし実行が未追随の oracle seal 検査へ到達 — :3865)と `test_repository_oracle_assets_are_valid` の 2 本**(計画レビュー 2 周目 P1-7)/ ステップ 11 の後 = **なし(全 green)**。**フィクスチャ単体テストは全ステップで green を維持**
- 例外表セル・変更履歴行(ステップ 2)と採取器是正(ステップ 3)は同じ NFR-018 周辺レコードを触るため、母集合追随(ステップ 10)で一括して 1 回で追随する

### (3) 再列挙の設計(ステップ 1 — 一次記録の消失への対処)

- **対象 = `contracts/authz/` 全 15 資産**(母集合 + 決定 lock + 派生 3 資産 + 各 lock + oracle 6 資産 + seal)+ 検査器 + 要件書 v2.4。結線情報(`source_claim_ids`)は経路レジストリ側にしかないため、母集合だけを対象にすると結線の指摘が構造的に不可能になる(計画レビュー 1 周目 P0-1)
- **観点の下限**: ①分類・`decidable_at` の誤り ②closed-world 文(全域性宣言)の扱い ③経路レジストリと要件行の結線(http 判定可能 184 件中 166 件未結線・cache 17 件下流ゼロ・db のみ exact-set)④分類規則の罠の無力(`allowed_source_kinds: []` = 制約なし)⑤インデント表の採取欠陥(既知)⑥oracle 資産(claim-mutant-map 等)と母集合の整合(**ステップ 2 で加わる変更履歴行はステップ 1 時点で未存在のため母集団・観点に含めない** — 分類は §2-4 の既定で固定し、ステップ 10 の合格条件で Claude が規則適用の妥当性を検査、PR の総合敵対レビューの対象に含める〔計画レビュー 3 周目 P0-4〕)
- **H-53 の統制の具体形(2 種類の集合を区別する — 計画レビュー 2 周目 P0-2・P0-3)**:
  1. **走査の全数性**: レビュアーに「**走査した母集団の全エントリ ID**」を **`<資産ファイル名>:<エントリ主キー>` の名前空間付き**で 1 行 1 ID の機械可読リストとして出力させる(母集合と決定 lock は同じ `source_id` を持つため名前空間なしでは lock の未走査を検出できない)。**主キーを持たない部分(`input_manifest`・`scope`・`classification_rules`・`basis_rules`・review/reseal policy・列挙表等)は `<資産ファイル名>:<JSON トップレベルキー>` 単位で列挙対象に含める**。**レビュー対象は 15 資産に加えて検査器と要件書を含むため、母集団リストには `check_authz_catalog.py:<トップレベル関数・クラス名・モジュールレベル定数名(大文字名 — `CLASSIFICATIONS`・`ROUTE_CLASSES`・`REQUIRED_*` 等の認可判定を規定する定数群を含む)>` と `requirements-pitchlog-2026-07-22.md:<heading_id>`(125 件)も含める(計画レビュー 5 周目 P0-1)**(計画レビュー 4 周目 P0-1)。**Claude は全対象から python で直接同じ名前空間付き集合を機械列挙し、exact-set(差集合 0)で突合**する(計画レビュー 3 周目 P0-5) — これが「全数を走査した」ことの証明
  2. **指摘の帰属**: 指摘対象 ID リストは**上記母集団リストの部分集合**であることを検査する(母集団外の ID の混入 = fail)
  - 両リストと突合結果は `docs/features/authz-claims-corpus/` 配下へ機械可読で保存し、コミットに含める。件数照合だけにしない(脱落と混入の相殺を許さない)。checker の標準出力に依存しない
- 当時の「7 件」との件数一致は要求しない — **再列挙の結果が新しい正**(worklog に旧要約 3 カテゴリとの対応を記録する)
- 全指摘に PO 裁定(採用/不採用・是正方針)を取り、**裁定リストがステップ 2〜11 の確定範囲**になる。§2 の衝突規則に該当する項目は (a)/(b) の PO 裁定を経る

### (4) 委任の分担と帰属の照合(CLAUDE.md の役割分担)

- コード(採取器・検査器・テスト)と母集合 JSON の機械的追随 = **`codex_run.py implement` 委任**(ステップ単位)。要件書・変更履歴・README・worklog = **Claude 直編集**
- 是正の**分類判断そのものは PO 裁定リストで固定**してから委任する(委任先に判断させない — H-53)
- **帰属表の定義(H-12 典拠照合の中核 — 計画レビュー 2 周目 P1-11)**: 保存先 = `docs/features/authz-claims-corpus/attribution.json`(機械可読・コミットに含める)。**比較基準 = 分岐点コミット `41884a9`(origin/develop)との git diff のうち、成果物(`contracts/authz/**`・`scripts/check_authz_catalog.py`・`tests/**`・要件書・`docs/README.md`)に限る** — feature 文書(plan/research/worklog/母集団リスト/突合シート/`attribution.json` 自身)は記録であり帰属対象に含めない(自己再帰の排除 — 計画レビュー 3 周目 P0-1)。抽出単位 = **JSON 資産はエントリ単位**(母集合 = `source_id` / lock = 決定 ID / 派生・oracle = 各エントリ主キー / manifest・seal のメタフィールドは「フィールド名」単位)/ **コード・テスト・文書は hunk 単位**。各エントリの帰属先 = 「裁定リストの項目 ID」「既知 3 件(採取欠陥・例外表セル・変更履歴行)」「機械的追随(digest・件数・oracle_commit — 帰属元の変更に従属)」のいずれか。**帰属のない変更 0** を機械検査し、人間の逐行確認用の突合シートは attribution.json から生成する(1 指摘対複数エントリ・1 エントリ対複数根拠を許す)

### (5) 意味論ステップの粒度規定(裁定前に確定できない部分の扱い — 発動済み)

裁定リストのうち**検査器・スキーマの意味論に触れる是正**は意味論単位のステップに置く。**本規定はステップ 1 の裁定(2026-09-03)で発動済み** — 意味論 6 単位((i)罠実効化 (ii)closed-world (iii)結線閉包 (iv)DDL 意味 (v)主張分割 (vi)probe_executable 判定)をステップ 4〜9 として分割した(差分レビュー 1 周を実施)。今後さらに独立単位が判明した場合も同じく**ステップ表を整数連番のまま振り直す計画改訂**(該当ステップを複数の整数ステップへ分割し、後続番号を繰り下げる — `feature_status.py` は整数連番のみ認識するため 4a・4b 等の枝番は使わない〔計画レビュー 2 周目 P1-4〕。**分割時は本文中のステップ番号参照(§4-(2) の red 規定・§2・§4-(6) を含む)を一括で更新**し、レビューは差分周 1 回。**総数が変わり得るため、本タスクのステップコミット件名には総数接尾辞 `/N` を付けず `(ステップ k)` のみを使う**〔計画レビュー 3 周目 P1-8〕)を経てから実行する。

### (6) oracle 資産の追随手続(ステップ 11 — 計画レビュー 2 周目 P1-8・P1-9)

- **追随対象の判定は checker に委譲する(依存閉包の正 = 検査器)**: ステップ 10 完了後に `check_authz_catalog.py`(引数なし)を実行し、**oracle 検査(`validate_claim_mutant_map` :2587・`validate_attack_tree` :3093 ほか)で fail した資産 = 追随対象**とする。**検査器は最初の `CatalogError` で停止するため、fail 集合は一括では得られない — 「fail → 当該資産の最小追随 → 再実行」を fail が oracle seal 検査(未 reseal 由来)だけになるまで反復する**(計画レビュー 4 周目 P1-3)(claim ID の直接交差だけでは HTTP matrix の allow セル・route registry・DDL・mutant 集合経由の間接依存を見落とす — 計画レビュー 3 周目 P1-6)。fail 0 の資産は `oracle_context.oracle_commit` の更新のみ。追随は **checker が強制する整合を green にする最小追随**に限る(参照フィールドの機械抽出は写像表の補助資料として worklog に残す)。**内容の新規判断(新しい変異・攻撃目標の設計等)は委任先に行わせない** — 判断が要る場合は差し戻して PO へ(写像表は worklog に記録)
- **seal の review_policy への適合(順序 — 計画レビュー 3 周目 P1-7)**: ①内容追随 → ②6 資産の `oracle_context.oracle_commit` と seal の `oracle_commit` をステップ 10 コミット SHA へ差し替え(**最終バイト列を確定**)→ ③**最終形に対して差分敵対レビュー + 人間の確認**(実施記録を worklog へ)→ ④`--reseal-oracle`(seal の digest のみ更新 — canonical digest は `oracle_context` を含む資産全体から生成されるため、レビュー後にバイト列を変えない)→ ⑤コミット(既存契約 — `contracts/authz/oracle-seal.lock.json` の review_policy)

### 実装ステップ(コミット単位)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **全 15 資産の敵対レビュー再実施(P0 の再列挙)** — `codex_run.py review adversarial` に §4-(3) の対象・観点下限・機構列挙の縛り(母集団全 ID リスト + 指摘 ID リストの 2 本出力)で依頼。指摘の全数を worklog へ記録し、**PO 裁定(採用/不採用・是正方針)を取得**。旧要約 3 カテゴリ + 8 件目候補との対応表を作る | 全指摘に重大度と裁定が付き未裁定 0 / **母集団リストと Claude の全対象(15 資産 + 検査器の関数・クラス・定数 + 要件書 heading — §4-(3))機械列挙の exact-set 突合(差集合 0)+ 指摘リスト ⊆ 母集団の検査が機械可読で保存されている** / 裁定リスト(= ステップ 2〜11 の確定範囲)が worklog にある / §2 衝突規則の該当項目は (a)/(b) の PO 裁定記録がある |
| 2 | **要件書 NFR-018 例外表の 2 セル更新**(Claude)— 検証テスト・状態の 2 セルのみ + 変更履歴 1 行 + `docs/README.md` 最終更新日 | 差分が 2 セル + 変更履歴 1 行 + README に限られる / 他セル・他行はバイト単位で無変更 / 版セルが 2.4 のまま / 実測 red 集合が §4-(2) の固定列挙と一致 |
| 3 | **採取器の是正 + 負例**(codex 委任・既知分のみ)— `_table_cells` のインデント対応 + インデント表のフィクスチャ負例 | フィクスチャ単体テストで**負例が是正前 red → 是正後 green** の記録(実行コマンドと出力を worklog へ)/ 実測 red 集合が固定列挙と一致 / 既知分以外の変更なし |
| 4 | **意味論(i) 分類規則の罠の実効化**(F5・codex 委任)— AUTH 5 規則へ非空の `allowed_heading_ids`・禁止パターン等の適用領域を定義し、**空の AUTH 適用条件を検査エラー**にする | 変更が F5 へ帰属 / **導入する検査の負例フィクスチャで是正前 red → 是正後 green を記録** / 失敗集合 = 期待失敗集合(§4-(2)) |
| 5 | **意味論(ii) closed-world 専用構造**(F6・codex 委任)— 全域性宣言・対象 universe・許可集合・既定拒否を専用構造にし、経路・資源・操作との exact-set を検査 | 変更が F6 へ帰属 / 負例 red→green 記録 / 失敗集合 = 期待失敗集合 |
| 6 | **意味論(iii) 結線の閉包**(F7 + F9 採用分・codex 委任)— HTTP 判定可能主張の全件に route ID または**理由付き disposition** を要求する逆向き exact-set 検査 + **cache 17 件の明示的 disposition 記録**(cache 行列の新設はしない — F9 裁定) | 変更が F7・F9 へ帰属 / 負例 red→green 記録 / 失敗集合 = 期待失敗集合 |
| 7 | **意味論(iv) DDL 意味検査**(F14・codex 委任)— policy の command・role・predicate を閉じた値域と意味対応表で検査し、必要 ACL・function owner の基表権限・caller の schema USAGE を exact-set 化 | 変更が F14 へ帰属 / 負例 red→green 記録 / 失敗集合 = 期待失敗集合 |
| 8 | **意味論(v) 主張分割の schema**(F1 採用分・F2・F3・F4・codex 委任)— 1 採取行から**複数の原子的主張**を宣言できる形(分割 ID・主張単位の layer/basis)と検査。client/端末内 location は**新設しない**(F1 裁定 — 別起票) | 変更が F1・F2・F3・F4 へ帰属 / 負例 red→green 記録 / 失敗集合 = 期待失敗集合 |
| 9 | **意味論(vi) probe_executable 判定規則**(F10 採用分・codex 委任)— 経路・DDL・runtime target のない主張の**自動 probe_executable を廃止**し、`contract_only` + 理由の明示を必須化(管理経路 universe の登録はしない — F10 裁定) | 変更が F10 へ帰属 / 負例 red→green 記録 / 失敗集合 = 期待失敗集合 |
| 10 | **母集合・lock・派生 3 資産の追随**(codex 委任)— 裁定リストの資産是正(**F1 採用分・F2・F3・F4 の分割適用 / F8 の帰属訂正〔origin + source_claim_ids。**従属変更として検査器の「legacy route は design origin 必須」強制を「要件由来 origin + 既定拒否主張への結線必須」へ是正**(この強制自体が F8 の誤帰属の焼き込み — 実装中に判明 2026-09-03・計画改訂 2。負例 red→green つき)〕/ F15 の分類修正**(F12・F13 は oracle 資産のためステップ 11 — 計画改訂 1 差分レビュー P1))+ 採取追随(kind/source_id 変更 3 件)+ 例外表セルの source_text 追随 + **変更履歴の新規行(total 1063・table_row +1・分類は §2-4 の既定)** + `input_manifest.commit` = ステップ 2 コミット SHA + **§4-(2) の reseal 実行順** + `tests/` 期待件数の更新 | **`check_authz_catalog.py --skip-oracle` green** / **Claude が python で直接計数した分布と全 ID 集合の照合が一致** / **変更履歴の新規行が既存変更履歴行と同一規則の `out_of_scope` に分類されていることを当該レコード単位で個別照合** / **帰属表(§4-(4))で帰属のない変更 0** / 失敗集合 = 期待失敗集合 |
| 11 | **oracle 6 資産の追随 + seal の 2 段目**(codex 委任)— §4-(6) の手続を**同節の順序どおり**実施(checker fail による追随対象判定〔反復規則〕→ 内容追随 → `oracle_context.oracle_commit`/seal の `oracle_commit` をステップ 10 コミット SHA へ差し替え → **最終形への差分敵対レビュー + 人間確認** → `--reseal-oracle`)。**F12(ddl-elements の ACL 宣言修正)・F13(app_role の DML 剥奪 + 攻撃木・負例追加)の oracle 資産是正は本ステップに一意に属する**(ステップ 10 には置かない) | `uv run pytest tests/` **全 green**(lock 4 本 bytes 不変検査を含む)/ seal の `input_assets` 8 件が現物 blob と一致 / oracle 変更が裁定項目へ帰属(新規判断 0)/ **差分敵対レビューと人間確認の実施記録が worklog にある** |
| 12 | **総合検証と後片付け**(Claude)— /check 一式・**最終成果物 diff(基準 `41884a9`・§4-(4) の対象)と attribution.json の双方向全件再照合**(両差集合 0)・**帰属表から人間の逐行確認用の突合シートを機械生成**・**別起票 4 件**(F1 client location〔ブロッカにしない〕/ F9 cache 行列・F10 管理経路 universe・F11 NFR-019(b) シナリオ行列〔**TSK-250 の開始条件へ紐付け**〕)+ H-85 案②③の起票・worklog 締め | /check green / **最終 diff と帰属表の双方向再照合で両差集合 0** / 突合シートが attribution.json の全エントリを覆う / **起票 URL(6 件)と TSK-250 への紐付け記録**が worklog にある |

## 5. DoD(Notion TSK-312 と同期 — **承認時に Notion 本文の DoD を本節と同一内容へ更新し、worklog に同期実施を記録する**〔計画レビュー 2 周目 P2-12〕)

- [ ] P0 の再列挙が完了し、全指摘に PO 裁定が付いている(一次記録の消失と再列挙の経緯が worklog に記録 — 母集団の exact-set と指摘⊆母集団で独立照合)
- [ ] **採用裁定された指摘の是正が母集合・検査器・派生資産・oracle 資産へ全件反映され、未反映 0**(帰属表と突合シートで確認)。**衝突規則 (a) で別起票した項目は、後続の扱い(本タスク /task-done の前提か・TSK-278 ブロッカ昇格か)の PO 裁定記録がある**
- [ ] TSK-233 申し送りの反映: 例外表 2 セル更新(7.6-3 前段・版 2.4 のまま)+ 母集合追随が同一 PR にある
- [ ] インデント表の採取欠陥が是正され、負例が追加されている(是正前 red の記録つき)。**意味論ステップ(4〜9)で導入した検査にも検査ごとの負例と red→green 記録がある**
- [ ] 派生 3 資産 + 各 lock + oracle 6 資産 + seal + tests の期待件数が追随し `uv run pytest tests/` green(oracle 変更は差分敵対レビュー + 人間確認済み)
- [ ] コア領域として敵対レビュー + 人間の逐行確認を通っている(突合シートで支援)

## 6. テスト計画(NFR-019)

- **単体(ハーネス pytest)**: インデント表の負例フィクスチャを `tests/fixtures/authz_claims/` に追加(**是正前 red → 是正後 green を、実行コマンドと出力つきで worklog に記録**)。**意味論ステップ(4〜9)で導入する検査ごとに負例フィクスチャを追加**し同様に記録(既存 green の維持だけでは新検査の実効を証明できない — 計画レビュー 2 周目 P1-10)。既存統合テスト 3 本(:300・:885・:1279)は期待件数更新のうえ green 維持。lock 4 本の bytes 不変検査(:301-324)を維持
- **一致性・越境・E2E・故障系**: 対象外(本タスクは contracts + scripts + tests + 文書のみ。DB・API・フロントのコード変更なし — 例外表が参照する `frontend/src/lib/courseCoordinateContract.spec.ts` は既存・無変更で Vitest green を /check で確認)
- 検証コマンド: `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/`(**各ステップの委任前後に失敗テスト ID の完全列挙を実測し worklog へ固定** — §4-(2))/ `uv run python scripts/check_authz_catalog.py`(中間ステップは `--skip-oracle`・reseal は §4-(2) の実行順)。**分布・ID 集合の照合は checker 出力に依存せず Claude が python で直接計数**(worklog へ転記)
