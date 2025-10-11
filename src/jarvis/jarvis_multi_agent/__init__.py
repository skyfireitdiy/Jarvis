# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_agent.edit_file_handler import EditFileHandler
from jarvis.jarvis_agent.rewrite_file_handler import RewriteFileHandler
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot


class MultiAgent(OutputHandler):
    def __init__(self, agents_config: List[Dict], main_agent_name: str, common_system_prompt: str = ""):
        self.agents_config = agents_config
        self.agents_config_map = {c["name"]: c for c in agents_config}
        self.agents: Dict[str, Agent] = {}
        self.main_agent_name = main_agent_name
        self.original_question: Optional[str] = None
        self.common_system_prompt: str = common_system_prompt

    def prompt(self) -> str:
        return f"""
# 多智能体消息发送

## 交互原则与策略
### 消息处理规范
- **单一操作原则**：每轮只执行一个操作（工具调用或消息发送）
- **完整性原则**：确保消息包含所有必要信息，避免歧义
- **明确性原则**：清晰表达意图、需求和期望结果
- **上下文保留**：在消息中包含足够的背景信息

### 消息格式标准
```
{ot("SEND_MESSAGE")}
to: 智能体名称    # 目标智能体名称
content: |2
  # 消息主题
  ## 背景信息
  [提供必要的上下文和背景]
  ## 具体需求
  [明确表达期望完成的任务]
  ## 相关资源
  [列出相关文档、数据或工具]
  ## 期望结果
  [描述期望的输出格式和内容]
  ## 下一步计划
  [描述下一步的计划和行动]
{ct("SEND_MESSAGE")}
```

或者：

```
{ot("SEND_MESSAGE")}
to: 智能体名称    # 目标智能体名称
content: |2
  # 消息主题
  ## 任务结果
  [任务完成结果，用于反馈]
{ct("SEND_MESSAGE")}
```

## 可用智能体资源
{chr(10).join([f"- **{c['name']}**: {c.get('description', '')}" for c in self.agents_config])}
"""

    def can_handle(self, response: str) -> bool:
        # 只要检测到 SEND_MESSAGE 起始标签即认为可处理，
        # 即便内容有误也由 handle 返回明确错误与修复指导
        return ot("SEND_MESSAGE") in response

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        """
        处理 SEND_MESSAGE。若存在格式/解析/字段/目标等问题，返回明确错误原因与修复指导。
        """
        # 优先使用解析器获取“正确路径”结果
        parsed = self._extract_send_msg(response)
        if len(parsed) == 1:
            msg = parsed[0]
            # 字段校验
            to_val = msg.get("to")
            content_val = msg.get("content")
            missing = []
            if not to_val:
                missing.append("to")
            if content_val is None or (isinstance(content_val, str) and content_val.strip() == ""):
                # 允许空格/空行被视为缺失
                missing.append("content")
            if missing:
                guidance = (
                    "SEND_MESSAGE 字段缺失或为空："
                    + ", ".join(missing)
                    + "\n修复建议：\n"
                    "- 必须包含 to 和 content 字段\n"
                    "- to: 目标智能体名称（字符串）\n"
                    "- content: 发送内容，建议使用多行块 |2 保持格式\n"
                    "示例：\n"
                    f"{ot('SEND_MESSAGE')}\n"
                    "to: 目标Agent名称\n"
                    "content: |2\n"
                    "  这里填写要发送的消息内容\n"
                    f"{ct('SEND_MESSAGE')}"
                )
                return False, guidance
            # 类型校验
            if not isinstance(to_val, str):
                return False, "SEND_MESSAGE 字段类型错误：to 必须为字符串。修复建议：将 to 改为字符串，如 to: ChapterPolisher"
            if not isinstance(content_val, str):
                return False, "SEND_MESSAGE 字段类型错误：content 必须为字符串。修复建议：将 content 改为字符串或使用多行块 content: |2"
            # 目标校验
            if to_val not in self.agents_config_map:
                available = ", ".join(self.agents_config_map.keys())
                return (
                    False,
                    f"目标智能体不存在：'{to_val}' 不在可用列表中。\n"
                    f"可用智能体：[{available}]\n"
                    "修复建议：\n"
                    "- 将 to 修改为上述可用智能体之一\n"
                    "- 或检查配置中是否遗漏了该智能体的定义"
                )
            # 通过校验，交给上层发送
            return True, {"to": to_val, "content": content_val}
        elif len(parsed) > 1:
            return (
                False,
                "检测到多个 SEND_MESSAGE 块。一次只能发送一个消息。\n修复建议：合并消息或分多轮发送，每轮仅保留一个 SEND_MESSAGE 块。"
            )
        # 未成功解析，进行诊断并返回可操作指导
        try:
            normalized = response.replace("\r\n", "\n").replace("\r", "\n")
        except Exception:
            normalized = response
        ot_tag = ot("SEND_MESSAGE")
        ct_tag = ct("SEND_MESSAGE")
        has_open = ot_tag in normalized
        has_close = ct_tag in normalized
        if has_open and not has_close:
            return (
                False,
                f"检测到 {ot_tag} 但缺少结束标签 {ct_tag}。\n"
                "修复建议：在消息末尾补充结束标签，并确认标签各自独占一行。\n"
                "示例：\n"
                f"{ot_tag}\n"
                "to: 目标Agent名称\n"
                "content: |2\n"
                "  这里填写要发送的消息内容\n"
                f"{ct_tag}"
            )
        # 尝试提取原始块并指出 YAML 问题
        import re as _re
        pattern = _re.compile(
            rf"{_re.escape(ot_tag)}[ \t]*\n(.*?)(?:\n)?[ \t]*{_re.escape(ct_tag)}",
            _re.DOTALL,
        )
        blocks = pattern.findall(normalized)
        if not blocks:
            alt_pattern = _re.compile(
                rf"{_re.escape(ot_tag)}[ \t]*(.*?)[ \t]*{_re.escape(ct_tag)}",
                _re.DOTALL,
            )
            blocks = alt_pattern.findall(normalized)
        if not blocks:
            return (
                False,
                "SEND_MESSAGE 格式错误：未能识别完整的消息块。\n"
                "修复建议：确保起止标签在单独行上，且中间内容为合法的 YAML，包含 to 与 content 字段。"
            )
        raw = blocks[0]
        try:
            msg_obj = yaml.safe_load(raw)
            if not isinstance(msg_obj, dict):
                return (
                    False,
                    "SEND_MESSAGE 内容必须为 YAML 对象（键值对）。\n"
                    "修复建议：使用 to 与 content 字段构成的对象。\n"
                    "示例：\n"
                    f"{ot('SEND_MESSAGE')}\n"
                    "to: 目标Agent名称\n"
                    "content: |2\n"
                    "  这里填写要发送的消息内容\n"
                    f"{ct('SEND_MESSAGE')}"
                )
            missing_keys = [k for k in ("to", "content") if k not in msg_obj]
            if missing_keys:
                return (
                    False,
                    "SEND_MESSAGE 缺少必要字段：" + ", ".join(missing_keys) + "\n"
                    "修复建议：补充缺失字段。\n"
                    "示例：\n"
                    f"{ot('SEND_MESSAGE')}\n"
                    "to: 目标Agent名称\n"
                    "content: |2\n"
                    "  这里填写要发送的消息内容\n"
                    f"{ct('SEND_MESSAGE')}"
                )
            # 针对值类型的提示（更细）
            if not isinstance(msg_obj.get("to"), str):
                return False, "SEND_MESSAGE 字段类型错误：to 必须为字符串。"
            if not isinstance(msg_obj.get("content"), str):
                return False, "SEND_MESSAGE 字段类型错误：content 必须为字符串，建议使用多行块 |2。"
            # 若到此仍未返回，说明结构基本正确，但 _extract_send_msg 未命中，给出泛化建议
            return (
                False,
                "SEND_MESSAGE 格式可能存在缩进或空白字符问题，导致未被系统识别。\n"
                "修复建议：\n"
                "- 确保起止标签各占一行\n"
                "- 标签与内容之间保留换行\n"
                "- 使用 content: |2 并保证 YAML 缩进一致\n"
                "示例：\n"
                f"{ot('SEND_MESSAGE')}\n"
                "to: 目标Agent名称\n"
                "content: |2\n"
                "  这里填写要发送的消息内容\n"
                f"{ct('SEND_MESSAGE')}"
            )
        except Exception as e:
            return (
                False,
                f"SEND_MESSAGE YAML 解析失败：{str(e)}\n"
                "修复建议：\n"
                "- 检查冒号、缩进与引号是否正确\n"
                "- 使用 content: |2 多行块以避免缩进歧义\n"
                "示例：\n"
                f"{ot('SEND_MESSAGE')}\n"
                "to: 目标Agent名称\n"
                "content: |2\n"
                "  这里填写要发送的消息内容\n"
                f"{ct('SEND_MESSAGE')}"
            )

    def name(self) -> str:
        return "SEND_MESSAGE"

    @staticmethod
    def _extract_send_msg(content: str) -> List[Dict]:
        """Extract send message from content.

        Args:
            content: The content containing send message
        """
        # Normalize line endings to handle CRLF/CR cases to ensure robust matching
        try:
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        except Exception:
            normalized = content

        ot_tag = ot("SEND_MESSAGE")
        ct_tag = ct("SEND_MESSAGE")

        # Auto-append closing tag if missing
        if ot_tag in normalized and ct_tag not in normalized:
            normalized += "\n" + ct_tag

        # Use robust regex with DOTALL; escape tags to avoid regex meta issues
        pattern = re.compile(
            rf"{re.escape(ot_tag)}[ \t]*\n(.*?)(?:\n)?[ \t]*{re.escape(ct_tag)}",
            re.DOTALL,
        )
        data = pattern.findall(normalized)
        # Fallback: handle cases without explicit newlines around closing tag
        if not data:
            alt_pattern = re.compile(
                rf"{re.escape(ot_tag)}[ \t]*(.*?)[ \t]*{re.escape(ct_tag)}",
                re.DOTALL,
            )
            data = alt_pattern.findall(normalized)

        ret = []
        for item in data:
            try:
                msg = yaml.safe_load(item)
                if isinstance(msg, dict) and "to" in msg and "content" in msg:
                    ret.append(msg)
            except Exception:
                continue
        return ret

    def _get_agent(self, name: str) -> Union[Agent, None]:
        if name in self.agents:
            return self.agents[name]

        if name not in self.agents_config_map:
            return None

        config = self.agents_config_map[name].copy()

        # Prepend common system prompt if configured
        common_sp = getattr(self, "common_system_prompt", "")
        if common_sp:
            existing_sp = config.get("system_prompt", "")
            if existing_sp:
                config["system_prompt"] = f"{common_sp}\n\n{existing_sp}"
            else:
                config["system_prompt"] = common_sp

        if name != self.main_agent_name and self.original_question:
            system_prompt = config.get("system_prompt", "")
            config["system_prompt"] = (
                f"{system_prompt}\n\n# 原始问题\n{self.original_question}"
            )

        agent = Agent(output_handler=[ToolRegistry(),  EditFileHandler(), RewriteFileHandler(), self],**config)
        self.agents[name] = agent
        return agent

    def run(self, user_input: str) -> str:
        self.original_question = user_input
        last_agent_name = self.main_agent_name

        agent = self._get_agent(self.main_agent_name)
        if not agent:
            # This should not happen if main_agent_name is correctly configured
            return f"主智能体 {self.main_agent_name} 未找到"

        msg: Any = agent.run(user_input)

        while msg:
            if isinstance(msg, str):
                return msg

            if not isinstance(msg, Dict):
                # Should not happen if agent.run() returns str or Dict
                PrettyOutput.print(f"未知消息类型: {type(msg)}", OutputType.WARNING)
                break

            # Generate a brief summary via direct model call to avoid run-loop recursion
            try:
                # 参照 Agent.generate_summary 的实现思路：基于当前 session.prompt 追加请求提示，直接调用底层模型
                multi_agent_summary_prompt = """
请基于当前会话，为即将发送给其他智能体的协作交接写一段摘要，包含：
- 已完成的主要工作与产出
- 关键决策及其理由
- 已知的约束/风险/边界条件
- 未解决的问题与待澄清点
- 下一步建议与对目标智能体的具体请求
要求：
- 仅输出纯文本，不包含任何指令或工具调用
- 使用简洁的要点式表述
""".strip()
                summary_any: Any = agent.model.chat_until_success(  # type: ignore[attr-defined]
                    f"{agent.session.prompt}\n{multi_agent_summary_prompt}"
                )
                summary_text = summary_any.strip() if isinstance(summary_any, str) else ""
            except Exception:
                summary_text = ""
            prompt = f"""
Please handle this message:
from: {last_agent_name}
summary_of_sender_work: {summary_text}
content: {msg['content']}
"""
            to_agent_name = msg.get("to")
            if not to_agent_name:
                return "消息中未指定 `to` 字段"

            if to_agent_name not in self.agents_config_map:
                PrettyOutput.print(
                    f"未找到智能体 {to_agent_name}，正在重试...", OutputType.WARNING
                )
                agent = self._get_agent(last_agent_name)
                if not agent:
                    return f"智能体 {last_agent_name} 未找到"
                msg = agent.run(
                    f"未找到智能体 {to_agent_name}，可用智能体列表: {list(self.agents_config_map.keys())}"
                )
                continue

            PrettyOutput.print(
                f"{last_agent_name} 正在向 {to_agent_name} 发送消息...", OutputType.INFO
            )

            agent = self._get_agent(to_agent_name)
            if not agent:
                return f"智能体 {to_agent_name} 未找到"

            # Check if the sending agent should be cleared
            sender_config = self.agents_config_map.get(last_agent_name, {})
            if sender_config.get("clear_after_send_message"):
                if agent:
                    PrettyOutput.print(f"清除智能体 {last_agent_name} 在发送消息后的历史记录...", OutputType.INFO)
                    agent.clear_history()

            last_agent_name = agent.name
            msg = agent.run(prompt)
        return ""
