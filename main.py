import os
import re
import json
import sys
import subprocess
import threading
import socket
import requests
import concurrent.futures
from tkinter import ttk, messagebox, simpledialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import ctypes
from datetime import datetime

# 获取程序所在目录
base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# 使用明确的绝对路径记录调试信息，确保日志文件能被找到
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_info.log")
with open(log_path, "w", encoding="utf-8") as f:
    f.write(f"程序启动时间: {datetime.now()}\n")
    f.write(f"base_path: {base_path}\n")
    f.write(f"当前工作目录: {os.getcwd()}\n")
    f.write(f"调试日志路径: {log_path}\n")
    
    # 检查头像文件
    avatar_path = os.path.join(base_path, "头像.jpg")
    f.write(f"头像文件路径: {avatar_path}\n")
    f.write(f"头像文件是否存在: {os.path.exists(avatar_path)}\n")
    
    # 检查PIL库
    try:
        from PIL import Image, ImageTk
        f.write("PIL库导入成功\n")
    except ImportError as e:
        f.write(f"PIL库导入失败: {e}\n")
    
    # 列出base_path目录下的文件
    try:
        files = os.listdir(base_path)
        f.write(f"base_path目录下的文件: {files}\n")
    except Exception as e:
        f.write(f"无法列出base_path目录: {e}\n")


# 检查是否以管理员身份运行
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


# 如果不是管理员，提示并退出
if not is_admin():
    messagebox.showerror("权限不足", "请以管理员身份运行程序，否则无法修改 Hosts 文件！")
    sys.exit(1)

# 全局常量配置
# 1. GitHub域名标记（仅选中此域名时加载指定远程Hosts）
GITHUB_TARGET_DOMAIN = "github.com"
# 2. 指定的远程Hosts文件地址（仅GitHub时使用）
REMOTE_HOSTS_URL = "https://github-hosts.tinsfox.com/hosts"
# 3. Hosts文件路径
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
# 4. 工具专属标记（用于管理工具添加的记录，不再清空全部，仅过滤指定域名）
HOSTS_START_MARK = "# === SmartHostsTool Start ==="
HOSTS_END_MARK = "# === SmartHostsTool End ==="


class HostsOptimizer(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master, padding=10)
        self.master = master
        self.master.title("智能 Hosts 测速工具")
        self.master.geometry("1000x600")
        self.master.resizable(True, True)

        # 设置主题
        self.style = ttk.Style("darkly")

        # 数据存储
        self.remote_hosts_data = []  # 仅GitHub时加载的远程Hosts全部数据
        self.smart_resolved_ips = []  # 智能解析的IP数据（所有域名通用）
        self.custom_presets = []  # 自定义预设网址列表
        self.test_results = []  # 测速结果 (ip, domain, delay, status, selected)
        self.presets_file = os.path.join(base_path, "presets.json")
        # 选中状态标记
        self.current_selected_presets = []  # 存储选中的预设网址
        self.is_github_selected = False  # 是否选中了GitHub域名
        # 测速控制标志
        self.stop_test = False  # 暂停/停止测速标志
        self.executor = None  # 线程池对象

        # 加载预设
        self.load_presets()

        # 创建UI
        self.create_widgets()

        # 初始状态：不自动加载任何数据，等待用户选择预设后触发

    def create_widgets(self):
        # 顶部区域 - 标题和功能按钮
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=X, pady=(0, 10))

        # 标题
        title_label = ttk.Label(top_frame, text="智能 Hosts 测速工具", font= ("微软雅黑", 16, "bold"))
        title_label.pack(side=LEFT, padx=10)

        # 功能按钮
        button_frame = ttk.Frame(top_frame)
        button_frame.pack(side=RIGHT)

        # 关于按钮
        self.about_btn = ttk.Button(
            button_frame, text="关于", command=self.show_about,
            bootstyle=INFO, width=8
        )
        self.about_btn.pack(side=LEFT, padx=5)

        # 刷新远程Hosts按钮（仅GitHub时可用）
        self.refresh_remote_btn = ttk.Button(
            button_frame, text="刷新远程 Hosts", command=self.refresh_remote_hosts,
            bootstyle=SUCCESS, width=15, state=DISABLED  # 初始禁用
        )
        self.refresh_remote_btn.pack(side=LEFT, padx=5)

        self.flush_dns_btn = ttk.Button(
            button_frame, text="刷新 DNS", command=self.flush_dns,
            bootstyle=INFO, width=10
        )
        self.flush_dns_btn.pack(side=LEFT, padx=5)

        # 查看Hosts文件按钮
        self.view_hosts_btn = ttk.Button(
            button_frame, text="查看 Hosts 文件", command=self.view_hosts_file,
            bootstyle=SECONDARY, width=12
        )
        self.view_hosts_btn.pack(side=LEFT, padx=5)

        # 开始测速按钮
        self.start_test_btn = ttk.Button(
            button_frame, text="开始测速", command=self.start_test,
            bootstyle=PRIMARY, width=10, state=DISABLED  # 初始禁用
        )
        self.start_test_btn.pack(side=LEFT, padx=5)

        # 暂停测速按钮
        self.pause_test_btn = ttk.Button(
            button_frame, text="暂停测速", command=self.pause_test,
            bootstyle=WARNING, width=10, state=DISABLED
        )
        self.pause_test_btn.pack(side=LEFT, padx=5)

        # 中间主区域
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=BOTH, expand=True)

        # 左侧标签页
        left_notebook = ttk.Notebook(main_frame, width=350)
        left_notebook.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))

        # 远程Hosts解析结果标签页（仅GitHub时显示）
        self.remote_frame = ttk.Frame(left_notebook)
        left_notebook.add(self.remote_frame, text="远程 Hosts 数据（仅GitHub）")

        # 远程Hosts结果列表
        self.remote_tree = ttk.Treeview(
            self.remote_frame, columns=["ip", "domain"], show="headings", height=15
        )
        self.remote_tree.heading("ip", text="IP 地址")
        self.remote_tree.heading("domain", text="域名")
        self.remote_tree.column("ip", width=120)
        self.remote_tree.column("domain", width=200)
        self.remote_tree.pack(fill=BOTH, expand=True, pady=(0, 10))

        # 自定义预设网址标签页
        self.custom_frame = ttk.Frame(left_notebook)
        left_notebook.add(self.custom_frame, text="自定义预设网址")

        # 自定义预设按钮
        custom_btn_frame = ttk.Frame(self.custom_frame)
        custom_btn_frame.pack(fill=X, pady=(0, 10))

        self.add_preset_btn = ttk.Button(
            custom_btn_frame, text="添加预设", command=self.add_preset,
            bootstyle=SUCCESS
        )
        self.add_preset_btn.pack(side=LEFT, padx=5)

        self.delete_preset_btn = ttk.Button(
            custom_btn_frame, text="删除预设", command=self.delete_preset,
            bootstyle=DANGER
        )
        self.delete_preset_btn.pack(side=LEFT, padx=5)

        # 智能解析预设按钮（触发IP解析）
        self.resolve_preset_btn = ttk.Button(
            custom_btn_frame, text="智能解析IP", command=self.resolve_selected_presets,
            bootstyle=INFO
        )
        self.resolve_preset_btn.pack(side=LEFT, padx=5)

        # 自定义预设列表（支持多选）
        self.preset_tree = ttk.Treeview(
            self.custom_frame, columns=["domain"], show="headings", height=14
        )
        self.preset_tree.heading("domain", text="网址")
        self.preset_tree.column("domain", width=300)
        # 开启多选模式
        self.preset_tree.configure(selectmode="extended")
        self.preset_tree.pack(fill=BOTH, expand=True)

        # 右侧测速结果区域
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True)

        # 测速结果表格（复选框列）
        self.result_tree = ttk.Treeview(
            right_frame, columns=["select", "ip", "domain", "delay", "status"], show="headings"
        )
        self.result_tree.heading("select", text="选择")
        self.result_tree.heading("ip", text="IP 地址")
        self.result_tree.heading("domain", text="域名")
        self.result_tree.heading("delay", text="延迟 (ms)")
        self.result_tree.heading("status", text="状态")
        # 调整列宽
        self.result_tree.column("select", width=60, anchor="center")
        self.result_tree.column("ip", width=120)
        self.result_tree.column("domain", width=200)
        self.result_tree.column("delay", width=80)
        self.result_tree.column("status", width=100)
        self.result_tree.pack(fill=BOTH, expand=True, pady=(0, 10))

        # 绑定复选框点击事件
        self.result_tree.bind("<Button-1>", self.on_tree_click)

        # 按钮区域
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=X, pady=(0, 10))

        self.write_selected_btn = ttk.Button(
            btn_frame, text="写入选中到 Hosts", command=self.write_selected_to_hosts,
            bootstyle=PRIMARY, width=20
        )
        self.write_selected_btn.pack(side=RIGHT, padx=5)

        # 一键写入最优IP按钮
        self.write_best_btn = ttk.Button(
            btn_frame, text="一键写入最优IP", command=self.write_best_ip_to_hosts,
            bootstyle=SUCCESS, width=20
        )
        self.write_best_btn.pack(side=RIGHT, padx=5)

        # 底部进度和状态区域
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=X, pady=(10, 0))

        # 进度条
        self.progress_var = ttk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            bottom_frame, variable=self.progress_var, length=100, mode="determinate"
        )
        self.progress_bar.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        # 状态标签
        self.status_var = ttk.StringVar(value="就绪 - 请选择预设网址并点击智能解析IP")
        self.status_label = ttk.Label(bottom_frame, textvariable=self.status_var)
        self.status_label.pack(side=RIGHT)

        # 初始加载预设列表
        self.update_preset_tree()

        # 绑定事件：预设网址选中/切换事件（核心：更新选中状态）
        self.preset_tree.bind("<<TreeviewSelect>>", self.on_preset_selected)
        self.result_tree.bind("<<TreeviewSelect>>", self.on_result_selected)

    # 复选框点击事件处理
    def on_tree_click(self, event):
        region = self.result_tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.result_tree.identify_column(event.x)
            if col == "#1":  # 点击的是选择列
                item = self.result_tree.identify_row(event.y)
                if item:
                    # 获取当前选中状态
                    current = self.result_tree.item(item, "values")[0]
                    # 切换状态（□/✓）
                    new_state = "✓" if current == "□" else "□"
                    # 更新表格显示
                    values = list(self.result_tree.item(item, "values"))
                    values[0] = new_state
                    self.result_tree.item(item, values=values)
                    # 更新数据中的选中状态
                    for i, res in enumerate(self.test_results):
                        if res[0] == values[1] and res[1] == values[2]:
                            self.test_results[i] = (res[0], res[1], res[2], res[3], new_state == "✓")
                            break

    # 核心事件：预设网址选中/切换事件
    def on_preset_selected(self, event):
        # 1. 获取当前选中的预设网址
        selected_items = self.preset_tree.selection()
        self.current_selected_presets = [self.preset_tree.item(item)["values"][0] for item in selected_items]

        # 2. 判断是否选中了GitHub域名
        self.is_github_selected = GITHUB_TARGET_DOMAIN in self.current_selected_presets

        # 3. 更新按钮状态：仅选中GitHub时启用刷新远程Hosts按钮
        self.refresh_remote_btn.config(state=NORMAL if self.is_github_selected else DISABLED)

        # 4. 状态栏提示
        if not self.current_selected_presets:
            self.status_var.set("就绪 - 请选择预设网址并点击智能解析IP")
            self.start_test_btn.config(state=DISABLED)
        elif self.is_github_selected:
            self.status_var.set(f"已选择：{', '.join(self.current_selected_presets)}（可刷新远程Hosts+智能解析IP）")
        else:
            self.status_var.set(f"已选择：{', '.join(self.current_selected_presets)}（仅智能解析IP）")

    # 加载预设
    def load_presets(self):
        try:
            if os.path.exists(self.presets_file):
                with open(self.presets_file, "r", encoding="utf-8") as f:
                    self.custom_presets = json.load(f)
            # 初始添加GitHub预设（方便用户使用）
            if GITHUB_TARGET_DOMAIN not in self.custom_presets:
                self.custom_presets.append(GITHUB_TARGET_DOMAIN)
                self.save_presets()
        except Exception as e:
            messagebox.showerror("错误", f"加载预设失败: {str(e)}")
            self.custom_presets = [GITHUB_TARGET_DOMAIN]  # 兜底：默认添加GitHub

    # 保存预设
    def save_presets(self):
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(self.custom_presets, f, ensure_ascii=False, indent=2)
            self.update_preset_tree()
        except Exception as e:
            messagebox.showerror("错误", f"保存预设失败: {str(e)}")

    # 更新预设列表
    def update_preset_tree(self):
        # 清空现有项
        for item in self.preset_tree.get_children():
            self.preset_tree.delete(item)
        # 添加所有预设
        for domain in self.custom_presets:
            self.preset_tree.insert("", END, values=[domain])

    # 添加预设
    def add_preset(self):
        domain = simpledialog.askstring("添加预设", "请输入网址 (如 github.com、gitee.com):")
        if domain:
            domain = domain.strip().lower()  # 统一小写，避免重复
            # 简单验证域名格式（包含.且不是纯数字）
            if re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', domain):
                if domain not in self.custom_presets:
                    self.custom_presets.append(domain)
                    self.save_presets()
                    messagebox.showinfo("成功", f"已添加预设: {domain}")
                else:
                    messagebox.showwarning("提示", "该网址已在预设列表中")
            else:
                messagebox.showerror("错误", "请输入有效的域名（如 github.com）")

    # 删除预设
    def delete_preset(self):
        selected_items = self.preset_tree.selection()
        if not selected_items:
            messagebox.showwarning("提示", "请先选择要删除的预设")
            return
        # 禁止删除GitHub预设（兜底）
        selected_domain = self.preset_tree.item(selected_items[0])["values"][0]
        if selected_domain == GITHUB_TARGET_DOMAIN:
            messagebox.showwarning("提示", "禁止删除GitHub预设（示例参考）")
            return
        if messagebox.askyesno("确认", f"确定要删除预设: {selected_domain} 吗?"):
            self.custom_presets.remove(selected_domain)
            self.save_presets()
            messagebox.showinfo("成功", f"已删除预设: {selected_domain}")

    # 智能解析选中的预设网址的IP（所有域名通用）
    def resolve_selected_presets(self):
        if not self.current_selected_presets:
            messagebox.showwarning("提示", "请先选择要解析的预设网址")
            return

        self.status_var.set("正在智能解析预设网址的IP...")
        self.master.update()

        # 清空之前的智能解析结果
        self.smart_resolved_ips = []
        # DNS服务器列表（国内+国外，提升解析成功率）
        dns_servers = ["8.8.8.8", "1.1.1.1", "223.5.5.5", "114.114.114.114"]
        resolved_ips = []

        for domain in self.current_selected_presets:
            ips = set()
            try:
                # 尝试使用dnspython解析（多DNS服务器）
                import dns.resolver
                for server in dns_servers:
                    resolver = dns.resolver.Resolver()
                    resolver.nameservers = [server]
                    resolver.timeout = 5
                    resolver.lifetime = 5
                    answers = resolver.query(domain, 'A')
                    for rdata in answers:
                        ips.add(str(rdata))
            except ImportError:
                # 降级使用socket解析（添加超时）
                try:
                    socket.setdefaulttimeout(5)
                    # 获取所有解析的IP
                    _, _, ip_addrs = socket.gethostbyname_ex(domain)
                    for ip in ip_addrs:
                        ips.add(ip)
                except Exception as e:
                    self.status_var.set(f"解析 {domain} 失败: {str(e)[:20]}")
            except Exception as e:
                self.status_var.set(f"解析 {domain} 失败: {str(e)[:20]}")

            # 将解析的IP添加到列表（格式：(ip, domain)）
            for ip in ips:
                resolved_ips.append((ip, domain))

        # 去重并保存智能解析结果
        self.smart_resolved_ips = list({(ip, domain) for ip, domain in resolved_ips})
        self.status_var.set(f"智能解析完成，获取到 {len(self.smart_resolved_ips)} 个IP")

        # 启用开始测速按钮
        self.start_test_btn.config(state=NORMAL)

        # 如果是GitHub，提示用户可刷新远程Hosts（可选）
        if self.is_github_selected and not self.remote_hosts_data:
            messagebox.showinfo("提示", "已智能解析GitHub的IP，你还可以点击「刷新远程Hosts」获取更多IP")

    # 刷新远程Hosts（仅GitHub时执行，加载指定网址的完整Hosts文件）
    def refresh_remote_hosts(self):
        if not self.is_github_selected:
            messagebox.showwarning("提示", "仅选中GitHub时可刷新远程Hosts")
            return

        self.status_var.set("正在加载远程Hosts文件...")
        self.refresh_remote_btn.config(state=DISABLED)
        self.master.update()

        # 开启新线程执行，避免UI卡顿
        threading.Thread(target=self._fetch_remote_hosts, daemon=True).start()

    # 拉取远程Hosts文件（加载完整内容，不过滤）
    def _fetch_remote_hosts(self):
        try:
            # 重试机制（2次）
            response = None
            for _ in range(2):
                try:
                    response = requests.get(REMOTE_HOSTS_URL, timeout=5)
                    response.encoding = "utf-8"
                    break
                except requests.exceptions.Timeout:
                    continue
            if not response or response.status_code != 200:
                raise Exception(f"拉取失败，状态码: {response.status_code if response else '无响应'}")

            # 解析远程Hosts的完整内容（所有IP+域名）
            self.parse_remote_hosts(response.text)
            self.status_var.set(f"远程Hosts加载成功，包含 {len(self.remote_hosts_data)} 个IP")

            # 更新远程Hosts表格
            self.update_remote_tree()
        except Exception as e:
            self.status_var.set(f"加载远程Hosts失败: {str(e)[:20]}")
        finally:
            self.refresh_remote_btn.config(state=NORMAL)

    # 解析远程Hosts文件（完整解析，不过滤任何内容）
    def parse_remote_hosts(self, content):
        temp_data = []
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith("#"):
                continue
            # 提取IP和域名（格式：ip domain1 domain2...）
            parts = re.split(r'\s+', line)
            if len(parts) >= 2:
                ip = parts[0]
                # 处理一个IP对应多个域名的情况
                for domain in parts[1:]:
                    temp_data.append((ip, domain))
        # 去重并保存远程Hosts数据
        self.remote_hosts_data = list({(ip, domain) for ip, domain in temp_data})

    # 更新远程Hosts列表
    def update_remote_tree(self):
        # 清空现有项
        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)
        # 添加所有远程Hosts数据
        for ip, domain in self.remote_hosts_data:
            self.remote_tree.insert("", END, values=[ip, domain])

    # 开始测速（核心：合并数据或仅用智能解析数据）
    def start_test(self):
        # 准备测速数据
        test_data = []
        if self.is_github_selected:
            # GitHub：合并远程Hosts数据 + 智能解析数据（去重）
            test_data = self.remote_hosts_data + self.smart_resolved_ips
        else:
            # 其他域名：仅用智能解析数据
            test_data = self.smart_resolved_ips

        # 去重处理
        test_data = list({(ip, domain) for ip, domain in test_data})

        if not test_data:
            messagebox.showwarning("提示", "暂无需要测速的IP，请先进行智能解析")
            return

        # 重置控制标志
        self.stop_test = False
        # 禁用/启用按钮
        self.start_test_btn.config(state=DISABLED)
        self.pause_test_btn.config(state=NORMAL)
        self.refresh_remote_btn.config(state=DISABLED)
        self.add_preset_btn.config(state=DISABLED)
        self.delete_preset_btn.config(state=DISABLED)
        self.resolve_preset_btn.config(state=DISABLED)

        self.status_var.set("准备开始测速...")
        self.test_results = []
        self.progress_var.set(0)
        self.master.update()

        total = len(test_data)

        # 使用线程池测速（守护线程，防止卡住）
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        futures = []

        for i, (ip, domain) in enumerate(test_data):
            future = self.executor.submit(self.ping_ip, ip, domain)
            future.add_done_callback(
                lambda f, idx=i, total=total: self.handle_ping_result(f, idx, total)
            )
            futures.append(future)

    # 暂停/停止测速
    def pause_test(self):
        self.stop_test = True
        if self.executor:
            self.executor.shutdown(wait=False)
        self.status_var.set("测速已暂停/停止")
        # 恢复按钮状态
        self.reset_test_buttons()
        self.pause_test_btn.config(state=DISABLED)

    # 重置测速按钮状态
    def reset_test_buttons(self):
        self.start_test_btn.config(state=NORMAL if self.smart_resolved_ips else DISABLED)
        self.refresh_remote_btn.config(state=NORMAL if self.is_github_selected else DISABLED)
        self.add_preset_btn.config(state=NORMAL)
        self.delete_preset_btn.config(state=NORMAL)
        self.resolve_preset_btn.config(state=NORMAL)

    # 处理Ping结果（增强异常处理）
    def handle_ping_result(self, future, index, total):
        if self.stop_test:
            return

        try:
            if future.exception() is not None:
                ip = "未知"
                domain = "未知"
                delay = "超时"
                status = "任务异常"
            else:
                ip, domain, delay, status = future.result()

            self.test_results.append((ip, domain, delay, status, False))
            # 按实际完成数更新进度
            completed = len([r for r in self.test_results if r is not None])
            progress = completed / total * 100
            self.progress_var.set(progress)
            self.status_var.set(f"正在测速: {completed}/{total}")

            # 按延迟从低到高排序
            self.sort_test_results()
            self.update_result_tree()

            if completed == total and not self.stop_test:
                self.status_var.set(f"测速完成，共 {total} 个IP")
                self.reset_test_buttons()
                self.pause_test_btn.config(state=DISABLED)
        except Exception as e:
            if not self.stop_test:
                self.status_var.set(f"测速出错: {str(e)[:20]}")
                self.reset_test_buttons()

    # 排序测试结果（严格按延迟从低到高）
    def sort_test_results(self):
        def sort_key(item):
            ip, domain, delay, status, selected = item
            # 状态权重
            status_weight = {
                "正常": 0,
                "不可达": 1,
                "未知错误": 2,
                "超时": 3,
                "命令超时": 3,
                "任务异常": 4
            }.get(status, 4)
            # 延迟权重
            try:
                delay_weight = int(delay) if delay.isdigit() else float('inf')
            except ValueError:
                delay_weight = float('inf')
            return (status_weight, delay_weight)

        self.test_results.sort(key=sort_key)

    # 更新结果表格
    def update_result_tree(self):
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        for ip, domain, delay, status, selected in self.test_results:
            select_mark = "✓" if selected else "□"
            self.result_tree.insert("", END, values=[select_mark, ip, domain, delay, status])

    # Ping IP地址（解决超时卡住问题）
    def ping_ip(self, ip, domain):
        if self.stop_test:
            return (ip, domain, "超时", "已停止")

        try:
            cmd = ['ping', '-n', '1', '-w', '2000', ip]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # 核心：subprocess超时控制（3秒）
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                startupinfo=startupinfo, encoding='gbk', timeout=3
            )

            output = result.stdout.lower()
            if "超时" in output or "request timed out" in output:
                return (ip, domain, "超时", "超时")
            elif "无法访问目标主机" in output or "destination host unreachable" in output:
                return (ip, domain, "超时", "不可达")
            elif "找不到主机" in output or "could not find host" in output:
                return (ip, domain, "超时", "未知主机")

            # 提取延迟值（兼容中英文）
            delay_match = re.search(r'平均 = (\d+)ms|average = (\d+)ms', output)
            if delay_match:
                delay = delay_match.group(1) or delay_match.group(2)
                delay = "1" if int(delay) < 1 else delay
                return (ip, domain, delay, "正常")
            else:
                return (ip, domain, "超时", "未知错误")
        except subprocess.TimeoutExpired:
            return (ip, domain, "超时", "命令超时")
        except Exception as e:
            return (ip, domain, "超时", f"错误: {str(e)[:20]}")

    # 查看Hosts文件功能
    def view_hosts_file(self):
        try:
            self.status_var.set("正在打开Hosts文件...")
            self.master.update()

            if not os.path.exists(HOSTS_PATH):
                messagebox.showwarning("提示", "Hosts文件不存在，将创建空文件后打开")
                with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                    f.write("# 空的Hosts文件\n")

            # 双方案打开：先系统默认编辑器，超时则用记事本
            subprocess.run(
                ['cmd', '/c', 'start', '', HOSTS_PATH],
                startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW),
                timeout=5
            )
            self.status_var.set("已打开Hosts文件")
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(
                    ['notepad.exe', HOSTS_PATH],
                    startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW),
                    timeout=5
                )
                self.status_var.set("已用记事本打开Hosts文件")
            except Exception as e:
                self.status_var.set(f"打开Hosts文件失败: {str(e)[:20]}")
                messagebox.showerror("错误", f"打开Hosts文件失败: {str(e)}")
        except PermissionError:
            self.status_var.set("打开Hosts文件失败：权限不足")
            messagebox.showerror("错误", "请以管理员身份运行程序！")
        except Exception as e:
            self.status_var.set(f"打开Hosts文件失败: {str(e)[:20]}")
            messagebox.showerror("错误", f"打开Hosts文件失败: {str(e)}")
    
    # 显示关于对话框
    def show_about(self):
        """显示关于界面"""
        try:
            # 直接导入并创建AboutWindow实例
            from about_gui import AboutWindow
            # 创建一个新线程来运行关于窗口，避免阻塞主界面
            about_thread = threading.Thread(target=AboutWindow, daemon=True)
            about_thread.start()
        except Exception as e:
            messagebox.showerror("错误", f"无法打开关于界面: {str(e)}")
            

    # 刷新DNS缓存
    def flush_dns(self):
        try:
            self.status_var.set("正在刷新DNS缓存...")
            self.master.update()
            subprocess.run(
                ['ipconfig', '/flushdns'],
                startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5
            )
            self.status_var.set("DNS缓存刷新成功")
        except Exception as e:
            self.status_var.set(f"刷新DNS失败: {str(e)[:20]}")
            messagebox.showerror("错误", f"刷新DNS缓存失败: {str(e)}")

    # 写入选中项到Hosts
    def write_selected_to_hosts(self):
        selected_entries = [(ip, domain) for ip, domain, _, _, selected in self.test_results if selected]
        if not selected_entries:
            messagebox.showwarning("提示", "请先勾选要写入的IP和域名")
            return
        self._write_hosts(selected_entries)

    # 一键写入最优IP
    def write_best_ip_to_hosts(self):
        normal_ips = [(ip, domain) for ip, domain, _, status, _ in self.test_results if status == "正常"]
        if not normal_ips:
            messagebox.showwarning("提示", "暂无状态正常的IP可写入")
            return
        best_entry = [normal_ips[0]]
        self._write_hosts(best_entry)
        messagebox.showinfo("成功", f"已写入最优IP: {best_entry[0][0]} {best_entry[0][1]}")

    # 核心优化：Hosts写入逻辑（仅覆盖当前域名的旧记录，保留其他域名）
    def _write_hosts(self, new_entries):
        try:
            # 1. 获取当前要写入的所有域名和IP映射（去重，相同域名保留最后一个）
            domain_ip_map = {}
            for ip, domain in new_entries:
                domain_ip_map[domain] = ip  # 相同域名后面的会覆盖前面的
            
            target_domains = set(domain_ip_map.keys())
            self.status_var.set(f"正在处理Hosts文件，涉及域名: {', '.join(target_domains)}")
            self.master.update()

            # 2. 读取现有Hosts文件内容
            if not os.path.exists(HOSTS_PATH):
                # 文件不存在则创建
                with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                    f.write("")
                existing_lines = []
            else:
                with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()

            # 3. 解析Hosts文件，分离出工具标记块内外的内容
            outside_lines = []  # 工具标记块外的内容
            inside_lines = []  # 工具标记块内的内容（包括注释）
            in_tool_block = False

            for line in existing_lines:
                stripped_line = line.strip()
                if stripped_line == HOSTS_START_MARK:
                    in_tool_block = True
                    inside_lines.append(line)  # 保留开始标记
                elif stripped_line == HOSTS_END_MARK:
                    in_tool_block = False
                    inside_lines.append(line)  # 保留结束标记
                elif in_tool_block:
                    inside_lines.append(line)
                else:
                    outside_lines.append(line)

            # 4. 处理工具标记块内的内容，保留非目标域名的记录
            processed_inside_lines = []
            if inside_lines:
                # 保留开始标记
                processed_inside_lines.append(inside_lines[0])
                
                # 遍历标记块内的内容（不包括开始和结束标记）
                for line in inside_lines[1:-1] if len(inside_lines) > 2 else []:
                    stripped_line = line.strip()
                    if stripped_line.startswith("#"):
                        # 跳过注释行，这些将被新的注释替换
                        continue
                    elif stripped_line:
                        # 提取域名
                        parts = re.split(r'\s+', stripped_line)
                        if len(parts) >= 2:
                            line_domain = parts[1]
                            if line_domain not in target_domains:
                                # 非目标域名，保留
                                processed_inside_lines.append(line)
                
                # 保留结束标记
                if len(inside_lines) > 1:
                    processed_inside_lines.append(inside_lines[-1])

            # 5. 准备新的工具标记块内容
            if processed_inside_lines:
                # 有现有的标记块，在开始和结束标记之间插入新记录
                new_tool_block = processed_inside_lines[:1]  # 开始标记
                
                # 添加新记录（带时间戳注释）
                new_tool_block.append(f"\n# 智能Hosts测速工具添加 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                for domain, ip in domain_ip_map.items():
                    new_tool_block.append(f"{ip}    {domain}\n")
                
                # 添加剩余的非目标记录和结束标记
                new_tool_block.extend(processed_inside_lines[1:])
            else:
                # 没有现有的标记块，创建新的
                new_tool_block = [
                    f"\n{HOSTS_START_MARK}\n",
                    f"# 智能Hosts测速工具添加 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                ]
                for domain, ip in domain_ip_map.items():
                    new_tool_block.append(f"{ip}    {domain}\n")
                new_tool_block.append(f"{HOSTS_END_MARK}\n")

            # 6. 重新组合文件内容
            new_lines = []
            
            # 添加标记块外的内容
            new_lines.extend(outside_lines)
            
            # 添加处理后的标记块内容
            new_lines.extend(new_tool_block)

            # 7. 写入文件（覆盖原文件）
            with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # 8. 刷新DNS
            self.flush_dns()

            self.status_var.set(f"成功写入 {len(domain_ip_map)} 条记录到Hosts，保留了其他域名的记录")
            messagebox.showinfo("成功",
                                f"已成功写入 {len(domain_ip_map)} 条记录到Hosts文件\n保留了其他域名的现有记录\n并刷新了DNS缓存")
        except PermissionError:
            self.status_var.set("写入Hosts失败：权限不足")
            messagebox.showerror("错误", "请以管理员身份运行程序！")
        except Exception as e:
            self.status_var.set(f"写入Hosts失败: {str(e)[:20]}")
            messagebox.showerror("错误", f"写入Hosts文件失败: {str(e)}")

    # 结果选中事件
    def on_result_selected(self, event):
        pass


if __name__ == "__main__":
    app = ttk.Window()
    app.style.theme_use("darkly")
    host_optimizer = HostsOptimizer(app)
    host_optimizer.pack(fill=BOTH, expand=True)
    app.mainloop()