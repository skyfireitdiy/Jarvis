import re
from typing import Dict, List, Tuple
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, get_multiline_input, get_single_line_input, is_long_context

class PlanGenerator:
    """Modification plan generator"""   
    
    def _build_prompt(self, feature: str, related_files: List[Dict], additional_info: str) -> str:
        """Build prompt
        
        Args:
            feature: Feature description
            related_files: Related files list
            additional_info: User supplement information
            
        Returns:
            str: Complete prompt
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
    
    
    @staticmethod
    def get_key_code(files: List[str], feature: str)->List[Dict[str, List[str]]]:
        """Extract relevant key code snippets from files"""
        ret = []
        for file in files:
            PrettyOutput.print(f"Analyzing file: {file}", OutputType.INFO)
            model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
            model.set_suppress_output(True)
            file_path = file
            content = open(file_path, "r", encoding="utf-8").read()

            try:
                prompt = f"""You are a code analysis expert who can extract relevant snippets from code.
Please return in the following format:
<PART>
content
</PART>

Multiple snippets can be returned. If the file content is not relevant to the requirement, return empty.

Requirement: {feature}
File path: {file_path}
Code content:
{content}
"""

                # 调用大模型进行分析
                response = model.chat_until_success(prompt)

                parts = re.findall(r'<PART>\n(.*?)\n</PART>', response, re.DOTALL)
                ret.append({"file_path": file, "parts": parts})
            except Exception as e:
                PrettyOutput.print(f"Failed to analyze file: {str(e)}", OutputType.ERROR)
        return ret
    
    def generate_plan(self, feature: str, related_files: List[str]) -> Dict[str,str]:
        """Generate modification plan
        
        Args:
            feature: Feature description
            related_files: Related files list
            
        Returns:
            Tuple[str, Dict[str,str]]: Modification plan, return None if user cancels
        """
        additional_info = ""
        file_info = []
        if is_long_context(related_files):
            file_info =  PlanGenerator.get_key_code(related_files, feature)
        else:
            for file in related_files:
                file_info.append({"file_path": file, "parts": [open(file, "r", encoding="utf-8").read()]})

        while True:
            prompt = self._build_prompt(feature, file_info, additional_info)
            # Build prompt
            PrettyOutput.print("Start generating modification plan...", OutputType.PROGRESS)
            
            # Get modification plan
            raw_plan = PlatformRegistry.get_global_platform_registry().get_thinking_platform().chat_until_success(prompt)
            structed_plan = self._extract_code(raw_plan)
            if not structed_plan:
                PrettyOutput.print("Modification plan generation failed, please try again", OutputType.ERROR)
                tmp = get_multiline_input("Please enter your additional information or suggestions (press Enter to cancel):")
                if tmp == "__interrupt__" or prompt == "":
                    return {}
                additional_info += tmp + "\n"
                continue
            user_input = get_single_line_input("Do you agree with this modification plan? (y/n) [y]").strip().lower() or 'y'
            if user_input == 'y' or user_input == '':
                return structed_plan
            elif user_input == 'n':
                # Get user feedback
                tmp = get_multiline_input("Please enter your additional information or suggestions (press Enter to cancel):")
                if prompt == "__interrupt__" or prompt == "":
                    return {}
                additional_info += tmp + "\n"
                continue 

    
    def _extract_code(self, response: str) -> Dict[str, str]:
        """Extract code from response
        
        Args:
            response: Model response content
            
        Returns:
            Dict[str, List[str]]: Code dictionary, key is file path, value is code snippet list
        """
        code_dict = {}
        for match in re.finditer(r'<PLAN>\n> (.+?)\n(.*?)\n</PLAN>', response, re.DOTALL):
            file_path = match.group(1)
            code_part = match.group(2)
            code_dict[file_path] = code_part
        return code_dict