---
feature: mvp-p3-api-closed-responses-20261107
status: review
承認: 未（PO委任rootの採用と非作者計画確認待ち）
重さ分類: コア領域
branch: fix/mvp-p3-api-closed-responses-20261107
計画レビュー周回: 0
確定ゲート周回: 0
---

# P3既応答を閉DTOで提供し、APIを既読取サービスの呼出しへ薄くする

起点は通常49＋復旧応答型修復の66d85fa6。P3の3routeがresponse_model未宣言で、target/confirmationの読取本体がAPI内で内部同期位置を扱い、既API検査が正しく拒否する。検査の除外や内部語の伏字renameで通さず、既wireと安全条件を保って修復する。rootが唯一writer、他担当のstarted GET/RR分離・成績/CSVには触れない。

| # | 実装単位 | 検証 |
|---|---|---|
| 1 | 専用P3読取serviceへtarget/confirmationの既query本体を機械抽出。実TenantContext/同TX/CP/slot/現P3 paged/tenant/version/有限pageの全照合・例外順を維持し、APIは呼出しと既HTTP写像だけへ | 元bodyのAST/差分同値、25超/現P3/不可視/不整合の既検査を継承。新集計/別S/別計算を作らず、認可/lock/副作用/拒否優先は不変更 |
| 2 | target/confirmation/変更結果にstrict・extra-forbidな閉DTOを追加しresponse_modelと実model返却へ接続。既domainのPrefixRef/after/変更本文モデルを再利用、受理I6とB8〜B14拒否は既boundaryで識別 | 既JSON全値・別名・null/省略の区別を保存。未知/余剰/型変換を拒否し、JSONResponseによる検証迂回なし。既401/404/409/422/503と再掲は不変更。既transport期待は緩めない |
| 3 | 既API conventions全件とP3/再送/対象参照の関連回帰を同版で実施、非作者差分確認後にroot候補へ接合 | downloads-only response_model例外と未知route検出は不変更、語彙guardの例外追加0。実PG/ブラウザはroot共通lock調整後、旧候補の成功を新固定版へ読み替えない |

編集所有はapi/routers/sync.py、専用api/schema、専用sync読取service、専用/既API関連tests、本plan/progressのみ。正本/contracts/正式seal/manifest/共有台帳/started読取共通ファイルは変更しない。新たな意味や新境界結果を決めず、元の受理・拒否内容をそのまま型に束縛する。正式受理・独立検証・人間署名を型試験から成立扱いにしない。
