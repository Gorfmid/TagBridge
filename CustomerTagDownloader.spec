# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — build with: python -m PyInstaller CustomerTagDownloader.spec

import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPEC).parent
entry = project_root / "customer_tag_downloader" / "__main__.py"

# Ensure Python runtime DLLs are bundled (fixes "Failed to load Python DLL" on other PCs).
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
    datas=[],
    hiddenimports=[
        "customer_tag_downloader.api",
        "customer_tag_downloader.export_data",
        "customer_tag_downloader.services",
        "customer_tag_downloader.ui.main_window",
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
    name="CustomerTagDownloader",
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
    name="CustomerTagDownloader",
)
