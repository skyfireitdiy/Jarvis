# 🤖 Jarvis AI 助手
<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[快速开始](#quick-start) • [核心功能](#core-features) • [配置说明](#configuration) • [Jarvis Book](#jarvis-book) • [技术细节](docs/technical_documentation.md) • [Wiki文档](docs/jarvis_book/1.项目介绍.md) • [贡献指南](#contributing) • [许可证](#license)
</div>

---

## 🚀 快速开始 <a id="quick-start"></a>

### 系统要求
- **Linux**: 完全支持。
- **Windows**: 未经充分测试，建议在 [WSL](https://docs.microsoft.com/en-us/windows/wsl/install) 中使用。

### 安装

#### 一键安装 (推荐)
只需一行命令即可完成所有安装和配置：
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh)"
```
> 该脚本会自动检测Python环境、克隆项目、安装依赖并设置好路径。

#### 手动安装
```bash
git clone https://github.com/skyfireitdiy/Jarvis
cd Jarvis
pip3 install -e .
```
或者从PyPI安装 (可能不是最新版):
```bash
pip3 install jarvis-ai-assistant
```

### 基本使用
Jarvis 包含一系列专注于不同任务的工具。以下是主要命令及其快捷方式：

| 命令 | 快捷方式 | 功能描述 |
|------|----------|----------|
| `jarvis` | `jvs` | 通用AI代理，适用于多种任务 |
| `jarvis-code-agent` | `jca` | 专注于代码分析、修改和生成的代码代理 |
| `jarvis-git-commit` | `jgc` | 自动化分析代码变更并生成规范的Git提交信息 |
| `jarvis-platform-manager` | `jpm` | 管理和测试不同的大语言模型平台 |
| `jarvis-rag` | `jrg` | 构建和查询本地化的RAG知识库 |
| `jarvis-smart-shell` | `jss` | 实验性的智能Shell功能 |

更多详细用法和参数，请查阅我们的 [**使用指南**](docs/jarvis_book/4.使用指南.md)。

---

## 🌟 核心功能 <a id="core-features"></a>

- **🆓 零成本接入**: 无缝集成腾讯元宝、Kimi等优质模型，无需支付API费用。
- **🛠️ 工具驱动**: 内置丰富工具集，涵盖脚本执行、代码开发、网页搜索、终端操作等。
- **🤖 人机协作**: 支持实时交互，用户可随时介入指导，确保AI行为符合预期。
- **🔌 高度可扩展**: 支持自定义工具、模型平台和MCP，轻松打造个性化工作流。
- **🧠 RAG 增强**: 内置RAG功能，可将本地文档作为知识库，实现精准问答。

### 视频演示
- [使用`jca`为Jarvis快速扩展功能](https://www.bilibili.com/video/BV1TCgLzvE6Q/)
- [10分钟搭建aarch64容器化Rust开发环境](https://www.bilibili.com/video/BV1K3ghzkEzZ/)
- [`jarvis-code-agent` 功能演示](https://www.bilibili.com/video/BV1KugbzKE6U/)

---

## ⚙️ 配置说明 <a id="configuration"></a>

Jarvis 的主要配置文件位于 `~/.jarvis/config.yaml`。您可以在此文件中配置模型、平台和其他行为。

**基本配置示例 (腾讯元宝):**
```yaml
# ~/.jarvis/config.yaml

# 使用的模型平台
JARVIS_PLATFORM: yuanbao
JARVIS_MODEL: deep_seek_v3

# 用于“思考”步骤的模型，通常选择能力更强的模型
JARVIS_THINKING_PLATFORM: yuanbao
JARVIS_THINKING_MODEL: deep_seek

# 平台所需的环境变量
ENV:
  YUANBAO_COOKIES: "在此处粘贴您的元宝Cookies"
```

Jarvis 支持多种平台，包括 **Kimi**, **通义千问**, **OpenAI** 等。详细的配置选项、模型组设置以及所有可用参数，请参阅 [**使用指南**](docs/jarvis_book/4.使用指南.md)。

> **模型推荐**: 目前效果最好的模型是 `gemini-1.5-pro`，可以通过国内代理商购买，例如 [FoxiAI](https://foxi-ai.top)。

---

## 🛠️ 扩展开发 <a id="extensions"></a>

Jarvis 被设计为高度可扩展的框架。您可以轻松地：
- **添加新工具**: 在 `~/.jarvis/tools/` 目录下创建新的工具实现。
- **集成新LLM平台**: 在 `~/.jarvis/platforms/` 目录下添加新的平台适配器。
- **定义MCP**: 通过配置文件集成外部或自定义的命令协议。

有关扩展开发的详细指南和[**技术细节**](docs/technical_documentation.md)，请访问我们的 [**开发者文档**](docs/jarvis_book/5.功能扩展.md)。

---

## 📖 Jarvis Book <a id="jarvis-book"></a>

欢迎阅读 Jarvis 的官方文档，这本开源书籍旨在为您提供从入门到精通的全方位指南。

- **[第一章：项目介绍](docs/jarvis_book/1.项目介绍.md)**
- **[第二章：快速开始](docs/jarvis_book/2.快速开始.md)**
- **[第三章：核心概念与架构](docs/jarvis_book/3.核心概念与架构.md)**
- **[第四章：使用指南](docs/jarvis_book/4.使用指南.md)**
- **[第五章：功能扩展](docs/jarvis_book/5.功能扩展.md)**
- **[第六章：高级主题](docs/jarvis_book/6.高级主题.md)**
- **[第七章：参与贡献](docs/jarvis_book/7.参与贡献.md)**
- **[第八章：常见问题](docs/jarvis_book/8.常见问题.md)**
- **[第九章：附录](docs/jarvis_book/9.附录.md)**

---

## 🤝 贡献指南 <a id="contributing"></a>

我们欢迎任何形式的贡献！
1. Fork 本仓库
2. 创建您的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

---

## ⚠️ 免责声明 <a id="disclaimer"></a>

- **模型使用风险**: 频繁使用通过非官方API（如腾讯元宝、Kimi、通义千问等）接入的模型可能会导致您的账户被平台封禁。请合理使用，并自行承担相应风险。
- **命令执行风险**: Jarvis具备执行系统命令的能力。请确保您了解将要执行的命令，并避免输入可能导致系统风险的指令。为了增强安全性，您可以在配置文件中启用工具执行确认（`JARVIS_EXECUTE_TOOL_CONFIRM: true`），以便在执行每个工具前进行手动确认。

---

## 📄 许可证 <a id="license"></a>

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---
<div align="center">
由 Jarvis 团队用 ❤️ 制作
</div>

![Jarvis技术支持群](docs/images/wechat.png)
