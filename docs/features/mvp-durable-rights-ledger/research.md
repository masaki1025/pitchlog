# 復元外台帳adapterの起案調査

## 固定入力と今回の権限

2026-10-24、rootから限定計画起案を委任された。新branch/pathの同名不存在を確認し、実develop `31194a39c9083bbef6c14bde19c24a3e49d09f2e`から`feature/mvp-durable-rights-ledger`を新設した。今回所有/編集は本featureのplan/researchだけ。source/正式JSON/正本/DB/資格/共有環境は変更していない。

最新PO範囲は主担当の指示による。PO4/10は合意済保証を変えない型/API/保存/失敗具体化と隔離環境構成をrootへ委任し、PO3で運用責任者山田正輝が明示済み。したがって旧提案の未承認表記だけを理由に、二台同期台帳の隔離ローカル実装/故障検証まで新たな人間待ちにしない。外部方式を厳密保証を満たす技術候補として限定計画・非作者レビュー・root判断へ出す。運用配置/共有DB/有料資源/新運用秘密は未実施の別ゲートである。

## 一次原典と読取所見

| 固定HEAD / path / 行 | 所見 |
| --- | --- |
| 旧`0aaa22e09d7e1a0301d03f7c63d188d9bba76844` / `docs/features/ur1-recording-rights/plan.md:94,180–187` | 旧方式案未採用と親9ステップを保持。新5の初期付与primitiveと新7復元・新8実Port接合は別責務 |
| 同 / `connection-contract.md:42,53–55,71–79` | 事前非ロック、直前共有ロック、復元開始はRG1行だけ先行commit。復元外発行源・起動epoch照合・不可分解除の設計根拠 |
| 同 / `d4-decision-proposal.md:7–16,22–28` | 同期二台/成功応答前WAL保全/非同期降格なし/旧primary fence/両系最新不明で発行停止。配置費用を仮決めしない。nonceで保証を弱めない |
| 同 / `backend/src/pitchlog/recording_rights/initial_grant.py:72–113,275–287` | ReservedGeneration、DurableGenerationSourceのreserve/claim/current_recovery_generation、RecoveryEpochFenceのgeneration/assert_held。外部epoch共有lockを業務commitまで保持する。実adapterではなく参照Protocol |
| 実`31194a39c9083bbef6c14bde19c24a3e49d09f2e` / `docs/design/sync-protocol.md:1769–1774` | 復元後非再利用・連続復元・全旧世代fence・回収/閲覧条件と新D4同時確定。対象0件なら発行0件解除可、preparingには解除時初期権なし |
| 同 / `backend/src/pitchlog/db/recording_rights/models.py:41–60` | RG1現物はsingleton/stateだけ。外部epoch/復旧manifest/完了証明の物理提供はない |
| 同 / `contracts/authz/product/function-bodies/functions/FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid).sql:15–24` | tenant一致とFOR SHARE NOWAIT後も常にfalse。stateをopenへ直接書くだけでは通常成功しない |
| 同 / `backend/src/pitchlog/repositories/rg1.py:69–86` | true以外を拒否し、既存2token経由。同契約を試験専用openへ置換しない |
| 同 / `docs/development/dev-harness-design-2026-08-07.md:533–543` | 7.6唯一の決定表。外部永続資産/復元境界の構造的改訂は同一PR内7.3、実装追随だけならPRレビュー |

上記旧commitはgit showの参照だけで、履歴輸入はない。旧P6/期待値/封印は閲覧しない。旧173/156の受理・レビュー履歴をこの新計画へリセットしない。

## source/検査器の現況

基線のpsycopg 3.3.4は既存依存で、新しいdriver依存は不要。既存tenant-boundary base-allowlistは完全修飾symbol/signature/API ID/正例fixtureの対応を持ち、psycopg接続/実行を自由には許可しない。新adapterにもexact登録と拒否試験を適用する。既存方式で表現できないAPIが判明した場合の検査器改訂は本計画で先決めせず、具体差分を主担当へ戻す。全ソース検査の除外はしない。

core JSONを読み、backend/tests/db/*は対象3領域、正例fixtureはtenant-isolationに既存被覆があることをfnmatchで確認した。新packageと単体契約試験は3領域とも被覆が不足し、正例fixtureもsync/recordでは不足する。従ってsync/record各3件・tenant2件の領域別追加層を宣言→別JSON登録する4ステップ構成とした。実装開始前に実base登録を再確認し、正常initial候補供給後も旧登録を削除せず本層だけを追加する。

local検証は実primary/実standby/別業務clusterを構成し、同期応答・standby flush・primary停止後保全と連続業務復元を測る。local同host試験を別故障領域での本番耐久性証明としない。運用配置未実施を理由に、adapter/契約検証の着手まで止めない。

## 起案時の未達

この新計画はレビュー0回・未承認。実台帳/role/schema/複製/試験はまだ作成・実行していない。実DB・Dockerを起動していない。正常initial供給・実Protocol接合・7.3/7.7実値・本物のRG1成功・全非0復元/実Port/HTTPは未達。新意味/可用性保証の弱体化・新運用秘密は採用しない。作者`/root/independent_review`は後の独立レビューを兼ねない。

## 起案検証

docs-statusは21文書/違反0、局所plan同期は指定base31194でexit0。両新規文書の末尾空白/NUL検査、git diff --checkは成功。core被覆は現JSONからfnmatchで独立に照合した結果を上へ記載した。実装・DB・複製・故障試験は未実施であり、文書検査を製品成功へ読み替えない。固定後は書込を停止し、非作者の計画レビューへ渡す。

## 計画第1回独立レビューと採否

/root/resolver_ledger_plan_reviewの全文レビューはP0=0/P1=1/P2=0。実31194 policyに新branch対象がなく、core_guardが新実PRを拒否するP1をrootが採用。planへ実番号取得後の同PR/branch1組追加とデータ自体の非作者最終確認だけを追補した。全旧target/authority/失効/拒否は不変。第2回限定差分確認前で、まだ計画未承認/製品未実装。正本順序自体は7.6根拠に一律違反とはしないとの非作者判定を保持する。

計画第2回限定反映差分/影響は非作者/root/resolver_ledger_plan_reviewの可決0/0/0。rootはplan末尾に対象SHA/日時/PO委任採用を記録。計画承認で運用設備・費用・共有DB・新秘密・正本確定/正式値受理・RG1成功が成立したとはしない。製品は未着手で個別step指示後に進める。
