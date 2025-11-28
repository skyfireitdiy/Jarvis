# -*- coding: utf-8 -*-
import os
import time
from typing import Any, Dict, List

from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count

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
    
    def _extract_syntax_units_with_split(
        self, filepath: str, content: str, start_line: int, end_line: int
    ) -> List[Dict[str, Any]]:
        """提取语法单元，然后对超过50行的单元再按每50行分割
        
        Args:
            filepath: 文件路径
            content: 文件内容
            start_line: 起始行号
            end_line: 结束行号
            
        Returns:
            语法单元列表，每个单元不超过50行
        """
        # 先获取语法单元
        syntax_units = self._extract_syntax_units(filepath, content, start_line, end_line)
        
        if not syntax_units:
            return []
        
        result = []
        for unit in syntax_units:
            unit_line_count = unit['end_line'] - unit['start_line'] + 1
            if unit_line_count > 50:
                # 如果单元超过50行，按每50行分割
                sub_groups = self._extract_line_groups(
                    content, unit['start_line'], unit['end_line'], group_size=50
                )
                result.extend(sub_groups)
            else:
                # 如果单元不超过50行，直接添加
                result.append(unit)
        
        return result
    
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
        self, filepath: str, units: List[Dict[str, Any]], total_lines: int, agent: Any = None
    ) -> str:
        """格式化结构化输出
        
        Args:
            filepath: 文件路径
            units: 语法单元或行号分组列表（已包含导入语句单元）
            total_lines: 文件总行数
            agent: Agent实例，用于从缓存中获取block_id
            
        Returns:
            格式化后的输出字符串
        """
        # 文件开始分界符
        output_lines = [
            "=" * 80,
            f"🔍 文件: {filepath}",
            f"📄 总行数: {total_lines}",
            f"📦 结构化单元数: {len(units)}",
            "=" * 80,
            "",
        ]
        
        # 为每个单元分配block-id
        # 如果unit已经有block_id（从缓存中获取），直接使用；否则按顺序生成
        for idx, unit in enumerate(units, start=1):
            # 如果unit已经有block_id，直接使用（在生成structured_units时已分配）
            block_id = unit.get('block_id')
            if not block_id:
                # 否则按顺序生成临时id
                block_id = f"block-{idx}"
            # 显示id
            output_lines.append(f"[id:{block_id}]")
            # 添加内容，保持原有缩进，并为每行添加行号
            content = unit.get('content', '')
            if content:
                # 获取单元的起始行号
                start_line = unit.get('start_line', 1)
                # 将内容按行分割
                content_lines = content.split('\n')
                # 为每一行添加行号（右对齐，4位，不足补空格）
                numbered_lines = []
                current_line = start_line
                for line in content_lines:
                    # 行号右对齐，占4位
                    line_number_str = f"{current_line:4d}"
                    numbered_lines.append(f"{line_number_str}:{line}")
                    current_line += 1
                # 将带行号的内容添加到输出
                output_lines.append('\n'.join(numbered_lines))
            # 块结束分界符
            output_lines.append("-" * 80)
            output_lines.append("")  # 单元之间空行分隔
        
        # 文件结束分界符
        output_lines.append("=" * 80)
        output_lines.append("")
        
        return '\n'.join(output_lines)
    
    def _get_file_cache(self, agent: Any, filepath: str) -> Dict[str, Any]:
        """获取文件的缓存信息
        
        Args:
            agent: Agent实例
            filepath: 文件路径
            
        Returns:
            缓存信息字典，如果不存在则返回None
        """
        if not agent:
            return None
        
        cache = agent.get_user_data("read_code_cache")
        if not cache:
            return None
        
        abs_path = os.path.abspath(filepath)
        return cache.get(abs_path)
    
    def _get_blocks_from_cache(self, cache_info: Dict[str, Any], start_line: int, end_line: int) -> List[Dict[str, Any]]:
        """从缓存中获取对应范围的blocks
        
        Args:
            cache_info: 缓存信息
            start_line: 起始行号（1-based）
            end_line: 结束行号（1-based，-1表示文件末尾）
            
        Returns:
            blocks列表，每个block包含block_id和content
        """
        if not cache_info or "id_list" not in cache_info or "blocks" not in cache_info:
            return []
        
        id_list = cache_info.get("id_list", [])
        blocks = cache_info.get("blocks", {})
        result = []
        
        # 如果end_line是-1，表示文件末尾，需要先计算文件总行数
        if end_line == -1:
            # 先遍历所有blocks计算总行数
            # 注意：块内容不包含末尾换行符，块之间需要添加换行符
            total_lines = 0
            for idx, block_id in enumerate(id_list):
                block_data = blocks.get(block_id)
                if block_data:
                    block_content = block_data.get("content", "")
                    if block_content:
                        # 块内容中的换行符数量 + 1 = 行数
                        block_line_count = block_content.count('\n') + 1
                        total_lines += block_line_count
                        # 如果不是最后一个块，块之间有一个换行符分隔（已计入下一个块的第一行）
                        # 所以不需要额外添加
            end_line = total_lines
        
        # 通过前面blocks的内容推算每个block的行号范围
        # 注意：块内容不包含末尾换行符，块之间需要添加换行符
        current_line = 1  # 从第1行开始
        
        for idx, block_id in enumerate(id_list):
            block_data = blocks.get(block_id)
            if not block_data:
                continue
            block_content = block_data.get("content", "")
            if not block_content:
                continue
            
            # 计算这个block的行数
            # 块内容中的换行符数量 + 1 = 行数（因为块内容不包含末尾换行符）
            block_line_count = block_content.count('\n') + 1
            
            block_start_line = current_line
            block_end_line = current_line + block_line_count - 1
            
            # block与请求范围有重叠就包含
            if block_end_line >= start_line and block_start_line <= end_line:
                result.append({
                    "block_id": block_id,
                    "content": block_content,
                    "start_line": block_start_line,
                })
            
            # 更新当前行号
            # 块之间有一个换行符分隔，所以下一个块从 block_end_line + 1 开始
            current_line = block_end_line + 1
            
            # 如果已经超过请求的结束行，可以提前退出
            if block_start_line > end_line:
                break
        
        return result
    
    def _convert_units_to_sequential_ids(self, units: List[Dict[str, Any]], full_content: str = None) -> Dict[str, Any]:
        """将单元列表转换为缓存格式（id_list和blocks字典）
        
        按照行号范围分割文件，不区分语法单元，确保完美恢复。
        
        Args:
            units: 结构化单元列表，每个单元包含 id, start_line, end_line, content
            full_content: 完整的文件内容（可选），用于确保块之间的空白行也被包含
            
        Returns:
            包含 id_list 和 blocks 的字典：
            - id_list: 有序的id列表，如 ["block-1", "block-2", "block-3"]
            - blocks: id到块信息的字典，如 {"block-1": {"content": "..."}, ...}
        """
        if not full_content or not units:
            # 没有完整内容，直接使用原始的content
            sorted_original = sorted(units, key=lambda u: u.get('start_line', 0))
            id_list = []
            blocks = {}
            for unit in sorted_original:
                block_id = f"block-{len(id_list) + 1}"  # block-1, block-2, ...
                id_list.append(block_id)
                content = unit.get('content', '')
                # 去掉块末尾的换行符
                if content.endswith('\n'):
                    content = content[:-1]
                blocks[block_id] = {
                    "content": content,
                }
            return {
                "id_list": id_list,
                "blocks": blocks,
                "file_ends_with_newline": False,  # 无法确定，默认False
            }
        
        # 收集所有单元的开始行号作为分割点
        # 关键：直接使用每个单元的start_line，不合并范围，保留语法单元边界
        split_points_set = {1}  # 从第1行开始
        for unit in units:
            start_line = unit.get('start_line', 1)
            if start_line > 0:
                split_points_set.add(start_line)
        
        if not split_points_set:
            # 没有有效的分割点，返回空列表
            return {"id_list": [], "blocks": {}, "file_ends_with_newline": False}
        
        # 按照每个单元的开始行作为分割点，连续分割文件内容
        # 每个块包含从当前分割点到下一个分割点之前的所有内容
        # 关键：直接按行号范围从原始内容中提取，确保完美恢复（包括文件末尾的换行符和所有空白行）
        # 使用 split('\n') 分割，然后手动为每行添加换行符（除了最后一行，根据原始文件决定）
        lines = full_content.split('\n')
        result_units = []
        
        # 排序分割点
        split_points = sorted(split_points_set)
        split_points.append(len(lines) + 1)  # 文件末尾
        
        # 按照分割点连续分割文件
        # 注意：如果文件以换行符结尾，split('\n')会在末尾产生一个空字符串
        # 我们需要正确处理这种情况
        file_ends_with_newline = full_content.endswith('\n')
        
        for idx in range(len(split_points) - 1):
            start_line = split_points[idx]  # 1-based
            next_start_line = split_points[idx + 1]  # 1-based
            
            # 提取从当前分割点到下一个分割点之前的所有内容
            unit_start_idx = max(0, start_line - 1)  # 0-based索引
            unit_end_idx = min(len(lines) - 1, next_start_line - 2)  # 0-based索引，下一个分割点之前
            
            # 确保索引有效
            if unit_start_idx <= unit_end_idx:
                # 提取行并重新组合，确保保留所有换行符
                extracted_lines = lines[unit_start_idx:unit_end_idx + 1]
                
                # 重新组合：每行后面添加换行符
                # 对于非最后一个块，最后一行也需要换行符，因为下一个块从下一行开始
                # 对于最后一个块，根据原始文件是否以换行符结尾来决定
                full_unit_content_parts = []
                is_last_block = (idx == len(split_points) - 2)
                
                for i, line in enumerate(extracted_lines):
                    if i < len(extracted_lines) - 1:
                        # 不是最后一行，添加换行符
                        full_unit_content_parts.append(line + '\n')
                    else:
                        # 最后一行
                        if not is_last_block:
                            # 非最后一个块：最后一行必须添加换行符，因为下一个块从下一行开始
                            # 这样可以保留块之间的空白行
                            full_unit_content_parts.append(line + '\n')
                        else:
                            # 最后一个块：需要特殊处理
                            # 如果文件以换行符结尾，且最后一行是空字符串（来自split('\n')的副作用），
                            # 且不是唯一的一行，那么前面的行已经输出了换行符，这里不需要再输出
                            if file_ends_with_newline and line == '' and len(extracted_lines) > 1:
                                # 最后一行是空字符串且来自trailing newline，且不是唯一的一行
                                # 前面的行已经输出了换行符，所以这里不需要再输出任何内容
                                # 空字符串表示不输出任何内容
                                full_unit_content_parts.append('')
                            elif file_ends_with_newline:
                                # 文件以换行符结尾，最后一行需要换行符
                                full_unit_content_parts.append(line + '\n')
                            else:
                                # 文件不以换行符结尾
                                full_unit_content_parts.append(line)
                
                full_unit_content = ''.join(full_unit_content_parts)
                
                # 去掉块末尾的换行符（存储时去掉，恢复时再添加）
                if full_unit_content.endswith('\n'):
                    full_unit_content = full_unit_content[:-1]
                
                block_id = f"block-{len(result_units) + 1}"  # block-1, block-2, ...
                result_units.append({
                    "id": block_id,
                    "content": full_unit_content,
                })
        
        # 转换为 id_list 和 blocks 格式
        id_list = [unit["id"] for unit in result_units]
        blocks = {
            unit["id"]: {
                "content": unit["content"],
            }
            for unit in result_units
        }
        
        # 保存文件是否以换行符结尾的信息（用于恢复时正确处理）
        file_ends_with_newline = full_content.endswith('\n')
        
        return {
            "id_list": id_list,
            "blocks": blocks,
            "file_ends_with_newline": file_ends_with_newline,
        }
    
    def _save_file_cache(
        self, agent: Any, filepath: str, units: List[Dict[str, Any]], 
        total_lines: int, file_mtime: float, full_content: str = None
    ) -> None:
        """保存文件的结构化信息到缓存
        
        Args:
            agent: Agent实例
            filepath: 文件路径
            units: 结构化单元列表
            total_lines: 文件总行数
            file_mtime: 文件修改时间
            full_content: 完整的文件内容（可选），用于确保块之间的空白行也被包含
        """
        if not agent:
            return
        
        cache = agent.get_user_data("read_code_cache")
        if not cache:
            cache = {}
            agent.set_user_data("read_code_cache", cache)
        
        abs_path = os.path.abspath(filepath)
        
        # 转换为 id_list 和 blocks 格式
        cache_data = self._convert_units_to_sequential_ids(units, full_content)
        
        cache[abs_path] = {
            "id_list": cache_data["id_list"],
            "blocks": cache_data["blocks"],
            "total_lines": total_lines,
            "read_time": time.time(),
            "file_mtime": file_mtime,
            "file_ends_with_newline": cache_data.get("file_ends_with_newline", False),
        }
        agent.set_user_data("read_code_cache", cache)
    
    def _is_cache_valid(self, cache_info: Dict[str, Any], filepath: str) -> bool:
        """检查缓存是否有效
        
        Args:
            cache_info: 缓存信息字典
            filepath: 文件路径
            
        Returns:
            True表示缓存有效，False表示缓存无效
        """
        if not cache_info:
            return False
        
        try:
            # 检查文件是否存在
            if not os.path.exists(filepath):
                return False
            
            # 检查文件修改时间是否变化
            current_mtime = os.path.getmtime(filepath)
            cached_mtime = cache_info.get("file_mtime")
            
            if cached_mtime is None or abs(current_mtime - cached_mtime) > 0.1:  # 允许0.1秒的误差
                return False
            
            # 检查缓存数据结构是否完整
            if "id_list" not in cache_info or "blocks" not in cache_info or "total_lines" not in cache_info:
                return False
            
            return True
        except Exception:
            return False
    
    def _restore_file_from_cache(self, cache_info: Dict[str, Any]) -> str:
        """从缓存恢复文件内容
        
        Args:
            cache_info: 缓存信息字典
            
        Returns:
            恢复的文件内容字符串（与原始文件内容完全一致）
        """
        if not cache_info:
            return ""
        
        # 按照 id_list 的顺序恢复
        id_list = cache_info.get("id_list", [])
        blocks = cache_info.get("blocks", {})
        file_ends_with_newline = cache_info.get("file_ends_with_newline", False)
        
        result = []
        for idx, block_id in enumerate(id_list):
            block = blocks.get(block_id)
            if block:
                content = block.get('content', '')
                if content:
                    result.append(content)
                    # 在块之间添加换行符（最后一个块后面根据文件是否以换行符结尾决定）
                    is_last_block = (idx == len(id_list) - 1)
                    if is_last_block:
                        # 最后一个块：如果文件以换行符结尾，添加换行符
                        if file_ends_with_newline:
                            result.append('\n')
                    else:
                        # 非最后一个块：在块之间添加换行符
                        result.append('\n')
        
        return ''.join(result) if result else ""
    
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
                # 尝试提取语法单元（确保每个单元不超过50行）
                syntax_units = self._extract_syntax_units_with_split(filepath, content, start_line, end_line)
                
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
                    # 使用剩余token的2/3作为限制，保留1/3作为安全余量
                    limit_tokens = int(remaining_tokens * 2 / 3)
                    # 确保至少返回一个合理的值
                    if limit_tokens > 0:
                        return limit_tokens
                except Exception:
                    pass
            
            # 回退方案：使用输入窗口的2/3
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

            # 获取文件修改时间
            file_mtime = os.path.getmtime(abs_path)
            
            # 检查缓存是否有效
            cache_info = self._get_file_cache(agent, abs_path)
            use_cache = self._is_cache_valid(cache_info, abs_path)

            # 读取完整文件内容用于语法分析和token计算
            if use_cache:
                # 从缓存恢复文件内容
                full_content = self._restore_file_from_cache(cache_info)
                # 如果恢复失败，重新读取文件
                if not full_content:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        full_content = f.read()
            else:
                # 读取文件内容
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
                
                # 计算安全读取的行数 (按比例缩减)
                safe_lines = int((max_token_limit / content_tokens) * read_lines)
                safe_lines = max(1, min(safe_lines, read_lines))
                safe_end_line = start_line + safe_lines - 1
                
                # 读取安全范围内的内容
                selected_content_lines = []
                for i in range(start_line - 1, min(safe_end_line, len(lines))):
                    selected_content_lines.append(lines[i])
                
                # 构造部分读取结果
                partial_content = '\n'.join(selected_content_lines)
                
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

            # 生成整个文件的结构化信息（用于缓存）
            # 提取整个文件的导入/包含语句
            full_import_units = self._extract_imports(abs_path, full_content, 1, total_lines)
            
            # 生成整个文件的结构化单元
            full_structured_units = None
            
            if raw_mode:
                # 原始读取模式：按每20行分组（整个文件）
                full_line_groups = self._extract_line_groups(full_content, 1, total_lines, group_size=20)
                # 合并导入单元和行号分组
                full_all_units = full_import_units + full_line_groups
                # 确保id唯一
                full_all_units = self._ensure_unique_ids(full_all_units)
                # 按行号排序
                full_all_units.sort(key=lambda u: u['start_line'])
                full_structured_units = full_all_units
            else:
                # 尝试提取整个文件的语法单元（确保每个单元不超过50行）
                full_syntax_units = self._extract_syntax_units_with_split(abs_path, full_content, 1, total_lines)
                
                # 检测语言类型
                if LANGUAGE_SUPPORT_AVAILABLE:
                    try:
                        detect_language(abs_path)
                    except Exception:
                        pass
                
                if full_syntax_units:
                    # 合并导入单元和语法单元
                    full_all_units = full_import_units + full_syntax_units
                    # 确保id唯一
                    full_all_units = self._ensure_unique_ids(full_all_units)
                    # 按行号排序
                    full_all_units.sort(key=lambda u: u['start_line'])
                    full_structured_units = full_all_units
                else:
                    # 使用空白行分组结构化输出（不支持语言时）
                    # 先按空行分割，然后对超过20行的块再按每20行分割（整个文件）
                    full_line_groups = self._extract_blank_line_groups_with_split(full_content, 1, total_lines)
                    # 合并导入单元和行号分组
                    full_all_units = full_import_units + full_line_groups
                    # 确保id唯一
                    full_all_units = self._ensure_unique_ids(full_all_units)
                    # 按行号排序
                    full_all_units.sort(key=lambda u: u['start_line'])
                    full_structured_units = full_all_units
            
            # 保存整个文件的结构化信息到缓存
            if full_structured_units is not None:
                self._save_file_cache(agent, abs_path, full_structured_units, total_lines, file_mtime, full_content)
            
            # 如果缓存有效，直接使用缓存中的blocks输出
            if agent:
                cache_info = self._get_file_cache(agent, abs_path)
                if cache_info and self._is_cache_valid(cache_info, abs_path):
                    # 直接从缓存中获取对应范围的blocks
                    cached_blocks = self._get_blocks_from_cache(cache_info, start_line, end_line)
                    if cached_blocks:
                        # 转换为units格式（用于输出）
                        structured_units = []
                        for block in cached_blocks:
                            structured_units.append({
                                "block_id": block["block_id"],
                                "content": block["content"],
                            })
                        output = self._format_structured_output(abs_path, structured_units, total_lines, agent)
                    else:
                        output = ""
                else:
                    # 缓存无效，重新提取units
                    # 提取请求范围的结构化单元（用于输出）
                    import_units = self._extract_imports(abs_path, full_content, start_line, end_line)
                    
                    # 确定使用的结构化单元（语法单元或行号分组）
                    structured_units = None
                    
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
                    else:
                        # 尝试提取语法单元（结构化读取，full_content 已在上面读取，确保每个单元不超过50行）
                        syntax_units = self._extract_syntax_units_with_split(abs_path, full_content, start_line, end_line)
                        
                        if syntax_units:
                            # 合并导入单元和语法单元
                            all_units = import_units + syntax_units
                            # 确保id唯一
                            all_units = self._ensure_unique_ids(all_units)
                            # 按行号排序，所有单元按在文件中的实际位置排序
                            all_units.sort(key=lambda u: u['start_line'])
                            structured_units = all_units
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
                    
                    if structured_units:
                        output = self._format_structured_output(abs_path, structured_units, total_lines, agent)
                    else:
                        output = ""
            else:
                # 没有agent，无法使用缓存，重新提取units
                import_units = self._extract_imports(abs_path, full_content, start_line, end_line)
                
                if raw_mode:
                    line_groups = self._extract_line_groups(full_content, start_line, end_line, group_size=20)
                    all_units = import_units + line_groups
                    all_units = self._ensure_unique_ids(all_units)
                    all_units.sort(key=lambda u: u['start_line'])
                    structured_units = all_units
                else:
                    syntax_units = self._extract_syntax_units_with_split(abs_path, full_content, start_line, end_line)
                    if syntax_units:
                        all_units = import_units + syntax_units
                        all_units = self._ensure_unique_ids(all_units)
                        all_units.sort(key=lambda u: u['start_line'])
                        structured_units = all_units
                    else:
                        line_groups = self._extract_blank_line_groups_with_split(full_content, start_line, end_line)
                        all_units = import_units + line_groups
                        all_units = self._ensure_unique_ids(all_units)
                        all_units.sort(key=lambda u: u['start_line'])
                        structured_units = all_units
                
                if structured_units:
                    output = self._format_structured_output(abs_path, structured_units, total_lines, agent)
                else:
                    output = ""

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
            print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": f"文件读取失败: {str(e)}"}

    def _handle_merged_ranges(
        self, filepath: str, requests: List[Dict], agent: Any = None
    ) -> Dict[str, Any]:
        """处理同一文件的多个范围请求，合并后去重
        
        Args:
            filepath: 文件绝对路径
            requests: 范围请求列表，每个请求包含 start_line, end_line, raw_mode
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
                full_content = f.read()
            
            total_lines = len(full_content.split('\n'))
            if total_lines == 0:
                return {
                    "success": True,
                    "stdout": f"\n🔍 文件: {filepath}\n📄 文件为空 (0行)\n",
                    "stderr": "",
                }
            
            # 先确保缓存存在（通过读取整个文件建立缓存）
            first_request = requests[0]
            self._handle_single_file(
                filepath, 1, -1, agent, first_request.get("raw_mode", False)
            )
            
            # 获取缓存
            cache_info = self._get_file_cache(agent, filepath)
            if not cache_info or not self._is_cache_valid(cache_info, filepath):
                # 缓存无效，使用合并范围的方式去重
                # 合并所有范围，计算最小起始行和最大结束行
                min_start = float('inf')
                max_end = 0
                raw_mode = False
                for req in requests:
                    start_line = req.get("start_line", 1)
                    end_line = req.get("end_line", -1)
                    raw_mode = raw_mode or req.get("raw_mode", False)
                    
                    # 处理特殊值
                    if end_line == -1:
                        end_line = total_lines
                    else:
                        end_line = max(1, min(end_line, total_lines)) if end_line >= 0 else total_lines + end_line + 1
                    start_line = max(1, min(start_line, total_lines)) if start_line >= 0 else total_lines + start_line + 1
                    
                    min_start = min(min_start, start_line)
                    max_end = max(max_end, end_line)
                
                # 用合并后的范围读取一次，自然就去重了
                result = self._handle_single_file(
                    filepath, int(min_start), int(max_end), agent, raw_mode
                )
                return result
            
            # 收集所有范围覆盖的块ID（去重）
            seen_block_ids = set()
            merged_blocks = []
            
            for req in requests:
                start_line = req.get("start_line", 1)
                end_line = req.get("end_line", -1)
                
                # 处理特殊值
                if end_line == -1:
                    end_line = total_lines
                else:
                    end_line = max(1, min(end_line, total_lines)) if end_line >= 0 else total_lines + end_line + 1
                start_line = max(1, min(start_line, total_lines)) if start_line >= 0 else total_lines + start_line + 1
                
                # 从缓存获取对应范围的块
                cached_blocks = self._get_blocks_from_cache(cache_info, start_line, end_line)
                for block in cached_blocks:
                    block_id = block["block_id"]
                    if block_id not in seen_block_ids:
                        seen_block_ids.add(block_id)
                        merged_blocks.append(block)
            
            # 按block_id排序（block-1, block-2, ...）
            def extract_block_num(block):
                block_id = block.get("block_id", "block-0")
                try:
                    return int(block_id.split("-")[1])
                except (IndexError, ValueError):
                    return 0
            
            merged_blocks.sort(key=extract_block_num)
            
            # 转换为units格式并格式化输出
            structured_units = []
            for block in merged_blocks:
                structured_units.append({
                    "block_id": block["block_id"],
                    "content": block["content"],
                })
            
            output = self._format_structured_output(filepath, structured_units, total_lines, agent)
            
            # 尝试获取上下文信息（使用合并后的范围）
            all_start_lines = [req.get("start_line", 1) for req in requests]
            all_end_lines = [req.get("end_line", total_lines) for req in requests]
            min_start = min(all_start_lines)
            max_end = max(all_end_lines)
            context_info = self._get_file_context(filepath, min_start, max_end, agent)
            if context_info:
                output += context_info
            
            return {"success": True, "stdout": output, "stderr": ""}
            
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"合并范围读取失败: {str(e)}"}

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
            print(f"🧠 正在分析代码上下文 ({file_name}, {line_info})...")

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
                # 对符号去重（基于 name + file_path + line_start）
                seen_symbols = set()
                unique_symbols = []
                for s in edit_context.used_symbols:
                    key = (s.name, getattr(s, 'file_path', ''), getattr(s, 'line_start', 0))
                    if key not in seen_symbols:
                        seen_symbols.add(key)
                        unique_symbols.append(s)
                
                # 区分定义和调用，显示定义位置信息
                definitions = []
                calls = []
                for symbol in unique_symbols[:10]:
                    is_def = getattr(symbol, 'is_definition', False)
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
                        def_loc = getattr(symbol, 'definition_location', None)
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

            # 不再感知导入符号

            if edit_context.relevant_files:
                # 对相关文件去重
                unique_files = list(dict.fromkeys(edit_context.relevant_files))
                rel_files = unique_files[:10]
                files_str = "\n   ".join(f"• {os.path.relpath(f, context_manager.project_root)}" for f in rel_files)
                more = len(unique_files) - 10
                if more > 0:
                    files_str += f"\n   ... 还有{more}个相关文件"
                context_lines.append(f"📁 相关文件 ({len(unique_files)}个):\n   {files_str}")

            context_lines.append("─" * 60)
            context_lines.append("")  # 空行

            # 打印上下文感知结果到控制台
            context_output = "\n".join(context_lines)
            print(f"🧠 上下文感知结果:\n{context_output}")
            
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
                        file_info.get("raw_mode", False),
                    )
                    if result["success"]:
                        all_outputs.append(result["stdout"])
                        status_lines.append(f"✅ {file_info['path']} 文件读取成功")
                    else:
                        all_outputs.append(f"❌ {file_info['path']}: {result['stderr']}")
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
                        status_lines.append(f"✅ {display_path} 文件读取成功 (合并{len(requests)}个范围请求，已去重)")
                    else:
                        all_outputs.append(f"❌ {display_path}: {merged_result['stderr']}")
                        status_lines.append(f"❌ {display_path} 文件读取失败")
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
            print(f"❌ {str(e)}")
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
