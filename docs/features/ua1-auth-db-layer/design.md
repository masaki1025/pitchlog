---
feature: ua1-auth-db-layer
type: design
date: 2026-10-04
---

# 詳細設計: U-A1 β — 認証の DB 層(TSK-468)

計画書 [plan.md](plan.md) 4 節から参照する。事実の典拠は [research.md](research.md)、条文の正は `docs/design/data-model.md` **v0.4**。
**名前(ロール・スキーマ・関数・設定キー)は本書で決める**(v0.4 の射程宣言「関数の名前と引数・物理 DDL の書式は実装時に確定 = TSK-468」)。

## 1. 置き場の決定

| 物 | 置き場 | 理由 |
| --- | --- | --- |
| 認証関数所有用ロール `pitchlog_auth_fn_owner`(`NOLOGIN` + `BYPASSRLS`) | **製品 authz 資産**(`contracts/authz/product/` のロール要素 — 既存 4 ロールと同じ形) | migration は `CREATE ROLE` を禁じる(`backend/tests/test_migration_hygiene.py:16-28`) |
| 認証関数(DML を含む) | **製品 authz 資産**の関数要素(新しい関数種別 `definer`) | migration は `INSERT INTO` / `UPDATE … SET` を禁じる(同上) |
| 認証関数のスキーマ | **専用スキーマ `authn`**(所有 = `pitchlog_owner`・`USAGE` = `pitchlog_app` と `pitchlog_management_fn_owner` と `pitchlog_auth_fn_owner`・`CREATE` は誰にも与えない) | `authz_private` は `pitchlog_app` に `USAGE` を与えられない(`product-authz-surface/design.md:253-256`)。`public` に置くと名前解決経路の非注入の検査対象が広がる |
| pgcrypto | **製品 authz 資産**で、**専用スキーマ `authn_crypto`** に作る(`USAGE` = `pitchlog_auth_fn_owner` だけ) | `public` / `authz_private` に置くと移行バッチ用ロールの関数 EXECUTE 0 件の検査に当たる(research.md 3-3)。資産は superuser の適用器が流すので trusted 拡張の所有の問題を避けられる |
| 表・列・索引・FK・`tenants.retired_at` | **migration 0027** | 表の構造は migration の役割(既存の分担) |
| 正規化関数 | **ステップ 1 の実測で確定**(下の 3 節) | 人間の決定 B-2 |
| 設定値の seed | **試験 = fixture / 本番 = δ の配備手順** | 人間の決定 B-4・migration は seed 不可 |

## 2. 製品 authz 資産の一般化(ステップ 3〜5)

**閉じた集合を「認証の分だけ」開くのではなく、後続の単位(U-A2・U-C1・U-C3)が同じ形で足せるように開く**(research.md 4 節)。

| 閉じた集合 | 現状 | 一般化 |
| --- | --- | --- |
| 関数種別 | `rls_helper` / `migration_trigger`(`backend/src/pitchlog/authz/asset_spec.py:244-253`) | **`definer`(越境・認証・管理の `SECURITY DEFINER` 関数)を足す**。種別ごとに「付与先の集合・所有ロール・スキーマ」を資産で宣言する |
| 要素群と適用手順 | 7 手順固定(同 `:498`・`:512-516`) | **拡張(`extensions`)とスキーマの追加を既存の手順へ入れる**(拡張は「DB とスキーマ」の手順、`definer` 関数は補助関数の後)。取り外し番号の固定式(`product_provisioning.py:226`・`:411`)を手順数から導く |
| 取り外しの `PUBLIC` 復帰 | `rls_helper` 以外を `GRANT EXECUTE … TO PUBLIC` に戻す(`product_provisioning.py:349-351`) | **`migration_trigger` だけを戻す**(`definer` は戻さない)。**変異試験で守る** |
| 関数 ACL の引数の形 | `{"", "uuid, boolean"}`(`product_function_acl.py:39`) | 資産の宣言から導く |
| ロール集合 | 4 件 exact(`scripts/check_authz_catalog.py:208-249`・試験 `roles == 4`) | 資産から導き、**独立の期待集合と照合**(製品資産 = 現行 4 → ステップ 7 以降 5。移行バッチ用ロールは別資産で別の期待集合 — v0.4「6 ロール」= 製品資産 5 + 移行バッチ用 1) |
| 列 ACL | 補助関数の 8 件 exact(`product_control_access.py:22-31`) | 関数所有ロールごとの宣言から導く |
| 表 ACL | プロファイル由来 exact | 関数所有ロールの表権限を宣言から足す(`function_only` の 4 表・`tenants` と `system_settings` の読み取り) |
| 保護関数・migration 関数の件数 | 38 件・37 件を試験の複数か所で固定 | **固定値を資産からの導出へ置き換える**(トートロジーにしない — 資産と実カタログの照合は残す)。**migration 由来の関数を「トリガ関数」と「通常関数」(正規化関数)に分けて宣言・照合**する(現行は全件を `migration_trigger` と照合) |
| 製品状態のランタイム契約 | 再導出モードなし(`runtime_contract_generator.py:264`) | **`rederive` モードを足す**(資産の変更 → 導出欄の再計算 → 7.7-2 の受理記録 1 件)。**PR B(#87)のマージ後の版を前提に書く** |

## 3. 正規化関数(ステップ 1 で確定)

**規則(v0.4 8-1)**: Unicode NFKC → 前後の空白の除去 → 小文字化。**組み込みはすべて IMMUTABLE**([実測] — research.md 3-2)。

**ステップ 1 で実測して、次のどれかに決める**(合格条件は plan.md):

| 案 | 形 | 当たる検査 |
| --- | --- | --- |
| A | migration に `IMMUTABLE` 関数 `authn_normalize_team_name(text)` を置き、**生成列 `tenants.name_normalized`** と認証関数の両方がそれを呼ぶ | migration 関数の固定数(→ 2 節で導出化)・移行バッチ用ロールの INSERT 時に関数 EXECUTE が要るか |
| B | **生成列 `tenants.name_normalized`** を組み込み関数だけの式で定義し、認証関数は入力を**同じ式の関数**で正規化する(関数は資産側の `definer` の内部関数) | 「1 つの関数」に対する式の重複 — 生成列の式と関数の式が同じであることを**試験で照合**する |
| C | 式索引 | manifest の「構成列が実在」(`test_schema_manifest.py:319-320`)に当たる — **採らない見込み** |

**既定は A**(v0.4 8-1「正規化は DB の 1 つの関数」の字面どおり)。**案 B は規則を生成列の式と関数の 2 か所に持つので v0.4 に反する — 採らない**(計画レビュー 1 周目 P1-2)。
**A が EXECUTE の検査で成り立たない場合も、単一の関数を保つ別の形**(例: 関数を `PUBLIC` 実行可の純関数として種別を分け、移行バッチ用ロールの「利用者定義関数 0 件」の検査から純関数を除く根拠を条文で示す)**をステップ 1 で確定する。単一の関数を保てる形が無ければ、実装に入らず人間に上げる**。一意索引は生成列に張る。

## 4. migration 0027

| 変更 | 内容 |
| --- | --- |
| `tenants.retired_at` | `timestamptz NULL`(`RetirementMixin`)。lifecycle を「退役述語を持つ」へ・`allowed_update_columns` に追加 |
| `tenants.name_normalized` | 生成列(3 節) |
| 一意索引 | `UNIQUE (name_normalized) WHERE retired_at IS NULL` |
| 長さの上限 | **`CHECK (char_length(name_normalized) <= 64)`**(人間の決定 B-3。正規化後の文字数。**migration 後の挿入・更新も DB が拒否する** — 計画レビュー 2 周目 P1-6) |
| 認証主体 | `UNIQUE (tenant_id)`(業務的一意性)・`UNIQUE (tenant_id, id)`(複合参照の参照先 — 前例 `uq_idempotency_ledger_kind`) |
| トークン | 単独参照 `fk_tenant_tokens_subject` を外し、`(tenant_id, auth_subject_id) → tenant_auth_subjects (tenant_id, id)` の複合 FK(`MATCH FULL`・`NO ACTION`)へ |
| 事前検査 | 退役していないテナントの正規化名の重複・64 文字超・認証主体の重複・トークンのテナント食い違いがあれば **migration を止める**(名前を書き換えない)。**`FORCE` 下で所有者に 0 行に見える場合も、索引・制約の作成自体が実データで失敗する**ことを試験で確かめる(research.md 3-4 の推測) |
| downgrade | 逆順に戻す(往復試験 `test_migration_round_trip.py`) |

## 5. 認証関数(スキーマ `authn`・所有 = `pitchlog_auth_fn_owner`・`SECURITY DEFINER`・`search_path = pg_catalog, pg_temp`・本体は完全修飾)

**名前と引数は本書で確定する**。戻り値はハッシュを含まない。

| 関数 | 付与先 | 要点(v0.4) |
| --- | --- | --- |
| `authn.login(team_name text, password text) → uuid` | `pitchlog_app` | 正規化 → **正規化後 64 文字超は `NULL`**(登録と同じ上限 — B-3。長さは公開の規則なので存在は漏れない。計数はしない)→ 退役していないテナントを解決 → 計数の器(③〜⑥)→ 有効テナントにだけ発行・ID は `gen_random_uuid()`。**失敗はすべて `NULL`**(存在・状態・誤り方で分岐して早く終わらない — 同じ照会・計数・同コストの照合)。**有効期限と計数の各設定値を読み、欠落・不正値ならどれか 1 つでも発行しない** |
| `authn.verify_token(token_id uuid) → uuid`(tenant_id) | `pitchlog_app` | 存在・期限・世代・テナント有効・テナント一致を 1 回で照合し、通れば延長。失効は `NULL`。**失効したトークンを延長で復活させない**(行ロックで直列化) |
| `authn.logout(token_id uuid) → void` | `pitchlog_app` | 期限を現在時刻へ(行は残す)。`CHECK expires_at >= last_used_at` と両立させる |
| `authn.change_password(token_id uuid, current_password text, new_password text) → boolean` | `pitchlog_app` | **トークンが `verify_token` と同じ有効性条件(存在・期限内・世代一致・テナント有効・テナント一致・失効していない)を満たすことを先に確かめる**(満たさなければ何もせず `false` — 計画レビュー 1 周目 P0-1)→ **対象はそのトークンの認証主体だけ**(引数で選べない)→ 現行 PW の照合 → ポリシー → ハッシュ更新・世代 +1・日時を 1 トランザクション。新トークンを発行しない |
| `authn.issue_initial_password(tenant_id uuid, password text) → void` | 管理関数所有用ロールだけ | 認証主体と認証情報を作る(1 テナント 1 件) |
| `authn.reset_password(tenant_id uuid, new_password text) → void` | 同上 | ポリシー → ハッシュ更新・世代 +1・日時 |
| `authn.revoke_tenant_tokens(tenant_id uuid) → void` | 同上 | 無効化と同じトランザクションで世代 +1。認証主体が無ければ何もせず成功 |
| `authn.record_admin_login_failure(scope_key text) → boolean`(ロック中か) | 同上 | 管理者用の計数。単位はチームと分ける(`admin:` 接頭辞)。**管理者用の設定値の欠落・不正値なら `true`(ロック中 = 拒否)を返す**(fail-closed)。**ロックの判定は管理者用の具体設計(U-A2)が変え得る** |
| `authn.password_policy_ok(password text) → boolean` | **付与しない**(内部) | 8 文字以上・英字と数字・上限なし |
| `authn_crypto.*`(pgcrypto) | **付与しない** | 認証関数の内側だけで使う |

## 6. システム設定値のキー(B-4 — β が定める)

| キー | 値の形 | 既定 | 備考 |
| --- | --- | --- | --- |
| `auth.token_ttl_seconds` | JSON 数値 | (seed しない) | 付録C の 7 日 = 604800。**未設定なら発行と延長を拒否** |
| `auth.team_login.max_failures` / `auth.team_login.window_seconds` / `auth.team_login.lock_seconds` | JSON 数値 | (seed しない) | **計数の器の試験用**。具体設計(10 章の相談)でキーが変わり得る — **δ が反映** |
| `auth.admin_login.max_failures` / `auth.admin_login.window_seconds` / `auth.admin_login.lock_seconds` | JSON 数値 | (seed しない) | `record_admin_login_failure` が読む。**欠落・不正値なら `true`(拒否)** |

**値の妥当条件(全キー共通)**: JSON の整数で 1 以上。**それ以外(欠落・文字列・0 以下・小数)は不正値**として扱い、該当の関数は fail-closed(発行しない / 延長しない / ログインを拒否 / 管理者計数は拒否)。**β は `auth.team_login.*` を読んで妥当性を確かめるが、ロックは適用しない**(7 節)

## 7. 計数の器(不変条件 ③〜⑥)

- カウント単位は**試験用の仮の形**(`team:` + 正規化名)。**β はロックを適用しない**(計数と、閾値の設定値の存在の確認〔欠落・不正値ならログインを拒否 — 不変条件⑤〕まで)。**ロックの効き方は具体設計そのもの**で、チーム名単位で新規ログインを止める仮設計は不変条件①(第三者の失敗連打で正規利用者を締め出せない)を破るため採らない(計画レビュー 2 周目 P1-4)。**具体設計の反映は δ**(DB 関数・migration の変更を含む — v0.4 12-8)
- **③ 同一コミットで確定**: 失敗は例外にせず `NULL` を返し、計数の更新をコミットする
- **④ 直列化**: 同じ `(scope_key, window_start)` の行を `SELECT … FOR UPDATE`。行が無い場合の競合は**一意の行を作る手段**(索引の追加か勧告ロック)を実測で選ぶ — 既存の索引は非一意(`0013_player_merge_rate_limits.py:122-127`)
- **⑥**: 物理削除しない・`scope_key` と `window_start` は書き換えない(既存トリガ)

## 8. 受理記録・最低要求④・一様性の観測(計画レビュー 1 周目)

- **受理記録**: 凍結基準の v2 記録は 1 受理(PR)につき 1 件(`scripts/frozen_history.py:579-592`)で、**承認者・承認日を要する**(設計書 7.7-2)。**人間が PR 上で最終状態の受理を明示した後に、ステップ 11 で 1 回だけ書く**(前例 PR B `design.md:224`)。中間のステップでは**ランタイム契約の導出欄(P4)は再導出して green に保ち、凍結基準の受理記録の検査だけ red を許容する**。PR 番号はステップ 2 の draft PR で固定する(前例 PR #82)。**ステップ 1 で、受理記録の無い中間コミットで red になる検査の範囲を実測して確定する**(凍結基準の検査以外に広がらないこと)
- **最低要求④**: 「対象側が非共有なら要求元が付与していても返らないこと」(`data-model.md:2596`)。**認証関数は共有の越境ではない**ので④の適用対象外と判定し、PR と ④ 注記タスクに記録する。既存の `test_app_can_execute_no_security_definer_function`(「0 件」)は④の代用ではない(TSK-344 `plan.md:235-249`)ので、**`definer` の付与先の exact 照合(構成検査)へ置き換える**(ステップ 7)
- **一様性の観測**: 失敗の種類ごとに ① 計数の行が同じく更新される ② `authn_crypto.crypt` の呼び出しが同じ回数(試験クラスタで `track_functions = all` と `pg_stat_user_functions`)を照合する。**照合を省く変異が red**。手段の成否はステップ 1 で確かめる
- **独立の期待集合**: v0.4 の 3-2 節の 6 ロール(名前・`NOLOGIN`/`LOGIN`・`BYPASSRLS`)と、関数群と付与先の対応(design.md 5 節)を**資産とは別に定数で置き**、資産と実カタログの両方をそれと照合する(導出がトートロジーにならない)
- **照合のコスト**: 実ハッシュとダミーハッシュのコスト係数がどちらも 12 であることを試験で照合する(`$2a$12$` の接頭辞)。異なるコストの変異が red(計画レビュー 2 周目 P1-5)

## 9. ロック順と確定境界(計画レビュー 2 周目 P1-7)

**認証情報の世代を読む・変える関数は、すべて認証情報の行を先にロックする**:

| 関数 | 認証情報の行 | トークンの行 |
| --- | --- | --- |
| `verify_token` | `FOR SHARE`(世代を読む) | `FOR UPDATE`(延長) |
| `change_password`(有効性確認から更新まで) | **最初から `FOR UPDATE`**(共有ロックから昇格しない — 昇格は相互待ちを生む。計画レビュー 3 周目 P0-1) | `FOR SHARE`(有効性を読む) |
| `reset_password` / `revoke_tenant_tokens` | `FOR UPDATE`(世代 +1) | — |
| `logout` | — | `FOR UPDATE`(期限を現在時刻へ) |

- 世代の更新がコミットされた後の検証は新しい世代と照合して落ちる。**検証が先に `FOR SHARE` を取った場合、世代の更新は検証のコミットを待つ**(その検証は旧世代で通るが、更新のコミット後の要求はすべて落ちる — 即時失効の意味はこの直列化で定まる)
- **ロックの順序は常に「認証情報 → トークン」**(デッドロックを避ける)。並行試験(plan.md 6 節)で、各組み合わせの後に失効が勝つことを確かめる。**両者が各ロックを保持した状態を試験で強制する**(2 接続 — 片方がロックを持ったまま、もう片方を待たせる)
- **時刻はロックを取った後の実時刻**: 期限の判定と更新(延長・ログアウト)には `clock_timestamp()` を使う。`now()` / `CURRENT_TIMESTAMP` はトランザクション開始時刻なので、**ログアウトの後でロックを得た検証が古い時刻で期限内と判定し延長し得る**(計画レビュー 3 周目 P0-2)。試験は「ログアウトが先にトークン行のロックを持ち、検証が待つ」順序を強制する
- **同じ照会**: 失敗の種類ごとに、照会した表と回数が同じであることを照合する(`pg_stat_user_tables` の走査回数の差分 — 統計の反映は `pg_stat_force_next_flush()` 後に読む。手段の成否はステップ 1 で確かめる)。**照会を省く変異が red**(計画レビュー 3 周目 P1-4)

## 10. ステップ 1 の決定と計画の更新

**ステップ 1 の実測で案 A(migration の通常関数 + 生成列)以外の形に決まった場合は、ステップ 6 の方式・検査・合格条件を計画書と本書で更新し、実装に入る前に計画レビューへ戻して人間の承認を受け直す**(計画レビュー 3 周目 P1-8)。案 A に決まった場合は計画どおり進める。
