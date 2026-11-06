"""native原本の値をコピーし、唯一の生成T5核へ有限射影する。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

_GENERATED_FACTS_SHA256 = (
    "a7ca0116a1bcb53af2cfe77f9535af08da635a53b1bbe0b06bf7bd241bb31ce6"
)


def _generated_module():
    """配置済み共通生成物だけをwrapper名で読み込む。"""
    path = Path(__file__).parent / "generated/facts.py"
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("T5生成物を読み込めません") from exc
    if (
        type(source) is not bytes
        or hashlib.sha256(source).hexdigest() != _GENERATED_FACTS_SHA256
    ):
        raise RuntimeError("T5生成物の固定SHA256が一致しません")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("T5生成物がUTF-8ではありません") from exc
    module = ModuleType("__pitchlog_generated_wrapper__")
    exec(compile(text, str(path), "exec"), module.__dict__)
    if module.__dict__["SOURCE_MODEL_HASH"] != SOURCE_MODEL_HASH:
        raise RuntimeError("T5/typed receiverのモデル版が一致しません")
    return module.__dict__


def _generated_api():
    """旧native入口は同じ検証済みmoduleの確定計算だけを返す。"""
    return _generated_module()["_pitchlog_generated"]


_EVENT_FACTS = _generated_api()


def derive_rates(metrics):
    """同じ生成核のOPS表示率を返す。率の式をこのmoduleへ複製しない。"""
    return _generated_module()["derive_rates"](metrics)


def derive_rates_with_components(metrics):
    """T5の同一評価でOPSと独立状態付きcomponentを返す。"""
    return _generated_module()["derive_rates_with_components"](metrics)


def native_projection(payload, *, source_event_id):
    """保存原本から既観測だけを写す。戻り値は保存資格/receiptではない。

    Args:
        payload: rootの真正frame/ledger照合を通す対象のV7原本辞書。
        source_event_id: 同TX受理ledgerが供給するevent識別子。

    Returns:
        共通modelの入力射影。欠測fieldを仮値で補完しない。

    Raises:
        ValueError: native variant/閉sourceの外である場合。
    """
    if type(payload) is not dict or type(source_event_id) is not UUID:
        raise ValueError("native sourceの閉入力が必要です")
    variant = payload["formatVersion"]
    if variant not in (
        "first-ball-play-v1",
        "ordinary-pitch-play-v1",
        "play-prefix-play-v2",
        "play-prefix-play-v3",
    ):
        raise ValueError("未対応native sourceです")
    calc = payload["calculation"]
    if calc["response"]["ok"] is not True:
        raise ValueError("native数学の非成功はT5入力になりません")
    value = calc["response"]["value"]
    t1 = value["t1"]
    request_kind = calc["request"]["t1"]["pitchEventKind"]
    if request_kind not in ("pitch-event", "non-pitch-event"):
        raise ValueError("native event区分が未対応です")
    event_kind = {"pitch-event": "pitch", "non-pitch-event": "non_pitch"}[request_kind]
    before = calc["request"]["t1"]["before"]["stateFields"]
    people = payload["participants"]
    # v3のbefore側を使用する。次打者/交代後守備者を今回のcreditに使わない。
    if variant == "play-prefix-play-v3" and value["beforeParticipants"] != people:
        raise ValueError("before参加者の原本が不一致です")
    participants = {
        "actual_pitcher_id": people["pitcherId"],
        "actual_batter_id": people["batterId"],
        "credited_batter_id": people["batterId"],
    }
    pa = {"ended_here": t1["plateAppearanceEnded"]}
    completeness = {
        "participants": "complete",
        "pa": "unavailable",
        "outs": "complete",
        "runs_rbi": "unavailable",
        "steals": "unavailable",
    }
    # 明示された未完PAは欠測ではない。count射影には終了済PAのID/表示を要求しない。
    # PA行生成はこの入口で無効であり、欠測IDやordinalを補うこともない。
    if t1["plateAppearanceEnded"] is False:
        completeness["pa"] = "complete"
    if variant in ("play-prefix-play-v2", "play-prefix-play-v3"):
        native_source = calc["request"]["source"]
        responsibility = native_source["responsibility"]
        if responsibility["kind"] != "no-change":
            raise ValueError("native継承責任variantは本接合の対象外です")
        if (
            variant == "play-prefix-play-v3"
            and value["responsibility"] != responsibility
        ):
            raise ValueError("今回責任の原本が不一致です")
        pa["pa_id"] = responsibility["paStartSource"]["id"]
        completeness["pa"] = "complete"
        # 対応variantの明示no-change原本だけをaliasする。A-2再判定はしない。
        for name in (
            "strikeout_pitcher_id",
            "walk_pitcher_id",
            "hbp_pitcher_id",
            "hit_pitcher_id",
            "home_run_pitcher_id",
            "outs_pitcher_id",
        ):
            participants[name] = people["pitcherId"]
    return {
        "event_kind": event_kind,
        "source": {"lifecycle": "effective", "source_event_id": str(source_event_id)},
        "before": {"inning": before["state.inning"], "half": before["state.half"]},
        "stat_flags": t1["statFlags"],
        "out_effect": {"effective_count": t1["outEffect"]["count"]},
        "pa": pa,
        "participants": participants,
        "completeness": completeness,
    }


def evaluate_native_projection(payload, *, source_event_id):
    """全26群を同じ生成核で評価する。認可/保存成功は発行しない。"""
    projection = native_projection(payload, source_event_id=source_event_id)
    # PA表示のordinal/語彙等を仮生成せず、count/creditだけを有限射影する。
    return _EVENT_FACTS(projection, METRIC_IDS)


def evaluate_closed_projection(projection, *, requested_metrics):
    """正式providerが閉じた他variantも同じ生成入口へ渡す。"""
    return _EVENT_FACTS(projection, requested_metrics)


@dataclass(frozen=True, slots=True)
class SavePrimitiveSourceToken(TenantOperationToken):
    """rootの実同TX frame資格と評価bindingを要する保存命令。"""

    attempt_id: UUID
    phase_id: UUID
    source_event_id: UUID
    model_sha256: str
    expected_revision: int
    expected_source_set_sha256: str | None
    evaluation_json: str

    @property
    def capability_id(self):
        """呼出者のboolを資格とせず固定能力を宣言する。"""
        return "CAP:stats_primitives:save_source"


def prepare_native_evaluation(
    payload,
    *,
    attempt_id,
    phase_id,
    source_event_id,
    expected_revision,
    expected_source_set_sha256,
):
    """同frame hookが渡す評価を閉tokenへ写す。token自身は保存権限ではない。

    rootのtransaction/登録関数が既消費frame/ledger/play/checkpointと評価を
    同TXで独立照合するまで、自由UUID/JSONは受理済みreceiptにならない。
    """
    if any(type(x) is not UUID for x in (attempt_id, phase_id, source_event_id)):
        raise ValueError("同frame識別子の型が不正です")
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("期待系列revisionの型が不正です")
    if expected_revision == 0:
        if expected_source_set_sha256 is not None:
            raise ValueError("初回系列の期待Sが不正です")
    elif (
        type(expected_source_set_sha256) is not str
        or re.fullmatch(r"[a-f0-9]{64}", expected_source_set_sha256) is None
    ):
        raise ValueError("期待系列Sの型が不正です")
    evaluation = evaluate_native_projection(payload, source_event_id=source_event_id)
    return SavePrimitiveSourceToken(
        attempt_id,
        phase_id,
        source_event_id,
        SOURCE_MODEL_HASH,
        expected_revision,
        expected_source_set_sha256,
        json.dumps(
            evaluation,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    )
