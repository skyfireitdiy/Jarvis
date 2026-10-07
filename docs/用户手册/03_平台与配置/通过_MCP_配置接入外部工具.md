# 通过 MCP 配置接入外部工具

## 使用场景

如果你希望把外部服务或外部进程提供的能力接入 Jarvis，并作为工具使用，可以通过配置文件里的 `mcp` 项进行注册。这个方式适合接入你自己维护的 MCP 服务，或者第三方提供的 MCP 工具服务。

## 操作步骤

1. 打开 Jarvis 全局配置文件：`~/.jarvis/config.yaml`。
2. 添加或修改 `mcp` 配置项。它是一个数组，每一项代表一条 MCP 连接配置。
3. 先确认你要接入的服务属于哪种方式，例如：
   - 本地命令启动型
   - 基于 URL 的远程服务型
4. 按服务类型填写必要字段。至少要有：
   - 名称
   - 类型
   - 是否启用
   - 该类型要求的连接参数
5. 示例一：本地命令启动型

   ```yaml
   mcp:
     - name: local-mcp
       type: stdio
       enable: true
       command: python
       args:
         - /path/to/your_mcp_server.py
   ```

6. 示例二：远程服务型

   ```yaml
   mcp:
     - name: remote-mcp
       type: sse
       enable: true
       base_url: http://127.0.0.1:8081/sse
   ```

7. 示例三：基于 Streamable HTTP 的远程服务型

   ```yaml
   mcp:
     - name: stream-mcp
       type: streamable
       enable: true
       base_url: https://example.com
       endpoint_path: mcp
   ```

   > `base_url` 填服务的主机地址，`endpoint_path` 填 MCP 端点路径（默认 `mcp`），二者拼接为实际请求地址。需要额外请求头（如 User-Agent、Bearer 认证）时，用 `headers` 字段指定。

8. 保存配置文件。
9. 重新启动会话，让 Jarvis 重新读取 MCP 配置。
10. 启动后检查这些外部工具是否已经出现在当前可用工具中。

## 你会看到的提示与反馈

- 如果某条 MCP 配置被显式关闭，系统会直接跳过，不会注册这条能力。
- 如果配置缺少必要字段，例如缺少类型、缺少命令或缺少地址，系统会给出警告。
- 如果连接成功且外部端返回了工具列表，这些工具会被注册成当前可用工具。
- 除了工具调用外，系统还可能额外注册资源列表和资源读取能力。
- 如果远端返回空工具列表，系统会给出警告，而不是假装接入成功。

## 示例：Parallel Search MCP（免 API key 网页搜索）

如果你需要让 Jarvis 搜索最新网页或读取指定网页内容，又不想配置任何 API key，可以接入 Parallel 官方提供的免费 Search MCP。它提供两个工具：

- `web_search`：实时网页搜索，返回相关结果与摘要。
- `web_fetch`：从指定 URL 提取干净的 Markdown 内容。

**免费匿名使用，无需 API key**（匿名有较低的速率限制；如需更高速率限制，可在 `headers` 中传 Parallel API key 的 Bearer 认证）。端点：`https://search.parallel.ai/mcp`。

在 `~/.jarvis/config.yaml` 中加入以下配置：

```yaml
mcp:
  - name: parallel-search
    type: streamable
    enable: true
    base_url: https://search.parallel.ai
    endpoint_path: mcp
    headers:
      User-Agent: Jarvis
```

说明：

- `base_url` 填 Parallel 的主机地址，`endpoint_path` 填 `mcp`，这样实际请求的是 `https://search.parallel.ai/mcp`（不要带尾斜杠，Parallel 端点不接受尾斜杠）。
- `headers.User-Agent` 用于标识请求来源为 Jarvis，可按需调整。
- 接入成功后，会注册 `parallel-search.tool_call.web_search` 与 `parallel-search.tool_call.web_fetch` 两个工具。
- 如需更高速率限制，可申请 Parallel API key 并通过 `headers.Authorization` 传入（如 `Authorization: Bearer <你的key>`）。

## 注意事项

- 配置项名称是 `mcp`。
- 不同连接类型需要的字段不同，写配置前先确认目标服务支持哪种接法。
- 如果配置文件里已经明确写了 `mcp`，系统会优先按配置加载，而不是优先扫描本地 MCP 目录。
- 即使接入成功，这些工具后续仍可能被 `tool_group`、白名单或黑名单过滤。
