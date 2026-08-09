# pitchlog 開発規約(人間・Claude・Codex 共通)

野球の試合を1球単位(Pitch by Pitch)で記録・分析するスコアリングシステム。Baseball_Scoring(Tsukuba PSS)の製品版としての全面再構築。

- 要件の正本: `docs/requirements/requirements-pitchlog-2026-07-22.md`(v1.7)
- ドキュメント索引: `docs/README.md`
- 開発プロセスの正本: `docs/development/dev-harness-design-2026-08-07.md`(ハーネス設計書)

## 絶対規則

1. **main / develop へ直接コミット・push しない**。作業は develop 起点の `feature/*`・`fix/*` ブランチ + PR のみ
2. **`.env`・シークレットを読まない・書かない・コミットしない**(NFR-014)。設定の正本は `.env.example`
3. **`docs/legacy/` は版固定アーカイブ — 変更禁止**
4. 正本ドキュメント(docs/requirements・design・adr・development・ops)の確定・改訂ゲートは**ハーネス設計書 7.6 の決定表**に従う(新設・版繰り上げ = 敵対レビュー+人間承認〔/finalize-doc〕/ 実装追随の節更新・変更履歴追記 = PR レビューで可)
5. 実装は**承認済みの実装計画書**(`docs/features/<slug>/plan.md`)に従う。計画にない変更範囲へ触れない

## コーディング規約

- コメント・docstring は**原則日本語**。docstring は **Google スタイル**(ruff の pydocstyle 検査 = google)
- 識別子・ファイル名は英語。ドキュメント・コミットメッセージ・PR は日本語
- コミット: Conventional Commits(`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `ci` / `build`)+ 日本語要約
- ドメイン計算は単一実装(NFR-018)— コピー実装を作らない。クライアント/サーバー一致の正解は `contracts/` のゴールデンベクタ
- 集計は DB 側絞り込み(WHERE / GROUP BY + インデックス)。**全件読み込み型の集計を書かない**(NFR-005)。一覧はページングする
- 利用者入力は全出力経路で自動エスケープ。生 HTML 挿入禁止。PDF レンダラは外部リソース無効(NFR-023)
- 削除はすべて論理削除(要件書 4.0-2「物理削除しない」)
- テスト必須: バックエンド = pytest、フロントエンド = Vitest。実装 PR はテストを伴う(NFR-019)
- 実装は計画書の**実装ステップ単位**で進める: 指示されたステップの範囲だけを実装して止まり、先のステップへ勝手に進まない。コミットはステップごとに Claude が作成する(段階実装 — ハーネス設計書 6.1)

## コマンド(実装フェーズで有効)

- バックエンド(backend/ で): `uv run ruff format` / `uv run ruff check --fix` / `uv run ty check` / `uv run pytest`
- フロントエンド(frontend/ で): `pnpm exec prettier --write .` / `pnpm exec eslint .` / `pnpm exec vue-tsc --noEmit` / `pnpm test`
- 開発 DB: `docker compose up -d`

## リポジトリ構成

`backend/`(FastAPI・uv)/ `frontend/`(Vue 3 + TypeScript・pnpm)/ `contracts/`(ゴールデンベクタ・スキーマ)/ `docs/`(正本体系 — 索引は docs/README.md)/ `scripts/` / `.claude/`(Claude 設定・skills・hooks)/ `.codex/`(Codex プロジェクト設定)

## Code Review Rules

- **コア領域**(同期プロトコル・状況計算・記録権・テナント分離・データ移行 — 定義の正は `.claude/core-areas.json`)の変更は最優先で深掘りする
- NFR-018 違反: 同一ドメイン計算の重複実装を検出したら **P0**
- NFR-023 違反: エスケープ欠落・生 HTML 挿入・PDF の外部リソース参照は **P0**
- シークレットのハードコード・ログ出力は **P0**
- NFR-005 違反: 全件読み込み集計・ページングなし一覧は **P1**
- 物理削除(論理削除の原則違反)・テナント分離の迂回経路を確認する
- テストのない実装変更・計画書のスコープ外の変更を指摘する
