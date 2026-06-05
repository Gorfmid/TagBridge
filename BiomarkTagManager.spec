# =============================================================================
# File:        BiomarkTagManager.spec
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: PyInstaller spec (one-folder COLLECT layout).
# =============================================================================
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

project_root = Path(SPEC).parent
entry = project_root / "customer_tag_downloader" / "__main__.py"
resources = project_root / "customer_tag_downloader" / "resources"

python_home = Path(sys.base_prefix)
extra_binaries = []
for dll_name in (
    "python3.dll",
    f"python{sys.version_info.major}{sys.version_info.minor}.dll",
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
):
    dll_path = python_home / dll_name
    if dll_path.is_file():
        extra_binaries.append((str(dll_path), "."))

a = Analysis(
    [str(entry)],
    pathex=[str(project_root)],
    binaries=extra_binaries,
    datas=[
        (str(resources), "resources"),
        (str(project_root / "pyproject.toml"), "."),
    ],
    hiddenimports=[
        "customer_tag_downloader.api",
        "customer_tag_downloader.config",
        "customer_tag_downloader.export_data",
        "customer_tag_downloader.export_fields",
        "customer_tag_downloader.ind_event",
        "customer_tag_downloader.ind_site_map",
        "customer_tag_downloader.portal_site",
        "customer_tag_downloader.api_schema",
        "customer_tag_downloader.services",
        "customer_tag_downloader.settings",
        "customer_tag_downloader.logging_util",
        "customer_tag_downloader.ui.main_window",
        "customer_tag_downloader.ui.custom_export_dialog",
        "customer_tag_downloader.ui.responsive",
        "customer_tag_downloader.ui.progress_dialog",
        "keyring.backends.Windows",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BiomarkTagManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BiomarkTagManager",
)
