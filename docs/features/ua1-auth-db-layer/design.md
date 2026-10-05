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
| 認証関数のスキーマ | **専用スキーマ `authn`**(所有 = `pitchlog_owner`・`USAGE` = `pitchlog_app` と `pitchlog_management_fn_owner` と `pitchlog_auth_fn_owner`・`CREATE` は誰にも与えない)。**認証関数所有用ロールには `public` スキーマの `USAGE` と正規化関数の `EXECUTE` も与える**(認証表・設定値・正規化関数が `public` にあるため — 4 周目 P1-3) | `authz_private` は `pitchlog_app` に `USAGE` を与えられない(`product-authz-surface/design.md:253-256`)。`public` に置くと名前解決経路の非注入の検査対象が広がる |
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

**「前後の空白」に含める文字**(計画レビュー 5 周目 P1-10 — `btrim(text)` の既定は U+0020 だけで、タブ・改行が残る): **NFKC の後に、前後の Unicode の空白類(`White_Space` 性質の文字 — 少なくとも U+0009〜U+000D・U+0020・U+0085・U+00A0・U+1680・U+2000〜U+200A・U+2028・U+2029・U+202F・U+205F・U+3000)を除く**(NFKC で U+3000 等は U+0020 になるが、タブ・改行・U+0085 などは残るため明示する)。**実現式と境界試験はステップ 1 で確定**する。**これは正本 8-1 の「空白」の解釈であり、ステップ 6 の実装追随で 8-1 節に文字の範囲を書き添える**

**ステップ 1 で実測して、次のどれかに決める**(合格条件は plan.md):

| 案 | 形 | 当たる検査 |
| --- | --- | --- |
| A | migration に `IMMUTABLE` 関数 `authn_normalize_team_name(text)` を置き、**生成列 `tenants.name_normalized`** と認証関数の両方がそれを呼ぶ | migration 関数の固定数(→ 2 節で導出化)・移行バッチ用ロールの INSERT 時に関数 EXECUTE が要るか |
| B | **生成列 `tenants.name_normalized`** を組み込み関数だけの式で定義し、認証関数は入力を**同じ式の関数**で正規化する(関数は資産側の `definer` の内部関数) | 「1 つの関数」に対する式の重複 — 生成列の式と関数の式が同じであることを**試験で照合**する |
| C | 式索引 | manifest の「構成列が実在」(`test_schema_manifest.py:319-320`)に当たる — **採らない見込み** |

**既定は A**(v0.4 8-1「正規化は DB の 1 つの関数」の字面どおり)。**ステップ 1 の実測で、案 A は移行バッチ用ロールに正規化関数の `EXECUTE` を要ると分かった → 案 A1 を提案(10-1 節 ①・plan.md 7 節 J-4)**。**案 B は規則を生成列の式と関数の 2 か所に持つので v0.4 に反する — 採らない**(計画レビュー 1 周目 P1-2)。
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
| `authn.login(team_name text, password text) → uuid` | `pitchlog_app` | 正規化 →(**長さで分岐しない** — 65 文字以上の名前も同じ失敗経路を通る。一致するテナントは `CHECK` により存在しない。入力の大きさの上限は HTTP 層〔δ〕。4 周目 P1-4)→ 退役していないテナントを解決 → 計数の器(③〜⑥)→ 有効テナントにだけ発行・ID は `gen_random_uuid()`。**失敗はすべて `NULL`**(存在・状態・誤り方で分岐して早く終わらない — 同じ照会・計数・同コストの照合)。**有効期限と計数の各設定値を読み、欠落・不正値ならどれか 1 つでも発行しない** |
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
- **④ 直列化**: 同じ `(scope_key, window_start)` の行を `SELECT … FOR UPDATE`。行が無い場合の競合は**一意の行を作る手段**(索引の追加か勧告ロック)を実測で選ぶ — 既存の索引は非一意(`0013_player_merge_rate_limits.py:122-127`)。**一意索引を選んだ場合は migration 0027 に索引を足し、ORM・manifest・スキーマ監査・試験もステップ 6 で更新する**(計画の更新と再承認 — 10 節)。**実測と提案(勧告ロック)は 10-1 節 ②・plan.md 7 節 J-5**
- **⑥**: 物理削除しない・`scope_key` と `window_start` は書き換えない(既存トリガ)

## 8. 受理記録・最低要求④・一様性の観測(計画レビュー 1 周目)

- **受理記録**: 凍結基準の v2 記録は 1 受理(PR)につき 1 件(`scripts/frozen_history.py:579-592`)で、**承認者・承認日を要する**(設計書 7.7-2)。**人間が PR 上で最終状態(S・H・D)の受理を明示した後に、ステップ 13 で 1 回だけ書く**(前例 PR B `design.md:224`)。中間のステップでは**ランタイム契約の導出欄(P4)は再導出して green に保ち、凍結基準の受理記録の検査だけ red を許容する**。**PR は `/pr` で作り、受理は S・H・D を固定して求める**(plan.md ステップ 12・13。draft PR を先に開かない)。**ステップ 1 で、受理記録の無い中間コミットで red になる検査の範囲を実測して確定する**(凍結基準の検査以外に広がらないこと)
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
- **同じ照会**: 失敗の種類ごとに、**実行された SQL 文(`pg_stat_statements` の `queryid`)と回数**が同じであることを照合する(表の走査回数だけでは照会の違いを区別できない — 計画レビュー 4 周目 P1-5)。**CI の試験クラスタで `pg_stat_statements` を事前読み込みし `track = all` にする必要がある**(既定の `top` は関数内の SQL を数えない — 5 周目 P1-5)。**認証の DB 試験は `backend/tests/db_fixtures.py` の `disposable_postgres_cluster()`(`:639` の `docker run`)で起動したクラスタに接続する**ので、**その起動引数**(`shared_preload_libraries`・`pg_stat_statements.track`)を変更対象とする。ステップ 1 で確かめ、ステップ 8 の同じコミットで変える(6 周目 P1-3)。**照会を省く変異・別の照会に替える変異が red**

## 10. ステップ 1 の決定と計画の更新

**ステップ 1 の実測で、正規化が案 A(migration の通常関数 + 生成列)以外の形に決まった場合、または計数の直列化に一意索引を選んだ場合は、ステップ 6 の方式・検査・合格条件を計画書と本書で更新し、実装に入る前に計画レビューへ戻して人間の承認を受け直す**(計画レビュー 3 周目 P1-8・5 周目 P1-7)。どちらでもなければ計画どおり進める。

### 10-1. ステップ 1 の実測(2026-10-05)

**環境**: 使い捨てコンテナ `postgres:17.11-bookworm`(試験クラスタと同じイメージ)・initdb 引数 `--encoding=UTF8 --locale-provider=libc --locale=C.UTF-8`(`docker-compose.yml:10` と同じ)・glibc 2.36。起動引数に `-c shared_preload_libraries=pg_stat_statements -c pg_stat_statements.track=all -c track_functions=all` を付けた。測定の SQL はリポジトリに入れない(結果だけをここに書く)。

#### ① 正規化関数(案 A の成否)

| 測定 | 結果 |
| --- | --- |
| 利用者定義関数を呼ぶ生成列への `INSERT`(呼び出し側に `EXECUTE` なし) | **`permission denied for function`** で失敗 |
| 同じく `UPDATE … SET name`(生成列の参照列を更新) | **失敗**(同じエラー) |
| `UPDATE … SET retired_at`(生成列の参照列でない列だけを更新) | **成功**(生成列を再計算しないので `EXECUTE` は要らない) |
| 呼び出し側へ `EXECUTE` を与えた後の `INSERT` | 成功(`' Foo '` → `foo`・`E'\tＦＯＯ\n'` → `foo`) |
| 関数のスキーマに `USAGE` が無く `EXECUTE` だけがある場合の `INSERT` | 成功(実行時は `USAGE` を見ない) |
| 生成列への `CHECK (char_length(...) <= 64)` | 65 文字を拒否 |
| `alembic` の比較(`compare_metadata`)で生成列の式を変えた場合 | **差分も警告も出ない**(`backend/migrations/env.py` は `compare_server_default` を指定していない)。**`alembic check` は式の違いで red にならないが、式の守りにもならない** → 式は schema manifest かスキーマ監査で照合する(ステップ 6) |
| `pg_get_expr` の逆構文化 | `norm_sql(name)`(`search_path` 上のスキーマは省かれる) |

**既存の検査との衝突**: 移行バッチ用ロールは `tenants` に `INSERT` を持つ(`contracts/authz/product/migration-batch-role.json` の `permissions`)が、関数の `EXECUTE` は**空であることを要求**されている(同資産の `active_role_shape.function_execute: []`・`backend/src/pitchlog/authz/product_catalog.py:865`・検査対象スキーマは `:1151-1170`)。**案 A は、移行バッチ用ロールに正規化関数の `EXECUTE` を与えないと移行の `INSERT` が失敗する**。正本(data-model.md 3-2 節「移行バッチの書き込み経路」の条件の表 `:294-303`)は関数の実行を禁じておらず、空の要求は TSK-442 の資産と検査の不変条件である。

**提案(人間の判断待ち)**: **案 A1 = 案 A + 移行バッチ用ロールに正規化関数 1 件だけの `EXECUTE` を与え、`function_execute` を「空」から「資産で宣言した集合と exact」へ変える**。正規化関数は表を読まない純関数(`LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE`・`SECURITY INVOKER`)なので、与えても到達できる行は増えない。**この安全条件は記述でなく検査で守る**(計画レビュー 7 周目 P1-1 — `CREATE OR REPLACE` は所有者と権限を保ったまま中身を変えられる): スキーマ `public`・所有者 `pitchlog_owner`(migration の関数と同じ)・`SECURITY INVOKER`・`IMMUTABLE`・`SET search_path = pg_catalog, pg_temp`・本体は組み込み関数だけを完全修飾で参照する、をカタログで照合し、`SECURITY DEFINER` 化・表の参照・所有者の変更・`search_path` の除去を変異試験で red にする。移行バッチ用ロールは所有権を持たず(資産の `ownership: []`)、`public` には `USAGE` だけなので、差し替えの経路を持たない(ステップ 6。`SET search_path` を付けた関数を生成列で使えることもステップ 6 で確かめる)
- 退けた案: **A2**(正規化関数を `PUBLIC` 実行可にし、検査から純関数の種別を除く)は必要より広い / **D**(生成列ではなくトリガで列を埋める)はトリガ関数から正規化関数を呼ぶ時点で同じ `EXECUTE` が要り、避けるには `SECURITY DEFINER` のトリガ関数が要る(既存の migration に `SECURITY DEFINER` は 0 件)/ **B** は v0.4 に反する(3 節)
- **計画への影響**: ステップ 7 の合格条件「移行バッチ用ロールの関数 EXECUTE 0 件が全スキーマで維持」と、ステップ 3 の「0 件の検査」の書き方を変える → **計画の更新と再承認**(本節の冒頭の規則)
- 後続への申し送り: テナントを作る管理経路(U-A2)の関数所有ロールも、生成列のために同じ `EXECUTE` を要る

**実現式**(案 A1 で使う): `lower(btrim(normalize(t, NFKC), <White_Space の 25 文字>) COLLATE pg_c_utf8)`。
- 組み込みはすべて `IMMUTABLE`(`normalize`・`btrim`・`lower` の `provolatile = i`)
- **小文字化は組み込みの照合 `pg_c_utf8`(PG 17 の builtin プロバイダ)で行う**: 試した 8 文字(`İ`・`ẞ`・`ΑΣ`・`Ǆ`・`Ⅻ`・`Ａ`・`ﬀ`・`K`)で libc の `C.UTF-8` と結果が同じで、**OS の glibc の版に依らない**(libc の照合は glibc の更新で結果が変わり得て、生成列と一意索引の前提が崩れる)
- `COLLATE "C"` は ASCII しか小文字化しない(`ÄÖ ΣΑ ǅ` が変わらない)ので使わない

#### ⑦ 「前後の空白」の範囲

- **Unicode の `White_Space` 性質の 25 文字**: U+0009〜U+000D・U+0020・U+0085・U+00A0・U+1680・U+2000〜U+200A・U+2028・U+2029・U+202F・U+205F・U+3000
- `btrim(text)` の既定は U+0020 だけを除く。**文字の一覧を第 2 引数に渡す `btrim`** と、同じ一覧の正規表現のどちらでも、前後のこれらを除いて内側の空白を残すことを確かめた。**正規表現の処理系を通さない `btrim` を採る**
- NFKC は U+3000・U+00A0 などを U+0020 に変えるが、タブ・改行・U+0085 は残す(実測)。だから一覧は NFKC の後にも要る
- ステップ 6 で data-model.md 8-1 節にこの範囲を書き添える(実装追随)

#### ② 計数の行が無い場合の直列化

同じ `(scope_key, window_start)` への 16 並行 × 200 回(`pgbench`・計 3,200 回)で測った:

| 手段 | 行数 | 計数の合計 |
| --- | --- | --- |
| 直列化なし(更新して、無ければ挿入) | **15 行**(重複)— `query returned more than one row` で中断が出る | 16 |
| **トランザクション単位の勧告ロック**(`pg_advisory_xact_lock`)→ `SELECT … FOR UPDATE` → 無ければ挿入・有れば更新 | 1 行 | 3,200 |
| 一意索引 `(scope_key, window_start)` + `INSERT … ON CONFLICT DO UPDATE` | 1 行 | 3,200 |

**提案(人間の判断待ち)**: **勧告ロックを採る**。どちらも数え落としは無い。違いは波及の範囲:
- **一意索引**は 3-4 節の業務的一意性に行が要り(`test_schema_manifest.py` の `_UNIQUE_ROLES` は一意制約に `business_unique` などの役割を要求する — `:55`・`:323-324`)、schema manifest・ORM・スキーマ監査・**受入突合シート(新しい行は人間の判定)**まで波及する
- **勧告ロック**はスキーマを変えない。鍵は 2 引数の形(`pg_advisory_xact_lock(int4, int4)` — 第 1 引数を計数専用の定数にして、他の用途の勧告ロックと名前空間を分ける)。ハッシュの衝突は無関係な単位を直列化するだけで正しさを壊さない。書き込みは認証関数だけ(`function_only`)なので、全経路がロックを通る
- **鍵の作り方**(計画レビュー 7 周目 P1-2): `(scope_key, window_start)` を関数の中で 1 回だけ決め、その値をロックの鍵・照会・更新のすべてに使う。**ロックは照会の前に取る**。カウンタ表を書く関数はチームのログインと管理者計数の 2 本で、**どちらも同じ手順を通す**(試験は両方で、行が無い状態からの並行試行)
- 勧告ロックでは、行の有無で実行する SQL(挿入か更新か)が分かれる。これは**過去の失敗の有無**で決まり、**チーム名の存在やパスワードの誤り方では決まらない**(不変条件②の対象外の差)。一様性の試験(ステップ 8)は、失敗の種類どうしを**同じ計数の状態から**比べる
- 一意索引を選ぶ場合は、本節冒頭の規則により計画を更新する

#### ③ 受理記録の無い中間コミットで red になる範囲

**方法**: `origin/develop`(`85fce8a7` — #87 のマージ後)の使い捨て worktree で、β のステップ 6 に近い変更を入れた。製品 DDL 資産(`contracts/authz/product/ddl-elements.json`)に `migration_trigger` の関数要素を 1 件足し、ランタイム契約の導出欄(`derive_runtime_contract_fields`)・`source_digest`・生成モジュール(生成器の `render`)を整合させた。受理記録は書かずにコミットし、CI と同じ形(PR の synthetic merge・`GITHUB_EVENT_NAME=pull_request`)で検査を走らせた。

| 検査(CI のジョブ) | 結果 | 理由 |
| --- | --- | --- |
| 生成器の `check`(P4) | **green** | 導出欄・`source_digest`・生成モジュールを揃えれば通る |
| `scripts/check_frozen_baselines.py --ci`(harness) | **green** | — |
| **`scripts/check_tenant_boundary_bypass.py`(tenant-boundary-bypass)** | **red(終了コード 2)** | `base-allowlist.json.baseline_control.history: movement と追記 record 件数が不一致: moved=True, records=0` — **受理記録の検査そのもの**。**契約の読み込みの段階で止まるため、迂回の走査そのものはステップ 13 まで走らない**(ステップ 13 では `--base-ref` との PR 全体の差分を走査するので、見落としにはならず遅れるだけ) |
| **`tests/test_frozen_archive.py`(harness)** | **red(12 件)** | `比較 corpus の入力が動いた` — corpus(`tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs`)は `contracts/tenant_boundary` の木全体を含む。**受理記録とは別の検査**で、**同じコミットで corpus の digest を再 pin すれば green にできる**(前例 `a74a62b0`・`b8fd5fe7`) |
| それ以外の凍結関係のハーネス試験(5 ファイル・519 件) | green | — |
| backend の非 DB 試験(契約・資産を読む 18 ファイル) | 失敗 43 件。**すべてダミー関数が migration・本体・写像表に無いことによる**(`製品関数ACL宣言がmigrationの37関数とexact-set不一致` ほか)。**受理記録に由来する失敗は 0 件** | 実際の β のステップでは、関数を migration・本体・写像表と同じコミットで足す |

**決定**:
- 中間コミットで許容する red は、**tenant-boundary-bypass ジョブの受理記録の検査(上の終了コード 2)だけ**とする。各ステップでは、その出力がこの 1 行だけであることを確かめる
- **`contracts/tenant_boundary` を変えるステップ(5・6・7 と本体を直すステップ)は、同じコミットで比較 corpus の digest を再 pin する**。harness ジョブを red にしない
- **迂回の走査がステップ 13 まで走らないことへの手当て**(計画レビュー 7 周目 P1-3): 検査器は履歴の検査(`scripts/check_tenant_boundary_bypass.py:6213`)を走査(`:6220` 以降)より先に行い、走査だけを回す引数は無い(引数は `--root` と `--base-ref` だけ — `:6271-6272`)。そこで**各ステップで、履歴の検査(`_validate_repository_histories`)だけを何もしない関数に差し替えた同じ走査を一時実行**し(差し替えはリポジトリに入れない)、違反 0 件の出力を worklog に残す。ステップ 13 では現行の検査をそのまま通す。PR 本文にもこの扱いを書く

#### ④⑤⑥ 失敗経路の一様性の観測手段

最小の認証関数(`SECURITY DEFINER`・`search_path = pg_catalog, pg_temp`・照会 2 件 + 照合 1 回 + 失敗時の計数)で、失敗 3 種(存在しない名前・誤った PW・無効テナント)と成功を比べた:

| 観測 | 結果 |
| --- | --- |
| `pg_stat_statements`(`track = all`)の関数内 SQL | **失敗 3 種で同じ `queryid` の 4 文がそれぞれ 1 回**。成功は計数の 1 文が無い(不変条件②は成功を対象外とする) |
| `pg_stat_statements.track = top`(既定) | トップレベルの 1 文しか記録しない → **関数内の照会は観測できない** |
| `pg_stat_user_functions`(`track_functions = all`)の `crypt` | どの経路も **1 回**(C 言語の関数も数える) |

**試験クラスタで使う条件**:
- `disposable_postgres_cluster()` の `docker run`(`backend/tests/db_fixtures.py:639`)に **`-c shared_preload_libraries=pg_stat_statements`** を足す(サーバー起動時にしか効かない)。`pg_stat_statements.track` と `track_functions` は superuser が後から変えられるが、起動引数にまとめる。**既存のコード・資産で `shared_preload_libraries`・`pg_stat_statements`・`pg_extension` を参照するものは無い**(`backend`・`contracts`・`scripts`・`tests` を検索して 0 件)
- **`CREATE EXTENSION pg_stat_statements` は `public` に置かない**: `public` に置くと移行バッチ用ロールの関数 EXECUTE の検査(`PUBLIC` 実行可の関数が入る)と、ステップ 3 で足す拡張の exact 照合に当たる。**一様性の試験の中で、カタログ検査の後に専用のスキーマへ作る**
- 統計は別の接続から読む。`pg_stat_user_functions` はセッションの終わりかフラッシュで反映される(測定は新しい接続で読んだ)。試験では `pg_stat_force_next_flush()` か接続の切り替えで確実にする(ステップ 8 で確定)

## 11. ステップ 2 — 新しく作るファイルとコア領域の paths の照合(2026-10-05)

`origin/develop`(`85fce8a7` — #87 のマージ後)を取り込んだ上で(マージコミット `2fc11f9b`・衝突 0 件)、β が新しく作るファイルを `.claude/core-areas.json` の paths と `fnmatch.fnmatchcase` で照合した(`scripts/core_guard.py:467` と同じ関数。`*` は `/` にも一致する)。

| 新しく作るファイル(置き場) | 一致する paths | 領域 |
| --- | --- | --- |
| `backend/migrations/versions/0027_*.py` | `backend/migrations/*` | テナント分離・データ移行ほか |
| `contracts/authz/product/function-bodies/**`(認証関数・内部関数の本体、拡張・スキーマの要素の本体) | `contracts/authz/*` | テナント分離 |
| `contracts/authz/product/*.json` に要素を足す場合の新しい資産ファイル | `contracts/authz/*` | テナント分離 |
| `contracts/tenant_boundary/history-snapshots/<digest>`(ステップ 13 の受理記録) | `contracts/tenant_boundary/*` | テナント分離 |
| `backend/src/pitchlog/authz/*.py`(一般化・`rederive` に新しいモジュールを足す場合) | `backend/src/pitchlog/authz/*` | テナント分離 |
| backend の新しい試験 — **`backend/tests/test_authz_*.py`・`backend/tests/test_product_authz_*.py`・`backend/tests/product_authz_*.py`・`backend/tests/db/*` のどれかの名前にする** | 同名の paths | テナント分離(`db/*` はデータ移行ほかも) |

**照合の結果: 全件一致 → `core-areas.json` へ paths を登録しない**(plan.md ステップ 2 の規則。DoD の paths 登録はこの記録で満たす)。**ステップ 3 の「(ステップ 2 で追加層を宣言した場合だけ)paths を登録」は行わない**。

**置き場の規則(以降のステップの拘束)**:
- backend の新しい試験は上の 4 つの名前のどれかにする。**`backend/tests/test_authn_*.py` のような名前はどの paths にも一致しない**(実測で不一致)ので使わない
- ハーネス側(リポジトリ直下の `tests/`)には新しい試験ファイルを作らず、既存のコア領域の試験(`tests/test_check_authz_catalog.py` など)に足す。**`tests/test_authn_*.py` も不一致**(実測)
- 上の表に無い場所へ新しいファイルが要るようになったら、そのステップに入る前に照合し直し、一致しなければ追加層の宣言(`scripts/core_guard.py:31` と `tests/test_core_guard.py`)を JSON より前の別コミットで入れる(`core_guard.py:302-314`)

## 12. ステップ 3 — 資産基盤の一般化 1 の実現(2026-10-05)

| 項目 | 実現 |
| --- | --- |
| 関数種別 `definer` | `_PRODUCT_FUNCTION_KINDS` に追加(`asset_spec.py`)。**「付与先・所有ロール・スキーマ」は種別単位ではなく関数の行ごとに宣言する**(`schema_name` が `schemas` に、`owner_role_id` が `roles` に宣言済みであること・`acl_expectations` と `revoked_acl_expectations` が配列であること・`definer` は `security_mode = definer` であることを検査)。種別ごとの付与先の正しさは、ステップ 7 の独立の期待集合で照合する |
| 適用手順 | `definer` 関数の群は手順 3(補助関数)の後、拡張の群は手順 2(DB とスキーマ)の後に、**宣言があるときだけ**加える。手順の連番・取り外し番号・実行の繰り返しは手順数から導く(`range(1, 8)`・`8 - n` の固定を廃止) |
| 拡張 | `extensions` は任意の要素群(未宣言・空配列を許す)。実カタログの照合は `PRODUCT-CATALOG:EXTENSIONS`(`pg_extension` と所属スキーマを、`plpgsql` を除く**DB 全体**で exact)。取り外しは `DROP EXTENSION IF EXISTS`(`CASCADE` なし) |
| 取り外しの `PUBLIC` 復帰 | `migration_trigger` だけ。`rls_helper` と `definer` は `DROP FUNCTION`。未知の種別は例外 |
| 関数 ACL の引数の形 | 固定集合 `{"", "uuid, boolean"}` を廃し、**リポジトリの製品資産の宣言**から導く(形の検査 = 型名の並びだけを許す正規表現) |
| 移行バッチ用ロールの関数 EXECUTE | 検査対象スキーマ = 製品資産の `schemas` の全件。期待集合 = `migration-batch-role.json` の `function_execute`(要素は `schema_name`・`function_name`・`identity_args` の 3 キー exact。製品資産に宣言された関数だけを許す)。**現時点の宣言は空のまま** |

**後続ステップへの注意(推論 — 実測はしていない)**:
- `PRODUCT-CATALOG:EXTENSIONS` は DB 全体の拡張を見る。**ステップ 8・10 で試験クラスタに `pg_stat_statements` を作ると、製品カタログの検査が red になる**(10-1 節 ④〜⑥)。その時点で、拡張を製品資産に宣言しない別の DB に置くか、観測用の拡張を検査の外にする根拠を決める
- 関数 ACL の引数の形はリポジトリの資産ファイルから読むので、試験の中で複製した資産に新しい引数の形を足しても `product_function_id` は受けない。ステップ 5 以降で認証関数(引数 `text` など)を足すときは、資産ファイルへの宣言と同じコミットで足す
