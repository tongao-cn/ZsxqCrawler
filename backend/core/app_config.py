from __future__ import annotations

import os

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    try:
        import tomli as tomllib
    except ImportError:  # pragma: no cover
        print("⚠️ 需要安装tomli库来解析TOML配置文件")
        print("💡 请运行: pip install tomli")
        tomllib = None


def load_config():
    """加载TOML配置文件"""
    if tomllib is None:
        return None

    # 尝试多个可能的配置文件路径
    config_paths = [
        "config.toml",           # 当前目录
        "../config.toml",        # 上级目录（从backend目录运行时）
        "../../config.toml"      # 上上级目录
    ]

    config_file = None
    for path in config_paths:
        if os.path.exists(path):
            config_file = path
            break

    if config_file is None:
        print("⚠️ 未找到config.toml配置文件，请先创建并配置")
        print("💡 可以复制config.toml.example为config.toml并修改")
        return None
    
    try:
        with open(config_file, 'rb') as f:
            config = tomllib.load(f)
        
        print("✅ 已从config.toml加载配置")
        return config
    except Exception as e:
        print(f"❌ 加载配置文件出错: {e}")
        return None

