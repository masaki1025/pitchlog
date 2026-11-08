"""短P3観測は元呼出/戻値/例外を変えず、秘密本文を出さない。"""

import ast
import asyncio
import contextlib
import io
import json
from types import FunctionType, SimpleNamespace

import pytest
from db.test_p3_short_current_diagnostic import (
    _P3_FAILURE_PROBE,
    _instrument_http_stages,
    build_short_p3_script,
)


@pytest.mark.parametrize("alias", ["_apply_e1_p3", "_apply_e1_f1"])
@pytest.mark.parametrize("mode", ["return", "B10", "raise"])
@pytest.mark.parametrize("broken_output", [False, True])
def test_short_probe_preserves_real_call_contract(alias, mode, broken_output):
    """未知本文やprint失敗を元API成功/例外へ混入させない。"""
    calls = []
    result = object()
    error = RuntimeError("SECRET_SENTINEL")

    def original(*args, **kwargs):
        calls.append((args, kwargs))
        if mode == "raise":
            raise error
        return "B10" if mode == "B10" else result

    namespace = {
        "json": json,
        "actual_sync_router": SimpleNamespace(
            _apply_e1_p3=original, _apply_e1_f1=original
        ),
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(_P3_FAILURE_PROBE, namespace)

    class BrokenOutput(io.StringIO):
        def write(self, *args):
            raise RuntimeError("SECRET_OUTPUT")

    with contextlib.redirect_stdout(BrokenOutput() if broken_output else output):
        try:
            actual = getattr(namespace["actual_sync_router"], alias)("SECRET_ARGUMENT")
        except RuntimeError as caught:
            assert mode == "raise" and caught is error
        else:
            assert actual == "B10" if mode == "B10" else actual is result
    assert calls == [(("SECRET_ARGUMENT",), {})]
    assert "SECRET" not in output.getvalue()


def test_short_script_removes_old_diagnostics_and_all_candidate_installers():
    """旧操作の正規app経路は保持し、後付DDLや文脈診断を除去する。"""
    script = build_short_p3_script()
    compile(script, "<short-p3-pure>", "exec")
    uid = ast.dump(
        ast.parse("os.geteuid()==20003 and os.getegid()==20003", mode="eval").body
    )
    assert any(
        ast.dump(node.test) == uid
        for node in ast.walk(ast.parse(script))
        if isinstance(node, ast.Assert)
    )
    assert "http-01-logged-before" in script
    assert "http-01-logged-after" in script
    assert "short-p3-post" in script
    assert "test_owned_candidate_0048_compiles" not in script
    assert "candidate.sql" not in script
    assert "message_primary" not in script
    assert "message_detail" not in script
    assert "format_exc" not in script
    assert "traced_p3_snapshot" not in script


def test_probe_metadata_failure_keeps_original_error_and_caps_output():
    """metadata自身の失敗も元例外を維持し、ログは80件までに限定する。"""

    class MetadataError(RuntimeError):
        @property
        def sqlstate(self):
            raise RuntimeError("SECRET_METADATA")

    error = MetadataError("SECRET_ORIGINAL")

    def original():
        raise error

    namespace = {
        "json": json,
        "actual_sync_router": SimpleNamespace(
            _apply_e1_p3=original, _apply_e1_f1=original
        ),
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(_P3_FAILURE_PROBE, namespace)
        with pytest.raises(MetadataError) as caught:
            namespace["actual_sync_router"]._apply_e1_p3()
        assert caught.value is error
        emit = namespace["_p3_emit"]
        assert isinstance(emit, FunctionType)
        for _ in range(90):
            emit({"boundary": "router-e1-p3", "outcome": "rejected", "result": "B10"})
    lines = output.getvalue().splitlines()
    assert (
        len([line for line in lines if line.startswith("PITCHLOG_P3_SHORT_SAFE ")])
        == 80
    )
    assert "SECRET" not in output.getvalue()


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("metadata_failure", [False, True])
def test_http_stage_insertion_keeps_original_await_calls_and_errors(
    failure, metadata_failure
):
    """HTTP前後の固定metadataは実await数・戻値・例外を変更しない。"""
    error = RuntimeError("SECRET_HTTP")
    calls = []

    class Response:
        @property
        def status_code(self):
            if metadata_failure:
                raise RuntimeError("SECRET_STATUS")
            return 200

    response = Response()

    class Client:
        async def get(self, index):
            calls.append(index)
            if failure and index == 5:
                raise error
            return response

    script = (
        "async def run():\n"
        + "".join(f"    r{index} = await client.get({index})\n" for index in range(10))
        + "    return r9\n"
    )
    namespace = {"runtime_diagnostics": {}, "client": Client()}
    exec(_instrument_http_stages(script), namespace)
    run = namespace["run"]
    assert isinstance(run, FunctionType)
    try:
        actual = asyncio.run(run())
    except RuntimeError as caught:
        assert failure and caught is error
        assert calls == list(range(6))
    else:
        assert not failure and actual is response
        assert calls == list(range(10))


def test_context_parser_emits_only_declared_function_and_numeric_line():
    """原context/SQL/引数/未知名は一切返さず既4関数の行だけを得る。"""
    namespace = {
        "json": json,
        "actual_sync_router": SimpleNamespace(
            _apply_e1_p3=lambda: None, _apply_e1_f1=lambda: None
        ),
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(_P3_FAILURE_PROBE, namespace)
    parse = namespace["_p3_parse_context"]
    assert isinstance(parse, FunctionType)
    context = (
        "SECRET_SQL parameters SECRET_ARGS\n"
        "PL/pgSQL function sync_right_api.persist_p3_projection(uuid,text) "
        "line 196 at RAISE\n"
        "PL/pgSQL function unknown.secret_fn(SECRET) line 123 at SQL statement\n"
        "PL/pgSQL function sync_fence_api.assert_writer_binding(uuid) "
        "line 55 at PERFORM"
    )
    result = parse(context)
    assert result == [
        {"function": "sync_right_api.persist_p3_projection", "line": 196},
        {"function": "sync_fence_api.assert_writer_binding", "line": 55},
    ]
    assert "SECRET" not in json.dumps(result)
    for raw in (
        None,
        {},
        123,
        context.replace("line 196", "line 0").replace("line 55", "line -1"),
    ):
        assert parse(raw) == []
    assert len(parse(context * 12)) == 8
    locate = namespace["_p3_error_locations"]
    assert isinstance(locate, FunctionType)
    assert locate(SimpleNamespace(diag=SimpleNamespace(context=context))) == []


def test_driver_context_access_failure_preserves_original_error():
    """Driver diag読取が失敗しても元例外を置換しない。"""
    import psycopg

    class DriverError(psycopg.Error):
        @property
        def diag(self):
            raise RuntimeError("SECRET_CONTEXT")

    error = DriverError("SECRET_ORIGINAL")

    def original():
        raise error

    namespace = {
        "json": json,
        "actual_sync_router": SimpleNamespace(
            _apply_e1_p3=original, _apply_e1_f1=original
        ),
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(_P3_FAILURE_PROBE, namespace)
        with pytest.raises(DriverError) as caught:
            namespace["actual_sync_router"]._apply_e1_p3()
        assert caught.value is error
    assert "SECRET" not in output.getvalue()
