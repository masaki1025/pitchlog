# C1相関・C2・U-F3・U-F13のPR依存（一枚）

## 現在値（2026-10-19、実統合後）

最新実developは`ba339cf8bdaac4761b8cf437abaf21763617d064`。次の統合待ちはすべて解消済みであり、自チーム取得の候補準備や今後の作業の停止条件へ戻さない。

| 順序 | PR | 実統合SHA | 状態 |
| --- | --- | --- | --- |
| 1 | #157 | a87510e6c431fbb4ee14c91775204a5c91bec745 | 統合済み |
| 2 | #150 | b4047e31645217ea7b93c08fa2ab4a7533d729b4 | 統合済み |
| 3 | #151 | b64d6aa1709310704658415ad09a86898bfdcb2a | 統合済み |
| 4 | #154 | ba339cf8bdaac4761b8cf437abaf21763617d064 | 統合済み。最終CI39205855069成功 |

統合後の同HEADで既存の実画面/API/隔離DB受入を再実行し、対戦相手配下の正常系8項目が成功した。候補時の成功や故障系の既済み結果とは別の証跡として、[作業ログ](../../worklog/2026-10-14-uf13-team-route-acceptance.md)へ固定する。自チームread/受入、TSK-528全体は未完了。[最小追補候補](../uf13-team-route-acceptance/self-team-read-addendum-candidate.md)が編集元であり、ここで新契約を重複作成しない。

## 以下は統合前候補の履歴

基線: 実origin/develop `015dfa9db0b7b8740369911a9cb5195dd59a62ea`。他担当の未統合枝は通常基線にしない。全担当は本Codex D、マージは人間。

| 推奨順 | PR/固定候補 | 実際の差分・提供物 | 単独/統合条件 |
| --- | --- | --- | --- |
| 1 | C1相関 #157（製品108c7562、fixture912585d1、レビュー入力a15128a1） | login応答tenant_id、authIntent/通知2キー、storeの検証済み化入口、auth client、共通client旧Cookie observer。C2 metadata分岐はない | 自身のbackend/frontend/拒否試験・相関レビュー・本人確認。公開routerは追加しない |
| 2 | C2 #150、3eb3a0d3（製品146c774cから不変） | backend tenant_access/7業務経路のmetadata前照合、正規client tenantBound/nonce、roster client/管理画面の利用指定 | C1の実develop統合後に通常mergeし、680c2a27の共通無効化を正規clientへ追加。新storeに合わせconsumer fixtureを追随。専用結合だけの修正を単独成功としない |
| 3 | U-F3 #151、9267116f（製品不変） | 経路未登録LoginScreen/試験/環境回復表示、LoginScreen*のT登録 | C1の厳密2項目login DTOとnotice/store APIが必要。C2と製品UIは独立だがcore追加層の基線/consumer試験を先行実統合へ追随。U-F3単独の1,273成功は旧C1基線の結果 |
| 4 | U-F13 #154、034fa876（製品不変） | router/Appのlogin/team接続・guard、router*/App*の宣言とJSON登録、受入 | C1/C2/U-F3の実develop統合後に取り込み、登録追加層は既存LoginScreen*を保持して再導出。現在の単独CI TS2307はLoginScreen未統合。metadata照合なしで/teamを公開しない |

同じ`client.ts`はC1のCookie observer→C2のmetadata検査の順。新しい共通clientをコピーしない。現在は承認済み専用検証枝だけに両方を結合し、680c2a27をそこで実装して反例を検査する。#150の通常枝を未統合C1で基線化する許可には読み替えない。

## 検査結果を帰属させる境界

- 単独HEAD: 各表の固定コードに対するローカル/CIだけを記録する。#154の欠落依存と本人未記入core-guard失敗は未完了のまま。
- 結合HEAD: 許可された自分の固定候補だけを合成する。最終結合の実画面/API/DB成功はどの単独PRのCI成功にも読み替えない。後発追随は再固定・必要な影響検査を行う。
- 自チーム受入: opponent専用のteam-records一覧から自チームIDを得られない。別資料self-team-read-gap.mdの最小契約候補を正式化するまで未実施。対戦相手の受入を代用しない。
- 正式資産/7.7、本人逐行確認、公開・Draft解除・マージは別ゲート。推奨順は自動マージ指示ではない。
