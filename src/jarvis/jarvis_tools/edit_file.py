"""普通文件编辑工具（基于 search/replace 的非结构化编辑）"""

import os
import shutil

from jarvis.jarvis_utils.config import (
    detect_file_encoding,
    get_default_encoding,
    read_text_file,
)
from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple


class EditFileNormalTool:
    """普通文件编辑工具，完全基于 search/replace 进行文件编辑"""

    name = "edit_file"
    description = (
        "使用 search/replace 对文件进行普通文本编辑（不依赖块id），支持同时修改多个文件。\n\n"
        "💡 使用方式：\n"
        "1. 直接指定要编辑的文件路径\n"
        "2. 为每个文件提供一组 search/replace 操作\n"
        "3. 使用精确匹配查找 search 文本，找到匹配后替换为新文本\n\n"
        "🚀 特殊功能：\n"
        '- 当 search 为空字符串 "" 时，表示直接重写整个文件，replace 的内容将作为文件的完整新内容\n'
        "- 如果存在多个diffs且第一个diff的search为空字符串，将只应用第一个diff（重写整个文件），跳过后续所有diffs\n"
        "- **支持部分成功**：当某个文件的多个 diffs 中有部分失败时，已成功的修改仍会保留到文件中，并会详细报告每个 diff 的执行结果\n\n"
        "⚠️ 提示：\n"
        "- search 使用精确字符串匹配，不支持正则表达式\n"
        "- **重要：search 必须提供足够的上下文来唯一定位目标位置**，避免匹配到错误的位置。建议包含：\n"
        "  * 目标代码的前后几行上下文（至少包含目标代码所在函数的签名或关键标识）\n"
        "  * 目标代码附近的唯一标识符（如函数名、变量名、注释等）\n"
        "  * 避免使用过短的 search 文本（如单个单词、短字符串），除非能确保唯一性\n"
        "- 如果某个 search 在文件中找不到精确匹配（search非空时），该 diff 会失败，但已成功的修改会保留\n"
        "- 建议在 search 中包含足够的上下文，确保能唯一匹配到目标位置，避免误匹配"
    )

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
                                    "search": {
                                        "type": "string",
                                        "description": '要搜索的原始文本（不支持正则表达式）。当为空字符串""时，表示直接重写整个文件，replace的内容将作为文件的完整新内容。非空时，**重要：必须提供足够的上下文来唯一定位目标位置**，建议包含目标代码的前后几行上下文、函数签名或唯一标识符，避免匹配到错误的位置。',
                                    },
                                    "replace": {
                                        "type": "string",
                                        "description": "替换后的文本（可以为空字符串）",
                                    },
                                },
                                "required": ["search", "replace"],
                            },
                            "description": "普通文本替换操作列表，按顺序依次应用到文件内容",
                        },
                    },
                    "required": ["file_path", "diffs"],
                },
                "description": "要修改的文件列表，每个文件包含文件路径和对应的 search/replace 操作列表",
            },
        },
        "required": ["files"],
    }

    def __init__(self) -> None:
        """初始化普通文件编辑工具"""
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
    def _read_file_with_backup(
        file_path: str,
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """读取文件并创建备份

        Args:
            file_path: 文件路径

        Returns:
            (文件内容, 备份文件路径或None, 检测到的编码或None)
        """
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        file_content = ""
        backup_path = None
        detected_encoding = None
        if os.path.exists(abs_path):
            # 先检测编码
            detected_encoding = detect_file_encoding(abs_path)
            file_content = read_text_file(abs_path)
            # 创建备份文件
            backup_path = abs_path + ".bak"
            try:
                shutil.copy2(abs_path, backup_path)
            except Exception:
                # 备份失败不影响主流程
                backup_path = None

        return file_content, backup_path, detected_encoding

    @staticmethod
    def _write_file_with_rollback(
        abs_path: str,
        content: str,
        backup_path: Optional[str],
        encoding: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """写入文件，失败时回滚

        Args:
            abs_path: 文件绝对路径
            content: 要写入的内容
            backup_path: 备份文件路径或None
            encoding: 指定编码，若为None则自动检测

        Returns:
            (是否成功, 错误信息或None)
        """
        enc = encoding or detect_file_encoding(abs_path) or get_default_encoding()
        try:
            with open(abs_path, "w", encoding=enc, errors="replace") as f:
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
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return (False, error_msg)

    @staticmethod
    def _validate_normal_diff(
        diff: Dict[str, Any], idx: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """验证并转换 normal 类型的 diff

        Returns:
            (错误响应或None, 规范化后的diff或None)
        """
        search = diff.get("search")
        replace = diff.get("replace")

        if search is None:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff缺少search参数",
                },
                None,
            )
        if not isinstance(search, str):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的search参数必须是字符串",
                },
                None,
            )
        # 允许空字符串作为search参数，表示直接重写整个文件

        if replace is None:
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff缺少replace参数",
                },
                None,
            )
        if not isinstance(replace, str):
            return (
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx} 个diff的replace参数必须是字符串",
                },
                None,
            )

        return (
            None,
            {
                "search": search,
                "replace": replace,
            },
        )

    @staticmethod
    def _count_matches(content: str, search_text: str) -> int:
        """统计文本在内容中的匹配次数

        Args:
            content: 文件内容
            search_text: 要搜索的文本

        Returns:
            匹配次数
        """
        if not search_text:
            return 0
        return content.count(search_text)

    @staticmethod
    def _is_file_in_workspace_subdir(file_path: str) -> bool:
        """检查文件是否在当前工作目录的子级目录下

        Args:
            file_path: 文件路径（可以是绝对路径或相对路径）

        Returns:
            True 如果文件在当前工作目录的子级目录下，False 否则
        """
        try:
            abs_file_path = os.path.abspath(file_path)
            abs_workspace_path = os.path.abspath(os.getcwd())

            # 检查文件路径是否以工作目录路径开头
            # 使用 os.path.commonpath 来正确处理路径
            try:
                common_path = os.path.commonpath([abs_file_path, abs_workspace_path])
                # 如果公共路径等于工作目录路径，说明文件在工作目录或其子目录下
                return os.path.abspath(common_path) == abs_workspace_path
            except ValueError:
                # 如果路径不在同一驱动器上（Windows），commonpath 会抛出 ValueError
                return False
        except Exception:
            # 如果出现任何异常，默认返回 False
            return False

    @staticmethod
    def _generate_diff_preview(
        original_content: str,
        modified_content: str,
        file_path: str,
    ) -> str:
        """生成修改后的预览diff

        Args:
            original_content: 原始文件内容
            modified_content: 修改后的文件内容
            file_path: 文件路径

        Returns:
            预览diff字符串
        """
        import difflib

        # 生成统一的diff格式
        original_lines = original_content.splitlines(keepends=True)
        modified_lines = modified_content.splitlines(keepends=True)

        # 使用difflib生成统一的diff
        diff = list(
            difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
        )

        diff_preview = "".join(diff)
        return diff_preview

    @staticmethod
    def _confirm_multiple_matches(
        agent: Any,
        file_path: str,
        original_content: str,
        modified_content: str,
        match_count: int,
        search_text: str,
        replace_text: str,
    ) -> bool:
        """使用 agent 确认多个匹配是否应该继续

        Args:
            agent: Agent 实例
            file_path: 文件路径
            original_content: 原始文件内容
            modified_content: 修改后的文件内容
            match_count: 匹配次数
            search_text: 搜索文本
            replace_text: 替换文本

        Returns:
            True 表示确认继续，False 表示取消
        """
        try:
            from jarvis.jarvis_agent import Agent

            agent_instance: Agent = agent
            if not agent_instance or not agent_instance.model:
                # 如果没有 agent 或 model，默认不继续
                return False

            # 生成预览diff
            diff_preview = EditFileNormalTool._generate_diff_preview(
                original_content,
                modified_content,
                file_path,
            )

            prompt = f"""检测到文件编辑操作中，search 文本在文件中存在多处匹配，需要您确认是否继续修改：

文件路径：{file_path}

匹配统计：
- 匹配数量: {match_count}
- 搜索文本长度: {len(search_text)} 字符
- 替换文本长度: {len(replace_text)} 字符

修改预览（diff）：
{diff_preview}

请仔细分析以上代码变更，判断这些修改是否合理。可能的情况包括：
1. 这些匹配位置都是您想要修改的，修改是正确的
2. 这些匹配位置不是您想要的，或者需要更精确的定位
3. 修改可能影响其他不相关的代码

请使用以下协议回答（必须包含且仅包含以下标记之一）：
- 如果认为这些修改是合理的，回答: <!!!YES!!!>
- 如果认为这些修改不合理或存在风险，回答: <!!!NO!!!>

请严格按照协议格式回答，不要添加其他内容。"""

            PrettyOutput.auto_print("🤖 正在询问大模型确认多处匹配的修改是否合理...")
            response = agent_instance.model.chat_until_success(prompt)
            response_str = str(response or "")

            # 使用确定的协议标记解析回答
            if "<!!!YES!!!>" in response_str:
                PrettyOutput.auto_print("✅ 大模型确认：修改合理，继续执行")
                return True
            elif "<!!!NO!!!>" in response_str:
                PrettyOutput.auto_print("⚠️ 大模型确认：修改不合理，取消操作")
                return False
            else:
                # 如果无法找到协议标记，默认认为不合理（保守策略）
                PrettyOutput.auto_print(
                    f"⚠️ 无法找到协议标记，默认认为不合理。回答内容: {response_str[:200]}"
                )
                return False
        except Exception as e:
            # 确认过程出错，默认不继续
            PrettyOutput.auto_print(f"⚠️ 确认过程出错: {e}，默认取消操作")
            return False

    @staticmethod
    def _apply_normal_edits_to_content(
        original_content: str,
        diffs: List[Dict[str, Any]],
        agent: Optional[Any] = None,
        file_path: Optional[str] = None,
        start_idx: int = 0,
    ) -> Tuple[
        bool, str, List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[int]
    ]:
        """对文件内容按顺序应用普通 search/replace 编辑（使用字符串替换）

        Args:
            original_content: 原始文件内容（或已部分修改的内容）
            diffs: diff 列表
            agent: 可选的 agent 实例
            file_path: 可选的文件路径
            start_idx: 从哪个 diff 索引开始处理（0-based，用于继续处理剩余 diffs）

        返回:
            (是否全部成功, 最终内容, diff执行结果列表, 确认信息字典或None, 需要确认的diff索引或None)
            diff执行结果列表格式: [{idx: int, success: bool, error: str or None}]
            确认信息字典包含: match_count, search_text, replace_text, modified_content, current_content
        """
        content = original_content
        diff_results: List[Dict[str, Any]] = []  # 记录每个 diff 的执行结果
        all_success = True  # 标记是否所有 diff 都成功

        for idx, diff in enumerate(diffs[start_idx:], start=start_idx + 1):
            search = diff["search"]
            replace = diff["replace"]

            # 处理空字符串search的特殊情况
            if search == "":
                # 空字符串表示直接重写整个文件
                content = replace
                # 记录这个 diff 成功
                diff_results.append({"idx": idx, "success": True, "error": None})
                # 空search只处理第一个diff，跳过后续所有diffs
                break

            # 检查 search 和 replace 是否完全一致（无效操作）
            if search == replace:
                all_success = False
                error_info = (
                    "search 和 replace 内容完全相同，这是一个无效操作（没有实际修改）"
                )
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue  # 继续处理后续 diffs

            # 验证 search 文本
            if not isinstance(search, str):
                all_success = False
                error_info = "search 文本必须是字符串"
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue

            # 统计匹配次数
            match_count = EditFileNormalTool._count_matches(content, search)

            if match_count == 0:
                # 找不到匹配
                all_success = False
                error_info = "未找到精确匹配的文本"
                if search:
                    error_info += f"\n搜索文本: {search[:200]}..."
                    error_info += (
                        "\n💡 提示：如果搜索文本在文件中存在但未找到匹配，可能是因为："
                    )
                    error_info += "\n   1. 搜索文本包含不可见字符或格式不匹配（建议检查空格、换行等）"
                    error_info += "\n   2. **文件可能已被更新**：如果文件在其他地方被修改了，搜索文本可能已经不存在或已改变"
                    if file_path:
                        error_info += f"\n   💡 建议：使用 `read_code` 工具重新读取文件 `{file_path}` 查看当前内容，"
                        error_info += "\n      确认文件是否已被更新，然后根据实际内容调整 search 文本"
                diff_results.append({"idx": idx, "success": False, "error": error_info})
                continue

            if match_count == 1:
                # 唯一匹配，直接替换
                content = content.replace(search, replace, 1)
                diff_results.append({"idx": idx, "success": True, "error": None})
            else:
                # 多个匹配，需要确认
                # 生成修改后的内容（替换所有匹配）
                modified_content = content.replace(search, replace)
                # 返回确认信息，包含当前内容以便继续处理后续 diffs
                # 注意：这里返回时，之前成功的 diff 的修改已经应用到 content 中了
                confirm_info = {
                    "match_count": match_count,
                    "search_text": search,
                    "replace_text": replace,
                    "modified_content": modified_content,
                    "current_content": content,  # 保存当前内容，用于继续处理
                    "diff_idx": idx,  # 保存当前 diff 索引
                    "diff_results_before_confirm": diff_results,  # 保存之前成功的结果
                }
                # 返回 False 表示需要确认，但之前成功的修改已经保留在 diff_results 中
                return False, content, diff_results, confirm_info, idx

        return all_success, content, diff_results, None, None

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行普通 search/replace 文件编辑操作（支持同时修改多个文件）"""
        try:
            # 验证基本参数（files 结构）
            error_response = EditFileNormalTool._validate_basic_args(args)
            if error_response:
                return error_response

            files = args.get("files", [])
            # 获取 agent 实例（v1.0 协议中 agent 在 args 中）
            agent = args.get("agent")

            all_results = []
            overall_success = True
            successful_files = []
            failed_files = []

            for file_item in files:
                file_path = file_item.get("file_path")
                diffs = file_item.get("diffs", [])

                # 校验并规范化 diffs
                normalized_diffs: List[Dict[str, Any]] = []
                for idx, diff in enumerate(diffs, start=1):
                    if not isinstance(diff, dict):
                        all_results.append(
                            f"❌ {file_path}: 第 {idx} 个diff必须是字典类型"
                        )
                        failed_files.append(file_path)
                        overall_success = False
                        normalized_diffs = []
                        break

                    error, normalized = EditFileNormalTool._validate_normal_diff(
                        diff, idx
                    )
                    if error:
                        all_results.append(
                            f"❌ {file_path}: {error.get('stderr', '参数验证失败')}"
                        )
                        failed_files.append(file_path)
                        overall_success = False
                        normalized_diffs = []
                        break

                    if normalized is not None:
                        normalized_diffs.append(normalized)

                if not normalized_diffs:
                    # 该文件的diffs有问题，已记录错误，跳过
                    continue

                # 读取原始内容并创建备份
                (
                    original_content,
                    backup_path,
                    detected_encoding,
                ) = EditFileNormalTool._read_file_with_backup(file_path)

                # 应用所有普通编辑，使用循环处理所有可能的确认情况
                current_content = original_content
                current_start_idx = 0
                success = False
                result_or_error = ""
                diff_results: List[Dict[str, Any]] = []  # 存储所有 diff 的执行结果
                max_confirm_iterations = len(normalized_diffs) * 2  # 防止无限循环
                confirm_iteration = 0

                while confirm_iteration < max_confirm_iterations:
                    (
                        iter_all_success,
                        iter_result_content,
                        iter_diff_results,
                        iter_confirm_info,
                        iter_confirm_diff_idx,
                    ) = EditFileNormalTool._apply_normal_edits_to_content(
                        current_content,
                        normalized_diffs,
                        agent=agent,
                        file_path=file_path,
                        start_idx=current_start_idx,
                    )

                    # 合并本次迭代的 diff_results
                    diff_results.extend(iter_diff_results)

                    if iter_all_success:
                        # 所有 diffs 处理成功
                        success = True
                        result_or_error = iter_result_content
                        break

                    # 处理失败，检查是否需要确认
                    if (
                        iter_confirm_info
                        and agent
                        and iter_confirm_diff_idx is not None
                    ):
                        # 需要确认
                        confirmed = EditFileNormalTool._confirm_multiple_matches(
                            agent,
                            file_path,
                            original_content,
                            iter_confirm_info["modified_content"],
                            iter_confirm_info["match_count"],
                            iter_confirm_info["search_text"],
                            iter_confirm_info["replace_text"],
                        )

                        if confirmed:
                            # 确认继续，应用当前 diff 的所有匹配替换
                            current_content = iter_confirm_info["modified_content"]
                            # 记录当前 diff 成功
                            diff_results.append(
                                {
                                    "idx": iter_confirm_diff_idx,
                                    "success": True,
                                    "error": None,
                                }
                            )
                            current_diff_idx = iter_confirm_info.get(
                                "diff_idx", iter_confirm_diff_idx
                            )
                            # 从下一个 diff 继续处理
                            # current_diff_idx 是 1-based（第几个 diff），转换为 0-based 列表索引
                            # 例如：diff_idx=2 表示第 2 个 diff（diffs[1]），下一个是 diffs[2]，所以 start_idx=2
                            # 注意：current_diff_idx 是 1-based，下一个 diff 的 0-based 索引正好等于 current_diff_idx
                            current_start_idx = current_diff_idx
                            confirm_iteration += 1
                            # 继续循环处理剩余 diffs
                            continue
                        else:
                            # 确认取消
                            if backup_path and os.path.exists(backup_path):
                                try:
                                    os.remove(backup_path)
                                except Exception:
                                    pass
                            # 检查是否有任何成功的 diff
                            has_success = any(dr.get("success") for dr in diff_results)
                            if has_success:
                                success = True  # 部分成功
                                result_or_error = current_content
                                # 添加取消信息到结果中
                                all_results.append(
                                    f"⚠️ {file_path}: 部分成功（取消多处匹配确认）"
                                )
                            else:
                                result_or_error = (
                                    "操作已取消（发现多处匹配，已确认不继续）"
                                )
                                all_results.append(f"❌ {file_path}: {result_or_error}")
                                failed_files.append(file_path)
                                overall_success = False
                            break
                    else:
                        # 没有确认信息或没有 agent，检查是否有任何成功的 diff
                        has_success = any(dr.get("success") for dr in diff_results)
                        if has_success:
                            # 部分成功
                            success = True
                            result_or_error = iter_result_content
                            # 部分成功时，需要将整体操作标记为失败
                            overall_success = False
                        else:
                            # 完全失败
                            success = False
                            # 构建错误信息
                            error_msg_parts = []
                            for dr in diff_results:
                                if not dr.get("success"):
                                    error_msg_parts.append(
                                        f"Diff #{dr.get('idx')}: {dr.get('error', '未知错误')}"
                                    )
                            result_or_error = (
                                "\n".join(error_msg_parts)
                                if error_msg_parts
                                else "处理失败：未知错误"
                            )
                        break

                if not success:
                    # 处理失败，确保有错误信息
                    if not result_or_error:
                        if confirm_iteration >= max_confirm_iterations:
                            # 达到最大确认次数，可能陷入循环
                            result_or_error = f"处理失败：达到最大确认次数限制（{max_confirm_iterations}），可能存在循环确认问题"
                        else:
                            result_or_error = "处理失败：未知错误"

                    # 处理失败
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass
                    all_results.append(f"❌ {file_path}: {result_or_error}")
                    failed_files.append(file_path)
                    overall_success = False
                    continue

                # 编辑成功，继续写入文件
                result_or_error = result_or_error  # 此时 result_or_error 是新内容

                # 写入文件（失败时回滚）
                abs_path = os.path.abspath(file_path)
                (
                    write_success,
                    write_error,
                ) = EditFileNormalTool._write_file_with_rollback(
                    abs_path, result_or_error, backup_path, detected_encoding
                )
                if write_success:
                    # 写入成功，删除备份文件
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass

                    # 检查文件是否不在当前工作目录的子级目录下
                    # 如果不在，生成并打印 diff
                    in_workspace = EditFileNormalTool._is_file_in_workspace_subdir(
                        abs_path
                    )

                    if not (
                        agent and agent.agent_type() == "code_agent" and in_workspace
                    ):
                        try:
                            # 生成 diff
                            diff_text = EditFileNormalTool._generate_diff_preview(
                                original_content,
                                result_or_error,
                                file_path,
                            )

                            # 打印 diff（使用 diff_visualizer）
                            from jarvis.jarvis_code_agent.diff_visualizer import (
                                visualize_diff_enhanced,
                            )

                            visualize_diff_enhanced(
                                diff_text,
                                file_path=file_path,
                                mode="side_by_side",
                                show_line_numbers=True,
                                context_lines=3,
                            )

                            # 将 diff 添加到 stdout
                            all_results.append(
                                f"\n📝 {file_path} 的 diff（文件不在当前工作目录的子级目录下）:"
                            )
                            all_results.append(diff_text)
                        except Exception as diff_error:
                            # diff 生成或打印失败不影响主流程
                            PrettyOutput.auto_print(
                                f"⚠️ 生成 diff 时出错: {str(diff_error)}"
                            )

                    # 检查是否是部分成功（有失败的 diff）
                    failed_diffs = [dr for dr in diff_results if not dr.get("success")]
                    if failed_diffs:
                        # 部分成功，生成详细报告
                        success_count = sum(
                            1 for dr in diff_results if dr.get("success")
                        )
                        all_results.append(
                            f"⚠️ {file_path}: 部分成功 ({success_count}/{len(diff_results)} 个diff成功)"
                        )
                        # 添加每个 diff 的详细信息
                        for dr in diff_results:
                            idx = dr.get("idx", 0)
                            if dr.get("success"):
                                all_results.append(f"   ✅ Diff #{idx}: 成功")
                            else:
                                error = dr.get("error", "未知错误")
                                # 简化错误信息显示（每行错误缩进显示）
                                for line in error.split("\n"):
                                    all_results.append(f"   ❌ Diff #{idx}: {line}")
                        successful_files.append(
                            file_path
                        )  # 仍然算作成功文件（部分成功也算成功）
                        # 部分成功时，不将文件添加到 failed_files，因为文件已成功写入
                        # 但需要将整体操作标记为失败
                        overall_success = False
                    else:
                        all_results.append(f"✅ {file_path}: 修改成功")
                        successful_files.append(file_path)
                else:
                    all_results.append(f"❌ {file_path}: {write_error}")
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
                # 失败时，stderr 应该包含详细的错误信息，而不仅仅是文件列表
                # 从 all_results 中提取失败和部分成功的详细错误信息
                failed_details = []
                for result in all_results:
                    # 提取失败信息（包含❌）和部分成功的警告（包含⚠️）
                    # 检查是否包含这些标记，而不是只检查开头，因为详细错误信息可能有缩进
                    if "❌" in result or "⚠️" in result:
                        failed_details.append(result)

                # 如果有详细的错误信息，使用它们；否则使用 summary
                stderr_content = (
                    "\n".join(failed_details)
                    if failed_details
                    else (summary if summary else "部分文件修改失败")
                )

                return {
                    "success": False,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": stderr_content,
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}


__all__ = ["EditFileNormalTool"]
