"""
EasyPrint Client - 主入口
"""
import sys
import os
import struct

# ==================== 架构检测（必须在导入 Qt 之前执行） ====================
# PySide6 仅提供 64 位 Windows wheel，32 位系统无法运行
if struct.calcsize("P") * 8 < 64:
    # 在导入 Qt 前弹窗提示
    import ctypes
    MB_ICONERROR = 0x00000010
    MB_OK = 0x00000000
    ctypes.windll.user32.MessageBoxW(
        0,
        "EasyPrint 不支持 32 位 Windows 系统。\n\n"
        "请使用 64 位版本的 Windows（Win 7 64 位 / Win 10 / Win 11）。\n\n"
        "如需帮助请联系管理员。",
        "EasyPrint - 不支持的系统",
        MB_ICONERROR | MB_OK,
    )
    sys.exit(1)

import logging
import asyncio
from pathlib import Path

# 切换工作目录到 exe 所在目录
# 开机自启时 CWD 是 C:\Windows\System32，需切回程序目录才能找到 config/logs/spool
if getattr(sys, "frozen", False):
    os.chdir(Path(sys.executable).parent)
else:
    os.chdir(Path(__file__).parent)

sys.path.insert(0, str(Path(__file__).parent))

import qasync
from PySide6.QtWidgets import QApplication, QWizard

from src.core.config_manager import config, APP_NAME, APP_VERSION
from src.core.client import Client, get_computer_name
from src.ui.main_window import MainWindow
from src.ui.setup_wizard import SetupWizard
from src.ui.tray import SystemTray, get_assets_dir
from src.utils.autostart import enable_autostart, disable_autostart, is_autostart_enabled

# 创建必要目录
Path("config").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)
Path("spool").mkdir(exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path("logs") / "client.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


def run_async(coro):
    """在 Qt 事件循环中运行异步协程"""
    loop = asyncio.get_event_loop()
    loop.create_task(coro)


async def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出程序（托盘保活）

    logger.info(f"启动 {APP_NAME} v{APP_VERSION}")

    # ==================== 重新验证开机自启状态 ====================
    # 注册表项可能被杀毒软件清理，每次启动时重新同步
    if config.auto_start and not is_autostart_enabled():
        logger.info("检测到自启已失效，重新启用")
        ok = enable_autostart()
        if not ok:
            logger.warning("重新启用自启失败")
    elif not config.auto_start and is_autostart_enabled():
        logger.info("检测到自启未关闭，重新禁用")
        disable_autostart()

    # ==================== 首次运行：向导 ====================
    if not config.is_configured():
        wizard = SetupWizard()
        if wizard.exec() != QWizard.DialogCode.Accepted:
            logger.info("用户取消了配置向导")
            sys.exit(0)

        # 保存配置
        new_config = wizard.get_config()
        config.update(**new_config)
        config.save()

        # 开机自启
        if config.auto_start:
            enable_autostart()
        else:
            disable_autostart()

        logger.info("配置已保存")

    # ==================== 系统托盘 ====================
    tray = SystemTray()
    tray.quit_requested.connect(lambda: on_quit(app, client))

    # ==================== 创建客户端和界面 ====================
    client = Client()

    window = MainWindow(client)
    window.setWindowIcon(tray.app_icon)
    window.set_tray_notify_callback(
        lambda: tray.show_message("EasyPrint", "程序已最小化到托盘，双击图标可恢复窗口")
    )

    # 设置按钮 -> 重新配置
    window.settings_requested.connect(lambda: on_settings(client, window, tray))

    # 托盘信号连接（窗口创建后）
    tray.show_main_window.connect(lambda: window.show_from_tray())
    tray.settings_requested.connect(lambda: on_settings(client, window, tray))
    tray.connect_requested.connect(lambda: on_connect(client, tray))
    tray.disconnect_requested.connect(lambda: on_disconnect(client, tray))

    # ==================== 状态回调 -> 更新托盘图标 ====================
    def on_status_changed(status: str, detail: str = ""):
        """状态变更时更新托盘图标和菜单"""
        if status in ("connected", "authenticated"):
            tray.set_connected(True)
        elif status in ("disconnected", "error", "auth_failed"):
            tray.set_connected(False)

    client.on_status_changed(on_status_changed)

    tray.show()

    # ==================== 自动连接 ====================
    logger.info("自动连接服务端...")
    tray.set_connected(False)  # 初始为未连接
    await client.auto_connect()

    # 根据连接状态更新图标
    if client.connected:
        tray.set_connected(True)
        tray.show_message("EasyPrint", "客户端已启动并连接服务端")
    else:
        tray.set_connected(False)
        tray.show_message("EasyPrint", "客户端已启动，但连接服务端失败")

    # 保持运行
    quit_future = asyncio.get_event_loop().create_future()
    app.aboutToQuit.connect(lambda: quit_future.set_result(None))
    await quit_future

    # 清理
    logger.info("正在关闭...")
    client.stop()


def on_connect(client: Client, tray: SystemTray):
    """连接服务器"""
    if not client.connected:
        tray.show_message("EasyPrint", "正在连接服务器...")
        run_async(client.auto_connect())


def on_disconnect(client: Client, tray: SystemTray):
    """断开服务器"""
    if client.connected:
        tray.show_message("EasyPrint", "正在断开服务器...")
        run_async(client.disconnect())


def on_settings(client: Client, window: MainWindow, tray: SystemTray):
    """重新设置"""
    # 断开当前连接
    if client.connected:
        run_async(client.disconnect())

    # 显示向导
    wizard = SetupWizard()
    if wizard.exec() == QWizard.DialogCode.Accepted:
        new_config = wizard.get_config()
        config.update(**new_config)
        config.save()

        # 更新开机自启
        if config.auto_start:
            enable_autostart()
        else:
            disable_autostart()

        # 更新客户端配置
        client.device_type = config.device_type
        client.device_name = config.device_name or get_computer_name()

        # 更新窗口显示
        window.device_name_label.setText(config.device_name or "未设置")
        type_map = {"host": "主机端", "user": "用户端", "mixed": "混合模式"}
        window.device_type_label.setText(type_map.get(config.device_type, config.device_type))
        window.server_label.setText(f"{config.server_host}:{config.server_tcp_port}")

        # 重新连接
        run_async(client.auto_connect())
        tray.show_message("EasyPrint", "配置已更新，正在重新连接...")


def on_quit(app: QApplication, client: Client):
    """退出程序"""
    client.stop()
    app.quit()


if __name__ == "__main__":
    qasync.run(main())
