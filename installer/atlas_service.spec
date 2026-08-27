# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)


PROJECT_ROOT = os.path.abspath(
    os.path.join(
        SPECPATH,
        "..",
    )
)

SERVICE_ROOT = os.path.join(
    PROJECT_ROOT,
    "service",
)

SRC_ROOT = os.path.join(
    PROJECT_ROOT,
    "src",
)

WINDOWS_SERVICE = os.path.join(
    SERVICE_ROOT,
    "windows_service.py",
)


datas = []
binaries = []
hiddenimports = [
    "atlas_service",
    "pipe_server",
]


# AtlasService utilise psutil pour valider et arrêter certains
# processus. collect_all couvre ses imports et binaires natifs.
try:
    (
        package_datas,
        package_binaries,
        package_hidden,
    ) = collect_all(
        "psutil"
    )

    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

except Exception:
    pass


# Les modules atlas.service sont peu nombreux, mais certains sont
# chargés indirectement par le client / la sécurité du Named Pipe.
hiddenimports += collect_submodules(
    "atlas.service"
)


analysis = Analysis(
    [
        WINDOWS_SERVICE,
    ],
    pathex=[
        PROJECT_ROOT,
        SERVICE_ROOT,
        SRC_ROOT,
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


pyz = PYZ(
    analysis.pure
)


exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Atlas.Service",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
)


collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Atlas.Service",
)
