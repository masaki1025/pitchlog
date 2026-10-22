# U-F8 9パス追補の追加独立レビュー・採否（2026-10-22）

## 実行・固定対象

POが許可した「追補と既存9パスの直接影響だけ」の追加1回を実行済み。経路は `python .claude/scripts/codex_run.py review adversarial -`、read-only、新規独立session `01a163d2-832f-7442-b6dd-17ea4e43d1fb`、正常終了exit0。exit0はレビュー可決を意味しない。再レビュー/再実行はしていない。

- 対象R: `69bf83f5b94e3a529039da9b1d5eb5f2aac5953f`、起点: `cf9702abfc35b6a8d4dac157da60784993e9a7ea`。
- 完全binary diff SHA-256: `908af9d2b4274b79fbf0c0b95b64a5aab62f473544067b922d8f0f33cec81774`。
- 追補案の査読時SHA-256: `71231b528619c5e255eb86d82f81623b143b8506c61dce91ded968e5a047a7ad`。
- 完全候補patch SHA-256: `5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b`。
- 9パス抜粋patch SHA-256: `b666700c7a1ad4ea152e35a41425fb281a992f80afed87f8ea0a0b102c5a73ee`。
- 下記独立結果本文のSHA-256: `1a9bac3bc262117758244120ccaa53b31c90fe7e0b5c4cf1701141dc09596c88`。生成器/v3/関連証拠の固定hashは[固定manifest](step7-additional-review1-freeze.json)。これは未来のB/C/7.7値ではない。

## 独立レビューの実結果（原文、重複出力のみ除去）

## 固定対象の確認

HEAD `69bf83f5b94e3a529039da9b1d5eb5f2aac5953f`、起点 `cf9702abfc35b6a8d4dac157da60784993e9a7ea`を確認しました。完全binary diffのSHA-256は `908af9d2b4274b79fbf0c0b95b64a5aab62f473544067b922d8f0f33cec81774`、完全候補patchは `5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b`、9パス抜粋は `b666700c7a1ad4ea152e35a41425fb281a992f80afed87f8ea0a0b102c5a73ee`で、いずれも固定manifestと一致しました。抜粋9ブロックは完全候補patchの同一ブロックです。

## 指摘：P0=0、P1=1、P2=0

**UF8-A1｜P1｜受理範囲(3) DoDと成果物の不対応。** [追補案54〜56行](/home/ymdms/projects/pitchlog-worktrees/feature-uf8-game-entry/docs/features/uf8-full-game-followup/step7-plan-addendum-2026-10-22.md:54)は、後続の単一Draft PRの番号を固定して7.7へ提示すると定めます。一方、再利用予定の[生成器647行](/home/ymdms/projects/pitchlog-worktrees/feature-uf8-game-entry/docs/features/uf8-full-game-followup/step7-candidate/generate.py:647)は、生成metadataの受理単位を旧「Draft 6〜7の同一PR・番号未割当」に固定しており、[現metadata350行](/home/ymdms/projects/pitchlog-worktrees/feature-uf8-game-entry/docs/features/uf8-full-game-followup/step7-candidate/metadata.json:350)も同じ値です。このまま将来のBから再生成すると、新しいPR番号を示す提出資料と生成証拠が食い違い、どちらを受理単位とするか一意になりません。[ハーネス7.7-2](/home/ymdms/projects/pitchlog-worktrees/feature-uf8-game-entry/docs/development/dev-harness-design-2026-08-07.md:600)は1回の受理による遷移を1記録とします。**最小是正案：**追補に、旧metadata値の扱いと、後続の実PR番号に結び付くB/C証拠をどう整合させるかを明記する。既存の許可範囲で整合できなければ、7.7提示前に具体差分を判断へ戻す。

その他の直接影響では、historic候補の6 JSONは版・識別子と4件のdigest追随、生成Python 3本は各2定数の変更で、認可・SQL・負例本文の意味変更は見つかりませんでした。9パスは既存core登録glob内です。追補は#174→#173→Dのread登録の実統合・引渡し後を基線Bの条件とし、封鎖CIの成功と未接続real-game、iPhone・10秒・成績・CSVの未達を分けています。

**限界：**今回の判定は固定追補と9パスの直接影響のみです。将来のB/C、正式7.7値、製品全体は未審査で、テスト・CI・DBは実行していません。編集・commit・pushも行っていません。既存レビューの結果や回数は変更しません。

**判定：否決｜P0=0 / P1=1 / P2=0。**

## 採否と主担当反映

| 指摘 | 独立判定 | 採否 | 反映内容 | 再査読状態 |
| --- | --- | --- | --- | --- |
| UF8-A1 | P1・DoDと成果物の不対応 | 採用 | [追補5節](step7-plan-addendum-2026-10-22.md)に旧metadataの受理単位ラベルを歴史的・適用外として保持し、後続実PR N/B/C・生成metadata hash・全patch/前後値hash・正式履歴案の同じNを単一束縛表で対応付ける必須条件を追加。整合/再現性が保てなければ7.7提示と反映を止め具体差分を人間へ戻す。生成器変更を9パス許可へ抱き合わせない | 反映後の独立再査読なし |

確定指摘はP0=0/P1=1/P2=0、1件採用・不採用0。独立判定の**否決はRへの実結果として保持**し、主担当反映を可決/承認へ読み替えない。今回の許可1枠は実行1回/指摘反映1周で消費し、P0例外を発動/推定しない。最終案の承認・是正差分の受容は人間判断。

## 残る未再レビュー範囲と既存履歴

R以後に変更したのは追補5節のUF8-A1反映と結果参照、planの運用追記、当レビュー記録/固定manifest/作業ログの追加である。**全て追加独立未再レビュー**。旧v3/47367110・原計画最終反映の未再査読という過去記録は保持し、今回の限定レビューを未対象の製品コード/将来基線へ広げない。

原計画3回/13件全採用/最終P0限定/反映2周・最終反映未再査読、6〜7製品一次1回11件全採用/敵対基本2回と各親PR履歴は不変。今回の追加限定系列1回は別記し、旧frontmatter/可決範囲をリセット/過去へ追加しない。

現在は候補資料だけで、9パスの正式反映・7.7最終値導出・新規PR・実送信/開始/保存/再開等の封鎖解除は行っていない。必要な判断は追補の最終承認（UF8-A1反映の未再査読を含む）、後日B/C固定後の7.7本人受理と提出単位/操作の許可。追加査読を望む場合は別の明示枠が必要で、自動再実行しない。
