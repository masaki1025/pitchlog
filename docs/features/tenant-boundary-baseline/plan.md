---
feature: tenant-boundary-baseline
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-24・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e193b75e68781b7a4ecee5917494f11
branch: fix/tenant-boundary-baseline
created: 2026-09-24
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 7.7 適合 — tenant_boundary 資産(TSK-431)

## 1. 背景・目的

**Notion**: [TSK-431](https://app.notion.com/p/3e193b75e68781b7a4ecee5917494f11)(出所: U-T1 = TSK-390 の敵対レビュー 3 周目。**人間の判断 2026-09-20・山田正輝**により U-T1 から分離)

**設計書 7.7「凍結基準の更新経路」は U-T1 の実装進行中に develop へ入った**(PR #71)。取り込みにより U-T1 が適用対象になり、7 資産へ `baseline_control` を追加して追随したが、**敵対レビューで同型の欠陥が出続けた**ため 7.7 適合だけを分離したもの。

**要件 FR/NFR との関係**: **要件書に 7.7 の上位根拠は無い**([research.md](research.md) 4 節 — 全文検索で確認)。法源は**設計書 7.7** と参照先の 10.2・`docs/design/data-model.md` だけ。**要件書の改訂は不要。**

### 本タスクが製品コード全体の唯一のゲートである(実測)

| # | 事実 |
| --- | --- |
| 1 | `_OPERATION_REGISTRY` は空で、**`execute` は `@final`**。未登録 token は必ず例外 |
| 2 | `PRODUCT_CAPABILITY_IDS = ()` は **`repository-contract.json` からの生成物** |
| 3 | `ALLOWED_PRODUCT_MODULES = ()` / `ALLOWED_TEST_MODULES` は 1 モジュールのみで、**`tenant-context-allowlist.json` からの生成物** |
| 4 | **両方とも `FROZEN_BASELINE_ASSETS`** → 登録も allowlist 追加も 7.7 の「基準を動かす」行為 |
| 5 | **製品コードで `TenantContext` を構築している箇所は 0 件** |

**したがって本タスクが入るまで、DB を触る全単位(帯 2 の葉 6 本・帯 3 の 6 本)は製品の振る舞いを 1 行も実装できない。**

**直接の消費者**: 帯 2 の capability 登録(U-M1 = TSK-393 ほか)/ TSK-442(PR A2)/ TSK-444(PR C)。

## 2. スコープ

### やること

| | 中身 |
| --- | --- |
| **7C** | 履歴が「変更前後の実内容」を持てるようにする(7.7-2 第 3 項) |
| **7B** | 7 資産の `frozen_projection.external_files` へ合否写像の実体を入れる |
| **`required_triggers` の第 2 決定元**(2 周目 `P0-6`) | 実装に残すのは 7.7-1 の普遍下限の一般則だけとし、下限外の trigger は比較元の宣言から取得する |
| **7D の最小限**(5 周目 `P0-3`) | **比較元側 ∪ HEAD 側の資産集合を走査する**。これが無いと `baseline_set` と `declaration_location` の下限を実装したと判定できない |

### やらないこと

| 範囲 | 理由 / 受け取り先 |
| --- | --- |
| **7A** | **既に閉じている**(PR #72)。**カードの「前提・依存」欄が古い** — 本計画で現況化する |
| **7D の残り**(削除記録の置き場・履歴アーカイブ・安定した履歴 ID) | 本 PR は走査の範囲だけを直す。**新規タスクへ送り出す** |
| **7E**(バイト正規化・P2) | 現時点で差が顕在化していない(実測: CRLF 0 件・`.gitattributes` 不在)。**新規タスクへ送り出す** |
| **センチネル 7 件** | **7.7 に既存記録の訂正の規定が無い**(1 周目 `P0-1`)。**条文改訂または PO 裁定が先** |
| **「合否写像だけを変える経路」を塞ぐこと** | **7.7-4 が明示的に「本節はこれを塞がない」としている** |
| **次回以降の通常更新で比較元版の評価器を使うか** | 本 PR では決めない(2 周目 `P0-2`)。**送り出す** |
| **要件書の改訂** | 上位根拠が無い(1 節) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md`(7.7) | **反映なし** — 条文は変えない。本タスクは条文への適合であって改訂ではない | — |
| `docs/design/data-model.md` | **反映なし** | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/development/harness-evaluation.md` | **`## 候補` へ 2 件追記 + 既存候補 1 件へ 6 例目 + 変更履歴表へ 2 行**(`/pr` のクローズ処理で確定。**版は上げない** — 7.6-3 前段) | PR レビュー |
| `docs/README.md` | **台帳行の最終更新日を現行化**(2026-09-24 → 2026-09-25) | PR レビュー |

**正本体系外だが同一 PR で更新するもの**

| ファイル | 変更内容 | 理由 |
| --- | --- | --- |
| `.claude/core-areas.json` | `tenant-isolation` 領域へ `scripts/frozen_history.py` と `tests/test_frozen_history.py` を追加 | **本 PR が作った穴**(新設ファイルがコア領域のどのパターンにも該当しない)。**計画スコープ外の逸脱として worklog・コミット・PR 本文に記録済み** |
| `tests/test_core_guard.py` | `TENANT_BOUNDARY_AREA_PATH_CASES` へ同じ 2 件を同順で追加 | 上記の期待集合が人手の列挙で、順序まで比較するため |

**正本の新設・版繰り上げはない。**

## 4. 実装方針

**調査の正**: [research.md](research.md)。**設計判断の正**: [design.md](design.md)(D1〜D6)。**本節は結論だけを引き、内容を複製しない**(設計書 7.1-1)。

**重さ分類の根拠**: **コア領域(テナント分離)**。`scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` はいずれも `.claude/core-areas.json` の `tenant-isolation` の paths(実測)。**sol xhigh・敵対レビュー + 人間の逐行確認必須。**

**確定した裁定**([design.md](design.md)):

| # | 裁定 |
| --- | --- |
| **D1** | **単一検査・1 記録**。7 資産は 1 つの検査とし、**`base-allowlist.json` を履歴の authority**、他 6 資産は `history_authority: false`。記録は**7 資産すべての新旧識別値**を持つ(5 周目 `P0-1`。4 周目の `check_id` 案は撤回) |
| **D2** | **版付き record schema** — v1 は**比較元 prefix の中だけ**。**prefix は `N` 件の生 JSON 値との deep-equal**。prefix 以後の追記は明示 v2 のみ |
| **D3** | **v2 は content-addressed snapshot を持つ** — `contracts/tenant_boundary/history-snapshots/<sha256>`(追記専用)。**`aspect` は実差分から機械導出し申告値と exact-set 一致を検査**(5 周目 `P0-2`。「復元できない」を保証範囲外へ逃がす案は撤回) |
| **D4** | **評価を役割別に分ける** + **PR コンテキストでは検査器自身が PR 受理モードを強制**し、**`ci.yml` を `external_files` へ含める**(5 周目 `P0-4`。「workflow は観測しない」を保証範囲外へ逃がす案は撤回) |
| **D5** | **5 軸と宣言 token の対応を固定**し、**負例は字面ではなく実状態を変異させる**。**7D の最小限(比較元側 ∪ HEAD 側の走査)を本 PR へ戻す**(5 周目 `P0-3`) |
| **D6** | **準備の実装は新規 `scripts/frozen_history.py` へ隔離**し、**結線・`external_files` への追加・記録を最終 1 コミットで同時に行う** |

**D6 が要る理由**: **検査器は `base-allowlist.json` の `external_files` に入っているので、1 バイトでも編集すると射影が動き、記録が無い時点で red になる**(2 周目 `P0-7`)。

**カードの行番号はすべて現行 HEAD とずれている**([research.md](research.md) 1 節)。**計画書と設計書では節番号と関数名で書く。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**準備(ステップ 2〜6)は `scripts/frozen_history.py` に閉じ、検査器を 1 バイトも触らない。有効化はステップ 7 の 1 コミットにまとめる。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **draft PR を作る**(`acceptance_id` の PR 番号を先に確定させる)+ カードの現況化を worklog へ記録 + **送り出し 4 件を Notion へ起票し対応表を置く**(7D の残り / 7E / センチネル / 評価器選択) | **draft PR が存在し PR 番号が確定している**。worklog に 3 件が典拠つきで記録されている。**計画書と設計書に行番号参照が 0 件**。**送り出し 4 項目それぞれに受取タスク ID が対応付いた表が worklog にある** |
| 2 | **`scripts/frozen_history.py` を新設**(未結線)— 版付き record の parser。**prefix は `N` 件の生 JSON 値との deep-equal**、prefix 以後は明示 v2 のみ。**`history_authority` の宣言を読み、`true` がちょうど 1 資産であることを検査** | **検査器を 1 バイトも触らない**。合成 fixture で v1 / v2 が読める。**prefix の変更・削除・並べ替え・同位置置換が `ContractError`**。**prefix 以後の版キー欠落・明示 v1・未知の版も同様**。**`history_authority: true` が 0 件・2 件以上でも red** |
| 3 | 同(未結線)— **v2 の内容保存**。`contracts/tenant_boundary/history-snapshots/<sha256>`(追記専用)への `snapshot_ref`、**`aspect` の実差分からの機械導出と申告値との exact-set 照合**、`movement_fact` / `reason` / 新旧識別値の必須化、予約 marker の拒否・空でない承認者・実在する ISO 日付、`acceptance_id` の形 | 合成 fixture で **`snapshot_ref` が解決できない / 既存 snapshot を変更・削除した / `aspect` の申告が実差分と不一致 / 予約 marker / 空の承認者 / 不正な ISO 日付** がいずれも red。**`acceptance_id` の導出式が `{repository.full_name}#{pull_request.number}` に固定されている** |
| 4 | 同(未結線)— **評価の役割分担** + **PR コンテキストでの受理モードの強制**(`GITHUB_EVENT_NAME` を検査器が見る)。PR 受理モードは `base.ref == develop` / HEAD が 2 親 / 第一親 == `base.sha` / 第二親 == `head.sha` を要求 | 合成 fixture で **HEAD 定義の変更が必ず movement になる**。**対象集合を同じ差分で縮小する変異が red**。**PR コンテキストでイベント情報を欠くと red**(workflow の指定に従わない)。**PR 受理モードで 4 条件のいずれかを崩すと red** |
| 5 | 同(未結線)— **`required_triggers` を普遍下限の一般則へ** + **7D の最小限**(比較元側 ∪ HEAD 側の資産集合を走査)。5 軸と宣言 token の対応を exact schema で固定 | **6 token それぞれについて、対応する実状態を変異させると movement と記録要求が発生する**(字面の欠落・置換だけでは合格としない)。**比較元にあって HEAD に無い資産を検出すると red**。**比較元宣言が下限外の trigger を足した遷移は通る** |
| 6 | 同(未結線)— **fail-closed の網羅**([design.md](design.md) 7 節の 14 種) | 各失敗が**非 zero 終了かつ合格と区別できる**。**HEAD 側だけへの fallback が存在しない**ことを assert |
| 7 | **有効化 — 1 コミット。** 検査器から `frozen_history.py` を呼ぶ結線 + **7 資産の `external_files` へ検査器・helper・`ci.yml` を入れる**(7B / D4)+ **`history_authority` の宣言** + **authority 資産へ v2 の記録 1 件と識別値の更新** | **実リポジトリに対して** `uv run python scripts/check_tenant_boundary_bypass.py` が green。`uv run pytest tests/` green。**記録を抜くと red・識別値を据え置くと red・authority 以外へ追記すると red・同一受理で 2 件足すと red** |
| 8 | **変異テストの `[0]` 固定を解消** — 7 資産 parametrize で、検査器の変更が各資産で射影移動として検出される | **6 資産それぞれで改変前 green → 検査器変異で red**(現行は `base-allowlist.json` の 1 件しか見ていない) |
| 9 | **確認対象コミットの SHA を固定した人間の逐行確認を worklog へ記録**(履歴は追加しない)。**6 資産の初回自己凍結が bootstrap であり、信頼根が本確認であることを明記** | worklog に **確認対象コミットの SHA** と `対象= / 範囲= / 方法=` がある。**確認項目に「7 資産の `external_files` の exact-set」「モード結線」「D1〜D6 の実装対応」が列挙されている**。**確認後の差分は worklog 等の証跡ファイルに限る**(5 周目 `P1` — 最終 HEAD SHA を書くと自己参照になるため) |
| 10 | 全ゲート + PR 本文へ **[design.md](design.md) 8 節の 5 項目をそのまま転記** + **送り出し 4 件の対応表**を記載 | `uv run pytest tests/` / `uv run ruff check .` / `uv run ty check` green。**PR 本文の「主張しない範囲」が [design.md](design.md) 8 節と同じ 5 項目・同じ順序である** |

## 5. DoD(受け入れ基準)

- [ ] **7A**: カードの「前提・依存」欄が古い旨を worklog へ記録した(7A は PR #72 で完了済み)
- [ ] **D1**: **7 資産を単一検査として扱い、1 受理につき記録は 1 件である**。**`history_authority: true` がちょうど 1 資産**で、**記録は 7 資産すべての新旧識別値を持つ**
- [ ] **D2**: **v1 は比較元 prefix の中でだけ受理される。`N = 比較元の history 件数` として、HEAD の先頭 N 件が比較元の生 JSON 値と deep-equal である場合だけ成立する**
- [ ] **D2**: **prefix 以後の追記は明示的な `record_schema_version: 2` のみ。版キーの欠落も明示的な v1 も拒否する**
- [ ] **D2**: **既存 7 記録を 1 バイトも変えていない**(`git diff` で 0 行)
- [ ] **D3**: **v2 は `contracts/tenant_boundary/history-snapshots/<sha256>` への `snapshot_ref` を持ち、変更前後の内容が履歴から必ず解決できる**。**同ディレクトリは追記専用で、既存ファイルの変更・削除を受理しない**
- [ ] **D3**: **`aspect` は実差分から機械導出され、申告値との exact-set 一致を検査する**
- [ ] **D3**: **`movement_fact` / `reason` / 新旧識別値が v2 でも必須である**。**既知の予約 marker を拒否し、承認者は空でない文字列、承認日は実在する ISO 8601 日付**
- [ ] **D3**: **`acceptance_id` を `{repository.full_name}#{pull_request.number}` から機械導出し、イベント値と照合する**。**同一 PR の再実行・reopen は同値、新しい PR は別値**であることをテストで示した
- [ ] **D4**: **movement 判定と対象集合は比較元の宣言、`before` は比較元の定義と実装、`after` は HEAD の定義と実体から導出する**
- [ ] **D4**: **PR コンテキストでは検査器自身が PR 受理モードを強制し、イベント情報が無ければ不合格にする**(workflow の指定に従わない)。**`.github/workflows/ci.yml` が 7 資産の `external_files` に入っている**
- [ ] **D4**: **実 PR 受理モードが draft PR の実 CI で実走し green である**(合成 fixture だけで満たさない)
- [ ] **D5**: **条文の 5 軸と宣言 token の対応が exact schema で固定され、6 token それぞれについて対応する実状態を変異させると movement と記録要求が発生する**
- [ ] **D5**: **比較元側 ∪ HEAD 側の資産集合を走査し、比較元にあって HEAD に無い資産を検出すると不合格になる**
- [ ] **D6**: **ステップ 2〜6 のどのコミットでも検査器が 1 バイトも変わっていない**
- [ ] **D6**: **`scripts/frozen_history.py` が 7 資産すべての `external_files` に入っている**
- [ ] **7B**: **7 資産すべてが宣言した `movement_triggers` を射影で実装している**
- [ ] **fail-closed**: [design.md](design.md) 7 節の 14 種すべてが**非 zero 終了かつ合格と区別できる**。**HEAD 側だけへの fallback が無い**
- [ ] **bootstrap**: **6 資産の初回自己凍結が bootstrap であることを明記し、確認対象コミットの SHA を固定した逐行確認を行った**。**確認後の差分は worklog 等の証跡ファイルに限る**
- [ ] **記録の大きさの見直しトリガー**: **`json.dumps(history, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")` の byte 長**で、**単一資産の履歴 256 KiB / 単一 record 64 KiB**。**検査時間は CI ジョブの当該ステップの実測秒**で 10 秒。**いずれかを超えたら delta 形式への移行を検討する**(既存記録は不変の checkpoint として残す)
- [ ] 上記それぞれについて、**変異させると red になる**テストがある(**改変前 green を assert する**)
- [ ] **変異テストの `[0]` 固定を解消し、7 資産 parametrize にした**
- [ ] **PR 本文の「主張しない範囲」が [design.md](design.md) 8 節と同じ 5 項目・同じ順序である**
- [ ] **送り出し 4 件**(7D の残り / 7E / センチネル / 評価器選択)を Notion へ起票し、**4 項目と受取タスク ID の対応表**を worklog と PR 本文へ置いた
- [ ] pytest / ruff / ty green

## 6. テスト計画

**NFR-019 のテスト種別のうち、本タスクが足すのは「単体」と「故障系」。** 越境・一致性・E2E は射程外(検査器自体の検査であり製品の経路を通らない)。

| 種別 | 足すもの | ステップ |
| --- | --- | --- |
| **単体** | 版付き parser — v1 / v2 の受理、prefix の deep-equal 判定、`history_authority` の一意性 | 2 |
| **単体** | v2 の内容保存 — `snapshot_ref` の解決、`aspect` の機械導出、必須フィールド、`acceptance_id` | 3 |
| **単体** | `_validate_repository_histories` / `_git_json_asset` を**直接呼ぶテスト**(現行 0 本 — [research.md](research.md) 6-3) | 4 |
| **故障系(変異)** | prefix の変更・削除・並べ替え・同位置置換 / prefix 以後に v1 を足す | 2 |
| **故障系(変異)** | **`snapshot_ref` の解決不能 / 既存 snapshot の変更・削除 / `aspect` の申告と実差分の不一致** | 3 |
| **故障系(変異)** | **PR コンテキストでイベント情報を欠く** / PR 受理モードの 4 条件を 1 つずつ崩す / HEAD 定義の変更が movement にならない / 対象集合の縮小 | 4 |
| **故障系(変異)** | **6 token それぞれに対応する実状態の変異**(字面ではなく) / **比較元にあって HEAD に無い資産** | 5 |
| **故障系(変異)** | [design.md](design.md) 7 節の 14 種(**HEAD 側だけへの fallback が無いことを含む**) | 6 |
| **故障系(変異)** | **記録を抜く / 識別値を据え置く / authority 以外へ追記する / 同一受理で 2 件足す** | 7 |
| **故障系(変異)** | **7 資産 parametrize** — 検査器の変更が各資産で射影移動として検出される | 8 |
