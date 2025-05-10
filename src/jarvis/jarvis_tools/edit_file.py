"""
文件搜索替换工具类

功能概述:
1. 提供精确的文件内容搜索和替换功能
2. 支持单个文件的编辑操作，包括创建新文件
3. 实现原子操作：所有修改要么全部成功，要么全部回滚
4. 严格匹配控制：每个搜索文本必须且只能匹配一次

核心特性:
- 支持不存在的文件和空文件处理
- 自动创建所需目录结构
- 完善的错误处理和回滚机制
- 严格的格式保持要求
"""
from typing import Any, Dict


class FileSearchReplaceTool:
    name = "edit_file"
    description = """代码编辑工具，用于编辑单个文件

# 代码编辑规范

## 重要提示
此工具可以查看和修改单个文件的代码，只需提供要修改的代码片段即可。应尽量精简内容，只包含必要的上下文和修改部分。特别注意：不要提供完整文件内容，只提供需要修改的部分！

## 基本使用
1. 指定需要修改的文件路径
2. 提供一组或多组"搜索文本"和"替换文本"对
3. 每个搜索文本需在目标文件中有且仅有一次精确匹配
4. 创建新文件时，使用空字符串("")作为搜索文本，替换文本作为完整文件内容
5. 所有修改要么全部成功，要么全部失败并回滚

## 核心原则
1. **精准修改**：只提供需要修改的代码部分，不需要展示整个文件内容
2. **最小补丁原则**：始终生成最小范围的补丁，只包含必要的上下文和实际修改
3. **格式严格保持**：
   - 严格保持原始代码的缩进方式（空格或制表符）
   - 保持原始代码的空行数量和位置
   - 保持原始代码的行尾空格处理方式
   - 不改变原始代码的换行风格
4. **新旧区分**：
   - 对于新文件：提供完整的代码内容
   - 对于现有文件：只提供修改部分，不要提供整个文件

## 格式兼容性要求
1. **缩进一致性**：
   - 如果原代码使用4个空格缩进，替换文本也必须使用4个空格缩进
   - 如果原代码使用制表符缩进，替换文本也必须使用制表符
2. **空行保留**：
   - 如果原代码在函数之间有两个空行，替换文本也必须保留这两个空行
   - 如果原代码在类方法之间有一个空行，替换文本也必须保留这一个空行
3. **行尾处理**：
   - 不要改变原代码的行尾空格或换行符风格
   - 保持原有的换行符类型(CR、LF或CRLF)

## 最佳实践
1. 每个修改应专注于单一职责，避免包含过多无关代码
2. 设计唯一的搜索文本，避免多处匹配的风险
3. 创建新文件时提供完整、格式良好的内容
4. 不要出现未实现的代码，如：TODO
"""
    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "需要修改的文件路径"
            },
            "changes": {
                "type": "array",
                "description": "一组或多组搜索替换对",
                "items": {
                    "type": "object",
                    "properties": {
                        "search": {
                            "type": "string",
                            "description": "需要被替换的文本，必须在文件中唯一匹配，新文件用空字符串"
                        },
                        "replace": {
                            "type": "string", 
                            "description": "替换的目标文本，需保持与原代码相同的缩进和格式风格"
                        }
                    },
                    "required": ["search", "replace"]
                }
            }
        },
        "required": ["file", "changes"]
    }

    def __init__(self):
        """初始化文件搜索替换工具"""
        pass

    def execute(self, args: Dict) -> Dict[str, Any]:
        """
        执行文件搜索替换操作，每个搜索文本只允许有且只有一次匹配，否则失败
        特殊支持不存在的文件和空文件处理

        参数:
            file (str): 文件路径
            changes (list): 一组或多组搜索替换对，格式如下：
            [
                {
                    "search": "搜索文本1",
                    "replace": "替换文本1"
                },
                {
                    "search": "搜索文本2",
                    "replace": "替换文本2"
                }
            ]

        返回:
            dict: 包含执行结果的字典
            {
                "success": bool,  # 是否成功完成所有替换
                "stdout": str,    # 标准输出信息
                "stderr": str     # 错误信息
            }
        """
        import os
        from jarvis.jarvis_utils.output import PrettyOutput, OutputType
        
        stdout_messages = []
        stderr_messages = []
        success = True
        
        file_path = args["file"]
        changes = args["changes"]
        
        # 创建已处理文件变量，用于失败时回滚
        original_content = None
        processed = False

        try:
            file_exists = os.path.exists(file_path)
            content = ""
            
            try:
                # 如果文件存在，则读取内容
                if file_exists:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        original_content = content
                
                # 创建一个临时内容副本进行操作
                temp_content = content
                replaced_count = 0
                
                # 处理所有搜索替换对
                for change in changes:
                    search_text = change["search"]
                    replace_text = change["replace"]
                    
                    # 特殊处理不存在的文件或空文件
                    if not file_exists or content == "":
                        if search_text == "":
                            # 对于不存在的文件或空文件，如果搜索文本为空，则直接使用替换文本作为内容
                            temp_content = replace_text
                            replaced_count += 1
                            # 只允许有一个空字符串搜索
                            break
                        else:
                            stderr_message = f"文件 {file_path} {'不存在' if not file_exists else '为空'}，但搜索文本非空: '{search_text}'"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.ERROR)
                            success = False
                            break
                    else:
                        # 正常文件处理 - 检查匹配次数
                        match_count = temp_content.count(search_text)
                        
                        if match_count == 0:
                            stderr_message = f"文件 {file_path} 中未找到匹配文本: '{search_text}'"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.ERROR)
                            success = False
                            break
                        elif match_count > 1:
                            stderr_message = f"文件 {file_path} 中匹配到多个 ({match_count}) '{search_text}'，搜索文本只允许一次匹配"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.ERROR)
                            success = False
                            break
                        else:
                            # 只有一个匹配，执行替换
                            temp_content = temp_content.replace(search_text, replace_text, 1)
                            replaced_count += 1

                # 只有当所有替换操作都成功时，才写回文件
                if success and (temp_content != original_content or not file_exists):
                    # 确保目录存在
                    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(temp_content)
                    
                    processed = True
                    
                    action = "创建并写入" if not file_exists else "成功替换"
                    stdout_message = f"文件 {file_path} {action} {replaced_count} 处"
                    stdout_messages.append(stdout_message)
                    PrettyOutput.print(stdout_message, OutputType.SUCCESS)
                elif success:
                    stdout_message = f"文件 {file_path} 没有找到需要替换的内容"
                    stdout_messages.append(stdout_message)
                    PrettyOutput.print(stdout_message, OutputType.INFO)
                
            except Exception as e:
                stderr_message = f"处理文件 {file_path} 时出错: {str(e)}"
                stderr_messages.append(stderr_message)
                PrettyOutput.print(stderr_message, OutputType.ERROR)
                success = False

            # 如果操作失败，回滚已修改的文件
            if not success and processed:
                rollback_message = "操作失败，正在回滚修改..."
                stderr_messages.append(rollback_message)
                PrettyOutput.print(rollback_message, OutputType.WARNING)
                
                try:
                    if original_content is None:
                        # 如果是新创建的文件，则删除
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        rollback_file_message = f"已删除新创建的文件: {file_path}"
                    else:
                        # 如果是修改的文件，则恢复原内容
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(original_content)
                        rollback_file_message = f"已回滚文件: {file_path}"
                        
                    stderr_messages.append(rollback_file_message)
                    PrettyOutput.print(rollback_file_message, OutputType.INFO)
                except Exception as e:
                    rollback_error = f"回滚文件 {file_path} 失败: {str(e)}"
                    stderr_messages.append(rollback_error)
                    PrettyOutput.print(rollback_error, OutputType.ERROR)

            return {
                "success": success,
                "stdout": "\n".join(stdout_messages),
                "stderr": "\n".join(stderr_messages)
            }
            
        except Exception as e:
            error_msg = f"文件搜索替换操作失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            
            # 如果有已修改的文件，尝试回滚
            if processed:
                rollback_message = "操作失败，正在回滚修改..."
                stderr_messages.append(rollback_message)
                PrettyOutput.print(rollback_message, OutputType.WARNING)
                
                try:
                    if original_content is None:
                        # 如果是新创建的文件，则删除
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        stderr_messages.append(f"已删除新创建的文件: {file_path}")
                    else:
                        # 如果是修改的文件，则恢复原内容
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(original_content)
                        stderr_messages.append(f"已回滚文件: {file_path}")
                except:
                    stderr_messages.append(f"回滚文件失败: {file_path}")
            
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg + "\n" + "\n".join(stderr_messages)
            }

            