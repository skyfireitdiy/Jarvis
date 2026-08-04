---
name: remote-deployment
description: 当需要远程部署Jarvis或配置远程开发环境时触发。每当用户提及"远程部署"、"远程开发"、"远程环境"、"远程配置"、"远程服务器"、"SSH部署"时触发。不触发：仅本地部署（用opensource-deployment规则）；仅讨论远程概念不涉及具体操作。
---

# 远程部署规范

## 连接管理

### SSH连接

- 用SSH密钥认证，避密码登录
- 配SSH配置文件（~/.ssh/config）简连接
- 用SSH隧道转发端口

### 安全连接

- 禁root直接登录
- 用非标准端口降扫描风险
- 配防火墙限访问IP
- 启Fail2Ban防暴力破解

## 环境配置

### 系统准备

- 更系统包
- 装必要工具（git、curl、wget等）
- 配时区与语言环境
- 建部署用户

### 依赖安装

- 装Python环境（pyenv或conda）
- 装Node.js环境（nvm）
- 装Docker与Docker Compose
- 装数据库（PostgreSQL、MySQL、Redis等）

## 部署流程

### 1. 代码传输

- 用git clone或rsync传代码
- 配git hooks实自动部署
- 用CI/CD流水线自动化部署

### 2. 环境变量

- 建.env文件配环境变量
- 用密钥管理服务存敏感信息
- 分开发、测试、生产环境配置

### 3. 服务管理

- 用systemd管服务
- 配日志轮转
- 设监控告警

### 4. 反向代理

- 配Nginx或Caddy为反向代理
- 配SSL证书（Let's Encrypt）
- 设负载均衡

## 检查清单

- [ ] SSH连接配置完成
- [ ] 安全配置完成
- [ ] 系统依赖安装完成
- [ ] 代码已传输
- [ ] 环境变量已配置
- [ ] 服务已启动
- [ ] 反向代理已配置
- [ ] HTTPS已启
- [ ] 监控已配置
