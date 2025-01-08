import requests
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from .models import BaseModel

class ZteLLM(BaseModel):
    """ZTE Nebula LLM implementation"""
    
    def __init__(self, 
                 app_id: str,
                 app_key: str,
                 emp_no: str,
                 auth_value: str,
                 model: str = "nebulacoder",
                 ):
        """Initialize ZTE LLM with required credentials"""
        self.app_id = str(app_id)
        self.app_key = str(app_key)
        self.emp_no = str(emp_no)
        self.auth_value = str(auth_value)
        self.model = model
        self.base_url = "https://studio.zte.com.cn/zte-studio-ai-platform/openapi/v1"
        
    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make request to ZTE API"""
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.app_id}-{self.app_key}',
            'X-Emp-No': self.emp_no,
            'X-Auth-Value': self.auth_value
        }
        
        response = requests.post(
            f"{self.base_url}/{endpoint}",
            headers=headers,
            json=data
        )
        
        response.raise_for_status()
        result = response.json()
        
        if result["code"]["code"] != "0000":
            raise Exception(f"API Error: {result['code']['msg']}")
            
        return result["bo"]

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Chat with ZTE LLM"""
        # Convert messages to prompt
        prompt = self._convert_messages_to_prompt(messages)
        
        # Prepare data for API call
        data = {
            "chatUuid": "",
            "chatName": "",
            "stream": False,
            "keep": False,
            "text": prompt,
            "model": self.model
        }
        
        # If tools are provided, add them to the prompt
        if tools:
            tools_desc = "Available tools:\n\n" + json.dumps(tools, indent=2, ensure_ascii=False)
            data["text"] = tools_desc + "\n\n" + data["text"]
        
        try:
            result = self._make_request("chat", data)
            
            # Parse the response to extract potential tool calls
            response_text = result["result"]
            tool_calls = BaseModel.extract_tool_calls(response_text)
            
            return {
                "message": {
                    "content": response_text,
                    "tool_calls": tool_calls
                }
            }
            
        except Exception as e:
            raise Exception(f"ZTE LLM chat failed: {str(e)}")

    def _convert_messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert message list to a single prompt string"""
        prompt_parts = []
        
        for message in messages:
            role = message["role"]
            content = message.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            elif role == "tool":
                prompt_parts.append(f"Tool Result: {content}")
                
        return "\n\n".join(prompt_parts)


def create_zte_llm(model_name: str = "NebulaBiz") -> ZteLLM:
    """Create ZTE LLM instance with provided parameters"""
    # Load environment variables from file
    
    # Get credentials from parameters, env file, or system environment variables
    app_id = os.getenv('ZTE_APP_ID') 
    app_key = os.getenv('ZTE_APP_KEY') 
    emp_no = os.getenv('ZTE_EMP_NO') 
    auth_value = os.getenv('ZTE_AUTH_VALUE') 
    
    # Validate required credentials
    if not all([app_id, app_key, emp_no, auth_value]):
        raise ValueError(
            "Missing required credentials. Please provide through either:\n"
            "1. Function parameters\n"
            "2. ~/.jarvis_env file\n"
            "3. System environment variables\n\n"
            "Required variables: ZTE_APP_ID, ZTE_APP_KEY, ZTE_EMP_NO, ZTE_AUTH_VALUE"
        )
    
    return ZteLLM(
        app_id=app_id,
        app_key=app_key,
        emp_no=emp_no,
        auth_value=auth_value,
        model=model_name
    ) 