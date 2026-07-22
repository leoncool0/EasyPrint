"""
Main Window - 主界面
"""
import logging
import asyncio
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QListWidget,
    QGroupBox, QTabWidget, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import QTimer, Signal

from src.core.config_manager import config, APP_NAME, APP_VERSION

if TYPE_CHECKING:
    from src.core.client import Client

logger = logging.getLogger(__name__)


def run_async(coro):
    """在 Qt 事件循环中运行异步协程"""
    loop = asyncio.get_event_loop()
    loop.create_task(coro)


class MainWindow(QMainWindow):
    """主界面窗口"""

    # 信号
    settings_requested = Signal()

    def __init__(self, client: "Client"):
        super().__init__()
        self.client = client

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(560, 420)
        self.resize(560, 420)

        self._setup_ui()

        # 注册客户端回调
        self.client.on_status_changed(self._on_status_changed)
        self.client.on_printers_updated(self._on_printers_updated)
        self.client.on_job_status(self._on_job_status)

        # 最小化到托盘标志
        self._tray_mode = False

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ==================== 顶部状态栏 ====================
        status_group = QGroupBox("连接状态")
        status_layout = QFormLayout(status_group)

        self.server_label = QLabel(f"{config.server_host}:{config.server_tcp_port}")
        status_layout.addRow("服务端:", self.server_label)

        self.device_name_label = QLabel(config.device_name or "未设置")
        status_layout.addRow("设备名称:", self.device_name_label)

        type_map = {"host": "主机端", "user": "用户端", "mixed": "混合模式"}
        self.device_type_label = QLabel(type_map.get(config.device_type, config.device_type))
        status_layout.addRow("设备类型:", self.device_type_label)

        self.conn_status_label = QLabel("● 未连接")
        self.conn_status_label.setStyleSheet("color: #ff4d4f; font-weight: bold;")
        status_layout.addRow("状态:", self.conn_status_label)

        self.spool_status_label = QLabel("-")
        status_layout.addRow("打印监视:", self.spool_status_label)

        layout.addWidget(status_group)

        # ==================== 中间标签页 ====================
        tabs = QTabWidget()

        # 打印机列表页
        printer_tab = QWidget()
        printer_layout = QVBoxLayout(printer_tab)

        self.printer_list = QListWidget()
        self.printer_list.setAlternatingRowColors(True)
        printer_layout.addWidget(self.printer_list)

        refresh_btn = QPushButton("刷新列表")
        refresh_btn.clicked.connect(self._refresh_printers)
        printer_layout.addWidget(refresh_btn)

        tabs.addTab(printer_tab, "打印机列表")

        # 任务状态页
        job_tab = QWidget()
        job_layout = QVBoxLayout(job_tab)

        self.job_table = QTableWidget(0, 5)
        self.job_table.setHorizontalHeaderLabels(["任务ID", "类型", "状态", "时间", "详情"])
        self.job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.job_table.setAlternatingRowColors(True)
        job_layout.addWidget(self.job_table)

        tabs.addTab(job_tab, "任务状态")

        layout.addWidget(tabs)

        # ==================== 底部按钮 ====================
        btn_layout = QHBoxLayout()

        self.connect_btn = QPushButton("连接服务端")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        btn_layout.addWidget(self.connect_btn)

        self.settings_btn = QPushButton("重新设置")
        self.settings_btn.clicked.connect(self._on_settings_clicked)
        btn_layout.addWidget(self.settings_btn)

        layout.addLayout(btn_layout)

        # 状态栏
        self.statusBar().showMessage("就绪")

    # ==================== 按钮事件 ====================

    def _on_connect_clicked(self):
        if self.client.connected:
            run_async(self.client.disconnect())
        else:
            run_async(self.client.auto_connect())

    def _on_settings_clicked(self):
        reply = QMessageBox.question(
            self, "重新设置",
            "重新设置将断开当前连接并重新启动配置向导。\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.settings_requested.emit()

    def _refresh_printers(self):
        if self.client.authenticated:
            run_async(self.client.get_printer_list())
        else:
            QMessageBox.warning(self, "提示", "请先连接服务端")

    # ==================== 客户端回调 ====================

    def _on_status_changed(self, status: str, detail: str = ""):
        """客户端状态变更"""
        status_map = {
            "connecting": ("● 连接中...", "#faad14"),
            "connected": ("● 已连接", "#52c41a"),
            "authenticated": ("● 已认证", "#52c41a"),
            "disconnected": ("● 已断开", "#ff4d4f"),
            "error": ("● 连接错误", "#ff4d4f"),
            "auth_failed": ("● 认证失败", "#ff4d4f"),
        }
        text, color = status_map.get(status, ("● 未知", "#666"))
        self.conn_status_label.setText(text)
        self.conn_status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        if status == "connected":
            self.connect_btn.setText("断开连接")
            self.statusBar().showMessage(f"已连接到 {detail}")
        elif status in ("disconnected", "error"):
            self.connect_btn.setText("连接服务端")
            self.statusBar().showMessage("已断开")
            self.spool_status_label.setText("-")

        # 更新 Spool 监视状态
        if status == "authenticated" and self.client.spool_monitor:
            self.spool_status_label.setText("● 运行中")
            self.spool_status_label.setStyleSheet("color: #52c41a;")
        elif status in ("disconnected", "error"):
            self.spool_status_label.setText("● 已停止")
            self.spool_status_label.setStyleSheet("color: #ff4d4f;")

    def _on_printers_updated(self, printers: list):
        """打印机列表更新"""
        self.printer_list.clear()
        for p in printers:
            name = p.get("name", "未知")
            model = p.get("model", "")
            status = p.get("status", "")
            status_map = {"online": "在线", "offline": "离线", "busy": "忙碌", "error": "错误"}
            status_text = status_map.get(status, status)
            self.printer_list.addItem(f"{name}  ({model}) - {status_text}")

    def _on_job_status(self, job_id: str, status: str, job_type: str = "", detail: str = ""):
        """打印任务状态更新
        
        job_type: "发送" (用户端创建) / "接收" (主机端接收)
        """
        status_map = {
            "created": "已创建", "transferring": "传输中", "queued": "排队中",
            "printing": "打印中", "completed": "已完成", "failed": "失败", "cancelled": "已取消"
        }
        status_text = status_map.get(status, status)

        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S")

        # 查找是否已存在该任务
        existing_row = -1
        for row in range(self.job_table.rowCount()):
            item = self.job_table.item(row, 0)
            if item and item.text() == job_id:
                existing_row = row
                break

        if existing_row >= 0:
            # 更新已有任务状态
            self.job_table.setItem(existing_row, 2, QTableWidgetItem(status_text))
            self.job_table.setItem(existing_row, 3, QTableWidgetItem(now))
            if detail:
                self.job_table.setItem(existing_row, 4, QTableWidgetItem(detail))
        else:
            # 添加新任务
            row = self.job_table.rowCount()
            self.job_table.insertRow(row)
            self.job_table.setItem(row, 0, QTableWidgetItem(job_id or "-"))
            self.job_table.setItem(row, 1, QTableWidgetItem(job_type))
            self.job_table.setItem(row, 2, QTableWidgetItem(status_text))
            self.job_table.setItem(row, 3, QTableWidgetItem(now))
            self.job_table.setItem(row, 4, QTableWidgetItem(detail))

        self.statusBar().showMessage(f"任务 {job_id}: {status_text}", 5000)

    # ==================== 窗口事件 ====================

    def closeEvent(self, event):
        """关闭事件 - 最小化到托盘"""
        if not self._tray_mode:
            # 第一次关闭时提示
            self._tray_mode = True
            event.ignore()
            self.hide()
            # 发送托盘通知
            if hasattr(self, '_tray_notify'):
                self._tray_notify()
        else:
            event.ignore()
            self.hide()

    def show_from_tray(self):
        """从托盘恢复显示"""
        self.show()
        self.raise_()
        self.activateWindow()

    def set_tray_notify_callback(self, callback):
        """设置托盘通知回调"""
        self._tray_notify = callback
