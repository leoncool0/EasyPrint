"""
Config Manager - 配置持久化
"""
import json
import platform
from pathlib import Path
from typing import Any, Optional

CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULT_CONFIG = {
    "server_host": "10.1.2.110",
    "server_tcp_port": 9100,
    "server_http_port": 8080,
    "device_name": "",
    "device_type": "user",  # host, user, mixed
    "auto_start": False,
    "token": "",
    "shared_printers": [],     # 主机端: 要共享的本机打印机名称列表
    "virtual_printers": [],    # 用户端: 已安装的虚拟打印机 [{name, printer_id}]
    "configured": False,       # 是否已完成首次配置
}

APP_NAME = "EasyPrint Client"
APP_VERSION = "0.1.0"


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self.config: dict = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        """从文件加载配置"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.config.update(loaded)
            except Exception:
                pass

    def save(self):
        """保存配置到文件"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def is_configured(self) -> bool:
        """是否已完成首次配置"""
        return self.config.get("configured", False)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value

    def update(self, **kwargs):
        self.config.update(kwargs)

    @property
    def server_host(self) -> str:
        return self.config.get("server_host", "")

    @property
    def server_tcp_port(self) -> int:
        return self.config.get("server_tcp_port", 9100)

    @property
    def server_http_port(self) -> int:
        return self.config.get("server_http_port", 8080)

    @property
    def device_name(self) -> str:
        return self.config.get("device_name", "")

    @property
    def device_type(self) -> str:
        return self.config.get("device_type", "user")

    @property
    def auto_start(self) -> bool:
        return self.config.get("auto_start", False)

    @property
    def token(self) -> str:
        return self.config.get("token", "")

    @property
    def shared_printers(self) -> list:
        return self.config.get("shared_printers", [])

    @property
    def virtual_printers(self) -> list:
        return self.config.get("virtual_printers", [])


# 全局配置实例
config = ConfigManager()
