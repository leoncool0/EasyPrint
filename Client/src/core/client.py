"""
Client Core - 客户端核心逻辑
"""
import asyncio
import logging
import sys
import uuid
import platform
import subprocess
import json
import os
from pathlib import Path
from typing import Optional, Callable, Dict, List
from datetime import datetime

from src.core.config_manager import config
from src.network.connection import NetworkConnection
from src.printer.scanner import PrinterScanner
from src.printer.virtual_printer import VirtualPrinterManager
from src.printer.spool_monitor import SpoolMonitor

logger = logging.getLogger(__name__)

SPOOL_DIR = Path("spool")


def get_mac_address() -> str:
    """获取本机 MAC 地址"""
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
                            return mac
        elif platform.system() == "Linux":
            output = subprocess.check_output(
                ["cat", "/sys/class/net/eth0/address"], stderr=subprocess.STDOUT, text=True
            )
            return output.strip()
        elif platform.system() == "Darwin":
            output = subprocess.check_output(
                ["ifconfig", "en0"], stderr=subprocess.STDOUT, text=True
            )
            for line in output.split("\n"):
                if "ether" in line:
                    return line.split()[1]
    except Exception as e:
        logger.warning(f"获取 MAC 地址失败: {e}")

    return ""


def get_computer_name() -> str:
    """获取计算机名"""
    try:
        return platform.node() or "我的电脑"
    except Exception:
        return "我的电脑"


class Client:
    """EasyPrint 客户端主类"""

    def __init__(self):
        # 设备信息
        self.mac_address = get_mac_address()
        self.device_id = self._generate_device_id()
        self.device_type = config.device_type
        self.device_name = config.device_name or get_computer_name()
        self.token: Optional[str] = config.token

        # 网络连接
        self.connection: Optional[NetworkConnection] = None

        # 打印机扫描器（主机端模式）
        self.printer_scanner: Optional[PrinterScanner] = None

        # 状态
        self.connected = False
        self.authenticated = False

        # 心跳定时器
        self._heartbeat_timer = None

        # 打印任务队列
        self._pending_jobs: Dict[str, dict] = {}  # job_id -> job_info

        # Spool 监视器（用户端模式）
        self.spool_monitor: Optional[SpoolMonitor] = None
        self._spool_timer = None

        # 打印任务 job_id 等待器
        self._pending_job_id: Optional[str] = None
        self._job_id_event: Optional[asyncio.Event] = None

        # 主机端打印任务缓存
        self._host_jobs: Dict[str, dict] = {}  # job_id -> {printer_id, job_name, data_chunks, total}

        # 回调
        self._on_connected_callbacks: List[Callable] = []
        self._on_disconnected_callbacks: List[Callable] = []
        self._on_printers_updated_callbacks: List[Callable] = []
        self._on_status_changed_callbacks: List[Callable] = []
        self._on_job_status_callbacks: List[Callable] = []

    def _generate_device_id(self) -> str:
        """基于 MAC 地址生成设备 ID"""
        if self.mac_address:
            return f"device_{self.mac_address.replace(':', '')}"
        return f"device_{uuid.uuid4().hex[:16]}"

    # ==================== 状态通知 ====================

    def _notify_status(self, status: str, detail: str = ""):
        """通知状态变更"""
        for cb in self._on_status_changed_callbacks:
            try:
                cb(status, detail)
            except Exception as e:
                logger.error(f"状态回调错误: {e}")

    # ==================== 连接管理 ====================

    async def connect(self, host: str = None, port: int = None):
        """连接服务端"""
        host = host or config.server_host
        port = port or config.server_tcp_port

        logger.info(f"连接到 {host}:{port}")
        self._notify_status("connecting", f"{host}:{port}")

        self.connection = NetworkConnection(host, port)
        self.connection.on_connected = self._on_connected
        self.connection.on_disconnected = self._on_disconnected
        self.connection.on_message = self._on_message

        await self.connection.connect()

    async def disconnect(self):
        """断开连接"""
        self._stop_heartbeat()

        if self.connection:
            await self.connection.disconnect()
            self.connection = None

        self.connected = False
        self.authenticated = False

    def stop(self):
        """停止客户端"""
        self._stop_heartbeat()
        self._stop_spool_monitor()
        if self.connection:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.disconnect())
            except RuntimeError:
                # 事件循环已停止，跳过优雅断开
                pass

    async def auto_connect(self):
        """自动连接并认证"""
        try:
            await self.connect()
            await self.authenticate()

            # 注意：注册打印机和启动监视器在认证成功回调中执行
            # 因为 authenticate() 只是发送请求，不等待响应

            self._start_heartbeat()
            self._notify_status("connected", f"{config.server_host}:{config.server_tcp_port}")

        except Exception as e:
            logger.error(f"自动连接失败: {e}")
            self._notify_status("error", str(e))

    # ==================== 认证 ====================

    async def authenticate(self):
        """向服务端认证"""
        if not self.connection or not self.connection.connected:
            raise RuntimeError("未连接到服务端")

        await self.connection.send_auth(
            device_id=self.device_id,
            device_name=self.device_name,
            device_type=self.device_type,
            os_version=platform.platform(),
            mac_address=self.mac_address,
        )

    # ==================== 心跳 ====================

    def _start_heartbeat(self):
        """启动心跳定时器"""
        if self._heartbeat_timer:
            return

        async def heartbeat_loop():
            while self.connected:
                try:
                    await asyncio.sleep(30)
                    if self.connection and self.connected:
                        await self.connection.send_heartbeat()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"心跳发送失败: {e}")

        self._heartbeat_timer = asyncio.create_task(heartbeat_loop())

    def _stop_heartbeat(self):
        """停止心跳"""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    # ==================== 用户端：Spool 监视 ====================

    def _start_spool_monitor(self):
        """启动 Spool 监视器，监视已安装的虚拟打印机"""
        if self.spool_monitor:
            return

        virtual_printers = config.virtual_printers
        if not virtual_printers:
            logger.info("未配置虚拟打印机，跳过 Spool 监视")
            return

        # 取第一个虚拟打印机进行监视
        # （如果有多台，可以创建多个 SpoolMonitor）
        vp = virtual_printers[0]
        printer_name = f"EasyPrint - {vp.get('name', 'Unknown')}"

        self.spool_monitor = SpoolMonitor(printer_name)
        self.spool_monitor.on_print_data = self._on_spool_data
        self.spool_monitor.start()

        # 启动定时轮询
        async def poll_loop():
            while self.spool_monitor and self.spool_monitor._running:
                self.spool_monitor.check_jobs()
                await asyncio.sleep(2)

        self._spool_timer = asyncio.create_task(poll_loop())
        logger.info(f"Spool 监视器已启动: {printer_name}")

    def _stop_spool_monitor(self):
        """停止 Spool 监视器"""
        if self.spool_monitor:
            self.spool_monitor.stop()
            self.spool_monitor = None
        if self._spool_timer:
            self._spool_timer.cancel()
            self._spool_timer = None

    def _on_spool_data(self, data: bytes, doc_name: str):
        """处理从 Spool 截获的打印数据"""
        logger.info(f"截获打印数据: {doc_name} ({len(data)} bytes)")

        if not self.connection or not self.authenticated:
            logger.warning("未连接服务端，无法转发打印数据")
            return

        # 获取目标 printer_id
        virtual_printers = config.virtual_printers
        if not virtual_printers:
            logger.warning("没有配置虚拟打印机，无法转发打印数据")
            return
        target_printer_id = virtual_printers[0].get("printer_id", "")
        if not target_printer_id:
            logger.warning("虚拟打印机缺少 printer_id，无法转发打印数据")
            return

        logger.info(f"准备发送到服务端: printer_id={target_printer_id}")
        # 异步发送到服务端
        asyncio.create_task(self._send_spool_data(target_printer_id, data, doc_name))

    async def _send_spool_data(self, printer_id: str, data: bytes, doc_name: str):
        """将 spool 数据发送到服务端"""
        try:
            # 1. 创建打印任务
            await self.connection.send_job_create(printer_id, doc_name, {
                "job_name": doc_name,
                "file_size": len(data),
            })

            # 等待获取 job_id（通过回调异步获取）
            job_id = await self._wait_for_job_id(timeout=5.0)
            if not job_id:
                logger.error("获取 job_id 超时")
                return

            # 2. 分块发送数据
            chunk_size = 64 * 1024
            total = (len(data) + chunk_size - 1) // chunk_size
            for seq in range(total):
                chunk = data[seq * chunk_size : (seq + 1) * chunk_size]
                await self.connection.send_job_data(job_id, chunk, seq, total)
                await asyncio.sleep(0.01)  # 避免发送过快

            logger.info(f"打印数据已发送: {doc_name} ({len(data)} bytes)")

            # 通知UI更新状态为传输中
            for cb in self._on_job_status_callbacks:
                try:
                    cb(job_id, "transferring", "发送")
                except Exception as e:
                    logger.error(f"回调错误: {e}")

        except Exception as e:
            logger.error(f"发送打印数据失败: {e}")

    # ==================== 主机端：打印机注册 ====================

    async def register_printers(self):
        """注册本机要共享的打印机"""
        if self.device_type not in ("host", "mixed"):
            return

        if not self.connection or not self.authenticated:
            return

        shared = config.shared_printers
        if not shared:
            # 如果没有配置，扫描所有打印机
            if not self.printer_scanner:
                self.printer_scanner = PrinterScanner()
            all_printers = self.printer_scanner.scan()
            shared = [{"name": p["name"], "model": p.get("model", "")} for p in all_printers]

        if shared:
            await self.connection.send_host_register(shared)
            logger.info(f"已注册 {len(shared)} 台共享打印机")

    # ==================== 用户端：获取打印机列表 ====================

    async def get_printer_list(self):
        """获取服务端可用打印机列表"""
        if not self.connection or not self.authenticated:
            raise RuntimeError("未认证")

        await self.connection.send_user_list_request()

    # ==================== 用户端：打印任务 ====================

    async def create_print_job(self, printer_id: str, file_path: str, params: dict = None):
        """创建打印任务"""
        if not self.connection or not self.authenticated:
            raise RuntimeError("未认证")

        await self.connection.send_job_create(printer_id, file_path, params or {})

    async def send_print_data(self, job_id: str, file_path: str):
        """发送打印数据（分块）"""
        if not self.connection:
            return

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"打印文件不存在: {file_path}")
            return

        file_size = file_path.stat().st_size
        chunk_size = 64 * 1024  # 64KB

        with open(file_path, "rb") as f:
            seq = 0
            total = (file_size + chunk_size - 1) // chunk_size

            while True:
                data = f.read(chunk_size)
                if not data:
                    break

                await self.connection.send_job_data(job_id, data, seq, total)
                seq += 1

        logger.info(f"打印数据已发送: {file_path.name} ({file_size} bytes, {seq} 块)")

    # ==================== 回调注册 ====================

    def on_connected(self, callback: Callable):
        self._on_connected_callbacks.append(callback)

    def on_disconnected(self, callback: Callable):
        self._on_disconnected_callbacks.append(callback)

    def on_printers_updated(self, callback: Callable):
        self._on_printers_updated_callbacks.append(callback)

    def on_status_changed(self, callback: Callable):
        """注册状态变更回调 callback(status, detail)"""
        self._on_status_changed_callbacks.append(callback)

    def on_job_status(self, callback: Callable):
        """注册打印任务状态回调"""
        self._on_job_status_callbacks.append(callback)

    # ==================== 内部回调 ====================

    def _on_connected(self):
        """TCP 连接建立"""
        self.connected = True
        for cb in self._on_connected_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"回调错误: {e}")

    def _on_disconnected(self):
        """TCP 连接断开"""
        self.connected = False
        self.authenticated = False
        self._stop_heartbeat()
        self._notify_status("disconnected")
        for cb in self._on_disconnected_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"回调错误: {e}")

    def _on_message(self, msg_type: int, data: dict):
        """处理收到的消息"""
        if msg_type == 0x0003:  # AUTH_RSP
            self._handle_auth_response(data)
        elif msg_type == 0x0010:  # HOST_REGISTER_RSP
            logger.info(f"打印机注册响应: {data}")
        elif msg_type == 0x0021:  # USER_LIST_RSP
            self._handle_printer_list(data)
        elif msg_type == 0x0030:  # JOB_CREATE (主机端接收)
            self._handle_host_job_create(data)
        elif msg_type == 0x0031:  # JOB_CREATE_RSP
            self._handle_job_created(data)
        elif msg_type == 0x0032:  # JOB_DATA (主机端接收)
            self._handle_host_job_data(data)
        elif msg_type == 0x0033:  # JOB_CANCEL
            self._handle_host_job_cancel(data)
        elif msg_type == 0x0034:  # JOB_STATUS
            self._handle_job_status(data)

    def _handle_auth_response(self, data: dict):
        """处理认证响应"""
        if data.get("success"):
            self.token = data.get("token")
            self.authenticated = True
            # 保存 token 到配置
            config.set("token", self.token)
            config.save()
            logger.info(f"认证成功, token: {self.token[:8]}...")
            self._notify_status("authenticated")

            # 认证成功后，根据设备类型执行后续操作
            if self.device_type in ("host", "mixed"):
                asyncio.create_task(self.register_printers())

            if self.device_type in ("user", "mixed"):
                self._start_spool_monitor()
        else:
            logger.error("认证失败")
            self._notify_status("auth_failed")

    def _handle_printer_list(self, data: dict):
        """处理打印机列表"""
        printers = data.get("printers", [])
        for cb in self._on_printers_updated_callbacks:
            try:
                cb(printers)
            except Exception as e:
                logger.error(f"回调错误: {e}")

    def _handle_job_created(self, data: dict):
        """处理打印任务创建响应"""
        job_id = data.get("job_id")
        success = data.get("success", False)
        if success:
            logger.info(f"打印任务已创建: {job_id}")
            # 设置等待中的 job_id
            if self._job_id_event:
                self._pending_job_id = job_id
                self._job_id_event.set()
        else:
            logger.error(f"打印任务创建失败: {data.get('error', '未知错误')}")
            # 设置为 None 表示失败
            if self._job_id_event:
                self._pending_job_id = None
                self._job_id_event.set()

        # 通知UI（用户端创建的任务标记为"发送"）
        for cb in self._on_job_status_callbacks:
            try:
                cb(job_id, "created" if success else "failed", "发送")
            except Exception as e:
                logger.error(f"回调错误: {e}")

    async def _wait_for_job_id(self, timeout: float = 5.0) -> Optional[str]:
        """等待服务端返回 job_id"""
        self._pending_job_id = None
        self._job_id_event = asyncio.Event()

        try:
            await asyncio.wait_for(self._job_id_event.wait(), timeout=timeout)
            return self._pending_job_id
        except asyncio.TimeoutError:
            return None
        finally:
            self._job_id_event = None

    def _handle_job_status(self, data: dict):
        """处理打印任务状态更新"""
        job_id = data.get("job_id")
        status = data.get("status")
        message = data.get("message", "")
        logger.info(f"任务 {job_id} 状态: {status}")

        # 判断是发送还是接收的任务
        job_type = "接收" if job_id in self._host_jobs else "发送"

        for cb in self._on_job_status_callbacks:
            try:
                cb(job_id, status, job_type, message)
            except Exception as e:
                logger.error(f"回调错误: {e}")

    # ==================== 主机端：接收打印任务 ====================

    def _handle_host_job_create(self, data: dict):
        """主机端处理新打印任务"""
        job_id = data.get("job_id", "")
        printer_id = data.get("printer_id", "")
        job_name = data.get("job_name", "Print Job")

        if not job_id or not printer_id:
            return

        logger.info(f"[主机端] 收到新打印任务: {job_id} -> {printer_id}")

        # 提取本地打印机名称
        local_printer_name = printer_id.replace(self.device_id + "_", "")
        if local_printer_name == printer_id:
            # 无法解析，使用原始名称
            local_printer_name = printer_id

        self._host_jobs[job_id] = {
            "printer_id": printer_id,
            "local_printer": local_printer_name,
            "job_name": job_name,
            "data_chunks": [],
            "total": None,
        }

        # 通知UI（主机端接收的任务标记为"接收"）
        for cb in self._on_job_status_callbacks:
            try:
                cb(job_id, "created", "接收", f"目标打印机: {local_printer_name}")
            except Exception as e:
                logger.error(f"回调错误: {e}")

    def _handle_host_job_data(self, data: dict):
        """主机端接收打印数据块"""
        job_id = data.get("job_id", "")
        chunk_data = data.get("data", "")
        seq = data.get("seq", 0)
        total = data.get("total", 1)

        if job_id not in self._host_jobs:
            return

        job_info = self._host_jobs[job_id]
        job_info["data_chunks"].append((seq, chunk_data))
        job_info["total"] = total

        # 如果是最后一块，开始打印
        if seq == total - 1:
            asyncio.create_task(self._process_host_print_job(job_id))

    def _handle_host_job_cancel(self, data: dict):
        """主机端处理任务取消"""
        job_id = data.get("job_id", "")
        if job_id in self._host_jobs:
            del self._host_jobs[job_id]
            logger.info(f"[主机端] 打印任务已取消: {job_id}")

    async def _process_host_print_job(self, job_id: str):
        """处理主机端打印任务"""
        if job_id not in self._host_jobs:
            return

        job_info = self._host_jobs[job_id]
        local_printer = job_info["local_printer"]
        job_name = job_info["job_name"]

        try:
            # 按顺序拼接数据块
            chunks = sorted(job_info["data_chunks"], key=lambda x: x[0])
            data_parts = [c[1] for c in chunks]
            
            # data 是 base64 编码的字符串，需要解码
            import base64
            raw_data = b""
            for part in data_parts:
                if isinstance(part, str):
                    raw_data += base64.b64decode(part)
                else:
                    raw_data += part

            if not raw_data:
                logger.error(f"[主机端] 打印数据为空: {job_id}")
                del self._host_jobs[job_id]
                return

            logger.info(f"[主机端] 准备打印: {job_name} ({len(raw_data)} bytes) -> {local_printer}")

            # 通知服务端：开始打印
            if self.connection and self.connection.connected:
                await self.connection.send_job_status(job_id, "printing")

            # 发送到本地打印机
            success = await self.print_to_local_printer(local_printer, raw_data)

            if success:
                logger.info(f"[主机端] 打印成功: {job_name}")
                # 通知服务端：打印完成
                if self.connection and self.connection.connected:
                    await self.connection.send_job_status(job_id, "completed")
            else:
                logger.error(f"[主机端] 打印失败: {job_name}")
                # 通知服务端：打印失败
                if self.connection and self.connection.connected:
                    await self.connection.send_job_status(job_id, "failed", "本地打印失败")

        except Exception as e:
            logger.error(f"[主机端] 处理打印任务失败: {e}")
            # 通知服务端：打印失败
            if self.connection and self.connection.connected:
                await self.connection.send_job_status(job_id, "failed", str(e))

        finally:
            # 清理缓存
            if job_id in self._host_jobs:
                del self._host_jobs[job_id]

    async def print_to_local_printer(self, printer_name: str, data: bytes):
        """将打印数据发送到本地打印机（主机端接收远程打印任务）

        支持的格式:
        - XPS: 用 PIL 解析 ZIP 提取图像，用 GDI 打印
        - EMF: 用 win32api ShellExecute 打印
        - RAW: 直接发送到打印机
        """
        import os
        import subprocess

        # 1. 检查数据格式
        if len(data) >= 4:
            if data[:2] == b"PK":
                data_format = "XPS"
            elif data[:4] == b"\x01\x00\x00\x00":
                data_format = "EMF"
            elif data[:2] == b"%!":
                data_format = "POSTSCRIPT"
            else:
                data_format = "RAW"
        else:
            data_format = "RAW"
        logger.info(f"打印数据格式: {data_format} ({len(data)} bytes)")

        # 2. 验证打印机是否存在
        try:
            import win32print
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            printer_names = []
            for p in printers:
                name = p.get("pPrinterName", "") if isinstance(p, dict) else (p[2] if isinstance(p, tuple) and len(p) > 2 else "")
                printer_names.append(name)
            if printer_name not in printer_names:
                logger.error(f"打印机不存在: {printer_name}, 可用: {printer_names}")
                return False
            logger.info(f"打印机验证通过: {printer_name}")
        except Exception as e:
            logger.warning(f"打印机验证失败: {e}")

        # 3. 根据格式选择打印方式
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        temp_dir = os.path.join(app_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # 3.1 EMF 格式：直接用 ShellExecute 打印
        if data_format == "EMF":
            temp_path = None
            try:
                temp_name = f"easyprint_{uuid.uuid4().hex[:8]}.emf"
                temp_path = os.path.join(temp_dir, temp_name)
                with open(temp_path, "wb") as f:
                    f.write(data)
                logger.info(f"EMF 文件已保存: {temp_path}")

                import win32api
                import win32con
                result = win32api.ShellExecute(
                    0, "printto", temp_path,
                    f'"{printer_name}"', ".", win32con.SW_HIDE
                )
                if result > 32:
                    logger.info(f"EMF 打印成功: {printer_name}")
                    return True
                else:
                    logger.warning(f"EMF 打印失败: result={result}")
            except Exception as e:
                logger.warning(f"EMF 打印异常: {e}")
            finally:
                if temp_path and os.path.exists(temp_path):
                    asyncio.create_task(self._delayed_remove(temp_path))

        # 3.2 XPS 格式：用 Python 解析并用 GDI 打印
        if data_format == "XPS":
            try:
                return await self._print_xps_with_pil(printer_name, data, temp_dir)
            except Exception as e:
                logger.error(f"XPS 打印失败: {e}")
                return False

        # 4. 不支持 RAW 直接发送（会导致乱码）
        logger.error(f"不支持的数据格式: {data_format}，无法打印到 {printer_name}")
        return False

    async def _print_xps_with_pil(self, printer_name: str, data: bytes, temp_dir: str) -> bool:
        """使用 PyMuPDF (fitz) 将 XPS 渲染为图像并通过 GDI 打印"""
        import fitz
        import win32print
        import win32ui
        import win32con
        from PIL import Image, ImageWin

        logger.info(f"准备 XPS->图像->打印: printer={printer_name}, data_size={len(data)}")

        os.makedirs(temp_dir, exist_ok=True)

        temp_name = f"easyprint_{uuid.uuid4().hex[:8]}.xps"
        temp_path = os.path.join(temp_dir, temp_name)
        with open(temp_path, "wb") as f:
            f.write(data)
        logger.info(f"XPS 文件已保存: {temp_path}, size={os.path.getsize(temp_path)}")

        try:
            doc = fitz.open(temp_path)
            page_count = doc.page_count
            logger.info(f"XPS 打开成功: {page_count} 页")

            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)

            try:
                for page_num in range(page_count):
                    page = doc.load_page(page_num)

                    # 获取打印机分辨率并计算合适的渲染 DPI
                    printer_dc = hdc.GetSafeHdc()
                    horz_res = win32print.GetDeviceCaps(printer_dc, win32con.HORZRES)
                    vert_res = win32print.GetDeviceCaps(printer_dc, win32con.VERTRES)
                    horz_dpi = win32print.GetDeviceCaps(printer_dc, win32con.LOGPIXELSX)
                    vert_dpi = win32print.GetDeviceCaps(printer_dc, win32con.LOGPIXELSY)

                    # 按打印机物理尺寸计算渲染尺寸（像素）
                    page_rect = page.rect
                    page_w = page_rect.width
                    page_h = page_rect.height

                    # 计算合适的矩阵使页面适应纸张
                    scale_x = horz_res / page_w
                    scale_y = vert_res / page_h
                    scale = min(scale_x, scale_y)

                    mat = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=mat, alpha=False)

                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    logger.info(f"页面 {page_num+1}/{page_count} 渲染: {img.size[0]}x{img.size[1]}")

                    hdc.StartDoc(f"EasyPrint Job")
                    hdc.StartPage()

                    dib = ImageWin.Dib(img)
                    dib.draw(hdc.GetSafeHdc(), (0, 0, img.size[0], img.size[1]))

                    hdc.EndPage()
                    hdc.EndDoc()
                    logger.info(f"页面 {page_num+1}/{page_count} 已打印")

                doc.close()
                logger.info(f"XPS 打印成功: {printer_name}")
                asyncio.create_task(self._delayed_remove(temp_path))
                return True
            finally:
                del hdc

        except Exception as e:
            logger.error(f"XPS 打印失败: {e}", exc_info=True)
            if temp_path and os.path.exists(temp_path):
                logger.info(f"保留 XPS 文件用于调试: {temp_path}")
            return False

    async def _delayed_remove(self, path: str):
        """延迟删除临时文件"""
        await asyncio.sleep(60)
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass
