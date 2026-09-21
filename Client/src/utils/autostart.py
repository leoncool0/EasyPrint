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


def _get_current_exe_path() -> str:
    """获取当前可执行文件路径（用于注册表写入，已加引号）

    用户可能更改 exe 文件名（如把 EasyPrint Client.exe 改为 共享打印.exe），
    因此每次都通过 sys.executable 动态获取当前实际路径。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    else:
        python_exe = Path(sys.executable).parent / "pythonw.exe"
        if not python_exe.exists():
            python_exe = Path(sys.executable)
        script_path = Path(__file__).parent.parent.parent / "main.py"
        return f'"{python_exe}" "{script_path}"'


def is_autostart_enabled() -> bool:
    """检查是否已启用开机自启（且注册表路径与当前 exe 一致）"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            current_path = _get_current_exe_path()
            if value != current_path:
                logger.info(f"Autostart path mismatch: registry={value!r}, current={current_path!r}")
                return False
            return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Failed to check autostart: {e}")
        return False


def enable_autostart() -> bool:
    """启用开机自启，返回是否成功"""
    try:
        import winreg
        exe_path = _get_current_exe_path()

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY) as key:
            winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, exe_path)

        # 验证写入
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            saved, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            if saved == exe_path:
                logger.info(f"Autostart enabled: {exe_path}")
                return True
            else:
                logger.error(f"Autostart verify failed: expected={exe_path!r}, got={saved!r}")
                return False
    except Exception as e:
        logger.error(f"Failed to enable autostart: {e}")
        return False


def disable_autostart() -> bool:
    """禁用开机自启，返回是否成功"""
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY) as key:
            winreg.DeleteValue(key, APP_REG_NAME)
        logger.info("Autostart disabled")
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        logger.error(f"Failed to disable autostart: {e}")
        return False
