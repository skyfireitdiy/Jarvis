from abc import ABC, abstractmethod
import re
from typing import Dict, List, Tuple

from jarvis.jarvis_utils import OutputType, PrettyOutput, while_success, while_true
from yaspin import yaspin
from yaspin.spinners import Spinners


class BasePlatform(ABC):
    """Base class for large language models"""
    
    def __init__(self):
        """Initialize model"""
        self.suppress_output = False  # 添加输出控制标志

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
            import time
            start_time = time.time()
            
            if self.suppress_output:
                with yaspin(Spinners.dots, text="Thinking", color="yellow") as spinner:
                    response = self.chat(message)
                    spinner.ok("✓")
            else:
                response = self.chat(message)
            
            # Calculate statistics
            end_time = time.time()
            duration = end_time - start_time
            char_count = len(response)
            
            # Print statistics
            PrettyOutput.print(f"对话完成 - 耗时: {duration:.2f}秒, 输出字符数: {char_count}", OutputType.INFO)
            
            # Keep original think tag handling
            response = re.sub(r'', '', response, flags=re.DOTALL)
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
