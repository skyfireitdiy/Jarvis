from typing import Dict, List, Optional
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, while_success
from jarvis.models.base import BasePlatform

class PlanGenerator:
    """修改方案生成器"""
    
    def __init__(self):
        """初始化
        
        Args:
            thinking_model: 用于思考的大模型
        """
        self.thinking_model = PlatformRegistry.get_global_platform_registry().get_thinking_platform()
    
    def _build_prompt(self, feature: str, related_files: List[Dict]) -> str:
        """构建提示词
        
        Args:
            feature: 功能描述
            related_files: 相关文件列表
            user_feedback: 用户反馈信息
            
        Returns:
            str: 完整的提示词
        """
        prompt = "我需要你帮我分析如何实现以下功能:\n\n"
        prompt += f"{feature}\n\n"
                
        prompt += "以下是相关的代码文件片段:\n\n"
        
        for file in related_files:
            prompt += f"文件: {file['file_path']}\n"
            for part in file["parts"]:
                prompt += f"<PART>\n{part}\n</PART>\n"
        
        prompt += "\n请详细说明需要做哪些修改来实现这个功能。包括:\n"
        prompt += "1. 需要修改哪些文件\n"
        prompt += "2. 每个文件需要做什么修改\n"
        prompt += "3. 修改的主要逻辑和原因\n"
        prompt += "4. 不要生成具体的代码，只需要生成修改方案\n"
        
        return prompt
    
    def generate_plan(self, feature: str, related_files: List[Dict]) -> str:
        """生成修改方案
        
        Args:
            feature: 功能描述
            related_files: 相关文件列表
            
        Returns:
            str: 修改方案，如果用户取消则返回 None
        """
        prompt = self._build_prompt(feature, related_files)
        while True:
            # 构建提示词
            PrettyOutput.print("开始生成修改方案...", OutputType.PROGRESS)
            
            # 获取修改方案
            plan = while_success(lambda: self.thinking_model.chat(prompt), 5)
            
            user_input = input("\n是否同意这个修改方案？(y/n/f) [y]: ").strip().lower() or 'y'
            if user_input == 'y':
                return plan
            elif user_input == 'n':
                return ""
            else:  # 'f' - feedback
                # 获取用户反馈
                prompt = get_multiline_input("请输入您的补充意见或建议:")
                if prompt == "__interrupt__":
                    return ""
                prompt = f"用户补充反馈：\n{prompt}\n\n请重新生成完整方案"
                continue 