---
feature: mvp-stats-primitives
status: active
承認: 済（2026-11-04・PO委任によるCodex主担当判断）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-stats-primitives
created: 2026-11-04
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 共通成績事実から27基本成績・画面・試合別/暦年CSVへ接続する

## 1. 目的・継承する判断

基線はdevelop `40ce2e312bc46435239f2a6d0ea0f1fb919a5de0`。初回MVPの打撃16・投手11項目を、T5の唯一の成績事実からT6の実DB集計、実API/画面、試合別・シーズン成績CSVへ接続する。投球数1項目の試作で本featureを完了しない。未回答/上流source不足の項目も全27の対応表に残し、該当成果だけ未完として追跡する。

既[計画候補8f67bbb2](https://github.com/masaki1025/pitchlog/blob/8f67bbb25f0f5aaad84706bd42e0afa63ab15152/docs/features/mvp-basic-stats-calculation/plan.md)の責任・27項目・版/原子性・十分統計量を再利用する。同候補の承認は3文書保全のみであり、未承認method-addendumの「TS正本→同一artifact/TS→SQL」は採用しない。現[ADR-003](../../adr/ADR-003-domain-calc-method.md) D-1/D-1-dで実装する。T5=(α)のPython/TS、T6=(β)③のSQL→Python typed receiver→生成formatterを、同じ宣言の派生物にする。D-14-mのT1/T2/座標量子化例外を成績へ広げない。

JST暦年と終了確定最新版だけの公式成績は既PO方針として維持する。40ceの要件に残る4/1年度の文言は、既採用方針の正式整合ゲートで追随し、期間の再裁定を求めない。未回答の**成績MVP-D02〜D05**は第7節のまま保持する。記録lock D02=A、CSV文書の「3表示区分は既決」という記述を、成績区分対応D02の回答へ流用しない。

今回の作業許可は本planと[research](research.md)のexact2だけ。rootが対象SHA/独立レビューを照合しPO委任で計画採用後、指定した実装ステップへ進める。コミット実施者と各ステップで止まる規律はAGENTS.mdに従う。rootは正式資産・共有式/producerの最終writerを直列管理する。

## 2. 唯一の正本・producer・読取集合

### 2.1 CSV G04-Aと式を共有する

[毎球CSV計画261b08b4](https://github.com/masaki1025/pitchlog/blob/261b08b438ef748960e7a8cd95611b5a893367ff/docs/features/ud2-csv-export/plan.md)・同supply-matrix G04-Aの契約を継承する。

- **共通primitiveの唯一の人手保守元**は `backend/domain/play-export.model.json`。投球対象、23計上flagの寄与、PA行、outs、各回score、0/NULL/未消化、論理順序/windowの式をここに一度だけ宣言する。座標等のCSV専用宣言との同file編集はrootが分担/統合を直列化し、CSV作者と同時に全fileを更新しない。
- 新 `backend/domain/stats.model.json` は共通primitive ID/型/hashを**参照**し、27項目の選択・共通十分統計量からの率/表示を一度だけ宣言する。共通count/score式をコピーしない。型付き参照の解決は生成時だけ。未知ID・型違い・循環・未宣言依存・hash不一致を拒否し、runtimeで別の手書きinterpreterを持たない。
- **共通事実producer/読取入口**は `backend/src/pitchlog/repositories/play_export_primitives.py::ReadPlayExportPrimitives`。生成SQL/同TX保存されたcanonical事実とsnapshot receiptを一元供給する。毎球CSV/T5/T6は同じ選択集合・fact版・式を消費し、別producerを作らない。T6専用readerはこのsource relationと生成式を同じDBで組み合わせるtyped adapterであり、試合ごとの結果をアプリで再合算しない。
- `exports/record_projection.py` とCSV serializer/ZIPは保存済み完成値の抽出・型検証・引用/JSON encodeだけ。statFlagsの再判定、Python/JSの全event count/sum/reduce、独自率/丸め/年導出を禁止する。保存T1 before/afterを画面状態として再計算しない。

D-1の生成器は現状骨格であり、設定追加だけで実計算を供給済みにしない。第4節の有限機能を実際に生成/実行し、宣言/生成物/製品呼出/3層検査を同じ対象追加に揃える。

### 2.2 canonical事実・版

真正な受理event/ledger/PlayRow/slotと結合したT1の**全23flag、実before/after、outEffect、参加者、責任、PA開始/完了参照、runner/scoreboard差分**を型付き入力にする。未知variant/不足を0・false・現在名簿へ補完しない。得点/打点/outsをboolから点数へ推測せず、T1が確定した有効数量を受け取る。二塁打/三塁打等の既規範の結果種別→十分統計量写像も共通宣言1か所へ置き、T1の野球判定を重ねない。盗塁は23flagだけでは足りず、正式な走者別企図/成否を入力にする。

候補factキーは `(tenant,game,source_version,source_event,player,metric)`。source_versionは正規の適用済event/slot版集合とcanonical projection版に結び、既D2/S8/V10/PlayRow.versionと名前だけで同一視しない。同D5再送は既eventを解決し再加算しない。訂正/取消/挿入は有効source集合から再投影し、旧版を論理失効させる。旧版への加算補正だけで確定成績を維持しない。

計算版は `computed_metric_keys`・source集合digest・計算モデルhash・完全性を持つ。期待source版を照合し、全factの同TX保存後だけ公開pointerを原子的に切り替える。途中故障/遅着した旧計算は公開しない。物理削除しない。出場区間/0球出場・PA未完了もtyped原事実として供給するが、未回答の登板/BFへ変換しない。

### 2.3 集合とscopeを分ける

| scope | 選択/実行 | 成功表示の条件 |
| --- | --- | --- |
| 共通S/毎球CSV | 同RR snapshotの同tenant/game、可視PlayRowと有効な受理source。hidden/trashed/retired/replaced/tombstoneを資源別に除外。適用済最新slot/行版を使用。世代をsource pairに保持し、current世代限定で過去の有効プレイを消さない | 進行中/中断中も対象。監査sidecarの全履歴集合と区別。G04-Aのreceiptと一致 |
| T5当日/断中 | 同じcanonical宣言のα生成コード。端末は正規版＋自分の未同期操作という別scopeを明示。サーバー当日取得は共通SをDB側で絞る | current/provisionalとsource版・鮮度を表示。確定版や他端末の未同期分と混ぜない。交代時点で対象選手を切替え、初球を待たない |
| 公式試合別/成績CSV | 明示的な終了確定原本と公開成績版が一致した、その試合の可視・有効最新版 | T2検知lockやgames.status='finished'単独で代用しない。再開中は公式対象外 |
| T6シーズン/成績CSV | 同tenant、公式試合別集合、JST暦年 `[start,end)`、同じ選手/区分/版条件で実表WHERE→GROUP BY | 率の平均を取らず十分統計量を合算。D02回答前は生の5区分キーを保持し、公式/練習/合算の写像を採用済みにしない |

G04-A列34は `event_kind='pitch'` を1投球としてtenant/game/実pitcherで分割し、source D2論理順＋source_event_idのCOUNT window。T1投球数flagとの不一致は供給不整合として拒否し、片方を無言で上書きしない。キーセット条件はwindow評価後、500境界で累計を再開しない。各回scoreは保存T1の有効scoreboard差分と到達状態からGROUP BY/windowし、未消化を0へ補完しない。両者をstatsモデルへ再定義しない。

断中のT5は、取得済み基準snapshotと自端末の有限な未同期操作に同じα生成処理を適用してpreviewを更新する。サーバー全履歴を取得してJS/Pythonで通算を作る経路は設けない。取消/訂正の再導出も正規source版と有効操作集合に束縛し、同期後に異なる版を混ぜない。

公式成績の一覧はDB keyset paging、件数は同じWHEREのDB COUNT。CSVは同snapshot/有効版集合を有限バッチでstreamし、率表示は生成formatterだけを通す。tenant/game/版/metric/player・期間/状態用の複合索引とquery planを実DBで確認する。

## 3. 影響する正本

| 正本 | 反映 |
| --- | --- |
| `docs/adr/ADR-003-domain-calc-method.md` | **反映なし**。D-1の既射程内で型付き有限参照/primitive/reducerを実行可能にする。表現不能が具体入力で判明した場合だけ、その対象の最小正式変更をrootへ返し、手書き式やD-2へ逃げない |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映**: 既PO採用のJST暦年整合。4/1年度の残存箇所・期間ラベル/bindingを同一ゲートで追随。新しい期間裁定ではない。D02〜05回答時も該当する最小節のみ正式化 |
| `docs/design/data-model.md` / `docs/design/sync-protocol.md` | **反映**: canonical事実/版/公開pointer、取消訂正/再開/再終了と既TX・読取snapshotの接合。現source_versionの実写像を確定して該当節だけ更新 |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**。既3層/core/7.7/段階実装を利用 |

本plan作成時は正本を編集しない。正本改訂は7.6決定表による既ゲート、正式asset受理はrootが最終差分から導出する。暦年正式追随をpure schema/独立期待/生成器準備の開始条件へ前倒しせず、該当する製品提供の前に閉じる。

## 4. 編集範囲とD-1の有限機能

### 4.1 生成器/契約・実生成code

既存exact7: `backend/domain/model.schema.json`、`backend/src/pitchlog/domaingen/core.py`、`backend/src/pitchlog/domaingen/pregen_checks.py`、`backend/src/pitchlog/domaingen/backends/python.py`、`backend/src/pitchlog/domaingen/backends/typescript.py`、`backend/src/pitchlog/domaingen/backends/sql.py`、`backend/src/pitchlog/domaingen/formatter.py`。

追加機能は型付き共通primitive参照・literal/ref/比較/相補guard→0/1・整数加算・typed item/accumulator・有限reducer・DB実表列binding/WHERE/GROUP BY・COUNT/SUM windowに閉じる。後続の率は同じ宣言の整数分子/分母・0分母null・half-up・scale/先頭0/母数・投球回混合分数を生成する。暦年境界は同じモデルの型付き単一正規化に定め、自由な日時文字列演算を導入しない。JST年からcanonical境界を作る既D-1表現の不足が具体化した場合は、その有限primitiveだけをrootへ返す。整数範囲・最大件数・nullable・参照元/依存の未知/循環を生成前拒否し、JSON整数/TS内部/SQL numericをlosslessに照合する。

人手正本: `backend/domain/play-export.model.json`、`backend/domain/stats.model.json`。前者の共通式を後者はID/hash参照だけにする。生成入力allowlistに両modelと実依存だけを閉列挙し、期待ベクタ/property catalogを入力にしない。

新規契約: `contracts/exports/play_primitives_v1.json`（CSV G04-Aと共同）、`contracts/stats/primitive_facts_v1.d.ts`、`contracts/stats/primitive_facts_schema_v1.json`、`contracts/stats/primitive_facts_cases_v1.json`、`contracts/stats/basic_stats_v1.d.ts`、`contracts/stats/basic_stats_schema_v1.json`、`contracts/stats/basic_stats_cases_v1.json`。source/版/選択集合・全23flag・27項目/state/display/denominatorを閉型化。契約/独立期待値/検査基盤を対象計算追加前に受理するが、T1全操作/実HTTP/画面の先行完成を条件に足さない。

実生成先: `backend/src/pitchlog/exports/generated/play_primitives.sql`、`backend/src/pitchlog/stats/generated/facts.py`、`backend/src/pitchlog/stats/generated/stats.sql`、`backend/src/pitchlog/stats/generated/receiver.py`、`backend/src/pitchlog/stats/generated/formatter.py`、`frontend/src/lib/generated/statsPrimitives.ts`、`frontend/src/lib/generated/statsFormatter.ts`。全て派生物で、人手で式を書かない。`backend/src/pitchlog/stats/facts.py` と `frontend/src/lib/generated/wrappers/statsPrimitives.ts` は検証/呼出だけ。現在のcontext echo/固定SUMの骨格を実計算完成としない。

登録/検査: `backend/domain/stats-manifest.json`、`backend/domain/stats-property-catalog.json`、`backend/domain/stats-property-catalog.schema.json`、`backend/domain/manifest.json`、`backend/domain/display-binding.json`、既BE/FE entrypoint/display collector・runnerのこのtarget登録だけ。既 `tests/domain/gen/test_core.py`、`test_pregen.py`、`test_backends.py`、`test_formatter.py` と、新 `backend/tests/stats/test_primitive_facts.py`、`backend/tests/stats/test_basic_stats.py`、`frontend/src/lib/generated/wrappers/statsPrimitives.spec.ts` を対象にする。唯一式/生成元hash/直接target・完成表示・全比較面と非等価変異を検証する。

### 4.2 保存/DB/認可

新規 `backend/src/pitchlog/repositories/play_export_primitives.py`、`backend/src/pitchlog/repositories/stats.py`、`backend/src/pitchlog/db/game_state/stats.py`、`backend/migrations/versions/stats_fact_versions.py`（具体filename候補、revisionは実施時に衝突なく採番）。`backend/src/pitchlog/db/all_models.py`へ登録。既 `backend/src/pitchlog/repositories/transaction.py`、`backend/src/pitchlog/sync/first_ball_projection.py`、`backend/src/pitchlog/sync/ordinary_pitch_projection.py`、必要な既 `backend/src/pitchlog/sync/ordinary_pitch_execution.py` の型付きframe/既同TXだけへ接合する。terminal/v3等の統合済み派生sourceは、その既frameの実版を照合して同じproducerへ技術bindingし、別計算を複製しない。

repositoryの既 `operation_registry.py`/`tokens.py`/生成 `repository_contract.py`、`contracts/tenant_boundary/repository-contract.json`/`runtime-authz-contract.json`、`contracts/authz/product/capability-catalog.json`/`ddl-elements.json`/`function-bodies/manifest.json` と、該当する有限function/ACL/RLSをrootが同期する。自由SQL/直接DBAPI/全app権限を増やさない。新SQL個別filenameは正式署名を契約で固定後にrootがexact集合へ追記する。事前に任意の関数名を許可する意味ではない。

対応試験 `backend/tests/db/test_stats_storage.py`、`backend/tests/db/test_stats_queries.py`、`backend/tests/db/test_play_export_primitives.py`。既全fixture/SQL拒否/認可を保持。core新pathは既境界での捕捉を確認し、必要な場合だけ先行宣言・別登録を行う。

### 4.3 API/画面・2種の成績CSV

新規 `backend/src/pitchlog/api/schemas/stats.py`、`backend/src/pitchlog/api/routers/stats.py`、`frontend/src/api/stats.ts`、`frontend/src/components/game/GameStats.vue`、`frontend/src/screens/SeasonStats.vue`、`backend/src/pitchlog/exports/stats.py`。既 `backend/src/pitchlog/api/app.py`/route・authz catalog、`frontend/src/router.ts`/`frontend/src/router.spec.ts`、実 `frontend/src/screens/GameScreenEntryRecordHost.vue`、`frontend/src/api/client.ts` の既認証/tenant stale guardに接続する。候補endpointは試合成績 `GET /games/{game_id}/stats`、暦年成績 `GET /stats/seasons/{year}`、試合別 `GET /games/{game_id}/exports/stats.zip`、暦年 `GET /stats/seasons/{year}/exports/stats.zip`。原区分キー集合/選手/左右条件はtyped入力、D02未回答の名前付き写像を仮登録しない。

両ZIPは打撃/投手CSVと版/フィルター/行数/hash manifestを持ち、同一供給snapshotから作る。既 `backend/src/pitchlog/exports/csv.py::stream_csv` とCSV作者の完成ZIP/hash・切断/cleanup部品を利用する。CSVに統計式を置かない。`backend/tests/test_stats_api.py`、`backend/tests/test_stats_export.py`、各component/API Vitest、`backend/tests/db/test_stats_screen_e2e.py` を追加する。生HTMLを挿入せず、実tenant選択変更/古い応答・未送信/未取得/ゼロを分ける。

後続ステップの追加pathは不可分理由と最小exact差分をrootへ返す。将来の全system改造を包括許可しない。実装を分担する際は各ステップのroot/作者/CSV作者のpath所有を固定してから書き込む。

## 5. 全27項目・補助事実の有限対応表

全行の完成値は同じcanonical事実・計算モデル版から得る。T5は計上/帰属を二重判定せず事実/当日PA行を形成し、T6はDBで十分統計量を集め同じmetric宣言をSQL/formatterへ生成する。各行は実API/画面・試合CSV/season CSVの全経路で比較する。

| ID | 指標 | T5の正式source/十分統計量 | T6/生成表示・留保 | 主ステップ |
| --- | --- | --- | --- | --- |
| B01 | 打席 | 完了PA参照/打席flag、before打者。未完PA原記録は別保持 | 完了PAの整数count | 1–3 |
| B02 | 打数 | PA行の打数算入、四球/死球/犠打/犠飛/妨害の既定義 | 同一PA行のcount。式を別に再判定しない | 1–3 |
| B03 | 安打 | 安打flagとPA行 | count | 1–3 |
| B04 | 二塁打 | 正式安打種別=二塁打。最終到達塁から推測しない | count | 1–3 |
| B05 | 三塁打 | 正式安打種別=三塁打 | count | 1–3 |
| B06 | 本塁打 | 本塁打flag/正式安打種別 | count | 1–3 |
| B07 | 得点 | 走者ごとの有効生還/本人帰属、OUT3処理後の数量 | sum、有効性をT6で再判定しない | 2–3 |
| B08 | 打点 | 正式RBI算入走者の数量、before打者 | sum、boolを1点と決めつけない | 2–3 |
| B09 | 四球 | 四球flag/PA行（申告敬遠を含む） | count | 1–3 |
| B10 | 死球 | 死球flag/PA行 | count、BBと混同しない | 1–3 |
| B11 | 三振 | 三振flag/PA行、振逃げでも打者outと独立 | count | 1–3 |
| B12 | 盗塁 | 正式な走者別盗塁成功、本人/企図・成否 | count。23flagだけで推測しない | 2–3 |
| B13 | 打率 | 安打/打数 | 合算分子÷合算分母、0分母null、3桁/先頭0なし/打数併記 | 3 |
| B14 | 出塁率 | 安打/BB/HBP/打数/犠飛 | (H+BB+HBP)/(AB+BB+HBP+SF)、3桁/母数併記 | 3 |
| B15 | 長打率 | 正式安打種別由来の塁打/打数 | 合算TB/AB、3桁/母数併記 | 3 |
| B16 | OPS | 出塁率/長打率の元分子分母 | **D05待ち**。丸め前/表示値加算を仮採用しない | 3–5 |
| P01 | 登板 | 出場区間/投手交代・再登板/0球を原記録供給 | **D03待ち**。区間数や1球以上を仮countしない | 2–5 |
| P02 | 投球回 | 正式outEffect/走者別out数量/投手帰属 | outs合算→混合分数。第3out後outs resetの差を使わない | 1–3 |
| P03 | 打者数 | PA開始/完了と継承カウント/交代原記録 | **D04待ち**。A-2四球責任をBFへ流用しない | 2–5 |
| P04 | 被安打 | 正式被安打flag/投手帰属 | count、B03との一致検査は二重加算しない | 1–3 |
| P05 | 被本塁打 | 正式被本塁打flag/投手帰属 | count | 1–3 |
| P06 | 与四球 | 正式四球の責任投手（既A-2継承カウント規則） | count。現在投手へ一律転記しない | 1–3 |
| P07 | 与死球 | 正式与死球flag/投手帰属 | count | 1–3 |
| P08 | 奪三振 | 正式奪三振flag/投手帰属 | count、P02のoutと独立 | 1–3 |
| P09 | 失点 | 有効生還走者の責任投手、継承/入替え含む | sum。得点時投手へ付け替えない | 2–3 |
| P10 | WHIP | 被安打/与四球/outs | (H+BB)×3/outs。HBP除外、0分母null、2桁/投球回併記 | 3 |
| P11 | 球数 | G04-Aの投球判定/実before投手/論理順序 | 同じCOUNT/window、非投球を除外 | 1–3 |

PAはFR-022の全7列（番号・回/表裏・結果表示名・打数算入・安打種別・打点・出塁別）を共通宣言で形成する。管理者可変語彙の表示名はsnapshot/ID入力で解決し、固定表へ焼き込まない。補助十分統計量は犠打・犠飛・妨害出塁・塁打・outs・走者別有効得点/RBI・出場区間・PA状態に閉じ、27以外の指標を勝手に完成範囲へ足さない。自責点/ERA/FIP/詳細分析/カルテ/PDF/過去移行は旧計画の別責務を保持する。

## 6. 実装ステップ（全5ステップ）

| # | 実装範囲 | 合格条件 |
| --- | --- | --- |
| 1 | 共通D-1実計算生成と既確定count primitive群/ReadPlayExportPrimitives | G04-Aと共同の型/source/S/版・全23flag/実beforeafter・独立期待を先行受理。共通モデル参照を一度だけ解決し、実Python/TS/実表SQL/typed受け口/整数formatterを生成。球数に加えPA/安打/BB/HBP/K/HR/outs等、正式sourceが閉じた群を同じengineで検証。DB WHERE/GROUP BY/windowと500前後・世代/非投球/取消の原典一致を実測。unknown source/式は拒否、T1全操作完成を開始前提にしない |
| 2 | T5 canonical事実・最新版冪等保存と出場/PA・取消訂正反映 | 既同TXへ接合し、同D5/同版再送1回、旧計算遅着拒否、公開pointer全原子性・各段故障全取消を実PG確認。PA7列・有効走者/RBI/盗塁/責任・出場原記録を全対応表へ供給。再開除外/訂正新版/再終了1版・跨世代有効source保持。D03/D04未回答は値を偽確定せず状態を残す |
| 3 | T6実表集計・全既確定率/表示生成・暦年/区分条件 | 第5節の定義済行と補助統計を生成SQL/同じモデルの式で完成。実表WHERE/GROUP BY・件数/window/索引/EXPLAIN、空/未計算/不定/0、巨大整数/分子分母/丸め/母数を独立比較。暦年の既方針正式整合を製品提供前に完了。D02〜05未回答は依存項目だけdecision_pending、無関係項目は継続 |
| 4 | 実APIと当日/暦年画面・断中/交代/閲覧更新 | 正式tenant-bound route/repository/認可、paging/鮮度・版DTO、実画面→HTTP→DBの当日/暦年成績を接続。交代直後/初登場/次打者、断中当日生成/season最終取得注記/未取得、別tenant/stale/取消/再取得を検証。未回答/未供給を0や古い値で最新表示しない |
| 5 | 試合別/season成績CSVと実結合受入 | 両CSV/画面が同snapshot/モデル/対象集合/全27metricの値・表示・状態に一致。実DB→実API→実画面DL、CSV bytes/ZIP manifest/hash/引用/無害化・大量/ページ/切断/容量/取消・認可撤回を検証。D02〜05を正式回答で閉じ、全27の実供給と取消訂正/再開/再終了を完了してからfeature完成。未回答中に独立部品/他項目を先行するが、27完成とは記録しない |

**具体的な最初の実装**はステップ1内で、(a)S/23flag/PA/帰属の閉型と独立期待、(b)共通モデル参照と整数/typed reducerの生成前検査、(c)実0/1/count/addコードとDB COUNT/SUM/window、(d)同一producerの実caller/3層まで。投球数だけのsample実装を合格条件に縮めない。最初にT5/T6全方式/全上流HTTP完成を要求せず、対象群の契約→その実計算へ操作単位で進む。rootのステップ指示を超えて次へ進まない。

## 7. 未回答4件・状態の扱い

根拠はlead判断票の固定 `725c6ba2085246768ef260fdc8effab0fd06abe3` の `docs/features/mvp-integration-lead/decision-sheet.md`（更新2026-10-30）。現root引継ぎも未回答4件を維持する。

| 成績ID | 未決の意味 | 回答前にできること/止める値 |
| --- | --- | --- |
| D02 | 5試合区分→公式/練習/合算の写像 | 原キー/typed選択集合とDB絞込を実装。名称から写像を決めず、名前付き集計はdecision_pending |
| D03 | 登板の単位・0球/再登板 | 出場区間/交代/投球原記録を供給。登板数の公式値はdecision_pending |
| D04 | 継承カウント/PA完了と打者数の投手帰属 | PA原記録/正式四球責任を別に保持。BFのみdecision_pending |
| D05 | OPSの式/合成/0分母/丸め順/表示 | OBP/SLGの既定義と構造値を実装。OPSのみdecision_pending |

metric state候補はavailable/decision_pending/source_unavailable/failed。集合集計の空はdataなしとして0/率nullの規範に従い、取得不能と区別する。生の未供給を0にしない。部分供給DTOは各stateとreason/版を明示し、全27供給済みという成功表示にしない。新たな意味空白が判明した場合だけ具体入力・根拠・未決結果をrootへ返す。

## 8. 検証・DoD

- 単一性: play-export/statsの共通式は1定義。生成物再現/hash・依存allowlist、未知/循環/余剰演算・動的SQL/別関数・全件アプリ集計を拒否。独立期待/規範を生成入力へ含めない。全23flag・完成表示/分母/状態・source版を比較する。
- 保存/集計: pytest/Vitest、直接生成targetの同値・性質・非等価変異生存0。DBでtenant/可視性/版/終了/JST年境界・出場0球/未完PA/継承責任・0点/未消化・第三out reset・訂正取消/再開・再送・遅着・故障・読取競合を検証する。
- 性能/認可: 15万play/同時3試合・閲覧10端末の要件を本経路で確認。件数/一覧/CSVの全件list化をせずDB COUNT/keyset/window/索引を使う。元deviceの記録権をviewerの読取条件に足さない。RLS/epoch/fence/既拒否順を保持する。
- 出力: 同じ供給版を画面/試合CSV/season CSVへ通す。writer数式無害化/BOM/引用/日本語/NULL、stale/tenant変更/切断/容量/取消で成功偽装0。実機未検証とブラウザ模擬を区別し、信頼済みHTTPS/実機は未実施なら残す。
- 品質: 対象pytest/Vitest、Ruff/ty/ESLint/vue-tsc/build、docs/plan/core/必要7.7/必須CI、最終HEADの通常非作者reviewと通常PR統合。数学/fixture/ZIPだけの成功を実保存/画面へ読み替えず、P6blind/全BOOT/全MVPの既未了も維持する。

完了は5ステップ・全27項目・2成績CSV・実接合の全条件が満たされた時だけ。rootの独立計画採否後はステップ1の対象群を開始でき、未回答4件を理由に非依存の実装を一律停止しない。


## 2026-11-04 主担当採用と最初のステップ指示

判断者Codex主担当/root。対象は計画SHA256 `4a3f8a1d164f8551e77e0e2ff45d27901b3e2ccf9946ced363ce85a115fbd35c`・research `5a4546b6f21e3e3bf9a800debce9cc2cc24bb2b45313ad75be4bd226fd827dca`、非作者REPORT `5bd400fd3c7041dd1efa5964e7dbe33f47dc5ec5a80a9ed790b5fbd15535badf` のP0/P1未解消0を照合し、既MVPのPO委任により計画を採用する。本人の逐行確認・署名・旧method方式承認の代記ではない。

ステップ1(a)の閉入力/出力型・有効集合/版/source境界・独立規範期待・3層比較契約候補から開始する。全23flagを入力として保持しつつPA/安打/BB/HBP/K/HR/outs/投球数等の正式sourceが閉じた群を同engineへ写す。未回答D02〜05や不足観測を仮採用しない。共通モデル/本計画の候補contract・同feature evidenceは担当を一本化し、共有registry・同期/DB・生成器source・正式contractsへの採用は非作者確認とrootの次の指示後。独立期待を製品出力から生成しない。対象群の契約成立後は直ちに1(b)の実生成コードへ進み、全27/MVP全体の開始待ちにしない。


## ステップ2：実native SQL/最小権限producerへの操作単位接合（2026-11-05、PO委任Codex /root判断）

反映1cache stats-native-functions-reflection1-20261105/ packet e053264b…と非作者de9d8cb3…を候補採用する。既4SQL本体は不変、必要通常SELECT12+xmin4/tenant policy3/logicalID正準化を確認済み。純parse/最小xmin PGと実製品4関数の成功は別であり、まだ実成績提供ではない。今は実native関数とcanonical publisherのsource化を先行し、shared installer/registry/同frame opaque proof/commit前flush/実native PGはroot直列で続ける。既Port/HTTP/全操作供給の完成を本単位の追加開始条件にしない。

専有writer batted_prefix_connectionへ新backend/src/pitchlog/authz/stats_primitive_sql.py・stats_primitive_product.py・backend/tests/test_stats_primitive_product.pyのexact3を許可。SQL生成は既唯一play-exportモデルと生成selector/count/page/totalsを参照し、別S/別T5算式を増やさない。候補build.py/publisher.pyを製品pathへ移し、cache絶対path/固定WT/relations候補への実行依存をなくす。SQL4が反映1全byteへ再生成一致すること、既54col/7policy値保持と追加通常12+xmin4/policy3/計70col10policy4func84bodyの閉集合を検証する。未知モデル/列/型/参照/権限を拒否、appへtable直接grantを追加しない。stats_api schemaの正式所有者/USAGE/再適用guardも既producer規約へ合わせて候補として提供し、承認済4SQLを暗黙に変更しない。新SQL/PL/nullable PA envelope/nonce+consumed sameframe/TX/canonical S/CAS/RRRO snapshot境界を保持する。

新3以外（既生成器/生成物/正式contracts/共有registry/transaction/sync/既migration/他WT/台帳/Git refs）を作者は編集しない。既export SQL/実モデル/54列表構造をsourceから参照し、必要受け口が不足ならcacheへexact差分候補を返す。型/ruff/pure有限検証・再現byte比較を行い、PG/HTTP/署名/正式7.7はroot後続として明示する。独立レビュー後rootが採否し、必要共有pathを直列実装する。未決4意味判断とMVP全27/両CSV・終了再開等の完成条件は維持する。


### 同TX writer前値の有限供給（2026-11-05、PO委任Codex /root判断）

source3/4SQLを非作者74f4212f…で採用し7ba56ed9へ保存。read-only調査e0618c87…により、実writerのREV/Sを既RRRO Openへ流用せず取得するprivate固定関数1件が不足と確認した。新authz/stats_primitive_write_state.pyとtests/test_stats_primitive_write_state.pyのexact2をpr191_residual_independentへ許可。stats_api.read_primitive_writer_state(attempt_id uuid,phase_id uuid,source_event_id uuid,model_sha256 text,binding_nonce bytea)→(revision bigint,source_set_sha256 text)をcanonical producer候補にし、既Saveと同じsession_user/current_user/tenantGUC・実binding/currentXID・実consumed admission/元event/game/nonceを全照合する。current_openの有効current行だけFOR UPDATEで読み、真に不在のときだけ0/NULLを返す。終了/失効/複数/未知モデル/別TX/偽nonce/別tenant/未consumeの事実を欠如や0へ読み替えない。JSON/UUID/nonce単独は資格でなく、rootの実state-key/TX/同frame/全evalと一回消費proofが別に必要。

既SQL4の署名/本文と70列10policy84bodyは不変、新関数1/必要最小metadata/ownerACLfooterだけを別追加し、新capabilityやapp直接tablegrantを足さない。既モデル/実SQL/旧固定guardを参照し計算を複製しない。作者は新2だけ、source3/共有registry/transaction/sync/正式資産/refs/DB非編集。構文/型/限界/構造変異を検証し、rootが独立確認後に正式producer・5identity限定codec/registryと単一flushへ直列接合する。純試験を実PGの資格/CAS/原子性成立へ読み替えない。


### 成績5固定関数の値codec（2026-11-05、PO委任Codex /root判断）

新repositories/stats_function_codec.pyとtests/test_stats_function_codec.pyのexact2をbatted_prefix_connectionへ許可する。既SQL4＋writer preflight1のidentityだけに閉じ、実宣言の引数順/型/NULL許可/行形から実bind/result値を厳格に形成する。tenant先頭を注入せずSQL内tenantGUCを使う5関数だけの固定Selectを供給し、caller指定SQL/identity/arity/tenant-injection flagや一般registryの型緩和を導入しない。Saveのprivate nonce、Page/Totalsのprivate transaction_idはrootが真正proof/receiptから渡す値であり、値codecが資格を発行したりscalar/UUID/JSON/trueを認可へ変換したりしない。公開値tokenのrun_function直実行を許す登録はrootのprivate資格gate前に行わない。

UUID/bytes32/modelhash/厳密int範囲・page上限・nullable S/cursorの全か無か/JSONB exact評価envelope/NUMERICの有限整数DecimalとNULLをfield単位に閉定義する。BigIntegerをfloatへ近似せず、計算/丸め/集計は既生成式へ任せ、codecに別統計算式を作らない。適用対象は新5だけで既Fn token/SQL/行validator/NULL拒否は不変。閉Query/typed params/厳密行変換の値部品と追加すべき共有callsiteの最小cache差分を提示する。source2以外のproducer/SQL/共有registry/transaction/sync/reader/正式assets/refs/PGは作者非編集。正常5/型混同/余剰欠落/未知identity/NaN fractional Decimal/BOOL-as-int/不完全cursor/偽hash/不適切NULL・JSON余剰を有限pureで検査し、別非作者確認後rootが実資格gate/登録/単一flushへ接ぐ。純transport成功は実認可/保存/読取の成立ではない。


## root隔離接続候補での実接合（2026-11-05、PO委任Codex /root判断）

feature/mvp-stats-native-connectionはbatted固定9d0a3dc1へ採用stats固定bc5b32b3を通常mergeした00d8811d起点。元2枝/WTと正式developを変更せず、実製品が同時に動く候補だけを作る。後段PRは依存元を維持し、このmergeだけを正式統合/成績提供としない。rootが同候補のshared writerを専有する。

最初に隔離未公開stats migration0040を0041_stats_fact_versionsへ改称しdown_revisionを0040_batted_vocabulary_indexへ接合する。本文/54列/PK/FK/ForceRLS/default-deny/物理削除禁止は全AST保持し、tests/db/test_stats_storage.pyの対象pathだけ追随する。tests/db/test_stats_primitive_read_scope.pyの既ty違反は実driver例外型を明示確認してSQLSTATE25006拒否を維持する。新列/データ修復/共有DB適用なし。新単一alembic head/DDL不変と既downgrade拒否をpure確認し、実migrationはroot owned PGで後段検証する。

続くroot接合はauthz/first_ball_product.py・product_catalog.py（新stats schema/私有3表/4+1関数/最小列policy/sourcebody/同じ再適用guard）、repositories/function_operations.py・operation_registry.py・transaction.py・play_export_primitives.py・stats.py、sync/prefix_path.py・first_ball_execution.py・ordinary_pitch_execution.py・新stats_native_hook.py、および対応新tests/test_stats_native_connection.pyの範囲に限定する。原実Executionのlive state/実state-key/同TX/source・元event原本/実規則/既nonce/consumed・projectedを全部照合するopaque qualifierと一回消費を実装し、after_d1_intents後/return前だけで唯一prepare_native_evaluation→実前値→Saveを実行する。既consumeを再呼出しせずDI2再掲はflushせず、失敗はnativeとstats全体rollback。RRRO readは既真正marker/同handle/実発行receipt・cursor identityを両入口で強制し、snapshot文字列だけに資格を与えない。5identity値codec以外の一般SQL/型/NULL/tenant先頭契約は不変。

正式資産はrootだけが同canonical producer/modelからcontracts/db/schema-manifest.json・contracts/authz/product/ddl-elements.json/function-bodies/manifestと新body・contracts/tenant_boundary/repository-contract.json/runtime-authz-contract.json、公式生成moduleを一括候補化する。旧全宣言値/権限を保持し必要統合後に単一受理前後とOracle/provenanceを独立確認する。body/生成module手編集や先取り再封印は不可。5th preflight/codec作者の新2+2は停止・独立採否・commit後に元stats枝から通常mergeし、同名pathを並行編集しない。

受入は隔離同候補のfresh画面/実API新規作成→start→native球→同TXstats原本/facts/series→新RRRO Open/Page/Totals、T4後/Save後/commit故障全取消、nonce/他tenant/別receipt・同snapshot別handle/再送二重加算/過去nativeのみの不足源閉拒否を検証する。現current_open供給だけで終了確定試合・全27/season/CSV/MVP完成としない。正式developへの順次統合・実機/運用/全受入は別条件を保持する。


### canonical producer共有pathの単独移管（2026-11-05、PO委任Codex /root判断）

接続WT rootの共有接合を滞らせないため、authz/first_ball_product.py・product_catalog.py・stats_primitive_product.py・必要時product_table_access.py、新authz/function_result_type.py・新tests/test_stats_native_product_connection.pyをpr191_residual_independentの単独writerへ移管する。rootは完了通知まで同pathを書かず、registry/transaction/sync/read資格と正式資産writerを専有する。既source3/SQL4と採用済preflight1から5関数・stats_api・私有3表/最小ACL/policy/RLS/bodyをcanonical集合へ接合し、未作成段のpre-rule配置を正しく保留する。新source値/SQL以外の旧全宣言/旧全body/既関数再適用guardを保持し、重複する既column宣言は同値なら旧body byteを残す。未知衝突/owner違い/余剰bodyは拒否。新schemaは既ownerのみ、CREATEをapp/FnOwnerへ与えず、runtime function-detailsの実queryへstats_apiを追加する。

stats_product→firstball._pg_result_typeの循環importは、既TABLE表記整形を新leafへ一度だけ移し、firstballの旧名は同じ結果の互換委譲、stats_productはleafを参照して両import順で起動できるようにする。単一のメタデータ整形で数学/SQL/期待値は不変。新xmin4の宣言照合が必要ならstatsの固定4table/column/ownerだけに閉じ、一般の未知列/role許可は広げない。source canonical段階はprospective資産をcacheに描画して局所対向を検証し、正式JSON/bodymanifest/生成Pythonの手編集や先取り再封印はしない。

作者は上記6pathだけ、他core/同期/registry/新codec/正式assets/refs/DB非編集。新5/3table/schemaの閉集合・old全値/guard保持・正規import両順・破壊対向/未知拒否をpure/lint/typeで確認し、raw4SQL/publisher84の値再現とformal供給不足を明記する。未適用は成功とせず、独立確認後rootがcanonical publisherで正式資産を一括候補化・実PG適用する。

### root実行時SQL生成の単一路維持（2026-11-05、PO委任Codex /root判断）

canonical producerの実接合で、既generate_primitive_bundleが実行時にPython/TS整形まで起動し、backendに開発用Prettierを要求する問題を確認した。rootはdomaingen/core.pyへ既schema・閉集合・参照hash/type/順序検証と同一sql_backendを共有する固定SQL二対象専用APIを追加する。既七対象API/生成byte/全拒否条件を保持し、SQL専用時だけ他言語生成・外部formatterを起動しない。authz/stats_primitive_sql.pyは同APIを呼び、既model/manifest/artifact/hash検証を保持する。backend/domain/stats-manifest.jsonの生成入力hashは既公式生成手順で追随し、生成物本文が変わらないことを検証する。backend/tests/test_stats_sql_generation_runtime.pyでformatter/他言語実行禁止・二SQL全byte・不正model/参照拒否を対向検査する。独立レビュー前に成立扱いにしない。併せてbackend/tests/test_stats_primitive_product.pyの隔離migration参照0040→0041だけを追随する。野球の意味・SQL式・54列・認可・正式資産の採用は変更しない。

### canonical schema反映1（2026-11-05、PO委任Codex /root判断）

非作者初回REPORT SHA11190154987079259d50c1d1e4aa5ff9414b5d3f606b4c1a5f2e86d392aa2345のP1を受け、同移管5source内でstats_api schema宣言1に対応するbody1を補う。既recording_vocab schemaと同型の存在/owner確認・異owner拒否、未作成時pitchlog_owner所有CREATE、PUBLIC全権限とapp/FnOwnerCREATEのREVOKE・app/FnOwnerUSAGEだけを描画し、canonical body lookup/既installerへ接合する。旧4SQL/84body/旧323/29guardは全byte保持し、新body総89。純構文・owner/CREATE等の宣言変異拒否を検査し、作者反映後に非作者再レビューする。実PG成功は別のroot後段検証まで留保する。

### native資格の分担移管（2026-11-05、PO委任Codex /root判断）

実frame源はsync/first_ball_execution.py・ordinary_pitch_execution.pyのgetter/ready時実identity保持/既finally失効、新sync/stats_native_hook.py・tests/test_stats_native_connection.pyをpr191_residual_independentへ限定移管する。消費後に消える実frameを捏造せず、ready時の実bridge/frame/payload参照と既completed/projected/consumed状態・同TX実OperationEventReadの全原本を照合して一回資格を発行する。既T1/consumeを再実行せず、T5準備/保存はroot後段。

読取資格はrepositories/play_export_primitives.py・stats.py、新tests/test_stats_native_read_receipts.pyをpr192_harness_values_independentへ限定移管する。既真正RRRO markerを維持し、Open実結果のreceipt/同reader・handle・state-key・実発行cursorをidentityで束縛する。実Open/Page/Totals呼出し中だけのprivate一回資格getterをroot dispatcherへ供給し、Page/Totals transaction_idは本物receiptからのみ取得する。自由な値token/同文字列snapshot/constructor clone/別handle/失効/直接実行では資格を発行しない。共有transaction/registry/正式assets/DBはroot専有、作者は3pathだけを編集し独立レビュー前に接続成立とはしない。

rootのtransaction.py接合は、まず既真正RRRO gateの直後でOpen/Page/Totals実型3だけをprivate一回資格へ渡し、固定codec factoryを選んで同Sessionへ実行する。Page/Totalsのsnapshotはprivate発行receiptからのみ注入し、上限超過行/型不一致をclosed decoderで拒否する。通常の固定関数登録/型/tenant注入/NULL条件は変更しない。新tests/test_stats_native_read_dispatch.pyで直接実行拒否・未資格時SQL0・三固定factory/同Session/上限/別token/失効を検査する。正式3操作登録・manifest/受理と実PGは後段まで未提供を維持する。

同TX保存のxmin依存検査（root、2026-11-05 PO委任判断）: 既schema manifestは利用者定義列のみであり、採用SQLが同TX照合に読むPostgreSQL system列xmin4件を誤って不存在と判定する。scripts/check_authz_catalog.pyの依存列検査は、既canonical producerの全field一致を通したstats用のpublic.operation_events/play_rows/idempotency_ledger・sync_fence.ordinary_pitch_checkpointsのSELECT xmin4件だけを有限例外として扱う。利用者定義の架空xminをmanifestへ追加せず、未知table/schema/列・owner/privilege/grant_option・canonical識別子の不一致は拒否する。新tests/test_stats_native_dependency_columns.pyへ正常4と変異対向を付け、独立レビューまで正式採用しない。旧全依存列検査/認可対象/SQL本文を維持する。

rootハーネス環境の必要依存も有限追随する。新canonical sourceは既backend実行時依存jsonschema==4.26.0を使って共通modelの全検証を行うため、root単独venvに同版が無く初回9検査が環境失敗した。pyproject.tomlのdevとuv.lockへ既backend同版を公式uvで追加し、root単独環境でも同検証を実行する。backend依存/生成検証を削除したり、失敗をskipして回避しない。

同TX flushの新単位（2026-11-05、PO委任Codex /root判断）: 新sync/stats_native_flush.py・tests/test_stats_native_flush.pyだけをpr191_residual_independentへ移管する。入口は実handle/writer/event/projectedから内部で真正source receiptを発行・一回消費し、private値を再投入する入口を作らない。同Sessionの固定preflight5引数で実REV/Sを取得し、一回だけ既prepare_native_evaluationを呼び、既実規則hashをenvelopeへ足して固定Save8引数で保存する。同writer/runtime/lifetimeの前後照合・上限+1/閉decoder・source/modelの戻り照合を保ち、Saveの新Sを前値Sと誤比較せず、実CASは前値全値へ束縛する。例外は外TXへ伝播し自前commit/rollback・認可省略・仮成功は不可。public値tokenの直接実行は未登録拒否のまま。rootがprefixの既after_d1_intents後だけへ接ぎ、正式5操作追跡/資産/資格/owned PGの全原子性を後段で成立させるまで提供済みとしない。

固定5操作の正式source登録（2026-11-05、PO委任Codex /root判断）: repositories/operation_registry.py・function_operations.py・transaction.py・play_export_primitives.py（import循環の最小解消だけ）、新repositories/stats_native_operations.py・tests/test_stats_native_function_registration.pyをpr191_residual_independentへ限定移管する。新5identity/cap/token/固定SQL/arity/行型をcanonical codecから束縛した閉宣言として既登録へ追加し、既全登録/文/型/tenant注入/NULL拒否を保持する。caller指定flagで一般SQL/JSON/nullableを開かない。実RRRO/private一回資格を通るread3と、内部真正sourceからだけ実行するflushのprivate2siteへ登録を追跡可能にする。public値Save/WriterState tokenを直接run/run_function/prepareへ渡してもSQL0で拒否する。read classのimport循環解消は同runtime実型を遅延参照するだけで、既receipt/cursor/真正scope条件を弱めない。rootは完了まで同6pathを書かず、共有正式資産のwriterを維持する。独立レビュー後にrootが5操作契約/資産を公式deriveし、prefix単一callsiteとowned PGへ接合する。

登録後のroot接合追随（2026-11-05、PO委任Codex /root判断）: 独立afc40ebcのflushとf8f48249の固定5登録を結び、sync/stats_native_flush.pyの2固定factory直後へrequire_private_writer_callによる実registry/固定SQL/全型・引数集合の照合を加える。真正source/一回消費/同scope前後照合はそのまま必須。既backend/tests/test_stats_native_flush.pyへ登録欠落/置換のSQL0またはSave前拒否を追加し、既2test（test_function_operations_boundary.py/test_sync_apply_function_registration.py）の旧全22/既12objectとbatted既index9を保持した末尾5の閉期待だけを追随する。旧counterを新出力へ無条件置換せず、作者cache旧2patchを非作者へ確認し、他失敗を成功扱いにしない。

private3表の分類・露出事実追随（2026-11-05、PO委任Codex /root判断）: contracts/authz/product/table-classification.json・exposure-facts.json、backend/src/pitchlog/authz/classification.py、scripts/check_authz_catalog.py、backend/tests/test_authz_product_classification.py・tests/test_check_authz_catalog.pyのexact6を実装追随対象へ加える。新3表だけfunction_only/reason=stats_primitive_storage/owner_unit=既U-X1、6-1-cの実原文に結ぶ事実を追加する。旧56表/既facts/分類規則は全保持、旧基線では新kind無しを許すが新表が現れればexact3全供給・scope/schema/owner/profile/余剰の閉拒否を必須にする。source/schemaの59全数と既sync_fence6＋新3以外を拒否し、app直接表権限や一般的な新profile許可は増やさない。作者cache-only exact6を非作者確認後rootだけが正式資産・sourceへ適用し、全CLI・実API/PGは別に成立させる。


実PG catalog表現の限定追随（2026-11-05、PO委任Codex /root判断）: 実0041/製品provision後のowned起動検査は初回1pass/3error8.62秒。拒否を維持した観測で、COLUMN-ACLのexpected617/actual613は既canonical xmin4列のみ欠落（extra0）、58関数detailsはstats5のTABLE列区切り空白だけ不一致と確認した。backend/src/pitchlog/authz/product_catalog.py・function_result_type.pyと新backend/tests/test_stats_catalog_pg_representation.pyのexact3を実装追随対象へ追加する。旧全正数attnum採取/全ACL/全関数列・型・権限照合は維持し、xminは既採用4組の実pg_attribute/attaclだけを採る。TABLE戻り値は型/列を無視せずpg_get_function_resultの表記にだけ揃える。一般system列許可/不足権限の成功補完/期待削除は不可。cache作者と非作者レビュー後にrootだけが採用し、95canonicalの静的レビューとは区別して同候補owned PGを再検証する。製品SQL/権限を変更して検査へ合わせない。


canonical採用後の閉期待追随（2026-11-05、PO委任Codex /root判断）: backend/tests/test_product_authz_catalog.py・test_authz_repository_contract.pyのexact2を追随対象へ加える。旧全DDL/706body/role/権限を保持した95pathの非作者094e815a…採否を根拠に、私有3表/1schema/5関数/10policy/70列ACLと2CAP/5tokenだけを固定期待へ追加する。旧policy基線91・旧66DML mapping/順序/値・既vocab function-only1は保持し、新5も一般DML登録へ混入させない。現在出力の集合をそのまま期待へ取り込まず、採用source/SQLから新有限literalと各拒否を明示して別非作者が確認する。検査条件・保存意味・新しい記録結果の変更ではない。


実RRRO試験の後発期待追随（2026-11-05、PO委任Codex /root判断）: tests/db/test_stats_primitive_read_scope.py（backend配下）の失効時assertだけを採用private reader境界へ追随する。owned初回1pass/1fail5.31秒では実REPEATABLE READ/on、書込SQLSTATE25006、scope失効拒否まで成立し、内部TenantBindingErrorのcause連鎖を要求する旧assertだけが不一致だった。採用f150aa2aの_state_key=None先行拒否は秘密参照を含まないPrimitiveReadError直返しなので、cause無し/args空と新BEGIN無しを厳密確認する。拒否自体・実driver例外型/SQLSTATE・データ不変の検査は全保持し、製品例外をテストへ合わせて弱めない。別非作者確認後にowned実2件を再実行する。


owned storage fixture接続の追随（2026-11-05、PO委任Codex /root判断）: backend/tests/db/test_stats_storage.pyのstats_ownerだけを既initial_scope_databaseの方式へ揃える。catalog修復後は実0041/provision/catalogを通過したが、fixtureが外側autouseに必要なDSNを消したままyieldし4error24.42秒になった。同一owned primaryの実admin/限定role DSNを既_dsn_names()の設定名へ渡し、verify_connection_identities自体と二主体区別・実認証照合は維持する。共有DSNの読取/利用やautouse無効化は行わず、所有container終結・環境復元を保つ。別非作者確認とowned全4試験を行う。


実API同TX縦断の受入試験（2026-11-05、PO委任Codex /root判断）: 新backend/tests/db/test_stats_native_vertical_http.pyを追加する。既実POST新規作成/開始/通常3球/再送/GETをそのまま呼び、同owned DBで新試合のevent3と成績source3の同ID、current_open版source_count/revision3、pitch_count3を照合する。参照選手以外のgame/記録事前投入・固定ACK・認可迂回なし。既requires_db/実identity autouseを有効にして、外部cache診断（42.41秒、DBmarker警告あり）を正式受入へ読み替えない。実API診断で発見したnative原本event_kindのplay→既正本play_inputへの是正は既source/test範囲で行い、元playの拒否対向を追加する。画面/公式成績/全T5/T6/終了確定集計/全原子性成立は別に検証する。
