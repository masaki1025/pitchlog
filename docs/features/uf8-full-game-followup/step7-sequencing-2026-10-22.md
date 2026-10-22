# ステップ7の共有資産順序と7.7準備（不変部分のみ）

## 実基線と先行PR

調査時の公表developは `760c04d540b22190cab076165f1b4e35ae473a1f`（#162実統合）。#172は `8a43d044052b6a343b3b90b0120d149898ac8f6c`、#170は `7717b986`、#153は `cad0f1eb` に統合済み。#172が追加した既受理25件目と旧署名/履歴は不変に保持する。

PO指定の順序は **#174→#173**。取得時#174 HEAD `4caa88c3fe2f76c5f78713fe09ee5283fdf9219f` と#173 HEAD `dac2ff15cd35b63a7c9f5bc69cd6a87f15e2ed5f` は、ともに番号取得用の引継ぎ資料のみを公開したDraft。製品・共有資産候補はこのHEADに未公開であり、旧#152/#156の受理を新値へ流用できない。

## パスの重なりと手順

| 資産群 | #174の公表予定 | #173の公表予定 | U-F8ステップ7 | 順序 |
| --- | --- | --- | --- | --- |
| tenant-boundary 9資産（base/census、追加6 JSON、frozen-inputs） | 9資産と外部8ファイル/履歴を新PR IDで再導出 | 9資産を実基線から再導出 | base/censusと追加6 JSONが変更候補。frozen-inputsは現在候補で変更0だが入力として照合 | #174実統合→#173再導出/受理/実統合→U-F8再照合。並行の履歴追記なし |
| 生成Python3（runtime/repository/tenant_context） | 契約追随の有無を先方の実候補で確定 | 3本を製品候補として明示 | 版/source_digestの限定追随 | 同上。先行成果を生成元ごと保持 |
| `history-snapshots/`・`base-allowlist`履歴 | 新#174の単一受理 | 新#173の単一受理 | 次の未割当単位。#171は候補コピーの統合であり正式受理IDとして割当済みではない | 既受理IDを移植/変更/重複追記しない。U-F8正式受理単位は人間と別途確定 |
| corpus宣言・`tests/fixtures/frozen-archive-cases/manifest.json` | corpus/seed/oracleと全前後値 | corpus/checker/fixture・snapshot | 比較manifest入力digestと既存corpus検査 | 先行PRの実変更を含む固定treeから導出。旧13値を流用しない |
| `.github/workflows/ci.yml` | S0〜S3参照・migration追随の必要差分 | checker/core/fixture影響の必要差分 | 必須frontend jobのブラウザ段・path filter候補 | 実CI差分を取得して再適合。harness取消/合否緩和なし |
| 認可/DDL/seed/oracle/共有checker | #174の所掌 | #173の所掌 | 旧U-F8候補では直接変更しない | U-F8が先回り編集しない。新たな直接波及は具体差分を判断へ戻す |

上表は取得した両PRの引継ぎ資料に基づく予定で、正確な重複パス/所有解除は各担当へ照会済み。返信とread-only実差分の照合は下の運用追記へ記録し、実統合前に所有解除と扱わない。U-G1 read登録の共有資産も重なるため、Dへこの順序とU-F8の正式編集0を伝える。

## 今進める不変の準備

- 固定v3/旧v2/旧提案/候補patchのbytes、既存レビュー回数/採否、過去の未再査読範囲を保全。
- [9パス判断票](step7-scope-decision-2026-10-22.md)、公開候補だけの抜粋patch、既承認との差・検査責任・受取物の一覧を作る。
- 再照合手順、履歴prefix保持、完全before/after bytes/hash、snapshot/corpus、生成整合/越境/実CI/実ブラウザの必要検査を列挙する。新しい正式値・次の通番・署名・受理単位は埋めない。
- 現在のv3/7.7 briefの161ab基線・24履歴/180snapshot値は歴史的資料であり、760c基線や先行PR統合後の受理値としては無効。既存資料を最新値へ書き換えて隠さない。

## 実統合後にだけ導出する7.7提出物

1. #174/#173の実merge SHA・develop包含・各最終CI・担当からのパス引渡しを確認し、公表基線Bを固定。新しい並行変更がある重複パスは先行させる。
2. BとU-F8の候補生成source/生成器SHAを固定し、全正式入力blob/逆依存閉包を照合する。元からの25件に限らず、Bに存在する**全受理履歴**を全値/署名・全snapshot bytesごとprefix保持する。
3. 範囲承認の限定差分だけを候補Cとして導出。CI・全波及JSON/生成Python/比較manifest・新snapshot/corpusの完全before/afterとSHA/識別子・射影・外部入力を同じ候補単位に固定する。表を超える差分は適用せず判断へ提示。
4. 隔離Gitで通常git apply --check/実apply、旧履歴不変・新行人間欄空、全生成一致、snapshot/archive/corpus/凍結/tenant境界を検査。必要な独立査読の許可枠と実対象を固定し、既存基本2枠はリセットしない。
5. 人間へB/C・固定diff・実受理単位・全前後値・検査/査読・未再査読範囲を一括提示して7.7の正式受理を得る。本人確認/受理/署名を代記しない。公開/マージの許可、新規PRの許可は今回与えられていない。
6. 正式反映が許可された後だけ適用し、全検査/最終CI/ブラウザ検査を回収する。候補CIのsealed-ui成功と実Port未提供のreal-game未達を別に保持。

### 運用追記

担当返信と実統合SHAは、実際に取得した時点で追記する。未回答を承認/所有解除や未提供Portの成功化へ使わない。

- #174担当回答: JSON6全件、生成authz/runtime、CI/base/census、正式反映時snapshot/corpusが重複。実統合SHAは未提供、#174→#173の実統合後にU-F8再導出という順を回答。
- 生成第3パスの照合注意: 初回先方走査は `backend/src/pitchlog/tenant_context_contract.py` を対象にしていた。U-F8が正しい `backend/src/pitchlog/repositories/tenant_context_contract.py` を先方worktreeでread-only照合したところ**差分あり**。したがって現在の重複実測はJSON6＋runtime＋tenant_contextの8件で、repository_contract生成のみ差分なし。正しいパスで担当へ再確認を送付済み。パス誤認を非重複/編集許可の根拠にしない。

- #174担当は正しいパスで再走査し、JSON6＋runtime/tenant_context生成2件の**8件重複**へ回答を訂正した。repository_contract生成1件のみ現在差分なし。初回7件という回答は撤回済みとして保持する。
- Dのpreparing read登録も#173後に同資産を変更するとの通知を回収。U-F8側は**#174→#173→Dのread登録の実統合/引渡し→U-F8**へ自分の正式編集を後置すると回答した。PO指定の#174→#173順を維持し、DとU-F8による同一履歴位置の並行追記を避ける。DのPR番号/固定製品SHA・共有差分/他担当受諾は取得後に記録する。

- Dの公開Draftは#175、取得HEAD `36e7129d17d584a4898d3ae0a212145e9373e65b`、base=develop。DTO/read componentの部分提供であり、正式read登録/保存成功提供とは区別する。U-F8が作成した新規PRではない。
