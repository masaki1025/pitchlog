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

## RG1資産5項目のPO設計方針承認と順序追補レビュー（2026-10-15）

- **人間承認の出所・採否**: 依頼者は[個別承認資料](../features/ur1-recording-rights/rg1-individual-approval-packet.md)2節の5件を設計方針として承認。①2読取関数専用`NOLOGIN/NOBYPASSRLS` owner、②単一状態行の`FORCE RLS`と最小権限、③PUBLIC EXECUTE剥奪とappへの固定読取2件限定、④通常側`FOR SHARE NOWAIT`・競合/欠損/不明/読取失敗のfail-closed・B7/P3はB10でscope全取消、⑤隔離行ロック正常系と製品関数常閉試験の分離。試験用openは運用解除ではない。自動再送と追加権限拡大を含めない。**具体DDL/JSON、候補開始条件、7.7実値/snapshot/正式受理、push/Draft/mergeは承認されていない**。
- **固定したレビュー対象と結果**: 文書候補`b0168ef9bd8fa6d57b82ad680ffd12b18c91042b`を、起案に関与しないread-only Codexセッション`01a13f7e-11a4-7912-b255-427ed570ddd6`が`.claude/scripts/codex_run.py review adversarial -`で照合。**否決 P0=1 P1=1 P2=0**。P0は新2での7.7正式受理・承認者/日付記入が、計画§4のPR最終headへの単一正式受理と矛盾すること。P1は候補資産を変更して正式台帳を未更新にすると`frozen_history.py`の履歴末尾不一致が必然となるのに、候補の検査赤をすべて修正対象と記したこと。
- **指摘の採否・影響**: P0/P1とも採用。順序追補案を**否決・未承認**に据え置き、候補確認とPR最終head受理の関係、受理前後の検査区分を再設計する。今回の承認は5項目の設計に限り、レビュー否決を覆さない。追加レビューは自動延長せず6.3のPO裁定を待つ。TSK-550 A統合、具体資産の個別承認、候補作成の明示許可、実値7.7受理はいずれも未成立。製品・凍結資産に変更なし。

## P0/P1反映候補と今回の追加レビュー裁定（2026-10-15）

- **PO裁定**: 依頼者はU-R1新2の設計・受理準備を一連の作業として再開し、前回レビューP0/P1の修正差分と直接影響節に限る**独立レビュー1回**を許可。既実施の前回`b0168ef9`レビューはこの新しい許可でのレビューに数えない。今回も追加周回は自動延長しない。追補の最終承認、正確な資産/候補実装、7.7正式受理は独立ゲート、mergeは禁止。
- **実測・候補**: `git fetch origin develop`で`origin/develop=3f6a935a`、TSK-550 Aは別worktreeの未コミット候補でdevelopに未統合と確認。Aの候補registry/固定関数実行器は読取のみ。前回P0の解消案は**新2単独PRを最終受理単位**とし、後続ステップは別PRにする計画のPR境界変更。`single_review_acceptance`と7.7条文は不変。前回P1の解消案は未受理ローカル候補の履歴不一致を不合格と記録し、正式記録反映後の全検査greenをステップコミット条件にする。[改訂追補案](../features/ur1-recording-rights/step2-acceptance-order-addendum-proposal.md)と[一括判断資料](../features/ur1-recording-rights/step2-decision-brief.md)をレビュー候補とし、§4・新2/9、既承認最小追補の着手/試験境界、7.7条文・A接続への直接影響だけを独立査読する。前回P0/P1を採用反映したため計画レビュー周回5→6。現行承認済み§4は人間の追補最終承認まで有効。

- **追加独立レビューの実施**: 固定候補`191427621d99f462c776b75b60a62a2c6078a94d`を起案に関与しないread-only Codexセッション`01a13f94-c8fc-7730-b5c0-60b595eeb750`が`.claude/scripts/codex_run.py review adversarial -`で修正差分と直接影響節だけ確認。**否決 P0=1/P1=2/P2=0**。前回の受理単位P0と未受理検査P1は修正を確認した。
- **新規P0・採用**: 新2PRだけを切り出すと、現行新7のコアパス宣言と新8のJSON登録が後続PRへ残り、同じPRで重複帰属を登録するDoDを満たせない。[判断資料](../features/ur1-recording-rights/step2-decision-brief.md)に、新2PR内の宣言→JSON登録→製品を独立コミットとする番号対応候補を示した。実順序・guard緑・後続PRの追加パスの扱いは最終人間確認事項。既存ステップ表は未変更。
- **新規P1・採用**: 承認済み最小追補の「製品実装前7.7正式受理」を置換する対象条件として明記し、試験境界は維持。作業ツリー検査と、Git HEADを読む契約/履歴検査・PR CIを分けて、コミット前の検査だけを全件greenとしない。前回候補からの追加反映により計画レビュー周回6→7。**P0/P1反映後の最終差分は未再レビュー**。今回のPO許可1回は消費済みで自動再実施しない。A未統合、具体資産/候補作成/7.7正式受理未承認、製品・凍結資産変更なし。

## 最終承認資料のguard/認可基線の実測（2026-10-15）

- **旧新ステップ・コミット・PR対応**: [一括判断資料](../features/ur1-recording-rights/step2-decision-brief.md)の推奨案は新2=パス宣言コミット、新3=JSON登録コミット、新4=旧新2のRG1製品・受理記録コミットを同じ先行PRに置く。旧新3/4/5/6は新5/6/7/8へ移し、旧新7/8は先行PR対象部分を新2/3へ移す。新9は全体の最終照合。旧名称のD4と実経路結合のゲートは移動先へ引き継ぐ。現行表は未変更、最終差分は未再レビューで人間確認対象。
- **guard根拠と検査**: `scripts/core_guard.py::validate_area_path_layers()`はmerge-base pathsと宣言済み追加層を照合し、製品ファイルの存在を要求しない。`verify_area_path_baseline()`はコミット列を走査し、JSONと基線定義の同一コミット変更を拒否。既存の合成repo試験`test_tenant_declaration_accepts_json_before_registration`は宣言→登録を製品ファイルなしで受理し、`test_addition_layer_requires_complete_declared_suffix`は部分/並べ替えを拒否する。`uv run pytest tests/test_core_guard.py -k 'tenant_declaration_accepts_json_before_registration or addition_layer_requires_complete_declared_suffix' -q -n 0`は**2 passed**。RG1の実パターンでの新2/3コミット検査とPR本文の逐行確認は後続ゲート。
- **正確な認可資産範囲の追加発見**: `ddl-elements.json`には列ACL群があるが、`product_control_access.py::generate_function_owner_column_acl_sql`と`check_authz_catalog.py`は追加definer列ACLを`["SELECT"]`に限定。RG1の最小権限`UPDATE(singleton_id)`はそのままでは不合格となる。表UPDATEへ広げず、RG1表/列/owner/commit-check関数のexact tupleだけ`UPDATE`を許す生成器・catalog・負例と宣言JSONを個別資産承認対象に加えた。正本3-2/特別露出の改訂と実DB権限検証も必要。A未統合のためrevision/digest/snapshot実値は記入しない。

## d5db8576のPO承認・最新develop再照合（2026-10-15）

- 依頼者は`d5db8576`の最終計画追補、判断資料の具体資産・RG1 exact tupleに限定した列`UPDATE(singleton_id)`検査器差分、ローカル候補作成、隔離DB試験・レビュー・修正・記録コミットを承認。追加レビュー後の未再レビュー差分も人間確認対象とした。既承認5項目は維持。新2宣言→新3 JSON登録→新4製品・受理記録を同じ先行PRに置き、新2/3のコミットを分離する。D4、運用open解除、7.7実値・正式受理、push/PR作成/mergeは承認範囲外。
- `git fetch origin develop`で`origin/develop=3f6a935a`を確認。U-R1専用worktreeに`git merge --no-edit origin/develop`を実施し、衝突なしで`7bf4a2a5`へ取り込んだ。他担当worktreeは変更していない。Aの共有実行器はdevelop未統合。U-R1の凍結7資産の実after/revision/digest/snapshotはA統合後まで確定しない。現存の未追跡`claude-handoff.md`は本作業の変更へ含めない。

## 新2・新3の分離コミットと新4の契約衝突（2026-10-15）

- 新2は`5480e350`で`scripts/core_guard.py`と`tests/test_core_guard.py`のRG1追加層だけを宣言。新3は`76f993f1`で`.claude/core-areas.json`の完全順列だけを別コミットに登録した。登録済み基線の検査を維持し、宣言済み・登録前と完全登録後の二状態を試験した。新3後の`uv run pytest tests/test_core_guard.py -q -n 0`は258件成功、Ruff・ty・`git diff --check`も成功。`verify_area_path_baseline(origin/develop, HEAD)`は`3f6a935a`基線で成功。push/PR作成はしていない。
- 隔離DB用`backend/tests/test_rg1_lock_contract.py`のローカル候補を作成し、使い捨てPostgreSQL 17で3件成功。専用NOLOGIN/NOBYPASSRLS owner、単一行、FORCE RLS、SELECT/UPDATEのsingleton限定policyと列`SELECT(singleton_id,state), UPDATE(singleton_id)`の組合せで`FOR SHARE NOWAIT`が通ることを実測。`UPDATE(state)`・INSERT・DELETEは拒否され、復元側先行のNOWAIT拒否と通常側先行のUPDATE待機を確認。Ruff・tyも成功。これは隔離正常系であり製品open解除ではない。製品関数常閉の検証は未了。
- **新規衝突1（A接続）**: TSK-550 Aの候補`196f1e3d`は`FunctionOperationRegistration`の固定関数呼出しで第1引数`tenant_id` bindを必須とする。一方、承認済みRG1資料は引数なし2関数。現状ではU-R1の2登録をAへ接続できない。推奨はRG1関数を`(uuid)`にし、引数/GUC一致をfail-closedで検査する最小契約改訂。関数identity・DDL/JSON・7.7資産に影響するため、個別差分承認待ち。A共有実行器の変更は行わない。
- **新規衝突2（列ACL ID）**: `COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_rg1_fn_owner`は表・列・ownerで一意であり、資料の`SELECT(singleton_id)`と`UPDATE(singleton_id)`を別行にするとID重複。推奨は同じIDの1行に`["SELECT", "UPDATE"]`を閉じ、`state`のSELECTは別行。生成SQLは列単位の2権限、検査器はRG1 exact tuple以外のUPDATEを拒否。実効権限は隔離DBで確認済みだが、資料の具体JSONとは異なるため人間の差分承認待ち。正式認可/凍結資産は未変更。
- Aはdevelop未統合。新4のA接続、正式認可/凍結資産、実revision・digest・snapshot、7.7正式受理は未了。現在の候補試験をステップ4完了や受理済みとして扱わない。独立レビューは候補差分が固定できるまで未実施。D4・運用open・新8結合・push/PR/mergeには進まない。
- 追加のローカル候補`tests/test_core_guard.py::test_ur1_actual_path_set_is_guarded_in_both_meaning_areas`で、予定するRG1製品・認可・契約・試験16経路すべてが実登録からガードされ、該当6経路が同期プロトコルにも重複帰属することを確認。`uv run pytest tests/test_core_guard.py -q -n 0`は259件成功。これは新4候補差分であり、まだコミットせず新2/3の既確認履歴は維持する。
- 人間判断用のexact前後表を[判断資料](../features/ur1-recording-rights/step2-decision-brief.md)末尾へ追記。Aの必須`tenant_id` bindに合わせる2関数`(uuid)`化と、重複列ACL IDを1行`["SELECT", "UPDATE"]`へ束ねる案だけを承認待ちにする。既存の5設計方針、Aの共有実行器、他のowner/表/列の権限は変更しない。

## RG1新4の最小契約修正承認と候補着手（2026-10-15）

- 依頼者は2関数の`(uuid)`化と検証済みscopeからAが注入する`tenant_id`限定、DB側GUC照合によるfail-closed、`singleton_id`の単一ACL行`["SELECT", "UPDATE"]`を明示承認。呼出側の任意tenant入力、表UPDATE、他列・他owner・他関数のUPDATEは許可されない。計画と接続契約、判断資料のSQL/JSON候補へ反映した。A統合後の実revision/digest/snapshot・7.7正式受理、push/PR/mergeは別ゲート。
- Aは`origin/develop=3f6a935a`にまだ未統合。承認済みのA非依存部分として`product_control_access.py`と`check_authz_catalog.py`にRG1 exact tupleだけの列ACL生成・検査を候補実装した。指定8種の表/列/owner/関数/権限変異を拒否する試験を加え、関連`backend/tests/test_authz_product_control_access.py`は26件成功。候補を正式受理済みとは扱わない。
- PC中断後に作業ツリーを確認し、未コミット候補が保持されていることを確認。RG1の`(uuid)`製品関数2本を隔離試験fixtureで実行し、開状態でも常閉、GUC欠損・不一致・不正、状態行欠損、表直接権限・他role実行拒否、NOWAIT競合を検証した。正式body manifestへ先置きすると既存の三方向exact-set検査が赤になるため、関数SQL候補は`backend/tests/fixtures/rg1/`に保全し、正式資産への登録は全対応行を揃える段階へ回した。`backend`の関連32件とrootのcore guard 259件、Ruff・tyは成功。未コミット候補・7.7未受理・pushなしを維持する。
- 状態行`(1,'closed')`のseedは既存migration衛生検査が原則禁止し、`contracts/migrations/seed-allowlist.json`の個別宣言だけを許す。現行のRG1承認資料はseedの分担を示すが、このseed allowlistの正確な宣言・履歴差分は未提示。正式資産へ追加する前に既承認範囲との対応を確定し、必要なら追加承認対象として具体差分を示す。既存seed履歴は変更しない。

## 初期closed行の台帳調査・独立レビュー1回目と反映（2026-10-15）

- [seed整合調査](../features/ur1-recording-rights/rg1-seed-allowlist-assessment.md)を追加。現行migration衛生試験は未宣言の`op.bulk_insert`を拒否し、RG1の`singleton_id/state`は現行台帳の語彙用`category/key`形に一致しない。最小候補を静的検査器へ与えると`禁止 API bulk_insert()`となった。承認済みの`(1,'closed')`を投入するには、同一表作成revisionに限定した新seed系列と、1行完全一致の検査器形が必要。現行台帳・受理済み履歴は触れず、別の具体資産承認と7.7受理候補にする。
- 候補に関与しない独立Codexセッション`/root/rg1_review`が現行未コミット差分をread-onlyで確認。1回目は**否決 P0=1/P1=2/P2=0**。P0はRG1専用ownerまたは表への表ACLを既存生成器・catalogが許し、`UPDATE(singleton_id)`限定を表全体UPDATEで迂回できる点。P1はcatalogのexact tuple経路への直接変異試験不足と、隔離fixtureが関数作成・PUBLIC剥奪・app付与をautocommitで分割し同一transactionを実証しない点。A未統合・正式RG1認可資産未作成・seed未決なのでレビュー対象は候補部分のみ。
- **採否は3件とも採用**。P0にはRG1表または専用ownerへの表ACLをcatalogと生成器の両方で拒否するガード、表/ownerの負例を追加。P1にはcatalogへ8種の列ACL変異を直接渡す拒否試験、製品関数fixtureの単一transaction化と2関数目の故障時に1関数目・権限までrollbackする試験を追加。`product_table_access.py`は既存tenant-isolationのglobでguard対象だが、記録権の意味範囲にも明示するため、追加パスを新2宣言と新3登録の候補へ反映した。正式コミットでは宣言と登録の分離を維持する。
- 2回目の独立差分レビューへ渡す候補識別: tracked code/guard差分の`git diff --binary` SHA-256=`4efbf6bc6c0ab08484a4afacc43fca29cc0853bd844d42ecbb427d3572d0a463`、未追跡の読取/直前関数SQL=`ee8071217f35d0663023f83cac17fa7aef73033eb5736dcf837cf4423a176e42` / `9fa3264653c7d04134453daa55df0b31453e90f5a4066d1820a630d6f3dfa1c9`、隔離試験=`e2518c2ddfe2bdfe2aef69e382eaefa17730f9723facf84eaa81439ad06c5eee`。対象は1回目の3件の反映差分と直接影響。6.3の基本枠2回目を用い、追加周回は自動延長しない。
- **独立2回目の結果: 可決 P0=0/P1=0/P2=0（候補差分限定）**。同一独立レビュアが上記tracked差分・未追跡SQL/試験のSHA一致を確認し、P0のRG1表/owner表ACL拒否とP1のcatalog直接変異/単一transaction故障rollbackの反映を全件確認。新たな指摘なし。レビューはA接続・正式認可資産・seed系列・7.7受理の完了判定ではなく、その後の差分は別途レビュー影響を評価する。
- 追加の`product_table_access.py`を記録権パスへ登録するため、ローカルで宣言`40e5f310`（新2追加）とJSON登録`3dcb437b`（新3追加）を別コミットに固定。最初の登録候補はJSONと`tests/test_core_guard.py`の基線テストを同時にコミットし、`verify_area_path_baseline`が正しく拒否した。**その未pushの新規コミットだけ**を組み直してJSON単独にし、既存の確認済み履歴を維持した。現在の`verify_area_path_baseline(3f6a935a, HEAD)`は成功、core guard 259件成功。実パス集合テストは新4候補の未コミット差分に保全。pushなし。
- 検査: backend Ruff・ty成功、関連認可/製品関数55件成功、migration衛生102件成功、root Ruff・ty成功、core guard259件成功。これらは限定範囲であり、正式RG1資産・A接続・凍結/archiveを含む全件検査ではない。

## RG1初期seedの追加範囲承認とレビュー対象固定（2026-10-16）

- **承認出所・範囲**: 依頼者（PO）が本会話でRG1専用seed系列、限定検査器、完全一致`(1,'closed')`の初期行、範囲外の負例、隔離検証・独立レビュー・指摘対応を承認。既存語彙seed/受理履歴は維持。7.7正式受理・運用open・push/PR/mergeは含まない。
- **候補**: migration `0032_rg1_restore_gate.py`は表作成と1行投入だけを同一upgradeで行う。`singleton_id`は`autoincrement=False`で`smallint`に固定。候補台帳fixtureは`pending_7_7`。検査器は旧語彙形を維持し、RG1専用形の単一表/単一行/型を完全一致で判定する。製品/正式凍結台帳・受理済み履歴は未変更。
- **レビュー対象識別値**: `backend/tests/test_migration_hygiene.py`=`1fd4a6e5`、`backend/migrations/versions/0032_rg1_restore_gate.py`=`8ba7f695`、`backend/tests/test_rg1_seed_migration.py`=`5eb4dc30`、`backend/tests/fixtures/rg1/seed-allowlist-candidate.json`=`59dc5159`（各SHA-256先頭8桁）。候補と直接影響だけを独立レビューする。候補fixtureと正式台帳は受理前後の両状態を区別し、受理後の全件検査でも試験を残す。
- **検査現在地**: 隔離DBの実Alembic適用2件（同ID追加拒否、試験用open既存行の再投入上書き拒否を含む）、候補検査器の正常1件・拒否11件、Ruff・tyが成功。正式台帳未受理のためmigration衛生全件114件中113件成功・新`bulk_insert`拒否1件で、これは設計通りの未完ゲート。Aは`origin/develop=3f6a935a`へ未統合。正式revision/digest/snapshotは未確定。
- **独立レビュー・採否**: 候補作成に関与しない`/root/rg1_review`が上記固定SHAの4ファイルと直接影響だけをread-onlyで確認。結果は**可決 P0=0/P1=0/P2=0**。途中の候補fixtureが7.7受理後に失敗するというP1指摘は、固定SHAでは既に受理前後両状態を扱うためレビュアが再読して撤回した。採用すべき残指摘なし。既存の製品/認可候補2回レビュー結果と混同せず、今回の判定はseed候補差分限定とする。
- **追加検査**: backend migration衛生の受理済み範囲113件、seed隔離DB/負例14件、root core guard259件、root/backend Ruff・ty成功。全migration衛生の1赤は正式台帳未受理の新`bulk_insert`拒否であり、正式受理前に検査器を緩和しない。試験用open既存行は隔離DBの上書き拒否を測るfixtureで、運用解除ではない。

## TSK-506へのguard編集所有引き渡し（2026-10-16）

- **比較元**: 最新`origin/develop=966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`（#132統合済み）。TSK-506専用worktreeは読取確認で同SHAをmerge-baseとし、guard3ファイルに未コミット変更なし。U-R1未統合ブランチをTSK-506のdevelop基線として使わない。
- **U-R1確定差分**: `5480e350`/`40e5f310`で`AREA_PATH_ADDITIONS`と試験のRG1層を宣言、`76f993f1`/`3dcb437b`で`.claude/core-areas.json`へ別コミット登録、`60202cf2`でRG1実経路帰属試験を固定。`19167e97`で最新developをmergeし、U-S1の登録済み層の後にRG1層を置いて3ファイルの競合を解消。現HEAD=`19167e97`、比較元との差分3ファイルのbinary diff SHA-256=`f8d898e5d5e4ec6ce7aa81fdea58b9148d6168432651d00ac2e3d26d00ec6821`。guard3ファイルの未コミット差分は**0**。
- **保持すべき境界**: `sync-protocol`のRG1追加6パターン、`recording-rights`のRG1追加17パターンを、U-S1の既登録3パターンの後の完全な末尾層として維持する。`scripts/core_guard.py`の宣言と`.claude/core-areas.json`の登録はコミット分離を維持し、`tests/test_core_guard.py`の段階登録・不完全末尾拒否・RG1実経路の二領域帰属・U-S1登録済み基線検査を残す。`verify_area_path_baseline(origin/develop, HEAD)`は`966d7a38`を返し、core guard262件、root Ruff・tyが成功。
- **所有判断**: U-R1からguard3ファイルの編集所有を**解除**する。TSK-506は自己の最新develop基線で着手できる。U-R1新4の現在判明している追加パスは登録済みで、これら3ファイルの予定編集はない。A統合後に新たなRG1パスが必要と判明した場合は、TSK-506と同時編集せず、同担当の変更確定後に差分と計画ゲートを再照合する。guard独立PRの分割は待ち短縮に不要で、現行の先行PR計画を維持する。製品/認可/seed候補は別の未コミット差分として保全し、今回の所有解除に混ぜない。

## A統合後のRG1新4候補と独立レビュー（2026-10-16）

- **統合出所**: `gh pr view 141`でTSK-550共有実行器AのPR #141がmerge済み、実統合SHA=`e7e8d3a4324687ada828b1e4b49692c087af5c44`と確認。`origin/develop`をU-R1 worktreeへrebaseせずmergeし、ローカルSHA=`9fa6415b713e5ce216ec325f02b07b014288e618`。他担当worktreeは変更せず、push/PR/mergeなし。
- **候補実装**: Aの静的固定関数registryへRG1専用2登録。scope注入`tenant_id`とGUCをDB側でも照合。2関数は今段階で常にfalse、③-a非ロック・⑧`FOR SHARE NOWAIT`。専用owner、単一FORCE RLS表、最小列ACL、2 policy、PUBLIC EXECUTE剥奪、初期closed行1件とseed専用検査器、schema/model/manifestを候補化。正式台帳・archive・history-snapshotsは未変更。詳細と実before/候補after値は[判断資料](../features/ur1-recording-rights/step4-a-integrated-acceptance-candidate.md)。
- **レビュー結果と採否**: 起案に関与しない`/root/rg1_review`が候補をread-only査読。モデル欠落、PK自動採番、隔離試験が正式bodyでなく複製fixtureを実行、A実scope/rollback試験欠落、`rg1_api` owner/ACL exact固定不足をP1として検出。全件採用し、最小モデルと`autoincrement=False`、正式body直接実行、実`tenant_transaction_scope`で2口のfalse→同一scope全取消、schema exact期待と負例を追加。同レビュアの修正後再照合では新規P0/P1/P2=0、関連65件成功。正式7.7と共有DB全資産適用はこの判定に含まない。
- **実測**: 関連RG1/認可100件、repository/capability200件、schema manifest14件、authz候補39件、core guard262件、backend/root Ruff・ty、製品authz catalog (`total=1414`) とfunction-bodies検査が成功。隔離DBの実scope全取消2件も成功。rootの大規模authz変異全数は途中停止したが、旧未発効45表fixtureとRG1候補46表の混線を修正し、該当1件を再検査済み。共有DBの製品認可round-tripは既存test roleによりsetup停止し、候補SQL未実行。未受理の凍結履歴末尾不一致とseed台帳の新bulk_insert拒否1件は予期した赤として保持。
- **7.7候補**: A統合後の実beforeはbase-allowlist 31、repository-contract 19、runtime-authz-contract 16。候補afterは順に32/20/17で、射影SHAは判断資料に記載。残り6資産は不変。seed新系列の候補canonical SHAは`d6d05be6344a266d4ec63e2750694aa4b71341c119e03fbd3460f73cab1b7fb0`。PR番号・最終HEAD・実承認者/日付は未取得で、正式記録を仮置きしない。C1が共有資産を先行統合した場合はbeforeを再固定し、全値を再算出する。
- **所有・調整**: guard3ファイルの未コミット差分0、比較元`origin/develop=e7e8d3a4`との差分SHAは従前と同じ`f8d898e5d5e4ec6ce7aa81fdea58b9148d6168432651d00ac2e3d26d00ec6821`。編集所有解除を維持し、TSK-506はdevelopを基線にする。既存ログの「C1 TenantProfileReadToken追補」が共有凍結資産を編集する場合は先行統合側を次のbeforeにする順序とし、同時編集を避ける。agentメッセージ基盤の本project登録は未設定だったため担当宛ての直接送信は行わず、本作業ログを引渡し証跡とする。
- **担当ラベルの訂正**: Notion正式カードを照合したところ、既存ログの「C1/TSK-528」は一致しない。TSK-528はU-F13起動・アクセス入口、U-C1はTSK-401グループ管理操作。`TenantProfileReadToken`追補の実担当タスク番号は未確認で、TSK-528へ通知・変更しない。以前のC1受理事実は維持し、ラベルのみ確認待ちとする。
- **最終再検査**: A統合後のRG1・認可・migration関連266件、repository/capability関連200件、schema manifest14件、core guard262件が成功。backend/root Ruff・ty、製品authz catalog（1414件）、function bodies検査も成功。最新`origin/develop=e7e8d3a4`はローカルHEADの祖先で、`git diff --check`は成功。正式7.7未受理による履歴検査とseed台帳検査の赤、共有DBでの製品認可round-tripセットアップ衝突は未解消として維持する。

## 2026-10-16 受理準備・担当引き渡し

- **TSK-506**: guard3ファイルの編集所有解除を確定。正式カードへコメント`3fb93b75-e687-8133-81a0-001d15c6c17d`で、既存コミット固定・未コミット差分0・既知の予定編集0、最新develop基線、宣言/登録/段階試験の保持を伝達した。TSK-506のworktreeは変更していない。
- **C1識別の訂正**: 直前の「TSK-528とは無関係」は誤り。正式カード自体はU-F13だが、`docs/features/auth-session-verification-contract/plan.md`に**TSK-528追補C1**が明記される。U-C1/TSK-401とは別。C1の第1段`d5ccc18e`・第2段`7731070a`がA統合後の共有凍結資産に触れることを確認し、C1先行正式受理・統合→U-R1が受理済み履歴から再導出する順序をTSK-528カードのコメント`3fb93b75-e687-8104-8d15-001d43c2f0a7`で提示。担当回答待ちで、合意済みとは扱わない。
- **使い捨てDB検査の発見**: 共有`pitchlog_test_role`を変更せず、管理接続も別コンテナへ向けた。製品認可round-trip初回適用は成功したが、unapply時にRG1の`UPDATE(singleton_id)`列権限が残り、専用ownerのDROP ROLEが依存関係で失敗。`product_provisioning.py`の取り外しをRG1 exact tupleのSELECT/UPDATE両方のREVOKEへ限定修正し、単体49件成功。使い捨てDB全体の再実行と追加レビュー結果は別途記録する。
- **隔離再実測と独立レビュー**: 専用使い捨てクラスタで製品認可round-trip3件成功。初回全資産適用・catalog照合、取り外し、migration往復、再適用まで実行した。追加独立レビュアは準備HEAD`ca37bfc2`、tracked binary diff SHA-256=`b32c7aa2f6e5e7541c49008e5d37fe5f32a72946786f7fa565c7cb45e3e0d805`、未追跡ファイル列SHA集約=`d21c69b3cc5ee4b50f860878430406bbcbb058fb9c5ba4288973f26f77201f00`を対象とし、RG1 exact REVOKEを含めP0/P1/P2=0。正本7.6と正式7.7、人間逐行確認は別ゲート。
- **番号取得**: 準備文書だけを`ca37bfc2`にコミットし、既コミットの新2宣言・新3登録とともにpushして[Draft PR #143](https://github.com/masaki1025/pitchlog/pull/143)を作成した。新4製品・凍結候補は未コミット・未push。7.7候補IDは実番号に基づく`masaki1025/pitchlog#143`、ただしC1先行順の回答・受理済み履歴を待ち、before/afterを再固定する。現PR本文の人間逐行確認欄は未チェック。core guard CIはこのため赤であり、未確認のままチェックしない。

## 2026-10-16 C1先行順と正本7.6の再照合

- **順序の出所・状態**: POはC1先行→U-R1追随を希望。C1/TSK-528追補はDraft PR #144で第1・第2段を公開したが、7.7正式受理・統合は未了。TSK-528カードの既存照会`3fb93b75-e687-8104-8d15-001d43c2f0a7`へのC1担当の明示回答は未確認。確定順序とは扱わず、C1担当には[PR #144のコメント](https://github.com/masaki1025/pitchlog/pull/144#issuecomment-6209073339)でも「#144の正式受理・統合を先行し、U-R1 #143が実統合SHAと受理済み履歴をbeforeにする」採否と、受理時のC1作業ログへの記録を求めた。U-R1はC1 worktreeを変更しない。
- **認可所有側**: TSK-424カードの既存照会`3fb93b75-e687-8148-a727-001d69510117`への項目別受理・修正回答も未確認。中継が必要な事項はRG1専用owner/FORCE RLS/列ACL/EXECUTEの採否、正本data-model§3-2の7.3担当と修正点に限る。既承認の5設計項目を再審査へ戻さない。
- **7.6判定**: 開発規約7.6-3は実装追随の節更新を通常PRレビュー、版繰り上げを伴う構造的変更を7.3確定ゲートに振り分ける。現data-model§3-2候補は専用ロール・権限境界の新設とロール数変更を含むため、実装事実の追記だけと断定できず、正式正本への反映には7.3の敵対レビューと人間承認を要する候補と判定。未コミット節案の「7.6未確定」を維持し、既存の製品コード独立レビューを7.3の代用にしない。
- **CIと候補試験の区分**: 公開中の準備HEAD`cd03ddcb028878ac5c43dc9823463974040a29eb`はharness・mutation・tenant-boundary-bypass等が成功、core guardだけが人間逐行確認欄未チェックで失敗、backend/frontendはskipping。未push新4候補の専用使い捨てクラスタ製品認可round-trip3件、関連266件などのローカル成功とは別。正式seed/7.7未受理に伴う予期した赤とroot大規模変異試験未完は維持する。2026-10-16時点の`origin/develop`はA統合SHA`e7e8d3a4`で、C1統合後の7.7実値再導出は未実施。

## 2026-10-16 PO統合順の確定・data-model v0.11確定ゲート起案

- POは**C1／#144先行→U-R1／#143追随**を統合順として固定した。C1担当の受領・C1側作業ログへの記録は未確認だが、順序自体を再裁定待ちへ戻さない。C1は#144の7.7正式受理・統合後、U-R1が実統合SHAと受理済み履歴を次のbeforeに使う。未返信を技術的な受理と扱わず、C1 worktreeも変更しない。
- `data-model.md`§3-2の規範候補をv0.11 `in-review`として固定する。対象はRG1専用owner、単一行のFORCE RLS、ownerの列SELECT/UPDATE、appの固定読取2関数限定EXECUTE、製品常閉。D4・運用open・新8実経路結合は射程外。7.3-1の**暫定適用版はハーネス設計書v1.19**、approved条文を収録する基点コミットは`239d391dea2442a340dba235bd5eff3befbbc27b`。初回敵対レビュー直前に適用版と条文コミットを再照合する。正本の人間承認、7.7正式受理、本人逐行確認は別ゲート。

### 7.3第1回全文レビューと採否

- **適用版の確定**: 初回実行時のハーネス設計書7.3はapproved v1.19、条文コミットは`b34c350a3c5c161fb45f20343e7e11fc48236bdd`（in-review化コミットの第一親`239d391d`から7.3本文に変更なし）。候補固定コミット`b34c350a`を正本全文で`codex_run.py review adversarial`へ渡した。応答は規定の重大度・起因・(A)/(B)/(-)・判定行を含み、**否決 P0=0 P1=5 P2=0**。第1回として算入する。
- **P1-1（起因・A、採用）**: `data-model.md`3-2の認証用`function_only`無policyと、RG1専用ownerのSELECT/UPDATE policyが衝突。認証前4表に限定した無policy規則とRG1だけの非テナント例外を明記し、app直接権限を拒否した。反例・典拠: レビュー回答`data-model.md:240-241`、候補`product_table_access.py:14`。
- **P1-2（起因・A、採用）**: `SECURITY DEFINER`と固定`search_path`、専用owner非付与・非継承の記述不足。2関数の実行境界とappの`SET ROLE`拒否を明記した。反例・典拠: 同`:241,:244`、`rg1-individual-approval-packet.md:11`。
- **P1-3（起因・A、採用）**: 全体共通行に対するUUID/GUC一致をテナント認可と誤読できる。検証済みscopeからの注入とDB文脈整合確認を分け、GUC自体は認証の証明にならないと明記した。反例・典拠: 同`:244,:342`。
- **P1-4（起因・-、採用）**: 用途一覧の旧6ロールと新見出し・表の総数7が不一致。RG1を用途一覧に加え、製品6・移行バッチ込み7へ修正した。典拠: 同`:264`。
- **P1-5（非起因・-、採用）**: v0.10からの「テーブル権限は表単位でしか与えられない」は列権限と矛盾。列権限は可能、行単位の絞り込みはRLSで行うと訂正した。典拠: 同`:263`。不採用・(B)送りは0件。5件の反映差分と3-2影響節を第2回レビューの対象にする。

### 7.3第2回差分レビューと最終反映

- `01ec08aa23f32d2a75aa275334e3d470da15f761`の`反映1周目`差分と3-2影響節を`codex_run.py review adversarial`で確認した。前周の不採用・(B)送りはともに0件。規定様式を満たす応答は**否決 P0=0 P1=2 P2=0**で、第2回として算入する。
- **P1-1（起因・A、採用）**: 共有・管理・認証owner向けの`BYPASSRLS`検査をRG1 ownerへ一律適用すると`NOBYPASSRLS`と矛盾し、適用しないとロール非付与・関数ACL・名前解決検査が漏れる。3-2の共通契約をRG1にも明示適用し、属性検査だけを既存3 ownerの`BYPASSRLS`とRG1の`NOBYPASSRLS`に分けた。RG1 ownerは誰にもGRANTしない。反例・典拠: レビュー回答`data-model.md:241,:264,:278`、PostgreSQLのRLS/SET ROLE公式文書。
- **P1-2（非起因・-、採用）**: 1-1・8-2-A・8-2-B・12章の旧「3-2節の6ロール」4参照を、製品用6/総数7または数値なしの3-2節参照へ修正した。典拠: 同`:80,:1606,:1623,:3059`。不採用・(B)送りは0件。基本枠2回を終了し、**最終反映差分は未再レビュー**として7.3-8の人間承認で確認する。追加レビューを自動延長しない。
- **C1の受領証跡**: C1担当Codex Dは[PR #143コメント](https://github.com/masaki1025/pitchlog/pull/143#issuecomment-6209084415)でPO固定順を受領し、技術上の阻害差分なしと回答。C1側の`docs/worklog/2026-10-14-uf13-team-route-acceptance.md`「C1とU-R1の統合順・7.7正式判断資料」へ同順序を記録し、PR #144の文書コミット`5df6141d`に固定した。これで双方の作業ログに確定順序の記録がそろった。C1の正式7.7受理・統合自体は未了。
- **正本の最終識別値と資料**: `data-model.md` v0.11の最終候補HEADは`78c649150b085074476cbfe85f963dd96ec5a335`、本文SHA-256=`fe8251678c9f29c9d03d1a5239d5780204b77995a31d2f3a0ead65c67954f759`。人間承認用の本文・7件全採用・権限差分・TSK-424無回答時の代替判断を[一括資料](../features/ur1-recording-rights/rg1-data-model-v011-final-approval.md)にまとめた。現時点で正本は`in-review`、認可所有側の項目別受理は未確認。
- **最終反映後の対象検査**: RG1資産の正本quoteを新本文の正確な文に追随した（権限変更なし）。`check_authz_catalog.py`は`total=1414`で成功、`check_docs_status.py`は20文書・違反0、`tests/test_check_docs_status.py`は専用`--basetemp`で72件成功、`git diff --check`成功。最初の通常tmpのpytestは`/tmp`が満杯で72件中大半が一時ファイル作成に失敗したが、別領域で再実行して72件全成功。環境故障をコード不合格として扱わず、初回失敗も記録に残す。新4製品候補は未コミット・未push、公開準備HEADのCIとは別。

## 2026-10-16 data-model v0.11の人間承認と限定

- **承認者・日時の出所**: 本会話のプロダクトオーナーが2026-10-16（Asia/Tokyo）に、最終反映`78c64915`に対応する[承認資料](../features/ur1-recording-rights/rg1-data-model-v011-final-approval.md)の本文・権限差分・7件全採用の記録、および最終反映未再レビューを確認したと明示し、**data-model v0.11の今回の3-2節改訂範囲を承認**した。氏名は本メッセージにないため推定記入しない。正本frontmatterと変更履歴、索引を`approved`へ確定する。
- **承認の射程**: RG1単一状態行、専用ownerの属性と権限境界、FORCE RLS、appの固定読取2関数限定EXECUTE、製品常閉まで。個別DDL/JSON、認可資産所有側TSK-424への未回答3項目、その代替受理、7.7実値・snapshot・seed正式履歴、D4方式、運用open、本人逐行確認、Draft解除・マージを含めない。他のdata-model候補改訂をこの承認へ混ぜない。
- **C1待ちと次の導出条件**: C1担当の受領・双方作業ログへの順序記録は確認済み。2026-10-16時点の#144はDraft・未統合で、最新`origin/develop=e7e8d3a4`。C1の正式受理・統合後に最新developをmergeし、受理済み履歴から7.7実値・snapshot・seed案を再導出する。現A直後の数値は暫定のままにする。

## 2026-10-16: 実 RecordingRightsPort と HTTP 入口の依存照合

- [依存表](../features/ur1-recording-rights/port-connection-dependency.md)を追加。U-R1新4のRG1候補は読取2関数であり、`RecordingRightsPort`具体クラス・登録・利用可能コミットはない。U-G1作成/開始worktreeにも初期付与実装はない。TSK-506は入口、U-S1は同期核、U-R1は本物の記録権Port提供を所有する。
- D4方式は既存の[裁定案](../features/ur1-recording-rights/d4-decision-proposal.md)とブロッカー側の調査を利用し、新たな方式調査を重ねない。推奨2台台帳は未採用で、配置・運用担当・費用/日程は未決。U-R1新5の初期付与より前にD4とV12/端末/復旧世代の物理契約を別途確定する。
- TSK-506計画のステップ1〜3とS-1/wire/認証/キュー保持の契約試験は実Port前に進められる。ステップ4の登録済み実Portによる入口完成、ステップ5の実DB証跡は未達。仮Portを製品注入しない。U-S1の合成Portによる核試験も実Port接続の証拠とは分ける。
- U-R1新8とTSK-506ステップ5に、実入口でのRG1閉鎖B7/B10・D5未消費、commit直前閉鎖時の原本/台帳/投影の全取消、試合行→世代行→RG1行の順を残す。新8の前倒しは現契約では利用可能な全Portを生まないため計画順序を維持する。C1先行統合後の新4 7.7、D4裁定、新5個別資産は別ゲート。
- 担当照合の照会先はTSK-506正式カードのNotionコメント`3fb93b75-e687-81e6-835d-001d319a79fc`、U-G1カードの`3fb93b75-e687-8177-bfdb-001dcf93a2fb`、U-S1カードの`3fb93b75-e687-8180-9a40-001d3d58e92f`。いずれも所有境界・先行可能範囲と、既受理契約からの修正点だけを質問した。担当返信は未確認で、技術受理を代記しない。

## 2026-10-16: 正本承認の重複防止と認可所有側の代替受理案

- `data-model.md` v0.11は`dc969d3e`で`approved`確定、索引・作業ログ・承認資料も同コミットの範囲で更新済み。今回の再承認メッセージで正本を再編集しない。`78c64915`最終反映が未再レビューである残余も既記録のまま保持する。
- TSK-424の未回答3項目について[代替受理判断資料](../features/ur1-recording-rights/rg1-authz-alternative-acceptance.md)を作成。①専用owner/FORCE RLS/列ACLと既存policy合成、②appの固定読取2関数EXECUTEとPUBLIC剥奪、③承認済み§3-2とRG1一表だけの`function_only`写像を、差分・証拠・推奨裁定ごとに分けた。これは別のPO裁定候補であり、正本承認や無回答を代替受理と記録しない。
- C1/#144はDraft・未統合（確認時HEAD`a417d2a54af55ce82921212e29f02f211c54279d`）。`origin/develop=e7e8d3a4324687ada828b1e4b49692c087af5c44`のまま。C1正式受理・統合後、実基線から7.7 revision/digest/snapshot/seedと全差分を再導出し、最終試験・レビュー結果とまとめる。本人逐行確認、Draft解除、マージは別ゲート。

## 2026-10-16: 認可所有側3項目のPO代替受理

- 本会話のPOは、[67eda311の判断資料](../features/ur1-recording-rights/rg1-authz-alternative-acceptance.md)のexact差分に限り、今回のRG1新4についてTSK-424の項目別回答に代わる受理を明示承認した。専用NOLOGIN/NOBYPASSRLS owner、1表・単一行FORCE RLS、owner向けSELECT/UPDATE policy各1件、`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`、appの固定読取2関数EXECUTEとPUBLIC既定EXECUTE剥奪、承認済み§3-2との一致だけを対象とする。余剰policy・表全体の権限・復元開始・運用openは対象外。承認者氏名は今回のメッセージにないため推定しない。
- この別裁定を正本v0.11の再承認、7.7実値の正式受理、本人逐行確認へ流用しない。C1/#144は確認時点でDraft・未統合、`origin/develop=e7e8d3a4`。現在の未受理履歴とseedによる全件検査赤は維持し、C1統合後の実基線で値を再導出する。
- **候補検査**: 既存製品候補を変更せず、backendのRG1/認可/関数境界/migration/ロック関連pytest155件、rootの認可catalog全数変異pytest25,820件（8並列、309.31秒）、backend/root Ruff・ty、固定関数body、製品authz catalog（1414項目）、docs-status（20文書・違反0）、差分検査が成功。全数試験の逐次実行は73件成功時点で並列へ切り替えるため中断し、その後の全数成功で完走した。前回の独立レビューP0/P1/P2=0は当時の候補識別値に対する結果であり、C1統合後の最終差分・PR最終HEADのレビュー認定ではない。指摘対応を要する新たな失敗は今回なかった。

## 2026-10-17: C1/#144統合後のRG1新4再導出

- `gh pr view 144`でMERGED、実統合SHA`3052e0db743877c7f15c0ec10daa0142cba7ab7e`を確認。`origin/develop`をmergeで取り込んだローカルHEADは`45694509801ebf295d5b09dfe6983c567b1fb703`。rebaseは行わず、未コミット候補をstashとbinary patchで保全して再適用した。stashは候補照合が終わるまで保持する。
- C1と競合した`repository-contract.json`および生成`repository_contract.py`はC1の記録・公開面を保持し、RG1 operation 2件を追加。`base-allowlist`はC1のrevision32をbeforeとして33へ、repository契約は20→21へ再採番した。C1受理履歴末尾`masaki1025/pitchlog#144`と既存22件、PR #72 markerは不変。`runtime-authz`は16→17。
- 実基線の9資産のsnapshotを`frozen_history.frozen_projection_content`で再導出。変化は3件のみで、具体値・seedの別系列・7.7単一記録案は[受理待ち資料](../features/ur1-recording-rights/step4-c1-merged-7.7-candidate.md)へ固定。正式台帳・snapshot・archive・seed履歴へ承認者や日付を先入れしない。
- 共有資産の編集枠はTSK-550本体B担当へNotionコメント`3fb93b75-e687-81e9-af4f-001dc819ab53`、T1/T2正本改訂担当へ`3fb93b75-e687-819b-b223-001dab24e3cf`で照会。提案順はC1統合済み→U-R1/#143の正式受理・統合→両後続がdevelopから再導出。担当の返信までは受領済みと扱わず、共有ファイルの同時編集を避ける。
- C1解消後の候補で認可catalog（1414項目）、関数body、backend/root Ruff・tyが成功。DB回帰と認可catalog全数、独立差分レビューは実行中で、未完了をgreenと記録しない。7.7正式受理、本人逐行確認、Draft解除・マージは別ゲート。
- **独立差分レビューの採否**: 既存レビュアがmerge後HEAD`45694509`とC1解消3ファイル、9資産の前後値・seed提案を独立に照合した。初回指摘P1はstash再適用によりindexだけ旧revision32がstageされていたこと。採用して全候補を`git reset`でunstageし、作業ツリーのrev33/21を唯一の候補とした。旧C1前の表は時点記録として残し、[新しい受理待ち資料](../features/ur1-recording-rights/step4-c1-merged-7.7-candidate.md)と[exact記録案](../features/ur1-recording-rights/step4-c1-merged-7.7-record-proposal.json)を追加した。最終再照合は**P0/P1/P2=0**。共有3ファイルのbinary diff SHA-256は`9b17d23211589453a0707d61973457b6fe32cd979a85a0e66117b3d46a3ad20d`、JSON提案SHA-256は`ea92f2d36d3db3654b1b71e8f0a54f36971523a68b323fb21b0cde3b36e77b8a`。資料本文にはレビュー後に算出済みsource digestとsnapshotサイズを追記した（受理値・権限は不変）。正式7.7受理とPR最終HEAD固定は未了。
- **C1後の検査**: backendのRG1・関数境界・認可・migration関連155件成功（457.34秒）。製品authz catalogは1414項目、関数body検査成功。backend/root Ruff・tyも成功。未受理の`check_tenant_boundary_bypass.py --base-ref origin/develop`は履歴末尾と7資産の識別値不一致でexit 2（想定赤）。seed正式台帳にもRG1系列を先入れしていない。この時点では認可catalog全数と専用DBの全資産適用試験は継続中。
- **追加実測**: 使い捨てDBによる製品認可の初回適用・ロール属性再適用・migration取り外し/再適用の3件成功（65.88秒）。C1で追加されたrepository/capability周辺149件も成功。`check_docs_status.py`は20文書・違反0、差分検査成功。受理待ちsnapshot 3件はローカルキャッシュに導出保全し、11,868＋7,560＋6,550=25,978バイト。正式archiveへの追加はしていない。TSK-392 Notionコメント`3fb93b75-e687-8166-bce1-001df0b68d61`へ実基線・検査・未受理状態を記録した。
- rootの認可catalog試験は`-k 'not mutation'`で**25,632件成功**（817.46秒）、補完の`-k mutation`で**188件成功**（6.92秒）。両集合は名称で分割され、合計25,820件をC1統合後に完走した。`git fetch origin develop`で再確認した最新remoteは引き続き`3052e0db`で、この文書コミット時点の比較元に変更はない。

## 2026-10-17: PR #143の7.7一括判断候補を固定

- POは共有資産の順序を**C1→U-R1→TSK-550本体B**と再確認。TSK-550カードへNotionコメント`3fb93b75-e687-818e-8976-001d900a0d88`で固定順を再送した。T1/T2担当の現worktreeの未コミット差分は`ux1-state-calc`のplan/design/worklogだけでRG1新4の製品・認可候補と現時点で重複しない。実際に共有ファイルへ触れるときだけ照合する旨を同担当へコメント`3fb93b75-e687-818f-a51a-001d7b1fe363`で訂正し、未返信を全作業の停止条件にしない。
- C1統合済み`origin/develop=3052e0db`を再fetchで確認。RG1新4の製品・認可・テスト40ファイルを、実indexに触れない一時indexで候補化した。binary patch SHA-256は`779a5bf69b793fae10735e1383c40fcb9f5c130b360c7afa9061fe796d2db604`、変更パスmanifest SHA-256は`dd2c4225456718b357fa90b7d52f06cddbaf03f4afa2a7af3623e40fc33f0f31`。古い未追跡`claude-handoff.md`は候補から除外。9資産の完全before/after、3 snapshot、seed別系列、正式受理後に初めて反映する履歴1件とGit HEAD検査の順は[一括判断資料](../features/ur1-recording-rights/step4-c1-merged-7.7-candidate.md)と[exact JSON案](../features/ur1-recording-rights/step4-c1-merged-7.7-record-proposal.json)に固定する。正式承認情報は未入力。公開PR HEADは準備文書だけの`cd03ddcb`であり、新4候補をpushしない。

## 2026-10-17: #143の7.7正式受理と最終検査是正

- PO山田正輝が2026-10-17（Asia/Tokyo）に、比較元`3052e0db743877c7f15c0ec10daa0142cba7ab7e`、候補tree`ab529513587528acea40951e06720baa5515d355`、判断資料SHA-256`8a400916a58a23f66096738b3d7e16c720960fafeaf5a98adec9f3b2ac97b81d`、記録案SHA-256`ea92f2d36d3db3654b1b71e8f0a54f36971523a68b323fb21b0cde3b36e77b8a`を単一の最終候補として7.7正式受理した。対象は9資産の前後、新snapshot3件、`rg1_closed_seed`の`(singleton_id=1,state='closed')`1行。PR #143の未マージ記録1件とseed記録1件に実承認者・日付を転記し、新4ローカルコミット`1ecfdc5fae495b92bd29d5455d6ab9cecff625f4`を作成した。beforeと先行22件の受理済み履歴は変更していない。
- コミット後のHEAD検査で3原因が判明した。基底許可署名は`Literal["precheck", "commit_check"]`だったが、検査器はAST正規形`Literal['precheck', 'commit_check']`を照合するためTB005/TB006が失敗した。RecordingGenerationの検出4行はモデル追加で`{153,246,247,248}`から`{189,282,283,284}`へ移動した。比較corpusの入力digestも実入力と一致しなかった。関連root pytestは745 passed / 49 failedで、失敗はこの3原因に集中した。公開PRのHEADは変更せず、pushとCIを止めた。
- 同日POは、この3点と#143の単一未マージ受理記録after、snapshot、確認資料だけの追随を追加承認した。base after snapshotは`18934cf78b6621bb43cbce93581e31d1f117e9ced21b24a23f1bd4bec68091d6`→`e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046`（実計算11,864バイト）。corpus入力digestは`68dbc129cca5927ea596cfd95d8b0665511373afdb59d602f28f6f885b747a32`→`c3874627cd1fe598344b4c695c07ca4fe315839f3333dfa31c5430cc148d6c42`（実計算一致）。許可シンボル、API種別、検出4行、他8資産、seed、before、先行履歴は維持する。旧snapshotは比較元に存在しない未マージ資産で、新記録から参照が外れたため除去する。
- POは今回の是正差分と直接影響箇所に限る独立レビュー1回を許可した。全検査とレビューがgreenになった後に是正コミットを通常pushし、Draft PRを更新する。本人逐行確認、Draft解除・マージ、D4方式、運用openは別ゲートを維持する。
- **許可済み1回の独立差分レビュー**: 実装担当と独立したレビュアが`1ecfdc5f`からの是正差分と直接影響をread-onlyで照合し、P0=0/P1=0/P2=0、全件採用不要と判定。AST署名とSQLA_SELECT限定、#143 beforeおよび先行22件履歴の不変、提案記録と正式記録（実承認情報を除く）の一致、9資産のafter射影、旧snapshot参照0、4行検出、corpus実digestを確認した。この追加レビュー枠は使い切り、追加周回を自動実施しない。
- **残る品質ゲート**: `backend/uv run ruff format --check .`が是正前から存在する新4候補7ファイルの整形差分で失敗した。対象は`0032_rg1_restore_gate.py`、`classification.py`、`recording_rights/models.py`、`repositories/rg1.py`、`test_migration_hygiene.py`、`test_rg1_lock_contract.py`、`test_rg1_seed_migration.py`。意味変更のない整形でもモデルの2行短縮により境界テストの期待行番号は`{187,280,281,282}`へ追随し、corpus入力digestは暫定試算`b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`へ変わる。今回承認の3点と実値の範囲を超えるため未変更、pushも保留する。全件pytestは共有`/tmp`満杯で一時書込OSErrorとなったため、他担当の一時ファイルは削除せず専用ディスク領域で再実行する。
- **2026-10-17 追加PO裁定（整形ゲート）**: POは`backend/ruff format --check`で検出された新4候補7ファイルの指定整形、境界試験の実測4行`{187,280,281,282}`、corpus入力digest`b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`への追随を明示承認した。今回の整形と派生値だけの独立差分レビュー1回も許可。既受理base after`e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046`、before、先行履歴、seed、許可シンボル/API種別は維持する。Ruff指定7ファイルだけを整形し、モデル実ファイルから4行、manifest全入力からdigestを再計算して両値の一致を確認した。共有`/tmp`は削除せず、全件試験にはディスク上の専用一時領域を使う。元の関連pytestは高負荷下でcore guardの30秒タイムアウトが1件発生（455 passed、未完走）し、当該試験単独再実行は1件成功した。タイムアウト上限は変更していない。最終候補のレビュー・全件検査・コミット・push・CIは未了。
- **追加検査の停止点**: 整形後候補はbackend Ruff check/format check（360ファイル）/ty、root Ruff/ty、authz catalog（1414項目）、function bodies、tenant-boundary bypass、docs-statusを通過。境界4行とcorpus digestの直接試験2件も成功した。一方、backend関連pytestの非DB側は190 passed / 3 failed。失敗は`tests/test_authz_product_classification.py`の旧45表・function_only 13表・露出事実7種の期待集合で、RG1の`rg1_restore_gate`と`rg1_control`が期待値に未追随。正本・製品資産の分類自体は`function_only`と`rg1_control`で一致し、必要な是正はこの試験の期待集合・数値・説明文だけと特定した。今回PO承認の7ファイル整形と2派生値の外なので、試験ファイルはまだ変更しない。
- RG1隔離DB関連pytestは6 passed後、`test_rg1_writer_first_holds_share_lock_until_commit`で使い捨てPostgreSQLが既存の60秒内に起動せず失敗。専用ディスク一時領域・単独実行でも同じ起動失敗を再現し、試験のロック/照合本体へは到達していない。共有`/tmp`は削除せず、timeoutも緩めていない。共有ホストの実測はload average約45、メモリ空き約320MiB、swapほぼ満杯。全件検査・レビュー・是正コミット・push・CIは未実施のまま維持する。
- **2026-10-17 分類試験の追加PO承認**: POは、承認済みRG1事実の追随として`tests/test_authz_product_classification.py`に`rg1_restore_gate`（function_only）と`rg1_control`の期待値を各1件追加し、45→46表、13→14件、7→8種の説明文を更新することを承認。製品挙動・許可範囲・受理値を変えず検出を弱めない試験期待値追随はまとめて進めてよく、許可済み独立レビュー1回にこの差分も含める。変更後の分類試験23件は全成功。backend/root Ruff・backend format・ty、tenant-boundary bypassも成功。
- **DB起動失敗の切り分け**: 使い捨てPostgreSQLの設定は`postgres:17.11-bookworm`と`--encoding=UTF8 --locale-provider=libc --locale=C.UTF-8`、固定拡張起動引数。先の試験は6成功後にクラスタ起動を60秒内に完了できず失敗、単独再試験でも同じ起動失敗（ロック試験本体には未到達）。同設定で新しい専用診断コンテナを起動したところDocker run 1.9秒、TCP接続まで合計7.4秒で成功し、診断コンテナを破棄。その後、元の失敗試験を既存60秒上限・同じ専用ディスク一時領域で再実行し1件成功（11.93秒）。先の失敗を成功へ読み替えず、隔離DB関連全件は改めて実行する。共有`/tmp`と他担当のコンテナは変更しない。

## 2026-10-17: 派生検査の追加追随候補（正式受理待ち）

- 指定整形・分類追随の12ファイルを`d815b52ad0cafe844bbaf73c15a2d40ae8da3361`へローカルコミットし、許可済み独立レビュー1回を実施。7 PythonファイルのAST同一、分類母集合・境界4行・corpus実digest、9資産/seed/SQLA_SELECTの不変を照合し、P0/P1/P2=0。公開PR #143のHEADは準備文書`cd03ddcb`のまま。以後の追加候補はこのレビューの対象外で、6.3の追加裁定が必要。
- PO承認により、`d815b52a`を基点としてORM受理シートを再生成した。旧362行の人間判定・理由は行識別子で全件保持。N3の5行はRG1のmanifest候補追記だけで、旧「対象外」の理由は列不変性ではないことを引き続き示す。N4に`rg1_restore_gate`の新規1行が増え、判定・理由は人間確認待ちとして空欄。N4の機械期待数だけ54→55へ追随した。自動持越しモードは既存判定を59行以上空欄にするため使わなかった。
- `shared-preconditions.json`の`data-model.md`参照blobは旧`7155ddf804ed21ef778cffeb334528df8f5e3f56`から実blob`21a85f5e794baaa05376b06aec7185cada6c33c8`へローカル候補を作成。別の凍結点`schema-manifest.json`の正本SHA-256も旧`3ce0fc22b66d965ada83a14221db75f6306d4d419c795f09d1c8aa9e88e1a799`から実SHA-256`a4504bbb2cf3fcbec13ea4fbb0ccd7d8ab2b9b66dafec3fc01f763ed06b16bfc`へ候補追随。どちらも正本・製品権限は変えず、正式7.7受理情報を先入れしない。
- #145の実差分は同じ`shared-preconditions.json`の要件書側digestだけで、U-R1はdata-model側digestだけ。#145はoracle入力8資産とseal・受理履歴も確定候補に持つため、#145先行統合→U-R1が最新developから両digest・7.7実値を再導出する順をPRコメントで提案した（`https://github.com/masaki1025/pitchlog/pull/145#issuecomment-6228162174`）。#145の回答・統合は未確認。現時点の`shared-preconditions.json`自体はoracle sealの8入力、9件のtenant-boundary凍結資産、frozen-baselinesの`oracle_input`宣言に含まれず、この1行だけではそれらのlock・seal・既受理履歴へ直接差分を生まない。ただし#145統合後のPR #143前後値は再導出する。
- 既承認RG1事実への追随として、backendの旧45表・旧role/schema/policy集合のテスト期待値を46表・追加owner/schema/2 policyへ更新。`backend/tests/db_fixtures.py`も分類資産の46表をexact-set要求する。関連136件中135件成功、残り1件は既存の手動seed計画にmigrationがclosed単一行を入れるRG1表を含める旧前提で、同表を明示除外する検出維持の追随後、対象18件成功。製品コード・認可DDLの変更なし。
- backend非DB全件は更新前に14失敗、追随後は1919成功・4 skip・5失敗。残る5件は`probe-product-map.json`がRG1の製品専用原子7件を未登録のためで、写像資産は未承認範囲として未編集。追加候補は2関数・2 policy・1 owner・1 schema・1表を`product_only`に各1行。rootで先の30秒timeoutが出た検査群を低並列2・専用一時領域で一括再実行し375件成功した。ハーネス全件は前回自動過並列の未完走結果（29631成功・2 skip・8失敗）を成功扱いしない。
- backend全件の初回は共有DBに既存の`pitchlog_test_role`があるため641件がsetup error（製品assertへ未到達）。共有DBは変更しなかった。専用コンテナで`docker exec`を使う試行は、ホスト`/tmp`満杯でOCIが一時ファイルを作れず接続確認に失敗。コンテナ自身のログは起動成功。ホストから専用TCPへ直接照合する方式では3回目で接続成功し、同じ60秒上限のままDB必須試験を一括実行中。共有`/tmp`の削除、共有ロールの変更、timeout緩和はしていない。
- 隔離DB必須試験は8分57秒で138件成功・1件失敗の時点で停止し、全件成功とは扱わない。失敗は`test_0028_preflight_restores_product_force_rls_after_success`。同試験はHEADまでmigration・製品認可適用後、`0027`へdowngradeして`0028`まで再upgradeし、その時点で**現行HEAD全46表の製品カタログ**を要求していた。新設`0032_rg1_restore_gate`の表とpolicyはdowngrade時に外れるため、旧版`0028`とHEAD全数の比較が成立しない。FORCE状態の照合は成功している。旧版での既存対象の保持と、HEAD復帰後のRG1を含む全数確認を分ける最小試験修正案を人間判断へ送る。製品migration・認可は変更しない。

## 2026-10-17: PO追加承認の写像・0028試験追随

- POはRG1製品専用原子7件の写像、0028時点とHEAD時点を分けるmigration試験修正、ORM・digest・写像・migration試験差分と直接影響箇所への独立レビュー1回を承認した。`product_only`へ2関数・2 policy・owner・schema・表を正確に追加し、写像を1件消す負例を追加。製品原子232件の双方向exact-set検査を実資産で通した。認可許可・製品コードは変更しない。
- 0028では版番号、RG1表不在、既存表のFORCE状態とテナント表の取消を確認する。HEADへ戻してRG1のclosed単一行を確認し、downgradeで落ちたRG1表のFORCE・2 policy・列ACLを正規資産から再適用した上で現行HEADの全カタログを確認する。専用使い捨てPostgreSQLで当該試験1件成功。共有DB・共有`/tmp`・既存timeout上限は変更していない。
- N4新規行の正式判定・理由は空欄を維持。既存362行の判定・理由は保持する。推奨判定と典拠は[判断資料](../features/ur1-recording-rights/step4-derived-followup-decision.md)へ記載。#145は現時点でDraft未統合。統合後に実正本からdigestと7.7値を再導出する。
- **追加独立レビュー1回**: 候補のtracked binary diff SHA-256 `9fc870cf2159ad8de4d016ccb89472e791659df53e0f20d145f0fc6e7c526836`、基点`d815b52a`で、候補作成に関与しないレビュアがORM・digest・写像・0028試験と直接影響を読取専用で確認。P0/P1/P2=0、指摘なし、採否は追加反映なし。レビュアが関連backend145件とORM生成一致1件を独立実測して成功。レビュー後は結果記録だけを追記し、対象コード・資産差分は変更していない。
- backendの非DB全件は`1925 passed, 4 skipped, 647 deselected`。プラグインが「DB必須テスト0件」で終了コード1にするため、テスト失敗0件とコマンド終了コード1を分けて記録する。backendのRuff・format check・ty、root Ruff・ty、ORM未判定完了試験を除く12件、製品認可関連117件、shared preconditions・認可catalog1414・function bodies・frozen-baselines不変は成功。N4の未判定1行があるため完了判定試験は未通過のまま。DB全件・CIを全成功とは扱わない。
- 追加レビュー後の関連DB一括試験で、新しい前提不一致を検出。`test_function_only_tables_are_permission_denied_and_grant_mutation_changes_it`は全function_only表に2行以上を要求するが、RG1表は承認済みのclosed単一行だけ。14件成功後に同試験が失敗した。RG1だけsuperuser可視行数を**ちょうど1**、他表は従来どおり2以上とする試験修正をローカル候補に加えた。permission deniedのSQLSTATE検査は維持する。この追加差分は前段レビュー識別値の外であり、レビュー済みとは記録しない。使い捨てDBで関連試験を再実行する。
- 上記試験だけのbinary diff SHA-256は`91287790aae1dcb1f630a331d66694cd55366c7cf0082c02946090efbe83d31f`。使い捨てPostgreSQLの同一隔離環境で、製品認可catalog・その他profile・migration batch role・0028/HEAD試験の**40件を一括成功**（134.28秒）。単独再試験だけで全件成功と呼ばない。review済み候補との差分はこの1ファイルのみで、追加独立レビュー枠を自動延長しない。最終候補の人間確認対象として明示する。
- `probe-product-map.json`の7件追加による写像検査の基準移動についても、全blob・内容SHA-256の前後と原子全文を[受理待ち資料](../features/ur1-recording-rights/step4-derived-followup-decision.md)に追記。正本束縛2件と写像検査の受理単位を無根拠に統合せず、7.7-2・7.7-4に沿う履歴の置き場と単位を正式反映前に確定する。#145統合前の値は暫定であり、承認者・承認日は未入力。#145現HEADは未統合のため、実基線からの最終再導出と正式受理は未了。

## 2026-10-17: N4正式判定と限定試験是正の採用

- POはN4追加行`rg1_restore_gate`を「一致」と正式判定した。理由は、data-model §3-2の削除操作を持たない単一状態行とmanifest `lifecycle.deletion=対象外`が整合し、§11-1に直接割当がないこと。追加1行の判定・理由だけを記入し、旧362行の判定・理由は保持する。承認者氏名は今回の回答に明記されていないため補わない。
- POは独立レビュー後の1ファイル試験前提修正を、RG1単一行だけの限定是正として採用承認した。RG1は**ちょうど1行**、他のfunction_only表は従来どおり**2行以上**、appの直接SELECTは引き続きSQLSTATE `42501`を要求する。binary diff SHA-256 `91287790aae1dcb1f630a331d66694cd55366c7cf0082c02946090efbe83d31f`。独立再レビュー未実施という残余を維持し、このPO採用を本人逐行確認済みとは扱わない。
- #145は確認時点でDraft未統合、origin/developは`3052e0db743877c7f15c0ec10daa0142cba7ab7e`。共有正本の再導出と7.7正式受理資料は実統合後に行い、旧worktreeの暫定digestを正式値へ流用しない。
- 判定反映後のORM受理シート試験は**13件成功**。旧362行の判定・理由をHEADとの対応で全件照合し、N1 103→103、N3 105→105、N4 54→55、N7 100→100、旧行の判定・理由は全件一致。backendの関連126件、Ruff/format/ty、root Ruff/ty、docs-status、shared preconditions、認可catalog1414、function bodies、frozen-baselines不変、tenant-boundary bypassも成功。前ターンの隔離DB関連40件成功は製品・試験コード未変更のまま維持。DB全件とCIの完走は別証跡であり、成功扱いしない。

## 2026-10-17: #145統合後の実基線への再導出

- PR #145の実統合SHAは`188acf839d4a5f4f42e9c7f5025f8bf3931e3bcb`。`origin/develop`をfetchで同SHAと照合した。未受理候補を専用キャッシュのbinary patch・文書へ保全し、`git stash`へ限定退避してfeatureブランチでmergeした（merge HEAD `46ac9ea9d4055e5236f6da59ae964baabb9ac4dd`）。候補を再適用し、Git競合なし。`shared-preconditions.json`の要件書側は#145受理値`ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`、data-model側はU-R1候補`21a85f5e794baaa05376b06aec7185cada6c33c8`を保持。古い未追跡`claude-handoff.md`は保全・再適用対象から除外。
- 現行正本・schema manifestからORMシート4枚をメモリ上で再生成し、363行の対象・正本欄・実装欄が現候補と完全一致。N4のPO判定を含む363行すべて判定・理由記入済み。旧362行の判定・理由は改めて比較して保持する。#145の正本・oracle・履歴へU-R1差分を混ぜない。
- 最新developの9資産と外部凍結入力、および現候補から`frozen_history.py::frozen_projection_content`で全9件のrevision・snapshotを再計算。3件の変更値も6件の不変値も既受理#143記録と完全一致。新snapshot3件とseed `rg1_closed_seed`の`(1,closed)`も不変。正確な前後値は[更新済み判断資料](../features/ur1-recording-rights/step4-derived-followup-decision.md)。既受理履歴・before・#145系列を改変しない。
- 派生3資産の実beforeは#145後`origin/develop`から再算出。shared-preconditionsはblob`4243eb8f…`→`53497616…`、schema-manifestは`ae83ea84…`→`d0efb89b…`（正本SHA `518ca3f6…`→`a4504bbb…`、RG1表1件追加）、probe-product-mapは`09d5b7e6…`→`3f23368f…`（7原子追加）。全文識別値と変更理由は判断資料に記載。3資産はいずれも`baseline_control`を持たず、既存の承認済み先例に従って新たな7.7権威履歴を作らない派生追随と整理する。以前の作業ログにある「この3資産へ新しい7.7記録案」の提案は本調査で撤回し、#143の単一受理記録・seed系列へ未受理記録を加えない。

## 2026-10-18: #145後の全件検査とDB試験前提の追加診断

- ハーネス全件は専用一時領域・2ワーカーで**29,640成功・2 skip、終了コード0**（25分57秒）。ORM・凍結履歴・archiveの関連146件、ORMシート363行の再生成一致、RG1関連隔離DB40件、backend/root Ruff・ty、backend format、認可catalog1417、function bodies、frozen-baselines、shared preconditions、tenant-boundary bypass、docs-statusは成功。backend非DBの1925成功・4 skip・647 DB必須除外はテスト失敗0だがプラグインのDB必須0件拒否で終了コード1であり、全件greenと記録しない。
- DB必須全件初回は152成功後、作業worktreeにfrontendの`typescript`が未導入でNode生成器が`ERR_MODULE_NOT_FOUND`となり停止。`pnpm install --frozen-lockfile`で既存ストアから依存を導入し、lockfileと製品ソースに差分なし。Node生成器の単独実行は成功。
- DB全件2回目は170成功後、試合区分seedの往復試験がmigration 0029へ戻した状態で現行HEADの全認可DDLを適用し、未存在RG1表に到達して停止。0029ではRG1表不在、試合区分表のFORCE RLS・seed専用policy継続を明示確認し、0030 seed投入とHEAD復帰の後で全認可DDLを再適用する試験前提へ限定修正。単独隔離DB試験1件成功。製品migration・認可資産は不変。差分SHA-256は[判断資料](../features/ur1-recording-rights/step4-derived-followup-decision.md)に記録。
- DB全件3回目は172成功後、既存の不変性試験が保護列すべてにBEFORE UPDATEトリガを要求し、RG1の定数CHECKと主キーによる`singleton_id`固定を認識せず停止。manifestの宣言から固定値・主キーを導出し、実DBで完全一致したRG1の1列だけをCHECK保護列とする限定候補を作成。CHECK除去後のID変更と宣言側protected除去の負例を加え、他表のトリガ検査・既存N1〜N5変異検査を維持。同ファイルの隔離DB3件、Ruff・ty成功。DDL・manifest・凍結資産は不変。後続36ファイルの隔離DB診断を進行中。
- これら後発の試験修正は既存の独立レビュー対象外。レビュー枠を自動延長せず、最終候補の本人逐行確認対象として識別する。#143のDraft解除・push・マージは行っていない。9資産・snapshot・seedの既受理値は#145後も不変で、派生3資産だけ完全before/afterを判断資料へ記載した。
- 作業中に#146（pytest一時領域の移送）が`ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`でdevelopへ統合された。旧基線の後続DB診断は117成功の時点で**意図的に中断**し、未コミット候補をbinary patch・文書へ保全してから`origin/develop`をmerge（HEAD `8780eb0a5c3c4fe7a6b8036ff03bb4e4a5bac0e6`）、候補再適用は競合0。新基線で9凍結資産のbefore/after射影18件と外部入力の前後各8件を実計算し、#143の既受理記録案と完全一致。#146はその凍結対象を変更せず、seed・正本も不変。#146の`backend/tests/conftest.py`に対するU-R1差分は0行。中断した診断を全件成功に数えない。
- #146後の関連ハーネス176件とbackend一時領域配線1件は成功。backend/root Ruff・ty、backend format、認可catalog1417、function bodies、frozen-baselines不変、tenant-boundary bypass、docs-statusも成功。backend非DB全件は1926成功・4 skip・648 DB必須除外で実テスト失敗0だが、DB必須0件拒否による終了コード1を別記する。DB必須全件は#146後の使い捨てクラスタで実行中。
- #146後のDB必須全件は606件成功後、0028→0029のFORCE RLS試験が旧版に現行HEAD全カタログを要求して停止。`test_system_vocab_category_fk_db.py`の該当2試験を、0028/0029でFK形状・4表FORCE状態・参照行保持を検証し、HEAD復帰と全認可DDL再適用後に製品カタログ全体を検証するよう限定修正。隔離DBの2件が成功、後続3ファイル22件も成功。差分SHA-256は[判断資料](../features/ur1-recording-rights/step4-derived-followup-decision.md)へ記録。製品DDL・凍結資産は不変。最終候補のDB全件を再実行中。後発試験3ファイルの独立再レビューは未実施で、本人逐行確認も未了。
- **#146後の最終候補実測（2026-10-18）**: 最新`origin/develop`=`ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`を再確認。専用使い捨てPostgreSQLで`backend/tests/db`全630件が32分12秒・終了コード0、同ディレクトリ外の`requires_db`27件が79秒・終了コード0。後者のpytest plugin再読込warning 1件を別記。backend/root Ruff・ty、backend format、`git diff --check`も成功。公開Draft #143は準備HEADのままで、未push候補のCIとは区別する。試験前提の後発3ファイルは独立再レビュー未実施、本人逐行確認未了。9凍結資産・seedの受理済み値は#145・#146取り込み後も全件一致し、新7.7受理値は発生していない。派生3資産の完全前後値は[最終判断資料](../features/ur1-recording-rights/step4-derived-followup-decision.md)へ固定する。
- **公開許可と残余の扱い**: POは2026-10-18の本会話で、既承認の期待値・migration前提・単一行試験修正の採用を維持し、独立再レビュー未実施の最終差分を本人逐行確認対象に明示したうえで、候補コミット・通常push・最終HEADのCI・PR本文/全差分資料更新を許可した。既承認範囲は再承認待ちへ戻さない。本人確認欄は代記せず、Draft解除・マージは別判断とする。TSK-550へは共有ファイルの確定コミット、予定編集、所有解除を通知する。


## 2026-10-18: Codex Dによる#143最終統合準備・TSK-550 Bへの編集解除

- **指示と所有**: DeepSeek停止中の#143統合準備をCodex Dが引き継ぐ。既承認の是正・7.7・限定レビューの採否を維持し、本人逐行確認・Draft解除・マージを代行しない。TSK-550 Bの作業木には一切書き込まない。
- **実基線**: C1ステップ2/#147の実統合`493342be37d4383ca572f8d1c826a3f184a4d213`を`4271ce14c6cb9b518dd28ca78e6e9e8513089791`へ通常mergeし、`5a2be19c29d90e01a7d06d7f566a61cc00b47cc0`。競合なし。追加19ファイルはC1フロント認証と記録・限定誤検知登録で、U-R1のbackend・凍結資産・正本・seedは変化しない。
- **受理値の実照合**: `frozen_history.frozen_projection_content`で実origin/developのbefore9件、実候補のafter9件を再計算し、#143既受理記録案の18 SHA-256および参照snapshot実bytesと完全一致した。正式受理の追加・置換は不要。base revision32→33、repository20→21、runtime16→17、先行受理履歴は維持。
- **検査中**: root全件4workerと、既存disposable PostgreSQL fixtureの専用クラスタを使うbackend全件1workerを開始した。専用ディスク一時領域と#146設定を使用し、除外・timeout緩和・共有DB利用は行わない。全件の実際の終了結果は最終HEADを識別するPR #143の検査記録へ添付し、実行中の状態を成功と記録しない。frontend品質検査も最新統合候補で実行する。
- **検査入口の区別**: ローカルbranch HEADへ`--ci`を直接当てると、CI合成mergeの第1親がbase SHAであるという前提で拒否される。前提の異なる呼出しであり検査を改変しない。ローカルは`--invariants-only`、受理値機械照合を使用し、正式PR受理遷移はGitHub合成mergeのCIで確認する。

### TSK-550 B向けパス別引渡し（本記録を編集解除回答とする）

ここでの「編集解除」はU-R1が追加編集を予定せず占有を外す意味であり、Bの個別承認・正式7.7を代替しない。未統合U-R1枝を基線にする許可ではない。Bは自分の作業木だけを編集し、実際の最新developを取得する。後続で新しい是正が必要になった場合だけ、該当パスを具体的に再調整する。

| パス（波括弧は列挙する全ファイル） | 現在の残編集／編集所有 | 引渡し・統合条件 |
| --- | --- | --- |
| `.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py` | U-R1の宣言・登録完了。既存の解除を維持、追加編集なし | **編集解除済み**。未統合宣言を基線と扱わず、Bの実developと自身の承認計画で判定する |
| `backend/src/pitchlog/authz/{classification.py,product_control_access.py,product_provisioning.py,product_role_contract.py,product_table_access.py}`、`scripts/check_authz_catalog.py` | RG1専用owner・列ACL・撤去・分類・照合の編集完了。追加編集なし | **各ファイルの編集占有を解除**。Bの正式組込みでは先行CのRG1追加集合と既存grant/revoke・負例を保持する。未統合Cをコピーせず、統合後の実developから差分を作る |
| `backend/src/pitchlog/repositories/{operation_registry.py,repository_contract.py}`、`backend/src/pitchlog/authz/runtime_contract.py` | RG1固定2operationと生成契約の編集完了。追加編集なし | **各ファイルの編集占有を解除**。生成元JSONと常に同期し、Bの固定resolver1件の登録はBの承認済みステップ4。Cの未統合生成物を基線にしない |
| `contracts/authz/product/{ddl-elements.json,exposure-facts.json,table-classification.json,probe-product-map.json,function-bodies/manifest.json,function-bodies/schemas/public.sql}` | RG1原子・owner・列権限・public schemaの編集完了。追加編集なし | **各ファイルの編集占有を解除**。Bの候補検証・独立資産準備を止めない。正式登録・manifest/digestはC統合後の実集合から導出し、同revisionの別候補を同一視しない |
| `contracts/authz/product/function-bodies/{functions/*rg1*,column_acl_expectations/*rg1*,policies/*rg1*,roles/pitchlog_rg1_fn_owner.sql,schemas/rg1_api.sql,tables/rg1_restore_gate.sql}` | U-R1専用の確定資産。追加編集なし | Bの別名resolver/owner/列ACL資産はU-R1占有外。RG1資産は既受理内容を保持し、Bは上書きしない |
| `contracts/authz/product/{application-steps.json,capability-catalog.json}` | 今回U-R1差分なし、占有なし | **即時利用可**。B固有のゲートを維持する |
| `contracts/authz/shared-preconditions.json`、`contracts/db/schema-manifest.json`、`docs/design/data-model.md`、`docs/README.md` | 正本・ORM・派生追随は完了。追加編集なし | **各ファイルの編集占有を解除**。Bの正本確定はBの承認範囲で扱う。正式blob/digest・表集合はC統合後の実developから再導出する |
| `backend/migrations/versions/0032_rg1_restore_gate.py`、`contracts/migrations/seed-allowlist.json` | RG1の0032/closed seedは確定、追加編集なし | B固有の候補配置は占有外。B正式migrationのrevision・down_revisionとS0は**C統合後の実Alembic headから決める**。Cの0032を上書き・別内容へ流用しない |
| `contracts/tenant_boundary/{base-allowlist.json,repository-contract.json,runtime-authz-contract.json,history-snapshots/**}` | 本候補の編集は完了。ただし#143既受理候補のhistory/revision/snapshotの**統合順所有はCが保持** | **C→B**を維持。人間確認・#143統合後に即引渡し、Bは実統合SHAと先行履歴を保持して自身のbefore/afterを再導出し別7.7へ出す。理由は同revisionの別候補・履歴の分岐と受理値の無断置換を避けるため。C完了までB全体を待たせる条件ではない |

- Bの読取照合対象は`feature/ux1-fr014-rule-resolution`の計画§3・§10-8以降および候補入口。Bの17SQLは未登録候補で、S0=`0031_intent_selectors`は候補時点の値。C統合後の正式組込みで0032を含む実headへ追随する必要がある。Bのcodec、固定候補SQL、隔離候補試験はU-R1占有外であり、継続可能。
- 古い未追跡`docs/features/ur1-recording-rights/claude-handoff.md`は保全し、今回の最新申し送りは**本コミット済み作業ログ**へ集約する。古い別ファイルを復元済み／最新と扱わない。

### 最終候補の固定と検査記録の保存先

- frontendはPrettier・ESLint・vue-tsc・buildが成功し、68ファイル/1,237件が成功。backend format/Ruff/ty、root Ruff/ty、frozen-baselines不変量、tenant-boundary bypass、認可catalog（1,417項目）、docs-status・設計追随・文書網羅は成功。
- 最終候補の追加変更はこの作業ログのみ。製品・試験・凍結資産は`5a2be19c`から変更しない。root/backend全件は同一製品・試験内容で実行中であり、最終終了コードと件数、最終HEADのGitHub CIはPR #143本文・最終確認コメントへ固定する。
- core-guardは97差分ファイルのうち68ファイルを検出し、本人逐行確認未チェックを終了コード1で拒否した。本人確認を代記せず、この拒否は残す。既存独立レビュー（差分SHA `9fc870cf2159ad8de4d016ccb89472e791659df53e0f20d145f0fc6e7c526836`、P0/P1/P2=0）を維持し、レビュー後にPO採用された試験是正は独立再レビュー済みと扱わない。
- 通常push・最終HEAD CI・PR資料更新は今回の指示で許可済み。全件検査で新たな製品不整合や受理値変更が判明した場合のみ、その具体差分と推奨案を提示する。本人確認・Draft解除・マージと、D4/運用open/実Port接合は本作業の完了扱いに含めない。
