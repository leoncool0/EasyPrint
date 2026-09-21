"""
System Tray - 系统托盘图标
"""
import logging
import os
import sys
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


def get_assets_dir() -> str:
    """获取 assets 目录路径（兼容开发环境和 PyInstaller 打包环境）"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的路径
        return os.path.join(sys._MEIPASS, "assets")
    else:
        # 开发环境路径
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "assets")


class SystemTray(QObject):
    """系统托盘管理"""

    show_main_window = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    connect_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        assets_dir = get_assets_dir()
        logger.info(f"Assets directory: {assets_dir}")

        # 加载图标
        app_icon_path = os.path.join(assets_dir, "app.ico")
        tray_connected_path = os.path.join(assets_dir, "tray_connected.ico")
        tray_disconnected_path = os.path.join(assets_dir, "tray_disconnected.ico")

        # 连接状态图标
        if os.path.exists(tray_disconnected_path):
            self._disconnected_icon = QIcon(tray_disconnected_path)
        else:
            self._disconnected_icon = QIcon()
            logger.warning(f"Tray disconnected icon not found: {tray_disconnected_path}")

        if os.path.exists(tray_connected_path):
            self._connected_icon = QIcon(tray_connected_path)
        else:
            self._connected_icon = self._disconnected_icon
            logger.warning(f"Tray connected icon not found: {tray_connected_path}")

        # 应用图标（用于主窗口）
        if os.path.exists(app_icon_path):
            self.app_icon = QIcon(app_icon_path)
        else:
            self.app_icon = self._disconnected_icon
            logger.warning(f"App icon not found: {app_icon_path}")

        # 创建托盘图标（初始为断开状态）
        self.tray = QSystemTrayIcon(self._disconnected_icon, parent)
        self.tray.setToolTip("EasyPrint - 未连接")

        # 创建右键菜单
        self._create_menu()

        # 双击托盘图标
        self.tray.activated.connect(self._on_activated)

    def _create_menu(self):
        """创建右键菜单"""
        menu = QMenu()

        # 连接/断开菜单项
        self.connect_action = menu.addAction("连接服务器")
        self.connect_action.triggered.connect(self.connect_requested.emit)

        self.disconnect_action = menu.addAction("断开服务器")
        self.disconnect_action.triggered.connect(self.disconnect_requested.emit)
        self.disconnect_action.setVisible(False)

        menu.addSeparator()

        # 显示主界面
        self.show_action = menu.addAction("显示主界面")
        self.show_action.triggered.connect(self.show_main_window.emit)

        menu.addSeparator()

        # 重新设置
        self.settings_action = menu.addAction("重新设置")
        self.settings_action.triggered.connect(self.settings_requested.emit)

        menu.addSeparator()

        # 退出
        self.quit_action = menu.addAction("退出")
        self.quit_action.triggered.connect(self.quit_requested.emit)

        self.tray.setContextMenu(menu)

    def set_connected(self, connected: bool):
        """设置连接状态并更新图标和菜单"""
        if connected:
            self.tray.setIcon(self._connected_icon)
            self.tray.setToolTip("EasyPrint - 已连接")
            self.connect_action.setVisible(False)
            self.disconnect_action.setVisible(True)
        else:
            self.tray.setIcon(self._disconnected_icon)
            self.tray.setToolTip("EasyPrint - 未连接")
            self.connect_action.setVisible(True)
            self.disconnect_action.setVisible(False)

    def _on_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main_window.emit()

    def show(self):
        """显示托盘图标"""
        self.tray.show()

    def show_message(self, title: str, message: str):
        """显示气泡通知"""
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def set_tooltip(self, text: str):
        """设置提示文字"""
        self.tray.setToolTip(text)
