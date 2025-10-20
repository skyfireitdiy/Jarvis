# -*- coding: utf-8 -*-
# 标准库导入
import datetime
import os
import platform
import re
import sys
from pathlib import Path
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union


# 第三方库导入
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# 本地库导入
# jarvis_agent 相关
from jarvis.jarvis_agent.prompt_builder import build_action_prompt
from jarvis.jarvis_agent.protocols import OutputHandlerProtocol
from jarvis.jarvis_agent.session_manager import SessionManager
from jarvis.jarvis_agent.tool_executor import execute_tool_call
from jarvis.jarvis_agent.memory_manager import MemoryManager
from jarvis.jarvis_memory_organizer.memory_organizer import MemoryOrganizer
from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer
from jarvis.jarvis_agent.file_methodology_manager import FileMethodologyManager
from jarvis.jarvis_agent.prompts import (
    DEFAULT_SUMMARY_PROMPT,
    SUMMARY_REQUEST_PROMPT,
    TASK_ANALYSIS_PROMPT,
)
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_agent.edit_file_handler import EditFileHandler
from jarvis.jarvis_agent.rewrite_file_handler import RewriteFileHandler
from jarvis.jarvis_agent.prompt_manager import PromptManager
from jarvis.jarvis_agent.event_bus import EventBus
from jarvis.jarvis_agent.run_loop import AgentRunLoop
from jarvis.jarvis_agent.events import (
    BEFORE_SUMMARY,
    AFTER_SUMMARY,
    TASK_COMPLETED,
    TASK_STARTED,
    BEFORE_ADDON_PROMPT,
    AFTER_ADDON_PROMPT,
    BEFORE_HISTORY_CLEAR,
    AFTER_HISTORY_CLEAR,
    BEFORE_MODEL_CALL,
    AFTER_MODEL_CALL,
    INTERRUPT_TRIGGERED,
    BEFORE_TOOL_FILTER,
    TOOL_FILTERED,
    AFTER_TOOL_CALL,
)
from jarvis.jarvis_agent.user_interaction import UserInteractionHandler
from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.methodology import _load_all_methodologies
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_agent.file_context_handler import file_context_handler
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler

# jarvis_platform 相关
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry

# jarvis_utils 相关
from jarvis.jarvis_utils.config import (
    get_data_dir,
    get_normal_model_name,
    get_normal_platform_name,
    is_execute_tool_confirm,
    is_force_save_memory,
    is_use_analysis,
    is_use_methodology,
    get_tool_filter_threshold,
    get_after_tool_call_cb_dirs,
    get_plan_max_depth,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import (
    delete_agent,
    get_interrupt,
    make_agent_name,
    set_agent,
    set_interrupt,
)
from jarvis.jarvis_utils.input import get_multiline_input, user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ot


def show_agent_startup_stats(
    agent_name: str,
    model_name: str,
    tool_registry_instance: Optional[Any] = None,
    platform_name: Optional[str] = None,
) -> None:
    """输出启动时的统计信息

    参数:
        agent_name: Agent的名称
        model_name: 使用的模型名称
    """
    try:
        methodologies = _load_all_methodologies()
        methodology_count = len(methodologies)

        # 获取工具数量
        # 创建一个临时的工具注册表类来获取所有工具（不应用过滤）
        class TempToolRegistry(ToolRegistry):
            def _apply_tool_config_filter(self) -> None:
                """重写过滤方法，不执行任何过滤"""
                pass

        # 获取所有工具的数量
        tool_registry_all = TempToolRegistry()
        total_tool_count = len(tool_registry_all.tools)

        # 获取可用工具的数量（应用过滤）
        if tool_registry_instance is not None:
            available_tool_count = len(tool_registry_instance.get_all_tools())
        else:
            tool_registry = ToolRegistry()
            available_tool_count = len(tool_registry.get_all_tools())

        global_memory_dir = Path(get_data_dir()) / "memory" / "global_long_term"
        global_memory_count = 0
        if global_memory_dir.exists():
            global_memory_count = len(list(global_memory_dir.glob("*.json")))

        # 检查项目记忆
        project_memory_dir = Path(".jarvis/memory")
        project_memory_count = 0
        if project_memory_dir.exists():
            project_memory_count = len(list(project_memory_dir.glob("*.json")))

        # 获取当前工作目录
        current_dir = os.getcwd()

        # 构建欢迎信息
        platform = platform_name or get_normal_platform_name()
        welcome_message = f"{agent_name} 初始化完成 - 使用 {platform} 平台 {model_name} 模型"

        stats_parts = [
            f"📚  本地方法论: [bold cyan]{methodology_count}[/bold cyan]",
            f"🛠️  工具: [bold green]{available_tool_count}/{total_tool_count}[/bold green] (可用/全部)",
            f"🧠  全局记忆: [bold yellow]{global_memory_count}[/bold yellow]",
        ]

        # 如果有项目记忆，添加到统计信息中
        if project_memory_count > 0:
            stats_parts.append(
                f"📝  项目记忆: [bold magenta]{project_memory_count}[/bold magenta]"
            )

        stats_text = Text.from_markup(" | ".join(stats_parts), justify="center")

        # 创建包含欢迎信息和统计信息的面板内容
        panel_content = Text()
        panel_content.append(welcome_message, style="bold white")
        panel_content.append("\n")
        panel_content.append(f"📁  工作目录: {current_dir}", style="dim white")
        panel_content.append("\n\n")
        panel_content.append(stats_text)
        panel_content.justify = "center"

        panel = Panel(
            panel_content,
            title="✨ Jarvis 资源概览 ✨",
            title_align="center",
            border_style="blue",
            expand=False,
        )

        console = Console()
        console.print(Align.center(panel))

    except Exception as e:
        PrettyOutput.print(f"加载统计信息失败: {e}", OutputType.WARNING)


origin_agent_system_prompt = f"""
<role>
# 🤖 角色
你是一个专业的任务执行助手，根据用户需求制定并执行详细的计划。
</role>

<rules>
# ❗ 核心规则
1.  **单步操作**: 每个响应必须包含且仅包含一个工具调用。
2.  **任务终结**: 当任务完成时，明确指出任务已完成。这是唯一可以不调用工具的例外。
3.  **无响应错误**: 空响应或仅有分析无工具调用的响应是致命错误，会导致系统挂起。
4.  **决策即工具**: 所有的决策和分析都必须通过工具调用来体现。
5.  **等待结果**: 在继续下一步之前，必须等待当前工具的执行结果。
6.  **持续推进**: 除非任务完成，否则必须生成可操作的下一步。
7.  **记录沉淀**: 如果解决方案有普适价值，应记录为方法论。
8.  **用户语言**: 始终使用用户的语言进行交流。
</rules>

<workflow>
# 🔄 工作流程
1.  **分析**: 理解和分析问题，定义清晰的目标。
2.  **设计**: 设计解决方案并制定详细的行动计划。
3.  **执行**: 按照计划，一次一个步骤地执行。
4.  **完成**: 验证任务是否达成目标，并进行总结。
</workflow>

<sub_agents_guide>
# 子任务工具使用建议
- 使用 sub_code_agent（代码子Agent）当：
  - 需要在当前任务下并行推进较大且相对独立的代码改造
  - 涉及多文件/多模块的大范围变更，或需要较长的工具调用链
  - 需要隔离上下文以避免污染当前对话（如探索性改动、PoC）
  - 需要专注于单一代码子问题，阶段性产出可复用的结果
- 使用 sub_agent（通用子Agent）当：
  - 子任务不是以代码改造为主（如调研、方案撰写、评审总结、用例设计、文档生成等）
  - 只是需要短期分流一个轻量的辅助性子任务
说明：
- 两者仅需参数 task（可选 background 提供上下文），完成后返回结果给父Agent
- 子Agent将自动完成并生成总结，请在上层根据返回结果继续编排
</sub_agents_guide>

<system_info>
# 系统信息
- OS: {platform.platform()} {platform.version()}
- Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</system_info>
"""


class LoopAction(Enum):
    SKIP_TURN = "skip_turn"
    CONTINUE = "continue"
    COMPLETE = "complete"


class Agent:
    # Attribute type annotations to satisfy static type checkers
    event_bus: EventBus
    memory_manager: MemoryManager
    task_analyzer: TaskAnalyzer
    file_methodology_manager: FileMethodologyManager
    prompt_manager: PromptManager
    model: BasePlatform
    session: SessionManager

    def clear_history(self):
        """
        Clears the current conversation history by delegating to the session manager.
        Emits BEFORE_HISTORY_CLEAR/AFTER_HISTORY_CLEAR and reapplies system prompt to preserve constraints.
        """
        # 广播清理历史前事件（不影响主流程）
        try:
            self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

        # 清理会话历史并重置模型状态
        self.session.clear_history()

        # 重置后重新设置系统提示词，确保系统约束仍然生效
        try:
            self._setup_system_prompt()
        except Exception:
            pass

        # 广播清理历史后的事件
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

    def __del__(self):
        # 只有在记录启动时才停止记录
        try:
            name = getattr(self, "name", None)
            if name:
                delete_agent(name)
        except Exception:
            pass

    def get_tool_usage_prompt(self) -> str:
        """获取工具使用提示"""
        return build_action_prompt(self.output_handler)  # type: ignore

    def __new__(cls, *args, **kwargs):
        if kwargs.get("agent_type") == "code":
            try:
                from jarvis.jarvis_code_agent.code_agent import CodeAgent
            except ImportError as e:
                raise RuntimeError(
                    "CodeAgent could not be imported. Please ensure jarvis_code_agent is installed correctly."
                ) from e

            # 移除 agent_type 避免无限循环，并传递所有其他参数
            kwargs.pop("agent_type", None)
            return CodeAgent(**kwargs)
        else:
            return super().__new__(cls)

    def __init__(
        self,
        system_prompt: str,
        name: str = "Jarvis",
        description: str = "",
        model_group: Optional[str] = None,
        summary_prompt: Optional[str] = None,
        auto_complete: bool = False,
        output_handler: Optional[List[OutputHandlerProtocol]] = None,
        use_tools: Optional[List[str]] = None,
        execute_tool_confirm: Optional[bool] = None,
        need_summary: bool = True,
        auto_summary_rounds: Optional[int] = None,
        multiline_inputer: Optional[Callable[[str], str]] = None,
        use_methodology: Optional[bool] = None,
        use_analysis: Optional[bool] = None,
        force_save_memory: Optional[bool] = None,
        files: Optional[List[str]] = None,
        confirm_callback: Optional[Callable[[str, bool], bool]] = None,
        non_interactive: Optional[bool] = None,
        in_multi_agent: Optional[bool] = None,
        plan: bool = False,
        plan_max_depth: Optional[int] = None,
        plan_depth: int = 0,
        agent_type: str = "normal",
        **kwargs,
    ):
        """初始化Jarvis Agent实例

        参数:
            system_prompt: 系统提示词，定义Agent的行为准则
            name: Agent名称，默认为"Jarvis"
            description: Agent描述信息

            summary_prompt: 任务总结提示模板
            auto_complete: 是否自动完成任务
            execute_tool_confirm: 执行工具前是否需要确认
            need_summary: 是否需要生成总结
            multiline_inputer: 多行输入处理器
            use_methodology: 是否使用方法论
            use_analysis: 是否使用任务分析
            force_save_memory: 是否强制保存记忆
            confirm_callback: 用户确认回调函数，签名为 (tip: str, default: bool) -> bool；默认使用CLI的user_confirm
            non_interactive: 是否以非交互模式运行（优先级最高，覆盖环境变量与配置）
            plan: 是否启用任务规划与子任务拆分（默认 False；启用后在进入主循环前评估是否需要将任务拆分为 <SUB_TASK> 列表，逐一由子Agent执行并汇总结果）
            plan_max_depth: 任务规划的最大层数（默认3，可通过配置 JARVIS_PLAN_MAX_DEPTH 或入参覆盖）
            plan_depth: 当前规划层数（内部用于递归控制，子Agent会在父基础上+1）
        """
        # 基础属性初始化（仅根据入参设置原始值；实际生效的默认回退在 _init_config 中统一解析）
        # 标识与描述
        self.name = make_agent_name(name)
        self.description = description
        self.system_prompt = system_prompt
        # 行为控制开关（原始入参值）
        self.auto_complete = bool(auto_complete)
        self.need_summary = bool(need_summary)
        # 自动摘要轮次：None 表示使用配置文件中的默认值，由 AgentRunLoop 决定最终取值
        self.auto_summary_rounds = auto_summary_rounds
        self.use_methodology = use_methodology
        self.use_analysis = use_analysis
        self.execute_tool_confirm = execute_tool_confirm
        self.summary_prompt = summary_prompt
        self.force_save_memory = force_save_memory
        # 资源与环境
        self.model_group = model_group
        self.files = files or []
        self.use_tools = use_tools
        self.non_interactive = non_interactive
        # 多智能体运行标志：用于控制非交互模式下的自动完成行为
        self.in_multi_agent = bool(in_multi_agent)
        self.plan = bool(plan)
        # 规划深度与上限
        try:
            self.plan_max_depth = (
                int(plan_max_depth) if plan_max_depth is not None else int(get_plan_max_depth())
            )
        except Exception:
            self.plan_max_depth = 3
        try:
            self.plan_depth = int(plan_depth)
        except Exception:
            self.plan_depth = 0
        # 运行时状态
        self.first = True
        self.run_input_handlers_next_turn = False
        self.user_data: Dict[str, Any] = {}


        # 用户确认回调：默认使用 CLI 的 user_confirm，可由外部注入以支持 TUI/GUI
        self.confirm_callback: Callable[[str, bool], bool] = (
            confirm_callback or user_confirm  # type: ignore[assignment]
        )

        # 初始化模型和会话
        self._init_model(model_group)
        self._init_session()

        # 初始化处理器
        self._init_handlers(
            multiline_inputer,
            output_handler,
            use_tools or [],
        )
        # 初始化用户交互封装，保持向后兼容
        self.user_interaction = UserInteractionHandler(self.multiline_inputer, self.confirm_callback)
        # 将确认函数指向封装后的 confirm，保持既有调用不变
        self.confirm_callback = self.user_interaction.confirm  # type: ignore[assignment]
        # 非交互模式参数支持：允许通过构造参数显式控制，便于其他Agent调用时设置
        try:
            # 优先使用构造参数，其次回退到环境变量
            self.non_interactive = (
                bool(non_interactive)
                if non_interactive is not None
                else str(os.environ.get("JARVIS_NON_INTERACTIVE", "")).lower() in ("1", "true", "yes")
            )
            # 如果构造参数显式提供，则同步到环境变量与全局配置，供下游组件读取
            if non_interactive is not None:
                os.environ["JARVIS_NON_INTERACTIVE"] = "true" if self.non_interactive else "false"

        except Exception:
            # 防御式回退
            self.non_interactive = False

        # 初始化配置（直接解析，不再依赖 _init_config）
        try:
            resolved_use_methodology = bool(use_methodology if use_methodology is not None else is_use_methodology())
        except Exception:
            resolved_use_methodology = bool(use_methodology) if use_methodology is not None else True

        try:
            resolved_use_analysis = bool(use_analysis if use_analysis is not None else is_use_analysis())
        except Exception:
            resolved_use_analysis = bool(use_analysis) if use_analysis is not None else True

        try:
            resolved_execute_tool_confirm = bool(execute_tool_confirm if execute_tool_confirm is not None else is_execute_tool_confirm())
        except Exception:
            resolved_execute_tool_confirm = bool(execute_tool_confirm) if execute_tool_confirm is not None else False

        try:
            resolved_force_save_memory = bool(force_save_memory if force_save_memory is not None else is_force_save_memory())
        except Exception:
            resolved_force_save_memory = bool(force_save_memory) if force_save_memory is not None else False

        self.use_methodology = resolved_use_methodology
        self.use_analysis = resolved_use_analysis
        self.execute_tool_confirm = resolved_execute_tool_confirm
        self.summary_prompt = (summary_prompt or DEFAULT_SUMMARY_PROMPT)
        self.force_save_memory = resolved_force_save_memory
        # 多智能体模式下，默认不自动完成（即使是非交互），仅在明确传入 auto_complete=True 时开启
        if self.in_multi_agent:
            self.auto_complete = bool(self.auto_complete)
        else:
            # 非交互模式下默认自动完成；否则保持传入的 auto_complete 值
            self.auto_complete = bool(self.auto_complete or (self.non_interactive or False))

        # 初始化事件总线需先于管理器，以便管理器在构造中安全订阅事件
        self.event_bus = EventBus()
        # 初始化管理器
        self.memory_manager = MemoryManager(self)
        self.task_analyzer = TaskAnalyzer(self)
        self.file_methodology_manager = FileMethodologyManager(self)
        self.prompt_manager = PromptManager(self)

        # 设置系统提示词
        self._setup_system_prompt()

        # 输出统计信息（包含欢迎信息）
        show_agent_startup_stats(
            name,
            self.model.name(),
            self.get_tool_registry(),  # type: ignore
            platform_name=self.model.platform_name(),  # type: ignore
        )
        # 动态加载工具调用后回调
        self._load_after_tool_callbacks()

    def _init_model(self, model_group: Optional[str]):
        """初始化模型平台（统一使用 normal 平台/模型）"""
        platform_name = get_normal_platform_name(model_group)
        model_name = get_normal_model_name(model_group)

        maybe_model = PlatformRegistry().create_platform(platform_name)
        if maybe_model is None:
            PrettyOutput.print(
                f"平台 {platform_name} 不存在，将使用普通模型", OutputType.WARNING
            )
            maybe_model = PlatformRegistry().get_normal_platform()

        # 在此处收敛为非可选类型，确保后续赋值满足类型检查
        self.model = maybe_model

        if model_name:
            self.model.set_model_name(model_name)

        self.model.set_model_group(model_group)
        self.model.set_suppress_output(False)

    def _init_session(self):
        """初始化会话管理器"""
        self.session = SessionManager(model=self.model, agent_name=self.name)  # type: ignore

    def _init_handlers(
        self,
        multiline_inputer: Optional[Callable[[str], str]],
        output_handler: Optional[List[OutputHandlerProtocol]],
        use_tools: List[str],
    ):
        """初始化各种处理器"""
        self.output_handler = output_handler or [ToolRegistry(),  EditFileHandler(), RewriteFileHandler()]
        self.set_use_tools(use_tools)
        self.input_handler = [
            builtin_input_handler,
            shell_input_handler,
            file_context_handler,
        ]
        self.multiline_inputer = multiline_inputer or get_multiline_input

    def _setup_system_prompt(self):
        """设置系统提示词"""
        try:
            if hasattr(self, "prompt_manager"):
                prompt_text = self.prompt_manager.build_system_prompt()
            else:
                action_prompt = self.get_tool_usage_prompt()
                prompt_text = f"""
{self.system_prompt}

{action_prompt}
"""
            self.model.set_system_prompt(prompt_text)  # type: ignore
        except Exception:
            # 回退到原始行为，确保兼容性
            action_prompt = self.get_tool_usage_prompt()
            self.model.set_system_prompt(  # type: ignore
                f"""
{self.system_prompt}

{action_prompt}
"""
            )

    def set_user_data(self, key: str, value: Any):
        """Sets user data in the session."""
        self.session.set_user_data(key, value)

    def get_user_data(self, key: str) -> Optional[Any]:
        """Gets user data from the session."""
        return self.session.get_user_data(key)

    def set_use_tools(self, use_tools):
        """设置要使用的工具列表"""
        for handler in self.output_handler:
            if isinstance(handler, ToolRegistry):
                if use_tools:
                    handler.use_tools(use_tools)
                break

    def set_addon_prompt(self, addon_prompt: str):
        """Sets the addon prompt in the session."""
        self.session.set_addon_prompt(addon_prompt)

    def set_run_input_handlers_next_turn(self, value: bool):
        """Sets the flag to run input handlers on the next turn."""
        self.run_input_handlers_next_turn = value

    def _multiline_input(self, tip: str, print_on_empty: bool) -> str:
        """
        Safe wrapper for multiline input to optionally suppress empty-input notice.
        If the configured multiline_inputer supports 'print_on_empty' keyword, pass it;
        otherwise, fall back to calling with a single argument for compatibility.
        """
        # 优先通过用户交互封装，便于未来替换 UI
        if hasattr(self, "user_interaction"):
            return self.user_interaction.multiline_input(tip, print_on_empty)
        try:
            # Try to pass the keyword for enhanced input handler
            return self.multiline_inputer(tip, print_on_empty=print_on_empty)  # type: ignore
        except TypeError:
            # Fallback for custom handlers that only accept one argument
            return self.multiline_inputer(tip)  # type: ignore

    def _load_after_tool_callbacks(self) -> None:
        """
        扫描 JARVIS_AFTER_TOOL_CALL_CB_DIRS 中的 Python 文件并动态注册回调。
        约定优先级（任一命中即注册）：
        - 模块级可调用对象: after_tool_call_cb
        - 工厂方法返回单个或多个可调用对象: get_after_tool_call_cb(), register_after_tool_call_cb()
        """
        try:
            dirs = get_after_tool_call_cb_dirs()
            if not dirs:
                return
            for d in dirs:
                p_dir = Path(d)
                if not p_dir.exists() or not p_dir.is_dir():
                    continue
                for file_path in p_dir.glob("*.py"):
                    if file_path.name == "__init__.py":
                        continue
                    parent_dir = str(file_path.parent)
                    added_path = False
                    try:
                        if parent_dir not in sys.path:
                            sys.path.insert(0, parent_dir)
                            added_path = True
                        module_name = file_path.stem
                        module = __import__(module_name)

                        candidates: List[Callable[[Any], None]] = []

                        # 1) 直接导出的回调
                        if hasattr(module, "after_tool_call_cb"):
                            obj = getattr(module, "after_tool_call_cb")
                            if callable(obj):
                                candidates.append(obj)  # type: ignore[arg-type]

                        # 2) 工厂方法：get_after_tool_call_cb()
                        if hasattr(module, "get_after_tool_call_cb"):
                            factory = getattr(module, "get_after_tool_call_cb")
                            if callable(factory):
                                try:
                                    ret = factory()
                                    if callable(ret):
                                        candidates.append(ret)
                                    elif isinstance(ret, (list, tuple)):
                                        for c in ret:
                                            if callable(c):
                                                candidates.append(c)
                                except Exception:
                                    pass

                        # 3) 工厂方法：register_after_tool_call_cb()
                        if hasattr(module, "register_after_tool_call_cb"):
                            factory2 = getattr(module, "register_after_tool_call_cb")
                            if callable(factory2):
                                try:
                                    ret2 = factory2()
                                    if callable(ret2):
                                        candidates.append(ret2)
                                    elif isinstance(ret2, (list, tuple)):
                                        for c in ret2:
                                            if callable(c):
                                                candidates.append(c)
                                except Exception:
                                    pass

                        for cb in candidates:
                            try:
                                def _make_wrapper(callback):
                                    def _wrapper(**kwargs: Any) -> None:
                                        try:
                                            agent = kwargs.get("agent")
                                            callback(agent)
                                        except Exception:
                                            pass
                                    return _wrapper
                                self.event_bus.subscribe(AFTER_TOOL_CALL, _make_wrapper(cb))
                            except Exception:
                                pass

                    except Exception as e:
                        PrettyOutput.print(f"从 {file_path} 加载回调失败: {e}", OutputType.WARNING)
                    finally:
                        if added_path:
                            try:
                                sys.path.remove(parent_dir)
                            except ValueError:
                                pass
        except Exception as e:
            PrettyOutput.print(f"加载回调目录时发生错误: {e}", OutputType.WARNING)

    def save_session(self) -> bool:
        """Saves the current session state by delegating to the session manager."""
        return self.session.save_session()

    def restore_session(self) -> bool:
        """Restores the session state by delegating to the session manager."""
        if self.session.restore_session():
            self.first = False
            return True
        return False

    def get_tool_registry(self) -> Optional[Any]:
        """获取工具注册表实例"""
        for handler in self.output_handler:
            if isinstance(handler, ToolRegistry):
                return handler
        return None

    def get_event_bus(self) -> EventBus:
        """获取事件总线实例"""
        return self.event_bus

    def _call_model(
        self, message: str, need_complete: bool = False, run_input_handlers: bool = True
    ) -> str:
        """调用AI模型并实现重试逻辑

        参数:
            message: 输入给模型的消息
            need_complete: 是否需要完成任务标记
            run_input_handlers: 是否运行输入处理器

        返回:
            str: 模型的响应

        注意:
            1. 将使用指数退避重试，最多重试30秒
            2. 会自动处理输入处理器链
            3. 会自动添加附加提示
            4. 会检查并处理上下文长度限制
        """
        # 处理输入
        if run_input_handlers:
            message = self._process_input(message)
            if not message:
                return ""

        # 添加附加提示
        message = self._add_addon_prompt(message, need_complete)

        # 管理对话长度
        message = self._manage_conversation_length(message)

        # 调用模型
        response = self._invoke_model(message)

        return response

    def _process_input(self, message: str) -> str:
        """处理输入消息"""
        for handler in self.input_handler:
            message, need_return = handler(message, self)
            if need_return:
                self._last_handler_returned = True
                return message
        self._last_handler_returned = False
        return message

    def _add_addon_prompt(self, message: str, need_complete: bool) -> str:
        """添加附加提示到消息"""
        # 广播添加附加提示前事件（不影响主流程）
        try:
            self.event_bus.emit(
                BEFORE_ADDON_PROMPT,
                agent=self,
                need_complete=need_complete,
                current_message=message,
                has_session_addon=bool(self.session.addon_prompt),
            )
        except Exception:
            pass

        addon_text = ""
        if self.session.addon_prompt:
            addon_text = self.session.addon_prompt
            message = join_prompts([message, addon_text])
            self.session.addon_prompt = ""
        else:
            addon_text = self.make_default_addon_prompt(need_complete)
            message = join_prompts([message, addon_text])

        # 广播添加附加提示后事件（不影响主流程）
        try:
            self.event_bus.emit(
                AFTER_ADDON_PROMPT,
                agent=self,
                need_complete=need_complete,
                addon_text=addon_text,
                final_message=message,
            )
        except Exception:
            pass
        return message

    def _manage_conversation_length(self, message: str) -> str:
        """管理对话长度计数；摘要触发由轮次在 AgentRunLoop 中统一处理。"""
        self.session.conversation_length += get_context_token_count(message)


        return message

    def _invoke_model(self, message: str) -> str:
        """实际调用模型获取响应"""
        if not self.model:
            raise RuntimeError("Model not initialized")

        # 事件：模型调用前
        try:
            self.event_bus.emit(
                BEFORE_MODEL_CALL,
                agent=self,
                message=message,
            )
        except Exception:
            pass

        response = self.model.chat_until_success(message)  # type: ignore
        # 防御: 模型可能返回空响应(None或空字符串)，统一为空字符串并告警
        if not response:
            try:
                PrettyOutput.print("模型返回空响应，已使用空字符串回退。", OutputType.WARNING)
            except Exception:
                pass
            response = ""
        
        # 事件：模型调用后
        try:
            self.event_bus.emit(
                AFTER_MODEL_CALL,
                agent=self,
                message=message,
                response=response,
            )
        except Exception:
            pass

        self.session.conversation_length += get_context_token_count(response)

        return response

    def generate_summary(self) -> str:
        """生成对话历史摘要

        返回:
            str: 包含对话摘要的字符串

        注意:
            仅生成摘要，不修改对话状态
        """

        try:
            if not self.model:
                raise RuntimeError("Model not initialized")
            # 优先使用外部传入的 summary_prompt；如为空则回退到默认的会话摘要请求
            safe_summary_prompt = self.summary_prompt or ""
            if isinstance(safe_summary_prompt, str) and safe_summary_prompt.strip() != "":
                prompt_to_use = safe_summary_prompt
            else:
                prompt_to_use = self.session.prompt + "\n" + SUMMARY_REQUEST_PROMPT

            summary = self.model.chat_until_success(prompt_to_use)  # type: ignore
            # 防御: 可能返回空响应(None或空字符串)，统一为空字符串并告警
            if not summary:
                try:
                    PrettyOutput.print("总结模型返回空响应，已使用空字符串回退。", OutputType.WARNING)
                except Exception:
                    pass
                summary = ""
            return summary
        except Exception:
            PrettyOutput.print("总结对话历史失败", OutputType.ERROR)
            return ""

    def _summarize_and_clear_history(self) -> str:
        """总结当前对话并清理历史记录

        该方法将:
        1. 提示用户保存重要记忆
        2. 调用 generate_summary 生成摘要
        3. 清除对话历史
        4. 保留系统消息
        5. 添加摘要作为新上下文
        6. 重置对话长度计数器

        返回:
            str: 包含对话摘要的字符串

        注意:
            当上下文长度超过最大值时使用
        """
        # 在清理历史之前，提示用户保存重要记忆（事件驱动触发实际保存）
        if self.force_save_memory:
            PrettyOutput.print(
                "对话历史即将被总结和清理，请先保存重要信息...", OutputType.INFO
            )

        if self._should_use_file_upload():
            return self._handle_history_with_file_upload()
        else:
            return self._handle_history_with_summary()

    def _should_use_file_upload(self) -> bool:
        """判断是否应该使用文件上传方式处理历史"""
        return bool(self.model and self.model.support_upload_files())

    def _handle_history_with_summary(self) -> str:
        """使用摘要方式处理历史"""
        summary = self.generate_summary()

        # 先获取格式化的摘要消息
        formatted_summary = ""
        if summary:
            formatted_summary = self._format_summary_message(summary)

        # 清理历史（但不清理prompt，因为prompt会在builtin_input_handler中设置）
        if self.model:
            # 广播清理历史前事件
            try:
                self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
            except Exception:
                pass
            self.model.reset()
            # 重置后重新设置系统提示词，确保系统约束仍然生效
            self._setup_system_prompt()
        # 重置会话
        self.session.clear_history()
        # 广播清理历史后的事件
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

        return formatted_summary

    def _handle_history_with_file_upload(self) -> str:
        """使用文件上传方式处理历史"""
        # 广播清理历史前事件
        try:
            self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
        except Exception:
            pass
        result = self.file_methodology_manager.handle_history_with_file_upload()
        # 广播清理历史后的事件
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception:
            pass
        return result

    def _format_summary_message(self, summary: str) -> str:
        """格式化摘要消息"""
        return f"""
以下是之前对话的关键信息总结：

<content>
{summary}
</content>

请基于以上信息继续完成任务。请注意，这是之前对话的摘要，上下文长度已超过限制而被重置。请直接继续任务，无需重复已完成的步骤。如有需要，可以询问用户以获取更多信息。
        """

    def _call_tools(self, response: str) -> Tuple[bool, Any]:
        """
        Delegates the tool execution to the external `execute_tool_call` function.
        """
        return execute_tool_call(response, self)

    def _complete_task(self, auto_completed: bool = False) -> str:
        """完成任务并生成总结(如果需要)

        返回:
            str: 任务总结或完成状态

        注意:
            1. 对于主Agent: 可能会生成方法论(如果启用)
            2. 对于子Agent: 可能会生成总结(如果启用)
            3. 使用spinner显示生成状态
        """
        # 事件驱动方式：
        # - TaskAnalyzer 通过订阅 before_summary/task_completed 事件执行分析与满意度收集
        # - MemoryManager 通过订阅 before_history_clear/task_completed 事件执行记忆保存（受 force_save_memory 控制）
        # 为减少耦合，这里不再直接调用上述组件，保持行为由事件触发
        self._check_and_organize_memory()

        result = "任务完成"

        if self.need_summary:

            # 确保总结提示词非空：若为None或仅空白，则回退到默认提示词
            safe_summary_prompt = self.summary_prompt or ""
            if isinstance(safe_summary_prompt, str) and safe_summary_prompt.strip() == "":
                safe_summary_prompt = DEFAULT_SUMMARY_PROMPT
            # 注意：不要写回 session.prompt，避免 BEFORE_SUMMARY 事件回调修改/清空后导致使用空prompt
            # 广播将要生成总结事件
            try:
                self.event_bus.emit(
                    BEFORE_SUMMARY,
                    agent=self,
                    prompt=safe_summary_prompt,
                    auto_completed=auto_completed,
                    need_summary=self.need_summary,
                )
            except Exception:
                pass

            if not self.model:
                raise RuntimeError("Model not initialized")
            # 直接使用本地变量，避免受事件回调影响
            ret = self.model.chat_until_success(safe_summary_prompt)  # type: ignore
            # 防御: 总结阶段模型可能返回空响应(None或空字符串)，统一为空字符串并告警
            if not ret:
                try:
                    PrettyOutput.print("总结阶段模型返回空响应，已使用空字符串回退。", OutputType.WARNING)
                except Exception:
                    pass
                ret = ""
            result = ret

            # 广播完成总结事件
            try:
                self.event_bus.emit(
                    AFTER_SUMMARY,
                    agent=self,
                    summary=result,
                )
            except Exception:
                pass

        # 广播任务完成事件（不影响主流程）
        try:
            self.event_bus.emit(
                TASK_COMPLETED,
                agent=self,
                auto_completed=auto_completed,
                need_summary=self.need_summary,
            )
        except Exception:
            pass

        return result

    def make_default_addon_prompt(self, need_complete: bool) -> str:
        """生成附加提示。

        参数:
            need_complete: 是否需要完成任务

        """
        # 优先使用 PromptManager 以保持逻辑集中
        if hasattr(self, "prompt_manager"):
            return self.prompt_manager.build_default_addon_prompt(need_complete)

        # 结构化系统指令
        action_handlers = ", ".join([handler.name() for handler in self.output_handler])

        # 任务完成提示
        complete_prompt = (
            f"- 输出{ot('!!!COMPLETE!!!')}"
            if need_complete and self.auto_complete
            else ""
        )

        # 检查工具列表并添加记忆工具相关提示
        tool_registry = self.get_tool_registry()
        memory_prompts = self.memory_manager.add_memory_prompts_to_addon(
            "", tool_registry
        )

        addon_prompt = f"""
<system_prompt>
    请判断是否已经完成任务，如果已经完成：
    - 直接输出完成原因，不需要再有新的操作，不要输出{ot("TOOL_CALL")}标签
    {complete_prompt}
    如果没有完成，请进行下一步操作：
    - 仅包含一个操作
    - 如果信息不明确，请请求用户补充
    - 如果执行过程中连续失败5次，请使用ask_user询问用户操作
    - 操作列表：{action_handlers}{memory_prompts}
</system_prompt>

请继续。
"""

        return addon_prompt

    def run(self, user_input: str) -> Any:
        """处理用户输入并执行任务

        参数:
            user_input: 任务描述或请求

        返回:
            str|Dict: 任务总结报告或要发送的消息

        注意:
            1. 这是Agent的主运行循环
            2. 处理完整的任务生命周期
            3. 包含错误处理和恢复逻辑
            4. 自动加载相关方法论(如果是首次运行)
        """
        self.session.prompt = f"{user_input}"
        try:
            set_agent(self.name, self)
            # 广播任务开始事件（不影响主流程）
            try:
                self.event_bus.emit(
                    TASK_STARTED,
                    agent=self,
                    name=self.name,
                    description=self.description,
                    user_input=self.session.prompt,
                )
            except Exception:
                pass
            # 如启用规划模式，先判断是否需要拆分并调度子任务
            if self.plan:
                try:
                    self._maybe_plan_and_dispatch(self.session.prompt)
                except Exception:
                    # 防御式处理，规划失败不影响主流程
                    pass
            return self._main_loop()
        except Exception as e:
            PrettyOutput.print(f"任务失败: {str(e)}", OutputType.ERROR)
            return f"Task failed: {str(e)}"

    def _main_loop(self) -> Any:
        """主运行循环"""
        # 委派至独立的运行循环类，保持行为一致
        loop = AgentRunLoop(self)
        return loop.run()

    def _handle_run_interrupt(self, current_response: str) -> Optional[Union[Any, "LoopAction"]]:
        """处理运行中的中断

        返回:
            None: 无中断，或中断后允许继续执行当前响应
            Any: 需要返回的最终结果
            LoopAction.SKIP_TURN: 中断后需要跳过当前响应，并立即开始下一次循环
        """
        if not get_interrupt():
            return None

        set_interrupt(False)
        user_input = self._multiline_input(
            "模型交互期间被中断，请输入用户干预信息：", False
        )
        # 广播中断事件（包含用户输入，可能为空字符串）
        try:
            self.event_bus.emit(
                INTERRUPT_TRIGGERED,
                agent=self,
                current_response=current_response,
                user_input=user_input,
            )
        except Exception:
            pass

        self.run_input_handlers_next_turn = True

        if not user_input:
            # 用户输入为空，完成任务
            return self._complete_task(auto_completed=False)

        if any(handler.can_handle(current_response) for handler in self.output_handler):
            if self.confirm_callback("检测到有工具调用，是否继续处理工具调用？", True):
                self.session.prompt = join_prompts([
                    f"被用户中断，用户补充信息为：{user_input}",
                    "用户同意继续工具调用。"
                ])
                return None  # 继续执行工具调用
            else:
                self.session.prompt = join_prompts([
                    f"被用户中断，用户补充信息为：{user_input}",
                    "检测到有工具调用，但被用户拒绝执行。请根据用户的补充信息重新考虑下一步操作。"
                ])
                return LoopAction.SKIP_TURN  # 请求主循环 continue
        else:
            self.session.prompt = f"被用户中断，用户补充信息为：{user_input}"
            return LoopAction.SKIP_TURN  # 请求主循环 continue

    def _get_next_user_action(self) -> Union[str, "LoopAction"]:
        """获取用户下一步操作

        返回:
            LoopAction.CONTINUE 或 LoopAction.COMPLETE（兼容旧字符串值 "continue"/"complete"）
        """
        user_input = self._multiline_input(
            f"{self.name}: 请输入，或输入空行来结束当前任务：", False
        )

        if user_input:
            self.session.prompt = user_input
            # 使用显式动作信号，保留返回类型注释以保持兼容
            return LoopAction.CONTINUE  # type: ignore[return-value]
        else:
            return LoopAction.COMPLETE  # type: ignore[return-value]

    def _first_run(self):
        """首次运行初始化"""
        # 如果工具过多，使用AI进行筛选
        if self.session.prompt:
            self._filter_tools_if_needed(self.session.prompt)

        # 准备记忆标签提示
        memory_tags_prompt = self.memory_manager.prepare_memory_tags_prompt()

        # 处理文件上传和方法论加载
        self.file_methodology_manager.handle_files_and_methodology()

        # 添加记忆标签提示
        if memory_tags_prompt:
            self.session.prompt = f"{self.session.prompt}{memory_tags_prompt}"

        self.first = False

    def _create_temp_model(self, system_prompt: str) -> BasePlatform:
        """创建一个用于执行一次性任务的临时模型实例，以避免污染主会话。"""
        temp_model = PlatformRegistry().create_platform(
            self.model.platform_name()  # type: ignore
        )
        if not temp_model:
            raise RuntimeError("创建临时模型失败。")

        temp_model.set_model_name(self.model.name())  # type: ignore
        temp_model.set_system_prompt(system_prompt)
        return temp_model

    def _build_child_agent_params(self, name: str, description: str) -> Dict[str, Any]:
        """构建子Agent参数，尽量继承父Agent配置，并确保子Agent非交互自动完成。"""
        use_tools_param: Optional[List[str]] = None
        try:
            tr = self.get_tool_registry()
            if isinstance(tr, ToolRegistry):
                selected_tools = tr.get_all_tools()
                use_tools_param = [t["name"] for t in selected_tools]
        except Exception:
            use_tools_param = None

        return {
            "system_prompt": origin_agent_system_prompt,
            "name": name,
            "description": description,
            "model_group": self.model_group,
            "summary_prompt": self.summary_prompt,
            "auto_complete": True,
            "use_tools": use_tools_param,
            "execute_tool_confirm": self.execute_tool_confirm,
            "need_summary": self.need_summary,
            "auto_summary_rounds": self.auto_summary_rounds,
            "multiline_inputer": self.multiline_inputer,
            "use_methodology": self.use_methodology,
            "use_analysis": self.use_analysis,
            "force_save_memory": self.force_save_memory,
            "files": self.files,
            "confirm_callback": self.confirm_callback,
            "non_interactive": True,
            "in_multi_agent": True,
            "plan": self.plan,  # 继承父Agent的规划开关
            "plan_depth": self.plan_depth + 1,  # 子Agent层数+1
            "plan_max_depth": self.plan_max_depth,  # 继承上限
        }

    def _maybe_plan_and_dispatch(self, task_text: str) -> None:
        """
        当启用 self.plan 时，调用临时模型评估是否需要拆分任务并执行子任务。
        - 若模型返回 <DONT_NEED/>，则直接返回不做任何修改；
        - 若返回 <SUB_TASK> 块，则解析每行以“- ”开头的子任务，逐个创建子Agent执行；
        - 将子任务与结果以结构化块写回到 self.session.prompt，随后由主循环继续处理。
        """
        try:
            planning_sys = (
                "你是一个任务规划助手。请判断是否需要拆分任务。\n"
                "当需要拆分时，仅按以下结构输出：\n"
                "<SUB_TASK>\n- 子任务1\n- 子任务2\n</SUB_TASK>\n"
                "当不需要拆分时，仅输出：\n<DONT_NEED/>\n"
                "禁止输出任何额外解释。"
            )
            temp_model = self._create_temp_model(planning_sys)
            plan_prompt = f"任务：\n{task_text}\n\n请严格按要求只输出结构化标签块。"
            plan_resp = temp_model.chat_until_success(plan_prompt)  # type: ignore
            if not plan_resp:
                return
        except Exception:
            # 规划失败不影响主流程
            return

        text = str(plan_resp).strip()
        # 不需要拆分
        if re.search(r"<\s*DONT_NEED\s*/\s*>", text, re.IGNORECASE):
            return

        # 解析 <SUB_TASK> 块
        m = re.search(
            r"<\s*SUB_TASK\s*>\s*(.*?)\s*<\s*/\s*SUB_TASK\s*>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        subtasks: List[str] = []
        if m:
            block = m.group(1)
            for line in block.splitlines():
                s = line.strip()
                if s.startswith("-"):
                    item = s[1:].strip()
                    if item:
                        subtasks.append(item)
        else:
            # 回退解析：无标签时，尝试解析所有以“- ”开头的行
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("-"):
                    item = s[1:].strip()
                    if item:
                        subtasks.append(item)

        if not subtasks:
            # 无有效子任务，直接返回
            return

        # 执行子任务
        executed_subtask_block_lines: List[str] = ["<SUB_TASK>"]
        executed_subtask_block_lines += [f"- {t}" for t in subtasks]
        executed_subtask_block_lines.append("</SUB_TASK>")

        results_lines: List[str] = []
        for i, st in enumerate(subtasks, 1):
            try:
                child_kwargs = self._build_child_agent_params(
                    name=f"{self.name}-child-{i}",
                    description=f"子任务执行器: {st}",
                )
                child = Agent(**child_kwargs)
                child_result = child.run(st)
                result_text = "" if child_result is None else str(child_result)
                # 防止极端长输出导致污染，这里不做截断，交由上层摘要策略控制
                results_lines.append(f"- 子任务{i}: {st}\n  结果: {result_text}")
            except Exception as e:
                results_lines.append(f"- 子任务{i}: {st}\n  结果: 执行失败，原因: {e}")

        subtask_block = "\n".join(executed_subtask_block_lines)
        results_block = "<SUB_TASK_RESULTS>\n" + "\n".join(results_lines) + "\n</SUB_TASK_RESULTS>"

        # 合并回父Agent的 prompt
        try:
            self.session.prompt = join_prompts(
                [
                    f"原始任务：\n{task_text}",
                    f"子任务规划：\n{subtask_block}",
                    f"子任务执行结果：\n{results_block}",
                    "请基于上述子任务结果整合并完成最终输出。",
                ]
            )
        except Exception:
            # 回退拼接
            self.session.prompt = (
                f"{task_text}\n\n{subtask_block}\n\n{results_block}\n\n"
                "请基于上述子任务结果整合并完成最终输出。"
            )

    def _filter_tools_if_needed(self, task: str):
        """如果工具数量超过阈值，使用大模型筛选相关工具"""
        tool_registry = self.get_tool_registry()
        if not isinstance(tool_registry, ToolRegistry):
            return

        all_tools = tool_registry.get_all_tools()
        threshold = get_tool_filter_threshold()
        if len(all_tools) <= threshold:
            return

        # 为工具选择构建提示
        tools_prompt_part = ""
        tool_names = []
        for i, tool in enumerate(all_tools, 1):
            tool_names.append(tool["name"])
            tools_prompt_part += f"{i}. {tool['name']}: {tool['description']}\n"

        selection_prompt = f"""
用户任务是：
<task>
{task}
</task>

这是一个可用工具的列表：
<tools>
{tools_prompt_part}
</tools>

请根据用户任务，从列表中选择最相关的工具。
请仅返回所选工具的编号，以逗号分隔。例如：1, 5, 12
"""
        PrettyOutput.print(
            f"工具数量超过{threshold}个，正在使用AI筛选相关工具...", OutputType.INFO
        )
        # 广播工具筛选开始事件
        try:
            self.event_bus.emit(
                BEFORE_TOOL_FILTER,
                agent=self,
                task=task,
                total_tools=len(all_tools),
                threshold=threshold,
            )
        except Exception:
            pass

        # 使用临时模型实例调用模型，以避免污染历史记录
        try:
            temp_model = self._create_temp_model("你是一个帮助筛选工具的助手。")
            selected_tools_str = temp_model.chat_until_success(
                selection_prompt
            )  # type: ignore

            # 解析响应并筛选工具
            selected_indices = [
                int(i.strip()) for i in re.findall(r"\d+", selected_tools_str)
            ]
            selected_tool_names = [
                tool_names[i - 1]
                for i in selected_indices
                if 0 < i <= len(tool_names)
            ]

            if selected_tool_names:
                # 移除重复项
                selected_tool_names = sorted(list(set(selected_tool_names)))
                tool_registry.use_tools(selected_tool_names)
                # 使用筛选后的工具列表重新设置系统提示
                self._setup_system_prompt()
                PrettyOutput.print(
                    f"已筛选出 {len(selected_tool_names)} 个相关工具: {', '.join(selected_tool_names)}",
                    OutputType.SUCCESS,
                )
                # 广播工具筛选事件
                try:
                    self.event_bus.emit(
                        TOOL_FILTERED,
                        agent=self,
                        task=task,
                        selected_tools=selected_tool_names,
                        total_tools=len(all_tools),
                        threshold=threshold,
                    )
                except Exception:
                    pass
            else:
                PrettyOutput.print(
                    "AI 未能筛选出任何相关工具，将使用所有工具。", OutputType.WARNING
                )
                # 广播工具筛选事件（无筛选结果）
                try:
                    self.event_bus.emit(
                        TOOL_FILTERED,
                        agent=self,
                        task=task,
                        selected_tools=[],
                        total_tools=len(all_tools),
                        threshold=threshold,
                    )
                except Exception:
                    pass

        except Exception as e:
            PrettyOutput.print(
                f"工具筛选失败: {e}，将使用所有工具。", OutputType.ERROR
            )

    def _check_and_organize_memory(self):
        """
        检查记忆库状态，如果满足条件则提示用户整理。
        每天只检测一次。
        """
        try:
            # 检查项目记忆
            self._perform_memory_check("project_long_term", Path(".jarvis"), "project")
            # 检查全局记忆
            self._perform_memory_check(
                "global_long_term",
                Path(get_data_dir()),
                "global",
            )
        except Exception as e:
            PrettyOutput.print(f"检查记忆库时发生意外错误: {e}", OutputType.WARNING)

    def _perform_memory_check(self, memory_type: str, base_path: Path, scope_name: str):
        """执行特定范围的记忆检查和整理"""
        check_file = base_path / ".last_memory_organizer_check"
        now = datetime.datetime.now()

        if check_file.exists():
            try:
                last_check_time = datetime.datetime.fromisoformat(
                    check_file.read_text()
                )
                if (now - last_check_time).total_seconds() < 24 * 3600:
                    return  # 24小时内已检查
            except (ValueError, FileNotFoundError):
                # 文件内容无效或文件在读取时被删除，继续执行检查
                pass

        # 立即更新检查时间，防止并发或重复检查
        base_path.mkdir(parents=True, exist_ok=True)
        check_file.write_text(now.isoformat())

        organizer = MemoryOrganizer()
        # NOTE: 使用受保护方法以避免重复实现逻辑
        memories = organizer._load_memories(memory_type)

        if len(memories) < 200:
            return

        # NOTE: 使用受保护方法以避免重复实现逻辑
        overlap_groups = organizer._find_overlapping_memories(memories, min_overlap=3)
        has_significant_overlap = any(groups for groups in overlap_groups.values())

        if not has_significant_overlap:
            return

        prompt = (
            f"检测到您的 '{scope_name}' 记忆库中包含 {len(memories)} 条记忆，"
            f"并且存在3个以上标签重叠的记忆。\n"
            f"是否立即整理记忆库以优化性能和相关性？"
        )
        if self.confirm_callback(prompt, True):
            PrettyOutput.print(
                f"正在开始整理 '{scope_name}' ({memory_type}) 记忆库...",
                OutputType.INFO,
            )
            organizer.organize_memories(memory_type, min_overlap=3)
        else:
            PrettyOutput.print(f"已取消 '{scope_name}' 记忆库整理。", OutputType.INFO)
