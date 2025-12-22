# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

# 让 spec 与当前工作目录无关：无论你从哪里执行 pyinstaller，都能找到入口脚本和资源文件
PROJECT_DIR = Path(os.path.abspath(os.getcwd()))

a = Analysis(
    [str(PROJECT_DIR / "main_modern.py")],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    # datas: (源文件路径, 打包后相对目录)
    datas=[
        (str(PROJECT_DIR / "头像.jpg"), "."),
        (str(PROJECT_DIR / "presets.json"), "."),
        # 你的 About 窗口会在运行时尝试读取 icon.ico/icon.png 来设置标题栏图标
        (str(PROJECT_DIR / "icon.ico"), "."),
        # 添加可能的备用头像文件（如果存在）
    ],
    hiddenimports=[],
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
    name="SmartHostsTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # GUI 程序建议关闭控制台窗口
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(PROJECT_DIR / "icon.ico")],
    # 如果你希望写 hosts 时自动弹出管理员权限请求，可取消下一行注释（仅 Windows 有效）
    # uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SmartHostsTool",
)
