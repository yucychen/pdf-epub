# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: 同时构建 CLI 与 GUI,带应用图标"""
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

if sys.platform.startswith("win"):
    _icon = os.path.join("assets", "icon.ico")
elif sys.platform == "darwin":
    _icon = os.path.join("assets", "icon.icns")
else:
    _icon = os.path.join("assets", "icon.png")
icon_arg = _icon if os.path.exists(_icon) else None

hidden, datas, binaries = [], [], []
for pkg in ("fitz", "ebooklib"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

cli_a = Analysis(["pdf2epub.py"], pathex=[], binaries=binaries, datas=datas,
                 hiddenimports=hidden, hookspath=[], runtime_hooks=[],
                 excludes=[], cipher=block_cipher, noarchive=False)
cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)
cli_exe = EXE(cli_pyz, cli_a.scripts, [], exclude_binaries=True,
              name="pdf2epub", console=True, icon=icon_arg)

gui_a = Analysis(["pdf2epub_gui.py"], pathex=[], binaries=binaries, datas=datas,
                 hiddenimports=hidden + ["pdf2epub"], hookspath=[],
                 runtime_hooks=[], excludes=[], cipher=block_cipher,
                 noarchive=False)
gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)
gui_exe = EXE(gui_pyz, gui_a.scripts, [], exclude_binaries=True,
              name="pdf2epub-gui", console=False, icon=icon_arg)

coll = COLLECT(
    cli_exe, cli_a.binaries, cli_a.zipfiles, cli_a.datas,
    gui_exe, gui_a.binaries, gui_a.zipfiles, gui_a.datas,
    strip=False, upx=True, upx_exclude=[], name="pdf2epub",
)
