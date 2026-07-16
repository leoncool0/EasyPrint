
# EasyPrint ️

**EasyPrint** 是一款专为解决跨操作系统打印机共享难题而设计的轻量级网络打印网关。它彻底打破了 Windows XP 与 Windows 10/11 之间因 SMB 协议禁用、驱动签名限制导致的“网络隔离”，让老旧设备与现代办公环境无缝连接。

通过“Docker 服务端 + 统一客户端”的现代化架构，EasyPrint 将复杂的系统级共享转化为简单的应用层数据转发，让每一次打印都简单、稳定、安全。

##  核心特性

-  **跨时代兼容**：完美支持 Windows XP 到 Windows 11 的全版本互联，彻底绕过 SMBv1 和 RPC 限制。
-  **统一客户端**：一个安装包搞定一切。通过勾选即可在“打印机主机”与“网络用户”之间自由切换，支持混合模式。
-  **Docker 容器化部署**：服务端轻量、稳定、跨平台。一行命令即可在 NAS、Linux 或云服务器上启动打印中枢。
-  **即插即用体验**：内置虚拟打印机驱动，用户端一键映射，无需手动安装老旧的硬件驱动。
- ️ **企业级管理**：提供现代化的 Web 管理后台，支持设备监控、打印日志审计、任务队列管理及权限控制。
-  **高可用设计**：支持断线重连、本地任务缓存与状态实时反馈（缺纸/卡纸/离线）。

## ️ 架构概览

EasyPrint 采用经典的 Client-Server 架构，通过自定义 TCP 协议进行高效的数据路由：

1. **Server (Docker)**: 系统的“大脑”。负责设备注册、心跳检测、任务队列调度与数据流转发。
2. **Host Client (主机端)**: 运行在连接物理打印机的电脑上（如 Win XP）。负责捕获本地打印数据或接收服务端转发的数据流，并透传给物理设备。
3. **User Client (用户端)**: 运行在需要打印的电脑上（如 Win 10/11）。通过虚拟打印机拦截打印任务，封装后发送至服务端。

##  快速开始

### 1. 部署服务端 (Server)

确保您的服务器已安装 Docker 和 Docker Compose。

```bash
# 创建项目目录
mkdir easyprint-server && cd easyprint-server

# 下载 docker-compose.yml 配置文件
# (请替换为实际的仓库链接或本地文件路径)
wget https://raw.githubusercontent.com/your-repo/easyprint/main/docker-compose.yml

# 启动服务
docker-compose up -d
```
启动后，访问 `http://<服务器IP>:8080` 进入 Web 管理后台。

### 2. 安装客户端 (Client)

1. 下载最新版本的 `EasyPrint_Setup.exe`。
2. 运行安装程序，选择语言并同意许可协议。
3. 在**角色配置页**，根据当前电脑的功能进行勾选：
   - [x] **我是打印机主机**（连接了物理打印机）
   - [x] **我是普通用户**（需要打印网络文件）
4. 输入 EasyPrint 服务端的 IP 地址和端口，完成配置。

## ️ 技术栈

- **Server**: Go / Node.js (轻量级高并发框架)
- **Web UI**: Vue.js / React
- **Client**: C++ (Win32 API / Qt) 确保对 Windows XP 的极致兼容
- **Protocol**: Custom TCP / MQTT (轻量级物联网通信协议)

##  贡献指南

我们欢迎任何形式的贡献！如果您发现了 Bug 或有新的功能建议，请提交 Issue 或 Pull Request。

##  开源协议

本项目基于 [MIT License](LICENSE) 开源。