---
name: execution_terminal_restore_spec
description: 修复前端聊天界面中未结束 shell 执行在切换 agent 后 xterm 消失的问题，确保执行输出持续缓存、切换期间不丢失未完成 execution 消息，并在切回时重建可交互终端
---

# 功能概述

在前端聊天界面中（包括 VSCode 扩展聊天面板与服务前端页面），当某个 Agent 的 shell/terminal 执行尚未结束时，前端必须持续保留该执行会话的输出缓存和对应的未完成 execution 消息。用户切换到其他 Agent 后，原执行会话仍应继续累积输出，且不得因为页面切换逻辑清空该 Agent 的未完成 execution 内存状态；当用户再切回原 Agent 时，前端必须基于缓存内容重建 xterm 视图，并允许用户继续与该终端交互。

该能力用于解决“切换 Agent 后未结束的 xterm 窗口消失且无法恢复”的问题。

# 接口定义

## 输入数据结构

### ChatMessageItem

execution 类型消息必须支持以下字段：

```ts
type ChatMessageItem = {
  text?: string;
  variant?: string;
  lang?: string;
  executionId?: string;
  executionBuffer?: string;
  finished?: boolean;
};
```

字段说明：

- `variant === "execution"`：表示该消息为终端执行消息
- `executionId`：终端执行会话唯一标识
- `executionBuffer`：当前执行会话的完整输出缓存
- `finished`：是否已结束；`false` 表示仍可交互，`true` 表示仅展示历史

## 前端行为接口

### renderExecutionMessage(item, agentId)

输入：
- `item`：execution 消息对象
- `agentId`：当前渲染的 Agent ID

输出：
- 返回可插入消息列表的 HTMLDivElement

行为要求：
- 当 `finished === false` 时，返回交互式 xterm 容器
- 当 `finished === true` 时，返回静态历史容器
- 若已有 xterm 实例但其 DOM 容器已失效，必须允许重建

### renderMessages(messageList, agentId, isInitialLoad)

输入：
- `messageList`：当前 Agent 的消息列表
- `agentId`：当前选中的 Agent ID
- `isInitialLoad`：是否首次/全量加载

行为要求：
- 对 execution 消息执行全量渲染时，必须正确恢复未结束的 xterm
- 切换 Agent、历史加载、首次加载都必须遵循同一恢复规则

# 输入输出说明

## 输入

1. Agent 状态消息中的 `messages`
   - 类型：`ChatMessageItem[]`
   - 约束：execution 消息若未结束，必须包含对应 `executionId`

2. executionBuffer
   - 类型：`string`
   - 约束：表示该 executionId 当前完整终端输出，不是增量片段

3. finished
   - 类型：`boolean | undefined`
   - 含义：
     - `false`：执行仍在进行，允许继续交互
     - `true`：执行已完成，仅展示静态历史

## 输出

1. 未结束执行的可交互 xterm 节点
2. 已结束执行的静态历史节点
3. 在 Agent 切换前后保持一致的执行输出展示

# 功能行为

## 正常情况

1. 当 execution 消息首次出现且 `finished === false` 时：
   - 创建 xterm 实例
   - 将 `executionBuffer` 回放到终端
   - 绑定输入事件，使用户可继续交互

2. 当同一 executionId 收到新的 `executionBuffer` 时：
   - 前端根据旧缓存与新缓存差异追加输出
   - 不重复写入已存在内容

3. 当用户切换到其他 Agent 时：
   - 原 execution 消息的缓存内容继续由状态源维护
   - 原未完成 execution 消息不得因为切换逻辑被直接从内存消息列表中清空
   - 前端不要求保留旧 DOM 节点的可见性
   - 允许旧 xterm DOM 从当前消息列表中移除

4. 当用户切换回原 Agent 时：
   - 若原 executionId 对应的 xterm 仍有效，可复用
   - 若原 xterm 已脱离当前 DOM 或无法继续显示，必须重建新的 xterm
   - 重建后必须基于完整 `executionBuffer` 重新回放历史输出
   - 重建后用户必须仍可继续输入
   - 前端内部若维护 execution terminal 实例缓存，必须按 `agentId + executionId` 做 namespacing，不能仅以 `executionId` 作为全局唯一键

5. 当 execution 结束且 `finished === true` 时：
   - 释放该 executionId 对应的交互式 xterm 资源
   - 若前端内部使用复合键管理终端实例，则释放逻辑也必须基于同一复合键定位
   - 使用静态历史内容展示 `executionBuffer`
   - 不再为该消息创建可交互终端

## 边界情况

1. `executionId` 为空时：
   - 前端可使用默认占位 ID 渲染，但必须保持同一消息在当前生命周期内行为一致

2. `executionBuffer` 为空字符串时：
   - 仍可创建空 xterm 容器，等待后续输出

3. 全量渲染时 execution 消息顺序未变化，但 `executionBuffer` 或 `finished` 变化：
   - 前端必须识别这类变化并更新 execution 视图

4. 历史消息加载时包含 execution 消息：
   - 已 finished 的 execution 显示为静态历史
   - 未 finished 的 execution 若属于当前 Agent 当前状态，必须可恢复为交互式 xterm

5. 某些前端实现可能不会将未 finished execution 持久化到历史存储：
   - 此时切换 Agent 不得依赖“重新加载历史”来恢复未完成 execution
   - 必须保留该 execution 的内存消息和终端缓存，供切回时恢复

6. 若多个 Agent 可能产生相同的 `executionId`：
   - 前端内部 terminal 缓存、DOM host 映射、重建状态都必须按 `agentId + executionId` 隔离
   - 发送到后端协议中的 `execution_id` 字段仍保持原始值，不应发送前端内部复合键

## 异常情况

1. 如果旧 xterm 实例存在但已无法挂载到当前页面：
   - 必须销毁无效引用并重建

2. 如果缓存回放失败：
   - 不得导致整个消息列表渲染中断
   - 至少应保留容器并允许后续状态再次驱动恢复

# 验收标准

1. 当某个 Agent 存在未结束 shell 执行时，切换到其他 Agent，原执行输出仍持续缓存。
2. 切换 Agent 不得清空该 Agent 未完成 execution 的内存消息项。
3. 切换回原 Agent 后，xterm 必须重新出现，且显示切换期间累计的完整历史输出。
4. 切回后用户必须可以继续向该 xterm 输入内容并交互。
5. 对于 `finished === true` 的 execution 消息，前端必须显示静态历史，而不是交互式 xterm。
6. 若多个 Agent 的 `executionId` 相同，前端也不得发生 terminal 实例复用、输出串台或输入错发。
7. execution 消息在全量渲染、首次加载、历史加载、Agent 切换等路径下，`executionBuffer` 与 `finished` 变化都不能被遗漏。
8. 修改后不得破坏普通消息、streaming 消息和历史分页加载功能。

# 验证方法

1. 启动一个会产生持续输出且未结束的 shell 执行。
2. 记录当前 xterm 已显示内容。
3. 切换到另一个 Agent，并等待原执行继续产生输出。
4. 切换回原 Agent，确认：
   - xterm 重新显示；
   - 显示内容包含切换期间新增输出；
   - 可以继续输入。
5. 再验证一个已结束 execution，确认其显示为静态历史内容。
