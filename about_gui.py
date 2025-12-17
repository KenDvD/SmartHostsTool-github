# -*- coding: utf-8 -*-
"""
关于窗口（ttkbootstrap）

改进点：
1) 使用 ttkbootstrap.Toplevel 而不是创建第二个 Tk/Window + mainloop（避免多窗口/多 mainloop 引发的显示/样式问题）。
2) 头像加载使用统一的 resource_path，兼容源码运行 & PyInstaller（--onefile/--onedir）。
3) 头像 PhotoImage 引用保存在窗口对象上，避免被 GC 回收导致“不显示/消失”。
4) 重新排版：信息区分组、加入分隔线/提示卡片、按钮区更清晰，整体更美观。
"""

from __future__ import annotations

import os
import sys
import webbrowser
from typing import Optional, Sequence

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText

# Pillow 用于加载/缩放 jpg；没有 Pillow 时会自动降级为占位符
try:
    from PIL import Image, ImageTk, ImageOps, ImageDraw
except Exception:  # pragma: no cover
    Image = None
    ImageTk = None
    ImageOps = None
    ImageDraw = None


def resource_path(*parts: str) -> str:
    """
    返回资源的绝对路径，兼容 PyInstaller 打包与源码运行。
    - PyInstaller 运行时，资源在 sys._MEIPASS（临时解包目录）里。
    - 源码运行时，资源相对当前文件所在目录。
    """
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


def find_first_existing(paths: Sequence[str]) -> Optional[str]:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


class AboutWindow:
    """
    关于窗口：作为 Toplevel 弹窗显示（不会再启动第二个 mainloop）

    用法：
        AboutWindow(master)  # master 为主窗口 Window/Tk
    """

    def __init__(
        self,
        master,
        *,
        app_name: str = "智能Hosts测速工具",
        version: str = "V1.0",
        author: str = "毕加索自画像",
        github_profile_url: str = "https://github.com/KenDvD",
        github_repo_url: str = "https://github.com/KenDvD/SmartHostsTool-github",
    ) -> None:
        self.master = master
        self.app_name = app_name
        self.version = version
        self.author = author
        self.github_profile_url = github_profile_url
        self.github_repo_url = github_repo_url

        # 窗口尺寸（折叠/展开）
        self.window_width = 780
        self.window_height = 470
        self.expanded_height = 730

        self.usage_expanded = False
        self.usage_frame = None

        # 创建窗口：用 Toplevel（避免创建第二个 Tk/Window）
        self.window = ttk.Toplevel(master=master, title=f"关于 {app_name}")
        self.window.resizable(False, False)

        # 居中显示
        try:
            self.window.geometry(f"{self.window_width}x{self.window_height}")
            self.window.place_window_center()
        except Exception:
            # 兼容老版本：手动居中
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = int(sw / 2 - self.window_width / 2)
            y = int(sh / 2 - self.window_height / 2)
            self.window.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

        # 作为模态窗口：阻止用户点到主窗口（可按需去掉）
        try:
            self.window.transient(master)
            self.window.grab_set()
            self.window.focus_set()
        except Exception:
            pass

        # 设置图标（如果存在）
        self._set_icon()

        # 构建 UI
        self._build_ui()

    # -------------------------
    # UI
    # -------------------------
    def _set_icon(self) -> None:
        ico = find_first_existing(
            [
                resource_path("icon.ico"),
                resource_path("icon.png"),
            ]
        )
        if not ico:
            return
        try:
            # Windows 下 iconbitmap 最稳定
            if ico.lower().endswith(".ico"):
                self.window.iconbitmap(ico)
            else:
                # png 作为 iconphoto
                if ImageTk and Image:
                    img = Image.open(ico)
                    photo = ImageTk.PhotoImage(img)
                    self.window.iconphoto(False, photo)
                    # 保存引用，避免被 GC
                    self.window._icon_photo = photo  # type: ignore[attr-defined]
        except Exception:
            pass

    def _build_ui(self) -> None:
        root = self.window
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        container = ttk.Frame(root, padding=20)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=0)
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(2, weight=1)

        # 顶部标题（横跨两列）
        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        title = ttk.Label(
            header,
            text=self.app_name,
            font=("微软雅黑", 18, "bold"),
            bootstyle="inverse-primary",
            padding=(12, 10),
            anchor=W,
        )
        title.grid(row=0, column=0, sticky="ew")

        # 内容区域：左头像 / 右信息
        left = ttk.Frame(container)
        left.grid(row=1, column=0, sticky="n", padx=(0, 18))

        right = ttk.Frame(container)
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        # 头像卡片
        avatar_card = ttk.Labelframe(left, text="头像", padding=(12, 10))
        avatar_card.grid(row=0, column=0, sticky="n")
        self._render_avatar(avatar_card)

        # 右侧信息（分组卡片）
        info_card = ttk.Labelframe(right, text="项目信息", padding=(14, 12))
        info_card.grid(row=0, column=0, sticky="ew")
        info_card.grid_columnconfigure(0, weight=1)

        ttk.Label(
            info_card,
            text=f"版本：{self.version}",
            font=("微软雅黑", 11),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        ttk.Label(
            info_card,
            text="简介：一个智能获取域名 IP 进行测试并写入 hosts 的工具",
            font=("微软雅黑", 10),
            wraplength=520,
            justify=LEFT,
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        ttk.Separator(info_card).grid(row=2, column=0, sticky="ew", pady=(4, 10))

        ttk.Label(
            info_card,
            text=f"作者：{self.author}",
            font=("微软雅黑", 10),
        ).grid(row=3, column=0, sticky="w", pady=(0, 6))

        # GitHub 链接（用 Label 做超链接效果）
        link_line = ttk.Frame(info_card)
        link_line.grid(row=4, column=0, sticky="ew")
        link_line.grid_columnconfigure(1, weight=1)

        ttk.Label(link_line, text="GitHub：", font=("微软雅黑", 10)).grid(
            row=0, column=0, sticky="w"
        )
        link = ttk.Label(
            link_line,
            text="KenDvD / SmartHostsTool-github",
            font=("微软雅黑", 10, "underline"),
            cursor="hand2",
            bootstyle="info",
        )
        link.grid(row=0, column=1, sticky="w")
        link.bind("<Button-1>", lambda _e: self.open_repo())

        # 开源提示卡片
        warn = ttk.Label(
            right,
            text="该工具完全开源免费！如果你买到此软件那么你被坑了",
            font=("微软雅黑", 10, "bold"),
            wraplength=520,
            justify=LEFT,
            bootstyle="inverse-danger",
            padding=(12, 10),
        )
        warn.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        # 使用说明（可展开）
        self.usage_container = ttk.Frame(container)
        self.usage_container.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0))
        self.usage_container.grid_columnconfigure(0, weight=1)
        self.usage_container.grid_rowconfigure(0, weight=1)

        # 底部按钮栏
        btnbar = ttk.Frame(container)
        btnbar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        btnbar.grid_columnconfigure(0, weight=1)

        left_btns = ttk.Frame(btnbar)
        left_btns.grid(row=0, column=0, sticky="w")

        right_btns = ttk.Frame(btnbar)
        right_btns.grid(row=0, column=1, sticky="e")

        self.usage_btn = ttk.Button(
            left_btns,
            text="展开使用说明",
            command=self.toggle_usage,
            bootstyle="success",
            width=14,
        )
        self.usage_btn.pack(side=LEFT)

        ttk.Button(
            left_btns,
            text="打开 GitHub",
            command=self.open_repo,
            bootstyle="info-outline",
            width=12,
        ).pack(side=LEFT, padx=(10, 0))

        ttk.Button(
            right_btns,
            text="确定",
            command=self.close,
            bootstyle="primary",
            width=10,
        ).pack(side=RIGHT)

        # ESC 关闭
        root.bind("<Escape>", lambda _e: self.close())

    # -------------------------
    # Avatar
    # -------------------------
    def _render_avatar(self, parent) -> None:
        """
        渲染头像。优先加载项目目录里的头像文件；失败则显示占位符。
        """
        # 尽量兼容你仓库里的资源命名（头像.jpg / 头线.jpg / avatar.png 等）
        candidate_names = [
            "头像.jpg",
            "头像.jpeg",
            "头像.png",
            "头线.jpg",
            "头线.png",
            "avatar.jpg",
            "avatar.png",
        ]
        candidate_paths = []

        # 1) 根目录
        for name in candidate_names:
            candidate_paths.append(resource_path(name))

        # 2) 常见资源目录
        for folder in ("assets", "res", "resources", "img", "images"):
            for name in candidate_names:
                candidate_paths.append(resource_path(folder, name))

        avatar_path = find_first_existing(candidate_paths)

        # 没有 Pillow / 没找到头像文件：占位符
        if not (avatar_path and Image and ImageTk and ImageOps and ImageDraw):
            ttk.Label(parent, text="🤖", font=("微软雅黑", 80), padding=(10, 6)).pack()
            ttk.Label(parent, text="(未找到头像资源)", font=("微软雅黑", 9)).pack(pady=(6, 0))
            return

        try:
            # 读取并裁剪成圆形头像（更好看）
            size = 160
            img = Image.open(avatar_path).convert("RGBA")
            img = ImageOps.fit(img, (size, size), method=Image.LANCZOS)

            # 圆形蒙版
            mask = Image.new("L", (size, size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size, size), fill=255)

            out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            out.paste(img, (0, 0), mask=mask)

            photo = ImageTk.PhotoImage(out)

            lbl = ttk.Label(parent, image=photo)
            lbl.pack()

            # 关键：保存引用，避免 PhotoImage 被 GC 回收导致“头像不显示”
            self.window._avatar_photo = photo  # type: ignore[attr-defined]
            self.window._avatar_label = lbl  # type: ignore[attr-defined]
        except Exception:
            ttk.Label(parent, text="🤖", font=("微软雅黑", 80), padding=(10, 6)).pack()
            ttk.Label(parent, text="(头像加载失败)", font=("微软雅黑", 9)).pack(pady=(6, 0))

    # -------------------------
    # Actions
    # -------------------------
    def open_repo(self) -> None:
        webbrowser.open(self.github_repo_url)

    def open_profile(self) -> None:
        webbrowser.open(self.github_profile_url)

    def close(self) -> None:
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    def toggle_usage(self) -> None:
        if not self.usage_expanded:
            if self.usage_frame is None:
                self.usage_frame = ttk.Labelframe(
                    self.usage_container, text="软件详细使用说明", padding=12
                )
                self.usage_frame.grid(row=0, column=0, sticky="nsew")
                self.usage_container.grid_rowconfigure(0, weight=1)

                usage_content = """
软件详细使用说明：

1. 首先以管理员身份打开软件，点击「自定义网站预设」选择你需要测速的域名（可以自己添加想要的域名）

2. 例如 github.com：选择后点击「智能解析IP」，也可以再点击「刷新远程 Hosts」获取更多 IP
   （刷新远程 Hosts 仅 GitHub 专属，其他域名均为智能解析后测速。）

3. 点击「开始测速」——选择延迟低的 IP 写入 hosts；也可以点「一键写入最优IP」

--- 其他功能 ---

1. 刷新 DNS：清除 DNS 缓存，使 hosts 修改立即生效
2. 查看 hosts 文件：用系统默认编辑器打开系统 hosts 文件
3. 添加/删除预设：管理自定义域名列表，方便下次使用
4. 手动选择IP：按实际需求选择特定 IP 写入 hosts
5. 自动排序：测速完成后结果按延迟自动排序，方便选择最优 IP
                """.strip()

                text = ScrolledText(
                    self.usage_frame, wrap=WORD, font=("微软雅黑", 10), height=12
                )
                text.insert("1.0", usage_content)
                text.configure(state="disabled")
                text.pack(fill=BOTH, expand=True)

            else:
                self.usage_frame.grid(row=0, column=0, sticky="nsew")

            self.usage_expanded = True
            self.usage_btn.configure(text="收起使用说明")
            self.window.geometry(f"{self.window_width}x{self.expanded_height}")
            try:
                self.window.place_window_center()
            except Exception:
                pass
        else:
            if self.usage_frame:
                self.usage_frame.grid_remove()

            self.usage_expanded = False
            self.usage_btn.configure(text="展开使用说明")
            self.window.geometry(f"{self.window_width}x{self.window_height}")
            try:
                self.window.place_window_center()
            except Exception:
                pass


if __name__ == "__main__":
    # 允许单独运行预览（不会影响主程序）
    app = ttk.Window(themename="darkly")
    app.withdraw()
    AboutWindow(app)
    app.mainloop()
