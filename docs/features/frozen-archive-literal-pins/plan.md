---
feature: frozen-archive-literal-pins
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-01・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ec93b75e6878109a146c1a822b8f139
branch: fix/frozen-archive-literal-pins
created: 2026-10-01
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: frozen_archive のテストのリテラル固定を外す(TSK-466)

## 1. 背景・目的

**Notion**: [TSK-466](https://app.notion.com/p/3ec93b75e6878109a146c1a822b8f139)(出所: **TSK-444 の報告 2026-10-01** と委任元の原典確認。TSK-448 の `/task-done` 手順 7)
**調査メモ**: [research.md](research.md)(2026-10-01 — 調査 3 本の統合。矛盾 1 件は委任元が原典で裁定)
**詳細設計**: [design.md](design.md)

**TSK-448(PR #83)が入れたテストが、`contracts/tenant_boundary/base-allowlist.json` へ受理記録を 1 件足す PR を例外なく落とす。**

**実測**: TSK-444(PR #82)のブランチで **48 件が落ちる**。develop 単独では 363 passed。**#74・#87・#443 も同じところで落ちる**(未実測 — 契約上そうなるという推論)。

**落ちる箇所は 11 箇所**([design.md](design.md) 0・[research.md](research.md) 1)。起票時の認識は 4 箇所で、**`SnapshotArchiveMetrics` の 3 群が漏れていた**。

**要件 FR/NFR との関係**: **要件書に上位根拠は無い**([research.md](research.md) 3 — spec-checker が独立確認)。**NFR-021 の母集団は `docs/ops/nfr021-acceptance/` 配下のみで `contracts/tenant_boundary` は入らない**(設計書 `:886` `:893` `:895`)。**NFR-018 の対象列挙に「参照集合を数える処理」は入らない**(同 `:892`)。**法源は設計書 7.7 と 6.3 だけ。要件書の改訂は不要。**

**本タスクが開くもの**: **#82 の harness ジョブ**。444 は本タスクの着地を待っている(合意済みのマージ順序 #82 → #74 → #87)。

## 2. スコープ

### やること

- **[design.md](design.md) 1 節のクラス A・B の置換** — 参照集合・版列・metrics・`len(authority_history)` を**独立オラクルまたは構造条件**へ置き換える
- **[design.md](design.md) 2 節の corpus digest を「追記不感応・改竄検知」の形へ** — **生成時点の履歴 prefix と snapshot 集合を固定**し、**追記は通し、改竄・削除は red にする**(**1 周目 P1-1 で「丸ごと外す」初稿を却下**)
- **既存 drift 試験 1 本の正例への反転と、負例 2 本の新設**([design.md](design.md) 2-4 — 1 周目 P1-2)
- **追記不感応を機械で示す試験の追加**([design.md](design.md) 2-5 — 1 周目 P1-3。ケース追加ではなく試験 1 本)
- **受理記録を 1 件足した合成状態で `tests/` 全件が green になることの実測**

### やらないこと

| 外すもの | 理由 | 送り先 |
| --- | --- | --- |
| **`scripts/frozen_archive.py` / `scripts/check_tenant_boundary_bypass.py` の変更** | **製品経路に現況のリテラル固定は 1 件も無い**([research.md](research.md) 1・3)。触ると凍結基準が動き、本タスク自身が受理記録を要することになる | — |
| **`acceptance_id` の `#79` / `#81` literal 11 箇所** | いまは落ちない。将来の衝突 | 新規起票([design.md](design.md) 4) |
| **`tests/test_frozen_archive.py:225-228` の無力な assertion** | 退化実装が素通りする。**リテラル固定とは別の欠陥** | 新規起票(同) |
| **448 側の残滓 2 件**(`design.md:120` の「18 件」・research.md の行ずれ) | 448 は閉じている | 新規起票(同) |
| **設計書 7.7 の条文改訂** | **本書は結論を出さない。** [design.md](design.md) 3 に**両分岐の作業**を書き、**ステップ 5 の前提ゲート**として人間が判断する(1 周目 P1-4)。条文へ書き足すなら版繰り上げで `/finalize-doc` が要る | 人間の判断 |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/requirements/**` | **反映なし**(上位根拠が無い — [research.md](research.md) 3) | — |
| `docs/design/**` | **反映なし** | — |
| `docs/adr/**` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(7.7 の条文は改訂しない — 2 節「やらないこと」) | — |
| `docs/development/harness-evaluation.md` | **`## 候補` へ新規 2 件** — ①「設計書 7.7 の射程がテストの期待値に及ぶか条文が決めていない」([design.md](design.md) 3 節の判断の記録)②「現況のリテラル固定を外す是正は、欠陥と仕様が同じ assertion に乗っていることがある」+ **変更履歴表に 1 行**。**`H-*` の採番なし・版は上げない**。**TSK-444 の候補「検査が、そのタスクに無関係な PR を巻き込んで赤にする」は本記述の時点で develop へ未着地のため追記できず、②から相互参照を張る旨だけ記した** | **PR レビュー**(7.6-3 前段) |
| `docs/README.md` | 台帳行の現行化(候補数・最終更新日) | **PR レビュー** |

## 4. 実装方針

**重さ分類: コア領域。** 根拠: 変更対象 4 ファイルがすべて `.claude/core-areas.json:365-374` に登録されている(`tests/test_frozen_archive.py` / `tests/test_frozen_archive_case_runner.py` / `tests/test_check_tenant_boundary_bypass.py` / `tests/fixtures/frozen-archive-cases/*`)。**意味範囲の正は設計書 6.3 の境界定義表で、落とし込み規則 ①(`:400`)と「判定に迷うコードは含む側に倒す」(`:399`)の当てはめ**([research.md](research.md) 3)。

→ **ADR-001 により敵対レビュー必須・人間の逐行確認必須。**

**実装の敵対レビュー**: **1 周**(2026-10-02 — P0 0 / P1 1 / P2 2 を反映。P1 = 新規孤児 snapshot の検出力低下 / P2 = 計画書の「ケース 12」の残滓・原文改竄の記述の不正確さ)。

**設計の詳細は [design.md](design.md)。** 要点のみ:

- **置換の原則**: 「守りたいもの」を落とさずに「偶然そこにあるもの」だけを外す([design.md](design.md) 0 の表)
- **参照集合は独立オラクルとの集合一致**へ(被検査実装の出力をそのまま期待値にしない — [design.md](design.md) 1-1)
- **corpus digest は残す。入力を正規化する**([design.md](design.md) 2-3)。**現況から再計算する案は採らない** — drift 変異テスト 5 本が恒真になるため([design.md](design.md) 2-6)
- **正規化が意図であることを追記不感応の試験で機械的に示す**([design.md](design.md) 2-5。**1 周目 P1-3 でケース追加をやめ、試験 1 本を足す形へ変えた** — `CaseDefinition` は 1 action + 前版/現版の終了コードなので 12 件目では 11 ケース分の照合にならない)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **受理記録を 1 件足した合成状態を作る道具を用意し、現況で落ちる箇所を実測する**(検証用スクリプトは `/tmp` に置き、記録だけ残す)。**「失敗テスト ID → 根因の固定箇所」の対応表を作る** | **1 周目 P2-6 の反映**: **失敗テスト ID の集合ではなく、対応表が [research.md](research.md) 1 の 11 箇所と exact-set 一致する**(`prepare_case` は digest を先に検査するため、digest 1 箇所が多数の failure へ連鎖する — `runner.py:735`)。**条件付きの 4 件**(`#79`/`#81` の衝突・`trees` exact-set・manifest description・.py の hex 走査)**が現況では落ちないことも実測する**。**この確認を経ずにステップ 2 へ進まない** |
| 2 | **参照集合の置換**([design.md](design.md) 1-1)— `tests/test_frozen_archive.py` の `:131` `:139` `:164` `:198-200` `:210-212` を独立オラクルとの集合一致へ | **対象 assertion が受理記録 +1 の合成状態で green**(**ステップ 5 の前は corpus digest が先に落ちるため、合格は assertion 単位で判定する** — 1 周目 P2-6)。**変異で red**: 「常に空集合を返す」実装 / **期待表照合を通過する誤抽出 1 件**(`external_snapshots` の extractor が `before` 側だけを見る — 1 周目 P2-5)。**変異ごとに red の原因(どの検査が落としたか)を記録する**。**`scripts/frozen_archive.py` を 1 バイトも触らない** |
| 3 | **版列と `len(authority_history)` の置換**([design.md](design.md) 1-2・1-4) | **対象 assertion が受理記録 +1 で green**。**変異で red**: 先頭を v2 にする / 途中に v1 を混ぜる / 履歴を 1 件に減らす。**`:3346` は `FROZEN_BASELINE_ASSETS` の 8 インスタンスすべてで green** |
| 4 | **metrics の置換**([design.md](design.md) 1-3) | **対象 assertion が受理記録 +1 で green**。**変異で red**: `_measure_snapshot_archive` が件数を 1 ずらす / バイト数を 1 ずらす / 孤児を数え落とす。**閾値ちょうどの受理を守る試験(`:363-364` `:396-397`)が無変更で green のまま** |
| 5 | **【前提ゲート】[design.md](design.md) 3 節の 7.7 射程判断を人間から得る**(分岐 A / B)。**そのうえで corpus digest を「追記不感応・改竄検知」の形へ**([design.md](design.md) 2-3・2-7)— `runner.py` の 3 関数と `manifest.json` の `pinned_prefixes` | **判断が [design.md](design.md) 3 節へ日付・判断者つきで記録されている**(分岐 B なら同節の追加作業を実施)。**受理記録 +1 で digest が動かない**。**変異で red**: 先頭 `k` 件の履歴のいずれかを書き換える / 固定済み snapshot を 1 件消す / 検査器 1 本を変える / 資産の宣言部を変える / 資産ファイルを 1 本足す / `runner.py` を変える / `pinned_prefixes` を改竄する。**`:147` `:167` `:193` `:237` の 4 本が red のまま**(**恒真化していないことを実測で示す**)。**安全の守り 3 つ**([design.md](design.md) 2-3): ① **除外先を資産の `baseline_control.identity.field` 宣言から導出している**(フィールド名をハードコードしていない)② **`pinned_prefixes` 自体が digest に拘束されている**(改竄で red)③ **fail-closed**: `k > len(history)`(記録の削除)/ `m` の snapshot が不在 / 宣言が読めない / `k < 2` / `m < 1` が**すべて red**(保留・skip・中立を認めない — 設計書 7.7-3 `:609-612`) |
| 6 | **drift 試験の反転と新設**([design.md](design.md) 2-4)+ **追記不感応の実測試験**([design.md](design.md) 2-5)— `:212` を `test_prepare_case_accepts_appended_history_record` へ反転し、**既存履歴の書き換え**と**固定済み snapshot の削除**の負例を新設。あわせて `test_appended_history_record_does_not_change_case_outcomes` を足す | **反転した `:212` が green**(適法な追記で digest 不変)。**新設 2 本が red を出す**。**不感応試験が green で、11 ケースの終了コードが追記前後で一致する**。**11 ケースのうち 1 件でも期待値を変えると red** |
| 7 | **全ゲート + 受理記録 +1 の合成状態での全件 green の実測** + **台帳と `docs/README.md` の反映** | `uv run pytest tests/` / `uv run ruff check .` / `uv run ty check` green。`uv run python scripts/check_tenant_boundary_bypass.py` exit 0。**受理記録 +1 の合成状態でも `tests/` 全件 green**(ステップ 1 の道具で再実測)。**台帳の追記が 7.6-3 前段の範囲**(版を上げない・`H-*` を採番しない) |
| 8 | **確認対象コミットの SHA を固定した人間の逐行確認を worklog へ記録**(履歴は追加しない) | worklog に**確認対象コミットの SHA** と `対象= / 範囲= / 方法= / 確認者= / 確認日=`。**確認項目に「置換が『守りたいもの』を落としていないこと」「corpus digest が恒真化していないこと」「既存履歴の改竄と既存 snapshot の削除が依然 red になること」「7.7 の射程判断」「製品経路を触っていないこと」が列挙されている**。**確認後の差分は証跡ファイルに限る** |

## 5. DoD(受け入れ基準)

- [ ] 【機】**受理記録を 1 件足した合成状態で `uv run pytest tests/` が全件 green**
- [ ] 【機】**既存履歴の先頭 `k` 件のいずれかを書き換えると red**(1 周目 P1-1 — digest から履歴を丸ごと外していない)
- [ ] 【機】**固定済み snapshot を 1 件削除すると red**(同上)
- [ ] 【機】**`:147` `:167` `:193` `:237` の 4 本が依然として red**(恒真化していない)
- [ ] 【機】**反転した `:212` が green**(適法な追記で digest 不変 — 1 周目 P1-2)
- [ ] 【機】**追記前後で 11 ケースの終了コードが一致する**([design.md](design.md) 2-5 — 1 周目 P1-3)
- [ ] 【機】**各置換に対応する変異がすべて red になり、red の原因が記録されている**(1 周目 P2-5)
- [ ] 【機】**`scripts/frozen_archive.py` と `scripts/check_tenant_boundary_bypass.py` の差分が 0 バイト**
- [ ] 【機】`uv run ruff check .` / `uv run ty check` / `uv run python scripts/check_tenant_boundary_bypass.py` が green
- [ ] 【機】**ステップ 1 の「失敗テスト ID → 根因の固定箇所」対応表が 11 箇所と exact-set 一致**(1 周目 P2-6)
- [ ] 【判】**設計書 7.7 の射程判断**([design.md](design.md) 3)**が日付・判断者つきで記録され、分岐 B なら追加作業が実施されている**(判定者: **人間**)
- [ ] 【判】**corpus digest の固定範囲が [design.md](design.md) 2-3 の表と一致している**(判定者: 人間。**2026-10-01 に識別値の除外と守り 3 つを承認済み**)
- [ ] 【機】**`k > len(history)`(記録の削除)で red**(fail-closed の要)
- [ ] 【機】**`m` の snapshot が 1 件でも不在なら red** / **`k < 2`・`m < 1` の退化値で red**
- [ ] 【機】**除外先が資産の `baseline_control.identity.field` 宣言から導出されている**(ハードコードした列挙でない)
- [ ] 【機】**`pinned_prefixes` を改竄すると red**(除外範囲の拡大自体が検出される)
- [ ] 【逐】**逐行確認**: 確認対象コミットの SHA を固定して実施した。**確認後の差分は証跡ファイルに限る**
- [ ] 【機】**射程外 4 件が新規タスクとして起票され、[design.md](design.md) 4 の表と対応している**

## 6. テスト計画

**NFR-019 の種別では「単体」と「故障系」。越境・E2E・一致性には足さない**(製品経路に触れないため)。

| 種別 | 足すもの |
| --- | --- |
| **単体** | 独立オラクルとの集合一致(参照集合)/ 構造条件(版列・履歴長)/ 独立計数との照合(metrics) |
| **故障系** | **各置換に対応する変異**(ステップ 2〜5 の合格条件に列挙 — 「常に空集合を返す」「extractor の誤割り当て」「件数を 1 ずらす」「正規化の改竄」ほか)+ **drift 変異 5 本が red のままであることの再確認** |
| **回帰** | **`test_appended_history_record_does_not_change_case_outcomes`**(受理記録の追記に対する 11 ケースの終了コードの不感応。**ケースは足さない**)+ **`test_current_unpinned_snapshots_are_referenced`**(実装の敵対レビュー 1 周目 P1 — 固定一覧に無い snapshot はすべて参照されている) |

**既存の試験で削除するものは無い。** 置換はすべて同じ試験の中の assertion の形を変えるもので、**試験の本数は減らさない**。**足すのは 4 本**: 追記不感応 1 本 / 負例 2 本(固定履歴の改竄・固定 snapshot の削除)/ 新規孤児の検出 1 本。**`test_prepare_case_rejects_appended_history_record` は削除ではなく正例へ反転**([design.md](design.md) 2-4)。
