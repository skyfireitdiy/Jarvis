# -*- coding: utf-8 -*-
"""
记忆管理器模块
负责处理Agent的记忆保存和检索功能
"""

from jarvis.jarvis_utils.globals import get_all_memory_tags
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class MemoryManager:
    """记忆管理器，负责处理记忆相关的功能"""

    def __init__(self, agent):
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
        except Exception:
            pass

    def prepare_memory_tags_prompt(self) -> str:
        """准备记忆标签提示"""
        memory_tags = get_all_memory_tags()
        memory_tags_prompt = ""

        # 检查是否有save_memory工具
        if self._has_save_memory_tool():
            memory_tags_prompt = "\n\n💡 提示：在分析任务之前，建议使用 save_memory 工具将关键信息记录下来，便于后续检索和复用。"

        # 构建记忆标签列表
        if any(tags for tags in memory_tags.values()):
            memory_tags_prompt += self._format_memory_tags(memory_tags)

        return memory_tags_prompt

    def _has_save_memory_tool(self) -> bool:
        """检查是否有save_memory工具"""
        tool_registry = self.agent.get_tool_registry()
        if tool_registry:
            tool_names = [tool.name for tool in tool_registry.tools.values()]
            return "save_memory" in tool_names
        return False

    def _format_memory_tags(self, memory_tags: dict) -> str:
        """格式化记忆标签"""
        prompt = (
            "\n\n系统中存在以下记忆标签，你可以使用 retrieve_memory 工具检索相关记忆："
        )

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

    def prompt_memory_save(self):
        """让大模型自动判断并保存值得记忆的信息"""
        # 检查是否有记忆相关工具
        tool_registry = self.agent.get_tool_registry()
        if not tool_registry:
            return

        tool_names = [tool.name for tool in tool_registry.tools.values()]
        if "save_memory" not in tool_names:
            return

        # 构建提示词，让大模型自己判断并保存记忆
        prompt = """请回顾本次任务的整个过程，判断是否有值得长期记忆或项目记忆的信息。

如果有以下类型的信息，请使用 save_memory 工具保存：
1. 解决问题的新方法或技巧（适合保存为 global_long_term）
2. 项目相关的重要发现或配置（适合保存为 project_long_term）
3. 用户的偏好或习惯（适合保存为 global_long_term）
4. 重要的技术知识或经验（适合保存为 global_long_term）
5. 项目特定的实现细节或约定（适合保存为 project_long_term）

请分析并保存有价值的信息，选择合适的记忆类型和标签。如果没有值得记忆的信息，请直接说明。"""

        # 处理记忆保存
        try:
            # 清空本轮执行标记，便于准确判断是否调用了 save_memory
            try:
                self.agent.set_user_data("__last_executed_tool__", "")
                self.agent.set_user_data("__executed_tools__", [])
            except Exception:
                pass

            response = self.agent.model.chat_until_success(prompt)  # type: ignore

            # 执行工具调用（如果有）
            need_return, result = self.agent._call_tools(response)

            # 根据实际执行的工具判断是否保存了记忆
            saved = False
            try:
                last_tool = self.agent.get_user_data("__last_executed_tool__")
                saved = last_tool == "save_memory"
            except Exception:
                saved = False

            if saved:
                PrettyOutput.print(
                    "已自动保存有价值的信息到记忆系统", OutputType.SUCCESS
                )
            else:
                PrettyOutput.print("本次任务没有特别需要记忆的信息", OutputType.INFO)

        except Exception as e:
            PrettyOutput.print(f"记忆分析失败: {str(e)}", OutputType.ERROR)
        finally:
            # 设置记忆提示完成标记，避免事件触发造成重复处理
            self._memory_prompted = True
            try:
                self.agent.set_user_data("__memory_save_prompted__", True)
            except Exception:
                pass

    def add_memory_prompts_to_addon(self, addon_prompt: str, tool_registry) -> str:
        """在附加提示中添加记忆相关提示"""
        memory_prompts = ""

        if tool_registry:
            tool_names = [tool.name for tool in tool_registry.tools.values()]

            # 如果有save_memory工具，添加相关提示
            if "save_memory" in tool_names:
                memory_prompts += (
                    "\n    - 如果有关键信息需要记忆，请调用save_memory工具进行记忆："
                )
                memory_prompts += "\n      * project_long_term: 保存与当前项目相关的长期信息（如：架构决策、关键配置、特定实现）"
                memory_prompts += "\n      * global_long_term: 保存通用的信息、用户喜好、知识、方法等（如：常用命令、个人偏好、解决方案）"
                memory_prompts += "\n      * short_term: 保存当前任务相关的临时信息（如：当前处理的文件、用户中间需求）"

            # 如果有retrieve_memory工具，添加相关提示
            if "retrieve_memory" in tool_names:
                memory_prompts += "\n    - 如果需要获取上下文或寻找解决方案，请调用retrieve_memory工具检索相关记忆"

        return memory_prompts

    # -----------------------
    # 事件订阅与处理（旁路）
    # -----------------------
    def _subscribe_events(self) -> None:
        bus = self.agent.get_event_bus()  # type: ignore[attr-defined]
        # 任务开始时重置去重标记
        bus.subscribe("task_started", self._on_task_started)
        # 在清理历史前尝试保存记忆（若开启强制保存且尚未处理）
        bus.subscribe("before_history_clear", self._ensure_memory_prompt)
        # 任务完成时作为兜底再尝试一次
        bus.subscribe("task_completed", self._ensure_memory_prompt)

    def _on_task_started(self, **payload) -> None:
        self._memory_prompted = False
        try:
            self.agent.set_user_data("__memory_save_prompted__", False)
        except Exception:
            pass

    def _ensure_memory_prompt(self, **payload) -> None:
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
        except Exception:
            pass
        # 静默执行保存逻辑，失败不影响主流程
        try:
            self.prompt_memory_save()
        except Exception:
            # 忽略异常，保持主流程稳定
            self._memory_prompted = True
