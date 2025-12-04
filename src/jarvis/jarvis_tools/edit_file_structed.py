# -*- coding: utf-8 -*-
"""结构化文件编辑工具（基于块id的结构化编辑）"""

import os
import shutil
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EditErrorType(Enum):
    """编辑错误类型枚举"""

    BLOCK_ID_NOT_FOUND = "block_id_not_found"  # 块id不存在
    CACHE_INVALID = "cache_invalid"  # 缓存无效
    MULTIPLE_MATCHES = "multiple_matches"  # 多处匹配
    SEARCH_NOT_FOUND = "search_not_found"  # 搜索文本未找到
    PARAMETER_MISSING = "parameter_missing"  # 参数缺失
    UNSUPPORTED_ACTION = "unsupported_action"  # 不支持的操作
    OTHER = "other"  # 其他错误


class EditFileTool:
    """文件编辑工具，用于对文件进行结构化编辑（基于块id）"""

    # 为了兼容旧版本，保留类名不变，但工具名称改为 edit_file_structed
    name = "edit_file_structed"
    description = "对文件进行结构化编辑（通过块id），支持同时修改多个文件。\n\n    💡 使用步骤：\n    1. 先使用read_code工具获取文件的结构化块id\n    2. 通过块id进行精确的代码块操作（删除、插入、替换、编辑）\n    3. 避免手动计算行号，减少错误风险\n    4. 可以在一次调用中同时修改多个文件\n\n    📝 支持的操作类型：\n    - delete: 删除块\n    - insert_before: 在块前插入内容\n    - insert_after: 在块后插入内容\n    - replace: 替换整个块\n    - edit: 在块内进行search/replace（需要提供search和replace参数）\n\n    ⚠️ 重要提示：\n    - 不要一次修改太多内容，建议分多次进行，避免超过LLM的上下文窗口大小\n    - 如果修改内容较长（超过2048字符），建议拆分为多个较小的编辑操作\n    - insert_before 和 insert_after 操作是在当前块内部操作，不会修改已存在的块索引：\n      * insert_before: 在块内容的前面插入新内容，插入的内容成为块的一部分\n      * insert_after: 在块内容的后面插入新内容，插入的内容成为块的一部分\n      * 这意味着插入的内容会合并到当前块中，不会创建新的块或改变其他块的索引"

    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
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
                                "properties": {
                                    "block_id": {
                                        "type": "string",
                                        "description": "要操作的块id（从read_code工具获取的结构化块id）",
                                    },
                                    "action": {
                                        "type": "string",
                                        "enum": [
                                            "delete",
                                            "insert_before",
                                            "insert_after",
                                            "replace",
                                            "edit",
                                        ],
                                        "description": "操作类型：delete（删除块）、insert_before（在块前插入）、insert_after（在块后插入）、replace（替换块）、edit（在块内进行search/replace）",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "新内容（对于insert_before、insert_after、replace操作必需，delete和edit操作不需要）",
                                    },
                                    "search": {
                                        "type": "string",
                                        "description": "要搜索的文本（对于edit操作必需）",
                                    },
                                    "replace": {
                                        "type": "string",
                                        "description": "替换后的文本（对于edit操作必需）",
                                    },
                                },
                                "required": ["block_id", "action"],
                            },
                            "description": "修改操作列表，每个操作包含一个结构化编辑块",
                        },
                    },
                    "required": ["file_path", "diffs"],
                },
                "description": "要修改的文件列表，每个文件包含文件路径和对应的编辑操作列表",
            },
        },
        "required": ["files"],
    }

    def __init__(self):
        """初始化文件编辑工具"""
        pass

    @staticmethod
    def _validate_basic_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证基本参数

        Returns:
            如果验证失败，返回错误响应；否则返回None
        """
        files = args.get("files")

        if not files:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：files",
            }

        if not isinstance(files, list):
            return {
                "success": False,
                "stdout": "",
                "stderr": "files参数必须是数组类型",
            }

        if len(files) == 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": "files数组不能为空",
            }

        # 验证每个文件项
        for idx, file_item in enumerate(files):
            if not isinstance(file_item, dict):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项必须是字典类型",
                }

            file_path = file_item.get("file_path")
            diffs = file_item.get("diffs", [])

            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项缺少必需参数：file_path",
                }

            if not diffs:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项缺少必需参数：diffs",
                }

            if not isinstance(diffs, list):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"files数组第 {idx + 1} 项的diffs参数必须是数组类型",
                }

        return None

    @staticmethod
    def _get_file_cache(agent: Any, filepath: str) -> Optional[Dict[str, Any]]:
        """获取文件的缓存信息

        Args:
            agent: Agent实例
            filepath: 文件路径

        Returns:
            缓存信息字典，如果不存在则返回None
        """
        if not agent:
            return None

        cache = agent.get_user_data("read_code_cache")
        if not cache:
            return None

        abs_path = os.path.abspath(filepath)
        return cache.get(abs_path)

    @staticmethod
    def _is_cache_valid(cache_info: Optional[Dict[str, Any]], filepath: str) -> bool:
        """检查缓存是否有效

        Args:
            cache_info: 缓存信息字典
            filepath: 文件路径

        Returns:
            True表示缓存有效，False表示缓存无效
        """
        if not cache_info:
            return False

        try:
            # 检查文件是否存在
            if not os.path.exists(filepath):
                return False

            # 检查文件修改时间是否变化
            current_mtime = os.path.getmtime(filepath)
            cached_mtime = cache_info.get("file_mtime")

            if (
                cached_mtime is None or abs(current_mtime - cached_mtime) > 0.1
            ):  # 允许0.1秒的误差
                return False

            # 检查缓存数据结构是否完整
            if (
                "id_list" not in cache_info
                or "blocks" not in cache_info
                or "total_lines" not in cache_info
            ):
                return False

            return True
        except Exception:
            return False

    @staticmethod
    def _find_block_by_id_in_cache(
        cache_info: Dict[str, Any], block_id: str
    ) -> Optional[Dict[str, Any]]:
        """从缓存中根据块id定位代码块

        Args:
            cache_info: 缓存信息字典
            block_id: 块id

        Returns:
            如果找到，返回包含 content 的字典；否则返回 None
        """
        if not cache_info:
            return None

        # 直接从 blocks 字典中查找
        blocks = cache_info.get("blocks", {})
        block = blocks.get(block_id)
        if block:
            return {
                "content": block.get("content", ""),
            }

        return None

    @staticmethod
    def _update_cache_timestamp(agent: Any, filepath: str) -> None:
        """更新缓存的时间戳

        Args:
            agent: Agent实例
            filepath: 文件路径
        """
        if not agent:
            return

        cache = agent.get_user_data("read_code_cache")
        if not cache:
            return

        abs_path = os.path.abspath(filepath)
        if abs_path in cache:
            cache[abs_path]["read_time"] = time.time()
            # 更新文件修改时间
            try:
                if os.path.exists(abs_path):
                    cache[abs_path]["file_mtime"] = os.path.getmtime(abs_path)
            except Exception:
                pass
            agent.set_user_data("read_code_cache", cache)

    @staticmethod
    def _validate_structured(
        diff: Dict[str, Any], idx: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换structured类型的diff

        Returns:
            (错误响应或None, patch字典或None)
        """
        block_id = diff.get("block_id")
        action = diff.get("action")
        content = diff.get("content")

        if block_id is None:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx + 1} 个diff缺少block_id参数",
                },
                None,
            )
        if not isinstance(block_id, str):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx + 1} 个diff的block_id参数必须是字符串",
                },
                None,
            )
        if not block_id.strip():
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx + 1} 个diff的block_id参数不能为空",
                },
                None,
            )

        if action is None:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx + 1} 个diff缺少action参数",
                },
                None,
            )
        if not isinstance(action, str):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx + 1} 个diff的action参数必须是字符串",
                },
                None,
            )
        if action not in ["delete", "insert_before", "insert_after", "replace", "edit"]:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx + 1} 个diff的action参数必须是 delete、insert_before、insert_after、replace 或 edit 之一",
                },
                None,
            )

        # 对于edit操作，需要search和replace参数
        if action == "edit":
            search = diff.get("search")
            replace = diff.get("replace")
            if search is None:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff的action为 edit，需要提供search参数",
                    },
                    None,
                )
            if not isinstance(search, str):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff的search参数必须是字符串",
                    },
                    None,
                )
            if replace is None:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff的action为 edit，需要提供replace参数",
                    },
                    None,
                )
            if not isinstance(replace, str):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff的replace参数必须是字符串",
                    },
                    None,
                )
        # 对于非delete和非edit操作，content是必需的
        elif action != "delete":
            if content is None:
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff的action为 {action}，需要提供content参数",
                    },
                    None,
                )
            if not isinstance(content, str):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff的content参数必须是字符串",
                    },
                    None,
                )

        patch = {
            "STRUCTURED_BLOCK_ID": block_id,
            "STRUCTURED_ACTION": action,
        }
        if content is not None:
            patch["STRUCTURED_CONTENT"] = content
        if action == "edit":
            patch["STRUCTURED_SEARCH"] = diff.get("search")
            patch["STRUCTURED_REPLACE"] = diff.get("replace")
        return (None, patch)

    @staticmethod
    def _convert_diffs_to_patches(
        diffs: List[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]]]:
        """验证并转换diffs为内部patches格式

        Returns:
            (错误响应或None, patches列表)
        """
        patches = []
        for idx, diff in enumerate(diffs):
            if not isinstance(diff, dict):
                return (
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": f"第 {idx + 1} 个diff必须是字典类型",
                    },
                    [],
                )

            # 所有diff都是structured类型
            error_response, patch = EditFileTool._validate_structured(diff, idx + 1)

            if error_response:
                return (error_response, [])

            if patch:
                patches.append(patch)

        return (None, patches)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文件编辑操作（支持同时修改多个文件）"""
        try:
            # 验证基本参数
            error_response = EditFileTool._validate_basic_args(args)
            if error_response:
                return error_response

            files = args.get("files", [])
            agent = args.get("agent", None)

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch", group="tool")
            except Exception:
                pass

            # 处理每个文件
            all_results = []
            overall_success = True
            successful_files = []
            failed_files = []

            for file_item in files:
                file_path = file_item.get("file_path")
                diffs = file_item.get("diffs", [])

                # 转换diffs为patches
                error_response, patches = EditFileTool._convert_diffs_to_patches(diffs)
                if error_response:
                    all_results.append(
                        f"❌ {file_path}: {error_response.get('stderr', '参数验证失败')}"
                    )
                    failed_files.append(file_path)
                    overall_success = False
                    continue

                # 执行编辑
                success, result = self._fast_edit(file_path, patches, agent)

                if success:
                    all_results.append(f"✅ {file_path}: 修改成功")
                    successful_files.append(file_path)
                else:
                    all_results.append(f"❌ {file_path}: {result}")
                    failed_files.append(file_path)
                    overall_success = False

            # 构建输出信息
            output_lines = []
            if successful_files:
                output_lines.append(f"✅ 成功修改 {len(successful_files)} 个文件:")
                for file_path in successful_files:
                    output_lines.append(f"   - {file_path}")

            if failed_files:
                output_lines.append(f"\n❌ 失败 {len(failed_files)} 个文件:")
                for file_path in failed_files:
                    output_lines.append(f"   - {file_path}")

            stdout_text = "\n".join(all_results)
            summary = "\n".join(output_lines) if output_lines else ""

            if overall_success:
                return {
                    "success": True,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": summary if summary else "部分文件修改失败",
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            print(f"❌ {error_msg}")
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
        """按顺序返回补丁列表

        注意：对于结构化编辑，由于需要在实际应用时才能获取块的行号范围，
        这里暂时按原始顺序返回。如果需要优化，可以在应用时动态排序。

        Args:
            patches: 补丁列表

        Returns:
            补丁列表（当前按原始顺序返回）
        """
        # 对于结构化编辑，暂时按原始顺序处理
        # 如果需要按行号排序，需要在应用时动态获取块的行号范围
        return patches

    @staticmethod
    def _restore_file_from_cache(cache_info: Dict[str, Any]) -> str:
        """从缓存恢复文件内容

        Args:
            cache_info: 缓存信息字典

        Returns:
            恢复的文件内容字符串（与原始文件内容完全一致）
        """
        if not cache_info:
            return ""

        # 按照 id_list 的顺序恢复
        id_list = cache_info.get("id_list", [])
        blocks = cache_info.get("blocks", {})
        file_ends_with_newline = cache_info.get("file_ends_with_newline", False)

        result = []
        for idx, block_id in enumerate(id_list):
            block = blocks.get(block_id)
            if block:
                content = block.get("content", "")
                if content:
                    result.append(content)
                    # 在块之间添加换行符（最后一个块后面根据文件是否以换行符结尾决定）
                    is_last_block = idx == len(id_list) - 1
                    if is_last_block:
                        # 最后一个块：如果文件以换行符结尾，添加换行符
                        if file_ends_with_newline:
                            result.append("\n")
                    else:
                        # 非最后一个块：在块之间添加换行符
                        result.append("\n")

        return "".join(result) if result else ""

    @staticmethod
    def _apply_structured_edit_to_cache(
        cache_info: Dict[str, Any],
        block_id: str,
        action: str,
        new_content: Optional[str] = None,
        search: Optional[str] = None,
        replace: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[EditErrorType]]:
        """在缓存中应用结构化编辑

        Args:
            cache_info: 缓存信息字典（会被修改）
            block_id: 块id（字符串，从read_code工具获取）
            action: 操作类型（delete, insert_before, insert_after, replace, edit）
            new_content: 新内容（对于非delete和非edit操作）
            search: 要搜索的文本（对于edit操作）
            replace: 替换后的文本（对于edit操作）

        Returns:
            (是否成功, 错误信息, 错误类型)
        """
        if not cache_info:
            return (False, "缓存信息不完整", EditErrorType.CACHE_INVALID)

        # 从 blocks 字典中查找
        blocks = cache_info.get("blocks", {})
        block = blocks.get(block_id)

        if block is None:
            # 获取当前可用的块id列表
            available_block_ids = list(blocks.keys())

            # 构建错误消息：仅提示块id范围，而不是列出所有id
            if available_block_ids:
                try:
                    # 如果块id是顺序编码（数字或可比较的字符串），计算最小和最大值
                    sorted_ids = sorted(available_block_ids, key=str)
                    min_id = sorted_ids[0]
                    max_id = sorted_ids[-1]
                    error_msg = (
                        f"未找到块id: {block_id}。\n\n"
                        f"当前可用的块id范围: {min_id} ~ {max_id}\n\n"
                        f"💡 提示：请使用 read_code 工具查看文件的结构化块id，"
                        f"或根据上述范围校对并选择正确的块id。"
                    )
                except Exception:
                    # 回退：不展示具体列表，只给通用提示
                    error_msg = (
                        f"未找到块id: {block_id}。\n\n"
                        "当前存在一些块id，但无法安全计算其范围。\n\n"
                        "💡 提示：请使用 read_code 工具查看文件的结构化块id。"
                    )
            else:
                error_msg = (
                    f"未找到块id: {block_id}。\n\n"
                    "当前文件中没有可用的块id。\n\n"
                    "💡 提示：请使用 read_code 工具读取文件以获取结构化块id。"
                )

            return (False, error_msg, EditErrorType.BLOCK_ID_NOT_FOUND)

        # 根据操作类型执行编辑
        if action == "delete":
            # 删除块：将当前块的内容清空
            block["content"] = ""
            return (True, None, None)

        elif action == "insert_before":
            # 在块前插入：在当前块的内容前面插入文本
            if new_content is None:
                return (
                    False,
                    "insert_before操作需要提供content参数",
                    EditErrorType.PARAMETER_MISSING,
                )

            current_content = block.get("content", "")
            # 自动添加换行符：在插入内容后添加换行符（如果插入内容不以换行符结尾）
            if new_content and not new_content.endswith("\n"):
                new_content = new_content + "\n"
            block["content"] = new_content + current_content
            return (True, None, None)

        elif action == "insert_after":
            # 在块后插入：在当前块的内容后面插入文本
            if new_content is None:
                return (
                    False,
                    "insert_after操作需要提供content参数",
                    EditErrorType.PARAMETER_MISSING,
                )

            current_content = block.get("content", "")
            # 自动添加换行符：在插入内容前添加换行符（如果插入内容不以换行符开头）
            # 避免重复换行符：如果当前内容以换行符结尾，则不需要添加
            if new_content and not new_content.startswith("\n"):
                # 如果当前内容不以换行符结尾，则在插入内容前添加换行符
                if not current_content or not current_content.endswith("\n"):
                    new_content = "\n" + new_content
            block["content"] = current_content + new_content
            return (True, None, None)

        elif action == "replace":
            # 替换块
            if new_content is None:
                return (
                    False,
                    "replace操作需要提供content参数",
                    EditErrorType.PARAMETER_MISSING,
                )

            block["content"] = new_content
            return (True, None, None)

        elif action == "edit":
            # 在块内进行search/replace
            if search is None:
                return (
                    False,
                    "edit操作需要提供search参数",
                    EditErrorType.PARAMETER_MISSING,
                )
            if replace is None:
                return (
                    False,
                    "edit操作需要提供replace参数",
                    EditErrorType.PARAMETER_MISSING,
                )

            current_content = block.get("content", "")

            # 检查匹配次数：必须刚好只有一处匹配
            match_count = current_content.count(search)
            if match_count == 0:
                return (
                    False,
                    f"在块 {block_id} 中未找到要搜索的文本: {search[:100]}...",
                    EditErrorType.SEARCH_NOT_FOUND,
                )
            elif match_count > 1:
                # 找到所有匹配位置，并显示上下文
                lines = current_content.split("\n")
                matches_info = []
                search_lines = search.split("\n")
                search_line_count = len(search_lines)

                # 使用更精确的方法查找所有匹配位置（处理多行搜索）
                start_pos = 0
                match_idx = 0
                while match_idx < match_count and start_pos < len(current_content):
                    pos = current_content.find(search, start_pos)
                    if pos == -1:
                        break

                    # 计算匹配位置所在的行号
                    content_before_match = current_content[:pos]
                    line_idx = content_before_match.count("\n")

                    # 显示上下文（前后各2行）
                    start_line = max(0, line_idx - 2)
                    end_line = min(len(lines), line_idx + search_line_count + 2)
                    context_lines = lines[start_line:end_line]
                    context = "\n".join(
                        [
                            f"  {start_line + i + 1:4d}: {context_lines[i]}"
                            for i in range(len(context_lines))
                        ]
                    )

                    # 标记匹配的行
                    match_start_in_context = line_idx - start_line
                    match_start_in_context + search_line_count
                    matches_info.append(
                        f"匹配位置 {len(matches_info) + 1} (行 {line_idx + 1}):\n{context}"
                    )

                    start_pos = pos + 1  # 继续查找下一个匹配
                    match_idx += 1

                    if len(matches_info) >= 5:  # 最多显示5个匹配位置
                        break

                matches_preview = "\n\n".join(matches_info)
                if match_count > len(matches_info):
                    matches_preview += (
                        f"\n\n... 还有 {match_count - len(matches_info)} 处匹配未显示"
                    )

                search_preview = search[:100] + "..." if len(search) > 100 else search
                error_msg = (
                    f"在块 {block_id} 中找到 {match_count} 处匹配，但 edit 操作要求刚好只有一处匹配。\n"
                    f"搜索文本: {search_preview}\n\n"
                    f"匹配位置详情:\n{matches_preview}\n\n"
                    f"💡 提示：请提供更多的上下文（如包含前后几行代码）来唯一标识要替换的位置。"
                )
                return (False, error_msg, EditErrorType.MULTIPLE_MATCHES)

            # 在块内进行替换（只替换第一次出现，此时已经确认只有一处）
            block["content"] = current_content.replace(search, replace, 1)
            return (True, None, None)

        else:
            return (
                False,
                f"不支持的操作类型: {action}",
                EditErrorType.UNSUPPORTED_ACTION,
            )

    @staticmethod
    def _format_patch_description(patch: Dict[str, str]) -> str:
        """格式化补丁描述用于错误信息

        Args:
            patch: 补丁字典

        Returns:
            补丁描述字符串
        """
        if "STRUCTURED_BLOCK_ID" in patch:
            block_id = patch.get("STRUCTURED_BLOCK_ID", "")
            action = patch.get("STRUCTURED_ACTION", "")
            if action == "edit":
                search = patch.get("STRUCTURED_SEARCH", "")
                replace = patch.get("STRUCTURED_REPLACE", "")
                search_preview = search[:50] + "..." if len(search) > 50 else search
                replace_preview = replace[:50] + "..." if len(replace) > 50 else replace
                return f"结构化编辑: block_id={block_id}, action={action}, search={search_preview}, replace={replace_preview}"
            else:
                content = patch.get("STRUCTURED_CONTENT", "")
                if content:
                    content_preview = (
                        content[:100] + "..." if len(content) > 100 else content
                    )
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
        successful_patches: int,
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
        has_block_id_error = False  # 是否有块id相关错误
        has_cache_error = False  # 是否有缓存相关错误
        has_multiple_matches_error = False  # 是否有多处匹配错误
        has_other_error = False  # 是否有其他错误

        for p in failed_patches:
            patch = p["patch"]
            patch_desc = EditFileTool._format_patch_description(patch)
            error_msg = p["error"]
            error_type = p.get("error_type")  # 获取错误类型（如果存在）
            error_details.append(f"  - 失败的补丁: {patch_desc}\n    错误: {error_msg}")

            # 优先使用错误类型进行判断（如果存在），否则回退到字符串匹配
            if error_type:
                if error_type == EditErrorType.BLOCK_ID_NOT_FOUND:
                    has_block_id_error = True
                elif error_type == EditErrorType.CACHE_INVALID:
                    has_cache_error = True
                elif error_type == EditErrorType.MULTIPLE_MATCHES:
                    has_multiple_matches_error = True
                else:
                    has_other_error = True
            else:
                # 回退到字符串匹配（兼容旧代码或异常情况）
                error_msg_lower = error_msg.lower()

                # 块id相关错误：检查是否包含"块id"和"未找到"/"不存在"/"找不到"等关键词
                if (
                    "块id" in error_msg
                    or "block_id" in error_msg_lower
                    or "block id" in error_msg_lower
                ) and (
                    "未找到" in error_msg
                    or "不存在" in error_msg
                    or "找不到" in error_msg
                    or "not found" in error_msg_lower
                ):
                    has_block_id_error = True
                # 缓存相关错误：检查是否包含"缓存"或"cache"关键词
                elif ("缓存" in error_msg or "cache" in error_msg_lower) and (
                    "信息不完整" in error_msg
                    or "无效" in error_msg
                    or "过期" in error_msg
                    or "invalid" in error_msg_lower
                    or "expired" in error_msg_lower
                ):
                    has_cache_error = True
                # 多处匹配错误：检查是否包含"匹配"和数量相关的关键词
                elif ("匹配" in error_msg or "match" in error_msg_lower) and (
                    "处" in error_msg
                    or "个" in error_msg
                    or "multiple" in error_msg_lower
                    or (
                        "找到" in error_msg and ("处" in error_msg or "个" in error_msg)
                    )
                ):
                    # 识别多处匹配错误（错误消息中已经包含了详细提示）
                    has_multiple_matches_error = True
                else:
                    has_other_error = True

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

        # 根据错误类型添加不同的提示
        # 注意：多处匹配错误的错误消息中已经包含了详细提示，不需要额外添加
        hints = []
        if has_block_id_error:
            hints.append(
                "💡 块id不存在：请检查块id是否正确，或使用 read_code 工具重新读取文件以获取最新的块id列表。"
            )
        if has_cache_error:
            hints.append(
                "💡 缓存问题：文件可能已被外部修改，请使用 read_code 工具重新读取文件。"
            )
        if has_other_error and not (
            has_block_id_error or has_cache_error or has_multiple_matches_error
        ):
            hints.append("💡 提示：请检查块id、操作类型和参数是否正确。")

        if hints:
            summary += "\n\n" + "\n".join(hints)

        return summary

    @staticmethod
    def _write_file_with_rollback(
        abs_path: str, content: str, backup_path: Optional[str]
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
            print(f"❌ {error_msg}")
            return (False, error_msg)

    @staticmethod
    def _fast_edit(
        file_path: str, patches: List[Dict[str, str]], agent: Any = None
    ) -> Tuple[bool, str]:
        """快速应用补丁到文件

        该方法基于缓存进行编辑：
        1. 先检查缓存有效性，无效则提示重新读取
        2. 在缓存中应用所有补丁
        3. 从缓存恢复文件内容并写入
        4. 更新缓存的时间戳

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含 STRUCTURED_BLOCK_ID
            agent: Agent实例，用于访问缓存

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否所有补丁都成功应用，
                第二个元素为结果信息，全部成功时为修改后的文件内容，部分或全部失败时为错误信息
        """
        abs_path = os.path.abspath(file_path)
        backup_path = None

        try:
            # 检查缓存有效性
            cache_info = EditFileTool._get_file_cache(agent, abs_path)
            if not EditFileTool._is_cache_valid(cache_info, abs_path):
                error_msg = (
                    f"⚠️ 缓存无效或文件已被外部修改。\n"
                    f"📋 文件: {abs_path}\n"
                    f"💡 请先使用 read_code 工具重新读取文件，然后再进行编辑。"
                )
                return False, error_msg

            # 创建缓存副本，避免直接修改原缓存
            cache_copy = {
                "id_list": list(cache_info["id_list"]),  # 浅拷贝列表
                "blocks": {
                    k: v.copy() for k, v in cache_info["blocks"].items()
                },  # 深拷贝字典
                "total_lines": cache_info["total_lines"],
                "read_time": cache_info.get("read_time", time.time()),
                "file_mtime": cache_info.get("file_mtime", 0),
                "file_ends_with_newline": cache_info.get(
                    "file_ends_with_newline", False
                ),
            }

            # 创建备份
            if os.path.exists(abs_path):
                backup_path = abs_path + ".bak"
                try:
                    shutil.copy2(abs_path, backup_path)
                except Exception:
                    backup_path = None

            # 对补丁进行排序
            ordered_patches = EditFileTool._order_patches_by_range(patches)
            patch_count = len(ordered_patches)
            failed_patches: List[Dict[str, Any]] = []
            successful_patches = 0

            # 在缓存中应用所有补丁
            for patch in ordered_patches:
                # 结构化编辑模式
                if "STRUCTURED_BLOCK_ID" in patch:
                    block_id = patch.get("STRUCTURED_BLOCK_ID", "")
                    action = patch.get("STRUCTURED_ACTION", "")
                    new_content = patch.get("STRUCTURED_CONTENT")
                    search = patch.get("STRUCTURED_SEARCH")
                    replace = patch.get("STRUCTURED_REPLACE")
                    try:
                        success, error_msg, error_type = (
                            EditFileTool._apply_structured_edit_to_cache(
                                cache_copy,
                                block_id,
                                action,
                                new_content,
                                search,
                                replace,
                            )
                        )
                        if success:
                            successful_patches += 1
                        else:
                            failed_patches.append(
                                {
                                    "patch": patch,
                                    "error": error_msg,
                                    "error_type": error_type,
                                }
                            )
                    except Exception as e:
                        error_msg = (
                            f"结构化编辑执行出错: {str(e)}\n"
                            f"block_id: {block_id}, action: {action}"
                        )
                        failed_patches.append(
                            {
                                "patch": patch,
                                "error": error_msg,
                                "error_type": EditErrorType.OTHER,
                            }
                        )
                else:
                    # 如果不支持的模式，记录错误
                    error_msg = "不支持的补丁格式。支持的格式: STRUCTURED_BLOCK_ID"
                    failed_patches.append(
                        {
                            "patch": patch,
                            "error": error_msg,
                            "error_type": EditErrorType.OTHER,
                        }
                    )

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
                print(f"❌ {summary}")
                return False, summary

            # 从缓存恢复文件内容
            modified_content = EditFileTool._restore_file_from_cache(cache_copy)
            if not modified_content:
                error_msg = (
                    "从缓存恢复文件内容失败。\n"
                    "可能原因：缓存数据结构损坏或文件结构异常。\n\n"
                    "💡 提示：请使用 read_code 工具重新读取文件，然后再进行编辑。"
                )
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                return False, error_msg

            # 写入文件
            success, error_msg = EditFileTool._write_file_with_rollback(
                abs_path, modified_content, backup_path
            )
            if not success:
                # 写入失败通常是权限、磁盘空间等问题，不需要重新读取文件
                error_msg += (
                    "\n\n💡 提示：文件写入失败，可能是权限不足、磁盘空间不足或文件被锁定。"
                    "请检查文件权限和磁盘空间，或稍后重试。"
                )
                return False, error_msg

            # 写入成功，更新缓存
            if agent:
                cache = agent.get_user_data("read_code_cache")
                if cache and abs_path in cache:
                    # 更新缓存内容
                    cache[abs_path] = cache_copy
                    # 更新缓存时间戳
                    EditFileTool._update_cache_timestamp(agent, abs_path)
                    agent.set_user_data("read_code_cache", cache)

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
                print(f"❌ {summary}")
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

            # 根据异常类型给出不同的提示
            error_type = type(e).__name__
            error_str = str(e)

            # 检查是否是权限错误
            is_permission_error = (
                error_type == "PermissionError"
                or (error_type == "OSError" and hasattr(e, "errno") and e.errno == 13)
                or "Permission denied" in error_str
                or "权限" in error_str
                or "permission" in error_str.lower()
            )

            # 检查是否是磁盘空间错误
            is_space_error = (
                (error_type == "OSError" and hasattr(e, "errno") and e.errno == 28)
                or "No space left" in error_str
                or "No space" in error_str
                or "ENOSPC" in error_str
                or "磁盘" in error_str
                or "空间" in error_str
            )

            # 检查是否是文件不存在错误
            is_not_found_error = (
                error_type == "FileNotFoundError"
                or (error_type == "OSError" and hasattr(e, "errno") and e.errno == 2)
                or "No such file" in error_str
                or "文件不存在" in error_str
            )

            # 检查是否是缓存或块相关错误（这些通常是我们自己的错误消息）
            is_cache_error = (
                "cache" in error_str.lower()
                or "缓存" in error_str
                or "未找到块id" in error_str
                or "块id" in error_str
            )

            if is_permission_error:
                hint = "💡 提示：文件权限不足，请检查文件权限或使用管理员权限运行。"
            elif is_space_error:
                hint = "💡 提示：磁盘空间不足，请清理磁盘空间后重试。"
            elif is_not_found_error:
                hint = "💡 提示：文件不存在，请检查文件路径是否正确。"
            elif is_cache_error:
                hint = "💡 提示：缓存或块id相关错误，请使用 read_code 工具重新读取文件，然后再进行编辑。"
            elif "block" in error_str.lower() or "块" in error_str:
                hint = "💡 提示：块操作错误，请使用 read_code 工具重新读取文件，然后再进行编辑。"
            else:
                hint = f"💡 提示：发生未知错误（{error_type}），请检查错误信息或重试。如问题持续，请使用 read_code 工具重新读取文件。"

            error_msg = f"文件修改失败: {error_str}\n\n{hint}"
            print(f"❌ {error_msg}")
            return False, error_msg


__all__ = ["EditFileTool", "EditErrorType"]


