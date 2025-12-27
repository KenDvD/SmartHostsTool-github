# -*- coding: utf-8 -*-
"""
hosts_file.py

hosts 文件相关的“系统层”能力抽离：
- 读取（自动猜测编码，尽量保留 BOM）
- 多方案写入（含权限不足时自动提权重启）
- 自动备份 / 列表 / 最近备份
- 写入 SmartHostsTool 标记块、清理旧块（安全策略）
- 刷新 DNS、打开 hosts 文件

该模块不依赖 ttkbootstrap/tkinter，避免与 UI 层耦合。
"""

from __future__ import annotations

import codecs
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from config import (
    BACKUP_DIR,
    BACKUP_FILE_FMT,
    HOSTS_END_MARK,
    HOSTS_PATH,
    HOSTS_START_MARK,
)
from utils import restart_as_admin


@dataclass
class RemoveBlockResult:
    content: str
    removed: bool
    marker_damaged: bool


class HostsFileManager:
    def __init__(
        self,
        *,
        hosts_path: str = HOSTS_PATH,
        backup_dir: str = BACKUP_DIR,
        backup_file_fmt: str = BACKUP_FILE_FMT,
        start_mark: str = HOSTS_START_MARK,
        end_mark: str = HOSTS_END_MARK,
    ) -> None:
        self.hosts_path = hosts_path
        self.backup_dir = backup_dir
        self.backup_file_fmt = backup_file_fmt
        self.start_mark = start_mark
        self.end_mark = end_mark

    # -----------------------------------------------------------------
    # Backup
    # -----------------------------------------------------------------
    def ensure_backup_dir(self) -> str:
        os.makedirs(self.backup_dir, exist_ok=True)
        return self.backup_dir

    def create_backup(self) -> str:
        """写入前自动备份 hosts。"""
        self.ensure_backup_dir()
        ts_name = datetime.now().strftime(self.backup_file_fmt)
        bak_path = os.path.join(self.backup_dir, ts_name)
        shutil.copy2(self.hosts_path, bak_path)
        return bak_path

    def list_backups(self) -> List[str]:
        if not os.path.isdir(self.backup_dir):
            return []
        items: List[str] = []
        for fn in os.listdir(self.backup_dir):
            if re.fullmatch(r"hosts_\d{8}_\d{6}\.bak", fn):
                items.append(os.path.join(self.backup_dir, fn))
        items.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return items

    def latest_backup(self) -> Optional[str]:
        lst = self.list_backups()
        return lst[0] if lst else None

    # -----------------------------------------------------------------
    # Read/Write
    # -----------------------------------------------------------------
    @staticmethod
    def read_text_guess_encoding(path: str) -> Tuple[str, str]:
        """读取文本并尽量保留原始编码特征（尤其是 UTF-8 BOM）。

        返回 (text, encoding_used)。

        规则（与原版一致）：
        - 若检测到 UTF-8 BOM：使用 utf-8-sig（写回时保留 BOM）
        - 若检测到 UTF-16 BOM：使用 utf-16
        - 否则优先 utf-8；失败后 Windows 上用 mbcs；再尝试 gbk；最后忽略错误
        """
        with open(path, "rb") as f:
            raw = f.read()

        if raw.startswith(codecs.BOM_UTF8):
            try:
                return raw.decode("utf-8-sig"), "utf-8-sig"
            except Exception:
                pass

        if raw.startswith(codecs.BOM_UTF16_LE):
            try:
                return raw.decode("utf-16-le"), "utf-16-le"
            except Exception:
                pass

        if raw.startswith(codecs.BOM_UTF16_BE):
            try:
                return raw.decode("utf-16-be"), "utf-16-be"
            except Exception:
                pass

        # 无 BOM：不要用 utf-8-sig（否则写回会引入 BOM）
        try:
            return raw.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            pass

        # Windows：mbcs = 系统 ANSI 代码页（比强行 gbk 更通用）
        if sys.platform == "win32":
            try:
                return raw.decode("mbcs"), "mbcs"
            except Exception:
                pass

        try:
            return raw.decode("gbk"), "gbk"
        except Exception:
            pass

        return raw.decode("utf-8", errors="ignore"), "utf-8"

    def read_hosts_text(self) -> Tuple[str, str]:
        return self.read_text_guess_encoding(self.hosts_path)

    def write_hosts_atomic(
        self,
        text: str,
        *,
        encoding: str = "utf-8",
        allow_elevate: bool = True,
        on_need_elevation: Optional[Callable[[], None]] = None,
    ) -> None:
        """多方案写入 hosts。

        - 方案1：直接写入
        - 方案2：系统临时目录写入 + shutil.copy2 覆盖
        - 方案3：hosts 同目录 .smarttmp + os.replace 原子替换
        - 若判断为权限问题：可选自动提权重启（allow_elevate=True）
        """
        tmp_path: Optional[str] = None
        hosts_tmp: Optional[str] = None

        # 方案1：直接写入（最直接的方法，优先尝试）
        try:
            with open(self.hosts_path, "w", encoding=encoding, newline="\n") as f:
                f.write(text)
            return
        except Exception:
            pass

        # 方案2：使用系统临时目录 + shutil.copy2（避免部分路径限制）
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding=encoding,
                newline="\n",
                suffix=".smarttmp",
                delete=False,
            ) as f:
                f.write(text)
                tmp_path = f.name

            shutil.copy2(tmp_path, self.hosts_path)
            os.remove(tmp_path)
            return
        except Exception:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        # 方案3：在 hosts 文件所在目录创建临时文件 + os.replace（更接近“原子”）
        try:
            hosts_tmp = self.hosts_path + ".smarttmp"
            with open(hosts_tmp, "w", encoding=encoding, newline="\n") as f:
                f.write(text)

            os.replace(hosts_tmp, self.hosts_path)
            return
        except Exception:
            if hosts_tmp and os.path.exists(hosts_tmp):
                try:
                    os.remove(hosts_tmp)
                except Exception:
                    pass

        # 所有方法都失败：判断是否权限问题，必要时提权重启
        error_msg = traceback.format_exc()
        is_perm = ("permission denied" in error_msg.lower()) or ("拒绝访问" in error_msg)

        if allow_elevate and is_perm and sys.platform == "win32":
            if on_need_elevation:
                try:
                    on_need_elevation()
                except Exception:
                    pass

            # 保存要写入的内容到临时文件，以便提权后直接写入（writer mode）
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding=encoding,
                newline="\n",
                suffix=".hostscontent",
                delete=False,
            ) as f:
                f.write(text)
                temp_content_path = f.name

            args = sys.argv.copy()
            args.append(f"--write-content={temp_content_path}")
            args.append(f"--encoding={encoding}")
            restart_as_admin(args)

        raise PermissionError("无法写入 hosts 文件：尝试了多种写入方案均失败。")

    # -----------------------------------------------------------------
    # SmartHostsTool block
    # -----------------------------------------------------------------
    def remove_existing_smart_block(self, content: str) -> RemoveBlockResult:
        """移除旧的 SmartHostsTool 标记块（Start..End），安全策略与原版一致。

        - 若 Start 与 End 都存在且顺序正确：删除旧块
        - 若仅存在 Start 或 End（标记损坏）：不激进删除，保持原内容，marker_damaged=True
        """
        s_idx = content.find(self.start_mark)
        e_idx = content.find(self.end_mark)

        # 标记损坏：只有一边
        if (s_idx != -1) ^ (e_idx != -1):
            return RemoveBlockResult(content=content, removed=False, marker_damaged=True)

        if s_idx != -1 and e_idx != -1 and s_idx < e_idx:
            pat = re.compile(
                rf"{re.escape(self.start_mark)}.*?{re.escape(self.end_mark)}\s*",
                re.DOTALL,
            )
            new_c, n = pat.subn("", content, count=1)
            return RemoveBlockResult(content=new_c, removed=(n > 0), marker_damaged=False)

        return RemoveBlockResult(content=content, removed=False, marker_damaged=False)

    def build_block(self, records: List[Tuple[str, str]]) -> str:
        """构建写入段（与原版一致）。"""
        return (
            f"\n{self.start_mark}\n"
            + "\n".join([f"{ip} {dom}" for ip, dom in records])
            + f"\n{self.end_mark}\n"
        )

    # -----------------------------------------------------------------
    # OS utilities
    # -----------------------------------------------------------------
    @staticmethod
    def flush_dns_cache() -> None:
        """刷新 DNS 缓存（Windows）。"""
        if sys.platform != "win32":
            return
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        except Exception:
            startupinfo = None
        subprocess.run("ipconfig /flushdns", shell=True, startupinfo=startupinfo)

    def open_hosts_file(self) -> None:
        """用系统默认方式打开 hosts 文件。"""
        try:
            os.startfile(self.hosts_path)  # type: ignore[attr-defined]
            return
        except Exception:
            pass

        # fallback：notepad（仅Windows）
        if sys.platform == "win32":
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            except Exception:
                startupinfo = None
            subprocess.run(["notepad", self.hosts_path], startupinfo=startupinfo)
