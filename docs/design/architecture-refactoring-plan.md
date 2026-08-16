# Jarvis 架构重构方案

> 版本：1.0  
> 日期：2026-08-16  
> 状态：设计草案

---

## 1. 项目概述

**项目名称**：Jarvis AI Assistant  
**当前版本**：3.1.14  
**技术栈**：Python 3.12 + FastAPI + Vue 3 + TypeScript  
**代码规模**：约 155,000 行 Python 代码，24 个模块，92 个测试文件

---

## 2. 现状分析

### 2.1 模块清单与代码量

| 模块                    | 文件数 | 代码行数 | 职责              |
| ----------------------- | ------ | -------- | ----------------- |
| jarvis_agent            | 51     | 19,131   | 主 Agent 核心逻辑 |
| jarvis_c2rust           | 52     | 18,658   | C→Rust 迁移流水线 |
| jarvis_code_agent       | 59     | 16,868   | 代码 Agent        |
| jarvis_tools            | 27     | 15,652   | 工具集            |
| jarvis_utils            | 23     | 15,292   | 通用工具库        |
| jarvis_web_gateway      | 21     | 14,313   | Web 网关          |
| jarvis_sec              | 23     | 27,734   | 安全扫描          |
| jarvis_lsp              | 8      | 6,302    | LSP 语言服务      |
| jarvis_browser          | 2      | 3,855    | 浏览器自动化      |
| jarvis_platform         | 7      | 2,515    | AI 平台适配       |
| jarvis_service          | 7      | 2,445    | Web 服务入口      |
| jarvis_config           | 4      | 2,444    | 配置管理          |
| jarvis_platform_manager | 3      | 2,032    | 平台管理器        |
| jarvis_windows          | 2      | 1,683    | Windows 支持      |
| jarvis_mcp              | 4      | 1,477    | MCP 协议集成      |
| jarvis_memory_organizer | 3      | 1,457    | 记忆组织器        |
| jarvis_gateway          | 7      | 886      | CLI 网关桥接      |
| jarvis_jck              | 4      | 754      | JCK 工具          |
| jarvis_git_utils        | 1      | 576      | Git 提交工具      |
| jarvis_methodology      | 1      | 481      | 方法论管理        |
| jarvis_smart_shell      | 2      | 458      | 智能 Shell        |
| jarvis_rules_index      | 3      | 255      | 规则索引          |
| jarvis_git_squash       | 2      | 76       | Git 压缩          |
| jarvis_data             | 0      | 0        | 数据文件（空）    |

### 2.2 核心问题识别

#### 问题 1：循环依赖严重

以下模块间存在双向依赖，违反依赖倒置原则：

```text
jarvis_agent ←→ jarvis_tools
jarvis_agent ←→ jarvis_code_agent
jarvis_utils ←→ jarvis_platform
jarvis_web_gateway → jarvis_service（反向依赖）
```

**影响**：

- 模块无法独立测试
- 修改一个模块可能影响另一个模块
- 导入顺序敏感，易产生运行时错误
- 阻碍模块化拆分与独立部署

#### 问题 2：超大文件

| 文件                                | 行数  | 问题                             |
| ----------------------------------- | ----- | -------------------------------- |
| jarvis_sec/checkers/c_checker.py    | 9,453 | 单文件承担全部 C 安全检查逻辑    |
| jarvis_web_gateway/app.py           | 7,357 | 所有路由集中在一个文件           |
| jarvis_sec/checkers/rust_checker.py | 3,908 | 单文件承担全部 Rust 安全检查逻辑 |
| jarvis_browser/cli.py               | 3,850 | CLI 入口与业务逻辑混合           |
| jarvis_agent/`__init__.py`          | 3,444 | 模块初始化文件承担过多职责       |

**影响**：

- 代码可读性差，难以维护
- 合并冲突频繁
- 无法并行开发
- 测试覆盖困难

#### 问题 3：模块职责不清

- `jarvis_agent/__init__.py` 3444 行，承担 Agent 类定义、事件处理、工具调用等多重职责
- `jarvis_service` 与 `jarvis_web_gateway` 边界模糊，service 仅含 cli.py 但被 web_gateway 反向依赖
- `jarvis_data` 目录为空，但被保留在模块列表中
- 前端代码嵌入 `jarvis_service/frontend/`，与后端 Python 代码混合

#### 问题 4：前端与后端耦合

前端 Vue 3 代码位于 `src/jarvis/jarvis_service/frontend/`，与后端 Python 代码在同一目录树下，导致：

- 构建系统需要同时处理 Python 和 Node.js
- 部署时需要额外处理前端构建产物
- 版本管理混乱

---

## 3. 目标架构

### 3.1 分层架构设计

```text
┌─────────────────────────────────────────────────┐
│                  接口层（Interface）              │
│  CLI / Web UI / WebSocket / REST API / LSP      │
├─────────────────────────────────────────────────┤
│                  应用层（Application）            │
│  Agent 核心 / Code Agent / C2Rust / 安全扫描     │
├─────────────────────────────────────────────────┤
│                  领域层（Domain）                 │
│  工具集 / 平台适配 / MCP / 方法论 / 记忆          │
├─────────────────────────────────────────────────┤
│                  基础设施层（Infrastructure）     │
│  配置 / 日志 / Git / 通用工具 / 数据存储          │
└─────────────────────────────────────────────────┘
```

### 3.2 依赖规则

```text
接口层 → 应用层 → 领域层 → 基础设施层

禁止反向依赖：
- 基础设施层不得依赖上层任何模块
- 领域层不得依赖应用层或接口层
- 应用层不得依赖接口层
```

### 3.3 目标模块划分

#### 基础设施层（Infrastructure）

| 模块           | 职责                           | 来源                              |
| -------------- | ------------------------------ | --------------------------------- |
| jarvis_core    | 配置、日志、通用工具、全局状态 | 合并 jarvis_utils + jarvis_config |
| jarvis_git     | Git 操作封装                   | 从 jarvis_utils 提取              |
| jarvis_storage | 文件存储、会话持久化、符号缓存 | 新建                              |

#### 领域层（Domain）

| 模块               | 职责                            | 来源                                 |
| ------------------ | ------------------------------- | ------------------------------------ |
| jarvis_platform    | AI 平台适配（OpenAI/Anthropic） | 保持独立                             |
| jarvis_tools       | 工具注册与调度                  | 保持独立，移除对 jarvis_agent 的依赖 |
| jarvis_mcp         | MCP 协议集成                    | 保持独立                             |
| jarvis_methodology | 方法论管理                      | 保持独立                             |
| jarvis_memory      | 记忆管理                        | 合并 jarvis_memory_organizer         |

#### 应用层（Application）

| 模块              | 职责          | 来源                  |
| ----------------- | ------------- | --------------------- |
| jarvis_agent      | 主 Agent 核心 | 拆分 `__init__.py`    |
| jarvis_code_agent | 代码 Agent    | 保持独立              |
| jarvis_c2rust     | C→Rust 迁移   | 保持独立              |
| jarvis_sec        | 安全扫描      | 拆分超大 checker 文件 |
| jarvis_lsp        | LSP 语言服务  | 保持独立              |
| jarvis_browser    | 浏览器自动化  | 保持独立              |

#### 接口层（Interface）

| 模块            | 职责            | 来源                                     |
| --------------- | --------------- | ---------------------------------------- |
| jarvis_cli      | CLI 入口        | 合并 jarvis_gateway + jarvis_smart_shell |
| jarvis_web      | Web 网关 + 服务 | 合并 jarvis_web_gateway + jarvis_service |
| jarvis_frontend | 前端 Vue 应用   | 从 jarvis_service/frontend 独立          |
| jarvis_windows  | Windows 支持    | 保持独立                                 |

---

## 4. 分阶段实施计划

### 阶段 1：消除循环依赖（优先级：高）

**目标**：打破 jarvis_agent ↔ jarvis_tools ↔ jarvis_code_agent 之间的循环依赖

**具体步骤**：

1. **提取共享接口**：创建 `jarvis_core/interfaces.py`，定义 Agent 与工具之间的抽象接口
2. **jarvis_tools 解耦**：移除 jarvis_tools 中对 jarvis_agent 的直接导入，改用依赖注入或回调
3. **jarvis_code_agent 解耦**：移除 jarvis_code_agent 中对 jarvis_agent 的直接导入
4. **jarvis_utils 解耦**：移除 jarvis_utils 中对 jarvis_platform 的依赖，将 platform 相关逻辑下沉

**验收标准**：

- `grep -rn "from jarvis.jarvis_agent" jarvis_tools/` 返回空
- `grep -rn "from jarvis.jarvis_tools" jarvis_agent/` 仅保留延迟导入
- 所有测试通过

### 阶段 2：拆分超大文件（优先级：高）

**目标**：将超过 2000 行的文件拆分为多个模块

**具体步骤**：

1. **拆分 c_checker.py（9453 行）**：
   - `c_checker/base.py`：基础检查器类
   - `c_checker/buffer_overflow.py`：缓冲区溢出检查
   - `c_checker/memory_safety.py`：内存安全检查
   - `c_checker/integer_overflow.py`：整数溢出检查
   - `c_checker/format_string.py`：格式化字符串检查
   - `c_checker/taint_analysis.py`：污点分析
   - `c_checker/concurrency.py`：并发安全检查

2. **拆分 app.py（7357 行）**：
   - `web/routes/agent_routes.py`：Agent 管理路由
   - `web/routes/node_routes.py`：节点管理路由
   - `web/routes/chat_routes.py`：聊天室路由
   - `web/routes/auth_routes.py`：认证路由
   - `web/routes/terminal_routes.py`：终端路由
   - `web/websocket_manager.py`：WebSocket 连接管理
   - `web/middleware.py`：中间件

3. **拆分 rust_checker.py（3908 行）**：
   - 按检查类型拆分为多个子模块

4. **拆分 jarvis_agent/`__init__.py`（3444 行）**：
   - `agent/core.py`：Agent 核心类
   - `agent/events.py`：事件定义
   - `agent/tool_executor.py`：工具执行器
   - `agent/session.py`：会话管理

**验收标准**：

- 每个文件不超过 1500 行
- 拆分后所有测试通过
- 导入路径更新正确

### 阶段 3：模块重组（优先级：中）

**目标**：按分层架构重新组织模块

**具体步骤**：

1. **合并 jarvis_service 到 jarvis_web_gateway**：消除反向依赖
2. **前端独立**：将 `jarvis_service/frontend/` 移至项目根目录 `frontend/`
3. **删除空模块**：移除 jarvis_data 空目录
4. **合并小模块**：
   - jarvis_git_squash → jarvis_git_utils
   - jarvis_methodology → jarvis_utils
   - jarvis_rules_index → jarvis_agent

**验收标准**：

- 模块间依赖关系符合分层架构
- 无反向依赖
- 所有 CLI 命令正常工作

### 阶段 4：测试覆盖补强（优先级：中）

**目标**：为重构后的核心模块补充测试

**具体步骤**：

1. 为 jarvis_tools 补充单元测试
2. 为 jarvis_web_gateway 补充集成测试
3. 为 jarvis_sec 补充安全检查器测试
4. 建立 CI 覆盖率门槛（核心模块 ≥ 80%）

**验收标准**：

- 测试覆盖率报告显示核心模块覆盖率 ≥ 80%
- CI 流水线包含覆盖率检查

### 阶段 5：文档与规范（优先级：低）

**目标**：建立架构文档与开发规范

**具体步骤**：

1. 编写模块间依赖关系图
2. 建立代码审查清单
3. 编写新模块开发指南
4. 建立架构决策记录（ADR）机制

---

## 5. 风险评估与缓解措施

| 风险                       | 影响 | 概率 | 缓解措施                   |
| -------------------------- | ---- | ---- | -------------------------- |
| 循环依赖解耦引入运行时错误 | 高   | 中   | 使用延迟导入过渡，逐步替换 |
| 大文件拆分导致导入路径错误 | 高   | 中   | 保留旧路径兼容层，逐步废弃 |
| 模块合并导致 CLI 命令失效  | 中   | 低   | 保留旧入口点别名           |
| 前端独立导致构建流程变更   | 中   | 低   | 分阶段迁移，保留旧路径     |
| 测试覆盖不足导致回归       | 高   | 中   | 重构前先补测试             |

---

## 6. 回退策略

每个阶段独立提交，确保可单独回退：

```bash
# 回退到阶段 1 之前
git revert <阶段1提交>

# 回退到阶段 2 之前
git revert <阶段2提交>

# 完全回退到重构前
git reset --hard 5c366bc7d2423597fdc85c214a962260120179df
```

---

## 7. 附录

### 7.1 当前模块依赖关系图

```text
jarvis_agent ←→ jarvis_tools
jarvis_agent ←→ jarvis_code_agent
jarvis_agent ←→ jarvis_sec
jarvis_agent ←→ jarvis_c2rust
jarvis_utils ←→ jarvis_platform
jarvis_web_gateway → jarvis_service
jarvis_web_gateway → jarvis_gateway
jarvis_tools → jarvis_mcp
jarvis_tools → jarvis_code_agent
```

### 7.2 目标模块依赖关系图

```text
接口层：
  jarvis_cli → jarvis_agent → jarvis_tools → jarvis_core
  jarvis_web → jarvis_agent → jarvis_tools → jarvis_core
  jarvis_frontend → jarvis_web（HTTP/WebSocket）

应用层：
  jarvis_agent → jarvis_tools → jarvis_core
  jarvis_code_agent → jarvis_tools → jarvis_core
  jarvis_c2rust → jarvis_agent → jarvis_tools → jarvis_core
  jarvis_sec → jarvis_tools → jarvis_core
  jarvis_lsp → jarvis_core
  jarvis_browser → jarvis_core

领域层：
  jarvis_platform → jarvis_core
  jarvis_tools → jarvis_core
  jarvis_mcp → jarvis_core
  jarvis_methodology → jarvis_core
  jarvis_memory → jarvis_core

基础设施层：
  jarvis_core（无依赖）
  jarvis_git → jarvis_core
  jarvis_storage → jarvis_core
```

### 7.3 关键文件索引

| 文件                                | 当前行数 | 目标行数    | 拆分方案           |
| ----------------------------------- | -------- | ----------- | ------------------ |
| jarvis_sec/checkers/c_checker.py    | 9,453    | < 1,500 × 7 | 按检查类型拆分     |
| jarvis_web_gateway/app.py           | 7,357    | < 1,500 × 5 | 按路由类型拆分     |
| jarvis_sec/checkers/rust_checker.py | 3,908    | < 1,500 × 3 | 按检查类型拆分     |
| jarvis_browser/cli.py               | 3,850    | < 1,500 × 3 | CLI 与业务逻辑分离 |
| jarvis_agent/`__init__.py`          | 3,444    | < 1,500 × 3 | 按职责拆分         |
| jarvis_tools/task_list_manager.py   | 2,671    | < 1,500 × 2 | 按功能拆分         |
| jarvis_utils/utils.py               | 2,389    | < 1,500 × 2 | 按功能拆分         |
| jarvis_tools/registry.py            | 2,311    | < 1,500 × 2 | 按功能拆分         |
| jarvis_tools/gateway_manager.py     | 2,300    | < 1,500 × 2 | 按功能拆分         |
| jarvis_web_gateway/node_manager.py  | 2,245    | < 1,500 × 2 | 按功能拆分         |
