import re
import os
from typing import List, Tuple, Dict

from jarvis.models.base import BasePlatform
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, while_success

class Patch:
    def __init__(self, old_code: str, new_code: str):
        self.old_code = old_code
        self.new_code = new_code

class PatchHandler:


    def _extract_patches(self, response: str) -> List[Patch]:
        """从响应中提取补丁
        
        Args:
            response: 模型响应内容
            
        Returns:
            List[Tuple[str, str, str]]: 补丁列表，每个补丁是 (格式, 文件路径, 补丁内容) 的元组
        """
        # 修改后的正则表达式匹配三种补丁格式
        fmt_pattern = r'<PATCH>\n>>>>>> SEARCH\n(.*?)\n?(={5,})\n(.*?)\n?<<<<<< REPLACE\n</PATCH>'
        ret = []
        for m in re.finditer(fmt_pattern, response, re.DOTALL):
            ret.append(Patch(m.group(1), m.group(3)))   
        return ret


    def _confirm_and_apply_changes(self, file_path: str) -> bool:
        """确认并应用修改"""
        os.system(f"git diff --cached {file_path}")
        confirm = input(f"\n是否接受 {file_path} 的修改？(y/n) [y]: ").lower() or "y"
        if confirm == "y":
            return True
        else:
            # 回退修改
            os.system(f"git reset {file_path}")
            os.system(f"git checkout -- {file_path}")
            PrettyOutput.print(f"已回退 {file_path} 的修改", OutputType.WARNING)
            return False

    
    def apply_file_patch(self, file_path: str, patches: List[Patch]) -> bool:
        """应用文件补丁"""
        if not os.path.exists(file_path):
            base_dir = os.path.dirname(file_path)
            os.makedirs(base_dir, exist_ok=True)
            open(file_path, "w", encoding="utf-8").close()
        file_content = open(file_path, "r", encoding="utf-8").read()
        for i, patch in enumerate(patches):
            if patch.old_code == "" and patch.new_code == "":
                PrettyOutput.print(f"应用第 {i+1}/{len(patches)} 个补丁：删除文件 {file_path}", OutputType.INFO)
                file_content = ""
                os.system(f"git rm {file_path}")
                PrettyOutput.print(f"应用第 {i+1}/{len(patches)} 个补丁成功", OutputType.SUCCESS)
            elif patch.old_code == "":
                PrettyOutput.print(f"应用第 {i+1}/{len(patches)} 个补丁：替换文件 {file_path} 内容：\n{patch.new_code}", OutputType.INFO)
                file_content = patch.new_code
                open(file_path, "w", encoding="utf-8").write(patch.new_code)
                os.system(f"git add {file_path}")
                PrettyOutput.print(f"应用第 {i+1}/{len(patches)} 个补丁成功", OutputType.SUCCESS)
            else:
                PrettyOutput.print(f"应用第 {i+1}/{len(patches)} 个补丁：文件原始内容：\n{patch.old_code}\n替换为：\n{patch.new_code}", OutputType.INFO)
                if file_content.find(patch.old_code) == -1:
                    PrettyOutput.print(f"文件 {file_path} 中不存在 {patch.old_code}", OutputType.WARNING)
                    os.system(f"git reset {file_path}")
                    os.system(f"git checkout -- {file_path}")
                    return False
                else:
                    file_content = file_content.replace(patch.old_code, patch.new_code, 1)
                    open(file_path, "w", encoding="utf-8").write(file_content)
                    os.system(f"git add {file_path}")
                    PrettyOutput.print(f"应用第 {i+1}/{len(patches)} 个补丁成功", OutputType.SUCCESS)
        return True
            
    
    def retry_comfirm(self) -> Tuple[str, str]:# 恢复用户选择逻辑
        choice = input("\n请选择操作: (1) 重试 (2) 跳过 (3) 完全中止 [1]: ") or "1"
        if choice == "2":
            return "skip", ""
        if choice == "3":
            return "break", ""
        return "continue", get_multiline_input("请输入补充说明和要求:")

    def apply_patch(self, feature: str, raw_plan: str, structed_plan: Dict[str, str]) -> Tuple[bool, str]:
        """应用补丁（主入口）"""
        for file_path, current_plan in structed_plan.items():
            additional_info = ""            
            while True:
                
                if os.path.exists(file_path):
                    content = open(file_path, "r", encoding="utf-8").read()
                else:
                    content = "<文件不存在，需要创建>"
                prompt = """你是一个资深程序开发专家，你可以根据代码完整修改方案、当前要修改的原始代码文件路径、代码内容、当前文件的修改方案，生成修改后的代码补丁。需要输出的格式如下：
                        <PATCH>
                        >>>>>> SEARCH
                        old_code
                        ======
                        new_code
                        <<<<<< REPLACE
                        </PATCH>
                        规则：
                        1. 当old_code为空时，表示从开头到结尾全部替换
                        2. 当new_code为空时，表示删除old_code
                        3. 当old_code和new_code都为空时，表示删除文件
                        注意：
                        1. 可生成多个补丁
                        2. old code的代码会被替换为new code的代码，注意上下文衔接
                        3. 生成补丁要避免破坏现有代码逻辑，比如：在现有函数体内部插入函数定义破坏已有代码
                        4. 带有足够的上下文，避免歧义
                        5. 补丁将以 file_content.replace(patch.old_code, patch.new_code, 1) 的方式合并，因此补丁的old_code和new_code需要精确匹配，old_code中的空行、换行、空白、制表符、注释都需要保持一致
                        6. 确保生成的代码格式正确（语法、缩进、换行）
                        7. 确保new_code的缩进、格式与old_code一致
                        8. 确保代码被插入到合适的位置，如使用变量的代码要在声明/定义之后
                        9. 修改的代码前后至少提供3行供定位


                        """
                prompt += f"""# 原始需求：{feature}
                    # 完整修改计划：{raw_plan}
                    # 当前修改文件路径:{file_path}
                    # 当前文件内容：
                    <CONTENT>
                    {content}
                    </CONTENT>
                    # 当前文件修改计划:
                    {current_plan}
                    { "# 补充信息：" + additional_info if additional_info else "" }
                    """


                PrettyOutput.print(f"为{file_path}生成格式化补丁...", OutputType.PROGRESS)
                response = PlatformRegistry.get_global_platform_registry().get_codegen_platform().chat_until_success(prompt)
                patches = self._extract_patches(response)

                if not patches or not self.apply_file_patch(file_path, patches) or not self._confirm_and_apply_changes(file_path):
                    os.system(f"git reset {file_path}")
                    os.system(f"git checkout -- {file_path}")
                    PrettyOutput.print("补丁生成失败", OutputType.WARNING)
                    act, msg = self.retry_comfirm()
                    if act == "break":
                        PrettyOutput.print("终止补丁应用", OutputType.WARNING)
                        return False, msg
                    if act == "skip":
                        PrettyOutput.print(f"跳过文件 {file_path}", OutputType.WARNING)
                        break
                    else:
                        additional_info += msg + "\n"
                        continue
                else:
                    break
        
        return True, ""



    def handle_patch_application(self, feature: str, raw_plan: str, structed_plan: Dict[str,str]) -> bool:
        """处理补丁应用流程
        
        Args:
            related_files: 相关文件列表
            feature: 功能描述
            modification_plan: 修改方案
            
        Returns:
            bool: 是否成功应用补丁
        """
        PrettyOutput.print("\n将要应用以下修改方案:", OutputType.INFO)
        for file_path, patches_code in structed_plan.items():
            PrettyOutput.print(f"\n文件: {file_path}", OutputType.INFO)
            PrettyOutput.print(f"修改方案: \n{patches_code}", OutputType.INFO)
        # 3. 应用补丁
        success, error_msg = self.apply_patch(feature, raw_plan, structed_plan)
        if not success:
            os.system("git reset --hard")
            return False
        # 6. 应用成功，让用户确认修改
        PrettyOutput.print("\n补丁已应用，请检查修改效果。", OutputType.SUCCESS)
        confirm = input("\n是否保留这些修改？(y/n) [y]: ").lower() or "y"
        if confirm != "y":
            PrettyOutput.print("用户取消修改，正在回退", OutputType.WARNING)
            os.system("git reset --hard")  # 回退所有修改
            return False
        else:
            return True
            
