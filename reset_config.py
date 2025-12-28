# -*- coding: utf-8 -*-
"""
重置测速配置为默认值
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import SpeedTestConfigManager
from config import SPEED_TEST_CONFIG

def reset_config():
    """重置配置为默认值"""
    print("=" * 60)
    print("重置测速配置为默认值")
    print("=" * 60)
    
    try:
        manager = SpeedTestConfigManager()
        config_path = manager.get_config_path()
        
        print(f"\n配置文件路径: {config_path}")
        
        if os.path.exists(config_path):
            print("发现已存在的配置文件，将重置为默认值...")
        else:
            print("配置文件不存在，将创建默认配置...")
        
        # 重置为默认值
        default_config = manager.reset_to_default()
        
        print("\n[SUCCESS] 配置已重置为默认值！")
        print("\n默认配置值：")
        print(f"  TCP端口: {default_config['tcp']['port']}")
        print(f"  TCP尝试次数: {default_config['tcp']['attempts']}")
        print(f"  TCP超时: {default_config['tcp']['timeout']}")
        print(f"  TLS超时: {default_config['tls']['timeout']}")
        print(f"  ICMP超时: {default_config['icmp']['timeout_ms']}")
        print(f"  最大重试次数: {default_config['retry']['max_retries']}")
        print(f"  退避因子: {default_config['retry']['backoff_factor']}")
        
        print("\n请重新打开测速设置窗口，TCP端口应该显示为443。")
        return True
        
    except Exception as e:
        print(f"[ERROR] 重置失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = reset_config()
    sys.exit(0 if success else 1)

