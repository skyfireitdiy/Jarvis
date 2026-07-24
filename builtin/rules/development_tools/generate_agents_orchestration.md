---
name: generate_agents_orchestration
description: 当需要生成Agents编排文件时使用此规则——Agents编排文件生成规则，用于指导用户创建YAML格式的Agent编排配置文件，供@OrganizeAgents命令批量创建Agent使用。包括：编排文件结构说明、字段定义、配置示例、最佳实践。每当用户提及"编排文件"、"批量创建Agent"、"Agent编排"、"OrganizeAgents配置"或需要批量创建多个Agent时触发。
---

# Agents 编排文件生成规则

## 规则简介

本规则用于指导用户创建 YAML 格式的 Agents 编排文件，配合 `@OrganizeAgents` 命令实现批量创建 Agent 的功能。

## 你必须遵守的原则

### 1. 文件格式要求

**要求说明：**

- **必须**：使用 YAML 格式
- **必须**：使用 UTF-8 编码
- **必须**：文件根节点包含 `agents` 列表
- **禁止**：在编排文件中使用 Tab 缩进（YAML 不支持 Tab）

### 2. 字段定义

#### agents 列表（必填）

`agents` 是一个列表，每个元素定义一个 Agent 的配置。

#### Agent 配置字段

| 字段名                | 类型   | 必填   | 默认值    | 说明                                                   |
| --------------------- | ------ | ------ | --------- | ------------------------------------------------------ |
| `name`                | string | 否     | `agent_N` | Agent 名称，用于标识和显示                             |
| `type`                | string | 否     | `code`    | Agent 类型，如 `code`、`chat` 等                       |
| `working_dir`         | string | **是** | -         | 工作目录，Agent 的工作路径                             |
| `llm_group`           | string | 否     | `default` | 模型组名称                                             |
| `tool_group`          | string | 否     | `default` | 工具组名称                                             |
| `config_file`         | string | 否     | -         | 配置文件路径                                           |
| `task`                | string | 否     | -         | 初始任务描述                                           |
| `additional_args`     | string | 否     | -         | 附加参数                                               |
| `worktree`            | bool   | 否     | `false`   | 是否使用 git worktree                                  |
| `quick_mode`          | bool   | 否     | `false`   | 是否启用快速模式                                       |
| `no_interaction_mode` | bool   | 否     | `false`   | 是否启用无交互模式（启用时 task 必填，**不推荐使用**） |

### 3. 字段约束

**必须遵守：**

- `working_dir` 必须是有效的目录路径
- `type` 必须是支持的 Agent 类型（通常为 `code` 或 `chat`）
- **禁止**：默认使用 `no_interaction_mode: true`，应优先使用交互模式以便人工确认和调整
- 当 `no_interaction_mode: true` 时，`task` 字段必填
- `name` 应具有描述性，便于识别

## 你必须执行的操作

### 操作 1：确定编排需求

在创建编排文件前，明确以下信息：

1. 需要创建多少个 Agent？
2. 每个 Agent 的类型是什么？
3. 每个 Agent 的工作目录是什么？
4. 是否需要指定模型组？
5. 是否需要设置初始任务？
6. 是否需要无交互模式？（仅当明确需要无人值守运行时才启用，默认不启用）

### 操作 2：编写编排文件

根据需求编写 YAML 格式的编排文件。

**基本模板（推荐，交互模式）：**

```yaml
agents:
  - name: "agent_name"
    type: "code"
    working_dir: "/path/to/project"
```

**完整模板（交互模式）：**

```yaml
agents:
  - name: "agent_1"
    type: "code"
    working_dir: "/home/user/project1"
    llm_group: "default"
    tool_group: "default"
    task: "实现用户登录功能"

  - name: "agent_2"
    type: "chat"
    working_dir: "/home/user/project2"
    llm_group: "gpt4"
    task: "分析需求文档"

  - name: "agent_3"
    type: "code"
    working_dir: "/home/user/project3"
    worktree: true
    quick_mode: true
```

**无人值守模板（仅当明确需要无人值守时使用）：**

```yaml
agents:
  - name: "agent_1"
    type: "code"
    working_dir: "/home/user/project1"
    task: "实现用户登录功能"
    no_interaction_mode: true
```

### 操作 3：验证编排文件

创建编排文件后，验证以下内容：

1. YAML 语法正确
2. `agents` 列表存在且非空
3. 每个 Agent 配置包含必填字段 `working_dir`
4. 无交互模式的 Agent 包含 `task` 字段

## 编排文件示例

### 示例 1：简单编排

创建两个代码 Agent，使用默认配置：

```yaml
agents:
  - name: "frontend_dev"
    type: "code"
    working_dir: "/home/user/frontend"

  - name: "backend_dev"
    type: "code"
    working_dir: "/home/user/backend"
```

### 示例 2：带任务的编排（交互模式，推荐）

创建多个 Agent 并分配初始任务，使用交互模式便于人工确认：

```yaml
agents:
  - name: "feature_auth"
    type: "code"
    working_dir: "/home/user/myapp"
    task: "实现用户认证模块，包括登录、注册、密码重置功能"

  - name: "feature_api"
    type: "code"
    working_dir: "/home/user/myapp"
    task: "设计并实现 RESTful API 接口"

  - name: "docs_writer"
    type: "chat"
    working_dir: "/home/user/myapp"
    task: "编写 API 文档"
```

### 示例 3：多项目编排

跨多个项目创建 Agent：

```yaml
agents:
  - name: "project_a_dev"
    type: "code"
    working_dir: "/home/user/projects/project_a"
    llm_group: "claude"

  - name: "project_b_dev"
    type: "code"
    working_dir: "/home/user/projects/project_b"
    llm_group: "gpt4"

  - name: "shared_lib_dev"
    type: "code"
    working_dir: "/home/user/projects/shared_lib"
    worktree: true
```

## 最佳实践

### 1. 命名规范

- 使用描述性名称，如 `frontend_dev`、`api_designer`
- 避免使用无意义名称，如 `agent_1`、`test`

### 2. 工作目录

- 使用绝对路径，避免路径歧义
- 确保目录存在且有访问权限

### 3. 任务描述

- 任务描述应具体、可执行
- 包含明确的目标和范围
- 避免过于笼统的描述

### 4. 交互模式优先

- **必须**：默认使用交互模式（不设置 `no_interaction_mode` 或设为 `false`）
- 交互模式允许人工确认和调整 Agent 行为，提高可控性
- 仅当明确需要无人值守运行时才启用 `no_interaction_mode: true`

### 5. 模型组选择

- 根据任务复杂度选择合适的模型组
- 简单任务可使用默认模型组
- 复杂任务建议使用高级模型组

## 检查清单

在创建编排文件后，你必须确认：

- [ ] 文件使用 YAML 格式
- [ ] 文件包含 `agents` 列表
- [ ] 每个 Agent 配置包含 `working_dir` 字段
- [ ] 默认使用交互模式（未设置 `no_interaction_mode` 或设为 `false`）
- [ ] 如有使用 `no_interaction_mode: true` 的 Agent，确认包含 `task` 字段
- [ ] 所有路径使用正确的格式
- [ ] YAML 语法正确（无缩进错误）

## 使用方式

1. 创建编排文件（如 `orchestration.yaml`）
2. 在 Jarvis 中输入 `@OrganizeAgents`
3. 根据提示输入编排文件路径
4. 等待批量创建完成

## 相关资源

- OrganizeAgents 命令：内置命令，用于批量创建 Agent
- gateway_manager 工具：底层实现，支持 create_agent 操作
