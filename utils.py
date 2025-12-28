# -*- coding: utf-8 -*-
"""
utils.py

小工具集合：
- resource_path：兼容 PyInstaller 打包后的资源路径
- user_data_path：把可写配置/数据放到用户目录（避免写到资源目录）
- atomic_write_*：原子写入，避免写到一半导致文件损坏
- is_admin / check_and_elevate / restart_as_admin：Windows 管理员权限相关
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, List, Optional


# ---------------------------------------------------------------------
# 资源路径（兼容 PyInstaller）
# ---------------------------------------------------------------------
_BASE_PATH = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    """返回资源绝对路径，兼容 PyInstaller 与源码运行。"""
    return os.path.join(_BASE_PATH, *parts)


# ---------------------------------------------------------------------
# 用户数据目录（可写）
# ---------------------------------------------------------------------
def _fallback_user_data_dir(app_name: str) -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, app_name)
    os.makedirs(path, exist_ok=True)
    return path


def user_data_dir(app_name: str, app_author: Optional[str] = None) -> str:
    """获取用户数据目录（可写）。
    优先使用 platformdirs（若存在）；否则回退到 %LOCALAPPDATA%/app_name。
    """
    try:
        from platformdirs import user_data_dir as _user_data_dir  # type: ignore
        try:
            # platformdirs 新版支持 ensure_exists
            path = _user_data_dir(app_name, app_author or app_name, ensure_exists=True)
        except TypeError:
            # 兼容旧版 platformdirs
            path = _user_data_dir(app_name, app_author or app_name)
            os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        return _fallback_user_data_dir(app_name)


def user_data_path(app_name: str, *parts: str, app_author: Optional[str] = None) -> str:
    """拼接用户数据目录下的文件路径。"""
    return os.path.join(user_data_dir(app_name, app_author=app_author), *parts)


# ---------------------------------------------------------------------
# Windows 管理员权限
# ---------------------------------------------------------------------
def is_admin(probe_path: Optional[str] = None) -> bool:
    """检查当前进程是否拥有管理员权限。

    - Windows：优先 IsUserAnAdmin；若返回 False，可选再对 probe_path 做一次“写入探测”。
    - 非 Windows：默认 True（保持跨平台容错，不阻塞 GUI）。
    """
    if sys.platform != "win32":
        return True

    try:
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "shell32"):
            if ctypes.windll.shell32.IsUserAnAdmin():
                return True
    except Exception:
        pass

    # 补充探测：使用临时文件测试写入权限，避免修改原文件
    if probe_path:
        try:
            import os
            probe_dir = os.path.dirname(probe_path)
            if probe_dir:
                test_path = os.path.join(probe_dir, f".admin_test_{os.getpid()}.tmp")
                with open(test_path, "w") as f:
                    f.write("test")
                os.remove(test_path)
                return True
        except Exception:
            return False

    return False


def _windows_message_box(text: str, title: str = "权限不足") -> None:
    """使用 Win32 MessageBox 弹窗（避免依赖 tkinter）。"""
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        # 最差情况：打印到控制台
        print(f"[{title}] {text}")


def check_and_elevate() -> bool:
    """启动时检查并请求管理员权限（Windows）。

    成功：返回 True
    若需提权：会触发 UAC 并退出当前进程（sys.exit）
    失败：弹窗提示并退出（sys.exit）
    """
    if sys.platform != "win32":
        return True

    # 尝试用 hosts 路径做探测（更贴近真实需求）
    try:
        from config import HOSTS_PATH  # 延迟导入，避免循环依赖
    except Exception:
        HOSTS_PATH = None  # type: ignore

    if is_admin(probe_path=HOSTS_PATH):
        return True

    try:
        # frozen: 直接提升 exe
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params: List[str] = sys.argv[1:]
        else:
            # script: python.exe + main.py + args...
            exe = sys.executable
            params = sys.argv

        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe,
            subprocess.list2cmdline(params),
            None,
            5,
        )
        sys.exit(0)
    except Exception:
        _windows_message_box(
            "需要管理员权限才能写入 Hosts 文件。\n请右键选择「以管理员身份运行」。",
            "权限不足",
        )
        sys.exit(1)


def restart_as_admin(args: List[str]) -> None:
    """以管理员权限重新启动当前程序，并传递参数（Windows）。

    args 通常使用 sys.argv.copy()，并在其后追加参数。
    """
    if sys.platform != "win32":
        return

    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = args[1:]  # 跳过可执行文件本身
        else:
            exe = sys.executable
            # 对脚本模式：python.exe + [脚本路径] + [其他参数]
            params = args

        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe,
            subprocess.list2cmdline(params),
            None,
            5,
        )
        sys.exit(0)
    except Exception:
        _windows_message_box(
            "需要管理员权限才能写入 Hosts 文件。\n请右键选择「以管理员身份运行」。",
            "权限不足",
        )
        sys.exit(1)


# ---------------------------------------------------------------------
# 文件读写（原子写入）
# ---------------------------------------------------------------------
def atomic_write_text(path: str, text: str, *, encoding: str = "utf-8") -> None:
    """原子写入文本文件：写临时文件 -> os.replace 覆盖。"""
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def atomic_write_json(
    path: str,
    data: Any,
    *,
    encoding: str = "utf-8",
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    """原子写入 JSON 文件。"""
    txt = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, txt, encoding=encoding)


def safe_read_json(path: str, default: Any) -> Any:
    """读取 JSON，失败返回 default。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------------------------------------------------------------------
# 兼容旧代码：保留简单的文件行读写接口
# ---------------------------------------------------------------------
def read_file_lines(file_path: str, encoding: str = "utf-8") -> List[str]:
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return f.readlines()
    except Exception:
        return []


def write_file_lines(file_path: str, lines: List[str], encoding: str = "utf-8") -> bool:
    try:
        atomic_write_text(file_path, "".join(lines), encoding=encoding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------
# 日志系统
# ---------------------------------------------------------------------
_logger: Optional[logging.Logger] = None


def setup_logger(
    app_name: str = "SmartHostsTool",
    *,
    log_level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True,
) -> logging.Logger:
    """配置并返回日志记录器。

    Args:
        app_name: 应用名称，用于日志目录和文件名
        log_level: 日志级别，默认 INFO
        max_bytes: 单个日志文件最大大小（字节），默认 10MB
        backup_count: 保留的备份文件数量，默认 5 个
        console_output: 是否输出到控制台，默认 True

    Returns:
        配置好的 Logger 实例
    """
    global _logger

    if _logger is not None:
        return _logger

    # 获取日志目录
    log_dir = user_data_dir(app_name)
    os.makedirs(log_dir, exist_ok=True)

    # 日志文件名：app_YYYYMMDD.log
    log_filename = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d')}.log")

    # 创建 logger
    logger = logging.getLogger(app_name)
    logger.setLevel(log_level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 文件 handler（带轮转）
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
        delay=False,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台 handler（可选）
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.info(f"日志系统已初始化，日志文件：{log_filename}")
    _logger = logger
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取日志记录器。

    Args:
        name: 日志记录器名称，默认使用 APP_NAME

    Returns:
        Logger 实例
    """
    if name is None:
        try:
            from config import APP_NAME
            name = APP_NAME
        except Exception:
            name = "SmartHostsTool"

    return logging.getLogger(name)
