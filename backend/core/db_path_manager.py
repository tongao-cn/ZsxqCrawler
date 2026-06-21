#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path

from backend.core.console_output import safe_console_print

print = safe_console_print

_DEFAULT_CONFIG_TOML = """# 知识星球数据采集器配置文件
# 首次启动自动生成；请按需修改

[auth]
# 知识星球登录 Cookie（Web 模式可留空，推荐使用“账号管理”配置）
cookie = "your_cookie_here"
# 旧单群组本地配置可留空；Web/API 会按当前群组动态选择
group_id = "your_group_id_here"

[download]
# 下载目录
dir = "downloads"

[ai]
# OpenAI 兼容模型配置（仅从项目内 config.toml 读取）
model = "gpt-5.5"
api_base = "https://api.openai.com/v1"
wire_api = "responses"
reasoning_effort = "low"
api_key = ""

[database]
# backend = "postgres"
# postgres_dsn = "postgresql://user:password@localhost:5432/zsxq"
"""


class DatabasePathManager:
    """本地资源路径管理器 - 统一管理下载和图片缓存目录。"""
    
    def __init__(self, base_dir: str = "output/databases"):
        # 以仓库根目录作为项目根目录，避免模块移动后把数据写入 backend/core。
        self.project_root = str(Path(__file__).resolve().parents[2])
        self._ensure_config_toml()

        # 确保使用项目根目录的绝对路径
        self.base_dir = base_dir if os.path.isabs(base_dir) else os.path.join(self.project_root, base_dir)

        self._ensure_base_dir()

    def _ensure_config_toml(self) -> None:
        """确保 config.toml 存在（不存在则创建默认模板）。"""
        config_path = os.path.join(self.project_root, "config.toml")
        if os.path.exists(config_path):
            return

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(_DEFAULT_CONFIG_TOML)
        except Exception as e:
            # 不能因为写配置失败导致程序无法启动；后续 load_config 会给出提示
            print(f"⚠️ 无法自动创建 config.toml: {e}")
    
    def _ensure_base_dir(self):
        """确保基础目录存在"""
        self._ensure_dir(self.base_dir, "本地资源目录")

    def _normalize_group_id(self, group_id: str) -> str:
        """归一化群组ID为路径组件使用的字符串。"""
        normalized = str(group_id).strip()
        if not normalized or normalized in {".", ".."}:
            raise ValueError("group_id must be a single path component")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("group_id must be a single path component")
        return normalized

    def _resolve_group_dir(self, group_id: str) -> Path:
        base_dir = Path(self.base_dir).resolve()
        group_dir = (base_dir / self._normalize_group_id(group_id)).resolve()
        if group_dir == base_dir or base_dir not in group_dir.parents:
            raise ValueError("group_id path escapes local resource directory")
        return group_dir

    def _ensure_dir(self, path: str, label: str) -> None:
        """确保目录存在。"""
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            print(f"创建{label}: {path}")

    def get_group_dir(self, group_id: str) -> str:
        """获取指定群组的本地资源目录。"""
        group_dir = str(self._resolve_group_dir(group_id))
        self._ensure_dir(group_dir, "群组目录")
        return group_dir

    def get_group_data_dir(self, group_id: str):
        """获取指定群组的数据目录（返回Path对象）"""
        return Path(self.get_group_dir(group_id))
    
    def list_all_groups(self) -> list:
        """列出所有存在的群组ID"""
        groups = []
        if not os.path.exists(self.base_dir):
            return groups
        
        for item in os.listdir(self.base_dir):
            item_path = os.path.join(self.base_dir, item)
            if os.path.isdir(item_path) and item.isdigit():  # 群组ID目录
                groups.append({
                    'group_id': item,
                    'group_dir': item_path,
                })
        
        return groups
    
    def cleanup_empty_dirs(self):
        """清理空的群组目录"""
        if not os.path.exists(self.base_dir):
            return
        
        for item in os.listdir(self.base_dir):
            item_path = os.path.join(self.base_dir, item)
            if os.path.isdir(item_path) and item.isdigit():  # 群组ID目录
                if not os.listdir(item_path):  # 空目录
                    os.rmdir(item_path)
                    print(f"删除空目录: {item_path}")

# 全局实例
db_path_manager = DatabasePathManager()

def get_db_path_manager() -> DatabasePathManager:
    """获取本地资源路径管理器实例。"""
    return db_path_manager
