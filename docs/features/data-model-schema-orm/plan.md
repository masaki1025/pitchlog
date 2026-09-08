---
feature: data-model-schema-orm
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7
branch: feature/data-model-schema-orm
created: 2026-09-08
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: データモデルのスキーマ本体と ORM 導入(TSK-250 の先行)

## 1. 背景・目的

**Notion タスク**: [TSK-342](https://app.notion.com/p/3d593b75e68781958074ed04dff7dab7)(高)
**前タスク**: [TSK-335](https://app.notion.com/p/3d493b75e687817eb966e0b5511ebd31)([PR #49](https://github.com/masaki1025/pitchlog/pull/49) マージ済み `f0eeae1`)
**要件**: `FR-038`(移行)/ `FR-015`(選手登録)/ `NFR-010`(テナント分離)/ `NFR-005`(性能規律)/
`NFR-014`(シークレット)/ `NFR-018`(ドメイン計算の単一実装)/ `4.0-2`(物理削除しない)/ 7.1(技術制約)
**下調べ**: [research.md](research.md)(488 行・全事実に典拠)

### なぜやるか

**`backend/` に DDL・マイグレーション・ORM が皆無で、製品コードは `GET /health` の 11 行しか無い**
(research.md 0 節)。データモデルの正本も存在せず、候補案
`docs/features/product-data-model-design/design.md`(1,866 行)は**一時作業域に置かれたまま**である。
**本タスクが「backend に実コードが入る最初のタスク」**であり、
[TSK-330](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b)(同期サーバー適用の実装)と
[TSK-250](https://app.notion.com/p/3c593b75e6878152b3edd6cf4f26b30b)(データモデル設計の正本化)の
**両方が本タスクの完了を開始条件にしている**。

### なぜ独立タスクか

TSK-250 の承認済み計画を表どおり実行すると**後段のステップが前段と同じ成果物を再変更する**構造だった。
**人間の裁定 2026-09-08(`R-1`・`R-2`・`R-5`)**により、
**① スキーマ本体(RLS の設計判断とテーブル制約を含む)② 設計書 5.1・10.1 の改訂 + 機械検査の更新
③ `models`・`migration`・依存追加とテスト**の 3 群が本タスクへ切り出された。

### 人間の裁定(取得済み — 2026-09-08・山田正輝)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **A-1** | `game_lineup_snapshot`(最終オーダーのスナップショット)の受け皿を作るか | **作る。** 要件書 `FR-038`(approved)が名指しで「別に保全する」と要求している。`DL` の precedence は **88 列の意味に限定**されテーブル一覧は射程外。旧側に存在しなくても害はない(移行 0 件で終わる) |
| **A-2** | 「実スキーマ適用後に越境テストを再実行するゲート」は誰が持つか | **定義は本タスク・実行は後。** 本タスクは「誰が・何に対して・いつ回すか」を**正本と DoD に定義**し、**`migration` はテーブル・制約・テナント列まで**を作る。**RLS ポリシーとロールの DDL・越境テストの実行は TSK-317 の実機確定後へ送る**(裁定 `R-1`「DDL の実機確定だけ TSK-317 を待つ」と一致)。**越境テスト自体がまだ存在しない**(TSK-270 第 1 群は DB テスト基盤まで。正例・拒否例・DDL 適用器は TSK-317 第 2 群 — 未着手)ため、本タスクに実行を入れると閉じられない |
| **A-3** | 移行バッチの書き込み経路 | **移行バッチ専用ロールへ `BYPASSRLS` を与える。** 所有者バイパスに頼らないので、**全テーブルに `FORCE ROW LEVEL SECURITY` を掛けたまま移行できる**。候補案 3-2 は「所有者がバイパス」と書きながら同節で `FORCE` を推奨しており**内部矛盾していた**(research.md 6-4)。probe の実測も同方向(`bypass_rls: true` は外部 `provisioner` と関数所有 2 ロールのみ) |
| **A-4** | `NFR-018` (b)③「動的コード生成の禁止」は ORM の実行時 SQL 生成に及ぶか | **及ばない。** 条文の適用範囲は (b)「宣言と機械判定」= **対象計算の出所・実行入口・派生関係**であり、ORM の実行時 SQL 生成は対象外と読む。**判定の根拠を本書 4 節に書き、確定ゲートの敵対レビューに掛ける** |

## 2. スコープ

### やること

1. **`docs/design/data-model.md` の新設**(候補案 1〜12 節を素材に移送)+ **`REQ:<行>` 引用 286 件を安定 ID 参照へ貼り替え** + 索引登録
2. **RLS を防御層とする設計判断の明文化**と、そこから導出される**テーブル制約**(テナント内一意 + 複合 FK)
3. **裁定 A-1・A-3 の反映** — `game_lineup_snapshot` の保全先 / 移行バッチ専用ロールへ `BYPASSRLS`(所有者バイパスの記述を除去)
4. **`WAIT-01`〜`WAIT-08` の物理表現**を本文へ(`WAIT-04` の**保持期間そのものは要件改訂待ち**として除く)
5. **設計書 5.1 の ORM 留保の解除**(SQLAlchemy 2.x / psycopg 3 / Alembic)+ **10.1 の「ORM は入れない」の改訂** + **`test_psycopg_is_exact_product_dependency_without_orm_packages` の更新** + **依存追加**(**同一コミット**)
6. **SQLAlchemy models** + **正規化層**(`0` / `"0"` / 空文字 / NULL を吸収 — 旧資料自身の推奨)+ テスト
7. **Alembic migration**(テーブル・制約・テナント列。**RLS ポリシー / ロール DDL は含まない** — 裁定 A-2)+ テスト
8. **越境テスト再実行ゲートの定義**と**送り先の起票**(裁定 A-2)
9. **`.claude/core-areas.json` へ本タスクの新設資産を登録**(6.3 規則⑤)
10. **7.3 の確定ゲート通過**(`/finalize-doc` — 正本の新設)

### やらないこと

| 対象外 | 受け取り先 | 理由 |
| --- | --- | --- |
| **RLS ポリシー・ロールの DDL の実機確定**(`BYPASSRLS` / `NOLOGIN` / 関数 ACL / `search_path` / `FORCE RLS` の組合せ) | **[TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)** | 裁定 `R-1`「DDL の実機確定だけ TSK-317 を待つ」。本タスクは**設計判断**を書く |
| **越境テストの実行**(実スキーマに対する再実行) | **本タスクが起票する送り先**(裁定 A-2) | **越境テスト自体が未作成**(TSK-317 第 2 群) |
| **88 列写像の値**(行き先・変換・逆変換可能性) | **TSK-250** | 2026-09-07 の PO 裁定で TSK-250 が所有。本タスクは**受け皿(物理実体名と型)を用意する側** |
| **記録権世代の生成アルゴリズム・物理形式** | **論点 17 の受け取り先**(実装計画 = 同期・記録権の最初の実装タスク) | 裁定 `R-6` の除外。**本タスクにも入れない** |
| **`WAIT-04` の保持期間そのもの** | **要件改訂タスク** | **要件書に行が無い**(同期正本 11-4 U-3)。9-4 も「保持期間そのものは決めない」と明記 |
| **`waiting-data-model.json` の `resolved` 記録** | **TSK-250**(新ステップ 6) | 資産の新設は TSK-250 の射程。本タスクは**本文に物理表現を書く**まで |
| **`data-model` プロファイル・レジストリ entry の作成** | **TSK-250**(新ステップ 3・16) | 文書検査機構への登録は TSK-250。→ **本タスクは `check_citation_format` を単発で呼んで自前で検査する**(4 節 検査 ①) |
| **要件書の改訂** | 要件改訂タスク | AGENTS.md 絶対規則 4。**本タスクで踏む要件は無い**(research.md 3 節で `FR-015` の衝突が成立しないことを確認) |
| **候補案 13 節・未解決メモの移送** | — | TSK-250 の `DM-MT-01` が **`absent-section: "13"`** で**正本に 13 節が無いこと**を検査する |
| **(β) 集計クエリの実装** | Phase 4 の実装タスク | **ORM で人手記述すると `NFR-018` (a) が発火する**(4 節)。本タスクは `models` と `migration` に限る |
| **索引の具体形・事前集計の採否** | 実装期の性能実測 | `NFR-005` は「毎球参照画面に限り採用可」とし具体形を定めない |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| [`docs/design/data-model.md`](../../design/data-model.md) | **新設**(`0.1` → `in-review` → `approved`)。候補案 1〜12 節を素材に移送し、**引用を安定 ID 参照へ貼り替え**、RLS の設計判断・テーブル制約・裁定 A-1/A-3 の反映・`WAIT-*` の物理表現・越境テスト再実行ゲートの定義を持たせる | **finalize-doc**(7.3 — **正本の新設**) |
| [`docs/development/dev-harness-design-2026-08-07.md`](../../development/dev-harness-design-2026-08-07.md) | **5.1 の ORM 留保を解除**(SQLAlchemy 2.x / psycopg 3 / Alembic)+ **10.1 の「ORM は入れない」箇条を改訂**。変更履歴表へ 1 行。**版は上げない** | **PR レビュー**(7.6-3 前段)。**ただし差分は本タスクの確定ゲートの敵対レビュー対象に含める**(裁定 `R-5` の折衷形) |
| [`docs/README.md`](../../README.md)(索引) | **設計正本の行を新設**(`draft` → `approved`)+ 設計書の最終更新日を現行化 | —(常に現行化 — 7.2) |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `contracts/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `backend/src/pitchlog/db/**`(**新設**) | SQLAlchemy models + **正規化層** |
| `backend/migrations/**`(**新設**) | Alembic migration(テーブル・制約・テナント列) |
| `backend/pyproject.toml` / `backend/uv.lock` | **`sqlalchemy` / `alembic` の追加**(psycopg の厳密固定は維持) |
| `backend/tests/**` | models・正規化層・migration のテスト |
| `tests/test_ci_wiring.py` | **`test_psycopg_is_exact_product_dependency_without_orm_packages` の更新** |
| `.claude/core-areas.json` / `tests/test_core_guard.py` | **本タスクの新設資産を paths へ登録**(6.3 規則⑤) |
| `docs/features/data-model-schema-orm/{plan,research}.md` / `docs/worklog/2026-09-08-data-model-schema-orm.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域(テナント分離・データ移行・記録権)**

設計書 6.3 の境界定義表がテナント分離に「認可境界・テナント列・越境経路」、データ移行に
「`FR-038` の全体」、記録権に「世代の永続化」を含める。
**本タスクはスキーマ本体そのもの**であり、意味範囲上 3 領域に該当する。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須**。

### 機構の発火判定 — **今回は core-guard が発火する**(前 2 タスクと違う)

変更ファイルを base 側 `core-areas.json` に突合した結果:

| ファイル | 該当 |
| --- | --- |
| `backend/pyproject.toml` / `backend/uv.lock` / `backend/tests/db/*` | **`tenant-isolation.paths`** に登録済み |
| `tests/test_ci_wiring.py` | **`guard_paths`** に登録済み |
| **`docs/design/data-model.md`**(新設)/ **`backend/src/pitchlog/db/**`**(新設)/ `backend/migrations/**`(新設) | **どの領域の paths にも無い** |

→ **PR テンプレの必須チェック行は自動付与され、CI の core-guard が `- [x]` を機械検査する。**
→ **新設資産は 6.3 規則⑤で paths へ登録する**(ステップ 8。**登録しないと H-12 の再発になる**)。
**`tenant-isolation` に該当するので、テンプレの adversarial レビュー項目も有効化される。**

**TSK-250 への申し送り**: T250P の新ステップ 17 は「既存 4 領域へ本正本を追加」を持つ。
**`docs/design/data-model.md` の登録は本タスクが行う**ので、**T250P 側は重複しないよう再承認時に調整する**。

### 設計判断 1 — **RLS を防御層として採る**(要件からは導出されない)

**要件書・改善台帳に `RLS` は 0 hits**(research.md 2-1 で独立に再確認)。
`NFR-010` が課すのは**結果**(内容・存在を含め参照できない)・**適用範囲**(初日から全機能)・
**検証**(自動テスト)だけで、**実現層を指定していない**。改善台帳 `I-2` が指名する手段は `team_id` 列。
→ **これは本タスクが決める設計判断である。**

**採る理由**(候補案 3-1 の消去法 + 要件条項):

1. **7.1「標準 PostgreSQL の範囲で使用し、ホスティング固有機能に依存しない」** — RLS は PostgreSQL 9.5 の
   コア機能なので**採ってよい**。**Supabase の認可機能に寄せる案は禁止事項 `P-04` 違反**で採れない
2. **`NFR-010`「テナント分離は初日から全機能に適用する」** — アプリ層のみの強制は、
   管理画面・バッチ・将来のリポジトリ層・手書き SQL で条件を落とすと隔離を失う。
   **旧システムがまさにその状態だった** — テナント境界は `game.owner_team_id` 1 列 + アプリ層ガードのみで、
   **所有権チェックはオプショナル引数で省略すると全データにアクセス可能**だった(research.md 5-2)
3. **`NFR-019(b)` の越境テストが「API 直叩きを含む全経路」を要求**する — DB 側に既定拒否があれば
   経路の追加漏れが構造的に塞がる

**この判断の帰結(避けられない)**: **一意制約と外部キーは RLS を必ず貫通する**
(PostgreSQL 公式 `ddl-rowsecurity.html`)。`NFR-010` が「内容・存在を含め参照できない」を要求するため、
**素直に設計すると制約違反エラーが他テナントの行の存在を漏らす**。
→ **テナント内一意 + 複合 FK + 制約違反詳細の一律秘匿**が従属して決まる(候補案 3-4)。
**要件単独からは導かれない**(research.md 2-5)。

### 設計判断 2 — **`NFR-018` (b)③ は ORM の実行時 SQL 生成に及ばない**(裁定 A-4)

**条文の適用範囲**: `NFR-018` (b) は「**宣言と機械判定**」であり、(b)③ の「動的機構の禁止」は
**対象計算の出所・実行入口・派生関係の宣言**に対する検査である。
**`NFR-018` の対象は本項の列挙が正**(達成条件 (d))= 「状況判定・座標変換・捕球選手推定・
成績集計の前処理・終了判定」で、**`models` と `migration` はどれにも当たらない**(research.md 4-3)。
→ **及ばないと判定する。要件書に適用範囲の明示が無い点は「不明」として記録し、確定ゲートの敵対レビューに掛ける。**

**ただし発火点が 1 つ残る**: **(β) の集計クエリを ORM で人手記述する段で `NFR-018` (a)
「人手で保守する実装は 1 系統」が発火する**。→ **本タスクの射程外**(2 節)。
**この境界を `docs/design/data-model.md` に明記する**(ステップ 4 の合格条件)。

### 検査(**機械 4 本に絞る** — 前タスクの教訓)

**前タスク(TSK-335)は計画レビュー 3 周・成果物レビュー 3 周でいずれも収束せず、
指摘の多くが「自分で書いた bash 検査の欠陥」だった**(台帳の候補「計画レビューに終端条件が無く…」へ実測を追記)。
→ **機械検査は「既存機構が検査主体を持つ」か「負例で red になることを本計画の中で実測済み」のものだけに絞る。**
**すべての検査に「是正前の実測値」を併記する。**

```bash
# 本ブランチの worktree で実行する
D=docs/design/data-model.md
C=docs/features/product-data-model-design/design.md

# ---- ① 引用形式(可変正本への行番号引用が 0 件)----
#    ※ check_design_propagation.py は**レジストリ駆動**で、現在の登録は sync-protocol 1 本だけ
#      (実測)。`data-model` プロファイルの作成は TSK-250 の射程なので、**本タスクは
#      check_citation_format を単発で呼んで自前で検査する**(登録待ちにすると腐ったまま通る)
uv run python -c "
import importlib.util, sys, pathlib
spec = importlib.util.spec_from_file_location('cdp','scripts/check_design_propagation.py')
m = importlib.util.module_from_spec(spec); sys.modules['cdp']=m; spec.loader.exec_module(m)
print('正本  :', m.check_citation_format(pathlib.Path('$D').read_text(encoding='utf-8')))
print('候補案:', m.check_citation_format(pathlib.Path('$C').read_text(encoding='utf-8')))
"
# → 正本 = ()  /  候補案 = ('REQ:<行番号>', '<パス>.md:<行番号>', '裸の行番号')
#   **是正前の実測**: 候補案に 3 形式すべてが検出される(= 負例が現物として存在する)

# ---- ② 文書検査(既存機構)----
uv run python scripts/check_docs_status.py                # → rc=0
uv run python scripts/check_design_propagation.py         # → rc=0(レジストリ列挙)
uv run python scripts/check_doc_coverage.py               # → rc=0
#   **是正前の実測**: 3 本とも rc=0(= 番人型。正本を新設して索引へ載せ忘れると ① で落ちる)

# ---- ③ ORM 検査の更新(ステップ 4 以降)----
uv run pytest tests/test_ci_wiring.py -q                  # → green
#   **是正前の実測**: green(旧形 = sqlalchemy/alembic が lock に無いことを確認している)
#   **ステップ 4 の途中で必ず red になる**(依存を足すと旧形の assert が落ちる)ため、
#   **10.1 の改訂・テストの更新・依存追加は同一コミットにする**

# ---- ④ 品質ゲート(ステップ 5・6)----
#    harness / backend / frontend の 3 層(/check 相当)
#    **是正前の実測**: backend の DB 必須テスト 3 件は PITCHLOG_TEST_ADMIN_DSN /
#    PITCHLOG_TEST_ROLE_DSN 未設定の環境要因で fail-closed に落ちる既知事象(CI では実行される)
```

**`[手動・外部]` に置くもの**(機械判定しない): 本文の意味の正しさ / 候補案からの移送の網羅 /
`WAIT-*` と同期正本の 1 対 1 照合 / RLS 採用の設計判断の妥当性 / 制約の形が
`NFR-010` を満たすか。**いずれも確定ゲートの敵対レビューと人間の逐行確認で見る。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**実行者を分ける**: **文書ステップは Claude が直接編集**(コード変更 0 行)。
**コードステップは `/implement` で Codex へ委任**(CLAUDE.md「実装コードは自分で書かず Codex へ委任する」)。

| # | ステップ(何を作るか) | 実行者 | 合格条件(このステップの検証方法) |
| --- | --- | --- | --- |
| 1 | **`docs/design/data-model.md` の新設と素材移送** — 候補案 **1〜12 節**を移送(**13 節と未解決メモは移送しない**)+ frontmatter 3 行 + 変更履歴表 + **`REQ:<行>` 引用 286 件を安定 ID 参照へ貼り替え**(**同一コミット** — 移送だけ先に入れると腐ったまま通る)+ `docs/README.md` へ行を新設 | Claude | `[機械]` **検査 ① の正本側が `()`**(**是正前 = 候補案に 3 形式検出**)/ **`## 13.` で始まる節が 0 件** / 検査 ② が 3 本とも rc=0。`[手動・外部]` **候補案 1〜12 節の全節が移送されている**(節見出しの集合を突合)/ **貼り替えた 286 件が指す条項が正しい**(判定者: 山田正輝) |
| 2 | **RLS の設計判断と裁定 A-1・A-3 の反映** — 4 節の「設計判断 1」を本文へ明文化 / **テナント内一意 + 複合 FK + 制約違反詳細の一律秘匿**を規則として置く / **`game_lineup_snapshot` の保全先**(裁定 A-1)/ **移行バッチ専用ロールへ `BYPASSRLS`**(裁定 A-3)。**候補案 3-2 の「テーブル所有者がバイパス」の記述を除去**し、**全テーブルに `FORCE ROW LEVEL SECURITY` を掛けたまま移行できることを明記** | Claude | `[機械]` **「テーブル所有者」+「バイパス」が同一文に現れる箇所が 0 件**(**是正前 = 候補案に 1 件**)/ **`FORCE ROW LEVEL SECURITY` と移行経路の両立が本文にある** / **`game_lineup_snapshot` の保全先が本文にある**(是正前 0 件)/ 検査 ①② green。`[手動・外部]` **RLS 採用の理由 3 点と却下案 3 件が本文にある** / **制約の形が `NFR-010` を満たす**(判定者: 山田正輝) |
| 3 | **`WAIT-01`〜`WAIT-08` の物理表現** — 8 件を本文へ書く。**`WAIT-04` は「構造側のみ・保持期間は要件改訂待ち」と理由つきで明記** / **`NFR-018` (a) の発火点**((β) 集計クエリの ORM 記述)**の境界を明記** / **記録権世代の生成方式は書かない**(`R-6` の除外) | Claude | `[機械]` **`WAIT-01`〜`WAIT-08` の 8 個の ID がすべて本文にある**(是正前 0 件)/ **「生成アルゴリズム」「物理形式」が記録権世代の文脈で 0 件** / 検査 ①② green。`[手動・外部]` **8 件が同期プロトコル正本の該当箇所と 1 対 1**(逐行照合の結果を worklog へ)/ **`WAIT-04` の理由が要件改訂待ちであることと整合**(判定者: 山田正輝) |
| 4 | **設計書 5.1・10.1 の改訂 + 機械検査の更新 + 依存追加**(**同一コミット必須** — 依存を足すと旧形の assert が落ちる)— 5.1 の ORM 留保を解除 / 10.1 の「ORM は入れない」を改訂 / `test_psycopg_is_exact_product_dependency_without_orm_packages` を新形へ(**psycopg の厳密固定は維持** + `sqlalchemy`・`alembic` が lock にあることを確認)/ `backend/pyproject.toml` + `backend/uv.lock` / 変更履歴表へ 1 行(**版は上げない**) | Claude | `[機械]` **検査 ③ が green** / **旧形の assert(`isdisjoint`)が 0 件** / **lock に `sqlalchemy` と `alembic` がある** / **psycopg の厳密固定(直接依存ちょうど 1 件・完全一致の版指定・lock と一致)が維持されている** / **負例: `sqlalchemy` を lock から外すと red**。`[手動・外部]` **5.1 と 10.1 の改訂が裁定 `R-5` の折衷形どおり**(版を上げず差分を確定ゲートの対象に含める) |
| 5 | **SQLAlchemy models と正規化層** — 論理スキーマを models へ写す。**`0`(int)/ `"0"`(str)/ 空文字 / NULL を吸収する正規化層を models の前に置く**(旧資料自身の推奨 — research.md 5-4 #3)。**`FR-015` の背番号に一意制約を置かない** | **Codex** | `[機械]` `/check` の harness・backend が green / **正規化層の負例テストが 4 形態(`0`・`"0"`・空文字・NULL)すべてを覆う** / **models に背番号の `UniqueConstraint` が 0 件** / **テナント内一意が `tenant_id` を先頭に含む**(グローバル一意が 0 件)。`[手動・外部]` **型の罠 14 件(research.md 5-4)への対処が models に反映されている**(判定者: 山田正輝) |
| 6 | **Alembic migration** — テーブル・制約・テナント列を作る。**RLS ポリシー / ロールの DDL は含まない**(裁定 A-2)。**`NFR-014`: DSN と URL 設定は環境変数から読む**(リポジトリに置かない) | **Codex** | `[機械]` **`upgrade` と `downgrade` の両方が通る** / **`CREATE POLICY` / `ALTER ROLE` / `CREATE ROLE` が 0 件**(TSK-317 待ちの明示)/ **DSN・接続文字列のリテラルが 0 件**(`NFR-014`)/ `/check` 3 層 green。`[手動・外部]` **migration が本文の論理スキーマと 1 対 1**(判定者: 山田正輝) |
| 7 | **越境テスト再実行ゲートの定義と送り先の起票**(裁定 A-2)— 「**誰が・何に対して・いつ回すか**」を本文へ書く。**RLS ポリシー / ロール DDL の実装 + 越境テストの実行**を Notion へ起票し、**開始条件を TSK-317 の完了**とする。**起票の前に必ず Notion をタスク名で検索する** | Claude | `[機械]` **本文にゲートの定義がある**(是正前 0 件)/ **本書と本文に起票した実 ID(URL 付き)がある**。`[手動・外部]` **重複起票していないこと**(検索結果を worklog へ)/ **ゲートの定義が「実スキーマに対して」「TSK-317 の資産で」回すことを一意に指している** |
| 8 | **`core-areas.json` へ新設資産を登録**(6.3 規則⑤)— `docs/design/data-model.md` を該当領域へ / `backend/src/pitchlog/db/**` と `backend/migrations/**` の**全パスを完全列挙**で登録 / **実設定を読む回帰テスト**。**TSK-250 への申し送りを worklog へ**(T250P 新 17 との重複回避) | Claude | `[機械]` `uv run pytest tests/test_core_guard.py` green / **新設資産の全パスが該当領域の `paths` に包含されている**(**`guard_paths` は完全一致集合でディレクトリ登録では発火しない** — `scripts/core_guard.py`)/ `/check` 3 層 green。`[手動・外部]` **paths 追加の敵対レビュー + 人間承認**(6.3 規則⑤・逐行確認は PR 作成者以外) |

**ステップ外ゲート(DoD で担保)**: **7.3 の確定ゲート通過**(下記)/ PR 本文の**必須チェック行**
(**今回は core-guard が自動付与し機械検査する**)と**実施記録行の記入** / Notion の DoD 現行化と PR URL 記録。

### 確定ゲート(ステップ 8 完了後 — 表外手順)

1. `plan.md` の `status` を `in-review` へ / 索引と `docs/design/data-model.md` の frontmatter を `in-review` へ
2. **開始条件(機械検査)**: 検査 ①②③④ がすべて期待値どおり
3. `codex_run.py review adversarial` で**本 PR の全差分を一括検証**(**設計書 5.1・10.1 の差分を含める** — 裁定 `R-5`)
4. 指摘を採用/不採用に分類して反映。**反映周ごとに 1 コミット**(件名に `反映<r>周目`。**ステップ記法を付けない**)。**`確定ゲート周回` を +1**
5. **反映周コミットは文書の変更に限る** — コードの修正が要るなら `status` を `active` へ戻し、**承認済み実装ステップを追加してから**直す
6. **人間の逐行確認**(コア領域)— **RLS の設計判断 / テーブル制約の形 / `WAIT-*` の 8 件 / 貼り替えた 286 件 / models の正規化層 / migration の DDL** を対象に含む。確認者・日付・対象 commit・結果・範囲を worklog へ
7. 逐行確認で欠陥が出たら手順 3 へ戻る
8. **停止条件**: **2 周連続で「直近の是正が原因の P0/P1」が増えたら人間へ 3 案を提示して打ち切る**(前タスクの実測 — 台帳の候補)
9. **人間承認** → `approved`・版数確定・変更履歴追記・索引を `approved` へ
10. approved 化コミットに対して 4 節の検査を再実行し、結果と最終 SHA を worklog へ記録する

## 5. DoD(受け入れ基準)

- [ ] **`docs/design/data-model.md` を新設し、7.3 の確定ゲートを通して `approved` にした**
- [ ] **候補案 1〜12 節を移送した**(**13 節と未解決メモは移送していない**)
- [ ] **`REQ:<行>` 引用 286 件を安定 ID 参照へ貼り替えた** — **`check_citation_format` が `()`**
- [ ] **RLS を防御層とする設計判断を明文化した**(理由 3 点 + 却下案 3 件)。**要件から導出されないことを明記した**
- [ ] **テナント内一意 + 複合 FK + 制約違反詳細の一律秘匿**を規則として置いた(**グローバル一意が 0 件**)
- [ ] **`FR-015` の背番号に一意制約を置いていない**(旧 `player` の `UNIQUE(チーム_id, 背番号)` を外す — `I-12`)
- [ ] **`game_lineup_snapshot` の保全先がある**(裁定 A-1)
- [ ] **移行バッチ専用ロールへ `BYPASSRLS` を与える形にした**(裁定 A-3)。**「テーブル所有者がバイパス」の記述が 0 件**で、**`FORCE ROW LEVEL SECURITY` と両立している**
- [ ] **`WAIT-01`〜`WAIT-08` の 8 件の物理表現がある**(**`WAIT-04` は構造側のみ・保持期間は要件改訂待ちと明記**)
- [ ] **記録権世代の生成アルゴリズム・物理形式を書いていない**(`R-6` の除外)
- [ ] **設計書 5.1 の ORM 留保を解除し、10.1 の「ORM は入れない」を改訂した**。**版は上げず、差分を確定ゲートの敵対レビュー対象に含めた**(裁定 `R-5`)
- [ ] **`test_psycopg_is_exact_product_dependency_without_orm_packages` を更新した** — **psycopg の厳密固定は維持**し、`sqlalchemy`・`alembic` が lock にあることを確認する形。**負例で red になる**
- [ ] **SQLAlchemy models と正規化層(`0` / `"0"` / 空文字 / NULL の 4 形態)がある**。**負例テストが 4 形態すべてを覆う**
- [ ] **Alembic migration の `upgrade` / `downgrade` が両方通る**。**`CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` が 0 件**(裁定 A-2)
- [ ] **`NFR-014`: DSN・URL 設定のリテラルがリポジトリに 0 件**(環境変数から読む)
- [ ] **越境テスト再実行ゲートを定義し、送り先を起票した**(裁定 A-2。開始条件 = TSK-317 の完了)
- [ ] **`core-areas.json` へ新設資産を登録した**(6.3 規則⑤の敵対レビュー + 人間承認)
- [ ] **`NFR-018` (b)③ の適用範囲の判定と、(a) の発火点((β) 集計クエリ)の境界を本文に書いた**
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**。**PR の必須チェック行は core-guard が自動付与・機械検査する**(今回は発火する)。**逐行確認は PR 作成者以外**が行い、**実施記録行を確認者本人が記入**した
- [ ] **`/check` が 3 層で green**(backend の DB 必須テスト 3 件は環境要因の既知事象)

## 6. テスト計画(NFR-019)

| 種別 | 追加内容 |
| --- | --- |
| **単体** | **正規化層** — `0`(int)/ `"0"`(str)/ 空文字 / NULL の **4 形態**と、**JSON 配列の非対称な長さ**(names 20 / poses・nums 10 / lrs 11 / score 16 — **固定長を仮定しない**)/ **TEXT 列に入る数値**(背番号・守備番号・ゾーン番号)の吸収 |
| **単体** | **models** — テナント内一意が `tenant_id` を先頭に含むこと / **グローバル一意が 0 件** / **背番号に一意制約が無い** / 複合 FK の形 |
| **単体** | **migration** — `upgrade` / `downgrade` の両方が通る / **`CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` が 0 件** / DSN リテラルが 0 件 |
| **CI 配線** | `tests/test_ci_wiring.py` の **`test_psycopg_is_exact_product_dependency_without_orm_packages` を更新**。**負例(`sqlalchemy` を lock から外す)で red** になることを確認する |
| **回帰(実設定)** | `tests/test_core_guard.py` — 新設資産の全パスが該当領域の `paths` に包含されていること(**負例: 1 パスを外すと red**) |
| **一致性 / 越境 / E2E / 故障系** | **本タスクでは足さない。** **越境テストは TSK-317 の第 2 群が作る**(裁定 A-2 — 本タスクは**ゲートの定義**まで)。一致性ベクタは TSK-235〜239。E2E・故障系は Phase 4 |

**件数のハードコードは 1 箇所に集約する** — `tests/test_check_authz_catalog.py` の期待件数ハードコードが
過去に他タスクを red にした連鎖があるため(`docs/worklog/2026-09-01-course-coordinate-contract.md`)。

## 検証(このタスクが終わったことの確認方法)

```bash
WT=../pitchlog-worktrees/feature-data-model-schema-orm

# 1. 4 節の検査 ①②③④ をすべて実行する(上記のコマンド集)

# 2. 正本の状態(索引と frontmatter が approved で一致)
uv run python scripts/check_docs_status.py

# 3. 品質ゲート一括(/check 相当)
#    harness / backend / frontend の 3 層

# 4. 正本反映の突合(3 節の宣言と差分の双方向突合)
uv run python scripts/check_plan_docs_sync.py \
  --plan docs/features/data-model-schema-orm/plan.md --base origin/develop

# 5. core-guard が新設資産にマッチすること
uv run pytest tests/test_core_guard.py
```

**人間が確認すること**: 貼り替えた 286 件 / RLS の設計判断 / テーブル制約の形 /
`WAIT-*` の 8 件と同期正本の 1 対 1 / models の正規化層 / migration の DDL。

## 進め方

1. **人間の裁定 4 件は取得済み**(2026-09-08・山田正輝)— 結果は 1 節の `A-1`〜`A-4` に記録した
2. **Notion TSK-342 の DoD を本書 5 節と逐項照合する** — 照合結果を worklog へ **3 列表**で記録し、**更新後の URL を併記**する
3. **コア領域なので敵対レビュー**: `python .claude/scripts/codex_run.py review adversarial -`
4. 指摘を反映(1 周ごとに `計画レビュー周回` を +1)→ 収束したら**人間の承認**を求める
5. **承認後**: ステップ 1〜4・7・8 は **Claude が直接編集**(文書)/ ステップ 5・6 は **`/implement` で Codex へ委任**
   (1 委任 = 1 ステップ = 1 コミット・件名は `(ステップ k/8)`)
6. **ステップ 8 完了後に 7.3 の確定ゲート**(表外手順)
