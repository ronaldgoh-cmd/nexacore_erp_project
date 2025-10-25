import importlib.util
import json
import os
from typing import Protocol, List, Tuple, Optional
from PySide6.QtWidgets import QWidget

MODULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules")

class BaseModule(Protocol):
    name: str
    submodules: List[str]
    def get_widget(self) -> QWidget: ...
    def get_submodule_widget(self, subname: str) -> QWidget: ...  # new
    def get_models(self) -> list[type] | None: ...
    def factory_reset(self) -> None: ...

def discover_modules() -> list[Tuple[dict, BaseModule]]:
    mods: list[Tuple[dict, BaseModule]] = []
    for entry in os.listdir(MODULES_DIR):
        path = os.path.join(MODULES_DIR, entry)
        if not os.path.isdir(path):
            continue
        manifest = os.path.join(path, "manifest.json")
        module_py = os.path.join(path, "module.py")
        if os.path.exists(manifest) and os.path.exists(module_py):
            with open(manifest, "r", encoding="utf-8") as f:
                info = json.load(f)
            spec = importlib.util.spec_from_file_location(f"nexacore_erp.modules.{entry}.module", module_py)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore
            module_obj: BaseModule = mod.Module()  # type: ignore
            mods.append((info, module_obj))
    return mods
