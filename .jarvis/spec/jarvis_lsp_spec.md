# jarvis_lsp 工具功能规范

## 功能概述

jarvis_lsp 是一个命令行 LSP（Language Server Protocol）客户端工具，用于与各种语言服务器通信并获取代码分析结果。该工具支持配置不同语言的 LSP 服务器启动命令，并提供基础的 LSP 客户端接口，如列出指定文件的符号。

### 使用场景

- 代码分析：通过 LSP 协议获取代码结构信息
- 符号导航：查询文件中的定义、引用、符号等
- 多语言支持：通过配置支持不同语言的 LSP 服务器
- 命令行集成：方便在 CI/CD 或脚本中使用

## 接口定义

### 命令行接口

```bash
# 主命令
jarvis-lsp [OPTIONS] COMMAND [ARGS]...

# 短命令别名
jlsp [OPTIONS] COMMAND [ARGS]...
```

### 子命令

#### 1. symbols - 列出文件符号

```bash
jarvis-lsp symbols [OPTIONS] FILE_PATH
```

**参数：**

- `FILE_PATH`: 目标文件路径（必需）

**选项：**

- `--language TEXT`: 指定语言（如 python, rust, javascript），如果不指定则自动检测
- `--server-path TEXT`: 指定 LSP 服务器可执行文件路径（覆盖配置）
- `--json`: 以 JSON 格式输出
- `--kind TEXT`: 过滤符号类型（如 function, class, variable）

**返回：**

- 符号列表，包含名称、类型、位置、描述等信息

#### 2. version - 显示版本信息

```bash
jarvis-lsp version
```

### 配置文件接口

**配置文件位置：**

- 复用 `~/.jarvis/config.yaml`

**配置文件格式：**

在 `~/.jarvis/config.yaml` 中添加 `lsp` 配置节：

```yaml
lsp:
  languages:
    python:
      command: "python"
      args: ["-m", "pylsp"]
      file_extensions: [".py"]
    rust:
      command: "rust-analyzer"
      args: []
      file_extensions: [".rs"]
    javascript:
      command: "typescript-language-server"
      args: ["--stdio"]
      file_extensions: [".js", ".ts", ".jsx", ".tsx"]
```

## 输入输出说明

### 输入

1. **文件路径**：绝对路径或相对路径
2. **语言标识**：字符串，如 "python", "rust", "javascript"
3. **配置选项**：命令行参数或配置文件

### 输出

1. **符号列表**（默认格式）：

```
📋 符号列表 (test.py)

Function: main
  位置: 第 5 行
  描述: 主函数

Class: MyClass
  位置: 第 10 行
  描述: 示例类
```

2. **符号列表**（JSON 格式）：

```json
{
  "file": "/path/to/test.py",
  "symbols": [
    {
      "name": "main",
      "kind": "function",
      "line": 5,
      "column": 0,
      "description": "主函数"
    }
  ]
}
```

### 异常输出

- LSP 服务器启动失败：显示错误信息并退出（exit code 1）
- 文件不存在：显示错误信息并退出（exit code 1）
- LSP 通信失败：显示详细错误信息和堆栈
- 配置文件格式错误：显示错误位置和原因

## 功能行为

### 正常情况

1. **启动 LSP 服务器**：
   - 读取配置文件，获取对应语言的启动命令
   - 如果未指定语言，通过文件扩展名自动检测
   - 启动 LSP 服务器进程，建立 stdio 通信
   - 发送 `initialize` 请求，等待服务器响应

2. **列出符号**：
   - 打开目标文件，发送 `textDocument/didOpen` 通知
   - 发送 `textDocument/documentSymbol` 请求
   - 解析响应，格式化输出
   - 发送 `textDocument/didClose` 通知

### 边界情况

1. **文件扩展名未知**：提示用户指定语言或使用默认配置

2. **空文件**：返回空符号列表

3. **LSP 服务器不支持符号查询**：显示警告信息

4. **配置文件不存在或未配置 lsp 节**：使用内置默认配置或提示用户配置

### 异常情况

1. **LSP 服务器未安装**：提示安装方法和错误信息

2. **文件读取权限错误**：显示权限错误和解决建议

3. **通信超时**：显示超时错误，允许重试

4. **LSP 协议错误**：显示服务器返回的错误信息

## 验收标准

### 功能验收

1. ✅ 能够正确识别常见语言的文件扩展名（Python, Rust, JavaScript/TypeScript）
2. ✅ 能够成功启动配置的 LSP 服务器并完成初始化
3. ✅ 能够正确列出 Python 文件的函数和类符号
4. ✅ 能够正确列出 Rust 文件的函数、结构体和 trait 符号
5. ✅ 支持通过命令行参数覆盖配置文件中的服务器路径
6. ✅ 支持 JSON 格式输出，便于程序化使用
7. ✅ 支持命令别名 `jlsp` 和 `jarvis-lsp`

### 质量验收

1. ✅ 代码类型注解覆盖率 ≥ 90%
2. ✅ 单元测试覆盖率 ≥ 80%
3. ✅ 通过 mypy 类型检查（无错误）
4. ✅ 通过 ruff 代码风格检查
5. ✅ 通过 bandit 安全检查
6. ✅ 所有公共函数都有完整的 docstring

### 文档验收

1. ✅ README.md 包含安装说明和使用示例
2. ✅ 每个公共函数都有详细的 docstring
3. ✅ 配置文件格式有清晰的说明
4. ✅ 提供常见语言的 LSP 服务器配置示例

## 架构设计

### 模块划分

```
jarvis_lsp/
├── __init__.py          # 包初始化，导出公共接口
├── cli.py               # 命令行接口（typer）
├── client.py            # LSP 客户端核心类
├── config.py            # 配置读取
└── protocol.py          # LSP 协议定义和消息处理
```

### 核心类设计

#### LSPClient

```python
class LSPClient:
    def __init__(self, command: str, args: List[str])
    async def initialize(self) -> None
    async def open_document(self, file_path: str) -> None
    async def document_symbol(self, file_path: str) -> List[Symbol]
    async def close_document(self, file_path: str) -> None
    async def shutdown(self) -> None
```

#### ConfigReader

```python
class ConfigReader:
    def load_config(self) -> LSPConfig
    def get_language_config(self, language: str) -> LanguageConfig
    def detect_language(self, file_path: str) -> Optional[str]
```

### 技术依赖

- typer: CLI 框架
- pyyaml: 配置文件解析
- asyncio: 异步 LSP 通信
- typing: 类型注解

## 实现计划

### 阶段 1：基础框架（MVP）
- [ ] 创建目录结构
- [ ] 实现配置读取模块
- [ ] 实现 CLI 框架（typer）
- [ ] 实现版本信息命令
- [ ] 编写基础测试

### 阶段 2：LSP 客户端核心
- [ ] 实现 LSP 协议消息处理
- [ ] 实现 LSPClient 类
- [ ] 实现服务器初始化和关闭
- [ ] 实现文档打开/关闭

### 阶段 3：符号查询功能
- [ ] 实现 documentSymbol 请求
- [ ] 实现符号数据结构
- [ ] 实现符号输出格式化
- [ ] 实现文件语言自动检测

### 阶段 4：测试和优化
- [ ] 编写完整的单元测试
- [ ] 集成测试（与真实 LSP 服务器）
- [ ] 性能优化
- [ ] 错误处理完善
- [ ] 文档编写

## 参考资源

- LSP 规范: https://microsoft.github.io/language-server-protocol/
- typer 文档: https://typer.tiangolo.com/
- Python LSP 客户端实现: https://github.com/python-lsp/python-lsp-client