# ステップ7の7.7正式受理へ渡す候補（未受理）

本書は受理記録ではない。計画承認・候補追随の範囲承認・機械検査を、正式資産受理・担当受理・署名へ読み替えない。実CI/正式基線/backend製品への適用は0である。

現在の提案は、最新公表develop `9136c2dad916313c28698f49f8668f3edbe36b4a` と正式入力339 blobを照合したもの。完全な13ファイルのbefore/after、旧23履歴179snapshot、新1履歴9snapshot、識別子/射影/外部入力のhashは[metadata.json](step7-candidate/metadata.json)に一元化した。[追補v2](step7-scope-extension-v2.md)に全13ファイルSHAの前後表、[candidate.patch](step7-candidate/candidate.patch)に全適用差分がある。

- patch SHA-256: `ad6642d2dd4cdaa37e1e0aeb92f42efadb506a40208e22b9b224911cb877a118`
- CI前: `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`
- CI後候補: `9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65`
- corpus前: `b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`
- corpus後候補: `7279ca0247dd41e2b294151daac4361a1ae2a9b8ec364248495748a04bc7977c`

候補は通常git apply --check、隔離適用後の13 after bytes/9snapshot SHA、生成3モジュールのbackend整合83件、既存snapshot/corpus検査、コミット/別枝統合後の再現性検査に成功した。正式人間欄が空の候補であり、正式履歴の合格を示すものではない。

受理前には、この後続6〜7 Draft PRを単一の対象として、正式な適用前後SHAと受理単位を固定する。PR番号は作成後のPR本文/コメントで本候補に紐付ける。実適用後のcommit SHAや本人の署名を先に作ったことにはしない。accepted_by/date/on/signature、新履歴のacceptance_id/approved_by/onは未記入のまま保持する。

共有する凍結基線は#153・U-S1・U-R1の候補とも重なる。編集/正式適用の順番が決まり、公表基線が変われば、本候補の鮮度検査で差を検出し、正式受理前に全前後値とdigestを再固定する。候補の存在を他担当の着手前条件や担当受理にしない。

追加6 JSONと生成3 Pythonの範囲追補、7.7の実値受理はそれぞれ人間判断待ち。App.vueのナビ/復帰追補も別の判断である。正式ゲームPort、544/545の計算/公開契約・同一変更の実呼出部、T5/T6等が未提供のため、GAP-05・原子性・実1試合は成立していない。受理後もそれらの実画面→実HTTP→専用DB検証を別に行う。
