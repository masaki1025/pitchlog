"""常駐 Node の JSON 境界・コード生成拒否・プロセス上限を固定する。"""

from __future__ import annotations

import json
import resource
import select
import subprocess

import pytest

from conftest import NODE, NodeHost

pytestmark = pytest.mark.skipif(NODE is None, reason="node が見つからない")


def test_persistent_node_reads_same_artifact_over_ndjson(
    node_host: NodeHost, cases: tuple[tuple[bytes, bytes], ...]
) -> None:
    process_id = node_host.process.pid
    for request, expected in cases:
        assert node_host.request(request) == expected
        assert node_host.process.pid == process_id
        assert node_host.process.poll() is None


def test_vm_options_reject_eval_function_and_dynamic_import() -> None:
    assert NODE is not None
    probe = """
import vm from 'node:vm';
const context = vm.createContext(Object.create(null), {
  codeGeneration: { strings: false, wasm: false },
});
const expressions = [
  'eval("2")',
  'new Function("return 2")()',
  'Function.prototype.constructor("return 2")()',
  'import("data:text/javascript,export default 2")',
];
const observed = [];
for (const expression of expressions) {
  try {
    observed.push(await vm.runInContext(expression, context));
  } catch (error) {
    observed.push(error.code ?? error.name);
  }
}
console.log(JSON.stringify(observed));
"""
    result = subprocess.run(
        [NODE, "--disallow-code-generation-from-strings", "--input-type=module", "-e", probe],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert json.loads(result.stdout) == [
        "EvalError",
        "EvalError",
        "EvalError",
        "ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING",
    ]


def test_node_flag_alone_does_not_restrict_vm_context() -> None:
    assert NODE is not None
    probe = (
        "const vm=require('node:vm');"
        "const context=vm.createContext(Object.create(null));"
        "console.log(vm.runInContext('new Function(\"return 2\")()',context));"
    )
    result = subprocess.run(
        [NODE, "--disallow-code-generation-from-strings", "-e", probe],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.stdout.strip() == "2"


def test_process_timeout_stops_unbounded_guest() -> None:
    assert NODE is not None
    process = subprocess.Popen(
        [NODE, "-e", 'console.log("started"); while (true) {}'], stdout=subprocess.PIPE
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 3)
        assert ready
        assert process.stdout.readline() == b"started\n"
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.2)
    finally:
        process.kill()
        process.wait(timeout=3)
        if process.stdout is not None:
            process.stdout.close()
    assert process.poll() is not None


def test_vm_timeout_rejects_unbounded_guest() -> None:
    assert NODE is not None
    probe = (
        "const vm=require('node:vm');"
        "try { vm.runInNewContext('while (true) {}', {}, {timeout: 20}); }"
        "catch(error) { console.log(error.code); }"
    )
    result = subprocess.run(
        [NODE, "-e", probe], check=True, capture_output=True, text=True, timeout=5
    )
    assert result.stdout.strip() == "ERR_SCRIPT_EXECUTION_TIMEOUT"


def _disable_core_dump() -> None:
    """OOM 試験の Node が core ファイルを残さないようにする。"""
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def test_heap_limit_stops_excessive_allocation() -> None:
    assert NODE is not None
    result = subprocess.run(
        [
            NODE,
            "--max-old-space-size=16",
            "-e",
            'const rows=[]; while (true) rows.push(new Array(100000).fill("x"));',
        ],
        capture_output=True,
        timeout=10,
        preexec_fn=_disable_core_dump,
    )
    assert result.returncode != 0
    assert b"heap out of memory" in result.stderr
