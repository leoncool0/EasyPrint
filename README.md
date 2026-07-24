# EasyPrint

**EasyPrint** 是一款跨系统打印机共享软件，解决 Windows XP 与 Windows 10/11 之间因 SMB 协议禁用、驱动签名限制导致的打印机共享问题。

通过 "Docker 服务端 + 统一客户端" 架构，将复杂的系统级打印共享转化为简单的应用层数据转发。

## 核心特性

- **跨系统兼容**：绕过 SMBv1 和 RPC 限制，支持 Windows XP 到 Windows 11 全版本互联
- **统一客户端**：一个安装包支持主机端、用户端、混合模式三种角色自由切换
- **Docker 容器化部署**：服务端一行命令启动，支持 NAS、Linux、云服务器
- **虚拟打印机**：用户端自动创建虚拟打印机，拦截打印任务并转发
- **Web 管理后台**：设备监控、打印机管理、任务队列、深色/浅色主题切换
- **实时状态同步**：打印任务状态（创建→传输→排队→打印→完成/失败）全程追踪

## 架构概览

```
┌─────────────┐        TCP/9100        ┌─────────────────┐        TCP/9100        ┌─────────────┐
│  用户端客户端  │ ────────────────────── │   服务端 (Docker)  │ ────────────────────── │  主机端客户端  │
│  (Win 10/11) │   打印数据转发 (XPS)    │  FastAPI + SQLite │   打印数据转发 (XPS)    │   (Win XP)   │
│              │                        │   Web: :8080      │                        │              │
│  虚拟打印机   │                        │   TCP: :9100      │                        │  物理打印机   │
└─────────────┘                        └─────────────────┘                        └─────────────┘
```

1. **Server (Docker)**：设备注册、心跳检测、任务队列调度、数据流转发、Web 管理后台
2. **Host Client (主机端)**：运行在连接物理打印机的电脑上，接收服务端转发的打印数据并输出到本地打印机
3. **User Client (用户端)**：运行在需要打印的电脑上，通过虚拟打印机拦截打印任务，封装后发送至服务端

## 打印流程

1. 用户端虚拟打印机拦截打印任务 → 生成 XPS 格式 spool 文件
2. 客户端读取 spool 文件 → 通过 TCP 协议发送到服务端
3. 服务端转发打印数据到目标主机端
4. 主机端接收 XPS 数据 → 用 PyMuPDF 渲染为图像 → 通过 GDI 发送到物理打印机

## 快速开始

### 1. 部署服务端

确保服务器已安装 Docker 和 Docker Compose。

```bash
# 上传 server 目录到服务器 /user/EasyPrint
cd /user/EasyPrint/server

# 启动服务
docker-compose up -d
```

启动后访问 `http://<服务器IP>:8080` 进入 Web 管理后台。

**默认端口：**
- Web 管理后台：8080
- TCP 网关：9100
- 数据持久化：`/user/EasyPrint/data` 和 `/user/EasyPrint/logs`

### 2. 安装客户端

1. 获取 `EasyPrint Client.exe`
2. 首次运行进入配置向导：
   - 输入服务端 IP 地址
   - 选择角色：主机端 / 用户端 / 混合模式
   - 主机端：选择要共享的打印机
   - 用户端：选择要使用的远程打印机，自动创建虚拟打印机
3. 完成配置后自动连接服务端，最小化到系统托盘

> **注意**：客户端需要以管理员身份运行，以访问 spool 目录和打印机 API。

## 技术栈

| 组件 | 技术 |
|------|------|
| 服务端 | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), SQLite (aiosqlite) |
| 客户端 | Python 3.8, PySide6, qasync, PyInstaller |
| Web UI | Vue 3 (CDN), Element Plus (CDN) |
| 打印渲染 | PyMuPDF (fitz), Pillow (PIL), win32print/win32ui (GDI) |
| 通信协议 | 自定义 TCP 二进制协议 |
| 部署 | Docker, docker-compose |

## 项目结构

```
EasyPrint/
├── Server/                    # 服务端
│   ├── app/
│   │   ├── api/               # REST API (设备/打印机/任务/日志/统计)
│   │   ├── models/            # 数据库模型 (SQLAlchemy)
│   │   ├── tcp/               # TCP 网关 (连接管理/心跳/协议)
│   │   ├── web/static/        # Web 管理后台 (单页应用)
│   │   ├── config.py          # 配置
│   │   └── main.py            # 入口
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
├── Client/                    # 客户端
│   ├── src/
│   │   ├── core/              # 核心逻辑 (客户端/配置管理)
│   │   ├── network/           # TCP 连接
│   │   ├── printer/           # 打印机扫描/虚拟打印机/Spool 监视
│   │   ├── ui/                # 界面 (主窗口/向导/托盘)
│   │   └── utils/             # 工具 (开机自启)
│   ├── main.py                # 入口
│   ├── build.bat              # 打包脚本
│   └── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

## 打包客户端

```bash
cd Client
# 使用 build.bat 打包（需要 Python 3.8 + PyInstaller）
build.bat
```

生成的 exe 在 `Client/dist/EasyPrint Client.exe`。

## 版本迭代

### v0.1.2 (2026-07-24)

**服务端：**
- 添加 `/api/info` 端点，修复管理后台版本号未显示问题
- 打印机列表 API 联表查询设备信息，返回 `host_device_name` 字段
- TCP 连接的打印机列表响应也返回设备名称，支持客户端区分不同设备的相同型号打印机
- CDN 链接切换为国内 BootCDN 源，提升页面加载速度
- 修复深色模式下表格行底色显示异常问题，优化隔行变色和 hover 效果

**客户端：**
- 设备信息页配置向导优化，设备名称预填后可直接点击下一步
- 打印机列表显示格式改为 `[设备名称] 打印机名称`，便于区分不同部门的相同型号打印机
- 配置向导中用户端打印机列表也显示设备名称前缀

### v0.1.0 (2026-07-22)

首个完整可运行版本，实现端到端打印共享功能。

**服务端：**
- Docker 容器化部署，SQLite 持久化
- TCP 网关，设备认证与心跳检测（30秒间隔，90秒超时）
- Web 管理后台（设备/打印机/任务/日志管理，深色/浅色主题）
- 打印任务状态流转（创建→传输→排队→打印→完成/失败/取消）
- 断线自动标记设备离线，同步关联打印机状态

**客户端：**
- 三种角色：主机端 / 用户端 / 混合模式
- 首次运行配置向导，支持连接测试
- 虚拟打印机自动创建（Windows Spool API）
- Spool 文件监视，XPS 格式打印数据截获
- PyMuPDF 渲染 XPS 为图像，GDI 发送到物理打印机
- 打印任务状态实时同步显示，区分发送/接收任务
- 系统托盘最小化，开机自启
- PyInstaller 打包为单文件 exe

### v0.0.1 (2026-07-15)

初始原型，搭建基本项目结构与通信框架。

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
