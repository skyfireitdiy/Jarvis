from abc import ABC, abstractmethod
import os
import os
from abc import ABC, abstractmethod

from jarvis.jarvis_agent import Agent as JarvisAgent
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry


class LLMInterface(ABC):
    """
    大型语言模型接口的抽象基类。

    该类定义了与远程LLM交互的标准接口。
    任何LLM提供商（如OpenAI、Anthropic等）都应作为该接口的子类来实现。
    """

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        根据给定的提示从LLM生成响应。

        参数:
            prompt: 发送给LLM的输入提示。
            **kwargs: LLM API调用的其他关键字参数
                      （例如，temperature, max_tokens）。

        返回:
            由LLM生成的文本响应。
        """
        pass


class ToolAgent_LLM(LLMInterface):
    """
    LLMInterface的一个实现，它使用一个能操作工具的JarvisAgent来生成最终响应。
    """

    def __init__(self):
        """
        初始化工具-代理 LLM 包装器。
        """
        print("🤖 已初始化工具 Agent 作为最终应答者。")
        self.allowed_tools = ["read_code", "execute_script"]
        # 为代理提供一个通用的系统提示
        self.system_prompt = "You are a helpful assistant. Please answer the user's question based on the provided context. You can use tools to find more information if needed."
        self.summary_prompt = """
<report>
请为本次问答任务生成一个总结报告，包含以下内容：

1. **原始问题**: 重述用户最开始提出的问题。
2. **关键信息来源**: 总结你是基于哪些关键信息或文件得出的结论。
3. **最终答案**: 给出最终的、精炼的回答。
</report>
"""

    def generate(self, prompt: str, **kwargs) -> str:
        """
        使用受限的工具集运行JarvisAgent以生成答案。

        参数:
            prompt: 要发送给代理的完整提示，包括上下文。
            **kwargs: 已忽略，为保持接口兼容性而保留。

        返回:
            由代理生成的最终答案。
        """
        try:
            # 使用RAG上下文的特定设置初始化代理
            agent = JarvisAgent(
                system_prompt=self.system_prompt,
                use_tools=self.allowed_tools,
                auto_complete=True,
                use_methodology=False,
                use_analysis=False,
                need_summary=True,
                summary_prompt=self.summary_prompt,
            )

            # 代理的run方法需要'user_input'参数
            final_answer = agent.run(user_input=prompt)
            return str(final_answer)

        except Exception as e:
            print(f"❌ Agent 在执行过程中发生错误: {e}")
            return "错误: Agent 未能成功生成回答。"


class JarvisPlatform_LLM(LLMInterface):
    """
    项目内部平台的LLMInterface实现。

    该类使用PlatformRegistry来获取配置的“普通”模型。
    """

    def __init__(self):
        """
        初始化Jarvis平台LLM客户端。
        """
        try:
            self.registry = PlatformRegistry.get_global_platform_registry()
            self.platform: BasePlatform = self.registry.get_normal_platform()
            self.platform.set_suppress_output(False)  # 确保模型没有控制台输出
            print(f"🚀 已初始化 Jarvis 平台 LLM，模型: {self.platform.name()}")
        except Exception as e:
            print(f"❌ 初始化 Jarvis 平台 LLM 失败: {e}")
            raise

    def generate(self, prompt: str, **kwargs) -> str:
        """
        向本地平台模型发送提示并返回响应。

        参数:
            prompt: 用户的提示。
            **kwargs: 已忽略，为保持接口兼容性而保留。

        返回:
            由平台模型生成的响应。
        """
        try:
            # 使用健壮的chat_until_success方法
            return self.platform.chat_until_success(prompt)
        except Exception as e:
            print(f"❌ 调用 Jarvis 平台模型时发生错误: {e}")
            return "错误: 无法从本地LLM获取响应。"
