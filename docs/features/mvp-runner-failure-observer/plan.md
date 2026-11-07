---
feature: mvp-runner-failure-observer
status: active
branch: feature/mvp-runner-failure-observer-20261107
承認: PO委任root（2026-11-07 JST、対象670e61f1）
計画レビュー周回: 1
---
# 通常経路の失敗境界だけを観測する最小追補

起点 `4a0e04b43b74cadd6ea1193d7911db6b55a72e31`。run14は全行trace OFFで正常NP保存/GETを通過し、同D5再送503と後続create503で停止。未知の原因を成功へ置換せず、RG1/lease/HTTPの既private境界を分離する。

編集は `backend/tests/db/test_runner_operations_screen_e2e.py` と本planだけ。専用worktree/branchを使用し、主WT/製品src/SQL/正式assets/期限/guard/テスト期待は変更しない。純probeとpacketはcacheへ保全する。

| ステップ | 内容 |
|---|---|
| 1/1 | test bootstrapへ相互排他の低負荷failure modeを追加し、元call/return/exception identityを保持するwrapperと閉metadataの純正負を固定する。 |

`rg1._require_open`、`_TenantTransaction._ensure_rg1_lease/_assert_rg1_lease`、`_BindingLease.check` の元関数を一度だけ呼び、例外時だけ記録。leaseは失敗時のclosed/expired boolと相対elapsedだけ。HTTPException handlerは503だけを同条件で記録し、元handlerへ返す。

出力は固定stage・最大8件の例外class/module・pitchlog末端function/lineのみ（lease bool/相対msを除く）。例外cycle/未知moduleや不正識別子は閉処理。原文/SQL/params/locals/資格/ID/絶対時刻/期限原値は出力しない（期限値はexpired bool算出だけの内部参照を許す）。総出力上限80件とtruncated明示。正常時に追加DB/RPCを呼ばない。

低負荷modeは旧app全行trace/worker exec-siteと同時指定を拒否し、sys.settrace/threading.settraceを使用しない。小さなcache純検査で元return/例外identity/呼出数、秘密sentinel非出力、閉型/件数/503限定を確認。root非作者確認後の新固定HEADでowned run15を1回実施し、source前後同一・mode/codeSHA・cleanupを固定する。実走はroot採用通知まで開始しない。

計画採用: rootが670e61f1 / plan SHA74ebe4fbc292636eac36f3f1f1c1aa73c4db2a2ae48c1a952aa550bf22a5c246を全文確認しP0/P1なし、PO委任Codex主担当判断でstep1採用。元handler登録前のmodule実体を置換し、同じhandler一回とreturn/例外identityを保持する。

同日root追加委任: scope終端のSession.close後に呼ばれる `_GateLoan.release` も、元呼出保持の失敗時wrapperで固定stage/class/function/lineだけを観測する。backend実在確認と解放順は変更せず、borrower PID消失raceは静的仮説として実因と分ける。

実装記録: failure-only bootstrapは登録前の実module/methodを元呼出保持でwrap。cache純probe9群（return/例外identity・GateLoan finally・HTTP実登録/503限定・chain8/総80・秘密sentinel非出力・mode混在拒否）成功、Ruff/Ty0、collect1。製品4a全byte差分空、owned/実DBはrootの最終source採用後に別実施する。
