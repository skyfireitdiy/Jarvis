# -*- coding: utf-8 -*-
"""Jev（TypeSafe System One）平台适配器。

Jev 与常规对话模型的接口形态差异很大：
- 无对话、无流式、无多模态，一次请求返回结构化的类型化决策；
- 请求体为 ``{"state": ..., "model": ..., "questions": {...}}``；
- 响应体为 ``{"model": ..., "answers": {...}, "usage": {...}}``。

为了不破坏 BasePlatform 的 ``chat()`` 契约（流式文本生成器），本适配器采用
**文本协议**：调用方把 ``state`` 与 ``questions`` 以 JSON 字符串传入 ``chat()``，
适配器解析后调用 ``POST /v1/systemone``，再把结构化答案序列化为可读文本 yield 出去。

输入格式（message 为 JSON 字符串）::

    {
      "state": "待评估的内容，可以是字符串/对象/数组",
      "questions": {
        "is_urgent": {"type": "noul", "instructions": "是否表达紧迫性？"},
        "team": {"type": "choice", "instructions": "应由哪个团队处理？",
                 "criteria": {"billing": "计费", "tech": "技术"}},
        "level": {"type": "score", "instructions": "严重程度？",
                  "criteria": ["低", "中", "高"]}
      }
    }

若 message 不是合法 JSON，或缺少 ``state``/``questions``，则抛出异常说明期望格式，
避免臆造默认问题导致静默的错误行为。
"""

import json
import os
import time
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import httpx

import jarvis.jarvis_utils.globals as jglobals
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.config import get_request_timeout
from jarvis.jarvis_utils.output import PrettyOutput

# 默认 API 地址与模型
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL_NAME = "jev-latest"

# 重试策略：429（限流）/ 529（服务过载）时指数退避
MAX_RETRIES = 4
RETRY_BACKOFF_BASE = 1.0  # 秒，实际等待为 base * 2**attempt

# 单次请求超时（秒）：Jev 延迟 70~500ms，给足网络抖动余量
DEFAULT_TIMEOUT = 60.0


class JevPlatform(BasePlatform):
    """Jev（TypeSafe System One）平台实现。

    Jev 只做"类型化决策"（Choice/Score/Noul），不生成自由文本、不支持多模态、
    也没有对话历史，因此本类把对话语义降级为"一次状态评估"。
    """

    def __init__(
        self,
        platform_type: str = "normal",
        agent: Optional[Any] = None,
    ):
        """初始化 Jev 平台。

        参数:
            platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'
            agent: Agent 实例，用于回调触发总结等功能
        """
        super().__init__(platform_type=platform_type, agent=agent)
        self.system_message = ""
        self.messages: List[Dict[str, Any]] = []
        llm_config = self._llm_config or {}

        # 基类按 platform_type 从全局配置取 model_name，但未配置 Jev 时会串到其它平台的
        # 模型名（如 gpt-5）。这里做一次兜底：非 Jev 系列模型名一律回退到 jev-latest。
        if not self._is_jev_model_name(self.model_name):
            self.model_name = DEFAULT_MODEL_NAME

        # 配置读取：llm_config 优先（键存在即采用，即使为空），否则回退环境变量
        if llm_config:
            if "typesafe_api_key" in llm_config:
                self.api_key = llm_config.get("typesafe_api_key")
            else:
                self.api_key = os.getenv("TYPESAFE_API_KEY")
            if "typesafe_api_base" in llm_config:
                self.base_url = llm_config.get("typesafe_api_base")
            else:
                self.base_url = os.getenv("TYPESAFE_API_BASE", DEFAULT_BASE_URL)
        else:
            self.api_key = os.getenv("TYPESAFE_API_KEY")
            self.base_url = os.getenv("TYPESAFE_API_BASE", DEFAULT_BASE_URL)

        # 归一化为 api_keys 列表，支持多 Key 轮询（与 openai/claude 平台一致）
        if isinstance(self.api_key, list):
            self.api_keys = self.api_key
        elif isinstance(self.api_key, str) and self.api_key:
            self.api_keys = [k.strip() for k in self.api_key.split(",") if k.strip()]
        else:
            self.api_keys = [self.api_key] if self.api_key else []
        if self.api_keys:
            self.api_key = self.api_keys[0]
        self._api_key_index = 0

        # base_url 为空时回退默认值，避免拼接出非法 URL
        if not self.base_url:
            self.base_url = DEFAULT_BASE_URL
        self.base_url = str(self.base_url).rstrip("/")

        # 代理模式：把原始 base_url 挂到网关的 http_proxy 路由下
        if jglobals.proxy_node and jglobals.master_url:
            self.base_url = (
                f"{jglobals.master_url}/api/node/{jglobals.proxy_node}"
                f"/http_proxy/{self.base_url}"
            )

        # 仅在显式配置了 llm_config 却没拿到 Key 时告警，避免配置未加载完成时误报
        if not self.api_key and llm_config:
            PrettyOutput.auto_print(
                "⚠️ 未找到 TypeSafe API Key，请在 llm_config 中设置 typesafe_api_key "
                "或设置 TYPESAFE_API_KEY 环境变量"
            )

        # 请求超时：优先 request_timeout 配置，未配置时使用默认值
        self.timeout: float = get_request_timeout() or DEFAULT_TIMEOUT

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    def _is_jev_model_name(model_name: Any) -> bool:
        """判断模型名是否属于 Jev 系列。

        参数:
            model_name: 待判断的模型名

        返回:
            bool: 是 Jev 系列返回 True
        """
        return isinstance(model_name, str) and model_name.strip().lower().startswith(
            "jev"
        )

    def _get_next_api_key(self) -> Optional[str]:
        """轮询获取下一个 API Key，用于多 Key 负载均衡。"""
        if not self.api_keys:
            return None
        if len(self.api_keys) == 1:
            return self.api_keys[0]
        key = self.api_keys[self._api_key_index]
        self._api_key_index = (self._api_key_index + 1) % len(self.api_keys)
        return key

    def _build_headers(self) -> Dict[str, str]:
        """构造请求头，包含动态注入的网关认证头。"""
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # 代理模式下每次请求实时读取 Token，避免主网关重启后 Token 失效
        headers.update(self._get_proxy_extra_headers())
        return headers

    @staticmethod
    def _validate_questions(questions: Any) -> Dict[str, Any]:
        """校验并规范化 questions 字段。

        参数:
            questions: 待校验的问题映射

        返回:
            Dict[str, Any]: 规范化后的问题映射

        异常:
            ValueError: questions 非法时抛出，并说明期望格式
        """
        if not isinstance(questions, dict) or not questions:
            raise ValueError(
                "questions 必须是非空对象，形如 "
                '{"<问题ID>": {"type": "noul|choice|score", "instructions": "..."}}'
            )
        normalized: Dict[str, Any] = {}
        for qid, question in questions.items():
            if not isinstance(question, dict):
                raise ValueError(
                    f"问题 '{qid}' 必须是对象，包含 type 与 instructions 字段"
                )
            qtype = question.get("type")
            if qtype not in ("noul", "choice", "score"):
                raise ValueError(
                    f"问题 '{qid}' 的 type 非法：{qtype!r}，"
                    "仅支持 'noul'、'choice'、'score'"
                )
            if not question.get("instructions"):
                raise ValueError(f"问题 '{qid}' 缺少 instructions 字段")
            # choice/score 的 criteria 是 API 必填项，提前校验可避免到服务端才报 422
            criteria = question.get("criteria")
            if qtype == "choice":
                if not isinstance(criteria, dict) or not criteria:
                    raise ValueError(
                        f"问题 '{qid}'（choice）的 criteria 必须是非空对象，"
                        '形如 {"选项名": "选项说明"}'
                    )
            elif qtype == "score":
                if not isinstance(criteria, list) or len(criteria) < 2:
                    raise ValueError(
                        f"问题 '{qid}'（score）的 criteria 必须是至少 2 项的数组，"
                        '形如 ["低", "中", "高"]'
                    )
                if len(criteria) > 10:
                    raise ValueError(
                        f"问题 '{qid}'（score）的 criteria 最多 10 项，"
                        f"当前为 {len(criteria)} 项"
                    )
            normalized[str(qid)] = question
        return normalized

    @classmethod
    def parse_state_and_questions(
        cls, message: Union[str, List[ContentBlock]]
    ) -> Tuple[Any, Dict[str, Any]]:
        """把 chat() 的 message 解析为 (state, questions)。

        参数:
            message: JSON 字符串，或已解析的 dict（便于程序内直接调用）

        返回:
            Tuple[Any, Dict[str, Any]]: (state, 规范化后的 questions)

        异常:
            ValueError: 输入不符合约定格式时抛出，并给出期望格式说明
        """
        if isinstance(message, list):
            # 多模态输入不支持：仅拼接文本块，避免直接崩溃
            text_parts = [
                block.get("text", "")
                for block in message
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            message = "\n".join(text_parts)

        if isinstance(message, str):
            raw = message.strip()
            try:
                payload = json.loads(raw)
            except Exception as e:
                raise ValueError(
                    "Jev 平台要求输入为 JSON 字符串，形如 "
                    '{"state": <待评估内容>, "questions": {<问题ID>: <问题定义>}}；'
                    f"当前输入无法解析为 JSON：{e}"
                )
        elif isinstance(message, dict):
            payload = message
        else:
            raise ValueError(
                "Jev 平台的输入必须是 JSON 字符串或 dict，"
                f"当前类型为 {type(message).__name__}"
            )

        if not isinstance(payload, dict):
            raise ValueError(
                "Jev 平台的输入 JSON 必须是对象，形如 "
                '{"state": <待评估内容>, "questions": {<问题ID>: <问题定义>}}'
            )
        if "state" not in payload:
            raise ValueError("Jev 平台的输入缺少 'state' 字段")
        if "questions" not in payload:
            raise ValueError("Jev 平台的输入缺少 'questions' 字段")

        return payload["state"], cls._validate_questions(payload["questions"])

    @classmethod
    def build_request_body(
        cls,
        state: Any,
        questions: Dict[str, Any],
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> Dict[str, Any]:
        """构造 /v1/systemone 的请求体（纯函数，便于独立验证）。

        参数:
            state: 待评估内容
            questions: 已校验的问题映射
            model_name: 模型名，默认 jev-latest

        返回:
            Dict[str, Any]: 请求体
        """
        return {
            "state": state,
            "model": model_name or DEFAULT_MODEL_NAME,
            "questions": questions,
        }

    @staticmethod
    def format_answers(response: Dict[str, Any]) -> str:
        """把 Jev 响应序列化为可读文本（纯函数，便于独立验证）。

        参数:
            response: Jev 的响应体

        返回:
            str: 人类可读的答案文本，含取值、置信度与概率分布
        """
        lines: List[str] = []
        model = response.get("model", DEFAULT_MODEL_NAME)
        lines.append(f"Jev 模型: {model}")

        answers = response.get("answers") or {}
        if not answers:
            lines.append("(无答案)")
        for qid, answer in answers.items():
            if not isinstance(answer, dict):
                lines.append(f"- {qid}: {answer}")
                continue
            atype = answer.get("type", "unknown")
            if atype == "noul":
                # Noul 返回"是"的概率，0~1
                lines.append(f"- {qid} [noul]: {answer.get('noul')}")
            elif atype == "choice":
                lines.append(f"- {qid} [choice]: {answer.get('choice')}")
            elif atype == "score":
                lines.append(f"- {qid} [score]: {answer.get('score')}")
            else:
                lines.append(f"- {qid} [{atype}]: {answer}")

            confidence = answer.get("confidence")
            if confidence is not None:
                lines.append(f"    confidence: {confidence}")
            probabilities = answer.get("probabilities")
            if probabilities is not None:
                lines.append(f"    probabilities: {probabilities}")
            legend = answer.get("legend")
            if legend is not None:
                lines.append(f"    legend: {legend}")

        usage = response.get("usage") or {}
        if usage:
            lines.append(
                f"usage: input_tokens={usage.get('input_tokens')}, "
                f"output_tokens={usage.get('output_tokens')}"
            )
        return "\n".join(lines)

    def _post_systemone(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """调用 POST /v1/systemone，处理重试与错误。

        参数:
            body: 请求体

        返回:
            Dict[str, Any]: 响应体

        异常:
            RuntimeError: 请求失败且重试耗尽时抛出，异常信息包含响应体
        """
        url = f"{self.base_url}/v1/systemone"
        last_error: Optional[str] = None

        for attempt in range(MAX_RETRIES):
            # 每轮轮询 API Key，实现多 Key 负载均衡
            next_key = self._get_next_api_key()
            if next_key:
                self.api_key = next_key
            try:
                resp = httpx.post(
                    url,
                    json=body,
                    headers=self._build_headers(),
                    timeout=self.timeout,
                )
            except Exception as e:
                # 网络层异常：同样按退避重试
                last_error = f"请求异常: {e}"
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                    continue
                raise RuntimeError(f"Jev 请求失败（{url}）：{last_error}")

            # 限流/过载：指数退避重试，优先尊重 retry-after 头
            if resp.status_code in (429, 529):
                last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF_BASE * (2**attempt)
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        try:
                            wait = max(wait, float(retry_after))
                        except ValueError:
                            pass
                    PrettyOutput.auto_print(
                        f"⚠️ Jev 限流/过载（HTTP {resp.status_code}），"
                        f"{wait:.0f}s 后重试 ({attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Jev 请求失败（限流/过载，已重试 {MAX_RETRIES} 次）：{last_error}"
                )

            # 认证/参数错误：不可重试，直接抛出带响应体的异常
            if resp.status_code in (401, 422):
                raise RuntimeError(
                    f"Jev 请求失败（HTTP {resp.status_code}）：{resp.text[:1000]}"
                )

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Jev 请求失败（HTTP {resp.status_code}）：{resp.text[:1000]}"
                )

            try:
                return resp.json()
            except Exception as e:
                raise RuntimeError(
                    f"Jev 响应解析失败：{e}，原始响应：{resp.text[:500]}"
                )

        raise RuntimeError(f"Jev 请求失败：{last_error}")

    # ------------------------------------------------------------------
    # BasePlatform 必需接口
    # ------------------------------------------------------------------
    def set_messages(self, messages: List[Dict[str, Any]]) -> None:
        """替换对话历史。

        Jev 无对话语义，这里仅保留最近一条 user 消息作为待评估输入，
        以便上层复用统一的会话管理接口。
        """
        self.messages = messages
        for msg in messages:
            if msg.get("role") == "system":
                self.system_message = msg.get("content", "")
                break

    def get_messages(self) -> List[Dict[str, Any]]:
        """获取对话历史。"""
        return self.messages

    def set_model_name(self, model_name: str):
        """设置模型名称。"""
        self.model_name = model_name

    def set_system_prompt(self, message: str):
        """设置系统提示。

        Jev 不支持 system prompt，这里仅记录，不参与请求构造。
        """
        self.messages = []
        self.system_message = message
        self.messages.append({"role": "system", "content": self.system_message})

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取可用模型列表（GET /v1/models）。

        返回:
            List[Tuple[str, str]]: (模型ID, 描述) 列表；失败时返回空列表
        """
        try:
            next_key = self._get_next_api_key()
            if next_key:
                self.api_key = next_key
            resp = httpx.get(
                f"{self.base_url}/v1/models",
                headers=self._build_headers(),
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                PrettyOutput.auto_print(
                    f"❌ 获取 Jev 模型列表失败：HTTP {resp.status_code} "
                    f"{resp.text[:200]}"
                )
                return []
            models = (resp.json() or {}).get("models") or []
            return [
                (str(m.get("name", "")), str(m.get("description", "")))
                for m in models
                if isinstance(m, dict) and m.get("name")
            ]
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 获取 Jev 模型列表失败：{str(e)}")
            return []

    def chat(
        self, message: Union[str, List[ContentBlock]]
    ) -> Generator[Tuple[str, str], None, None]:
        """执行一次 Jev 评估。

        参数:
            message: JSON 字符串，包含 state 与 questions（见模块文档）

        返回:
            Generator[Tuple[str, str], None, None]: 仅 yield ("content", 文本)

        异常:
            ValueError: 输入格式不符合约定
            RuntimeError: API 调用失败
        """
        # 记录追加前的长度，失败时回滚，避免污染历史
        messages_before_user = len(self.messages)
        try:
            state, questions = self.parse_state_and_questions(message)
            body = self.build_request_body(state, questions, self.model_name)

            # 记录用户消息（原始 JSON 文本），保持会话历史可追溯
            user_content = (
                message
                if isinstance(message, str)
                else json.dumps(message, ensure_ascii=False)
            )
            self.messages.append({"role": "user", "content": user_content})

            response = self._post_systemone(body)
            text = self.format_answers(response)

            self.messages.append({"role": "assistant", "content": text})
            yield ("content", text)
        except Exception:
            # 失败时回滚已追加的用户消息
            if len(self.messages) > messages_before_user:
                self.messages = self.messages[:messages_before_user]
            raise

    def name(self) -> str:
        """获取当前使用的模型名称。"""
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """获取平台名称（用于配置中的 platform 字段）。"""
        return "jev"

    def delete_chat(self) -> bool:
        """清空对话历史（保留系统消息）。"""
        if self.system_message:
            self.messages = [{"role": "system", "content": self.system_message}]
        else:
            self.messages = []
        return True

    def trim_messages(self) -> bool:
        """裁剪消息历史。

        Jev 无对话上下文，每次请求只依赖当前输入，因此直接清空非系统消息即可。
        """
        if not self.messages:
            return False
        system_messages = [m for m in self.messages if m.get("role") == "system"]
        non_system = [m for m in self.messages if m.get("role") != "system"]
        if not non_system:
            PrettyOutput.auto_print("⚠️ 非系统消息数量不足，无法裁剪")
            return False
        self.messages = system_messages
        return True

    def supports_multimodal(self) -> bool:
        """Jev 仅支持文本输入。"""
        return False

    def supports_native_tool_calls(self) -> bool:
        """Jev 不支持原生 function calling。"""
        return False

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """获取 Jev 平台所需的配置键列表。

        返回:
            List[str]: 配置键列表（对应 llm_config 中的 typesafe_api_key/typesafe_api_base）
        """
        return ["TYPESAFE_API_KEY", "TYPESAFE_API_BASE"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """获取配置指导。"""
        return {
            "TYPESAFE_API_KEY": (
                "请输入您的 TypeSafe API Key:\n"
                "1. 登录 TypeSafe 控制台: https://console.typesafe.ai/\n"
                "2. 进入 API Keys 页面创建 Key\n"
                "3. 复制 API Key 并填入（llm_config 键名：typesafe_api_key）"
            ),
            "TYPESAFE_API_BASE": (
                "请输入 API Base URL:\n"
                "- 官方 API: https://api.typesafe.ai\n"
                "- 如使用代理或第三方网关，请输入对应的 Base URL"
            ),
        }

    @classmethod
    def get_env_defaults(cls) -> Dict[str, str]:
        """获取环境变量默认值。"""
        return {"TYPESAFE_API_BASE": DEFAULT_BASE_URL}
