# -*- coding: utf-8 -*-
import os
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_global_model_group
from jarvis.jarvis_utils.output import PrettyOutput


class ReadCodeTool:
    name = "read_code"
    description = "读取源代码文件的指定行号范围，并为每行添加行号后返回。"
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
                "description": "要读取的文件列表，每个文件可指定行号范围（start_line 到 end_line，-1 表示文件末尾）。",
            }
        },
        "required": ["files"],
    }

    def _get_max_token_limit(self, agent: Optional[Any] = None) -> int:
        """获取基于剩余token数量的token限制

        Args:
            agent: Agent实例，用于获取模型和剩余token数量

        Returns:
            int: 允许的最大token数（剩余token的2/3，或至少保留1/3剩余token）
        """
        try:
            # 优先使用剩余token数量
            if agent and hasattr(agent, "model"):
                try:
                    remaining_tokens = agent.model.get_remaining_token_count()
                    # 使用剩余token的1/2作为限制，保留1/2作为安全余量
                    limit_tokens = int(remaining_tokens * 1 / 2)
                    # 确保至少返回一个合理的值
                    if limit_tokens > 0:
                        return limit_tokens
                except Exception:
                    pass

            # 回退方案：使用输入窗口的2/3
            # 使用全局模型组（不再从 agent 继承）
            model_group = get_global_model_group()

            max_input_tokens = get_max_input_token_count(model_group)
            # 计算1/2限制的token数
            limit_tokens = int(max_input_tokens * 1 / 2)
            return limit_tokens
        except Exception:
            # 如果获取失败，使用默认值（假设128000 token，2/3是85333）
            return 21333

    def _handle_single_file(
        self,
        filepath: str,
        start_line: int = 1,
        end_line: int = -1,
        agent: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """处理单个文件的读取操作

        Args:
            filepath (str): 文件路径
            start_line (int): 起始行号，默认为1
            end_line (int): 结束行号，默认为-1表示文件末尾
            agent: Agent实例，用于获取token限制

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
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            total_lines = len(lines)

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

            # 读取指定行号范围的内容
            selected_lines = lines[start_line - 1 : end_line]

            # 为每行添加行号
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start_line):
                # 行号右对齐，占4位
                line_number_str = f"{i:4d}"
                # 移除行尾的换行符，因为我们会在后面统一添加
                line_content = line.rstrip("\n\r")
                numbered_lines.append(f"{line_number_str}:{line_content}")

            # 构造输出内容
            output_content = "\n".join(numbered_lines)

            # 估算token数
            content_tokens = get_context_token_count(output_content)
            max_token_limit = self._get_max_token_limit(agent)

            # 检查token数是否超过限制
            if content_tokens > max_token_limit:
                read_lines = end_line - start_line + 1

                # 计算安全读取的行数 (按比例缩减)
                safe_lines = int((max_token_limit / content_tokens) * read_lines)
                safe_lines = max(1, min(safe_lines, read_lines))
                safe_end_line = start_line + safe_lines - 1

                # 读取安全范围内的内容
                safe_selected_lines = lines[start_line - 1 : safe_end_line]
                safe_numbered_lines = []
                for i, line in enumerate(safe_selected_lines, start=start_line):
                    line_number_str = f"{i:4d}"
                    line_content = line.rstrip("\n\r")
                    safe_numbered_lines.append(f"{line_number_str}:{line_content}")

                # 构造部分读取结果
                partial_content = "\n".join(safe_numbered_lines)

                return {
                    "success": True,
                    "stdout": (
                        f"⚠️ 警告: 仅读取前{safe_lines}行 (共{read_lines}行)，因为内容超出限制\n"
                        f"📊 实际读取范围: {start_line}-{safe_end_line} (原请求范围: {start_line}-{end_line})\n\n"
                        f"{partial_content}\n\n"
                        f"💡 建议:\n"
                        f"   1. 如需继续读取，请使用:\n"
                        f"      start_line={safe_end_line + 1}&end_line={end_line}\n"
                        f"   2. 需要读取全部内容? 请缩小行范围或分批读取"
                    ),
                    "stderr": (
                        f"原始请求范围 {start_line}-{end_line} 超过token限制 "
                        f"({content_tokens}/{max_token_limit} tokens)"
                    ),
                }

            # 构造完整输出
            read_lines = end_line - start_line + 1
            output = f"\n🔍 文件: {abs_path}\n📄 总行数: {total_lines}\n📊 读取范围: {start_line}-{end_line}\n📈 读取行数: {read_lines}\n"
            output += "=" * 80 + "\n"
            output += output_content
            output += "\n" + "=" * 80 + "\n"

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
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": f"文件读取失败: {str(e)}"}

    def _get_file_context(
        self, filepath: str, start_line: int, end_line: int, agent: Optional[Any] = None
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

            # 上下文感知日志已移除

            # 确保文件已更新到上下文管理器
            # 如果文件内容已缓存，直接使用；否则读取并更新
            if (
                not hasattr(context_manager, "_file_cache")
                or filepath not in context_manager._file_cache
            ):
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    context_manager.update_context_for_file(filepath, content)
                except Exception:
                    # 如果读取失败，尝试获取已有上下文
                    pass

            # 获取编辑上下文
            edit_context = context_manager.get_edit_context(
                filepath, start_line, end_line
            )

            # 构建上下文信息
            if (
                not edit_context.context_summary
                or edit_context.context_summary == "No context available"
            ):
                return ""

            # 格式化上下文信息
            context_lines = ["\n📋 代码上下文信息:"]
            context_lines.append("─" * 60)

            if edit_context.current_scope:
                scope_info = f"📍 当前作用域: {edit_context.current_scope.kind} `{edit_context.current_scope.name}`"
                if edit_context.current_scope.signature:
                    scope_info += (
                        f"\n   └─ 签名: {edit_context.current_scope.signature}"
                    )
                context_lines.append(scope_info)

            if edit_context.used_symbols:
                # 对符号去重（基于 name + file_path + line_start）
                seen_symbols = set()
                unique_symbols = []
                for s in edit_context.used_symbols:
                    key = (
                        s.name,
                        getattr(s, "file_path", ""),
                        getattr(s, "line_start", 0),
                    )
                    if key not in seen_symbols:
                        seen_symbols.add(key)
                        unique_symbols.append(s)

                # 区分定义和调用，显示定义位置信息
                definitions = []
                calls = []
                for symbol in unique_symbols[:10]:
                    is_def = getattr(symbol, "is_definition", False)
                    if is_def:
                        definitions.append(symbol)
                    else:
                        calls.append(symbol)

                # 显示定义
                if definitions:
                    def_names = [f"`{s.name}`" for s in definitions]
                    context_lines.append(f"📝 定义的符号: {', '.join(def_names)}")

                # 显示调用（带定义位置信息）
                if calls:
                    call_info = []
                    for symbol in calls:
                        def_loc = getattr(symbol, "definition_location", None)
                        if def_loc:
                            def_file = os.path.basename(def_loc.file_path)
                            def_line = def_loc.line_start
                            call_info.append(f"`{symbol.name}` → {def_file}:{def_line}")
                        else:
                            call_info.append(f"`{symbol.name}`")
                    context_lines.append(f"🔗 调用的符号: {', '.join(call_info)}")

                # 如果还有更多符号
                more = len(edit_context.used_symbols) - 10
                if more > 0:
                    context_lines.append(f"   ... 还有{more}个符号")

            if edit_context.relevant_files:
                # 对相关文件去重
                unique_files = list(dict.fromkeys(edit_context.relevant_files))
                rel_files = unique_files[:10]
                files_str = "\n   ".join(
                    f"• {os.path.relpath(f, context_manager.project_root)}"
                    for f in rel_files
                )
                more = len(unique_files) - 10
                if more > 0:
                    files_str += f"\n   ... 还有{more}个相关文件"
                context_lines.append(
                    f"📁 相关文件 ({len(unique_files)}个):\n   {files_str}"
                )

            context_lines.append("─" * 60)
            context_lines.append("")  # 空行

            # 上下文感知结果已移除，不再打印到控制台
            context_output = "\n".join(context_lines)
            return context_output

        except Exception:
            # 静默失败，不影响文件读取
            return ""

    def _handle_merged_ranges(
        self, filepath: str, requests: List[Dict[str, Any]], agent: Optional[Any] = None
    ) -> Dict[str, Any]:
        """处理同一文件的多个范围请求，合并后去重

        Args:
            filepath: 文件绝对路径
            requests: 范围请求列表，每个请求包含 start_line, end_line
            agent: Agent实例

        Returns:
            Dict[str, Any]: 包含成功状态、输出内容和错误信息的字典
        """
        try:
            # 文件存在性检查
            if not os.path.exists(filepath):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"文件不存在: {filepath}",
                }

            # 读取文件内容
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            total_lines = len(lines)
            if total_lines == 0:
                return {
                    "success": True,
                    "stdout": f"\n🔍 文件: {filepath}\n📄 文件为空 (0行)\n",
                    "stderr": "",
                }

            # 合并所有范围，计算最小起始行和最大结束行
            min_start = float("inf")
            max_end = 0
            for req in requests:
                start_line = req.get("start_line", 1)
                end_line = req.get("end_line", -1)

                # 处理特殊值
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

                min_start = min(min_start, start_line)
                max_end = max(max_end, end_line)

            # 用合并后的范围读取一次，自然就去重了
            result = self._handle_single_file(
                filepath, int(min_start), int(max_end), agent
            )
            return result

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"合并范围读取失败: {str(e)}",
            }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

            if len(args["files"]) == 0:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "文件列表不能为空",
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
                    # 读取文件内容
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    total_lines = len(lines)

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
                        # 读取指定行号范围的内容
                        selected_lines = lines[actual_start_line - 1 : actual_end_line]

                        # 为每行添加行号
                        numbered_lines = []
                        for i, line in enumerate(
                            selected_lines, start=actual_start_line
                        ):
                            line_number_str = f"{i:4d}"
                            line_content = line.rstrip("\n\r")
                            numbered_lines.append(f"{line_number_str}:{line_content}")

                        # 构造输出内容用于token估算
                        output_content = "\n".join(numbered_lines)
                        content_tokens = get_context_token_count(output_content)

                        file_read_info.append(
                            {
                                "filepath": filepath,
                                "start_line": actual_start_line,
                                "end_line": actual_end_line,
                                "read_lines": actual_end_line - actual_start_line + 1,
                                "tokens": content_tokens,
                                "file_info": file_info,
                            }
                        )
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

            # 第二遍：实际读取文件（按文件分组，合并同一文件的多个范围请求，避免块重复）
            # 按文件路径分组
            from collections import defaultdict

            file_requests = defaultdict(list)
            for file_info in args["files"]:
                if not isinstance(file_info, dict) or "path" not in file_info:
                    continue
                abs_path = os.path.abspath(file_info["path"].strip())
                file_requests[abs_path].append(file_info)

            # 按文件处理，合并同一文件的多个范围请求
            for abs_path, requests in file_requests.items():
                if len(requests) == 1:
                    # 单个范围请求，直接处理
                    file_info = requests[0]
                    result = self._handle_single_file(
                        file_info["path"].strip(),
                        file_info.get("start_line", 1),
                        file_info.get("end_line", -1),
                        agent,
                    )
                    if result["success"]:
                        all_outputs.append(result["stdout"])
                        status_lines.append(
                            f"✅ {file_info['path']} 文件读取成功 (范围: {file_info.get('start_line', 1)}-{file_info.get('end_line', -1)})"
                        )
                    else:
                        all_outputs.append(
                            f"❌ {file_info['path']}: {result['stderr']}"
                        )
                        status_lines.append(f"❌ {file_info['path']} 文件读取失败")
                        overall_success = False
                else:
                    # 多个范围请求，合并处理并去重
                    merged_result = self._handle_merged_ranges(
                        abs_path, requests, agent
                    )
                    display_path = requests[0]["path"]
                    if merged_result["success"]:
                        all_outputs.append(merged_result["stdout"])
                        # 获取合并后的范围信息
                        min_start = min(req.get("start_line", 1) for req in requests)
                        max_end = max(req.get("end_line", -1) for req in requests)
                        status_lines.append(
                            f"✅ {display_path} 文件读取成功 (合并{len(requests)}个范围请求，已去重，范围: {min_start}-{max_end})"
                        )
                    else:
                        all_outputs.append(
                            f"❌ {display_path}: {merged_result['stderr']}"
                        )
                        status_lines.append(f"❌ {display_path} 文件读取失败")
                        overall_success = False

            stdout_text = "\n".join(all_outputs)
            # 仅打印每个文件的读取状态，不打印具体内容
            try:
                if status_lines:
                    PrettyOutput.auto_print("\n".join(status_lines))
            except Exception:
                pass
            return {
                "success": overall_success,
                "stdout": stdout_text,
                "stderr": "",
            }

        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": f"代码读取失败: {str(e)}"}


def main() -> None:
    """测试读取功能"""
    import os
    import tempfile

    tool = ReadCodeTool()

    PrettyOutput.auto_print("=" * 80)
    PrettyOutput.auto_print("测试读取功能")
    PrettyOutput.auto_print("=" * 80)

    # 测试1: 基本读取
    PrettyOutput.auto_print("\n【测试1】基本读取")
    PrettyOutput.auto_print("-" * 80)

    test_code = """def hello():
    PrettyOutput.auto_print("Hello, World!")

def add(a, b):
    return a + b

def sub(a, b):
    return a - b
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        test_file = f.name
        f.write(test_code)

    try:
        result = tool.execute(
            {
                "files": [{"path": test_file, "start_line": 1, "end_line": -1}],
                "agent": None,
            }
        )

        if result["success"]:
            PrettyOutput.auto_print("✅ 文件读取成功")
            PrettyOutput.auto_print("\n输出内容:")
            PrettyOutput.auto_print(result["stdout"])
        else:
            PrettyOutput.auto_print(f"❌ 文件读取失败: {result['stderr']}")
    finally:
        os.unlink(test_file)

    # 测试2: 指定行号范围
    PrettyOutput.auto_print("\n【测试2】指定行号范围读取")
    PrettyOutput.auto_print("-" * 80)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        test_file2 = f.name
        f.write(test_code)

    try:
        result = tool.execute(
            {
                "files": [{"path": test_file2, "start_line": 1, "end_line": 3}],
                "agent": None,
            }
        )

        if result["success"]:
            PrettyOutput.auto_print("✅ 指定范围读取成功")
            PrettyOutput.auto_print("\n输出内容:")
            PrettyOutput.auto_print(result["stdout"])
        else:
            PrettyOutput.auto_print(f"❌ 指定范围读取失败: {result['stderr']}")
    finally:
        os.unlink(test_file2)

    # 测试3: 多个文件
    PrettyOutput.auto_print("\n【测试3】多个文件读取")
    PrettyOutput.auto_print("-" * 80)

    with (
        tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f1,
        tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f2,
    ):
        test_file3 = f1.name
        test_file4 = f2.name
        f1.write(test_code)
        f2.write(test_code)

    try:
        result = tool.execute(
            {
                "files": [
                    {"path": test_file3, "start_line": 1, "end_line": -1},
                    {"path": test_file4, "start_line": 1, "end_line": -1},
                ],
                "agent": None,
            }
        )

        if result["success"]:
            PrettyOutput.auto_print("✅ 多文件读取成功")
            PrettyOutput.auto_print("\n输出内容（前500字符）:")
            PrettyOutput.auto_print(
                result["stdout"][:500] + "..."
                if len(result["stdout"]) > 500
                else result["stdout"]
            )
        else:
            PrettyOutput.auto_print(f"❌ 多文件读取失败: {result['stderr']}")
    finally:
        os.unlink(test_file3)
        os.unlink(test_file4)

    PrettyOutput.auto_print("\n" + "=" * 80)
    PrettyOutput.auto_print("测试完成")
    PrettyOutput.auto_print("=" * 80)


if __name__ == "__main__":
    main()
