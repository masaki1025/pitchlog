---
status: approved
---

# ADR-001: コーディング委任の Codex モデル・effort 選定

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 1.0 | 2026-08-07 | 新設。ハーネス設計書の確定ゲート(敵対レビュー5周 → PO 承認)で一括検証・approved 化 | approved |
| 1.0 | 2026-08-07 | PO 指示により effort を調整(通常実装/一次レビュー = max・コア領域 = xhigh・軽作業 = luna xhigh)+ Web 調査行を追加。max の CLI 指定可否を実機検証 | approved |
| 1.0 | 2026-08-17 | 様式の正規化(変更履歴表の新設。決定内容の変更なし) | approved |
| 1.1 | 2026-09-27 | **GPT-6 世代への対応表の再設計(起案)**(TSK-463・PO 判断 2026-09-27・徳光 尋弥): 見直しトリガー 3 条件(世代交代・料金改定・新 tier 登場)が同時に成立したため改訂。**決定** = 全枠を `gpt-6-sol`(機械的軽作業のみ `gpt-6-luna`)へ・effort は v1.0 の値を据え置き・`gpt-6-astra` は本版では載せない(昇格が必要になった実例で v1.2)・Fast / Ultra は使わない。**新設** = 決定表の固定構文(ラッパーとの同期テストが読む)・分類主体と優先順位・実測期間(開始/終了/記録者/判定者・記録項目)と巻き戻し条件・Codex CLI 0.157.x 以上の前提とラッパーの版検査・`probe` 経路による全組の受理確認。**旧表(v1.0)の要約** = 通常実装/一次レビュー `gpt-5.6-terra` max・軽微 terra medium・コア領域/敵対レビュー `gpt-5.6-sol` xhigh・機械的軽作業 `gpt-5.6-luna` xhigh・Web 調査 terra high(深い技術検証は sol xhigh)。**射程宣言(7.3-7)**: 本改訂で確定する範囲 = ① 決定表 8 行のモデル ID と effort ② 決定表の固定構文と行キー → ラッパー定数の対応・分類主体と優先順位 ③ 実測期間・記録項目・巻き戻し条件・見直しトリガー ④ astra 不掲載と Fast / Ultra 不使用の方針 ⑤ ラッパーの版検査と `probe` 経路の要件。実装時(TSK-463 の後続ステップ・後続タスク)に確定する範囲 = ラッパー定数・版検査・`probe`・同期テストの実装・`exec` 経路での受理の実機検証(追随行で記録)・実測期間後の再判定(v1.2 の要否)・Claude 側のモデル既定(設計書 8.1 / 8.5 — 本 ADR の対象外)。設計書 v1.18 と**単一の確定ゲート**(7.3)で一括検証する。**確定ゲート 反映1周目**(sol xhigh・P0 0 / P1 12 / P2 3 — 全件採用): 固定構文へ effort 許容値と行の記載順・各 1 回を明記 / 行の意味に `review normal`・`review adversarial` 経路の実利用範囲を反映 / 分類主体(計画作成者)と優先順位(コア領域 > 軽微 > 機械的軽作業 > 通常)を規定 / 実測期間の開始・終了・記録者・判定者と記録項目・巻き戻し閾値を確定 / 実機検証を決定表の全 5 組(read-only の `probe` 経路)へ / ラッパーの Codex 版検査(fail-closed)を帰結へ / GPT-6 Sol の公式声明を再照合済みに区分。**反映2周目**(P0 0 / P1 8 / P2 1 — 全件採用・全件起因): 軽微な修正の条件を設計書 6.1 の fast path 全 3 条件へ / `review normal` の範囲から「通常 PR」を除く(通常 PR の必須レビュアは Claude — 6.3)/ `重さ分類` の欠落・空値・不正値は通常へ既定せず停止(fail-closed)/ `probe` は read-only + cached search と明記。**反映3周目**(P0 0 / P1 4 / P2 1 — 全件採用。起因過半 2 周連続で 7.3-6 発火 → **PO 裁定 2026-09-27・徳光 = 続行指示**〔射程不変〕): `review normal` の注記を「Codex が実装した通常 PR の必須レビュアは Claude」へ / 分類主体を通常経路(計画作成者・テンプレは空値)と fast(事前 OK の人間・`軽微` + `fast` の一括更新をラッパーが両値検査)に分ける。**反映4周目**(P0 0 / P1 3 / P2 0 — 全件採用): fast 経路の計画書はブランチ名から導出した正規位置だけを受理(重複・不一致・別位置は停止)。**反映5周目**(P0 0 / P1 1 — 採用。起因過半 2 周連続で 7.3-6 再発火 → **PO 裁定 2026-09-27・徳光 = 続行指示**〔射程不変〕): 負例の列挙を frontmatter 不正の内訳と機構読取キーの範囲まで明示。**反映7周目**(最終全文確認周の再実施・P0 0 / P1 3 — 全件採用): 集計者を時間条件から独立(TSK-463 の実施者)/ `probe` はラッパー内蔵の固定短文で stdin を読まない / `finalize-doc` スキルの割当て複製を同期対象へ。**反映9周目**(最終全文確認周・12 回目・P0 0 / P1 1 — 採用): `fast` 経路は `status: active` を含む 3 値を検査(in-review のままの fast 実行を機械的に排除)。**反映11周目**(最終全文確認周・14 回目・P0 0 / P1 1 / P2 1 — 全件採用): カタログ追加版の記録を両出典(公式変更履歴 0.156.1 hotfix / GitHub リリースノート 0.157.0)で記載 | in-review |
| **1.1** | 2026-09-27 | **確定ゲート通過(approved)**: 敵対レビュー **18 回**(gpt-5.6-sol xhigh — 全文 6 + 差分 12)・**反映 13 周**・**指摘 48 件(P0 0 / P1 39 / P2 9)を全件採用・不採用 0**・7.3-6 エスカレーション 2 回(3 周目・5 周目 — いずれも PO 裁定 = 続行指示)・6 周警告 1 回(PO 判断 = 続行)・適用版 = 7.3 v1.17(条文 SHA `ab72a58a`)→ **PO 承認(2026-09-27・徳光 尋弥)**。採否記録は `docs/worklog/2026-09-26-harness-model-refresh.md`(設計書 v1.18 と単一ゲート) | approved |

| 項目 | 内容 |
| --- | --- |
| 状態 | **approved**(v1.1 — 2026-09-27。設計書 v1.18 と単一の確定ゲート〔敵対レビュー 18 回・反映 13 周〕→ PO 承認) |
| 日付 | 2026-09-27(v1.1)/ 2026-08-07(v1.0) |
| 決定者 | プロダクトオーナー(徳光 尋弥 — v1.1 の 3 判断: 対応表 = 案 A・effort 据え置き・主セッションの機構化〔後者は設計書 8.1 の所管〕)+ Claude(調査・起案) |

## 文脈

### v1.1 の文脈(2026-09-26〜27 調査 — 典拠つきの詳細は `docs/features/harness-model-refresh/research.md`)

- **見直しトリガーの成立**: OpenAI は GPT-6 世代として `gpt-6-astra`(2026-09-03)・`gpt-6-sol`・`gpt-6-luna`(2026-09-22)を公開した。**GPT-6 に terra 相当の tier は無く、astra が上位に加わった**ため、v1.0 の帰結が前提にした「tier 名は維持されつつ各 tier が独自更新される」は成立せず、ID 置換ではなく対応表の再設計が必要になった(新 tier 登場・世代交代)。あわせて API 料金も改定された(料金改定)
- **本機のカタログ(codex-cli 0.157.1・2026-09-27 再取得)**: `gpt-6-sol` = "Workhorse model for coding and everyday work."・effort low / medium / high / xhigh / max(+ 対話専用 ultra)・既定 medium / `gpt-6-luna` = "Fast and affordable model for easier tasks."・low〜max / `gpt-6-astra` = "Frontier intelligence for the most demanding work."。gpt-5.6 の 3 tier は "Older" 表記で残る。**`gpt-6-sol` / `gpt-6-luna` のカタログ追加**: 公式変更履歴上のカタログ追加は Codex CLI 0.156.1〔0.156.0 向け hotfix〕・GitHub リリースノートでは 0.157.0〔2026-09-25〕に記載・モデル定義の `minimal_client_version` は 0.155.0。**本ハーネスの運用下限は本機で確認済みの 0.157.0**(0.153.4 では選べなかった)
- **API 料金($/1M tok: input / cached / output — 公式 pricing で照合済み)**: `gpt-6-astra` $10 / $1 / $50 ・ **`gpt-6-sol` $2 / $0.20 / $10** ・ `gpt-6-luna` $0.10 / $0.01 / $0.50 / 旧: `gpt-5.6-sol` $4 / $0.40 / $20(2026-08-21 改定の promotional。v1.0 に書いた $5/$30 は改定前)・`gpt-5.6-terra` $2 / $0.20 / $12・`gpt-5.6-luna` $0.20 / $0.02 / $1.20。→ **gpt-6-sol は 5.6-sol の半額で、5.6-terra と同じ input 単価**
- **サブスク利用枠の消費重み**(ChatGPT Business / Enterprise の credit rate card・2026-09-24 更新 — Plus / Pro の係数は非公開のため**代理指標**): 1M tok あたり astra 250 / 25 / 1,250・**sol 50 / 5 / 250**・luna 2.5 / 0.25 / 12.5 / 旧 5.6-sol 100 / 10 / 500・5.6-terra 50 / 5 / 300。→ **gpt-6-sol は 5.6-sol の 2 倍長く使え、5.6-terra と同等**。Fast(旧 priority)は API 2 倍・Business 2.5 倍。Ultra は API の effort 値ではなく Codex 側の「max 推論 + 自動タスク委任」モードで固定倍率不明
- **公式の位置づけ(GPT-6 Sol — OpenAI 発表ページを Codex が 2026-09-27 に再照合済み)**: "improves substantially over GPT-5.6 Sol"(FrontierCode)・"match Claude Fable 5.1 xhigh at much lower cost"・"higher usage limits and lower cost"・API 価格は GPT-5.6 promotional 比 50% 引き下げ。**Astra 対 5.6-sol の数値**(Terminal-Bench 4.0 57.9% vs 37.3%・FrontierCode 1.1 Main 53.3 vs 47.5)は Codex の引用のみで**未照合**。公式は「高い effort は利用枠をより多く使い得るが常に良い結果になるわけではない」と明記
- **移行前のベースライン(ローカル実測 — Codex 60 日・`~/.codex/sessions` の集計)**: `gpt-5.6-sol` xhigh(敵対レビュー・確定ゲート)42 セッション・入力 105.7M(うちキャッシュ 96.6M)・出力 0.79M / `gpt-5.6-terra` max(実装・一次レビュー)49 セッション・入力 89.0M(81.0M)・出力 1.22M。入力の 9 割超がキャッシュで、出力は消費の 3 割程度。rate card の重みで換算すると、全枠 gpt-6-sol 化で **現行比 −35%**(コア・敵対を astra にすると +97%)の試算

### v1.0 の文脈(2026-08-07 — 当時の前提として保存)

- 開発ハーネス([設計書](../development/dev-harness-design-2026-08-07.md))はコーディングを Codex に委任する。モデルは GPT-5.6 世代の 3 tier(sol / terra / luna)+ 旧 spark から選ぶ必要があった
- 実測・公式情報(2026-08-07 調査。本機 codex-cli v0.146.1 のモデルカタログ + 公式ドキュメント): `gpt-5.6-sol` = フロンティア(当時 API $5/$30・サブスク消費は terra の 2 倍)/ `gpt-5.6-terra` = バランス型(API $2/$12。SWE-Bench Pro で sol と 1.2pt 差)/ `gpt-5.6-luna` = 高速・安価(消費 sol の 1/5)
- effort は CLI から **max まで指定可能**(実機検証 2026-08-07: `codex exec -c model_reasoning_effort=max` で実行成功。公式 config リファレンスの記載は xhigh までだが実装は受理する)。対話ピッカー専用なのは Ultra のみ
- Codex クラウドのコードレビューは公式に sol が担当(2026-07 末〜)。要件フェーズの敵対レビューは sol / sol ultra の実績あり(要件書変更履歴 v1.1 / 1.4 / 1.5)

## 決定

「作業の重さ」で選ぶ。**通常経路の分類主体は計画作成者**(根拠を実装計画書 4 節に記録して frontmatter `重さ分類` に書く。計画書テンプレートは `重さ分類` を**空値**で置き、/plan が 4 値のいずれかへ必ず置換する)。**fast path の分類主体は事前 OK を出す人間**(適用時に計画書雛形の `重さ分類: 軽微` と `実行方式: fast` を一括更新し、ラッパーの `fast` 経路は、登録済み worktree のブランチ名〔`feature/<slug>` / `fix/<slug>`〕から導出した**正規位置 `docs/features/<slug>/plan.md` の計画書だけを受理**し、**`status: active`・`重さ分類: 軽微`・`実行方式: fast` の 3 値**を検査してから「軽微な修正」行を適用する。`status: in-review` を含むいずれかの不一致ではモデル実行前に停止する)。**ラッパー(`codex_run.py`)がその分類を機械適用する**(人が実行のたびにモデルを選ばない。**`重さ分類` の欠落・空値・不正値、および fast の 3 値不一致は「通常」「軽微」へ既定せず、モデル実行前に停止する** — fail-closed)。分類は次の優先順位で判定し、**先に一致した 1 分類だけを採る**: **コア領域**(設計書 6.3 のリストに触れる — 迷う場合は含む側に倒す)> **軽微な修正**(設計書 6.1 の fast path の**全 3 条件**〔① 非コア領域 ② 小差分(目安 50 行以下)かつ正本への影響なし ③ typo・コメント・小さなテスト修正・設定微調整の類〕を満たし、人間の事前 OK がある)> **機械的軽作業**(リネーム・ボイラープレート等、判断を要しない変更)> **通常実装**(それ以外)。

**下表は固定構文**で、ラッパーとの同期テスト(`tests/`)が構造的に読む: ヘッダ固定・**下記 8 行を記載順に各 1 回**・「作業」セルは行キーと完全一致・「モデル」セルは code span ちょうど 1 個(中身がモデル ID)・「effort」セルは **`low` / `medium` / `high` / `xhigh` / `max` のいずれか 1 トークン**(装飾・注記なし)。

| 作業 | モデル(明示 ID 固定) | effort |
| --- | --- | --- |
| 通常実装 | `gpt-6-sol` | max |
| 軽微な修正 | `gpt-6-sol` | medium |
| コア領域の実装 | `gpt-6-sol` | xhigh |
| 機械的軽作業 | `gpt-6-luna` | xhigh |
| 一次コードレビュー | `gpt-6-sol` | max |
| 敵対レビュー・コア領域 PR・正本確定ゲート | `gpt-6-sol` | xhigh |
| Web 調査 | `gpt-6-sol` | high |
| Web 調査(深い技術検証 `--deep`) | `gpt-6-sol` | xhigh |

- 行の意味: 通常実装 = CRUD・画面・帳票・テスト / 軽微な修正 = 小さな差分・微調整(fast path)/ コア領域の実装 = 設計書 6.3 のリスト / 機械的軽作業 = リネーム・ボイラープレート / **一次コードレビュー = `review normal` 経路**(通常の実装計画書のレビュー・Claude が直接書いたコードのレビュー。**Codex が実装した通常 PR の必須レビュアは Claude**〔設計書 6.3 の反対側レビュー〕であり本経路ではない)/ **敵対レビュー・コア領域 PR・正本確定ゲート = `review adversarial` 経路**(コア領域の実装計画書・コア領域 PR・正本確定ゲート 7.3)/ Web 調査 = `research` 経路(`--deep` はコア領域に関わる深い技術検証)
- 行キー → ラッパー定数(`.claude/scripts/codex_run.py`)の対応: 通常実装 → `MODEL_MAP["通常"]` / 軽微な修正 → `MODEL_MAP["軽微"]` / コア領域の実装 → `MODEL_MAP["コア領域"]` / 機械的軽作業 → `MODEL_MAP["機械的軽作業"]` / 一次コードレビュー → `REVIEW_NORMAL` / 敵対レビュー・コア領域 PR・正本確定ゲート → `REVIEW_ADVERSARIAL` / Web 調査 → `RESEARCH` / Web 調査(深い技術検証 `--deep`) → `RESEARCH_DEEP`
- **effort は v1.0 の値を据え置く**(PO 指示 2026-09-27。出力トークンは消費の 3 割程度で、モデル切替と別変数として実測期間の終了時に再判定する)
- **`gpt-6-astra` は本版では対応表に載せない**(単価・消費重みが 5.6-sol の 2.5 倍で「利用上限内で長く働く」目的に反する。必要になった実例で v1.2 として昇格を起案する — 帰結の巻き戻し条件)
- **Fast(priority)tier と Ultra は使わない**(Fast は利用枠を増やす方向・Ultra は `exec` の effort 値として指定できず消費倍率も不明)

## 理由

1. **欠陥コストで線を引く(継承)**: 試合記録の喪失・クライアント/サーバー計算の乖離(要件書 R-3/R-5・G-1)は取り返しがつかない → コア領域と品質ゲートには**旧フロンティア(gpt-5.6-sol)以上の水準**を維持する。gpt-6-sol は 5.6-sol の後継 tier で、公式が "improves substantially over GPT-5.6 Sol" と述べる。GPT-6 世代のフロンティア(astra)を投じない代わりに、水準差は **effort(通常 max / コア・敵対 xhigh)と依頼文(設計書 6.3 の敵対姿勢・7.3-5 の規約)**で保ち、品質下限を実測期間で検証する(帰結)
2. **物量は同一 tier に寄せる**: 通常枠(旧 terra)も gpt-6-sol へ。input 単価・利用枠の重みは terra と同等以下で世代は上位。GPT-6 に terra 相当が無い以上、通常枠を luna に落とすのは品質を下げる方向で採らない
3. **利用上限内で長く働く(v1.1 で追加)**: 敵対レビュー・確定ゲート(sol xhigh)が Codex 側消費の約半分を占める実測に対し、gpt-6-sol は同 effort で消費重みが半分。全枠 gpt-6-sol 化で現行比 −35% の試算(Business rate card の代理指標)。astra 化は +97% で目的に反する
4. **レビュー水準の連続性**: 敵対レビューは引き続き「通常枠より高い effort(xhigh)+ 敵対依頼文」で回す。要件フェーズ以来の sol 系での実績(H-30: 計画レビュー 6 周で見えなかった P0 を確定ゲート 1 周目で 3 件検出)を、同系統の後継 tier で引き継ぐ
5. **エイリアスを使わず明示 ID で固定(継承)**: `gpt-6`(提供側が上位 tier へ振り向ける可能性がある)等のエイリアスは使わない(モデルドリフト防止。設計書 8.5 の Opus 5.5 固定と同じ規律)
6. **表と機構の乖離を機械検査する(v1.1 で追加)**: v1.0 では対応表とラッパー定数の一致を検査するテストが無く、乖離は CI で検出されなかった。決定表を固定構文にして同期テストが読む。設計書 9.4 は値・一覧を再掲せず本 ADR を参照する(7.1-1 の複製禁止)

## 帰結

- `.claude/scripts/codex_run.py` が本表どおり `-m <model> -c model_reasoning_effort=<effort>` を自動指定する(設計書 9.4)。**決定表 ↔ ラッパー定数の同期テスト**(固定構文の抽出・負例〔モデル不一致・effort 不一致・行キー欠落・構文違反・行順逆転・行キー重複〕・各経路の引数)を `tests/` に置き、乖離を CI(harness ジョブ)で検出する。`重さ分類` の欠落・空値・不正値で停止すること、`fast` 経路が正規位置の計画書の `status: active`・`重さ分類: 軽微`・`実行方式: fast` の 3 値を要求すること(`status: in-review`・計画書なし・読取不能・frontmatter 不正(非閉止・8 KiB 超過・UTF-8 不正・厳密 status 不適合 — `feature_status.py` と同じ判定)・機構読取キーの重複(全機構読取キーをパラメータ化)・`branch` 不一致・同一 branch を持つ別位置の計画書・3 値の欠落/空値/不一致は停止)も負例テストで固定する
- **前提: Codex CLI 0.157.x 以上**(gpt-6-sol / gpt-6-luna — 公式変更履歴上のカタログ追加は Codex CLI 0.156.1〔0.156.0 向け hotfix〕・GitHub リリースノートでは 0.157.0〔2026-09-25〕に記載・モデル定義の `minimal_client_version` は 0.155.0。**本ハーネスの運用下限は本機で確認済みの 0.157.0**)。**ラッパーは起動前に `codex --version` を解析し、0.157.0 未満または解析不能ならモデル実行前に fail-closed で停止して更新手順(onboarding 1-6)を示す**(既存開発者が onboarding を再実行しない経路を閉じる)。本機は 2026-09-27 に 0.157.1 へ更新し、カタログで `gpt-6-sol` の supported_reasoning_levels(low〜max)と `gpt-6-luna`(low〜max)を確認済み
- **実機検証(受理確認)**: ラッパーに検証専用経路 **`probe`**(sandbox は `read-only`・web_search は `cached`・書き込み・live search を含まない)を設け、本表に現れる**すべての一意な `(model, effort)` の組**(v1.1 では 5 組: sol×max・sol×medium・sol×xhigh・sol×high・luna×xhigh)を実際の `exec` 経路で**ラッパー内蔵の固定短文**(stdin は読まない)により受理確認する。**`review normal` / `review adversarial` は本番の依頼文様式でも受理と判定行を確認**する。結果は TSK-463 ステップ 4 で worklog に記録し、本表へ版を上げない追随行で記録する
- **実測期間**: **開始日 = TSK-463 の機構同期 PR が develop へマージされた日**。開始後に初周を実行した正本確定ゲートを対象とし、**対象 3 ゲートの完了かつ開始から 4 週間の経過の遅い方**で終了する(8 週間を過ぎても 3 ゲートに満たない場合は、その時点の実績で PO が判定する)。**記録者 = 各ゲートの実施者**(当該ゲートの worklog に記録)。**集計者 = TSK-463 の実施者**(通常の終了条件が成立した日、または対象 3 ゲート未満のまま開始から 8 週間が経過した日に、その時点の実績を横断集計して運用評価台帳の候補節へ記録し PO へ提出する)。**判定者 = PO**(v1.2 の要否・effort 引き下げの要否)
- **記録項目(ゲートごと)**: ゲート ID(対象正本と版)・期間・使用した model / effort・レビュー実行回数・各回の遮断回数と再実行回数・入力 / キャッシュ入力 / 出力トークン(Codex の `tokens used` と `token_count`)・P0 / P1 件数と周回数・ゲート通過後に別工程(人間の逐行確認・実装・PR レビュー・CI)が発見した P0 の所在と発見工程。生値の正は各 worklog とし、台帳には横断集計だけを置く
- **巻き戻し条件(いずれかで v1.2 を起案し新規の確定ゲートで再改訂)**: (a) 本表の `(model, effort)` が受理されない(`probe` または本番経路で拒否)(b) **1 ゲート内の安全分類器による遮断回数が 2 回を超える**(5.6-sol 時代の実測 = 1 ゲートで flagged 2 回 — 台帳 2026-09-21 追記 — を基準値とする)(c) **ゲート通過後に、人間の逐行確認・実装・PR レビュー・CI のいずれかが、ゲート対象に残っていた P0 を特定した**実例が出る。品質下限の判定は周回数でなく**検出実例の有無**で行う(H-30: 周回数はモデル差だけの効果と切り分けられない)。v1.2 の候補 = astra 昇格(コア領域・敵対レビュー・`--deep`)
- **見直しトリガー**: 上記 (a)〜(c) / 実測期間の終了(effort 引き下げの要否を含む再判定)/ 料金・レート改定 / 新 tier 登場 / 提供側の廃止告知(gpt-5.6 の 3 tier の廃止日は 2026-09-26 時点で未告知)
- 対話ピッカー限定の Ultra・速度優先の Fast は本ハーネスでは使わない。Claude 側(主セッション・調査サブエージェント)のモデル既定は本 ADR の対象外で、設計書 8.1 / 8.5 が正

## 参照

- 設計書 9.4(参照・注記)・9.2(コマンド一覧)・8.5(調査サブエージェントの既定)・8.1(主セッションの既定)・6.1(fast path・段階実装)・6.3(コア領域・反対側レビュー)・7.3(確定ゲート): [dev-harness-design-2026-08-07.md](../development/dev-harness-design-2026-08-07.md)
- 調査メモ(典拠・実測・決定経緯): [docs/features/harness-model-refresh/research.md](../features/harness-model-refresh/research.md)
- 公式: https://developers.openai.com/api/docs/pricing / https://developers.openai.com/api/docs/models/gpt-6-sol / https://developers.openai.com/api/docs/guides/latest-model / https://openai.com/index/introducing-gpt-6-sol-and-luna/ / https://help.openai.com/en/articles/11481834-chatgpt-rate-card-business-enterpriseedu-credit-based-pricing / https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex / https://github.com/openai/codex/releases/tag/rust-v0.157.0
- v1.0 当時の公式: https://learn.chatgpt.com/docs/models / https://developers.openai.com/api/docs/pricing / https://learn.chatgpt.com/docs/config-file/config-reference
