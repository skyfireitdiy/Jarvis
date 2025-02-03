import re
import os
from typing import List, Tuple, Dict
from jarvis.utils import OutputType, PrettyOutput
from .model_utils import call_model_with_retry

class PatchHandler:
    def __init__(self, model):
        self.model = model

    def make_patch(self, related_files: List[Dict], feature: str) -> List[Tuple[str, str, str]]:
        """生成修改方案"""
        prompt = """你是一个资深程序员，请根据需求描述，修改文件内容。

修改格式说明：
1. 第一种格式 - 完整代码块替换：
<PATCH_FMT1>
> path/to/file
def old_function():
    print("old code")
    return False
@@@@@@
def old_function():
    print("new code")
    return True
</PATCH_FMT1>

2. 第二种格式 - 通过首尾行定位：
<PATCH_FMT2>
> path/to/file
    def old_function():  # 第一行内容
    return False  # 最后一行内容
    def new_function():
        print("new code")
        return True
</PATCH_FMT2>

注意事项：
1、仅输出补丁内容，不要输出任何其他内容
2、如果在大段代码中有零星修改，生成多个补丁
3、要替换的内容，一定要与文件内容完全一致，不要有任何多余或者缺失的内容
4、每个patch不超过20行，超出20行，请生成多个patch
5、务必保留原始文件的缩进和格式
6、优先使用第二种格式（PATCH_FMT2）
7、如果第二种格式无法定位到要修改的代码或者有歧义，请使用第一种格式（PATCH_FMT1）
"""
        # ... (其余代码保持不变)

    def apply_patch(self, related_files: List[Dict], patches: List[Tuple[str, str, str]]) -> Tuple[bool, str]:
        """应用补丁
        
        Args:
            related_files: 相关文件列表
            patches: 补丁列表，每个补丁是 (格式, 文件路径, 补丁内容) 的元组
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        error_info = []
        modified_files = set()

        # 创建文件内容映射
        file_map = {file["file_path"]: file["file_content"] for file in related_files}
        temp_map = file_map.copy()  # 创建临时映射用于尝试应用
        
        # 尝试应用所有补丁
        for i, (fmt, file_path, patch_content) in enumerate(patches):
            PrettyOutput.print(f"正在应用补丁 {i+1}/{len(patches)}", OutputType.INFO)
            
            try:
                # 处理文件修改
                if file_path not in temp_map:
                    error_info.append(f"文件不存在: {file_path}")
                    return False, "\n".join(error_info)
                
                current_content = temp_map[file_path]
                
                if fmt == "FMT1":  # 完整代码块替换格式
                    parts = patch_content.split("@@@@@@")
                    if len(parts) != 2:
                        error_info.append(f"FMT1补丁格式错误: {file_path}，缺少分隔符")
                        return False, "\n".join(error_info)
                        
                    old_content, new_content = parts
                    
                    # 处理新文件
                    if not old_content:
                        temp_map[file_path] = new_content
                        modified_files.add(file_path)
                        continue
                    
                    # 查找并替换代码块
                    if old_content not in current_content:
                        error_info.append(
                            f"补丁应用失败: {file_path}\n"
                            f"原因: 未找到要替换的代码\n"
                            f"期望找到的代码:\n{old_content}\n"
                            f"实际文件内容:\n{current_content[:200]}..."
                        )
                        return False, "\n".join(error_info)
                    
                    # 应用更改
                    temp_map[file_path] = current_content.replace(old_content, new_content)
                    
                else:  # FMT2 - 首尾行定位格式
                    lines = patch_content.splitlines()
                    if len(lines) < 3:
                        error_info.append(f"FMT2补丁格式错误: {file_path}，行数不足")
                        return False, "\n".join(error_info)
                        
                    first_line = lines[0]
                    last_line = lines[1]
                    new_content = '\n'.join(lines[2:])
                    
                    # 在文件内容中定位要替换的区域
                    content_lines = current_content.splitlines()
                    start_idx = -1
                    end_idx = -1
                    
                    # 查找匹配的起始行和结束行
                    for idx, line in enumerate(content_lines):
                        if line.rstrip() == first_line.rstrip():
                            start_idx = idx
                        if start_idx != -1 and line.rstrip() == last_line.rstrip():
                            end_idx = idx
                            break
                    
                    if start_idx == -1 or end_idx == -1:
                        error_info.append(
                            f"补丁应用失败: {file_path}\n"
                            f"原因: 未找到匹配的代码范围\n"
                            f"起始行: {first_line}\n"
                            f"结束行: {last_line}"
                        )
                        return False, "\n".join(error_info)
                    
                    # 替换内容
                    content_lines[start_idx:end_idx + 1] = new_content.splitlines()
                    temp_map[file_path] = "\n".join(content_lines)
                
                modified_files.add(file_path)
                
            except Exception as e:
                error_info.append(f"处理补丁时发生错误: {str(e)}")
                return False, "\n".join(error_info)
        
        # 所有补丁都应用成功，更新实际文件
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

    def handle_patch_feedback(self, error_msg: str, feature: str) -> List[Tuple[str, str, str]]:
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
        success, response = call_model_with_retry(self.model, retry_prompt)
        if not success:
            return []
            
        try:
            patches = []
            
            # 匹配两种格式的补丁
            fmt1_patches = re.finditer(r'<PATCH_FMT1>\n?(.*?)\n?</PATCH_FMT1>', response, re.DOTALL)
            fmt2_patches = re.finditer(r'<PATCH_FMT2>\n?(.*?)\n?</PATCH_FMT2>', response, re.DOTALL)
            
            # 处理 FMT1 格式的补丁
            for match in fmt1_patches:
                patch_content = match.group(1)
                if not patch_content:
                    continue
                    
                # 提取文件路径和补丁内容
                lines = patch_content.split('\n')
                file_path_match = re.search(r'> (.*)', lines[0])
                if not file_path_match:
                    continue
                    
                file_path = file_path_match.group(1).strip()
                patch_content = '\n'.join(lines[1:])
                patches.append(("FMT1", file_path, patch_content))
            
            # 处理 FMT2 格式的补丁
            for match in fmt2_patches:
                patch_content = match.group(1)
                if not patch_content:
                    continue
                    
                # 提取文件路径和补丁内容
                lines = patch_content.split('\n')
                file_path_match = re.search(r'> (.*)', lines[0])
                if not file_path_match:
                    continue
                    
                file_path = file_path_match.group(1).strip()
                patch_content = '\n'.join(lines[1:])
                patches.append(("FMT2", file_path, patch_content))
            
            return patches
            
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.WARNING)
            return []

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
            
        PrettyOutput.print(f"补丁应用失败: {error_msg}", OutputType.ERROR)
        
        # 询问是否继续尝试
        retry = input("\n是否重新尝试？(y/n) [y]: ").lower() or "y"
        return retry == "y"

    def handle_patch_application(self, related_files: List[Dict], feature: str) -> bool:
        """处理补丁应用流程
        
        Args:
            related_files: 相关文件列表
            feature: 功能描述
            
        Returns:
            bool: 是否成功应用补丁
        """
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            
            # 1. 生成补丁
            patches = self.make_patch(related_files, feature)
            if not patches:
                return False
            
            # 2. 应用补丁
            success, error_msg = self.apply_patch(related_files, patches)
            
            # 3. 监控结果
            should_retry = self.monitor_patch_result(success, error_msg)
            if not should_retry:
                return success
                
            # 4. 处理失败反馈
            patches = self.handle_patch_feedback(error_msg, feature)
            if not patches:
                return False
        
        PrettyOutput.print(f"达到最大重试次数 ({max_attempts})", OutputType.WARNING)
        return False 