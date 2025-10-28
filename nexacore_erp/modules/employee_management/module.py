# nexacore_erp/modules/employee_management/module.py
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .ui.employee_main import EmployeeMainWidget
from .ui.leave_module import LeaveModuleWidget
from .ui.salary_module import SalaryModuleWidget

# module DB init
from ...core.database import init_module_db
from . import models as em_models

# ensure the employee module tables exist on its own DB
init_module_db("employee_management", em_models.Base.metadata)



class Module:
    """Concrete plugin class expected by core.plugins.discover_modules()."""

    def __init__(self):
        self._info = {
            "name": "Employee Management",
            "submodules": ["Leave Management", "Salary Management"],
            "version": "0.1.0",
            "author": "NexaCore Digital Solutions",
        }

    def get_info(self) -> dict:
        return self._info

    def get_widget(self) -> QWidget:
        return EmployeeMainWidget()

    def get_submodule_widget(self, name: str) -> QWidget:
        if name == "Leave Management":
            return LeaveModuleWidget()
        if name == "Salary Management":
            return SalaryModuleWidget()
        return EmployeeMainWidget()


# Optional helpers for loaders that use module-level functions
def get_info():
    return Module().get_info()

def get_widget() -> QWidget:
    return Module().get_widget()

def get_submodule_widget(name: str) -> QWidget:
    return Module().get_submodule_widget(name)
