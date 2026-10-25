---
feature: mvp-t1-input-closure
status: active
承認: 済（2026-10-25・PO委任によるCodex判断）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f
branch: feature/mvp-t1-input-closure
created: 2026-10-25
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# T1入力閉鎖の有限実行手順

## 1. 背景・目的

[TSK544](https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f)の承認済みT1計画7d6ce544のステップ1内で、G6-S02の入力相関を先行供給する。[要件正本](../../requirements/requirements-pitchlog-2026-07-22.md)FR-003/FR-009、NFR-018/019を根拠とする。T1を実行する唯一の上位計画と既10計画反映/2確定ゲート周を保持し、本書で本体開始条件や既意味を変更しない。正式起点はdevelop dcd4fda8（PR183統合済み）。

## 2. スコープ

型検査と指定inning/現在inningの一致が必要であること、不一致時の状態変更0を、既正式payload/状態型へ束縛する。次の4pathだけが最初の実装対象である。

- contracts/state-transition/t1_g6_s02_input_schema_v1.json
- contracts/state-transition/t1_g6_s02_inputs_v1.json
- contracts/state-transition/t1_g6_s02_author_cases_v1.json
- tests/test_state_transition_contract_schema.py

3JSONは既候補の全byteを再利用し、author_casesのcandidate_only=trueを保持する。これは作者の必要条件ケースでありP6封印/独立期待値や完全S02の正式受理を表明しない。既operationRows3payload/既positive2件と完全一致を検査する。回不一致でmust-not-applyをother-preconditionsへ弱める変異を拒否する。一致だけでappliedへ昇格しない。

公開結果ID/D5、他G6、13不足分岐、7marker、23flag、製品T1計算/別計算器、Port/DB/HTTPは本単位で供給しない。未掲載単打配置へのD07拡張や観測推定、既D06拒否順変更も行わない。後続P8ケースは別の有限範囲確認後に扱う。正式共有資産とGitの唯一writerはroot、候補作者と独立レビュー担当は分離する。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| requirements/design/ADR/development/ops | 反映なし。既意味の必要条件を収録するのみ | 既原典との一致をPRレビュー |

本plan/researchと上記契約/試験以外は変更しない。共有識別値/派生値への実影響が判明した場合だけ完全前後値を固定し、既7.7でrootが受理する。未影響値の再承認は求めない。

## 4. 実装方針

状況計算の入力契約に触れるコア領域である。既core-areasのcontracts/state-transition/*と既schema試験捕捉を実確認し、core拒否条件は変更しない。候補はcache t1-g6-s02-current-candidate-20261025、author handoff ef5ec43245aede032d4b0f4c8543194cbaf07007b10e7c8cd0175e98b19c4019、非作者evidence59ec3f7ffbb28fd0280f6cd091bc52a2c912a46f5cca30da9b62455504c72b07。候補への非作者確認と本有限計画への確認を区別する。旧268試験定義を保持し、親/PR183のレビュー履歴をリセットしない。

### 実装ステップ(コミット単位)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 固定4pathの有限型/相関ケースを収録 | 前後SHA一致、既型/参照一致、20局所検査/義務弱化・適用昇格等の変異拒否、旧試験保持、Ruff/ty成功 |
| 2 | 実影響値・最終差分・必須CIを確認し通常提供 | 影響する場合だけ既7.7、最終HEADの非作者確認/PO委任証拠/必須CI。完全S02やT1本体の成立とは別記 |

本書のPO委任承認後にrootが指定ステップだけを実施する。署名/本人逐行確認/P6資格は代記しない。人間の再承認待ちを設けず、技術受理は実対象版/根拠/日時を記録する。

## 5. DoD

- 指定4pathが正式branchで再現でき、型/相関と現規範参照が検査される。
- 不一致ではpre_state_after全値不変を必須にし、必要条件一致だけの成功昇格を拒否する。
- candidate_onlyと公開結果/D5未供給を保持する。親S02全閉鎖/P8不足13/P7/P6/本体/MVP完成を主張しない。
- 最終差分/必要正式値/必須CI/通常統合までの証拠を対応付ける。TSK544全DoDは親計画のまま未達範囲を保持する。

## 6. テスト計画

NFR-019の単体/一致性として既schema試験へ追加し、extra/型/回不一致/状態改変/弱化/成功昇格/既参照ずれを拒否する。候補独立20成功/167変異拒否は当該候補の証拠であり、正式反映後にも対象検査を行う。統合候補固定後に必須全件CIを実施、実DB/実機試験は本入力準備単位の成果として数えない。P6封印/期待値本文を開かず、新blind導出とも呼ばない。

## 有限手順の承認記録

2026-10-25T11:45:57.153332+00:00、Codex主担当/rootはPO委任4/5/8/10に基づき対象dcd4fda8/plan486bbc3823b4bba0201fdbb58a21ecc30c75d896e6d6d5c7ea7761557d2efe58/research b699a98b7bb62680a4bad82b33d8b67800bdfa6411be9268a8012444d1f69a44を承認。非作者creation_pathの限定計画確認は可決0/0/0、evidence72b93e7e5491271816874ea0ca9b18481cda46f0b324a8552d58c9b4fde06bff。指摘反映0周。既候補の独立source確認とは別の計画確認1回で、親544/183の実績をリセットしない。まずステップ1の4pathだけ実施する。本人署名/逐行確認/P6新blind/完全S02/T1本体開始を成立扱いにしない。
