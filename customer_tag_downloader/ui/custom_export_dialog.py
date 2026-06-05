# =============================================================================
# File:        custom_export_dialog.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Modal dialog to choose columns for custom export.
# =============================================================================
"""Popup column picker for custom CSV/TXT export."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from customer_tag_downloader.config import get_provider
from customer_tag_downloader.export_fields import (
    ExportField,
    default_custom_fields_for_provider,
    fields_for_provider,
    normalize_field_ids,
)

_SECTION_TAG_READS = "Tag reads"
_SECTION_SITE = "Site information"
_SECTION_DCA = "DCA / National Animal Database"


class CustomExportColumnsDialog(QDialog):
    """Select which fields to include in a custom export."""

    def __init__(
        self,
        field_ids: list[str] | None = None,
        *,
        provider_id: str = "biomark",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._provider_id = provider_id.strip().lower()
        portal = get_provider(self._provider_id).label
        self.setWindowTitle(f"Custom export columns — {portal}")
        self.setMinimumSize(480, 420)
        self.resize(520, 480)
        self.setModal(True)

        self._checkboxes: dict[str, QCheckBox] = {}
        self._catalog = fields_for_provider(self._provider_id)

        root = QVBoxLayout(self)
        root.addWidget(
            QLabel(
                f"Columns for <b>{portal}</b>. Only fields available on this portal are "
                "listed. The export file includes a header row with these names."
            )
        )
        root.addWidget(self._build_field_list(), stretch=1)

        presets = QHBoxLayout()
        for label, handler in (
            ("Default", self._apply_default),
            ("All", self._apply_all),
            ("None", self._apply_none),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            presets.addWidget(button)
        presets.addStretch()
        root.addLayout(presets)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        initial = field_ids if field_ids else default_custom_fields_for_provider(self._provider_id)
        self._set_checks(initial)

    def _build_field_list(self) -> QScrollArea:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setSpacing(8)

        sections: list[tuple[str, list[ExportField]]] = [
            (_SECTION_TAG_READS, []),
            (_SECTION_SITE, []),
            (_SECTION_DCA, []),
        ]
        dca_ids = {
            "ind_event_code",
            "ind_premise_id",
            "ind_timestamp",
            "ind_usain_flag",
            "ind_electronically_read",
        }
        site_ids = {"type_specie", "premises_number"}
        for field in self._catalog:
            if field.id in dca_ids:
                sections[2][1].append(field)
            elif field.id in site_ids:
                sections[1][1].append(field)
            else:
                sections[0][1].append(field)

        for title, fields in sections:
            if not fields:
                continue
            heading = QLabel(f"<b>{title}</b>")
            layout.addWidget(heading)
            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(4)
            for index, field in enumerate(fields):
                checkbox = QCheckBox(field.label)
                checkbox.setToolTip(field.description)
                self._checkboxes[field.id] = checkbox
                grid.addWidget(checkbox, index // 2, index % 2)
            layout.addWidget(grid_host)

        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def selected_field_ids(self) -> list[str]:
        return normalize_field_ids(
            [fid for fid, box in self._checkboxes.items() if box.isChecked()],
            self._provider_id,
        )

    def _apply_default(self) -> None:
        self._set_checks(default_custom_fields_for_provider(self._provider_id))

    def _apply_all(self) -> None:
        self._set_checks([f.id for f in self._catalog])

    def _apply_none(self) -> None:
        self._set_checks([])

    def _set_checks(self, field_ids: list[str]) -> None:
        wanted = set(normalize_field_ids(field_ids, self._provider_id))
        for fid, checkbox in self._checkboxes.items():
            checkbox.setChecked(fid in wanted)


def summarize_custom_columns(field_ids: list[str], provider_id: str = "biomark") -> str:
    """One-line summary for the main window (hover for full list)."""
    ids = normalize_field_ids(field_ids, provider_id)
    if not ids:
        return "(no columns)"
    count = len(ids)
    if count == 1:
        return f"1 column"
    return f"{count} columns"
