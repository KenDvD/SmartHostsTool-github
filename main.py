# -*- coding: utf-8 -*-
"""
main.py

程序入口：
- 支持 writer mode：用于“自动提权后仅写入 hosts 内容并退出”
- 正常模式：启动 GUI

说明：
- writer mode 由 hosts_file.HostsFileManager.write_hosts_atomic 触发：
  会把写入内容保存到临时文件，然后以管理员权限重启并传入：
    --write-content=<tempfile> --encoding=<encoding>
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from config import APP_NAME, APP_THEME, LOG_CONFIG, TRAY_CONFIG
from hosts_file import HostsFileManager
from utils import check_and_elevate, get_logger, resource_path, setup_logger


def _run_writer_mode(write_content_path: str, encoding: str) -> None:
    """提权后的写入模式：写入 hosts -> 刷新 DNS -> 退出。"""
    logger = get_logger()
    mgr = HostsFileManager()

    if not (write_content_path and os.path.exists(write_content_path)):
        logger.error("writer mode: 临时内容文件不存在，退出。")
        sys.exit(0)

    success = False
    try:
        with open(write_content_path, "r", encoding=encoding) as f:
            content = f.read()

        # 这里关闭"再次提权"，避免循环
        mgr.write_hosts_atomic(content, encoding=encoding, allow_elevate=False)
        success = True
        logger.info("Hosts文件写入成功（writer mode）")
    except Exception as e:
        logger.exception(f"writer mode: 写入 hosts 失败: {e}")
    finally:
        try:
            os.remove(write_content_path)
        except Exception as e:
            logger.warning(f"删除临时文件失败: {e}")

    if success:
        try:
            mgr.flush_dns_cache()
            logger.info("DNS缓存已刷新（writer mode）")
        except Exception as e:
            logger.error(f"writer mode: 刷新DNS失败: {e}")

    sys.exit(0)


def main() -> None:
    # 初始化日志系统（最早初始化，确保所有模块都能使用日志）
    log_level_str = LOG_CONFIG.get("level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    logger = setup_logger(
        APP_NAME,
        log_level=log_level,
        max_bytes=LOG_CONFIG.get("max_bytes", 10 * 1024 * 1024),
        backup_count=LOG_CONFIG.get("backup_count", 5),
        console_output=LOG_CONFIG.get("console_output", True),
    )
    
    logger.info("=" * 60)
    logger.info(f"{APP_NAME} 启动")
    logger.info(f"Python 版本: {sys.version}")
    logger.info(f"平台: {sys.platform}")
    logger.info("=" * 60)

    parser = argparse.ArgumentParser()
    parser.add_argument("--write-content", type=str, help="临时文件路径，包含要写入的 hosts 内容")
    parser.add_argument("--encoding", type=str, default="utf-8", help="写入内容的编码")
    args = parser.parse_args()

    # writer mode：仅执行写入动作并退出
    if args.write_content:
        logger.info(f"进入 writer mode，临时文件: {args.write_content}")
        _run_writer_mode(args.write_content, args.encoding)

    # 正常 GUI 启动：先请求管理员权限
    logger.info("检查管理员权限...")
    check_and_elevate()
    logger.info("管理员权限检查通过")

    import ttkbootstrap as ttk  # 延迟导入，避免 writer mode 拉起 GUI 依赖
    from main_window import HostsOptimizer

    logger.info("初始化 GUI 界面...")
    app = ttk.Window(themename=APP_THEME)
    ico = resource_path("icon.ico")
    if os.path.exists(ico):
        try:
            app.iconbitmap(ico)
            logger.debug(f"设置窗口图标: {ico}")
        except Exception as e:
            logger.warning(f"设置窗口图标失败: {e}")

    # 创建主窗口
    hosts_optimizer = HostsOptimizer(app)
    
    # 初始化系统托盘（如果可用）
    tray_icon = None
    if TRAY_CONFIG.get("minimize_to_tray", True):
        try:
            from tray_icon import SystemTrayIcon, check_tray_dependencies
            
            available, missing = check_tray_dependencies()
            if available:
                logger.info("初始化系统托盘...")
                tray_icon = SystemTrayIcon(
                    app_name=APP_NAME,
                    on_show_window=hosts_optimizer.show_window,
                    on_hide_window=hosts_optimizer.hide_window,
                    on_quick_test=lambda: app.after(0, hosts_optimizer.start_test),
                    on_flush_dns=lambda: app.after(0, lambda: hosts_optimizer.flush_dns(silent=True)),
                    on_exit=hosts_optimizer.force_exit,
                )
                
                if tray_icon.start():
                    hosts_optimizer.set_tray_icon(tray_icon)
                    logger.info("系统托盘初始化成功")
                else:
                    logger.warning("系统托盘启动失败")
                    tray_icon = None
            else:
                logger.info(f"系统托盘不可用，缺少依赖: {', '.join(missing)}")
                logger.info("如需使用托盘功能，请运行: pip install pystray Pillow")
        except ImportError as e:
            logger.warning(f"无法导入托盘模块: {e}")
        except Exception as e:
            logger.warning(f"初始化托盘时出错: {e}")
    
    # 如果配置了启动时最小化
    if TRAY_CONFIG.get("start_minimized", False) and tray_icon and tray_icon.is_running:
        logger.info("启动时最小化到托盘")
        app.after(100, hosts_optimizer.hide_window)
    
    logger.info("GUI 界面初始化完成，进入主循环")
    app.mainloop()
    
    # 清理托盘
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass
    
    logger.info("程序退出")


if __name__ == "__main__":
    main()
