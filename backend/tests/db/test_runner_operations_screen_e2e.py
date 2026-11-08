"""同一試合の走塁操作を実画面・実保存・原本全値で検査する。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.repositories.ordinary_prefix_read import _evaluate_lineup_payload
from pitchlog.repositories.recorded_snapshot_operations import RECORDED_PLAY_ROW_COLUMNS
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
_CONFIG = "GameScreenRunnerOperations.playwright.config.ts"


_RUNNER_FAILURE_OBSERVER_BOOTSTRAP = r"""
import functools,json,re,threading,time
from datetime import datetime,timezone
from sqlalchemy.exc import DBAPIError as _LowDBAPIError
from starlette.exceptions import HTTPException as _LowHTTPException
from fastapi.routing import APIRoute as _LowAPIRoute
from pitchlog.api.app import ROUTERS as _low_routers
from pitchlog.repositories import rg1 as _low_rg1
from pitchlog.repositories import transaction as _low_transaction
from pitchlog.sync.control_provider import binding_control as _low_binding
from pitchlog.api import errors as _low_errors
from pitchlog.recording_rights import rg1_lifecycle as _low_gate
_low_start=time.monotonic()
_low_lock=threading.Lock()
_low_count=0
_low_truncated=False
_low_operation_ids=frozenset(route.operation_id for router in _low_routers
 for route in router.routes if isinstance(route,_LowAPIRoute)
 and type(route.operation_id) is str
 and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,159}',route.operation_id))
_low_stages=frozenset({'rg1-require-open','rg1-ensure-lease',
 'rg1-assert-lease','rg1-release','writer-lease-check','http-503'})
def _low_identifier(value,*,module=False):
 if type(value) is not str:return None
 pattern=(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'
  if module else r'[A-Za-z_][A-Za-z0-9_]*')
 if len(value)>160 or re.fullmatch(pattern,value) is None:return None
 if module and value.split('.')[0] not in {'pitchlog','sqlalchemy','psycopg',
  'builtins','starlette','fastapi','asyncio'}:return None
 return value

def _low_metadata(error):
 chain=[]
 seen=set()
 current=error
 leaf=None
 cycle=False
 while isinstance(current,BaseException) and len(chain)<8:
  if id(current) in seen:
   cycle=True
   break
  seen.add(id(current))
  kind=type(current)
  kind_module=_low_identifier(kind.__module__,module=True)
  kind_name=_low_identifier(kind.__name__) if kind_module is not None else None
  chain.append({'class':kind_name or 'unknown','module':kind_module or 'unknown'})
  tb=current.__traceback__
  while tb is not None:
   frame=tb.tb_frame
   module=_low_identifier(frame.f_globals.get('__name__'),module=True)
   function=_low_identifier(frame.f_code.co_name)
   line=tb.tb_lineno
   if (module is not None and module.startswith('pitchlog.') and function is not None
    and type(line) is int and 0<line<10000000):
    leaf={'module':module,'function':function,'line':line}
   tb=tb.tb_next
  cause=current.__cause__
  context=current.__context__
  if isinstance(cause,BaseException):current=cause
  elif isinstance(context,BaseException):current=context
  elif isinstance(current,_LowDBAPIError) and isinstance(current.orig,BaseException):
   current=current.orig
  else:current=None
 result={'chain':chain,'chainTruncated':isinstance(current,BaseException) and not cycle,
  'chainCycle':cycle}
 if leaf is not None:result['pitchlogLeaf']=leaf
 return result

def _low_emit(stage,error,extra=None):
 global _low_count,_low_truncated
 try:
  if stage not in _low_stages:return
  with _low_lock:
   if _low_count>=80:
    if not _low_truncated:
     _low_truncated=True
     print('PITCHLOG_RUNNER_FAILURE '+
      json.dumps({'truncated':True,'limit':80}),flush=True)
    return
   record={'stage':stage,**_low_metadata(error),
    'observerMs':min(3600000,max(0,int((time.monotonic()-_low_start)*1000)))}
   if extra is not None:
    for key in ('closed','expired'):
     if type(extra.get(key)) is bool:record[key]=extra[key]
    operation=extra.get('operationId')
    if type(operation) is str and operation in _low_operation_ids:
     record['operationId']=operation
    elapsed=extra.get('elapsedMs')
    if type(elapsed) is int and 0<=elapsed<=3600000:record['elapsedMs']=elapsed
   _low_count+=1
   print('PITCHLOG_RUNNER_FAILURE '+json.dumps(record),flush=True)
 except BaseException:
  pass

def _low_failure_wrapper(original,stage):
 @functools.wraps(original)
 def wrapped(*args,**kwargs):
  try:return original(*args,**kwargs)
  except BaseException as error:
   _low_emit(stage,error)
   raise
 return wrapped

_low_rg1._require_open=_low_failure_wrapper(_low_rg1._require_open,'rg1-require-open')
_low_transaction._TenantTransaction._ensure_rg1_lease=_low_failure_wrapper(
 _low_transaction._TenantTransaction._ensure_rg1_lease,'rg1-ensure-lease')
_low_transaction._TenantTransaction._assert_rg1_lease=_low_failure_wrapper(
 _low_transaction._TenantTransaction._assert_rg1_lease,'rg1-assert-lease')
_low_gate._GateLoan.release=_low_failure_wrapper(
 _low_gate._GateLoan.release,'rg1-release')
_low_original_check=_low_binding._BindingLease.check
@functools.wraps(_low_original_check)
def _low_check(self,*args,**kwargs):
 start=None
 try:start=time.monotonic()
 except BaseException:pass
 try:return _low_original_check(self,*args,**kwargs)
 except BaseException as error:
  extra={}
  try:
   if type(start) is float:
    extra['elapsedMs']=min(3600000,max(0,int((time.monotonic()-start)*1000)))
   closed=self._closed
   if type(closed) is bool:extra['closed']=closed
   expires=self._expires
   if type(expires) is datetime:extra['expired']=datetime.now(timezone.utc)>=expires
  except BaseException:
   pass
  _low_emit('writer-lease-check',error,extra)
  raise
_low_binding._BindingLease.check=_low_check
_low_original_http=_low_errors._http_exception_handler
@functools.wraps(_low_original_http)
async def _low_http(request,error):
 try:
  if isinstance(error,_LowHTTPException) and error.status_code==503:
   extra={}
   scope=getattr(request,'scope',None)
   route=scope.get('route') if type(scope) is dict else None
   if (isinstance(route,_LowAPIRoute) and type(route.operation_id) is str
    and route.operation_id in _low_operation_ids):
    extra['operationId']=route.operation_id
   _low_emit('http-503',error,extra)
 except BaseException:pass
 return await _low_original_http(request,error)
_low_errors._http_exception_handler=_low_http
"""


_RUNNER_DIAGNOSTIC_BOOTSTRAP = r"""
import json,threading,time,re
import psycopg.errors as _owned_pg_errors
from sqlalchemy.exc import DBAPIError as _OwnedDBAPIError
_owned_observer_started=time.monotonic()
_seen_probe_threads=set()
_owned_trace_lock=threading.Lock()
_owned_trace_count=0
_owned_trace_truncated=False
_owned_phase_previous=None
_owned_rpc_state={}
_allowed_errors={
 'RuntimeError','ValueError','TypeError','KeyError','ValidationError',
 'OrdinaryPrefixError','OrdinaryPlayRowError','OrdinaryPitchExecutionError',
 'NonplaySourceUnavailable','PlayExportWriterUnavailable','WriterBindingUnavailable',
 'LineupPrefixProtocolError','TerminalPitchPayloadError','PlayExportIdentityUnavailable',
 'RecordedExportProjectionUnavailable','InsufficientPrivilege','CheckViolation',
 'RaiseException','UndefinedFunction','UndefinedColumn','UniqueViolation',
 'NotNullViolation','ForeignKeyViolation','InvalidTextRepresentation','IntegrityError',
 'ProgrammingError','DataError','OperationalError','StatementError','DomainRuntimeError',
 'LedgerUnavailable','RG1Unavailable','RG1Blocked','P1PreconditionError','SourceBindingError',
 'NoDataFound','TooManyRows','UndefinedTable','InvalidSchemaName',
 'InvalidParameterValue','TimeoutError',
}
def _owned_emit(value):
 global _owned_trace_count,_owned_trace_truncated
 with _owned_trace_lock:
  if _owned_trace_count<80:
   _owned_trace_count+=1
   print('PITCHLOG_RUNNER_STAGE '+json.dumps(dict(value,observerMs=
    min(3600000,max(0,int((time.monotonic()-_owned_observer_started)*1000))))),flush=True)
  elif not _owned_trace_truncated:
   _owned_trace_truncated=True
   print('PITCHLOG_RUNNER_STAGE '+json.dumps({'truncated':True,'limit':80}),flush=True)
def _owned_runner_trace(frame,event,arg):
 module=frame.f_globals.get('__name__','')
 probe=module=='__main__' and frame.f_code.co_name=='_owned_runner_probe'
 if not (probe or (type(module) is str and module.startswith('pitchlog.'))):
  return None
 if event=='exception':
  error_type=arg[0].__name__
  if probe and error_type=='RuntimeError':
   _seen_probe_threads.add(threading.get_ident())
  elif error_type in _allowed_errors:
   _owned_error_record={'module':module,'function':frame.f_code.co_name,
    'line':frame.f_lineno,'error':error_type}
   _owned_error=arg[1]
   if isinstance(_owned_error,_OwnedDBAPIError):
    _owned_orig=_owned_error.orig
    _owned_orig_type=type(_owned_orig)
    _owned_orig_name=_owned_orig_type.__name__
    if (re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',_owned_orig_name)
     and _owned_orig_type.__module__=='psycopg.errors'
     and getattr(_owned_pg_errors,_owned_orig_name,None) is _owned_orig_type):
     _owned_error_record['dbapiKind']=_owned_orig_name
     _owned_state=_owned_orig.sqlstate
     if type(_owned_state) is str and re.fullmatch(r'[A-Z0-9]{5}',_owned_state):
      _owned_error_record['sqlstate']=_owned_state
     _owned_primary=_owned_orig.diag.message_primary
     _owned_fixed_tags={
      'lineup physical source rejected':'lineup_physical',
      'lineup source mismatch':'lineup_source',
      'play prefix source or runners rejected':'play_prefix_runners'}
     if type(_owned_primary) is str and _owned_primary in _owned_fixed_tags:
      _owned_error_record['prepareRejection']=_owned_fixed_tags[_owned_primary]
   _owned_emit(_owned_error_record)
 return _owned_runner_trace
def _owned_runner_probe():
 try:raise RuntimeError()
 except RuntimeError:pass
sys.settrace(_owned_runner_trace)
threading.settrace(_owned_runner_trace)
_owned_runner_probe()
_probe_thread=threading.Thread(target=_owned_runner_probe)
_probe_thread.start();_probe_thread.join(timeout=5)
if _probe_thread.is_alive() or len(_seen_probe_threads)!=2:
 raise RuntimeError('owned diagnostic main/thread trace unavailable')
print('PITCHLOG_RUNNER_OBSERVER '+json.dumps(
 {'probe':'main-and-worker','threads':2}),flush=True)
from pitchlog.api.routers import sync as _owned_sync
from pitchlog.durable_rights_ledger import adapter as _owned_adapter
_owned_original_phase=_owned_sync._phase_id
_owned_original_request=_owned_adapter._request
def _owned_phase(attempt,fingerprint):
 global _owned_phase_previous
 phase=_owned_original_phase(attempt,fingerprint)
 with _owned_trace_lock:
  previous=_owned_phase_previous
  _owned_phase_previous=(attempt,fingerprint,phase)
 _owned_emit({'stage':'phase','prior':previous is not None,
  'sameAttempt':None if previous is None else previous[0]==attempt,
  'sameFingerprint':None if previous is None else previous[1]==fingerprint,
  'samePhase':None if previous is None else previous[2]==phase})
 return phase
def _owned_request(channel,value,*,mutation=False):
 operation=value.get('operation') if type(value) is dict else None
 if operation not in {'binding_open','binding_check','binding_close'}:
  return _owned_original_request(channel,value,mutation=mutation)
 started=time.monotonic()
 with _owned_trace_lock:
  prior=_owned_rpc_state.get(id(channel),{'checkCount':0,'lastCheck':None})
  state=dict(prior)
 def summary(event):
  last=state['lastCheck']
  writer=value.get('writer')
  pid=writer.get('backend_pid') if type(writer) is dict else None
  if type(pid) is not int or not 0<pid<2147483648:pid=None
  _owned_emit({'stage':'binding-rpc','operation':operation,'event':event,
   'writerPid':pid,
   'elapsedMs':min(3600000,max(0,int((time.monotonic()-started)*1000))),
   'checkCount':state['checkCount'],
   'sinceCheckMs':None if last is None else min(3600000,
    max(0,int((started-last)*1000)))})
 if operation!='binding_check':summary('start')
 try:result=_owned_original_request(channel,value,mutation=mutation)
 except BaseException:
  summary('raised')
  raise
 else:
  if operation=='binding_check':
   with _owned_trace_lock:
    state['checkCount']+=1;state['lastCheck']=time.monotonic()
    _owned_rpc_state[id(channel)]=state
  else:summary('done')
  return result
 finally:
  if operation=='binding_close':
   with _owned_trace_lock:_owned_rpc_state.pop(id(channel),None)
_owned_sync._phase_id=_owned_phase
_owned_adapter._request=_owned_request
from contextlib import contextmanager as _owned_contextmanager
from pitchlog.api.routers import started_games as _owned_started_games
from pitchlog.repositories import transaction as _owned_transaction
_owned_started_scope_key=('started_snapshot_read_scope'
 if hasattr(_owned_started_games,'started_snapshot_read_scope')
 else 'tenant_transaction_scope')
_owned_original_started_scope=getattr(_owned_started_games,_owned_started_scope_key)
def _owned_started_pid(handle):
 try:
  runtime=_owned_transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
  if runtime is None:return None
  pid=runtime[0].connection().connection.driver_connection.info.backend_pid
  return pid if type(pid) is int and 0<pid<2147483648 else None
 except Exception:
  return None
def _owned_get_scope_marker(event,pid):
 try:
  _owned_emit({'stage':'get-started-scope','event':event,'pid':pid})
 except Exception:
  pass
@_owned_contextmanager
def _owned_started_scope(*args,**kwargs):
 pid=None
 try:
  with _owned_original_started_scope(*args,**kwargs) as handle:
   pid=_owned_started_pid(handle)
   _owned_get_scope_marker('start',pid)
   yield handle
 finally:
  _owned_get_scope_marker('end',pid)
setattr(_owned_started_games,_owned_started_scope_key,_owned_started_scope)
"""


def _install_runner_fault_server(monkeypatch) -> None:
    """隔離appだけに固定T4故障を注入し、実認可/実TX/元応答は変更しない。"""
    from . import test_screen_start_e2e as screen

    original = screen._app_container
    bootstrap = r"""
import sys,uvicorn
from pitchlog.api.app import create_app
from pitchlog.sync.crash_points import testing_crash_hook
app=create_app()
class OwnedRunnerT4Fault(RuntimeError):
 pass
@app.middleware('http')
async def owned_runner_fault(request,call_next):
 if (request.method=='POST'
     and request.url.path.endswith('/sync/events')
     and request.headers.get('X-Pitchlog-Owned-Runner-Fault')=='after_t4_projection'):
  def fail(point):
   if point=='after_t4_projection':
    print('PITCHLOG_RUNNER_T4_REACHED',flush=True)
    raise OwnedRunnerT4Fault('owned runner projection fault')
  with testing_crash_hook(fail):
   return await call_next(request)
 return await call_next(request)
uvicorn.run(app,host='0.0.0.0',port=int(sys.argv[1]),log_level='warning')
"""

    low_mode = os.environ.get("PITCHLOG_E2E_RUNNER_FAILURE_OBSERVER")
    if low_mode not in (None, "1"):
        raise RuntimeError("低負荷観測modeが未登録")
    if low_mode == "1":
        if any(
            name in os.environ
            for name in (
                "PITCHLOG_E2E_RUNNER_DIAGNOSTIC",
                "PITCHLOG_E2E_RUNNER_AUTHORITY_DIAGNOSTIC_SITE",
            )
        ):
            raise RuntimeError("低負荷観測と全行traceを混在できない")
        code_sha = hashlib.sha256(
            _RUNNER_FAILURE_OBSERVER_BOOTSTRAP.encode()
        ).hexdigest()
        marker = (
            "print('PITCHLOG_RUNNER_FAILURE_OBSERVER ' + "
            + repr(json.dumps({"mode": "failure-only", "observerSha256": code_sha}))
            + ", flush=True)"
        )
        bootstrap = bootstrap.replace(
            "app=create_app()",
            _RUNNER_FAILURE_OBSERVER_BOOTSTRAP + "\n" + marker + "\napp=create_app()",
            1,
        )
    elif os.environ.get("PITCHLOG_E2E_RUNNER_DIAGNOSTIC") == "1":
        bootstrap = bootstrap.replace(
            "app=create_app()", _RUNNER_DIAGNOSTIC_BOOTSTRAP + "\napp=create_app()", 1
        )

    def app_arguments(db, app_port, origin):
        command = original(db, app_port, origin)
        positions = [
            index
            for index in range(len(command) - 1)
            if command[index : index + 2] == ["-m", "uvicorn"]
        ]
        assert len(positions) == 1, "owned故障serverの既bootstrap形が不一致"
        return [*command[: positions[0]], "-c", bootstrap, str(app_port)]

    monkeypatch.setattr(screen, "_app_container", app_arguments)


def _capture_authority_diagnostic(db, destination: Path) -> None:
    """Raw logは保存せず、別workerの閉JSON観測だけを最大200件で固定する。"""
    from .durable_rights_ledger_support import docker

    markers = []
    ready = False
    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,95}$")
    for line in docker("logs", db.authority.service, check=False).splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if value == {"authority_diag_ready": 1}:
            ready = True
        if type(value) is not dict or set(value) != {"authority_diag"}:
            continue
        row = value["authority_diag"]
        if (
            type(row) is not dict
            or set(row) != {"kind", "function", "line", "elapsed_ms"}
            or any(
                type(row[k]) is not str or not identifier.fullmatch(row[k])
                for k in ("kind", "function")
            )
            or type(row["line"]) is not int
            or not 0 < row["line"] < 1000000
            or type(row["elapsed_ms"]) is not int
            or not 0 <= row["elapsed_ms"] <= 3600000
        ):
            continue
        if len(markers) < 200:
            markers.append(row)
    probe = any(
        row["function"] == "_authority_observer_probe" and row["kind"] == "ValueError"
        for row in markers
    )
    destination.write_text(
        json.dumps(
            {
                "ready": ready,
                "probe": probe,
                "atLimit": len(markers) >= 200,
                "records": markers,
            },
            indent=2,
        )
        + "\n"
    )
    assert ready and probe, "authority worker observer did not load"


def _capture_owned_binding_locks(db, destination: Path, stop, comparison: Path) -> None:
    """二要求目の有限窓でowned actorの待機列/lockだけを読み、原文を取得しない。"""
    from time import monotonic

    started = monotonic()
    window_started = None
    samples = []
    error_kind = None
    stop_reason = "stopped-before-second-request"
    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,95}$")
    relation_name = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")

    def closed_identifier(value):
        if value is not None and (
            type(value) is not str or not identifier.fullmatch(value)
        ):
            raise ValueError("診断enumが閉identifierではありません")
        return value

    def positive_pid(value):
        if type(value) is not int or not 0 < value < 2147483648:
            raise ValueError("診断PIDの有限型が不正です")
        return value

    try:
        while not stop.is_set():
            try:
                value = json.loads(comparison.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                stop.wait(0.01)
                continue
            if (
                type(value) is dict
                and type(value.get("comparisons")) is list
                and any(
                    type(row) is dict
                    and type(row.get("ordinal")) is int
                    and row["ordinal"] >= 2
                    for row in value["comparisons"]
                )
            ):
                window_started = monotonic()
                break
            stop.wait(0.01)
        if window_started is None:
            return
        with psycopg.connect(
            db.authority.database.business_admin, autocommit=True
        ) as admin:
            admin.execute("SET statement_timeout='250ms'")
            while (
                not stop.is_set()
                and len(samples) < 40
                and monotonic() - window_started < 4
            ):
                actors = admin.execute(
                    "SELECT pid,usename,wait_event_type,wait_event,"
                    "pg_blocking_pids(pid) "
                    "FROM pg_catalog.pg_stat_activity "
                    "WHERE datname=pg_catalog.current_database() AND ("
                    "(usename='pitchlog_sync_binding_actor' AND state='active') OR "
                    "(usename='pitchlog_app' AND "
                    "pg_catalog.cardinality(pg_catalog.pg_blocking_pids(pid))>0)) "
                    "ORDER BY pid LIMIT 9"
                ).fetchall()
                participants = []
                pids = set()
                for pid, role, wait_type, wait_event, blockers in actors[:8]:
                    pid = positive_pid(pid)
                    blockers = [positive_pid(blocker) for blocker in blockers]
                    pids.update([pid, *blockers])
                    participants.append(
                        {
                            "pid": pid,
                            "role": closed_identifier(role),
                            "waitEventType": closed_identifier(wait_type),
                            "waitEvent": closed_identifier(wait_event),
                            "blockingPids": blockers,
                        }
                    )
                rows = []
                if pids:
                    rows = admin.execute(
                        "SELECT l.pid,a.usename,l.locktype,l.mode,l.granted,"
                        "CASE WHEN c.oid IS NULL THEN NULL "
                        "ELSE n.nspname||'.'||c.relname END "
                        "FROM pg_catalog.pg_locks l "
                        "JOIN pg_catalog.pg_stat_activity a ON a.pid=l.pid "
                        "LEFT JOIN pg_catalog.pg_class c ON c.oid=l.relation "
                        "LEFT JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE l.pid=ANY(%s) "
                        "ORDER BY l.granted,CASE WHEN l.locktype IN "
                        "('transactionid','advisory','tuple','virtualxid') "
                        "THEN 0 ELSE 1 END,CASE WHEN n.nspname IN "
                        "('pg_catalog','information_schema') THEN 1 ELSE 0 END,"
                        "l.pid,l.locktype,l.mode LIMIT 61",
                        (sorted(pids),),
                    ).fetchall()
                locks = []
                for pid, role, kind, mode, granted, relation in rows[:60]:
                    if type(granted) is not bool or (
                        relation is not None
                        and (
                            type(relation) is not str
                            or not relation_name.fullmatch(relation)
                        )
                    ):
                        raise ValueError("診断lockの閉列が不正です")
                    locks.append(
                        {
                            "pid": positive_pid(pid),
                            "role": closed_identifier(role),
                            "locktype": closed_identifier(kind),
                            "mode": closed_identifier(mode),
                            "granted": granted,
                            "relation": relation,
                        }
                    )
                samples.append(
                    {
                        "elapsedMs": round((monotonic() - started) * 1000),
                        "windowElapsedMs": round((monotonic() - window_started) * 1000),
                        "participants": participants,
                        "participantsTruncated": len(actors) > 8,
                        "locks": locks,
                        "locksTruncated": len(rows) > 60,
                    }
                )
                stop.wait(0.1)
            stop_reason = (
                "stopped-during-window" if stop.is_set() else "finite-window-complete"
            )
    except Exception as error:
        error_kind = type(error).__name__
        stop_reason = "observer-error"
    finally:
        destination.write_text(
            json.dumps(
                {
                    "triggered": window_started is not None,
                    "windowStartedMs": None
                    if window_started is None
                    else round((window_started - started) * 1000),
                    "windowSecondsLimit": 4,
                    "sampleLimit": 40,
                    "sampleLimitReached": len(samples) >= 40,
                    "lockRowsLimit": 60,
                    "samples": samples,
                    "stopReason": stop_reason,
                    "errorKind": error_kind,
                },
                indent=2,
            )
            + "\n"
        )


def _all_runner_stats(admin, tenant, game):
    """有効/旧版を含む実T5全行を、当該owned試合だけで閉じて読む。"""
    return {
        table: [
            r[0]
            for r in admin.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) FROM sync_fence.{} AS t "
                    "WHERE tenant_id=%s AND game_id=%s ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table)),
                (tenant, game),
            ).fetchall()
        ]
        for table in (
            "stats_fact_versions",
            "stats_primitive_sources",
            "stats_primitive_facts",
        )
    }


def _capture_runner_fault_baseline(db, checkpoint, stop):
    """実画面の先行1球後を読取専用で封印してから、2球目の送信を許可する。"""
    while not checkpoint.is_file():
        if stop.wait(0.05):
            return None
    game = UUID(json.loads(checkpoint.read_text())["game"])
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute("SET TRANSACTION READ ONLY")
        admin.execute("SET LOCAL statement_timeout='5s'")
        before = _all_runner_stats(admin, db.tenant_id, game)
    assert len(before["stats_fact_versions"]) == 1
    assert before["stats_fact_versions"][0]["source_count"] == 1
    checkpoint.with_suffix(".snapshot.json").write_text(
        json.dumps(before, sort_keys=True)
    )
    Path(str(checkpoint) + ".ready").write_text(str(game))
    return game, before


def _verify_runner_fault_rollback(admin, tenant, result, baseline):
    """実故障要求のlogical IDを使い、runnerを含む全保存面の残存を拒否する。"""
    game = UUID(result["game"])
    assert baseline is not None and baseline[0] == game
    assert _all_runner_stats(admin, tenant, game) == baseline[1]
    failed_play = UUID(result["failedPlayId"])
    failed_event = UUID(result["failedEventId"])
    failed_d5 = UUID(result["failedD5"])
    assert result["status"] == 500 and result["prefix"] == "1"
    for table in ("play_rows", "operation_events", "event_slots"):
        assert admin.execute(
            sql.SQL(
                "SELECT count(*) FROM public.{} WHERE tenant_id=%s AND game_id=%s"
            ).format(sql.Identifier(table)),
            (tenant, game),
        ).fetchone() == (1,)
    assert admin.execute(
        "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND id=%s",
        (tenant, failed_play),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.play_runners WHERE tenant_id=%s AND play_id=%s",
        (tenant, failed_play),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.operation_events WHERE tenant_id=%s AND id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.idempotency_ledger WHERE tenant_id=%s AND d5=%s",
        (tenant, failed_d5),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM sync_fence.stats_primitive_sources "
        "WHERE tenant_id=%s AND source_event_id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM sync_fence.stats_primitive_facts "
        "WHERE tenant_id=%s AND source_event_id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.play_export_snapshots "
        "WHERE tenant_id=%s AND source_event_id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT source_count FROM sync_fence.stats_fact_versions "
        "WHERE tenant_id=%s AND game_id=%s AND is_current",
        (tenant, game),
    ).fetchall() == [(1,)]


def _verify_rows(admin, tenant, game: str, result: dict) -> None:
    """唯一計算が返した原値と実41列/全走者、および独立した終状態を照合する。"""
    count = 2 if result["scope"] == "first" else 17
    assert result["length"] == count
    records = admin.execute(
        "SELECT to_jsonb(p),e.payload FROM public.play_rows AS p "
        "JOIN public.operation_events AS e "
        "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
        "WHERE p.tenant_id=%s AND p.game_id=%s ORDER BY p.play_number LIMIT 18",
        (tenant, game),
    ).fetchall()
    assert len(records) == count
    assert len(result["records"]) == count
    for index, (actual, raw) in enumerate(records):
        payload = _evaluate_lineup_payload(raw)
        request = payload.calculation.request
        value = payload.calculation.response.value
        assert len(actual) == len(RECORDED_PLAY_ROW_COLUMNS) == 41
        assert set(actual) == set(RECORDED_PLAY_ROW_COLUMNS)
        assert actual == pitch_physical_row(
            payload.observations,
            payload.participants,
            request.t1.result_id,
            tenant_id=tenant,
            game_id=UUID(game),
            source_event_id=UUID(actual["source_event_id"]),
            row_id=UUID(actual["id"]),
            play_number=actual["play_number"],
        )
        runners = admin.execute(
            "SELECT to_jsonb(r) FROM public.play_runners AS r "
            "WHERE tenant_id=%s AND play_id=%s ORDER BY base LIMIT 4",
            (tenant, actual["id"]),
        ).fetchall()
        assert [r[0] for r in runners] == runner_physical_rows(
            request.source.runners,
            t1=value.t1,
            t1_input=request.t1,
            tenant_id=tenant,
            play_id=UUID(actual["id"]),
        )
        observed = result["records"][index]
        assert observed["after"] == value.t1.after.model_dump(by_alias=True)
        assert observed["runners"] == [
            r.model_dump(by_alias=True) for r in value.runners
        ]
        if index == 1:
            assert actual["event_kind"] == "non_pitch"
            assert actual["course_x"] is None and actual["course_y"] is None
            assert value.runners[0].base == "2"
            assert value.runners[0].runner_id == request.source.runners[0].runner_id
            assert (
                value.runners[0].responsible_pitcher_id
                == request.source.runners[0].responsible_pitcher_id
            )
    for table in ("operation_events", "event_slots", "play_rows"):
        assert admin.execute(
            sql.SQL(
                "SELECT count(*) FROM public.{} WHERE tenant_id=%s AND game_id=%s"
            ).format(sql.Identifier(table)),
            (tenant, game),
        ).fetchone() == (count,), table
    assert result["replay"] == {"status": 200, "a5": "重複"}
    assert admin.execute(
        "SELECT count(*) FROM public.idempotency_ledger AS l "
        "JOIN public.operation_events AS e ON e.tenant_id=l.tenant_id AND e.d5=l.d5 "
        "WHERE e.tenant_id=%s AND e.game_id=%s",
        (tenant, game),
    ).fetchone() == (count,)
    version = admin.execute(
        "SELECT id,source_count,completion_state FROM sync_fence.stats_fact_versions "
        "WHERE tenant_id=%s AND game_id=%s AND is_current",
        (tenant, game),
    ).fetchall()
    assert len(version) == 1 and version[0][1:] == (count, "current_open")
    # 合計1だけでなく、明示走者本人への帰属と現打者への非加算を確認する。
    # 全recordは上の唯一validatorで検証済み。新しいT5計算は作らない。
    steal_payload = records[1][1]
    steal_request = steal_payload["calculation"]["request"]
    steal_runner = UUID(steal_request["source"]["runners"][0]["runnerId"])
    steal_batter = UUID(steal_payload["participants"]["batterId"])
    assert steal_runner == UUID(records[0][0]["batter_id"])
    assert steal_runner != steal_batter
    steal_credits = admin.execute(
        "SELECT player_id,amount FROM sync_fence.stats_primitive_facts "
        "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
        "AND source_event_id=%s AND metric_id='stolen_bases' AND amount<>0 "
        "ORDER BY player_id,credit_ordinal LIMIT 5",
        (
            tenant,
            game,
            version[0][0],
            UUID(steal_request["playIdentity"]["eventId"]),
        ),
    ).fetchall()
    assert steal_credits == [(steal_runner, 1)]
    assert all(player != steal_batter for player, _ in steal_credits)
    sums = dict(
        admin.execute(
            "SELECT metric_id,SUM(amount) FROM sync_fence.stats_primitive_facts "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
            "GROUP BY metric_id",
            (tenant, game, version[0][0]),
        ).fetchall()
    )
    expected = (
        {"h": 1, "stolen_bases": 1, "pitch_count": 1}
        if count == 2
        else {
            "h": 6,
            "stolen_bases": 1,
            "pitch_count": 11,
            "pitching_outs": 6,
            "k": 1,
            "pitcher_k": 1,
            "runs": 1,
            "runs_allowed": 1,
        }
    )
    assert {key: sums.get(key, 0) for key in expected} == expected
    assert sums.get("rbi", 0) == 0
    if count == 17:
        final = records[-1][1]["calculation"]["response"]["value"]
        fields = final["t1"]["after"]["stateFields"]
        assert fields["state.inning"] == "2"
        assert fields["state.half"] == "top"
        assert fields["state.outs"] == "0"
        assert fields["state.score"] == {"home": "0", "away": "1"}
    print(
        "PITCHLOG_RUNNER_OPERATIONS_DB="
        + json.dumps(
            {
                "scope": result["scope"],
                "plays": count,
                "primitiveSums": {key: str(value) for key, value in sums.items()},
            }
        )
    )


def _verify_available_runner_artifacts(
    db,
    result_file: Path,
    baseline,
    *,
    playwright_returncode: int | None,
    execution_errors: tuple[Exception, ...] = (),
) -> None:
    """存在する各成果を独立DB接続で照合し、元UI失敗は必ず残す。"""
    failures = list(execution_errors)
    evidence = {
        "playwright_returncode": playwright_returncode,
        "execution_error_count": len(execution_errors),
        "normal": "not-generated",
        "fault": "not-generated",
    }
    for label, artifact in (
        ("normal", result_file),
        ("fault", Path(str(result_file) + ".fault")),
    ):
        if not artifact.is_file():
            failures.append(AssertionError(f"{label}成果は未生成/検証未実施"))
            continue
        try:
            result = json.loads(artifact.read_text())
            with psycopg.connect(db.authority.database.business_admin) as admin:
                admin.execute("SET TRANSACTION READ ONLY")
                if label == "normal":
                    assert result["scope"] in ("first", "full")
                    assert result["gameId"] != str(db.game_id)
                    _verify_rows(admin, db.tenant_id, result["gameId"], result)
                else:
                    _verify_runner_fault_rollback(admin, db.tenant_id, result, baseline)
        except Exception as error:
            failures.append(error)
            evidence[label] = "failed"
        else:
            evidence[label] = "verified"
    Path(str(result_file) + ".db-evidence.json").write_text(
        json.dumps(evidence, sort_keys=True)
    )
    if type(playwright_returncode) is not int or playwright_returncode != 0:
        failures.append(AssertionError("Playwrightは成功終了していない"))
    if failures:
        raise ExceptionGroup("走者画面のUI/DB検証に未完了または失敗がある", failures)


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離実HTTPSの明示TLS PATH未供給。画面縦断未実証",
)
def test_runner_operations_screen(
    vertical_database, tmp_path: Path, monkeypatch
) -> None:
    """UI作成/開始から実走塁の保存・重複・reload・越境とDB全値を照合する。"""
    # 共通owned PG lockはrun_owned.pyがfixture作成からcleanupまで保持する。
    # 内側で再取得すると別fdの同一process lock待ちになるため重複取得しない。
    _install_runner_fault_server(monkeypatch)
    db = vertical_database
    # 外部DSNはlauncherが起動前に除外する。fixtureが設定したowned DSNだけを認める。
    owned_admin = (
        os.environ.get("PITCHLOG_TEST_ADMIN_DSN") == db.authority.database.primary_admin
    )
    owned_role = (
        os.environ.get("PITCHLOG_TEST_ROLE_DSN")
        == db.authority.database.endpoints.primary_dsn
    )
    assert owned_admin and owned_role, "隔離fixtureのDSNへ束縛されていません"
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        # 語彙だけを供給する。証拠試合/走者/プレイは全て実画面が作る。
        vocabularies = [
            ("batting-result.single", "batting_result"),
            ("batting-result.called-pitch", "batting_result"),
            ("batting-result.strikeout-double-play", "batting_result"),
            ("secondary-result.wild-pitch", "batting_result"),
            ("secondary-result.passed-ball", "batting_result"),
            ("secondary-result.balk", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ]
        for key, category in vocabularies:
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    assert teams is not None
    result_file = tmp_path / "runner-operations.json"
    assert not result_file.exists()
    assert not Path(str(result_file) + ".fault").exists()
    completed = None
    execution_errors: list[Exception] = []
    baseline = None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, _CONFIG, "runner-operations", https=True
        ) as origin:
            checkpoint = tmp_path / "fault-before.json"
            stop = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as workers:
                captured = workers.submit(
                    _capture_runner_fault_baseline, db, checkpoint, stop
                )
                if os.environ.get("PITCHLOG_E2E_RUNNER_AUTHORITY_DIAGNOSTIC_SITE"):
                    workers.submit(
                        _capture_owned_binding_locks,
                        db,
                        tmp_path / "binding-locks-safe.json",
                        stop,
                        Path(str(result_file) + ".comparison.json"),
                    )
                try:
                    completed = _run_playwright(
                        db,
                        _CONFIG,
                        origin,
                        "runner-operations",
                        {
                            "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                            "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                            "PITCHLOG_E2E_OTHER_TEAM": db.other_team_name,
                            "PITCHLOG_E2E_RESULT_FILE": str(result_file),
                            "PITCHLOG_E2E_RUNNER_FAULT_CHECKPOINT": str(checkpoint),
                        },
                        timeout_seconds=1200,
                    )
                    if os.environ.get("PITCHLOG_E2E_RUNNER_AUTHORITY_DIAGNOSTIC_SITE"):
                        _capture_authority_diagnostic(
                            db, tmp_path / "authority-safe.json"
                        )
                except Exception as error:
                    execution_errors.append(error)
                finally:
                    stop.set()
                try:
                    baseline = captured.result()
                except Exception as error:
                    execution_errors.append(error)
    _verify_available_runner_artifacts(
        db,
        result_file,
        baseline,
        playwright_returncode=None if completed is None else completed.returncode,
        execution_errors=tuple(execution_errors),
    )
