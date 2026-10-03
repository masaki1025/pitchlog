---
feature: ua1-team-auth
type: research
date: 2026-09-24
---

# 調査メモ: U-A1 チーム認証(ログイン・パスワード変更)

調査方式: 調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列で実行し、
**計画を左右する主張は Claude が原典を再確認して裁定**した。以下の表記を使う:

- **[確認済]** = Claude が本メモ作成時に当該ファイルを読んで裏を取った事実
- **[報告]** = 調査エージェントの報告をそのまま採った事実(典拠は付いているが Claude は再確認していない)

## 問い

TSK-399 / U-A1「チーム認証(ログイン・パスワード変更)」(FR-033 / FR-036・帯 3 認可源・依存 U-T1・
コア判定「テナント分離」)の実装計画を書くために、次を確かめる。

1. 要件書が何をどこまで定めているか(および**定めていない**のはどこか)
2. 旧システム Baseball_Scoring の実挙動と移行制約
3. 既に確定している決定・既存実装資産の上に、この単位がどう載るか
4. **着手・マージを妨げる機構上の制約は何か**

## 結論(要約)

1. **要件は揃っている**。FR-033 / FR-036 の受入基準 7 本 + 補足 1 本がすべて明文化され、矛盾はない。
   NFR-011 が保存形式・ポリシー・トークン寿命・失効を一括で定める **[確認済]**。
2. **スキーマは既に出揃っている**。migration `0011_authentication_tables.py` が認証 5 表を作り済みで、
   **U-A1 が足すのは DDL ではなくアプリ実装**(ハッシュ生成・照合、世代照合、スライディング延長、
   テナント有効性検証、レート制限の適用) **[確認済]**。
3. **着手はできるがマージは止まる**。U-A1 は帯 3 = **入口を開く単位**なので `data-model.md` 12-4 の
   マージゲートが発火し、通過条件①②(実スキーマへの RLS DDL 適用・実スキーマに対する越境テスト green)の
   産出元 **TSK-344 が未着手**である。律速連鎖は **TSK-367 → TSK-317 PR #3 → TSK-344 → U-A1** **[確認済]**。
4. **機構上の衝突が 4 件ある**(いずれも実装に入る前に計画書が決着させる必要がある):
   **① bcrypt 依存の追加が「依存追加禁止」と衝突 ② 迂回検査 TB002 が `generation` 識別子で red
   ③ `TenantContext` 生成 allowlist の製品モジュールが空 ④ operation registry が空・
   `tenant_credentials` に `tenant_id` 列が無くリポジトリ基底の述語要求と噛み合わない** **[確認済]**。
5. **設計判断が 10 件以上未決**。とくに**トークンの表現・保存形式**、**チーム名 → テナントの解決規則**、
   **ログイン時(tenant_id 確定前)の DB 到達経路**は、要件書にも設計正本にも実装にも記述がない **[確認済]**。

## 詳細と典拠

### 1. 要件(spec-checker)

#### 1-1. FR-033 チームログイン(`docs/requirements/requirements-pitchlog-2026-07-22.md:590-597`)**[確認済]**

受入基準 3 本 + 補足 1 本:

| # | 要求 | 行 |
| --- | --- | --- |
| F1 | 正しいチーム名+パスワードで、**操作は自チームのみ / 参照は自チーム + FR-041 の付与範囲**に限られるセッションが開始される。**付与は参照のみを許し操作は許さない** | `:594` |
| F2 | 誤パスワードは拒否し、**失敗理由からチーム名の存在・パスワードの部分一致が推測できない** | `:595` |
| F3 | 失敗連続でレート制限が発動。ただし**ログイン済みの既存セッションはロック中も有効**(締め出し攻撃に使えない設計)。**※制限の具体設計は未決事項(10 章)の相談後に確定** | `:596` |
| F4 | **認証はアプリの 1 層のみ**(旧 nginx Basic 認証の前段は置かない) | `:597` |

#### 1-2. FR-036 チームパスワードの変更(同 `:750-757`)**[確認済]**

| # | 要求 | 行 |
| --- | --- | --- |
| F5 | **現行パスワードの入力が必須**・**変更の事実(日時)が記録される** | `:754` |
| F6 | 変更完了後、旧パスワード由来のトークンは**全経路で失効**し再ログインが要求される | `:755` |
| F7 | 新パスワードは**8 文字以上・英字と数字を必ず含む**ポリシーを満たさなければ受け付けない | `:756` |
| F8 | 忘失時は**チーム代表 → システム管理者がリセットし安全に伝達**(復旧経路) | `:757` |

#### 1-3. NFR-011 認証情報の保護(同 `:852-855`)**[確認済]**

> パスワードは**ソルト付きbcrypt**で保存し、平文・可逆形式で保持しない。パスワードポリシー=**8文字以上・英字と数字を必ず含む**。認証トークンの有効期限は**既定7日**(システム設定値 → 付録C)とし、利用中は**自動延長**(スライディング方式。放置端末は自然失効)。**パスワード変更で全経路のトークンが即時失効する**

付録C: トークン有効期限 = 7 日(スライディング延長)は**設定値**(`:1220`)、
**レート制限の閾値・ロック時間は「未決(10 章)」**(`:1222`)。10 章は
「セキュリティ詳細…| **FR-033の暫定設計で着手** | 山田さん+関係者相談 | **リリース判定前**」(`:1081`) **[確認済]**
→ **閾値が未確定でも U-A1 は着手してよい**ことの条文根拠。

#### 1-4. 隣接 FR との境界 **[報告]**

FR-033 の第 1 受入基準は「**…に限られるセッションが開始される**」で切れており(`:594`)、
資源ごとの判定規則(404・理由コードなし等)は FR-034 側にしかない(`:645`)。
→ **U-A1 は「認可源 = セッションが担持するテナント文脈と付与範囲」の確立まで。資源ごとの判定は U-T1(FR-034)**。

U-A2 へ送る範囲: チーム登録・初期パスワード発行(`:736` FR-035)/ 管理コンソールの PW リセット(`:768` FR-037)/
管理者自身の PW 変更(`:742`)/ 管理者ログインのレート制限(`:748`)/ 管理者認証の分離(`:859` NFR-012)。
ただし **FR-035 `:737`「サーバーは毎リクエストでテナント有効状態を検証する」は U-A1 が作るトークン検証面に掛かる**。

#### 1-5. 横断 NFR の落とし方 **[報告]**

| NFR | U-A1 への効き方 |
| --- | --- |
| **NFR-014**(`:867-870`) | 条文が名指しする 4 つの秘密のうち **「JWT署名鍵」「チーム初期パスワード」の 2 つを直接扱う唯一の単位**。ハードコード・ログ出力・テストフィクスチャへの実値混入がないこと |
| **NFR-019**(`:923-938`) | 柱書(pytest / Vitest)+ **(b) 越境テストの発効条項**が「U-A1 が開く経路について発効」。ただし **(b) の網羅組合せ列挙(`:933`)にログイン経路固有の組合せは無い**ため、U-A1 に全組合せを課す条文上の根拠はない。列挙中「**テナント無効化後**」はトークン検証面に掛かる |
| **NFR-018**(`:887-921`) | **対象外**。対象列挙(`:892` 状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定)に認証は含まれない。ただし「同一計算のコピー実装を作らない」一般規律(PW ポリシー判定をフロント/バックで別実装しない)は AGENTS.md のレビュー規則で P0 |
| **NFR-005**(`:816-820`) | ログイン/PW 変更には集計も一覧も無く直接の要求は発生しない。掛かるとすればレート制限カウンタの参照 |
| **NFR-023**(`:965-969`) | **チーム名が利用者入力として明示列挙**。ログイン・PW 変更画面での自動エスケープと CSP。ただし FR-033 `:595` の存在秘匿により**エラー応答にチーム名をエコーする設計自体が別途禁じられる** |
| **論理削除**(`:161` / `:997`) | トークン行・レート制限カウンタ行を含め**物理削除経路を作らない**。設計正本は「**期限(ウィンドウ)による非使用化**。行は残す」で決着済み(`docs/design/data-model.md:1711-1720`) |

#### 1-6. 改善台帳 **[報告]**

- **I-3**(`docs/improvements-from-baseball-scoring.md:41-46`): 認証トークンの失効を全経路で最初から実装。
  FR-036 `:755` / NFR-011 の**動機の正本**
- **I-20**(同 `:175-180`): 認証の一元化とログイン保護。**FR-033 の全受入基準と NFR-011 全文の出所**
- **I-28**(同 `:237-243`): 逐語移植より改善既決が優先。**旧 SPA の 403/404 使い分けは移植しない**

### 2. 旧システム(legacy-analyst)**[報告]**

| 論点 | 事実 | 典拠 |
| --- | --- | --- |
| 認証主体 | **チーム単位**。JWT ペイロードは `{team_id, team_name, exp}` | `docs/legacy/research/services-shell.md:106` |
| `user_account` 表 | 存在し管理 UI もあるが**ログインには使われていない**。**移行しない**(個人アカウントは Won't 継続) | 同 `:107` / `docs/legacy/baseball-scoring-db-structure.md:170`・`:314` |
| 保存形式 | **bcrypt**(`team.password_hash`)。旧 NFR-008 も「ソルト付きハッシュ(bcrypt)」 | `services-shell.md:103` / `docs/legacy/requirements-tsukuba-pss-v0.2.md:407` |
| セッション | Cookie `tsukuba_pss_auth` + **JWT HS256・有効期限 30 日** | `services-shell.md:102` |
| 本番の実経路 | **nginx Basic 認証**が付与する `X-Remote-User`(= チーム名)で `team` を引く。**Cookie 認証は `ENABLE_COOKIE_AUTH` 既定 false のオプトイン** | 同 `:101` / `docs/legacy/research/docs-tests-ops.md:128` |
| ログイン画面 | **チーム選択(セレクト)+ パスワード**。選択肢は `list_teams_with_password()` = **パスワード保有チーム名を未認証画面で列挙** | `services-shell.md:102` / `docs/legacy/research/data-layer.md:313` |
| PW 変更 | start ページに「チームパスワード変更」expander あり。**現行 PW 再入力の要否は記述なし(不明)** | `services-shell.md:46` / `data-layer.md:314` |
| 変更後の失効 | **Streamlit 版の Cookie セッションは PW 変更後も失効しない**(既知ギャップ・是正対象) | `docs/legacy/requirements-tsukuba-pss-v0.2.md:326` |
| 管理者リセット UI | **記述なし**。実質は環境変数 `INITIAL_TEAM_PASSWORDS`(**未設定チームのみ**・既存ハッシュ非上書き) | `services-shell.md:103`・`:107` / `docs-tests-ops.md:101` |
| テナント境界 | 旧の唯一の境界は `game.owner_team_id`。**所有権チェックはオプショナル引数で、省略すると全データにアクセス可能** | `data-layer.md:397` |
| 88 列との関係 | `play_data` の 88 列に**認証情報は 1 件も含まれない**。認証移行は `team` 表の問題で、88 列変換層とは独立 | `data-layer.md:58-63`・`:142-238` |

**旧に存在しなかった機能**(= 踏襲元が無い): レート制限(旧要件 NFR-010① の是正項目 —
`requirements-tsukuba-pss-v0.2.md:418`)/ パスワード強度ポリシー / アカウントロックアウト / MFA /
ログイン監査ログ / 管理者リセット UI。前段 Basic 認証のハッシュは**ソルトなし SHA-1**(同 `:409`)。

**移行上の含意**:

- 旧 `team` の振り分け(`password_hash` あり = テナント、なし = 相手チームレコード)が認証移行の前提。
  単純な 1:1 では移行できず複製が要る — `docs/design/data-model.md:1365-1383`
- **旧 bcrypt ハッシュを新表へ再利用してよいか / 初回ログイン時の再設定を課すかは、旧・新いずれの正本にも記述なし**
  → 未決(§4-2 D-3)
- 旧本番の実経路が nginx Basic 認証だったため、**`team.password_hash` が実運用の生きた資格情報かは旧資料から判定できない(不明)**

### 3. 既存決定と実装資産(decision-tracer + Claude の再確認)

#### 3-1. スキーマは出揃っている **[確認済]**

`backend/migrations/versions/0011_authentication_tables.py` が作る表:

| 表 | 主な列 | 行 |
| --- | --- | --- |
| `tenant_auth_subjects` | `id` / `tenant_id`(FK→tenants) | `:27-45` |
| `tenant_credentials` | `auth_subject_id`(**PK**)/ `password_hash` / `generation`(default 1・CHECK > 0)/ `password_changed_at` | `:46-74` |
| `admin_credentials` | `id` / `password_hash` / `generation` / `password_changed_at` | `:75-93` |
| `admin_sessions` | `id` / `admin_credential_id` / `credential_generation` / `expires_at` / `last_used_at` | `:94-117` |
| `tenant_tokens` | `id` / `tenant_id` / `auth_subject_id` / `credential_generation` / `expires_at` / `last_used_at` | `:118-149` |

設計正本との対応 **[確認済]**:

| 設計正本 | 典拠 | 0011 での状況 |
| --- | --- | --- |
| ハッシュ = **ソルト付き bcrypt**(P-23) | `docs/design/data-model.md:1509` | 列は `password_hash TEXT` のみ。**形式の強制は DB に無い → アプリ側 = U-A1 の責務** |
| 認証情報の世代(PW 変更で +1) | 同 `:1510` | `generation` 実装済み |
| パスワード変更日時 | 同 `:1511` | `password_changed_at` 実装済み |
| **認証情報をテナント列に直付けせず別表**(裁定 `A-10`・`RQ-06`・2026-09-08) | 同 `:1516-1518`・一意制約表 `:385` | 2 表分離で実装済み |
| `users` 表・入力者識別列を作らない(P-20) | 同 `:1513-1514` | 該当列なし |
| 管理者は**別系統**(テナント参照を持たない) | 同 `:1524-1546` | 実装済み。**U-A1 は触らない(U-A2 の射程)** |
| トークン: 既定 7 日 + スライディング延長 | 同 `:1623-1630` | 列は揃う。**延長ロジックは未実装** |
| **PW 変更で全経路失効 = 世代照合**(全トークン UPDATE は却下済み) | 同 `:1632-1638` | `credential_generation` 列のみ。**照合ロジック未実装** |
| **テナント有効性の検証はトークン検証で行う**(RLS ポリシーに含めない) | 同 `:1497-1503`・`:1640-1641` | `tenants.enabled` は `0002` にあり。**検証ロジック未実装** |
| レート制限カウンタはプロセス外・専用表・**物理削除しない** | 同 `:1704-1720` | `rate_limit_counters` は `0013_player_merge_rate_limits.py:108-119` に実装済み **[報告]** |

> **DoD「パスワードの保存形式が設計正本と一致する」が指す設計正本** = `docs/design/data-model.md` **8-2 節 `:1509`**
> (上流の要件正本は NFR-011 `:854`) **[確認済]**

#### 3-2. 認可基盤(U-T1 の成果物)の上にどう載るか **[確認済]**

`backend/src/pitchlog/repositories/` の公開面:

- `TenantContext`(frozen・`tenant_id` + プロセス内 HMAC 発行証跡)。docstring が
  「テナント ID が認証済み主体のものであることは引き続き **API 層(TSK-217 / U-A1)の責務**」と明記 — `context.py:20-27` **[報告]**
- `TenantRepositoryBase.execute(context, operation)` **のみ**が公開面。**生 Session・任意 SQL を受けない** — `base.py:152-201` **[報告]**
- `_tenant_transaction` が `Session.begin()` 直後に `SELECT set_config('app.tenant_id', …, true)` を 1 文目で発行 — `binding.py:37-77` **[報告]**

**U-A1 に直撃する「空集合」**(すべて Claude が実測) **[確認済]**:

| 資産 | 現在値 | 典拠 |
| --- | --- | --- |
| operation registry | `MappingProxyType({})` = **空** | `backend/src/pitchlog/repositories/base.py:60-62` |
| 製品 capability / token 型 / 越境関数 | **3 つとも空タプル** | `backend/src/pitchlog/repositories/repository_contract.py:57-59` |
| `TenantContext` 生成を許す製品モジュール | **空タプル** | `backend/src/pitchlog/repositories/tenant_context_contract.py:26` |
| 同(契約資産側) | `"allowed_product_modules": []` | `contracts/tenant_boundary/tenant-context-allowlist.json:88` |

さらに `base.py:41-58` は、テナント所有操作の SQL が**最上位 AND に `tenant_id = :tenant_id` を持つこと**を
`__post_init__` で強制する **[確認済]**。

#### 3-3. 依存 U-T1 の状態 **[確認済 / 一部報告]**

- feature: `docs/features/tenant-boundary-enforcement/`(承認済 2026-09-17・`status: in-review`)。
  **develop へ PR #72 としてマージ済み**(セッション開始時の develop HEAD = `871fd97`)。
  本 worktree は origin/develop 起点なので `repositories/` 一式が入っている **[確認済]**
- **U-T1 が明示的に U-A1 へ送ったもの** — `docs/features/tenant-boundary-enforcement/plan.md:74-90` **[確認済]**:
  - **テナント文脈の値の真正性の検証** = **TSK-217 / U-A1 の責務**(`:76`)
  - **製品表向けの汎用 CRUD の公開は TSK-424 の表分類が確定するまで行わない**(`:87`)
  - 製品 RLS 述語・未束縛の直接 SQL 0 行・不正 UUID の `22P02` = **TSK-424**(`:86`)
  - **実スキーマへの適用と越境テスト再実行 = TSK-344**(`:78`)
- U-T1 からの申し送り 3 件(一覧 operation のページング責務 / 入口を開かない判定の記録 /
  NFR-015 の「気づける形」の到達確認は**入口を開く単位が負う**)は**いずれも U-A1 に掛かる** **[報告]**

#### 3-4. ADR と決定記録 **[報告]**

| 決定 | 内容 | U-A1 への含意 |
| --- | --- | --- |
| **ADR-004** マージゲートの適用単位 | 裁定 A(入口ごと)・裁定 B(入口を開く PR は同一 PR に直叩きテスト) | **U-A1 に直撃**(§4-1) |
| **ADR-003** ドメイン計算 | NFR-018 の対象に認証は含まれない | U-A1 は一致性テスト対象外 |
| **ADR-001** モデル選定 | コア領域 → sol xhigh・敵対レビュー・**人間の逐行確認必須** | 実装委任の条件 |
| **D-3**(`requirements-draft-pitchlog.md:49-52`) | チーム共有アカウント継続。個人アカウント・入力者識別は Won't。**利用者表を追加できる余地だけ残す** | `users` 表・`created_by` 列は作れない |
| **D-29 7-1**(同 `:272-275`) | レート制限は締め出し攻撃に使えない設計(**暫定採用・詳細は相談後確定**)/ **認証失効時も未同期キューは保持**され再ログイン後に同期再開 / PW ポリシーは 8 文字英数**以上の複雑性要件は課さない** | 設計の上限・下限 |
| **D-31 S-2**(同 `:343`) | トークン 7 日 + スライディング延長(旧 30 日から短縮) | |

#### 3-5. コア領域 paths の登録 **[報告 / 一部確認済]**

規則の正は設計書 6.3 `docs/development/dev-harness-design-2026-08-07.md:395`(①変え得るファイルを含める
②混在ファイルは全体 ③重複可 ④過剰包含はモジュール分割で解消 ⑤**追加・削除・縮小は敵対レビュー + 人間承認**)。

- **`backend/src/pitchlog/api/*` はどのコア領域にも未登録** **[確認済 — `.claude/core-areas.json` の tenant-isolation paths に `api/` は無い]**。
  一方 6.3 の境界定義表は **FR-033 を明示的にテナント分離の「含む」側**に置く(同書 `:391`)**[報告]**
  → **U-A1 の PR が規則①で登録して機械判定と意味範囲のずれを解消する**(= 6.3-⑤ の審査対象)
- 前例: U-T1 はステップ 4 で `tests/test_core_guard.py` に**正例と、paths から外すと red になる負例**を
  セットで追加した(`docs/features/tenant-boundary-enforcement/plan.md:169`)**[報告]** → **U-A1 も同じ形が既定の踏襲**

#### 3-6. `backend/tests/conftest.py` 差分 0 行の経緯 **[報告 / 現況は確認済]**

1. 起点は**収集迂回の閉塞** — 親 conftest の `pytest_ignore_collect` で保護テストの収集を外せるため、
   `backend/*conftest.py` を tenant-isolation へ、ルートの `conftest.py` / `tests/conftest.py` を
   guard_paths へ登録した(`docs/features/core-area-paths/plan.md:94`・`:110`)
2. **`fnmatch` の `*` は意図より広く当たる**(`docs/worklog/2026-09-09-orm-schema-migration.md:179-180`)
3. DoD 化: 「**1 行でも編集したら `backend/*conftest.py` に一致してコア**。fixture は
   `backend/tests/api_fixtures.py` に置き明示 import する」(`docs/features/product-impl-unit-split/plan.md:465`)、
   リスク⑤ 緩和として「**全計画書の DoD に差分 0 行を入れる**」(同 `:482`・`:569`)
4. **現況 = 9 行・`anyio_backend` fixture のみ** **[確認済]** → 0 行差分は無理なく満たせる。
   **fixture は `backend/tests/api_fixtures.py`(既存)へ置き明示 import する**のが既定路線

### 4. 機構上の制約 — ここが計画の要

#### 4-1. 【最重要】12-4 マージゲートにより**マージが TSK-344 待ちになる** **[確認済]**

`docs/design/data-model.md` 12-4 の通過条件:

> **① RLS のポリシーとロールの DDL が実スキーマへ適用されている ② その実スキーマに対して越境テストが green である**(NFR-019(b) の越境テスト)。**②の green は本表の「適用単位」の範囲で判定する**

測定経路(裁定 B): **入口を開く PR は、同一 PR にその入口を製品の外から直接叩くテストを含む**。
判定の記録: **誰が・いつ・どの実スキーマに対して green を確認したか・どの入口について判定したか
(HTTP なら `route_id` と method / path の組)**。入口を開かない PR は**「対象入口なし」と書く(項目を省かない)**。

`docs/features/product-impl-unit-split/plan.md` **[確認済]**:

- `:431` 「入口を開く PR だけがゲートの判定を受ける(**着手はできる**)…通過条件①② の産出は **TSK-344**」
- `:442` 「`U-T1` は TSK-344 を待たずにマージできる」
- `:456` 「**TSK-344 が要るのは葉・帯 3 のマージであって `U-T1` ではない。**」

**U-A1 は帯 3 で、ログイン・PW 変更という入口を開く** → **ゲートの対象**。
TSK-344 は **未着手**で、律速連鎖は
**TSK-367(contract-only-runtime-handoff・`status: in-review`) → TSK-317 PR #3 → TSK-344**
(`docs/features/contract-only-runtime-handoff/plan.md:24`)**[確認済]**。

> **帰結**: U-A1 は**実装・レビューまで進められるがマージはできない**。計画書はこれを前提に、
> ステップ構成とマージ待ちの扱い(stacked PR / 統合枝 / 待つ — 同 `plan.md:446-452` の 3 案)を決める必要がある。

#### 4-2. 【高】bcrypt 依存の追加が「依存追加禁止」と衝突 **[確認済]**

`backend/pyproject.toml:5-10` の依存は **alembic / fastapi / psycopg / sqlalchemy の 4 つだけで、
bcrypt も passlib も無い**。一方 `docs/features/product-impl-unit-split/plan.md:462` は
「**依存追加禁止(5 領域全部のコア)**。依存が要るなら**依存追加だけの単独 PR** に切る」**[報告]**。

**U-A1 は bcrypt 実装なしに DoD「保存形式が設計正本と一致」を満たせない**
→ **依存追加だけの先行 PR を切る分割が要る**。

#### 4-3. 【高】迂回検査 TB002 が `generation` 識別子で red になる **[確認済]**

- `contracts/tenant_boundary/base-allowlist.json:147-158` の**条件 2(TB002)のパターンに
  `"(?:^|_)generation(?:_|$)"` がある**(`:156`)
- 検査器は**変更行に現れる識別子を正規化して部分一致**で落とす —
  `scripts/check_tenant_boundary_bypass.py` の `_check_identifier`(`:2672-2699`)
- 検査対象は **`git diff -U0 {base_ref}...HEAD -- backend/src`**(allowlist の `diff.command`)
- CI ジョブ `tenant-boundary-bypass` は `.github/workflows/ci.yml:113` で**無条件に走る**

→ **`generation` / `credential_generation` を `backend/src` に書いた瞬間に TB002 で red**。
設計正本が要求する世代照合(`data-model.md:1632-1638`)と機械検査が正面衝突する。
同様に**条件 1(TB001)の `is_allowed` / `has_permission` / `check_*_access` / `require_role`**(同 `:139-142`)も
認証コードの命名に掛かる。
→ 対処は (a) allowlist の改訂(**`contracts/tenant_boundary/*` はコア paths + 凍結基準の履歴追記が機械強制**)
(b) 命名の回避 (c) 条件 2 の例外設計 — **計画書が選ぶ**。

#### 4-4. 【高】`TenantContext` を製品コードから作れない **[確認済]**

`tenant_context_contract.py:26` / `tenant-context-allowlist.json:88` がともに**製品モジュール 0 件**。
U-T1 は意図的に空にして「U-A1 / TSK-217 待ち」とした(`tenant-boundary-enforcement/plan.md:172`)**[報告]**。
→ **U-A1 は自モジュールをここへ登録しないと `TenantContext` を作れない** =
コア契約資産の改訂 + 敵対レビュー + 人間承認 + 凍結基準の履歴追記(設計書 7.7)。

#### 4-5. 【高】operation registry が空 / 認証表の形が述語要求と噛み合わない **[確認済]**

- `base.py:60-62` の registry は空、`repository_contract.py:57-59` の capability / token / 越境関数も空
- `base.py:41-58` は最上位 AND に `tenant_id = :tenant_id` を要求する
- しかし **`tenant_credentials` に `tenant_id` 列が無い**(`0011:46-74` — PK は `auth_subject_id` のみ)
- さらに**ログインは tenant_id 確定前**に認証情報を引く必要がある。`CROSS_TENANT_FUNCTIONS` も空

→ (a) `tenant_auth_subjects.tenant_id` を結合して使う形にする (b) 事前認証専用の別経路を設ける
(後者は越境関数 = TSK-424 / U-A2 の領分と重なる)のいずれかを**計画書が決める**。
あわせて U-T1 の決定「**製品表向けの汎用 CRUD は TSK-424 の表分類が確定するまで公開しない**」
(`tenant-boundary-enforcement/plan.md:87`)との関係を整理する必要がある。

#### 4-6. 【中】HTTP 経路が契約資産に無い **[確認済]**

`contracts/authz/route-registry.json:905-935`(FR-033)・`:1343-1373`(FR-036)は
**`disposition: out_of_registry` / `reason_code: design_pending_task`**。
`contracts/authz/http-route-matrix.json` に **FR-033 / FR-036 の `route_id` は 1 件も無い**。

一方 12-4 は「**同ファイルに `route_id` を持たない HTTP の入口を開く PR は、同一 PR でその入口へ
`route_id` を与える**」と要求する。→ **U-A1 の PR が `route_id` を付与する**(経路表は計画書が書く —
`product-impl-unit-split/plan.md:499-501`・`:519` **[報告]**)。

#### 4-8. 【最重要・2026-09-24 追記】TSK-424 が U-A1 の認可面の前提を決める **[確認済]**

**本節は調査 3 本の完了後に判明した**(人間からの指摘で TSK-424 を当たった結果)。
**§4-5 の衝突と未決 D-4 は、U-A1 が決める事項ではなく TSK-424 が決める事項である。**

TSK-424「製品認可面の確定(全 45 表の許可プロファイル・製品 authz DDL 資産・probe↔製品写像・移行ロール)」
(Notion `3de93b75e6878172a4b4d2f6edd663fc`・**ステータス `進行中`**・worktree `feature/product-authz-surface`・
ブランチ作成 2026-09-24)**[確認済 — Notion 実測 / `git worktree list`]**。

**カード本文が U-A1 を名指ししている**:

> 2026-09-17 に「(TSK-418)を U-T1 に取り込む」と決めたが、**取り込んだ範囲が製品の認可面ぜんたい
> (45 表 × 許可プロファイル × 所有単位)に及び、U-C1 / U-C2 / U-C3 / **U-A1** / U-A2 をまたぐ**ことが
> 計画レビューで判明した。

**U-T1 で収束しなかった P0 のうち 3 件が、そのまま U-A1 の認証表の論点である**(カード「なぜ U-T1 では閉じないか」):

| TSK-424 が挙げる P0 | 本メモの該当箇所 |
| --- | --- |
| **`TenantCredential` は `tenant_id` を持たず `TenantAuthSubject` 経由でテナントに属する(親表経由の所属)** | §4-5 の衝突(リポジトリ基底の `tenant_id = :tenant_id` 述語要求と噛み合わない) |
| **`RateLimitCounter` は認証主体の確定前に読み書きするグローバル可変表** | 未決 **D-4**(ログイン時の DB 到達経路)・**D-5**(レート制限) |
| **`Tenant` は `tenant_id` を持たず主キーが `id`** | §4-5(チーム名 → テナント解決時の到達経路) |

TSK-424 の「やること 2」は
**「許可プロファイルの種別を確定する(少なくとも『親表経由のテナント所属』『認証前グローバル可変』を追加)」**
であり、**これが U-A1 のリポジトリ設計の入力になる**。

あわせて `backend/src/pitchlog/authz/runtime_contract.py:7-8` は
`PROVISIONAL = True` / `SUPERSEDED_BY = "contracts/authz/product/ddl-elements.json"` と宣言しており、
**その差し替え元を作るのが TSK-424 のやること 3**(`contracts/authz/product/` の新設)である **[確認済]**。

**帰結**:

1. **衝突④(§4-5)と未決 D-4 を U-A1 の計画書が先に決めてはならない** — TSK-424 と二重決定になる。
   U-A1 は**その出力を受け取る側**である
2. **順序**: **TSK-424 → (TSK-317 → TSK-344) → U-A1 のマージ**。
   TSK-424 と TSK-344 は別系統(資産・DDL 側 / 実適用・実行側)で、TSK-424 の「やらないこと」が
   **実スキーマへの適用と越境テスト再実行を TSK-344 へ明示的に送っている**
3. **衝突面**: TSK-424 の card が挙げる衝突面は `contracts/authz/product/` と `backend/tests/db/conftest.py`。
   **U-A1 が触る `contracts/authz/http-route-matrix.json`(`route_id` 付与)とは重ならない**

#### 4-7. 【中】凍結基準のプレースホルダ **[報告]**

`contracts/tenant_boundary/*.json` に `source_commit: "PENDING_ACCEPTANCE"` /
`approved_by: "未承認(PR #72 のレビュー待ち)"` が残っている。U-A1 がこれらを改訂すると
履歴追記規則が機械強制される。**既存プレースホルダの扱いは不明 → 人間判断**。

### 5. エージェント間の食い違いと裁定

| 論点 | 食い違い | Claude の裁定 |
| --- | --- | --- |
| NFR-019(b) の網羅が U-A1 に全部掛かるか | spec-checker「(b) の列挙にログイン経路固有の組合せは無く、全組合せを課す根拠はない」/ decision-tracer「12-4 が越境テスト green を要求」 | **両立する**。12-4 の当該行を確認したところ「**本ゲートの判定と NFR-019(b) の網羅の成立とは別の事柄である** — 本ゲートは PR ごとに判定するのに対し、網羅がいつ成立していなければならないかは要件書 8 章のリリース判定基準 2 が定める」と明記されている(`data-model.md` 12-4「適用単位」行)**[確認済]**。→ **U-A1 に掛かるのはゲート(自 PR が開く入口の範囲)であって (b) の全網羅ではない** |
| チーム名に一意制約があるか | legacy-analyst「pitchlog はチーム名に一意制約を置かない方針(FR-039)」/ decision-tracer「それは `team_records`(相手チーム)側の条項で、`tenants.name` は別」 | **DDL で決着**: `0002_tenants_teams_players.py` の `tenants` は `name TEXT NOT NULL` のみで **UNIQUE 制約は無い** **[確認済]**。`data-model.md:400-402` の「一意制約を意図的に置かない/チーム名」は 7-1 節(チームレコード)・FR-039 由来、`:1495`(8-1 テナント)は「登録時の重複チェックで存在が判別され得る」と述べるのみ **[確認済]**。→ **どちらの読みでも「チーム名 → テナントを一意に解決する規則は正本に無い」が結論**(未決 D-2) |

## 未解決・申し送り

### 計画書が決める必要がある設計判断

| # | 論点 | 状態 |
| --- | --- | --- |
| **D-1** | **トークンの表現と保存形式**(不透明値か JWT か・秘密値をハッシュ保存するか) | `tenant_tokens` に**秘密値/ハッシュ列が無い** **[確認済]**。`data-model.md` 8-3 にも規定なし。招待コードは「ハッシュで保存」と明記(同 `:1784`)されているのと対照的 |
| **D-2** | **チーム名 → テナントの解決規則**(同名テナントの扱い) | `tenants.name` に UNIQUE なし **[確認済]**。正本に解決規則の記述なし |
| **D-3** | **旧 bcrypt ハッシュの再利用可否 / 初回ログイン時の再設定の要否** | 旧・新いずれの正本にも記述なし **[報告]**。アルゴリズムは旧新とも bcrypt で一致するが、旧ハッシュからは新ポリシー適合を検証できない |
| **D-4** | **ログイン(tenant_id 確定前)の DB 到達経路** | **TSK-424 が決める**(§4-8)。U-A1 は受け取る側。正本にも実装にも経路が無い |
| **D-5** | **レート制限の閾値・ロック時間・カウント単位(IP / チーム名 / 組合せ)・解除方法** | 閾値とロック時間は**要件書が明示的に未決**(`:1081`・`:1222`)**[確認済]**。カウント単位と解除方法は記述すらなし |
| **D-6** | **トークンの伝達方式**(Cookie / Authorization ヘッダ)・Cookie 属性・**CSRF 対策** | 要件書に記述なし(`Cookie` / `CSRF` の語が 0 件)**[報告]** |
| **D-7** | **ログアウト機能の有無** | 要件書に記述なし。条文化された失効経路は寿命切れ・PW 変更・テナント無効化の 3 つのみ **[報告]** |
| **D-8** | **PW 変更を実行した端末自身のセッションを維持するか** | 条文は「**全経路で失効**」としか書かず、実行端末の除外規定も非除外の明記もない **[確認済 — `:755`・`:854`]** |
| **D-9** | **パスワードの最大長・文字種上限**(bcrypt の 72 バイト境界) | 要件書は下限のみ **[確認済]** |
| **D-10** | **ログイン成功/失敗の監査ログを残すか** | 記述なし。NFR-015(失敗の顕在化)と FR-033 `:595`(存在秘匿)の両立設計が要る **[報告]** |
| **D-11** | **エラー応答の形**(存在秘匿を満たす具体形・**応答時間差によるオラクル化**の防止) | FR-033 `:595` は性質のみ規定。タイミング攻撃への言及なし **[確認済]** |
| **D-12** | **12-4 ゲートの通し方**(および TSK-424 の完了待ち — §4-8) | TSK-344 を待つか、stacked PR / 統合枝で進めるか(3 案 — `product-impl-unit-split/plan.md:446-452`)**[確認済]** |
| **D-13** | **TB002 / TB001 への対処**(allowlist 改訂 / 命名回避 / 例外設計) | §4-3 |
| **D-14** | **NFR-015 の「気づける形」の到達確認**・一覧経路を持つならページング責務 | U-T1 が入口を開く単位へ申し送り **[報告]** |

### 射程外(U-A2 へ)

初期パスワードの発行(FR-035)/ 管理者によるリセット(FR-037)/ 管理者自身の PW 変更・管理者ログインの
レート制限 — **U-A1 が「復旧経路」を実装射程に入れると U-A2 と重複する** **[報告]**。

### 認証と無関係だが検出した事項(移行系タスクへの申し送り)

legacy-analyst が `docs/legacy/` 内の 2 資料間で不一致 3 点を報告した(**Claude は未検証** **[報告]**):

| 論点 | `baseball-scoring-db-structure.md` | `research/data-layer.md` |
| --- | --- | --- |
| テーブル数 | 13 個(`game_lineup_snapshot` を含む・`:17`) | 12 個(`game_lineup_snapshot` の記載なし) |
| ON DELETE CASCADE | `game_lineup_snapshot.game_id` に唯一のカスケード(`:47`) | 「外部キーに ON DELETE CASCADE は一切ない」(`:21`) |
| PG 接続プール | `ThreadedConnectionPool`(min1/max10・`:18`) | `SimpleConnectionPool(1, 3)`(`:249`) |

認証に関する記述(`team.password_hash` の型・bcrypt・`user_account` の構造)は**両資料で一致**している。
U-A1 には影響しないが、**移行タスク(カスケード削除前提・接続プール設計)で効く可能性がある**。

---

## 追補: 2026-10-03 再測定(develop `9ff36743` 取り込み後)

本ブランチへ `origin/develop`(`9ff36743`)を取り込み(差分は本 feature の docs だけで衝突 0 件)、
調査 3 本(spec-checker / decision-tracer / Explore)で本メモの結論を測り直した。表記は本文と同じ
(**[確認済]** = Claude が原典を読んで裏を取った / **[報告]** = 調査エージェントの報告)。

### A. 結論の変化

| 本文の結論 | 2026-10-03 の状態 |
| --- | --- |
| 1. 要件は揃っている | **変化なし**。要件書は v2.9(`requirements-pitchlog-2026-07-22.md:46`)のまま、§1 の引用行・内容とも一致 **[報告]** |
| 2. スキーマは出揃っている | **変化なし**。`0011` は差分 0、0012〜0026 に認証 5 表を変える migration は無い **[報告]**。`data-model.md` の引用行は一律 **+2**(8-2 = `:1511`、8-3 = `:1625-1643`、8-6 = `:1706-1722`)**[報告]** |
| 3. マージは TSK-344 待ち | **入口を開く PR についてのみ成立**(下の B)。**律速連鎖の形が変わった**(下の C) |
| 4. 機構上の衝突 4 件 | ① **人間の決定で消滅**(D・ハッシュは DB 内)② TB002 は残るが**記号単位の裁定機構 `condition_2_adjudications`**(`contracts/tenant_boundary/base-allowlist.json:4253-4278`)が入った **[報告]** ③ allowlist は空のまま。**登録は U-A1 の責務と PR C が明文化**(`feature/tenant-session-supply` の `plan.md:72`)**[報告]** ④ **TSK-424 が決着**(下の B) |
| 5. 設計判断 10 件以上が未決 | D-1 / D-2 / D-4 の骨格 / D-12 は人間の決定と TSK-424 で決着(下の D)。残りは計画書が既定値を置く |

### B. TSK-424 が認証表の到達経路を決めた **[確認済]**

- `contracts/authz/product/table-classification.json:36-67`: `tenant_auth_subjects` / `tenant_credentials` /
  `tenant_tokens` = **`function_only`**(`access_path.reason = pre_context_authentication`)、`rate_limit_counters` =
  **`function_only`**(`pre_context_global_mutable`)。**4 表とも `owner_unit: "U-A1"`**。`tenants` は `self_tenant_row`
- `function_only` = **ポリシーを置かず、アプリ用ロールに権限を与えない**(期待は `42501`)
  (`docs/features/product-authz-surface/design.md:32`)
- 理由(同 `:40`): 「ログインは TenantContext の束縛前に走る…束縛後に使えるようにすると、
  **パスワードハッシュをアプリ用ロールが直接読める経路が残る**」→ **到達経路 = 認証関数(所有単位 U-A1)**
- 関数の ACL・`search_path`・関数所有ロールへの所有の付与は各単位が持つ(同 `:655`)。
  「`pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件」を試験で表明しており、
  **関数を足すと red になり最低要求④の試験を足すよう促す**(同 `:482`)
- **トークンの提示形式と秘密性の確定は U-A1**(同 `:168`・`product-authz-surface/plan.md:149`)
- `tenant_credentials.password_hash` は露出の事実「秘密の列」(`exposure-facts.json:228-250`
  「平文と同様に直接露出させない」)
- **関数所有ロールは正本に 2 つしかない**(`data-model.md:212-213` = 共有関数所有用 / 管理関数所有用)。
  認証関数をどちらが持つかの記述は無い **[確認済]**

→ **§4-5 の案 (a)(リポジトリ基底で結合)は成り立たない**(アプリ用ロールに権限も capability も無い)。
**§4-8 の帰結 1「U-A1 は受け取る側」は「分類は TSK-424 で確定、関数の実装は U-A1」へ読み替える。**

### C. 律速連鎖と 12-4 ゲート **[確認済]**

- **TSK-344 の実体は `feature/product-rls-boundary-tests`**(計画レビュー 7 周・承認待ち)。
  依存の exact-set は 9 件で **U-A1 は入れない**(裁定 2026-09-27 — 同 `plan.md:361`・`:381`・`:385`)。
  依存 5〜8 は **U-C3 / U-C2 / U-C1 / U-A2 の代表関数**(同 `:377-380`)
- 順序契約(同 `:463-478`): **U-C1 / U-C2 / U-C3 / U-A2 が「関数だけを作り、入口を 1 つも開かない PR」を先にマージ
  → TSK-344 が実スキーマで再実行 → 各単位が入口を開く PR を出す**
- 一方 **U-A2 と U-C1 は U-A1 に依存する**(`product-impl-unit-split/plan.md:224-225`)
- 12-4 の「開く」の定義(`data-model.md:2461-2468`): **① 処理するコードが存在 ② 製品の外から到達できる(ルーティングに載る)
  ③ DB を読み書きする — の 3 つがそろうこと。いずれかを欠く PR は開いていない**

→ **律速連鎖 = U-A1(関数層・入口なし)→ U-A2・U-C1 の関数 PR(→ U-C2)→ TSK-344 → U-A1 の入口 PR / U-M1 の入口 PR**。
U-A1 は TSK-344 の**上流と下流の両方**にいる。**U-A2・U-C1 の関数 PR が U-A1 の関数層のマージまで要るかは、
単位の依存表(単位単位の粒度)からの推論で未検証**。

### D. 人間の決定(2026-10-03・本セッション)

| # | 論点 | 決定 |
| --- | --- | --- |
| H-1 | PR の分け方 | **入口を開かない関数層 PR(本ブランチ)を先にマージ**し、**HTTP の入口 PR は TSK-344 の後**に別タスクで出す。当初「依存追加 PR + 関数層 + 入口」の 3 本としたが、H-5 により依存追加 PR は不要になり **2 本** |
| H-2 | トークンの形と伝達(D-1 / D-6) | **`tenant_tokens.id` に HMAC-SHA256 署名を付けた値**を **Cookie(`HttpOnly`・`Secure`・`SameSite=Strict`)** で渡す。CSRF はカスタムヘッダ必須化 + `Origin` 検査。毎リクエスト DB の行で世代・期限・テナント有効性を照合。**スキーマ変更なし・JWT ライブラリ不要** |
| H-3 | チーム名 → テナント(D-2) | **正規化名に UNIQUE 索引**を足す(登録時の重複チェック `data-model.md:1497` の形を DDL で強制) |
| H-4 | 認証関数の所有ロール | **認証専用の関数所有ロールを新設**(`NOLOGIN` + `BYPASSRLS`。正本ロール表の改訂を伴う) |
| H-5 | ハッシュの生成・照合の場所 | **DB 内で pgcrypto**(`crypt()` / `gen_salt('bf')`)。ハッシュを DB の外へ出さない(B の TSK-424 の理由と整合)。Python の bcrypt 依存は追加しない |

### E. TSK-399 の DoD(Notion カード実測・2026-10-03)**[確認済]**

シークレットのハードコード・ログ出力なし(NFR-014・P0)/ パスワードの保存形式が設計正本と一致 /
NFR-019 の越境テスト(他テナントの認証情報へ到達できないこと)/ `core-areas.json` への paths 登録を本 PR で行う /
`backend/tests/conftest.py` の差分 0 行 / pytest・ruff・ty green。横断要求: 物理削除しない・テナント分離・自動エスケープ。
