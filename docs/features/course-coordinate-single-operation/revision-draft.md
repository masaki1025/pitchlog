# 座標量子化 正式改訂草案（現行起案との対応）

対象版: `2c87758d` を基線とする反映候補。ADR-003 v0.10・要件v2.18はin-review。正式確定は未了。

- D-14-mの許可・関係規定・着手前/マージ前・開始/終期をT1/T2および座標入力形成の量子化に揃える。他対象は拡張しない。
- 付録A-1はhalf-up、B-2の視点とD11=Aは量子化後の投手後方視点のx反転を規定する。y反転はB-7で一度。
- ABIはJSON文字列in/out、入力 `{x,y,view,size}`（x/y/sizeは十進文字列）、出力 `{ok:true,value:{unit,x,y}}` または `{ok:false,error:{code}}`。
- 入力文法は `^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$`。入力長400・指数絶対値400は実装防護上限。表示側はクランプ、operationは量子化前の厳密値による範囲外拒否。
- 既存42ケースとB-7の式・丸めは不変。入力形成は別計算 `course-input-quantization`。
- NFR-018(c)の既存例外は `COURSE_COORDINATE_SIZE` のみ。本改訂では例外表を変更せず、新operationを例外に追加しない。float反転削除・検証テストの追随は実装段の本書改訂。
- D-11計算manifest `backend/domain/manifest.json` はゲート後に新設。artifact SHA宣言とは別資産。
- 試作第3版SHA256 `71b515e35e470c3f66f6f6ab6377d3be07c60308904a677882ac2a2dbd2b06e3`、oracle `edcf5eadb2ba280b24be041b5a6db19ce8535649c656ba65b592c0eaa346d9fc`。保管先 `/tmp/opencode/proto/` は作業用であり恒久資産ではない。製品実装済みとは扱わない。

承認はPO委任によるCodex判断として対象版・日時・非作者レビューを記録する。PO本人の実値確認・署名は代記しない。
