# post-153 T2固定候補へのU-F8/523回答（2026-10-23）

## 対象と受取の限界

TSK-564のローカル固定コミット `8a816e02f6250cc13efdfcf1edaa2083d6481270`、`docs/features/t2-provenance-checker/candidates/t2-product-handoff-v1/README.md` / manifestを受領対象とする。供給側基線表記は `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`、manifest SHA-256 `8e2b99716eee5d45234b8f4e2d2aae9c25b482fe6f2cece9c1087cfdc1bbe660`、contract候補 SHA-256 `225b8fd736ade548b52233f8245228c1a86d8ef9048105115d455fa333e12533`。公開済み/正式反映済みではない。固定コミットの11資料hash、24規範射影/59具体case/54ハーネス入力、旧5セル参照と表示11case/E11二caseのIDを構造・対応だけ照合した。作者の期待射影を独立に正しいと検証したとはしない。

当回答は**U-F8自担当の候補受領と表示責任の回答**であり、7.7正式資産受理・型の製品提供・P-6所有側受理・本人確認/署名ではない。独立oracle/製品比較/実HTTP/DB完成を候補受領前条件へ追加しない。GAP-05はopenを維持する。

## 項目別回答と実担当

| 対象 | U-F8回答 | 実担当・境界 |
| --- | --- | --- |
| scope/projectionRevision/対象cell(inning,half)を揃えた表示責任 | 受理（候補/523責任） | U-F8/TSK-523が提供済み投影/生成formatterの結果を既存GameScreenLiveDisplayへ描画。UI独自の終了/X判定・得点計算は作らない |
| 未開始blank・開始済み整数（0を含む）・不要な未開始裏Xの区別、旧5セル保持 | 受理（候補対応） | 表示結果の受取/0を未取得にしない描画/不一致時未取得・旧投影拒否は523。started/対応表完了/裏不要の意味・適用時点は545、記録セル得点は544 |
| 評価状態が裏であることと攻撃開始receiptの分離（E11） | 受理（候補対応）、比較キーの補足は要修正 | 545が開始receipt/完了評価/対象cellの出所を供給。523はstatePosition/evaluationHalfだけから開始済みと推定しない |
| `decision.xMark`単一結果と全cell表示の区別 | 受理（境界） | 545/契約所有の正式型・単一生成formatterへ接続する。523がxMarkを全cellへ一括配布したり、候補inputから別の判定関数を作ったりしない |
| 全59caseのT2規範/終了・DRAW/phase/認可・undo後再評価 | 担当外（表示射影の受取は523） | 545/564/正式契約所有。523は新outcome/権限を決定せず、宣言済みを自動再宣言・解除しない |
| 正式表示型・formatter/codec、prefixとrevisionの照合契約 | 未提供/要修正（受領を拒む条件ではない） | 545/契約・生成物所有が正式版/対象cell/順序/prefix・出所を公開し、523は同版をimport/受取。現UIのInningCell/DisplaySupplyはUI専用型で正式供給の証拠ではない |
| P-6独立oracle・正式受理、GAP-05製品比較 | 未実施を保持、独立導出/正式受理は担当外 | 独立担当が独立期待値、権限ある受理者が正式受理。523は実装後の同一キーで実formatter/製品表示との比較を担当し、自己fixtureをoracleへ昇格しない |

## 具体caseとの対応（候補期待射影の参照）

次の表示値は供給側候補の主張を転記した対応であって、523の独立期待値ではない。

| 既受領5セル/追加観点 | 新固定候補case | 受け取る表示射影 |
| --- | --- | --- |
| DISPLAY-COLD-AFTER-TOP | T2-DISPLAY-COLD-AFTER-TOP | 5裏の未開始/不要cellはX |
| DISPLAY-FUTURE | T2-DISPLAY-FUTURE | 将来の6裏はblank |
| DISPLAY-STARTED-BOTTOM | T2-DISPLAY-STARTED-BOTTOM | 開始済み5裏の提供得点3 |
| DISPLAY-DECLARED-UNSTARTED | T2-DISPLAY-EARLY-DECLARATION | 早期宣言後でも未開始7裏はblank |
| DISPLAY-STARTED-BEFORE-FIRST-PITCH | T2-DISPLAY-FIRST-PITCH-PENDING | 開始済み初球前の1表は整数0 |
| 通常/延長の不要裏 | T2-DISPLAY-NORMAL-AFTER-TOP / T2-DISPLAY-EXTRA-AFTER-TOP | 9裏/12裏の当該不要cellだけX |
| 開始済み完了/サヨナラ | T2-DISPLAY-STARTED-COMPLETED / T2-DISPLAY-WALKOFF | 当該cellの提供整数4/2 |
| 未開始表/同点で必要な裏 | T2-DISPLAY-UNSTARTED-TOP / T2-DISPLAY-TOP-TIE-BOTTOM-NEEDED | 未開始8表/必要な12裏はblank |
| E11未開始 | T2-E11-BOTTOM-NOT-STARTED | post-turnの評価位置が5裏でも、未開始/不要と結び付く対象cellはX |
| E11開始済み | T2-E11-BOTTOM-STARTED | 5裏開始receiptとT1セル観測3を受け、3を表示。総得点10からセル3を算出しない |

旧GE-CANDIDATE-E02-DECLARED/E09-LOCKED/E10-REOPENEDの既受領表示境界は維持する。追加T2-DECLARED-UNDO-BOUNDARYを根拠に終了宣言後のundo許可を新設しない。E11開始済みのcaseKind=negative/部分射影は既存型の不足を示す候補で、正式行の修正済み/全6出力の正解とはしない。

## 不足・供給側へ返す具体点

1. **E11の比較キー対応**：表示11caseにはscope/projectionRevision/targetCellが明記されるが、E11二caseはevaluationContext/displayCellObservation側の座標/開始観測で表現されている。独立比較へ渡す前に、case ID→同一scope/accepted prefix/対象revision/targetCellへの対応参照を補足してほしい。新しい規則や得点を推定で埋める依頼ではない。
2. **revisionとprefixの正式対応**：synthetic revision41やstatePositionだけでは実accepted prefixへの相関を証明しない。545/544が公開する版・scope/prefix・開始receipt/セル観測と整合する閉じた受渡し型・失効/旧投影拒否契約が必要。523はそれを受けて描画する。
3. **正式表示型/生成formatter**：現UIは整形済みのtext/blank/unavailableを受ける。X/blank/整数の選択意味をUIへコピーする依頼としては受けない。候補条件から単一formatterへ移す正式所有・対象版・import先を545/契約側で確定し、523へ提供してほしい。全型完成や製品Portを今回候補受領の前提にはしない。
4. **独立oracle/製品比較**：新規case・旧5セル/E11を、同じscope/prefix/revision/cellで照合する独立導出と実製品結果は未実施。作者のvalidation-results/自己fixtureは構造検査の証拠に限定。未取得を0/blankの成功へ置換しない。
5. **新しい意味裁定**：T2-DECISION-COLD-WALKOFF-PRIORITYのA/BはPO/意味所有側の判断で523は選ばない。共通の候補表示射影の受取とoutcome未決を分離し、E08から優先理由を推定しない。

## 状態保持

正式T2の旧8行/248case/拒否12入力・T1資産・旧署名・旧P-6 blocked/verifiedは変更しない。型/formatter/規範の正式反映は供給側の別ゲートで、実HTTP/専用DB/独立比較は実装後DoD。U-F8の9パス追補（最終案52797591/SHA e6946557...）は別の未承認事項のまま、新規パス/製品機能を今回追加しない。未接続の取消/訂正/確定/保存/送信/開始/再開の封鎖、新規PRなし・本人確認代記なしを維持する。
