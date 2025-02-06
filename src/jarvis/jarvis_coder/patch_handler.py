import re
import os
from typing import List, Tuple, Dict
from jarvis.utils import OutputType, PrettyOutput
from .model_utils import call_model_with_retry

class PatchHandler:
    def __init__(self, model):
        self.model = model

    def _extract_patches(self, response: str) -> List[Tuple[str, str, str]]:
        """从响应中提取补丁
        
        Args:
            response: 模型响应内容
            
        Returns:
            List[Tuple[str, str, str]]: 补丁列表，每个补丁是 (格式, 文件路径, 补丁内容) 的元组
        """
        patches = []
        
        # 匹配两种补丁格式
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
            if fmt_type == "1":
                # FMT1格式：新旧内容分隔
                parts = '\n'.join(lines[1:]).split('@@@@@@')
                if len(parts) != 2:
                    continue
                old_content = parts[0].strip()
                new_content = parts[1].strip()
                patches.append(("FMT1", file_path, f"{old_content}\n@@@@@@\n{new_content}"))
            elif fmt_type == "2":
                # FMT2格式：全文件替换
                full_content = '\n'.join(lines[1:]).strip()
                patches.append(("FMT2", file_path, full_content))

        return patches

    def make_patch(self, related_files: List[Dict], feature: str, modification_plan: str) -> List[Tuple[str, str, str]]:
        """生成修改方案"""
        prompt = f"""你是一个资深程序员，请根据需求描述和修改方案，修改文件内容。

修改格式说明：
可选两种格式：
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

注意事项：
1、仅输出补丁内容，不要输出任何其他内容
2、如果在大段代码中有零星修改，生成多个补丁
3、要替换的内容，一定要与文件内容完全一致（**包括缩进与空白**），不要有任何多余或者缺失的内容
4、每个patch不超过20行，超出20行，请生成多个patch
5、务必保留原始文件的缩进和格式
6、对于新文件，不需要写old_content部分
"""
        # 添加文件内容到提示
        for i, file in enumerate(related_files):
            prompt += f"""\n{i}. {file["file_path"]}\n"""
            prompt += f"""文件内容:\n"""
            prompt += f"<FILE_CONTENT>\n"
            prompt += f'{file["file_content"]}\n'
            prompt += f"</FILE_CONTENT>\n"

        # 调用模型生成补丁
        success, response = call_model_with_retry(self.model, prompt)
        if not success:
            PrettyOutput.print("生成补丁失败", OutputType.ERROR)
            return []
            
        try:
            patches = self._extract_patches(response)
            
            if not patches:
                PrettyOutput.print("未生成任何有效补丁", OutputType.WARNING)
                return []
                
            PrettyOutput.print(f"生成了 {len(patches)} 个补丁", OutputType.SUCCESS)
            return patches
            
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.WARNING)
            return []

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
                if fmt == "FMT2":
                    # 全文件替换逻辑
                    if file_path not in temp_map:
                        # 新建文件
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(patch_content)
                        temp_map[file_path] = patch_content
                        modified_files.add(file_path)
                        continue
                        
                    # 替换现有文件
                    temp_map[file_path] = patch_content
                    modified_files.add(file_path)
                    continue
                
                # 分割新旧内容，并处理换行符
                parts = patch_content.split("@@@@@@")
                if len(parts) != 2:
                    error_info.append(f"补丁格式错误: {file_path}，缺少分隔符")
                    return False, "\n".join(error_info)
                    
                old_content = parts[0].strip('\n')  # 移除前后的换行符
                new_content = parts[1].strip('\n')  # 移除前后的换行符
                
                # 处理新文件的情况
                if file_path not in temp_map and not old_content.strip():
                    PrettyOutput.print(f"检测到新文件: {file_path}", OutputType.INFO)
                    # 确保目录存在
                    dir_path = os.path.dirname(file_path)
                    if dir_path and not os.path.exists(dir_path):
                        os.makedirs(dir_path, exist_ok=True)
                    
                    # 写入新文件
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        # 将新文件加入版本控制
                        os.system(f"git add {file_path}")
                        PrettyOutput.print(f"成功创建并添加文件: {file_path}", OutputType.SUCCESS)
                        modified_files.add(file_path)
                        temp_map[file_path] = new_content  # 更新临时映射
                        continue
                    except Exception as e:
                        error_info.append(f"创建新文件失败 {file_path}: {str(e)}")
                        return False, "\n".join(error_info)
                
                # 处理现有文件的修改
                if file_path not in temp_map:
                    error_info.append(f"文件不存在: {file_path}")
                    return False, "\n".join(error_info)
                
                current_content = temp_map[file_path]
                
                # 查找并替换代码块
                if old_content and old_content not in current_content:
                    error_info.append(
                        f"补丁应用失败: {file_path}\n"
                        f"原因: 未找到要替换的代码\n"
                        f"期望找到的代码:\n{old_content}\n"
                        f"实际文件内容:\n{current_content[:200]}..."
                    )
                    return False, "\n".join(error_info)
                
                # 应用更改
                temp_map[file_path] = current_content.replace(old_content, new_content)
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
            patches = self._extract_patches(response)
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

    def handle_patch_application(self, related_files: List[Dict], feature: str, modification_plan: str) -> bool:
        """处理补丁应用流程
        
        Args:
            related_files: 相关文件列表
            feature: 功能描述
            modification_plan: 修改方案
            
        Returns:
            bool: 是否成功应用补丁
        """
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            PrettyOutput.print("开始生成补丁...", OutputType.PLANNING)
            attempt += 1
            
            while True:  # 在当前尝试中循环，直到成功或用户放弃
                # 1. 生成补丁
                patches = self.make_patch(related_files, feature, modification_plan)
                if not patches:
                    return False
                
                # 2. 显示补丁内容
                PrettyOutput.print("\n将要应用以下补丁:", OutputType.INFO)
                for fmt, file_path, patch_content in patches:
                    PrettyOutput.print(f"\n文件: {file_path}", OutputType.INFO)
                    PrettyOutput.print(f"格式: {fmt}", OutputType.INFO)
                    PrettyOutput.print("补丁内容:", OutputType.INFO)
                    print(patch_content)
                
                # 3. 应用补丁
                success, error_msg = self.apply_patch(related_files, patches)
                if not success:
                    # 4. 如果应用失败，询问是否重试
                    should_retry = self.monitor_patch_result(success, error_msg)
                    if not should_retry:
                        return False  # 用户选择不重试，直接返回失败
                        
                    # 5. 处理失败反馈
                    patches = self.handle_patch_feedback(error_msg, feature)
                    if not patches:
                        return False
                    continue  # 继续当前迭代
                
                # 6. 应用成功，让用户确认修改
                PrettyOutput.print("\n补丁已应用，请检查修改效果。", OutputType.SUCCESS)
                confirm = input("\n是否保留这些修改？(y/n) [y]: ").lower() or "y"
                if confirm != "y":
                    PrettyOutput.print("用户取消修改，正在回退", OutputType.WARNING)
                    os.system("git reset --hard")  # 回退所有修改
                    
                    # 询问是否要在当前迭代中重试
                    retry = input("\n是否要重新生成补丁？(y/n) [y]: ").lower() or "y"
                    if retry != "y":
                        return False  # 用户选择不重试，直接返回失败
                    continue  # 继续当前迭代
                
                return True  # 用户确认修改，返回成功
            
            # 如果内层循环正常退出（非return），继续外层循环
            continue
        
        PrettyOutput.print(f"达到最大重试次数 ({max_attempts})", OutputType.WARNING)
        return False 