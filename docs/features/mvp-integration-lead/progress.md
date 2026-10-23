# 初回MVP 主担当引受・進捗台帳

更新: 2026-10-23。判断者: Codex主担当。根拠: 同日POの `/goal` 指示と例外委任（撤回または今回MVP終了まで）。山田正輝の個別実値確認・署名とは記録しない。

## 引受と固定点

全体目標・編集権を引受。各領域の現HEAD・作業状態は [takeover.json](takeover.json)。既存引継ぎを正として参照し、全保全物を読了したとは扱わない。P-6は役割・封印・曝露履歴を維持し、候補作成へ吸収しない。TSK-545はHEAD一致・clean、対象cwdの稼働なし。独立引継ぎ未受領の不足は残し、今回POによる主担当移管を記録する。旧担当への再許可照会は要しない。

- develop: `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`。2026-10-23 fetch確認。
- #176/#174/#175公開HEADは報告値一致、Draft。#173は公開`dac2ff15`、ローカル`6af8c801`と未コミット36パス。既存引継ぎmanifest照合前に触れない。
- #176: `c1413b25`と未コミット3文書は引継ぎ通り。pytest/ruff等の変更・検査プロセスなし。停止記録と今回指示に基づき引受。旧担当通知はPRコメントを使う（agmsgは当該project未登録で既存担当との経路がない）。送付と受諾を分ける。
- #174未コミット引継ぎ文書、T2未追跡JSON、成績未追跡文書は原状保存。採用・削除前に確認。
- 初回MVP Pageは接続tool read_pageで取得済み: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01 。元正本への反映は未実施。

## 編集所有と順序

主担当管理worktree: `feature-mvp-integration-lead`（develop起点）。一括移植をせずPR単位を維持。

| 単位 | 編集所有/場所 | 現在の範囲 | 提供・接続・検証 |
| --- | --- | --- | --- |
| O5コア登録・委任手続 | 主担当worktree、担当をpath別指定 | 独立planと前提PRへ分割するPO委任判断。既存#176一件ステップへの押込みを避ける | 計画作成中。#176のO5製品runner成功は未成立 |
| #175 step3 codec接合 | 分離`feature/mvp-preparing-codec-connection`、product_connection担当 | 保存JSON復元と正式codec接合の2製品パス＋テストのみ | #174固定候補との隔離接続。正式統合とは別記 |
| #176→#174→#173→#175 | 主担当、共有正式資産は直列 | 各最終HEADの独立レビュー・受理・CI後通常merge | 全て未統合。チェック欄だけで成立扱いしない |
| T5/T6・成績CSV | 主担当（今回責任移管） | 既存U-X1と調査・計画候補照合後にstep単位 | 製品未提供。毎球CSVはU-D2調査/計画を再利用（製品実装は未存在） |
| P-6 | 独立役割、既存資料参照 | 封印物/期待値を候補作成担当へ渡さない | 新blind導出未実施。段階B一致を一般化しない |

## 製品到達点と残件

| 到達点 | 実装場所/提供版 | 状態 | 次の証拠 |
| --- | --- | --- | --- |
| A 試合作成・preparing再取得 | #174 resolver後続、#175 components後続、U-F8 | 候補部品あり・実画面→実API→実DB未接続 | 正式codec拒否を先に接合、resolver operation/read route/providerを順次供給 |
| B 開始・権利・1球保存と復元 | U-R1/T1/U-S1/TSK506 | 接合未成立 | 実権利・計算・永続providerを結ぶ |
| C 通常全操作・終了後訂正 | U-F8/T1/T2/U-S1 | 未検証 | 実製品1試合・版一貫性 |
| D 故障・再起動・再送・交代 | U-S1/U-R1 | 部品検査と実DB/HTTPを区別 | 隔離DBの原子性/復旧試験 |
| E 閲覧・基本成績・CSV・負荷 | U-F8/U-D2/T5/T6 | 未接続/未提供を含む | 暦年JST、終了確定版、毎球/成績CSV双方 |
| 実機・運用HTTPS・バックアップ復旧 | 山田正輝（運用責任）/主担当準備 | 未実施 | 実機版と機種、許可済環境を固定。エミュレーションと区別 |

MVP-FR-001〜017 / MVP-NFR-001〜012の個別対応は実装場所確認時にこの台帳へ追記する。現時点で正式受入を推定しない。委任外の未裁定意味、実機/運用資源は具体判断票へ集約予定。Goalは継続中。

## 照合の追記と判断票（2026-10-23）

- `/root/o5_registration`がUR1 manifest全46パスのSHA/集合一致、HEAD一致、後発差分0を確認。status通常36行は未追跡ディレクトリ集約によるもの。旧公開#173との差分を後続の正式受理時に扱う。
- U-F8は封鎖UIの統合と実接続/受入の未着手を分離。9パス追補は旧最終承認待ち、既存追加レビュー残0を保持。US1 C1/F1候補成功はF2/F3の実耐久provider完成を表さない。
- U-D1は544一次引継ぎで未承認計画/製品実装0。毎球CSVもUG1 A01で一時保留/製品0。どちらも実装済みという調査側表示を採用しない。
- TSK-545のE11/E07未裁定表示は2026-10-18の旧状態。T2 post-153引継ぎと `p8-human-decisions-and-receivers-2026-10-18.md`、planはE11=A/E07=B採用済みを保持する。再裁定を求めない。正本/正式契約反映は別条件。545からの個別受領回答は未取得だったため、これから主担当が版を特定して受領範囲を確認する。
- P6はALL-WORK-HANDOFF.txtの資格/封印注意のみ照合。結果JSON/期待値/封印物は未読。主担当・候補担当を新blind検証者にしない。
- 保存codec接合: 隔離候補HEAD `6ddbc341`。実体2パスの新差分だけを独立レビュー（P0/P1/P2=0/0/0）。対象pytest100成功。#174固定codec+#175既存成果を供給した候補で、正式API/DB/画面の成功ではない。patch/bundleはcache保全。正式基線統合後の再接合が必要。
- O5パス宣言: commit `6ca9d157`。対象pytest274成功/Ruff/ty成功。JSON登録は次ステップ、元#176には変更なし。引受通知: https://github.com/masaki1025/pitchlog/pull/176#issuecomment-6364057612 （送付済・受諾未確認）。
- 限定委任手続PR #177はDraftで準備中。計画第1回P1×2/P2×1全採用、第2回0件、PO委任で承認。人間チェックの代記は行わない。

### POの新意味判断を要する事項（同一事項の再照会を避ける）

| ID | 具体例・現在の根拠 | 選択肢と推奨 | 影響・再開条件 |
| --- | --- | --- | --- |
| MVP-D01 | 9回裏2対2→3対2、9回から1点差でコールド可という有効規則。サヨナラとコールドが同時成立。T2引継ぎはoutcome優先だけを未採用と明記。既採用E08はコールド対通常終了だけで、サヨナラには拡張しない | B推奨: walk-off（サヨナラ）を返す。A: cold-end（コールド）を返す。どちらも検知/ロック/宣言促しtrue、自動終了falseは既存方針維持 | 終了理由の正式値・画面表示・契約case/独立期待値が変わる。PO回答後にその範囲だけ正本/契約へ反映。未回答中は仮仕様で確定せず、保存接合・guard等を継続 |

実機/運用資源は製品経路準備と並行で具体化し、利用直前の委任外承認が必要なものだけ同表へ追記する。

## 接続・故障検証の証拠追記

2026-10-23、#174固定HEAD `e30edc79a7f90aa27cb14303910676e414c2cab6`（未コミット差分は既存引継ぎ文書のみ）のbackendで、既存使い捨てPostgreSQL fixtureを使った実DB検査を主担当が実行。Docker Server29.1.3、既存postgres:17.11-bookworm。共有DB/利用者データへ適用なし。

コマンド: `uv run pytest tests/db/test_stage_a_rule_candidates.py -q -k 'formal_stage_a_startup_preserves_closed_publication or formal_stage_a_startup_authz_failure_keeps_placement_closed or stage_a_staged_startup_from_empty_database_and_retry or stage_a_candidate_insert_fault_rolls_back_everything or stage_a_function_candidate_rejects_override_and_guc_mismatch'`

結果: **5 passed, 21 deselected in 33.82s / exit0**。正式段階起動、認可失敗の非公開保持、空DB→配置→再試行、配置途中故障の全取消、override/GUC不一致拒否を実測。DBの独立接続試験であり実HTTP/画面作成成功ではない。O5製品runner/実耐久provider完成/実機受入の代替ではない。

#178コード候補 `719bb308`は独立実装レビュー第1回可決（P0/P1/P2=0/0/0）。reviewer `/root/independent_review`、候補作者 `/root/o5_registration`と主担当。対象base1ab398cc、diff SHA256 `dab69624aad19aeaf093d8fc2968cb165c23808d4a5bbb14fb0bda989546c13f`（git diff --no-ext-diff --binary base head）。JSON登録時の旧試験1件失敗は隠さず51a030d3のステップ1範囲是正に記録し、公開履歴を書き換えていない。最終274件成功・履歴基線成功。root全件は実行中。#177手続実統合後の基線追随と最終版の限定確認を残す。

成績引継ぎ文書・台帳のSHA256はPO提示値とそれぞれ一致。未追跡は引継ぎ2＋候補4の計6文書で原状保存。現候補の配信層をT5/T6実装と混同しない。暦年は既決、登板/打者数など未裁定境界は既採用判断の追加照合を続ける。
