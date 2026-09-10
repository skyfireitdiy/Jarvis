# -*- coding: utf-8 -*-
import json
import logging
import os
import re
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
from typing import cast

from openai import OpenAI

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.native_tools import sanitize_message, to_openai_messages
from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ot, ct
import jarvis.jarvis_utils.globals as jglobals

# 配置日志
logger = logging.getLogger(__name__)

# 模型返回的 tool_calls.arguments 不是合法 JSON 时（截断、夹带文本等），
# 用它作为键把原始字符串传给工具层，由工具层给出可自我纠正的提示。
PARSE_ERROR_KEY = "__argument_parse_error__"


def _accumulate_openai_stream(
    stream: Any,
) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
    """累积 OpenAI 流式响应，返回 (content, tool_calls)。

    tool_calls 为规范格式 [{"id","name","arguments": <dict>}]；无工具调用时为 None。
    按 delta.tool_calls 的 index 归并 id/name/arguments 片段。
    """
    content_parts: List[str] = []
    tool_calls_acc: Dict[int, Dict[str, str]] = {}
    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        content_piece = getattr(delta, "content", None)
        if content_piece:
            content_parts.append(content_piece)
        for tc in getattr(delta, "tool_calls", None) or []:
            idx = getattr(tc, "index", 0) or 0
            entry = tool_calls_acc.setdefault(
                idx, {"id": "", "name": "", "arguments": ""}
            )
            if getattr(tc, "id", None):
                entry["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if getattr(fn, "name", None):
                    entry["name"] = fn.name
                if getattr(fn, "arguments", None):
                    entry["arguments"] += fn.arguments or ""

    content = "".join(content_parts)
    tool_calls: List[Dict[str, Any]] = []
    for idx in sorted(tool_calls_acc.keys()):
        e = tool_calls_acc[idx]
        raw_args = e.get("arguments", "")
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except Exception:
            # 参数不是合法 JSON（截断/夹带文本等），保留原文供工具层给出可自我纠正的提示
            args = {PARSE_ERROR_KEY: raw_args}
        tool_calls.append(
            {"id": e.get("id", ""), "name": e.get("name", ""), "arguments": args}
        )
    return (content or None), (tool_calls or None)


class OpenAIModel(BasePlatform):
    def __init__(
        self,
        platform_type: str = "normal",
        agent: Optional[Any] = None,
    ):
        """
        Initialize OpenAI model

        参数:
            platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'
        """
        super().__init__(platform_type=platform_type, agent=agent)
        self.system_message = ""
        self.extra_headers: Dict[str, str] = {}  # 初始化额外请求头
        llm_config = self._llm_config or {}

        # 如果传入了 llm_config（非空字典），优先从 llm_config 读取，避免环境变量污染
        # 只有在 llm_config 中没有对应键时才从环境变量读取（向后兼容）
        # 注意：如果 llm_config 中某个键存在但值为 None 或空字符串，也使用该值，不从环境变量读取
        if llm_config:
            # 传入了 llm_config，优先使用 llm_config 中的值
            # 使用 get() 方法，如果键不存在返回 None，然后才从环境变量读取
            # 但是，如果 llm_config 是空字典 {}，说明是显式传入的空配置，应该从环境变量读取
            # 如果 llm_config 中有键但值为 None，也应该使用 None，不从环境变量读取
            if "openai_api_key" in llm_config:
                # 键存在，使用 llm_config 中的值（即使为 None 或空字符串）
                self.api_key = llm_config.get("openai_api_key")
            else:
                # 键不存在，从环境变量读取（向后兼容）
                self.api_key = os.getenv("OPENAI_API_KEY")

            if "openai_api_base" in llm_config:
                # 键存在，使用 llm_config 中的值（即使为 None 或空字符串）
                self.base_url = llm_config.get("openai_api_base")
            else:
                # 键不存在，从环境变量读取（向后兼容）
                self.base_url = os.getenv(
                    "OPENAI_API_BASE", "https://api.openai.com/v1"
                )
        else:
            # 没有传入 llm_config，从环境变量读取（向后兼容）
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

        # Normalize api_key to api_keys list for round-robin support
        # Support: single string, comma-separated string, or list
        if isinstance(self.api_key, list):
            self.api_keys = self.api_key
        elif isinstance(self.api_key, str) and self.api_key:
            # Support comma-separated keys in string format
            self.api_keys = [k.strip() for k in self.api_key.split(",") if k.strip()]
        else:
            self.api_keys = [self.api_key] if self.api_key else []
        # Set current api_key to the first one for backward compatibility
        if self.api_keys:
            self.api_key = self.api_keys[0]
        self._api_key_index = 0

        # 如果设置了代理节点，将 base_url 转为 Gateway 代理 URL
        if jglobals.proxy_node and jglobals.master_url:
            # 将 base_url 拼接为代理格式
            # 注意：需要添加 /api/node/{node_id}/ 前缀以匹配 FastAPI 路由
            self.base_url = f"{jglobals.master_url}/api/node/{jglobals.proxy_node}/http_proxy/{self.base_url}"
            # 注意：X-Jarvis-Token 不在此处静态缓存，改为每次 API 调用时
            # 通过 _get_proxy_extra_headers() 动态注入，避免主网关重启后 Token 失效

        # 只有当 llm_config 不为空但其中没有 openai_api_key，且环境变量也没有设置时，才打印警告
        # 如果 llm_config 为空字典，说明可能是配置还未加载完成，不打印警告（避免第一轮误报）
        if not self.api_key and llm_config:
            PrettyOutput.auto_print(
                "⚠️ 未找到 OpenAI API Key，请在 llm_config 中设置 openai_api_key 或设置 OPENAI_API_KEY 环境变量"
            )
        # model_name 已在基类 BasePlatform.__init__ 中根据 platform_type 设置

        # Optional: Inject extra HTTP headers via llm_config or environment variable
        # Expected format: openai_extra_headers='{"Header-Name": "value", "X-Trace": "abc"}'
        headers_value = llm_config.get("openai_extra_headers")
        if headers_value is None:
            headers_str = os.getenv("OPENAI_EXTRA_HEADERS")
        else:
            headers_str = (
                headers_value
                if isinstance(headers_value, str)
                else json.dumps(headers_value)
            )

        # 注意：不要重新初始化 self.extra_headers，保留之前代理模式下设置的头
        # self.extra_headers: Dict[str, str] = {}  # 已移除这行
        if headers_str:
            try:
                parsed = (
                    json.loads(headers_str)
                    if isinstance(headers_str, str)
                    else headers_str
                )
                if isinstance(parsed, dict):
                    # Ensure all header keys/values are strings
                    self.extra_headers = {str(k): str(v) for k, v in parsed.items()}
                else:
                    PrettyOutput.auto_print(
                        "⚠️ openai_extra_headers 格式错误，应为 JSON 字符串"
                    )
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 解析 openai_extra_headers 失败: {e}")
        # 默认添加浏览器 User-Agent，避免被某些 API 网关拦截
        if "User-Agent" not in self.extra_headers:
            # 检测是否为 Kimi API，如果是则使用特定的 User-Agent
            if self.base_url and "https://api.kimi.com" in self.base_url:
                self.extra_headers["User-Agent"] = "KimiCLI/1.6"
            else:
                self.extra_headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )

        # Optional: Set reasoning effort for o1 series models via llm_config or environment variable
        # Expected format: openai_reasoning_effort="low" or "medium" or "high" or "xhigh"
        reasoning_effort_value = llm_config.get("openai_reasoning_effort")
        if reasoning_effort_value is None:
            reasoning_effort_value = os.getenv("OPENAI_REASONING_EFFORT")

        self.reasoning_effort: Optional[str] = (
            reasoning_effort_value if reasoning_effort_value else None
        )

        # Optional: Set extra_body for additional API parameters via llm_config
        # Expected format: openai_extra_body='{"key": "value"}' or dict
        extra_body_value = llm_config.get("openai_extra_body")
        if extra_body_value is None:
            extra_body_str = os.getenv("OPENAI_EXTRA_BODY")
        else:
            extra_body_str = (
                extra_body_value
                if isinstance(extra_body_value, str)
                else json.dumps(extra_body_value)
            )

        self.extra_body: Optional[Dict[str, Any]] = None
        if extra_body_str:
            try:
                parsed = (
                    json.loads(extra_body_str)
                    if isinstance(extra_body_str, str)
                    else extra_body_str
                )
                if isinstance(parsed, dict):
                    self.extra_body = parsed
                else:
                    PrettyOutput.auto_print("⚠️ openai_proxy 格式错误，应为字符串")
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 设置 OpenAI 代理失败: {e}")
        # 采样参数：可在 llm_config（temperature/top_p/max_tokens）中覆盖。
        # 默认 temperature=0.7（温和、不贪心，避免过低温度导致大段重复）；
        # top_p 默认 None 不发送（即服务端默认 1.0），避免温度+top_p 双重收窄。
        # 任一字段为 None 表示请求时不携带。
        self.temperature: Optional[float] = llm_config.get("temperature", 0.7)
        self.top_p: Optional[float] = llm_config.get("top_p")
        _mt = llm_config.get("max_tokens")
        self.max_tokens: Optional[int] = _mt if _mt not in (None, "") else None

        # Initialize OpenAI client, try to pass default headers if SDK supports it
        from jarvis.jarvis_utils.config import get_request_timeout

        _req_timeout = get_request_timeout()

        def _build_client(**overrides: Any) -> OpenAI:
            # 用 Dict[str, Any] 承载可选参数，避免类型检查器对 **kwargs 展开的误报
            params: Dict[str, Any] = {
                "api_key": self.api_key,
                "base_url": self.base_url,
            }
            if _req_timeout is not None:
                params["timeout"] = _req_timeout
            params.update(overrides)
            return OpenAI(**params)

        try:
            if self.extra_headers:
                self.client = _build_client(default_headers=self.extra_headers)
            else:
                self.client = _build_client()
        except TypeError:
            # Fallback: SDK version may not support default_headers
            self.client = _build_client()
            if self.extra_headers:
                PrettyOutput.auto_print(
                    "⚠️ 当前 OpenAI SDK 版本不支持 default_headers，已忽略 extra_headers"
                )
        self.messages: List[Dict[str, Any]] = []
        self.system_message = ""
        self._streaming_disabled: Optional[bool] = None

    def _get_next_api_key(self) -> Optional[str]:
        """Get next API key using round-robin rotation.

        Returns the next key in the api_keys list, advancing the index.
        If only one key is available, returns that key without rotation.
        If no keys are available, returns None.
        """
        if not self.api_keys:
            return None
        if len(self.api_keys) == 1:
            return self.api_keys[0]
        # Round-robin: get next key and advance index
        key = self.api_keys[self._api_key_index]
        self._api_key_index = (self._api_key_index + 1) % len(self.api_keys)
        return key

    def set_messages(self, messages: List[Dict[str, Any]]) -> None:
        """替换对话历史

        参数:
            messages: 新的对话历史列表，每个元素包含 role 和 content

        注意:
            - 会根据 messages 重新计算 conversation_turn（统计非 system 消息中的 user 消息数量）
            - 如果消息列表包含系统消息，会同时更新 system_message 属性
        """
        self.messages = messages

        # 如果消息列表包含系统消息，更新 system_message 属性
        for msg in messages:
            if msg.get("role") == "system":
                self.system_message = msg.get("content", "")
                break

        # 计算 conversation_turn：统计非 system 消息中的 user 消息数量
        non_system_messages = [msg for msg in messages if msg.get("role") != "system"]
        self._conversation_turn = sum(
            1 for msg in non_system_messages if msg.get("role") == "user"
        )

    def get_messages(self) -> List[Dict[str, Any]]:
        """获取对话历史

        返回:
            List[Dict[str, Any]]: 对话历史列表，每个元素包含 role 和 content
        """
        return self.messages

    def _filter_think_tags(self, content: str) -> str:
        """过滤 think 标签内容

        参数:
            content: 原始内容

        返回:
            str: 过滤后的内容
        """
        # 过滤 <think> 标签
        content = re.sub(
            ot("think") + r".*?" + ct("think"), "", content, flags=re.DOTALL
        )
        # 过滤 <thinking> 标签
        content = re.sub(
            ot("thinking") + r".*?" + ct("thinking"), "", content, flags=re.DOTALL
        )
        return content

    def get_model_list(self) -> List[Tuple[str, str]]:
        """
        获取可用的OpenAI模型列表

        返回:
            List[Tuple[str, str]]: 模型ID和名称的元组列表

        异常:
            当API调用失败时会打印错误信息并返回空列表
        """
        try:
            proxy_headers = self._get_proxy_extra_headers()
            models = (
                self.client.models.list(extra_headers=proxy_headers)
                if proxy_headers
                else self.client.models.list()
            )
            model_list = []
            for model in models:
                model_list.append((model.id, model.id))
            return model_list
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 获取模型列表失败：{str(e)}")
            return []

    def set_model_name(self, model_name: str):
        """
        设置当前使用的模型名称

        参数:
            model_name: 要设置的模型名称
        """

        self.model_name = model_name

    def set_system_prompt(self, message: str):
        """
        设置系统消息(角色设定)

        参数:
            message: 系统消息内容

        说明:
            设置后会立即添加到消息历史中
        """
        self.messages = []
        self.system_message = message
        self.messages.append({"role": "system", "content": self.system_message})

    def chat(
        self, message: Union[str, List[ContentBlock]]
    ) -> Generator[Tuple[str, str], None, None]:
        """
        执行对话并返回生成器

        参数:
            message: 用户输入的消息内容，支持纯文本(str)或多模态内容(List[ContentBlock])

        返回:
            Generator[Tuple[str, str], None, None]: 生成器，逐块返回AI响应内容

        异常:
            当API调用失败时会抛出异常并打印错误信息
        """
        # 记录添加用户消息前的消息列表长度，用于失败时回滚
        messages_before_user = len(self.messages)

        # Rotate API key for round-robin support
        next_key = self._get_next_api_key()
        if next_key:
            self.api_key = next_key
            self.client.api_key = next_key

        try:
            # 处理多模态消息
            if isinstance(message, str):
                user_message_content = message
            else:
                # 检查多模态支持，如果不支持则降级为纯文本
                if not self.supports_multimodal():
                    from jarvis.jarvis_utils.output import PrettyOutput

                    PrettyOutput.auto_print(
                        "⚠️ 当前模型不支持多模态输入，已自动降级为纯文本模式"
                    )
                    # 只保留文本内容
                    text_parts = [
                        block["text"] for block in message if block["type"] == "text"
                    ]
                    user_message_content = (
                        "\n".join(text_parts) if text_parts else "[多模态内容已跳过]"
                    )
                else:
                    # 将 List[ContentBlock] 转换为 OpenAI API 期望的格式
                    user_message_content = []
                    for block in message:
                        if block["type"] == "text":
                            user_message_content.append(
                                {"type": "text", "text": block["text"]}
                            )
                        elif block["type"] == "image_url":
                            # OpenAI API 期望 image_url 是一个对象，包含 url 字段
                            image_url_data = block["image_url"]
                            if isinstance(image_url_data, str):
                                image_url_data = {"url": image_url_data}
                            user_message_content.append(
                                {"type": "image_url", "image_url": image_url_data}
                            )
                    else:
                        # 未知类型，忽略或报错
                        pass

            # 清理孤立代理字符：当前用户消息可能来自 eval_js 等前端回传，
            # 若含孤立代理会在 httpx 编码请求体时抛 UnicodeEncodeError。
            self.messages.append(
                sanitize_message({"role": "user", "content": user_message_content})
            )

            # 循环处理，直到不是因为长度限制而结束
            # 构造 API 调用参数
            # 用规范消息序列化发送，保证历史中出现 role=tool/tool_calls 时也能正确表达
            use_streaming = not self._streaming_disabled
            api_params: Dict[str, Any] = {
                "model": self.model_name,
                "messages": to_openai_messages(self.messages),
                "stream": use_streaming,
            }
            _temperature = getattr(self, "temperature", 0.7)
            _top_p = getattr(self, "top_p", None)
            _max_tokens = getattr(self, "max_tokens", None)
            if _temperature is not None:
                api_params["temperature"] = _temperature
            if _top_p is not None:
                api_params["top_p"] = _top_p
            if _max_tokens is not None:
                api_params["max_tokens"] = _max_tokens
            # 只有在配置了 reasoning_effort 时才添加 reasoning_effort 参数
            if self.reasoning_effort:
                api_params["reasoning_effort"] = self.reasoning_effort

            # 只有在配置了 extra_body 时才添加 extra_body 参数
            if self.extra_body:
                api_params["extra_body"] = self.extra_body

            # 如果没有指定 max_tokens，不设置默认值，让模型使用自身的默认值

            # 动态注入代理认证头，确保主网关重启后 Token 更新生效
            proxy_headers = self._get_proxy_extra_headers()
            if proxy_headers:
                api_params["extra_headers"] = proxy_headers
            response = self.client.chat.completions.create(**api_params)

            full_response = ""
            full_reasoning = ""

            if use_streaming:
                # 流式模式：迭代 chunk 增量输出
                for chunk in response:
                    # 使用类型注解明确chunk的类型，避免union类型错误
                    from openai.types.chat import ChatCompletionChunk

                    chunk_typed: ChatCompletionChunk = cast(ChatCompletionChunk, chunk)
                    if chunk_typed.choices and len(chunk_typed.choices) > 0:
                        choice = chunk_typed.choices[0]

                        # 获取内容增量
                        if choice.delta:
                            # 处理 reasoning_content（推理过程，如 GLM 模型）
                            if (
                                hasattr(choice.delta, "reasoning_content")
                                and choice.delta.reasoning_content
                            ):
                                text: str = str(choice.delta.reasoning_content)
                                full_reasoning = full_reasoning + text
                                yield ("reason", text)
                            # 处理 content（正文内容）
                            if choice.delta.content:
                                text: str = str(choice.delta.content)
                                full_response = full_response + text
                                yield ("content", text)
                if full_response:
                    # 曾经成功过，说明流式请求是可以的
                    self._streaming_disabled = False
                    assistant_message = {"role": "assistant", "content": full_response}
                    if full_reasoning:
                        assistant_message["reasoning_content"] = full_reasoning
                    self.messages.append(assistant_message)
                else:
                    # 未设置的状态才设置为True
                    if self._streaming_disabled is None:
                        self._streaming_disabled = True
                    fallback_params = api_params.copy()
                    fallback_params["stream"] = False
                    fallback_headers = self._get_proxy_extra_headers()
                    if fallback_headers:
                        fallback_params["extra_headers"] = fallback_headers
                    fallback_response = self.client.chat.completions.create(
                        **fallback_params
                    )
                    if fallback_response.choices and len(fallback_response.choices) > 0:
                        fallback_message = fallback_response.choices[0].message
                        fallback_reasoning = (
                            getattr(fallback_message, "reasoning_content", None) or ""
                        )
                        fallback_text = fallback_message.content or ""
                        fallback_content = fallback_text
                        if fallback_content:
                            assistant_message = {
                                "role": "assistant",
                                "content": fallback_content,
                            }
                            if fallback_reasoning:
                                assistant_message["reasoning_content"] = (
                                    fallback_reasoning
                                )
                            self.messages.append(assistant_message)
                            yield ("content", fallback_content)
                            return
                    raise Exception("No response from model")
            else:
                # 非流式模式：直接获取完整响应
                if response.choices and len(response.choices) > 0:
                    response_message = response.choices[0].message
                    # 处理 reasoning_content（推理过程，如 GLM 模型）
                    reasoning = (
                        getattr(response_message, "reasoning_content", None) or ""
                    )
                    content = response_message.content or ""
                    full_response = content
                    full_reasoning = reasoning
                if full_response:
                    assistant_message = {"role": "assistant", "content": full_response}
                    if full_reasoning:
                        assistant_message["reasoning_content"] = full_reasoning
                    self.messages.append(assistant_message)
                    yield ("content", full_response)
                else:
                    raise Exception("No response from model")
        except Exception as e:
            # 失败时回滚：移除已添加的用户消息
            if len(self.messages) > messages_before_user:
                self.messages = self.messages[:messages_before_user]
            raise Exception(f"Chat failed: {str(e)}")

    def supports_native_tool_calls(self) -> bool:
        return True

    def chat_native_once(
        self,
        message: Optional[Union[str, List[ContentBlock]]],
        tools: List[Dict[str, Any]],
        append_user: bool = True,
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """流式执行一次带原生 tools 的对话。

        返回 (content, tool_calls)：
        - content：assistant 的文本（可能为 None）
        - tool_calls：规范格式 [{"id","name","arguments": <dict>}]；无工具调用时为 None

        调用成功会以规范消息追加 assistant 消息（含 tool_calls）进历史。
        若端点不支持 tools，会降级为纯文本并置 _native_disabled，之后本实例不再尝试。
        """
        # 已经降级或未启用原生能力，走纯文本
        if self._native_disabled or not tools:
            content, _ = self._native_fallback_text(message, append_user)
            return content, None

        # 追加用户消息（工具后续轮 append_user=False，避免重复加空消息）
        # 同时清理孤立代理字符，避免 httpx 编码请求体时抛 UnicodeEncodeError
        if append_user and message:
            self.messages.append(sanitize_message({"role": "user", "content": message}))
        next_key = self._get_next_api_key()
        if next_key:
            self.api_key = next_key
            self.client.api_key = next_key

        proxy_headers = self._get_proxy_extra_headers()
        api_params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": to_openai_messages(self.messages),
            "stream": True,
            "tools": tools,
        }
        _temperature = getattr(self, "temperature", 0.7)
        _top_p = getattr(self, "top_p", None)
        _max_tokens = getattr(self, "max_tokens", None)
        if _temperature is not None:
            api_params["temperature"] = _temperature
        if _top_p is not None:
            api_params["top_p"] = _top_p
        if _max_tokens is not None:
            api_params["max_tokens"] = _max_tokens
        if self.reasoning_effort:
            api_params["reasoning_effort"] = self.reasoning_effort
        if self.extra_body:
            api_params["extra_body"] = self.extra_body
        if proxy_headers:
            api_params["extra_headers"] = proxy_headers

        # 复用文本协议路径的流式渲染管线（pretty/simple/suppressed 三模式）
        import time
        from jarvis.jarvis_utils.config import get_pretty_output
        from jarvis.jarvis_utils.globals import get_interrupt

        # 工具续轮 message 可能为 None，渲染层需要非 None 的展示消息（中断时保存历史用）
        render_message: Union[str, List[ContentBlock]] = (
            message if message is not None else ""
        )

        # 重试循环：渲染管线检测到输出陷入重复（返回空 content 且无 tool_calls）时重试，
        # 与文本协议路径 chat_until_success 的 while_true 重试机制对齐。
        max_retries = 6
        for attempt in range(max_retries):
            # 与文本协议路径 while_true/while_success 对齐：每轮开始前检查中断信号，
            # 用户点击“人工介入”后立即停止重试，避免继续空转重试。
            if get_interrupt() > 0:
                break
            try:
                response = self.client.chat.completions.create(**api_params)

                # 累积器：content 逐块 yield 供流式渲染，tool_calls 分片按 index 归并
                content_parts: List[str] = []
                tool_calls_acc: Dict[int, Dict[str, str]] = {}

                def _gen() -> Generator[Tuple[str, str], None, None]:
                    for chunk in response:
                        if not getattr(chunk, "choices", None):
                            continue
                        delta = chunk.choices[0].delta
                        if delta is None:
                            continue
                        piece = getattr(delta, "content", None)
                        if piece:
                            content_parts.append(piece)
                            yield ("content", piece)
                        for tc in getattr(delta, "tool_calls", None) or []:
                            idx = getattr(tc, "index", 0) or 0
                            entry = tool_calls_acc.setdefault(
                                idx, {"id": "", "name": "", "arguments": ""}
                            )
                            if getattr(tc, "id", None):
                                entry["id"] = tc.id
                            fn = getattr(tc, "function", None)
                            if fn is not None:
                                if getattr(fn, "name", None):
                                    entry["name"] = fn.name
                                if getattr(fn, "arguments", None):
                                    entry["arguments"] += fn.arguments or ""

                start_time = time.time()
                if not self.suppress_output:
                    if get_pretty_output():
                        content, _reasoning, _ft = self._chat_with_pretty_output(
                            render_message, start_time, chat_iterator=_gen()
                        )
                    else:
                        content, _reasoning, _ft = self._chat_with_simple_output(
                            render_message, start_time, chat_iterator=_gen()
                        )
                else:
                    content, _reasoning = self._chat_with_suppressed_output(
                        render_message, chat_iterator=_gen()
                    )

                # 从累积的 tool_calls 分片解析规范格式
                tool_calls: List[Dict[str, Any]] = []
                for idx in sorted(tool_calls_acc.keys()):
                    e = tool_calls_acc[idx]
                    raw_args = e.get("arguments", "")
                    try:
                        args = json.loads(raw_args) if raw_args.strip() else {}
                    except Exception:
                        # 参数不是合法 JSON（截断/夹带文本等），保留原文供工具层给出可自我纠正的提示
                        args = {PARSE_ERROR_KEY: raw_args}
                    tool_calls.append(
                        {
                            "id": e.get("id", ""),
                            "name": e.get("name", ""),
                            "arguments": args,
                        }
                    )

                # 渲染管线检测到输出陷入重复时返回空 content；若同时无 tool_calls，
                # 判定为重复导致空输出，回滚本轮并重试（与文本协议路径一致）。
                if not content and not tool_calls:
                    if attempt < max_retries - 1:
                        sleep_time = 2**attempt
                        PrettyOutput.auto_print(
                            f"⚠️ 模型输出为空或陷入重复，重试中 ({attempt + 1}/{max_retries})，等待 {sleep_time}s..."
                        )
                        # 分段睡眠以便及时响应中断信号
                        for _ in range(sleep_time):
                            if get_interrupt() > 0:
                                break
                            time.sleep(1)
                        if get_interrupt() > 0:
                            break
                        continue
                    # 重试耗尽仍未获得有效输出，跳出循环统一回滚
                    break

                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": content,
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                self.messages.append(assistant_msg)
                # 与文本协议 _chat 对齐：打印模型响应统计信息（含工具调用 token）
                if not self.suppress_output:
                    self._print_response_stats(
                        content or "",
                        _reasoning or "",
                        _ft,
                        start_time,
                        tool_calls=tool_calls or None,
                    )
                return (content or None), (tool_calls or None)
            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ 原生工具调用不可用（{str(e)}），本模型将回退纯文本协议"
                )
                self._native_disabled = True
                # 回滚本轮已追加的用户消息，交给纯文本路径重新处理
                if (
                    append_user
                    and message
                    and self.messages
                    and self.messages[-1].get("role") == "user"
                ):
                    self.messages.pop()
                content, _ = self._native_fallback_text(message, append_user)
                return content, None

        # 重试耗尽仍未获得有效输出，回滚用户消息并返回空
        if (
            append_user
            and message
            and self.messages
            and self.messages[-1].get("role") == "user"
        ):
            self.messages.pop()
        return None, None

    def _native_fallback_text(
        self,
        message: Optional[Union[str, List[ContentBlock]]],
        append_user: bool,
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """原生失败后的纯文本回退：复用既有 chat() 文本协议。"""
        if message is None:
            # 理论上工具轮不该出现纯文本轮；若发生，仅返回 None
            return None, None
        text_parts: List[str] = []
        for typ, text in self.chat(message):
            if typ == "content":
                text_parts.append(text)
        joined = "".join(text_parts)
        return (joined or None), None

    def name(self) -> str:
        """
        获取当前使用的模型名称

        返回:
            str: 当前配置的模型名称
        """
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """
        获取当前平台的名称

        返回:
            str: 当前平台的名称
        """
        return "openai"

    def delete_chat(self) -> bool:
        """
        删除当前对话历史

        返回:
            bool: 操作是否成功

        说明:
            如果设置了系统消息，会保留系统消息
        """
        if self.system_message:
            self.messages = [{"role": "system", "content": self.system_message}]
        else:
            self.messages = []
        return True

    def trim_messages(self) -> bool:
        """裁剪消息历史以腾出token空间

        保留所有system消息，并丢弃开头的10条非system消息。

        返回:
            bool: 如果成功腾出空间返回True，否则返回False
        """
        if not self.messages:
            return False

        # 分离system消息和非system消息
        system_messages = [msg for msg in self.messages if msg.get("role") == "system"]
        non_system_messages = [
            msg for msg in self.messages if msg.get("role") != "system"
        ]

        # 如果非system消息少于等于10条，无法裁剪
        if len(non_system_messages) <= 10:
            PrettyOutput.auto_print("⚠️ 非系统消息数量不足，无法裁剪")
            return False

        # 丢弃开头的10条非system消息
        trimmed_messages = non_system_messages[10:]
        trimmed_count = len(non_system_messages) - len(trimmed_messages)

        # 重新组装消息列表：system消息 + 裁剪后的非system消息
        self.messages = system_messages + trimmed_messages

        # 检查裁剪后是否有剩余token
        remaining_tokens = self.get_remaining_token_count()
        if remaining_tokens > 0:
            PrettyOutput.auto_print(
                f"✅ 裁剪成功：丢弃了{trimmed_count}条非system消息，剩余token: {remaining_tokens}"
            )
            return True
        else:
            PrettyOutput.auto_print(f"⚠️ 裁剪失败：剩余token {remaining_tokens} 不足")
            return False

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """
        获取OpenAI平台所需的配置键列表（已弃用：建议使用 llm_config 配置）

        返回:
            List[str]: 配置键的列表（对应 llm_config 中的 openai_api_key, openai_api_base）
        """
        return ["OPENAI_API_KEY", "OPENAI_API_BASE"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取配置指导（已弃用：建议使用 llm_config 配置）

        返回:
            Dict[str, str]: 配置键名到配置指导的映射
        """
        return {
            "OPENAI_API_KEY": (
                "请输入您的 OpenAI API Key:\n"
                "获取方式一（官方）:\n"
                "1. 登录 OpenAI 平台: https://platform.openai.com/\n"
                "2. 进入 API Keys 页面\n"
                "3. 创建新的 API Key 或使用现有的\n"
                "4. 复制 API Key (以 sk- 开头)\n"
                "\n获取方式二（第三方代理）:\n"
                "如果使用第三方代理服务，请从代理服务商处获取 API Key"
            ),
            "OPENAI_API_BASE": (
                "请输入 API Base URL:\n"
                "- 官方 API: https://api.openai.com/v1\n"
                "- 如使用代理或第三方服务，请输入对应的 Base URL\n"
                "- 例如: https://your-proxy.com/v1"
            ),
        }

    @classmethod
    def get_env_defaults(cls) -> Dict[str, str]:
        """
        获取OpenAI平台环境变量的默认值

        返回:
            Dict[str, str]: 环境变量默认值的字典
        """
        return {"OPENAI_API_BASE": "https://api.openai.com/v1"}
