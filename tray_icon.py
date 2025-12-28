# -*- coding: utf-8 -*-
"""
tray_icon.py

系统托盘图标模块：
- 支持最小化到托盘
- 托盘菜单快捷操作
- 托盘通知
- 低资源占用设计

依赖：
- pystray（可选，无则降级为无托盘模式）
- Pillow（用于图标处理）
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Callable, Optional, Any

from utils import get_logger, resource_path

# 尝试导入 pystray
pystray = None
PystrayIcon = None
PystrayMenu = None
PystrayMenuItem = None

try:
    import pystray
    from pystray import Icon as PystrayIcon, Menu as PystrayMenu, MenuItem as PystrayMenuItem
except ImportError:
    pass

# 尝试导入 Pillow
Image = None
try:
    from PIL import Image
except ImportError:
    pass


class SystemTrayIcon:
    """
    系统托盘图标管理器
    
    功能：
    - 创建托盘图标
    - 托盘菜单（显示/隐藏窗口、快速测速、刷新DNS、退出）
    - 托盘通知
    - 低资源占用（使用事件驱动而非轮询）
    """
    
    def __init__(
        self,
        app_name: str = "SmartHostsTool",
        on_show_window: Optional[Callable[[], None]] = None,
        on_hide_window: Optional[Callable[[], None]] = None,
        on_quick_test: Optional[Callable[[], None]] = None,
        on_flush_dns: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self.logger = get_logger()
        self.app_name = app_name
        
        # 回调函数
        self.on_show_window = on_show_window
        self.on_hide_window = on_hide_window
        self.on_quick_test = on_quick_test
        self.on_flush_dns = on_flush_dns
        self.on_exit = on_exit
        
        # 托盘图标实例
        self._icon: Optional[Any] = None
        self._icon_thread: Optional[threading.Thread] = None
        self._running = False
        self._window_visible = True
        
        # 检查依赖
        self._available = bool(pystray and Image)
        if not self._available:
            missing = []
            if not pystray:
                missing.append("pystray")
            if not Image:
                missing.append("Pillow")
            self.logger.warning(f"系统托盘不可用，缺少依赖: {', '.join(missing)}")
    
    @property
    def is_available(self) -> bool:
        """检查托盘功能是否可用"""
        return self._available
    
    @property
    def is_running(self) -> bool:
        """检查托盘是否正在运行"""
        return self._running
    
    def _load_icon_image(self) -> Optional[Any]:
        """加载托盘图标图片"""
        if not Image:
            return None
        
        # 尝试多个图标路径
        icon_paths = [
            resource_path("icon.ico"),
            resource_path("icon.png"),
        ]
        
        for path in icon_paths:
            if path and os.path.exists(path):
                try:
                    img = Image.open(path)
                    # 转换为合适的尺寸（托盘图标通常 16x16 或 32x32）
                    img = img.resize((32, 32), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
                    self.logger.debug(f"成功加载托盘图标: {path}")
                    return img
                except Exception as e:
                    self.logger.warning(f"加载图标失败 {path}: {e}")
        
        # 创建默认图标（蓝色圆形）
        try:
            img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.ellipse([2, 2, 30, 30], fill=(56, 189, 248, 255))
            self.logger.debug("使用默认生成的托盘图标")
            return img
        except Exception as e:
            self.logger.warning(f"创建默认图标失败: {e}")
            return None
    
    def _create_menu(self) -> Any:
        """创建托盘菜单"""
        if not PystrayMenu or not PystrayMenuItem:
            return None
        
        def toggle_window(icon, item):
            if self._window_visible:
                if self.on_hide_window:
                    self.on_hide_window()
                self._window_visible = False
            else:
                if self.on_show_window:
                    self.on_show_window()
                self._window_visible = True
        
        def quick_test(icon, item):
            if self.on_quick_test:
                self.on_quick_test()
        
        def flush_dns(icon, item):
            if self.on_flush_dns:
                self.on_flush_dns()
        
        def exit_app(icon, item):
            self.stop()
            if self.on_exit:
                self.on_exit()
        
        def get_window_text(item):
            return "隐藏窗口" if self._window_visible else "显示窗口"
        
        menu = PystrayMenu(
            PystrayMenuItem(get_window_text, toggle_window, default=True),
            PystrayMenu.SEPARATOR,
            PystrayMenuItem("快速测速", quick_test),
            PystrayMenuItem("刷新 DNS", flush_dns),
            PystrayMenu.SEPARATOR,
            PystrayMenuItem("退出程序", exit_app),
        )
        
        return menu
    
    def start(self) -> bool:
        """启动托盘图标（非阻塞）"""
        if not self._available:
            self.logger.warning("托盘功能不可用，跳过启动")
            return False
        
        if self._running:
            self.logger.debug("托盘已在运行")
            return True
        
        icon_image = self._load_icon_image()
        if not icon_image:
            self.logger.error("无法加载托盘图标")
            return False
        
        menu = self._create_menu()
        
        try:
            self._icon = PystrayIcon(
                name=self.app_name,
                icon=icon_image,
                title=f"{self.app_name} - 智能Hosts测速工具",
                menu=menu,
            )
            
            # 在单独的线程中运行托盘（避免阻塞主线程）
            self._running = True
            self._icon_thread = threading.Thread(target=self._run_icon, daemon=True)
            self._icon_thread.start()
            
            self.logger.info("系统托盘已启动")
            return True
        except Exception as e:
            self.logger.error(f"启动托盘失败: {e}")
            self._running = False
            return False
    
    def _run_icon(self):
        """在后台线程运行托盘图标"""
        try:
            if self._icon:
                self._icon.run()
        except Exception as e:
            self.logger.error(f"托盘运行出错: {e}")
        finally:
            self._running = False
    
    def stop(self):
        """停止托盘图标"""
        if self._icon:
            try:
                self._icon.stop()
                self.logger.info("系统托盘已停止")
            except Exception as e:
                self.logger.warning(f"停止托盘时出错: {e}")
        self._running = False
    
    def set_window_visible(self, visible: bool):
        """更新窗口可见状态（用于同步状态）"""
        self._window_visible = visible
    
    def show_notification(self, title: str, message: str):
        """显示托盘通知"""
        if not self._icon or not self._running:
            return
        
        try:
            # pystray 的 notify 方法
            if hasattr(self._icon, 'notify'):
                self._icon.notify(message, title)
                self.logger.debug(f"托盘通知: {title} - {message}")
        except Exception as e:
            self.logger.warning(f"显示托盘通知失败: {e}")
    
    def update_tooltip(self, text: str):
        """更新托盘图标提示文字"""
        if not self._icon or not self._running:
            return
        
        try:
            self._icon.title = text
        except Exception as e:
            self.logger.warning(f"更新托盘提示失败: {e}")


def check_tray_dependencies() -> tuple:
    """
    检查托盘依赖是否可用
    
    Returns:
        (is_available, missing_packages)
    """
    missing = []
    if not pystray:
        missing.append("pystray")
    if not Image:
        missing.append("Pillow")
    
    return len(missing) == 0, missing


def install_tray_dependencies():
    """尝试安装托盘依赖（仅提示，不自动安装）"""
    available, missing = check_tray_dependencies()
    if available:
        return True
    
    print(f"系统托盘功能需要安装以下依赖: {', '.join(missing)}")
    print(f"请运行: pip install {' '.join(missing)}")
    return False

