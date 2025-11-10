# nexacore_erp/ui/access_helpers.py
from __future__ import annotations
from typing import Dict, Optional
from PySide6.QtWidgets import QTabWidget, QLabel
from nexacore_erp.core.auth import get_current_user
from nexacore_erp.core.permissions import can_view

def apply_tab_access(tabs: QTabWidget, module_name: str, submap: Optional[Dict[str, str]] = None) -> None:
    """
    Hide tabs the current user cannot view.
    - module_name must equal discover_modules()[i]["name"] for this module.
    - submap maps visible tab text -> submodule key stored in AccessRule.
      If None, the visible tab text is used as the submodule key.
    """
    user = get_current_user()
    # superadmin always sees everything
    if not user or getattr(user, "role", "") == "superadmin":
        return

    # remove disallowed tabs (iterate backwards)
    for i in range(tabs.count() - 1, -1, -1):
        label = tabs.tabText(i)
        key = (submap or {}).get(label, label)
        if not can_view(user.id, module_name, key):
            tabs.removeTab(i)

    # if nothing left, show a friendly message
    if tabs.count() == 0:
        tabs.addTab(QLabel("No access to any tabs in this module."), "Access")
