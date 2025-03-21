from abc import ABC, abstractmethod
import re
from typing import Dict, List, Tuple
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import ct, ot, get_context_token_count, while_success, while_true


class BasePlatform(ABC):
    """Base class for large language models"""
    
    def __init__(self):
        """Initialize model"""
        self.suppress_output = True  # 添加输出控制标志

    def __del__(self):
        """Destroy model"""
        self.delete_chat()

    @abstractmethod
    def set_model_name(self, model_name: str):
        """Set model name"""
        raise NotImplementedError("set_model_name is not implemented")
        
    @abstractmethod
    def chat(self, message: str) -> str:
        """Execute conversation"""
        raise NotImplementedError("chat is not implemented")

    def chat_until_success(self, message: str) -> str:
        def _chat():
            response = self.chat(message)
            # Keep original think tag handling
            response = re.sub(ot("think")+r'.*?'+ct("think"), '', response, flags=re.DOTALL)
            return response
                
        return while_true(lambda: while_success(lambda: _chat(), 5), 5)

    @abstractmethod
    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """Upload files"""
        raise NotImplementedError("upload_files is not implemented")

    @abstractmethod
    def reset(self):
        """Reset model"""
        raise NotImplementedError("reset is not implemented")
        
    @abstractmethod
    def name(self) -> str:
        """Model name"""
        raise NotImplementedError("name is not implemented")
    
    @abstractmethod
    def delete_chat(self)->bool:
        """Delete chat"""
        raise NotImplementedError("delete_chat is not implemented")
    
    @abstractmethod
    def set_system_message(self, message: str):
        """Set system message"""
        raise NotImplementedError("set_system_message is not implemented")
    
    @abstractmethod
    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        raise NotImplementedError("get_model_list is not implemented")

    def set_suppress_output(self, suppress: bool):
        """Set whether to suppress output"""
        self.suppress_output = suppress
