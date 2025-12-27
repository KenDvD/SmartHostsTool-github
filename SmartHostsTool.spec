# -*- mode: python ; coding: utf-8 -*-

import sys
import os

# 获取项目根目录
try:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    PROJECT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

a = Analysis(
    [os.path.join(PROJECT_DIR, 'main.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        (os.path.abspath('头像.jpg'), '.'),
        (os.path.abspath('presets.json'), '.'),
        (os.path.abspath('icon.ico'), '.'),
        (os.path.abspath('utils.py'), '.'),
        (os.path.abspath('config.py'), '.'),
        (os.path.abspath('hosts_file.py'), '.'),
        (os.path.abspath('services.py'), '.'),
        (os.path.abspath('main_window.py'), '.'),
        (os.path.abspath('ui_visuals.py'), '.'),
        (os.path.abspath('about_window.py'), '.'),
    ],
    hiddenimports=[
        'ttkbootstrap',
        'ttkbootstrap.constants',
        'ttkbootstrap.tooltip',
        'ttkbootstrap.toast',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageOps',
        'PIL.ImageDraw',
        'PIL.ImageFilter',
        'requests',
        'urllib3',
        'platformdirs',
        'asyncio',
        'concurrent.futures',
        'threading',
        'socket',
        'ssl',
        'ipaddress',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'ctypes',
        'argparse',
        'webbrowser',
        'dataclasses',
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
    name='SmartHostsTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartHostsTool',
)
