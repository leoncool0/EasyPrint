"""
Virtual Printer Manager - Windows Spool API 虚拟打印机管理
创建 PostScript 虚拟打印机，通过 Spool 目录截获打印数据
"""
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

PRINTER_PREFIX = "EasyPrint"


def _find_postscript_drivers() -> List[str]:
    """查找系统上可用的 PostScript 驱动"""
    try:
        import win32print
        drivers = win32print.EnumPrinterDrivers(None, None, 2)
        candidates = []
        for d in drivers:
            name = d.get("pName", "")
            lowered = name.lower()
            # 匹配 PostScript 相关驱动
            if any(k in lowered for k in [
                "postscript", "imagesetter", "laserwriter",
                " laserjet ", " ps ", "-ps ", "ps class",
            ]):
                candidates.append(name)
        return candidates
    except Exception as e:
        logger.error(f"查找驱动失败: {e}")
        return []


def _find_generic_driver() -> Optional[str]:
    """查找通用文本驱动（后备方案）"""
    try:
        import win32print
        drivers = win32print.EnumPrinterDrivers(None, None, 2)
        # 优先查找 Generic / Text Only
        for d in drivers:
            name = d.get("pName", "")
            if "generic / text only" in name.lower():
                return name
        # 查找 Generic 驱动
        for d in drivers:
            name = d.get("pName", "")
            if "generic" in name.lower():
                return name
        return None
    except Exception:
        return None


def _find_fallback_driver() -> Optional[str]:
    """查找后备驱动（PDF/XPS等系统内置驱动）"""
    try:
        import win32print
        drivers = win32print.EnumPrinterDrivers(None, None, 2)
        logger.info(f"系统驱动数量: {len(drivers)}")

        for d in drivers:
            if isinstance(d, dict):
                name = d.get("pName", "") or d.get("Name", "")
                if name:
                    logger.info(f"驱动: {name}")
                    lowered = name.lower()
                    if "pdf" in lowered or "xps" in lowered:
                        logger.info(f"使用后备驱动: {name}")
                        return name
            elif isinstance(d, tuple):
                logger.info(f"驱动元组: {d}")
                if len(d) >= 2:
                    name = d[1]
                    logger.info(f"驱动名称: {name}")
                    lowered = str(name).lower()
                    if "pdf" in lowered or "xps" in lowered:
                        return name

        if drivers:
            d = drivers[0]
            if isinstance(d, dict):
                name = d.get("pName", "") or d.get("Name", "")
            elif isinstance(d, tuple):
                name = d[1] if len(d) >= 2 else ""
            else:
                name = str(d)
            logger.info(f"使用第一个可用驱动: {name}")
            return name if name else None
        return None
    except Exception as e:
        logger.error(f"查找后备驱动失败: {e}")
        return None


def _find_local_printer_driver() -> Optional[str]:
    """查找现有本地打印机的驱动（用于复制其配置创建虚拟打印机）"""
    try:
        import win32print
        # 找到一个真实的本地打印机，使用其驱动
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
        for p in printers:
            if isinstance(p, dict):
                name = p.get("pPrinterName", "")
            elif isinstance(p, tuple):
                name = p[2] if len(p) > 2 else ""
            else:
                continue
            # 跳过 EasyPrint 自己的虚拟打印机
            if name.startswith(PRINTER_PREFIX):
                continue
            # 打开打印机获取其驱动名
            try:
                hprinter = win32print.OpenPrinter(name)
                try:
                    info = win32print.GetPrinter(hprinter, 2)
                    driver_name = info.get("pDriverName", "")
                    if driver_name:
                        return driver_name
                finally:
                    win32print.ClosePrinter(hprinter)
            except Exception:
                continue
        return None
    except Exception as e:
        logger.error(f"查找本地打印机驱动失败: {e}")
        return None


def _find_emf_driver() -> Optional[str]:
    """查找能输出 EMF 格式的驱动"""
    # 使用 EPSON L300 驱动或其他本地驱动，输出 EMF
    return _find_local_printer_driver()


class VirtualPrinterManager:
    """管理 Windows 虚拟打印机（Spool API 方案）"""

    def __init__(self):
        pass

    def find_suitable_driver(self) -> Optional[str]:
        """查找合适的打印机驱动"""
        ps_drivers = _find_postscript_drivers()
        if ps_drivers:
            logger.info(f"找到 PostScript 驱动: {ps_drivers}")
            return ps_drivers[0]

        generic = _find_generic_driver()
        if generic:
            logger.warning(f"未找到 PostScript 驱动，使用通用驱动: {generic}")
            return generic

        fallback = _find_fallback_driver()
        if fallback:
            logger.warning(f"未找到 PostScript/通用驱动，使用后备驱动: {fallback}")
            return fallback

        logger.error("系统上未找到合适的打印机驱动")
        return None

    def create_virtual_printer(self, display_name: str, target_printer_id: str) -> Tuple[bool, str]:
        """创建虚拟打印机

        Args:
            display_name: 显示名称（如 "前台HP打印机"）
            target_printer_id: 服务端对应的 printer_id（用于标识）

        Returns:
            (success, error_message)
        """
        try:
            import win32print
            import win32con

            driver_name = self.find_suitable_driver()
            if not driver_name:
                return False, "未找到合适的打印机驱动（需要 PostScript 或通用驱动）"

            printer_name = f"{PRINTER_PREFIX} - {display_name}"

            # 检查是否已存在
            existing = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
            for p in existing:
                if isinstance(p, dict):
                    p_name = p.get("pPrinterName", "")
                elif isinstance(p, tuple):
                    p_name = p[2] if len(p) > 2 else ""
                else:
                    p_name = ""
                if p_name == printer_name:
                    logger.info(f"虚拟打印机已存在: {printer_name}")
                    return True, ""

            # 使用 level=1 创建打印机（字段更少）
            import win32print
            try:
                printer_info_1 = {
                    "pPrinterName": printer_name,
                    "pPortName": "LPT1:",
                    "pDriverName": driver_name,
                }
                handle = win32print.AddPrinter(None, 1, printer_info_1)
                if handle:
                    win32print.ClosePrinter(handle)
                    logger.info(f"虚拟打印机已创建: {printer_name} (驱动: {driver_name})")
                    return True, ""
            except Exception:
                pass

            # 备选方案：使用命令行工具添加打印机
            try:
                import subprocess
                cmd = f'rundll32 printui.dll,PrintUIEntry /if /b "{printer_name}" /f "%windir%\\inf\\ntprint.inf" /r "LPT1:" /m "{driver_name}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"虚拟打印机已创建(命令行): {printer_name}")
                    return True, ""
                else:
                    logger.warning(f"命令行创建失败: {result.stderr}")
            except Exception as e:
                logger.warning(f"命令行创建异常: {e}")

            return False, f"无法创建虚拟打印机（win32print和命令行方式均失败）"

        except Exception as e:
            err_msg = str(e)
            logger.error(f"创建虚拟打印机失败: {err_msg}")
            return False, err_msg

    def remove_virtual_printer(self, printer_name: str) -> bool:
        """删除虚拟打印机"""
        try:
            import win32print

            full_name = printer_name if printer_name.startswith(PRINTER_PREFIX) else f"{PRINTER_PREFIX} - {printer_name}"

            handle = win32print.OpenPrinter(full_name)
            try:
                win32print.DeletePrinter(handle)
            finally:
                win32print.ClosePrinter(handle)

            logger.info(f"虚拟打印机已删除: {full_name}")
            return True

        except Exception as e:
            logger.error(f"删除虚拟打印机失败: {e}")
            return False

    def list_virtual_printers(self) -> List[Dict]:
        """列出已安装的虚拟打印机"""
        result = []
        try:
            import win32print
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
            for p in printers:
                name = p.get("pPrinterName", "")
                if name.startswith(f"{PRINTER_PREFIX} - "):
                    display_name = name[len(f"{PRINTER_PREFIX} - "):]
                    # 从 Comment 提取 target_printer_id
                    comment = p.get("pComment", "")
                    target_id = ""
                    if comment.startswith("EasyPrint:"):
                        target_id = comment[len("EasyPrint:"):]
                    result.append({
                        "name": display_name,
                        "printer_name": name,
                        "target_printer_id": target_id,
                        "port": p.get("pPortName", ""),
                    })
        except Exception as e:
            logger.error(f"列出虚拟打印机失败: {e}")
        return result

    def install_multiple(self, printers: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """批量安装虚拟打印机

        Args:
            printers: [{"name": "显示名", "printer_id": "服务端printer_id"}, ...]
        Returns:
            (成功安装的列表, 失败原因列表)
        """
        installed = []
        errors = []
        for p in printers:
            ok, err = self.create_virtual_printer(p["name"], p["printer_id"])
            if ok:
                installed.append(p)
            else:
                errors.append(f"{p.get('name', 'Unknown')}: {err}")
        return installed, errors
