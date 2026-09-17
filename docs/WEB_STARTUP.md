# Web 端启动指南

本指南介绍如何使用 `jarvis-service run` 启动 Jarvis 的 Web 界面，包括网关服务和前端服务。

## 目录

- [环境要求](#环境要求)
- [快速启动](#快速启动)
- [环境变量配置](#环境变量配置)
- [访问地址](#访问地址)
- [常见问题](#常见问题)
- [使用限制](#使用限制)

## 环境要求

### 基础要求

#### Linux/macOS

- **操作系统**: Linux 或 macOS
- **Python**: Python 3.12 或更高版本
- **Node.js**: Node.js 16 或更高版本（包含 npm）

#### Windows

- **操作系统**: Windows 10/11
- **Python**: Python 3.12 或更高版本
- **Node.js**: Node.js 16 或更高版本（包含 npm）

### 依赖检查

`jarvis-service run` 在启动前端时会检查以下依赖：

- npm 命令是否可用

如果 npm 缺失，服务会报错并退出。

## 快速启动

### Linux/macOS/Windows

1. **启动服务**

```bash
jarvis-service run
```

该命令会依次完成：

- 启动 Web 网关服务（默认 `127.0.0.1:8000`）
- 安装前端依赖（`npm install`）
- 构建前端发布产物（`npm run build`）
- 启动前端发布服务（默认 `127.0.0.1:5173`）

1. **停止服务**

在终端按 `Ctrl+C` 停止所有服务。

> 如需以开发模式启动前端（热加载、跳过构建），可加 `--dev` 参数：
>
> ```bash
> jarvis-service run --dev
> ```

### 指定监听地址与端口

```bash
jarvis-service run --gateway-host 0.0.0.0 --gateway-port 9000 --frontend-host 0.0.0.0 --frontend-port 3000
```

### 安装为系统服务（可选）

在支持 systemd 的 Linux 环境中，也可以把服务安装为 systemd 用户服务长期运行：

```bash
jarvis-service install --node-mode master
jarvis-service start master
```

## 环境变量配置

可以通过环境变量自定义启动参数。支持以下环境变量：

### 网关配置

| 环境变量                  | 默认值      | 说明                 |
| ------------------------- | ----------- | -------------------- |
| `JARVIS_GATEWAY_HOST`     | `127.0.0.1` | 网关监听地址         |
| `JARVIS_GATEWAY_PORT`     | `8000`      | 网关监听端口         |
| `JARVIS_GATEWAY_PASSWORD` | 无          | 网关访问密码（可选） |

> 网关密码只能通过环境变量 `JARVIS_GATEWAY_PASSWORD` 设置，`jarvis-service run` 没有对应的命令行选项。

### 前端配置

| 环境变量               | 默认值      | 说明         |
| ---------------------- | ----------- | ------------ |
| `JARVIS_FRONTEND_HOST` | `127.0.0.1` | 前端监听地址 |
| `JARVIS_FRONTEND_PORT` | `5173`      | 前端监听端口 |

### 节点模式配置

| 环境变量             | 默认值   | 说明                          |
| -------------------- | -------- | ----------------------------- |
| `JARVIS_NODE_MODE`   | `master` | 节点模式：`master` 或 `child` |
| `JARVIS_NODE_ID`     | 无       | 当前节点 ID（child 模式使用） |
| `JARVIS_MASTER_URL`  | 无       | 主节点地址（child 模式使用）  |
| `JARVIS_NODE_SECRET` | 无       | 主子节点共享密钥              |
| `JARVIS_DEV_MODE`    | `false`  | 是否以开发模式启动前端        |

### 配置示例

#### Linux/macOS

```bash
# 设置自定义端口
export JARVIS_GATEWAY_PORT=9000
export JARVIS_FRONTEND_PORT=3000

# 设置网关密码
export JARVIS_GATEWAY_PASSWORD="your-password-here"

# 启动服务
jarvis-service run
```

#### Windows (PowerShell)

```powershell
# 设置自定义端口
$env:JARVIS_GATEWAY_PORT = "9000"
$env:JARVIS_FRONTEND_PORT = "3000"

# 设置网关密码
$env:JARVIS_GATEWAY_PASSWORD = "your-password-here"

# 启动服务
jarvis-service run
```

#### Windows (CMD)

```cmd
REM 设置环境变量
set JARVIS_GATEWAY_PORT=9000
set JARVIS_FRONTEND_PORT=3000
set JARVIS_GATEWAY_PASSWORD=your-password-here

REM 启动服务
jarvis-service run
```

## 访问地址

服务启动成功后，您可以通过以下地址访问：

- **网关服务**: <http://127.0.0.1:8000>（或您配置的地址和端口）
- **前端界面**: <http://127.0.0.1:5173>（或您配置的地址和端口）

在浏览器中打开前端地址即可使用 Jarvis 的 Web 界面。

## 常见问题

### Q1: 启动时报错 "未找到 npm 环境"

**原因**: Node.js 或 npm 未安装或未添加到系统 PATH。

**解决方案**:

1. 检查 npm 是否已安装：

   ```bash
   npm --version
   ```

2. 如果未安装，请先安装 Node.js：
   - Linux: `sudo apt install nodejs npm`
   - macOS: `brew install node`
   - Windows: 从 [nodejs.org](https://nodejs.org) 下载安装

### Q2: 前端依赖安装失败

**原因**: 网络问题或 npm 镜像源访问慢。

**解决方案**:

1. 使用国内 npm 镜像源：

   ```bash
   npm config set registry https://registry.npmmirror.com
   ```

2. 删除 node_modules 后重新启动服务：

   ```bash
   rm -rf src/jarvis/jarvis_service/frontend/node_modules
   jarvis-service run
   ```

### Q3: 端口被占用

**原因**: 默认端口已被其他程序占用。

**解决方案**:

通过命令行参数或环境变量修改端口：

```bash
# Linux/macOS
export JARVIS_GATEWAY_PORT=9000
export JARVIS_FRONTEND_PORT=3000
jarvis-service run
```

```powershell
# Windows
$env:JARVIS_GATEWAY_PORT = "9000"
$env:JARVIS_FRONTEND_PORT = "3000"
jarvis-service run
```

也可以直接使用命令行参数：

```bash
jarvis-service run --gateway-port 9000 --frontend-port 3000
```

### Q4: 如何在后台运行服务？

**Linux/macOS**:

```bash
# 使用 nohup 在后台运行
nohup jarvis-service run > jarvis.log 2>&1 &

# 查看日志
tail -f jarvis.log
```

**Windows**:

```powershell
# 使用 Start-Process 在后台运行
Start-Process jarvis-service -ArgumentList "run" -NoNewWindow
```

### Q5: 服务异常退出后如何重启？

`jarvis-service run` 会自行处理重启信号：

- `SIGUSR1`：重启全部服务
- `SIGUSR2`：仅重启网关服务

在支持 systemd 的 Linux 环境中，也可以安装为 systemd 用户服务，由 systemd 负责守护与重启：

```bash
jarvis-service install --node-mode master
jarvis-service start master
```

## 使用限制

### 开发模式限制

- **仅用于开发**: `--dev` 模式适用于开发环境，不建议用于生产环境
- **性能限制**: 开发模式下前端使用 Vite dev server，性能未优化
- **安全性**: 开发模式下未启用完整的安全防护措施

### 网络限制

- **默认监听**: 默认仅监听 `127.0.0.1`，仅本机可访问
- **远程访问**: 如需远程访问，请将网关和前端监听地址都改为 `0.0.0.0`

  ```bash
  jarvis-service run --gateway-host 0.0.0.0 --frontend-host 0.0.0.0
  ```

  ⚠️ **注意**: 在公网环境开启远程访问存在安全风险，请确保设置了网关密码（`JARVIS_GATEWAY_PASSWORD`）。

### 资源限制

- **内存占用**: 需要至少 2GB 可用内存
- **磁盘空间**: 首次运行 npm install 需要约 500MB 磁盘空间

### 浏览器兼容性

- **推荐浏览器**: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- **不支持**: IE 浏览器

### 数据持久化

- **数据存储**: 数据默认保存在 `~/.jarvis` 目录下
- **生产部署**: 如需多节点或长期运行，请参考分布式部署方案

## 下一步

成功启动 Web 服务后，您可以：

1. 在浏览器中访问前端地址，开始使用 Jarvis
2. 查看更多配置选项和高级功能
3. 了解如何部署到生产环境

如需更多帮助，请参考：

- [快速开始指南](jarvis_book/2.快速开始.md)
- [常见问题解答](jarvis_book/8.常见问题.md)
- [功能扩展文档](jarvis_book/5.功能扩展.md)
