# #177のCI外部凍結差分と最小是正

## 固定点と初回失敗

比較元は実PR base `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`、初回提出HEADは
`d5d851343b1e95a3ac41a5795620652f2a26a931`。
[CI run39950625656 / job120404214901](https://github.com/masaki1025/pitchlog/actions/runs/39950625656/job/120404214901)
のtenant-boundary-bypassは、`base-allowlist.json.baseline_control.history`の
`movement と追記 record 件数が不一致: moved=True, records=0`で失敗した。
core-guard成功と、この別CIの失敗を区別する。

初回の`ci.yml`へのGH_TOKEN環境変数2行追加は、既存外部凍結対象のバイトを変更した。
正式資産のJSON本文に差分がなくても、下記8資産の`pass_fail_mapping`観測が動く。
基準集合・宣言の置場・識別粒度・解釈は不変だった。

| 資産 | 維持する識別値 |
| --- | --- |
| base-allowlist.json | contract_revision:33 |
| cache-invalidation-contract.json | contract_revision:15 |
| census-baseline.json | contract_revision:14 |
| db-api-inventory.json | inventory_revision:15 |
| negative-fixtures.json | fixture_set_revision:17 |
| repository-contract.json | contract_revision:22 |
| runtime-authz-contract.json | runtime_contract_revision:18 |
| tenant-context-allowlist.json | contract_revision:16 |

9件目のfrozen-inputs.jsonはci.ymlを外部対象に含めず、この変更の影響はなかった。
これらの対象集合や比較方式を縮小してCIを通す修正は行わない。

## 判断と変更範囲

2026-10-23のPO委任に基づくCodex主担当 `/root` の差戻し修正承認を受け、
ステップ1内の取得実装を公開GitHub APIへの無認証GETへ変更する。
個別実値をPO本人が直接確認したとは記録しない。

- `core_guard.py`は固定host/数値comment ID/既定TLS検証/30秒timeout/redirect拒否/
  1MiB上限で読む。Authorizationを付けず、GH_TOKENや署名鍵を取得しない。
- HTTP・rate limit・非公開化・ネット/TLS・JSON/UTF8異常・応答所在不一致はfail-closed。
  PR/掲載主体/最終HEAD/実差分/重大指摘の既存照合は維持する。
- ci.ymlを上記実baseのblobとバイト同一へ戻す。正式資産・revision・履歴・snapshotは変更しない。
- planのGH_TOKEN設定記述を事実へ追随する。一般的なgh PR操作や既存手続きは変更しない。

取得前に無認証APIでrepositoryがpublic/private=falseであることを確認した。
#177証拠comment6364409643のGETもHTTP200・OWNER・publisher masaki1025を確認。
実装後の同関数からも同commentの取得成功を確認した。本文・認証値はログへ出していない。
無認証APIのrate limit、将来の非公開化、ネット障害でCIが拒否され得る境界は残る。

## 検査と正式受理の区別

比較元に対する正式資産9件と全external_filesのGitバイト比較は差分0。
その同一内容から既存frozen_historyで`movement=False, affected=[]`を再導出した。
既存checkerの`PR_ACCEPTANCE`モードを実base/HEAD/PR177で明示し、
作業木の是正後に`violations=0`を確認した。対象は旧HEAD＋未コミット修正であり、
新固定HEADのCI成功を先行記録したものではない。新たな7.7受理値の流用・履歴追加は不要。

root Ruff/ty、docs-status20文書0違反、diffチェックは成功。
最終 `uv run pytest -n 2 tests/test_core_guard.py -q` は
`350 passed in 20.89s`、終了コード0（旧HEAD＋未コミット是正版）。
初回のty検査ではHTTPError試験用headerの型不一致1件を検出し、Messageへ是正した。
既存レビューの回数をリセットせず、後発修正を新固定HEADの第2回差分レビューへ渡す。
旧HEADの証拠コメントは履歴保持し、新HEADへ流用すると拒否される既存条件を維持する。
