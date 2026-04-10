---
name: websocket_message_performance_optimization
description: 优化VSCode插件中WebSocket消息处理的性能，解决消息处理慢、UI卡顿的问题
---

# WebSocket消息处理性能优化规范

## 功能概述

优化Jarvis VSCode插件中WebSocket消息处理的性能，解决以下问题：

1. `postPanelState()` 调用过于频繁，导致UI更新开销大
2. 流式输出（STREAM_CHUNK）处理存在双重更新问题
3. `renderAgentListView()` 全量重绘导致性能问题
4. `persistAgentHistory` 频繁写入存储
5. 消息数组传输开销大

## 优化目标

1. 减少不必要的UI更新调用
2. 实现消息更新的节流（throttle）机制
3. 实现存储写入的防抖（debounce）机制
4. 优化流式消息处理逻辑
5. 保持功能完整性，不破坏现有行为

## 接口定义

### 新增工具函数

```typescript
// 节流函数
function throttle<T extends (...args: any[]) => any>(func: T, delay: number): T;

// 防抖函数
function debounce<T extends (...args: any[]) => any>(func: T, delay: number): T;
```

### 修改的方法

#### 1. `postPanelState()`

- **修改前**: 每次调用立即执行
- **修改后**: 使用节流机制，100ms内最多执行一次

#### 2. `persistAgentHistory(agentId: string)`

- **修改前**: 每次调用立即执行
- **修改后**: 使用防抖机制，500ms内只执行一次

#### 3. `handleOutputPayload()`

- **修改前**: `STREAM_CHUNK` 处理后额外调用 `postPanelState()`
- **修改后**: 移除多余的 `postPanelState()` 调用

#### 4. `renderAgentListView()`

- **修改前**: 每次调用都重新生成整个HTML
- **修改后**: 添加防抖机制，100ms内最多执行一次

## 输入输出说明

### 节流函数

- **输入**:
  - `func`: 需要节流的函数
  - `delay`: 节流延迟时间（毫秒）
- **输出**: 节流后的函数
- **行为**: 在 `delay` 时间内多次调用，只执行最后一次

### 防抖函数

- **输入**:
  - `func`: 需要防抖的函数
  - `delay`: 防抖延迟时间（毫秒）
- **输出**: 防抖后的函数
- **行为**: 在 `delay` 时间内多次调用，只执行最后一次，且每次调用都会重置计时器

## 功能行为

### 正常情况

1. **节流机制**:
   - 第一次调用立即执行
   - 在节流期间内的后续调用会被忽略
   - 节流期结束后，下一次调用会立即执行

2. **防抖机制**:
   - 每次调用都会重置计时器
   - 只有最后一次调用后的 `delay` 毫秒内没有新调用，才会执行

3. **流式消息处理**:
   - `STREAM_START`: 创建新的流消息
   - `STREAM_CHUNK`: 更新流消息内容，不触发额外的UI更新
   - `STREAM_END`: 清理流消息状态

### 边界情况

1. **节流函数在节流期间被多次调用**:
   - 只有第一次调用会执行
   - 后续调用在节流期结束后才会执行

2. **防抖函数在防抖期间被多次调用**:
   - 每次调用都重置计时器
   - 只有最后一次调用会执行

3. **WebSocket消息处理速度超过UI更新速度**:
   - 节流机制确保UI不会被过度更新
   - 消息状态会正确累积

### 异常情况

1. **节流/防抖函数执行时发生异常**:
   - 异常会被捕获并记录
   - 不会影响后续调用

2. **WebView未初始化**:
   - `postPanelState()` 会检查 `this.currentPanel` 是否存在
   - 不存在时直接返回，不执行更新

## 验收标准

### 1. 节流机制验证

- [ ] `postPanelState()` 在100ms内多次调用时，只执行一次
- [ ] 节流后的函数保持正确的 `this` 上下文
- [ ] 节流期结束后，下一次调用能正常执行

### 2. 防抖机制验证

- [ ] `persistAgentHistory()` 在500ms内多次调用时，只执行最后一次
- [ ] `renderAgentListView()` 在100ms内多次调用时，只执行最后一次
- [ ] 防抖后的函数保持正确的 `this` 上下文

### 3. 流式消息处理验证

- [ ] `STREAM_CHUNK` 处理后不再额外调用 `postPanelState()`
- [ ] 流式消息能正确显示和更新
- [ ] `STREAM_END` 能正确清理流消息状态

### 4. 功能完整性验证

- [ ] 所有现有功能正常工作
- [ ] 消息发送和接收正常
- [ ] Agent状态更新正常
- [ ] 执行终端输出正常

### 5. 性能验证

- [ ] WebSocket消息处理延迟降低
- [ ] UI更新频率降低
- [ ] 存储写入频率降低

## 实现步骤

1. 添加节流和防抖工具函数
2. 修改 `postPanelState()` 使用节流
3. 修改 `persistAgentHistory()` 使用防抖
4. 修改 `renderAgentListView()` 使用防抖
5. 修复 `handleOutputPayload()` 中的双重更新问题
6. 验证所有功能正常工作

## 风险评估

- **风险**: 节流/防抖可能导致某些状态更新延迟
- **缓解**: 选择合适的延迟时间（100ms/500ms），确保用户体验不受影响

- **风险**: 修改核心消息处理逻辑可能引入bug
- **缓解**: 保持原有逻辑不变，只添加节流/防抖包装

- **风险**: `this` 上下文可能丢失
- **缓解**: 使用箭头函数或 `bind` 确保上下文正确
