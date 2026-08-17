---
feature: dev-db-contracts
type: research
date: 2026-08-17
---

# 調査メモ: Phase 4-3(開発用 PostgreSQL + `contracts/` 雛形)

調査方法: 調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列実行し、決定的な引用は Claude が原典で再確認した。行番号は develop = `5164c4d` 時点。

## 問い

1. `contracts/` に何を置くと正本が規定しているか。雛形の完了条件は何か
2. 開発用 PostgreSQL(docker compose)に対する要件・設計の規定は何か。バージョンは決まっているか
3. `frontend/src/lib/display_geometry_263_v1.json` を `contracts/` へ移す件の根拠と制約は何か
4. この feature はコア領域に触れるか
5. 旧システムから引き継ぐべき事実は何か

## 結論(要約)

- **`contracts/` の位置づけは限定されている**。設計書 4 章は「NFR-019(a) のゴールデンベクタの置き場であって、**NFR-018(単一実装)の実現方式そのものではない**。実現方式は **Phase 4 着手前に ADR で確定する**」と明記するが、**その ADR は未起票**(`docs/adr/` は ADR-001・ADR-002 のみ)。4-3 は `contracts/` の中身を初めて決める PR なので、**この空白をどう扱うかが最大の論点**(→ 論点 A)。
- **`contracts/` の内部構造・命名・形式・「雛形」の完了条件は、要件書にも設計書にも規定がない**。4-3 の裁量であり、計画書で定義して人間承認を取る必要がある。
- **PostgreSQL のメジャーバージョンはどの正本にも規定がない**(要件・設計・ADR・onboarding すべて)。/research で調査し、**Supabase Platform の既定が PostgreSQL 17** であることを一次情報で確認 → 開発 DB は **`postgres:17.11-bookworm`** を推奨(→ 論点 B)。
- **旧システムから引き継ぐ開発 DB 設定は存在しない**。旧の開発 DB は SQLite ファイルで、docker は本番配信用 Dockerfile にしか使われていなかった。
- **CI に既知の乖離がある**。設計書 10.1 は backend/frontend ジョブの paths filter に `contracts/` を含めると定めるが、現行 `ci.yml` に無い。座標 JSON を移した後にこれを直さないと、**契約ファイルを変更しても frontend ジョブが起動しない**(→ 論点 C)。
- **コア領域は「現状の機構上は触れない」が、意味範囲上は触れる**。座標変換は設計書 6.3 の境界定義表で「状況計算」に明示的に含まれる一方、`.claude/core-areas.json` の paths は全領域 `[]` で機構は空回りしている(→ 論点 D)。

## 詳細と典拠

### 1. `contracts/` の位置づけ

| 事実 | 典拠 |
| --- | --- |
| 「両側が参照する契約物: OpenAPI スキーマ・付録E ゴールデンベクタ(NFR-019a の共通正解)」 | `docs/development/dev-harness-design-2026-08-07.md:160` |
| 「`contracts/` は **NFR-019a(一致性テスト)のゴールデンベクタの置き場**…**NFR-018(単一実装)の実現方式そのものではない** — 状況計算の配置・実現方式(共有実装・生成・その他)は要件書 v1.8 の申し送りどおり、**Phase 4 着手前に ADR で確定する**(敵対レビュー P0-3 対応)」 | 同 `:177` |
| 要件書側の同じ申し送り: 「クライアント/サーバー両方で必要な状況計算の配置と実現方式は、**実装着手前に設計フェーズの ADR で確定する設計課題として申し送り**〔v1.8明文化〕」 | `docs/requirements/requirements-pitchlog-2026-07-22.md:856`(NFR-018) |
| 正解ベクタの出所は **付録E**: 「全表は機械可読なシードデータ(バージョン管理・リポジトリ収載)として固定し、NFR-019(a) の一致性テストは本マトリクスのゴールデンケースを正解ベクタとする(**全表の完成は設計フェーズの必須成果物**)」 | 同 `:1149` |
| 規約側の呼称 | `AGENTS.md:23`・`:38` |
| **要件書に `contracts` の語は 1 件も無い**(置き場の名指しは設計書由来) | 要件書全文 grep |
| **ADR が存在しない** | `docs/adr/` = ADR-001-codex-model-selection.md / ADR-002-frontend-vue.md のみ |

要件書が「リポジトリ収載」を求めている契約物(= `contracts/` の将来の射程):

| 契約物 | 典拠 |
| --- | --- |
| 付録E 打撃結果・状態遷移マトリクス(機械可読シード) | 要件書 `:1149` |
| 付録B-6 フィールド領域シード(守備位置領域・方向区分の座標多角形) | 同 `:1107` |
| 付録B-5 座標移行のテストベクタ(ゴールデンフィクスチャ) | 同 `:1106` |
| 付録D-1 88 列スキーマ定義ファイル / D-3 サイドカー契約 / D-4 語彙初期値 | 同 `:1132`・`:1134`・`:1135` |
| 付録A 指標定義 — **固定ベクタ化の計画がどこにも無い**(台帳 H-55) | 同 `:1002`・`docs/development/harness-evaluation.md:684-693`(未対応) |

**規定なし**: `contracts/` 配下のディレクトリ構造・命名規則・ファイル形式(JSON/YAML)・バージョニング規則・スキーマ検証器の有無・「雛形」の最小完了条件。設計書 13 章 `:795` は「`contracts/` 雛形」とだけ書き、マージ条件は「通常の PR 要件」。

### 2. 開発用 PostgreSQL(docker compose)

| 事項 | 典拠 |
| --- | --- |
| NFR-021: 「開発DBもPostgreSQLを使用し、**WSL2から完結して利用できる**こと(**配置方式は設計フェーズで決定する**)」 | 要件書 `:871` |
| 配置方式 = Docker Compose(設計フェーズの決定)。「接続情報は `.env`(gitignore・**`.env.example` を正とする**)」 | 設計書 `:218`(5.3)・`:162`(ディレクトリマップ) |
| 「標準 PostgreSQL の範囲で使用(ホスティング固有機能に依存しない)。**接続プール上限の設定を運用文書に定める**」 | 要件書 `:930`(7.1) |
| **Docker Desktop の事前導入は前提としない**(Windows ホスト側の事前導入は WSL2 有効化のみ) | 同 `:873` |
| Phase 4 完了時の合格項目に「**開発 DB へ接続でき**」 | 同 `:875` |
| 証跡に docker の版を記録 | 同 `:877` |
| 起動コマンドの規約 = `docker compose up -d`(v2 構文・ルート配置) | `AGENTS.md:34` |
| 前提ツール表: 「Docker / 開発 DB(PostgreSQL) / Docker Desktop の WSL2 統合、または WSL 内ネイティブ導入」 | `docs/development/onboarding.md:32`(status: draft) |
| 「開発 DB(docker compose)は共有資源のため、**DB スキーマを変えるタスクの並行は避ける**」 | 設計書 `:753` |
| I-6: SQLite/PostgreSQL 二重運用をやめ一本化。「開発環境での配置は要件書 NFR-021 を正とする」 | `docs/improvements-from-baseball-scoring.md:61-66` |

**規定なし(重要)**:

- **PostgreSQL のメジャーバージョン / イメージタグ** — 要件書・設計書・ADR・onboarding のいずれにも記載なし。設計書 `:91` の「Docker v29.3.1(PostgreSQL は Docker で立てる。psql ネイティブ未導入)」は環境実査の**実測値であって決定ではない**。
- **NFR-009(バックアップ)が開発 DB に及ぶか** — NFR-009 本文(要件書 `:807-811`)は運用中サーバーの規定で、開発 DB を対象とする語がない。
- **開発 DB の初期スキーマ・Alembic の導入時期** — 設計書 `:190` が「Alembic。設計フェーズで最終確定」と書くのみ。4-3 の範囲かは未規定(実務上は backend 骨格 = 4-2 以降の話)。

**機構上の注意(実装時)**:

- `.env.example` は **basename が厳密に `.env.example` のときのみ書き込み可**(`.claude/hooks/protect_paths.py:40-42`)。
- **`.env.example` は Read できない** — `.claude/settings.json:42` の `Read(./.env.*)` が deny に掛かる(既知の摩擦: `docs/development/harness-evaluation.md:772-776`)。内容確認は Bash 経由になる。
- `docker compose down -v` / `--volumes` は **deny**(`.claude/settings.json:49-50`)。
- `.gitignore:9-11` は既に `!.env.example` の例外を持つ(追加改修不要)。

### 3. 旧システムから引き継げる事実(legacy-analyst)

| 事実 | 典拠 |
| --- | --- |
| **旧の開発 DB は SQLite ファイル**(`data/app_data.db`)、本番のみ Supabase PostgreSQL。`APP_DB_MODE` で切替・既定 SQLite | `docs/legacy/research/data-layer.md:242`・`docs/legacy/baseball-scoring-db-structure.md:15` |
| **docker は本番配信(Render の Dockerfile)にのみ使用**。開発 DB を立てる `docker-compose.yml` 相当は存在しない | `docs/legacy/research/docs-tests-ops.md:115,117-118` |
| PostgreSQL の権威 DDL は `db/supabase_schema.sql`(PG では `init_db()` は no-op、Supabase の SQL Editor で手動実行) | `docs/legacy/research/data-layer.md:17,267` |
| 日時カラムはすべて `TEXT`(ISO 文字列・TZ なし)。旧要件でも**タイムゾーン対応は Won't** | 同 `:22`・`docs/legacy/requirements-tsukuba-pss-v0.2.md:448` |
| PG 側は大文字混在・**日本語カラム**をダブルクオート付きで定義。`打球位置X/Y`・`打席Id` は**未クオート定義のため実列名が小文字**で偶発的に整合 | `docs/legacy/research/data-layer.md:20,256`・`docs/legacy/baseball-scoring-db-structure.md:278` |
| **ゴールデンベクタ相当は旧側に存在しない**。あるのは Python unittest のアサーション(88 列契約テスト・リプレイ整合性・状況計算 34 本ほか)で、言語中立のデータではない | `docs/legacy/research/docs-tests-ops.md:73,104`・`docs/legacy/research/domain-logic.md:16,158` |
| 旧 B 期(dd03160)の React SPA は `scoringReview.ts` で打点・自責点の判定表を**独自に再実装**していた(NFR-018 違反・P0)。「踏襲する場合は **`contracts/` のゴールデンベクタ化が前提条件**」 | `docs/features/req-v2-legacy-parity/research.md:218` |

**PostgreSQL のバージョン・ENCODING/LC_COLLATE・timezone パラメータ・拡張の有無はいずれも旧側の典拠に記載なし**(探索範囲は legacy-analyst 報告の §6 に一覧)。

**申し送り(4-3 の範囲外だが記録)**: legacy 文書間に未裁定の矛盾が 3 件ある — ①テーブル数 12(`data-layer.md:17`)/ 13(`baseball-scoring-db-structure.md:17`。差分は `game_lineup_snapshot`)②`ON DELETE CASCADE` の有無(同 `:21` vs `:177`)③接続プール `SimpleConnectionPool(1,3)`(`data-layer.md:249`)/ `ThreadedConnectionPool(min1/max10)`(`baseball-scoring-db-structure.md:18`)。③は将来 `max_connections` を検討する際の前提に効く。

### 4. `display_geometry_263_v1.json` の移設

**申し送りの出所**(いずれも正本ではない — `.claude/rules/docs.md` により `docs/features/` は一時作業域、`docs/worklog/` は記録):

- `docs/features/frontend-skeleton/porting-rules.md:130-137`「…旧ではリポジトリ直下の `shared/` にあり、frontend と backend が共有する意図の唯一のファイルだった。…**backend が同じ座標定義を必要とした時点で複製になり NFR-018 に違反する。Phase 4-3 で `contracts/` を作る際に移すこと**」
- `docs/worklog/2026-08-16-frontend-skeleton.md:252-253`(同旨)
- 計画書 `docs/features/frontend-skeleton/plan.md` の申し送り節(`:191`)には**列挙されていない** — ステップ 5 の実測で事後に発生した申し送り(節見出し `porting-rules.md:113`「8. ステップ 5 の実測でわかったこと」)

**移設の制約**:

| 制約 | 典拠 |
| --- | --- |
| 逐語性 = **バイト等価**。比較対象は旧 `shared/display_geometry_263_v1.json`(固定コミット `dd03160044aa5932d3b5a025870c9a5a56d979ef`) | `porting-rules.md:127`・`:146-153`(比較コマンド)・`:5-8` |
| Prettier 対象外の維持。規則本体は「受入条件が逐語比較であるファイルは Prettier の対象外にする。ただし対象外にする前に、旧コミット・許容する変換・比較コマンドを記録する」 | `porting-rules.md:96-97`・実体 `frontend/.prettierignore:13` |
| `displayGeometry.ts` に許した逸脱は「**import パス 1 行のみ変更**」 | `porting-rules.md:124`・現物 `frontend/src/lib/displayGeometry.ts:1` |

**要件との突合(spec-checker + Claude 再確認)**:

- NFR-018 は「ドメイン計算(状況判定・**座標変換**・捕球選手推定・成績集計の前処理・終了判定)は単一の共有実装とし、UI別・経路別のコピー実装を作らない」(要件書 `:856`)→ 座標変換が対象であることは**適合**。
- 付録B-4「**ゾーン枠はデータ**: ストライクゾーンの枠は座標値としてデータ保持し、コードにマジックナンバーを散らさない」(同 `:1105`)→ この JSON はまさにその形。**適合**。
- **ただし、この JSON は付録B の保存座標系ではない**。付録B-1/2 は「0〜1 に正規化」「原点は左下、y 正方向は上」(同 `:1102-1103`)だが、当該ファイルは `"size": 263, "origin": "top_left", "y_direction": "down"`(`frontend/src/lib/display_geometry_263_v1.json:2-6`)= **旧 263px の表示/保存座標系**。位置づけとしては ①frontend の表示幾何、②付録B-5 の移行変換式 `x_norm = x_old/263`, `y_norm = (263 − y_old)/263`(同 `:1106`)の**入力側定義**、の 2 つ。
- **付録B-6 が求めるフィールド領域シード(守備位置領域の多角形・方向区分・タイブレーク規則)は、この JSON に含まれていない**(内容は strike_zone・home_plate・塁位置・fence_radius のみ)。つまり**捕球選手推定の契約はまだ存在しない**。
- 「この JSON を `contracts/` に置け」という**直接の要件条文は存在しない**。根拠は NFR-018 + 付録B-4 + porting-rules の申し送りの合成。

**263 の由来**(legacy-analyst): 旧の**保存座標系のスケール**。コースはクリック点を 400×400 空間へ写してから `x = 263 * px / 400`、打球位置は `x = 263 * px / 421` で 0〜263 の float として保存していた(`docs/legacy/research/input-screen.md:201,210`)。分析側は `コースYadj = 263 - コースY` で上向きに直していた(`docs/legacy/research/analytics-reports.md:18`)。**なぜ 263 なのかは不明**。

### 5. コア領域の判定

| 観点 | 判定 | 典拠 |
| --- | --- | --- |
| 意味範囲(設計書 6.3 境界定義表) | **触れる** — 状況計算欄に「**座標変換・捕球選手推定**(NFR-018・NFR-019(a) の対象 — 旧システムで 3 箇所コピー・『静かなデータ破壊』の事故前例〔改善台帳 I-2・I-17〕)」 | 設計書 `:340` |
| paths 落とし込み規則 ①「コアの不変条件・強制点・**契約(ベクタ・スキーマ・テスト)を変え得るファイル**を含める」 | `contracts/` 配下は文言上該当し得る | 同 `:346` |
| 機構(`.claude/core-areas.json`) | **発火しない** — 5 領域すべて `"paths": []`、`contracts/` も `docker-compose.yml` も guard_paths 外 | `.claude/core-areas.json:12-17`・`:3-11` |
| ガード実挙動 | paths が空なら「コア領域 paths 未定義(Phase 4 で定義予定)— コア検査対象なし」を出力するのみ | `scripts/core_guard.py:269-271` |
| **例外**: `ci.yml` は guard_paths | **CI に触れると core-guard が発火し、PR 必須チェック(人間の逐行確認)が要る** | `.claude/core-areas.json:5` |
| paths 充填の担当スロット | **未規定** — 設計書 `:335`・`:346`・core-areas.json `:2` はいずれも「Phase 4」までしか特定せず、13 章の 4-1〜4-6 のどのセルにも現れない。台帳 H-12 の残余(承認手続の組み込み・承認者指定)も未対応 | 設計書 `:807`・`docs/development/harness-evaluation.md:371-380` |
| paths を触る場合の重さ | **敵対レビュー + 人間承認の対象**(通常 PR 要件では通らない) | 設計書 `:346` ⑤ |

**NFR-021 証跡との関係**: `contracts/`・`docker-compose.yml`・`.env.example` はいずれも**失効対象パス**に列挙されている(設計書 `:636`)。ただし 4-3 は Phase 4 の受入判定(4-6)より前にマージされるため、順序上の問題はない(同 `:801`・`:807`)。

### 6. CI・ツールチェーンの実測(Claude 直接確認)

| 事実 | 典拠 |
| --- | --- |
| 設計書 10.1 は backend/frontend 両ジョブの paths filter に **`contracts/` を含める**と定める | 設計書 `:603-604` |
| 現行 `ci.yml` の frontend filter は `frontend/**`・`mise.toml`・`frontend/pnpm-lock.yaml`・`.github/workflows/ci.yml` のみで **`contracts/**` が無い** | `.github/workflows/ci.yml:99-104` |
| frontend の CI は `eslint` → `prettier --check .` → `vue-tsc --noEmit` → `vitest`(すべて `working-directory: frontend`) | 同 `:112-128` |
| `tsconfig.app.json` の include は `src/**` のみ。alias 定義なし | `frontend/tsconfig.app.json:14` |
| `vite.config.ts` に alias も `server.fs.allow` もない(全 16 行) | `frontend/vite.config.ts` |
| `vitest.config.ts` は別ファイルで、vite.config.ts の設定を継承していない | `frontend/vitest.config.ts` |
| `vite.config.ts:5` のコメントが参照する `docs/api_contract_v1.md` は**実在しない**(lychee は .md しか走査しないため未検出) | `frontend/vite.config.ts:5` |
| `/check` は「`frontend/package.json` があれば frontend/ で」の構成。**`contracts/` を検査する層は存在しない** | `.claude/skills/check/SKILL.md:21-26` |

**帰結(技術的リスク)**: JSON を `contracts/` へ移すと、`frontend/` の外を import する形になる。①`tsconfig` の include 外(型解決は import 追跡で通る見込みだが未検証)②Vite dev サーバは project root 外を `/@fs/` 経由で配信し `server.fs.allow` の制約を受ける(frontend/ に `pnpm-lock.yaml` があるため workspace root が frontend/ に解決される可能性がある)③`vitest.config.ts` にも同じ alias を入れないとテストだけ壊れる。**実装ステップ 1 で `pnpm dev` / `vue-tsc` / `vitest` の 3 経路すべてを実測すること。**

## 未解決・申し送り(/plan で扱う論点)

> **人間判断(2026-08-17)**: 論点 A = **A-1**(置き場 + 最小規約に限定し、ベクタの中身と実現方式は ADR へ送る)/ 論点 B = **/research で Supabase の現行版を確認してから決める**(結果は下記 §論点 B に追記)/ 論点 C = **4-3 に含める** / 論点 E = **4-3 に含める** / 論点 F = **porting-rules.md へ追記する** / 論点 D = **4-3 では行わない**(別タスク H-12 へ送る)。

### 論点 A(最重要): NFR-018 実現方式 ADR が未起票のまま Phase 4 に入っている

設計書 `:177` と要件書 `:856` はともに「**Phase 4 着手前 / 実装着手前に ADR で確定する**」と定めているが、ADR は存在しない。4-3 は `contracts/` の中身を初めて決める PR なので、この空白の上に立っている。台帳 **H-55**(付録A 集計定義の契約化がどの計画にも無い・未対応)は同じ ADR のスコープに紐づいており、さらにこの ADR は**コア領域の広狭を動かす発効判断**を握っている(設計書 `:340` 右欄「付録A 契約の実装完了後に除外を発効する。発効判断は NFR-018 実現方式 ADR〔台帳 H-55〕」)。

選択肢:

| 案 | 内容 | 影響 |
| --- | --- | --- |
| **A-1(推奨)** | 4-3 は「**置き場と最小規約(`contracts/README.md`)+ 座標 JSON の移設**」に限定し、ゴールデンベクタの中身(付録E・付録A)と NFR-018 の実現方式は ADR へ送る。README に「本ディレクトリは NFR-019a のベクタ置き場であり、実現方式は ADR-00X で確定する」と明記して先取りを避ける | 4-3 は通常 PR 要件のまま。ADR は別タスクで起票(H-55 と同時) |
| A-2 | 4-3 の中で ADR を起票・確定させる | ADR は正本の新設 = **確定ゲート(/finalize-doc・敵対レビュー + 人間承認)** が要る。4-3 の重さが跳ね上がり、13 章 `:795` の「通常の PR 要件」と整合しない |
| A-3 | 座標 JSON の移設だけ先行し、`contracts/` の規約は一切書かない | 「雛形」の完了条件が不明のまま。README すら無いと後続が置き方を推測することになる |

**人間の判断が要る。** 私の推奨は A-1。

### 論点 B: PostgreSQL のバージョン — /research 実施済み(2026-08-17)

どの正本にも記載がなく、旧システムにも典拠がない。本番は Supabase 継承(要件書 `:928`)・「標準 PostgreSQL の範囲で使用(ホスティング固有機能に依存しない)」(同 `:930`)なので、開発版は本番が乗る版に合わせるのが筋。/research(Codex・read-only + live search)で調査し、**決定に直結する 2 点は Claude が一次情報で再確認した**。

**確認済みの事実**:

| 事実 | 出典 | 検証 |
| --- | --- | --- |
| Supabase Platform の**既定は PostgreSQL 17**。原文「Postgres 17 is what we currently default to on the Supabase platform, and aligning the self-hosted default keeps behavior consistent across deployment models」(2026-05-18 公開) | https://supabase.com/changelog/46080-self-hosted-supabase-upgrading-from-pg-15-to-17-breaking-change | **Claude が原文確認済み** |
| 既存プロジェクトの 15→17 アップグレード経路あり。事前に `plcoffee`・`plls`・`plv8`・`timescaledb`・`pgjwt` の無効化が要る(`pgjwt` は PG17 まで既定有効) | https://supabase.com/docs/guides/platform/upgrading | **Claude が原文確認済み** |
| `postgres` 公式イメージの現行タグ: 17 → **17.11**、16 → 16.15、15 → 15.19、18 → 18.6(`latest`)、14 → 14.24、ほかに 19beta3。各版に trixie / bookworm / alpine3.24 / alpine3.23 の variant | https://github.com/docker-library/official-images/blob/master/library/postgres | **Claude が manifest を直接確認済み**(Codex の報告と完全一致) |
| PG 14 は 2026-07-01 に Supabase Platform サポートから撤去済み。現行の Supabase Postgres で併存サポートされる通常メジャーは **15 と 17** | https://supabase.com/changelog/45827-deprecation-notice-support-for-postgres-14-ending-on-1st-july-2026 | Codex 報告(未再確認) |
| PostgreSQL 本体の EOL は初回リリースから 5 年(17 = 2029-11、15 = 2027-11) | https://www.postgresql.org/support/versioning/ | Codex 報告(未再確認) |
| Docker Official Images に「タグを落とす日」の固定規則はない。manifest から削除されると以後ビルドされないが、Hub 上の既存タグ自体は取得可能なまま残る | https://github.com/docker-library/official-images | Codex 報告(未再確認) |

**結論(計画書で承認を得る)**: 開発 DB のイメージは **`postgres:17.11-bookworm`** とする。

- **メジャー 17** = 本番 Supabase の既定に一致(I-6「開発と本番で DB が違うと『開発では動くが本番で壊れる』事故が構造的に発生する」— `docs/improvements-from-baseball-scoring.md:64`)。
- **パッチまで固定** = `postgres:17` は 17 系の最新パッチへ動く mutable tag。再現性を要求する NFR-021 の証跡(「主要ツールの版を記録」— 要件書 `:877`)と相性が悪い。完全な同一性が要るなら `@sha256:` の digest 固定が唯一確実だが、更新運用のコストが増えるため**開発 DB ではパッチ固定までに留める**のを推奨(digest 固定は将来の選択肢として記録)。
- **bookworm(debian)** = alpine は musl libc でロケール・照合順序が glibc と同一とは限らない。日本語データを扱うため差異要因を持ち込まない。
- **`supabase/postgres` イメージは使わない** — 要件書 `:930`「標準 PostgreSQL の範囲で使用(ホスティング固有機能に依存しない)」に照らすと、素の `postgres` イメージで動くこと自体が可搬性規律の担保になる。Supabase 固有拡張の検証が要る局面が来たら、その時に別途手当てする。

**ロケールの申し送り(重要)**: `LC_COLLATE` / `LC_CTYPE` は **DB 作成後に変更できない**(https://www.postgresql.org/docs/17/locale.html)。一方で **Supabase Platform の `lc_collate` / `lc_ctype` の実値は公開ドキュメントから確認できなかった**(Codex 報告)。本番プロジェクトは未構築(設計書の論点D)なので現時点では突合不能。

→ 開発 compose では **`POSTGRES_INITDB_ARGS` でエンコーディング UTF8・ロケールを明示**し、その値を計画書に記録する。**本番 Supabase を構築した時点で `SHOW lc_collate; SHOW lc_ctype;` を確認し、開発側と一致しているかを突合する**ことを申し送りとして残す(不一致だと日本語の `ORDER BY` が開発と本番で変わり、I-6 が消したかった「開発では動くが本番で壊れる」と同型の差異が座る)。

**compose 実装時の既知の落とし穴(/research より)**:

- `/docker-entrypoint-initdb.d` の初期化スクリプトは **PGDATA が空の初回起動時のみ**実行される。既存の名前付きボリュームがあると、環境変数の変更も初期化 SQL の変更も反映されない(https://hub.docker.com/_/postgres)。**やり直しにはボリューム削除が要るが、`docker compose down -v` は deny 設定**(`.claude/settings.json:49-50`)なので、手順は人間が実行する前提で書く。
- healthcheck は **`pg_isready -h 127.0.0.1` と TCP を明示する**。`-h` を省くと、初期化 SQL 実行用に立つ**一時サーバー(Unix socket のみ)**に成功してしまい、**初期化完了前に healthy になる偽陽性**が起きる(https://hub.docker.com/_/postgres・https://www.postgresql.org/docs/17/app-pg-isready.html)。
- データ領域は **名前付きボリューム**を第一選択にする。`/mnt/c` 配下のバインドマウントは NTFS の権限が Linux 権限へ写らず、`initdb` の 0700 要求で失敗し得る(https://learn.microsoft.com/en-us/windows/wsl/file-permissions)。
- Docker Desktop の WSL2 統合と WSL 内ネイティブ Docker Engine は**同居させない**(https://docs.docker.com/desktop/features/wsl/)。onboarding.md `:32` は両方を許容しているため、**compose ファイルはどちらでも動く形にする**(名前付きボリューム + TCP healthcheck ならこの条件を満たす)。

### 論点 C: CI の paths filter の追随(設計書 `:603-604` への実装追随)

`contracts/` を作る以上、frontend(将来は backend も)の paths filter に `contracts/**` を足すのが筋。**ただし `ci.yml` は guard_paths(`.claude/core-areas.json:5`)なので core-guard が発火し、PR に人間の逐行確認チェックが必須になる**。4-3 に含めるか別 PR にするかを計画で決める。含めない場合、**移設した契約ファイルを変更しても CI が回らない穴が残る**ため、含める方を推奨。

### 論点 D: `core-areas.json` の paths 充填は 4-3 でやらない(推奨)

担当スロットが未規定(H-12 残余)である一方、paths の追加は**敵対レビュー + 人間承認の対象**(設計書 `:346` ⑤)で、13 章 `:795` が 4-3 に与えたマージ条件(通常 PR 要件)では通らない。**4-3 では触れず、「`contracts/` に座標定義を置いたことで `game-state` の paths 候補が初めて発生した」事実を申し送りとして残す**のが整合的。

### 論点 E: `.env.example` の初版作成は 4-3 の担当か

設計書 `:218` が「接続情報は `.env`(`.env.example` を正とする)」と定めており、docker-compose を作る以上は接続情報の正本が要る。**4-3 で作るのが自然**だが、13 章 `:795` は明示していない。キー名の決定も既存の典拠がない(ファイル自体が未作成)。計画で明示してスコープに入れること。

### 論点 F: 逐語性の維持手段(移設後)

`frontend/.prettierignore` は frontend/ 起点の Prettier にしか効かず、`contracts/` は射程外になる(ルートに Prettier は無いので直ちに壊れはしない)。ただし `porting-rules.md:96` は「逐語比較のファイルは対象外にし、比較コマンドを記録する」を**今後にも適用する規則**として書いている。移設後の逐語性をどこで担保するか(`contracts/README.md` への注記 / porting-rules.md への追記 / 将来ルート Prettier を入れる際の ignore)を計画で決める。あわせて **H-59 の照合規律**(照合した項目を列挙してから合否を述べる)に従い、旧 `shared/` 版とのバイト等価を `dd03160` に対して照合した事実を明記する。

### 論点 G: 技術的実現(実装ステップ 1 で実測)

`tsconfig`(include 外の JSON import)・`vite.config.ts`(alias / `server.fs.allow`)・`vitest.config.ts`(同じ alias の二重定義)の 3 点。`pnpm dev` / `vue-tsc --noEmit` / `vitest` の**すべてで通ること**を合格条件に置く。

### 抵触しないことを確認した項目

- **H-56(移行実データの取り扱い統制・未対応)**: 開発 DB を**空で起動するだけ**なら抵触しない。旧実データの投入を計画に含めないこと。
- **Won't(要件書 2.2 `:74-87`)との衝突なし**。
- **4-2(backend 骨格)との順序拘束なし** — 設計書 `:807`「4-1 が先行 → **4-2 / 4-3 は相互任意**」。
- **4-3 で NFR-021 判定は行わない** — 同 `:795`・`:801`。
- **`docs/ops/` には手を出さない** — ディレクトリ新設は 4-4 とブートストラップ監査 PR の担当(同 `:796`・`:636`)。
