---
name: jarvis_tui
description: Jarvis TUI版本功能规范，基于textual框架实现终端用户界面
---

# Jarvis TUI 功能规范

## 功能概述

基于web版本App.vue的功能，使用Python textual框架实现终端用户界面(TUI)版本。TUI版本提供与web版本相同的核心功能，包括认证连接、Agent管理、聊天交互、终端面板等。

### 目标用户

- 偏好终端操作的开发者
- 无GUI环境的服务器用户

### 核心价值

- 提供与web版本一致的功能体验
- 支持流式消息输出
- 支持多Agent管理
- 集成终端面板

## 技术栈

- **TUI框架**: textual
- **WebSocket客户端**: websockets
- **HTTP客户端**: httpx
- **Python版本**: >=3.10

## 接口定义

### 1. 认证接口

```python
class AuthManager:
    async def login(self, gateway_url: str, password: str) -> str:
        """使用密码登录获取Token

        Returns:
            str: 认证Token
        """
    def has_token(self) -> bool:
        """检查是否有有效Token"""
    def get_token(self) -> Optional[str]:
        """获取当前Token"""
    def clear_token(self) -> None:
        """清除Token"""
```

### 2. 连接接口

```python
class ConnectionManager:
    async def connect_gateway(self, host: str, port: int, token: str) -> bool:
        """连接到Gateway WebSocket"""
    async def disconnect_gateway(self) -> None:
        """断开Gateway连接"""
    async def connect_agent(self, agent_id: str, host: str, port: int, token: str, node_id: str = "master") -> bool:
        """连接到Agent（带重试逻辑）"""
    async def disconnect_agent(self, agent_id: str) -> None:
        """断开Agent连接"""
    async def disconnect_all(self) -> None:
        """断开所有连接"""
```

### 3. Agent管理接口

```python
class AgentManager:
    def get_agents(self) -> List[AgentInfo]:
        """获取所有Agent列表"""
    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """获取指定Agent"""
    def get_current_agent(self) -> Optional[AgentInfo]:
        """获取当前选中的Agent"""
    def set_current_agent(self, agent_id: str) -> None:
        """设置当前Agent"""
    def add_agent(self, agent: AgentInfo) -> None:
        """添加Agent"""
    def remove_agent(self, agent_id: str) -> None:
        """移除Agent"""
    def process_agent_list(self, agents_data: List[Dict[str, Any]]) -> None:
        """处理从Gateway收到的Agent列表"""
    async def rename_agent(self, agent_id: str, new_name: str) -> bool:
        """重命名Agent

        Args:
            agent_id: Agent ID
            new_name: 新名称（1-64字符）

        Returns:
            bool: 重命名是否成功

        Raises:
            AgentNotFoundError: Agent不存在
            ValueError: 名称无效
        """
    def get_agent_by_name(self, name: str) -> Optional[AgentInfo]:
        """根据名称获取Agent"""
```

### 4. 消息接口

```python
class ChatManager:
    async def send_message(self, message: str, agent_id: Optional[str] = None) -> None:
        """发送消息到Agent"""
    async def load_history_messages(self, agent_id: str, limit: int = 50, before: Optional[str] = None) -> List[Message]:
        """加载历史消息

        Args:
            agent_id: Agent ID
            limit: 加载数量限制（1-500）
            before: 加载此时间之前的消息（ISO格式）

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

## 输入输出说明

### 输入参数约束

| 参数        | 类型 | 约束               | 示例               |
| ----------- | ---- | ------------------ | ------------------ |
| gateway_url | str  | host:port或完整URL | 127.0.0.1:8000     |
| password    | str  | 1-128字符          | -                  |
| agent_id    | str  | UUID格式           | -                  |
| work_dir    | str  | 有效目录路径       | /home/user/project |
| message     | str  | 1-100000字符       | -                  |

### 输出说明

- AgentInfo: agent_id, name, work_dir, status, created_at
- Message: role, content, timestamp, agent_id, message_type

## 功能行为

### 1. 启动流程

1. 显示登录界面
2. 用户输入网关地址和密码
3. 验证连接并获取Token
4. 连接Gateway WebSocket
5. 加载Agent列表
6. 显示主界面

### 2. 聊天交互

- 发送消息: 用户输入后按Enter发送
- 流式输出: STREAM_START -> STREAM_CHUNK -> STREAM_END
- 消息渲染: 用户消息右对齐，Agent消息Markdown渲染

### 3. Agent管理

- 查看列表: 侧边栏显示所有Agent
- 创建Agent: 输入工作目录和名称
- 删除Agent: 确认后删除
- 切换Agent: 点击切换，加载历史消息

### 4. 终端面板

- 打开/关闭: Ctrl+T快捷键
- 执行命令: 输入后Enter执行
- 实时输出: 支持ANSI颜色

### 5. 快捷键

| 快捷键 | 功能          |
| ------ | ------------- |
| Ctrl+N | 新建Agent     |
| Ctrl+D | 删除当前Agent |
| Ctrl+T | 打开/关闭终端 |
| Ctrl+Q | 退出程序      |

## 边界条件

### 网络异常

#### Gateway连接

- 连接断开: 自动重连
- 超时: 显示提示，允许手动重连
- 认证失败: 清除Token，提示重新登录

#### Agent连接重试（与web版本对齐）

- **最大重试次数**: 12次
- **重试间隔**: 2秒
- **连接超时**: 10秒
- **重试触发条件**:
  1. 连接超时（10秒内未建立连接）
  2. 连接未完成就关闭
  3. 连接发生错误
- **连接清理逻辑**:
  1. 重试前必须等待旧连接完全关闭
  2. 使用轮询检查连接状态（每50ms检查一次）
  3. 最多等待1秒让旧连接关闭
  4. 清理完成后才发起新连接

### 消息限制

- 消息过长: 超过100000字符提示截断
- 发送频率: 每秒最多1条

### Agent限制

- 数量限制: 最多50个
- 工作目录: 必须有效且有权限

## 异常处理

- ConnectionError: 连接错误，自动重试
- AuthenticationError: 认证失败，重新登录
- AgentNotFoundError: Agent不存在，提示用户
- MessageTooLongError: 消息过长，提示截断

## 验收标准

### AC1: 认证连接

- [ ] 能够输入网关地址和密码
- [ ] 能够成功登录获取Token
- [ ] 能够连接Gateway WebSocket
- [ ] 连接失败时显示错误信息

### AC2: Agent管理

- [ ] 能够查看Agent列表
- [ ] 能够创建新Agent
- [ ] 能够删除Agent
- [ ] 能够切换Agent

### AC3: 聊天功能

- [ ] 能够发送文本消息
- [ ] 能够接收流式消息
- [ ] 消息实时显示
- [ ] Markdown正确渲染

### AC4: 终端面板

- [ ] 能够打开/关闭终端
- [ ] 能够执行命令
- [ ] 命令输出实时显示

### AC5: 用户体验

- [ ] 界面响应流畅
- [ ] 快捷键正常工作
- [ ] 错误提示友好
