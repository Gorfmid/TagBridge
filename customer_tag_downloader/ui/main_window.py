# =============================================================================
# File:        main_window.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: PySide6 main window (login, sites, export, download).
# =============================================================================
"""
Biomark Tag Manager — PySide6 main window.

Layout: left column (logo, version, login, sites); right column (export); compact download footer.
Network work runs on ``Worker`` (QThread); see ``ProgressDialog`` for status/logs.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from customer_tag_downloader import api
from customer_tag_downloader.config import (
    APP_NAME,
    PROVIDERS,
    app_version,
    get_provider,
    resource_path,
    tags_dir,
)
from customer_tag_downloader.settings import (
    AppSettings,
    delete_password,
    load_password,
    save_password,
)
from customer_tag_downloader.export_fields import (
    default_custom_fields_for_provider,
    field_labels,
    normalize_field_ids,
)
from customer_tag_downloader.export_data import render_export_preview
from customer_tag_downloader.export_fields import needs_site_info
from customer_tag_downloader.services import download_tags, fetch_preview_site_exports
from customer_tag_downloader.ui.custom_export_dialog import (
    CustomExportColumnsDialog,
    summarize_custom_columns,
)
from customer_tag_downloader.ui.progress_dialog import ProgressDialog
from customer_tag_downloader.ui.responsive import (
    apply_root_font,
    download_button_style,
    is_compact,
    is_narrow,
    sites_list_style,
    summary_label_style,
    update_splitter_orientation,
    version_label_style,
)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_PREVIEW_PLACEHOLDER = "Sign in and select at least one site, then click Build Preview."
_PREVIEW_READY_PLACEHOLDER = "Click Build Preview to load a sample from the API."


def _is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def _normalize_calendar_year(year: int) -> int:
    if 0 <= year < 100:
        return year + 2000
    return year


def _coerce_qdate(value: QDate) -> QDate:
    if not value.isValid():
        return value
    year = _normalize_calendar_year(value.year())
    if year == value.year():
        return value
    return QDate(year, value.month(), value.day())


class Worker(QThread):
    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(self, task) -> None:
        super().__init__()
        self._task = task

    def run(self) -> None:
        try:
            self.finished_ok.emit(self._task())
        except api.ApiError as exc:
            self.finished_error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.finished_error.emit(f"Unexpected error: {exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._client: api.BioLogicClient | None = None
        self._sites: list[api.Site] = []
        self._worker: Worker | None = None
        self._progress: ProgressDialog | None = None
        self._ignore_worker_result = False
        self._settings = AppSettings.load()
        self._output_dir = Path(self._settings.output_dir) if self._settings.output_dir else tags_dir()

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(520, 380)
        self.resize(860, 520)
        self._custom_export_field_ids: list[str] = default_custom_fields_for_provider("biomark")
        self._compact_mode: bool | None = None
        self._logo_pixmap: QPixmap | None = None
        self._active_export_format = "csv"
        self._applying_site_group = False
        self._build_ui()
        self._apply_settings()
        self._apply_responsive_layout()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        self._scroll_body = QScrollArea()
        self._scroll_body.setWidgetResizable(True)
        self._scroll_body.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setSpacing(6)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.addWidget(self._build_left_column())
        self._main_splitter.addWidget(self._build_export_group())
        self._main_splitter.setStretchFactor(0, 3)
        self._main_splitter.setStretchFactor(1, 4)
        self._main_splitter.setSizes([380, 460])
        self._scroll_layout.addWidget(self._main_splitter, stretch=1)

        self._scroll_body.setWidget(scroll_content)
        root.addWidget(self._scroll_body, stretch=1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.addStretch()
        self.download_button = QPushButton("Download tags")
        self.download_button.setFixedHeight(28)
        self.download_button.clicked.connect(self._on_download)
        footer.addWidget(self.download_button)
        root.addLayout(footer)

    def _build_branding_block(self) -> QWidget:
        block = QWidget()
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 4)
        col.setSpacing(2)

        logo_path = resource_path("biomark_logo.png")
        self._logo_label: QLabel | None = None
        if logo_path.is_file():
            self._logo_label = QLabel()
            self._logo_pixmap = QPixmap(str(logo_path))
            self._logo_label.setPixmap(
                self._logo_pixmap.scaledToHeight(
                    40, Qt.TransformationMode.SmoothTransformation
                )
            )
            self._logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            col.addWidget(self._logo_label)

        self.version_label = QLabel(f"Version {app_version()}")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.version_label)
        block.setMaximumWidth(220)
        return block

    def _build_left_column(self) -> QWidget:
        column = QWidget()
        column.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout = QVBoxLayout(column)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 4, 0)

        layout.addWidget(self._build_branding_block())
        login = self._build_login_group()
        login.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(login)
        sites = self._build_sites_group()
        sites.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(sites, stretch=1)
        return column

    def _build_login_group(self) -> QGroupBox:
        group = QGroupBox("Login")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        form = QFormLayout()
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(3)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.provider_combo = QComboBox()
        for provider in PROVIDERS.values():
            self.provider_combo.addItem(provider.label, provider.id)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Portal:", self.provider_combo)

        self.login_id_input = QLineEdit()
        self.login_id_input.setPlaceholderText("Email address")
        form.addRow("Email:", self.login_id_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        form.addRow("Password:", self.password_input)
        layout.addLayout(form)

        opts = QVBoxLayout()
        opts.setSpacing(0)
        self.save_credentials_checkbox = QCheckBox("Save credentials")
        self.skip_ssl_checkbox = QCheckBox("Skip SSL verify")
        self.save_settings_checkbox = QCheckBox("Remember settings")
        self.save_settings_checkbox.setChecked(True)
        opts.addWidget(self.save_credentials_checkbox)
        opts.addWidget(self.skip_ssl_checkbox)
        opts.addWidget(self.save_settings_checkbox)
        layout.addLayout(opts)

        buttons = QHBoxLayout()
        self.sign_in_button = QPushButton("Sign In")
        self.sign_in_button.clicked.connect(self._on_sign_in)
        buttons.addWidget(self.sign_in_button)
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._on_test_connection)
        buttons.addWidget(self.test_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        return group

    def _build_sites_group(self) -> QGroupBox:
        group = QGroupBox("Sites")
        layout = QVBoxLayout(group)
        self.sites_list = QListWidget()
        self.sites_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.sites_list.setStyleSheet(sites_list_style())
        self.sites_list.itemSelectionChanged.connect(self._on_site_selection_changed)
        self.sites_list.itemClicked.connect(self._on_site_item_clicked)
        layout.addWidget(self.sites_list)
        row = QHBoxLayout()
        select_all = QPushButton("All")
        select_all.clicked.connect(self._select_all_visible_sites)
        row.addWidget(select_all)
        clear_sel = QPushButton("None")
        clear_sel.clicked.connect(self._clear_visible_site_selection)
        row.addWidget(clear_sel)
        self.sites_search_input = QLineEdit()
        self.sites_search_input.setPlaceholderText("Search sites…")
        self.sites_search_input.textChanged.connect(self._filter_sites_list)
        row.addWidget(self.sites_search_input, stretch=1)
        layout.addLayout(row)
        group_row = QHBoxLayout()
        group_row.addWidget(QLabel("Group:"))
        self.site_group_combo = QComboBox()
        self.site_group_combo.setToolTip("Choose a saved site grouping to load")
        self.site_group_combo.currentIndexChanged.connect(self._on_site_group_changed)
        group_row.addWidget(self.site_group_combo, stretch=1)
        save_group = QPushButton("Save…")
        save_group.setToolTip("Save the current site selection as a named group")
        save_group.clicked.connect(self._on_save_site_group)
        group_row.addWidget(save_group)
        delete_group = QPushButton("Delete")
        delete_group.setToolTip("Delete the selected saved group")
        delete_group.clicked.connect(self._on_delete_site_group)
        group_row.addWidget(delete_group)
        layout.addLayout(group_row)
        self._refresh_site_group_combo()
        return group

    def _build_export_group(self) -> QGroupBox:
        self._export_group = QGroupBox("Export")
        group = self._export_group
        group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout = QVBoxLayout(group)

        self.format_txt = QRadioButton("TXT")
        self.format_csv = QRadioButton("CSV")
        self.format_ind = QRadioButton("IND")
        self.format_custom = QRadioButton("Custom")
        self.format_csv.setChecked(True)
        format_row = QHBoxLayout()
        for button in (
            self.format_txt,
            self.format_csv,
            self.format_ind,
            self.format_custom,
        ):
            format_row.addWidget(button)
        format_row.addStretch()
        layout.addLayout(format_row)
        self._bind_format_radio(self.format_txt, "txt")
        self._bind_format_radio(self.format_csv, "csv")
        self._bind_format_radio(self.format_ind, "ind")
        self._bind_format_radio(self.format_custom, "custom")
        self.format_custom.toggled.connect(self._toggle_custom_export_panel)

        self.export_all_formats_checkbox = QCheckBox("All formats (txt, csv, ind)")
        self.export_all_formats_checkbox.toggled.connect(self._toggle_format_selection)
        layout.addWidget(self.export_all_formats_checkbox)

        self.single_file_checkbox = QCheckBox("Single combined file")
        layout.addWidget(self.single_file_checkbox)

        self.custom_export_row = QWidget()
        custom_row = QHBoxLayout(self.custom_export_row)
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(6)
        custom_row.addWidget(QLabel("Delimiter:"))
        self.custom_delimiter_combo = QComboBox()
        self.custom_delimiter_combo.addItem("Comma (CSV)", ",")
        self.custom_delimiter_combo.addItem("Tab (TXT)", "\t")
        custom_row.addWidget(self.custom_delimiter_combo)
        self.choose_columns_button = QPushButton("Choose columns…")
        self.choose_columns_button.clicked.connect(self._on_choose_custom_columns)
        custom_row.addWidget(self.choose_columns_button)
        self.custom_columns_summary = QLabel()
        self.custom_columns_summary.setWordWrap(False)
        self.custom_columns_summary.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.custom_columns_summary.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        custom_row.addWidget(self.custom_columns_summary, stretch=1)
        self.custom_export_row.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self.custom_export_row)

        self.use_date_range_checkbox = QCheckBox("Custom date range")
        self.use_date_range_checkbox.setChecked(True)
        self.use_date_range_checkbox.toggled.connect(self._toggle_date_range)
        layout.addWidget(self.use_date_range_checkbox)

        dates = QHBoxLayout()
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setMinimumDate(QDate(2000, 1, 1))
        self.start_date_edit.setMaximumDate(QDate(2100, 12, 31))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setMinimumDate(QDate(2000, 1, 1))
        self.end_date_edit.setMaximumDate(QDate(2100, 12, 31))
        dates.addWidget(QLabel("From"))
        dates.addWidget(self.start_date_edit)
        dates.addWidget(QLabel("To"))
        dates.addWidget(self.end_date_edit)
        layout.addLayout(dates)

        quick_row = QHBoxLayout()
        self.quick_label = QLabel("Quick:")
        quick_row.addWidget(self.quick_label)
        self.quick_24h_button = QPushButton("Last 24 hours")
        self.quick_7d_button = QPushButton("Last 7 days")
        self.quick_30d_button = QPushButton("Last 30 days")
        self._quick_button_labels = {
            self.quick_24h_button: ("Last 24 hours", "24h"),
            self.quick_7d_button: ("Last 7 days", "7d"),
            self.quick_30d_button: ("Last 30 days", "30d"),
        }
        for days, button in ((1, self.quick_24h_button), (7, self.quick_7d_button), (30, self.quick_30d_button)):
            button.clicked.connect(lambda _checked=False, d=days: self._apply_date_quick_pick(d))
            quick_row.addWidget(button)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        out_row = QHBoxLayout()
        self.output_dir_label = QLabel()
        self.output_dir_label.setWordWrap(True)
        out_row.addWidget(self.output_dir_label, stretch=1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._choose_output_dir)
        out_row.addWidget(browse)
        layout.addLayout(out_row)

        self.export_preview_box = QGroupBox("Sample output")
        preview_layout = QVBoxLayout(self.export_preview_box)
        preview_layout.setContentsMargins(6, 4, 6, 4)
        preview_header = QHBoxLayout()
        self.preview_format_label = QLabel()
        self.preview_format_label.setStyleSheet("color: #555;")
        preview_header.addWidget(self.preview_format_label)
        preview_header.addStretch()
        self.preview_build_button = QPushButton("Build Preview")
        self.preview_build_button.setToolTip(
            "Load a sample from the API using the current format, sites, and date range"
        )
        self.preview_build_button.clicked.connect(self._refresh_export_preview)
        preview_header.addWidget(self.preview_build_button)
        preview_layout.addLayout(preview_header)
        self.export_preview = QTextEdit()
        self.export_preview.setReadOnly(True)
        self.export_preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        mono = QFont("Consolas")
        if not mono.exactMatch():
            mono = QFont("Courier New")
        mono.setPointSize(8)
        self.export_preview.setFont(mono)
        self.export_preview.setMinimumHeight(48)
        self.export_preview.setPlaceholderText(_PREVIEW_PLACEHOLDER)
        preview_layout.addWidget(self.export_preview)
        layout.addWidget(self.export_preview_box, stretch=1)

        return group

    def _bind_format_radio(self, button: QRadioButton, export_format: str) -> None:
        def on_toggled(checked: bool) -> None:
            if checked:
                self._active_export_format = export_format

        button.toggled.connect(on_toggled)

    def _on_site_selection_changed(self) -> None:
        if not self._applying_site_group:
            self._reset_site_group_combo_selection()
        self._clear_export_preview()

    def _export_format_from_ui(self) -> str:
        """Read the format radio that is checked (source of truth for preview/download)."""
        if self.format_ind.isChecked():
            return "ind"
        if self.format_txt.isChecked():
            return "txt"
        if self.format_custom.isChecked():
            return "custom"
        return "csv"

    def _sync_active_export_format_from_ui(self) -> None:
        self._active_export_format = self._export_format_from_ui()

    def _preview_sites(self) -> list[tuple[str, str]]:
        sites: list[tuple[str, str]] = []
        for item in self._selected_site_items():
            site = item.data(Qt.ItemDataRole.UserRole)
            sites.append((str(site.id), str(site.name)))
        return sites

    def _date_edit_value(self, widget: QDateEdit) -> QDate:
        coerced = _coerce_qdate(widget.date())
        if coerced != widget.date():
            widget.setDate(coerced)
        return coerced

    def _preview_date_range(self) -> tuple[str | None, str | None]:
        if self.use_date_range_checkbox.isChecked():
            return (
                self._qdate_to_iso(self._date_edit_value(self.start_date_edit)),
                self._qdate_to_iso(self._date_edit_value(self.end_date_edit)),
            )
        end = QDate.currentDate()
        start = end.addDays(-30)
        return self._qdate_to_iso(start), self._qdate_to_iso(end)

    @Slot()
    def _on_site_item_clicked(self, item: QListWidgetItem) -> None:
        """Plain click selects one site; Ctrl/Shift keep multi-select."""
        modifiers = QApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        self.sites_list.blockSignals(True)
        self.sites_list.clearSelection()
        item.setSelected(True)
        self.sites_list.setCurrentItem(item)
        self.sites_list.blockSignals(False)

    def _clear_export_preview(self) -> None:
        if not hasattr(self, "export_preview"):
            return
        self.export_preview.clear()
        self.preview_format_label.setText("")
        if self._can_show_export_preview():
            self.export_preview.setPlaceholderText(_PREVIEW_READY_PLACEHOLDER)
        else:
            self.export_preview.setPlaceholderText(_PREVIEW_PLACEHOLDER)
        self._update_preview_button_state()

    def _update_preview_button_state(self) -> None:
        if hasattr(self, "preview_build_button"):
            self.preview_build_button.setEnabled(self._can_show_export_preview())

    def _can_show_export_preview(self) -> bool:
        return self._client is not None and bool(self._selected_site_items())

    def _refresh_export_preview(self) -> None:
        if not hasattr(self, "export_preview"):
            return
        if not self._can_show_export_preview():
            self._clear_export_preview()
            return
        self.preview_build_button.setEnabled(False)
        self.export_preview.setPlaceholderText("")
        export_format = self._export_format_from_ui()
        self._active_export_format = export_format
        sites = self._preview_sites()
        site_label = ", ".join(code for code, _name in sites)
        if self.export_all_formats_checkbox.isChecked():
            self.preview_format_label.setText(
                f"Format: all — Sites: {site_label}"
            )
        else:
            self.preview_format_label.setText(
                f"Format: {export_format.upper()} — Sites: {site_label}"
            )
        if export_format == "ind":
            self.export_preview.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.export_preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        header = f"# Sites: {site_label}\n"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            need_site_info = (
                export_format == "ind"
                or self.export_all_formats_checkbox.isChecked()
                or (
                    export_format == "custom"
                    and needs_site_info(self._selected_custom_field_ids())
                )
            )
            start_date, end_date = self._preview_date_range()
            site_exports = fetch_preview_site_exports(
                self._client,
                sites,
                self._provider_id(),
                start_date,
                end_date,
                need_site_info=need_site_info,
            )
            text = render_export_preview(
                site_exports,
                export_format,
                custom_field_ids=self._selected_custom_field_ids(),
                custom_delimiter=str(self.custom_delimiter_combo.currentData() or ","),
                export_all_formats=self.export_all_formats_checkbox.isChecked(),
                header_comment=header,
            )
        except Exception as exc:  # noqa: BLE001
            text = f"{header}Preview error: {exc}"
        finally:
            QApplication.restoreOverrideCursor()
            self._update_preview_button_state()
        self.export_preview.document().setPlainText(text)
        self.export_preview.verticalScrollBar().setValue(0)

    def _update_export_preview_visibility(self) -> None:
        if not hasattr(self, "export_preview_box"):
            return
        tall_enough = self._export_group.height() >= 160 and self.height() >= 400
        self.export_preview_box.setVisible(tall_enough)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_export_preview_visibility()
        self._update_preview_button_state()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        width = self.width()
        height = self.height()
        compact = is_compact(width, height)
        narrow = is_narrow(width)

        if compact != self._compact_mode:
            self._compact_mode = compact
            scroll_widget = self._scroll_body.widget()
            if scroll_widget is not None:
                apply_root_font(scroll_widget, compact)
            self.download_button.setStyleSheet(download_button_style(compact))
            self.download_button.setText("Download" if compact else "Download tags")
            self.version_label.setStyleSheet(version_label_style(compact))
            self.custom_columns_summary.setStyleSheet(summary_label_style(compact))
            if self._logo_label is not None and self._logo_pixmap is not None:
                logo_h = 32 if compact else 40
                self._logo_label.setPixmap(
                    self._logo_pixmap.scaledToHeight(
                        logo_h, Qt.TransformationMode.SmoothTransformation
                    )
                )
            for button, (long_label, short_label) in self._quick_button_labels.items():
                button.setText(short_label if compact else long_label)

        self.quick_label.setVisible(not narrow)
        update_splitter_orientation(self._main_splitter, width, height)
        self._update_export_preview_visibility()

    def _apply_settings(self) -> None:
        s = self._settings
        self.provider_combo.blockSignals(True)
        idx = self.provider_combo.findData(s.provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.login_id_input.setText(s.login_id or s.api_email)
        self.save_credentials_checkbox.setChecked(s.save_credentials)
        self.skip_ssl_checkbox.setChecked(s.skip_ssl_verify)
        self.save_settings_checkbox.setChecked(s.save_ui_settings)

        if s.export_format == "txt":
            self.format_txt.setChecked(True)
        elif s.export_format == "ind":
            self.format_ind.setChecked(True)
        elif s.export_format == "custom":
            self.format_custom.setChecked(True)
        else:
            self.format_csv.setChecked(True)
        self._custom_export_field_ids = normalize_field_ids(
            s.custom_export_fields or None,
            s.provider,
        )
        self._update_custom_columns_summary()
        delim_idx = self.custom_delimiter_combo.findData(
            "\t" if s.custom_export_delimiter in ("\t", "tab") else ","
        )
        if delim_idx >= 0:
            self.custom_delimiter_combo.setCurrentIndex(delim_idx)
        self.export_all_formats_checkbox.setChecked(s.export_all_formats)
        self.single_file_checkbox.setChecked(s.single_file)
        self.use_date_range_checkbox.setChecked(s.use_custom_date_range)

        if s.start_date:
            parts = s.start_date.split("-")
            if len(parts) == 3:
                self.start_date_edit.setDate(
                    QDate(
                        _normalize_calendar_year(int(parts[0])),
                        int(parts[1]),
                        int(parts[2]),
                    )
                )
        else:
            self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        if s.end_date:
            parts = s.end_date.split("-")
            if len(parts) == 3:
                self.end_date_edit.setDate(
                    QDate(
                        _normalize_calendar_year(int(parts[0])),
                        int(parts[1]),
                        int(parts[2]),
                    )
                )
        else:
            self.end_date_edit.setDate(QDate.currentDate())

        self._toggle_date_range(s.use_custom_date_range)
        self._toggle_format_selection(s.export_all_formats)
        self._toggle_custom_export_panel(self.format_custom.isChecked())
        self.output_dir_label.setText(str(self._output_dir))
        self.provider_combo.blockSignals(False)
        self._sync_active_export_format_from_ui()

        if s.save_credentials and s.login_id:
            password = load_password(s.provider, s.login_id)
            if password:
                self.password_input.setText(password)

        self._clear_export_preview()
        self._refresh_site_group_combo()

    def _active_site_group_name(self) -> str:
        if not hasattr(self, "site_group_combo"):
            return self._settings.active_site_group
        name = self.site_group_combo.currentData()
        return str(name) if name else ""

    def _refresh_site_group_combo(self) -> None:
        if not hasattr(self, "site_group_combo"):
            return
        active = self._settings.active_site_group
        self.site_group_combo.blockSignals(True)
        self.site_group_combo.clear()
        self.site_group_combo.addItem("— choose group —", "")
        for name in sorted(self._settings.site_groups):
            self.site_group_combo.addItem(name, name)
        if active:
            index = self.site_group_combo.findData(active)
            if index >= 0:
                self.site_group_combo.setCurrentIndex(index)
            else:
                self.site_group_combo.setCurrentIndex(0)
        else:
            self.site_group_combo.setCurrentIndex(0)
        self.site_group_combo.blockSignals(False)

    def _reset_site_group_combo_selection(self) -> None:
        if not hasattr(self, "site_group_combo"):
            return
        if self.site_group_combo.currentIndex() == 0:
            return
        self.site_group_combo.blockSignals(True)
        self.site_group_combo.setCurrentIndex(0)
        self.site_group_combo.blockSignals(False)
        self._settings.active_site_group = ""

    def _select_sites_by_ids(self, site_ids: list[str]) -> None:
        wanted = {site_id.strip().upper() for site_id in site_ids if site_id}
        self._applying_site_group = True
        self.sites_list.blockSignals(True)
        self.sites_list.clearSelection()
        for index in range(self.sites_list.count()):
            item = self.sites_list.item(index)
            site = item.data(Qt.ItemDataRole.UserRole)
            if site.id in wanted:
                item.setSelected(True)
        self.sites_list.blockSignals(False)
        self._applying_site_group = False
        self._clear_export_preview()

    @Slot(int)
    def _on_site_group_changed(self, index: int) -> None:
        if index <= 0 or self._applying_site_group:
            return
        name = self.site_group_combo.currentData()
        if not name:
            return
        site_ids = self._settings.site_groups.get(str(name), [])
        if not site_ids:
            return
        self._settings.active_site_group = str(name)
        self._select_sites_by_ids(site_ids)
        missing = len(site_ids) - len(self._selected_site_ids())
        if missing > 0:
            QMessageBox.information(
                self,
                APP_NAME,
                f"Loaded group \"{name}\" ({len(self._selected_site_ids())} site(s)). "
                f"{missing} saved site(s) are not in your authorized list.",
            )

    @Slot()
    def _on_save_site_group(self) -> None:
        site_ids = self._selected_site_ids()
        if not site_ids:
            QMessageBox.warning(self, APP_NAME, "Select at least one site to save as a group.")
            return
        name, ok = QInputDialog.getText(
            self,
            "Save site group",
            "Group name:",
            text=self._active_site_group_name(),
        )
        if not ok:
            return
        label = name.strip()
        if not label:
            QMessageBox.warning(self, APP_NAME, "Enter a name for the group.")
            return
        if label in self._settings.site_groups and label != self._active_site_group_name():
            replace = QMessageBox.question(
                self,
                APP_NAME,
                f"A group named \"{label}\" already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if replace != QMessageBox.StandardButton.Yes:
                return
        self._settings.site_groups[label] = sorted(
            {site_id.strip().upper() for site_id in site_ids}
        )
        self._settings.active_site_group = label
        if self._settings.save_ui_settings:
            self._settings.save()
        self._refresh_site_group_combo()
        index = self.site_group_combo.findData(label)
        if index >= 0:
            self.site_group_combo.blockSignals(True)
            self.site_group_combo.setCurrentIndex(index)
            self.site_group_combo.blockSignals(False)

    @Slot()
    def _on_delete_site_group(self) -> None:
        name = self._active_site_group_name()
        if not name:
            QMessageBox.information(self, APP_NAME, "Choose a saved group to delete.")
            return
        confirm = QMessageBox.question(
            self,
            APP_NAME,
            f"Delete saved group \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._settings.site_groups.pop(name, None)
        if self._settings.active_site_group == name:
            self._settings.active_site_group = ""
        if self._settings.save_ui_settings:
            self._settings.save()
        self._refresh_site_group_combo()

    def _collect_settings(self) -> AppSettings:
        return AppSettings(
            provider=self.provider_combo.currentData(),
            login_id=self.login_id_input.text().strip().lower(),
            api_email="",
            save_credentials=self.save_credentials_checkbox.isChecked(),
            skip_ssl_verify=self.skip_ssl_checkbox.isChecked(),
            save_ui_settings=self.save_settings_checkbox.isChecked(),
            export_format=self._selected_export_format(),
            custom_export_fields=self._selected_custom_field_ids(),
            custom_export_delimiter=str(self.custom_delimiter_combo.currentData() or ","),
            export_all_formats=self.export_all_formats_checkbox.isChecked(),
            single_file=self.single_file_checkbox.isChecked(),
            use_custom_date_range=self.use_date_range_checkbox.isChecked(),
            start_date=self._qdate_to_iso(self._date_edit_value(self.start_date_edit)),
            end_date=self._qdate_to_iso(self._date_edit_value(self.end_date_edit)),
            selected_site_ids=self._selected_site_ids(),
            site_groups=dict(self._settings.site_groups),
            active_site_group=self._active_site_group_name(),
            output_dir=str(self._output_dir),
        )

    def _persist_settings(self) -> None:
        self._settings = self._collect_settings()
        if self._settings.save_ui_settings:
            self._settings.save()
        if self._settings.save_credentials and self._settings.login_id:
            try:
                save_password(
                    self._settings.provider,
                    self._settings.login_id,
                    self.password_input.text(),
                )
            except RuntimeError:
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "Could not save credentials (keyring unavailable).",
                )
        elif self._settings.login_id:
            delete_password(self._settings.provider, self._settings.login_id)

    def _selected_site_ids(self) -> list[str]:
        return [
            item.data(Qt.ItemDataRole.UserRole).id
            for item in self.sites_list.selectedItems()
            if not item.isHidden()
        ]

    def _selected_site_items(self) -> list[QListWidgetItem]:
        return [item for item in self.sites_list.selectedItems() if not item.isHidden()]

    @Slot(bool)
    def _toggle_date_range(self, enabled: bool) -> None:
        self.start_date_edit.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        for button in (
            self.quick_24h_button,
            self.quick_7d_button,
            self.quick_30d_button,
        ):
            button.setEnabled(enabled)

    def _apply_date_quick_pick(self, days: int) -> None:
        self.use_date_range_checkbox.setChecked(True)
        end = QDate.currentDate()
        if days == 1:
            start = end.addDays(-1)
        else:
            start = end.addDays(-(days - 1))
        self.start_date_edit.setDate(start)
        self.end_date_edit.setDate(end)

    @Slot(bool)
    def _toggle_format_selection(self, all_formats: bool) -> None:
        for button in (
            self.format_txt,
            self.format_csv,
            self.format_ind,
            self.format_custom,
        ):
            button.setEnabled(not all_formats)
        if all_formats:
            self._toggle_custom_export_panel(False)
        else:
            self._toggle_custom_export_panel(self.format_custom.isChecked())

    @Slot(bool)
    def _toggle_custom_export_panel(self, enabled: bool) -> None:
        use_custom = enabled and not self.export_all_formats_checkbox.isChecked()
        self.custom_export_row.setEnabled(use_custom)

    def _selected_custom_field_ids(self) -> list[str]:
        return list(self._custom_export_field_ids)

    def _update_custom_columns_summary(self) -> None:
        provider = self._provider_id()
        ids = normalize_field_ids(self._custom_export_field_ids, provider)
        self.custom_columns_summary.setText(summarize_custom_columns(ids, provider))
        labels = field_labels(ids, provider)
        self.custom_columns_summary.setToolTip(
            ", ".join(labels) if labels else "No columns selected"
        )

    @Slot()
    def _on_provider_changed(self) -> None:
        self._custom_export_field_ids = normalize_field_ids(
            self._custom_export_field_ids,
            self._provider_id(),
        )
        self._update_custom_columns_summary()

    @Slot()
    def _on_choose_custom_columns(self) -> None:
        dialog = CustomExportColumnsDialog(
            self._custom_export_field_ids,
            provider_id=self._provider_id(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._custom_export_field_ids = dialog.selected_field_ids()
        self._update_custom_columns_summary()

    def _selected_export_format(self) -> str:
        self._sync_active_export_format_from_ui()
        return self._active_export_format

    def _provider_id(self) -> str:
        return str(self.provider_combo.currentData())

    def _open_progress(self, title: str) -> ProgressDialog:
        dialog = ProgressDialog(title, self)
        dialog.show()
        QApplication.processEvents()
        return dialog

    def _set_busy(self, busy: bool) -> None:
        signed_in = self._client is not None
        self.sign_in_button.setEnabled(not busy)
        self.test_button.setEnabled(not busy and signed_in)
        self.download_button.setEnabled(not busy and signed_in)
        self.provider_combo.setEnabled(not busy)
        self.login_id_input.setEnabled(not busy)
        self.password_input.setEnabled(not busy)
        self.save_credentials_checkbox.setEnabled(not busy)
        self.skip_ssl_checkbox.setEnabled(not busy)

    @Slot()
    def _on_progress_dismissed(self) -> None:
        self._ignore_worker_result = True
        self._set_busy(False)

    def _start_worker(self, title: str, task) -> None:
        if self._worker and self._worker.isRunning():
            if self._progress:
                self._progress.log("Another operation is already running.")
            return

        self._ignore_worker_result = False
        self._progress = self._open_progress(title)
        self._progress.dismissed.connect(self._on_progress_dismissed)
        self._progress.log(title + "…")
        self._set_busy(True)
        self._worker = Worker(task)
        self._worker.finished_ok.connect(self._on_worker_ok)
        self._worker.finished_error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    @Slot()
    def _on_sign_in(self) -> None:
        email = self.login_id_input.text().strip().lower()
        password = self.password_input.text()
        if not email or not password:
            QMessageBox.warning(self, APP_NAME, "Enter your email and password.")
            return
        if not _is_valid_email(email):
            QMessageBox.warning(
                self,
                APP_NAME,
                "Enter a valid email address (for example, you@company.com).",
            )
            return

        verify_ssl = not self.skip_ssl_checkbox.isChecked()
        provider_id = self._provider_id()

        def task():
            client = api.BioLogicClient.login(
                email,
                password,
                verify_ssl=verify_ssl,
                provider_id=provider_id,
            )
            return client, client.get_sites()

        provider = get_provider(provider_id)
        token_url = provider.api_base_url.rstrip("/") + "/token/"

        self._start_worker("Sign In", task)
        if self._progress:
            self._progress.log(f"Portal: {self.provider_combo.currentText()}")
            self._progress.log(f"POST {token_url}")
            self._progress.log("Requesting API token…")

    @Slot()
    def _on_test_connection(self) -> None:
        if not self._client:
            QMessageBox.warning(self, APP_NAME, "Sign in first.")
            return

        def task():
            self._client.test_connection()
            return True

        self._start_worker("Test Connection", task)

    @Slot()
    def _on_download(self) -> None:
        if not self._client:
            QMessageBox.warning(self, APP_NAME, "Sign in first.")
            return

        selected_items = self._selected_site_items()
        if not selected_items:
            QMessageBox.warning(self, APP_NAME, "Select at least one site.")
            return

        selected_sites = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        export_format = self._selected_export_format()
        export_all = self.export_all_formats_checkbox.isChecked()
        single_file = self.single_file_checkbox.isChecked()
        custom_fields = self._selected_custom_field_ids()
        custom_delimiter = str(self.custom_delimiter_combo.currentData() or ",")

        if export_format == "custom" and not custom_fields:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Select at least one column for custom export, or click Default.",
            )
            return

        if self.use_date_range_checkbox.isChecked():
            start_q = self._date_edit_value(self.start_date_edit)
            end_q = self._date_edit_value(self.end_date_edit)
        else:
            end_q = QDate.currentDate()
            start_q = end_q.addDays(-30)
        if start_q > end_q:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"Start date must be on or before end date.\n\n"
                f"From: {self._qdate_to_iso(start_q)}\n"
                f"To: {self._qdate_to_iso(end_q)}",
            )
            return
        start_date = self._qdate_to_iso(start_q)
        end_date = self._qdate_to_iso(end_q)

        self._persist_settings()
        client = self._client
        output_dir = self._output_dir

        def task():
            reporter = self._progress.reporter() if self._progress else None
            return download_tags(
                client,
                selected_sites,
                export_format,
                single_file,
                output_dir,
                start_date,
                end_date,
                export_all,
                provider_id=self._settings.provider,
                custom_export_fields=custom_fields,
                custom_delimiter=custom_delimiter,
                progress=reporter,
            )

        self._start_worker("Download Tags", task)

    @staticmethod
    def _qdate_to_iso(value: QDate) -> str:
        value = _coerce_qdate(value)
        return date(value.year(), value.month(), value.day()).isoformat()

    @Slot(object)
    def _on_worker_ok(self, result) -> None:
        if self._ignore_worker_result or not self._progress:
            return

        if isinstance(result, tuple) and len(result) == 2:
            client, sites = result
            self._client = client
            self._sites = sites
            self._populate_sites(sites)
            self._persist_settings()
            self._clear_export_preview()
            method = "API token" if client.auth_method == "token" else "web session"
            portal = client.provider.label
            msg = f"Signed in to {portal} ({method}). {len(sites)} site(s) loaded."
            self._progress.finish(True, msg)
            return

        if result is True:
            self._progress.finish(True, "Connection test passed: Hello World!")
            return

        if isinstance(result, list):
            self._progress.finish(
                True, f"Download complete — {len(result)} file(s) in {self._output_dir}"
            )
            QMessageBox.information(
                self,
                APP_NAME,
                f"Exported {len(result)} file(s) to:\n{self._output_dir}",
            )

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        if self._ignore_worker_result:
            return
        if self._progress:
            self._progress.finish(False, message)
        if "401" in message or "403" in message or "token" in message.lower():
            self._client = None
            self._clear_export_preview()
        QMessageBox.critical(self, APP_NAME, message)

    @Slot()
    def _on_worker_finished(self) -> None:
        self._set_busy(False)

    @Slot(str)
    def _filter_sites_list(self, text: str) -> None:
        query = text.strip().lower()
        for index in range(self.sites_list.count()):
            item = self.sites_list.item(index)
            site = item.data(Qt.ItemDataRole.UserRole)
            label = item.text().lower()
            visible = (
                not query
                or query in label
                or query in site.id.lower()
                or query in site.name.lower()
            )
            item.setHidden(not visible)

    def _select_all_visible_sites(self) -> None:
        for index in range(self.sites_list.count()):
            item = self.sites_list.item(index)
            if not item.isHidden():
                item.setSelected(True)

    def _clear_visible_site_selection(self) -> None:
        for index in range(self.sites_list.count()):
            item = self.sites_list.item(index)
            if not item.isHidden():
                item.setSelected(False)

    def _populate_sites(self, sites: list[api.Site]) -> None:
        self.sites_list.blockSignals(True)
        self.sites_list.clear()
        self.sites_search_input.clear()
        saved = set(self._settings.selected_site_ids)
        active_group = self._settings.active_site_group
        group_ids: set[str] | None = None
        if active_group and active_group in self._settings.site_groups:
            group_ids = set(self._settings.site_groups[active_group])
        elif saved:
            group_ids = saved
        for site in sites:
            label = site.name if site.name.upper() != site.id else site.id
            item = QListWidgetItem(f"{label}  [{site.id}]")
            item.setData(Qt.ItemDataRole.UserRole, site)
            self.sites_list.addItem(item)
            if group_ids and site.id in group_ids:
                item.setSelected(True)
        self.sites_list.blockSignals(False)
        self._refresh_site_group_combo()
        self._clear_export_preview()

    @Slot()
    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Output folder", str(self._output_dir)
        )
        if directory:
            self._output_dir = Path(directory)
            self.output_dir_label.setText(directory)


def run() -> None:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    app.exec()
