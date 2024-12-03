---
name: file_tool_encoding_consistency
description: 规范 edit_file 与 read_code 的文件编码处理一致性，仅支持 utf-8 和 gbk，并按平台使用不同优先级。
---

# 文件工具编码一致性规范

## 功能概述

修复 `edit_file` 与 `read_code` 在读取同一文本文件时使用不同编码或不同解码错误策略导致的内容不一致问题，减少 search/replace 替换失败。

使用场景：

- 用户先通过 `read_code` 查看代码，再用 `edit_file` 提交 search/replace 修改。
- 文件可能是 UTF-8 或 GBK 编码。
- 需要在 Windows 与非 Windows 环境下提供稳定、一致、可预期的编码优先级。

## 接口定义

### EditFileNormalTool 内部编码辅助接口

```python
def _get_preferred_encodings() -> List[str]

def _read_text_with_preferred_encoding(
    file_path: str,
) -> Tuple[str, Optional[str]]
```

### ReadCodeTool 内部编码辅助接口

```python
def _get_preferred_encodings(self) -> List[str]

def _read_text_with_preferred_encoding(self, file_path: str) -> str
```

上述接口为工具内部辅助接口，不改变对外工具参数结构。

## 输入输出说明

### 输入

- `file_path`: 要读取或写入的文本文件路径。

### 输出

- `edit_file` 读取阶段返回：
  - 文件文本内容
  - 备份文件路径（若存在）
  - 已确认的文件编码（`utf-8` / `gbk` / `None`）
- `read_code` 读取阶段返回：
  - 供展示与上下文分析使用的文本内容

### 异常与错误

- 若文件不存在，按原有工具逻辑返回错误。
- 若文件无法按 `utf-8` 和 `gbk` 解码：
  - `edit_file` 与 `read_code` 允许回退到 `read_text_file()` 的现有逻辑，以避免无意义中断。
  - 但对常见 UTF-8 / GBK 文件，必须优先走本规范定义的确定性路径。

## 功能行为

### 编码支持范围

- 工具侧优先支持且重点保证：`utf-8`、`gbk`
- 不在工具侧继续扩展新的编码分支

### 平台优先级

- 非 Windows：优先 `utf-8`，其次 `gbk`
- Windows：优先 `gbk`，其次 `utf-8`

### 读取行为

1. 工具读取文件时，先按平台优先级顺序尝试显式解码。
2. 一旦某个编码成功解码，即将该编码视为本次处理的确认编码。
3. 对同一文件：
   - `edit_file` 的匹配文本必须来自确认编码解码结果。
   - `read_code` 的展示文本必须尽量与 `edit_file` 使用同一策略。
4. 不应使用 `errors="ignore"` 作为主路径读取策略，因为它会吞掉字节并改变文本结构，导致匹配失败。

### 写入行为

1. `edit_file` 写回文件时，优先使用读取阶段确认的编码。
2. 若本次是新文件且无确认编码：
   - Windows 默认 `gbk`
   - 非 Windows 默认 `utf-8`
3. 写入时不得再次优先重新探测编码，以避免编码漂移。

### 边界条件

- 空文件：
  - 读取结果为空字符串
  - 新写入时使用平台默认优先编码
- 新文件：
  - 无备份文件时允许正常写入
- 仅包含 ASCII 的文件：
  - 可被两种编码兼容解码时，按平台优先级确定

### 异常处理

- 如果显式优先编码尝试均失败，可回退到现有公共读取函数的默认逻辑。
- 如果写入失败，必须沿用现有回滚机制恢复备份。

## 验收标准

1. 在非 Windows 环境下，`edit_file` 读取 UTF-8 文件时优先使用 `utf-8`。
2. 在 Windows 环境下，`edit_file` 读取 GBK 文件时优先使用 `gbk`。
3. `edit_file` 对同一文件的读取、匹配、写回使用同一确认编码。
4. `read_code` 读取同一 UTF-8 / GBK 文件时，结果与 `edit_file` 的解码策略保持一致。
5. 不再使用 `errors="ignore"` 作为 `read_code` 主读取路径。
6. 不修改 `src/jarvis/jarvis_utils/config.py`。
7. 不改变 `edit_file` 与 `read_code` 的对外参数接口。
8. 对 UTF-8 与 GBK 示例文件，最小读取与替换验证可以通过。
