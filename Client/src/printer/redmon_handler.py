#!/usr/bin/env python
"""
RedMon Handler - RedMon 端口监视器调用此脚本处理打印数据
读取 stdin 的打印数据，保存到 spool 目录，客户端会自动拾取并发送到服务端

用法: pythonw redmon_handler.py <printer_id> <spool_dir>
环境变量 (RedMon 设置):
  REDMON_DOCNAME  - 文档名称
  REDMON_USER     - 打印用户
  REDMON_MACHINE  - 计算机名
  REDMON_PRINTER  - 打印机名
"""
import sys
import os
import json
import time
from pathlib import Path


def main():
    # 解析参数
    if len(sys.argv) < 3:
        return

    printer_id = sys.argv[1]
    spool_dir = Path(sys.argv[2])

    # 获取文档名
    doc_name = os.environ.get("REDMON_DOCNAME", "Print Job")

    # 从 stdin 读取打印数据
    data = sys.stdin.buffer.read()
    if not data:
        return

    # 确保目录存在
    spool_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名
    timestamp = int(time.time() * 1000)
    pid = os.getpid()
    data_file = spool_dir / f"job_{timestamp}_{pid}.dat"
    job_file = spool_dir / f"job_{timestamp}_{pid}.json"

    # 保存打印数据
    with open(data_file, "wb") as f:
        f.write(data)

    # 保存任务信息
    job_info = {
        "printer_id": printer_id,
        "job_name": doc_name,
        "file_path": str(data_file.resolve()),
        "file_size": len(data),
        "timestamp": timestamp,
    }
    with open(job_file, "w", encoding="utf-8") as f:
        json.dump(job_info, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
