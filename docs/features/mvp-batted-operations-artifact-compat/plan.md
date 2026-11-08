---
feature: mvp-batted-operations-artifact-compat
status: active
承認: PO委任rootの既MVP内明示実装指示（2026-11-08）
重さ分類: コア領域
branch: feature/mvp-batted-operations-artifact-compat-20261108
created: 2026-11-08
計画レビュー周回: 0
確定ゲート周回: 0
---

# 打球群後継artifactの有限互換と実行pin

root指示により既mvp-game-operations-product step2/3内の実行接合を進める。起点2b762、SH全走者実進塁修復の作者a94cfac2を依存固定として受領。暫定ef7は実行pinに採らず公式71f2726aを候補にする。意味の新判断/旧数学期待再採取を行わない。

編集は新v5 witness/registry、repositories/play_prefix.pyの有限validator/分岐、旧v4・新v5専用試験、既7manifest/現在fixture/D11の宣言済実行pin・自己echo派生のみ、本docs。domain/正本/SQL/正式authz/tenant/seal/台帳は非編集（受領済source依存4pathは作者版のまま保持し、自分の変更と分離する）。旧v1-v4 witness/registry/規範53/過去pinは全byte不変更。

| # | 作業 | 検査 |
|---|---|---|
| 1 | 実Git旧0db artifactと新実artifactで旧53を全値比較し新v5/有限5pair生成 | 許可自己echo/実行pin4欄以外全leaf同値、旧原本byte保持 |
| 2 | 旧全chain固定検証＋v5有限validator/改変拒否と現行metadataへ接合 | 旧4e8/4e7/ab8/0dbから新currentだけ許可、未知pair/旧registry/数学改変拒否、旧v4を実旧hostで保持 |
| 3 | 対象純検査/型/再現生成/全file before-after packet | PG/正式受理/merge/P6blindは未実施と区別 |

旧実行環境専用のv4試験は旧Git0dbを実hostとして検証し続け、実gate正例だけ旧prior→新currentへの正規接続に追随する。旧証拠を削らず、現在の読取に不要な旧current配置の成功を要求しない。rootが共有schema/SQL/T5/rowgateを同候補へ接合し、最後の正式受理/全件/実PGを担当する。

## 候補証拠

新公式artifactはSH全走者進塁の作者修復 `a94cfac2` / SHA `71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff`。実Git `bb0b08dc` の0db3 IIFE/宣言と新IIFE/宣言をNodeDomainHostで旧v4の53入力へ実行し、旧全応答と原期待の完全一致、新応答と旧期待から実行pin2欄＋依存digest2欄だけ再束縛した全値の一致を確認。新v5 witness `981572b187097ac52435bb143cb718aa993c9ffec9692e9332b79894f2621955`、registry `fc55be98546bba6e4e6fdba53cbf0f8fa327550fae957eacb3e2cbd30aa00ab2` は再生成で同byte。

旧v1-v4 witness/registry・規範source等11資産は全byte保持。既validatorを含む既存全関数/decoratorは全byte保持し、既入口に新current固定分岐だけ追加。新validatorは旧4段の全固定hashと全検証を通し、旧4e8/4e7/ab8/0db＋新71fの5prior→新71f以外を拒否する。数学/RBI/OUT3/責任/型/registry順序・欠落・重複・旧段byte改変はhash追随しても拒否。既v4の53数学は実Git旧hostで保持し、実gateは旧4prior→新currentへ正規接続する。

7manifest/現在fixture5/既D11包絡5は実行pinと既宣言自己echo・canonical digest派生だけを更新し、別shadowで元a94 byteから17出力を再現一致。差分全leafはhash/digestまたはserialized V7中の旧pin→新pin完全可逆置換のみ。旧数学expectationを新hostの実測から採取していない。

検査: 旧v4＋新v5の24pure成功17.81秒、新v5改変26pure成功17.44秒、BE関連8suiteは131passed/2failed86.89秒（1件v2 D11自己echo更新漏れ、1件同時FE負荷中のNP guest TIME_LIMIT）。v2は既56規範からpin2+自己echo2だけ生成する手順へ是正し、同2caseを限定再実行して2passed5.51秒。期限は不変更、TIME_LIMIT初回を成功へ読み替えない。対象型/Ruff成功。FE metadata/API関連6suite131passed8.24秒、Vue型成功。実PG/正式受理/merge/CI/P6blindは未実施。rootの正式SQL・D03等body内artifact pinは本packet外で、rootが唯一generatorから接合する。

59playの画面シナリオも同71f hostで再純59操作を照合し、旧ef7の固定状態/flags/normal-endと一致した。これは実画面/認可/同TX/DB成功ではなく、driver期待を保った合法性対向だけ。共有SQL/schema/T5/rowgate接合後の実runはroot順序を守る。
