---
name: lsp_usage
description: 当需要使用LSP工具进行代码分析或开发环境配置时触发。每当用户提及"LSP"、"Language Server"、"代码导航"、"符号查询"、"代码诊断"、"类型推导"、"代码补全"时触发。不触发：仅用grep搜索代码；仅运行代码不分析；不涉及LSP的简单文件操作。
---

# LSP 工具使用规则

## 规则简介

此规则指导Jarvis如何使用jarvis_lsp（jlsp）工具以增强代码理解与代码修改之能力。jlsp工具通过与语言服务器（Language Server Protocol, LSP）通信，提供代码导航、符号查询、诊断信息、代码动作等功能。

**核心价值**：

- 为LLM Agent提供准确之代码语义信息
- 支持代码导航与符号定位
- 提供代码诊断与修复建议
- 适合LLM之简化参数设计

## 汝必守之原则

### 1. 工具选择原则（必守）

**适用场景**：

- **必**：当需理解代码结构、查找符号定义、查看符号引用时，优先用jlsp工具
- **必**：当需获取代码诊断信息（语法错误、lint警告）时，用jlsp diagnostic
- **必**：当需获取代码修复建议（重构、优化）时，用jlsp codeAction相关命令
- **建议**：当需理解函数、类之语义信息时，用jlsp hover
- **禁**：勿用jlsp工具进行简单之文本搜索（应用rg、grep）

**工具优势**：

- 准确性：基于LSP服务器之语义分析，非简单之文本匹配
- 完整性：含类型信息、文档字符串、调用关系等
- 一致性：统一之接口，支持多种编程语言

### 2. 命令使用原则（必守）

**符号查询类命令**（优先用）：

1. **document_symbols** - 列出文件中所有符号

   ```bash
   jlsp document_symbols <file_path>
   ```

   - **必**：分析新文件时，先用此命令了解文件结构
   - **必**：查找符号前，确认符号名称与位置
   - **输出**：含所有类、函数、变量之列表及其位置

2. **def-name** - 通过符号名查找定义（最适合LLM）

   ```bash
   jlsp def-name <file_path> <symbol_name>
   ```

   - **必**：LLM优先用此命令，只需知符号名称
   - **禁**：勿用需精确列号之命令
   - **适用**：查找函数、类、变量等之定义

3. **hover** - 获取符号之悬停信息

   ```bash
   jlsp hover <file_path> <line> <column> --language <lang>
   ```

   - **必**：`--language`参数为必填项，必指定编程语言

   - **必**：需理解符号之语义、类型、文档字符串时用之
   - **输出**：含类型信息、参数说明、文档字符串等

**诊断与修复类命令**：

1. **diagnostic** - 获取代码诊断信息

   ```bash
   jlsp diagnostic <file_path> --language <lang>
   ```

   - **必**：`--language`参数为必填项，必指定编程语言

   - **必**：检查代码质量、查找错误时用之
   - **输出**：含所有诊断信息（ERROR/WARNING/INFO/HINT）
   - **注意**：pylsp可能不支持此方法，会显示友好错误

2. **codeAction-by-name** - 通过符号名获取修复建议（最适合LLM）

   ```bash
   jlsp codeAction-by-name <file_path> <symbol_name> --language <lang>
   ```

   - **必**：`--language`参数为必填项，必指定编程语言

   - **必**：LLM优先用此命令获取修复建议
   - **适用**：获取针对特定符号之修复、重构、优化建议

3. **codeAction** - 通过行号获取修复建议

   ```bash
   jlsp codeAction <file_path> <line>
   ```

   - **建议**：当只需行号时用此命令
   - **特点**：列号默认为0，适合快速查询

### 3. LLM友好使用原则（必守）

**参数简化**：

- **必**：优先用基于符号名之命令（如`def-name`、`codeAction-by-name`）
- **必**：避用需精确列号之命令（LLM不擅处理精确之列号）
- **必**：用`--language`参数指定编程语言（必填项，无默认值）

**使用流程**：

1. 先用`document_symbols`了解文件结构
2. 获取符号列表后，用符号名进行查询
3. 用`hover`获取详细之语义信息
4. 用`diagnostic`检查代码问题
5. 用`codeAction-by-name`获取修复建议

**JSON输出**：

- **建议**：当需程序化处理结果时，用`--json`参数
- **输出**：结构化之JSON格式，便于解析与处理

### 4. 守护进程管理原则（必守）

**自动启动**：

- **必**：守护进程会在首次用任何jlsp命令时自动启动
- **禁**：勿手动启动守护进程（`jlsp daemon start`已废弃）

**状态检查**：

- **建议**：用`jlsp daemon status`查看守护进程状态
- **建议**：用`jlsp daemon stop`停止守护进程（仅用于调试）

## 命令完整列表

### 符号查询类

| 命令             | 参数                    | 说明                 | LLM适用性 |
| ---------------- | ----------------------- | -------------------- | ---------- |
| document_symbols | file_path               | 列出文件中所有符号 | ⭐⭐⭐⭐⭐ |
| def-name         | file_path, symbol_name  | 通过符号名查找定义   | ⭐⭐⭐⭐⭐ |
| ref-name         | file_path, symbol_name  | 通过符号名查找引用   | ⭐⭐⭐⭐⭐ |
| impl-name        | file_path, symbol_name  | 通过符号名查找实现   | ⭐⭐⭐⭐⭐ |
| callers-name     | file_path, symbol_name  | 查找函数内调用之符号 | ⭐⭐⭐⭐⭐ |
| hover            | file_path, line, column | 获取符号悬停信息     | ⭐⭐⭐⭐   |

### 诊断与修复类

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

### 示例1：分析一个Python文件

```bash
# 1. 先了解文件结构
jlsp document_symbols src/main.py --language python

# 2. 查找某函数之定义
jlsp def-name src/main.py MyClass --language python

# 3. 获取函数之详细信息
jlsp hover src/main.py 10 5 --language python

# 4. 检查代码问题
jlsp diagnostic src/main.py --language python

# 5. 获取修复建议
jlsp codeAction-by-name src/main.py MyClass --language python
```

### 示例2：查找所有引用

```bash
# 1. 先获取符号列表
jlsp document_symbols src/main.py --language python

# 2. 查找符号之所有引用
jlsp ref-name src/main.py MyClass --language python
```

### 示例3：查找函数调用之符号（被调用方）

```bash
# 1. 先获取符号列表
jlsp document_symbols src/main.py --language python

# 2. 查找函数内部调用之所有符号
jlsp callers-name src/main.py my_function --language python

# 3. 用JSON格式输出（默认）
jlsp callers-name src/main.py my_function --language python
```

**说明**：`callers-name`命令用于分析指定函数内部调用了哪些其他符号，返回这些被调用符号之定义位置。此对于理解函数依赖关系非常有用。

### 示例4：JSON输出格式

```bash
# 获取结构化之JSON输出（默认）
jlsp document_symbols src/main.py --language python
jlsp diagnostic src/main.py --language python
jlsp codeAction-by-name src/main.py MyClass --language python
```

## 常见问题与注意事项

### 1. pylsp限制

**不支持之功能**：

- `textDocument/diagnostic` - pylsp不支持此方法
- `textDocument/implementation` - pylsp不支持此方法
- `textDocument/typeDefinition` - pylsp不支持此方法

**应对方法**：

- 工具会返回友好之错误信息
- 可尝试用其他LSP服务器（如rust-analyzer、gopls等）

### 2. 性能优化

**守护进程复用**：

- 守护进程长期运行，避重复启动
- LSP服务器实例会被复用
- 后续查询性能显著提升

**超时设置**：

- LSP服务器初始化超时：30秒
- 请求超时：30秒
- 若超时，可检查LSP服务器配置

### 3. 错误处理

**常见错误**：

- `LSP server not initialized` - 守护进程未启动
- `Method Not Found` - LSP服务器不支持该方法
- `Timeout` - LSP服务器响应超时

**处理方法**：

- 检查守护进程状态：`jlsp daemon status`
- 尝试重启守护进程：`jlsp daemon stop`然后重新执行命令
- 检查LSP服务器配置

## 最佳实践

### 1. 代码理解流程

```bash
# 步骤1：了解文件结构
document_symbols → 获取符号列表

# 步骤2：查找符号定义
def-name → 定位符号位置

# 步骤3：获取符号信息
hover → 理解符号语义

# 步骤4：查看符号引用
ref-name → 了解使用情况

# 步骤5：检查代码问题
diagnostic → 发现潜在问题

# 步骤6：获取修复建议
codeAction-by-name → 应用修复方案
```

### 2. LLM使用建议

**优先用**：

- 基于符号名之命令（`def-name`、`ref-name`、`codeAction-by-name`）
- 只需行号之命令（`codeAction`）

**避用**：

- 需精确列号之命令
- 需手动管理守护进程之命令

### 3. 多语言支持

**支持之编程语言**：

- Python（pylsp）- 默认支持
- Rust（rust-analyzer）- 需配置
- JavaScript/TypeScript（typescript-language-server）- 需配置
- Go（gopls）- 需配置
- 其他任何实现了LSP协议之语言服务器

**必守原则**：

- **必**：若LSP server不存在，必先安装对应之LSP server
- **必**：安装LSP server后，确保其在系统PATH中可访问

**通用LSP Server安装流程**：

1. **查找目标语言之LSP server**
   - 访问<https://langserver.org/>查看已知之LSP server列表
   - 在GitHub或搜索引擎中搜索`"<language> language server"`
   - 查看目标语言之官方文档或社区推荐

2. **安装LSP server**
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
   # 方法1：检查命令是否可执行
   <lsp-server-command> --version
   <lsp-server-command> --help

   # 方法2：检查命令是否在PATH中
   which <lsp-server-command>
   where <lsp-server-command>  # Windows

   # 方法3：用jlsp测试
   jlsp document_symbols test.<ext> --language <lang>
   ```

4. **配置jlsp使用新之LSP server**
   - **必**：用`--language`参数指定编程语言（必填项）
   - 确保用正确之languageId
   - 常见languageId：`python`, `rust`, `javascript`, `typescript`, `go`, `cpp`, `java`, etc.
   - 若LSP server不在PATH中，需设绝对路径或添加至PATH

**常见语言LSP Server示例**：

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
   # 检查PATH
   echo $PATH

   # 检查包管理器
   pip --version
   npm --version
   go version
   rustc --version
   ```

2. **检查权限**
   - 若需sudo，用`sudo pip install`或`sudo npm install -g`
   - 或用用户目录安装：`pip install --user`、`npm config set prefix ~/.local`

3. **查看错误日志**
   - 大多数LSP server在启动时会输出详细日志
   - 可在终端直接运行`<lsp-server-command>`查看错误

4. **查找替代方案**
   - 若一个LSP server不工作，可尝试其他实现
   - 例如：Python有pyls、pylsp、pyright等多种选择

**使用方法**：

```bash
jlsp document_symbols src/main.rs --language rust
jlsp def-name src/main.rs MyStruct --language rust
```

**注意**：`--language`参数为必填项，所有命令必指定。

## 总结

**核心原则**：

1. 优先用基于符号名之命令，避精确列号
2. 先了解文件结构，再进行符号查询
3. 结合诊断与修复建议，提升代码质量
4. 利用守护进程复用，优化性能

**适用场景**：

- 代码理解与分析
- 符号导航与定位
- 代码质量检查
- 代码修复与重构

**不适用场景**：

- 简单之文本搜索（应用rg、grep）
- 非代码文件之查询
- 不支持LSP之编程语言
