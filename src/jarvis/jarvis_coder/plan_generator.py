import re
from typing import Dict, List, Tuple
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input

class PlanGenerator:
    """修改方案生成器"""
    
    def _build_prompt(self, feature: str, related_files: List[Dict], additional_info: str) -> str:
        """构建提示词
        
        Args:
            feature: 功能描述
            related_files: 相关文件列表
            additional_info: 用户补充信息
            
        Returns:
            str: 完整的提示词
        """
        prompt = "You are a code modification expert who can generate modification plans based on requirements and relevant code snippets. I need your help to analyze how to implement the following feature:\n\n"
        prompt += f"{feature}\n\n"
                
        prompt += "Here are the relevant code file snippets:\n\n"
        
        for file in related_files:
            prompt += f"File: {file['file_path']}\n"
            for part in file["parts"]:
                prompt += f"<PART>\n{part}\n</PART>\n"
        
        prompt += "\nPlease provide detailed modifications needed to implement this feature. Include:\n"
        prompt += "1. Which files need to be modified\n"
        prompt += "2. How to modify each file, no explanation needed\n"
        prompt += "3. Don't assume other files or code exist, only generate modification plans based on provided file contents and description\n"
        prompt += "4. Don't implement features outside the requirement\n"
        prompt += "5. Output only one modification plan per file (can be multiple lines)\n"
        prompt += "6. Output format as follows:\n"
        prompt += "<PLAN>\n"
        prompt += "> path/to/file1\n"
        prompt += "modification plan\n"
        prompt += "</PLAN>\n"
        prompt += "<PLAN>\n"
        prompt += "> path/to/file2\n"
        prompt += "modification plan\n"
        prompt += "</PLAN>\n"
        if additional_info:
            prompt += f"# Additional information:\n{additional_info}\n"
        
        return prompt
    
    
    def generate_plan(self, feature: str, related_files: List[Dict]) -> Tuple[str, Dict[str,str]]:
        """生成修改方案
        
        Args:
            feature: 功能描述
            related_files: 相关文件列表
            
        Returns:
            Tuple[str, Dict[str,str]]: 修改方案，如果用户取消则返回 None
        """
        additional_info = ""
        while True:
            prompt = self._build_prompt(feature, related_files, additional_info)
            # 构建提示词
            PrettyOutput.print("开始生成修改方案...", OutputType.PROGRESS)
            
            # 获取修改方案
            raw_plan = PlatformRegistry.get_global_platform_registry().get_thinking_platform().chat_until_success(prompt)
            structed_plan = self._extract_code(raw_plan)
            if not structed_plan:
                PrettyOutput.print("修改方案生成失败，请重试", OutputType.ERROR)
                tmp = get_multiline_input("请输入您的补充意见或建议（直接回车取消）:")
                if tmp == "__interrupt__" or prompt == "":
                    return "", {}
                additional_info += tmp + "\n"
                continue
            user_input = input("\n是否同意这个修改方案？(y/n) [y]: ").strip().lower() or 'y'
            if user_input == 'y' or user_input == '':
                return raw_plan, structed_plan
            elif user_input == 'n':
                # 获取用户反馈
                tmp = get_multiline_input("请输入您的补充意见或建议（直接回车取消）:")
                if prompt == "__interrupt__" or prompt == "":
                    return "", {}
                additional_info += tmp + "\n"
                continue 

    
    def _extract_code(self, response: str) -> Dict[str, str]:
        """从响应中提取代码
        
        Args:
            response: 模型响应内容
            
        Returns:
            Dict[str, List[str]]: 代码字典，key为文件路径，value为代码片段列表
        """
        code_dict = {}
        for match in re.finditer(r'<PLAN>\n> (.+?)\n(.*?)\n</PLAN>', response, re.DOTALL):
            file_path = match.group(1)
            code_part = match.group(2)
            code_dict[file_path] = code_part
        return code_dict