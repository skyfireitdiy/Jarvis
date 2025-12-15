"""普通文件编辑工具（基于 search/replace 的非结构化编辑）"""

import os
import shutil

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
        "- 当 search 为空字符串 \"\" 时，表示直接重写整个文件，replace 的内容将作为文件的完整新内容\n"
        "- 如果存在多个diffs且第一个diff的search为空字符串，将只应用第一个diff（重写整个文件），跳过后续所有diffs\n\n"
        "⚠️ 提示：\n"
        "- search 使用精确字符串匹配，不支持正则表达式\n"
        "- **重要：search 必须提供足够的上下文来唯一定位目标位置**，避免匹配到错误的位置。建议包含：\n"
        "  * 目标代码的前后几行上下文（至少包含目标代码所在函数的签名或关键标识）\n"
        "  * 目标代码附近的唯一标识符（如函数名、变量名、注释等）\n"
        "  * 避免使用过短的 search 文本（如单个单词、短字符串），除非能确保唯一性\n"
        "- 如果某个 search 在文件中找不到精确匹配（search非空时），将导致该文件的编辑失败，文件内容会回滚到原始状态\n"
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
                                        "description": "要搜索的原始文本（不支持正则表达式）。当为空字符串\"\"时，表示直接重写整个文件，replace的内容将作为文件的完整新内容。非空时，**重要：必须提供足够的上下文来唯一定位目标位置**，建议包含目标代码的前后几行上下文、函数签名或唯一标识符，避免匹配到错误的位置。",
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

    def __init__(self):
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
    def _generate_diff_preview(
        original_content: str,
        modified_content: str,
        file_path: str,
        match_count: int,
        search_text: str,
        replace_text: str,
        agent: Optional[Any] = None,
        token_ratio: float = 0.3,
    ) -> str:
        """生成修改后的预览diff

        Args:
            original_content: 原始文件内容
            modified_content: 修改后的文件内容
            file_path: 文件路径
            match_count: 匹配次数
            search_text: 搜索文本
            replace_text: 替换文本
            agent: 可选的 agent 实例，用于获取剩余 token 数量
            token_ratio: token 使用比例（默认 0.3，即 30%）

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

        # 根据剩余token计算最大字符数
        max_diff_chars = None

        # 优先尝试使用 agent 获取剩余 token（更准确，包含对话历史）
        if agent:
            try:
                remaining_tokens = agent.get_remaining_token_count()
                if remaining_tokens > 0:
                    # 使用剩余 token 的指定比例作为字符限制（1 token ≈ 4字符）
                    max_diff_chars = int(remaining_tokens * token_ratio * 4)
                    if max_diff_chars <= 0:
                        max_diff_chars = None
            except Exception:
                pass

        # 回退方案：使用输入窗口的指定比例转换为字符数
        if max_diff_chars is None:
            try:
                from jarvis.jarvis_utils.config import get_max_input_token_count

                max_input_tokens = get_max_input_token_count()
                max_diff_chars = int(max_input_tokens * token_ratio * 4)
            except Exception:
                # 如果获取失败，使用默认值（约 10000 字符）
                max_diff_chars = 10000

        # 限制diff长度
        if len(diff_preview) > max_diff_chars:
            diff_preview = (
                diff_preview[:max_diff_chars] + "\n... (diff 内容过长，已截断)"
            )

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
                match_count,
                search_text,
                replace_text,
                agent=agent_instance,
                token_ratio=0.3,  # 使用30%的剩余token用于diff预览
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
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[int]]:
        """对文件内容按顺序应用普通 search/replace 编辑（使用字符串替换）

        返回:
            (是否成功, 新内容或错误信息, 确认信息字典或None, 需要确认的diff索引或None)
            确认信息字典包含: match_count, search_text, replace_text, modified_content
        """
        content = original_content

        for idx, diff in enumerate(diffs, start=1):
            search = diff["search"]
            replace = diff["replace"]

            # 处理空字符串search的特殊情况
            if search == "":
                # 空字符串表示直接重写整个文件
                content = replace
                # 空search只处理第一个diff，跳过后续所有diffs
                break

            # 验证 search 文本
            if not isinstance(search, str):
                error_info = f"第 {idx} 个diff失败：search 文本必须是字符串"
                return False, error_info, None, None

            # 统计匹配次数
            match_count = EditFileNormalTool._count_matches(content, search)

            if match_count == 0:
                # 找不到匹配
                error_info = f"第 {idx} 个diff失败：未找到精确匹配的文本"
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
                return False, error_info, None, None

            if match_count == 1:
                # 唯一匹配，直接替换
                content = content.replace(search, replace, 1)
            else:
                # 多个匹配，需要确认
                # 生成修改后的内容（替换所有匹配）
                modified_content = content.replace(search, replace)
                # 返回确认信息
                confirm_info = {
                    "match_count": match_count,
                    "search_text": search,
                    "replace_text": replace,
                    "modified_content": modified_content,
                }
                error_info = (
                    f"第 {idx} 个diff失败：发现 {match_count} 处匹配，需要确认后再修改"
                )
                return False, error_info, confirm_info, idx

        return True, content, None, None

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

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch_normal", group="tool")
            except Exception:
                pass

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
                ) = EditFileNormalTool._read_file_with_backup(file_path)

                # 应用所有普通编辑
                (
                    success,
                    result_or_error,
                    confirm_info,
                    confirm_diff_idx,
                ) = EditFileNormalTool._apply_normal_edits_to_content(
                    original_content,
                    normalized_diffs,
                    agent=agent,
                    file_path=file_path,
                )

                if not success:
                    # 如果有确认信息且有 agent，尝试确认
                    if confirm_info and agent and confirm_diff_idx is not None:
                        # 确认是否继续
                        confirmed = EditFileNormalTool._confirm_multiple_matches(
                            agent,
                            file_path,
                            original_content,
                            confirm_info["modified_content"],
                            confirm_info["match_count"],
                            confirm_info["search_text"],
                            confirm_info["replace_text"],
                        )
                        if confirmed:
                            # 确认继续，用户确认了要替换所有匹配
                            # 直接使用 confirm_info 中已生成的 modified_content（已包含所有匹配的替换）
                            result_or_error = confirm_info["modified_content"]
                            success = True
                            # 确认后成功，继续写入文件
                        else:
                            # 确认取消
                            if backup_path and os.path.exists(backup_path):
                                try:
                                    os.remove(backup_path)
                                except Exception:
                                    pass
                            all_results.append(
                                f"❌ {file_path}: 操作已取消（发现多处匹配，已确认不继续）"
                            )
                            failed_files.append(file_path)
                            overall_success = False
                            continue
                    else:
                        # 没有确认信息或没有 agent，直接失败
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
                    abs_path, result_or_error, backup_path
                )
                if write_success:
                    # 写入成功，删除备份文件
                    if backup_path and os.path.exists(backup_path):
                        try:
                            os.remove(backup_path)
                        except Exception:
                            pass
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
                return {
                    "success": False,
                    "stdout": stdout_text + ("\n\n" + summary if summary else ""),
                    "stderr": summary if summary else "部分文件修改失败",
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}


__all__ = ["EditFileNormalTool"]
