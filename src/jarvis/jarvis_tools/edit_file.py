# -*- coding: utf-8 -*-
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class EditFileTool:
    """文件编辑工具，用于对文件进行局部修改"""

    name = "edit_file"
    description = "对文件进行局部修改。支持sed命令模式（正则表达式）和结构化编辑（通过块id），可指定行号范围限制。\n\n    💡 推荐使用结构化编辑（structured模式）：\n    1. 先使用read_code工具获取文件的结构化块id\n    2. 通过块id进行精确的代码块操作（删除、插入、替换）\n    3. 避免手动计算行号，减少错误风险"

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要修改的文件路径（支持绝对路径和相对路径）",
            },
            "diffs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["sed"],
                                    "description": "sed命令模式：使用类sed命令进行编辑，支持正则表达式替换、删除、追加、插入等",
                                },
                                "command": {
                                    "type": "string",
                                    "description": "sed命令，支持：s/pattern/replacement/flags（替换）、d（删除）、a\\text（追加）、i\\text（插入）、c\\text（替换整行）。可指定行号范围，如：10,20s/old/new/g 或 /pattern/s/old/new/",
                                },
                            },
                            "required": ["type", "command"],
                        },
                        {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["structured"],
                                    "description": "结构化编辑模式：通过块id进行编辑，支持删除块、在块前插入、在块后插入、替换块",
                                },
                                "block_id": {
                                    "type": "string",
                                    "description": "要操作的块id（从read_code工具获取的结构化块id）",
                                },
                                "action": {
                                    "type": "string",
                                    "enum": ["delete", "insert_before", "insert_after", "replace"],
                                    "description": "操作类型：delete（删除块）、insert_before（在块前插入）、insert_after（在块后插入）、replace（替换块）",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "新内容（对于insert_before、insert_after、replace操作必需，delete操作不需要）",
                                },
                                "raw_mode": {
                                    "type": "boolean",
                                    "description": "原始模式：false（默认，使用语法单元模式或空白行分组模式）、true（使用行号分组模式，每20行一组）。必须与read_code工具读取时使用的raw_mode参数一致，否则无法找到对应的块id",
                                    "default": False,
                                },
                            },
                            "required": ["type", "block_id", "action"],
                        },
                    ],
                },
                "description": "修改操作列表，每个操作包含一个DIFF块",
            },
        },
        "required": ["file_path", "diffs"],
    }

    def __init__(self):
        """初始化文件编辑工具"""
        pass

    @staticmethod
    def _parse_range(range_str: str) -> Optional[Tuple[int, int]]:
        """解析RANGE字符串为行号范围
        
        Args:
            range_str: 格式为 "start-end" 的字符串（1-based, 闭区间）
            
        Returns:
            如果格式有效，返回 (start_line, end_line) 元组；否则返回 None
        """
        if not range_str or not str(range_str).strip():
            return None
        m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(range_str))
        if m:
            return int(m.group(1)), int(m.group(2))
        return None

    @staticmethod
    def _count_occurrences(haystack: str, needle: str) -> int:
        """统计字符串出现次数"""
        if not needle:
            return 0
        return haystack.count(needle)

    @staticmethod
    def _find_all_with_count(haystack: str, needle: str) -> Tuple[int, List[int]]:
        """一次遍历同时返回匹配次数和所有位置
        
        Args:
            haystack: 目标字符串
            needle: 搜索字符串
            
        Returns:
            (匹配次数, 所有匹配位置的索引列表)
        """
        if not needle:
            return 0, []
        count = 0
        positions = []
        start = 0
        while True:
            pos = haystack.find(needle, start)
            if pos == -1:
                break
            count += 1
            positions.append(pos)
            start = pos + 1
        return count, positions

    @staticmethod
    def _find_all_positions(haystack: str, needle: str) -> List[int]:
        """查找所有匹配位置
        
        Args:
            haystack: 目标字符串
            needle: 搜索字符串
            
        Returns:
            所有匹配位置的索引列表
        """
        if not needle:
            return []
        positions = []
        start = 0
        while True:
            pos = haystack.find(needle, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        return positions

    @staticmethod
    def _get_line_number(content: str, position: int) -> int:
        """获取字符位置对应的行号（1-based）"""
        return content[:position].count("\n") + 1

    @staticmethod
    def _get_line_context(content: str, line_num: int, context_lines: int = 2) -> str:
        """获取指定行号周围的上下文
        
        Args:
            content: 文件内容
            line_num: 行号（1-based）
            context_lines: 上下各显示的行数
            
        Returns:
            包含上下文的多行字符串
        """
        lines = content.splitlines()
        if line_num < 1 or line_num > len(lines):
            return ""
        start = max(0, line_num - context_lines - 1)
        end = min(len(lines), line_num + context_lines)
        context = []
        for i in range(start, end):
            prefix = ">>> " if i == line_num - 1 else "    "
            context.append(f"{prefix}{i+1:4d}: {lines[i]}")
        return "\n".join(context)

    @staticmethod
    def _detect_indent_style(content: str, search_text: str) -> Optional[int]:
        """检测文件中的缩进风格
        
        Args:
            content: 文件内容
            search_text: 要匹配的搜索文本（用于定位上下文）
            
        Returns:
            检测到的缩进空格数，如果无法检测则返回 None
        """
        # 尝试在文件中找到搜索文本的上下文
        pos = content.find(search_text)
        if pos == -1:
            return None
        
        # 获取匹配位置所在行的缩进
        line_start = content.rfind("\n", 0, pos) + 1
        line_content = content[line_start:pos]
        
        # 计算前导空格数
        indent = 0
        for char in line_content:
            if char == " ":
                indent += 1
            elif char == "\t":
                # 制表符通常等于4个空格
                indent += 4
            else:
                break
        
        return indent if indent > 0 else None

    @staticmethod
    def _apply_indent(text: str, indent_spaces: int) -> str:
        """为文本应用缩进
        
        Args:
            text: 原始文本
            indent_spaces: 缩进空格数
            
        Returns:
            应用缩进后的文本
        """
        lines = text.split("\n")
        indented_lines = []
        for line in lines:
            if line.strip():  # 非空行添加缩进
                indented_lines.append(" " * indent_spaces + line)
            else:  # 空行保持原样
                indented_lines.append(line)
        return "\n".join(indented_lines)

    @staticmethod
    def _execute_sed_command(content: str, sed_cmd: str) -> str:
        """使用系统sed命令执行编辑
        
        Args:
            content: 文件内容
            sed_cmd: sed命令字符串（如 "s/old/new/g" 或 "10,20d"）
            
        Returns:
            执行sed命令后的内容
            
        Raises:
            ValueError: 如果sed命令执行失败
        """
        try:
            # 直接使用subprocess执行sed命令，通过stdin传递内容
            result = subprocess.run(
                ['sed', '-e', sed_cmd],
                input=content,
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=False,
                timeout=30  # 30秒超时
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "sed命令执行失败"
                raise ValueError(f"sed命令执行失败: {error_msg}")
            
            return result.stdout
            
        except FileNotFoundError:
            raise ValueError("系统中未找到sed命令，请确保已安装sed")
        except subprocess.TimeoutExpired:
            raise ValueError("sed命令执行超时（超过30秒）")
        except Exception as e:
            raise ValueError(f"sed命令执行出错: {str(e)}")

    @staticmethod
    def _validate_basic_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证基本参数
        
        Returns:
            如果验证失败，返回错误响应；否则返回None
        """
        file_path = args.get("file_path")
        diffs = args.get("diffs", [])

        if not file_path:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：file_path",
            }

        if not diffs:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：diffs",
            }

        if not isinstance(diffs, list):
            return {
                "success": False,
                "stdout": "",
                "stderr": "diffs参数必须是数组类型",
            }
        
        return None

    @staticmethod
    def _find_block_by_id(filepath: str, block_id: str, raw_mode: bool = False) -> Optional[Dict[str, Any]]:
        """根据块id定位代码块
        
        Args:
            filepath: 文件路径
            block_id: 块id
            raw_mode: 原始模式，False（语法单元或空白行分组）、True（行号分组）
            
        Returns:
            如果找到，返回包含 start_line, end_line, content 的字典；否则返回 None
        """
        try:
            from jarvis.jarvis_code_agent.code_analyzer.structured_code import StructuredCodeExtractor
            return StructuredCodeExtractor.find_block_by_id(filepath, block_id, raw_mode)
        except Exception:
            return None

    @staticmethod
    def _validate_structured(diff: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换structured类型的diff
        
        Returns:
            (错误响应或None, patch字典或None)
        """
        block_id = diff.get("block_id")
        action = diff.get("action")
        content = diff.get("content")
        
        if block_id is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少block_id参数",
            }, None)
        if not isinstance(block_id, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的block_id参数必须是字符串",
            }, None)
        if not block_id.strip():
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的block_id参数不能为空",
            }, None)
        
        if action is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少action参数",
            }, None)
        if not isinstance(action, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的action参数必须是字符串",
            }, None)
        if action not in ["delete", "insert_before", "insert_after", "replace"]:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的action参数必须是 delete、insert_before、insert_after 或 replace 之一",
            }, None)
        
        # 对于非delete操作，content是必需的
        if action != "delete":
            if content is None:
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的action为 {action}，需要提供content参数",
                }, None)
            if not isinstance(content, str):
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的content参数必须是字符串",
                }, None)
        
        # 验证raw_mode参数
        raw_mode = diff.get("raw_mode", False)  # 默认为False
        if not isinstance(raw_mode, bool):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的raw_mode参数必须是布尔值",
            }, None)
        
        patch = {
            "STRUCTURED_BLOCK_ID": block_id,
            "STRUCTURED_ACTION": action,
            "STRUCTURED_RAW_MODE": raw_mode,
        }
        if content is not None:
            patch["STRUCTURED_CONTENT"] = content
        return (None, patch)

    @staticmethod
    def _validate_sed(diff: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换sed类型的diff
        
        Returns:
            (错误响应或None, patch字典或None)
        """
        command = diff.get("command")
        
        if command is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少command参数",
            }, None)
        if not isinstance(command, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的command参数必须是字符串",
            }, None)
        if not command.strip():
            return ({
                "success": False,
                "stdout": "",
                "stderr": (
                    f"第 {idx+1} 个diff的command参数为空或只包含空白字符。"
                    f"command参数不能为空。"
                ),
            }, None)
        
        patch = {
            "SED_COMMAND": command,
        }
        return (None, patch)

    @staticmethod
    def _convert_diffs_to_patches(diffs: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]]]:
        """验证并转换diffs为内部patches格式
        
        Returns:
            (错误响应或None, patches列表)
        """
        patches = []
        for idx, diff in enumerate(diffs):
            if not isinstance(diff, dict):
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff必须是字典类型",
                }, [])
            
            diff_type = diff.get("type")
            error_response = None
            patch = None
            
            if diff_type == "sed":
                error_response, patch = EditFileTool._validate_sed(diff, idx + 1)
            elif diff_type == "structured":
                error_response, patch = EditFileTool._validate_structured(diff, idx + 1)
            else:
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"第 {idx+1} 个diff的类型不支持: {diff_type}。"
                        f"支持的类型: sed、structured"
                    ),
                }, [])
            
            if error_response:
                return (error_response, [])
            
            if patch:
                patches.append(patch)
        
        return (None, patches)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文件编辑操作"""
        try:
            # 验证基本参数
            error_response = EditFileTool._validate_basic_args(args)
            if error_response:
                return error_response
            
            file_path = args.get("file_path")
            diffs = args.get("diffs", [])

            # 转换diffs为patches
            error_response, patches = EditFileTool._convert_diffs_to_patches(diffs)
            if error_response:
                return error_response

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch", group="tool")
            except Exception:
                pass

            # 执行编辑
            success, result = self._fast_edit(file_path, patches)

            if success:
                return {
                    "success": True,
                    "stdout": f"文件 {file_path} 修改成功",
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result,
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}

    @staticmethod
    def _read_file_with_backup(file_path: str) -> Tuple[str, Optional[str]]:
        """读取文件并创建备份
        
        Args:
            file_path: 文件路径
            
        Returns:
            (文件内容, 备份文件路径或None)
        """
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        file_content = ""
        backup_path = None
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            # 创建备份文件
            backup_path = abs_path + ".bak"
            try:
                shutil.copy2(abs_path, backup_path)
            except Exception:
                # 备份失败不影响主流程
                backup_path = None
        
        return file_content, backup_path

    @staticmethod
    def _order_patches_by_range(patches: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """按行号范围对补丁进行排序（从后往前，避免行号变化影响）
        
        Args:
            patches: 补丁列表
            
        Returns:
            排序后的补丁列表
        """
        sed_items: List[Tuple[int, int, int, Dict[str, str]]] = []
        range_items: List[Tuple[int, int, int, Dict[str, str]]] = []
        non_range_items: List[Tuple[int, Dict[str, str]]] = []
        
        for idx, p in enumerate(patches):
            if "SED_COMMAND" in p:
                # sed命令补丁：尝试从命令中提取行号范围（简单匹配）
                sed_cmd = p.get("SED_COMMAND", "")
                range_match = re.match(r'^(\d+)(?:,(\d+))?', sed_cmd)
                if range_match:
                    start_line = int(range_match.group(1))
                    end_line = int(range_match.group(2)) if range_match.group(2) else start_line
                    sed_items.append((start_line, end_line, idx, p))
                else:
                    non_range_items.append((idx, p))
            else:
                # 处理RANGE补丁
                r = p.get("RANGE")
                range_tuple = EditFileTool._parse_range(str(r)) if r else None
                if range_tuple:
                    start_line, end_line = range_tuple
                    range_items.append((start_line, end_line, idx, p))
                else:
                    non_range_items.append((idx, p))
        
        # 按行号从后往前排序
        sed_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        range_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        
        return (
            [item[3] for item in sed_items] +
            [item[3] for item in range_items] +
            [item[1] for item in non_range_items]
        )

    @staticmethod
    def _extract_range_content(
        content: str, 
        range_tuple: Optional[Tuple[int, int]]
    ) -> Tuple[bool, str, str, str, Optional[str]]:
        """提取RANGE范围内的内容
        
        Args:
            content: 文件内容
            range_tuple: 行号范围 (start_line, end_line) 或 None
            
        Returns:
            (是否成功, prefix, base_content, suffix, 错误信息)
        """
        if not range_tuple:
            return (True, "", content, "", None)
        
        start_line, end_line = range_tuple
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        
        if (
            start_line < 1
            or end_line < 1
            or start_line > end_line
            or start_line > total_lines
        ):
            error_msg = (
                f"RANGE行号无效（文件共有{total_lines}行，请求范围: {start_line}-{end_line}）。\n"
                f"注意：如果这是多个补丁中的后续补丁，前面的补丁可能已经改变了文件行数。\n"
                f"建议：使用read_code工具重新读取文件获取最新行号，或使用structured模式。"
            )
            return (False, "", "", "", error_msg)
        
        end_line = min(end_line, total_lines)
        prefix = "".join(lines[: start_line - 1])
        base_content = "".join(lines[start_line - 1 : end_line])
        suffix = "".join(lines[end_line:])
        
        return (True, prefix, base_content, suffix, None)

    @staticmethod
    def _apply_search_replace(
        base_content: str,
        search_text: str,
        replace_text: str,
        range_tuple: Optional[Tuple[int, int]],
        modified_content: str,
        patch: Dict[str, str]
    ) -> Tuple[bool, str, Optional[str]]:
        """应用search替换
        
        Args:
            base_content: 要搜索的内容（可能是RANGE范围内的内容）
            search_text: 搜索文本
            replace_text: 替换文本
            range_tuple: RANGE范围或None
            modified_content: 完整文件内容（用于获取上下文）
            patch: 补丁字典（用于错误信息）
            
        Returns:
            (是否成功, 替换后的base_content, 错误信息)
        """
        # 1) 精确匹配，要求唯一
        exact_search = search_text
        cnt = EditFileTool._count_occurrences(base_content, exact_search)
        
        if cnt == 1:
            return (True, base_content.replace(exact_search, replace_text, 1), None)
        elif cnt > 1:
            # 多匹配错误
            positions = EditFileTool._find_all_positions(base_content, exact_search)
            line_numbers = [EditFileTool._get_line_number(base_content, pos) for pos in positions]
            range_info = f"（RANGE: {patch.get('RANGE', '无')}）" if range_tuple else ""
            
            context_count = min(3, cnt)
            match_details = []
            for i in range(context_count):
                line_num = line_numbers[i]
                context = EditFileTool._get_line_context(modified_content, line_num, 2)
                if context:
                    match_details.append(f"匹配 {i+1} (第{line_num}行):\n{context}")
            
            error_details = [
                f"SEARCH 在指定范围内出现 {cnt} 次，要求唯一匹配{range_info}。",
                f"匹配位置行号: {', '.join(map(str, line_numbers[:10]))}" + 
                (f" 等共{cnt}处" if cnt > 10 else ""),
            ]
            
            if match_details:
                error_details.append("\n匹配位置的上下文:\n" + "\n---\n".join(match_details))
                if cnt > context_count:
                    error_details.append(f"\n... 还有 {cnt - context_count} 个匹配")
            
            suggestions = [
                "1. 使用更具体的SEARCH文本，包含更多上下文（如前后的代码行）",
            ]
            if range_tuple:
                suggestions.append(f"2. 检查RANGE是否正确（当前RANGE: {range_tuple[0]}-{range_tuple[1]}）")
            else:
                suggestions.append("2. 使用RANGE参数限制搜索范围到目标位置")
            suggestions.append("3. 使用structured模式，通过块id进行精确编辑")
            
            error_details.append("\n建议的修正方法：\n" + "\n".join(suggestions))
            error_msg = "\n".join(error_details)
            return (False, base_content, error_msg)
        
        # 2) 若首尾均为换行，尝试去掉首尾换行后匹配
        if (
            search_text.startswith("\n")
            and search_text.endswith("\n")
            and replace_text.startswith("\n")
            and replace_text.endswith("\n")
        ):
            stripped_search = search_text[1:-1]
            stripped_replace = replace_text[1:-1]
            cnt2 = EditFileTool._count_occurrences(base_content, stripped_search)
            if cnt2 == 1:
                return (True, base_content.replace(stripped_search, stripped_replace, 1), None)
            elif cnt2 > 1:
                positions = EditFileTool._find_all_positions(base_content, stripped_search)
                line_numbers = [EditFileTool._get_line_number(base_content, pos) for pos in positions]
                error_msg = (
                    f"SEARCH 在指定范围内出现多次（去掉首尾换行后），要求唯一匹配。"
                    f"匹配次数: {cnt2}，行号: {', '.join(map(str, line_numbers[:10]))}"
                )
                return (False, base_content, error_msg)
        
        # 3) 尝试缩进适配
        current_search = search_text
        current_replace = replace_text
        if (
            current_search.startswith("\n")
            and current_search.endswith("\n")
            and current_replace.startswith("\n")
            and current_replace.endswith("\n")
        ):
            current_search = current_search[1:-1]
            current_replace = current_replace[1:-1]
        
        detected_indent = EditFileTool._detect_indent_style(modified_content, search_text)
        indent_candidates = []
        if detected_indent and 1 <= detected_indent <= 16:
            indent_candidates.append(detected_indent)
        for space_count in range(1, 17):
            if space_count not in indent_candidates:
                indent_candidates.append(space_count)
        
        for space_count in indent_candidates:
            indented_search = EditFileTool._apply_indent(current_search, space_count)
            indented_replace = EditFileTool._apply_indent(current_replace, space_count)
            cnt3, positions3 = EditFileTool._find_all_with_count(base_content, indented_search)
            
            if cnt3 == 1:
                # 验证匹配位置是否在RANGE范围内
                pos = positions3[0]
                if range_tuple:
                    start_line, end_line = range_tuple
                    match_line = EditFileTool._get_line_number(base_content, pos)
                    if not (start_line <= match_line <= end_line):
                        continue
                
                return (True, base_content.replace(indented_search, indented_replace, 1), None)
            elif cnt3 > 1:
                positions = EditFileTool._find_all_positions(base_content, indented_search)
                line_numbers = [EditFileTool._get_line_number(base_content, pos) for pos in positions]
                error_msg = (
                    f"SEARCH 在指定范围内出现多次（缩进适配后，缩进: {space_count}空格），"
                    f"要求唯一匹配。匹配次数: {cnt3}，行号: {', '.join(map(str, line_numbers[:10]))}\n"
                    f"注意：缩进适配可能匹配到错误的实例。\n"
                    f"建议：提供包含正确缩进的SEARCH文本，或使用structured模式。"
                )
                return (False, base_content, error_msg)
        
        # 未找到匹配
        error_msg_parts = [
            "未找到唯一匹配的SEARCH。",
            f"搜索内容预览: {repr(search_text[:100])}..."
            if len(search_text) > 100 else f"搜索内容: {repr(search_text)}",
            "",
            "建议的修正方法：",
            "1. 检查SEARCH文本是否完全匹配文件中的内容（包括缩进、换行符、空格）",
            "2. 使用read_code工具读取文件，确认要修改的内容",
            "3. 使用structured模式，通过块id进行精确编辑",
            "4. 使用RANGE参数限制搜索范围",
        ]
        error_msg = "\n".join(error_msg_parts)
        return (False, base_content, error_msg)

    @staticmethod
    def _apply_structured_edit(
        filepath: str,
        content: str,
        block_id: str,
        action: str,
        new_content: Optional[str],
        raw_mode: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """应用结构化编辑
        
        Args:
            filepath: 文件路径
            content: 文件内容
            block_id: 块id
            action: 操作类型（delete, insert_before, insert_after, replace）
            new_content: 新内容（对于非delete操作）
            raw_mode: 原始模式，False（语法单元或空白行分组）、True（行号分组）
            
        Returns:
            (是否成功, 修改后的内容, 错误信息)
        """
        # 定位块
        block_info = EditFileTool._find_block_by_id(filepath, block_id, raw_mode)
        if not block_info:
            mode_desc = "行号分组模式" if raw_mode else "语法单元/空白行分组模式"
            return (False, content, f"未找到块id: {block_id}（{mode_desc}）。请使用read_code工具查看文件的结构化块id，并确保raw_mode参数与读取时使用的模式一致。")
        
        start_line = block_info['start_line']
        end_line = block_info['end_line']
        # block_content = block_info['content']
        
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        
        # 验证行号范围
        if start_line < 1 or end_line < 1 or start_line > total_lines or end_line > total_lines or start_line > end_line:
            return (False, content, f"块的行号范围无效: {start_line}-{end_line}（文件总行数: {total_lines}）")
        
        # 计算行索引（0-based）
        # end_line是包含的，所以end_idx应该是end_line（0-based，不包含，即end_line行之后）
        start_idx = start_line - 1
        end_idx = end_line  # end_line是包含的，所以end_idx应该是end_line（0-based，不包含）
        
        # 根据操作类型执行编辑
        if action == "delete":
            # 删除块：移除从start_line到end_line的所有行（包含）
            new_lines = lines[:start_idx] + lines[end_idx:]
            result_content = ''.join(new_lines)
            return (True, result_content, None)
        
        elif action == "insert_before":
            # 在块前插入
            if new_content is None:
                return (False, content, "insert_before操作需要提供content参数")
            # 确保新内容以换行符结尾
            insert_content = new_content
            if not insert_content.endswith('\n'):
                insert_content += '\n'
            new_lines = lines[:start_idx] + [insert_content] + lines[start_idx:]
            result_content = ''.join(new_lines)
            return (True, result_content, None)
        
        elif action == "insert_after":
            # 在块后插入
            if new_content is None:
                return (False, content, "insert_after操作需要提供content参数")
            # 确保新内容以换行符结尾
            insert_content = new_content
            if not insert_content.endswith('\n'):
                insert_content += '\n'
            new_lines = lines[:end_idx] + [insert_content] + lines[end_idx:]
            result_content = ''.join(new_lines)
            return (True, result_content, None)
        
        elif action == "replace":
            # 替换块
            if new_content is None:
                return (False, content, "replace操作需要提供content参数")
            # 保持原有的换行符风格
            replace_content = new_content
            # 检查原块最后一行是否有换行符
            if end_idx > 0 and end_idx <= len(lines):
                # 原块的最后一行是 lines[end_idx - 1]
                if lines[end_idx - 1].endswith('\n'):
                    if not replace_content.endswith('\n'):
                        replace_content += '\n'
            new_lines = lines[:start_idx] + [replace_content] + lines[end_idx:]
            result_content = ''.join(new_lines)
            return (True, result_content, None)
        
        else:
            return (False, content, f"不支持的操作类型: {action}")

    @staticmethod
    def _format_patch_description(patch: Dict[str, str]) -> str:
        """格式化补丁描述用于错误信息
        
        Args:
            patch: 补丁字典
            
        Returns:
            补丁描述字符串
        """
        if "SED_COMMAND" in patch:
            return f"sed命令: {patch.get('SED_COMMAND', '')[:100]}..."
        elif "STRUCTURED_BLOCK_ID" in patch:
            block_id = patch.get('STRUCTURED_BLOCK_ID', '')
            action = patch.get('STRUCTURED_ACTION', '')
            content = patch.get('STRUCTURED_CONTENT', '')
            if content:
                content_preview = content[:100] + "..." if len(content) > 100 else content
                return f"结构化编辑: block_id={block_id}, action={action}, content={content_preview}"
            else:
                return f"结构化编辑: block_id={block_id}, action={action}"
        else:
            return "未知的补丁格式"

    @staticmethod
    def _generate_error_summary(
        abs_path: str,
        failed_patches: List[Dict[str, Any]],
        patch_count: int,
        successful_patches: int
    ) -> str:
        """生成错误摘要
        
        Args:
            abs_path: 文件绝对路径
            failed_patches: 失败的补丁列表
            patch_count: 总补丁数
            successful_patches: 成功的补丁数
            
        Returns:
            错误摘要字符串
        """
        error_details = []
        for p in failed_patches:
            patch = p["patch"]
            patch_desc = EditFileTool._format_patch_description(patch)
            error_details.append(f"  - 失败的补丁: {patch_desc}\n    错误: {p['error']}")
        
        if successful_patches == 0:
            summary = (
                f"文件 {abs_path} 修改失败（全部失败，文件未修改）。\n"
                f"失败: {len(failed_patches)}/{patch_count}.\n"
                f"失败详情:\n" + "\n".join(error_details)
            )
        else:
            summary = (
                f"文件 {abs_path} 修改部分成功。\n"
                f"成功: {successful_patches}/{patch_count}, "
                f"失败: {len(failed_patches)}/{patch_count}.\n"
                f"失败详情:\n" + "\n".join(error_details)
            )
        return summary

    @staticmethod
    def _write_file_with_rollback(
        abs_path: str,
        content: str,
        backup_path: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """写入文件，失败时回滚
        
        Args:
            abs_path: 文件绝对路径
            content: 要写入的内容
            backup_path: 备份文件路径或None
            
        Returns:
            (是否成功, 错误信息或None)
        """
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return (True, None)
        except Exception as write_error:
            # 写入失败，尝试回滚
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, abs_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            error_msg = f"文件写入失败: {str(write_error)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return (False, error_msg)

    @staticmethod
    def _fast_edit(file_path: str, patches: List[Dict[str, str]]) -> Tuple[bool, str]:
        """快速应用补丁到文件

        该方法直接尝试将补丁应用到目标文件，适用于简单、明确的修改场景。
        特点：
        1. 支持sed命令模式和结构化编辑模式
        2. 如果部分补丁失败，会继续应用剩余补丁，并报告失败信息
        3. 支持备份和回滚机制

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含 SED_COMMAND 或 STRUCTURED_BLOCK_ID

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否所有补丁都成功应用，
                第二个元素为结果信息，全部成功时为修改后的文件内容，部分或全部失败时为错误信息
        """
        abs_path = os.path.abspath(file_path)
        backup_path = None
        
        try:
            # 读取文件并创建备份
            file_content, backup_path = EditFileTool._read_file_with_backup(file_path)
            modified_content = file_content
            
            # 对补丁进行排序
            ordered_patches = EditFileTool._order_patches_by_range(patches)
            patch_count = len(ordered_patches)
            failed_patches: List[Dict[str, Any]] = []
            successful_patches = 0
            
            # 应用所有补丁
            for patch in ordered_patches:
                found = False
                
                # sed命令模式
                if "SED_COMMAND" in patch:
                    sed_cmd = patch.get("SED_COMMAND", "")
                    try:
                        modified_content = EditFileTool._execute_sed_command(modified_content, sed_cmd)
                        found = True
                        successful_patches += 1
                    except ValueError as e:
                        error_msg = (
                            f"sed命令执行失败: {str(e)}\n"
                            f"命令: {sed_cmd}\n"
                            f"建议：检查命令格式是否正确，参考sed命令文档"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                    except Exception as e:
                        error_msg = (
                            f"sed命令执行出错: {str(e)}\n"
                            f"命令: {sed_cmd}"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                    continue
                
                # 结构化编辑模式
                if "STRUCTURED_BLOCK_ID" in patch:
                    block_id = patch.get("STRUCTURED_BLOCK_ID", "")
                    action = patch.get("STRUCTURED_ACTION", "")
                    new_content = patch.get("STRUCTURED_CONTENT")
                    raw_mode = patch.get("STRUCTURED_RAW_MODE", False)  # 默认为False
                    try:
                        success, new_modified_content, error_msg = EditFileTool._apply_structured_edit(
                            abs_path, modified_content, block_id, action, new_content, raw_mode
                        )
                        if success:
                            modified_content = new_modified_content
                            found = True
                            successful_patches += 1
                        else:
                            failed_patches.append({"patch": patch, "error": error_msg})
                    except Exception as e:
                        error_msg = (
                            f"结构化编辑执行出错: {str(e)}\n"
                            f"block_id: {block_id}, action: {action}"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                    continue
                
                # 如果不支持的模式，记录错误
                error_msg = f"不支持的补丁格式。支持的格式: SED_COMMAND、STRUCTURED_BLOCK_ID"
                failed_patches.append({"patch": patch, "error": error_msg})
            
            # 如果有失败的补丁，且没有成功的补丁，则不写入文件
            if failed_patches and successful_patches == 0:
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                summary = EditFileTool._generate_error_summary(
                    abs_path, failed_patches, patch_count, successful_patches
                )
                PrettyOutput.print(summary, OutputType.ERROR)
                return False, summary
            
            # 写入文件
            success, error_msg = EditFileTool._write_file_with_rollback(abs_path, modified_content, backup_path)
            if not success:
                return False, error_msg
            
            # 写入成功，删除备份文件
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
            
            # 如果有失败的补丁，返回部分成功信息
            if failed_patches:
                summary = EditFileTool._generate_error_summary(
                    abs_path, failed_patches, patch_count, successful_patches
                )
                PrettyOutput.print(summary, OutputType.ERROR)
                return False, summary
            
            return True, modified_content
            
        except Exception as e:
            # 发生异常时，尝试回滚
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, abs_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            error_msg = f"文件修改失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return False, error_msg

