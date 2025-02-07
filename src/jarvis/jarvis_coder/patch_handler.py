import re
import os
from typing import List, Tuple, Dict

from jarvis.models.base import BasePlatform
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, while_success

class PatchHandler:
    def __init__(self):
        self.code_part_model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        self.code_part_model.set_system_message("""你是一个资深程序开发专家，你可以根据代码文件片段，生成修改计划，供大模型根据计划生成完整代码。生成修改计划的格式如下：
<PLAN>
> path/to/file
修改方法
</PLAN>
<PLAN>
> path/to/file
修改方法
</PLAN>
""")

    def _extract_full_code(self, response: str) -> str:
        """从响应中提取补丁
        
        Args:
            response: 模型响应内容
            
        Returns:
            List[Tuple[str, str, str]]: 补丁列表，每个补丁是 (格式, 文件路径, 补丁内容) 的元组
        """
        # 修改后的正则表达式匹配三种补丁格式
        fmt_pattern = r'<CODE>\n(.*?)\n</CODE>\n'
        match = re.search(fmt_pattern, response, re.DOTALL)
        if match:
            return match.group(1)
        return ""
    
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

    def make_code_raw_patch(self, related_files: List[Dict], modification_plan: str) -> Dict[str, str]:
        """生成修改方案"""
        prompt = f"# 修改方案：\n{modification_plan}\n# 相关文件："
        # 添加文件内容到提示
        for i, file in enumerate(related_files):
            if file["parts"]:
                prompt += f"""\n{i}. {file["file_path"]}\n"""
                prompt += f"""文件内容片段:\n"""
                for i, p in enumerate(file["parts"]):
                    prompt += f"<PART{i}>\n"
                    prompt += f'{p}\n'
                    prompt += f"</PART{i}>\n"

        # 调用模型生成代码片段
        response = self.code_part_model.chat_until_success(prompt)
        return self._extract_code(response)
    
    def merge_patch(self, file: str, complete_plan: str, curr_plan: str, model: BasePlatform) -> str:
        """合并补丁"""
        if os.path.exists(file):
            content = open(file, "r", encoding="utf-8").read()
        else:
            content = "<文件不存在，需要创建>"
        prompt = f"""\n# 完整修改方案：{complete_plan}\n# 当前修改文件路径:\n{file}\n# 当前文件内容：\n<CONTENT>{content}\n</CONTENT>\n# 当前文件修改方案:\n{curr_plan}"""
        PrettyOutput.print(f"为{file}生成格式化补丁...", OutputType.PROGRESS)
        response = model.chat_until_success(prompt)
        return self._extract_full_code(response)


    def _confirm_and_apply_changes(self, file_path: str) -> bool:
        """确认并应用修改"""
        os.system(f"git diff {file_path}")
        confirm = input(f"\n是否接受 {file_path} 的修改？(y/n) [y]: ").lower() or "y"
        if confirm == "y":
            return True
        else:
            # 回退修改
            os.system(f"git checkout -- {file_path}")
            PrettyOutput.print(f"已回退 {file_path} 的修改", OutputType.WARNING)
            return False

    def make_merge_model(self) -> BasePlatform:
        model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        model.set_system_message("""你是一个资深程序开发专家，你可以根据代码完整修改方案、当前要修改的原始代码文件路径、代码内容、当前文件的修改方案，生成修改后的新代码。需要输出的完整代码格式如下：
                                 <CODE>
                                 code
                                 </CODE>
                                 注意：需要生成完整的代码
                                 """)
        return model

    def apply_patch(self, complete_plan: str, patches_code: Dict[str, str]) -> Tuple[bool, str]:
        """应用补丁（主入口）"""
        error_info = []

        for file_path, code_list in patches_code.items():
            retry_count = 0
            additional_info = ""
            model = self.make_merge_model()
            
            while True:
                try:
                    if retry_count == 0:  # 首次调用生成格式化补丁
                        code_content = self.merge_patch(
                            file_path, complete_plan, code_list, model
                        )
                    else:  # 重试时直接生成新补丁
                        retry_prompt = f"""合并的修改有问题：
用户补充：{additional_info}
请生成新的补丁，特别注意代码匹配准确性"""
                        
                        response = model.chat_until_success(retry_prompt)
                        code_content = self._extract_full_code(response)
                        if not code_content:
                            return False, "生成补丁失败"
                
                except Exception as e:
                    error_info.append(f"生成补丁失败: {str(e)}")
                    return False, "\n".join(error_info)

                
                additional_info = ""
                
                open(file_path, "w", encoding="utf-8").write(code_content)
                
                if not self._confirm_and_apply_changes(file_path):
                    os.system(f"git reset --hard")
                    # 显示错误信息并询问用户操作
                    PrettyOutput.print(f"\n文件 {file_path} 补丁合并被拒绝", OutputType.WARNING)
                    
                    # 恢复用户选择逻辑
                    choice = input("\n请选择操作: (1) 重试 (2) 跳过 (3) 完全中止 [1]: ") or "1"
                    
                    if choice == "2":
                        PrettyOutput.print(f"跳过文件 {file_path}", OutputType.WARNING)
                        break
                    if choice == "3":
                        return False, "用户中止补丁应用"

                    additional_info = get_multiline_input("请输入补充说明和要求:")
                    retry_count += 1
                    continue  # 直接进入下一次循环生成新补丁

                else:
                    break
        
        return True, ""

    def handle_patch_feedback(self, error_msg: str) -> Dict[str, str]:
        """处理补丁应用失败的反馈
        
        Args:
            error_msg: 错误信息
            feature: 功能描述
            
        Returns:
            List[Tuple[str, str, str]]: 新的补丁列表
        """
        PrettyOutput.print("补丁应用失败，尝试重新生成", OutputType.WARNING)
        
        # 获取用户补充信息
        additional_info = input("\n请输入补充信息(直接回车跳过):")
        PrettyOutput.print(f"开始重新生成补丁", OutputType.INFO)
        
        # 构建重试提示
        retry_prompt = f"""补丁应用失败，请根据以下信息重新生成补丁：

错误信息：
{error_msg}

用户补充信息：
{additional_info}

请重新生成补丁，确保：
1. 代码匹配完全准确
2. 保持正确的缩进和格式
3. 避免之前的错误
"""
        response = self.code_part_model.chat_until_success(retry_prompt)
            
        try:
            patches = self._extract_code(response)
            return patches
            
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.WARNING)
            return {}

    def monitor_patch_result(self, success: bool, error_msg: str) -> bool:
        """监控补丁应用结果
        
        Args:
            success: 是否成功
            error_msg: 错误信息
            
        Returns:
            bool: 是否继续尝试
        """
        if success:
            PrettyOutput.print("补丁应用成功", OutputType.SUCCESS)
            return False
            
        PrettyOutput.print(f"补丁应用失败: {error_msg}", OutputType.WARNING)
        
        # 询问是否继续尝试
        retry = input("\n是否重新尝试？(y/n) [y]: ").lower() or "y"
        return retry == "y"

    def handle_patch_application(self, related_files: List[Dict], feature: str, modification_plan: str) -> bool:
        """处理补丁应用流程
        
        Args:
            related_files: 相关文件列表
            feature: 功能描述
            modification_plan: 修改方案
            
        Returns:
            bool: 是否成功应用补丁
        """
        
        PrettyOutput.print("开始生成补丁...", OutputType.PROGRESS)
        plans = self.make_code_raw_patch(related_files, modification_plan)
        while True:  # 在当前尝试中循环，直到成功或用户放弃
            # 1. 生成补丁
            if plans:
                # 2. 显示补丁内容
                PrettyOutput.print("\n将要应用以下修改方案:", OutputType.INFO)
                for file_path, patches_code in plans.items():
                    PrettyOutput.print(f"\n文件: {file_path}", OutputType.INFO)
                    PrettyOutput.print(f"修改方案: \n{patches_code}", OutputType.INFO)
                # 3. 应用补丁
                success, error_msg = self.apply_patch( modification_plan, plans)
                if not success:
                    # 4. 如果应用失败，询问是否重试
                    should_retry = self.monitor_patch_result(success, error_msg)
                    if not should_retry:
                        return False  # 用户选择不重试，直接返回失败
                        
                    # 5. 处理失败反馈
                    plans = self.handle_patch_feedback(error_msg)
                    continue
                # 6. 应用成功，让用户确认修改
                PrettyOutput.print("\n补丁已应用，请检查修改效果。", OutputType.SUCCESS)
                confirm = input("\n是否保留这些修改？(y/n) [y]: ").lower() or "y"
                if confirm != "y":
                    PrettyOutput.print("用户取消修改，正在回退", OutputType.WARNING)
                    os.system("git reset --hard")  # 回退所有修改
                else:
                    return True
            user_feed = get_multiline_input("请输入补充修改需求（直接回车结束）: ").strip()
            if not user_feed or user_feed == "__interrupt__":
                return False
            
            response = self.code_part_model.chat_until_success(user_feed)
            plans = self._extract_code(response)
            
