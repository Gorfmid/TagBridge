"""
Biomark Tag Manager — PySide6 main window.

Layout: header (logo), login, sites + export panels, download footer with version.
Network work runs on ``Worker`` (QThread); see ``ProgressDialog`` for status/logs.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
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
from customer_tag_downloader.services import download_tags
from customer_tag_downloader.ui.progress_dialog import ProgressDialog

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


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
        self.setMinimumSize(780, 480)
        self.resize(860, 520)
        self._build_ui()
        self._apply_settings()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        root.addWidget(self._build_header())
        root.addWidget(self._build_login_group())

        middle = QHBoxLayout()
        middle.addWidget(self._build_sites_group(), stretch=1)
        middle.addWidget(self._build_export_group(), stretch=1)
        root.addLayout(middle, stretch=1)

        footer = QHBoxLayout()
        self.version_label = QLabel(f"Version {app_version()}")
        self.version_label.setStyleSheet("color: #666; font-size: 11px;")
        footer.addWidget(self.version_label)
        footer.addStretch()
        self.download_button = QPushButton("Download Tags")
        self.download_button.setMinimumSize(180, 48)
        self.download_button.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-size: 14px; "
            "font-weight: bold; border-radius: 6px; padding: 8px 20px; }"
            "QPushButton:hover { background-color: #1b5e20; }"
            "QPushButton:disabled { background-color: #9e9e9e; }"
        )
        self.download_button.clicked.connect(self._on_download)
        footer.addWidget(self.download_button)
        root.addLayout(footer)

    def _build_header(self) -> QWidget:
        row = QHBoxLayout()
        widget = QWidget()
        widget.setLayout(row)

        logo_path = resource_path("biomark_logo.png")
        if logo_path.is_file():
            logo = QLabel()
            pixmap = QPixmap(str(logo_path))
            logo.setPixmap(pixmap.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation))
            row.addWidget(logo)

        row.addStretch()
        return widget

    def _build_login_group(self) -> QGroupBox:
        group = QGroupBox("Login")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        self.provider_combo = QComboBox()
        for provider in PROVIDERS.values():
            self.provider_combo.addItem(provider.label, provider.id)
        grid.addWidget(QLabel("Portal:"), 0, 0)
        grid.addWidget(self.provider_combo, 0, 1)

        self.login_id_input = QLineEdit()
        self.login_id_input.setPlaceholderText("Email address")
        grid.addWidget(QLabel("Email:"), 0, 2)
        grid.addWidget(self.login_id_input, 0, 3)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        grid.addWidget(QLabel("Password:"), 1, 0)
        grid.addWidget(self.password_input, 1, 1, 1, 3)

        opts = QHBoxLayout()
        self.save_credentials_checkbox = QCheckBox("Save credentials")
        self.skip_ssl_checkbox = QCheckBox("Skip SSL verify")
        self.save_settings_checkbox = QCheckBox("Remember settings")
        self.save_settings_checkbox.setChecked(True)
        opts.addWidget(self.save_credentials_checkbox)
        opts.addWidget(self.skip_ssl_checkbox)
        opts.addWidget(self.save_settings_checkbox)
        opts.addStretch()
        grid.addLayout(opts, 2, 0, 1, 2)

        buttons = QHBoxLayout()
        self.sign_in_button = QPushButton("Sign In")
        self.sign_in_button.clicked.connect(self._on_sign_in)
        buttons.addWidget(self.sign_in_button)
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._on_test_connection)
        buttons.addWidget(self.test_button)
        buttons.addStretch()
        grid.addLayout(buttons, 2, 2, 1, 2)

        return group

    def _build_sites_group(self) -> QGroupBox:
        group = QGroupBox("Sites")
        layout = QVBoxLayout(group)
        self.sites_list = QListWidget()
        self.sites_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
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
        return group

    def _build_export_group(self) -> QGroupBox:
        group = QGroupBox("Export")
        layout = QVBoxLayout(group)

        format_row = QHBoxLayout()
        self.format_group = QButtonGroup(self)
        self.format_txt = QRadioButton("TXT")
        self.format_csv = QRadioButton("CSV")
        self.format_ind = QRadioButton("IND")
        self.format_csv.setChecked(True)
        for button in (self.format_txt, self.format_csv, self.format_ind):
            self.format_group.addButton(button)
            format_row.addWidget(button)
        format_row.addStretch()
        layout.addLayout(format_row)

        self.export_all_formats_checkbox = QCheckBox("All formats (txt, csv, ind)")
        self.export_all_formats_checkbox.toggled.connect(self._toggle_format_selection)
        layout.addWidget(self.export_all_formats_checkbox)

        self.single_file_checkbox = QCheckBox("Single combined file")
        layout.addWidget(self.single_file_checkbox)

        self.use_date_range_checkbox = QCheckBox("Custom date range")
        self.use_date_range_checkbox.setChecked(True)
        self.use_date_range_checkbox.toggled.connect(self._toggle_date_range)
        layout.addWidget(self.use_date_range_checkbox)

        dates = QHBoxLayout()
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        dates.addWidget(QLabel("From"))
        dates.addWidget(self.start_date_edit)
        dates.addWidget(QLabel("To"))
        dates.addWidget(self.end_date_edit)
        layout.addLayout(dates)

        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Quick:"))
        self.quick_24h_button = QPushButton("Last 24 hours")
        self.quick_7d_button = QPushButton("Last 7 days")
        self.quick_30d_button = QPushButton("Last 30 days")
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
        layout.addStretch()
        return group

    def _apply_settings(self) -> None:
        s = self._settings
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
        else:
            self.format_csv.setChecked(True)
        self.export_all_formats_checkbox.setChecked(s.export_all_formats)
        self.single_file_checkbox.setChecked(s.single_file)
        self.use_date_range_checkbox.setChecked(s.use_custom_date_range)

        if s.start_date:
            parts = s.start_date.split("-")
            if len(parts) == 3:
                self.start_date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
        else:
            self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        if s.end_date:
            parts = s.end_date.split("-")
            if len(parts) == 3:
                self.end_date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
        else:
            self.end_date_edit.setDate(QDate.currentDate())

        self._toggle_date_range(s.use_custom_date_range)
        self._toggle_format_selection(s.export_all_formats)
        self.output_dir_label.setText(str(self._output_dir))

        if s.save_credentials and s.login_id:
            password = load_password(s.provider, s.login_id)
            if password:
                self.password_input.setText(password)

    def _collect_settings(self) -> AppSettings:
        return AppSettings(
            provider=self.provider_combo.currentData(),
            login_id=self.login_id_input.text().strip().lower(),
            api_email="",
            save_credentials=self.save_credentials_checkbox.isChecked(),
            skip_ssl_verify=self.skip_ssl_checkbox.isChecked(),
            save_ui_settings=self.save_settings_checkbox.isChecked(),
            export_format=self._selected_export_format(),
            export_all_formats=self.export_all_formats_checkbox.isChecked(),
            single_file=self.single_file_checkbox.isChecked(),
            use_custom_date_range=self.use_date_range_checkbox.isChecked(),
            start_date=self._qdate_to_iso(self.start_date_edit.date()),
            end_date=self._qdate_to_iso(self.end_date_edit.date()),
            selected_site_ids=self._selected_site_ids(),
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
        for button in (self.format_txt, self.format_csv, self.format_ind):
            button.setEnabled(not all_formats)

    def _selected_export_format(self) -> str:
        if self.format_txt.isChecked():
            return "txt"
        if self.format_ind.isChecked():
            return "ind"
        return "csv"

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

        if self.use_date_range_checkbox.isChecked():
            start_q = self.start_date_edit.date()
            end_q = self.end_date_edit.date()
        else:
            end_q = QDate.currentDate()
            start_q = end_q.addDays(-30)
        if start_q > end_q:
            QMessageBox.warning(self, APP_NAME, "Start date must be on or before end date.")
            return
        start_date = self._qdate_to_iso(start_q)
        end_date = self._qdate_to_iso(end_q)

        self._persist_settings()
        client = self._client
        output_dir = self._output_dir

        def task():
            return download_tags(
                client,
                selected_sites,
                export_format,
                single_file,
                output_dir,
                start_date,
                end_date,
                export_all,
            )

        self._start_worker("Download Tags", task)

    @staticmethod
    def _qdate_to_iso(value: QDate) -> str:
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
            method = "API token" if client.auth_method == "token" else "web session"
            portal = client.provider.label
            msg = f"Signed in to {portal} ({method}). {len(sites)} site(s) loaded."
            self._progress.finish(True, msg)
            return

        if result is True:
            self._progress.finish(True, "Connection test passed: Hello World!")
            return

        if isinstance(result, list):
            for path in result:
                self._progress.log(f"Saved: {path}")
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
        self.sites_list.clear()
        self.sites_search_input.clear()
        saved = set(self._settings.selected_site_ids)
        for site in sites:
            label = site.name if site.name.upper() != site.id else site.id
            item = QListWidgetItem(f"{label}  [{site.id}]")
            item.setData(Qt.ItemDataRole.UserRole, site)
            self.sites_list.addItem(item)
            if site.id in saved or not saved:
                item.setSelected(True)

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
