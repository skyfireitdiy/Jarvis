from abc import ABC, abstractmethod
from typing import Dict, List


class BasePlatform(ABC):
    """大语言模型基类"""
    
    def __init__(self):
        """初始化模型"""
        self.suppress_output = False  # 添加输出控制标志
        pass

    def set_model_name(self, model_name: str):
        """设置模型名称"""
        raise NotImplementedError("set_model_name is not implemented")
        
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
    
    def set_system_message(self, message: str):
        """设置系统消息"""
        raise NotImplementedError("set_system_message is not implemented")

    def set_suppress_output(self, suppress: bool):
        """设置是否屏蔽输出
        
        Args:
            suppress: 是否屏蔽输出
        """
        self.suppress_output = suppress
