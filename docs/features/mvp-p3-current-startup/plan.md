---
feature: mvp-p3-current-startup
status: active
branch: feature/mvp-p3-current-startup
承認: PO委任によるCodex主担当/root判断（2026-11-07、既P3/復旧成果の正規接合）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# 過去訂正と結果不明復旧を通常配置へ接合する

起点5cb4407d2f4df63428f15d8da8c576ff684e5a16は正式develop45bを取り込んだ通常CSV47候補。ae82631b同sourceの新規配置/再開/全故障改変49件と、後付SQLなしの実画面記録/取消/再入力/ZIPは成立済み。旧source/レビューを継承し、P3候補9687caa038629409d024cac54270df3d186d5a27の訂正→終了→再開→追加球→再終了/reloadと、復旧e690dba8の真正P3照会/旧生存拒否/終結後だけ許可を再利用する。

| # | 実装単位 | 成立条件 |
|---|---|---|
| 1 | 既P3と復旧を通常mergeで同居し、必要なFE接合patchを適用する | 元枝不変更、実固定点/全編集集合/競合理由を記録。旧P1/P2/CSV/記録権とD5原本文資格を保持し、古いcatalogでroot47を上書きしない |
| 2 | 原本schemaの0048・型元・全構造/ACL/catalog/標準controlを通常起動へ供給する | 手書き成功DDLの後付けを除き、実sourceから閉派生。旧47/復旧guardと実P3資格を保持。全故障を同TX全取消、正式7.7はsource固定後に別ゲート |
| 3 | 同版新規画面→複数球→過去訂正→終了再開追記→再終了/reload・結果不明復旧を実証する | 実認証/記録権/唯一artifact/同TX保存、旧版失効/同D5再掲/越境/途中故障/遅着遮断。P3の88列CSV未供給・25超/複数/終了後訂正は別残件として完了へ読み替えない |

rootのみが本WT/共有接合を編集する。編集は既P3/recoveryの実source集合・専用fixture/tests・FE耐久/画面接合、既cache原本からの0048 migrationと専用型元、current_product_startup/閉検査、authz候補catalog/公式派生と本計画。元P3作者は別WTで25超/複数/終了後の純sourceを担当し、同じ物理pathを並行編集しない。既capsuleのwatermark<=25などを上限だけ外して全試合成立にせず、ページ完全性の追補を受けて整合する。新しい野球意味を裁定せず既採用意味と保存保証を維持する。

正式共有DB/運用公開/新秘密/本人署名は行わない。試験はowned PG全寿命共通lock、共有DSNをunsetし実source前後と所有cleanupを固定。独立reviewは対象版/差分SHA/作者別に維持、既13path等の部分reviewを全依存へ拡張しない。最終認可/tenant/7.7/必須CI/通常merge/実機の未了を保持する。8分割CIの保留を本製品接続の条件にしない。

初回source結合の6競合はimports/C2 operationの和集合、本文指紋＋D1less kind双方の保持/除去対象分離、sync transportのevents/change/recover閉3入口、同一内容の試験表記で解消する。旧P3側の選択で復旧body_fingerprint/CSV資格を失わせない。後発型検査4件は通常投球fixtureをFirstBallObservationsへ実isinstanceで狭化し、非投球unionや製品の未対応拒否は変えない。対象271成功/10失敗を保全し、Port宣言18口と実cold bootstrap13口の供給漏れを検出。必要最小修復として既port_guard._load_first_ball_port_classesへ既宣言済P3/交代5型の明示import/返却だけを追加し、実クラス同一性・SQL-free静的閉包/未登録/未import拒否を維持、既2試験の期待集合も同5型を正確に追随。自由importやfallbackは作らない。旧関数registry pin期待漏れ1件は別残件として扱い、比較を削除しない。

ステップ1第一接合の検証: backend全Ty0/Ruff0、cold bootstrapと元要求/port境界147passed5.66秒。frontend型0/lint0、client/sync transport/P3 controller/UI92passed3.26秒。旧registry全関数pin期待は新增22件を未収録の1failであり未解消として保持（型を無視したり比較を削除しない）。元271/10失敗もcache保持。これはP3機能sourceの接合だけで、0048通常配備/新source実PG/最終受理の完了ではない。

ステップ1第二接合はe690の標準control/P3 body fingerprintと旧要求照会・P3専用送信barrierを通常mergeで取り込む。16競合をcache p3-recovery-merge-resolutions.jsonへstage1/2/3と解消SHAで固定、root47 catalog/UUID parser/分類とP1実証browser条件を維持し、他の競合はP3 sourceを採用。phase_kindとbody_fingerprintの同一代入重複だけを除去、adapterは独立確認済40d9b070…とmanifestの全byte一致を別途照合。P3 APIには既cache patchのpostRecoverableP3Changeを接合、元body/D5/V12を改変せずsent.bodyと実応答でparseする。既wire単体にPinia/IndexedDB/安全context前提を明示し、unsafeではfetch前に拒否する負例追加。mock/単体成功を実認証/PGへ読み替えない。

第二接合の局所検査は402backend/20.35秒、107frontend/3.30秒、P3送信/barrier境界23/2.80秒成功。P3単位の旧3failは新耐久前提を試験準備していなかったものとして保全、旧応答期待やC2拒否を削除していない。Ruff/Ty、独立sourceレビュー、正常0048/実owned・cold P3・CSV88・正式受理は後続。旧registry追加22件の期待不足1failは未解消。
