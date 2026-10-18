# C1ステップ2 gitleaks検出2件の判定資料

## 検出と機械照合

PR #147 / 初回CI 39094298692 のsecrets jobはgeneric-api-keyで2件を検出した。対象は製品資格情報ではなく、正式第2周の同一性確認に使う公開ソースのSHA-256を保存したreview manifestである。

同じ検出コミットのmanifestとソースblobをgit showで取得し、hashlib.sha256で再計算して保存値と比較した。結果は次のとおり。

- frontend/src/api/auth.ts: 保存値と当該コミット内のファイルSHA-256が一致。
- frontend/src/stores/authStore.ts: 保存値と当該コミット内のファイルSHA-256が一致。

値の性質は再計算可能な内容ハッシュであり、DB接続情報・JWT署名鍵・管理者/チーム初期パスワードではない。値の流出として扱う秘密情報はない。別の兄弟ハッシュと異なり、キーにauthを含む2行でgeneric-api-keyが発火している。

## 提示する最小差分（人間判定待ち）

既存github-setup.md 4章と.gitleaksignoreの運用に従い、下記2つのコミット/ファイル/ルール/行に限定するfingerprintだけを.gitleaksignoreへ追記する。全ルール・全ファイル・testを除外せず、秘密検査や試験timeoutは変更しない。通常pushだけとし履歴を書き換えない。

```text
1fea2c60f04f9c50c882298042b5a0458dd5879a:docs/features/auth-session-verification-contract/step2-review-manifest.json:generic-api-key:4
1fea2c60f04f9c50c882298042b5a0458dd5879a:docs/features/auth-session-verification-contract/step2-review-manifest.json:generic-api-key:6
```

現時点では追記していない。既存の人間判定例と同じく、この2件の誤検知判定と登録範囲をPOが承認した後だけ反映する。C1の製品コードや認証契約は変更しない。本件を本人逐行確認実施済みには流用しない。
