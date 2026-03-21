# 🤖 Jarvis AI 助手

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### 像钢铁侠的 Jarvis 一样，让你的开发效率飞起来 🚀

**一句话**：本地运行、开箱即用、可深度定制的 AI 开发助手 —— 写代码、做审查、搞迁移，一个命令行搞定。

[快速开始](#-快速开始) · [核心能力](#-核心能力) · [系统架构](#-系统架构) · [Jarvis Book](#-jarvis-book) · [参与贡献](#-贡献指南)

</div>

---

## ✨ 为什么选 Jarvis？

> 不是又一个「聊天机器人」，而是一个**真正能动手**的 AI 伙伴。

- 🎯 **即用即走**：一条命令启动，无需复杂配置，支持一键安装
- 💻 **代码优先**：专为开发者设计，自动 Git、构建验证、静态检查、影响分析
- 🧠 **越用越聪明**：方法论沉淀、记忆分层、规则按需加载，经验可复用
- 🔒 **本地可控**：数据留在本机，支持 Windows GUI 自动化，无 vendor lock-in
- 🔌 **高度可扩展**：自定义工具、MCP 集成、元代理自举、新平台适配，想加就加

## 🎯 核心能力 <a id="core-capabilities"></a>

| 维度             | 能力                                                                                                             |
| ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| **本地化**       | 可操作本机任意资源（文件、命令、进程等）                                                                         |
| **人机协作**     | 执行前确认、虚拟终端、关键节点可介入，确保过程透明可控                                                           |
| **方法论**       | 成功经验自动沉淀为可复用方法论，支持中心库 Git 共享                                                              |
| **记忆管理**     | 标签化分层（短期/项目/全局），无向量计算，更轻量                                                                 |
| **代码开发**     | 全自动 Git、Worktree 并行、波及分析、交叉引用、上下文推荐、独立 Agent 验证、静态检查、代码格式化、变更后自动处理 |
| **上下文压缩**   | Git 上下文、任务列表、近期记忆、关键信息、意图识别等多机制，保证任务目标不偏离                                   |
| **任务列表**     | 支线流程与主流程分离，不污染主 Agent 上下文                                                                      |
| **会话管理**     | 自动保存、手动恢复，退出可继续                                                                                   |
| **人格与规则**   | 内置多种人格与开发规则，高效开发兼顾情绪价值                                                                     |
| **规则加载**     | 前期固定流程筛选，后期按需自主加载，确保规则能被有效运用                                                         |
| **工具自举**     | 元代理（meta_agent）根据自然语言生成/改进工具并注册，支持自演化                                                  |
| **工具调度**     | 按任务智能筛选工具、工具组切换，支持多工具并行调用（无依赖时）                                                   |
| **智能提示**     | 根据任务优化系统提示词，使 Agent 更贴合当前场景                                                                  |
| **Windows 支持** | 支持 Windows，可自动化操作 Windows GUI 程序                                                                      |

### 与其他方案对比

| 项目          | 定位              | 形态             | 核心场景                        |
| ------------- | ----------------- | ---------------- | ------------------------------- |
| **Jarvis**    | AI 助手平台       | CLI + Python SDK | 代码开发、安全分析、C→Rust 迁移 |
| **LangChain** | LLM 应用框架      | Python 库        | 通用 Agent、RAG、工作流编排     |
| **AutoGPT**   | 自主 AI Agent     | 独立应用         | 目标驱动的自主任务执行          |
| **OpenClaw**  | 个人 AI 助手框架  | Node.js 应用     | 多通道消息、24/7 自主运行       |
| **ZeroClaw**  | OpenClaw 轻量替代 | Rust 二进制      | 同 OpenClaw                     |

- **Jarvis**：面向代码开发，分层架构（Agent/CodeAgent），本地化、轻量记忆、任务分离、规则按需加载，支持 Windows GUI 自动化。
- **LangChain**：通用编排框架，1000+ 集成，LangGraph 图编排，侧重生产级 RAG 与工作流，记忆以向量存储为主。
- **AutoGPT**：早期自主 Agent，目标驱动、有会话保存，但易陷入循环、成本较高、任务上下文分离不足。
- **OpenClaw / ZeroClaw**：消息渠道与日常自动化，Skills 兼容，OpenClaw 支持 Windows GUI，ZeroClaw 极致轻量（~3MB）。

---

## 🏗️ 系统架构 <a id="architecture"></a>

Jarvis 采用**分层架构**：以通用 Agent 为核心，通过继承构建 CodeAgent 增强层，再实现专业应用（安全分析、C→Rust 迁移等）。

```mermaid
flowchart TB
    subgraph 专业应用层["专业应用层"]
        jsec["jarvis-sec (jsec) 安全分析"]
        jc2r["jarvis-c2rust (jc2r) C→Rust 迁移"]
    end

    subgraph 功能增强层["功能增强层 CodeAgent"]
        code["代码结构分析 | 文件编辑 | 变更影响分析"]
    end

    subgraph 核心基础层["核心基础层 Agent"]
        agent["对话与工具执行 | 会话管理 | 工具注册 | 平台适配 | 事件总线"]
    end

    专业应用层 -->|使用| 功能增强层
    功能增强层 -->|继承| 核心基础层
```

### 核心基础层：Agent

Jarvis 的核心执行实体，提供对话、工具执行、会话管理等基础能力：统一入口、会话管理、工具注册、平台适配、事件总线与输入/输出处理链，支持非交互模式与多 Agent 编排。

### 功能增强层：CodeAgent

继承自 Agent，叠加代码相关能力：代码结构分析（文件/函数/类层次）、文件编辑（`edit_file` 支持 search/replace 与整文件重写）、变更影响分析（依赖与调用链）、基于构建错误的自动迭代修复。被 jarvis-c2rust 用于代码生成与修复，也可独立使用（`jca`）。

### 专业应用层

| 应用              | 命令   | 说明                                                                               |
| ----------------- | ------ | ---------------------------------------------------------------------------------- |
| **jarvis-sec**    | `jsec` | 安全分析套件：启发式扫描 → 聚类 → Agent 验证 → 报告聚合，支持 C/C++ 与 Rust        |
| **jarvis-c2rust** | `jc2r` | C→Rust 迁移套件：scan → lib-replace → prepare → transpile → optimize，支持断点续跑 |

---

## 🔧 关键组件 <a id="components"></a>

| 组件                                | 用途                                                        |
| ----------------------------------- | ----------------------------------------------------------- |
| **AgentRunLoop**                    | 主运行循环，驱动「模型思考 → 工具执行 → 结果拼接」迭代      |
| **SessionManager**                  | 会话状态管理，支持保存、恢复、清理历史                      |
| **PromptManager**                   | 构建系统提示与附加提示（工具规范、记忆引导等）              |
| **EventBus**                        | 事件总线，关键节点广播，支持旁路扩展                        |
| **ToolRegistry**                    | 工具注册表，发现、加载、执行工具（内置、外部、MCP）         |
| **MemoryManager**                   | 记忆管理，短期/项目/全局三层架构                            |
| **TaskAnalyzer**                    | 任务分析，满意度收集与方法论沉淀                            |
| **PlatformRegistry / BasePlatform** | 平台适配层，屏蔽不同 LLM 服务商差异                         |
| **RulesManager**                    | 规则管理，多来源加载与激活，与 Skills 标准兼容              |
| **输入处理器链**                    | 内置、Shell、文件上下文处理器，处理特殊标记、命令、文件引用 |

---

## 🚀 快速开始 <a id="quick-start"></a>

> 💡 **30 秒上手**：安装后运行 `jvs` 或 `jca`，按提示配置 API Key，即可开始与 AI 协作开发。

### 系统要求

- **操作系统**：Linux（主要）、Windows 10/11（WSL 或原生，支持 GUI 自动化）
- **Python**：3.12
- **Docker**（可选）：镜像已预装依赖，无需本地 Python/Rust

### 安装

**一键安装（推荐）**

```bash
# Linux/macOS
bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh)"

# Windows PowerShell
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.ps1'))
```

**手动安装**

```bash
git clone https://github.com/skyfireitdiy/Jarvis.git
cd Jarvis
pip3 install -e .
```

**Docker**

```bash
docker pull ghcr.io/skyfireitdiy/jarvis:latest
docker-compose run --rm jarvis
```

### 主要命令

| 命令                      | 快捷方式 | 功能                         |
| ------------------------- | -------- | ---------------------------- |
| `jarvis`                  | `jvs`    | 通用 AI 代理                 |
| `jarvis-code-agent`       | `jca`    | 代码代理（分析、修改、生成） |
| `jarvis-sec`              | `jsec`   | 安全分析套件                 |
| `jarvis-c2rust`           | `jc2r`   | C→Rust 迁移套件              |
| `jarvis-git-commit`       | `jgc`    | 自动生成 Git 提交信息        |
| `jarvis-platform-manager` | `jpm`    | 管理大语言模型平台           |
| `jarvis-quick-config`     | `jqc`    | 快速配置工具                 |

完整命令列表见 [使用指南](docs/jarvis_book/4.使用指南.md)。

### 试试这些

```bash
# 通用任务：让 AI 帮你分析、规划、执行
jvs -T "分析当前项目结构，找出可优化的依赖关系"

# 代码任务：自动读代码、改代码、跑测试
jca -T "在 user 模块添加忘记密码功能"

# 一键生成规范的 Git 提交信息
jgc
```

### Python SDK 集成

```python
from jarvis.jarvis_code_agent.code_agent import CodeAgent

agent = CodeAgent()
agent.run('修复 user/service.py 中的登录验证 bug')
```

```python
from jarvis.jarvis_agent import Agent

agent = Agent(system_prompt="你是一个专业的文档维护助手。", name="DocGenerator")
agent.run('分析 README.md，补充用户群体信息')
```

---

## Star History

<a href="https://www.star-history.com/?repos=skyfireitdiy%2FJarvis&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=skyfireitdiy/Jarvis&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=skyfireitdiy/Jarvis&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=skyfireitdiy/Jarvis&type=date&legend=top-left" />
 </picture>
</a>

---

## ⚙️ 配置说明 <a id="configuration"></a>

配置文件位于 `~/.jarvis/config.yaml`，首次运行将启动交互式配置向导。

**示例**

```yaml
llm_group: default

llm_groups:
  default:
    normal_llm: gpt-5

llms:
  gpt-5:
    platform: openai
    model: gpt-5
    max_input_token_count: 128000
    llm_config:
      openai_api_key: "your-api-key-here"
```

更多配置项见 [使用指南](docs/jarvis_book/4.使用指南.md)。

---

## 🛠️ 扩展开发 <a id="extensions"></a>

- **自定义工具**：在 `~/.jarvis/tools/` 下创建并注册，支持中心工具仓库（`central_tool_repo`）团队共享
- **新 LLM 平台**：在 `~/.jarvis/platforms/` 下添加适配器
- **MCP 集成**：通过配置文件接入命令协议

详见 [功能扩展](docs/jarvis_book/5.功能扩展.md)。

---

## 📖 Jarvis Book <a id="jarvis-book"></a>

[项目介绍](docs/jarvis_book/1.项目介绍.md) · [快速开始](docs/jarvis_book/2.快速开始.md) · [核心概念与架构](docs/jarvis_book/3.核心概念与架构.md) · [使用指南](docs/jarvis_book/4.使用指南.md) · [功能扩展](docs/jarvis_book/5.功能扩展.md) · [高级主题](docs/jarvis_book/6.高级主题.md) · [参与贡献](docs/jarvis_book/7.参与贡献.md) · [常见问题](docs/jarvis_book/8.常见问题.md)

---

## 🤝 贡献指南 <a id="contributing"></a>

欢迎一起把 Jarvis 做得更好！无论是修 Bug、加功能、写文档，还是分享使用心得，我们都期待你的参与。

- **GitHub**: https://github.com/skyfireitdiy/Jarvis.git
- **Gitee**: https://gitee.com/skyfireitdiy/Jarvis.git

1. Fork 仓库 → 2. 创建分支 → 3. 提交更改 → 4. 发起 Pull Request

---

## ⚠️ 免责声明 <a id="disclaimer"></a>

- **模型使用**：请遵守各模型平台服务条款，合理使用。
- **命令执行**：Jarvis 具备执行系统命令能力，请谨慎输入；可启用 `execute_tool_confirm: true` 进行执行前确认。

---

## 📄 许可证 <a id="license"></a>

MIT 许可证，详见 [LICENSE](LICENSE)。

---

<div align="center">

**如果 Jarvis 对你有帮助，欢迎给个 ⭐ Star**

由 Jarvis 团队用 ❤️ 制作 · [反馈与讨论](https://github.com/skyfireitdiy/Jarvis/discussions)

</div>
