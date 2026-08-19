# contracts

このディレクトリは、[NFR-019(a)](../docs/requirements/requirements-pitchlog-2026-07-22.md) の一致性テストに用いるゴールデンベクタ、およびクライアントとサーバーが共通して参照する契約物の置き場です。位置づけの定義は [ハーネス設計書 4章](../docs/development/dev-harness-design-2026-08-07.md) を正とし、本文はここに複製しません。

ここは NFR-018（ドメイン計算の単一実装）の実現方式そのものではありません。状況計算の配置・実現方式は [ADR-003](../docs/adr/ADR-003-domain-calc-method.md) で確定済みで、**制約された宣言モデル（DSL）を正本に Python / TypeScript / SQL 式を生成する**方式を採ります。**DSL の正本・生成器・生成物はこのディレクトリに置きません**（backend / frontend 側に置きます — ハーネス設計書 4章の限定と衝突させないため）。

このディレクトリに置く契約は 2 種類です（内訳と規約の正は ADR-003 の D-6 / D-12）。

- **対象計算ベクタ契約** — 対象計算に 1 対 1 で紐づく版付き JSON（`schemaVersion` / `calculation` / `cases[]`）。**1 ファイル = 1 対象計算**。ここに置くのは NFR-019(a) の一致性テストの対象、すなわち **クライアント・サーバー双方の runner が読むもの**に限ります（サーバーでのみ実行する集計のベクタは `backend/` 配下）
- **参照データ契約** — 対象計算に紐づかない共有の定義データ（フィールド領域シードなど）。`calculation` も `cases[]` も持ちません

ディレクトリは `contracts/<領域>/` の 1 階層で、2 階層以上に分けません（`state-transition/` / `field-regions/` / `display-geometry/` / `stat-vectors/`）。既存の `display_geometry_263_v1.json` は現在のパスのまま据え置きます（要件書 NFR-018 の逐語移植の例外表が現在のパスを名指ししているため — ADR-003 D-12）。

将来は、打撃結果・状態遷移マトリクス（付録E）、フィールド領域シード（付録B-6）、88列スキーマ定義・サイドカー契約・語彙初期値（付録D-1/D-3/D-4）、OpenAPI スキーマを収載します。これらの正は [要件書の該当付録](../docs/requirements/requirements-pitchlog-2026-07-22.md) であり、この README は所在を示す索引に留めます。
