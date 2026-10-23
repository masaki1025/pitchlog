# U-R1新5 / PR #173 主担当タブへの引継ぎ（2026-10-23）

この文書は既存worktreeをそのまま引き渡すための固定点である。2026-10-23時点の調査結果を記し、過去の承認・レビュー・正式履歴を変更しない。先行の[PR #173作業ログ](../../worklog/2026-10-22-ur1-pr173-review.md)と[7.7候補資料](step5-pr173-7.7-acceptance-brief.md)を併読する。後者の「受理待ち」「未反映」は作成時点の表示であり、下記のローカル受理反映が現在状態である。

## 1. 担当と固定識別値

- 担当: TSK-392 / U-R1新5の初期記録権付与候補、D4/V12・復旧世代の接続候補、PR #173の7.7・認可・試験の後続。RG1新4はPR #143で統合済みだが、RecordingRightsPort全体と新5は未完了。
- worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-initial-rights-followup`。ブランチ: `feature/ur1-initial-rights-followup`。ローカルHEAD: `6af8c80156ceec615e0749ace1187129e95bd642`。候補比較元: `760c04d540b22190cab076165f1b4e35ae473a1f`。
- 確認時の`origin/develop`: `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`（#159統合を含む）。ローカルHEADはこの最新developを取り込んでいない。#174は未マージのため、現在の候補を最新develop上の最終版と呼ばない。
- 公開[Draft PR #173](https://github.com/masaki1025/pitchlog/pull/173)の公開HEADは`dac2ff15cd35b63a7c9f5bc69cd6a87f15e2ed5f`。公開差分は`step5-followup-handoff.md`の文書1ファイルだけで、製品・試験・正式7.7反映は未公開。PR冒頭の「番号取得用・製品差分未公開・マージ不可」を維持する。
- 旧[PR #156](https://github.com/masaki1025/pitchlog/pull/156)は未マージ・open。旧枝、是正HEAD`92c5b9ec38c3b49c9a1c8c11b1d27d2a232099e3`、正式受理記録、承認・レビュー履歴を保持する。製品差分と未決事項の公開引継ぎ前に閉じない。

## 2. 作業ツリーと保全

- ローカルには追跡済み17パスの変更と未追跡の製品・試験・資料・snapshot群が残る。製品候補は`backend/src/pitchlog/recording_rights/initial_grant.py`、認可・repository生成物3ファイル、`backend/tests/test_initial_recording_right_candidate.py`など。正式7.7の#173単一記録と新snapshot10件は**ローカル作業ツリーだけ**に反映済み。Git履歴にはまだコミットされず、pushもしていない。`git status --short`で全数を再確認する。
- 作業ツリーの事前保全: `/home/ymdms/.cache/pitchlog/pr173-pre174-preservation-20261022/`。`tracked.patch`、`untracked.tar`、45実ファイルのSHA-256を列挙した`manifest.json`を持つ。patch SHA-256=`9054676bc09201335cff2b6f455edbff9a475a5376db53adb5b5170583971a29`、tar SHA-256=`dd684cb7375fa5d80bb5dab0184f37ba50d2327faaa287bdee6e23c2c74ef102`、manifest SHA-256=`41fc7fd0156a6104550b38cb3f4a7c99896795d64aea148fa3a179d98e8d56b3`。順序裁定とTSK-544回答を追記した作業ログの追加保全も同ディレクトリに置く。下記引継ぎ文書を含む最終保全のSHAは末尾に追記する。
- 旧#170候補は`/home/ymdms/.cache/pitchlog/pr170-local-candidate-preservation/`、旧worktreeと承認資料にも保持。旧#156/#170の受理行を#173へ移植しない。秘密値は保全資料へ転載しない。

## 3. 進捗の区別

| 状態 | 対象 |
| --- | --- |
| 統合済み | RG1新4 / #143、開始時初期付与を定めたsync-protocol / #148、文書のみの#170、#162の正本・派生資産、#172の25件目の受理履歴。各統合SHAの詳報は既存計画・作業ログを参照。 |
| ローカル候補実装済み | 新5の隔離初期付与、V12暗号化再交付、拒否・競合試験、限定認可登録、fixture是正、#173の7.7単一記録・snapshot反映。実台帳・実端末資格・実鍵・実RecordingRightsPortとの製品接続は未提供。 |
| 未着手・未完了 | #174統合後の再導出と新実値の必要な正式受理、製品差分の公開、最終CIと本人逐行確認、旧#156の引継ぎ後クローズ、U-G1/U-S1の実入口接合、新6実経路試験、D4実配置・運用open。 |

## 4. 承認と未承認

- [計画](plan.md)の承認済み新5範囲を維持。意味仕様は「開始時に初期付与、preparing作成時と復元調整解除時には付与しない」「既存D4対象0件ならRG1解除のための新D4発行0件」「復元後もD4を再利用しない」。限定正本改訂は#148で統合済み。
- D4の設計方針は業務DBの復元範囲外にある別故障領域のprimary＋同期standby、旧primaryフェンス、耐久性を証明できない障害時は新規発行停止。V12は同一要求・認証済み同一端末への暗号化再交付、端末資格は認証と結合し自己申告IDを信用せず、復旧世代は毎書込で照合して不明・不一致では既存世代を含め停止する。これらは設計と隔離候補作成の承認であり、実配置・有料資源・鍵/端末資格の本番提供・運用openの承認ではない。
- #173の7.7正式受理は、山田正輝による2026-10-22の会話内承認。受理対象はローカルHEAD`6af8c80156ceec615e0749ace1187129e95bd642`、候補tree`a4ecb8cf9d76dc4e5183f0559f9cc8d3937ad4f7`、比較元`760c04d540b22190cab076165f1b4e35ae473a1f`、binary差分SHA-256`19a98d87cd61c346235dd9c98d1979ca49ac6bb7c7d6d9e44811a79fe880b8bf`、payload案SHA-256`eefc3f6b5496c75427ce15a05d947315f55671bfe5094a4b61fb5d1afb5999ac`、単一記録案SHA-256`9e8f7ed75a2edff26934b0baf389492167c12b54543f8bc49794e66015861f19`。9資産の完全前後値、8外部対象、snapshotとcorpusは上記資料に記載。既受理25件と末尾#172、before側を保持し、#173単一記録へ実承認者・日付を転記した。proposalファイルは承認前SHAを保全し、正式ローカル行との差は承認メタデータ2項目。現基線以外への承認の自動延長はしない。
- 未承認: #174後に変わる受理対象実値、実台帳の配置・耐久性、鍵管理・端末資格の提供と責任者、実Port/U-G1/U-S1接続署名と全ロック順、運用open、共有DB適用、本人確認、Draft解除・マージ。新しい仕様・認可・凍結差分には別ゲートが必要。

## 5. レビュー

- 旧#156候補の独立レビューP0/P1/P2=`0/2/0`、旧#170の限定レビュー=`0/0/0`を保全。#173で許可された追加差分レビュー1回は**使用済み**で、fixture・25件履歴保持・新受理単位・runtime/corpus/snapshotへの直接影響をレビューし、`0/0/1`。P2の古い状態表記を採用修正した。既存レビューの対象と回数はリセットしない。
- #173のP2反映後の資料/作業ログ2ファイル、正式受理後の承認メタデータと本引継ぎ追記は独立再レビュー未実施。本人逐行確認は未実施。追加レビューの未消費許可は、この引継ぎ時点で確認できないため**なしと扱い、推定しない**。

## 6. 検査と実行環境

- 上記保全候補版のルート全件`uv run pytest -n 4 tests/`: **29,919 passed / 2 skipped / 0 failed**（947.06秒）。archive49件、製品・生成契約の限定104件、Ruff・ty、backend Ruff整形検査は成功。この結果を#174後の再導出版へ流用しない。
- backend全件は**未完走**。初回は当worktreeの`frontend/node_modules`未導入でTS生成器の4件が失敗し、`pnpm install --frozen-lockfile`後の4件単独再試験は成功。再実行は52件成功・失敗0件時点で中断した。単独成功をbackend全件成功としない。共有領域や他担当の長時間Viteプロセスは操作しない。引継ぎ確認時、このworktreeでpytest/ruff/tyの実行中プロセスは見つからなかった。
- 公開#173 HEADのCIは文書1ファイルに対するgreenで、backend/frontend jobはskip。**製品候補の公開HEADに対するCIではない**。新主担当は隔離DB・必要な専用一時領域・低並列を用い、再導出版の全件と必須CIを別途完走させる。

## 7. 担当間の受理と所有

- U-G1のpreparing作成側RG1接続受理は`79e3da4a`。U-S1のRG1③-a/⑧Port署名・呼出位置・同一transactionの固定関数口は確認済み（既存[接続契約](connection-contract.md)と計画132行付近）。これを新5の初期付与・D4/V12・実Portの担当受理や実接合完了へ拡張しない。新5でのU-G1/U-S1公開署名、DTO、全ロック順、不明commit時の再試行境界は未受理。TSK-544のJ6原入力・ACL照会は[作業ログ](../../worklog/2026-10-22-ur1-pr173-review.md)で項目別に回答したが、相手への直接送達・項目別受領は未確認。
- 共有資産のPO統合順は**#174→#173**で確定。再裁定を待たない。[#174担当への通知](https://github.com/masaki1025/pitchlog/pull/174#issuecomment-6339090455)は送達済み。#174は確認時に未マージ、公開HEAD`e30edc79a7f90aa27cb14303910676e414c2cab6`で製品・認可候補を公開。現公開差分との正確な重複パスは`backend/pyproject.toml`、`backend/uv.lock`、`backend/src/pitchlog/authz/runtime_contract.py`、`backend/src/pitchlog/repositories/{repository_contract,tenant_context_contract}.py`の5つ。#174後に派生値が変わり得るため、現#173の9資産・corpusも実ファイルから再照合する。#174の未統合枝をdevelop基線にしない。
- 550にはRG1新4の共有ファイル編集所有を解除済み。TSK-506・U-S1・認証/鍵管理・外部D4台帳の担当受理と実提供は別々に管理する。#176のcore登録是正とP-6独立検証は**別担当の継続作業**であり、このworktreeから編集・代行しない。

## 8. 新主担当の次手と停止条件

1. まず本worktreeの`git status`、保全パッチ・tarのSHA、公開#173/#174状態を照合し、未コミット差分を隠さず保持する。
2. #174の実統合SHAと共有パスを確認する。最新developをこの枝へ**merge**で取り込み、#174の履歴と権限を保持して、5重複パス、9凍結資産、25件の既受理履歴、snapshot、corpusを実ファイルから再導出する。正本・意味仕様・履歴が変わる場合は旧受理との差分と必要な正式ゲートを提示する。無関係な基線更新だけなら既承認の不変性照合による追随条件を確認する。
3. 必要な7.7の新実値を正式受理してから、候補・履歴・snapshotを整合させ、独立レビューの対象差分を確定する。未受理値を正式台帳へ先行入力しない。本人逐行確認は代記しない。
4. 製品・試験差分を#173へ公開し、PR冒頭の番号取得表示を実態に合わせて更新する。全検査と最終HEADのCIを確認し、公開引継ぎが成立したら旧#156へ置換先・未マージ・保全済みを記載してクローズする。#173のDraft解除・マージ、既存DB適用、資源購入、運用openは別判断。

**このタブの停止点**: 本文と保全を固定後、新しい製品実装・共有資産編集・push・PR操作をしない。新主担当が引受を明示するまで、worktree・枝・候補・保全物を保持する。

## 9. 会話で確定した判断と出所の限界

- 「#174→#173」は2026-10-22のPO指定。#174先行中に#173の衝突資産をpushしない。#174統合後、受理対象値が変われば新しい正式受理が必要。候補版の29,919件成功を再導出版へ流用しない。
- 旧#156は#173の製品・試験・未決事項の**公開**引継ぎまで保持する。#173の番号取得文書だけでは引継ぎ完了にならない。
- J6については、U-R1新5の実装責任とdata-model接続窓口を分けた。既存`SyncEvent`/`event_source()`だけでは原wire・codec版の保存証明にならず、T8/T9の既決原子境界だけを受理した。相手担当の正式受領と物理型/ACLは未確認。
- #174担当の個人名、#176の現在の完了度、P-6の封印・曝露・資格留保・比較結果はこのworktreeから根拠を確認していない。各担当の引継ぎを参照し、ここで受理済みと補完しない。

初版引継ぎ時のパッチ・未追跡ファイル・各ファイルSHAは`/home/ymdms/.cache/pitchlog/pr173-tab-handoff-20261023/manifest.json`で固定した。この全作業補遺を含む最終状態は`/home/ymdms/.cache/pitchlog/pr173-all-work-handoff-20261023/manifest.json`へ別に固定する。いずれもGitコミット済み・公開済みと混同しない。

## 10. このタブの全作業台帳（#173以外）

以下はこのタブの会話、作業ログ、Git worktree、公開PRを突合した棚卸しである。状態はタスク全体と個別PRを分ける。別担当のworktreeをこのタブの編集所有へ取り込まない。

| 作業・状態 | PRと成果 | 現在の残責任・次手 |
| --- | --- | --- |
| **TSK-394 / U-M2（製品分割は統合済み、接続は待機）** | [#121](https://github.com/masaki1025/pitchlog/pull/121)で記憶保存、[#124](https://github.com/masaki1025/pitchlog/pull/124)でGET・復元候補、[#126](https://github.com/masaki1025/pitchlog/pull/126)でステップ4の品質・接続記録を統合。正式DoD・レビュー・検査は[計画](../um2-lineup-memory/plan.md)と[作業ログ](../../worklog/2026-10-13-um2-lineup-memory-plan-review.md)。現存の専用worktreeは見当たらず、旧`/tmp/pitchlog-um2-lineup-memory-step3`も存在しない。3枝はGitに残る。 | U-G1が試合スタメン確定と同一scopeの`save_lineup_memory`呼出し、紅白戦後攻側記憶、側識別・守備位置DTO・全取消を接合する。U-F8がGET 204/200、差し替え必須候補の画面採用を接合する。双方の実装完了・担当受理は未確認。U-M2 API/operationの統合を接合済みと扱わない。再編集は新主担当が所有・計画ゲートを照合する。 |
| **core-guard是正（完了・統合済み）** | U-F8登録後の固定試験前提を[fix #130](https://github.com/masaki1025/pitchlog/pull/130)で修正・統合。文書のみの#126も統合済み。U-F5/#127担当へ両登録維持を[通知](https://github.com/masaki1025/pitchlog/pull/127#issuecomment-6150461510)。記録は[作業ログ](../../worklog/2026-10-14-core-guard-uf8-postmerge-tests.md)。 | 本タブの未実装修正は確認されない。#127と以降の登録変更は各担当の所有。#130の計画3回・コード2回のレビュー記録は同作業ログに保持し、最終slug P0反映の独立再レビュー未実施もそのまま残す。 |
| **U-R1接続/計画同期（計画は承認済み、局所枝は履歴保全）** | `feature/ur1-abc-plan-sync`に共有実行器A/B/Cの承認同期コミット`7aea7b44`があり、公開PRは確認できない。`feature/ur1-recording-rights`には承認済み[9ステップ計画](plan.md)、RG1・D4候補・接続契約がある。 | Aは#141で統合、C1は#144で先行し、RG1新4は#143で統合済み。局所枝は後続developの代わりに使わない。計画上の未実装は新5〜9。 |
| **RG1新4（完了・統合済み）** | [#143](https://github.com/masaki1025/pitchlog/pull/143)、実統合SHA`156dd139`。単一closed行、読取2関数、常閉・認可・凍結/seed受理と隔離DB試験。レビュー/DoD/所有解除は[長期作業ログ](../../worklog/2026-10-15-ur1-recording-rights.md)と[新5準備ログ](../../worklog/2026-10-18-ur1-step4-closeout-step5-prep.md)。 | RG1新4の完了を全Portの提供と扱わない。`feature/ur1-recording-rights`の未追跡`claude-handoff.md`は古い時点の別ファイルで、復元済みの最新申し送りとは扱わない。実worktreeに保持し、保全tarにも収めた。#143側のguard3ファイル・共有編集所有は550へ解除済み。 |
| **TSK-547 初期付与時点の正本化（完了・統合済み）** | [#148](https://github.com/masaki1025/pitchlog/pull/148)でsync-protocol v0.9を2026-10-19の人間承認に従い正式化。`feature/tsk547-start-grant-canonical`はclean、HEAD`f69c6b3daded6481d63dedd9ac65550046a61a13`。正式7.3審査・CI是正履歴は[新5準備ログ](../../worklog/2026-10-18-ur1-step4-closeout-step5-prep.md)。 | 「開始時だけ付与」「preparingに付与しない」「対象0件時のRG1解除」「復元後D4非再利用」を新5候補で守る。#148の正本承認を新5物理資産・Port・運用open承認に流用しない。 |
| **U-R1新5旧#156（PR open、ローカル是正履歴保全）** | 公開[Draft #156](https://github.com/masaki1025/pitchlog/pull/156)はHEAD`73ebf8ee`、文書・旧候補。ローカル`feature/ur1-initial-rights`はHEAD`92c5b9ec`でcleanだが公開追跡枝より47コミット先行。旧正式受理記録とレビュー履歴は保持。 | #173の**製品・試験・未決事項が公開**されるまでcloseしない。旧記録の書換え・同PR番号重複受理・force pushは禁止。旧候補の追加差分へ旧7.7承認を自動延長しない。 |
| **U-R1新5旧#170（PRは文書のみ統合、ローカル製品候補は未統合）** | [#170](https://github.com/masaki1025/pitchlog/pull/170)は`7717b986`で文書2ファイルだけ統合。置換worktree`feature/ur1-initial-rights-replacement`はHEAD`d41c8b8b`、公開枝と分岐しローカル専有6コミットと未コミット候補55ファイルが残る。旧承認資料・レビュー・P2差分・正本§6-1候補を保全。 | 最新の#173とは別の**比較元候補**として保持し、#170公開ブランチへ追加pushしない。#162後のdata-model v0.12へ§6-1を追随する際は、旧worktree値をそのまま上書きしない。現#173へ未統合の必要差分が移ったか実ファイルで照合する。 |
| **U-R1新5現#173（進行中、引継ぎ停止中）** | 上記1〜9節。ローカルHEADは公開HEADより6コミット先行し、未コミット候補46実ファイル。正式受理済み候補の履歴反映はローカルのみ。#174先行、#173後続。 | #174実統合後に再導出、必要なら新7.7正式受理、製品/試験公開、最終CIと本人逐行確認。新主担当の明示引受まで本タブは追加作業をしない。 |
| **U-R1新6〜9・全Port（待機/未着手）** | [計画](plan.md)の新6は通常/緊急引き継ぎ、新7は復元ライフサイクル、新8は本物のRecordingRightsPort登録・U-S1/T8/管理者入口の実接合、新9は全凍結・品質照合。復元系10 IDは2026-10-08のPO裁定でU-R1へ送ると[U-S1作業ログ](../../worklog/2026-10-08-us1-sync-apply-core.md)に記録。 | D4実台帳の非再利用とフェンス、鍵・端末資格、復旧世代、U-G1/U-S1/506接続の担当受理と実提供が必要。実経路のB7/B10・D5未消費・全取消は新8の必須結合試験。独立隔離候補を実Port合格や本番耐久性とみなさない。 |
| **TSK-544 J6接続照会（回答記録済み、送達/受領未確認）** | [#173作業ログ](../../worklog/2026-10-22-ur1-pr173-review.md)末尾で原入力保存型/ACLを要修正、T8/T9原子境界を受理、同期保存器・HTTP/読取provider実装をU-R1新5の担当外として回答。 | 相手の公開型・codec・物理型・ACL・実装責任の項目別受領は未確認。J6純計算・P-7同値性はTSK-544/U-S1側。別担当worktreeは編集しない。 |

## 11. 旧worktree・未公開差分・保全物

| worktree絶対パス / ブランチ | 固定HEADと公開状態 | ローカル差分・保全 |
| --- | --- | --- |
| `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-abc-plan-sync` / `feature/ur1-abc-plan-sync` | `7aea7b44b3f8a5b6e5bac472ab0bca770ba9b6fd`。公開PRなし、現在developとの差分で専有1コミット | clean。`/home/ymdms/.cache/pitchlog/ur1-all-tabs-handoff-20261023/feature-ur1-abc-plan-sync/`と同`bundles/`にmanifest・bundleを保全。 |
| `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-recording-rights` / `feature/ur1-recording-rights` | `b06971deceeb86711f73859592357ff0482e2f51`。#143公開HEADと同じ | 未追跡`docs/features/ur1-recording-rights/claude-handoff.md`1件。他の追跡差分0。上記保全rootの同名ディレクトリにtar・manifest。内容は2026-10-14中心で後日の回答に優先しない。 |
| `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-initial-rights` / `feature/ur1-initial-rights` | `92c5b9ec38c3b49c9a1c8c11b1d27d2a232099e3`。#156公開HEAD`73ebf8ee`より47ローカルコミット先行 | clean。上記保全rootの同名ディレクトリと`bundles/feature-ur1-initial-rights.bundle`に保存。 |
| `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-initial-rights-replacement` / `feature/ur1-initial-rights-replacement` | `d41c8b8bdf99674761a80ca49e828bd7eb5da2a1`。#170公開HEAD`b3efd492`とは分岐し、公開追跡枝に対して18コミットbehind/6 ahead | 追跡30パス・未追跡25パスの候補。上記保全rootの同名ディレクトリにpatch・tar・各ファイルSHA・6コミットbundle。旧保全`/home/ymdms/.cache/pitchlog/pr170-local-candidate-preservation/`も保持。 |
| `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-initial-rights-followup` / `feature/ur1-initial-rights-followup` | `6af8c80156ceec615e0749ace1187129e95bd642`。#173公開HEAD`dac2ff15`より6ローカルコミット先行 | 初版[manifest](/home/ymdms/.cache/pitchlog/pr173-tab-handoff-20261023/manifest.json)と`bundles/feature-ur1-initial-rights-followup.bundle`に保全。今回の補遺を含む最終版は`pr173-all-work-handoff-20261023/`に別に固定する。 |
| `/home/ymdms/projects/pitchlog-worktrees/feature-tsk547-start-grant-canonical` / `feature/tsk547-start-grant-canonical` | `f69c6b3daded6481d63dedd9ac65550046a61a13`。#148公開HEADと同じ、統合済み | clean。Git履歴が保全物。 |
| `/home/ymdms/projects/pitchlog-worktrees/fix-core-guard-uf8-postmerge-tests` / `fix/core-guard-uf8-postmerge-tests` | `4b4dab9a052c895f21163436cffcf8a82236d291`。#130公開HEADは`6416f567`、PR統合済み | clean。追加文書コミットはリモート追跡枝と同一で、#130の公開HEADそのものには含まれない。Git枝を維持する。 |

`/home/ymdms/.cache/pitchlog/pr170-rebase-analysis/`と`/tmp/opencode/ur1-census-candidate`は比較・診断用のdetached worktreeとして存在するが、製品提出枝と確認できない。削除せず、引継ぎ後に由来を確認する。TSK-394旧`/tmp`専用worktreeは現存せず、3統合PRとGit枝で追跡する。保全bundleは同じGit object databaseの既存親コミットを前提とする薄いbundleで、`git bundle verify`は全件成功。worktreeと枝も保持する。

## 12. 全作業に共通の受理・レビュー・検査境界

- **TSK-394**: 計画は2026-10-13に人間承認済み、正式カードの追加DoDなしは同作業ログで確認。#121の直接token迂回P0と競合P0への改訂・限定再レビュー・人間逐行確認・7.7受理は#121差分に限る。#124のGET・oracle・7.7も当該PRに限る。#126は文書のみ。最終U-G1/U-F8接合は同計画の未チェック項目で、過去CIを接合試験に読み替えない。#124最終HEADの12 CIジョブgreenと関連実DB94件等は[計画](../um2-lineup-memory/plan.md)に記録。現在developでの再実測は本引継ぎでは行っていない。
- **#143新4**: 所有側代替受理・data-model正本・単一closed seed・9資産7.7受理、独立レビューと後発未再レビュー差分は[作業ログ](../../worklog/2026-10-15-ur1-recording-rights.md)に保全。統合済みDoDを再承認待ちへ戻さない。実Port・運用open・D4耐久性は別。
- **#148正本**: 正式7.3の審査対象・採否と最終反映差分の独立再レビュー未実施は[新5準備ログ](../../worklog/2026-10-18-ur1-step4-closeout-step5-prep.md)に保全。正本の人間承認は新5具体DDL・鍵・配置の承認ではない。
- **#156→#170→#173**: 旧候補のレビューP0/P1/P2=`0/2/0`、#170の限定追加レビュー=`0/0/0`、#173の1回=`0/0/1`。#156のcensus限定是正と履歴単位のP1は旧[置換作業ログ](../../worklog/2026-10-21-ur1-pr156-replacement.md)に採否を残す。新5隔離候補の先行全文/限定/事前レビュー3回とP2/P1反映後の未再レビュー差分は[新5準備ログ](../../worklog/2026-10-18-ur1-step4-closeout-step5-prep.md)にある。これらは#173の最終再導出版のレビュー済み認定へ自動延長しない。使用済み枠は各資料の対象にだけ結び付け、未消費追加枠の存在は確認できない。
- **検査の帰属**: #130の最終CI green/harness 28,937件、#124のCI 12ジョブgreen、#143/#148の統合検査、#173現ローカル候補の29,919件はそれぞれ異なる対象版。#173 backend全件は未完走。#173公開PRのgreenは番号取得用文書HEADに対するものでbackend/frontendはskip。旧#170/#156の診断・単独試験も現候補の全件合格へ読み替えない。DB/認可試験には専用の使い捨てPostgreSQLクラスタと適切なディスク側一時領域が必要で、共有DBを使わない。
- **実行中プロセス**: このタブ所有のU-R1/TSK-394/core-guardのpytest・ruff・tyは確認時点で稼働していない。他担当由来のViteプロセスは存在するが、本タブの検査・引継ぎ対象として停止・削除しない。

## 13. 提供責任、未送達、停止条件と棚卸しの限界

- **U-G1**: TSK-394の試合スタメン確定→U-M2保存operation、U-R1新5の試合開始時初期付与を同一scope・全取消に接続する担当。U-G1のRG1 preparing側受理`79e3da4a`と新5の開始側契約受理は別。側識別、守備位置DTO、D4/V12開始結果、U-M2を含む全ロック順の項目別受理は未確認。
- **U-S1 / TSK-506**: U-S1のRG1③-a/⑧契約は既受理だが、新5の実Port登録と同期T8/T9・commit不明境界は未提供。506はHTTP/wire入口の所有者。#173の候補用adapterは製品Portではない。実Port提供コミット・登録箇所・J6 raw/codec保存型・資格失効競合の所有側回答は未確認。TSK-544への項目別回答はローカル作業ログとこのタブの会話で提示済みだが、相手の受領・実装担当の合意は**未送達/未確認**。
- **認証・鍵・D4運用**: 認証に結び付く端末資格の発行/失効、V12再交付鍵の保管/ローテーション/旧暗号文の再交付、外部台帳の配置・fence・同期耐久性・運用責任・費用は担当受理/実配置が未確認。既存認証署名鍵の破棄手順をV12鍵へ無断流用しない。証明不能時の新規D4発行停止と復旧世代照合不能時の全書込停止を維持する。新主担当は既存[物理契約候補](step5-physical-contract-annex.md)と[担当別受理シート](step5-owner-acceptance-sheet.md)を旧#170 worktreeから照合し、未回答だけを担当へ出す。
- **統合順と所有**: #174担当には重複・引渡し条件をPRコメントで送付済み。POは#174→#173を固定済み。#174の製品候補は公開されたが未統合で、実developではない。正確な直接重複は前節の5パス。共有凍結資産は#174後の実入力で再導出し、既受理履歴を保持する。#176のcore登録是正はその担当が編集所有を保持し、P-6は独立検証者として継続する。本タブは両作業の封印・曝露・資格留保・比較結果を保有していないため、完了や独立性成立を代記しない。
- **停止条件**: 新主担当の明示引受まで、本タブは実装・共有資産編集・push・PR操作を行わず、全worktree・枝・保全物を保持する。引受後も#174統合前の衝突資産push、変更した7.7値の無承認入力、旧履歴書換え、#156の先行close、本人確認代記、Draft解除/マージ、共有DB適用・資源購入・運用openは禁止のまま。新5後続ステップは9ステップ表の合格条件と個別ゲートを満たしてから順に進める。
- **確認できない範囲**: このタブの会話に表示されない別タブ内の全履歴、現存しないTSK-394旧`/tmp`の未保存ファイル、Notionの現在プロパティ、他担当の未公開差分・口頭受理、#176/P-6担当の進捗は実測できない。該当判断は未確認とし、過去の承認・レビューを補完しない。秘密情報そのものは本文に記載しない。
