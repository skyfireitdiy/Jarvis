---
name: jarvis_tui_advanced_features
description: Jarvis TUI版本高级功能规范，补充Agent管理增强、历史消息、文件编辑等特性
---

# Jarvis TUI 高级功能规范

## 功能概述

在基础TUI版本之上，补充与web版本对齐的高级功能，包括Agent管理增强、历史消息持久化、文件编辑器等。

### 目标

- 提供与web版本一致的Agent管理体验
- 支持历史消息加载和持久化
- 提供基础的文件查看和编辑能力
- 支持多节点管理

## 技术栈

- **TUI框架**: textual
- **WebSocket客户端**: websockets
- **HTTP客户端**: httpx
- **Python版本**: >=3.10

---

## 接口定义

### 1. Agent管理增强接口

```python
class AgentManager:
    async def rename_agent(self, agent_id: str, new_name: str) -> bool:
        """重命名Agent

        Args:
            agent_id: Agent ID
            new_name: 新名称

        Returns:
            bool: 重命名是否成功

        Raises:
            AgentNotFoundError: Agent不存在
        """

    async def batch_delete_agents(self, agent_ids: List[str]) -> Dict[str, bool]:
        """批量删除Agent

        Args:
            agent_ids: Agent ID列表

        Returns:
            Dict[str, bool]: 每个Agent的删除结果
        """
```

### 2. 历史消息接口

```python
class ChatManager:
    async def load_history_messages(self, agent_id: str, limit: int = 50, before: Optional[str] = None) -> List[Message]:
        """加载历史消息

        Args:
            agent_id: Agent ID
            limit: 加载数量限制
            before: 加载此时间之前的消息

        Returns:
            List[Message]: 消息列表
        """

    def get_message_count(self, agent_id: str) -> int:
        """获取Agent消息数量"""

    def export_messages(self, agent_id: str, format: str = "json") -> str:
        """导出消息

        Args:
            agent_id: Agent ID
            format: 导出格式 (json/markdown/text)

        Returns:
            str: 导出内容
        """
```

### 3. 文件管理接口

```python
class FileManager:
    async def list_files(self, agent_id: str, path: str = "/") -> List[FileInfo]:
        """列出目录文件

        Args:
            agent_id: Agent ID
            path: 目录路径

        Returns:
            List[FileInfo]: 文件信息列表
        """

    async def read_file(self, agent_id: str, path: str) -> str:
        """读取文件内容

        Args:
            agent_id: Agent ID
            path: 文件路径

        Returns:
            str: 文件内容

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限
        """

    async def write_file(self, agent_id: str, path: str, content: str) -> bool:
        """写入文件内容

        Args:
            agent_id: Agent ID
            path: 文件路径
            content: 文件内容

        Returns:
            bool: 写入是否成功
        """

    async def search_files(self, agent_id: str, query: str, path: str = "/", glob: str = "*") -> List[SearchResult]:
        """全局搜索

        Args:
            agent_id: Agent ID
            query: 搜索关键词
            path: 搜索路径
            glob: 文件过滤

        Returns:
            List[SearchResult]: 搜索结果列表
        """
```

### 4. 节点管理接口

```python
class NodeManager:
    async def fetch_nodes(self) -> List[NodeInfo]:
        """获取节点列表

        Returns:
            List[NodeInfo]: 节点信息列表
        """

    async def get_node_status(self, node_id: str) -> NodeStatus:
        """获取节点状态

        Args:
            node_id: 节点ID

        Returns:
            NodeStatus: 节点状态
        """

    async def restart_service(self, node_id: str, service: str) -> bool:
        """重启服务

        Args:
            node_id: 节点ID
            service: 服务名称

        Returns:
            bool: 重启是否成功
        """
```

---

## 数据结构

### FileInfo

```python
@dataclass
class FileInfo:
    """文件信息"""
    name: str           # 文件名
    path: str           # 完整路径
    is_directory: bool  # 是否为目录
    size: int = 0       # 文件大小
    modified_at: Optional[datetime] = None  # 修改时间
```

### SearchResult

```python
@dataclass
class SearchResult:
    """搜索结果"""
    file_path: str      # 文件路径
    line_number: int    # 行号
    line_content: str   # 行内容
    match_start: int    # 匹配开始位置
    match_end: int      # 匹配结束位置
```

### NodeInfo

```python
@dataclass
class NodeInfo:
    """节点信息"""
    node_id: str        # 节点ID
    name: str           # 节点名称
    host: str           # 主机地址
    port: int           # 端口
    status: str         # 状态
```

### NodeStatus

```python
@dataclass
class NodeStatus:
    """节点状态"""
    node_id: str        # 节点ID
    cpu_percent: float  # CPU使用率
    memory_percent: float  # 内存使用率
    agent_count: int    # Agent数量
    uptime: int         # 运行时间(秒)
```

---

## 功能行为

### 1. Agent重命名

1. 用户在侧边栏右键点击Agent
2. 选择"重命名"选项
3. 弹出输入框，显示当前名称
4. 用户输入新名称并确认
5. 调用API更新Agent名称
6. 刷新侧边栏显示

### 2. 批量删除Agent

1. 用户在侧边栏勾选多个Agent
2. 点击"批量删除"按钮
3. 弹出确认对话框
4. 用户确认后，逐个调用删除API
5. 显示删除结果统计
6. 刷新侧边栏

### 3. 历史消息加载

1. 用户切换到Agent时自动触发
2. 调用API加载最近50条消息
3. 消息按时间正序显示
4. 支持向上滚动加载更多
5. 消息缓存到本地，避免重复加载

### 4. 文件查看/编辑

1. 用户在终端或聊天中点击文件路径
2. 打开文件查看面板
3. 显示文件内容，支持语法高亮
4. 如果有写权限，可切换为编辑模式
5. 编辑后可保存

### 5. 全局搜索

1. 用户输入搜索关键词
2. 可选择搜索路径和文件过滤
3. 调用API执行搜索
4. 显示搜索结果列表
5. 点击结果可跳转到对应文件

---

## 输入输出说明

### 输入参数约束

| 参数     | 类型 | 约束               | 示例               |
| -------- | ---- | ------------------ | ------------------ |
| agent_id | str  | UUID格式           | agent-abc123       |
| new_name | str  | 1-64字符           | MyAgent            |
| path     | str  | 有效路径           | /home/user/project |
| query    | str  | 1-256字符          | function           |
| limit    | int  | 1-500              | 50                 |
| format   | str  | json/markdown/text | json               |

### 输出说明

- FileInfo: name, path, is_directory, size, modified_at
- SearchResult: file_path, line_number, line_content, match_start, match_end
- NodeInfo: node_id, name, host, port, status
- NodeStatus: node_id, cpu_percent, memory_percent, agent_count, uptime

---

## 边界条件

### Agent重命名

- 名称重复: 提示用户名称已存在
- 名称为空: 提示用户输入有效名称
- 网络错误: 显示错误信息，允许重试

### 批量删除

- 删除数量限制: 最多50个
- 部分失败: 显示成功/失败统计
- 当前Agent被删除: 自动切换到其他Agent

### 历史消息

- 消息数量限制: 单次最多加载500条
- 网络超时: 显示加载失败，允许重试
- Agent不存在: 清空消息列表

### 文件操作

- 文件过大: 超过1MB提示用户
- 编码问题: 自动检测编码
- 权限不足: 显示只读模式

---

## 异常处理

- AgentNotFoundError: Agent不存在，提示用户
- FileNotFoundError: 文件不存在，显示错误
- PermissionError: 权限不足，切换只读模式
- NetworkError: 网络错误，自动重试
- ValidationError: 参数验证失败，提示用户

---

## 验收标准

### AC1: Agent重命名

- [ ] 能够通过右键菜单触发重命名
- [ ] 能够输入新名称并确认
- [ ] 重命名后侧边栏正确更新
- [ ] 重命名失败时显示错误信息

### AC2: 批量删除

- [ ] 能够勾选多个Agent
- [ ] 能够执行批量删除
- [ ] 删除后显示结果统计
- [ ] 删除当前Agent时自动切换

### AC3: 历史消息

- [ ] 切换Agent时自动加载历史消息
- [ ] 消息按时间正序显示
- [ ] 支持向上滚动加载更多
- [ ] 加载失败时显示错误信息

### AC4: 文件查看

- [ ] 能够打开文件查看面板
- [ ] 能够显示文件内容
- [ ] 支持语法高亮
- [ ] 文件过大时显示提示

### AC5: 全局搜索

- [ ] 能够输入搜索关键词
- [ ] 能够设置搜索路径和过滤
- [ ] 能够显示搜索结果
- [ ] 能够跳转到搜索结果

### AC6: 节点管理

- [ ] 能够查看节点列表
- [ ] 能够查看节点状态
- [ ] 能够切换Agent到不同节点

---

## 快捷键

| 快捷键            | 功能              |
| ----------------- | ----------------- |
| Ctrl+F            | 全局搜索          |
| Ctrl+E            | 打开/关闭编辑器   |
| Ctrl+S            | 保存当前文件      |
| Ctrl+W            | 关闭当前标签      |
| F2                | 重命名当前Agent   |
| Delete            | 删除当前Agent     |
| Ctrl+Shift+Delete | 批量删除选中Agent |

---

## 实现优先级

### P0 (必须实现)

1. Agent重命名
2. 历史消息加载

### P1 (重要功能)

3. 批量删除Agent
4. 文件查看

### P2 (增强功能)

5. 全局搜索
6. 文件编辑
7. 节点管理
