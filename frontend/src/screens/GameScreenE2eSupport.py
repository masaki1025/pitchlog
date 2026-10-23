"""E2Eのoriginを依存読込み前に確認し、製品DB起動へ渡す。"""

from __future__ import annotations

import os
import re
import runpy
from pathlib import Path


def validated_browser_mode_origin() -> tuple[str, str]:
    """専用loopbackの明示モードとoriginだけを受理する。

    Returns:
        検証済みのモードとorigin。
    """
    origin = os.environ["PITCHLOG_E2E_FRONTEND_ORIGIN"]
    mode = os.environ.get("PITCHLOG_E2E_MODE", "sealed-ui")
    if mode not in {"sealed-ui", "preparing-read"}:
        raise AssertionError("E2Eの明示モードが不正")
    scheme = "http" if mode == "preparing-read" else "https"
    match = re.fullmatch(rf"{scheme}://127\.0\.0\.1:([1-9][0-9]{{0,4}})", origin)
    if match is None or int(match.group(1)) > 65535:
        raise AssertionError("E2E origin は明示モードの専用loopbackポートだけ許す")
    return mode, origin


def main() -> None:
    """標準ライブラリだけで拒否した後、同じprocessで実serverを起動する。"""
    validated_browser_mode_origin()
    runpy.run_path(
        str(Path(__file__).with_name("GameScreenE2eServer.py")),
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
