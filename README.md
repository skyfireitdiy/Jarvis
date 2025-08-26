# 🤖 Jarvis AI 助手
<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[快速开始](#quick-start) • [核心功能](#core-features) • [配置说明](#configuration) • [Jarvis Book](#jarvis-book) • [Wiki文档](docs/jarvis_book/1.项目介绍.md) • [贡献指南](#contributing) • [许可证](#license)
</div>

---

## 🎯 定位与优势

Jarvis 的定位是**个人开发者的高效助理**，旨在将研发流程中一次性、碎片化的工作变得更加流畅和高效。这与 `workflow` 形式的 `Agent` 平台（如 Dify）有着本质区别，专注于提升个人生产力。

### Jarvis 的核心优势

1.  **访问本地资源**: Jarvis 能够直接与您的本地环境交互，执行诸如**软件开发、代码修复、环境搭建**等需要本地文件系统和工具链的复杂任务。
2.  **纯粹的命令行体验**: 作为一款纯命令行工具，Jarvis 可以无缝集成到您喜爱的任何IDE、终端或SSH会话中，不干扰您现有的工作流程。
3.  **Python包形式提供**: Jarvis 以标准的Python包形式分发，可以轻松地作为依赖项集成到您自己构建的AI应用或自动化脚本中。

### 💡 Jarvis 的价值：工作流对比

#### 示例一：开发新功能

**传统工作流 (没有 Jarvis):**

1.  **理解需求**: 阅读需求文档，在代码库中全局搜索，定位可能需要修改的文件和函数。
2.  **切换上下文**: 在IDE、浏览器（查资料）、终端（执行命令）之间反复切换。
3.  **编写代码**: 手动编写新功能、单元测试和相关文档。
4.  **调试**: 反复运行、打印日志、设置断点来定位和修复bug。
5.  **代码提交**: 手动检查代码变更，撰写符合团队规范的 Git Commit Message。
> 这个过程不仅耗时，而且频繁的上下文切换极易打断心流，消耗大量精力。

**Jarvis 增强工作流:**

1.  **任务启动**: 在项目根目录，用自然语言向 `jca` (代码助理) 描述需求：`jca "为 'user' 模块增加 'profile' 接口，需要包含用户信息查询和更新功能"`。
2.  **AI 分析与编码**:
    *   Jarvis 自动分析代码结构，定位相关文件 (`user/service.py`, `user/controller.py`, `tests/test_user.py`)。
    *   自动生成新接口的代码、必要的单元测试，并提出修改方案。
3.  **人机协作与迭代**:
    *   你审查 AI 生成的代码，并提出修改意见：`"字段名需要用驼峰式"` 或 `"增加一个输入校验"`。
    *   Jarvis 根据反馈快速迭代，更新代码。
4.  **自动化提交**:
    *   完成开发后，执行 `jgc` (Git 提交助理)。
    *   Jarvis 自动分析代码变更，生成一条规范的 Git Commit Message (例如: `feat(user): add user profile api with query and update`)。
> 通过 Jarvis，整个流程从“手动执行”变为了“监督和指导”，开发者可以将精力集中在**架构设计和代码审查**等高价值活动上，而不是繁琐的编码和调试细节。

#### 示例二：用 Jarvis 完善本文档

您正在阅读的这部分文档，其诞生过程本身就是 Jarvis 价值的体现。

1.  **初始指令**: `“在README.md中补充jarvis的用户群体和应用场景等信息”`
2.  **探索与学习**: Jarvis 使用 `fd` 和 `read_code` 工具，分析了 `docs/` 目录下的说明文档，快速学习了项目的核心定位和功能。
3.  **迭代完善**: 根据 “补充用户群体”、“增加工作流对比”、“再增加一个例子” 等一系列追加指令，Jarvis 通过多次 `PATCH` 操作，逐步、精确地将新内容添加到本文档的指定位置。
4.  **人机协作**: 在整个过程中，人类提供高层次的目标和方向，Jarvis 负责具体的探索、总结和代码（文档）修改任务，将一个模糊的想法快速落地为结构清晰的文档。

### Vibe Working: 一种更直觉的工作流

Jarvis 的核心理念与一种新兴的人机协作模式 **"Vibe Working"** (氛围式工作)不谋而合。这个概念源于AI研究者Andrej Karpathy，指的是利用大语言模型（LLM），将人类头脑中模糊、直觉性的想法（即“Vibe”）高效转化为具体的、结构化的成果。

这不再是传统的“指令-执行”模式，而是一种**对话式、迭代式**的共同创造过程。

*   **从一个“感觉”开始**: 传统的自动化需要精确的输入和规则。而使用 Jarvis，你可以从一个模糊的目标开始，比如 `jca "给我写个脚本，监控这个网站的变化"` 或者 `jca "重构 'user' 模块，让它看起来更清爽"`。你提供的是方向和“感觉”，而不是详细的规格书。

*   **迭代中逼近完美**: Jarvis (或其背后的LLM) 会提供一个初步的实现。这个版本可能不完美，但它是一个坚实的起点。接下来，你通过反馈来指导它，比如 `“这个地方的逻辑不对，应该先检查A再处理B”` 或者 `“变量名能再语义化一点吗？”`。通过这种快速的反馈循环，AI的产出将逐步逼近你的真实意图。

*   **人与AI的角色转变**:
    *   **你 (人类)**: 扮演**创意总监、品味判断者和方向引领者**。你负责提供愿景、经验和高层次的判断力，确保最终结果的质量和方向。
    *   **Jarvis (AI)**: 扮演**强大的执行伙伴和灵感催化剂**。它负责处理所有繁重、重复和技术性的细节，并能提供意想不到的解决方案，激发你的新想法。

Jarvis 正是为这种工作流而设计的工具。它通过无缝的命令行集成和强大的本地交互能力，将 "Vibe Working" 从一个抽象概念，变为了开发者触手可及的日常生产力工具，让你能更专注于**高价值的创造性思考**，而非琐碎的实现细节。

### 👥 目标用户

**谁适合使用 Jarvis？**

*   **个人开发者和极客**: 希望通过AI提升个人开发、学习和探索效率的用户。
*   **需要处理碎片化任务的工程师**: 面对各种一次性、非标准化的技术任务，例如快速编写脚本、调试代码、搭建新环境等。
*   **AI应用探索者**: 希望有一个灵活的本地框架来实验和集成不同的大语言模型和工具。

**谁可能不适合？**

*   **寻求固定工作流自动化的人**: 如果您的需求是高度固定和重复的，例如“每天定时抓取数据并生成报告”，那么编写一个专门的、功能单一的脚本可能是更直接、更高效的解决方案。Jarvis 更擅长处理多变和探索性的任务。
*   **企业级团队协作者**: Jarvis 被设计为个人工具，不包含团队管理、权限控制等面向企业级协作的功能。

总之，Jarvis 是为每一位开发者量身打造的个人助手，而非用于团队协作的集中式平台。

---

## 🚀 快速开始 <a id="quick-start"></a>

### 系统要求
- **Linux**: 完全支持。
- **Windows**: 完全支持（需要 PowerShell）。

### 安装

#### 一键安装 (推荐)
只需一行命令即可完成所有安装和配置：

**Linux/macOS:**
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh)"
```

**Windows (PowerShell):**
```powershell
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.ps1'))
```

> 该脚本会自动检测Python环境、克隆项目、安装依赖并设置好路径。

#### 手动安装
```bash
# 1. 克隆仓库
git clone https://github.com/skyfireitdiy/Jarvis

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

# 2. 克隆仓库
git clone https://github.com/skyfireitdiy/Jarvis

# 3. 进入项目目录
cd Jarvis

# 4. 创建虚拟环境并安装
uv venv

# 安装基础功能
uv pip install .

# 可选: 安装RAG功能(包含PyTorch等较重的依赖)
# uv pip install .[rag]
```

> **提示**: 安装完成后，建议将虚拟环境激活命令添加到您的 shell 配置文件中:
> - Bash/Zsh: 在 ~/.bashrc 或 ~/.zshrc 中添加 `source /path/to/Jarvis/.venv/bin/activate`
> - Fish: 在 ~/.config/fish/config.fish 中添加 `source /path/to/Jarvis/.venv/bin/activate.fish`

### 基本使用
Jarvis 包含一系列专注于不同任务的工具。以下是主要命令及其快捷方式：

| 命令 | 快捷方式 | 功能描述 |
|------|----------|----------|
| `jarvis` | `jvs` | 通用AI代理，适用于多种任务 |
| `jarvis-agent` | `ja` | AI代理基础功能，处理会话和任务 |
| `jarvis-code-agent` | `jca` | 专注于代码分析、修改和生成的代码代理 |
| `jarvis-code-review` | `jcr` | 智能代码审查工具 |
| `jarvis-git-commit` | `jgc` | 自动化分析代码变更并生成规范的Git提交信息 |
| `jarvis-git-squash` | `jgs` | Git提交历史整理工具 |
| `jarvis-platform-manager` | `jpm` | 管理和测试不同的大语言模型平台 |
| `jarvis-multi-agent` | `jma` | 多智能体协作系统 |
| `jarvis-tool` | `jt` | 工具管理与调用系统 |
| `jarvis-methodology` | `jm` | 方法论知识库管理 |
| `jarvis-rag` | `jrg` | 构建和查询本地化的RAG知识库 |
| `jarvis-smart-shell` | `jss` | 实验性的智能Shell功能 |
| `jarvis-stats` | `jst` | 通用统计模块，支持记录和可视化任意指标数据 |
| `jarvis-memory-organizer` | `jmo` | 记忆管理工具，支持整理、合并、导入导出记忆 |

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


# 平台所需的环境变量
ENV:
  YUANBAO_COOKIES: "在此处粘贴您的元宝Cookies"
```

提示：错误回溯输出控制
- 默认情况下，当 PrettyOutput 打印错误信息（OutputType.ERROR）时，不会自动打印回溯调用链。
- 如需全局启用错误回溯，请在配置中设置：
```yaml
JARVIS_PRINT_ERROR_TRACEBACK: true
```
- 也可以在单次调用时通过传入 `traceback=True` 临时开启回溯打印。

提示：AI 工具筛选阈值
- 当可用工具数量过多时，可能会干扰模型的决策。Jarvis 支持在可用工具数量超过阈值时，先让 AI 自动筛选相关工具再启动，以专注于本次任务。
- 默认阈值为 30，可在配置中调整：
```yaml
# ~/.jarvis/config.yaml
JARVIS_TOOL_FILTER_THRESHOLD: 30
```

Jarvis 支持多种平台，包括 **Kimi**, **通义千问**, **OpenAI** 等。详细的配置选项、模型组设置以及所有可用参数，请参阅 [**使用指南**](docs/jarvis_book/4.使用指南.md)。

> **模型推荐**: 目前效果较好的模型是 `claude-opus-4-20250514`，可以通过国内代理商购买，例如 [FoxiAI](https://foxi-ai.top)。

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
