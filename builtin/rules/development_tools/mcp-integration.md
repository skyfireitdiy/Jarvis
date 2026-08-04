---
name: mcp-integration
description: 当需要集成MCP服务或扩展工具功能时触发。每当用户提及"MCP集成"、"MCP服务"、"工具扩展"、"协议开发"时触发。不触发：仅使用已有工具不涉及MCP；仅配置Agent不涉及MCP；普通工具调用。
---

# MCP集成规则

## 规则简介

此规则指导如何通过配置文件将MCP（Model Context Protocol）工具集成至Jarvis中。

## 汝必循之工作流程

### MCP集成流程（严格执行）

1. **🔧 配置准备阶段**：
   - 确定MCP服务器类型与通信方式
   - 准备MCP服务器运行环境与依赖
   - 规划客户端命名与配置结构

2. **⚙️ 配置实施阶段**：
   - 于`~/.jarvis/config.yaml`文件中添加MCP配置
   - 根据服务器类型选择正确之客户端配置格式
   - 验证YAML语法与配置完整性

3. **🧪 验证测试阶段**：
   - 重启Jarvis加载新配置
   - 检查启动日志确认配置加载成功
   - 验证MCP工具是否正确注册与可用

4. **🔍 故障排除阶段**：
   - 分析配置错误与运行时问题
   - 根据错误信息进行针对性修复
   - 验证修复后之功能完整性

## 汝必守之原则

### 配置管理原则

- **必**：MCP工具配置应置于`~/.jarvis/config.yaml`文件中之`mcp`列表
- **必**：每个MCP客户端配置皆为独立之列表项
- **禁**：直接修改`~/.jarvis/mcp/`目录下之YAML文件（此方式已废弃）
- **必**：配置文件中必指定MCP客户端类型
- **必**：根据客户端类型提供必需之配置参数

### 类型安全原则

- **必**：stdio类型必含`command`字段
- **必**：sse与streamable类型必含`base_url`字段
- **必**：用正确之YAML语法与格式
- **禁**：在配置中用未定义之字段

### 验证确认原则

- **必**：配置完成后重启Jarvis进行验证
- **必**：检查启动日志确认无配置错误
- **必**：验证MCP工具是否正确注册
- **禁**：在未验证之情况下直接用MCP工具

## 具体要求与规范

### 1. 配置文件位置要求（必守）

**位置规范：**

- **必**：MCP工具配置应置于`~/.jarvis/config.yaml`文件中之`mcp`列表
- **必**：每个MCP客户端配置皆为独立之列表项
- **禁**：直接修改`~/.jarvis/mcp/`目录下之YAML文件（此方式已废弃）

### 2. 配置结构要求（必守）

**基本配置格式：**

每个MCP配置项必含以下字段：

```yaml
mcp:
  - type: "stdio" | "sse" | "streamable"  # 必指定类型
    name: "自定义名称"                      # 可选，默认为"mcp"
    enable: true                             # 可选，默认为true
    # 其他类型特定参数...
```

### 3. MCP客户端类型选择要求

根据汝之MCP服务器实现方式，选择合适之客户端类型：

#### 1. stdio类型（标准输入输出）

**适用场景：** 本地运行之命令行程序，通过stdin/stdout通信

**必需参数：**

- `type`: 必为`"stdio"`
- `command`: 启动MCP服务器之完整命令

**可选参数：**

- `name`: MCP客户端名称（用于工具命名前缀）
- `args`: 命令参数列表（数组格式）
- `env`: 环境变量（对象格式）
- `enable`: 是否启用（默认true）

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

#### 2. sse类型（Server-Sent Events）

**适用场景：** 通过HTTP SSE协议通信之MCP服务器

**必需参数：**

- `type`: 必为`"sse"`
- `base_url`: MCP服务器之HTTP基础URL

**可选参数：**

- `name`: MCP客户端名称
- `enable`: 是否启用（默认true）

**配置示例：**

```yaml
mcp:
  - type: "sse"
    name: "remote-mcp"
    base_url: "https://example.com/mcp/sse"
```

#### 3. streamable类型

**适用场景：** 支持流式通信之MCP服务器

**必需参数：**

- `type`: 必为`"streamable"`
- `base_url`: MCP服务器之HTTP基础URL

**可选参数：**

- `name`: MCP客户端名称
- `enable`: 是否启用（默认true）

**配置示例：**

```yaml
mcp:
  - type: "streamable"
    name: "streaming-server"
    base_url: "https://example.com/mcp/stream"
```

### 操作2：配置多个MCP客户端

可于`mcp`列表中配置多个MCP客户端：

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

### 4. 配置验证要求（必守）

**验证步骤：**

1. **必**：保存`~/.jarvis/config.yaml`文件
2. **必**：重启Jarvis以加载新配置
3. **必**：观察启动日志确认MCP工具加载情况

**成功标志：**

- **必**：未出现`⚠️`配置错误警告
- **必**：未出现`⚠️`MCP工具加载失败警告
- **必**：未出现`⚠️`MCP工具注册失败警告

**工具命名规则：**

- **必**：MCP工具会以`{name}.tool_call.{tool_name}`之形式注册
- **必**：资源相关工具会以`{name}.resource.get_resource_list`与`{name}.resource.get_resource`之形式注册

例如，配置`name: "filesystem"`，服务器提供工具`read_file`，则注册之工具名为`filesystem.tool_call.read_file`

## 实践指导

### 配置前之准备工作

- **必**：确认MCP服务器已正确安装并可用
- **必**：了解MCP服务器之通信方式（stdio、sse、streamable）
- **必**：规划合理之客户端命名，避免与现有工具冲突
- **必**：准备MCP服务器运行所需之依赖与环境

### 配置过程中之最佳实践

- **荐**：用有意义之客户端名称，便于识别与管理
- **荐**：为每个MCP客户端添加`enable`字段，便于临时禁用
- **荐**：用绝对路径或确认命令在PATH中，避免路径问题
- **荐**：先配置单个MCP客户端，验证成功后再添加更多
- **荐**：保持配置文件之备份，便于回滚与恢复

### 多客户端配置管理

- **必**：确保每个客户端配置皆为独立之列表项
- **必**：为每个客户端用唯一之名称标识
- **荐**：按功能或用途对客户端进行分组与命名
- **荐**：用注释说明每个客户端之用途与配置

### 故障排除思路

1. **配置加载问题**：检查YAML语法、字段完整性、类型正确性
2. **服务器启动问题**：验证命令可用性、权限、依赖完整性
3. **网络连接问题**：检查URL可访问性、网络连通性、防火墙设置
4. **工具注册问题**：确认命名规范、工具可用性、参数正确性

## 常见问题排查

### 问题1：配置加载失败

**现象：** `⚠️`配置错误警告

**可能原因：**

- MCP服务器未安装或不在PATH中
- command路径错误
- 权限不足

**解决方法：**

- 确认MCP服务器已正确安装
- 用绝对路径或确认命令在PATH中
- 检查命令是否可在终端中手动执行

### 问题2：获取工具列表失败

**现象：** `⚠️`MCP工具加载失败警告

**可能原因：**

- MCP服务器未正常启动
- base_url配置错误（sse/streamable）
- 网络连接问题

**解决方法：**

- 检查MCP服务器日志
- 验证base_url可访问性
- 测试网络连接

### 问题3：工具执行无响应

**现象：** 工具注册成功，但执行时无响应或超时

**可能原因：**

- MCP服务器处理请求时间过长
- 参数传递错误
- 服务器端异常

**解决方法：**

- 检查MCP服务器日志
- 验证工具参数格式
- 增加服务器超时配置（若支持）

### 问题4：废弃文件方式警告

**现象：** `⚠️`废弃文件方式警告

**解决方法：**

- 将`~/.jarvis/mcp/`目录下之YAML配置迁移至`~/.jarvis/config.yaml`之`mcp`列表中
- 删除或重命名`~/.jarvis/mcp/`目录中之配置文件

## 执行检查清单

### 配置完成前必确认

- [ ] 已确认MCP服务器类型与通信方式
- [ ] 已准备MCP服务器运行环境与依赖
- [ ] 已规划合理之客户端命名方案

### 配置过程中必确认

- [ ] 配置已添加至`~/.jarvis/config.yaml`之`mcp`列表中
- [ ] 每个MCP配置皆含`type`字段
- [ ] stdio类型含`command`字段
- [ ] sse/streamable类型含`base_url`字段
- [ ] YAML格式正确（缩进、引号等）
- [ ] 已删除或禁用`~/.jarvis/mcp/`目录中之旧配置文件

### 配置完成后必确认

- [ ] 已重启Jarvis并检查启动日志
- [ ] 未出现配置错误警告
- [ ] MCP工具已成功注册（可通过工具列表验证）
- [ ] 已验证MCP工具功能正常可用

## 相关资源

- 配置管理：`{{ jarvis_src_dir }}/src/jarvis/jarvis_utils/config.py`
- MCP注册实现：`{{ jarvis_src_dir }}/src/jarvis/jarvis_tools/registry.py`（register_mcp_tool_by_config方法）
- MCP客户端实现：`{{ jarvis_src_dir }}/src/jarvis/jarvis_mcp/`
