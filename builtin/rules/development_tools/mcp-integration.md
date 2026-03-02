# MCP集成规则

## 规则简介

本规则指导如何通过配置文件将 MCP (Model Context Protocol) 工具集成到 Jarvis 中。

## 你必须遵循的工作流程

### MCP集成流程（严格执行）

1. **🔧 配置准备阶段**：
   - 确定MCP服务器类型和通信方式
   - 准备MCP服务器运行环境和依赖
   - 规划客户端命名和配置结构

2. **⚙️ 配置编写阶段**：
   - 在`~/.jarvis/config.yaml`文件中添加MCP配置
   - 根据服务器类型选择正确的客户端配置格式
   - 验证YAML语法和配置完整性

3. **🧪 验证测试阶段**：
   - 重启Jarvis加载新配置
   - 检查启动日志确认配置加载成功
   - 验证MCP工具是否正确注册和可用

4. **🔍 故障排除阶段**：
   - 分析配置错误和运行时问题
   - 根据错误信息进行针对性修复
   - 验证修复后的功能完整性

## 你必须遵守的原则

### 配置管理原则

- **必须**：MCP工具配置应放置在`~/.jarvis/config.yaml`文件中的`mcp`列表
- **必须**：每个MCP客户端配置都是一个独立的列表项
- **禁止**：直接修改`~/.jarvis/mcp/`目录下的YAML文件（此方式已废弃）
- **必须**：配置文件中必须指定MCP客户端类型
- **必须**：根据客户端类型提供必需的配置参数

### 类型安全原则

- **必须**：stdio类型必须包含`command`字段
- **必须**：sse和streamable类型必须包含`base_url`字段
- **必须**：使用正确的YAML语法和格式
- **禁止**：在配置中使用未定义的字段

### 验证确认原则

- **必须**：配置完成后重启Jarvis进行验证
- **必须**：检查启动日志确认无配置错误
- **必须**：验证MCP工具是否正确注册
- **禁止**：在未验证的情况下直接使用MCP工具

## 具体要求和规范

### 1. 配置文件位置要求（必须遵守）

**位置规范：**

- **必须**：MCP工具配置应放置在`~/.jarvis/config.yaml`文件中的`mcp`列表
- **必须**：每个MCP客户端配置都是一个独立的列表项
- **禁止**：直接修改`~/.jarvis/mcp/`目录下的YAML文件（此方式已废弃）

### 2. 配置结构要求（必须遵守）

**基本配置格式：**

每个MCP配置项必须包含以下字段：

```yaml
mcp:
  - type: "stdio" | "sse" | "streamable"  # 必须指定类型
    name: "自定义名称"                      # 可选，默认为"mcp"
    enable: true                             # 可选，默认为true
    # 其他类型特定参数...
```

### 3. MCP客户端类型选择要求

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

### 4. 配置验证要求（必须遵守）

**验证步骤：**

1. **必须**：保存`~/.jarvis/config.yaml`文件
2. **必须**：重启Jarvis以加载新配置
3. **必须**：观察启动日志确认MCP工具加载情况

**成功标志：**

- **必须**：没有出现`⚠️ 配置XXX缺少type字段`警告
- **必须**：没有出现`⚠️ 配置XXX缺少command字段`（stdio）或`⚠️ 配置XXX缺少base_url字段`（sse/streamable）警告
- **必须**：没有出现`⚠️ MCP配置XXX加载失败`错误

**工具命名规则：**

- **必须**：MCP工具会以`{name}.tool_call.{tool_name}`的形式注册
- **必须**：资源相关工具会以`{name}.resource.get_resource_list`和`{name}.resource.get_resource`的形式注册

例如，配置`name: "filesystem"`，服务器提供工具`read_file`，则注册的工具名为`filesystem.tool_call.read_file`

## 实践指导

### 配置前的准备工作

- **必须**：确认MCP服务器已正确安装并可用
- **必须**：了解MCP服务器的通信方式（stdio、sse、streamable）
- **必须**：规划合理的客户端命名，避免与现有工具冲突
- **必须**：准备MCP服务器运行所需的依赖和环境

### 配置过程中的最佳实践

- **推荐**：使用有意义的客户端名称，便于识别和管理
- **推荐**：为每个MCP客户端添加`enable`字段，便于临时禁用
- **推荐**：使用绝对路径或确认命令在PATH中，避免路径问题
- **推荐**：先配置单个MCP客户端，验证成功后再添加更多
- **推荐**：保持配置文件的备份，便于回滚和恢复

### 多客户端配置管理

- **必须**：确保每个客户端配置都是独立的列表项
- **必须**：为每个客户端使用唯一的名称标识
- **推荐**：按功能或用途对客户端进行分组和命名
- **推荐**：使用注释说明每个客户端的用途和配置

### 故障排除思路

1. **配置加载问题**：检查YAML语法、字段完整性、类型正确性
2. **服务器启动问题**：验证命令可用性、权限、依赖完整性
3. **网络连接问题**：检查URL可访问性、网络连通性、防火墙设置
4. **工具注册问题**：确认命名规范、工具可用性、参数正确性

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

## 执行检查清单

### 配置完成前必须确认

- [ ] 已确认MCP服务器类型和通信方式
- [ ] 已准备MCP服务器运行环境和依赖
- [ ] 已规划合理的客户端命名方案

### 配置过程中必须确认

- [ ] 配置已添加到`~/.jarvis/config.yaml`的`mcp`列表中
- [ ] 每个MCP配置都包含`type`字段
- [ ] stdio类型包含`command`字段
- [ ] sse/streamable类型包含`base_url`字段
- [ ] YAML格式正确（缩进、引号等）
- [ ] 已删除或禁用`~/.jarvis/mcp/`目录中的旧配置文件

### 配置完成后必须确认

- [ ] 已重启Jarvis并检查启动日志
- [ ] 没有出现配置错误警告
- [ ] MCP工具已成功注册（可通过工具列表验证）
- [ ] 已验证MCP工具功能正常可用

## 相关资源

- 配置管理：`{{ jarvis_src_dir }}/src/jarvis/jarvis_utils/config.py`
- MCP 注册实现：`{{ jarvis_src_dir }}/src/jarvis/jarvis_tools/registry.py` (register_mcp_tool_by_config 方法)
- MCP 客户端实现：`{{ jarvis_src_dir }}/src/jarvis/jarvis_mcp/`
