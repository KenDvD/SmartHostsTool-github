# -*- coding: utf-8 -*-
"""
SmartHostsTool - 主程序（Modern Glass UI, ttkbootstrap）

本文件以“保留全部功能”为前提，重点改造 UI：
- 更现代的 AppBar（顶部操作区）
- 左侧：Tabs 以卡片分组（远程 Hosts / 预设）
- 右侧：测速结果 + 底部动作栏（写入 Hosts / 一键最优）
- 底部状态栏：进度 + 状态文本
- 玻璃质感：窗口轻透明 + 背景渐变（若 Pillow 可用更好看）

业务逻辑（解析 / 测速 / hosts 写入等）保持不变。
"""

from __future__ import annotations

import concurrent.futures
import ctypes
import json
import os
import re
import ipaddress
import socket
import subprocess
import sys
import threading
from datetime import datetime
from typing import List, Tuple, Optional

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, simpledialog, StringVar, Menu

from about_gui_modern import AboutWindow

# Pillow 可选（用于背景渐变）
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter
except Exception:  # pragma: no cover
    Image = None
    ImageTk = None
    ImageDraw = None
    ImageFilter = None

# ---------------------------------------------------------------------
# 资源路径（兼容 PyInstaller）
# ---------------------------------------------------------------------
BASE_PATH = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    return os.path.join(BASE_PATH, *parts)


# ---------------------------------------------------------------------
# 常量配置
# ---------------------------------------------------------------------
APP_THEME = "vapor"  # 可选：darkly / superhero / cyborg / flatly ...
GITHUB_TARGET_DOMAIN = "github.com"
# 远程 hosts 多源列表（按优先级轮询）
REMOTE_HOSTS_URLS = [
    # 你原来使用的站点（保留为高优先级）
    "https://github-hosts.tinsfox.com/hosts",
    # GitHub520 官方推荐
    "https://raw.hellogithub.com/hosts",
    # GitHub520 - GitHub Raw（直连）
    "https://raw.githubusercontent.com/521xueweihan/GitHub520/main/hosts",
    # GitHub520 - jsDelivr CDN（部分网络更稳）
    "https://fastly.jsdelivr.net/gh/521xueweihan/GitHub520@main/hosts",
    "https://cdn.jsdelivr.net/gh/521xueweihan/GitHub520@main/hosts",
    # GitHub Raw 加速代理（可选备用）
    "https://ghproxy.com/https://raw.githubusercontent.com/521xueweihan/GitHub520/main/hosts",
    # ineo6/hosts GitLab 镜像备用
    "https://gitlab.com/ineo6/hosts/-/raw/master/hosts",
]

# 远程 Hosts 源选择（用于 UI 下拉框）：(显示名, URL/None)
REMOTE_HOSTS_SOURCE_CHOICES = [
    ("自动（按优先级）", None),
    ("tinsfox（github-hosts.tinsfox.com）", REMOTE_HOSTS_URLS[0]),
    ("GitHub520（raw.hellogithub.com）", REMOTE_HOSTS_URLS[1]),
    ("GitHub520（raw.githubusercontent.com）", REMOTE_HOSTS_URLS[2]),
    ("GitHub520 CDN（fastly.jsdelivr.net）", REMOTE_HOSTS_URLS[3]),
    ("GitHub520 CDN（cdn.jsdelivr.net）", REMOTE_HOSTS_URLS[4]),
    ("GitHub Raw 代理（ghproxy.com）", REMOTE_HOSTS_URLS[5]),
    ("ineo6 镜像（gitlab.com）", REMOTE_HOSTS_URLS[6]),
]
# 超时： (连接超时, 读取超时)
REMOTE_FETCH_TIMEOUT = (5, 15)
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
HOSTS_START_MARK = "# === SmartHostsTool Start ==="
HOSTS_END_MARK = "# === SmartHostsTool End ==="


# ---------------------------------------------------------------------
# 权限检查
# ---------------------------------------------------------------------
def is_admin() -> bool:
    """Windows 管理员权限检测"""
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def show_admin_required_and_exit() -> None:
    """没有管理员权限时提示并退出（尽量避免在 GUI 创建前使用 Tk messagebox）。"""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "请以管理员身份运行程序，否则无法修改 Hosts 文件！",
                "权限不足",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
    else:
        print("需要管理员权限运行。")
    raise SystemExit(1)


# ---------------------------------------------------------------------
# 玻璃背景（拟态）
# ---------------------------------------------------------------------
class _GlassBackground:
    def __init__(self, master: ttk.Window):
        self.master = master
        self.canvas = ttk.Canvas(master, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._img = None
        self._img_id = None
        self._after_id = None

        master.bind("<Configure>", self._schedule_redraw)

    def lower(self):
        self.canvas.lower()

    def _schedule_redraw(self, _evt=None):
        if self._after_id:
            try:
                self.master.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.master.after(40, self._redraw)

    def _redraw(self):
        self._after_id = None
        w = max(640, int(self.master.winfo_width()))
        h = max(420, int(self.master.winfo_height()))

        if not (Image and ImageTk and ImageDraw and ImageFilter):
            self.canvas.configure(background="#0b1020")
            return

        # 渐变底 + 光晕
        img = Image.new("RGB", (w, h), "#0b1020")
        top = (16, 24, 40)
        mid = (17, 22, 54)
        bot = (10, 14, 28)

        px = img.load()
        for y in range(h):
            t = y / max(1, h - 1)
            if t < 0.55:
                tt = t / 0.55
                r = int(top[0] + (mid[0] - top[0]) * tt)
                g = int(top[1] + (mid[1] - top[1]) * tt)
                b = int(top[2] + (mid[2] - top[2]) * tt)
            else:
                tt = (t - 0.55) / 0.45
                r = int(mid[0] + (bot[0] - mid[0]) * tt)
                g = int(mid[1] + (bot[1] - mid[1]) * tt)
                b = int(mid[2] + (bot[2] - mid[2]) * tt)
            for x in range(w):
                px[x, y] = (r, g, b)

        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse((-w * 0.30, -h * 0.45, w * 0.85, h * 0.70), fill=(56, 189, 248, 55))
        draw.ellipse((w * 0.15, h * 0.10, w * 1.25, h * 1.15), fill=(167, 139, 250, 35))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=50))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

        # 微噪点
        noise = Image.effect_noise((w, h), 18).convert("L")
        noise = noise.point(lambda v: 18 if v > 120 else 0)
        noise_rgba = Image.merge("RGBA", (noise, noise, noise, noise))
        img = Image.alpha_composite(img.convert("RGBA"), noise_rgba).convert("RGB")

        self._img = ImageTk.PhotoImage(img)
        if self._img_id is None:
            self._img_id = self.canvas.create_image(0, 0, anchor="nw", image=self._img)
        else:
            self.canvas.itemconfig(self._img_id, image=self._img)


# ---------------------------------------------------------------------
# 主界面
# ---------------------------------------------------------------------
class HostsOptimizer(ttk.Frame):
    def __init__(self, master=None):
        print("HostsOptimizer.__init__ 开始")
        super().__init__(master, padding=14)
        self.master = master
        print(f"父类初始化完成，master: {master}")

        # 用于获取远程 hosts 的复用 Session（带重试/连接池）
        self._http = self._build_http_session()
        self.remote_hosts_source_url: Optional[str] = None


        # 远程源选择：None 表示自动按优先级轮询；否则固定使用某个 URL
        self.remote_source_url_override: Optional[str] = None
        self.master.title("智能 Hosts 测速工具")
        print("设置窗口标题成功")
        self.master.geometry("1080x680")
        print("设置窗口大小成功")
        self.master.minsize(980, 620)
        print("设置窗口最小大小成功")
        self.master.resizable(True, True)
        print("设置窗口可调整大小成功")

        # 轻透明（暂时禁用以排除问题）
        # try:
        #     self.master.attributes("-alpha", 0.985)
        #     print("设置窗口透明度成功")
        # except Exception as e:
        #     print(f"设置窗口透明度失败: {e}")

        # 背景 - 暂时禁用玻璃效果
        # try:
        #     self._bg = _GlassBackground(self.master)
        #     self._bg.lower()
        #     print("设置玻璃背景成功")
        # except Exception as e:
        #     print(f"设置玻璃背景失败: {e}")

        # 数据存储
        self.remote_hosts_data: List[Tuple[str, str]] = []
        self.smart_resolved_ips: List[Tuple[str, str]] = []
        self.custom_presets: List[str] = []
        self.test_results: List[Tuple[str, str, int, str, bool]] = []
        print("初始化数据存储成功")

        self.presets_file = resource_path("presets.json")
        print(f"设置预设文件路径: {self.presets_file}")

        # 选中状态标记
        self.current_selected_presets: List[str] = []
        self.is_github_selected = False
        print("初始化选中状态标记成功")

        # 测速控制
        self.stop_test = False
        self.executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        print("初始化测速控制成功")

        # About 窗口引用（防止重复打开）
        self._about: Optional[AboutWindow] = None
        print("初始化About窗口引用成功")

        print("开始设置样式...")
        self._setup_style()
        print("样式设置完成")

        # 先创建 UI，再加载预设（避免预设列表加载时机问题）
        print("开始创建 widgets...")
        self.create_widgets()
        print("widgets 创建完成")
        print("开始加载预设...")
        self.load_presets()
        print("预设加载完成")
        print("HostsOptimizer.__init__ 完成")

    def _setup_style(self):
        """统一调教字体/TreeView 行高等，使界面更“现代”。"""
        style = ttk.Style()

        try:
            # 更舒服的 TreeView 行高与字体
            style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
            style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

            # 卡片 Labelframe（视觉上更像“玻璃卡片”）
            style.configure("Card.TLabelframe", background=style.colors.bg, bordercolor=style.colors.border)
            style.configure("Card.TLabelframe.Label", background=style.colors.bg, foreground=style.colors.fg)
            style.configure("Card.TFrame", background=style.colors.bg)
        except Exception:
            pass

    # -------------------------
    # UI
    # -------------------------
    def create_widgets(self):
        print("create_widgets: 开始创建UI组件...")
        try:
            # AppBar
            appbar = ttk.Frame(self, padding=(10, 8))
            appbar.pack(fill=X)
            print("create_widgets: AppBar创建完成")

            left = ttk.Frame(appbar)
            left.pack(side=LEFT, fill=X, expand=True)

            title = ttk.Label(
                left,
                text="智能 Hosts 测速工具",
                font=("Segoe UI", 18, "bold"),
                bootstyle="inverse-primary",
                padding=(14, 10),
            )
            title.pack(side=LEFT, fill=X, expand=True)

            actions = ttk.Frame(appbar)
            actions.pack(side=RIGHT)

            self.about_btn = ttk.Button(actions, text="关于", command=self.show_about, bootstyle=INFO, width=8)
            self.about_btn.pack(side=LEFT, padx=5)

            # 远程源选择（下拉菜单按钮，仅影响「刷新远程 Hosts」）
            self.remote_source_var = StringVar(value=REMOTE_HOSTS_SOURCE_CHOICES[0][0])
            self.remote_source_btn_text = StringVar()
            self.remote_source_btn_text.set(self._format_remote_source_button_text(self.remote_source_var.get()))

            self.remote_source_btn = ttk.Menubutton(
                actions,
                textvariable=self.remote_source_btn_text,
                bootstyle="secondary",
                width=15,
            )
            self.remote_source_btn.pack(side=LEFT, padx=(12, 8))

            self.remote_source_menu = Menu(self.remote_source_btn, tearoff=0)
            for label, _url in REMOTE_HOSTS_SOURCE_CHOICES:
                self.remote_source_menu.add_radiobutton(
                    label=label,
                    variable=self.remote_source_var,
                    value=label,
                    command=self.on_remote_source_change,
                )
            self.remote_source_btn["menu"] = self.remote_source_menu



            self.refresh_remote_btn = ttk.Button(
                actions,
                text="刷新远程 Hosts",
                command=self.refresh_remote_hosts,
                bootstyle=SUCCESS,
                width=15,
                state=DISABLED,
            )
            self.refresh_remote_btn.pack(side=LEFT, padx=5)

            self.flush_dns_btn = ttk.Button(actions, text="刷新 DNS", command=self.flush_dns, bootstyle=INFO, width=10)
            self.flush_dns_btn.pack(side=LEFT, padx=5)

            self.view_hosts_btn = ttk.Button(
                actions, text="查看 Hosts 文件", command=self.view_hosts_file, bootstyle=SECONDARY, width=12
            )
            self.view_hosts_btn.pack(side=LEFT, padx=5)

            self.start_test_btn = ttk.Button(
                actions, text="开始测速", command=self.start_test, bootstyle=PRIMARY, width=10, state=DISABLED
            )
            self.start_test_btn.pack(side=LEFT, padx=5)

            self.pause_test_btn = ttk.Button(
                actions, text="暂停测速", command=self.pause_test, bootstyle=WARNING, width=10, state=DISABLED
            )
            self.pause_test_btn.pack(side=LEFT, padx=5)

            # 主体（左右分栏）
            body = ttk.Frame(self)
            body.pack(fill=BOTH, expand=True, pady=(12, 0))

            paned = ttk.PanedWindow(body, orient=HORIZONTAL)
            paned.pack(fill=BOTH, expand=True)

            # 左侧：Tabs
            left_panel = ttk.Frame(paned, padding=10)
            paned.add(left_panel, weight=1)

            left_card = ttk.Labelframe(left_panel, text="配置", padding=10, style="Card.TLabelframe")
            left_card.pack(fill=BOTH, expand=True)

            notebook = ttk.Notebook(left_card)
            notebook.pack(fill=BOTH, expand=True)

            # 远程 Hosts
            self.remote_frame = ttk.Frame(notebook, padding=8)
            notebook.add(self.remote_frame, text="远程 Hosts（仅 GitHub）")

            self.remote_tree = ttk.Treeview(self.remote_frame, columns=["ip", "domain"], show="headings", height=14)
            self.remote_tree.heading("ip", text="IP 地址")
            self.remote_tree.heading("domain", text="域名")
            self.remote_tree.column("ip", width=140)
            self.remote_tree.column("domain", width=240)
            self.remote_tree.pack(fill=BOTH, expand=True)

            # 自定义预设
            self.custom_frame = ttk.Frame(notebook, padding=8)
            notebook.add(self.custom_frame, text="自定义预设")
            
            # 所有解析结果
            self.all_resolved_frame = ttk.Frame(notebook, padding=8)
            notebook.add(self.all_resolved_frame, text="🔍 所有解析结果")
            
            self.all_resolved_tree = ttk.Treeview(self.all_resolved_frame, columns=["ip", "domain"], show="headings", height=14)
            self.all_resolved_tree.heading("ip", text="IP 地址")
            self.all_resolved_tree.heading("domain", text="域名")
            self.all_resolved_tree.column("ip", width=140)
            self.all_resolved_tree.column("domain", width=240)
            self.all_resolved_tree.pack(fill=BOTH, expand=True)

            custom_toolbar = ttk.Frame(self.custom_frame)
            custom_toolbar.pack(fill=X, pady=(0, 10))

            self.add_preset_btn = ttk.Button(custom_toolbar, text="添加", command=self.add_preset, bootstyle=SUCCESS, width=8)
            self.add_preset_btn.pack(side=LEFT, padx=(0, 6))

            self.delete_preset_btn = ttk.Button(custom_toolbar, text="删除", command=self.delete_preset, bootstyle=DANGER, width=8)
            self.delete_preset_btn.pack(side=LEFT, padx=6)

            self.resolve_preset_btn = ttk.Button(custom_toolbar, text="批量解析", command=self.resolve_selected_presets, bootstyle=INFO, width=12)
            self.resolve_preset_btn.pack(side=LEFT, padx=6)

            tip = ttk.Label(
                self.custom_frame,
                text="提示：按住 Ctrl/Shift 可多选域名；选中 github.com 后可启用「刷新远程 Hosts」。",
                bootstyle="secondary",
                wraplength=320,
                justify=LEFT,
            )
            tip.pack(fill=X, pady=(0, 10))

            self.preset_tree = ttk.Treeview(self.custom_frame, columns=["domain"], show="headings", height=14)
            self.preset_tree.heading("domain", text="域名")
            self.preset_tree.column("domain", width=310)
            self.preset_tree.configure(selectmode="extended")
            self.preset_tree.pack(fill=BOTH, expand=True)

            # 右侧：测速结果
            right_panel = ttk.Frame(paned, padding=10)
            paned.add(right_panel, weight=2)

            right_card = ttk.Labelframe(right_panel, text="测速结果", padding=10, style="Card.TLabelframe")
            right_card.pack(fill=BOTH, expand=True)

            self.result_tree = ttk.Treeview(
                right_card, columns=["select", "ip", "domain", "delay", "status"], show="headings"
            )
            self.result_tree.heading("select", text="选择")
            self.result_tree.heading("ip", text="IP 地址")
            self.result_tree.heading("domain", text="域名")
            self.result_tree.heading("delay", text="延迟 (ms)")
            self.result_tree.heading("status", text="状态")
            self.result_tree.column("select", width=64, anchor="center")
            self.result_tree.column("ip", width=150)
            self.result_tree.column("domain", width=240)
            self.result_tree.column("delay", width=100)
            self.result_tree.column("status", width=100)
            self.result_tree.pack(fill=BOTH, expand=True, pady=(0, 10))

            self.result_tree.bind("<Button-1>", self.on_tree_click)

            # 动作区
            action_bar = ttk.Frame(right_card)
            action_bar.pack(fill=X)

            self.write_best_btn = ttk.Button(
                action_bar, text="一键写入最优 IP", command=self.write_best_ip_to_hosts, bootstyle=SUCCESS, width=18
            )
            self.write_best_btn.pack(side=RIGHT, padx=(8, 0))

            self.write_selected_btn = ttk.Button(
                action_bar, text="写入选中到 Hosts", command=self.write_selected_to_hosts, bootstyle=PRIMARY, width=18
            )
            self.write_selected_btn.pack(side=RIGHT)

            # 底部状态栏
            statusbar = ttk.Frame(self, padding=(10, 8))
            statusbar.pack(fill=X, pady=(12, 0))

            self.progress = ttk.Progressbar(statusbar, orient=HORIZONTAL, mode="determinate")
            self.progress.pack(side=LEFT, fill=X, expand=True)

            self.status_label = ttk.Label(statusbar, text="就绪", bootstyle=INFO)
            self.status_label.pack(side=RIGHT, padx=(10, 0))

            # 事件
            self.preset_tree.bind("<<TreeviewSelect>>", self.on_preset_select)

            # 显示界面
            self.pack(fill=BOTH, expand=True)
            print("create_widgets: UI组件创建完成")
        except Exception as e:
            print(f"create_widgets: 创建UI时发生错误: {e}")
            import traceback
            traceback.print_exc()

    # -------------------------
    # About
    # -------------------------
    def show_about(self):
        """显示关于窗口（避免重复打开）"""
        try:
            if self._about and self._about.window.winfo_exists():
                self._about.window.lift()
                self._about.window.focus_force()
                return
        except Exception:
            pass
        self._about = AboutWindow(self.master)


    # -------------------------
    # Remote source selector (UI)
    # -------------------------
    
    def _format_remote_source_button_text(self, choice_label: str) -> str:
        """把远程源选择显示成更紧凑的按钮文本。"""
        label = (choice_label or "").strip()
        # 按钮上尽量短一点，菜单里仍保留完整描述
        if len(label) > 16:
            label = label[:15] + "…"
        return f"远程源：{label} ▾"

    def _toast(self, title: str, message: str, *, bootstyle: str = "info", duration: int = 1800):
        """轻量提示：优先用 ttkbootstrap 的 ToastNotification；不可用则静默跳过。"""
        try:
            from ttkbootstrap.toast import ToastNotification  # ttkbootstrap 官方 toast 模块
            ToastNotification(
                title=title,
                message=message,
                duration=duration,
                bootstyle=bootstyle,
            ).show_toast()
        except Exception:
            # 不影响主流程
            pass

    def on_remote_source_change(self, _event=None):
        """远程 Hosts 源下拉选择变化。"""
        choice = None
        try:
            choice = self.remote_source_var.get()
        except Exception:
            return

        # 同步更新按钮显示
        try:
            self.remote_source_btn_text.set(self._format_remote_source_button_text(choice))
        except Exception:
            pass

        mapping = {label: url for (label, url) in REMOTE_HOSTS_SOURCE_CHOICES}
        self.remote_source_url_override = mapping.get(choice)

        # 轻提示：不打断用户操作
        if self.remote_source_url_override:
            self.status_label.config(text=f"已选择远程源：{choice}", bootstyle=INFO)
        else:
            self.status_label.config(text="已选择远程源：自动（按优先级）", bootstyle=INFO)


    def _stop_progress_indeterminate_safe(self):
        """线程回调中安全停止 indeterminate 进度条动画。"""
        try:
            self.progress.stop()
            self.progress.configure(mode="determinate")
        except Exception:
            pass

    # -------------------------
    # Presets
    # -------------------------
    def load_presets(self):
        """加载预设网址列表并刷新 TreeView"""
        default_presets = ["github.com", "bitbucket.org", "bilibili.com", "baidu.com"]

        try:
            if os.path.exists(self.presets_file):
                with open(self.presets_file, "r", encoding="utf-8") as f:
                    self.custom_presets = json.load(f)
            else:
                self.custom_presets = default_presets
        except Exception as e:
            messagebox.showerror("错误", f"加载预设失败: {e}")
            self.custom_presets = default_presets

        for item in self.preset_tree.get_children():
            self.preset_tree.delete(item)
        for domain in self.custom_presets:
            self.preset_tree.insert("", "end", values=[domain])

    def save_presets(self):
        """保存预设到文件"""
        try:
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(self.custom_presets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("错误", f"保存预设失败: {e}")

    def add_preset(self):
        """添加新的预设网址"""
        domain = simpledialog.askstring("添加预设", "请输入域名（例如：example.com）:")
        if not domain:
            return
        domain = domain.strip().lower()
        if domain in self.custom_presets:
            return

        if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$", domain):
            self.custom_presets.append(domain)
            self.preset_tree.insert("", "end", values=[domain])
            self.save_presets()
        else:
            messagebox.showerror("格式错误", "请输入有效的域名格式（例如：example.com）")

    def delete_preset(self):
        """删除选中的预设网址"""
        selected_items = self.preset_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择要删除的预设")
            return

        if messagebox.askyesno("确认", f"确定要删除选中的 {len(selected_items)} 个预设吗？"):
            for item in selected_items:
                domain = self.preset_tree.item(item, "values")[0]
                if domain in self.custom_presets:
                    self.custom_presets.remove(domain)
                self.preset_tree.delete(item)
            self.save_presets()

    # -------------------------
    # Selection & Resolve
    # -------------------------
    def on_preset_select(self, _event):
        selected_items = self.preset_tree.selection()
        self.current_selected_presets = [self.preset_tree.item(item, "values")[0] for item in selected_items]
        self.is_github_selected = GITHUB_TARGET_DOMAIN in self.current_selected_presets

        if self.current_selected_presets:
            self.resolve_preset_btn.config(state=NORMAL)
            self.start_test_btn.config(state=NORMAL if (self.remote_hosts_data or self.smart_resolved_ips) else DISABLED)
            self.refresh_remote_btn.config(state=NORMAL if self.is_github_selected else DISABLED)
        else:
            self.resolve_preset_btn.config(state=DISABLED)
            self.start_test_btn.config(state=DISABLED)
            self.refresh_remote_btn.config(state=DISABLED)

    def resolve_selected_presets(self):
        if not self.current_selected_presets:
            return

        self.status_label.config(text="正在解析IP地址...", bootstyle=INFO)
        self.resolve_preset_btn.config(state=DISABLED)

        self.smart_resolved_ips = []
        threading.Thread(target=self._resolve_ips_thread, daemon=True).start()

    def _resolve_ips_thread(self):
        print(f"_resolve_ips_thread: 开始解析IP，共{len(self.current_selected_presets)}个域名需要解析")
        try:
            for domain in self.current_selected_presets:
                print(f"_resolve_ips_thread: 正在解析域名 {domain}")
                try:
                    ip_addresses = socket.gethostbyname_ex(domain)[2]
                    print(f"_resolve_ips_thread: 域名 {domain} 解析到 {len(ip_addresses)} 个IP")
                    for ip in ip_addresses:
                        self.smart_resolved_ips.append((ip, domain))
                        print(f"_resolve_ips_thread: 添加IP {ip} 对应域名 {domain}")
                except Exception as e:
                    print(f"_resolve_ips_thread: 解析域名 {domain} 失败: {e}")
                    self.master.after(
                        0, lambda d=domain, err=e: messagebox.showerror("解析错误", f"解析 {d} 失败: {err}")
                    )

            print(f"_resolve_ips_thread: 解析完成，共找到{len(self.smart_resolved_ips)}个IP")
            self.master.after(0, self._update_resolve_ui)
        except Exception as e:
            print(f"_resolve_ips_thread: 解析过程出错: {e}")
            import traceback
            traceback.print_exc()
            self.master.after(0, lambda err=e: messagebox.showerror("错误", f"解析过程出错: {err}"))
            self.master.after(0, lambda: self.status_label.config(text="解析失败", bootstyle=DANGER))
            self.master.after(0, lambda: self.resolve_preset_btn.config(state=NORMAL))

    def _update_resolve_ui(self):
        print(f"_update_resolve_ui: 开始更新UI，共有{len(self.smart_resolved_ips)}个解析结果")
        try:
            # 清空远程Hosts树
            print(f"_update_resolve_ui: 清空远程Hosts树，当前有{len(self.remote_tree.get_children())}个项目")
            for item in self.remote_tree.get_children():
                self.remote_tree.delete(item)
            
            # 清空所有解析结果标签页
            print(f"_update_resolve_ui: 清空所有解析结果树，当前有{len(self.all_resolved_tree.get_children())}个项目")
            for item in self.all_resolved_tree.get_children():
                self.all_resolved_tree.delete(item)

            if self.is_github_selected:
                github_ips = [(ip, domain) for ip, domain in self.smart_resolved_ips if domain == GITHUB_TARGET_DOMAIN]
                for ip, domain in github_ips:
                    self.remote_tree.insert("", "end", values=[ip, domain])
            
            # 在所有解析结果标签页中显示所有解析的IP
            for ip, domain in self.smart_resolved_ips:
                self.all_resolved_tree.insert("", "end", values=[ip, domain])

            self.status_label.config(text=f"解析完成，共找到 {len(self.smart_resolved_ips)} 个IP", bootstyle=SUCCESS)
            self.resolve_preset_btn.config(state=NORMAL)
            self.start_test_btn.config(state=NORMAL)
            print("_update_resolve_ui: UI更新完成")
        except Exception as e:
            print(f"_update_resolve_ui: 更新UI时发生错误: {e}")
            import traceback
            traceback.print_exc()


    # -------------------------
    # Remote hosts - 网络与校验（更稳）
    # -------------------------
    def _build_http_session(self) -> requests.Session:
        """构造一个带重试/连接池的 Session，用于远程 hosts 获取。"""
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": "SmartHostsTool/Modern (+https://github.com/KenDvD/SmartHostsTool-github)",
                "Accept": "text/plain, */*",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,  # 指数退避
            status_forcelist=(429, 500, 502, 503, 504),
            method_whitelist=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def _looks_like_hosts(self, text: str) -> bool:
        """粗略判断返回内容是否像 hosts（避免拿到 HTML/错误页）。"""
        head = (text or "")[:400].lower()
        if "<html" in head or "<!doctype" in head:
            return False

        # 常见标记（GitHub520/ineo6）
        if "github520 host start" in head or "github host start" in head or "github hosts" in head:
            return True

        good = 0
        for line in (text or "").splitlines()[:400]:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 2:
                continue
            ip, host = parts[0], parts[1]
            try:
                ipaddress.ip_address(ip)
            except Exception:
                continue
            if "." in host:
                good += 1
            if good >= 8:
                return True
        return False

    def _download_remote_hosts_text(self) -> tuple[str, str]:
        """获取远程 hosts 文本，返回 (text, used_url)。

        - 若用户在 UI 中选择了固定远程源，则仅请求该 URL；
        - 否则按 REMOTE_HOSTS_URLS 优先级轮询，任一源成功即返回。
        """
        errors: List[str] = []

        url_list = [self.remote_source_url_override] if self.remote_source_url_override else list(REMOTE_HOSTS_URLS)

        for url in url_list:
            try:
                resp = self._http.get(url, timeout=REMOTE_FETCH_TIMEOUT, allow_redirects=True)
                resp.raise_for_status()

                # 尽量使用响应编码；不行则 fallback
                if not resp.encoding:
                    resp.encoding = "utf-8"
                text = resp.text

                if not self._looks_like_hosts(text):
                    raise ValueError("内容校验失败：返回内容不像 hosts（可能被劫持/返回 HTML/错误页）")

                return text, url
            except Exception as e:
                errors.append(f"{url} -> {type(e).__name__}: {e}")

        raise RuntimeError("所有远程 hosts 源均获取失败：\n" + "\n".join(errors))


    # -------------------------
    # Remote hosts (GitHub only)
    # -------------------------
    def refresh_remote_hosts(self):
        if not self.is_github_selected:
            return

        # 远程获取时长不可预测：用 indeterminate 动画反馈“仍在工作”
        try:
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(10)
        except Exception:
            pass

        choice = None
        try:
            choice = self.remote_source_var.get()
        except Exception:
            choice = "自动（按优先级）"

        self.status_label.config(text=f"正在刷新远程Hosts…（源：{choice}）", bootstyle=INFO)
        self.refresh_remote_btn.config(state=DISABLED)
        threading.Thread(target=self._fetch_remote_hosts, daemon=True).start()

    def _fetch_remote_hosts(self):
        try:
            hosts_content, used_url = self._download_remote_hosts_text()

            self.remote_hosts_source_url = used_url

            # 兼容“按行 hosts”以及“单行+空格分隔多条记录”的 hosts 文本
            # 直接在全文里提取 (IP, Domain) 对，避免被注释/换行格式影响。
            pairs = re.findall(
                r'((?:\d{1,3}\.){3}\d{1,3}|[0-9A-Fa-f:]{2,})\s+([A-Za-z0-9.-]+)',
                hosts_content,
            )

            self.remote_hosts_data = []
            for ip, domain in pairs:
                try:
                    ipaddress.ip_address(ip)
                except Exception:
                    continue
                if "github" in domain.lower():
                    self.remote_hosts_data.append((ip, domain))

            self.master.after(0, self._update_remote_hosts_ui)
        except Exception as e:
            self.master.after(0, lambda: self._stop_progress_indeterminate_safe())
            self.master.after(0, lambda err=e: messagebox.showerror("获取失败", f"无法获取远程Hosts:\n{err}"))
            self.master.after(0, lambda: self._toast("远程 Hosts", "获取失败：已尝试备用源（详见弹窗）", bootstyle="danger", duration=2600))
            self.master.after(0, lambda: self.status_label.config(text="远程Hosts获取失败", bootstyle=DANGER))
            self.master.after(0, lambda: self.refresh_remote_btn.config(state=NORMAL))

    def _update_remote_hosts_ui(self):
        # 结束远程获取动画
        try:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.configure(value=0)
        except Exception:
            pass

        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)

        for ip, domain in self.remote_hosts_data:
            self.remote_tree.insert("", "end", values=[ip, domain])

        source = f"（来源：{self.remote_hosts_source_url}）" if getattr(self, "remote_hosts_source_url", None) else ""
        self.status_label.config(text=f"远程Hosts刷新完成，共找到 {len(self.remote_hosts_data)} 条记录{source}", bootstyle=SUCCESS)
        self._toast("远程 Hosts", f"刷新完成：{len(self.remote_hosts_data)} 条（{self.remote_source_var.get()}）", bootstyle="success", duration=2200)
        self.refresh_remote_btn.config(state=NORMAL)
        self.start_test_btn.config(state=NORMAL)

    # -------------------------
    # Speed test
    # -------------------------
    def start_test(self):
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.test_results = []

        test_data: List[Tuple[str, str]] = []
        if self.remote_hosts_data:
            test_data.extend(self.remote_hosts_data)
        if self.smart_resolved_ips:
            test_data.extend(self.smart_resolved_ips)

        if not test_data:
            messagebox.showinfo("提示", "没有可测试的IP地址，请先解析IP或刷新远程Hosts")
            return

        self.start_test_btn.config(state=DISABLED)
        self.pause_test_btn.config(state=NORMAL)
        self.resolve_preset_btn.config(state=DISABLED)
        self.refresh_remote_btn.config(state=DISABLED)
        self.stop_test = False

        # 已知总量：用 determinate 百分比
        try:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.configure(value=0, maximum=100)
        except Exception:
            self.progress["value"] = 0

        self.total_tests = len(test_data)
        self.completed_tests = 0

        self.status_label.config(text=f"正在测速… 0/{self.total_tests}", bootstyle=INFO)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

        for ip, domain in test_data:
            if self.stop_test:
                break
            self.executor.submit(self._test_ip_delay, ip, domain)

        threading.Thread(target=self._monitor_test_completion, daemon=True).start()

    def _test_ip_delay(self, ip: str, domain: str):
        try:
            start_time = datetime.now()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                result = s.connect_ex((ip, 80))
                end_time = datetime.now()

                if self.stop_test:
                    return

                if result == 0:
                    delay = int((end_time - start_time).total_seconds() * 1000)
                    self.master.after(0, lambda: self._add_test_result(ip, domain, delay, "可用", False))
                else:
                    self.master.after(0, lambda: self._add_test_result(ip, domain, 9999, "超时", False))
        except Exception:
            if not self.stop_test:
                self.master.after(0, lambda: self._add_test_result(ip, domain, 9999, "错误", False))

    def _add_test_result(self, ip: str, domain: str, delay: int, status: str, selected: bool):
        self.test_results.append((ip, domain, delay, status, selected))
        self.result_tree.insert("", "end", values=["□" if not selected else "✓", ip, domain, delay, status])

        self.completed_tests += 1
        progress = (self.completed_tests / self.total_tests) * 100
        try:
            self.progress.configure(value=progress)
        except Exception:
            self.progress["value"] = progress

        # 状态栏实时反馈
        self.status_label.config(text=f"测速中… {self.completed_tests}/{self.total_tests}", bootstyle=INFO)

        self._sort_test_results()

    def _sort_test_results(self):
        current_selection = [self.result_tree.item(item, "values") for item in self.result_tree.selection()]

        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        sorted_results = sorted(self.test_results, key=lambda x: x[2])
        for ip, domain, delay, status, selected in sorted_results:
            self.result_tree.insert("", "end", values=["□" if not selected else "✓", ip, domain, delay, status])

        if current_selection:
            for item in self.result_tree.get_children():
                values = self.result_tree.item(item, "values")
                if values in current_selection:
                    self.result_tree.selection_add(item)

    def _monitor_test_completion(self):
        if self.executor:
            self.executor.shutdown(wait=True)

        if not self.stop_test:
            self.master.after(
                0, lambda: self.status_label.config(text=f"测速完成，共测试 {self.total_tests} 个IP", bootstyle=SUCCESS)
            )
            self.master.after(0, lambda: self.progress.configure(value=100))
        else:
            self.master.after(
                0,
                lambda: self.status_label.config(
                    text=f"测速已暂停，已测试 {self.completed_tests}/{self.total_tests} 个IP", bootstyle=WARNING
                ),
            )

        self.master.after(0, lambda: self.start_test_btn.config(state=NORMAL))
        self.master.after(0, lambda: self.pause_test_btn.config(state=DISABLED))
        self.master.after(0, lambda: self.resolve_preset_btn.config(state=NORMAL))
        self.master.after(0, lambda: self.refresh_remote_btn.config(state=NORMAL if self.is_github_selected else DISABLED))

    def pause_test(self):
        self.stop_test = True
        self.status_label.config(text="正在停止测速...", bootstyle=WARNING)

    # -------------------------
    # Tree select
    # -------------------------
    def on_tree_click(self, event):
        region = self.result_tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = int(self.result_tree.identify_column(event.x).replace("#", ""))
        if column != 1:
            return

        item = self.result_tree.identify_row(event.y)
        if not item:
            return

        values = self.result_tree.item(item, "values")
        ip, domain = values[1], values[2]

        for i, result in enumerate(self.test_results):
            if result[0] == ip and result[1] == domain:
                new_selected = not result[4]
                self.test_results[i] = (ip, domain, result[2], result[3], new_selected)
                self.result_tree.item(item, values=["✓" if new_selected else "□", ip, domain, result[2], result[3]])
                break

    # -------------------------
    # Hosts file operations
    # -------------------------
    def write_selected_to_hosts(self):
        selected_ips = [(ip, domain) for ip, domain, _, _, selected in self.test_results if selected]
        if not selected_ips:
            messagebox.showinfo("提示", "请先选择要写入的IP地址")
            return

        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            start_idx = content.find(HOSTS_START_MARK)
            end_idx = content.find(HOSTS_END_MARK)

            if start_idx != -1 and end_idx != -1:
                new_content = content[:start_idx] + content[end_idx + len(HOSTS_END_MARK) :]
            else:
                new_content = content

            hosts_entries = [f"{ip} {domain}" for ip, domain in selected_ips]
            tool_content = f"\n{HOSTS_START_MARK}\n" + "\n".join(hosts_entries) + f"\n{HOSTS_END_MARK}\n"

            with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                f.write(new_content.rstrip() + tool_content)

            messagebox.showinfo("成功", f"已成功将 {len(selected_ips)} 条记录写入Hosts文件\n建议刷新DNS使修改生效")
            self.status_label.config(text="Hosts文件已更新", bootstyle=SUCCESS)
        except Exception as e:
            messagebox.showerror("错误", f"写入Hosts文件失败: {e}")
            self.status_label.config(text="写入Hosts失败", bootstyle=DANGER)

    def write_best_ip_to_hosts(self):
        if not self.test_results:
            messagebox.showinfo("提示", "请先进行测速")
            return

        best_ips = {}
        for ip, domain, delay, status, _ in self.test_results:
            if status != "可用":
                continue
            if domain not in best_ips or delay < best_ips[domain][1]:
                best_ips[domain] = (ip, delay)

        if not best_ips:
            messagebox.showinfo("提示", "没有可用的IP地址")
            return

        selected_ips = [(ip, domain) for domain, (ip, _) in best_ips.items()]

        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            start_idx = content.find(HOSTS_START_MARK)
            end_idx = content.find(HOSTS_END_MARK)

            if start_idx != -1 and end_idx != -1:
                new_content = content[:start_idx] + content[end_idx + len(HOSTS_END_MARK) :]
            else:
                new_content = content

            hosts_entries = [f"{ip} {domain}" for ip, domain in selected_ips]
            tool_content = f"\n{HOSTS_START_MARK}\n" + "\n".join(hosts_entries) + f"\n{HOSTS_END_MARK}\n"

            with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                f.write(new_content.rstrip() + tool_content)

            messagebox.showinfo("成功", f"已成功将 {len(selected_ips)} 个最优IP写入Hosts文件\n建议刷新DNS使修改生效")
            self.status_label.config(text="最优IP已写入Hosts", bootstyle=SUCCESS)
        except Exception as e:
            messagebox.showerror("错误", f"写入Hosts文件失败: {e}")
            self.status_label.config(text="写入Hosts失败", bootstyle=DANGER)

    # -------------------------
    # Utilities
    # -------------------------
    def flush_dns(self):
        try:
            self.status_label.config(text="正在刷新DNS缓存...", bootstyle=INFO)
            subprocess.run(
                ["ipconfig", "/flushdns"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            self.status_label.config(text="DNS缓存已刷新", bootstyle=SUCCESS)
            messagebox.showinfo("成功", "DNS缓存已成功刷新")
        except Exception as e:
            messagebox.showerror("错误", f"刷新DNS缓存失败: {e}")
            self.status_label.config(text="刷新DNS失败", bootstyle=DANGER)

    def view_hosts_file(self):
        try:
            subprocess.run(["notepad.exe", HOSTS_PATH])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开Hosts文件: {e}")


# ---------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------
def main():
    """主函数，包含全面的异常处理和调试输出"""
    print("="*50)
    print("程序开始运行...")
    print(f"是否管理员权限: {is_admin()}")
    print(f"当前主题: {APP_THEME}")
    print("="*50)
    
    try:
        print("尝试创建窗口对象...")
        app = ttk.Window(themename=APP_THEME)
        print("窗口对象创建成功")
        
        # 图标（不存在就忽略）
        try:
            app.iconbitmap(resource_path("icon.ico"))
            print("图标设置成功")
        except Exception as e:
            print(f"设置图标失败: {e}")
        
        try:
            print("尝试创建HostsOptimizer实例...")
            HostsOptimizer(app)
            print("HostsOptimizer实例创建成功")
            
            print("进入主循环...")
            app.mainloop()
            print("主循环结束")
        except Exception as e:
            print(f"应用程序运行错误: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("错误", f"应用程序运行错误: {e}")
    except Exception as e:
        print(f"程序初始化失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()