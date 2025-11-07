# -*- coding: utf-8 -*-
import os
from typing import Any, Dict

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ReadCodeTool:
    name = "read_code"
    description = "代码阅读与分析工具，用于读取源代码文件并添加行号，针对代码文件优化，提供更好的格式化输出和行号显示，适用于代码分析、审查和理解代码实现的场景"
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

            # 添加行号并构建输出内容（第二遍流式读取，仅提取范围行）
            selected_items = []
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, start=1):
                    if i < start_line:
                        continue
                    if i > end_line:
                        break
                    selected_items.append((i, line))
            numbered_content = "".join(f"{i:4d}:{line}" for i, line in selected_items)

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
                symbol_names = [s.name for s in edit_context.used_symbols[:8]]
                symbols_str = ", ".join(f"`{name}`" for name in symbol_names)
                more = len(edit_context.used_symbols) - 8
                if more > 0:
                    symbols_str += f" (还有{more}个)"
                context_lines.append(f"🔗 使用的符号: {symbols_str}")

            if edit_context.imported_symbols:
                import_names = [s.name for s in edit_context.imported_symbols[:8]]
                imports_str = ", ".join(f"`{name}`" for name in import_names)
                more = len(edit_context.imported_symbols) - 8
                if more > 0:
                    imports_str += f" (还有{more}个)"
                context_lines.append(f"📦 导入的符号: {imports_str}")

            if edit_context.relevant_files:
                rel_files = edit_context.relevant_files[:5]
                files_str = "\n   ".join(f"• {os.path.relpath(f, context_manager.project_root)}" for f in rel_files)
                more = len(edit_context.relevant_files) - 5
                if more > 0:
                    files_str += f"\n   ... 还有{more}个相关文件"
                context_lines.append(f"📁 相关文件 ({len(edit_context.relevant_files)}个):\n   {files_str}")

            context_lines.append("─" * 60)
            context_lines.append("")  # 空行

            return "\n".join(context_lines)

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
