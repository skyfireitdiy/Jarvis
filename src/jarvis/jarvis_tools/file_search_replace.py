class FileSearchReplaceTool:
    name = "file_search_replace"
    description = """文件精确编辑工具，基于搜索替换实现文件内容的修改与创建

# 文件编辑指南

## 基本说明
该工具通过精确的文本搜索和替换操作实现代码编辑，可以安全地修改、创建和更新各类文本文件。

## 使用说明
1. 指定需要修改的一个或多个文件路径
2. 为每个文件提供一组或多组"搜索文本"和"替换文本"对
3. 搜索文本需在目标文件中有且仅有一次精确匹配
4. 创建新文件时，使用空字符串("")作为搜索文本，替换文本作为完整文件内容
5. 所有编辑要么全部成功，要么全部失败并回滚

## 重要注意事项
1. **提供充分上下文**：搜索文本应包含足够的上下文，确保在文件中能唯一匹配到目标位置
2. **保持代码风格**：替换文本必须与原代码保持相同的缩进、空行和格式风格
3. **精确定位**：每个搜索文本在文件中必须只有一次匹配，不能模糊匹配
4. **顺序重要性**：对同一文件的多个编辑将按照指定的顺序依次执行
"""
    parameters = {
        "type": "object",
        "properties": {
            "files_config": {
                "type": "object",
                "description": "文件编辑配置，键为文件路径，值为搜索替换对列表",
                "additionalProperties": {
                    "type": "array",
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
            }
        },
        "required": ["files_config"]
    }

    def __init__(self):
        """初始化文件搜索替换工具"""
        pass

    def execute(self, files_config):
        """
        执行文件搜索替换操作，每个搜索块只允许有且只有一次匹配，否则失败
        任意一个文件处理失败，则整个操作就失败，并停止处理后续文件
        特殊支持不存在的文件和空文件处理

        参数:
            files_config (dict): 文件搜索替换配置，格式如下：
            {
                "文件1": [
                    {
                        "search": "搜索块1",
                        "replace": "替换块1"
                    },
                    {
                        "search": "搜索块2",
                        "replace": "替换块2"
                    }
                ],
                "文件2": [
                    {
                        "search": "搜索块1",
                        "replace": "替换块1"
                    }
                ]
            }

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
        
        # 创建已处理文件列表，用于失败时回滚
        processed_files = []

        try:
            for file_path, replacements in files_config.items():
                file_exists = os.path.exists(file_path)
                content = ""
                original_content = ""
                
                try:
                    # 如果文件存在，则读取内容
                    if file_exists:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            original_content = content
                    
                    file_success = True
                    file_replaced_count = 0
                    
                    # 创建一个临时内容副本进行操作
                    temp_content = content
                    
                    # 执行所有替换操作
                    for replacement in replacements:
                        search_text = replacement["search"]
                        replace_text = replacement["replace"]
                        
                        # 特殊处理不存在的文件或空文件
                        if not file_exists or content == "":
                            if search_text == "":
                                # 对于不存在的文件或空文件，如果搜索文本为空，则直接使用替换文本作为内容
                                temp_content = replace_text
                                file_replaced_count += 1
                                continue
                            else:
                                stderr_message = f"文件 {file_path} {'不存在' if not file_exists else '为空'}，但搜索文本非空: '{search_text}'"
                                stderr_messages.append(stderr_message)
                                PrettyOutput.print(stderr_message, OutputType.ERROR)
                                file_success = False
                                success = False
                                break
                        
                        # 正常文件处理 - 检查匹配次数
                        match_count = temp_content.count(search_text)
                        
                        if match_count == 0:
                            stderr_message = f"文件 {file_path} 中未找到匹配文本: '{search_text}'"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.ERROR)
                            file_success = False
                            success = False
                            break
                        elif match_count > 1:
                            stderr_message = f"文件 {file_path} 中匹配到多个 ({match_count}) '{search_text}'，每个搜索块只允许一次匹配"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.ERROR)
                            file_success = False
                            success = False
                            break
                        else:
                            # 只有一个匹配，执行替换
                            temp_content = temp_content.replace(search_text, replace_text, 1)
                            file_replaced_count += 1

                    # 只有当所有替换操作都成功时，才写回文件
                    if file_success and (temp_content != original_content or not file_exists):
                        # 确保目录存在
                        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(temp_content)
                        
                        if file_exists:
                            processed_files.append((file_path, original_content))
                        else:
                            processed_files.append((file_path, None))  # 标记为新创建的文件
                        
                        action = "创建并写入" if not file_exists else "成功替换"
                        stdout_message = f"文件 {file_path} {action} {file_replaced_count} 处"
                        stdout_messages.append(stdout_message)
                        PrettyOutput.print(stdout_message, OutputType.SUCCESS)
                    elif not file_success:
                        # 如果当前文件处理失败，停止处理后续文件
                        break
                    else:
                        stdout_message = f"文件 {file_path} 没有找到需要替换的内容"
                        stdout_messages.append(stdout_message)
                        PrettyOutput.print(stdout_message, OutputType.INFO)
                    
                except Exception as e:
                    stderr_message = f"处理文件 {file_path} 时出错: {str(e)}"
                    stderr_messages.append(stderr_message)
                    PrettyOutput.print(stderr_message, OutputType.ERROR)
                    success = False
                    break  # 任意文件失败，停止处理

            # 如果操作失败，回滚已修改的文件
            if not success and processed_files:
                rollback_message = "操作失败，正在回滚已修改的文件..."
                stderr_messages.append(rollback_message)
                PrettyOutput.print(rollback_message, OutputType.WARNING)
                
                for file_path, original_content in processed_files:
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
            if processed_files:
                rollback_message = "操作失败，正在回滚已修改的文件..."
                stderr_messages.append(rollback_message)
                PrettyOutput.print(rollback_message, OutputType.WARNING)
                
                for file_path, original_content in processed_files:
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

            