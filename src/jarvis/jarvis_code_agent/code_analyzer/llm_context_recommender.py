"""智能上下文推荐器。

使用LLM进行语义理解，提供更准确的上下文推荐。
完全基于LLM实现，不依赖硬编码规则。
"""


import os
import re
import yaml
from typing import List, Optional, Dict, Any, Set

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

from .context_recommender import ContextRecommendation
from .context_manager import ContextManager
from .file_ignore import filter_walk_dirs
from .symbol_extractor import Symbol


class ContextRecommender:
    """智能上下文推荐器。
    
    使用LLM进行语义理解，根据编辑意图推荐相关的上下文信息。
    完全基于LLM实现，提供语义级别的推荐，而非简单的关键词匹配。
    """

    def __init__(self, context_manager: ContextManager, llm_model: Any):
        """初始化上下文推荐器
        
        Args:
            context_manager: 上下文管理器
            llm_model: LLM模型实例（必需）
            
        Raises:
            ValueError: 如果未提供LLM模型
        """
        self.context_manager = context_manager
        self.llm_model = llm_model
        
        if not llm_model:
            raise ValueError("LLM model is required for context recommendation")

    def recommend_context(
        self,
        user_input: str,
    ) -> ContextRecommendation:
        """根据编辑意图推荐上下文
        
        Args:
            user_input: 用户输入/任务描述
            
        Returns:
            ContextRecommendation: 推荐的上下文信息
        """
        # 1. 使用LLM提取关键词（仅提取关键词）
        keywords = self._extract_keywords_with_llm(user_input)
        
        # 2. 初始化推荐结果
        recommended_files: Set[str] = set()
        recommended_symbols: List[Symbol] = []
        related_tests: Set[str] = set()
        reasons: List[str] = []

        # 3. 基于关键词进行符号查找和文本查找，然后使用LLM挑选关联度高的条目（主要推荐方式）
        if keywords:
            # 3.1 使用关键词进行符号查找和文本查找，找到所有候选符号及其位置
            candidate_symbols = self._search_symbols_by_keywords(keywords)
            candidate_symbols_from_text = self._search_text_by_keywords(keywords)
            
            # 合并候选符号（去重）
            all_candidates = {}
            for symbol in candidate_symbols + candidate_symbols_from_text:
                # 使用 (file_path, name, line_start) 作为唯一键
                key = (symbol.file_path, symbol.name, symbol.line_start)
                if key not in all_candidates:
                    all_candidates[key] = symbol
            
            candidate_symbols_list = list(all_candidates.values())
            
            # 3.2 使用LLM从候选符号中挑选关联度高的条目
            if candidate_symbols_list:
                selected_symbols = self._select_relevant_symbols_with_llm(
                    user_input, keywords, candidate_symbols_list
                )
                recommended_symbols.extend(selected_symbols)
                
                # 从选中的符号中提取文件
                for symbol in selected_symbols:
                    recommended_files.add(symbol.file_path)
                
                if selected_symbols:
                    reasons.append(f"基于关键词（{', '.join(keywords[:5])}）的符号查找与LLM筛选")

        # 4. 使用LLM对推荐结果进行相关性评分和排序
        file_scores = self._score_files_with_llm(
            user_input,
            list(recommended_files),
        )
        scored_symbols = self._score_symbols_with_llm(
            user_input,
            recommended_symbols,
        )
        
        # 5. 过滤和排序
        # 按评分和修改时间对文件排序，并选择最相关的10个
        if file_scores:
            final_files = sorted(
                list(recommended_files),
                key=lambda f: (file_scores.get(f, 5.0), os.path.getmtime(f)),
                reverse=True
            )[:10]
        else:
            final_files = sorted(list(recommended_files), key=os.path.getmtime, reverse=True)[:10]
        
        final_symbols = [s for s, _ in sorted(scored_symbols.items(), key=lambda x: x[1], reverse=True)[:10]]
        
        # 6. 更新推荐原因
        reason = "；".join(reasons[:3]) if reasons else "基于LLM关键词语义分析"
        if len(reasons) > 3:
            reason += f" 等{len(reasons)}个原因"
        if keywords:
            reason = f"基于关键词（{', '.join(keywords[:5])}）的LLM语义分析；{reason}"

        return ContextRecommendation(
            recommended_files=final_files,
            recommended_symbols=final_symbols,
            related_tests=list(related_tests),
            reason=reason,
        )

    def _extract_keywords_with_llm(self, user_input: str) -> List[str]:
        """使用LLM提取关键词（仅提取关键词）
        
        Args:
            user_input: 用户输入
            
        Returns:
            关键词列表
        """
        prompt = f"""分析以下代码编辑任务，提取关键词。关键词应该是与任务相关的核心概念、技术术语、功能模块等。

任务描述：
{user_input}

请提取5-10个关键词，以YAML数组格式返回，并用<KEYWORDS>标签包裹。
只返回关键词数组，不要包含其他文字。

示例格式：
<KEYWORDS>
- data processing
- validation
- error handling
- API endpoint
- authentication
</KEYWORDS>
"""

        try:
            response = self._call_llm(prompt)
            # 从<KEYWORDS>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<KEYWORDS>\s*(.*?)\s*</KEYWORDS>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            keywords = yaml.safe_load(yaml_content)
            if not isinstance(keywords, list):
                return []
            
            # 过滤空字符串和过短的关键词
            keywords = [k.strip() for k in keywords if k and isinstance(k, str) and len(k.strip()) > 1]
            return keywords
        except Exception as e:
            # 解析失败，返回空列表
            PrettyOutput.print(f"LLM关键词提取失败: {e}", OutputType.WARNING)
            return []

    def _search_symbols_by_keywords(self, keywords: List[str]) -> List[Symbol]:
        """基于关键词在符号表中查找相关符号
        
        Args:
            keywords: 关键词列表
            
        Returns:
            候选符号列表
        """
        if not keywords:
            return []
        
        found_symbols: List[Symbol] = []
        keywords_lower = [k.lower() for k in keywords]
        found_symbol_keys = set()  # 用于去重，使用 (file_path, name, line_start) 作为键
        
        # 遍历所有符号，查找名称或签名中包含关键词的符号
        for symbol_name, symbols in self.context_manager.symbol_table.symbols_by_name.items():
            symbol_name_lower = symbol_name.lower()
            
            # 检查符号名称是否包含任何关键词
            name_matched = False
            for keyword in keywords_lower:
                if keyword in symbol_name_lower:
                    # 找到匹配的符号，添加所有同名符号（可能有重载）
                    for symbol in symbols:
                        key = (symbol.file_path, symbol.name, symbol.line_start)
                        if key not in found_symbol_keys:
                            found_symbols.append(symbol)
                            found_symbol_keys.add(key)
                    name_matched = True
                    break
            
            # 如果名称不匹配，检查符号签名是否包含关键词
            if not name_matched:
                for symbol in symbols:
                    if symbol.signature:
                        signature_lower = symbol.signature.lower()
                        for keyword in keywords_lower:
                            if keyword in signature_lower:
                                key = (symbol.file_path, symbol.name, symbol.line_start)
                                if key not in found_symbol_keys:
                                    found_symbols.append(symbol)
                                    found_symbol_keys.add(key)
                                break
        
        return found_symbols

    def _search_text_by_keywords(self, keywords: List[str]) -> List[Symbol]:
        """基于关键词在文件内容中进行文本查找，找到相关符号
        
        Args:
            keywords: 关键词列表
            
        Returns:
            候选符号列表（在包含关键词的文件中找到的符号）
        """
        if not keywords:
            return []
        
        found_symbols: List[Symbol] = []
        keywords_lower = [k.lower() for k in keywords]
        
        # 获取所有已分析的文件
        all_files = set()
        for symbol_name, symbols in self.context_manager.symbol_table.symbols_by_name.items():
            for symbol in symbols:
                all_files.add(symbol.file_path)
        
        # 在文件内容中搜索关键词
        for file_path in all_files:
            content = self.context_manager._get_file_content(file_path)
            if not content:
                continue
            
            content_lower = content.lower()
            
            # 检查文件内容是否包含任何关键词
            file_matches = False
            for keyword in keywords_lower:
                if keyword in content_lower:
                    file_matches = True
                    break
            
            if file_matches:
                # 获取该文件中的所有符号
                file_symbols = self.context_manager.symbol_table.get_file_symbols(file_path)
                found_symbols.extend(file_symbols)
        
        return found_symbols

    def _select_relevant_symbols_with_llm(
        self, user_input: str, keywords: List[str], candidate_symbols: List[Symbol]
    ) -> List[Symbol]:
        """使用LLM从候选符号中挑选关联度高的条目
        
        Args:
            user_input: 用户输入/任务描述
            keywords: 关键词列表
            candidate_symbols: 候选符号列表（包含位置信息）
            
        Returns:
            选中的符号列表
        """
        if not candidate_symbols:
            return []
        
        # 限制候选符号数量，避免prompt过长
        candidates_to_consider = candidate_symbols[:100]  # 最多100个候选
        
        # 构建带编号的符号信息列表（包含位置信息）
        symbol_info_list = []
        for idx, symbol in enumerate(candidates_to_consider, start=1):
            symbol_info = {
                "序号": idx,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": os.path.relpath(symbol.file_path, self.context_manager.project_root),
                "line": symbol.line_start,
                "signature": symbol.signature or "",
            }
            symbol_info_list.append(symbol_info)
        
        prompt = f"""根据以下任务描述和关键词，从候选符号列表中选择最相关的符号。

任务描述：{user_input}
关键词：{', '.join(keywords)}

候选符号列表（已编号，包含位置信息）：
{yaml.dump(symbol_info_list, allow_unicode=True, default_flow_style=False)}

请返回最相关的10-20个符号的序号（YAML数组格式），按相关性排序，并用<SELECTED_INDICES>标签包裹。

只返回序号数组，例如：
<SELECTED_INDICES>
- 3
- 7
- 12
- 15
- 23
</SELECTED_INDICES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SELECTED_INDICES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<SELECTED_INDICES>\s*(.*?)\s*</SELECTED_INDICES>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            selected_indices = yaml.safe_load(yaml_content)
            if not isinstance(selected_indices, list):
                return []
            
            # 根据序号查找对应的符号对象
            selected_symbols = []
            for idx in selected_indices:
                # 序号从1开始，转换为列表索引（从0开始）
                if isinstance(idx, int) and 1 <= idx <= len(candidates_to_consider):
                    symbol = candidates_to_consider[idx - 1]
                    selected_symbols.append(symbol)
            
            return selected_symbols
        except Exception as e:
            # 解析失败，返回空列表
            PrettyOutput.print(f"LLM符号筛选失败: {e}", OutputType.WARNING)
            return []

    def _semantic_search_files(
        self, user_input: str, keywords: List[str]
    ) -> List[str]:
        """使用LLM进行语义搜索，查找相关文件
        
        Args:
            user_input: 用户输入
            keywords: 关键词列表
            
        Returns:
            相关文件路径列表
        """
        # 获取项目中的文件列表（简化版，只获取已分析的文件）
        known_files = list(self.context_manager.dependency_graph.dependencies.keys())
        known_files.extend(self.context_manager.dependency_graph.dependents.keys())
        
        if not known_files:
            return []
        
        # 限制文件数量
        files_sample = known_files[:30]  # 最多30个文件
        
        file_info = [
            {
                "path": os.path.relpath(f, self.context_manager.project_root),
                "basename": os.path.basename(f),
            }
            for f in files_sample
        ]
        
        prompt = f"""根据以下任务描述和关键词，从文件列表中选择最相关的文件。

任务描述：{user_input}
关键词：{', '.join(keywords)}

文件列表：
{yaml.dump(file_info, allow_unicode=True, default_flow_style=False)}

请返回最相关的5-10个文件路径（YAML数组格式），按相关性排序，并用<FILES>标签包裹。
只返回文件路径数组，例如：
<FILES>
- path/to/file1.py
- path/to/file2.py
</FILES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<FILES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<FILES>\s*(.*?)\s*</FILES>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            file_paths = yaml.safe_load(yaml_content)
            if not isinstance(file_paths, list):
                return []
            
            # 转换为绝对路径
            result = []
            for path in file_paths:
                abs_path = os.path.join(self.context_manager.project_root, path)
                if os.path.exists(abs_path):
                    result.append(abs_path)
            
            return result
        except Exception:
            return []

    def _score_files_with_llm(
        self, user_input: str, files: List[str]
    ) -> Dict[str, float]:
        """使用LLM对文件进行相关性评分
        
        Args:
            user_input: 用户输入
            files: 文件列表
            
        Returns:
            文件路径到相关性分数的字典
        """
        if not files:
            return {}
        
        # 限制文件数量，避免prompt过长
        files_to_score = files[:20]
        
        file_info = [
            {
                "path": os.path.relpath(f, self.context_manager.project_root),
                "basename": os.path.basename(f),
            }
            for f in files_to_score
        ]
        
        prompt = f"""根据以下任务描述，对文件列表中的每个文件进行相关性评分（0-10分）。

任务描述：{user_input}

文件列表：
{yaml.dump(file_info, allow_unicode=True, default_flow_style=False)}

请返回YAML对象，键为文件路径，值为相关性分数（0-10的浮点数），并用<FILE_SCORES>标签包裹。
只返回YAML对象，例如：
<FILE_SCORES>
path/to/file1.py: 8.5
path/to/file2.py: 7.0
path/to/file3.py: 5.5
</FILE_SCORES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<FILE_SCORES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<FILE_SCORES>\s*(.*?)\s*</FILE_SCORES>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            scores = yaml.safe_load(yaml_content)
            if not isinstance(scores, dict):
                return {}
            
            # 转换为绝对路径的键
            result = {}
            for rel_path, score in scores.items():
                abs_path = os.path.join(self.context_manager.project_root, rel_path)
                if abs_path in files_to_score:
                    result[abs_path] = float(score)
            
            # 为未评分的文件设置默认分数
            for f in files_to_score:
                if f not in result:
                    result[f] = 5.0  # 默认中等相关性
            
            return result
        except Exception:
            # 评分失败，返回默认分数
            return {f: 5.0 for f in files_to_score}

    def _score_symbols_with_llm(
        self, user_input: str, symbols: List[Symbol]
    ) -> Dict[Symbol, float]:
        """使用LLM对符号进行相关性评分
        
        Args:
            user_input: 用户输入
            symbols: 符号列表
            
        Returns:
            符号到相关性分数的字典
        """
        if not symbols:
            return {}
        
        # 限制符号数量
        symbols_to_score = symbols[:20]
        
        symbol_info = [
            {
                "name": s.name,
                "kind": s.kind,
                "file": os.path.basename(s.file_path),
                "signature": s.signature or "",
            }
            for s in symbols_to_score
        ]
        
        prompt = f"""根据以下任务描述，对符号列表中的每个符号进行相关性评分（0-10分）。

任务描述：{user_input}

符号列表：
{yaml.dump(symbol_info, allow_unicode=True, default_flow_style=False)}

请返回YAML对象，键为符号名称，值为相关性分数（0-10的浮点数），并用<SYMBOL_SCORES>标签包裹。
只返回YAML对象，例如：
<SYMBOL_SCORES>
symbol1: 9.0
symbol2: 7.5
symbol3: 6.0
</SYMBOL_SCORES>
"""

        try:
            response = self._call_llm(prompt)
            # 从<SYMBOL_SCORES>标签中提取内容
            response = response.strip()
            yaml_match = re.search(r'<SYMBOL_SCORES>\s*(.*?)\s*</SYMBOL_SCORES>', response, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
                # 如果没有找到标签，尝试清理markdown代码块
                if response.startswith("```yaml"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                yaml_content = response.strip()
            
            scores = yaml.safe_load(yaml_content)
            if not isinstance(scores, dict):
                return {}
            
            # 创建符号到分数的映射
            result = {}
            for s in symbols_to_score:
                score = scores.get(s.name, 5.0)  # 默认中等相关性
                result[s] = float(score)
            
            return result
        except Exception:
            # 评分失败，返回默认分数
            return {s: 5.0 for s in symbols_to_score}

    def _find_test_files(self, file_path: str) -> List[str]:
        """查找与文件相关的测试文件
        
        Args:
            file_path: 源文件路径
            
        Returns:
            测试文件路径列表
        """
        test_files = []
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        project_root = self.context_manager.project_root

        # 常见的测试文件命名模式
        test_patterns = [
            f"test_{base_name}.py",
            f"{base_name}_test.py",
            f"test_{base_name}.js",
            f"{base_name}.test.js",
            f"test_{base_name}.ts",
            f"{base_name}.test.ts",
            f"{base_name}_test.rs",
            f"test_{base_name}.go",
        ]

        # 在项目根目录搜索测试文件
        for root, dirs, files in os.walk(project_root):
            # 跳过隐藏目录和常见忽略目录
            dirs[:] = filter_walk_dirs(dirs)

            # 检查是否是测试目录
            if 'test' in root.lower() or 'tests' in root.lower():
                for pattern in test_patterns:
                    if pattern in files:
                        test_file = os.path.join(root, pattern)
                        if os.path.exists(test_file):
                            test_files.append(test_file)

        return test_files[:5]  # 限制数量

    def _call_llm(self, prompt: str) -> str:
        """调用LLM生成响应
        
        Args:
            prompt: 提示词
            
        Returns:
            LLM生成的响应文本
        """
        if not self.llm_model:
            raise ValueError("LLM model not available")
        
        try:
            # 使用chat_until_success方法（BasePlatform的标准接口）
            if hasattr(self.llm_model, 'chat_until_success'):
                response = self.llm_model.chat_until_success(prompt)
                return str(response)
            else:
                # 如果不支持chat_until_success，抛出异常
                raise ValueError("LLM model does not support chat_until_success interface")
        except Exception as e:
            PrettyOutput.print(f"LLM调用失败: {e}", OutputType.WARNING)
            raise

    def format_recommendation(self, recommendation: ContextRecommendation) -> str:
        """格式化推荐结果为可读文本
        
        Args:
            recommendation: 推荐结果
            
        Returns:
            格式化的文本
        """
        lines = ["\n💡 智能上下文推荐:"]
        lines.append("─" * 60)

        if recommendation.reason:
            lines.append(f"📌 推荐原因: {recommendation.reason}")

        if recommendation.recommended_files:
            files_str = "\n   ".join(
                f"• {os.path.relpath(f, self.context_manager.project_root)}"
                for f in recommendation.recommended_files[:5]
            )
            more = len(recommendation.recommended_files) - 5
            if more > 0:
                files_str += f"\n   ... 还有{more}个文件"
            lines.append(f"📁 推荐文件 ({len(recommendation.recommended_files)}个):\n   {files_str}")

        if recommendation.recommended_symbols:
            symbols_str = "\n   ".join(
                f"• {s.kind} `{s.name}` ({os.path.relpath(s.file_path, self.context_manager.project_root)}:{s.line_start})"
                for s in recommendation.recommended_symbols[:5]
            )
            more = len(recommendation.recommended_symbols) - 5
            if more > 0:
                symbols_str += f"\n   ... 还有{more}个符号"
            lines.append(f"🔗 推荐符号 ({len(recommendation.recommended_symbols)}个):\n   {symbols_str}")

        if recommendation.related_tests:
            tests_str = "\n   ".join(
                f"• {os.path.relpath(f, self.context_manager.project_root)}"
                for f in recommendation.related_tests[:3]
            )
            more = len(recommendation.related_tests) - 3
            if more > 0:
                tests_str += f"\n   ... 还有{more}个测试文件"
            lines.append(f"🧪 相关测试 ({len(recommendation.related_tests)}个):\n   {tests_str}")

        lines.append("─" * 60)
        lines.append("")  # 空行

        return "\n".join(lines) if len(lines) > 2 else ""  # 如果没有推荐内容，返回空字符串
