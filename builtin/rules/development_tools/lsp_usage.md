# LSP 工具使用规则

## 规则简介

本规则指导 Jarvis 如何使用 jarvis_lsp（jlsp）工具来增强代码理解和代码修改能力。jlsp 工具通过与语言服务器（Language Server Protocol, LSP）通信，提供代码导航、符号查询、诊断信息、代码动作等功能。

**核心价值**：

- 提供 LLM Agent 准确的代码语义信息
- 支持代码导航和符号定位
- 提供代码诊断和修复建议
- 适合 LLM 的简化参数设计

## 你必须遵守的原则

### 1. 工具选择原则（必须遵守）

**适用场景**：

- **必须**：当需要理解代码结构、查找符号定义、查看符号引用时，优先使用 jlsp 工具
- **必须**：当需要获取代码诊断信息（语法错误、lint 警告）时，使用 jlsp diagnostic
- **必须**：当需要获取代码修复建议（重构、优化）时，使用 jlsp codeAction 相关命令
- **建议**：当需要理解函数、类的语义信息时，使用 jlsp hover
- **禁止**：不要使用 jlsp 工具进行简单的文本搜索（应使用 rg、grep）

**工具优势**：

- 准确性：基于 LSP 服务器的语义分析，而非简单的文本匹配
- 完整性：包含类型信息、文档字符串、调用关系等
- 一致性：统一的接口，支持多种编程语言

### 2. 命令使用原则（必须遵守）

**符号查询类命令**（优先使用）：

1. **document_symbols** - 列出文件中的所有符号

   ```bash
   jlsp document_symbols <file_path>
   ```

   - **必须**：在分析新文件时，先使用此命令了解文件结构
   - **必须**：在查找符号前，确认符号名称和位置
   - **输出**：包含所有类、函数、变量的列表及其位置

2. **def-name** - 通过符号名查找定义（最适合 LLM）

   ```bash
   jlsp def-name <file_path> <symbol_name>
   ```

   - **必须**：LLM 优先使用此命令，只需知道符号名称
   - **禁止**：不要使用需要精确列号的命令
   - **适用**：查找函数、类、变量等的定义

3. **hover** - 获取符号的悬停信息

   ```bash
   jlsp hover <file_path> <line> <column> --language <lang>
   ```

   - **必须**：在需要理解符号的语义、类型、文档字符串时使用
   - **输出**：包含类型信息、参数说明、文档字符串等

**诊断和修复类命令**：

1. **diagnostic** - 获取代码诊断信息

   ```bash
   jlsp diagnostic <file_path>
   ```

   - **必须**：在检查代码质量、查找错误时使用
   - **输出**：包含所有诊断信息（ERROR/WARNING/INFO/HINT）
   - **注意**：pylsp 可能不支持此方法，会显示友好错误

2. **codeAction-by-name** - 通过符号名获取修复建议（最适合 LLM）

   ```bash
   jlsp codeAction-by-name <file_path> <symbol_name>
   ```

   - **必须**：LLM 优先使用此命令获取修复建议
   - **适用**：获取针对特定符号的修复、重构、优化建议

3. **codeAction** - 通过行号获取修复建议

   ```bash
   jlsp codeAction <file_path> <line>
   ```

   - **建议**：当只需要行号时使用此命令
   - **特点**：列号默认为 0，适合快速查询

### 3. LLM 友好使用原则（必须遵守）

**参数简化**：

- **必须**：优先使用基于符号名的命令（如 `def-name`、`codeAction-by-name`）
- **必须**：避免使用需要精确列号的命令（LLM 不擅长处理精确的列号）
- **必须**：使用 `--language` 参数指定编程语言（默认为 python）

**使用流程**：

1. 先使用 `document_symbols` 了解文件结构
2. 获取符号列表后，使用符号名进行查询
3. 使用 `hover` 获取详细的语义信息
4. 使用 `diagnostic` 检查代码问题
5. 使用 `codeAction-by-name` 获取修复建议

**JSON 输出**：

- **建议**：当需要程序化处理结果时，使用 `--json` 参数
- **输出**：结构化的 JSON 格式，便于解析和处理

### 4. 守护进程管理原则（必须遵守）

**自动启动**：

- **必须**：守护进程会在第一次使用任何 jlsp 命令时自动启动
- **禁止**：不要手动启动守护进程（`jlsp daemon start` 已废弃）

**状态检查**：

- **建议**：使用 `jlsp daemon status` 查看守护进程状态
- **建议**：使用 `jlsp daemon stop` 停止守护进程（仅用于调试）

## 命令完整列表

### 符号查询类

| 命令             | 参数                    | 说明                 | LLM 适用性 |
| ---------------- | ----------------------- | -------------------- | ---------- |
| document_symbols | file_path               | 列出文件中的所有符号 | ⭐⭐⭐⭐⭐ |
| def-name         | file_path, symbol_name  | 通过符号名查找定义   | ⭐⭐⭐⭐⭐ |
| hover            | file_path, line, column | 获取符号悬停信息     | ⭐⭐⭐⭐   |

### 诊断和修复类

| 命令               | 参数                   | 说明                   | LLM 适用性 |
| ------------------ | ---------------------- | ---------------------- | ---------- |
| diagnostic         | file_path              | 获取代码诊断信息       | ⭐⭐⭐⭐⭐ |
| codeAction-by-name | file_path, symbol_name | 通过符号名获取修复建议 | ⭐⭐⭐⭐⭐ |
| codeAction         | file_path, line        | 通过行号获取修复建议   | ⭐⭐⭐⭐   |

### 守护进程管理类

| 命令          | 参数 | 说明             |
| ------------- | ---- | ---------------- |
| daemon status | -    | 查看守护进程状态 |
| daemon stop   | -    | 停止守护进程     |

## 使用示例

### 示例 1：分析一个 Python 文件

```bash
# 1. 先了解文件结构
jlsp document_symbols src/main.py

# 2. 查找某个函数的定义
jlsp def-name src/main.py MyClass

# 3. 获取函数的详细信息
jlsp hover src/main.py 10 5

# 4. 检查代码问题
jlsp diagnostic src/main.py

# 5. 获取修复建议
jlsp codeAction-by-name src/main.py MyClass
```

### 示例 2：查找所有引用

```bash
# 1. 先获取符号列表
jlsp document_symbols src/main.py

# 2. 查找符号的所有引用
jlsp ref-name src/main.py MyClass
```

### 示例 3：JSON 输出格式

```bash
# 获取结构化的 JSON 输出
jlsp document_symbols src/main.py --json
jlsp diagnostic src/main.py --json
jlsp codeAction-by-name src/main.py MyClass --json
```

## 常见问题和注意事项

### 1. pylsp 限制

**不支持的功能**：

- `textDocument/diagnostic` - pylsp 不支持此方法
- `textDocument/implementation` - pylsp 不支持此方法
- `textDocument/typeDefinition` - pylsp 不支持此方法

**应对方法**：

- 工具会返回友好的错误信息
- 可以尝试使用其他 LSP 服务器（如 rust-analyzer、gopls 等）

### 2. 性能优化

**守护进程复用**：

- 守护进程长期运行，避免重复启动
- LSP 服务器实例会被复用
- 后续查询性能显著提升

**超时设置**：

- LSP 服务器初始化超时：30 秒
- 请求超时：30 秒
- 如果超时，可以检查 LSP 服务器配置

### 3. 错误处理

**常见错误**：

- `LSP server not initialized` - 守护进程未启动
- `Method Not Found` - LSP 服务器不支持该方法
- `Timeout` - LSP 服务器响应超时

**处理方法**：

- 检查守护进程状态：`jlsp daemon status`
- 尝试重启守护进程：`jlsp daemon stop` 然后重新执行命令
- 检查 LSP 服务器配置

## 最佳实践

### 1. 代码理解流程

```bash
# 步骤 1：了解文件结构
document_symbols → 获取符号列表

# 步骤 2：查找符号定义
def-name → 定位符号位置

# 步骤 3：获取符号信息
hover → 理解符号语义

# 步骤 4：查看符号引用
ref-name → 了解使用情况

# 步骤 5：检查代码问题
diagnostic → 发现潜在问题

# 步骤 6：获取修复建议
codeAction-by-name → 应用修复方案
```

### 2. LLM 使用建议

**优先使用**：

- 基于符号名的命令（`def-name`、`ref-name`、`codeAction-by-name`）
- 只需要行号的命令（`codeAction`）

**避免使用**：

- 需要精确列号的命令
- 需要手动管理守护进程的命令

### 3. 多语言支持

**支持的编程语言**：

- Python（pylsp）- 默认支持
- Rust（rust-analyzer）- 需要配置
- JavaScript/TypeScript（typescript-language-server）- 需要配置
- Go（gopls）- 需要配置
- 其他任何实现了 LSP 协议的语言服务器

**必须遵守原则**：

- **必须**：如果 LSP server 不存在，必须先安装对应的 LSP server
- **必须**：安装 LSP server 后，确保其在系统 PATH 中可访问

**通用 LSP Server 安装流程**：

1. **查找目标语言的 LSP server**
   - 访问 <https://langserver.org/> 查看已知的 LSP server 列表
   - 在 GitHub 或搜索引擎中搜索 `"<language> language server"`
   - 查看目标语言的官方文档或社区推荐

2. **安装 LSP server**
   - **通过包管理器安装**（推荐）

     ```bash
     # Python
     pip install python-lsp-server

     # Node.js
     npm install -g <language-server-name>

     # Go
     go install <package-path>

     # Rust
     cargo install <crate-name>

     # 系统包管理器
     apt install <language-server>   # Debian/Ubuntu
     brew install <language-server>  # macOS
     pacman -S <language-server>     # Arch Linux
     ```

   - **下载预编译二进制**
     - 访问 LSP server 的 GitHub Releases 页面
     - 下载对应平台的二进制文件
     - 解压并移动到 PATH 中的目录（如 `/usr/local/bin` 或 `~/.local/bin`）

   - **从源代码编译**

     ```bash
     git clone <repository-url>
     cd <repository>
     cargo build --release  # 或 make、npm run build 等
     cp target/release/<binary> /usr/local/bin/
     ```

3. **验证安装**

   ```bash
   # 方法 1：检查命令是否可执行
   <lsp-server-command> --version
   <lsp-server-command> --help

   # 方法 2：检查命令是否在 PATH 中
   which <lsp-server-command>
   where <lsp-server-command>  # Windows

   # 方法 3：使用 jlsp 测试
   jlsp document_symbols test.<ext> --language <lang>
   ```

4. **配置 jlsp 使用新的 LSP server**
   - 如果使用 `--language` 参数，确保使用正确的 languageId
   - 常见 languageId：`python`, `rust`, `javascript`, `typescript`, `go`, `cpp`, `java`, etc.
   - 如果 LSP server 不在 PATH 中，需要设置绝对路径或添加到 PATH

**常见语言 LSP Server 示例**：

| 语言                  | LSP Server                 | 安装命令                                               | LanguageId                 |
| --------------------- | -------------------------- | ------------------------------------------------------ | -------------------------- |
| Python                | python-lsp-server          | `pip install "python-lsp-server[all]"`                 | `python`                   |
| Rust                  | rust-analyzer              | `rustup component add rust-analyzer`                   | `rust`                     |
| JavaScript/TypeScript | typescript-language-server | `npm install -g typescript typescript-language-server` | `javascript`, `typescript` |
| Go                    | gopls                      | `go install golang.org/x/tools/gopls@latest`           | `go`                       |
| C/C++                 | clangd                     | `apt install clangd` 或 `brew install clangd`          | `c`, `cpp`                 |
| Java                  | jdt.ls                     | 下载 Eclipse 插件或使用 VSCode 扩展                    | `java`                     |
| PHP                   | intelephense               | `npm install -g intelephense`                          | `php`                      |
| Lua                   | lua-language-server        | 下载二进制或从源码编译                                 | `lua`                      |

**安装失败排查**：

1. **检查系统环境**

   ```bash
   # 检查 PATH
   echo $PATH

   # 检查包管理器
   pip --version
   npm --version
   go version
   rustc --version
   ```

2. **检查权限**
   - 如果需要 sudo，使用 `sudo pip install` 或 `sudo npm install -g`
   - 或使用用户目录安装：`pip install --user`、`npm config set prefix ~/.local`

3. **查看错误日志**
   - 大多数 LSP server 在启动时会输出详细日志
   - 可以在终端直接运行 `<lsp-server-command>` 查看错误

4. **查找替代方案**
   - 如果一个 LSP server 不工作，可以尝试其他实现
   - 例如：Python 有 pyls、pylsp、pyright 等多种选择

**使用方法**：

```bash
jlsp document_symbols src/main.rs --language rust
jlsp def-name src/main.rs MyStruct --language rust
```

## 总结

**核心原则**：

1. 优先使用基于符号名的命令，避免精确列号
2. 先了解文件结构，再进行符号查询
3. 结合诊断和修复建议，提升代码质量
4. 利用守护进程复用，优化性能

**适用场景**：

- 代码理解和分析
- 符号导航和定位
- 代码质量检查
- 代码修复和重构

**不适用场景**：

- 简单的文本搜索（应使用 rg、grep）
- 非代码文件的查询
- 不支持 LSP 的编程语言
