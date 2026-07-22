"""
System Tray - 系统托盘图标
"""
import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import QObject, Signal, Qt

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


def create_app_icon() -> QIcon:
    """创建应用图标（蓝色圆圈 + P 字母）"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 蓝色圆圈背景
    painter.setBrush(QColor("#1890ff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)

    # 白色 "P" 字母
    painter.setPen(QColor("#ffffff"))
    font = QFont("Arial", 28, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "P")

    painter.end()
    return QIcon(pixmap)


class SystemTray(QObject):
    """系统托盘管理"""

    show_main_window = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.tray = QSystemTrayIcon(create_app_icon(), parent)
        self.tray.setToolTip("EasyPrint 客户端")

        # 创建右键菜单
        menu = QMenu()

        self.show_action = QAction("显示主界面", menu)
        self.show_action.triggered.connect(self.show_main_window.emit)
        menu.addAction(self.show_action)

        menu.addSeparator()

        self.settings_action = QAction("重新设置", menu)
        self.settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(self.settings_action)

        menu.addSeparator()

        self.quit_action = QAction("退出", menu)
        self.quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(self.quit_action)

        self.tray.setContextMenu(menu)

        # 双击托盘图标
        self.tray.activated.connect(self._on_activated)

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
