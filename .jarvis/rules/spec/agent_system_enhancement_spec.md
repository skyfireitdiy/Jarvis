---
name: agent_system_enhancement
description: 增强Jarvis Agent系统的类型安全、权限控制和工具接口，参考claude-code的优秀实践
---

# Agent系统增强规范

## 功能概述

本规范定义了对Jarvis Agent系统的增强功能，旨在提升系统的类型安全性、完善权限控制机制、增强工具接口特性。这些改进参考了claude-code项目的优秀实践，同时保持与现有Jarvis架构的兼容性。

### 目标

1. **增强类型安全**：引入Protocol和泛型类型定义，提升代码的类型检查能力
2. **完善权限系统**：实现细粒度的权限控制，支持多种权限模式
3. **增加工具接口特性**：支持别名、搜索提示、进度回调等高级特性
4. **改进状态管理**：引入不可变状态和函数式更新模式
5. **支持异步生成器**：使用AsyncGenerator支持流式响应

### 适用场景

- 新工具开发时需要遵循统一的接口规范
- 需要细粒度权限控制的生产环境
- 需要实时进度反馈的长时间运行任务
- 需要流式响应的交互式场景

## 接口定义

### 1. 增强的工具接口

#### 1.1 Tool Protocol定义

```python
from typing import Protocol, TypeVar, Generic, Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

Input = TypeVar('Input')
Output = TypeVar('Output')

@dataclass
class ToolProgress:
    """工具执行进度信息"""
    percentage: Optional[float] = None  # 0-100
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

@dataclass
class ToolResult(Generic[Output]):
    """工具执行结果"""
    data: Output
    new_messages: Optional[List[Any]] = None
    error: Optional[str] = None
    is_error: bool = False

class Tool(Protocol[Input, Output]):
    """工具协议定义"""
    
    @property
    def name(self) -> str: ...
    
    @property
    def aliases(self) -> List[str]: ...
    
    @property
    def description(self) -> str: ...
    
    @property
    def input_schema(self) -> type[Input]: ...
    
    @property
    def search_hint(self) -> Optional[str]: ...
    
    async def call(
        self,
        args: Input,
        context: Any,
        on_progress: Optional[Callable[[ToolProgress], None]] = None
    ) -> ToolResult[Output]: ...
```

#### 1.2 ToolDefinition数据类

```python
@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    aliases: List[str] = field(default_factory=list)
    search_hint: Optional[str] = None
    category: Optional[str] = None
    version: str = "1.0.0"
    requires_permissions: bool = False
```

### 2. 权限系统接口

#### 2.1 权限模式枚举

```python
from enum import Enum
from typing import Literal, Set

class PermissionMode(Enum):
    """权限模式"""
    DEFAULT = "default"      # 默认模式，需要用户确认
    BYPASS = "bypass"        # 绕过权限检查（仅限管理员）
    AUTO = "auto"            # 自动模式，根据规则自动决定
    READONLY = "readonly"    # 只读模式
```

#### 2.2 权限上下文

```python
@dataclass
class ToolPermissionContext:
    """工具权限上下文"""
    mode: PermissionMode
    always_allow_rules: Dict[str, Set[str]] = field(default_factory=dict)
    always_deny_rules: Dict[str, Set[str]] = field(default_factory=dict)
    always_ask_rules: Dict[str, Set[str]] = field(default_factory=dict)
    is_bypass_permissions_mode_available: bool = False
    should_avoid_permission_prompts: bool = False
    user_id: Optional[str] = None
    session_id: Optional[str] = None
```

#### 2.3 权限结果

```python
@dataclass
class PermissionResult:
    """权限检查结果"""
    behavior: Literal["allow", "deny", "ask"]
    reason: Optional[str] = None
    updated_input: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False
    confirmation_message: Optional[str] = None
```

### 3. 状态管理接口

#### 3.1 Agent状态

```python
from typing import Tuple

@dataclass(frozen=True)
class AgentState:
    """Agent不可变状态"""
    messages: Tuple[Any, ...]
    tool_permission_context: ToolPermissionContext
    file_state_cache: Dict[str, Any]
    current_tool: Optional[str] = None
    execution_count: int = 0
    
    def with_messages(self, messages: Tuple[Any, ...]) -> 'AgentState':
        """创建带有新消息的状态副本"""
        return AgentState(
            messages=messages,
            tool_permission_context=self.tool_permission_context,
            file_state_cache=self.file_state_cache,
            current_tool=self.current_tool,
            execution_count=self.execution_count
        )
```

#### 3.2 状态管理器

```python
class AgentStateManager:
    """Agent状态管理器"""
    
    def __init__(self, initial_state: AgentState):
        self._state = initial_state
        self._history: List[AgentState] = [initial_state]
    
    @property
    def state(self) -> AgentState:
        return self._state
    
    def update_state(
        self,
        updater: Callable[[AgentState], AgentState]
    ) -> None:
        """函数式状态更新"""
        new_state = updater(self._state)
        self._history.append(new_state)
        self._state = new_state
    
    def rollback(self, steps: int = 1) -> bool:
        """回滚到之前的状态"""
        if len(self._history) > steps:
            self._history = self._history[:-steps]
            self._state = self._history[-1]
            return True
        return False
```

### 4. 异步生成器接口

#### 4.1 查询引擎接口

```python
from typing import AsyncGenerator, Literal

@dataclass
class AgentMessage:
    """Agent消息"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class QueryEngine(Protocol):
    """查询引擎协议"""
    
    async def submit_message(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AgentMessage, None]:
        """异步生成器，支持流式响应"""
        ...
    
    async def submit_tool_result(
        self,
        tool_call_id: str,
        result: ToolResult[Any]
    ) -> AsyncGenerator[AgentMessage, None]:
        """提交工具执行结果"""
        ...
```

## 验收标准

### 1. 类型安全

- [ ] 所有工具接口使用Protocol定义
- [ ] 泛型类型正确应用于ToolResult
- [ ] 静态类型检查通过（mypy --strict）
- [ ] 运行时类型验证正确

### 2. 权限系统

- [ ] 支持4种权限模式（DEFAULT, BYPASS, AUTO, READONLY）
- [ ] 权限规则可以动态配置
- [ ] 权限检查结果包含修改输入的能力
- [ ] 后台agent可以避免权限提示

### 3. 工具接口

- [ ] 工具支持别名
- [ ] 工具支持搜索提示
- [ ] 工具支持进度回调
- [ ] 进度回调正确触发

### 4. 状态管理

- [ ] 状态不可变
- [ ] 状态更新使用函数式方式
- [ ] 支持状态历史和回滚
- [ ] 状态更新性能良好

### 5. 异步支持

- [ ] 查询引擎支持AsyncGenerator
- [ ] 流式响应正确工作
- [ ] 异步操作不阻塞主线程
- [ ] 错误处理正确传播

### 6. 向后兼容

- [ ] 现有工具无需修改即可工作
- [ ] 现有API保持兼容
- [ ] 渐进式迁移路径清晰
- [ ] 文档和示例完整

## 实施计划

### 阶段1：类型安全增强（2周）

1. 定义Tool Protocol和泛型类型
2. 更新现有工具实现
3. 添加类型检查到CI/CD

### 阶段2：权限系统完善（3周）

1. 实现PermissionMode和ToolPermissionContext
2. 集成到现有工具系统
3. 添加权限配置UI

### 阶段3：工具接口增强（2周）

1. 添加别名和搜索提示支持
2. 实现进度回调机制
3. 更新工具注册系统

### 阶段4：状态管理改进（2周）

1. 实现不可变状态
2. 添加状态历史和回滚
3. 性能优化

### 阶段5：异步支持（1周）

1. 实现AsyncGenerator接口
2. 更新查询引擎
3. 测试流式响应

## 风险评估

### 技术风险

- **类型系统复杂性**：泛型和Protocol可能增加代码复杂度
  - 缓解措施：提供详细的文档和示例

- **性能影响**：不可变状态可能增加内存使用
  - 缓解措施：使用结构共享优化

- **兼容性问题**：新接口可能与现有代码冲突
  - 缓解措施：提供适配器层

### 进度风险

- **学习曲线**：团队需要时间学习新概念
  - 缓解措施：提供培训和文档

- **迁移成本**：现有工具需要适配
  - 缓解措施：提供自动化迁移工具

## 附录

### A. 参考资料

- claude-code项目：/home/skyfire/code/claude-code/
- 对比分析报告：/home/skyfire/code/Jarvis/docs/technical/implementation/agent_comparison_analysis.md
- Python typing文档：https://docs.python.org/3/library/typing.html
