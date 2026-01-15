# 添加 MCP 工具

## 规则简介

本规则指导如何通过配置文件将 MCP (Model Context Protocol) 工具集成到 Jarvis 中。

## 你必须遵守的原则

### 配置文件位置

- **必须**：MCP 工具配置应放置在 `~/.jarvis/config.yaml` 文件中的 `mcp` 列表
- **必须**：每个 MCP 客户端配置都是一个独立的列表项
- **禁止**：直接修改 `~/.jarvis/mcp/` 目录下的 YAML 文件（此方式已废弃）

### 配置结构

每个 MCP 配置项必须包含以下字段：

```yaml
mcp:
  - type: "stdio" | "sse" | "streamable"  # 必须指定类型
    name: "自定义名称"                      # 可选，默认为 "mcp"
    enable: true                             # 可选，默认为 true
    # 其他类型特定参数...
```

## 你必须执行的操作

### 操作 1：选择 MCP 客户端类型

根据你的 MCP 服务器实现方式，选择合适的客户端类型：

#### 1. stdio 类型（标准输入输出）

**适用场景：** 本地运行的命令行程序，通过 stdin/stdout 通信

**必需参数：**

- `type`: 必须为 `"stdio"`
- `command`: 启动 MCP 服务器的完整命令

**可选参数：**

- `name`: MCP 客户端名称（用于工具命名前缀）
- `args`: 命令参数列表（数组格式）
- `env`: 环境变量（对象格式）
- `enable`: 是否启用（默认 true）

**配置示例：**

```yaml
mcp:
  - type: "stdio"
    name: "filesystem"
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/path/to/allowed/directory"
    env:
      NODE_ENV: "production"
```

#### 2. sse 类型（Server-Sent Events）

**适用场景：** 通过 HTTP SSE 协议通信的 MCP 服务器

**必需参数：**

- `type`: 必须为 `"sse"`
- `base_url`: MCP 服务器的 HTTP 基础 URL

**可选参数：**

- `name`: MCP 客户端名称
- `enable`: 是否启用（默认 true）

**配置示例：**

```yaml
mcp:
  - type: "sse"
    name: "remote-mcp"
    base_url: "https://example.com/mcp/sse"
```

#### 3. streamable 类型

**适用场景：** 支持流式通信的 MCP 服务器

**必需参数：**

- `type`: 必须为 `"streamable"`
- `base_url`: MCP 服务器的 HTTP 基础 URL

**可选参数：**

- `name`: MCP 客户端名称
- `enable`: 是否启用（默认 true）

**配置示例：**

```yaml
mcp:
  - type: "streamable"
    name: "streaming-server"
    base_url: "https://example.com/mcp/stream"
```

### 操作 2：配置多个 MCP 客户端

可以在 `mcp` 列表中配置多个 MCP 客户端：

```yaml
mcp:
  - type: "stdio"
    name: "filesystem"
    command: "npx"
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/home/user/documents"

  - type: "sse"
    name: "remote-tools"
    base_url: "https://api.example.com/mcp"

  - type: "stdio"
    name: "database"
    command: "python"
    args:
      - "-m"
      - "mcp_database_server"
    enable: false # 临时禁用
```

### 操作 3：验证配置

**验证步骤：**

1. 保存 `~/.jarvis/config.yaml` 文件
2. 重启 Jarvis
3. 观察启动日志，确认 MCP 工具加载情况

**成功标志：**

- 没有出现 `⚠️ 配置XXX缺少type字段` 警告
- 没有出现 `⚠️ 配置XXX缺少command字段`（stdio）或 `⚠️ 配置XXX缺少base_url字段`（sse/streamable）警告
- 没有出现 `⚠️ MCP配置XXX加载失败` 错误

**工具命名规则：**

- MCP 工具会以 `{name}.tool_call.{tool_name}` 的形式注册
- 资源相关工具会以 `{name}.resource.get_resource_list` 和 `{name}.resource.get_resource` 的形式注册

例如，配置 `name: "filesystem"`，服务器提供工具 `read_file`，则注册的工具名为 `filesystem.tool_call.read_file`

## 常见问题排查

### 问题 1：配置加载失败

**现象：** `⚠️ MCP配置XXX加载失败: 错误信息`

**可能原因：**

- MCP 服务器未安装或不在 PATH 中
- command 路径错误
- 权限不足

**解决方法：**

- 确认 MCP 服务器已正确安装
- 使用绝对路径或确认命令在 PATH 中
- 检查命令是否可在终端中手动执行

### 问题 2：获取工具列表失败

**现象：** `⚠️ 从配置XXX获取工具列表失败`

**可能原因：**

- MCP 服务器未正常启动
- base_url 配置错误（sse/streamable）
- 网络连接问题

**解决方法：**

- 检查 MCP 服务器日志
- 验证 base_url 可访问性
- 测试网络连接

### 问题 3：工具执行无响应

**现象：** 工具注册成功，但执行时无响应或超时

**可能原因：**

- MCP 服务器处理请求时间过长
- 参数传递错误
- 服务器端异常

**解决方法：**

- 检查 MCP 服务器日志
- 验证工具参数格式
- 增加服务器超时配置（如果支持）

### 问题 4：废弃文件方式警告

**现象：** `⚠️ 警告: 从文件目录加载MCP工具的方式将在未来版本中废弃，请尽快迁移到mcp配置方式`

**解决方法：**

- 将 `~/.jarvis/mcp/` 目录下的 YAML 配置迁移到 `~/.jarvis/config.yaml` 的 `mcp` 列表中
- 删除或重命名 `~/.jarvis/mcp/` 目录中的配置文件

## 检查清单

在完成 MCP 工具配置后，你必须确认：

- [ ] 配置已添加到 `~/.jarvis/config.yaml` 的 `mcp` 列表中
- [ ] 每个 MCP 配置都包含 `type` 字段
- [ ] stdio 类型包含 `command` 字段
- [ ] sse/streamable 类型包含 `base_url` 字段
- [ ] YAML 格式正确（缩进、引号等）
- [ ] 已删除或禁用 `~/.jarvis/mcp/` 目录中的旧配置文件
- [ ] 重启 Jarvis 后没有出现配置错误警告
- [ ] MCP 工具已成功注册（可通过工具列表验证）

## 相关资源

- 配置管理：`{{ jarvis_src_dir }}/src/jarvis/jarvis_utils/config.py`
- MCP 注册实现：`{{ jarvis_src_dir }}/src/jarvis/jarvis_tools/registry.py` (register_mcp_tool_by_config 方法)
- MCP 客户端实现：`{{ jarvis_src_dir }}/src/jarvis/jarvis_mcp/`
