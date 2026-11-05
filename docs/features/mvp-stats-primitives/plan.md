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

JST暦年と終了確定最新版だけの公式成績は既PO方針として維持する。40ceの要件に残る4/1年度の文言は、既採用方針の正式整合ゲートで追随し、期間の再裁定を求めない。**成績MVP-D02〜D05は2026-11-05のPO実回答で全てAを採用済み**。末尾の採用記録と伝播条件を現状の正とし、以下の旧未回答記述は採用前の履歴である。記録lock D02=A、CSV文書の「3表示区分は既決」という記述を、成績区分対応D02の回答へ流用しない。

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
| B16 | OPS | 出塁率/長打率の元分子分母 | **D05採用済み**。未丸めOBP+SLG→最終3桁half-up、分母0はnull/−、両母数は別保持 | 3–5 |
| P01 | 登板 | 出場区間/投手交代・再登板/0球を原記録供給 | **D03採用済み**。実出場game/player1、0球を含み再登板重複なし。実source供給待ち | 2–5 |
| P02 | 投球回 | 正式outEffect/走者別out数量/投手帰属 | outs合算→混合分数。第3out後outs resetの差を使わない | 1–3 |
| P03 | 打者数 | PA開始/完了と継承カウント/交代原記録 | **D04採用済み**。既A-2責任に合わせる。複数交代の責任source欠落時は推測しない | 2–5 |
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
| 5 | 試合別/season成績CSVと実結合受入 | 両CSV/画面が同snapshot/モデル/対象集合/全27metricの値・表示・状態に一致。実DB→実API→実画面DL、CSV bytes/ZIP manifest/hash/引用/無害化・大量/ページ/切断/容量/取消・認可撤回を検証。採用済みD02〜05を実装/契約へ伝播し、全27の実供給と取消訂正/再開/再終了を完了してからfeature完成。未回答中に独立部品/他項目を先行するが、27完成とは記録しない |

**具体的な最初の実装**はステップ1内で、(a)S/23flag/PA/帰属の閉型と独立期待、(b)共通モデル参照と整数/typed reducerの生成前検査、(c)実0/1/count/addコードとDB COUNT/SUM/window、(d)同一producerの実caller/3層まで。投球数だけのsample実装を合格条件に縮めない。最初にT5/T6全方式/全上流HTTP完成を要求せず、対象群の契約→その実計算へ操作単位で進む。rootのステップ指示を超えて次へ進まない。

## 7. 採用済み4判断・供給状態の扱い

2026-11-05のPO実回答をlead判断票1879aa46へ保存し、要件v2.19（本枝e65f4e3d、追加敵対レビュー3142286f…）へ反映済み。旧725c6ba2時点の未回答4件は履歴であり、現在の開始待ち条件にはしない。

| 成績ID | 採用済みの意味 | 実装と残る供給条件 |
| --- | --- | --- |
| D02 | 公式=公式戦+準公式戦、練習=オープン戦+紅白戦+その他、合算=5区分 | 同一typed選択集合をDB絞込・画面・CSVへ供給。未知キーを名称推測で補完しない |
| D03 | 実際に投手出場したgame/playerを1登板、0球を含み同試合再登板は重複しない | 正式出場/交代sourceが必要。区間数や1球以上へ代替しない |
| D04 | 既A-2の責任帰属に従う。2ボール交代→四球は前任1/救援0、既継承5countと申告敬遠も照合 | 正式責任sourceを用い、複数交代の責任source欠落時だけ留保。現在投手へ一律帰属しない |
| D05 | 未丸めOBP+未丸めSLGを加算し最後にhalf-up小数3桁、いずれか分母0なら値null/表示U+2212 | 同一D-1式/formatterを生成し画面・CSVを一致。OBP分母とSLG分母は別に保持し、供給不能と0分母を混同しない |

4件についてPO回答待ちを再生成しない。未実装/原記録不足をavailable/0へ置換せず、現候補codeのdecision_pendingは旧版の未反映でありPO未回答の証拠ではない。唯一モデル/閉契約/生成全targetと実供給を同じ作業単位で伝播する。metricの取得不能はsource_unavailable、失敗はfailedと明示し、空集合の0/率nullと区別する。全27供給前は完成表示しない。既原典で解決できない新しい意味空白だけ具体入力・根拠・未決結果をrootへ返す。

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


native accepted D5のtop-level挿入追補（2026-11-05、PO委任Codex /root採用・本体未着手）: 実API r3はread_primitive_writer_state prosrc107で閉拒否。既insert_result_or_recheckはbegin_nestedでINSERTし、owned PGのsubxid741/742可視性・ロック観測からSQLのledger xmin==topとの不整合を確認した。新backend/src/pitchlog/sync/native_ledger_insert.py、新backend/tests/test_native_ledger_insert.py、既sync/prefix_path.py・tests/test_stats_native_prefix_connection.py（後2もbackend配下）のexact4へ限定し、既4native validatorのaccepted台帳だけtop-level固定ON CONFLICT ON CONSTRAINT pk_idempotency_ledger DO NOTHING RETURNING1を実行する。既_prepare_operationの正本Table/全6typed bind/実tenant検証を再利用し、同handle/Session/topTX/native ready identity/原event/token全値/livebinding/lifetimeを前後照合する。caller指定SQL/資格boolを受けず、generic capability validator/旧66DML/旧SAVEPOINT経路/他validator/拒否は全保持する。実1行だけ新規、0行は既classify_d5で同じDI2/異内容等へ再照合、他失敗・不可視競合は閉拒否。初回classifyが既保存を返す場合はfresh専用control/source検査へ進めず既結果を返す。RETURNING0の場合も、待機中にleaseが失効していても最低限のhandle/runtime/context/同Session/topTX安全性だけを確認し、fresh側のpostcontrol/source検査より先に既classifyを実行して同じ再掲/異内容を返す。厳密RETURNING1の新規時だけfresh postcontrol/source/lifetime全条件を確認し、失敗は全体rollbackする。厳密0後unusedは従来どおり異常伝播。初回storedと0後storedそれぞれでfresh検査が必ずraiseする対向を要求する。新role/CAP/table/一般公開tokenを作らず、SQL側のxmin==top/全保存原子性条件を削らない。旧D5消費/優先順/結果を変える案は本追補外。固定SQL形be170656…・owned ON CONFLICTミクロ結果は実製品の認可/同TX受入とは分離し、非作者計画確認→作者cache4→別レビュー→owned競合/非D5故障→正式新規3球の順に実証する。


native台帳追補の採用記録: 対象HEAD7587e6124c58671af51370fc8337d67bf2039b86、計画全SHA256 3cc4ee7ef8e0811f1c64843b4c6abbf65845b5e364e3527567e8202f9b5c975a、作者資料b8b831e5…/固定SQL be170656…、非作者batted_hits_independentの同版確認通知「計画採用可」と独立compileの元Table/全6typed bind再現を根拠に採用する。初版2af02dacの0後lease失効時のreplay順序の曖昧さは7587で解消した。非作者証拠入口はcache stats-native-ledger-plan-independent-20261105/（最終REPORT固定後に同台帳から参照する）。判断者Codex /root、2026-11-05T14:39:34.647560+09:00、PO既委任による判断であり本人署名/人間逐行確認/P6blindではない。source exact4以外へ触れず、本体は別非作者レビューと実PK+uq_kind/競合/異内容/非D5/4profile/原子性の検証を要する。初回storedと0後storedではfresh資格を前倒しせず、厳密1の時のみfresh post全確認を行う条件を優先する。


native台帳接合に伴う単体試験境界の追随（2026-11-05、PO委任Codex /root判断）: backend/tests/test_sync_apply_first_ball_persistence.pyのtest_b2_absent_still_rolls_back_after_kernel_callback内だけを追加対象とする。作者検査385pass/3fail48.99秒で、同試験の既generic台帳lambdaNoneが新private入口へ適用されずfake Sessionが先に拒否されると判明した。B2非供給のprojection段階を検査する元の目的を維持し、同試験内でnew native台帳の私有入口を観測doubleへ明示設定する3行だけを追随する。旧consume1/host1/write3/FirstBallExecutionError/rollback全assertは保持する。実native台帳の真正拒否・正負検査は新test_native_ledger_insert.pyと実PG縦断で別に成立させ、単体doubleを製品認可成功へ読み替えない。作者exact4に本test1を加えたexact5へ限定、他test/製品/SQL/正式資産を増やさない。最終5差分を別非作者が確認する。


成績保存後故障の実HTTP原子性試験（2026-11-05、PO委任Codex /root判断）: 新backend/tests/db/test_stats_native_atomicity_http.pyを追加する。既ordinary実HTTP新規作成/開始関数・実認証/初期権/元artifactを再利用し、開始・initial GET後/最初の保存前に同owned DBを別admin read-only接続でsnapshotする。元flushを実行して戻った直後だけ固定故障を注入し、成功ACKが出ず、記録/台帳/prefix/投影/history/checkpoint/成績version/source/factの実前後が原状であることを検証する。同期点はtest専用tmp mountの公開gameUUID marker/continueのみ、元apply/認可/SQLをstub成功へ置換しない。snapshotに資格・原payloadをログせず、固定表/tenant/gameで絞った件数とcanonical行digestだけを保存。既requires_db/実identity autouse・cleanupを保持し、先行D5ミクロやpureを実原子性の代用としない。結果不明時の全取消・旧要求終結未確認を勝手に未消費/新D5置換可能とは扱わない。cache作者・別非作者確認後rootがowned PGで実行する。対象は当該故障1経路であり、全4profile/全故障/実画面/運用成立は別受入とする。


native台帳接合の採用記録: 作者exact5 packet c7e7f653…（helper74f8b4ca…/prefixf774ba0d…/新test97571cb9…/prefixTest6ccad048…/persistencecf1bea69…）を非作者98e28cd1793bba44035f60abc4cb77c99a2c91d805e8db0012dbfdd08be59c81で照合し採用する。作者497成功/独立421成功・追加20SQL0拒否、旧generic6source/66DML/SQLxmin/全保存境界を保持。新HTTP test f28283e4…は非作者90baf30e…でtmp結果分離P2反映を確認した。root隔離r4は実新POST作成/開始→ordinary-prefix-v1で3球/replay/GET→event3=成績source3/current_open(count3,rev3)/pitch_count3が1成功63.34秒。ただし未commit固定候補の初回実測であり、本commit固定HEADの再実証・全4profile・故障全取消・正式source/D11/7.7/CI・公式成績表示は残る。判断者Codex /root、2026-11-05 JST、PO既委任に基づく判断で本人署名・P6blindではない。


成績保存後故障試験の採用記録（2026-11-05、PO委任Codex /root判断）: exact1 c8ce45ad14f64de1c21b1c618d5237985aba00ae4f2445f76a84e87692e5961f、作者packet27d6ee50aa8a5449eda8ea7482152ec7e4a69cc1461ab535c2dc4d97c7105ac7、非作者REPORT fb28f4d9c3ef58d146ad8c33122b27142cee9764f8056eec1af3ab3267e6e9eb（P0/P1/P2=0、独立pure48成功）を照合して採用する。元flush完了後だけ固定故障を注入し13表全行を比較する。実PGの成功はこの採用時点では未成立。旧要求終結・D5未消費・新D5置換を推定しない。別の固定版b051defaの正常R5は新規作成/開始/ordinary3球/再送/GETと成績source3・球数3を1成功66.95秒で確認し、HEAD/tree/index前後一致・7証拠SHAを非作者8ba1dd24e939432cba81a4607489a9f2543213ae23bffda2b18ae5acb7270f0cで照合した。正常R5を故障・全profile・画面・正式集計の受入へ拡張しない。


同一保存データの実読取3入口試験（2026-11-05、PO委任Codex /root判断）: backend/tests/db/test_stats_native_read_http.pyの新exact1を追加対象とする。既実HTTP新規作成/開始/ordinary3球の記録を再利用し、実製品のRRRO scope/ReadPlayExportPrimitives.open/read_pageと成績Totals adapterを同じ実DBで呼ぶ。全取得/page_size=1の連続cursor/正規sourceと確定指標の一致を確認し、同receiptを別scopeへ移植/終了後利用/別tenantを拒否する。既source/SQL/認可/fixtureを成功stubへ置換せず、未確定指標を0で補わない。実UI/公式終了試合集計は別受入。最初はcache-only exact1、不可分な供給不足は最小差分と根拠をrootへ返し、別非作者確認後に実PGをroot直列実行する。


current製品起動の接合追補（2026-11-05、PO委任Codex /root判断・レビュー前）: owned回帰20setupERROR90秒で、既S0〜S3入口は0039までなのに現canonical成績5関数が0041表を必要とする不足を確認した。read-only338ced7bb113b04706e7ebc88b0f7b243cc978f75e4e37b82f7de79771c53e70に基づき、新backend/src/pitchlog/db/current_product_startup.py、backend/tests/db_fixtures.pyの_prepare_current_product_baselineだけ、新backend/tests/test_current_product_startup.py、新backend/tests/db/test_current_product_startup.pyのexact4を追補候補とする。旧stage_a_startup.py/S0〜S3/0039/legacy/0036 profileは全byte保持し、新current入口が既privateのS0認証・同接続先主体・S1認可/placement/epoch/initial/writer各検査を再利用、旧0039実検査成立後かつ全現認可適用前にowner同TXで固定0040→0041を適用する。固定0041版、採用済成績3表54列/制約/index/owner/FORCE RLS/default-denyを閉照合し、現canonical全認可・全catalog照合後もpublishableFalseを維持する。汎用head upgrade/任意DSN/共有DB適用/欠損補完/旧段階検査skip/全旧fixture0041化は不可。失敗は伝播・対象TX rollbackし未完を完了扱いしない。外部DB supply経路は変更せず、current fixtureだけ新入口へ接続する。計画の別非作者確認後cache-only exact4を実装し、再レビュー後にrootがowned PGで新入口と旧prefix境界20件を検証する。旧0039試験がcurrent全DDLを直適用する残件は歴史profileへ分離調査し、本追補で既旧期待を書き換えない。


実read3試験の採用（2026-11-05、PO委任Codex /root判断）: source exact1 e1f159dc5a49c798c28e857bc535000de621ae81a6d9f25074f1fe44d62fea04/作者packet4db7573b…を非作者6a79d6a15b4b4afac14051eddd2fa08c3354978360aa4a24360254fa7d238f32（独立pure32成功0.99秒、既12anchor全byte同一、P0/P1/P2=0）で採用する。既実POST3球保存をそのまま通し、真正issuer/RRRO/Open/Page全78行/Totals球数3/移植・失効・別tenant固定拒否を検査する新testであり、採用時点の実PGは未実施。writer側の作者による通常非作者testレビューを全source/P6blindの成立へ広げず、未決4意味/公式終了集計/成績HTTP UI/通常current起動/7.7/CIは別残とする。


実read3のwindow期待訂正（2026-11-05、PO委任Codex /root判断）: 初回a040a792実PGは1fail69.41秒、真正read実行後にPage球数2を旧testが各source寄与1と誤認して停止。既plan§4のCOUNT window・唯一モデル・生成SQLは保存寄与1/1/1とPage累計1/2/3を区別する。test exact1候補053fbca38468aa6a4203c36190438f273360abb6561ef21f2be3fdad44b77a5dで3行の(value,display)を固定[(1,1),(2,2),(3,3)]へ完全比較し、他全assertを保持。非作者0c7f13af939fbe04853fbb3cdd925386ecf9f787dfc036a2dff91d4a9bdd8dacが原典と旧32全対向/新all1拒否を独立33成功1.01秒で確認したので採用する。初回レビュー見落としと実失敗を保全、製品SQL/計算/保存値や未決意味は変更しない。実PG再検証前を成功にしない。


current起動追補の限定反映・採用（2026-11-05、PO委任Codex /root判断）: 非作者REPORT a1345944b0ae3949cd48857ff0af0bbd4c9efd9332dfa1fd029731f399591fd6（対象8ba1c909/plan SHA d3dacdc555a76848080c907326a89289bff320080995f6c142d7aab47b2b1e59、packet8761a081e08553aeb1e5bebec773083b3aa3256bbe92390397713b6fc451dd5c）の初回P1=scope不足を次で解消し採用する。前記exact4にbackend/tests/test_product_authz_provisioning.py::test_current_and_legacy_owned_baselines_do_not_forge_stageのcurrent半分だけを追加したexact5へ限定する。新entry mock/固定0041・publishableFalseのCurrentProductStartupResultへ追随し、旧0039/0036をcurrent拒否、legacy後半全ASTを保持する。
採用条件は同REPORT全7項を本計画へ取り込む。旧stage_a_startup/S0〜S3/legacy全byteは保持し、旧validatorを使うのは実0039までのみ。0041後は新currentの全sync_fence9表を、旧全期待と新54列（型/null/default/identity/generated）・PK/FK/CHECK/index/owner/RLS/FORCE/ACLで閉照合する。0040 fixed index ix_admin_vocabularies_batted_ball_key_cのpublic.admin_vocabularies/key/C/btree/nonunique/承認predicateをexact確認し、欠落・異型/対象/式/順序/predicate/collation/invalid/未知余剰変更を拒否する。既0036seed hookは旧module属性を実呼出しし、alias固定で迂回しない。0040→0041は同owner supplied connection/TXで、故障時revision/構造とも0039へ戻す。実0041再開はmigration0、全構造/index検査後、既知pre-full default-denyと正規full catalogのみを区別して許可し、未知partial/余剰ACLを補修成功化しない。pre-fullのFnOwner未grantとfullのcanonical最小grantを区別しapp/PUBLIC/actor拒否を維持する。偽revision/接続wrapperによる表隠し/旧globals拡張/汎用head upgrade/検査skipは禁止。新role/CAP/権限/野球意味・公開許可を増やさず既全DDL/catalogを確認する。
実装作者pr191_residual_independentへcache-only exact5を許可し、別非作者確認後rootだけが実sourceへ採用/owned PGで新入口・旧境界を検証する。承認の実態はPO委任Codex判断であり、人間逐行確認/P6blind/実PG成立ではない。初回P1と全条件・後発差分を保持する。


current pre-full宣言の共有（2026-11-05、PO委任Codex /root判断）: exact5へbackend/src/pitchlog/authz/product_provisioning.pyの既_build_operation_statementsからselected generated要素の閉導出をprivate helper1へ抽出する技術追随だけを加えexact6とする。既APPLY_PRE_RULEの70＋追加deferredの算法をcurrent側へコピーしないための不可分最小差分で、新scopeの機能追加/権限追加ではない。既loader/validate/全deferred exact-set/主体拒否/全手順・生成SQL・順序・全operation結果と例外を保持し、unknown operationや自由選択setを許可しない。newcurrentは同helperから読み取り専用で正規pre-full要素集合を受け、任意subsetや現DB出力でexpectedを作らない。既test_current内に抽出前後の全SQL/sequence/手順/拒否の同値回帰を置き、全6差分を別非作者が再確認する。旧stage_a_startup/legacy全byte保持と前記7条件は継続する。実source採用は非作者確認後rootのみ。


成績D02〜D05のPO回答に伴う正式伝播（2026-11-05）: PO実回答と留保の正はlead WT decision-sheetの1879aa46。D02は公式=公式戦+準公式戦、練習=オープン戦+紅白戦+その他の同写像を画面/集計/CSVへ。D03は実投手出場のgame/player1件で0球も対象、再登板重複0。D04は既A-2の責任帰属に合わせ、ボール優勢5count/その他count・四球/申告敬遠/他結果・複数交代を既記録へ照合し、未定義/矛盾だけPOへ具体提示。D05は未丸めOBP+SLG→最後に表示round、分母0/桁数を既A-1へ整合する。意味判断待ちは4件とも解消したがsource不足/未実装をavailable/0へ変えず、正常保存/読取の26primitiveを新公式27指標完成へ読み替えない。
pr192_harness_values_independentへcache-onlyで、既候補55期待を保持した採用4規則の対向ケースと要件正本最小改訂草案（既PO採用JST暦年の残存年度文言も同一正式整合候補へ）を割当てる。正本/READMEの追随候補、既docs/features/mvp-stats-primitives/research.mdとprimitive-cases.candidate.jsonへの根拠/境界ケース追加候補をexact4として作成し、公式版番号は実統合履歴を照合する。D04の明示既規定・推定不可の空白、D05の既定零除算/小数3桁half-upと構造値を区別。コード/期待値を製品出力から生成しない。rootが必要な7.3/契約採用/独立確認を直列処理し、成立したD02選択集合・D05式/formatterから同一D-1モデル/生成target/typedSQLを実装する。D03/D04のsource/API未完成を他指標の着手前条件に追加しない。正式models/contract/generated/shared assets/台帳の実writerはroot、current起動作者pr191の6pathへ触れない。


current起動exact6の採用（2026-11-05、PO委任Codex /root判断）: 作者packet5428dac1e633f134c91daccb863affc4ec70bd35ba3d7109134eb44153fe0b15（currentf98713a1…/fixture8cb228f3…/purebf935dab…/DBbc636bae…/oldtest8f37989a…/provision9e751b49…）を非作者0188d75195880401f41e63f2d030848019b78944c9eb95dda9abaa9d39129aaf（独立83pure成功13.33秒/追加式反例11、旧AST・全54列・scope保持、P0/P1/P2=0）で照合し採用する。旧stage全byte/fixturecurrent外・legacy半分/元provision抽出以外ASTと適用SQLを保持し、canonical選択集合の共通helperを使う。DB15件は収集のみであり、実PG deparse/pre-full全catalog/0039rollback/41migration0再開は採用時点未実証。rootがまず実S0→0041/正規再開の1件をowned PGで実行し、準備成功後に残14・旧prefix境界20を実施する。新正常実証を全MVP/正式統合/P6成立へ拡張しない。


current pre-full builtin分類の是正（2026-11-05、PO委任Codex /root判断）: 017cd09f実nominalは5.57秒でpre-full未知catalogに閉拒否。元catalogを変えず検査ID/件数だけのowned観測で未知はBUILTIN-ADDITIONAL-EXECUTE1分類と特定。既selected canonicalがpreの追加EXECUTE2主体を適用しbinding owner1だけを保留するので、current/test exact2（f994139f…/c669291a…）で同selected由来pre2/full3の全tuple対を追加。旧他8分類/全旧期待/全判定を保持、PUBLIC/DECLARED/未知/混在/余剰を許可しない。非作者de656d2f212274113bfbcfc0b7acb54cb95825095ccf8e5d775d11968ee7f84bが独立95成功40.26秒（候補83+新12対向）で採用可確認したので採用する。runtime他AST/全旧6setsと全pairs保持。実PGは再検証前であり、初回拒否を成功へ書換えない。


current migration既設pre-fullの厳格接合（2026-11-05、PO委任Codex /root判断）: owned nominal r2はpre/fullの部分不一致で閉拒否。元catalog/期待を改変しない観測で、0036 protect_initial_right_storage関数1と0006 projection_identity trigger1はmigrationが既設するがselected app DDLだけのpre導出に欠けると特定。current/test exact2に限定し、canonical full原典の既1関数/既1triggerを全fieldと一意件数を確認してpreへ含める。全文/owner/schema/対象/列/型/全trigger16値・旧他分類/full全tupleを保持、未知/余剰/重複/宣言欠落/full混在を拒否する。候補376598f0…/7c21340e…を非作者a0861e715bd6b7fde77898c3e3e970513e12eeb59cf0594eda3268c0dd15821f（独立96成功37.76秒=旧84＋追加12、Ruff0、P0/P1/P2=0）で採用可確認。実PG成功は未成立、旧拒否を残しfixed採用後owned nominal1から再確認する。権限/判定ID/検査範囲を緩和しない。


current適用前読取transactionの終結（2026-11-05、PO委任Codex /root判断）: 277da7d6 owned nominal r3はpre-full厳密照合を通過し、正式apply_product_authz_ddlのIDLE前提で拒否した。直前の同connection readがimplicit transactionを開始している。current/test exact2で、既legacy resumeと同様、全構造/index/rules/public storage/pre-full検査用接続を正常に終了してから新しいIDLE接続で既applyを実行する。apply自体の状態再照合/同TX・全拒否条件/事後全catalogは保持する。既進行TXを強制commit/rollbackして適用する回避やautocommitは使わず、検査失敗時applyしない。新純回帰で全5読取がdirty化した接続の正常終結→別接続IDLE→apply→事後全確認の順序を検査、検査例外時applyなし/伝播を保持。root候補を別非作者確認後に実sourceへ採用しowned nominal1を再検証する。r3の失敗は保持。


current IDLE接合exact2採用（2026-11-05、PO委任Codex /root判断）: root候補8e7467c9…/d4191c9a…を非作者fb295a1f1f2be77e173e454c3bc138ceddda28f77f370ee14d42b43ddb05c193（独立84成功24.27秒＋review copyのGit不足を補完した旧原典1成功2.57秒=85固有case、P0/P1/P2=0）で採用。旧全AST/適用器IDLE・主体・同TX・全事後catalog不変、事前read接続終結後の新IDLE接続だけへ分離する。初回review環境失敗は保持し同候補の全実DB成功とはしない。rootが同固定版でowned nominal1を実証後、未実施残14/旧prefix20へ進む。


製品fixtureのsnapshot schema追随（2026-11-05、PO委任Codex /root判断）: e8e991a1のcurrent normal1/negative14は実PG成功、次の旧prefix20は全setup ERROR131.36秒。現在の起動を通った後、tests/db_fixtures.py::_snapshot_product_catalogが旧3profileのschema閉集合にstats_apiを含めず拒否した同根で、prefix本体実行は0件。exact2はbackend/tests/db_fixtures.pyとbackend/tests/test_current_product_startup.py。作者pr191へcache-onlyで、旧3schema集合・全文snapshot項目/SQL/順序を保持し、既現currentのlegacy+private+recording_vocab+stats_apiの全13schema1profileだけを明示追加する。任意subset/unknown schema/重複/型不正を許さず、stats_apiだけの欠けた親profileを受けない。必要なら閉schema名検査だけprivate helperへ抽出し元snapshotが必ずその検査を通す。実DB出力から期待を採取せず、固定既宣言名と前後完全なprofileを対向で検査。新schemaに属する関数/ACL/ポリシー等は既snapshot query対象へ含まれ、実現集合から除外しない。旧historical snapshot/旧stage/runtime/生成物/正式資産は変更0。別非作者確認後root反映し、旧prefixまず1case→成立後残19を一度だけ検証する。全20の同根ERRORを意味修正で成功化しない。

同snapshotの不可分private表集合も同exact2内で追随する: 新current全13schemaだけは既sync_fence6表＋既正式0041のstats_fact_versions/stats_primitive_sources/stats_primitive_facts3表=9の全集合を期待し、旧3profileは旧0/6表のまま。新3があるのにschema不足/9表の一部欠落/重複/別schema/未知表を拒否する。既builtin権限3主体/全snapshot列・SQLを保持、新stats表をsnapshotから除外せず実値として含める。helper抽出はこの閉profile(schema,private table)対だけとし、現在DBから正例期待を作らない。


snapshot exact2採用（2026-11-05、PO委任Codex /root判断）: 作者packete0ef8cb4…/source d29546e0…・d4746114…を非作者/root e5067fc5407b4e2d04305859bd3a3af60e48fa65af136a212b724e2ed2ee1c51（独立新36成功0.39秒、旧85定義AST保持、P0/P1/P2=0）で採用。作者最終121と既旧85独立fb295a1fは別証拠として保持。旧3profile/全snapshot SQL/項目/builtinは不変更、新full13/9だけ追加しsource不足を補正しない。次は同固定sourceでowned旧prefix1→成立後残19。


D02/D05の最初の契約単位（2026-11-05、PO委任Codex /root判断）: 調査7343218c25f66b33ac1611305fe2af235d525e73cbee2c9e42bba9eb25867b6c/scope d307974a…に基づき、同compilerの歴史v1入力＋current v2出力を区別する技術版境界を採用する。旧55全値/順序（34のpending4全比較含む）と既PO76を保持し、current v2のD02選択集合/採用metadata/D05整数比・両分母/零分母/一度だけhalf-upを独立20対向で先置きする。新v2でも旧26primitive/PA/creditの全値を比較し、歴史期待の置換/部分一致化/数値availableへの状態flipは不可。候補編集はdocs/features/mvp-stats-primitives/primitive-input.candidate.json・primitive-output.candidate.json・primitive-cases.candidate.jsonのexact3だけ、作者pr191がcache-only作成、実writerrootが非作者確認後に採用する。期待を製品出力から採取せず、PO76の根拠/整数比から再計算し出所を分離する。候補contractであり正式D11/P6/実装/DB完了とはしない。

後続の単一計算は同調査のdecl/emitter9＋回帰7/生成8、同版native admission最低5/正式D11登録5とcollector追加scopeを、契約ABIが固定した時点で最小追補する。OPSを旧26整数metric行へ偽装せず、同一D1のratio/add/名前付き閉集合とformatterからPython/TS/SQLを生成する。一般formatterのNumber/Decimal精度依存へ流用しない。D03/D04source待ち・DB/HTTP/全27/画面CSV完成は当該計算bodyの開始前提に追加しない。旧D5の保存済みACK再掲/新旧seriesの拒否条件を維持し、旧factの破壊/無根拠再刻印やserver/client数学コピーはしない。rootが次scopeを明示するまで本体source/生成物/正式資産を変更しない。


D02/D05前置契約v2 deltaの受理（2026-11-05、PO委任Codex /root判断）: 作者packete9b8972b…/REPORTc5cc2262… exact3を非作者de8096a99ff8d4a784f519fa1778f6b03a1ddadc15dac3990aaa5e58fc347fe6（P0/P1/P2=0）で採用する。旧55/PO76/finite2/全v1と固定Git3モデルを保持、新20＋v2回帰55の26metric/PA/credit全比較を追加。T6数学21・115否定/EOS48/5001桁shape/101桁比を独立照合。reviewerはbaseline内旧PO76作者と開示した本delta3の非作者であり、全stats PR/P6blind/実装/DB/GUI/D11を承認したものではない。実before/after全SHAを検査して反映し、根拠のあるv2数学本体の開始条件とする。正式D11の未成立を実装完了へ読替えず、他source不足を計算本体の追加開始条件にしない。


D02/D05 v2数学の計算本体着手（同日、PO委任Codex /root判断）: 前置contract3を採用済みとして、作者pr191へcache-onlyのdecl/emitter/回帰exact16を許可する: backend/domain/model.schema.json、backend/domain/play-export.model.json、backend/domain/stats.model.json、backend/src/pitchlog/domaingen/pregen_checks.py、backend/src/pitchlog/domaingen/core.py、backend/src/pitchlog/domaingen/backends/python.py、backend/src/pitchlog/domaingen/backends/typescript.py、backend/src/pitchlog/domaingen/backends/sql.py、backend/src/pitchlog/domaingen/formatter.py、tests/domain/gen/test_pregen.py、tests/domain/gen/test_core.py、tests/domain/gen/test_formatter.py、backend/tests/stats/test_basic_stats.py、backend/tests/stats/test_primitive_facts.py、frontend/src/lib/generated/wrappers/statsPrimitives.spec.ts、backend/tests/db/test_stats_queries.py。共通D1だけがnamed scopes公式2/練習3/合算5・exact ratio/add・2分母構造・表示bindingを宣言し、Python/TS/typed SQLへ生成する。旧26integer refsを保持しOPSをinteger metricへ偽装しない。同じWHEREをcount/rate/seasonの両境界へ適用し、tenant/終了確定/JST/canonicalS/version/keyset/NULLとsource不足区別を維持。half-upは整数商/剰余による最後1回だけ、小数3桁/先頭0/両母数/U+2212を宣言から一致させ、Float/Number除算やDecimal既定精度/全局桁数制限変更に頼らない。旧55は同compilerへ真正immutable v1モデルを与え全値比較、current v2も旧26/PA/credit全比較＋新20を保持、旧期待を修正して緑にしない。

生成8（公式generatorのみ・root実writer）: backend/src/pitchlog/stats/generated/facts.py、frontend/src/lib/generated/statsPrimitives.ts、backend/src/pitchlog/exports/generated/play_primitives.sql、backend/src/pitchlog/stats/generated/stats.sql、backend/src/pitchlog/stats/generated/receiver.py、backend/src/pitchlog/stats/generated/formatter.py、frontend/src/lib/generated/statsFormatter.ts、backend/src/pitchlog/stats/generated/stats_rates.sql。作者は検査用shadowで生成して3層の全値/型/NULL/巨大整数/最終roundと対象集合を検査し、source候補16と配布提案SHAを分離する。既native admission2source/3回帰と正式D11/collector/生成authzは後続でrootがscope固定するので、今回SQL/DB live採用を完了としない。shared files/他WT/refs/台帳/DB/uv環境を変更せず、必要scope不足のみ根拠提示し一括追補する。別非作者の最終差分確認後root採用する。


D02/D05数学本体24の採用（2026-11-05、PO委任Codex /root）: 作者packet0d4ce74d6f412f052a3e57722b9f7ca9dc7a83b4b405a1b024c1d85209a12406のsource16＋公式生成8を、非作者7fd457b6b1d2d3209c5494a2cdf127adba82eb6d2a2c92a39fdc7abf6cc5314d（P0/P1/P2=0）で採用する。共通D1旧26/PA/credit/選択集合保持、生成8再現、Py/実TSのFraction1023入力/5001桁とglobal4300不変を独立確認。検査環境のprettier不足/venv jsonschema不足/同copy内Vitestとroot snapshot競合は保存し、根拠を変えた当該2だけ再確認して62固有成功へ結合。rootがactual source16を反映し公式generate_primitive_bundleで8を再生成、全24後値SHAを完全照合した。同実枝でbackend245成功45.52秒→root62成功10.35秒→frontend25成功を直列に行い、一時fileの競合を避けた。SQLite/構文・閉bind確認と実PostgreSQL未実施を分離する。D03/D04採用済みとsource不足を分け、全27/正式D11/native接合/画面/CSV完成にはしない。


D02/D05同版native admissionの次scope（2026-11-05、PO委任Codex /root）: 前記数学24と受理済v2契約3を基に、step2のbackend/src/pitchlog/repositories/stats_function_codec.py、backend/src/pitchlog/authz/stats_primitive_sql.py、backend/tests/test_stats_function_codec.py、backend/tests/test_stats_primitive_product.py、backend/tests/test_stats_native_product_connection.py exact5を作者pr191へcache-only実装許可する。旧v1の全閉形/旧4pending/旧modelhash・署名/保存済みACK・拒否を保持し、current v2は採用済みD02/D05、実装未了D03/D04、正準modelhash/版/源本/SQL宣言を同じ閉envelopeへ正確に束縛する。旧schemaを曖昧化せずversionで閉じた別profileへ分け、未知版/余剰/型違い/誤hash/source不足/未完を0やavailableへ補完しない。既factをin-placeにv2刻印し直さず、旧ACK再掲や旧版sourceの意味を新版へ拡張しない。既真正source/同TX/ACL/既故障分類・D5/失敗順を維持する。数学は生成物を一度呼ぶだけでnative層へOPS式/全event独自集計を重複させない。v2純生成だけの成功を実DB/耐久性へ拡張せず、正規native providerのnamed/raw bind、rates追加/SQL/source登録/正式D11に追加scopeが必要なら不可分理由とexactpathを返しrootが一括具体化する。共有source/正式assets/refs/DBへ作者は書かず別非作者後root採用。shared DB適用なし、実PGはrootのowned隔離環境で正式5関数の配置/新規試合3球保存/再読取/再送/原子性を後段検証する。


同版native接合の不可分scope追補（2026-11-05、PO委任Codex /root）: 既5内の一次照合でsync/stats_native_flush.pyの旧pending4固定検査がSQL前にv2を拒否すると確定したため、同fileとbackend/tests/test_stats_native_flush.pyのexact2を追加し、writer許可を計7にする。SQLモデル/ARTの多版IN許可やwriter-state2の変更は採用しない。current登録5 SQL関数は現v2の1model/1ART完全一致を保持し、v1は既保存履歴の厳格decodeと既ACK再掲を保持する歴史profileとして区別する。旧v1の新規SQL writeをcurrent資格へ追加せず、旧保存factを破棄/書換え/新版へ暗黙解釈しない。旧モデルしか無いsourceをcurrent available/0へ補完しない。未統合候補の先行実測を旧v1 SQLの正式提供保証へ拡張しない。既正式live旧版の継続提供を要求する原典があればその限定範囲を再確認し、黙って撤回しない。

root専有metadataはbackend/domain/stats-manifest.json exact1へnativeEvaluationProfiles.v1/v2の閉layout {model_sha256,generation_input_files3,artifact_binding}を提案する（作者案60b72220…）。v1は元manifestの全来歴/旧原値、v2はrootが公式生成8から全後値を再現し、別非作者後に供給する。runtime Gitや旧hash文字列の手書き、自由未知profile、旧D1 UTF8全体の新manifest埋込み追加は採用しない。旧artifact bindingは歴史identityで、現実行fileと偽らない。type/version/必須・余剰/modelhash/3inputSHA/ARTの全型/値を検査し、1/true等の混同も拒否する。型やmanifest行は保存/認可資格でなく、current SQL sinkは旧model/ARTを引続き拒否する。現在D11のinput/generated/T5 binding SHAを変える正式metadata追随はrootが全pointerを列挙し、旧v1値を前置保存してから独立確認する。未知SQLや全27/実PG/UI/CSVを成立扱いしない。


同版native接合7＋root manifest反映1の採用（2026-11-05、PO委任Codex /root判断）: 対象計画固定HEAD c08aa2c0470443cc0814432ada8524c82968ac32、作者packet ad48cfd11ff924c77223b0f9fb7395efee0ab6a7e16559870e9d7efc91298a52、非作者REPORT 38cbe9704a1df6379740a8314943f60545bbb94007e6c5112a2c6ad741a2b096 / checks 4c6cbaf115e4fd59361547c06bc72d4ab755867c229c21c622a22fb4ab214cae、全8差分SHA 622d844a8c554fc4c7ff6cf7f47c6a63ec731cde0859841d3a46267f3326f68cを根拠に採用する。初案manifestの独立contract参照3の旧SHA残存P1は、同fileだけの反映1（2af26c51e4e563ddab837b152b39b6877a8b727f011a90b5cda104e41ececef9、旧27＋参照3=30pointer）で解消した。独立595成功＋追加29拒否対向・静的検査は実PG・正式受理・全MVP完了を示さない。

信頼境界の明確化: v1歴史decodeの信頼入力はレビューして配置する固定manifestであり、runtimeが旧モデルの真正性・本人署名を独立に暗号検証する仕組みではない。「未知hash拒否」は入力を当該閉profileへ照合する保証を指し、自己整合した配置metadata差替えへの独立耐性を意味しない。旧v1の全値は原manifest・immutable旧モデル3/生成7との独立照合で固定する。v1は保存済み原値decode/ACK再掲だけ、current SQLはv2の1model/1ART完全一致だけを許す。旧factの破壊・新版再刻印・0補完・旧SQL資格の追加はしない。採用後rootが実枝で影響検査、owned PG起動/3球保存/再取得/再送/故障全取消を順に検証する。人間逐行確認・P6 blind・山田正輝本人署名とは記録しない。


受け口生成の型絞込み追随（2026-11-05、PO委任Codex /root判断）: actual3c81f522の関連766成功・scopedRuff成功後、backend全Tyが生成receiver.py:258/267でNoneの添字参照2件を検出した。前置any(None)拒否は保持し、domaingen/backends/python.pyの生成文字列中の後続2条件だけをpair is not None and pair[1] == 0へ明示する。任意Noneを受理する意味変更ではなく型推論へ同じ到達条件を示す追随とし、正式generate_primitive_bundleで8を再生成し他7生成byte不変を要求する。編集許可exact3は当該emitter1・公式生成receiver1・backend/domain/stats-manifest.jsonの同入力/生成SHA2pointerだけ。contract/モデル/SQL/formatter/旧v1profile/T5 ART bindingは不変更。既receiverの全PO/拒否対向を検査し、別非作者が意味同値・公式生成・前後値を確認するまで本体へ採用しない。元Ty失敗を保全しignoreや検査除外で通さない。


型追随exact3反映1の採用（2026-11-05、PO委任Codex /root判断）: 非作者REPORT2f5b4af9d23093774f79b90ab33048a57be9a86a73541a6d0ae7c50443293f1f/checks44245d369e6e1a8013d56f87080209952028994134a1ce40c0f81d967cecaaf3を根拠に採用。初案emitterのE501を生成文字列内の括弧改行だけで解消、ignore追加なし。独立492nullable/state/不正数値の旧新全返却/例外型/文言一致、既PO/拒否/巨大Decimal3成功、公式8再現・他7不変・真正v1旧7不変、manifest2pointerのみ・Ruff/全backendTy成功。新SQLやPG提供を証明した結果ではない。

実起動停止の正式本文v2追随（同日、PO委任Codex /root判断）: read-only REPORT82826eecceb51d2b73a4782257c6a546b5e57fd2a387cc3e5a1fbcc42bc464c3/checks5555f0fbb3c5acee2ba6ec36c60b3a614cda9d11d21a81f9ffea04c291a0ffdbにより、既canonical34中29は一致、採用済みcurrent v2のstats5だけ旧v1正式本文との不一致と確定した。author pr191へ次exact5をcache-onlyでproducer.body()から生成する許可を与える。各原本は真正ec3fdad5 blob/旧beforeSHAと全byte照合して保全し、既source7/公式SQLと独立比較する。手で本文を変更せず、v1歴史入力/生成/保存ACK/全旧29/署名/関数ABI/ACLは保持。
- `contracts/authz/product/function-bodies/functions/FUNCTION:stats_api:save_primitive_source(uuid, uuid, uuid, text, bigint, text, jsonb, bytea).sql` before SHA256 `85b0c8a1088a24f04ac6615383611bed274aca4a4819de141e95992ee214a372`
- `contracts/authz/product/function-bodies/functions/FUNCTION:stats_api:open_primitive_snapshot(uuid, uuid, text).sql` before SHA256 `bb4ff6223cf2d682741e3b494f141718394430aafcd2949e5066de838e669039`
- `contracts/authz/product/function-bodies/functions/FUNCTION:stats_api:read_play_export_primitives(uuid, uuid, uuid, bigint, text, text, text, bigint, uuid, text, integer).sql` before SHA256 `18c5d961828d5a7c06b94bb01a802b029a61f41b9d51ecc4a83d7537cec553cd`
- `contracts/authz/product/function-bodies/functions/FUNCTION:stats_api:read_primitive_totals(uuid, uuid, uuid, bigint, text, text, text).sql` before SHA256 `c37e01be3bdd8a16eee3bd570a1885f656b2495ebfd7c80988cf05d9582c20ab`
- `contracts/authz/product/function-bodies/functions/FUNCTION:stats_api:read_primitive_writer_state(uuid, uuid, uuid, text, bytea).sql` before SHA256 `073e7a5e0617cd6f286677027eb864aa09134dc61b369f3520ed732011aabd5b`

source/body5確定後のruntime derive/render・tenant rederive・実変化の7.7/必要seal追随はroot専有で直列化し、差分path/全前後/非作者を先に固定する。登録manifest795集合/役割/関数追加や拒否の緩和は許可しない。実PGから期待を採取せず、official関数生成との正確な対応だけを受理し、owned新規作成/開始/3球/replay/read/faultで再実証する。型追随や旧v1実測をv2成功としない。


正式stats5本文の採用（2026-11-06 JST、PO委任Codex /root判断）: 固定6d4994bbの候補packetfd4d4895b2a88c79e845771282079af1b538692995c42bfe2c4c02123856bd49を、非作者REPORT9ddcabc1ce22713cf18af2fd565f13c3d87ea5fedf84be13826114d2b749a301/checks8c57c2ce94d546d27d90feb0d201faac3d1fa640ae218214be2edd90b95ef7f6で採用する。独立全差分c255499cec5ffde143f2c77589cda64ce0b023133a07e7d82a521325f5968986はmodel/唯一ART/閉decisions metadataだけ、全認可/TX/tenant/WHERE/page/拒否/関数ABI/ACLを保持。旧before5は真正ec3原物と照合保存、manifest795/旧29/全DDL/immutablev1旧10のbyte保持を確認。新5受理/旧5＋改変15拒否・official bodycheck/関連38独立成功。rootは全before/after SHAを確認して5だけ反映し、runtime/tenantの公式deriveをread-only照合、差分が実在する場合だけ別scope/非作者後に更新する。実PG compile/保存・再取得/再送/故障、7.7/必要seal/正式D11/画面・CSVは未成立。PO本人の確認/署名やP6blindとは記録しない。


step1 native共通基盤の独立通常統合単位（2026-11-06 JST、PO委任Codex /root）: 実PGで保存/実RRRO読取/全13表rollbackを同版確認済みbcee3decの源本を保持し、既c229c68f（#196候補3eccとbceeの必要依存だけを合成した固定点）から専用feature/mvp-stats-native-foundationへ分離した。51bcb4e1正式developへ通常mergeし源本/旧生成/採用済み意味を保持する。取消/未採用spikeをこの単位へ混ぜず、後続取消Sは本native5関数/0041/26共通事実を依存として引き継ぐ。原stable bcee/BF27枝/取消枝は保全する。

本PR単位は真正native sourceから唯一T5の26既metric（BFは後続）を同外側TXへ保存し、同版RRRO receiptでOpen/Page/Totalsを読み取る実基盤だけ。親planの27基本成績/公式終了最新版/暦年画面/成績CSV/0球登板/責任継承等の未完条件を削減せず、feature/step1全体やMVP完成判定はしない。actualcurrent27関数とformal27、関連7module437成功41.75秒を確認済み。tenant CLIのfrozen-input識別未追随は旧候補履歴に対する真正移動なので、未受理を隠さず新単位の正式値として全前後を導出する。

rootはこの専用WT/PRの唯一writerとして既公式producerで最新base51bに対するrepo/runtime/tenant/Census/derived modules/D11/認可seal等の必要差だけを整合し、公開PR番号取得後の委任policy対象も当該PR/枝に限定追加する。既37+196履歴を保持し未公開旧候補のjournalを正式採用としない。生成物手編集・snapshot一括削除・検出/拒否緩和・本人署名代記は禁止。最終差分の非作者レビュー/同版owned新規作成・保存・再送・実read・途中故障検証/公開委任証拠/全必須CIの後だけ通常mergeする。検査待ちには取消S/GET接続を継続する。


release検査の生成集合追随（2026-11-06 JST、PO委任Codex /root判断）: 固定582375bdの非作者REPORT823a96303c3232d963ef7c95c53fd3fc1f18e015be2b0e85ccd87f119b78da6cが検出したR1だけを先に是正する。対象exact1はbackend/tests/test_stats_sql_generation_runtime.py。SQL_PATHSへ採用済み唯一生成stats_rates.sqlを加えて正確な3件集合へ追随し、二SQL/七対象の説明と試験名を三SQL/八対象へ現状整合する。元のformatter/他言語生成禁止・全byte比較・不正モデル拒否を全て保持し、製品数学/モデル/生成物/manifest/正式値は変更しない。修正後に当該全検査と非作者の限定再確認を行う。追加release gateのscopeは別記し、本修正でcore/D11/正式受理/実PGが成立したとは扱わない。


release core登録・CI起動の最小追補（2026-11-06 JST、PO委任Codex /root判断）: source review823a9630で固定した未登録25path（cache stats-native-foundation-source-independent-20261106/core-unmapped.json）を既6.3意味領域へ閉登録する。作者候補の許可exact4はscripts/core_guard.py、tests/test_core_guard.py、.github/workflows/ci.yml、tests/test_ci_wiring.py。新25pairのstrict suffix外層だけを足し、旧schema比較2/PR196全3/既各層と検出・拒否条件・code/test前置commit要件を保持する。領域別完全性・欠落/余剰/順序/誤area/削除/guard_only迂回の拒否を検査する。実core-areas.json登録はこのcode/testを独立確認し先行commitしてからrootが後置する。
CIは旧advance_stage_a_from_s0とcompleted_stage S3/publishableFalseの実検査を保持し、その後の0040単独upgradeを既resume_current_product_after_placement(owner_dsn=同owner, applicator_dsn=同DB admin)一回へ置換する。同入口が旧0039実検査後の同ownerTXで固定0040/0041を配置し全schema/index/rules/catalogを検査する。completed_revision==0041_stats_fact_versions/publishableFalseを実際の公開定数に完全一致させ、後段current --check-heads/alembic checkを維持する。中間0040をcurrent入口へ与える経路/汎用head upgrade/成功mock/検査省略は禁止。CI配線試験は同DB/主体/実入口/固定版/順序と欠落の対向を保つ。source code/test修正と実JSON/正式deriveは分離し、CI sourceが変わるtenant/corpus等の正式後値は全source固定後にrootが導出する。作者はcache-only、別非作者が当該追加差分を確認する。D11/生成物/計算意味は本exact4へ混ぜない。


同版owned検証の結果（2026-11-06 JST、PO委任Codex /root記録）: 固定41d13638c336ef16ca0bb1d4e8e5410e8b2f7679で実HTTP保存/実RRRO読取/原子性の既3moduleを使い捨てPG17.11へ実行し3成功186.11秒。source HEAD/tree/index前後一致、共有DSN非継承、自前container撤去をcache native-foundation-save-read-fault-r1-result.jsonに固定した。旧bcee証拠だけでなく今回のdevelop51b取り込み候補そのものを実証したが、画面成績/API公開/正式D11/27指標/全MVP成功ではない。CI追補内のrevision文字列誤記を真正CURRENT_REVISION=0041_stats_fact_versionsへ整合し、実装定数/期待値は変えない。


core登録閉包のexact1追補（2026-11-06 JST、PO委任Codex /root判断）: authorのordinary-payload-registration-evidence.jsonを実照合し、backend/tests/test_stats_native_connection.py:15/60のDB seed→静的ImportFrom閉包がbackend/tests/test_ordinary_pitch_payload.pyを検出する一方、現5area全て未登録で、当初25pair仮合成後もこれ1pathだけ欠落することを確認した。新有限外層を25から26pathへ限定拡張し、この1をsync-protocolへ追加する。新意味・検出除外ではなく既DB schema参照閉包への登録追随である。現4areaへ既登録のtest_terminal_pitch_payload.pyは新外層へ重複追加しない。旧HTTP歴史fixtureの完全性検査は真正固定_terminal_expected_additionsと新26宣言を明示合成した検査fixtureへ追随し、元scanner全件検査/旧期待/全負対向/各旧validator ASTを保持する。無条件suffix切捨てや欠落skipで通さず、全26と旧各層の独立確認後にrootがcode/test先行commit→JSON後置を実施する。
