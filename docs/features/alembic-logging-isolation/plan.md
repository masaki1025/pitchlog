---
feature: alembic-logging-isolation
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-17・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3dd93b75e6878147aae9d37a76665e14
branch: fix/alembic-logging-isolation
created: 2026-09-16
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: alembic の fileConfig がアプリのロガーを無効化する問題の是正

## 1. 背景・目的

- **Notion タスク**: [alembic の fileConfig がアプリのロガーを無効化する](https://app.notion.com/p/3dd93b75e6878147aae9d37a76665e14)
- **出所**: TSK-387(U-00 API 器)の PR #67 が CI red になったことで顕在化。
  経緯は `docs/worklog/2026-09-16-u00-api-shell.md` の「CI red と是正」節。
- **調査メモ**: [research.md](research.md)

### 事実

`backend/migrations/env.py:16-17` の `fileConfig(config.config_file_name)` は Python 標準の既定
**`disable_existing_loggers=True`** で動く。`backend/alembic.ini:6-7` の
`[loggers] keys = root,sqlalchemy,alembic` に `pitchlog` 系の qualname が無いため、
**呼び出し時点で生成済みのアプリのロガーが `disabled = True` にされる**(実測)。

`fileConfig` を呼ぶのは**リポジトリ全体でこの 1 箇所だけ**(`dictConfig` / `basicConfig` はゼロ)。

**標準ライブラリの引用は関数名で行い、行番号を使わない** — 2 周目レビューで、
同じ 3.12.3 でもビルドにより `logging/config.py` の行番号がずれることが分かったため
(私の測定環境と レビュー環境で `:87`/`:198` と `:88`/`:201` に食い違いが出た)。

### 要件との関係(**過大に書かない** — [research.md](research.md) B-2)

**本件は現時点で要件違反ではない。**

- NFR-015(要件書 `:872-875`)は顕在化手段を「画面通知・**ログ**」の**選択肢**として示し、
  ログを唯一の手段と定めていない。対象も「保存・同期・バックアップ・出力の失敗」に限定される
- **アプリのプロセスは `env.py` を import しない**(`backend/src/` に `command.upgrade` /
  `lifespan` / `startup` の一致 0 件)。現に無効化が起きるのは **pytest プロセスの中だけ**

**したがって本タスクの目的は「NFR-015 違反の是正」ではなく、
「NFR-015 の顕在化経路のうちログ側が将来無効化されるのを防ぐ予防的是正」である。**

**現に起きている実害**は 1 件: TSK-387 がテスト隔離の手当て
(`backend/tests/api_fixtures.py` の `error_logger` フィクスチャ)を入れざるを得なかった。

## 2. スコープ

### やること

- `backend/migrations/env.py` の `fileConfig` へ **`disable_existing_loggers=False` を渡す**(1 行)
- **回帰テストを足す** — `backend/tests/test_alembic_environment.py` に、
  **子プロセスで** env.py を実行する検査(4 節 決定③)
- **`error_logger` フィクスチャの docstring を現況化する**(4 節 決定②)

### やらないこと

| やらないこと | 理由 |
| --- | --- |
| **ロギング方針を決めない**(出力先・形式・水準・アプリ側 logging 設定の新設) | **要件書にログの構成を定めた条項が存在しない**([research.md](research.md) B-1) |
| **`backend/alembic.ini` を変更しない**(`[loggers]` に `pitchlog` を足さない) | 4 節 決定① 案 B。ロギング方針が未決の段階で alembic.ini がアプリのログ水準を決めるのは筋が悪い |
| **`fileConfig` による既存ハンドラの close は扱わない** | `_clearExistingHandlers()` は **`disable_existing_loggers` の値に関わらず**既存ハンドラを全消去・close する(CPython 実測)。→ 申し送り①(6 節) |
| **列挙ロガーの子孫を除く非列挙ロガーの「再有効化」を止めない** | 4 節 決定① の副作用。**許容する**(根拠と回帰条件は同節)。→ 申し送り②(6 節) |
| **`backend/migrations/versions/**` を触らない** | DDL に一切関係しない |
| **`error_logger` フィクスチャを撤去しない**(1 周目で方針を反転) | 4 節 決定② |
| **`.claude/core-areas.json` の paths を狭めない** | 設計書 6.3 規則④(`:393`)が PR 単位の例外を明文で禁じる |
| **`backend/tests/test_api_errors.py` を変更しない** | TSK-387 の 3 表明をそのまま残す(`docs/worklog/2026-09-16-u00-api-shell.md:106-108`) |
| **台帳の `H-*` を採番しない** | `harness-evaluation.md:2756` の未処理の申し送りだが、採番は PO 判断 |

## 3. 影響する正本

**すべて「反映なし」**。本修正はコードの欠陥是正であり、正本に追随を要する変更を持たない。

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし**(ログの構成を定めた条項が無く、条項を新設もしない) | — |
| `docs/design/data-model.md` | **反映なし**(スキーマ・入口に触れない) | — |
| `docs/design/sync-protocol.md` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(6.3 の paths 規則を変えない) | — |
| `docs/adr/ADR-001〜004` | **反映なし**(ロギング方針の決定ではない) | — |
| `.claude/core-areas.json` | **反映なし**(paths を足しも狭めもしない) | — |
| `contracts/**` | **反映なし** | — |
| `docs/README.md`(索引) | **反映なし**(進行中 feature の静的一覧を持たない) | — |
| `AGENTS.md` / `CLAUDE.md` | **反映なし** | — |
| `docs/development/harness-evaluation.md`(台帳) | **反映なし**(見込み)。本件の知見は TSK-387 の PR #67 で記録済み。**新たな知見が出たら /pr のクローズ処理で判断し、その場合は本節へ先に宣言を追記する** | PR レビュー |

## 4. 実装方針

調査メモ: [research.md](research.md)

### 重さ分類 = コア領域

| 判定 | 根拠 |
| --- | --- |
| **機械判定: コア** | `backend/migrations/*` と `backend/tests/test_alembic_environment.py` が **5 領域すべての paths** に登録済み(実測) |
| **意味判定: 境界定義表に直接は該当しない** | 6.3 の境界定義表(`:382-393`)の 5 領域はいずれもロギング設定を射程に含まない。**ただしこれは「軽い」という意味ではない** |
| **運用上コア PR で確定** | 設計書 6.3 規則④(`:393`)が「**過剰包含は PR 単位の例外で外さず**、モジュール分割してから paths を狭める」と明文で禁じる。**機械 paths に登録済みである以上、PR 単位では除外できない** |

**「5 領域だから 5 倍重い」は誤り** — `scripts/core_guard.py:124` が全領域の paths を一本へ平坦化し、
`:212` が変更パスごとの二値マッチだけを行う。**重いのは「コアかどうか」の 1 段だけ。**

### 決定① 修正の形 — `disable_existing_loggers=False`

| 案 | 内容 | 判定 |
| --- | --- | --- |
| **A(採用)** | `env.py` の `fileConfig` へ `disable_existing_loggers=False` を渡す | **直接目的を達成する**(有効だったアプリのロガーを無効化しない) |
| B | `alembic.ini` の `[loggers]` へ `pitchlog` を追加 | **却下**。ロギング方針が未決の段階で alembic.ini がアプリのログ水準を決めてしまう |
| C | アプリ側で logging を再設定する仕組みを入れる | **却下**。ロギング方針の決定そのもので、要件に条項が無い |
| D | 現状維持 | **却下**。今後どの単位がログ表明を書いても同じ形で落ちる |

#### A の副作用(**2 周目レビュー P1 で記述を精密化**)

CPython の `logging.config._handle_existing_loggers` は、既存ロガーを **2 群に分けて**扱う(実測):

| 群 | 扱い | `disable_existing_loggers` の影響 |
| --- | --- | --- |
| **列挙ロガー(`root` / `alembic` / `sqlalchemy.engine`)の子孫** | `level = NOTSET` / `handlers = []` / `propagate = True` にリセット | **受けない**(値に依らず常にリセット) |
| **それ以外の非列挙ロガー** | `logger.disabled = disable_existing` を代入 | **受ける** |

したがって A の副作用は「**列挙ロガーの子孫を除く非列挙ロガーが、すべて有効化し直される**」である
(当初「非列挙ロガーすべて」と書いたのは不正確 — 2 周目 P1)。
**意図的に無効化されていた第三者ロガーがあれば、それも有効化される。**

**この副作用を許容する**。根拠:

1. **実測 — 該当する第三者ロガーは 0 件**。`.python-version` = 3.12.3。
   **env.py が `fileConfig` に到達する直前と同じ import 状態**(`pitchlog.db.base` /
   `pitchlog.db.config` / `pitchlog.db.url` / `alembic` / `sqlalchemy`)で `loggerDict` を数えたところ、
   **実ロガー 34 件・`disabled = True` は 0 件**だった。再現コマンドは[research.md](research.md) A に置く。
   リポジトリ側も `\.disabled\s*=` の全走査で `backend/tests/api_fixtures.py` の一時解除のみ
2. 「無効化されるべきものが有効化される」より「**有効であるべきものが無効化される**」ほうが
   本タスクの目的(ログへの顕在化経路の保全)に反する。**fail-loud 側に倒す**
3. **回帰条件を置く** — 決定③の表明 4(characterization test)で挙動を固定する

**根拠 1 は「現時点の実測」であり将来の保証ではない。** 依存が増えれば変わりうるため、申し送り②に送る。

### 決定② `error_logger` フィクスチャは**残す**(1 周目で反転)

撤去しない理由:

- **当初の撤去理由が成立しない** — 決定③で env.py 専用の回帰テストを足す以上、
  **根本是正はそちらで直接検出される**。フィクスチャの有無は根本検出に関係しない
- **撤去すると隔離が実際に失われる** — フィクスチャは**原因を問わず**テスト開始前に無効だった
  ロガーを有効化し、終了時に元へ戻す(`api_fixtures.py:19-38`)
- **順序依存を回帰契約にしない** — 根本検出は決定③の専用テストへ一本化し、
  API テストは隔離したままにする

**docstring を現況化する。** 現在の docstring は alembic の `env.py` を名指ししているが、
根本是正後はその記述が古くなる。**「当該ロガーの `disabled` 状態からテストを隔離する」**と
**狭く**書き直す(2 周目 P2 — 「一般の logging 状態」は過大。フィクスチャが触るのは `disabled` だけ)。
TSK-387 が置いた `assert not ...disabled` との役割分担も 1 文で書く。

### 決定③ テストは子プロセスで env.py を実行する

`backend/tests/test_alembic_environment.py:52-56` の `_ConfigStub.config_file_name = None` により、
**既存の構造検査は `fileConfig` の分岐に一度も入っていない**。
**ただし pytest プロセス内で実 `fileConfig` を呼ぶと、root handlers と全既存ロガーの状態が変化する**
ため、**子プロセスで実行する**。

#### 子プロセスの実行条件(**2 周目レビュー P0 — 実行可能な水準まで固定する**)

既存テストは `monkeypatch.setattr(alembic, "context", context_stub)` を使うが(`:88-89`)、
**monkeypatch は子プロセスへ継承されない**。子プロセス側で自前に用意する:

| 項目 | 指定 |
| --- | --- |
| 起動 | `subprocess.run([sys.executable, "-c", <script>], ...)` |
| `cwd` | **`backend/`**(`alembic.ini` と `src/` の解決基準) |
| 環境変数 | 親の `os.environ` を引き継ぎ、**`PITCHLOG_MIGRATION_DATABASE_URL` を明示的に設定**する(`env.py:23`,`:41` がオフラインでも URL の取得・正規化を実行するため) |
| `alembic.context` | **子プロセス内で** `import alembic` → `alembic.context = <子プロセス内に定義した ContextStub>` と代入する(`is_offline_mode()` が `True` を返し、`configure` / `begin_transaction` / `run_migrations` を受ける最小スタブ) |
| `config_file_name` | 子プロセス内の `ConfigStub` に **`alembic.ini` の絶対パス**を持たせる |
| env.py の実行 | `runpy.run_path(<env.py の絶対パス>)` |
| 出力 | スナップショットを **JSON で標準出力**へ 1 行 |
| 親の検証 | **`returncode == 0` を表明し、非 0 なら `stderr` を添えて失敗させる**。そのうえで JSON を解析する |

**子プロセス (a) と (b) の違いは 1 点だけ**にする:

- **(a)**: `runpy.run_path(env.py)` で env.py を実行する(= `disable_existing_loggers=False` が効く経路)
- **(b)**: **同じ ini を `fileConfig` の既定引数で直接適用した対照**
  (**「env.py の既定実行」ではない** — 2 周目 P2。env.py を通らないため、
  比較の主張は「**引数差による最終 logging 状態の違い**」に限る)

どちらの子プロセスも、実行前に **アプリのロガー**(`pitchlog.api.errors`)と
**番兵ロガー**を生成する。**番兵の qualname は `alembic.` / `sqlalchemy.engine.` の子孫にしない**
(子孫は `disabled` ではなくリセットの対象になるため — 決定①の表。2 周目 P1)。
本計画では **`pitchlog_sentinel_disabled`** を用い、生成直後に `disabled = True` を設定する。

#### スナップショットの正規化スキーマ(**2 周目レビュー P1 — 検査面を主張に合わせる**)

**下に列挙した項目だけ**を比較する。DoD の主張も「**列挙した項目が一致**」に狭める
(「alembic 側の構成が完全に一致」とは書かない)。

| 対象 | 採る項目 |
| --- | --- |
| `root` | `level` / `handlers` の各要素の **クラス名・`level`・`formatter` のクラス名・`_fmt`・`datefmt`・`filters` の有無・stream の名前**(`sys.stderr` 等) |
| `alembic` / `sqlalchemy.engine` | `level` / `propagate` / `disabled` / `handlers` の各要素(上と同じ項目) |
| `pitchlog.api.errors` | `disabled` |
| `pitchlog_sentinel_disabled` | `disabled` |

#### 親テストの表明

| # | 表明 | 意味 |
| --- | --- | --- |
| 1 | (a) の `pitchlog.api.errors` が `disabled` **でない** | 修正の直接目的 |
| 2 | (b) の `pitchlog.api.errors` が `disabled` **である** | **内蔵の対照** — 検査が空振りでないことを、変異を待たずに示す |
| 3 | (a) と (b) の **列挙した alembic 側項目が一致** | 「alembic 側は引数差の影響を受けない」 |
| 4 | (a) の `pitchlog_sentinel_disabled` が `disabled` **でない** | **characterization test**(下記) |

**表明 4 の位置づけ(2 周目レビュー P1)** — これは「望ましい仕様」ではなく
**現在の挙動を記録し、変化したら気づくための表明**である。
**この表明が落ちたときにすべきことを先に決めておく**:

> **表明 1〜3 が成立したまま表明 4 だけが落ちた場合は、副作用が消えた(= より安全になった)ことを意味する。
> 副作用を復活させてはならない。表明 4 を更新または撤去し、決定①の副作用の記述と申し送り②を現況化する。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**2 周目レビュー P2 を受けて 2 ステップを 1 本へ統合した** — docstring だけのコミットには
観測可能な成果が無く、コア領域 PR の差分と検証を 1 組増やすだけだった。
根本是正・その検査・手当ての説明の現況化は**ひとまとまりの論理変更**である。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **根本是正と回帰テスト** — ① `backend/migrations/env.py:17` へ `disable_existing_loggers=False` を渡す ② `backend/tests/test_alembic_environment.py` に決定③の子プロセス検査(表明 1〜4)を追加する ③ `backend/tests/api_fixtures.py` の `error_logger` の docstring を現況化する(**本体と 3 表明は変更しない**) | **`backend/` で** `uv run pytest --ignore=tests/db -q` green。決定③の表明 1〜4 がすべて成立し、**子プロセスの `returncode == 0` を表明している**(非 0 なら `stderr` を添えて失敗)。`git diff` で **`api_fixtures.py` の変更が docstring だけ**・`test_api_errors.py` が無変更であることを確認。**変異**: `disable_existing_loggers=False` を外すと**表明 1 が落ちる**。**報告に含める** = ① 変異前の baseline が green ② 変異の差分 ③ 落ちた node ID ④ **失敗が表明 1 の assertion であり setup/teardown error ではないこと**(台帳 `H-81`)。**`backend/` で** `uv run ruff check .` / `ruff format --check .` / `ty check` green |

**触れてはならないパス**(コミット前に `git diff --name-only origin/develop..HEAD` で確認):
`backend/pyproject.toml` / `backend/uv.lock` / ルートの `pyproject.toml` / `uv.lock` / `.python-version` /
`backend/tests/conftest.py` / ルートの `conftest.py` / `tests/conftest.py` / `backend/alembic.ini` /
`backend/migrations/versions/**` / `contracts/**` / `.claude/**` / `backend/src/pitchlog/**` /
`backend/tests/test_api_errors.py`。

**変更してよいのは次の 3 ファイルだけ**:

1. `backend/migrations/env.py`
2. `backend/tests/test_alembic_environment.py`
3. `backend/tests/api_fixtures.py`(**docstring のみ**)

## 5. DoD(受け入れ基準)

Notion タスクの DoD と同期。**カード起票時の「NFR-015 の顕在化を壊す」は過大**だったため、
本計画書 1 節の表現(**予防的是正**)が正。カード側は補正済み。

- [ ] `backend/migrations/env.py` の `fileConfig` が**既存ロガーを無効化しない**ことを、
      **env.py を実際に実行するテストで固定**する(スタブで分岐を迂回しない — 決定③)
- [ ] **列挙した alembic 側項目**(決定③のスキーマ)が (a)(b) で一致することを固定する
      — **「完全に一致」とは主張しない**
- [ ] **内蔵の対照を置く** — 既定引数の適用ではアプリのロガーが無効化されることを同テストで表明する
- [ ] **表明 4 を characterization test として置き、落ちたときの扱いを計画書に明記してある**
- [ ] **テストが pytest プロセスの logging 状態を汚染しない**(子プロセス実行 — 決定③)
- [ ] **子プロセスの `returncode` を表明する**(非 0 なら `stderr` を添えて失敗させる)
- [ ] **負例で検出力を確認する** — 変異を当て、**baseline green / 変異差分 / 落ちた node ID /
      失敗が当該 assertion であり setup・teardown error でないこと**を報告に含める(台帳 `H-81`)
- [ ] **`error_logger` フィクスチャを撤去しない**。docstring のみ現況化する(決定②)
- [ ] **`backend/tests/test_api_errors.py` を変更しない**
- [ ] **`backend/alembic.ini` を変更しない**
- [ ] **`backend/migrations/versions/**` を変更しない**
- [ ] **backend CI 全件 green**(PostgreSQL 付き・`tests/db` を含む)
- [ ] **Claude 一次レビュー**(要件適合・規約・NFR-018 のコピー実装検査)を通す
      — コア領域のコード PR は通常レビューに「加えて」敵対レビューと逐行確認を要する(設計書 `:371-372`)
- [ ] **敵対レビュー(`codex_run.py review adversarial`)を通す**(設計書 `:372`)
- [ ] **人間による逐行確認を実施**(設計書 `:372` `:378` `:380`。PR 本文に実施記録行を置く)
- [ ] **横断要求(全単位共通・破っていないこと)**
  - [ ] 物理削除しない(要件書 4.0-2)— 本修正は削除操作を持たない
  - [ ] テナント分離を全機能に適用(NFR-010)— テナントデータを扱わない
  - [ ] 利用者入力は全出力経路で自動エスケープ・生 HTML 挿入禁止(NFR-023)— 出力経路を持たない

## 6. テスト計画

**NFR-019 のテスト種別への対応**(要件書 `:923-938` — [research.md](research.md) B-4):

| 種別 | 本修正での扱い |
| --- | --- |
| **単体(pytest)** | **追加する** — `backend/tests/test_alembic_environment.py` に決定③の表明 1〜4。**既存の構造検査が通っていなかった `fileConfig` の分岐を初めて踏む** |
| **(a) 一致性テスト** | **対象外** — NFR-018 の対象計算に該当しない |
| **(b) 越境アクセステスト** | **発効しない**。要件書 `:933` の発効条項 — **製品の外から到達できる経路を新設も変更もしない**。**網羅の総量は 1 件も減らない** |
| **(c) E2E** | **対象外** |
| **(d) 同期プロトコル故障系** | **対象外** |

**負例(変異)を必須にする** — 台帳 `H-48`(合格条件が実効性を持たない)と
`H-81`(変異が無効だった可能性と区別できない)を踏まえ、**失敗チャネルまで固定して報告する**。
あわせて**内蔵の対照**(表明 2)を置き、変異に頼らずとも空振りが分かる形にする。

**テストの配置**: 既存の `backend/tests/test_alembic_environment.py` を拡張する。新規ファイルを作らない。
`backend/tests/conftest.py` は触らない。

**DB 依存**: 子プロセスは env.py をオフライン実行するため **DB 接続を必要としない**
(`requires_db` マーカを付けない)。ローカルで `--ignore=tests/db` のまま全経路を検証できる。

### 別タスクへの申し送り(本修正では解けない残余)

① **`fileConfig` は既存ハンドラを全消去・close する** — `_clearExistingHandlers()` は
   **`disable_existing_loggers` の値に関わらず**実行される(CPython 実測)。
   したがって「**同一プロセスのアプリ logging 構成を保全する**」問題全体は本修正では解けない。
   アプリ側の logging 構成が入った段階で、**同一プロセス隔離**として別タスクで扱う。

② **列挙ロガーの子孫を除く非列挙ロガーの再有効化**(決定①の副作用)— 現時点の実測では
   **該当する第三者ロガーは 0 件**だが、**これは将来の保証ではない**。依存が増えれば変わりうる。
   決定③の表明 4 が挙動を固定しているので、変化は検出できる。
   **ロギング方針を決めるタスクで再評価する。**
