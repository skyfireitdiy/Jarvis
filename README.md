# 🤖 Jarvis AI 助手

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

_您的智能开发和系统交互助手_

[快速开始](#quick-start) • [核心功能](#core-features) • [配置说明](#configuration) • [Jarvis Book](#jarvis-book) • [Wiki文档](docs/jarvis_book/1.项目介绍.md) • [贡献指南](#contributing) • [许可证](#license)

</div>

---

## 🎯 定位与优势

Jarvis 的定位是**AI应用开发SDK**，提供强大而灵活的基础组件，帮助开发者快速构建专业的AI应用。与传统的`workflow`形式Agent平台（如Dify）不同，Jarvis以Python SDK的形式提供，强调可编程性和可扩展性，让开发者能够自由定制AI应用的行为和逻辑。

### Jarvis 的核心优势

1. **强大而灵活的基础组件**: 提供 `Agent` 和 `CodeAgent` 等精心设计的基础组件，开发者可以快速基于这些组件构建专业的AI应用，无需从零开始。
2. **高度可编程的SDK**: 以纯Python SDK形式提供，开发者可以自由组合各种能力，编写符合自己业务逻辑的AI应用，而非受限于固定的工作流。
3. **开箱即用的工具生态**: 内置丰富的工具集（代码分析、文件操作、命令执行等），开发者可以直接使用，也可以轻松扩展自定义工具。

### 💡 Jarvis 的价值：工作流对比

#### 示例一：开发代码分析Agent

**传统开发方式 (没有 Jarvis SDK):**

1. **设计Agent架构**: 从零开始设计Agent的决策流程、工具调用机制、上下文管理等核心模块。
2. **实现工具系统**: 手动实现工具注册、参数解析、结果处理等基础设施。
3. **集成LLM**: 编写代码调用各种大模型API，处理流式输出、错误重试等复杂逻辑。
4. **开发特定能力**: 针对代码分析需求，实现代码解析、符号查找、编辑操作等专门功能。
5. **测试与调试**: 反复测试Agent行为，修复各种边界情况和错误场景。

> 这个过程需要大量时间和精力投入在基础设施开发上，而非核心业务逻辑。

**使用 Jarvis SDK 开发:**

```python
from jarvis.jarvis_code_agent.code_agent import CodeAgent

# 创建CodeAgent实例，内置代码分析、编辑、执行等能力
agent = CodeAgent()

# 让Agent自主完成任务，自动使用内置工具
result = agent.run('为 user/service.py 添加用户profile接口')

# CodeAgent会自动：
# 1. 分析代码结构，定位相关文件
# 2. 使用read_code读取文件内容
# 3. 使用edit_file精确修改代码
# 4. 使用execute_script运行测试
# 5. 验证修改是否成功
```

> 通过 Jarvis SDK，开发者只需几行代码就能构建功能完善的AI应用，将精力集中在**业务逻辑和用户体验**等高价值活动上，而非重复造轮子。

#### 示例二：开发文档生成Agent

基于Jarvis SDK，您可以轻松构建文档生成Agent，自动维护项目文档。

```python
from jarvis import Agent

# 创建文档生成Agent，通过system_prompt定制行为
agent = Agent(
    system_prompt="""你是一个专业的文档维护助手。
能够分析现有文档，并根据指令改进文档内容。
""",
    name="DocGenerator"
)

# 让Agent自主完成文档维护任务
agent.run('分析README.md，补充用户群体和应用场景信息')

# 继续迭代文档
agent.run('在README中增加一个工作流对比示例')

# Agent会自动：
# 1. 使用read_code读取文档内容
# 2. 分析现有结构和风格
# 3. 使用edit_file精确修改文档
# 4. 确保格式和风格一致
```

> 通过简单的SDK调用，就能构建出功能完善的文档生成Agent，将文档维护从手动操作转为自动化流程。

### Vibe Working: 一种更直觉的工作流

Jarvis 的核心理念与一种新兴的人机协作模式 **"Vibe Working"** (氛围式工作)不谋而合。这个概念源于AI研究者Andrej Karpathy，指的是利用大语言模型（LLM），将人类头脑中模糊、直觉性的想法（即“Vibe”）高效转化为具体的、结构化的成果。

这不再是传统的“指令-执行”模式，而是一种**对话式、迭代式**的共同创造过程。

- **从一个“感觉”开始**: 传统的自动化需要精确的输入和规则。而使用 Jarvis，你可以从一个模糊的目标开始，比如 `jca "给我写个脚本，监控这个网站的变化"` 或者 `jca "重构 'user' 模块，让它看起来更清爽"`。你提供的是方向和“感觉”，而不是详细的规格书。

- **迭代中逼近完美**: Jarvis (或其背后的LLM) 会提供一个初步的实现。这个版本可能不完美，但它是一个坚实的起点。接下来，你通过反馈来指导它，比如 `“这个地方的逻辑不对，应该先检查A再处理B”` 或者 `“变量名能再语义化一点吗？”`。通过这种快速的反馈循环，AI的产出将逐步逼近你的真实意图。

- **人与AI的角色转变**:
  - **你 (人类)**: 扮演**创意总监、品味判断者和方向引领者**。你负责提供愿景、经验和高层次的判断力，确保最终结果的质量和方向。
  - **Jarvis (AI)**: 扮演**强大的执行伙伴和灵感催化剂**。它负责处理所有繁重、重复和技术性的细节，并能提供意想不到的解决方案，激发你的新想法。

Jarvis 正是为这种工作流而设计的工具。它通过无缝的命令行集成和强大的本地交互能力，将 "Vibe Working" 从一个抽象概念，变为了开发者触手可及的日常生产力工具，让你能更专注于**高价值的创造性思考**，而非琐碎的实现细节。

### 👥 目标用户

**谁适合使用 Jarvis？**

- **个人开发者和极客**: 希望通过AI提升个人开发、学习和探索效率的用户。
- **需要处理碎片化任务的工程师**: 面对各种一次性、非标准化的技术任务，例如快速编写脚本、调试代码、搭建新环境等。
- **AI应用探索者**: 希望有一个灵活的本地框架来实验和集成不同的大语言模型和工具。

**谁可能不适合？**

- **寻求固定工作流自动化的人**: 如果您的需求是高度固定和重复的，例如“每天定时抓取数据并生成报告”，那么编写一个专门的、功能单一的脚本可能是更直接、更高效的解决方案。Jarvis 更擅长处理多变和探索性的任务。
- **企业级团队协作者**: Jarvis 被设计为个人工具，不包含团队管理、权限控制等面向企业级协作的功能。

总之，Jarvis 是为每一位开发者量身打造的个人助手，而非用于团队协作的集中式平台。

---

## 🚀 快速开始 <a id="quick-start"></a>

### 系统要求

- **操作系统**: Jarvis 的许多核心工具依赖于Linux环境，因此目前主要支持在 **Linux** 系统下使用。
- **Windows用户**: 虽然未经原生测试，但 Windows 10/11 用户可以通过 **WSL (Windows Subsystem for Linux)** 来完整地体验 Jarvis 的所有功能。
- **Python版本**: 需要 Python 3.9 或更高版本（支持 3.9-3.12）。
- **Docker**（可选）: 支持通过 Docker 镜像使用，无需本地安装 Python/Rust 环境。

### 安装

#### 一键安装 (推荐)

只需一行命令即可完成所有安装和配置：

**Linux/macOS:**

```bash
# GitHub（推荐）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh)"

# 或者使用 Gitee 镜像（国内访问更快）
bash -c "$(curl -fsSL https://gitee.com/skyfireitdiy/Jarvis/raw/main/scripts/install.sh)"
```

**Windows (PowerShell):**

```powershell
# GitHub（推荐）
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.ps1'))

# 或者使用 Gitee 镜像（国内访问更快）
iex ((New-Object System.Net.WebClient).DownloadString('https://gitee.com/skyfireitdiy/Jarvis/raw/main/scripts/install.ps1'))
```

> 该脚本会自动检测Python环境、克隆项目、安装依赖并设置好路径。

#### 手动安装

```bash
# 1. 克隆仓库（选择以下任一方式）
# GitHub（推荐）
git clone https://github.com/skyfireitdiy/Jarvis.git

# 或者使用 Gitee 镜像（国内访问更快）
git clone https://gitee.com/skyfireitdiy/Jarvis.git

# 2. 进入项目目录
cd Jarvis

# 3. 安装项目为可编辑模式
pip3 install -e .
```

> **提示**: 使用 `-e .` (可编辑模式) 安装后，您对源码的任何修改都会立刻生效，非常适合开发者。

或者从PyPI安装 (可能不是最新版):

```bash
pip3 install jarvis-ai-assistant
```

**通过 uv 安装 (推荐)**

```bash
# 1. 安装 uv (如果未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 使用 uv tool 安装 jarvis（推荐）
# 从 GitHub 仓库安装
uv tool install git+https://github.com/skyfireitdiy/Jarvis.git

# 或从 Gitee 镜像安装（国内访问更快）
# uv tool install git+https://gitee.com/skyfireitdiy/Jarvis.git
```

> **提示**: `uv tool` 会自动管理工具的虚拟环境，无需手动创建和激活。安装完成后，jarvis 的所有命令（如 `jvs`、`jca` 等）将立即可用。

#### Docker 镜像安装 (推荐用于隔离环境)

使用 Docker 镜像可以避免本地环境配置，所有依赖都已预装。镜像已发布到 GitHub Container Registry (GHCR)，**公开可用，无需登录**。

**从 GitHub Container Registry 拉取镜像：**

```bash
# 拉取最新版本
docker pull ghcr.io/skyfireitdiy/jarvis:latest

# 或拉取特定版本（例如 v1.0.0）
docker pull ghcr.io/skyfireitdiy/jarvis:v1.0.0
```

> **提示**:
>
> - 镜像默认公开，无需登录即可拉取
> - 每次发布新版本时，会自动生成多个标签：`latest`、`v1.0.0`、`1.0`、`1` 等
> - 建议使用 `latest` 标签获取最新版本

**使用 Docker Compose（推荐）：**

Docker Compose 配置默认使用**非 root 用户**（jarvis 用户，UID 1000），避免文件权限问题：

```bash
# 运行容器（使用预构建镜像，无需本地构建）
docker-compose run --rm jarvis
```

> **说明**:
>
> - 容器使用 jarvis 用户（UID 1000）运行，GID 可通过环境变量 `GID` 设置（默认 1000），建议设置为当前用户的组 ID 以避免文件权限问题
> - 容器内创建的文件将属于 jarvis 用户，如果 GID 匹配宿主机组，外部可以直接访问，无需调整权限
> - 配置文件（`.jarvis` 和 `.gitconfig`）会自动挂载到容器内用户的主目录

**直接使用 Docker 命令：**

**使用非 root 用户（推荐，避免权限问题）：**

```bash
# 使用当前用户运行（推荐）
docker run -it --rm \
  --user "$(id -u):$(id -g)" \
  -v $(pwd):/workspace \
  -v $HOME/.jarvis:/home/jarvis/.jarvis \
  -v $HOME/.gitconfig:/home/jarvis/.gitconfig:ro \
  -w /workspace \
  ghcr.io/skyfireitdiy/jarvis:latest
```

**使用 root 用户（简单但不推荐，可能产生权限问题）：**

```bash
# 基本运行（root 用户）
docker run -it --rm ghcr.io/skyfireitdiy/jarvis:latest

# 挂载当前目录到容器（root 用户）
docker run -it --rm \
  -v $(pwd):/workspace \
  -v $HOME/.jarvis:/root/.jarvis \
  -v $HOME/.gitconfig:/root/.gitconfig:ro \
  -w /workspace \
  ghcr.io/skyfireitdiy/jarvis:latest
```

> **注意**：使用 root 用户时，容器内创建的文件将属于 root，在宿主机上可能需要使用 `sudo` 或调整文件权限。

**本地构建镜像（可选）：**

```bash
# 克隆仓库（选择以下任一方式）
# GitHub（推荐）
git clone https://github.com/skyfireitdiy/Jarvis.git

# 或者使用 Gitee 镜像（国内访问更快）
git clone https://gitee.com/skyfireitdiy/Jarvis.git

cd Jarvis

# 构建镜像
docker build -t jarvis:latest .

# 运行容器（非 root 用户，推荐）
docker run -it --rm \
  --user "$(id -u):$(id -g)" \
  -v $(pwd):/workspace \
  -v $HOME/.jarvis:/home/jarvis/.jarvis \
  -v $HOME/.gitconfig:/home/jarvis/.gitconfig:ro \
  -w /workspace \
  jarvis:latest

# 或使用 root 用户
docker run -it --rm \
  -v $(pwd):/workspace \
  -v $HOME/.jarvis:/root/.jarvis \
  -v $HOME/.gitconfig:/root/.gitconfig:ro \
  -w /workspace \
  jarvis:latest
```

> **提示**:
>
> - `$(pwd)` 可以替换为其他工程目录
> - `.gitconfig` 文件可以保留 Git 用户信息，方便在容器内使用 Git
> - `.jarvis` 文件可以保留主机 Jarvis 配置信息，方便在容器内使用 Jarvis
> - Docker 镜像已预装所有工具（Python 3.12、Rust、Clang、Fish shell 等），开箱即用
> - 容器启动后会自动进入 fish shell，虚拟环境已激活
> - 使用 `-v` 挂载目录可以方便地在容器内处理本地代码
> - **推荐使用非 root 用户**，避免文件权限问题，容器内创建的文件可直接在宿主机访问
> - 使用 Docker Compose 是最简单的方式，自动处理用户权限配置和文件挂载
> - 推荐直接使用 GHCR 上的预构建镜像，无需本地构建

### 基本使用

Jarvis 包含一系列专注于不同任务的工具。以下是主要命令及其快捷方式：

| 命令                           | 快捷方式 | 功能描述                                                                 |
| ------------------------------ | -------- | ------------------------------------------------------------------------ |
| `jarvis`                       | `jvs`    | 通用AI代理，适用于多种任务（支持 -f/-c/-T/-g/-n 等参数）                 |
| `jarvis-agent-dispatcher`      | `jvsd`   | jvs 的便捷封装，支持任务派发和交互模式                                   |
| `jarvis-agent`                 | `ja`     | AI代理基础功能，处理会话和任务                                           |
| `jarvis-code-agent`            | `jca`    | 专注于代码分析、修改和生成的代码代理（支持 -g/-G/-f/-T/-n/-w/-d 等参数） |
| `jarvis-code-agent-dispatcher` | `jcad`   | jca 的便捷封装，支持任务派发和交互模式                                   |
| `jarvis-code-review`           | `jcr`    | 智能代码审查工具                                                         |
| `jarvis-git-commit`            | `jgc`    | 自动化分析代码变更并生成规范的Git提交信息                                |
| `jarvis-git-squash`            | `jgs`    | Git提交历史整理工具                                                      |
| `jarvis-platform-manager`      | `jpm`    | 管理和测试不同的大语言模型平台                                           |
| `jarvis-multi-agent`           | `jma`    | 多智能体协作系统                                                         |
| `jarvis-tool`                  | `jt`     | 工具管理与调用系统                                                       |
| `jarvis-methodology`           | `jm`     | 方法论知识库管理                                                         |
| `jarvis-rag`                   | `jrg`    | 构建和查询本地化的RAG知识库                                              |
| `jarvis-smart-shell`           | `jss`    | 实验性的智能Shell功能                                                    |
| `jarvis-stats`                 | `jst`    | 通用统计模块，支持记录和可视化任意指标数据                               |
| `jarvis-memory-organizer`      | `jmo`    | 记忆管理工具，支持整理、合并、导入导出记忆                               |
| `jarvis-sec`                   | `jsec`   | 安全分析套件，结合启发式扫描和 AI 深度验证，支持 C/C++ 和 Rust 语言      |
| `jarvis-c2rust`                | `jc2r`   | C→Rust 迁移套件，支持渐进式迁移、断点续跑和智能库替代                    |
| `jarvis-config`                | `jcfg`   | 配置管理工具，基于 JSON Schema 动态生成配置 Web 页面，提供可视化配置界面 |
| `jarvis-quick-config`          | `jqc`    | 快速配置 LLM 平台信息（Claude/OpenAI）到 Jarvis 配置文件的 llms 部分     |

更多详细用法和参数，请查阅我们的 [**使用指南**](docs/jarvis_book/4.使用指南.md)。

### SDK 快速开始

Jarvis SDK 可以轻松集成到您的 Python 项目中。以下是一些快速上手的示例：

#### 使用 CodeAgent 处理代码任务

```python
from jarvis.jarvis_code_agent.code_agent import CodeAgent

# 创建 CodeAgent
agent = CodeAgent()

# 执行代码修改任务
agent.run('修复 user/service.py 中的登录验证 bug')
```

#### 使用 Agent 构建专用应用

```python
from jarvis import Agent

# 创建定制化的 Agent
agent = Agent(
    system_prompt="你是一个数据分析师，专注于数据清洗和可视化。",
    name="DataAnalyst"
)

# 执行数据分析任务
agent.run('分析 sales.csv 数据，生成月度销售趋势图')
```

#### 在 Python 脚本中使用

```python
from jarvis.jarvis_code_agent.code_agent import CodeAgent
import os

# 设置工作目录
os.chdir('/path/to/your/project')

# 创建并运行 Agent
agent = CodeAgent()
result = agent.run('优化代码性能，减少数据库查询次数')

print(f"任务完成: {result}")
```

> 💡 更多 SDK 使用示例和高级用法，请参阅 [开发者文档](docs/jarvis_book/)

---

## 🌟 核心功能 <a id="core-features"></a>

Jarvis SDK 提供强大的基础组件和可扩展能力，帮助开发者快速构建专业的AI应用。

### 基础组件

- **Agent (通用AI代理)**: 提供完整的任务执行能力，支持工具调用、记忆管理、任务规划等核心功能。开发者只需通过 system_prompt 定义行为，即可快速定制专用Agent。
- **CodeAgent (代码专用代理)**: 继承自 Agent，专为代码任务优化。内置代码分析、符号查找、精确编辑、构建验证等专业能力，大幅简化代码类AI应用的开发。

### 工具系统

- **丰富内置工具**: SDK内置 `read_code`、`edit_file`、`execute_script` 等30+工具，覆盖文件操作、代码分析、命令执行等常见场景。
- **轻松扩展自定义工具**: 通过简单接口即可添加自定义工具，无缝集成到Agent的工具链中，实现个性化能力扩展。

### 能力模块

- **记忆系统**: 三层记忆架构（短期、项目长期、全局长期），支持知识持久化和智能检索，让Agent能够记住并复用关键信息。
- **RAG增强**: 内置RAG功能，可将本地文档作为知识库，实现精准的上下文增强和问答。
- **方法论系统**: 将成功经验沉淀为可复用的方法论，支持本地和中心化共享，提升任务执行效率。

### 可扩展性

- **多模型支持**: 支持腾讯元宝、Kimi、OpenAI等多种模型平台，可根据需求灵活切换。
- **自定义模型平台**: 提供统一的平台接口，开发者可轻松集成新的LLM提供商。

### 专业套件

- **安全分析**: 内置安全扫描套件（jsec），支持启发式扫描和AI深度验证，适用于C/C++和Rust语言。
- **代码迁移**: C→Rust迁移套件（jc2r），支持渐进式迁移和断点续跑。
- **代码审查**: 智能代码审查工具，自动化检查代码质量和潜在问题。

---

## ⚙️ 配置说明 <a id="configuration"></a>

Jarvis 的主要配置文件位于 `~/.jarvis/config.yaml`。您可以在此文件中配置模型、平台和其他行为。

**首次运行配置：**

首次运行任何 Jarvis 命令时，系统会检测是否缺少配置文件。如果未找到配置，Jarvis 将自动启动交互式配置向导，引导您完成所有必要设置。

**基本配置示例（推荐使用新的配置方式）：**

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/docs/schema/config.schema.json

# ====== 基础配置 ======
# 设置默认使用的模型组
llm_group: default

# ====== 模型组配置 ======
# 可以定义多个模型组，通过llm_group切换
llm_groups:
  default: # 默认模型组
    normal_llm: gpt-5 # 引用下面llms中定义的模型
    # 可选配置廉价模型和智能模型
    # cheap_llm: gpt-3.5-turbo
    # smart_llm: gpt-5

# ====== 模型定义 ======
llms:
  gpt-5:
    platform: openai # 平台类型
    model: gpt-5 # 模型名称
    max_input_token_count: 128000 # 模型最大输入token数

    # 模型特定配置 (llm_config)
    llm_config:
      openai_api_key: "your-api-key-here" # 替换为你的API密钥
      openai_api_base: "https://api.openai.com/v1" # API基础地址，可用于代理
      openai_extra_headers: '{"X-Source": "jarvis"}' # 额外的HTTP头（可选）

# ====== 环境变量配置 ======
# 旧版配置方式（仍支持，但推荐使用上面的 llm_config）
ENV:
  # 腾讯元宝
  YUANBAO_COOKIES: "在此处粘贴您的元宝Cookies"

  # Kimi
  KIMI_API_KEY: ""

  # 通义千问
  TONGYI_COOKIES: ""

  # OpenAI
  OPENAI_API_KEY: ""
  OPENAI_API_BASE: ""
```

> **注意**: 新版本推荐使用 `llm_groups` 和 `llms` 配置方式，它提供了更灵活的模型管理能力。`ENV` 配置方式仍然支持，但建议迁移到新的配置方式。

提示：错误回溯输出控制

- 默认情况下，当 PrettyOutput 打印错误信息（OutputType.ERROR）时，不会自动打印回溯调用链。
- 如需全局启用错误回溯，请在配置中设置：

```yaml
print_error_traceback: true
```

- 也可以在单次调用时通过传入 `traceback=True` 临时开启回溯打印。

提示：AI 工具筛选阈值

- 当可用工具数量过多时，可能会干扰模型的决策。Jarvis 支持在可用工具数量超过阈值时，先让 AI 自动筛选相关工具再启动，以专注于本次任务。
- 默认阈值为 30，可在配置中调整：

```yaml
# ~/.jarvis/config.yaml
tool_filter_threshold: 30
```

Jarvis 支持多种平台，包括 **Kimi**, **通义千问**, **OpenAI** 等。详细的配置选项、模型组设置以及所有可用参数，请参阅 [**使用指南**](docs/jarvis_book/4.使用指南.md)。

> **模型推荐**: 目前效果较好的模型是 `claude-opus-4-20250514`，可以通过国内代理商购买，例如 [FoxiAI](https://foxi-ai.top)。

---

## 🛠️ 扩展开发 <a id="extensions"></a>

Jarvis SDK 提供强大的可扩展能力，让您能够快速开发专业的AI应用。

### 快速开发专业Agent

基于 `Agent` 和 `CodeAgent` 基础组件，您可以快速构建各种专业Agent：

- **文档助手**: 基于 Agent 定制 system_prompt，实现文档生成、维护和优化
- **代码分析器**: 基于 CodeAgent，利用内置代码分析能力，快速构建代码审查、重构工具
- **自动化测试**: 集成测试工具，自动化执行测试用例并分析结果
- **数据处理**: 扩展数据处理工具，实现自动化数据清洗、转换和分析

### 扩展能力

- **自定义工具**: 在 `~/.jarvis/tools/` 目录下创建新的工具实现，无缝集成到Agent
- **集成新LLM平台**: 在 `~/.jarvis/platforms/` 目录下添加新的平台适配器
- **定义MCP**: 通过配置文件集成外部或自定义的命令协议

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

Jarvis 在 GitHub 和 Gitee 都有镜像仓库，您可以选择其中任一平台进行贡献：

- **GitHub**: https://github.com/skyfireitdiy/Jarvis.git
- **Gitee**: https://gitee.com/skyfireitdiy/Jarvis.git

1. Fork 本仓库（选择您偏好的平台）
2. 创建您的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

---

## ⚠️ 免责声明 <a id="disclaimer"></a>

- **模型使用风险**: 频繁使用通过非官方API（如腾讯元宝、Kimi、通义千问等）接入的模型可能会导致您的账户被平台封禁。请合理使用，并自行承担相应风险。
- **命令执行风险**: Jarvis具备执行系统命令的能力。请确保您了解将要执行的命令，并避免输入可能导致系统风险的指令。为了增强安全性，您可以在配置文件中启用工具执行确认（`execute_tool_confirm: true`），以便在执行每个工具前进行手动确认。

---

## 📄 许可证 <a id="license"></a>

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

<div align="center">
由 Jarvis 团队用 ❤️ 制作
</div>

![Jarvis技术支持群](docs/images/wechat.png)
