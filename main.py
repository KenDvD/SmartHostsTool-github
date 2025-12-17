# -*- coding: utf-8 -*-
"""
SmartHostsTool - 主程序

本次优化重点：
1) 清理 main.py 中与业务无关/多余的调试与日志相关代码（例如：无用的 PIL 检测、重复的 ttk 导入等）。
2) 修复一个隐藏 bug：load_presets() 在 UI 创建前调用，会导致预设列表无法正确加载。
3) AboutWindow 改为 Toplevel 弹窗后，show_about() 逻辑同步调整（不再创建第二个 mainloop）。
"""

from __future__ import annotations

import concurrent.futures
import ctypes
import json
import os
import re
import socket
import subprocess
import sys
import threading
from datetime import datetime
from typing import List, Tuple, Optional

import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, simpledialog

from about_gui import AboutWindow

# ---------------------------------------------------------------------
# 资源路径（兼容 PyInstaller）
# ---------------------------------------------------------------------
BASE_PATH = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    return os.path.join(BASE_PATH, *parts)


# ---------------------------------------------------------------------
# 常量配置
# ---------------------------------------------------------------------
GITHUB_TARGET_DOMAIN = "github.com"
REMOTE_HOSTS_URL = "https://github-hosts.tinsfox.com/hosts"
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
    """
    没有管理员权限时提示并退出。
    使用 Windows 原生 MessageBox，避免在未创建主窗口前弹 Tk 的 messagebox 导致样式/根窗口问题。
    """
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
# 主界面
# ---------------------------------------------------------------------
class HostsOptimizer(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master, padding=10)
        self.master = master

        self.master.title("智能 Hosts 测速工具")
        self.master.geometry("1000x600")
        self.master.resizable(True, True)

        # 数据存储
        self.remote_hosts_data: List[Tuple[str, str]] = []  # 仅 GitHub 时加载的远程 Hosts
        self.smart_resolved_ips: List[Tuple[str, str]] = []  # 智能解析的 IP（所有域名通用）
        self.custom_presets: List[str] = []  # 自定义预设网址列表
        self.test_results: List[Tuple[str, str, int, str, bool]] = []  # (ip, domain, delay, status, selected)

        self.presets_file = resource_path("presets.json")

        # 选中状态标记
        self.current_selected_presets: List[str] = []
        self.is_github_selected = False

        # 测速控制
        self.stop_test = False
        self.executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

        # About 窗口引用（防止重复打开）
        self._about: Optional[AboutWindow] = None

        # 先创建 UI，再加载预设（修复预设列表加载时机问题）
        self.create_widgets()
        self.load_presets()

    # -------------------------
    # UI
    # -------------------------
    def create_widgets(self):
        # 顶部区域 - 标题和功能按钮
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=X, pady=(0, 10))

        title_label = ttk.Label(top_frame, text="智能 Hosts 测速工具", font=("微软雅黑", 16, "bold"))
        title_label.pack(side=LEFT, padx=10)

        button_frame = ttk.Frame(top_frame)
        button_frame.pack(side=RIGHT)

        self.about_btn = ttk.Button(button_frame, text="关于", command=self.show_about, bootstyle=INFO, width=8)
        self.about_btn.pack(side=LEFT, padx=5)

        self.refresh_remote_btn = ttk.Button(
            button_frame,
            text="刷新远程 Hosts",
            command=self.refresh_remote_hosts,
            bootstyle=SUCCESS,
            width=15,
            state=DISABLED,
        )
        self.refresh_remote_btn.pack(side=LEFT, padx=5)

        self.flush_dns_btn = ttk.Button(button_frame, text="刷新 DNS", command=self.flush_dns, bootstyle=INFO, width=10)
        self.flush_dns_btn.pack(side=LEFT, padx=5)

        self.view_hosts_btn = ttk.Button(
            button_frame, text="查看 Hosts 文件", command=self.view_hosts_file, bootstyle=SECONDARY, width=12
        )
        self.view_hosts_btn.pack(side=LEFT, padx=5)

        self.start_test_btn = ttk.Button(
            button_frame, text="开始测速", command=self.start_test, bootstyle=PRIMARY, width=10, state=DISABLED
        )
        self.start_test_btn.pack(side=LEFT, padx=5)

        self.pause_test_btn = ttk.Button(
            button_frame, text="暂停测速", command=self.pause_test, bootstyle=WARNING, width=10, state=DISABLED
        )
        self.pause_test_btn.pack(side=LEFT, padx=5)

        # 中间主区域
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=BOTH, expand=True)

        # 左侧标签页
        left_notebook = ttk.Notebook(main_frame, width=350)
        left_notebook.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))

        # 远程 Hosts 标签页（仅 GitHub）
        self.remote_frame = ttk.Frame(left_notebook)
        left_notebook.add(self.remote_frame, text="远程 Hosts 数据（仅GitHub）")

        self.remote_tree = ttk.Treeview(self.remote_frame, columns=["ip", "domain"], show="headings", height=15)
        self.remote_tree.heading("ip", text="IP 地址")
        self.remote_tree.heading("domain", text="域名")
        self.remote_tree.column("ip", width=120)
        self.remote_tree.column("domain", width=200)
        self.remote_tree.pack(fill=BOTH, expand=True, pady=(0, 10))

        # 自定义预设标签页
        self.custom_frame = ttk.Frame(left_notebook)
        left_notebook.add(self.custom_frame, text="自定义预设网址")

        custom_btn_frame = ttk.Frame(self.custom_frame)
        custom_btn_frame.pack(fill=X, pady=(0, 10))

        self.add_preset_btn = ttk.Button(custom_btn_frame, text="添加预设", command=self.add_preset, bootstyle=SUCCESS)
        self.add_preset_btn.pack(side=LEFT, padx=5)

        self.delete_preset_btn = ttk.Button(custom_btn_frame, text="删除预设", command=self.delete_preset, bootstyle=DANGER)
        self.delete_preset_btn.pack(side=LEFT, padx=5)

        self.resolve_preset_btn = ttk.Button(custom_btn_frame, text="智能解析IP", command=self.resolve_selected_presets, bootstyle=INFO)
        self.resolve_preset_btn.pack(side=LEFT, padx=5)

        self.preset_tree = ttk.Treeview(self.custom_frame, columns=["domain"], show="headings", height=14)
        self.preset_tree.heading("domain", text="网址")
        self.preset_tree.column("domain", width=300)
        self.preset_tree.configure(selectmode="extended")
        self.preset_tree.pack(fill=BOTH, expand=True)

        # 右侧测速结果区域
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True)

        self.result_tree = ttk.Treeview(
            right_frame, columns=["select", "ip", "domain", "delay", "status"], show="headings"
        )
        self.result_tree.heading("select", text="选择")
        self.result_tree.heading("ip", text="IP 地址")
        self.result_tree.heading("domain", text="域名")
        self.result_tree.heading("delay", text="延迟 (ms)")
        self.result_tree.heading("status", text="状态")
        self.result_tree.column("select", width=60, anchor="center")
        self.result_tree.column("ip", width=120)
        self.result_tree.column("domain", width=200)
        self.result_tree.column("delay", width=80)
        self.result_tree.column("status", width=100)
        self.result_tree.pack(fill=BOTH, expand=True, pady=(0, 10))

        self.result_tree.bind("<Button-1>", self.on_tree_click)

        # 按钮区域
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=X, pady=(0, 10))

        self.write_selected_btn = ttk.Button(
            btn_frame, text="写入选中到 Hosts", command=self.write_selected_to_hosts, bootstyle=PRIMARY, width=20
        )
        self.write_selected_btn.pack(side=RIGHT, padx=5)

        self.write_best_btn = ttk.Button(
            btn_frame, text="一键写入最优IP", command=self.write_best_ip_to_hosts, bootstyle=SUCCESS, width=20
        )
        self.write_best_btn.pack(side=RIGHT, padx=5)

        # 底部
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=X, pady=(10, 0))

        self.progress = ttk.Progressbar(bottom_frame, orient=HORIZONTAL, length=100, mode="determinate")
        self.progress.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        self.status_label = ttk.Label(bottom_frame, text="就绪", bootstyle=INFO)
        self.status_label.pack(side=RIGHT)

        self.preset_tree.bind("<<TreeviewSelect>>", self.on_preset_select)

        # 显示界面
        self.pack(fill=BOTH, expand=True)

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
            # 不生成额外日志文件，直接提示
            messagebox.showerror("错误", f"加载预设失败: {e}")
            self.custom_presets = default_presets

        # 刷新 TreeView
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

        # 简单验证域名格式
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
        """处理预设选择事件"""
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
        """解析选中的预设网址的 IP"""
        if not self.current_selected_presets:
            return

        self.status_label.config(text="正在解析IP地址...", bootstyle=INFO)
        self.resolve_preset_btn.config(state=DISABLED)

        self.smart_resolved_ips = []
        threading.Thread(target=self._resolve_ips_thread, daemon=True).start()

    def _resolve_ips_thread(self):
        try:
            for domain in self.current_selected_presets:
                try:
                    ip_addresses = socket.gethostbyname_ex(domain)[2]
                    for ip in ip_addresses:
                        self.smart_resolved_ips.append((ip, domain))
                except Exception as e:
                    self.master.after(0, lambda d=domain, err=e: messagebox.showerror("解析错误", f"解析 {d} 失败: {err}"))

            self.master.after(0, self._update_resolve_ui)
        except Exception as e:
            self.master.after(0, lambda err=e: messagebox.showerror("错误", f"解析过程出错: {err}"))
            self.master.after(0, lambda: self.status_label.config(text="解析失败", bootstyle=DANGER))
            self.master.after(0, lambda: self.resolve_preset_btn.config(state=NORMAL))

    def _update_resolve_ui(self):
        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)

        if self.is_github_selected:
            github_ips = [(ip, domain) for ip, domain in self.smart_resolved_ips if domain == GITHUB_TARGET_DOMAIN]
            for ip, domain in github_ips:
                self.remote_tree.insert("", "end", values=[ip, domain])

        self.status_label.config(text=f"解析完成，共找到 {len(self.smart_resolved_ips)} 个IP", bootstyle=SUCCESS)
        self.resolve_preset_btn.config(state=NORMAL)
        self.start_test_btn.config(state=NORMAL)

    # -------------------------
    # Remote hosts (GitHub only)
    # -------------------------
    def refresh_remote_hosts(self):
        if not self.is_github_selected:
            return

        self.status_label.config(text="正在刷新远程Hosts...", bootstyle=INFO)
        self.refresh_remote_btn.config(state=DISABLED)
        threading.Thread(target=self._fetch_remote_hosts, daemon=True).start()

    def _fetch_remote_hosts(self):
        try:
            resp = requests.get(REMOTE_HOSTS_URL, timeout=10)
            resp.raise_for_status()

            hosts_content = resp.text
            lines = hosts_content.splitlines()

            self.remote_hosts_data = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = re.split(r"\s+", line)
                if len(parts) >= 2:
                    ip, domain = parts[0], parts[1]
                    # 匹配所有GitHub相关域名
                    if "github" in domain:
                        self.remote_hosts_data.append((ip, domain))

            self.master.after(0, self._update_remote_hosts_ui)
        except Exception as e:
            self.master.after(0, lambda err=e: messagebox.showerror("获取失败", f"无法获取远程Hosts: {err}"))
            self.master.after(0, lambda: self.status_label.config(text="远程Hosts获取失败", bootstyle=DANGER))
            self.master.after(0, lambda: self.refresh_remote_btn.config(state=NORMAL))

    def _update_remote_hosts_ui(self):
        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)

        for ip, domain in self.remote_hosts_data:
            self.remote_tree.insert("", "end", values=[ip, domain])

        self.status_label.config(text=f"远程Hosts刷新完成，共找到 {len(self.remote_hosts_data)} 条记录", bootstyle=SUCCESS)
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

        self.progress["value"] = 0
        self.total_tests = len(test_data)
        self.completed_tests = 0

        self.status_label.config(text="正在测速，请稍候...", bootstyle=INFO)
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
        self.progress.configure(value=progress)

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
if __name__ == "__main__":
    if not is_admin():
        show_admin_required_and_exit()

    app = ttk.Window(themename="darkly")
    # 图标（不存在就忽略）
    try:
        app.iconbitmap(resource_path("icon.ico"))
    except Exception:
        pass

    HostsOptimizer(app)
    app.mainloop()
