---
name: agent_goal_manager
description: 为当前 Agent 会话提供目标管理工具，支持设置与查询当前目标，并通过 SessionManager 在会话保存与恢复时持久化目标文本。
---

# Agent 目标管理工具规范

## 功能概述

为当前 Agent 会话新增一个内置工具 `goal_manager`，用于管理“当前任务目标”的最新文本。

使用场景：

- Agent 在任务执行过程中需要显式记录当前整体目标。
- 当目标发生变化时，Agent 可以主动更新目标文本。
- 在会话保存、恢复或上下文压缩后，Agent 仍需要能够读取当前最新目标，避免丢失整体任务方向。

调用时机：

- 当整体任务目标发生变更时，Agent 应调用 `goal_manager(action="set", goal="...")` 更新当前目标。
- 当需要确认当前整体目标，或在会话压缩、恢复后重新获取目标时，Agent 应调用 `goal_manager(action="get")` 读取当前目标。

该工具仅面向**当前 Agent 会话**，不承担长期项目记忆或任务列表级目标管理职责。

## 接口定义

### GoalManagerTool 对外工具接口

```python
{
    "action": "set" | "get",
    "goal": str,  # 仅 action=set 时必填
}
```

### GoalManagerTool 内部行为约束

```python
def execute(self, args: Dict[str, Any]) -> Dict[str, Any]
```

工具通过现有 v1.0 工具协议从 `args` 中获取 `agent`，再通过 `agent.session` 访问当前会话状态。

## 输入输出说明

### 输入

- `action`:
  - `set`：设置或更新当前目标文本
  - `get`：获取当前最新目标文本
- `goal`:
  - 仅在 `action=set` 时必填
  - 类型为字符串
  - 表示当前最新目标的纯文本内容

### 输出

- `action=set` 成功时返回：
  - 设置成功提示
  - 当前已保存的目标文本
- `action=get` 成功时返回：
  - 当前目标文本
  - 若尚未设置目标，返回明确提示

### 异常与错误

- 若缺少 `agent`，返回工具执行失败信息。
- 若 `agent` 不存在 `session`，返回工具执行失败信息。
- 若 `action` 不是 `set` 或 `get`，返回参数错误信息。
- 若 `action=set` 且未提供非空 `goal`，返回参数错误信息。

## 功能行为

### 数据存储位置

1. 工具必须将当前目标文本保存到当前会话的 `SessionManager.user_data` 中。
2. 键名必须固定且明确，例如 `current_goal`。
3. 工具不得引入新的独立持久化文件或新的记忆系统。

### 设置行为

1. 当 `action=set` 时，工具读取 `goal` 参数。
2. 若 `goal` 为非空字符串，则写入 `agent.session.user_data`。
3. 重复设置时，新值覆盖旧值，仅保留最新目标文本。
4. 设置成功后，应返回可读的成功信息与当前目标内容。

### 查询行为

1. 当 `action=get` 时，工具从 `agent.session.user_data` 读取当前目标文本。
2. 若存在目标文本，则返回该文本。
3. 若不存在目标文本，则返回“当前未设置目标”之类的明确提示。

### 会话持久化行为

1. 目标文本必须随 `SessionManager.user_data` 一同进入 `_save_agent_state()` 的状态文件。
2. 目标文本必须在 `_restore_agent_state()` 后可重新从 `SessionManager.user_data` 中读取。
3. 工具本身不直接负责写文件，只复用现有 SessionManager 保存/恢复链路。

### 边界条件

- 初始会话未设置目标时：
  - `get` 返回未设置提示，不报错。
- 多次连续更新目标时：
  - 总是返回最新一次设置的值。
- 会话恢复后首次读取目标时：
  - 若恢复文件中存在目标文本，应正确返回。

### 非目标范围

- 不支持目标历史版本查询。
- 不支持任务列表级目标继承。
- 不支持项目长期记忆同步。
- 不新增除纯文本外的结构化目标字段。

## 验收标准

1. 新增内置工具 `goal_manager`，并可被 ToolRegistry 自动注册。
2. `goal_manager` 支持 `action=set` 与 `action=get`。
3. `action=set` 后，`action=get` 返回最新设置的纯文本目标。
4. 目标文本保存在 `agent.session.user_data["current_goal"]` 中。
5. `SessionManager` 保存会话时，目标文本会随现有 `user_data` 写入状态文件。
6. `SessionManager` 恢复会话后，目标文本可重新读取。
7. `goal_manager` 被加入 CodeAgent 默认工具列表。
8. 对无 `agent`、无 `session`、非法 `action`、缺失 `goal` 的情况，工具返回明确错误信息。
9. 不新增独立持久化机制，不改变现有 SessionManager 主存储路径。
