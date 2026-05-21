"""Session log file writer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from customer_tag_downloader.config import logs_dir

_session_log: Path | None = None


def start_session_log() -> Path:
    global _session_log
    logs_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _session_log = logs_dir() / f"session_{stamp}.log"
    _session_log.write_text(
        f"Biomark Tag Manager log started {datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )
    return _session_log


def append_log(message: str) -> None:
    global _session_log
    if _session_log is None:
        start_session_log()
    assert _session_log is not None
    line = f"{datetime.now().strftime('%H:%M:%S')}  {message}\n"
    with _session_log.open("a", encoding="utf-8") as handle:
        handle.write(line)


def current_log_path() -> Path | None:
    return _session_log
