# C1ステップ2 gitleaks検出2件の判定資料

## 検出と機械照合

PR #147 / 初回CI 39094298692 のsecrets jobはgeneric-api-keyで2件を検出した。対象は製品資格情報ではなく、正式第2周の同一性確認に使う公開ソースのSHA-256を保存したreview manifestである。

同じ検出コミットのmanifestとソースblobをgit showで取得し、hashlib.sha256で再計算して保存値と比較した。結果は次のとおり。

- frontend/src/api/auth.ts: 保存値と当該コミット内のファイルSHA-256が一致。
- frontend/src/stores/authStore.ts: 保存値と当該コミット内のファイルSHA-256が一致。

値の性質は再計算可能な内容ハッシュであり、DB接続情報・JWT署名鍵・管理者/チーム初期パスワードではない。値の流出として扱う秘密情報はない。別の兄弟ハッシュと異なり、キーにauthを含む2行でgeneric-api-keyが発火している。

## 承認済みの限定登録

既存github-setup.md 4章と.gitleaksignoreの運用に従い、下記2つのコミット/ファイル/ルール/行に限定するfingerprintだけを.gitleaksignoreへ追記する。全ルール・全ファイル・testを除外せず、秘密検査や試験timeoutは変更しない。通常pushだけとし履歴を書き換えない。

```text
1fea2c60f04f9c50c882298042b5a0458dd5879a:docs/features/auth-session-verification-contract/step2-review-manifest.json:generic-api-key:4
1fea2c60f04f9c50c882298042b5a0458dd5879a:docs/features/auth-session-verification-contract/step2-review-manifest.json:generic-api-key:6
```

山田正輝から「実認証情報ではない」との確認と、理由コメント付きのfingerprint単位登録承認を受領し、上記2件のみ反映した。C1の製品コードや認証契約は変更しない。同回答に含まれるHEAD a3934fb7の全18ファイルの本人逐行確認完了は、登録承認と区別して記録する。

## 別の未判定1件：既存同期試験の母集合

対象はcommit b86df9de64d6b3d95f9b7d7b13592d57fc19c6a1のtests/fixtures/sync-protocol-population_v1.json、105行（generic-api-key）。当該commitは最新developの祖先で、C1は対象fixtureを変更していない。

用途は同期故障試験の観点とシナリオの対応表。対象値はO4永続化とD2同値性の固定試験IDで、隣接するscenarioIdと同値である。backend/tests/test_sync_apply_failure_contract.pyのtest_population_is_an_exact_set_of_pairsは26組・22観点・所有16/繰延10を照合し、frontend/src/testing/failureScenarioAdapter.spec.tsも同じ表のペアを検査する。認証処理や資格情報の入出力には使用していない。

同commit blobと現行表の該当row、backend/frontend両consumer、docs/features/us1-sync-apply-core/plan.mdのステップ18（TSK-330由来の試験ID）を照合した。意味のある固定シナリオ名をKeyというfieldへ入れており、generic-api-keyの名称・文字列形状による検出と判断できる根拠がある。C1のソースhash2件とは別の用途・別commit・別fileである。

本件の人間判定・限定登録は未承認のため、fingerprintを追加しない。承認済み2件と本人確認完了の状態には影響させない。
