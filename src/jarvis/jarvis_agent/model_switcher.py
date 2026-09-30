# -*- coding: utf-8 -*-
"""模型/平台切换职责模块
从 Agent 类中抽离的「模型/平台切换」职责簇。
设计说明：
- 遵循 jarvis_agent 包既有拆分范式（如 MemoryManager(self)、HistoryCompressor(self)）：
  本模块持有 agent 引用，方法体内通过 self.agent.xxx 访问 Agent 的其它能力。
- Agent 侧保留同名薄委托方法，保证对外接口（含 run_loop / code_agent 的反向调用）完全不变。
- 循环依赖通过 TYPE_CHECKING 处理。
"""

from typing import TYPE_CHECKING
from typing import Callable
from typing import List
from typing import Optional
from typing import Union
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_agent import Agent


class ModelSwitcher:
    """模型/平台切换职责实现
    所有方法等价于原先 Agent 类上的同名方法，仅把 self.xxx 改为 self.agent.xxx。
    """

    def __init__(self, agent: "Agent") -> None:
        self.agent = agent

    def switch_model_by_difficulty(self, difficulty: str) -> None:
        """根据任务难度切换模型

        参数:
            difficulty: 任务难度等级（easy/medium/hard）
        """
        # 如果用户手动切换过模型，则禁用自动切换
        if getattr(self.agent, "_manual_model_switch", False):
            return

        # 难度到模型类型的映射：只做质量升级（hard->smart），不做廉价降级，
        # 避免难度误判把真实任务丢给 cheap 档模型而牺牲质量。
        difficulty_to_model_type = {
            "easy": "normal",
            "medium": "normal",
            "hard": "smart",
        }

        model_type = difficulty_to_model_type.get(difficulty, "normal")
        current_model_type = getattr(self.agent, "_model_type", "normal")

        # 如果模型类型没有变化，不需要切换
        if model_type == current_model_type:
            return

        # 延迟导入以避免循环依赖
        from jarvis.jarvis_agent.builtin_input_handler import switch_platform_type

        # 使用通用的 switch_platform_type 函数进行切换
        success = switch_platform_type(
            self.agent, model_type, preserve_model_group=True
        )

        if success:
            # 更新模型类型标记
            self.agent._model_type = model_type

            # 如果有系统提示词，设置到新模型
            if hasattr(self.agent, "system_prompt") and self.agent.system_prompt:
                # 使用 prompt_manager 重新构建系统提示词（包含方法论等）
                if hasattr(self.agent, "prompt_manager") and self.agent.prompt_manager:
                    prompt_text = self.agent.prompt_manager.build_system_prompt(
                        self.agent
                    )
                    self.agent.model.set_system_prompt(prompt_text)
                else:
                    self.agent.model.set_system_prompt(self.agent.system_prompt)

            # 输出切换信息
            model_type_display = {
                "cheap": "经济",
                "normal": "标准",
                "smart": "智能",
            }.get(model_type, model_type)
            PrettyOutput.auto_print(
                f"🔄 根据任务难度（{difficulty}）切换模型类型: {model_type_display} ({model_type})"
            )

        else:
            PrettyOutput.auto_print("⚠️ 模型切换失败，保持当前模型")

    def classify_and_switch_model(
        self,
        user_input: Union[str, List[ContentBlock]],
        classify_fn: Callable,
        get_prompt_fn: Callable,
    ) -> None:
        """执行需求分类、模型切换、采样温度适配和系统提示词更新的统一流程

        参数:
            user_input: 用户输入的需求描述
            classify_fn: 分类函数，签名为 (user_input) -> (scenario, difficulty, temperature)
            get_prompt_fn: 获取系统提示词函数，签名为 (scenario) -> str
        """
        try:
            scenario, difficulty, temperature = classify_fn(user_input)

            # 根据难度切换模型（可能重建 self.model）
            self.switch_model_by_difficulty(difficulty)

            # 按任务性质调整采样温度（须在可能的重建之后应用）
            self.apply_task_temperature(temperature)

            # 根据分类结果获取对应的系统提示词并更新
            scenario_system_prompt = get_prompt_fn(scenario)
            if scenario_system_prompt != self.agent.system_prompt:
                self.agent.system_prompt = scenario_system_prompt
                # 更新模型的系统提示词
                if self.agent.model:
                    # 使用 prompt_manager 重新构建系统提示词（包含方法论等）
                    if self.agent.prompt_manager:
                        prompt_text = self.agent.prompt_manager.build_system_prompt(
                            self.agent
                        )
                        self.agent.model.set_system_prompt(prompt_text)
                    else:
                        self.agent.model.set_system_prompt(self.agent.system_prompt)
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 需求分类失败: {e}，使用默认配置")

    def apply_task_temperature(self, temperature: Optional[float]) -> None:
        """按任务性质把推荐采样温度应用到当前模型（带范围保护）。

        温度只改当前 Agent 自己的平台实例（registry 每次新建），不影响其它 Agent。
        """
        try:
            model = getattr(self.agent, "model", None)
            if model is None:
                return
            if temperature is None:
                return
            # 尊重用户在 llm_config 里显式锁定的 temperature：显式配置优先于自动调整
            try:
                from jarvis.jarvis_utils.config import get_llm_config

                pinned = get_llm_config(getattr(model, "platform_type", "normal")).get(
                    "temperature"
                )
            except Exception:
                pinned = None
            if pinned is not None:
                return
            # 范围保护：拒绝明显异常的数值，避免把采样推到极端
            try:
                temp = float(temperature)
            except (TypeError, ValueError):
                return
            temp = min(max(temp, 0.1), 1.5)
            if not hasattr(model, "temperature"):
                return
            model.temperature = temp
            PrettyOutput.auto_print(f"🌡️ 按任务性质调整采样温度: {temp}")
        except Exception:
            # 温度调整失败不影响主流程
            pass

    def create_temp_model(
        self, system_prompt: str = "", force_model_type: Optional[str] = None
    ) -> BasePlatform:
        """创建一个用于执行一次性任务的临时模型实例，以避免污染主会话。

        默认使用与调用方相同的模型配置，也可以强制指定模型类型。

        参数:
            system_prompt: 系统提示词，可选。如果调用方会通过 set_messages 设置包含系统消息的对话历史，
                          则无需传入此参数（set_messages 会覆盖此处设置的系统提示词）。
            force_model_type: 强制使用的模型类型（smart/normal/cheap），可选。
                            如果指定，将使用该类型的模型而不是当前模型类型。
        """
        # 确定要使用的模型类型
        if force_model_type:
            # 使用强制指定的模型类型
            platform_registry = PlatformRegistry()
            if force_model_type == "smart":
                temp_model = platform_registry.get_smart_platform()
            elif force_model_type == "cheap":
                temp_model = platform_registry.get_cheap_platform()
            else:  # normal
                temp_model = platform_registry.get_normal_platform()
        else:
            # 使用与调用方相同的模型配置
            temp_model = PlatformRegistry().create_platform(
                self.agent.model.platform_type
            )

        if not temp_model:
            raise RuntimeError("创建临时模型失败。")

        if system_prompt:
            temp_model.set_system_prompt(system_prompt)
        temp_model.set_suppress_output(False)  # 关闭抑制输出，显示压缩过程
        return temp_model
