# Jarvis

基于 Jarvis-Agent 的智能 AI 助手系统，提供安全分析套件（jsec）和 C→Rust 迁移套件（jc2r）等专业应用工具。

## 项目介绍

Jarvis 是一个基于通用 Agent 的智能 AI 助手系统，采用分层架构设计：

- **核心基础层**：通用 Agent，提供对话、工具执行、会话管理等基础能力
- **功能增强层**：CodeAgent（代码分析与修改）、MultiAgent（多智能体协作）
- **专业应用层**：jarvis-sec（安全分析套件）和 jarvis-c2rust（C→Rust 迁移套件）

本项目专注于提供两个专业应用工具：

### jarvis-sec（jsec）

安全分析套件，采用四阶段流水线设计：

1. **启发式扫描**：纯 Python 本地扫描，不依赖外部服务
2. **聚类**：按文件分组，使用 Agent 进行验证条件一致性聚类
3. **分析**：使用 Agent 执行只读验证，确认真实安全风险
4. **报告**：聚合为 JSON + Markdown 报告

### jarvis-c2rust（jc2r）

C→Rust 迁移套件，实现完整的 C/C++ 代码到 Rust 的自动化迁移流水线：

1. **扫描**：分析 C/C++ 代码结构，生成引用依赖图
2. **库替代**：评估标准库替代方案
3. **模块规划**：使用 Agent 规划 Rust crate 模块结构
4. **转译**：使用 CodeAgent 生成 Rust 代码并修复构建错误
5. **优化**：保守优化生成的 Rust 代码

## 系统要求

- **操作系统**：Linux（推荐）或 Windows 10/11（通过 WSL）
- **Python 版本**：Python 3.9 或更高版本（支持 3.9-3.12）
- **Docker**：支持通过 Docker 镜像使用，无需本地安装 Python/Rust 环境

## 安装

### 一键安装（推荐）

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/install.sh)"
```

### 手动安装

#### 从源码安装（获取最新功能）

```bash
# 1. 克隆仓库
git clone https://openatom.tech/codeforge-ai-agent/1f4e9750e7bd1838fb0127f051c18414
cd Jarvis

# 2. 安装项目为可编辑模式
pip3 install -e .
```

#### 通过 PyPI 安装

```bash
pip3 install jarvis-ai-assistant
```

#### 通过 uv 安装（推荐）

```bash
# 1. 安装 uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 使用 uv tool 安装 jarvis（推荐）
# 从比赛仓库安装
uv tool install git+https://openatom.tech/codeforge-ai-agent/1f4e9750e7bd1838fb0127f051c18414
```

> **提示**: `uv tool` 会自动管理工具的虚拟环境，无需手动创建和激活。安装完成后，jarvis 的所有命令（如 `jvs`、`jca`、`jsec`、`jc2r` 等）将立即可用。

#### Docker 镜像安装（推荐用于隔离环境）

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

Docker Compose 配置默认使用**非 root 用户**（当前用户的 UID/GID），避免文件权限问题：

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
  -v $HOME/.jarvis:/home/$(whoami)/.jarvis \
  -v $HOME/.gitconfig:/home/$(whoami)/.gitconfig:ro \
  -w /workspace \
  -e USER=$(whoami) \
  -e HOME=/home/$(whoami) \
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
# 克隆仓库
git clone https://openatom.tech/codeforge-ai-agent/1f4e9750e7bd1838fb0127f051c18414
cd Jarvis

# 构建镜像
docker build -t jarvis:latest .

# 运行容器（非 root 用户，推荐）
docker run -it --rm \
  --user "$(id -u):$(id -g)" \
  -v $(pwd):/workspace \
  -v $HOME/.jarvis:/home/$(whoami)/.jarvis \
  -v $HOME/.gitconfig:/home/$(whoami)/.gitconfig:ro \
  -w /workspace \
  -e USER=$(whoami) \
  -e HOME=/home/$(whoami) \
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
> - Docker 镜像已预装所有工具（Python 3.12、Rust、Clang、Fish shell 等），开箱即用
> - 容器启动后会自动进入 fish shell，虚拟环境已激活
> - 使用 `-v` 挂载目录可以方便地在容器内处理本地代码
> - **推荐使用非 root 用户**，避免文件权限问题，容器内创建的文件可直接在宿主机访问
> - 挂载 `.gitconfig` 可以保留 Git 用户信息，方便在容器内使用 Git
> - 使用 Docker Compose 是最简单的方式，自动处理用户权限配置和文件挂载
> - 推荐直接使用 GHCR 上的预构建镜像，无需本地构建

## 配置

### 首次运行配置

首次运行任何 Jarvis 命令时，系统会检测是否缺少配置文件。如果未找到配置，Jarvis 将自动启动交互式配置向导。

### 手动配置 OpenAI

编辑 `~/.jarvis/config.yaml` 文件：

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

### 验证配置

配置完成后，运行以下命令验证配置是否正确：

```bash
jpm info -p openai
```

如果配置正确，将列出所有可用的模型。

## 使用指南

### jarvis-sec（jsec）安全分析套件

#### 基本用法

对指定目录进行安全分析：

```bash
jarvis-sec --path ./target_project
```

#### 参数说明

- `--path` / `-p`：待分析的根目录（必需）
- `--llm-group` / `-g`：使用的模型组（仅对本次运行生效，不修改全局配置）
- `--output` / `-o`：最终 Markdown 报告输出路径（默认 `./report.md`）
- `--cluster-limit` / `-c`：聚类每批最多处理的告警数（按文件分批聚类，默认 50）

#### 示例

```bash
# 分析当前目录，使用特定模型组
jarvis-sec --path . --llm-group gpt-4 --output security_report.md

# 分析指定项目目录，自定义聚类批次大小
jarvis-sec --path /path/to/project --cluster-limit 100
```

#### 工作流程

1. **启发式扫描**：纯 Python 本地扫描，生成候选问题列表
2. **聚类**：按文件分组，使用 Agent 进行验证条件一致性聚类
3. **分析**：使用 Agent 执行只读验证，确认真实安全风险
4. **报告**：生成 JSON + Markdown 报告

#### 输出文件

分析结果保存在 `<project_root>/.jarvis/sec/` 目录下：

- `heuristic_issues.jsonl`：直扫候选问题
- `cluster_report.jsonl`：聚类快照
- `agent_issues.jsonl`：验证确认问题
- `progress.jsonl`：进度日志

最终报告会输出到指定的 Markdown 文件（默认 `./report.md`）。

### jarvis-c2rust（jc2r）C→Rust 迁移套件

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

参数说明：

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

参数说明：

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
jc2r run
```

**说明**：

- 使用 `jc2r` 作为 `jarvis-c2rust` 的简写命令
- `--files` 指定头文件路径，自动提取函数名作为根符号
- `--root-list-syms` 额外指定 `main` 作为根符号
- `--disabled-libs` 禁用所有已存在的 Rust bzip2 库，避免依赖冲突
- `--additional-notes` 添加特殊要求说明，这些说明会被追加到所有 agent 的提示词中
- `run` 命令会自动执行所有阶段，支持断点续跑

## 相关文件说明

### 技术报告.pdf

初赛交付的技术文档，详细介绍了 Jarvis 系统的架构设计、实现原理和使用方法。

### test_cases 目录

包含各测试案例的扫描分析报告：

- **bzip2**：bzip2 项目的安全扫描分析报告
- **OpenHarmony 相关目录**（如 `commonlibrary_c_utils`、`communication_ipc`、`hiviewdfx_hilog` 等）：OpenHarmony 各模块的安全扫描分析报告

#### test_cases/bzip2_c2rust.7z

bzip2 C 原版源码压缩包，包含以下内容：

- **C 源码**：修改了 Makefile 以集成 Rust FFI 库
- **`.jarvis/c2rust` 目录**：包含完整的转译过程文件，可验证转译流程
- **转译后的 Rust 库**：`bzip2_rs` 库的源码

**解压方法**：

```bash
# 使用 7z 解压
7z x bzip2_c2rust.7z

# 或使用 p7zip
p7zip -d bzip2_c2rust.7z
```

### videos 目录

视频压缩包（分卷压缩），解压后包含以下视频文件：

- **jarvis-sec安全分析套件使用视频.mkv**：演示 jarvis-sec 安全分析套件的使用方法
- **c2rust修复&集成测试视频.mkv**：可直观看到 Agent 的运行过程，包括代码修复和集成测试
- **Jarvis视频介绍.mkv**：Jarvis 系统的整体介绍视频

**分卷压缩文件解压方法**：

```bash
# 方法 1：使用 7z 解压（推荐）
7z x 视频.7z.001

# 方法 2：使用 p7zip
p7zip -d 视频.7z.001

# 方法 3：先合并分卷再解压（适用于不支持分卷的工具）
cat 视频.7z.* > 视频.7z
7z x 视频.7z
```

**注意**：解压分卷压缩文件时，只需指定第一个分卷文件（`.001`），7z 会自动识别并解压所有分卷。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 相关链接

- 仓库地址：[https://openatom.tech/codeforge-ai-agent/1f4e9750e7bd1838fb0127f051c18414](https://openatom.tech/codeforge-ai-agent/1f4e9750e7bd1838fb0127f051c18414)
- 文档：详见 `docs/` 目录
- 案例：详见 `test_cases/` 目录
