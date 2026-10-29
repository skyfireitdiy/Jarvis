# -*- coding: utf-8 -*-
"""model_chat 工具模块。

为插件作者提供「创建模型并直接对话」的能力：向已配置的 LLM 模型发起一次
**无状态**对话并拿到完整文本回复，无需自行封装 ``BasePlatform``/``PlatformRegistry``。

设计要点（对应 NLSpec .jarvis/.df/specs/model-chat.md）：
- 复用 ``jarvis.jarvis_platform.registry.PlatformRegistry`` 与
  ``jarvis.jarvis_platform.base.BasePlatform``，不重新实现 LLM 调用/鉴权/平台适配。
- 无状态：使用 ``BasePlatform.complete()``（每次调用前自动 ``delete_chat()`` 重置，
  且不触发 dialogue_recorder 副作用），不保留/不恢复会话上下文。
- 模型组可指定：``normal`` / ``cheap`` / ``smart`` / ``eval``，缺省 ``normal``。
- 输出抑制：调用期间 ``set_suppress_output(True)``，避免污染调用方输出。
- 错误语义显式：参数错误/平台创建失败/调用异常/空结果均返回 ``success: false``
  并附可读错误信息，不抛异常穿透。
"""

from typing import Any
from typing import Dict

from jarvis.jarvis_platform.registry import PlatformRegistry

# 合法模型组（对应 PlatformRegistry.create_platform 的 platform_type）
VALID_MODEL_GROUPS = ("normal", "cheap", "smart", "eval")
DEFAULT_MODEL_GROUP = "normal"


class ModelChatTool:
    """创建模型并直接对话（无状态）。

    插件作者可在自己的工具中调用：:

        model_chat({"model_group": "normal", "system_prompt": "...", "message": "..."})

    返回 ``{"success": true, "content": <模型回复>, "model_group": "normal"}``；
    失败时返回 ``{"success": false, "content": "", "error": <可读错误信息>}``。
    """

    name = "model_chat"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用。

        模型直聊工具始终可用（平台是否配置由调用时决定，未配置时返回错误）。
        """
        return True

    description = (
        "创建模型并直接对话（无状态）：向已配置的 LLM 模型发起一次无状态对话并返回完整文本回复。"
        "适用于插件作者在 tools/ 中直接调用，无需自行封装 BasePlatform/PlatformRegistry。"
        "参数：message(必填, 用户消息纯文本)、system_prompt(可选, 系统提示语)、"
        "model_group(可选, normal/cheap/smart/eval, 缺省 normal)。"
        "返回 {success, content, model_group}；失败时返回 {success:false, content:'', error}。"
        "不做流式/多模态/function calling/会话持久化。"
    )

    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "用户消息（纯文本）",
            },
            "system_prompt": {
                "type": "string",
                "description": "系统提示语，缺省不设置",
            },
            "model_group": {
                "type": "string",
                "enum": list(VALID_MODEL_GROUPS),
                "description": "模型组：normal/cheap/smart/eval，缺省 normal",
            },
        },
        "required": ["message"],
    }

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """执行一次无状态模型对话。

        参数:
            **kwargs: 包含 message / system_prompt / model_group 的关键字参数。

        返回:
            Dict[str, Any]: 统一返回结构
            ``{"success": bool, "content": str, "model_group": str}``，
            失败时额外含 ``error`` 字段。
        """
        # 1. 参数校验：message 必填且为字符串
        message = kwargs.get("message")
        if not isinstance(message, str) or not message.strip():
            return {
                "success": False,
                "content": "",
                "error": "message is required",
            }

        # 2. 参数校验：model_group 合法（缺省 normal）
        model_group = kwargs.get("model_group", DEFAULT_MODEL_GROUP)
        if model_group not in VALID_MODEL_GROUPS:
            return {
                "success": False,
                "content": "",
                "error": (
                    f"invalid model_group '{model_group}': "
                    f"must be one of {', '.join(VALID_MODEL_GROUPS)}"
                ),
            }

        # 3. 创建平台实例（复用现有模型层）
        try:
            platform = PlatformRegistry().create_platform(
                platform_type=model_group,
                silent=True,
            )
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "error": f"failed to create platform for model_group '{model_group}': {e}",
            }
        if platform is None:
            return {
                "success": False,
                "content": "",
                "error": (
                    f"platform for model_group '{model_group}' is unavailable, "
                    "please check the model configuration (e.g. API key)"
                ),
            }

        try:
            # 4. 输出抑制：避免污染调用方输出
            platform.set_suppress_output(True)

            # 5. 可选系统提示语
            system_prompt = kwargs.get("system_prompt")
            if system_prompt:
                platform.set_system_prompt(system_prompt)

            # 6. 无状态对话：complete() 每次调用前自动重置对话状态，
            #    且不触发 dialogue_recorder 副作用
            content = platform.complete(message)
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "error": f"model call failed: {e}",
            }

        # 7. 空结果判定
        if not content or not content.strip():
            return {
                "success": False,
                "content": "",
                "error": "model returned empty result",
            }

        return {
            "success": True,
            "content": content,
            "model_group": model_group,
        }
