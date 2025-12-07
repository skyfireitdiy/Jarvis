# -*- coding: utf-8 -*-
"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import os
import subprocess
import sys
import hashlib
from typing import Optional

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_code_agent.code_analyzer import ContextManager
from jarvis.jarvis_code_agent.code_analyzer.llm_context_recommender import (
    ContextRecommender,
)
from jarvis.jarvis_code_agent.code_agent_prompts import get_system_prompt
from jarvis.jarvis_code_agent.code_agent_rules import RulesManager
from jarvis.jarvis_code_agent.code_agent_git import GitManager
from jarvis.jarvis_code_agent.code_agent_diff import DiffManager
from jarvis.jarvis_code_agent.code_agent_impact import ImpactManager
from jarvis.jarvis_code_agent.code_agent_build import BuildValidationManager
from jarvis.jarvis_code_agent.code_agent_lint import LintManager
from jarvis.jarvis_code_agent.code_agent_postprocess import PostProcessManager
from jarvis.jarvis_code_agent.code_agent_llm import LLMManager
from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
from jarvis.jarvis_utils.config import (
    is_confirm_before_apply_patch,
    is_enable_intent_recognition,
    set_config,
    get_smart_platform_name,
    get_smart_model_name,
)
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_code_agent.utils import get_project_overview
from jarvis.jarvis_utils.git_utils import (
    detect_large_code_deletion,
    find_git_root_and_cd,
    get_commits_between,
    get_diff,
    get_diff_file_list,
    get_latest_commit_hash,
    handle_commit_workflow,
    revert_change,
)
from jarvis.jarvis_utils.input import get_multiline_input, user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput  # 保留用于语法高亮
from jarvis.jarvis_utils.utils import init_env, _acquire_single_instance_lock

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
        non_interactive: Optional[bool] = None,
        rule_names: Optional[str] = None,
        **kwargs,
    ):
        self.root_dir = os.getcwd()
        self.tool_group = tool_group
        # 记录当前是否为非交互模式，便于在提示词/输入中动态调整行为说明
        self.non_interactive: bool = bool(non_interactive)

        # 初始化上下文管理器
        self.context_manager = ContextManager(self.root_dir)
        # 上下文推荐器将在Agent创建后初始化（需要LLM模型）
        self.context_recommender: Optional[ContextRecommender] = None

        # 初始化各个管理器
        self.rules_manager = RulesManager(self.root_dir)
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
            "rewrite_file",
            "lsp_client",  # LSP客户端工具，用于获取代码补全、悬停等信息
            "task_list_manager",  # 任务列表管理工具
        ]

        if append_tools:
            additional_tools = [
                t for t in (tool.strip() for tool in append_tools.split(",")) if t
            ]
            base_tools.extend(additional_tools)
            # 去重
            base_tools = list(dict.fromkeys(base_tools))

        code_system_prompt = get_system_prompt()
        # 加载所有规则
        merged_rules, loaded_rule_names = self.rules_manager.load_all_rules(rule_names)

        if merged_rules:
            code_system_prompt = (
                f"{code_system_prompt}\n\n<rules>\n{merged_rules}\n</rules>"
            )
            # 显示加载的规则名称
            if loaded_rule_names:
                rules_display = ", ".join(loaded_rule_names)
                print(f"ℹ️ 已加载规则: {rules_display}")

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
            print(f"⚠️ 上下文推荐器初始化失败: {e}，将跳过上下文推荐功能")

        self.event_bus.subscribe(AFTER_TOOL_CALL, self._on_after_tool_call)

        # 打印语言功能支持表格
        try:
            from jarvis.jarvis_agent.language_support_info import (
                print_language_support_table,
            )

            print_language_support_table()
        except Exception:
            pass

    def _init_model(self, model_group: Optional[str]):
        """初始化模型平台（CodeAgent使用smart平台，适用于代码生成等复杂场景）"""
        platform_name = get_smart_platform_name(model_group)
        model_name = get_smart_model_name(model_group)

        maybe_model = PlatformRegistry().create_platform(platform_name)
        if maybe_model is None:
            print(f"⚠️ 平台 {platform_name} 不存在，将使用smart模型")
            maybe_model = PlatformRegistry().get_smart_platform()

        # 在此处收敛为非可选类型，确保后续赋值满足类型检查
        self.model = maybe_model

        if model_name:
            self.model.set_model_name(model_name)

        self.model.set_model_group(model_group)
        self.model.set_suppress_output(False)

        # 初始化LLM管理器
        self.llm_manager = LLMManager(self.model)

    def run(self, user_input: str, prefix: str = "", suffix: str = "") -> Optional[str]:
        """使用给定的用户输入运行代码代理.

        参数:
            user_input: 用户的需求/请求

        返回:
            str: 描述执行结果的输出，成功时返回None
        """
        prev_dir = os.getcwd()
        try:
            # 根据当前模式生成额外说明，供 LLM 感知执行策略
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

            # 获取项目概况信息
            project_overview = get_project_overview(self.root_dir)

            first_tip = """请严格遵循以下规范进行代码修改任务：
            1. 每次响应仅执行一步操作，先分析再修改，避免一步多改。
            2. 充分利用工具理解用户需求和现有代码，禁止凭空假设。
            3. 如果不清楚要修改的文件，必须先分析并找出需要修改的文件，明确目标后再进行编辑。
            4. 对于简单的文本替换（如修改单个字符串、常量值、配置项等），优先使用 execute_script 工具执行 sed 命令完成，简单高效。
            5. 代码编辑任务优先使用 PATCH 操作，确保搜索文本在目标文件中有且仅有一次精确匹配，保证修改的准确性和安全性。
            6. 如需大范围重写，才可使用 REWRITE 操作。
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
                    print("🔍 正在进行智能上下文推荐....")

                    # 生成上下文推荐（基于关键词和项目上下文）
                    recommendation = self.context_recommender.recommend_context(
                        user_input=user_input,
                    )

                    # 格式化推荐结果
                    context_recommendation_text = (
                        self.context_recommender.format_recommendation(recommendation)
                    )

                    # 打印推荐的上下文
                    if context_recommendation_text:
                        print(f"ℹ️ {context_recommendation_text}")
                except Exception as e:
                    # 上下文推荐失败不应该影响主流程
                    print(f"⚠️ 上下文推荐失败: {e}")
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
                super().run(enhanced_input)
            except RuntimeError as e:
                print(f"⚠️ 执行失败: {str(e)}")
                return str(e)

            self.git_manager.handle_uncommitted_changes()
            end_commit = get_latest_commit_hash()
            commits = self.git_manager.show_commit_history(start_commit, end_commit)
            self.git_manager.handle_commit_confirmation(
                commits,
                start_commit,
                prefix,
                suffix,
                self,
                self.post_process_manager.post_process_modified_files,
            )
            return None

        except RuntimeError as e:
            return f"Error during execution: {str(e)}"
        finally:
            # Ensure switching back to the original working directory after CodeAgent completes
            try:
                os.chdir(prev_dir)
            except Exception:
                pass

    def _on_after_tool_call(
        self,
        agent: Agent,
        current_response=None,
        need_return=None,
        tool_prompt=None,
        **kwargs,
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
                from jarvis.jarvis_utils.config import (
                    get_diff_visualization_mode,
                    get_diff_show_line_numbers,
                )

                # 显示整体 diff（使用增强可视化）
                visualization_mode = get_diff_visualization_mode()
                show_line_numbers = get_diff_show_line_numbers()
                visualize_diff_enhanced(
                    diff, mode=visualization_mode, show_line_numbers=show_line_numbers
                )
            except ImportError:
                # 如果导入失败，回退到原有方式
                PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            except Exception as e:
                # 如果可视化失败，回退到原有方式
                print(f"⚠️ Diff 可视化失败，使用默认方式: {e}")
                PrettyOutput.print(diff, OutputType.CODE, lang="diff")

            # 更新上下文管理器
            self.impact_manager.update_context_for_modified_files(modified_files)

            # 进行影响范围分析
            impact_report = self.impact_manager.analyze_edit_impact(modified_files)

            per_file_preview = self.diff_manager.build_per_file_patch_preview(
                modified_files
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
                    print("ℹ️ 已撤销修改（大模型认为代码删除不合理）")
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
                    build_validation_result, final_ret = (
                        self.build_validation_manager.handle_build_validation(
                            modified_files, self, final_ret
                        )
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
                                commit_hash, commit_message = (
                                    result.stdout.strip().split("|", 1)
                                )
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
) -> None:
    """Jarvis主入口点。"""
    # CLI 标志：非交互模式（不依赖配置文件）
    if non_interactive:
        try:
            os.environ["JARVIS_NON_INTERACTIVE"] = "true"
        except Exception:
            pass
        # 注意：全局配置同步放在 init_env 之后执行，避免被 init_env 覆盖
    # 非交互模式要求从命令行传入任务
    if non_interactive and not (requirement and str(requirement).strip()):
        print(
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
            set_config("JARVIS_LLM_GROUP", str(model_group))
        if tool_group:
            set_config("JARVIS_TOOL_GROUP", str(tool_group))
        if restore_session:
            set_config("JARVIS_RESTORE_SESSION", True)
        if non_interactive:
            set_config("JARVIS_NON_INTERACTIVE", True)
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
        print(f"⚠️ 警告：当前目录 '{curr_dir_path}' 不是一个git仓库。")
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
                print("✅ 已成功初始化git仓库。")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"❌ 初始化git仓库失败: {e}")
                sys.exit(1)
        else:
            print("ℹ️ 操作已取消。Jarvis需要在git仓库中运行。")
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
        )

        # 显示可用的规则信息
        _print_available_rules(agent.rules_manager, rule_names)

        # 尝试恢复会话
        if restore_session:
            if agent.restore_session():
                print("✅ 已从 .jarvis/saved_session.json 恢复会话。")
            else:
                print("⚠️ 无法从 .jarvis/saved_session.json 恢复会话。")

        if requirement:
            agent.run(requirement, prefix=prefix, suffix=suffix)
        else:
            while True:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    raise typer.Exit(code=0)
                agent.run(user_input, prefix=prefix, suffix=suffix)

    except typer.Exit:
        raise
    except RuntimeError as e:
        print(f"❌ 错误: {str(e)}")
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
        from rich.panel import Panel
        from rich.text import Text
        from rich.console import Console

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
        has_project_rule = rules_manager.read_project_rules() is not None
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

        # 文件规则
        if file_rules:
            has_any_rules = True
            file_text = Text()
            file_text.append("📄 文件规则 ", style="bold blue")
            file_text.append(f"({len(file_rules)} 个): ", style="dim")
            for i, rule in enumerate(file_rules):
                if i > 0:
                    file_text.append(", ", style="dim")
                file_text.append(rule, style="cyan")
            content_parts.append(file_text)

        # YAML 规则
        if yaml_rules:
            has_any_rules = True
            yaml_text = Text()
            yaml_text.append("📝 YAML规则 ", style="bold magenta")
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
    except Exception:
        # 静默失败，不影响主流程
        pass


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
