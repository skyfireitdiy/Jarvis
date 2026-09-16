# 🤖 Jarvis AI 助手

![Jarvis Logo](docs/images/jarvis-logo.svg)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 让 Agent 从「独自工作」走向「与众共事」 🚀

**一句话**：本地运行、开箱即用、可深度定制的**协作式 AI 开发平台**——完整覆盖「单人单 Agent、单人多 Agent、多人单 Agent、多人多 Agent」四种协作模式，写代码、做审查、跑自动化、做安全分析、搞 C→Rust 迁移，一个命令行搞定。

[为什么选 Jarvis](#-为什么选-jarvis) · [协作模式](#协作模式四象限) · [访问方式](#-访问方式) · [核心能力](#-核心能力) · [快速开始](#-快速开始) · [常用命令](#-常用命令) · [文档导航](#-文档导航) · [Python SDK](#-python-sdk-集成) · [系统架构](#-系统架构) · [配置说明](#-配置说明) · [扩展能力](#-扩展能力) · [贡献指南](#-贡献指南)

---

## 👋 Jarvis 是什么？

Jarvis 是一个面向开发者的 **协作式 AI 开发平台**。它不只是对话工具，还能真正进入工作流：读代码、改代码、执行工具、管理上下文、复用经验，并在关键节点保持可控。

它的核心命题是：**让 Agent 从「独自工作」走向「与众共事」**。AI 开发工具的协作能力可以从两个维度交叉分析——**人的维度**（单人 vs 多人）与 **Agent 的维度**（单个 vs 多个），由此得到四种协作模式，Jarvis 完整覆盖全部四种。

如果你希望 AI 不只是“给建议”，而是能在你的本地环境里 **帮助分析、执行、验证和沉淀经验**，Jarvis 就是为这种场景设计的。

![Jarvis 多 Agent 界面](docs/competition/images/多Agent界面.png)

### 适合谁使用？

- 想把 AI 引入日常开发流程的个人开发者
- 想统一代码修改、审查、验证流程的工程团队
- 需要做安全分析、自动化处理、C→Rust 迁移的专项场景用户
- 希望保留本地可控性、避免被单一平台深度绑定的用户

### 协作模式（四象限）

| 协作模式         | 一句话价值       | 核心能力                                                         |
| ---------------- | ---------------- | ---------------------------------------------------------------- |
| **单人单 Agent** | 独当一面         | 符号级代码理解、影响分析、无人值守、交叉 Review、集成终端/编辑器 |
| **单人多 Agent** | 一人驱动一个团队 | 多 Agent 同屏操作、编排网络（devteam）、Agent 间交互、自发群聊   |
| **多人单 Agent** | 团队共享一个 AI  | 多用户认证、ACL 权限、共享协作、聊天室群聊                       |
| **多人多 Agent** | 分布式协作网络   | 多节点多网关、跨节点通信、节点级运维、权限控制                   |

四种模式层层递进：**单人单 Agent 是基础，单人多 Agent 是扩展，多人单 Agent 是共享，多人多 Agent 是终极形态**。主流工具（Claude Code、CodeX、CodeBuddy）聚焦「单人单 Agent」场景，Jarvis 则完整覆盖人 × Agent 两个维度的四种协作模式。

![宠物大厅：多 Agent 同屏协作](docs/competition/images/多Agent界面2.png)

### 核心亮点

- 🏆 **第三届开放原子大赛「智锻代码·开源鸿蒙全球 AI Agent 代码生成挑战赛」总冠军**（99 支报名团队）
- 🤖 **超 1 万次 Agent 自举提交**（2025 年 5795 次 + 2026 年 4524 次，99% 以上由 CodeAgent 自主完成）
- 🏢 **中兴通讯内部深度使用验证**（约 20 人研发协作单元，累计代码开发超 5 万行，超 5 个内部工具以 SDK 方式集成）

详细论述见 [协作模式文档](docs/competition/collaboration_modes.md)。

---

## ✨ 为什么选 Jarvis？

> 不是又一个“聊天机器人”，而是一个 **真正能动手、还能与人共事** 的 AI 伙伴。

- 🎯 **即用即走**：一条命令启动，无需复杂配置，支持一键安装
- 💻 **代码优先**：专为开发者设计，自动 Git、构建验证、静态检查、影响分析
- 🧠 **越用越聪明**：方法论沉淀、记忆分层、规则按需加载，经验可复用
- 🔒 **本地可控**：数据留在本机，支持 Windows GUI 自动化，无 vendor lock-in
- 🔌 **高度可扩展**：自定义工具、MCP 集成、元代理自举、新平台适配，想加就加
- 🤝 **协作共事**：多用户认证、多 Agent 编排、多节点分布式，从个人工具到团队平台

### 与其他方案对比

| 项目            | 定位               | 形态            | 协作模式                | 核心场景                        |
| --------------- | ------------------ | --------------- | ----------------------- | ------------------------------- |
| **Jarvis**      | 协作式 AI 开发平台 | CLI + Web + SDK | 人 × Agent 四象限全覆盖 | 代码开发、安全分析、C→Rust 迁移 |
| **Claude Code** | 代码助手           | CLI             | 单人单 Agent 为主       | 单人编码                        |
| **CodeX**       | 代码助手           | CLI             | 单人单 Agent 为主       | 单人编码                        |
| **CodeBuddy**   | 代码助手           | IDE 插件        | 单用户多 Agent          | 单人编码                        |
| **OpenClaw**    | 个人 AI 助手框架   | Node.js 应用    | 单人/团队共享 Gateway   | 多通道消息、24/7 自主运行       |
| **AutoGen**     | 多 Agent 编排框架  | Python 库       | Agent 间消息传递        | 构建多 Agent 应用               |
| **CrewAI**      | 多 Agent 编排框架  | Python 库       | 角色协作 + 事件驱动     | 构建多 Agent 应用               |

- **Jarvis**：面向代码开发的**协作式平台**，采用分层架构（Agent / CodeAgent），强调本地化、轻量记忆、任务分离、规则按需加载，并支持 Windows GUI 自动化；内置符号数据库 + 影响分析，提供精确的结构化代码理解。
- **Claude Code / CodeX / CodeBuddy**：聚焦「单人单 Agent」场景的代码助手，多 Agent 协作以子代理树状扩展为主，团队协同与跨节点能力有限。
- **OpenClaw**：更偏向消息渠道和日常自动化场景，支持团队共享 Gateway，但无 JWT 认证与 ACL 权限组等细粒度权限控制。
- **AutoGen / CrewAI**：多 Agent 编排**开发框架**，需自行编写 Agent 逻辑搭建应用；Jarvis 则是开箱即用的协作平台。

> 详细对比（含量化性能数据）见 [协作模式文档 · 第四章](docs/competition/collaboration_modes.md)。

### 你可以用它做什么？

- 分析项目结构，生成执行计划
- 修改代码后自动跑验证，减少手工来回切换
- 做安全扫描与报告聚合
- 执行 C→Rust 迁移流水线并支持断点续跑
- 沉淀团队方法论、规则和长期记忆
- 一人驱动多个 Agent 组成开发/测试/部署流水线
- 团队共享同一个 Agent，或搭建跨节点的分布式 Agent 网络
- 通过 CLI、Web 界面或 Python SDK 集成到自己的流程中

---

## 📱 访问方式

Jarvis 提供三种访问方式，满足不同场景需求：

| 方式           | 适用场景             | 说明                                                                 |
| -------------- | -------------------- | -------------------------------------------------------------------- |
| **CLI**        | 终端用户、自动化脚本 | 命令行工具，支持 `jvs`、`jca` 等快捷命令                             |
| **Web**        | 浏览器访问、团队协作 | 通过 `jarvis-service` 启动 Web 网关，支持多节点分布式部署            |
| **Python SDK** | 集成到自有系统       | 以库的形式嵌入，供内部工具调用（见 [Python SDK](#-python-sdk-集成)） |

> 💡 **多用户与协作能力仅通过 Web 接口提供**，CLI 面向单人使用。

### CLI（命令行）

```bash
# 启动通用 Agent
jvs

# 启动代码 Agent
jca

# 启动安全分析
jsec
```

### Web 网关

```bash
# 启动 Web 服务（默认监听 localhost:8000）
jarvis-service

# 指定监听地址和端口
jarvis-service --host 0.0.0.0 --port 9000

# 设置访问密码
jarvis-service --gateway-password your_password
```

启动后在浏览器访问 `http://localhost:8000` 即可使用。

#### 分布式部署

**Master 节点**（主节点，提供统一入口）：

```bash
jarvis-service --node-mode master --gateway-host 0.0.0.0 --gateway-port 8000 --gateway-password your_password
```

**Child 节点**（子节点，运行 Agent）：

```bash
jarvis-service --node-mode child \
    --node-id worker-01 \
    --master-url ws://master-host:8000 \
    --node-secret your_secret_key
```

> 💡 **获取节点密钥**：启动 Master 节点后，可通过前端管理页面的"设置"→"节点连接私钥"获取。Child 节点启动时需要使用相同的密钥。

![节点与 Agent 拓扑视图](docs/competition/images/节点Agent拓扑.png)

详细部署说明见 [分布式网关部署方法](docs/用户手册/04_web_界面与网关/分布式网关部署方法.md)。

#### 多用户与协作

Jarvis 支持完整的多用户认证、权限管理与团队协作能力，适合团队共享使用。

- **多用户认证**：基于 JWT 的认证体系，支持注册/登录/登出，管理员与普通用户角色区分
- **权限管理**：分组权限体系（内置组 + 自定义组）、权限矩阵可视化配置、节点级权限控制、Agent 访问控制（ACL）持久化
- **聊天室协作**：群聊/私聊、在线用户实时同步、未读消息角标、图片发送、聊天记录持久化与清空
- **多用户会话**：多端广播、WebSocket 会话隔离、终端操作与文件上传权限校验

详细说明见 [Web 界面与网关](docs/用户手册/04_web_界面与网关/)。

---

## 🎯 核心能力

| 维度              | 能力                                                                                                              |
| ----------------- | ----------------------------------------------------------------------------------------------------------------- |
| **本地化**        | 可操作本机任意资源（文件、命令、进程等）                                                                          |
| **人机协作**      | 执行前确认、虚拟终端、关键节点可介入，确保过程透明可控                                                            |
| **符号级理解**    | SQLite 符号数据库 + 图遍历，精确回答「改这个函数会影响哪里」（Django 52.4 万行建库 22 秒，find_definition 6.4ms） |
| **影响分析**      | 五类影响（引用/依赖/测试/接口变更/依赖链）+ 风险等级评估                                                          |
| **方法论**        | 成功经验自动沉淀为可复用方法论，支持中心库 Git 共享                                                               |
| **记忆管理**      | 标签化分层（短期 / 项目 / 全局），无向量计算，更轻量                                                              |
| **代码开发**      | 全自动 Git、Worktree 并行、波及分析、交叉引用、上下文推荐、独立 Agent 验证、静态检查、代码格式化、变更后自动处理  |
| **多 Agent 编排** | YAML 声明式编排一键部署 Agent 网络，Agent 间群聊/点对点通信，多面板同屏操作                                       |
| **多人协作**      | JWT 多用户认证、两层权限模型（系统级 + 资源级）、聊天室群聊私聊、共享 Agent                                       |
| **分布式部署**    | 多节点多网关架构、跨节点 Agent 通信、节点级一键更新/重启、拓扑可视化                                              |
| **上下文压缩**    | Git 上下文、任务列表、近期记忆、关键信息、意图识别等多机制，保证任务目标不偏离                                    |
| **任务列表**      | 支线流程与主流程分离，不污染主 Agent 上下文                                                                       |
| **会话管理**      | 自动保存、手动恢复，退出可继续                                                                                    |
| **人格与规则**    | 内置多种人格与开发规则，高效开发兼顾情绪价值                                                                      |
| **规则加载**      | 前期固定流程筛选，后期按需自主加载，确保规则能被有效运用                                                          |
| **工具自举**      | 元代理（meta_agent）根据自然语言生成 / 改进工具并注册，支持自演化                                                 |
| **工具调度**      | 按任务智能筛选工具、工具组切换，支持多工具并行调用（无依赖时）                                                    |
| **智能提示**      | 根据任务优化系统提示词，使 Agent 更贴合当前场景                                                                   |
| **Windows 支持**  | 支持 Windows，可自动化操作 Windows GUI 程序                                                                       |

![变更影响分析](docs/competition/images/变更影响.png)

![多 Agent 编排](docs/competition/images/编排.png)

---

## 🚀 快速开始

> 💡 **30 秒上手**：安装后运行 `jvs` 或 `jca`，按提示配置 API Key，即可开始与 AI 协作开发。

### 系统要求

- **操作系统**：Linux（主要）、Windows 10/11（WSL 或原生，支持 GUI 自动化）
- **Python**：3.12
- **Docker**（可选）：镜像已预装依赖，无需本地 Python / Rust

### 安装

#### 一键安装（推荐）

```bash
# Linux/macOS（GitHub 源）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/quick-install.sh)"

# Linux/macOS（Gitee 源，国内用户加速）
bash -c "$(curl -fsSL https://gitee.com/skyfireitdiy/Jarvis/raw/main/scripts/quick-install.sh)"
```

安装脚本会自动完成以下操作：

- 自动安装 `uv` 包管理器（如果未安装）
- 下载 Jarvis 最新版本源码（浅克隆，减少下载体积）
- 使用 `uv tool install -e . --python 3.12` 安装 Jarvis
- 可选安装增强工具（rg、fd、fzf、tmux、tree）

> 💡 **提示**：新版本采用极简安装方式，不再内置二进制依赖，仓库体积减小约 164MB。安装过程需要网络连接以下载 `uv` 和 Python 依赖。

#### 手动安装

如果您希望手动安装或自定义安装位置：

```bash
# 1. 安装 uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 克隆仓库
git clone --depth 1 https://github.com/skyfireitdiy/Jarvis.git ~/Jarvis
cd ~/Jarvis

# 3. 安装 Jarvis
uv tool install -e . --python 3.12

# 4. 验证安装
jarvis --version
```

#### 升级

```bash
cd ~/Jarvis
git pull
uv tool install -e . --python 3.12
```

#### 手动源码安装

```bash
git clone --depth 1 --branch <latest-tag> https://github.com/skyfireitdiy/Jarvis.git
cd Jarvis
export PATH="$(pwd)/src/jarvis/jarvis_data/deps/x86_64_linux:$PATH"
uv tool install -e . --python 3.12
uv tool install playwright
uv tool install ddgr
```

> Docker 相关说明请参考仓库中的容器/部署文档；主安装入口已统一为“源码下载 + 仓库内置 `uv` + `uv tool` 安装”方式。

### 第一个任务

```bash
# 通用任务：让 AI 帮你分析、规划、执行
jvs -T "分析当前项目结构，找出可优化的依赖关系"

# 代码任务：自动读代码、改代码、跑测试
jca -T "在 user 模块添加忘记密码功能"

# 一键生成规范的 Git 提交信息
jgc
```

---

## 💡 常用命令

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

---

## 📚 文档导航

### 新用户推荐阅读路径

1. **先看 README**：快速判断 Jarvis 是否适合你的场景
2. **再看用户手册**：按任务直接上手 CLI、CodeAgent、平台配置和专项能力
3. **需要系统性理解时再看 Jarvis Book**：了解架构、概念与扩展设计

### 用户手册（推荐新用户优先阅读）

`docs/用户手册` 是更偏“怎么用”的任务型文档，适合首次接触项目的用户快速入门。

- [通用 Agent 手册](docs/用户手册/01_通用_agent/)
- [CodeAgent 手册](docs/用户手册/02_codeagent/)
- [平台与配置](docs/用户手册/03_平台与配置/)
- [Web 界面与网关](docs/用户手册/04_web_界面与网关/)
- [工具与效率](docs/用户手册/05_工具与效率/)
- [专项能力](docs/用户手册/06_专项能力/)

### Jarvis Book（适合系统性阅读）

- [项目介绍](docs/jarvis_book/1.项目介绍.md)
- [快速开始](docs/jarvis_book/2.快速开始.md)
- [核心概念与架构](docs/jarvis_book/3.核心概念与架构.md)
- [使用指南](docs/jarvis_book/4.使用指南.md)
- [功能扩展](docs/jarvis_book/5.功能扩展.md)
- [高级主题](docs/jarvis_book/6.高级主题.md)
- [参与贡献](docs/jarvis_book/7.参与贡献.md)
- [常见问题](docs/jarvis_book/8.常见问题.md)

---

## 🐍 Python SDK 集成

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

## 🏗 系统架构

Jarvis 采用 **分层 + 分布式架构**：单机内以通用 Agent 为核心，通过继承构建 CodeAgent 增强层，再实现专业应用（安全分析、C→Rust 迁移等）；跨机则由多节点多网关组成 Agent 网络，支持跨节点协作。

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

### 分布式部署

多个节点通过网关互联，形成可横向扩展的 Agent 网络：

```mermaid
flowchart TB
    subgraph 网关层["网关层"]
        gw["jarvis-service 网关<br/>JWT 认证 | 权限管理 | 路由"]
    end

    subgraph 节点A["节点 A"]
        a1["Agent 1"]
        a2["Agent 2"]
    end

    subgraph 节点B["节点 B"]
        b1["Agent 3"]
    end

    网关层 -->|调度| 节点A
    网关层 -->|调度| 节点B
    节点A <-->|跨节点 Agent 通信| 节点B
```

### 专业应用

| 应用              | 命令   | 说明                                                                               |
| ----------------- | ------ | ---------------------------------------------------------------------------------- |
| **jarvis-sec**    | `jsec` | 安全分析套件：启发式扫描 → 聚类 → Agent 验证 → 报告聚合，支持 C/C++ 与 Rust        |
| **jarvis-c2rust** | `jc2r` | C→Rust 迁移套件：scan → lib-replace → prepare → transpile → optimize，支持断点续跑 |

### 关键组件

| 组件                                | 用途                                                        |
| ----------------------------------- | ----------------------------------------------------------- |
| **AgentRunLoop**                    | 主运行循环，驱动“模型思考 → 工具执行 → 结果拼接”迭代        |
| **SessionManager**                  | 会话状态管理，支持保存、恢复、清理历史                      |
| **PromptManager**                   | 构建系统提示与附加提示（工具规范、记忆引导等）              |
| **EventBus**                        | 事件总线，关键节点广播，支持旁路扩展                        |
| **ToolRegistry**                    | 工具注册表，发现、加载、执行工具（内置、外部、MCP）         |
| **MemoryManager**                   | 记忆管理，短期 / 项目 / 全局三层架构                        |
| **TaskAnalyzer**                    | 任务分析，满意度收集与方法论沉淀                            |
| **PlatformRegistry / BasePlatform** | 平台适配层，屏蔽不同 LLM 服务商差异                         |
| **RulesManager**                    | 规则管理，多来源加载与激活，与 Skills 标准兼容              |
| **输入处理器链**                    | 内置、Shell、文件上下文处理器，处理特殊标记、命令、文件引用 |

---

## ⚙ 配置说明

配置文件位于 `~/.jarvis/config.yaml`，首次运行将启动交互式配置向导。

### 示例

```yaml
llm_group: default

llm_groups:
  default:
    normal_llm: gpt-5
    fast_llm: gpt-5-mini
  code:
    normal_llm: claude-sonnet

llms:
  gpt-5:
    platform: openai
    model: gpt-5
    max_input_token_count: 128000
    llm_config:
      openai_api_key: "your-api-key-here"
  gpt-5-mini:
    platform: openai
    model: gpt-5-mini
    max_input_token_count: 64000
    llm_config:
      openai_api_key: "your-api-key-here"
  claude-sonnet:
    platform: anthropic
    model: claude-sonnet-4
    max_input_token_count: 128000
    llm_config:
      anthropic_api_key: "your-anthropic-key-here"
```

更多配置项见 [使用指南](docs/jarvis_book/4.使用指南.md)。

---

## 🛠 扩展能力

- **自定义工具**：在 `~/.jarvis/tools/` 下创建并注册，支持中心工具仓库（`central_tool_repo`）团队共享
- **新 LLM 平台**：在 `~/.jarvis/platforms/` 下添加适配器
- **MCP 集成**：通过配置文件接入命令协议

详见 [功能扩展](docs/jarvis_book/5.功能扩展.md)。

---

## 🤝 贡献指南

欢迎一起把 Jarvis 做得更好！无论是修 Bug、加功能、写文档，还是分享使用心得，我们都期待你的参与。

- **GitHub**: [https://github.com/skyfireitdiy/Jarvis.git](https://github.com/skyfireitdiy/Jarvis.git)
- **Gitee**: [https://gitee.com/skyfireitdiy/Jarvis.git](https://gitee.com/skyfireitdiy/Jarvis.git)

参与流程：**Fork 仓库 → 创建分支 → 提交更改 → 发起 Pull Request**

---

## ⚠ 注意事项

- **模型使用**：请遵守各模型平台服务条款，合理使用。
- **命令执行**：Jarvis 具备执行系统命令能力，请谨慎输入；可启用 `execute_tool_confirm: true` 进行执行前确认。

---

## 📄 许可证

MIT 许可证，详见 [LICENSE](LICENSE)。

---

## 如果 Jarvis 对你有帮助，欢迎给个 ⭐ Star

由 Jarvis 团队用 ❤ 制作。
