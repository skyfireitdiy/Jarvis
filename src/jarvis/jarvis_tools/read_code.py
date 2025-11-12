# -*- coding: utf-8 -*-
import os
from typing import Any, Dict

from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ReadCodeTool:
    name = "read_code"
    description = "读取源代码文件并添加行号，适用于代码分析和审查。"
    # 工具标签
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "number", "default": 1},
                        "end_line": {"type": "number", "default": -1},
                    },
                    "required": ["path"],
                },
                "description": "要读取的文件列表",
            }
        },
        "required": ["files"],
    }
    
    def _get_max_token_limit(self, agent: Any = None) -> int:
        """获取基于最大窗口数量的token限制
        
        Args:
            agent: Agent实例，用于获取模型组配置
            
        Returns:
            int: 允许的最大token数（2/3最大窗口）
        """
        try:
            # 尝试从agent获取模型组
            model_group = None
            if agent:
                model_group = getattr(agent, "model_group", None)
            
            max_input_tokens = get_max_input_token_count(model_group)
            # 计算2/3限制的token数
            limit_tokens = int(max_input_tokens * 2 / 3)
            return limit_tokens
        except Exception:
            # 如果获取失败，使用默认值（假设32000 token，2/3是21333）
            return 21333

    def _handle_single_file(
        self, filepath: str, start_line: int = 1, end_line: int = -1, agent: Any = None
    ) -> Dict[str, Any]:
        """处理单个文件的读取操作

        Args:
            filepath (str): 文件路径
            start_line (int): 起始行号，默认为1
            end_line (int): 结束行号，默认为-1表示文件末尾
            agent: Agent实例，用于获取上下文管理器

        Returns:
            Dict[str, Any]: 包含成功状态、输出内容和错误信息的字典
        """
        try:
            abs_path = os.path.abspath(filepath)

            # 文件存在性检查
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"文件不存在: {abs_path}",
                }

            # 文件大小限制检查（10MB）
            if os.path.getsize(abs_path) > 10 * 1024 * 1024:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "文件过大 (>10MB)",
                }

            # 读取文件内容
            # 第一遍流式读取，仅统计总行数，避免一次性读入内存
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                total_lines = sum(1 for _ in f)

            # 处理空文件情况
            if total_lines == 0:
                return {
                    "success": True,
                    "stdout": f"\n🔍 文件: {abs_path}\n📄 文件为空 (0行)\n",
                    "stderr": "",
                }

            # 处理特殊值-1表示文件末尾
            if end_line == -1:
                end_line = total_lines
            else:
                end_line = (
                    max(1, min(end_line, total_lines))
                    if end_line >= 0
                    else total_lines + end_line + 1
                )

            start_line = (
                max(1, min(start_line, total_lines))
                if start_line >= 0
                else total_lines + start_line + 1
            )

            if start_line > end_line:

                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"无效的行范围 [{start_line}-{end_line}] (总行数: {total_lines})",
                }

            # 读取要读取的行范围内容，计算实际token数
            selected_content_lines = []
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, start=1):
                    if i < start_line:
                        continue
                    if i > end_line:
                        break
                    selected_content_lines.append(line)
            
            # 构建带行号的内容用于token计算（与实际输出格式一致）
            numbered_content = "".join(f"{i:4d}:{line}" for i, line in enumerate(selected_content_lines, start=start_line))
            
            # 计算实际token数
            content_tokens = get_context_token_count(numbered_content)
            max_token_limit = self._get_max_token_limit(agent)
            
            # 检查单文件读取token数是否超过2/3限制
            if content_tokens > max_token_limit:
                read_lines = end_line - start_line + 1
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"⚠️ 读取范围过大: 请求读取内容约 {content_tokens} tokens，超过限制 ({max_token_limit} tokens，约2/3最大窗口)\n"
                        f"📊 读取范围: {read_lines} 行 (第 {start_line}-{end_line} 行，文件总行数 {total_lines})\n"
                        f"💡 建议：\n"
                        f"   1. 分批读取：将范围分成多个较小的批次，每批内容不超过 {max_token_limit} tokens\n"
                        f"   2. 先定位：使用搜索或分析工具定位大致位置，再读取具体范围\n"
                        f"   3. 缩小范围：为文件指定更精确的行号范围"
                    ),
                }

            # 使用已读取的内容构建输出（避免重复读取）
            numbered_content = "".join(f"{i:4d}:{line}" for i, line in enumerate(selected_content_lines, start=start_line))

            # 构建输出格式
            output = (
                f"\n🔍 文件: {abs_path}\n"
                f"📄 原始行号: {start_line}-{end_line} (共{total_lines}行) \n\n"
                f"{numbered_content}\n\n"
            )

            # 尝试获取并附加上下文信息
            context_info = self._get_file_context(abs_path, start_line, end_line, agent)
            if context_info:
                output += context_info

            if agent:
                files = agent.get_user_data("files")
                if files:
                    files.append(abs_path)
                else:
                    files = [abs_path]
                agent.set_user_data("files", files)

            return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": f"文件读取失败: {str(e)}"}

    def _get_file_context(
        self, filepath: str, start_line: int, end_line: int, agent: Any = None
    ) -> str:
        """获取文件的上下文信息

        Args:
            filepath: 文件路径
            start_line: 起始行号
            end_line: 结束行号
            agent: Agent实例

        Returns:
            格式化的上下文信息字符串，如果无法获取则返回空字符串
        """
        try:
            # 尝试从Agent获取CodeAgent实例
            if not agent:
                return ""

            # 通过agent获取CodeAgent实例
            # CodeAgent在初始化时会将自身关联到agent
            code_agent = getattr(agent, "_code_agent", None)
            if not code_agent:
                return ""

            # 获取上下文管理器
            context_manager = getattr(code_agent, "context_manager", None)
            if not context_manager:
                return ""

            # 输出上下文感知日志
            file_name = os.path.basename(filepath)
            if start_line == end_line:
                line_info = f"第{start_line}行"
            else:
                line_info = f"第{start_line}-{end_line}行"
            PrettyOutput.print(f"🧠 正在分析代码上下文 ({file_name}, {line_info})...", OutputType.INFO)

            # 确保文件已更新到上下文管理器
            # 如果文件内容已缓存，直接使用；否则读取并更新
            if not hasattr(context_manager, "_file_cache") or filepath not in context_manager._file_cache:
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    context_manager.update_context_for_file(filepath, content)
                except Exception:
                    # 如果读取失败，尝试获取已有上下文
                    pass

            # 获取编辑上下文
            edit_context = context_manager.get_edit_context(filepath, start_line, end_line)

            # 构建上下文信息
            if not edit_context.context_summary or edit_context.context_summary == "No context available":
                return ""

            # 格式化上下文信息
            context_lines = ["\n📋 代码上下文信息:"]
            context_lines.append("─" * 60)

            if edit_context.current_scope:
                scope_info = f"📍 当前作用域: {edit_context.current_scope.kind} `{edit_context.current_scope.name}`"
                if edit_context.current_scope.signature:
                    scope_info += f"\n   └─ 签名: {edit_context.current_scope.signature}"
                context_lines.append(scope_info)

            if edit_context.used_symbols:
                symbol_names = [s.name for s in edit_context.used_symbols[:10]]
                symbols_str = ", ".join(f"`{name}`" for name in symbol_names)
                more = len(edit_context.used_symbols) - 10
                if more > 0:
                    symbols_str += f" (还有{more}个)"
                context_lines.append(f"🔗 使用的符号: {symbols_str}")

            # 不再感知导入符号

            if edit_context.relevant_files:
                rel_files = edit_context.relevant_files[:10]
                files_str = "\n   ".join(f"• {os.path.relpath(f, context_manager.project_root)}" for f in rel_files)
                more = len(edit_context.relevant_files) - 10
                if more > 0:
                    files_str += f"\n   ... 还有{more}个相关文件"
                context_lines.append(f"📁 相关文件 ({len(edit_context.relevant_files)}个):\n   {files_str}")

            context_lines.append("─" * 60)
            context_lines.append("")  # 空行

            # 打印上下文感知结果到控制台
            context_output = "\n".join(context_lines)
            PrettyOutput.print(f"🧠 上下文感知结果:\n{context_output}", OutputType.INFO)
            
            return context_output

        except Exception:
            # 静默失败，不影响文件读取
            return ""

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行代码读取操作

        Args:
            args (Dict): 包含文件列表的参数字典

        Returns:
            Dict[str, Any]: 包含成功状态、输出内容和错误信息的字典
        """
        try:
            agent = args.get("agent", None)
            if "files" not in args or not isinstance(args["files"], list):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "参数中必须包含文件列表",
                }

            all_outputs = []
            overall_success = True
            status_lines = []
            total_tokens = 0  # 累计读取的token数
            max_token_limit = self._get_max_token_limit(agent)

            # 第一遍：检查所有文件的累计token数是否超过限制
            file_read_info = []  # 存储每个文件要读取的信息
            for file_info in args["files"]:
                if not isinstance(file_info, dict) or "path" not in file_info:
                    continue
                
                filepath = file_info["path"].strip()
                start_line = file_info.get("start_line", 1)
                end_line = file_info.get("end_line", -1)
                
                # 检查文件是否存在并计算要读取的token数
                abs_path = os.path.abspath(filepath)
                if not os.path.exists(abs_path):
                    continue
                
                try:
                    # 统计总行数
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        total_lines = sum(1 for _ in f)
                    
                    if total_lines == 0:
                        continue
                    
                    # 计算实际要读取的行范围
                    if end_line == -1:
                        actual_end_line = total_lines
                    else:
                        actual_end_line = (
                            max(1, min(end_line, total_lines))
                            if end_line >= 0
                            else total_lines + end_line + 1
                        )
                    
                    actual_start_line = (
                        max(1, min(start_line, total_lines))
                        if start_line >= 0
                        else total_lines + start_line + 1
                    )
                    
                    if actual_start_line <= actual_end_line:
                        # 读取要读取的行范围内容
                        selected_content_lines = []
                        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, start=1):
                                if i < actual_start_line:
                                    continue
                                if i > actual_end_line:
                                    break
                                selected_content_lines.append(line)
                        
                        # 构建带行号的内容用于token计算（与实际输出格式一致）
                        numbered_content = "".join(
                            f"{i:4d}:{line}" 
                            for i, line in enumerate(selected_content_lines, start=actual_start_line)
                        )
                        
                        # 计算实际token数
                        content_tokens = get_context_token_count(numbered_content)
                        
                        file_read_info.append({
                            "filepath": filepath,
                            "start_line": actual_start_line,
                            "end_line": actual_end_line,
                            "read_lines": actual_end_line - actual_start_line + 1,
                            "tokens": content_tokens,
                            "file_info": file_info,
                        })
                        total_tokens += content_tokens
                except Exception:
                    continue

            # 检查累计token数是否超过限制
            if total_tokens > max_token_limit:
                file_list = "\n   ".join(
                    f"• {info['filepath']}: {info['tokens']} tokens ({info['read_lines']} 行, 范围: {info['start_line']}-{info['end_line']})"
                    for info in file_read_info[:10]
                )
                more_files = len(file_read_info) - 10
                if more_files > 0:
                    file_list += f"\n   ... 还有 {more_files} 个文件"
                
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"⚠️ 累计读取范围过大: 请求累计读取内容约 {total_tokens} tokens，超过限制 ({max_token_limit} tokens，约2/3最大窗口)\n"
                        f"📋 文件列表 ({len(file_read_info)} 个文件):\n   {file_list}\n"
                        f"💡 建议：\n"
                        f"   1. 分批读取：将文件分成多个批次，每批累计内容不超过 {max_token_limit} tokens\n"
                        f"   2. 先定位：使用搜索或分析工具定位关键代码位置，再读取具体范围\n"
                        f"   3. 缩小范围：为每个文件指定更精确的行号范围"
                    ),
                }

            # 第二遍：实际读取文件
            for file_info in args["files"]:
                if not isinstance(file_info, dict) or "path" not in file_info:
                    continue

                result = self._handle_single_file(
                    file_info["path"].strip(),
                    file_info.get("start_line", 1),
                    file_info.get("end_line", -1),
                    agent,
                )

                if result["success"]:
                    all_outputs.append(result["stdout"])
                    status_lines.append(f"✅ {file_info['path']} 文件读取成功")
                else:
                    all_outputs.append(f"❌ {file_info['path']}: {result['stderr']}")
                    status_lines.append(f"❌ {file_info['path']} 文件读取失败")
                    overall_success = False

            stdout_text = "\n".join(all_outputs)
            # 仅打印每个文件的读取状态，不打印具体内容
            try:
                if status_lines:
                    print("\n".join(status_lines), end="\n")
            except Exception:
                pass
            return {
                "success": overall_success,
                "stdout": stdout_text,
                "stderr": "",
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": f"代码读取失败: {str(e)}"}
