# -*- coding: utf-8 -*-
"""
config.py

集中管理 SmartHostsTool 的配置与常量，便于后期扩展与维护。
"""

from __future__ import annotations

import os
import sys

APP_NAME = "SmartHostsTool"
APP_THEME = "vapor"

# 远程 Hosts 功能目前仅针对 GitHub（逻辑上：只有选择 github.com 预设时启用刷新远程 hosts）
GITHUB_TARGET_DOMAIN = "github.com"

# Windows hosts 文件路径（本工具主要面向 Windows）
if sys.platform == "win32":
    HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
elif sys.platform == "darwin":
    HOSTS_PATH = "/etc/hosts"
else:
    HOSTS_PATH = "/etc/hosts"

# 备份目录：%LOCALAPPDATA%\SmartHostsTool\hosts_backups\
BACKUP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    APP_NAME,
    "hosts_backups",
)
BACKUP_FILE_FMT = "hosts_%Y%m%d_%H%M%S.bak"

# 写入 hosts 时追加的标记块
HOSTS_START_MARK = "# === SmartHostsTool Start ==="
HOSTS_END_MARK = "# === SmartHostsTool End ==="

# requests 超时： (connect_timeout, read_timeout)
REMOTE_FETCH_TIMEOUT = (5, 15)

# 远程 hosts 源（按优先级）
REMOTE_HOSTS_URLS = [
    "https://github-hosts.tinsfox.com/hosts",
    "https://raw.hellogithub.com/hosts",
    "https://raw.githubusercontent.com/521xueweihan/GitHub520/main/hosts",
    "https://fastly.jsdelivr.net/gh/521xueweihan/GitHub520@main/hosts",
    "https://cdn.jsdelivr.net/gh/521xueweihan/GitHub520@main/hosts",
    "https://ghproxy.com/https://raw.githubusercontent.com/521xueweihan/GitHub520/main/hosts",
    "https://gitlab.com/ineo6/hosts/-/raw/master/hosts",
]

# UI 上用于选择远程 hosts 源的显示项（保留原版文字）
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

SPEED_TEST_CONFIG = {
    "tcp": {
        "port": 443,
        "attempts": 10,
        "timeout": 2.0,
        "interval": 0.02,
    },
    "tls": {
        "enabled": True,
        "timeout": 2.5,
        "verify_hostname": False,
        # strict=True  -> TLS/SNI 验证失败则判定该 IP 不可用（更安全，可能更"挑"）
        # strict=False -> TCP 可用即保留为"可用(TCP,TLS失败)"（不至于全红；写入最优时仍优先选 TLS 通过的）
        "strict": False,
        # 对同一 IP，最多尝试多少个候选域名做 SNI 验证（避免一开始选到不匹配域名导致误判）
        "try_hosts_limit": 3,
        # 候选域名优先级（存在于该 IP 关联域名列表时优先尝试）
        "preferred_hosts": [
            "github.com",
            "api.github.com",
            "raw.githubusercontent.com",
            "githubusercontent.com",
            "github.githubassets.com",
        ],
    },
    "icmp": {
        "enabled": True,
        "timeout_ms": 2000,
        "fallback_only": True,
    },
    "retry": {
        "enabled": True,
        "max_retries": 2,
        "backoff_factor": 1.5,
    },
    "advanced": {
        "measure_jitter": True,
        "calculate_stability": True,
    },
}

# HTTP 客户端配置
# 用途：配置远程 Hosts 获取时的 HTTP 连接行为
# 注意：
#   - retry.total: 最大重试次数，建议 2-5 次，过多会导致响应变慢
#   - retry.connect/connect: 连接超时重试次数，通常与 total 相同
#   - retry.read: 读取超时重试次数，通常与 total 相同
#   - retry.backoff_factor: 退避因子，建议 0.3-1.0，值越大重试间隔越长
#   - retry.status_forcelist: 需要重试的 HTTP 状态码列表
#   - pool.connections: 连接池大小，建议 10-50，根据并发需求调整
#   - pool.maxsize: 连接池最大大小，建议与 connections 相同
HTTP_CLIENT_CONFIG = {
    "retry": {
        "total": 3,
        "connect": 3,
        "read": 3,
        "backoff_factor": 0.5,
        "status_forcelist": [429, 500, 502, 503, 504],
    },
    "pool": {
        "connections": 20,
        "maxsize": 20,
    },
}

# DNS 解析器配置
# 用途：配置域名解析时的并发工作线程数
# 注意：
#   - max_workers: 最大并发解析线程数，建议 10-50
#     - 值过小：解析速度慢，用户体验差
#     - 值过大：占用过多系统资源，可能导致 DNS 服务器限流
#     - 推荐值：20（平衡速度与资源占用）
DNS_RESOLVER_CONFIG = {
    "max_workers": 20,
}

# UI 界面配置
# toast: 通知显示时长（毫秒）
# delay_thresholds: 延迟阈值（warning_ms: 超过此值标记为"差"）
UI_CONFIG = {
    "toast": {
        "default_duration_ms": 1800,
    },
    "delay_thresholds": {
        "warning_ms": 200,
    },
}
