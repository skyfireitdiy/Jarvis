from typing import Dict, Any, List, Optional, Union, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import PrettyOutput, OutputType, init_env, user_confirm

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
            pm_result = self.pm.analyze_requirement(requirement)
            if not pm_result["success"]:
                return pm_result
            
            PrettyOutput.print(pm_result["analysis"], OutputType.INFO)
            
            # PM will coordinate with other roles through messages
            # Each role can decide next steps and send messages to others
            # Development flow is determined by role interactions
            
            # Track development state
            state = {
                "requirement": requirement,
                "pm_analysis": pm_result,
                "current_stage": "analysis"
            }
            
            # Let roles collaborate until completion
            while True:
                if state.get("completed"):
                    return {
                        "success": True,
                        "result": state
                    }
                    
                if state.get("failed"):
                    return {
                        "success": False,
                        "error": state.get("error", "Development failed")
                    }
                    
                # Wait for user confirmation before continuing
                if not user_confirm("Continue development?"):
                    return {
                        "success": False,
                        "error": "Development cancelled by user"
                    }
    
        except Exception as e:
            return {
                "success": False, 
                "error": f"Development process failed: {str(e)}"
            }

    def _check_qa_passed(self, verification: Dict) -> bool:
        """Check if QA verification passed"""
        try:
            # Check unit tests
            unit_tests = verification["test_results"]["unit_tests"]
            for suite in unit_tests:
                if suite["failed"] > 0:
                    return False
                
            # Check integration tests    
            integration_tests = verification["test_results"]["integration_tests"]
            for suite in integration_tests:
                for scenario in suite["scenarios"]:
                    if scenario["status"] == "Fail":
                        return False
                        
            # Check critical issues
            if verification["recommendations"]["critical_issues"]:
                return False
                
            return True
            
        except Exception:
            return False
            
    def _update_design_with_qa_feedback(self, design: str, qa_feedback: Dict) -> str:
        """Update design based on QA feedback"""
        try:
            # Create feedback prompt
            prompt = f"""Please update this system design based on QA feedback:

Current Design:
{design}

QA Feedback:
{qa_feedback}

Please provide updated design maintaining the same YAML format."""

            # Get updated design
            result = self.sa.agent.run(prompt)
            return result
            
        except Exception as e:
            PrettyOutput.print(f"Failed to update design: {str(e)}", OutputType.ERROR)
            return design

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
    import argparse

    init_env()
    
    parser = argparse.ArgumentParser(description='Development team automation')
    parser.add_argument('requirement', help='Development requirement')
    args = parser.parse_args()
    
    team = DevTeam()
    result = team.handle_requirement(args.requirement)
    
    if result["success"]:
        PrettyOutput.print("Development completed successfully!", OutputType.SUCCESS)
        PrettyOutput.print(result["result"], OutputType.INFO)
    else:
        PrettyOutput.print(f"Development failed: {result['error']}", OutputType.ERROR)

if __name__ == "__main__":
    main()
