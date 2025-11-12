# LSP客户端集成指南

## 概述

Jarvis CodeAgent 集成了 LSP 客户端功能，可以连接到现有的 Language Server Protocol 服务器（如 pylsp、typescript-language-server 等），获取代码补全、悬停信息、定义跳转等功能，辅助代码生成和修改。

## 功能特性

### 支持的LSP操作

1. **代码补全 (completion)** - 获取当前位置的代码补全建议
2. **悬停信息 (hover)** - 获取符号的详细信息（类型、文档等）
3. **定义跳转 (definition)** - 查找符号的定义位置
4. **引用查找 (references)** - 查找符号的所有引用位置
5. **文档符号 (document_symbols)** - 获取文件中的所有符号（函数、类等）

### 支持的编程语言

- **Python** - 使用 `pylsp`
- **TypeScript/JavaScript** - 使用 `typescript-language-server`
- **Rust** - 使用 `rust-analyzer`
- **Go** - 使用 `gopls`
- **Java** - 使用 `jdtls`

## 使用方法

### 在CodeAgent中使用

LSP客户端工具已自动集成到CodeAgent中，工具名为 `lsp_client`。

#### 示例1：获取代码补全

```json
{
  "name": "lsp_client",
  "arguments": {
    "action": "completion",
    "file_path": "src/main.py",
    "line": 10,
    "character": 5
  }
}
```

#### 示例2：获取悬停信息

```json
{
  "name": "lsp_client",
  "arguments": {
    "action": "hover",
    "file_path": "src/main.py",
    "line": 10,
    "character": 5
  }
}
```

#### 示例3：查找定义

```json
{
  "name": "lsp_client",
  "arguments": {
    "action": "definition",
    "file_path": "src/main.py",
    "line": 10,
    "character": 5
  }
}
```

#### 示例4：查找引用

```json
{
  "name": "lsp_client",
  "arguments": {
    "action": "references",
    "file_path": "src/main.py",
    "line": 10,
    "character": 5
  }
}
```

#### 示例5：获取文档符号

```json
{
  "name": "lsp_client",
  "arguments": {
    "action": "document_symbols",
    "file_path": "src/main.py"
  }
}
```

## 安装LSP服务器

### Python (pylsp)

```bash
pip install python-lsp-server
```

### TypeScript/JavaScript

```bash
npm install -g typescript-language-server typescript
```

### Rust

```bash
# rust-analyzer 通常随 Rust 工具链一起安装
# 或使用 rustup component add rust-analyzer
```

### Go

```bash
go install golang.org/x/tools/gopls@latest
```

### Java

```bash
# 下载 Eclipse JDT Language Server
# 或使用 IDE 内置的服务器
```

## 使用场景

### 场景1：代码生成时获取补全建议

当CodeAgent需要生成代码时，可以先查询LSP服务器获取可用的API和函数：

```
用户：在文件 src/main.py 第20行生成一个处理数据的函数

CodeAgent可以：
1. 使用 lsp_client 获取当前位置的补全建议
2. 查看可用的导入和函数
3. 基于这些信息生成更准确的代码
```

### 场景2：理解代码结构

当需要修改代码时，先了解代码结构：

```
用户：修改 src/utils.py 中的 process_data 函数

CodeAgent可以：
1. 使用 lsp_client 获取 process_data 的定义位置
2. 使用 lsp_client 查找所有引用，了解影响范围
3. 使用 lsp_client 获取函数的文档和类型信息
4. 基于这些信息进行更安全的修改
```

### 场景3：代码审查

在生成代码后，使用LSP验证代码的正确性：

```
CodeAgent生成代码后：
1. 使用 lsp_client 获取文档符号，验证函数/类是否正确创建
2. 使用 lsp_client 检查类型信息，确保类型正确
3. 使用 lsp_client 查找引用，确保没有破坏现有代码
```

## 配置

### 项目根目录

LSP客户端会自动检测项目根目录，也可以手动指定：

```python
# 在工具调用中指定
{
  "name": "lsp_client",
  "arguments": {
    "action": "completion",
    "file_path": "src/main.py",
    "project_root": "/path/to/project"  # 可选
  }
}
```

### 自定义LSP服务器

可以在代码中扩展 `LSP_SERVERS` 字典来添加新的LSP服务器：

```python
from jarvis.jarvis_tools.lsp_client import LSP_SERVERS, LSPServerConfig

LSP_SERVERS["cpp"] = LSPServerConfig(
    name="clangd",
    command=["clangd"],
    language_ids=["cpp", "c"],
    file_extensions=[".cpp", ".c", ".h", ".hpp"],
)
```

## 性能优化

### 客户端缓存

LSP客户端会按项目根目录和语言进行缓存，避免重复创建连接。

### 连接管理

- 客户端在首次使用时创建
- 建议在长时间不使用时关闭连接（当前实现会在进程结束时自动关闭）

## 故障排除

### LSP服务器未找到

**问题**：提示"无法创建LSP客户端"或"LSP服务器未安装"

**解决**：
1. 确认已安装对应的LSP服务器
2. 确认LSP服务器命令在PATH中
3. 检查 `LSP_SERVERS` 配置中的命令是否正确

### 连接超时

**问题**：LSP请求超时或无响应

**解决**：
1. 检查LSP服务器是否正常运行
2. 检查项目根目录是否正确
3. 查看日志了解详细错误信息

### 结果不准确

**问题**：LSP返回的结果不准确或过时

**解决**：
1. 确保文件已保存
2. 使用 `notify_did_change` 通知LSP服务器文件已更新
3. 等待LSP服务器完成索引

## 技术细节

### 通信协议

LSP客户端使用 JSON-RPC 2.0 协议与LSP服务器通信，通过标准输入/输出（stdio）进行数据传输。

### 请求格式

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "textDocument/completion",
  "params": {
    "textDocument": {"uri": "file:///path/to/file"},
    "position": {"line": 0, "character": 0}
  }
}
```

### 响应格式

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "items": [...]
  }
}
```

## 未来增强

1. **异步支持** - 使用异步I/O提高性能
2. **增量更新** - 支持增量文档更新
3. **更多语言** - 支持更多编程语言的LSP服务器
4. **智能缓存** - 更智能的缓存策略
5. **错误恢复** - 自动重连和错误恢复机制

## 相关文档

- [LSP规范](https://microsoft.github.io/language-server-protocol/)
- [CodeAgent文档](./code_agent.py)

