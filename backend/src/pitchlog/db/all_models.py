"""製品の全 ORM モデルを走査して宣言的基底へ登録する。"""

from importlib import import_module
from pathlib import Path
from pkgutil import walk_packages


def _discover_model_module_names() -> tuple[str, ...]:
    """`pitchlog.db` 配下の models モジュール名を走査で返す。"""
    package_path = Path(__file__).parent
    package_prefix = f"{__package__}."
    return tuple(
        sorted(
            module_info.name
            for module_info in walk_packages(
                [str(package_path)],
                prefix=package_prefix,
            )
            if module_info.name.rsplit(".", maxsplit=1)[-1] == "models"
        )
    )


def _import_all_models() -> tuple[str, ...]:
    """走査で見つけた全 models モジュールを import して名前を返す。"""
    module_names = _discover_model_module_names()
    for module_name in module_names:
        import_module(module_name)
    return module_names


IMPORTED_MODEL_MODULE_NAMES = _import_all_models()
