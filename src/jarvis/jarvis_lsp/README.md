# Jarvis LSP 客户端工具

`jarvis_lsp` 是一个命令行 LSP（Language Server Protocol）客户端工具，支持与各种语言的 LSP 服务器通信，提供代码符号查询等功能。

## 功能特性

- 支持多种编程语言的 LSP 服务器
- 自动检测文件语言类型
- 符号查询（列出函数、类、变量等）
- 支持人类可读和 JSON 格式输出
- 配置复用 `~/.jarvis/config.yaml`

## 安装

`jarvis_lsp` 已集成在 Jarvis 项目中，无需额外安装。

### 安装 LSP 服务器

`jarvis_lsp` 需要安装相应的 LSP 服务器才能工作。以下是常用语言的 LSP 服务器安装方式：

#### Python

```bash
pip install python-lsp-server
```

#### Go

```bash
go install golang.org/x/tools/gopls@latest
```

#### Rust

```bash
rustup component add rust-analyzer
```

#### C/C++

```bash
# Ubuntu/Debian
sudo apt-get install clangd

# macOS
brew install llvm

# 或从源码编译: https://clangd.llvm.org/installation/
```

#### JavaScript/TypeScript

```bash
npm install -g javascript-typescript-stdio typescript-language-server
```

#### 其他语言

查看 [LSP 服务器实现列表](https://microsoft.github.io/language-server-protocol/implementors/tools/) 获取更多语言的 LSP 服务器安装方式。

## 使用方法

### 命令

支持两个命令名称：

- `jarvis-lsp`
- `jlsp`

### 查询文件符号

````bash
# 查询文件的符号（人类可读格式）
jlsp symbols /path/to/file.py

# 查询文件的符号（JSON 格式）
jlsp symbols /path/to/file.py --json

# 指定 LSP 服务器命令
jlsp symbols /path/to/file.py --server-command "python -m pylsp"
``

### 查看版本

```bash
jlsp version
````

## 配置

### 内置默认配置

`jarvis_lsp` 内置了以下常用语言的 LSP 服务器配置，开箱即用：

| 语言       | LSP 服务器                            |
| ---------- | ------------------------------------- |
| Python     | `python -m pylsp`                     |
| Go         | `gopls`                               |
| Rust       | `rust-analyzer`                       |
| C/C++      | `clangd`                              |
| JavaScript | `javascript-typescript-stdio`         |
| TypeScript | `typescript-language-server --stdio`  |
| Lua        | `lua-language-server`                 |
| Bash       | `bash-language-server start`          |
| Ruby       | `solargraph stdio`                    |
| PHP        | `intelephense --stdio`                |
| HTML       | `vscode-html-language-server --stdio` |
| CSS        | `vscode-css-language-server --stdio`  |

### 配置文件位置

`~/.jarvis/config.yaml`

### 配置格式

```yaml
lsp:
  # 语言配置（会覆盖内置默认配置）
  languages:
    python:
      command: python
      args: ["-m", "pylsp"]
      file_extensions: [".py", ".pyi"]

    rust:
      command: rust-analyzer
      args: []
      file_extensions: [".rs"]

    go:
      command: gopls
      args: []
      file_extensions: [".go"]
```

### 配置说明

- 用户配置会覆盖内置默认配置
- `lsp.languages`: 定义语言到 LSP 服务器启动命令的映射
  - `command`: LSP 服务器可执行文件命令
  - `args`: 启动参数列表
  - `file_extensions`: 支持的文件扩展名列表
- 服务器命令应支持 stdin/stdout 通信方式（stdio）

## 示例

### Python 文件符号查询

```bash
# 内置了 Python LSP 服务器配置，开箱即用
# 查询符号
jlsp symbols myapp.py
```

### Rust 文件符号查询

```bash
# 内置了 Rust LSP 服务器配置，开箱即用
# 查询符号
jlsp symbols main.rs --json
```

### 使用自定义服务器命令

```bash
# 临时使用不同的服务器命令
jlsp symbols test.py --server-command "custom-lsp-server --stdio"
```

## 技术架构

```text
CLI 层 (cli.py)
  ↓
配置层 (config.py)
  ↓
LSP 客户端层 (client.py)
  ↓
协议层 (protocol.py)
```

## 开发说明

- 使用 `typer` 作为 CLI 框架
- 使用 `asyncio` 实现异步 LSP 通信
- 使用 `print` 进行输出
- 遵循项目代码规范（mypy、ruff、bandit 检查）

## 依赖

- Python 3.8+
- typer
- pydantic
- jarvis_utils
