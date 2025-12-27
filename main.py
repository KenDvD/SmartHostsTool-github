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
import os
import sys

from config import APP_THEME
from hosts_file import HostsFileManager
from utils import check_and_elevate, resource_path


def _run_writer_mode(write_content_path: str, encoding: str) -> None:
    """提权后的写入模式：写入 hosts -> 刷新 DNS -> 退出。"""
    mgr = HostsFileManager()

    if not (write_content_path and os.path.exists(write_content_path)):
        print("writer mode: 临时内容文件不存在，退出。")
        sys.exit(0)

    success = False
    try:
        with open(write_content_path, "r", encoding=encoding) as f:
            content = f.read()

        # 这里关闭“再次提权”，避免循环
        mgr.write_hosts_atomic(content, encoding=encoding, allow_elevate=False)
        success = True
        print("Hosts文件写入成功（writer mode）")
    except Exception as e:
        print(f"writer mode: 写入 hosts 失败: {e}")
    finally:
        try:
            os.remove(write_content_path)
        except Exception:
            pass

    if success:
        try:
            mgr.flush_dns_cache()
            print("DNS缓存已刷新（writer mode）")
        except Exception as e:
            print(f"writer mode: 刷新DNS失败: {e}")

    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-content", type=str, help="临时文件路径，包含要写入的 hosts 内容")
    parser.add_argument("--encoding", type=str, default="utf-8", help="写入内容的编码")
    args = parser.parse_args()

    # writer mode：仅执行写入动作并退出
    if args.write_content:
        _run_writer_mode(args.write_content, args.encoding)

    # 正常 GUI 启动：先请求管理员权限
    check_and_elevate()

    import ttkbootstrap as ttk  # 延迟导入，避免 writer mode 拉起 GUI 依赖
    from main_window import HostsOptimizer

    app = ttk.Window(themename=APP_THEME)
    ico = resource_path("icon.ico")
    if os.path.exists(ico):
        try:
            app.iconbitmap(ico)
        except Exception:
            pass

    HostsOptimizer(app)
    app.mainloop()


if __name__ == "__main__":
    main()
