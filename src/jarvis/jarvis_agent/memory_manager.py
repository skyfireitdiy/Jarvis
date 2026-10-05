# -*- coding: utf-8 -*-
"""
记忆管理器模块
负责处理Agent的记忆保存和检索功能
"""

from typing import Any

from jarvis.jarvis_agent.events import BEFORE_HISTORY_CLEAR
from jarvis.jarvis_agent.events import TASK_COMPLETED
from jarvis.jarvis_agent.events import TASK_STARTED
from jarvis.jarvis_utils.globals import get_all_memory_tags
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.exception_utils import save_exception


class MemoryManager:
    """记忆管理器，负责处理记忆相关的功能"""

    def __init__(self, agent: Any) -> None:
        """
        初始化记忆管理器

        参数:
            agent: Agent实例
        """
        self.agent = agent
        # 本轮任务是否已进行过记忆保存提示/处理的标记，用于事件去重
        self._memory_prompted = False
        # 订阅 Agent 事件（旁路集成，失败不影响主流程）
        try:
            self._subscribe_events()
        except Exception as e:
            save_exception(e, module="jarvis_agent.memory_manager", function="__init__")
            pass

    def prepare_memory_tags_prompt(self) -> str:
        """准备记忆标签提示"""
        memory_tags = get_all_memory_tags()
        memory_tags_prompt = ""

        # 检查是否有memory工具
        if self._has_memory_tool():
            memory_tags_prompt = "\n\n💡 提示：在分析任务之前，建议使用 memory 工具（action=save）将关键信息记录下来，便于后续检索和复用。"

        # 构建记忆标签列表
        if any(tags for tags in memory_tags.values()):
            memory_tags_prompt += self._format_memory_tags(memory_tags)

        return memory_tags_prompt

    def _has_memory_tool(self) -> bool:
        """检查是否有memory工具"""
        tool_registry = self.agent.get_tool_registry()
        if tool_registry:
            tool_names = [tool.name for tool in tool_registry.tools.values()]
            return "memory" in tool_names
        return False

    def prepare_memory_context_prompt(self, user_input: str) -> str:
        """主动检索与当前任务相关的历史记忆并注入上下文

        与 prepare_memory_tags_prompt 不同，此方法直接执行语义检索，
        将最相关的记忆内容注入到会话上下文中，而非仅列出标签让模型自行检索。

        参数:
            user_input: 当前任务的用户输入文本

        返回:
            str: 格式化后的相关记忆提示，无相关记忆时返回空字符串
        """
        if not user_input or not user_input.strip():
            return ""

        # 仅在存在记忆目录且有记忆文件时执行检索，避免无谓开销
        try:
            from pathlib import Path

            from jarvis.jarvis_utils.config import get_data_dir

            # 检查项目记忆目录和全局记忆目录是否存在
            project_dir = Path(".jarvis/memory")
            global_dir = Path(get_data_dir()) / "memory"
            if not project_dir.exists() and not global_dir.exists():
                return ""
        except Exception:
            return ""

        try:
            from jarvis.jarvis_memory_organizer.smart_retrieval import SmartRetriever

            retriever = SmartRetriever()
            memories = retriever.semantic_search(
                query=user_input,
                memory_types=["project_long_term", "global_long_term"],
                limit=5,
            )
            if not memories:
                return ""

            # 格式化检索结果
            prompt = "\n\n📚 基于当前任务自动检索到以下相关历史记忆（供参考）："
            for i, memory in enumerate(memories):
                content = (memory.content or "").strip()
                if not content:
                    continue
                # 限制单条记忆长度，避免撑爆上下文
                if len(content) > 500:
                    content = content[:500] + "..."
                tags_str = "/".join(memory.tags) if memory.tags else "无标签"
                prompt += f"\n\n[{i + 1}] ({memory.type} | {tags_str})\n{content}"

            return prompt
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.memory_manager",
                function="prepare_memory_context_prompt",
            )
            return ""

    def _format_memory_tags(self, memory_tags: dict[str, Any]) -> str:
        """格式化记忆标签"""
        prompt = "\n\n系统中存在以下记忆标签，你可以使用 memory 工具（action=retrieve）检索相关记忆："

        type_names = {
            "short_term": "短期记忆",
            "project_long_term": "项目长期记忆",
            "global_long_term": "全局长期记忆",
        }

        for memory_type, tags in memory_tags.items():
            if tags:
                type_name = type_names.get(memory_type, memory_type)
                prompt += f"\n- {type_name}: {', '.join(tags)}"

        return prompt

    def prompt_memory_save(self) -> None:
        """让大模型自动判断并保存值得记忆的信息"""
        # 检查是否有记忆相关工具
        tool_registry = self.agent.get_tool_registry()
        if not tool_registry:
            return

        tool_names = [tool.name for tool in tool_registry.tools.values()]
        if "memory" not in tool_names:
            return

        # 构建提示词，让大模型自己判断并保存记忆
        prompt = """回顾本次任务，判断是否有值得记忆的信息。使用 memory 工具（action=save）保存：
- global_long_term: 新方法/技巧、用户偏好、技术知识
- project_long_term: 项目发现/配置、实现细节/约定
如无值得记忆的信息，直接说明。"""

        # 处理记忆保存
        try:
            # 清空本轮执行标记，便于准确判断是否调用了 memory 工具
            try:
                self.agent.set_user_data("__last_executed_tool__", "")
                self.agent.set_user_data("__executed_tools__", [])
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.memory_manager",
                    function="prompt_memory_save",
                )
                pass

            if self.agent._native_active():
                # 原生：模型直接调用 memory 工具（内部原生循环执行），无需文本 JSON 解析
                self.agent._run_native_until_content(prompt)
            else:
                response = self.agent.model.chat_until_success(prompt)
                # 执行工具调用（如果有）
                need_return, result = self.agent._call_tools(response)

            # 根据实际执行的工具判断是否保存了记忆
            saved = False
            try:
                last_tool = self.agent.get_user_data("__last_executed_tool__")
                saved = last_tool == "memory"
            except Exception:
                saved = False

            if saved:
                PrettyOutput.auto_print("✅ 已自动保存有价值的信息到记忆系统")
            else:
                PrettyOutput.auto_print("ℹ️ 本次任务没有特别需要记忆的信息")

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 记忆分析失败: {str(e)}")
        finally:
            # 设置记忆提示完成标记，避免事件触发造成重复处理
            self._memory_prompted = True
            try:
                self.agent.set_user_data("__memory_save_prompted__", True)
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.memory_manager",
                    function="prompt_memory_save",
                )
                pass

    def add_memory_prompts_to_addon(self, addon_prompt: str, tool_registry: Any) -> str:
        """在附加提示中添加记忆相关提示"""
        memory_prompts = ""

        if tool_registry:
            tool_names = [tool.name for tool in tool_registry.tools.values()]

            # 如果有memory工具，添加相关提示（save 与 retrieve 各一行）
            if "memory" in tool_names:
                memory_prompts += (
                    "\n    - 有关键信息需要沉淀时，用 memory(action=save) 保存："
                    "project_long_term 存项目相关（架构决策、关键配置、实现约定），"
                    "global_long_term 存通用经验与用户偏好，short_term 存当前任务临时信息"
                )
                memory_prompts += "\n    - 需要过往上下文或方案时，用 memory(action=retrieve) 检索相关记忆"

        return memory_prompts

    # -----------------------
    # 事件订阅与处理（旁路）
    # -----------------------
    def _subscribe_events(self) -> None:
        bus = self.agent.get_event_bus()
        # 任务开始时重置去重标记
        bus.subscribe(TASK_STARTED, self._on_task_started)
        # 在清理历史前尝试保存记忆（若开启强制保存且尚未处理）
        bus.subscribe(BEFORE_HISTORY_CLEAR, self._ensure_memory_prompt)
        # 任务完成时作为兜底再尝试一次
        bus.subscribe(TASK_COMPLETED, self._ensure_memory_prompt)

    def _on_task_started(self, **payload: Any) -> None:
        self._memory_prompted = False
        try:
            self.agent.set_user_data("__memory_save_prompted__", False)
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.memory_manager", function="_on_task_started"
            )
            pass

    def _ensure_memory_prompt(self, **payload: Any) -> None:
        # 仅在开启强制保存记忆时启用
        if not getattr(self.agent, "force_save_memory", False):
            return
        # 避免在同一任务内重复提示/处理
        if self._memory_prompted:
            return
        try:
            already = bool(self.agent.get_user_data("__memory_save_prompted__"))
            if already:
                self._memory_prompted = True
                return
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.memory_manager",
                function="_ensure_memory_prompt",
            )
            pass
        # 静默执行保存逻辑，失败不影响主流程
        try:
            self.prompt_memory_save()
        except Exception:
            # 忽略异常，保持主流程稳定
            self._memory_prompted = True
