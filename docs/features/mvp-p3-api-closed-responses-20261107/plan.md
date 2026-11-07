---
feature: mvp-p3-api-closed-responses-20261107
status: active
承認: PO委任によるCodex/root判断（2026-11-07、7a7c82fc非作者計画確認後）
重さ分類: コア領域
branch: fix/mvp-p3-api-closed-responses-20261107
計画レビュー周回: 1
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


限定非作者計画確認: recovery_continue_20261107、対象7a7c82fc/plan SHA5d59b52aed06ff0dcdd90845796eaba7ecd0ddf5e7a2a9e5a2fea07d12928d23、REPORT SHAd77226548ff69b64fa811a5a95ebe62f68d55daf9257dab49630e82df8201fbc。P0/P1なし・必須追補なし。rootがPO委任で採用。受理/先行再掲双方のmodel返却、alias/null/省略全値、元query/TX順を保持し、post-accept型エラーを未受理へ雑写像しない。人間署名/実装レビュー/実PG検証ではない。


step1: 既opaque D4からAttemptBindingを形成する部分も同serviceへ機械分離（復号→Authority→Attemptの順・引数/定数不変）、既I6 serializerは全AST同一で移管。内部同期codec/不変JSONの知識をtransportから分離し、識別子を伏せるためのrenameやguard除外は行わない。target/confirmationの同TX本文はJSONResponseの成功封筒だけを外した全ASTが元66d85fa6と一致、cache read-extraction-proof.jsonへ固定。未知contextは業務接続前に拒否、既owner codecの1/2/2^53/最大64bitと別tenant/game/破損拒否、旧409/503写像を検査。影響検査89passed5.70秒、残1赤はstep2対象の3route応答型欠落で、同期語彙guardは除外0で通過。元raw DB例外をAPI対象型と取り違えた試験2件は実際の既SQLAlchemyErrorへ是正し、製品の例外集合は変更しない。実PG/正式受理ではない。


step2: 3routeにstrict/extra-forbidな応答型と実model返却を接続。GETの英字対象参照とI6の日本語参照は別型で既aliasを保持、既PrefixRef/StrikeoutSnapshot/LineupPitchChangePayloadを再利用し、計算の再実装なし。受理/再掲の両経路が既boundaryの閉unionを検証し、post-accept検証例外を未受理422へ変換しない。全routeでexclude_unsetを指定し、nestedの元の省略と明示nullを保持。実route fieldのvalidate/serializeで4形全値一致、未知/余剰/欠落/型変換/既7拒否/不正boundaryを対向。API規約のexact-route/語彙/None例外は不変更で全件を含む146passed5.16秒、Ruff/Ty0。旧2赤は検査除外0で閉鎖。実PG・旧P3長履歴の障害解消・正式受理の証拠ではない。


step3影響検査: API/既E1受付/Cookie/C2/roster exactの統合回帰は初回66pass2fail。追加2件は基線66d85fa6でも同名2failed3.22秒を確認した既有限集合の追随漏れ（既登録recover/毎球CSV）で、実registered routeとCookie非対象を照合して有限追記。製品C2/同Cookie policy/未知route検出は変更しない。影響8suiteを同候補で一括し214passed6.17秒。元全API規約の2赤はDTO/service修復で、別の既基線2赤は有限metadata整合で閉じた。最終非作者差分確認と実HTTP/正規統合後の接合は未了、必須CI/7.7/正式受理の代わりとはしない。


実装非作者レビューの元cf847cfb REPORT SHA406f8d5073332d31e05af10787dfd2c1fe9e2f616fe488caabfb60764481514eでP1=1。rootが変更可能な3結果とtarget GETの読取結果を取り違え、後者DTOを3Literalへ狭めた。元T1/打球/走塁sourceはstrのまま返すため、target.original_result_idは補正のないStrictStrへ戻す。既source唯一validatorによる意味判定と、変更POSTの既3結果制限は保持する。4安打IDの読取正例/型不正4例/安打を変更対応へ昇格しない負例を追加し、同関連8suite223passed6.25秒/Ruff/Ty0。元P1を消したとは再確認前に記録せず、後発source版の限定確認を受ける。独立153pure/元query・serializer全AST一致の証拠は継承し、後発DTO1field差分と分離する。
