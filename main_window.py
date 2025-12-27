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
)
from hosts_file import HostsFileManager
from services import DomainResolver, RemoteHostsClient, SpeedTester, EnhancedSpeedTester
from ui_visuals import GlassBackground
from utils import atomic_write_json, is_admin, resource_path, safe_read_json, user_data_path

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

        # Services / Managers
        self.remote_client = RemoteHostsClient(urls=list(REMOTE_HOSTS_URLS))
        self.resolver = DomainResolver(max_workers=UI_OTHER_VALUES["resolver_max_workers"])
        self.hosts_mgr = HostsFileManager(hosts_path=HOSTS_PATH)

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
        """退出清理"""
        self.stop_test = True
        self._stop_event.set()
        if self.executor:
            try:
                self.executor.shutdown(wait=False)
            except Exception:
                pass
        try:
            self.master.destroy()
        except Exception:
            pass
        sys.exit(0)

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
        more_menu.add_command(label="ℹ 关于", command=self.show_about)
        self.more_btn["menu"] = more_menu

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
        except Exception as e:
            print(f"Toast通知显示失败: {e}")

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
            return
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
                    records, used_url = await self.remote_client.fetch_github_hosts_async(
                        url_override=self.remote_source_url_override,
                        concurrent=False
                    )
                else:
                    records, used_url = await self.remote_client.fetch_github_hosts_async(concurrent=True)
                self.remote_hosts_data = records
                self.remote_hosts_source_url = used_url
                self.master.after(0, self._update_remote_hosts_ui)
            except Exception as e:
                self.master.after(0, self.progress.stop)
                self.master.after(0, lambda: self.progress.configure(mode="determinate", value=0))
                self.master.after(0, lambda: self.refresh_remote_btn.config(state=NORMAL))
                self.master.after(0, lambda: messagebox.showerror("获取失败", f"无法获取远程Hosts:\n{e}"))

        try:
            asyncio.run(fetch_async())
        except Exception as e:
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
        tls_cfg = SPEED_TEST_CONFIG.get("tls", {}) if isinstance(SPEED_TEST_CONFIG, dict) else {}
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
            tester = EnhancedSpeedTester(
                stop_event=self._stop_event,
                stop_flag=lambda: self.stop_test,
            )
            workers = min(60, max(1, self.total_ip_tests))
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            self._futures = []
            for ip in ip_list:
                doms = self._ip_to_domains.get(ip, [])
                cands = build_sni_candidates(doms)
                self._futures.append(self.executor.submit(tester.test_with_retry, ip, sni_hosts=cands))
        else:
            tester = SpeedTester(
                icmp_fallback=bool(self.icmp_fallback_var.get()),
                stop_event=self._stop_event,
                stop_flag=lambda: self.stop_test,
            )
            workers = min(60, max(1, self.total_ip_tests))
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            self._futures = []
            for ip in ip_list:
                doms = self._ip_to_domains.get(ip, [])
                cands = build_sni_candidates(doms)
                self._futures.append(self.executor.submit(tester.test_one_ip, ip, sni_hosts=cands))

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
        try:
            # UI 提示：即便未管理员也先提示（写入时可能触发自动提权）
            if not is_admin(probe_path=HOSTS_PATH):
                self._toast("提示", "当前没有管理员权限，将尝试写入Hosts文件...", bootstyle="info", duration=2000)

            # 1) 读取原 hosts + 备份
            content, enc = self.hosts_mgr.read_hosts_text()
            bak_path = self.hosts_mgr.create_backup()
            try:
                self.rollback_hosts_btn.config(state=NORMAL)
            except Exception:
                pass

            # 2) 移除旧标记块（安全策略）
            rm = self.hosts_mgr.remove_existing_smart_block(content)
            if rm.marker_damaged:
                self._toast(
                    "提示",
                    "检测到 Hosts 标记可能损坏（Start/End 不成对）。已采用安全写入：不删除旧段，仅追加新段。必要时可点击“回滚 Hosts”。",
                    bootstyle="warning",
                    duration=4500,
                )

            # 3) 生成新块并追加到文件末尾
            blk = self.hosts_mgr.build_block(records)
            final_text = rm.content.rstrip() + blk

            # 4) 多方案写入（权限不足时可自动提权）
            self.hosts_mgr.write_hosts_atomic(
                final_text,
                encoding=enc,
                allow_elevate=True,
                on_need_elevation=lambda: self._toast("权限不足", "写入Hosts文件需要管理员权限，将自动尝试提权...", bootstyle="warning", duration=3000),
            )

            # 5) 刷新 DNS
            self.hosts_mgr.flush_dns_cache()

            messagebox.showinfo(
                "成功",
                f"已成功将 {len(records)} 条记录写入 Hosts 文件\n\n"
                f"写入前已自动备份：\n{bak_path}\n\n"
                f"备份目录：{self.hosts_mgr.backup_dir}\n"
                f"备份文件格式：hosts_YYYYMMDD_HHMMSS.bak\n\n"
                "如需恢复，请点击底部“回滚 Hosts”。",
            )
            self.status_label.config(text="Hosts文件已更新（已备份）", bootstyle=SUCCESS)
        except Exception as e:
            if "permission denied" in str(e).lower() or "拒绝访问" in str(e):
                self._toast("权限不足", "写入Hosts文件失败，请以管理员身份运行程序", bootstyle="warning", duration=3000)
                messagebox.showerror("权限不足", f"写入Hosts文件失败: {e}\n请以管理员身份运行程序")
            else:
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
