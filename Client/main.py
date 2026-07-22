"""
EasyPrint Client - 主入口
"""
import sys
import logging
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import qasync
from PySide6.QtWidgets import QApplication, QWizard

from src.core.config_manager import config, APP_NAME, APP_VERSION
from src.core.client import Client, get_computer_name
from src.ui.main_window import MainWindow
from src.ui.setup_wizard import SetupWizard
from src.ui.tray import SystemTray
from src.utils.autostart import enable_autostart, disable_autostart

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

    # ==================== 创建客户端和界面 ====================
    client = Client()

    window = MainWindow(client)
    window.set_tray_notify_callback(
        lambda: tray.show_message("EasyPrint", "程序已最小化到托盘，双击图标可恢复窗口")
    )

    # 设置按钮 -> 重新配置
    window.settings_requested.connect(lambda: on_settings(client, window, tray))

    # 系统托盘
    tray = SystemTray()
    tray.show_main_window.connect(window.show_from_tray)
    tray.settings_requested.connect(lambda: on_settings(client, window, tray))
    tray.quit_requested.connect(lambda: on_quit(app, client))
    tray.show()

    # ==================== 自动连接 ====================
    logger.info("自动连接服务端...")
    await client.auto_connect()

    # 首次运行或正常启动都最小化到托盘
    tray.show_message("EasyPrint", "客户端已启动并连接服务端")

    # 保持运行
    quit_future = asyncio.get_event_loop().create_future()
    app.aboutToQuit.connect(lambda: quit_future.set_result(None))
    await quit_future

    # 清理
    logger.info("正在关闭...")
    client.stop()


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
