---
feature: mvp-runner-failure-observer
status: review
branch: feature/mvp-runner-failure-observer-20261107
承認: 未（PO委任rootの対象版確認待ち）
計画レビュー周回: 0
---
# 通常経路の失敗境界だけを観測する最小追補

起点 `4a0e04b43b74cadd6ea1193d7911db6b55a72e31`。run14は全行trace OFFで正常NP保存/GETを通過し、同D5再送503と後続create503で停止。未知の原因を成功へ置換せず、RG1/lease/HTTPの既private境界を分離する。

編集は `backend/tests/db/test_runner_operations_screen_e2e.py` と本planだけ。専用worktree/branchを使用し、主WT/製品src/SQL/正式assets/期限/guard/テスト期待は変更しない。純probeとpacketはcacheへ保全する。

| ステップ | 内容 |
|---|---|
| 1/1 | test bootstrapへ相互排他の低負荷failure modeを追加し、元call/return/exception identityを保持するwrapperと閉metadataの純正負を固定する。 |

`rg1._require_open`、`_TenantTransaction._ensure_rg1_lease/_assert_rg1_lease`、`_BindingLease.check` の元関数を一度だけ呼び、例外時だけ記録。leaseは失敗時のclosed/expired boolと相対elapsedだけ。HTTPException handlerは503だけを同条件で記録し、元handlerへ返す。

出力は固定stage・最大8件の例外class/module・pitchlog末端function/lineのみ（lease bool/相対msを除く）。例外cycle/未知moduleや不正識別子は閉処理。原文/SQL/params/locals/資格/ID/絶対時刻/期限原値は読取・出力しない。総出力上限80件とtruncated明示。正常時に追加DB/RPCを呼ばない。

低負荷modeは旧app全行trace/worker exec-siteと同時指定を拒否し、sys.settrace/threading.settraceを使用しない。小さなcache純検査で元return/例外identity/呼出数、秘密sentinel非出力、閉型/件数/503限定を確認。root非作者確認後の新固定HEADでowned run15を1回実施し、source前後同一・mode/codeSHA・cleanupを固定する。実走はroot採用通知まで開始しない。
