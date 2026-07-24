"""
Setup Wizard - 首次运行配置向导
"""
import logging
import socket
import platform
import json
import uuid
import subprocess
import urllib.request
from pathlib import Path
from typing import List

from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QListWidget, QListWidgetItem,
    QRadioButton, QPushButton, QGroupBox, QMessageBox,
    QProgressBar
)
from PySide6.QtCore import Qt

from src.core.config_manager import config
from src.printer.scanner import PrinterScanner
from src.printer.virtual_printer import VirtualPrinterManager
from src.utils.autostart import enable_autostart, disable_autostart

logger = logging.getLogger(__name__)


# ==================== 工具函数 ====================

def test_server_connection(host: str, tcp_port: int, timeout: int = 3) -> bool:
    """测试 TCP 连接"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, tcp_port))
        s.close()
        return True
    except Exception:
        return False


def fetch_server_printers(host: str, http_port: int) -> List[dict]:
    """从服务端 HTTP API 获取可用打印机列表"""
    url = f"http://{host}:{http_port}/api/printers/?online_only=true"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            printers = data.get("printers", [])
            # 只返回共享且在线的
            return [p for p in printers if p.get("is_shared", True) and p.get("status") == "online"]
    except Exception as e:
        logger.error(f"获取打印机列表失败: {e}")
        return []


def get_computer_name() -> str:
    """获取计算机名"""
    try:
        return platform.node() or "我的电脑"
    except Exception:
        return "我的电脑"


def get_device_id() -> str:
    """生成设备 ID（与客户端一致的逻辑）"""
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output(
                ["ipconfig", "/all"], stderr=subprocess.STDOUT, text=True
            )
            for line in output.split("\n"):
                if "物理地址" in line or "Physical Address" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        mac = parts[1].strip().replace("-", ":")
                        if len(mac) == 17:
                            return f"device_{mac.replace(':', '')}"
        elif platform.system() == "Linux":
            output = subprocess.check_output(
                ["cat", "/sys/class/net/eth0/address"], stderr=subprocess.STDOUT, text=True
            )
            mac = output.strip()
            return f"device_{mac.replace(':', '')}"
        elif platform.system() == "Darwin":
            output = subprocess.check_output(
                ["ifconfig", "en0"], stderr=subprocess.STDOUT, text=True
            )
            for line in output.split("\n"):
                if "ether" in line:
                    mac = line.split()[1]
                    return f"device_{mac.replace(':', '')}"
    except Exception as e:
        logger.warning(f"生成设备 ID 失败: {e}")
    return f"device_{uuid.uuid4().hex[:12]}"


def check_device_registered(host: str, http_port: int, device_id: str) -> dict:
    """检查服务端是否已注册该设备，返回设备信息或空字典"""
    url = f"http://{host}:{http_port}/api/devices/{device_id}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data
            elif resp.status == 404:
                return {}
    except Exception as e:
        logger.error(f"检查设备注册状态失败: {e}")
    return {}


# ==================== 向导页面 ====================

class WelcomePage(QWizardPage):
    """第1页: 欢迎页"""

    def __init__(self):
        super().__init__()
        self.setTitle("欢迎使用 EasyPrint")
        self.setSubTitle("跨系统打印机共享软件")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("本向导将引导您完成 EasyPrint 客户端的初始配置。"))
        layout.addSpacing(10)
        layout.addWidget(QLabel("配置步骤："))
        layout.addWidget(QLabel("  1. 设置服务端连接"))
        layout.addWidget(QLabel("  2. 输入设备名称并选择设备类型"))
        layout.addWidget(QLabel("  3. 配置打印机"))
        layout.addWidget(QLabel("  4. 设置开机启动"))
        layout.addSpacing(20)
        layout.addWidget(QLabel("点击「下一步」开始配置。"))
        layout.addStretch()
        self.setLayout(layout)


class ServerPage(QWizardPage):
    """第2页: 服务端连接"""

    def __init__(self):
        super().__init__()
        self.setTitle("服务端连接")
        self.setSubTitle("输入 EasyPrint 服务端的 IP 地址和端口")

        layout = QVBoxLayout()

        form = QFormLayout()
        self.host_edit = QLineEdit(config.server_host or "10.1.2.110")
        self.host_edit.setPlaceholderText("如: 10.1.2.110")
        form.addRow("服务端 IP:", self.host_edit)

        self.tcp_port_edit = QLineEdit(str(config.server_tcp_port or 9100))
        self.tcp_port_edit.setMaximumWidth(80)
        form.addRow("TCP 端口:", self.tcp_port_edit)

        self.http_port_edit = QLineEdit(str(config.server_http_port or 8080))
        self.http_port_edit.setMaximumWidth(80)
        form.addRow("HTTP 端口:", self.http_port_edit)

        layout.addLayout(form)
        layout.addSpacing(10)

        # 测试连接按钮
        btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.test_btn)
        self.test_result = QLabel("")
        btn_layout.addWidget(self.test_result)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.setLayout(layout)

        # 注册字段
        self.registerField("server_host", self.host_edit)
        self.registerField("tcp_port", self.tcp_port_edit)
        self.registerField("http_port", self.http_port_edit)

        self._connection_ok = False

    def _test_connection(self):
        host = self.host_edit.text().strip()
        if not host:
            self.test_result.setText("请输入 IP 地址")
            self.test_result.setStyleSheet("color: red;")
            return

        try:
            tcp_port = int(self.tcp_port_edit.text().strip())
        except ValueError:
            self.test_result.setText("端口必须是数字")
            self.test_result.setStyleSheet("color: red;")
            return

        self.test_btn.setEnabled(False)
        self.test_result.setText("连接中...")
        self.test_result.setStyleSheet("color: #666;")

        if test_server_connection(host, tcp_port):
            self.test_result.setText("连接成功")
            self.test_result.setStyleSheet("color: green;")
            self._connection_ok = True
        else:
            self.test_result.setText("连接失败，请检查 IP 和端口")
            self.test_result.setStyleSheet("color: red;")
            self._connection_ok = False

        self.test_btn.setEnabled(True)
        self.completeChanged.emit()
        # 手动更新下一步按钮状态
        wizard = self.wizard()
        if wizard:
            wizard.button(QWizard.NextButton).setEnabled(self._connection_ok and self.isComplete())

    def isComplete(self) -> bool:
        """只有连接成功才允许下一步"""
        if not super().isComplete():
            return False
        return self._connection_ok

    def validatePage(self) -> bool:
        if not self._connection_ok:
            QMessageBox.warning(self, "提示", "请先测试连接并确保连接成功")
            return False

        host = self.host_edit.text().strip()
        http_port = int(self.http_port_edit.text().strip())
        device_id = get_device_id()

        self.test_result.setText("检查设备注册状态...")
        self.test_result.setStyleSheet("color: #666;")

        registered_device = check_device_registered(host, http_port, device_id)
        if registered_device:
            reply = QMessageBox.question(
                self, "设备已注册",
                f"检测到本机已在服务端注册：\n\n"
                f"设备名称: {registered_device.get('device_name', '未知')}\n"
                f"设备类型: {registered_device.get('device_type', '未知')}\n"
                f"是否直接使用服务端配置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                wizard = self.wizard()
                if wizard:
                    wizard._registered_config = registered_device
                    wizard._skip_to_complete = True
                return True

        return True

    def nextId(self) -> int:
        wizard = self.wizard()
        if getattr(wizard, "_skip_to_complete", False):
            return WizardPageId.COMPLETE
        return WizardPageId.DEVICE


class DevicePage(QWizardPage):
    """第3页: 设备名称和类型"""

    def __init__(self):
        super().__init__()
        self.setTitle("设备信息")
        self.setSubTitle("设置设备名称并选择设备类型")

        layout = QVBoxLayout()

        form = QFormLayout()
        self.name_edit = QLineEdit(config.device_name or get_computer_name())
        self.name_edit.setPlaceholderText("如: 前台电脑")
        form.addRow("设备名称:", self.name_edit)
        layout.addLayout(form)
        layout.addSpacing(15)

        # 设备类型
        type_group = QGroupBox("设备类型")
        type_layout = QVBoxLayout(type_group)

        self.radio_host = QRadioButton("主机端 - 共享本机打印机供其他用户使用")
        self.radio_user = QRadioButton("用户端 - 使用其他主机共享的打印机")
        self.radio_mixed = QRadioButton("混合模式 - 同时作为主机端和用户端")

        # 默认选择
        current_type = config.device_type or "user"
        if current_type == "host":
            self.radio_host.setChecked(True)
        elif current_type == "mixed":
            self.radio_mixed.setChecked(True)
        else:
            self.radio_user.setChecked(True)

        type_layout.addWidget(self.radio_host)
        type_layout.addWidget(self.radio_user)
        type_layout.addWidget(self.radio_mixed)
        layout.addWidget(type_group)

        layout.addSpacing(10)
        type_help = QLabel("提示：\n"
                           "• 主机端：本机有物理打印机，想让其他人通过网络使用\n"
                           "• 用户端：本机没有打印机，想使用其他人共享的打印机\n"
                           "• 混合模式：两者都需要")
        type_help.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(type_help)
        layout.addStretch()
        self.setLayout(layout)

        # 不使用 registerField 的必填验证，改用 isComplete() 手动控制
        # 监听名称变化，实时更新下一步按钮状态
        self.name_edit.textChanged.connect(lambda: self.completeChanged.emit())

        # 初始化完成后立即触发一次验证，确保下一步按钮状态正确
        self.completeChanged.emit()

    def initializePage(self):
        """页面显示时触发验证"""
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        """设备名称必填，类型默认已选中"""
        # 设备名称不能为空
        if not self.name_edit.text().strip():
            return False
        # 三种类型总有一个被选中（默认是用户端）
        return True

    def get_device_type(self) -> str:
        if self.radio_host.isChecked():
            return "host"
        elif self.radio_mixed.isChecked():
            return "mixed"
        else:
            return "user"

    def nextId(self) -> int:
        """根据类型决定下一页"""
        wizard = self.wizard()
        if getattr(wizard, "_skip_to_complete", False):
            return WizardPageId.COMPLETE
        dev_type = self.get_device_type()
        if dev_type == "user":
            return WizardPageId.USER_PRINTERS  # 直接到用户端打印机页
        else:
            return WizardPageId.HOST_PRINTERS  # 先到主机端打印机页


class HostPrinterPage(QWizardPage):
    """第4页: 主机端 - 选择要共享的本机打印机"""

    def __init__(self):
        super().__init__()
        self.setTitle("共享本机打印机")
        self.setSubTitle("选择要共享的打印机（可多选）")

        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("扫描本机打印机")
        self.scan_btn.clicked.connect(self._scan_printers)
        btn_layout.addWidget(self.scan_btn)
        self.scan_status = QLabel("")
        btn_layout.addWidget(self.scan_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.printer_list = QListWidget()
        self.printer_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.printer_list)

        layout.addWidget(QLabel("选中要共享的打印机，点击下一步。"))
        self.setLayout(layout)

        # 自动扫描
        self._scanned = False

    def initializePage(self):
        """页面显示时自动扫描"""
        if not self._scanned:
            self._scan_printers()

    def _scan_printers(self):
        self.scan_btn.setEnabled(False)
        self.scan_status.setText("扫描中...")
        self.printer_list.clear()

        scanner = PrinterScanner()
        printers = scanner.scan()

        if not printers:
            self.scan_status.setText("未找到打印机")
            self.scan_btn.setEnabled(True)
            return

        for p in printers:
            status_text = " [默认]" if p.get("is_default") else ""
            item_text = f"{p['name']}  ({p.get('model', '未知')}){status_text}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, p)
            self.printer_list.addItem(item)
            # 默认打印机默认选中
            if p.get("is_default"):
                item.setSelected(True)

        self.scan_status.setText(f"找到 {len(printers)} 台打印机")
        self.scan_btn.setEnabled(True)
        self._scanned = True

    def get_selected_printers(self) -> List[dict]:
        """获取选中的打印机"""
        result = []
        for item in self.printer_list.selectedItems():
            printer = item.data(Qt.UserRole)
            result.append(printer)
        return result

    def validatePage(self) -> bool:
        if not self.get_selected_printers():
            reply = QMessageBox.question(
                self, "确认", "您没有选择任何打印机，确定要跳过吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return False
        return True

    def nextId(self) -> int:
        """如果是混合模式，下一步到用户端打印机页；否则到自启页"""
        wizard = self.wizard()
        if getattr(wizard, "_skip_to_complete", False):
            return WizardPageId.COMPLETE
        device_page = wizard.page(WizardPageId.DEVICE)
        if device_page and device_page.get_device_type() == "mixed":
            return WizardPageId.USER_PRINTERS
        return WizardPageId.AUTOSTART


class UserPrinterPage(QWizardPage):
    """第5页: 用户端 - 从服务端选择可用打印机"""

    def __init__(self):
        super().__init__()
        self.setTitle("选择可用打印机")
        self.setSubTitle("从服务端选择要使用的共享打印机（可多选）")

        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.clicked.connect(self._fetch_printers)
        btn_layout.addWidget(self.refresh_btn)
        self.fetch_status = QLabel("")
        btn_layout.addWidget(self.fetch_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.printer_list = QListWidget()
        self.printer_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.printer_list)

        # 虚拟打印机安装进度
        self.install_progress = QProgressBar()
        self.install_progress.setVisible(False)
        layout.addWidget(self.install_progress)

        layout.addWidget(QLabel("选中要使用的打印机，点击下一步将自动安装虚拟打印机。"))
        self.setLayout(layout)

        self._fetched = False

    def initializePage(self):
        """页面显示时自动获取"""
        if not self._fetched:
            self._fetch_printers()

    def _fetch_printers(self):
        self.refresh_btn.setEnabled(False)
        self.fetch_status.setText("获取中...")
        self.printer_list.clear()

        host = self.wizard().page(WizardPageId.SERVER).host_edit.text().strip()
        try:
            http_port = int(self.wizard().page(WizardPageId.SERVER).http_port_edit.text().strip())
        except ValueError:
            http_port = 8080

        printers = fetch_server_printers(host, http_port)

        if not printers:
            self.fetch_status.setText("暂无可用打印机")
            self.refresh_btn.setEnabled(True)
            return

        for p in printers:
            host_device_name = p.get("host_device_name", "")
            if host_device_name:
                display_name = f"[{host_device_name}] {p.get('name', '未知')}"
            else:
                display_name = p.get("name", "未知")
            item_text = f"{display_name}  ({p.get('model', '未知')})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, p)
            self.printer_list.addItem(item)
            item.setSelected(True)  # 默认全选

        self.fetch_status.setText(f"找到 {len(printers)} 台共享打印机")
        self.refresh_btn.setEnabled(True)
        self._fetched = True

    def get_selected_printers(self) -> List[dict]:
        """获取选中的打印机"""
        result = []
        for item in self.printer_list.selectedItems():
            printer = item.data(Qt.UserRole)
            result.append(printer)
        return result

    def validatePage(self) -> bool:
        """点击下一步时安装虚拟打印机"""
        selected = self.get_selected_printers()
        if not selected:
            reply = QMessageBox.question(
                self, "确认", "您没有选择任何打印机，确定要跳过吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return False
            return True

        # 安装虚拟打印机
        self.install_progress.setVisible(True)
        self.install_progress.setMaximum(len(selected))
        self.install_progress.setValue(0)

        vpm = VirtualPrinterManager()
        installed = []
        errors = []
        for i, p in enumerate(selected):
            display_name = p.get("name", "Unknown")
            printer_id = p.get("printer_id", "")
            self.fetch_status.setText(f"正在安装: {display_name}...")
            ok, err = vpm.create_virtual_printer(display_name, printer_id)
            if ok:
                installed.append({"name": display_name, "printer_id": printer_id})
            else:
                errors.append(f"{display_name}: {err}")
            self.install_progress.setValue(i + 1)

        # 保存安装结果
        self.wizard().installed_virtual_printers = installed
        self.fetch_status.setText(f"已安装 {len(installed)}/{len(selected)} 台虚拟打印机")

        if errors:
            detail = "\n".join(errors)
            QMessageBox.warning(self, "部分失败", f"有 {len(errors)} 台虚拟打印机安装失败:\n\n{detail}")

        return True

    def nextId(self) -> int:
        wizard = self.wizard()
        if getattr(wizard, "_skip_to_complete", False):
            return WizardPageId.COMPLETE
        return WizardPageId.AUTOSTART


class AutostartPage(QWizardPage):
    """第6页: 开机启动设置"""

    def __init__(self):
        super().__init__()
        self.setTitle("开机启动")
        self.setSubTitle("设置 EasyPrint 是否随系统启动")

        layout = QVBoxLayout()
        self.autostart_check = QCheckBox("开机自动启动 EasyPrint 客户端")
        self.autostart_check.setChecked(config.auto_start)
        layout.addWidget(self.autostart_check)
        layout.addSpacing(10)
        layout.addWidget(QLabel("建议勾选此项，以确保客户端在开机后自动连接服务端。"))
        layout.addStretch()
        self.setLayout(layout)


class CompletePage(QWizardPage):
    """第7页: 完成"""

    def __init__(self):
        super().__init__()
        self.setTitle("配置完成")
        self.setSubTitle("EasyPrint 客户端已配置完成")

        layout = QVBoxLayout()
        self.summary = QLabel("配置摘要：\n")
        self.summary.setStyleSheet("font-size: 13px; line-height: 1.8;")
        layout.addWidget(self.summary)
        layout.addSpacing(20)
        layout.addWidget(QLabel("点击「完成」保存配置并启动客户端。"))
        layout.addStretch()
        self.setLayout(layout)

    def initializePage(self):
        """显示配置摘要"""
        wizard = self.wizard()
        registered_config = getattr(wizard, "_registered_config", None)

        if registered_config:
            host = wizard.page(WizardPageId.SERVER).host_edit.text().strip()
            dev_name = registered_config.get("device_name", "未知")
            dev_type = registered_config.get("device_type", "user")
            type_label = {"host": "主机端", "user": "用户端", "mixed": "混合模式"}.get(dev_type, dev_type)

            summary = f"配置摘要（从服务端恢复）：\n\n"
            summary += f"  服务端地址: {host}\n"
            summary += f"  设备名称: {dev_name}\n"
            summary += f"  设备类型: {type_label}\n"
            summary += f"  提示: 将使用服务端保存的配置\n"
        else:
            server_page = wizard.page(WizardPageId.SERVER)
            device_page = wizard.page(WizardPageId.DEVICE)

            host = server_page.host_edit.text().strip()
            dev_name = device_page.name_edit.text().strip()
            dev_type = device_page.get_device_type()
            type_label = {"host": "主机端", "user": "用户端", "mixed": "混合模式"}.get(dev_type, dev_type)

            summary = f"配置摘要：\n\n"
            summary += f"  服务端地址: {host}\n"
            summary += f"  设备名称: {dev_name}\n"
            summary += f"  设备类型: {type_label}\n"

            if dev_type in ("host", "mixed"):
                host_page = wizard.page(WizardPageId.HOST_PRINTERS)
                if host_page:
                    selected = host_page.get_selected_printers()
                    summary += f"  共享打印机: {len(selected)} 台\n"

            if dev_type in ("user", "mixed"):
                installed = getattr(wizard, "installed_virtual_printers", [])
                summary += f"  虚拟打印机: {len(installed)} 台\n"

            autostart_page = wizard.page(WizardPageId.AUTOSTART)
            autostart = autostart_page.autostart_check.isChecked()
            summary += f"  开机自启: {'是' if autostart else '否'}\n"

        self.summary.setText(summary)


# ==================== 向导页 ID ====================

class WizardPageId:
    WELCOME = 0
    SERVER = 1
    DEVICE = 2
    HOST_PRINTERS = 3
    USER_PRINTERS = 4
    AUTOSTART = 5
    COMPLETE = 6


# ==================== 主向导 ====================

class SetupWizard(QWizard):
    """首次运行配置向导"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EasyPrint 配置向导")
        self.setMinimumSize(620, 480)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.IndependentPages, False)

        self.installed_virtual_printers: List[dict] = []

        # 添加页面
        self.setPage(WizardPageId.WELCOME, WelcomePage())
        self.setPage(WizardPageId.SERVER, ServerPage())
        self.setPage(WizardPageId.DEVICE, DevicePage())
        self.setPage(WizardPageId.HOST_PRINTERS, HostPrinterPage())
        self.setPage(WizardPageId.USER_PRINTERS, UserPrinterPage())
        self.setPage(WizardPageId.AUTOSTART, AutostartPage())
        self.setPage(WizardPageId.COMPLETE, CompletePage())

        # 起始页
        self.setStartId(WizardPageId.WELCOME)

    def get_config(self) -> dict:
        """从向导收集配置"""
        server_page = self.page(WizardPageId.SERVER)
        registered_config = getattr(self, "_registered_config", None)

        if registered_config:
            dev_type = registered_config.get("device_type", "user")
            return {
                "server_host": server_page.host_edit.text().strip(),
                "server_tcp_port": int(server_page.tcp_port_edit.text().strip()),
                "server_http_port": int(server_page.http_port_edit.text().strip()),
                "device_name": registered_config.get("device_name", ""),
                "device_type": dev_type,
                "auto_start": config.auto_start,
                "shared_printers": registered_config.get("shared_printers", []),
                "virtual_printers": [],
                "configured": True,
            }

        device_page = self.page(WizardPageId.DEVICE)
        autostart_page = self.page(WizardPageId.AUTOSTART)

        dev_type = device_page.get_device_type()

        # 主机端共享的打印机
        shared_printers = []
        if dev_type in ("host", "mixed"):
            host_page = self.page(WizardPageId.HOST_PRINTERS)
            if host_page:
                shared_printers = [
                    {"name": p["name"], "model": p.get("model", "")}
                    for p in host_page.get_selected_printers()
                ]

        # 用户端虚拟打印机
        virtual_printers = getattr(self, "installed_virtual_printers", [])

        return {
            "server_host": server_page.host_edit.text().strip(),
            "server_tcp_port": int(server_page.tcp_port_edit.text().strip()),
            "server_http_port": int(server_page.http_port_edit.text().strip()),
            "device_name": device_page.name_edit.text().strip(),
            "device_type": dev_type,
            "auto_start": autostart_page.autostart_check.isChecked(),
            "shared_printers": shared_printers,
            "virtual_printers": virtual_printers,
            "configured": True,
        }
