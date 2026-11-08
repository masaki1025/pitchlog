---
feature: mvp-p3-batted-family-followers
status: active
承認: 済（PO委任Codex主担当/root、2026-11-08 21:00 JST）
重さ分類: コア領域
branch: feature/mvp-p3-batted-family-followers-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-p3-batted-family-followers-20261108
created: 2026-11-08
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# P3後続打球群の再計算接続

既承認 `docs/features/mvp-past-correction-product/plan.md` step2/4 の有限拡張。起点はroot統合 `ee8b3e52dab981c4f393f95e4d3de8c81169572f`、現 `past_correction_lineup.py` は後続4安打だけを許可する。既artifact `71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff` の通常打球12結果へ、対象外の**後続原本再生と訂正後再評価**を広げる。対象投球の変更種別・結果（ball/called）と保存済み旧履歴の意味は変えない。妨害は新artifact未供給につき対象外。

編集所有は `backend/src/pitchlog/domainrt/past_correction_lineup.py`、新専用pytest、本計画のみ。正式schema/SQL/artifact/ledger/PGと他WTは編集しない。

| # | 実装単位 | 到達条件 |
|---|---|---|
| 1 | 閉followers拡張 | 12打球結果を原T1/V7/actual ID・参加者・走者・lineup・責任投手・phaseと同核旧再生へ束縛し、元観測の現行資格欠落や訂正後成立不能を閉拒否する。旧4安打/通常targetを維持 |
| 2 | 投影対向と候補封印 | 既71f host→seal→current codec→既41列/runner/T5で凡打hold、SH/SF/DP/FC、公式error、RBI-04を正負確認し、旧原本を書き換えない。型だけ通るfixture成功を禁止する。差分・検査・残件をroot独立レビューへ渡す |

原V7を書き換えない。訂正後に打席・攻守・走者資格が変わり同じ観測を再採用できない場合はI6候補として閉拒否し、第三アウトや打点因果を新たに推測しない。旧保存再生へ新RBI観測を遡及必須にせず、新訂正のcurrent payloadだけが現行因果条件を満たす。全試合/全P3操作の完了はこの候補単位では主張しない。

## 実装進捗

step1/2候補: 現行T1閉12結果と後続許可集合を全値一致にし、対象打球の閉拒否は維持する。71f実hostで対象後の凡打hold、犠打、犠飛、併殺、野選、公式失策2形、RBI-04を再生/訂正後再評価し、元V7/物理41列/走者/T5の全値一致を確認する。対象前の凡打原本も原形のまま持ち越す。別event・欠V7・改竄lineupは不成立とする。正式統合/実PG/独立確認は未実施。

## 非作者P1を受けた限定修復（2026-11-08 21:59 JST）

b417の最初の限定REPORT3452e659…はI6/HTTP/PG分類を範囲外としていたが、rootがcaller2経路との関係を照合し、非作者追補fd449238…がP1を確定した。新しいProtocolError→Unsupported変換は、既保存原本のseal破損をnonpagedのContentRejected/pagedのrejected系へ再分類し得る。実DBでD5結果変化を実証したとは言わず、変更を正当化する契約根拠もないため採用しない。

rootは新catch2箇所と不要importだけを旧分類へ戻し、followers12の許可集合/target4/replacement2/旧再生と新RBI資格/全response・物理・T5比較は維持した。改竄lineup原本は具体的なProtocolErrorを要求する負例へ是正し、saved-seal/saved-payload各故障の例外identity・元呼出一回を2対向で追加。限定3passed2.57秒、Ruff/Ty成功。最初の収集は別WT venvのeditable import先へ解決して失敗したため、新WT src:testsを明示し実import先を確認してから上記を実行した。製品失敗/実PG検査とはしない。修復後sourceの非作者差分再確認後にroot統合へ採否する。
