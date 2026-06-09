"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import hashlib
import logging
import os
from datetime import datetime

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import subprocess
import sys
from typing import Any, Dict, List, Optional, Union

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.content_types import ContentBlock, TextContent
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
from jarvis.jarvis_code_agent.code_agent_build import BuildValidationManager
from jarvis.jarvis_code_agent.code_agent_diff import DiffManager
from jarvis.jarvis_code_agent.code_agent_git import GitManager
from jarvis.jarvis_code_agent.code_agent_impact import ImpactManager
from jarvis.jarvis_code_agent.code_agent_lint import LintManager
from jarvis.jarvis_code_agent.code_agent_postprocess import PostProcessManager
from jarvis.jarvis_agent.builtin_input_handler import (
    builtin_input_handler,
)
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_code_agent.code_agent_prompts import (
    classify_user_request,
    get_system_prompt,
)
from jarvis.jarvis_code_agent.code_analyzer import ContextManager
from jarvis.jarvis_code_agent.worktree_manager import WorktreeManager
from jarvis.jarvis_code_agent.utils import get_project_overview
from jarvis.jarvis_utils.config import is_auto_resume_session
from jarvis.jarvis_utils.config import is_confirm_before_apply_patch
from jarvis.jarvis_utils.config import is_enable_quick_mode
from jarvis.jarvis_utils.config import is_enable_request_classification
from jarvis.jarvis_utils.config import is_use_analysis
from jarvis.jarvis_utils.config import is_use_methodology
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
from jarvis.jarvis_utils.git_utils import reset_confirm_add_new_files_flag
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.tmux_wrapper import check_and_launch_tmux
from jarvis.jarvis_utils.tmux_wrapper import dispatch_to_tmux_window

from jarvis.jarvis_utils.utils import _acquire_single_instance_lock
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.globals import set_current_agent
from jarvis.jarvis_utils.globals import clear_current_agent
import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)

app = typer.Typer(help="Jarvis 代码助手")


class CodeAgent(Agent):
    """Jarvis系统的代码修改代理。

    负责处理代码分析、修改和git操作。
    """

    def __init__(
        self,
        need_summary: bool = True,
        append_tools: Optional[str] = None,
        tool_group: Optional[str] = None,
        non_interactive: Optional[bool] = True,
        rule_names: Optional[str] = None,
        disable_review: bool = False,
        review_max_iterations: int = 0,
        enable_task_list_manager: bool = True,
        optimize_system_prompt: bool = False,
        quick_mode: bool = False,
        **kwargs: Any,
    ) -> None:
        # 存储极速模式标志
        self.quick_mode = quick_mode

        # CodeAgent 基础属性初始化
        self._init_code_agent_base_attributes(
            tool_group, disable_review, review_max_iterations
        )

        # 上下文管理相关初始化
        self._init_code_agent_context_managers()

        # 代码管理相关管理器初始化
        self._init_code_agent_managers()

        # 工具列表构建
        base_tools = self._build_code_agent_tool_list(
            append_tools, enable_task_list_manager
        )

        # 父类初始化准备和调用
        explicit_params = self._prepare_code_agent_parent_init(
            need_summary,
            non_interactive,
            base_tools,
            optimize_system_prompt,
            kwargs,
        )
        super().__init__(**explicit_params, **kwargs)

        # 父类初始化后的设置
        self._setup_code_agent_after_parent_init()

    def get_user_origin_input(self) -> Union[str, List[ContentBlock]]:
        """获取原始用户输入（CodeAgent重写）

        返回:
            Union[str, List[ContentBlock]]: 原始用户输入（未经CodeAgent增强处理）
        """
        return self._raw_user_input

    def _convert_to_string(self, user_input: Union[str, List[ContentBlock]]) -> str:
        """将用户输入转换为字符串

        参数:
            user_input: 用户输入（纯文本或多模态内容）

        返回:
            str: 字符串表示形式
        """
        if isinstance(user_input, str):
            return user_input

        # 如果是多模态内容，提取文本部分
        text_parts = []
        for block in user_input:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return "\n".join(text_parts) if text_parts else "[多模态内容]"

    def _append_to_session_prompt(self, content: str) -> None:
        """安全地追加内容到 session.prompt

        参数:
            content: 要追加的字符串内容
        """
        if isinstance(self.session.prompt, str):
            self.session.prompt += content
        else:
            # 如果 session.prompt 是 List[ContentBlock]，将 content 转换为 TextContent 并追加
            text_block: TextContent = {"type": "text", "text": content}
            self.session.prompt.append(text_block)

    def _init_code_agent_base_attributes(
        self,
        tool_group: Optional[str],
        disable_review: bool,
        review_max_iterations: int,
    ) -> None:
        """初始化 CodeAgent 基础属性

        参数:
            tool_group: 工具组配置
            disable_review: 是否禁用代码审查
            review_max_iterations: 代码审查最大迭代次数
        """
        # 设置工作目录和工具组配置
        self.root_dir = os.getcwd()
        self.tool_group = tool_group

        # Review 相关配置
        # 注意：disable_review 仅保存配置值，实际是否执行 review 在运行时动态判断
        self.disable_review = disable_review  # 保存用户配置的 disable_review 值
        self.review_max_iterations = review_max_iterations

        # Git 相关初始化：存储开始时的 commit hash，用于后续 git diff 获取
        self.start_commit: Optional[str] = None
        # 记录上次备份时的 commit hash，用于计算增量备份
        self.last_backup_commit: Optional[str] = None

        # Commit prefix 和 suffix，用于生成提交信息
        self.prefix: str = ""
        self.suffix: str = ""

        # 保存原始用户输入（用于会话名称生成）
        self._raw_user_input: Union[str, List[ContentBlock]] = ""

    def _init_code_agent_context_managers(self) -> None:
        """初始化 CodeAgent 上下文管理相关组件"""
        # 初始化上下文管理器（用于代码分析和上下文追踪）
        self.context_manager = ContextManager(self.root_dir)

    def _init_code_agent_managers(self) -> None:
        """初始化 CodeAgent 代码管理相关的各个管理器"""
        # Git 管理器：处理 Git 操作和提交
        self.git_manager = GitManager(self.root_dir)
        # 检测 git username 和 email 是否已设置
        self.git_manager.check_git_config()

        # Diff 管理器：处理代码差异分析和展示
        self.diff_manager = DiffManager(self.root_dir)

        # 影响分析管理器：分析代码修改的影响范围
        self.impact_manager = ImpactManager(self.root_dir, self.context_manager)

        # 构建验证管理器：验证代码修改后的构建状态
        self.build_validation_manager = BuildValidationManager(self.root_dir)

        # Lint 管理器：执行静态代码分析
        self.lint_manager = LintManager(self.root_dir)

        # 后处理管理器：处理代码修改后的清理和优化
        self.post_process_manager = PostProcessManager(self.root_dir)

    def _build_code_agent_tool_list(
        self,
        append_tools: Optional[str],
        enable_task_list_manager: bool,
    ) -> List[str]:
        """构建 CodeAgent 工具列表

        参数:
            append_tools: 要追加的工具列表（逗号分隔）
            enable_task_list_manager: 是否启用任务列表管理器

        返回:
            List[str]: 构建好的工具列表
        """
        # 构建基础工具列表（CodeAgent 专用的代码操作工具）
        base_tools = [
            "execute_script",  # 脚本执行工具
            "read_code",  # 代码读取工具
            "edit_file",  # 普通 search/replace 编辑工具
            "load_rule",  # 规则加载工具
            "auto_select_rule",  # 自动规则选择工具
            "virtual_tty",  # 虚拟终端工具，支持交互式操作
            "search_web",  # 网络搜索工具
            "read_webpage",  # 网页内容读取工具
            "memory",  # 记忆管理工具（支持save/retrieve/clear操作）
            "methodology",  # 方法论工具
            "symbol_dependency",  # 符号依赖查询工具
            "add_images",  # 添加图片到对话上下文工具
            "gateway_manager",  # Gateway 管理工具（Agent 通信、节点管理、模型组查询等）
        ]
        # 如果启用了任务列表管理器，添加相应工具
        if enable_task_list_manager:
            base_tools.append("task_list_manager")  # 任务列表管理工具

        # 处理追加的工具（从参数中解析并去重）
        if append_tools:
            additional_tools = [
                t for t in (tool.strip() for tool in append_tools.split(",")) if t
            ]
            base_tools.extend(additional_tools)
            # 去重，保持顺序
            base_tools = list(dict.fromkeys(base_tools))

        return base_tools

    def _merge_rule_names(self, cli_rule_names: Optional[str]) -> Optional[str]:
        """合并配置文件默认规则和命令行规则

        参数:
            cli_rule_names: 命令行传入的规则名称（逗号分隔的字符串）

        返回:
            Optional[str]: 合并后的规则名称（逗号分隔的字符串），如果都为空则返回 None
        """
        from jarvis.jarvis_utils.config import get_default_rule_names

        # 获取配置文件中的默认规则
        default_rules = get_default_rule_names()

        # 解析命令行规则
        cli_rules: List[str] = []
        if cli_rule_names and cli_rule_names.strip():
            cli_rules = [
                name.strip() for name in cli_rule_names.split(",") if name.strip()
            ]

        # 如果两个都没有，返回 None
        if not default_rules and not cli_rules:
            return None

        # 合并并去重
        all_rules = list(dict.fromkeys(default_rules + cli_rules))  # 保持顺序的去重

        # 转换为逗号分隔的字符串
        return ",".join(all_rules) if all_rules else None

    def _prepare_code_agent_parent_init(
        self,
        need_summary: bool,
        non_interactive: Optional[bool],
        base_tools: List[str],
        optimize_system_prompt: bool,
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """准备 CodeAgent 父类初始化的参数

        参数:
            need_summary: 是否需要总结
            non_interactive: 是否非交互模式
            base_tools: 基础工具列表
            optimize_system_prompt: 是否优化系统提示词
            kwargs: 其他关键字参数

        返回:
            Dict[str, Any]: 准备传递给父类的参数字典
        """
        # 获取 CodeAgent 专用的系统提示词
        code_system_prompt = get_system_prompt()

        # 合并默认规则和命令行规则
        cli_rule_names = kwargs.pop("rule_names", None)
        merged_rule_names = self._merge_rule_names(cli_rule_names)

        # 从配置文件读取默认值，允许通过 kwargs 覆盖
        # 如果 kwargs 中未指定，则从配置文件读取默认值
        use_methodology = kwargs.pop("use_methodology", is_use_methodology())
        use_analysis = kwargs.pop("use_analysis", is_use_analysis())
        # 保存原始的 use_analysis 配置值，用于在 run 方法结束前手动调用分析
        self._use_analysis_config = use_analysis
        # name 使用传入的值，如果没有传入则使用默认值 "CodeAgent"
        name = kwargs.pop("name", "CodeAgent")

        # 极速模式下禁用方法论加载和自动规则选择
        if self.quick_mode:
            use_methodology = False
            enable_auto_rule_select = False
        else:
            # 非极速模式下，根据 kwargs 或默认值设置 enable_auto_rule_select
            enable_auto_rule_select = kwargs.pop("enable_auto_rule_select", True)

        # 准备显式传递给 super().__init__ 的参数
        # 注意：这些参数如果也在 kwargs 中，需要先移除，避免重复传递错误
        explicit_params = {
            "system_prompt": code_system_prompt,
            "name": name,
            "auto_complete": False,
            "need_summary": need_summary,
            "use_methodology": use_methodology,
            "use_analysis": False,  # 初始化时不启用分析，在 run 方法结束前手动调用
            "non_interactive": non_interactive,
            "use_tools": base_tools,
            "optimize_system_prompt": optimize_system_prompt,
            "rule_names": merged_rule_names,
            "enable_auto_rule_select": enable_auto_rule_select,
            "quick_mode": self.quick_mode,  # 传递极速模式标志到父类
        }

        # 自动移除所有显式传递的参数，避免重复传递错误
        # 这样以后添加新参数时，只要在 explicit_params 中声明，就会自动处理
        for key in explicit_params:
            kwargs.pop(key, None)

        return explicit_params

    def _setup_code_agent_after_parent_init(self) -> None:
        """CodeAgent 父类初始化后的设置"""
        # 设置 Agent 类型标识
        self._agent_type = "code_agent"

        # 建立 CodeAgent 与 Agent 的关联，便于工具获取上下文管理器
        self._code_agent = self

        # 订阅工具调用后事件，用于处理代码修改后的 diff 展示和提交
        self.event_bus.subscribe(AFTER_TOOL_CALL, self._on_after_tool_call)

    def run(
        self,
        user_input: Union[str, List[ContentBlock]],
        prefix: str = "",
        suffix: str = "",
    ) -> Optional[str]:
        """使用给定的用户输入运行代码代理.

        参数:
            user_input: 用户的需求/请求

        返回:
            str: 描述执行结果的输出，成功时返回None
        """
        # 标记是否应该保存会话（内置命令处理完成时不保存）
        _should_save_session = True
        try:
            set_current_agent(self.name, self)

            # 保存原始用户输入（用于会话名称生成）
            self._raw_user_input = user_input
            self.original_user_input = user_input

            # 存储 prefix 和 suffix，供 commit 命令使用
            self.prefix = prefix
            self.suffix = suffix

            # 优先处理输入处理器（如内置命令、shell 快捷输入）
            # 如果当前输入已被处理，则继续等待用户输入，不进入需求分类流程
            processed_input = ""
            while True:
                # 只有当 user_input 是字符串时才处理内置命令和 shell 命令
                if isinstance(user_input, str):
                    processed_input, is_handled = builtin_input_handler(
                        user_input, self
                    )
                    if is_handled:
                        # 如果有返回的提示信息，追加到 addon_prompt
                        if processed_input:
                            current_addon = self.session.addon_prompt or ""
                            self.set_addon_prompt(
                                f"{current_addon}\n{processed_input}".strip()
                            )
                        # 内置命令已处理完成，继续等待用户输入
                        user_input = get_multiline_input(
                            "请输入你的需求（Ctrl+C 退出）"
                        )
                        if not user_input:
                            # 用户取消输入，不保存会话
                            _should_save_session = False
                            return None
                        continue

                    processed_input, is_handled = shell_input_handler(user_input, self)
                    if is_handled:
                        # Shell 输入已处理完成，继续等待用户输入
                        user_input = get_multiline_input(
                            "请输入你的需求（Ctrl+C 退出）"
                        )
                        if not user_input:
                            # 用户取消输入，不保存会话
                            _should_save_session = False
                            return None
                        continue

                    if processed_input:
                        user_input = processed_input
                break

            prev_dir = os.getcwd()

            # 需求分类：仅在首次运行时执行（未恢复会话）
            # 如果指定了恢复会话的参数，就不用对需求进行分类了（因为系统提示词早就有了）
            if self.first:
                # 极速模式：跳过任务分类、规则自动加载、上下文推荐、方法论加载
                if self.quick_mode:
                    # 极速模式已启用，跳过相关步骤
                    # === 阶段3: Git环境初始化 ===
                    self.git_manager.init_env(prefix, suffix, self)
                    # 获取初始 commit（在 Git 环境初始化之后）
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

                    # 极速模式下直接使用用户输入
                    user_input_str = self._convert_to_string(user_input)
                    enhanced_input = user_input_str
                else:
                    # 正常模式：执行所有阶段
                    # === 阶段1: 需求分类（仅在启用时执行） ===
                    if is_enable_request_classification():
                        self._classify_and_switch_model(
                            user_input, classify_user_request, get_system_prompt
                        )

                    # === 阶段2: 生成非交互模式说明 ===
                    # 根据当前模式生成额外说明，供 LLM 感知执行策略
                    non_interactive_note = ""
                    if getattr(self, "non_interactive", False):
                        non_interactive_note = (
                            "\n\n[系统说明]\n"
                            "本次会话处于**非交互模式**：\n"
                            "- 在 PLAN 模式中给出清晰、可执行的详细计划后，应**自动进入 EXECUTE 模式执行计划**，不要等待用户额外确认；\n"
                            '- 在 EXECUTE 模式中，保持一步一步的小步提交和可回退策略，但不需要向用户反复询问"是否继续"；\n'
                            "- 如遇信息严重不足，可以在 RESEARCH 模式中自行补充必要分析，而不是卡在等待用户输入。\n"
                        )

                    # === 阶段3: Git环境初始化 ===
                    self.git_manager.init_env(prefix, suffix, self)
                    # 获取初始 commit（在 Git 环境初始化之后）
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

                    # === 阶段4: 获取项目概况 ===
                    project_overview = get_project_overview(self.root_dir)

                    first_tip = """请严格遵循以下规范进行代码修改任务：
            1. 每次响应仅执行一步操作，先分析再修改，避免一步多改。
            2. 充分利用工具理解用户需求和现有代码，禁止凭空假设。
            3. 如果不清楚要修改的文件，必须先分析并找出需要修改的文件，明确目标后再进行编辑。
            4. 对于简单的文本替换，推荐使用 edit_file 工具进行精确修改。对于复杂代码（超过50行或涉及多文件协调），必须使用task_list_manager创建任务列表进行安全拆分。
            5. 代码编辑任务优先使用 PATCH 操作，确保搜索文本在目标文件中有且仅有一次精确匹配，保证修改的准确性和安全性。
            6. 如需大范围重写（超过200行或涉及重构），请使用 edit_file 工具配合空search参数 ""，并提前备份原始文件。
            7. 如遇信息不明，优先调用工具补充分析，不要主观臆断。
            8. **重要：清理临时文件**：开发过程中产生的临时文件（如测试文件、调试脚本、备份文件、临时日志等）必须在提交前清理删除，否则会被自动提交到git仓库。如果创建了临时文件用于调试或测试，完成后必须立即删除。
            """

                    # === 阶段6: 构建增强输入 ===
                    # 将 user_input 转换为字符串
                    user_input_str = self._convert_to_string(user_input)
                    if project_overview:
                        enhanced_input = (
                            project_overview
                            + "\n\n"
                            + first_tip
                            + non_interactive_note
                            + "\n\n任务描述：\n"
                            + user_input_str
                        )
                    else:
                        enhanced_input = (
                            first_tip
                            + non_interactive_note
                            + "\n\n任务描述：\n"
                            + user_input_str
                        )

            else:
                # 会话恢复时，直接使用用户输入（上下文已从会话中恢复）
                user_input_str = self._convert_to_string(user_input)
                enhanced_input = user_input_str

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
                    prefix=prefix,
                    suffix=suffix,
                    code_generation_summary=result_str,
                )

            # 根据配置在任务结束时手动调用分析功能（在最终提交之前）
            if self._use_analysis_config:
                # 询问用户是否需要分析，默认不执行分析
                default_analyze = bool(self.non_interactive)
                should_analyze = user_confirm(
                    "📊 是否对本次任务进行分析并生成方法论？",
                    default=default_analyze,
                )
                if should_analyze:
                    try:
                        self.analysis()
                    except Exception as e:
                        # 分析失败不应该影响主流程，仅记录错误
                        PrettyOutput.auto_print(f"⚠️ 任务分析失败: {str(e)}")

            end_commit = get_latest_commit_hash()
            commits = self.git_manager.show_commit_between(
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
            # 自动保存会话状态
            try:
                if _should_save_session:
                    self.save_session()
            except Exception as e:
                # 保存会话失败不影响其他清理操作
                PrettyOutput.auto_print(f"⚠️ 保存会话失败: {str(e)}")
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
        # 重置全局标记，允许在此流程中重新进行文件确认
        reset_confirm_add_new_files_flag()

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
                PrettyOutput.auto_print(diff, lang="diff")
            except Exception as e:
                # 如果可视化失败，回退到原有方式
                PrettyOutput.auto_print(f"⚠️ Diff 可视化失败，使用默认方式: {e}")
                PrettyOutput.auto_print(diff, lang="diff")

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
                is_reasonable = self.ask_llm_about_large_deletion(
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
                    PrettyOutput.auto_print(final_ret, lang="markdown")  # 保留语法高亮
                    self._append_to_session_prompt(final_ret)
                    return

            commited = handle_commit_workflow(start_hash)
            if commited:
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

                #
                latest_commit_hash = get_latest_commit_hash()
                if self.start_commit and latest_commit_hash:
                    diff_lines = get_diff_between_commits(
                        self.start_commit, latest_commit_hash
                    )
                else:
                    diff_lines = ""
                if diff_lines:
                    assert (
                        self.start_commit is not None and latest_commit_hash is not None
                    )
                    # 使用上次备份的提交作为起点，如果没有则使用初始提交
                    backup_start_commit = self.last_backup_commit or self.start_commit
                    commits = get_commits_between(
                        backup_start_commit, latest_commit_hash
                    )

                    # 计算从上次备份点到当前的增量变更（用于备份判断）
                    diff_lines_since_backup = get_diff_between_commits(
                        backup_start_commit, latest_commit_hash
                    )
                    lines_added_since_backup = sum(
                        1
                        for line in diff_lines_since_backup
                        if line.startswith("+") and not line.startswith("+++")
                    )
                    lines_removed_since_backup = sum(
                        1
                        for line in diff_lines_since_backup
                        if line.startswith("-") and not line.startswith("---")
                    )
                    incremental_lines = (
                        lines_added_since_backup + lines_removed_since_backup
                    )

                    if incremental_lines > 1000:
                        # 在压缩前创建备份分支
                        try:
                            # 生成备份分支名（格式：backup/YYYY-MM-DD_HH-MM-SS）
                            backup_branch = (
                                f"backup/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
                            )

                            # 创建备份分支指向 latest_commit_hash
                            # 注意：git branch 只创建分支，不会切换当前分支
                            subprocess.run(
                                ["git", "branch", backup_branch, latest_commit_hash],
                                capture_output=True,
                                check=True,
                            )
                            PrettyOutput.auto_print(
                                f"✅ 已创建备份分支：{backup_branch}（变更超过 1000 行，已自动备份，请手动确认提交）"
                            )
                            # 更新上次备份的提交点，下次备份将从这里开始计算
                            self.last_backup_commit = latest_commit_hash
                        except subprocess.CalledProcessError as e:
                            PrettyOutput.auto_print(f"⚠️ 创建备份分支失败：{str(e)}")
                        except Exception as e:
                            PrettyOutput.auto_print(f"⚠️ 备份分支创建异常：{str(e)}")
            else:
                final_ret += "\n修改被拒绝\n"
                final_ret += f"# 补丁预览（按文件）:\n{per_file_preview}"
        else:
            return
        # 用户确认最终结果
        if commited:
            self._append_to_session_prompt(final_ret)
            return
        PrettyOutput.auto_print(final_ret, lang="markdown")  # 保留语法高亮
        if not is_confirm_before_apply_patch() or user_confirm(
            "是否使用此回复？", default=True
        ):
            self._append_to_session_prompt(final_ret)
            return
        # 用户未确认，允许输入自定义回复作为附加提示
        custom_reply = get_multiline_input("请输入自定义回复")
        if custom_reply.strip():  # 如果自定义回复为空，不设置附加提示
            self.set_addon_prompt(custom_reply)
        self._append_to_session_prompt(final_ret)
        return

    def ask_llm_about_large_deletion(
        self, detection_result: Dict[str, int], preview: str
    ) -> bool:
        """询问大模型大量代码删除是否合理

        参数:
            detection_result: 检测结果字典，包含 'insertions', 'deletions', 'net_deletions'
            preview: 补丁预览内容

        返回:
            bool: 如果大模型认为合理返回True，否则返回False
        """
        insertions = detection_result["insertions"]
        deletions = detection_result["deletions"]
        net_deletions = detection_result["net_deletions"]

        prompt = f"""检测到大量代码删除，请判断是否合理：

统计信息：
- 新增行数: {insertions}
- 删除行数: {deletions}
- 净删除行数: {net_deletions}

补丁预览：
{preview}

请仔细分析以上代码变更，判断这些大量代码删除是否合理。可能的情况包括：
1. 重构代码，删除冗余或过时的代码
2. 简化实现，用更简洁的代码替换复杂的实现
3. 删除未使用的代码或功能
4. 错误地删除了重要代码

请使用以下协议回答（必须包含且仅包含以下标记之一）：
- 如果认为这些删除是合理的，回答: <!!!YES!!!>
- 如果认为这些删除不合理或存在风险，回答: <!!!NO!!!>

请严格按照协议格式回答，不要添加其他内容。
"""

        # 确保模型实例存在
        if self.model is None:
            raise ValueError("模型实例为空，无法执行询问")

        try:
            PrettyOutput.auto_print("🤖 正在询问大模型判断大量代码删除是否合理...")
            # 直接使用当前模型的实例，保留完整对话上下文
            response = self.model.chat_until_success(prompt)

            # 使用确定的协议标记解析回答
            if "<!!!YES!!!>" in response:
                PrettyOutput.auto_print("✅ 大模型确认：代码删除合理")
                return True
            elif "<!!!NO!!!>" in response:
                PrettyOutput.auto_print("⚠️ 大模型确认：代码删除不合理")
                return False
            else:
                # 如果无法找到协议标记，默认认为不合理（保守策略）
                PrettyOutput.auto_print(
                    f"⚠️ 无法找到协议标记，默认认为不合理。回答内容: {response[:200]}"
                )
                return False
        except Exception as e:
            # 如果询问失败，默认认为不合理（保守策略）
            PrettyOutput.auto_print(f"⚠️ 询问大模型失败: {str(e)}，默认认为不合理")
            return False

    def _get_code_reviewer(self) -> "CodeReviewer":
        """获取 CodeReviewer 实例。"""
        from jarvis.jarvis_code_agent.code_reviewer import CodeReviewer

        return CodeReviewer(
            model=self.model,
            start_commit=self.start_commit,
            non_interactive=self.non_interactive,
            quick_mode=self.quick_mode,
        )

    def _truncate_diff_for_review(self, git_diff: str, token_ratio: float = 0.4) -> str:
        """截断 git diff 以适应 token 限制（委托给 CodeReviewer）。"""
        return self._get_code_reviewer().truncate_diff_for_review(git_diff, token_ratio)

    def _generate_fix_summary(self) -> str:
        """生成修复阶段的总结

        返回:
            str: 修复总结
        """
        try:
            # 使用父类的 generate_summary 方法
            summary = self.generate_summary(for_token_limit=False)
            return summary or ""
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 生成修复总结失败: {e}")
            return ""

    def _generate_review_target(self, max_retries: int = 3) -> str:
        """生成代码审查的目标和验收准则（委托给 CodeReviewer）。"""
        return self._get_code_reviewer().generate_review_target(max_retries)

    def _build_review_prompts(
        self,
        review_target: str,
        git_diff: str,
        modification_history: Optional[str] = None,
        start_commit: Optional[str] = None,
    ) -> tuple:
        """构建 review Agent 的 prompts（委托给 CodeReviewer）。"""
        return self._get_code_reviewer().build_review_prompts(
            review_target=review_target,
            git_diff=git_diff,
            modification_history=modification_history,
            start_commit=start_commit,
        )

    def _check_and_get_git_diff(self) -> Optional[str]:
        """检查并获取 git diff（委托给 CodeReviewer）。"""
        return self._get_code_reviewer().check_and_get_git_diff()

    def _review_and_fix(
        self,
        prefix: str = "",
        suffix: str = "",
        code_generation_summary: Optional[str] = None,
    ) -> None:
        """执行 review 和修复循环（委托给 CodeReviewer.run_review_with_fix）。

        参数:
            prefix: 前缀
            suffix: 后缀
            code_generation_summary: 代码生成总结
        """
        # 获取从开始到当前的 git diff（提前检测是否有代码修改）
        git_diff = self._check_and_get_git_diff()
        if git_diff is None:
            return

        if self.disable_review:
            PrettyOutput.auto_print("ℹ️ 代码审查已禁用，跳过审查")
            return

        # 获取 CodeReviewer 实例并委托执行审查+修复循环
        reviewer = self._get_code_reviewer()
        reviewer.run_review_with_fix(
            modification_history=code_generation_summary or "",
            max_iterations=self.review_max_iterations,
            use_tools=["execute_script", "read_code", "memory"],
            non_interactive=self.non_interactive,
            quick_mode=self.quick_mode,
            on_fix=lambda fix_prompt: self._do_fix(fix_prompt),
            on_generate_fix_summary=lambda: self._generate_fix_summary(),
            on_handle_uncommitted_changes=lambda: (
                self.git_manager.handle_uncommitted_changes()
            ),
        )

    def _do_fix(self, fix_prompt: str) -> None:
        """执行修复（供 run_review_with_fix 的 on_fix 回调调用）。"""
        if self.model:
            self.model.set_suppress_output(False)
        super().run(fix_prompt)


@app.command()
def cli(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    tool_group: Optional[str] = typer.Option(
        None, "-G", "--tool-group", help="使用的工具组，覆盖配置文件中的设置"
    ),
    config_file: Optional[str] = typer.Option(
        None, "-f", "--config", help="配置文件路径"
    ),
    task: Optional[str] = typer.Option(None, "-T", "--task", help="要处理的任务描述"),
    task_file: Optional[str] = typer.Option(
        None, "--task-file", help="从文件读取任务描述"
    ),
    append_tools: Optional[str] = typer.Option(
        None, "--append-tools", help="要追加的工具列表，用逗号分隔"
    ),
    restore: bool = typer.Option(
        False,
        "-r",
        "--restore",
        help="交互式选择恢复会话",
    ),
    restore_session: Optional[str] = typer.Option(
        None,
        "-R",
        "--restore-session",
        help="从指定会话文件恢复",
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
        help="禁用代码审查：在代码修改完成后不进行自动代码审查",
    ),
    review_max_iterations: int = typer.Option(
        0,
        "--review-max-iterations",
        help="代码审查最大迭代次数，达到上限后停止审查（默认0次，表示无限）",
    ),
    worktree: bool = typer.Option(
        False,
        "-w",
        "--worktree",
        help="启用 git worktree 模式，在独立分支上开发",
    ),
    dispatch: bool = typer.Option(
        False,
        "-d",
        "--dispatch",
        help="将任务派发到新的 tmux 窗口中执行（仅在 tmux 环境中有效），当前进程退出",
    ),
    optimize_system_prompt: bool = typer.Option(
        False,
        "-o",
        "--optimize-system-prompt",
        help="自动优化系统提示词：根据用户需求使用大模型优化系统提示词",
    ),
    web_gateway: bool = typer.Option(
        False,
        "--web-gateway",
        help="启用 Web Gateway 服务（WebSocket 输入输出）",
    ),
    quick_mode: bool = typer.Option(
        False,
        "-q",
        "--quick",
        help="极速模式：取消任务分类、规则自动加载、上下文推荐、方法论加载",
    ),
    print_prompt: bool = typer.Option(
        False,
        "--print-prompt",
        help="打印提示信息（覆盖配置文件设置）",
    ),
    web_gateway_port: int = typer.Option(
        8000,
        "--web-gateway-port",
        help="Web Gateway 监听端口",
    ),
    gateway_password: Optional[str] = typer.Option(
        None,
        "--gateway-password",
        help="Web Gateway 密码（如未设置将禁用密码认证）",
    ),
    proxy_node: Optional[str] = typer.Option(
        None,
        "--proxy-node",
        help="HTTP 代理请求转发到的目标节点 ID",
    ),
    master_url: Optional[str] = typer.Option(
        None,
        "--master-url",
        help="Master 节点 URL，用于 HTTP 代理请求转发",
    ),
    agent_id: Optional[str] = typer.Option(
        None,
        "--agent-id",
        help="Agent ID，由 Web Gateway 的 AgentManager 分配的唯一标识符",
    ),
) -> None:
    """Jarvis主入口点。"""
    # 处理任务描述：优先从文件读取
    if task and task_file:
        PrettyOutput.auto_print("❌ 错误: 不能同时使用 --task 和 --task-file 参数")
        raise typer.Exit(code=1)

    # 用于tmux并行任务的状态文件路径
    status_file_path = None
    web_gateway_server = None

    if task_file:
        try:
            import json
            from pathlib import Path

            with open(task_file, "r", encoding="utf-8") as file_handle:
                file_content = file_handle.read()

            # 尝试解析为JSON以获取status_file字段
            try:
                task_data = json.loads(file_content)
                status_file_path = task_data.get("status_file")
                if status_file_path:
                    # 将status_file_path转换为Path对象
                    status_file_path = Path(status_file_path)
                # 提取实际任务内容
                if "task_desc" in task_data:
                    task = task_data["task_desc"]
                    if "background" in task_data:
                        task += f"\n\n背景信息:\n{task_data['background']}"
                    if "additional_info" in task_data:
                        task += f"\n\n附加信息:\n{task_data['additional_info']}"
                else:
                    # 不是JSON格式或没有task_desc字段，直接使用文件内容
                    task = file_content
            except json.JSONDecodeError:
                # 不是JSON格式，直接使用文件内容
                task = file_content

        except (Exception, FileNotFoundError) as e:
            PrettyOutput.auto_print(f"❌ 错误: 无法从文件读取任务描述: {str(e)}")
            raise typer.Exit(code=1)

    # 非交互模式要求从命令行传入任务
    if non_interactive and not (task and str(task).strip()):
        PrettyOutput.auto_print(
            "❌ 非交互模式已启用：必须使用 --task 传入任务内容，因多行输入不可用。"
        )
        raise typer.Exit(code=2)

    # 处理 --dispatch 参数：派发任务到新的 tmux 窗口
    if dispatch:
        if not (task and str(task).strip()):
            PrettyOutput.auto_print(
                "❌ 错误: --dispatch 参数必须与 --task 参数配合使用"
            )
            raise typer.Exit(code=1)

        PrettyOutput.auto_print("ℹ️ 正在派发任务到新的 tmux 窗口...")
        success = dispatch_to_tmux_window(task, sys.argv)
        if success:
            PrettyOutput.auto_print("✅ 任务已成功派发到新的 tmux 窗口")
            raise typer.Exit(code=0)
        else:
            PrettyOutput.auto_print(
                "❌ 任务派发失败：无法创建tmux窗口或窗格，请检查tmux配置"
            )
            raise typer.Exit(code=1)

    # 检测tmux并在需要时启动（在参数解析之后）
    # 传入 config_file 以便在检查前加载配置
    check_and_launch_tmux(config_file=config_file)

    init_env(
        "欢迎使用 Jarvis-CodeAgent，您的代码工程助手已准备就绪！",
        config_file=config_file,
        llm_group=llm_group,
    )

    # 设置代理节点
    if proxy_node:
        jglobals.proxy_node = proxy_node
    if master_url:
        jglobals.master_url = master_url
    if agent_id:
        jglobals.agent_id = agent_id

    if web_gateway:
        try:
            import threading

            import uvicorn

            from jarvis.jarvis_web_gateway.app import create_app

            # 检测认证方式：Token 认证（新）或密码认证（旧）
            auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
            if auth_token:
                pass
                # Token 认证：validate_gateway_token() 会直接从环境变量读取
            elif gateway_password:
                # 旧密码认证（兼容模式）
                from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

                if "gateway_auth" not in GLOBAL_CONFIG_DATA:
                    GLOBAL_CONFIG_DATA["gateway_auth"] = {}
                GLOBAL_CONFIG_DATA["gateway_auth"]["password"] = gateway_password
                GLOBAL_CONFIG_DATA["gateway_auth"]["enable"] = True
                GLOBAL_CONFIG_DATA["gateway_auth"]["allow_unset"] = False

            # 创建自定义 FastAPI app，添加状态查询接口
            from fastapi import FastAPI, Request
            from fastapi.responses import JSONResponse
            from jarvis.jarvis_web_gateway.app import get_current_execution_status

            custom_app = FastAPI()

            @custom_app.get("/status")
            async def get_status() -> dict:
                """获取 Agent 运行状态。

                返回状态说明：
                - execution_status: 任务执行状态（running/waiting_multi/waiting_single）
                - status: 进程状态（永远返回 running，因为进程还在运行）
                """
                return {
                    "execution_status": get_current_execution_status(),
                    "status": "running",  # Agent 进程状态（永远返回 running，因为进程还在运行）
                }

            @custom_app.get("/diff")
            async def get_diff_api() -> dict:
                """获取从 start_commit 到当前代码的 diff（结构化数据）。

                返回:
                    dict: 包含结构化 diff 数据的字典
                        - diff: 原始 diff 文本（兼容旧接口）
                        - files: 结构化数据列表
                """
                from jarvis.jarvis_utils.globals import (
                    global_agents,
                    running_agent_stack,
                )
                from jarvis.jarvis_code_agent.diff_visualizer import (
                    parse_diff_to_structured_data,
                )

                # 获取根agent（running_agent_stack中第一个，即最早启动的agent）
                if running_agent_stack:
                    root_agent_name = running_agent_stack[0]
                    root_agent = global_agents.get(root_agent_name)
                    if (
                        root_agent
                        and hasattr(root_agent, "start_commit")
                        and root_agent.start_commit
                    ):
                        diff_content = get_diff_between_commits(root_agent.start_commit)
                        # 解析为结构化数据
                        structured_data = parse_diff_to_structured_data(diff_content)
                        return {"diff": diff_content, "files": structured_data}
                return {"diff": "", "files": []}

            @custom_app.get("/rules")
            async def get_rules_api() -> dict:
                """获取规则信息（总体的和已加载的）。"""
                from jarvis.jarvis_web_gateway.common_endpoints import get_rules_info

                return get_rules_info()

            @custom_app.get("/tools")
            async def get_tools_api() -> dict:
                """获取工具信息（全量工具和允许使用的工具）。"""
                from jarvis.jarvis_web_gateway.common_endpoints import get_tools_info

                return get_tools_info()

            @custom_app.post("/sessions/save")
            async def save_session():
                """保存当前会话并返回文件路径。"""
                try:
                    from jarvis.jarvis_utils.globals import (
                        global_agents,
                        running_agent_stack,
                    )

                    # 获取根agent（running_agent_stack中第一个，即最早启动的agent）
                    if not running_agent_stack:
                        return {"success": False, "error": "No active agent"}

                    root_agent_name = running_agent_stack[0]
                    agent = global_agents.get(root_agent_name)

                    if agent is None:
                        return {"success": False, "error": "No active agent"}

                    # 调用 session_manager 的 save_session 方法
                    result = agent.session.save_session()
                    if result:
                        # 获取保存的会话文件路径
                        session_file = agent.session.last_restored_session or ""
                        return {
                            "success": True,
                            "session_file": session_file,
                            "message": "Session saved successfully",
                        }
                    else:
                        return {"success": False, "error": "Failed to save session"}
                except Exception as e:
                    return {"success": False, "error": str(e)}

            @custom_app.post("/update_token")
            async def update_token(request: Request):
                """更新 Agent 的认证 Token。

                当主网关重启后 Token 发生变化时，子网关通过此端点通知 Agent 更新 Token。

                参数:
                    token: 新的认证 Token

                返回:
                    dict: 操作结果
                """
                try:
                    # 验证 Authorization Bearer token
                    auth_header = request.headers.get("Authorization", "")
                    current_token = os.environ.get("JARVIS_AUTH_TOKEN", "")
                    if not auth_header or not auth_header.startswith("Bearer "):
                        return JSONResponse(
                            status_code=401,
                            content={"success": False, "error": "unauthorized"},
                        )
                    if auth_header[7:] != current_token:
                        return JSONResponse(
                            status_code=401,
                            content={"success": False, "error": "invalid token"},
                        )

                    body = await request.json()
                    new_token = body.get("token")
                    if not new_token:
                        return {"success": False, "error": "token is required"}

                    os.environ["JARVIS_AUTH_TOKEN"] = new_token
                    logger.info("Auth token updated via /update_token endpoint")
                    return {"success": True}
                except Exception as e:
                    logger.error("Failed to update token: %s", e)
                    return {"success": False, "error": str(e)}

            @custom_app.post("/message")
            async def receive_message(request: dict):
                """接收消息并添加到输入缓冲区。

                参数:
                    sender_id: 发送方 ID
                    content: 消息内容

                返回:
                    dict: 操作结果
                """
                try:
                    sender_id = request.get("sender_id")
                    content = request.get("content")

                    if not content:
                        return {"success": False, "error": "content is required"}

                    # 构建消息格式：Agent xxxx 发来消息：yyyyy
                    if sender_id:
                        message = f"Agent {sender_id} 发来消息：{content}"
                    else:
                        message = f"Agent 发来消息：{content}"

                    # 如果 Agent 正在等待输入，直接注入到输入流实现即时送达
                    if jglobals.input_inject_callback is not None:
                        jglobals.input_inject_callback(message)
                        delivered = "instant"
                    else:
                        # 否则存入缓冲区，等待下一轮循环消费
                        jglobals.input_buffer.append(message)
                        delivered = "buffered"

                    # 打印收到的消息到终端
                    PrettyOutput.auto_print(f"[收到消息] {message}")

                    return {
                        "success": True,
                        "data": {
                            "sender_id": sender_id,
                            "content": content,
                            "delivered": delivered,
                        },
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}

            config = uvicorn.Config(
                create_app(custom_app=custom_app),
                host="127.0.0.1",
                port=web_gateway_port,
                log_level="info",
            )
            web_gateway_server = uvicorn.Server(config)
            thread = threading.Thread(target=web_gateway_server.run, daemon=True)
            thread.start()
            PrettyOutput.auto_print(
                f"🌐 Web Gateway 已启动: ws://127.0.0.1:{web_gateway_port}/ws"
            )
        except Exception as web_gateway_err:
            try:
                from jarvis.jarvis_gateway.manager import set_current_gateway

                set_current_gateway(None)
            except Exception:
                pass
            PrettyOutput.auto_print(f"⚠️ 启动 Web Gateway 失败: {str(web_gateway_err)}")

    # CodeAgent 单实例互斥：改为按仓库维度加锁（延后至定位仓库根目录后执行）
    # 锁的获取移动到确认并切换到git根目录之后

    # 在初始化环境后同步 CLI 选项到全局配置，避免被 init_env 覆盖
    try:
        if llm_group:
            set_config("llm_group", str(llm_group))
        if tool_group:
            set_config("tool_group", str(tool_group))
        if restore or restore_session is not None or is_auto_resume_session():
            set_config("restore_session", True)
            # 如果用户指定了文件路径，检查文件是否存在
            if restore_session is not None and restore_session != "":
                if not os.path.exists(restore_session):
                    PrettyOutput.auto_print(f"❌ 会话文件不存在: {restore_session}")
                    return
        if print_prompt:
            set_config("print_prompt", True)
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

                # 初始化 .gitignore 文件，包含所有语言的默认忽略规则
                from jarvis.jarvis_utils.git_utils import (
                    get_default_gitignore_templates,
                )

                gitignore_path = ".gitignore"
                default_templates = get_default_gitignore_templates()
                with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(default_templates + "\n")
                PrettyOutput.auto_print("✅ 已创建 .gitignore 并添加各语言默认忽略规则")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                PrettyOutput.auto_print(f"❌ 初始化git仓库失败: {e}")
                sys.exit(1)
        else:
            PrettyOutput.auto_print("ℹ️ 操作已取消。Jarvis需要在git仓库中运行。")
            sys.exit(0)

    curr_dir = os.getcwd()
    find_git_root_and_cd(curr_dir)
    # 获取 git 仓库根目录（用于文件锁和 worktree 管理）
    repo_root = os.getcwd()
    # 在定位到 git 根目录后，按仓库维度加锁，避免跨仓库互斥
    # worktree 模式下不需要创建文件锁，因为 worktree 本身就是为了隔离不同任务
    if not worktree:
        try:
            lock_name = f"code_agent_{hashlib.md5(repo_root.encode('utf-8'), usedforsecurity=False).hexdigest()}.lock"
            _acquire_single_instance_lock(lock_name=lock_name)
        except Exception:
            # 回退到全局锁，确保至少有互斥保护
            _acquire_single_instance_lock(lock_name="code_agent.lock")

    # Worktree 管理
    worktree_manager = None
    original_branch = None
    if worktree:
        try:
            PrettyOutput.auto_print("🌿 Git Worktree 模式已启用")
            worktree_manager = WorktreeManager(repo_root)
            original_branch = worktree_manager.get_current_branch()
            PrettyOutput.auto_print(f"📍 当前分支: {original_branch}")

            # 创建 worktree
            worktree_path = worktree_manager.create_worktree()

            # 切换到 worktree 目录
            os.chdir(worktree_path)
            repo_root = worktree_path
            PrettyOutput.auto_print(f"✅ 已切换到 worktree 目录: {worktree_path}")
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 创建 worktree 失败: {str(e)}")
            sys.exit(1)
    try:
        output_content: Optional[str] = ""
        import json

        try:
            exit_code = 0
            error_message = ""
            try:
                if task:
                    # 单次任务模式：创建agent并执行
                    agent = CodeAgent(
                        need_summary=False,
                        append_tools=append_tools,
                        tool_group=tool_group,
                        non_interactive=non_interactive,
                        rule_names=rule_names,
                        disable_review=disable_review,
                        review_max_iterations=review_max_iterations,
                        allow_savesession=True,
                        optimize_system_prompt=optimize_system_prompt,
                        quick_mode=quick_mode or is_enable_quick_mode(),
                    )

                    # 尝试恢复会话
                    if restore or restore_session is not None:
                        if agent.restore_session(
                            restore_session if restore_session else True
                        ):
                            # 显示实际恢复的session文件名
                            restored_file = agent.session.last_restored_session
                            if restored_file:
                                file_basename = os.path.basename(restored_file)
                                PrettyOutput.auto_print(
                                    f"✅ 已从 {file_basename} 恢复会话。"
                                )
                        else:
                            PrettyOutput.auto_print("⚠️ 无法恢复会话。")

                    output_content = agent.run(task, prefix=prefix, suffix=suffix)
                    # 单次任务模式：任务完成后直接退出
                    raise typer.Exit(code=0)
                else:
                    # 循环任务模式：每次迭代创建新的agent实例，避免任务间污染

                    # 创建第一个 agent 实例（用于会话恢复和第一条任务）
                    agent = CodeAgent(
                        need_summary=False,
                        append_tools=append_tools,
                        tool_group=tool_group,
                        non_interactive=non_interactive,
                        rule_names=rule_names,
                        disable_review=disable_review,
                        review_max_iterations=review_max_iterations,
                        allow_savesession=True,
                        optimize_system_prompt=optimize_system_prompt,
                        quick_mode=quick_mode or is_enable_quick_mode(),
                    )

                    # 检测与当前commit一致的历史会话（仅在交互模式且未指定restore_session时）
                    if (
                        not non_interactive
                        and not restore_session
                        and not is_auto_resume_session()
                    ):
                        try:
                            current_commit = get_latest_commit_hash()
                            if current_commit:
                                matching_sessions = (
                                    agent.session._find_sessions_by_commit(
                                        current_commit
                                    )
                                )
                                if matching_sessions:
                                    selected_session = agent.session._prompt_to_restore_matching_sessions(
                                        matching_sessions
                                    )
                                    if selected_session:
                                        # 用户选择恢复会话，使用统一的恢复方法
                                        # 该方法会执行完整的检测：commit一致性、平台重新创建、token兼容性
                                        session_name = agent.session._read_session_name(
                                            selected_session
                                        )
                                        if agent.session.restore_session_from_file(
                                            selected_session, session_name
                                        ):
                                            # 设置first标志为False，避免run()方法执行需求分类和方法论加载
                                            agent.first = False
                                            file_basename = os.path.basename(
                                                selected_session
                                            )
                                            PrettyOutput.auto_print(
                                                f"✅ 已从 {file_basename} 恢复会话。"
                                            )
                        except Exception as e:
                            # 检测失败不影响主流程
                            PrettyOutput.auto_print(f"⚠️  检测历史会话失败: {e}")

                    # 如果指定了会话恢复，先恢复会话（让用户先选择会话，再输入需求）
                    if (
                        restore
                        or restore_session is not None
                        or is_auto_resume_session()
                    ):
                        if agent.restore_session(
                            restore_session if restore_session else True
                        ):
                            # 显示实际恢复的session文件名
                            restored_file = agent.session.last_restored_session
                            if restored_file:
                                file_basename = os.path.basename(restored_file)
                                PrettyOutput.auto_print(
                                    f"✅ 已从 {file_basename} 恢复会话。"
                                )
                        else:
                            PrettyOutput.auto_print("⚠️ 无法恢复会话。")

                    user_input = get_multiline_input("请输入你的需求（Ctrl+C 退出）")
                    if not user_input:
                        raise typer.Exit(code=0)

                    # 使用当前 agent 执行任务
                    output_content = agent.run(user_input, prefix=prefix, suffix=suffix)

                    # 任务正常退出
                    raise typer.Exit(code=0)
            except typer.Exit:
                # 正常退出，设置成功状态
                exit_code = 0
                error_message = ""
                # agent.run() 正常结束时output_content应该已经有了值
            except Exception as exec_err:
                exit_code = 1
                error_message = str(exec_err)
                raise
        finally:
            # 如果是tmux并行任务，写入状态文件
            if status_file_path:
                import json
                from pathlib import Path

                try:
                    # 写入状态文件
                    status_data = {
                        "status": "completed" if exit_code == 0 else "failed",
                        "exit_code": exit_code,
                    }
                    status_file_path.write_text(
                        json.dumps(status_data, ensure_ascii=False), encoding="utf-8"
                    )

                    # 写入输出文件（如果存在）
                    output_file = status_file_path.with_suffix(".output")

                    # 将捕获的输出内容写入文件
                    def _convert_to_string(content: Any) -> str:
                        if content is None:
                            return ""
                        try:
                            # 尝试序列化，如果失败则转换为字符串
                            json.dumps(content)
                            return json.dumps(content, ensure_ascii=False, indent=2)
                        except (TypeError, ValueError):
                            # 无法序列化时，转换为字符串
                            return str(content)

                    output_content_str = _convert_to_string(output_content)
                    try:
                        output_file.write_text(output_content_str, encoding="utf-8")
                    except Exception as output_err:
                        # 如果写入输出失败，记录错误
                        PrettyOutput.auto_print(
                            f"⚠️ 写入输出文件失败: {str(output_err)}"
                        )
                        pass

                    # 写入错误文件
                    if exit_code != 0 and error_message:
                        error_file = status_file_path.with_suffix(".error")
                        try:
                            error_file.write_text(error_message, encoding="utf-8")
                        except Exception:
                            pass
                except Exception as status_err:
                    PrettyOutput.auto_print(f"⚠️ 写入状态文件失败: {str(status_err)}")

            # Worktree 合并逻辑（确保所有退出路径都会执行）
            if worktree and worktree_manager and original_branch:
                _handle_worktree_merge(
                    worktree_manager, original_branch, non_interactive
                )

            if web_gateway_server is not None:
                try:
                    web_gateway_server.should_exit = True
                except Exception:
                    pass
                try:
                    from jarvis.jarvis_gateway.manager import set_current_gateway

                    set_current_gateway(None)
                except Exception:
                    pass

    except typer.Exit:
        raise
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {str(e)}")
        sys.exit(1)


def _handle_worktree_merge(
    worktree_manager: "WorktreeManager",
    original_branch: str,
    non_interactive: bool,
) -> None:
    """处理 worktree rebase 并合并逻辑

    使用 rebase 策略：先在 worktree 分支上执行 rebase 到原分支，
    然后通过 fast-forward 合并，保持线性历史。

    参数:
        worktree_manager: WorktreeManager 实例
        original_branch: 原始分支名
        non_interactive: 是否为非交互模式
    """
    try:
        worktree_info = worktree_manager.get_worktree_info()
        worktree_branch = worktree_info.get("worktree_branch")
        worktree_path = worktree_info.get("worktree_path")

        PrettyOutput.auto_print(f"🌿 Worktree 分支: {worktree_branch}")
        PrettyOutput.auto_print(f"📁 Worktree 路径: {worktree_path}")

        # 询问用户是否 rebase 并合并（交互模式）或自动执行（非交互模式）
        should_merge = False
        if non_interactive:
            should_merge = True
            PrettyOutput.auto_print("🤖 非交互模式：自动 rebase 并合并 worktree 分支")
        else:
            should_merge = user_confirm(
                f"是否将 worktree 分支 '{worktree_branch}' 变基并合并回 '{original_branch}'？",
                default=True,
            )

        if should_merge:
            # Rebase 并合并 worktree 分支
            merge_success = worktree_manager.merge_back(
                original_branch, non_interactive
            )
            if merge_success:
                PrettyOutput.auto_print("✅ Worktree 分支已成功 rebase 并合并")
                # 自动清理 worktree 目录
                PrettyOutput.auto_print("🧹 正在清理 worktree 目录...")
                cleanup_success = worktree_manager.cleanup()
                if cleanup_success:
                    PrettyOutput.auto_print(
                        f"✅ Worktree 目录已自动删除: {worktree_path}"
                    )
                else:
                    PrettyOutput.auto_print(
                        f"⚠️ Worktree 目录删除失败，请手动清理: {worktree_path}"
                    )
                    PrettyOutput.auto_print(f"   git worktree remove {worktree_branch}")
            else:
                PrettyOutput.auto_print(
                    f"⚠️ Rebase/合并失败或取消，worktree 分支 '{worktree_branch}' 保留"
                )
                PrettyOutput.auto_print(
                    "💡 提示：您可以稍后手动 rebase 并合并或清理 worktree："
                )
                PrettyOutput.auto_print(f"   cd {worktree_path}")
                PrettyOutput.auto_print(f"   git checkout {original_branch}")
                PrettyOutput.auto_print(f"   git rebase {worktree_branch}")
        else:
            PrettyOutput.auto_print(
                f"ℹ️ worktree 分支 '{worktree_branch}' 已保留，您可以稍后手动 rebase 并合并"
            )
            PrettyOutput.auto_print(f"💡 提示：worktree 路径: {worktree_path}")

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 处理 worktree 合并时出错: {str(e)}")


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
