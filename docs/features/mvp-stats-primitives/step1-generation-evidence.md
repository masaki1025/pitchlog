# ステップ1(b) 実生成候補と検証範囲

基点は `fe9d6a1b07c618d4f454b317a6a8b975dc25790f`。末尾の主担当指示と受理済み55期待に従う操作単位の候補で、ステップ1全体・T5/T6正式供給・全27成績の完成ではない。共有manifest、display-binding、正式contracts、source registry、同期/API/DB、refsは変更していない。

## 供給する実装

人手の寄与式は `backend/domain/play-export.model.json` の26 metricに一度だけ定義し、`stats.model.json` は共通calculation ID・canonical SHA256・ID順序・型を参照する。閉演算はtyped ref、boolean、非負整数、guard、加算、等値、有限lookup、有限collection reducer。未知演算・未知参照・不一致hash/型・余剰キーを生成前に拒否する。期待case/property catalogを生成入力へ渡さない。

生成先はPython/TypeScriptの単一遷移facts、SQL2件、typed SQL受け口、整数formatter2件の7ファイル。式をtarget言語へ直接コンパイルし、第二のruntime式interpreterを追加しない。構造path取得/型検査/整数codecは汎用処理だけ。既存公開BackendInput/Calculation型・旧target・旧拒否テストは保持し、新typed経路ではcontext echoや固定SUMを使わない。既存legacy model全体を実計算へ移行済みとは述べない。

PA/AB/H/2B/3B/HR/BB/HBP/K/SH/SF/妨害出塁/塁打、球数、実効outs、投手K/BB/HBP/被安打/被HR、走者別得点/RBI/失点、盗塁、失策を共通宣言から生成する。T1の旗・有効数量・責任IDを再野球判定しない。23 flagsを閉じ、未完PA・非投球・invalid run・未供給RBIを0補完しない。PA行は同じRBI寄与と欠測状態を参照する。走者集合は最大4、盗塁集合は最大3の単一遷移だけで、製品側の全event集計APIは設けない。D02〜05はnull/decision_pendingを保持する。

## SQLと真正sourceの境界

SQLは候補relation `public.stats_primitive_facts` / `public.stats_fact_versions` に同TX保存される受理済みT5 amount/state/creditを消費する。生T1 documentから寄与を再形成しない。tenant/game/event、D1/D2、slot/play版、現在モデル、有効fact版、可視game、終了・確定pointer・選択キーをWHERE/JOINへ宣言し、DB GROUP BY/SUM/windowを生成する。欠測metric coverageはsource_unavailable/NULL、providerが全件計算済みと証明する空は0として区別する。window後のkeysetはD2・event・metricの全tieを含み、初回NULL cursorを許容する。

relation名/列/DDL・RLS・真正provider receipt・checkpoint/ledger照合・索引・実DB SQL適合/EXPLAINはroot後段のtyped binding正式化対象であり、現DBに存在すると主張しない。JSON合格/UUID/hashやwrapper packaging印は認可ではない。fixture resolverによるsource拒否は実provider認可の証明ではない。DB・共有DSNを使用していない。

## 整数と資源境界

共通整数は任意精度canonical非負整数で、128桁の一律意味上限は設けない。Python codecは9桁chunkで変換し、globalの4300桁制限設定を変更しない。129桁/5001桁をNode BigIntと比較した。型で既に有限のouts 0..3だけを変換前の文字長/範囲検査で拒否する。float/bool/unsafe Numberへの近似や0/NULLへの置換はしない。

SQL受け口の必須引数 `maximum_integer_chars` は出力資源予算で、上限超過は `OutputBudgetExceeded`。既定128桁やドメイン上限ではない。呼出側の予算値・HTTPエラー/容量運用は未採用で後段レビュー対象。受理済み候補input/output契約自体の文字列上限をこの変更で緩和/改訂していない。利用経路ごとの予算と契約上限の接合は正式binding時に確認する。

## 検証結果と実証限界

共有DSN `PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN` / `DATABASE_URL` をunsetしてpure pytestを実施。新テスト109件と旧生成器/formatter/schema等81件の合計190件が成功。55独立期待は手指定のまま、生成Pythonと実Nodeの結果を比較する。source/schema拒否ケースはfixture resolverで停止し、T6ケースは有限fact fixtureのadd/formatter比較でありSQL実行ではない。最大2遷移のtest harnessは製品の全件集計ではない。

26 metricそれぞれのquantity+1非等価変異は独立正例で全件検出した。この有限変異面を全演算・全3層の変異網羅と読み替えない。生成7ファイルのbyte再現、未知/循環参照等拒否、23 flags余剰、列型、0/NULL、Decimal整数、資源予算、巨大整数、SQL shape/cursorを検査した。Ruff/ty、生成TSとwrapper specのPrettier/ESLint、vue-tsc、Vitest6件が成功。既テストは編集していない。

原典は受理済み `primitive-{input,output,cases}.candidate.json` のsource/expectation参照と `step1-contract-evidence.md` のA-1 OUT3/RBI適用域、A-2責任、D1/FR-022の指定を継承する。製品artifact/生成器から期待を転写していない。候補モデル・生成器・生成物のSHAは `backend/domain/stats-manifest.json` とcache packetへ固定する。

次の独立実装単位はroot採否後の真正provider/T5保存binding・relation正式化・隔離DB SQL実行比較。現T1全操作やDB不足を本pure生成の開始待ちへ戻さず、未実sourceは非成功/pendingのまま保全した。本人確認/独立非作者review/正式採用は本作者の検証で代替しない。
