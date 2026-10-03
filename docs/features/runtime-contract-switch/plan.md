---
feature: runtime-contract-switch
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-26・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e68781aaa090cc99ec7e7dcb
branch: feature/runtime-contract-switch
created: 2026-09-26
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: ランタイム契約をその場で製品化する(TSK-443 / TSK-424 PR B)

## 1. 背景・目的

**Notion**: [TSK-443](https://app.notion.com/p/3e593b75e68781aaa090cc99ec7e7dcb)(TSK-424 の PR B — 人間の判断 2026-09-24)

**下調べ**: [research.md](research.md)(2026-09-26)/ **詳細設計**: [design.md](design.md)

U-T1 の接続ロール真正性検査は、いま**暫定のランタイム契約**を入力にしている(`contracts/tenant_boundary/runtime-authz-contract.json`・`provisional: true`)。
TSK-424 PR A1 が製品の DDL 資産(`contracts/authz/product/ddl-elements.staged.json`)を置いたので、ランタイム契約をそこから導いた値へ切り替える。
**暫定資産は保護対象の関数 4 件(0015・0016・0017・0024)を取りこぼしている**(Notion カードの申し送り)。切り替えでこの漏れも閉じる。

**方式の変更(人間の判断 2026-09-26・山田正輝)**: 契約(`product-authz-surface/design.md` 9 節)は暫定資産の**削除**を定めていた。
しかし削除はいまの検査器で必ず不合格になり、削除を通す機構は TSK-461(`未着手`)の完了を待つことになる(research.md 1・2 節)。
→ **暫定資産を同じパスに残し、製品のランタイム契約そのものに変える(Y2)**。凍結基準は値の変更として記録 1 件で動かす。比較と理由は [design.md](design.md) 0 節。

**要件 FR/NFR との関係**: テナント分離の上位根拠は **NFR-010**(チーム間データ分離)と **FR-034**(データ所有権制御)。
**ランタイム契約・凍結基準の規律に当たる FR/NFR は無い**。法源は設計書 7.7 と 10.1・10.2。**要件書 4.0-2 と NFR-012 は根拠にしない**(research.md 6 節)。**要件書の改訂は不要**。

## 2. スコープ

### やること

1. **共有 API と生成器の新設** — `backend/src/pitchlog/authz/runtime_contract_state.py`(状態の判定・導出・述語・描画 — 副作用なし)と `runtime_contract_generator.py`(CLI: `check` / `render` / `switch`)。生成器・`check_authz_catalog.py`・試験の三者が共有 API を呼ぶ(design.md 2・3 節)
2. **二状態契約の改訂** — 判定を「暫定資産のファイルがあるか」から「中身が製品状態を満たすか」へ変える(design.md 3 節)
3. **検査器の状態分け** — `scripts/check_authz_catalog.py` のキー集合・件数 33・暫定資産を比較元にした照合を、未発効状態と製品状態で分ける(design.md 3 節)
4. **製品 DB での統合試験**(PR A2 の適用器を使う — design.md 5 節)と、**製品化のドライラン**
5. **切り替えと凍結基準の受理を 1 コミットで** — staged を最終パスへ `git mv`・未発効状態の欄を除去・ランタイム契約を製品化・モジュールを再生成・`base-allowlist.json` に v2 記録 1 件(design.md 1・4 節)
6. **改める既存の決定への改訂注記** — `product-authz-surface/design.md` 9 節ほか・`tenant-boundary-enforcement/design.md` 3-5-a(design.md 6 節)
7. **正本の実装追随** — `data-model.md` 12-8 の TSK-443 項目・変更履歴・`docs/README.md`

### やらないこと

- **暫定資産の削除と、退去を通す機構**(design.md 0 節で採らなかった — 退去の機構は TSK-461 が持つ)
- **凍結の外部ファイル 3 件(`scripts/check_tenant_boundary_bypass.py`・`scripts/frozen_history.py`・`.github/workflows/ci.yml`)の変更** — 触れると 7 資産すべての射影が動く
- 設計書 7.7 の条文の改訂(確定ゲートが要る。Y2 は条文を変えずに書ける — design.md 0 節)
- 同期モジュールの残り 2 本(`repository_contract.py`・`tenant_context_contract.py`)の生成器化(design.md 未解決 2)
- 保護対象が DB に実在しないときの検出(U-T1 の射程 — design.md 未解決 1)
- PR A2(TSK-442)の射程(適用器・実 DB 試験・移行ロールの資産・写像)
- `engine.py` の変更は、ステップ 6 の関数照会の是正(型だけでの突き合わせ)に限る(2026-10-03 の改訂)。DB に無い保護対象の検出(design.md 未解決 1)は引き続き射程外

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8(`:2846`) | 残件の「ランタイム契約の切り替え = TSK-443(PR B)」を確定へ書き換える(同じパスで製品化したこと)。**解消済みにはしない**(適用は TSK-344) | 7.6-3 前段(実装追随の節更新)→ PR レビュー |
| `docs/design/data-model.md` 変更履歴 | 上を 1 行追記。版は上げない | 同上 |
| `docs/README.md` | 索引の data-model 行を現行化 | 同上 |
| 要件書 | **反映なし**(上位根拠の変更なし — research.md 6 節) | — |
| ハーネス設計書(7.7・10.1・10.2) | **反映なし**(条文を変えない) | — |
| ADR | **反映なし** | — |

正本ではない feature 文書(`product-authz-surface/design.md`・`tenant-boundary-enforcement/design.md`)には、改訂の注記を追記する(本文は書き換えない — design.md 6 節)。

## 4. 実装方針

**重さ分類 = コア領域**。触れるパスはすべてテナント分離(`contracts/authz/*`・`contracts/tenant_boundary/*`・`backend/src/pitchlog/authz/*`・`backend/tests/test_authz*.py` — `.claude/core-areas.json:307`・`:318-319`・`:363-365`)。`scripts/check_authz_catalog.py` は `guard_paths` にも当たる。
**生成器も `backend/src/pitchlog/authz/*` に置くので、コア領域と backend の CI の両方に入る**(design.md 2-1)。`core-areas.json` 自体は変えない。
→ 敵対レビュー必須・**人間の逐行確認必須**(設計書 6.3)。

**進め方**:
- **ステップ 1〜5 は PR A2(TSK-442)を待たない**。資産を動かさず、いまの状態(未発効)で green のまま入れられる
- **ステップ 6 の前に、PR A2 のマージを待って develop を取り込み、draft PR を作って `acceptance_id` を確定する**。A2 は「staged 資産の差分 0 行」を不変条件にしており `git mv` と衝突する。適用器(ステップ 6 の統合試験で使う)も A2 が持つ
- **最終ステップ 8 は、切り替えと受理の記録を 1 コミットで入れる**(design.md 4-1)。**全ステップのコミットが単独で green**になる(移動と記録が同じコミットに入るため、凍結基準の検査が途中で red にならない)
- **ステップ 8 は、人間が PR 上で比較元 S・ステップ 7 までの HEAD の H・ドライラン digest D を明記して受理した後に実行する**。受理の判断材料は、H までの全差分と、ドライランの差分。**「受理した差分」と「入れた差分」の一致は検査器では検出できないので、S・H・D による手動のゲートにする**(design.md 4-1)。**PR は `origin/develop == S` の間にマージする**
- **A2 が長く止まるとき**は、ステップ 1〜5 だけで PR にする判断を人間に仰ぐ(計画の改訂で行う)
- **backend のテストは `backend/` で回す**(`a75549c0` の教訓 — リポジトリルートからでは collect されない)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **共有 API の描画と、生成器の `render` / `check`**: `runtime_contract_state.py`(描画・状態の判定・述語 D1〜D5)と `runtime_contract_generator.py` を新設し、ランタイム契約の資産から `runtime_contract.py` を生成する。`DERIVED_FROM` を足す(暫定では `None`)。モジュールを生成器の出力に置き換える(design.md 1-3・2-1・2-3) | `[機械]` 生成結果と現行モジュールの差が `DERIVED_FROM` の 1 行だけ / `check` が exit 0・資産を 1 値変えた複製で非 0 / `render` の 2 回目が差分 0 / リポジトリの外で実行すると終了コード 2 / `cd backend && uv run ruff format --check src/pitchlog/authz/runtime_contract.py` / `runtime_contract.py`・`engine.py` が生成器と共有 API を import していない / `backend/` で `uv run pytest`・`uv run ruff check`・`uv run ty check` green / 凍結の外部ファイル 3 件の差分 0 行 |
| 2 | **共有 API の導出**: 製品資産(staged / 最終をパスで受ける)から `application_role.attributes` と `protected_objects` を導く。属性名の対応表と fail-closed(design.md 2-2) | `[機械]` staged から導いた保護対象 == 暫定資産の保護対象 ∪ 追加分 6 件(exact)/ 導いた属性 == 暫定資産の 7 属性 / 未知の属性キー・`role_id == rolname` の行が 0 件・2 件で失敗する変異 / 並びが辞書順で決定的 / 資産とモジュールの差分 0 行 |
| 3 | **状態の述語と違反 ID**: design.md 3-1〜3-3 の 4 状態と述語 D1〜D5・T1〜T8・U1・P1〜P11 を共有 API に実装し、`backend/tests/test_authz_runtime_contract.py` の二状態の判定をこれを呼ぶ形へ書き換える。既存の違反 ID は 3-3 の表のとおり引き継ぐ / 廃止する | `[機械]` いまのリポジトリ(未発効)で green / 製品状態の複製で正例 green / **design.md 3-2 の変異がすべて、期待した違反 ID の集合と exact に一致して red** / 暫定・未発効で既存の ID(`PROVISIONAL_ASSET_MISSING`・`GENERATED_MODULE_IS_NOT_PROVISIONAL`・`GENERATED_MODULE_SOURCE_MISMATCH`・`GENERATED_MODULE_SUPERSEDED_BY_MISMATCH`)が同じ名前で出る / 不正状態で `BOTH_STAGED_AND_FINAL` / 判定の実装が共有 API の 1 か所 |
| 4 | **検査器の状態分け**: `scripts/check_authz_catalog.py` のキー集合(`:4250-4271`)・件数 33(`:3962`)・暫定資産を比較元にした照合(`:4089-4167`・`:4321-4322`)を、共有 API の状態の判定で分ける(design.md 3-4) | `[機械]` いまのリポジトリで既存の検査がすべて green(挙動不変)/ 製品状態の複製で green・`pending_switch` を残す変異・`provisional_contract_additions` を残す変異・保護関数を 1 件ずらす変異で red / 状態ごとに必ずどちらかの照合が走ることを試験で表明 / 検査器の中に状態の判定を別に書いていない(共有 API を呼ぶ)/ `uv run pytest tests/` と `backend/` の pytest green |
| 5 | **試験を状態で分ける**: 実リポジトリが未発効状態だと仮定している試験を、状態に応じた期待値を持つ形へ直す。対象は `backend/tests/test_authz_product_staging.py`(`:24`・`:52-60`・`:115-120`・`:147-167`)・`test_authz_product_function_acls.py`(`:154`・`:172-231`)・`test_authz_product_control_access.py`(`:35`・`:108`・`:400-425`)・`test_authz_product_classification.py`(`:29-31`)・`test_authz_runtime_contract.py`(`:192`)(research.md 3 節の 12) | `[機械]` いまのリポジトリで green / 製品状態の複製で、上の試験が**編集なしで** green / 実リポジトリの資産に対して `PROVISIONAL is True`・`pending_switch == "TSK-443"`・`len(...) == 33`・`{"public"}` を無条件に表明する箇所が 0 件(`rg` で確認し、結果を worklog に残す) |
| 6 | **(A2 のマージ・develop の取り込み・draft PR の後)製品 DB での統合試験と製品化のドライラン**: **【改訂 2026-10-03・山田正輝の承認】`backend/src/pitchlog/db/engine.py` の保護関数の所有者の照会を、`pg_get_function_identity_arguments(oid)`(引数名を含む)から `pg_catalog.oidvectortypes(proargtypes)`(型だけ)での突き合わせに変える。統合試験が、補助関数 `authz_private.tenant_has_effective_membership(p_group_id uuid, p_require_admin boolean)` を資産の `uuid, boolean` と突き合わせられず、切り替え後に照会から黙って漏れることを検出したため(トリガ関数 37 件は引数なしで影響なし)。** design.md 5 節の試験を `backend/tests/db/` に書く。`switch` を実装し、ドライランの仕組み(H の複製でステップ 8 のコミットを固定の承認値で作り、その tree の SHA をドライラン digest D として出す — design.md 4-1)を置き、複製で**全試験**を回す。複製で見つかった互換の修正(A2 が足した試験を含む)はこのステップに入れる。`switch` の拘束(`--base` の検証・revision + 1 の自己検証・保護対象の自己検証)の試験を足す | `[機械]` 製品 DB で、導出した保護対象のスキーマ 2・表 45・関数 38 がすべて実在し、接続時の検査の経路で所有者が期待件数ちょうど得られる / 危険ロールに `pitchlog_shared_fn_owner` が入る / **ドライランの複製で `backend/` の全 pytest(`tests/db` を含む — `docker compose up -d`)とリポジトリルートの `uv run pytest tests/` が green**・予定の v2 記録が `frozen_history.py` の検査を通る(予約語の検査を含む)/ `--base` に HEAD・無関係なコミット・古い祖先を渡すと止まる・revision + 2 で止まる / `switch` の 1 ファイル目の置き換えの直後に失敗させると `check` が red・再実行で green / 同じ H からのドライランを 2 回行うと D が一致する / いまのリポジトリ(未発効)でも全試験 green / S・H・D を worklog に残す |
| 7 | **改訂の注記と正本の追随**: **【例外 2026-10-03・山田正輝の許可】`data-model.md` の変更に合わせて `contracts/authz/shared-preconditions.json` の `git_blob_digest` と `contracts/db/schema-manifest.json` の `canonical_source.sha256` の 2 行を取り直す(どちらも凍結資産ではない。A2 の b3062045 と同じ)。** design.md 6 節の 7 件を `product-authz-surface/design.md`・`tenant-boundary-enforcement/design.md` に注記として追記(本文は書き換えない)/ `data-model.md` 12-8 の TSK-443 項目と変更履歴 1 行 / `docs/README.md` の data-model 行 | `[機械]` `uv run pytest tests/` のうち文書系の検査 green / `data-model.md` の版が変わっていない `[手動]` 注記が「どの決定を・いつ・誰の判断で・どう改めたか」を持つ |
| 8 | **最終フェンス: 切り替えと受理(人間が PR 上で S・H・D を明記して受理した後)**: **【例外 2026-10-03・山田正輝の承認 — TSK-467 が未マージの場合に限る】`tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs.digest` の 1 行だけを取り直す。先に動いた corpus 入力をすべて列挙し、本 PR の意図した変更(`base-allowlist.json` の記録・`runtime-authz-contract.json`・追加した snapshot)だけであることを確かめる。意図しない入力が 1 件でもあれば止めて人間に報告する。`pinned_prefixes`・`files`・`trees`・`cases`・`pull_request_number` は触らない(資産の持ち主 TSK-466 の同意あり)。この取り直しはドライランの D にも含める。** design.md 4-1 の手順で、`git fetch` の後に `HEAD == H`・`origin/develop == S`・D の一致を確かめてから、`git mv`・`pending_switch` と `provisional_contract_additions` の除去・`asset_spec.py:262` の変更・`switch --base S`・`history-snapshots/` と `base-allowlist.json` の v2 記録(`change.aspect = ["asset_snapshots", "declaration"]`・`movement_fact` に S)を 1 コミットで入れる。`approved_by` / `approved_on` は人間の発話を逐語で書く。**試験のファイルは編集しない** | `[機械]` 実行前の 3 つの一致と、コミット後の「親 == H」「承認の 2 欄を固定値に戻した tree == D」の確認の結果を worklog に残す / 生成器 `check` exit 0 / `switch` の 2 回目が差分 0 / 保護関数 38・保護スキーマ 2・保護表 45 / `baseline_control.history` の差分 0 行 / `scripts/check_tenant_boundary_bypass.py` exit 0(PR 受理モードで `acceptance_id` が一致)/ 凍結系の試験(`tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`)green / CI 全ジョブ green / このコミットの差分に試験のファイルが含まれない `[手動]` **コア領域の逐行確認**(設計書 6.3)・`movement_fact` に漏れ 4 件と v1 記録の扱いがある |

## 5. DoD(受け入れ基準)

- [ ] ステップ 1〜8 の合格条件をすべて満たす
- [ ] `runtime_contract.py` が生成器で作られ、backend の pytest が生成結果との一致を検査している(手の同期が残っていない)
- [ ] 製品状態で、暫定の値(`provisional: true`・`superseded_by`・33 件の関数集合)が生きた入力として残っていない
- [ ] 保護関数が 38 件になり、暫定資産の漏れ 4 件が閉じている。その事実が受理の記録にある
- [ ] 暫定資産の v1 記録(`PENDING_ACCEPTANCE`・「未承認(PR #72 のレビュー待ち)」)が書き換えられていない
- [ ] 凍結の外部ファイル 3 件の差分が 0 行
- [ ] 改める既存の決定 7 件(design.md 6 節)に改訂の注記がある / `data-model.md` 12-8・変更履歴・`docs/README.md` が現行化されている
- [ ] 敵対レビュー(計画・実装)を通り、人間の逐行確認が済んでいる
- [ ] 製品 DB で、スキーマ 2・表 45・関数 38 の保護対象がすべて実在し、所有者の照会が黙って飛ばす対象を持たないことが試験で示されている
- [ ] 申し送り 2 件(design.md 未解決 1・2)の行き先が Notion に記録されている

## 6. テスト計画

| NFR-019 の種別 | 足すもの |
| --- | --- |
| **単体** | 生成器の描画・導出(属性名の対応・並びの決定性)/ `check` の終了コード / `render`・`switch` の冪等性 / 原子的な書き込み(途中の失敗でファイルが変わらない) |
| **一致性** | 生成モジュール == 資産(バイト単位)/ 資産の導出欄 == 製品資産から導いた値 / 未発効状態で staged から導いた保護対象 == 暫定 ∪ 追加分 6 件 |
| **越境** | **製品 DB での統合試験**(A2 の適用器 — design.md 5 節): 保護対象 2 / 45 / 38 の実在・所有者の照会の件数・危険ロールに `pitchlog_shared_fn_owner` が入ること / 既存のロール真正性の DB 試験(`backend/tests/db/`・`test_authz_tenant_binding.py`)も回す(ただし既存の試験は製品の保護対象の全件を証明しない — design.md 1-1) |
| **故障系** | 状態の述語の変異(design.md 3-2 の全行 — 違反 ID の exact-set で表明)/ `switch` の拘束(`--base` の検証・revision + 1・保護対象の自己検証)/ 2 ファイルの置き換えの間の失敗/ 不正状態(staged ∧ 最終)/ 検査器の製品状態の変異(`pending_switch`・`provisional_contract_additions` の残存・保護関数のずれ)/ 生成器の fail-closed(未知の属性キー・アプリ用ロールの行の 0 件・2 件・リポジトリの外での実行)/ `switch` の比較元が暫定状態でないときの停止 |
| **E2E** | 該当なし(ランタイム契約はアプリの画面・API の挙動を変えない) |
