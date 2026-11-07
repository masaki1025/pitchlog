"""自動生成: 保存V7/T2の半回完了値を閉形で読む。"""

from __future__ import annotations

_PROFILES = ({'calculationFormat': 'first-ball-calculation-v1',
  'kind': 'evaluated-no-end-condition',
  'path': None,
  'scope': None,
  'sourceFormat': 'first-ball-play-v1',
  'value': False},
 {'calculationFormat': 'ordinary-pitch-calculation-v1',
  'kind': 'evaluated-no-end-condition',
  'path': ['basis', 'halfCompleted'],
  'scope': 'ordinary37',
  'sourceFormat': 'ordinary-pitch-play-v1',
  'value': False},
 {'calculationFormat': 'play-prefix-calculation-v2',
  'kind': 'evaluated-no-end-condition',
  'path': ['basis', 'halfCompleted'],
  'scope': 'play-prefix-v2',
  'sourceFormat': 'play-prefix-play-v2',
  'value': False},
 {'calculationFormat': 'play-prefix-calculation-v3',
  'kind': 'evaluated-end-condition',
  'path': ['facts', 'halfCompleted'],
  'scope': 'play-prefix-v3',
  'sourceFormat': 'play-prefix-play-v3',
  'value': None},
 {'calculationFormat': 'nonplay-prefix-calculation-v1',
  'kind': 'evaluated-end-condition',
  'path': ['facts', 'halfCompleted'],
  'scope': 'play-prefix-v3',
  'sourceFormat': 'play-prefix-play-v3',
  'value': None})


def saved_half_completed(payload: dict) -> bool:
    """宣言済みのsource/calculation/T2形だけを受理する。"""
    try:
        calculation = payload["calculation"]
        t2 = calculation["response"]["value"]["t2"]
        for profile in _PROFILES:
            if (
                payload["formatVersion"] != profile["sourceFormat"]
                or calculation["formatVersion"] != profile["calculationFormat"]
                or t2["kind"] != profile["kind"]
                or t2.get("scope") != profile["scope"]
            ):
                continue
            path = profile["path"]
            if path is None:
                return False
            if type(path) is not list:
                raise ValueError("保存T2参照経路が不正")
            value = t2
            for key in path:
                value = value[key]
            if type(value) is not bool or (
                profile["value"] is not None and value is not profile["value"]
            ):
                raise ValueError("保存T2完了値が不正")
            return value
    except (KeyError, TypeError):
        pass
    raise ValueError("保存V7/T2の閉形が不正")
