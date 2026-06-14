# 项目综述

> 最后更新：2025-06-14 | 变更摘要：版本号更新至3.1.14，补充新增模块说明（jarvis_sec/jarvis_lsp/jarvis_smart_shell/jarvis_platform等），更新代码统计，完善CLI命令列表和CI/CD信息

## 项目概述

**项目名称**: Jarvis AI Assistant  
**版本**: 3.1.14  
**定位**: 本地运行、开箱即用、可深度定制的 AI 开发助手平台  
**目标用户**: 个人开发者、工程团队、专项场景用户  
**仓库**: https://github.com/skyfireitdiy/Jarvis.git

### 核心能力

- 分析项目结构，生成执行计划
- 修改代码后自动验证（Git、构建、静态检查、影响分析）
- 安全扫描与报告聚合（C/Rust安全检查器）
- C→Rust 迁移流水线
- 方法论沉淀、记忆分层、规则按需加载
- 支持 CLI、Web、VSCode 三种访问方式
- 分布式部署（Master/Child节点模式）
- LSP语言服务集成
- 智能Shell交互
- 多AI平台适配（OpenAI/Anthropic）

## 技术栈

### 编程语言

- **Python**: 3.12 (严格要求，pyproject.toml中指定 `requires-python = "==3.12.*"`)

### 核心框架

- **FastAPI**: 0.115.12 (Web 服务框架)
- **Uvicorn**: 0.33.0 (ASGI 服务器)
- **OpenAI SDK**: 1.78.1 (AI 模型调用)
- **Anthropic SDK**: >=0.40.0 (Claude 模型支持)
- **Requests**: 2.32.3 (HTTP 客户端)
- **PyYAML**: >=5.3.1 (YAML解析)
- **Jinja2**: >=3.0.0 (模板引擎)
- **Typer**: (CLI框架)
- **Websockets**: (WebSocket支持)
- **HTTPX**: (异步HTTP客户端)
- **AIOHTTP**: >=3.9.0 (异步HTTP)
- **psutil**: >=5.9.0 (系统监控)

### 关键依赖

- **代码解析**: tree-sitter 0.25.2 系列 (支持 JS/TS/Rust/Go/Java/C/C++/Python/HTML/CSS/SQL/YAML/Markdown/Bash/Ruby/PHP 等15+语言)
- **终端UI**: prompt_toolkit 3.0.50, pygments 2.19.2, rich 14.2.0, pyte 0.8.2
- **Web抓取**: playwright 1.48.0, beautifulsoup4, lxml 6.0.0, markdownify
- **文本处理**: tiktoken 0.7.0, jieba, fuzzywuzzy 0.18.0, python-Levenshtein 0.25.1
- **代码检查**: ruff, bandit, python-lsp-server>=1.14.0
- **测试**: pytest, pytest-xdist, pytest-asyncio
- **文档**: mkdocs-material, mkdocs-git-revision-date-localized-plugin, pymdown-extensions
- **其他工具**: colorama 0.4.6, packaging>=24.2, jsonnet>=0.20.0, ddgr, ty

### 可选依赖

- **browser**: playwright==1.48.0 (浏览器自动化)
- **clang16/17/18/19/20/21**: Clang编译器支持 (C→Rust迁移)
- **tree-sitter-all**: 全部tree-sitter语言解析器（含Ruby/PHP）

## 代码统计

| 模块 | 文件数 | 代码行数 |
| --- | --- | --- |
| jarvis_agent | 53 | 17,662 |
| jarvis_code_agent | 60 | 16,968 |
| jarvis_c2rust | 52 | 18,329 |
| jarvis_tools | 25 | 14,550 |
| jarvis_utils | 22 | 14,773 |
| jarvis_web_gateway | 17 | 11,016 |
| jarvis_sec | 18 | 11,513 |
| jarvis_lsp | 8 | 6,287 |
| jarvis_service | 7 | 2,473 |
| jarvis_platform | 7 | 2,417 |
| jarvis_config | 4 | 2,444 |
| jarvis_platform_manager | 3 | 2,019 |
| jarvis_browser | 2 | 3,833 |
| jarvis_gateway | 7 | 907 |
| jarvis_jck | 4 | 754 |
| jarvis_memory_organizer | 3 | 1,457 |
| jarvis_mcp | 4 | 1,467 |
| jarvis_windows | 2 | 1,683 |
| jarvis_methodology | 1 | 481 |
| jarvis_smart_shell | 2 | 458 |
| jarvis_git_utils | 1 | 574 |
| jarvis_git_squash | 2 | 76 |
| jarvis_rules_index | 3 | 255 |
| jarvis_vscode_extension | 1 | 144 |
| **合计** | **311** | **132,594** |

> 注：统计范围 src/ 目录下的Python文件；测试文件87个

## 目录结构

```text
Jarvis/
├── src/jarvis/                    # 核心源码
│   ├── jarvis_agent/             # 主Agent模块（17,662行）
│   │   ├── jarvis.py             # Jarvis主类
│   │   ├── run_loop.py           # 运行循环
│   │   ├── session_manager.py    # 会话管理
│   │   ├── rules_manager.py      # 规则管理
│   │   ├── task_list.py          # 任务列表
│   │   ├── tool_executor.py      # 工具执行器
│   │   ├── builtin_input_handler.py  # 内置输入处理
│   │   ├── prompts.py            # 提示词模板
│   │   ├── language_support_info.py  # 语言支持信息
│   │   ├── skill_discovery/      # 技能发现
│   │   └── language_extractors/   # 语言提取器
│   ├── jarvis_code_agent/        # 代码Agent模块（16,968行）
│   │   ├── code_agent.py         # 代码Agent核心
│   │   ├── code_reviewer.py       # 代码审查
│   │   ├── code_analyzer/        # 代码分析器
│   │   ├── diff_visualizer.py    # 差异可视化
│   │   └── worktree_manager.py   # Git worktree管理
│   ├── jarvis_tools/             # 工具集（14,550行）
│   │   ├── registry.py            # 工具注册中心（83KB）
│   │   ├── task_list_manager.py   # 任务列表管理（107KB）
│   │   ├── gateway_manager.py     # Agent管理工具（81KB）
│   │   ├── execute_script.py      # 脚本执行（56KB）
│   │   ├── edit_file.py           # 文件编辑
│   │   ├── read_code.py           # 代码读取与符号分析
│   │   ├── memory.py              # 记忆管理
│   │   ├── virtual_tty.py         # 虚拟终端
│   │   ├── timer.py               # 定时任务
│   │   ├── search_web.py          # Web搜索
│   │   ├── read_webpage.py        # 网页读取
│   │   ├── symbol_dependency.py   # 符号依赖分析
│   │   ├── meta_agent.py          # 元代理工具
│   │   ├── methodology.py         # 方法论管理
│   │   ├── load_rule.py           # 规则加载
│   │   ├── auto_select_rule.py    # 自动规则选择
│   │   ├── add_images.py          # 图片添加
│   │   └── cli/                   # CLI子命令
│   ├── jarvis_utils/             # 工具库（14,773行）
│   │   ├── utils.py               # 通用工具函数（75KB）
│   │   ├── input.py               # 输入处理（68KB）
│   │   ├── output.py              # 输出处理（62KB）
│   │   ├── git_utils.py           # Git工具（52KB）
│   │   ├── config.py              # 配置管理（39KB）
│   │   ├── builtin_replace_map.py # 内置替换映射
│   │   ├── tmux_wrapper.py        # Tmux封装
│   │   ├── jsonnet_compat.py      # Jsonnet兼容层
│   │   ├── methodology.py         # 方法论工具
│   │   ├── quick_config.py         # 快速配置
│   │   ├── scenario_prompts.py    # 场景提示词
│   │   ├── embedding.py           # 嵌入计算
│   │   ├── dialogue_recorder.py   # 对话记录
│   │   └── globals.py             # 全局状态
│   ├── jarvis_c2rust/            # C→Rust迁移（18,329行）
│   ├── jarvis_web_gateway/       # Web网关（11,016行）
│   │   ├── app.py                 # 主应用（223KB，核心路由）
│   │   ├── node_manager.py        # 节点管理（87KB）
│   │   ├── agent_manager.py       # Agent管理
│   │   ├── agent_proxy_manager.py # Agent代理管理
│   │   ├── terminal_session_manager.py # 终端会话
│   │   ├── timer_manager.py       # 定时任务管理
│   │   ├── node_config.py          # 节点配置
│   │   ├── node_runtime.py         # 节点运行时
│   │   ├── node_protocol.py        # 节点协议
│   │   ├── token_manager.py        # Token管理
│   │   └── system_info.py          # 系统信息
│   ├── jarvis_sec/               # 安全扫描（11,513行）
│   │   ├── cli.py                 # CLI入口
│   │   ├── clustering.py          # 漏洞聚类（61KB）
│   │   ├── verification.py        # 验证引擎（45KB）
│   │   ├── workflow.py            # 工作流
│   │   ├── analysis.py            # 分析引擎
│   │   ├── review.py              # 审查逻辑
│   │   ├── report.py              # 报告生成
│   │   ├── agents.py              # 安全Agent
│   │   ├── file_manager.py        # 文件管理
│   │   ├── utils.py               # 工具函数
│   │   ├── prompts.py             # 提示词
│   │   ├── status.py              # 状态管理
│   │   ├── parsers.py             # 解析器
│   │   ├── types.py               # 类型定义
│   │   └── checkers/              # 语言检查器
│   │       ├── c_checker.py       # C安全检查器（122KB）
│   │       └── rust_checker.py    # Rust安全检查器（40KB）
│   ├── jarvis_lsp/               # LSP语言服务（6,287行）
│   │   ├── client.py              # LSP客户端（66KB）
│   │   ├── daemon.py              # LSP守护进程（50KB）
│   │   ├── daemon_client.py       # 守护进程客户端
│   │   ├── server_manager.py      # 服务器管理
│   │   ├── cli.py                 # CLI入口
│   │   ├── config.py              # 配置
│   │   └── protocol.py            # LSP协议
│   ├── jarvis_service/           # Web服务模块（2,473行）
│   │   └── cli.py                 # 服务CLI（67KB）
│   ├── jarvis_platform/          # AI平台适配（2,417行）
│   │   ├── base.py                 # 平台基类（33KB）
│   │   ├── openai.py              # OpenAI适配
│   │   ├── claude.py              # Claude适配
│   │   ├── registry.py            # 平台注册
│   │   ├── content_processor.py   # 内容处理器
│   │   └── content_types.py       # 内容类型
│   ├── jarvis_config/            # 配置管理（2,444行）
│   ├── jarvis_platform_manager/  # 平台管理器（2,019行）
│   │   ├── main.py                # 主逻辑（60KB）
│   │   └── service.py             # 服务层
│   ├── jarvis_browser/           # 浏览器自动化（3,833行）
│   ├── jarvis_gateway/            # CLI网关（907行）
│   │   ├── gateway.py             # 网关核心
│   │   ├── input_bridge.py        # 输入桥接
│   │   ├── output_bridge.py       # 输出桥接
│   │   ├── cli_gateway.py        # CLI网关
│   │   ├── events.py             # 事件定义
│   │   └── manager.py            # 管理器
│   ├── jarvis_mcp/                # MCP协议集成（1,467行）
│   ├── jarvis_memory_organizer/   # 记忆组织器（1,457行）
│   ├── jarvis_windows/            # Windows支持（1,683行）
│   ├── jarvis_jck/                # JCK工具（754行）
│   ├── jarvis_smart_shell/        # 智能Shell（458行）
│   ├── jarvis_git_utils/         # Git工具（574行）
│   ├── jarvis_methodology/       # 方法论（481行）
│   ├── jarvis_git_squash/        # Git压缩（76行）
│   ├── jarvis_rules_index/       # 规则索引（255行）
│   ├── jarvis_tui/               # 终端UI模块
│   ├── jarvis_vscode_extension/  # VSCode插件
│   ├── prompts/                  # 提示词模板
│   ├── scripts/                  # 安装脚本
│   └── jarvis_data/              # 数据文件
├── tests/                        # 测试目录（87个文件）
│   ├── jarvis_agent/             # Agent测试
│   ├── jarvis_code_agent/        # 代码Agent测试
│   ├── jarvis_c2rust/            # C→Rust迁移测试
│   ├── jarvis_config/            # 配置测试
│   ├── jarvis_git_utils/         # Git工具测试
│   ├── jarvis_lsp/               # LSP测试
│   ├── jarvis_mcp/               # MCP测试
│   ├── jarvis_memory_organizer/  # 记忆组织器测试
│   ├── jarvis_platform/          # 平台测试
│   ├── jarvis_platform_manager/  # 平台管理器测试
│   ├── jarvis_sec/               # 安全扫描测试
│   ├── jarvis_smart_shell/       # 智能Shell测试
│   ├── jarvis_tools/             # 工具测试
│   ├── jarvis_utils/             # 工具库测试
│   ├── jarvis_web_gateway/       # Web网关测试
│   ├── performance/              # 性能测试
│   ├── regression/              # 回归测试
│   ├── security/                 # 安全测试
│   └── test_utils/               # 测试工具
├── builtin/                      # 内置资源
│   ├── agent/                    # Agent配置模板
│   ├── prompts/                  # 内置提示词
│   └── rules/                    # 内置规则
│       ├── development_workflow/ # 开发工作流
│       ├── code_quality/         # 代码质量
│       ├── security/             # 安全
│       └── architecture_design/  # 架构设计
├── docs/                         # 文档
│   ├── jarvis_book/              # Jarvis手册
│   ├── best_practices/          # 最佳实践
│   ├── compare/                  # 对比分析
│   ├── technical/               # 技术文档
│   └── 用户手册/                 # 用户手册
├── scripts/                      # 脚本
├── .github/workflows/            # CI/CD
│   ├── test.yml                  # 测试流水线
│   ├── publish.yml               # PyPI发布
│   ├── docker-publish.yml        # Docker发布
│   ├── deploy-docs.yml           # 文档部署
│   └── publish-vscode.yml        # VSCode插件发布
├── .jarvis/                      # Jarvis配置目录
│   ├── rule.md                   # 项目综述
│   ├── config.yaml               # 运行配置
│   ├── build_validation_config.yaml # 构建验证配置
│   ├── memory/                   # 记忆存储
│   ├── sessions/                 # 会话存储
│   ├── symbol_cache/             # 符号缓存
│   ├── methodologies/            # 方法论
│   ├── evolution/                # 演化计划
│   └── jsec/                     # 安全配置
├── pyproject.toml                # 项目配置（版本3.1.14）
├── Dockerfile                    # Docker镜像
├── docker-compose.yml            # Docker编排
├── start.sh                      # 启动脚本
└── README.md                     # 项目说明
```

## 核心模块

### jarvis_agent (主Agent模块)

- **职责**: 核心Agent逻辑、会话管理、规则加载、任务调度、技能发现
- **关键文件**: `jarvis.py`(主类), `run_loop.py`(运行循环), `session_manager.py`(会话管理), `rules_manager.py`(规则管理), `tool_executor.py`(工具执行器)
- **依赖**: jarvis_tools, jarvis_code_agent, jarvis_utils
- **对外接口**: `jarvis`/`jvs` CLI命令, `jarvis-agent`/`ja` CLI命令

### jarvis_code_agent (代码Agent模块)

- **职责**: 代码修改、审查、构建验证、Lint检查、Diff处理
- **关键文件**: `code_agent.py`(核心), `code_reviewer.py`(审查), `code_analyzer/`(分析器)
- **依赖**: tree-sitter系列, ruff, bandit
- **对外接口**: `jarvis-code-agent`/`jca` CLI命令, `jcad`/`jarvis-code-agent-dispatcher` CLI命令

### jarvis_tools (工具集)

- **职责**: 提供Agent可调用的所有工具，工具注册与调度
- **关键文件**: `registry.py`(注册中心), `task_list_manager.py`(任务管理), `gateway_manager.py`(Agent通信), `execute_script.py`(脚本执行), `edit_file.py`(文件编辑)
- **依赖**: jarvis_utils, jarvis_web_gateway
- **对外接口**: `jarvis-tool`/`jt` CLI命令

### jarvis_web_gateway (Web网关)

- **职责**: HTTP/WebSocket服务、Agent管理、节点管理、终端会话、定时任务、Token认证
- **关键文件**: `app.py`(主应用223KB), `node_manager.py`(节点管理87KB), `agent_manager.py`(Agent管理), `agent_proxy_manager.py`(代理管理)
- **依赖**: FastAPI, Uvicorn, WebSockets
- **对外接口**: `jarvis-web-gateway`/`jwg` CLI命令

### jarvis_sec (安全扫描)

- **职责**: C/Rust代码安全漏洞扫描、聚类分析、验证、报告生成
- **关键文件**: `clustering.py`(漏洞聚类61KB), `verification.py`(验证引擎45KB), `checkers/c_checker.py`(C检查器122KB), `checkers/rust_checker.py`(Rust检查器40KB)
- **依赖**: tree-sitter-c, tree-sitter-rust
- **对外接口**: `jarvis-sec`/`jsec` CLI命令

### jarvis_lsp (LSP语言服务)

- **职责**: LSP协议客户端、守护进程管理、代码智能服务
- **关键文件**: `client.py`(LSP客户端66KB), `daemon.py`(守护进程50KB), `daemon_client.py`(客户端28KB), `server_manager.py`(服务器管理)
- **依赖**: python-lsp-server>=1.14.0
- **对外接口**: `jarvis-lsp`/`jlsp` CLI命令

### jarvis_platform (AI平台适配)

- **职责**: 多AI平台统一接口（OpenAI/Anthropic）、内容处理、平台注册
- **关键文件**: `base.py`(平台基类33KB), `openai.py`(OpenAI适配), `claude.py`(Claude适配), `registry.py`(平台注册)
- **依赖**: openai==1.78.1, anthropic>=0.40.0
- **对外接口**: 供jarvis_agent/jarvis_platform_manager调用

### jarvis_c2rust (C→Rust迁移)

- **职责**: C代码到Rust的自动迁移流水线
- **关键文件**: 模块内52个文件，18,329行代码
- **依赖**: clang, tree-sitter-c, tree-sitter-rust
- **对外接口**: `jarvis-c2rust`/`jc2r` CLI命令

### jarvis_utils (工具库)

- **职责**: 通用工具函数、配置管理、Git工具、输入输出处理、全局状态
- **关键文件**: `utils.py`(75KB), `input.py`(68KB), `output.py`(62KB), `git_utils.py`(52KB), `config.py`(39KB)
- **依赖**: 被所有模块依赖
- **对外接口**: `jarvis-quick-config`/`jqc` CLI命令

### jarvis_service (Web服务)

- **职责**: Web服务启动入口，服务生命周期管理
- **关键文件**: `cli.py`(服务CLI 67KB)
- **依赖**: jarvis_web_gateway
- **对外接口**: `jarvis-service`/`jservice` CLI命令

### 其他模块

| 模块 | 职责 | CLI命令 |
| --- | --- | --- |
| jarvis_config | 配置管理 | `jcfg` |
| jarvis_platform_manager | AI平台管理器 | `jpm` |
| jarvis_browser | 浏览器自动化 | `jb` |
| jarvis_gateway | CLI网关桥接 | - |
| jarvis_mcp | MCP协议集成 | - |
| jarvis_memory_organizer | 记忆组织与整理 | `jmo` |
| jarvis_smart_shell | 智能Shell交互 | `jss` |
| jarvis_git_utils | Git提交工具 | `jgc` |
| jarvis_git_squash | Git压缩合并 | `jgs` |
| jarvis_methodology | 方法论管理 | `jm` |
| jarvis_rules_index | 规则索引查询 | `jri` |
| jarvis_windows | Windows平台支持 | `jw` |
| jarvis_jck | JCK工具 | - |

## 代理与节点架构

### 整体通信架构

```text
┌──────────────┐                    ┌─────────────────────────────────────┐
│  Web 前端    │ ──── WebSocket ──▶ │           Master 节点                 │
│  (浏览器)    │ ◀─── WebSocket ──  │      (jarvis_web_gateway)            │
│              │                    │  ┌─────────────────────────────┐    │
│              │ ──── HTTP ──────▶  │  │ /ws          主连接         │    │
│              │                    │  │ /api/agent/{id}/ws  Agent WS │    │
│              │                    │  │ /api/agents   管理接口      │    │
│              │                    │  └─────────────────────────────┘    │
└──────────────┘                    │                 │                   │
                                    │    WebSocket    │    HTTP/WS       │
                                    │   (节点间协议)   │  (本地代理)      │
                                    │                 ▼                   │
                                    │  ┌─────────────────────────────┐    │
                                    │  │      Child 节点 (可选)       │    │
                                    │  │   (jarvis_web_gateway)      │    │
                                    │  └───────────┬─────────────────┘    │
                                    └──────────────┼─────────────────────┘
                                                   │ HTTP/WS (本地代理)
                                                   ▼
                                    ┌─────────────────────────────────────┐
                                    │           Agent 进程                 │
                                    │    (独立子进程，监听随机端口)         │
                                    │  ┌─────────────────────────────┐    │
                                    │  │ /ws          消息收发        │    │
                                    │  │ /status      状态查询        │    │
                                    │  │ /message     消息注入        │    │
                                    │  │ /sessions    会话管理        │    │
                                    │  └─────────────────────────────┘    │
                                    └─────────────────────────────────────┘
```

### 组件间通信关系详解

#### 1. Web前端 ↔ Master节点

| 方向        | 协议      | 端点                                      | 用途                                |
| ----------- | --------- | ----------------------------------------- | ----------------------------------- |
| 前端→Master | WebSocket | `/ws`                                     | 主连接，发送用户输入、接收Agent输出 |
| 前端→Master | WebSocket | `/api/agent/{agent_id}/ws`                | Agent专用连接，独立于主连接         |
| 前端→Master | WebSocket | `/api/node/{node_id}/agent/{agent_id}/ws` | 指定节点的Agent连接                 |
| 前端→Master | HTTP      | `/api/auth/login`                         | 登录获取Token                       |
| 前端→Master | HTTP      | `/api/agents`                             | 创建/列出/停止/删除Agent            |
| 前端→Master | HTTP      | `/api/agent/{agent_id}/*`                 | 代理到Agent的HTTP请求               |

#### 2. Master节点 ↔ Child节点

| 方向         | 协议      | 端点                            | 用途                 |
| ------------ | --------- | ------------------------------- | -------------------- |
| Child→Master | WebSocket | `/ws/node`                      | 子节点注册、心跳保活 |
| Master→Child | 节点协议  | `AGENT_CREATE_REQUEST`          | 跨节点创建Agent      |
| Master→Child | 节点协议  | `AGENT_HTTP_REQUEST`            | 跨节点HTTP代理       |
| Master→Child | 节点协议  | `AGENT_WS_OPEN/SEND/RECV/CLOSE` | 跨节点WebSocket代理  |
| Child→Master | 节点协议  | `NODE_HEARTBEAT`                | 心跳保活             |

#### 3. Master/Child节点 ↔ Agent进程

| 方向       | 协议      | 地址                             | 用途               |
| ---------- | --------- | -------------------------------- | ------------------ |
| 节点→Agent | HTTP      | `http://127.0.0.1:{port}/{path}` | 反向代理HTTP请求   |
| 节点→Agent | WebSocket | `ws://127.0.0.1:{port}/ws`       | 双向消息转发       |
| Agent→节点 | WebSocket | 回复消息                         | 输出事件、执行状态 |

#### 4. Agent进程内部端点

Agent进程启动时在随机端口上启动微型Web服务（uvicorn），提供以下端点：

| 端点        | 方法      | 用途                                     |
| ----------- | --------- | ---------------------------------------- |
| `/ws`       | WebSocket | WebSocketConnectionManager处理，消息收发 |
| `/status`   | GET       | 返回Agent执行状态                        |
| `/diff`     | GET       | 返回代码差异                             |
| `/rules`    | GET       | 返回已加载规则                           |
| `/tools`    | GET       | 返回可用工具列表                         |
| `/sessions` | GET/POST  | 会话管理                                 |
| `/message`  | POST      | 接收其他Agent发来的消息，注入到输入流    |

### 节点模式

Jarvis 支持分布式部署，采用 **Master/Child** 节点模式：

- **Master 节点**：对外统一入口，管理所有子节点连接，路由 Agent 请求
- **Child 节点**：运行 Agent 实例，通过 WebSocket 长连接注册到 Master

**核心组件**：

| 组件         | 文件                                  | 职责                                                                              |
| ------------ | ------------------------------------- | --------------------------------------------------------------------------------- |
| 节点配置     | `jarvis_web_gateway/node_config.py`   | NodeRuntimeConfig，定义 node_mode(master/child)、node_id、master_url、node_secret |
| 节点运行时   | `jarvis_web_gateway/node_runtime.py`  | NodeRuntime，管理 NodeRegistry、AgentRouteRegistry、TokenSyncState                |
| 节点连接管理 | `jarvis_web_gateway/node_manager.py`  | NodeConnectionManager(Master端)，管理子节点 WebSocket 连接，处理节点间请求转发    |
| 子节点客户端 | `jarvis_web_gateway/node_manager.py`  | ChildNodeClient(Child端)，连接 Master、心跳保活、接收并处理 Master 下发的请求     |
| 节点协议     | `jarvis_web_gateway/node_protocol.py` | 定义节点间所有消息类型和消息构建工具                                              |

**节点生命周期**：

1. Child 启动 → 通过 `node_secret` 认证连接 Master `/ws/node`
2. Master 返回 `JARVIS_AUTH_TOKEN` → Child 同步到环境变量
3. Child 心跳保活（`NODE_HEARTBEAT`），断线自动重连
4. Master 通过 `NodeConnectionManager.send_request_to_node()` 向 Child 发送请求

### Agent 路由

**AgentRouteRegistry** 维护 agent_id → node_id 的映射关系：

- Agent 创建时注册路由（`register`），删除时移除（`remove`）
- Master 收到浏览器请求时，通过路由表确定 Agent 所在节点
- 浏览器重连不影响路由（路由与 Agent 生命周期绑定，非连接绑定）

### 本地 Agent 代理

**AgentProxyManager** 负责将前端请求反向代理到本地 Agent：

- **HTTP 代理**：`proxy_http_request()` → 转发到 `http://127.0.0.1:{port}/{path}`
- **WebSocket 代理**：`proxy_websocket()` → 连接 `ws://127.0.0.1:{port}/ws`
  - 通过 subprotocol `jarvis-token.{auth_token}` 传递认证
  - 连接后发送 auth JSON 消息 `{"type": "auth", "payload": {"token": ...}}`
  - 双向转发：client→agent 和 agent→client 并行任务
  - 消息缓存：客户端断开时缓存 Agent 消息（`_agent_message_cache`，上限200条），重连后刷新（`_flush_cached_messages`）

### 远程 Agent 代理

当 Agent 运行在 Child 节点时，Master 通过 **SEND/RECV 轮询模式** 代理 WebSocket：

```text
浏览器 → Master /api/agent/{agent_id}/ws
  → NodeConnectionManager.send_request_to_node(AGENT_WS_OPEN_REQUEST)
  → Child _handle_agent_ws_open_request() → 连接 Agent ws://127.0.0.1:{port}/ws
  → 存入 _agent_ws_sessions[session_id]
双向转发：AGENT_WS_SEND_REQUEST / AGENT_WS_RECV_REQUEST 轮询
```

**关键差异（本地 vs 远程）**：

- 本地代理：连接 Agent 后发送 auth JSON 消息
- 远程代理：仅通过 subprotocol 传递 token，不发送 auth JSON 消息
- Agent 端 `WebSocketConnectionManager.handle` 只从 headers 提取 auth，不处理 JSON auth 消息，因此差异不影响功能

**远程代理轮询机制**：

- `forward_client_to_remote`：浏览器消息 → `AGENT_WS_SEND_REQUEST` → Child → `agent_ws.send()`
- `forward_remote_to_client`：`AGENT_WS_RECV_REQUEST`(timeout=1.0s) → Child `agent_ws.recv()` → 浏览器
- 浏览器断开 → Master finally 块发 `AGENT_WS_CLOSE_REQUEST` → Child 关闭 agent_ws 并从 `_agent_ws_sessions` 移除

### WebSocket 连接管理

**WebSocketConnectionManager**（Agent 端，`app.py:487`）：

- `session_id = "default"` 固定，简化重连逻辑
- `_connection_lock_enabled = False`：允许新连接替换旧连接
- 新连接替换时：关闭旧 WebSocket → unregister 旧路由 → 清除旧 auth → 注册新连接
- `connection_id` 检查保护：finally 块中只有当前 connection_id 匹配才清理，避免新连接被旧连接的清理逻辑误删
- 断开时恢复：发送缓存输出（`_pending_outputs`）、恢复待处理输入/确认请求

### 节点间协议消息类型

| 类别           | 消息类型                                | 说明                          |
| -------------- | --------------------------------------- | ----------------------------- |
| 认证           | `NODE_AUTH` / `NODE_AUTH_RESULT`        | 子节点认证，Master 返回 token |
| 心跳           | `NODE_HEARTBEAT`                        | 子节点心跳保活                |
| Agent 管理     | `AGENT_CREATE_REQUEST/RESPONSE`         | 跨节点创建 Agent              |
|                | `AGENT_LIST_REQUEST/RESPONSE`           | 获取节点 Agent 列表           |
|                | `AGENT_STOP_REQUEST/RESPONSE`           | 跨节点停止 Agent              |
|                | `AGENT_DELETE_REQUEST/RESPONSE`         | 跨节点删除 Agent              |
| HTTP 代理      | `AGENT_HTTP_REQUEST/RESPONSE`           | 跨节点 HTTP 代理              |
|                | `NODE_HTTP_PROXY_REQUEST/RESPONSE`      | 节点级 HTTP 代理              |
| WebSocket 代理 | `AGENT_WS_OPEN_REQUEST/RESPONSE`        | 打开远程 WS 会话              |
|                | `AGENT_WS_SEND_REQUEST/RESPONSE`        | 发送 WS 消息                  |
|                | `AGENT_WS_RECV_REQUEST/RESPONSE`        | 接收 WS 消息                  |
|                | `AGENT_WS_CLOSE_REQUEST/RESPONSE`       | 关闭 WS 会话                  |
|                | `AGENT_WS_REQUEST/RESPONSE`             | 通用 WS 请求                  |
| 终端           | `NODE_TERMINAL_REQUEST/RESPONSE/OUTPUT` | 远程终端会话                  |
| 目录           | `DIRECTORY_LIST_REQUEST/RESPONSE`       | 跨节点目录列表                |
| 配置           | `CONFIG_SYNC/GET/SET_REQUEST/RESPONSE`  | 配置同步与管理                |
| 运维           | `SERVICE_RESTART_REQUEST/RESPONSE`      | 远程重启服务                  |
|                | `CODE_UPDATE_TO_MAIN_REQUEST/RESPONSE`  | 更新代码到 main 分支          |

### 认证机制

1. **Gateway Token**：服务启动时生成 `JARVIS_AUTH_TOKEN`，存入环境变量，子进程（Agent）共享
2. **HTTP 认证**：支持 `Authorization: Bearer <token>` 和 `X-Jarvis-Token: <token>` 两种方式
3. **WebSocket 认证**：通过 subprotocol `jarvis-token.{auth_token}` 传递，Agent 端从 `sec-websocket-protocol` header 提取
4. **节点认证**：Child 通过 `node_secret` 认证连接 Master，认证成功后 Master 下发 `JARVIS_AUTH_TOKEN`
5. **登录接口**：`POST /api/auth/login`，验证密码后返回 Token

## 架构特点

### 架构模式

- **插件化架构**：Agent、CodeAgent、Tools三层分离，工具热插拔
- **分布式部署**：Master/Child节点模式，支持跨节点Agent管理
- **事件驱动**：WebSocket双向通信，节点间协议消息驱动

### 扩展机制

- **工具系统**：ToolRegistry管理所有工具，支持通过meta_agent动态生成新工具
- **规则系统**：内置规则与自定义规则共存，auto_select_rule按需加载
- **平台适配**：jarvis_platform提供统一AI平台接口，registry模式注册新平台
- **MCP协议**：Model Context Protocol支持外部工具集成
- **配置驱动**：YAML/JSON配置文件、环境变量、远程配置

### 关键设计模式

- **注册表模式（Registry）**：ToolRegistry、AgentRouteRegistry、PlatformRegistry统一管理可扩展组件
- **代理模式（Proxy）**：AgentProxyManager实现本地/远程Agent透明代理
- **观察者模式**：WebSocket连接管理、事件总线
- **策略模式**：jarvis_platform/base.py定义平台接口，OpenAI/Claude为具体策略
- **工厂模式**：meta_agent动态创建工具
- **守护进程模式**：jarvis_lsp/daemon.py管理LSP服务生命周期

### 数据持久化

- **文件存储**：会话（`.jarvis/sessions/`）、记忆（`.jarvis/memory/`）、符号缓存（`.jarvis/symbol_cache/`）
- **无数据库依赖**：所有数据本地文件存储，零外部依赖
- **Git集成**：git_utils.py提供完整的Git操作封装

### 异常处理与容错

- **WebSocket重连**：断开时缓存消息，重连后自动刷新
- **节点心跳保活**：Child节点定期发送心跳，断线自动重连
- **Agent进程隔离**：Agent运行在独立子进程，崩溃不影响主服务
- **连接替换保护**：connection_id检查防止新连接被旧连接清理逻辑误删

## CLI命令一览

| 命令 | 别名 | 入口模块 | 用途 |
| --- | --- | --- | --- |
| `jarvis` | `jvs` | jarvis_agent.jarvis | 主Agent CLI |
| `jarvis-agent` | `ja` | jarvis_agent.main | Agent入口 |
| `jarvis-agent-dispatcher` | `jvsd` | jarvis_agent.jvsd_cli | Agent调度器 |
| `jarvis-code-agent` | `jca` | jarvis_code_agent.code_agent | 代码Agent |
| `jarvis-code-agent-dispatcher` | `jcad` | jarvis_code_agent.jcad_cli | 代码Agent调度器 |
| `jarvis-smart-shell` | `jss` | jarvis_smart_shell.main | 智能Shell |
| `jarvis-platform-manager` | `jpm` | jarvis_platform_manager.main | 平台管理器 |
| `jarvis-git-commit` | `jgc` | jarvis_git_utils.git_commiter | Git提交 |
| `jarvis-git-squash` | `jgs` | jarvis_git_squash.main | Git压缩 |
| `jarvis-memory-organizer` | `jmo` | jarvis_memory_organizer.memory_organizer | 记忆组织器 |
| `jarvis-tool` | `jt` | jarvis_tools.cli.main | 工具CLI |
| `jarvis-methodology` | `jm` | jarvis_methodology.main | 方法论管理 |
| `jarvis-sec` | `jsec` | jarvis_sec.cli | 安全扫描 |
| `jarvis-c2rust` | `jc2r` | jarvis_c2rust.cli | C→Rust迁移 |
| `jarvis-config` | `jcfg` | jarvis_config.cli | 配置管理 |
| `jarvis-lsp` | `jlsp` | jarvis_lsp.cli | LSP服务 |
| `jarvis-browser` | `jb` | jarvis_browser.cli | 浏览器自动化 |
| `jarvis-windows` | `jw` | jarvis_windows.cli | Windows支持 |
| `jarvis-web-gateway` | `jwg` | jarvis_web_gateway.cli | Web网关 |
| `jarvis-service` | `jservice` | jarvis_service.cli | Web服务 |
| `jarvis-quick-config` | `jqc` | jarvis_utils.quick_config | 快速配置 |
| `jarvis-rules-index` | `jri` | jarvis_rules_index.cli | 规则索引 |
| `install-playwright` | - | jarvis.scripts.install_playwright | Playwright安装 |

## 构建与运行

### 安装

```bash
pip install -e .                    # 开发模式安装
pip install -e ".[browser]"        # 带浏览器支持
pip install -e ".[clang18]"        # 带Clang编译器支持
pip install -e ".[tree-sitter-all]" # 全部tree-sitter语言
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

- Python: 3.12 (严格要求，`requires-python = "==3.12.*"`)
- 系统: Linux (主要), Windows (部分支持，需pywinauto/pywinpty)
- 可选: Playwright浏览器、Clang编译器
- 架构限制: tree-sitter/playwright不支持armv6l/armv7l/armv8l/armhf

### Docker支持

- **镜像**: `ghcr.io/skyfireitdiy/jarvis:latest`
- **基础镜像**: `python:3.12`
- **工作目录**: `/workspace`
- **用户**: jarvis(UID 1000)
- **挂载**: 当前目录→/workspace, ~/.jarvis→/home/jarvis/.jarvis, ~/.gitconfig(只读)

## 测试

### 测试框架

- **pytest**: 主测试框架（minversion = "3.1.14"）
- **pytest-xdist**: 并行测试
- **pytest-asyncio**: 异步测试支持

### 测试标记

- `slow`: 慢速测试
- `integration`: 集成测试
- `unit`: 单元测试
- `smoke`: 冒烟测试
- `security`: 安全测试
- `regression`: 回归测试
- `monitoring`: 监控测试

### 运行测试

```bash
pytest tests/                        # 运行所有测试
pytest tests/jarvis_agent/          # 运行特定模块测试
pytest -n auto                     # 并行运行
pytest --cov=src/jarvis            # 带覆盖率
pytest -m "not slow"               # 跳过慢速测试
pytest -m integration              # 只运行集成测试
```

### 测试目录结构

```text
tests/
├── jarvis_agent/                   # Agent测试
├── jarvis_code_agent/              # 代码Agent测试
├── jarvis_c2rust/                  # C→Rust迁移测试
├── jarvis_config/                  # 配置测试
├── jarvis_git_utils/               # Git工具测试
├── jarvis_lsp/                     # LSP测试
├── jarvis_mcp/                     # MCP测试
├── jarvis_memory_organizer/        # 记忆组织器测试
├── jarvis_platform/                # 平台测试
├── jarvis_platform_manager/        # 平台管理器测试
├── jarvis_sec/                     # 安全扫描测试
├── jarvis_smart_shell/             # 智能Shell测试
├── jarvis_tools/                   # 工具测试
├── jarvis_utils/                   # 工具库测试
├── jarvis_web_gateway/             # Web网关测试
├── performance/                    # 性能测试
├── regression/                    # 回归测试
├── security/                      # 安全测试
└── test_utils/                    # 测试工具
```

## CI/CD

| 工作流 | 文件 | 触发条件 | 用途 |
| --- | --- | --- | --- |
| 测试 | `.github/workflows/test.yml` | push/PR到main | 运行pytest |
| PyPI发布 | `.github/workflows/publish.yml` | 推送v*标签 | 构建并发布到PyPI |
| Docker发布 | `.github/workflows/docker-publish.yml` | - | 构建并推送Docker镜像到GHCR |
| 文档部署 | `.github/workflows/deploy-docs.yml` | - | 部署MkDocs文档到GitHub Pages |
| VSCode插件发布 | `.github/workflows/publish-vscode.yml` | - | 发布VSCode扩展 |

## 关键配置

### 配置文件

- `pyproject.toml`: 项目元数据、依赖管理、CLI入口、pytest配置
- `.jarvis/config.yaml`: Jarvis运行配置
- `.jarvis/build_validation_config.yaml`: 构建验证配置
- `.jarvis/rules/`: 项目规则目录
- `.jarvis/methodologies/`: 方法论目录
- `.jarvis/jsec/config.json`: 安全扫描配置

### 环境变量

- `OPENAI_API_KEY`: OpenAI API密钥
- `ANTHROPIC_API_KEY`: Anthropic API密钥
- `JARVIS_MODEL`: 使用的AI模型（默认gpt-4）
- `JARVIS_AUTH_TOKEN`: Gateway认证Token（服务启动时自动生成）
- `TERM`: 终端类型

### AI模型配置

支持多种模型:

- **OpenAI**: gpt-4, gpt-4-turbo, gpt-3.5-turbo (通过 openai==1.78.1)
- **Anthropic**: claude-3-opus, claude-3-sonnet, claude-3-haiku (通过 anthropic>=0.40.0)
- **环境变量**: `JARVIS_MODEL` 指定默认模型（默认gpt-4）
- **平台管理器**: `jpm` 命令管理模型组配置
