---
feature: core-area-paths
type: research
date: 2026-09-02
---

# 調査メモ: コア領域 paths のコード側充填(core-areas.json — H-12 顕在化の是正)

## 問い

`.claude/core-areas.json` の `areas[].paths` へ、現存する実装資産を設計書 6.3 の境界定義表に当てはめて充填する(TSK-281 / 台帳 H-12 / gate-convergence 申し送り C1)。何をどの領域へ登録すべきか、充填を拘束する過去決定・機構制約・手続は何か。

調査体制: spec-checker / legacy-analyst / decision-tracer の 3 並列(設計書 8.5)+ 統合者による原典確認(PR #33 の実マージ内容・`tests/test_core_guard.py` のオラクル・`docs/features/pg-authz-verification/plan.md` 3 節)。

## 結論(要約)

1. 充填の主対象は**テナント分離**(`contracts/authz/` 15 本・検査器・`backend/tests/db/` ほか)と**状況計算**(座標変換系 frontend 実装 4 + spec 3 + 契約 JSON 1)。**同期プロトコル・記録権に登録できる実装コードは現存しない**(文書 2 本は登録済み)。**データ移行の現存候補は未使用ヘルパー `frontend/src/lib/format.ts` の 1 件のみ**(fail-closed 判定)。
2. paths の追加は **6.3-⑤(敵対レビュー + 人間承認)+ guard_paths PR 手続**(逐行確認チェック + 実施記録行 + base SHA 3 点一致・`--match-head-commit`)の対象。承認手続は PO 判断済み(起草 = 徳光 / 逐行確認 = 山田 / PO 承認 = 徳光 — [worklog 決定節](../../worklog/2026-09-01-core-area-paths.md))。
3. **機構制約**: `tests/test_core_guard.py` が paths・guard_paths を完全一致で固定する 3 種のオラクルを持ち、**充填と同一 PR で期待値の追随が必須**(同ファイル自身が guard_paths)。照合は `fnmatchcase`(glob の `*` は `/` を跨いで一致)。
4. **条件付き除外(後段集計)は不発効** — 含む側が正(ただし該当実装は現存ゼロ)。paths の**縮小は今回やってはならない**(ADR-003)。
5. 責務調整 2 件が未決: **pg-authz 計画が登録を「第 2 群(計画改訂 2)の射程」と宣言済み** → TSK-281 への移管の明示が要る / **TSK-228・TSK-254 との統合**(Notion 裁定待ち)。

## 詳細と典拠

### 1. 正本の規定(現行文言の所在)

- **境界定義表(5 領域の含む/含めない)**: `docs/development/dev-harness-design-2026-08-07.md:358-362`(v1.6 で新設・approved)。内容はここに複製しない(7.1-1)— 領域別の当てはめは 2 節の判定表に反映済み。
- **fail-closed**: 「判定に迷うコードは含む側に倒す」 — 同 `:364`
- **paths への落とし込み規則 5 点**: ① 不変条件・強制点・契約(ベクタ・スキーマ・テスト)を**変え得る**ファイルを含める ② 混在ファイルはファイル全体 ③ 領域間の重複帰属可 ④ 過剰包含は PR 単位の例外で外さずモジュール分割してから狭める ⑤ **追加・削除・縮小は敵対レビュー + 人間承認** — 同 `:365`
- **実施記録行の様式**(`- 実施記録: 対象= 範囲= 方法=`・人間記入・機械検証なし): 同 `:352`
- **マージ手続**(base SHA 3 点一致・`gh pr merge --match-head-commit`・該当判定は **base 側 core-areas.json が正**): `docs/development/github-setup.md:39-41`
- **機構の照合仕様**: `areas[].paths` = `fnmatch.fnmatchcase` の glob(`/` を跨ぐ)/ `guard_paths` = 完全一致 — `scripts/core_guard.py:219-224`

### 2. 領域別の充填候補(帰属判定)

確度: **確実** = 6.3 の含む欄に直接該当 / **fail-closed** = 6.3 に明示がなく `:364` で含む側に倒した(→ 計画レビュー・敵対レビューでの裁定対象)。

#### テナント分離(tenant-isolation)

| パス | 確度 | 根拠 |
| --- | --- | --- |
| `contracts/authz/*`(15 本 — lock・oracle-seal 含む) | 確実 | 6.3 `:361` + 規則①。FR-033/034/035/037/041/042 の認可主張母集合・認可行列・経路レジストリ。`oracle-seal.lock.json:44-74` が他資産の digest を封印 = 強制点。pg-authz 計画自身が「テナント境界の認可判定そのもの」と自認(`docs/features/pg-authz-verification/plan.md:147` 相当・4 節) |
| `scripts/check_authz_catalog.py` | 確実 | 規則①(強制点)。要件書 + authz 契約群の exact-set 突合(既定資産 = 要件書 1 + authz 15 パス — `:17-34`) |
| `tests/test_check_authz_catalog.py`・`tests/fixtures/authz_claims/*` | 確実 | 規則①(テスト・フィクスチャ)。要件書 blob digest と母集合件数を凍結 |
| `backend/tests/db/**`(6 本) | fail-closed | pg-authz 計画がコア領域資産として列挙(3 節)。現存 2 テストは DB 環境値の突合のみで**越境テスト・RLS テストは未実装** — 将来その枠になるため含む側 |
| `backend/pyproject.toml`・`backend/uv.lock` | fail-closed | `requires_db` マーカー・testpaths の定義点(`pyproject.toml:48-52`)+ 計画が「uv.lock も変更資産」(P0-19)。混在(規則②) |
| `docker-compose.yml` | fail-closed | `backend/tests/db/environment-expectations.json:19-144` の全期待値の provenance が同ファイルの逐語行。6.3 に環境ファイルの明示なし |
| `docs/features/pg-authz-verification/probe/*.sql`(13 本) | **不明** | RLS・ACL の実機検証 DDL だが、`docs/features/` は正本ではない一時作業域(設計書 7.2 `:395`)で 6.3 に規定なし。裁定対象 |

#### 状況計算(game-state)

| パス | 確度 | 根拠 |
| --- | --- | --- |
| `frontend/src/lib/courseInputView.ts` | 確実 | 6.3 `:359` 座標変換。NFR-018(c) 例外表が `COURSE_COORDINATE_SIZE` を名指し(要件書 `:906`)。※将来 TSK-275 で生成物へ移設予定(ADR-003 `:380`) |
| `frontend/src/lib/displayGeometry.ts` | 確実 | 契約 JSON の読み込み・座標系定数の中継・幾何計算(`:5-29`) |
| `frontend/src/lib/spatialInput.ts` | 確実 | 座標域 0.1〜262.9 のハードコードとクランプ(`:13-24`)。UI との混在 → 規則②で全体 |
| `frontend/src/components/zone/StrikeZone.vue` | 確実 | 画面座標→保存座標の変換ロジックがコンポーネント側にも存在(`:43-53`)— 規則② |
| `frontend/src/lib/courseCoordinateContract.spec.ts` | 確実 | 規則①(契約テスト)。course-coordinate-contract からの明示的引き渡し(下記 3 節) |
| `frontend/src/lib/displayGeometry.spec.ts` | 確実 | 規則①。契約 version・263・枠値を固定(`:11-18`) |
| `contracts/display_geometry_263_v1.json` | 確実 | ②参照データ契約(ADR-003 `:250`)。例外表が契約値として名指し(同 `:285`) |
| `frontend/src/components/zone/StrikeZone.spec.ts` | fail-closed | 座標変換コンポーネントのテスト(規則①) |
| `frontend/vite.config.ts`・`frontend/vitest.config.ts` | fail-closed | `@contracts` エイリアスの唯一の定義 = 契約解決点(`vite.config.ts:7-19`)。6.3 にビルド設定の明示なし |
| `frontend/.prettierignore` | fail-closed | 逐語移植 4 本の保持指定(`:8-12`)。外すと逐語性(NFR-018(c) 例外の前提)が壊れる |

#### 記録権 / 同期プロトコル

**充填できる実装コードは現存しない**(実測: `backend/src/pitchlog/` は `main.py`〔`/health` のみ〕と `__init__.py`)。文書 2 本は登録済み(`.claude/core-areas.json:25,27`)。

#### データ移行(data-migration — 現在 paths 空)

- **現存する候補は `frontend/src/lib/format.ts` のみ**(fail-closed): 自らコメントで「88列契約の試合日時形式」と宣言する `isoToSlashDate` を実装(`:1-4`)。ただし**リポ内に呼び出し元 0 件の未使用・逐語移植ヘルパー**。88 列本体の日付書式の逐語規定は要件書になく、正は `docs/legacy/research/data-layer.md:51,152`(付録D-1 `:1210` が意味の正を委任)。混在ファイルのため規則②なら全体。
- **変換層・取り込み・隔離・名寄せ・責任投手導出・88 列スキーマ・サイドカー契約・ゴールデンフィクスチャは 1 ファイルも現存しない**(Glob 実測。`contracts/README.md:14` も「将来収載」と明記)。
- `data-layer.md` は `docs/legacy/`(変更禁止 — 設計書 7.1-2 `:381`・settings.json の deny)にあり、規則①「変え得るファイル」に該当しない構図。**移行領域の契約本体が変更不能アーカイブにあるという他 4 領域との非対称に規定はない(不明)**。
- 負のオラクル: `tests/test_core_guard.py:329-335` が **data-migration に文書 2 本を登録しないこと**を assert(統合者確認済み)。コードパスの追加は抵触しない。
- `contracts/authz/requirement-claims.json` は FR-038/FR-031 条文の逐語 `source_text` を内包(FR-038 55 箇所・FR-031 25 箇所)するが、性質は authz 検証の入力マニフェストであり移行契約ではない。`route-registry.json:62-97` の `ROUTE:FR-031` はテナント分離主題(共有グループ経由 404)。

#### 非コア判定の代表(根拠つき)

`backend/src/pitchlog/main.py`(`/health` のみ — 6.3 `:358` 右欄の単純 CRUD 相当)/ `backend/tests/{test_health,test_package,conftest}.py` / `frontend/src/App.vue`・`main.ts` / `StrikeZoneCompareHost.vue`(開発時目視比較専用と自己申告 `:142`・変換なし)/ frontend の各種設定(`package.json`・`tsconfig*` 等。ただし `vite.config.ts` は上記の別扱い)/ `scripts/`・`tests/` のハーネス系(検査経路は `guard_paths` 側で保護済み)。

### 3. 拘束決定(paths 充填に効くもの)

| 決定 | 日付 | 内容 | 典拠 |
| --- | --- | --- | --- |
| 設計書 v1.6 approved | 2026-08-17 | 境界定義表・fail-closed・落とし込み規則 5 点の確定。H-12 残余を「Phase 4 完了条件への組み込み・承認者の指定」へ絞り込み | `dev-harness-design-2026-08-07.md:41-42,354-365` |
| ADR-003 approved | 2026-08-18 | **後段集計の除外は不発効**(当面コア領域に含む)/ **paths は本 ADR で変更しない・発効判定と縮小は別手続**(= 今回縮小はしない)/ 充填は 6.3-⑤ 要 | `docs/adr/ADR-003-domain-calc-method.md:352,354,382,390` |
| sync-protocol-canonical(初回充填の前例) | 2026-08-28 | 4 領域へ**文書 2 本**を登録・guard_paths へ検査資産を完全列挙。⑤の充足は「当該タスクのゲート」で宣言。**コード側は Phase 4 へ明示留保** | `docs/features/sync-protocol-canonical/plan.md:175,186,195,206`・`docs/worklog/2026-08-28-sync-protocol-canonical.md:174-187` |
| pg-authz-verification 計画 | 2026-08-31 | `tenant-isolation.paths`・`guard_paths` への登録は**「第 2 群(計画改訂 2)の射程」として意図的に未実施**(「登録対象のパス集合が改訂 2 で確定するまで登録しない」)。→ PR #33 の core-guard 非発火は規則違反ではなく計画上の未実施(統合者が 3 節を原典確認)。※計画資産表の `backend/src/pitchlog/db/authz/**` は**実マージに含まれていない**(git diff 1ab778f 実測 — 現存しない) | `docs/features/pg-authz-verification/plan.md` 3 節 |
| gate-convergence-rules 裁定 | 2026-09-01 | areas 側のコード拡張は **C1 = 緊急・別タスク**(同タスクは guard_paths のみ)。H-12 へ PR #33 顕在化を補記・「コード側 paths の充填は別タスクで起票する」 | `docs/features/gate-convergence-rules/plan.md:47,57`・`docs/development/harness-evaluation.md:452` |
| course-coordinate-contract 引き渡し | 2026-09-01 | 候補 3 件(`courseCoordinateContract.spec.ts`・`courseInputView.ts`・`display_geometry_263_v1.json` → game-state)を worklog 記録+TSK-228 へ引き渡し済み(コミット 154bb84) | `docs/worklog/2026-09-01-course-coordinate-contract.md:311-317,347` |
| 設計書 v1.12 / github-setup v1.2 | 2026-09-01 | 実施記録行様式(6.3)・base SHA 3 点一致 + head 拘束マージ・記録未記入ならマージしない | `dev-harness-design-2026-08-07.md:352`・`github-setup.md:39-41` |
| 承認手続の PO 判断 | 2026-09-01 | 起草・PR 作成 = 徳光 / 逐行確認 = 山田 / PO 承認 = 徳光。恒久規則「paths 変更 PR の逐行確認は PR 作成者以外」→ 計画書の承認手続へ転記(H-12 残余「承認者の指定」を充足) | [worklog 決定節](../../worklog/2026-09-01-core-area-paths.md) |

補足: 「Phase 4 完了条件を待たずに充填してよい」と明文で述べた PO 裁定は**存在しない(不明)** — 実質根拠は C1 緊急裁定と H-12 補記(上表)。`core-areas.json:2` の description「Phase 4 のコード骨格確定時に埋める」との整合は要裁定(申し送り 4)。

### 4. 機構影響(実装ステップに直結する事実 — 統合者が原典確認済み)

- **`tests/test_core_guard.py` の 3 オラクル**(同ファイルは guard_paths — `.claude/core-areas.json:21`):
  1. `:311-317` — 4 領域(`CORE_AREA_IDS`)の `paths` を**文書 2 本と完全一致**で assert → コードパス 1 本の追加で red
  2. `:329-335` — data-migration に文書 2 本が**入っていない**ことを assert
  3. `:337-341` — `guard_paths` を**期待集合と完全一致**で assert → guard_paths 追加でも red
  完全一致は「意図しない追加も捕まえる」ための意図的設計(`docs/worklog/2026-08-28-sync-protocol-canonical.md:187`)。**充填と同一 PR で期待値を追随させる**(前例の作法は「登録の追随のみ」— `docs/features/gate-convergence-rules/plan.md:53`)。
- **glob 意味論**: `fnmatchcase` のため `contracts/authz/*` は入れ子まで一致(`scripts/core_guard.py:219-224`)。規則②(混在ファイル全体)・将来の移設(TSK-275)を見込んだ粒度設計が必要。
- **本 PR 自身は新 paths では捕捉されない**(該当判定は base 側が正 — `github-setup.md:40`)。ただし `core-areas.json`・`test_core_guard.py` が guard_paths 該当のため**逐行確認チェック + 実施記録行は必須**。
- `scripts/core_guard.py:18` の `NO_CORE_PATHS_MESSAGE`(「Phase 4 で定義予定」)は paths 非空の現在は出力されない(`:268-269`)。

### 5. 隣接事実(本タスクの入力・または申し送り)

- **guard_paths の非対称**: authz 検査器 3 資産(`scripts/check_authz_catalog.py`・`tests/test_check_authz_catalog.py`・`tests/fixtures/authz_claims/**`)が guard_paths 未登録。同種の `check_design_propagation.py`・`check_doc_coverage.py` とテスト・フィクスチャは登録済み(`.claude/core-areas.json:11-20`)。
- `contracts/README.md:7` の「契約は 2 種類」宣言に `contracts/authz/**`(`asset_kind: authz_*` の独自系)が未記載(索引の未追随)。
- 要件書 NFR-018(c) 例外表(`:906`)が「検証テスト未整備」のまま — 実体 `courseCoordinateContract.spec.ts` は既在。既知の残余で **TSK-270 へ合流済み**(`docs/features/course-coordinate-contract/plan.md:156-183`)。本タスクで spec を paths に含めることは規則①に適合。
- 台帳 H-12 の事象文 `:447`(「5 領域すべて空」)は検出時点(2026-08-12)の記述。現況は 4 領域に文書 2 本・空は data-migration のみ(`:452` の補記が現況側)。
- PR #33 マージ済み分への**遡及逐行確認の義務を定めた決定は存在しない(不明)**。

## 未解決・申し送り(/plan での裁定事項)

1. **fail-closed 候補の採否**(2 節の fail-closed 行: `backend/tests/db/**`・`pyproject.toml`・`uv.lock`・`docker-compose.yml`・`vite/vitest.config`・`.prettierignore`・`StrikeZone.spec.ts`・`format.ts`)— 6.3 に設定・環境ファイルの明示規定がなく、当てはめの確定は ⑤ のゲート(敵対レビュー + 人間承認)で行う
2. **probe SQL(`docs/features/` 一時作業域)の扱い** — 規定なし(不明)
3. **オラクル更新方針** — 完全一致を維持し期待値を新 paths に追随(前例あり)か、構造を変えるか
4. **`core-areas.json:2` description の現行化**(「Phase 4 のコード骨格確定時に埋める」文言)と、台帳 H-12 事象文の現況整合
5. **guard_paths への authz 検査器 3 資産の追加**を本タスクのスコープに含めるか
6. **責務整理 2 件**: pg-authz「第 2 群(計画改訂 2)」の登録責務を TSK-281 へ移管する旨の明示(山田さんと調整・pg-authz 計画は履歴のため追記可否も判断)/ TSK-228・TSK-254 との統合(Notion コメントで PO 裁定依頼済み)
7. **H-12 のクローズ設計**: 残余のうち「承認者の指定」は PO 判断で決着(3 節)。「**Phase 4 完了条件への組み込み**」は 13 章の規範変更 = 確定ゲートが要る(7.6-3 後段)ため、本タスクで扱うか別裁定へ送るか
8. **glob 粒度の設計**: ファイル名指定 vs ディレクトリ glob(`contracts/authz/*` は入れ子まで一致)・TSK-275 移設の吸収
9. **遡及逐行確認の要否**(PR #33 済み分 — 未規定・PO 判断事項)
10. **data-migration の初コード登録**: `format.ts`(未使用ヘルパー)を入れるか、現存コードなしとして空を維持し将来の移行実装 PR で登録するか
