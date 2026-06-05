# =============================================================================
# File:        __main__.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Application entry point (python -m customer_tag_downloader).
# =============================================================================
"""Launch the PySide6 GUI (``python -m customer_tag_downloader``)."""

from customer_tag_downloader.ui.main_window import run

if __name__ == "__main__":
    run()
