from abc import ABC, abstractmethod
from typing import Callable, Dict, List

class BaseModel(ABC):
    """大语言模型基类"""
    
    @abstractmethod
    def chat(self, message: str) -> str:
        """执行对话"""
        raise NotImplementedError("chat is not implemented")

    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """上传文件"""
        raise NotImplementedError("upload_files is not implemented")

    def reset(self):
        """重置模型"""
        raise NotImplementedError("reset is not implemented")
        
    @abstractmethod
    def name(self) -> str:
        """模型名称"""
        raise NotImplementedError("name is not implemented")
    
    @abstractmethod
    def delete_chat(self)->bool:
        """删除对话"""
        raise NotImplementedError("delete_chat is not implemented")
    
global_model_create_func = None

def set_global_model(model_create_func: Callable[[], BaseModel]):
    global global_model_create_func
    global_model_create_func = model_create_func

def get_global_model() -> BaseModel:
    if global_model_create_func is None:
        raise Exception("global_model_create_func is not set")
    return global_model_create_func()
