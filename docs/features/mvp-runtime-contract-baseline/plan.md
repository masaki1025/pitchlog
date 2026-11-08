---
feature: mvp-runtime-contract-baseline
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-08T21:02:40.675335+09:00、既実装追随の有限整合に限定）
重さ分類: コア領域
branch: fix/mvp-runtime-contract-baseline-20261108
計画レビュー周回: 0
---

# 現行登録へ検査基線を追随する

起点ee8b3e52の既知赤2件を独立単位で是正する。製品動作・DB操作許可・認可・拒否・数学期待は変更しない。ステップ1の旧28/後尾17という検査内位置を、既stageA資産28件は不変のまま、P3の9件/後尾22件を含む現行59件の全operation/function対の固定期待へ更新し、旧語彙/RG1/Statsの全入力出力・型・capability検査は残す。自己参照のruntime出力を期待にするのではなく、対象版の宣言/生成runtime双方の既登録を全値照合し、以後の追加/削除/並替えを拒否する。

| ステップ | 範囲・完了条件 |
| --- | --- |
| 1 | backend/tests/test_authz_repository_contract.pyのstale stageA exact期待だけを追随、全59順序/function対と旧詳細検査を保持。関連pytestで赤を確認/是正し、製品sourceは不変更 |
| 2 | contracts/tenant_boundary/base-allowlist.jsonの_BindingAuthority._call署名と正例fixtureへ既register_d1lessを追加。allowed_api_ids/対象symbol集合/拒否条件は不変。既正式helperで受理record/生成/corpusを導出して独立レビュー・必須検査へ。手で生成Pythonやsnapshotを調整しない |

ステップ2正式値/受理はrootが対象版/差分/根拠を照合して記録する。検査のskipや弱化によるgreen化はしない。実PG/共有DB/秘密/他worktree/共有台帳をこの枝では編集しない。計画/最終の非作者確認は別途実施し、現時点で成立扱いにしない。

## ステップ1検査

PO委任rootの既実装追随: stageAの資産/生成モジュール28件は変更しない。登録内のstageA28をIDで選択し、P3 9件/後尾22件/全59件の順序とfunction対を固定期待で全照合する。旧語彙/RG1/StageA/Statsの入力出力型/capability/DDLとの区別/パラメータ検査を残す。対象pytest 1passed2.55秒、正式7.7受理/全件CIの成功とはしない。
