from typing import Tuple
import time
from jarvis.models.base import BasePlatform
from jarvis.utils import OutputType, PrettyOutput

def call_model_with_retry(model: BasePlatform, prompt: str, max_retries: int = 3, initial_delay: float = 1.0) -> Tuple[bool, str]:
    """调用模型并支持重试
    
    Args:
        model: 模型实例
        prompt: 提示词
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间(秒)
        
    Returns:
        Tuple[bool, str]: (是否成功, 响应内容)
    """
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            response = model.chat(prompt)
            return True, response
        except Exception as e:
            if attempt == max_retries - 1:  # 最后一次尝试
                PrettyOutput.print(f"调用模型失败: {str(e)}", OutputType.ERROR)
                return False, str(e)
                
            PrettyOutput.print(f"调用模型失败，{delay}秒后重试: {str(e)}", OutputType.WARNING)
            time.sleep(delay)
            delay *= 2  # 指数退避 