"""旧試行照会の既二値と、ACKを混ぜない閉HTTP応答を検証する。"""

from __future__ import annotations

import ast
import inspect
from typing import get_args, get_type_hints

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from pitchlog.api.routers import sync
from pitchlog.api.schemas.recovery_response import AttemptRecoveryResponse
from pitchlog.sync.control_provider.binding_control import BindingControl


def _route() -> APIRoute:
    """実登録routerから旧試行照会の一意なrouteを取得する。"""
    matches = [
        route
        for route in sync.router.routes
        if isinstance(route, APIRoute) and route.operation_id == "recover_sync_attempt"
    ]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("resolution", ["retry_allowed", "unresolved"])
def test_each_existing_resolution_keeps_the_same_closed_wire_value(resolution):
    """既実portと同じ二値を、変換/キー追加なく実routeの型へ通す。"""
    body = {"resolution": resolution}
    response = AttemptRecoveryResponse.model_validate(body)
    assert response.model_dump(mode="json") == body
    route = _route()
    assert route.response_field is not None
    validated, errors = route.response_field.validate(body, {}, loc=("response",))
    assert not errors
    assert isinstance(validated, AttemptRecoveryResponse)
    assert validated.model_dump(mode="json") == body


@pytest.mark.parametrize(
    "body",
    [
        {},
        None,
        [],
        {"resolution": None},
        {"resolution": True},
        {"resolution": 1},
        {"resolution": ["retry_allowed"]},
        {"resolution": "unknown"},
        {"resolution": "stopped"},
        {"resolution": "stored_result_available"},
        {"resolution": "rollback_confirmed"},
        {"resolution": "commit_unknown"},
        {"resolution": "B5"},
        {"resolution": "B6"},
        {"resolution": "B7"},
        {"resolution": "受理"},
        {"resolution": "retry_allowed", "advancedD3": 0},
        {"resolution": "unresolved", "eventResults": []},
        {"resolution": "retry_allowed", "extra": None},
        {"advancedD3": 0, "eventResults": []},
    ],
)
def test_non_wire_results_ack_and_extra_fields_are_rejected(body):
    """停止照会の別union・認可境界・ACK・余剰を成功二値へ読み替えない。"""
    with pytest.raises(ValidationError):
        AttemptRecoveryResponse.model_validate(body)
    route = _route()
    assert route.response_field is not None
    _, errors = route.response_field.validate(body, {}, loc=("response",))
    assert errors


def test_response_type_matches_existing_control_port_and_validates_actual_return():
    """実portの二値と一致し、JSONResponseによる型検証迂回をしない。"""
    expected = get_args(get_type_hints(BindingControl.recover_attempt)["return"])
    assert get_args(AttemptRecoveryResponse.model_fields["resolution"].annotation) == (
        expected
    )
    route = _route()
    assert route.response_model is AttemptRecoveryResponse
    assert get_type_hints(sync.recover_attempt)["return"] is AttemptRecoveryResponse
    tree = ast.parse(inspect.getsource(sync.recover_attempt))
    returns = [node.value for node in ast.walk(tree) if isinstance(node, ast.Return)]
    assert len(returns) == 1 and isinstance(returns[0], ast.Call)
    assert isinstance(returns[0].func, ast.Name)
    assert returns[0].func.id == "AttemptRecoveryResponse"
    assert [(k.arg, ast.unparse(k.value)) for k in returns[0].keywords] == [
        ("resolution", "result")
    ]


def test_existing_authorization_http_error_mapping_is_preserved():
    """既B5/B6/B7を二値DTOへ合流せず401/404/503のままにする。"""
    tree = ast.parse(inspect.getsource(sync.recover_attempt))
    errors = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if ast.unparse(node.test.left) != "result" or len(node.test.comparators) != 1:
            continue
        literal = node.test.comparators[0]
        if not isinstance(literal, ast.Constant):
            continue
        assert len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
        raised = node.body[0].exc
        assert (
            isinstance(raised, ast.Call) and ast.unparse(raised.func) == "HTTPException"
        )
        status = next(k.value for k in raised.keywords if k.arg == "status_code")
        assert isinstance(status, ast.Constant)
        errors[literal.value] = status.value
    assert errors == {"B5": 401, "B6": 404, "B7": 503}
