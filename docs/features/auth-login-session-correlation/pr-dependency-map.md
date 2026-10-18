# C1相関・C2・U-F3・U-F13のPR依存（一枚）

基線: 実origin/develop `5bb1ff89306712c1de61c3a0152141c8f771b3a0`。他担当の未統合枝は通常基線にしない。全担当は本Codex D、マージは人間。

| 推奨順 | PR/固定候補 | 実際の差分・提供物 | 単独/統合条件 |
| --- | --- | --- | --- |
| 1 | C1相関（専用枝a15128a1、追加Draft準備） | login応答tenant_id、authIntent/通知2キー、storeの検証済み化入口、auth client、共通client旧Cookie observer。C2 metadata分岐はない | 自身のbackend/frontend/拒否試験・相関レビュー・本人確認。公開routerは追加しない |
| 2 | C2 #150、146c774c（既存固定候補） | backend tenant_access/7業務経路のmetadata前照合、正規client tenantBound/nonce、roster client/管理画面の利用指定 | C1の実develop統合後に通常mergeし、680c2a27の共通無効化を正規clientへ追加。新storeに合わせconsumer fixtureを追随。専用結合だけの修正を単独成功としない |
| 3 | U-F3 #151、37c41110 | 経路未登録LoginScreen/試験/環境回復表示、LoginScreen*のT登録 | C1の厳密2項目login DTOとnotice/store APIが必要。C2と製品UIは独立だがcore追加層の基線/consumer試験を先行実統合へ追随。U-F3単独の1,273成功は旧C1基線の結果 |
| 4 | U-F13 #154、e05303e2 | router/Appのlogin/team接続・guard、router*/App*の宣言とJSON登録、受入 | C1/C2/U-F3の実develop統合後に取り込み、登録追加層は既存LoginScreen*を保持して再導出。現在の単独CI TS2307はLoginScreen未統合。metadata照合なしで/teamを公開しない |

同じ`client.ts`はC1のCookie observer→C2のmetadata検査の順。新しい共通clientをコピーしない。現在は承認済み専用検証枝だけに両方を結合し、680c2a27をそこで実装して反例を検査する。#150の通常枝を未統合C1で基線化する許可には読み替えない。

## 検査結果を帰属させる境界

- 単独HEAD: 各表の固定コードに対するローカル/CIだけを記録する。#154の欠落依存と本人未記入core-guard失敗は未完了のまま。
- 結合HEAD: 許可された自分の固定候補だけを合成する。最終結合の実画面/API/DB成功はどの単独PRのCI成功にも読み替えない。後発追随は再固定・必要な影響検査を行う。
- 自チーム受入: opponent専用のteam-records一覧から自チームIDを得られない。別資料self-team-read-gap.mdの最小契約候補を正式化するまで未実施。対戦相手の受入を代用しない。
- 正式資産/7.7、本人逐行確認、公開・Draft解除・マージは別ゲート。推奨順は自動マージ指示ではない。
