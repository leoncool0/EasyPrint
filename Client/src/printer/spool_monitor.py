"""
Spool Monitor - Windows 打印队列监视器
通过监视打印队列和 spool 目录，截获虚拟打印机的输出数据
"""
import logging
import os
import time
import glob
from pathlib import Path
from typing import Callable, Optional, Set
from datetime import datetime

# 预导入 win32timezone，避免 EnumJobs 使用时因缺少该模块报错
try:
    import win32timezone
except ImportError:
    pass

logger = logging.getLogger(__name__)

SPOOL_DIR = Path(r"C:\Windows\System32\spool\PRINTERS")


def detect_spool_format(data: bytes) -> str:
    """检测 spool 文件格式"""
    if len(data) < 4:
        return "UNKNOWN"
    # XPS 是 ZIP 文件，以 PK 开头
    if data[:2] == b"PK":
        return "XPS"
    # EMF 格式: 以 EMF 头部开始
    if data[:4] == b"\x01\x00\x00\x00":
        return "EMF"
    # PostScript: 以 %! 开头
    if data[:2] == b"%!":
        return "POSTSCRIPT"
    # PCL: 以 ESC 开头
    if data[:1] == b"\x1b":
        return "PCL"
    return "RAW"


class SpoolMonitor:
    """监视指定打印机的打印队列，截获打印数据"""

    def __init__(self, printer_name: str):
        self.printer_name = printer_name
        self.on_print_data: Optional[Callable[[bytes, str], None]] = None
        self._running = False
        self._known_jobs: dict = {}  # job_id -> {file, processed}
        self._known_spl_files: Set[Path] = set()

    def _get_current_spl_files(self) -> Set[Path]:
        """获取当前 spool 目录中的所有 .SPL 文件"""
        if not SPOOL_DIR.exists():
            return set()
        return set(SPOOL_DIR.glob("*.SPL"))

    def _find_new_spl_file(self, old_files: Set[Path], timeout: float = 5.0) -> Optional[Path]:
        """等待并查找新创建的 spool 文件"""
        start = time.time()
        while time.time() - start < timeout:
            current = self._get_current_spl_files()
            new_files = current - old_files
            if new_files:
                # 返回最新的一个
                return max(new_files, key=lambda p: p.stat().st_ctime)
            time.sleep(0.3)
        return None

    def check_jobs(self):
        """检查打印队列和 spool 目录（应在定时器中调用）

        处理逻辑：
        1. 先扫描打印队列，记录所有任务
        2. 再扫描 spool 目录，读取新文件
        3. 把新 spool 文件和队列中最新的未处理任务关联
        4. 下一轮检查时，删除已关联（已处理）的任务
           （延迟一轮删除，确保数据有时间发送到服务端）
        """
        try:
            import win32print

            # 1. 扫描打印队列
            handle = win32print.OpenPrinter(self.printer_name)
            try:
                jobs = win32print.EnumJobs(handle, 0, -1, 1)
                current_job_ids = set()

                for job in jobs:
                    job_id = job["JobId"]
                    doc_name = job.get("pDocument", "Print Job")
                    current_job_ids.add(job_id)

                    if job_id not in self._known_jobs:
                        logger.info(f"[SpoolMonitor] 队列任务: {doc_name} (Job {job_id})")
                        self._known_jobs[job_id] = {
                            "doc_name": doc_name,
                            "matched": False,  # 是否已匹配到 spool 文件
                            "delete_ready": False,  # 是否可以删除（下一轮）
                        }

                # 清理已消失的任务记录
                self._known_jobs = {
                    k: v for k, v in self._known_jobs.items()
                    if k in current_job_ids
                }

                # 2. 删除已标记为 delete_ready 的任务
                for job_id, job_info in list(self._known_jobs.items()):
                    if job_info.get("delete_ready", False):
                        try:
                            win32print.SetJob(handle, job_id, 0, None,
                                              win32print.JOB_CONTROL_DELETE)
                            logger.info(f"[SpoolMonitor] 已删除已处理任务: Job {job_id}")
                            del self._known_jobs[job_id]
                        except Exception as e:
                            logger.debug(f"[SpoolMonitor] 删除任务失败 Job {job_id}: {e}")

            finally:
                win32print.ClosePrinter(handle)

            # 3. 扫描 spool 目录，处理新文件
            current_spl = self._get_current_spl_files()
            new_spl_files = current_spl - self._known_spl_files

            for spl_file in sorted(new_spl_files, key=lambda p: p.stat().st_ctime):
                logger.info(f"[SpoolMonitor] 发现新 spool 文件: {spl_file.name}")

                # 等待文件写入完成（稳定时间3秒，超时30秒）
                self._wait_for_file_complete(spl_file, stable_time=3.0, timeout=30.0)

                # 读取数据
                try:
                    if not spl_file.exists():
                        logger.warning(f"[SpoolMonitor] spool 文件已被删除: {spl_file.name}")
                        self._known_spl_files.add(spl_file)
                        continue

                    data = spl_file.read_bytes()
                    logger.info(f"[SpoolMonitor] 读取到 {len(data)} bytes from {spl_file.name}")
                    if data:
                        fmt = detect_spool_format(data)
                        logger.info(f"[SpoolMonitor] 数据格式: {fmt}")
                        doc_name = self._get_doc_name_for_spl(spl_file)
                        if self.on_print_data:
                            self.on_print_data(data, doc_name)

                        # 匹配队列中最新的未匹配任务
                        unmatched_jobs = [
                            (jid, jinfo) for jid, jinfo in self._known_jobs.items()
                            if not jinfo.get("matched", False)
                        ]
                        if unmatched_jobs:
                            latest_job_id = max(unmatched_jobs, key=lambda x: x[0])[0]
                            self._known_jobs[latest_job_id]["matched"] = True
                            self._known_jobs[latest_job_id]["delete_ready"] = True
                            logger.debug(f"[SpoolMonitor] 任务 Job {latest_job_id} 已匹配，下轮删除")
                    else:
                        logger.warning(f"[SpoolMonitor] spool 文件为空: {spl_file.name}")
                except Exception as e:
                    logger.error(f"[SpoolMonitor] 读取 spool 文件失败: {e}", exc_info=True)

                self._known_spl_files.add(spl_file)

            # 4. 清理已消失的 spool 文件记录
            self._known_spl_files &= current_spl

        except Exception as e:
            logger.error(f"[SpoolMonitor] 检查失败: {e}")

    def _get_doc_name_for_spl(self, spl_file: Path) -> str:
        """尝试从队列获取 spool 文件对应的文档名"""
        try:
            import win32print
            handle = win32print.OpenPrinter(self.printer_name)
            try:
                jobs = win32print.EnumJobs(handle, 0, -1, 1)
                # 返回最新任务的文档名
                if jobs:
                    return jobs[-1].get("pDocument", "Print Job")
            finally:
                win32print.ClosePrinter(handle)
        except Exception:
            pass
        return "Print Job"

    def _wait_for_file_complete(self, file_path: Path, stable_time: float = 1.0, timeout: float = 30.0):
        """等待文件写入完成（大小稳定）"""
        start = time.time()
        last_size = -1
        stable_start = None
        last_change = time.time()

        while time.time() - start < timeout:
            try:
                if not file_path.exists():
                    return

                size = file_path.stat().st_size
                if size != last_size:
                    last_size = size
                    stable_start = None
                    last_change = time.time()
                else:
                    if size > 0:
                        if stable_start is None:
                            stable_start = time.time()
                        elif time.time() - stable_start >= stable_time:
                            return
            except Exception:
                pass
            time.sleep(0.5)

    def cleanup_old_jobs(self):
        """清理已消失的已处理任务记录"""
        try:
            import win32print
            handle = win32print.OpenPrinter(self.printer_name)
            try:
                jobs = win32print.EnumJobs(handle, 0, -1, 1)
                current_ids = {j["JobId"] for j in jobs}
                self._known_jobs = {k: v for k, v in self._known_jobs.items() if k in current_ids}
            finally:
                win32print.ClosePrinter(handle)
        except Exception:
            pass

    def start(self):
        """初始化已知文件集合"""
        self._known_spl_files = self._get_current_spl_files()
        self._known_jobs = {}
        self._running = True
        logger.info(f"[SpoolMonitor] 开始监视打印机: {self.printer_name}")

    def stop(self):
        self._running = False
