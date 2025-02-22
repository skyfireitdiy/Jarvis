from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

class MessageType(Enum):
    QUESTION = "question"  # 询问/澄清
    FEEDBACK = "feedback"  # 反馈/建议
    UPDATE = "update"     # 更新/修改
    CONFIRM = "confirm"   # 确认/同意
    REJECT = "reject"     # 拒绝/否决

@dataclass
class Message:
    """Team communication message"""
    from_role: str
    to_role: str
    msg_type: MessageType
    content: str
    context: Optional[Dict[str, Any]] = None  # 相关上下文

def parse_message_command(output: str) -> Optional[Message]:
    """Parse message command from output
    
    Format:
    <SEND_MESSAGE>
    to: role_name
    type: message_type
    content: message_content
    context: optional_context_dict
    </SEND_MESSAGE>
    """
    import re
    import yaml
    
    msg_match = re.search(r'<SEND_MESSAGE>\s*(.*?)\s*</SEND_MESSAGE>', output, re.DOTALL)
    if not msg_match:
        return None
        
    try:
        msg_yaml = yaml.safe_load(msg_match.group(1))
        return Message(
            from_role="",  # Will be set by sender
            to_role=msg_yaml["to"],
            msg_type=MessageType(msg_yaml["type"]),
            content=msg_yaml["content"],
            context=msg_yaml.get("context")
        )
    except:
        return None 