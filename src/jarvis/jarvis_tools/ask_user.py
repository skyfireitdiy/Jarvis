from typing import Dict, Any
from jarvis.jarvis_tools.base import Tool
from jarvis.utils import get_multiline_input, PrettyOutput, OutputType

class AskUserTool:
    name="ask_user"
    description="""Ask the user when information needed to complete the task is missing or when critical decision information is lacking. Users can input multiple lines of text, ending with an empty line. Use cases: 1. Need user to provide more information to complete the task; 2. Need user to make critical decisions; 3. Need user to confirm important operations; 4. Need user to provide additional information"""
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user"
            }
        },
        "required": ["question"]
    }
        

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the operation of asking the user
        
        Args:
            args: A dictionary containing the question
            
        Returns:
            Dict: A dictionary containing the user's response
        """
        try:
            question = args["question"]
            
            # Display the question
            PrettyOutput.print(f"Question: {question}", OutputType.SYSTEM)
            
            # Get user input
            user_response = get_multiline_input("Please enter your answer (input empty line to end)")
            
            return {
                "success": True,
                "stdout": user_response,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to ask user: {str(e)}"
            } 