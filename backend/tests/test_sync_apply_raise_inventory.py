"""O5 の列挙と ``sync/*.py`` の ``raise`` 全件の棚卸しを AST で突合する。

突合は 2 本(US-1 提示 6-4):

1. ``O5_CODES`` と、AST の ``raise O5InvariantViolation(<code>, ...)`` の
   ``<code>`` の集合が一致する(過不足を別々に数える)
2. ``sync/*.py`` の AST の ``raise`` 文と、下の棚卸し(``_TABLE``)が一対一で
   対応する(欠落 0・余分 0)

棚卸しは US-1 の設計 ``docs/features/us1-sync-port-surface/design.md`` 11-4 の表
(コミット ``b63d11e9`` 時点の 193 行)を、ステップ 8 で試験データへ移したもの。
以後は**この表が棚卸しの正**。``raise`` を足す・消す・型や文言を変えるコミットは、
同じコミットでこの表を更新する。

表の列(`` | `` 区切り):

1. ファイル(``sync/`` からの相対)
2. 関数(クラスの中は ``クラス.メソッド``。モジュール直下は ``<module>``)
3. 例外型(``raise X(...)`` の ``X``。引数なしの再送出は ``(再送出)``、
   インスタンスの送出は式そのもの)
4. 文言(位置引数のうち文字列リテラルはその値、それ以外は ``ast.unparse`` の式、
   キーワード引数は ``名前=式`` を ``", "`` で連結。引数がなければ空)
5. 行(**表示用** — 照合のキーにしない。無関係な編集で動くため)
6. 区分(design.md 11-2 の区分。区分 8 は 11-1・11-2 の判定ごとに分ける)
7. 備考(``-`` は無し)

照合のキーは「ファイル・関数・例外型・文言・出現順」(同じ 4 項目の行が複数あれば、
ファイル内の出現順で対応させる)。区分の判断に迷う行は備考に「要確認」と書く。
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Final, Literal, NamedTuple, cast, get_args

import pitchlog
from pitchlog.sync import invariants
from pitchlog.sync.invariants import O5_CODES, O5InvariantViolation

_PITCHLOG_ROOT = Path(pitchlog.__file__).resolve().parent
_SYNC_ROOT = _PITCHLOG_ROOT / "sync"

type _Key = tuple[str, str, str, str, int]


type RaiseCategory = Literal[
    "1 適用外",
    "2 定義・登録の検査",
    "3 S-1",
    "4 P3",
    "5 内部制御",
    "6 O4",
    "7 既に境界結果(B3a)",
    "7 既に境界結果(B4)",
    "7 既に境界結果(RG1)",
    "8 O5",
    "8 再照合前",
    "8 再掲の破損",
    "8 確定スロットの食い違い",
    "8 U-R1 待ち",
    "8 B3a",
    "8 B7(状態依存)",
    "8 B7",
    "8 決定的・取引外",
    "8 決定的・確定後",
    "8 中継",
]

RAISE_CATEGORIES: Final[frozenset[str]] = frozenset(get_args(RaiseCategory.__value__))


class RaiseRow(NamedTuple):
    """棚卸しの一行。"""

    file: str
    function: str
    exception: str
    message: str
    line: int
    category: RaiseCategory
    note: str


_TABLE = """
apply.py | _preflight_d1 | RuntimeError | 自テナントの記録権世代行が一件ではない | 189 | 8 決定的・取引外 | -
apply.py | _preflight_d1 | RuntimeError | D3 の型が不正 | 192 | 8 決定的・取引外 | -
apply.py | _preflight_d1 | RuntimeError | 記録権世代の型が不正 | 195 | 8 決定的・取引外 | -
apply.py | _preflight_d1 | RuntimeError | D3 の型が不正 | 215 | 8 決定的・取引外 | -
apply.py | _run_d1_event | (再送出) |  | 290 | 8 中継 | -
apply.py | _apply_d1_request | TypeError | registrations と targets は D1 をキーにする | 475 | 2 定義・登録の検査 | ステップ 4〜6 で追加(呼出し規約)
apply.py | _apply_d1_request | P1PreconditionError | P4 は記録権不成立の経路に限る, other | 489 | 8 決定的・取引外 | -
apply.py | _apply_d1_request | RuntimeError | 同じ一時 ID に異なる確定選手 ID がある | 604 | 8 決定的・確定後 | -
change_path.py | _target | ValueError | V10 の対象参照が不正 | 79 | 4 P3 | -
change_path.py | _target | ValueError | V10 の対象参照が不正 | 91 | 4 P3 | -
change_path.py | _accepted_from_candidate | RuntimeError | P3 の保存済み結果の形が不正 | 115 | 4 P3 | -
change_path.py | _apply_locked | RuntimeError | 認可後に試合行が消失した | 132 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B9', event.d5, '要求作成時の復旧世代が旧世代') | 147 | 4 P3 | -
change_path.py | _apply_locked | _D5Race | previous | 155 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, '変更対象の試合が進行中・終了後ではない') | 158 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B9', event.d5, '現在の記録権証明がない') | 170 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, 'P3 のイベント種別が不正') | 174 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, 'P3 の内容は JSON object が必要') | 178 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, 'V10 の対象参照が不正') | 184 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, 'V11 の期待版が不正') | 188 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, reason or '変更内容を受理できない') | 193 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B14', event.d5, '変更対象が存在しない') | 201 | 4 P3 | -
change_path.py | _apply_locked | RuntimeError | event_slots の対象行が一件ではない | 205 | 4 P3 | -
change_path.py | _apply_locked | RuntimeError | 対象の確定版の型が不正 | 209 | 4 P3 | -
change_path.py | _apply_locked | _NoWriteResult | RejectedChangeResult('B8', event.d5, f'現在版: {current_version}') | 211 | 4 P3 | -
change_path.py | _apply_locked | RuntimeError | D5 再照合が未使用に戻った | 245 | 4 P3 | -
change_path.py | _apply_locked | _D5Race | outcome | 246 | 4 P3 | -
change_path.py | _apply_locked | RuntimeError | 試合行ロック下で対象版の CAS が失敗 | 254 | 4 P3 | -
change_path.py | apply_p3_change | ValueError | P3 の要求 1 件が必要 | 290 | 2 定義・登録の検査 | -
gate.py | game_accessible | RuntimeError | 認可対象の試合行が複数ある | 46 | 8 決定的・取引外 | -
gate.py | read_before_d5 | RG1Blocked | RG1 の事前読取に失敗 | 56 | 7 既に境界結果(RG1) | -
gate.py | read_before_d5 | RG1Blocked | 復元調整中 | 58 | 7 既に境界結果(RG1) | -
gate.py | check_before_commit | RG1Blocked | RG1 のコミット前読取に失敗 | 66 | 7 既に境界結果(RG1) | -
gate.py | check_before_commit | RG1Blocked | 復元調整中 | 68 | 7 既に境界結果(RG1) | -
idempotency.py | _json_value | TypeError | 入力原本の JSON object のキーは文字列が必要 | 53 | 2 定義・登録の検査 | -
idempotency.py | _json_value | TypeError | 入力原本に JSON 以外の値を含められない | 59 | 2 定義・登録の検査 | -
idempotency.py | _stored_result | RuntimeError | D5 台帳の読み取り列数が正本と異なる | 105 | 2 定義・登録の検査 | -
idempotency.py | _stored_result | RuntimeError | D5 台帳の保存結果の型が不正 | 117 | 8 決定的・取引外 | -
idempotency.py | classify_result | ValueError | 未知の適用経路 | 128 | 2 定義・登録の検査 | -
idempotency.py | classify_result | RuntimeError | 同じテナントと D5 に複数の台帳行がある | 132 | 8 決定的・取引外 | -
idempotency.py | classify_request_d5 | ValueError | D5 指紋の件数がイベント列と異なる | 159 | 2 定義・登録の検査 | -
idempotency.py | insert_result_or_recheck | (再送出) |  | 195 | 8 B7 | -
idempotency.py | insert_result_or_recheck | RuntimeError | D5 一意制約違反後に先着行を観測できない | 198 | 8 B7 | -
idempotency.py | decode_stored_negative | RuntimeError | 拒否・退避以外の保存済み結果 | 250 | 8 B7 | -
idempotency.py | decode_stored_negative | RuntimeError | 拒否・退避の保存済み結果の形が不正 | 261 | 8 再掲の破損 | -
intent_ids.py | derive_sync_intent_id | ValueError | 同期意図にはイベント識別と既知の範囲が必要 | 20 | 2 定義・登録の検査 | -
invalidation.py | _record_intents | (再送出) |  | 70 | 8 B7 | -
invalidation.py | _record_intents | RuntimeError | 意図の一意制約違反後に先着行を観測できない | 72 | 8 B7 | -
invalidation.py | record_p3_intents | ValueError | P3 の V10 と対象確定版が必要 | 116 | 2 定義・登録の検査 | -
invalidation.py | record_d1_intents | ValueError | D1 付き経路には試合 ID と D5 が必要 | 137 | 2 定義・登録の検査 | -
invalidation.py | _optional_uuid | RuntimeError | f'意図行の {column} の型が不正' | 145 | 1 適用外 | -
invalidation.py | _delivery_intent | RuntimeError | 意図 ID または範囲の型が不正 | 158 | 1 適用外 | -
invalidation.py | _delivery_intent | RuntimeError | 意図行の chart_kind の型が不正 | 160 | 1 適用外 | -
invalidation.py | deliver_pending_sync_intents | ValueError | 配信ページの上限は 1〜100 | 187 | 1 適用外 | -
invalidation.py | deliver_pending_sync_intents | RuntimeError | 意図行の列数が正本と異なる | 204 | 1 適用外 | -
invalidation.py | deliver_pending_sync_intents | RuntimeError | 意図 ID または範囲の型が不正 | 208 | 1 適用外 | -
invalidation.py | deliver_pending_sync_intents | RuntimeError | 同期意図 ID と範囲が一致しない | 213 | 1 適用外 | -
invalidation.py | deliver_pending_sync_intents | RuntimeError | 配信完了を記録した意図行を再読できない | 237 | 1 適用外 | -
invalidation.py | deliver_pending_sync_intents | RuntimeError | 配信完了の状態が永続化されていない | 241 | 1 適用外 | -
model.py | _object_with_keys | RequestShapeError | S-1: JSON object またはキーの外形が不正 | 79 | 3 S-1 | -
model.py | freeze_json | TypeError | JSON object のキーは文字列が必要 | 91 | 2 定義・登録の検査 | -
model.py | freeze_json | TypeError | JSON に含められない値 | 93 | 2 定義・登録の検査 | -
model.py | SyncEvent.__new__ | RequestShapeError | S-1: D5 または試合 ID が UUID 正規形ではない | 135 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: 未知の適用経路 | 176 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: 試合 ID が UUID 正規形ではない | 178 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: イベント列の外形が不正 | 182 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: P3 は変更イベント 1 件が必要 | 185 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: P3 の復旧世代がないか型が不正 | 187 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: P3 に D1・D4・V6・V8・V9 を指定できない | 194 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: D1 付き経路に復旧世代・V11 を指定できない | 199 | 3 S-1 | -
model.py | SyncRequest.__new__ | RequestShapeError | S-1: 試合 ID がイベント列と一致しない | 204 | 3 S-1 | -
model.py | SyncRequest.from_payload | RequestShapeError | S-1: 変更イベントの識別がない | 241 | 3 S-1 | -
model.py | _validate_d1_events | RequestShapeError | S-1: D1 付き経路のイベント列は空にできない | 272 | 3 S-1 | -
model.py | _validate_d1_events | RequestShapeError | S-1: D1 付き経路の D4 がないか型が不正 | 274 | 3 S-1 | -
model.py | _validate_d1_events | RequestShapeError | S-1: D1 または要求内 D4 が不正 | 281 | 3 S-1 | -
model.py | _validate_d1_events | RequestShapeError | S-1: D1 が重複している | 284 | 3 S-1 | -
model.py | _parse_d1_payload | RequestShapeError | S-1: イベント列は空でない JSON array が必要 | 294 | 3 S-1 | -
model.py | _parse_d1_payload | RequestShapeError | S-1: イベントの識別がない | 313 | 3 S-1 | -
model.py | SyncEventBatch.__new__ | RequestShapeError | S-1: 試合 ID が UUID 正規形ではない | 349 | 3 S-1 | ステップ 6 で追加(E-1 の外形)
model.py | SyncEventBatch.__new__ | RequestShapeError | S-1: イベント列の外形が不正 | 353 | 3 S-1 | ステップ 6 で追加(E-1 の外形)
model.py | SyncEventBatch.__new__ | RequestShapeError | S-1: D1 付き経路に復旧世代・V11 を指定できない | 356 | 3 S-1 | ステップ 6 で追加(E-1 の外形)
model.py | SyncEventBatch.__new__ | RequestShapeError | S-1: 試合 ID がイベント列と一致しない | 358 | 3 S-1 | ステップ 6 で追加(E-1 の外形)
model.py | AcceptedChangeResult.__new__ | ValueError | 変更受理には I6 の対象参照と確定時刻が必要 | 454 | 4 P3 | -
model.py | AcceptedChangeResult.__new__ | ValueError | 変更受理には期待版と確定内容が必要 | 456 | 2 定義・登録の検査 | -
model.py | RejectedChangeResult.__post_init__ | ValueError | P3 の拒否結果には B8〜B14 が必要 | 481 | 2 定義・登録の検査 | -
ordering.py | _assign_d2 | P1ContentRejection | P2 の V6 は非負の bigint が必要 | 45 | 8 B3a | -
ordering.py | _assign_d2 | O5InvariantViolation | d2_row_type, D2 順の行の型が不正 | 60 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の ordering.py:49)
ordering.py | _assign_d2 | O5InvariantViolation | d2_out_of_range, 永続化済み D2 が bigint の値域外 | 62 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の ordering.py:51)
ordering.py | _assign_d2 | O5InvariantViolation | d2_no_gap, D2 の局所再採番に必要な隙間がない | 110 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の ordering.py:97)
port_guard.py | _module_file | PortRegistrationError | f'ポート実装のソースがない: {module_name}' | 249 | 2 定義・登録の検査 | -
port_guard.py | _module_file | PortRegistrationError | f'ポート実装のソースを解決できない: {module_name}' | 256 | 2 定義・登録の検査 | -
port_guard.py | _module_file | PortRegistrationError | f'ポート実装の Python ソースがない: {module_name}' | 260 | 2 定義・登録の検査 | -
port_guard.py | _module_file | PortRegistrationError | f'ポート実装のソースがない: {module_name}' | 263 | 2 定義・登録の検査 | -
port_guard.py | _validate_standard_symbols | PortRegistrationError | f'禁止された標準ライブラリ名: {module_name}: {base}.{node.attr}' | 296 | 2 定義・登録の検査 | -
port_guard.py | _validate_standard_symbols | PortRegistrationError | f'禁止された getattr: {module_name}' | 313 | 2 定義・登録の検査 | -
port_guard.py | _validate_standard_symbols | PortRegistrationError | f'getattr の別名化は禁止: {module_name}' | 317 | 2 定義・登録の検査 | -
port_guard.py | _validate_standard_symbols | PortRegistrationError | f'標準モジュールの受け渡しは禁止: {module_name}: {node.id}' | 331 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'禁止名を参照するポート実装: {module_name}: {node.id}' | 347 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'禁止属性を参照するポート実装: {module_name}: {node.attr}' | 357 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'Pitchlog モジュールのオブジェクト import は禁止: {alias.name}' | 363 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'相対 import を解決できない: {module_name}' | 379 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | Pitchlog のルートからの import は禁止 | 385 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'Pitchlog モジュールのオブジェクト import は禁止: {base}.{alias.name}' | 392 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'Pitchlog の非モジュール名と確認できないため import 禁止: {base}.{alias.name}' | 397 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'禁止 import 属性を含むポート実装: {module_name}' | 402 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'禁止された標準ライブラリ名: {base}.{alias.name}' | 408 | 2 定義・登録の検査 | -
port_guard.py | _imported_modules | PortRegistrationError | f'書き手の発行情報を参照するポート実装: {module_name}' | 420 | 2 定義・登録の検査 | -
port_guard.py | _validate_source | PortRegistrationError | f'禁止 import を含むポート実装: {target}' | 437 | 2 定義・登録の検査 | -
port_guard.py | _validate_source | PortRegistrationError | f'ソースのない import: {target}' | 440 | 2 定義・登録の検査 | -
port_guard.py | _validate_source | PortRegistrationError | f'禁止 import を含むポート実装: {target}' | 442 | 2 定義・登録の検査 | -
port_guard.py | validate_port_source | PortRegistrationError | ポート実装の構文を検査できない | 451 | 2 定義・登録の検査 | -
port_guard.py | validate_port_modules | PortRegistrationError | f'ポート実装のソースを検査できない: {module_name}' | 472 | 2 定義・登録の検査 | -
port_guard.py | require_registered_port | PortRegistrationError | f'登録モジュールが読み込まれていない: {module_name}' | 490 | 2 定義・登録の検査 | -
port_guard.py | require_registered_port | PortRegistrationError | f'未登録のポート実装: {type(port).__name__}' | 496 | 2 定義・登録の検査 | -
ports.py | PortWriter.__init__ | PermissionError | PortWriter は適用核だけが発行できる | 41 | 2 定義・登録の検査 | -
ports.py | PortWriter.run | RuntimeError | PortWriter のトランザクションは閉じている | 48 | 2 定義・登録の検査 | -
ports.py | PortWriter.run | TypeError | PortWriter は operation token だけを受け付ける | 50 | 2 定義・登録の検査 | -
ports.py | require_registered_port | PortRegistrationError | ポート登録検査器が未接続 | 142 | 2 定義・登録の検査 | -
prefix_path.py | _cell | RuntimeError | 同期表の読み取り列数が正本と異なる | 173 | 2 定義・登録の検査 | -
prefix_path.py | _one_row | RuntimeError | f'{table} の対象行が一件ではない' | 180 | 8 B7 | -
prefix_path.py | _json_object | P1PreconditionError | P1 の V7 は JSON object が必要 | 187 | 7 既に境界結果(B3a) | -
prefix_path.py | _replacement_state | P1PreconditionError | V9 の置換種別と拒否原本 D5 が不正 | 208 | 7 既に境界結果(B3a) | -
prefix_path.py | _replacement_state | P1PreconditionError | V9 の置換種別が不正 | 211 | 7 既に境界結果(B3a) | -
prefix_path.py | _replacement_state | P1PreconditionError | V9 の拒否原本 D5 が不正 | 216 | 7 既に境界結果(B3a) | -
prefix_path.py | _replacement_state | P1PreconditionError | V9 の拒否原本 D5 が不正 | 222 | 7 既に境界結果(B3a) | -
prefix_path.py | _event_kind | P1PreconditionError | P1 の V5 は D1 付きイベント種別が必要 | 233 | 7 既に境界結果(B3a) | -
prefix_path.py | _replacement_target | P1PreconditionError | 墓標・改訂には V10 の対象参照が必要, w2_violation | 241 | 7 既に境界結果(B3a) | -
prefix_path.py | _replacement_target | P1PreconditionError | V10 が置換する D1 と一致しない, w2_violation | 250 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | 対応する内容拒否の D5 がない, w2_violation | 264 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | 対応する内容拒否原本がない, w2_violation | 267 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | 内容拒否原本の D1 が置換対象と一致しない, w2_violation | 278 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | V10 が内容拒否原本と一致しない, w2_violation | 286 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | 改訂版は拒否原本の参加区分を継承する, w2_violation | 288 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | 改訂版は拒否原本の D2 を継承する, w2_violation | 293 | 7 既に境界結果(B3a) | -
prefix_path.py | _require_rejected_original | P1PreconditionError | 内容拒否原本と D5 台帳の指紋が一致しない, w2_violation | 299 | 7 既に境界結果(B3a) | -
prefix_path.py | _d2 | P1PreconditionError | 墓標は D2 を持たない | 308 | 7 既に境界結果(B3a) | -
prefix_path.py | _d2 | P1PreconditionError | このイベント種別には D2 が必要 | 314 | 7 既に境界結果(B3a) | -
prefix_path.py | _d2 | P1PreconditionError | このイベント種別は D2 を持たない | 316 | 7 既に境界結果(B3a) | -
prefix_path.py | _d2 | P1PreconditionError | P1 の D2 が不正 | 320 | 7 既に境界結果(B3a) | -
prefix_path.py | _state_diff | P1PreconditionError | 墓標は V8 を持たない | 328 | 7 既に境界結果(B3a) | -
prefix_path.py | _state_diff | P1PreconditionError | このイベント種別には V8 の状態差分が必要 | 334 | 7 既に境界結果(B3a) | -
prefix_path.py | _state_diff | P1PreconditionError | このイベント種別は V8 の状態差分を持たない | 336 | 7 既に境界結果(B3a) | -
prefix_path.py | _validate_v11 | RuntimeError | P1 の V11 種別条件が未対応 | 348 | 2 定義・登録の検査 | -
prefix_path.py | _validate_v11 | P1PreconditionError | P1 のイベント種別は V11 を持たない | 350 | 7 既に境界結果(B3a) | -
prefix_path.py | _validate_v10 | P1PreconditionError | 墓標・改訂には undo の対象を指定できない | 359 | 7 既に境界結果(B3a) | -
prefix_path.py | _validate_v10 | P1PreconditionError | このイベント種別は V10 の対象を持たない | 364 | 7 既に境界結果(B3a) | -
prefix_path.py | _validate_v10 | P1PreconditionError | undo の V10 と照合済み対象が一致しない | 377 | 7 既に境界結果(B3a) | -
prefix_path.py | _stored_result | RuntimeError | P1 の保存済み結果が受理ではない | 411 | 2 定義・登録の検査 | -
prefix_path.py | _stored_result | RuntimeError | P1 の保存済み結果の形が不正 | 421 | 8 再掲の破損 | -
prefix_path.py | _stored_result | RuntimeError | P1 の保存済み写像の形が不正 | 425 | 8 再掲の破損 | -
prefix_path.py | _resolve_player_reference | P1ContentRejection | 選手参照は UUID 文字列が必要 | 447 | 8 B3a | -
prefix_path.py | _resolve_player_reference | P1ContentRejection | 選手参照は UUID 文字列が必要 | 451 | 8 B3a | -
prefix_path.py | _resolve_player_reference | P1ContentRejection | 選手参照は正規 UUID が必要 | 453 | 8 B3a | -
prefix_path.py | _resolve_player_reference | O5InvariantViolation | player_mapping_type, 正式選手 ID の型が不正 | 462 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の prefix_path.py:459)
prefix_path.py | _resolve_player_reference | P1PreconditionError | 一時選手 ID の確定写像がない | 475 | 8 B7(状態依存) | -
prefix_path.py | _resolve_payload | P1ContentRejection | V5 で定義されない選手参照位置 | 501 | 8 B3a | -
prefix_path.py | _call_port | RuntimeError | ポートが O5 の型を送出した | 545 | 8 B7 | ステップ 8 の是正: ポートの例外は O5 に寄せない(design 12-2)
prefix_path.py | _apply_locked | RuntimeError | 認可後に試合行が消失した | 554 | 8 B7 | -
prefix_path.py | _apply_locked | P1PreconditionError | D1 付き経路には D1 と D4 が必要 | 597 | 2 定義・登録の検査 | -
prefix_path.py | _apply_locked | P1PreconditionError | P1 の記録権不一致は退避経路へ渡す, recording_rights | 606 | 7 既に境界結果(B4) | -
prefix_path.py | _apply_locked | P1PreconditionError | 確定済み D1 は墓標・改訂で置換できない, 'w2_violation' if event.v9 is not ABSENT else 'other' | 612 | 8 確定スロットの食い違い | -
prefix_path.py | _apply_locked | P1PreconditionError | P2 は論理位置を持つイベント種別だけを受ける | 622 | 7 既に境界結果(B3a) | -
prefix_path.py | _apply_locked | P1PreconditionError | P2 には論理位置 V6 が必要 | 626 | 7 既に境界結果(B3a) | -
prefix_path.py | _apply_locked | P1PreconditionError | 墓標の payload は空 object が必要 | 632 | 7 既に境界結果(B3a) | -
prefix_path.py | _apply_locked | P1PreconditionError | その場登録には選手作成値が必要 | 634 | 7 既に境界結果(B3a) | -
prefix_path.py | _apply_locked | P1PreconditionError | 選手作成値はその場登録だけに使える | 636 | 7 既に境界結果(B3a) | -
prefix_path.py | _apply_locked | P1PreconditionError | その場登録の V7 に一時選手 ID がない | 640 | 7 既に境界結果(B3a) | -
prefix_path.py | _apply_locked | P1ContentRejection | str(error) | 643 | 5 内部制御 | -
prefix_path.py | _apply_locked | (再送出) |  | 644 | 5 内部制御 | -
prefix_path.py | _apply_locked | P1ContentRejection | reason or 'P1 の内容拒否は T9 へ渡す' | 649 | 5 内部制御 | -
prefix_path.py | _apply_locked | O5InvariantViolation | d1_multiple_current_rows, D1 に複数の現行行がある | 656 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の prefix_path.py:651)
prefix_path.py | _apply_locked | O5InvariantViolation | event_without_slot, 現行イベントのスロットがない | 660 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の prefix_path.py:653)
prefix_path.py | _apply_locked | P1PreconditionError | 確定済みイベントは墓標・改訂で置換できない, 'w2_violation' if original_d5 is not None else 'other' | 664 | 8 確定スロットの食い違い | -
prefix_path.py | _apply_locked | _NoWriteStop | P1Result('B3', d3, False, a5='拒否', reason='O4: 永続化済み D2 の同値', b3_code='O4') | 673 | 6 O4 | -
prefix_path.py | _apply_locked | P1PreconditionError | 一時 ID は別の確定写像に使用済み | 694 | 8 B7(状態依存) | -
prefix_path.py | _apply_locked | RuntimeError | D5 再照合が未使用に戻った | 724 | 8 B7 | -
prefix_path.py | _apply_locked | _D5Race | outcome | 725 | 5 内部制御 | -
prefix_path.py | _apply_locked | O5InvariantViolation | d3_advance_failed, D3 の前進に失敗 | 743 | 8 O5 | ステップ 8 で O5 の型へ(11-4 の prefix_path.py:729)
prefix_path.py | _original_fingerprint | P1PreconditionError | T9 原本の指紋が不正, w2_violation | 872 | 7 既に境界結果(B3a) | -
prefix_path.py | _replay_saved_result | RuntimeError | P1 の保存済み結果がない | 880 | 2 定義・登録の検査 | -
prefix_path.py | _lock_game_generation | RuntimeError | 記録権世代の型が不正 | 907 | 8 再照合前 | -
prefix_path.py | _lock_game_generation | RuntimeError | D3 の型が不正 | 914 | 8 再照合前 | -
rejection.py | content_reason_for_precondition | ValueError | 内容拒否以外を T9 に記録できない | 75 | 2 定義・登録の検査 | -
rejection.py | _candidate_result | RuntimeError | 拒否・退避以外の保存済み結果は元の適用経路で再掲する | 87 | 2 定義・登録の検査 | -
rejection.py | _commit_result | RuntimeError | D5 再照合が未使用に戻った | 134 | 8 B7 | -
rejection.py | _commit_result | _RaceReplay | result | 135 | 5 内部制御 | -
rejection.py | _commit_result | RuntimeError | 退避原本の世代または D1 がない | 146 | 2 定義・登録の検査 | -
rejection.py | _apply_locked | RuntimeError | 認可後に試合行が消失した | 175 | 8 B7 | -
rejection.py | _apply_locked | P1PreconditionError | D1 付き経路には D1 と D4 が必要 | 184 | 2 定義・登録の検査 | -
rejection.py | _apply_locked | P1PreconditionError | 退避する旧 D4 の世代番号が不正 | 193 | 8 U-R1 待ち | -
rejection.py | _apply_locked | P1PreconditionError | 退避する旧 D4 の世代番号が不正 | 195 | 8 U-R1 待ち | -
rejection.py | _apply_locked | P1PreconditionError | 記録権が成立するイベントは内容拒否の理由が必要 | 206 | 8 B7 | -
rejection.py | _apply_locked | P1PreconditionError | 確定済み D1 は内容拒否原本にできない | 210 | 8 B7 | -
rejection.py | _apply_locked | P1PreconditionError | 内容拒否の理由が空 | 212 | 2 定義・登録の検査 | -
rejection.py | apply_rejection_or_escrow | ValueError | P4 はその場登録を持たない | 245 | 2 定義・登録の検査 | -
tokens.py | InvalidationIntentPendingToken.__post_init__ | ValueError | 意図 ID のカーソルは文字列が必要 | 247 | 1 適用外 | -
tokens.py | SyncInvalidationIntentInsertToken.validate | ValueError | 試合範囲には試合 ID が必要 | 268 | 2 定義・登録の検査 | -
tokens.py | SyncInvalidationIntentInsertToken.validate | ValueError | 広域範囲に試合 ID を指定できない | 271 | 2 定義・登録の検査 | -
tokens.py | SyncInvalidationIntentInsertToken.validate | ValueError | 共有集計には専用 token が必要 | 273 | 2 定義・登録の検査 | -
"""  # noqa: E501


def _parse(table: str) -> tuple[RaiseRow, ...]:
    """表の文字列を行へ分解し、列数と区分の値域を検査する。"""
    rows: list[RaiseRow] = []
    for raw in table.strip().splitlines():
        columns = raw.split(" | ")
        if len(columns) != 7:
            raise ValueError(f"棚卸しの列数が 7 でない: {raw}")
        file, function, exception, message, line, category, note = columns
        if category not in RAISE_CATEGORIES:
            raise ValueError(f"未知の区分: {raw}")
        rows.append(
            RaiseRow(
                file,
                function,
                exception,
                message,
                int(line),
                cast(RaiseCategory, category),
                "" if note == "-" else note,
            )
        )
    return tuple(rows)


SYNC_RAISE_INVENTORY: Final[tuple[RaiseRow, ...]] = _parse(_TABLE)


def _render(node: ast.Raise) -> tuple[str, str]:
    """``raise`` 文の例外型と文言を棚卸しの規則で文字列にする。"""
    exc = node.exc
    if exc is None:
        return "(再送出)", ""
    if not isinstance(exc, ast.Call):
        return ast.unparse(exc), ""
    parts = [
        arg.value
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        else ast.unparse(arg)
        for arg in exc.args
    ]
    parts.extend(
        f"{keyword.arg}={ast.unparse(keyword.value)}" for keyword in exc.keywords
    )
    return ast.unparse(exc.func), ", ".join(parts)


class _RaiseCollector(ast.NodeVisitor):
    """関数・クラスの入れ子を保ちながら ``raise`` 文を出現順に集める。"""

    def __init__(self, file: str) -> None:
        """対象ファイル名と空の結果を持つ。"""
        self.file = file
        self.stack: list[str] = []
        self.rows: list[tuple[str, str, str, str, int]] = []

    def _enter(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """名前を積んで中を走査する。"""
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """クラスの中を走査する。"""
        self._enter(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """関数の中を走査する。"""
        self._enter(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数の中を走査する。"""
        self._enter(node)

    def visit_Raise(self, node: ast.Raise) -> None:  # noqa: N802
        """``raise`` 文を一行として記録する。"""
        exception, message = _render(node)
        function = ".".join(self.stack) or "<module>"
        self.rows.append((self.file, function, exception, message, node.lineno))
        self.generic_visit(node)


def _ast_raises() -> list[tuple[str, str, str, str, int]]:
    """``sync/*.py`` の ``raise`` 文をファイル順・出現順に返す。"""
    rows: list[tuple[str, str, str, str, int]] = []
    for path in sorted(_SYNC_ROOT.glob("*.py")):
        collector = _RaiseCollector(path.name)
        collector.visit(ast.parse(path.read_text(encoding="utf-8")))
        rows.extend(collector.rows)
    return rows


def _keyed(rows: list[tuple[str, str, str, str]]) -> Counter[_Key]:
    """(ファイル・関数・例外型・文言)に出現順を付けたキーを数える。"""
    return Counter(
        (*row, index)
        for row, index in zip(rows, _occurrence_indexes(rows), strict=True)
    )


def _occurrence_indexes(rows: list[tuple[str, str, str, str]]) -> list[int]:
    """同じキーの行に 1 から始まる出現順を振る。"""
    seen: Counter[tuple[str, str, str, str]] = Counter()
    indexes: list[int] = []
    for row in rows:
        seen[row] += 1
        indexes.append(seen[row])
    return indexes


def _inventory_key(row: RaiseRow) -> tuple[str, str, str, str]:
    """棚卸しの行から照合のキーを取り出す(行番号は使わない)。"""
    return row.file, row.function, row.exception, row.message


def test_o5_codes_equal_literal_members() -> None:
    """列挙の定数と型の値域が同じ 7 件である。"""
    assert O5_CODES == frozenset(get_args(invariants.O5Code.__value__))
    assert len(O5_CODES) == 7


def test_o5_violation_is_not_precondition_subtype() -> None:
    """区分付き前提違反の捕捉(T9・再送出)に吸われない型である。"""
    from pitchlog.sync.prefix_path import P1PreconditionError

    assert issubclass(O5InvariantViolation, RuntimeError)
    assert not issubclass(O5InvariantViolation, P1PreconditionError)


def _o5_raise_codes() -> tuple[Counter[str], list[str]]:
    """製品コード全体の ``O5InvariantViolation`` の生成箇所を集める。

    Returns:
        ``raise O5InvariantViolation("<code>", ...)`` の code の出現数と、
        その形でない生成箇所(列挙を迂回する経路)の一覧。
    """
    codes: Counter[str] = Counter()
    irregular: list[str] = []
    for path in sorted(_PITCHLOG_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        raised_calls: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                call = node.exc
                if ast.unparse(call.func).endswith("O5InvariantViolation"):
                    raised_calls.add(id(call))
                    first = call.args[0] if call.args else None
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        codes[first.value] += 1
                    else:
                        irregular.append(f"{path.name}:{node.lineno}")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and ast.unparse(node.func).endswith("O5InvariantViolation")
                and id(node) not in raised_calls
            ):
                irregular.append(f"{path.name}:{node.lineno}")
    return codes, irregular


def test_o5_codes_match_raise_sites() -> None:
    """``O5_CODES`` と送出箇所の code が過不足なく一対一に対応する。"""
    codes, irregular = _o5_raise_codes()
    missing = sorted(O5_CODES - set(codes))
    unknown = sorted(set(codes) - O5_CODES)
    duplicated = sorted(code for code, count in codes.items() if count > 1)
    assert missing == []
    assert unknown == []
    assert duplicated == []
    assert irregular == []


def test_sync_raises_match_inventory_one_to_one() -> None:
    """``sync/*.py`` の ``raise`` と棚卸しが欠落 0・余分 0 で一致する。"""
    actual_rows = _ast_raises()
    actual = _keyed([row[:4] for row in actual_rows])
    expected = _keyed([_inventory_key(row) for row in SYNC_RAISE_INVENTORY])
    lines = {
        (*row[:4], index): row[4]
        for row, index in zip(
            actual_rows,
            _occurrence_indexes([row[:4] for row in actual_rows]),
            strict=True,
        )
    }
    missing_from_inventory = sorted(
        f"{key[0]}:{lines[key]} {key[1]} {key[2]}({key[3]})"
        for key in actual - expected
    )
    missing_from_code = sorted(
        f"{key[0]} {key[1]} {key[2]}({key[3]}) #{key[4]}" for key in expected - actual
    )
    assert missing_from_inventory == []
    assert missing_from_code == []
    assert len(SYNC_RAISE_INVENTORY) == len(actual_rows)


def test_inventory_o5_category_is_exactly_o5_type() -> None:
    """区分「8 O5」の行と ``O5InvariantViolation`` の送出行が同じ 7 行である。"""
    o5_category = {
        _inventory_key(row) for row in SYNC_RAISE_INVENTORY if row.category == "8 O5"
    }
    o5_type = {
        _inventory_key(row)
        for row in SYNC_RAISE_INVENTORY
        if row.exception == "O5InvariantViolation"
    }
    assert o5_category == o5_type
    assert len(o5_category) == len(O5_CODES)
    assert {row[3].split(", ", 1)[0] for row in o5_category} == O5_CODES
