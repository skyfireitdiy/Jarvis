---
name: remote-deployment
description: 当需要将Jarvis部署到远程服务器时使用此规则——远程部署规则，定义通过SSH远程部署Jarvis的标准化流程和要求。包括：收集远程服务器信息（IP、端口、用户名、密码）；使用sshpass建立SSH连接；检测远程服务器环境和依赖；在远程服务器上执行部署脚本；验证远程部署结果；处理部署过程中的错误和异常；询问用户是否需要注册为系统服务；根据用户选择注册为master或child节点。每当用户提及"远程部署"、"部署到服务器"、"服务器部署"、"SSH部署"或需要将Jarvis部署到远程目标环境时触发。如果需要将Jarvis部署到远程服务器，请使用此规则。
---

# Jarvis 远程部署规则

Jarvis 远程部署规则定义了将 Jarvis 部署到远程服务器中的标准化流程和要求。

## 你必须遵守的原则

1. **安全优先原则**：SSH凭证仅在当前会话中使用，不持久化存储
2. **清晰指导原则**：提供清晰、逐步可执行的部署指导
3. **用户确认原则**：关键步骤需要用户确认后再执行
4. **问题解决原则**：系统性分析和解决部署过程中的错误
5. **服务注册原则**：部署成功后主动询问是否需要注册为系统服务

## 你必须遵循的工作流程

### 1. 收集远程服务器信息

在开始部署之前，必须向用户收集以下信息：

| 参数     | 说明                       | 示例          |
| -------- | -------------------------- | ------------- |
| 远程IP   | 服务器IP地址或域名         | 192.168.1.100 |
| 端口     | SSH端口号（默认22）        | 22            |
| 用户名   | SSH登录用户名              | root          |
| 密码     | SSH登录密码                | \*\*\*\*      |
| 安装目录 | Jarvis安装目标目录（可选） | ~/Jarvis      |

**收集方式**：使用交互式对话向用户询问上述信息。

### 2. 前置检查

#### 2.1 检查本地环境

在本地执行以下检查：

```bash
# 检查 sshpass 是否可用
which sshpass || echo "sshpass not found"

# 检查 SSH 客户端是否可用
which ssh || echo "ssh not found"
```

如果 sshpass 不可用，提示用户安装：

```bash
# Ubuntu/Debian
sudo apt-get install sshpass

# macOS
brew install sshpass

# CentOS/RHEL
sudo yum install sshpass
```

#### 2.2 测试远程连接

在收集到凭证后，先测试SSH连接是否正常：

```bash
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PORT $USERNAME@$IP "echo 'Connection OK'"
```

如果连接失败，记录错误信息并向用户报告。

### 3. 远程环境检测

通过SSH在远程服务器上执行环境检测：

#### 3.1 系统信息检测

```bash
# 检测操作系统
uname -a
cat /etc/os-release 2>/dev/null || cat /etc/redhat-release 2>/dev/null

# 检测架构
uname -m

# 检测磁盘空间（需要至少1GB可用）
df -h ~

# 检测用户权限
whoami
id
```

#### 3.2 依赖检测

```bash
# 检测 git
which git && git --version

# 检测 Python（可选，用于检测预装环境）
which python3 && python3 --version

# 检测网络连接（测试GitHub/Gitee可达性）
curl -s --connect-timeout 5 https://github.com --head || echo "GitHub unreachable"
curl -s --connect-timeout 5 https://gitee.com --head || echo "Gitee unreachable"
```

### 4. 执行远程部署

#### 4.1 一键安装（推荐）

直接执行远程安装命令：

```bash
# 一键安装 Jarvis（使用 GitHub 官方安装脚本）
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT \
  'curl -sL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh | bash'
```

#### 4.2 分步执行（用于调试）

适用于需要分步验证的场景：

```bash
# 步骤1：测试连接
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT 'hostname && whoami'

# 步骤2：执行安装
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT \
  'curl -sL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh | bash'

# 步骤3：验证安装
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT 'source ~/.bashrc && jarvis --version'
```

### 5. 部署验证

#### 5.1 基本验证

```bash
# 验证 jarvis 命令可用
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT "
source ~/.bashrc 2>/dev/null || true
command -v jarvis && jarvis --version || echo 'Jarvis command not found in PATH'
"

# 验证安装目录
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT "
ls -la ~/Jarvis/pyproject.toml
"
```

#### 5.2 服务验证（如果安装成功）

```bash
# 验证 jarvis-service 命令
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT "
source ~/.bashrc 2>/dev/null || true
jarvis-service --help || echo 'jarvis-service not found'
"
```

### 6. 服务注册询问

### 服务注册询问

部署成功后，必须主动询问用户是否需要注册为系统服务

向用户展示以下询问信息：

```text
========================================
Jarvis 远程部署成功！
========================================

安装目录：$INSTALL_DIR
部署主机：$USERNAME@$IP:$PORT

是否需要将 Jarvis 注册为系统服务？

选项说明：
  1. 不注册服务 - 仅完成部署，不配置systemd服务
  2. 注册为 Master 节点 - 主节点模式，启动Web前端和网关服务
  3. 注册为 Child 节点 - 子节点模式，需要指定主节点URL和密钥

请选择 [1/2/3]：
========================================
```

### 7. 服务注册执行

根据用户选择执行相应的服务注册命令。

#### 7.1 不注册服务

```bash
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT "
source ~/.bashrc 2>/dev/null || true
echo '服务注册已跳过'
echo '如需手动启动，请执行：jarvis-service start'
"
```

#### 7.2 注册为 Master 节点

```bash
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT "
source ~/.bashrc 2>/dev/null || true

# 安装为systemd用户服务
jarvis-service install --node-mode master

# 重新加载systemd配置
systemctl --user daemon-reload

# 启用并启动服务
systemctl --user enable jarvis-service.service
systemctl --user start jarvis-service.service

# 检查服务状态
systemctl --user status jarvis-service.service
"
```

Master节点可选参数：

- `--gateway-host`：网关监听地址（默认127.0.0.1）
- `--gateway-port`：网关端口（默认8000）
- `--gateway-password`：网关密码（可选）

#### 7.3 注册为 Child 节点

**在执行前，需要向用户收集以下信息**：

| 参数        | 说明                           | 示例             |
| ----------- | ------------------------------ | ---------------- |
| Node ID     | 当前节点标识                   | worker-01        |
| Master URL  | 主节点WebSocket地址            | ws://master:8000 |
| Node Secret | 主节点密钥（从master节点获取） | \*\*\*\*         |

```bash
sshpass -p "$PASSWORD" ssh $USERNAME@$IP -p $PORT "
source ~/.bashrc 2>/dev/null || true

# 安装为systemd用户服务（子节点模式）
jarvis-service install \
    --node-mode child \
    --node-id '$NODE_ID' \
    --master-url '$MASTER_URL' \
    --node-secret '$NODE_SECRET'

# 重新加载systemd配置
systemctl --user daemon-reload

# 启用并启动服务
systemctl --user enable jarvis-service.service
systemctl --user start jarvis-service.service

# 检查服务状态
systemctl --user status jarvis-service.service
"
```

### 8. 错误处理

#### 8.1 常见错误及解决方案

| 错误类型         | 可能原因                 | 解决方案                             |
| ---------------- | ------------------------ | ------------------------------------ |
| SSH连接失败      | 网络不通/端口错误/防火墙 | 检查网络连接、确认端口号、开放防火墙 |
| 认证失败         | 用户名/密码错误          | 核对凭证信息                         |
| 磁盘空间不足     | 可用空间小于1GB          | 清理磁盘或扩展存储                   |
| Git克隆失败      | 网络问题/GitHub不可达    | 尝试使用Gitee镜像源                  |
| 安装脚本执行失败 | 依赖缺失/权限不足        | 检查系统依赖、确保用户权限           |
| systemctl失败    | systemd未运行/权限不足   | 检查systemd状态、启用linger          |

#### 8.2 错误处理流程

1. 记录完整的错误信息和上下文
2. 分析错误原因
3. 尝试实施解决方案
4. 如果无法解决，向用户请求帮助并提供详细信息

## 执行检查清单

### 部署前检查

- [ ] 已收集完整的远程服务器信息（IP、端口、用户名、密码）
- [ ] 已验证本地 sshpass 工具可用
- [ ] 已测试SSH连接正常
- [ ] 已确认远程服务器磁盘空间充足（≥1GB）

### 部署过程检查

- [ ] 已成功下载安装脚本到远程服务器
- [ ] 已成功执行安装脚本
- [ ] 部署过程无致命错误
- [ ] 已验证jarvis命令可用

### 服务注册检查（如果用户选择注册）

- [ ] Master节点：已确认npm可用（如需要Web前端）
- [ ] Child节点：已收集完整的主节点信息（URL、Secret）
- [ ] 已成功执行 jarvis-service install
- [ ] 已启用并启动服务
- [ ] 已验证服务状态正常

### 部署后检查

- [ ] 已向用户展示部署结果
- [ ] 已提供服务管理命令
- [ ] 已说明如何验证部署成功

## 服务管理命令参考

部署完成后，向用户提供以下常用命令：

```bash
# 查看服务状态
systemctl --user status jarvis-service.service

# 查看服务日志
journalctl --user -u jarvis-service.service -f

# 重启服务
systemctl --user restart jarvis-service.service

# 停止服务
systemctl --user stop jarvis-service.service

# 禁用服务
systemctl --user disable jarvis-service.service

# 手动启动（不注册服务时）
jarvis-service start

# 手动启动（开发模式）
jarvis-service start --dev
```

## 注意事项

1. **安全提醒**：
   - SSH密码仅在当前会话中使用，不会持久化存储
   - 建议后续配置SSH密钥认证以提高安全性
   - Node Secret是敏感信息，妥善保管

2. **网络考虑**：
   - 确保远程服务器可以访问GitHub/Gitee
   - 如网络受限，可修改脚本使用内网源

3. **权限考虑**：
   - systemd用户服务需要linger模式支持
   - 如遇权限问题，检查loginctl linger状态
