# CodeAgent 会话管理功能规范

## 功能概述

### 目标

实现 CodeAgent 的完整会话保存和恢复功能，确保在会话中断后能够恢复所有必要的执行上下文，使 CodeAgent 能够继续之前的任务而无需重新初始化。

### 架构设计

采用**统一的会话管理架构**，所有需要会话恢复功能的类都继承自 `SessionRestorable` 基类，实现统一的保存和恢复接口。

#### 核心设计原则

1. **单一职责**：`SessionRestorable` 基类负责会话文件管理、版本控制、序列化/反序列化等通用逻辑
2. **开闭原则**：子类只需实现自己特有的状态保存和恢复逻辑
3. **里氏替换**：所有继承 `SessionRestorable` 的类都可以通过统一接口进行会话管理
4. **依赖倒置**：高层模块依赖 `SessionRestorable` 抽象接口，而不是具体实现

#### 类设计

```
SessionRestorable (抽象基类)
├── 通用功能：
│   ├── save_session() - 统一的保存入口
│   ├── restore_session() - 统一的恢复入口
│   ├── _get_session_state() - 抽象方法，子类实现状态收集
│   ├── _set_session_state() - 抽象方法，子类实现状态恢复
│   ├── _validate_session_state() - 验证状态完整性
│   └── _get_session_file_path() - 生成会话文件路径
├── 通用实现：
│   ├── 会话文件版本管理
│   ├── JSON 序列化/反序列化
│   ├── 文件读写和错误处理
│   └── 会话文件列表管理
└── 子类实现：
    ├── CodeAgent - 实现代码代理特有的状态保存和恢复
    ├── [未来可扩展]
        ├── ChatAgent - 实现聊天代理的状态保存和恢复
        ├── TaskAgent - 实现任务代理的状态保存和恢复
        └── ...
```

#### 接口定义

```python
class SessionRestorable(ABC):
    """会话可恢复抽象基类
    
    所有需要会话保存和恢复功能的类都应继承此类。
    """
    
    @abstractmethod
    def _get_session_state(self) -> Dict[str, Any]:
        """收集当前状态，返回可序列化的字典
        
        子类必须实现此方法，返回需要保存的所有状态。
        
        返回:
            Dict[str, Any]: 状态字典，所有值必须是 JSON 可序列化的
        """
        pass
    
    @abstractmethod
    def _set_session_state(self, state: Dict[str, Any]) -> None:
        """从状态字典恢复当前状态
        
        子类必须实现此方法，根据传入的状态字典恢复内部状态。
        
        参数:
            state: 状态字典，由 _get_session_state() 生成
        """
        pass
    
    def save_session(self) -> bool:
        """保存会话到文件
        
        基类提供统一实现，调用 _get_session_state() 获取状态，
        然后序列化并写入文件。
        
        返回:
            bool: 保存成功返回 True，失败返回 False
        """
        pass
    
    def restore_session(self) -> bool:
        """从文件恢复会话
        
        基类提供统一实现，读取文件、反序列化、验证，
        然后调用 _set_session_state() 恢复状态。
        
        返回:
            bool: 恢复成功返回 True，失败返回 False
        """
        pass
    
    @abstractmethod
    def _get_session_file_prefix(self) -> str:
        """获取会话文件名前缀
        
        子类必须实现此方法，返回唯一的文件名前缀。
        
        返回:
            str: 文件名前缀（如 "code_agent"）
        """
        pass
```

#### CodeAgent 实现

```python
class CodeAgent(Agent, SessionRestorable):
    """代码代理，支持会话保存和恢复"""
    
    def _get_session_state(self) -> Dict[str, Any]:
        """收集 CodeAgent 特有的状态"""
        return {
            "agent_type": "code_agent",
            "root_dir": self.root_dir,
            "tool_group": self.tool_group,
            "model_group": self.model_group,
            "model_name": self.model.name(),
            "disable_review": self.disable_review,
            "review_max_iterations": self.review_max_iterations,
            "start_commit": self.start_commit,
            "messages": self.messages,
            "non_interactive": self.non_interactive,
        }
    
    def _set_session_state(self, state: Dict[str, Any]) -> None:
        """恢复 CodeAgent 特有的状态"""
        self.root_dir = state["root_dir"]
        self.tool_group = state["tool_group"]
        self.model_group = state["model_group"]
        self.model.set_model_name(state["model_name"])
        self.disable_review = state["disable_review"]
        self.review_max_iterations = state["review_max_iterations"]
        self.start_commit = state["start_commit"]
        self.messages = state["messages"]
        self.non_interactive = state["non_interactive"]
        
        # 重建所有 Manager 实例
        self._rebuild_managers()
    
    def _get_session_file_prefix(self) -> str:
        """返回文件名前缀"""
        return "code_agent"
```

### 使用场景

1. **长时间任务中断恢复**：当长时间运行的代码生成任务因系统崩溃、网络问题等原因中断时，可以恢复到中断前的状态继续执行
2. **会话持久化**：将重要的对话历史和任务状态保存到文件，便于后续查看和恢复
3. **调试和审计**：保存完整的会话状态用于问题排查和审计追溯
4. **多环境切换**：在不同环境之间迁移会话状态

### 当前问题

当前 CodeAgent 的会话管理仅通过继承自 BasePlatform 的 `save_session()` 和 `restore_session()` 方法实现，仅保存了对话历史（messages）和模型名称（model_name），缺少大量关键状态信息，导致恢复后的 CodeAgent 无法正常工作。

## 接口定义

### SessionRestorable 基类接口

#### 抽象方法（子类必须实现）

```python
def _get_session_state(self) -> Dict[str, Any]:
    """收集当前状态，返回可序列化的字典
    
    返回:
        Dict[str, Any]: 状态字典，所有值必须是 JSON 可序列化的
    """

def _set_session_state(self, state: Dict[str, Any]) -> None:
    """从状态字典恢复当前状态
    
    参数:
        state: 状态字典，由 _get_session_state() 生成
    """

def _get_session_file_prefix(self) -> str:
    """获取会话文件名前缀
    
    返回:
        str: 文件名前缀（如 "code_agent"）
    """
```

#### 公共方法（基类提供统一实现）

```python
def save_session(self) -> bool:
    """保存会话到文件（基类统一实现）
    
    返回:
        bool: 保存成功返回 True，失败返回 False
    """

def restore_session(self) -> bool:
    """从文件恢复会话（基类统一实现）
    
    返回:
        bool: 恢复成功返回 True，失败返回 False
    """
```

### CodeAgent 实现

CodeAgent 继承自 `SessionRestorable`，实现以下抽象方法：

```python
class CodeAgent(Agent, SessionRestorable):
    def _get_session_state(self) -> Dict[str, Any]:
        """收集 CodeAgent 的所有状态"""
        
    def _set_session_state(self, state: Dict[str, Any]) -> None:
        """恢复 CodeAgent 的所有状态"""
        
    def _get_session_file_prefix(self) -> str:
        """返回 'code_agent' 作为文件名前缀"""
        
    def _rebuild_managers(self) -> None:
        """重建所有 Manager 实例（恢复时调用）"""
```

### 文件格式

会话文件使用 JSON 格式，由 `SessionRestorable` 基类统一管理。文件结构分为两部分：

#### 元数据（基类管理）

```json
{
  "version": "1.0",
  "saved_at": "2025-01-19T12:34:56",
  "file_prefix": "code_agent"
}
```

#### 状态数据（子类提供）

```json
{
  "state": {
    "agent_type": "code_agent",
    "root_dir": "/path/to/project",
    "tool_group": "default",
    "model_group": "smart",
    "model_name": "gpt-4o",
    "disable_review": false,
    "review_max_iterations": 3,
    "start_commit": "abc123def456",
    "messages": [...],
    "non_interactive": false
  }
}
```

#### 完整示例

```json
{
  "version": "1.0",
  "saved_at": "2025-01-19T12:34:56",
  "file_prefix": "code_agent",
  "state": {
    "agent_type": "code_agent",
    "root_dir": "/path/to/project",
    "tool_group": "default",
    "model_group": "smart",
    "model_name": "gpt-4o",
    "disable_review": false,
    "review_max_iterations": 3,
    "start_commit": "abc123def456",
    "messages": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ],
    "non_interactive": false
  }
}
```

### 字段说明

| 字段名 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| version | string | 是 | 会话文件版本号，用于向后兼容 |
| saved_at | string | 是 | 保存时间（ISO 8601 格式） |
| agent_type | string | 是 | Agent 类型标识（固定为 "code_agent"） |
| root_dir | string | 是 | 工作目录绝对路径 |
| tool_group | string | 是 | 工具组名称 |
| model_group | string | 是 | 模型组名称 |
| model_name | string | 是 | 模型名称 |
| disable_review | boolean | 是 | 是否禁用代码审查 |
| review_max_iterations | int | 是 | 代码审查最大迭代次数 |
| start_commit | string or null | 是 | 起始 Git commit hash（可为空） |
| messages | array | 是 | 对话消息历史（兼容 OpenAI 格式） |
| non_interactive | boolean | 是 | 是否为非交互模式 |

## 输入输出说明

### save_session()

**输入**：无参数

**输出**：
- 返回 `True`：会话成功保存到文件
- 返回 `False`：保存失败（文件写入失败、序列化错误等）

**副作用**：
- 在当前工作目录的 `.jarvis/` 子目录下创建会话文件
- 文件命名格式：`saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json`

### restore_session()

**输入**：无参数

**输出**：
- 返回 `True`：会话成功恢复
- 返回 `False`：恢复失败（文件不存在、格式错误、版本不兼容等）

**副作用**：
- 修改 CodeAgent 的内部状态（messages、model_name、start_commit 等）
- 重新初始化所有 Manager 实例（context_manager、git_manager 等）

## 功能行为

### SessionRestorable 基类行为

#### 保存会话（统一实现）

1. 调用子类的 `_get_session_state()` 获取状态数据
2. 添加元数据（version、saved_at、file_prefix）
3. 将状态序列化为 JSON 格式
4. 写入到 `.jarvis/` 目录下的文件中
5. 文件命名格式：`saved_session_{file_prefix}_{platform}_{model}_{timestamp}.json`
6. 设置 `self._saved = True` 标记
7. 输出成功消息和文件路径

#### 恢复会话（统一实现）

1. 如果有多个会话文件，显示列表让用户选择（交互模式）或自动选择最新的（非交互模式）
2. 读取并解析会话文件
3. 验证版本兼容性和数据完整性
4. 调用子类的 `_set_session_state()` 恢复状态
5. 输出成功消息

### CodeAgent 特定行为

#### 保存会话

1. 收集所有核心状态（root_dir、tool_group、model_name、start_commit 等）
2. 包含对话消息历史（messages）
3. 通过基类的统一接口保存

#### 恢复会话

1. 恢复所有核心状态
2. 重新初始化所有 Manager 实例：
   - `context_manager`：通过 root_dir 重建
   - `git_manager`：通过 root_dir 重建
   - `diff_manager`：通过 root_dir 重建
   - `impact_manager`：通过 root_dir 和 context_manager 重建
   - `build_validation_manager`：通过 root_dir 重建
   - `lint_manager`：通过 root_dir 重建
   - `post_process_manager`：通过 root_dir 重建
3. 重建 `context_recommender`（需要 model 实例）
4. 重新订阅事件总线
5. 验证恢复的完整性（检查 root_dir 是否存在）

### 边界条件

1. **空会话**：messages 为空列表时也能正常保存和恢复
2. **无 start_commit**：start_commit 为 None 时保存为 null，恢复时保持 None
3. **工作目录不存在**：如果 root_dir 不存在，恢复失败并提示用户
4. **版本升级**：支持从旧版本会话文件恢复（向后兼容）

### 异常情况

#### 保存时的异常

1. **权限错误**：如果 `.jarvis/` 目录或文件没有写权限，返回 False 并输出错误信息
2. **磁盘空间不足**：如果磁盘空间不足，返回 False 并输出错误信息
3. **序列化错误**：如果某个状态无法序列化（如包含不可序列化的对象），返回 False 并输出错误信息

#### 恢复时的异常

1. **文件不存在**：如果没有找到会话文件，返回 False 并提示用户
2. **文件损坏**：如果 JSON 解析失败，返回 False 并提示文件损坏
3. **版本不兼容**：如果会话文件版本高于当前支持的版本，返回 False 并提示升级
4. **字段缺失**：如果必需字段缺失，返回 False 并提示文件格式错误
5. **Git 状态变化**：如果 start_commit 对应的提交已被删除，给出警告但继续恢复

## 状态保存策略

### 核心状态（直接保存）

以下状态直接保存到会话文件：

- `root_dir`：工作目录路径
- `tool_group`：工具组名称
- `model_group`：模型组名称
- `model_name`：模型名称
- `disable_review`：是否禁用代码审查
- `review_max_iterations`：代码审查最大迭代次数
- `start_commit`：起始 Git commit hash
- `messages`：对话消息历史（调用父类的 save 方法）
- `non_interactive`：是否为非交互模式

### 可重建状态（恢复时重建）

以下状态不直接保存，而是在恢复时根据保存的信息重新初始化：

- `context_manager`：通过 root_dir 重建
- `git_manager`：通过 root_dir 重建，并检查 git 配置
- `diff_manager`：通过 root_dir 重建
- `impact_manager`：通过 root_dir 和重建的 context_manager 重建
- `build_validation_manager`：通过 root_dir 重建
- `lint_manager`：通过 root_dir 重建
- `post_process_manager`：通过 root_dir 重建
- `context_recommender`：通过重建的 context_manager 和 model 重建

### 运行时状态（不保存）

以下状态不需要保存：

- 临时变量和局部状态
- 事件总线的订阅状态（恢复时重新订阅）
- 缓存数据（恢复时重新生成）
- 模型实例的状态（恢复时使用当前模型实例）

## 验收标准

### 功能验收

1. **完整保存**：能保存 CodeAgent 的所有核心状态到文件
2. **完整恢复**：能从保存的文件恢复 CodeAgent 的所有核心状态
3. **继续工作**：恢复后的 CodeAgent 能够继续之前的任务，不影响功能
4. **多会话管理**：能正确处理多个会话文件，支持用户选择或自动选择
5. **版本兼容**：支持从旧版本的会话文件恢复（向后兼容至少一个主版本）

### 边界情况验收

1. **空会话**：空 messages 列表时能正常保存和恢复
2. **无 start_commit**：start_commit 为 None 时能正常保存和恢复
3. **目录不存在**：root_dir 不存在时能正确处理，给出明确错误提示

### 异常处理验收

1. **文件权限**：权限错误时能正确返回 False 并输出错误信息
2. **文件损坏**：损坏的会话文件不会导致程序崩溃，给出明确错误提示
3. **版本不兼容**：高版本会话文件能被正确识别并提示升级

### 兼容性验收

1. **向后兼容**：能读取并恢复 v1.0 格式的会话文件
2. **跨平台**：会话文件在不同操作系统间可以正常迁移（使用相对路径或绝对路径统一处理）

### 性能验收

1. **保存性能**：保存会话时间不超过 2 秒（包含 1000 条消息的典型场景）
2. **恢复性能**：恢复会话时间不超过 3 秒（包含 1000 条消息的典型场景）

## 实现注意事项

### 安全性

1. **敏感信息**：不保存任何敏感信息（如 API keys、密码等）
2. **路径验证**：恢复时验证 root_dir 的合法性，防止路径遍历攻击
3. **文件权限**：会话文件应设置为仅当前用户可读写（600 权限）

### 用户体验

1. **友好提示**：所有成功和失败操作都应给出清晰的中文提示
2. **进度显示**：对于大型会话（如超过 500 条消息），显示保存/恢复进度
3. **文件信息**：恢复时显示会话文件的详细信息（时间、大小、消息数量等）

### 可维护性

1. **版本管理**：会话文件格式应包含版本号，便于后续升级
2. **扩展性**：设计时应考虑未来可能需要保存的新状态字段
3. **日志记录**：关键操作应记录日志，便于问题排查

## 测试场景

### 单元测试

1. 测试保存和恢复所有核心状态字段
2. 测试空会话、无 start_commit 等边界情况
3. 测试文件不存在、文件损坏等异常情况

### 集成测试

1. 保存完整会话，恢复后继续执行任务，验证功能正常
2. 在不同目录间迁移会话文件，验证路径正确处理
3. 使用不同版本的会话文件，验证兼容性

### 压力测试

1. 测试包含 1000+ 条消息的大型会话保存和恢复性能
2. 测试并发保存和恢复多个会话文件

## 文档更新

### 需要更新的文档

1. 用户手册：添加会话保存和恢复的使用说明
2. API 文档：添加 `save_session()` 和 `restore_session()` 方法的 API 文档
3. 开发者文档：说明会话文件格式和版本管理策略

## 发布检查清单

- [ ] 所有验收标准都已满足
- [ ] 代码实现与 Spec 一致
- [ ] 已编写测试并全部通过
- [ ] 文档已更新
- [ ] 代码已通过审查
- [ ] 已添加版本兼容性测试
- [ ] 性能测试符合要求