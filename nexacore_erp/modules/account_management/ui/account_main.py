from __future__ import annotations
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from .users_tab import UsersTab
from .roles_tab import RolesAccessTab

class AccountMainWidget(QWidget):
    def __init__(self):
        super().__init__()
        tabs = QTabWidget(self)
        tabs.addTab(UsersTab(), "Users")
        tabs.addTab(RolesAccessTab(), "Roles & Access")
        v = QVBoxLayout(self); v.addWidget(tabs)
