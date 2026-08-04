---
name: generate_agents_orchestration
description: 当需要生成Agents编排文件以批量创建Agent时触发。每当用户提及"编排文件"、"批量创建Agent"、"Agent编排"、"OrganizeAgents配置"时触发。不触发：仅创建单个Agent；仅查看Agent列表；Agent间通信不涉及编排。
---

# Agents编排文件生成规则

## 规则简介

此规则用以指导用户创建YAML格式之Agents编排文件，配合`@OrganizeAgents`命令，实现批量创建Agent之功能。

## 汝必守之原则

### 1. 文件格式要求

**要求说明：**

- **必**：用YAML格式
- **必**：用UTF-8编码
- **必**：文件根节点含`agents`列表
- **禁**：编排文件中用Tab缩进（YAML不支持Tab）

### 2. 字段定义

#### agents列表（必填）

`agents`乃一列表，每元素定义一Agent之配置。

#### Agent配置字段

| 字段名                | 类型   | 必填   | 默认值    | 说明               |
| --------------------- | ------ | ------ | --------- | ------------------------------------------------------ |
| `name`                | string | 否     | `agent_N` | Agent名称，用以标识与显示                             |
| `type`                | string | 否     | `code_agent` | Agent类型，如`agent`、`code_agent`等                       |
| `working_dir`         | string | **是** | -         | 工作目录，Agent之工作路径                             |
| `llm_group`           | string | 否     | `default` | 模型组名称          |
| `tool_group`          | string | 否     | `default` | 工具组名称                                             |
| `config_file`         | string | 否     | -         | 配置文件路径                                           |
| `task`                | string | 否     | -         | 初始任务描述                                           |
| `additional_args`     | string | 否     | -         | 附加参数                                               |
| `worktree`            | bool   | 否     | `false`   | 是否用git worktree                                  |
| `quick_mode`          | bool   | 否     | `false`   | 是否启用快速模式                                       |
| `no_interaction_mode` | bool   | 否     | `false`   | 是否启用无交互模式（启用时task必填，**不推荐用**） |

### 3. 字段约束

**必守：**

- `working_dir`必为有效之目录路径
- `type`必为支持之Agent类型（`agent`或`code_agent`）
- **禁**：默认用`no_interaction_mode: true`，当优先用交互模式以便人工确认与调整
- 当`no_interaction_mode: true`时，`task`字段必填
- `name`当具描述性，便于识别

### 操作 1：确定编排需求

创建编排文件前，当明以下信息：

1. 需创建多少Agent？
2. 每Agent之类型为何？
3. 每Agent之工作目录为何？
4. 需指定模型组否？
5. 需设置初始任务否？
6. 需无交互模式否？（仅当明确需无人值守运行时方启用，默认不启用）

### 操作 2：编写编排文件

依需求编写YAML格式之编排文件。

**基本模板（推荐，交互模式）：**

```yaml
agents:
  - name: "agent_name"
    type: "code_agent"
    working_dir: "/path/to/project"
```

**完整模板（交互模式）：**

```yaml
agents:
  - name: "agent_1"
    type: "code_agent"
    working_dir: "/home/user/project1"
    llm_group: "default"
    tool_group: "default"
    task: "实现用户登录功能"

  - name: "agent_2"
    type: "agent"
    working_dir: "/home/user/project2"
    llm_group: "gpt4"
    task: "分析需求文档"

  - name: "agent_3"
    type: "code_agent"
    working_dir: "/home/user/project3"
    worktree: true
    quick_mode: true
```

**无人值守模板（仅当明确需无人值守时用之）：**

```yaml
agents:
  - name: "agent_1"
    type: "code_agent"
    working_dir: "/home/user/project1"
    task: "实现用户登录功能"
    no_interaction_mode: true
```

### 操作 3：验证编排文件

创建编排文件后，验证以下内容：

1. YAML语法正确
2. `agents`列表存在且非空
3. 每Agent配置含必填字段`working_dir`
4. 无交互模式之Agent含`task`字段

## 编排文件示例

### 示例 1：简单编排

创建两个代码Agent，用默认配置：

```yaml
agents:
  - name: "frontend_dev"
    type: "code_agent"
    working_dir: "/home/user/frontend"

  - name: "backend_dev"
    type: "code_agent"
    working_dir: "/home/user/backend"
```

### 示例 2：带任务之编排（交互模式，推荐）

创建多个Agent并分配初始任务，用交互模式便于人工确认：

```yaml
agents:
  - name: "feature_auth"
    type: "code_agent"
    working_dir: "/home/user/myapp"
    task: "实现用户认证模块，包括登录、注册、密码重置功能"

  - name: "feature_api"
    type: "code_agent"
    working_dir: "/home/user/myapp"
    task: "设计并实现 RESTful API 接口"

  - name: "docs_writer"
    type: "agent"
    working_dir: "/home/user/myapp"
    task: "编写 API 文档"
```

### 示例 3：多项目编排

跨多个项目创建Agent：

```yaml
agents:
  - name: "project_a_dev"
    type: "code_agent"
    working_dir: "/home/user/projects/project_a"
    llm_group: "claude"

  - name: "project_b_dev"
    type: "code_agent"
    working_dir: "/home/user/projects/project_b"
    llm_group: "gpt4"

  - name: "shared_lib_dev"
    type: "code_agent"
    working_dir: "/home/user/projects/shared_lib"
    worktree: true
```

## 最佳实践

### 1. 命名规范

- 用描述性名称，如`frontend_dev`、`api_designer`
- 避用无意义名称，如`agent_1`、`test`

### 2. 工作目录

- 用绝对路径，避路径歧义
- 确保目录存在且有访问权限

### 3. 任务描述

- 任务描述当具体、可执行
- 含明确之目标与范围
- 避过于笼统之描述

### 4. 交互模式优先

- **必**：默认用交互模式（不设`no_interaction_mode`或设为`false`）
- 交互模式允许人工确认与调整Agent行为，提高可控性
- 仅当明确需无人值守运行时方启用`no_interaction_mode: true`

### 5. 模型组选择

- 依任务复杂度选合适之模型组
- 简单任务可用默认模型组
- 复杂任务建议用高级模型组

## 检查清单

创建编排文件后，汝必确认：

- [ ] 文件用YAML格式
- [ ] 文件含`agents`列表
- [ ] 每Agent配置含`working_dir`字段
- [ ] 默认用交互模式（未设`no_interaction_mode`或设为`false`）
- [ ] 如有用`no_interaction_mode: true`之Agent，确认含`task`字段
- [ ] 所有路径用正确格式
- [ ] YAML语法正确（无缩进错误）

## 使用方式

1. 创建编排文件（如`orchestration.yaml`）
2. 在Jarvis中输入`@OrganizeAgents`
3. 依提示输入编排文件路径
4. 等待批量创建完成

## 相关资源

- OrganizeAgents命令：内置命令，用于批量创建Agent
- gateway_manager工具：底层实现，支持create_agent操作
