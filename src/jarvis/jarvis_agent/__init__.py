# -*- coding: utf-8 -*-
# 标准库导入
import datetime
import os
import platform
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

# 第三方库导入
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.event_bus import EventBus
from jarvis.jarvis_agent.events import AFTER_ADDON_PROMPT
from jarvis.jarvis_agent.events import AFTER_HISTORY_CLEAR
from jarvis.jarvis_agent.events import AFTER_MODEL_CALL
from jarvis.jarvis_agent.events import AFTER_SUMMARY
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_ADDON_PROMPT
from jarvis.jarvis_agent.events import BEFORE_HISTORY_CLEAR
from jarvis.jarvis_agent.events import BEFORE_MODEL_CALL
from jarvis.jarvis_agent.events import BEFORE_SUMMARY
from jarvis.jarvis_agent.events import BEFORE_TOOL_FILTER
from jarvis.jarvis_agent.events import INTERRUPT_TRIGGERED
from jarvis.jarvis_agent.events import TASK_COMPLETED
from jarvis.jarvis_agent.events import TASK_STARTED
from jarvis.jarvis_agent.events import TOOL_FILTERED
from jarvis.jarvis_agent.file_context_handler import file_context_handler
from jarvis.jarvis_agent.file_methodology_manager import FileMethodologyManager
from jarvis.jarvis_agent.memory_manager import MemoryManager

# 本地库导入
# jarvis_agent 相关
from jarvis.jarvis_agent.prompt_builder import build_action_prompt
from jarvis.jarvis_agent.prompt_manager import PromptManager
from jarvis.jarvis_agent.prompts import DEFAULT_SUMMARY_PROMPT
from jarvis.jarvis_agent.prompts import SUMMARY_REQUEST_PROMPT
from jarvis.jarvis_agent.protocols import OutputHandlerProtocol
from jarvis.jarvis_agent.run_loop import AgentRunLoop
from jarvis.jarvis_agent.session_manager import SessionManager
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer
from jarvis.jarvis_agent.task_list import TaskListManager
from jarvis.jarvis_agent.tool_executor import execute_tool_call
from jarvis.jarvis_agent.user_interaction import UserInteractionHandler
from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_memory_organizer.memory_organizer import MemoryOrganizer

# jarvis_platform 相关
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

# jarvis_utils 相关
from jarvis.jarvis_utils.config import get_addon_prompt_threshold
from jarvis.jarvis_utils.config import get_after_tool_call_cb_dirs
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_llm_config
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.config import get_tool_filter_threshold
from jarvis.jarvis_utils.config import is_enable_memory_organizer
from jarvis.jarvis_utils.config import is_execute_tool_confirm
from jarvis.jarvis_utils.config import is_force_save_memory
from jarvis.jarvis_utils.config import is_use_analysis
from jarvis.jarvis_utils.config import is_use_methodology
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import clear_current_agent
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import get_short_term_memories
from jarvis.jarvis_utils.globals import make_agent_name
from jarvis.jarvis_utils.globals import set_global_model_group
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.globals import set_current_agent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.methodology import _load_all_methodologies
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot

__all__ = [
    "Agent",
    "LoopAction",
    "show_agent_startup_stats",
    "get_multiline_input",
    "user_confirm",
]


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

        # 检查短期记忆
        short_term_memories = get_short_term_memories()
        short_term_memory_count = len(short_term_memories) if short_term_memories else 0

        # 获取当前工作目录
        current_dir = os.getcwd()

        # 构建欢迎信息
        platform = platform_name or get_normal_platform_name()
        welcome_message = (
            f"{agent_name} 初始化完成 - 使用 {platform} 平台 {model_name} 模型"
        )

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

        # 如果有短期记忆，添加到统计信息中
        if short_term_memory_count > 0:
            stats_parts.append(
                f"💭  短期记忆: [bold blue]{short_term_memory_count}[/bold blue]"
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
        PrettyOutput.auto_print(f"⚠️ 加载统计信息失败: {e}")


origin_agent_system_prompt = f"""
<role>
# 🤖 Jarvis Agent
你是一个专业的任务执行助手，根据用户需求制定并执行详细计划。
</role>

## 核心模式
每个响应必须以[MODE: MODE_NAME]开头：
- **INTENT**: 理解用户需求
- **RESEARCH**: 收集信息
- **INNOVATE**: 探索方案
- **PLAN**: 制定计划（复杂任务用task_list_manager）
- **EXECUTE**: 执行操作
- **REVIEW**: 验证结果

### IIRIPER 工作流强制约束
- 整体工作流必须严格按照 **INTENT → RESEARCH → INNOVATE → PLAN → EXECUTE → REVIEW** 的顺序推进。
- **禁止跳步或乱序**：例如，不能在未经过 PLAN 就直接进入 EXECUTE，也不能从 INTENT 直接跳到 REVIEW。
- 如因用户以非常明确的指令要求跳过某阶段，必须在当前回复中：
  - 明确指出被跳过的阶段；
  - 解释为什么认为可以跳过；
  - 简要提示可能的风险。

## 执行规则
1. **单次操作**: 每个响应只含一个工具调用
2. **禁止虚构**: 必须基于实际结果，禁止假设
3. **任务列表**: 复杂任务用task_list_manager，简单任务直接执行
4. **必须验证**: 代码需编译通过、功能验证
5. **模式转换**: 需明确信号"ENTER [MODE]"

## 工具使用
- 优先用task_list_manager执行复杂任务
- execute_task必须提供additional_info参数
- 禁止同时调用多个工具

<system_info>
OS: {platform.platform()} {platform.version()}
Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
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

    def clear_history(self) -> None:
        """
        Clears the current conversation history by delegating to the session manager.
        直接调用关键流程函数，事件总线仅用于非关键流程（如日志、监控等）。
        """
        # 获取当前会话文件路径用于提示
        from jarvis.jarvis_utils.dialogue_recorder import get_global_recorder

        recorder = get_global_recorder()
        session_file_path = recorder.get_session_file_path()

        # 关键流程：直接调用 memory_manager 确保记忆提示
        try:
            self.memory_manager._ensure_memory_prompt(agent=self)
        except Exception:
            pass

        # 非关键流程：广播清理历史前事件（用于日志、监控等）
        try:
            self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

        # 清理会话历史并重置模型状态
        self.session.clear_history()
        # 重置 addon_prompt 跳过轮数计数器
        self._addon_prompt_skip_rounds = 0
        # 重置没有工具调用的计数器
        self._no_tool_call_count = 0

        # 提示用户会话文件位置
        if Path(session_file_path).exists():
            PrettyOutput.auto_print(f"💾 当前会话记录已保存到: {session_file_path}")
            PrettyOutput.auto_print("🤖 大模型可以读取此文件了解完整对话历史")

        # 重置后重新设置系统提示词，确保系统约束仍然生效
        try:
            self._setup_system_prompt()
        except Exception:
            pass

        # 非关键流程：广播清理历史后的事件（用于日志、监控等）
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

    def __del__(self) -> None:
        # 只有在记录启动时才停止记录
        pass

    def get_tool_usage_prompt(self) -> str:
        """获取工具使用提示"""
        return build_action_prompt(self.output_handler)

    def __new__(cls, *args: Any, **kwargs: Any) -> "Agent":
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
        auto_complete: bool = True,
        output_handler: Optional[List[OutputHandlerProtocol]] = None,
        use_tools: Optional[List[str]] = None,
        execute_tool_confirm: Optional[bool] = None,
        need_summary: bool = True,
        multiline_inputer: Optional[Callable[[str], str]] = None,
        use_methodology: Optional[bool] = None,
        use_analysis: Optional[bool] = None,
        force_save_memory: Optional[bool] = None,
        files: Optional[List[str]] = None,
        confirm_callback: Optional[Callable[[str, bool], bool]] = None,
        non_interactive: Optional[bool] = True,
        in_multi_agent: Optional[bool] = None,
        agent_type: str = "normal",
        **kwargs: Any,
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
        """
        # 基础属性初始化（仅根据入参设置原始值；实际生效的默认回退在 _init_config 中统一解析）
        # 标识与描述
        self.name = make_agent_name(name)
        self.description = description
        self.system_prompt = system_prompt
        # 行为控制开关（原始入参值）
        self.auto_complete = bool(auto_complete)
        self.need_summary = bool(need_summary)
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
        # 运行时状态
        self.first = True
        self.run_input_handlers_next_turn = False
        self.user_data: Dict[str, Any] = {}
        # 记录固定的内容
        self.pin_content: str = ""
        # 记录连续未添加 addon_prompt 的轮数
        self._addon_prompt_skip_rounds = 0
        # 记录连续没有工具调用的次数（用于非交互模式下的工具使用提示）
        self._no_tool_call_count = 0

        self._agent_type = "normal"

        # 用户确认回调：默认使用 CLI 的 user_confirm，可由外部注入以支持 TUI/GUI
        self.confirm_callback: Callable[[str, bool], bool] = (
            confirm_callback or user_confirm
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
        self.user_interaction = UserInteractionHandler(
            self.multiline_inputer, self.confirm_callback
        )
        # 将确认函数指向封装后的 confirm，保持既有调用不变
        self.confirm_callback = self.user_interaction.confirm
        # 非交互模式参数支持：允许通过构造参数显式控制，便于其他Agent调用时设置
        # 仅作为 Agent 实例属性，不写入环境变量或全局配置，避免跨 Agent 污染
        try:
            # 优先使用构造参数，若未提供则默认为 False
            self.non_interactive = (
                bool(non_interactive) if non_interactive is not None else False
            )
        except Exception:
            # 防御式回退
            self.non_interactive = False

        # 初始化配置（直接解析，不再依赖 _init_config）
        try:
            resolved_use_methodology = bool(
                use_methodology if use_methodology is not None else is_use_methodology()
            )
        except Exception:
            resolved_use_methodology = (
                bool(use_methodology) if use_methodology is not None else True
            )

        try:
            resolved_use_analysis = bool(
                use_analysis if use_analysis is not None else is_use_analysis()
            )
        except Exception:
            resolved_use_analysis = (
                bool(use_analysis) if use_analysis is not None else True
            )

        try:
            resolved_execute_tool_confirm = bool(
                execute_tool_confirm
                if execute_tool_confirm is not None
                else is_execute_tool_confirm()
            )
        except Exception:
            resolved_execute_tool_confirm = (
                bool(execute_tool_confirm)
                if execute_tool_confirm is not None
                else False
            )

        try:
            resolved_force_save_memory = bool(
                force_save_memory
                if force_save_memory is not None
                else is_force_save_memory()
            )
        except Exception:
            resolved_force_save_memory = (
                bool(force_save_memory) if force_save_memory is not None else False
            )

        self.use_methodology = resolved_use_methodology
        self.use_analysis = resolved_use_analysis
        self.execute_tool_confirm = resolved_execute_tool_confirm
        self.summary_prompt = summary_prompt or DEFAULT_SUMMARY_PROMPT
        self.force_save_memory = resolved_force_save_memory
        # 多智能体模式下，默认不自动完成（即使是非交互），仅在明确传入 auto_complete=True 时开启
        if self.in_multi_agent:
            self.auto_complete = bool(self.auto_complete)
        else:
            # 非交互模式下默认自动完成；否则保持传入的 auto_complete 值
            self.auto_complete = bool(
                self.auto_complete or (self.non_interactive or False)
            )

        # 初始化事件总线需先于管理器，以便管理器在构造中安全订阅事件
        self.event_bus = EventBus()
        # 初始化管理器
        self.memory_manager = MemoryManager(self)
        self.task_analyzer = TaskAnalyzer(self)
        self.file_methodology_manager = FileMethodologyManager(self)
        self.prompt_manager = PromptManager(self)
        # 初始化任务列表管理器（使用当前工作目录作为 root_dir，如果子类已设置 root_dir 则使用子类的）
        root_dir = getattr(self, "root_dir", None) or os.getcwd()
        self.task_list_manager = TaskListManager(root_dir)

        # 如果配置了强制保存记忆，确保 save_memory 工具可用
        if self.force_save_memory:
            self._ensure_save_memory_tool()

        # 如果启用了分析，确保 methodology 工具可用
        if self.use_analysis:
            self._ensure_methodology_tool()

        # 设置系统提示词
        self._setup_system_prompt()

        # 输出统计信息（包含欢迎信息）
        show_agent_startup_stats(
            name,
            self.model.name(),
            self.get_tool_registry(),
            platform_name=self.model.platform_name(),
        )

        # 动态加载工具调用后回调
        self._load_after_tool_callbacks()

    def _init_model(self, model_group: Optional[str]) -> None:
        """初始化模型平台（统一使用 normal 平台/模型）"""
        model_name = get_normal_model_name(model_group)

        # 直接使用 get_normal_platform，避免先调用 create_platform 再回退导致的重复错误信息
        # get_normal_platform 内部会处理配置获取和平台创建
        self.model = PlatformRegistry().get_normal_platform(model_group)

        if model_name:
            self.model.set_model_name(model_name)

        self.model.set_model_group(model_group)
        self.model.set_suppress_output(False)

        # 设置全局模型组，供工具和其他组件使用
        set_global_model_group(model_group)

    def _init_session(self) -> None:
        """初始化会话管理器"""
        self.session = SessionManager(model=self.model, agent_name=self.name)

    def _init_handlers(
        self,
        multiline_inputer: Optional[Callable[[str], str]],
        output_handler: Optional[List[OutputHandlerProtocol]],
        use_tools: List[str],
    ) -> None:
        """初始化各种处理器"""
        default_handlers: List[Any] = [ToolRegistry()]
        handlers = output_handler or default_handlers
        self.output_handler = handlers
        self.set_use_tools(use_tools)
        self.input_handler = [
            builtin_input_handler,
            shell_input_handler,
            file_context_handler,
        ]
        self.multiline_inputer = multiline_inputer or get_multiline_input

    def _setup_system_prompt(self) -> None:
        """设置系统提示词"""
        prompt_text = self.prompt_manager.build_system_prompt(self)
        self.model.set_system_prompt(prompt_text)

    def set_user_data(self, key: str, value: Any) -> None:
        """Sets user data in the session."""
        self.session.set_user_data(key, value)

    def get_user_data(self, key: str) -> Optional[Any]:
        """Gets user data from the session."""
        return self.session.get_user_data(key)

    def get_remaining_token_count(self) -> int:
        """获取剩余可用的token数量

        返回:
            int: 剩余可用的token数量，如果无法获取则返回0
        """
        if not self.model:
            return 0
        try:
            return self.model.get_remaining_token_count()
        except Exception:
            return 0

    def set_use_tools(self, use_tools: List[str]) -> None:
        """设置要使用的工具列表"""
        for handler in self.output_handler:
            if isinstance(handler, ToolRegistry):
                if use_tools:
                    handler.use_tools(use_tools)
                break

    def set_addon_prompt(self, addon_prompt: str) -> None:
        """Sets the addon prompt in the session."""
        self.session.set_addon_prompt(addon_prompt)

    def set_run_input_handlers_next_turn(self, value: bool) -> None:
        """Sets the flag to run input handlers on the next turn."""
        self.run_input_handlers_next_turn = value

    def _multiline_input(self, tip: str, print_on_empty: bool) -> str:
        """
        Safe wrapper for multiline input to optionally suppress empty-input notice.
        If the configured multiline_inputer supports 'print_on_empty' keyword, pass it;
        otherwise, fall back to calling with a single argument for compatibility.
        """
        # 优先通过用户交互封装，便于未来替换 UI
        try:
            return self.user_interaction.multiline_input(tip, print_on_empty)
        except Exception:
            pass
        try:
            # Try to pass the keyword for enhanced input handler
            return self.multiline_inputer(
                tip,
            )
        except TypeError:
            # Fallback for custom handlers that only accept one argument
            return self.multiline_inputer(tip)

    def _load_after_tool_callbacks(self) -> None:
        """
        扫描 after_tool_call_cb_dirs 中的 Python 文件并动态注册回调。
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
                                candidates.append(obj)

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

                                def _make_wrapper(
                                    callback: Callable[[Any], None],
                                ) -> Callable[..., None]:
                                    def _wrapper(**kwargs: Any) -> None:
                                        try:
                                            agent = kwargs.get("agent")
                                            callback(agent)
                                        except Exception:
                                            pass

                                    return _wrapper

                                self.event_bus.subscribe(
                                    AFTER_TOOL_CALL, _make_wrapper(cb)
                                )
                            except Exception:
                                pass

                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 从 {file_path} 加载回调失败: {e}")
                    finally:
                        if added_path:
                            try:
                                sys.path.remove(parent_dir)
                            except ValueError:
                                pass
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 加载回调目录时发生错误: {e}")

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

    def _ensure_save_memory_tool(self) -> None:
        """如果配置了强制保存记忆，确保 save_memory 工具在 use_tools 列表中"""
        try:
            tool_registry = self.get_tool_registry()
            if not tool_registry:
                return

            # 检查 save_memory 工具是否已注册（工具默认都会注册）
            if not tool_registry.get_tool("save_memory"):
                # 如果工具本身不存在，则无法使用，直接返回
                return

            # 检查 save_memory 是否在 use_tools 列表中
            # 如果 use_tools 为 None，表示使用所有工具，无需添加
            if self.use_tools is None:
                return

            # 如果 save_memory 不在 use_tools 列表中，则添加
            if "save_memory" not in self.use_tools:
                self.use_tools.append("save_memory")
                # 更新工具注册表的工具列表
                self.set_use_tools(self.use_tools)
        except Exception:
            # 忽略所有错误，不影响主流程
            pass

    def _ensure_methodology_tool(self) -> None:
        """如果启用了分析，确保 methodology 工具在 use_tools 列表中"""
        try:
            tool_registry = self.get_tool_registry()
            if not tool_registry:
                return

            # 检查 methodology 工具是否已注册（工具默认都会注册）
            if not tool_registry.get_tool("methodology"):
                # 如果工具本身不存在，则无法使用，直接返回
                return

            # 检查 methodology 是否在 use_tools 列表中
            # 如果 use_tools 为 None，表示使用所有工具，无需添加
            if self.use_tools is None:
                return

            # 如果 methodology 不在 use_tools 列表中，则添加
            if "methodology" not in self.use_tools:
                self.use_tools.append("methodology")
                # 更新工具注册表的工具列表
                self.set_use_tools(self.use_tools)
        except Exception:
            # 忽略所有错误，不影响主流程
            pass

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
        """添加附加提示到消息

        规则：
        1. 如果 session.addon_prompt 存在，优先使用它
        2. 如果消息长度超过阈值，添加默认 addon_prompt
        3. 如果连续10轮都没有添加过 addon_prompt，强制添加一次
        """
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
        should_add = False

        if self.session.addon_prompt:
            # 优先使用 session 中设置的 addon_prompt
            addon_text = self.session.addon_prompt
            message = join_prompts([message, addon_text])
            self.session.addon_prompt = ""
            should_add = True
        else:
            threshold = get_addon_prompt_threshold()
            # 条件1：消息长度超过阈值
            if len(message) > threshold:
                addon_text = self.make_default_addon_prompt(need_complete)
                message = join_prompts([message, addon_text])
                should_add = True
            # 条件2：连续10轮都没有添加过 addon_prompt，强制添加一次
            elif self._addon_prompt_skip_rounds >= 10:
                addon_text = self.make_default_addon_prompt(need_complete)
                message = join_prompts([message, addon_text])
                should_add = True

        # 更新计数器：如果添加了 addon_prompt，重置计数器；否则递增
        if should_add:
            self._addon_prompt_skip_rounds = 0
        else:
            self._addon_prompt_skip_rounds += 1

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
        """管理对话长度计数；摘要触发由剩余token数量在 AgentRunLoop 中统一处理（剩余token低于20%时触发）。"""
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

        response = self.model.chat_until_success(message)
        # 防御: 模型可能返回空响应(None或空字符串)，统一为空字符串并告警
        if not response:
            try:
                PrettyOutput.auto_print("⚠️ 模型返回空响应，已使用空字符串回退。")
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

    def generate_summary(self, for_token_limit: bool = False) -> str:
        """生成对话历史摘要

        参数:
            for_token_limit: 如果为True，表示由于token限制触发的summary，使用SUMMARY_REQUEST_PROMPT
                            如果为False，表示任务完成时的summary，使用用户传入的summary_prompt

        返回:
            str: 包含对话摘要的字符串

        注意:
            仅生成摘要，不修改对话状态
        """

        try:
            if not self.model:
                raise RuntimeError("Model not initialized")

            PrettyOutput.auto_print("🔍 开始生成对话历史摘要...")

            if for_token_limit:
                # token限制触发的summary：使用SUMMARY_REQUEST_PROMPT进行上下文压缩
                prompt_to_use = self.session.prompt + "\n" + SUMMARY_REQUEST_PROMPT
            else:
                # 任务完成时的summary：使用用户传入的summary_prompt或DEFAULT_SUMMARY_PROMPT
                safe_summary_prompt = self.summary_prompt or ""
                if (
                    isinstance(safe_summary_prompt, str)
                    and safe_summary_prompt.strip() != ""
                ):
                    prompt_to_use = safe_summary_prompt
                else:
                    prompt_to_use = DEFAULT_SUMMARY_PROMPT

            summary = self.model.chat_until_success(prompt_to_use)
            # 防御: 可能返回空响应(None或空字符串)，统一为空字符串并告警
            if not summary:
                try:
                    PrettyOutput.auto_print(
                        "⚠️ 总结模型返回空响应，已使用空字符串回退。"
                    )
                except Exception:
                    pass
                summary = ""
            return summary
        except Exception:
            PrettyOutput.auto_print("❌ 总结对话历史失败")
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

        if self._should_use_file_upload():
            return self._handle_history_with_file_upload()
        else:
            return self._handle_history_with_summary()

    def _should_use_file_upload(self) -> bool:
        """判断是否应该使用文件上传方式处理历史"""
        return bool(self.model and self.model.support_upload_files())

    def _handle_history_with_summary(self) -> str:
        """使用摘要方式处理历史"""
        # token限制触发的summary，使用SUMMARY_REQUEST_PROMPT
        summary = self.generate_summary(for_token_limit=True)

        # 获取git diff信息
        git_diff_info = ""
        try:
            # 尝试从 AgentRunLoop 获取已缓存的 git diff
            from jarvis.jarvis_agent.run_loop import AgentRunLoop

            if hasattr(self, "_agent_run_loop") and isinstance(
                self._agent_run_loop, AgentRunLoop
            ):
                agent_run_loop = self._agent_run_loop
            else:
                # 创建临时 AgentRunLoop 实例来获取 git diff
                agent_run_loop = AgentRunLoop(self)

            if agent_run_loop.has_git_diff():
                cached_diff = agent_run_loop.get_cached_git_diff()
                git_diff_info = cached_diff or ""
            else:
                # 如果还没有缓存，直接获取
                git_diff_info = agent_run_loop.get_git_diff()
        except Exception as e:
            git_diff_info = f"获取git diff失败: {str(e)}"

        # 先获取格式化的摘要消息
        formatted_summary = ""
        if summary:
            formatted_summary = self._format_summary_message(summary)

        # 添加git diff信息到摘要中 - 只显示有效的代码变更
        is_valid_git_diff = (
            git_diff_info
            and git_diff_info.strip()
            and
            # 过滤错误信息（获取失败等）
            not git_diff_info.startswith("获取git diff失败")
            and not git_diff_info.startswith("Failed to get git diff")
            and
            # 过滤无变更提示
            "没有检测到代码变更" not in git_diff_info
            and "No code changes detected" not in git_diff_info
            and
            # 确保包含实际代码变更（diff格式）
            "diff --git" in git_diff_info
        )

        if is_valid_git_diff:
            diff_section = f"\n\n## 代码变更摘要\n```\n{git_diff_info}\n```"
            formatted_summary += diff_section

        # 关键流程：直接调用 memory_manager 确保记忆提示
        try:
            self.memory_manager._ensure_memory_prompt(agent=self)
        except Exception:
            pass

            # 非关键流程：广播清理历史前事件（用于日志、监控等）
            try:
                self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
            except Exception:
                pass

        # 清理历史（但不清理prompt，因为prompt会在builtin_input_handler中设置）
        if self.model:
            self.model.reset()
            # 重置后重新设置系统提示词，确保系统约束仍然生效
            self._setup_system_prompt()
        # 重置会话
        self.session.clear_history()
        # 重置 addon_prompt 跳过轮数计数器
        self._addon_prompt_skip_rounds = 0
        # 重置没有工具调用的计数器
        self._no_tool_call_count = 0
        # 打开input handler开关，让下一轮可以处理pin_content中的特殊标记
        self.run_input_handlers_next_turn = True

        # 获取任务列表信息（用于历史记录）
        task_list_info = ""
        try:
            # 获取所有任务列表的摘要信息
            task_lists_summary: List[Dict[str, Any]] = []
            for task_list_id, task_list in self.task_list_manager.task_lists.items():
                summary_dict = self.task_list_manager.get_task_list_summary(
                    task_list_id
                )
                if summary_dict and isinstance(summary_dict, dict):
                    task_lists_summary.append(summary_dict)

            if task_lists_summary:
                task_list_info = "\\n\\n## 任务列表状态\\n"
                for summary_dict in task_lists_summary:
                    task_list_info += (
                        f"\\n- 目标: {summary_dict.get('main_goal', '未知')}"
                    )
                    task_list_info += (
                        f"\\n- 总任务数: {summary_dict.get('total_tasks', 0)}"
                    )
                    task_list_info += f"\\n- 待执行: {summary_dict.get('pending', 0)}"
                    task_list_info += f"\\n- 执行中: {summary_dict.get('running', 0)}"
                    task_list_info += f"\\n- 已完成: {summary_dict.get('completed', 0)}"
                    task_list_info += f"\\n- 失败: {summary_dict.get('failed', 0)}"
                    task_list_info += (
                        f"\\n- 已放弃: {summary_dict.get('abandoned', 0)}\\n"
                    )
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        # 非关键流程：广播清理历史后的事件（用于日志、监控等）
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

        # 将任务列表信息添加到摘要中
        if task_list_info:
            formatted_summary += task_list_info

        # 添加用户固定的重要内容
        if self.pin_content.strip():
            pin_section = f"\n\n## 用户的原始需求和要求\n{self.pin_content.strip()}"
            formatted_summary += pin_section

        return formatted_summary

    def _handle_history_with_file_upload(self) -> str:
        """使用文件上传方式处理历史"""
        # 关键流程：直接调用 memory_manager 确保记忆提示
        try:
            self.memory_manager._ensure_memory_prompt(agent=self)
        except Exception:
            pass

        # 非关键流程：广播清理历史前事件（用于日志、监控等）
        try:
            self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
        except Exception:
            pass

        result = self.file_methodology_manager.handle_history_with_file_upload()
        # 重置 addon_prompt 跳过轮数计数器
        self._addon_prompt_skip_rounds = 0
        # 重置没有工具调用的计数器
        self._no_tool_call_count = 0
        # 打开input handler开关，让下一轮可以处理pin_content中的特殊标记
        self.run_input_handlers_next_turn = True

        # 添加系统约束提醒
        if result:
            constraint_reminder = """

**⚠️ 重要系统约束提醒（总结后必须严格遵守）：**
1. **每次只能执行一个工具调用**：每个响应必须包含且仅包含一个工具调用（任务完成时除外）。同时调用多个工具会导致错误。
2. **禁止虚构结果**：所有操作必须基于实际执行结果，禁止推测、假设或虚构任何执行结果。必须等待工具执行完成并获得实际结果后再进行下一步。
3. **等待工具结果**：在继续下一步之前，必须等待当前工具的执行结果，不能假设工具执行的结果。
4. **基于实际验证**：所有结论必须基于实际执行结果和验证证据，禁止基于推测或假设。
5. **代码任务完成标准（严格执行）**：
   - **编译/构建必须通过**：代码必须能够成功编译/构建，无编译错误、无语法错误、无链接错误
   - **功能必须验证**：功能必须经过实际运行验证，不能仅凭代码存在就认为完成
   - **错误必须修复**：如果存在编译错误、运行时错误、测试失败，任务必须标记为"部分完成"或"进行中"，不能标记为"已完成"
   - **不能因为"代码已编写"就认为任务完成**：必须验证编译通过、功能正常运行、测试通过
"""
            result += constraint_reminder

        # 添加用户固定的重要内容
        if self.pin_content.strip():
            pin_section = (
                f"\n\n## 用户强调的任务目标和关键信息\n{self.pin_content.strip()}"
            )
            result += pin_section

        # 非关键流程：广播清理历史后的事件（用于日志、监控等）
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception:
            pass
        return result

    def _format_summary_message(self, summary: str) -> str:
        """格式化摘要消息"""
        # 获取任务列表信息
        task_list_info = self._get_task_list_info()

        # 获取会话文件路径信息
        session_file_info = ""
        try:
            from jarvis.jarvis_utils.dialogue_recorder import get_global_recorder
            from pathlib import Path

            recorder = get_global_recorder()
            session_file_path = recorder.get_session_file_path()
            if Path(session_file_path).exists():
                session_file_info = f"\n\n**📁 完整对话历史文件**：\n完整的对话历史已自动保存到以下文件，如果需要查看详细的历史信息，可以读取此文件：\n`{session_file_path}`\n\n此文件包含之前所有对话的完整记录（JSONL格式），每行一个消息记录，包括时间戳、角色和内容。"
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        # 获取初始 commit 信息（仅对 CodeAgent）
        initial_commit_info = ""
        try:
            if hasattr(self, "start_commit") and self.start_commit:
                initial_commit_info = f"\n\n**🔖 初始 Git Commit（安全回退点）**：\n本次任务开始时的初始 commit 是：`{self.start_commit}`\n\n**⚠️ 重要提示**：如果文件被破坏得很严重无法恢复，可以使用以下命令重置到这个初始 commit：\n```bash\ngit reset --hard {self.start_commit}\n```\n这将丢弃所有未提交的更改，将工作区恢复到任务开始时的状态。请谨慎使用此命令，确保这是你真正想要的操作。"
        except Exception:
            # 非关键流程，失败时不影响主要功能
            pass

        formatted_message = f"""
以下是之前对话的关键信息总结：

<content>
{summary}
</content>

**⚠️ 重要系统约束提醒（总结后必须严格遵守）：**
1. **每次只能执行一个工具调用**：每个响应必须包含且仅包含一个工具调用（任务完成时除外）。同时调用多个工具会导致错误。
2. **禁止虚构结果**：所有操作必须基于实际执行结果，禁止推测、假设或虚构任何执行结果。必须等待工具执行完成并获得实际结果后再进行下一步。
3. **等待工具结果**：在继续下一步之前，必须等待当前工具的执行结果，不能假设工具执行的结果。
4. **基于实际验证**：所有结论必须基于实际执行结果和验证证据，禁止基于推测或假设。
5. **代码任务完成标准（严格执行）**：
   - **编译/构建必须通过**：代码必须能够成功编译/构建，无编译错误、无语法错误、无链接错误
   - **功能必须验证**：功能必须经过实际运行验证，不能仅凭代码存在就认为完成
   - **错误必须修复**：如果存在编译错误、运行时错误、测试失败，任务必须标记为"部分完成"或"进行中"，不能标记为"已完成"
   - **不能因为"代码已编写"就认为任务完成**：必须验证编译通过、功能正常运行、测试通过

请基于以上信息继续完成任务。请注意，这是之前对话的摘要，上下文长度已超过限制而被重置。请直接继续任务，无需重复已完成的步骤。如有需要，可以询问用户以获取更多信息。{session_file_info}{initial_commit_info}
        """

        # 如果有任务列表信息，添加到消息后面
        if task_list_info:
            formatted_message += f"\n\n{task_list_info}"

        return formatted_message

    def _get_task_list_info(self) -> str:
        """获取并格式化当前任务列表信息

        返回:
            str: 格式化的任务列表信息，如果没有任务列表则返回空字符串
        """
        try:
            # 使用当前Agent的任务列表管理器获取所有任务列表信息
            if (
                not hasattr(self, "task_list_manager")
                or not self.task_list_manager.task_lists
            ):
                return ""

            all_task_lists_info = []

            # 遍历所有任务列表
            for task_list_id, task_list in self.task_list_manager.task_lists.items():
                summary = self.task_list_manager.get_task_list_summary(task_list_id)
                if not summary:
                    continue

                # 构建任务列表摘要信息
                info_parts = []
                info_parts.append(f"📋 任务列表: {summary['main_goal']}")
                info_parts.append(
                    f"   总任务: {summary['total_tasks']} | 待执行: {summary['pending']} | 执行中: {summary['running']} | 已完成: {summary['completed']}"
                )

                # 如果有失败或放弃的任务，也显示
                if summary["failed"] > 0 or summary["abandoned"] > 0:
                    status_parts = []
                    if summary["failed"] > 0:
                        status_parts.append(f"失败: {summary['failed']}")
                    if summary["abandoned"] > 0:
                        status_parts.append(f"放弃: {summary['abandoned']}")
                    info_parts[-1] += f" | {' | '.join(status_parts)}"

                all_task_lists_info.append("\n".join(info_parts))

            if not all_task_lists_info:
                return ""

            return "\n\n".join(all_task_lists_info)

        except Exception:
            # 静默失败，不干扰主流程
            return ""

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
        # 仅在启用自动记忆整理时检查并整理记忆
        if is_enable_memory_organizer():
            self._check_and_organize_memory()

        result = "任务完成"

        if self.need_summary:
            # 确保总结提示词非空：若为None或仅空白，则回退到默认提示词
            safe_summary_prompt = self.summary_prompt or ""
            if (
                isinstance(safe_summary_prompt, str)
                and safe_summary_prompt.strip() == ""
            ):
                safe_summary_prompt = DEFAULT_SUMMARY_PROMPT
            # 注意：不要写回 session.prompt，避免回调修改/清空后导致使用空prompt

            # 关键流程：直接调用 task_analyzer 执行任务分析
            try:
                self.task_analyzer._on_before_summary(
                    agent=self,
                    prompt=safe_summary_prompt,
                    auto_completed=auto_completed,
                    need_summary=self.need_summary,
                )
            except Exception:
                pass

            # 非关键流程：广播将要生成总结事件（用于日志、监控等）
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
            ret = self.model.chat_until_success(safe_summary_prompt)
            # 防御: 总结阶段模型可能返回空响应(None或空字符串)，统一为空字符串并告警
            if not ret:
                try:
                    PrettyOutput.auto_print(
                        "⚠️ 总结阶段模型返回空响应，已使用空字符串回退。"
                    )
                except Exception:
                    pass
                ret = ""
            result = ret

            # 打印任务总结内容给用户查看
            if ret and ret.strip():
                try:
                    import jarvis.jarvis_utils.globals as G
                    from jarvis.jarvis_utils.globals import console
                    from rich.panel import Panel
                    from rich import box

                    agent_name = self.name if hasattr(self, "name") else None
                    panel = Panel(
                        ret,
                        title=f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{agent_name or 'LLM'} 任务总结[/bold cyan]",
                        border_style="bright_green",
                        box=box.ROUNDED,
                        expand=True,
                    )
                    console.print(panel)
                except Exception:
                    # 如果格式化输出失败，回退到简单打印
                    PrettyOutput.auto_print(f"📋 任务总结:\n{ret}")

            # 非关键流程：广播完成总结事件（用于日志、监控等）
            try:
                self.event_bus.emit(
                    AFTER_SUMMARY,
                    agent=self,
                    summary=result,
                )
            except Exception:
                pass

            # 关键流程：直接调用 task_analyzer 和 memory_manager
        try:
            self.task_analyzer._on_task_completed(
                agent=self,
                auto_completed=auto_completed,
                need_summary=self.need_summary,
            )
        except Exception:
            pass

        try:
            self.memory_manager._ensure_memory_prompt(
                agent=self,
                auto_completed=auto_completed,
                need_summary=self.need_summary,
            )
        except Exception:
            pass

        # 非关键流程：广播任务完成事件（用于日志、监控等）
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
        try:
            return self.prompt_manager.build_default_addon_prompt(need_complete)
        except Exception:
            pass

        # 结构化系统指令（回退方案）
        action_handlers = ", ".join([handler.name() for handler in self.output_handler])

        # 任务完成提示
        complete_prompt = (
            f"- 如果任务已完成，只输出 {ot('!!!COMPLETE!!!')}，不要输出其他任何内容。任务总结将会在后面的交互中被询问。"
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
    {complete_prompt if complete_prompt else f"- 直接输出完成原因，不需要再有新的操作，不要输出{ot('TOOL_CALL')}标签"}
    如果没有完成，请进行下一步操作：
    - 仅包含一个操作
    - 如果信息不明确，请请求用户补充
    - 如果执行过程中连续失败5次，请请求用户操作
    - 工具调用必须使用{ot("TOOL_CALL")}和{ct("TOOL_CALL")}标签
    - 操作列表：{action_handlers}{memory_prompts}
    
    注意：如果当前部分任务已完成，之前的上下文价值不大，可以输出{ot("!!!SUMMARY!!!")}标记来触发总结并清空历史，以便开始新的任务阶段。
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
        # 根据当前模式生成额外说明，供 LLM 感知执行策略
        try:
            # 延迟导入CodeAgent以避免循环依赖
            from jarvis.jarvis_code_agent.code_agent import CodeAgent

            # 如果是CodeAgent实例，则跳过注册，由CodeAgent.run自行管理
            if not isinstance(self, CodeAgent):
                set_current_agent(self.name, self)  # 标记agent开始运行
            non_interactive_note = ""
            if getattr(self, "non_interactive", False):
                non_interactive_note = (
                    "\n\n[系统说明]\n"
                    "本次会话处于**非交互模式**：\n"
                    "- 在 PLAN 模式中给出清晰、可执行的详细计划后，应**自动进入 EXECUTE 模式执行计划**，不要等待用户额外确认；\n"
                    "- 在 EXECUTE 模式中，保持一步一步的小步提交和可回退策略，但不需要向用户反复询问“是否继续”；\n"
                    "- 如遇信息严重不足，可以在 RESEARCH 模式中自行补充必要分析，而不是卡在等待用户输入。\n"
                )

                # 如果是非交互模式，可以假设用户输入的是完整的需求
                self.pin_content = user_input

            # 将非交互模式说明添加到用户输入中
            enhanced_input = user_input + non_interactive_note
            self.session.prompt = enhanced_input

            # 关键流程：直接调用 memory_manager 重置任务状态
            try:
                self.memory_manager._on_task_started(
                    agent=self,
                    name=self.name,
                    description=self.description,
                    user_input=self.session.prompt,
                )
            except Exception:
                pass

            # 非关键流程：广播任务开始事件（用于日志、监控等）
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

            return self._main_loop()

        finally:
            if not isinstance(self, CodeAgent):
                clear_current_agent()

    def _main_loop(self) -> Any:
        """主运行循环"""
        # 委派至独立的运行循环类，保持行为一致
        loop = AgentRunLoop(self)
        self._agent_run_loop = loop  # 存储引用以便其他方法访问
        return loop.run()

    def set_non_interactive(self, value: bool) -> None:
        """设置非交互模式并管理自动完成状态。

        当进入非交互模式时，自动启用自动完成；
        当退出非交互模式时，恢复自动完成的原始值。

        参数:
            value: 是否启用非交互模式
        """
        # 保存auto_complete的原始值（如果是首次设置）
        if not hasattr(self, "_auto_complete_backup"):
            self._auto_complete_backup = self.auto_complete

        # 设置非交互模式（仅作为 Agent 实例属性，不写入环境变量或全局配置）
        self.non_interactive = value

        # 根据non_interactive的值调整auto_complete
        if value:  # 进入非交互模式
            self.auto_complete = True
        else:  # 退出非交互模式
            # 恢复auto_complete的原始值
            self.auto_complete = self._auto_complete_backup
            # 清理备份，避免状态污染
            delattr(self, "_auto_complete_backup")

    def _handle_run_interrupt(
        self, current_response: str
    ) -> Optional[Union[Any, "LoopAction"]]:
        """处理运行中的中断

        返回:
            None: 无中断，或中断后允许继续执行当前响应
            Any: 需要返回的最终结果
            LoopAction.SKIP_TURN: 中断后需要跳过当前响应，并立即开始下一次循环
        """
        if not get_interrupt():
            return None

        set_interrupt(False)

        # 被中断时，如果当前是非交互模式，立即切换到交互模式（在获取用户输入前）
        if self.non_interactive:
            self.set_non_interactive(False)

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
            if self.confirm_callback("检测到有工具调用，是否继续处理工具调用？", False):
                self.session.prompt = join_prompts(
                    [
                        f"被用户中断，用户补充信息为：{user_input}",
                        "用户同意继续工具调用。",
                    ]
                )
                return None  # 继续执行工具调用
            else:
                self.session.prompt = join_prompts(
                    [
                        f"被用户中断，用户补充信息为：{user_input}",
                        "检测到有工具调用，但被用户拒绝执行。请根据用户的补充信息重新考虑下一步操作。",
                    ]
                )
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
            return LoopAction.CONTINUE
        else:
            return LoopAction.COMPLETE

    def _first_run(self) -> None:
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
        """创建一个用于执行一次性任务的临时模型实例，以避免污染主会话。

        筛选操作使用cheap模型以降低成本。
        """
        from jarvis.jarvis_utils.config import get_cheap_model_name
        from jarvis.jarvis_utils.config import get_cheap_platform_name

        # 筛选操作使用cheap模型
        platform_name = get_cheap_platform_name(None)
        model_name = get_cheap_model_name(None)
        # 获取 cheap_llm 的 llm_config，确保使用正确的 API base 和 API key
        llm_config = get_llm_config("cheap", None)

        temp_model = PlatformRegistry().create_platform(platform_name, llm_config)
        if not temp_model:
            raise RuntimeError("创建临时模型失败。")

        temp_model.set_model_name(model_name)
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
            "multiline_inputer": self.multiline_inputer,
            "use_methodology": self.use_methodology,
            "use_analysis": self.use_analysis,
            "force_save_memory": self.force_save_memory,
            "files": self.files,
            "confirm_callback": self.confirm_callback,
            "non_interactive": True,
            "in_multi_agent": True,
        }

    def _filter_tools_if_needed(self, task: str) -> None:
        """如果工具数量超过阈值，使用大模型筛选相关工具

        注意：仅筛选用户自定义工具，内置工具不参与筛选（始终保留）
        """
        tool_registry = self.get_tool_registry()
        if not isinstance(tool_registry, ToolRegistry):
            return

        all_tools = tool_registry.get_all_tools()
        threshold = get_tool_filter_threshold()
        if len(all_tools) <= threshold:
            return

        # 获取用户自定义工具（非内置工具），仅对这些工具进行筛选
        custom_tools = tool_registry.get_custom_tools()
        if not custom_tools:
            # 没有用户自定义工具，无需筛选
            return

        # 为工具选择构建提示（仅包含用户自定义工具）
        tools_prompt_part = ""
        tool_names = []
        for i, tool in enumerate(custom_tools, 1):
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
        PrettyOutput.auto_print(
            f"ℹ️ 工具数量超过{threshold}个，正在使用AI筛选相关工具..."
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
            selected_tools_str = temp_model.chat_until_success(selection_prompt)

            # 解析响应并筛选工具
            selected_indices = [
                int(i.strip()) for i in re.findall(r"\d+", selected_tools_str)
            ]
            selected_tool_names = [
                tool_names[i - 1] for i in selected_indices if 0 < i <= len(tool_names)
            ]

            if selected_tool_names:
                # 移除重复项
                selected_tool_names = sorted(list(set(selected_tool_names)))
                # 合并内置工具名称和筛选出的用户自定义工具名称
                builtin_names = list(tool_registry._builtin_tool_names)
                final_tool_names = sorted(
                    list(set(builtin_names + selected_tool_names))
                )
                tool_registry.use_tools(final_tool_names)
                # 使用筛选后的工具列表重新设置系统提示
                self._setup_system_prompt()
                PrettyOutput.auto_print(
                    f"✅ 已筛选出 {len(selected_tool_names)} 个相关工具: {', '.join(selected_tool_names)}"
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
                PrettyOutput.auto_print("⚠️ AI 未能筛选出任何相关工具，将使用所有工具。")
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
            PrettyOutput.auto_print(f"❌ 工具筛选失败: {e}，将使用所有工具。")

    def _check_and_organize_memory(self) -> None:
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
            PrettyOutput.auto_print(f"⚠️ 检查记忆库时发生意外错误: {e}")

    def _perform_memory_check(
        self, memory_type: str, base_path: Path, scope_name: str
    ) -> None:
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
        if self.confirm_callback(prompt, False):
            PrettyOutput.auto_print(
                f"ℹ️ 正在开始整理 '{scope_name}' ({memory_type}) 记忆库..."
            )
            organizer.organize_memories(memory_type, min_overlap=3)
        else:
            PrettyOutput.auto_print(f"ℹ️ 已取消 '{scope_name}' 记忆库整理。")
