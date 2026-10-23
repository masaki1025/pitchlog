# このタブ全体の引継ぎ固定点（2026-10-23）

この文書は新主担当へ作業を集約するための棚卸しである。記載時点のGit・PR・作業ログを照合した。新主担当が引受を明示するまで各worktreeと編集所有を保持し、引受後に旧タブから並行編集しない。既受理履歴、レビュー回数、本人確認欄を変更しない。秘密値は記載しない。

## A. 引継ぎ対象の全一覧

| 作業 | 区分と実状態 | worktree・枝・HEAD・PR |
| --- | --- | --- |
| TSK-550段階A B・ステップ3置換提出 | 主担当の未完了作業。候補製品差分と7.7正式反映は公開済み。ステップ3全体、TSK-550全体は未完了 | `/home/ymdms/projects/pitchlog-worktrees/feature-ux1-fr014-rule-resolution-followup`・`feature/ux1-fr014-rule-resolution-followup`・`e30edc79a7f90aa27cb14303910676e414c2cab6`・Draft [#174](https://github.com/masaki1025/pitchlog/pull/174)。ローカル=公開HEAD、集約引継ぎ文書1件のみ未コミット |
| 旧TSK-550候補・#152 | 保全対象。#174へ置換済み、再公開・履歴再使用はしない | `/home/ymdms/projects/pitchlog-worktrees/feature-ux1-fr014-rule-resolution-replacement`・`feature/ux1-fr014-rule-resolution-replacement`・ローカル `86045abfa28a0960ddeb6e7469ce89c762029e80`・CLOSED Draft [#152](https://github.com/masaki1025/pitchlog/pull/152) の公開HEAD `401ea4280f3a4c9ae252fade33165acae8b81cdc`。ローカルはremote枝より112コミット先行、未コミット6ファイル |
| 旧TSK-550候補・#149 | 保全対象。旧7.7受理行を変更・移植しない | `/home/ymdms/projects/pitchlog-worktrees/feature-ux1-fr014-rule-resolution`・`feature/ux1-fr014-rule-resolution`・ローカル `67a6a68b73970d2dfc53d35d10a979cbc2441a97`・CLOSED Draft [#149](https://github.com/masaki1025/pitchlog/pull/149) の公開HEAD `96dcb38f1746eb22abbf7cd6027782165b27151f`。ローカルはremote枝より4コミット先行、worktree clean |
| 旧TSK-372／#161置換元 | #172へ置換済みの文書・計画承認履歴を保全。製品是正は統合済み#172の証跡を参照する | `/home/ymdms/projects/pitchlog-worktrees/feature-tsk372-applied-rules-plan`・`feature/tsk372-applied-rules-plan`・ローカル `cfed434776d1354d9fed9c78df19b870979cf911`・CLOSED Draft [#161](https://github.com/masaki1025/pitchlog/pull/161) の公開HEAD `441b078ec8886b50b0dec4e7c2c235b6769a2ec2`。ローカルはremote枝より1文書コミット先行、worktree clean |
| TSK-550ステップ4〜9とU-G1向けresolver供給 | #174の後続未着手。#174に無断混入しない。担当はTSK-550本体、U-X1ドメイン所有を維持 | 正規計画は#174枝の `docs/features/ux1-fr014-rule-resolution/plan.md`。新しい実装枝・PRはまだない |
| U-G1／TSK-395元の8ステップ計画・契約 | 旧主担当が保持した文書中心の未完了作業。元枝は最新developより大幅に古く、製品の試合作成成功を供給しない | `/home/ymdms/projects/pitchlog-worktrees/feature-ug1-game-lifecycle`・`feature/ug1-game-lifecycle`・`67dff5f707dcb2311a35140ae870b44f46e24803`。公開PRなし、upstreamは `origin/develop`、この比較で12コミット先行・826コミット後行。worktree clean |
| #176 O5同期母集合基線是正とcore登録残P1 | このタブの継続例外。詳細は別worktreeの既存引継ぎログ `/home/ymdms/projects/pitchlog-worktrees/fix-us1-o5-observation-population/docs/worklog/2026-10-23-us1-o5-core-path-registration.md` を正として参照。製品経路のO5実行検証は未完 | `/home/ymdms/projects/pitchlog-worktrees/fix-us1-o5-observation-population`・`fix/us1-o5-observation-population`・ローカル/公開 `c1413b250593cce622c2f8a1bc5448c136e299a3`・OPEN Draft [#176](https://github.com/masaki1025/pitchlog/pull/176)。計画追補3ファイル未コミット |
| U-R1向けA/B/C分割同期候補 | U-R1側へ送付した文書のみの別枝。担当受諾・統合は未確認。U-R1製品C登録の編集所有を引き取らない | `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-abc-plan-sync`・`feature/ur1-abc-plan-sync`・`7aea7b44b3f8a5b6e5bac472ab0bca770ba9b6fd`。公開PR・upstreamなし、worktree clean |

関連する[U-G1 preparing限定Draft #175](https://github.com/masaki1025/pitchlog/pull/175)は別の現行実装枝 `feature/ug1-preparing-connection` にあり、公開HEAD `6bed7cf2f8ffd5c1fe95fd9e14b19a8d8a1ffa82`。worktree `/home/ymdms/projects/pitchlog-worktrees/feature-ug1-preparing-connection` のローカルHEADは `d430d839b5623ff0b395f91ebffc9b30de512b35`（公開枝より2コミット先行）。このタブが同枝の編集所有を持つ根拠は確認できないため、**依存先として追跡し、編集・未push差分の移動をしない**。#175はDTO/read componentまで、正式registry/API・保存成功は未接続、TB005 2件と7.7が未成立とPR本文にある。現担当へ所有と受取条件を確認する。

## B. 未公開差分と保全場所

- #174: 製品差分はworktree clean、未pushコミットなし。この集約引継ぎ文書1件だけ未コミットで、保全patchは `/home/ymdms/.cache/pitchlog/handoff/tab-wide-2026-10-23/pr174-tab-wide-handoff.patch`。165ファイルの提出差分は公開HEADにある。公開PR本文は製品差分・検査・残件を記載する。`step3-followup-handoff.md`の冒頭には旧「番号取得用・製品差分未公開」という**過去時点の文言が残る**ため、現状の正は公開PRとHEAD。無断で旧資料を改ざんせず、後続で記録追随の要否を判断する。
- #152: 未コミット6ファイルは `docs/features/orm-schema-migration/acceptance-sheets/{N3-immutability-completeness.md,N7-required-attributes.md,README.md}`、`docs/worklog/2026-10-18-tsk550-replacement-pr.md`、`scripts/generate_orm_acceptance_sheets.py`、`tests/test_orm_acceptance_sheets.py`。他担当のmanifest/ORM差分と重なるため移動・破棄・自動統合しない。保全patch `/home/ymdms/.cache/pitchlog/handoff/tab-wide-2026-10-23/pr152-uncommitted-6files.patch`（逆適用チェック成功）。未push履歴bundleは同ディレクトリの `pr152-local-ahead.bundle`。
- #149・U-G1元枝・U-R1同期枝はそれぞれworktree cleanだがローカル固有コミットを保持する。保全bundleは同ディレクトリの `pr149-local-ahead.bundle`、`ug1-original-local.bundle`、`ur1-abc-plan-sync-local.bundle`。すべて `git bundle verify` 成功。#176の未コミットpatch/bundleは別worktreeの専用ログ `/home/ymdms/projects/pitchlog-worktrees/fix-us1-o5-observation-population/docs/worklog/2026-10-23-us1-o5-core-path-registration.md` に記録済み。
- #161置換元の未push文書コミットも同ディレクトリの `pr161-local-ahead.bundle` へ保全し、`git bundle verify` 成功。旧#161レビュー・承認記録を#172の製品レビューへ無条件に転用しない。
- 旧#149/#152の正式受理行、旧レビュー/承認資料、枝とworktreeを保全し、#174履歴へ直接連結しない。上記保全物は元成果物の代わりに使わず、復元時は隔離worktreeで確認する。

## C. 承認・レビュー・検査の境界

### #174とTSK-550

- 承認済みの計画はTSK-550の9ステップ計画と段階A/開始条件追補。固定5組、既存codec、公開request3項目、DB関数`public.resolve_stage_a_rule(uuid,text,text,boolean)`、A固定実行器のscope注入、製品operation登録0件を維持する。FR-014/DRAW-04のN>R保存拒否、data-model§6-5、認可・配置の個別承認の根拠は[計画](../features/ux1-fr014-rule-resolution/plan.md)と[作業ログ](2026-10-14-ux1-fr014-rule-resolution.md)に記録済み。承認をU-G1保存成功へ広げない。
- #174 v2の**正式7.7受理**は2026-10-23・山田正輝。対象tree `a319cd8fd5b114a2c0b6c1147630d395a5e314ed`、完全値資料SHA-256 `1e3a495d07c3dd7d92cd2b3cffbe80fb6057ad75ded8e7a78bf05e921624ed70`。tenant/seed/oracle各記録案SHAは `757498421e9e2efe0d9ce7d382f1406ab2332bb4210227a8c3004410703b3dc5` / `025aa9a386c49258d8b4b87f8138ba8fd350deec7bdc536207f94890d633881e` / `fa6ef1fb6bcd63e946ea87bb99454a57a270bb2b8b8b1a0f1b1a916f89586f8f`。既受理prefix25/3/12件を保持し#174単一記録で26/4/13件。旧#149/#152の固有行は流用しない。
- 後発のcorpus限定7.7受理も同日・同承認者。旧 `f1c30f7a03d1d377b593df7857c5805364630f3984eef32c1ab1c409c90c5dc1` → 新 `8fa501a4c6f9b2736160f7c49b60630f23505ae9a71590004062b97c74c8a0a3`。対象HEAD `a38387cc`、tree `8b6b2474`、8ファイル差分SHA-256 `1cc3862a9d434d4b6fd4960c8f4462f0a851f19b541b18be186e8e21ea2e94ce`。理由はrepository-contract内部source_digestの是正。9資産射影・外部8ファイル・snapshot・3記録案は不変として照合。受理はPR全体の本人逐行確認ではない。
- 既済みレビューを維持する。9ステップ計画の正式敵対レビューは全文/差分/P0限定の3回、A追補は基本2回。ステップ3正式組込のコアレビューは既定2回を使用。0033衛生・probe写像の追加独立1回、#174移植限定1回、v2 revision22→23限定1回、後発source_digest/8ファイル限定1回をそれぞれ指定対象で使用済みと記録している。既済み全文を反復しない。最終のcorpus pin・ORM分類・受理記録・0033試験追随・リンク是正を、各限定レビュー済みと読み替えない。**新たな包括追加レビュー許可は確認できない**。指摘の個別採否は[既存作業ログ](2026-10-14-ux1-fr014-rule-resolution.md)と[ステップ3引継ぎ](../features/ux1-fr014-rule-resolution/step3-followup-handoff.md)を参照。
- #174公開HEAD `e30edc79`のローカルroot全件は29,910成功/2 skip、root Ruff/tyと関連基線は成功。backend全件の初回は3,126成功/5失敗/4 skip。DB4失敗は旧revision参照を0033へ是正して限定4件成功。残るO5母集合欠落はdevelop由来で、#176の実統合後に正式基線から再検査する。最新CI run `39835429345` は同HEADで**failure**（`backend`、`core-guard`）。旧CI成功を新基線の成功へ流用しない。本人逐行確認は未実施。既存DB適用・S4公開・Draft解除・マージは未許可。
- ステップ3全体の合格・ステップ4以降の完了は未記録。次は#176実統合と実develop追随、共有受理履歴と0034親の照合、backend/root必要検査、規約上のレビュー・最終CI、本人確認資料を更新する。受理対象値が変われば正式履歴を書き換えず規約上の新受理方法を提示。#174→#173の共有履歴統合順は人間指定で確定済み。#173への通知は送付済み、担当の明示受諾は未確認。

### U-G1／TSK-395とresolver供給

- 元の8ステップ計画は2026-10-14に人間承認。U-R1のRG1作成側①〜⑤はコミット`79e3da4a`で受理済み。作成と開始を別操作にし、D4外部台帳は未承認・`preparing`作成の一律条件にしない。元計画のステップ1はU-X1規則解決の担当受理が残ったままで、ステップ1完了コミット・ステップ2の製品作成成功は元枝にない。開始側の初期権物理発行・U-M2 DTO/同一scope保存・側識別・全ロック順はステップ3前条件。TSK-547はU-G1マージ前条件。根拠は元worktree `/home/ymdms/projects/pitchlog-worktrees/feature-ug1-game-lifecycle/docs/features/ug1-game-lifecycle/` の計画・申し送りと同worktreeの作業ログ。
- #174/TSK-550ステップ3が供給するのは**DB関数・厳格codec・非公開S0〜S3**。公開resolver request/result型、固定function operationの製品登録、4失敗分類とU-G1の同一scope試合保存接続は**未提供**。TSK-550ステップ4=resolver1登録、5=公開型/分類、6=実関数2接続・故障注入、TSK-395ステップ2=実HTTP/RG1/INSERTと全取消の結合。A/B/C分割ではBとU-R1 Cの機能上の相互待ちは設けない。`#174=ステップ3`を`公開resolver提供済み`と扱わない。
- #175は別実装枝の部分作業として上表の状態を維持し、所有側へ接続型と正式operationの供給待ちを知らせる。受諾・担当引受は本タブから代記しない。

### #176とU-R1同期枝

- #176の原計画承認、O5正本、計画・製品レビュー、現在の追補レビューP0、保全patch、CI実行状態、U-S1への送付・受諾未確認は別worktreeの専用引継ぎ `/home/ymdms/projects/pitchlog-worktrees/fix-us1-o5-observation-population/docs/worklog/2026-10-23-us1-o5-core-path-registration.md`の記録を参照する。追補固有の6.1処置と6.3⑤承認前にcore設定へ触れない。本人確認欄は未成立として扱う。
- U-R1向け `7aea7b44` はA=登録0、B=resolver1、C=RG1専用2の既承認分割を担当側計画へ反映する**送付候補**。TSK-392へ照会済みだが取り込み・受諾の証拠はこのタブで未確認。U-R1所有の関数・権限・履歴を編集しない。後続が必要なら担当へこのコミットの採否を確認する。

## D. 対象外とした作業・理由

- [#120](https://github.com/masaki1025/pitchlog/pull/120) U-F6接続、[#125](https://github.com/masaki1025/pitchlog/pull/125) U-F8先行画面、[#141](https://github.com/masaki1025/pitchlog/pull/141) 共有実行器A、[#158](https://github.com/masaki1025/pitchlog/pull/158) 起動入口core登録、[#172](https://github.com/masaki1025/pitchlog/pull/172) applied_rules不変性、[#162](https://github.com/masaki1025/pitchlog/pull/162) 正本/ORM側は**統合済み**。成果は各PR/統合SHAを参照し、このタブの未完編集として再開しない。U-F8全体、TSK-550全体の完了を意味しない。旧#161自身は未マージで、上表の保全対象として維持する。
- #156・#159・#161・#162・#163のDeepSeek担当作業、U-R1のC登録・#173、C1/P-7、P-6の封印・曝露・資格留保・比較検証、U-S1本体は**別担当の編集所有**。このタブが引き取る証拠はない。#173は#174の後続依存として追跡し、正式履歴を上書きしない。P-6の実測資料は本タブで確認できないため、内容を推定して記載しない。
- `/home/ymdms/projects/pitchlog-worktrees/feature-ux1-t1t2-plan-revision` 等、上表にない他のworktreeは本タブの担当・編集所有を示す証拠がなく、一覧だけを根拠に引き取らない。現主担当へ個別照合を依頼する。

## E. 固定時点の運用と次の停止条件

1. 新主担当がこの引継ぎと各worktreeの所有を明示的に引き受けるまで、元worktree・枝・保全物を削除しない。引受後、旧タブは並行編集しない。
2. #174/旧#152/#149/U-G1元枝/U-R1同期枝は、引継ぎ後に新しい製品・共有資産編集、push、PR操作を旧タブから行わない。#176だけは人間が認めた例外に従い、必要な6.1・6.3承認を得られた場合に限り、core登録是正→検査→最終CI→本人確認資料まで担当を継続する。承認未成立なら同じ保全点で待つ。
3. #174と#176のPR全体の本人逐行確認、Draft解除、マージ、既存DB適用、試合作成公開は人間判断。空欄を代記しない。長時間の検査は各PRのrun IDと対象HEADで成功・未完走・失敗を分け、他候補へ成功を転用しない。

## F. 根拠の限界

人間メッセージで明示された`#174→#173`、旧#149/#152保全、#176の新PR禁止・継続例外、P-6独立担当の指定は会話由来の有効指示として保持する。各PRの公開状態・HEAD・CIはGitHub、worktree状態はGitで確認した。担当間の**送付**は既存コメント・作業ログで確認したが、相手の**明示受諾**は確認できない。Notionの最新担当状態、P-6の検証値、#175現担当の編集所有はこの固定点では未確認。
