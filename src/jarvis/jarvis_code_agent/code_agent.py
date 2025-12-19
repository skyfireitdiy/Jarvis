"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import hashlib
import os

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import subprocess
import sys
from typing import Any, Optional

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
from jarvis.jarvis_code_agent.code_agent_build import BuildValidationManager
from jarvis.jarvis_code_agent.code_agent_diff import DiffManager
from jarvis.jarvis_code_agent.code_agent_git import GitManager
from jarvis.jarvis_code_agent.code_agent_impact import ImpactManager
from jarvis.jarvis_code_agent.code_agent_lint import LintManager
from jarvis.jarvis_code_agent.code_agent_llm import LLMManager
from jarvis.jarvis_code_agent.code_agent_postprocess import PostProcessManager
from jarvis.jarvis_code_agent.code_agent_prompts import get_system_prompt
from jarvis.jarvis_code_agent.code_agent_rules import RulesManager
from jarvis.jarvis_code_agent.code_analyzer import ContextManager
from jarvis.jarvis_code_agent.code_analyzer.llm_context_recommender import (
    ContextRecommender,
)
from jarvis.jarvis_code_agent.utils import get_project_overview
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_smart_model_name
from jarvis.jarvis_utils.config import is_confirm_before_apply_patch
from jarvis.jarvis_utils.config import is_enable_intent_recognition
from jarvis.jarvis_utils.config import set_config
from jarvis.jarvis_utils.git_utils import detect_large_code_deletion
from jarvis.jarvis_utils.git_utils import find_git_root_and_cd
from jarvis.jarvis_utils.git_utils import get_commits_between
from jarvis.jarvis_utils.git_utils import get_diff
from jarvis.jarvis_utils.git_utils import get_diff_between_commits
from jarvis.jarvis_utils.git_utils import get_diff_file_list
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash
from jarvis.jarvis_utils.git_utils import handle_commit_workflow
from jarvis.jarvis_utils.git_utils import revert_change
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import OutputType  # 保留用于语法高亮
from jarvis.jarvis_utils.utils import _acquire_single_instance_lock
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.globals import set_current_agent
from jarvis.jarvis_utils.globals import clear_current_agent

app = typer.Typer(help="Jarvis 代码助手")


class CodeAgent(Agent):
    """Jarvis系统的代码修改代理。

    负责处理代码分析、修改和git操作。
    """

    def __init__(
        self,
        model_group: Optional[str] = None,
        need_summary: bool = True,
        append_tools: Optional[str] = None,
        tool_group: Optional[str] = None,
        non_interactive: Optional[bool] = True,
        rule_names: Optional[str] = None,
        disable_review: bool = False,
        review_max_iterations: int = 0,
        enable_task_list_manager: bool = True,
        **kwargs: Any,
    ) -> None:
        self.root_dir = os.getcwd()
        self.tool_group = tool_group
        # 记录当前是否为非交互模式，便于在提示词/输入中动态调整行为说明
        self.non_interactive: bool = bool(non_interactive)
        # Review 相关配置
        self.disable_review = disable_review
        self.review_max_iterations = review_max_iterations

        # 存储开始时的commit hash，用于后续git diff获取
        self.start_commit: Optional[str] = None

        # 初始化上下文管理器
        self.context_manager = ContextManager(self.root_dir)
        # 上下文推荐器将在Agent创建后初始化（需要LLM模型）
        self.context_recommender: Optional[ContextRecommender] = None

        # 初始化各个管理器
        self.rules_manager = RulesManager(self.root_dir)

        # 加载rules
        _, self.loaded_rule_names = self.rules_manager.load_all_rules(rule_names)

        self.git_manager = GitManager(self.root_dir)
        self.diff_manager = DiffManager(self.root_dir)
        self.impact_manager = ImpactManager(self.root_dir, self.context_manager)
        self.build_validation_manager = BuildValidationManager(self.root_dir)
        self.lint_manager = LintManager(self.root_dir)
        self.post_process_manager = PostProcessManager(self.root_dir)
        # LLM管理器将在模型初始化后创建

        # 检测 git username 和 email 是否已设置
        self.git_manager.check_git_config()
        base_tools = [
            "execute_script",
            "read_code",
            "edit_file",  # 普通 search/replace 编辑
        ]
        if enable_task_list_manager:
            base_tools.append("task_list_manager")  # 任务列表管理工具

        if append_tools:
            additional_tools = [
                t for t in (tool.strip() for tool in append_tools.split(",")) if t
            ]
            base_tools.extend(additional_tools)
            # 去重
            base_tools = list(dict.fromkeys(base_tools))

        code_system_prompt = get_system_prompt()

        # 调用父类 Agent 的初始化
        # 默认禁用方法论和分析，但允许通过 kwargs 覆盖
        use_methodology = kwargs.pop("use_methodology", False)
        use_analysis = kwargs.pop("use_analysis", False)
        # name 使用传入的值，如果没有传入则使用默认值 "CodeAgent"
        name = kwargs.pop("name", "CodeAgent")

        # 准备显式传递给 super().__init__ 的参数
        # 注意：这些参数如果也在 kwargs 中，需要先移除，避免重复传递错误
        explicit_params = {
            "system_prompt": code_system_prompt,
            "name": name,
            "auto_complete": False,
            "model_group": model_group,
            "need_summary": need_summary,
            "use_methodology": use_methodology,
            "use_analysis": use_analysis,
            "non_interactive": non_interactive,
            "use_tools": base_tools,
        }

        # 自动移除所有显式传递的参数，避免重复传递错误
        # 这样以后添加新参数时，只要在 explicit_params 中声明，就会自动处理
        for key in explicit_params:
            kwargs.pop(key, None)

        super().__init__(
            **explicit_params,
            **kwargs,
        )

        self._agent_type = "code_agent"

        # 建立CodeAgent与Agent的关联，便于工具获取上下文管理器
        self._code_agent = self

        # 初始化上下文推荐器（自己创建LLM模型，使用父Agent的配置）
        try:
            # 获取当前Agent的model实例
            parent_model = None
            if self.model:
                parent_model = self.model

            self.context_recommender = ContextRecommender(
                self.context_manager, parent_model=parent_model
            )
        except Exception as e:
            # LLM推荐器初始化失败
            PrettyOutput.auto_print(
                f"⚠️ 上下文推荐器初始化失败: {e}，将跳过上下文推荐功能"
            )

        self.event_bus.subscribe(AFTER_TOOL_CALL, self._on_after_tool_call)

        # 打印语言功能支持表格
        try:
            from jarvis.jarvis_agent.language_support_info import (
                print_language_support_table,
            )

            print_language_support_table()
        except Exception:
            pass

    def get_rules_prompt(self) -> str:
        """
        获取rules加载的prompt
        """
        prompt, _ = self.rules_manager.load_all_rules(",".join(self.loaded_rule_names))
        return f"\n\n<rules>\n{prompt}</rules>\n"

    def _init_model(self, model_group: Optional[str]) -> None:
        """初始化模型平台（CodeAgent使用smart平台，适用于代码生成等复杂场景）"""
        model_name = get_smart_model_name(model_group)

        # 直接使用 get_smart_platform，避免先调用 create_platform 再回退导致的重复错误信息
        # get_smart_platform 内部会处理配置获取和平台创建
        self.model = PlatformRegistry().get_smart_platform(model_group)

        if model_name:
            self.model.set_model_name(model_name)

        self.model.set_model_group(model_group)
        self.model.set_suppress_output(False)

        # 初始化LLM管理器（使用普通模型，不使用smart模型）
        self.llm_manager = LLMManager(parent_model=self.model, model_group=model_group)
        # 同步模型组到全局，便于后续工具（如提交信息生成）获取一致的模型配置
        try:
            from jarvis.jarvis_utils.globals import set_global_model_group

            set_global_model_group(model_group)
        except Exception:
            # 若全局同步失败，不影响主流程
            pass

    def run(self, user_input: str, prefix: str = "", suffix: str = "") -> Optional[str]:
        """使用给定的用户输入运行代码代理.

        参数:
            user_input: 用户的需求/请求

        返回:
            str: 描述执行结果的输出，成功时返回None
        """
        try:
            set_current_agent(self.name, self)

            # 根据当前模式生成额外说明，供 LLM 感知执行策略
            prev_dir = os.getcwd()
            non_interactive_note = ""
            if getattr(self, "non_interactive", False):
                non_interactive_note = (
                    "\n\n[系统说明]\n"
                    "本次会话处于**非交互模式**：\n"
                    "- 在 PLAN 模式中给出清晰、可执行的详细计划后，应**自动进入 EXECUTE 模式执行计划**，不要等待用户额外确认；\n"
                    "- 在 EXECUTE 模式中，保持一步一步的小步提交和可回退策略，但不需要向用户反复询问“是否继续”；\n"
                    "- 如遇信息严重不足，可以在 RESEARCH 模式中自行补充必要分析，而不是卡在等待用户输入。\n"
                )

            self.git_manager.init_env(prefix, suffix, self)
            start_commit = get_latest_commit_hash()
            self.start_commit = start_commit

            # 将初始 commit 信息添加到 addon_prompt（安全回退点）
            if start_commit:
                initial_commit_prompt = f"""
**🔖 初始 Git Commit（安全回退点）**：
本次任务开始时的初始 commit 是：`{start_commit}`

**⚠️ 重要提示**：如果文件被破坏得很严重无法恢复，可以使用以下命令重置到这个初始 commit：
```bash
git reset --hard {start_commit}
```
这将丢弃所有未提交的更改，将工作区恢复到任务开始时的状态。请谨慎使用此命令，确保这是你真正想要的操作。
"""
                # 将初始 commit 信息追加到现有的 addon_prompt
                current_addon = self.session.addon_prompt or ""
                self.set_addon_prompt(
                    f"{current_addon}\n{initial_commit_prompt}".strip()
                )

            # 获取项目概况信息
            project_overview = get_project_overview(self.root_dir)

            first_tip = """请严格遵循以下规范进行代码修改任务：
            1. 每次响应仅执行一步操作，先分析再修改，避免一步多改。
            2. 充分利用工具理解用户需求和现有代码，禁止凭空假设。
            3. 如果不清楚要修改的文件，必须先分析并找出需要修改的文件，明确目标后再进行编辑。
            4. 对于简单的文本替换，推荐使用 edit_file 工具进行精确修改。避免使用 sed 命令，因为sed极易出错且可能产生不可预期的结果。对于复杂代码（超过50行或涉及多文件协调），禁止直接使用sed或python脚本编辑，必须使用task_list_manager创建任务列表进行安全拆分。
            5. 代码编辑任务优先使用 PATCH 操作，确保搜索文本在目标文件中有且仅有一次精确匹配，保证修改的准确性和安全性。
            6. 如需大范围重写（超过200行或涉及重构），请使用 edit_file 工具配合空search参数 ""，并提前备份原始文件。
            7. 如遇信息不明，优先调用工具补充分析，不要主观臆断。
            8. **重要：清理临时文件**：开发过程中产生的临时文件（如测试文件、调试脚本、备份文件、临时日志等）必须在提交前清理删除，否则会被自动提交到git仓库。如果创建了临时文件用于调试或测试，完成后必须立即删除。
            """

            # 智能上下文推荐：根据用户输入推荐相关上下文
            context_recommendation_text = ""
            if self.context_recommender and is_enable_intent_recognition():
                # 在意图识别和上下文推荐期间抑制模型输出
                was_suppressed = False
                if self.model:
                    was_suppressed = getattr(self.model, "_suppress_output", False)
                    self.model.set_suppress_output(True)
                try:
                    # 生成上下文推荐（基于关键词和项目上下文）
                    recommendation = self.context_recommender.recommend_context(
                        user_input=user_input,
                    )

                    # 格式化推荐结果
                    context_recommendation_text = (
                        self.context_recommender.format_recommendation(recommendation)
                    )
                except Exception:
                    # 上下文推荐失败不应该影响主流程
                    pass
                finally:
                    # 恢复模型输出设置
                    if self.model:
                        self.model.set_suppress_output(was_suppressed)

            if project_overview:
                enhanced_input = (
                    project_overview
                    + "\n\n"
                    + first_tip
                    + non_interactive_note
                    + context_recommendation_text
                    + "\n\n任务描述：\n"
                    + user_input
                )
            else:
                enhanced_input = (
                    first_tip
                    + non_interactive_note
                    + context_recommendation_text
                    + "\n\n任务描述：\n"
                    + user_input
                )

            try:
                if self.model:
                    self.model.set_suppress_output(False)
                result = super().run(enhanced_input)
                # 确保返回值是 str 或 None
                if result is None:
                    result_str = None
                else:
                    result_str = str(result)
            except RuntimeError as e:
                PrettyOutput.auto_print(f"⚠️ 执行失败: {str(e)}")
                return str(e)

            # 处理未提交的更改（在 review 之前先提交）
            self.git_manager.handle_uncommitted_changes()

            # 如果启用了 review，执行 review 和修复循环
            if not self.disable_review:
                self._review_and_fix(
                    user_input=user_input,
                    enhanced_input=enhanced_input,
                    prefix=prefix,
                    suffix=suffix,
                    code_generation_summary=result_str,
                )

            end_commit = get_latest_commit_hash()
            commits = self.git_manager.show_commit_history(
                self.start_commit, end_commit
            )
            self.git_manager.handle_commit_confirmation(
                commits,
                self.start_commit,
                prefix,
                suffix,
                self,
                self.post_process_manager.post_process_modified_files,
            )
            return result_str

        except RuntimeError as e:
            return f"Error during execution: {str(e)}"
        finally:
            # 在run方法结束时反注册agent
            clear_current_agent()

            # Ensure switching back to the original working directory after CodeAgent completes
            try:
                os.chdir(prev_dir)
            except Exception:
                pass

    def _on_after_tool_call(
        self,
        agent: Agent,
        current_response: Optional[str] = None,
        need_return: Optional[bool] = None,
        tool_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """工具调用后回调函数。"""

        final_ret = ""
        diff = get_diff()

        if diff:
            start_hash = get_latest_commit_hash()
            modified_files = get_diff_file_list()

            # 使用增强的 diff 可视化（如果可用）
            try:
                from jarvis.jarvis_code_agent.diff_visualizer import (
                    visualize_diff_enhanced,
                )
                from jarvis.jarvis_utils.config import get_diff_show_line_numbers
                from jarvis.jarvis_utils.config import get_diff_visualization_mode

                # 显示整体 diff（使用增强可视化）
                visualization_mode = get_diff_visualization_mode()
                show_line_numbers = get_diff_show_line_numbers()
                # 构建文件路径显示（多文件时显示所有文件名）
                file_path_display = ", ".join(modified_files) if modified_files else ""
                visualize_diff_enhanced(
                    diff,
                    file_path=file_path_display,
                    mode=visualization_mode,
                    show_line_numbers=show_line_numbers,
                )
            except ImportError:
                # 如果导入失败，回退到原有方式
                PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            except Exception as e:
                # 如果可视化失败，回退到原有方式
                PrettyOutput.auto_print(f"⚠️ Diff 可视化失败，使用默认方式: {e}")
                PrettyOutput.print(diff, OutputType.CODE, lang="diff")

            # 更新上下文管理器
            self.impact_manager.update_context_for_modified_files(modified_files)

            # 进行影响范围分析
            impact_report = self.impact_manager.analyze_edit_impact(modified_files)

            per_file_preview = self.diff_manager.build_per_file_patch_preview(
                modified_files, use_enhanced_visualization=False
            )

            # 所有模式下，在提交前检测大量代码删除并询问大模型
            detection_result = detect_large_code_deletion()
            if detection_result is not None:
                # 检测到大量代码删除，询问大模型是否合理
                is_reasonable = self.llm_manager.ask_llm_about_large_deletion(
                    detection_result, per_file_preview
                )
                if not is_reasonable:
                    # 大模型认为不合理，撤销修改
                    PrettyOutput.auto_print("ℹ️ 已撤销修改（大模型认为代码删除不合理）")
                    revert_change()
                    final_ret += (
                        "\n\n修改被撤销（检测到大量代码删除且大模型判断不合理）\n"
                    )
                    final_ret += f"# 补丁预览（按文件）:\n{per_file_preview}"
                    PrettyOutput.print(
                        final_ret, OutputType.USER, lang="markdown"
                    )  # 保留语法高亮
                    self.session.prompt += final_ret
                    return

            commited = handle_commit_workflow()
            if commited:
                # 统计代码行数变化
                # 获取diff的统计信息
                try:
                    diff_result = subprocess.run(
                        ["git", "diff", "HEAD~1", "HEAD", "--shortstat"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=True,
                    )
                    if diff_result.returncode == 0 and diff_result.stdout:
                        self.git_manager.record_code_changes_stats(diff_result.stdout)
                except subprocess.CalledProcessError:
                    pass

                # 统计修改次数
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("code_modifications", group="code_agent")

                # 获取提交信息
                end_hash = get_latest_commit_hash()
                commits = get_commits_between(start_hash, end_hash)

                # 添加提交信息到final_ret（按文件展示diff；删除文件仅提示）
                if commits:
                    # 获取最新的提交信息（commits列表按时间倒序，第一个是最新的）
                    latest_commit_hash, latest_commit_message = commits[0]
                    commit_short_hash = (
                        latest_commit_hash[:7]
                        if len(latest_commit_hash) >= 7
                        else latest_commit_hash
                    )

                    final_ret += (
                        f"\n\n代码已修改完成\n"
                        f"✅ 已自动提交\n"
                        f"   Commit ID: {commit_short_hash} ({latest_commit_hash})\n"
                        f"   提交信息: {latest_commit_message}\n"
                        f"\n补丁内容（按文件）:\n{per_file_preview}\n"
                    )

                    # 添加影响范围分析报告
                    final_ret = self.impact_manager.handle_impact_report(
                        impact_report, self, final_ret
                    )

                    # 构建验证
                    config = BuildValidationConfig(self.root_dir)
                    (
                        build_validation_result,
                        final_ret,
                    ) = self.build_validation_manager.handle_build_validation(
                        modified_files, self, final_ret
                    )

                    # 静态分析
                    final_ret = self.lint_manager.handle_static_analysis(
                        modified_files, build_validation_result, config, self, final_ret
                    )
                else:
                    # 如果没有获取到commits，尝试直接从end_hash获取commit信息
                    commit_info = ""
                    if end_hash:
                        try:
                            result = subprocess.run(
                                ["git", "log", "-1", "--pretty=format:%H|%s", end_hash],
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                check=False,
                            )
                            if (
                                result.returncode == 0
                                and result.stdout
                                and "|" in result.stdout
                            ):
                                (
                                    commit_hash,
                                    commit_message,
                                ) = result.stdout.strip().split("|", 1)
                                commit_short_hash = (
                                    commit_hash[:7]
                                    if len(commit_hash) >= 7
                                    else commit_hash
                                )
                                commit_info = (
                                    f"\n✅ 已自动提交\n"
                                    f"   Commit ID: {commit_short_hash} ({commit_hash})\n"
                                    f"   提交信息: {commit_message}\n"
                                )
                        except Exception:
                            pass

                    if commit_info:
                        final_ret += f"\n\n代码已修改完成{commit_info}\n"
                    else:
                        final_ret += "\n\n修改没有生效\n"
            else:
                final_ret += "\n修改被拒绝\n"
                final_ret += f"# 补丁预览（按文件）:\n{per_file_preview}"
        else:
            return
        # 用户确认最终结果
        if commited:
            self.session.prompt += final_ret
            return
        PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")  # 保留语法高亮
        if not is_confirm_before_apply_patch() or user_confirm(
            "是否使用此回复？", default=True
        ):
            self.session.prompt += final_ret
            return
        # 用户未确认，允许输入自定义回复作为附加提示
        custom_reply = get_multiline_input("请输入自定义回复")
        if custom_reply.strip():  # 如果自定义回复为空，不设置附加提示
            self.set_addon_prompt(custom_reply)
        self.session.prompt += final_ret
        return

    def _truncate_diff_for_review(self, git_diff: str, token_ratio: float = 0.4) -> str:
        """截断 git diff 以适应 token 限制（用于 review）

        参数:
            git_diff: 原始的 git diff 内容
            token_ratio: token 使用比例（默认 0.4，即 40%，review 需要更多上下文）

        返回:
            str: 截断后的 git diff（如果超出限制则截断并添加提示、文件列表和起始 commit）
        """
        if not git_diff or not git_diff.strip():
            return git_diff

        from jarvis.jarvis_utils.embedding import get_context_token_count
        from jarvis.jarvis_utils.config import get_max_input_token_count

        # 获取最大输入 token 数量
        model_group = self.model.model_group if self.model else None
        try:
            max_input_tokens = get_max_input_token_count(model_group)
        except Exception:
            # 如果获取失败，使用默认值（约 100000 tokens）
            max_input_tokens = 100000

        # 使用指定比例作为 diff 的 token 限制
        max_diff_tokens = int(max_input_tokens * token_ratio)

        # 计算 diff 的 token 数量
        diff_token_count = get_context_token_count(git_diff)

        if diff_token_count <= max_diff_tokens:
            return git_diff

        # 如果 diff 内容太大，进行截断
        # 先提取修改的文件列表和起始 commit
        import re

        files = set()
        # 匹配 "diff --git a/path b/path" 格式
        pattern = r"^diff --git a/([^\s]+) b/([^\s]+)$"
        for line in git_diff.split("\n"):
            match = re.match(pattern, line)
            if match:
                file_a = match.group(1)
                file_b = match.group(2)
                files.add(file_b)
                if file_a != file_b:
                    files.add(file_a)
        modified_files = sorted(list(files))

        # 获取起始 commit id
        start_commit = self.start_commit if hasattr(self, "start_commit") else None

        lines = git_diff.split("\n")
        truncated_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = get_context_token_count(line)
            if current_tokens + line_tokens > max_diff_tokens:
                # 添加截断提示
                truncated_lines.append("")
                truncated_lines.append(
                    "# ⚠️ diff内容过大，已截断显示（review 需要更多上下文）"
                )
                truncated_lines.append(
                    f"# 原始diff共 {len(lines)} 行，{diff_token_count} tokens"
                )
                truncated_lines.append(
                    f"# 显示前 {len(truncated_lines) - 3} 行，约 {current_tokens} tokens"
                )
                truncated_lines.append(
                    f"# 限制: {max_diff_tokens} tokens (输入窗口的 {token_ratio * 100:.0f}%)"
                )

                # 添加起始 commit id
                if start_commit:
                    truncated_lines.append("")
                    truncated_lines.append(f"# 起始 Commit ID: {start_commit}")

                # 添加完整修改文件列表
                if modified_files:
                    truncated_lines.append("")
                    truncated_lines.append(
                        f"# 完整修改文件列表（共 {len(modified_files)} 个文件）："
                    )
                    for file_path in modified_files:
                        truncated_lines.append(f"#   - {file_path}")

                break

            truncated_lines.append(line)
            current_tokens += line_tokens

        return "\n".join(truncated_lines)

    def _build_review_prompts(
        self,
        user_input: str,
        git_diff: str,
        code_generation_summary: Optional[str] = None,
    ) -> tuple:
        """构建 review Agent 的 prompts

        参数:
            user_input: 用户原始需求
            git_diff: 代码修改的 git diff（会自动进行 token 限制处理）

        返回:
            tuple: (system_prompt, user_prompt, summary_prompt)
        """
        system_prompt = """你是代码审查专家。你的任务是审查代码修改是否正确完成了用户需求。

审查标准：
1. 功能完整性：代码修改是否完整实现了用户需求的所有功能点？
2. 代码正确性：修改的代码逻辑是否正确，有无明显的 bug 或错误？
3. 代码质量：代码是否符合最佳实践，有无明显的代码异味？
4. 潜在风险：修改是否可能引入新的问题或破坏现有功能？

审查要求：
- 仔细阅读用户需求、代码生成总结（summary）和代码修改（git diff）
- **对代码生成总结中的关键信息进行充分验证**：不能盲目信任总结，必须结合 git diff 和实际代码逐条核对
- 如需了解更多上下文，必须使用 read_code 工具读取相关文件以验证总结中提到的行为/位置/文件是否真实存在并符合描述
- 基于实际代码进行审查，不要凭空假设
- 如果代码生成总结与实际代码不一致，应以实际代码为准，并将不一致情况作为问题记录
- 只关注本次修改相关的问题，不要审查无关代码"""

        user_prompt = f"""请审查以下代码修改是否正确完成了用户需求。

【用户需求】
{user_input}

【代码生成总结】
{code_generation_summary if code_generation_summary else "无代码生成总结信息（如为空，说明主 Agent 未生成总结，请完全依赖 git diff 和实际代码进行审查）"}

【代码修改（Git Diff）】
```diff
{git_diff}

```

请仔细审查代码修改，并特别注意：
- 不要直接相信代码生成总结中的描述，而是将其视为“待核实的说明”
- 对总结中提到的每一个关键修改点（如函数/文件/行为变化），都应在 git diff 或实际代码中找到对应依据
- 如发现总结与实际代码不一致，必须在审查结果中指出

如需要可使用 read_code 工具查看更多上下文。

如果审查完毕，直接输出 {ot("!!!COMPLETE!!!")}，不要输出其他任何内容。
"""

        summary_prompt = """请输出 JSON 格式的审查结果，格式如下：

```json
{
  "ok": true/false,  // 审查是否通过
  "issues": [        // 发现的问题列表（如果 ok 为 true，可以为空数组）
    {
      "type": "问题类型",  // 如：功能缺失、逻辑错误、代码质量、潜在风险
      "description": "问题描述",
      "location": "问题位置（文件:行号）",
      "suggestion": "修复建议"
    }
  ],
  "summary": "审查总结"  // 简要说明审查结论
}
```

注意：
- 如果代码修改完全满足用户需求且无明显问题，设置 ok 为 true
- 如果存在需要修复的问题，设置 ok 为 false，并在 issues 中列出所有问题
- 每个问题都要提供具体的修复建议"""

        return system_prompt, user_prompt, summary_prompt

    def _parse_review_result(
        self, summary: str, review_agent: Optional[Any] = None, max_retries: int = 3
    ) -> dict:
        """解析 review 结果

        参数:
            summary: review Agent 的输出
            review_agent: review Agent 实例，用于格式修复
            max_retries: 最大重试次数

        返回:
            dict: 解析后的审查结果，包含 ok 和 issues 字段
        """
        import json
        import re

        def _try_parse_json(content: str) -> tuple[bool, dict | None, str | None]:
            """尝试解析JSON，返回(成功, 结果, json字符串)"""
            # 尝试从输出中提取 JSON
            # 首先尝试匹配 ```json ... ``` 代码块
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # 尝试匹配裸 JSON 对象
                json_match = re.search(r'\{[\s\S]*"ok"[\s\S]*\}', content)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    return False, None, None

            try:
                result = json.loads(json_str)
                if isinstance(result, dict):
                    return True, result, json_str
                else:
                    return False, None, json_str
            except json.JSONDecodeError:
                return False, None, json_str

        # 第一次尝试解析
        success, result, json_str = _try_parse_json(summary)
        if success and result is not None:
            return {
                "ok": result.get("ok", True),
                "issues": result.get("issues", []),
                "summary": result.get("summary", ""),
            }

        # 如果没有提供review_agent，无法修复，返回默认值
        if review_agent is None:
            PrettyOutput.auto_print("⚠️ 无法解析 review 结果，且无法修复格式")
            return {"ok": True, "issues": [], "summary": "无法解析审查结果"}

        # 尝试修复格式
        for retry in range(max_retries):
            PrettyOutput.auto_print(
                f"🔧 第 {retry + 1}/{max_retries} 次尝试修复 JSON 格式..."
            )

            fix_prompt = f"""
之前的review回复格式不正确，无法解析为有效的JSON格式。

原始回复内容：
```
{summary}
```

请严格按照以下JSON格式重新组织你的回复：

```json
{{
    "ok": true/false,  // 表示代码是否通过审查
    "summary": "总体评价和建议",  // 简短总结
    "issues": [  // 问题列表，如果没有问题则为空数组
        {{
            "type": "问题类型",  // 如: bug, style, performance, security等
            "description": "问题描述",
            "location": "问题位置",  // 文件名和行号
            "suggestion": "修复建议"
        }}
    ]
}}
```

确保回复只包含上述JSON格式，不要包含其他解释或文本。"""

            try:
                # 使用review_agent的底层model进行修复，保持review_agent的专用配置和系统prompt
                fixed_summary = review_agent.model.chat_until_success(fix_prompt)
                if fixed_summary:
                    success, result, _ = _try_parse_json(str(fixed_summary))
                    if success and result is not None:
                        PrettyOutput.auto_print(
                            f"✅ JSON格式修复成功（第 {retry + 1} 次）"
                        )
                        return {
                            "ok": result.get("ok", True),
                            "issues": result.get("issues", []),
                            "summary": result.get("summary", ""),
                        }
                    else:
                        PrettyOutput.auto_print("⚠️ 修复后的格式仍不正确，继续尝试...")
                        summary = str(fixed_summary)  # 使用修复后的内容继续尝试
                else:
                    PrettyOutput.auto_print("⚠️ 修复请求无响应")

            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 修复过程中出错: {e}")

        # 3次修复都失败，标记需要重新review
        PrettyOutput.auto_print("❌ JSON格式修复失败，需要重新进行review")
        return {
            "ok": False,
            "issues": [],
            "summary": "JSON_FORMAT_ERROR",
            "need_re_review": True,
        }

    def _review_and_fix(
        self,
        user_input: str,
        enhanced_input: str,
        prefix: str = "",
        suffix: str = "",
        code_generation_summary: Optional[str] = None,
    ) -> None:
        """执行 review 和修复循环

        参数:
            user_input: 用户原始需求
            enhanced_input: 增强后的用户输入（用于修复）
            prefix: 前缀
            suffix: 后缀
        """
        from jarvis.jarvis_agent import Agent

        iteration = 0
        max_iterations = self.review_max_iterations
        # 如果 max_iterations 为 0，表示无限 review
        is_infinite = max_iterations == 0

        while is_infinite or iteration < max_iterations:
            iteration += 1

            # 获取从开始到当前的 git diff（提前检测是否有代码修改）
            current_commit = get_latest_commit_hash()
            if self.start_commit is None or current_commit == self.start_commit:
                git_diff = get_diff()  # 获取未提交的更改
            else:
                git_diff = get_diff_between_commits(self.start_commit, current_commit)

            if not git_diff or not git_diff.strip():
                PrettyOutput.auto_print("ℹ️ 没有代码修改，跳过审查")
                return

            # 每轮审查开始前显示清晰的提示信息
            if not self.non_interactive:
                if is_infinite:
                    PrettyOutput.auto_print(
                        f"\n🔄 代码审查循环 - 第 {iteration} 轮（无限模式）"
                    )
                else:
                    PrettyOutput.auto_print(
                        f"\n🔄 代码审查循环 - 第 {iteration}/{max_iterations} 轮"
                    )
                if not user_confirm("是否开始本轮代码审查？", default=True):
                    PrettyOutput.auto_print("ℹ️ 用户终止了代码审查")
                    return
            else:
                if is_infinite:
                    PrettyOutput.auto_print(
                        f"\n🔍 开始第 {iteration} 轮代码审查...（无限模式）"
                    )
                else:
                    PrettyOutput.auto_print(
                        f"\n🔍 开始第 {iteration}/{max_iterations} 轮代码审查..."
                    )

            # 对 git diff 进行 token 限制处理（review 需要更多上下文，使用 40% 的 token 比例）
            truncated_git_diff = self._truncate_diff_for_review(
                git_diff, token_ratio=0.4
            )
            if truncated_git_diff != git_diff:
                PrettyOutput.auto_print("⚠️ Git diff 内容过大，已截断以适应 token 限制")

            # 构建 review prompts
            sys_prompt, usr_prompt, sum_prompt = self._build_review_prompts(
                user_input, truncated_git_diff, code_generation_summary
            )

            review_agent = Agent(
                system_prompt=sys_prompt,
                name=f"CodeReview-Agent-{iteration}",
                model_group=self.model.model_group if self.model else None,
                summary_prompt=sum_prompt,
                need_summary=True,
                auto_complete=True,
                use_tools=[
                    "execute_script",
                    "read_code",
                    "save_memory",
                    "retrieve_memory",
                    "clear_memory",
                    "methodology",
                ],
                non_interactive=self.non_interactive,
                use_methodology=True,
                use_analysis=True,
            )

            # 运行 review
            summary = review_agent.run(usr_prompt)

            # 解析审查结果，支持格式修复和重新review
            result = self._parse_review_result(
                str(summary) if summary else "", review_agent=review_agent
            )

            # 检查是否需要重新review（JSON格式错误3次修复失败）
            if result.get("need_re_review", False):
                PrettyOutput.auto_print(
                    f"\n🔄 JSON格式修复失败，重新进行代码审查（第 {iteration} 轮）"
                )
                # 跳过当前迭代，重新开始review流程
                continue

            if result["ok"]:
                PrettyOutput.auto_print(f"\n✅ 代码审查通过（第 {iteration} 轮）")
                if result.get("summary"):
                    PrettyOutput.auto_print(f"   {result['summary']}")
                return

            # 审查未通过，需要修复
            PrettyOutput.auto_print(f"\n⚠️ 代码审查发现问题（第 {iteration} 轮）：")
            for i, issue in enumerate(result.get("issues", []), 1):
                issue_type = issue.get("type", "未知")
                description = issue.get("description", "无描述")
                location = issue.get("location", "未知位置")
                suggestion = issue.get("suggestion", "无建议")
                PrettyOutput.auto_print(f"   {i}. [{issue_type}] {description}")
                PrettyOutput.auto_print(f"      位置: {location}")
                PrettyOutput.auto_print(f"      建议: {suggestion}")

            # 在每轮审查后给用户一个终止选择
            if not self.non_interactive:
                if not user_confirm("是否继续修复这些问题？", default=True):
                    PrettyOutput.auto_print("ℹ️ 用户选择终止审查，保持当前代码状态")
                    return

            # 只有在非无限模式下才检查是否达到最大迭代次数
            if not is_infinite and iteration >= max_iterations:
                PrettyOutput.auto_print(
                    f"\n⚠️ 已达到最大审查次数 ({max_iterations})，停止审查"
                )
                # 在非交互模式下直接返回，交互模式下询问用户
                if not self.non_interactive:
                    if not user_confirm("是否继续修复？", default=False):
                        return
                    # 用户选择继续，重置迭代次数
                    iteration = 0
                    max_iterations = self.review_max_iterations
                    is_infinite = max_iterations == 0
                else:
                    return

            # 构建修复 prompt
            fix_prompt = f"""代码审查发现以下问题，请修复：

【审查结果】
{result.get("summary", "")}

【问题列表】
"""
            for i, issue in enumerate(result.get("issues", []), 1):
                fix_prompt += f"{i}. [{issue.get('type', '未知')}] {issue.get('description', '')}\n"
                fix_prompt += f"   位置: {issue.get('location', '')}\n"
                fix_prompt += f"   建议: {issue.get('suggestion', '')}\n\n"

            fix_prompt += "\n请根据上述问题进行修复，确保代码正确实现用户需求。"

            PrettyOutput.auto_print("\n🔧 开始修复问题...")

            # 调用 super().run() 进行修复
            try:
                if self.model:
                    self.model.set_suppress_output(False)
                super().run(fix_prompt)
            except RuntimeError as e:
                PrettyOutput.auto_print(f"⚠️ 修复失败: {str(e)}")
                return

            # 处理未提交的更改
            self.git_manager.handle_uncommitted_changes()

    def add_runtime_rule(self, rule_name: str) -> None:
        """添加运行时加载的规则到跟踪列表

        用于记录通过builtin_input_handler等方式动态加载的规则，
        确保这些规则能够被后续的子代理继承。

        参数:
            rule_name: 规则名称
        """
        if not rule_name or not isinstance(rule_name, str):
            return

        # 同时更新完整规则集合（自动去重）
        self.loaded_rule_names.add(rule_name)

        # 防止rule_name无效
        _, self.loaded_rule_names = self.rules_manager.load_all_rules(
            ",".join(self.loaded_rule_names)
        )


@app.command()
def cli(
    model_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    tool_group: Optional[str] = typer.Option(
        None, "-G", "--tool-group", help="使用的工具组，覆盖配置文件中的设置"
    ),
    config_file: Optional[str] = typer.Option(
        None, "-f", "--config", help="配置文件路径"
    ),
    requirement: Optional[str] = typer.Option(
        None, "-r", "--requirement", help="要处理的需求描述"
    ),
    append_tools: Optional[str] = typer.Option(
        None, "--append-tools", help="要追加的工具列表，用逗号分隔"
    ),
    restore_session: bool = typer.Option(
        False,
        "--restore-session",
        help="从 .jarvis/saved_session.json 恢复会话状态",
    ),
    prefix: str = typer.Option(
        "",
        "--prefix",
        help="提交信息前缀（用空格分隔）",
    ),
    suffix: str = typer.Option(
        "",
        "--suffix",
        help="提交信息后缀（用换行分隔）",
    ),
    non_interactive: bool = typer.Option(
        False,
        "-n",
        "--non-interactive",
        help="启用非交互模式：用户无法与命令交互，脚本执行超时限制为5分钟",
    ),
    rule_names: Optional[str] = typer.Option(
        None,
        "--rule-names",
        help="指定规则名称列表，用逗号分隔，从 rules.yaml 文件中读取对应的规则内容",
    ),
    disable_review: bool = typer.Option(
        False,
        "--disable-review",
        help="启用代码审查：在代码修改完成后自动进行代码审查，发现问题则自动修复",
    ),
    review_max_iterations: int = typer.Option(
        0,
        "--review-max-iterations",
        help="代码审查最大迭代次数，达到上限后停止审查（默认3次）",
    ),
) -> None:
    """Jarvis主入口点。"""
    # 非交互模式要求从命令行传入任务
    if non_interactive and not (requirement and str(requirement).strip()):
        PrettyOutput.auto_print(
            "❌ 非交互模式已启用：必须使用 --requirement 传入任务内容，因多行输入不可用。"
        )
        raise typer.Exit(code=2)
    init_env(
        "欢迎使用 Jarvis-CodeAgent，您的代码工程助手已准备就绪！",
        config_file=config_file,
    )
    # CodeAgent 单实例互斥：改为按仓库维度加锁（延后至定位仓库根目录后执行）
    # 锁的获取移动到确认并切换到git根目录之后

    # 在初始化环境后同步 CLI 选项到全局配置，避免被 init_env 覆盖
    try:
        if model_group:
            set_config("llm_group", str(model_group))
        if tool_group:
            set_config("tool_group", str(tool_group))
        if restore_session:
            set_config("restore_session", True)
    except Exception:
        # 静默忽略同步异常，不影响主流程
        pass

    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        curr_dir_path = os.getcwd()
        PrettyOutput.auto_print(f"⚠️ 警告：当前目录 '{curr_dir_path}' 不是一个git仓库。")
        init_git = (
            True
            if non_interactive
            else user_confirm(
                f"是否要在 '{curr_dir_path}' 中初始化一个新的git仓库？", default=True
            )
        )
        if init_git:
            try:
                subprocess.run(
                    ["git", "init"],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                PrettyOutput.auto_print("✅ 已成功初始化git仓库。")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                PrettyOutput.auto_print(f"❌ 初始化git仓库失败: {e}")
                sys.exit(1)
        else:
            PrettyOutput.auto_print("ℹ️ 操作已取消。Jarvis需要在git仓库中运行。")
            sys.exit(0)

    curr_dir = os.getcwd()
    find_git_root_and_cd(curr_dir)
    # 在定位到 git 根目录后，按仓库维度加锁，避免跨仓库互斥
    try:
        repo_root = os.getcwd()
        lock_name = (
            f"code_agent_{hashlib.md5(repo_root.encode('utf-8')).hexdigest()}.lock"
        )
        _acquire_single_instance_lock(lock_name=lock_name)
    except Exception:
        # 回退到全局锁，确保至少有互斥保护
        _acquire_single_instance_lock(lock_name="code_agent.lock")
    try:
        agent = CodeAgent(
            model_group=model_group,
            need_summary=False,
            append_tools=append_tools,
            tool_group=tool_group,
            non_interactive=non_interactive,
            rule_names=rule_names,
            disable_review=disable_review,
            review_max_iterations=review_max_iterations,
        )

        # 显示可用的规则信息
        _print_available_rules(agent.rules_manager, rule_names)

        # 尝试恢复会话
        if restore_session:
            if agent.restore_session():
                PrettyOutput.auto_print("✅ 已从 .jarvis/saved_session.json 恢复会话。")
            else:
                PrettyOutput.auto_print(
                    "⚠️ 无法从 .jarvis/saved_session.json 恢复会话。"
                )

        if requirement:
            agent.run(requirement, prefix=prefix, suffix=suffix)
            if agent.non_interactive:
                raise typer.Exit(code=0)
        else:
            while True:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    raise typer.Exit(code=0)
                agent.run(user_input, prefix=prefix, suffix=suffix)
                if agent.non_interactive:
                    raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {str(e)}")
        sys.exit(1)


def _print_available_rules(
    rules_manager: RulesManager, rule_names: Optional[str] = None
) -> None:
    """打印可用的规则信息

    参数:
        rules_manager: 规则管理器实例
        rule_names: 用户指定的规则名称列表（逗号分隔）
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text

        console = Console()

        # 获取所有可用规则
        all_rules = rules_manager.get_all_available_rule_names()
        builtin_rules = all_rules.get("builtin", [])
        file_rules = all_rules.get("files", [])
        yaml_rules = all_rules.get("yaml", [])

        # 获取已加载的规则
        loaded_rules = []
        if rule_names:
            rule_list = [name.strip() for name in rule_names.split(",") if name.strip()]
            for rule_name in rule_list:
                if rules_manager.get_named_rule(rule_name):
                    loaded_rules.append(rule_name)

        # 检查项目规则和全局规则
        has_project_rule = rules_manager.read_project_rule() is not None
        has_global_rule = rules_manager.read_global_rules() is not None

        # 构建规则信息内容
        content_parts = []

        # 显示所有规则（按来源分类）
        has_any_rules = False

        # 内置规则
        if builtin_rules:
            has_any_rules = True
            builtin_text = Text()
            builtin_text.append("📚 内置规则 ", style="bold cyan")
            builtin_text.append(f"({len(builtin_rules)} 个): ", style="dim")
            for i, rule in enumerate(builtin_rules):
                if i > 0:
                    builtin_text.append(", ", style="dim")
                builtin_text.append(rule, style="yellow")
            content_parts.append(builtin_text)

        # 用户自定义规则
        user_custom_rules = file_rules + yaml_rules
        if user_custom_rules:
            has_any_rules = True
            user_text = Text()
            user_text.append("👤 用户自定义规则 ", style="bold green")
            user_text.append(f"({len(user_custom_rules)} 个): ", style="dim")

            # 分别显示文件规则和YAML规则
            custom_rules_parts = []
            if file_rules:
                file_part = Text()
                file_part.append("文件规则: ", style="blue")
                for i, rule in enumerate(file_rules):
                    if i > 0:
                        file_part.append(", ", style="dim")
                    file_part.append(rule, style="cyan")
                custom_rules_parts.append(file_part)

            if yaml_rules:
                yaml_part = Text()
                yaml_part.append("YAML规则: ", style="magenta")
                for i, rule in enumerate(yaml_rules):
                    if i > 0:
                        yaml_part.append(", ", style="dim")
                    yaml_part.append(rule, style="magenta")
                custom_rules_parts.append(yaml_part)

            # 合并显示自定义规则
            for i, part in enumerate(custom_rules_parts):
                if i > 0:
                    user_text.append(" | ", style="dim")
                user_text.append(part)

            content_parts.append(user_text)

        # 分别显示详细的文件规则和YAML规则（保留原有详细信息）
        if file_rules:
            has_any_rules = True
            file_text = Text()
            file_text.append("📄 详细文件规则 ", style="bold blue")
            file_text.append(f"({len(file_rules)} 个): ", style="dim")
            for i, rule in enumerate(file_rules):
                if i > 0:
                    file_text.append(", ", style="dim")
                file_text.append(rule, style="cyan")
            content_parts.append(file_text)

        if yaml_rules:
            has_any_rules = True
            yaml_text = Text()
            yaml_text.append("📝 详细YAML规则 ", style="bold magenta")
            yaml_text.append(f"({len(yaml_rules)} 个): ", style="dim")
            for i, rule in enumerate(yaml_rules):
                if i > 0:
                    yaml_text.append(", ", style="dim")
                yaml_text.append(rule, style="magenta")
            content_parts.append(yaml_text)

        # 如果没有规则，显示提示
        if not has_any_rules:
            no_rules_text = Text()
            no_rules_text.append("ℹ️ 当前没有可用的规则", style="dim")
            content_parts.append(no_rules_text)

        # 提示信息
        if has_any_rules:
            tip_text = Text()
            tip_text.append("💡 提示: ", style="bold green")
            tip_text.append("使用 ", style="dim")
            tip_text.append("--rule-names", style="bold yellow")
            tip_text.append(" 参数加载规则，例如: ", style="dim")
            tip_text.append("--rule-names tdd,clean_code", style="bold yellow")
            tip_text.append("\n   或使用 ", style="dim")
            tip_text.append("@", style="bold yellow")
            tip_text.append(" 触发规则加载，例如: ", style="dim")
            tip_text.append("@tdd @clean_code", style="bold yellow")
            content_parts.append(tip_text)

        # 显示已加载的规则
        if loaded_rules:
            loaded_text = Text()
            loaded_text.append("✅ 已加载规则: ", style="bold green")
            for i, rule in enumerate(loaded_rules):
                if i > 0:
                    loaded_text.append(", ", style="dim")
                loaded_text.append(rule, style="bold yellow")
            content_parts.append(loaded_text)

        # 显示项目规则和全局规则
        if has_project_rule or has_global_rule:
            rule_files_text = Text()
            if has_project_rule:
                rule_files_text.append("📁 项目规则: ", style="bold blue")
                rule_files_text.append(".jarvis/rule", style="dim")
                if has_global_rule:
                    rule_files_text.append(" | ", style="dim")
            if has_global_rule:
                rule_files_text.append("🌐 全局规则: ", style="bold magenta")
                rule_files_text.append("~/.jarvis/rule", style="dim")
            content_parts.append(rule_files_text)

        # 如果有规则信息，使用 Panel 打印
        if content_parts:
            from rich.console import Group

            # 创建内容组
            content_group = Group(*content_parts)

            # 创建 Panel
            panel = Panel(
                content_group,
                title="📋 规则信息",
                title_align="center",
                border_style="cyan",
                padding=(0, 1),
            )

            console.print(panel)
    except Exception as e:
        # 显示错误信息而不是静默失败
        PrettyOutput.auto_print(f"⚠️ 规则信息显示失败: {e}")
        import traceback

        traceback.print_exc()


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
