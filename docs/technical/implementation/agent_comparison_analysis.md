# Jarvis vs claude-code Agent实现对比分析报告

## 1. 项目概述

### 1.1 分析范围

**Jarvis项目**：

- 核心文件：`src/jarvis/jarvis_agent/jarvis.py`, `src/jarvis/jarvis_agent/run_loop.py`, `src/jarvis/jarvis_agent/tool_executor.py`, `src/jarvis/jarvis_tools/registry.py`
- 技术栈：Python + Typer + Rich
- 架构模式：模块化单体应用

**claude-code项目**：

- 核心文件：`src/Tool.ts`, `src/tools.ts`, `src/QueryEngine.ts`
- 技术栈：TypeScript + Bun + React/Ink
- 架构模式：面向对象 + 异步生成器

### 1.2 代码来源

- Jarvis分析来源：
  - `/home/skyfire/code/Jarvis/src/jarvis/jarvis_agent/jarvis.py` (1496行)
  - `/home/skyfire/code/Jarvis/src/jarvis/jarvis_agent/run_loop.py` (908行)
  - `/home/skyfire/code/Jarvis/src/jarvis/jarvis_agent/tool_executor.py` (219行)
  - `/home/skyfire/code/Jarvis/src/jarvis/jarvis_tools/registry.py` (1480行)

- claude-code分析来源：
  - `/home/skyfire/code/claude-code/src/Tool.ts` (792行)
  - `/home/skyfire/code/claude-code/src/tools.ts` (389行)
  - `/home/skyfire/code/claude-code/src/QueryEngine.ts` (1295行)

---

## 2. 核心功能对比表

### 2.1 Agent初始化

| 维度           | Jarvis                            | claude-code                        | 差异分析                                  |
| -------------- | --------------------------------- | ---------------------------------- | ----------------------------------------- |
| **初始化方式** | CLI入口 `run_cli()` + Typer框架   | `QueryEngine` 类构造函数           | Jarvis基于命令式，claude-code基于类实例化 |
| **配置加载**   | YAML配置文件 + 环境变量           | `QueryEngineConfig` 对象注入       | Jarvis配置分散，claude-code集中管理       |
| **状态管理**   | `AgentStateManager` 单例 + 线程锁 | `AppState` 不可变状态 + 函数式更新 | Jarvis可变状态，claude-code函数式         |
| **会话恢复**   | `--restore-session` 参数          | `initialMessages` 参数             | 两者都支持会话恢复                        |

### 2.2 工具系统

| 维度             | Jarvis                          | claude-code                              | 差异分析                              |
| ---------------- | ------------------------------- | ---------------------------------------- | ------------------------------------- |
| **工具定义**     | `ToolRegistry` 类 + JSON Schema | `Tool<Input, Output, P>` 泛型接口        | Jarvis动态注册，claude-code静态类型   |
| **工具调用格式** | Jsonnet格式 `<TOOL_CALL>` 标签  | Anthropic API原生格式                    | Jarvis自定义格式，claude-code标准格式 |
| **工具发现**     | `get_all_tools()` 动态加载      | `getAllBaseTools()` 静态列表 + 条件导入  | Jarvis支持MCP动态扩展                 |
| **权限控制**     | `execute_tool_confirm` 布尔标志 | `ToolPermissionContext` + `CanUseToolFn` | claude-code权限系统更完善             |
| **工具别名**     | 不支持                          | `aliases?: string[]`                     | claude-code支持向后兼容               |
| **进度回调**     | 不支持                          | `onProgress?: ToolCallProgress<P>`       | claude-code支持实时进度               |

### 2.3 执行流程

| 维度           | Jarvis                                        | claude-code                              | 差异分析                            |
| -------------- | --------------------------------------------- | ---------------------------------------- | ----------------------------------- |
| **主循环**     | `AgentRunLoop` 类 + `_handle_tool_calls()`    | `QueryEngine.submitMessage()` 异步生成器 | Jarvis同步循环，claude-code异步流   |
| **工具执行**   | `execute_tool_call()` 函数                    | `tool.call()` 方法                       | Jarvis过程式，claude-code面向对象   |
| **多工具调用** | 支持，顺序执行                                | 支持，并行/顺序可配置                    | claude-code更灵活                   |
| **上下文压缩** | `check_and_compress_context()` 基于token/轮次 | 内置压缩机制 + snip功能                  | 两者都有压缩机制                    |
| **中断处理**   | `_handle_interrupt_with_input()`              | `AbortController`                        | Jarvis用户交互，claude-code信号机制 |

### 2.4 错误处理

| 维度               | Jarvis                            | claude-code                     | 差异分析                            |
| ------------------ | --------------------------------- | ------------------------------- | ----------------------------------- |
| **工具解析错误**   | 返回错误信息 + 工具使用提示       | 类型验证 + 错误码               | Jarvis用户友好，claude-code结构化   |
| **工具执行异常**   | try-catch + 错误消息打印          | `ToolResult<T>` 类型封装        | Jarvis简单捕获，claude-code类型安全 |
| **连续无工具调用** | `_track_no_tool_call()` + LLM修复 | 未明确实现                      | Jarvis有自动修复机制                |
| **权限拒绝**       | `user_confirm()` 交互确认         | `PermissionResult` + 拒绝跟踪   | claude-code权限系统更完善           |
| **API错误**        | 未详细分析                        | `categorizeRetryableAPIError()` | claude-code有错误分类机制           |

---

## 3. 架构设计差异分析

### 3.1 模块划分

**Jarvis架构**：

```
jarvis/
├── jarvis_agent/          # Agent核心
│   ├── jarvis.py          # CLI入口
│   ├── run_loop.py        # 执行循环
│   ├── tool_executor.py   # 工具执行器
│   └── agent_manager.py   # Agent管理
├── jarvis_tools/          # 工具系统
│   ├── registry.py        # 工具注册表
│   └── base.py            # 工具基类
└── jarvis_utils/          # 工具函数
```

**claude-code架构**：

```
src/
├── Tool.ts                # 工具类型定义
├── tools.ts               # 工具注册
├── QueryEngine.ts         # 查询引擎
├── query.ts               # 查询实现
├── tools/                 # 工具实现
│   ├── BashTool/
│   ├── FileEditTool/
│   └── ...
└── utils/                 # 工具函数
```

### 3.2 接口设计

**Jarvis工具接口**：

```python
class OutputHandlerProtocol(Protocol):
    def name(self) -> str: ...
    def can_handle(self, response: str) -> bool: ...
    def prompt(self) -> str: ...
    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]: ...
```

**claude-code工具接口**：

```typescript
type Tool<Input, Output, P> = {
  aliases?: string[]
  searchHint?: string
  call(args: z.infer<Input>, context: ToolUseContext, ...): Promise<ToolResult<Output>>
  description(input: z.infer<Input>, options: {...}): Promise<string>
  readonly inputSchema: Input
  outputSchema?: z.ZodType<unknown>
}
```

### 3.3 依赖关系

**Jarvis依赖**：

- 外部：typer, rich, yaml, pyte
- 内部：jarvis_utils, jarvis_mcp, jarvis_config

**claude-code依赖**：

- 外部：@anthropic-ai/sdk, zod, lodash-es, react, ink
- 内部：services/, utils/, components/

---

## 4. 性能优化对比

### 4.1 上下文管理

| 维度             | Jarvis                        | claude-code              |
| ---------------- | ----------------------------- | ------------------------ |
| **Token监控**    | `get_remaining_token_count()` | 内置usage跟踪            |
| **压缩触发**     | 25%剩余token 或 轮次阈值      | 类似机制                 |
| **压缩策略**     | 调用 `summarize_context()`    | snip + compaction        |
| **文件状态缓存** | 未明确                        | `FileStateCache` LRU缓存 |

### 4.2 资源利用

| 维度         | Jarvis          | claude-code                  |
| ------------ | --------------- | ---------------------------- |
| **并发模型** | 单线程 + 异步IO | 异步生成器 + AbortController |
| **内存管理** | Python GC       | Bun运行时优化                |
| **工具执行** | 顺序执行        | 支持并行执行                 |

---

## 5. 扩展性分析

### 5.1 插件系统

**Jarvis**：

- MCP协议支持：`McpClient`, `SSEMcpClient`, `StdioMcpClient`, `StreamableMcpClient`
- 动态工具加载：`get_all_tools()` 从配置目录加载
- 角色系统：`get_roles_dirs()` 支持多角色配置

**claude-code**：

- 条件导入：`feature()` 函数控制功能开关
- Agent定义：`AgentDefinition` 支持子agent
- 技能系统：`SkillTool` 支持动态技能发现

### 5.2 配置管理

**Jarvis**：

- YAML配置文件
- 环境变量覆盖
- 命令行参数优先

**claude-code**：

- `QueryEngineConfig` 集中配置
- `AppState` 不可变状态
- 函数式状态更新

### 5.3 第三方集成

**Jarvis**：

- MCP协议：支持多种传输方式
- Git集成：自动检测仓库、代码模式切换
- Tmux集成：任务派发到tmux窗口

**claude-code**：

- MCP协议：`MCPServerConnection`
- LSP集成：`LSPTool`
- Web工具：`WebFetchTool`, `WebSearchTool`

---

## 6. 各自优势与不足

### 6.1 Jarvis优势

1. **MCP协议支持完善**：支持SSE、Stdio、Streamable多种传输方式
2. **自动修复机制**：连续无工具调用时自动使用LLM修复
3. **用户交互友好**：Rich库提供美观的终端输出
4. **Git仓库自动检测**：自动切换到代码开发模式
5. **Tmux集成**：支持任务派发到tmux窗口
6. **Jsonnet格式**：支持注释和尾随逗号，更灵活

### 6.2 Jarvis不足

1. **类型安全不足**：Python动态类型，缺少编译时检查
2. **权限系统简单**：只有布尔标志控制确认
3. **工具接口不够丰富**：缺少别名、进度回调等特性
4. **状态管理可变**：使用全局单例，可能存在线程安全问题
5. **异步支持有限**：主要使用同步模型

### 6.3 claude-code优势

1. **类型安全**：TypeScript + Zod提供完整的类型检查
2. **权限系统完善**：`ToolPermissionContext` 支持细粒度控制
3. **工具接口丰富**：支持别名、搜索提示、进度回调
4. **函数式状态管理**：不可变状态 + 纯函数更新
5. **异步生成器**：支持流式响应和并行处理
6. **Feature Flag**：支持条件编译和功能开关

### 6.4 claude-code不足

1. **学习曲线陡峭**：复杂的类型系统和函数式编程
2. **调试困难**：异步生成器和不可变状态增加调试复杂度
3. **依赖较多**：React/Ink增加包体积
4. **MCP支持相对简单**：主要关注Stdio传输

---

## 7. 优化建议

### 7.1 Jarvis可借鉴claude-code的优化点

#### 7.1.1 增强类型安全

**建议**：引入类型注解和静态检查

```python
# 当前实现
def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
    ...

# 建议实现
from typing import Protocol, TypeVar, Generic
from dataclasses import dataclass

Input = TypeVar('Input')
Output = TypeVar('Output')

@dataclass
class ToolResult(Generic[Output]):
    data: Output
    new_messages: Optional[List[Message]] = None
    context_modifier: Optional[Callable[[AgentContext], AgentContext]] = None

class Tool(Protocol[Input, Output]):
    @property
    def name(self) -> str: ...

    @property
    def aliases(self) -> List[str]: ...

    @property
    def input_schema(self) -> Type[Input]: ...

    async def call(
        self,
        args: Input,
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None
    ) -> ToolResult[Output]: ...
```

#### 7.1.2 完善权限系统

**建议**：引入细粒度权限控制

```python
# 建议实现
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set

class PermissionMode(Enum):
    DEFAULT = "default"
    BYPASS = "bypass"
    AUTO = "auto"

@dataclass
class ToolPermissionContext:
    mode: PermissionMode
    always_allow_rules: Dict[str, Set[str]]  # tool_name -> allowed_params
    always_deny_rules: Dict[str, Set[str]]
    always_ask_rules: Dict[str, Set[str]]
    is_bypass_permissions_mode_available: bool
    should_avoid_permission_prompts: bool  # 用于后台agent

class PermissionResult:
    behavior: Literal["allow", "deny", "ask"]
    reason: Optional[str] = None
    updated_input: Optional[Dict] = None  # 允许修改输入参数
```

#### 7.1.3 增加工具接口特性

**建议**：支持别名、搜索提示、进度回调

```python
# 建议实现
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    aliases: List[str] = field(default_factory=list)  # 向后兼容
    search_hint: Optional[str] = None  # 关键词搜索提示

    async def call(
        self,
        args: Dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None
    ) -> ToolResult:
        ...
```

#### 7.1.4 改进状态管理

**建议**：引入不可变状态和函数式更新

```python
# 建议实现
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar('T')

@dataclass(frozen=True)
class AgentState:
    messages: Tuple[Message, ...]  # 不可变元组
    tool_permission_context: ToolPermissionContext
    file_state_cache: FileStateCache

class AgentStateManager:
    def __init__(self, initial_state: AgentState):
        self._state = initial_state

    @property
    def state(self) -> AgentState:
        return self._state

    def update_state(
        self,
        updater: Callable[[AgentState], AgentState]
    ) -> None:
        """函数式状态更新"""
        self._state = updater(self._state)
```

#### 7.1.5 支持异步生成器

**建议**：使用异步生成器支持流式响应

```python
# 建议实现
from typing import AsyncGenerator
import asyncio

class QueryEngine:
    async def submit_message(
        self,
        prompt: str,
        options: Optional[Dict] = None
    ) -> AsyncGenerator[AgentMessage, None]:
        """异步生成器，支持流式响应"""
        # 初始化
        yield AgentMessage(type="status", content="Processing...")

        # 调用模型
        async for chunk in self._call_model_stream(prompt):
            yield AgentMessage(type="content", content=chunk)

        # 工具执行
        for tool_call in tool_calls:
            yield AgentMessage(type="tool_start", content=tool_call)
            result = await self._execute_tool(tool_call)
            yield AgentMessage(type="tool_result", content=result)
```

### 7.2 claude-code可借鉴Jarvis的优化点

#### 7.2.1 增强MCP协议支持

**建议**：支持多种传输方式

```typescript
// 建议实现
type MCPTransport = "stdio" | "sse" | "streamable";

interface MCPServerConfig {
  transport: MCPTransport;
  url?: string; // for SSE/Streamable
  command?: string; // for Stdio
  args?: string[];
}

class MCPClientFactory {
  static create(config: MCPServerConfig): MCPClient {
    switch (config.transport) {
      case "stdio":
        return new StdioMCPClient(config);
      case "sse":
        return new SSEMCPClient(config);
      case "streamable":
        return new StreamableMCPClient(config);
    }
  }
}
```

#### 7.2.2 增加自动修复机制

**建议**：实现连续无工具调用的自动修复

```typescript
// 建议实现
class QueryEngine {
  private noToolCallCount = 0;
  private readonly MAX_NO_TOOL_CALLS = 3;

  private async handleNoToolCall(): Promise<void> {
    this.noToolCallCount++;

    if (this.noToolCallCount >= this.MAX_NO_TOOL_CALLS) {
      // 使用LLM修复
      const fixPrompt = this.buildFixPrompt();
      const fixedResponse = await this.callLLM(fixPrompt);
      this.noToolCallCount = 0;
      return fixedResponse;
    }
  }
}
```

#### 7.2.3 增加Git仓库自动检测

**建议**：自动切换到代码开发模式

```typescript
// 建议实现
class GitIntegration {
  static async detectAndSwitchMode(cwd: string): Promise<AgentMode> {
    const isGitRepo = await this.isGitRepository(cwd);

    if (isGitRepo) {
      const hasCode = await this.hasSourceCode(cwd);
      if (hasCode) {
        return "code";
      }
    }

    return "general";
  }
}
```

---

## 8. 总结

### 8.1 关键发现

1. **架构差异**：Jarvis采用模块化单体架构，claude-code采用面向对象+函数式混合架构
2. **类型系统**：claude-code的TypeScript+Zod提供更强的类型安全
3. **工具系统**：Jarvis的MCP支持更完善，claude-code的工具接口更丰富
4. **状态管理**：claude-code的函数式状态管理更安全
5. **扩展性**：两者都有良好的扩展机制，但实现方式不同

### 8.2 优化优先级

**高优先级**：

1. Jarvis增强类型安全（引入TypeHint和Protocol）
2. Jarvis完善权限系统（细粒度控制）
3. claude-code增强MCP协议支持

**中优先级**：

1. Jarvis增加工具别名和进度回调
2. Jarvis改进状态管理（不可变状态）
3. claude-code增加自动修复机制

**低优先级**：

1. Jarvis支持异步生成器
2. claude-code增加Git仓库自动检测

### 8.3 下一步行动

1. 基于本报告编写SDD spec文档
2. 选择高优先级优化点进行详细设计
3. 制定实施计划和时间表
