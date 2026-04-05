# Jarvis AI Assistant - VS Code Extension

Jarvis AI Assistant 是一个强大的 VS Code 扩展，为开发者提供智能 AI 编程助手。它集成了 Agent 侧边栏、聊天面板和终端面板，让 AI 辅助编程更加便捷高效。

## 功能特性

- 🤖 **Agent 侧边栏**：在 VS Code 侧边栏中直接访问 AI Agent，快速获取编程帮助
- 💬 **聊天面板**：与 AI 进行自然语言对话，获取代码建议、问题解答等
- 🖥️ **终端面板**：集成终端功能，支持在编辑器内直接执行命令
- 🎨 **Markdown 渲染**：支持完整的 Markdown 渲染，包括代码高亮
- 📊 **PlantUML 支持**：支持 PlantUML 图表渲染

## 快速开始

1. **打开 Jarvis 面板**
   - 按 `Ctrl+Shift+P`（macOS：`Cmd+Shift+P`）
   - 输入 `Jarvis: Open Panel`
   - 或者点击左侧活动栏的 Jarvis 图标

2. **使用 Agent 侧边栏**
   - 在左侧活动栏找到 Jarvis 图标
   - 点击打开 Agent 列表视图
   - 与 AI Agent 进行交互

3. **开始对话**
   - 在聊天面板中输入您的问题
   - AI 将为您提供代码建议和解答

## 配置说明

### 扩展设置

该扩展目前开箱即用，无需额外配置。

### 连接设置

扩展通过 WebSocket 与 Jarvis 后端服务通信。请确保 Jarvis 服务正在运行。

## 网关服务安装与运行

VSCode 扩展需要 Jarvis 网关服务（jarvis-service）支持才能正常工作。以下是网关服务的安装和启动方法。

### 方式一：通过 pip 安装

```bash
# 安装 Jarvis（包含 jarvis-service）
pip install jarvis-ai-assistant
```

### 方式二：从源码安装

```bash
# 克隆仓库
git clone https://github.com/skyfireitdiy/Jarvis.git
cd Jarvis

# 安装依赖并构建
pip install -e .
```

### 启动网关服务

```bash
# 启动网关服务（默认监听 localhost:8000）
jarvis-service

# 指定监听地址和端口
jarvis-service --host 0.0.0.0 --port 9000

# 设置访问密码
jarvis-service --gateway-password your_password
```

### 验证服务状态

1. 打开浏览器访问 `http://localhost:8000`
2. 如果看到 Jarvis 界面，说明服务启动成功
3. 现在可以打开 VSCode 使用 Jarvis 扩展了

### 常用启动参数

| 参数                 | 说明     | 示例                        |
| -------------------- | -------- | --------------------------- |
| `--host`             | 监听地址 | `--host 0.0.0.0`            |
| `--port`             | 监听端口 | `--port 9000`               |
| `--gateway-password` | 访问密码 | `--gateway-password mypass` |

## 使用示例

### 代码咨询

```text
用户：如何在 Python 中读取文件？
Jarvis：在 Python 中，您可以使用以下方式读取文件...
```

### 代码审查

```text
用户：请帮我审查这段代码
[粘贴代码]
Jarvis：我发现了以下几个问题...
```

## 常见问题

### Q: 扩展无法连接到 Jarvis 服务？

A: 请检查：

1. Jarvis 后端服务是否正在运行
2. WebSocket 连接地址是否正确
3. 防火墙设置是否允许连接

### Q: 如何更新扩展？

A: 下载最新版本的 VSIX 文件，重复安装步骤即可。

## 项目结构

```text
jarvis_vscode_extension/
├── src/
│   ├── extension.ts      # 扩展主入口
│   ├── types/            # TypeScript 类型定义
│   └── webview/          # Webview 相关代码
├── media/                # 静态资源
├── dist/                 # 编译输出
├── package.json          # 扩展配置
└── README.md             # 本文档
```

## 相关链接

- [Jarvis 项目主页](https://github.com/skyfireitdiy/Jarvis)
- [问题反馈](https://github.com/skyfireitdiy/Jarvis/issues)

## 许可证

请参阅项目根目录的 [LICENSE](LICENSE) 文件。

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request
