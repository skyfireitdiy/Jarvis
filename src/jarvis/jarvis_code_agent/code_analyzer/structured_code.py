# -*- coding: utf-8 -*-
"""结构化代码提取和查找工具

提供从源代码文件中提取结构化单元（函数、类、导入语句等）的功能，
以及根据块id定位代码块的功能。
"""

import os
from typing import Any, Dict, List, Optional, Tuple

# 尝试导入语言支持模块
try:
    from jarvis.jarvis_code_agent.code_analyzer.language_support import (
        detect_language,
        get_symbol_extractor,
        get_dependency_analyzer,
    )
    from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol

    LANGUAGE_SUPPORT_AVAILABLE = True
except ImportError:
    LANGUAGE_SUPPORT_AVAILABLE = False

    def get_dependency_analyzer(language: str):
        return None


class StructuredCodeExtractor:
    """结构化代码提取器

    提供从源代码文件中提取结构化单元的功能，包括：
    - 语法单元（函数、类等）
    - 导入/包含语句
    - 空白行分组
    - 行号分组
    """

    @staticmethod
    def get_full_definition_range(
        symbol: Symbol, content: str, language: Optional[str]
    ) -> Tuple[int, int]:
        """获取完整的定义范围（包括函数体等）

        对于 tree-sitter 提取的符号，可能需要向上查找父节点以获取完整定义。
        对于 Python AST，已经包含完整范围。

        Args:
            symbol: 符号对象
            content: 文件内容
            language: 语言名称

        Returns:
            (start_line, end_line) 元组
        """
        # Python AST 已经包含完整范围（使用 end_lineno）
        if language == "python":
            return symbol.line_start, symbol.line_end

        # 对于 tree-sitter，尝试查找包含函数体的完整定义
        # 由于 tree-sitter 查询可能只捕获声明节点，我们需要查找包含函数体的节点
        # 这里使用一个简单的启发式方法：查找下一个同级别的定义或文件结束

        lines = content.split("\n")
        start_line = symbol.line_start
        end_line = symbol.line_end

        # 如果结束行号看起来不完整（比如只有1-2行），尝试查找函数体结束
        if end_line - start_line < 2:
            # 从结束行开始向下查找，寻找匹配的大括号或缩进变化
            # 这是一个简化的实现，实际可能需要解析语法树
            brace_count = 0
            found_start = False
            for i in range(
                start_line - 1, min(len(lines), start_line + 100)
            ):  # 最多查找100行
                line = lines[i]
                if "{" in line:
                    brace_count += line.count("{")
                    found_start = True
                if found_start and "}" in line:
                    brace_count -= line.count("}")
                    if brace_count == 0:
                        end_line = i + 1
                        break

        # 确保不超过文件末尾和请求的范围
        end_line = min(end_line, len(lines))

        return start_line, end_line

    @staticmethod
    def extract_syntax_units(
        filepath: str, content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """提取语法单元（函数、类等）

        Args:
            filepath: 文件路径
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号

        Returns:
            语法单元列表，每个单元包含 id, start_line, end_line, content
        """
        if not LANGUAGE_SUPPORT_AVAILABLE:
            return []

        try:
            # 检测语言
            language = detect_language(filepath)
            if not language:
                return []

            # 获取符号提取器
            extractor = get_symbol_extractor(language)
            if not extractor:
                return []

            # 提取符号
            symbols = extractor.extract_symbols(filepath, content)
            if not symbols:
                return []

            # 过滤符号：返回与请求范围有重叠的所有语法单元（包括边界上的）
            # 重叠条件：symbol.line_start <= end_line AND symbol.line_end >= start_line
            syntax_kinds = {
                "function",
                "method",
                "class",
                "struct",
                "enum",
                "union",
                "interface",
                "trait",
                "impl",
                "module",
                "attribute",
                "const",
                "static",
                "type",
                "extern",
                "macro",
                "typedef",
                "template",
                "namespace",
                "var",
                "constructor",
                "field",
                "annotation",
                "decorator",
            }
            filtered_symbols = [
                s
                for s in symbols
                if s.kind in syntax_kinds
                and s.line_start <= end_line  # 开始行在范围结束之前或等于
                and s.line_end >= start_line  # 结束行在范围开始之后或等于
            ]

            # 按行号排序（导入语句通常在文件开头，所以会排在最前面）
            filtered_symbols.sort(key=lambda s: s.line_start)

            # 构建语法单元列表（先收集所有单元信息）
            units_info = []
            lines = content.split("\n")

            for symbol in filtered_symbols:
                # 获取完整的定义范围（不截断，返回完整语法单元）
                unit_start, unit_end = (
                    StructuredCodeExtractor.get_full_definition_range(
                        symbol, content, language
                    )
                )

                # 提取该符号的完整内容（不截断到请求范围）
                symbol_start_idx = max(0, unit_start - 1)  # 转为0-based索引
                symbol_end_idx = min(len(lines), unit_end)

                symbol_content = "\n".join(lines[symbol_start_idx:symbol_end_idx])

                # 生成id：体现作用域（如果有parent，使用 parent.name 格式）
                if symbol.parent:
                    unit_id = f"{symbol.parent}.{symbol.name}"
                else:
                    unit_id = symbol.name

                # 如果id重复，加上行号
                if any(u["id"] == unit_id for u in units_info):
                    if symbol.parent:
                        unit_id = f"{symbol.parent}.{symbol.name}_{unit_start}"
                    else:
                        unit_id = f"{symbol.name}_{unit_start}"

                units_info.append(
                    {
                        "id": unit_id,
                        "start_line": unit_start,
                        "end_line": unit_end,
                        "content": symbol_content,
                        "has_parent": symbol.parent is not None,
                    }
                )

            # 处理重叠：如果一个单元完全包含另一个单元，父符号排除被子符号覆盖的行
            # 策略：保留所有符号，但父符号只显示未被子符号覆盖的部分
            units = []
            for unit in units_info:
                # 找出所有被unit包含的子符号
                child_ranges = []
                for other in units_info:
                    if unit == other:
                        continue
                    # 检查other是否完全被unit包含（other是unit的子符号）
                    if (
                        unit["start_line"] <= other["start_line"]
                        and unit["end_line"] >= other["end_line"]
                    ):
                        # 排除范围完全相同的情况（范围相同时不认为是父子关系）
                        if not (
                            unit["start_line"] == other["start_line"]
                            and unit["end_line"] == other["end_line"]
                        ):
                            child_ranges.append(
                                (other["start_line"], other["end_line"])
                            )

                # 如果有子符号，需要排除被子符号覆盖的行
                if child_ranges:
                    # 合并重叠的子符号范围
                    child_ranges.sort()
                    merged_ranges = []
                    for start, end in child_ranges:
                        if merged_ranges and start <= merged_ranges[-1][1] + 1:
                            # 合并重叠或相邻的范围
                            merged_ranges[-1] = (
                                merged_ranges[-1][0],
                                max(merged_ranges[-1][1], end),
                            )
                        else:
                            merged_ranges.append((start, end))

                    # 提取未被覆盖的行
                    unit_lines = unit["content"].split("\n")
                    filtered_lines = []
                    current_line = unit["start_line"]

                    for line in unit_lines:
                        # 检查当前行是否在任何子符号范围内
                        is_covered = any(
                            start <= current_line <= end for start, end in merged_ranges
                        )
                        if not is_covered:
                            filtered_lines.append(line)
                        current_line += 1

                    # 如果还有未被覆盖的行，创建新的单元
                    if filtered_lines:
                        filtered_content = "\n".join(filtered_lines)
                        # 计算新的结束行号（最后一个未被覆盖的行）
                        unit["start_line"] + len(filtered_lines) - 1
                        # 需要调整，因为跳过了被覆盖的行
                        # 重新计算：找到最后一个未被覆盖的实际行号
                        actual_last_line = unit["start_line"]
                        for i, line in enumerate(unit_lines):
                            line_num = unit["start_line"] + i
                            is_covered = any(
                                start <= line_num <= end for start, end in merged_ranges
                            )
                            if not is_covered:
                                actual_last_line = line_num

                        new_unit = {
                            "id": unit["id"],
                            "start_line": unit["start_line"],
                            "end_line": actual_last_line,
                            "content": filtered_content,
                        }
                        units.append(new_unit)
                    # 如果所有行都被覆盖，跳过父符号
                else:
                    # 没有子符号，直接添加
                    unit.pop("has_parent", None)
                    units.append(unit)

            return units
        except Exception:
            # 如果提取失败，返回空列表，将使用行号分组
            return []

    @staticmethod
    def extract_blank_line_groups(
        content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """按空白行分组提取内容

        遇到空白行（除了空格、制表符等，没有任何其他字符的行）时，作为分隔符将代码分成不同的组。

        Args:
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号

        Returns:
            分组列表，每个分组包含 id, start_line, end_line, content
        """
        lines = content.split("\n")
        groups = []

        # 获取实际要处理的行范围
        actual_lines = lines[start_line - 1 : end_line]

        if not actual_lines:
            return groups

        current_start = start_line
        group_start_idx = 0
        i = 0

        while i < len(actual_lines):
            line = actual_lines[i]
            # 空白行定义：除了空格、制表符等，没有任何其他字符的行
            is_blank = not line.strip()

            if is_blank:
                # 空白行作为分隔符，结束当前分组（不包含空白行）
                if group_start_idx < i:
                    group_end_idx = i - 1
                    group_content = "\n".join(
                        actual_lines[group_start_idx : group_end_idx + 1]
                    )
                    if group_content.strip():  # 只添加非空分组
                        group_id = f"{current_start}-{current_start + (group_end_idx - group_start_idx)}"
                        groups.append(
                            {
                                "id": group_id,
                                "start_line": current_start,
                                "end_line": current_start
                                + (group_end_idx - group_start_idx),
                                "content": group_content,
                            }
                        )
                # 跳过空白行，开始新分组
                i += 1
                # 跳过连续的多个空白行
                while i < len(actual_lines) and not actual_lines[i].strip():
                    i += 1
                if i < len(actual_lines):
                    current_start = start_line + i
                    group_start_idx = i
            else:
                # 非空白行，继续当前分组
                i += 1

        # 处理最后一组
        if group_start_idx < len(actual_lines):
            group_end_idx = len(actual_lines) - 1
            group_content = "\n".join(actual_lines[group_start_idx : group_end_idx + 1])
            if group_content.strip():  # 只添加非空分组
                group_id = f"{current_start}-{current_start + (group_end_idx - group_start_idx)}"
                groups.append(
                    {
                        "id": group_id,
                        "start_line": current_start,
                        "end_line": current_start + (group_end_idx - group_start_idx),
                        "content": group_content,
                    }
                )

        # 如果没有找到任何分组（全部是空白行），返回整个范围作为一个分组
        if not groups:
            group_content = "\n".join(actual_lines)
            group_id = f"{start_line}-{end_line}"
            groups.append(
                {
                    "id": group_id,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": group_content,
                }
            )

        return groups

    @staticmethod
    def extract_line_groups(
        content: str, start_line: int, end_line: int, group_size: int = 20
    ) -> List[Dict[str, Any]]:
        """按行号分组提取内容

        Args:
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号
            group_size: 每组行数，默认20行

        Returns:
            分组列表，每个分组包含 id, start_line, end_line, content
        """
        lines = content.split("\n")
        groups = []

        current_start = start_line
        while current_start <= end_line:
            current_end = min(current_start + group_size - 1, end_line)

            # 提取该组的内容（0-based索引）
            group_start_idx = current_start - 1
            group_end_idx = current_end
            group_content = "\n".join(lines[group_start_idx:group_end_idx])

            # 生成id：行号范围
            group_id = f"{current_start}-{current_end}"

            groups.append(
                {
                    "id": group_id,
                    "start_line": current_start,
                    "end_line": current_end,
                    "content": group_content,
                }
            )

            current_start = current_end + 1

        return groups

    @staticmethod
    def ensure_unique_ids(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """确保单元列表中所有id唯一

        Args:
            units: 单元列表

        Returns:
            确保id唯一后的单元列表
        """
        seen_ids = set()
        result = []

        for unit in units:
            original_id = unit["id"]
            unit_id = original_id
            counter = 1

            # 如果id已存在，添加后缀使其唯一
            while unit_id in seen_ids:
                unit_id = f"{original_id}_{counter}"
                counter += 1

            seen_ids.add(unit_id)
            # 创建新单元，使用唯一的id
            new_unit = unit.copy()
            new_unit["id"] = unit_id
            result.append(new_unit)

        return result

    @staticmethod
    def extract_imports(
        filepath: str, content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """提取文件的导入/包含语句作为结构化单元

        Args:
            filepath: 文件路径
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号

        Returns:
            导入语句单元列表，每个单元包含 id, start_line, end_line, content
        """
        if not LANGUAGE_SUPPORT_AVAILABLE:
            return []

        try:
            language = detect_language(filepath)
            if not language:
                return []

            analyzer = get_dependency_analyzer(language)
            if not analyzer:
                return []

            dependencies = analyzer.analyze_imports(filepath, content)
            if not dependencies:
                return []

            # 过滤在请求范围内的导入语句
            lines = content.split("\n")
            import_units = []

            # 按行号分组导入语句（连续的导入语句作为一个单元）
            current_group = []
            for dep in sorted(dependencies, key=lambda d: d.line):
                line_num = dep.line
                # 只包含在请求范围内的导入语句
                if start_line <= line_num <= end_line and 1 <= line_num <= len(lines):
                    if not current_group or line_num == current_group[-1]["line"] + 1:
                        # 连续的导入语句，添加到当前组
                        current_group.append(
                            {"line": line_num, "content": lines[line_num - 1]}
                        )
                    else:
                        # 不连续，先处理当前组
                        if current_group:
                            import_units.append(
                                StructuredCodeExtractor.create_import_unit(
                                    current_group
                                )
                            )
                        # 开始新组
                        current_group = [
                            {"line": line_num, "content": lines[line_num - 1]}
                        ]

            # 处理最后一组
            if current_group:
                import_units.append(
                    StructuredCodeExtractor.create_import_unit(current_group)
                )

            return import_units
        except Exception:
            return []

    @staticmethod
    def create_import_unit(import_group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建导入语句单元

        Args:
            import_group: 导入语句组（连续的导入语句）

        Returns:
            导入单元字典
        """
        start_line = import_group[0]["line"]
        end_line = import_group[-1]["line"]
        content = "\n".join(item["content"] for item in import_group)

        # 生成id：根据导入语句内容生成唯一标识
        import_group[0]["content"].strip()
        if len(import_group) == 1:
            unit_id = f"import_{start_line}"
        else:
            unit_id = f"imports_{start_line}_{end_line}"

        return {
            "id": unit_id,
            "start_line": start_line,
            "end_line": end_line,
            "content": content,
        }

    @staticmethod
    def find_block_by_id(
        filepath: str, block_id: str, raw_mode: bool = False
    ) -> Optional[Dict[str, Any]]:
        """根据块id定位代码块

        Args:
            filepath: 文件路径
            block_id: 块id
            raw_mode: 原始模式，False（默认，先尝试语法单元，找不到则尝试空白行分组）、True（行号分组模式，每20行一组）

        Returns:
            如果找到，返回包含 start_line, end_line, content 的字典；否则返回 None
        """
        try:
            # 读取文件内容
            abs_path = os.path.abspath(filepath)
            if not os.path.exists(abs_path):
                return None

            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            total_lines = len(content.split("\n"))

            if raw_mode:
                # 行号分组模式（raw_mode=true）
                line_groups = StructuredCodeExtractor.extract_line_groups(
                    content, 1, total_lines, group_size=20
                )
                for group in line_groups:
                    if group["id"] == block_id:
                        return {
                            "start_line": group["start_line"],
                            "end_line": group["end_line"],
                            "content": group["content"],
                        }
            else:
                # raw_mode=False: 先尝试语法单元和导入单元，如果找不到再尝试空白行分组
                # 语法单元模式：先尝试提取语法单元和导入单元
                syntax_units = StructuredCodeExtractor.extract_syntax_units(
                    abs_path, content, 1, total_lines
                )
                import_units = StructuredCodeExtractor.extract_imports(
                    abs_path, content, 1, total_lines
                )

                # 合并并确保id唯一
                all_units = import_units + syntax_units
                all_units = StructuredCodeExtractor.ensure_unique_ids(all_units)

                # 查找匹配的块
                for unit in all_units:
                    if unit["id"] == block_id:
                        return {
                            "start_line": unit["start_line"],
                            "end_line": unit["end_line"],
                            "content": unit["content"],
                        }

                # 如果语法单元模式没找到，尝试空白行分组模式
                blank_line_groups = StructuredCodeExtractor.extract_blank_line_groups(
                    content, 1, total_lines
                )
                for group in blank_line_groups:
                    if group["id"] == block_id:
                        return {
                            "start_line": group["start_line"],
                            "end_line": group["end_line"],
                            "content": group["content"],
                        }

            # 如果没找到，返回None
            return None

        except Exception:
            return None
