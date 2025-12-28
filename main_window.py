# -*- coding: utf-8 -*-
"""
main_window.py

GUI 层（ttkbootstrap）：
- 负责 UI 布局、交互、状态更新
- 调用 services.py / hosts_file.py 的能力完成业务逻辑

说明：
- 保留原有 UI 与功能，不改变用户使用习惯。
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import socket
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.tooltip import ToolTip
from tkinter import BooleanVar, Menu, StringVar, filedialog, messagebox, simpledialog

from config import (
    APP_NAME,
    GITHUB_TARGET_DOMAIN,
    HOSTS_PATH,
    REMOTE_HOSTS_SOURCE_CHOICES,
    REMOTE_HOSTS_URLS,
    UI_CONFIG,
    SPEED_TEST_CONFIG,
    SCHEDULED_TEST_CONFIG,
    TRAY_CONFIG,
)
from hosts_file import HostsFileManager
from services import DomainResolver, RemoteHostsClient, SpeedTester, EnhancedSpeedTester, SpeedTestConfigManager
from ui_visuals import GlassBackground
from utils import atomic_write_json, get_logger, is_admin, resource_path, safe_read_json, user_data_path

# 主窗口尺寸配置（像素）
# MAIN_WINDOW_WIDTH_PX: 主窗口宽度（推荐 1000-1200px）
# MAIN_WINDOW_HEIGHT_PX: 主窗口高度（推荐 600-750px）
# MIN_WINDOW_WIDTH_PX: 窗口最小宽度（推荐 900-1050px）
# MIN_WINDOW_HEIGHT_PX: 窗口最小高度（推荐 550-650px）
MAIN_WINDOW_WIDTH_PX = 1080
MAIN_WINDOW_HEIGHT_PX = 680
MIN_WINDOW_WIDTH_PX = 980
MIN_WINDOW_HEIGHT_PX = 620

# 表格视图行高配置（像素，推荐 24-30px，应与字体大小匹配）
TREEVIEW_ROW_HEIGHT_PX = 26

# 斑马纹混合比例配置（用于玻璃效果，推荐 0.03-0.10）
# ZEBRA_ROW_A_MIX_RATIO: 偶数行混合比例
# ZEBRA_ROW_B_MIX_RATIO: 奇数行混合比例（应大于 A）
ZEBRA_ROW_A_MIX_RATIO = 0.04
ZEBRA_ROW_B_MIX_RATIO = 0.07

# 渐变分割点配置（0.0-1.0，推荐 0.45-0.65，控制渐变色切换位置）
GRADIENT_SPLIT_POINT = 0.55

# 噪声阈值配置（灰度值 0-255，推荐 100-150，控制噪声生成密度）
NOISE_THRESHOLD_GRAY = 120

# 表格列宽配置（像素）
# select: 选择列（复选框）
# ip: IP地址列
# domain: 域名列
# delay: 延迟列
# jitter: 抖动列
# stability: 稳定性列
# status: 状态列
COLUMN_WIDTHS = {
    "select": 64,
    "ip": 150,
    "domain": 200,
    "delay": 90,
    "jitter": 90,
    "stability": 80,
    "status": 120,
}

# 按钮宽度配置（字符数）
# remote_source: 远程源选择按钮
# refresh_remote: 刷新远程 Hosts 按钮
# pause_test: 暂停测速按钮
# start_test: 开始测速按钮
# more: 更多功能按钮
# add_preset: 添加预设按钮
# delete_preset: 删除预设按钮
# resolve_preset: 批量解析按钮
# rollback_hosts: 回滚 Hosts 按钮
# write_best: 一键写入最优 IP 按钮
# write_selected: 写入选中到 Hosts 按钮
BUTTON_WIDTHS = {
    "remote_source": 15,
    "refresh_remote": 15,
    "pause_test": 10,
    "start_test": 10,
    "more": 10,
    "add_preset": 8,
    "delete_preset": 8,
    "resolve_preset": 12,
    "rollback_hosts": 12,
    "write_best": 18,
    "write_selected": 18,
}

# 表格视图配置
# remote.columns: 远程 Hosts 表格列标识
# remote.headers: 远程 Hosts 表格列标题
# remote.widths: 远程 Hosts 表格列宽（像素）
# preset.height: 预设表格显示行数（推荐 12-16 行）
# preset.domain_width: 预设表格域名列宽（像素，推荐 280-340px）
TREEVIEW_CONFIGS = {
    "remote": {
        "columns": ["ip", "domain"],
        "headers": ["IP 地址", "域名"],
        "widths": [140, 240],
    },
    "preset": {
        "height": 14,
        "domain_width": 310,
    },
}

# 字体大小配置（磅）
# title: 标题字体（推荐 16-20pt）
# treeview: 表格字体（推荐 9-11pt）
FONT_SIZES = {
    "title": 18,
    "treeview": 10,
}

# 内边距配置（像素）
# appbar: 顶部应用栏（水平, 垂直）
# title: 标题（水平, 垂直）
# panel: 左右面板
# card: 卡片容器
# tab_frame: 标签页框架
# body_vertical: 主体垂直外边距（顶部, 底部）
# statusbar: 状态栏（水平, 垂直）
PADDING_VALUES = {
    "appbar": (10, 8),
    "title": (14, 10),
    "panel": 10,
    "card": 10,
    "tab_frame": 8,
    "body_vertical": (12, 0),
    "statusbar": (10, 8),
}

# 其他 UI 数值配置
# tip_wraplength: 提示文字换行宽度（像素，推荐 300-350px）
# resolver_max_workers: DNS 解析最大线程数（推荐 15-25）
# remote_source_button_max_length: 远程源按钮文字最大长度（字符，推荐 14-18）
UI_OTHER_VALUES = {
    "tip_wraplength": 320,
    "resolver_max_workers": 20,
    "remote_source_button_max_length": 16,
}


# 关于窗口（可选）
try:
    from about_window import AboutWindow
except Exception:
    AboutWindow = None  # type: ignore

# Toast通知 可选
try:
    from ttkbootstrap.toast import ToastNotification
except Exception:
    ToastNotification = None


class HostsOptimizer(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master, padding=0)
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 初始化日志记录器
        self.logger = get_logger()
        self.logger.info("初始化 HostsOptimizer 主窗口")

        # Services / Managers
        self.remote_client = RemoteHostsClient(urls=list(REMOTE_HOSTS_URLS))
        self.resolver = DomainResolver(max_workers=UI_OTHER_VALUES["resolver_max_workers"])
        self.hosts_mgr = HostsFileManager(hosts_path=HOSTS_PATH)
        
        # 测速配置管理器
        self.speed_test_config_manager = SpeedTestConfigManager()
        self.speed_test_config = self.speed_test_config_manager.load_config()
        self.logger.info("测速配置管理器已初始化")

        # 远程 Hosts 来源（用于 UI 展示）
        self.remote_hosts_source_url: Optional[str] = None
        self.remote_source_url_override: Optional[str] = None

        # 窗口属性
        self.master.title("智能 Hosts 测速工具")
        self.master.geometry(f"{MAIN_WINDOW_WIDTH_PX}x{MAIN_WINDOW_HEIGHT_PX}")
        self.master.minsize(MIN_WINDOW_WIDTH_PX, MIN_WINDOW_HEIGHT_PX)

        # 背景（玻璃拟态）
        try:
            self._bg = GlassBackground(self.master)
        except Exception:
            self._bg = None

        # 数据
        self.remote_hosts_data: List[Tuple[str, str]] = []
        self.smart_resolved_ips: List[Tuple[str, str]] = []
        self.custom_presets: List[str] = []
        # test_results: (ip, domain, delay_ms, status, selected, jitter, stability)
        self.test_results: List[Tuple[str, str, int, str, bool, float, float]] = []
        self._test_metadata: Dict[str, Dict[str, Any]] = {}

        self.presets_file = user_data_path(APP_NAME, "presets.json")
        self.current_selected_presets: List[str] = []
        self.is_github_selected = False

        # 测速相关
        self.stop_test = False
        self.executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._stop_event = threading.Event()
        self._futures: List[concurrent.futures.Future] = []

        # 进度统计（按唯一 IP）
        self.total_ip_tests = 0
        self.completed_ip_tests = 0
        self._ip_to_domains: Dict[str, List[str]] = {}

        # 结果排序节流
        self._sort_after_id = None

        # UI vars
        self.icmp_fallback_var = BooleanVar(value=True)
        self.advanced_metrics_var = BooleanVar(value=True)

        self._about = None
        
        # 定时测速相关
        self._scheduled_test_enabled = False
        self._scheduled_test_interval = SCHEDULED_TEST_CONFIG.get("interval_minutes", 60)
        self._scheduled_test_auto_write = SCHEDULED_TEST_CONFIG.get("auto_write_best", True)
        self._scheduled_test_after_id = None
        self._last_scheduled_test_time = None
        self._scheduled_test_domains: List[str] = []  # 定时测速的目标域名列表
        self._is_scheduled_test_running = False  # 标记当前是否是定时测速
        
        # 系统托盘相关
        self._tray_icon = None
        self._minimize_to_tray = TRAY_CONFIG.get("minimize_to_tray", True)
        
        # 加载定时测速配置
        self._load_scheduled_test_config()

        # UI
        self._setup_style()
        self.create_widgets()
        self.load_presets()

        # 【布局关键修复】：留出 padding 让背景透出来，lift 提升控件层级
        self.pack(fill=BOTH, expand=True, padx=15, pady=15)
        self.lift()
        if self._bg:
            try:
                self._bg.lower()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------
    def on_close(self):
        """关闭窗口处理：支持最小化到托盘"""
        # 如果启用了托盘且托盘可用，最小化到托盘而非退出
        if self._minimize_to_tray and self._tray_icon and self._tray_icon.is_running:
            self.logger.info("最小化到系统托盘")
            self.hide_window()
            return
        
        # 否则执行真正的退出
        self.force_exit()
    
    def force_exit(self):
        """强制退出程序（清理所有资源）"""
        self.logger.info("用户关闭窗口，开始清理资源...")
        
        # 停止定时测速
        self._stop_scheduled_test()
        
        # 停止当前测速
        self.stop_test = True
        self._stop_event.set()
        if self.executor:
            try:
                self.executor.shutdown(wait=False)
                self.logger.debug("线程池已关闭")
            except Exception as e:
                self.logger.warning(f"关闭线程池时出错: {e}")
        
        # 停止托盘
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception as e:
                self.logger.warning(f"停止托盘时出错: {e}")
        
        try:
            self.master.destroy()
        except Exception as e:
            self.logger.warning(f"销毁窗口时出错: {e}")
        self.logger.info("程序退出")
        sys.exit(0)
    
    def hide_window(self):
        """隐藏窗口到托盘"""
        try:
            self.master.withdraw()
            if self._tray_icon:
                self._tray_icon.set_window_visible(False)
                self._tray_icon.show_notification(
                    "智能Hosts测速工具",
                    "程序已最小化到系统托盘，双击图标可恢复窗口"
                )
            self.logger.debug("窗口已隐藏到托盘")
        except Exception as e:
            self.logger.warning(f"隐藏窗口失败: {e}")
    
    def show_window(self):
        """从托盘恢复显示窗口"""
        try:
            self.master.deiconify()
            self.master.lift()
            self.master.focus_force()
            if self._tray_icon:
                self._tray_icon.set_window_visible(True)
            self.logger.debug("窗口已从托盘恢复")
        except Exception as e:
            self.logger.warning(f"显示窗口失败: {e}")
    
    def minimize_to_tray(self):
        """手动最小化到托盘"""
        if self._tray_icon and self._tray_icon.is_running:
            self.hide_window()
        else:
            messagebox.showinfo("提示", "系统托盘功能不可用。\n请安装 pystray 和 Pillow 库：\npip install pystray Pillow")
    
    def set_tray_icon(self, tray_icon):
        """设置托盘图标实例（由 main.py 调用）"""
        self._tray_icon = tray_icon
        self.logger.info("托盘图标已关联到主窗口")
    
    # -----------------------------------------------------------------
    # 定时测速功能
    # -----------------------------------------------------------------
    def _load_scheduled_test_config(self):
        """从用户配置文件加载定时测速设置"""
        config_path = user_data_path(APP_NAME, "scheduled_test.json")
        config = safe_read_json(config_path, None)
        if config:
            self._scheduled_test_enabled = config.get("enabled", False)
            self._scheduled_test_interval = config.get("interval_minutes", 60)
            self._scheduled_test_auto_write = config.get("auto_write_best", True)
            self._scheduled_test_domains = config.get("domains", [])
            self.logger.info(f"加载定时测速配置: enabled={self._scheduled_test_enabled}, interval={self._scheduled_test_interval}分钟, domains={len(self._scheduled_test_domains)}个")
            
            # 如果启用了定时测速，启动调度器
            if self._scheduled_test_enabled and self._scheduled_test_domains:
                self._start_scheduled_test()
    
    def _save_scheduled_test_config(self):
        """保存定时测速配置"""
        config_path = user_data_path(APP_NAME, "scheduled_test.json")
        config = {
            "enabled": self._scheduled_test_enabled,
            "interval_minutes": self._scheduled_test_interval,
            "auto_write_best": self._scheduled_test_auto_write,
            "domains": self._scheduled_test_domains,
        }
        try:
            atomic_write_json(config_path, config)
            self.logger.info("定时测速配置已保存")
        except Exception as e:
            self.logger.error(f"保存定时测速配置失败: {e}")
    
    def _start_scheduled_test(self):
        """启动定时测速调度器"""
        if self._scheduled_test_after_id:
            return  # 已经在运行
        
        interval_ms = self._scheduled_test_interval * 60 * 1000
        self._scheduled_test_after_id = self.master.after(interval_ms, self._run_scheduled_test)
        self.logger.info(f"定时测速已启动，间隔 {self._scheduled_test_interval} 分钟")
        
        # 更新状态栏
        self.status_label.config(text=f"定时测速已启用（每 {self._scheduled_test_interval} 分钟）", bootstyle=INFO)
    
    def _stop_scheduled_test(self):
        """停止定时测速调度器"""
        if self._scheduled_test_after_id:
            try:
                self.master.after_cancel(self._scheduled_test_after_id)
            except Exception:
                pass
            self._scheduled_test_after_id = None
            self.logger.info("定时测速已停止")
    
    def _run_scheduled_test(self):
        """执行定时测速任务"""
        import datetime
        self._last_scheduled_test_time = datetime.datetime.now()
        self.logger.info(f"开始执行定时测速任务，目标域名: {self._scheduled_test_domains}")
        
        # 检查是否有配置的域名
        if not self._scheduled_test_domains:
            self.logger.warning("定时测速：未配置目标域名，跳过本次测速")
            self._schedule_next_test()
            return
        
        # 清空旧数据，准备新测速
        self.remote_hosts_data = []
        self.smart_resolved_ips = []
        
        # 使用配置的域名列表进行解析
        self.current_selected_presets = list(self._scheduled_test_domains)
        self.is_github_selected = GITHUB_TARGET_DOMAIN in self._scheduled_test_domains
        
        # 如果包含 github.com，先刷新远程 Hosts
        if self.is_github_selected:
            self.logger.info("定时测速：刷新远程Hosts...")
            threading.Thread(target=self._scheduled_fetch_and_test, daemon=True).start()
        else:
            # 直接解析并测速
            self.logger.info("定时测速：解析域名IP...")
            threading.Thread(target=self._scheduled_resolve_and_test, daemon=True).start()
    
    def _schedule_next_test(self):
        """安排下一次定时测速"""
        if self._scheduled_test_enabled:
            interval_ms = self._scheduled_test_interval * 60 * 1000
            self._scheduled_test_after_id = self.master.after(interval_ms, self._run_scheduled_test)
    
    def _scheduled_fetch_and_test(self):
        """定时测速：获取远程Hosts并测速"""
        import asyncio
        try:
            async def fetch_async():
                try:
                    records, used_url = await self.remote_client.fetch_github_hosts_async(concurrent=True)
                    self.remote_hosts_data = records
                    self.logger.info(f"定时测速：获取到 {len(records)} 条远程Hosts记录")
                except Exception as e:
                    self.logger.error(f"定时测速：获取远程Hosts失败: {e}")
            
            asyncio.run(fetch_async())
        except Exception as e:
            self.logger.error(f"定时测速：获取远程Hosts异常: {e}")
        
        # 继续解析其他域名
        self._scheduled_resolve_and_test()
    
    def _scheduled_resolve_and_test(self):
        """定时测速：解析域名并测速"""
        try:
            # 解析非 GitHub 域名
            non_github_domains = [d for d in self._scheduled_test_domains if d != GITHUB_TARGET_DOMAIN]
            if non_github_domains:
                self.logger.info(f"定时测速：解析 {len(non_github_domains)} 个域名...")
                resolved = self.resolver.resolve(non_github_domains)
                self.smart_resolved_ips = resolved
                self.logger.info(f"定时测速：解析到 {len(resolved)} 个IP")
            
            # 在主线程中启动测速
            self.master.after(0, self._start_scheduled_speed_test)
        except Exception as e:
            self.logger.error(f"定时测速：解析域名失败: {e}")
            self._schedule_next_test()
    
    def _start_scheduled_speed_test(self):
        """在主线程中启动定时测速"""
        if self.remote_hosts_data or self.smart_resolved_ips:
            self.logger.info("定时测速：开始测速...")
            # 标记这是定时测速，完成后调用回调
            self._is_scheduled_test_running = True
            self.start_test()
        else:
            self.logger.warning("定时测速：没有可测试的IP")
            self._schedule_next_test()
    
    def _on_scheduled_test_complete(self):
        """定时测速完成后的回调"""
        if self._scheduled_test_auto_write:
            # 自动写入最优 IP
            self.logger.info("定时测速完成，自动写入最优IP")
            self.write_best_ip_to_hosts()
        
        # 托盘通知
        if self._tray_icon and self._tray_icon.is_running:
            self._tray_icon.show_notification(
                "定时测速完成",
                f"已测试 {self.total_ip_tests} 个IP，{'已自动写入最优IP' if self._scheduled_test_auto_write else '请手动选择写入'}"
            )
    
    def show_scheduled_test_settings(self):
        """显示定时测速设置窗口"""
        self.logger.info("打开定时测速设置窗口")
        
        settings_window = ttk.Toplevel(self.master)
        settings_window.title("定时测速设置")
        settings_window.geometry("680x820")
        settings_window.resizable(True, True)
        settings_window.minsize(620, 750)
        
        # 居中
        try:
            settings_window.place_window_center()
        except Exception:
            sw = settings_window.winfo_screenwidth()
            sh = settings_window.winfo_screenheight()
            x = int(sw / 2 - 340)
            y = int(sh / 2 - 410)
            settings_window.geometry(f"680x820+{x}+{y}")
        
        # 模态
        settings_window.transient(self.master)
        settings_window.grab_set()
        
        # 主容器
        container = ttk.Frame(settings_window, padding=20)
        container.pack(fill=BOTH, expand=True)
        
        # 标题
        title = ttk.Label(
            container,
            text="定时测速设置",
            font=("Segoe UI", 16, "bold"),
            bootstyle="primary",
        )
        title.pack(pady=(0, 15))
        
        # 启用开关
        enabled_var = BooleanVar(value=self._scheduled_test_enabled)
        enabled_frame = ttk.Frame(container)
        enabled_frame.pack(fill=X, pady=8)
        ttk.Checkbutton(
            enabled_frame,
            text="启用定时自动测速",
            variable=enabled_var,
            bootstyle="success-round-toggle",
        ).pack(side=LEFT)
        
        # 间隔设置
        interval_frame = ttk.Frame(container)
        interval_frame.pack(fill=X, pady=8)
        ttk.Label(interval_frame, text="测速间隔：", font=("Segoe UI", 10)).pack(side=LEFT)
        interval_var = StringVar(value=str(self._scheduled_test_interval))
        interval_entry = ttk.Entry(interval_frame, textvariable=interval_var, width=10)
        interval_entry.pack(side=LEFT, padx=5)
        ttk.Label(interval_frame, text="分钟（推荐：30-240）", font=("Segoe UI", 9), bootstyle="secondary").pack(side=LEFT)
        
        # 自动写入
        auto_write_var = BooleanVar(value=self._scheduled_test_auto_write)
        ttk.Checkbutton(
            container,
            text="测速完成后自动写入最优IP到Hosts",
            variable=auto_write_var,
        ).pack(anchor=W, pady=8)
        
        # 域名选择区域
        domain_frame = ttk.Labelframe(container, text="选择要定时测速的域名", padding=10)
        domain_frame.pack(fill=BOTH, expand=True, pady=10)
        
        # 域名列表（带复选框）
        domain_list_frame = ttk.Frame(domain_frame)
        domain_list_frame.pack(fill=BOTH, expand=True)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(domain_list_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 使用 Treeview 显示域名列表（带复选框效果）
        domain_tree = ttk.Treeview(
            domain_list_frame,
            columns=["selected", "domain"],
            show="headings",
            height=12,
            yscrollcommand=scrollbar.set,
        )
        domain_tree.heading("selected", text="选择")
        domain_tree.heading("domain", text="域名")
        domain_tree.column("selected", width=60, anchor="center")
        domain_tree.column("domain", width=400)
        domain_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=domain_tree.yview)
        
        # 域名选择状态
        domain_selected: Dict[str, BooleanVar] = {}
        
        # 填充域名列表（从预设列表获取）
        for domain in self.custom_presets:
            is_selected = domain in self._scheduled_test_domains
            domain_selected[domain] = is_selected
            check_mark = "✓" if is_selected else "□"
            domain_tree.insert("", "end", values=[check_mark, domain], iid=domain)
        
        def toggle_domain(event):
            """切换域名选择状态"""
            item = domain_tree.identify_row(event.y)
            if not item:
                return
            domain = item  # iid 就是域名
            domain_selected[domain] = not domain_selected.get(domain, False)
            check_mark = "✓" if domain_selected[domain] else "□"
            domain_tree.item(item, values=[check_mark, domain])
        
        domain_tree.bind("<Button-1>", toggle_domain)
        
        # 快捷按钮
        quick_btn_frame = ttk.Frame(domain_frame)
        quick_btn_frame.pack(fill=X, pady=(10, 0))
        
        def select_all():
            for domain in self.custom_presets:
                domain_selected[domain] = True
                domain_tree.item(domain, values=["✓", domain])
        
        def select_none():
            for domain in self.custom_presets:
                domain_selected[domain] = False
                domain_tree.item(domain, values=["□", domain])
        
        def select_github():
            for domain in self.custom_presets:
                is_github = "github" in domain.lower()
                domain_selected[domain] = is_github
                check_mark = "✓" if is_github else "□"
                domain_tree.item(domain, values=[check_mark, domain])
        
        ttk.Button(quick_btn_frame, text="全选", command=select_all, bootstyle="info-outline", width=8).pack(side=LEFT, padx=2)
        ttk.Button(quick_btn_frame, text="全不选", command=select_none, bootstyle="secondary-outline", width=8).pack(side=LEFT, padx=2)
        ttk.Button(quick_btn_frame, text="仅GitHub", command=select_github, bootstyle="success-outline", width=10).pack(side=LEFT, padx=2)
        
        # 已选数量提示
        selected_count_var = StringVar(value=f"已选择 {sum(1 for v in domain_selected.values() if v)} 个域名")
        selected_label = ttk.Label(quick_btn_frame, textvariable=selected_count_var, font=("Segoe UI", 9), bootstyle="info")
        selected_label.pack(side=RIGHT)
        
        def update_selected_count(*args):
            count = sum(1 for v in domain_selected.values() if v)
            selected_count_var.set(f"已选择 {count} 个域名")
        
        # 状态显示
        status_frame = ttk.Frame(container)
        status_frame.pack(fill=X, pady=5)
        if self._last_scheduled_test_time:
            status_text = f"上次测速时间：{self._last_scheduled_test_time.strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            status_text = "尚未执行过定时测速"
        ttk.Label(container, text=status_text, font=("Segoe UI", 9), bootstyle="info").pack(anchor=W, pady=5)
        
        # 按钮
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=X, pady=(20, 0))
        
        def save_settings():
            # 验证间隔
            try:
                interval = int(interval_var.get().strip())
                if interval < 5 or interval > 1440:
                    messagebox.showerror("输入错误", "测速间隔必须在 5-1440 分钟之间")
                    return
            except ValueError:
                messagebox.showerror("输入错误", "请输入有效的数字")
                return
            
            # 获取选中的域名
            selected_domains = [domain for domain, selected in domain_selected.items() if selected]
            
            # 如果启用了定时测速，必须选择至少一个域名
            if enabled_var.get() and not selected_domains:
                messagebox.showerror("配置错误", "请至少选择一个要测速的域名！")
                return
            
            # 保存设置
            old_enabled = self._scheduled_test_enabled
            self._scheduled_test_enabled = enabled_var.get()
            self._scheduled_test_interval = interval
            self._scheduled_test_auto_write = auto_write_var.get()
            self._scheduled_test_domains = selected_domains
            self._save_scheduled_test_config()
            
            # 根据状态启动或停止调度器
            if self._scheduled_test_enabled and not old_enabled:
                self._start_scheduled_test()
                domain_str = ", ".join(selected_domains[:3])
                if len(selected_domains) > 3:
                    domain_str += f" 等{len(selected_domains)}个"
                self._toast("定时测速", f"已启用，每 {interval} 分钟测速 {domain_str}", bootstyle="success")
            elif not self._scheduled_test_enabled and old_enabled:
                self._stop_scheduled_test()
                self._toast("定时测速", "已停止", bootstyle="warning")
            elif self._scheduled_test_enabled:
                # 间隔或域名可能变了，重新调度
                self._stop_scheduled_test()
                self._start_scheduled_test()
            
            messagebox.showinfo("成功", f"定时测速设置已保存！\n\n已选择 {len(selected_domains)} 个域名进行定时测速。")
            settings_window.destroy()
        
        ttk.Button(btn_frame, text="保存", command=save_settings, bootstyle="success", width=12).pack(side=RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=settings_window.destroy, bootstyle="secondary", width=12).pack(side=RIGHT)
        
        # 立即测试按钮
        def run_now():
            selected_domains = [domain for domain, selected in domain_selected.items() if selected]
            if not selected_domains:
                messagebox.showerror("配置错误", "请至少选择一个要测速的域名！")
                return
            # 保存配置并立即运行
            self._scheduled_test_domains = selected_domains
            self._save_scheduled_test_config()
            settings_window.destroy()
            self._run_scheduled_test()
            self._toast("定时测速", "正在执行测速...", bootstyle="info")
        
        ttk.Button(btn_frame, text="立即测试", command=run_now, bootstyle="info-outline", width=12).pack(side=LEFT, padx=5)
        
        settings_window.bind("<Escape>", lambda e: settings_window.destroy())

    # -----------------------------------------------------------------
    # Style / Treeview
    # -----------------------------------------------------------------
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.configure("Treeview", rowheight=TREEVIEW_ROW_HEIGHT_PX, font=("Segoe UI", 10))
            style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
            style.configure("Card.TLabelframe", background=style.colors.bg, bordercolor=style.colors.border)
            style.configure("Card.TLabelframe.Label", background=style.colors.bg, foreground=style.colors.fg)
            style.configure("Card.TFrame", background=style.colors.bg)
        except Exception:
            pass

    def _hex_to_rgb(self, h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(self, rgb):
        return "#%02x%02x%02x" % rgb

    def _mix(self, a: str, b: str, t: float) -> str:
        ra, ga, ba = self._hex_to_rgb(a)
        rb, gb, bb = self._hex_to_rgb(b)
        r = int(ra + (rb - ra) * t)
        g = int(ga + (gb - ga) * t)
        b2 = int(ba + (bb - ba) * t)
        return self._rgb_to_hex((r, g, b2))

    def _setup_treeview_tags(self, tv: ttk.Treeview):
        """给 Treeview 加：斑马纹 + 状态色（可用/超时）。"""
        try:
            style = ttk.Style()
            bg = style.colors.bg
            fg = style.colors.fg

            row_a = self._mix(bg, fg, ZEBRA_ROW_A_MIX_RATIO)
            row_b = self._mix(bg, fg, ZEBRA_ROW_B_MIX_RATIO)

            tv.tag_configure("row_a", background=row_a)
            tv.tag_configure("row_b", background=row_b)

            tv.tag_configure("ok", foreground=style.colors.success)
            tv.tag_configure("bad", foreground=style.colors.danger)
        except Exception:
            pass

    def _tv_insert(self, tv: ttk.Treeview, values, index: int, status: Optional[str] = None):
        tags = ["row_a" if index % 2 == 0 else "row_b"]
        if status:
            st = str(status)
            if ("超时" in st) or ("不可达" in st) or ("失败" in st) or ("拒绝" in st):
                tags.append("bad")
            elif st.startswith("可用") or "可用(ICMP)" in st:
                tags.append("ok")
        tv.insert("", "end", values=values, tags=tags)

    # -----------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------
    def create_widgets(self):
        # --- App Bar ---
        appbar = ttk.Frame(self, padding=PADDING_VALUES["appbar"])
        appbar.pack(fill=X)

        left = ttk.Frame(appbar)
        left.pack(side=LEFT, fill=X, expand=True)
        title = ttk.Label(
            left,
            text="智能 Hosts 测速工具",
            font=("Segoe UI", FONT_SIZES["title"], "bold"),
            bootstyle="inverse-primary",
            padding=PADDING_VALUES["title"],
        )
        title.pack(side=LEFT, fill=X, expand=True)

        actions = ttk.Frame(appbar)
        actions.pack(side=RIGHT)

        # 源选择 - 下拉按钮
        self.remote_source_var = StringVar(value=REMOTE_HOSTS_SOURCE_CHOICES[0][0])
        self.remote_source_btn_text = StringVar()
        self.remote_source_btn_text.set(self._format_remote_source_button_text(self.remote_source_var.get()))

        self.remote_source_btn = ttk.Menubutton(
            actions,
            textvariable=self.remote_source_btn_text,
            bootstyle="secondary",
            width=BUTTON_WIDTHS["remote_source"],
        )
        self.remote_source_btn.pack(side=LEFT, padx=(12, 8))

        menu = Menu(self.remote_source_btn, tearoff=0)
        for label, _ in REMOTE_HOSTS_SOURCE_CHOICES:
            menu.add_radiobutton(
                label=label,
                variable=self.remote_source_var,
                value=label,
                command=self.on_source_change,
            )
        self.remote_source_btn["menu"] = menu

        # 刷新远程 Hosts
        self.refresh_remote_btn = ttk.Button(
            actions,
            text="🔄 刷新远程 Hosts",
            command=self.refresh_remote_hosts,
            bootstyle=SUCCESS,
            width=BUTTON_WIDTHS["refresh_remote"],
            state=DISABLED,
        )
        self.refresh_remote_btn.pack(side=LEFT, padx=5)

        # 主操作
        self.pause_test_btn = ttk.Button(
            actions,
            text="⏸ 暂停测速",
            command=self.pause_test,
            bootstyle=WARNING,
            width=BUTTON_WIDTHS["pause_test"],
            state=DISABLED,
        )
        self.pause_test_btn.pack(side=RIGHT, padx=(8, 0))

        self.start_test_btn = ttk.Button(
            actions,
            text="▶ 开始测速",
            command=self.start_test,
            bootstyle=PRIMARY,
            width=BUTTON_WIDTHS["start_test"],
            state=DISABLED,
        )
        self.start_test_btn.pack(side=RIGHT, padx=5)

        # 更多功能
        self.more_btn = ttk.Menubutton(actions, text="🧰 更多 ▾", bootstyle="secondary", width=BUTTON_WIDTHS["more"])
        self.more_btn.pack(side=RIGHT, padx=(0, 8))
        more_menu = Menu(self.more_btn, tearoff=0)
        more_menu.add_command(label="🧹刷新 DNS", command=self.flush_dns)
        more_menu.add_command(label="📄查看 Hosts 文件", command=self.view_hosts_file)
        more_menu.add_checkbutton(label="📡 TCP失败时使用ICMP补充", variable=self.icmp_fallback_var)
        more_menu.add_checkbutton(label="📊 启用高级测速指标", variable=self.advanced_metrics_var)
        more_menu.add_separator()
        more_menu.add_command(label="⏰ 定时测速设置", command=self.show_scheduled_test_settings)
        more_menu.add_command(label="⚙️ 测速设置", command=self.show_speed_test_settings)
        more_menu.add_separator()
        more_menu.add_command(label="🔽 最小化到托盘", command=self.minimize_to_tray)
        more_menu.add_command(label="ℹ 关于", command=self.show_about)
        self.more_btn["menu"] = more_menu
        self._more_menu = more_menu  # 保存引用以便动态更新

        # ToolTip（不影响功能）
        try:
            ToolTip(self.remote_source_btn, text="选择远程 hosts 数据源（默认按优先级自动选择）")
            ToolTip(self.refresh_remote_btn, text="从远程源获取 GitHub 相关 hosts 记录")
            ToolTip(self.start_test_btn, text="对当前 IP 列表进行并发测速并排序")
            ToolTip(self.pause_test_btn, text="停止当前测速任务")
            ToolTip(self.more_btn, text="更多工具：刷新 DNS / 查看 hosts / 关于")
        except Exception:
            pass

        # --- Body ---
        body = ttk.Frame(self)
        body.pack(fill=BOTH, expand=True, pady=PADDING_VALUES["body_vertical"])

        paned = ttk.PanedWindow(body, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True)

        # 左侧面板
        left_panel = ttk.Frame(paned, padding=PADDING_VALUES["panel"])
        paned.add(left_panel, weight=1)
        left_card = ttk.Labelframe(left_panel, text="配置", padding=PADDING_VALUES["card"], style="Card.TLabelframe")
        left_card.pack(fill=BOTH, expand=True)

        notebook = ttk.Notebook(left_card)
        notebook.pack(fill=BOTH, expand=True)

        # 远程Hosts页 - 保留原版文字
        self.remote_frame = ttk.Frame(notebook, padding=PADDING_VALUES["tab_frame"])
        notebook.add(self.remote_frame, text="🌐远程Hosts（仅 GitHub）")
        remote_config = TREEVIEW_CONFIGS["remote"]
        self.remote_tree = self._create_treeview(
            self.remote_frame,
            remote_config["columns"],
            remote_config["headers"],
            remote_config["widths"]
        )

        # 自定义预设页 - 保留原版文字
        self.custom_frame = ttk.Frame(notebook, padding=PADDING_VALUES["tab_frame"])
        notebook.add(self.custom_frame, text="自定义预设")

        self.all_resolved_frame = ttk.Frame(notebook, padding=PADDING_VALUES["tab_frame"])
        notebook.add(self.all_resolved_frame, text="🔍 所有解析结果")
        remote_config = TREEVIEW_CONFIGS["remote"]
        self.all_resolved_tree = self._create_treeview(
            self.all_resolved_frame,
            remote_config["columns"],
            remote_config["headers"],
            remote_config["widths"]
        )

        # 自定义工具栏
        custom_toolbar = ttk.Frame(self.custom_frame)
        custom_toolbar.pack(fill=X, pady=(0, 10))
        self.add_preset_btn = ttk.Button(custom_toolbar, text="➕ 添加", command=self.add_preset, bootstyle=SUCCESS, width=BUTTON_WIDTHS["add_preset"])
        self.add_preset_btn.pack(side=LEFT, padx=(0, 6))
        self.delete_preset_btn = ttk.Button(custom_toolbar, text="🗑 删除", command=self.delete_preset, bootstyle=DANGER, width=BUTTON_WIDTHS["delete_preset"])
        self.delete_preset_btn.pack(side=LEFT, padx=6)
        self.resolve_preset_btn = ttk.Button(custom_toolbar, text="批量解析", command=self.resolve_selected_presets, bootstyle=INFO, width=BUTTON_WIDTHS["resolve_preset"])
        self.resolve_preset_btn.pack(side=LEFT, padx=6)

        tip = ttk.Label(
            self.custom_frame,
            text="提示：按住 Ctrl/Shift 可多选域名；选中 github.com 后可启用「刷新远程 Hosts」。",
            bootstyle="secondary",
            wraplength=UI_OTHER_VALUES["tip_wraplength"],
            justify=LEFT,
        )
        tip.pack(fill=X, pady=(0, 10))

        preset_config = TREEVIEW_CONFIGS["preset"]
        self.preset_tree = ttk.Treeview(self.custom_frame, columns=["domain"], show="headings", height=preset_config["height"])
        self.preset_tree.heading("domain", text="域名")
        self.preset_tree.column("domain", width=preset_config["domain_width"])
        self.preset_tree.configure(selectmode="extended")
        self.preset_tree.pack(fill=BOTH, expand=True)
        self._setup_treeview_tags(self.preset_tree)
        self.preset_tree.bind("<<TreeviewSelect>>", self.on_preset_select)

        # 右侧面板
        right_panel = ttk.Frame(paned, padding=PADDING_VALUES["panel"])
        paned.add(right_panel, weight=2)
        right_card = ttk.Labelframe(right_panel, text="测速结果", padding=PADDING_VALUES["card"], style="Card.TLabelframe")
        right_card.pack(fill=BOTH, expand=True)

        # 结果列表 - 保留原版文字
        self.result_tree = ttk.Treeview(right_card, columns=["select", "ip", "domain", "delay", "jitter", "stability", "status"], show="headings")
        cols = [
            ("select", "选择", COLUMN_WIDTHS["select"]),
            ("ip", "IP 地址", COLUMN_WIDTHS["ip"]),
            ("domain", "域名", COLUMN_WIDTHS["domain"]),
            ("delay", "延迟 (ms)", COLUMN_WIDTHS["delay"]),
            ("jitter", "抖动 (ms)", COLUMN_WIDTHS["jitter"]),
            ("stability", "稳定性", COLUMN_WIDTHS["stability"]),
            ("status", "状态", COLUMN_WIDTHS["status"]),
        ]
        for c, t, w in cols:
            self.result_tree.heading(c, text=t)
            self.result_tree.column(c, width=w, anchor="center" if c == "select" else "w")
        self.result_tree.pack(fill=BOTH, expand=True, pady=(0, 10))
        self._setup_treeview_tags(self.result_tree)
        self.result_tree.bind("<Button-1>", self.on_tree_click)

        action_bar = ttk.Frame(right_card)
        action_bar.pack(fill=X)

        # 回滚 Hosts（从自动备份恢复）
        self.rollback_hosts_btn = ttk.Button(
            action_bar,
            text="↩ 回滚 Hosts",
            command=self.rollback_hosts,
            bootstyle=WARNING,
            width=BUTTON_WIDTHS["rollback_hosts"],
            state=DISABLED,
        )
        self.rollback_hosts_btn.pack(side=LEFT)

        # 底部按钮 - 保留原版文字
        self.write_best_btn = ttk.Button(
            action_bar,
            text="一键写入最优 IP",
            command=self.write_best_ip_to_hosts,
            bootstyle=SUCCESS,
            width=BUTTON_WIDTHS["write_best"],
        )
        self.write_best_btn.pack(side=RIGHT, padx=(8, 0))
        self.write_selected_btn = ttk.Button(
            action_bar,
            text="写入选中到 Hosts",
            command=self.write_selected_to_hosts,
            bootstyle=PRIMARY,
            width=BUTTON_WIDTHS["write_selected"],
        )
        self.write_selected_btn.pack(side=RIGHT)

        # 状态栏
        statusbar = ttk.Frame(self, padding=PADDING_VALUES["statusbar"])
        statusbar.pack(fill=X, pady=(12, 0))
        self.progress = ttk.Progressbar(statusbar, orient=HORIZONTAL, mode="determinate")
        self.progress.pack(side=LEFT, fill=X, expand=True)
        self.status_label = ttk.Label(statusbar, text="就绪", bootstyle=INFO)
        self.status_label.pack(side=RIGHT, padx=(10, 0))

    def _create_treeview(self, parent, cols, headers, widths):
        tv = ttk.Treeview(parent, columns=cols, show="headings")
        for c, h, w in zip(cols, headers, widths):
            tv.heading(c, text=h)
            tv.column(c, width=w)
        tv.pack(fill=BOTH, expand=True)
        self._setup_treeview_tags(tv)
        return tv

    # -----------------------------------------------------------------
    # Toast / small utils
    # -----------------------------------------------------------------
    def _toast(self, title: str, message: str, *, bootstyle: str = "info", duration: Optional[int] = None):
        if duration is None:
            duration = UI_CONFIG.get("toast", {}).get("default_duration_ms", 1800)
        try:
            if ToastNotification:
                ToastNotification(
                    title=title,
                    message=message,
                    duration=duration,
                    bootstyle=bootstyle,
                ).show_toast()
                self.logger.debug(f"Toast通知: {title} - {message}")
        except Exception as e:
            self.logger.warning(f"Toast通知显示失败: {e}", exc_info=True)

    def _format_remote_source_button_text(self, choice_label: str) -> str:
        label = (choice_label or "").strip()
        max_length = UI_OTHER_VALUES["remote_source_button_max_length"]
        if len(label) > max_length:
            label = label[:max_length - 1] + "…"
        return f"远程源：{label} ▾"

    # -----------------------------------------------------------------
    # Presets
    # -----------------------------------------------------------------
    def show_about(self):
        if AboutWindow:
            try:
                if self._about and self._about.window.winfo_exists():
                    self._about.window.lift()
                else:
                    self._about = AboutWindow(self.master)
            except Exception:
                messagebox.showinfo("关于", "SmartHostsTool\\nModern Glass UI")
        else:
            messagebox.showinfo("关于", "SmartHostsTool\\nModern Glass UI")

    def show_speed_test_settings(self):
        """显示测速设置窗口"""
        self.logger.info("打开测速设置窗口")
        
        # 创建设置窗口
        settings_window = ttk.Toplevel(self.master)
        settings_window.title("测速设置")
        settings_window.geometry("750x800")
        settings_window.resizable(True, True)
        settings_window.minsize(650, 650)
        
        # 居中显示
        try:
            settings_window.place_window_center()
        except Exception:
            sw = settings_window.winfo_screenwidth()
            sh = settings_window.winfo_screenheight()
            x = int(sw / 2 - 375)
            y = int(sh / 2 - 400)
            settings_window.geometry(f"750x800+{x}+{y}")
        
        # 模态窗口（延迟设置，确保窗口先显示）
        def set_modal():
            try:
                settings_window.transient(self.master)
                settings_window.grab_set()
                settings_window.focus_set()
            except Exception:
                pass
        
        # 主容器 - 简化布局
        main_container = ttk.Frame(settings_window, padding=15)
        main_container.pack(fill=BOTH, expand=True)
        
        # 标题
        title = ttk.Label(
            main_container,
            text="测速配置设置",
            font=("Segoe UI", 18, "bold"),
            bootstyle="primary",
        )
        title.pack(pady=(0, 15))
        
        # 创建 Notebook 用于分页
        # 使用明确的尺寸确保标签页显示
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill=BOTH, expand=True, pady=(0, 15))
        
        # 确保Notebook有足够的高度来显示标签
        notebook.update_idletasks()
        
        # 配置变量 - 必须在函数作用域内定义，以便保存函数访问
        tcp_config = self.speed_test_config.get("tcp", {})
        tls_config = self.speed_test_config.get("tls", {})
        icmp_config = self.speed_test_config.get("icmp", {})
        retry_config = self.speed_test_config.get("retry", {})
        advanced_config = self.speed_test_config.get("advanced", {})
        
        # 先创建所有Frame，确保它们都有内容
        
        # TCP 配置页
        tcp_frame = ttk.Frame(notebook, padding=20)
        # 配置grid权重，确保内容正确显示
        tcp_frame.grid_columnconfigure(0, weight=0)
        tcp_frame.grid_columnconfigure(1, weight=0)
        tcp_frame.grid_columnconfigure(2, weight=1)
        
        ttk.Label(tcp_frame, text="端口:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky=W, pady=12, padx=10)
        port_var = StringVar(value=str(tcp_config.get("port", 443)))
        port_entry = ttk.Entry(tcp_frame, textvariable=port_var, width=20)
        port_entry.grid(row=0, column=1, sticky=W, padx=10)
        ttk.Label(tcp_frame, text="(默认: 443)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=0, column=2, sticky=W, padx=10)
        
        ttk.Label(tcp_frame, text="尝试次数:", font=("Segoe UI", 10)).grid(row=1, column=0, sticky=W, pady=12, padx=10)
        attempts_var = StringVar(value=str(tcp_config.get("attempts", 5)))
        attempts_entry = ttk.Entry(tcp_frame, textvariable=attempts_var, width=20)
        attempts_entry.grid(row=1, column=1, sticky=W, padx=10)
        ttk.Label(tcp_frame, text="(默认: 5, 推荐: 3-10)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=1, column=2, sticky=W, padx=10)
        
        ttk.Label(tcp_frame, text="超时时间(秒):", font=("Segoe UI", 10)).grid(row=2, column=0, sticky=W, pady=12, padx=10)
        timeout_var = StringVar(value=str(tcp_config.get("timeout", 2.0)))
        timeout_entry = ttk.Entry(tcp_frame, textvariable=timeout_var, width=20)
        timeout_entry.grid(row=2, column=1, sticky=W, padx=10)
        ttk.Label(tcp_frame, text="(默认: 2.0, 推荐: 1.0-5.0)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=2, column=2, sticky=W, padx=10)
        
        ttk.Label(tcp_frame, text="间隔时间(秒):", font=("Segoe UI", 10)).grid(row=3, column=0, sticky=W, pady=12, padx=10)
        interval_var = StringVar(value=str(tcp_config.get("interval", 0.02)))
        interval_entry = ttk.Entry(tcp_frame, textvariable=interval_var, width=20)
        interval_entry.grid(row=3, column=1, sticky=W, padx=10)
        ttk.Label(tcp_frame, text="(默认: 0.02)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=3, column=2, sticky=W, padx=10)
        
        # 添加TCP标签页到Notebook
        notebook.add(tcp_frame, text="TCP 设置")
        
        # TLS 配置页
        tls_frame = ttk.Frame(notebook, padding=20)
        # 配置grid权重
        tls_frame.grid_columnconfigure(0, weight=0)
        tls_frame.grid_columnconfigure(1, weight=0)
        tls_frame.grid_columnconfigure(2, weight=1)
        
        tls_enabled_var = BooleanVar(value=tls_config.get("enabled", True))
        tls_check = ttk.Checkbutton(
            tls_frame,
            text="启用 TLS/SNI 验证",
            variable=tls_enabled_var
        )
        tls_check.grid(row=0, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        ttk.Label(tls_frame, text="超时时间(秒):", font=("Segoe UI", 10)).grid(row=1, column=0, sticky=W, pady=12, padx=10)
        tls_timeout_var = StringVar(value=str(tls_config.get("timeout", 3.0)))
        tls_timeout_entry = ttk.Entry(tls_frame, textvariable=tls_timeout_var, width=20)
        tls_timeout_entry.grid(row=1, column=1, sticky=W, padx=10)
        ttk.Label(tls_frame, text="(默认: 3.0, 推荐: 2.0-5.0)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=1, column=2, sticky=W, padx=10)
        
        verify_hostname_var = BooleanVar(value=tls_config.get("verify_hostname", False))
        verify_check = ttk.Checkbutton(
            tls_frame,
            text="验证主机名",
            variable=verify_hostname_var
        )
        verify_check.grid(row=2, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        strict_var = BooleanVar(value=tls_config.get("strict", False))
        strict_check = ttk.Checkbutton(
            tls_frame,
            text="严格模式 (TLS失败则判定IP不可用)",
            variable=strict_var
        )
        strict_check.grid(row=3, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        ttk.Label(tls_frame, text="尝试域名数量:", font=("Segoe UI", 10)).grid(row=4, column=0, sticky=W, pady=12, padx=10)
        try_hosts_limit_var = StringVar(value=str(tls_config.get("try_hosts_limit", 3)))
        try_hosts_limit_entry = ttk.Entry(tls_frame, textvariable=try_hosts_limit_var, width=20)
        try_hosts_limit_entry.grid(row=4, column=1, sticky=W, padx=10)
        ttk.Label(tls_frame, text="(默认: 3)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=4, column=2, sticky=W, padx=10)
        
        # 添加TLS标签页到Notebook
        notebook.add(tls_frame, text="TLS 设置")
        
        # ICMP 配置页
        icmp_frame = ttk.Frame(notebook, padding=20)
        # 配置grid权重
        icmp_frame.grid_columnconfigure(0, weight=0)
        icmp_frame.grid_columnconfigure(1, weight=0)
        icmp_frame.grid_columnconfigure(2, weight=1)
        
        icmp_enabled_var = BooleanVar(value=icmp_config.get("enabled", True))
        icmp_check = ttk.Checkbutton(
            icmp_frame,
            text="启用 ICMP Ping",
            variable=icmp_enabled_var
        )
        icmp_check.grid(row=0, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        ttk.Label(icmp_frame, text="超时时间(毫秒):", font=("Segoe UI", 10)).grid(row=1, column=0, sticky=W, pady=12, padx=10)
        icmp_timeout_var = StringVar(value=str(icmp_config.get("timeout_ms", 2000)))
        icmp_timeout_entry = ttk.Entry(icmp_frame, textvariable=icmp_timeout_var, width=20)
        icmp_timeout_entry.grid(row=1, column=1, sticky=W, padx=10)
        ttk.Label(icmp_frame, text="(默认: 2000)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=1, column=2, sticky=W, padx=10)
        
        fallback_only_var = BooleanVar(value=icmp_config.get("fallback_only", True))
        fallback_check = ttk.Checkbutton(
            icmp_frame,
            text="仅在 TCP 失败时使用",
            variable=fallback_only_var
        )
        fallback_check.grid(row=2, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        # 添加ICMP标签页到Notebook
        notebook.add(icmp_frame, text="ICMP 设置")
        
        # 重试配置页
        retry_frame = ttk.Frame(notebook, padding=20)
        # 配置grid权重
        retry_frame.grid_columnconfigure(0, weight=0)
        retry_frame.grid_columnconfigure(1, weight=0)
        retry_frame.grid_columnconfigure(2, weight=1)
        
        retry_enabled_var = BooleanVar(value=retry_config.get("enabled", True))
        retry_check = ttk.Checkbutton(
            retry_frame,
            text="启用重试",
            variable=retry_enabled_var
        )
        retry_check.grid(row=0, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        ttk.Label(retry_frame, text="最大重试次数:", font=("Segoe UI", 10)).grid(row=1, column=0, sticky=W, pady=12, padx=10)
        max_retries_var = StringVar(value=str(retry_config.get("max_retries", 2)))
        max_retries_entry = ttk.Entry(retry_frame, textvariable=max_retries_var, width=20)
        max_retries_entry.grid(row=1, column=1, sticky=W, padx=10)
        ttk.Label(retry_frame, text="(默认: 2)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=1, column=2, sticky=W, padx=10)
        
        ttk.Label(retry_frame, text="退避因子:", font=("Segoe UI", 10)).grid(row=2, column=0, sticky=W, pady=12, padx=10)
        backoff_factor_var = StringVar(value=str(retry_config.get("backoff_factor", 1.5)))
        backoff_factor_entry = ttk.Entry(retry_frame, textvariable=backoff_factor_var, width=20)
        backoff_factor_entry.grid(row=2, column=1, sticky=W, padx=10)
        ttk.Label(retry_frame, text="(默认: 1.5)", font=("Segoe UI", 9), bootstyle="secondary").grid(row=2, column=2, sticky=W, padx=10)
        
        # 添加重试标签页到Notebook
        notebook.add(retry_frame, text="重试设置")
        
        # 高级配置页
        advanced_frame = ttk.Frame(notebook, padding=20)
        # 配置grid权重
        advanced_frame.grid_columnconfigure(0, weight=1)
        
        measure_jitter_var = BooleanVar(value=advanced_config.get("measure_jitter", True))
        jitter_check = ttk.Checkbutton(
            advanced_frame,
            text="测量抖动 (Jitter)",
            variable=measure_jitter_var
        )
        jitter_check.grid(row=0, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        calculate_stability_var = BooleanVar(value=advanced_config.get("calculate_stability", True))
        stability_check = ttk.Checkbutton(
            advanced_frame,
            text="计算稳定性分数",
            variable=calculate_stability_var
        )
        stability_check.grid(row=1, column=0, columnspan=3, sticky=W, pady=12, padx=10)
        
        # 添加高级设置标签页到Notebook
        notebook.add(advanced_frame, text="高级设置")
        
        # 立即更新Notebook以确保标签页显示
        notebook.update_idletasks()
        settings_window.update_idletasks()
        settings_window.update()
        
        # 验证所有标签页都已添加
        tab_count = len(notebook.tabs())
        try:
            tab_names = [notebook.tab(tab, 'text') for tab in notebook.tabs()]
        except Exception as e:
            tab_names = []
            self.logger.warning(f"获取标签页名称失败: {e}")
        
        self.logger.info(f"测速设置窗口已创建，共 {tab_count} 个标签页")
        if tab_names:
            self.logger.info(f"标签页名称列表: {tab_names}")
        
        if tab_count != 5:
            self.logger.error(f"标签页数量异常！期望5个，实际{tab_count}个")
            if tab_names:
                self.logger.error(f"已添加的标签页: {tab_names}")
            # 尝试多次强制刷新
            for i in range(3):
                settings_window.update()
                notebook.update()
                settings_window.update_idletasks()
                tab_count_after = len(notebook.tabs())
                if tab_count_after == 5:
                    self.logger.info(f"第{i+1}次刷新后标签页数量恢复正常: {tab_count_after}")
                    break
                elif tab_count_after != tab_count:
                    self.logger.info(f"第{i+1}次刷新后标签页数量变化: {tab_count} -> {tab_count_after}")
        else:
            self.logger.info("所有标签页已成功添加并显示")
        
        # 按钮栏
        btn_frame = ttk.Frame(main_container)
        btn_frame.pack(fill=X, pady=(15, 0))
        
        def validate_int(value: str, name: str, min_val: int, max_val: int) -> tuple:
            """验证整数输入，返回 (是否有效, 值或错误信息)"""
            try:
                val = int(value.strip())
                if val < min_val or val > max_val:
                    return False, f"{name} 必须在 {min_val} 到 {max_val} 之间（当前值：{val}）"
                return True, val
            except ValueError:
                return False, f"{name} 必须是有效的整数（当前输入：'{value}'）"
        
        def validate_float(value: str, name: str, min_val: float, max_val: float) -> tuple:
            """验证浮点数输入，返回 (是否有效, 值或错误信息)"""
            try:
                val = float(value.strip())
                if val < min_val or val > max_val:
                    return False, f"{name} 必须在 {min_val} 到 {max_val} 之间（当前值：{val}）"
                return True, val
            except ValueError:
                return False, f"{name} 必须是有效的数字（当前输入：'{value}'）"
        
        def validate_all_inputs() -> tuple:
            """验证所有输入，返回 (是否全部有效, 错误信息列表, 配置字典)"""
            errors = []
            config = {}
            
            # TCP 配置验证
            config["tcp"] = {}
            
            ok, result = validate_int(port_var.get(), "TCP端口", 1, 65535)
            if ok:
                config["tcp"]["port"] = result
            else:
                errors.append(result)
            
            ok, result = validate_int(attempts_var.get(), "TCP尝试次数", 1, 50)
            if ok:
                config["tcp"]["attempts"] = result
            else:
                errors.append(result)
            
            ok, result = validate_float(timeout_var.get(), "TCP超时时间", 0.1, 60.0)
            if ok:
                config["tcp"]["timeout"] = result
            else:
                errors.append(result)
            
            ok, result = validate_float(interval_var.get(), "TCP间隔时间", 0.0, 10.0)
            if ok:
                config["tcp"]["interval"] = result
            else:
                errors.append(result)
            
            # TLS 配置验证
            config["tls"] = {}
            config["tls"]["enabled"] = tls_enabled_var.get()
            config["tls"]["verify_hostname"] = verify_hostname_var.get()
            config["tls"]["strict"] = strict_var.get()
            
            ok, result = validate_float(tls_timeout_var.get(), "TLS超时时间", 0.1, 60.0)
            if ok:
                config["tls"]["timeout"] = result
            else:
                errors.append(result)
            
            ok, result = validate_int(try_hosts_limit_var.get(), "尝试域名数量", 1, 20)
            if ok:
                config["tls"]["try_hosts_limit"] = result
            else:
                errors.append(result)
            
            # ICMP 配置验证
            config["icmp"] = {}
            config["icmp"]["enabled"] = icmp_enabled_var.get()
            config["icmp"]["fallback_only"] = fallback_only_var.get()
            
            ok, result = validate_int(icmp_timeout_var.get(), "ICMP超时时间(毫秒)", 100, 60000)
            if ok:
                config["icmp"]["timeout_ms"] = result
            else:
                errors.append(result)
            
            # 重试配置验证
            config["retry"] = {}
            config["retry"]["enabled"] = retry_enabled_var.get()
            
            ok, result = validate_int(max_retries_var.get(), "最大重试次数", 0, 20)
            if ok:
                config["retry"]["max_retries"] = result
            else:
                errors.append(result)
            
            ok, result = validate_float(backoff_factor_var.get(), "退避因子", 0.1, 10.0)
            if ok:
                config["retry"]["backoff_factor"] = result
            else:
                errors.append(result)
            
            # 高级配置（布尔值无需验证）
            config["advanced"] = {}
            config["advanced"]["measure_jitter"] = measure_jitter_var.get()
            config["advanced"]["calculate_stability"] = calculate_stability_var.get()
            
            return len(errors) == 0, errors, config
        
        def save_config():
            """保存配置（带输入验证）"""
            try:
                # 验证所有输入
                is_valid, errors, validated_config = validate_all_inputs()
                
                if not is_valid:
                    # 显示所有错误
                    error_msg = "配置验证失败，请修正以下问题：\n\n"
                    for i, err in enumerate(errors, 1):
                        error_msg += f"{i}. {err}\n"
                    messagebox.showerror("输入验证失败", error_msg)
                    self.logger.warning(f"配置验证失败: {errors}")
                    return
                
                # 合并配置（保留原有的其他配置项）
                new_config = self.speed_test_config.copy()
                
                # 更新 TCP 配置
                new_config["tcp"] = new_config.get("tcp", {}).copy()
                new_config["tcp"].update(validated_config["tcp"])
                
                # 更新 TLS 配置（保留 preferred_hosts 等其他配置）
                new_config["tls"] = new_config.get("tls", {}).copy()
                new_config["tls"].update(validated_config["tls"])
                
                # 更新 ICMP 配置
                new_config["icmp"] = new_config.get("icmp", {}).copy()
                new_config["icmp"].update(validated_config["icmp"])
                
                # 更新重试配置
                new_config["retry"] = new_config.get("retry", {}).copy()
                new_config["retry"].update(validated_config["retry"])
                
                # 更新高级配置
                new_config["advanced"] = new_config.get("advanced", {}).copy()
                new_config["advanced"].update(validated_config["advanced"])
                
                # 保存配置
                if self.speed_test_config_manager.save_config(new_config):
                    self.speed_test_config = new_config
                    self.logger.info("测速配置已保存")
                    self.logger.info(f"新配置: TCP端口={new_config['tcp']['port']}, "
                                    f"尝试次数={new_config['tcp']['attempts']}, "
                                    f"超时={new_config['tcp']['timeout']}秒")
                    messagebox.showinfo("成功", "配置已保存成功！\n新配置将在下次测速时生效。")
                    settings_window.destroy()
                else:
                    messagebox.showerror("错误", "保存配置失败，请检查日志文件。")
            except Exception as e:
                self.logger.exception(f"保存配置时出错: {e}")
                messagebox.showerror("错误", f"保存配置时发生错误：\n{e}")
        
        def reset_to_default():
            """重置为默认配置"""
            if messagebox.askyesno("确认", "确定要重置为默认配置吗？"):
                default_config = self.speed_test_config_manager.reset_to_default()
                self.speed_test_config = default_config
                self.logger.info("配置已重置为默认值")
                messagebox.showinfo("成功", "配置已重置为默认值！")
                settings_window.destroy()
                # 重新打开设置窗口以显示默认值
                self.show_speed_test_settings()
        
        ttk.Button(btn_frame, text="重置为默认", command=reset_to_default, bootstyle="warning", width=15).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=settings_window.destroy, bootstyle="secondary", width=15).pack(side=RIGHT, padx=5)
        ttk.Button(btn_frame, text="保存", command=save_config, bootstyle="success", width=15).pack(side=RIGHT, padx=5)
        
        # 绑定 ESC 键关闭窗口
        settings_window.bind("<Escape>", lambda e: settings_window.destroy())
        
        # 延迟设置模态窗口，确保Notebook先显示
        settings_window.after(100, set_modal)
        
        # 最终更新确保所有内容显示
        settings_window.update_idletasks()
        settings_window.update()

    def load_presets(self):
        """加载域名预设（保持原逻辑）。"""
        defaults = ["github.com", "bitbucket.org", "bilibili.com", "baidu.com"]
        presets: List[str] = []

        # 1) 用户目录
        data = safe_read_json(self.presets_file, None)
        if isinstance(data, list) and data:
            presets = [str(x).strip().lower() for x in data if str(x).strip()]
        else:
            # 2) 打包资源（可选）
            packaged = resource_path("presets.json")
            data2 = safe_read_json(packaged, None) if os.path.exists(packaged) else None
            if isinstance(data2, list) and data2:
                presets = [str(x).strip().lower() for x in data2 if str(x).strip()]
            else:
                presets = list(defaults)

            # 首次落盘到用户目录，保证后续可持久化
            self.custom_presets = presets
            self.save_presets()

        # 去重（保持顺序）
        seen = set()
        uniq: List[str] = []
        for d in presets:
            if d not in seen:
                seen.add(d)
                uniq.append(d)
        self.custom_presets = uniq if uniq else list(defaults)

        # 刷新 UI
        self.preset_tree.delete(*self.preset_tree.get_children())
        for idx, x in enumerate(self.custom_presets):
            self._tv_insert(self.preset_tree, [x], idx)

    def save_presets(self):
        try:
            atomic_write_json(self.presets_file, self.custom_presets)
        except Exception:
            pass

    def add_preset(self):
        s = simpledialog.askstring("添加预设", "请输入域名（例如：example.com）:")
        if s:
            s = s.strip().lower()
            if s not in self.custom_presets:
                self.custom_presets.append(s)
                idx = len(self.preset_tree.get_children())
                self._tv_insert(self.preset_tree, [s], idx)
                self.save_presets()

    def delete_preset(self):
        sel = self.preset_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的预设")
            return
        if messagebox.askyesno("确认", f"确定要删除选中的 {len(sel)} 个预设吗？"):
            for i in sel:
                v = self.preset_tree.item(i, "values")[0]
                if v in self.custom_presets:
                    self.custom_presets.remove(v)
                self.preset_tree.delete(i)
            self.save_presets()

    def on_preset_select(self, _):
        sel = [self.preset_tree.item(i, "values")[0] for i in self.preset_tree.selection()]
        self.current_selected_presets = sel
        self.is_github_selected = GITHUB_TARGET_DOMAIN in sel
        ok = bool(sel)
        self.resolve_preset_btn.config(state=NORMAL if ok else DISABLED)
        self.refresh_remote_btn.config(state=NORMAL if self.is_github_selected else DISABLED)
        self.check_start_btn()

    def check_start_btn(self):
        ok = bool(self.remote_hosts_data or self.smart_resolved_ips)
        self.start_test_btn.config(state=NORMAL if ok else DISABLED)

    # -----------------------------------------------------------------
    # Remote hosts
    # -----------------------------------------------------------------
    def on_source_change(self):
        c = self.remote_source_var.get()
        self.remote_source_btn_text.set(self._format_remote_source_button_text(c))
        mp = {l: u for l, u in REMOTE_HOSTS_SOURCE_CHOICES}
        self.remote_source_url_override = mp.get(c)
        if self.remote_source_url_override:
            self.status_label.config(text=f"已选择远程源：{c}", bootstyle=INFO)
            self._toast("数据源切换", f"已切换到：{c}", bootstyle="info")
        else:
            self.status_label.config(text="已选择远程源：自动（按优先级）", bootstyle=INFO)
            self._toast("数据源切换", "已切换到：自动（按优先级）", bootstyle="info")

    def refresh_remote_hosts(self):
        if not self.is_github_selected:
            self.logger.warning("刷新远程Hosts失败：未选择 github.com")
            return
        self.logger.info("开始刷新远程Hosts...")
        self.refresh_remote_btn.config(state=DISABLED)
        self.progress.configure(mode="indeterminate")
        self.progress.start(10)

        choice = self.remote_source_var.get()
        self.status_label.config(text=f"正在刷新远程Hosts…（源：{choice}）", bootstyle=INFO)
        threading.Thread(target=self._fetch_remote_hosts, daemon=True).start()

    def _fetch_remote_hosts(self):
        import asyncio

        async def fetch_async():
            try:
                if self.remote_source_url_override:
                    self.logger.info(f"从指定源获取Hosts: {self.remote_source_url_override}")
                    records, used_url = await self.remote_client.fetch_github_hosts_async(
                        url_override=self.remote_source_url_override,
                        concurrent=False
                    )
                else:
                    self.logger.info("从自动源获取Hosts（按优先级）")
                    records, used_url = await self.remote_client.fetch_github_hosts_async(concurrent=True)
                self.remote_hosts_data = records
                self.remote_hosts_source_url = used_url
                self.logger.info(f"成功获取远程Hosts: {len(records)} 条记录，来源: {used_url}")
                self.master.after(0, self._update_remote_hosts_ui)
            except Exception as e:
                self.logger.error(f"获取远程Hosts失败: {e}", exc_info=True)
                self.master.after(0, self.progress.stop)
                self.master.after(0, lambda: self.progress.configure(mode="determinate", value=0))
                self.master.after(0, lambda: self.refresh_remote_btn.config(state=NORMAL))
                self.master.after(0, lambda: messagebox.showerror("获取失败", f"无法获取远程Hosts:\n{e}"))

        try:
            asyncio.run(fetch_async())
        except Exception as e:
            self.logger.exception(f"异步获取远程Hosts时发生异常: {e}")
            self.master.after(0, self.progress.stop)
            self.master.after(0, lambda: self.progress.configure(mode="determinate", value=0))
            self.master.after(0, lambda: self.refresh_remote_btn.config(state=NORMAL))
            self.master.after(0, lambda: messagebox.showerror("获取失败", f"无法获取远程Hosts:\n{e}"))

    def _update_remote_hosts_ui(self):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)

        self.remote_tree.delete(*self.remote_tree.get_children())
        for idx, x in enumerate(self.remote_hosts_data):
            self._tv_insert(self.remote_tree, x, idx)

        src = self.remote_hosts_source_url or self.remote_source_var.get()
        self.status_label.config(
            text=f"远程Hosts刷新完成，共找到 {len(self.remote_hosts_data)} 条记录（来源：{src}）",
            bootstyle=SUCCESS,
        )
        self.refresh_remote_btn.config(state=NORMAL)
        self.check_start_btn()

        self._toast(
            "远程 Hosts",
            f"刷新完成：{len(self.remote_hosts_data)} 条（{src}）",
            bootstyle="success",
            duration=2200,
        )

    # -----------------------------------------------------------------
    # DNS resolve
    # -----------------------------------------------------------------
    def resolve_selected_presets(self):
        self.resolve_preset_btn.config(state=DISABLED)
        self.status_label.config(text="正在解析IP地址...", bootstyle=INFO)
        threading.Thread(target=self._resolve_ips_thread, daemon=True).start()

    def _resolve_ips_thread(self):
        res = self.resolver.resolve(self.current_selected_presets)
        self.smart_resolved_ips = res
        self.master.after(0, self._update_resolve_ui)

    def _update_resolve_ui(self):
        self.all_resolved_tree.delete(*self.all_resolved_tree.get_children())
        for idx, x in enumerate(self.smart_resolved_ips):
            self._tv_insert(self.all_resolved_tree, x, idx)
        self.status_label.config(text=f"解析完成，共找到 {len(self.smart_resolved_ips)} 个IP", bootstyle=SUCCESS)
        self.resolve_preset_btn.config(state=NORMAL)
        self.check_start_btn()

    # -----------------------------------------------------------------
    # Speed test
    # -----------------------------------------------------------------
    def start_test(self):
        """
        开始测速（修复版）
        关键点（保持原版行为）：
        1) 进度条实时更新：按 as_completed() 逐个回调 UI。
        2) 结果完整：同一 IP 可能对应多个域名，使用 ip -> [domains] 映射展开多行。
        3) 进度统计：按“唯一 IP 数”统计；结果表展示每个 (IP, 域名) 组合。
        """
        # 清空旧结果
        self.result_tree.delete(*self.result_tree.get_children())
        self.test_results = []

        raw_pairs = list(self.remote_hosts_data) + list(self.smart_resolved_ips)
        if not raw_pairs:
            messagebox.showinfo("提示", "没有可测试的IP地址，请先解析IP或刷新远程Hosts")
            return

        # 去除“完全重复的 (ip, domain)”
        seen_pair = set()
        pairs: List[Tuple[str, str]] = []
        for ip, dom in raw_pairs:
            key = (str(ip).strip(), str(dom).strip())
            if key in seen_pair:
                continue
            seen_pair.add(key)
            pairs.append(key)

        # ip -> [domains]
        self._ip_to_domains = {}
        for ip, dom in pairs:
            self._ip_to_domains.setdefault(ip, []).append(dom)

        ip_list = list(self._ip_to_domains.keys())

        # UI 状态
        self.start_test_btn.config(state=DISABLED)
        self.pause_test_btn.config(state=NORMAL)
        self.stop_test = False
        self._stop_event.clear()

        self.total_ip_tests = len(ip_list)
        self.completed_ip_tests = 0
        self.progress.configure(mode="determinate", value=0)
        self.status_label.config(text=f"正在测速… 0/{self.total_ip_tests} (IP)", bootstyle=INFO)

        use_advanced = bool(self.advanced_metrics_var.get())

        # TLS/SNI: 为同一 IP 生成候选域名列表（按优先级），避免只用第一个域名导致误判全失败
        # 使用自定义配置
        tls_cfg = self.speed_test_config.get("tls", {}) if isinstance(self.speed_test_config, dict) else {}
        preferred_hosts = tls_cfg.get("preferred_hosts", []) if isinstance(tls_cfg, dict) else []
        try_hosts_limit = int(tls_cfg.get("try_hosts_limit", 3)) if isinstance(tls_cfg, dict) else 3

        def build_sni_candidates(domains: List[str]) -> List[str]:
            cleaned: List[str] = []
            seen_l: set = set()
            for d in domains or []:
                dd = str(d).strip()
                if not dd:
                    continue
                dl = dd.lower()
                if dl in seen_l:
                    continue
                seen_l.add(dl)
                cleaned.append(dd)
            if not cleaned:
                return []
            lower_to_orig = {c.lower(): c for c in cleaned}
            out: List[str] = []
            for p in preferred_hosts or []:
                pl = str(p).strip().lower()
                if pl in lower_to_orig and lower_to_orig[pl] not in out:
                    out.append(lower_to_orig[pl])
            for c in cleaned:
                if c not in out:
                    out.append(c)
            return out[:max(1, try_hosts_limit)]
        if use_advanced:
            # 使用自定义配置创建 EnhancedSpeedTester
            tester = EnhancedSpeedTester(
                config=self.speed_test_config.copy(),  # 传入自定义配置
                stop_event=self._stop_event,
                stop_flag=lambda: self.stop_test,
            )
            workers = min(60, max(1, self.total_ip_tests))
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            self._futures = []
            
            # 获取 TCP 配置
            tcp_cfg = self.speed_test_config.get("tcp", {})
            port = tcp_cfg.get("port", 443)
            attempts = tcp_cfg.get("attempts", 5)
            timeout = tcp_cfg.get("timeout", 2.0)
            
            for ip in ip_list:
                doms = self._ip_to_domains.get(ip, [])
                cands = build_sni_candidates(doms)
                self._futures.append(self.executor.submit(
                    tester.test_with_retry, 
                    ip, 
                    sni_hosts=cands,
                    port=port,
                    attempts=attempts,
                    timeout=timeout
                ))
        else:
            # 获取 ICMP 配置
            icmp_cfg = self.speed_test_config.get("icmp", {})
            icmp_enabled = icmp_cfg.get("enabled", True) and bool(self.icmp_fallback_var.get())
            
            tester = SpeedTester(
                icmp_fallback=icmp_enabled,
                stop_event=self._stop_event,
                stop_flag=lambda: self.stop_test,
            )
            workers = min(60, max(1, self.total_ip_tests))
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            self._futures = []
            
            # 获取 TCP 配置
            tcp_cfg = self.speed_test_config.get("tcp", {})
            port = tcp_cfg.get("port", 443)
            attempts = tcp_cfg.get("attempts", 5)
            timeout = tcp_cfg.get("timeout", 2.0)
            
            for ip in ip_list:
                doms = self._ip_to_domains.get(ip, [])
                cands = build_sni_candidates(doms)
                self._futures.append(self.executor.submit(
                    tester.test_one_ip, 
                    ip, 
                    sni_hosts=cands,
                    port=port,
                    attempts=attempts,
                    timeout=timeout
                ))
        
        self.logger.info(f"开始测速，使用配置: TCP端口={port}, 尝试次数={attempts}, 超时={timeout}秒")

        threading.Thread(target=self._collect_speedtest_results, daemon=True).start()

    def _collect_speedtest_results(self):
        """后台收集测速结果：按完成顺序逐个更新 UI（保证进度条实时）。"""
        try:
            use_advanced = bool(self.advanced_metrics_var.get())
            for fut in concurrent.futures.as_completed(self._futures):
                if self._stop_event.is_set() or self.stop_test:
                    break
                try:
                    result = fut.result()
                    if use_advanced and len(result) == 4:
                        ip, ms, st, metadata = result
                        self._test_metadata[ip] = metadata
                    else:
                        ip, ms, st = result[:3]
                        metadata = {}
                except Exception as e:
                    ip, ms, st = "?", 9999, f"失败:{str(e)[:12]}"
                    metadata = {}

                domains = self._ip_to_domains.get(ip, [""])
                self.master.after(0, lambda ip=ip, domains=domains, ms=ms, st=st, meta=metadata: self._on_one_ip_finished(ip, domains, ms, st, meta))

            self.master.after(0, self._finish_speedtest_ui)
        finally:
            if self.executor:
                try:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self.executor.shutdown(wait=False)
                except Exception:
                    pass

    def _on_one_ip_finished(self, ip: str, domains: List[str], ms: int, status: str, metadata: Dict[str, Any] = None):
        if self._stop_event.is_set() or self.stop_test:
            return
        metadata = metadata or {}
        jitter = metadata.get("jitter", 0.0) or 0.0
        stability = metadata.get("stability_score", 0.0) or 0.0
        rows = [(ip, dom, ms, status, jitter, stability) for dom in domains]
        self._add_test_results_batch(rows, ip_completed_increment=1)

    def _finish_speedtest_ui(self):
        if self._stop_event.is_set() or self.stop_test:
            self.status_label.config(text=f"测速已停止（完成 {self.completed_ip_tests}/{self.total_ip_tests} 个IP）", bootstyle=WARNING)
        else:
            self.progress.configure(value=100)
            self.status_label.config(text=f"测速完成，共测试 {self.total_ip_tests} 个IP", bootstyle=SUCCESS)

        self.start_test_btn.config(state=NORMAL)
        self.pause_test_btn.config(state=DISABLED)
        
        # 如果是定时测速，执行回调
        if self._is_scheduled_test_running:
            self._is_scheduled_test_running = False
            self._on_scheduled_test_complete()
            self._schedule_next_test()

    def _add_test_results_batch(self, rows, ip_completed_increment: int = 0):
        for row in rows:
            if len(row) == 6:
                ip, domain, delay, status, jitter, stability = row
            else:
                ip, domain, delay, status = row[:4]
                jitter, stability = 0.0, 0.0
            self.test_results.append((ip, domain, int(delay), str(status), False, float(jitter), float(stability)))

        if ip_completed_increment:
            self.completed_ip_tests += int(ip_completed_increment)
            if self.total_ip_tests:
                self.progress["value"] = (self.completed_ip_tests / self.total_ip_tests) * 100.0
            else:
                self.progress["value"] = 0
            self.status_label.config(
                text=f"测速中… {self.completed_ip_tests}/{self.total_ip_tests} (IP)",
                bootstyle=INFO,
            )

        # 节流排序，避免界面卡顿
        if not self._sort_after_id:
            self._sort_after_id = self.master.after(200, self._flush_sort_results)

    def _rank_key_for_result_row(self, row):
        """综合排序/选优键：越小越好。

        兼顾：
        - 延迟(ms)：越低越好
        - 抖动(jitter)：越低越好（若可用）
        - 稳定性(stability_score)：越高越好（若可用）
        - TLS 通过：在接近情况下略微优先
        """
        try:
            ms = int(row[2])
        except Exception:
            ms = 10**9

        jitter = 0.0
        stability = 0.0
        status = ""
        try:
            status = str(row[3])
        except Exception:
            status = ""

        if len(row) >= 7:
            try:
                jitter = float(row[5]) or 0.0
            except Exception:
                jitter = 0.0
            try:
                stability = float(row[6]) or 0.0
            except Exception:
                stability = 0.0

        # 评分：以 ms 为主体，其他指标作为温和惩罚/奖励
        score = float(ms)

        # jitter 是“ms”量纲：直接线性加权即可（没有则不影响）
        if jitter and jitter > 0:
            score += jitter * 1.5

        # stability_score 通常为 0~100，越高越好；没有则不影响
        if stability and stability > 0:
            score += (100.0 - stability) * 2.0

        # TLS 通过（可用(TLS)）轻微加分：仅在分数接近时更偏向它
        if "(TLS)" in status:
            score -= 15.0

        # 二级排序：延迟更低优先
        return (score, float(ms))


    def _flush_sort_results(self):
        self._sort_after_id = None
        if not self.result_tree.winfo_exists():
            return
        self.result_tree.delete(*self.result_tree.get_children())
        for idx, row in enumerate(sorted(self.test_results, key=self._rank_key_for_result_row)):
            if len(row) == 7:
                ip, d, ms, st, sel, jitter, stability = row
                jitter_str = f"{jitter:.1f}" if jitter > 0 else "-"
                stability_str = f"{stability:.0f}" if stability > 0 else "-"
                self._tv_insert(self.result_tree, ["✓" if sel else "□", ip, d, ms, jitter_str, stability_str, st], idx, status=st)
            else:
                ip, d, ms, st, sel = row[:5]
                self._tv_insert(self.result_tree, ["✓" if sel else "□", ip, d, ms, "-", "-", st], idx, status=st)

    def pause_test(self):
        """停止当前测速任务（尽量快速释放线程池与UI状态）。"""
        self.stop_test = True
        self._stop_event.set()

        if self.executor:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self.executor.shutdown(wait=False)
            except Exception:
                pass

        self.status_label.config(text="测速已请求停止…", bootstyle=WARNING)
        try:
            self.progress.stop()
        except Exception:
            pass
        self._toast("测速暂停", "已停止/取消当前测速任务", bootstyle="warning", duration=2000)

        self.start_test_btn.config(state=NORMAL)
        self.pause_test_btn.config(state=DISABLED)

    # -----------------------------------------------------------------
    # Result selection
    # -----------------------------------------------------------------
    def on_tree_click(self, event):
        if self.result_tree.identify_column(event.x) != "#1":
            return
        item = self.result_tree.identify_row(event.y)
        if not item:
            return
        v = self.result_tree.item(item, "values")
        t_ip, t_dom = v[1], v[2]
        for i, row in enumerate(self.test_results):
            if len(row) == 7:
                ip, d, ms, st, s, jitter, stability = row
                if ip == t_ip and d == t_dom:
                    self.test_results[i] = (ip, d, ms, st, not s, jitter, stability)
                    jitter_str = f"{jitter:.1f}" if jitter > 0 else "-"
                    stability_str = f"{stability:.0f}" if stability > 0 else "-"
                    self.result_tree.item(item, values=["✓" if not s else "□", ip, d, ms, jitter_str, stability_str, st])
                    break
            else:
                ip, d, ms, st, s = row[:5]
                if ip == t_ip and d == t_dom:
                    self.test_results[i] = (ip, d, ms, st, not s, 0.0, 0.0)
                    self.result_tree.item(item, values=["✓" if not s else "□", ip, d, ms, "-", "-", st])
                    break

    # -----------------------------------------------------------------
    # Write / rollback hosts
    # -----------------------------------------------------------------
    def write_best_ip_to_hosts(self):
        # 优先写入 TLS/SNI 验证通过的结果；若某域名没有 TLS 通过项，再回退到普通“可用”项
        best_tls: Dict[str, Tuple[str, int, tuple]] = {}
        best_any: Dict[str, Tuple[str, int, tuple]] = {}

        for row in self.test_results:
            if len(row) == 7:
                ip, d, ms, st, _, _, _ = row
            else:
                ip, d, ms, st, _ = row[:5]

            st_s = str(st)
            if not st_s.startswith("可用"):
                continue

            # 记录任意可用
            rk = self._rank_key_for_result_row((ip, d, ms, st, False, 0.0, 0.0) if len(row) < 7 else row)
            if (d not in best_any) or (rk < best_any[d][2]):
                best_any[d] = (ip, ms, rk)

            # 记录 TLS 可用（更可信）
            if "(TLS)" in st_s:
                rk = self._rank_key_for_result_row((ip, d, ms, st, False, 0.0, 0.0) if len(row) < 7 else row)
                if (d not in best_tls) or (rk < best_tls[d][2]):
                    best_tls[d] = (ip, ms, rk)

        # 合并：TLS 优先
        best: Dict[str, Tuple[str, int, tuple]] = {}
        for d, v in best_any.items():
            best[d] = best_tls.get(d, v)

        if not best:
            messagebox.showinfo("提示", "没有可用的IP地址")
            return
        self._do_write([(ip, d) for d, (ip, _, _) in best.items()])

    def write_selected_to_hosts(self):
        sel = []
        for row in self.test_results:
            if len(row) == 7:
                ip, d, _, _, s, _, _ = row
            else:
                ip, d, _, _, s = row[:5]
            if s:
                sel.append((ip, d))
        if not sel:
            messagebox.showinfo("提示", "请先选择要写入的IP地址")
            return
        self._do_write(sel)

    def _do_write(self, records: List[Tuple[str, str]]):
        self.logger.info(f"开始写入Hosts文件，共 {len(records)} 条记录")
        try:
            # UI 提示：即便未管理员也先提示（写入时可能触发自动提权）
            if not is_admin(probe_path=HOSTS_PATH):
                self.logger.warning("当前没有管理员权限，将尝试自动提权")
                self._toast("提示", "当前没有管理员权限，将尝试写入Hosts文件...", bootstyle="info", duration=2000)

            # 1) 读取原 hosts + 备份
            content, enc = self.hosts_mgr.read_hosts_text()
            bak_path = self.hosts_mgr.create_backup()
            self.logger.info(f"已创建备份文件: {bak_path}")
            try:
                self.rollback_hosts_btn.config(state=NORMAL)
            except Exception as e:
                self.logger.warning(f"更新回滚按钮状态失败: {e}")

            # 2) 移除旧标记块（安全策略）
            rm = self.hosts_mgr.remove_existing_smart_block(content)
            if rm.marker_damaged:
                self.logger.warning("检测到Hosts标记可能损坏（Start/End不成对），采用安全写入策略")
                self._toast(
                    "提示",
                    "检测到 Hosts 标记可能损坏（Start/End 不成对）。已采用安全写入：不删除旧段，仅追加新段。必要时可点击\"回滚 Hosts\"。",
                    bootstyle="warning",
                    duration=4500,
                )

            # 3) 生成新块并追加到文件末尾
            blk = self.hosts_mgr.build_block(records)
            final_text = rm.content.rstrip() + blk

            # 4) 多方案写入（权限不足时可自动提权）
            self.logger.info(f"开始写入Hosts文件（编码: {enc}）")
            self.hosts_mgr.write_hosts_atomic(
                final_text,
                encoding=enc,
                allow_elevate=True,
                on_need_elevation=lambda: self._toast("权限不足", "写入Hosts文件需要管理员权限，将自动尝试提权...", bootstyle="warning", duration=3000),
            )
            self.logger.info("Hosts文件写入成功")

            # 5) 刷新 DNS
            self.logger.info("刷新DNS缓存...")
            self.hosts_mgr.flush_dns_cache()
            self.logger.info("DNS缓存刷新成功")

            messagebox.showinfo(
                "成功",
                f"已成功将 {len(records)} 条记录写入 Hosts 文件\n\n"
                f"写入前已自动备份：\n{bak_path}\n\n"
                f"备份目录：{self.hosts_mgr.backup_dir}\n"
                f"备份文件格式：hosts_YYYYMMDD_HHMMSS.bak\n\n"
                "如需恢复，请点击底部\"回滚 Hosts\"。",
            )
            self.status_label.config(text="Hosts文件已更新（已备份）", bootstyle=SUCCESS)
        except Exception as e:
            if "permission denied" in str(e).lower() or "拒绝访问" in str(e):
                self.logger.error(f"写入Hosts文件失败（权限不足）: {e}", exc_info=True)
                self._toast("权限不足", "写入Hosts文件失败，请以管理员身份运行程序", bootstyle="warning", duration=3000)
                messagebox.showerror("权限不足", f"写入Hosts文件失败: {e}\n请以管理员身份运行程序")
            else:
                self.logger.error(f"写入Hosts文件失败: {e}", exc_info=True)
                messagebox.showerror("错误", f"写入Hosts文件失败: {e}")

    def rollback_hosts(self):
        """回滚按钮：默认回滚到最近一次备份；也可选择备份文件回滚。"""
        if not is_admin(probe_path=HOSTS_PATH):
            self._toast("权限不足", "回滚Hosts文件需要管理员权限，请以管理员身份运行程序", bootstyle="warning", duration=3000)
            messagebox.showerror("权限不足", "回滚Hosts文件需要管理员权限，请以管理员身份运行程序")
            return

        latest = self.hosts_mgr.latest_backup()
        if not latest:
            messagebox.showwarning("没有备份", f"未找到备份文件\n备份目录：{self.hosts_mgr.backup_dir}")
            return

        use_latest = messagebox.askyesno("回滚 Hosts", f"是否回滚到最近备份？\n\n{latest}")
        bak_path = latest
        if not use_latest:
            bak_path = filedialog.askopenfilename(
                title="选择要回滚的备份文件",
                initialdir=self.hosts_mgr.backup_dir,
                filetypes=[("Hosts backup", "*.bak"), ("All files", "*.*")],
            )
            if not bak_path:
                return

        try:
            bak_text, used_enc = self.hosts_mgr.read_text_guess_encoding(bak_path)
            self.hosts_mgr.write_hosts_atomic(bak_text, encoding=used_enc, allow_elevate=False)
            self.hosts_mgr.flush_dns_cache()
            messagebox.showinfo(
                "回滚成功",
                f"已从备份恢复 hosts：\n{bak_path}\n\n备份目录：{self.hosts_mgr.backup_dir}",
            )
            self.status_label.config(text="Hosts 已回滚并刷新DNS", bootstyle=SUCCESS)
        except Exception as e:
            messagebox.showerror("回滚失败", f"回滚 Hosts 失败：{e}")

    # -----------------------------------------------------------------
    # OS helpers
    # -----------------------------------------------------------------
    def flush_dns(self, silent: bool = False):
        """刷新DNS缓存（与原版行为一致：silent=True 时用 Toast）。"""
        try:
            self.hosts_mgr.flush_dns_cache()
            if not silent:
                messagebox.showinfo("成功", "DNS缓存已成功刷新")
                self.status_label.config(text="DNS缓存已刷新", bootstyle=SUCCESS)
            else:
                self._toast("DNS刷新", "DNS缓存已成功刷新", bootstyle="success")
        except Exception:
            pass

    def view_hosts_file(self):
        try:
            self.hosts_mgr.open_hosts_file()
        except Exception:
            # 最保守的 fallback（仅Windows）
            if sys.platform == "win32":
                try:
                    os.startfile(HOSTS_PATH)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    except Exception:
                        startupinfo = None
                    subprocess.run(["notepad", HOSTS_PATH], startupinfo=startupinfo)
