"""
Auto Start - Windows 开机自启管理
"""
import logging
import sys
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 注册表路径（当前用户，无需管理员权限）
AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "EasyPrintClient"


def is_autostart_enabled() -> bool:
    """检查是否已启用开机自启"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_REG_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Failed to check autostart: {e}")
        return False


def enable_autostart():
    """启用开机自启"""
    try:
        import winreg
        # 获取当前可执行文件路径
        if getattr(sys, "frozen", False):
            # 打包后的 exe
            exe_path = sys.executable
        else:
            # 开发模式：用 pythonw 运行 main.py
            python_exe = Path(sys.executable).parent / "pythonw.exe"
            if not python_exe.exists():
                python_exe = Path(sys.executable)
            script_path = Path(__file__).parent.parent.parent / "main.py"
            exe_path = f'"{python_exe}" "{script_path}"'

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, exe_path)

        logger.info(f"Autostart enabled: {exe_path}")
    except Exception as e:
        logger.error(f"Failed to enable autostart: {e}")


def disable_autostart():
    """禁用开机自启"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_REG_NAME)
        logger.info("Autostart disabled")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error(f"Failed to disable autostart: {e}")
