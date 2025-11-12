"""Dashboard module entry point."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .ui.dashboard_widget import DashboardWidget


class Module:
    """Concrete plugin for the configurable dashboard."""

    def __init__(self) -> None:
        self._info = {
            "name": "Dashboard",
            "submodules": [],
            "version": "0.1.0",
            "author": "NexaCore Digital Solutions",
            "always_enabled": True,
            "always_visible": True,
            "weight": -1000,
            "tab_manifest": {"__module__": ["Overview"]},
        }

    def get_info(self) -> dict:
        return self._info

    def get_widget(self) -> QWidget:
        return DashboardWidget()

    def get_submodule_widget(self, name: str) -> QWidget:  # pragma: no cover - there are no submodules
        return DashboardWidget()


# Optional helpers for loaders that use module-level functions

def get_info():
    return Module().get_info()


def get_widget() -> QWidget:
    return Module().get_widget()


def get_submodule_widget(name: str) -> QWidget:
    return Module().get_submodule_widget(name)
