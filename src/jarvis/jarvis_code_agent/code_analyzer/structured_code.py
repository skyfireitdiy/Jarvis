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

        # 对于 Rust，如果符号开始行是文档注释（以 /// 或 //! 开头），
        # 向上查找实际的函数/结构体定义开始行
        if language == "rust" and start_line > 1:
            # 向上查找，跳过文档注释
            for i in range(start_line - 2, -1, -1):  # 从 start_line - 2 开始向上查找
                line = lines[i] if i < len(lines) else ""
                stripped = line.strip()
                # 如果是文档注释（/// 或 //!），继续向上查找
                if stripped.startswith("///") or stripped.startswith("//!"):
                    start_line = i + 1  # 更新起始行号
                # 如果是空行或普通注释，也继续向上查找
                elif not stripped or stripped.startswith("//"):
                    continue
                else:
                    # 找到非文档注释的行，停止查找
                    break

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
            # 处理end_line为-1的情况（表示文件末尾）
            if end_line == -1:
                lines = content.split("\n")
                end_line = len(lines)
            
            filtered_symbols = [
                s
                for s in symbols
                if s.kind in syntax_kinds
                and s.line_start <= end_line  # 开始行在范围结束之前或等于
                and s.line_end >= start_line  # 结束行在范围开始之后或等于
            ]

            # 按行号排序（导入语句通常在文件开头，所以会排在最前面）
            filtered_symbols.sort(key=lambda s: s.line_start)

            # 返回原始语法单元（不进行切分，切分统一在read_code.py的_merge_and_split_by_points中处理）
            units = []
            lines = content.split("\n")

            for symbol in filtered_symbols:
                # 获取完整的定义范围（不截断，返回完整语法单元）
                unit_start, unit_end = (
                    StructuredCodeExtractor.get_full_definition_range(
                        symbol, content, language
                    )
                )
                
                # 确保在请求范围内
                unit_start = max(unit_start, start_line)
                unit_end = min(unit_end, end_line)

                # 提取该符号的完整内容（不截断到请求范围）
                symbol_start_idx = max(0, unit_start - 1)  # 转为0-based索引
                # unit_end 是包含的（inclusive），所以需要 +1 来包含最后一行
                symbol_end_idx = min(len(lines), unit_end + 1)

                symbol_content = "\n".join(lines[symbol_start_idx:symbol_end_idx])

                # 生成id：体现作用域（如果有parent，使用 parent.name 格式）
                if symbol.parent:
                    unit_id = f"{symbol.parent}.{symbol.name}"
                else:
                    unit_id = symbol.name

                # 重复id处理
                if any(u["id"] == unit_id for u in units):
                    if symbol.parent:
                        unit_id = f"{symbol.parent}.{symbol.name}_{unit_start}"
                    else:
                        unit_id = f"{symbol.name}_{unit_start}"

                units.append({
                    "id": unit_id,
                    "start_line": unit_start,
                    "end_line": unit_end,
                    "content": symbol_content,
                })

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
        # end_line 是包含的（inclusive），所以需要 +1 来包含最后一行
        actual_lines = lines[start_line - 1 : end_line + 1]

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
            # current_end 是包含的（inclusive），所以需要 +1 来包含最后一行
            group_end_idx = current_end + 1
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
