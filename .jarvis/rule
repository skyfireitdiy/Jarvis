# 项目综述

## 项目概述

**项目名称**: Jarvis AI Assistant  
**版本**: 3.1.2  
**定位**: 本地运行、开箱即用、可深度定制的 AI 开发助手平台  
**目标用户**: 个人开发者、工程团队、专项场景用户

### 核心能力
- 分析项目结构，生成执行计划
- 修改代码后自动验证（Git、构建、静态检查、影响分析）
- 安全扫描与报告聚合
- C→Rust 迁移流水线
- 方法论沉淀、记忆分层、规则按需加载
- 支持 CLI、Web、VSCode 三种访问方式

## 技术栈

### 编程语言
- **Python**: 3.12 (严格要求)

### 核心框架
- **FastAPI**: 0.115.12 (Web 服务框架)
- **Uvicorn**: 0.33.0 (ASGI 服务器)
- **OpenAI SDK**: 1.78.1 (AI 模型调用)
- **Anthropic SDK**: >=0.40.0 (Claude 模型支持)

### 关键依赖
- **代码解析**: tree-sitter 系列 (支持 JS/TS/Rust/Go/Java/C/C++/Python/HTML/CSS/SQL/YAML/Markdown 等)
- **终端UI**: prompt_toolkit, pygments, rich, pyte
- **Web抓取**: playwright, beautifulsoup4, lxml, markdownify
- **文本处理**: tiktoken, jieba, fuzzywuzzy, python-Levenshtein
- **代码检查**: ruff, bandit, python-lsp-server
- **测试**: pytest, pytest-xdist, pytest-asyncio

## 目录结构

```
Jarvis/
├── src/jarvis/                    # 核心源码
│   ├── jarvis_agent/             # 主Agent模块（122KB核心文件）
│   │   ├── jarvis.py             # Jarvis主类
│   │   ├── run_loop.py           # 运行循环
│   │   ├── session_manager.py    # 会话管理
│   │   ├── rules_manager.py      # 规则管理
│   │   ├── task_list.py          # 任务列表
│   │   ├── tool_executor.py      # 工具执行器
│   │   ├── builtin_input_handler.py  # 内置输入处理
│   │   ├── prompts.py            # 提示词模板
│   │   └── language_support_info.py  # 语言支持信息
│   ├── jarvis_code_agent/        # 代码Agent模块
│   │   ├── code_agent.py         # 代码Agent核心（76KB）
│   │   ├── code_reviewer.py       # 代码审查
│   │   ├── code_analyzer/        # 代码分析器
│   │   ├── diff_visualizer.py    # 差异可视化
│   │   └── worktree_manager.py   # Git worktree管理
│   ├── jarvis_tools/             # 工具集（54KB注册器）
│   │   ├── registry.py            # 工具注册中心
│   │   ├── edit_file.py           # 文件编辑
│   │   ├── execute_script.py      # 脚本执行
│   │   ├── read_code.py           # 代码读取
│   │   ├── task_list_manager.py   # 任务列表管理（106KB）
│   │   └── memory.py              # 记忆管理
│   ├── jarvis_tui/               # 终端UI模块
│   ├── jarvis_service/           # Web服务模块
│   ├── jarvis_vscode_extension/  # VSCode插件
│   ├── jarvis_browser/           # 浏览器自动化
│   ├── jarvis_c2rust/            # C→Rust迁移
│   ├── jarvis_mcp/                # MCP协议集成
│   ├── jarvis_config/             # 配置管理
│   └── jarvis_memory_organizer/   # 记忆组织器
├── tests/                        # 测试目录
│   ├── jarvis_agent/
│   ├── jarvis_code_agent/
│   ├── jarvis_tools/
│   └── performance/
├── builtin/rules/                # 内置规则
│   ├── development_workflow/      # 开发工作流
│   ├── code_quality/             # 代码质量
│   ├── security/                 # 安全
│   └── architecture_design/      # 架构设计
├── .jarvis/                      # Jarvis配置目录
│   ├── rule/                     # 项目规则文件
│   ├── memory/                   # 记忆存储
│   ├── sessions/                 # 会话存储
│   └── symbol_cache/             # 符号缓存
├── docs/                         # 文档
├── frontend/                     # 前端代码
├── pyproject.toml                # 项目配置
├── setup.py                      # 安装脚本
├── Dockerfile                    # Docker镜像
└── docker-compose.yml            # Docker编排
```

## 核心模块

### jarvis_agent (主Agent模块)
- **职责**: 核心Agent逻辑、会话管理、规则加载、任务调度
- **关键文件**:
  - `jarvis.py`: Jarvis主类，入口点
  - `run_loop.py`: 主运行循环，处理用户输入
  - `session_manager.py`: 会话生命周期管理
  - `rules_manager.py`: 规则加载与匹配
  - `builtin_input_handler.py`: 内置输入处理逻辑
- **依赖**: jarvis_tools, jarvis_code_agent

### jarvis_code_agent (代码Agent模块)
- **职责**: 代码修改、审查、构建验证、Lint检查
- **关键文件**:
  - `code_agent.py`: 代码Agent核心实现
  - `code_reviewer.py`: 自动代码审查
  - `code_agent_build.py`: 构建验证
  - `code_agent_lint.py`: Lint检查集成
  - `code_agent_diff.py`: Diff生成与处理
- **依赖**: tree-sitter系列, ruff, bandit

### jarvis_tools (工具集)
- **职责**: 提供Agent可调用的所有工具
- **关键文件**:
  - `registry.py`: 工具注册中心（管理所有工具）
  - `edit_file.py`: 文件编辑工具
  - `execute_script.py`: 脚本执行工具
  - `read_code.py`: 代码读取与符号分析
  - `task_list_manager.py`: 复杂任务拆分与执行
  - `memory.py`: 长期/短期记忆管理
  - `load_rule.py`: 规则加载工具
  - `symbol_dependency.py`: 符号依赖分析

### jarvis_service (Web服务)
- **职责**: 提供HTTP API访问方式，支持分布式部署
- **入口**: `jarvis-service start`
- **依赖**: FastAPI, Uvicorn, WebSockets

### jarvis_vscode_extension (VSCode插件)
- **职责**: IDE集成，Agent侧边栏、聊天面板、终端
- **关键文件**: `jarvis_vscode_extension/` 目录

## 构建与运行

### 安装
```bash
pip install -e .                    # 开发模式安装
pip install -e ".[browser]"        # 带浏览器支持
```

### 运行
```bash
# CLI模式
jarvis                              # 或 jvs
jarvis-code-agent                   # 或 jca

# Web服务模式
jarvis-service start

# Docker模式
docker-compose up -d

# 或使用启动脚本
./start.sh
```

### 环境要求
- Python: 3.12 (严格要求)
- 系统: Linux (主要), Windows (部分支持)
- 可选: Playwright浏览器、Clang编译器

## 测试

### 测试框架
- **pytest**: 主测试框架
- **pytest-xdist**: 并行测试
- **pytest-asyncio**: 异步测试支持

### 运行测试
```bash
pytest tests/                        # 运行所有测试
pytest tests/jarvis_agent/          # 运行特定模块测试
pytest -n auto                     # 并行运行
pytest --cov=src/jarvis            # 带覆盖率
```

### 测试目录结构
```
tests/
├── jarvis_agent/                   # Agent测试
├── jarvis_code_agent/              # 代码Agent测试
├── jarvis_tools/                   # 工具测试
├── jarvis_c2rust/                  # C→Rust迁移测试
├── jarvis_memory_organizer/         # 记忆组织器测试
├── performance/                    # 性能测试
├── regression/                     # 回归测试
└── security/                      # 安全测试
```

## 关键配置

### 配置文件
- `pyproject.toml`: 项目元数据、依赖管理
- `.jarvis/build_validation_config.yaml`: 构建验证配置
- `.jarvis/rules/`: 项目规则目录
- `.jarvis/methodologies/`: 方法论目录

### 环境变量
- `OPENAI_API_KEY`: OpenAI API密钥
- `ANTHROPIC_API_KEY`: Anthropic API密钥
- `JARVIS_MODEL`: 使用的AI模型（默认gpt-4）
- `TERM`: 终端类型

### AI模型配置
支持多种模型:
- OpenAI: gpt-4, gpt-4-turbo, gpt-3.5-turbo
- Anthropic: claude-3-opus, claude-3-sonnet, claude-3-haiku

## 架构特点

### 模块化设计
- Agent、CodeAgent、Tools三层分离
- 支持工具热插拔
- 内置规则与自定义规则共存

### 可扩展性
- MCP (Model Context Protocol) 协议支持
- 自定义工具可通过 meta_agent 工具生成
- 支持新平台适配

### 本地优先
- 所有数据本地存储
- 支持离线工作
- 无vendor lock-in
