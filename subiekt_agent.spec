# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None

# Szukamy cloudflared.exe na maszynie dewelopera, żeby dołączyć jeśli istnieje
binary_datas = []
dev_cf_path = Path("installer") / "bin" / "cloudflared.exe"
if dev_cf_path.exists():
    binary_datas.append((str(dev_cf_path), '.'))
else:
    # sprawdzamy w AppData
    appdata_cf = Path(os.getenv("APPDATA", "")) / "SuppSalesAgent" / "bin" / "cloudflared.exe"
    if appdata_cf.exists():
        binary_datas.append((str(appdata_cf), '.'))

# Szukamy ngrok.exe na maszynie dewelopera lub w AppData
dev_ngrok_path = Path("installer") / "bin" / "ngrok.exe"
if dev_ngrok_path.exists():
    binary_datas.append((str(dev_ngrok_path), '.'))
else:
    appdata_ngrok = Path(os.getenv("APPDATA", "")) / "SuppSalesAgent" / "bin" / "ngrok.exe"
    if appdata_ngrok.exists():
        binary_datas.append((str(appdata_ngrok), '.'))

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=binary_datas,
    datas=[
        ('app/gui/assets/icon.png', 'app/gui/assets'),
        ('app/static', 'app/static'),
        ('config.json', '.'),
    ],
    hiddenimports=[
        'win32timezone',
        'pystray._win32'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SuppSalesAgentApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/gui/assets/icon.png'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SuppSalesAgentApp',
)
