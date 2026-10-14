# U-R1 / TSK-392 作業ログ（2026-10-15）

- `git fetch origin develop` 後も `origin/develop=e6e1a867f88bbdac90f2be9bed20dff900eec866`。U-R1専用worktreeは文書だけ未追跡。TSK-550 worktreeは `34b0e1a4`、承認済み計画のステップ2完了・ステップ3個別ゲート起案、固定実行器はステップ4で未実装。U-S1/TSK-550/認可面の所有worktreeは変更しない。
- PO方向指定: TSK-550共有固定関数実行器を先行統合、U-R1はRG1専用2登録を後載せ、TSK-550全体完了待ちなし。製品コード・凍結資産変更は未承認。
- `shared-function-executor-addendum-proposal.md` にA=TSK-550所有の共有実行器・製品登録0件封印、B=TSK-550段階A最初の登録、C=U-R1 RG1専用2登録の順序を起案。A/B分割はTSK-550計画の正式追補とコア計画レビュー・PO承認が要る。担当へNotion `3f993b75-e687-81da-9f7e-001d84a4684b`でA/Bの所有・PR/コミット・最初の登録との整合を照会。分割不可なら現行ステップ4統合後にU-R1へ接続する代案を明示。
- U-S1には③-a/⑧のPort署名・呼出位置・PortWriterから同一transactionの `run_function` を呼ぶ口と失効条件の3点をNotion `3f993b75-e687-81d6-9c29-001db71d4381`で再照会。実Port接合と結合試験は新ステップ6のまま。
- 現行 `authz_private` schemaはappのUSAGEを明示拒否するため、前日の同schema配置候補を撤回。[RG1認可審査資料](../features/ur1-recording-rights/rg1-authz-review-packet.md)へ別`rg1_api` schema、既存management ownerの限定列SELECT/UPDATE、FORCE RLSとfunction_only分類、appの読取2関数限定EXECUTE、復元側UPDATE関数のapp拒否を候補として整理。TSK-424へNotion `3f993b75-e687-8104-a1b5-001d5f9979e4`で4項目の採否を依頼。GUCを偽造不能な認証とは扱わず、DB直接EXECUTEのロック待機を残余として審査する。
- 方式・接続面の受理と7.7実値受理は分離。repository/base-allowlist/runtime-authz等のrevision/digest、7.7 before/afterはTSK-550共有実行器の統合後の実基線から算出し、正式反映前に提示する。未承認資産・製品コードは変更しない。回答待ちの担当と判断はClaude申し送りへ記録した。

## 候補の独立査読と採否

- 読取専用の別Codexセッションが、追補案SHA256 `0e4fd2ac0b2b854b838d2f7cef7897df9bf3914550432088a96bdff8b0fdf29b`、認可資料SHA256 `9a04a32f841bb0f032ab1d90d037081839bb1115ce8935352eca3b0e786c36d9` を確認して敵対査読。結果は **P0 1 / P1 6**。修正後差分の追加査読は未実施。
- P0は新規`rg1_begin_restore()`の既定`PUBLIC EXECUTE`によるapp直接閉鎖。**採用**: 新2から当該関数を除外し新5の別承認へ送る。将来の作成transactionでPUBLICを剥奪し、appを含む実効ACLをexact-set検査する。
- P1のowner表schema USAGE漏れ、管理関数ownerの過大権限を**採用**: 専用owner候補、表schema USAGE・必要列ACL・FORCE RLSの一組のDB検証へ改める。新role/ロール総数改訂は別ゲート。
- P1のTSK-550の0件中間PR・PR/7.7単位の衝突を**採用**: 旧A/B/C案を撤回。TSK-550現行ステップ3→4を初回段階A登録まで先行PRで統合し、U-R1を次の別PR、TSK-550ステップ5以降を後続PRとする。TSK-550担当受理、1 PR→複数PRの計画追補・レビュー・人間承認待ち。
- P1の非テナント`function_only`不整合を**採用**: RG1一表の特別事実、owner集合、分類正負例、正本3-2改訂を7.6/7.3判断へ送る。P1の古いopen行の起動時閉鎖強制点不明、app直接`FOR SHARE`による無期限待機も**採用**: 強制点、transaction寿命、復元lock_timeout/再試行上限と失敗時閉鎖動作、3接続負例を認可/運用担当の未解決判断として明示。数値や実装点を仮決めしない。
- 最新候補は[追補案](../features/ur1-recording-rights/shared-function-executor-addendum-proposal.md)と[認可審査資料](../features/ur1-recording-rights/rg1-authz-review-packet.md)。この査読を承認や7.7受理と読み替えない。U-S1 Port実接合は新6。製品コード・凍結資産・受理履歴は未変更。

## 担当への修正連絡と受理状況

- TSK-550担当へ0件中間PR案撤回・現行ステップ3→4を段階A登録まで先行PRとする修正案をNotion `3f993b75-e687-81f1-bac5-001d96f9f48b`で送付。担当受理、PR所有、計画追補、7.7単位の回答待ち。
- TSK-424認可担当へP0/P1採用後の専用owner・PUBLIC剥奪・起動時閉鎖等の具体判断を`3f993b75-e687-81b0-bd8f-001dd9b76faa`で送付。項目別回答待ち。
- U-S1担当のNotion `3f993b75-e687-8116-a83e-001d29547fdc`を確認。2署名`read_rg1_before_d5(writer: PortWriter)->bool` / `check_rg1_before_commit(writer: PortWriter)->bool`、結果型、認可後/行ロック前のPortWriter発行、③-aをD5/試合行ロック前、⑧をゲーム→世代ロックと全書込後・commit前、P1/P2/P4/P5/P3両ゲート、内部配信は③-aだけ、scope終了時失効を**担当受理・宣言済み**として記録。取得本文は固定関数の同一transaction口の節で切れたため、その1点だけ`3f993b75-e687-81f9-9aea-001dd644570a`で補足を依頼した。Port実接合試験は新6を維持。
- TSK-392 Notion `3f993b75-e687-817c-8e76-001d8919018b`にClaude調整役向けの未回答項目と担当・コメントIDを記録。TSK-550担当、U-S1担当、TSK-424認可担当の返答は代記しない。

## 第3回・P0限定の独立差分査読

- 6.3の「第2回にP0が残る場合」の1回を使用。候補作成に関与しない別Codex読取専用セッション`01a13b02-578f-7b63-bc8e-e7aac5443862`が、追補案SHA256 `05d81c8b83b164df8bd5782ddd5ff6a01272d18679bd4654a68d0fa04a722fce`、認可資料SHA256 `6c836effbf70cc03919dbb9cb1964eb78fe5818a16c0d6315471e1d5fac5c94f`を照合。第2回P0の修正差分と直接影響だけを読み、**可決・P0 0件**と判定。旧`PUBLIC EXECUTE`迂回の解消と新P0なしを確認した。P1/P2の再レビューは行っていない。
- 3回の自動枠は終了。第2回のP1を採用して候補へ反映したが、起動時閉鎖強制点・待機上限・分類などの担当判断は未決。担当受理・具体DDL/認可資産の個別人間承認前に新ステップ2へ進まない。

## U-S1 Port・C1 接続回答と意図 ID の A-1 照合（2026-10-15）

**出所**: U-S1担当worktree `/home/ymdms/projects/pitchlog-worktrees/feature-us1-sync-apply-core` の`docs/features/us1-sync-apply-core/plan.md` 8節と`docs/worklog/2026-10-08-us1-sync-apply-core.md`「他単位との接続契約」。HEAD `43f8ad0114015bc415d7e7d9b58081ecfc8c4f6c` を読取確認。U-R1から同worktreeは変更していない。前段のNotion回答は③の途中で切れていたが、担当が計画・作業ログに固定した全文を確認したため、以下を受理記録へ引き継げる。

| 宛先・項目 | 担当回答と採否 | 残条件 |
| --- | --- | --- |
| U-R1: RG1 Port署名・呼出位置 | U-S1は`read_rg1_before_d5(writer: PortWriter)->bool`（③-a非ロック）と`check_rg1_before_commit(writer: PortWriter)->bool`（⑧同じsingletonを`FOR SHARE`）を**採用**。True=通過、False/Port例外=全scope取消のB7、P3はB10。PortWriterを認可後・行ロック前に発行し、③-aを試合行ロック/D5照合前、⑧を試合行→世代行のロックと全書込の後・commit直前に呼ぶ。P1/P2/P4/P5と進行中・終了後P3に両ゲート、内部配信には③-aだけを置き閉鎖中は延期 | U-R1はRG1状態行とexact `FOR SHARE`関数を個別承認で実装。Port実接合試験はU-R1新6。失敗/ロック待機の具体分類は別途固定 |
| U-R1: 固定関数の同一transaction接続 | U-S1は`PortWriter.run_function(token)`を**条件付き採用**。TSK-550の固定関数exact token型だけを受け、同じscopeの`_TenantTransaction.run_function`へ委譲。関数名・SQL・Sessionは受けない。PortWriterは適用核だけが発行し、commit/rollbackで失効、失効後の`run`/`run_function`は拒否 | TSK-550実行器のdevelop統合、token型のimport/port_guard契約、`sync/ports.py`のコアレビューと人間逐行確認。PortWriterの変更・実接合はU-R1新6 |
| C1/TSK-528追補: 自テナントprofile読取 | U-S1は`CAP:tenants:read`の`TenantProfileReadToken`/`TENANT_PROFILE_OPERATIONS` 1件を**採用**。`tenants.c.id = :tenant_id`を基底の文脈束縛で満たす登録は#132 headで検査済み。C1の非共有部分を先行し、共有registry/凍結資産は#131→#132統合後に追随する順を採用 | `tenants`のRLSとapp SELECTで自テナント1行を実DB読取できることはC1のDB試験待ち。統合前の未登録状態で実endpoint完了とは扱わない。U-R1はC1/U-S1の共有ファイルを変更しない |

**A-1の「イベント識別」の同一性**: U-S1承認済み計画7節A-1はD1付き経路の意図IDを`<トリガー>:<イベントのD5>:<範囲>`と記す。一方、ステップ7実装の`record_d1_intents(scope, game_id, d5)`は受け取った`UUID d5`を`str(d5)`にして`derive_sync_intent_id`へ渡し、結果は`sync:<同じD5>:<scope_kind>`（`backend/src/pitchlog/sync/invalidation.py:117-135`、`intent_ids.py:11-21`）。呼出元`prefix_path.py:729`が渡す`d5`は当該`event.d5`から作った同じUUIDで、D3前進時だけ記録する。別のイベントIDへの置換はない。

**再送・一意性・経路判別**: `prefix_path.py`は保存済みD5を意図生成より前に分類し、同一内容の再送では保存結果を再掲する。DBのD5台帳は`PRIMARY KEY(tenant_id,d5)`、意図表は`PRIMARY KEY(tenant_id,intent_id)`。B03は同期経路で「1回の論理無効化につき範囲ごとに1行」を要求し、トリガー1/3/4の番号を別行の区別子として要求しない。実装はD1付き経路でD5ごとに5範囲のIDを1集合だけ作る。`sync:`は同期所有の意図をB06の非同期トリガー意図から分ける固定接頭辞で、非同期tokenは`sync`開始のトリガー値を拒否する。P3は`sync:<game UUID>:<世代>:<D1>:<確定版>:<範囲>`であり、D1側の単一UUID識別とは構造が異なる。既存試験は同じD5再実行で5行のまま、別D5/範囲は別ID、B06混在行は同期配信から除外することを検査する。したがって**A-1のイベントD5と実装のD1側イベント識別は同一で、差は接頭辞の表記**と判定する。ただし実経路の全故障シナリオはU-S1側の残ステップで検査する。

**A-1最小追補の採用方針（U-S1反映待ち・要計画ゲート）**: 2026-10-15のPO指示に従い、U-S1計画7節A-1の表記だけを`<トリガー>:<イベントのD5>:<範囲>`→`sync:<イベントのD5>:<範囲>`へ置換する方針を採用。理由として「`sync:`は同期経路の所有判別、**トリガー1・3・4で同じD5・範囲につき1意図**、トリガー番号はIDに含めない」を明示する。再送・一意性・D3発火・5範囲・P3のV10/確定版規則・B06・DDL/契約資産・配信所有は変更しない。承認済みコア計画本文の追補はU-S1担当が実施し、計画レビュー・人間承認の記録を残す。U-R1は他担当の計画・製品・共有資産へ変更を加えない。

**Claude向け申し送りの置き場**: 今後は各担当の**コミット済み作業ログ**内の節へ集約する。消失した`docs/worklog/2026-10-13-claude-mvp-handoff.md`を復元済みとは扱わない。

**担当への共有**: U-S1/TSK-391へPort全文確認とA-1最小追補候補をNotionコメント`3f993b75-e687-81df-ad8e-001d5ec61e23`で通知。C1/TSK-528へ読取tokenの受理、#131→#132後の共有資産統合、残るRLS/SELECT実DB試験を`3f993b75-e687-810c-b894-001d12de5510`で通知。両担当の計画・worktreeは変更していない。

**PO方針と残条件の固定**: 上記A-1最小追補の採用と「トリガー1・3・4で同じD5・範囲につき1意図」は2026-10-15の依頼者指示による。U-S1担当へ確定方針とコア計画ゲートをNotionコメント`3f993b75-e687-8129-9c42-001d47f18059`で伝達した。U-R1のPort署名・呼出位置・同一transaction口の**回答待ちは解消済み**。U-R1新2はTSK-550共有実行器Aの統合とRG1専用DDL・認可・凍結資産の**個別承認**を残す。方式・接続面の受理を実revision/digestの7.7受理へ流用しない。C1のRLS/SELECT実DB読取試験はC1担当の後続工程、U-R1の実経路結合試験は新6に残す。既受理事項は再照会しない。
