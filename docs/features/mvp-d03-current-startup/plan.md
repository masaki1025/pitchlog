---
feature: mvp-d03-current-startup
status: active
branch: feature/mvp-d03-current-startup-20261107
承認: PO委任によるCodex/root判断（2026-11-07、計画ce698e8dの非作者確認後に採用）
重さ分類: コア領域
計画レビュー周回: 1
確定ゲート周回: 0
---

# 登板の既候補を通常49へ接続する

起点は走塁接合版ba561d91f493b7fcce2450837826ed5c863de3f6、CURRENT48。rootが唯一writer。走塁の実画面検証は同固定版の別shadowで継続し、このWTの変更で実測sourceを差し替えない。既D03計画/モデル/SQLと作者a5e3fe34の正常48移植packet（patch SHA9db55d32049ddd94dd85be084a397531021432a39a7c334fd68cf4271072afa0）を再利用する。

D03の実出場/0球交代/同試合再登板1、D02区分、JST暦年、既終了最新版を維持。mutable名簿や球数から推測しない。既唯一Sのv2 generatorとCOUNT DISTINCTを使用し、新集計/別野球計算を作らない。未供給P3/Undo/複数世代/全試合0球を0へ補完せず、後続接続をMVP残件として維持する。

| # | 実装単位 | 検査/成立条件 |
|---|---|---|
| 1 | 作者所有15pathを再利用し、正常48/v2 S上のread/生成SQLを接合 | 全15byte/既モデル/全数学期待を照合、旧T6のgame/year/category/status scopeと集計後段を保持。candidate_sqlは公式再生成、89pure/型/限定lintを同版で確認 |
| 2 | owner-onlyの0049構造/5helper/同TX3hookを通常配置へ接続 | 1表はowner/default deny/append-only、initial/sync ownerの有限列ACLのみ。旧P3 baseline Save11pinを改変せず、正常48成立後に真正normal Saveだけのoverlayを厳格旧body一致から生成。開始/Save/交代hookは既真正receipt/phase/nonce/xid/slot/FPと親最後のbinding確認を維持。caller由来の成功bool/Sを受けない |
| 3 | 全catalog/起動/故障を実PGで閉じる | CURRENT49/S0→49/同版resume/全21私有表の実構造・関数/所有/ACL/guard全値を検査。既Stats source/versionの正規xmin2をcollectorでも観測し余剰を拒否。関数body/DDLは同factory描画、7.7/sealは公式helperで直列導出し固定版/独立レビュー/CI後のみ通常統合 |
| 4 | 実開始/0球交代/終了再開と登板API/season/CSVを同版で確認 | 実画面または既実HTTPから新規作成した試合を使用。初期投手/0球交代/非投手/同D5再掲/終了v1/再開中対象外/追加球/再終了v2を確認し、25/27候補やtest-only finalizeを完成へ読み替えない。越境/不正receipt/途中故障は全取消。既走塁/CSV/訂正接合は回帰で確認 |

編集範囲は作者15path、既共有3hookの正式factory、専用migration0049/model/storage/起動catalog、公式assetsの生成差分とその正負試験、本計画だけ。旧migration/歴史pin/legacy/archiveを掃引せず、既modelの数学や他機能は範囲外。正式受理/通常mergeは最終HEADと依存/全必須CIの成立後、main/developへ直接commit/pushしない。共有DB/秘密/運用公開は適用しない。

検査は各単位の影響と負例を先に、統合候補で必要全件を一括。基線だけの変化による同値の再承認は繰返さず、承認実対象/固定SHA/後発差分を記録する。source/P6blind/人間署名を代記せず、PO委任rootの判断として採否を記録する。大きなハーネス再設計をこの単位の前提へ追加しない。

独立計画確認: game_operations_final_independent、対象ce698e8d0410e16917438a702b70d468f4378ebf/plan SHA7db912cb74a1ab5f22c34c482ea7d91fb0246c594dfc40d30139fcb01b3c305f、REPORT SHAb23c8abb34a2699650f6b56fb095937ef15dad3b8420f1d741868053f4566404、未解消P0/P1なし。rootは2026-11-07T17:22:13.501469+09:00にPO委任で採用。本人署名/実装・実PG/正式受理ではない。後発r20移植packet SHA7b9ae2d06a01cfbd80b27ed31a2051cd363b84d980d81e40c160ecd07b0e92b5は同15path/runtime同値、testのgame_other区分と結果文書だけを既D02へ整合。正式通常49はrootの次単位で実装する。

step1: r20最新15pathをpatch SHA7b9ae2d06a01cfbd80b27ed31a2051cd363b84d980d81e40c160ecd07b0e92b5から採用し全15byteをmanifest照合。同root版で89passed9.01秒/対象Ruff0/全Ty0。既normal48/v2 Sのread接合を再利用し、T6 scope/集計数式/数学期待は不変更。作者r20は旧通常45＋候補helperで実終了再開/登板API/season/CSV1passed225.83秒、root通常49の実証とは分離。次単位でhelperは現物ab8から公式factory再描画し、旧cacheの4e版bodyを独自にpin置換しない。

step2途中: 子担当862db714の新migration/専用試験2pathをpatch SHAc42240bef0db89d8349f2d563176e2262225025b2c04e8704d44709f01d003a8から全byte照合して採用。17列/PK/FK/CHECK/indexのliteral凍結、owner/FORCE RLS/default-deny、downgrade拒否を保持。rootは既3helper＋read2、列ACL36（新17列×2owner＋既native xmin2）/2tenant policyの有限publisher候補と厳密元body overlayを実装。Save後overlay全byteは作者正常48候補e93e2b55f1f6ddeb1cd7833a7282ec3cc30db059ce3643a2ca79b036c48a21d4と一致、旧P3 baselineに触れず末尾2点だけ。初回の境界markerが入口を含め3点だったため末尾RETURN隣接へ限定し、不足を無視せず修復。未知親版/owner/再overlayは拒否。対象合算100passed8.87秒/Ruff/Ty0。まだpublisherを通常profileへ有効化せず、共有hook/guard配置/構造検査/catalog/正式asset/通常49実PGは続く。原子保存・正式受理の成功ではない。


step2の通常profileを有効化: post-P3の厳密元body overlayから5helper/3hookを配置し、通常CURRENT49/全21私有表/17列監査原表/2append-only guardへ接続。初期ownerのreserved関数・17列ACL・2tenant policyはD03全profileの原典一致時だけ有限に受入れ、未知・欠落・余剰・owner/権限/predicate変更を拒否する。sync_fence schemaは初期fn ownerのUSAGEのみ追加、CREATEを明示REVOKE。公式factoryから新44宣言/49body（既5body変更を含む）を描画し、手作業で期待値を緩めない。関連200passed98.54秒、閉profile/guard21passed5.82秒、Ruff/Ty0。

非作者csvの限定REPORT SHAd00dccb3cdb09e56a4d7cb138f805b004b82fe71a318a1e3d0101041e64579cfは元WIP59path/combined diff SHA6fa40bbc2c4bcd90749aeefe82a884d1078a6610a899c24b27c1ba1dd7333fe1を固定し、独立201pure/49body/44宣言の機械一致を確認。P1は新entry表の余剰SELECT(xmin)が観測対象外という1件。rootは有限collectorへ新表を追加し、xmin許可宣言は追加せず、純対向を22passed5.82秒へ更新。さらに2ownerの余剰xminで再起動拒否・49表途中故障の全取消を実DB対向へ追加。後発限定確認と実PGは次。元helper/3hook意味の非作者最終確認は作者関与のない別Reviewerへ残す。正式7.7/seal/全CI/通常統合・本人確認ではない。


step3初回full49-normal-r1は4failed82.36秒/source前後同一/owned cleanup。49migration/全表構造/ACL収集へ到達したが、5helperの生CREATEにOWNER/REVOKE終端が欠けて実owner/EXECUTE集合が宣言と相違し、全catalogで拒否。起動成功や公開とは記録しない。rootは既factoryの各関数宣言から有限OWNER/REVOKE2文を生成し、公式BODIESから5bodyだけを再描画。各2文の逆除去で元本文/guard全byte不変、未知・欠落REVOKE集合は拒否。30pure6.29秒/Ruff/Ty0/公式body検査OK。

非作者 d03_helpers_final_independent_20261107 は固定f5版P1をREPORT SHAd677af1de74b584b06bbd1d8a447ca2a7138a207e4f2289a0b9c4a98ebf9fec2へ保存し、後発patch SHAc93ff7aac0954ee9366e79d3ea1c8dc58bf56cfff8c1a587dae1a39c14aa9d04の5body完全可逆/公式一致を独立再確認、81pure4.59秒、追加P0/P1なし。追補REPORT SHA11539f5af7134e0d6c30a94b6a2dd6e26f9de4bbcc447f94958fb0e3287299faでsource上P1解消。全意味の追加P0/P1なし、通常49の実receipt不正/保存途中全取消は未了。再実走は同じ4対向を新固定版で実行し、旧失敗を保存する。
