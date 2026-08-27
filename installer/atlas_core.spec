# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)


# PyInstaller exécute le .spec depuis son propre emplacement.
# SPECPATH pointe donc vers C:\Atlas\installer.
PROJECT_ROOT = os.path.abspath(
    os.path.join(
        SPECPATH,
        "..",
    )
)

MAIN_CORE = os.path.join(
    PROJECT_ROOT,
    "main_core.py",
)

SRC_ROOT = os.path.join(
    PROJECT_ROOT,
    "src",
)

WINDOWS_WAKEWORD_WORKER = os.path.join(
    SRC_ROOT,
    "atlas",
    "audio",
    "windows_wakeword.ps1",
)


datas = []
binaries = []
hiddenimports = []


# Worker local Windows Speech utilise par le mode wake word.
# Il doit etre present a cote du module atlas.audio.wakeword
# dans le bundle PyInstaller.
if os.path.isfile(
    WINDOWS_WAKEWORD_WORKER
):
    datas.append(
        (
            WINDOWS_WAKEWORD_WORKER,
            "atlas/audio",
        )
    )


# Packages comportant des imports / DLL dynamiques utilisés
# par Atlas Core.
for package_name in (
    "openai",
    "sounddevice",
    "pycaw",
    "comtypes",
):
    try:
        (
            package_datas,
            package_binaries,
            package_hidden,
        ) = collect_all(
            package_name
        )

        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden

    except Exception:
        # Une collecte partielle ne doit pas empêcher PyInstaller
        # de poursuivre son analyse standard.
        pass


hiddenimports += collect_submodules(
    "atlas"
)


analysis = Analysis(
    [
        MAIN_CORE,
    ],
    pathex=[
        PROJECT_ROOT,
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
    name="Atlas.Core",
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
    name="Atlas.Core",
)
