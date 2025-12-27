# -*- coding: utf-8 -*-
"""
ui_visuals.py

玻璃拟态背景（渐变 + 光晕 + 噪点）
- Pillow 可用时生成背景图
- Pillow 不可用时退化为纯色背景
- 对 <Configure> 做节流，避免窗口缩放时频繁重绘导致卡顿
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, Optional

import ttkbootstrap as ttk

# Pillow 可选
Image = None
ImageTk = None
ImageDraw = None
ImageFilter = None

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter  # type: ignore
except Exception:  # pragma: no cover
    pass


COLORS = {
    "bg_dark": "#0b1020",
    "bg_top": (16, 24, 40),      # #101828
    "bg_mid": (17, 22, 54),      # #111636
    "bg_bot": (10, 14, 28),      # #0a0e1c
    "glow_1": (56, 189, 248, 45),
    "glow_2": (167, 139, 250, 30),
    "noise_level": 20,
    "noise_opacity": 15,
}


class GlassBackground:
    """
    为窗口提供"玻璃质感"背景（拟态实现）：
    - 生成渐变背景图铺在 Canvas 上
    - 使用柔和光晕与轻噪点增加质感
    """

    def __init__(self, master: tk.Widget, **kwargs: Any) -> None:
        self.master = master
        self.canvas = ttk.Canvas(master, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self.min_width = int(kwargs.get("min_width", 420))
        self.min_height = int(kwargs.get("min_height", 260))
        self.redraw_delay = int(kwargs.get("redraw_delay", 40))

        self.bg_colors: Dict[str, Any] = {
            "top": kwargs.get("bg_top", COLORS["bg_top"]),
            "mid": kwargs.get("bg_mid", COLORS["bg_mid"]),
            "bot": kwargs.get("bg_bot", COLORS["bg_bot"]),
        }
        self.glow_colors: Dict[str, Any] = {
            "glow_1": kwargs.get("glow_1", COLORS["glow_1"]),
            "glow_2": kwargs.get("glow_2", COLORS["glow_2"]),
        }

        self.noise_level = int(kwargs.get("noise_level", COLORS["noise_level"]))
        self.noise_opacity = int(kwargs.get("noise_opacity", COLORS["noise_opacity"]))

        self._img = None
        self._img_id = None
        self._after_id = None

        # add="+" 避免覆盖别的 <Configure> 绑定
        try:
            master.bind("<Configure>", self._schedule_redraw, add="+")
        except Exception:
            master.bind("<Configure>", self._schedule_redraw)

    def lower(self) -> None:
        """将背景 Canvas 置于最低层。"""
        try:
            self.canvas.lower()
        except Exception:
            pass

    def _schedule_redraw(self, _evt=None) -> None:
        """节流重绘：窗口尺寸变化频繁时避免过度重绘。"""
        if self._after_id:
            try:
                self.master.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.master.after(self.redraw_delay, self._redraw)

    def _redraw(self) -> None:
        self._after_id = None
        w = max(self.min_width, int(self.master.winfo_width()))
        h = max(self.min_height, int(self.master.winfo_height()))

        # Pillow 不可用：退化为纯色
        if not (Image and ImageTk):
            self.canvas.configure(background=COLORS["bg_dark"])
            self.lower()
            return

        # 生成 1×H 的渐变条，然后 resize 到目标尺寸（更省）
        grad = Image.new("RGB", (1, h), COLORS["bg_dark"])
        gpx = grad.load()
        top, mid, bot = self.bg_colors["top"], self.bg_colors["mid"], self.bg_colors["bot"]

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
            gpx[0, y] = (r, g, b)

        img = grad.resize((w, h), resample=Image.BILINEAR)

        # 光晕
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse((-w * 0.3, -h * 0.4, w * 0.8, h * 0.7), fill=self.glow_colors["glow_1"])
        draw.ellipse((w * 0.2, h * 0.1, w * 1.2, h * 1.1), fill=self.glow_colors["glow_2"])
        glow = glow.filter(ImageFilter.GaussianBlur(radius=50))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

        # 噪点
        noise = Image.effect_noise((w, h), self.noise_level).convert("L")
        noise = noise.point(lambda v: self.noise_opacity if v > 120 else 0)
        noise_rgba = Image.merge("RGBA", (noise, noise, noise, noise))
        img = Image.alpha_composite(img.convert("RGBA"), noise_rgba).convert("RGB")

        self._img = ImageTk.PhotoImage(img)
        if self._img_id is None:
            self._img_id = self.canvas.create_image(0, 0, anchor="nw", image=self._img)
        else:
            self.canvas.itemconfig(self._img_id, image=self._img)

        # 绘制完成后确保在最底层
        self.lower()
