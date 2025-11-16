# -*- coding: utf-8 -*-
"""jarvis_utils.jsonnet_compat 模块单元测试"""

import pytest

from jarvis.jarvis_utils.jsonnet_compat import (
    _fix_jsonnet_multiline_strings,
    _strip_markdown_code_blocks,
    loads,
    dumps,
)


class TestStripMarkdownCodeBlocks:
    """测试 _strip_markdown_code_blocks 函数"""

    def test_strip_json_code_block(self):
        """测试去除 ```json 代码块标记"""
        input_str = """```json
{
  "key": "value"
}
```"""
        result = _strip_markdown_code_blocks(input_str)
        assert "```" not in result
        assert '"key"' in result
        assert '"value"' in result

    def test_strip_json5_code_block(self):
        """测试去除 ```json5 代码块标记"""
        input_str = """```json5
{
  "key": "value" // 注释
}
```"""
        result = _strip_markdown_code_blocks(input_str)
        assert "```" not in result
        assert '"key"' in result

    def test_strip_plain_code_block(self):
        """测试去除 ``` 代码块标记（无语言标识）"""
        input_str = """```
{
  "key": "value"
}
```"""
        result = _strip_markdown_code_blocks(input_str)
        assert "```" not in result
        assert '"key"' in result

    def test_strip_code_block_with_whitespace(self):
        """测试去除代码块标记（前后有空白）"""
        input_str = """  ```json
{
  "key": "value"
}
```  """
        result = _strip_markdown_code_blocks(input_str)
        assert "```" not in result
        assert '"key"' in result

    def test_no_code_block(self):
        """测试没有代码块标记的情况"""
        input_str = '{"key": "value"}'
        result = _strip_markdown_code_blocks(input_str)
        assert result == input_str

    def test_empty_string(self):
        """测试空字符串"""
        result = _strip_markdown_code_blocks("")
        assert result == ""

    def test_non_string_input(self):
        """测试非字符串输入"""
        result = _strip_markdown_code_blocks(123)
        assert result == 123

    def test_code_block_with_backticks_in_content(self):
        """测试代码块内容中包含反引号的情况"""
        input_str = """```json
{
  "text": "包含 `反引号` 的内容"
}
```"""
        result = _strip_markdown_code_blocks(input_str)
        assert "```" not in result
        assert "`反引号`" in result


class TestFixJsonnetMultilineStrings:
    """测试 _fix_jsonnet_multiline_strings 函数"""

    def test_fix_no_indent_first_line(self):
        """测试修复第一行没有缩进的情况"""
        input_str = """{
  "text": |||
第一行没有缩进
第二行也没有
|||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 第一行应该有缩进
        assert " 第一行没有缩进" in result or "第一行没有缩进" not in result.split("\n")[2]
        # 应该能解析成功
        parsed = loads(result)
        assert "text" in parsed

    def test_fix_all_lines_no_indent(self):
        """测试修复所有行都没有缩进的情况"""
        input_str = """{
  "text": |||
第一行
第二行
第三行
|||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 所有行都应该有缩进
        lines = result.split("\n")
        text_start_idx = None
        for i, line in enumerate(lines):
            if "|||" in line and text_start_idx is None:
                text_start_idx = i + 1
                break
        if text_start_idx:
            # 检查后续行（直到下一个 |||）
            for i in range(text_start_idx, len(lines)):
                if "|||" in lines[i]:
                    break
                if lines[i].strip():
                    assert lines[i].startswith(" "), f"行 {i} 应该有缩进: {repr(lines[i])}"

    def test_preserve_existing_indent(self):
        """测试保持已有缩进的情况"""
        input_str = """{
  "text": |||
    第一行有缩进
    第二行也有
  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 应该保持原样
        assert "    第一行有缩进" in result
        assert "    第二行也有" in result

    def test_mixed_indent(self):
        """测试混合缩进的情况（会被统一为第一行的缩进级别）"""
        input_str = """{
  "text": |||
第一行没有
    第二行有4个空格
第三行没有
  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 所有行都会被统一为第一行的缩进级别（1个空格，因为第一行没有缩进）
        # 没有缩进的行应该被修复
        assert " 第一行没有" in result or "第一行没有" not in result.split("\n")[2]
        # 已有缩进的行会被统一为第一行的缩进级别（去除原有缩进，添加统一缩进）
        assert " 第二行有4个空格" in result

    def test_empty_multiline_string(self):
        """测试空的多行字符串"""
        input_str = """{
  "text": |||
|||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 空内容应该保持不变
        assert "|||" in result

    def test_multiple_multiline_strings(self):
        """测试多个多行字符串"""
        input_str = """{
  "text1": |||
第一行
|||,
  "text2": |||
第二行
|||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 两个多行字符串都应该被修复
        assert " 第一行" in result or "第一行" not in result.split("\n")[2]
        assert " 第二行" in result or "第二行" not in result.split("\n")[5]

    def test_multiline_string_with_tabs(self):
        """测试使用制表符缩进的情况（制表符会被转换为空格，统一缩进）"""
        input_str = """{
  "text": |||
\t第一行有制表符
第二行没有
|||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 制表符会被转换为空格，所有行统一为第一行的缩进级别
        # 第一行有制表符，会被转换为空格（通常是4个或8个，但这里统一为1个空格）
        # 没有缩进的行应该被修复
        assert " 第一行有制表符" in result or "第一行有制表符" in result.replace("\t", " ")
        assert " 第二行没有" in result or "第二行没有" not in result.split("\n")[3]

    def test_first_line_with_indent_others_without(self):
        """测试第一行有缩进，后续行没有缩进的情况（包含空行）"""
        input_str = """{
  "text": |||
     带缩进的第一行

没有缩进的第二行

没有缩进的第三行
  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 第一行有6个空格的缩进，后续行应该被统一为相同的缩进级别
        # 空行应该被保留（不需要缩进）
        assert "     带缩进的第一行" in result
        assert "     没有缩进的第二行" in result
        assert "     没有缩进的第三行" in result
        # 验证可以解析
        parsed = loads(input_str)
        assert "text" in parsed
        assert "带缩进的第一行" in parsed["text"]
        assert "没有缩进的第二行" in parsed["text"]
        assert "没有缩进的第三行" in parsed["text"]

    def test_first_line_with_indent_others_without_no_empty_lines(self):
        """测试第一行有缩进，后续行没有缩进的情况（无空行，类似 \"    第一行\\n第二行\\n第三行\"）"""
        input_str = """{
  "text": |||
    第一行
第二行
第三行
  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 第一行有4个空格的缩进，后续行应该被统一为相同的缩进级别
        assert "    第一行" in result
        assert "    第二行" in result
        assert "    第三行" in result
        # 验证可以解析
        parsed = loads(input_str)
        assert "text" in parsed
        # 解析后的文本内容应该包含所有行，用 \n 分隔
        text = parsed["text"]
        assert "第一行" in text
        assert "第二行" in text
        assert "第三行" in text
        # 验证行数（应该包含换行符）
        lines = text.split("\n")
        assert len([l for l in lines if l.strip()]) >= 3  # 至少3个非空行

    def test_first_line_with_indent_mixed_with_indented_lines(self):
        """测试第一行有缩进，部分后续行也有缩进（不同级别）的情况"""
        input_str = """{
  "text": |||
    第一行有4个空格
  第二行有2个空格
第三行没有
    第四行有4个空格
  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 修复后的内容应该统一缩进（以满足 jsonnet 的要求）
        assert "    第一行有4个空格" in result
        assert "    第二行有2个空格" in result  # 修复后会统一为4个空格
        assert "    第三行没有" in result
        assert "    第四行有4个空格" in result
        # 验证可以解析，并且解析后应该恢复原始缩进
        parsed = loads(input_str)
        assert "text" in parsed
        text = parsed["text"]
        # 验证每行的原始缩进被保留
        lines = text.split('\n')
        assert "    第一行有4个空格" in lines[0]  # 4个空格
        assert "  第二行有2个空格" in lines[1]  # 2个空格
        assert "第三行没有" in lines[2]  # 没有缩进
        assert "    第四行有4个空格" in lines[3]  # 4个空格

    def test_multiline_string_with_indented_end_marker(self):
        """测试 ||| 多行字符串的结束标记有缩进的情况（应该自动修复）"""
        input_str = """{
  "text": |||
    第一行
    第二行
     |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 结束标记应该被修复为没有缩进
        assert "\n|||" in result or result.endswith("|||")
        assert "     |||" not in result  # 不应该有缩进的结束标记
        # 验证可以解析
        parsed = loads(input_str)
        assert "text" in parsed
        assert "第一行" in parsed["text"]
        assert "第二行" in parsed["text"]

    def test_first_line_empty_then_indented(self):
        """测试第一行是空行，后续行有缩进的情况"""
        input_str = """{
  "text": |||

    第二行有4个空格
第三行没有
  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 第一行是空行，应该跳过，使用第一个非空行的缩进级别
        # 或者使用默认的1个空格
        # 验证可以解析
        parsed = loads(input_str)
        assert "text" in parsed

    def test_all_lines_empty_except_first(self):
        """测试只有第一行有内容，其他都是空行的情况"""
        input_str = """{
  "text": |||
    第一行有4个空格


  |||
}"""
        result, _ = _fix_jsonnet_multiline_strings(input_str)
        # 第一行有缩进，空行应该被保留
        assert "    第一行有4个空格" in result
        # 验证可以解析
        parsed = loads(input_str)
        assert "text" in parsed
        assert "第一行有4个空格" in parsed["text"]


class TestLoads:
    """测试 loads 函数"""

    def test_loads_simple_json(self):
        """测试解析简单 JSON"""
        json_str = '{"key": "value"}'
        result = loads(json_str)
        assert result == {"key": "value"}

    def test_loads_with_trailing_comma(self):
        """测试解析带尾随逗号的 JSON5"""
        json_str = '{"key": "value",}'
        result = loads(json_str)
        assert result == {"key": "value"}

    def test_loads_with_comments(self):
        """测试解析带注释的 JSON5"""
        json_str = """{
  "key": "value", // 这是注释
  "key2": "value2" /* 这也是注释 */
}"""
        result = loads(json_str)
        assert result == {"key": "value", "key2": "value2"}

    def test_loads_with_multiline_string_no_indent(self):
        """测试解析 ||| 多行字符串（没有缩进，应该自动修复）"""
        json_str = """{
  "text": |||
第一行
第二行
|||
}"""
        result = loads(json_str)
        assert "text" in result
        assert "第一行" in result["text"]
        assert "第二行" in result["text"]

    def test_loads_with_multiline_string_with_indent(self):
        """测试解析 ||| 多行字符串（已有缩进）"""
        json_str = """{
  "text": |||
    第一行
    第二行
  |||
}"""
        result = loads(json_str)
        assert "text" in result
        assert "第一行" in result["text"]
        assert "第二行" in result["text"]

    def test_loads_with_markdown_code_block(self):
        """测试解析包含 markdown 代码块标记的 JSON"""
        json_str = """```json
{
  "key": "value"
}
```"""
        result = loads(json_str)
        assert result == {"key": "value"}

    def test_loads_with_markdown_and_multiline_string(self):
        """测试解析包含 markdown 代码块和 ||| 多行字符串的 JSON"""
        json_str = """```json5
{
  "text": |||
第一行
第二行
|||
}
```"""
        result = loads(json_str)
        assert "text" in result
        assert "第一行" in result["text"]
        assert "第二行" in result["text"]

    def test_loads_with_special_characters_in_multiline(self):
        """测试 ||| 多行字符串中包含特殊字符"""
        json_str = """{
  "text": |||
包含 "双引号" 和 '单引号'
包含 \\n 转义字符
|||
}"""
        result = loads(json_str)
        assert "text" in result
        assert '"双引号"' in result["text"] or "双引号" in result["text"]
        assert "'单引号'" in result["text"] or "单引号" in result["text"]

    def test_loads_with_backticks_in_multiline(self):
        """测试 ||| 多行字符串中包含反引号"""
        json_str = """{
  "text": |||
包含 `反引号` 的内容
|||
}"""
        result = loads(json_str)
        assert "text" in result
        assert "`反引号`" in result["text"] or "反引号" in result["text"]

    def test_loads_array(self):
        """测试解析数组"""
        json_str = "[1, 2, 3,]"
        result = loads(json_str)
        assert result == [1, 2, 3]

    def test_loads_nested_objects(self):
        """测试解析嵌套对象"""
        json_str = """{
  "outer": {
    "inner": "value"
  }
}"""
        result = loads(json_str)
        assert result["outer"]["inner"] == "value"

    def test_loads_invalid_json(self):
        """测试解析无效的 JSON（应该抛出异常）"""
        json_str = "{invalid json}"
        with pytest.raises(Exception):
            loads(json_str)

    def test_loads_empty_string(self):
        """测试解析空字符串"""
        with pytest.raises(Exception):
            loads("")

    def test_loads_multiple_multiline_strings(self):
        """测试解析包含多个 ||| 多行字符串的 JSON"""
        json_str = """{
  "text1": |||
第一段
|||,
  "text2": |||
第二段
|||
}"""
        result = loads(json_str)
        assert "text1" in result
        assert "text2" in result
        assert "第一段" in result["text1"]
        assert "第二段" in result["text2"]

    def test_loads_multiline_string_with_empty_lines(self):
        """测试 ||| 多行字符串中包含空行"""
        json_str = """{
  "text": |||
第一行

第三行
|||
}"""
        result = loads(json_str)
        assert "text" in result
        # 空行应该被保留
        lines = result["text"].split("\n")
        assert len(lines) >= 3

    def test_loads_multiline_string_with_only_whitespace_lines(self):
        """测试 ||| 多行字符串中只包含空白行"""
        json_str = """{
  "text": |||
    
|||
}"""
        result = loads(json_str)
        assert "text" in result
        # 空白行应该被处理
        assert isinstance(result["text"], str)


class TestDumps:
    """测试 dumps 函数"""

    def test_dumps_simple_dict(self):
        """测试序列化简单字典"""
        obj = {"key": "value"}
        result = dumps(obj)
        assert '"key"' in result
        assert '"value"' in result

    def test_dumps_with_ensure_ascii(self):
        """测试序列化时使用 ensure_ascii=False"""
        obj = {"中文": "值"}
        result = dumps(obj, ensure_ascii=False)
        assert "中文" in result
        assert "值" in result

    def test_dumps_with_indent(self):
        """测试序列化时使用缩进"""
        obj = {"key": "value", "key2": "value2"}
        result = dumps(obj, indent=2)
        assert "\n" in result
        assert "  " in result  # 应该有缩进


class TestIntegration:
    """集成测试：组合功能"""

    def test_markdown_code_block_with_multiline_string_no_indent(self):
        """测试 markdown 代码块 + ||| 多行字符串（没有缩进）"""
        json_str = """```json5
{
  "text": |||
第一行
第二行
|||
}
```"""
        result = loads(json_str)
        assert "text" in result
        assert "第一行" in result["text"]
        assert "第二行" in result["text"]

    def test_complex_jsonnet_with_all_features(self):
        """测试包含所有特性的复杂 Jsonnet"""
        json_str = """```json5
{
  // 这是注释
  "text": |||
第一行没有缩进
第二行也没有
|||,
  "number": 42,
  "array": [1, 2, 3,], // 尾随逗号
  "nested": {
    "key": "value"
  }
}
```"""
        result = loads(json_str)
        assert "text" in result
        assert "number" in result
        assert result["number"] == 42
        assert "array" in result
        assert result["array"] == [1, 2, 3]
        assert "nested" in result

    def test_multiple_multiline_strings_in_markdown(self):
        """测试 markdown 代码块中包含多个 ||| 多行字符串"""
        json_str = """```json
{
  "text1": |||
第一段内容
|||,
  "text2": |||
第二段内容
|||
}
```"""
        result = loads(json_str)
        assert "text1" in result
        assert "text2" in result
        assert "第一段内容" in result["text1"]
        assert "第二段内容" in result["text2"]

    def test_multiline_string_with_mixed_content(self):
        """测试 ||| 多行字符串中包含混合内容（JSON、代码等）"""
        json_str = """{
  "code": |||
function hello() {
  console.log("Hello");
}
|||
}"""
        result = loads(json_str)
        assert "code" in result
        assert "function" in result["code"]
        assert "console.log" in result["code"]

    def test_multiline_string_preserves_formatting(self):
        """测试 ||| 多行字符串统一缩进（混合缩进会被统一为第一行的缩进级别）"""
        json_str = """{
  "text": |||
    第一行有4个空格
  第二行有2个空格
第三行没有
  |||
}"""
        result = loads(json_str)
        assert "text" in result
        # 修复函数会统一所有行的缩进级别为第一行的缩进级别（4个空格）
        # 这样可以确保 jsonnet 能正确解析（jsonnet 要求所有行都有相同的缩进级别）
        text = result["text"]
        assert "第一行" in text
        assert "第二行" in text
        assert "第三行" in text

