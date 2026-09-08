---
feature: data-model-canonical
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 初回承認 2026-08-31 → 2026-09-04 再承認(A の申し送り 24 項目の反映・契約 5 の文言変更・ステップ 26 → 28)。**2026-09-08 に TSK-335 の射程改訂のため「未」へ戻した**(改訂中に旧承認日の「済」を残さない — TSK-335 計画レビュー 3 周目 `#8`)。改訂完了後に新しい日付・承認者で「済」へ
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3c593b75e6878152b3edd6cf4f26b30b
branch: feature/data-model-canonical
created: 2026-08-30
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: データモデル設計の正本化(**TSK-342 が新設した正本への加筆** + 7.3 の確定ゲート)

## 1. 背景・目的

**下調べ**: [research.md](research.md)(2026-08-30 — 調査サブエージェント 4 本 + 原典の直接確認)。
本計画の前提事実・件数・裁定待ちはすべて同メモが正で、**本書へ内容を複製しない**(設計書 7.1-1)。

前タスク **「製品データモデル設計の起草」(TSK-248・PR #23 マージ済み)** の成果物
`docs/features/product-data-model-design/design.md`(**1,866 行**)は **候補案**であり、
`docs/features/` 配下の一時ディレクトリにある(設計書 7.6-4)。
**`docs/design/data-model.md` の新設と最初の `approved` 化は [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)**(裁定 `R-1`・2026-09-08)。
**本タスクは TSK-342 が `approved` にした正本へ加筆し、加筆差分について設計書 7.3 の確定ゲートを通す。**

- Notion タスク: [TSK-250 データモデル設計の正本化](https://app.notion.com/p/3c593b75e6878152b3edd6cf4f26b30b)
- 前タスク: [TSK-248](https://app.notion.com/p/3c393b75e687810d8187ea8cce6b1bef) / PR #23
- 直前に正本化された姉妹文書: [同期プロトコル設計](../../design/sync-protocol.md)(approved v0.1・2026-08-30)

**候補案の「形」をそのまま採ってはならない。** 前タスクは敵対レビュー 4 周・指摘 37 件を全件反映した
うえで、**3 領域が収束しなかった**と宣言して閉じた(候補案 12-7 節・人間の裁定 2026-08-22)。

### 射程の決定(**人間の裁定 2026-08-31**)

本計画は**計画レビューで 2 周続けて否決**された。**2 周とも同じ構造的理由** — 「1 タスクに独立した確定単位が
複数入っており、後段が前段の成果を壊す」— を指摘され、**2 周目の指摘の多くは 1 周目の是正が生んだ新しい欠陥**
だった(前タスクが 3 周続けて打ち切った状態と同型)。**計画へ入れた停止条件が計画段階で発火した**ものとして、
**独立した確定単位を先行タスクへ切り出す**。

| 先行タスク | 射程 | 本タスクへ渡すもの(**機械可読資産**) |
| --- | --- | --- |
| **A.** [TSK-269](https://app.notion.com/p/3cc93b75e6878194b72bcc12219d6cdb) 文書検査機構の多文書対応(**マージ済 2026-09-04**) | 検査エンジンの**文書プロファイル**化 / **不変条件 DSL**(13 種 + 契約 5 種別名。**未対応種別は fail-closed**)/ レジストリと `--registry` / 4 検査 + 集合一致 + `unique-owner` の**機構**(評価器・構造抽出器・集合一致・資産ローダー・pins)/ 参照の分類(`normative` / `evidence` / `informative`)/ CI 配線の一般化(**引数なし列挙**) | **エンジンと DSL とスキーマ版**、および**合成サンプル一式**。本タスクは**データモデル用プロファイルとデータを作る側**に立つ |
| **B.** [TSK-270](https://app.notion.com/p/3cc93b75e687816a9230e1c1b0ded0e7) PostgreSQL 認可構成の実機検証(**第 1 群のみマージ済 — 続きは [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)**) | DB テスト基盤 / **AUTH カタログの固定** / 認可 DDL 適用器 / **正例・拒否例・カタログ検査・ACL 検査・同一トランザクションの証明・ロール到達性・`search_path`・mutation test・4 ロール × 関数群の実行行列** | **① AUTH カタログ ② DDL 要素表 ③ 不採用構成表**(いずれも機械可読・**スキーマ版・安定 ID・共通正規化 ID・元 commit・blob digest 付き**)。本タスクは**写像する側**に立ち、**再裁定しない** |
| **C.** [TSK-271](https://app.notion.com/p/3cc93b75e68781dba1f3ec87cf24711e) 88 列と旧資料矛盾の裁定 | `DM-LG-*` 16 件の原典照合と `DM-LX-*` 6 件の裁定 / 88 列すべての**意味欄 4 項目**(**実際の中身 / 旧コードの参照箇所 / 新スキーマの行き先 / 変換規則** — **要件書 付録 D-1 が「スキーマ定義ファイルに意味欄を含める」と要求する 4 項目そのもの**)の確定。**`逆変換可能性` は要件のどの条項にも紐づかないため、任意の判断材料へ降格する**(裁定 `R-4`・2026-09-08) | **`DM-LG-01`〜`16` / `DM-LX-01`〜`06` の判定 22 件と調査メモ**(`docs/features/legacy-column-mapping/research.md`。**`research_blob_sha` = `59cb50fca6fdbcc045c5604f935c415e6d16b90a` で固定**)+ **センチネル全 88 列表**と**座標の確定式**。**C は 88 列写像 JSON を作らない**(2026-09-07 の PO 裁定で射程が「判定 22 件 + 調査メモ」へ縮小)。→ **写像の値は本タスクが `#### 写像ステップの許可入力集合` の `IN-01`〜`IN-08` だけを根拠に決める**(裁定 `R-9`・2026-09-08) |

**開始条件は 5 節が正**(裁定 `R-3`・2026-09-08 で**タスク単位から成果単位へ改めた**)。
**マージ済みであることは必要条件だが十分ではない** — B はマージ済みでも成果が候補 probe 資産であり、
C はマージ済みでも 88 列写像 JSON を作らない。**要旨**: TSK-342 の完了 / TSK-317 の完了 /
TSK-334 の完了 / 本改訂への人間の再承認(2026-08-31 の「A・B・C がマージ済み」は**旧条件**)。
**あわせて Notion の TSK-250 の DoD を「先行タスクの確定成果を取り込む」形へ書き換える。**

**B の信頼境界について**(3 周目 P0-3 を採用): `AUTH-*` の exact-set 一致は「**B を正確に転記した**」ことしか
証明しない。**B が要件を 1 件落としてカタログ・DDL・テストを同じ欠落状態で作れば、本タスクは検出できない。**
したがって **B 側の完了条件に、AUTH カタログとは独立した要件主張母集合**を置き、
**`要件安定 ID → AUTH 主張 → 関数の全シグネチャ・ロール・期待結果 → テスト ID`** を exact-set で結ぶ。
**B 自体をコア領域タスクとして敵対レビュー + 人間の逐行確認済みにする**(TSK-270 の DoD に反映済み)。
本タスクの開始条件は、**その受入証跡と merge commit の確認**まで含む。

### 承認時に記録すること(3 周目 P1-6 を採用)

計画承認と同時に、**開始条件に立つ全タスクのタスク ID / 計画書パス / PR / merge commit /
受け渡し資産のパスと digest** を worklog へ記録する。**対象は
[TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)(スキーマ本体・ORM)/
[TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)(認可構成の確定成果)/
[TSK-334](https://app.notion.com/p/3d493b75e6878176bf75dcbdd70d35b9)(値の採否)/ A(TSK-269)/
C(TSK-271)**であり(裁定 `R-3` — **「A・B・C」固定ではない**)、
**`IN-01`〜`IN-08` の実値(`research_blob_sha`・成果 ID・digest)を含める**。
および **TSK-250 の DoD 更新結果**を記録する。**ステップ 1 の前提はこの記録である。**

### 先行タスク A のマージ実績(2026-09-04)

| 項目 | 実値 |
| --- | --- |
| PR / merge commit | **PR #42** / **`fdda374`**(`feature/doc-check-multi-doc` → `develop`) |
| 詳細設計 | [`docs/features/doc-check-multi-doc/design.md`](../doc-check-multi-doc/design.md)(**申し送りは 11 節・24 項目**。射程の縮小は PO 裁定 (b)・同 0 節) |
| 共通ローダー / 評価器 / ランナー | `scripts/doc_check_profile.py` / `scripts/doc_check_invariants.py` / `scripts/check_doc_profiles.py` |
| レジストリ・プロファイル・宣言資産 | `scripts/design_relations/profiles/{registry,sync-protocol}.json` / `scripts/design_relations/invariants/sync-protocol.json` |
| スキーマ(`schema_version` 1) | `scripts/design_relations/schemas/{profile,registry,invariant,assets,runner-envelope}.schema.json` |
| 合成サンプル | `tests/fixtures/profile-sample/`(**`profiles/data-model-like.json` が全 22 ID を有効化したデータモデル型の雛形** — 本タスクのプロファイルはこれを実文書向けに写す) |

**本改訂は A の申し送り 24 項目だけを反映したものであり、計画全体の再レビューではない**(2026-09-04)。
**射程が変わった**(契約 5 の文言・**総ステップ数 26 → 28**)ため `承認` をいったん `未` へ戻し、
**2026-09-04 に人間の再承認を得た**(山田正輝 — A の design 11 節ヘッダ「**TSK-250 は着手前に再レビューが必要**」・本書 4 節 確定ゲート手順 8 が要求する承認)。

### 先行タスク A との受け渡し契約(**本タスクが依存する最小集合**)

**A がこれらを提供しない場合、本計画は「開始条件不成立」として停止し、計画の再レビューへ戻す**
(3 周目 P0-1 を採用)。**契約 1〜4 は A のマージで充足済み**(下表)。**契約 5 は PO 裁定 (b) により文言を改めた**(申し送り 24)。

1. **CLI 名の固定** — `--document` / `--profile` / `--manifest` / `--defects-file` / `--checks` / `--defects`(+ **`--registry`**)。
   **充足**(`check_design_propagation.py` / `check_doc_coverage.py` / `check_doc_profiles.py`)
2. **プロファイルスキーマの版**(宣言表節・帰属表節・台帳節・帰属区分の語彙・欠陥 ID の名前空間・不変条件の種別を持つ)。
   **充足**(`schemas/profile.schema.json` ほか 5 本・`schema_version: 1`)
3. **fail-closed 条件**。**充足**(申し送り 6 — 未対応の不変条件種別 / 未知の ID / プロファイル欠落 に加え、
   **解決できない節 / 脱落トークン / レジストリ不一致 / 完全分割違反 / 必須検査の資産・抽出器・集合宣言の欠落 / 正規化衝突 / 重複 JSON キー / 抽出器が 1 件も構造を得られない / pins 不一致・必須 pin の欠落** も終了コード 2)
4. **汎用コンフォーマンスランナーとサンプルプロファイル** — A は**実プロファイルに依存しない**形で契約テストを持つ。
   **充足**(`scripts/check_doc_profiles.py` + `tests/fixtures/profile-sample/`)。**実プロファイルを使う契約テストは本タスクのステップ 3** で足す
5. **(改訂 — PO 裁定 (b)・2026-09-04)** **A は 4 検査 + 集合一致 + `unique-owner` の機構(評価器・構造抽出器・集合一致・資産ローダー・pins)を提供し、
   合成サンプルで全 22 ID が動くことを保証する。データモデル正本に対する実入力契約(資産形状・必須抽出器・集合宣言・pin 対象と実値)は
   本タスクが自分の計画で固定し、機械保証の主張は本タスク側の受け入れ条件(5 節)に置く。**
   **「人間確認へ回して契約を満たす」逃げ道の禁止は維持する** — 機械保証の**実装場所**が A から「本タスクのプロファイル宣言 + A の機構」へ移るだけであり、
   次の 4 つは**本タスクの DoD として機械で保証する**(対応する check ID を併記する):
   - **`FORB` の構造判定**(別名・暗黙関係を含む。語句一致では不可)— `forbidden-structure`
   - **データモデル直接要件の「対象外」禁止** — `attribution-direct`(+ `collection-consistency`)
   - **ベースラインの不変部分と可変状態の分離**(digest 拘束)— `baseline-digest`(+ `unique-owner`)
   - **`WAIT` / `AUTH` / `FORB` の交差検査** — `cross-consistency`

**「D1〜D9 の定義と参照の区別」は本タスク側の不変条件設定で表現する**(`forbidden-element` で
定義文の型を禁止する)。**ステップ 7 は「DSL の設定」に限定**し、**エンジンの変更が必要と判明したら停止する**
(`scripts/check_*.py`・`scripts/doc_check_*.py` は本タスクの変更対象外 — 3 節)。
**「A へ戻す」経路**(申し送り 9): A はマージ済みのため差し戻し先が無い。**Notion の TSK-269 へコメントを残し、
新規タスクを起票**して、そのマージを本タスクの再開条件に加える(TSK-269 を再開しない)。

### A の申し送り 24 項目の反映先(2026-09-04)

| # | 申し送り | 本書の反映先 |
| --- | --- | --- |
| 1 | CI は引数なし列挙 | 4 節 検証コマンド集合 5・6 / **ステップ 16**(「明示引数」を撤回) |
| 2 | 設計書 10.1・`test_ci_wiring.py` は A が触らない | 3 節 / **ステップ 16** |
| 3 | `guard_paths` 登録(B 集合) | **ステップ 1(最初の独立コミット・新設)** |
| 4 | 台帳 H-78・H-79 | 3 節 / **ステップ 18** |
| 5 | プロファイル・レジストリの実パス | 3 節(`profiles/data-model.json`・`profiles/registry.json` の entry 追加) |
| 6 | fail-closed の条件 | 1 節 契約 3 / **ステップ 3** |
| 7 | `verify_handoff_digest.py` はランナーに載せない | 3 節(**専用スクリプトとして新設**)/ 4 節 コマンド 9 / **ステップ 5** |
| 8 | `assets` の宣言形式 | 3 節 / **ステップ 3・5・6** |
| 9 | 「A へ戻す」経路 | 1 節(上記)/ **ステップ 7** |
| 10 | 欠陥台帳・宣言資産の項目 | 3 節(immutable / mutable の確定)/ **ステップ 4** |
| 11 | 完全分割と `must_require` | 3 節(registry entry)/ **ステップ 3** |
| 12 | ランナー契約と全検査 0 の時期 | **ステップ 2**(終了 1 の診断)/ **ステップ 15**(終了 0) |
| 13 | `absent-section` | **ステップ 4**(`DM-MT-01`: 候補案 13 節の不在) |
| 14 | 作成順と staging の木 | **ステップ 2(新設)** / **ステップ 16**(本番移設 + 登録を同一コミット) |
| 15 | `auth_ddl_map` / `product_ddl_map` / `direct_requirements` / `expected_ids` | 3 節(**独立資産 4 本を新設**)/ **ステップ 4・5・13** |
| 16 | 計画書の改訂点 | 本表のとおり全件反映(`auth_target` は本書に記述が無く、削除対象なし) |
| 17 | 契約の種別名 | **ステップ 3**(`invariant_kinds` に 5 種別名を書ける) |
| 18 | 変異テストの方針 | 6 節 テスト計画 |
| 19 | `structure_extractors` | **ステップ 3**(遷移表・列役割表・暗黙関係) |
| 20 | `collection_sets` | **ステップ 6**(claims の `relation` 行 = manifest) |
| 21 | レジストリ entry の `must_require` + `pins` | 3 節 / **ステップ 3** / 4 節「pins の更新規律」 |
| 22 | claims の分類 `direct_requirement` | **採る** — 3 節(4 分類)/ **ステップ 5** |
| 23 | `product_ddl_map` の二段階射影 | 4 節 台帳間の交差検査 / **ステップ 13** |
| 24 | 契約 5 の文言変更 | 1 節 契約 5(上記)/ 5 節 DoD |

## 2. スコープ

### やること

**※ TSK-335 の裁定 `R-1`〜`R-9`(2026-09-08)で射程を切り出した。**
**送り先は下の `### 切り出しの線引き` が正。**

1. **`docs/design/data-model.md` への加筆**(**新設は TSK-342** — `R-1`)と、**その加筆差分に対する
   設計書 7.3 の確定ゲート通過**(`/finalize-doc`)
2. **同期プロトコル正本の決定のうち、`D4`・復旧世代の永続化写像を本文へ写像**する(`R-6`)。
   **矛盾 15 件・欠落 20 件・書き換え 5 件の残りは TSK-342**(`R-1` — スキーマ本体の物理表現)
3. **先行タスク B の成果(認可構成と `AUTH-*` カタログ)を本文へ写像**する
4. **88 列写像の確定** — **許可入力集合(`IN-01`〜`IN-08`)だけを根拠に値を決める**(`R-9`。
   **C は写像 JSON を作らない**)
5. **要件帰属表**と**意味照合台帳**(**典拠の識別子参照化そのものは TSK-342** — `R-1`)
6. **`.claude/core-areas.json`** — **A の新資産 33 件の `guard_paths` 登録(最初の独立コミット)**、
   `data-migration` の `paths` 充填(**`contracts/legacy-columns/` 資産の登録は TSK-339** — `R-8`)、
   本タスクの新資産追加、既存 4 領域へ本正本を追加
7. **データモデル用プロファイル一式の作成**(A の機構に対する実入力契約 — 裁定 (b)):
   プロファイル・宣言資産・`structure_extractors`・`collection_sets`・独立資産 4 本・**レジストリ entry の `must_require` = 全 22 と `pins`**
8. **staging の木の本番移設とレジストリ登録(= CI 配線)** — `tests/test_ci_wiring.py` の docs-lint 系
   検査と設計書 10.1 の **`docs-lint` 行**の現行化を含む(**`R-8`。ORM 条項は 5.1 とともに TSK-342**)
9. **台帳の更新** — H-12 の事象欄・H-78・H-79 への実績追記(**`H-*` の新規採番はしない**)

### やらないこと

| 対象外 | 受け取り先 | 理由 |
| --- | --- | --- |
| 検査エンジン・DSL・参照分類の実装 | **先行タスク A**(マージ済) | 人間の裁定 2026-08-31。**本タスクは `scripts/check_*.py` / `scripts/doc_check_*.py` を変更しない** |
| **認可 DDL の実装と実機検証**(基盤・カタログ固定・テスト) | **先行タスク B** | 同上。**独立した確定単位**であり、本タスクは成果の写像に限る |
| **88 列の原典照合と旧資料矛盾の裁定** | **先行タスク C** | 同上。**本タスクのステップ内で裁定すると、後段が前段の成果を壊す**(2 周目 P1-11) |
| **`.claude/scripts/codex_run.py` と `tests/test_codex_run.py` の `guard_paths` 登録**(A の C 集合) | — | **裁定 2026-09-04 が委ねたのは B 集合のみ**。ラッパーは元から `guard_paths` 外(hooks 側の統制対象)であり、本タスクで統制範囲を広げない |
| **退避イベントの現行世代への取り込み**(挿入位置指定・採番) | **TSK-267** | 同期正本 U-2 が「取り込みの規則は一切決めない。本書から類推してはならない」と宣言(`FORB-01`)。**候補案 8-2-B の管理関数クラス (c) がこれを含んでいる**ため、本文から分離する(`DM-SY-C16`) |
| U-1 の 3 経路 / 復元前受理の復帰経路 / RR-3 の回収機構 | TSK-267・NFR-009 の復旧手順 | `FORB-02`・`FORB-03`・`FORB-04` |
| **HTTP 404 の検証**(NFR-019(b) の API 合否) | **Phase 4 の API テスト** | 生 SQL では DB レベルの「0 行 / 権限拒否」までしか判定できない |
| NFR-019(b) の行列全体の網羅 | Phase 4 の実装タスク | — |
| 移行のファンアウトの実測・カットオーバー日・`game_lineup_snapshot` の帰属・サイドカーの列定義 | 移行仕様タスク | 旧 DB の実データが要る |
| ドメイン計算の宣言モデル・付録A 固定ベクタ・付録E 全表 | TSK-235/236/237 | ADR-003 が確定済み |
| 索引の具体形・事前集計の採否 | 実装期の性能実測 | — |
| **要件書の改訂** | 要件改訂タスク | 管理者操作ログの Must/Should 矛盾は**計画承認前の裁定**へ(5 節) |
| `core-areas.json` のコードパス診断 | Phase 4 | 本タスクは文書パスと検査資産パスの登録に限る |
| **`docs/design/data-model.md` の新設とスキーマ本体**(RLS を防御層とする設計判断・そこから導出されるテーブル制約)/ **同期正本由来の物理表現 `WAIT-01`〜`WAIT-08`** / **要件由来の裁定の反映**(`RQ-*`・`SP-*`・FR-030・管理者操作ログ)/ **典拠の識別子参照化** / **設計書 5.1・10.1 の ORM 条項** | **[TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** | TSK-335 の裁定 `R-1`・`R-2`・`R-5`。**本タスクは加筆する側**に立つ |
| **`contracts/legacy-columns/` の契約化**(JSON・schema・lock・`scripts/check_column_map.py`・**その** CI 3 段・**その資産の** `data-migration.paths` 登録) | **[TSK-339](https://app.notion.com/p/3d493b75e6878160abe1c3564bfcca8c)** | 裁定 `R-8`・`R-9`。**本タスクが値を決め、TSK-339 が器を作る**(依存は本タスク → TSK-339 の一方向) |
| **旧資料矛盾の値の採否**(列 44 球種 / 列 86-87 末尾 4 集計 / 列 63-71 の行き先) | **[TSK-334](https://app.notion.com/p/3d493b75e6878176bf75dcbdd70d35b9)** | 本タスクは `IN-05` として受けるだけ(`#### 写像ステップの許可入力集合`) |
| **authz DDL の実機確定**(`BYPASSRLS` / `NOLOGIN` / 関数 ACL / `search_path` / `FORCE RLS` の組合せ) | **[TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)** | 先行タスク B の続き。本タスクは成果の写像に限る |
| **記録権世代の生成アルゴリズム・物理形式** | **論点 17 の受け取り先**(実装計画 = 同期・記録権の最初の実装タスク) | `R-6` の除外。**本タスクにも TSK-342 にも入れない** |

### 切り出しの線引き

**TSK-335 の裁定 `R-1`〜`R-9`(2026-09-08・山田正輝)による確定表。この表が送り先の正。**
**線引き表は実行ステップの所有者を上書きしない** — 4 節の実装ステップ表と
`#### ステップの資産所有表` が同じ内容を持つ。

| 旧ステップ | 触る資産 | 行き先 | 根拠 |
| --- | --- | --- | --- |
| **2・11〜13・15・17・20・22** | `docs/design/data-model.md` の**本文**と引用 | **[TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** | `R-1`(RLS を防御層とする設計判断とテーブル制約は分離できない) |
| **14 のうち「`D5` 一意範囲・`D1` 連続性・適用水位・履歴文脈・楽観ロック・`WAIT-01`(D3 の物理表現)」** | 同上 | **TSK-342** | `R-1` |
| **14 のうち「`D4` の永続化写像」**(`C13` の非再利用・世代) | 記録権世代の物理化 | **本タスクに残す** | `R-6`(同期プロトコル 11-2 の名指し) |
| **16 のうち「退避原本・端末キュー状態 4 種・保持期間の器・`C16` の管理関数クラス分離・`WAIT-02`・`WAIT-04`」** | 同上 | **TSK-342** | `R-1` |
| **16 のうち「復旧世代・`RG1`・`I6` の永続化写像」** | 記録権世代の物理化 | **本タスクに残す** | `R-6`(同上) |
| **25** | 設計書 5.1(ORM = SQLAlchemy 2.x / psycopg 3 / Alembic) | **TSK-342** | `R-2`・`R-5`(折衷形を維持し、TSK-342 の確定ゲートで扱う) |
| **24**(**分割しない**) | staging の木の本番移設 + `profiles/registry.json` の `data-model` entry + `tests/test_ci_wiring.py` の docs-lint 系 + 設計書 10.1 の **`docs-lint` 行** | **本タスクに残す** | `R-8`。**ステップ 16 が触る 10.1 は `docs-lint` 行**であり ORM 条項ではない |
| **26 のうち「`contracts/legacy-columns/` 資産の `data-migration.paths` 登録」** | 同 `paths` | **[TSK-339](https://app.notion.com/p/3d493b75e6878160abe1c3564bfcca8c)** | `R-8`(**TSK-339 の射程はこの範囲だけ**) |
| **26 の残り**(既存 4 領域へ本正本を追加 / `guard_paths` へ新資産の全パスを完全列挙 / 実設定を読む回帰テスト)**・27**(台帳更新) | `.claude/core-areas.json` / `docs/development/harness-evaluation.md` | **本タスクに残す** | `R-8` |
| **3〜10・21・23・28** | 文書検査機構・帰属表・意味照合台帳・検証手順 | **本タスクに残す** | 文書の内部整合の装置 |
| **18・19** | **88 列写像の確定**(値は本タスクが決める)/ **B 由来の認可構成の写像** | **本タスクに残す** | `R-9` / 入力は [TSK-334](https://app.notion.com/p/3d493b75e6878176bf75dcbdd70d35b9) の値の採否と [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2) の完了 |
| **1** | `guard_paths` へ **A(TSK-269)の新資産 33 件**を登録 | **本タスクに残す** | TSK-339 の射程は `contracts/legacy-columns/` 資産の登録であり別物(`R-8`) |

**`R-6` の除外**: **記録権世代の生成アルゴリズム・物理形式そのものは、本タスクにも TSK-342 にも
入れない。** 同期プロトコル 10-1 の論点 17 が受け取り先を「**実装計画(同期・記録権の最初の実装
タスク)**」と名指ししており、**その所有者は変更しない**。

**依存の向き**(`R-9`): **本タスク → TSK-339** の一方向。**本タスクが 88 列写像の値を決め、
TSK-339 が器(`contracts/legacy-columns/` の JSON・schema・lock・検査器)を作る。**
**本タスクは TSK-339 の完了を待たない。**

#### 統制の維持(切り出しても統制は落ちない)

| 対象 | 統制 |
| --- | --- |
| **TSK-342** | **コア領域**(テナント分離・データ移行)→ `sol xhigh`・敵対レビュー・**人間の逐行確認(PR 作成者以外)** |
| **`docs/design/data-model.md` の新設** | **TSK-342 が設計書 7.3 の確定ゲートを通す**(7.6 の決定表 — 正本の新設) |
| **本タスクの加筆分** | **本タスクが改めて 7.3 の確定ゲートを通す**(4 節「確定ゲート」)。**新設のゲートで加筆分は担保されない** |
| **設計書 5.1・10.1**(ORM 条項) | **`R-5` の折衷形** — **版は上げず、差分を TSK-342 の確定ゲートの敵対レビュー対象に含める** |
| **設計書 10.1 の `docs-lint` 行** | 本タスクが持つ(`R-8`)。**実装追随の節更新**なので PR レビューで足りる(7.6-3 前段) |
| **TSK-339** | **コア領域**(データ移行)→ 同上。`data-migration.paths` 登録は**設計書 6.3 規則⑤**(敵対レビュー + 人間承認) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| **`docs/design/data-model.md`** | **加筆**(**新設と最初の `approved` 化は TSK-342** — 裁定 `R-1`。**候補案 1〜12 節の素材移送も TSK-342 の旧ステップ 2**)。本タスクは既存 `approved` 文書へ**同期 ID → 物理写像の表**・**表間参照宣言表**・**`AUTH-*` 対応表**・**要件帰属表**・**意味照合台帳**を新設。**候補案 13 節は移送しない**(`absent-section` で機械保証 — ステップ 4) | **finalize-doc**(7.3。**加筆差分** — 新設と最初の `approved` 化は TSK-342) |
| **`docs/development/dev-harness-design-2026-08-07.md`** | **10.1 の `docs-lint` 行のみ**(**5.1 の追随と 10.1 の ORM 条項は TSK-342** — 裁定 `R-2`・`R-5`)。**10.1 の `docs-lint` 行を現行化**(「伝播突合 12 検査(引数なし)」→ **レジストリ列挙**で同期 12 / データモデル 18、`check_doc_coverage.py` は同期 2 / データモデル 4 — 申し送り 2)。**版は上げない**が、**5.1 の差分を `/finalize-doc` の敵対レビュー対象に含める** | **finalize-doc**(差分のみ。版は上げない) |
| **`docs/README.md`**(索引) | 設計正本の行の**状態追随**(**新設は TSK-342**)。設計書の最終更新日を現行化 | PR レビュー |
| **`.claude/core-areas.json`** | **① A の新資産 33 件を `guard_paths` へ完全列挙で追加(ステップ 1)** ② `data-migration` の `paths` を充填 + 既存 4 領域へ本正本を追加 ③ **本タスクの新資産を `guard_paths` へ完全列挙で追加**(ステップ 17) | PR レビュー(+ 6.3 規則⑤は本ゲートで充足) |
| **`scripts/design_relations/profiles/data-model.json`**(新設) | **文書プロファイル**(A のスキーマ版 1。識別・資産・文法・宣言表・語彙・帰属・名前空間〔`all` = `machine` = `["DM"]`〕・`invariant_kinds`・**`required_checks` = 全 22 / `not_applicable` = {}**・`assets`・**`structure_extractors`**・**`collection_sets`**・`direct_requirements`・`reference_policy`)。**雛形は `tests/fixtures/profile-sample/profiles/data-model-like.json`** | PR レビュー(テストを伴う) |
| **`scripts/design_relations/profiles/registry.json`**(**変更**・既登録) | **`data-model` entry を追加** — `name` / `file` / `document` / **`must_require` = 全 22**(申し送り 11)/ **`pins`**(`profile_gating_digest`・`invariants_digest`・`asset_digests`)。**プロファイル・宣言資産・oracle 資産の変更は必ずこの entry の差分を伴う**(申し送り 21) | PR レビュー + 人間の逐行確認 |
| **`scripts/design_relations/invariants/data-model.json`**(新設) | **宣言資産**(`schema_version` / `structural_required` / `legacy_structural`〔= `[]`〕/ `required_declarations` / `declarations` / `global_invariants`〔`unique-owner`〕)。**A の design 2-2 節の結合規則 1〜6 を満たす**(申し送り 10) | PR レビュー(テストを伴う) |
| **`scripts/design_relations/claims-data-model.json`**(新設) | **入力主張母集合**。同期正本 11-2 の行・要件のデータモデル直接条項・候補案の関係主張を安定 ID 付きで固定し、全行を **`relation` / `forbidden` / **`direct_requirement`** / `out-of-scope`(理由・受取先)** の**排他 4 分類**へ振る(申し送り 22。同一 ID が 2 分類に現れたら失格) | PR レビュー(テストを伴う) |
| **`scripts/design_relations/data-model.json`**(新設) | **関係マニフェスト**。**入力主張母集合の `relation` 行の exact-set** でなければ失格(判定は `collection_sets` の `claims-relations-vs-manifest`) | PR レビュー(テストを伴う) |
| **`scripts/design_relations/defects-data-model.json`**(新設) | **欠陥台帳**。ベースライン **78 件**は `baseline: true`。**項目は immutable = `id / baseline / source / location / detection / check / owner_step / invariant.{scope,forbidden,positive,mapping}`、mutable = `status / discovered_at / closure_evidence`**(A の design 6-2 の digest 対象と一致させる — 申し送り 10)。**機械欠陥は `check`(22 ID のいずれか)と `invariant` を必ず持つ**。新規は追記可 | PR レビュー(テストを伴う) |
| **`scripts/design_relations/waiting-data-model.json`**(新設) | **`WAIT-01`〜`WAIT-08`**。各件に `status` / `physical` / `decision_section` / `source_id`(同期側の安定 ID) | PR レビュー(テストを伴う) |
| **`scripts/design_relations/forbidden-data-model.json`**(新設) | **`FORB-01`〜`FORB-04`**。**構造宣言の列 `{id, kind: relation|column-role|transition|reference, source, target, direction, participants}`**(語句一致にしない)。**別名表はここに置かない**(単一の `normalize.aliases` へ) | PR レビュー(テストを伴う) |
| **`scripts/design_relations/baseline-digest-data-model.txt`**(新設) | 欠陥台帳の**不変部分の digest**(A の canonical 形・SHA-256・`envelope` 先頭行)。ベースライン 78 件の改変を検出する | PR レビュー(テストを伴う) |
| **`scripts/design_relations/expected-ids-data-model.json`**(**新設** — 申し送り 15) | **`unique-owner` の期待 ID 集合**(独立資産)。`baseline_digest` asset の `expected_ids` / `owner_steps_allowed` が参照する | PR レビュー(テストを伴う) |
| **`scripts/design_relations/direct-requirements-data-model.json`**(**新設** — 申し送り 15) | **データモデル直接要件の ID 集合**(非空・全 ID が `req-universe.json` に存在)。**`claims` の `direct_requirement` 分類と exact-set**。`attribution-direct` の oracle であり、**`pins.asset_digests.direct_requirements` で固定する** | PR レビュー + 人間の逐行確認 |
| **`scripts/design_relations/auth-ddl-map-data-model.json`**(**新設** — 申し送り 15) | **AUTH カタログ entry → DDL 要素 ID + 構造**の写像。`entries[*].{catalog_entry_id, ddl_ids[*], structures[*]}`。ID 集合 = `auth_catalog` と exact-set / `ddl_ids` 非空 / **`structures` は entry ごとに非空・`participants ⊆ ddl_ids`・全 entry の和 = `ddl_elements` 導出構造と exact** | PR レビュー + 人間の逐行確認 |
| **`scripts/design_relations/product-ddl-map-data-model.json`**(**新設・条件付き** — 申し送り 15・23) | **probe 要素 ID → 製品要素 ID** の写像。**`contracts/authz/ddl-elements.json` の `scope.product_schema` が `false`(2026-09-04 時点は `candidate_probe_only`)である限り必須**。domain = `auth_ddl_map` が参照する全 ID(`refs` ∪ `structures` の `source`/`target`/`participants`)と exact-set。未写像・余分・曖昧(1 対多)は終了 2 | PR レビュー + 人間の逐行確認 |
| **`scripts/design_relations/citation-map-data-model.json`**(新設) | **旧参照 → 新安定 ID の対応表**(**TSK-342 の旧ステップ 22** の置換を覆い、置換前後の規範の同一性判定を行ごとに記録する。**本資産は TSK-342 の射程**) | **TSK-342 が持つ**(裁定 `R-1`) |
| **`scripts/design_relations/handoff-digest-data-model.json`**(新設) | **受け渡し資産のパスと digest**(写像時点の値。最終検証で再照合する)— **TSK-317 の確定成果**(AUTH カタログ・DDL 要素表・不採用構成表)**と `IN-01`〜`IN-04` の `research_blob_sha`**。**「C の 88 列写像 JSON」は入れない**(存在しない — 裁定 `R-9`) | PR レビュー(テストを伴う) |
| **`scripts/verify_handoff_digest.py`**(**新設** — 申し送り 7) | **受け渡し digest の再照合器**。**A のコンフォーマンスランナーには載せない**(ランナーは単一プロファイルの検証器)。本タスクの専用スクリプトとして置き、`guard_paths` へ加える | PR レビュー(テストを伴う) |
| **`tests/fixtures/data-model-source.txt`** | 退行 fixture(本文のバイト単位のコピー。**拡張子は `.txt`**)。**新設は TSK-342 の旧ステップ 2** — 本タスクは**入力として受ける**(加筆に合わせた更新は本タスク) | **新設は TSK-342** / 更新は PR レビュー |
| **`scripts/design_relations/fixture-sha256-data-model.txt`** | **ソース fixture 専用の SHA-256**(**新設は TSK-342 の旧ステップ 2**。本タスクは加筆に合わせて更新する)(欠陥台帳用の `baseline-digest-data-model.txt` とは別資産 — 用途が違うので代用しない) | PR レビュー |
| **`tests/fixtures/data-model-negative/` 配下の 10 ファイル**(新設) | 負例。**`guard_paths` は完全一致集合でディレクトリ登録では配下の変更が発火しない**(`scripts/core_guard.py`)ため、**個別ファイル名で固定する**: `01-relation-missing.json` / `02-claim-missing.json` / `03-all-out-of-scope.json` / `04-forbidden-alias.json` / `05-wait-resolved-by-forbidden.json` / `06-baseline-digest-tampered.json` / `07-auth-uses-forbidden-direction.json`(4 周目 P1-2)/ **`08-auth-ddl-map-structure-missing.json`** / **`09-product-ddl-map-domain-gap.json`** / **`10-direct-requirements-claims-mismatch.json`**(申し送り 15・22・23) | PR レビュー(テストを伴う) |
| **`scripts/design_relations/staging/data-model/`**(**一時物** — 申し送り 14) | ステップ 2 で作りステップ 16 で本番へ移設して削除する。**`guard_paths` へは登録しない**(最終パスをステップ 17 で登録する) | PR レビュー |
| **CI ワークフロー** | **`ci.yml` は無変更**(docs-lint の 3 step。**引数なし = 本番レジストリ列挙**)。`tests/test_ci_wiring.py` を**登録の事実**に合わせて更新する | PR レビュー(テストを伴う) |
| **`docs/development/harness-evaluation.md`**(台帳) | H-12 の事象欄を現況へ。**H-78・H-79 に本タスクの実績を追記**(A の申し送り処理と統制の空白の解消を含む — 申し送り 4)。**`H-*` の新規採番はしない** | PR レビュー |
| `docs/requirements/**` / `docs/adr/**` / `contracts/` / `backend/` / `scripts/check_*.py` / `scripts/doc_check_*.py` | **反映なし**(要件改訂・ADR・ベクタ・実装・検査エンジンはいずれも別タスクの射程) | — |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域**

本タスクは 5 つのコア領域すべてに触れる(設計書 6.3)。**敵対レビュー必須・人間の逐行確認必須**。
ラッパーは ADR-001 により **sol xhigh** を自動適用する。**design.md は作らない**(詳細設計は成果物である
正本そのもの — 設計書 7.1-1)。

### 同期正本との関係 — **意味規則を再記述しない**

本書は **`同期側の安定 ID → 物理表・列・制約・索引可否` の写像**だけを持つ。**D1〜D9 の意味規則・
発火条件・遷移条件を本文へ書き直さない**。キャッシュ無効化も**同期側のトリガー ID を参照**し、
本書は**物理的な無効化先**だけを決める。

### 欠陥台帳(ベースライン 78 件)

**ベースラインは不変、新規発見は追記可**(1 周目 P0 を採用)。**`ID → 所有ステップ` の全展開表**を持ち、
**全 ID がちょうど 1 回出現する**ことを機械検査する(`unique-owner` — 期待集合は
`expected-ids-data-model.json`、許容する所有ステップは `owner_steps_allowed`)。

**所有は TSK-335 のステップ 6・7(裁定 `R-1`・`R-6`)で再割当てした。旧番号は使わない。**

| 群 | 件数 | ID | 所有タスク | 所有ステップ(**新番号**) |
| --- | --- | --- | --- | --- |
| `DM-SY-C*` | **16** | `C01`〜`C15` + **`C16`**(2 周目に発見 — 候補案 8-2-B クラス (c) が `FORB-01` の構造を含む) | **TSK-342**(旧 11・12 と旧 14・16 の TSK-342 側)/ **本タスク**(旧 14・16 の永続化写像側) | 本タスク分 = **10**(`C13` の `D4`)・**11**(`C07`・`C15`・`C16` の復旧世代・`RG1`・`I6` 側) |
| `DM-SY-M*` | 20 | `M01`〜`M20` | **TSK-342**(旧 12・13・15 と旧 16 の TSK-342 側)/ **本タスク**(旧 16 の永続化写像側) | 本タスク分 = **11** |
| `DM-SY-B*` | 5 | `B01`〜`B05` | **TSK-342**(旧 17) | — |
| `DM-LG-*` | 16 | `LG-01`〜`LG-16`(**個別 ID を台帳に明記** — 2 周目 P1-10 を採用) | **本タスク** | **12**(88 列写像の確定 — 裁定 `R-9`) |
| `DM-LX-*` | 6 | `LX-01`〜`LX-06` | **本タスク** | **12**(同上。**`LX-01`・`LX-02` は「射程外・不明」のまま渡す**) |
| `DM-RQ-*` | 9 | `RQ-01`〜`RQ-09`(**各件に裁定 ID・決定者・決定日・反映節** — 2 周目 P1-12 を採用) | **TSK-342**(旧 20) | — |
| `DM-SP-*` | 6 | `SP-01`〜`SP-06`(同期正本が判定を放棄して送った禁止事項) | **TSK-342**(旧 20) | — |
| 合計 | **78** | | | |

**TSK-342 所有の群の扱い**: **TSK-342 側の欠陥台帳で `resolved` + `closure_evidence` を持つ。**
本タスクは **① 開始条件(TSK-342 の完了)でそれを確認**し、**② ステップ 15 で本タスクの台帳へ
`closure_evidence` を取り込む**(取り込んだ行の `owner_step` は **`TSK-342` を明示**し、
本タスクの `S<番号>` を割り当てない)。**`owner_steps_allowed` は「新 1〜19 または `TSK-342`」という広い集合にしない**
(2 周目 `P0-1`: それでは `DM-LG-*` を旧 18 のまま残しても通ってしまう。**失格になるのは旧 20 だけ**
だった — 実測)。→ **群ごとの許可集合の写像**として `expected-ids-data-model.json` に固定する
(**作成は ステップ 4**):

**`owner_step` の値は素の数値にしない。`S<新番号>` の形にする**(自己走査で発見 — 素の数値だと
**旧 11(順序系の写像 → TSK-342)と新 11(復旧世代の永続化写像 → 本タスク)が数字として衝突**し、
`DM-SY-C*` は旧番号のままでも通ってしまった〔実測〕)。**`S` 接頭辞により旧番号の残存が構文的に落ちる。**
※ これは `owner_step` の**値**の書式であり、`#### ステップの資産所有表` の「新ステップ ID」列
(素の `1`〜`19`)とは別物である。

| 群 | `owner_steps_allowed`(この集合の外は終了 2) |
| --- | --- |
| `DM-LG-*` | **`{"S12"}`** のみ |
| `DM-LX-*` | **`{"S12"}`** のみ |
| `DM-SY-C*` | **`{"S10", "S11", "TSK-342"}`** のみ |
| `DM-SY-M*` | **`{"S11", "TSK-342"}`** のみ |
| `DM-SY-B*` | **`{"TSK-342"}`** のみ |
| `DM-RQ-*` | **`{"TSK-342"}`** のみ |
| `DM-SP-*` | **`{"TSK-342"}`** のみ |

**`DM-SY-C*`・`DM-SY-M*` の ID 単位の内訳はステップ 4 で確定する**(旧 16 は `C07`・`C15`・`C16`・
`M11`〜`M14`・`M16`・`M19` を持ち、そのうち **復旧世代・`RG1`・`I6` に関わる ID が新 11**、
**残りが TSK-342**。旧 14 は `C13` が `S10`)。**1 欠陥 ID を 2 つの所有へ分けない**(`unique-owner`)。
ステップ 4 の合格条件で **各 ID が群の許可集合のいずれか 1 つに割り当てられている**ことを検査する。

**追記分**: `DM-MT-01`(候補案 13 節の不在 — `absent-section`。申し送り 13)は**ベースライン外の追記**として
`baseline: false` で置き、`required_declarations` に入れる。**ベースライン 78 件の集合は変えない。**

### 台帳間の交差検査(2 周目 P0-6 を採用 / 申し送り 23)

表・列・制約・状態遷移・関数に**共通の正規化 ID** を与え(端点はすべて `{namespace, id}`)、次を機械検査する:

- `WAIT` が `resolved` なら、その物理表・列が**関係マニフェストと本文の双方に存在する**
- `AUTH` の DDL 要素が**関係マニフェストに存在する** — **二段階射影**で判定する:
  - **段階 A(raw DDL ID)**: `auth_ddl_map` の各 ref が `ddl_elements` に存在 / map の ID 集合 = `auth_catalog` /
    各 entry の `refs`・`structures` 非空 / `structures` の和 = DDL 導出構造(exact)
  - **段階 B(製品 ID)**: `product_ddl_map` を `refs` と `structures` の `source`/`target`/`participants` の**全 ID に適用**して
    製品構造へ射影し(`product_schema` が真なら恒等写像)、射影後の各 ref が**マニフェスト要素集合に存在する**
- **`WAIT` ∩ `FORB` = ∅** かつ **`AUTH` ∩ `FORB` = ∅** — 射影後の AUTH structures ∪ WAIT 導出構造と `forbidden` を
  **`{kind, source, target, direction, participants}` の全項目**で照合(`both` は方向不問)

**衝突の負例**(WAIT を FORB 対象の関係で解消する / AUTH が FORB の参照方向を使う / `structures` 1 件脱落 /
`product_ddl_map` の domain 欠落)を fixture に置く。

### pins の更新規律(申し送り 21)

**プロファイルのゲート節・宣言資産・oracle 資産を変えるステップは、同一コミットで
レジストリ entry の `pins` を再計算して更新する。** 更新を怠れば `pins` 不一致で終了 2 になる(黙って通らない)。
**`pins` の差分がレビュー対象**であり、プロファイルの自己申告だけで必須検査を有効化・空洞化できない。
`asset_digests` のキー集合は **`required_checks` に対応する資産を必ず含む**(`attribution-direct` があるなら
`direct_requirements`、`cross-consistency` があるなら `auth_ddl_map` / `product_ddl_map` / `ddl_elements` / `forbidden`、等)。

### 検証コマンド集合(**計画で事前固定する** — 2 周目 P1-13 を採用 / 申し送り 1・7)

ステップ 19 が収録するのは**次の集合と exact-set 一致**でなければ失格とする:

1. `uv run ruff check .`
2. `uv run ty check`
3. `uv run pytest tests/`
4. `uv run python scripts/check_docs_status.py`
5. `uv run python scripts/check_design_propagation.py`
   — **引数なし = 本番レジストリ列挙**(同期 + データモデルの 2 プロファイル。CI の docs-lint と同一)
6. `uv run python scripts/check_doc_coverage.py` — **引数なし = 同上**
7. `uv run python scripts/check_doc_profiles.py --profile scripts/design_relations/profiles/data-model.json`
   — コンフォーマンスランナー(**22 件すべて `pass`**・`partial: false`)
8. `uv run python scripts/check_doc_profiles.py --profile scripts/design_relations/profiles/sync-protocol.json`
   — 同期側の回帰(既存 14 が `pass`・新 8 が `not_applicable`)
9. `uv run python scripts/verify_handoff_digest.py --handoff scripts/design_relations/handoff-digest-data-model.json`
   — **先行資産の digest 再照合**(**TSK-317 の確定成果**〔AUTH カタログ・DDL 要素表・不採用構成表〕と
   **`IN-01`〜`IN-04` の `research_blob_sha`** が本タスクの写像時点の値と一致すること
   = **先行タスクの成果が後から動いていないことの確認**)。**「C の 88 列写像 JSON」は照合対象に入れない**
   — **存在しない**(裁定 `R-9`)。
   **A のランナーには載せない**(申し送り 7)。本タスクの専用スクリプトとして置き、3 節と `guard_paths` へ加える

**旧 7・8 の「同期正本側を明示引数で指定する暫定コマンド」は撤回した**(4 周目 P1-1 の宿題は本改訂で解消 —
A のマージで引数なし列挙が正になったため、暫定パスの置換自体が不要になった)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**開始条件は 5 節が正**(裁定 `R-3` — **成果単位**)。**要旨**: **TSK-342 の完了**(`docs/design/data-model.md` が
`approved`)/ **TSK-317 の完了**(認可構成の確定成果。候補 probe 資産では満たさない)/ **TSK-334 の完了**
(値の採否 = `IN-05`)/ **本改訂への人間の再承認**。A(TSK-269)は充足 — PR #42 / `fdda374`。
C(TSK-271)は PR #48 / `196627ec` でマージ済みだが **88 列写像 JSON は作らない**(裁定 `R-9`)。
**文書の是正ステップでは fixture と digest を変更しない。**
**ステップ 3 以降、プロファイル・宣言資産・oracle 資産を触るステップは `pins` を同一コミットで更新する。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **A の新資産の `guard_paths` 登録**(**最初の独立コミット** — 申し送り 3)— `.claude/core-areas.json` の `guard_paths` へ、**TSK-269 が新設した B 集合の未登録 33 パスを完全列挙で追加**する(`scripts/design_relations/{profiles/registry.json, profiles/sync-protocol.json, invariants/sync-protocol.json}`・`schemas/` 5 本・`scripts/doc_check_profile.py`・**`scripts/doc_check_invariants.py`**・`scripts/check_doc_profiles.py`・`tests/fixtures/profile-sample/` 19 本・`tests/fixtures/structural-reasons-expected.json`・`tests/test_doc_check_profile.py`・`tests/test_check_doc_profiles.py`)。**`.claude/scripts/codex_run.py` / `tests/test_codex_run.py`(C 集合)は対象外**(2 節) | **`fdda374` の差分のうち `docs/` 以外の全ファイルが `guard_paths` に包含されている**(実 diff から導出した集合と突合。**A の design 3 節 B 表は 38 件だが `scripts/doc_check_invariants.py` が漏れているため、表ではなく実 diff を正とする**)/ **各パスの変更で `core_guard.py` が発火することを実設定から確認するテストがある** / `uv run pytest tests/` green / **本ステップの差分は `.claude/core-areas.json` と `tests/test_core_guard.py` のみ** |
| 2 | **staging の木の原子的作成**(**新設** — 申し送り 14・12)— **開始条件(TSK-342 の完了)を満たした直後**に `scripts/design_relations/staging/data-model/` へ `profiles/{registry.json,data-model.json}`・`doc/{manifest,defects,invariants}.json`・`assets/`(10 資産)を、**全必須資産の構造的に妥当な骨格つきで 1 コミットに**作る。`document` / `requirements` / `universe` は本番パスを参照する | **`check_doc_profiles.py --registry <staging>/profiles/registry.json --profile <staging>/profiles/data-model.json --json` が終了 2 にならない**(= スキーマ・レジストリ・完全分割・`must_require`・`pins`・必須資産の宣言がすべて成立)/ **終了 1・`partial: false` で 22 件の診断が返る** / **`staging/.../profiles/` にレジストリとプロファイル以外を置いていない** / **本番レジストリは無変更**(CI green) |
| 3 | **文書プロファイルの確定** — staging の `data-model.json` を実仕様へ確定する: 識別・資産・文法・宣言表節・帰属表節・台帳節・帰属区分の語彙・**`defect_id_namespaces` = `{all: ["DM"], machine: ["DM"]}`**・`invariant_kinds`(**契約の 5 種別名も書ける** — 申し送り 17)・**`required_checks` = 全 22 / `not_applicable` = {}**(申し送り 11)・**`assets`**(申し送り 8 — `path` / `identity` / `collections` / `join` / `namespace` / `structure` / `normalize`)・**`structure_extractors`**(申し送り 19 — 関係・遷移表・列役割表・暗黙関係)・**`collection_sets`**(申し送り 20)・`direct_requirements`・`reference_policy`。**レジストリ entry の `must_require` = 全 22 と `pins` を同時に確定** | **staging レジストリでローダーを通る**(スキーマ版一致・`profiles/` 実ファイル完全一致・`pins` 一致)/ **`required_checks ∪ not_applicable` = 22・積は空・`required_checks ⊇ must_require`** / **未対応の不変条件種別・未知フィールド・pins 不一致・必須検査の資産/抽出器/集合宣言の欠落がいずれも終了 2 になる**(fail-closed の確認 — 申し送り 6)/ **`structure_extractors` が `forbidden` の全 `kind` を覆う** / **実プロファイルを使う契約テストがある**(契約 4) |
| 4 | **欠陥台帳のベースライン固定** — `defects-data-model.json` に **78 件**を全 ID 明記で固定し、**immutable / mutable を 3 節の項目どおりに分け**、`baseline-digest-data-model.txt` と `expected-ids-data-model.json` を作る。**`invariants/data-model.json` に `global_invariants`(`unique-owner`)と `DM-MT-01`(`absent-section: "13"`)を置く**(申し送り 10・13・15) | **78 件すべてに必須フィールド(機械欠陥は `check` と `invariant` を持つ)** / **群別件数と ID 集合が 4 節の表と一致**(exact-set)/ **全 ID がちょうど 1 回・`owner_steps_allowed` の範囲に割り当て**(`unique-owner`)/ **`owner_steps_allowed` が 4 節の群写像どおり**(`DM-LG-*`・`DM-LX-*` は `{"S12"}` のみ / `DM-SY-C*` は `{"S10", "S11", "TSK-342"}` のみ / `DM-SY-M*` は `{"S11", "TSK-342"}` のみ / `DM-SY-B*`・`DM-RQ-*`・`DM-SP-*` は `{"TSK-342"}` のみ)/ **`owner_step` の値が `^S(1[0-9]|[1-9])$` または `TSK-342` に一致**(**素の数値は終了 2** — 旧番号の残存を構文で落とす)。**旧番号を素の数値で入れた負例(`11`・`18`・`20`)で終了 2**/ **immutable 各フィールド(`baseline` 反転を含む)の改変で red・mutable 改変で green**(`baseline-digest`)/ **候補案 13 節を復活させると `absent-section` が red** / **負例 `06-baseline-digest-tampered.json` で red** |
| 5 | **入力主張母集合・独立資産・受け渡し digest の固定** — `claims-data-model.json` に、**同期正本 11-2 の行・要件のデータモデル直接条項・候補案の関係主張・TSK-317 の DDL 要素表・C の `IN-01`〜`IN-04`**(判定 22 件 + センチネル全 88 列表 + 座標の確定式)**の和集合**を**安定 ID + 共通正規化 ID 付き**で固定し、全行を **`relation` / `forbidden` / `direct_requirement` / `out-of-scope`(理由・受取先)** へ排他分類する(申し送り 22)。**同一コミットで `direct-requirements-data-model.json`・`auth-ddl-map-data-model.json`・(probe-only なら)`product-ddl-map-data-model.json`・`handoff-digest-data-model.json` を作り、`scripts/verify_handoff_digest.py` を新設する**(申し送り 7・15) | **全行に出典の安定 ID と共通正規化 ID がある**(**該当なしは明示的な空集合 + 理由**)/ **TSK-317 の確定成果の全行と `IN-01`〜`IN-04` の全行が母集合に現れる**(exact-set。**成果 ID + blob digest と `research_blob_sha` の照合つき**。**`IN-05`〜`IN-08` は claims の母集合に入れない** — `IN-05` は値の採否・`IN-06` は要件・`IN-07` は evidence・`IN-08` は物理実体名であり主張ではない)/ **未分類・二重分類が 0 件** / **`direct_requirements` が非空で `claims` の `direct_requirement` と exact**(`collection-consistency`)/ **`auth_ddl_map` の ID 集合 = `auth_catalog`・`structures` 非空・`participants ⊆ ddl_ids`** / **`verify_handoff_digest.py` が TSK-317 の確定成果と `IN-01`〜`IN-04` を覆い green** / **負例 `02`・`03`・`08`・`09`・`10` で red** / **本ステップで本文を変更していない** |
| 6 | **受け取り台帳・禁止構造台帳・関係マニフェスト** — `waiting-data-model.json`(`WAIT-01`〜`08`)/ `forbidden-data-model.json`(`FORB-01`〜`04`)/ `data-model.json`(**母集合の `relation` 行の exact-set**)を固定し、**`collection_sets` に `claims-relations-vs-manifest`(exact)を宣言する**(申し送り 20) | **`WAIT-01`〜`08` が同期正本の該当箇所と 1 対 1**(逐行照合し結果を worklog へ)/ **`FORB-*` が `{kind, source, target, direction, participants}` の構造として表現され、別名の負例で red**(別名は単一の `normalize.aliases` のみが供給源)/ **マニフェストが `relation` 行の exact-set でなければ red** / **禁止関係を母集合へ混入させた負例で red** |
| 7 | **交差検査の設定** — 4 節の 3 条件(`WAIT` → 存在 / `AUTH` → 二段階射影で存在 / `WAIT`・`AUTH` ∩ `FORB` = ∅)を **A の DSL・`structure_extractors`・`collection_sets` の設定として**表現し、衝突の負例 fixture を置く。**エンジンの変更が必要と判明したら停止し、Notion の TSK-269 へコメント + 新規タスク起票**(申し送り 9。本ステップで `scripts/check_*.py` / `scripts/doc_check_*.py` を変更しない) | `uv run pytest tests/` green / **3 条件それぞれに正常系と衝突負例がある** / **正規化 ID の付け方が本書とマニフェストで一致** / **本ステップの差分に `scripts/check_*.py` / `scripts/doc_check_*.py` が含まれていない**(含める必要が生じた時点で停止) |
| 8 | **表間参照宣言表** — 本書へ宣言表を置き、マニフェストと一致させる | 宣言表がマニフェストと**全フィールドで双方向に一致** / **母集合の全 `relation` が宣言表に現れる** / 伝播検査 green |
| 9 | **述語の参照規約** — D1〜D9 を**本書で再定義せず参照**する規約と、**同期 ID → 物理写像の表**の枠を置く。本書固有の述語の単一定義節と**禁じる別名の表**を作る | **D1〜D9 の定義文が本書に無い**(`forbidden-element`)/ **本書の述語がすべて単一定義節にあり他節は参照のみ** / 伝播検査 green |
| 10 | **`D4` の永続化写像**(`C13` の非再利用・世代)— **旧ステップ 14 を資産単位で分割した残り**(裁定 `R-6`。`D5` の一意範囲・`D1` の連続性・適用水位・履歴文脈・楽観ロック・`WAIT-01` は **TSK-342**)。**生成アルゴリズム・物理形式は入れない**(`R-6` の除外 — 論点 17 の受け取り先が持つ) | **`D4` が非再利用として表現されている** / **世代の物理表現がある** / **生成アルゴリズム・物理形式の記述が 0 件** / **意味規則の再記述が 0 件**(ステップ 9 の検査)/ 伝播検査(累積)green |
| 11 | **復旧世代・`RG1`・`I6` の永続化写像** — **旧ステップ 16 を資産単位で分割した残り**(裁定 `R-6`。退避原本・端末キュー状態 4 種・保持期間の器・`C16` の管理関数クラス分離・`WAIT-02`・`WAIT-04` は **TSK-342**)。**生成アルゴリズム・物理形式は入れない**(`R-6` の除外) | **復旧世代・`RG1`・`I6` に物理写像がある** / **退避原本との区別が本文にある** / **生成アルゴリズム・物理形式の記述が 0 件** / 伝播検査(累積)green |
| 12 | **88 列写像の確定**(`LG-01`〜`LG-16`・`LX-01`〜`LX-06`)— **許可入力集合**(`#### 写像ステップの許可入力集合` の `IN-01`〜`IN-08`)**だけ**を根拠に、**88 列すべての意味欄 4 項目**(実際の中身 / 旧コードの参照箇所 / 新スキーマの行き先 / 変換規則)と**欠損時規則**(センチネル由来と解決不能由来を分離)を本文へ確定する。**値を決めるのは本タスク**(裁定 `R-9`)。**`LX-01`・`LX-02` は「射程外・不明」のまま渡す** | **`column_index` 0〜87 の全行が本文にある**(欠番 0)/ **各行の根拠が `IN-01`〜`IN-08` のいずれかを明示**しており、**集合外の資料を根拠に引いた行が 0 件** / **`IN-01`〜`IN-04` は `research_blob_sha` を照合**し、一致しなければ fail / **`docs/legacy/` が `normative` として参照されていない**(`reference-class` で `evidence` のみ)/ **`LX-01`・`LX-02` に値を書いていない**(「不明」のまま)/ 伝播検査(累積)green |
| 13 | **認可構成の写像** — **TSK-317 の確定成果**(`AUTH-*` カタログ・DDL 要素表・不採用構成表 — **成果 ID と blob digest で特定する**。`candidate_probe_only` の probe 資産は入力にしない)を本文へ写像し、**主張 ID → DDL 要素 → テスト ID → 正本の節**の対応表を置く。**`auth_ddl_map`(と probe-only なら `product_ddl_map`)を実値で埋める**(申し送り 15・23) | **`AUTH-*` が TSK-317 の確定成果と exact-set 一致**(**成果 ID と blob digest を照合**。本文に書いた分だけを数えない)/ **入力の `status` が `candidate_probe_only` でない**/ **全 `AUTH-*` に DDL 要素とテスト ID がある** / **段階 A・段階 B の両方が green**(`cross-consistency`)/ **B の不採用構成表の各項目が本文に 1 件も現れない**(**不採用集合との突合**で判定)/ **`AUTH` ∩ `FORB` = ∅ green** / **負例 `07`・`08`・`09` で red** |
| 14 | **要件帰属表** — `req-universe.json` に対する本書の帰属表を安定 ID で作る。**「対象外」は理由コードと受取先を必須**とし、**データモデル直接要件には使用禁止**(`attribution-direct`) | **母集合の全 ID が分類されている** / **帰属先の節が実在し、展開した節のいずれかに当該要件の安定 ID が明示出現する行が 1 行以上ある**(`attribution-destination`)/ **全件「対象外」の負例で red** / **`direct_requirements` の ID を「対象外」にすると red** / **行番号由来のキーが 0 件** |
| 15 | **意味照合台帳の記入と本文の是正** — 全引用について台帳を埋め、判定が「支持」以外の箇所を本文で是正する。**ここで staging の全 22 検査が終了 0 になる**(申し送り 12) | 台帳検査 green(**台帳のキー集合 = 本文の引用集合**)/ **判定が「支持」以外の行が 0 件** / **`check_doc_profiles.py --registry <staging>/profiles/registry.json --profile <staging>/profiles/data-model.json` が終了 0・22 件すべて `pass`** / 伝播検査(累積)green |
| 16 | **本番移設と登録(= CI 配線)**(申し送り 1・2・14)— staging の木を**本番パスへ移設**し、**`profiles/registry.json` へ `data-model` entry(`must_require` = 全 22・`pins` 実値)を追加**する。**移設と登録は同一コミット**。`ci.yml` は無変更(引数なし列挙)。`tests/test_ci_wiring.py` を更新し、設計書 10.1 の `docs-lint` 行を現行化 | **引数なしの `check_design_propagation.py` / `check_doc_coverage.py` が 2 プロファイルを列挙して green**(新旧両文書)/ **`profiles/` の実ファイル集合とレジストリの `file` 集合が完全一致** / **`staging/` が残っていない** / **`test_ci_wiring.py` が「本番レジストリに `data-model` entry がある」ことを確認**(明示引数のアサーションを置かない)/ `uv run pytest tests/` green / 設計書の変更履歴表に行がある |
| 17 | **`core-areas.json` の登録(本タスク分)** — `data-migration` の `paths` 充填、既存 4 領域へ本正本を追加、**`guard_paths` へ 3 節で固定した新資産の全パスを完全列挙**、**実設定を読む回帰テスト** | `uv run pytest tests/` green / **3 節が列挙する新資産の全パスが `guard_paths` に包含されている**(**負例 10 ファイルも個別に登録**。`guard_paths` は完全一致集合で**ディレクトリ登録では配下の変更が発火しない**)/ **`staging/` のパスが登録されていない**(移設済み)/ **① 5 領域すべてに本正本 ② `data-migration` が空でない ③ 新資産それぞれの変更で発火 を実設定から確認するテストがある** |
| 18 | **台帳の更新** — H-12 の事象欄を現況へ(**`core-areas.json` から導出した期待値を列挙して照合**)、**H-78・H-79 に実績を追記**(A の申し送り 24 項目の処理結果と、ステップ 1 による統制の空白の解消を含む)。**`H-*` の新規採番はしない** | `check_docs_status.py` green / **H-12 の記述が `core-areas.json` の実値と一致** / **H-78・H-79 に本タスクの実績行がある** / **`H-*` の新規採番が 0 件** |
| 19 | **検証手順の収録** — 本書へ**4 節で事前固定したコマンド集合(9 件)**を収録する。**実行結果・SHA は worklog へ** | **収録列が 4 節の集合と exact-set 一致** / **本書に実行結果が書かれていない** / **worklog に全コマンドの結果と対象 SHA がある** / **全コマンド green** |
#### 移管資産の禁止集合と残存資産の必須集合

**TSK-335 のステップ 7 で固定した安定 ID 付きの 2 集合。**
**禁止集合(`FB-*`)は operative な DoD・確定ゲートの両方に 1 件も現れてはならない。**
**必須集合(`MB-*`)は DoD に全件必要**であり、**確定ゲートには該当する逐行確認対象を置く**
(**確定ゲートは手順であって資産の目録ではない** — 全 12 件の列挙は求めない)。履歴節の逐語は対象外。

**禁止集合(移管した資産 — `FB-*`)**

| ID | 資産 | 送り先 | 根拠 |
| --- | --- | --- | --- |
| `FB-01` | `docs/design/data-model.md` の**新設**と最初の `approved` 化 | **TSK-342** | `R-1` |
| `FB-02` | 設計書 5.1 の ORM 確定(SQLAlchemy 2.x / psycopg 3 / Alembic) | **TSK-342** | `R-2`・`R-5` |
| `FB-03` | 設計書 10.1 の **ORM 条項**と `test_psycopg_is_exact_product_dependency_without_orm_packages` | **TSK-342** | `R-2` |
| `FB-04` | `WAIT-01`〜`WAIT-08` の `resolved` 化 | **TSK-342** | `R-1`(スキーマ本体の物理表現) |
| `FB-05` | 典拠の識別子参照化と `citation-map-data-model.json` | **TSK-342** | `R-1`(旧ステップ 22) |
| `FB-06` | 要件由来の写像(`RQ-01`〜`09`・`SP-01`〜`06`・FR-030・管理者操作ログ)と、そのための人間の裁定 | **TSK-342** | `R-1`(旧ステップ 20) |
| `FB-07` | `contracts/legacy-columns/` 資産の `data-migration.paths` 登録 | **TSK-339** | `R-8` |
| `FB-08` | 旧資料矛盾の**値の採否**(列 44 / 列 86-87 / 列 63-71) | **TSK-334** | 本タスクは `IN-05` として受ける |
| `FB-09` | 記録権世代の**生成アルゴリズム・物理形式** | **論点 17 の受け取り先** | `R-6` の除外 |

**必須集合(残存する資産 — `MB-*`)**

| ID | 資産 | 所有ステップ |
| --- | --- | --- |
| `MB-01` | `docs/design/data-model.md` への**加筆**と、**加筆差分**の 7.3 確定ゲート通過 | 8〜15・19 + 確定ゲート |
| `MB-02` | ベースライン欠陥 78 件 + 追記分の `resolved` + `closure_evidence` | 4・15 |
| `MB-03` | `FORB-01`〜`FORB-04` の構造が本書に存在しないこと | 6・15 |
| `MB-04` | `AUTH-*` が TSK-317 の確定成果と exact-set 一致(成果 ID + blob digest) | 13 |
| `MB-05` | 88 列すべての意味欄 4 項目 + 欠損時規則、根拠が `IN-01`〜`IN-08` | 12 |
| `MB-06` | `D4`・復旧世代・`RG1`・`I6` の永続化写像 | 10・11 |
| `MB-07` | `.claude/core-areas.json`(A の 33 件の `guard_paths` / `data-migration.paths` の本タスク分 / 5 領域へ本正本) | 1・17 |
| `MB-08` | 契約 5 の 4 保証の機械化(`required_checks` = 全 22・`must_require` = 全 22 + 負例) | 3・7 |
| `MB-09` | レジストリ entry の `pins`(`profile_gating_digest` / `invariants_digest` / `asset_digests`) | 16 |
| `MB-10` | 本番移設とレジストリ登録(= CI 配線)+ 設計書 10.1 の **`docs-lint` 行** | 16 |
| `MB-11` | 台帳 H-12・H-78・H-79 の更新(**`H-*` の新規採番 0 件**) | 18 |
| `MB-12` | 検証手順の収録(**実行結果と SHA は worklog**) | 19 |

#### ステップの資産所有表

**operative なステップ表と 1:1 で対応する。所有が `TSK-250` 以外の行はここに置かない。**
**`contracts/legacy-columns/` 資産の `data-migration.paths` 登録は TSK-339 の所有**であり、
ステップ 17 には含めない(裁定 `R-8`)。

**各行は operative なステップ表の「変更する資産」の完全集合**(1 周目 `P1-5` の反映 —
当初は代表資産だけを書いていた)。**テスト・`pins`・digest・`expected_ids`・`invariants`・
負例 fixture も漏れなく含める。**

**負例 fixture の所有規則**(2 周目 `P0-3`): `tests/fixtures/data-model-negative/` の 10 ファイルは、
**それを合格条件に使う各ステップが同一コミットで置く**。**1 ファイルが複数ステップの合格条件に
現れる場合は、最初に使うステップが所有する**(`08`・`09` はステップ 5 が所有し、ステップ 13 は
既存のものを使う)。**ステップ 3 は負例を所有しない**(fail-closed の確認は入力不正の合成で行う)。

**`pins` の更新規則**(同): **ステップ 3 で初期確定**し、**ステップ 4 以降でプロファイル・宣言資産・
oracle 資産を触るステップは同一コミットで更新する**(4 節「pins の更新規律」)。**所有表では
初期確定(3)と本番 entry(16)を明示し、途中の更新はこの規則で覆う。**

| 新ステップ ID | 変更する資産 | 所有タスク |
| --- | --- | --- |
| 1 | `.claude/core-areas.json` の `guard_paths`(**A の新資産 B 集合 33 パスを完全列挙**)/ `tests/test_core_guard.py`(実設定を読む回帰) | TSK-250 |
| 2 | `scripts/design_relations/staging/data-model/**`(staging の木 — `profiles/{registry.json,data-model.json}`・`invariants/data-model.json`・各台帳・マニフェストの器) | TSK-250 |
| 3 | staging の `profiles/data-model.json`(識別・資産・文法・宣言表節・帰属表節・台帳節・語彙・`defect_id_namespaces`・`invariant_kinds`・`required_checks` = 全 22・`assets`・`structure_extractors`)/ **staging の `profiles/registry.json` の `data-model` entry**(`must_require` = 全 22・`pins` 実値 — **ステップ 3 で同時確定**) | TSK-250 |
| 4 | `scripts/design_relations/defects-data-model.json`(78 件・`owner_step` は `S<新番号>` 形式)/ `baseline-digest-data-model.txt` / `expected-ids-data-model.json`(**群ごとの `owner_steps_allowed` 写像**)/ `invariants/data-model.json`(`global_invariants` の `unique-owner`・`DM-MT-01`)/ **負例 `06-baseline-digest-tampered.json`** | TSK-250 |
| 5 | `claims-data-model.json` / `direct-requirements-data-model.json` / `auth-ddl-map-data-model.json` /(probe-only なら)`product-ddl-map-data-model.json` / `handoff-digest-data-model.json` / `scripts/verify_handoff_digest.py` + そのテスト / **負例 `02`・`03`・`08`・`09`・`10`** | TSK-250 |
| 6 | `waiting-data-model.json`(`WAIT-01`〜`08`)/ `forbidden-data-model.json`(`FORB-01`〜`04`)/ `data-model.json`(関係マニフェスト)/ staging プロファイルの `collection_sets` | TSK-250 |
| 7 | staging プロファイルの交差検査設定(`structure_extractors`・`collection_sets`)/ **衝突の負例 fixture**(3 条件それぞれの正常系と衝突負例)/(検査器そのものは変更しない — 申し送り 9) | TSK-250 |
| 8 | `docs/design/data-model.md` の表間参照宣言表節 + 関係マニフェストとの一致 | TSK-250 |
| 9 | `docs/design/data-model.md` の述語の参照規約節・単一定義節・禁じる別名の表 | TSK-250 |
| 10 | `docs/design/data-model.md` の `D4` の永続化写像節(`C13`) | TSK-250 |
| 11 | `docs/design/data-model.md` の復旧世代・`RG1`・`I6` の永続化写像節 | TSK-250 |
| 12 | `docs/design/data-model.md` の 88 列写像節(88 行 + 各行の根拠 `IN-01`〜`IN-08`) | TSK-250 |
| 13 | `docs/design/data-model.md` の認可構成の写像節 / `auth-ddl-map-data-model.json` /(probe-only なら)`product-ddl-map-data-model.json` の実値 / **負例 `07`**(`08`・`09` は**ステップ 5 が所有** — 下の規則) | TSK-250 |
| 14 | `docs/design/data-model.md` の要件帰属表節 / `req-universe.json` に対する帰属 | TSK-250 |
| 15 | `docs/design/data-model.md` の意味照合台帳節と本文の是正 / `defects-data-model.json`(**TSK-342 の `closure_evidence` の取り込み**)/ **`tests/fixtures/data-model-source.txt` と `scripts/design_relations/fixture-sha256-data-model.txt` の更新**(**本文の最終形に合わせる** — 本タスク最後の本文変更ステップ) | TSK-250 |
| 16 | `scripts/design_relations/**` の**本番パス**(staging から移設)/ `profiles/registry.json` の `data-model` entry(`must_require` = 全 22・`pins` 実値)/ `tests/test_ci_wiring.py`(**docs-lint 系のみ**)/ 設計書 10.1 の **`docs-lint` 行** | TSK-250 |
| 17 | `.claude/core-areas.json`(`data-migration.paths` の本タスク分 / 既存 4 領域へ本正本 / `guard_paths` へ新資産の全パス〔**負例 10 ファイルも個別に**〕)/ `tests/test_core_guard.py`(実設定を読む回帰) | TSK-250 |
| 18 | `docs/development/harness-evaluation.md`(H-12 の事象欄 / H-78・H-79 への実績追記。**`H-*` の新規採番なし**) | TSK-250 |
| 19 | `docs/design/data-model.md` の検証手順節(4 節のコマンド集合と exact-set。**実行結果と SHA は worklog**) | TSK-250 |

#### 旧番号 → 新番号の対応表

**除去・分割した旧番号も全部載せる**(裁定 `R-1`・`R-6`・`R-8`)。

| 旧 | 新 | 行き先 |
| --- | --- | --- |
| 1 | 1 | 本タスク |
| 2 | — | **TSK-342** |
| 3 | 2 | 本タスク |
| 4 | 3 | 本タスク |
| 5 | 4 | 本タスク |
| 6 | 5 | 本タスク |
| 7 | 6 | 本タスク |
| 8 | 7 | 本タスク |
| 9 | 8 | 本タスク |
| 10 | 9 | 本タスク |
| 11 | — | **TSK-342** |
| 12 | — | **TSK-342** |
| 13 | — | **TSK-342** |
| 14 | **10**(分割) | **`D4` の永続化写像だけ本タスク** / 残りは **TSK-342** |
| 15 | — | **TSK-342** |
| 16 | **11**(分割) | **復旧世代・`RG1`・`I6` の永続化写像だけ本タスク** / 残りは **TSK-342** |
| 17 | — | **TSK-342** |
| 18 | 12 | 本タスク |
| 19 | 13 | 本タスク |
| 20 | — | **TSK-342** |
| 21 | 14 | 本タスク |
| 22 | — | **TSK-342** |
| 23 | 15 | 本タスク |
| 24 | 16 | 本タスク |
| 25 | — | **TSK-342** |
| 26 | 17(**一部**) | 本タスク。**`contracts/legacy-columns/` 資産の paths 登録は TSK-339** |
| 27 | 18 | 本タスク |
| 28 | 19 | 本タスク |

**`R-6` の除外**: 記録権世代の**生成アルゴリズム・物理形式**は新ステップ 10・11 にも
TSK-342 にも入れない — 論点 17 の受け取り先が持つ。

#### 写像ステップの許可入力集合

**この集合の外にある資料を 88 列写像の根拠に使わない。**(TSK-335 のステップ 4・裁定 `R-9`)
**見出しに旧ステップ番号を入れない** — 再採番後の対応は `#### 旧番号 → 新番号の対応表` で解決する。

| 入力 ID | 出所 | digest / 版の参照先 |
| --- | --- | --- |
| `IN-01` | **TSK-271 `research.md` の `DM-LG-*` 16 件の判定**(同書 1 節) | `research_blob_sha` = `59cb50fca6fdbcc045c5604f935c415e6d16b90a`(TSK-271 worklog に記録) |
| `IN-02` | **TSK-271 `research.md` の `DM-LX-*` 6 件の判定**(同書 3 節。**`LX-01`・`LX-02` は `DL` precedence の射程外で「不明」**) | 同上 |
| `IN-03` | **TSK-271 `research.md` のセンチネル全 88 列表**(同書 2 節) | 同上 |
| `IN-04` | **TSK-271 `research.md` の座標の確定式**(同書 4 節 — 付録 B-5 の確定式。x 恒等・y 反転) | 同上 |
| `IN-05` | **TSK-334 の値の採否**(列 44 球種 / 列 86-87 末尾 4 集計 / 列 63-71 の行き先) | TSK-334 の裁定記録(Notion コメント。**採否 ID と決定日で引く**) |
| `IN-06` | **要件書 付録 D-1** — 列名・順序・型(`config.py` の `COLUMN_NAMES` の固定コピー)と**意味欄 4 項目** | 要件書の版(同書 変更履歴表) |
| `IN-07` | **`docs/legacy/research/data-layer.md`** — **`evidence` としてのみ**参照する(`normative` 0 件)。引用は `記号:行` | 版固定アーカイブ(`docs/legacy/` は変更禁止) |
| `IN-08` | **TSK-342 の `docs/design/data-model.md`** — **新スキーマの物理実体名**(= 「行き先」の値域) | 同書の安定 ID(節番号ではなく安定 ID で引く) |

**依存の向きは一方向**(`R-9`): **本タスクが値を決め、TSK-339 が器(`contracts/legacy-columns/` の
JSON・schema・lock・検査器)を作る。** 本タスクは TSK-339 の完了を待たない。
**`IN-08` だけが TSK-342 待ち**であり、それは本タスクの開始条件そのものである。

### 確定ゲート(ステップ 19 完了後 — 表外手順)

1. `plan.md` の `status` を `in-review` へ / 索引と本書の frontmatter を `in-review` へ
2. **開始条件(機械検査)**: **欠陥台帳の全件(ベースライン + 追記分)が `resolved` で
   `closure_evidence` を持ち、`owner_step` が有効**(2 周目 P1-10 を採用。**`WAIT-01`〜`08` は
   TSK-342 の射程へ移した** — 裁定 `R-1`)。**`owner_step` の有効値は `S1`〜`S19` または
   `TSK-342`**(**素の数値は無効** — 旧番号との数字の衝突を構文で落とす)。**群ごとの許可集合は
   4 節の群写像が正**であり、`owner_steps_allowed` はそれと一致していること。**TSK-342 所有の群は
   取り込んだ `closure_evidence` で `resolved`** になっていること、
   かつ **`check_doc_profiles.py --profile scripts/design_relations/profiles/data-model.json` が終了 0(22 件 `pass`)**
3. `codex_run.py review adversarial` で**本 PR の全差分を一括検証**(文書・プロファイル・レジストリ entry・各台帳・
   マニフェスト・独立資産 4 本・CI・**設計書 10.1 の `docs-lint` 行**の差分を含む。**設計書 5.1 の差分は
   TSK-342 の確定ゲートの対象** — 裁定 `R-5`)
4. 指摘を採用/不採用に分類して反映。**反映周ごとに 1 コミット**(件名に `反映<r>周目`。ステップ番号を
   割り当てない)。**`確定ゲート周回` を +1**
5. **反映周コミットは文書の変更に限る** — コードや台帳の修正が要るなら `status` を `active` へ戻し、
   **承認済み実装ステップを追加してから**直す(**`pins` の更新を伴う変更は必ずこちら**)
6. **人間の逐行確認**(コア領域)— **意味照合台帳の各行と参照先**、**`AUTH-*` の対応表**、
   **`FORB-*` の別名・暗黙関係**、**レジストリ entry の `pins` と `must_require`**、
   **`direct-requirements` / `auth-ddl-map` / `product-ddl-map` の実値**、
   **88 列写像の全 88 行(各行の根拠 `IN-01`〜`IN-08` を含む)**、
   **`D4`・復旧世代・`RG1`・`I6` の永続化写像**を対象に含む(裁定 `R-6`・`R-9`)。
   確認者・日付・対象 commit・結果・範囲を worklog へ
7. 逐行確認で欠陥が出たら手順 3 へ戻る
8. **停止条件**: 2 周連続で「直近の是正が原因の P0/P1」が増えた領域は切り出す。ただし
   **必須 DoD 領域(`AUTH` / `FORB` / 欠陥台帳 / 88 列写像 / 永続化写像)で発火した場合は approved にしない** —
   **`status` を `active` のまま停止し、切り出した後続タスクのマージを再開条件とする**。
   射程変更には**計画書の再レビューと人間承認**を要する(2 周目 P0-8 を採用)
9. **人間承認** → `approved`・版数確定・変更履歴追記・索引を `approved` へ
10. approved 化コミットに対して 4 節のコマンド集合を再実行し、結果と最終 SHA を worklog へ記録する

## 5. DoD(受け入れ基準)

**Notion タスク TSK-250 の DoD を、本計画の承認と同時に「先行タスクの確定成果を取り込む」形へ書き換える**
(人間の裁定 2026-08-31)。

**開始条件**(満たすまでステップ 1 に着手しない)— **裁定 `R-3`(2026-09-08)でタスク単位から
成果単位へ改めた**:

- [ ] **[TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)(データモデルのスキーマ本体と
      ORM 導入)の完了** — `docs/design/data-model.md` が**新設され 7.3 の確定ゲートを通って `approved`**
      になっていること。**本タスクは同書へ加筆する側**に立つ(裁定 `R-1`・`R-2`・`R-5`)
- [x] **先行タスク A**(文書検査機構の多文書対応)がマージ済み — **PR #42 / `fdda374`(2026-09-04)**。
      1 節の受け渡し契約は **1〜4 充足・5 は裁定 (b) により改訂**(実入力契約は本計画で固定する)
- [ ] **[TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)(先行 B の第 2 群・第 3 群)の完了** —
      B は **TSK-270 の第 1 群(契約と前提の凍結・PR #33)だけがマージ済み**で、成果の
      `contracts/authz/ddl-elements.json` は **`status: candidate_probe_only` / `product_schema: false` /
      `second_group_approval_required: true`** の**候補 probe 資産**である。**「B がマージ済み」では
      開始条件を満たさない。** **通った構成と `AUTH-*` カタログ + テスト ID** が確定していること、
      **`scope.product_schema` の真偽**(= `product_ddl_map` の要否)を開始条件で確定する
- [x] **先行タスク C**(88 列と旧資料矛盾の**事実判定**)がマージ済み — **PR #48 / `196627ec`(2026-09-07)**。
      **C は 88 列写像 JSON を作らない**(2026-09-07 の PO 裁定で射程が「判定 22 件 + 調査メモ」へ縮小)。
      **写像の値は本タスクが決める**(裁定 `R-9`)
- [ ] **[TSK-334](https://app.notion.com/p/3d493b75e6878176bf75dcbdd70d35b9)(旧資料矛盾の値の採否)の完了** —
      列 44 球種 / 列 86-87 末尾 4 集計 / 列 63-71 の行き先。**`#### 写像ステップの許可入力集合` の
      `IN-05`** として受ける
- [ ] **本改訂に対する人間の再承認** — **TSK-335 による射程改訂(受け渡し契約の改訂・スキーマ + ORM の
      切り出し・ステップ表の再採番)の完了後に、新しい日付・承認者で `承認: 済` へ**。
      **2026-09-08 に `承認: 未` へ戻した**(TSK-335 計画レビュー 3 周目 `#8`)。
      **過去の承認**: 初回 2026-08-31 / 再承認 2026-09-04・山田正輝(A の申し送り 24 項目の反映)

**「本番パス検査ステップ(新 19)の実行前に TSK-339 の完了を要する」開始条件は置かない**(裁定 `R-8`)。
**依存の向きは本タスク → TSK-339 の一方向**であり、本タスクは TSK-339 を待たない。

#### 開始条件を変えた理由と、統制の空白の扱い

**理由**(裁定 `R-3`): 2026-08-31 の判断は開始条件を「**A・B・C がすべてマージ済み**」という
**タスク単位**で書いていた。しかし ① **B はマージ済みでも成果が候補 probe 資産**であり(第 1 群だけ)、
② **C はマージ済みでも写像 JSON を作らない**(PO 裁定で射程が縮小)。**マージの有無と成果の確定は
別の事実**だった。→ **成果単位**(`approved` になった正本 / 確定した資産 / 採否の決定)へ改めた。

**統制の空白**: **A(TSK-269)の新資産 33 件は、A のマージ(2026-09-04)から本タスクの
ステップ 1(`guard_paths` 登録)までのあいだ core-guard の対象外**である。**本改訂で開始条件に
TSK-342 の完了が入ったため、この期間はさらに延びる。**

| 扱い | 内容 |
| --- | --- |
| **短縮しない** | ステップ 1 を前倒しして単独 PR にすると、**本タスクの計画外の変更**になる(AGENTS.md 絶対規則 5)。**ステップ 1 は本タスクの最初の独立コミットのまま**にする |
| **代替統制** | 空白期間中に A の 33 件を変更する PR が出た場合、**core-guard は発火しない**。→ **その PR のレビュー時に必須チェック行を手動付与する**(設計書 6.3 の代替統制 3 と同型) |
| **記録** | 空白の開始日(2026-09-04)・想定終了(本タスクのステップ 1)・**期間中に 33 件へ触った PR の一覧**を worklog へ残す |
- [ ] **本改訂に対する人間の再承認** — **TSK-335 による射程改訂(受け渡し契約の改訂・スキーマ + ORM の
      切り出し・ステップ表の再採番)の完了後に、新しい日付・承認者で `承認: 済` へ**。
      **2026-09-08 に `承認: 未` へ戻した**(TSK-335 計画レビュー 3 周目 `#8`)。
      **過去の承認**: 初回 2026-08-31 / 再承認 2026-09-04・山田正輝(A の申し送り 24 項目の反映)

**本タスクの受け入れ基準**:

- [ ] **`docs/design/data-model.md` へ加筆**し、**加筆差分**について設計書 7.3 の確定ゲートを通す
      (**新設と最初の `approved` 化は TSK-342** — 裁定 `R-1`。**新設のゲートで加筆分は担保されない**)
- [ ] **ベースライン欠陥 78 件 + 追記分**が全件 `resolved` で `closure_evidence` を持つ。
      **本タスク所有分**(`DM-LG-*` 16 / `DM-LX-*` 6 / `DM-SY-*` の永続化写像側)は本タスクが閉じ、
      **TSK-342 所有分は取り込んだ `closure_evidence` で閉じる**(`owner_step` = `TSK-342` を明示)
- [ ] **`FORB-01`〜`FORB-04` の構造が本書に存在しない**(`forbidden-structure` — 別名・暗黙関係を含む構造検査 +
      `cross-consistency` + 人間の逐行確認)
- [ ] **`AUTH-*` が TSK-317 の確定成果と exact-set で一致**し、テストの無い主張が 0 件
      (**成果 ID と blob digest を照合**する — 開始条件で確定した `AUTH-*` カタログ)
- [ ] **88 列すべてに意味欄 4 項目**(実際の中身 / 旧コードの参照箇所 / 新スキーマの行き先 / 変換規則)
      **と欠損時規則**があり、**各行の根拠が `IN-01`〜`IN-08` のいずれか**である(**集合外の資料を
      根拠に引いた行が 0 件** — 裁定 `R-9`)
- [ ] **`.claude/core-areas.json`** — **A の新資産 33 件を `guard_paths` へ登録**(ステップ 1)し、
      `data-migration` の `paths` を充填(**`contracts/legacy-columns/` 資産の登録は TSK-339** — 裁定 `R-8`)、
      5 領域すべてに本正本を登録する
- [ ] **契約 5 の 4 保証を本タスク側で機械化する**(裁定 (b) — 申し送り 24):
      `forbidden-structure` / `attribution-direct` / `baseline-digest` / `cross-consistency` が
      **実プロファイルで有効(`required_checks` = 全 22・`must_require` = 全 22)かつ green**、
      **それぞれに負例(red)がある**
- [ ] **レジストリ entry の `pins`**(`profile_gating_digest` / `invariants_digest` / `asset_digests`)が
      最終 commit の実値と一致し、**`asset_digests` が必須検査に対応する資産をすべて覆う**
- [ ] **`D4`・復旧世代・`RG1`・`I6` の永続化写像**が本文にある(裁定 `R-6`)。
      **生成アルゴリズム・物理形式の記述が 0 件**(`R-6` の除外 — 論点 17 の受け取り先が持つ)
- [ ] **本番移設とレジストリ登録(= CI 配線)**が済み、**設計書 10.1 の `docs-lint` 行**が現行化されている
      (裁定 `R-8`。**ORM 条項は TSK-342**)
- [ ] **台帳の H-12 の事象欄が `core-areas.json` の実値と一致**し、**H-78・H-79 に本タスクの実績行がある**
      (**`H-*` の新規採番が 0 件**)
- [ ] **検証手順が本書に収録**され、**実行結果と SHA は worklog にある**(本書に実行結果を書かない)

## 6. テスト計画

**本タスクは文書とその検査データが成果物であり、DB テストは先行タスク B の射程**である。

| 種別 | 足すもの | 置き場 |
| --- | --- | --- |
| **単体**(a) | プロファイル・入力主張母集合・関係マニフェスト・欠陥台帳・受け取り台帳・禁止構造台帳・**独立資産 4 本**の検査、**および負例 10 件**(関係を 1 件落とす / 入力主張を 1 行落とす / 全件「対象外」/ 禁止構造を別名で作る / WAIT を FORB 対象の関係で解消する / digest の改変 / AUTH が FORB の参照方向を使う / **`auth_ddl_map` の `structures` 脱落** / **`product_ddl_map` の domain 欠落** / **`direct_requirements` と claims の不一致**) | `tests/` |
| **単体**(a) | **交差検査**(`WAIT` → 存在 / `AUTH` → 二段階射影で存在 / `WAIT`・`AUTH` ∩ `FORB` = ∅)の正常系と衝突負例 | `tests/` |
| **単体**(a) | **fail-closed**(1 節 契約 3 の各条件で終了 2)・**`pins` 不一致**・**完全分割違反**・**必須 pin の欠落** | `tests/` |
| **単体**(a) | `test_ci_wiring.py`(**本番レジストリへの登録**)・`test_core_guard.py`(**A の新資産 33 件**・5 領域への登録・本タスクの新資産での発火) | `tests/` |
| **越境テスト**(b) | **本タスクでは足さない** — 先行タスク B の射程。**HTTP 404 の判定は Phase 4 の API テストへ送付** | — |
| **一致性**(c)・**E2E**・**故障系**(d) | **本タスクでは足さない**(ベクタは TSK-235/236/237、実装は Phase 4)。**故障系の注入点が定義できる配置**は **TSK-342 の旧ステップ 15** の合格条件で担保する(裁定 `R-1`) | — |

**変異テストの方針**(申し送り 18): **行スコープの宣言 = 別行移動**、**節スコープの宣言 = 別節移動・意味部欠落・ID 交換**、
**`row-selector` = needle 語・識別子を別行へ分散させて選択行を不成立にする**、**`exact-set` = 別 relation を同一マニフェストに置く**。
**旧述語と同値でない変異(意味反転・主述交換)は使わない**(A の design 2-1 節の変異集合が唯一の正)。

**文書側の検証**: 表間伝播検査・要件帰属の全数検査・意味照合台帳・行番号引用の残存検査・参照分類の検査。
いずれも**本番レジストリへの登録による引数なし列挙で** CI で常時実行する(ステップ 16)。

## 履歴

#### 履歴(改訂前の記述)

**本節は operative な記述ではない。** TSK-335 による改訂で置き換えた記述を、追跡のために逐語で残す
(4 節 検査 ① が本節を除外して走る)。

| 改訂日 | 場所 | 改訂前の逐語 | 置き換えた理由 |
| --- | --- | --- | --- |
| 2026-09-08 | 1 節 受け渡し契約表 C 行 | 88 列すべての 保存元 / 変換 / 欠損時規則 / 逆変換可能性 の確定 | 裁定 `R-4` — 要件書 付録 D-1 の意味欄 4 項目(実際の中身 / 旧コードの参照箇所 / 新スキーマの行き先 / 変換規則)へ接続し直した。`保存元` `欠損時規則` は D-1 の語彙に無く、`逆変換可能性` は要件のどの条項にも紐づかない |
| 2026-09-08 | 2 節 やること 5 | 先行タスク C の成果(88 列の行き先表)を本文へ写像する | 「行き先表」は要件書・TSK-271 の成果物名のいずれにも存在しない呼称。成果物の実体は `column_index = 0..87` をキーにした **88 列写像 JSON** |
| 2026-09-08 | 4 節 実装ステップ表 ステップ 12(**旧 18**) | \| 18 \| **88 列の写像**(`LG-01`〜`LG-16`・`LX-01`〜`LX-06`)— **先行タスク C の 88 列写像 JSON**(`column_index = 0..87`)を本文へ写像する。**本タスクでは裁定しない** \| **`column_index` 0〜87 の全行が本文にあり、C の JSON と 4 項目 + 共通正規化 ID で exact-set 一致**(**C の blob digest を照合し、一致しなければ fail**)/ **本文の記述のうち C の JSON に無い値が 0 件**(再解釈の機械検出)/ **`docs/legacy/` が `normative` として参照されていない**(`reference-class` で `evidence` のみ)/ 伝播検査(累積)green \| | 裁定 `R-9` — **C(TSK-271)は 88 列写像 JSON を作らない**(2026-09-07 の PO 裁定で射程が「判定 22 件 + 調査メモ」へ縮小され、写像 JSON は TSK-250 が所有することになった)。よって「C の JSON と exact-set 一致」「C の blob digest を照合」は**入力が存在しない**。かつ TSK-339 の開始条件が「TSK-250 のマージ」であるため**循環していた** |
| 2026-09-08 | 2 節 やること(全 10 項目) | ### やること ⏎  ⏎ 1. **`docs/design/data-model.md` の新設**と設計書 7.3 の確定ゲート通過(`/finalize-doc`) ⏎ 2. **同期プロトコル正本の決定を本文へ写像**する — 矛盾 15 件・欠落 20 件・書き換え 5 件 ⏎ 3. **`WAIT-01`〜`WAIT-08`**(同期正本が本書の確定を待つ 8 件)を個別に閉じる ⏎ 4. **先行タスク B の成果(認可構成と `AUTH-*` カタログ)を本文へ写像**する ⏎ 5. **先行タスク C の成果(88 列写像 JSON)を本文へ写像**する ⏎ 6. **要件由来の裁定の反映**(導出 5 件・FR-030・管理者操作ログ) ⏎ 7. **典拠の全件貼り替え**と**要件帰属表**・**意味照合台帳** ⏎ 8. **設計書 5.1 の追随** — **ORM = SQLAlchemy 2.x / ドライバ = psycopg 3 / マイグレーション = Alembic** ⏎    に確定する(**人間の裁定 2026-08-31**。値を計画で固定し、実装者が選ばない) ⏎ 9. **`.claude/core-areas.json`** — **A の新資産 33 件の `guard_paths` 登録(最初の独立コミット)**、 ⏎    `data-migration` の `paths` 充填、本タスクの新資産追加 ⏎ 10. **データモデル用プロファイル一式の作成**(A の機構に対する実入力契約 — 裁定 (b)): ⏎     プロファイル・宣言資産・`structure_extractors`・`collection_sets`・独立資産 4 本・**レジストリ entry の `must_require` = 全 22 と `pins`** | 裁定 `R-1`〜`R-9` — 送り先を実 ID で確定し、TSK-342 / TSK-339 / TSK-334 / TSK-317 所有の項目を除去した。旧 1(新設 + 確定ゲート)→ 加筆 + 加筆差分のゲートへ / 旧 5(C の成果を写像)→ 許可入力集合だけを根拠に決める(`R-9`)/ 旧 8(設計書 5.1)→ TSK-342 / 本番移設と台帳更新を明示的な項目として立てた(`R-8`) |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 2(**除去**) | \| 2 \| **素材の移送・索引・fixture の固定** — `docs/design/data-model.md` を新設し候補案 1〜12 節を移送(**変更は相対リンクの解決のみ**)+ frontmatter 3 行・変更履歴表(`0.1`/`draft`)。**同一コミットで** 索引 1 行 + fixture と SHA-256 \| `check_docs_status.py` green / **相対リンクの参照先がすべて実在** / **相対リンク以外の本文が候補案と一致**(diff)/ **13 節が存在しない** / **fixture が本文とバイト一致し SHA-256 が一致** \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 11(**除去**) | \| 11 \| **順序系の写像**(`C01`〜`C05`・`C08`)+ **`WAIT-05`**(U-7 の D1/D2 用途分離)— 用途対応表・6-2 節・**12-3 節(移行)**の 4 箇所すべてで境界・起点を **D2** へ改め、**到着順の語を全廃**する。**同型の残存を一括で直す**(台帳 H-79 の教訓) \| **該当 4 箇所を逐行照合**し結果を worklog へ / **禁止語(到着順・受信順)が 0 件** / **`WAIT-05` が `resolved` になり物理要素と closure evidence が記録されている** / 伝播検査 `--defects`(該当 ID)green \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 12(**除去**) | \| 12 \| **削除経路の分離**(`C06`・`M06`)— 確定済み記録の修正・削除を**変更イベント(参加区分 #10〜#12)**として実体化し、墓標・改訂の流用記述を撤去する \| **#10〜#12 に対応する実体・属性・制約がある** / **「正は墓標・改訂イベント」が 0 件** / 伝播検査(累積)green \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 13(**除去**) | \| 13 \| **識別子と一意性**(`M01`〜`M04`・`M07`・`M08`・`M17`)+ **`WAIT-03`**(D2 の数値型)— D2 の列・部分一意・索引の禁止、V10 の複合参照列、V11 と確定版列を物理写像として置く \| **`(試合, D4, D1)` の部分一意がある** / **D2 に不変前提の索引を張らない旨が索引原則にある** / **`WAIT-03` が `resolved`(数値型と根拠が本文にある)** / 伝播検査(累積)green \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 14(**分割**) | \| 14 \| **一意範囲・連続性・世代**(`C09`・`C10`・`C13`)+ **適用水位・履歴文脈・楽観ロック**(`C11`・`C12`・`C14`)+ **`WAIT-01`**(D3 の物理表現)\| **D5 の一意範囲が `(テナント, D5)`** / **D1 の連続性が新規割り当てに限られる** / **D4 が非再利用として表現されている** / **`WAIT-01` が `resolved`(物理表・列・後退禁止の表現)** / **意味規則の再記述が 0 件**(ステップ 10 の検査)/ 伝播検査(累積)green \| | 裁定 `R-6`。**永続化写像だけを本タスクの新ステップ 10** として残し、**残りは [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** へ送った |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 15(**除去**) | \| 15 \| **原子境界と結果保持**(`M05`・`M09`・`M10`・`M15`・`M18`・`M20`)+ **`WAIT-06`**(U-8 構造側)・**`WAIT-08`**(9-2 境界表 17 行の永続化写像)\| **P1〜P5 と T1〜T9 の対応表がある** / **拒否原本が受理済み行と混ざらない** / **9-2 境界表の 17 行すべてに物理写像がある**(exact-set)/ **`WAIT-06`・`WAIT-08` が `resolved`** / 伝播検査(累積)green \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 16(**分割**) | \| 16 \| **退避と復元**(`C07`・`C15`・`C16`・`M11`〜`M14`・`M16`・`M19`)+ **`WAIT-02`**(退避の列定義)・**`WAIT-04`**(U-3 構造側)— 復旧世代・RG1・I6 と退避原本の区別・端末キュー状態 4 種・保持期間の器を置く。**`C16`: 候補案 8-2-B の管理関数クラス (c) から「取り込み」を分離**し、現版で許可する「閲覧・書き出し」だけを残す \| **`FORB-01`〜`04` の構造がいずれも存在しない**(`forbidden-structure` — **別名・暗黙関係を含む** + `cross-consistency`)/ **管理関数の記述に「取り込み」が残っていない** / **`WAIT-02`・`WAIT-04` が `resolved`** / 伝播検査(累積)green \| | 裁定 `R-6`。**永続化写像だけを本タスクの新ステップ 11** として残し、**残りは [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** へ送った |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 17(**除去**) | \| 17 \| **キャッシュ無効化の物理化**(`B01`〜`B05`)+ **`WAIT-07`** — **同期側のトリガー ID を参照**し、本書は**物理的な無効化先**だけを決める \| **要件の 14 トリガーが全数対応づいている**(**招待の失効を含めない**)/ **在籍区分変更が入っている** / **発火条件の再記述が 0 件** / **`WAIT-07` が `resolved`** / 伝播検査(累積)green \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 20(**除去**) | \| 20 \| **要件由来の写像**(`RQ-01`〜`RQ-09`・`SP-01`〜`SP-06`)— **計画承認前に得た裁定**(5 節)を反映し、FR-030・管理者操作ログ・6.1 超過実体の 3 群分け・検証可能条件を落とす。禁止事項 6 件を判定する \| **`RQ-*` 各件に裁定 ID・決定者・決定日・反映節・closure evidence がある** / **FR-030 と管理者操作ログが独立した行として閉じている** / **`SP-01`〜`06` に判定と該当節があり、各判定が構造不変条件に対応づいている** / 伝播検査(累積)green \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 22(**除去**) | \| 22 \| **典拠の識別子参照化** — 行番号引用 3 形式を識別子参照へ置換し、**旧参照 → 新安定 ID の対応表を資産として固定**する。参照を `normative` / `evidence` / `informative` に分類する(`reference_policy` は順序付き first-match・未一致は終了 2) \| 残存検査 green / **対応表が全置換を覆い、置換前後の規範の同一性判定が行ごとに記録されている** / **規範参照に feature・worklog・Notion・legacy が 0 件** / **`normative` のリンク先がすべて `status: approved`** \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
| 2026-09-08 | 4 節 実装ステップ表 旧ステップ 25(**除去**) | \| 25 \| **設計書 5.1 の追随** — **ORM = SQLAlchemy 2.x**・**ドライバ = psycopg 3**・**Alembic** を確定し、留保文言を除去。変更履歴表へ 1 行(**版は上げない**)。**本差分は `/finalize-doc` の対象** \| `check_docs_status.py` green / **5.1 の 3 行が計画の固定値と exact-set 一致** / **「設計フェーズで最終確定」が残っていない** / **B の DDL 要素表が使うドライバ・接続方式が固定値と一致**(digest 照合。「矛盾しない」ではなく**両者の値の一致**で判定する) \| | 裁定 `R-1`(`R-2`・`R-5` を含む)。**送り先 = [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)** |
