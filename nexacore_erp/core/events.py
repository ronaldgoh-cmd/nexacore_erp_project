"""Global application-wide signals.

These are lightweight Qt signals that allow widgets living in separate
modules (for example the Employee list and the Leave/Summary submodules)
to react to shared state changes without creating a tight coupling between
the widgets themselves.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class _EmployeeEvents(QObject):
    """Signals related to employee data changes."""

    employees_changed = Signal()


# Single shared instance that other modules can import and connect to.
employee_events = _EmployeeEvents()

