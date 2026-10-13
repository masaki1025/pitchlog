"""同一合成 artifact の QuickJS と常駐 Node の出力を照合する。"""

from __future__ import annotations

import pytest
from _runtime_support import ARTIFACT, NodeHost


def test_same_artifact_outputs_identical_bytes(
    node_host: NodeHost, cases: tuple[tuple[bytes, bytes], ...]
) -> None:
    quickjs = pytest.importorskip("quickjs")
    context = quickjs.Context()
    context.eval(ARTIFACT.read_text(encoding="utf-8"))
    for request, expected in cases:
        context.set("requestJson", request.decode("utf-8"))
        quickjs_bytes = context.eval("PitchlogSynthetic.run(requestJson)").encode("utf-8")
        node_bytes = node_host.request(request)
        assert quickjs_bytes == node_bytes == expected
