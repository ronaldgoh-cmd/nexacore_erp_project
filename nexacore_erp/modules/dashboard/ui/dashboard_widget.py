"""Dashboard main widget with configurable cards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, Iterable, List, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:  # Optional dependency on employee module
    from ....core.database import get_employee_session
    from ....modules.employee_management.models import Employee, LeaveApplication
except Exception:  # pragma: no cover - module may be missing during unit tests
    get_employee_session = None
    Employee = None
    LeaveApplication = None

from sqlalchemy import inspect

from ....core.auth import get_current_user
from ....core.cloud import (
    digitalocean_provisioning_plan,
    load_cloud_environment,
    render_plan_summary,
)
from ....core.database import SessionLocal
from ....core.models import DashboardPreference


@dataclass
class WidgetDefinition:
    key: str
    title: str
    description: str
    builder: Callable[["DashboardWidget"], QWidget]
    coming_soon: bool = False
    default_enabled: bool = False


class DashboardWidget(QWidget):
    """Host widget displayed when users open the Dashboard module."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DashboardRoot")

        self._current_user = get_current_user()
        self._user_id = getattr(self._current_user, "id", None)
        self._account_id = getattr(self._current_user, "account_id", "default") or "default"
        self._is_ephemeral = isinstance(self._user_id, int) and self._user_id < 0

        self._definitions: Sequence[WidgetDefinition] = _available_widget_definitions()
        self._definitions_by_key: Dict[str, WidgetDefinition] = {d.key: d for d in self._definitions}
        self._active_keys: List[str] = []

        self._load_preferences()
        self._build_ui()
        self._refresh_cards()

    # ---- preference helpers ----
    def _default_keys(self) -> List[str]:
        defaults = [d.key for d in self._definitions if d.default_enabled]
        if defaults:
            return defaults
        return [self._definitions[0].key] if self._definitions else []

    def _load_preferences(self) -> None:
        defaults = self._default_keys()
        if not self._user_id or self._is_ephemeral:
            self._active_keys = list(defaults)
            return

        with SessionLocal() as session:
            pref = (
                session.query(DashboardPreference)
                .filter(
                    DashboardPreference.account_id == self._account_id,
                    DashboardPreference.user_id == self._user_id,
                )
                .first()
            )
            if not pref:
                self._active_keys = list(defaults)
                pref = DashboardPreference(
                    account_id=self._account_id,
                    user_id=self._user_id,
                    widgets_json=json.dumps(self._active_keys),
                )
                session.add(pref)
                session.commit()
                session.refresh(pref)
                return

            try:
                stored = json.loads(pref.widgets_json or "[]")
            except json.JSONDecodeError:
                stored = []
            active = [k for k in stored if k in self._definitions_by_key]
            self._active_keys = active or list(defaults)

    def _save_preferences(self) -> None:
        if not self._user_id or self._is_ephemeral:
            return

        payload = json.dumps(self._active_keys)
        with SessionLocal() as session:
            pref = (
                session.query(DashboardPreference)
                .filter(
                    DashboardPreference.account_id == self._account_id,
                    DashboardPreference.user_id == self._user_id,
                )
                .first()
            )
            if not pref:
                pref = DashboardPreference(
                    account_id=self._account_id,
                    user_id=self._user_id,
                    widgets_json=payload,
                )
                session.add(pref)
            else:
                pref.widgets_json = payload
            session.commit()

    # ---- UI ----
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Dashboard", self)
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        header.addWidget(title)

        subtitle = QLabel("Your at-a-glance company overview", self)
        subtitle.setStyleSheet("color: #666;")
        header.addWidget(subtitle)
        header.addStretch(1)

        config_btn = QPushButton("Configure Widgets", self)
        config_btn.clicked.connect(self._configure_widgets)
        header.addWidget(config_btn)
        root.addLayout(header)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        root.addWidget(self._scroll, 1)

        self._cards_host = QWidget(self)
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)
        self._scroll.setWidget(self._cards_host)

    def _clear_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _refresh_cards(self) -> None:
        self._clear_cards()

        if not self._active_keys:
            placeholder = QLabel("No widgets selected. Use “Configure Widgets” to populate your dashboard.", self._cards_host)
            placeholder.setWordWrap(True)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #777; font-style: italic;")
            self._cards_layout.addWidget(placeholder)
            self._cards_layout.addStretch(1)
            return

        for key in self._active_keys:
            definition = self._definitions_by_key.get(key)
            if not definition:
                continue
            try:
                card = definition.builder(self)
            except Exception as exc:  # pragma: no cover - defensive
                card = self._make_error_card(definition.title, str(exc))
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch(1)

    # ---- events ----
    def _configure_widgets(self) -> None:
        dialog = _WidgetPickerDialog(self._definitions, self._active_keys, self)
        if dialog.exec() != QDialog.Accepted:
            return

        selected = [k for k in dialog.selected_keys() if k in self._definitions_by_key]
        if not selected:
            selected = self._default_keys()
        self._active_keys = selected
        self._save_preferences()
        self._refresh_cards()

    # ---- card factories ----
    def _make_card(
        self,
        title: str,
        body: QWidget,
        *,
        description: str | None = None,
        coming_soon: bool = False,
    ) -> QFrame:
        card = QFrame(self._cards_host)
        card.setFrameShape(QFrame.StyledPanel)
        card.setObjectName("DashboardCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title_lbl = QLabel(title, card)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        header.addWidget(title_lbl)
        header.addStretch(1)
        if coming_soon:
            badge = QLabel("Coming soon", card)
            badge.setStyleSheet(
                "color: #d17c00; border: 1px solid #d17c00; border-radius: 8px;"
                " padding: 2px 8px; font-size: 11px;"
            )
            header.addWidget(badge, 0, Qt.AlignRight)
        layout.addLayout(header)

        if description:
            desc_lbl = QLabel(description, card)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #666;")
            layout.addWidget(desc_lbl)

        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(body)
        return card

    def _make_info_body(self, text: str, *, emphasis: bool = False) -> QWidget:
        host = QWidget(self._cards_host)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(text, host)
        label.setWordWrap(True)
        if emphasis:
            label.setStyleSheet("color: #444; font-style: italic;")
        else:
            label.setStyleSheet("color: #555;")
        layout.addWidget(label)
        return host

    def _make_error_card(self, title: str, message: str) -> QFrame:
        body = self._make_info_body(f"Unable to render widget: {message}", emphasis=True)
        return self._make_card(title, body)

    # ---- public helpers for widget builders ----
    @property
    def account_id(self) -> str:
        return self._account_id


# =============================================================================
# Widget builders
# =============================================================================

def _available_widget_definitions() -> Sequence[WidgetDefinition]:
    return [
        WidgetDefinition(
            key="leave_window",
            title="People on Leave",
            description="Shows employees on approved leave today, tomorrow and the following day.",
            builder=_build_leave_window_card,
            default_enabled=True,
        ),
        WidgetDefinition(
            key="online_presence",
            title="Online Presence",
            description="Planned widget that will list who is online once cloud synchronisation is connected.",
            builder=_build_online_presence_card,
            coming_soon=True,
        ),
        WidgetDefinition(
            key="accounting_overview",
            title="Accounting Overview",
            description="Reserved space for general ledger and cashflow highlights once the accounting module ships.",
            builder=_build_accounting_placeholder,
            coming_soon=True,
        ),
        WidgetDefinition(
            key="inventory_low_stock",
            title="Inventory Alerts",
            description="Will surface low-stock items after the inventory module is installed.",
            builder=_build_inventory_placeholder,
            coming_soon=True,
        ),
    ]


def _build_leave_window_card(host: DashboardWidget) -> QFrame:
    content = LeaveSummaryView(host.account_id)
    description = (
        "Automatically aggregates approved leave applications captured in the "
        "Employee Management module."
    )
    return host._make_card("People on Leave (next 3 days)", content, description=description)


def _build_online_presence_card(host: DashboardWidget) -> QFrame:
    env = load_cloud_environment(host.account_id)
    plan = digitalocean_provisioning_plan(env)
    summary = render_plan_summary(plan)
    body = QWidget(host._cards_host)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    info = QLabel(body)
    info.setWordWrap(True)
    info.setTextInteractionFlags(Qt.TextSelectableByMouse)
    info.setStyleSheet("color: #555;")
    info.setText(
        "Real-time presence requires the cloud synchronisation service. "
        "Follow the provisioning checklist below to prepare the shared environment:<br><br>"
        + summary.replace("\n", "<br>")
    )
    layout.addWidget(info)
    return host._make_card(
        "Online Presence",
        body,
        description="Planning guide for the upcoming online presence widget.",
        coming_soon=True,
    )


def _build_accounting_placeholder(host: DashboardWidget) -> QFrame:
    body = host._make_info_body(
        "Accounting metrics such as cashflow, receivables and payables will appear here once the accounting module is ready.\n"
        "Design the API schema in the new module and the dashboard will connect automatically.",
        emphasis=True,
    )
    return host._make_card(
        "Accounting Overview",
        body,
        description="Placeholder card awaiting the accounting module integration.",
        coming_soon=True,
    )


def _build_inventory_placeholder(host: DashboardWidget) -> QFrame:
    body = host._make_info_body(
        "Low-stock alerts and reorder suggestions will surface here after the inventory module publishes its dataset.",
        emphasis=True,
    )
    return host._make_card(
        "Inventory Alerts",
        body,
        description="Placeholder for the inventory module integration.",
        coming_soon=True,
    )


# =============================================================================
# Leave summary view
# =============================================================================

class LeaveSummaryView(QWidget):
    """Display upcoming leave for the current account."""

    def __init__(self, account_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._account_id = account_id or "default"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._message = QLabel("", self)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #666;")
        layout.addWidget(self._message)

        self._days_host = QVBoxLayout()
        self._days_host.setContentsMargins(0, 0, 0, 0)
        self._days_host.setSpacing(6)
        layout.addLayout(self._days_host)

        self._refresh()

    def _refresh(self) -> None:
        result = _fetch_leave_window(self._account_id, days=3)
        if error := result.get("error"):
            self._message.setText(f"Unable to load leave records: {error}")
            self._message.setStyleSheet("color: #b00020;")
            return
        if message := result.get("message"):
            self._message.setText(message)
            self._message.setStyleSheet("color: #666;")
            return

        self._message.setText("Approved leave for the next three days.")
        self._message.setStyleSheet("color: #666;")

        while self._days_host.count():
            item = self._days_host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        for day, entries in result.get("days", []):
            row = _LeaveDayRow(day, entries)
            self._days_host.addWidget(row)


class _LeaveDayRow(QFrame):
    def __init__(self, day: date, entries: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title = QLabel(day.strftime("%A, %d %b %Y"), self)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        if entries:
            for item in entries:
                lbl = QLabel(f"• {item}", self)
                lbl.setWordWrap(True)
                layout.addWidget(lbl)
        else:
            lbl = QLabel("No employees are on leave.", self)
            lbl.setStyleSheet("color: #777; font-style: italic;")
            layout.addWidget(lbl)


# =============================================================================
# Data layer for leave widget
# =============================================================================

def _fetch_leave_window(account_id: str, days: int = 3) -> Dict[str, object]:
    if not get_employee_session or Employee is None or LeaveApplication is None:
        return {"message": "Employee Management module is not installed yet."}

    session = None
    try:
        session = get_employee_session()
        if session.bind is None:
            return {"message": "Employee database is not initialised."}

        inspector = inspect(session.bind)
        if "employee_leave_applications" not in inspector.get_table_names():
            return {
                "message": "No leave applications recorded yet. Capture leave requests in Employee Management to populate this card.",
            }

        today = date.today()
        window_end = today + timedelta(days=days - 1)

        rows = (
            session.query(LeaveApplication, Employee)
            .join(Employee, LeaveApplication.employee_id == Employee.id)
            .filter(LeaveApplication.account_id == account_id)
            .filter(LeaveApplication.start_date <= window_end)
            .filter(LeaveApplication.end_date >= today)
            .all()
        )

        buckets: Dict[date, List[str]] = {today + timedelta(days=i): [] for i in range(days)}
        for application, employee in rows:
            status = (application.status or "").strip().lower()
            if status and "approve" not in status:
                continue
            start = application.start_date or application.end_date or today
            end = application.end_date or start
            name = (employee.full_name or employee.code or f"Employee #{employee.id}").strip()
            detail = application.leave_type.strip() if application.leave_type else ""
            label = f"{name} — {detail}" if detail else name
            for offset in range(days):
                current = today + timedelta(days=offset)
                if start <= current <= end:
                    buckets[current].append(label)

        ordered = [(day, buckets[day]) for day in sorted(buckets.keys())]
        return {"days": ordered, "today": today, "end": window_end}
    except Exception as exc:  # pragma: no cover - defensive against DB failures
        return {"error": str(exc)}
    finally:
        if session is not None:
            session.close()


# =============================================================================
# Widget picker dialog
# =============================================================================

class _WidgetPickerDialog(QDialog):
    def __init__(
        self,
        definitions: Sequence[WidgetDefinition],
        active_keys: Iterable[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select dashboard widgets")
        self.resize(420, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro = QLabel("Choose which widgets appear on your dashboard.", self)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._list = QListWidget(self)
        self._list.setAlternatingRowColors(True)
        active = set(active_keys)
        for definition in definitions:
            item = QListWidgetItem(definition.title, self._list)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if definition.key in active else Qt.Unchecked)
            item.setData(Qt.UserRole, definition.key)
            tooltip = definition.description
            if definition.coming_soon:
                tooltip += "\n(Integration in progress — data will appear once the respective module is live.)"
            item.setToolTip(tooltip)
            if definition.coming_soon:
                item.setText(f"{definition.title} — planned")
            self._list.addItem(item)
        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_keys(self) -> List[str]:
        keys: List[str] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                key = item.data(Qt.UserRole)
                if key:
                    keys.append(str(key))
        return keys
