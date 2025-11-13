# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.config import get_patch_format


class EditFileTool:
    """文件编辑工具，用于对文件进行局部修改"""

    name = "edit_file"
    description = "对文件进行局部修改。支持行号替换（推荐，最准确）、单点替换（精确匹配）、区间替换（标记之间）和sed命令模式（正则表达式），可指定行号范围限制。"

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
                                    "enum": ["line_replace"],
                                    "description": "行号替换模式（推荐）：直接指定行号范围进行替换，最准确且不受格式影响",
                                },
                                "line_start": {
                                    "type": "integer",
                                    "description": "起始行号（1-based，包含）",
                                },
                                "line_end": {
                                    "type": "integer",
                                    "description": "结束行号（1-based，包含）",
                                },
                                "new_content": {
                                    "type": "string",
                                    "description": "替换后的新内容",
                                },
                            },
                            "required": ["type", "line_start", "line_end", "new_content"],
                        },
                        {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["search"],
                                    "description": "单点替换模式：通过搜索文本进行替换",
                                },
                                "range": {
                                    "type": "string",
                                    "description": "可选的行号范围，格式：start-end（1-based，闭区间）",
                                },
                                "search": {
                                    "type": "string",
                                    "description": "要搜索的原始代码",
                                },
                                "replace": {
                                    "type": "string",
                                    "description": "替换后的新代码",
                                },
                            },
                            "required": ["type", "search", "replace"],
                        },
                        {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["search_range"],
                                    "description": "区间替换模式：通过起始和结束标记进行替换",
                                },
                                "range": {
                                    "type": "string",
                                    "description": "可选的行号范围，格式：start-end（1-based，闭区间）",
                                },
                                "search_start": {
                                    "type": "string",
                                    "description": "起始标记",
                                },
                                "search_end": {
                                    "type": "string",
                                    "description": "结束标记",
                                },
                                "replace": {
                                    "type": "string",
                                    "description": "替换内容",
                                },
                            },
                            "required": ["type", "search_start", "search_end", "replace"],
                        },
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
    def _validate_line_replace(diff: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换line_replace类型的diff
        
        Returns:
            (错误响应或None, patch字典或None)
        """
        line_start = diff.get("line_start")
        line_end = diff.get("line_end")
        new_content = diff.get("new_content")
        
        if line_start is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少line_start参数",
            }, None)
        if line_end is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少line_end参数",
            }, None)
        if not isinstance(line_start, int) or not isinstance(line_end, int):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的line_start和line_end必须是整数",
            }, None)
        if line_start < 1 or line_end < 1:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的行号必须大于0（行号从1开始）",
            }, None)
        if line_start > line_end:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的line_start({line_start})不能大于line_end({line_end})",
            }, None)
        if new_content is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少new_content参数",
            }, None)
        if not isinstance(new_content, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的new_content必须是字符串",
            }, None)
        
        patch = {
            "LINE_START": line_start,
            "LINE_END": line_end,
            "NEW_CONTENT": new_content,
        }
        return (None, patch)

    @staticmethod
    def _validate_search(diff: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换search类型的diff
        
        Returns:
            (错误响应或None, patch字典或None)
        """
        search = diff.get("search")
        replace = diff.get("replace")
        
        if search is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少search参数",
            }, None)
        if not isinstance(search, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的search参数必须是字符串",
            }, None)
        if not search.strip():
            return ({
                "success": False,
                "stdout": "",
                "stderr": (
                    f"第 {idx+1} 个diff的search参数为空或只包含空白字符。"
                    f"search参数不能为空，请提供要搜索的文本。"
                ),
            }, None)
        if replace is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少replace参数",
            }, None)
        if not isinstance(replace, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的replace参数必须是字符串",
            }, None)
        
        patch = {
            "SEARCH": search,
            "REPLACE": replace,
        }
        if "range" in diff:
            patch["RANGE"] = diff["range"]
        return (None, patch)

    @staticmethod
    def _validate_search_range(diff: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换search_range类型的diff
        
        Returns:
            (错误响应或None, patch字典或None)
        """
        search_start = diff.get("search_start")
        search_end = diff.get("search_end")
        replace = diff.get("replace")
        
        if search_start is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少search_start参数",
            }, None)
        if not isinstance(search_start, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的search_start参数必须是字符串",
            }, None)
        if not search_start.strip():
            return ({
                "success": False,
                "stdout": "",
                "stderr": (
                    f"第 {idx+1} 个diff的search_start参数为空或只包含空白字符。"
                    f"search_start参数不能为空。"
                ),
            }, None)
        if search_end is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少search_end参数",
            }, None)
        if not isinstance(search_end, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的search_end参数必须是字符串",
            }, None)
        if not search_end.strip():
            return ({
                "success": False,
                "stdout": "",
                "stderr": (
                    f"第 {idx+1} 个diff的search_end参数为空或只包含空白字符。"
                    f"search_end参数不能为空。"
                ),
            }, None)
        if replace is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少replace参数",
            }, None)
        if not isinstance(replace, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的replace参数必须是字符串",
            }, None)
        
        patch = {
            "SEARCH_START": search_start,
            "SEARCH_END": search_end,
            "REPLACE": replace,
        }
        if "range" in diff:
            patch["RANGE"] = diff["range"]
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
            
            if diff_type == "line_replace":
                error_response, patch = EditFileTool._validate_line_replace(diff, idx + 1)
            elif diff_type == "search":
                error_response, patch = EditFileTool._validate_search(diff, idx + 1)
            elif diff_type == "search_range":
                error_response, patch = EditFileTool._validate_search_range(diff, idx + 1)
            elif diff_type == "sed":
                error_response, patch = EditFileTool._validate_sed(diff, idx + 1)
            else:
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"第 {idx+1} 个diff的类型不支持: {diff_type}。"
                        f"支持的类型: line_replace（推荐）、search、search_range、sed"
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
    def _fast_edit(file_path: str, patches: List[Dict[str, str]]) -> Tuple[bool, str]:
        """快速应用补丁到文件

        该方法直接尝试将补丁应用到目标文件，适用于简单、明确的修改场景。
        特点：
        1. 直接进行字符串替换，效率高
        2. 会自动处理缩进问题，尝试匹配不同缩进级别的代码
        3. 确保搜索文本在文件中唯一匹配
        4. 如果部分补丁失败，会继续应用剩余补丁，并报告失败信息
        5. 支持备份和回滚机制

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含search(搜索文本)和replace(替换文本)

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否所有补丁都成功应用，
                第二个元素为结果信息，全部成功时为修改后的文件内容，部分或全部失败时为错误信息
        """
        backup_path = None
        try:
            # 确保目录存在
            abs_path = os.path.abspath(file_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            # 读取原始文件内容并创建备份
            file_content = ""
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

            # 应用所有补丁
            modified_content = file_content
            patch_count = 0
            failed_patches: List[Dict[str, Any]] = []
            successful_patches = 0

            # 当存在RANGE或LINE时，确保按行号从后往前应用补丁，避免前面补丁影响后续行号
            ordered_patches: List[Dict[str, str]] = []
            line_items: List[Tuple[int, int, int, Dict[str, str]]] = []  # 行号编辑补丁
            sed_items: List[Tuple[int, int, int, Dict[str, str]]] = []  # sed命令补丁（如果有行号范围）
            range_items: List[Tuple[int, int, int, Dict[str, str]]] = []  # RANGE补丁
            non_range_items: List[Tuple[int, Dict[str, str]]] = []  # 无行号限制的补丁
            for idx, p in enumerate(patches):
                # 优先处理行号编辑（LINE_START/LINE_END）
                if "LINE_START" in p and "LINE_END" in p:
                    start_line = p["LINE_START"]
                    end_line = p["LINE_END"]
                    line_items.append((start_line, end_line, idx, p))
                elif "SED_COMMAND" in p:
                    # sed命令补丁：尝试从命令中提取行号范围（简单匹配）
                    # 格式如：10,20s/old/new/g 或 10d
                    sed_cmd = p.get("SED_COMMAND", "")
                    # 尝试匹配行号范围
                    range_match = re.match(r'^(\d+)(?:,(\d+))?', sed_cmd)
                    if range_match:
                        start_line = int(range_match.group(1))
                        end_line = int(range_match.group(2)) if range_match.group(2) else start_line
                        sed_items.append((start_line, end_line, idx, p))
                    else:
                        # sed命令使用模式匹配或没有范围限制，放在最后处理
                        non_range_items.append((idx, p))
                else:
                    # 处理RANGE补丁
                    r = p.get("RANGE")
                    range_tuple = EditFileTool._parse_range(str(r)) if r else None
                    if range_tuple:
                        start_line, end_line = range_tuple
                        range_items.append((start_line, end_line, idx, p))
                    else:
                        # RANGE格式无效或没有RANGE的补丁保持原有顺序
                        non_range_items.append((idx, p))
            # 先应用行号编辑补丁：按start_line、end_line、原始索引逆序
            line_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            # 再应用sed命令补丁（如果有行号范围）：按start_line、end_line、原始索引逆序
            sed_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            # 再应用RANGE补丁：按start_line、end_line、原始索引逆序
            range_items.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            # 最后应用无行号限制的补丁
            ordered_patches = (
                [item[3] for item in line_items] +
                [item[3] for item in sed_items] +
                [item[3] for item in range_items] +
                [item[1] for item in non_range_items]
            )

            patch_count = len(ordered_patches)
            for patch in ordered_patches:
                found = False

                # 行号替换模式（最准确，推荐使用）
                if "LINE_START" in patch and "LINE_END" in patch:
                    line_start = patch["LINE_START"]
                    line_end = patch["LINE_END"]
                    new_content = patch["NEW_CONTENT"]
                    
                    # 获取当前文件的行列表
                    lines = modified_content.splitlines(keepends=True)
                    total_lines = len(lines)
                    
                    # 验证行号有效性
                    if (
                        line_start < 1
                        or line_end < 1
                        or line_start > total_lines
                        or line_start > line_end
                    ):
                        error_msg = (
                            f"行号范围无效（文件共有{total_lines}行，请求范围: {line_start}-{line_end}）。\n"
                            f"注意：如果这是多个补丁中的后续补丁，前面的补丁可能已经改变了文件行数。\n"
                            f"建议：使用read_code工具重新读取文件获取最新行号，或使用search/search_range模式。"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                        continue
                    
                    # 截断end_line不超过总行数
                    line_end = min(line_end, total_lines)
                    
                    # 执行行号替换
                    prefix = "".join(lines[: line_start - 1])
                    suffix = "".join(lines[line_end:])
                    
                    # 处理换行符：如果原文件最后一行有换行符，保持格式
                    if new_content and not new_content.endswith("\n"):
                        # 检查原范围最后一行是否有换行符
                        if line_end <= len(lines) and lines[line_end - 1].endswith("\n"):
                            new_content = new_content + "\n"
                    
                    modified_content = prefix + new_content + suffix
                    found = True
                    successful_patches += 1
                    continue

                # sed命令模式：直接使用系统sed命令
                elif "SED_COMMAND" in patch:
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

                # 处理可选的RANGE范围：格式 "start-end"（1-based, 闭区间）
                scoped = False
                prefix = suffix = ""
                base_content = modified_content
                range_tuple = EditFileTool._parse_range(str(patch.get("RANGE", "")))
                if range_tuple:
                    start_line, end_line = range_tuple

                    # 拆分为三段
                    lines = modified_content.splitlines(keepends=True)
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
                            f"建议：使用read_code工具重新读取文件获取最新行号，或使用line_replace模式（推荐）。"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                        continue
                    # 截断end_line不超过总行数
                    end_line = min(end_line, total_lines)

                    prefix = "".join(lines[: start_line - 1])
                    base_content = "".join(lines[start_line - 1 : end_line])
                    suffix = "".join(lines[end_line:])
                    scoped = True

                # 单点替换
                if "SEARCH" in patch:
                    search_text = patch["SEARCH"]
                    replace_text = patch["REPLACE"]

                    # 精确匹配搜索文本（保留原始换行和空格）
                    exact_search = search_text

                    # 1) 精确匹配，要求唯一
                    cnt = EditFileTool._count_occurrences(base_content, exact_search)
                    if cnt == 1:
                        base_content = base_content.replace(exact_search, replace_text, 1)
                        found = True
                    elif cnt > 1:
                        # 提供更详细的错误信息，包括所有匹配位置的行号和上下文
                        positions = EditFileTool._find_all_positions(base_content, exact_search)
                        line_numbers = [EditFileTool._get_line_number(base_content, pos) for pos in positions]
                        range_info = f"（RANGE: {patch.get('RANGE', '无')}）" if range_tuple else ""
                        
                        # 为前几个匹配提供上下文
                        context_count = min(3, cnt)
                        match_details = []
                        for i in range(context_count):
                            line_num = line_numbers[i]
                            context = EditFileTool._get_line_context(modified_content, line_num, 2)
                            if context:
                                match_details.append(f"匹配 {i+1} (第{line_num}行):\n{context}")
                        
                        # 构建详细的错误信息
                        error_details = [
                            f"SEARCH 在指定范围内出现 {cnt} 次，要求唯一匹配{range_info}。",
                            f"匹配位置行号: {', '.join(map(str, line_numbers[:10]))}" + 
                            (f" 等共{cnt}处" if cnt > 10 else ""),
                        ]
                        
                        if match_details:
                            error_details.append(f"\n匹配位置的上下文:\n" + "\n---\n".join(match_details))
                            if cnt > context_count:
                                error_details.append(f"\n... 还有 {cnt - context_count} 个匹配")
                        
                        # 提供可操作的建议
                        suggestions = [
                            "1. 使用更具体的SEARCH文本，包含更多上下文（如前后的代码行）",
                        ]
                        if range_tuple:
                            suggestions.append(
                                f"2. 检查RANGE是否正确（当前RANGE: {range_tuple[0]}-{range_tuple[1]}）"
                            )
                        else:
                            suggestions.append("2. 使用RANGE参数限制搜索范围到目标位置")
                        suggestions.append("3. 使用search_range模式，通过SEARCH_START和SEARCH_END精确定位")
                        suggestions.append("4. 如果已知行号，使用line_replace模式（推荐，最准确）")
                        
                        error_details.append(f"\n建议的修正方法：\n" + "\n".join(suggestions))
                        error_msg = "\n".join(error_details)
                        failed_patches.append({"patch": patch, "error": error_msg})
                        # 不继续尝试其它变体
                        continue
                    else:
                        # 2) 若首尾均为换行，尝试去掉首尾换行后匹配，要求唯一
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
                                base_content = base_content.replace(
                                    stripped_search, stripped_replace, 1
                                )
                                found = True
                            elif cnt2 > 1:
                                positions = EditFileTool._find_all_positions(base_content, stripped_search)
                                line_numbers = [EditFileTool._get_line_number(base_content, pos) for pos in positions]
                                error_msg = (
                                    f"SEARCH 在指定范围内出现多次（去掉首尾换行后），要求唯一匹配。"
                                    f"匹配次数: {cnt2}，行号: {', '.join(map(str, line_numbers[:10]))}"
                                )
                                failed_patches.append({"patch": patch, "error": error_msg})
                                continue

                        # 3) 尝试缩进适配，先检测文件缩进风格
                        if not found:
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

                            # 先尝试检测到的缩进
                            detected_indent = EditFileTool._detect_indent_style(modified_content, search_text)
                            indent_candidates = []
                            if detected_indent and 1 <= detected_indent <= 16:
                                indent_candidates.append(detected_indent)
                            # 添加其他可能的缩进值
                            for space_count in range(1, 17):
                                if space_count not in indent_candidates:
                                    indent_candidates.append(space_count)

                            for space_count in indent_candidates:
                                indented_search = EditFileTool._apply_indent(current_search, space_count)
                                indented_replace = EditFileTool._apply_indent(current_replace, space_count)
                                cnt3, positions3 = EditFileTool._find_all_with_count(base_content, indented_search)
                                if cnt3 == 1:
                                    # 验证匹配位置是否在RANGE范围内（如果有RANGE）
                                    pos = positions3[0]
                                    if range_tuple:
                                        start_line, end_line = range_tuple
                                        match_line = EditFileTool._get_line_number(base_content, pos)
                                        if not (start_line <= match_line <= end_line):
                                            # 匹配位置不在RANGE内，继续尝试下一个缩进
                                            continue
                                    
                                    base_content = base_content.replace(
                                        indented_search, indented_replace, 1
                                    )
                                    found = True
                                    # 记录使用了缩进适配（可以在日志中提示，但不影响成功）
                                    # 注意：缩进适配成功，但建议LLM使用line_replace模式以获得更高准确性
                                    break
                                elif cnt3 > 1:
                                    positions = EditFileTool._find_all_positions(base_content, indented_search)
                                    line_numbers = [EditFileTool._get_line_number(base_content, pos) for pos in positions]
                                    error_msg = (
                                        f"SEARCH 在指定范围内出现多次（缩进适配后，缩进: {space_count}空格），"
                                        f"要求唯一匹配。匹配次数: {cnt3}，行号: {', '.join(map(str, line_numbers[:10]))}\n"
                                        f"注意：缩进适配可能匹配到错误的实例。\n"
                                        f"建议：使用line_replace模式（推荐）或提供包含正确缩进的SEARCH文本。"
                                    )
                                    failed_patches.append({"patch": patch, "error": error_msg})
                                    # 多匹配直接失败，不再继续尝试其它缩进
                                    found = False
                                    break

                        if not found:
                            # 未找到任何可用的唯一匹配，提供更详细的错误信息
                            error_msg_parts = [
                                f"未找到唯一匹配的SEARCH。",
                                f"搜索内容预览: {repr(search_text[:100])}..."
                                if len(search_text) > 100 else f"搜索内容: {repr(search_text)}",
                                "",
                                "建议的修正方法：",
                                "1. 检查SEARCH文本是否完全匹配文件中的内容（包括缩进、换行符、空格）",
                                "2. 使用read_code工具读取文件，确认要修改的内容",
                                "3. 如果已知行号，使用line_replace模式（推荐，最准确）",
                                "4. 使用search_range模式，通过SEARCH_START和SEARCH_END精确定位",
                                "5. 使用RANGE参数限制搜索范围",
                            ]
                            error_msg = "\n".join(error_msg_parts)
                            failed_patches.append({"patch": patch, "error": error_msg})

                # 区间替换
                elif "SEARCH_START" in patch and "SEARCH_END" in patch:
                    search_start = patch["SEARCH_START"]
                    search_end = patch["SEARCH_END"]
                    replace_text = patch["REPLACE"]

                    # 范围替换（包含边界），命中第一个起始标记及其后的第一个结束标记
                    start_idx = base_content.find(search_start)
                    if start_idx == -1:
                        error_msg = (
                            f"未找到SEARCH_START。"
                            f"搜索内容: {repr(search_start[:50])}..."
                            if len(search_start) > 50 else f"搜索内容: {repr(search_start)}"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                    else:
                        # 从 search_start 之后开始查找 search_end
                        end_idx = base_content.find(search_end, start_idx + len(search_start))
                        if end_idx == -1:
                            start_line = EditFileTool._get_line_number(base_content, start_idx)
                            context = EditFileTool._get_line_context(modified_content, start_line, 2)
                            error_msg = (
                                f"在SEARCH_START之后未找到SEARCH_END。"
                                f"SEARCH_START位置: 第{start_line}行。"
                                f"SEARCH_END内容: {repr(search_end[:50])}..."
                                if len(search_end) > 50 else f"SEARCH_END内容: {repr(search_end)}"
                            )
                            if context:
                                error_msg += f"\nSEARCH_START上下文:\n{context}"
                            failed_patches.append({"patch": patch, "error": error_msg})
                        else:
                            # 将替换范围扩展到整行
                            # 找到 start_idx 所在行的行首
                            line_start_idx = base_content.rfind("\n", 0, start_idx) + 1

                            # 找到 end_idx 所在行的行尾
                            match_end_pos = end_idx + len(search_end)
                            line_end_idx = base_content.find("\n", match_end_pos)

                            if line_end_idx == -1:
                                # 如果没有找到换行符，说明是最后一行
                                end_of_range = len(base_content)
                            else:
                                # 包含换行符
                                end_of_range = line_end_idx + 1

                            final_replace_text = replace_text
                            original_slice = base_content[line_start_idx:end_of_range]

                            # 如果原始片段以换行符结尾，且替换内容不为空且不以换行符结尾，
                            # 则为替换内容添加换行符以保持格式
                            if (
                                final_replace_text
                                and original_slice.endswith("\n")
                                and not final_replace_text.endswith("\n")
                            ):
                                final_replace_text += "\n"

                            base_content = (
                                base_content[:line_start_idx]
                                + final_replace_text
                                + base_content[end_of_range:]
                            )
                            found = True

                else:
                    error_msg = "不支持的补丁格式"
                    failed_patches.append({"patch": patch, "error": error_msg})

                # 若使用了RANGE，则将局部修改写回整体内容
                if found:
                    if scoped:
                        modified_content = prefix + base_content + suffix
                    else:
                        modified_content = base_content
                    successful_patches += 1

            # 如果有失败的补丁，且没有成功的补丁，则不写入文件（保持原文件不变）
            if failed_patches and successful_patches == 0:
                # 全部失败，不修改文件
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                error_details = []
                for p in failed_patches:
                    patch = p["patch"]
                    if "LINE_START" in patch and "LINE_END" in patch:
                        patch_desc = (
                            f"行号替换 (line_replace): "
                            f"行 {patch.get('LINE_START')}-{patch.get('LINE_END')}"
                        )
                    elif "SED_COMMAND" in patch:
                        patch_desc = f"sed命令: {patch.get('SED_COMMAND', '')[:100]}..."
                    elif "SEARCH" in patch:
                        patch_desc = patch["SEARCH"][:200] + "..." if len(patch["SEARCH"]) > 200 else patch["SEARCH"]
                    else:
                        patch_desc = (
                            f"SEARCH_START: {patch.get('SEARCH_START', '')[:100]}...\n"
                            f"SEARCH_END: {patch.get('SEARCH_END', '')[:100]}..."
                        )
                    error_details.append(f"  - 失败的补丁: {patch_desc}\n    错误: {p['error']}")
                summary = (
                    f"文件 {abs_path} 修改失败（全部失败，文件未修改）。\n"
                    f"失败: {len(failed_patches)}/{patch_count}.\n"
                    f"失败详情:\n" + "\n".join(error_details)
                )
                PrettyOutput.print(summary, OutputType.ERROR)
                return False, summary

            # 写入修改后的内容
            try:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)
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
                return False, error_msg

            # 写入成功，删除备份文件
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass

            if failed_patches:
                error_details = []
                for p in failed_patches:
                    patch = p["patch"]
                    if "LINE_START" in patch and "LINE_END" in patch:
                        patch_desc = (
                            f"行号替换 (line_replace): "
                            f"行 {patch.get('LINE_START')}-{patch.get('LINE_END')}"
                        )
                    elif "SED_COMMAND" in patch:
                        patch_desc = f"sed命令: {patch.get('SED_COMMAND', '')[:100]}..."
                    elif "SEARCH" in patch:
                        patch_desc = patch["SEARCH"][:200] + "..." if len(patch["SEARCH"]) > 200 else patch["SEARCH"]
                    else:
                        patch_desc = (
                            f"SEARCH_START: {patch.get('SEARCH_START', '')[:100]}...\n"
                            f"SEARCH_END: {patch.get('SEARCH_END', '')[:100]}..."
                        )
                    error_details.append(f"  - 失败的补丁: {patch_desc}\n    错误: {p['error']}")
                summary = (
                    f"文件 {abs_path} 修改部分成功。\n"
                    f"成功: {successful_patches}/{patch_count}, "
                    f"失败: {len(failed_patches)}/{patch_count}.\n"
                    f"失败详情:\n" + "\n".join(error_details)
                )
                PrettyOutput.print(summary, OutputType.ERROR)
                return False, summary

            return True, modified_content

        except Exception as e:
            # 发生异常时，尝试回滚
            abs_path = os.path.abspath(file_path)
            backup_path = abs_path + ".bak"
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, abs_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            error_msg = f"文件修改失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return False, error_msg

