# EasyPrint Server Docker 部署指南

## 文件说明

将 `server/` 目录下的以下文件上传到 Ubuntu 服务器：

```
server/
├── Dockerfile           # Docker 镜像构建文件
├── docker-compose.yml   # Docker Compose 编排配置
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量示例
└── app/                 # 应用代码
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── api/
    │   ├── __init__.py
    │   ├── printers.py
    │   ├── jobs.py
    │   └── devices.py
    ├── tcp/
    │   ├── __init__.py
    │   ├── protocol.py
    │   ├── gateway.py
    │   └── connection.py
    └── models/
        └── __init__.py
        └── database.py
```

## 部署步骤

### 1. 安装 Docker 和 Docker Compose

```bash
# 更新包索引
sudo apt-get update

# 安装 Docker
sudo apt-get install -y docker.io

# 安装 Docker Compose
sudo apt-get install -y docker-compose

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 将当前用户加入 docker 组（免 sudo）
sudo usermod -aG docker $USER
# 重新登录使权限生效
```

### 2. 上传项目文件

将 `server/` 目录上传到 Ubuntu，例如 `/opt/easyprint/`：

```bash
# 创建目录
sudo mkdir -p /opt/easyprint

# 上传文件后，设置权限
sudo chown -R $USER:$USER /opt/easyprint
```

### 3. 配置环境变量

```bash
cd /opt/easyprint

# 复制环境变量示例
cp .env.example .env

# 编辑 .env 文件，修改 SECRET_KEY
nano .env
```

`.env` 文件示例：
```
SECRET_KEY=your-very-long-random-secret-key-here
DEBUG=false
```

### 4. 构建并启动服务

```bash
cd /opt/easyprint

# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看状态
docker-compose ps
```

### 5. 验证部署

```bash
# 检查服务是否运行
curl http://localhost:8080/

# 健康检查
curl http://localhost:8080/health

# 查看 API 文档（Swagger UI）
# 浏览器访问: http://<服务器IP>:8080/docs
```

### 6. 常用命令

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看实时日志
docker-compose logs -f

# 进入容器内部
docker exec -it easyprint-server bash

# 更新代码后重新构建
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 查看容器资源使用
docker stats easyprint-server
```

### 7. 数据备份

SQLite 数据库和日志文件通过数据卷挂载到宿主机：

```bash
# 备份数据库
cp /opt/easyprint/data/easyprint.db /backup/easyprint-$(date +%Y%m%d).db

# 备份日志
tar -czf /backup/easyprint-logs-$(date +%Y%m%d).tar.gz /opt/easyprint/logs/
```

## 端口说明

| 端口 | 协议 | 用途 | 外部访问 |
|------|------|------|----------|
| 8080 | TCP | HTTP API / Web UI | 需要 |
| 9100 | TCP | TCP Gateway（客户端连接）| 需要 |
| 20000 | UDP | 服务发现（局域网广播）| 可选 |

## 防火墙配置

如果启用了 UFW 防火墙，需要开放端口：

```bash
sudo ufw allow 8080/tcp
sudo ufw allow 9100/tcp
sudo ufw allow 20000/udp
sudo ufw reload
```

## 故障排查

### 容器无法启动

```bash
# 查看详细日志
docker-compose logs --tail=100

# 检查端口是否被占用
sudo netstat -tlnp | grep 8080
sudo netstat -tlnp | grep 9100
```

### 客户端无法连接

1. 确认服务器防火墙已开放端口
2. 确认 docker-compose.yml 中的端口映射正确
3. 检查服务器 IP 地址是否正确

### 数据库问题

```bash
# 进入容器查看数据库
docker exec -it easyprint-server sqlite3 /app/data/easyprint.db

# 查看表结构
sqlite> .tables
sqlite> .schema devices
```