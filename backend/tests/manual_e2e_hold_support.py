"""owned E2E環境の任意手動待機だけを提供する。DBやTLS資材を操作しない。"""

import json
import os
import re
import time


def manual_hold_seconds() -> int:
    """明示した有限の手動確認時間だけを受け付ける。既定は待機しない。"""
    raw = os.environ.get("PITCHLOG_E2E_MANUAL_HOLD_SECONDS", "0")
    if raw == "0":
        return 0
    if re.fullmatch(r"[1-9][0-9]{0,3}", raw) is None or int(raw) > 3600:
        raise ValueError("手動確認の待機秒数は0または1..3600の整数が必要")
    return int(raw)


def hold_manual_environment(
    origin: str, seconds: int, team_name: str | None = None
) -> None:
    """全検査後のowned環境だけを有限時間保ち、割込を既finallyへ伝える。"""
    if seconds == 0:
        return
    if type(seconds) is not int or not 1 <= seconds <= 3600:
        raise ValueError("手動確認の待機秒数が不正")
    if re.fullmatch(r"https://127\.0\.0\.1:[1-9][0-9]{0,4}", origin) is None:
        raise ValueError("手動確認の接続先はowned HTTPS loopbackだけが必要")
    if team_name is not None and (type(team_name) is not str or not team_name):
        raise ValueError("手動確認のfixtureチーム名が不正")
    print(f"PITCHLOG_E2E_MANUAL_ORIGIN={origin}", flush=True)
    if team_name is not None:
        print(
            "PITCHLOG_E2E_MANUAL_TEAM_NAME="
            + json.dumps(team_name, ensure_ascii=False),
            flush=True,
        )
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(1.0, remaining))
