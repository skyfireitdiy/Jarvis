---
name: fix_tool_parse_pattern
description: 当需要分析工具调用解析失败数据或补充解析模式时触发。每当用户提及"解析失败"、"工具调用解析"、"补充解析模式"、"优化解析器"时触发。不触发：添加新工具；工具功能开发；非解析相关的工具问题。
---

# 工具调用解析模式补充规范

## 规则简介

本规范用于指导如何基于真实错误数据，为 `_extract_tool_calls` 补充新的解析模式，提升工具调用的解析成功率。

## 第一步：读取错误数据

错误数据保存在 `~/.jarvis/tool_parse_errors/` 目录下（可通过 `JARVIS_DATA_DIR` 环境变量覆盖）。

**文件命名格式**：`{YYYYMMDD_HHMMSS}_{model_name}.json`

**文件内容结构**：

```json
{
  "timestamp": "2025-01-15_143022",
  "model": "gpt-4o",
  "error_msg": "解析失败的原因描述",
  "content": "LLM原始输出文本（已脱敏）"
}
```

**读取方法**：

```bash
# 查看所有错误文件
ls -lt ~/.jarvis/tool_parse_errors/

# 查看最近的错误
cat ~/.jarvis/tool_parse_errors/$(ls -t ~/.jarvis/tool_parse_errors/ | head -1)

# 按模型筛选
grep -l "model_name" ~/.jarvis/tool_parse_errors/*.json
```

## 第二步：分析模式

阅读错误数据中的 `content` 字段，识别LLM输出中工具调用的格式模式：

1. **关注点**：
   - 工具名称和参数的包裹方式（JSON、XML、markdown代码块等）
   - 工具名称的标识方式（前缀、标记、标签等）
   - 参数的键值对格式
   - 多个工具调用的分隔方式

2. **与现有解析器对比**，确认是否为新模式：
   - `_parse_tool_call_format`：`<tool_call>tool_name {json}` 格式
   - `_parse_special_marker_format`：特殊标记格式
   - `_parse_function_call_format`：函数调用格式
   - `_parse_tool_name_json_format`：工具名+JSON格式
   - `_parse_xml_tag_format`：XML标签格式
   - `_parse_xml_parameter_format`：XML参数格式
   - `_parse_tool_calls_xml_format`：tool_calls XML格式
   - `_parse_arg_key_value_format`：参数键值对格式
   - `_parse_code_block_format`：markdown代码块格式
   - `_parse_embedded_json_format`：嵌入JSON格式
   - `_fuzzy_extract_tool_json`：宽松模糊提取
   - `_try_llm_fix`：LLM修复兜底

3. **模式分类**：
   - 如果是现有解析器的边界情况（如JSON格式微变），优先修改现有解析器
   - 如果是全新的格式模式，需要新增解析器

## 第三步：补充解析器

### 修改位置

文件：`src/jarvis/jarvis_tools/registry.py`

- **新增解析方法**：在 `_extract_tool_calls` 内部类区域（约929-1400行），添加新的 `@staticmethod` 解析方法
- **注册解析器**：在 `_extract_tool_calls` 主方法中（约1482行起），按优先级插入调用

### 解析方法模板

```python
@staticmethod
def _parse_xxx_format(content: str) -> list:
    """解析XXX格式的工具调用。

    格式示例：
        <格式描述>

    Args:
        content: LLM输出的原始文本

    Returns:
        解析出的工具调用列表，每项为 (tool_name, arguments_dict) 元组
    """
    ret = []
    # 使用正则或字符串操作提取工具调用
    # pattern = r'...'
    # matches = re.findall(pattern, content)
    # for match in matches:
    #     tool_name = match[0]
    #     arguments = json.loads(match[1])  # 或手动解析
    #     ret.append((tool_name, arguments))
    return ret
```

### 注册解析器

在 `_extract_tool_calls` 主方法中，按优先级顺序添加：

```python
# 在现有解析器调用序列中适当位置插入
ret.extend(ToolRegistry._parse_xxx_format(content))
if ret:
    return ret
```

### 设计原则

1. **最小匹配**：正则模式应尽量精确，避免误匹配非工具调用的文本
2. **宽松容错**：对参数格式适度宽容（如允许单引号、尾随逗号等）
3. **独立可测**：每个解析器是独立的静态方法，可单独测试
4. **优先级合理**：越精确的模式优先级越高，模糊匹配放后面
5. **不破坏现有**：新增解析器不应影响已有解析器的匹配结果

## 第四步：验证与清理

1. **单元测试**：用错误数据中的 `content` 构造测试用例
2. **回归测试**：确保现有解析器仍正常工作
3. **静态扫描**：`python -m py_compile src/jarvis/jarvis_tools/registry.py`
4. **删除已处理的错误记录**：验证解析器能正确处理该模式后，**必须删除**对应的错误数据文件，避免重复处理

   ```bash
   # 删除已成功处理的错误记录
   rm ~/.jarvis/tool_parse_errors/<filename>.json
   ```

   删除标准：新增或修改的解析器能成功解析该错误记录中的 `content` 字段，提取出正确的工具调用

## 注意事项

- 解析器顺序很重要：精确匹配在前，模糊匹配在后
- `existing` 参数用于避免重复提取，部分解析器接收此参数
- 脱敏处理已在 `_save_parse_error` 中完成，错误数据中不含敏感信息
- 如果新模式仅特定模型使用，在解析方法注释中标注模型名称
- 错误记录处理完成后必须删除，保持错误目录仅包含未解决的问题
