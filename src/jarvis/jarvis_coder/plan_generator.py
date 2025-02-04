from typing import Dict, List
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input
from jarvis.models.base import BasePlatform

class PlanGenerator:
    """修改方案生成器"""
    
    def __init__(self, thinking_model: BasePlatform):
        """初始化
        
        Args:
            thinking_model: 用于思考的大模型
        """
        self.thinking_model = thinking_model
    
    def _build_prompt(self, feature: str, related_files: List[Dict], user_feedback: str = None) -> str:
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
        
        # 如果有用户反馈，添加到提示中
        if user_feedback:
            prompt += "用户对之前的方案有以下补充意见：\n"
            prompt += f"{user_feedback}\n\n"
        
        prompt += "以下是相关的代码文件:\n\n"
        
        for file in related_files:
            prompt += f"文件: {file['file_path']}\n```\n{file['file_content']}\n```\n\n"
        
        prompt += "\n请详细说明需要做哪些修改来实现这个功能。包括:\n"
        prompt += "1. 需要修改哪些文件\n"
        prompt += "2. 每个文件需要做什么修改\n"
        prompt += "3. 修改的主要逻辑和原因\n"
        
        return prompt
    
    def generate_plan(self, feature: str, related_files: List[Dict]) -> str:
        """生成修改方案
        
        Args:
            feature: 功能描述
            related_files: 相关文件列表
            
        Returns:
            str: 修改方案，如果用户取消则返回 None
        """
        user_feedback = None
        
        while True:
            # 构建提示词
            prompt = self._build_prompt(feature, related_files, user_feedback)

            PrettyOutput.print("开始生成修改方案...", OutputType.PLANNING)
            
            # 获取修改方案
            plan = self.thinking_model.chat(prompt)
            
            # 显示修改方案并获取用户确认
            PrettyOutput.section("修改方案", OutputType.PLANNING)
            PrettyOutput.print(plan, OutputType.PLANNING)
            
            user_input = input("\n是否同意这个修改方案？(y/n/f) [y]: ").strip().lower() or 'y'
            if user_input == 'y':
                return plan
            elif user_input == 'n':
                return None
            else:  # 'f' - feedback
                # 获取用户反馈
                PrettyOutput.print("\n请输入您的补充意见或建议:", OutputType.INFO)
                user_feedback = get_multiline_input("")
                if user_feedback == "__interrupt__":
                    return None
                continue 