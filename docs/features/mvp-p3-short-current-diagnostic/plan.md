---
feature: mvp-p3-short-current-diagnostic
status: active
承認: PO委任Codex主担当/root（2026-11-09、短P3正常49 route切分けのtest-only候補を採用）
branch: feature/mvp-p3-short-current-diagnostic-20261109
created: 2026-11-09
計画レビュー周回: 1
---

# 正常49の短P3 APIで共通503原因を切り分ける

起点0a233123（71/c275+GC+位置3guard修復）。画面26run2はtarget26 GET200/原要求耐久保存→P3 POST503、controller/authority failures[]、DB26のまま/binding27closed。既保存ログにSQLSTATE/DBclass/frameが無く、causeは未確定。

編集はbackend/tests/db/test_p3_short_current_diagnostic.py＋専用pure試験と本計画のみ。実UIや26paged成功ではなく、実UID20003/ASGI app/実認証C2/記録権/PGの約2球で共通routeを切り分ける。既三球scriptの操作のみ再利用し、旧通常/P3 trace（diag文脈/原primary依存）は除去。正常49fixtureの公式配置だけで、candidate SQL/control/ACL/roleの後付なし。

_apply_e1_p3実aliasを元一回/同return・同例外identityでwrapし、失敗時だけ最大80件/chain8の閉class/5桁SQLSTATE/固定source site、B10等の有限戻値だけ保存する。rawmessage/SQL/params/ID/資格は出さない。通常処理追加DB/RPC0、期限/guard/SQL/生成核を不変更。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 短診断と透明probeを固定 | 元call/return/error/metadata失敗の純対向、脚本compile/collect/型Ruff、固定hashをrootへ |

PGはINTの終了とroot許可まで実施不可。短経路で不成立なら同class/siteへ修復を絞り、成立なら26paged固有へ分離。旧26試験/別HTTP T2T4の条件は削減せず未成立を維持する。


## 候補検査

短caseは実新規作成/開始→v3通常2球→target1→P3 POST→同current再取得に限定し、旧26/fault本体は不変更。旧ordinary/P3診断blockは全文除去してmessage_primary/message_detail/diag.context/format_exc依存0。元alias1回・戻値/例外identity・print/metadata失敗非干渉・80cap/secret0の8pure4.29秒、全Ty/対象Ruff0、collect1、脚本compile成功。初回純6pass/1failはUID確認文字列のgeteuid表記を誤った試験期待であり、実UID条件を変えず是正。型検査のfetchone None/exec namespace callableの対向側2診断も実型/FunctionType確認へ是正し、失敗logを保全。

実PG未実施。probe SHA6b63f6e65b9566d90876066e3d3f7b1e4a8539ca3bb0748c662d0d99d93c63f9、操作脚本SHA6b34c2164df184c904d03a335ec86dd59b03e338bf3177ac4c128047aff5c3bb（25,235byte）。実UID20003のASGI経路であり、実画面/HTTPS/26paged成功を証明しない。


## 短run1の未到達と段階追補

48685083の短ownedは1failed80.56秒（wrapper81.448秒）。実1play/event/slot、binding2、P3alias失敗0で、P3には未到達。元脚本のassertで止まったがstage/statusがnullで具体箇所を保存できず、同条件再走はせず未観測として封印した。

root採用の追補として、全HTTP16静的箇所へ固定before/after stageとstatusを付け、失敗時は固定script名/行だけ追加する。全元await ASTの全値を前後比較し、元assert/期待を変更しない。metadata取得失敗を握って元応答/例外を維持する4群を追加。次にprefixが失敗しても情報を失わないよう、同じfailure-only wrapperを実F1/P3両aliasへ各1回付ける（B6/B7は既022aの閉結果、P3 B10/B11/B12）。元コール数/戻値/例外identity、secret0、80capを計18pure4.68秒、Ty/Ruff0で確認。生成脚本9717e555f1363172cbec719bef7a4831599a91aa638856192116192a7524da72、probe6bb33d36228831b29db6c7d9b5a2ddf8f0e9dd03fba11333433b8af44e55dbc5。AST整形によるUID確認の文字列期待だけの1failはAST比較へ是正し保全。

本候補は71f2726a/v5の固定製品で、rootmain859/v6とは分離。旧操作の入力ARTは実open_domain_host値、prior pin/規則/状態/participantsは直前の実GET、V7 sealは既唯一helperを使う。古い固定ARTへの書換やcastはしていない。旧assert/メタデータの意味が現固定製品に整合するかは次の正確なstage/行で照合し、無根拠な期待緩和は行わない。PGはrootload/INT後の明示順序まで禁止。


## 短run2のFK拒否とfixture追補

3ecの短ownedは1failed81.04秒（wrapper81.959秒）、正常2球目のhttp-07-posted-after503/P3未到達。F1例外IntegrityError→SQLSTATE23503、terminal_pitch_projection346の物理INSERTに到達。元P3 fixtureはcalled-pitch語彙を個別seedしていたが、短caseはnormal verticalのballのみを継承し、入力called-pitchを供給し忘れていた。rootが元fixtureと全値同じkey/category/display_name1行と事前EXPLAIN/存在全値照合を技術修復として採用。製品/認可/SQL本文/計算の修復とはしない。旧2runは保全、次PGはroot0050smoke終了後の割当まで待つ。


## 短run3の真正P3拒否と閉SQL位置追補

e4e8の短ownedは1failed92.46秒（wrapper93.363秒）、2play/event/slot・binding3、http-15-changed-after503。P3 ProgrammingError→InsufficientPrivilege/42501をpersist_p3_projection呼出（projection311/transaction510）で捕捉。source4929前後同一・cleanup、authority failures[]。P3受理/訂正は未成立。実行中にrootがcaseの200+prefix2だけでは受理証明にならない点を監査し、transport診断の範囲に限定した。

root許可の失敗限定追補: 実psycopg.Errorだけのdiag.contextをメモリ内regexへ渡し、既BODIESへ所属を検査した4関数の名前/数値行のみ返す。原context/引数/SQL/primary全文は保存表示0、65536字以上は閉拒否、最大8位置、未知名/行0/型不正を拒否。driver diag読取失敗も元例外identityを維持。計20pure7.03秒/TyRuff0。固定SQL行でguardを特定するまでT5/D03context不足を根因とは断定せず、TTL/権限/SQL条件は非編集。
