from typing import Dict, Any, List, Optional, Union, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, init_env, user_confirm

from jarvis.jarvis_dev.pm import ProductManager
from jarvis.jarvis_dev.ba import BusinessAnalyst
from jarvis.jarvis_dev.tl import TechLead
from jarvis.jarvis_dev.sa import SystemAnalyst
from jarvis.jarvis_dev.dev import Developer
from jarvis.jarvis_dev.qa import QualityAssurance
from jarvis.jarvis_dev.message import Message, MessageType

class DevTeam:
    """Development team with multiple roles"""
    
    def __init__(self):
        """Initialize development team"""
        # Create typed message handler
        message_handler: Callable[[Message], Dict[str, Any]] = lambda msg: self.handle_message(msg)
        
        # Initialize roles
        self.pm = ProductManager(message_handler=message_handler)
        self.ba = BusinessAnalyst(message_handler=message_handler)
        self.tl = TechLead(message_handler=message_handler)
        self.sa = SystemAnalyst(message_handler=message_handler)
        self.dev = Developer(message_handler=message_handler)
        self.qa = QualityAssurance(message_handler=message_handler)
        
        # Role mapping
        self.roles = {
            "ProductManager": self.pm,
            "BusinessAnalyst": self.ba,
            "TechLead": self.tl,
            "SystemAnalyst": self.sa,
            "Developer": self.dev,
            "QualityAssurance": self.qa
        }
        
    def handle_requirement(self, requirement: str) -> Dict[str, Any]:
        """Handle development requirement with team collaboration"""
        try:
            # Let PM analyze and plan the development process
            PrettyOutput.section("\n=== Product Manager Analysis ===", OutputType.INFO)
            self.pm.complete_requirement(requirement)
            return {
                "success": True,
                "result": "Product Manager completed the requirement"
            }
        except Exception as e:
            return {
                "success": False, 
                "error": f"Development process failed: {str(e)}"
            }

            

    def handle_message(self, message: Message) -> Dict[str, Any]:
        """Handle inter-role message"""
        if message.to_role not in self.roles:
            return {
                "success": False,
                "error": f"Unknown recipient role: {message.to_role}"
            }
        
        # Get recipient role and handle message
        recipient = self.roles[message.to_role]
        result = recipient.handle_message(message)
        
        if result["success"]:
            PrettyOutput.print(f"\n{message.to_role}'s Response:", OutputType.INFO)
            PrettyOutput.print(result["response"], OutputType.INFO)
        
        return result

    def send_message(self, from_role: str, to_role: str,
                    msg_type: MessageType, content: str,
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send message between roles"""
        if from_role not in self.roles:
            return {
                "success": False,
                "error": f"Unknown sender role: {from_role}"
            }
            
        # Create and send message
        sender = self.roles[from_role]
        message = sender.send_message(to_role, msg_type, content, context)
        return self.handle_message(message)

def main():
    """CLI entry point"""
    init_env()
    
    team = DevTeam()
    
    while True:
        # 获取用户输入
        requirement = get_multiline_input("\n请输入开发需求 (输入空行退出)")
        if not requirement:
            break
            
        # 处理需求
        result = team.handle_requirement(requirement)
        
        if result["success"]:
            PrettyOutput.print("开发任务完成!", OutputType.SUCCESS)
            PrettyOutput.print(result["result"], OutputType.INFO)
        else:
            PrettyOutput.print(f"开发任务失败: {result['error']}", OutputType.ERROR)

if __name__ == "__main__":
    main()
