---
name: self_evolving_network_setup
description: 当需要从零开始搭建自进化Agent网络时使用此规则——自进化Agent网络搭建流程规则，指导如何完整搭建自进化Agent网络基础设施。包括：知识库目录结构创建、知识库Agent创建、协作群组创建、网络架构信息保存、规则优化等完整流程。每当用户提及"搭建自进化网络"、"创建Agent网络"、"初始化知识库"、"网络基础设施"或需要从零开始构建自进化Agent网络时触发。
license: MIT
---

# 自进化Agent网络搭建流程规则

## 1. 概述

### 规则目的

本规则提供完整的自进化Agent网络搭建流程指导，确保搭建过程规范、可验证、可回溯。

### 适用场景

- 从零开始搭建自进化Agent网络
- 初始化知识库基础设施
- 创建网络协作群组
- 保存网络架构信息

### 前置条件

- Jarvis服务已启动（jarvis-service）
- 具备gateway_manager工具访问权限
- 具备memory工具访问权限
- 具备execute_script工具访问权限

## 2. 核心概念澄清

**Agent（智能体）**：

- 独立的智能实体，有自己的工作目录、模型、任务
- 使用 `gateway_manager` 工具的 `create_agent` 操作创建
- agent_type 必须是 `'agent'` 或 `'codeagent'`
- 示例：知识库Agent、监控Agent、调度Agent

**Tool（工具）**：

- 供Agent调用的功能模块
- 使用 `meta_agent` 工具创建（不在此规则范围内）
- 示例：memory工具、execute_script工具、read_code工具

**常见错误警示**：

- ❌ 混淆Agent和工具的概念
- ❌ 使用错误的agent_type（如'knowledge'、'monitor'等）
- ❌ 尝试用工具创建方式创建Agent

## 3. 搭建流程

### 阶段1：知识库目录结构创建

#### 目标

创建知识库的目录结构和配置文件。

#### 操作步骤

**步骤1.1：创建知识库根目录**

```bash
mkdir -p /path/to/project/.jarvis/knowledge_base
```

**步骤1.2：创建子目录结构**

```bash
mkdir -p /path/to/project/.jarvis/knowledge_base/{experiences,best_practices,solutions,patterns,collective_wisdom,index}
```

目录说明：

- `experiences/`：存储Agent执行经验
- `best_practices/`：存储最佳实践
- `solutions/`：存储问题解决方案
- `patterns/`：存储可复用模式
- `collective_wisdom/`：存储集体智慧
- `index/`：存储索引文件

**步骤1.3：初始化配置文件**

创建 `config.json`：

```json
{
  "version": "1.0.0",
  "created_at": "2025-01-21T00:00:00Z",
  "knowledge_types": [
    "experiences",
    "best_practices",
    "solutions",
    "patterns",
    "collective_wisdom"
  ],
  "quality_threshold": 0.7,
  "max_entries_per_type": 10000
}
```

创建 `quality_scores.json`：

```json
{
  "experiences": {},
  "best_practices": {},
  "solutions": {},
  "patterns": {},
  "collective_wisdom": {}
}
```

创建 `usage_stats.json`：

```json
{
  "total_queries": 0,
  "successful_retrievals": 0,
  "knowledge_contributions": 0,
  "last_updated": "2025-01-21T00:00:00Z"
}
```

创建 `tags_index.json`：

```json
{
  "by_task_type": {},
  "by_agent": {},
  "by_quality": {},
  "by_date": {}
}
```

#### 验证方法

```bash
ls -la /path/to/project/.jarvis/knowledge_base/
```

预期输出应包含所有子目录和配置文件。

---

### 阶段2：知识库Agent创建

#### 目标

创建负责管理知识库的Agent。

#### 操作步骤

**步骤2.1：创建知识库Agent**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "create_agent",
    "agent_type": "agent",
    "agent_name": "knowledge_base_agent",
    "working_dir": "/path/to/project",
    "task": "你是知识库Agent，负责管理Agent网络的知识库。主要职责：1) 存储和检索Agent经验；2) 维护最佳实践库；3) 提供知识检索服务；4) 整理和优化知识库内容。知识库路径：.jarvis/knowledge_base/"
  }
}
```

**重要参数说明**：

- `agent_type`：必须是 `'agent'`（不能是 'knowledge' 或其他值）
- `working_dir`：建议设置为项目根目录
- `task`：详细描述Agent职责和知识库路径

**步骤2.2：记录Agent ID**
创建成功后，记录返回的 `agent_id`，后续操作需要使用。

#### 验证方法

**方法1：检查Agent状态**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "list_agents"
  }
}
```

**方法2：检查Agent端口**
Agent启动后会在随机端口运行微型Web服务，可通过日志查看。

---

### 阶段3：网络协作群组创建

#### 目标

创建Agent协作群组，便于Agent间通信和协作。

#### 操作步骤

**步骤3.1：创建协作群组**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "create_group",
    "group_name": "self_evolving_network",
    "group_description": "自进化Agent网络协作群组，用于Agent间的知识共享和任务协作"
  }
}
```

**步骤3.2：让知识库Agent加入群组**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "join_group",
    "group_id": "<group_id_from_step_3.1>",
    "agent_id": "<knowledge_base_agent_id>"
  }
}
```

**步骤3.3：验证群组状态**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "get_group",
    "group_id": "<group_id>"
  }
}
```

#### 验证方法

- 群组创建成功返回 `group_id`
- 群组详情中应包含知识库Agent

---

### 阶段4：网络架构信息保存

#### 目标

将网络架构信息保存到项目长期记忆，便于后续查询和恢复。

#### 操作步骤

**步骤4.1：保存网络架构信息**

```json
{
  "name": "memory",
  "arguments": {
    "action": "save",
    "memories": [
      {
        "memory_type": "project_long_term",
        "tags": ["self_evolving_network", "architecture", "knowledge_base"],
        "content": "自进化Agent网络架构信息：\n\n## 知识库配置\n- 路径：.jarvis/knowledge_base/\n- 目录结构：experiences/, best_practices/, solutions/, patterns/, collective_wisdom/, index/\n- 配置文件：config.json, quality_scores.json, usage_stats.json, tags_index.json\n\n## 知识库Agent\n- Agent ID: <knowledge_base_agent_id>\n- Agent名称：knowledge_base_agent\n- 工作目录：/path/to/project\n\n## 协作群组\n- 群组ID: <group_id>\n- 群组名称：self_evolving_network\n- 成员：knowledge_base_agent\n\n## 创建时间\n- 2025-01-21"
      }
    ]
  }
}
```

**步骤4.2：验证记忆保存**

```json
{
  "name": "memory",
  "arguments": {
    "action": "retrieve",
    "memory_types": ["project_long_term"],
    "tags": ["self_evolving_network", "architecture"],
    "limit": 5
  }
}
```

#### 验证方法

- 检索结果应包含刚保存的架构信息
- 内容完整且格式正确

---

### 阶段5：规则优化（可选）

#### 目标

优化相关规则文件，补充概念澄清和最佳实践。

#### 操作步骤

**步骤5.1：创建Code Agent**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "create_agent",
    "agent_type": "codeagent",
    "agent_name": "rule_optimizer",
    "working_dir": "/path/to/Jarvis",
    "task": "优化agent_network目录下的规则文件，添加核心概念澄清章节和Agent创建示例"
  }
}
```

**步骤5.2：发送优化任务**

```json
{
  "name": "gateway_manager",
  "arguments": {
    "action": "send_to_agent",
    "agent_id": "<rule_optimizer_agent_id>",
    "message": "请优化 builtin/rules/agent_network/ 目录下的规则文件，添加核心概念澄清章节，明确区分Agent和工具的概念。"
  }
}
```

#### 验证方法

- 检查规则文件是否包含"核心概念澄清"章节
- 检查是否包含Agent创建示例

## 4. 验证清单

搭建完成后，确认以下项目：

- [ ] **知识库目录结构完整**
  - experiences/、best_practices/、solutions/、patterns/、collective_wisdom/、index/ 目录已创建
  - config.json、quality_scores.json、usage_stats.json、tags_index.json 配置文件已创建

- [ ] **知识库Agent运行正常**
  - Agent ID 已记录
  - Agent 状态为 running
  - Agent 端口可访问

- [ ] **协作群组创建成功**
  - 群组 ID 已记录
  - 知识库Agent已加入群组
  - 群组成员列表正确

- [ ] **网络架构信息已保存**
  - 架构信息已保存到项目长期记忆
  - 可通过检索获取架构信息
  - 信息内容完整准确

- [ ] **规则文件已优化（可选）**
  - 规则文件包含核心概念澄清
  - 规则文件包含Agent创建示例

## 5. 常见问题与解决方案

### 问题1：agent_type 参数错误

**错误现象**：

```
Error: Invalid agent_type 'knowledge'
```

**原因**：agent_type 只能是 `'agent'` 或 `'codeagent'`。

**解决方案**：

```json
{
  "agent_type": "agent" // 正确
}
```

---

### 问题2：混淆Agent和工具概念

**错误现象**：尝试使用工具创建方式创建Agent。

**原因**：不理解Agent和工具的区别。

**解决方案**：

- Agent：独立智能实体，使用 `gateway_manager create_agent` 创建
- Tool：功能模块，使用 `meta_agent` 创建

---

### 问题3：知识库Agent无法启动

**错误现象**：Agent创建后状态异常。

**可能原因**：

1. 工作目录不存在
2. 权限不足
3. 服务未启动

**解决方案**：

1. 确认工作目录存在：`ls -la /path/to/project`
2. 检查权限：`chmod 755 /path/to/project`
3. 确认服务运行：`jarvis-service status`

---

### 问题4：记忆保存失败

**错误现象**：memory save 操作失败。

**可能原因**：

1. memory_types 参数错误
2. tags 格式不正确

**解决方案**：

```json
{
  "memory_type": "project_long_term", // 正确
  "tags": ["tag1", "tag2"], // 必须是数组
  "content": "内容"
}
```

## 6. 最佳实践

### 6.1 使用任务列表管理搭建流程

对于复杂的搭建任务，建议使用 `task_list_manager` 工具进行任务拆分：

```json
{
  "name": "task_list_manager",
  "arguments": {
    "action": "add_tasks",
    "main_goal": "搭建自进化Agent网络",
    "background": "从零开始搭建完整的自进化Agent网络基础设施",
    "tasks_info": [
      {
        "task_name": "创建知识库目录结构",
        "task_desc": "创建知识库目录和配置文件",
        "expected_output": "目录结构完整，配置文件就绪",
        "agent_type": "main"
      },
      {
        "task_name": "创建知识库Agent",
        "task_desc": "使用gateway_manager创建知识库Agent",
        "expected_output": "Agent创建成功，状态正常",
        "agent_type": "main"
      },
      {
        "task_name": "创建协作群组",
        "task_desc": "创建网络协作群组并让Agent加入",
        "expected_output": "群组创建成功，Agent已加入",
        "agent_type": "main"
      },
      {
        "task_name": "保存网络架构信息",
        "task_desc": "将架构信息保存到项目长期记忆",
        "expected_output": "记忆保存成功，可检索",
        "agent_type": "main"
      }
    ]
  }
}
```

### 6.2 每个阶段完成后立即验证

不要等到所有阶段完成才验证，每个阶段完成后立即验证：

- 阶段1：`ls -la` 检查目录结构
- 阶段2：`list_agents` 检查Agent状态
- 阶段3：`get_group` 检查群组状态
- 阶段4：`memory retrieve` 检查记忆保存

### 6.3 保存关键信息到长期记忆

所有关键信息都应保存到项目长期记忆：

- Agent ID
- 群组 ID
- 知识库路径
- 配置参数

### 6.4 记录错误经验到知识库

遇到错误时，将错误信息和解决方案记录到知识库：

```json
{
  "name": "memory",
  "arguments": {
    "action": "save",
    "memories": [
      {
        "memory_type": "project_long_term",
        "tags": ["error_experience", "self_evolving_network"],
        "content": "错误经验：agent_type参数错误\n\n## 错误描述\n尝试使用 'knowledge' 作为 agent_type 创建Agent失败\n\n## 错误原因\nagent_type 只能是 'agent' 或 'codeagent'\n\n## 解决方案\n使用 'agent' 作为 agent_type"
      }
    ]
  }
}
```

## 7. 相关规则

本规则与以下规则配合使用：

1. **self_evolving_network.md**：自进化Agent网络架构规则
2. **knowledge_management.md**：知识管理规则
3. **agent_execution.md**：Agent执行规则
4. **intelligent_scheduling.md**：智能调度规则
5. **fault_recovery.md**：故障恢复规则
6. **network_monitoring.md**：网络监控规则
7. **self_evolution.md**：自进化规则
