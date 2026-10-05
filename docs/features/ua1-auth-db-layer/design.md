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

### 2-1. ステップ 4 — 固定値の全数探索と置き換え(2026-10-05)

**探索の範囲と方法**(Codex の報告 — 行番号は変更前): `backend/src`・`backend/tests`・`scripts`・`tests` の Python を AST で全走査し、整数リテラル `4`・`8`・`37`・`38`(43・106・20・84 箇所、計 253 箇所)を確認した。ロール名の列挙と `range(1, 8)` は別に検索した。

| 位置 | 固定値 | 扱い |
| --- | --- | --- |
| `scripts/check_authz_catalog.py:207-249`・`:4366`、`backend/tests/test_authz_product_roles.py:40-80`・`:184` | 4 ロールの列挙・件数 | **独立の期待集合**(`backend/src/pitchlog/authz/product_role_contract.py`)へ置換 |
| `backend/src/pitchlog/authz/product_control_access.py:22-31`、`scripts/check_authz_catalog.py:3805`・`:3871`、`backend/tests/test_authz_product_control_access.py:254` | 補助関数の列 ACL 8 件 | 検査器は宣言から導く。試験の依存列集合は意味の検査として残す |
| `scripts/check_authz_catalog.py:3753`、`backend/tests/test_authz_product_table_access.py:248` | 表 ACL をアプリ用の固定集合とする扱い・件数 | アプリ用の独立の検査は残し、関数所有ロールの宣言を受ける |
| `scripts/check_authz_catalog.py:3992`・`:4038`・`:4067`、`backend/tests/test_authz_product_function_acls.py:253`・`:262` | migration 関数 37 件・保護関数 38 件 | 資産・migration・ランタイム契約の集合照合へ置換 |
| `backend/tests/test_product_authz_catalog.py:433`・`:436-448`、`backend/tests/test_authz_runtime_contract_generator.py:477`、`backend/tests/db/test_runtime_contract_product_integration.py:92`・`:180` | ロール・関数・列 ACL の件数 | 資産から導く(表 ACL の件数の照合を追加) |
| `backend/tests/product_authz_cross_cutting_cases.py:60`、`backend/tests/db/test_product_authz_cross_cutting.py:94`・`:281`・`:328`、`backend/tests/test_product_authz_provisioning.py:718` | トリガ 37 件 | 宣言したトリガの集合から導く |
| `backend/tests/test_authz_product_application_steps.py:77-80`、`test_product_authz_provisioning.py:176`・`:666`・`:872`、`test_product_authz_failure_injection_points.py:86`、`db/test_product_authz_provisioning.py:306` | `range(1, 8)` | 手順数から導く |
| `backend/tests/test_authz_product_staging.py:255`、`tests/test_check_authz_catalog.py:330` | `product_role_count: 4` | 宣言の件数へ置換 |
| `backend/tests/test_product_authz_provisioning.py`(DB の取り外し検査) | 作るロール 3 件の列挙 | 資産の `creation = product_ddl` から導く |

**残した固定値**(製品のロール・ACL・関数の件数ではない): 分類プロファイルの各 4 件(`test_authz_product_classification.py:304-305`・`product_authz_other_profiles_cases.py:90-91`)/ 暫定契約の漏れの 4 件(`test_authz_product_function_acls.py:300` — 過去の受理の記録)/ 特定の手順・故障注入点の番号 / 要素セクションの位置 / PostgreSQL の表権限 8 種(`check_authz_catalog.py:4447-4448`・`test_check_authz_catalog.py:5470`)/ oracle 入力 8 資産(同 `:719`)/ 経緯の説明の「38 件」(`runtime_contract_dryrun.py:270`)。

**独立の期待集合と段階化**: ロールの属性は `product_role_contract.py` に設計値として置き(資産から読まない)、**資産の宣言と実カタログの両方**をこれと照合する(`PRODUCT-CATALOG:ROLES` は資産でなくこの集合と比べる)。**5 件目(`pitchlog_auth_fn_owner`)を要求する条件 = 資産に `authn`・`authn_crypto` スキーマ、またはそこに置く関数・同ロールが所有する関数が宣言されていること**(ロール配列を段階の判定に使わないので、ロールを 1 つ消すと必ず red)。移行バッチ用ロールの属性は同じモジュールの別の定数。

**migration 由来の関数の 2 種別**: `RETURNS trigger` = `migration_trigger`、それ以外 = `migration_function`。宣言・ACL・検査は種別込みの exact。現時点の `migration_function` は 0 件。**取り外しでは `migration_function` に何もしない**(`PUBLIC` の復帰も、宣言した付与の取り消しもしない)。→ **ステップ 6 で決め直す(推論 — 未実測)**: 正規化関数に資産から `EXECUTE` を与えると、取り外しで付与が残り、`DROP ROLE` が「依存するオブジェクトがある」で失敗するおそれがある。また migration が作った直後の状態(`PUBLIC` 実行可かどうかは 0027 の書き方による)へ戻らない。ステップ 6 で、0027 の `REVOKE` の有無と合わせて取り外しの文を決め、適用 → 取り外しの往復試験で確かめる

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
| 事前検査 | 退役していないテナントの正規化名の重複・64 文字超・認証主体の重複・トークンのテナント食い違いがあれば **migration を止める**(名前を書き換えない)。製品 `FORCE` RLS 下では所有者にも行が見えず、複合 FK の作成だけではテナント不一致を見逃した。検査対象 3 表の `relforcerowsecurity` を読み、`FORCE` の表だけ同じ migration トランザクション内で一時的に `NO FORCE` にして全行を検査し、成功時は元の状態へ戻す。失敗時はトランザクションのロールバックで戻る。 |
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

**値の妥当条件(全キー共通)**: JSON の整数で **1 以上 2,147,483,647 以下**(上限は日時の計算があふれない範囲 — 約 68 年分の秒数。実装の敵対レビュー P1-3 で追加)。**それ以外(欠落・文字列・0 以下・小数・上限超え)は不正値**として扱い、該当の関数は fail-closed(発行しない / 延長しない / ログインを拒否 / 管理者計数は拒否)。**β は `auth.team_login.*` を読んで妥当性を確かめるが、ロックは適用しない**(7 節)

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

## 13. ステップ 5 — `rederive` と受理記録の雛形(2026-10-05)

- **`rederive`**: `cd backend && uv run python -m pitchlog.authz.runtime_contract_generator rederive --base <rev>`(`runtime_contract_generator.py` の `rederive_repository`)。終了コード = 変更なし `0`・変更あり `3`・エラー `1`
  - `--base` はコミット SHA に正規化し、**HEAD の祖先**かつ製品状態であることを要求する。`origin/develop` の先端との一致は要求しない(最終の一致は ステップ 13 の手動ゲート)
  - 導出欄が比較元から動いたら `runtime_contract_revision` と `current_identifiers` を**比較元 + 1**、戻れば比較元の値。何度走らせても + 1 を超えない。書いた後に拘束を確かめ、違えば元へ戻して止まる
  - **ステップ 6・7 で使う比較元 = `git merge-base HEAD origin/develop`**(取り込み後に develop が進むと `origin/develop` は HEAD の祖先でなくなり、`rederive` は止まる — 2026-10-05 に実測。#92 の docs だけが入った)
- **受理記録の雛形**: `cd backend && uv run python -m pitchlog.authz.runtime_contract_acceptance --repository <複製> --base <S> --acceptance-id … --approved-by … --approved-on … --reason … --movement-fact … --output <リポジトリ外のパス>`(`runtime_contract_acceptance.py`)。出力 = 追記する v2 記録 1 件と、要る history snapshot(base64)。射影・`change.aspect` の導出・予約語の検査は `scripts/frozen_history.py` を再利用する(凍結資産の検査器は変えていない)。承認者・承認日の既定値は無く、ドライランでは `DRYRUN`・`1970-01-01` を明示する
- ステップ 12・13 の手順(Codex の報告を要約): 12 = H の複製で雛形を出し、`baseline_control.history` へ追記・snapshot を配置して `git write-tree` で D を得る / 13 = `git fetch` の後に `HEAD == H`・`origin/develop == S`・同じ代替値での D の一致を確かめ、実際の承認者・承認日で書き、コミット後に代替値へ戻した tree SHA を D と再照合する

## 14. ステップ 6 — migration 0027 と正規化関数(2026-10-05)

- **migration**: `backend/migrations/versions/0027_tenant_login_identity.py`(**develop の取り込みで `0028_tenant_login_identity.py` へ繰り下げた — 19 節**)。正規化関数 `public.authn_normalize_team_name(text)`(10-1 節 ① の安全条件)・`tenants.retired_at`・生成列 `name_normalized`・`uq_tenants_active_name_normalized`(`WHERE retired_at IS NULL`)・`CHECK (char_length(name_normalized) <= 64)`・`uq_tenant_auth_subjects_tenant`・`uq_tenant_auth_subjects_tenant_id`・トークンの複合 FK(`MATCH FULL`)・事前検査 4 種・downgrade
- **`migration_function` の取り外し**(2-1 節の持ち越しの決着): **migration が関数を作った直後の状態へ戻す** = 資産が与えた直接の付与を取り消し、資産が剥奪した `PUBLIC` の実行権を戻す(`migration_trigger` と同じ考え方)。直接の付与を残すと付与先ロールの `DROP ROLE` が依存で失敗するため。**往復(適用 → 取り外し)で関数 ACL が適用前と一致し、`DROP ROLE` が成功する**ことを `backend/tests/db/test_product_authz_round_trip.py` で確かめた。2 節の表の「取り外しの `PUBLIC` 復帰 = `migration_trigger` だけ」は、**migration 由来の関数(トリガ・通常)を戻し、`definer` と `rls_helper` は戻さない**と読み替える
- **生成列の式の照合**: schema manifest の列定義に `generated_expression` を許し(生成列に限る。空の式・通常の既定値との併存は拒否 — `backend/tests/test_schema_manifest.py`)、スキーマ監査が実カタログの式と照合する(`alembic check` は式の違いを検出しない — 10-1 節 ①)
- **受理記録の検査の文言**: このステップから、受理記録の無い中間コミットの red は「`base-allowlist.json.baseline_control.history: 履歴末尾と 7 資産の識別値が不一致`」(ランタイム契約の識別値が比較元 + 1 に動いたため)。10-1 節 ③ の「movement と追記 record 件数が不一致」と同じ `_validate_repository_histories` の検査で、差し替えた走査は違反 0 件
- **派生資産**: data-model.md の digest 2 か所(`shared-preconditions.json` の blob・`schema-manifest.json` の SHA-256)/ 受入突合シートの再生成(判定の持ち越しで 11 行が空になった → 人間の判定 — worklog)/ 比較 corpus の digest の再 pin(`tests/fixtures/frozen-archive-cases/manifest.json`)

## 15. ステップ 7 — 認証の資産一式(2026-10-05)

- **宣言**: ロール `pitchlog_auth_fn_owner` / スキーマ `authn`・`authn_crypto` / 拡張 pgcrypto(`authn_crypto`。全メンバー関数の `PUBLIC` を剥奪し認証関数所有用ロールにだけ与える)/ 関数 11 件(5 節の 9 件 + 内部の補助 2 件)。独立の期待集合は `backend/src/pitchlog/authz/product_authn_contract.py`(関数の署名・付与先・スキーマ・拡張・表/列 ACL)
- **付与先**(全関数 = 所有 `pitchlog_auth_fn_owner`・`SECURITY DEFINER`・`search_path = pg_catalog, pg_temp`):

| 付与先 | 関数 |
| --- | --- |
| `pitchlog_app` | `login`・`verify_token`・`logout`・`change_password` |
| `pitchlog_management_fn_owner` | `issue_initial_password`・`reset_password`・`revoke_tenant_tokens`・`record_admin_login_failure` |
| 付与しない(内部) | `password_policy_ok`・`setting_positive_integer`(設定値の妥当性 — 6 節)・`record_failure`(計数の共通部) |

- **認証関数所有用ロールの表/列権限**: 認証主体 = `SELECT, INSERT` / 認証情報・トークン・計数 = `SELECT, INSERT, UPDATE` / `tenants` = 列 `id, name_normalized, enabled, retired_at` の `SELECT` / `system_settings` = 列 `key, value` の `SELECT` / `public` の `USAGE` と正規化関数の `EXECUTE`。`DELETE` は与えない(物理削除しない)
- **計数の勧告ロックの鍵**: `pg_advisory_xact_lock(87001223, hashtext(scope_key || ':' || epoch(window_start)))`(第 1 引数 = 計数専用の定数)。`(scope_key, window_start)` を 1 回だけ決めて鍵・照会・更新に共用し、照会の前に取る(10-1 節 ②)
- **構成検査の置き換え**: 「アプリが実行できる `SECURITY DEFINER` は 0 件」を、**`pitchlog_app` が実効 `EXECUTE` できる `definer` の集合 == 資産で `pitchlog_app` に付与した集合**の exact 照合へ(最低要求④の試験ではない — 7 節 J-2)。危険ロールへの到達の試験は、所有者の照会を資産で宣言した全スキーマへ広げた
- **ステップ 8 で特に確かめる点**(レビューで気づいた点 — 推論): `login` のダミーハッシュ(`$2a$12$…`)が本当にコスト 12 の有効な bcrypt 値で、実ハッシュと同じコストで照合されること / 設定値が欠けたときは計数を更新しない分岐がある(失敗の種類の間の一様性の比較から、設定値の欠落は外すか、別に扱うかを決める)

## 16. ステップ 8 — アプリ用の認証関数の試験(2026-10-05)

- **観測の置き場**: 試験クラスタの起動引数に `shared_preload_libraries=pg_stat_statements`・`pg_stat_statements.track=all`・`track_functions=all`(`backend/tests/db_fixtures.py`)。**`pg_stat_statements` の拡張は製品 DB でなく同じクラスタの保守用 DB(`postgres`)に作り、製品 DB の `dbid` で絞って読む**(製品 DB に作ると `PRODUCT-CATALOG:EXTENSIONS` — DB 全体の拡張の exact 照合 — が red になるため。12 節の申し送りの決着)。統計はクラスタ共有なので製品 DB の関数内の SQL も観測できる
- **一様性の比較の範囲**: 設定値が揃った状態の失敗 5 種(存在しない名前・誤 PW・無効テナント・退役テナント・65 文字以上の名前)の間で、計数の更新・`crypt` の回数・関数内 SQL の `queryid` と回数を比べる。**設定値の欠落・不正値は計数を更新しない分岐**があるので、比較から外し「発行しない・延長しない」の試験で扱う(15 節の申し送りの決着)
- **関数本体の是正**: `change_password` は新パスワードが `NULL` のときポリシー判定が三値論理で通り、書き込みで例外になっていた → ポリシー結果を `IS NOT TRUE` で拒否し、現行 PW の照合も `IS DISTINCT FROM` にした
- 試験: `backend/tests/db/test_product_authz_authn_app.py`(20 ケース — 計画書 #8 の各項目と、`crypt` の省略・コストの変更・設定照会の省略・勧告ロックの除去の各変異)

## 17. ステップ 9 — 限定関数・越境・ACL の試験(2026-10-05)

- 試験: `backend/tests/db/test_product_authz_authn_limited.py`(11 ケース — 計画書 #9 の各項目)
- **関数本体の是正**: `issue_initial_password`・`reset_password` も、パスワードが `NULL` のときポリシー判定が三値論理で通り抜けていた(16 節の `change_password` と同じ型)→ `IS NOT TRUE` で拒否し、何も更新しない
- **`function_only` 4 表への直接アクセスの検査対象**: `pitchlog_app` と試験用の非特権 LOGIN ロール。**`pitchlog_owner`(表の所有者)は ACL で拒否できないので対象外**(所有者は migration を流す信頼済みのロール — 正本 3-2 節)。限定関数の実行拒否は `pitchlog_owner` も検査する
- **ID を返す関数**: カタログ上 `uuid` を返すのは `login` と `verify_token` の 2 件。`verify_token` の値は発行 ID でなくテナント ID であることを試験で確かめる(5 節の表どおり)

## 18. ステップ 10 — 最低要求 ②③・④の適用判定・DB ログ・露出の事実(2026-10-05)

- 試験: `backend/tests/db/test_product_authz_authn_security.py`(6 ケース — `authn` 全関数の `PUBLIC`・信頼しない LOGIN ロールの `EXECUTE` 拒否 / スキーマの所有者・`USAGE`・`CREATE` / 全関数の固定 `search_path` / `pg_temp` に同名の表・関数・演算子を置き呼び出し元の経路を変えても結果が変わらない / DB ログ / トークン ID)
- **最低要求④の適用判定**: 既存の判定と同じく **DB 試験の docstring** に置いた —「最低要求④の適用判定: authn は共有対象行を返さないため対象外。」(集合を返す認証関数・共有対象表への参照が無いことも検査する)。**PR と ④ 注記タスクへの連絡は ステップ 12(`/pr`)で行う**(7 節 J-2)
- **DB ログ**: 試験内の superuser セッションで `log_parameter_max_length = 0`・`log_parameter_max_length_on_error = 0`・`log_statement = all` を設定し、アプリ用ロールでバインド引数付きで呼んで、通常文・エラー文のどちらでも `docker logs` に試験用パスワードが出ないことを表明する(ログ本文は試験の出力へ出さない)
- **露出の事実**(`contracts/authz/product/exposure-facts.json` の `secret_column`): 3 件の典拠を v0.4 の非露出の条文へ差し替え(8-2・8-2-A・9-3)、`tenant_tokens.id` を追加(8-3「ID の列は秘密の列として扱う」)。**4 件とも正本の逐語と一致することを確かめた**

## 19. develop の取り込みと migration の繰り下げ(2026-10-05 — ステップ 12 の前)

- **取り込んだ比較元**: `origin/develop` = `f2dc9f9b`(#94 TSK-475 のマージ後)。凍結資産(`contracts/tenant_boundary`)は develop 側で動いていない
- **migration の番号**: develop に `0027_seed_roster_status`(親 0026)が入り、β の 0027 と head が 2 本になった → **β の側を `0028_tenant_login_identity`(親 = `0027_seed_roster_status`)へ繰り下げた**。本書の 4 節・14 節の「0027」は β の migration を指す(繰り下げ後は 0028)
- **develop の新しい衛生検査**(`backend/tests/test_migration_hygiene.py` — migration の中で `op.get_bind()` 経由の `execute()` を禁止)に合わせ、**事前検査を `DO` ブロック(`IF EXISTS` → `RAISE EXCEPTION`)へ書き直した**。これで、取り込み前から落ちていた `backend/tests/test_database_configuration.py::test_same_direct_url_is_valid_when_not_pooled`(**β の事前検査が alembic のオフライン実行で結果行を読もうとして落ちていた — 影響範囲に絞った試験では見えなかった**)も直った
- **TSK-344 との順序(人間の判断)**: TSK-344 も migration を足す予定。TSK-344 が先にマージされると 0028 を取り、β は 0029 へ 2 度目の繰り下げになる(別タブ u-x1 master の全 worktree 走査 — 2026-10-05)
- **正本**: data-model.md の「migration 0027」(β が書いた 3 か所)を 0028 へ直し、digest 2 か所と受入突合シートを追随させた(新規の判定行 0)

## 20. 実装の敵対レビュー(2026-10-05 — `/pr` の前)

`codex_run.py review adversarial`(β の全実装 — `git log --first-parent 85fce8a7..HEAD`)。**P0 0 件・P1 4 件・全件採用**:

| # | 指摘 | 是正 | 帰属 |
| --- | --- | --- | --- |
| 1 | 正規化関数の安全検査が、完全修飾した別スキーマの関数呼び出しを見逃す | 本体を全字消費し、許可した関数・演算子・式の形だけを通す検査へ。完全修飾・非修飾の両方の追加呼び出しの変異が red | ステップ 6 |
| 2 | 製品 RLS を適用した DB では、`NOBYPASSRLS` の所有者から行が 0 行に見え、0028 の事前検査が素通りする | 実 DB ではトークンのテナント不一致が残っても複合 FK の追加が通った。`MATCH FULL` かつ `NOT VALID` なしでも制約の作成に依存できない。3 表の元の `FORCE` 状態を読み、事前検査の間だけ `NO FORCE` にして、成功時は復元・失敗時は migration 全体のロールバックで復元する。4 種の不整合で停止し、行・revision・`FORCE` が変わらないことを確認する DB 試験を追加した | ステップ 6 |
| 3 | 有効期限の設定値が巨大な整数だと、正しい資格情報のときだけ日時の計算のあふれで例外になる(失敗の一様性が崩れる) | 設定値の妥当条件に上限 2,147,483,647 を置いた(6 節)。上限・上限 + 1 の境界の試験 | ステップ 7 |
| 4 | 認証の資産を丸ごと消すと、独立の期待集合が 4 ロールの段階に戻り検査が消える | 製品状態では資産の有無に依らず 5 ロールと認証一式を要求する(段階の切り替えをやめた。過去の未発効契約の 4 ロール検査は別関数)。認証一式の削除の変異が red | ステップ 7(4 の段階化の撤去) |

是正中の DB 試験では、並行試験 2 件の `window_seconds = 4,000,000,000` が新しい上限を超えたため、`login` が `NULL` を返し、計数行も作らなかった。日時計算を守る上限を維持し、両試験の値を上限内の `2,000,000,000` に直した。試験値の追随なので帰属はステップ 8。
