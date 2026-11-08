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

## step1候補と純対向

同じGC正対向をGit6c52の旧__exit__だけへ束縛すると、Sessionがloan終結前に消失し1failed0.16秒。新sourceは実SQLAlchemy Session/QueuePool Engine（SQLite、PGや認可成功ではない）をrelease/abandonまで保持し、終結後には弱参照が回収される。正常/body/precommit/release/closeの5新条件と既RG1を合わせ55passed2.30秒。元例外identity/handle失効/commitrollback/close→releaseabandon順を確認し、旧prefixと既終了tail全ASTが不変であることも機械比較した。全backendTy/対象Ruff0。今回の23球EOFの実因や実PG修復成功とはまだ記録しない。

## step2の実走候補（起案時PG未実施）

PO委任rootが5ab1固定源を全文確認し、2026-11-08 23:31 JSTにstep2を採用。既実UID20003/C2/正常49の初球HTTPbootstrapだけを再利用し、新規作成→端末登録→開始→一球→GETへ絞る。試験だけのweakmapにscope入口の実Session/Engine弱参照を結び、実GateLoan.release直前にGC→元release一回を行う。controllerの元backend生存照合/期限/未知拒否は変更せず、監査は終端後owned readonlyのみ。collectorが失敗しても元return/例外identityを置換しない6純対向と元5条件の11passed2.74秒、型/Ruff0・collect1・脚本2compile。実PGはroot固定差分確認/実行許可待ち。

失敗時counter追補: rootの既scope委任内判断で、短脚本が失敗した場合も閉じた非負counter8欄だけを一回出力しbare raiseする。snapshot/出力失敗は元例外を保持し、ホストも元rc失敗を成功化しない。元GC probeと製品sourceは5338と全byte不変。追加3対向を含め14pure/型/Ruffを確認。実行形態は実UID20003のASGITransport＋実app API/実C2認証・記録権・PGであり、画面や実ネットワークHTTPSの成功証拠ではない。


## step2の短owned実測結果

root非作者確認とPO委任採用後、e828bdf92d1d78a567b8232a01072c3a89fffb3eの専用detached shadowで1回実施。pytestは1passed74.20秒（wrapper75.059秒/rc0）。実UID20003＋ASGITransportの実app/実C2認証・記録権・ownedPGで、新規試合（fixtureとは別）の作成201→開始200→初球受理200→GET200/1ボールを確認。実release直前GCは3scope/3GC/3release成功、Session/Engine欠落・release失敗・metadata失敗は全て0。物理play/event/slot各1、固定source4921ファイル前後一致、新running containerなし、通常cleanup後commonlock再取得成功。実画面/ネットワークHTTPSや旧23球EOFの実因・根治を証明したとはしない。全26は実行していない。

証拠は `/home/ymdms/.cache/pitchlog/rg1-scope-runtime-lifetime-owned-20261108/run1-short-gc/`。REPORT.md SHA b7d1f9ad6ddce93551f7c709b88f64d8fbd2989f4705ff30064c3abe4ce3a8c2、manifest.json SHA 883e36b3b8a8a5b1ebd92a32e74613e9a7d5f476ef488c1e0b42d10a438d79fe。候補の短scope完了と正式採用/旧障害解消は分離し、rootの統合判断へ渡す。
