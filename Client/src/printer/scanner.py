"""
Printer Scanner - Scan local printers (Windows)
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class PrinterScanner:
    """Scan local printers"""

    def __init__(self):
        self.printers: List[Dict] = []

    def scan(self) -> List[Dict]:
        """Scan local printers"""
        self.printers = []

        try:
            # Try to use win32print
            import win32print

            # Get default printer
            default = win32print.GetDefaultPrinter()

            # Enumerate printers
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            printers_info = win32print.EnumPrinters(flags, None, 2)

            for info in printers_info:
                printer_name = info['pPrinterName']
                self.printers.append({
                    "name": printer_name,
                    "model": info.get('pDriverName', ''),
                    "is_default": printer_name == default,
                    "status": self._get_status(info.get('Status', 0)),
                })

            logger.info(f"Found {len(self.printers)} printers")

        except ImportError:
            logger.warning("win32print not available, using mock data")
            # Mock data for development
            self.printers = [
                {"name": "Microsoft Print to PDF", "model": "PDF", "is_default": True, "status": "online"},
            ]

        return self.printers

    def _get_status(self, status_code: int) -> str:
        """Convert status code to string"""
        # Windows printer status constants
        STATUS_ONLINE = 0x00000000
        STATUS_PAUSED = 0x00000001
        STATUS_ERROR = 0x00000002
        STATUS_PAPER_JAM = 0x00000008
        STATUS_PAPER_OUT = 0x00000010
        STATUS_MANUAL_FEED = 0x00000020
        STATUS_OFFLINE = 0x00000100
        STATUS_IO_ACTIVE = 0x00000100
        STATUS_BUSY = 0x00000200

        if status_code == STATUS_ONLINE:
            return "online"
        elif status_code & STATUS_OFFLINE:
            return "offline"
        elif status_code & STATUS_BUSY:
            return "busy"
        elif status_code & STATUS_ERROR:
            return "error"
        else:
            return "unknown"


if __name__ == "__main__":
    scanner = PrinterScanner()
    printers = scanner.scan()
    for p in printers:
        print(f"  - {p['name']} ({p['model']}) - {p['status']}")