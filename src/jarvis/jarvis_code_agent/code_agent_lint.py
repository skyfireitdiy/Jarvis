"""CodeAgent 静态分析模块"""

import os
import shlex
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_code_agent.lint import LINT_AUTO_FIX_COMMANDS
from jarvis.jarvis_code_agent.lint import LINT_COMMAND_TEMPLATES_BY_FILE
from jarvis.jarvis_code_agent.lint import get_lint_commands_for_files
from jarvis.jarvis_code_agent.lint import group_commands_by_template
from jarvis.jarvis_utils.config import is_enable_static_analysis


class LintManager:
    """静态分析管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    @staticmethod
    def _clean_surrogates(text: str) -> str:
        """清理字符串中的 surrogate 字符

        Windows 下 subprocess 返回的输出可能包含 surrogates (U+DC80-U+DCFF),
        这些字符无法被 UTF-8 编码，会导致打印时抛出异常。
        此方法将 surrogates 替换为替换字符 。

        Args:
            text: 可能包含 surrogates 的字符串

        Returns:
            清理后的字符串
        """
        # 使用 encode 的 errors='replace' 参数将 surrogates 替换为 ?
        # 然后 decode 回字符串
        return text.encode("utf-8", errors="replace").decode("utf-8")

    def run_static_analysis(
        self, modified_files: List[str]
    ) -> List[Tuple[str, str, int, str]]:
        """执行静态分析

        Args:
            modified_files: 修改的文件列表

        Returns:
            [(file_path, command, returncode, output), ...] 格式的结果列表
            只返回有错误或警告的结果（returncode != 0）
        """
        if not modified_files:
            return []

        # 获取所有lint命令
        commands = get_lint_commands_for_files(modified_files, self.root_dir)
        if not commands:
            return []

        # 输出静态检查日志
        file_count = len(modified_files)
        files_str = ", ".join(os.path.basename(f) for f in modified_files[:3])
        if file_count > 3:
            files_str += f" 等{file_count}个文件"
        # 从命令中提取工具名（第一个单词）
        tool_names = list(set(cmd[1].split()[0] for cmd in commands if cmd[1].split()))
        tools_str = ", ".join(tool_names[:3])
        if len(tool_names) > 3:
            tools_str += f" 等{len(tool_names)}个工具"
        # 将静态检查信息反馈给LLM而不是输出给用户
        # PrettyOutput.auto_print("🔍 静态检查中...")

        results = []
        # 记录每个文件的检查结果
        file_results = []  # [(file_name, command, status, message), ...]

        # 按命令模板分组，相同工具可以批量执行
        grouped = group_commands_by_template(commands)

        for template_key, file_commands in grouped.items():
            for file_path, command in file_commands:
                file_name = os.path.basename(file_path)
                try:
                    # 检查文件是否存在
                    abs_file_path = (
                        os.path.join(self.root_dir, file_path)
                        if not os.path.isabs(file_path)
                        else file_path
                    )
                    if not os.path.exists(abs_file_path):
                        file_results.append((file_name, command, "跳过", "文件不存在"))
                        continue

                    # 仍然向用户显示执行的命令
                    PrettyOutput.auto_print(f"ℹ️ 执行: {command}")

                    # 执行命令（静态分析工具：ruff/mypy等，command来自配置）
                    result = subprocess.run(
                        command,
                        shell=True,  # nosec B602
                        cwd=self.root_dir,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=600,  # 600秒超时
                    )

                    # 只记录有错误或警告的结果
                    if result.returncode != 0:
                        output = result.stdout + result.stderr
                        if output.strip():  # 有输出才记录
                            results.append(
                                (
                                    file_path,
                                    command,
                                    result.returncode,
                                    output,
                                )
                            )
                            file_results.append(
                                (file_name, command, "失败", "发现问题")
                            )
                            # 失败时打印检查结果
                            output_preview = (
                                output[:2000] if len(output) > 2000 else output
                            )
                            # 清理可能存在的 surrogates 字符，避免 Windows 下编码异常
                            output_preview = self._clean_surrogates(output_preview)
                            PrettyOutput.auto_print(
                                f"⚠️ 检查失败 ({file_name}):\n{output_preview}"
                            )
                            if len(output) > 2000:
                                PrettyOutput.auto_print(
                                    f"⚠️ ... (输出已截断，共 {len(output)} 字符)"
                                )
                        else:
                            file_results.append((file_name, command, "通过", ""))
                    else:
                        file_results.append((file_name, command, "通过", ""))

                except subprocess.TimeoutExpired:
                    results.append((file_path, command, -1, "执行超时（600秒）"))
                    file_results.append(
                        (file_name, command, "超时", "执行超时（600秒）")
                    )
                    PrettyOutput.auto_print(
                        f"⚠️ 检查超时 ({file_name}): 执行超时（600秒）"
                    )
                except FileNotFoundError:
                    # 工具未安装，跳过
                    file_results.append((file_name, command, "跳过", "工具未安装"))
                    continue
                except Exception as e:
                    # 其他错误，记录但继续
                    # 清理异常消息中的 surrogates 字符
                    e_msg = self._clean_surrogates(str(e))
                    PrettyOutput.auto_print(
                        f"⚠执行lint命令失败: {command}, 错误: {e_msg}"
                    )
                    file_results.append(
                        (file_name, command, "失败", f"执行失败: {str(e)[:50]}")
                    )
                    continue

        # 一次性打印所有检查结果
        if file_results:
            total_files = len(file_results)
            passed_count = sum(
                1 for _, _, status, _ in file_results if status == "通过"
            )
            failed_count = sum(
                1 for _, _, status, _ in file_results if status == "失败"
            )
            timeout_count = sum(
                1 for _, _, status, _ in file_results if status == "超时"
            )
            sum(1 for _, _, status, _ in file_results if status == "跳过")

            # 收缩为一行的结果摘要
            summary = f"🔍 静态检查: {total_files}个文件"
            if failed_count > 0:
                summary += f", {failed_count}失败"
            if timeout_count > 0:
                summary += f", {timeout_count}超时"
            if passed_count == total_files:
                summary += " ✅全部通过"

            if failed_count > 0 or timeout_count > 0:
                PrettyOutput.auto_print(f"⚠️ {summary}")
            else:
                PrettyOutput.auto_print(f"✅ {summary}")
        else:
            PrettyOutput.auto_print("✅ 静态检查完成")

        return results

    def format_lint_results(self, results: List[Tuple[str, str, int, str]]) -> str:
        """格式化lint结果

        Args:
            results: [(file_path, command, returncode, output), ...]

        Returns:
            格式化的错误信息字符串
        """
        if not results:
            return ""

        lines = []
        for file_path, command, returncode, output in results:
            # 从命令中提取工具名（第一个单词）
            tool_name = command.split()[0] if command.split() else "unknown"
            lines.append(f"工具: {tool_name}")
            lines.append(f"文件: {file_path}")
            lines.append(f"命令: {command}")
            if returncode == -1:
                lines.append(f"错误: {output}")
            else:
                # 限制输出长度，避免过长
                output_preview = output[:1000] if len(output) > 1000 else output
                lines.append(f"输出:\n{output_preview}")
                if len(output) > 1000:
                    lines.append(f"... (输出已截断，共 {len(output)} 字符)")
            lines.append("")  # 空行分隔

        return "\n".join(lines)

    def _get_auto_fix_suggestions(
        self, lint_results: List[Tuple[str, str, int, str]]
    ) -> str:
        """根据lint结果生成自动修复建议

        Args:
            lint_results: [(file_path, command, returncode, output), ...]

        Returns:
            自动修复命令建议字符串，如果没有可用的自动修复工具则返回空字符串
        """
        # 收集所有涉及的文件和工具
        file_tool_map: Dict[str, set] = {}  # {file_path: set(tool_names)}
        for file_path, command, _, _ in lint_results:
            command_parts = command.split()
            tool_name = command_parts[0] if command_parts else "unknown"
            if file_path not in file_tool_map:
                file_tool_map[file_path] = set()
            file_tool_map[file_path].add(tool_name)

        # 生成自动修复命令
        suggestions = []
        for file_path, tool_names in file_tool_map.items():
            for tool_name in tool_names:
                # 查找该工具的自动修复命令
                auto_fix_cmds = LINT_AUTO_FIX_COMMANDS.get(tool_name, [])
                for cmd_template in auto_fix_cmds:
                    # 替换占位符
                    if "{file_path}" in cmd_template:
                        cmd = cmd_template.replace(
                            "{file_path}", shlex.quote(file_path)
                        )
                    else:
                        cmd = cmd_template
                    suggestions.append(f"  {cmd}")

        if suggestions:
            return "\n".join(suggestions)
        return ""

    def handle_static_analysis(
        self,
        modified_files: List[str],
        build_validation_result: Optional[Any],
        config: Any,
        agent: Any,
        final_ret: str,
    ) -> str:
        """处理静态分析

        Returns:
            更新后的结果字符串
        """
        # 检查是否启用静态分析
        if not is_enable_static_analysis():
            PrettyOutput.auto_print("ℹ️ 静态分析已禁用，跳过静态检查")
            return final_ret

        # 检查是否有可用的lint工具
        def get_lint_tool_names(file_path: str) -> List[str]:
            """获取文件的lint工具名称列表"""
            filename = os.path.basename(file_path)
            filename_lower = filename.lower()
            templates = LINT_COMMAND_TEMPLATES_BY_FILE.get(filename_lower, [])
            if not templates:
                ext = os.path.splitext(filename)[1]
                if ext:
                    templates = LINT_COMMAND_TEMPLATES_BY_FILE.get(ext.lower(), [])
            # 提取工具名（命令模板的第一个单词）
            return [
                template.split()[0] if template.split() else "unknown"
                for template in templates
            ]

        lint_tools_info = "\n".join(
            f"   - {file}: 使用 {'、'.join(get_lint_tool_names(file))}"
            for file in modified_files
            if get_lint_tool_names(file)
        )

        if not lint_tools_info:
            PrettyOutput.auto_print("ℹ️ 未找到可用的静态检查工具，跳过静态检查")
            return final_ret

        # 如果构建验证失败且未禁用，不进行静态分析（避免重复错误）
        # 如果构建验证已禁用，则进行静态分析（因为只做了基础静态检查）
        should_skip_static = (
            build_validation_result
            and not build_validation_result.success
            and not config.is_build_validation_disabled()
        )

        if should_skip_static:
            PrettyOutput.auto_print("ℹ️ 构建验证失败，跳过静态分析（避免重复错误）")
            return final_ret

        # 直接执行静态扫描
        lint_results = self.run_static_analysis(modified_files)
        if lint_results:
            # 有错误或警告，先检查是否有自动修复工具
            auto_fix_suggestions = self._get_auto_fix_suggestions(lint_results)

            # 打印自动修复建议
            if auto_fix_suggestions:
                PrettyOutput.auto_print(
                    f"💡 检测到静态检查告警，建议优先使用自动修复工具:\n{auto_fix_suggestions}"
                )

            # 打印完整的检查结果
            errors_summary = self.format_lint_results(lint_results)

            # 构建提示信息
            if auto_fix_suggestions:
                addon_prompt = f"""
静态扫描发现以下问题，建议优先使用自动修复工具处理:

{auto_fix_suggestions}

如果自动修复工具无法解决所有问题，再手动修复。静态检查详情:

{errors_summary}

请先尝试使用上述自动修复命令，然后再检查剩余问题。
                """
            else:
                addon_prompt = f"""
静态扫描发现以下问题，请根据错误信息修复代码:

{errors_summary}

请仔细检查并修复所有问题。
                """
            agent.set_addon_prompt(addon_prompt)
            final_ret += "\n\n⚠️ 静态扫描发现问题，已提示修复\n"
        else:
            final_ret += "\n\n✅ 静态扫描通过\n"

        return final_ret
