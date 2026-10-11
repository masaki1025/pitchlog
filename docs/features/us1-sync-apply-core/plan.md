---
feature: us1-sync-apply-core
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-08・山田正輝 / 第 1 改訂 2026-10-11・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e6878108a4c1e66253a25065
branch: feature/us1-sync-apply-core
created: 2026-10-08
計画レビュー周回: 6        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 2          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-S1 同期適用核(TSK-391)

## 1. 背景・目的

調査: [research.md](research.md)(スパイクの結果を含む)/ 詳細設計: [design.md](design.md)

- Notion: [TSK-391 U-S1 同期適用核](https://app.notion.com/p/3da93b75e6878108a4c1e66253a25065)。出所は TSK-363 の単位分割(`docs/features/product-impl-unit-split/plan.md:205`)。帯 1(核)
- 主所有は [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012)(通信断耐性・同期)。関係する要件は NFR-007・NFR-010・NFR-015・NFR-019(d) と、[FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013) の記録権拒否
- サーバー側で同期を適用する製品コードは、まだ 1 行もない。表・制約・トリガ・RLS はあるが、それを使って「重複到達しても二重適用しない」「欠落以降を適用しない」「べき等キー・イベント・prefix・状態遷移を単一トランザクションで確定する」(REQ:302-303)を実行する層がない(research C-1)
- **目的**: 同期プロトコル正本(`docs/design/sync-protocol.md` v0.4)の 6〜9 章のサーバー側を、経路 P1〜P5 の適用核として実装する。あわせて NFR-019(d) の故障系テスト資産の契約を作り直し、適用核をその資産で実行検証する

裁定(2026-10-08・人間。research.md 末尾):

| ID | 内容 |
| --- | --- |
| R-1 | U-S1 が TSK-330(8 章の適用実装と runner)を吸収する |
| R-2 | 記録権の判定(V12・D4・RG1・復旧世代)と状態遷移(T4)・内容検証は、注入境界で受ける。FR-012 は U-S1 では部分充足 |
| R-3 | HTTP 入口は開かない。入口は TSK-331 で wire 形式が決まった後に、別の小さな PR で開く |
| R-5 | UM01 の #95 の上に積む(起点 `3e19b295`)。実装の開始は #95 のマージ後 |
| R-9 | **U-S1 が TSK-332(NFR-019(d) の資産契約の再設計とシナリオ資産)も吸収する**。スパイク(`feature/us1-sync-spike`)で資産の実際の形が見えたため |
| R-10 | **正本 `docs/design/sync-protocol.md` 10-3 の比較単位を改訂する**(当初 v0.6 → **第 1 改訂で v0.7 に変更** — v0.6 は新ステップ 1 の「1 件」の追随に使う)。資産の比較単位が `scenarioId × caseId × 注入対象 × 観測点 × expected の全フィールド` になり、現行の「`scenarioId × 観測点 × expected の全フィールド`」(SP:1716)と食い違うため(計画レビュー 2 周目)。U-S1 の PR に確定ゲート(/finalize-doc)を含める |
| R-12 | **ポートの別スレッドへの書き込みの預け入れは、アプリの層で最大限に防ぎ、残りは記録する**(計画レビュー 3 周目 P1。人間の判断 2026-10-08)。DB のトリガで完全に閉じる案は採らない。投影の表の持ち主である U-X1 が、本物の投影ポートを作るときにトリガを入れる(申し送り)。**I6 の端末側の検証は U-S1 で閉じる**(Vitest 側の runner) |
| R-11 | **TSK-330 から引き継いだ繰り延べ 12 ID のうち、復元ライフサイクルの 10 件は U-R1(TSK-392)へ送る**。残り 2 件(`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence`)は U-S1 で作る。R-1 の「吸収」から 10 件を除く |


> ## 【第 1 改訂 2026-10-11・改訂承認: 山田正輝 2026-10-11(7 節 A-1〜A-3 を含む)】develop の取り込み(574 コミット)後の測り直しと、#114(TSK-447)との接合
>
> **引き継ぎ**: TSK-391 を UM01(447)タブが引き継いだ(2026-10-11 — 盤面で所有者が空であることを master が確認)。開始条件の #95・#81 は着地済み。develop `8060b8d0`(#114 を含む)を取り込んだ(`607ed4cc`・競合なし)。測り直しの結果は worklog の 2026-10-11 の段。
>
> **前提が維持されたもの**: 開始条件 / R-3(TSK-331 はマージ済みで正本を改訂しない。入口 PR は TSK-506)/ R-1・R-9・R-11 / sync-protocol の v0.6 の予約(現行 v0.5・v0.6 は空き)。TSK-455(#107)は (α) ベクタの runner で、(d) の runner(ステップ 18〜19 → 新 20)とファイルは重ならない。
>
> **人間の裁定(2026-10-11・山田正輝 — AskUserQuestion)**:
>
> | ID | 内容 |
> | --- | --- |
> | R-13 | **I5 の配信と再試行は U-S1 が持つ**(承認済みの Q-10 のとおり)。配信先は `InvalidationSinkPort`(本物は未登録)。data-model `B06` の「配信の所有」の行(#114 で新設・「`B04` の補足」と書かれ I5 にも掛かるように読める)を、**同期を通らないトリガーに限る**と明確にする |
> | R-14 | **同期経路の無効化意図は範囲ごとに 1 行書く**。意図 ID は「対象イベントの識別 + 範囲」(P3 = `V10` + 対象の確定版 + 範囲)。DDL は変えない。**data-model `B03` を改訂する**(v0.8・確定ゲート)。同期経路のトリガー 1・3・4(記録側)は `V10` か `V11` を欠いて現行 `B03` に当てはまらない(#114 の申し送り — `docs/features/roster-status-invalidation/design.md:59-60`)ので、**D1 付き経路の意図 ID の導出も同じ改訂で定める**(作成者の案: イベントの D5 + 範囲 — 保存済み結果の再掲で同じ ID になる。8 節で承認を受ける) |
> | R-15 | **契約の語彙を DB に合わせる**: `cache-invalidation-contract.json` の配信状態を `pending`/`delivered`、未配信の検索列を `delivery_status` へ改める(凍結資産・revision を上げ受理記録)。範囲名は名前を変えず、#114 の写像(`repositories/invalidation_intents.py` の私有の表)を公開して共有する(写像を 2 つ持たない) |
>
> **計画の変更**(ステップ表は本改訂で番号を振り直した — まだステップのコミットは無い):
>
> 1. **新ステップ 1 = 正本の改訂案**: data-model(`B03` の範囲ごとの行と同期経路の意図 ID・`B06` の配信の行の限定・一意性の索引表)と **sync-protocol(8-1 の `T7`・10-2・10-3 の「1 件だけ永続化」を範囲ごとの 1 件へ — 計画レビュー 1 周目 P0)** を**単一の確定ゲート**で → **PO 承認の後に新ステップ 2 以降へ進む**。R-10 の 10-3 の資産構造の改訂は従来どおり新ステップ 16 の前に置き、版を v0.7 へ繰り下げる
> 2. **core-areas の窓口**: 現在の `AREA_PATH_ADDITIONS = {"tenant-isolation": ("frontend/src/stores/authStore*",)}`(#116 — 基線へ取り込み済み)を**消して** U-S1 の宣言だけを書く(累積すると「追加層が一部だけ基線へ取り込まれている」で落ちる)。`tests/test_core_guard.py` の期待値も置き換える。`backend/src/pitchlog/sync/*` はどの領域の glob にも当たらず、`repositories/sync_apply.py`・`test_sync_apply_*_boundary.py` は tenant-isolation だけに当たる — 宣言と登録(sync-protocol × recording-rights の重複帰属)は引き続き要る
> 3. **基底の拡張**(旧 4 → 新 5)から「registry を複数モジュールから集める形」を外す(#114 で導入済み — `backend/src/pitchlog/repositories/operation_registry.py:5-12`)。合格条件の「#95 の roster の operation が変わらず green」に #114 の意図の operation を加える
> 4. **新ステップ 9 = 同期経路の無効化意図の記録**(`sync/invalidation.py` の記録部): 改訂後 `B03` の意図 ID・範囲ごとの 1 行・契約の語彙の改訂(R-15)・範囲名の写像の共有。P1(新 10)が D1 付き経路の発火(D3 の前進 — SP 8-5)で使い、P3(新 13)が T7 で使う。**承認済み計画は D1 付き経路の意図の記録を持っていなかった**(research・計画とも 0 件 — 本改訂で足す)
> 5. **同期表の operation 登録**(旧 6 → 新 7): `invalidation_intents` の insert は #114 が `InvalidationIntentInsertToken`(トリガー 14 専用)で登録済み。同期経路の行の形が違うので別の token にし、同じ capability で共存させる(登録検査が許すかはステップ内で確かめる)
> 6. **新ステップ 22 = 受理記録の最終導出**: ステップ 4・5・7・9 が `contracts/tenant_boundary/` を動かすのに、1 件へまとめるステップが無かった。#95(内訳 10)・#114(ステップ 5)と同じ形で最後に置く。センサス基準が動けば同じコミットで更新する
> 7. **型**(新 6): TSK-331 の決定(V12・V5〜V11 は wire の層で検査せず値のまま処理段階へ渡す — `docs/features/sync-wire-schema/design.md:101`)に合わせ、`sync/model.py` はこれらを型の層で弾かず処理段階で判定できる形にする
> 8. **クライアント側の runner**(旧 18 → 新 20): `frontend/src/lib/sync/prohibitions.spec.ts:577-580` の `EXPECTED_TESTING_SOURCE_FILE_NAMES`(TSK-455 で 2 件)を、`src/testing/` に足す .ts に合わせる
> 9. **各ステップの合格条件の既定**(#114 の取りこぼしの教訓 — 台帳の既存候補へ実測済み): 関係ファイルのテストに加え、**backend の DB 不要の全件**と、凍結資産を動かすステップでは**迂回検査・凍結履歴・凍結 archive・センサスの一式**を回す。正本を改訂するステップでは、その正本の digest を持つ資産(`contracts/db/schema-manifest.json`・`contracts/authz/shared-preconditions.json`・ORM 受入シート)を同じステップで追随させる
> 10. 1 節の「正本 v0.4」は v0.5 に読み替える(#81 で v0.5 approved)
>
> **スパイク**(`feature/us1-sync-spike`): 自身の承認済み計画が「捨てる前提。PR にせず develop へマージしない。答えを本計画の research.md へ転記した後に削除する」と定めており、research.md「スパイクの結果」(S-1〜S-5)に転記済み。ブランチは origin に無いので、削除は人間の確認の後に行う

## 2. スコープ

### やること

1. 適用核のサービス層 `backend/src/pitchlog/sync/`(構成は [design.md 1 節](design.md#1-置き場とモジュール構成))
   - 段階③〜⑧の順序(SP 6-2)。③認可は U-T1 の `TenantContext` 束縛を使う
   - ④ D5 の内部分類 DI1〜DI5・I1〜I4 と、イベントのトランザクション内での再照合([design.md 3 節](design.md#3-トランザクションの単位と-d5-の再照合スパイク-s-1s-5))
   - P1・P2: ⑥ D3+1 からの走査、T1+T6・T2・T3・T4、墓標(R3)・改訂(R4)、B2・B3b、一時 ID 写像 C1〜C4
   - P2 の T5: O1・O2・O4
   - P5 / T9(B3a・B3b)、P4 / T8(B4・退避)
   - P3: ③-b 復旧世代、B8〜B14、T7・I5(無効化意図の保存と配信・冪等な再試行)、I6 の `accepted_at`
   - ③-a RG1 と ⑧ のコミット直前再検証(同期経路の範囲)
   - 公開入口: D1 昇順の外部結果の確定、DI5 の混在バッチ、ACK の合成、名前付きのクラッシュ注入点
2. 注入境界 4 種と、ポートの拘束([design.md 2 節](design.md#2-注入境界とポートの拘束裁定-r-2スパイク-s-2))
3. リポジトリ基底の拡張: 複合主キーの UPDATE・行ロック・JSONB の結果の実体化・registry を複数モジュールから集める形・適用中に新しいスコープを開けない検査([design.md 4 節](design.md#4-リポジトリ基底の拡張tenant-isolation-のコアスパイク-s-3))
4. 同期表 9 表の operation 登録(`backend/src/pitchlog/repositories/sync_apply.py`)と registry への接続
5. TB002(条件 2)の所有パス。core-areas.json の sync-protocol の paths と機械で結ぶ([design.md 5 節](design.md#5-tb002条件-2との衝突の解き方))
6. **NFR-019(d) の資産契約の再設計**(TSK-332 の吸収。[design.md 7 節](design.md#7-nfr-019d-の資産契約tsk-332-の吸収スパイク-s-4)): 構造の改訂、契約検査と結果検査の分離、既存 4 資産の版移行と frontend の消費側の追随、新規資産 12 件(TSK-332 の 10 件 + TSK-330 から引き継いだ 2 件)
7. **(d) runner の両側**: サーバー側(pytest — 資産を読み、適用核に注入して DB を観測する)と、クライアント側(Vitest — 既存の `frontend/src/testing/failureScenarioAdapter.ts` を拡張し、I6 の「サーバー確定の後・端末永続化の前」の注入を含めて端末の状態を観測する)
8. core-areas.json への登録(宣言と登録の 2 段)
9. TSK-330・TSK-332 を受け取り先として書いている箇所を TSK-391 へ追随させる(`frontend/src/lib/sync/canonOracle.ts:493-515`・`canonOracle.spec.ts:685-688`・`idempotencyCollision.ts:3`)

### やらないこと

- **HTTP 入口・wire 形式・API スキーマ**(R-3。TSK-331)。route_id の付与と 12-4 ゲートも入口 PR が持つ。**B5・B11(認証失効)は入口がないと発生しないので、入口 PR へ送る**
- **記録権の判定の本物**(V12・D4・復旧世代・RG1 の状態)。U-R1(TSK-392)が `RecordingRightsPort` に差し込む
- **状態計算(投影・再計算・内容検証)の本物**。U-X1(凍結中)・U-G2 がポートに差し込む
- **復元ライフサイクルの故障シナリオ 10 件**(R-11。`restore-fence-escrow-new-generation`・`restore-crash-before-new-generation`・`restore-uncollected-device`・`restore-commit-race`・`restore-cleanup-held`・`restore-expired-not-collected`・`restore-d4-issued-set`・`restore-d4-consecutive-rollbacks`・`restore-all-write-paths-blocked`・`restore-release-new-generation-boundary` — `docs/features/sync-server-apply/design.md:394-403`)と、**RG1 による同期以外の変更経路の停止**。**U-R1(TSK-392)へ送る**。記録権・復元の状態(D4 の発行・端末の回収)が U-S1 の外にあるため
- **クライアント側の実装**(キュー・採番の不可分性・単一書き手・通知)。強制点はクライアントで、実装済み(SP:1401、DM:803-812)。ただし (d) 資産の版移行に伴う frontend の消費側の追随はやる
- **ポートが別スレッドへ書き込みを預け、待たずに戻る経路の完全な遮断**(R-12)。U-S1 は静的規則と実行時の拒否で最大限に防ぎ、残りは逐行確認に任せる。DB のトリガによる遮断は、投影の表の持ち主である U-X1 へ申し送る
- I5 の配信先の本物(キャッシュ層)。通知の文面と契約(TSK-441)。U-1・U-2・RR-1 の 3 経路(TSK-267)
- `backend/src/pitchlog/db/` へのファイル追加と、表・列・マイグレーションの追加(`docs/features/product-impl-unit-split/plan.md:467`)。依存パッケージの追加

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/sync-protocol.md` | **第 1 改訂で 2 回の改訂に分けた**: ① **v0.6(新ステップ 1・data-model v0.8 と単一の確定ゲート)** — 8-1 の `T7`・10-2 の P3・10-3 の `T7` の必須観測の「1 件」を範囲ごとの 1 件へ追随(R-14)② **v0.7(新ステップ 16 の前)** — **10-3 の (d) 資産契約を改訂する(R-10)**: 比較単位に `caseId` と注入対象を加える、単一の `faultInjection`・`expected` を `cases` 構造にする、`tElementCommitment` の T の内部単位と `no-write` / `no-change`。意味規則(6〜9 章)は変えない。v0.2 は TSK-267、v0.5 は #81(TSK-236・2026-09-28 approved)の先約。当初は v0.6 を使う裁定(2026-10-09 山田正輝)だったが、第 1 改訂で ① を v0.6・② を v0.7 とした(版を予約しているのは U-S1 だけ — TSK-331 は改訂しない)。確定ゲートは #81 のマージ後に通す。変更履歴に追記し、`docs/README.md` の索引を現行化する | **finalize-doc**(敵対レビュー + 人間承認)。Claude が行い、Codex のステップにしない。**新ステップ 16 の前に確定させる**(第 1 改訂で番号を振り直した) |
| `contracts/tenant_boundary/base-allowlist.json`(凍結資産) | 条件 2 に同期核の所有パスを足す。凍結基準の履歴追記を伴う | PR レビュー + 敵対レビュー + 人間承認(コア) |
| `contracts/tenant_boundary/repository-contract.json`(凍結資産) | 複合主キー UPDATE・行ロック・JSONB 結果・同期の capability と token を足す | 同上 |
| `.claude/core-areas.json` | `backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py`・`backend/tests/test_sync_apply_*.py` を sync-protocol と recording-rights の両方に登録する | 敵対レビュー + 人間承認(6.3 規則⑤) |
| `docs/design/data-model.md` | **第 1 改訂で追加(R-13・R-14)**: 11-2 節 `B03` を改訂し、同期経路の無効化意図を範囲ごとに 1 行とし、意図 ID の導出を「対象イベントの識別 + 範囲」へ(P3 = `V10` + 確定版 + 範囲、D1 付き経路 = 8 節の承認による)。`B06` の「配信の所有」を同期を通らないトリガーに限る。版 v0.7 → v0.8・変更履歴 | **finalize-doc**(新ステップ 1 の直後) |
| `contracts/tenant_boundary/cache-invalidation-contract.json`(凍結資産) | **第 1 改訂で追加(R-15)**: 配信状態を `pending`/`delivered`、未配信の検索列を `delivery_status` へ。`durable_intent` の同期経路の規則を改訂後 `B03` に追随 | PR レビュー + 敵対レビュー + 人間承認(コア) |
| `contracts/db/schema-manifest.json`・`contracts/authz/shared-preconditions.json`・ORM 受入シート(`docs/features/orm-schema-migration/acceptance-sheets/`) | **第 1 改訂で追加**: data-model.md の digest と生成物の追随(#114 の教訓) | PR レビュー |
| `docs/README.md` | sync-protocol.md の版の表示を v0.6(新ステップ 1)・v0.7(新ステップ 16 の前)にする。**data-model 行を v0.8 にする(第 1 改訂)** | finalize-doc と同じ |
| 要件書・ADR | **反映なし** | — |

## 4. 実装方針

**重さ分類 = コア領域**。根拠: U-S1 は sync-protocol × recording-rights の重複帰属(`docs/features/product-impl-unit-split/design.md:101`、ハーネス設計書 6.3-③)。新ステップ 4・5・7・9 は tenant-isolation の凍結資産と repositories の基底に触れる(第 1 改訂)。**触れるコア領域は 3 つ**(sync-protocol・recording-rights・tenant-isolation)。テストは平場に置き、`backend/tests/db/`(全 5 領域に一致)を使わない。全ステップで敵対レビューと人間の逐行確認を受ける。

設計の詳細は [design.md](design.md)。スパイクで確かめた前提(research.md「スパイクの結果」):

- 1 イベント = 1 トランザクションで、名前付き注入点を置ける(S-1)
- ポートにハンドルを渡すだけでは、独自スコープの書き込みを防げない(S-2)→ 書き手を制限し、適用中は新しいスコープを開けなくする
- #95 の形では D3 の UPDATE・スロットの版 UPDATE・JSONB の結果が表せない(S-3)→ 新ステップ 5 で拡張する
- 両方が「未使用」と分類した後に**先着が確定してから**後着を再開した場合、後着はトランザクション内の再照合で B3b になる(S-5。**再照合から INSERT までの窓の競合は試していない** — 新ステップ 8 で試す)
- T1 と T6 の台帳の確定結果は同じ書き込みで確定する(台帳の `result` は NOT NULL かつ不変)。T6 の一時 ID 写像表は別の書き込み

**開始条件**:
- #95(UM01)のマージ(UPDATE の CompileError の是正 = #95 の「ステップ 5 是正」を含む)。マージ後に develop を取り込んでから始める
- 旧ステップ 1・2(新 2・3 — core-areas)は、**#95 → #81 → U-S1 の順**で窓口を使う(469 master の実測 2026-10-08: #81 は sync-protocol と recording-rights を宣言済みで、U-S1 と同じ領域で当たる)。#81 のマージ後に develop を取り込んでから始める
- **第 1 改訂**: #95・#81 は着地済み(条件は満たされた)。窓口は #116 の `authStore*` の 1 件を消して置き換える。**新ステップ 1(data-model の改訂)の確定ゲートの PO 承認の後に新ステップ 2 以降へ進む**

**正本の改訂の順序**(第 1 改訂で番号を振り直した): **新ステップ 1 の直後に data-model v0.8 と sync-protocol v0.6(R-14)を単一の確定ゲートで確定させる**。新ステップ 15 の後、新ステップ 16 の前に、sync-protocol.md 10-3 の資産構造の改訂(v0.7・R-10)を /finalize-doc で確定させる。資産契約(新ステップ 16〜19)は改訂後の正本に従う。

**計画レビューで確認する論点**(design.md 8 節): Q-2(NFR-018 — 1 周目で「当たらない」)/ Q-3(O1 の直列化)/ Q-4(内容同一性)/ Q-5(改訂版の区別・TSK-373)/ Q-6(D3 の列)/ Q-7(RG1 の範囲)/ Q-10(I5 の配信先)。Q-8 は R-10、Q-9 は R-11 で裁定済み

**到達可能な境界結果**(計画レビュー 1 周目 P1-8): P1・P2・P4 = B1・B2・B3(B3a・B3b・O4)・B4・B6・B7。P3 = 変更受理・B8・B9・B10・B12・B13・B14。**B5・B11 は入口 PR へ送る**。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **正本の改訂案 — data-model v0.8 と sync-protocol v0.6 を単一の確定ゲートで**(第 1 改訂・R-13・R-14): **data-model**: 11-2 節 `B03` を改訂し、同期経路の無効化意図を範囲ごとに 1 行とし、意図 ID を「対象イベントの識別 + 範囲」(P3 = `V10` + 確定版 + 範囲 / D1 付き経路 = 8 節の承認による)へ。`B06` の「配信の所有」を同期を通らないトリガーに限る。一意性の索引表の 11-2 行(`:414` 付近 — 旧導出「`V10` + 対象の確定版」)を追随させる。変更履歴 v0.8(射程宣言つき)。**sync-protocol**: 8-1 の `T7`(「安定した意図 ID で 1 件だけ永続化」— `:1229`)・10-2 の P3 の行(`:1669`)・10-3 の P3 の期待結果の「安定した意図 ID」(`:1715` 付近 — 単数)と `T7` の必須観測(`:1724`)の「1 件」を、改訂後 `B03` の「範囲ごとに 1 件」へ追随させ、**範囲ごとの全意図 ID・永続状態・再掲後の件数を観測対象と明記する**(意味規則は「1 回の論理無効化を重複なく永続化し配信完了まで冪等に再試行する」のまま)。変更履歴 v0.6(射程宣言つき)。`docs/README.md` の両行。**data-model.md の digest を持つ資産(`contracts/db/schema-manifest.json`・`contracts/authz/shared-preconditions.json`)と ORM 受入シートを同じステップで追随させる**。このあと /finalize-doc(反映周のコミットはステップ記法を付けず `反映<r>周目`) | `check_docs_status`・`check_design_propagation`・`check_doc_coverage`・`check_plan_docs_sync`・`check_shared_preconditions` が ok / backend の DB 不要の全件(`test_schema_manifest.py`・`test_authz_cache_invalidation.py` を含む)と `tests/test_orm_acceptance_sheets.py` が green / **確定ゲート(2 文書の一括検証 — 7.3-1)の PO 承認** |
| 2 | **core-areas の宣言**: `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` を、**現在の `tenant-isolation` の `authStore*` の 1 件を消して(第 1 改訂)**sync-protocol と recording-rights への追加分(`backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py`・`backend/tests/test_sync_apply_*.py`)だけに置き換える。`tests/test_core_guard.py` の期待値(`EXPECTED_AREA_PATH_ADDITIONS` ほか)も置き換える | `tests/test_core_guard.py` が green。宣言と JSON を同じコミットで変えていない。**他の単位の宣言(#95・#81 ほか、基線の core-areas.json に取り込み済みのもの)を累積していない** |
| 3 | **core-areas の登録**: `.claude/core-areas.json` に登録し、`test_core_guard.py` の期待集合を追随させる | core-guard の CI 相当が green。新しいパスが sync-protocol と recording-rights の両方に一致する(重複帰属の明示) |
| 4 | **TB002 の所有パス**: 条件 2 に同期核の所有パスを足す。所有パスは、検査時点で core-areas.json の sync-protocol の paths に一致するパスに限って発効する。凍結基準の履歴を追記する | 所有パス内の同期語彙が TB002 にならない(正例)。所有パス外(例: `repositories/roster.py`)は TB002 になる(負例)。core-areas.json から外したパスは免除されない(負例)。条件 1・3・4・5 は所有パス内でも効く(負例 3 件)。迂回検査のテストが green |
| 5 | **リポジトリ基底の拡張**: 複合主キーの UPDATE 条件、行ロックの宣言、JSONB の結果の不変表現への実体化、適用中に同じスレッドで新しい `tenant_transaction_scope` を開けない検査(多層防御の 2 層目。1 層目は新ステップ 6 の `TenantContext` を渡さない拘束)。repository-contract を改訂する | 複合主キーの全列を束縛しない UPDATE が登録時に拒否される(負例)。宣言していない文はロックを取らない。JSONB の結果が不変な表現で返る。適用中の印があると、同じスレッドで新しいスコープを開けない(負例)。#95 の roster と #114 の意図の operation が変わらず green。`backend/tests/conftest.py` の差分 0 行 |
| 6 | **型とポートの拘束**: `sync/model.py`(要求・A5・境界結果・ACK 結果。**V12・V5〜V11 は型の層で弾かず処理段階で判定できる形にする** — TSK-331 の決定 `docs/features/sync-wire-schema/design.md:101`・第 1 改訂)と `sync/ports.py`(ポート 4 種・`PortWriter`・**ポート実装モジュールの登録表**)。ポートには `TenantContext` もハンドルも渡さない。適用核は、登録表にないモジュールのポートを実行時に拒否する。登録表のモジュールは、pitchlog パッケージ内の**推移的な import** に `pitchlog.repositories.transaction`・`pitchlog.repositories.context`・`pitchlog.db.engine`・`sqlalchemy`・`psycopg`・`threading`・`concurrent.futures`・`asyncio`・`multiprocessing` を含めてはならない(静的検査。DB 接続の生成と直接 SQL を含めて禁じる)。U-S1 では登録表は空(本物は U-R1・U-X1 が登録する)。テスト用の合成実装は `backend/tests/` に置く | 型の単体テストが green。製品コードにポートの既定実装がない。`PortWriter` は token の実行だけを受け付け、SQL を受け付けない。ポートの署名に `TenantContext`・ハンドル・session が現れない。登録表にないポートを渡すと、ポートが呼ばれる前に適用が失敗する(負例)。禁止モジュールを推移的に import するモジュールを登録すると静的検査が落ちる(負例: `pitchlog.db.engine` から別接続を作るポート) |
| 7 | **同期表の operation 登録**: `repositories/sync_apply.py` に 9 表の read/insert/update を登録し、registry に接続する。`invalidation_intents` の insert は #114 の `InvalidationIntentInsertToken`(トリガー 14 専用)と別の token にし、同じ capability で共存させる(第 1 改訂) | 全 operation が構築時の検査を通り、registry から引ける。2 テナントの越境テスト(他テナントの行を読めない・書けない)が green |
| 8 | **D5 の分類と再照合**: `sync/idempotency.py`(DI1〜DI5・I1〜I4、内容同一性 Q-4、イベントのトランザクション内の再照合)。台帳の INSERT を SAVEPOINT で囲み、一意制約違反なら SAVEPOINT まで戻して D5 を照合し直し、再掲か B3b / B13 へ切り替える | 3 分類(保存済み結果候補・B3b / B13 候補・未使用)を DB テストで確認。順序を固定した並行試験 2 種: ① 両方が未使用と分類した後に先着を確定 → 後着は再照合で再掲か B3b ② **後着が再照合を終えて INSERT の直前で止まっている間に先着を確定** → 後着は一意制約違反から SAVEPOINT で戻り、再掲か B3b になる(トランザクション全体は失敗しない)。他テナントの同じ D5 は未使用として扱われ、存在が判別できない |
| 9 | **同期経路の無効化意図の記録**(第 1 改訂・R-14・R-15): `sync/invalidation.py` の記録部。改訂後 `B03` の意図 ID で範囲ごとに 1 行を、イベントと同じトランザクションに書く。`cache-invalidation-contract.json` の配信状態を `pending`/`delivered`・検索列を `delivery_status` へ改め、`durable_intent` の同期経路の規則を改訂後 `B03` に追随させる。範囲名の写像は #114 の表を公開して共有する(写像を 2 つ持たない)。受理記録をこの時点の比較元に対して 1 件のまま導出し直し、比較 corpus を再封印する | 記録部を直接呼ぶ DB テストで、範囲ごとの行の数と意図 ID の形(P3 の入力と D1 付き経路の入力の両方)/ 同じ入力で 2 回呼ぶと同じ意図 ID になり重複しない(実経路からの発火と保存済み結果の再掲は新 10・13 の合格条件)/ 写像が契約の 5 範囲と DDL の CHECK の 5 値を全単射で覆う(#114 のテストを共有の写像に向け直す)/ 契約と DDL の配信状態の語彙が一致する検査 / 迂回検査・凍結履歴・凍結 archive・センサスの一式 green |
| 10 | **P1 の 1 イベントの適用**: `sync/prefix_path.py`。T1 と T6 の台帳の確定結果(同じ INSERT)・T2・T3(D3 を `FOR UPDATE` で読み直す)・T4(ポート経由)・T6 の一時 ID 写像表の保存(台帳とは別の書き込み)、墓標(R3)・改訂(R4)、C1〜C4。**D1 付き経路の発火**(D3 が前進したとき — SP 8-5)で新 9 の記録部を呼ぶ(第 1 改訂) | D3 が前進したときだけ意図が範囲ごとに書かれ、据え置き(B1 の全件重複など)では書かれない。保存済み結果の再掲で意図が重複しない(第 1 改訂)。1 イベント単位の DB テスト: 墓標で D3 前進、改訂で D3 が後退しない、拒否位置の改訂でその位置まで前進。その場登録で写像が保存され、再送で同じ写像が返る。**テスト中だけ合成ポートを登録表に足して**(製品の登録表は空のまま)、同じスレッドで独自スコープを開こうとするポートを差し込むと、**ポートが呼ばれた後に**スコープの入口で拒否され(spy で確かめる)、適用が失敗し何も残らない。ACK 全体の検査は新ステップ 15 |
| 11 | **P2 の T5**: `sync/ordering.py`。O1 の直列化(Q-3)・O2 の局所再採番・O4 の同値停止 | 同じ試合への並行 2 トランザクションで D2 が重複しない。隙間枯渇時に局所再採番と新イベントの保存が同じトランザクションで確定する。O4 で B3 と A5「拒否」になり、投影を止める |
| 12 | **P5 / T9 と P4 / T8**: `sync/rejection.py` | B3a の再送で同じ拒否結果と理由。B3b の前後で台帳と原本表が変わらず、T9 を開始しない。B4 で退避原本と A5「退避」を保存してから結果を返す。保存済みの退避結果は、現在の記録権によらず再掲される |
| 13 | **P3 と I5**: `sync/change_path.py`(③-b・B8〜B14・T7・I6)と `sync/invalidation.py` の配信部(未配信の意図を `InvalidationSinkPort` へ渡し、完了まで冪等に再試行し、完了を `delivered` で記録する — R-13。T7 の意図の記録は新 9 の記録部を使う) | **P3 の初回受理で、対象範囲ごとの意図の行と意図 ID が変更イベントと同じトランザクションで保存される**(記録部を実経路から呼ぶ — 第 1 改訂・計画レビュー 2 回目)。B8〜B10・B12〜B14 の各分岐が DB テストで再現する。保存済み結果の再掲で無効化意図を重複作成しない(範囲ごとの行のどれも — 第 1 改訂)。配信先が消費した後・完了記録の前にクラッシュしても、再試行で二重の完了にならない。終了後の P3 では V12 を照合しない |
| 14 | **RG1 とコミット直前再検証**: `sync/gate.py`(同期経路の範囲) | 復元調整中なら P1・P2・P4 は B7、P3 は B10 で、D5 を消費しない。③-a の通過後に復元調整へ移ったら、⑧ で全ロールバックする |
| 15 | **公開入口と注入点**: `sync/apply.py`(段階の順序、D1 昇順の外部結果、DI5、ACK の合成)と `sync/crash_points.py`(トランザクションの前後、各 T 要素の間、**T6 の写像表の保存の前後**、T8・T9 の内部の保存境界) | SP 6-3 の例(D3 = 4・D1 = 5 欠落・D1 = 6 未使用・D1 = 7 既存異内容 → B2、D1 6 と 7 は未処理)を再現する。ACK 消失後の再送・引き継ぎ後の再送で、保存済み結果が再掲され、二重適用も選手 ID の重複生成も起きない。段階の順序を入れ替えると落ちるテストがある。他テナントの試合は B6 で、D5・記録権・連番の状態が応答に現れない。P1〜P5 の全注入点で、全部確定か全部未確定 |
| 16 | **(d) 資産契約の改訂**(改訂後の正本 10-3 に従う): `cases` 構造・共通の期待フィールドと **P3 に加わる期待フィールド**・`tElementCommitment`(T の内部単位・`no-write` / `no-change`)・判別共用体・到達性。注入点の組は `R-TXN-ROUTE` から導出する。**トランザクション外の 3 注入点**の被覆と繰り延べを exact-set で照合する。契約検査と結果検査を分ける(Python 側) | 契約検査の正例・負例(部分確定・孤立した観測点・重複注入・判別共用体の食い違い・到達性の不一致・**P3 固有フィールドの欠落**)が期待どおり。母集合と、トランザクション外の 3 注入点の被覆・繰り延べの exact-set 照合が green |
| 17 | **既存 4 資産の版移行と frontend の追随**: 既存 4 資産を最終構造へ一度だけ移行し、`frontend/src/testing/failureScenarioAdapter.ts`・`frontend/src/lib/sync/failureScenarioContract.ts` と、**spec に固定された版の期待集合**(`frontend/src/lib/sync/failureScenarioContract.spec.ts:72` ほか)を追随させる | 移行後の 4 資産が契約検査を通る。frontend の該当 spec(`pnpm test`)が green |
| 18 | **新規資産 12 件**: TSK-332 の 10 件(墓標・改訂、P1〜P4、`p5-b3a`、`p5-b3b`、`d1-mixed-batch`、`b3b-after-gap`)と、TSK-330 から引き継いだ 2 件(`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence`) | 12 件が契約検査を通る。母集合のペア集合と一致する。復元系 10 件は U-R1 への繰り延べとして母集合に記録されている |
| 19 | **サーバー側の (d) runner**(pytest): 資産を読み、適用核に注入して DB を観測し、結果検査で比較する | サーバー側の資産がすべて green。負例(部分確定を起こす変異)が red になる |
| 20 | **クライアント側の (d) runner**(Vitest): `frontend/src/testing/failureScenarioAdapter.ts` を、改訂後の資産契約と P3・I6 の資産に対応させる。`frontend/src/lib/sync/prohibitions.spec.ts:577-580` の `EXPECTED_TESTING_SOURCE_FILE_NAMES` を、`src/testing/` に足す .ts に合わせる(第 1 改訂)。I6 は、サーバーの確定応答(`accepted_at` を含む)を受けた後・端末永続化の前に注入し(`frontend/src/lib/sync/durableQueue.ts` の I6 の注入口を使う)、端末の状態を比較する | クライアント側の資産がすべて green(`pnpm test`)。I6 の注入点で、端末に受理結果が残らない・同期済みとして扱われない・再起動後の扱いが資産の期待どおりになる。負例(注入後も端末に結果が残る変異)が red になる |
| 21 | **TSK-330・TSK-332 の参照の追随**: `canonOracle.ts`・`canonOracle.spec.ts`・`idempotencyCollision.ts` の受け取り先 | `pnpm test` の該当 spec が green。射程外として残す ID とその理由が、本計画の「やらないこと」と一致する |
| 22 | **受理記録の最終導出**(第 1 改訂): テナント境界の受理記録を、新 4・5・7・9 の変更すべてを覆う本 PR の 1 件として PR の base に対して導出し直し、比較 corpus を再封印する。センサス基準が動けば同じコミットで更新する(#95 の内訳 10・#114 のステップ 5 の手順を準用) | 権威履歴に本 PR の記録が 1 件だけ / 迂回検査・凍結履歴・凍結 archive・センサスの一式 green / **一時の `pull_request` event で受理検査を再現して ok**(ローカルの迂回検査は不変量モードで `change.after` の取り残しを見逃す — #114 の実測)/ CI の backend green |

## 5. DoD(受け入れ基準)

Notion カードの DoD と対応づける。カードの文言と食い違う 1 項目は、カードを直す(下記)。

- [ ] 段階③〜⑧の順序と P1〜P5 の T 要素の集合が、DB テストで固定されている(新ステップ 8〜15)
- [ ] 再送・競合の故障系テスト: ACK 消失後の再送、引き継ぎ後の再送、並行 D5、並行 D2、クラッシュ注入、(d) 資産の runner(カード「再送・競合の故障系テスト」)
- [ ] **NFR-018 のコピー実装を作らない**: ドメイン計算(状態遷移・内容検証)はポートで受け、適用核に書かない
- [ ] **core-areas.json への paths 登録を本 PR で行う**。**重複帰属(sync-protocol × recording-rights)を登録時に明示する**(新ステップ 2・3)
- [ ] **`backend/tests/conftest.py` の差分が 0 行**。`backend/src/pitchlog/db/` にファイルを足していない。依存パッケージを足していない
- [ ] pytest / ruff / ty green。frontend の該当 spec green
- [ ] 横断要求: 物理削除しない(墓標はイベントの追加・改訂は旧版を残す)/ テナント分離(越境テスト)/ 利用者 ID を持たない
- [ ] 緑を「FR-012 充足」と報告しない。FR-012 は、ポートの本物(U-R1・U-X1)が入るまで部分充足
- [ ] TSK-330・TSK-332 を Notion で U-S1 に統合した(取り下げ + 相互リンク)。復元系 10 件を TSK-392(U-R1)へ送ったことを、同カードに記録した
- [ ] sync-protocol.md 10-3 の資産構造の改訂(v0.7 — 第 1 改訂で v0.6 から繰り下げ)が /finalize-doc で確定している(R-10)
- [ ] **第 1 改訂**: data-model.md 11-2 の改訂(v0.8 — `B03` の範囲ごとの行と同期経路の意図 ID・`B06` の配信の行の限定)と sync-protocol.md の改訂(v0.6 — `T7` の「1 件」の追随)が単一の確定ゲートで確定している(R-13・R-14)。data-model.md の digest を持つ資産と ORM 受入シートが追随している
- [ ] **第 1 改訂**: 同期経路の無効化意図が範囲ごとに 1 行、イベントと同じトランザクションで書かれる(P3 と D1 付き経路)。保存済み結果の再掲で重複しない。I5 の配信と再試行が `InvalidationSinkPort` 経由で動き、完了が `delivered` で記録される
- [ ] **第 1 改訂**: `cache-invalidation-contract.json` の配信状態の語彙が DB と一致し(R-15)、範囲名の写像が 1 か所にある
- [ ] **第 1 改訂**: テナント境界の受理記録が本 PR について 1 件だけで、PR の base に対して導出・検証済み(新ステップ 22)

**カードの修正(人間へ上げる)**: カードの「ゴールデンベクタ(`contracts/`)との一致」は対象が存在しない。同期の故障系テストの置き場は `tests/fixtures/sync-protocol-failures/`(SP:1712)で、`contracts/` は NFR-019(a) 専用(`contracts/README.md:3`)。本 PR では「(d) 資産と runner」に読み替える。

## 6. テスト計画

| NFR-019 の種別 | 足すもの | 置き場 |
| --- | --- | --- |
| 単体 | 型・ポート・D5 分類・A5 合成・契約検査 | `backend/tests/test_sync_apply_*.py` |
| 越境 | 他テナントの同じ D5、他テナントの試合は B6、9 表の operation の越境 | `backend/tests/test_sync_apply_*_boundary.py` |
| 故障系 (d) | 資産 16 件(既存 4 の移行 + 新規 12)と runner、クラッシュ注入、並行 D5・D2、RG1 のロールバック、I5 の配信 | `tests/fixtures/sync-protocol-failures/`(資産)、`backend/tests/test_sync_apply_*.py`(runner・DB) |
| 一致性 (a) | **対象外**。同期は NFR-018 の対象列挙に入っていない(REQ:892) | — |
| E2E (c) | **対象外**。入口を開かないため(R-3)。入口 PR で足す | — |

- DB テストは平場に置き、`backend/tests/db_fixtures.py` の fixture(`disposable_postgres_cluster`・`provisioned_product_catalog`)を明示 import する。seed と観測は RLS に掛からない接続(applicator / observer)で行う(スパイクで確認)。conftest は変えない
- Codex の sandbox では Docker を使えないので、DB テストは Claude が各ステップで実行する(スパイクで確認)
- 検証はステップごとに影響範囲だけを回す。**第 1 改訂: 各ステップで backend の DB 不要の全件を回す**(凍結資産を動かすステップでは迂回検査・凍結履歴・凍結 archive・センサスの一式も)。DB の全件は CI に任せる

## 7. 第 1 改訂で人間の承認を受ける事項

| # | 事項 | 作成者の案 | 理由 |
| --- | --- | --- | --- |
| A-1 | **D1 付き経路(トリガー 1・3・4 の記録側)の意図 ID の導出** | **`<トリガー>:<イベントの D5>:<範囲>`** — D3 を前進させたイベントの D5(べき等キー)と範囲から導く | D5 はイベントに 1 つで全経路一意(`UNIQUE (tenant_id, D5)` の台帳)。保存済み結果の再掲では同じ D5 なので同じ意図 ID になり、`B03` の狙い(重複作成が構造的に起きない)を保てる。`V10` も `V11` も要らない |
| A-2 | **D1 付き経路の行の量** | 受け入れる(1 イベント = 1 トランザクションで、D3 を前進させた各イベントが 5 範囲 × 1 行) | 正本の発火条件(SP 8-5「D3 が前進したこと」)と 6.2 の対応表(トリガー 1 は 5 範囲すべて)の帰結。未配信の行は `(tenant_id, delivery_status)` の索引で引ける。配信の実体が入るまで行は溜まる(キャッシュ本体を入れる単位の申し送り) |
| A-3 | **スパイクのブランチと worktree の削除** | 本改訂の承認の後に削除する | スパイク自身の承認済み計画が「転記の後に削除」と定め、research.md に転記済み。origin に無いので削除は戻せない |

