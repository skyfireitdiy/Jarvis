# Web 端启动指南

本指南介绍如何使用 `start.sh` 和 `start.ps1` 脚本启动 Jarvis 的 Web 界面，包括网关服务和前端服务。

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
- **权限**: 需要 Bash 执行权限

#### Windows

- **操作系统**: Windows 10/11
- **Python**: Python 3.12 或更高版本
- **Node.js**: Node.js 16 或更高版本（包含 npm）
- **PowerShell**: PowerShell 5.1 或更高版本

### 依赖检查

启动脚本会自动检查以下依赖：

- Python 命令是否可用
- npm 命令是否可用

如果依赖缺失，脚本会报错并退出。

## 快速启动

### Linux/macOS

1. **赋予执行权限**（首次运行）

```bash
chmod +x start.sh
```

1. **启动服务**

```bash
./start.sh
```

1. **停止服务**

按 `Ctrl+C` 停止所有服务。

### Windows

1. **启动服务**

在 PowerShell 中执行：

```powershell
.\start.ps1
```

如果遇到执行策略限制，可以先临时允许脚本执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\start.ps1
```

1. **停止服务**

按 `Ctrl+C` 停止所有服务。

## 环境变量配置

可以通过环境变量自定义启动参数。支持以下环境变量：

### 网关配置

| 环境变量                  | 默认值      | 说明                 |
| ------------------------- | ----------- | -------------------- |
| `JARVIS_GATEWAY_HOST`     | `127.0.0.1` | 网关监听地址         |
| `JARVIS_GATEWAY_PORT`     | `8000`      | 网关监听端口         |
| `JARVIS_GATEWAY_PASSWORD` | 无          | 网关访问密码（可选） |

### 前端配置

| 环境变量               | 默认值      | 说明         |
| ---------------------- | ----------- | ------------ |
| `JARVIS_FRONTEND_HOST` | `127.0.0.1` | 前端监听地址 |
| `JARVIS_FRONTEND_PORT` | `5173`      | 前端监听端口 |

### 配置示例

#### Linux/macOS

```bash
# 设置自定义端口
export JARVIS_GATEWAY_PORT=9000
export JARVIS_FRONTEND_PORT=3000

# 设置网关密码
export JARVIS_GATEWAY_PASSWORD="your-password-here"

# 启动服务
./start.sh
```

#### Windows (PowerShell)

```powershell
# 设置自定义端口
$env:JARVIS_GATEWAY_PORT = "9000"
$env:JARVIS_FRONTEND_PORT = "3000"

# 设置网关密码
$env:JARVIS_GATEWAY_PASSWORD = "your-password-here"

# 启动服务
.\start.ps1
```

#### Windows (CMD)

```cmd
REM 设置环境变量
set JARVIS_GATEWAY_PORT=9000
set JARVIS_FRONTEND_PORT=3000
set JARVIS_GATEWAY_PASSWORD=your-password-here

REM 启动 PowerShell 并运行脚本
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

## 访问地址

服务启动成功后，您可以通过以下地址访问：

- **网关服务**: <http://127.0.0.1:8000（或您配置的地址和端口）>
- **前端界面**: <http://127.0.0.1:5173（或您配置的地址和端口）>

在浏览器中打开前端地址即可使用 Jarvis 的 Web 界面。

## 常见问题

### Q1: 启动时报错 "未找到 Python 环境"

**原因**: Python 未安装或未添加到系统 PATH。

**解决方案**:

1. 检查 Python 是否已安装：

   ```bash
   python --version
   # 或
   python3 --version
   ```

2. 如果未安装，请先安装 Python 3.12：
   - Linux: `sudo apt install python3.12` (Debian/Ubuntu)
   - macOS: `brew install python3.12`
   - Windows: 从 [python.org](https://www.python.org) 下载安装

### Q2: 启动时报错 "未找到 npm 环境"

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

### Q3: 前端依赖安装失败

**原因**: 网络问题或 npm 镜像源访问慢。

**解决方案**:

1. 使用国内 npm 镜像源：

   ```bash
   npm config set registry https://registry.npmmirror.com
   ```

2. 删除 node_modules 后重新安装：

   ```bash
   rm -rf frontend/node_modules
   ./start.sh
   ```

### Q4: Windows PowerShell 提示无法加载脚本

**原因**: PowerShell 执行策略限制。

**解决方案**:

```powershell
# 临时允许当前会话执行脚本
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 然后再运行启动脚本
.\start.ps1
```

### Q5: 端口被占用

**原因**: 默认端口已被其他程序占用。

**解决方案**:

通过环境变量修改端口：

```bash
# Linux/macOS
export JARVIS_GATEWAY_PORT=9000
export JARVIS_FRONTEND_PORT=3000
./start.sh
```

```powershell
# Windows
$env:JARVIS_GATEWAY_PORT = "9000"
$env:JARVIS_FRONTEND_PORT = "3000"
.\start.ps1
```

### Q6: 如何在后台运行服务？

**Linux/macOS**:

```bash
# 使用 nohup 在后台运行
nohup ./start.sh > jarvis.log 2>&1 &

# 查看日志
tail -f jarvis.log
```

**Windows**:

```powershell
# 使用 Start-Process 在后台运行
Start-Process powershell -ArgumentList "-File .\start.ps1" -NoNewWindow
```

## 使用限制

### 开发模式限制

- **仅用于开发**: 启动脚本适用于开发环境，不建议用于生产环境
- **性能限制**: 前端使用开发模式运行（Vite dev server），性能未优化
- **安全性**: 开发模式下未启用完整的安全防护措施

### 网络限制

- **默认监听**: 默认仅监听 `127.0.0.1`，仅本机可访问
- **远程访问**: 如需远程访问，请修改 `JARVIS_GATEWAY_HOST` 和 `JARVIS_FRONTEND_HOST` 为 `0.0.0.0`

  ```bash
  export JARVIS_GATEWAY_HOST=0.0.0.0
  export JARVIS_FRONTEND_HOST=0.0.0.0
  ./start.sh
  ```

  ⚠️ **注意**: 在公网环境开启远程访问存在安全风险，请确保设置了网关密码。

### 资源限制

- **内存占用**: 需要至少 2GB 可用内存
- **磁盘空间**: 首次运行 npm install 需要约 500MB 磁盘空间

### 浏览器兼容性

- **推荐浏览器**: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- **不支持**: IE 浏览器

### 数据持久化

- **数据存储**: 开发模式下数据存储在内存中，重启后丢失
- **生产部署**: 如需持久化存储，请使用生产环境部署方案

## 下一步

成功启动 Web 服务后，您可以：

1. 在浏览器中访问前端地址，开始使用 Jarvis
2. 查看更多配置选项和高级功能
3. 了解如何部署到生产环境

如需更多帮助，请参考：

- [快速开始指南](jarvis_book/2.快速开始.md)
- [常见问题解答](jarvis_book/8.常见问题.md)
- [功能扩展文档](jarvis_book/5.功能扩展.md)
