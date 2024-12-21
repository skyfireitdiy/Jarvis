import requests
from typing import Dict, Any
from .base import BaseLLM

class ZteLLM(BaseLLM):
    """ZTE Nebula LLM implementation"""
    
    def __init__(self, 
                 app_id: str,
                 app_key: str,
                 emp_no: str,
                 auth_value: str,
                 model: str = "nebulacoder",
                 **kwargs):
        """Initialize ZTE LLM with required credentials"""
        super().__init__(f"zte-{model}", **kwargs)
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
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Get completion from ZTE LLM"""
        data = {
            "chatUuid": "",
            "chatName": "",
            "stream": False,
            "keep": False,
            "text": prompt,
            "model": self.model
        }
        
        result = self._make_request("chat", data)
        return result["result"]
    
    def get_model_name(self) -> str:
        """Get the name of the current model"""
        return f"zte-{self.model}"

def create_llm(**kwargs) -> ZteLLM:
    """Create ZTE LLM instance with provided parameters"""
    import os
    
    # Get credentials from parameters or environment variables
    app_id = kwargs.pop('app_id', None) or os.getenv('ZTE_APP_ID')
    app_key = kwargs.pop('app_key', None) or os.getenv('ZTE_APP_KEY')
    emp_no = kwargs.pop('emp_no', None) or os.getenv('ZTE_EMP_NO')
    auth_value = kwargs.pop('auth_value', None) or os.getenv('ZTE_AUTH_VALUE')
    
    # Validate required credentials
    if not all([app_id, app_key, emp_no, auth_value]):
        raise ValueError(
            "Missing required credentials. Please provide either through parameters "
            "or environment variables (ZTE_APP_ID, ZTE_APP_KEY, ZTE_EMP_NO, ZTE_AUTH_VALUE)"
        )
    
    return ZteLLM(
        app_id=app_id,
        app_key=app_key,
        emp_no=emp_no,
        auth_value=auth_value,
        **kwargs
    ) 