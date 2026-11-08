---
feature: mvp-rg1-scope-runtime-lifetime
status: active
承認: PO委任Codex主担当/root（2026-11-08 23:22 JST、対象bf9ed4fe/56e92d8134c1d4f06d554994dcaf988f694c59cb37b1d41967a47e9c6010e9ac）
重さ分類: コア領域
branch: fix/mvp-rg1-scope-runtime-lifetime-20261108
created: 2026-11-08
計画レビュー周回: 1
---

# RG1借用終結まで同scopeの実runtime参照を保持する

基点6c52fd2b3b665b825d9c4aaf4aabc5d3ab03c732。実26画面run1は23保存後24件目alias前503、authority側fresh_controller EOFを観測した。client側の先行停止原因は未捕捉で、本仮説を今回の実因とはまだ断定しない。

現transactionはinner終了時にruntime登録をpopし、PGcommit/rollback→Session.closeを終えて戻り、outerでloan.releaseする。scopeごとのEngineを保持するSessionがこの間にGC可能となると、releaseの実backend生存確認前にpool接続が閉じ得る。正常borrower不在を許すのではなく、同runtimeを終結まで保持する。

編集はbackend/src/pitchlog/repositories/transaction.pyの_TenantTransactionScope.__exit__（実クラス名は現物に従う）と専用backend/tests/test_rg1_scope_runtime_lifetime.py、本計画、必要な専用backend/tests/db/test_rg1_scope_runtime_lifetime_owned.pyだけ。共有SQL/authority/RG1プロトコル/設定/asset/台帳/他WTは非編集。rootから当transaction pathの唯一writerを委任済み。

- outerは元runtime tupleをloan.releaseまたはabandon終結までローカル強参照する。finallyで解放し、恒久global保持・新engine共有・pool構成変更をしない。
- 元commit/rollback/Session.close/handle失効/解放時backend実確認/未知abandon/例外identityとcauseの順序を保持する。新RPC/SQL/TTL延長/失効成功化なし。
- gc.collect/weakrefでreleaseとabandon時のSession/Engine生存、終結後の参照解放を正負で検査する。まずpureで従前の寿命不足を区別し、一般scope全体の可用性成功とはしない。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 最小保持とGC正負を固定 | 元終了順/identity保持、GC下release/abandon時だけ元runtime生存・終結後解放、対象静的/pure成功 |
| 2 | root確認後のowned短scope終結 | 共通lock/共有DSNunset/固定源で実backend生存と正常終結を確認し、旧23件失敗の実因とは別記する。全26反復は行わない |

新しい観測が必要なら元call/return/error一回を保持する失敗限定metadataのみ別packetへ固定する。PGはrootの固定差分確認と明示許可まで開始しない。
