# textDocument/hover 功能规范

## 功能概述

实现 LSP `textDocument/hover` 功能，用于获取指定位置符号的悬停信息（注释、类型、参数说明、文档字符串等）。此功能为 LLM 补充代码的语义信息，避免 LLM 解析原始代码。

### 使用场景

- LLM 需要理解某个符号的类型、用途、参数信息时
- 代码审查时快速查看符号的文档
- 重构时了解函数/类的签名和行为

## 接口定义

### 数据结构

```python
@dataclass
class HoverInfo:
    """符号悬停信息

    包含符号的注释、类型、参数说明、文档字符串等语义信息。

    Attributes:
        contents: 悬停内容（Markdown 或纯文本格式）
        range: 符号的位置范围（可选）
        file_path: 文件路径
        line: 符号所在行号（0-based）
        character: 符号所在列号（0-based）
    """

    contents: str
    range: Optional[tuple[int, int, int, int]]  # (start_line, start_char, end_line, end_char)
    file_path: str
    line: int
    character: int
```

### 函数签名

```python
# LSPClient.hover()
async def hover(
    self,
    file_path: str,
    line: int,
    character: int
) -> Optional[HoverInfo]
```

### CLI 命令

```bash
jlsp hover <file_path> <line> <character> [--language <lang>] [--json]
```

## 输入输出说明

### 输入参数

- `file_path`: 目标文件路径（必需）
  - 类型：字符串
  - 约束：必须是存在的文件路径

- `line`: 行号（必需）
  - 类型：整数
  - 约束：0-based，非负数
  - 范围：0 到文件总行数

- `character`: 列号（必需）
  - 类型：整数
  - 约束：0-based，非负数
  - 范围：0 到该行字符数

- `--language`: 语言（可选）
  - 类型：字符串
  - 默认值：根据文件扩展名自动检测
  - 示例：python, rust, javascript

- `--json`: JSON 格式输出（可选）
  - 类型：布尔值
  - 默认值：False

### 返回值

**成功时返回 HoverInfo：**

- `contents`: 悬停内容字符串（包含 Markdown 格式的文档）
- `range`: 符号位置范围（可选）
- `file_path`: 文件路径
- `line`: 符号所在行号
- `character`: 符号所在列号

**符号未找到时返回 None：**

- 如果指定位置没有可悬停的符号

### 异常说明

- `RuntimeError`: LSP 服务器未启动或响应超时
- `FileNotFoundError`: 文件不存在
- `ValueError`: 行号或列号超出范围

## 功能行为

### 正常情况

1. **函数悬停**
   - 输入：`jlsp hover src/test.py 10 5`
   - 输出：显示函数签名、参数说明、文档字符串
   - 示例：
     ```python
     ```python
     def calculate_sum(a: int, b: int) -> int:
         """计算两个整数的和

         Args:
             a: 第一个整数
             b: 第二个整数

         Returns:
             两个整数的和
         """
     ```
     ```

2. **类悬停**
   - 输入：`jlsp hover src/test.py 5 8`
   - 输出：显示类文档、继承关系、方法列表

3. **变量悬停**
   - 输入：`jlsp hover src/test.py 15 3`
   - 输出：显示变量类型、初始值

### 边界条件

1. **文件第一行**
   - 行号 0，列号 0
   - 正常处理

2. **文件最后一行**
   - 行号为文件行数减1
   - 正常处理

3. **空行**
   - 返回 None（无悬停信息）

4. **注释行**
   - 返回 None（无悬停信息）

### 异常情况

1. **文件不存在**
   - 抛出 FileNotFoundError
   - 显示友好的错误消息

2. **行号超出范围**
   - 抛出 ValueError
   - 显示文件实际行数

3. **列号超出范围**
   - 抛出 ValueError
   - 显示该行实际字符数

4. **LSP 服务器不支持 hover**
   - 抛出 RuntimeError
   - 显示友好错误消息

5. **位置无符号**
   - 返回 None
   - 不抛出异常

## 实现步骤

### 第一步：定义数据结构

在 `protocol.py` 中添加 `HoverInfo` 数据类。

### 第二步：实现客户端

在 `client.py` 中实现 `hover()` 方法：
1. 发送 `textDocument/hover` 请求
2. 解析 LSP 响应
3. 返回 `HoverInfo` 对象

### 第三步：实现守护进程

在 `daemon.py` 中实现 `hover()` 方法：
1. 添加路由处理
2. 调用客户端的 `hover()` 方法
3. 返回 JSON 格式的响应

### 第四步：实现守护进程客户端

在 `daemon_client.py` 中实现 `hover()` 方法：
1. 通过 Unix socket 发送请求
2. 解析响应
3. 返回 `HoverInfo` 对象

### 第五步：实现 CLI 命令

在 `cli.py` 中添加 `hover` 命令：
1. 添加命令参数定义
2. 实现命令逻辑
3. 添加格式化函数（人类可读和 JSON）

## 验收标准

### 功能验收

1. ✅ 能正确获取函数的悬停信息（签名、参数、文档）
2. ✅ 能正确获取类的悬停信息（文档、方法）
3. ✅ 能正确获取变量的悬停信息（类型）
4. ✅ 能正确处理无符号的位置（返回 None）
5. ✅ 能正确处理文件不存在的错误
6. ✅ 能正确处理行号列号超出范围的错误
7. ✅ 能正确输出人类可读格式
8. ✅ 能正确输出 JSON 格式

### 代码质量验收

9. ✅ mypy strict 检查通过
10. ✅ ruff 检查通过

### 文档验收

11. ✅ CLI 命令有完整的帮助文档
12. ✅ 代码有清晰的注释

## 测试用例

### 基本功能测试

```bash
# 测试函数悬停
jlsp hover src/jarvis/jarvis_lsp/cli.py 14 10 --language python

# 测试类悬停
jlsp hover src/jarvis/jarvis_lsp/client.py 1 10 --language python

# 测试变量悬停
jlsp hover src/jarvis/jarvis_lsp/client.py 50 5 --language python

# 测试 JSON 输出
jlsp hover src/jarvis/jarvis_lsp/cli.py 14 10 --language python --json
```

### 边界条件测试

```bash
# 测试文件第一行
jlsp hover src/jarvis/jarvis_lsp/cli.py 0 0 --language python

# 测试空位置
jlsp hover src/jarvis/jarvis_lsp/cli.py 999 0 --language python
```

### 错误处理测试

```bash
# 测试文件不存在
jlsp hover nonexistent.py 10 5 --language python

# 测试行号超出范围
jlsp hover src/jarvis/jarvis_lsp/cli.py 99999 0 --language python
```

## 风险评估

### 技术风险

- **LSP 服务器差异**：不同 LSP 服务器返回的 hover 信息格式可能不同
  - 缓解措施：测试 pylsp、rust-analyzer 等主流服务器

- **Markdown 解析**：contents 字段可能包含复杂的 Markdown 格式
  - 缓解措施：原样返回 Markdown，由客户端渲染

### 兼容性风险

- ** pylsp 不支持 hover**：某些版本的 pylsp 可能不支持 hover
  - 缓解措施：显示友好的错误消息

## 参考资料

- [LSP Specification - textDocument/hover](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_hover)
- [pylsp 文档](https://github.com/python-lsp/python-lsp-server)
