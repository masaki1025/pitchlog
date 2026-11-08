"""正常currentだけの約二球P3で、公開503の元例外分類を限定採取する。"""

from __future__ import annotations

import ast
import json
import subprocess
from uuid import uuid4

import psycopg
import pytest

from pitchlog.db.current_product_startup import CURRENT_REVISION

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_p3_candidate_compile_author import _three_ball_p3_script

pytestmark = pytest.mark.requires_db

_P3_FAILURE_PROBE = r"""
import re, traceback
import psycopg as _p3_driver
_probe_plpgsql_names = frozenset({
    'sync_right_api.persist_p3_projection',
    'sync_fence_api.assert_writer_binding',
    'sync_fence_api.read_p3_writer_binding',
    'stats_api.save_primitive_source',
})
def _p3_parse_context(context):
    if type(context) is not str or len(context)>65536:
        return []
    result=[]
    pattern=(r'^PL/pgSQL function ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)'
             r'\([^\n)]{0,512}\) line ([1-9][0-9]{0,5})(?: at [^\n]*)?$')
    for match in re.finditer(pattern,context,re.MULTILINE):
        if match.group(1) in _probe_plpgsql_names:
            result.append({'function':match.group(1),'line':int(match.group(2))})
        if len(result)>=8:break
    return result

def _p3_error_locations(error):
    if not isinstance(error,_p3_driver.Error):
        return []
    # 原contextはメモリ内で閉関数名/行だけに変え、出力/保存しない。
    return _p3_parse_context(getattr(error.diag,'context',None))

_probe_count = 0
_probe_allowed = frozenset({
    'SourceBindingError','ValueError','TypeError','WriterBindingUnavailable',
    'OrdinaryPrefixError','OrdinaryPitchExecutionError','OrdinaryPlayRowError',
    'PlayExportWriterUnavailable',
    'LedgerUnavailable','PastCorrectionExecutionError',
    'PastCorrectionPreparationUnavailable','PastCorrectionProjectionError',
    'PastCorrectionPageUnavailable','PastCorrectionSourceUnavailable',
    'PastCorrectionContentRejected','PastCorrectionStatsUnsupported',
    'RG1Blocked','RG1Unavailable','RG1ControlUnavailable',
    'ProgrammingError','OperationalError','InterfaceError','DBAPIError',
    'StatementError','IntegrityError','InsufficientPrivilege','CheckViolation',
    'RaiseException','UndefinedColumn','AmbiguousColumn','UndefinedFunction',
    'UndefinedTable','InvalidSchemaName','InvalidParameterValue','QueryCanceled',
    'TimeoutError','ConnectionTimeout','DomainRuntimeError','NodeUnavailable',
})
def _p3_safe_chain(error):
    pending=[error];seen=set();rows=[]
    while pending and len(rows)<8:
        current=pending.pop(0)
        if not isinstance(current,BaseException) or id(current) in seen:
            continue
        seen.add(id(current));name=type(current).__name__
        state=getattr(current,'sqlstate',None)
        if not isinstance(state,str) or not re.fullmatch(r'[0-9A-Z]{5}',state):
            state=None
        sites=[]
        for frame in traceback.extract_tb(current.__traceback__):
            match=re.search(r'/src/pitchlog/([A-Za-z0-9_/]+\.py)$',frame.filename)
            if match:
                sites.append({'file':'src/pitchlog/'+match.group(1),'line':frame.lineno})
        rows.append({'class':name if name in _probe_allowed else 'other',
                     'sqlstate':state,'sites':sites[-3:],
                     'plpgsql_sites':_p3_error_locations(current)})
        pending.extend((current.__cause__,current.__context__,getattr(current,'orig',None)))
    return rows

def _p3_emit(value):
    global _probe_count
    try:
        if _probe_count>=80:return
        _probe_count+=1
        print('PITCHLOG_P3_SHORT_SAFE '+json.dumps(value),flush=True)
    except BaseException:
        pass

def _p3_wrap(original,boundary):
    assert boundary in {'router-e1-p3','router-e1-f1'}
    def observed(*args,**kwargs):
        try:
            result=original(*args,**kwargs)
        except BaseException as error:
            try:_p3_emit({'boundary':boundary,'outcome':'raised',
                         'chain':_p3_safe_chain(error)})
            except BaseException:pass
            raise
        if type(result) is str and result in {'B6','B7','B10','B11','B12'}:
            _p3_emit({'boundary':boundary,'outcome':'rejected','result':result})
        return result
    return observed
actual_sync_router._apply_e1_p3 = _p3_wrap(
    actual_sync_router._apply_e1_p3,'router-e1-p3')
actual_sync_router._apply_e1_f1 = _p3_wrap(
    actual_sync_router._apply_e1_f1,'router-e1-f1')
print('PITCHLOG_P3_SHORT_READY='+json.dumps({'ready':1,'limit':80}),flush=True)
"""


def build_short_p3_script() -> str:
    """既実HTTPの操作だけを使い、旧診断/候補DDL/故障統合を呼ばない。"""
    from pitchlog.authz.first_ball_product import BODIES

    declared = {
        ".".join(key.removeprefix("function|FUNCTION:").split("(", 1)[0].split(":"))
        for key in BODIES
        if key.startswith("function|FUNCTION:")
    }
    assert {
        "sync_right_api.persist_p3_projection",
        "sync_fence_api.assert_writer_binding",
        "sync_fence_api.read_p3_writer_binding",
        "stats_api.save_primitive_source",
    } <= declared
    script = _three_ball_p3_script()
    # 旧ordinary/P3のdiag.context/primary依存traceは起動前に全文除去する。
    start = script.index("_actual_apply = actual_sync_router._apply_e1_f1")
    end = script.index("actual_sync_router._apply_e1_f1 = traced_apply", start)
    end += len("actual_sync_router._apply_e1_f1 = traced_apply")
    script = script[:start] + script[end:]
    start = script.index("_actual_p3_apply = actual_sync_router._apply_e1_p3")
    end = script.index("async def run():", start)
    script = script[:start] + _P3_FAILURE_PROBE + "\n" + script[end:]
    # 新しい診断caseは2球/target1/P3/同current再取得だけ。旧26/fault条件は不変更。
    end = script.index("        negative_d5s = []")
    script = (
        script[:end]
        + r"""
        runtime_diagnostics.update(stage='short-p3-post',status=None)
        changed=await client.post('/games/'+game+'/sync/change',
            headers=device_headers(pair,str(uuid4())),json=p3_payload)
        runtime_diagnostics['status']=changed.status_code
        assert changed.status_code==200
        runtime_diagnostics.update(stage='short-p3-get',status=None)
        saved=await client.get(
            '/games/'+game+'/started?projection=play-prefix-v3&limit=25',
            headers=headers())
        runtime_diagnostics['status']=saved.status_code
        assert saved.status_code==200
        assert saved.json()['prefix_ref']['length']=='2'
        return {'complete':True,'prefix':'2','stage':'short-p3-get','status':200}

try:
    out=asyncio.run(run())
except BaseException as error:
    print('PITCHLOG_P3_SHORT_RESULT='+json.dumps({
        'exception':type(error).__name__,
        'stage':runtime_diagnostics.get('stage'),
        'status':runtime_diagnostics.get('status'),
        'script_sites':[{'file':'p3-short-current','line':frame.lineno}
                        for frame in traceback.extract_tb(error.__traceback__)
                        if frame.filename=='<string>'][-3:]}),flush=True)
    raise SystemExit(1)
print('PITCHLOG_P3_SHORT_RESULT='+json.dumps(out),flush=True)
"""
    )
    assert "message_primary" not in script
    assert "message_detail" not in script and "format_exc" not in script
    script = _instrument_http_stages(script)
    compile(script, "<p3-short-current>", "exec")
    return script


def _instrument_http_stages(script: str) -> str:
    """既await原式を不変更に保ち、固定stageだけ前後へ付ける。"""
    module = ast.parse(script)
    stages = []

    class Instrument(ast.NodeTransformer):
        def visit_AsyncFunctionDef(self, node):
            if node.name != "run":
                return node
            return self.generic_visit(node)

        def visit_Assign(self, node):
            value = node.value
            if not (
                isinstance(value, ast.Await)
                and isinstance(value.value, ast.Call)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                return node
            function = value.value.func
            if not (
                isinstance(function, ast.Attribute)
                and function.attr in {"get", "post", "put", "patch", "delete"}
                or isinstance(function, ast.Name)
                and function.id == "login"
            ):
                return node
            name = node.targets[0].id
            label = f"http-{len(stages) + 1:02d}-{name}"
            stages.append(label)
            before = ast.parse(f"_short_stage({label + '-before'!r})").body[0]
            after = ast.parse(f"_short_stage({label + '-after'!r}, {name})").body[0]
            return [before, node, after]

    before_calls = [
        ast.dump(n.value, include_attributes=False)
        for n in ast.walk(module)
        if isinstance(n, ast.Await)
    ]
    module = Instrument().visit(module)
    after_calls = [
        ast.dump(n.value, include_attributes=False)
        for n in ast.walk(module)
        if isinstance(n, ast.Await)
    ]
    assert before_calls == after_calls
    assert len(stages) >= 10
    helper = ast.parse("""
def _short_stage(stage, response=None):
    try:
        runtime_diagnostics.update(stage=stage,
            status=None if response is None else response.status_code)
    except BaseException:
        pass
""")
    module.body[0:0] = helper.body
    ast.fix_missing_locations(module)
    return ast.unparse(module)


def _counts(db) -> dict[str, object]:
    """隔離tenantの有限末尾counterだけをREAD ONLYで保持する。"""
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as conn:
        result: dict[str, object] = {}
        for name, table in (
            ("plays", "public.play_rows"),
            ("events", "public.operation_events"),
            ("slots", "public.event_slots"),
            ("bindings", "sync_fence.writer_bindings"),
            ("checkpoints", "sync_fence.ordinary_pitch_checkpoints"),
            ("p3caps", "sync_fence.p3_projection_capsules"),
            ("p3heads", "sync_fence.p3_projection_heads"),
            ("p3snapshots", "sync_fence.play_export_p3_snapshots"),
        ):
            row = conn.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (db.tenant_id,)
            ).fetchone()
            assert row is not None and type(row[0]) is int and row[0] >= 0
            result[name] = row[0]
        result["checkpoint_rows"] = [
            [str(row[0]), row[1], row[2]]
            for row in conn.execute(
                "SELECT id,revision,content_digest "
                "FROM sync_fence.ordinary_pitch_checkpoints "
                "WHERE tenant_id=%s ORDER BY revision",
                (db.tenant_id,),
            ).fetchall()
        ]
        result["slot_generations"] = [
            [row[0], row[1]]
            for row in conn.execute(
                "SELECT generation,count(*) FROM public.event_slots "
                "WHERE tenant_id=%s GROUP BY generation ORDER BY generation",
                (db.tenant_id,),
            ).fetchall()
        ]
        result["versions"] = [
            [str(row[0]), row[1], row[2], row[3], row[4], row[5], row[6]]
            for row in conn.execute(
                "SELECT id,revision,source_count,is_current,"
                "invalidated_at,completion_state,source_set_sha256 "
                "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s "
                "ORDER BY revision",
                (db.tenant_id,),
            ).fetchall()
        ]
        result["primitive_counts"] = [
            [str(row[0]), row[1]]
            for row in conn.execute(
                "SELECT fact_version_id,count(*) "
                "FROM sync_fence.stats_primitive_sources WHERE tenant_id=%s "
                "GROUP BY fact_version_id ORDER BY 1",
                (db.tenant_id,),
            ).fetchall()
        ]
        hash_row = conn.execute(
            "SELECT encode(sha256(convert_to(COALESCE(string_agg("
            "jsonb_build_array(tenant_id,game_id,recording_generation,d1,d2,"
            "source_event_id,slot_version,play_row_id,play_row_version,"
            "source_fingerprint)::text,E'\\n' ORDER BY tenant_id,game_id,d2,"
            "source_event_id),'accepted-play-slot-v1:empty'),'UTF8')),'hex') "
            "FROM sync_fence.stats_primitive_sources WHERE tenant_id=%s",
            (db.tenant_id,),
        ).fetchone()
        result["primitive_hash"] = None if hash_row is None else hash_row[0]
        return result


def test_p3_short_current_route_diagnostic(vertical_database, tmp_path):
    """後付SQLなしの正常49配置で、実C2/実P3入口の失敗を切り分ける。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as conn:
        assert conn.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [(CURRENT_REVISION,)]
        # 元P3 fixtureと同じ入力語彙だけを用意する。候補SQL/認可は追加しない。
        conn.execute(
            "EXPLAIN SELECT category,display_name FROM public.admin_vocabularies "
            "WHERE key=%s",
            ("batting-result.called-pitch",),
        )
        conn.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch',"
            "'batting_result','見逃し') ON CONFLICT(key) DO NOTHING"
        )
        assert conn.execute(
            "SELECT category,display_name FROM public.admin_vocabularies WHERE key=%s",
            ("batting-result.called-pitch",),
        ).fetchall() == [("batting_result", "見逃し")]
        for table in (
            "public.play_rows",
            "public.operation_events",
            "public.event_slots",
            "sync_fence.writer_bindings",
        ):
            conn.execute(
                f"EXPLAIN SELECT count(*) FROM {table} WHERE tenant_id=%s",
                (db.tenant_id,),
            )
    case = dict(
        tenant=str(db.tenant_id),
        game=str(db.game_id),
        team_name=db.team_name,
        other_team_name=db.other_team_name,
        other_tenant_id=str(db.other_tenant_id),
        password=_PASSWORD,
        pitch_type=_PITCH_TYPE,
    )
    token = uuid4()
    script = build_short_p3_script()
    result = None
    audit_ok = False
    try:
        with db.broker_worker(token), binding_broker(db, token):
            _prepare_app_configuration(db)
            result = subprocess.run(
                ["docker", *_app_arguments(db, case), "-u", "-c", script],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
    finally:
        try:
            (tmp_path / "p3-short-db-counts.json").write_text(json.dumps(_counts(db)))
            audit_ok = True
        except Exception as error:
            try:
                (tmp_path / "p3-short-db-counts.json").write_text(
                    json.dumps({"audit": "unavailable", "class": type(error).__name__})
                )
            except Exception:
                pass
    assert result is not None
    safe = {"ready": [], "failures": [], "result": []}
    for line in result.stdout.splitlines():
        for prefix, key in (
            ("PITCHLOG_P3_SHORT_READY=", "ready"),
            ("PITCHLOG_P3_SHORT_SAFE ", "failures"),
            ("PITCHLOG_P3_SHORT_RESULT=", "result"),
        ):
            if line.startswith(prefix):
                safe[key].append(json.loads(line[len(prefix) :]))
    (tmp_path / "p3-short-safe.json").write_text(json.dumps(safe, indent=2))
    assert safe["ready"] == [{"ready": 1, "limit": 80}]
    assert result.returncode == 0, "短P3正常routeは未成立（閉metadataを別保存）"
    assert audit_ok, "owned末尾監査は未成立"
    assert safe["result"] == [
        {"complete": True, "prefix": "2", "stage": "short-p3-get", "status": 200}
    ]
