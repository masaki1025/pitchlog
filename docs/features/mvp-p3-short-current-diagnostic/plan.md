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
