---
feature: vocab-category-fk
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-06・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ef93b75e687812aaa6dc32c63cde291
branch: feature/vocab-category-fk
created: 2026-10-05
計画レビュー周回: 4        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: system_vocabularies の FK に category 強制を入れる(TSK-480)

> ## 計画レビューの経過(`codex_run.py review adversarial`)
>
> | 周 | 判定 | 何が変わったか |
> | --- | --- | --- |
> | **1**(2026-10-06) | 否決 `P0`1 / `P1`4 / `P2`2 — **全件反映** | **受入シートの既定の再生成は判定欄を全部消す** → `--carry-judgments-from HEAD` + 空行の全件拾い + 人間の承認(4-4)/ 事前検査の試験を 3 参照元ごと・FORCE で隠れる行・正常系・往復へ強化(ステップ 2)/ **操作の順序を固定**(列追加のロックの後に検査 — 4-2)/ 最終ステップに DB 全件の再実行 / 着地条件の申し送り(4-7)/ DML 走査の範囲の記述 / 変異に MATCH と列順 |
> | **2**(2026-10-06) | 否決 `P0`0 / `P1`3 / `P2`1 — **全件反映** | **`--carry-judgments-from HEAD` は `HEAD..HEAD` で差分が空になり持ち越しの安全判定が働かない** → 仮コミット + ステップ開始時の HEAD を基準 + amend(4-4)・変更した 4 表の持ち越し行も人間に示す / 着地条件を**各単位の開始条件として固定**してもらう(4-7)/ ステップ 3 を 1 委任 → 検証 → 1 コミットに(4-6)/ テスト計画の番号 |
> | **3**(2026-10-06) | 否決 `P0`0 / `P1`2 / `P2`1 — **全件反映** | **委任の途中に仮コミットを挟めない** → シート再生成は委任から外し Claude がコミット後に行う(4-4)/ U-M1 への反映確認を**ステップ 1 の着手条件**に・TSK-479 / U-G1 のカードのコメントを現在有効な条件と明記(4-7)/ PR 後の develop 取り込みは追随ステップを足して新コミット(4-4) |
> | **4**(2026-10-06) | 否決 `P0`0 / `P1`2 / `P2`0 — **全件反映** | ステップ表 3 の委任対象を digest だけに統一(表と 4-4・4-6 の食い違い)/ **ステップ記法に総数 `/<N>` を付けない**(追随ステップの追加で公開済みコミットが不正記法になる) |
> | **5**(2026-10-06・収束確認) | **承認可** `P0`0 / `P1`0 / `P2`1 | 4-6 の「コミット前に人間の承認」を「amend を確定する前に」へ字面合わせ(周回数は増やさない) |

## 1. 背景・目的

- **Notion**: [TSK-480](https://app.notion.com/p/3ef93b75e687812aaa6dc32c63cde291)(起票元 TSK-475 のステップ 8)。調査: [research.md](research.md)
- **問題**: `system_vocabularies` の主キーは `key` 単独で、`category` は CHECK だけの列。参照側の FK 3 本は `key` だけを参照し **`category` を拘束しない**(`backend/migrations/versions/0010_vocabularies_settings.py:98-142`)。
  TSK-475 が在籍区分 `active` / `other` / `ob` を投入した時点で **`games.game_type_key = 'active'` が DB を通る**(`docs/design/data-model.md:2021-2027` の ⚠ 項が事実として記録)
- **要件**: 語彙の 3 層 [4.0-3](../../requirements/requirements-pitchlog-2026-07-22.md#4.0-3)(試合区分 = 公式戦〜その他 / 在籍区分 = 現役・その他・OB を**別の区分**として定める)・試合区分を使う [FR-001](../../requirements/requirements-pitchlog-2026-07-22.md#FR-001) / [FR-014](../../requirements/requirements-pitchlog-2026-07-22.md#FR-014)・在籍区分の [FR-017](../../requirements/requirements-pitchlog-2026-07-22.md#FR-017)。**要件書は語彙キーの一意性の範囲を定めておらず、改訂は不要**(research.md 1 節)
- **目的**: 区分違いのキーを参照列に入れられないことを **DB の制約で**保証する。**着地条件**(カードの DoD・data-model:2025-2026): 「試合区分の seed(TSK-479)」と「`games` / `game_type_rule_defaults` を含む全参照元の書き込み開始」の**いずれよりも前**。依存として待つ単位: U-M1(TSK-393・選手の入口の前)/ U-G1(TSK-395)/ TSK-479

## 2. スコープ

### やること

1. **新しい migration `0029_system_vocab_category_fk`**(down_revision = `0028_tenant_login_identity`):
   - 参照先 `system_vocabularies` に `UNIQUE (key, category)`(`uq_system_vocabularies_key_category`)を足す。**主キー `(key)` は残す**
   - 参照側 3 表に **category 固定の定数列**を足す(既定値 + NOT NULL + `CHECK (列 = '定数')`):
     `players.roster_status_category = 'roster_status'` / `games.game_type_category = 'game_type'` / `game_type_rule_defaults.game_type_category = 'game_type'`
   - FK 3 本を**同じ名前のまま**複合 FK へ張り替える: `(…_key, …_category) → system_vocabularies (key, category)`・`MATCH FULL`・`ON DELETE NO ACTION`
   - 既存行の不整合を張り替えの前に検出する**事前検査**(0028 の `_reject_existing_rows` と同じ作法)
   - downgrade は逆順に、**同じ名前の単列 `MATCH SIMPLE` FK** へ戻し、列と UNIQUE を外す
2. ORM モデル(`SystemVocabulary` / `Player` / `Game` / `GameTypeRuleDefault`)と `contracts/db/schema-manifest.json` を migration に一致させる
3. 既存テストのうち FK の形を固定しているものの追随と、**負例・正例・事前検査・往復の DB テスト**の追加
4. ORM 受入突合シートの再生成(manifest の列が変わるため)
5. 正本 `data-model.md` 10-3 節の ⚠ 項を**是正済みの記録へ書き換える**(実装追随・版据え置き)+ 変更履歴 + 索引 + digest 2 件の取り直し

### やらないこと

- **`system_vocabularies` の主キーを `(category, key)` へ変えること・3-4 節の一意性の表(:399・:407)の改訂**(【裁定 2026-10-06】— research.md「判断点 A」)
- **`admin_vocabularies`(FK 4 本)・`tenant_vocabularies`(FK 7 本)の同型の非拘束**(【裁定 2026-10-06】射程は system 層 3 本 → **TSK-489** へ起票済み)
- 試合区分の seed とキー名(TSK-479)。**試合区分の「その他」は在籍区分の `other` と同じキーにできない**(主キーが `key` 単独のまま — 本タスクでも変わらない)ことを TSK-479 へ申し送る
- 新列の不変性の分類(3 表とも `coverage: partial`・引き取り先 TSK-372 のまま。**`protected_columns` へ入れるとトリガが要り射程が広がる** — research.md 3 節)
- トリガ関数・DB 関数の新設・変更(作ると製品 authz 資産一式が連動する — research.md 3 節)
- 移行バッチ・製品の入口の変更(移行バッチは未実装。定数列は既定値で埋まるので、列を省いた INSERT は無変更で通る)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 10-3 節(:2021-2027 の ⚠ 項) | 「構造的に可能になる」の記録を、**是正済み**(migration 0029・定数列 + 複合 FK・`MATCH FULL`)の記録へ書き換える。**主キー・3-4 節の表・FK の書き方の規約は変えない** | **PR レビュー**(7.6-3 前段の実装追随・版据え置き — 【裁定 2026-10-06・山田正輝】。⚠ 項自身の「確定ゲートを要する」と TSK-475 裁定の当てはめを**今回は採らない**ことを人間が裁定した) |
| `docs/design/data-model.md` 変更履歴 | 実装追随(TSK-480・版は上げない)の追記 | PR レビュー |
| `docs/README.md`(索引) | data-model 行へ実装追随の追記 | PR レビュー |
| `docs/requirements/` | **反映なし**(一意性の範囲を定める条文が無い — research.md 1 節) | — |
| `docs/adr/` / `docs/development/` / `docs/ops/` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの

| 資産 | 変更 |
| --- | --- |
| `contracts/db/schema-manifest.json` | 4 表の列・CHECK・一意構造・FK の追記と、`canonical_source.sha256` の取り直し |
| `contracts/authz/shared-preconditions.json` | data-model.md の `git_blob_digest` の取り直し |
| `docs/features/orm-schema-migration/acceptance-sheets/*` | 生成器での再生成と判定欄の記入 |

## 4. 実装方針

### 4-1. 型 — 定数列 + 参照先 UNIQUE + `MATCH FULL` の複合 FK

前例は D5 台帳(`0005_sync_events.py:60-65,83` / `0007_idempotency_originals.py:40-96` / ORM `sync_protocol/models.py:199-210,260-262,375-380` / manifest :327,:347,:502)。

| 要素 | 内容 | 理由 |
| --- | --- | --- |
| 参照先 | `UniqueConstraint("key", "category", name="uq_system_vocabularies_key_category", info={"roles": ("fk_target",)})`。manifest は `"roles": ["fk_target"]`・`"verification": "カタログ照合"`・`source_row` なし | `business_unique` を付けると 3-4 節の全数表と `test_schema_audit.py:762-776` の固定件数に掛かる。前例 `uq_idempotency_ledger_kind`(manifest :502)は fk_target だけ |
| 定数列 | `sa.Text()`・`server_default=sa.text("'<category>'")`・`nullable=False` + `CheckConstraint("<列> = '<category>'")`(0005 と同じ**名前なし** CHECK) | NOT NULL + `MATCH FULL` で NULL による照合省略を塞ぐ(orm-schema-migration/design.md:305-323)。既定値があるので**列を指定しない既存の INSERT はそのまま通る**(product_authz の試験ケース・移行バッチ) |
| 複合 FK | 同名で drop → create。`match="FULL"`・`ondelete="NO ACTION"`・`info={"cross_tenant": False}` | 名前で検査する既存テスト(`test_roster_status_seed_db.py:225-323`)を壊さない。0028:153-167 の手順 |
| **生成列は使わない** | — | FK に生成列を使った前例が無く、`test_game_state_models.py:132-140` が `Computed` を拒否する |

**列名**: `players.roster_status_category` / `games.game_type_category` / `game_type_rule_defaults.game_type_category`(参照列 `<x>_key` と対にする)。

### 4-2. 事前検査(upgrade の中)と操作の順序

**upgrade の順序を固定する**(計画レビュー 1 周目 `P1-2`): ① 参照先へ `UNIQUE (key, category)` ② 参照元 3 表へ定数列と CHECK を追加(`ALTER TABLE … ADD COLUMN` が各表の `ACCESS EXCLUSIVE` ロックを取り、migration のトランザクションの終わりまで保持する)③ 事前検査 ④ FK 3 本の同名張り替え。**ロックを取った後に検査する**ので、検査と張り替えの間に不整合行が入る余地が無い(0028 も列追加の後に検査している — 0028:123)。

張り替えの前に、**区分の合わない既存行**を検出して止める。対象: `players.roster_status_key` が `roster_status` 以外のキーを指す行 / `games.game_type_key` と `game_type_rule_defaults.game_type_key` が `game_type` 以外を指す行。
- **作法は 0028 の `_reject_existing_rows`(0028:22-102)と同じ**: `DO` ブロックで対象 4 表の `relforcerowsecurity` を読み、FORCE なら検査の間だけ `NO FORCE` にして全行を見て、`RAISE EXCEPTION '0029 の事前検査に失敗: …'` で止め、元の FORCE 状態へ戻す(FORCE 下の FK 初期検証は所有者の不可視行を見落とし得る — 0028:42-44・worklog 2026-10-04-ua1-auth-db-layer.md:239)
- **DML 禁止検査に掛からない**こと: `SELECT` と `RAISE` と `ALTER TABLE … [NO] FORCE ROW LEVEL SECURITY` だけで書く(`test_migration_hygiene.py:26-39` が拒否する `INSERT INTO` / `UPDATE … SET` / `DELETE FROM` を、**Python の文字列リテラル**〔docstring と SQL 文字列の中のコメントを含む — 同 :784〕で使わない。通常の Python コメントは走査対象外)
- 既存行への埋め戻しは要らない(定数列の既定値で全行が埋まる)。**埋まった値と参照キーの区分が合わない行は、FK 作成でなく事前検査で先に止める**(エラー文言を固定して試験できるようにする)

### 4-3. 往復と head 前提のテスト

- downgrade は **FK を同名の単列 `MATCH SIMPLE` へ戻す → 定数列を外す(CHECK は列と一緒に消える)→ UNIQUE を外す**。0028 の downgrade と同じ順序の考え方
- head を前提にした既存テストのうち、`test_alembic_migrations.py:8400-8456`(0028 までの upgrade で authz カタログ ok)と `:8270`・`:8458-8526`(head → 0027 の downgrade を FORCE RLS 下で実行)は、**0029 が関数・ACL を持つ物体を作らない**ので形の上では影響しない。**ステップ 1 で実際に回して確かめる**(推論で済ませない)
- `test_alembic_migrations.py:4260-4323` は 3 FK の `confmatchtype = 's'` を固定している → **検査がどの revision の時点かを読み、head 時点なら `'f'` と列の組へ追随させる**

### 4-4. 正本の書き換えと digest の取り直し(**最後のステップに置く**)

- data-model.md を触るのは**最終ステップだけ**にし、digest 2 件(`schema-manifest.json` の `canonical_source.sha256` = `sha256sum` / `shared-preconditions.json` の `git_blob_digest` = `git hash-object`)は**そのステップでその時点の内容から取り直す**。**値を先に測って計画書や申し送りへ焼き込まない**(TSK-475 で片方だけ直して CI が落ちた — roster plan.md:879-923)
- **PR を出した後に develop を取り込む必要が生じたら**(3 周目 `P2-1`)、公開済みのステップ 3 を amend しない(force push 禁止)。**計画書を改訂して追随用のステップ(4 以降)を足し、新しいコミットで** digest の取り直し・シートの再生成(4-4)・DB 全件の再実行を行う
- **TSK-382(feature/real-schema-meaning)が data-model.md を v0.6 で改訂中**(確定ゲート 4 周・PR 未作成 — 2026-10-06 実測)。**先にマージされた側の data-model.md を後から入る側が取り込み、digest を取り直す**。本 PR が後になったら、develop 取り込みの後に最終ステップをやり直す(取り込みは 1 回だけ・できるだけ遅く)
- 受入突合シートは正本の本文と節参照を含むので、data-model.md の変更後に再生成する(N1 / N3 / N7 — 生成器が対象を決める)
- **受入突合シートは判定を持ち越して再生成する**(計画レビュー 1 周目 `P0-1`・2 周目 `P1-1`)。**既定の再生成は判定欄と理由欄を全部空にする**(`acceptance-sheets/README.md:11`・`generate_orm_acceptance_sheets.py:1166`)。**持ち越しの安全判定は `<基準>..HEAD` のコミット済み差分から変更識別子を拾う**(同 :1077-1096)ので、**未コミットの変更は見えず、`HEAD` を基準にすると差分が空になり検査が働かない**。手順を次に固定する:
  1. **Codex**(委任)がシート以外の変更を終える。**シートの再生成は委任に含めない**(3 周目 `P1-1` — コミットは Claude の担当で、委任の途中に仮コミットを挟めない — `.claude/skills/implement/SKILL.md:33`)
  2. **Claude** が委任の結果を検証し、**ステップ記法つきの件名で**ローカルにコミットする(push しない)
  3. **Claude** が `uv run python scripts/generate_orm_acceptance_sheets.py --carry-judgments-from <ステップ開始時の HEAD>` で再生成する(変更識別子が 2 のコミットの差分から拾われる)
  4. **Claude** が引き継ぎ・判定案を作り、**人間の承認**を受け、シートと期待行数の追随を 2 のコミットへ amend する(1 ステップ = 1 コミット。**amend は push 前に限る**)
  
  そのうえで**空になった行を全件**拾い、`(対象から通し番号を除いたもの, 正本側, 実装側)` の内容一致で旧判定を引き継げる行は引き継ぎ、新規の行には既存の同種の行と同じ判定案を入れる。**持ち越された行のうち、対象が本タスクで変えた 4 表(`players` / `games` / `game_type_rule_defaults` / `system_vocabularies`)または 10-3 節に当たる行も全件**、空になった行と合わせて人間に示す。**引き継ぎと判定案は人間の承認を受けてから amend を確定する**(前例: TSK-468 — worklog 2026-10-04-ua1-auth-db-layer.md:173,:221)。行数が変わったら `tests/test_orm_acceptance_sheets.py` の期待行数を追随させる。**develop 取り込み(TSK-382 など)の後は N3 の通し番号がずれるので、同じ手順をやり直す**

### 4-5. 重さ分類 = **コア領域**

- 触るパスのうち `backend/migrations/*`・`backend/tests/db/*`・`contracts/db/schema-manifest.json`・`docs/design/data-model.md` は **5 領域すべての paths** に一致(`.claude/core-areas.json:138-139,159` ほか)。`db/tenant_isolation/*` はテナント分離(:359)、`db/game_state/*` は状況計算(:211)
- 意味範囲(設計書 6.3 の境界定義表)はスキーマ FK の拘束を名指ししないが、「迷えば含む側に倒す」(6.3 :400)。**TSK-475 も同じ当てはめでコア領域にした**(roster plan.md:470-485)
- → ADR-001「コア領域の実装」行(ラッパーが固定)・計画と PR の敵対レビュー・**人間の逐行確認**
- **paths の宣言の追加は不要**(新規ファイルは既存 glob `backend/migrations/*`・`backend/tests/db/*` に入る)

### 4-6. 実装の担当

- ステップ 1〜2 は Codex へ委任(`codex_run.py implement`)
- **ステップ 3 も 1 委任 → 検証 → 1 コミット**(2 周目 `P1-3` — 設計書 6.1 :313・`/implement` 手順)。順序: ① **Claude が** data-model.md 10-3 節 ⚠ 項・変更履歴・`docs/README.md` を書く(ドキュメントは Claude の役割 — CLAUDE.md。委任先は同じ worktree の未コミット編集を読める)② **Codex へ委任**: digest 2 件の取り直し ③ Claude が検証してステップ記法つきでコミットし(= 4-4 の 2)、**その後に 4-4 の 3〜4**(シートの再生成・人間承認・amend)を行う。Claude が書いた部分は `codex_run.py review normal` を通す(前例: TSK-468 ステップ 11 — worklog 2026-10-04-ua1-auth-db-layer.md:172)
- 受入突合シートの判定欄は 4-4 の手順で Claude が引き継ぎと判定案を作り、**amend を確定する前に人間の承認を受ける**(README :3「判定・理由と典拠は人間が記入する」)。**ここは実装の途中で人間の手が要る点**

### 4-7. 着地条件の申し送り(計画レビュー 1 周目 `P1-4`)

カードの依存欄(U-M1 / U-G1 / TSK-479 → TSK-480)は Notion に張ってあるが、**U-M1 の計画書は入口を開くステップ 8 の前提に TSK-480 を挙げていない**(um1 plan.md:253 付近・research.md「未解決」)。**申し送るだけでは足りない**(2 周目 `P1-2` — 入口が先に開くと、マージ直前の確認では回復できない)。**各単位の側で開始条件として固定してもらう**: U-M1 = 計画書の外部依存表に TSK-480 を足し、**ステップ 8(入口)の着手条件**に「TSK-480 が develop に着地済み」を入れる(UM01 タブへ依頼済み 2026-10-06 → **反映を確認済み 2026-10-06**: `origin/feature/um1-player-roster-opponent` の U-M1 計画書 外部依存表 :115〔dep 10〕・着手の拘束 :258〔ステップ 8 以降は dep 10 = TSK-480 の develop 着地後〕)。**反映の確認を本計画のステップ 1 の着手条件にする**(3 周目 `P1-2` — 反映が無ければ実装に入らず人間へ上げる)/ TSK-479・U-G1 = 計画書がまだ無いので、Notion の依存欄(TSK-480 へのメンション — 張り済み)を**計画作成時に着手条件として取り込む**旨を各カードへコメントした(2026-10-06 — TSK-479 には「その他」のキーの件も併記)。**コメントは「TSK-480 の develop 着地前は seed / 書き込みに着手しない」という現在有効な条件として書いてある**(どちらもまだ計画書もブランチも無い — 着手する者が最初に読むのはカード)。U-M1 の `players` への INSERT は列を明示しており(um1 `backend/src/pitchlog/repositories/roster.py:300`)、**定数列の既定値があるのでコードの変更は要らない**ことも併せて伝える。**PR 作成時とマージの直前**に 3 単位の状態(U-M1 の計画書に条件が入ったか・ステップ 8 未着手か / TSK-479 の seed 未着地か / U-G1 の書き込み未開始か)を再測し、PR に記録する(DoD 1 項目目)。**条件が入っていない単位があれば、本 PR のマージ前に人間へ上げる**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**ステップコミットの件名は `(ステップ <k>)` とし、総数 `/<N>` を付けない**(4 周目 `P1-2`)。PR 後に追随ステップを足すと(4-4)、公開済みコミットの `/3` が表の総数と食い違い、`scripts/feature_status.py:517` が不正と判定するため(書き換えは force push になる)。前例: U-M1 計画書 :255。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **(着手条件: U-M1 計画書への TSK-480 の反映を確認済み — 4-7)** **migration 0029 と、それに一致させる ORM・manifest・既存テスト・受入シート**: 4-1〜4-3 の migration(UNIQUE・定数列 3・CHECK 3・事前検査・FK 3 本の同名張り替え・downgrade)/ ORM 4 モデル / `schema-manifest.json` の 4 表(**`canonical_source` は触らない**)/ FK の形を固定している既存テストの追随(`test_alembic_migrations.py:4260-4323` ほか、実行して落ちたもの)/ 受入シートを 4-4 の手順(Codex の委任はシート以外まで → Claude がコミット → ステップ開始時の HEAD を基準に持ち越し再生成 → 人間承認 → amend)で再生成し、空になった行と変更 4 表の持ち越し行の引き継ぎ・判定案を作る**→ 人間の承認** | `backend/` で `uv run ruff check` / `uv run ty check` / **`uv run pytest -c pyproject.toml --cov` の全件 green(使い捨て postgres に DSN を向けて DB テストを含める)**・`alembic upgrade head` / `current --check-heads` / `check` が通る / リポジトリルートの `uv run pytest tests/` が green(`test_orm_acceptance_sheets.py` を含む)/ `test_migration_hygiene.py` が green(DML 禁止に掛からない)/ 受入シートの判定を人間が承認済み(worklog に記録) |
| 2 | **新しい DB テスト**(`backend/tests/db/test_system_vocab_category_fk_db.py`・`requires_db`): head で ① 在籍区分キーを `games.game_type_key` へ・試合区分キー(試験用に投入)を `players.roster_status_key` へ・在籍区分キーを `game_type_rule_defaults.game_type_key` へ入れると **`fk_*` の名前で ForeignKeyViolation** ② 定数列へ別の値を明示すると CheckViolation・NULL を明示すると NotNullViolation ③ 区分の合う参照は通る(列を省いた INSERT で既定値が入る)④ **事前検査(参照元 3 表それぞれ)**: 製品 authz を適用した使い捨てクラスタで、0028 の時点に**所有者から FORCE RLS で隠れる**区分違いの行を 1 表ずつ置き、0029 への upgrade が**その表を名指す事前検査の文言**で止まること・行が残ること・revision が 0028 のままであること・4 表の FORCE 状態が元に戻っていることを確かめる(既存の 0028 の試験 `test_alembic_migrations.py:8270`・`:8400` を型にする)⑤ **FORCE 下の正常系**: 区分の合う行だけがある状態で 0029 への upgrade が通り、製品 authz カタログの検査が ok のまま ⑥ 0029 ⇄ 0028 の往復で FK が単列 SIMPLE ⇄ 複合 FULL に戻り、`command.check` が通り、製品 authz カタログが維持される | 新テストが green / **変異で red になることを Claude が自分で再現**: (a) FK を単列へ戻すと ① が red (b) CHECK を外すと ② が red (c) 事前検査の 3 分岐を**1 つずつ**外すと、それぞれ対応する ④ が red (d) `MATCH FULL` を `SIMPLE` にすると・FK の参照列の順序を崩すと、既存の `test_schema_audit.py`(列順と MATCH を読む — :417)が red。再現の記録を worklog に残す / `backend/` の全件 green |
| 3 | **正本の書き換えと凍結点**(正本は Claude が書く・**委任は digest 2 件の取り直しだけ**・シートは委任後に Claude — 4-4・4-6): data-model.md 10-3 節 ⚠ 項を是正済みの記録へ / 変更履歴(実装追随・版据え置き)/ `docs/README.md` の data-model 行 / `schema-manifest.json` の `canonical_source.sha256` と `shared-preconditions.json` の `git_blob_digest` を**この時点の data-model.md から**取り直す / 受入シートの再生成(4-4 の手順・**人間の承認**)。**このステップは develop の最後の取り込みの後に行う**(4-4)| `scripts/check_shared_preconditions.py` と `test_schema_manifest.py::test_manifest_is_bound_to_the_canonical_data_model` が green / `tests/test_orm_acceptance_sheets.py` が green / `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/` が green / **最後の取り込みと digest 取り直しの後に、`backend/` の全件(DB を含む・`uv run pytest -c pyproject.toml --cov`)と `alembic upgrade head` / `current --check-heads` / `check` を再実行して green**(計画レビュー 1 周目 `P1-3`)/ `codex_run.py review normal` の指摘を反映済み |

## 5. DoD(受け入れ基準)

Notion カードの DoD と同期(2026-10-06 の裁定で「7.3 の確定ゲート」を PR レビューへ変更 — カード側も同日に追随させる):

- [ ] **着地条件**: 「試合区分の seed(TSK-479)」と「`games` / `game_type_rule_defaults` を含む全参照元の書き込み開始」のいずれよりも前に develop へマージされている(マージ時に TSK-479 と U-M1 / U-G1 の状態を測って PR に記録する)
- [ ] 3 FK すべてが `(…_key, …_category) → system_vocabularies (key, category)` の `MATCH FULL` 複合 FK になっている(manifest・ORM・実カタログが一致 — `test_schema_audit.py` green)
- [ ] **在籍区分のキーを `game_type_key` へ入れられないこと**を実 DB で検査している(TSK-475 ステップ 7 で書けなかった検査)。逆向き・`game_type_rule_defaults` も同様
- [ ] 事前検査・往復・定数列の CHECK / NOT NULL の負例が実 DB で green で、変異で red になることを再現済み
- [ ] data-model.md 10-3 節の ⚠ 項が是正済みの記録になり、変更履歴・索引・digest 2 件が追随している
- [ ] 正本ゲート: 実装追随として PR レビュー(【裁定 2026-10-06・山田正輝】)。コード: 計画と PR の敵対レビュー + 人間の逐行確認
- [x] TSK-479 へ「試合区分の『その他』は `other` 以外のキーにする」ことを申し送っている(Notion コメント 2026-10-06)

## 6. テスト計画

| NFR-019 の種別 | 足すもの |
| --- | --- |
| 単体 | なし(ORM と manifest の一致は既存の `test_tenant_models.py` / `test_game_state_models.py` / `test_schema_manifest.py` が検査する — 追随のみ) |
| 一致性 | 既存の `test_schema_audit.py`(manifest ⇔ 実カタログの完全一致)が新しい列・CHECK・UNIQUE・FK を検査する。受入突合シート(`tests/test_orm_acceptance_sheets.py`) |
| 越境 | **新規**: 区分をまたぐ参照の拒否(ステップ 2 ①)。テナント越境ではなく**語彙の区分の越境**。既存の product_authz 試験は列を省いた INSERT のまま green であることを確認する |
| E2E | なし(入口が無い) |
| 故障系 | **新規**: 事前検査が不整合な既存行で止まり FORCE 状態を戻す(ステップ 2 ④)/ 往復(⑥)・FORCE 下の正常系(⑤)/ 定数列の CHECK・NOT NULL(②) |

- **実行範囲**: backend は CI と同じ `uv run pytest -c pyproject.toml --cov` で**全件**を回す(影響範囲で絞ると選び落としが見えない — TSK-475 の誤報)。共有開発 DB は使わず**使い捨ての postgres**(`postgres:17.11-bookworm`)に `PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN` を向ける。`docker compose down -v` は使わない
