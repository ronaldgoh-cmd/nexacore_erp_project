import importlib.util
import json
import os
import sys
from typing import Protocol, List, Tuple
from PySide6.QtWidgets import QWidget

MODULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules")

class BaseModule(Protocol):
    name: str
    submodules: List[str]
    def get_widget(self) -> QWidget: ...
    def get_submodule_widget(self, subname: str) -> QWidget: ...  # new
    def get_models(self) -> list[type] | None: ...
    def factory_reset(self) -> None: ...

_CACHE: list[Tuple[dict, BaseModule]] | None = None


def _load_modules() -> list[Tuple[dict, BaseModule]]:
    mods: list[Tuple[dict, BaseModule]] = []
    for entry in os.listdir(MODULES_DIR):
        path = os.path.join(MODULES_DIR, entry)
        if not os.path.isdir(path):
            continue
        manifest = os.path.join(path, "manifest.json")
        module_py = os.path.join(path, "module.py")
        if not (os.path.exists(manifest) and os.path.exists(module_py)):
            continue

        with open(manifest, "r", encoding="utf-8") as f:
            info = json.load(f)

        module_name = f"nexacore_erp.modules.{entry}.module"
        spec = importlib.util.spec_from_file_location(module_name, module_py)
        if not spec or not spec.loader:
            continue

        module = importlib.util.module_from_spec(spec)
        # Ensure Python reuses the loaded module instead of executing it repeatedly.
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[call-arg]

        module_obj: BaseModule = module.Module()  # type: ignore[attr-defined]
        mods.append((info, module_obj))
    return mods


def discover_modules(*, refresh: bool = False) -> list[Tuple[dict, BaseModule]]:
    """Return available modules, caching the discovery for repeated lookups."""

    global _CACHE
    if refresh or _CACHE is None:
        _CACHE = _load_modules()
    # Return a shallow copy so callers cannot mutate the cache directly.
    return list(_CACHE)


def clear_module_cache() -> None:
    """Reset the cached module discovery results."""

    global _CACHE
    _CACHE = None
