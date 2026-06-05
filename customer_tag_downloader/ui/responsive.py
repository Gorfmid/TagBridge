# =============================================================================
# File:        responsive.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Window-size breakpoints and compact UI adjustments.
# =============================================================================
"""Helpers to adapt layout and fonts when the main window is resized."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QSplitter, QWidget

# Below these sizes the UI switches to compact layout / smaller fonts.
COMPACT_WIDTH = 820
COMPACT_HEIGHT = 500
NARROW_WIDTH = 680

FONT_NORMAL_PT = 9
FONT_COMPACT_PT = 8


def is_compact(width: int, height: int) -> bool:
    return width < COMPACT_WIDTH or height < COMPACT_HEIGHT


def is_narrow(width: int) -> bool:
    return width < NARROW_WIDTH


def apply_root_font(widget: QWidget, compact: bool) -> None:
    font = QFont(widget.font())
    font.setPointSize(FONT_COMPACT_PT if compact else FONT_NORMAL_PT)
    widget.setFont(font)


def update_splitter_orientation(splitter: QSplitter, width: int, height: int) -> None:
    vertical = is_compact(width, height)
    orientation = Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal
    if splitter.orientation() != orientation:
        splitter.setOrientation(orientation)
        if vertical:
            splitter.setSizes([320, 240])
        else:
            splitter.setSizes([380, 460])


def download_button_style(compact: bool) -> str:
    font_px = 11 if compact else 12
    pad_v = 3 if compact else 4
    pad_h = 10 if compact else 14
    return (
        f"QPushButton {{ background-color: #2e7d32; color: white; font-size: {font_px}px; "
        f"font-weight: 600; border-radius: 4px; padding: {pad_v}px {pad_h}px; "
        f"min-height: 0; max-height: 28px; }}"
        "QPushButton:hover { background-color: #1b5e20; }"
        "QPushButton:disabled { background-color: #9e9e9e; }"
    )


def summary_label_style(compact: bool) -> str:
    px = 10 if compact else 11
    return f"color: #555; font-size: {px}px;"


def version_label_style(compact: bool) -> str:
    px = 9 if compact else 10
    return f"color: #666; font-size: {px}px;"


def sites_list_style() -> str:
    return (
        "QListWidget::item:selected {"
        " background-color: #c8e6c9; color: #1b5e20;"
        "}"
        "QListWidget::item:selected:!active {"
        " background-color: #c8e6c9; color: #1b5e20;"
        "}"
    )
