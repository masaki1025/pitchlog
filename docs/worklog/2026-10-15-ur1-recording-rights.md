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

## RG1個別承認資料とTSK-550順序の再照合（2026-10-15）

- **依頼者の最新方針**: `30ffaa71`のPort契約・A-1照合は完了として維持。A-1最小追補はU-S1担当へ引渡済み。共有実行器A待ちと並行してRG1専用2登録、owner/RLS/EXECUTE、状態行・起動時閉鎖を個別承認資料にする。実revision/digestと7.7前後値はA統合後。新6の実経路結合試験、D4の別ゲート、個別承認前の製品/凍結停止を維持。
- **TSK-550出所と採否**: `feature/ux1-fr014-rule-resolution` HEAD`ae380801`の承認済み`plan.md`には初回製品登録＝段階A resolver1件が残る。同branchの`shared-function-executor-split-proposal.md`と作業ログ末尾はA＝共有実行器0件、B＝resolver1件、C＝RG1専用2件を条件付き提案し、独立レビュー第1回P0=0/P1=5を全採用、第2回P0/P1/P2=0と記録。**正式追補・PO承認・個別資産承認の記録は確認できない**。U-R1の旧A＝resolver込み案との差を採用し、[旧案](../features/ur1-recording-rights/shared-function-executor-addendum-proposal.md)を履歴扱いに更新した。現行初回順序を守るならA→B→C、A→C→BにはPOの順序改訂が必要。レビュー済み提案を承認記録へ昇格させない。
- **RG1候補の具体化**: [個別承認資料](../features/ur1-recording-rights/rg1-individual-approval-packet.md)に固定token/SQL2件、単一状態表・seed、`rg1_api`と専用NOLOGIN/NOBYPASSRLS owner、`SELECT(singleton_id,state)`＋`UPDATE(singleton_id)`、owner専用SELECT/UPDATE policy・FORCE RLS、appの関数2件だけのEXECUTE、PUBLIC剥奪を候補化。PostgreSQL 17のSELECT/CREATE POLICY/RLS文書で`FOR SHARE`のUPDATE権・UPDATE policyとBYPASSRLSの強さを確認。新2の製品関数は古いopen行でも常にfalseを返す候補とし、安全な解除は新5へ送る。通常appの直接表操作・直接EXECUTE・余剰policy/権限の負例を個別審査する。
- **残条件**: TSK-550 Aの正式追補・レビュー・PO承認とdevelop統合、TSK-550 B/C統合順の正式記録、RG1表分類/role総数を含む正本7.6/必要な7.3、認可面・データモデル所有側の項目別採否、RG1個別DDL/認可/凍結資産の人間承認、A統合後の実revision/digest・7.7前後値。関数ownerの`UPDATE(singleton_id)`が`FOR SHARE`に足りること、direct EXECUTE待機上限、製品常閉と隔離open競合試験の境界は実DB試験・個別承認で確定する。新2製品コード/正式台帳は未変更。U-R1新6の実Port経路試験とD4方式は別。
- **担当への絞った照会**: TSK-550には後発A＝0件案を接続候補として採用した事実と、正式追補/PO承認/先行PRの共有資産7.7単位の記録所在だけをNotion`3f993b75-e687-8179-8ae7-001d84b8132f`で照会。TSK-424認可面には専用owner、列ACL＋SELECT/UPDATE policy、app直接EXECUTE、非テナント分類、起動/再接続閉鎖・待機上限の項目別採否を`3f993b75-e687-817d-b1c5-001d96fcfaa1`で依頼。既受理Port/A-1や固定function契約は再照会しない。
- **計画差分の追加発見**: 現行新2ステップ表は隔離openの「正常系」検査を要求するが、本候補の製品関数は古いopen行を含め常にfalseを返す。製品の正常open成功を新2と同一視すると起動時fail-closedを破る。新2では同じ行への共有ロック・復元UPDATE待機・rollbackと閉鎖拒否を隔離実DBで検証し、製品の正常open成功は新5の安全な解除後へ送る**最小計画追補候補**を個別資料へ明記。承認済みステップ表を本資料だけで変更せず、6.1/6.3レビューと人間承認を新2着手前に求める。

## TSK-550正式承認の追随と5件の承認一覧（2026-10-15）

- **出所**: TSK-550所有worktree`feature/ux1-fr014-rule-resolution`のコミット`8a270c2a4bcb41d067341b02cdd8171299a2e2a4`を読取照合。同コミットは`plan.md`、`step1-contract-acceptance.md`、作業ログへPOの2026-10-15分割追補承認を記録し、レビュー対象`ae380801`を明示する。A＝登録0件の共有実行器を別PRで先行、A後はB resolver1件/C RG1専用2件が相互に登録完了を待たない。旧初回resolver順序だけ本分割で変更。共有実行器の具体凍結資産・7.7とCの関数権限は別ゲート。この承認事実をU-R1計画・[個別資料](../features/ur1-recording-rights/rg1-individual-approval-packet.md)・旧追補案へ同期し、前節の「追補未承認」「A→B→Cのみ」は照合前の時点記録とする。
- **判断一覧**: 個別資料2節へ、(1)専用NOLOGIN/NOBYPASSRLS owner、(2)FORCE RLS・SELECT/UPDATE singleton policyと最小列ACL、(3)appの2関数限定EXECUTE/PUBLIC剥奪、(4)新2の`FOR SHARE NOWAIT`/全取消と新5の復元側待機上限、(5)隔離open fixtureでの行ロック正常試験と製品正常openを新5へ分離する最小計画追補、の各推奨案・具体差分・採用時の影響を一表に整理。owner/RLS/EXECUTE/待機上限/追補以外の既受理契約は再審査しない。
- **fixtureの判定**: 特権試験接続が隔離DBのRG1行を`open`にし、同じ行への直接`FOR SHARE`取得と復元UPDATE競合を検査することは可能。新2の製品用関数は古いopen行でも常にfalseを返す候補なので、開状態fixtureだけで製品operationの`true`成功を証明することは**できない**。試験用開状態を運用解除の承認・実装へ読み替えず、製品関数にtest-onlyバイパスを足さない。
- **残条件**: Aのdevelop統合、RG1個別判断の担当採否・必要な正本/計画レビューと人間承認、A統合後の実revision/digest・7.7 before/after。D4方式は別ゲート、U-R1実経路結合試験は新6。製品コード・正式凍結資産は未変更。

## 新ステップ2の最小追補候補とA統合確認（2026-10-15）

- 最新`origin/develop`は`9b8f9bc689fb70dc9d084fbad9758bf4b3c353fb`。TSK-550のA専用worktreeは`04988b82`でステップ1の文書・資産差分を固定中。祖先照合でAはdevelop未統合と確認したため、U-R1側の7.7実revision/digest・before/afterを旧試算から流用しない。別のU-R1 A/B/C文書同期worktree`7aea7b44`も読取照合し、現行ブランチ`19f28ba2`にある正式承認同期と重複編集しない。
- [新2最小追補案](../features/ur1-recording-rights/step2-minimal-addendum-proposal.md)を文書のみで用意した。現行ステップ表の隔離正常系は、開状態fixtureによる**行ロックの正常取得と復元UPDATEとの直列化**、製品2関数の**常閉拒否**に分離する候補。製品の正常open成功は新5へ移す。復元UPDATEは新2では隔離試験の特権接続だけで、製品の復元開始関数は新5に残す。試験用openを運用解除と扱わない。
- owner・RLS・EXECUTE・待機上限・隔離正常系の5判断を同案の承認一覧へ整理した。現行計画レビューは4周で、6.3上の追加独立レビューを自動で実施しない。追補差分と影響箇所についてPOの範囲・1回の裁定、独立レビュー、人間の計画承認、認可/データモデル担当の採否、具体的資産と7.7実値の別承認を要する。現行ステップ表・製品コード・凍結資産・正式受理履歴は変更していない。U-R1新6の実経路結合試験、D4方式は別ゲート。

## 6.3追加レビュー裁定用の提示（2026-10-15、裁定待ち）

- [新2最小追補案](../features/ur1-recording-rights/step2-minimal-addendum-proposal.md)へ、**追加1回・追補差分と直接影響箇所**の独立レビューを推奨として明記した。対象は追補案全節、現行計画の新2/5/6行、RG1個別承認資料2〜4節とRG1正本・U-S1受理契約との整合。6.1の正本違反・ステップ不成立・DoD不対応をP0/P1/P2で判定する。これはPO裁定の候補であり、レビュー実施許可や計画承認を推定しない。
- 同案の5項目を推奨案・承認後の変更対象資産・残判断の一表へ更新。開状態fixtureの直接SQLロック試験と製品関数の常閉試験は別証拠とし、製品open成功は新5に維持する。A統合後の7.7は実基線取得→C候補after算定→単一未マージPR記録の提示→個別受理後の正式反映→新9で最終head照合の順に固定。現時点の`origin/develop`は`9b8f9bc6`でA未統合。承認済みステップ表、製品コード、凍結資産は無変更。

## PO裁定と独立レビュー依頼の固定（2026-10-15）

- **裁定**: 依頼者は6.3の追加独立レビューを**1回**承認。対象は新2の最小追補差分と直接影響箇所（現行計画の新2/5/6、RG1個別承認資料の該当節、RG1正本・U-S1受理契約との整合）。6.1の正本違反・ステップの実行可能性・DoDとの対応をP0/P1/P2で評価する。5項目・具体的資産の個別承認ではない。追加周回の自動延長、製品/凍結資産変更、push/mergeは禁止。
- **レビュー対象識別値**: 候補コミット`6615889696c26e841be999d545dc136426cb8ced`。差分は`9da8416c..66158896`の追補案・作業ログであり、候補本体は`step2-minimal-addendum-proposal.md`。照合先は`plan.md`新2/5/6、`rg1-individual-approval-packet.md`2〜4節、`connection-contract.md`とsync-protocol 9-5。作業ログへの本裁定記録は候補の意味差分に含めない。

## 追加独立レビュー1回の結果・採否（2026-10-15）

- **実施**: `.claude/scripts/codex_run.py review adversarial -`、別Codexセッション`01a13f3b-4d97-77b0-965c-0951d7d5b504`、read-only、候補`66158896`と裁定範囲。判定は**否決 P0=1 P1=0 P2=0**。常閉製品関数と隔離fixture、復元UPDATEの新5移管、NOWAIT/復元側待機上限、owner/RLS/EXECUTEの別承認には追加指摘なし。受理範囲外の指摘なし。
- **P0の採否: 採用**。追補案の7.7手順は、候補提示(3)で未取得の「実承認者/日付」を要求し、個別受理(4)より先に実値を必要としていた。現行計画§4の「実記録から転記」「未承認を承認済みにしない」と矛盾し、新2の開始ゲートが成立しない。候補提示では承認者・日付を**受理待ち**と記し、個別受理後に実記録を転記して正式反映するよう最小修正した。影響は7.7の提示/受理順だけで、資産の許可範囲・ステップ表・製品実装は変えない。
- **反映差分の扱い**: このP0修正は承認済み追加1回のレビュー後の差分であり、独立再レビューは未実施。6.3の追加枠を自動延長しない。人間の計画承認時にこの最終差分を確認する。さらに独立確認する場合は、P0反映差分限定の別PO裁定が必要。frontmatterの`計画レビュー周回`は採用反映により4→5とした。

## 最小計画追補の最終確認・条件付き承認の成立（2026-10-15）

- **人間承認の出所と範囲**: 依頼者（PO）は`d6b306e0e09ae43a24fb7819ef0c0042dbe0bf1a`の5条件の最終確認を承認し、満たせば新2最小計画追補を承認すると指示した。owner、FORCE RLS、EXECUTE、FOR SHARE NOWAIT、隔離正常系の**個別資産承認は含まない**。push/mergeと製品・凍結資産変更は許可しない。
- **5条件の突合**: ①[追補§「着手判定と7.7」](../features/ur1-recording-rights/step2-minimal-addendum-proposal.md)は候補提示で承認者/日付を「受理待ち」とし仮値を置かない。②個別受理後に実承認記録から転記する。③同書の検査表は隔離DB特権fixtureの直接`FOR SHARE`正常/競合と、製品2関数の常閉拒否を別系列にする。④同書の変更表・個別承認資料は製品open成功と復元開始関数を新5へ置く。⑤sync-protocol 6-2/9-5の事前/直前停止・全取消・起動時閉鎖・解除と新D4の不可分性、U-S1受理契約の③-a/⑧、計画DoDの新5/6/9での完走、6.1/6.3のレビュー上限・最終反映人間確認、7.7-2の実承認記録/追記履歴と矛盾しない。**5件とも充足**。P0反映差分は独立再レビューなしのまま人間確認された。
- **更新後の新2開始条件**: 計画追補のレビュー・人間承認は充足。残るのはTSK-550共有実行器Aのdevelop統合、5項目の個別資産/担当採否、具体的DDL・認可・凍結契約と必要正本の個別承認、A統合後の実revision/digest・7.7 before/after候補の提示と正式受理。U-S1 Port契約は受理済み、新6の実経路結合試験とD4方式は別ゲート。現時点の`origin/develop`は`9b8f9bc6`でA未統合のため、製品実装には進まない。
- **最終承認の追認**: 上記の5条件充足報告後、依頼者は「承認するう」と明示した。対象は新2の**最小計画追補**のみ。owner・FORCE RLS・EXECUTE・FOR SHARE NOWAIT・隔離正常系の個別資産や7.7実値の受理、製品実装開始、push/mergeの承認には拡張しない。

## RG1個別判断資料と7.7順序の循環（2026-10-15、手順裁定待ち）

- **既存資料**: [RG1個別承認資料](../features/ur1-recording-rights/rg1-individual-approval-packet.md)2節にowner、単一行FORCE RLS/最小列権限、2関数限定EXECUTE、通常側FOR SHARE NOWAIT、隔離正常系の推奨案・具体差分・影響があり、3〜4節に対象資産と拒否/試験条件がある。[承認済み最小追補](../features/ur1-recording-rights/step2-minimal-addendum-proposal.md)の判断表にも要約済み。方式の5件は人間の項目別採否待ち。正本7.6/必要な7.3、認可・データモデル担当の採否、正確なDDL/JSONと実DB検証、A統合後の実revision/digestはまだない。現在の`origin/develop` `f36d0fee`へAの統合は確認できない。
- **順序の循環**: 計画§4は新2のステップコミットに製品operation/SQL許可・snapshot・単一未マージ受理記録のafterを同梱し、7.7の受理単位をPR最終headとする。一方、承認済み追補は「7.7実値の正式受理を製品実装開始条件」とする。実際のafter digest/snapshot/最終headは候補実装・資産差分を固定しないと算出できない。正式受理を候補作成より先に置くと必要値を提示できない。未承認の候補作成や仮の承認記録で埋めない。
- **変更前に提示する解消手順案（未承認）**: ①Aの正式統合後、最新developからbefore revision/digest/snapshot/履歴と共有実行器契約を読取固定。②5方式・具体DDL/認可・必要正本と、**ローカル候補作成だけを7.7正式受理に先行させる限定許可**を別途人間が判断。③許可された範囲だけ専用worktreeで製品/資産候補・試験を作り、正式台帳にはまだ受理済みと書かない。④候補のSQL/JSON・revision/digest・snapshot・before/after・movement_fact/reasonと既存Draft PRの実番号を固定して独立レビュー/検査と人間の7.7個別受理を受ける。PR番号が未取得なら、番号取得用push/Draft作成を別途許可してから行う。提示時の承認者/日付は受理待ち。⑤実受理後に承認記録から承認者/日付を転記して正式台帳・archive・派生資産を同ステップコミットへ整合させ、最終headを再照合する。未マージ記録は1件、既受理履歴とbeforeは不変。⑥範囲変更や候補と最終headのずれは再提示・再受理。POの手順裁定前に③へ進まない。
- D4方式と新6実経路結合試験は別ゲート。A統合・個別資産承認・7.7正式受理は未成立として扱い、新2製品実装や凍結資産の変更はしない。

## 7.7候補作成順序のPO方針と最小追補起案（2026-10-15）

- **PO方針**: 依頼者は`dd206b4e`の正式受理前ローカル候補作成という順序変更方針を承認し、最小計画追補の作成・必要な計画レビューを指示した。この承認は候補実装、5項目、正確なDDL/JSON、7.7実値、PR番号取得用push/Draft作成を許可しない。D4と新6は射程外。
- **候補とレビュー対象**: [新2受理順序追補案](../features/ur1-recording-rights/step2-acceptance-order-addendum-proposal.md)に、A後before固定→5項目/資産の個別承認→明示許可後のローカル候補→実after/snapshot/完全差分提示→7.7受理→同一ステップコミットの順を記した。レビュー対象は本追補全文と、計画§4の開始条件/ステップ単位受理・新2/9行、7.7-2/3、既存最小追補の「着手判定と7.7」への直接影響に限定する。6.1の正本違反・ステップ不成立・DoD不対応をP0/P1/P2で判定する。依頼者の「必要な計画レビューを経て」を、6.3の**追加1回・上記差分と影響箇所**の裁定として扱い、追加周回は自動延長しない。明示された回数/範囲が異なるとの指示があればレビュー開始前に止める。
