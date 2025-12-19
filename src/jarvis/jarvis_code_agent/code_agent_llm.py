"""CodeAgent LLM 询问模块"""

from typing import Any
from typing import Dict

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Optional

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.globals import get_global_model_group


class LLMManager:
    """LLM 询问管理器"""

    def __init__(
        self, parent_model: Optional[Any] = None, model_group: Optional[str] = None
    ):
        """初始化LLM管理器

        Args:
            parent_model: 父Agent的模型实例（已废弃，保留参数兼容性）
            model_group: 模型组名称，如果提供则优先使用，否则使用全局模型组
        """
        # 保存配置信息，用于后续创建 LLM 实例
        self._platform_name = None
        self._model_name = None
        # 优先使用传入的model_group，否则使用全局模型组
        self._model_group = model_group or get_global_model_group()

        # 根据 model_group 获取配置（不再从 parent_model 继承）
        # 使用普通模型，LLM询问可以降低成本
        if self._model_group:
            try:
                self._platform_name = get_normal_platform_name(self._model_group)
                self._model_name = get_normal_model_name(self._model_group)
            except Exception:
                # 如果从 model_group 解析失败，回退到从 parent_model 获取的值
                pass

        # 如果仍未获取到，使用默认配置
        if not self._platform_name:
            self._platform_name = get_normal_platform_name(None)
        if not self._model_name:
            self._model_name = get_normal_model_name(None)

    def _create_llm_model(self) -> BasePlatform:
        """创建新的 LLM 模型实例

        每次调用都创建新的实例，避免上下文窗口累积。

        Returns:
            LLM 模型实例

        Raises:
            ValueError: 如果无法创建LLM模型
        """
        try:
            registry = PlatformRegistry.get_global_platform_registry()

            # 创建平台实例
            # 直接使用 get_normal_platform，避免先调用 create_platform 再回退导致的重复错误信息
            # get_normal_platform 内部会处理配置获取和平台创建
            llm_model = registry.get_normal_platform(self._model_group)

            if not llm_model:
                raise ValueError("无法创建LLM模型实例")

            # 先设置模型组（如果从父Agent获取到），因为 model_group 可能会影响模型名称的解析
            if self._model_group:
                try:
                    llm_model.set_model_group(self._model_group)
                except Exception:
                    pass

            # 然后设置模型名称（如果从父Agent或model_group获取到）
            if self._model_name:
                try:
                    llm_model.set_model_name(self._model_name)
                except Exception:
                    pass

            # 设置抑制输出，因为这是后台任务
            llm_model.set_suppress_output(True)

            return llm_model
        except Exception as e:
            raise ValueError(f"无法创建LLM模型: {e}")

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

        try:
            PrettyOutput.auto_print("🤖 正在询问大模型判断大量代码删除是否合理...")
            # 每次调用都创建新的 LLM 实例，避免上下文窗口累积
            llm_model = self._create_llm_model()
            response = llm_model.chat_until_success(prompt)

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
