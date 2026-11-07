"""真正P3元本文の未送信/故障/ACK喪失復旧。標準controlのみを使用する。"""

from __future__ import annotations

import pytest

from . import test_p3_candidate_compile_author as p3
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


def _recovery_script(original: str) -> str:
    """既実縦断の成否期待を維持して、同原文の権威照会だけを挿入する。"""

    def once(before: str, after: str) -> None:
        nonlocal original
        assert original.count(before) == 1, before
        original = original.replace(before, after, 1)

    once(
        "        negative_d5s = []",
        """        async def recover_original(original_headers):
            recovered = await client.post(
                "/games/" + game + "/sync/attempts/recover",
                headers=original_headers, json=p3_payload)
            assert recovered.status_code == 200, ("p3-recover", recovered.status_code)
            assert recovered.json() == {"resolution": "retry_allowed"}
            altered = json.loads(json.dumps(p3_payload))
            altered["recording_right_proof"] = "other-original-V12"
            refused = await client.post(
                "/games/" + game + "/sync/attempts/recover",
                headers=original_headers, json=altered)
            assert refused.status_code == 200, ("p3-recover-V12", refused.status_code)
            assert refused.json() == {"resolution": "unresolved"}

        # 未登録をrow0だけで成功としない。実fence/旧publisher遮断後だけ成立する。
        unsent_headers = device_headers(pair, str(uuid4()))
        await recover_original(unsent_headers)
        late = await client.post("/games/" + game + "/sync/change",
                                 headers=unsent_headers, json=p3_payload)
        assert late.status_code == 503, ("p3-unsent-late", late.status_code)
        negative_d5s = []""",
    )
    once(
        "            failed = None\n            try:",
        "            failed = None\n"
        "            failed_headers = device_headers(pair, str(uuid4()))\n"
        "            try:",
    )
    once(
        "                        headers=device_headers(pair, str(uuid4())),\n"
        "                        json=p3_payload)",
        "                        headers=failed_headers,\n"
        "                        json=p3_payload)",
    )
    once(
        "        p3_headers = device_headers(pair, str(uuid4()))",
        "            await recover_original(failed_headers)\n"
        "        p3_headers = device_headers(pair, str(uuid4()))",
    )
    once(
        '        runtime_diagnostics.update(stage="p3-get", status=None)',
        """        # 実受理後のACK喪失を権威照会し、新attemptの同D5で再掲する。
        await recover_original(p3_headers)
        recovered_replay = await client.post(
            "/games/" + game + "/sync/change",
            headers=device_headers(pair, str(uuid4())), json=p3_payload)
        assert recovered_replay.status_code == 200
        assert recovered_replay.json() == changed.json()
        runtime_diagnostics.update(stage="p3-get", status=None)""",
    )
    return original


def test_p3_original_body_recovery_uses_standard_control(
    vertical_database, monkeypatch
):
    """実login/記録権/正式P3計算/TXと標準controlの原本再送を接続する。"""
    original = p3._three_ball_p3_script()
    candidate = _recovery_script(original)
    monkeypatch.setattr(p3, "_three_ball_p3_script", lambda: candidate)
    p3.test_owned_candidate_actual_http_p3(vertical_database)
