# Jarvis Docker 部署以及工具使用说明

本文档详细介绍如何使用 Docker 部署 Jarvis 系统，以及各专业工具的使用方法。

## Docker 部署

Jarvis 提供了预构建的 Docker 镜像，已发布到 GitHub Container Registry (GHCR)，**公开可用，无需登录**。镜像已预装所有必需工具（Python 3.12、Rust、Clang、Fish shell 等），开箱即用。

### 从 GitHub Container Registry 拉取镜像

```bash
# 拉取最新版本
docker pull ghcr.io/skyfireitdiy/jarvis:latest
```

### 直接使用 Docker 命令

#### 使用非 root 用户（推荐，避免权限问题）

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

> **提示**:
>
> - `$(pwd)` 可以替换为其他工程目录。
> - `.gitconfig` 文件可以保留 Git 用户信息，方便在容器内使用 Git。
> - `.jarvis` 文件可以保留主机 Jarvis 配置信息，方便在容器内使用 Jarvis。
> - Docker 镜像已预装所有工具（Python 3.12、Rust、Clang、Fish shell 等），开箱即用
> - 容器启动后会自动进入 fish shell，虚拟环境已激活
> - 使用 `-v` 挂载目录可以方便地在容器内处理本地代码
> - **推荐使用非 root 用户**，避免文件权限问题，容器内创建的文件可直接在宿主机访问

---

## 配置说明

### 首次运行配置

首次运行任何 Jarvis 命令时，系统会检测是否缺少配置文件。如果未找到配置，Jarvis 将自动启动交互式配置向导，也可以自己编辑 `~/.jarvis/config.yaml` 文件（建议）。

### 模型配置

编辑 `~/.jarvis/config.yaml` 文件（建议）：

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
```

## 工具使用说明（仅包含与本次大赛相关工具）

| 命令 | 快捷方式 | 功能描述 |
|------|----------|----------|
| `jarvis-code-agent` | `jca` | 专注于代码分析、修改和生成的代码代理，支持智能符号分析 |
| `jarvis-sec` | `jsec` | 安全分析套件，结合启发式扫描和 AI 深度验证，支持 C/C++ 和 Rust 语言 |
| `jarvis-c2rust` | `jc2r` | C→Rust 迁移套件，支持渐进式迁移、断点续跑和智能库替代 |

### jarvis-sec（jsec）安全分析套件

`jarvis-sec` 是一个专业的安全分析套件，采用四阶段流水线设计，结合启发式扫描和 AI 深度验证，支持 C/C++ 和 Rust 语言。

#### 基本用法

对指定目录进行安全分析：

```bash
jarvis-sec --path .
```

#### 参数说明

- `--path` / `-p`：待分析的根目录（默认当前目录）
- `--llm-group` / `-g`：使用的模型组（仅对本次运行生效，不修改全局配置）
- `--output` / `-o`：最终报告输出路径（默认 `./report.md`）。如果后缀为 `.csv`，则输出 CSV 格式；否则输出 Markdown 格式
- `--cluster-limit` / `-c`：聚类每批最多处理的告警数（按文件分批聚类，默认 50）
- `--enable-verification` / `--no-verification`：是否启用二次验证（默认开启）
- `--force-save-memory` / `--no-force-save-memory`：强制使用记忆（默认关闭）

#### 示例

```bash
# 分析当前目录，使用特定模型组
jarvis-sec agent --path . --llm-group gpt-4 --output security_report.md

# 分析指定项目目录，自定义聚类批次大小
jarvis-sec agent --path /path/to/project --cluster-limit 100

# 输出 CSV 格式报告
jarvis-sec agent --path . --output report.csv

# 禁用二次验证（仅进行聚类分析）
jarvis-sec agent --path . --no-verification
```

#### 工作流程

1. **启发式扫描**：纯 Python 本地扫描，生成候选问题列表
2. **聚类**：按文件分组，使用 Agent 进行验证条件一致性聚类
3. **分析**：使用 Agent 执行只读验证，确认真实安全风险
4. **验证**（可选）：使用独立的验证 Agent 进行二次确认，降低误报
5. **报告**：生成 JSON + Markdown/CSV 报告

#### 输出文件

分析结果保存在 `<project_root>/.jarvis/sec/` 目录下：

- `heuristic_issues.jsonl`：直扫候选问题
- `cluster_report.jsonl`：聚类快照
- `agent_issues.jsonl`：验证确认问题
- `progress.jsonl`：进度日志

最终报告会输出到指定的 Markdown 或 CSV 文件（默认 `./report.md`）。

### jarvis-c2rust（jc2r）C→Rust 迁移套件

`jarvis-c2rust` 是一个专业的 C→Rust 迁移套件，实现完整的 C/C++ 代码到 Rust 的自动化迁移流水线，支持渐进式迁移、断点续跑和智能库替代。

#### 命令概览

`jarvis-c2rust` 提供以下子命令：

- `config`：管理配置文件，设置根符号列表、禁用库列表和附加说明
- `run`：执行完整流水线（scan → lib-replace → prepare → transpile → optimize），支持断点续跑

#### 配置管理（config）

管理配置文件（`.jarvis/c2rust/config.json`），设置根符号列表、禁用库列表和附加说明：

```bash
# 从头文件自动提取函数名并设置根符号列表
jarvis-c2rust config --files bzlib.h

# 从多个头文件提取函数名
jarvis-c2rust config --files a.h b.hpp c.hxx

# 从函数名列表文件设置根符号列表
jarvis-c2rust config --files roots.txt

# 从命令行设置根符号列表
jarvis-c2rust config --root-list-syms "func1,func2,func3"

# 设置禁用库列表
jarvis-c2rust config --disabled-libs "libc,libm"

# 设置附加说明（将在所有 agent 的提示词中追加）
jarvis-c2rust config --additional-notes "注意：所有函数必须处理错误情况，避免 panic"

# 同时设置多个参数
jarvis-c2rust config --files bzlib.h --disabled-libs "libc" --additional-notes "特殊要求说明"

# 查看当前配置
jarvis-c2rust config --show

# 清空配置
jarvis-c2rust config --clear
```

**参数说明**：

- `--files <paths...>`：头文件（.h/.hh/.hpp/.hxx）或函数名列表文件（每行一个函数名，忽略空行与以#开头的注释），头文件会自动提取函数名
- `--root-list-syms <str>`：根符号列表内联（逗号分隔）
- `--disabled-libs <str>`：禁用库列表（逗号分隔）
- `--additional-notes <str>`：附加说明（将在所有 agent 的提示词中追加）
- `--show`：显示当前配置内容
- `--clear`：清空配置（重置为默认值）

#### 完整流水线（run）

执行完整迁移流水线，依次执行以下阶段：

1. **scan**：扫描 C/C++ 代码并生成引用依赖图
2. **lib-replace**：评估并应用标准库替代
3. **prepare**：使用 LLM Agent 规划 Rust crate 模块结构
4. **transpile**：转译 C/C++ 代码为 Rust
5. **optimize**：优化生成的 Rust 代码

```bash
jarvis-c2rust run
```

**参数说明**：

- `--llm-group` / `-g`：用于 LLM 相关阶段（lib-replace/prepare/transpile/optimize）的模型组
- `--max-retries` / `-m`：transpile 构建/修复与审查的最大重试次数（0 表示不限制）
- `--interactive`：启用交互模式（默认非交互模式）
- `--reset`：重置状态，从头开始执行所有阶段

**注意**：

- 从配置文件（`.jarvis/c2rust/config.json`）读取 `root_symbols`、`disabled_libraries` 和 `additional_notes`，使用 `config` 命令预先设置
- 根据状态文件（`.jarvis/c2rust/run_state.json`）自动跳过已完成的阶段，支持断点续跑
- 各阶段执行前会自动检查前置依赖，确保流程正确性
- optimize 阶段采用默认优化配置，自动检测 crate 根目录并进行保守优化（unsafe 清理、结构优化、可见性优化、文档补充）

#### 典型使用流程

推荐使用 `run` 命令一键执行完整流水线：

```bash
# 1. 配置根符号列表（推荐先执行）
# 从头文件自动提取函数名
jarvis-c2rust config --files bzlib.h

# 或从命令行设置
jarvis-c2rust config --root-list-syms "main,init,cleanup"

# 设置禁用库列表
jarvis-c2rust config --disabled-libs "libc,libm"

# 设置附加说明（可选）
jarvis-c2rust config --additional-notes "注意：所有函数必须处理错误情况，避免 panic"

# 2. 运行完整流水线
jarvis-c2rust run -g <llm-group>
```

**断点续跑**：如果中途中断，再次运行 `jarvis-c2rust run` 会自动从断点继续，跳过已完成的阶段。使用 `--reset` 可以重置状态，从头开始执行所有阶段。

#### 实际使用案例

以下展示的是本次实际执行的命令，用于将 bzip2 C 代码迁移到 Rust：

```bash
# 1. 配置：从头文件提取函数名，设置根符号，禁用已存在的 Rust 库，添加附加说明
jc2r config \
  --files '/home/skyfire/code/bzip2/bzlib.h' \
  --root-list-syms main \
  --disabled-libs bzip2-rs,bzip2,bzip2-os,bzip2-sys,libbzip2-rs \
  --additional-notes "本次就是要实现rust版本的bzip2，因此任何已经实现的rust版本的bzip2库都不能使用"

# 2. 运行完整流水线
jc2r run -g <llm-group>
```

**说明**：

- 使用 `jc2r` 作为 `jarvis-c2rust` 的简写命令
- `--files` 指定头文件路径，自动提取函数名作为根符号
- `--root-list-syms` 额外指定 `main` 作为根符号
- `--disabled-libs` 禁用所有已存在的 Rust bzip2 库，避免依赖冲突
- `--additional-notes` 添加特殊要求说明，这些说明会被追加到所有 agent 的提示词中
- `run` 命令会自动执行所有阶段，支持断点续跑

### jarvis-code-agent（jca）代码代理

`jarvis-code-agent` 是专注于代码分析、修改和生成的代码代理，支持智能符号分析、上下文感知、波及影响分析等功能。

#### 基本用法

```bash
# 启动代码代理
jarvis-code-agent

# 或使用快捷方式
jca
```

加载规则：

```bash
jca --rule-names tdd,clean_code
```

接下来会进入交互式操作，详细细节，参考 Jarvis Book文档。

#### 主要功能

- **代码分析与修改**：智能分析代码结构，支持代码修改、重构和优化
- **智能符号分析**：自动构建符号表，支持符号查找和依赖分析
- **上下文感知**：自动推荐相关代码上下文，提高代码理解效率
- **波及影响分析**：分析代码修改的影响范围，包括依赖链和接口变更
- **自动化构建验证**：自动检测构建系统，验证代码编译和测试
- **静态检查集成**：集成多种静态分析工具（ruff、mypy、clippy 等）
- **Git 自动管理**：自动管理 Git 仓库，支持检查点和错误恢复
