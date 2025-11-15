# -*- coding: utf-8 -*-
import os
from typing import Any, Dict, List

from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 尝试导入语言支持模块
try:
    from jarvis.jarvis_code_agent.code_analyzer.language_support import (
        detect_language,
        get_dependency_analyzer,
    )
    from jarvis.jarvis_code_agent.code_analyzer.structured_code import StructuredCodeExtractor
    LANGUAGE_SUPPORT_AVAILABLE = True
except ImportError:
    LANGUAGE_SUPPORT_AVAILABLE = False
    def get_dependency_analyzer(language: str):
        return None
    StructuredCodeExtractor = None


class ReadCodeTool:
    name = "read_code"
    description = (
        "结构化读取源代码文件。"
        "支持的语言按语法单元（函数、类等）读取；不支持的语言按空白行分组；"
        "raw_mode=true 时按每20行分组读取。"
    )
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
                        "raw_mode": {"type": "boolean", "default": False},
                    },
                    "required": ["path"],
                },
                "description": "要读取的文件列表，每个文件可指定行号范围（start_line 到 end_line，-1 表示文件末尾）。raw_mode为true时按每20行分组读取（原始模式）。",
            }
        },
        "required": ["files"],
    }
    
    def _extract_syntax_units(
        self, filepath: str, content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """提取语法单元（函数、类等）
        
        Args:
            filepath: 文件路径
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号
            
        Returns:
            语法单元列表，每个单元包含 id, start_line, end_line, content
        """
        if StructuredCodeExtractor:
            return StructuredCodeExtractor.extract_syntax_units(filepath, content, start_line, end_line)
        return []
    
    def _extract_blank_line_groups(
        self, content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """按空白行分组提取内容（委托给StructuredCodeExtractor）"""
        if StructuredCodeExtractor:
            return StructuredCodeExtractor.extract_blank_line_groups(content, start_line, end_line)
        return []
    
    def _extract_blank_line_groups_with_split(
        self, content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """先按空白行分组，然后对超过20行的块再按每20行分割
        
        Args:
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号
            
        Returns:
            分组列表，每个分组包含 id, start_line, end_line, content
        """
        # 先获取空白行分组
        blank_line_groups = self._extract_blank_line_groups(content, start_line, end_line)
        
        if not blank_line_groups:
            return []
        
        result = []
        for group in blank_line_groups:
            group_line_count = group['end_line'] - group['start_line'] + 1
            if group_line_count > 20:
                # 如果块超过20行，按每20行分割
                sub_groups = self._extract_line_groups(
                    content, group['start_line'], group['end_line'], group_size=20
                )
                result.extend(sub_groups)
            else:
                # 如果块不超过20行，直接添加
                result.append(group)
        
        return result
    
    def _extract_line_groups(
        self, content: str, start_line: int, end_line: int, group_size: int = 20
    ) -> List[Dict[str, Any]]:
        """按行号分组提取内容（委托给StructuredCodeExtractor）"""
        if StructuredCodeExtractor:
            return StructuredCodeExtractor.extract_line_groups(content, start_line, end_line, group_size)
        return []
    
    def _ensure_unique_ids(self, units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """确保单元列表中所有id唯一（委托给StructuredCodeExtractor）"""
        if StructuredCodeExtractor:
            return StructuredCodeExtractor.ensure_unique_ids(units)
        return units
    
    def _extract_imports(self, filepath: str, content: str, start_line: int, end_line: int) -> List[Dict[str, Any]]:
        """提取文件的导入/包含语句作为结构化单元（委托给StructuredCodeExtractor）"""
        if StructuredCodeExtractor:
            return StructuredCodeExtractor.extract_imports(filepath, content, start_line, end_line)
        return []
    
    def _create_import_unit(self, import_group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建导入语句单元（委托给StructuredCodeExtractor）"""
        if StructuredCodeExtractor:
            return StructuredCodeExtractor.create_import_unit(import_group)
        return {}
    
    def _format_structured_output(
        self, filepath: str, units: List[Dict[str, Any]], total_lines: int
    ) -> str:
        """格式化结构化输出
        
        Args:
            filepath: 文件路径
            units: 语法单元或行号分组列表（已包含导入语句单元）
            total_lines: 文件总行数
            
        Returns:
            格式化后的输出字符串
        """
        output_lines = [
            f"\n🔍 文件: {filepath}",
            f"📄 总行数: {total_lines}",
            f"📦 结构化单元数: {len(units)}\n",
        ]
        
        for unit in units:
            # 显示id
            output_lines.append(f"[id:{unit['id']}]")
            # 添加内容，保持原有缩进，并添加行号
            content_lines = unit['content'].split('\n')
            current_line_num = unit['start_line']
            for line in content_lines:
                # 行号格式：5位右对齐，后面加冒号
                output_lines.append(f"{current_line_num:5d}:{line}")
                current_line_num += 1
            output_lines.append("")  # 单元之间空行分隔
        
        return '\n'.join(output_lines)
    
    def _estimate_structured_tokens(
        self, filepath: str, content: str, start_line: int, end_line: int, total_lines: int, raw_mode: bool = False
    ) -> int:
        """估算结构化输出的token数
        
        Args:
            filepath: 文件路径
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号
            total_lines: 文件总行数
            
        Returns:
            估算的token数
        """
        try:
            if raw_mode:
                # 原始模式：按每20行分组计算token
                line_groups = self._extract_line_groups(content, start_line, end_line, group_size=20)
                if line_groups:
                    import_units = self._extract_imports(filepath, content, start_line, end_line)
                    all_units = import_units + line_groups[:1]
                    # 确保id唯一
                    all_units = self._ensure_unique_ids(all_units)
                    # 按行号排序
                    all_units.sort(key=lambda u: u['start_line'])
                    sample_output = self._format_structured_output(filepath, all_units, total_lines)
                    if len(line_groups) > 1:
                        group_tokens = get_context_token_count(sample_output)
                        return group_tokens * len(line_groups)
                    else:
                        return get_context_token_count(sample_output)
            else:
                # 尝试提取语法单元
                syntax_units = self._extract_syntax_units(filepath, content, start_line, end_line)
                
                if syntax_units:
                    # 使用语法单元结构化输出格式计算token
                    import_units = self._extract_imports(filepath, content, start_line, end_line)
                    all_units = import_units + syntax_units[:1]
                    # 确保id唯一
                    all_units = self._ensure_unique_ids(all_units)
                    # 按行号排序
                    all_units.sort(key=lambda u: u['start_line'])
                    sample_output = self._format_structured_output(filepath, all_units, total_lines)
                    if len(syntax_units) > 1:
                        unit_tokens = get_context_token_count(sample_output)
                        return unit_tokens * len(syntax_units)
                    else:
                        return get_context_token_count(sample_output)
                else:
                    # 使用空白行分组格式计算token（不支持语言时）
                    # 先按空行分割，然后对超过20行的块再按每20行分割
                    line_groups = self._extract_blank_line_groups_with_split(content, start_line, end_line)
                    if line_groups:
                        import_units = self._extract_imports(filepath, content, start_line, end_line)
                        all_units = import_units + line_groups[:1]
                        # 确保id唯一
                        all_units = self._ensure_unique_ids(all_units)
                        # 按行号排序
                        all_units.sort(key=lambda u: u['start_line'])
                        sample_output = self._format_structured_output(filepath, all_units, total_lines)
                        if len(line_groups) > 1:
                            group_tokens = get_context_token_count(sample_output)
                            return group_tokens * len(line_groups)
                        else:
                            return get_context_token_count(sample_output)
                    else:
                        # 回退到原始格式计算
                        lines = content.split('\n')
                        selected_lines = lines[start_line - 1:end_line]
                        numbered_content = "".join(f"{i:5d}:{line}\n" for i, line in enumerate(selected_lines, start=start_line))
                        return get_context_token_count(numbered_content)
        except Exception:
            # 如果估算失败，使用简单的行号格式估算
            lines = content.split('\n')
            selected_lines = lines[start_line - 1:end_line]
            numbered_content = "".join(f"{i:5d}:{line}\n" for i, line in enumerate(selected_lines, start=start_line))
            return get_context_token_count(numbered_content)
    
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
        self, filepath: str, start_line: int = 1, end_line: int = -1, agent: Any = None, raw_mode: bool = False
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

            # 读取完整文件内容用于语法分析和token计算
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                full_content = f.read()
            
            # 读取要读取的行范围内容
            selected_content_lines = []
            lines = full_content.split('\n')
            for i in range(start_line - 1, min(end_line, len(lines))):
                selected_content_lines.append(lines[i])
            
            # 估算结构化输出的token数
            content_tokens = self._estimate_structured_tokens(abs_path, full_content, start_line, end_line, total_lines, raw_mode)
            
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

            # 提取导入/包含语句作为结构化单元
            import_units = self._extract_imports(abs_path, full_content, start_line, end_line)
            
            # 确定使用的结构化单元（语法单元或行号分组）
            structured_units = None
            # unit_type = None
            
            if raw_mode:
                # 原始读取模式：按每20行分组
                line_groups = self._extract_line_groups(full_content, start_line, end_line, group_size=20)
                # 合并导入单元和行号分组
                all_units = import_units + line_groups
                # 确保id唯一
                all_units = self._ensure_unique_ids(all_units)
                # 按行号排序，所有单元按在文件中的实际位置排序
                all_units.sort(key=lambda u: u['start_line'])
                structured_units = all_units
                # unit_type = "line_groups"
                output = self._format_structured_output(abs_path, structured_units, total_lines)
            else:
                # 尝试提取语法单元（结构化读取，full_content 已在上面读取）
                syntax_units = self._extract_syntax_units(abs_path, full_content, start_line, end_line)
                
                # 检测语言类型
                # language = None
                if LANGUAGE_SUPPORT_AVAILABLE:
                    try:
                        detect_language(abs_path)
                    except Exception:
                        pass
                
                if syntax_units:
                    # 合并导入单元和语法单元
                    all_units = import_units + syntax_units
                    # 确保id唯一
                    all_units = self._ensure_unique_ids(all_units)
                    # 按行号排序，所有单元按在文件中的实际位置排序
                    all_units.sort(key=lambda u: u['start_line'])
                    structured_units = all_units
                    # unit_type = "syntax_units"
                    output = self._format_structured_output(abs_path, structured_units, total_lines)
                else:
                    # 使用空白行分组结构化输出（不支持语言时）
                    # 先按空行分割，然后对超过20行的块再按每20行分割
                    line_groups = self._extract_blank_line_groups_with_split(full_content, start_line, end_line)
                    # 合并导入单元和行号分组
                    all_units = import_units + line_groups
                    # 确保id唯一
                    all_units = self._ensure_unique_ids(all_units)
                    # 按行号排序，所有单元按在文件中的实际位置排序
                    all_units.sort(key=lambda u: u['start_line'])
                    structured_units = all_units
                    # unit_type = "line_groups"
                    output = self._format_structured_output(abs_path, structured_units, total_lines)

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
                        # 读取完整文件内容用于token估算
                        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                            file_content = f.read()
                        
                        # 估算结构化输出的token数
                        raw_mode = file_info.get("raw_mode", False)
                        content_tokens = self._estimate_structured_tokens(
                            abs_path, file_content, actual_start_line, actual_end_line, total_lines, raw_mode
                        )
                        
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
                    file_info.get("raw_mode", False),
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


def main():
    """测试结构化读取功能"""
    import tempfile
    import os
    
    tool = ReadCodeTool()
    
    print("=" * 80)
    print("测试结构化读取功能")
    print("=" * 80)
    
    # 测试1: C语言文件（tree-sitter支持）
    print("\n【测试1】C语言文件 - 语法单元提取")
    print("-" * 80)
    
    c_code = """#include <stdio.h>

void main() {
    printf("Hello, World!\\n");
}

int add(int a, int b) {
    return a + b;
}

int sub(int a, int b) {
    return a - b;
}

struct Point {
    int x;
    int y;
};
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
        c_file = f.name
        f.write(c_code)
    
    try:
        result = tool.execute({
            "files": [{"path": c_file, "start_line": 1, "end_line": -1}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ C语言文件读取成功")
            print("\n输出内容:")
            print(result["stdout"])
        else:
            print(f"❌ C语言文件读取失败: {result['stderr']}")
    finally:
        os.unlink(c_file)
    
    # 测试2: Python文件（AST支持）
    print("\n【测试2】Python文件 - 语法单元提取")
    print("-" * 80)
    
    python_code = """def main():
    print("Hello, World!")

def add(a, b):
    return a + b

def sub(a, b):
    return a - b

class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        py_file = f.name
        f.write(python_code)
    
    try:
        result = tool.execute({
            "files": [{"path": py_file, "start_line": 1, "end_line": -1}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ Python文件读取成功")
            print("\n输出内容:")
            print(result["stdout"])
        else:
            print(f"❌ Python文件读取失败: {result['stderr']}")
    finally:
        os.unlink(py_file)
    
    # 测试3: 不支持的语言 - 行号分组
    print("\n【测试3】不支持的语言 - 行号分组（20行一组）")
    print("-" * 80)
    
    text_content = "\n".join([f"这是第 {i} 行内容" for i in range(1, 51)])
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        txt_file = f.name
        f.write(text_content)
    
    try:
        result = tool.execute({
            "files": [{"path": txt_file, "start_line": 1, "end_line": -1}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ 文本文件读取成功（使用行号分组）")
            print("\n输出内容（前500字符）:")
            print(result["stdout"][:500] + "..." if len(result["stdout"]) > 500 else result["stdout"])
        else:
            print(f"❌ 文本文件读取失败: {result['stderr']}")
    finally:
        os.unlink(txt_file)
    
    # 测试4: 指定行号范围
    print("\n【测试4】指定行号范围读取")
    print("-" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
        c_file2 = f.name
        f.write(c_code)
    
    try:
        result = tool.execute({
            "files": [{"path": c_file2, "start_line": 1, "end_line": 10}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ 指定范围读取成功")
            print("\n输出内容:")
            print(result["stdout"])
        else:
            print(f"❌ 指定范围读取失败: {result['stderr']}")
    finally:
        os.unlink(c_file2)
    
    # 测试5: 边界情况 - 返回边界上的语法单元
    print("\n【测试5】边界情况 - 返回边界上的语法单元")
    print("-" * 80)
    
    boundary_test_code = """def func1():
    line1 = 1
    line2 = 2
    line3 = 3

def func2():
    line1 = 1
    line2 = 2

def func3():
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        boundary_file = f.name
        f.write(boundary_test_code)
    
    try:
        # 请求第3-8行
        # func1: 1-4行（结束行4在范围内，应该返回完整func1）
        # func2: 6-8行（开始行6在范围内，应该返回完整func2）
        # func3: 10-14行（完全不在范围内，不应该返回）
        result = tool.execute({
            "files": [{"path": boundary_file, "start_line": 3, "end_line": 8}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ 边界情况测试成功")
            print("请求范围: 3-8行")
            print("预期结果:")
            print("  - func1 (1-4行): 结束行4在范围内，应返回完整func1")
            print("  - func2 (6-8行): 开始行6在范围内，应返回完整func2")
            print("  - func3 (10-14行): 完全不在范围内，不应返回")
            print("\n实际输出:")
            print(result["stdout"])
        else:
            print(f"❌ 边界情况测试失败: {result['stderr']}")
    finally:
        os.unlink(boundary_file)
    
    # 测试6: 多个文件
    print("\n【测试6】多个文件读取")
    print("-" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f1, \
         tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f2:
        c_file3 = f1.name
        py_file2 = f2.name
        f1.write(c_code)
        f2.write(python_code)
    
    try:
        result = tool.execute({
            "files": [
                {"path": c_file3, "start_line": 1, "end_line": -1},
                {"path": py_file2, "start_line": 1, "end_line": -1}
            ],
            "agent": None
        })
        
        if result["success"]:
            print("✅ 多文件读取成功")
            print("\n输出内容（前800字符）:")
            print(result["stdout"][:800] + "..." if len(result["stdout"]) > 800 else result["stdout"])
        else:
            print(f"❌ 多文件读取失败: {result['stderr']}")
    finally:
        os.unlink(c_file3)
        os.unlink(py_file2)
    
    # 测试7: 嵌套作用域的边界情况
    print("\n【测试7】嵌套作用域的边界情况")
    print("-" * 80)
    
    nested_code = """class Outer:
    def method1(self):
        line1 = 1
        line2 = 2
    
    def method2(self):
        line1 = 1
        line2 = 2
        line3 = 3

def standalone_func():
    line1 = 1
    line2 = 2
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        nested_file = f.name
        f.write(nested_code)
    
    try:
        # 请求第4-7行
        # Outer.method1: 2-4行（结束行4在范围内，应该返回完整method1）
        # Outer.method2: 6-9行（开始行6在范围内，应该返回完整method2）
        # Outer类: 1-9行（包含method1和method2，应该返回）
        # standalone_func: 11-13行（完全不在范围内，不应返回）
        result = tool.execute({
            "files": [{"path": nested_file, "start_line": 4, "end_line": 7}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ 嵌套作用域边界测试成功")
            print("请求范围: 4-7行")
            print("预期结果:")
            print("  - Outer类 (1-9行): 包含method1和method2，应返回")
            print("  - Outer.method1 (2-4行): 结束行4在范围内，应返回完整method1")
            print("  - Outer.method2 (6-9行): 开始行6在范围内，应返回完整method2")
            print("\n实际输出:")
            print(result["stdout"])
        else:
            print(f"❌ 嵌套作用域边界测试失败: {result['stderr']}")
    finally:
        os.unlink(nested_file)
    
    # 测试8: Java文件（tree-sitter支持）
    print("\n【测试8】Java文件 - 语法单元提取")
    print("-" * 80)
    
    java_code = """public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
    
    public int add(int a, int b) {
        return a + b;
    }
    
    private int subtract(int a, int b) {
        return a - b;
    }
}

class Point {
    private int x;
    private int y;
    
    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
        java_file = f.name
        f.write(java_code)
    
    try:
        result = tool.execute({
            "files": [{"path": java_file, "start_line": 1, "end_line": -1}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ Java文件读取成功")
            print("\n输出内容:")
            print(result["stdout"])
        else:
            print(f"❌ Java文件读取失败: {result['stderr']}")
    finally:
        os.unlink(java_file)
    
    # 测试9: Rust文件（tree-sitter支持）
    print("\n【测试9】Rust文件 - 语法单元提取")
    print("-" * 80)
    
    rust_code = """fn main() {
    println!("Hello, World!");
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn subtract(a: i32, b: i32) -> i32 {
    a - b
}

struct Point {
    x: i32,
    y: i32,
}

impl Point {
    fn new(x: i32, y: i32) -> Point {
        Point { x, y }
    }
}

enum Color {
    Red,
    Green,
    Blue,
}
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
        rust_file = f.name
        f.write(rust_code)
    
    try:
        result = tool.execute({
            "files": [{"path": rust_file, "start_line": 1, "end_line": -1}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ Rust文件读取成功")
            print("\n输出内容:")
            print(result["stdout"])
        else:
            print(f"❌ Rust文件读取失败: {result['stderr']}")
    finally:
        os.unlink(rust_file)
    
    # 测试10: Go文件（tree-sitter支持）
    print("\n【测试10】Go文件 - 语法单元提取")
    print("-" * 80)
    
    go_code = """package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}

func add(a int, b int) int {
    return a + b
}

func subtract(a int, b int) int {
    return a - b
}

type Point struct {
    x int
    y int
}

func (p *Point) New(x int, y int) {
    p.x = x
    p.y = y
}

type Color int

const (
    Red Color = iota
    Green
    Blue
)

type Shape interface {
    Area() float64
    Perimeter() float64
}

type Drawable interface {
    Draw()
}
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
        go_file = f.name
        f.write(go_code)
    
    try:
        result = tool.execute({
            "files": [{"path": go_file, "start_line": 1, "end_line": -1}],
            "agent": None
        })
        
        if result["success"]:
            print("✅ Go文件读取成功")
            print("\n输出内容:")
            print(result["stdout"])
        else:
            print(f"❌ Go文件读取失败: {result['stderr']}")
    finally:
        os.unlink(go_file)
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
