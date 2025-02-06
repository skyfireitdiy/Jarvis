import re
import os
from typing import List, Tuple, Dict

from click import prompt
from jarvis.models.base import BasePlatform
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, while_success

class PatchHandler:
    def __init__(self):
        self.code_part_model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
        self.code_part_model.set_system_message("""你是一个资深程序开发专家，你可以根据代码文件片段，需求和修改计划生成修改代码，供程序自动应用。生成代码的格式如下，可以生成多个修改片段：
<CODE>
> path/to/file
code
</CODE>
                                     
如：
<CODE>
> /src/a.cpp
// add function
// existing code
int add(int a, int b) {
    return a + b;
}
</CODE>""")

    def _extract_patches(self, response: str) -> List[Tuple[str, str, str]]:
        """从响应中提取补丁
        
        Args:
            response: 模型响应内容
            
        Returns:
            List[Tuple[str, str, str]]: 补丁列表，每个补丁是 (格式, 文件路径, 补丁内容) 的元组
        """
        patches = []
        
        # 修改后的正则表达式匹配三种补丁格式
        fmt_pattern = r'<PATCH_FMT(\d?)>\n?(.*?)\n?</PATCH_FMT\d?>\n?'
        
        for match in re.finditer(fmt_pattern, response, re.DOTALL):
            fmt_type = match.group(1) or "1"  # 默认FMT1
            patch_content = match.group(2).strip()
            
            # 提取文件路径和内容
            lines = patch_content.split('\n')
            if not lines:
                continue
                
            file_path_match = re.search(r'>\s*(.*)', lines[0])
            if not file_path_match:
                continue
                
            file_path = file_path_match.group(1).strip()
            
            # 处理不同格式
            if fmt_type == "3":
                # FMT3格式：文件删除
                if len(lines) < 2 or "CONFIRM_DELETE" not in lines[1]:
                    continue
                patches.append(("FMT3", file_path, "CONFIRM_DELETE"))
            elif fmt_type == "1":
                # FMT1格式：新旧内容分隔
                parts = '\n'.join(lines[1:]).split('@@@@@@')
                if len(parts) != 2:
                    continue
                old_content = parts[0].strip()
                new_content = parts[1].strip()
                patches.append(("FMT1", file_path, f"{old_content}\n@@@@@@\n{new_content}"))
            elif fmt_type == "2":
                # FMT2格式：全文件替换
                if not lines[1:]:  # 新增内容校验
                    continue
                full_content = '\n'.join(lines[1:]).strip()
                patches.append(("FMT2", file_path, full_content))

        return patches
    
    def _extract_code(self, response: str) -> Dict[str, List[str]]:
        """从响应中提取代码
        
        Args:
            response: 模型响应内容
            
        Returns:
            Dict[str, List[str]]: 代码字典，key为文件路径，value为代码片段列表
        """
        code_dict = {}
        for match in re.finditer(r'<CODE>\n> (.+?)\n(.*)\n</CODE>', response, re.DOTALL):
            file_path = match.group(1).strip()
            code_list = match.group(2).strip()
            code_dict[file_path] = code_list
        return code_dict

    def make_code_raw_patch(self, related_files: List[Dict], modification_plan: str) -> Dict[str, List[str]]:
        """生成修改方案"""
        prompt = f"# 修改方案：\n{modification_plan}\n# 相关文件："
        # 添加文件内容到提示
        for i, file in enumerate(related_files):
            prompt += f"""\n{i}. {file["file_path"]}\n"""
            prompt += f"""文件内容:\n"""
            prompt += f"<FILE_CONTENT>\n"
            prompt += f'{file["file_content"]}\n'
            prompt += f"</FILE_CONTENT>\n"

        # 调用模型生成代码片段
        response = while_success(lambda: self.code_part_model.chat(prompt), 5)
        return self._extract_code(response)
    
    def make_file_formatted_patch(self, file: str, plan: str, code_list: List[str], model: BasePlatform) -> List[Tuple[str, str, str]]:
        """生成文件补丁"""
        if os.path.exists(file):
            content = open(file, "r", encoding="utf-8").read()
        else:
            content = "<文件不存在，需要创建>"
        prompt = f"""文件路径:\n{file}\n文件内容：\n<CONTENT>{content}\n</CONTENT>\n要修改的代码片段:"""
        for code in code_list:
            prompt += f"\n<CODE>\n{code}\n</CODE>"
        PrettyOutput.print(f"为{file}生成格式化补丁...", OutputType.PROGRESS)
        response = while_success(lambda: model.chat(prompt), 5)
        return self._extract_patches(response)

    def _handle_fmt3_delete(self, patch_file_path: str, patch_content: str, temp_map: dict, modified_files: set) -> Tuple[bool, str]:
        """处理FMT3文件删除补丁"""
        if not os.path.exists(patch_file_path):
            return False, f"文件不存在无法删除: {patch_file_path}"
            
        # 安全检查
        if patch_content != "CONFIRM_DELETE":
            return False, f"删除确认标记缺失: {patch_file_path}"
            
        # 执行删除
        os.remove(patch_file_path)
        os.system(f"git rm {patch_file_path}")
        PrettyOutput.print(f"成功删除文件: {patch_file_path}", OutputType.SUCCESS)
        if patch_file_path in temp_map:
            del temp_map[patch_file_path]
        modified_files.add(patch_file_path)
        return True, ""

    def _handle_fmt2_full_replace(self, patch_file_path: str, patch_content: str, 
                                 temp_map: dict, modified_files: set) -> Tuple[bool, str]:
        """处理FMT2全文件替换补丁"""
        if not os.path.isabs(patch_file_path):
            patch_file_path = os.path.abspath(patch_file_path)
            
        if patch_file_path not in temp_map:
            # 新建文件
            try:
                os.makedirs(os.path.dirname(patch_file_path), exist_ok=True)
                with open(patch_file_path, "w", encoding="utf-8") as f:
                    f.write(patch_content)
                temp_map[patch_file_path] = patch_content
                modified_files.add(patch_file_path)
                return True, ""
            except Exception as e:
                return False, f"创建新文件失败 {patch_file_path}: {str(e)}"
                
        # 替换现有文件
        temp_map[patch_file_path] = patch_content
        modified_files.add(patch_file_path)
        return True, ""

    def _handle_fmt1_diff(self, patch_file_path: str, old_content: str, new_content: str,
                         temp_map: dict, modified_files: set) -> Tuple[bool, str]:
        """处理FMT1差异补丁"""
        if patch_file_path not in temp_map and not old_content.strip():
            # 处理新文件创建
            try:
                dir_path = os.path.dirname(patch_file_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                with open(patch_file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                os.system(f"git add {patch_file_path}")
                PrettyOutput.print(f"成功创建并添加文件: {patch_file_path}", OutputType.SUCCESS)
                modified_files.add(patch_file_path)
                temp_map[patch_file_path] = new_content
                return True, ""
            except Exception as e:
                return False, f"创建新文件失败 {patch_file_path}: {str(e)}"

        if patch_file_path not in temp_map:
            return False, f"文件不存在: {patch_file_path}"
            
        current_content = temp_map[patch_file_path]
        if old_content and old_content not in current_content:
            return False, (
                f"补丁应用失败: {patch_file_path}\n"
                f"原因: 未找到要替换的代码\n"
                f"期望找到的代码:\n{old_content}\n"
                f"实际文件内容:\n{current_content[:200]}..."
            )
            
        temp_map[patch_file_path] = current_content.replace(old_content, new_content)
        modified_files.add(patch_file_path)
        return True, ""

    def _apply_single_patch(self, fmt: str, patch_file_path: str, patch_content: str,
                           temp_map: dict, modified_files: set) -> Tuple[bool, str]:
        """应用单个补丁"""
        try:
            if fmt == "FMT3":
                return self._handle_fmt3_delete(patch_file_path, patch_content, temp_map, modified_files)
                
            elif fmt == "FMT2":
                return self._handle_fmt2_full_replace(patch_file_path, patch_content, temp_map, modified_files)
                
            elif fmt == "FMT1":
                parts = patch_content.split("@@@@@@")
                if len(parts) != 2:
                    return False, f"补丁格式错误: {patch_file_path}，缺少分隔符"
                old_content = parts[0].strip('\n')
                new_content = parts[1].strip('\n')
                return self._handle_fmt1_diff(patch_file_path, old_content, new_content, temp_map, modified_files)
                
            return False, f"未知的补丁格式: {fmt}"
        except Exception as e:
            return False, f"处理补丁时发生错误: {str(e)}"

    def _confirm_and_apply_changes(self, file_path: str, temp_map: dict, modified_files: set) -> bool:
        """确认并应用修改"""
        os.system(f"git diff {file_path}")
        confirm = input(f"\n是否接受 {file_path} 的修改？(y/n) [y]: ").lower() or "y"
        if confirm == "y":
            # 写入实际文件
            try:
                dir_path = os.path.dirname(file_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(temp_map[file_path])
                PrettyOutput.print(f"成功修改文件: {file_path}", OutputType.SUCCESS)
                return True
            except Exception as e:
                PrettyOutput.print(f"写入文件失败 {file_path}: {str(e)}", OutputType.WARNING)
                return False
        else:
            # 回退修改
            os.system(f"git checkout -- {file_path}")
            PrettyOutput.print(f"已回退 {file_path} 的修改", OutputType.WARNING)
            modified_files.discard(file_path)
            if file_path in temp_map:
                del temp_map[file_path]
            return False

    def apply_patch(self, related_files: List[Dict], plan: str, patches_code: Dict[str, List[str]]) -> Tuple[bool, str]:
        """应用补丁（主入口）"""
        error_info = []
        modified_files = set()
        file_map = {file["file_path"]: file["file_content"] for file in related_files}
        temp_map = file_map.copy()

        for file_path, code_list in patches_code.items():
            retry_count = 0
            original_code_list = code_list.copy()
            additional_info = ""
            error_details = ""
            model = PlatformRegistry.get_global_platform_registry().get_codegen_platform()
            model.set_system_message("""你是一个资深程序开发专家，你可以根据修改方案，要修改的代码文件，要修改代码的代码片段，生成给出代码片段的规范的补丁片段供程序自动应用。
补丁片段格式说明：
可选三种格式：
1. 差异模式（适合局部修改）：
<PATCH_FMT1>
> path/to/file
old_content
@@@@@@
new_content
</PATCH_FMT1>

2. 全文件模式（适合新建或完全重写）：
<PATCH_FMT2>
> path/to/new_file.py
def new_function():
    print("new code")
</PATCH_FMT2>

3. 删除文件模式：
<PATCH_FMT3>
> path/to/file_to_delete
CONFIRM_DELETE  # 必须包含此确认标记
</PATCH_FMT3>

注意事项：
1、仅输出补丁内容，不要输出任何其他内容
2、如果在大段代码中有零星修改，生成多个补丁
3、要替换的内容，一定要与文件内容完全一致（**包括缩进与空白**），不要有任何多余或者缺失的内容
4、务必保留原始文件的缩进和格式
5、对于新文件，不需要写old_content部分
6、删除文件时必须包含CONFIRM_DELETE确认标记
7、给出的代码是修改的一部分，不用关注除本文件以外的修改""")

            while True:
                try:
                    if retry_count == 0:  # 首次调用生成格式化补丁
                        patches = self.make_file_formatted_patch(
                            file_path, plan, original_code_list, model
                        )
                        initial_patches = patches  # 保存初始补丁
                    else:  # 重试时直接生成新补丁
                        # 构建重试提示
                        original_code_str = '\n'.join(original_code_list)
                        retry_prompt = f"""根据以下信息重新生成补丁：
原始需求：{plan}
错误信息：{error_details}
用户补充：{additional_info}
原始代码片段：
{original_code_str}
请生成新的补丁，特别注意代码匹配准确性"""
                        
                        response = while_success(lambda: model.chat(retry_prompt), 5)
                        patches = self._extract_patches(response)
                
                except Exception as e:
                    error_info.append(f"生成补丁失败: {str(e)}")
                    return False, "\n".join(error_info)

                # 处理当前文件的所有补丁
                file_success = True
                current_errors = []
                for fmt, patch_file_path, patch_content in patches:
                    success, msg = self._apply_single_patch(fmt, patch_file_path, patch_content, temp_map, modified_files)
                    if not success:
                        current_errors.append(msg)
                        file_success = False
                
                if not file_success:
                    # 显示错误信息并询问用户操作
                    PrettyOutput.print(f"\n文件 {file_path} 补丁应用失败:", OutputType.WARNING)
                    PrettyOutput.print("\n".join(current_errors), OutputType.WARNING)
                    
                    # 恢复用户选择逻辑
                    choice = input("\n请选择操作: (1) 重试 (2) 补充信息后重试 (3) 跳过 (4) 完全中止 [1]: ") or "1"
                    
                    if choice == "3":
                        PrettyOutput.print(f"跳过文件 {file_path}", OutputType.WARNING)
                        break
                    if choice == "4":
                        return False, "用户中止补丁应用"
                    
                    # 处理补充信息
                    if choice == "2":
                        additional_info = get_multiline_input("请输入补充说明和要求:")
                        retry_count += 1
                        continue  # 直接进入下一次循环生成新补丁
                    
                    # 选择1直接重试
                    retry_count += 1
                    continue

                # 确认修改
                if self._confirm_and_apply_changes(file_path, temp_map, modified_files):
                    break
                else:
                    continue

        # 所有文件处理完成后写入实际文件
        for file_path in modified_files:
            try:
                dir_path = os.path.dirname(file_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(temp_map[file_path])
                    
                PrettyOutput.print(f"成功修改文件: {file_path}", OutputType.SUCCESS)
                
            except Exception as e:
                error_info.append(f"写入文件失败 {file_path}: {str(e)}")
                return False, "\n".join(error_info)
        
        return True, ""

    def handle_patch_feedback(self, error_msg: str, feature: str) -> Dict[str, List[str]]:
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

原始需求：
{feature}

用户补充信息：
{additional_info}

请重新生成补丁，确保：
1. 代码匹配完全准确
2. 保持正确的缩进和格式
3. 避免之前的错误
"""
        response = while_success(lambda: self.code_part_model.chat(retry_prompt), 5)
            
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
        
        while True:
            PrettyOutput.print("开始生成补丁...", OutputType.PROGRESS)
            patches = self.make_code_raw_patch(related_files, modification_plan)
            while True:  # 在当前尝试中循环，直到成功或用户放弃
                # 1. 生成补丁
                if patches:
                    # 2. 显示补丁内容
                    PrettyOutput.print("\n将要应用以下补丁:", OutputType.INFO)
                    for file_path, patches_code in patches.items():
                        PrettyOutput.print(f"\n文件: {file_path}", OutputType.INFO)
                        for i, code_part in enumerate(patches_code):
                            PrettyOutput.print(f"片段{i}: \n{code_part}", OutputType.INFO)
                    # 3. 应用补丁
                    success, error_msg = self.apply_patch(related_files, modification_plan, patches)
                    if not success:
                        # 4. 如果应用失败，询问是否重试
                        should_retry = self.monitor_patch_result(success, error_msg)
                        if not should_retry:
                            return False  # 用户选择不重试，直接返回失败
                            
                        # 5. 处理失败反馈
                        patches = self.handle_patch_feedback(error_msg, modification_plan)
                        continue
                    # 6. 应用成功，让用户确认修改
                    PrettyOutput.print("\n补丁已应用，请检查修改效果。", OutputType.SUCCESS)
                    confirm = input("\n是否保留这些修改？(y/n) [y]: ").lower() or "y"
                    if confirm != "y":
                        PrettyOutput.print("用户取消修改，正在回退", OutputType.WARNING)
                        os.system("git reset --hard")  # 回退所有修改
                user_feed = get_multiline_input("请输入补充修改需求（直接回车结束）: ").strip()
                if not user_feed or user_feed == "__interrupt__":
                    return True
                
                response = while_success(lambda: self.code_part_model.chat(user_feed), 5)
                patches = self._extract_code(response)
                
                continue  # 回到外层循环重新开始补丁生成流程