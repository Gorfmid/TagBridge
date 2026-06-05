# =============================================================================
# File:        progress_dialog.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Modal progress and log dialog for background work.
# =============================================================================
"""
Modal progress and log window for sign-in, connection test, and download.

Emits ``dismissed`` when the user cancels or closes the dialog so the main window
can re-enable controls without waiting for the background thread to finish.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from customer_tag_downloader import logging_util


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "calculating…"
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class ProgressDialog(QDialog):
    log_message = Signal(str)
    dismissed = Signal()
    _download_begin = Signal(list, str, str)
    _download_site = Signal(dict)
    _download_overall = Signal(str, float, object)

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 360)
        self.setModal(True)
        self._working = True
        self._dismissed_emitted = False
        self._site_lines: list[str] = []

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Working…")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

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
        self._download_begin.connect(self._on_download_begin)
        self._download_site.connect(self._on_download_site)
        self._download_overall.connect(self._on_download_overall)
        logging_util.start_session_log()

    def log(self, message: str) -> None:
        self.log_message.emit(message)
        logging_util.append_log(message)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def finish(self, success: bool, message: str) -> None:
        self._working = False
        self.set_status(message)
        if success:
            self.progress_bar.setValue(100)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.close_button.setEnabled(True)
        if success:
            self.log(message)
        else:
            self.log(f"ERROR: {message}")

    def reporter(self) -> DownloadProgressReporter:
        return DownloadProgressReporter(self)

    def _emit_download_begin(
        self,
        sites: list[tuple[str, str]],
        start_date: str,
        end_date: str,
    ) -> None:
        self._download_begin.emit(sites, start_date, end_date)

    def _emit_download_site(self, **payload) -> None:
        self._download_site.emit(payload)

    def _emit_download_overall(
        self,
        message: str,
        percent: float,
        eta_seconds: float | None,
    ) -> None:
        self._download_overall.emit(message, percent, eta_seconds)

    def _on_download_begin(
        self,
        sites: list[tuple[str, str]],
        start_date: str,
        end_date: str,
    ) -> None:
        self._site_lines = [f"[ .... ] {site_id} — waiting" for site_id, _name in sites]
        self.log_view.clear()
        self.log(f"Date range: {start_date} to {end_date}")
        self.log(f"Sites: {len(sites)}")
        self.log("")
        for line in self._site_lines:
            self.log(line)
        self.progress_bar.setValue(0)
        self.set_status(f"Downloading tags… 0/{len(sites)} sites")

    def _on_download_overall(
        self,
        message: str,
        percent: float,
        eta_seconds: float | None,
    ) -> None:
        pct = max(0, min(100, int(round(percent))))
        self.progress_bar.setValue(pct)
        eta_text = _format_duration(eta_seconds)
        self.set_status(f"{message} — {pct}% — about {eta_text} remaining")

    def _on_download_site(self, payload: dict) -> None:
        index = int(payload["index"])
        total = int(payload["total"])
        site_id = str(payload["site_id"])
        phase = str(payload.get("phase", "downloading"))
        percent = float(payload.get("percent", 0))
        eta_seconds = payload.get("eta_seconds")
        pct = max(0, min(100, int(round(percent))))
        self.progress_bar.setValue(pct)

        if not self._site_lines and total > 0:
            self._site_lines = [f"[ .... ] site {i + 1} — waiting" for i in range(total)]

        if 0 <= index < len(self._site_lines):
            if phase == "downloading":
                site_name = str(payload.get("site_name") or site_id)
                eta_text = _format_duration(eta_seconds)
                self._site_lines[index] = (
                    f"[ >>> ] {site_id} — downloading {site_name}… ({pct}%, ~{eta_text} left)"
                )
                self.set_status(
                    f"Downloading {site_id} ({index + 1}/{total}) — {pct}% — ~{eta_text} remaining"
                )
            elif phase == "chunk":
                chunk_index = int(payload.get("chunk_index") or 1)
                chunk_total = int(payload.get("chunk_total") or 1)
                eta_text = _format_duration(eta_seconds)
                self._site_lines[index] = (
                    f"[ >>> ] {site_id} — chunk {chunk_index}/{chunk_total} ({pct}%, ~{eta_text} left)"
                )
                self.set_status(
                    f"{site_id} chunk {chunk_index}/{chunk_total} ({index + 1}/{total}) — "
                    f"{pct}% — ~{eta_text} remaining"
                )
            elif phase == "done":
                tag_count = int(payload.get("tag_count") or 0)
                elapsed = float(payload.get("elapsed_seconds") or 0)
                paths = payload.get("paths") or []
                path_names = ", ".join(str(path).split("\\")[-1] for path in paths)
                if path_names:
                    detail = f"{tag_count:,} tags — {path_names}"
                else:
                    detail = f"{tag_count:,} tags downloaded"
                self._site_lines[index] = (
                    f"[ OK  ] {site_id} — {detail} ({_format_duration(elapsed)})"
                )
                eta_text = _format_duration(eta_seconds)
                self.set_status(
                    f"Finished {site_id} ({index + 1}/{total}) — {pct}% — ~{eta_text} remaining"
                )

        self._refresh_site_lines()

    def _refresh_site_lines(self) -> None:
        if not self._site_lines:
            return
        lines = self.log_view.toPlainText().splitlines()
        header_count = 0
        for line in lines:
            if line.startswith("[ "):
                break
            header_count += 1
        header = lines[:header_count]
        self.log_view.setPlainText("\n".join(header + self._site_lines))
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

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


class DownloadProgressReporter:
    """Thread-safe download progress updates for the worker thread."""

    def __init__(self, dialog: ProgressDialog) -> None:
        self._dialog = dialog

    def begin(self, sites: list[tuple[str, str]], start_date: str, end_date: str) -> None:
        self._dialog._emit_download_begin(sites, start_date, end_date)

    def site_started(
        self,
        index: int,
        total: int,
        site_id: str,
        site_name: str,
        *,
        percent: float,
        eta_seconds: float | None,
    ) -> None:
        self._dialog._emit_download_site(
            index=index,
            total=total,
            site_id=site_id,
            site_name=site_name,
            phase="downloading",
            percent=percent,
            eta_seconds=eta_seconds,
        )

    def site_chunk(
        self,
        index: int,
        total: int,
        site_id: str,
        chunk_index: int,
        chunk_total: int,
        *,
        percent: float,
        eta_seconds: float | None,
    ) -> None:
        self._dialog._emit_download_site(
            index=index,
            total=total,
            site_id=site_id,
            phase="chunk",
            percent=percent,
            eta_seconds=eta_seconds,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )

    def site_saved(
        self,
        index: int,
        total: int,
        site_id: str,
        tag_count: int,
        paths: list[str],
        elapsed_seconds: float,
        *,
        percent: float,
        eta_seconds: float | None,
    ) -> None:
        self._dialog._emit_download_site(
            index=index,
            total=total,
            site_id=site_id,
            phase="done",
            percent=percent,
            eta_seconds=eta_seconds,
            tag_count=tag_count,
            paths=paths,
            elapsed_seconds=elapsed_seconds,
        )

    def combining(self, *, percent: float) -> None:
        self._dialog._emit_download_overall("Combining into a single file", percent, None)
