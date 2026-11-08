# P3 25件超の真正ページ処理・終結を現候補で完成させる

- 状態: 計画レビュー待ち
- 起点: `1bfad343fa365f3902d1a02b38a5f1b1a5cf8139`
- 枝: `feature/mvp-p3-paging-lifecycle-20261108`
- 担当: Codex recovery 子担当。PO委任によるroot採用後に製品実装へ進む。
- 計画レビュー回数: 0

目的は現候補で実HTTPの26件以上の変更・再取得・次球・再送と途中故障全取消を通すこと。既二段階ページ/私有stage/finalize・同TX/真正source/現在版CAS/全件digest検証を維持し、TTL延長/期限無視/固定成功/独自計算を追加しない。既P3作者sourceとcacheを再利用し全調査をやり直さない。

旧一次証拠はauthority binding idle10秒であるが、当該channelが現P3か旧残存か未証明。準備3.765秒・source最大gap3.667秒から『現P3再計算が期限超過』とは断定しない。既旧GETのwriterロックは現在RRへ修復済みなので、同原因が現候補にも残るとは扱わない。

## 編集所有

本担当だけが `backend/src/pitchlog/sync/past_correction_{execution,paged,preparation}.py`、`backend/src/pitchlog/domainrt/past_correction_lineup.py`、`backend/tests/sync/test_past_correction_paged.py`、専用 `backend/tests/db/test_p3_paging_lifecycle_http.py` とこの計画を編集する。既実HTTP試験は原本から専用試験へ再利用し、旧証拠を上書きしない。実証で必要なtest-only観測は固定stage/相対時間/例外型に限定し、本文/SQL/資格/IDをログしない。共通binding/transaction/正式SQL/正式assets/追跡artifact/共有台帳はroot専有。そこへの修復が必要なら根拠付き閉packetを渡し、所有移管前に編集しない。

## 実装ステップ

| ステップ | 内容 | 完了条件 |
|---|---|---|
| 1 | 現P3呼出と正式期限/更新・終結境界を旧証拠へ照合。既保証内のライフサイクル欠落が再現すれば最小修復と純正負。欠落未検出なら製品変更せず現候補の実検証を準備 | source根拠/対象path/旧証拠の射程を固定、仮説だけの修復なし |
| 2 | 既26件以上の実HTTP/owned PG試験を現正常49・唯一artifactへ接合し一回実行。新失敗なら最初の原因を有限観測で固定し必要修復へ | 真正ページ/保存/再送/読取/次球、途中故障の証拠または具体的未達 |
| 3 | 最終sourceの独立レビュー/必要再検証・証拠封印とroot接合packet | 未統合候補と正式提供を分離、残るMVP範囲を省略しない |

共通owned lockはfixture作成からcleanupまで保持し共有DSNを入口unset。source前後固定、実行中source変更禁止、同じ停止の無根拠反復なし。viewer実走は先行し、重いPGを競合させない。新意味判断が本当に必要な点だけrootへ提示する。
