"""
Modal progress and log window for sign-in, connection test, and download.

Emits ``dismissed`` when the user cancels or closes the dialog so the main window
can re-enable controls without waiting for the background thread to finish.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from customer_tag_downloader import logging_util


class ProgressDialog(QDialog):
    log_message = Signal(str)
    dismissed = Signal()

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(520, 320)
        self.setModal(True)
        self._working = True
        self._dismissed_emitted = False

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Working…")
        layout.addWidget(self.status_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        mono = QFont("Consolas")
        if not mono.exactMatch():
            mono = QFont("Courier New")
        self.log_view.setFont(mono)
        layout.addWidget(self.log_view)

        row = QHBoxLayout()
        row.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        row.addWidget(self.cancel_button)
        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        row.addWidget(self.close_button)
        layout.addLayout(row)

        self.log_message.connect(self._append)
        logging_util.start_session_log()

    def log(self, message: str) -> None:
        self.log_message.emit(message)
        logging_util.append_log(message)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def finish(self, success: bool, message: str) -> None:
        self._working = False
        self.set_status(message)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.close_button.setEnabled(True)
        if success:
            self.log(message)
        else:
            self.log(f"ERROR: {message}")

    def _emit_dismissed(self) -> None:
        if not self._dismissed_emitted:
            self._dismissed_emitted = True
            self.dismissed.emit()

    def _on_cancel(self) -> None:
        if self._working:
            self.log("Cancelled.")
            self._working = False
        self._emit_dismissed()
        self.reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._working:
            self.log("Cancelled.")
            self._working = False
        self._emit_dismissed()
        super().closeEvent(event)

    def _append(self, message: str) -> None:
        self.log_view.append(message)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )
