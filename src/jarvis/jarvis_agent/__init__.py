# -*- coding: utf-8 -*-
# 标准库导入
import datetime
import json
import os
import platform
import re
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

# 第三方库导入
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.callback_loader import CallbackLoader
from jarvis.jarvis_agent.model_switcher import ModelSwitcher
from jarvis.jarvis_agent.event_bus import EventBus
from jarvis.jarvis_agent.events import AFTER_ADDON_PROMPT
from jarvis.jarvis_agent.events import AFTER_HISTORY_CLEAR
from jarvis.jarvis_agent.events import AFTER_MODEL_CALL
from jarvis.jarvis_agent.events import AFTER_SUMMARY
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
from jarvis.jarvis_agent.rules_manager import RulesManager

# 本地库导入
# jarvis_agent 相关
from jarvis.jarvis_utils.config import is_enable_quick_mode
from jarvis.jarvis_utils.decision import decide_choice
from jarvis.jarvis_utils.exception_utils import save_exception
from jarvis.jarvis_utils.config import is_enable_request_classification
from jarvis.jarvis_agent.prompt_builder import build_action_prompt
from jarvis.jarvis_agent.prompt_builder import get_tool_registry
from jarvis.jarvis_agent.prompt_manager import PromptManager
from jarvis.jarvis_agent.history_compressor import HistoryCompressor
from jarvis.jarvis_agent.prompts import DEFAULT_SUMMARY_PROMPT

# 保持对外 re-export（历史摘要/压缩实现已迁至 history_compressor.py）
from jarvis.jarvis_agent.prompts import SUMMARY_REQUEST_PROMPT as SUMMARY_REQUEST_PROMPT
from jarvis.jarvis_agent.protocols import OutputHandlerProtocol
from jarvis.jarvis_agent.run_loop import AgentRunLoop, ensure_str
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
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.config import get_tool_filter_threshold
from jarvis.jarvis_utils.config import is_enable_memory_organizer
from jarvis.jarvis_utils.config import is_execute_tool_confirm
from jarvis.jarvis_utils.config import is_force_save_memory
from jarvis.jarvis_utils.config import is_use_analysis
from jarvis.jarvis_utils.config import is_use_methodology
from jarvis.jarvis_utils.globals import clear_current_agent
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import get_short_term_memories
from jarvis.jarvis_utils.globals import make_agent_name
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.globals import set_current_agent
from jarvis.jarvis_platform.content_types import ContentBlock
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


class SafeEncoder(json.JSONEncoder):
    """自定义JSON编码器，用于处理不可序列化的对象

    主要用于会话保存时的序列化，处理以下情况：
    - 函数对象：转换为字符串表示
    - 其他不可序列化对象：尝试转换为字符串
    """

    def default(self, o: Any) -> Any:
        """处理不可序列化的对象

        参数:
            o: 要序列化的对象

        返回:
            可序列化的对象
        """
        # 处理函数对象
        if callable(o):
            # 尝试获取函数名
            if hasattr(o, "__name__"):
                return f"<function:{o.__name__}>"
            # 尝试获取类名（对于可调用对象）
            elif hasattr(o, "__class__"):
                return f"<callable:{o.__class__.__name__}>"
            else:
                return "<function>"

        # 对于其他不可序列化的对象，尝试转换为字符串
        try:
            return str(o)
        except Exception:
            return "<unserializable_object>"


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

        PrettyOutput.print_resource_overview_panel(
            welcome_message=welcome_message,
            current_dir=current_dir,
            stats_parts=stats_parts,
        )

    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 加载统计信息失败: {e}")


origin_agent_system_prompt = f"""
<role>
# 🤖 Jarvis Agent
你是专业的任务执行助手，根据用户需求制定并执行详细计划。
</role>

## 核心模式

### ARCHER 工作流说明

#### ANALYZE（分析）
理解用户需求，明确任务目标与约束，识别可能需要的规则支撑。若需求不清晰，主动提问澄清。**只分析不设计方案**。

#### RULE（加载规则）
用 `load_rule` 加载相关规则与最佳实践，理解规则约束与要求。仅在需要专业知识指导时执行。

#### COLLECT（收集信息）
只读收集必要信息：必要时可用 `memory` 工具（action=retrieve）检索相关记忆获取历史信息；用合适的工具（如搜索工具、查询工具等）精准定位并获取相关信息，禁止臆测。对代码任务，用搜索工具（rg、fd）定位文件（必须带目录/后缀过滤），阅读目标文件及直接依赖。

#### HYPOTHESIZE（制定方案）
基于收集到的信息提出多个可行方案，比较各方案的优劣、风险、成本，询问用户偏好。用户答复后，根据任务繁简决定是否用 `task_list_manager` 建立任务列表，并制定详细执行计划。**必须明确每个方案的验收标准与清晰的执行步骤**，保证可量化、可验证、可执行。

**注意：此阶段完成后，必须经过用户确认，才能进入 EXECUTE 阶段。**

**用户确认方案后，必须用 `memory` 工具（action=save）将确认的方案存入短期记忆**，以便执行时随时参考。保存时应包含：
- 完整的执行计划（所有步骤）
- 影响范围（修改/新增/删除的文件）
- 风险评估与缓解策略
- 验收标准
- 任务理解与技术栈信息

建议使用标签如：["执行方案", "任务计划", "当前任务"] 等，便于后续检索。

**HYPOTHESIZE 阶段必须输出以下结构化内容：**

1. **任务理解**
   - 明确说明对用户需求的理解
   - 识别任务的核心目标与约束
   - 明确可能涉及的技术栈与依赖关系

2. **执行计划**
   - 列出详细执行步骤（按顺序编号）
   - 每步应当包含：操作内容、涉及文件/工具、预期结果
   - 对复杂任务，说明是否用 `task_list_manager` 进行任务拆分

3. **影响范围**
   - 列出将要修改的文件（新增/修改/删除）
   - 明确可能影响的功能模块
   - 评估对其他代码的依赖关系

4. **风险评估**
   - 识别潜在风险点与难点
   - 明确缓解策略与退路
   - 评估任务繁简（简单/中等/复杂）

5. **验收标准**
   - 明确每个方案的验收标准
   - 明确如何验证任务完成
   - 列出必须的测试与验证步骤

**输出格式示例：**
```
## 任务理解
[对任务的理解与核心目标]

## 执行计划
1. [步骤1：操作内容、涉及文件、预期结果]
2. [步骤2：操作内容、涉及文件、预期结果]
...

## 影响范围
- 修改文件：[文件列表]
- 新增文件：[文件列表]
- 涉及模块：[模块列表]

## 风险评估
- 风险点：[风险描述]
- 缓解策略：[策略描述]
- 任务繁简：[简单/中等/复杂]

## 验收标准
- [标准1]
- [标准2]
...

请确认此计划无误，确认后我将开始执行（输入"确认"、"继续"或"ENTER EXECUTE"）。
```

#### EXECUTE（执行）
按计划精确实施：先读后写（read_code 定位 → edit_file/edit_file_by_line 修改，大范围重写用 write_file），最小改动，单次回复单次工具调用，每次修改完成即验证。

#### REVIEW（复盘）
全面复盘工作成果：审查代码质量（语法/功能/风格），核对功能是否完成，检查受影响的代码是否都已考虑到，确认是否有配套的修改（如文档、测试、配置等），评估影响面与潜在风险，清理临时文件，确认可以安全回退。

### ARCHER 灵活执行指南
- **准备期（A→R→C）灵活**：ANALYZE 必需；RULE 与 COLLECT 可根据需要选择执行或调整顺序；简单任务可跳过 RULE/COLLECT
- **执行期（H→E→R）严格顺序**：HYPOTHESIZE → EXECUTE → REVIEW 必须按顺序执行，禁止跳步
- **各阶段可回退**：任何阶段都可根据需要回退至前一阶段，形成迭代闭环

## 执行规则
1. **单次操作**: 每次响应只包含一次工具调用
2. **禁止虚构**: 必须基于实际结果，禁止假设
3. **任务列表**: 复杂任务用 task_list_manager，简单任务直接执行
4. **必须验证**: 代码需要编译通过、功能验证
5. **模式切换**: 需要明确信号 "ENTER [MODE]"

## 工具使用
- 优先用 task_list_manager 执行复杂任务
- execute_task 必须提供 additional_info 参数
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

    # Commit 相关属性（CodeAgent 使用）
    prefix: str
    suffix: str

    # CodeAgent 特有属性（仅在 CodeAgent 实例中存在）
    disable_review: bool
    review_max_iterations: int
    tool_group: Optional[str]
    root_dir: str
    start_commit: Optional[str]
    last_backup_commit: Optional[str]

    # tmux 布局是否已设置（类级标志）
    _tmux_layout_set: bool = False

    # review 是否已执行（CodeAgent 使用，避免重复 review）
    _review_already_done: bool = False

    def agent_type(self) -> str:
        """获取Agent类型"""
        return self._agent_type

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
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="clear_history")
            pass

        # 非关键流程：广播清理历史前事件（用于日志、监控等）
        try:
            self.event_bus.emit(BEFORE_HISTORY_CLEAR, agent=self)
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="clear_history")
            pass

        # 清理会话历史并重置模型状态
        self.session.clear_history()
        # 重置 addon_prompt 跳过轮数计数器
        self._addon_prompt_skip_rounds = 0
        # 重置没有工具调用的计数器
        self._no_tool_call_count = 0
        # 重置最近一次LLM响应内容
        self._last_response_content = ""

        # 提示用户会话文件位置
        if Path(session_file_path).exists():
            PrettyOutput.auto_print(f"💾 当前会话记录已保存到: {session_file_path}")
            PrettyOutput.auto_print("🤖 大模型可以读取此文件了解完整对话历史")

        # 重置后重新设置系统提示词，确保系统约束仍然生效
        try:
            self._setup_system_prompt()
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="clear_history")
            pass

        # 非关键流程：广播清理历史后的事件（用于日志、监控等）
        try:
            self.event_bus.emit(AFTER_HISTORY_CLEAR, agent=self)
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="clear_history")
            pass

    def __del__(self) -> None:
        # 只有在记录启动时才停止记录
        pass

    def get_user_origin_input(self) -> Union[str, List[ContentBlock]]:
        """获取原始用户输入

        返回:
            Union[str, List[ContentBlock]]: 原始用户输入（未经任何增强处理）
        """
        return self.original_user_input

    def add_multimodal_content(self, content: List[ContentBlock]) -> None:
        """添加多模态内容到当前对话上下文

        Args:
            content: 多模态内容列表
        """
        if not content:
            return

        # 检查是否支持多模态
        if hasattr(self, "model") and not self.model.supports_multimodal():
            warning_msg = "⚠️ 当前模型不支持多模态输入，已跳过多模态内容添加。如需使用多模态功能，请在 llm_config 中设置 supports_multimodal: true"
            PrettyOutput.auto_print(warning_msg)
            return

        # 获取当前的 prompt
        current_prompt = self.session.prompt

        # 如果当前 prompt 是字符串，则转换为列表
        if isinstance(current_prompt, str):
            if current_prompt.strip():
                new_prompt: List[ContentBlock] = [
                    {"type": "text", "text": current_prompt}
                ]
            else:
                new_prompt = []
        else:
            new_prompt = current_prompt.copy() if current_prompt else []

        # 添加新的内容
        new_prompt.extend(content)

        # 更新 session.prompt
        self.session.prompt = new_prompt

        # 记录日志
        PrettyOutput.auto_print(f"✅ 已添加 {len(content)} 个多模态内容块到对话上下文")

    def get_tool_usage_prompt(self) -> str:
        """获取工具使用提示"""
        return build_action_prompt(self.output_handler)

    def __new__(cls, *args: Any, **kwargs: Any) -> "Agent":
        if kwargs.get("agent_type") == "code_agent":
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
        system_prompt: Optional[str] = None,
        name: str = "Jarvis",
        description: str = "",
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
        allow_savesession: bool = False,
        rule_names: Optional[str] = None,
        optimize_system_prompt: bool = False,
        enable_auto_rule_select: bool = True,
        model_type: str = "normal",
        quick_mode: bool = False,
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
            allow_savesession: 是否允许使用SaveSession命令（默认False，仅jvs/jca主程序传入True）
            rule_names: 规则名称列表（逗号分隔），用于加载指定的规则
            optimize_system_prompt: 如果为True，将在第一次run()时使用用户输入来优化系统提示词
            enable_auto_rule_select: 是否启用自动规则选择（默认True）
            model_type: 模型类型，可选 "normal"、"smart"、"cheap"（默认 "normal"）
        """

        # 基础属性初始化
        self._init_base_attributes(
            name,
            description,
            system_prompt,
            auto_complete,
            need_summary,
            use_methodology,
            use_analysis,
            execute_tool_confirm,
            summary_prompt,
            force_save_memory,
            files,
            use_tools,
            non_interactive,
            in_multi_agent,
            allow_savesession,
        )

        # 模型类型配置
        self._model_type = model_type
        # 手动切换模型标记（禁用自动切换）
        self._manual_model_switch = False
        # 极速模式配置（合并命令行参数和配置项）
        self.quick_mode = quick_mode or is_enable_quick_mode()

        # 核心组件初始化
        self._init_model()
        self._init_session()
        self._init_handlers(multiline_inputer, output_handler, use_tools or [])

        # 用户交互相关初始化（需要在 _init_handlers 之后，因为需要使用 self.multiline_inputer）
        self._init_user_interaction(confirm_callback, non_interactive)

        # 配置解析和设置
        self._init_config(
            use_methodology,
            use_analysis,
            execute_tool_confirm,
            force_save_memory,
            summary_prompt,
        )

        # 事件总线和管理器初始化
        self._init_managers()
        # 保存是否启用自动规则选择的标志
        self._enable_auto_rule_select = enable_auto_rule_select
        # 加载规则内容（确保 loaded_rules 和 loaded_rule_names 被初始化）
        self.loaded_rules, self.loaded_rule_names = self.rules_manager.load_all_rules(
            rule_names
        )

        # 工具和系统提示词设置
        self._setup_tools_and_prompt()

        # 设置延迟优化标志（将在第一次run()时优化）
        self._optimize_system_prompt_on_first_run = optimize_system_prompt
        self._system_prompt_optimized = False

        # 动态回调加载
        self._load_after_tool_callbacks()
        self._load_all_event_callbacks()

    def _init_base_attributes(
        self,
        name: str,
        description: str,
        system_prompt: Optional[str],
        auto_complete: bool,
        need_summary: bool,
        use_methodology: Optional[bool],
        use_analysis: Optional[bool],
        execute_tool_confirm: Optional[bool],
        summary_prompt: Optional[str],
        force_save_memory: Optional[bool],
        files: Optional[List[str]],
        use_tools: Optional[List[str]],
        non_interactive: Optional[bool],
        in_multi_agent: Optional[bool],
        allow_savesession: bool,
    ) -> None:
        """初始化基础属性

        参数:
            name: Agent名称
            description: Agent描述
            system_prompt: 系统提示词
            auto_complete: 是否自动完成
            need_summary: 是否需要总结
            use_methodology: 是否使用方法论
            use_analysis: 是否使用分析
            execute_tool_confirm: 执行工具前是否需要确认
            summary_prompt: 总结提示词
            force_save_memory: 是否强制保存记忆
            llm_group: 模型组
            files: 文件列表
            use_tools: 使用的工具列表
            non_interactive: 是否非交互模式
            in_multi_agent: 是否在多智能体模式
            allow_savesession: 是否允许保存会话
        """
        # 标识与描述
        self.name = make_agent_name(name)
        self.description = description
        self.system_prompt = system_prompt or ""

        # 行为控制开关（原始入参值，后续会根据配置进行解析和覆盖）
        self.auto_complete = bool(auto_complete)
        self.need_summary = bool(need_summary)
        self.use_methodology = use_methodology
        self.use_analysis = use_analysis
        self.execute_tool_confirm = execute_tool_confirm
        self.summary_prompt = summary_prompt
        self.force_save_memory = force_save_memory

        # 资源与环境配置
        self.files = files or []
        self.use_tools = use_tools
        self.non_interactive = non_interactive

        # 多智能体运行标志：用于控制非交互模式下的自动完成行为
        self.in_multi_agent = bool(in_multi_agent)

        # 运行时状态变量
        self.first = True
        self.run_input_handlers_next_turn = False
        self.user_data: Dict[str, Any] = {}
        self.pin_content: str = ""  # 记录固定的内容
        self.original_user_input: Union[str, List[ContentBlock]] = (
            ""  # 记录原始用户输入
        )
        self.recent_memories: List[str] = []  # 最近10条记忆内容
        self.MAX_RECENT_MEMORIES = 10  # 最大记忆数量
        self.return_control_on_auto_complete = False  # 自动完成后将控制权交还用户

        # 权限和状态控制
        self.allow_savesession = bool(allow_savesession)  # SaveSession 命令权限控制
        self._addon_prompt_skip_rounds = 0  # 记录连续未添加 addon_prompt 的轮数

        # 记忆标签收集：用于记录当前 agent 及其子 agent 产生的所有记忆标签
        self.memory_tags: set = set()  # 使用 set 自动去重
        self._no_tool_call_count = (
            0  # 记录连续没有工具调用的次数（用于非交互模式下的工具使用提示）
        )
        self._last_response_content = (
            ""  # 记录最近一次LLM响应内容（用于手动修复等操作）
        )
        self._last_handler_returned = False  # 记录最近一次输入处理器是否返回了消息
        self._agent_type = "agent"
        self._last_responses: List[str] = []  # 记录最近LLM响应（用于重复检测）
        self._repeat_detected = False  # 是否已检测到重复响应
        self._repeat_count = 0  # 连续相同响应计数
        self._repeat_escalation_level = 0  # 重复响应升级级别（0/1/2）

        # 原生工具调用状态（方案A：循环展开到 run_loop 主循环，每轮经过压缩/注入）
        self._pending_native_tool_calls: Optional[List[Dict[str, Any]]] = (
            None  # 待执行的原生 tool_calls
        )
        self._native_continue: bool = (
            False  # 是否处于原生工具续轮状态（上一轮已回填 tool 结果）
        )

        # 后台预压缩相关属性
        self._pre_compressed_summary: Optional[str] = None  # 后台预压缩生成的摘要
        self._pre_compressing: bool = False  # 是否正在后台预压缩
        self._pre_compress_snapshot_count: int = 0  # 预压缩时快照的消息数量

    def add_memory_tags(self, tags: List[str]) -> None:
        """添加记忆标签到 memory_tags 集合

        参数:
            tags: 要添加的标签列表
        """
        if tags:
            self.memory_tags.update(tags)

    def get_memory_tags(self) -> List[str]:
        """获取所有记忆标签

        返回:
            标签列表（已排序）
        """
        return sorted(list(self.memory_tags))

    def _init_user_interaction(
        self,
        confirm_callback: Optional[Callable[[str, bool], bool]],
        non_interactive: Optional[bool],
    ) -> None:
        """初始化用户交互相关组件

        参数:
            confirm_callback: 用户确认回调函数
            non_interactive: 是否非交互模式
        """
        # 用户确认回调：默认使用 CLI 的 user_confirm，可由外部注入以支持 TUI/GUI
        self.confirm_callback: Callable[[str, bool], bool] = (
            confirm_callback or user_confirm
        )

        # 初始化用户交互封装，保持向后兼容
        # 注意：self.multiline_inputer 已在 _init_handlers 中设置
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

    def _init_config(
        self,
        use_methodology: Optional[bool],
        use_analysis: Optional[bool],
        execute_tool_confirm: Optional[bool],
        force_save_memory: Optional[bool],
        summary_prompt: Optional[str],
    ) -> None:
        """解析并设置配置项

        参数:
            use_methodology: 是否使用方法论
            use_analysis: 是否使用分析
            execute_tool_confirm: 执行工具前是否需要确认
            force_save_memory: 是否强制保存记忆
            summary_prompt: 总结提示词
        """
        # 解析 use_methodology 配置
        try:
            resolved_use_methodology = bool(
                use_methodology if use_methodology is not None else is_use_methodology()
            )
        except Exception:
            resolved_use_methodology = (
                bool(use_methodology) if use_methodology is not None else True
            )

        # 解析 use_analysis 配置
        try:
            resolved_use_analysis = bool(
                use_analysis if use_analysis is not None else is_use_analysis()
            )
        except Exception:
            resolved_use_analysis = (
                bool(use_analysis) if use_analysis is not None else True
            )

        # 解析 execute_tool_confirm 配置
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

        # 解析 force_save_memory 配置
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

        # 应用解析后的配置值
        self.use_methodology = resolved_use_methodology
        self.use_analysis = resolved_use_analysis
        self.execute_tool_confirm = resolved_execute_tool_confirm
        self.summary_prompt = summary_prompt or DEFAULT_SUMMARY_PROMPT
        self.force_save_memory = resolved_force_save_memory

        # 根据运行模式设置 auto_complete
        # 多智能体模式下，默认不自动完成（即使是非交互），仅在明确传入 auto_complete=True 时开启
        if self.in_multi_agent:
            self.auto_complete = bool(self.auto_complete)
        else:
            # 非交互模式下默认自动完成；否则保持传入的 auto_complete 值
            self.auto_complete = bool(
                self.auto_complete or (self.non_interactive or False)
            )

    def _init_managers(self) -> None:
        """初始化事件总线和管理器"""
        # 初始化事件总线（需先于管理器，以便管理器在构造中安全订阅事件）
        self.event_bus = EventBus()

        # Hook/Modifier 机制（独立于 EventBus）
        # Hook：拦截型，回调返回 False 拦截执行
        self._before_tool_call_hooks: List[Callable] = []
        # Modifier：修改型，回调返回修改后的值
        self._before_model_call_modifiers: List[Callable] = []
        self._before_summary_modifiers: List[Callable] = []

        # 初始化各个功能管理器
        self.memory_manager = MemoryManager(self)  # 记忆管理器：管理长期和短期记忆
        self.task_analyzer = TaskAnalyzer(self)  # 任务分析器：分析任务完成度和满意度
        self.file_methodology_manager = FileMethodologyManager(
            self
        )  # 文件和方法论管理器：处理文件上传和方法论加载
        self.prompt_manager = PromptManager(self)  # 提示词管理器：构建和管理系统提示词
        self._history_compressor = HistoryCompressor(self)  # 历史摘要/压缩处理器
        self._callback_loader = CallbackLoader(self)  # 回调/事件加载处理器
        self._model_switcher = ModelSwitcher(self)  # 模型/平台切换处理器

        # 初始化任务列表管理器（使用当前工作目录作为 root_dir，如果子类已设置 root_dir 则使用子类的）
        root_dir = getattr(self, "root_dir", None) or os.getcwd()
        self.task_list_manager = TaskListManager(root_dir)

        # 初始化规则管理器（如果子类已经创建，则不覆盖）
        if not hasattr(self, "rules_manager"):
            self.rules_manager = RulesManager(root_dir)

    def _setup_tools_and_prompt(self) -> None:
        """设置工具和系统提示词"""
        # 如果配置了强制保存记忆，确保 memory 工具可用
        if self.force_save_memory:
            self._ensure_save_memory_tool()

        # 如果启用了分析，确保 methodology 工具可用
        if self.use_analysis:
            self._ensure_methodology_tool()

        # 设置系统提示词（基于配置和工具列表构建）
        self._setup_system_prompt()

    def _init_model(self) -> None:
        """初始化模型平台，根据 model_type 选择对应的平台（normal/smart/cheap）"""

        registry = PlatformRegistry()
        model_type = getattr(self, "_model_type", "normal")
        if model_type == "smart":
            self.model = registry.get_smart_platform()
        elif model_type == "cheap":
            self.model = registry.get_cheap_platform()
        else:
            self.model = registry.get_normal_platform()

        self.model.set_suppress_output(False)

        # 设置Agent引用，使Platform能够回调Agent方法（如自动总结）
        self.model.agent = self

    def _init_session(self) -> None:
        """初始化会话管理器"""
        self.session = SessionManager(
            model=self.model, agent_name=self.name, agent=self
        )

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

    # ------------------------------------------------------------------
    # 模型/平台切换：委托至 ModelSwitcher（实现见 model_switcher.py）
    # 保留同名方法，保证对外接口（含 run_loop / code_agent 的反向调用）不变。
    # ------------------------------------------------------------------
    def _switch_model_by_difficulty(self, difficulty: str) -> None:
        """根据任务难度切换模型（委托至 ModelSwitcher）"""
        return self._model_switcher.switch_model_by_difficulty(difficulty)

    def _classify_and_switch_model(
        self,
        user_input: Union[str, List[ContentBlock]],
        classify_fn: Callable,
        get_prompt_fn: Callable,
    ) -> None:
        """执行需求分类、模型切换、采样温度适配和系统提示词更新（委托至 ModelSwitcher）"""
        return self._model_switcher.classify_and_switch_model(
            user_input=user_input,
            classify_fn=classify_fn,
            get_prompt_fn=get_prompt_fn,
        )

    def _apply_task_temperature(self, temperature: Optional[float]) -> None:
        """按任务性质把推荐采样温度应用到当前模型（委托至 ModelSwitcher）"""
        return self._model_switcher.apply_task_temperature(temperature)

    def _setup_system_prompt(self) -> None:
        """设置系统提示词"""
        prompt_text = self.prompt_manager.build_system_prompt(self)
        self.model.set_system_prompt(prompt_text)

    def optimize_system_prompt(self, user_requirement: str) -> None:
        """根据用户需求优化系统提示词

        参数:
            user_requirement: 用户需求描述，用于优化系统提示词
        """
        try:
            from jarvis.jarvis_agent.prompt_optimizer import optimize_system_prompt

            # 获取当前系统提示词
            current_prompt = self.system_prompt

            # 优化系统提示词
            optimized_prompt = optimize_system_prompt(
                current_system_prompt=current_prompt, user_requirement=user_requirement
            )

            # 更新系统提示词
            if optimized_prompt and optimized_prompt != current_prompt:
                self.system_prompt = optimized_prompt
                # 重新设置系统提示词到模型
                self._setup_system_prompt()
        except Exception as e:
            PrettyOutput.auto_print(
                f"⚠️ 系统提示词优化失败: {str(e)}，继续使用原始系统提示词"
            )

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
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="_multiline_input"
            )
            pass
        try:
            # Try to pass the keyword for enhanced input handler
            return self.multiline_inputer(
                tip,
            )
        except TypeError:
            # Fallback for custom handlers that only accept one argument
            return self.multiline_inputer(tip)

    # ------------------------------------------------------------------
    # 回调/事件加载：委托至 CallbackLoader（实现见 callback_loader.py）
    # 保留同名方法，保证对外接口不变。
    # ------------------------------------------------------------------
    def _load_after_tool_callbacks(self) -> None:
        """扫描 after_tool_call_cb_dirs 并注册回调（委托至 CallbackLoader）"""
        return self._callback_loader.load_after_tool_callbacks()

    def _load_event_callbacks(
        self,
        event_name: str,
        config_getter: Callable[[], List[str]],
        callback_names: List[str],
        target: str = "event_bus",
    ) -> None:
        """通用的回调加载方法（委托至 CallbackLoader）"""
        return self._callback_loader.load_event_callbacks(
            event_name=event_name,
            config_getter=config_getter,
            callback_names=callback_names,
            target=target,
        )

    def _load_all_event_callbacks(self) -> None:
        """加载所有事件回调（委托至 CallbackLoader）"""
        return self._callback_loader.load_all_event_callbacks()

    def save_session(self) -> bool:
        """Saves the current session state by delegating to the session manager."""
        return self.session.save_session()

    def restore_session(
        self, restore_session: Optional[Union[bool, str]] = None
    ) -> bool:
        """Restores the session state by delegating to the session manager.

        Args:
            restore_session: 恢复会话的参数。
                - True: 交互式选择会话文件
                - str: 指定会话文件路径
                - None/False: 不恢复
        """
        if not restore_session:
            return False

        if isinstance(restore_session, str):
            # 指定文件路径恢复
            session_restored = self.session.restore_session_from_file(restore_session)
        else:
            # 交互式选择恢复
            session_restored = self.session.restore_session()

        if session_restored:
            self.first = False
        return session_restored

    def get_tool_registry(self) -> Optional[Any]:
        """获取工具注册表实例"""
        return get_tool_registry(self.output_handler)

    def _native_active(self) -> bool:
        """当前 agent 是否应走原生 function calling。"""
        try:
            from jarvis.jarvis_utils.config import is_enable_native_tool_calls

            if not is_enable_native_tool_calls():
                return False
            model = getattr(self, "model", None)
            if model is None:
                return False
            if not getattr(model, "supports_native_tool_calls", lambda: False)():
                return False
            if getattr(model, "_native_disabled", False):
                return False
            registry = self.get_tool_registry()
            if not registry or not getattr(registry, "tools", None):
                return False
            return True
        except Exception:
            return False

    def _native_tools(self) -> list:
        """构建当前平台所需的原生工具 schema。"""
        from jarvis.jarvis_platform.claude import ClaudeModel
        from jarvis.jarvis_platform.native_tools import (
            build_anthropic_tools,
            build_openai_tools,
        )
        from jarvis.jarvis_platform.openai import OpenAIModel

        registry = self.get_tool_registry()
        if not registry:
            return []
        if isinstance(self.model, OpenAIModel):
            return build_openai_tools(registry)
        if isinstance(self.model, ClaudeModel):
            return build_anthropic_tools(registry)
        return []

    def _execute_pending_native_calls(self) -> None:
        """执行待处理的原生 tool_calls 并回填 role=tool 结果。

        由 run_loop 主循环在每轮模型调用后调用（方案A：原生工具循环展开到主循环）。
        执行后清空 _pending_native_tool_calls，并置 _native_continue 供下一轮续轮。
        """
        calls = self._pending_native_tool_calls or []
        if not calls:
            return
        model = self.model
        outputs = self._execute_native_batch(calls)
        for call, out in zip(calls, outputs):
            call_id = call.get("id", "") or ""
            name = call.get("name", "") or "unknown"
            # 每个 tool_call_id 都要回包，否则 OpenAI/Anthropic 报 pairing 400
            if call_id:
                model.append_native_tool_result(call_id, name, out)
        # 与文本协议一致：工具执行后触发 AFTER_TOOL_CALL 回调与事件
        # （供 diff 可视化 / 自动提交 / 构建验证 / lint 等旁路使用）
        self._fire_after_tool_call()
        self._pending_native_tool_calls = None
        self._native_continue = True

    def _run_native_until_content(self, message: str) -> str:
        """执行原生工具循环直到模型返回纯 content（供非主循环场景使用）。

        与主循环展开方案不同，此方法在内部完成多轮 tool_calls 执行与回填，
        适用于 memory_manager / task_analyzer 等不经过 run_loop 主循环的调用方。
        """
        from jarvis.jarvis_platform.claude import ClaudeModel
        from jarvis.jarvis_platform.openai import OpenAIModel
        from jarvis.jarvis_utils.globals import get_interrupt

        model = self.model
        if not isinstance(model, (OpenAIModel, ClaudeModel)):
            return model.chat_until_success(message)

        content, calls = model.chat_native_once(
            message, self._native_tools(), append_user=True
        )
        guard = 0
        while calls and guard < 30:
            guard += 1
            self._pending_native_tool_calls = calls
            self._execute_pending_native_calls()
            if get_interrupt():
                break
            content, calls = model.chat_native_once(
                None, self._native_tools(), append_user=False
            )
        self._pending_native_tool_calls = None
        self._native_continue = False
        return content or ""

    def _fire_after_tool_call(self) -> None:
        """触发 AFTER_TOOL_CALL（委托至 CallbackLoader）"""
        return self._callback_loader.fire_after_tool_call()

    def _exec_native_one(self, call: Dict[str, Any]) -> str:
        """串行执行单个原生工具调用（含确认门控与拒绝处理）。"""
        name = call.get("name", "")
        if not name:
            return ""
        if getattr(self, "execute_tool_confirm", False):
            try:
                ok = self.confirm_callback(f"执行原生工具 {name} ？", False)
            except Exception:
                ok = False
            if not ok:
                return "用户拒绝执行该工具，请据此调整方案。"
        try:
            registry = self.get_tool_registry()
            if registry is None:
                return f"工具 {name} 执行失败: 工具注册表不可用"
            return registry.execute_native_tool_call(
                name, call.get("arguments") or {}, self
            )
        except Exception as e:
            return f"工具 {name} 执行异常: {e}"

    def _execute_native_batch(self, calls: List[Dict[str, Any]]) -> List[str]:
        """执行一批原生 tool_calls，按原顺序返回各工具的结果文本。

        - 含可交互/独占工具（execute_script/virtual_tty 等）、需要用户确认、或仅单条时：逐条串行；
        - 否则对互不依赖的只读类工具并行执行（线程池，最多 4 并发）。
        """
        non_parallel = {
            "execute_script",
            "virtual_tty",
            "task_list_manager",
            "gateway_manager",
            "edit_file",
            "edit_file_by_line",
            "write_file",
            "add_images",
            "meta_agent",
        }
        registry = self.get_tool_registry()

        def _is_serial(name: str) -> bool:
            # 内置名单或工具声明 interactive（用户自定义工具可用 interactive=True 声明）
            if name in non_parallel:
                return True
            if registry is None:
                return False
            tool = registry.get_tool(name)
            if tool is None:
                return False
            return bool(getattr(tool, "interactive", False))

        names = [c.get("name", "") for c in calls]
        any_serial = any(_is_serial(n) for n in names if n)
        parallel_ok = (
            not getattr(self, "execute_tool_confirm", False)
            and len(calls) > 1
            and bool(names)
            and not any_serial
        )
        if not parallel_ok:
            return [self._exec_native_one(c) for c in calls]

        from concurrent.futures import ThreadPoolExecutor

        def run(call: Dict[str, Any]) -> str:
            n = call.get("name", "")
            try:
                if registry is None:
                    return f"工具 {n} 执行失败: 工具注册表不可用"
                return registry.execute_native_tool_call(
                    n, call.get("arguments") or {}, self, record=False
                )
            except Exception as e:
                return f"工具 {n} 执行异常: {e}"

        with ThreadPoolExecutor(max_workers=min(len(calls), 4)) as executor:
            futures = [executor.submit(run, c) for c in calls]
            outputs = [f.result() for f in futures]

        # 并行下统一记录已执行工具，避免共享状态竞态
        try:
            prev = self.get_user_data("__executed_tools__")
            prev = prev if isinstance(prev, list) else []
            self.set_user_data("__executed_tools__", prev + [n for n in names if n])
            if names:
                self.set_user_data("__last_executed_tool__", names[-1])
        except Exception:
            pass
        return outputs

    def _ensure_save_memory_tool(self) -> None:
        """如果配置了强制保存记忆，确保 memory 工具在 use_tools 列表中"""
        try:
            tool_registry = self.get_tool_registry()
            if not tool_registry:
                return

            # 检查 memory 工具是否已注册（工具默认都会注册）
            if not tool_registry.get_tool("memory"):
                # 如果工具本身不存在，则无法使用，直接返回
                return

            # 检查 memory 是否在 use_tools 列表中
            # 如果 use_tools 为 None，表示使用所有工具，无需添加
            if self.use_tools is None:
                return

            # 如果 memory 不在 use_tools 列表中，则添加
            if "memory" not in self.use_tools:
                self.use_tools.append("memory")
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
        self,
        message: Union[str, List[ContentBlock]],
        need_complete: bool = False,
        run_input_handlers: bool = True,
    ) -> str:
        """调用AI模型并实现重试逻辑

        参数:
            message: 输入给模型的消息，支持纯文本或多模态内容
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
            if not message or self._last_handler_returned:
                return ""

        # 添加附加提示
        message = self._add_addon_prompt(message, need_complete)

        # 广播模型调用前事件（不影响主流程）
        # 调用模型（_invoke_model 内部会触发 BEFORE_MODEL_CALL Modifier + Event）
        response = self._invoke_model(message)

        return response

    def _process_input(
        self, message: Union[str, List[ContentBlock]]
    ) -> Union[str, List[ContentBlock]]:
        """处理输入消息

        注意：输入处理器目前仅支持文本消息。如果是多模态消息，将跳过输入处理器。
        """
        if isinstance(message, list):
            self._last_handler_returned = False
            return message

        for handler in self.input_handler:
            message, need_return = handler(message, self)
            if need_return:
                self._last_handler_returned = True
                return message
        self._last_handler_returned = False
        return message

    def _add_addon_prompt(
        self, message: Union[str, List[ContentBlock]], need_complete: bool
    ) -> Union[str, List[ContentBlock]]:
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
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="_add_addon_prompt"
            )
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
            # 对于多模态内容，检查文本部分的长度
            message_len = (
                len(message)
                if isinstance(message, str)
                else sum(
                    len(b.get("text", "")) if b.get("type") == "text" else 0
                    for b in message
                )
            )
            # 原生工具调用下不自动注入默认 addon（工具由 API tools 提供，避免每轮重复指令/干扰原生循环）
            if message_len > threshold and not self._native_active():
                addon_text = self.make_default_addon_prompt(need_complete)
                message = join_prompts([message, addon_text])
                should_add = True
            # 条件2：连续10轮都没有添加过 addon_prompt，强制添加一次（仅文本协议）
            elif self._addon_prompt_skip_rounds >= 10 and not self._native_active():
                addon_text = self.make_default_addon_prompt(need_complete)
                message = join_prompts([message, addon_text])
                should_add = True

        # 更新计数器：如果添加了 addon_prompt，重置计数器；否则递增
        # 但如果 input_handler 已处理本轮（如执行 shell 命令），跳过计数
        if should_add:
            self._addon_prompt_skip_rounds = 0
        elif not self._last_handler_returned:
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
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="_add_addon_prompt"
            )
            pass
        return message

    def _invoke_model(self, message: Union[str, List[ContentBlock]]) -> str:
        """实际调用模型获取响应"""
        if not self.model:
            raise RuntimeError("Model not initialized")

        # Modifier：调用 before_model_call modifiers（修改型）
        # 回调返回修改后的 message，用于修改提示词
        for modifier in self._before_model_call_modifiers:
            try:
                result = modifier(agent=self, message=message)
                if result is not None:
                    message = result
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.__init__", function="_invoke_model"
                )
                pass

        # 事件：模型调用前（通知型）
        try:
            self.event_bus.emit(
                BEFORE_MODEL_CALL,
                agent=self,
                message=message,
            )
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="_invoke_model")
            pass

        if self._native_active():
            # 原生 function calling：每次只做一次模型调用，返回 content 并把 tool_calls 存入
            # _pending_native_tool_calls，由 run_loop 主循环执行工具、回填 role=tool 后继续下一轮，
            # 从而每轮都经过主循环的上下文压缩 / input_buffer 注入 / 轮次检查。
            from jarvis.jarvis_platform.claude import ClaudeModel
            from jarvis.jarvis_platform.openai import OpenAIModel

            model = self.model
            if not isinstance(model, (OpenAIModel, ClaudeModel)):
                response = model.chat_until_success(message)
            else:
                if self._native_continue:
                    # 续轮：上一轮 tool_calls 已回填 role=tool。若本轮有补充消息
                    # （input_buffer 注入 / addon），作为 user 消息追加使其生效；否则基于历史继续。
                    if isinstance(message, str) and message.strip():
                        content, calls = model.chat_native_once(
                            message, self._native_tools(), append_user=True
                        )
                    else:
                        content, calls = model.chat_native_once(
                            None, self._native_tools(), append_user=False
                        )
                    self._native_continue = False
                elif isinstance(message, str) and message.strip():
                    content, calls = model.chat_native_once(
                        message, self._native_tools(), append_user=True
                    )
                else:
                    content, calls = None, None
                self._pending_native_tool_calls = calls
                response = content or ""
        else:
            response = self.model.chat_until_success(message)
        # 防御: 模型可能返回空响应(None或空字符串)，统一为空字符串并告警。
        # 但原生工具调用返回 tool_calls 时 content 为空是正常情况（模型决定调用工具而非回复文本），不告警。
        if not response and not self._pending_native_tool_calls:
            try:
                PrettyOutput.auto_print("⚠️ 模型返回空响应，已使用空字符串回退。")
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.__init__", function="_invoke_model"
                )
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
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="_invoke_model")
            pass

        return response

    # ------------------------------------------------------------------
    # 历史摘要/压缩：委托至 HistoryCompressor（实现见 history_compressor.py）
    # 保留同名方法，保证对外接口（含 run_loop / code_agent 的反向调用）不变。
    # ------------------------------------------------------------------
    def _validate_summary(self, summary: str) -> tuple[bool, list[str]]:
        """检查摘要是否可接受（委托至 HistoryCompressor）"""
        return self._history_compressor.validate_summary(summary)

    def generate_summary(self, for_token_limit: bool = False) -> str:
        """生成对话历史摘要（委托至 HistoryCompressor）"""
        return self._history_compressor.generate_summary(
            for_token_limit=for_token_limit
        )

    def _print_compression_summary(self, summary: str, compression_type: str) -> None:
        """使用 Panel 打印压缩摘要（委托至 HistoryCompressor）"""
        return self._history_compressor.print_compression_summary(
            summary, compression_type
        )

    def _sliding_window_compression(self, window_size: Optional[int] = None) -> bool:
        """滑动窗口压缩（委托至 HistoryCompressor）"""
        return self._history_compressor.sliding_window_compression(
            window_size=window_size
        )

    def _start_background_pre_compression(self) -> None:
        """启动后台预压缩（委托至 HistoryCompressor）"""
        return self._history_compressor.start_background_pre_compression()

    def _check_and_use_pre_compressed_summary(self) -> bool:
        """检查并使用预压缩摘要重建会话（委托至 HistoryCompressor）"""
        return self._history_compressor.check_and_use_pre_compressed_summary()

    def _format_compressed_summary(self, compressed_summary: str) -> str:
        """格式化压缩后的摘要（委托至 HistoryCompressor）"""
        return self._history_compressor.format_compressed_summary(compressed_summary)

    def _adaptive_compression(self) -> bool:
        """自适应压缩（委托至 HistoryCompressor）"""
        return self._history_compressor.adaptive_compression()

    def _summarize_and_clear_history(
        self, trigger_reason: str = "Token限制触发"
    ) -> str:
        """总结当前对话并清理历史记录（委托至 HistoryCompressor）"""
        return self._history_compressor.summarize_and_clear_history(
            trigger_reason=trigger_reason
        )

    def _handle_history_with_summary(self) -> str:
        """使用摘要方式处理历史（委托至 HistoryCompressor）"""
        return self._history_compressor.handle_history_with_summary()

    def _format_summary_message(self, summary: str) -> str:
        """格式化摘要消息（委托至 HistoryCompressor）"""
        return self._history_compressor.format_summary_message(summary)

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

        # 🔧 修复：任务分析和总结解耦，use_analysis 独立于 need_summary
        # 关键流程：直接调用 task_analyzer 执行任务分析（内部会根据模式决定是否询问）
        if self.use_analysis:
            try:
                self.task_analyzer.trigger_task_analysis(auto_completed=auto_completed)
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.__init__", function="_complete_task"
                )
                pass

        if self.need_summary:
            # 确保总结提示词非空：若为None或仅空白，则回退到默认提示词
            safe_summary_prompt = self.summary_prompt or ""
            if (
                isinstance(safe_summary_prompt, str)
                and safe_summary_prompt.strip() == ""
            ):
                safe_summary_prompt = DEFAULT_SUMMARY_PROMPT
            # 注意：不要写回 session.prompt，避免回调修改/清空后导致使用空prompt

            # Modifier：调用 before_summary modifiers（修改型）
            # 回调返回修改后的 prompt，用于修改总结提示词
            for modifier in self._before_summary_modifiers:
                try:
                    result = modifier(
                        agent=self,
                        prompt=safe_summary_prompt,
                        auto_completed=auto_completed,
                    )
                    if result is not None:
                        safe_summary_prompt = result
                except Exception as e:
                    save_exception(
                        e, module="jarvis_agent.__init__", function="_complete_task"
                    )
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
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.__init__", function="_complete_task"
                )
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
                except Exception as e:
                    save_exception(
                        e, module="jarvis_agent.__init__", function="_complete_task"
                    )
                    pass
                ret = ""
            result = ret

            # 打印任务总结内容给用户查看
            if ret and ret.strip():
                try:
                    import jarvis.jarvis_utils.globals as G

                    title = f"[bold cyan]{(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{self.model.model_name or 'LLM'} 任务总结[/bold cyan]"
                    PrettyOutput.print_markdown(
                        ret, title=title, border_style="bright_green"
                    )
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
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.__init__", function="_complete_task"
                )
                pass

            # 关键流程：直接调用 task_analyzer 和 memory_manager

        # 不管是否需要summary，都打印原始用户输入，帮助用户区分多个任务
        if self.non_interactive:
            if self.original_user_input:
                PrettyOutput.auto_print(f"📝 原始任务输入:\n{self.original_user_input}")

        try:
            self.memory_manager._ensure_memory_prompt(
                agent=self,
                auto_completed=auto_completed,
                need_summary=self.need_summary,
            )
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="_complete_task")
            pass

        # 非关键流程：广播任务完成事件（用于日志、监控等）
        try:
            self.event_bus.emit(
                TASK_COMPLETED,
                agent=self,
                auto_completed=auto_completed,
                need_summary=self.need_summary,
            )
        except Exception as e:
            save_exception(e, module="jarvis_agent.__init__", function="_complete_task")
            pass

        # 如果有记忆标签，在返回结果中添加提示信息
        memory_tags = self.get_memory_tags()
        if memory_tags:
            tags_str = ", ".join(f"`{tag}`" for tag in memory_tags)
            memory_hint = f"\n\n💡 **记忆标签提示**: 本次任务产生了以下记忆标签: {tags_str}\n你可以使用 `memory` 工具（action=retrieve）通过这些标签检索相关记忆，获取更多详细信息。"
            result = result + memory_hint

        return result

    def make_default_addon_prompt(self, need_complete: bool) -> str:
        """生成附加提示。

        参数:
            need_complete: 是否需要完成任务

        """
        # 优先使用 PromptManager 以保持逻辑集中
        try:
            return self.prompt_manager.build_default_addon_prompt(need_complete)
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="make_default_addon_prompt"
            )
            pass

        # 结构化系统指令（回退方案）
        action_handlers = ", ".join([handler.name() for handler in self.output_handler])

        # 任务完成提示
        complete_prompt = (
            f"- 若整个任务已完成，只输出 {ot('!!!COMPLETE!!!')}，不要输出其他内容；任务总结将在后续交互中询问。"
            if need_complete and self.auto_complete
            else ""
        )

        # 原生 function calling 激活时不注入文本 JSON/操作清单指令
        if self._native_active():
            tool_lines = (
                "- 需要执行操作时，直接发起工具调用；工具名与参数以当前上下文给出的工具定义为准"
                "\n        - 一次可调用一个或多个互不依赖的工具；有依赖则先等前一个结果再调用下一个"
            )
            actions_line = ""
        else:
            tool_registry = self.get_tool_registry()
            memory_prompts = self.memory_manager.add_memory_prompts_to_addon(
                "", tool_registry
            )
            tool_lines = (
                "- 工具调用直接输出 JSON 对象，无需任何标签包裹"
                "\n        - 一次可调用一个或多个工具，但多个工具之间必须**互不依赖**"
                "（前者的结果/副作用不能作为后者的输入）；存在依赖时先调用被依赖的工具，等结果后再调下一个"
            )
            actions_line = f"- 可用操作：{action_handlers}{memory_prompts}"

        addon_prompt = f"""
<system_prompt>
    先判断整个任务是否已完成：

    - 若已完成：
        {complete_prompt if complete_prompt else "- 说明完成原因并停止，不要再发起新的工具调用"}
    - 若未完成，继续推进下一步：
        - 写文件等大段内容时不要一次性写满，应分多次写入，以免被长度上限截断
        - 需求或信息不明确时，先向用户询问补充
        - 连续 5 次执行失败时，停止并向用户询问应如何继续
        {tool_lines}
        {actions_line}

    补充：若当前这阶段的任务已完成、之前上下文价值不大，可输出 {ot("!!!SUMMARY!!!")} 触发压缩并清空历史，以便开启新阶段。
</system_prompt>

请继续。
"""

        return addon_prompt

    def run(self, user_input: Union[str, List[ContentBlock]]) -> Any:
        """处理用户输入并执行任务

        参数:
            user_input: 任务描述或请求，支持纯文本或多模态内容

        返回:
            str|Dict: 任务总结报告或要发送的消息

        注意:
            1. 这是Agent的主运行循环
            2. 处理完整的任务生命周期
            3. 包含错误处理和恢复逻辑
            4. 自动加载相关方法论(如果是首次运行)
        """
        # 设置tmux窗口平铺布局（仅在首次运行时执行一次）
        if not hasattr(Agent, "_tmux_layout_set"):
            Agent._tmux_layout_set = False
        if not Agent._tmux_layout_set:
            Agent._tmux_layout_set = True
            try:
                if "TMUX" in os.environ:
                    # 在tmux环境中，设置当前窗口为平铺布局
                    import subprocess

                    subprocess.run(
                        ["tmux", "select-layout", "tiled"],
                        check=True,
                        timeout=5,
                    )
            except Exception:
                # 静默失败，不影响正常使用
                pass

        # 如果需要延迟优化系统提示词，在第一次运行时进行优化
        if (
            self._optimize_system_prompt_on_first_run
            and not self._system_prompt_optimized
        ):
            # 检查 user_input 是否有内容
            has_content = False
            text_input = ""
            if user_input:
                if isinstance(user_input, str):
                    if user_input.strip():
                        has_content = True
                        text_input = user_input.strip()
                else:
                    # 多模态内容
                    text_parts = [
                        b.get("text", "") for b in user_input if b.get("type") == "text"
                    ]
                    text_input = "\n".join(text_parts).strip()
                    if text_input:
                        has_content = True

            if has_content:
                self.optimize_system_prompt(text_input)
                self._system_prompt_optimized = True
        # 根据当前模式生成额外说明，供 LLM 感知执行策略
        # 延迟导入CodeAgent以避免循环依赖
        try:
            from jarvis.jarvis_code_agent.code_agent import CodeAgent
        except ImportError as e:
            raise RuntimeError(
                "CodeAgent could not be imported. Please ensure jarvis_code_agent is installed correctly."
            ) from e

        try:
            # 保存原始任务目标（用于长期运行时的上下文保持）
            # 只在第一次运行时设置原始任务目标，确保交互模式下后续输入不会覆盖原始目标
            if not self.original_user_input:
                self.original_user_input = user_input

            # 如果是CodeAgent实例，则跳过注册，由CodeAgent.run自行管理
            if not isinstance(self, CodeAgent):
                set_current_agent(self.name, self)  # 标记agent开始运行

                # 通用Agent需求分类（仅在首次运行且启用分类时执行）
                if (
                    self.first
                    and is_enable_request_classification()
                    and not self.quick_mode
                ):
                    from jarvis.jarvis_agent.agent_prompts import (
                        classify_user_request,
                        get_system_prompt,
                    )

                    self._classify_and_switch_model(
                        user_input, classify_user_request, get_system_prompt
                    )

            non_interactive_note = ""
            if getattr(self, "non_interactive", False):
                non_interactive_note = (
                    "\n\n[系统说明]\n"
                    "本次会话处于**非交互模式**：\n"
                    "- 在 PLAN 模式中给出清晰、可执行的详细计划后，应**自动进入 EXECUTE 模式执行该计划**，无需等待用户额外确认；\n"
                    "- 在 EXECUTE 模式中，保持逐步的小步提交与可回退策略，但无需向用户反复询问'是否继续'；\n"
                    "- 若遇到信息严重不足，可在 RESEARCH 模式中自行补充必要的分析，而不是困于等待用户输入。\n"
                )

                # 非交互模式下不再自动设置pin_content

            # 将非交互模式说明添加到用户输入中
            enhanced_input: Union[str, List[ContentBlock]]
            if non_interactive_note:
                if isinstance(user_input, str):
                    enhanced_input = user_input + non_interactive_note
                else:
                    # 对于多模态内容，将说明作为文本块添加到末尾
                    enhanced_input = user_input + cast(
                        List[ContentBlock],
                        [{"type": "text", "text": non_interactive_note}],
                    )
            else:
                enhanced_input = user_input

            # 先设置 session.prompt，确保 _first_run() 中可以访问到用户输入
            # 注意：此时还没有添加已激活的规则内容，规则内容会在之后追加
            self.session.prompt = enhanced_input

            # 首次运行初始化（包括自动规则选择）
            # 必须在获取规则内容之前执行，否则规则索引会被错误的规则内容覆盖
            if self.first:
                self._first_run()
                # 极速模式提示
                if self.quick_mode:
                    from jarvis.jarvis_utils.output import PrettyOutput

                    PrettyOutput.auto_print(
                        "⚡ 极速模式已启用：跳过任务分类、规则加载、上下文推荐"
                    )

            # 将已加载的规则内容添加到用户输入的最前面
            active_rules_content = self.rules_manager.get_injectable_rules_content()
            if active_rules_content:
                enhanced_input = (
                    f"<rules>\n{active_rules_content}\n</rules>\n\n{enhanced_input}"
                )
                # 更新 session.prompt，添加规则内容
                self.session.prompt = enhanced_input

            # 关键流程：直接调用 memory_manager 重置任务状态
            try:
                self.memory_manager._on_task_started(
                    agent=self,
                    name=self.name,
                    description=self.description,
                    user_input=self.session.prompt,
                )
            except Exception as e:
                save_exception(e, module="jarvis_agent.__init__", function="run")
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
            except Exception as e:
                save_exception(e, module="jarvis_agent.__init__", function="run")
                pass

            return self._main_loop()

        finally:
            if not isinstance(self, CodeAgent):
                clear_current_agent()

    def analysis(self, satisfaction_feedback: str = "") -> None:
        """直接执行任务分析（跳过用户确认）

        该方法提供了任务分析的直接接口，可以立即执行任务分析流程，
        包括保存记忆、生成方法论等操作，无需用户确认。

        参数:
            satisfaction_feedback: 满意度反馈内容（可选）。
                - 如果提供，则直接使用该反馈进行分析
                - 如果为空字符串，则不收集反馈，直接进行分析

        示例:
            >>> agent.analysis()  # 直接分析，无反馈
            >>> agent.analysis("用户满意")  # 带反馈的分析

        注意:
            - 该方法会跳过用户确认环节
            - 适用于自动化场景或需要程序化调用的场景
            - 如需用户确认和反馈收集，请使用 task_analyzer.trigger_task_analysis()
        """
        self.task_analyzer.analysis_task(satisfaction_feedback)

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
        # 保存auto_complete和need_summary的原始值（如果是首次设置）
        if not hasattr(self, "_auto_complete_backup"):
            self._auto_complete_backup = self.auto_complete
        if not hasattr(self, "_need_summary_backup"):
            self._need_summary_backup = self.need_summary

        # 设置非交互模式（仅作为 Agent 实例属性，不写入环境变量或全局配置）
        self.non_interactive = value

        # 同步更新 SessionManager 的非交互模式状态
        self.session.non_interactive = value

        # 根据non_interactive的值调整auto_complete和need_summary
        if value:  # 进入非交互模式
            self.auto_complete = True
            # 进入非交互模式时，禁用总结（避免自动完成时触发总结）
            self.need_summary = False
        else:  # 退出非交互模式
            # 恢复auto_complete和need_summary的原始值
            self.auto_complete = self._auto_complete_backup
            self.need_summary = self._need_summary_backup
            # 清理备份，避免状态污染
            delattr(self, "_auto_complete_backup")
            delattr(self, "_need_summary_backup")

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

        # 原生工具调用路径：中断后丢弃本轮尚未执行的待调用工具，
        # 避免 run_loop 主循环在中断恢复后仍执行这些 tool_calls。
        # （模型下一轮会基于用户补充信息重新决策，而非沿用已中断的输出）
        self._pending_native_tool_calls = None

        # 被中断时，如果当前是非交互模式，立即切换到交互模式（在获取用户输入前）
        if self.non_interactive:
            self.set_non_interactive(False)

        user_input = self._multiline_input(
            "模型交互期间被中断，请输入用户干预信息", False
        )
        # 广播中断事件（包含用户输入，可能为空字符串）
        try:
            self.event_bus.emit(
                INTERRUPT_TRIGGERED,
                agent=self,
                current_response=current_response,
                user_input=user_input,
            )
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="_handle_run_interrupt"
            )
            pass

        self.run_input_handlers_next_turn = True

        if not user_input:
            # 用户输入为空，完成任务
            # 退出自动完成模式，防止 _execute_auto_complete 重复调用 _complete_task
            self.return_control_on_auto_complete = True
            return self._complete_task(auto_completed=False)

        # 处理输入（包括 shell 命令等），让 input_handler 有机会处理
        processed_input = self._process_input(user_input)

        # 如果输入处理器返回了空字符串或标记需要返回，说明已经被处理（如 shell 命令）
        if not processed_input or self._last_handler_returned:
            # 输入已被处理器处理（如执行了 shell 命令），不需要继续
            return LoopAction.SKIP_TURN

        if any(handler.can_handle(current_response) for handler in self.output_handler):
            if self.confirm_callback("检测到工具调用，是否继续执行工具调用？", False):
                self.session.prompt = join_prompts(
                    [
                        f"用户中断了操作，用户补充信息为：{processed_input}",
                        "用户允许继续执行工具调用。",
                    ]
                )
                return None  # 继续执行工具调用
            else:
                self.session.prompt = join_prompts(
                    [
                        f"用户中断了操作，用户补充信息为：{processed_input}",
                        "检测到工具调用，但用户拒绝执行。请根据用户的补充信息重新思考下一步操作。",
                    ]
                )
                return LoopAction.SKIP_TURN  # 请求主循环 continue
        else:
            self.session.prompt = f"用户中断了操作，用户补充信息为：{processed_input}"
            return LoopAction.SKIP_TURN  # 请求主循环 continue

    def _get_next_user_action(self) -> Union[str, "LoopAction"]:
        """获取用户下一步操作

        返回:
            LoopAction.CONTINUE 或 LoopAction.COMPLETE（兼容旧字符串值 "continue"/"complete"）
        """
        user_input = self._multiline_input(
            f"{self.name}: 请输入（Ctrl+C 结束当前任务）", False
        )

        if user_input:
            # 处理输入（包括 shell 命令等），让 input_handler 有机会处理
            processed_input = self._process_input(user_input)

            # 如果输入处理器返回了空字符串或标记需要返回，说明已经被处理（如 shell 命令）
            if not processed_input or self._last_handler_returned:
                # 输入已被处理器处理（如执行了 shell 命令），继续获取下一个输入
                return LoopAction.CONTINUE

            self.session.prompt = processed_input
            # 会话中途的新任务：强触发可能相关的规则并包进本条上下文
            self._hard_trigger_rules(ensure_str(processed_input))
            # 检测到重复响应时，在提示词末尾补充不要重复的提示
            if self._repeat_detected:
                self.session.prompt = join_prompts(
                    [
                        self.session.prompt,
                        "请不要复述之前的回答，请给出不同的回答。",
                    ]
                )
                self._repeat_detected = False
                self._repeat_escalation_level = 0
            # 使用显式动作信号，保留返回类型注释以保持兼容
            return LoopAction.CONTINUE
        else:
            return LoopAction.COMPLETE

    def _first_run(self) -> None:
        """首次运行初始化"""
        # 如果工具过多，使用AI进行筛选
        if self.session.prompt:
            self._filter_tools_if_needed(ensure_str(self.session.prompt))

        # 准备记忆标签提示
        memory_tags_prompt = self.memory_manager.prepare_memory_tags_prompt()

        # 极速模式下跳过文件上传、方法论加载和自动规则选择
        if not self.quick_mode:
            # 处理文件上传和方法论加载
            self.file_methodology_manager.handle_files_and_methodology()

            # 自动选择并加载规则（如果用户未指定规则且启用了自动规则选择）
            if self.session.prompt and self._enable_auto_rule_select:
                self.auto_select_and_load_rules(ensure_str(self.session.prompt))

        # 添加记忆标签提示
        if memory_tags_prompt:
            self.session.prompt = f"{self.session.prompt}{memory_tags_prompt}"

        # 标记首次运行初始化已执行（供首轮无工具调用检测使用）
        self._first_run_occurred = True
        self.first = False

    def _create_temp_model(
        self, system_prompt: str = "", force_model_type: Optional[str] = None
    ) -> BasePlatform:
        """创建一个用于执行一次性任务的临时模型实例（委托至 ModelSwitcher）"""
        return self._model_switcher.create_temp_model(
            system_prompt=system_prompt,
            force_model_type=force_model_type,
        )

    def _has_user_specified_rules(self) -> bool:
        """判断用户是否已指定规则

        用户指定规则的方式：
        1. 命令行参数 rule_names
        2. input 标记 '<rule:xxx>'

        返回:
            bool: 如果用户已指定规则（非默认规则），返回 True
        """
        from jarvis.jarvis_utils.config import get_default_rule_names
        from jarvis.jarvis_agent.builtin_input_handler import extract_tags_from_text

        # 默认规则（来自配置 default_rule_names，不视为用户指定）
        default_rules = set(get_default_rule_names())

        # 检查 loaded_rule_names 中是否有非默认规则
        for rule_name in self.loaded_rule_names:
            if rule_name not in default_rules:
                return True

        # 检查用户输入中是否包含 '<rule:xxx>' 标签
        if self.session.prompt:
            tags = extract_tags_from_text(self.session.prompt)
            if any(tag.startswith("rule:") for tag in tags):
                return True

        return False

    def auto_select_and_load_rules(self, task_description: str) -> None:
        """根据任务描述自动选择并加载规则（最多3个）

        参数:
            task_description: 任务描述字符串
        """
        try:
            # 如果用户已指定规则，跳过自动选择
            if self._has_user_specified_rules():
                PrettyOutput.auto_print("ℹ️  用户已指定规则，跳过自动规则选择")
                return

            # 调用规则匹配方法（支持本地+远程搜索）
            selected_rules = self.rules_manager.match_rules_to_task(task_description)

            # 如果成功选择了规则，将其激活
            if selected_rules:
                # 检查是否为"不需要规则"的标记
                if selected_rules == ["__NO_RULES_NEEDED__"]:
                    PrettyOutput.auto_print("✅ 任务简单，无需特定规则即可完成")
                    return

                # 遍历规则列表并激活
                for rule_name in selected_rules:
                    # 使用 load_rule 方法加载规则（内部会检查重复并自动合并）
                    if self.rules_manager.load_rule(rule_name):
                        # 打印时给出规则文件全路径，避免 Agent 误把「作用域:相对路径」
                        # 当作 load_rule 的 file_path 直接使用
                        rule_path = self.rules_manager.get_rule_file_path(rule_name)
                        display = (
                            rule_path if rule_path and rule_path != "--" else rule_name
                        )
                        PrettyOutput.auto_print(f"✅ 已根据任务自动选择规则: {display}")
                    else:
                        PrettyOutput.auto_print(f"ℹ️  规则已存在或激活失败: {rule_name}")
        except Exception as e:
            # 规则选择失败不影响主流程，静默处理
            PrettyOutput.auto_print(f"⚠️  自动选择规则失败: {e}")

    def _wrap_loaded_rules(self, text: str) -> str:
        """把当前已加载规则包成 <rules> 前缀（替换旧块），返回新文本。"""
        try:
            import re

            content = self.rules_manager.get_injectable_rules_content()
            if not content:
                return text
            block = f"<rules>\n{content}\n</rules>"
            cleaned = re.sub(r"<rules>.*?</rules>", "", text, flags=re.S).strip()
            return block + "\n\n" + cleaned
        except Exception:
            return text

    def _hard_trigger_rules(self, task: str) -> None:
        """强触发：新任务进入处理前用 cheap 判定并强制载入可能相关的规则。

        首次任务的自动选择已在 _first_run 完成；这里负责会话中途出现的新任务，
        保证规则/技能"≥1% 命中就载入"，并把已载规则包进本条任务上下文。
        """
        try:
            if getattr(self, "quick_mode", False) or not getattr(
                self, "_enable_auto_rule_select", False
            ):
                return
            if not task or len(task.strip()) < 40:
                return
            picked = self.rules_manager.match_task_cheap(task)
            if not picked:
                return
            newly = []
            for rule_name in picked:
                if rule_name in (self.loaded_rule_names or []):
                    continue
                if self.rules_manager.load_rule(rule_name):
                    newly.append(rule_name)
            if newly:
                PrettyOutput.auto_print("⚡ 强触发载入规则: " + ", ".join(newly))
                self.session.prompt = self._wrap_loaded_rules(
                    ensure_str(self.session.prompt or task)
                )
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️  强触发载入规则失败: {e}")

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
        tool_desc_by_name = {}
        for i, tool in enumerate(custom_tools, 1):
            tool_names.append(tool["name"])
            tool_desc_by_name[tool["name"]] = tool["description"]
            tools_prompt_part += f"{i}. {tool['name']}: {tool['description']}\n"

        selection_prompt = f"""
用户任务：
<task>
{task}
</task>

可用工具列表：
<tools>
{tools_prompt_part}
</tools>

请根据用户任务，从中选择最相关的工具。
只返回所选工具的编号，用逗号分隔。例如：1, 5, 12
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
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="_filter_tools_if_needed"
            )
            pass

        # 使用临时模型实例调用模型，以避免污染历史记录
        try:

            def _select_with_normal_model() -> str:
                """现有流程：用临时模型筛选工具编号。"""
                temp_model = self._create_temp_model("你是辅助筛选工具的助手。")
                return temp_model.chat_until_success(selection_prompt)

            # 优先用结构化评估模型做候选选择：它只接受 JSON 协议，
            # 无法消费自然语言提示词，故走 decide_choice 做协议转换。
            # 未配置评估模型或调用失败时，decide_choice 内部会回退到 lambda: None。
            picked_tools = decide_choice(
                task,
                {name: desc for name, desc in tool_desc_by_name.items()},
                lambda: None,
                max_select=len(tool_names),
            )
            if picked_tools:
                selected_tool_names = sorted(set(picked_tools))
            else:
                # 结构化评估模型未选出工具（未配置/失败/无匹配）时，走现有流程。
                # 注意：这里不能再用 decide()，因为 selection_prompt 是自然语言协议，
                # 结构化评估模型无法消费，只会白白失败一次。
                selected_tools_str = _select_with_normal_model()

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
                except Exception as e:
                    save_exception(
                        e,
                        module="jarvis_agent.__init__",
                        function="_filter_tools_if_needed",
                    )
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
                except Exception as e:
                    save_exception(
                        e,
                        module="jarvis_agent.__init__",
                        function="_filter_tools_if_needed",
                    )
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
            f"检测到你的'{scope_name}'记忆库包含 {len(memories)} 条记忆，"
            f"且有三条以上标签重叠的记忆。\n"
            f"是否立即整理记忆库以优化性能与相关性？"
        )
        if self.confirm_callback(prompt, False):
            PrettyOutput.auto_print(
                f"ℹ️ 正在开始整理 '{scope_name}' ({memory_type}) 记忆库..."
            )
            organizer.organize_memories(memory_type)
        else:
            PrettyOutput.auto_print(f"ℹ️ 已取消 '{scope_name}' 记忆库整理。")
